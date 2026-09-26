from typing import Optional

from fastapi import BackgroundTasks

from app.config.settings import settings
from app.workers.tasks.extraction_task import (
    abort_pending_runs,
    run_extraction_job,
    run_extraction_job_task,
)
from app.config.logging import get_logger

logger = get_logger(__name__)


class ExtractionDispatchError(RuntimeError):
    """The extraction job could not be handed to its executor."""


def dispatch_extraction_job(job_id: str, background_tasks: Optional[BackgroundTasks] = None) -> str:
    """
    Hands ONE ordered job to the configured executor (settings.EXTRACTION_EXECUTOR).

    Chapters are never dispatched individually: the job runner processes them in chapter order, so
    ordering does not depend on which executor is used. If the executor is unreachable the job is
    marked FAILED and an error is raised; there is no silent switch to another executor.
    """
    executor = settings.EXTRACTION_EXECUTOR.lower()

    if executor == "celery":
        try:
            run_extraction_job_task.apply_async(args=[job_id])
        except Exception as e:
            logger.error(f"Could not enqueue extraction job {job_id} on Celery: {e}", exc_info=True)
            abort_pending_runs(job_id, f"Extraction could not be queued: {e}")
            raise ExtractionDispatchError(f"Could not queue extraction job: {e}") from e
        return "celery"

    if executor == "background":
        if background_tasks is None:
            raise ExtractionDispatchError("EXTRACTION_EXECUTOR=background requires a BackgroundTasks instance")
        background_tasks.add_task(run_extraction_job, job_id)
        return "background"

    raise ExtractionDispatchError(f"Unknown EXTRACTION_EXECUTOR '{settings.EXTRACTION_EXECUTOR}'")
