"""Deterministic mention -> entity resolution (Phase 5). See resolver.py for the exact rules."""
from app.resolution.models import (
    EntityResolution, EntityResolutionResult, KnownEntity, NewEntity, ResolutionType, UnresolvedMention,
    is_provisional,
)
from app.resolution.references import ground_mention_references
from app.resolution.resolver import NICKNAMES, ResolvedExtraction, name_key, resolve_entities

__all__ = [
    "ground_mention_references",
    "EntityResolution", "EntityResolutionResult", "KnownEntity", "NewEntity", "ResolutionType",
    "UnresolvedMention", "is_provisional", "NICKNAMES", "ResolvedExtraction", "name_key", "resolve_entities",
]
