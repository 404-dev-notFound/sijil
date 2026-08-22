import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.line_item import LineItem
from app.repositories.line_item_repository import LineItemRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.utils.exceptions import ConflictError, NotFoundError
from app.workers.celery_app import celery_app


class LineItemService:
    """API-facing, tenant-scoped — every method resolves access via
    accessible_company_ids the same way ShipmentService/DocumentService do
    (architecture doc Section 14). The worker-side classification pipeline lives in
    ClassificationService instead, which is never called from here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._line_items = LineItemRepository(session)
        self._shipments = ShipmentRepository(session)

    async def list_line_items(
        self, shipment_id: uuid.UUID, *, accessible_company_ids: list[uuid.UUID]
    ) -> list[LineItem]:
        # A shipment with zero line items yet is a legitimate empty list; a shipment
        # that isn't accessible at all should 404, same as GET /shipments/{id} does —
        # list_by_shipment_scoped alone can't tell the two apart (an inaccessible
        # shipment_id also just yields zero matching rows).
        shipment = await self._shipments.get_by_id_scoped(shipment_id, accessible_company_ids)
        if shipment is None:
            raise NotFoundError("Shipment not found.")
        return await self._line_items.list_by_shipment_scoped(shipment_id, accessible_company_ids)

    async def get_line_item(
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

    async def override_classification(
        self,
        *,
        shipment_id: uuid.UUID,
        line_item_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
        hs_code: str,
        reason: str | None,
    ) -> LineItem:
        line_item = await self.get_line_item(
            shipment_id, line_item_id, accessible_company_ids=accessible_company_ids
        )
        if line_item.classification is None:
            raise ConflictError("This line item has not been classified yet.")

        # The AI suggestion is never overwritten — only the override fields change
        # (API SPEC Section 8: both are retained for audit purposes).
        line_item.classification.user_override_hs_code = hs_code
        line_item.classification.user_override_reason = reason
        return line_item

    async def trigger_reclassify(
        self,
        *,
        shipment_id: uuid.UUID,
        line_item_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
    ) -> None:
        line_item = await self.get_line_item(
            shipment_id, line_item_id, accessible_company_ids=accessible_company_ids
        )
        # Commit before enqueueing — same rationale as document_service.py's
        # upload_document (the worker reads from its own connection).
        await self._session.commit()
        celery_app.send_task("reclassify_line_item", args=[str(line_item.id)])
