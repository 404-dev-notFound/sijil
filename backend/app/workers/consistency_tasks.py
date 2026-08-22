import asyncio
import uuid

from app.config.database import async_session_factory, engine
from app.services.consistency_service import ConsistencyService
from app.workers.celery_app import celery_app


@celery_app.task(name="check_shipment_consistency")
def check_shipment_consistency_task(shipment_id: str) -> None:
    """Chained from document_processing_tasks.py whenever any document finishes
    extraction, and from document_service.py's manual-correction endpoint (any
    doc_type — unlike classification, consistency checking needs the packing
    list/bill of lading/air waybill too, not just the commercial invoice). See
    document_processing_tasks.py's docstring for why disposing the engine pool at the
    end of every task is required here too.
    """
    asyncio.run(_check_shipment_consistency(uuid.UUID(shipment_id)))


async def _check_shipment_consistency(shipment_id: uuid.UUID) -> None:
    try:
        async with async_session_factory() as session:
            try:
                await ConsistencyService(session).check_shipment(shipment_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
