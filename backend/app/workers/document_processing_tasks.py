import asyncio
import uuid

from app.config.database import async_session_factory, engine
from app.models.enums import DocumentStatus, DocumentType
from app.services.document_extraction_service import DocumentExtractionService
from app.workers.celery_app import celery_app


@celery_app.task(name="process_document")
def process_document_task(document_id: str) -> None:
    """Entry point Celery invokes in the worker process (a fresh OS process per the
    architecture doc Section 11.1 sequence diagram's Worker participant, though a real
    worker handles many tasks over its lifetime rather than exiting after one).

    Each call opens its own event loop via asyncio.run — the module-level async engine
    (app/config/database.py) is a long-lived singleton whose connection pool binds to
    whichever event loop first used it, so a connection acquired in this loop cannot
    survive into the next task's loop. Disposing the pool at the end of every task
    forces the next task to lazily open fresh connections on its own new loop instead
    of reusing now-invalid ones (SQLAlchemy's documented pattern for an async engine
    used across multiple asyncio.run() boundaries).
    """
    asyncio.run(_process_document(uuid.UUID(document_id)))


async def _process_document(document_id: uuid.UUID) -> None:
    try:
        async with async_session_factory() as session:
            try:
                document = await DocumentExtractionService(session).extract(document_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        # Chained after commit, not inside the transaction above — the downstream
        # workers read this document from their own connections and must never
        # dequeue a task before the row they depend on is durably committed (same
        # "commit before enqueue" rule as document_service.py's upload_document).
        if document is not None and document.status in (
            DocumentStatus.EXTRACTED,
            DocumentStatus.NEEDS_MANUAL_REVIEW,
        ):
            if document.doc_type == DocumentType.COMMERCIAL_INVOICE:
                celery_app.send_task(
                    "classify_shipment_from_document", args=[str(document.id)]
                )
            # Every doc_type, not just the invoice — consistency checking needs the
            # packing list/bill of lading/air waybill too (architecture doc Section
            # 6.2), and runs against whatever's extracted so far even if this
            # particular document ended up needing manual review.
            celery_app.send_task(
                "check_shipment_consistency", args=[str(document.shipment_id)]
            )
    finally:
        await engine.dispose()
