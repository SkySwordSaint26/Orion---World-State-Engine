from wse import events as E
from wse.evaluate import score
from wse.pipeline import LISTS

TEXT = "I ran to the desk and called my boss. Noise."
# word, lemma, POS, dependency, head token, BookNLP event flag
PARSE = [("I", "I", "PRON", "nsubj", 1, "O"), ("ran", "run", "VERB", "ROOT", 1, "EVENT"),
         ("to", "to", "ADP", "prep", 1, "O"), ("the", "the", "DET", "det", 4, "O"),
         ("desk", "desk", "NOUN", "pobj", 2, "O"), ("and", "and", "CCONJ", "cc", 1, "O"),
         ("called", "call", "VERB", "conj", 1, "EVENT"), ("my", "my", "PRON", "poss", 8, "O"),
         ("boss", "boss", "NOUN", "dobj", 6, "O"), (".", ".", "PUNCT", "punct", 1, "O"),
         ("Noise", "noise", "NOUN", "ROOT", 10, "EVENT"), (".", ".", "PUNCT", "punct", 10, "O")]


def tokens():
    out, cursor = [], 0
    for word, lemma, pos, dep, head, event in PARSE:
        a = TEXT.index(word, cursor)
        cursor = a + len(word)
        out.append({"word": word, "lemma": lemma, "POS_tag": pos, "dependency_relation": dep,
                    "syntactic_head_ID": str(head), "event": event, "byte_onset": str(a), "byte_offset": str(cursor)})
    return out


def mention(mid, s, kind="nominal"):
    a = TEXT.index(s)
    return {"mention_id": mid, "text": s, "type": "character", "mention_kind": kind, "start": a, "end": a + len(s)}


MENTIONS = [mention("M1", "I", "pronominal"), mention("M2", "desk"), mention("M3", "my", "pronominal"),
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


def test_entity_level_arguments_credit_a_pronoun_through_its_cluster():
    gold_event = {"event_id": "E1", "type": "OTHER", "trigger": "ran", "start": 2, "end": 5,
                  "participants": [{"role": "agent", "mention_id": "M9"}]}
    gold = doc([mention("M9", "boss"), mention("M2", "desk")], events=[gold_event])
    pred = doc(clusters=[["M1", "M4"]], events=[{**gold_event, "participants": [{"role": "agent", "mention_id": "M1"}]}])
    s = score(pred, gold)
    assert s["event_arguments"]["f1"] == 0.0 and s["event_arguments_entity"]["f1"] == 1.0
