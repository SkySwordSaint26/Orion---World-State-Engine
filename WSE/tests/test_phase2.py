from wse.mentions import build, spacy_nlp

TEXT = "Dan left the old radio station. He took his phone."


def span(text, t="character", c=0.9, nth=0):
    s = -1
    for _ in range(nth + 1):
        s = TEXT.index(text, s + 1)
    return (s, s + len(text), t, c)


def test_build_keeps_one_mention_per_span_with_kind_and_drops_pronouns():
    spans = [span("Dan"), span("radio station", "location", 0.8), span("radio station", "object", 0.6),
             span("He"), span("phone", "object")]
    out = build(TEXT, spans, spacy_nlp()(TEXT))
    assert [(m["mention_id"], m["text"], m["type"], m["mention_kind"]) for m in out] == [
        ("M1", "Dan", "character", "proper"), ("M2", "radio station", "location", "nominal"),
        ("M3", "phone", "object", "nominal")]
    assert all(TEXT[m["start"]:m["end"]] == m["text"] for m in out)
