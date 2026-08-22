import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discrepancy import Discrepancy
from app.models.shipment import Shipment


class DiscrepancyRepository:
    """Same tenant-isolation pattern as DocumentRepository/LineItemRepository
    (architecture doc Section 14): _scoped methods join through Shipment.company_id
    for every API-reachable path; the unscoped methods below are worker-only
    (app/services/consistency_service.py), never called from an API route.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, discrepancy: Discrepancy) -> Discrepancy:
        self._session.add(discrepancy)
        await self._session.flush()
        return discrepancy

    async def delete(self, discrepancy: Discrepancy) -> None:
        await self._session.delete(discrepancy)

    async def list_by_shipment(self, shipment_id: uuid.UUID) -> list[Discrepancy]:
        """No tenant scope — worker-only."""
        result = await self._session.execute(
            select(Discrepancy).where(Discrepancy.shipment_id == shipment_id)
        )
        return list(result.scalars().all())

    async def list_by_shipment_scoped(
        self, shipment_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> list[Discrepancy]:
        stmt = (
            select(Discrepancy)
            .join(Shipment, Discrepancy.shipment_id == Shipment.id)
            .where(Discrepancy.shipment_id == shipment_id, Shipment.company_id.in_(company_ids))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_scoped(
        self, discrepancy_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> Discrepancy | None:
        stmt = (
            select(Discrepancy)
            .join(Shipment, Discrepancy.shipment_id == Shipment.id)
            .where(Discrepancy.id == discrepancy_id, Shipment.company_id.in_(company_ids))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
