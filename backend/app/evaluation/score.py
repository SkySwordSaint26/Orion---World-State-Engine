"""
Scores a predicted `orion_gold_v1` document against a gold one (same story, same text).

Metrics (each: tp / fp / fn, precision / recall / F1):

    mentions_exact        mention span identical
    mentions_typed        span identical and same type
    mentions_overlap      spans overlap (1:1, largest overlap first); tolerates boundary differences
    mention_texts         DIAGNOSTIC, ignores offsets: distinct mention strings, compared exactly
    triggers_exact        event trigger span identical
    triggers_typed        trigger span identical and same event type
    event_arguments       (event, role, participant) with events and participants aligned by overlapping span
    relationships         (subject entity, predicate, object entity)
    facts                 (entity, property, value); values compared case-insensitively, whitespace-trimmed
    temporal_expressions  span identical

Relationships and facts are scored per ENTITY, not per mention: a mention stands for its gold coreference cluster
(or itself when unclustered), so linking a relationship to another mention of the same character still counts.

Gold spans that do not fit the text (wrong text, or cutting through a word; see convert.span_problem) are excluded
from the gold and counted in `gold_excluded`. Predicted items without offsets can match nothing: they count as
false positives and are counted in `pred_unanchored`. A span annotated twice in the gold counts once; a predicted
duplicate is a false positive.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.evaluation.convert import span_problem

Span = Tuple[int, int]
METRICS = ("mentions_exact", "mentions_typed", "mentions_overlap", "mention_texts", "triggers_exact", "triggers_typed",
           "event_arguments", "relationships", "facts", "temporal_expressions")


def prf(tp: int, fp: int, fn: int) -> Dict[str, Any]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def _set_counts(pred: Iterable[Any], gold: Iterable[Any]) -> Tuple[int, int, int]:
    pred, gold = set(pred), set(gold)
    return len(pred & gold), len(pred - gold), len(gold - pred)


def _span(item: Dict[str, Any]) -> Optional[Span]:
    s, e = item.get("start"), item.get("end")
    return (s, e) if isinstance(s, int) and isinstance(e, int) else None


def align(pred: Dict[str, Span], gold: Dict[str, Span]) -> Dict[str, str]:
    """pred id -> gold id, one-to-one, pairing overlapping spans largest overlap first (ties: document order)."""
    pairs = []
    for pid, (ps, pe) in pred.items():
        for gid, (gs, ge) in gold.items():
            overlap = min(pe, ge) - max(ps, gs)
            if overlap > 0:
                pairs.append((-overlap, gs, ps, pid, gid))
    out: Dict[str, str] = {}
    taken: Set[str] = set()
    for _, _, _, pid, gid in sorted(pairs):
        if pid not in out and gid not in taken:
            out[pid] = gid
            taken.add(gid)
    return out


def score_document(pred: Dict[str, Any], gold: Dict[str, Any]) -> Dict[str, Any]:
    if pred.get("text") != gold.get("text"):
        raise ValueError(f"{pred.get('story_id')!r} vs {gold.get('story_id')!r}: the documents have different texts")
    text = gold["text"]
    excluded: Dict[str, int] = {"mentions": 0, "triggers": 0, "temporal_expressions": 0}
    unanchored: Dict[str, int] = {"mentions": 0, "triggers": 0, "temporal_expressions": 0}

    def gold_spans(items: Sequence[Dict[str, Any]], id_key: str, text_key: str, kind: str) -> Dict[str, Span]:
        out = {}
        for it in items:
            if span_problem(text, it["start"], it["end"], it[text_key]):
                excluded[kind] += 1
            else:
                out[it[id_key]] = (it["start"], it["end"])
        return out

    def pred_spans(items: Sequence[Dict[str, Any]], id_key: str, kind: str) -> Dict[str, Span]:
        out = {}
        for it in items:
            sp = _span(it)
            if sp is None:
                unanchored[kind] += 1
            else:
                out[it[id_key]] = sp
        return out

    g_m = {m["mention_id"]: m for m in gold["mentions"]}
    p_m = {m["mention_id"]: m for m in pred.get("mentions", [])}
    gm_span = gold_spans(gold["mentions"], "mention_id", "text", "mentions")
    pm_span = pred_spans(pred.get("mentions", []), "mention_id", "mentions")
    m_align = align(pm_span, gm_span)
    n_pred_m = len(p_m)

    tp = len(set(pm_span.values()) & set(gm_span.values()))
    res = {"mentions_exact": prf(tp, n_pred_m - tp, len(set(gm_span.values())) - tp)}
    typed = _set_counts(((sp, p_m[i].get("type")) for i, sp in pm_span.items()),
                        ((sp, g_m[i]["type"]) for i, sp in gm_span.items()))
    res["mentions_typed"] = prf(typed[0], n_pred_m - typed[0], typed[2])
    res["mentions_overlap"] = prf(len(m_align), n_pred_m - len(m_align), len(gm_span) - len(m_align))
    res["mention_texts"] = prf(*_set_counts((m["text"] for m in p_m.values()), (g_m[i]["text"] for i in gm_span)))

    g_e = {e["event_id"]: e for e in gold["events"]}
    p_e = {e["event_id"]: e for e in pred.get("events", [])}
    ge_span = gold_spans(gold["events"], "event_id", "trigger", "triggers")
    pe_span = pred_spans(pred.get("events", []), "event_id", "triggers")
    tp = len(set(pe_span.values()) & set(ge_span.values()))
    res["triggers_exact"] = prf(tp, len(p_e) - tp, len(set(ge_span.values())) - tp)
    typed = _set_counts(((sp, p_e[i].get("type")) for i, sp in pe_span.items()),
                        ((sp, g_e[i]["type"]) for i, sp in ge_span.items()))
    res["triggers_typed"] = prf(typed[0], len(p_e) - typed[0], typed[2])

    e_align = align(pe_span, ge_span)
    gold_args = {(eid, p["role"], p["mention_id"]) for eid in ge_span for p in g_e[eid]["participants"]
                 if p["mention_id"] in gm_span}
    pred_args = [(e_align.get(eid), p["role"], m_align.get(p["mention_id"]))
                 for eid, e in p_e.items() for p in e.get("participants", [])]
    matched = {a for a in pred_args if a in gold_args}
    res["event_arguments"] = prf(len(matched), len(pred_args) - len(matched), len(gold_args) - len(matched))

    cluster_of = {mid: c["cluster_id"] for c in gold["coreference_clusters"] for mid in c["mentions"]}

    def entity(gold_mid: Optional[str]) -> Optional[str]:
        return None if gold_mid is None else cluster_of.get(gold_mid, gold_mid)

    def pred_entity(pred_mid: Any) -> Optional[str]:
        return entity(m_align.get(pred_mid))

    def unmatched_if_none(t: Tuple[Any, ...], n: int) -> Tuple[Any, ...]:
        return t if all(x is not None for x in t) else ("unmatched", n)   # never equals a gold tuple

    gold_rels = {(entity(r["subject_mention_id"]), r["predicate"], entity(r["object_mention_id"]))
                 for r in gold["relationships"]}
    pred_rels = {unmatched_if_none((pred_entity(r.get("subject_mention_id")), r.get("predicate"),
                                    pred_entity(r.get("object_mention_id"))), n)
                 for n, r in enumerate(pred.get("relationships", []))}
    res["relationships"] = prf(*_set_counts(pred_rels, gold_rels))

    def value(v: Any) -> str:
        return " ".join(str(v).split()).casefold()

    gold_facts = {(entity(f["entity_mention_id"]), f["property"], value(f["value"])) for f in gold["facts"]}
    pred_facts = {unmatched_if_none((pred_entity(f.get("entity_mention_id")), f.get("property"),
                                     value(f.get("value"))), n)
                  for n, f in enumerate(pred.get("facts", []))}
    res["facts"] = prf(*_set_counts(pred_facts, gold_facts))

    gt = gold_spans(gold["temporal_expressions"], "temporal_id", "text", "temporal_expressions")
    pt = pred_spans(pred.get("temporal_expressions", []), "temporal_id", "temporal_expressions")
    tp = len(set(pt.values()) & set(gt.values()))
    res["temporal_expressions"] = prf(tp, len(pred.get("temporal_expressions", [])) - tp, len(set(gt.values())) - tp)

    res["gold_excluded"] = excluded
    res["pred_unanchored"] = unanchored
    return res


def micro_average(per_story: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Sums tp/fp/fn over stories, then recomputes precision/recall/F1."""
    out: Dict[str, Any] = {}
    for m in METRICS:
        out[m] = prf(*(sum(s[m][k] for s in per_story) for k in ("tp", "fp", "fn")))
    for key in ("gold_excluded", "pred_unanchored"):
        out[key] = {k: sum(s[key][k] for s in per_story) for k in per_story[0][key]} if per_story else {}
    return out


def format_table(scores: Dict[str, Any]) -> str:
    rows = [f"{'metric':22s} {'P':>6s} {'R':>6s} {'F1':>6s} {'tp':>5s} {'fp':>5s} {'fn':>5s}"]
    for m in METRICS:
        s = scores[m]
        rows.append(f"{m:22s} {s['precision']:6.3f} {s['recall']:6.3f} {s['f1']:6.3f} "
                    f"{s['tp']:5d} {s['fp']:5d} {s['fn']:5d}")
    rows.append(f"gold excluded (bad spans): {scores['gold_excluded']}   "
                f"predicted without offsets: {scores['pred_unanchored']}")
    return "\n".join(rows)
