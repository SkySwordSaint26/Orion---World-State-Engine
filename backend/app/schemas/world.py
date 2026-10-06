from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

class WorldBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("World name cannot be empty or whitespace only.")
        return stripped

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> str:
        return (v or "").strip()

class WorldCreate(WorldBase):
    pass

class WorldUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_update_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("World name cannot be empty or whitespace only.")
            return stripped
        return v

class WorldStats(BaseModel):
    manuscripts_count: int = 0
    entities_count: int = 0
    characters_count: int = 0
    locations_count: int = 0
    objects_count: int = 0
    relationships_count: int = 0
    events_count: int = 0
    contradictions_count: int = 0

class WorldResponse(WorldBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    stats: Optional[WorldStats] = None

class WorldDetailResponse(WorldResponse):
    pass
