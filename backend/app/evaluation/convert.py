"""
Converts a teammate annotation file (the format the gold annotators export) into an `orion_gold_v1` document.

The mapping is a rename, never a repair: every annotated item is kept as written. Only what the schema cannot
hold is changed, and each change is reported in `issues`:

    entity_mentions[].start_offset/end_offset -> mentions[].start/end
    events[].trigger {text, start_offset, end_offset} -> events[].trigger/start/end
    temporal[].expression -> temporal_expressions[].text; `type` is required but not annotated -> "other"
    coreference clusters with fewer than 2 mentions are dropped (the schema requires >= 2)
    source_file / review_notes are not part of the schema and are dropped
    text (from the source file) and schema_version are added

Spans are checked against the text but NOT moved: a span whose text differs from the annotation, or that starts or
ends inside a word ("road" in "broadcast"), is reported, and so is a span annotated more than once. The scorer
excludes the bad spans from the gold and counts a duplicated span once.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.evaluation.schema import schema_errors

SCHEMA_VERSION = "1.0"


def span_problem(text: str, start: int, end: int, expected: str) -> Optional[str]:
    """Why the span [start, end) cannot be a gold span of `expected`, or None when it is fine."""
    if not (0 <= start <= end <= len(text)):
        return f"span ({start}, {end}) lies outside the text"
    if text[start:end] != expected:
        return f"text at ({start}, {end}) is {text[start:end]!r}, not {expected!r}"
    if (start > 0 and text[start - 1].isalnum()) or (end < len(text) and text[end].isalnum()):
        around = text[max(0, start - 10):end + 10].replace("\n", " ")
        return f"span ({start}, {end}) cuts through a word: ...{around}..."
    return None


def convert_annotation(annotation: Dict[str, Any], text: str) -> Tuple[Dict[str, Any], List[str]]:
    """(gold document, issues). The document is schema-valid unless `issues` reports schema errors."""
    issues: List[str] = []

    mentions = []
    for m in annotation.get("entity_mentions", []):
        d = {"mention_id": m["mention_id"], "text": m["text"], "type": m["type"],
             "start": m["start_offset"], "end": m["end_offset"]}
        if m.get("mention_kind") is not None:
            d["mention_kind"] = m["mention_kind"]
        problem = span_problem(text, d["start"], d["end"], d["text"])
        if problem:
            issues.append(f"{d['mention_id']}: {problem}")
        mentions.append(d)

    clusters = []
    for c in annotation.get("coreference_clusters", []):
        if len(c["mentions"]) < 2:
            issues.append(f"{c['cluster_id']}: dropped, a cluster needs at least 2 mentions (has {c['mentions']})")
            continue
        clusters.append({"cluster_id": c["cluster_id"], "mentions": list(c["mentions"])})

    events = []
    for e in annotation.get("events", []):
        trig = e["trigger"]
        d = {"event_id": e["event_id"], "type": e["type"], "trigger": trig["text"], "start": trig["start_offset"],
             "end": trig["end_offset"],
             "participants": [{"role": p["role"], "mention_id": p["mention_id"]} for p in e.get("participants", [])]}
        problem = span_problem(text, d["start"], d["end"], d["trigger"])
        if problem:
            issues.append(f"{d['event_id']}: trigger {problem}")
        events.append(d)

    relationships = [{k: r[k] for k in ("relationship_id", "subject_mention_id", "predicate", "object_mention_id")}
                     for r in annotation.get("relationships", [])]
    facts = [{k: f[k] for k in ("fact_id", "entity_mention_id", "property", "value")}
             for f in annotation.get("facts", [])]

    expressions = []
    for t in annotation.get("temporal", []):
        d = {"temporal_id": t["temporal_id"], "text": t["expression"], "type": t.get("type") or "other",
             "start": t["start_offset"], "end": t["end_offset"]}
        problem = span_problem(text, d["start"], d["end"], d["text"])
        if problem:
            issues.append(f"{d['temporal_id']}: {problem}")
        expressions.append(d)
    untyped = sum(1 for t in annotation.get("temporal", []) if not t.get("type"))
    if untyped:
        issues.append(f"{untyped} temporal expression(s) have no annotated type; set to 'other'")

    temporal_relations = [{k: r[k] for k in ("temporal_relation_id", "source_event_id", "relation", "target_event_id")}
                          for r in annotation.get("temporal_relations", [])]

    for kind, items, key in (("mention", mentions, "mention_id"), ("event trigger", events, "event_id"),
                             ("temporal expression", expressions, "temporal_id")):
        by_span: Dict[Tuple[int, int], List[str]] = {}
        for it in items:
            by_span.setdefault((it["start"], it["end"]), []).append(it[key])
        for (s, e), ids in by_span.items():
            if len(ids) > 1:
                issues.append(f"{', '.join(ids)}: same {kind} span ({s}, {e}) {text[s:e]!r} annotated {len(ids)} times")

    for key in sorted(set(annotation) - {"story_id", "entity_mentions", "coreference_clusters", "events",
                                         "relationships", "facts", "temporal", "temporal_relations"}):
        issues.append(f"'{key}' is not part of the schema; dropped")

    doc: Dict[str, Any] = {"schema_version": SCHEMA_VERSION, "story_id": annotation["story_id"]}
    if annotation.get("source_file"):
        doc["title"] = Path(annotation["source_file"]).stem
    doc.update(text=text, mentions=mentions, coreference_clusters=clusters, events=events,
               relationships=relationships, facts=facts, temporal_expressions=expressions,
               temporal_relations=temporal_relations)
    issues += [f"schema: {e}" for e in schema_errors(doc)]
    return doc, issues
