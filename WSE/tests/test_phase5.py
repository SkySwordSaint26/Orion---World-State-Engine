from wse import relations as R
from wse.pipeline import LISTS

TEXT = "My name is Evelyn. I am Twenty four and work for my boss. Dan left."


def mention(mid, s, kind, t="character"):
    i = TEXT.index(s)
    return {"mention_id": mid, "text": s, "type": t, "mention_kind": kind, "start": i, "end": i + len(s)}


def doc():
    ms = [mention("M1", "My", "pronominal"), mention("M2", "Evelyn", "proper"), mention("M3", "I", "pronominal"),
          mention("M4", "boss", "nominal"), mention("M6", "Dan", "proper"), mention("M7", "name", "nominal", "other")]
    return {"text": TEXT, **{k: [] for k in LISTS}, "mentions": ms,
            "coreference_clusters": [{"cluster_id": "C1", "mentions": ["M1", "M2", "M3"]}]}


def test_answers_are_grounded_deduplicated_and_recorded_on_named_mentions(monkeypatch):
    prompts = []

    def fake(system, user, fmt):
        prompts.append(user)
        if '"people"' in user:
            return {"people": [{"name": "I", "age": "twenty four", "occupation": None},     # recorded on Evelyn
                               {"name": "Evelyn", "age": "twenty four"},                   # duplicate
                               {"name": "boss", "age": "24"},                              # value not in the text
                               {"name": "name", "occupation": "Evelyn"},                   # not a character
                               {"name": "Rose", "age": "Dan"}]}                            # no such mention
        return {"relationships": [{"subject": "I", "relation": "works_for", "object": "boss"},
                                  {"subject": "Evelyn", "relation": "friend_of", "object": "my"},   # same entity
                                  {"subject": "Dan", "relation": "sister_of", "object": "boss"}]}   # not a predicate

    monkeypatch.setattr(R, "generate", fake)
    d = doc()
    R.relations(d)
    assert d["facts"] == [{"fact_id": "F1", "property": "age", "entity_mention_id": "M2", "value": "Twenty four"}]
    assert d["relationships"] == [{"relationship_id": "R1", "predicate": "WORKS_FOR", "subject_mention_id": "M2",
                                   "object_mention_id": "M4"}]
    assert prompts[0].startswith("# Template:\n{") and prompts[0].endswith(TEXT) and '"relationships"' in prompts[1]


def test_canonical_folds_symmetric_and_inverse_relations():
    assert R.canonical("B", "FRIEND_OF", "A") == R.canonical("A", "FRIEND_OF", "B") == ("A", "FRIEND_OF", "B")
    assert R.canonical("kid", "CHILD_OF", "mom") == ("mom", "PARENT_OF", "kid")
    assert R.canonical("B", "WORKS_FOR", "A") == ("B", "WORKS_FOR", "A")          # directed: unchanged


def test_reversed_symmetric_relationships_are_extracted_once_and_scored_as_matches(monkeypatch):
    from wse.evaluate import score
    rels = [{"subject": "Evelyn", "relation": "friend_of", "object": "Dan"},
            {"subject": "Dan", "relation": "friend_of", "object": "Evelyn"}]
    monkeypatch.setattr(R, "generate", lambda s, u, f: {"people": []} if '"people"' in u else {"relationships": rels})
    pred = doc()
    R.relations(pred)
    assert [(r["subject_mention_id"], r["object_mention_id"]) for r in pred["relationships"]] == [("M2", "M6")]
    gold = doc()
    gold["relationships"] = [{"relationship_id": "R1", "subject_mention_id": "M6", "predicate": "FRIEND_OF",
                              "object_mention_id": "M2"}]
    s = score(pred, gold)
    assert s["relationships"]["f1"] == 0.0 and s["relationships_entity"]["f1"] == 1.0   # backend: direction-bound
