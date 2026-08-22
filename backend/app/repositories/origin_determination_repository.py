import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OriginQualificationStatus
from app.models.line_item import LineItem
from app.models.origin_determination import OriginDetermination
from app.models.shipment import Shipment


class OriginDeterminationRepository:
    """Same tenant-isolation pattern as ClassificationResultRepository (architecture
    doc Section 14): upsert is worker-only (app/services/cepa_origin_service.py); the
    API-facing paths use the scoped method below.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        line_item_id: uuid.UUID,
        *,
        agreement: str | None,
        qualifies: OriginQualificationStatus,
        reasoning: str,
        required_documents: list[str],
        missing_fields: list[str],
        estimated_duty_savings_amount: Decimal | None,
        estimated_duty_savings_currency: str | None,
        local_content_value: Decimal | None,
        total_value: Decimal | None,
        value_currency: str | None,
    ) -> OriginDetermination:
        """Worker-only. A re-determination overwrites the existing row in place — one
        determination per line item, never a growing history (same pattern as
        ClassificationResultRepository.upsert)."""
        result = await self._session.execute(
            select(OriginDetermination).where(OriginDetermination.line_item_id == line_item_id)
        )
        determination = result.scalar_one_or_none()
        if determination is None:
            determination = OriginDetermination(line_item_id=line_item_id)
            self._session.add(determination)

        determination.agreement = agreement
        determination.qualifies = qualifies
        determination.reasoning = reasoning
        determination.required_documents = required_documents
        determination.missing_fields = missing_fields
        determination.estimated_duty_savings_amount = estimated_duty_savings_amount
        determination.estimated_duty_savings_currency = estimated_duty_savings_currency
        determination.local_content_value = local_content_value
        determination.total_value = total_value
        determination.value_currency = value_currency
        await self._session.flush()
        return determination

    async def get_by_line_item_id(
        self, line_item_id: uuid.UUID
    ) -> OriginDetermination | None:
        """No tenant scope — worker-only, so a re-determination can read back a
        previously user-supplied value-content breakdown without asking again."""
        result = await self._session.execute(
            select(OriginDetermination).where(OriginDetermination.line_item_id == line_item_id)
        )
        return result.scalar_one_or_none()

    async def get_by_line_item_id_scoped(
        self, line_item_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> OriginDetermination | None:
        stmt = (
            select(OriginDetermination)
            .join(LineItem, OriginDetermination.line_item_id == LineItem.id)
            .join(Shipment, LineItem.shipment_id == Shipment.id)
            .where(
                OriginDetermination.line_item_id == line_item_id,
                Shipment.company_id.in_(company_ids),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
