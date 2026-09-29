"""
Explicit mention-reference grounding (Phase 7). Relationships, events and facts produced by the split pipeline cite
their mentions by id (`subject_mention_id`, `participant_refs`, `entity_mention_id`). Once Phase 5 has given the
mentions entity ids, those references ground directly, with no name lookup involved. An explicit reference wins
over a name-based id; observations without references (monolithic output) are left untouched.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from app.contracts import ExtractionResult


def ground_mention_references(result: ExtractionResult) -> ExtractionResult:
    entity_of = {m.id: m.entity_id for m in result.entity_mentions if m.id}

    def eid(mention_id: Optional[str]) -> Optional[str]:
        return entity_of.get(mention_id) if mention_id else None

    def event_ids(e):
        if not e.participant_refs:
            return e.participant_entity_ids
        refs = [r for r in e.participant_refs if r.role != "location"]   # `participants` excludes the location role
        if len(refs) != len(e.participants):
            return e.participant_entity_ids
        old = e.participant_entity_ids or (None,) * len(refs)
        return tuple(eid(r.mention_id) or old[i] for i, r in enumerate(refs))

    return replace(
        result,
        relationships=tuple(replace(
            r, subject_entity_id=eid(r.subject_mention_id) or r.subject_entity_id,
            object_entity_id=eid(r.object_mention_id) or r.object_entity_id) for r in result.relationships),
        events=tuple(replace(e, participant_entity_ids=event_ids(e)) for e in result.events),
        facts=tuple(replace(f, entity_id=eid(f.entity_mention_id) or f.entity_id) for f in result.facts))
