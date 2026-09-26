"""
Phase 2 — proper and nominal mentions: GLiNER2 spans (exact offsets, never invented text) typed with the gold
vocabulary; `mention_kind` from the spaCy part of speech of the span's head word. Pronouns are left to the
coreference stage, which owns them.

Settings chosen on the 4 gold stories (docs/wse_extraction_plan.md, Phase 2): the large model, the library's
long-document windows, threshold 0.5, and label descriptions stating the annotation conventions (animals are
characters; weather, nature and media are `other`). A paragraph-window variant and adding BookNLP mentions both scored
lower.
"""
from functools import cache
from typing import Any, Dict, List, Sequence, Tuple

from app.contracts.gold import MENTION_TYPES

MODEL = "fastino/gliner2-large-v1"
THRESHOLD = 0.5
LABELS = {
    "character": "a person or animal in the story, or a group of people, including titles and roles like boss",
    "location": "a place, building, room or part of a building where someone can be: town, woods, door, stairs",
    "object": "a physical item someone can hold, use, touch or look at, including body parts and furniture",
    "organization": "an institution acting as a body: company, employer, police, government",
    "other": "weather, natural phenomena, plants, broadcasts, signals, media, rules and other things that are not "
             "people, places or physical items",
}
assert tuple(LABELS) == MENTION_TYPES

Span = Tuple[int, int, str, float]   # start, end, type, confidence


@cache
def _gliner():
    import torch
    from gliner2 import GLiNER2
    return GLiNER2.from_pretrained(MODEL).to("cuda" if torch.cuda.is_available() else "cpu")


@cache
def spacy_nlp():
    import spacy
    return spacy.load("en_core_web_sm", exclude=["ner", "lemmatizer"])


def gliner_spans(text: str, labels: Dict[str, str] = LABELS, threshold: float = THRESHOLD) -> List[Span]:
    out = _gliner().extract_entities_long(text, labels, threshold=threshold, include_spans=True,
                                          include_confidence=True)
    return [(e["start"], e["end"], t, e["confidence"]) for t, es in out["entities"].items() for e in es]


def best_type(spans: Sequence[Span]) -> Dict[Tuple[int, int], str]:
    """One label per distinct span, the most confident one, in text order."""
    best: Dict[Tuple[int, int], Tuple[str, float]] = {}
    for s, e, t, c in spans:
        if (s, e) not in best or c > best[(s, e)][1]:
            best[(s, e)] = (t, c)
    return {span: t for span, (t, _) in sorted(best.items())}


def kind(parsed: Any, start: int, end: int) -> str:
    span = parsed.char_span(start, end, alignment_mode="expand")
    pos = span.root.pos_ if span is not None else ""
    return {"PROPN": "proper", "PRON": "pronominal"}.get(pos, "nominal")


def build(text: str, spans: Sequence[Span], parsed: Any) -> List[Dict[str, Any]]:
    """One mention per distinct span (the most confident type wins), in text order; pronouns dropped."""
    out = []
    for (s, e), t in best_type(spans).items():
        k = kind(parsed, s, e)
        if k != "pronominal":
            out.append({"mention_id": f"M{len(out) + 1}", "text": text[s:e], "type": t, "mention_kind": k,
                        "start": s, "end": e})
    return out


def mentions(doc: Dict[str, Any]) -> None:
    doc["mentions"] += build(doc["text"], gliner_spans(doc["text"]), spacy_nlp()(doc["text"]))
