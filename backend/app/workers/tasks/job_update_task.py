from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.processing_job import ProcessingJob
from app.models.extraction_run import ExtractionRun
from app.core.constants import JobStatus, ExtractionRunStatus
from app.workers.celery_app import celery_app
from app.config.logging import get_logger

logger = get_logger(__name__)


def update_job_stage_progress(
    job_id: str,
    chapter_number: int,
    stage: str,
    completed_stages: int,
    total_stages: int,
) -> None:
    """Persist best-effort progress from inside one chapter's extractor subprocess."""
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if not job or job.status == JobStatus.CANCELLED.value or not job.chapters_total:
            return
        completed_chapters = db.query(ExtractionRun).filter(
            ExtractionRun.processing_job_id == job_id,
            ExtractionRun.status == ExtractionRunStatus.DONE.value,
        ).count()
        fraction = completed_chapters + min(completed_stages, total_stages) / max(total_stages, 1)
        job.progress_percent = min(99, max(job.progress_percent, int(100 * fraction / job.chapters_total)))
        job.current_chapter = chapter_number
        job.current_stage = stage
        db.commit()
    except Exception as error:
        db.rollback()
        logger.warning("Could not persist extraction stage progress for job %s: %s", job_id, error)
    finally:
        db.close()

def update_job_progress(job_id: str, db: Optional[Session] = None):
    """
    Rolls up status from all extraction runs attached to a job.
    As per ER diagram notes:
    rolls status to DONE only when every spawned extraction_run is DONE (any FAILED fails the job).

    The rollup is a recount of the run rows, never an increment, so it is idempotent and safe when
    several runs finish close together. Pass `db` to run inside an existing session (the caller's
    session is committed); otherwise a private session is used.
    """
    owns_session = db is None
    session = db if db is not None else SessionLocal()
    try:
        job = session.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            return
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.CANCELLED.value:
            return

        runs = session.query(ExtractionRun).filter(ExtractionRun.processing_job_id == job_id).all()
        if not runs:
            return

        completed_count = sum(1 for r in runs if r.status == ExtractionRunStatus.DONE.value)
        failed_count = sum(1 for r in runs if r.status == ExtractionRunStatus.FAILED.value)

        job.chapters_completed = completed_count
        chapter_percent = min(99, int(100 * completed_count / max(job.chapters_total, 1)))
        if failed_count:
            job.progress_percent = max(job.progress_percent, chapter_percent)
        elif completed_count >= len(runs) and len(runs) > 0:
            job.progress_percent = 100
        else:
            job.progress_percent = max(job.progress_percent, chapter_percent)

        if failed_count > 0:
            job.status = JobStatus.FAILED.value
            job.completed_at = datetime.utcnow()
            first_fail = next(r for r in runs if r.status == ExtractionRunStatus.FAILED.value)
            job.error_message = first_fail.error_message
        elif completed_count >= len(runs) and len(runs) > 0:
            job.current_stage = "Complete"
            job.current_chapter = None
            job.status = JobStatus.DONE.value
            job.completed_at = datetime.utcnow()
        elif completed_count:
            job.current_stage = "Chapter complete"

        session.commit()
    finally:
        if owns_session:
            session.close()


@celery_app.task(name="tasks.update_job_status")
def update_job_status_task(job_id: str):
    update_job_progress(job_id)
