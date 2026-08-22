import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discrepancy import Discrepancy
from app.repositories.discrepancy_repository import DiscrepancyRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.utils.exceptions import NotFoundError


class DiscrepancyService:
    """API-facing, tenant-scoped — every method resolves access via
    accessible_company_ids the same way ShipmentService/DocumentService/
    LineItemService do (architecture doc Section 14). The worker-side comparison
    pipeline lives in ConsistencyService instead, which is never called from here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._discrepancies = DiscrepancyRepository(session)
        self._shipments = ShipmentRepository(session)

    async def list_discrepancies(
        self, shipment_id: uuid.UUID, *, accessible_company_ids: list[uuid.UUID]
    ) -> list[Discrepancy]:
        # A shipment with no discrepancies yet is a legitimate empty list; a shipment
        # that isn't accessible at all should 404 (same rationale as
        # LineItemService.list_line_items).
        shipment = await self._shipments.get_by_id_scoped(shipment_id, accessible_company_ids)
        if shipment is None:
            raise NotFoundError("Shipment not found.")
        return await self._discrepancies.list_by_shipment_scoped(
            shipment_id, accessible_company_ids
        )

    async def acknowledge(
        self,
        *,
        shipment_id: uuid.UUID,
        discrepancy_id: uuid.UUID,
        accessible_company_ids: list[uuid.UUID],
        user_id: uuid.UUID,
    ) -> Discrepancy:
        discrepancy = await self._discrepancies.get_by_id_scoped(
            discrepancy_id, accessible_company_ids
        )
        if discrepancy is None or discrepancy.shipment_id != shipment_id:
            raise NotFoundError("Discrepancy not found.")

        discrepancy.acknowledged = True
        discrepancy.acknowledged_by_user_id = user_id
        discrepancy.acknowledged_at = datetime.now(UTC)
        return discrepancy
