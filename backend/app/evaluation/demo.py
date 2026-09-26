"""
Live demonstration of the split pipeline on a short passage: each stage's output and timing, printed as it happens.

It calls the four stage functions in the same order and with the same arguments as `extract_chunk_split`, so what
is shown is exactly what the pipeline does. For every mention and event trigger it also re-checks, visibly, that
the stored offsets point at exactly that text in the passage. A stage that rejects its output prints the reasons.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from app.config.settings import settings
from app.pipeline import extractor
from app.pipeline.stages import (GroundingLog, IdCounters, StageError, extract_events, extract_facts, extract_mentions,
                                 extract_relationships)
from app.preprocessing import chunk_document, preprocess_chapter

Print = Callable[[str], None]


def _check(text: str, start: Optional[int], end: Optional[int], expected: str) -> str:
    if start is None:
        return "no offsets"
    return "✓ offsets verified" if text[start:end] == expected else f"✗ offsets point at {text[start:end]!r}"


def run_demo(text: str, generate: Any = None, out: Print = print) -> bool:
    """Run the four stages on every chunk of `text`, printing as it goes. True when every chunk completes."""
    doc = preprocess_chapter(text)
    chunks = chunk_document(doc, max_chars=extractor.CHUNK_MAX_CHARS,
                            overlap_sentences=extractor.CHUNK_OVERLAP_SENTENCES)
    mode = ("partial (invalid items dropped)" if settings.ALLOW_PARTIAL_STAGE
            else "strict (any invalid item fails the stage)")
    out(f"Model {settings.OLLAMA_MODEL} · {len(text)} characters · {len(doc.sentences)} sentences · "
        f"{len(chunks)} chunk(s) · mode: {mode}")
    ids, ok = IdCounters(), True
    for chunk in chunks:
        out(f"\n=== {chunk.id}: sentences {chunk.sentence_ids[0]}–{chunk.sentence_ids[-1]}")
        log = GroundingLog()
        log.chunk_id = chunk.id
        t0 = time.time()
        stage = "entities"
        try:
            mentions = extract_mentions(chunk, doc, ids, generate, log)
            out(f"\n[Stage 1 · entities] {len(mentions)} mentions in {time.time() - t0:.1f}s")
            for m in mentions:
                out(f"  {m.id:>4}  {m.text!r:28} {m.type:12} chars {m.start}–{m.end}  {m.sentence_ids[0]}  "
                    f"{_check(doc.text, m.start, m.end, m.text)}")

            stage, t0 = "relationships", time.time()
            relationships = extract_relationships(chunk, doc, mentions, generate, log)
            out(f"\n[Stage 2 · relationships] {len(relationships)} in {time.time() - t0:.1f}s")
            for r in relationships:
                out(f"  {r.subject} —{r.predicate}→ {r.object}   ({r.certainty})\n        evidence: {r.raw_text!r}")

            stage, t0 = "events", time.time()
            events, temporal = extract_events(chunk, doc, mentions, ids, generate, log)
            out(f"\n[Stage 3 · events] {len(events)} events, {len(temporal)} temporal links in {time.time() - t0:.1f}s")
            for e in events:
                who = ", ".join(f"{p.mention_id}:{p.role}" for p in e.participant_refs) or "none"
                out(f"  {e.id:>4}  {e.type:13} trigger {e.trigger!r} ({_check(doc.text, e.start, e.end, e.trigger)})  "
                    f"participants {who}\n        evidence: {e.raw_text!r}")

            stage, t0 = "facts", time.time()
            facts = extract_facts(chunk, doc, mentions, generate, log)
            out(f"\n[Stage 4 · facts] {len(facts)} in {time.time() - t0:.1f}s")
            for f in facts:
                out(f"  {f.entity} ({f.entity_mention_id}) · {f.property} = {f.value!r}   [{f.origin.value}]\n"
                    f"        evidence: {f.raw_text!r}")
        except StageError as exc:
            ok = False
            out(f"\n[{stage}] REJECTED after {time.time() - t0:.1f}s. The validator refused this output:")
            for reason in exc.errors:
                out(f"  - {reason}")
            out("  (strict mode stops this chunk here; set ALLOW_PARTIAL_STAGE=true to drop only the invalid items)")
        except Exception as exc:                                  # LLM unreachable, timeout, ...
            ok = False
            out(f"\n[{stage}] FAILED after {time.time() - t0:.1f}s: {type(exc).__name__}: {exc}")
        s = log.summary()
        out(f"\nGrounding for {chunk.id}: {s['located']} names located by code, {s['unique']} quotes matched to one "
            f"sentence, {s['ambiguous']} ambiguous, {s['unmatched']} unmatched")
        for name, stats in log.stages.items():
            if stats["dropped"]:
                out(f"  {name}: {stats['dropped']} invalid item(s) dropped")
    return ok
