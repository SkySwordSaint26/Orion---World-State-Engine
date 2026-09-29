"""World-State side of entity resolution (Phase 5): builds the index of existing entities and runs the resolver."""
from typing import Any, List

from sqlalchemy.orm import Session

from app.contracts import ExtractionResult
from app.repositories.entity_repo import EntityRepository
from app.resolution import KnownEntity, ResolvedExtraction, resolve_entities


class EntityResolutionService:
    def __init__(self, db: Session):
        self.entity_repo = EntityRepository(db)

    def known_entities(self, world_id: str) -> List[KnownEntity]:
        return [
            KnownEntity(id=e.id, canonical_name=e.canonical_name, entity_type=e.entity_type or "unknown",
                        aliases=tuple(a.alias for a in e.aliases))
            for e in self.entity_repo.list_with_aliases(world_id)
        ]

    def resolve(self, world_id: str, observations: ExtractionResult, document: Any = None) -> ResolvedExtraction:
        return resolve_entities(observations, self.known_entities(world_id), document)
