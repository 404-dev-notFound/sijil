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
)

# Phase 2+: document_processing_tasks.py and report_generation_tasks.py register their
# tasks against this app. Workers call services/ directly, not through the API layer
# (architecture doc Section 5).
