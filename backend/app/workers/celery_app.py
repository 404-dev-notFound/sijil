from celery import Celery

from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery("sijil", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # A string reference, not an actual import — keeps this module from depending on
    # services/ (services/document_service.py depends on *this* module to enqueue
    # tasks by name, so the reverse import would be circular). Celery resolves and
    # imports it lazily inside each worker process at startup.
    imports=("app.workers.document_processing_tasks",),
)

# Phase 2: document_processing_tasks.py registers "process_document" against this app.
# Phase 7: report_generation_tasks.py adds "generate_report" the same way. Workers call
# services/ directly, not through the API layer (architecture doc Section 5).
