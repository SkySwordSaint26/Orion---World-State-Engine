from typing import List, Dict, Any, NamedTuple, Optional
from sqlalchemy.orm import Session

from app.contracts.normalization import normalize_predicate, normalize_property
from app.consistency import ConsistencyEngine, ContradictionRecorder, Finding
from app.consistency import vocabulary as vocab
from app.consistency.types import (
    FactCheck, FactVersionView, RelationshipCheck, RelationshipVersionView, TemporalCheck
)
from app.models.chapter import Chapter
from app.models.contradiction import Contradiction
from app.models.entity import Entity
from app.models.fact import Fact, FactVersion
from app.models.relationship import Relationship, RelationshipVersion
from app.repositories.contradiction_repo import ContradictionRepository
from app.repositories.fact_repo import FactRepository
from app.repositories.relationship_repo import RelationshipRepository
from app.config.logging import get_logger

logger = get_logger(__name__)


class CheckResult(NamedTuple):
    findings: List[Finding]            # every rule violation found (whether or not it was already recorded)
    created: List[Contradiction]       # only the contradiction rows newly written by this check


class ConsistencyService:
    """
    Consistency-check orchestration (database side): loads the affected rows into plain views, asks the
    deterministic ConsistencyEngine for findings, and records them. It never commits; new rows are
    flushed into the caller's transaction (see WorldStateService.integrate_extraction_result), and no
    LLM is involved anywhere.

    Checks are incremental: a fact check reads one entity+property, a relationship check reads one
    entity pair (plus the target's incoming relationships for single-source predicates), and the
    temporal check reads only the current chapter's relations.
    """

    def __init__(self, db: Session, engine: Optional[ConsistencyEngine] = None):
        self.db = db
        self.engine = engine or ConsistencyEngine()
        self.contradiction_repo = ContradictionRepository(db)
        self.fact_repo = FactRepository(db)
        self.relationship_repo = RelationshipRepository(db)
        self.recorder = ContradictionRecorder(db)

    def _chapter_number(self, chapter_id: Optional[str]) -> Optional[int]:
        if not chapter_id:
            return None
        chapter = self.db.get(Chapter, chapter_id)
        return chapter.chapter_number if chapter else None

    # ---------------------------------------------------------------- facts
    def evaluate_fact_version(self, entity: Entity, fact: Fact, new_version: FactVersion) -> CheckResult:
        """Checks one freshly flushed fact version against the other versions of the same fact."""
        history = tuple(
            FactVersionView(v.id, v.value, v.status, number)
            for v, number in self.fact_repo.list_versions_with_chapter(fact.id, exclude_version_id=new_version.id)
        )
        check = FactCheck(
            entity_name=entity.canonical_name,
            # TODO(property-normalization): this only normalizes case/separators of the STORED name. Fact rows
            # are still keyed by the raw name (see WorldStateService), so history here never spans spellings.
            property_name=vocab.normalize_property(normalize_property(fact.property_name)),  # hook: pass-through
            new=FactVersionView(new_version.id, new_version.value, new_version.status,
                                self._chapter_number(new_version.chapter_id)),
            history=history,
        )
        findings = self.engine.check_fact(check)
        return CheckResult(findings, self.recorder.record_all(entity.world_id, findings))

    # -------------------------------------------------------- relationships
    def evaluate_relationship_version(
        self,
        world_id: str,
        relationship: Relationship,
        new_version: RelationshipVersion,
        subject: Entity,
        obj: Entity
    ) -> CheckResult:
        """Checks one freshly flushed relationship version against its own pair history and, for single-source predicates, the target's other incoming relationships."""
        # TODO(relationship-normalization): only case/separators are normalized here; synonyms and inverse
        # predicates are not mapped, and pair_history below covers ONLY this (source, target) direction.
        predicate = vocab.normalize_predicate(normalize_predicate(new_version.relationship_type))  # hook: pass-through
        pair_history = tuple(
            RelationshipVersionView(v.id, vocab.normalize_predicate(normalize_predicate(v.relationship_type)), v.status, number,
                                    relationship.source_entity_id, subject.canonical_name)
            for v, number in self.relationship_repo.list_versions_with_chapter(
                relationship.id, exclude_version_id=new_version.id)
        )
        incoming: tuple = ()
        if predicate in vocab.SINGLE_VALUED_INCOMING_PREDICATES:
            incoming = tuple(
                RelationshipVersionView(v.id, vocab.normalize_predicate(v.relationship_type), v.status, number,
                                        rel.source_entity_id,
                                        rel.source_entity.canonical_name if rel.source_entity else "")
                for v, rel, number in self.relationship_repo.list_incoming_versions(
                    world_id, obj.id, exclude_relationship_id=relationship.id)
            )
        check = RelationshipCheck(
            subject_name=subject.canonical_name,
            object_name=obj.canonical_name,
            new=RelationshipVersionView(new_version.id, predicate, new_version.status,
                                        self._chapter_number(new_version.chapter_id),
                                        relationship.source_entity_id, subject.canonical_name),
            pair_history=pair_history,
            incoming=incoming,
        )
        findings = self.engine.check_relationship(check)
        return CheckResult(findings, self.recorder.record_all(world_id, findings))

    # ------------------------------------------------------------- temporal
    def run_checks(
        self,
        world_id: str,
        events: List[Dict[str, Any]] = [],
        temporal_relations: List[Dict[str, Any]] = [],
        chapter_id: Optional[str] = None,
        event_ids: Optional[Dict[str, str]] = None
    ) -> List[Contradiction]:
        """
        Chapter-level temporal check: BEFORE/AFTER relations extracted from this chapter must form a DAG.
        `event_ids` optionally maps the extractor's local event ids to the persisted Event rows so the
        contradiction can reference the two events that close the cycle. Returns only newly created
        contradiction rows; an identical, already-recorded cycle is not duplicated.
        """
        # TODO(temporal-normalization): the ids below are extractor-local (chunk-scoped, possibly colliding) and
        # only THIS chapter's relations are checked; nothing is loaded from earlier chapters because temporal
        # relations are not persisted. Normalized, globally unique event ids and stored relations will change
        # the input built here, without changing TemporalCycleRule itself.
        check = TemporalCheck(
            event_ids=tuple(e.get("id") or e.get("event_id") for e in events if (e.get("id") or e.get("event_id"))),
            relations=tuple(
                (tr.get("event_1"), str(tr.get("relation", "")).upper(), tr.get("event_2"))
                for tr in temporal_relations
            ),
            chapter_number=self._chapter_number(chapter_id),
        )
        findings = self.engine.check_temporal(check)
        return self.recorder.record_all(world_id, findings, event_ids)

    def resolve_contradiction(
        self,
        contradiction_id: str,
        status: str = "RESOLVED",
        preferred_fact_version_id: Optional[str] = None,
        preferred_relationship_version_id: Optional[str] = None
    ) -> Optional[Contradiction]:
        con = self.contradiction_repo.get(contradiction_id)
        if not con:
            return None

        # Fact contradiction resolution
        if preferred_fact_version_id and con.old_fact_version_id and con.new_fact_version_id:
            if preferred_fact_version_id not in (con.old_fact_version_id, con.new_fact_version_id):
                raise ValueError("preferred_fact_version_id must match one of the contradiction's fact versions.")
            from app.models.fact import FactVersion
            chosen = self.db.query(FactVersion).filter_by(id=preferred_fact_version_id).first()
            other_id = con.old_fact_version_id if preferred_fact_version_id == con.new_fact_version_id else con.new_fact_version_id
            other = self.db.query(FactVersion).filter_by(id=other_id).first()
            if chosen:
                chosen.status = "ACTIVE"
            if other:
                other.status = "SUPERSEDED"

        # Relationship contradiction resolution
        if preferred_relationship_version_id and con.old_relationship_version_id and con.new_relationship_version_id:
            if preferred_relationship_version_id not in (con.old_relationship_version_id, con.new_relationship_version_id):
                raise ValueError("preferred_relationship_version_id must match one of the contradiction's relationship versions.")
            from app.models.relationship import RelationshipVersion
            chosen = self.db.query(RelationshipVersion).filter_by(id=preferred_relationship_version_id).first()
            other_id = con.old_relationship_version_id if preferred_relationship_version_id == con.new_relationship_version_id else con.new_relationship_version_id
            other = self.db.query(RelationshipVersion).filter_by(id=other_id).first()
            if chosen:
                chosen.status = "ACTIVE"
            if other:
                other.status = "SUPERSEDED"

        con.status = status
        self.db.commit()
        self.db.refresh(con)
        return con

    def list_contradictions(self, world_id: str, status: Optional[str] = None) -> List[Contradiction]:
        return self.contradiction_repo.list_by_world(world_id, status=status)
