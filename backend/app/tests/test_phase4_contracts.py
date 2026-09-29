"""Phase 4: explicit pipeline data contracts, observations, span propagation, validation and normalization hooks."""
import ast
import json
import pathlib

import pytest

from app import contracts
from app.contracts import (
    ContractError, CoreferenceCluster, EntityMention, Event, ExtractionResult, ExtractorInput, FactObservation,
    FactOrigin, ObservationKind, Relationship, TemporalRelation, extract_observations, observations_from_parsed,
    validate_result,
)
from app.contracts import mapping as mapping_module
from app.models.fact import Fact
from app.pipeline import extractor as extractor_module
from app.pipeline.extractor import ExtractionError, ExtractionOrchestrator
from app.pipeline.llm_client import llm_client
from app.pipeline.parsers.extraction_parser import parse_and_validate_extraction
from app.preprocessing import chunk_document, preprocess_chapter
from app.services import consistency_service as consistency_module
from app.services import world_state_service as wss_module
from app.services.world_state_service import WorldStateService

CHAPTER = (
    "Chapter 1: Start\n\n"
    "Alice, whose eyes are blue, met Bob in Silver Haven. Bob was 30 years old. "
    "Later they left the town.\n\n"
    "Bob is the father of Carl. Carl became captain."
)

PAYLOAD = {
    "entities": [
        {"mention": "Alice", "canonical_name": "Alice", "type": "Character",
         "attributes": {"eye_color": "blue", "hair": ""}, "evidence": "Alice, whose eyes are blue"},
        {"mention": "Bob", "canonical_name": "Bob Stone", "type": "character", "attributes": {"age": "30"}},
    ],
    "relationships": [
        {"subject": "Bob", "predicate": "father_of", "object": "Carl", "certainty": "probable",
         "evidence": "Bob is the father of Carl"},
    ],
    "events": [
        {"id": "e1", "type": "meeting", "participants": ["Alice", "Bob"], "location": "Silver Haven",
         "time_expression": "noon", "evidence": "Alice met Bob"},
        {"id": "e2", "type": "departure", "participants": "Alice"},
    ],
    "state_changes": [
        {"entity": "Carl", "property": "rank", "previous_value": None, "new_value": "captain",
         "caused_by_event": "e2", "evidence": "Carl became captain"},
    ],
    "temporal_relations": [{"event_1": "e1", "relation": "before", "event_2": "e2", "evidence": "Later"}],
}


def parsed_payload(payload=PAYLOAD):
    parsed, errors = parse_and_validate_extraction(json.dumps(payload))
    assert errors == []
    return parsed


def one_chunk(text=CHAPTER, **kw):
    doc = preprocess_chapter(text)
    chunks = chunk_document(doc, **kw)
    return doc, chunks


def obs_kwargs(**over):
    base = dict(source_chunk="chunk_0000", source_span=(0, 10), sentence_ids=("s0000",))
    base.update(over)
    return base


# ============================================================================ contract creation
def test_every_contract_type_can_be_created_and_reports_its_kind():
    kw = obs_kwargs()
    made = [
        (EntityMention(text="A", canonical_name="A", **kw), ObservationKind.ENTITY),
        (Relationship(subject="A", predicate="KNOWS", object="B", **kw), ObservationKind.RELATIONSHIP),
        (Event(local_id="e1", **kw), ObservationKind.EVENT),
        (FactObservation(entity="A", property="age", value="3", **kw), ObservationKind.FACT),
        (TemporalRelation(source_event_id="e1", relation="BEFORE", target_event_id="e2", **kw), ObservationKind.TEMPORAL_RELATION),
    ]
    for obs, kind in made:
        assert obs.kind is kind
        assert obs.source_span == (0, 10) and obs.sentence_ids == ("s0000",)
        assert obs.confidence is None and obs.raw_text == ""
        assert json.loads(json.dumps(obs.to_dict()))["kind"] == kind.value


def test_observations_are_immutable():
    obs = EntityMention(text="A", canonical_name="A", **obs_kwargs())
    with pytest.raises(Exception):
        obs.mention = "B"


def test_coreference_cluster_is_an_inert_placeholder():
    m = EntityMention(text="A", canonical_name="A", **obs_kwargs())
    c = CoreferenceCluster(cluster_id="C1", mentions=("M1", "M2"))
    assert c.to_dict() == {"cluster_id": "C1", "mentions": ["M1", "M2"]}
    assert ExtractionResult().coreference_clusters == ()


def test_extraction_result_merge_and_json():
    a = EntityMention(text="A", canonical_name="A", **obs_kwargs())
    b = EntityMention(text="B", canonical_name="B", **obs_kwargs())
    merged = ExtractionResult(entity_mentions=(a,)).merge(ExtractionResult(entity_mentions=(b,)))
    assert [m.text for m in merged.entity_mentions] == ["A", "B"]
    assert json.loads(merged.to_json())["entity_mentions"][1]["text"] == "B"
    assert merged.observations() == [a, b]


# ============================================================================ validation failures
@pytest.mark.parametrize("over", [
    {"source_span": (5, 2)}, {"source_span": (-1, 3)}, {"source_span": (1,)}, {"source_span": ("a", "b")},
    {"source_span": (True, 3)}, {"sentence_ids": ()}, {"sentence_ids": ("",)}, {"source_chunk": " "},
    {"confidence": 1.5}, {"confidence": -0.1}, {"confidence": "high"},
])
def test_invalid_observation_metadata_is_rejected(over):
    with pytest.raises(ContractError):
        EntityMention(text="A", canonical_name="A", **obs_kwargs(**over))


@pytest.mark.parametrize("build", [
    lambda kw: EntityMention(text="", canonical_name="A", **kw),
    lambda kw: EntityMention(text="A", canonical_name="  ", **kw),
    lambda kw: EntityMention(text="A", canonical_name="A", attributes=[1], **kw),
    lambda kw: Relationship(subject="", predicate="P", object="B", **kw),
    lambda kw: Relationship(subject="A", predicate="", object="B", **kw),
    lambda kw: Relationship(subject="A", predicate="P", object="", **kw),
    lambda kw: Event(local_id="", **kw),
    lambda kw: FactObservation(entity="", property="p", value="v", **kw),
    lambda kw: FactObservation(entity="A", property="", value="v", **kw),
    lambda kw: FactObservation(entity="A", property="p", value=None, **kw),
    lambda kw: TemporalRelation(source_event_id="", relation="BEFORE", target_event_id="e", **kw),
    lambda kw: TemporalRelation(source_event_id="e", relation="", target_event_id="e", **kw),
])
def test_missing_required_fields_are_rejected(build):
    with pytest.raises(ContractError):
        build(obs_kwargs())


def test_document_boundary_rejects_span_beyond_chapter_and_unknown_or_outside_sentences():
    doc, [chunk] = one_chunk()
    good = EntityMention(text="A", canonical_name="A", source_chunk=chunk.id,
                         source_span=(chunk.start, chunk.end), sentence_ids=chunk.sentence_ids)
    validate_result(ExtractionResult(entity_mentions=(good,)), doc)

    beyond = EntityMention(text="A", canonical_name="A", source_chunk=chunk.id,
                           source_span=(0, len(doc.text) + 1), sentence_ids=chunk.sentence_ids)
    unknown = EntityMention(text="A", canonical_name="A", source_chunk=chunk.id,
                            source_span=(chunk.start, chunk.end), sentence_ids=("s9999",))
    last = doc.sentences[-1]
    outside = EntityMention(text="A", canonical_name="A", source_chunk=chunk.id,
                            source_span=(0, doc.sentences[0].end), sentence_ids=(last.id,))
    for bad in (beyond, unknown, outside):
        with pytest.raises(ContractError):
            validate_result(ExtractionResult(entity_mentions=(bad,)), doc)


def test_invalid_parser_output_fails_early_in_the_orchestrator(monkeypatch):
    # an item that slipped past the parser with an empty required field must fail the chapter, not pass through
    monkeypatch.setattr(llm_client, "generate", lambda **kw: "{}")
    monkeypatch.setattr(extractor_module, "parse_and_validate_extraction", lambda raw: (
        {"entities": [{"mention": "", "canonical_name": "", "type": "x", "attributes": {}, "evidence": ""}],
         "relationships": [], "events": [], "state_changes": [], "temporal_relations": []}, []))
    with pytest.raises(ExtractionError, match="contract violated"):
        ExtractionOrchestrator().extract_chapter(CHAPTER, 1)


# ============================================================================ mapping
def test_parsed_output_maps_to_typed_observations():
    doc, [chunk] = one_chunk()
    r = observations_from_parsed(chunk, parsed_payload(), chapter_number=3)
    assert r.chapter_number == 3
    assert [(m.text, m.canonical_name, m.type) for m in r.entity_mentions] == [
        ("Alice", "Alice", "character"), ("Bob", "Bob Stone", "character")]
    [rel] = r.relationships
    assert (rel.subject, rel.predicate, rel.object, rel.certainty) == ("Bob", "FATHER_OF", "Carl", "PROBABLE")
    assert rel.raw_text == "Bob is the father of Carl" and rel.confidence is None
    e1, e2 = r.events
    assert (e1.local_id, e1.type, e1.participants, e1.location, e1.time_expression) == (
        "e1", "MEETING", ("Alice", "Bob"), "Silver Haven", "noon")
    assert e2.participants == ("Alice",)
    [tr] = r.temporal_relations
    assert (tr.source_event_id, tr.relation, tr.target_event_id) == ("e1", "BEFORE", "e2")


def test_attributes_and_state_changes_become_fact_observations():
    doc, [chunk] = one_chunk()
    r = observations_from_parsed(chunk, parsed_payload())
    by_origin = {o: [f for f in r.facts if f.origin is o] for o in FactOrigin}
    attrs = {(f.entity, f.property, f.value) for f in by_origin[FactOrigin.ATTRIBUTE]}
    assert attrs == {("Alice", "eye_color", "blue"), ("Bob Stone", "age", "30")}  # empty "hair" is skipped
    [sc] = by_origin[FactOrigin.STATE_CHANGE]
    assert (sc.entity, sc.property, sc.value, sc.previous_value, sc.caused_by_event) == (
        "Carl", "rank", "captain", None, "e2")


def test_observation_kinds_cover_entity_event_relationship_and_fact():
    doc, [chunk] = one_chunk()
    kinds = {o.kind for o in observations_from_parsed(chunk, parsed_payload()).observations()}
    assert {ObservationKind.ENTITY, ObservationKind.EVENT, ObservationKind.RELATIONSHIP,
            ObservationKind.FACT} <= kinds


# ============================================================================ span propagation
def test_span_and_sentence_ids_propagate_from_chunk_to_every_observation():
    doc, chunks = one_chunk(max_chars=90, overlap_sentences=1)
    assert len(chunks) > 1
    for chunk in chunks:
        result = extract_observations(ExtractorInput(document=doc, chunk=chunk), parsed_payload())
        assert result.observations()
        for o in result.observations():
            assert o.source_chunk == chunk.id
            assert o.source_span == (chunk.start, chunk.end)
            assert o.sentence_ids == tuple(chunk.sentence_ids)
            assert doc.text[o.source_span[0]:o.source_span[1]] == chunk.text


def test_end_to_end_orchestrator_keeps_spans_in_observations_and_legacy_dicts(monkeypatch):
    monkeypatch.setattr(extractor_module, "CHUNK_MAX_CHARS", 90)
    monkeypatch.setattr(extractor_module, "CHUNK_OVERLAP_SENTENCES", 1)
    monkeypatch.setattr(llm_client, "generate", lambda **kw: json.dumps(PAYLOAD))
    out = ExtractionOrchestrator().extract_chapter(CHAPTER, 1)
    doc = preprocess_chapter(CHAPTER)
    chunk_meta = {c["id"]: c for c in out["preprocessing"]["chunks"]}
    assert len(chunk_meta) > 1

    for o in out["observations"].observations():
        meta = chunk_meta[o.source_chunk]
        assert o.source_span == (meta["start"], meta["end"])
        assert list(o.sentence_ids) == meta["sentence_ids"]
    for key in ("raw_mentions", "relationships", "events"):
        assert out[key]
        for item in out[key]:
            meta = chunk_meta[item["source_chunk"]]
            assert item["source_span"] == [meta["start"], meta["end"]]
    validate_result(out["observations"], doc)


# ============================================================================ behavior preserved
def test_extractor_output_is_unchanged_by_the_contract_layer(monkeypatch):
    monkeypatch.setattr(extractor_module, "CHUNK_MAX_CHARS", 90)
    monkeypatch.setattr(extractor_module, "CHUNK_OVERLAP_SENTENCES", 1)
    monkeypatch.setattr(llm_client, "generate", lambda **kw: json.dumps(PAYLOAD))
    out = ExtractionOrchestrator().extract_chapter(CHAPTER, 1)
    doc = preprocess_chapter(CHAPTER)
    chunks = chunk_document(doc, max_chars=90, overlap_sentences=1)

    # what the pre-Phase-4 loop produced, computed straight from the parser output
    expected = {"raw_mentions": [], "relationships": [], "events": [], "state_changes": [], "temporal_relations": []}
    for chunk in chunks:
        p = parsed_payload()
        prov = {"source_chunk": chunk.id, "source_span": [chunk.start, chunk.end]}
        expected["raw_mentions"] += [{**e, **prov} for e in p["entities"]]
        expected["relationships"] += [{**r, **prov} for r in p["relationships"]]
        expected["events"] += [{**e, **prov} for e in p["events"]]
        expected["state_changes"] += p["state_changes"]
        expected["temporal_relations"] += p["temporal_relations"]

    for key, want in expected.items():
        assert out[key] == want, key


# ============================================================================ compatibility with preprocessing
def test_contracts_work_with_every_chunk_of_a_real_chapter(monkeypatch):
    text = (pathlib.Path(__file__).resolve().parents[3] / "WSE" / "data" / "Left Right Game 1.txt")
    if not text.exists():
        pytest.skip("sample chapter not available")
    monkeypatch.setattr(llm_client, "generate", lambda **kw: json.dumps(PAYLOAD))
    monkeypatch.setattr(extractor_module, "CHUNK_MAX_CHARS", 1000)
    body = text.read_text(encoding="utf-8")
    out = ExtractionOrchestrator().extract_chapter(body, 1)
    assert len(out["preprocessing"]["chunks"]) >= 2
    validate_result(out["observations"], preprocess_chapter(body))


def test_empty_chapter_yields_an_empty_result(monkeypatch):
    monkeypatch.setattr(llm_client, "generate", lambda **kw: pytest.fail("no LLM call expected"))
    out = ExtractionOrchestrator().extract_chapter("", 1)
    assert out["observations"].observations() == [] and out["entities"] == []


# ============================================================================ normalization hooks
def test_hooks_are_pass_through():
    for fn in (contracts.normalize_property, contracts.normalize_predicate, contracts.normalize_entity_name):
        for s in ("Eye Color", "  x  ", "SON_OF", "dr. bob", ""):
            assert fn(s) == s


def test_hooks_are_applied_at_observation_creation(monkeypatch):
    monkeypatch.setattr(mapping_module, "normalize_property", lambda s: "P:" + s)
    monkeypatch.setattr(mapping_module, "normalize_predicate", lambda s: "R:" + s)
    monkeypatch.setattr(mapping_module, "normalize_entity_name", lambda s: "N:" + s)
    doc, [chunk] = one_chunk()
    r = observations_from_parsed(chunk, parsed_payload())
    assert r.entity_mentions[0].canonical_name == "N:Alice"
    assert r.relationships[0].predicate == "R:FATHER_OF" and r.relationships[0].subject == "N:Bob"
    assert {f.property for f in r.facts} == {"P:eye_color", "P:age", "P:rank"}
    assert r.events[0].participants == ("N:Alice", "N:Bob")


def test_hooks_are_applied_at_the_integration_boundary(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("H", chapters=1)
    monkeypatch.setattr(wss_module, "normalize_property", lambda s: s.replace(" ", "_").lower())
    with env.Session() as s:
        WorldStateService(s).integrate_extraction_result(
            w["world_id"],
            {"entities": [{"canonical_name": "Alice", "type": "character", "attributes": {"Eye Color": "blue"}}]},
            chapter_id=w["runs"][1]["chapter_id"], chapter_version_id=w["runs"][1]["chapter_version_id"])
        s.commit()
        assert [f.property_name for f in s.query(Fact).all()] == ["eye_color"]


def test_consistency_boundary_uses_the_hooks():
    src = pathlib.Path(consistency_module.__file__).read_text()
    assert src.count("normalize_property(fact.property_name)") == 1
    assert src.count("normalize_predicate(new_version.relationship_type)") == 1
    assert "normalize_predicate(v.relationship_type)" in src


# ============================================================================ layering
def test_contracts_package_stays_deterministic_and_db_free():
    root = pathlib.Path(contracts.__file__).parent
    banned = ("llm_client", "httpx", "requests", "openai", "spacy", "nltk", "sqlalchemy", "app.models",
              "app.repositories", "app.services", "app.pipeline")
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for m in mods:
                assert not any(m == b or m.startswith(b + ".") or b in m.split(".") for b in banned), (path.name, m)
