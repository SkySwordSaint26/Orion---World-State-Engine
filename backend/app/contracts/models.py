"""
Pipeline data contracts (Phase 4).

Explicit, immutable, serializable models for what flows between pipeline stages:

    raw chapter text --preprocess--> ChapterDocument --chunk--> Chunk
    Chunk --extract--> ExtractionResult(EntityMention[], Relationship[], Event[], FactObservation[],
                                        TemporalRelation[])

Every extracted item is an `Observation`: something the text was *said* to assert, BEFORE it becomes a
world-state fact. Observations are not persisted yet.

Field names follow `orion_gold_v1.schema.json` (text/type/trigger/start/end, source_event_id/target_event_id,
...). Fields the schema has but the current extractor cannot supply (mention/trigger offsets, mention_kind,
trigger, participant roles, mention-id references, temporal expressions) are OPTIONAL and NOT YET POPULATED.
Fields the schema does not have (canonical_name, attributes, certainty, location, time_expression,
previous_value, caused_by_event, origin) are kept because the legacy output and integration need them.
Values are kept exactly as the LLM produced them: gold enums are checked by `gold.py`, never enforced here
(remapping would be normalization).
NOTE (historic): `orion_gold_v1.schema.json` was not available in
the repository when Phase 4 was written; Phase 4.5 aligned the models with it (see `gold.py` for the mapping,
vocabularies and the strict projection).

Span rule: `source_span` is `(start, end)` in CHAPTER coordinates and `sentence_ids` are ids of the
chapter's `ChapterDocument`. The LLM does not report where an item came from, so today both describe the
whole chunk the item was extracted from (chunk-level provenance). Per-item spans need a later stage.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Tuple


class ContractError(ValueError):
    """An object crossing a pipeline boundary violates its contract."""


class ObservationKind(str, Enum):
    ENTITY = "entity"
    EVENT = "event"
    RELATIONSHIP = "relationship"
    FACT = "fact"
    TEMPORAL_RELATION = "temporal_relation"
    TEMPORAL_EXPRESSION = "temporal_expression"


def _require_text(owner: str, name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{owner}.{name} is required and must be a non-empty string (got {value!r})")


def _check_entity_ids(owner: str, *ids: Optional[str]) -> None:
    for eid in ids:
        if eid is not None and (not isinstance(eid, str) or not eid.strip()):
            raise ContractError(f"{owner}: entity id must be None or a non-empty string (got {eid!r})")


def _check_mention_refs(owner: str, *ids: Optional[str]) -> None:
    for mid in ids:
        if mid is not None and not re.fullmatch("M[0-9]+", str(mid)):
            raise ContractError(f"{owner}: mention id must match M<number> (got {mid!r})")


@dataclass(frozen=True, kw_only=True)
class Observation:
    """Base of every extracted item. `kind` is fixed per subclass."""

    KIND: ClassVar[ObservationKind]
    ID_PREFIX: ClassVar[str] = ""  # gold id prefix: M, E, R, F, T, TR

    source_chunk: str
    source_span: Tuple[int, int]
    sentence_ids: Tuple[str, ...]
    raw_text: str = ""  # supporting text the LLM quoted (its "evidence"); optional
    confidence: Optional[float] = None  # LLM-reported, if any; the current prompt does not produce one
    id: Optional[str] = None  # gold id ("M1", "E2", ...); NOT YET ASSIGNED by the extractor (see gold.py)

    @property
    def kind(self) -> ObservationKind:
        return self.KIND

    def __post_init__(self) -> None:
        owner = type(self).__name__
        object.__setattr__(self, "source_span", tuple(self.source_span))
        object.__setattr__(self, "sentence_ids", tuple(self.sentence_ids))
        _require_text(owner, "source_chunk", self.source_chunk)
        span = self.source_span
        if (len(span) != 2 or not all(isinstance(x, int) and not isinstance(x, bool) for x in span)
                or span[0] < 0 or span[0] > span[1]):
            raise ContractError(f"{owner}.source_span must be (start, end) with 0 <= start <= end (got {span!r})")
        if not self.sentence_ids or not all(isinstance(s, str) and s for s in self.sentence_ids):
            raise ContractError(f"{owner}.sentence_ids must be a non-empty tuple of ids (got {self.sentence_ids!r})")
        if self.confidence is not None and not (
                isinstance(self.confidence, (int, float)) and not isinstance(self.confidence, bool)
                and 0.0 <= self.confidence <= 1.0):
            raise ContractError(f"{owner}.confidence must be None or within [0, 1] (got {self.confidence!r})")
        if self.id is not None and not re.fullmatch(f"{self.ID_PREFIX}[0-9]+", str(self.id)):
            raise ContractError(f"{owner}.id must match {self.ID_PREFIX}<number> (got {self.id!r})")
        self._validate_fields()

    def _check_own_span(self) -> None:
        """Gold `start`/`end`: the item's OWN character span (mention text, event trigger), inside the source span."""
        start, end = getattr(self, "start"), getattr(self, "end")
        if start is None and end is None:
            return
        owner = type(self).__name__
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (start, end)) or start is None or end is None:
            raise ContractError(f"{owner}.start/end must both be integers or both be None (got {start!r}, {end!r})")
        if not (self.source_span[0] <= start <= end <= self.source_span[1]):
            raise ContractError(f"{owner}: own span ({start}, {end}) must lie inside source_span {self.source_span}")

    def _validate_fields(self) -> None:  # subclass hook
        pass

    def _base_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.KIND.value,
            "source_chunk": self.source_chunk,
            "source_span": list(self.source_span),
            "sentence_ids": list(self.sentence_ids),
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "id": self.id,
        }


@dataclass(frozen=True, kw_only=True)
class EntityMention(Observation):
    """Gold `mention`. `text` is the surface form, `type` the LLM's entity type (gold enum checked in gold.py)."""

    KIND: ClassVar[ObservationKind] = ObservationKind.ENTITY
    ID_PREFIX: ClassVar[str] = "M"

    text: str
    type: str = "unknown"
    mention_kind: Optional[str] = None  # gold: proper|nominal|pronominal. NOT YET POPULATED
    start: Optional[int] = None  # own offsets in the chapter. NOT YET POPULATED (source_span is the chunk)
    end: Optional[int] = None
    # -- not in gold (kept for the legacy output / integration):
    canonical_name: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    entity_id: Optional[str] = None  # Phase 5: resolved World State entity; None = unresolved / not yet resolved

    def _validate_fields(self) -> None:
        _require_text("EntityMention", "text", self.text)
        _check_entity_ids("EntityMention", self.entity_id)
        if not self.canonical_name:  # gold has no canonical_name; default to the surface form
            object.__setattr__(self, "canonical_name", self.text)
        _require_text("EntityMention", "canonical_name", self.canonical_name)
        if not isinstance(self.attributes, dict):
            raise ContractError("EntityMention.attributes must be a dict")
        self._check_own_span()

    def to_dict(self) -> Dict[str, Any]:
        return {**self._base_dict(), "text": self.text, "type": self.type, "mention_kind": self.mention_kind,
                "start": self.start, "end": self.end, "canonical_name": self.canonical_name,
                "attributes": dict(self.attributes), "entity_id": self.entity_id}


@dataclass(frozen=True, kw_only=True)
class Relationship(Observation):
    KIND: ClassVar[ObservationKind] = ObservationKind.RELATIONSHIP
    ID_PREFIX: ClassVar[str] = "R"

    subject: str  # names (what the LLM emits); gold refers to mentions by id, see the *_mention_id fields
    predicate: str
    object: str
    subject_mention_id: Optional[str] = None  # gold. NOT YET POPULATED (needs mention grounding)
    object_mention_id: Optional[str] = None
    certainty: str = "DEFINITE"  # not in gold
    subject_entity_id: Optional[str] = None  # Phase 5: resolved World State entities (None = unresolved)
    object_entity_id: Optional[str] = None

    def _validate_fields(self) -> None:
        for name in ("subject", "predicate", "object"):
            _require_text("Relationship", name, getattr(self, name))
        _check_mention_refs("Relationship", self.subject_mention_id, self.object_mention_id)
        _check_entity_ids("Relationship", self.subject_entity_id, self.object_entity_id)

    def to_dict(self) -> Dict[str, Any]:
        return {**self._base_dict(), "subject": self.subject, "predicate": self.predicate,
                "object": self.object, "subject_mention_id": self.subject_mention_id,
                "object_mention_id": self.object_mention_id, "certainty": self.certainty,
                "subject_entity_id": self.subject_entity_id, "object_entity_id": self.object_entity_id}


@dataclass(frozen=True, kw_only=True)
class EventParticipant:
    """Gold `eventParticipant`: a mention playing a role. NOT YET POPULATED by the extractor."""

    role: str
    mention_id: str

    def __post_init__(self) -> None:
        _require_text("EventParticipant", "role", self.role)
        _check_mention_refs("EventParticipant", self.mention_id)
        if self.mention_id is None:
            raise ContractError("EventParticipant.mention_id is required")

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "mention_id": self.mention_id}


@dataclass(frozen=True, kw_only=True)
class Event(Observation):
    KIND: ClassVar[ObservationKind] = ObservationKind.EVENT
    ID_PREFIX: ClassVar[str] = "E"

    local_id: str  # extractor-local label ("event_1"); NOT globally unique (see temporal-normalization TODO)
    type: str = "EVENT"
    trigger: Optional[str] = None  # gold. NOT YET POPULATED (the prompt has no trigger field)
    start: Optional[int] = None  # trigger offsets. NOT YET POPULATED
    end: Optional[int] = None
    participant_refs: Tuple[EventParticipant, ...] = ()  # gold participants[{role, mention_id}]. NOT YET POPULATED
    # -- not in gold (kept for the legacy output / integration):
    participants: Tuple[str, ...] = ()  # names
    location: Optional[str] = None  # gold models this as a participant with role "location"
    time_expression: Optional[str] = None  # gold models this as a separate temporal_expression
    participant_entity_ids: Tuple[Optional[str], ...] = ()  # Phase 5: aligned with `participants`; None = unresolved

    def _validate_fields(self) -> None:
        _require_text("Event", "local_id", self.local_id)
        object.__setattr__(self, "participants", tuple(self.participants))
        object.__setattr__(self, "participant_refs", tuple(self.participant_refs))
        if not all(isinstance(p, EventParticipant) for p in self.participant_refs):
            raise ContractError("Event.participant_refs must contain EventParticipant objects")
        object.__setattr__(self, "participant_entity_ids", tuple(self.participant_entity_ids))
        if self.participant_entity_ids and len(self.participant_entity_ids) != len(self.participants):
            raise ContractError("Event.participant_entity_ids must align one-to-one with participants")
        _check_entity_ids("Event", *self.participant_entity_ids)
        if self.trigger is not None:
            _require_text("Event", "trigger", self.trigger)
        self._check_own_span()

    def to_dict(self) -> Dict[str, Any]:
        return {**self._base_dict(), "local_id": self.local_id, "type": self.type, "trigger": self.trigger,
                "start": self.start, "end": self.end,
                "participant_refs": [p.to_dict() for p in self.participant_refs],
                "participants": list(self.participants), "location": self.location,
                "time_expression": self.time_expression,
                "participant_entity_ids": list(self.participant_entity_ids)}


class FactOrigin(str, Enum):
    ATTRIBUTE = "attribute"  # from an entity's `attributes` map
    STATE_CHANGE = "state_change"  # from the extractor's `state_changes` list


@dataclass(frozen=True, kw_only=True)
class FactObservation(Observation):
    """An attribute assertion: `entity` has `property` = `value` (optionally changed from `previous_value`)."""

    KIND: ClassVar[ObservationKind] = ObservationKind.FACT
    ID_PREFIX: ClassVar[str] = "F"

    entity: str  # name; gold refers to the mention by id, see entity_mention_id
    property: str
    value: Any
    entity_mention_id: Optional[str] = None  # gold. NOT YET POPULATED
    previous_value: Any = None
    caused_by_event: Optional[str] = None
    origin: FactOrigin = FactOrigin.STATE_CHANGE
    entity_id: Optional[str] = None  # Phase 5: resolved World State entity (None = unresolved)

    def _validate_fields(self) -> None:
        _require_text("FactObservation", "entity", self.entity)
        _require_text("FactObservation", "property", self.property)
        if self.value is None:
            raise ContractError("FactObservation.value is required")
        _check_mention_refs("FactObservation", self.entity_mention_id)
        _check_entity_ids("FactObservation", self.entity_id)

    def to_dict(self) -> Dict[str, Any]:
        return {**self._base_dict(), "entity": self.entity, "property": self.property, "value": self.value,
                "entity_mention_id": self.entity_mention_id, "previous_value": self.previous_value, "caused_by_event": self.caused_by_event,
                "origin": self.origin.value, "entity_id": self.entity_id}


@dataclass(frozen=True, kw_only=True)
class TemporalRelation(Observation):
    """Gold `temporalRelation`. Until event ids are assigned the two ids hold the extractor-local event labels."""

    KIND: ClassVar[ObservationKind] = ObservationKind.TEMPORAL_RELATION
    ID_PREFIX: ClassVar[str] = "TR"

    source_event_id: str
    relation: str
    target_event_id: str

    def _validate_fields(self) -> None:
        for name in ("source_event_id", "relation", "target_event_id"):
            _require_text("TemporalRelation", name, getattr(self, name))

    def to_dict(self) -> Dict[str, Any]:
        return {**self._base_dict(), "source_event_id": self.source_event_id, "relation": self.relation,
                "target_event_id": self.target_event_id}


@dataclass(frozen=True, kw_only=True)
class TemporalExpression(Observation):
    """Gold `temporalExpression`. NOT YET EXTRACTED (the prompt only has an event `time_expression` string)."""

    KIND: ClassVar[ObservationKind] = ObservationKind.TEMPORAL_EXPRESSION
    ID_PREFIX: ClassVar[str] = "T"

    text: str
    type: str = "other"
    start: Optional[int] = None
    end: Optional[int] = None

    def _validate_fields(self) -> None:
        _require_text("TemporalExpression", "text", self.text)
        self._check_own_span()

    def to_dict(self) -> Dict[str, Any]:
        return {**self._base_dict(), "text": self.text, "type": self.type, "start": self.start, "end": self.end}


@dataclass(frozen=True, kw_only=True)
class CoreferenceCluster:
    """
    Mentions of ONE chapter that refer to the same entity. Gold `coreferenceCluster` is `cluster_id` + `mentions`
    (mention ids, at least 2, unique); the rest is internal: `canonical_name` and `entity_id` are optional
    (`entity_id` only when the members are resolved to one World State entity), `rules` names the strict rules
    that formed the cluster (exact_text / same_entity / pronoun) for auditing.
    """

    cluster_id: str
    mentions: Tuple[str, ...] = ()
    canonical_name: Optional[str] = None
    entity_id: Optional[str] = None
    rules: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mentions", tuple(self.mentions))
        object.__setattr__(self, "rules", tuple(self.rules))
        if not re.fullmatch("C[0-9]+", str(self.cluster_id)):
            raise ContractError(f"CoreferenceCluster.cluster_id must match C<number> (got {self.cluster_id!r})")
        if len(self.mentions) < 2 or len(set(self.mentions)) != len(self.mentions):
            raise ContractError("CoreferenceCluster.mentions needs at least 2 unique mention ids")
        _check_mention_refs("CoreferenceCluster", *self.mentions)
        if self.canonical_name is not None:
            _require_text("CoreferenceCluster", "canonical_name", self.canonical_name)
        _check_entity_ids("CoreferenceCluster", self.entity_id)

    def to_gold_dict(self) -> Dict[str, Any]:
        """Exactly the gold schema shape (the schema forbids extra properties)."""
        return {"cluster_id": self.cluster_id, "mentions": list(self.mentions)}

    def to_dict(self) -> Dict[str, Any]:
        out = self.to_gold_dict()
        if self.canonical_name is not None:
            out["canonical_name"] = self.canonical_name
        if self.entity_id is not None:
            out["entity_id"] = self.entity_id
        if self.rules:
            out["rules"] = list(self.rules)
        return out


@dataclass(frozen=True, kw_only=True)
class ExtractorInput:
    """Extractor stage input: one chunk (sentences + offsets) of a chapter document."""

    document: Any  # app.preprocessing.ChapterDocument
    chunk: Any  # app.preprocessing.Chunk
    chapter_number: int = 1


@dataclass(frozen=True, kw_only=True)
class ExtractionResult:
    """Extractor stage output: typed observations, in extraction order, for one chunk or a whole chapter."""

    chapter_number: int = 1
    entity_mentions: Tuple[EntityMention, ...] = ()
    relationships: Tuple[Relationship, ...] = ()
    events: Tuple[Event, ...] = ()
    facts: Tuple[FactObservation, ...] = ()
    temporal_relations: Tuple[TemporalRelation, ...] = ()
    temporal_expressions: Tuple[TemporalExpression, ...] = ()  # gold; not extracted yet, always empty today
    coreference_clusters: Tuple[CoreferenceCluster, ...] = ()  # filled by app/coreference (Phase 6); empty from the extractor

    def observations(self) -> List[Observation]:
        return [*self.entity_mentions, *self.relationships, *self.events, *self.facts, *self.temporal_expressions,
                *self.temporal_relations]

    def merge(self, other: "ExtractionResult") -> "ExtractionResult":
        return ExtractionResult(
            chapter_number=self.chapter_number,
            entity_mentions=self.entity_mentions + other.entity_mentions,
            relationships=self.relationships + other.relationships,
            events=self.events + other.events,
            facts=self.facts + other.facts,
            temporal_relations=self.temporal_relations + other.temporal_relations,
            temporal_expressions=self.temporal_expressions + other.temporal_expressions,
            coreference_clusters=self.coreference_clusters + other.coreference_clusters,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "entity_mentions": [o.to_dict() for o in self.entity_mentions],
            "relationships": [o.to_dict() for o in self.relationships],
            "events": [o.to_dict() for o in self.events],
            "facts": [o.to_dict() for o in self.facts],
            "temporal_relations": [o.to_dict() for o in self.temporal_relations],
            "temporal_expressions": [o.to_dict() for o in self.temporal_expressions],
            "coreference_clusters": [c.to_dict() for c in self.coreference_clusters],
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)
