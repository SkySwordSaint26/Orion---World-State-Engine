"""Shared helpers for the split extraction stages (Phase 7): errors, JSON, sentence rendering, exact text location."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from app.config.logging import get_logger
from app.config.settings import settings
from app.pipeline.llm_client import llm_client
from app.pipeline.parsers.extraction_parser import clean_json_response
from app.pipeline.stages.grounding import GroundingLog, Provenance, locate_sentence
from app.resolution import name_key

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts" / "stages"
PRONOUNS = {"he", "she", "they", "him", "her", "them", "his", "hers", "their", "theirs", "it", "its",
            "i", "we", "you", "me", "us", "himself", "herself", "themselves", "itself"}
CERTAINTIES = ("DEFINITE", "PROBABLE", "UNCERTAIN")
ITEM_PATH = re.compile(r"^\$\.\w+\[\d+\]")  # "$.events[2]" (errors outside any item are structural)

logger = get_logger("app.pipeline.stages")

Generate = Callable[..., str]


class StageError(RuntimeError):
    """One extraction stage produced unusable output. Names the stage and lists every violation found."""

    def __init__(self, stage: str, chunk_id: str, errors: Sequence[str]):
        self.stage, self.chunk_id, self.errors = stage, chunk_id, list(errors)
        shown = "; ".join(self.errors[:5]) + (f" (+{len(self.errors) - 5} more)" if len(self.errors) > 5 else "")
        super().__init__(f"stage '{stage}' failed on {chunk_id}: {shown}")


@dataclass
class IdCounters:
    """Chapter-wide id allocation shared by the stages of every chunk, so ids never collide across chunks."""

    next_mention: int = 1
    next_event: int = 1

    def mention(self) -> str:
        n, self.next_mention = self.next_mention, self.next_mention + 1
        return f"M{n}"

    def event(self) -> str:
        n, self.next_event = self.next_event, self.next_event + 1
        return f"E{n}"


@dataclass
class Errors:
    stage: str
    chunk_id: str
    items: List[str] = field(default_factory=list)
    by_item: Dict[str, List[str]] = field(default_factory=dict)  # "$.events[2]" -> that item's violations
    unmatched: int = 0                                            # items whose evidence is in no NEW sentence

    def add(self, path: str, message: str) -> None:
        self.items.append(f"{path}: {message}")
        item = ITEM_PATH.match(path)
        if item:
            self.by_item.setdefault(item.group(0), []).append(f"{path}: {message}")

    def failed(self, item_path: str) -> bool:
        return item_path in self.by_item

    def finish(self, total: int, grounding: Optional[GroundingLog] = None) -> Set[str]:
        """
        End of a stage: log its item stats and every invalid item with its reasons, then apply the failure policy.
        Strict (default): any violation raises StageError. Partial (settings.ALLOW_PARTIAL_STAGE): invalid items are
        dropped; the stage still fails on a structural error or when it produced items and none is valid.
        Returns the paths of the items the caller must drop.
        """
        partial = bool(settings.ALLOW_PARTIAL_STAGE)
        structural = [e for e in self.items if not ITEM_PATH.match(e)]
        valid = total - len(self.by_item)
        fails = bool(self.items) and (not partial or bool(structural) or valid == 0)
        dropped = set() if fails else set(self.by_item)
        stats = {"mode": "partial" if partial else "strict", "items": total, "valid": valid,
                 "invalid": len(self.by_item), "dropped": len(dropped), "unmatched_evidence": self.unmatched,
                 "failed": fails}
        if grounding is not None:
            grounding.stages[self.stage] = stats
        logger.info("stage %s %s: mode=%s items=%d valid=%d invalid=%d dropped=%d unmatched_evidence=%d -> %s",
                    self.stage, self.chunk_id, stats["mode"], total, valid, stats["invalid"], stats["dropped"],
                    self.unmatched, "FAILED" if fails else "ok")
        for path, reasons in self.by_item.items():
            logger.warning("stage %s %s: %s %s: %s", self.stage, self.chunk_id,
                           "dropped" if path in dropped else "invalid", path, " | ".join(reasons))
        for e in structural:
            logger.warning("stage %s %s: structural error %s", self.stage, self.chunk_id, e)
        if fails:
            extra = ["$: no valid item remains"] if partial and not structural and valid == 0 else []
            raise StageError(self.stage, self.chunk_id, self.items + extra)
        return dropped


def load_stage_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def call_stage(generate: Optional[Generate], system_prompt: str, user_prompt: str, schema: Dict[str, Any]) -> str:
    fn = generate or llm_client.generate
    return fn(prompt=user_prompt, system_prompt=system_prompt, json_mode=True, temperature=0.0, schema=schema)


# Output schemas: passed to the model to constrain generation (Ollama). They only narrow what the model can emit;
# the stage validation below stays the contract, since no schema can check that evidence is a verbatim quote.
STRING: Dict[str, Any] = {"type": "string"}


def obj(**props: Dict[str, Any]) -> Dict[str, Any]:
    """Object schema; every key is required and generated in the given order (so put `evidence` first: the model
    then copies triggers and values out of a quote it has already written)."""
    return {"type": "object", "properties": props, "required": list(props)}


def array(items: Dict[str, Any], cap: int) -> Dict[str, Any]:
    return {"type": "array", "items": items, "maxItems": cap}


def enum(values: Sequence[str]) -> Dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def item_cap(chunk: Any) -> int:
    """Max items per list in one stage output: stops repetition loops (e.g. one name listed hundreds of times until
    the output limit breaks the JSON). Generous so it never binds on real prose; hitting it is logged."""
    return max(8, 2 * len(chunk.new_sentence_ids))


def parse_object(raw: str, stage: str, chunk_id: str) -> Dict[str, Any]:
    """The stage output must be one JSON object. (Fences / leading prose are stripped like the legacy parser.)"""
    try:
        data = json.loads(clean_json_response(raw))
    except Exception as exc:
        raise StageError(stage, chunk_id, [f"not valid JSON: {exc}"]) from exc
    if not isinstance(data, dict):
        raise StageError(stage, chunk_id, ["output is not a JSON object"])
    return data


def list_field(data: Dict[str, Any], key: str, err: Errors, required: bool = True, cap: Optional[int] = None) -> List[Any]:
    if key not in data:
        if required:
            err.add("$", f"missing required key '{key}'")
        return []
    if not isinstance(data[key], list):
        err.add(f"$.{key}", "must be a list")
        return []
    if cap is not None and len(data[key]) >= cap:
        logger.warning("stage %s %s: $.%s hit the cap of %d items; later items may have been cut off",
                       err.stage, err.chunk_id, key, cap)
    return data[key]


def text_field(item: Any, key: str, err: Errors, path: str, required: bool = True) -> Optional[str]:
    if not isinstance(item, dict):
        return None
    value = item.get(key)
    if value is None or value == "":
        if required:
            err.add(f"{path}.{key}", "is required")
        return None
    if not isinstance(value, str) or not value.strip():
        err.add(f"{path}.{key}", "must be a non-empty string")
        return None
    return value.strip()


def choice_field(
    item: Any, key: str, choices: Sequence[str], err: Errors, path: str, required: bool = True
) -> Optional[str]:
    """A value from a closed vocabulary, matched case-insensitively and returned in its canonical spelling."""
    value = text_field(item, key, err, path, required)
    if value is None:
        return None
    canonical = {c.lower(): c for c in choices}.get(value.lower())
    if canonical is None:
        err.add(f"{path}.{key}", f"{value!r} is not one of {list(choices)}")
    return canonical


def sentences_of(chunk: Any, document: Any) -> Tuple[List[Any], Dict[str, Any], set]:
    """(chunk sentences in order, id -> sentence, ids of the NEW sentences a stage may cite)."""
    wanted = set(chunk.sentence_ids)
    sents = [s for s in document.iter_sentences() if s.id in wanted]
    return sents, {s.id: s for s in sents}, set(chunk.new_sentence_ids)


def render_sentences(sents: Sequence[Any], new_ids: set) -> str:
    """One block per sentence: a marker line (metadata: id and NEW/CONTEXT), then the EXACT sentence text. The id is
    never on the same line as the text, and the text is not altered, so anything a model copies from a text line
    is an exact substring of the source sentence."""
    blocks = []
    for s in sents:
        tag = "NEW" if s.id in new_ids else "CONTEXT"
        blocks.append(f"[{s.id}] {tag}\n{s.text}")
    return "\n".join(blocks)


def mention_label(index: int) -> str:
    return f"M{index + 1}"


def mention_groups(mentions: Sequence[Any]) -> List[List[Any]]:
    """The distinct names among `mentions` (case-insensitively, via name_key), each with its occurrences, in order
    of first occurrence. Stages 2-4 see one label per name instead of one per occurrence."""
    groups: Dict[str, List[Any]] = {}
    for m in mentions:
        groups.setdefault(name_key(m.text), []).append(m)
    return list(groups.values())


def render_mentions(mentions: Sequence[Any]) -> str:
    return "\n".join(f"{mention_label(i)} | {g[0].text} | {g[0].type}" for i, g in enumerate(mention_groups(mentions)))


def label_map(mentions: Sequence[Any]) -> Dict[str, List[Any]]:
    """label -> the occurrences of that name; resolve one with `pick_mention`."""
    return {mention_label(i): g for i, g in enumerate(mention_groups(mentions))}


def pick_mention(occurrences: Sequence[Any], prov: Optional[Provenance]) -> Any:
    """The occurrence inside the item's grounded sentence(s) (the first, if several), else the first in the chunk."""
    inside = [m for m in occurrences if prov is not None and m.sentence_ids and m.sentence_ids[0] in prov.sentence_ids]
    return (inside or list(occurrences))[0]


def find_in_sentence(sentence_text: str, needle: str) -> List[Tuple[int, int]]:
    """Offsets (relative to the sentence) of every whole-word occurrence of `needle`; used only to compute
    mention / trigger offsets once the sentence is known. Runs of whitespace in the needle match any whitespace run."""
    tokens = needle.split()
    if not tokens:
        return []
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(t) for t in tokens) + r"(?!\w)"
    return [(m.start(), m.end()) for m in re.finditer(pattern, sentence_text)]


def evidence_field(item: Any, err: Errors, path: str) -> Optional[str]:
    """Mandatory `evidence`: a non-empty string, returned EXACTLY as the model wrote it (never stripped or edited)."""
    if not isinstance(item, dict):
        return None
    value = item.get("evidence")
    if value is None or value == "":
        err.add(f"{path}.evidence", "is required")
        return None
    if not isinstance(value, str) or not value.strip():
        err.add(f"{path}.evidence", "must be a non-empty string")
        return None
    return value


def ground_item(
    item: Any, chunk: Any, sents: Sequence[Any], new_ids: set, err: Errors, path: str, log: Optional[GroundingLog]
) -> Optional[Provenance]:
    """
    Grounds one item through its evidence. Returns its Provenance, or None after recording the violation.
    Evidence quoted across consecutive NEW sentences grounds the item to those sentences ("spanning", no offsets).
    Only NEW sentences can ground an item: evidence found solely in a CONTEXT (overlap) sentence is rejected, which
    keeps overlap sentences from being extracted twice.
    """
    evidence = evidence_field(item, err, path)
    if evidence is None:
        if log is not None:
            log.add(err.stage, path, "", [], None, "missing")
        return None
    new = [s for s in sents if s.id in new_ids]
    match = locate_sentence(evidence, new, (chunk.text, chunk.start))
    if match.status == "none":
        context = locate_sentence(evidence, [s for s in sents if s.id not in new_ids])
        if context.matches:
            err.add(f"{path}.evidence", f"occurs only in CONTEXT sentence(s) {list(context.sentence_ids)}; extract from NEW sentences only")
        else:
            err.add(f"{path}.evidence", "does not occur verbatim in any sentence of this chunk")
        err.unmatched += 1
        if log is not None:
            log.add(err.stage, path, evidence, [], None, "unmatched")
        return None
    if log is not None:
        log.add(err.stage, path, evidence, match.sentence_ids, match.sentence_id, match.status)
    if match.status == "unique":
        return Provenance.for_sentence(match.sentence)
    if match.status == "spanning":
        return Provenance.for_sentences(match.spanned)
    return Provenance.for_chunk(chunk)


def in_evidence(value: Optional[str], item: Any, err: Errors, path: str, key: str) -> None:
    """`value` (the item's `key`) must occur in the item's own evidence: exact, case-sensitive substring."""
    evidence = item.get("evidence") if isinstance(item, dict) else None
    if value is not None and isinstance(evidence, str) and evidence.strip() and value not in evidence:
        err.add(f"{path}.{key}", f"{value!r} does not occur in its own evidence {evidence!r}")


def offsets_in(sentence: Optional[Any], needle: str) -> Tuple[Optional[int], Optional[int]]:
    """Exact (start, end) of `needle` in the chapter, only when the sentence is known and the needle occurs once."""
    if sentence is None:
        return None, None
    spans = find_in_sentence(sentence.text, needle)
    if len(spans) != 1:
        return None, None
    return sentence.start + spans[0][0], sentence.start + spans[0][1]
