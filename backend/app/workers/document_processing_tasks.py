import asyncio
import uuid

from app.config.database import async_session_factory, engine
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
                await DocumentExtractionService(session).extract(document_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
