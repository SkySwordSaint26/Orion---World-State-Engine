"""
Mapping between the parser's dict output and the Phase 4 contracts, plus boundary validation.

`observations_from_parsed` wraps ONE chunk's parsed extraction (unchanged prompt, unchanged parser) into
typed observations carrying the chunk's span and sentence ids. `legacy_*` turn observations back into the
exact dicts the extractor produced before Phase 4, so downstream integration is unaffected.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from app.contracts.models import (
    ContractError, EntityMention, Event, ExtractionResult, ExtractorInput, FactObservation, FactOrigin,
    Observation, Relationship, TemporalRelation,
)
from app.contracts.normalization import normalize_entity_name, normalize_predicate, normalize_property


def _chunk_provenance(chunk: Any) -> Dict[str, Any]:
    return {"source_chunk": chunk.id, "source_span": (chunk.start, chunk.end), "sentence_ids": tuple(chunk.sentence_ids)}


def observations_from_parsed(chunk: Any, parsed: Mapping[str, Any], chapter_number: int = 1) -> ExtractionResult:
    """Wrap one chunk's `parse_and_validate_extraction` output. Invalid items raise `ContractError`."""
    prov = _chunk_provenance(chunk)

    mentions: List[EntityMention] = []
    facts: List[FactObservation] = []
    for ent in parsed.get("entities", []):
        name = normalize_entity_name(ent["canonical_name"])
        evidence = ent.get("evidence", "")
        attributes = ent.get("attributes") or {}
        mentions.append(EntityMention(
            text=normalize_entity_name(ent["mention"]), canonical_name=name,
            type=ent.get("type", "unknown"), attributes=attributes, raw_text=evidence, **prov))
        for prop, value in attributes.items():  # same skip rule as WorldStateService
            if value is None or value == "":
                continue
            facts.append(FactObservation(
                entity=name, property=normalize_property(prop), value=value,
                origin=FactOrigin.ATTRIBUTE, raw_text=evidence, **prov))

    relationships = [
        Relationship(
            subject=normalize_entity_name(r["subject"]), predicate=normalize_predicate(r["predicate"]),
            object=normalize_entity_name(r["object"]), certainty=r.get("certainty", "DEFINITE"),
            raw_text=r.get("evidence", ""), **prov)
        for r in parsed.get("relationships", [])
    ]
    events = [
        Event(
            local_id=e["id"], type=e.get("type", "EVENT"),
            participants=tuple(normalize_entity_name(p) for p in e.get("participants", [])),
            location=e.get("location"), time_expression=e.get("time_expression"),
            raw_text=e.get("evidence", ""), **prov)
        for e in parsed.get("events", [])
    ]
    for sc in parsed.get("state_changes", []):
        facts.append(FactObservation(
            entity=normalize_entity_name(sc["entity"]), property=normalize_property(sc["property"]),
            value=sc["new_value"], previous_value=sc.get("previous_value"),
            caused_by_event=sc.get("caused_by_event"), origin=FactOrigin.STATE_CHANGE,
            raw_text=sc.get("evidence", ""), **prov))
    temporal = [
        TemporalRelation(source_event_id=t["event_1"], relation=t["relation"], target_event_id=t["event_2"],
                         raw_text=t.get("evidence", ""), **prov)
        for t in parsed.get("temporal_relations", [])
    ]
    return ExtractionResult(
        chapter_number=chapter_number, entity_mentions=tuple(mentions), relationships=tuple(relationships),
        events=tuple(events), facts=tuple(facts), temporal_relations=tuple(temporal))


def extract_observations(inp: ExtractorInput, parsed: Mapping[str, Any]) -> ExtractionResult:
    """Stage contract entry point: (ExtractorInput, parsed LLM output) -> validated ExtractionResult."""
    result = observations_from_parsed(inp.chunk, parsed, inp.chapter_number)
    validate_result(result, inp.document)
    return result


# --------------------------------------------------------------------------- validation
def validate_observation(obs: Observation, document: Any, _index: Any = None) -> None:
    """Document-dependent checks: span inside the chapter, sentence ids exist and lie inside the span."""
    index = _index if _index is not None else {s.id: s for s in document.iter_sentences()}
    owner = f"{type(obs).__name__}({obs.source_chunk})"
    start, end = obs.source_span
    if end > len(document.text):
        raise ContractError(f"{owner}: source_span {obs.source_span} exceeds chapter length {len(document.text)}")
    for sid in obs.sentence_ids:
        sentence = index.get(sid)
        if sentence is None:
            raise ContractError(f"{owner}: unknown sentence id {sid!r}")
        if sentence.start < start or sentence.end > end:
            raise ContractError(
                f"{owner}: sentence {sid} [{sentence.start}, {sentence.end}) lies outside source_span {obs.source_span}")


def validate_result(result: ExtractionResult, document: Any) -> None:
    index = {s.id: s for s in document.iter_sentences()}
    for obs in result.observations():
        validate_observation(obs, document, index)


# --------------------------------------------------------------------------- back to the legacy dicts
def _prov(o: Observation) -> Dict[str, Any]:
    return {"source_chunk": o.source_chunk, "source_span": list(o.source_span)}


def legacy_entities(result: ExtractionResult) -> List[Dict[str, Any]]:
    return [{"mention": m.text, "canonical_name": m.canonical_name, "type": m.type,
             "attributes": dict(m.attributes), "evidence": m.raw_text, **_prov(m)} for m in result.entity_mentions]


def legacy_relationships(result: ExtractionResult) -> List[Dict[str, Any]]:
    return [{"subject": r.subject, "predicate": r.predicate, "object": r.object, "certainty": r.certainty,
             "evidence": r.raw_text, **_prov(r)} for r in result.relationships]


def legacy_events(result: ExtractionResult) -> List[Dict[str, Any]]:
    return [{"id": e.local_id, "type": e.type, "participants": list(e.participants), "location": e.location,
             "time_expression": e.time_expression, "evidence": e.raw_text, **_prov(e)} for e in result.events]


def legacy_state_changes(result: ExtractionResult) -> List[Dict[str, Any]]:
    return [{"entity": f.entity, "property": f.property, "previous_value": f.previous_value, "new_value": f.value,
             "caused_by_event": f.caused_by_event, "evidence": f.raw_text}
            for f in result.facts if f.origin is FactOrigin.STATE_CHANGE]


def legacy_temporal_relations(result: ExtractionResult) -> List[Dict[str, Any]]:
    return [{"event_1": t.source_event_id, "relation": t.relation, "event_2": t.target_event_id, "evidence": t.raw_text}
            for t in result.temporal_relations]
