import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OriginQualificationStatus
from app.models.line_item import LineItem
from app.models.origin_determination import OriginDetermination
from app.repositories.line_item_repository import LineItemRepository
from app.utils.exceptions import NotFoundError
from app.workers.celery_app import celery_app


class OriginService:
    """API-facing, tenant-scoped — same rationale as DiscrepancyService/
    PermitService/LineItemService (architecture doc Section 14). The worker-side
    determination pipeline lives in CEPAOriginService instead, which is never called
    from here — submitting a value breakdown stores the raw numbers via the already
    tenant-scoped LineItem fetch and defers recomputing qualification to the worker,
    same pattern as a classification override.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._line_items = LineItemRepository(session)

    async def get_origin(
        self,
        *,
        shipment_id: uuid.UUID,
        line_item_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
    ) -> OriginDetermination:
        line_item = await self._get_line_item(
            shipment_id, line_item_id, accessible_company_ids=accessible_company_ids
        )
        if line_item.origin_determination is None:
            raise NotFoundError(
                "No origin determination available yet for this line item."
            )
        return line_item.origin_determination

    async def submit_value_breakdown(
        self,
        *,
        shipment_id: uuid.UUID,
        line_item_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
        local_content_value: Decimal,
        total_value: Decimal,
        currency: str,
    ) -> OriginDetermination:
        line_item = await self._get_line_item(
            shipment_id, line_item_id, accessible_company_ids=accessible_company_ids
        )

        determination = line_item.origin_determination
        if determination is None:
            # A placeholder the worker overwrites momentarily — recomputing
            # qualification from the values below is CEPAOriginService's job, not
            # this API-facing service's (architecture doc Section 14 layering).
            determination = OriginDetermination(
                line_item_id=line_item.id,
                qualifies=OriginQualificationStatus.INSUFFICIENT_DATA,
                reasoning="Awaiting recalculation.",
            )
            self._session.add(determination)

        determination.local_content_value = local_content_value
        determination.total_value = total_value
        determination.value_currency = currency

        # Commit before enqueueing — same rationale as line_item_service.py's
        # override_classification (the worker reads from its own connection).
        await self._session.commit()
        celery_app.send_task("determine_shipment_origin", args=[str(shipment_id)])

        return determination

    async def _get_line_item(
        self,
        shipment_id: uuid.UUID,
        line_item_id: uuid.UUID,
        *,
        accessible_company_ids: list[uuid.UUID],
    ) -> LineItem:
        line_item = await self._line_items.get_by_id_scoped(line_item_id, accessible_company_ids)
        if line_item is None or line_item.shipment_id != shipment_id:
            raise NotFoundError("Line item not found.")
        return line_item
