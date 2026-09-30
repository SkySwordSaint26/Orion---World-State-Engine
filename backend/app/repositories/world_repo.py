from typing import List, Optional, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.world import World
from app.models.entity import Entity
from app.models.relationship import Relationship
from app.models.event import Event
from app.models.contradiction import Contradiction
from app.models.manuscript import Manuscript
from app.repositories.base import BaseRepository

class WorldRepository(BaseRepository[World]):
    def __init__(self, db: Session):
        super().__init__(World, db)

    def get_by_user_and_name(self, user_id: str, name: str) -> Optional[World]:
        if not user_id or not name:
            return None
        return self.db.query(World).filter(
            World.user_id == user_id,
            func.lower(func.trim(World.name)) == func.lower(func.trim(name))
        ).first()

    def list_worlds(self, user_id: Optional[str] = None) -> List[World]:
        if not user_id:
            return []
        return self.db.query(World).filter(
            World.user_id == user_id
        ).order_by(World.created_at.desc()).all()

    def get_world_stats(self, world_id: str) -> Dict[str, int]:
        entities_count = self.db.query(Entity).filter(Entity.world_id == world_id).count()
        characters_count = self.db.query(Entity).filter(
            Entity.world_id == world_id,
            Entity.entity_type == "character"
        ).count()
        locations_count = self.db.query(Entity).filter(
            Entity.world_id == world_id,
            Entity.entity_type == "location"
        ).count()
        objects_count = self.db.query(Entity).filter(
            Entity.world_id == world_id,
            Entity.entity_type == "object"
        ).count()
        relationships_count = self.db.query(Relationship).filter(Relationship.world_id == world_id).count()
        events_count = self.db.query(Event).filter(Event.world_id == world_id).count()
        contradictions_count = self.db.query(Contradiction).filter(
            Contradiction.world_id == world_id,
            Contradiction.status == "DETECTED"
        ).count()

        manuscripts_count = self.db.query(Manuscript).filter(Manuscript.world_id == world_id).count()

        return {
            "manuscripts_count": manuscripts_count,
            "entities_count": entities_count,
            "characters_count": characters_count,
            "locations_count": locations_count,
            "objects_count": objects_count,
            "relationships_count": relationships_count,
            "events_count": events_count,
            "contradictions_count": contradictions_count
        }
