from extractor import relations as R
from extractor.mentions import spacy_nlp
from extractor.pipeline import LISTS

TEXT = "My name is Evelyn. I am Twenty four and work for my boss. Dan left. Evelyn and Dan are friends."


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
        work = "I am Twenty four and work for my boss."
        return {"relationships": [{"subject": "I", "relation": "works_for", "object": "boss", "evidence": work},
                                  {"subject": "Evelyn", "relation": "friend_of", "object": "my",    # same entity
                                   "evidence": "My name is Evelyn."},
                                  {"subject": "Dan", "relation": "sister_of", "object": "boss"},    # not a predicate
                                  {"subject": "Dan", "relation": "married_to", "object": "boss",    # no quote
                                   "evidence": None},
                                  {"subject": "Dan", "relation": "enemy_of", "object": "Evelyn",    # no cue word
                                   "evidence": "Evelyn and Dan are friends."},
                                  {"subject": "Dan", "relation": "works_for", "object": "boss",     # Dan not in it
                                   "evidence": work}]}

    monkeypatch.setattr(R, "generate", fake)
    d = doc()
    R.relations(d)
    assert d["facts"] == [{"fact_id": "F1", "property": "age", "entity_mention_id": "M2", "value": "Twenty four"}]
    assert d["relationships"] == [{"relationship_id": "R1", "predicate": "WORKS_FOR", "subject_mention_id": "M2",
                                   "object_mention_id": "M4"}]
    assert prompts[0].startswith("# Template:\n{") and prompts[0].endswith(f"# Context:\n{TEXT}")
    assert "# Examples:" in prompts[0] and '"relationships"' in prompts[1]


def test_canonical_folds_symmetric_and_inverse_relations():
    assert R.canonical("B", "FRIEND_OF", "A") == R.canonical("A", "FRIEND_OF", "B") == ("A", "FRIEND_OF", "B")
    assert R.canonical("kid", "CHILD_OF", "mom") == ("mom", "PARENT_OF", "kid")
    assert R.canonical("B", "WORKS_FOR", "A") == ("B", "WORKS_FOR", "A")          # directed: unchanged


def test_reversed_symmetric_relationships_are_extracted_once_and_scored_as_matches(monkeypatch):
    from extractor.evaluate import score
    quote = "Evelyn and Dan are friends."
    rels = [{"subject": "Evelyn", "relation": "friend_of", "object": "Dan", "evidence": quote},
            {"subject": "Dan", "relation": "friend_of", "object": "Evelyn", "evidence": quote}]
    monkeypatch.setattr(R, "generate", lambda s, u, f: {"people": []} if '"people"' in u else {"relationships": rels})
    pred = doc()
    R.relations(pred)
    assert [(r["subject_mention_id"], r["object_mention_id"]) for r in pred["relationships"]] == [("M2", "M6")]
    gold = doc()
    gold["relationships"] = [{"relationship_id": "R1", "subject_mention_id": "M6", "predicate": "FRIEND_OF",
                              "object_mention_id": "M2"}]
    s = score(pred, gold)
    assert s["relationships"]["f1"] == 0.0 and s["relationships_entity"]["f1"] == 1.0   # backend: direction-bound


def test_possessive_role_nouns_become_relationships_with_a_new_mention_when_missing():
    t = "Dan’s mother called. My boss left."
    ms = [{"mention_id": "M1", "text": "Dan", "type": "character", "mention_kind": "proper", "start": 0, "end": 3},
          {"mention_id": "M2", "text": "My", "type": "character", "mention_kind": "pronominal", "start": 21, "end": 23},
          {"mention_id": "M3", "text": "boss", "type": "character", "mention_kind": "nominal", "start": 24, "end": 28}]
    d = {"text": t, **{k: [] for k in LISTS}, "mentions": ms}
    assert R.role_pairs(d, spacy_nlp()(t)) == [("M4", "PARENT_OF", "M1"), ("M2", "WORKS_FOR", "M3")]
    assert d["mentions"][-1]["text"] == "Dan’s mother" and d["mentions"][-1]["type"] == "character"


def test_a_role_noun_in_apposition_points_at_the_named_person():
    t = "Mara's brother, Tobias Quinn, was a fisherman. Lily Quinn, Mara's daughter, smiled."
    ms = [{"mention_id": f"M{i}", "text": s, "type": "character", "mention_kind": "proper", "start": t.index(s),
           "end": t.index(s) + len(s)} for i, s in enumerate(["Mara", "Tobias Quinn", "Lily Quinn"], 1)]
    ms.append({**ms[0], "mention_id": "M4", "start": t.index("Mara", 1), "end": t.index("Mara", 1) + 4})
    d = {"text": t, **{k: [] for k in LISTS}, "mentions": ms}
    assert R.role_pairs(d, spacy_nlp()(t)) == [("M1", "SIBLING_OF", "M2"), ("M4", "PARENT_OF", "M3")]
    assert len(d["mentions"]) == 4                         # no "Mara's brother" mention invented


def test_answer_names_match_mentions_without_a_leading_article_or_title():
    assert R.name_key(" The Harbor Council") == R.name_key("harbor council") == "harbor council"
    assert R.name_key("Doctor Hanna Weiss") == R.name_key("Dr. Hanna Weiss") == "hanna weiss"
    assert R.name_key("Theo") == "theo"                    # only a whole leading word is dropped


def test_titles_before_a_name_become_facts_but_honorifics_do_not():
    t = "Doctor Hanna Weiss waved. Captain Elias Brandt left. Mr. Hale and Dr. Ross stayed. Captain Ahab"
    names = ["Hanna Weiss", "Captain Elias Brandt", "Hale", "Ross", "Ahab"]
    ms = [{"mention_id": f"M{i}", "text": n, "type": "character", "mention_kind": "proper", "start": t.index(n),
           "end": t.index(n) + len(n)} for i, n in enumerate(names, 1)]
    ms.append({**ms[0], "mention_id": "M6", "type": "location"})                  # not a character: no fact
    assert R.title_facts({"text": t, "mentions": ms}) == [
        ("M1", "occupation", "doctor"), ("M2", "title", "Captain"), ("M4", "occupation", "doctor"),
        ("M5", "title", "Captain")]


def test_fact_values_are_checked_per_property():
    t = ("I let him give the weather forecast. His moppy dark hair flew. This is Evelyn with 104.6 F.M. "
         "I applied for a radio DJ position. I tend to my new coworker. He is recovering. A bird with human eyes. "
         "Hanna examined the body. She brought bread from the bakery. She worked as a nurse.")
    parsed = spacy_nlp()(t)
    value = lambda prop, s: R.fact_value(prop, parsed.char_span(t.index(s), t.index(s) + len(s)))
    assert value("occupation", "weather") is None                     # cut from "weather forecast"
    assert value("occupation", "radio DJ") == "radio DJ"              # ... unless the noun is a job noun
    assert value("hair_color", "moppy dark") == "dark"
    assert value("eye_color", "human") is None
    assert value("location", "104.6 F.M.") is None
    assert value("occupation", "coworker") is None
    assert value("occupation", "examined the body") is None           # an action, not a job
    assert value("occupation", "bakery") is None                      # where the bread came from
    assert value("occupation", "nurse") == "nurse"                    # "worked as a nurse"
    assert value("status", "recovering") == "recovering"
