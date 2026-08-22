import asyncio
import uuid

from app.config.database import async_session_factory, engine
from app.services.report_generation_service import ReportGenerationService
from app.workers.celery_app import celery_app


@celery_app.task(name="generate_report")
def generate_report_task(report_id: str) -> None:
    """Triggered by POST /shipments/{id}/report (app/services/report_service.py). See
    document_processing_tasks.py's docstring for why disposing the engine pool at the
    end of every task is required here too.
    """
    asyncio.run(_generate_report(uuid.UUID(report_id)))


async def _generate_report(report_id: uuid.UUID) -> None:
    try:
        async with async_session_factory() as session:
            try:
                await ReportGenerationService(session).generate(report_id)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
