import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.line_item import LineItem
from app.models.shipment import Shipment


class LineItemRepository:
    """Same tenant-isolation pattern as DocumentRepository (architecture doc Section
    14): _scoped methods join through Shipment.company_id for every API-reachable
    path; the unscoped methods below are worker-only (app/services/
    classification_service.py), never called from an API route.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_shipment(
        self, shipment_id: uuid.UUID, line_items: list[LineItem]
    ) -> list[LineItem]:
        """Worker-only. Deletes existing line items for the shipment then inserts the
        freshly extracted ones — idempotent if extraction re-runs (e.g. after a manual
        document correction), rather than accumulating duplicates."""
        await self._session.execute(delete(LineItem).where(LineItem.shipment_id == shipment_id))
        for item in line_items:
            self._session.add(item)
        await self._session.flush()
        return line_items

    async def get_by_id(self, line_item_id: uuid.UUID) -> LineItem | None:
        """No tenant scope — worker-only."""
        result = await self._session.execute(
            select(LineItem).where(LineItem.id == line_item_id)
        )
        return result.scalar_one_or_none()

    async def list_by_shipment(self, shipment_id: uuid.UUID) -> list[LineItem]:
        """No tenant scope — worker-only."""
        result = await self._session.execute(
            select(LineItem).where(LineItem.shipment_id == shipment_id)
        )
        return list(result.scalars().all())

    async def get_by_id_scoped(
        self, line_item_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> LineItem | None:
        stmt = (
            select(LineItem)
            .join(Shipment, LineItem.shipment_id == Shipment.id)
            .where(LineItem.id == line_item_id, Shipment.company_id.in_(company_ids))
            .options(selectinload(LineItem.classification))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_shipment_scoped(
        self, shipment_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> list[LineItem]:
        stmt = (
            select(LineItem)
            .join(Shipment, LineItem.shipment_id == Shipment.id)
            .where(LineItem.shipment_id == shipment_id, Shipment.company_id.in_(company_ids))
            .options(selectinload(LineItem.classification))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
