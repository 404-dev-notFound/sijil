import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permit_requirement import PermitRequirement
from app.repositories.line_item_repository import LineItemRepository
from app.repositories.permit_requirement_repository import PermitRequirementRepository
from app.repositories.permit_rules_repository import PermitRule, PermitRulesRepository
from app.services.line_item_helpers import effective_hs_code


class PermitTriageService:
    """Maps each line item's effective HS code to applicable UAE regulators
    (architecture doc Section 6.3) — the user's override always wins over the AI's
    suggestion when determining which permits apply, same "effective code" concept
    used everywhere else classification results are consumed. A line item with no
    classification yet (or hs_code still null, e.g. requires_manual_review) is simply
    skipped rather than guessed at. Worker-only, same rationale as
    ClassificationService/ConsistencyService (architecture doc Section 14).
    """

    def __init__(
        self, session: AsyncSession, *, rules: PermitRulesRepository | None = None
    ) -> None:
        self._line_items = LineItemRepository(session)
        self._permits = PermitRequirementRepository(session)
        self._rules = rules or PermitRulesRepository()

    async def triage_shipment(self, shipment_id: uuid.UUID) -> None:
        line_items = await self._line_items.list_by_shipment(shipment_id)

        # Grouped by (regulator, permit_type) so a shipment with several line items
        # needing the same permit produces one row listing every item it applies to,
        # not duplicate rows.
        grouped: dict[tuple[str, str], PermitRequirement] = {}
        for line_item in line_items:
            hs_code = effective_hs_code(line_item)
            if hs_code is None:
                continue
            for rule in self._rules.find_matching(hs_code):
                key = (rule.regulator, rule.permit_type)
                requirement = grouped.get(key)
                if requirement is None:
                    requirement = _to_permit_requirement(shipment_id, rule)
                    grouped[key] = requirement
                requirement.applies_to_line_items.append(str(line_item.id))

        await self._permits.replace_for_shipment(shipment_id, list(grouped.values()))


def _to_permit_requirement(shipment_id: uuid.UUID, rule: PermitRule) -> PermitRequirement:
    return PermitRequirement(
        shipment_id=shipment_id,
        regulator=rule.regulator,
        permit_type=rule.permit_type,
        applies_to_line_items=[],
        estimated_processing_time_days=rule.estimated_processing_time_days,
        reference_link=rule.reference_link,
    )
