import asyncio
import uuid

from app.config.database import async_session_factory, engine
from app.repositories.line_item_repository import LineItemRepository
from app.services.classification_service import ClassificationService
from app.services.line_item_extraction_service import LineItemExtractionService
from app.workers.celery_app import celery_app


@celery_app.task(name="classify_shipment_from_document")
def classify_shipment_from_document_task(document_id: str) -> None:
    """Chained from document_processing_tasks.py once a commercial invoice document
    reaches EXTRACTED (architecture doc Section 11.1: "If all shipment docs extracted,
    trigger next stage... Enqueue classification"). See document_processing_tasks.py's
    docstring for why disposing the engine pool at the end of every task is required
    here too — same cross-event-loop issue applies to every Celery task in this app.
    """
    asyncio.run(_classify_shipment_from_document(uuid.UUID(document_id)))


async def _classify_shipment_from_document(document_id: uuid.UUID) -> None:
    shipment_id: uuid.UUID | None = None
    try:
        async with async_session_factory() as session:
            try:
                line_items = await LineItemExtractionService(session).materialize_from_document(
                    document_id
                )
                if line_items:
                    shipment_id = line_items[0].shipment_id
                    await ClassificationService(session).classify_shipment(shipment_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        # Chained after commit, not inside the transaction above — same "commit
        # before enqueue" rule as document_processing_tasks.py (architecture doc
        # Section 11.2: permit triage and CEPA origin both run immediately following
        # classification).
        if shipment_id is not None:
            celery_app.send_task("triage_shipment_permits", args=[str(shipment_id)])
            celery_app.send_task("determine_shipment_origin", args=[str(shipment_id)])
    finally:
        await engine.dispose()


@celery_app.task(name="reclassify_line_item")
def reclassify_line_item_task(line_item_id: str) -> None:
    """Triggered by POST .../line-items/{id}/reclassify (app/services/
    line_item_service.py) — re-runs classification for a single line item, e.g. after
    the underlying extracted description was corrected."""
    asyncio.run(_reclassify_line_item(uuid.UUID(line_item_id)))


async def _reclassify_line_item(line_item_id: uuid.UUID) -> None:
    shipment_id: uuid.UUID | None = None
    try:
        async with async_session_factory() as session:
            try:
                line_item = await LineItemRepository(session).get_by_id(line_item_id)
                if line_item is not None:
                    shipment_id = line_item.shipment_id
                    await ClassificationService(session).classify(line_item)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        # A reclassify can change this line item's HS code, which can change which
        # permits apply and which CEPA agreement (if any) covers it.
        if shipment_id is not None:
            celery_app.send_task("triage_shipment_permits", args=[str(shipment_id)])
            celery_app.send_task("determine_shipment_origin", args=[str(shipment_id)])
    finally:
        await engine.dispose()
