"""Plain, database-free data passed to and returned from consistency rules."""
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


@dataclass(frozen=True)
class FactVersionView:
    version_id: Optional[str]
    value: Any
    status: str
    chapter_number: Optional[int] = None   # None when the version has no chapter (e.g. added manually)


@dataclass(frozen=True)
class FactCheck:
    """One newly written fact version plus every OTHER version of the same entity+property, oldest first."""
    entity_name: str
    property_name: str                     # already normalized
    new: FactVersionView
    history: Tuple[FactVersionView, ...] = ()


@dataclass(frozen=True)
class RelationshipVersionView:
    version_id: Optional[str]
    predicate: str                         # already normalized
    status: str
    chapter_number: Optional[int] = None
    source_entity_id: Optional[str] = None
    source_name: str = ""


@dataclass(frozen=True)
class RelationshipCheck:
    """
    One newly written relationship version.
    pair_history: other versions of the same (source, target) relationship, oldest first.
    incoming: versions of OTHER relationships that point at the same target (only loaded for
              predicates that need it), oldest first.
    """
    subject_name: str
    object_name: str
    new: RelationshipVersionView
    pair_history: Tuple[RelationshipVersionView, ...] = ()
    incoming: Tuple[RelationshipVersionView, ...] = ()


@dataclass(frozen=True)
class TemporalCheck:
    event_ids: Tuple[str, ...]
    relations: Tuple[Tuple[str, str, str], ...]   # (event_1, BEFORE|AFTER|SIMULTANEOUS, event_2)
    chapter_number: Optional[int] = None


@dataclass(frozen=True)
class Finding:
    """One detected contradiction, expressed only with data the existing contradictions table can hold."""
    rule_id: str
    contradiction_type: str
    explanation: str
    confidence: float
    old_fact_version_id: Optional[str] = None
    new_fact_version_id: Optional[str] = None
    old_relationship_version_id: Optional[str] = None
    new_relationship_version_id: Optional[str] = None
    event_refs: Tuple[str, ...] = ()       # engine-local event ids; the recorder maps them to Event rows

    @property
    def stored_explanation(self) -> str:
        # The schema has no rule column, so the rule id is carried as a stable prefix.
        return f"[{self.rule_id}] {self.explanation}"
