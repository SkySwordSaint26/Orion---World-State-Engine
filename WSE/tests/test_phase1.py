from wse.evaluate import coreference_b3, micro, score
from wse.pipeline import LISTS, extract

TEXT = "Alice met Bob. She saw Alice and Bob."


def mention(mid, text, nth=0, kind="proper"):
    start = -1
    for _ in range(nth + 1):
        start = TEXT.index(text, start + 1)
    return {"mention_id": mid, "text": text, "type": "character", "start": start, "end": start + len(text),
            "mention_kind": kind}


def doc(mentions, clusters):
    return {"text": TEXT, **{k: [] for k in LISTS}, "mentions": mentions,
            "coreference_clusters": [{"cluster_id": f"C{i}", "mentions": c} for i, c in enumerate(clusters, 1)]}


GOLD = doc([mention("M1", "Alice"), mention("M2", "Bob"), mention("M3", "Alice", 1), mention("M4", "Bob", 1)],
           [["M1", "M3"], ["M2", "M4"]])


def test_b3_is_perfect_for_identical_clusters_even_with_other_mention_ids():
    pred = doc([mention("M7", "Alice"), mention("M8", "Alice", 1), mention("M9", "Bob"), mention("M5", "Bob", 1)],
               [["M7", "M8"], ["M9", "M5"]])
    assert coreference_b3(pred, GOLD)["f1"] == 1.0


def test_b3_merging_two_entities_keeps_recall_and_halves_precision():
    pred = doc(GOLD["mentions"], [["M1", "M2", "M3", "M4"]])
    b3 = coreference_b3(pred, GOLD)
    assert (b3["precision"], b3["recall"], b3["f1"]) == (0.5, 1.0, 0.6667)


def test_pronouns_are_counted_but_never_scored():
    she = mention("M6", "She", kind="pronominal")
    pred = doc(GOLD["mentions"] + [she], [["M1", "M3", "M6"], ["M2", "M4"]])
    s = score(pred, GOLD)
    assert s["pronouns_predicted"] == 1 and s["mentions_exact"]["f1"] == 1.0 and s["coreference_b3"]["f1"] == 1.0
    assert micro([s, s])["coreference_b3"]["f1"] == 1.0


def test_an_empty_extraction_is_a_schema_valid_document(monkeypatch):
    monkeypatch.setattr("wse.pipeline.STAGES", ())
    out = extract("story", TEXT)
    assert out["text"] == TEXT and all(out[k] == [] for k in LISTS)


def test_b3_gives_nothing_for_an_empty_prediction():
    b3 = coreference_b3(doc([], []), GOLD)
    assert (b3["precision"], b3["recall"], b3["f1"]) == (0.0, 0.0, 0.0)


def test_gold_cluster_members_without_a_mention_are_left_out_and_counted():
    gold = {**GOLD, "coreference_clusters": GOLD["coreference_clusters"] + [{"cluster_id": "C9", "mentions": ["M1", "M99"]}]}
    gold["coreference_clusters"][0] = {"cluster_id": "C1", "mentions": ["M1", "M3", "M98"]}
    b3 = coreference_b3(GOLD, gold)
    assert b3["f1"] == 1.0 and b3["gold_missing"] == 2


def test_items_without_offsets_score_as_unmatched_instead_of_crashing():
    pred = doc([{"mention_id": "M1", "text": "Alice", "type": "character"}], [])
    pred["events"] = [{"event_id": "E1", "type": "OTHER", "trigger": "met", "participants": []}]
    pred["relationships"] = [{"relationship_id": "R1", "predicate": "KNOWS", "subject_mention_id": "M1"}]
    s = score(pred, GOLD)
    assert s["mentions_exact"]["tp"] == 0 and s["event_arguments_entity"]["f1"] == 0.0
    assert s["relationships_entity"]["fp"] == 1
