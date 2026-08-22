import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.shipment import Shipment


class DocumentRepository:
    """Scoped via a join to Shipment.company_id — same mandatory-tenant-scope rule as
    ShipmentRepository (architecture doc Section 14)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.flush()
        return document

    async def get_by_id_scoped(
        self, document_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> Document | None:
        stmt = (
            select(Document)
            .join(Shipment, Document.shipment_id == Shipment.id)
            .where(Document.id == document_id, Shipment.company_id.in_(company_ids))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_shipment_scoped(
        self, shipment_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> list[Document]:
        stmt = (
            select(Document)
            .join(Shipment, Document.shipment_id == Shipment.id)
            .where(Document.shipment_id == shipment_id, Shipment.company_id.in_(company_ids))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        """No tenant scope — for the background worker only, which operates on a
        document_id it already enqueued itself, not on client-supplied input. Never
        call this from an API-reachable code path (architecture doc Section 14)."""
        result = await self._session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def list_by_shipment(self, shipment_id: uuid.UUID) -> list[Document]:
        """No tenant scope — worker-only, same rationale as get_by_id above."""
        result = await self._session.execute(
            select(Document).where(Document.shipment_id == shipment_id)
        )
        return list(result.scalars().all())
