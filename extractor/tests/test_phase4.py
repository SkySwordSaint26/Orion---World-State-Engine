from extractor import events as E
from extractor.evaluate import score
from extractor.pipeline import LISTS

TEXT = "I ran to the desk and called my boss. Noise."
# word, lemma, POS, dependency, head token, BookNLP event flag
PARSE = [("I", "I", "PRON", "nsubj", 1, "O"), ("ran", "run", "VERB", "ROOT", 1, "EVENT"),
         ("to", "to", "ADP", "prep", 1, "O"), ("the", "the", "DET", "det", 4, "O"),
         ("desk", "desk", "NOUN", "pobj", 2, "O"), ("and", "and", "CCONJ", "cc", 1, "O"),
         ("called", "call", "VERB", "conj", 1, "EVENT"), ("my", "my", "PRON", "poss", 8, "O"),
         ("boss", "boss", "NOUN", "dobj", 6, "O"), (".", ".", "PUNCT", "punct", 1, "O"),
         ("Noise", "noise", "NOUN", "ROOT", 10, "EVENT"), (".", ".", "PUNCT", "punct", 10, "O")]


def tokens(text=TEXT, parse=PARSE):
    out, cursor = [], 0
    for word, lemma, pos, dep, head, event in parse:
        a = text.index(word, cursor)
        cursor = a + len(word)
        out.append({"word": word, "lemma": lemma, "POS_tag": pos, "dependency_relation": dep,
                    "syntactic_head_ID": str(head), "event": event, "byte_onset": str(a), "byte_offset": str(cursor)})
    return out


def mention(mid, s, kind="nominal", t="character", text=TEXT, nth=0):
    a = -1
    for _ in range(nth + 1):
        a = text.index(s, a + 1)
    return {"mention_id": mid, "text": s, "type": t, "mention_kind": kind, "start": a, "end": a + len(s)}


MENTIONS = [mention("M1", "I", "pronominal"), mention("M2", "desk", t="location"), mention("M3", "my", "pronominal"),
            mention("M4", "boss")]


def doc(mentions=MENTIONS, clusters=(), events=()):
    return {"text": TEXT, **{k: [] for k in LISTS}, "mentions": list(mentions), "events": list(events),
            "coreference_clusters": [{"cluster_id": f"C{i}", "mentions": c} for i, c in enumerate(clusters, 1)]}


def test_verb_triggers_typed_by_lexicon_with_dependency_participants(monkeypatch):
    monkeypatch.setattr(E, "booknlp_output", lambda text: (tokens(), []))
    d = doc()
    E.events(d)
    assert [(e["trigger"], e["type"], TEXT[e["start"]:e["end"]], [(p["role"], p["mention_id"]) for p in e["participants"]])
            for e in d["events"]] == [
        ("ran", "OTHER", "ran", [("agent", "M1"), ("location", "M2")]),       # place preposition -> location
        ("called", "CONVERSATION", "called", [("agent", "M1"), ("patient", "M4")])]   # shared subject; "my" skipped
    # "Noise" is a BookNLP event but a noun: not a trigger


def test_conjoined_subjects_people_after_to_a_stated_death_and_saying_nothing(monkeypatch):
    t = ("Mara, Tobias and Lily climbed. Mara said nothing to Hanna. Brandt was dead. Brandt was not dead. "
         "Mara ran to Hanna.")
    parse = [("Mara", "Mara", "PROPN", "nsubj", 5, "O"), (",", ",", "PUNCT", "punct", 0, "O"),
             ("Tobias", "Tobias", "PROPN", "conj", 0, "O"), ("and", "and", "CCONJ", "cc", 2, "O"),
             ("Lily", "Lily", "PROPN", "conj", 2, "O"), ("climbed", "climb", "VERB", "ROOT", 5, "EVENT"),
             (".", ".", "PUNCT", "punct", 5, "O"),
             ("Mara", "Mara", "PROPN", "nsubj", 8, "O"), ("said", "say", "VERB", "ROOT", 8, "EVENT"),
             ("nothing", "nothing", "PRON", "dobj", 8, "O"), ("to", "to", "ADP", "prep", 8, "O"),
             ("Hanna", "Hanna", "PROPN", "pobj", 10, "O"), (".", ".", "PUNCT", "punct", 8, "O"),
             ("Brandt", "Brandt", "PROPN", "nsubj", 14, "O"), ("was", "be", "AUX", "ROOT", 14, "O"),
             ("dead", "dead", "ADJ", "acomp", 14, "O"), (".", ".", "PUNCT", "punct", 14, "O"),
             ("Brandt", "Brandt", "PROPN", "nsubj", 18, "O"), ("was", "be", "AUX", "ROOT", 18, "O"),
             ("not", "not", "PART", "neg", 18, "O"), ("dead", "dead", "ADJ", "acomp", 18, "O"),
             (".", ".", "PUNCT", "punct", 18, "O"),
             ("Mara", "Mara", "PROPN", "nsubj", 23, "O"), ("ran", "run", "VERB", "ROOT", 23, "EVENT"),
             ("to", "to", "ADP", "prep", 23, "O"), ("Hanna", "Hanna", "PROPN", "pobj", 24, "O"),
             (".", ".", "PUNCT", "punct", 23, "O")]
    monkeypatch.setattr(E, "booknlp_output", lambda text: (tokens(t, parse), []))
    ms = [mention(f"M{i}", name, "proper", text=t, nth=nth) for i, (name, nth) in
          enumerate([("Mara", 0), ("Tobias", 0), ("Lily", 0), ("Mara", 1), ("Hanna", 0), ("Brandt", 0), ("Mara", 2),
                     ("Hanna", 1)], 1)]
    d = {"text": t, **{k: [] for k in LISTS}, "mentions": ms}
    E.events(d)
    found = [(e["trigger"], e["type"], [(p["role"], p["mention_id"]) for p in e["participants"]]) for e in d["events"]]
    assert found == [
        ("climbed", "TRAVEL", [("agent", "M1"), ("agent", "M2"), ("agent", "M3")]),   # every conjunct
        ("said", "OTHER", [("agent", "M4"), ("recipient", "M5")]),     # nothing said; "to Hanna" is no place
        ("dead", "DEATH", [("patient", "M6")]),                        # "was not dead": no event
        ("ran", "OTHER", [("agent", "M7"), ("location", "M8")])]       # a movement's goal stays a location


def test_entity_level_arguments_credit_a_pronoun_through_its_cluster():
    gold_event = {"event_id": "E1", "type": "OTHER", "trigger": "ran", "start": 2, "end": 5,
                  "participants": [{"role": "agent", "mention_id": "M9"}]}
    gold = doc([mention("M9", "boss"), mention("M2", "desk")], events=[gold_event])
    pred = doc(clusters=[["M1", "M4"]], events=[{**gold_event, "participants": [{"role": "agent", "mention_id": "M1"}]}])
    s = score(pred, gold)
    assert s["event_arguments"]["f1"] == 0.0 and s["event_arguments_entity"]["f1"] == 1.0


def test_llm_types_is_off_by_default_and_retypes_by_mode(monkeypatch):
    text = "Mara said hello and ran home. She slept."
    event = lambda eid, word, etype: {"event_id": eid, "type": etype, "trigger": word, "start": text.index(word),
                                      "end": text.index(word) + len(word), "participants": []}
    fresh = lambda: {"text": text, "events": [event("E1", "said", "CONVERSATION"), event("E2", "ran", "OTHER"),
                                              event("E3", "slept", "OTHER")]}
    asked = []

    def generate(system, user, schema, num_predict, model):
        asked.append((user, schema["required"], model))
        return {i: "TRAVEL" for i in schema["required"]}

    monkeypatch.setattr(E, "generate", generate)
    doc = fresh()
    E.llm_types(doc)                                                    # ORION_EVENT_LLM unset: no calls
    assert asked == [] and [e["type"] for e in doc["events"]] == ["CONVERSATION", "OTHER", "OTHER"]

    monkeypatch.setattr(E, "EVENT_LLM", "qwen2.5:14b")
    E.llm_types(doc)                                                    # "all": every trigger, one call per sentence
    assert asked == [("Mara [T1 said] hello and [T2 ran] home.", ["T1", "T2"], "qwen2.5:14b"),
                     ("She [T1 slept].", ["T1"], "qwen2.5:14b")]
    assert [e["type"] for e in doc["events"]] == ["TRAVEL", "TRAVEL", "TRAVEL"]

    monkeypatch.setattr(E, "EVENT_LLM_MODE", "other")
    asked.clear()
    doc = fresh()
    E.llm_types(doc)                                                    # "other": the lexicon's types stay
    assert [a[0] for a in asked] == ["Mara said hello and [T1 ran] home.", "She [T1 slept]."]
    assert [e["type"] for e in doc["events"]] == ["CONVERSATION", "TRAVEL", "TRAVEL"]
