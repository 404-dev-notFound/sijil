import uuid
from datetime import datetime

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

    async def get_by_id(self, shipment_id: uuid.UUID) -> Shipment | None:
        """No tenant scope — for the background worker only (architecture doc Section
        14). Never call this from an API-reachable code path."""
        result = await self._session.execute(select(Shipment).where(Shipment.id == shipment_id))
        return result.scalar_one_or_none()

    async def count_since(self, company_id: uuid.UUID, since: datetime) -> int:
        """Used by BillingService to derive shipments_used_this_period — always scoped
        to exactly one company. Billing is per-company, never aggregated across a
        broker's managed companies, so this deliberately takes a single company_id
        rather than the usual company_ids scope list."""
        stmt = (
            select(func.count())
            .select_from(Shipment)
            .where(Shipment.company_id == company_id, Shipment.created_at >= since)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_status_scoped(
        self, shipment_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> ShipmentStatus | None:
        """Lightweight scalar read for the SSE status-streaming endpoint's poll loop —
        deliberately not the full ORM entity, so each poll is a fresh committed-data
        read under READ COMMITTED with no identity-map staleness to worry about."""
        stmt = select(Shipment.status).where(
            Shipment.id == shipment_id, Shipment.company_id.in_(company_ids)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
