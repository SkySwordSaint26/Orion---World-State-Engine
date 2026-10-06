"""Evaluation tooling: annotation -> gold conversion, and scoring predictions against the gold."""
import copy
import json
import pathlib

import pytest

from app.evaluation import convert_annotation, micro_average, schema_errors, score_document, span_problem
from app.evaluation.__main__ import main
from app.evaluation.schema import SCHEMA_PATH, load_schema

pytestmark = pytest.mark.skipif(not SCHEMA_PATH.exists(), reason="orion_gold_v1.schema.json not present")

TEXT = "Evelyn works at the broadcast station. Dan visited Evelyn on Monday. Rose called."


def at(word, nth=0):
    i = -1
    for _ in range(nth + 1):
        i = TEXT.index(word, i + 1)
    return i, i + len(word)


def ann():
    """A small annotation in the teammate export format."""
    def m(mid, word, mtype="character", nth=0):
        s, e = at(word, nth)
        return {"text": word, "start_offset": s, "end_offset": e, "mention_id": mid, "type": mtype}
    vs, ve = at("visited")
    ts, te = at("Monday")
    return {
        "story_id": "story_1", "source_file": "Story [Part 1].txt",
        "entity_mentions": [m("M001", "Evelyn"), m("M002", "broadcast station", "location"), m("M003", "Dan"),
                            m("M004", "Evelyn", nth=1), m("M005", "Rose")],
        "coreference_clusters": [{"cluster_id": "C001", "mentions": ["M001", "M004"]},
                                 {"cluster_id": "C002", "mentions": ["M005"]}],
        "events": [{"event_id": "E001", "type": "ARRIVAL", "trigger": {"text": "visited", "start_offset": vs,
                                                                      "end_offset": ve},
                    "participants": [{"role": "agent", "mention_id": "M003"},
                                     {"role": "target", "mention_id": "M004"}]}],
        "relationships": [{"relationship_id": "R001", "subject_mention_id": "M001", "predicate": "WORKS_FOR",
                           "object_mention_id": "M002"}],
        "facts": [{"fact_id": "F001", "entity_mention_id": "M001", "property": "occupation", "value": "Radio DJ"}],
        "temporal": [{"temporal_id": "T001", "expression": "Monday", "start_offset": ts, "end_offset": te}],
        "temporal_relations": [],
        "review_notes": ["a note"],
    }


def gold():
    doc, _ = convert_annotation(ann(), TEXT)
    return doc


# ============================================================================ conversion
def test_conversion_renames_fields_into_a_schema_valid_gold_document():
    doc, issues = convert_annotation(ann(), TEXT)
    assert schema_errors(doc) == [] and not [i for i in issues if i.startswith("schema:")]
    assert doc["schema_version"] == "1.0" and doc["text"] == TEXT and doc["title"] == "Story [Part 1]"
    assert doc["mentions"][0] == {"mention_id": "M001", "text": "Evelyn", "type": "character", "start": 0, "end": 6}
    e = doc["events"][0]
    assert (e["trigger"], TEXT[e["start"]:e["end"]]) == ("visited", "visited")
    assert doc["temporal_expressions"] == [{"temporal_id": "T001", "text": "Monday", "type": "other",
                                            "start": at("Monday")[0], "end": at("Monday")[1]}]


def test_conversion_reports_every_change_it_makes():
    _, issues = convert_annotation(ann(), TEXT)
    assert any(i.startswith("C002: dropped") for i in issues)                     # singleton cluster
    assert "1 temporal expression(s) have no annotated type; set to 'other'" in issues
    assert "'review_notes' is not part of the schema; dropped" in issues
    assert "'source_file' is not part of the schema; dropped" in issues


def test_conversion_flags_but_never_moves_a_span_that_cuts_through_a_word():
    a = ann()
    s = TEXT.index("road")                                                        # inside "broadcast"
    a["entity_mentions"].append({"text": "road", "start_offset": s, "end_offset": s + 4, "mention_id": "M006",
                                 "type": "location"})
    doc, issues = convert_annotation(a, TEXT)
    assert doc["mentions"][-1]["start"] == s                                     # kept as annotated
    assert any(i.startswith("M006: span") and "cuts through a word" in i for i in issues)


def test_conversion_reports_spans_annotated_twice():
    a = ann()
    a["events"].append(copy.deepcopy(a["events"][0]) | {"event_id": "E002"})
    doc, issues = convert_annotation(a, TEXT)
    assert len(doc["events"]) == 2
    s, e = at("visited")
    assert f"E001, E002: same event trigger span ({s}, {e}) 'visited' annotated 2 times" in issues


def test_a_gold_span_annotated_twice_counts_once():
    g = gold()
    g["events"].append(copy.deepcopy(g["events"][0]) | {"event_id": "E002"})
    s = score_document(gold(), g)
    assert s["triggers_exact"]["f1"] == 1.0 and s["triggers_typed"]["f1"] == 1.0


@pytest.mark.parametrize("start,end,expected,problem", [
    (0, 6, "Evelyn", None),
    (0, 5, "Evely", "cuts through a word"),
    (0, 6, "Evelyn!", "not 'Evelyn!'"),
    (80, 99, "x", "outside the text"),
])
def test_span_problem(start, end, expected, problem):
    got = span_problem(TEXT, start, end, expected)
    assert got is None if problem is None else problem in got


# ============================================================================ scoring
def test_gold_scored_against_itself_is_perfect_on_every_metric():
    s = score_document(gold(), gold())
    for metric in ("mentions_exact", "mentions_typed", "mentions_overlap", "mention_texts", "triggers_exact",
                   "triggers_typed", "event_arguments", "relationships", "facts", "temporal_expressions"):
        assert (s[metric]["precision"], s[metric]["recall"], s[metric]["f1"]) == (1.0, 1.0, 1.0), metric


def test_an_empty_prediction_has_zero_recall_and_no_false_positives():
    empty = {"text": TEXT, "mentions": [], "events": [], "relationships": [], "facts": [], "temporal_expressions": []}
    s = score_document(empty, gold())
    assert s["mentions_exact"] == {"tp": 0, "fp": 0, "fn": 5, "precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_boundary_difference_fails_exact_but_passes_overlap():
    pred = gold()
    m = next(x for x in pred["mentions"] if x["text"] == "broadcast station")
    m.update(text="the broadcast station", start=m["start"] - 4)
    s = score_document(pred, gold())
    assert (s["mentions_exact"]["tp"], s["mentions_exact"]["fp"], s["mentions_exact"]["fn"]) == (4, 1, 1)
    assert s["mentions_overlap"]["f1"] == 1.0
    assert s["relationships"]["f1"] == 1.0              # relationships align mentions by overlap, not exact span


def test_mention_texts_ignore_offsets_and_count_distinct_strings():
    pred = gold()
    for m in pred["mentions"]:
        m.pop("start"), m.pop("end")
    pred["mentions"].append({"mention_id": "M9", "text": "evelyn", "type": "character"})
    s = score_document(pred, gold())
    assert s["mentions_exact"]["tp"] == 0
    assert (s["mention_texts"]["tp"], s["mention_texts"]["fp"], s["mention_texts"]["fn"]) == (4, 1, 0)


def test_wrong_type_counts_for_exact_but_not_typed():
    pred = gold()
    pred["mentions"][1]["type"] = "object"
    s = score_document(pred, gold())
    assert s["mentions_exact"]["f1"] == 1.0 and s["mentions_typed"]["tp"] == 4


def test_mentions_without_offsets_are_false_positives_and_counted():
    pred = gold()
    pred["mentions"].append({"mention_id": "M99", "text": "Rose", "type": "character"})
    s = score_document(pred, gold())
    assert s["mentions_exact"]["fp"] == 1 and s["pred_unanchored"]["mentions"] == 1


def test_relationships_are_scored_per_entity_through_coreference():
    pred = gold()
    pred["relationships"][0]["subject_mention_id"] = "M004"   # the other "Evelyn" mention, same cluster C001
    assert score_document(pred, gold())["relationships"]["f1"] == 1.0
    pred["relationships"][0]["subject_mention_id"] = "M003"   # Dan: a different entity
    s = score_document(pred, gold())["relationships"]
    assert (s["tp"], s["fp"], s["fn"]) == (0, 1, 1)


def test_relationship_to_a_mention_the_gold_does_not_have_can_never_match():
    pred = gold()
    pred["mentions"].append({"mention_id": "M50", "text": "Monday", "type": "other",
                             "start": at("Monday")[0], "end": at("Monday")[1]})
    pred["relationships"].append({"relationship_id": "R9", "subject_mention_id": "M50", "predicate": "KNOWS",
                                  "object_mention_id": "M001"})
    s = score_document(pred, gold())["relationships"]
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 0)


def test_fact_values_compare_case_and_whitespace_insensitively():
    pred = gold()
    pred["facts"][0]["value"] = "  radio   dj "
    assert score_document(pred, gold())["facts"]["f1"] == 1.0


def test_event_arguments_need_the_aligned_event_role_and_participant():
    pred = gold()
    pred["events"][0]["participants"][1]["role"] = "patient"
    s = score_document(pred, gold())["event_arguments"]
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 1)


def test_gold_spans_that_cut_through_words_are_excluded_from_the_gold():
    a = ann()
    s = TEXT.index("road")
    a["entity_mentions"].append({"text": "road", "start_offset": s, "end_offset": s + 4, "mention_id": "M006",
                                 "type": "location"})
    g, _ = convert_annotation(a, TEXT)
    sc = score_document(gold(), g)
    assert sc["gold_excluded"]["mentions"] == 1 and sc["mentions_exact"]["recall"] == 1.0


def test_different_texts_are_refused():
    pred = copy.deepcopy(gold())
    pred["text"] = TEXT + " "
    with pytest.raises(ValueError, match="different texts"):
        score_document(pred, gold())


def test_micro_average_sums_counts_before_dividing():
    a = score_document(gold(), gold())
    empty = {"text": TEXT, "mentions": [], "events": [], "relationships": [], "facts": [], "temporal_expressions": []}
    b = score_document(empty, gold())
    total = micro_average([a, b])
    assert (total["mentions_exact"]["tp"], total["mentions_exact"]["fn"]) == (5, 5)
    assert total["mentions_exact"]["precision"] == 1.0 and total["mentions_exact"]["recall"] == 0.5


# ============================================================================ command line
def test_cli_convert_then_score_round_trip(tmp_path, capsys):
    (tmp_path / "texts").mkdir()
    (tmp_path / "texts" / "Story [Part 1].txt").write_text(TEXT, encoding="utf-8")
    (tmp_path / "ann.json").write_text(json.dumps(ann()), encoding="utf-8")
    assert main(["convert", str(tmp_path / "ann.json"), "--text-dir", str(tmp_path / "texts"),
                 "--out-dir", str(tmp_path / "gold")]) == 0
    assert json.loads((tmp_path / "gold" / "story_1.json").read_text())["text"] == TEXT
    assert "dropped" in (tmp_path / "gold" / "story_1.issues.txt").read_text()
    (tmp_path / "pred").mkdir()
    assert main(["score", str(tmp_path / "gold"), str(tmp_path / "pred"), "--json", str(tmp_path / "s.json")]) == 0
    out = capsys.readouterr().out
    assert "(no prediction)" in out and "MICRO AVERAGE" in out
    assert json.loads((tmp_path / "s.json").read_text())["micro"]["mentions_exact"]["fn"] == 5


@pytest.mark.skipif(not SCHEMA_PATH.exists(), reason="orion_gold_v1.schema.json not present")
def test_vocabulary_constants_match_the_schema_file():
    from app.contracts import gold
    sch = load_schema()
    d = sch["$defs"]
    assert gold.MENTION_TYPES == tuple(d["mention"]["properties"]["type"]["enum"])
    assert gold.MENTION_KINDS == tuple(d["mention"]["properties"]["mention_kind"]["enum"])
    assert gold.EVENT_TYPES == tuple(d["event"]["properties"]["type"]["enum"])
    assert gold.PARTICIPANT_ROLES == tuple(d["eventParticipant"]["properties"]["role"]["enum"])
    assert gold.PREDICATES == tuple(d["relationship"]["properties"]["predicate"]["enum"])
    assert gold.FACT_PROPERTIES == tuple(d["fact"]["properties"]["property"]["enum"])
    assert gold.TEMPORAL_EXPRESSION_TYPES == tuple(d["temporalExpression"]["properties"]["type"]["enum"])
    assert gold.TEMPORAL_RELATIONS == tuple(d["temporalRelation"]["properties"]["relation"]["enum"])
    assert sch["properties"]["schema_version"]["const"] == gold.GOLD_SCHEMA_VERSION


REAL = pathlib.Path(__file__).resolve().parents[3] / "accounts_from_a_lonely_broadcast_station_orion_annotation"


@pytest.mark.skipif(not REAL.exists(), reason="teammate annotation files not present")
def test_real_annotation_files_have_the_expected_export_shape():
    for path in sorted(REAL.glob("*.json")):
        a = json.loads(path.read_text(encoding="utf-8"))
        assert {"story_id", "source_file", "entity_mentions", "events"} <= set(a), path.name
        assert all({"start_offset", "end_offset", "mention_id"} <= set(m) for m in a["entity_mentions"])
