from typing import List, Optional
from sqlalchemy.orm import Session, joinedload, selectinload
from app.models.entity import Entity, EntityAlias, EntityMention
from app.models.fact import Fact, FactVersion
from app.repositories.base import BaseRepository

class EntityRepository(BaseRepository[Entity]):
    def __init__(self, db: Session):
        super().__init__(Entity, db)

    def get_by_canonical(self, world_id: str, canonical_name: str) -> Optional[Entity]:
        return self.db.query(Entity).filter(
            Entity.world_id == world_id,
            Entity.canonical_name.ilike(canonical_name.strip())
        ).first()

    def get_by_alias(self, world_id: str, alias: str) -> Optional[Entity]:
        alias_record = self.db.query(EntityAlias).join(
            Entity, EntityAlias.entity_id == Entity.id
        ).filter(
            Entity.world_id == world_id,
            EntityAlias.alias.ilike(alias.strip())
        ).first()
        if alias_record:
            return alias_record.entity
        return None

    def list_by_world(self, world_id: str, entity_type: Optional[str] = None) -> List[Entity]:
        query = self.db.query(Entity).filter(Entity.world_id == world_id)
        if entity_type:
            query = query.filter(Entity.entity_type == entity_type)
        return query.order_by(Entity.canonical_name.asc()).all()

    def list_with_aliases(self, world_id: str) -> List[Entity]:
        return self.db.query(Entity).options(selectinload(Entity.aliases)).filter(
            Entity.world_id == world_id).order_by(Entity.created_at.asc(), Entity.id.asc()).all()

    def add_alias(self, entity_id: str, alias: str, confidence: float = 1.0, commit: bool = True) -> EntityAlias:
        existing = self.db.query(EntityAlias).filter(
            EntityAlias.entity_id == entity_id,
            EntityAlias.alias.ilike(alias.strip())
        ).first()
        if existing:
            return existing

        alias_obj = EntityAlias(
            entity_id=entity_id,
            alias=alias.strip(),
            confidence=confidence
        )
        return self._persist(alias_obj, commit)

    def add_mention(
        self,
        entity_id: str,
        surface_text: str,
        extraction_run_id: Optional[str] = None,
        start_position: Optional[int] = None,
        end_position: Optional[int] = None,
        confidence: float = 1.0,
        commit: bool = True
    ) -> EntityMention:
        mention = EntityMention(
            entity_id=entity_id,
            extraction_run_id=extraction_run_id,
            surface_text=surface_text,
            start_position=start_position,
            end_position=end_position,
            confidence=confidence
        )
        return self._persist(mention, commit)

    def get_entity_with_facts(self, entity_id: str) -> Optional[Entity]:
        return self.db.query(Entity).options(
            joinedload(Entity.facts).joinedload(Fact.versions),
            joinedload(Entity.aliases)
        ).filter(Entity.id == entity_id).first()
