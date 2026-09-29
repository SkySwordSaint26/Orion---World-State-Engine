from celery import Celery
from app.config.settings import settings

celery_app = Celery(
    "orion_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks.extraction_task", "app.workers.tasks.job_update_task"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
)

# Auto-discover tasks in app.workers.tasks
celery_app.autodiscover_tasks(["app.workers.tasks"])
