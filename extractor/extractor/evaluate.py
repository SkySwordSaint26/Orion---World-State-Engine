"""
Scoring on top of the backend scorer (`app.evaluation.score`), which stays the single source of the metrics it has.
Two additions:

    pronoun-aware mentions  the gold never annotates pronouns, so predicted `pronominal` mentions are counted
                            (`pronouns_predicted`) and left out of every score instead of counting as false positives
    coreference_b3          B-cubed over the clustered mentions. Predicted mentions map to gold mentions through the
                            backend's span alignment, so clusters compare as sets of gold mention ids; a mention in
                            no cluster on the other side earns nothing. Gold cluster members that are not gold
                            mentions (an annotation defect) cannot be predicted: they are left out and counted
                            (`gold_missing`).
    coreference_b3_linked   the same, on only the mentions both sides have: linking quality apart from mention
                            detection. The gold marks salient entities only, so strict B-cubed also penalizes a
                            cluster for containing real but unannotated mentions.
    event_arguments_entity  (event, role, entity) instead of the backend's (event, role, mention): the gold names a
                            participant by any mention of it ("Evelyn" for "I started"), so a participant counts when
                            its predicted cluster contains a mention of the right gold entity.
    relationships_entity    the backend's entity-level relationships, with predicted mentions mapped through their
                            clusters the same way, and both sides in canonical form: "B FRIEND_OF A" matches a gold
                            "A FRIEND_OF B", "B CHILD_OF A" matches "A PARENT_OF B".
"""
from collections import Counter
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from app.evaluation.score import align, format_table, micro_average, prf, score_document
from extractor.relations import canonical

B3_KEYS = ("p_num", "p_den", "r_num", "r_den", "gold_missing")


def _spans(items: Sequence[Dict[str, Any]], key: str = "mention_id") -> Dict[str, Tuple[int, int]]:
    """Id -> span; items without offsets (other pipelines' output) can match nothing, as in the backend scorer."""
    return {i[key]: (i["start"], i["end"]) for i in items
            if isinstance(i.get("start"), int) and isinstance(i.get("end"), int)}


def _b3(counts: Dict[str, float]) -> Dict[str, float]:
    p = counts["p_num"] / counts["p_den"] if counts["p_den"] else 0.0
    r = counts["r_num"] / counts["r_den"] if counts["r_den"] else 0.0
    return {**counts, "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def _side(a: Sequence[FrozenSet[str]], b: Sequence[FrozenSet[str]]) -> Tuple[float, int]:
    """B-cubed in entity-overlap form: sum of |A ∩ B|² / |A| over cluster pairs, and the number of mentions in `a`."""
    return sum(len(x & y) ** 2 / len(x) for x in a for y in b), sum(len(x) for x in a)


def coreference_b3(pred: Dict[str, Any], gold: Dict[str, Any], linked_only: bool = False) -> Dict[str, float]:
    to_gold = align(_spans(pred["mentions"]), _spans(gold["mentions"]))
    present = set(to_gold) if linked_only else {m["mention_id"] for m in pred["mentions"]}
    gold_ids = {m["mention_id"] for m in gold["mentions"]}
    key = [k for c in gold["coreference_clusters"] if len(k := frozenset(c["mentions"]) & gold_ids) >= 2]
    missing = sum(m not in gold_ids for c in gold["coreference_clusters"] for m in c["mentions"])
    response: List[FrozenSet[str]] = []
    for c in pred["coreference_clusters"]:
        ids = frozenset(to_gold.get(m, f"pred:{m}") for m in c["mentions"] if m in present)
        if len(ids) >= 2:
            response.append(ids)
    r_num, r_den = _side(key, response)
    p_num, p_den = _side(response, key)
    return _b3({"p_num": p_num, "p_den": p_den, "r_num": r_num, "r_den": r_den, "gold_missing": missing})


def entity_maps(pred: Dict[str, Any], scored: Dict[str, Any], gold: Dict[str, Any]):
    """(gold mention -> gold entity, predicted mention -> gold entity or None). A gold entity is its coreference cluster
    (or the mention itself); a predicted mention maps through its cluster to the gold entity most of its aligned
    members belong to. `scored` is `pred` without pronoun mentions: alignment uses it, cluster lookups use `pred`."""
    m_align = align(_spans(scored["mentions"]), _spans(gold["mentions"]))
    gold_entity = {m: c["cluster_id"] for c in gold["coreference_clusters"] for m in c["mentions"]}
    entity = lambda gm: gold_entity.get(gm, gm)
    pred_cluster = {m: c["mentions"] for c in pred["coreference_clusters"] for m in c["mentions"]}

    def pred_entity(pm: str) -> Any:
        votes = Counter(entity(m_align[m]) for m in pred_cluster.get(pm, [pm]) if m in m_align)
        return votes.most_common(1)[0][0] if votes else None

    return entity, pred_entity


def event_arguments_entity(pred: Dict[str, Any], scored: Dict[str, Any], gold: Dict[str, Any]) -> Dict[str, Any]:
    entity, pred_entity = entity_maps(pred, scored, gold)
    e_align = align(_spans(pred["events"], "event_id"), _spans(gold["events"], "event_id"))
    gold_args = {(e["event_id"], p["role"], entity(p["mention_id"])) for e in gold["events"] for p in e["participants"]}
    pred_args = [(e_align.get(e["event_id"]), p["role"], pred_entity(p["mention_id"]))
                 for e in pred["events"] for p in e["participants"]]
    tp = len({a for a in pred_args if a in gold_args})
    return prf(tp, len(pred_args) - tp, len(gold_args) - tp)


def relationships_entity(pred: Dict[str, Any], scored: Dict[str, Any], gold: Dict[str, Any]) -> Dict[str, Any]:
    entity, pred_entity = entity_maps(pred, scored, gold)
    gold_rels = {canonical(entity(r["subject_mention_id"]), r["predicate"], entity(r["object_mention_id"]))
                 for r in gold["relationships"]}
    pred_rels = set()
    for n, r in enumerate(pred["relationships"]):
        s, o = pred_entity(r.get("subject_mention_id")), pred_entity(r.get("object_mention_id"))
        pred_rels.add(canonical(s, r["predicate"], o) if s is not None and o is not None else ("unmatched", n))
    tp = len(pred_rels & gold_rels)
    return prf(tp, len(pred_rels) - tp, len(gold_rels) - tp)


def corrected(gold: Dict[str, Any], fix: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The gold with data/gold_corrections.json applied: its facts and relationships replace the converted ones, and
    `merge` joins the clusters of mentions that are one entity. Entities are named by a gold mention's text."""
    if not fix:
        return gold
    story = gold["story_id"]

    def mention(name: str) -> str:
        found = [m["mention_id"] for m in gold["mentions"] if m["text"].casefold() == name.casefold()]
        if not found:
            raise ValueError(f"{story}: gold_corrections names {name!r}, which is not the text of a gold mention")
        return found[0]

    for item in fix["facts"] + fix["relationships"]:
        if item["evidence"] not in gold["text"]:
            raise ValueError(f"{story}: evidence not in the text: {item['evidence']!r}")
    clusters = [dict(c) for c in gold["coreference_clusters"]]
    for names in fix.get("merge", []):
        ids = {mention(n) for n in names}
        group = [c for c in clusters if ids & set(c["mentions"])]
        group[0]["mentions"] = sorted({m for c in group for m in c["mentions"]} | ids)
        clusters = [c for c in clusters if c not in group[1:]]
    facts = [{"fact_id": f"F{n}", "property": f["property"], "entity_mention_id": mention(f["entity"]),
              "value": f["value"]} for n, f in enumerate(fix["facts"], 1)]
    rels = [{"relationship_id": f"R{n}", "predicate": r["predicate"], "subject_mention_id": mention(r["subject"]),
             "object_mention_id": mention(r["object"])} for n, r in enumerate(fix["relationships"], 1)]
    return {**gold, "coreference_clusters": clusters, "facts": facts, "relationships": rels}


def score(pred: Dict[str, Any], gold: Dict[str, Any]) -> Dict[str, Any]:
    scored = {**pred, "mentions": [m for m in pred["mentions"] if m.get("mention_kind") != "pronominal"]}
    res = score_document(scored, gold)
    res["coreference_b3"] = coreference_b3(scored, gold)
    res["coreference_b3_linked"] = coreference_b3(scored, gold, linked_only=True)
    res["event_arguments_entity"] = event_arguments_entity(pred, scored, gold)
    res["relationships_entity"] = relationships_entity(pred, scored, gold)
    res["pronouns_predicted"] = len(pred["mentions"]) - len(scored["mentions"])
    return res


def micro(per_story: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    out = micro_average(per_story)
    for key in ("coreference_b3", "coreference_b3_linked"):
        out[key] = _b3({k: sum(s[key][k] for s in per_story) for k in B3_KEYS})
    for key in ("event_arguments_entity", "relationships_entity"):
        out[key] = prf(*(sum(s[key][k] for s in per_story) for k in ("tp", "fp", "fn")))
    out["pronouns_predicted"] = sum(s["pronouns_predicted"] for s in per_story)
    return out


def table(scores: Dict[str, Any]) -> str:
    row = lambda key: (f"{key:22s} {scores[key]['precision']:6.3f} {scores[key]['recall']:6.3f} "
                      f"{scores[key]['f1']:6.3f}")
    return (f"{format_table(scores)}\n{row('coreference_b3')}   (gold cluster members without a mention, left out: "
            f"{scores['coreference_b3']['gold_missing']})\n{row('coreference_b3_linked')}\n"
            f"{row('event_arguments_entity')}\n{row('relationships_entity')}\n"
            f"pronoun mentions predicted (not scored): {scores['pronouns_predicted']}")
