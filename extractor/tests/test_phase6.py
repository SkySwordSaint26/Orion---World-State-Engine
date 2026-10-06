from extractor import temporal as T
from extractor.pipeline import LISTS

TEXT = "I left before he arrived. After leaving, I sat."
# word, lemma, dependency, head token
PARSE = [("I", "I", "nsubj", 1), ("left", "leave", "ROOT", 1), ("before", "before", "mark", 4), ("he", "he", "nsubj", 4),
         ("arrived", "arrive", "advcl", 1), (".", ".", "punct", 1),
         ("After", "after", "prep", 10), ("leaving", "leave", "pcomp", 6), (",", ",", "punct", 10),
         ("I", "I", "nsubj", 10), ("sat", "sit", "ROOT", 10), (".", ".", "punct", 10)]


def tokens():
    out, cursor = [], 0
    for word, lemma, dep, head in PARSE:
        a = TEXT.index(word, cursor)
        cursor = a + len(word)
        out.append({"word": word, "lemma": lemma, "dependency_relation": dep, "syntactic_head_ID": str(head),
                    "byte_onset": str(a), "byte_offset": str(cursor)})
    return out


def test_markers_order_events_and_expressions_are_typed(monkeypatch):
    toks = tokens()
    monkeypatch.setattr(T, "booknlp_output", lambda text: (toks, []))
    monkeypatch.setattr(T, "gliner_spans", lambda text, labels, th: [(0, 1, "duration", 0.4), (0, 1, "other", 0.2)])
    events = [{"event_id": f"E{i}", "start": int(toks[j]["byte_onset"])} for i, j in enumerate((1, 4, 7, 10), 1)]
    d = {"text": TEXT, **{k: [] for k in LISTS}, "events": events}
    T.temporal(d)
    assert [(r["source_event_id"], r["relation"], r["target_event_id"]) for r in d["temporal_relations"]] == [
        ("E1", "BEFORE", "E2"),                   # left BEFORE arrived
        ("E4", "AFTER", "E3")]                    # sat AFTER leaving
    assert d["temporal_expressions"] == [{"temporal_id": "T1", "text": "I", "type": "duration", "start": 0, "end": 1}]
