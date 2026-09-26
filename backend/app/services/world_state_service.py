import json
from dataclasses import replace
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
from app.contracts import ExtractionResult
from app.coreference import apply_coreference
from app.resolution import ground_mention_references, is_provisional, name_key, ResolutionType
from app.services.entity_resolution_service import EntityResolutionService
from app.contracts.normalization import normalize_entity_name, normalize_predicate, normalize_property
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
        self.last_resolution = None  # Phase 5: ResolvedExtraction of the latest integration (inspection only)
        self.last_coreference = None  # Phase 6: CoreferenceResult of the latest integration (inspection only)

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

        # Phase 5: deterministic mention -> entity resolution against the World State. Only runs when the
        # extractor supplied observations (hand-built dicts keep the legacy name-based path unchanged).
        # Anything the resolver leaves unresolved falls through to the legacy lookup below.
        observations = extraction_data.get("observations")
        resolved = (
            EntityResolutionService(self.db).resolve(world_id, observations, extraction_data.get("document"))
            if isinstance(observations, ExtractionResult) else None
        )
        self.last_resolution = None
        self.last_coreference = None

        def entity_from_resolution(*names: Optional[str]) -> Optional[Entity]:
            if resolved is None:
                return None
            for n in names:
                eid = resolved.entity_for_name(n or "")
                if eid and not is_provisional(eid):
                    ent = self.db.get(Entity, eid)
                    if ent is not None and ent.world_id == world_id:
                        return ent
            return None

        # Map canonical/mention names to DB Entity objects
        entity_cache: Dict[str, Entity] = {}

        # 1. Process Entities
        for ent_data in extraction_data.get("entities", []):
            canonical = normalize_entity_name(ent_data.get("canonical_name", "").strip())  # pass-through hook (Phase 4)
            if not canonical:
                continue

            # Look up by canonical or alias in world
            existing_ent = self.entity_repo.get_by_canonical(world_id, canonical)
            if not existing_ent:
                for alias in ent_data.get("aliases", []):
                    existing_ent = self.entity_repo.get_by_alias(world_id, alias)
                    if existing_ent:
                        break

            if not existing_ent:
                existing_ent = entity_from_resolution(canonical, ent_data.get("mention"))

            if existing_ent:
                entity = existing_ent
                counts["entities_updated"] += 1
                # Add any new aliases
                for alias in ent_data.get("aliases", []):
                    self.entity_repo.add_alias(entity.id, alias, commit=False)
            else:
                entity = self.entity_repo.create({
                    "world_id": world_id,
                    "entity_type": ent_data.get("type", "unknown").lower(),
                    "canonical_name": canonical,
                    "provenance": json.dumps(ent_data.get("source_chunk", ""))
                }, commit=False)
                counts["entities_created"] += 1
                for alias in ent_data.get("aliases", []):
                    self.entity_repo.add_alias(entity.id, alias, commit=False)

            entity_cache[canonical.lower()] = entity
            for alias in ent_data.get("aliases", []):
                entity_cache[alias.lower()] = entity

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

        if resolved is not None:
            # Bind provisional ids (entities the resolver planned to create) to the rows step 1 created, attach
            # ids to the observations, and persist resolved pronoun mentions (with exact offsets).
            binding = {}
            for planned in resolved.resolution.new_entities:
                row = entity_cache.get(planned.canonical_name.lower()) or self.entity_repo.get_by_canonical(
                    world_id, planned.canonical_name)
                if row is not None:
                    binding[planned.entity_id] = row.id
            resolved = resolved.rebind(binding)
            # Phase 7: explicit mention references (split pipeline) ground directly through the mentions' entities.
            resolved = replace(resolved, result=ground_mention_references(resolved.result))
            # Phase 6: cluster mentions of this chapter and let relationships/events/facts resolve through the
            # clusters where the name lookup could not (e.g. a raw pronoun subject).
            resolved, coref = apply_coreference(resolved, extraction_data.get("document"))
            self.last_resolution = resolved
            self.last_coreference = coref
            for pm in resolved.result.entity_mentions:
                if pm.mention_kind == "pronominal" and pm.entity_id and not is_provisional(pm.entity_id):
                    res = resolved.resolution.get(pm.id)
                    self.entity_repo.add_mention(
                        entity_id=pm.entity_id, surface_text=pm.text, extraction_run_id=extraction_run_id,
                        start_position=pm.start, end_position=pm.end,
                        confidence=res.confidence if res else 0.5, commit=False)

        def entity_by_id(entity_id: Optional[str]) -> Optional[Entity]:
            if not entity_id or is_provisional(entity_id):
                return None
            ent = self.db.get(Entity, entity_id)
            return ent if ent is not None and ent.world_id == world_id else None

        # The extractor's legacy lists are derived 1:1 from the observations; only trust the positional pairing
        # when the list still lines up (same length and same names), otherwise ignore cluster ids.
        def paired(observed, legacy_items, same):
            if resolved is None or len(observed) != len(legacy_items):
                return [None] * len(legacy_items)
            return [o if same(o, d) else None for o, d in zip(observed, legacy_items)]

        # Helper for entity resolution from cache or DB
        def resolve_cached_entity(name_str: str) -> Optional[Entity]:
            name_str = normalize_entity_name(name_str)  # pass-through hook (Phase 4)
            norm = name_str.strip().lower()
            if norm in entity_cache:
                return entity_cache[norm]
            ent = self.entity_repo.get_by_canonical(world_id, name_str)
            if not ent:
                ent = self.entity_repo.get_by_alias(world_id, name_str)
            if not ent:
                ent = entity_from_resolution(name_str)
            if ent:
                entity_cache[norm] = ent
            return ent

        # 2. Process Relationships
        rel_items = extraction_data.get("relationships", [])
        rel_obs = paired(resolved.result.relationships if resolved else (), rel_items,
                         lambda o, d: (o.subject, o.object) == (d.get("subject", ""), d.get("object", "")))
        for rel_idx, rel_data in enumerate(rel_items):
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
            if rel_obs[rel_idx] is not None:  # Phase 6: cluster-grounded ids fill what the name lookup missed
                subj_ent = subj_ent or entity_by_id(rel_obs[rel_idx].subject_entity_id)
                obj_ent = obj_ent or entity_by_id(rel_obs[rel_idx].object_entity_id)
                # Phase 7: an EXPLICIT mention reference (split pipeline) wins over a name lookup
                if rel_obs[rel_idx].subject_mention_id:
                    subj_ent = entity_by_id(rel_obs[rel_idx].subject_entity_id) or subj_ent
                if rel_obs[rel_idx].object_mention_id:
                    obj_ent = entity_by_id(rel_obs[rel_idx].object_entity_id) or obj_ent

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
        ev_items = extraction_data.get("events", [])
        ev_obs = paired(resolved.result.events if resolved else (), ev_items,
                        lambda o, d: list(o.participants) == list(d.get("participants", [])))
        for ev_idx, ev_data in enumerate(ev_items):
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

            for p_idx, p_name in enumerate(ev_data.get("participants", [])):
                p_ent = resolve_cached_entity(p_name)
                if p_ent is None and ev_obs[ev_idx] is not None and ev_obs[ev_idx].participant_entity_ids:
                    p_ent = entity_by_id(ev_obs[ev_idx].participant_entity_ids[p_idx])  # Phase 6
                if ev_obs[ev_idx] is not None and ev_obs[ev_idx].participant_refs and ev_obs[ev_idx].participant_entity_ids:
                    p_ent = entity_by_id(ev_obs[ev_idx].participant_entity_ids[p_idx]) or p_ent  # Phase 7: explicit ref
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
