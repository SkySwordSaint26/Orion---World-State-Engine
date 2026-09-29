from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user_world
from app.models.world import World
from app.schemas.manuscript import ManuscriptResponse, ManuscriptDetailResponse
from app.schemas.chapter import ChapterResponse
from app.services.manuscript_service import ManuscriptService
from app.workers.dispatch import dispatch_extraction_job, ExtractionDispatchError

router = APIRouter()

@router.post("/{world_id}/manuscripts", status_code=status.HTTP_202_ACCEPTED)
async def upload_manuscript(
    world_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    content = await file.read()
    if not content or len(content.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file cannot be empty."
        )

    safe_filename = Path(file.filename or "manuscript.txt").name
    service = ManuscriptService(db)

    result = service.upload_manuscript(
        world_id=world.id,
        filename=safe_filename,
        file_bytes=content,
        file_type=file.content_type or "text/plain",
        user_id=world.user_id
    )

    # One ordered job per manuscript (chapters run 1..N, stopping at the first failure).
    try:
        dispatch_extraction_job(result["job_id"], background_tasks)
    except ExtractionDispatchError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    return {
        "job_id": result["job_id"],
        "manuscript_id": result["manuscript_id"],
        "chapters_total": result["chapters_count"],
        "message": "Manuscript accepted for processing"
    }

@router.get("/{world_id}/manuscripts", response_model=List[ManuscriptResponse])
def list_manuscripts(
    world_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = ManuscriptService(db)
    manuscripts = service.list_manuscripts(world.id)
    return [
        ManuscriptResponse(
            id=m.id,
            world_id=m.world_id,
            title=m.title,
            original_file_path=m.original_file_path,
            file_type=m.file_type,
            chapter_count=len(m.chapters),
            created_at=m.created_at,
            updated_at=m.updated_at
        )
        for m in manuscripts
        if len(m.chapters) > 0
    ]

@router.get("/{world_id}/manuscripts/{manuscript_id}", response_model=ManuscriptDetailResponse)
def get_manuscript(
    world_id: str,
    manuscript_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = ManuscriptService(db)
    manuscript = service.get_manuscript(manuscript_id)
    if not manuscript or manuscript.world_id != world.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found")

    chapters = [
        ChapterResponse(
            id=ch.id,
            manuscript_id=ch.manuscript_id,
            chapter_number=ch.chapter_number,
            title=ch.title,
            created_at=ch.created_at,
            updated_at=ch.updated_at
        )
        for ch in manuscript.chapters
    ]

    return ManuscriptDetailResponse(
        id=manuscript.id,
        world_id=manuscript.world_id,
        title=manuscript.title,
        original_file_path=manuscript.original_file_path,
        file_type=manuscript.file_type,
        chapter_count=len(chapters),
        created_at=manuscript.created_at,
        updated_at=manuscript.updated_at,
        chapters=chapters
    )

@router.delete("/{world_id}/manuscripts/{manuscript_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manuscript(
    world_id: str,
    manuscript_id: str,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    service = ManuscriptService(db)
    manuscript = service.get_manuscript(manuscript_id)
    if not manuscript or manuscript.world_id != world.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript not found")
    service.manuscript_repo.delete(manuscript_id)
    return None
