import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import ShipmentDirection, ShipmentStatus
from app.models.shipment import Shipment


class ShipmentRepository:
    """Every read method takes a mandatory `company_ids` scope — the caller (service
    layer) resolves this to either [own company_id], for a plain company user, or
    [own company_id] + managed company ids, for a broker. There is deliberately no
    method that queries shipments without this scope (architecture doc Section 14).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, shipment: Shipment) -> Shipment:
        self._session.add(shipment)
        await self._session.flush()
        return shipment

    async def get_by_id_scoped(
        self, shipment_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> Shipment | None:
        stmt = (
            select(Shipment)
            .where(Shipment.id == shipment_id, Shipment.company_id.in_(company_ids))
            .options(selectinload(Shipment.documents))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_scoped(
        self,
        company_ids: list[uuid.UUID],
        *,
        status: ShipmentStatus | None = None,
        direction: ShipmentDirection | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[Shipment], int]:
        filters: list[ColumnElement[bool]] = [Shipment.company_id.in_(company_ids)]
        if status is not None:
            filters.append(Shipment.status == status)
        if direction is not None:
            filters.append(Shipment.direction == direction)

        count_stmt = select(func.count()).select_from(Shipment).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(Shipment)
            .where(*filters)
            .order_by(Shipment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total
