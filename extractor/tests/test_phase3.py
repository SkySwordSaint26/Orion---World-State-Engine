import torch

from extractor.coref import link, merge, naming_links, strip_position_ids
from extractor.evaluate import coreference_b3
from extractor.pipeline import LISTS


def at(text, s, nth=0):
    i = -1
    for _ in range(nth + 1):
        i = text.index(s, i + 1)
    return (i, i + len(s))


def mention(text, mid, s, t, nth=0, kind="nominal"):
    a, b = at(text, s, nth)
    return {"mention_id": mid, "text": s, "type": t, "mention_kind": kind, "start": a, "end": b}


def doc(text, mentions, clusters=()):
    return {"text": text, **{k: [] for k in LISTS}, "mentions": mentions,
            "coreference_clusters": [{"cluster_id": f"C{i}", "mentions": c} for i, c in enumerate(clusters, 1)]}


def test_link_adds_typed_pronouns_and_skips_untypable_or_orphan_chains():
    t = "Dan left the station. He took his phone. It rang. It was late."
    d = doc(t, [mention(t, "M1", "Dan", "character"), mention(t, "M2", "station", "location"),
                mention(t, "M3", "phone", "object")])
    link(d, [[at(t, "Dan"), at(t, "He"), at(t, "his")],   # pronouns typed from the named mention
             [at(t, "phone"), at(t, "It")],               # "It" joins the phone: typed object
             [at(t, "It", 1), at(t, "late")],             # "it"-only chain, nothing to type it by: skipped
             [at(t, "station")]])                         # a single mention is no cluster
    texts = {m["mention_id"]: (m["text"], m["type"], m["mention_kind"]) for m in d["mentions"]}
    assert [[texts[m][0] for m in c["mentions"]] for c in d["coreference_clusters"]] == [["Dan", "He", "his"],
                                                                                          ["phone", "It"]]
    assert texts["M4"] == ("He", "character", "pronominal") and texts["M6"] == ("It", "object", "pronominal")
    assert len(d["mentions"]) == 6                        # no orphan pronoun from the skipped chains


def test_merge_joins_repeats_and_existing_clusters_but_not_other_types():
    t = "trees and trees near the trees; the Trees shop."
    d = doc(t, [mention(t, "M1", "trees", "other"), mention(t, "M2", "trees", "other", 1),
                mention(t, "M3", "trees", "other", 2), mention(t, "M4", "Trees", "organization", kind="proper")],
            [["M2", "M3"]])
    merge(d)
    assert [c["mentions"] for c in d["coreference_clusters"]] == [["M1", "M2", "M3"]]


def test_strip_position_ids_removes_only_the_stale_buffer(tmp_path):
    path = tmp_path / "x.model"
    torch.save({"bert.embeddings.position_ids": torch.arange(3), "bert.w": torch.ones(2)}, path)
    strip_position_ids(tmp_path)
    assert list(torch.load(path)) == ["bert.w"]


def test_linked_only_b3_ignores_predicted_mentions_the_gold_did_not_annotate():
    t = "Dan met Dan by the desk."
    dans = [mention(t, "M1", "Dan", "character"), mention(t, "M2", "Dan", "character", 1)]
    gold = doc(t, dans, [["M1", "M2"]])
    pred = doc(t, dans + [mention(t, "M3", "desk", "object")], [["M1", "M2", "M3"]])
    assert coreference_b3(pred, gold)["precision"] < 1 and coreference_b3(pred, gold, linked_only=True)["f1"] == 1.0


def test_a_name_introduced_with_my_name_is_joins_the_speaker():
    t = "My name is Evelyn. I work here. His name's Daniel."
    kinds = {"My": "pronominal", "Evelyn": "proper", "I": "pronominal", "His": "pronominal", "Daniel": "proper"}
    d = doc(t, [mention(t, f"M{i}", s, "character", kind=k) for i, (s, k) in enumerate(kinds.items(), 1)], [["M1", "M3"]])
    assert naming_links(d) == [("M1", "M2"), ("M4", "M5")]
    merge(d, naming_links(d))
    assert sorted(sorted(c["mentions"]) for c in d["coreference_clusters"]) == [["M1", "M2", "M3"], ["M4", "M5"]]


def test_this_is_x_names_the_narrator():
    t = "I work here. I sing. This is Evelyn from 104.6 F.M. This is Pinehaven."
    ms = [mention(t, "M1", "I", "character", kind="pronominal"), mention(t, "M2", "I", "character", 1, "pronominal"),
          mention(t, "M3", "Evelyn", "character", kind="proper"), mention(t, "M4", "Pinehaven", "location", kind="proper")]
    assert naming_links(doc(t, ms, [["M1", "M2"]])) == [("M1", "M3")]
