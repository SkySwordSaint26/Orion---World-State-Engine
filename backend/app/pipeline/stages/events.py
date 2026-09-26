"""Stage 3 - event extraction (Phase 7). Input: chunk sentences + mentions. Output: Event[] (+ temporal relations)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.contracts import EntityMention, Event, EventParticipant, TemporalRelation
from app.contracts.gold import EVENT_TYPES, PARTICIPANT_ROLES, TEMPORAL_RELATIONS
from app.pipeline.stages.common import (
    STRING, Errors, Generate, IdCounters, array, call_stage, choice_field, enum, ground_item, in_evidence, item_cap,
    label_map, list_field, load_stage_prompt, obj, offsets_in, parse_object, pick_mention, render_mentions,
    render_sentences, sentences_of, text_field,
)
from app.pipeline.stages.grounding import GroundingLog

STAGE = "events"


def build_events(
    payload: Dict[str, Any], chunk: Any, document: Any, mentions: Sequence[EntityMention], ids: IdCounters,
    grounding: Optional[GroundingLog] = None
) -> Tuple[List[Event], List[TemporalRelation]]:
    err = Errors(STAGE, chunk.id)
    sents, _, new_ids = sentences_of(chunk, document)
    labels = label_map(mentions)
    staged = []
    event_ids = set()
    items = list_field(payload, "events", err, cap=item_cap(chunk))
    for i, item in enumerate(items):
        path = f"$.events[{i}]"
        if not isinstance(item, dict):
            err.add(path, "must be an object")
            continue
        eid = text_field(item, "id", err, path)
        if eid is not None:
            if eid in event_ids:
                err.add(f"{path}.id", f"duplicate event id {eid!r}")
            event_ids.add(eid)
        etype = choice_field(item, "type", EVENT_TYPES, err, path)
        trigger = text_field(item, "trigger", err, path)
        prov = ground_item(item, chunk, sents, new_ids, err, path, grounding)
        in_evidence(trigger, item, err, path, "trigger")
        refs: List[Tuple[str, List[EntityMention]]] = []   # (role, occurrences of the referenced name)
        parts = item.get("participants", [])
        if not isinstance(parts, list):
            err.add(f"{path}.participants", "must be a list")
            parts = []
        for j, part in enumerate(parts):
            ppath = f"{path}.participants[{j}]"
            if not isinstance(part, dict):
                err.add(ppath, "must be an object with 'mention' and 'role'")
                continue
            label = text_field(part, "mention", err, ppath)
            role = choice_field(part, "role", PARTICIPANT_ROLES, err, ppath)
            if label is not None and label not in labels:
                err.add(f"{ppath}.mention", f"{label!r} is not a mention label of this chunk ({', '.join(labels) or 'none'})")
            elif label is not None and role is not None:
                refs.append((role, labels[label]))
        if eid and etype and trigger and prov is not None:
            staged.append((path, eid, etype, trigger, prov, refs, item["evidence"]))
    # ids of events without violations; a temporal relation to any other event would dangle once it is dropped
    valid_ids = {eid for path, eid, *_ in staged if not err.failed(path)}

    relations = []
    rel_items = list_field(payload, "temporal_relations", err, required=False, cap=item_cap(chunk))
    for i, item in enumerate(rel_items):
        path = f"$.temporal_relations[{i}]"
        if not isinstance(item, dict):
            err.add(path, "must be an object")
            continue
        src, dst = text_field(item, "source", err, path), text_field(item, "target", err, path)
        rel = choice_field(item, "relation", TEMPORAL_RELATIONS, err, path)
        for key, val in (("source", src), ("target", dst)):
            if val is not None and val not in event_ids:
                err.add(f"{path}.{key}", f"{val!r} is not an event id of this stage")
            elif val is not None and val not in valid_ids:
                err.add(f"{path}.{key}", f"{val!r} refers to an invalid event")
        if src and src == dst:
            err.add(path, "source and target are the same event")
        if src in event_ids and dst in event_ids and rel:
            relations.append((path, src, rel, dst))
    dropped = err.finish(len(items) + len(rel_items), grounding)

    events: List[Event] = []
    for path, eid, etype, trigger, prov, refs, evidence in staged:
        if path in dropped:
            continue
        start, end = offsets_in(prov.sentence, trigger)   # exact offsets only when the sentence is known and unique
        refs = [(role, pick_mention(group, prov)) for role, group in refs]
        location = next((m.text for role, m in refs if role == "location"), None)
        events.append(Event(
            id=ids.event(), local_id=f"{chunk.id}:{eid}", type=etype, trigger=trigger, start=start, end=end,
            participants=tuple(m.text for role, m in refs if role != "location"),
            participant_refs=tuple(EventParticipant(role=role, mention_id=m.id) for role, m in refs),
            location=location, raw_text=evidence, source_chunk=chunk.id,
            source_span=prov.source_span, sentence_ids=prov.sentence_ids))
    temporal = [TemporalRelation(
        source_event_id=f"{chunk.id}:{s}", relation=r, target_event_id=f"{chunk.id}:{d}",
        source_chunk=chunk.id, source_span=(chunk.start, chunk.end), sentence_ids=tuple(chunk.sentence_ids))
        for path, s, r, d in relations if path not in dropped]
    return events, temporal


def extract_events(
    chunk: Any, document: Any, mentions: Sequence[EntityMention], ids: IdCounters,
    generate: Optional[Generate] = None, grounding: Optional[GroundingLog] = None
) -> Tuple[List[Event], List[TemporalRelation]]:
    if not mentions:
        return [], []                                   # an event needs a mention as participant: nothing to ask
    sents, _, new_ids = sentences_of(chunk, document)
    user = (f"CHUNK {chunk.id}\nSENTENCES:\n{render_sentences(sents, new_ids)}\n\n"
            f"MENTIONS (label | text | type):\n{render_mentions(mentions)}\n\nReturn the JSON object now.")
    cap = item_cap(chunk)
    schema = obj(
        events=array(obj(
            id=STRING, evidence=STRING, trigger=STRING, type=enum(EVENT_TYPES),
            participants=array(obj(mention=enum(list(label_map(mentions))), role=enum(PARTICIPANT_ROLES)), 6)), cap),
        temporal_relations=array(obj(source=STRING, relation=enum(TEMPORAL_RELATIONS), target=STRING), cap))
    raw = call_stage(generate, load_stage_prompt("stage3_events.txt"), user, schema)
    return build_events(parse_object(raw, STAGE, chunk.id), chunk, document, mentions, ids, grounding)
