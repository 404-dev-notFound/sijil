import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OriginQualificationStatus
from app.models.line_item import LineItem
from app.models.origin_determination import OriginDetermination
from app.models.shipment import Shipment
from app.repositories.cepa_rules_repository import CepaRule, CepaRulesRepository
from app.repositories.line_item_repository import LineItemRepository
from app.repositories.origin_determination_repository import OriginDeterminationRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.services.line_item_helpers import effective_hs_code

_CENTS = Decimal("0.01")


@dataclass
class _Evaluation:
    agreement: str | None
    qualifies: OriginQualificationStatus
    reasoning: str
    required_documents: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    estimated_duty_savings_amount: Decimal | None = None


def _evaluate(
    *,
    rule: CepaRule | None,
    hs_code: str | None,
    local_content_value: Decimal | None,
    total_value: Decimal | None,
) -> _Evaluation:
    """Pure rules-of-origin logic (architecture doc Section 6.4), no repository access
    of its own — mirrors ConsistencyService's compute_shipment_status pattern so the
    actual decision logic is unit-testable without a database. Missing value-content
    data is explicitly INSUFFICIENT_DATA, never silently DOES_NOT_QUALIFY — a false
    negative costs the user real money.
    """
    if rule is None:
        reasoning = (
            "Line item has not been classified yet."
            if hs_code is None
            else "No covered CEPA agreement applies to this origin/destination/"
            "HS-code combination."
        )
        return _Evaluation(
            agreement=None, qualifies=OriginQualificationStatus.NOT_APPLICABLE, reasoning=reasoning
        )

    if local_content_value is None or total_value is None:
        missing_fields = [
            field_name
            for field_name, value in (
                ("local_content_value", local_content_value),
                ("total_value", total_value),
            )
            if value is None
        ]
        return _Evaluation(
            agreement=rule.agreement,
            qualifies=OriginQualificationStatus.INSUFFICIENT_DATA,
            reasoning=(
                "Value-content breakdown required to determine origin qualification "
                "under this agreement."
            ),
            required_documents=list(rule.required_documents),
            missing_fields=missing_fields,
        )

    rvc_percent = (local_content_value / total_value) * 100
    threshold = rule.regional_value_content_threshold_percent
    qualifies_bool = rvc_percent >= threshold
    comparison = "exceeds" if qualifies_bool else "does not meet"
    reasoning = (
        f"Regional value content of {round(rvc_percent)}% {comparison} the "
        f"{threshold}% threshold required for this HS heading under the agreement's "
        "origin rules."
    )

    savings_amount = None
    if qualifies_bool:
        duty_rate_delta = Decimal(rule.duty_rate_without_percent - rule.duty_rate_with_percent)
        savings_amount = (total_value * duty_rate_delta / Decimal(100)).quantize(_CENTS)

    return _Evaluation(
        agreement=rule.agreement,
        qualifies=(
            OriginQualificationStatus.QUALIFIES
            if qualifies_bool
            else OriginQualificationStatus.DOES_NOT_QUALIFY
        ),
        reasoning=reasoning,
        required_documents=list(rule.required_documents),
        estimated_duty_savings_amount=savings_amount,
    )


class CEPAOriginService:
    """Per-agreement rules-of-origin determination for each of a shipment's line
    items (architecture doc Section 6.4) — the actual decision logic lives in the
    pure _evaluate() function above; this class only handles fetching and persisting.
    Worker-only, same rationale as ClassificationService/PermitTriageService
    (architecture doc Section 14).
    """

    def __init__(
        self, session: AsyncSession, *, rules: CepaRulesRepository | None = None
    ) -> None:
        self._line_items = LineItemRepository(session)
        self._shipments = ShipmentRepository(session)
        self._origins = OriginDeterminationRepository(session)
        self._rules = rules or CepaRulesRepository()

    async def determine_shipment(self, shipment_id: uuid.UUID) -> None:
        shipment = await self._shipments.get_by_id(shipment_id)
        if shipment is None:
            return
        for line_item in await self._line_items.list_by_shipment(shipment_id):
            await self._determine_line_item(line_item, shipment)

    async def _determine_line_item(
        self, line_item: LineItem, shipment: Shipment
    ) -> OriginDetermination:
        existing = await self._origins.get_by_line_item_id(line_item.id)
        local_content_value = existing.local_content_value if existing else None
        total_value = existing.total_value if existing else None
        value_currency = existing.value_currency if existing else None

        hs_code = effective_hs_code(line_item)
        rule = (
            self._rules.find_matching(
                hs_code=hs_code,
                origin_country=shipment.origin_country,
                destination_country=shipment.destination_country,
            )
            if hs_code is not None
            else None
        )

        evaluation = _evaluate(
            rule=rule,
            hs_code=hs_code,
            local_content_value=local_content_value,
            total_value=total_value,
        )

        return await self._origins.upsert(
            line_item.id,
            agreement=evaluation.agreement,
            qualifies=evaluation.qualifies,
            reasoning=evaluation.reasoning,
            required_documents=evaluation.required_documents,
            missing_fields=evaluation.missing_fields,
            estimated_duty_savings_amount=evaluation.estimated_duty_savings_amount,
            estimated_duty_savings_currency=(
                value_currency if evaluation.estimated_duty_savings_amount is not None else None
            ),
            local_content_value=local_content_value,
            total_value=total_value,
            value_currency=value_currency,
        )
