"""
Gold-schema alignment (Phase 4.5): vocabularies and a projection of an `ExtractionResult` onto
`orion_gold_v1.schema.json`.

The projection is an ADAPTER: it never changes the observations and never repairs values. It assigns gold ids,
resolves name references to mention ids by EXACT string match (no coreference, no normalization), and reports
everything the schema requires but the current extractor cannot supply, or that is outside a gold enum, as
`GoldProjection.issues`. A document with no issues is schema-complete; today's extractor output is not
(mention offsets, event triggers and participant mentions are not extracted yet).

The enum constants below are copies of the schema's enums; a test compares them with the schema file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.contracts.models import ExtractionResult

GOLD_SCHEMA_VERSION = "1.0"
MENTION_TYPES = ("character", "location", "object", "organization", "other")
MENTION_KINDS = ("proper", "nominal", "pronominal")
EVENT_TYPES = ("ARRIVAL", "DEPARTURE", "TRAVEL", "MEETING", "CONVERSATION", "DISCOVERY", "ATTACK", "DEATH",
               "CONFLICT", "CREATION", "DESTRUCTION", "OTHER")
PARTICIPANT_ROLES = ("agent", "patient", "target", "recipient", "location", "instrument", "participant")
PREDICATES = ("FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "PARENT_OF", "CHILD_OF", "MARRIED_TO", "ALLY_OF",
              "WORKS_FOR", "MEMBER_OF", "OWNS", "KNOWS", "RELATED_TO")
FACT_PROPERTIES = ("birth_place", "date_of_birth", "origin", "eye_color", "hair_color", "species", "age",
                   "occupation", "title", "status", "location")
TEMPORAL_EXPRESSION_TYPES = ("absolute_time", "relative_time", "duration", "sequence_marker", "other")
TEMPORAL_RELATIONS = ("BEFORE", "AFTER", "DURING")

_SCALARS = (str, int, float, bool, type(None))


@dataclass(frozen=True)
class GoldProjection:
    document: Dict[str, Any]
    issues: Tuple[str, ...]

    @property
    def is_schema_complete(self) -> bool:
        return not self.issues


def project_to_gold(
    result: ExtractionResult, *, story_id: str, text: str, title: Optional[str] = None
) -> GoldProjection:
    """Project `result` onto the gold document shape. Items lacking required gold data are still emitted with
    what they have and reported in `issues`, so the document is schema-valid only when `issues` is empty."""
    issues: List[str] = []

    def ids(items, prefix):  # keep an assigned id, otherwise number sequentially without colliding
        used = {o.id for o in items if o.id}
        out, n = [], 0
        for o in items:
            if o.id:
                out.append(o.id)
                continue
            n += 1
            while f"{prefix}{n}" in used:
                n += 1
            out.append(f"{prefix}{n}")
        return out

    mentions = list(result.entity_mentions)
    mention_ids = ids(mentions, "M")

    def find_mention(name: str, chunk: str) -> Optional[str]:
        """Exact-name lookup (surface text or canonical name), preferring the same chunk. Not coreference."""
        hits = [(m.source_chunk != chunk, i) for i, m in enumerate(mentions) if name in (m.text, m.canonical_name)]
        return mention_ids[min(hits)[1]] if hits else None

    out_mentions = []
    for mid, m in zip(mention_ids, mentions):
        d: Dict[str, Any] = {"mention_id": mid, "text": m.text, "type": m.type}
        if m.type not in MENTION_TYPES:
            issues.append(f"{mid}: type {m.type!r} is not a gold mention type")
        if m.mention_kind is not None:
            d["mention_kind"] = m.mention_kind
        if m.start is None:
            issues.append(f"{mid}: no start/end (mention offsets are not populated)")
        else:
            d["start"], d["end"] = m.start, m.end
        out_mentions.append(d)

    events = list(result.events)
    event_ids = ids(events, "E")
    label_to_event: Dict[str, Optional[str]] = {}
    for eid, e in zip(event_ids, events):
        # a reference may be the extractor-local label or an already-assigned gold id. The same label in several
        # chunks is ambiguous (temporal-normalization TODO): refuse to guess.
        for ref in {e.local_id, eid}:
            label_to_event[ref] = None if ref in label_to_event and label_to_event[ref] != eid else eid
    out_events = []
    for eid, e in zip(event_ids, events):
        parts = [p.to_dict() for p in e.participant_refs]
        if not parts:
            for name in e.participants:
                mid = find_mention(name, e.source_chunk)
                if mid is None:
                    issues.append(f"{eid}: participant {name!r} has no mention")
                else:
                    parts.append({"role": "participant", "mention_id": mid})
        d = {"event_id": eid, "type": e.type, "participants": parts}
        if e.type not in EVENT_TYPES:
            issues.append(f"{eid}: type {e.type!r} is not a gold event type")
        if e.trigger is None or e.start is None:
            issues.append(f"{eid}: no trigger/start/end (not populated)")
        else:
            d.update(trigger=e.trigger, start=e.start, end=e.end)
        out_events.append(d)

    rels = list(result.relationships)
    out_rels = []
    for rid, r in zip(ids(rels, "R"), rels):
        s_id = r.subject_mention_id or find_mention(r.subject, r.source_chunk)
        o_id = r.object_mention_id or find_mention(r.object, r.source_chunk)
        if s_id is None or o_id is None:
            issues.append(f"{rid}: subject/object {r.subject!r}/{r.object!r} has no mention")
        if r.predicate not in PREDICATES:
            issues.append(f"{rid}: predicate {r.predicate!r} is not a gold predicate")
        d = {"relationship_id": rid, "predicate": r.predicate}
        if s_id:
            d["subject_mention_id"] = s_id
        if o_id:
            d["object_mention_id"] = o_id
        out_rels.append(d)

    facts = list(result.facts)
    out_facts = []
    for fid, f in zip(ids(facts, "F"), facts):
        e_id = f.entity_mention_id or find_mention(f.entity, f.source_chunk)
        if e_id is None:
            issues.append(f"{fid}: entity {f.entity!r} has no mention")
        if f.property not in FACT_PROPERTIES:
            issues.append(f"{fid}: property {f.property!r} is not a gold property")
        if not isinstance(f.value, _SCALARS):
            issues.append(f"{fid}: value of type {type(f.value).__name__} is not a gold scalar")
        d = {"fact_id": fid, "property": f.property, "value": f.value}
        if e_id:
            d["entity_mention_id"] = e_id
        out_facts.append(d)

    exprs = list(result.temporal_expressions)
    out_exprs = []
    for tid, t in zip(ids(exprs, "T"), exprs):
        d = {"temporal_id": tid, "text": t.text, "type": t.type}
        if t.type not in TEMPORAL_EXPRESSION_TYPES:
            issues.append(f"{tid}: type {t.type!r} is not a gold temporal expression type")
        if t.start is None:
            issues.append(f"{tid}: no start/end (not populated)")
        else:
            d["start"], d["end"] = t.start, t.end
        out_exprs.append(d)

    trs = list(result.temporal_relations)
    out_trs = []
    for trid, t in zip(ids(trs, "TR"), trs):
        src, dst = label_to_event.get(t.source_event_id), label_to_event.get(t.target_event_id)
        if src is None or dst is None:
            issues.append(f"{trid}: event {t.source_event_id!r}/{t.target_event_id!r} is unknown or ambiguous")
        if t.relation not in TEMPORAL_RELATIONS:
            issues.append(f"{trid}: relation {t.relation!r} is not a gold temporal relation")
        d = {"temporal_relation_id": trid, "relation": t.relation}
        if src:
            d["source_event_id"] = src
        if dst:
            d["target_event_id"] = dst
        out_trs.append(d)

    document: Dict[str, Any] = {
        "schema_version": GOLD_SCHEMA_VERSION, "story_id": story_id, "text": text,
        "mentions": out_mentions,
        "coreference_clusters": [c.to_gold_dict() for c in result.coreference_clusters],
        "events": out_events, "relationships": out_rels, "facts": out_facts,
        "temporal_expressions": out_exprs, "temporal_relations": out_trs,
    }
    if title is not None:
        document["title"] = title
    return GoldProjection(document, tuple(issues))
