import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ShipmentDirection, ShipmentStatus
from app.models.shipment import Shipment
from app.models.user import User
from app.repositories.shipment_repository import ShipmentRepository
from app.schemas.shipment import ShipmentCreateRequest
from app.utils.exceptions import ForbiddenError, NotFoundError


class ShipmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._shipments = ShipmentRepository(session)

    async def create_shipment(
        self,
        request: ShipmentCreateRequest,
        *,
        user: User,
        accessible_company_ids: list[uuid.UUID],
    ) -> Shipment:
        owning_company_id = request.on_behalf_of_company_id or user.company_id
        if owning_company_id not in accessible_company_ids:
            raise ForbiddenError(
                "You do not have access to create shipments for this company."
            )

        shipment = Shipment(
            company_id=owning_company_id,
            direction=request.direction,
            status=ShipmentStatus.CREATED,
            notes=request.notes,
        )
        return await self._shipments.create(shipment)

    async def get_shipment(
        self, shipment_id: uuid.UUID, *, accessible_company_ids: list[uuid.UUID]
    ) -> Shipment:
        shipment = await self._shipments.get_by_id_scoped(shipment_id, accessible_company_ids)
        if shipment is None:
            raise NotFoundError("Shipment not found.")
        return shipment

    async def list_shipments(
        self,
        *,
        accessible_company_ids: list[uuid.UUID],
        status: ShipmentStatus | None,
        direction: ShipmentDirection | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Shipment], int]:
        return await self._shipments.list_scoped(
            accessible_company_ids,
            status=status,
            direction=direction,
            page=page,
            page_size=page_size,
        )

    async def get_status(
        self, shipment_id: uuid.UUID, *, accessible_company_ids: list[uuid.UUID]
    ) -> ShipmentStatus | None:
        """Used by the SSE status-streaming endpoint's poll loop — returns None (rather
        than raising) once the shipment stops being accessible/found, so the caller can
        end the stream cleanly instead of surfacing an error on an already-open
        connection."""
        return await self._shipments.get_status_scoped(shipment_id, accessible_company_ids)
