from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class JobCreate(BaseModel):
    world_id: str
    manuscript_id: Optional[str] = None
    job_type: str = "INITIAL_EXTRACTION"

class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    world_id: str
    manuscript_id: Optional[str] = None
    job_type: str
    status: str
    chapters_total: int
    chapters_completed: int
    progress_percent: int = 0
    current_stage: Optional[str] = None
    current_chapter: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class JobStatusResponse(BaseModel):
    id: str
    status: str
    progress_current: int
    progress_total: int
    progress_percent: int = 0
    current_stage: Optional[str] = None
    current_chapter: Optional[int] = None
    error_message: Optional[str] = None
