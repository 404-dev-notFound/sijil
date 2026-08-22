import asyncio
import uuid

from app.config.database import async_session_factory, engine
from app.services.cepa_origin_service import CEPAOriginService
from app.workers.celery_app import celery_app


@celery_app.task(name="determine_shipment_origin")
def determine_shipment_origin_task(shipment_id: str) -> None:
    """Chained alongside triage_shipment_permits — from classification_tasks.py's
    classify_shipment_from_document/reclassify_line_item, from line_item_service.py's
    override endpoint, and from origin_service.py's value-breakdown endpoint (supplying
    the breakdown is what turns INSUFFICIENT_DATA into an actual determination). See
    document_processing_tasks.py's docstring for why disposing the engine pool at the
    end of every task is required here too.
    """
    asyncio.run(_determine_shipment_origin(uuid.UUID(shipment_id)))


async def _determine_shipment_origin(shipment_id: uuid.UUID) -> None:
    try:
        async with async_session_factory() as session:
            try:
                await CEPAOriginService(session).determine_shipment(shipment_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
