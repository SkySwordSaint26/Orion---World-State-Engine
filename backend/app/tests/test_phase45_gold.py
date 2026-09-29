"""Phase 4.5: contracts aligned with orion_gold_v1.schema.json, projection adapter, legacy output unchanged."""
import json

import pytest

from app.contracts import (
    ContractError, CoreferenceCluster, EntityMention, Event, EventParticipant, ExtractionResult, FactObservation,
    Relationship, TemporalExpression, TemporalRelation, observations_from_parsed, project_to_gold,
)
from app.contracts import gold
from app.evaluation.schema import SCHEMA_PATH, load_schema, schema_errors
from app.pipeline import extractor as extractor_module
from app.pipeline.extractor import ExtractionOrchestrator
from app.pipeline.llm_client import llm_client
from app.preprocessing import chunk_document, preprocess_chapter
from app.tests.test_phase4_contracts import CHAPTER, PAYLOAD, parsed_payload

pytestmark = pytest.mark.skipif(not SCHEMA_PATH.exists(), reason="orion_gold_v1.schema.json not present")


def schema():
    return load_schema()


def obs(**over):
    base = dict(source_chunk="chunk_0000", source_span=(0, 100), sentence_ids=("s0000",))
    base.update(over)
    return base


def full_result():
    """Every gold field populated, the way a future mention-grounded extractor would."""
    return ExtractionResult(
        entity_mentions=(
            EntityMention(text="Alice", type="character", mention_kind="proper", start=0, end=5, id="M1", **obs()),
            EntityMention(text="Silver Haven", type="location", mention_kind="proper", start=20, end=32, id="M2", **obs()),
            EntityMention(text="She", type="character", mention_kind="pronominal", start=40, end=43, id="M3", **obs()),
        ),
        coreference_clusters=(CoreferenceCluster(cluster_id="C1", mentions=("M1", "M3")),),
        events=(Event(local_id="e1", type="ARRIVAL", trigger="arrived", start=6, end=13, id="E1",
                      participant_refs=(EventParticipant(role="agent", mention_id="M1"),
                                        EventParticipant(role="location", mention_id="M2")), **obs()),
                Event(local_id="e2", type="DEPARTURE", trigger="left", start=50, end=54, id="E2", **obs())),
        relationships=(Relationship(subject="Alice", predicate="FRIEND_OF", object="She",
                                    subject_mention_id="M1", object_mention_id="M3", id="R1", **obs()),),
        facts=(FactObservation(entity="Alice", property="age", value=30, entity_mention_id="M1", id="F1", **obs()),),
        temporal_expressions=(TemporalExpression(text="at noon", type="absolute_time", start=60, end=67, id="T1", **obs()),),
        temporal_relations=(TemporalRelation(source_event_id="E1", relation="BEFORE", target_event_id="E2", id="TR1", **obs()),),
    )


# ============================================================================ schema vocabulary
def test_vocabulary_constants_match_the_schema_file():
    d = schema()["$defs"]
    assert gold.MENTION_TYPES == tuple(d["mention"]["properties"]["type"]["enum"])
    assert gold.MENTION_KINDS == tuple(d["mention"]["properties"]["mention_kind"]["enum"])
    assert gold.EVENT_TYPES == tuple(d["event"]["properties"]["type"]["enum"])
    assert gold.PARTICIPANT_ROLES == tuple(d["eventParticipant"]["properties"]["role"]["enum"])
    assert gold.PREDICATES == tuple(d["relationship"]["properties"]["predicate"]["enum"])
    assert gold.FACT_PROPERTIES == tuple(d["fact"]["properties"]["property"]["enum"])
    assert gold.TEMPORAL_EXPRESSION_TYPES == tuple(d["temporalExpression"]["properties"]["type"]["enum"])
    assert gold.TEMPORAL_RELATIONS == tuple(d["temporalRelation"]["properties"]["relation"]["enum"])
    assert schema()["properties"]["schema_version"]["const"] == gold.GOLD_SCHEMA_VERSION


def test_validator_itself_rejects_bad_documents():  # guards the guard
    proj = project_to_gold(full_result(), story_id="s", text="x" * 100)
    assert schema_errors(proj.document) == []
    for mutate in (lambda d: d.pop("facts"), lambda d: d["mentions"][0].update(mention_id="X1"),
                   lambda d: d["events"][0].update(type="PARTY"), lambda d: d["mentions"][0].update(extra=1)):
        doc = json.loads(json.dumps(proj.document))
        mutate(doc)
        assert schema_errors(doc)


# ============================================================================ schema-compliant creation
def test_fully_populated_result_projects_to_a_schema_valid_document():
    proj = project_to_gold(full_result(), story_id="story-1", text="x" * 100, title="T")
    assert proj.issues == () and proj.is_schema_complete
    assert schema_errors(proj.document) == []
    d = proj.document
    assert [m["mention_id"] for m in d["mentions"]] == ["M1", "M2", "M3"]
    assert d["coreference_clusters"] == [{"cluster_id": "C1", "mentions": ["M1", "M3"]}]
    assert d["events"][0]["participants"] == [{"role": "agent", "mention_id": "M1"},
                                              {"role": "location", "mention_id": "M2"}]
    assert d["temporal_relations"][0]["source_event_id"] == "E1"
    assert d["title"] == "T"


def test_ids_are_assigned_deterministically_when_missing():
    r = ExtractionResult(entity_mentions=(
        EntityMention(text="A", **obs()), EntityMention(text="B", id="M2", **obs()), EntityMention(text="C", **obs())))
    ids = [m["mention_id"] for m in project_to_gold(r, story_id="s", text="t").document["mentions"]]
    assert ids == ["M1", "M2", "M3"] and ids == [m["mention_id"] for m in project_to_gold(r, story_id="s", text="t").document["mentions"]]


# ============================================================================ pipeline output -> aligned models
def test_parser_output_maps_to_aligned_models_with_unpopulated_gold_fields():
    doc = preprocess_chapter(CHAPTER)
    [chunk] = chunk_document(doc)
    r = observations_from_parsed(chunk, parsed_payload())
    m = r.entity_mentions[0]
    assert (m.text, m.type, m.mention_kind, m.start, m.end, m.id) == ("Alice", "character", None, None, None, None)
    e = r.events[0]
    assert (e.local_id, e.type, e.trigger, e.start, e.participant_refs) == ("e1", "MEETING", None, None, ())
    assert e.participants == ("Alice", "Bob")
    rel = r.relationships[0]
    assert (rel.subject_mention_id, rel.object_mention_id) == (None, None)
    assert r.temporal_expressions == () and r.coreference_clusters == ()
    for o in r.observations():  # span + sentence ids survive the alignment
        assert o.source_span == (chunk.start, chunk.end) and o.sentence_ids == tuple(chunk.sentence_ids)


def test_current_extraction_projects_honestly_and_is_reported_incomplete():
    doc = preprocess_chapter(CHAPTER)
    [chunk] = chunk_document(doc)
    r = observations_from_parsed(chunk, parsed_payload())
    proj = project_to_gold(r, story_id="s1", text=CHAPTER)
    joined = "\n".join(proj.issues)
    assert not proj.is_schema_complete
    assert "no start/end (mention offsets are not populated)" in joined
    assert "no trigger/start/end" in joined
    assert "predicate 'FATHER_OF' is not a gold predicate" in joined   # reported, NOT remapped
    assert "property 'rank' is not a gold property" in joined
    # the projection never repairs: a document is schema-valid exactly when there are no issues
    assert bool(schema_errors(proj.document)) == bool(proj.issues)
    assert r.relationships[0].predicate == "FATHER_OF"


def test_name_references_resolve_by_exact_match_only():
    doc = preprocess_chapter(CHAPTER)
    [chunk] = chunk_document(doc)
    d = project_to_gold(observations_from_parsed(chunk, parsed_payload()), story_id="s", text=CHAPTER).document
    alice, bob = d["mentions"][0]["mention_id"], d["mentions"][1]["mention_id"]
    assert d["events"][0]["participants"] == [{"role": "participant", "mention_id": alice},
                                              {"role": "participant", "mention_id": bob}]
    assert d["relationships"][0]["subject_mention_id"] == bob        # "Bob" matches the mention text
    assert "object_mention_id" not in d["relationships"][0]          # "Carl" has no mention: not invented


def test_ambiguous_event_labels_are_refused_not_guessed():
    r = ExtractionResult(
        events=(Event(local_id="e1", **obs()), Event(local_id="e1", **obs(source_chunk="chunk_0001"))),
        temporal_relations=(TemporalRelation(source_event_id="e1", relation="BEFORE", target_event_id="e2", **obs()),))
    proj = project_to_gold(r, story_id="s", text="t")
    assert any("unknown or ambiguous" in i for i in proj.issues)
    assert "source_event_id" not in proj.document["temporal_relations"][0]


# ============================================================================ backward compatibility
def test_legacy_dict_output_is_unchanged(monkeypatch):
    monkeypatch.setattr(extractor_module, "CHUNK_MAX_CHARS", 90)
    monkeypatch.setattr(extractor_module, "CHUNK_OVERLAP_SENTENCES", 1)
    monkeypatch.setattr(llm_client, "generate", lambda **kw: json.dumps(PAYLOAD))
    out = ExtractionOrchestrator().extract_chapter(CHAPTER, 1)
    ent, ev, tr, rel = out["raw_mentions"][0], out["events"][0], out["temporal_relations"][0], out["relationships"][0]
    assert set(ent) == {"mention", "canonical_name", "type", "attributes", "evidence", "source_chunk", "source_span"}
    assert set(ev) == {"id", "type", "participants", "location", "time_expression", "evidence", "source_chunk", "source_span"}
    assert set(tr) == {"event_1", "relation", "event_2", "evidence"}
    assert set(rel) == {"subject", "predicate", "object", "certainty", "evidence", "source_chunk", "source_span"}
    assert (ent["mention"], ev["id"], tr["event_1"], tr["event_2"]) == ("Alice", "e1", "e1", "e2")
    assert set(out["state_changes"][0]) == {"entity", "property", "previous_value", "new_value", "caused_by_event", "evidence"}
    assert not any("id" in o for o in out["raw_mentions"] if o is not ev)  # legacy items carry no gold ids


# ============================================================================ schema violations
@pytest.mark.parametrize("build", [
    lambda: EntityMention(text="A", id="E1", **obs()),                       # wrong id prefix
    lambda: EntityMention(text="A", id="M", **obs()),
    lambda: Event(local_id="e", id="M1", **obs()),
    lambda: EntityMention(text="A", start=5, **obs()),                       # start without end
    lambda: EntityMention(text="A", start=9, end=3, **obs()),                # start > end
    lambda: EntityMention(text="A", start=90, end=120, **obs()),             # outside source_span
    lambda: Event(local_id="e", trigger=" ", **obs()),                       # blank trigger
    lambda: Event(local_id="e", trigger="x", start=-1, end=2, **obs()),
    lambda: Event(local_id="e", participant_refs=("M1",), **obs()),          # not EventParticipant
    lambda: EventParticipant(role="", mention_id="M1"),
    lambda: EventParticipant(role="agent", mention_id="X1"),
    lambda: Relationship(subject="A", predicate="P", object="B", subject_mention_id="A1", **obs()),
    lambda: FactObservation(entity="A", property="p", value="v", entity_mention_id="mention1", **obs()),
    lambda: TemporalExpression(text="", **obs()),
    lambda: TemporalRelation(source_event_id="e", relation="BEFORE", target_event_id="e", id="T1", **obs()),
    lambda: CoreferenceCluster(cluster_id="C1", mentions=("M1",)),           # < 2 mentions
    lambda: CoreferenceCluster(cluster_id="C1", mentions=("M1", "M1")),      # not unique
    lambda: CoreferenceCluster(cluster_id="X1", mentions=("M1", "M2")),
    lambda: CoreferenceCluster(cluster_id="C1", mentions=("M1", "E2")),
])
def test_schema_violations_are_rejected(build):
    with pytest.raises(ContractError):
        build()


def test_projection_reports_out_of_enum_and_non_scalar_values():
    r = ExtractionResult(
        entity_mentions=(EntityMention(text="A", type="creature", **obs()),),
        facts=(FactObservation(entity="A", property="age", value=["x"], **obs()),
               FactObservation(entity="ghost", property="age", value=3, **obs())))
    issues = "\n".join(project_to_gold(r, story_id="s", text="t").issues)
    assert "type 'creature' is not a gold mention type" in issues
    assert "not a gold scalar" in issues
    assert "entity 'ghost' has no mention" in issues
