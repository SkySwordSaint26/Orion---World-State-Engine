"""Stage 4 - fact / attribute extraction (Phase 7). Input: chunk sentences + mentions. Output: FactObservation[]."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.contracts import EntityMention, FactObservation, FactOrigin
from app.contracts.gold import FACT_PROPERTIES
from app.pipeline.stages.common import (
    STRING, Errors, Generate, array, call_stage, choice_field, enum, ground_item, item_cap, label_map, list_field,
    load_stage_prompt, obj, parse_object, pick_mention, render_mentions, render_sentences, sentences_of, text_field,
)
from app.pipeline.stages.grounding import GroundingLog

STAGE = "facts"
KINDS = {"attribute": FactOrigin.ATTRIBUTE, "state_change": FactOrigin.STATE_CHANGE}


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and not (isinstance(value, str) and not value.strip())


def build_facts(
    payload: Dict[str, Any], chunk: Any, document: Any, mentions: Sequence[EntityMention],
    grounding: Optional[GroundingLog] = None
) -> List[FactObservation]:
    err = Errors(STAGE, chunk.id)
    sents, _, new_ids = sentences_of(chunk, document)
    labels = label_map(mentions)
    out: List[FactObservation] = []
    items = list_field(payload, "facts", err, cap=item_cap(chunk))
    for i, item in enumerate(items):
        path = f"$.facts[{i}]"
        if not isinstance(item, dict):
            err.add(path, "must be an object")
            continue
        label = text_field(item, "entity", err, path)
        if label is not None and label not in labels:
            err.add(f"{path}.entity", f"{label!r} is not a mention label of this chunk ({', '.join(labels) or 'none'})")
            label = None
        prop = choice_field(item, "property", FACT_PROPERTIES, err, path)
        value = item.get("value")
        if not _scalar(value):
            err.add(f"{path}.value", "is required and must be a non-empty string, number or boolean")
        kind = choice_field(item, "kind", tuple(KINDS), err, path, required=False) or "attribute"
        previous = item.get("previous_value")
        if previous is not None and not _scalar(previous):
            err.add(f"{path}.previous_value", "must be a string, number, boolean or null")
        if previous is not None and kind == "attribute":
            err.add(f"{path}.previous_value", "is only allowed for kind 'state_change'")
        prov = ground_item(item, chunk, sents, new_ids, err, path, grounding)
        if err.failed(path) or label is None or prop is None or prov is None:
            continue
        m = pick_mention(labels[label], prov)
        out.append(FactObservation(
            entity=m.text, entity_mention_id=m.id, property=prop, value=value, previous_value=previous,
            origin=KINDS[kind], raw_text=item["evidence"], source_chunk=chunk.id,
            source_span=prov.source_span, sentence_ids=prov.sentence_ids))
    err.finish(len(items), grounding)                   # items with violations were never added to `out`
    return out


def extract_facts(
    chunk: Any, document: Any, mentions: Sequence[EntityMention], generate: Optional[Generate] = None,
    grounding: Optional[GroundingLog] = None
) -> List[FactObservation]:
    if not mentions:
        return []                                       # facts are about mentions: nothing to ask the LLM
    sents, _, new_ids = sentences_of(chunk, document)
    user = (f"CHUNK {chunk.id}\nSENTENCES:\n{render_sentences(sents, new_ids)}\n\n"
            f"MENTIONS (label | text | type):\n{render_mentions(mentions)}\n\nReturn the JSON object now.")
    schema = obj(facts=array(obj(
        evidence=STRING, entity=enum(list(label_map(mentions))), property=enum(FACT_PROPERTIES), value=STRING,
        kind=enum(tuple(KINDS)), previous_value={"type": ["string", "null"]}), item_cap(chunk)))
    raw = call_stage(generate, load_stage_prompt("stage4_facts.txt"), user, schema)
    return build_facts(parse_object(raw, STAGE, chunk.id), chunk, document, mentions, grounding)
