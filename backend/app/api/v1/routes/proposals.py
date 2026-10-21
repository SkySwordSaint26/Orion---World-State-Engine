from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user_job
from app.core.constants import JobStatus, JobType
from app.models.processing_job import ProcessingJob
from app.services.proposal_service import load_proposals

# Owner: Extraction (feature/extraction-review). Contract: docs/api.md §17. Registered in router.py (Step 0).
router = APIRouter()


@router.get("/{job_id}/proposals")
def get_proposals(job: ProcessingJob = Depends(get_current_user_job)):
    """A RE_EXTRACTION job's proposals: 200 when done, 202 with an empty list while it runs, 404 otherwise."""
    if job.job_type != JobType.RE_EXTRACTION.value or job.status in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No proposals for this job")
    if job.status != JobStatus.DONE.value:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={
            "job_id": job.id, "world_id": job.world_id, "chapter_id": None, "chapter_number": None,
            "status": "pending", "generated_at": None, "proposals": []})
    result = load_proposals(job.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No proposals for this job")
    return result
