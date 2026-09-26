"""Phase 7 / 7.1: split extraction pipeline (entities -> relationships -> events -> facts) with evidence-based,
code-assigned sentence grounding (the model never outputs sentence ids)."""
import json
import logging
import pathlib
import re

import pytest

from app.config.settings import settings
from app.contracts import (EntityMention, Event, EventParticipant, ExtractionResult, FactObservation, Relationship,
                           project_to_gold)
from app.models.entity import Entity
from app.models.event import EventParticipant as EventParticipantRow
from app.models.fact import Fact
from app.models.relationship import Relationship as RelationshipRow, RelationshipVersion
from app.pipeline import extractor as extractor_module
from app.pipeline.extractor import ExtractionError, ExtractionOrchestrator
from app.pipeline.llm_client import llm_client
from app.pipeline.stages import (GroundingLog, IdCounters, StageError, extract_chunk_split, extract_events,
                                 extract_facts, extract_mentions, extract_relationships, locate_sentence)
from app.pipeline.stages.common import item_cap, render_sentences
from app.preprocessing import chunk_document, preprocess_chapter
from app.resolution import ground_mention_references
from app.services.world_state_service import WorldStateService
from app.tests.test_phase45_gold import schema_errors

S0, S1, S2 = "Alice met Bob in Silver Haven.", "Bob was 30 years old.", "Later Alice left."
TEXT = f"{S0} {S1} {S2}"
STAGE_NAMES = {"STAGE 1": "entities", "STAGE 2": "relationships", "STAGE 3": "events", "STAGE 4": "facts"}


def setup(text=TEXT, **chunk_kw):
    doc = preprocess_chapter(text)
    return doc, chunk_document(doc, **chunk_kw)


def one():
    doc, [chunk] = setup()
    return doc, chunk


class FakeLLM:
    """Deterministic stand-in: returns the canned payload of whichever stage the system prompt announces."""

    def __init__(self, **payloads):
        self.payloads, self.calls, self.prompts, self.schemas = payloads, [], [], []

    def __call__(self, prompt, system_prompt=None, json_mode=True, temperature=0.0, schema=None):
        stage = next(v for k, v in STAGE_NAMES.items() if system_prompt.startswith(k))
        self.calls.append(stage)
        self.prompts.append(prompt)
        self.schemas.append(schema)
        out = self.payloads[stage]
        out = out(prompt) if callable(out) else out
        return out if isinstance(out, str) else json.dumps(out)


def m(text, mtype="character", **extra):
    return {"text": text, "type": mtype, **extra}


# Stage 1 lists each name once; code finds 5 occurrences: Alice/Bob/Silver Haven in S0, Bob in S1, Alice in S2
# (mention ids M1..M5). Stages 2-4 see one label per name: M1 Alice, M2 Bob, M3 Silver Haven.
MENTIONS = {"mentions": [m("Alice", "Character"), m("Bob"), m("Silver Haven", "location")]}
RELS = {"relationships": [{"subject": "M1", "predicate": "knows", "object": "M2", "evidence": S0}]}
EVENTS = {
    "events": [
        {"id": "e1", "type": "meeting", "trigger": "met", "evidence": S0,
         "participants": [{"mention": "M1", "role": "agent"}, {"mention": "M2", "role": "participant"},
                          {"mention": "M3", "role": "location"}]},
        {"id": "e2", "type": "departure", "trigger": "left", "evidence": S2,
         "participants": [{"mention": "M1", "role": "agent"}]}],
    "temporal_relations": [{"source": "e1", "relation": "before", "target": "e2"}]}
FACTS = {"facts": [{"entity": "M2", "property": "age", "value": "30", "evidence": S1}]}


def full_llm(**over):
    return FakeLLM(**{"entities": MENTIONS, "relationships": RELS, "events": EVENTS, "facts": FACTS, **over})


def mentions_for(doc, chunk):
    return extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities=MENTIONS))


# ============================================================================ locate_sentence
def test_locate_sentence_reports_exactly_one_match():
    doc, _ = one()
    r = locate_sentence("Bob was 30", list(doc.iter_sentences()))
    assert (r.status, r.sentence_ids, r.sentence_id) == ("unique", ("s0001",), "s0001")
    assert r.sentence.start == doc.sentence("s0001").start and r.evidence == "Bob was 30"


def test_locate_sentence_marks_several_matches_ambiguous_without_choosing():
    doc, _ = one()
    r = locate_sentence("Bob", list(doc.iter_sentences()))
    assert r.status == "ambiguous" and r.sentence_ids == ("s0000", "s0001") and r.sentence_id is None and r.sentence is None


def test_locate_sentence_no_match():
    doc, _ = one()
    r = locate_sentence("Carol arrived", list(doc.iter_sentences()))
    assert (r.status, r.sentence_ids, r.sentence_id) == ("none", (), None)


@pytest.mark.parametrize("evidence", ["alice met bob in silver haven.",       # case differs
                                      "Alice  met Bob",                         # extra whitespace
                                      "Alice met Bob in Silver Haven. Bob",     # spans two sentences
                                      "Alice met Bob in Silver Haven. ",        # trailing space
                                      " Bob was"])                              # leading space
def test_locate_sentence_is_an_exact_substring_match_with_no_normalization(evidence):
    doc, _ = one()
    assert locate_sentence(evidence, list(doc.iter_sentences())).status == "none"


@pytest.mark.parametrize("evidence", ["", "   ", None, 5])
def test_locate_sentence_never_matches_empty_or_non_string_evidence(evidence):
    doc, _ = one()
    assert locate_sentence(evidence, list(doc.iter_sentences())).status == "none"


def test_locate_sentence_counts_a_sentence_once_even_if_the_evidence_repeats_in_it():
    doc, [chunk] = setup("Bob saw Bob. Zed slept.")
    assert locate_sentence("Bob", list(doc.iter_sentences())).status == "unique"


# ============================================================================ stage 1: entities
def test_stage1_creates_one_mention_per_exact_occurrence_with_exact_offsets():
    doc, chunk = one()
    ms = mentions_for(doc, chunk)
    assert [(m_.id, m_.text, m_.type) for m_ in ms] == [("M1", "Alice", "character"), ("M2", "Bob", "character"),
                                                        ("M3", "Silver Haven", "location"), ("M4", "Bob", "character"),
                                                        ("M5", "Alice", "character")]
    assert [m_.sentence_ids for m_ in ms] == [("s0000",)] * 3 + [("s0001",), ("s0002",)]
    for mention_ in ms:
        sentence = doc.sentence(mention_.sentence_ids[0])
        assert mention_.source_span == (sentence.start, sentence.end) and mention_.source_chunk == chunk.id
        assert doc.text[mention_.start:mention_.end] == mention_.text          # exact own offsets, always
        assert mention_.raw_text == sentence.text and isinstance(mention_, EntityMention)
    assert all(m_.attributes == {} and m_.entity_id is None and m_.mention_kind is None for m_ in ms)


def test_stage1_ignores_evidence_or_sentence_ids_the_model_still_writes():
    doc, chunk = one()
    payload = {"mentions": [m("Bob", evidence="Nothing like this.", sentence_id="s9999")]}
    ms = extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities=payload))
    assert [x.sentence_ids for x in ms] == [("s0000",), ("s0001",)]      # decided by where "Bob" occurs


def test_stage1_a_name_listed_twice_is_one_form():
    doc, chunk = one()
    assert len(extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m("Bob")] * 3}))) == 2


def test_stage1_every_occurrence_in_a_sentence_is_a_mention():
    doc, [chunk] = setup("Alice saw Alice in the\nold tower.")
    a1, a2, tower = extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [
        m("Alice"), m("old tower", "location")]}))
    assert [(x.text, x.start) for x in (a1, a2, tower)] == [("Alice", 0), ("Alice", 10), ("old tower", 23)]


def test_stage1_nested_forms_are_all_kept_and_one_span_is_one_mention():
    doc, chunk = one()
    ms = extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [
        m("Silver Haven", "location"), m("Haven", "location"), m("Haven", "other")]}))
    assert [(x.text, x.start, x.end) for x in ms] == [("Silver Haven", 17, 29), ("Haven", 24, 29)]


def test_stage1_a_lowercase_form_also_matches_a_sentence_initial_capital_and_keeps_the_source_text():
    doc, [chunk] = setup("Old tower stood. The old tower fell. The Old tower ruins.")
    ms = extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m("old tower", "location")]}))
    assert [(x.text, x.start) for x in ms] == [("Old tower", 0), ("old tower", 21)]   # not mid-sentence "Old"


def test_stage1_straight_and_typographic_apostrophes_match_each_other_and_the_source_text_is_kept():
    doc, [chunk] = setup("Dan’s mother called. Rob's car waited.")
    ms = extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [
        m("Dan's mother"), m("Rob’s car", "object")]}))
    assert [x.text for x in ms] == ["Dan’s mother", "Rob's car"]


@pytest.mark.parametrize("form", ["Zed", "BOB", "Ali", "Silver  Haven", "Bob was 31", "the Bob"])
def test_stage1_matching_is_exact_whole_word_and_never_normalized(form):
    doc, chunk = one()
    with pytest.raises(StageError, match="does not occur in any sentence of this chunk"):
        extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m(form)]}))


def test_stage1_prompt_marks_new_vs_context_and_keeps_ids_out_of_the_text():
    doc, chunks = setup(TEXT, max_chars=60, overlap_sentences=1)
    fake = FakeLLM(entities={"mentions": []})
    extract_mentions(chunks[1], doc, IdCounters(), fake)
    p = fake.prompts[0]
    assert "[s0001] CONTEXT\n" + S1 in p and "[s0002] NEW\n" + S2 in p


BAD_STAGE1 = [
    "not json at all", "[1, 2]", {}, {"mentions": "x"}, {"mentions": ["x"]},
    {"mentions": [{"type": "character"}]},                                          # no text
    {"mentions": [{"text": "Alice"}]},                                              # no type
    {"mentions": [{"text": "", "type": "character"}]},
    {"mentions": [m("Alice", "person")]},                                           # type outside the gold list
    {"mentions": [m("Carol")]},                                                     # occurs nowhere
    {"mentions": [m("He")]}, {"mentions": [m("she")]},                              # pronouns are still rejected
]


@pytest.mark.parametrize("payload", BAD_STAGE1)
def test_stage1_rejects_malformed_output(payload):
    doc, chunk = one()
    with pytest.raises(StageError) as exc:
        extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities=payload))
    assert exc.value.stage == "entities" and exc.value.chunk_id == chunk.id and exc.value.errors


def test_stage1_a_form_only_in_a_context_sentence_makes_no_mention_and_is_logged_not_failed():
    doc, chunks = setup(TEXT, max_chars=60, overlap_sentences=1)
    assert chunks[1].overlap_sentence_ids == ("s0001",)
    log = GroundingLog()
    ms = extract_mentions(chunks[1], doc, IdCounters(), FakeLLM(entities={"mentions": [m("Bob"), m("Alice")]}), log)
    assert [(x.text, x.sentence_ids) for x in ms] == [("Alice", ("s0002",))]         # Bob is only in the overlap
    assert [(r.evidence, r.status, r.matched_sentence_ids) for r in log.records] == [
        ("Bob", "context_only", ["s0001"]), ("Alice", "located", ["s0002"])]


def test_stage1_reports_every_violation_not_just_the_first():
    doc, chunk = one()
    fake = FakeLLM(entities={"mentions": [m("Zed"), m("He"), {"text": "Amy"}]})
    with pytest.raises(StageError) as exc:
        extract_mentions(chunk, doc, IdCounters(), fake)
    assert len(exc.value.errors) == 3


# ============================================================================ stage 2: relationships
def test_stage2_references_mentions_by_id_and_grounds_through_evidence():
    doc, chunk = one()
    [r] = extract_relationships(chunk, doc, mentions_for(doc, chunk), FakeLLM(relationships=RELS))
    assert (r.subject_mention_id, r.object_mention_id) == ("M1", "M2")
    assert (r.subject, r.predicate, r.object, r.certainty) == ("Alice", "KNOWS", "Bob", "DEFINITE")
    assert r.sentence_ids == ("s0000",) and r.raw_text == S0
    assert doc.text[r.source_span[0]:r.source_span[1]] == S0


def test_stage2_ambiguous_evidence_is_valid_and_falls_back_to_the_chunk():
    doc, chunk = one()
    fake = FakeLLM(relationships={"relationships": [{"subject": "M1", "predicate": "KNOWS", "object": "M2", "evidence": "Bob"}]})
    [r] = extract_relationships(chunk, doc, mentions_for(doc, chunk), fake)
    assert r.sentence_ids == tuple(chunk.sentence_ids) and r.source_span == (chunk.start, chunk.end)


def test_stage2_prompt_lists_each_name_once_and_needs_no_names():
    doc, chunk = one()
    fake = FakeLLM(relationships={"relationships": []})
    extract_relationships(chunk, doc, mentions_for(doc, chunk), fake)
    listing = fake.prompts[0].split("MENTIONS (label | text | type):\n")[1].split("\n\n")[0]
    assert listing.split("\n") == ["M1 | Alice | character", "M2 | Bob | character", "M3 | Silver Haven | location"]


@pytest.mark.parametrize("item", [
    {"subject": "Alice", "predicate": "KNOWS", "object": "Bob", "evidence": S0},              # free-text names
    {"subject": "M1", "predicate": "KNOWS", "object": "M9", "evidence": S0},                  # unknown label
    {"subject": "M1", "predicate": "KNOWS", "object": "M1", "evidence": S0},                  # self relationship
    {"subject": "M1", "object": "M2", "evidence": S0},                                        # no predicate
    {"subject": "M1", "predicate": "KNOWS", "object": "M2"},                                  # no evidence
    {"subject": "M1", "predicate": "KNOWS", "object": "M2", "evidence": ""},
    {"subject": "M1", "predicate": "KNOWS", "object": "M2", "evidence": "They never met."},   # evidence not in chunk
    {"subject": "M1", "predicate": "KNOWS", "object": "M2", "evidence": S0, "certainty": "MAYBE"},
])
def test_stage2_rejects_malformed_relationships(item):
    doc, chunk = one()
    with pytest.raises(StageError) as exc:
        extract_relationships(chunk, doc, mentions_for(doc, chunk), FakeLLM(relationships={"relationships": [item]}))
    assert exc.value.stage == "relationships"


def test_stage2_rejects_missing_key_and_bad_json():
    doc, chunk = one()
    ms = mentions_for(doc, chunk)
    for payload in ({}, "nope", {"relationships": {}}):
        with pytest.raises(StageError):
            extract_relationships(chunk, doc, ms, FakeLLM(relationships=payload))


def test_stage2_makes_no_llm_call_without_two_mentions():
    doc, chunk = one()
    boom = FakeLLM(relationships=lambda p: pytest.fail("LLM must not be called"))
    assert extract_relationships(chunk, doc, mentions_for(doc, chunk)[:1], boom) == []
    assert extract_relationships(chunk, doc, [], boom) == []


# ============================================================================ stage 3: events
def test_stage3_grounds_events_by_evidence_and_computes_trigger_offsets_by_participant_reference():
    doc, chunk = one()
    ms = mentions_for(doc, chunk)
    events, temporal = extract_events(chunk, doc, ms, IdCounters(), FakeLLM(events=EVENTS))
    e1, e2 = events
    assert (e1.id, e1.type, e1.trigger) == ("E1", "MEETING", "met") and doc.text[e1.start:e1.end] == "met"
    assert e1.sentence_ids == ("s0000",) and e1.raw_text == S0 and e2.sentence_ids == ("s0002",)
    assert e1.participant_refs == (EventParticipant(role="agent", mention_id="M1"),
                                   EventParticipant(role="participant", mention_id="M2"),
                                   EventParticipant(role="location", mention_id="M3"))
    assert e1.participants == ("Alice", "Bob") and e1.location == "Silver Haven"
    assert e2.id == "E2" and doc.text[e2.start:e2.end] == "left"
    assert e1.local_id == f"{chunk.id}:e1"
    [t] = temporal
    assert (t.source_event_id, t.relation, t.target_event_id) == (f"{chunk.id}:e1", "BEFORE", f"{chunk.id}:e2")


@pytest.mark.parametrize("trigger", ["talk", "Met", "met Bob in Silver Haven and"])
def test_stage3_trigger_must_occur_in_its_own_evidence_exactly(trigger):
    doc, chunk = one()
    fake = FakeLLM(events={"events": [{"id": "e1", "type": "MEETING", "trigger": trigger, "evidence": S0}]})
    with pytest.raises(StageError, match="does not occur in its own evidence"):
        extract_events(chunk, doc, mentions_for(doc, chunk), IdCounters(), fake)


def test_stage3_offsets_stay_empty_when_the_trigger_occurs_only_as_part_of_a_word():
    doc, chunk = one()      # substring rule: "Hav" is in the evidence, but not as a whole word in the sentence
    fake = FakeLLM(events={"events": [{"id": "e1", "type": "MEETING", "trigger": "Hav", "evidence": S0}]})
    [e], _ = extract_events(chunk, doc, mentions_for(doc, chunk), IdCounters(), fake)
    assert e.trigger == "Hav" and (e.start, e.end) == (None, None) and e.sentence_ids == ("s0000",)


def test_stage3_allows_no_participants():
    doc, chunk = one()
    fake = FakeLLM(events={"events": [{"id": "e1", "type": "TRAVEL", "trigger": "left", "evidence": S2}]})
    [e], t = extract_events(chunk, doc, mentions_for(doc, chunk), IdCounters(), fake)
    assert e.participants == () and e.participant_refs == () and t == []


def test_stage3_makes_no_llm_call_without_mentions():
    doc, chunk = one()
    boom = FakeLLM(events=lambda p: pytest.fail("LLM must not be called"))
    assert extract_events(chunk, doc, [], IdCounters(), boom) == ([], [])


@pytest.mark.parametrize("payload", [
    {"events": [{"id": "e1", "type": "X", "trigger": "met"}]},                                          # no evidence
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": "  "}]},
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": "They exploded."}]},           # not in chunk
    {"events": [{"id": "e1", "type": "X", "evidence": S0}]},                                            # no trigger
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": S0, "participants": ["Alice"]}]},   # free text
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": S0,
                 "participants": [{"mention": "M9", "role": "agent"}]}]},                              # unknown mention
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": S0,
                 "participants": [{"mention": "M1"}]}]},                                                 # no role
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": S0, "participants": "M1"}]},
    {"events": [{"type": "X", "trigger": "met", "evidence": S0}]},                                      # no id
    {"events": [{"id": "e1", "trigger": "met", "evidence": S0}]},                                       # no type
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": S0},
                {"id": "e1", "type": "X", "trigger": "left", "evidence": S2}]},                        # duplicate id
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": S0}],
     "temporal_relations": [{"source": "e1", "relation": "BEFORE", "target": "e7"}]},                  # unknown event
    {"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": S0}],
     "temporal_relations": [{"source": "e1", "relation": "BEFORE", "target": "e1"}]},                  # self loop
    {"events": "x"}, {},
])
def test_stage3_rejects_malformed_output(payload):
    doc, chunk = one()
    with pytest.raises(StageError) as exc:
        extract_events(chunk, doc, mentions_for(doc, chunk), IdCounters(), FakeLLM(events=payload))
    assert exc.value.stage == "events"


# ============================================================================ stage 4: facts
def test_stage4_builds_attribute_and_state_change_facts_bound_to_mentions():
    doc, chunk = one()
    fake = FakeLLM(facts={"facts": [
        {"entity": "M2", "property": "age", "value": "30", "evidence": S1},
        {"entity": "M1", "property": "status", "value": "gone", "kind": "state_change", "previous_value": "here",
         "evidence": S2},
        {"entity": "M1", "property": "status", "value": True, "evidence": S0}]})
    a, b, c = extract_facts(chunk, doc, mentions_for(doc, chunk), fake)
    assert (a.entity, a.entity_mention_id, a.property, a.value, a.origin.value) == ("Bob", "M4", "age", "30", "attribute")
    assert (b.previous_value, b.origin.value) == ("here", "state_change") and c.value is True
    assert [f.sentence_ids for f in (a, b, c)] == [("s0001",), ("s0002",), ("s0000",)]
    assert a.source_span == (doc.sentence("s0001").start, doc.sentence("s0001").end) and a.raw_text == S1
    assert (b.entity, b.entity_mention_id) == ("Alice", "M5")   # label M1 resolves to Alice's occurrence in S2


def test_a_label_without_an_occurrence_in_the_grounded_sentence_uses_the_first_occurrence():
    doc, chunk = one()
    [f] = extract_facts(chunk, doc, mentions_for(doc, chunk), FakeLLM(facts={"facts": [
        {"entity": "M3", "property": "status", "value": "quiet", "evidence": S2}]}))
    assert (f.entity, f.entity_mention_id, f.sentence_ids) == ("Silver Haven", "M3", ("s0002",))


@pytest.mark.parametrize("item", [
    {"entity": "Bob", "property": "age", "value": "30", "evidence": S1},                       # name, not a label
    {"entity": "M9", "property": "age", "value": "30", "evidence": S1},
    {"entity": "M2", "property": "age", "value": None, "evidence": S1},
    {"entity": "M2", "property": "age", "value": "", "evidence": S1},
    {"entity": "M2", "property": "age", "value": {"n": 30}, "evidence": S1},
    {"entity": "M2", "property": "age", "value": "30", "kind": "guess", "evidence": S1},
    {"entity": "M2", "property": "age", "value": "30", "previous_value": "29", "evidence": S1},   # attribute
    {"entity": "M2", "value": "30", "evidence": S1},                                            # no property
    {"entity": "M2", "property": "age", "value": "30"},                                         # no evidence
    {"entity": "M2", "property": "age", "value": "30", "evidence": "He was thirty."},           # not in chunk
])
def test_stage4_rejects_malformed_facts(item):
    doc, chunk = one()
    with pytest.raises(StageError) as exc:
        extract_facts(chunk, doc, mentions_for(doc, chunk), FakeLLM(facts={"facts": [item]}))
    assert exc.value.stage == "facts"


def test_stage4_makes_no_llm_call_without_mentions():
    doc, chunk = one()
    assert extract_facts(chunk, doc, [], FakeLLM(facts=lambda p: pytest.fail("LLM must not be called"))) == []


# ============================================================================ combined pipeline
def test_combined_pipeline_runs_four_stages_in_order_and_builds_one_extraction_result():
    doc, chunk = one()
    llm = full_llm()
    result = extract_chunk_split(chunk, doc, IdCounters(), 3, llm)
    assert llm.calls == ["entities", "relationships", "events", "facts"]
    assert isinstance(result, ExtractionResult) and result.chapter_number == 3
    assert (len(result.entity_mentions), len(result.relationships), len(result.events), len(result.facts),
            len(result.temporal_relations)) == (5, 1, 2, 1, 1)
    assert result.entity_mentions[3].attributes == {"age": "30"}
    assert [f.property for f in result.facts] == ["age"]


def test_no_prompt_asks_the_model_for_sentence_ids_and_none_is_needed_end_to_end():
    doc, chunk = one()
    llm = full_llm()
    extract_chunk_split(chunk, doc, IdCounters(), 1, llm)
    assert all("sentence_id" not in p for p in llm.prompts)
    assert json.dumps([MENTIONS, RELS, EVENTS, FACTS]).count("sentence_id") == 0     # the fixtures never contain one


def test_ids_stay_unique_across_chunks_and_context_sentences_are_never_extracted_twice():
    text = "Alice met Bob. Alice greeted Bob. Alice thanked Bob. Alice left Bob."
    doc, chunks = setup(text, max_chars=45, overlap_sentences=1)
    assert len(chunks) > 1 and any(c.overlap_sentence_ids for c in chunks)

    def stage1(prompt):
        new = " ".join(body for _, body in re.findall(r"\[(s\d+)\] NEW\n(.*)", prompt))
        return {"mentions": [m(name) for name in ("Alice", "Bob") if name in new]}

    ids, ms = IdCounters(), []
    for chunk in chunks:
        ms += extract_mentions(chunk, doc, ids, FakeLLM(entities=stage1))
    assert len(ms) == 8                                                         # 4 sentences x 2 names, none doubled
    assert [x.id for x in ms] == [f"M{i}" for i in range(1, 9)]
    assert len({x.sentence_ids for x in ms if x.text == "Alice"}) == 4


def test_pipeline_is_deterministic():
    doc, chunk = one()
    a = extract_chunk_split(chunk, doc, IdCounters(), 1, full_llm()).to_dict()
    b = extract_chunk_split(chunk, doc, IdCounters(), 1, full_llm()).to_dict()
    assert a == b


def test_downstream_contract_is_identical_to_the_cited_sentence_version():
    """Same sentence-level provenance, offsets and ids as before 7.1: only WHO decides the sentence changed."""
    doc, chunk = one()
    r = extract_chunk_split(chunk, doc, IdCounters(), 1, full_llm())
    s0, s1, s2 = (doc.sentence(i) for i in ("s0000", "s0001", "s0002"))
    assert [(x.sentence_ids, x.source_span) for x in r.entity_mentions] == [
        (("s0000",), (s0.start, s0.end))] * 3 + [(("s0001",), (s1.start, s1.end)), (("s0002",), (s2.start, s2.end))]
    assert [(x.start, x.end) for x in r.entity_mentions] == [(0, 5), (10, 13), (17, 29), (31, 34), (s2.start + 6, s2.start + 11)]
    assert (r.relationships[0].sentence_ids, r.events[1].sentence_ids, r.facts[0].sentence_ids) == (
        ("s0000",), ("s0002",), ("s0001",))
    assert [e.id for e in r.events] == ["E1", "E2"] and r.temporal_relations[0].sentence_ids == tuple(chunk.sentence_ids)


# ============================================================================ grounding log
def test_grounding_log_records_evidence_matches_and_assigned_sentence_per_item(caplog):
    doc, chunk = one()
    log = GroundingLog()
    rel = lambda ev: {"subject": "M1", "predicate": "KNOWS", "object": "M2", "evidence": ev}   # noqa: E731
    with caplog.at_level(logging.DEBUG, logger="app.pipeline.stages.grounding"):
        with pytest.raises(StageError):
            extract_relationships(chunk, doc, mentions_for(doc, chunk), FakeLLM(relationships={"relationships": [
                rel(S0), rel("Bob"), rel("Zed appeared.")]}), log)
    assert [(r.evidence, r.matched_sentence_ids, r.assigned_sentence_id, r.status) for r in log.records] == [
        (S0, ["s0000"], "s0000", "unique"), ("Bob", ["s0000", "s0001"], None, "ambiguous"),
        ("Zed appeared.", [], None, "unmatched")]
    assert {"items": 3, "ambiguous": 1, "unmatched": 1, "missing_evidence": 0, "unique": 1, "spanning": 0,
            "located": 0, "context_only": 0} == log.summary()
    text = caplog.text
    assert "evidence='Bob' matched=['s0000', 's0001'] assigned=None" in text and "assigned=s0000" in text


def test_stage1_logs_each_listed_form_with_the_sentences_it_occurs_in():
    doc, chunk = one()
    log = GroundingLog()
    with pytest.raises(StageError):
        extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m("Bob"), m("Zed")]}), log)
    assert [(r.evidence, r.matched_sentence_ids, r.assigned_sentence_id, r.status) for r in log.records] == [
        ("Bob", ["s0000", "s0001"], None, "located"), ("Zed", [], None, "unmatched")]


def test_missing_evidence_is_counted_separately(caplog):
    doc, chunk = one()
    log = GroundingLog()
    with pytest.raises(StageError):
        extract_relationships(chunk, doc, mentions_for(doc, chunk), FakeLLM(relationships={"relationships": [
            {"subject": "M1", "predicate": "KNOWS", "object": "M2"}]}), log)
    assert log.summary()["missing_evidence"] == 1 and log.summary()["unmatched"] == 0


def test_chunk_summary_is_logged_at_info_even_when_a_stage_fails(caplog):
    doc, chunk = one()
    llm = full_llm(events={"events": [{"id": "e1", "type": "X", "trigger": "met", "evidence": "Nothing like it."}]})
    log = GroundingLog()
    with caplog.at_level(logging.INFO, logger="app.pipeline.stages.grounding"):
        with pytest.raises(StageError, match="stage 'events'"):
            extract_chunk_split(chunk, doc, IdCounters(), 1, llm, log)
    assert (f"grounding {chunk.id}: items=5 ambiguous=0 unmatched=1 missing_evidence=0 unique=1 spanning=0 "
            f"located=3 context_only=0") in caplog.text
    assert log.chunk_id == chunk.id


def test_pipeline_creates_its_own_log_when_none_is_given(caplog):
    doc, chunk = one()
    with caplog.at_level(logging.INFO, logger="app.pipeline.stages.grounding"):
        extract_chunk_split(chunk, doc, IdCounters(), 1, full_llm())
    assert f"grounding {chunk.id}: items=7 ambiguous=0 unmatched=0" in caplog.text


# ============================================================================ prompts and rendering
def test_stage_prompts_are_plain_instructions_without_examples_or_sentence_ids():
    root = pathlib.Path(extractor_module.__file__).parent / "prompts" / "stages"
    files = sorted(root.glob("stage*.txt"))
    assert [f.name for f in files] == ["stage1_entities.txt", "stage2_relationships.txt", "stage3_events.txt",
                                       "stage4_facts.txt"]
    for n, f in enumerate(files, 1):
        text = f.read_text()
        assert text.startswith(f"STAGE {n} - ") and "Return strictly valid JSON" in text
        assert "example" not in text.lower() and "few-shot" not in text.lower()
        assert "sentence_id" not in text and "cited" not in text
        if n == 1:
            assert "evidence" not in text and "mention_kind" not in text        # stage 1 only names things
        else:
            assert '"evidence" is required' in text and '"evidence": "..."' in text


def test_sentence_ids_are_metadata_lines_never_embedded_in_the_text_the_model_copies():
    text = "Alice saw Bob in the\nold tower. Bob left."
    doc, [chunk] = setup(text)
    sents = [s for s in doc.iter_sentences()]
    out = render_sentences(sents, {s.id for s in sents})
    marker = re.compile(r"^\[s\d{4}\] (NEW|CONTEXT)$")
    body = [line for line in out.split("\n") if not marker.match(line)]
    assert not any(re.search(r"\[s\d+\]", line) for line in body)                   # no id inside any text line
    assert "Alice saw Bob in the\nold tower." in out                                # text is verbatim (newline kept)
    for s in sents:
        assert s.text in out                                                        # so evidence copies are exact


@pytest.mark.parametrize("evidence", ["[s0000] NEW", "[s0000] Alice met Bob in Silver Haven."])
def test_a_model_that_copies_the_marker_into_evidence_fails_grounding(evidence):
    doc, chunk = one()
    with pytest.raises(StageError, match="does not occur verbatim"):
        extract_relationships(chunk, doc, mentions_for(doc, chunk), FakeLLM(relationships={"relationships": [
            {"subject": "M1", "predicate": "KNOWS", "object": "M2", "evidence": evidence}]}))


# ============================================================================ failure isolation
@pytest.mark.parametrize("bad_stage, called", [
    ("entities", ["entities"]),
    ("relationships", ["entities", "relationships"]),
    ("events", ["entities", "relationships", "events"]),
    ("facts", ["entities", "relationships", "events", "facts"]),
])
def test_a_failing_stage_stops_the_pipeline_and_names_itself(bad_stage, called):
    doc, chunk = one()
    llm = full_llm(**{bad_stage: "this is not json"})
    with pytest.raises(StageError) as exc:
        extract_chunk_split(chunk, doc, IdCounters(), 1, llm)
    assert exc.value.stage == bad_stage and llm.calls == called


def test_a_later_stage_cannot_hide_or_repair_an_earlier_stages_failure():
    doc, chunk = one()
    llm = full_llm(entities={"mentions": [m("Carol")]})
    with pytest.raises(StageError, match="stage 'entities'"):
        extract_chunk_split(chunk, doc, IdCounters(), 1, llm)
    assert llm.calls == ["entities"]


def test_stages_do_not_trust_each_other_a_foreign_mention_list_is_validated_too():
    doc, chunk = one()
    ms = mentions_for(doc, chunk)
    with pytest.raises(StageError):
        extract_relationships(chunk, doc, ms[:2], FakeLLM(relationships={"relationships": [
            {"subject": "M1", "predicate": "KNOWS", "object": "M3", "evidence": S0}]}))


# ============================================================================ orchestrator wiring
def test_orchestrator_defaults_to_monolithic_and_split_is_opt_in(monkeypatch):
    assert settings.EXTRACTION_PIPELINE == "monolithic" and ExtractionOrchestrator().pipeline == "monolithic"
    monkeypatch.setattr(settings, "EXTRACTION_PIPELINE", "split")
    assert ExtractionOrchestrator().pipeline == "split"
    assert ExtractionOrchestrator(pipeline="monolithic").pipeline == "monolithic"
    monkeypatch.setattr(settings, "EXTRACTION_PIPELINE", "bogus")
    with pytest.raises(ExtractionError, match="Unknown EXTRACTION_PIPELINE"):
        ExtractionOrchestrator().extract_chapter(TEXT, 1)


def test_monolithic_mode_never_touches_the_stage_prompts(monkeypatch):
    seen = []
    monkeypatch.setattr(llm_client, "generate", lambda **kw: seen.append(kw["system_prompt"]) or "{}")
    out = ExtractionOrchestrator(pipeline="monolithic").extract_chapter(TEXT, 1)
    assert out["pipeline"] == "monolithic" and len(seen) == 1 and not seen[0].startswith("STAGE")


def test_split_extraction_through_the_orchestrator_matches_the_legacy_output_shape(monkeypatch):
    llm = full_llm()
    monkeypatch.setattr(llm_client, "generate", llm)
    out = ExtractionOrchestrator(pipeline="split").extract_chapter(TEXT, 1)
    assert out["pipeline"] == "split" and llm.calls == ["entities", "relationships", "events", "facts"]
    assert {"entities", "raw_mentions", "relationships", "events", "state_changes", "temporal_relations",
            "preprocessing", "observations", "document"} <= set(out)
    assert set(out["raw_mentions"][0]) == {"mention", "canonical_name", "type", "attributes", "evidence",
                                           "source_chunk", "source_span"}
    assert set(out["events"][0]) == {"id", "type", "participants", "location", "time_expression", "evidence",
                                     "source_chunk", "source_span"}
    assert out["events"][0]["location"] == "Silver Haven" and out["events"][0]["participants"] == ["Alice", "Bob"]
    assert {e["canonical_name"]: e for e in out["entities"]}["Bob"]["attributes"] == {"age": "30"}


def test_a_stage_failure_fails_the_chapter_with_an_actionable_message(monkeypatch):
    monkeypatch.setattr(llm_client, "generate", full_llm(events={"events": [{"id": "e1"}]}))
    with pytest.raises(ExtractionError, match=r"chunk 1/1: split extraction failed: stage 'events'"):
        ExtractionOrchestrator(pipeline="split").extract_chapter(TEXT, 1)


# ============================================================================ schema compliance
def test_split_output_projects_to_a_gold_schema_valid_document():
    doc, chunk = one()
    result = extract_chunk_split(chunk, doc, IdCounters(), 1, full_llm())
    proj = project_to_gold(result, story_id="s1", text=doc.text)
    assert proj.issues == () and proj.is_schema_complete
    assert schema_errors(proj.document) == []
    d = proj.document
    assert [x["mention_id"] for x in d["mentions"]] == ["M1", "M2", "M3", "M4", "M5"]
    assert d["events"][0]["participants"] == [{"role": "agent", "mention_id": "M1"},
                                              {"role": "participant", "mention_id": "M2"},
                                              {"role": "location", "mention_id": "M3"}]
    assert d["relationships"][0]["subject_mention_id"] == "M1" and d["facts"][0]["entity_mention_id"] == "M4"
    assert d["temporal_relations"][0]["source_event_id"] == "E1"


# ============================================================================ explicit-reference grounding
def prov(**over):
    base = dict(source_chunk="c0", source_span=(0, 50), sentence_ids=("s0000",))
    base.update(over)
    return base


def test_explicit_mention_references_win_over_name_based_ids_and_skip_the_location_role():
    ms = (EntityMention(id="M1", text="Al", entity_id="e-right", **prov()),
          EntityMention(id="M2", text="Bo", entity_id="e-bo", **prov()),
          EntityMention(id="M3", text="Ho", entity_id="e-home", **prov()))
    result = ExtractionResult(
        entity_mentions=ms,
        relationships=(Relationship(subject="Al", predicate="KNOWS", object="Bo", subject_mention_id="M1",
                                    object_mention_id="M2", subject_entity_id="e-wrong", **prov()),),
        events=(Event(local_id="e", participants=("Al", "Bo"), participant_entity_ids=(None, None),
                      participant_refs=(EventParticipant(role="location", mention_id="M3"),
                                        EventParticipant(role="agent", mention_id="M1"),
                                        EventParticipant(role="participant", mention_id="M2")), **prov()),),
        facts=(FactObservation(entity="Al", property="age", value="3", entity_mention_id="M1", **prov()),))
    out = ground_mention_references(result)
    assert (out.relationships[0].subject_entity_id, out.relationships[0].object_entity_id) == ("e-right", "e-bo")
    assert out.events[0].participant_entity_ids == ("e-right", "e-bo")
    assert out.facts[0].entity_id == "e-right"


def test_observations_without_references_are_left_untouched():
    result = ExtractionResult(
        entity_mentions=(EntityMention(id="M1", text="Al", entity_id="e1", **prov()),),
        relationships=(Relationship(subject="Al", predicate="KNOWS", object="Al", subject_entity_id="x", **prov()),),
        facts=(FactObservation(entity="Al", property="p", value="v", entity_id="y", **prov()),))
    assert ground_mention_references(result) == result


# ============================================================================ World State integration
def integrate(env, w, data, chapter=1):
    with env.Session() as s:
        svc = WorldStateService(s)
        counts = svc.integrate_extraction_result(
            w["world_id"], data, chapter_id=w["runs"][chapter]["chapter_id"],
            chapter_version_id=w["runs"][chapter]["chapter_version_id"])
        s.commit()
        return svc, counts


def test_split_output_integrates_into_the_world_state_with_grounded_references(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("SP", chapters=1)
    monkeypatch.setattr(llm_client, "generate", full_llm())
    data = ExtractionOrchestrator(pipeline="split").extract_chapter(TEXT, 1)
    svc, counts = integrate(env, w, data)
    with env.Session() as s:
        assert sorted(e.canonical_name for e in s.query(Entity)) == ["Alice", "Bob", "Silver Haven"]
        alice = s.query(Entity).filter_by(canonical_name="Alice").one()
        bob = s.query(Entity).filter_by(canonical_name="Bob").one()
        [rel] = s.query(RelationshipRow).all()
        assert (rel.source_entity_id, rel.target_entity_id) == (alice.id, bob.id)
        assert [v.relationship_type for v in s.query(RelationshipVersion)] == ["KNOWS"]
        assert {p.entity_id for p in s.query(EventParticipantRow)} == {alice.id, bob.id}
        [fact] = s.query(Fact).all()
        assert fact.entity_id == bob.id and fact.property_name == "age"
    res = svc.last_resolution.result
    assert res.relationships[0].subject_entity_id == res.entity_mentions[0].entity_id
    assert [c.entity_id for c in svc.last_coreference.clusters] == [res.entity_mentions[0].entity_id, res.entity_mentions[1].entity_id]
    assert counts["events_added"] == 2


def test_split_extraction_reuses_existing_entities_through_phase5(phase1_env, monkeypatch):
    env = phase1_env
    w = env.make_world("RU", chapters=2)
    monkeypatch.setattr(llm_client, "generate", FakeLLM(
        entities={"mentions": [m("Robert")]},
        relationships={"relationships": []}, events={"events": []}, facts={"facts": []}))
    integrate(env, w, ExtractionOrchestrator(pipeline="split").extract_chapter("Robert waited.", 1), 1)

    text2 = "Rob hit John."
    monkeypatch.setattr(llm_client, "generate", FakeLLM(
        entities={"mentions": [m("Rob"), m("John")]},
        relationships={"relationships": [{"subject": "M1", "predicate": "ENEMY_OF", "object": "M2", "evidence": text2}]},
        events={"events": [{"id": "e1", "type": "ATTACK", "trigger": "hit", "evidence": text2,
                            "participants": [{"mention": "M1", "role": "agent"}, {"mention": "M2", "role": "patient"}]}]},
        facts={"facts": []}))
    integrate(env, w, ExtractionOrchestrator(pipeline="split").extract_chapter(text2, 1), 2)
    with env.Session() as s:
        assert sorted(e.canonical_name for e in s.query(Entity)) == ["John", "Robert"]      # no duplicate "Rob"
        robert = s.query(Entity).filter_by(canonical_name="Robert").one()
        john = s.query(Entity).filter_by(canonical_name="John").one()
        [rel] = s.query(RelationshipRow).all()
        assert (rel.source_entity_id, rel.target_entity_id) == (robert.id, john.id)
        assert {p.entity_id for p in s.query(EventParticipantRow)} == {robert.id, john.id}


# ============================================================================ Phase 7.1b: spanning evidence
def test_evidence_quoted_across_consecutive_sentences_grounds_to_exactly_those_sentences():
    doc, chunk = one()
    log = GroundingLog()
    [r] = extract_relationships(chunk, doc, mentions_for(doc, chunk), FakeLLM(relationships={"relationships": [
        {"subject": "M1", "predicate": "KNOWS", "object": "M2", "evidence": f"{S0} {S1}"}]}), log)
    s0, s1 = doc.sentence("s0000"), doc.sentence("s0001")
    assert r.sentence_ids == ("s0000", "s0001") and r.source_span == (s0.start, s1.end)
    assert r.raw_text == f"{S0} {S1}" and (r.subject_mention_id, r.object_mention_id) == ("M1", "M2")
    [rec] = log.records
    assert (rec.status, rec.matched_sentence_ids, rec.assigned_sentence_id) == ("spanning", ["s0000", "s0001"], None)
    assert log.summary()["spanning"] == 1


def fact_with(evidence):
    return FakeLLM(facts={"facts": [{"entity": "M1", "property": "status", "value": "x", "evidence": evidence}]})


def test_spanning_evidence_keeps_the_original_gap_across_a_paragraph_break():
    doc, [chunk] = setup(f"{S0}\n\n{S1}")
    ms = mentions_for(doc, chunk)
    [f] = extract_facts(chunk, doc, ms, fact_with("Silver Haven.\n\nBob was"))
    assert f.sentence_ids == ("s0000", "s0001")
    for altered in (f"Silver Haven. Bob was", f"Silver Haven.\nBob was"):       # the gap is not normalized
        with pytest.raises(StageError, match="does not occur verbatim"):
            extract_facts(chunk, doc, ms, fact_with(altered))


def test_spanning_never_includes_a_context_sentence():
    doc, chunks = setup(TEXT, max_chars=60, overlap_sentences=1)
    assert chunks[1].overlap_sentence_ids == ("s0001",) and "s0002" in chunks[1].new_sentence_ids
    ms = extract_mentions(chunks[1], doc, IdCounters(), FakeLLM(entities={"mentions": [m("Alice")]}))
    with pytest.raises(StageError, match="does not occur verbatim"):
        extract_facts(chunks[1], doc, ms, fact_with(f"{S1} {S2}"))


def test_repeated_spanning_evidence_is_ambiguous_and_falls_back_to_the_chunk():
    doc, [chunk] = setup("Run. Now. Run. Now.")
    ms = extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m("Run", "other")]}))
    [f] = extract_facts(chunk, doc, ms, fact_with("Run. Now"))
    assert f.sentence_ids == tuple(chunk.sentence_ids) and f.entity_mention_id == ms[0].id


# ============================================================================ Phase 7.1b: partial acceptance
@pytest.fixture
def partial(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_PARTIAL_STAGE", True)


def test_partial_mode_is_off_by_default_and_strict_mode_is_unchanged():
    assert settings.ALLOW_PARTIAL_STAGE is False
    doc, chunk = one()
    with pytest.raises(StageError):
        extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m("Alice"), m("Zed")]}))


def test_partial_mode_drops_invalid_items_keeps_valid_ones_and_logs_each_reason(partial, caplog):
    doc, chunk = one()
    log = GroundingLog()
    payload = {"mentions": [m("Zed"), m("Alice"), m("He"), m("Bob", "person"), m("Bob")]}
    with caplog.at_level(logging.INFO, logger="app.pipeline.stages"):
        ms = extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities=payload), log)
    assert [(x.id, x.text) for x in ms] == [("M1", "Alice"), ("M2", "Bob"), ("M3", "Bob"), ("M4", "Alice")]
    assert log.stages["entities"] == {"mode": "partial", "items": 5, "valid": 2, "invalid": 3, "dropped": 3,
                                      "unmatched_evidence": 1, "failed": False}
    assert (f"stage entities {chunk.id}: mode=partial items=5 valid=2 invalid=3 dropped=3 unmatched_evidence=1 -> ok"
            in caplog.text)
    assert "dropped $.mentions[0]: $.mentions[0].text: 'Zed' does not occur in any sentence" in caplog.text
    assert "dropped $.mentions[2]: $.mentions[2].text: 'He' is a pronoun" in caplog.text
    assert "dropped $.mentions[3]: $.mentions[3].type: 'person' is not one of" in caplog.text


def test_partial_mode_still_fails_when_no_valid_item_remains(partial):
    doc, chunk = one()
    with pytest.raises(StageError, match="no valid item remains"):
        extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m("Zed")]}))


@pytest.mark.parametrize("payload", [{}, {"mentions": "x"}, "not json"])
def test_partial_mode_still_fails_on_structural_errors(partial, payload):
    doc, chunk = one()
    with pytest.raises(StageError):
        extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities=payload))


def test_partial_mode_empty_output_is_still_valid(partial):
    doc, chunk = one()
    assert extract_relationships(chunk, doc, mentions_for(doc, chunk), FakeLLM(relationships={"relationships": []})) == []


def test_partial_mode_keeps_valid_relationships_and_facts_after_an_invalid_one(partial):
    doc, chunk = one()
    ms = mentions_for(doc, chunk)
    rels = extract_relationships(chunk, doc, ms, FakeLLM(relationships={"relationships": [
        {"subject": "M1", "predicate": "knows", "object": "M9", "evidence": S0}, RELS["relationships"][0]]}))
    assert [(r.subject_mention_id, r.object_mention_id) for r in rels] == [("M1", "M2")]
    facts = extract_facts(chunk, doc, ms, FakeLLM(facts={"facts": [
        {"entity": "M2", "property": "age", "value": "30", "kind": "bogus", "evidence": S1}, FACTS["facts"][0]]}))
    assert [(f.entity_mention_id, f.property) for f in facts] == [("M4", "age")]


def test_partial_mode_drops_temporal_relations_to_dropped_events(partial):
    doc, chunk = one()
    payload = {"events": [EVENTS["events"][0], {**EVENTS["events"][1], "trigger": "departed"}],
               "temporal_relations": EVENTS["temporal_relations"]}
    events, temporal = extract_events(chunk, doc, mentions_for(doc, chunk), IdCounters(), FakeLLM(events=payload))
    assert [e.trigger for e in events] == ["met"] and temporal == []


def test_temporal_relation_to_an_invalid_event_is_reported_in_strict_mode_too():
    doc, chunk = one()
    payload = {"events": [EVENTS["events"][0], {**EVENTS["events"][1], "trigger": "departed"}],
               "temporal_relations": EVENTS["temporal_relations"]}
    with pytest.raises(StageError) as exc:
        extract_events(chunk, doc, mentions_for(doc, chunk), IdCounters(), FakeLLM(events=payload))
    assert "$.temporal_relations[0].target: 'e2' refers to an invalid event" in exc.value.errors


def test_partial_mode_passes_through_the_orchestrator_pipeline(partial):
    doc, chunk = one()
    llm = full_llm(events={"events": [EVENTS["events"][0], {"id": "e2", "type": "X", "trigger": "gone",
                                                              "evidence": S2}]})
    log = GroundingLog()
    r = extract_chunk_split(chunk, doc, IdCounters(), 1, llm, log)
    assert [e.trigger for e in r.events] == ["met"] and log.stages["events"]["dropped"] == 1
    assert set(log.stages) == {"entities", "relationships", "events", "facts"}


def test_stage_stats_are_logged_in_strict_mode_before_the_failure(caplog):
    doc, chunk = one()
    with caplog.at_level(logging.INFO, logger="app.pipeline.stages"):
        with pytest.raises(StageError):
            extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities={"mentions": [m("Alice"), m("Zed")]}))
    assert f"stage entities {chunk.id}: mode=strict items=2 valid=1 invalid=1 dropped=0 unmatched_evidence=1 -> FAILED" in caplog.text
    assert "invalid $.mentions[1]: $.mentions[1].text: 'Zed' does not occur in any sentence of this chunk" in caplog.text


# ============================================================================ Phase 7.1b: stage 3 prompt
def test_stage3_prompt_constrains_triggers_and_participants():
    text = (pathlib.Path(extractor_module.__file__).parent / "prompts" / "stages" / "stage3_events.txt").read_text()
    for needle in ("1 to 3 words", "NEVER a full sentence", '"said"', "at least one participant",
                   "must occur inside the\n  evidence"):
        assert needle in text
    assert "The list may be empty" not in text


# ============================================================================ output schemas (constrained generation)
def test_each_stage_sends_a_schema_with_chunk_labels_closed_vocabularies_evidence_first_and_a_cap():
    doc, chunk = one()
    llm = full_llm()
    extract_chunk_split(chunk, doc, IdCounters(), 1, llm)
    schema = dict(zip(llm.calls, llm.schemas))
    item = lambda stage, key: schema[stage]["properties"][key]["items"]
    labels = ["M1", "M2", "M3"]                         # one per distinct name: Alice, Bob, Silver Haven
    assert all(schema[s]["properties"][k]["maxItems"] == item_cap(chunk) == 8 for s, k in
               [("entities", "mentions"), ("relationships", "relationships"), ("events", "events"), ("facts", "facts")])
    assert item("entities", "mentions")["properties"]["type"]["enum"] == ["character", "location", "object",
                                                                          "organization", "other"]
    rel, event, fact = item("relationships", "relationships"), item("events", "events"), item("facts", "facts")
    assert rel["properties"]["subject"]["enum"] == rel["properties"]["object"]["enum"] == labels
    assert event["properties"]["participants"]["items"]["properties"]["mention"]["enum"] == labels
    assert fact["properties"]["entity"]["enum"] == labels and "FEEL" not in event["properties"]["type"]["enum"]
    assert list(rel["properties"])[0] == list(fact["properties"])[0] == "evidence"
    assert list(event["properties"]).index("evidence") < list(event["properties"]).index("trigger")
    assert all(i["required"] == list(i["properties"]) for i in (rel, event, fact))


@pytest.mark.parametrize("stage, payload, error", [
    ("relationships", {"relationships": [{"subject": "M1", "predicate": "FATHER_OF", "object": "M2", "evidence": S0}]},
     "$.relationships[0].predicate: 'FATHER_OF' is not one of"),
    ("events", {"events": [{"id": "e1", "type": "FEEL", "trigger": "met", "evidence": S0}]},
     "$.events[0].type: 'FEEL' is not one of"),
    ("events", {"events": [{"id": "e1", "type": "MEETING", "trigger": "met", "evidence": S0,
                            "participants": [{"mention": "M1", "role": "speaker"}]}]},
     "$.events[0].participants[0].role: 'speaker' is not one of"),
    ("events", {"events": [{"id": "e1", "type": "MEETING", "trigger": "met", "evidence": S0},
                           {"id": "e2", "type": "DEPARTURE", "trigger": "left", "evidence": S2}],
                "temporal_relations": [{"source": "e1", "relation": "CAUSES", "target": "e2"}]},
     "$.temporal_relations[0].relation: 'CAUSES' is not one of"),
    ("facts", {"facts": [{"entity": "M2", "property": "sound", "value": "loud", "evidence": S1}]},
     "$.facts[0].property: 'sound' is not one of"),
])
def test_values_outside_the_closed_vocabularies_are_rejected_without_a_schema(stage, payload, error):
    # providers other than Ollama ignore the schema, so validation enforces the same vocabularies
    doc, chunk = one()
    with pytest.raises(StageError) as exc:
        extract_chunk_split(chunk, doc, IdCounters(), 1, full_llm(**{stage: payload}))
    assert exc.value.stage == stage and any(e.startswith(error) for e in exc.value.errors)


def test_a_list_that_hits_the_cap_is_logged(caplog):
    doc, chunk = one()
    names = {"mentions": [m("Alice")] * item_cap(chunk)}          # a repetition loop cut off by maxItems
    with caplog.at_level(logging.WARNING, logger="app.pipeline.stages"):
        extract_mentions(chunk, doc, IdCounters(), FakeLLM(entities=names))
    assert f"stage entities {chunk.id}: $.mentions hit the cap of 8 items" in caplog.text
