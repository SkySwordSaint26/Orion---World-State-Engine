from typing import List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from app.models.chapter import Chapter
from app.models.fact import Fact, FactVersion, FactMention
from app.core.constants import FactStatus
from app.repositories.base import BaseRepository

class FactRepository(BaseRepository[Fact]):
    def __init__(self, db: Session):
        super().__init__(Fact, db)

    def get_or_create_fact(self, entity_id: str, property_name: str, commit: bool = True) -> Fact:
        fact = self.db.query(Fact).filter(
            Fact.entity_id == entity_id,
            Fact.property_name == property_name
        ).first()
        if not fact:
            fact = Fact(entity_id=entity_id, property_name=property_name)
            self._persist(fact, commit)
        return fact

    def get_active_version(self, fact_id: str) -> Optional[FactVersion]:
        return self.db.query(FactVersion).filter(
            FactVersion.fact_id == fact_id,
            FactVersion.status == FactStatus.ACTIVE.value
        ).order_by(FactVersion.created_at.desc()).first()

    def add_version(
        self,
        fact_id: str,
        value: Any,
        chapter_id: Optional[str] = None,
        chapter_version_id: Optional[str] = None,
        extraction_run_id: Optional[str] = None,
        status: str = FactStatus.ACTIVE.value,
        confidence: float = 1.0,
        commit: bool = True
    ) -> FactVersion:
        version = FactVersion(
            fact_id=fact_id,
            chapter_id=chapter_id,
            chapter_version_id=chapter_version_id,
            extraction_run_id=extraction_run_id,
            value=value,
            status=status,
            confidence=confidence
        )
        return self._persist(version, commit)

    def list_versions_with_chapter(
        self,
        fact_id: str,
        exclude_version_id: Optional[str] = None
    ) -> List[Tuple[FactVersion, Optional[int]]]:
        """All versions of one fact, oldest first, each with its chapter number (None if no chapter)."""
        query = self.db.query(FactVersion, Chapter.chapter_number).outerjoin(
            Chapter, FactVersion.chapter_id == Chapter.id
        ).filter(FactVersion.fact_id == fact_id)
        if exclude_version_id:
            query = query.filter(FactVersion.id != exclude_version_id)
        return [(v, n) for v, n in query.order_by(FactVersion.created_at.asc(), FactVersion.id.asc()).all()]

    def add_mention(
        self,
        entity_id: str,
        property_name: str,
        value: Any,
        extraction_run_id: Optional[str] = None,
        start_position: Optional[int] = None,
        end_position: Optional[int] = None,
        confidence: float = 1.0,
        commit: bool = True
    ) -> FactMention:
        mention = FactMention(
            entity_id=entity_id,
            property_name=property_name,
            value=value,
            extraction_run_id=extraction_run_id,
            start_position=start_position,
            end_position=end_position,
            confidence=confidence
        )
        return self._persist(mention, commit)

    def list_by_entity(self, entity_id: str) -> List[Fact]:
        return self.db.query(Fact).filter(Fact.entity_id == entity_id).all()
