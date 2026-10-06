import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.world import World
from app.models.entity import Entity
from app.models.fact import Fact, FactVersion
from app.models.relationship import Relationship, RelationshipVersion
from app.models.event import Event, EventParticipant
from app.repositories.world_repo import WorldRepository
from app.repositories.entity_repo import EntityRepository
from app.repositories.fact_repo import FactRepository
from app.repositories.relationship_repo import RelationshipRepository
from app.repositories.event_repo import EventRepository
from app.repositories.contradiction_repo import ContradictionRepository
from app.core.constants import FactStatus, RelationshipStatus
from app.pipeline.resolution.fact_resolution import compare_fact_values
from app.services.consistency_service import ConsistencyService
from app.contracts.normalization import (
    is_proper_name, name_words, normalize_entity_name, normalize_predicate, normalize_property)
from app.config.logging import get_logger

logger = get_logger(__name__)

class WorldStateService:
    def __init__(self, db: Session):
        self.db = db
        self.world_repo = WorldRepository(db)
        self.entity_repo = EntityRepository(db)
        self.fact_repo = FactRepository(db)
        self.relationship_repo = RelationshipRepository(db)
        self.event_repo = EventRepository(db)
        self.contradiction_repo = ContradictionRepository(db)
        self.consistency_service = ConsistencyService(db)

    def create_world(self, name: str, description: str = "", user_id: Optional[str] = None) -> World:
        return self.world_repo.create({
            "name": name,
            "description": description,
            "user_id": user_id
        })

    def get_world(self, world_id: str) -> Optional[World]:
        return self.world_repo.get(world_id)

    def list_worlds(self, user_id: Optional[str] = None) -> List[World]:
        return self.world_repo.list_worlds(user_id=user_id)

    def get_world_stats(self, world_id: str) -> Dict[str, int]:
        return self.world_repo.get_world_stats(world_id)

    def delete_world(self, world_id: str) -> Optional[World]:
        return self.world_repo.delete(world_id)

    def find_entity(self, world_id: str, names: List[str], entity_type: Optional[str] = None) -> Optional[Entity]:
        """The stored entity one of `names` refers to. An exact name or alias wins; otherwise a short or full form
        ("Mara" / "Mara Quinn") of exactly one stored entity of the same type. Role phrases ("mother") never match:
        "her mother" in two chapters is rarely the same person."""
        names = [n for n in names if is_proper_name(n)]
        lookup = lambda n: self.entity_repo.get_by_canonical(world_id, n) or self.entity_repo.get_by_alias(world_id, n)
        exact = next((e for n in names if (e := lookup(n))), None)
        if exact or not names:
            return exact
        wanted = [name_words(n) for n in names]
        # ponytail: scans every entity of the world per unmatched name; index the name words if worlds grow to thousands
        stored = lambda e: [name_words(n) for n in [e.canonical_name, *(a.alias for a in e.aliases)]
                            if is_proper_name(n)]
        candidates = [e for e in self.entity_repo.list_with_aliases(world_id)
                      if (entity_type is None or e.entity_type == entity_type)
                      and any(w <= s or s <= w for s in stored(e) for w in wanted)]
        return candidates[0] if len(candidates) == 1 else None   # "Quinn" with three Quinns stored: ambiguous, no match

    def integrate_extraction_result(
        self,
        world_id: str,
        extraction_data: Dict[str, Any],
        chapter_id: Optional[str] = None,
        chapter_version_id: Optional[str] = None,
        extraction_run_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Integrates parsed extraction data into persistent relational state:
        - Resolves or creates Entities
        - Adds Aliases and Mentions
        - Inserts Facts & FactVersions (with consistency check)
        - Inserts Relationships & RelationshipVersions
        - Inserts Events & Participants
        - Detects Contradictions

        TRANSACTION CONTRACT: this method never commits. Every write is flushed into the caller's
        open transaction, so the caller (the extraction task) owns commit/rollback and a chapter is
        integrated all-or-nothing.
        """
        counts = {
            "entities_created": 0,
            "entities_updated": 0,
            "facts_added": 0,
            "relationships_added": 0,
            "events_added": 0,
            "contradictions_found": 0
        }

        # Map canonical/mention names to DB Entity objects
        entity_cache: Dict[str, Entity] = {}

        # 1. Process Entities
        for ent_data in extraction_data.get("entities", []):
            canonical = normalize_entity_name(ent_data.get("canonical_name", "").strip())
            if not canonical:
                continue
            entity_type = ent_data.get("type", "unknown").lower()

            # Look up every name (canonical and aliases) against every stored name (canonical and aliases): a
            # chapter may call "Daniel" (alias "Dan") the entity stored as "Dan" (alias "Daniel").
            names = [canonical, *ent_data.get("aliases", [])]
            existing_ent = self.find_entity(world_id, names, entity_type)

            if existing_ent:
                entity = existing_ent
                counts["entities_updated"] += 1
                # Add any new aliases, this chapter's canonical name included
                for alias in names:
                    if alias.strip().lower() != entity.canonical_name.strip().lower():
                        self.entity_repo.add_alias(entity.id, alias, commit=False)
            else:
                entity = self.entity_repo.create({
                    "world_id": world_id,
                    "entity_type": entity_type,
                    "canonical_name": canonical,
                    "provenance": json.dumps(ent_data.get("source_chunk", ""))
                }, commit=False)
                counts["entities_created"] += 1
                for alias in ent_data.get("aliases", []):
                    self.entity_repo.add_alias(entity.id, alias, commit=False)

            entity_cache[canonical.lower()] = entity
            for alias in ent_data.get("aliases", []):
                entity_cache[normalize_entity_name(alias.strip()).lower()] = entity

            # Record mention
            mention_text = ent_data.get("mention") or canonical
            self.entity_repo.add_mention(
                entity_id=entity.id,
                surface_text=mention_text,
                extraction_run_id=extraction_run_id,
                commit=False
            )

            # Insert Facts & Version Check
            attributes = ent_data.get("attributes", {})
            if isinstance(attributes, dict):
                for prop_name, new_val in attributes.items():
                    if new_val is None or new_val == "":
                        continue

                    # TODO(property-normalization): NOT IMPLEMENTED. `prop_name` is the raw LLM string and is
                    # used as the storage key, so "Eye Color" and "eye_color" become two separate Fact rows and
                    # a change between them is never compared. Normalize/map the property to the controlled
                    # vocabulary (consistency/vocabulary.py) BEFORE this call, in the future observation-
                    # normalization stage, so all spellings land on one Fact row. Rules must not guess synonyms.
                    prop_name = prop_name
                    prop_name = normalize_property(prop_name)  # pass-through hook (Phase 4): no logic yet
                    fact = self.fact_repo.get_or_create_fact(entity.id, prop_name, commit=False)
                    active_ver = self.fact_repo.get_active_version(fact.id)

                    old_val = active_ver.value if active_ver else None

                    # Write the new version, then let the deterministic rule engine judge it.
                    new_version = self.fact_repo.add_version(
                        fact_id=fact.id,
                        value=new_val,
                        chapter_id=chapter_id,
                        chapter_version_id=chapter_version_id,
                        extraction_run_id=extraction_run_id,
                        status=FactStatus.ACTIVE.value,
                        confidence=1.0,
                        commit=False
                    )
                    counts["facts_added"] += 1

                    result = self.consistency_service.evaluate_fact_version(entity, fact, new_version)
                    if result.findings:
                        # Conflicting claim: keep it as CONTRADICTED and leave the earlier ACTIVE value in place.
                        new_version.status = FactStatus.CONTRADICTED.value
                        counts["contradictions_found"] += len(result.created)
                    elif active_ver and not compare_fact_values(old_val, new_val):
                        # Valid chronological evolution.
                        active_ver.status = FactStatus.SUPERSEDED.value
                    self.db.flush()

        # Helper for entity resolution from cache or DB
        def resolve_cached_entity(name_str: str) -> Optional[Entity]:
            name_str = normalize_entity_name(name_str.strip())
            norm = name_str.lower()
            if norm in entity_cache:   # this chapter's entities, role phrases ("mother") included
                return entity_cache[norm]
            ent = self.find_entity(world_id, [name_str])
            if ent:
                entity_cache[norm] = ent
            return ent

        # 2. Process Relationships
        for rel_data in extraction_data.get("relationships", []):
            subj_name = rel_data.get("subject", "")
            obj_name = rel_data.get("object", "")
            # TODO(relationship-normalization): NOT IMPLEMENTED. `rel_type` is the raw LLM predicate and is
            # stored as-is (only compared after case/separator normalization inside the rules). Map synonyms
            # and inverse phrasings (e.g. "SON_OF" -> inverse "FATHER_OF") to the controlled predicate
            # vocabulary here, before storage. Relationships are also keyed by DIRECTION (source, target):
            # symmetric predicates are not folded together (see TODO in consistency/rules.py).
            rel_type = normalize_predicate(rel_data.get("predicate", "RELATED_TO"))  # pass-through hook (Phase 4)

            subj_ent = resolve_cached_entity(subj_name)
            obj_ent = resolve_cached_entity(obj_name)

            if subj_ent and obj_ent and subj_ent.id != obj_ent.id:
                rel = self.relationship_repo.get_or_create_relationship(
                    world_id=world_id,
                    source_entity_id=subj_ent.id,
                    target_entity_id=obj_ent.id,
                    commit=False
                )

                active_ver = self.relationship_repo.get_active_version(rel.id)
                old_type = active_ver.relationship_type if active_ver else ""

                new_ver = self.relationship_repo.add_version(
                    relationship_id=rel.id,
                    relationship_type=rel_type,
                    chapter_id=chapter_id,
                    chapter_version_id=chapter_version_id,
                    extraction_run_id=extraction_run_id,
                    status=RelationshipStatus.ACTIVE.value,
                    confidence=1.0,
                    commit=False
                )
                counts["relationships_added"] += 1

                result = self.consistency_service.evaluate_relationship_version(
                    world_id, rel, new_ver, subj_ent, obj_ent
                )
                if result.findings:
                    new_ver.status = RelationshipStatus.CONTRADICTED.value
                    counts["contradictions_found"] += len(result.created)
                elif active_ver and old_type.strip().upper() != rel_type.strip().upper():
                    active_ver.status = RelationshipStatus.SUPERSEDED.value
                self.db.flush()

        # 3. Process Events
        # TODO(temporal-normalization): NOT IMPLEMENTED. Extractor event ids ("event_1", ...) are local to a
        # chunk and not namespaced, so two chunks can reuse an id and this map keeps only the last Event row.
        # Once ids are made globally unique per chapter (and temporal relations are persisted), the
        # temporal rule can be applied across chapters instead of one chapter's relations only.
        local_event_ids: Dict[str, str] = {}  # extractor-local event id -> persisted Event.id
        for ev_data in extraction_data.get("events", []):
            desc = ev_data.get("evidence") or ev_data.get("description") or f"Event ({ev_data.get('type')})"
            ev = self.event_repo.create_event(
                world_id=world_id,
                description=desc,
                event_type=ev_data.get("type", "EVENT"),
                chapter_id=chapter_id,
                chapter_version_id=chapter_version_id,
                extraction_run_id=extraction_run_id,
                confidence=1.0,
                commit=False
            )
            counts["events_added"] += 1
            if ev_data.get("id"):
                local_event_ids[ev_data["id"]] = ev.id

            for p_name in ev_data.get("participants", []):
                p_ent = resolve_cached_entity(p_name)
                if p_ent:
                    self.event_repo.add_participant(ev.id, p_ent.id, role="PARTICIPANT", commit=False)

        # 4. Consistency Checks (Temporal & Cycles)
        detected_cons = self.consistency_service.run_checks(
            world_id=world_id,
            events=extraction_data.get("events", []),
            temporal_relations=extraction_data.get("temporal_relations", []),
            chapter_id=chapter_id,
            event_ids=local_event_ids
        )
        counts["contradictions_found"] += len(detected_cons)

        # No commit here: see TRANSACTION CONTRACT above.
        self.db.flush()
        return counts
