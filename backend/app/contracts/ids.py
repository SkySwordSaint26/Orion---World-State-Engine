"""Deterministic gold-style id assignment for observations (Phase 5). Existing ids are kept."""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence, Tuple

from app.contracts.models import ExtractionResult


def _number(items: Sequence, prefix: str) -> Tuple:
    used = {o.id for o in items if o.id}
    out, n = [], 0
    for o in items:
        if o.id:
            out.append(o)
            continue
        n += 1
        while f"{prefix}{n}" in used:
            n += 1
        out.append(replace(o, id=f"{prefix}{n}"))
    return tuple(out)


def assign_ids(result: ExtractionResult) -> ExtractionResult:
    """Return `result` with every observation numbered in order (M1.., E1.., R1.., F1.., T1.., TR1..)."""
    return replace(
        result,
        entity_mentions=_number(result.entity_mentions, "M"),
        events=_number(result.events, "E"),
        relationships=_number(result.relationships, "R"),
        facts=_number(result.facts, "F"),
        temporal_expressions=_number(result.temporal_expressions, "T"),
        temporal_relations=_number(result.temporal_relations, "TR"),
    )
