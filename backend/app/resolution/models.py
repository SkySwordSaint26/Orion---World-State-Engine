"""
Entity-resolution contract (Phase 5): EntityMention -> canonical entity.

Pure, immutable, serializable, DB-free. `resolved_entity_id` is either the id of an entity that already exists
in the World State, or a PROVISIONAL id (`new:<n>`) for an entity that must be created; the integration layer
rebinds provisional ids to real ones once the rows exist.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

PROVISIONAL_PREFIX = "new:"


def is_provisional(entity_id: Optional[str]) -> bool:
    return bool(entity_id) and str(entity_id).startswith(PROVISIONAL_PREFIX)


class ResolutionType(str, Enum):
    EXACT_MATCH = "exact_match"            # identical string to a canonical name
    NORMALIZED_MATCH = "normalized_match"  # equal after case / whitespace / edge-punctuation folding
    ALIAS = "alias"                        # a stored alias, a listed nickname, or a unique short form
    PRONOUN = "pronoun"                    # he / she / they with exactly one compatible antecedent
    NEW_ENTITY = "new_entity"              # nothing matched: a new entity is required


@dataclass(frozen=True)
class KnownEntity:
    """An entity already in the World State (or created earlier in the same batch)."""

    id: str
    canonical_name: str
    entity_type: str = "unknown"
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityResolution:
    mention_id: str
    resolved_entity_id: str
    resolution_type: ResolutionType
    confidence: float
    evidence: str = ""

    def __post_init__(self) -> None:
        if not self.mention_id or not self.resolved_entity_id:
            raise ValueError("EntityResolution needs a mention_id and a resolved_entity_id")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1] (got {self.confidence})")

    @property
    def is_new(self) -> bool:
        return self.resolution_type is ResolutionType.NEW_ENTITY

    def to_dict(self) -> Dict[str, Any]:
        return {"mention_id": self.mention_id, "resolved_entity_id": self.resolved_entity_id,
                "resolution_type": self.resolution_type.value, "confidence": self.confidence,
                "evidence": self.evidence}


@dataclass(frozen=True)
class UnresolvedMention:
    """A mention deliberately left unresolved (ambiguous or conflicting). Never guessed."""

    mention_id: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {"mention_id": self.mention_id, "reason": self.reason}


@dataclass(frozen=True)
class NewEntity:
    entity_id: str  # provisional
    canonical_name: str
    entity_type: str
    first_mention_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {"entity_id": self.entity_id, "canonical_name": self.canonical_name,
                "entity_type": self.entity_type, "first_mention_id": self.first_mention_id}


@dataclass(frozen=True)
class EntityResolutionResult:
    resolutions: Tuple[EntityResolution, ...] = ()
    unresolved: Tuple[UnresolvedMention, ...] = ()
    new_entities: Tuple[NewEntity, ...] = ()

    @property
    def mapping(self) -> Dict[str, str]:
        """mention_id -> resolved_entity_id"""
        return {r.mention_id: r.resolved_entity_id for r in self.resolutions}

    def get(self, mention_id: str) -> Optional[EntityResolution]:
        return next((r for r in self.resolutions if r.mention_id == mention_id), None)

    def to_dict(self) -> Dict[str, Any]:
        return {"resolutions": [r.to_dict() for r in self.resolutions],
                "unresolved": [u.to_dict() for u in self.unresolved],
                "new_entities": [n.to_dict() for n in self.new_entities]}

    def to_json(self, **kw: Any) -> str:
        return json.dumps(self.to_dict(), **kw)
