import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report
from app.models.shipment import Shipment


class ReportRepository:
    """Same tenant-isolation pattern as the other repositories (architecture doc
    Section 14): get_by_id_scoped is the API-reachable path; get_by_id is
    worker-only (app/services/report_generation_service.py).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, report: Report) -> Report:
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_by_id(self, report_id: uuid.UUID) -> Report | None:
        """No tenant scope — worker-only."""
        result = await self._session.execute(select(Report).where(Report.id == report_id))
        return result.scalar_one_or_none()

    async def get_by_id_scoped(
        self, report_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> Report | None:
        stmt = (
            select(Report)
            .join(Shipment, Report.shipment_id == Shipment.id)
            .where(Report.id == report_id, Shipment.company_id.in_(company_ids))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
