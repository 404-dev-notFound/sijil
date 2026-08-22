import asyncio
import uuid

from app.config.database import async_session_factory, engine
from app.services.permit_triage_service import PermitTriageService
from app.workers.celery_app import celery_app


@celery_app.task(name="triage_shipment_permits")
def triage_shipment_permits_task(shipment_id: str) -> None:
    """Chained after classification completes (architecture doc Section 11.2: "Runs
    as a fast, synchronous-feeling step... immediately following classification") —
    from classification_tasks.py's classify_shipment_from_document/
    reclassify_line_item, and from line_item_service.py's override endpoint (an
    override changes the effective HS code permit determination is based on). See
    document_processing_tasks.py's docstring for why disposing the engine pool at the
    end of every task is required here too.
    """
    asyncio.run(_triage_shipment_permits(uuid.UUID(shipment_id)))


async def _triage_shipment_permits(shipment_id: uuid.UUID) -> None:
    try:
        async with async_session_factory() as session:
            try:
                await PermitTriageService(session).triage_shipment(shipment_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
