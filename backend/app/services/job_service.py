from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.processing_job import ProcessingJob
from app.models.extraction_run import ExtractionRun
from app.models.world import World
from app.core.constants import JobStatus, ExtractionRunStatus
from app.repositories.job_repo import JobRepository

class JobService:
    def __init__(self, db: Session):
        self.db = db
        self.job_repo = JobRepository(db)

    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        return self.job_repo.get(job_id)

    def get_job_status(self, job_id: str) -> Optional[dict]:
        job = self.job_repo.get(job_id)
        if not job:
            return None
        return {
            "id": job.id,
            "status": job.status,
            "progress_current": job.chapters_completed,
            "progress_total": job.chapters_total,
            "progress_percent": job.progress_percent,
            "current_stage": job.current_stage,
            "current_chapter": job.current_chapter,
            "error_message": job.error_message
        }

    def list_jobs(self, world_id: str) -> List[ProcessingJob]:
        return self.job_repo.get_by_world(world_id)

    def cancel_job(self, job_id: str) -> ProcessingJob:
        job = self.job_repo.get(job_id)
        # Use the integration lock so cancellation cannot split a chapter's commit.
        self.db.query(World).filter(World.id == job.world_id).with_for_update().first()
        self.db.refresh(job, with_for_update=True)
        if job.status in (JobStatus.QUEUED.value, JobStatus.PROCESSING.value):
            now = datetime.now(timezone.utc)
            job.chapters_completed = self.db.query(ExtractionRun).filter(
                ExtractionRun.processing_job_id == job.id,
                ExtractionRun.status == ExtractionRunStatus.DONE.value,
            ).count()
            job.status = JobStatus.CANCELLED.value
            job.completed_at = now
            job.error_message = "Cancelled by the author. Completed chapters have been kept."
            runs = self.db.query(ExtractionRun).filter(
                ExtractionRun.processing_job_id == job.id,
                ExtractionRun.status.in_([ExtractionRunStatus.PENDING.value, ExtractionRunStatus.PROCESSING.value]),
            ).all()
            for run in runs:
                run.status = ExtractionRunStatus.CANCELLED.value
                run.completed_at = now
                run.error_message = job.error_message
            self.db.commit()
        return job
