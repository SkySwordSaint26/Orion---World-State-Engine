from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.models.event import Event, EventParticipant
from app.repositories.base import BaseRepository

class EventRepository(BaseRepository[Event]):
    def __init__(self, db: Session):
        super().__init__(Event, db)

    def create_event(
        self,
        world_id: str,
        description: str,
        event_type: str = "EVENT",
        chapter_id: Optional[str] = None,
        chapter_version_id: Optional[str] = None,
        extraction_run_id: Optional[str] = None,
        start_position: Optional[int] = None,
        end_position: Optional[int] = None,
        confidence: float = 1.0,
        commit: bool = True
    ) -> Event:
        event = Event(
            world_id=world_id,
            description=description,
            event_type=event_type,
            chapter_id=chapter_id,
            chapter_version_id=chapter_version_id,
            extraction_run_id=extraction_run_id,
            start_position=start_position,
            end_position=end_position,
            confidence=confidence
        )
        return self._persist(event, commit)

    def add_participant(self, event_id: str, entity_id: str, role: str = "PARTICIPANT", commit: bool = True) -> EventParticipant:
        participant = EventParticipant(
            event_id=event_id,
            entity_id=entity_id,
            role=role
        )
        return self._persist(participant, commit)

    def list_by_world(self, world_id: str) -> List[Event]:
        return self.db.query(Event).options(
            joinedload(Event.participants).joinedload(EventParticipant.entity)
        ).filter(Event.world_id == world_id).order_by(Event.created_at.asc()).all()

    def list_by_chapter(self, chapter_id: str) -> List[Event]:
        return self.db.query(Event).options(
            joinedload(Event.participants).joinedload(EventParticipant.entity)
        ).filter(Event.chapter_id == chapter_id).order_by(Event.created_at.asc()).all()

    def list_by_entity(self, entity_id: str) -> List[Event]:
        return self.db.query(Event).join(
            EventParticipant, Event.id == EventParticipant.event_id
        ).filter(
            EventParticipant.entity_id == entity_id
        ).all()
