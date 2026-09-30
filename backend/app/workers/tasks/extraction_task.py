from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.extraction_run import ExtractionRun
from app.models.processing_job import ProcessingJob
from app.models.world import World
from app.core.constants import JobStatus, ExtractionRunStatus
from app.pipeline import extractor
from app.services.world_state_service import WorldStateService
from app.utils.file_handler import read_file_text
from app.workers.celery_app import celery_app
from app.workers.tasks.job_update_task import update_job_progress
from app.config.logging import get_logger

logger = get_logger(__name__)


class ChapterOrderError(RuntimeError):
    """Raised when an earlier chapter of the same manuscript has not been successfully integrated."""


def _now() -> datetime:
    return datetime.utcnow()


def _lock_world(db: Session, world_id: str) -> None:
    """
    Serializes integrations within ONE world by locking that world's row until the transaction ends.
    Effective on PostgreSQL (SELECT ... FOR UPDATE); SQLite ignores it (single writer anyway).
    Other worlds are unaffected.
    """
    db.query(World).filter(World.id == world_id).with_for_update().first()


def find_blocking_predecessors(db: Session, chapter_id: str) -> List[str]:
    """
    Returns a description of every LOWER-numbered chapter in the same manuscript whose current
    version was submitted for extraction but whose latest run is not DONE (pending, processing or
    failed). Chapters that were never submitted for extraction do not block.
    """
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        return []

    blockers: List[str] = []
    predecessors = db.query(Chapter).filter(
        Chapter.manuscript_id == chapter.manuscript_id,
        Chapter.chapter_number < chapter.chapter_number
    ).order_by(Chapter.chapter_number.asc()).all()

    for pred in predecessors:
        current = db.query(ChapterVersion).filter(
            ChapterVersion.chapter_id == pred.id,
            ChapterVersion.is_current == True  # noqa: E712
        ).first()
        if current is None:
            continue
        latest = db.query(ExtractionRun).filter(
            ExtractionRun.chapter_version_id == current.id
        ).order_by(ExtractionRun.created_at.desc(), ExtractionRun.id.desc()).first()
        if latest is None:
            continue
        if latest.status != ExtractionRunStatus.DONE.value:
            blockers.append(f"chapter {pred.chapter_number} (latest run is '{latest.status}')")
    return blockers


def _record_failure(db: Session, extraction_run_id: str, job_id: str, message: str) -> None:
    """
    Puts the run into FAILED and rolls the job up, in a fresh transaction. Rolls back whatever the
    failed attempt left pending first. Never overwrites a run that already committed as DONE.
    """
    db.rollback()
    run = db.get(ExtractionRun, extraction_run_id) if extraction_run_id else None
    if run is not None and run.status != ExtractionRunStatus.DONE.value:
        run.status = ExtractionRunStatus.FAILED.value
        run.error_message = message
        run.completed_at = _now()
    db.commit()

    job = db.get(ProcessingJob, job_id) if job_id else None
    if job is None:
        return
    update_job_progress(job_id, db)
    # No run row to roll up (failure before/without an ExtractionRun): fail the job directly.
    db.refresh(job)
    if run is None and job.status != JobStatus.FAILED.value:
        job.status = JobStatus.FAILED.value
        job.error_message = message
        job.completed_at = _now()
        db.commit()


def _execute(
    db: Session,
    world_id: str,
    job_id: str,
    extraction_run_id: str,
    chapter_id: str,
    chapter_version_id: str,
    chapter_text: Optional[str],
    chapter_number: Optional[int],
) -> Dict[str, Any]:
    run = db.get(ExtractionRun, extraction_run_id)
    if run is None:
        raise LookupError(f"ExtractionRun {extraction_run_id} not found")

    # Claim PENDING -> PROCESSING atomically so the same run can never be integrated twice.
    claimed = db.query(ExtractionRun).filter(
        ExtractionRun.id == extraction_run_id,
        ExtractionRun.status == ExtractionRunStatus.PENDING.value
    ).update({"status": ExtractionRunStatus.PROCESSING.value, "started_at": _now()}, synchronize_session=False)
    db.commit()
    if not claimed:
        db.expire_all()
        current_status = db.get(ExtractionRun, extraction_run_id).status
        logger.warning(
            f"Skipping run {extraction_run_id}: status is '{current_status}', not 'pending' "
            f"(world={world_id} job={job_id})"
        )
        return {"status": "skipped", "reason": f"run status is '{current_status}'"}

    db.query(ProcessingJob).filter(
        ProcessingJob.id == job_id,
        ProcessingJob.status == JobStatus.QUEUED.value
    ).update({"status": JobStatus.PROCESSING.value, "started_at": _now()}, synchronize_session=False)
    db.commit()

    if chapter_number is None:
        chapter = db.get(Chapter, chapter_id)
        chapter_number = chapter.chapter_number if chapter else 1
    if chapter_text is None:
        version = db.get(ChapterVersion, chapter_version_id)
        if version is None or not version.content_path:
            raise LookupError(f"ChapterVersion {chapter_version_id} has no stored content")
        chapter_text = read_file_text(version.content_path)
    db.commit()  # end the read transaction; nothing is held open while extraction runs

    logger.info(
        f"Starting extraction: world={world_id} job={job_id} run={extraction_run_id} "
        f"chapter_id={chapter_id} chapter={chapter_number}"
    )
    extracted_data = extractor.extract_chapter(chapter_text, chapter_number)

    # ---- single integration transaction: lock -> ordering gate -> integrate -> DONE -> commit ----
    _lock_world(db, world_id)
    blockers = find_blocking_predecessors(db, chapter_id)
    if blockers:
        raise ChapterOrderError(
            f"Chapter {chapter_number} cannot be integrated before earlier chapters succeed; "
            f"blocked by: {', '.join(blockers)}"
        )

    counts = WorldStateService(db).integrate_extraction_result(
        world_id=world_id,
        extraction_data=extracted_data,
        chapter_id=chapter_id,
        chapter_version_id=chapter_version_id,
        extraction_run_id=extraction_run_id
    )

    run = db.get(ExtractionRun, extraction_run_id)
    run.status = ExtractionRunStatus.DONE.value
    run.completed_at = _now()
    run.error_message = None
    db.commit()  # the ONLY commit of the chapter's world-state changes
    return {"status": "success", "counts": counts}


def execute_chapter_extraction(
    world_id: str,
    job_id: str,
    extraction_run_id: str,
    chapter_id: str,
    chapter_version_id: str,
    chapter_text: Optional[str] = None,
    chapter_number: Optional[int] = None
) -> Dict[str, Any]:
    """
    Executes extraction and integration for ONE chapter run.

    - The run ends in DONE or FAILED (or is skipped untouched if it is not PENDING).
    - All world-state writes for the chapter commit together with the DONE status, or not at all.
    - Never raises; failures are returned as {"status": "failed", "error": ...}.
    - chapter_text is read from the stored ChapterVersion when not supplied.
    - Job progress is a recount of run statuses (update_job_progress), not an increment.

    Chapter ordering across a whole job is enforced by run_extraction_job; the predecessor gate above
    additionally protects direct/legacy callers.
    """
    ids = f"world={world_id} job={job_id} run={extraction_run_id} chapter_id={chapter_id}"
    try:
        db = SessionLocal()
    except Exception as e:
        logger.error(f"Could not open database session for extraction ({ids}): {e}", exc_info=True)
        return {"status": "failed", "error": f"database unavailable: {e}"}

    try:
        try:
            outcome = _execute(
                db, world_id, job_id, extraction_run_id, chapter_id, chapter_version_id,
                chapter_text, chapter_number
            )
        except Exception as e:
            logger.error(f"Extraction failed ({ids}): {e}", exc_info=True)
            try:
                _record_failure(db, extraction_run_id, job_id, str(e))
            except Exception as inner:
                logger.error(f"Could not record failure state ({ids}): {inner}", exc_info=True)
            return {"status": "failed", "error": str(e)}

        if outcome["status"] == "success":
            try:
                update_job_progress(job_id, db)
            except Exception as e:
                # The chapter is already durably DONE; a rollup hiccup must not turn it into a failure.
                logger.error(f"Job progress rollup failed after success ({ids}): {e}", exc_info=True)
            logger.info(f"Extraction completed ({ids}) counts={outcome['counts']}")
        return outcome
    finally:
        db.close()


def abort_pending_runs(job_id: str, message: str) -> int:
    """Marks every still-PENDING run of a job FAILED (valid terminal state) and rolls the job up."""
    db = SessionLocal()
    try:
        runs = db.query(ExtractionRun).filter(
            ExtractionRun.processing_job_id == job_id,
            ExtractionRun.status == ExtractionRunStatus.PENDING.value
        ).all()
        for run in runs:
            run.status = ExtractionRunStatus.FAILED.value
            run.error_message = message
            run.completed_at = _now()
        db.commit()
        update_job_progress(job_id, db)
        return len(runs)
    finally:
        db.close()


def run_extraction_job(job_id: str) -> Dict[str, Any]:
    """
    Runs every extraction run of a job strictly in ascending chapter order, stopping at the first
    failure. Chapter N is never integrated before chapter N-1 of the same job; if a chapter fails,
    all later chapters are marked FAILED (skipped) instead of being integrated on top of a gap.

    One job is the unit of dispatch, so different worlds/jobs run independently of each other.
    """
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            logger.error(f"run_extraction_job: job {job_id} not found")
            return {"status": "failed", "error": f"job {job_id} not found"}
        world_id = job.world_id
        rows = db.query(ExtractionRun, Chapter).join(
            ChapterVersion, ExtractionRun.chapter_version_id == ChapterVersion.id
        ).join(
            Chapter, ChapterVersion.chapter_id == Chapter.id
        ).filter(
            ExtractionRun.processing_job_id == job_id
        ).order_by(Chapter.chapter_number.asc(), ExtractionRun.created_at.asc()).all()
        plan = [
            {
                "run_id": run.id,
                "status": run.status,
                "chapter_id": chapter.id,
                "chapter_number": chapter.chapter_number,
                "chapter_version_id": run.chapter_version_id,
            }
            for run, chapter in rows
        ]
    finally:
        db.close()

    if any(item["status"] == ExtractionRunStatus.PROCESSING.value for item in plan):
        logger.warning(f"run_extraction_job: job {job_id} already has a run in progress; not starting a second runner")
        return {"status": "skipped", "reason": "job already in progress"}

    failed_chapter: Optional[int] = None
    for item in plan:
        if item["status"] == ExtractionRunStatus.DONE.value:
            continue
        if item["status"] == ExtractionRunStatus.FAILED.value:
            failed_chapter = item["chapter_number"]
            break
        result = execute_chapter_extraction(
            world_id=world_id,
            job_id=job_id,
            extraction_run_id=item["run_id"],
            chapter_id=item["chapter_id"],
            chapter_version_id=item["chapter_version_id"],
            chapter_number=item["chapter_number"],
        )
        if result["status"] != "success":
            failed_chapter = item["chapter_number"]
            break

    if failed_chapter is not None:
        skipped = abort_pending_runs(
            job_id,
            f"Skipped: chapter {failed_chapter} did not complete, so later chapters were not integrated."
        )
        logger.error(f"Job {job_id} (world={world_id}) stopped at chapter {failed_chapter}; {skipped} later run(s) skipped")
        return {"status": "failed", "failed_chapter": failed_chapter, "skipped_runs": skipped}

    return {"status": "success", "chapters": len(plan)}


@celery_app.task(bind=True, name="tasks.run_extraction_job")
def run_extraction_job_task(self, job_id: str):
    """Celery entry point: one ordered task per job."""
    return run_extraction_job(job_id)


@celery_app.task(bind=True, name="tasks.extract_chapter", max_retries=2)
def extract_chapter_task(
    self,
    world_id: str,
    job_id: str,
    extraction_run_id: str,
    chapter_id: str,
    chapter_version_id: str,
    chapter_text: Optional[str] = None,
    chapter_number: Optional[int] = None
):
    """Celery wrapper for a single chapter run (protected by the predecessor gate; prefer run_extraction_job_task)."""
    return execute_chapter_extraction(
        world_id=world_id,
        job_id=job_id,
        extraction_run_id=extraction_run_id,
        chapter_id=chapter_id,
        chapter_version_id=chapter_version_id,
        chapter_text=chapter_text,
        chapter_number=chapter_number
    )
