from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class ContradictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    world_id: str
    contradiction_type: str
    explanation: str
    confidence: float
    status: str
    old_fact_version_id: Optional[str] = None
    new_fact_version_id: Optional[str] = None
    old_relationship_version_id: Optional[str] = None
    new_relationship_version_id: Optional[str] = None
    event_id_a: Optional[str] = None
    event_id_b: Optional[str] = None
    created_at: datetime
    # No `metadata` field: on a SQLAlchemy model that name is the table registry (Base.metadata), not a column,
    # so from_attributes read MetaData() and every list with a contradiction failed validation (HTTP 500).

class ContradictionResolveRequest(BaseModel):
    status: str = "RESOLVED"
    resolution_notes: Optional[str] = None
    preferred_fact_version_id: Optional[str] = None
    preferred_relationship_version_id: Optional[str] = None
