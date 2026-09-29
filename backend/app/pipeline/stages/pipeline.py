"""
Split extraction pipeline (Phase 7): entities -> relationships -> events -> facts, one focused LLM call each.

Each stage validates its own output and raises `StageError` on malformed output; no stage reads another stage's
raw output. Stages 2-4 only see the validated mention list of stage 1 and reference it by explicit mention ids.
Results are combined into one `ExtractionResult` per chunk, in the same shape the monolithic extractor
produces, so Phase 5 resolution, Phase 6 clustering and grounding run unchanged afterwards.

Provenance is assigned BY CODE. Stage 1 (Phase 7.2): the model lists distinct names, code creates one mention per
exact occurrence in a NEW sentence (exact offsets, sentence-level provenance). Stages 2-4 (Phase 7.1): every item
carries mandatory `evidence`, which must occur verbatim in a NEW sentence (overlap sentences are context only); one
match grounds the item to that sentence, several make it ambiguous (chunk-level provenance, never fatal). Stages 2-4
see one label per distinct name; a label resolves to that name's occurrence in the item's grounded sentence.
Trigger offsets are computed from the sentence text, and ids are chapter-unique (`IdCounters`).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional

from app.contracts import ExtractionResult, FactOrigin
from app.pipeline.stages.common import Generate, IdCounters, StageError
from app.pipeline.stages.entities import extract_mentions
from app.pipeline.stages.events import extract_events
from app.pipeline.stages.facts import extract_facts
from app.pipeline.stages.grounding import GroundingLog
from app.pipeline.stages.relationships import extract_relationships

STAGES = ("entities", "relationships", "events", "facts")


def extract_chunk_split(
    chunk: Any, document: Any, ids: IdCounters, chapter_number: int = 1, generate: Optional[Generate] = None,
    grounding: Optional[GroundingLog] = None
) -> ExtractionResult:
    """Run the four stages on one chunk. Raises StageError (naming the stage) on the first malformed output.
    `grounding` (optional) collects one record per item; a per-chunk summary is logged even when a stage fails."""
    grounding = grounding if grounding is not None else GroundingLog()
    grounding.chunk_id = chunk.id
    try:
        mentions = extract_mentions(chunk, document, ids, generate, grounding)
        relationships = extract_relationships(chunk, document, mentions, generate, grounding)
        events, temporal = extract_events(chunk, document, mentions, ids, generate, grounding)
        facts = extract_facts(chunk, document, mentions, generate, grounding)
    finally:
        grounding.log_summary()

    # The World State integration reads attributes from the entity records, exactly as it does for the
    # monolithic output: fold ATTRIBUTE facts into their mention's `attributes` (the facts are kept as well).
    attrs: Dict[str, Dict[str, Any]] = {}
    for f in facts:
        if f.origin is FactOrigin.ATTRIBUTE and f.entity_mention_id:
            attrs.setdefault(f.entity_mention_id, {}).setdefault(f.property, f.value)
    mentions = [replace(m, attributes=attrs[m.id]) if m.id in attrs else m for m in mentions]

    return ExtractionResult(
        chapter_number=chapter_number, entity_mentions=tuple(mentions), relationships=tuple(relationships),
        events=tuple(events), facts=tuple(facts), temporal_relations=tuple(temporal))
