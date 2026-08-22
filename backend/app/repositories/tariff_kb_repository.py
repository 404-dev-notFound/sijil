from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tariff_heading import TariffHeading


class TariffKBRepository:
    """Vector search over the tariff knowledge base (architecture doc Section 6.1 / 9's
    TariffKnowledgeBaseRepository). Not tenant-scoped — the tariff schedule is shared
    reference data, not per-company data.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, heading: TariffHeading) -> TariffHeading:
        self._session.add(heading)
        await self._session.flush()
        return heading

    async def count(self) -> int:
        result = await self._session.execute(select(TariffHeading.id))
        return len(result.scalars().all())

    async def vector_search(
        self, embedding: list[float], *, limit: int
    ) -> list[tuple[TariffHeading, float]]:
        """Nearest headings by cosine distance, closest first. Distance is returned
        alongside each heading (0 = identical, larger = less similar) so the caller
        (ClassificationService) can pass it to the LLM as a similarity signal."""
        distance = TariffHeading.embedding.cosine_distance(embedding).label("distance")
        stmt = select(TariffHeading, distance).order_by(distance).limit(limit)
        result = await self._session.execute(stmt)
        return [(row.TariffHeading, row.distance) for row in result]
