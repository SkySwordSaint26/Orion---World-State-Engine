from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from app.models.chapter import Chapter
from app.models.relationship import Relationship, RelationshipVersion
from app.core.constants import RelationshipStatus
from app.repositories.base import BaseRepository

class RelationshipRepository(BaseRepository[Relationship]):
    def __init__(self, db: Session):
        super().__init__(Relationship, db)

    def get_or_create_relationship(
        self,
        world_id: str,
        source_entity_id: str,
        target_entity_id: str,
        source_extraction_id: Optional[str] = None,
        commit: bool = True
    ) -> Relationship:
        rel = self.db.query(Relationship).filter(
            Relationship.world_id == world_id,
            Relationship.source_entity_id == source_entity_id,
            Relationship.target_entity_id == target_entity_id
        ).first()
        if not rel:
            rel = Relationship(
                world_id=world_id,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                source_extraction_id=source_extraction_id
            )
            self._persist(rel, commit)
        return rel

    def get_active_version(self, relationship_id: str) -> Optional[RelationshipVersion]:
        return self.db.query(RelationshipVersion).filter(
            RelationshipVersion.relationship_id == relationship_id,
            RelationshipVersion.status == RelationshipStatus.ACTIVE.value
        ).order_by(RelationshipVersion.created_at.desc()).first()

    def add_version(
        self,
        relationship_id: str,
        relationship_type: str,
        chapter_id: Optional[str] = None,
        chapter_version_id: Optional[str] = None,
        extraction_run_id: Optional[str] = None,
        status: str = RelationshipStatus.ACTIVE.value,
        confidence: float = 1.0,
        commit: bool = True
    ) -> RelationshipVersion:
        version = RelationshipVersion(
            relationship_id=relationship_id,
            relationship_type=relationship_type,
            chapter_id=chapter_id,
            chapter_version_id=chapter_version_id,
            extraction_run_id=extraction_run_id,
            status=status,
            confidence=confidence
        )
        return self._persist(version, commit)

    def list_versions_with_chapter(
        self,
        relationship_id: str,
        exclude_version_id: Optional[str] = None
    ) -> List[Tuple[RelationshipVersion, Optional[int]]]:
        """All versions of one relationship, oldest first, each with its chapter number."""
        query = self.db.query(RelationshipVersion, Chapter.chapter_number).outerjoin(
            Chapter, RelationshipVersion.chapter_id == Chapter.id
        ).filter(RelationshipVersion.relationship_id == relationship_id)
        if exclude_version_id:
            query = query.filter(RelationshipVersion.id != exclude_version_id)
        return [(v, n) for v, n in query.order_by(RelationshipVersion.created_at.asc(), RelationshipVersion.id.asc()).all()]

    def list_incoming_versions(
        self,
        world_id: str,
        target_entity_id: str,
        exclude_relationship_id: str
    ) -> List[Tuple[RelationshipVersion, Relationship, Optional[int]]]:
        """Versions of every OTHER relationship pointing at target_entity_id, oldest first."""
        rows = self.db.query(RelationshipVersion, Relationship, Chapter.chapter_number).join(
            Relationship, RelationshipVersion.relationship_id == Relationship.id
        ).outerjoin(
            Chapter, RelationshipVersion.chapter_id == Chapter.id
        ).filter(
            Relationship.world_id == world_id,
            Relationship.target_entity_id == target_entity_id,
            Relationship.id != exclude_relationship_id
        ).order_by(RelationshipVersion.created_at.asc(), RelationshipVersion.id.asc()).all()
        return [(v, r, n) for v, r, n in rows]

    def list_by_world(self, world_id: str) -> List[Relationship]:
        return self.db.query(Relationship).options(
            joinedload(Relationship.versions),
            joinedload(Relationship.source_entity),
            joinedload(Relationship.target_entity)
        ).filter(Relationship.world_id == world_id).all()

    def list_by_entity(self, entity_id: str) -> List[Relationship]:
        return self.db.query(Relationship).options(
            joinedload(Relationship.versions),
            joinedload(Relationship.source_entity),
            joinedload(Relationship.target_entity)
        ).filter(
            (Relationship.source_entity_id == entity_id) |
            (Relationship.target_entity_id == entity_id)
        ).all()
