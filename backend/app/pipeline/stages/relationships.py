"""Stage 2 - relationship extraction (Phase 7). Input: chunk sentences + stage-1 mentions. Output: Relationship[]."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.contracts import EntityMention, Relationship
from app.contracts.gold import PREDICATES
from app.pipeline.stages.common import (
    CERTAINTIES, STRING, Errors, Generate, array, call_stage, choice_field, enum, ground_item, item_cap, label_map,
    list_field, load_stage_prompt, mention_groups, obj, parse_object, pick_mention, render_mentions,
    render_sentences, sentences_of, text_field,
)
from app.pipeline.stages.grounding import GroundingLog

STAGE = "relationships"


def build_relationships(
    payload: Dict[str, Any], chunk: Any, document: Any, mentions: Sequence[EntityMention],
    grounding: Optional[GroundingLog] = None
) -> List[Relationship]:
    err = Errors(STAGE, chunk.id)
    sents, _, new_ids = sentences_of(chunk, document)
    labels = label_map(mentions)
    out: List[Relationship] = []
    items = list_field(payload, "relationships", err, cap=item_cap(chunk))
    for i, item in enumerate(items):
        path = f"$.relationships[{i}]"
        if not isinstance(item, dict):
            err.add(path, "must be an object")
            continue
        refs = {}
        for role in ("subject", "object"):
            label = text_field(item, role, err, path)
            if label is not None and label not in labels:
                err.add(f"{path}.{role}", f"{label!r} is not a mention label of this chunk ({', '.join(labels) or 'none'})")
                label = None
            refs[role] = labels.get(label) if label else None
        predicate = choice_field(item, "predicate", PREDICATES, err, path)
        prov = ground_item(item, chunk, sents, new_ids, err, path, grounding)
        certainty = choice_field(item, "certainty", CERTAINTIES, err, path, required=False) or "DEFINITE"
        subj_group, obj_group = refs["subject"], refs["object"]
        if subj_group is not None and subj_group is obj_group:
            err.add(path, "subject and object are the same mention")
        if err.failed(path) or predicate is None or prov is None or subj_group is None or obj_group is None:
            continue
        subj, target = pick_mention(subj_group, prov), pick_mention(obj_group, prov)
        out.append(Relationship(
            subject=subj.text, object=target.text, predicate=predicate, certainty=certainty,
            subject_mention_id=subj.id, object_mention_id=target.id, raw_text=item["evidence"],
            source_chunk=chunk.id, source_span=prov.source_span, sentence_ids=prov.sentence_ids))
    err.finish(len(items), grounding)                   # items with violations were never added to `out`
    return out


def extract_relationships(
    chunk: Any, document: Any, mentions: Sequence[EntityMention], generate: Optional[Generate] = None,
    grounding: Optional[GroundingLog] = None
) -> List[Relationship]:
    if len(mention_groups(mentions)) < 2:
        return []                                       # a relationship needs two mentions: nothing to ask the LLM
    sents, _, new_ids = sentences_of(chunk, document)
    user = (f"CHUNK {chunk.id}\nSENTENCES:\n{render_sentences(sents, new_ids)}\n\n"
            f"MENTIONS (label | text | type):\n{render_mentions(mentions)}\n\nReturn the JSON object now.")
    label = enum(list(label_map(mentions)))
    schema = obj(relationships=array(obj(
        evidence=STRING, subject=label, predicate=enum(PREDICATES), object=label, certainty=enum(CERTAINTIES)),
        item_cap(chunk)))
    raw = call_stage(generate, load_stage_prompt("stage2_relationships.txt"), user, schema)
    return build_relationships(parse_object(raw, STAGE, chunk.id), chunk, document, mentions, grounding)
