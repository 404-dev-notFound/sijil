import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permit_requirement import PermitRequirement
from app.repositories.permit_requirement_repository import PermitRequirementRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.utils.exceptions import NotFoundError


class PermitService:
    """API-facing, tenant-scoped — same rationale as DiscrepancyService/
    LineItemService (architecture doc Section 14). The worker-side triage pipeline
    lives in PermitTriageService instead, which is never called from here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._permits = PermitRequirementRepository(session)
        self._shipments = ShipmentRepository(session)

    async def list_permits(
        self, shipment_id: uuid.UUID, *, accessible_company_ids: list[uuid.UUID]
    ) -> list[PermitRequirement]:
        # A shipment with no permits required yet is a legitimate empty list; a
        # shipment that isn't accessible at all should 404 (same rationale as
        # DiscrepancyService.list_discrepancies).
        shipment = await self._shipments.get_by_id_scoped(shipment_id, accessible_company_ids)
        if shipment is None:
            raise NotFoundError("Shipment not found.")
        return await self._permits.list_by_shipment_scoped(shipment_id, accessible_company_ids)
