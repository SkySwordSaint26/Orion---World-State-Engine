"""
Phase 6 — temporal expressions and temporal relations, no LLM (docs/wse_extraction_plan.md, Phase 6).
    expressions  GLiNER2 spans (the Phase 2 model, already loaded) labelled with the gold's temporal types. On the gold
                 stories it tied spaCy's DATE/TIME entities and their union (~0.3 exact F1: the gold's boundaries
                 are inconsistent) and alone gives the gold's types.
    relations    from BookNLP's dependency parse, between two extracted events: a clause introduced by before /
                 after / while / until, attached to another event ("I left before he arrived": left BEFORE arrived),
                 or the same markers as a preposition before a verb ("after leaving the room, I sat": sat AFTER
                 leaving). "when" and "as" are skipped as ambiguous (time, cause or simultaneity).
"""
from typing import Any, Dict, Optional

from app.contracts.gold import TEMPORAL_EXPRESSION_TYPES, TEMPORAL_RELATIONS
from extractor.coref import booknlp_output
from extractor.events import children
from extractor.mentions import best_type, gliner_spans

THRESHOLD = 0.5
LABELS = {
    "absolute_time": "a clock time, date, day or part of day: nine o'clock, at noon, Monday, this morning, last night",
    "relative_time": "a time relative to now or another event: yesterday, today, last week, after a while, later",
    "duration": "a length of time: six hours, three weeks, for a few minutes",
    "sequence_marker": "a word ordering events in time: then, afterwards, meanwhile, until then, first",
}
assert set(LABELS) <= set(TEMPORAL_EXPRESSION_TYPES)
MARKERS = {"before": "BEFORE", "until": "BEFORE", "after": "AFTER", "while": "DURING"}   # main event <relation> clause
assert set(MARKERS.values()) <= set(TEMPORAL_RELATIONS)


def temporal(doc: Dict[str, Any]) -> None:
    text = doc["text"]
    for (s, e), t in best_type(gliner_spans(text, LABELS, THRESHOLD)).items():
        doc["temporal_expressions"].append({"temporal_id": f"T{len(doc['temporal_expressions']) + 1}",
                                            "text": text[s:e], "type": t, "start": s, "end": e})

    tokens, _ = booknlp_output(text)
    kids = children(tokens)
    event_at = {e["start"]: e["event_id"] for e in doc["events"]}
    event = lambda j: event_at.get(int(tokens[j]["byte_onset"]))
    head = lambda j: int(tokens[j]["syntactic_head_ID"])
    for j, t in enumerate(tokens):
        clause: Optional[str] = event(j)
        if clause is None:
            continue
        if t["dependency_relation"] == "advcl":                  # "... before he arrived"
            main = head(j)
            markers = [tokens[k]["lemma"].lower() for k in kids.get(j, []) if tokens[k]["dependency_relation"] == "mark"]
        elif t["dependency_relation"] == "pcomp":                # "after leaving ..."
            main = head(head(j))
            markers = [tokens[head(j)]["lemma"].lower()]
        else:
            continue
        relation = next((MARKERS[m] for m in markers if m in MARKERS), None)
        if relation and event(main) and event(main) != clause:
            doc["temporal_relations"].append({"temporal_relation_id": f"TR{len(doc['temporal_relations']) + 1}",
                                              "source_event_id": event(main), "relation": relation,
                                              "target_event_id": clause})
