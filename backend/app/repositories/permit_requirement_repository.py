import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permit_requirement import PermitRequirement
from app.models.shipment import Shipment


class PermitRequirementRepository:
    """Same tenant-isolation pattern as DiscrepancyRepository (architecture doc
    Section 14): _scoped methods join through Shipment.company_id for the
    API-reachable path; replace_for_shipment below is worker-only (app/services/
    permit_triage_service.py), never called from an API route.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_shipment(
        self, shipment_id: uuid.UUID, requirements: list[PermitRequirement]
    ) -> list[PermitRequirement]:
        """Worker-only. Delete-then-insert on every re-triage — unlike Discrepancy,
        a permit requirement has no per-row user state (no acknowledge flow) to
        preserve, so a clean replace is simplest and correct."""
        await self._session.execute(
            delete(PermitRequirement).where(PermitRequirement.shipment_id == shipment_id)
        )
        for requirement in requirements:
            self._session.add(requirement)
        await self._session.flush()
        return requirements

    async def list_by_shipment_scoped(
        self, shipment_id: uuid.UUID, company_ids: list[uuid.UUID]
    ) -> list[PermitRequirement]:
        stmt = (
            select(PermitRequirement)
            .join(Shipment, PermitRequirement.shipment_id == Shipment.id)
            .where(
                PermitRequirement.shipment_id == shipment_id,
                Shipment.company_id.in_(company_ids),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
