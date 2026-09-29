"""
Deterministic sentence grounding for the split stages (Phase 7.1).

The model no longer cites sentence ids. Every item carries mandatory `evidence`, and CODE decides which sentence
it belongs to: `locate_sentence` finds the sentences whose text contains the evidence as an EXACT substring (no
fuzzy matching, no normalization, the evidence text is never modified).

    one match     -> the item is grounded to that sentence (sentence-level span, exact offsets possible)
    several       -> ambiguous: valid, sentence_id is None, provenance falls back to the whole chunk (the same
                     chunk-level provenance the monolithic extractor uses); logged, never fatal
    none          -> validation failure

Spanning (Phase 7.1b): the prompt shows one sentence per line, so a model may quote across a line break. When no
single sentence contains the evidence, it may still be an EXACT substring of the source text of CONSECUTIVE
sentences (including the original whitespace between them, e.g. " " or "\n\n"). Exactly one such occurrence
grounds the item to the sentences it covers ("spanning"); several are ambiguous. Nothing is normalized: the
evidence must match the source character for character, gaps included.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config.logging import get_logger

logger = get_logger("app.pipeline.stages.grounding")


@dataclass(frozen=True)
class MatchResult:
    evidence: str
    matches: Tuple[Any, ...] = ()  # every Sentence whose text contains the evidence, in document order
    spans: Tuple[Tuple[Any, ...], ...] = ()  # only when `matches` is empty: sentences covered by each spanning match

    @property
    def sentence_ids(self) -> Tuple[str, ...]:
        if self.matches:
            return tuple(s.id for s in self.matches)
        return tuple(dict.fromkeys(s.id for span in self.spans for s in span))

    @property
    def status(self) -> str:
        if self.matches:
            return "unique" if len(self.matches) == 1 else "ambiguous"
        if self.spans:
            return "spanning" if len(self.spans) == 1 else "ambiguous"
        return "none"

    @property
    def spanned(self) -> Tuple[Any, ...]:
        """The consecutive sentences of the single spanning match, else ()."""
        return self.spans[0] if len(self.spans) == 1 and not self.matches else ()

    @property
    def sentence(self) -> Optional[Any]:
        """The grounded sentence, or None (no match, or ambiguous)."""
        return self.matches[0] if len(self.matches) == 1 else None

    @property
    def sentence_id(self) -> Optional[str]:
        return self.sentence.id if self.sentence is not None else None


def locate_sentence(evidence: str, sentences: Sequence[Any], source: Optional[Tuple[str, int]] = None) -> MatchResult:
    """
    Sentences (objects with id/start/end/text) whose text contains `evidence` as an exact substring.
    With `source` = (text, offset of text[0] in the chapter), evidence found in no single sentence is also searched,
    exactly, in the source text of each run of consecutive sentences; an occurrence counts only if it covers at
    least two sentences.
    """
    if not isinstance(evidence, str) or not evidence.strip():
        return MatchResult(evidence if isinstance(evidence, str) else "")
    matches = tuple(s for s in sentences if evidence in s.text)
    if matches or source is None:
        return MatchResult(evidence, matches)
    return MatchResult(evidence, (), _spanning(evidence, sentences, *source))


def _spanning(evidence: str, sentences: Sequence[Any], text: str, offset: int) -> Tuple[Tuple[Any, ...], ...]:
    runs: List[List[Any]] = []
    for s in sentences:                  # consecutive = nothing but the original gap between them in the source
        if runs and runs[-1][-1].end <= s.start and not text[runs[-1][-1].end - offset:s.start - offset].strip():
            runs[-1].append(s)
        else:
            runs.append([s])
    found: List[Tuple[Any, ...]] = []
    for run in runs:
        if len(run) < 2:
            continue
        base = run[0].start
        window = text[base - offset:run[-1].end - offset]
        at = window.find(evidence)
        while at != -1:
            start, end = base + at, base + at + len(evidence)
            covered = tuple(s for s in run if s.start < end and start < s.end)
            if len(covered) >= 2:
                found.append(covered)
            at = window.find(evidence, at + 1)
    return tuple(found)


@dataclass(frozen=True)
class Provenance:
    """Where an observation came from, as the contracts want it."""

    sentence_ids: Tuple[str, ...]
    source_span: Tuple[int, int]
    sentence: Optional[Any]  # the grounded sentence when unambiguous, else None (chunk-level provenance)

    @classmethod
    def for_sentence(cls, sentence: Any) -> "Provenance":
        return cls((sentence.id,), (sentence.start, sentence.end), sentence)

    @classmethod
    def for_sentences(cls, sentences: Sequence[Any]) -> "Provenance":
        """Consecutive sentences quoted by one spanning evidence: sentence-level, but no single sentence."""
        return cls(tuple(s.id for s in sentences), (sentences[0].start, sentences[-1].end), None)

    @classmethod
    def for_chunk(cls, chunk: Any) -> "Provenance":
        return cls(tuple(chunk.sentence_ids), (chunk.start, chunk.end), None)


@dataclass
class GroundingRecord:
    stage: str
    path: str
    evidence: str
    matched_sentence_ids: List[str]
    assigned_sentence_id: Optional[str]
    status: str  # unique | spanning | ambiguous | unmatched | missing; stage 1: located | context_only | unmatched


@dataclass
class GroundingLog:
    """Per-item records of one chunk; also logs each item (DEBUG) and the chunk summary (INFO)."""

    chunk_id: str = ""
    records: List[GroundingRecord] = field(default_factory=list)
    stages: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # per-stage item stats (see common.Errors)

    def add(self, stage: str, path: str, evidence: str, matched: Sequence[str], assigned: Optional[str], status: str) -> None:
        rec = GroundingRecord(stage, path, evidence, list(matched), assigned, status)
        self.records.append(rec)
        shown = evidence if len(evidence) <= 200 else evidence[:200] + "..."
        logger.debug("grounding %s %s %s evidence=%r matched=%s assigned=%s", self.chunk_id, stage, path, shown,
                     rec.matched_sentence_ids, assigned)

    def summary(self) -> Dict[str, int]:
        count = lambda s: sum(1 for r in self.records if r.status == s)  # noqa: E731
        return {"items": len(self.records), "ambiguous": count("ambiguous"), "unmatched": count("unmatched"),
                "missing_evidence": count("missing"), "unique": count("unique"), "spanning": count("spanning"),
                "located": count("located"), "context_only": count("context_only")}

    def log_summary(self) -> None:
        s = self.summary()
        logger.info("grounding %s: items=%d ambiguous=%d unmatched=%d missing_evidence=%d unique=%d spanning=%d "
                    "located=%d context_only=%d", self.chunk_id, s["items"], s["ambiguous"], s["unmatched"],
                    s["missing_evidence"], s["unique"], s["spanning"], s["located"], s["context_only"])
