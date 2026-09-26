"""
Stage 1 - entity mention extraction (Phase 7.2). Input: chunk sentences. Output: EntityMention[] only.

The model only NAMES things: each distinct name or noun phrase once, with a type. CODE finds where they are: every
exact, whole-word occurrence in a NEW sentence becomes one mention with exact chapter offsets and its sentence as
provenance. The model never has to pair a name with a sentence, which is what it got wrong (a correct name quoted
with a sentence that says "He ...", or a speaker's untagged dialogue line).

    a listed form occurring in no sentence of the chunk        -> violation (the anti-hallucination check)
    a listed form occurring only in CONTEXT (overlap) sentences -> no mention, logged: the previous chunk has it
    a pronoun                                                   -> violation (pronouns are resolved downstream)

Matching is exact (case-sensitive, whole word) with two exceptions: a form starting with a lowercase letter also
matches the same text with that letter capitalised at the very start of a sentence ("professional cynic" in
"Professional cynic."), and a straight apostrophe matches a typographic one and vice versa ("Dan's" in "Dan’s"; the
model cannot reliably reproduce ’). A mention always stores the SOURCE characters. Forms are matched independently,
so nested mentions ("Dan" inside "Dan's mother") are all kept, as the gold annotations keep them.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.contracts import EntityMention
from app.contracts.gold import MENTION_TYPES
from app.pipeline.stages.common import (
    PRONOUNS, STRING, Errors, Generate, IdCounters, array, call_stage, choice_field, enum, item_cap, list_field,
    load_stage_prompt, obj, parse_object, render_sentences, sentences_of, text_field,
)
from app.pipeline.stages.grounding import GroundingLog
from app.resolution import name_key

STAGE = "entities"


def _pattern(form: str) -> str:
    return "".join("['’]" if ch in "'’" else re.escape(ch) for ch in form)


def occurrences(form: str, sentence_text: str) -> List[Tuple[int, int]]:
    """Sentence-relative spans of `form`: exact whole-word matches, plus the two exceptions above."""
    spans = [m.span() for m in re.finditer(r"(?<!\w)" + _pattern(form) + r"(?!\w)", sentence_text)]
    if form[:1].islower():
        capital = form[0].upper() + form[1:]
        start = re.match(_pattern(capital) + r"(?!\w)", sentence_text)
        if start:
            spans.insert(0, start.span())
    return spans


def build_mentions(
    payload: Dict[str, Any], chunk: Any, document: Any, ids: IdCounters, grounding: Optional[GroundingLog] = None
) -> List[EntityMention]:
    """Validate a parsed stage-1 payload, locate every listed form and build the mentions. Raises StageError."""
    err = Errors(STAGE, chunk.id)
    sents, _, new_ids = sentences_of(chunk, document)
    new = [s for s in sents if s.id in new_ids]
    context = [s for s in sents if s.id not in new_ids]
    items = list_field(payload, "mentions", err, cap=item_cap(chunk))
    staged: List[Tuple[str, str, Any, int, int]] = []    # (item path, type, sentence, start, end in the sentence)
    listed = set()
    for i, item in enumerate(items):
        path = f"$.mentions[{i}]"
        if not isinstance(item, dict):
            err.add(path, "must be an object")
            continue
        text = text_field(item, "text", err, path)
        mtype = choice_field(item, "type", MENTION_TYPES, err, path)
        if text is None or mtype is None:
            continue
        if name_key(text) in PRONOUNS:
            err.add(f"{path}.text", f"{text!r} is a pronoun; pronouns are not extracted as mentions")
            continue
        if text in listed:
            continue                                     # listed twice: still one form
        listed.add(text)
        hits = [(s, a, b) for s in new for a, b in occurrences(text, s.text)]
        if not hits:
            in_context = [s.id for s in context if occurrences(text, s.text)]
            if grounding is not None:
                grounding.add(STAGE, path, text, in_context, None, "context_only" if in_context else "unmatched")
            if not in_context:
                err.unmatched += 1
                err.add(f"{path}.text", f"{text!r} does not occur in any sentence of this chunk")
            continue
        if grounding is not None:
            matched = list(dict.fromkeys(s.id for s, _, _ in hits))
            grounding.add(STAGE, path, text, matched, matched[0] if len(matched) == 1 else None, "located")
        staged.extend((path, mtype, s, a, b) for s, a, b in hits)
    dropped = err.finish(len(items), grounding)

    by_span: Dict[Tuple[int, int], Tuple[str, Any]] = {}   # two forms on the same span are one mention
    for path, mtype, s, a, b in staged:
        if path not in dropped:
            by_span.setdefault((s.start + a, s.start + b), (mtype, s))
    return [EntityMention(
        id=ids.mention(), text=document.text[start:end], type=mtype, start=start, end=end, raw_text=s.text,
        source_chunk=chunk.id, source_span=(s.start, s.end), sentence_ids=(s.id,))
        for (start, end), (mtype, s) in sorted(by_span.items(), key=lambda kv: (kv[0][0], -kv[0][1]))]


def extract_mentions(
    chunk: Any, document: Any, ids: IdCounters, generate: Optional[Generate] = None,
    grounding: Optional[GroundingLog] = None
) -> List[EntityMention]:
    sents, _, new_ids = sentences_of(chunk, document)
    user = f"CHUNK {chunk.id}\nSENTENCES:\n{render_sentences(sents, new_ids)}\n\nReturn the JSON object now."
    schema = obj(mentions=array(obj(text=STRING, type=enum(MENTION_TYPES)), item_cap(chunk)))
    raw = call_stage(generate, load_stage_prompt("stage1_entities.txt"), user, schema)
    return build_mentions(parse_object(raw, STAGE, chunk.id), chunk, document, ids, grounding)
