"""
Deterministic, rule-based paragraph and sentence segmentation. No LLM, no NLP library, no randomness:
the same text always yields the same ChapterDocument, and every span is an exact slice of the input.

Paragraphs
    Runs of non-blank lines separated by blank lines. If the chapter's first line is a heading
    ("Chapter 3: ...", "Prologue"), it becomes its own paragraph so it is not glued to the first sentence.

Sentences (inside a paragraph)
    A sentence ends at a terminator run (. ! ? …) plus any attached closing quotes/brackets, when
    whitespace follows AND the next token starts with an uppercase letter or digit. It does NOT end:
      * after title abbreviations (Mr. Dr. St. ...), initials (J. R. R.), e.g./i.e., dotted acronyms (U.S.)
      * inside numbers (3.14) or before a lowercase word ("Wait... what?", '"Stop!" he said')
      * before a dialogue tag ('"Stop!" Alice said.' stays one sentence)
    Single newlines inside a paragraph are ordinary whitespace (hard-wrapped text stays intact).

Known limits (documented, deterministic): "Vitamin C. Next" and "the U.S. Army" are not split/handled
perfectly; a sentence that ends with a title-like abbreviation before a new sentence is merged with it.
"""
import re
from typing import List, Tuple

from app.preprocessing.models import ChapterDocument, Paragraph, Sentence

TERMINATORS = ".!?…"
CLOSERS = "\"”’'»)]}›"
OPENERS = "\"“‘'«([{‹"

# A period after these never ends a sentence.
_NEVER_BREAK = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "lt", "col", "gen", "capt", "sgt",
    "rev", "hon", "gov", "sen", "rep", "vs", "mme", "mlle", "messrs", "e.g", "i.e", "cf",
})

_SPEECH_VERBS = frozenset({
    "said", "says", "asked", "asks", "replied", "replies", "whispered", "shouted", "cried", "answered",
    "called", "muttered", "murmured", "exclaimed", "yelled", "added", "continued", "demanded", "snapped",
    "sighed", "laughed", "growled", "screamed", "announced", "declared", "suggested", "insisted", "warned",
    "remarked", "observed", "explained", "wondered", "offered", "agreed", "protested", "begged", "sobbed",
    "hissed", "stammered", "gasped", "groaned", "cheered", "urged", "pleaded", "retorted", "thought",
})

_HEADING_RE = re.compile(
    r"^\s*(?:[#*]{1,3}\s*)?(?:"
    r"(?i:prologue|epilogue)(?:\s*[:.\-—]\s*\S.*)?"
    r"|(?i:chapter|part|act|book)\s+(?:\d+|[IVXLCDM]+|(?i:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))\b(?:\s*[:.\-—]?\s*\S.*)?"
    r")\s*$"
)
_DOTTED_ACRONYM_RE = re.compile(r"^(?:[A-Za-z]\.)+[A-Za-z]$")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def _paragraph_spans(text: str) -> List[Tuple[int, int]]:
    """(start, end) of each paragraph, trimmed of surrounding whitespace; blank lines separate paragraphs."""
    spans: List[Tuple[int, int]] = []
    block_start = block_end = None
    pos = 0
    first_block_lines: List[Tuple[int, int]] = []
    lines: List[Tuple[int, int]] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped:
            lead = len(line) - len(line.lstrip())
            start = pos + lead
            end = start + len(stripped)
            if block_start is None:
                block_start = start
                lines = []
            block_end = end
            lines.append((start, end))
        elif block_start is not None:
            spans.append((block_start, block_end))
            if not first_block_lines:
                first_block_lines = lines
            block_start = block_end = None
        pos += len(line)
    if block_start is not None:
        spans.append((block_start, block_end))
        if not first_block_lines:
            first_block_lines = lines

    # A heading line at the very top of the chapter is its own paragraph.
    if spans and len(first_block_lines) > 1:
        h_start, h_end = first_block_lines[0]
        if _HEADING_RE.match(text[h_start:h_end]) and not text[h_start:h_end].rstrip().endswith((".", "!", "?")):
            first_start, first_end = spans[0]
            spans[0:1] = [(h_start, h_end), (first_block_lines[1][0], first_end)]
    return spans


def _word_before(text: str, i: int) -> str:
    j = i
    while j > 0 and (text[j - 1].isalnum() or text[j - 1] == "."):
        j -= 1
    return text[j:i].lstrip(".")


def _looks_like_dialogue_tag(text: str, pos: int, hi: int) -> bool:
    words = _WORD_RE.findall(text[pos:min(hi, pos + 100)])[:3]
    if len(words) >= 2 and words[1].lower() in _SPEECH_VERBS:
        return True
    return len(words) >= 3 and words[1][0].isupper() and words[2].lower() in _SPEECH_VERBS


def _is_boundary(text: str, i: int, run_end: int, closers_end: int, next_start: int, hi: int) -> bool:
    run = text[i:run_end]
    if run == ".":
        word = _word_before(text, i)
        lowered = word.lower()
        if lowered in _NEVER_BREAK:
            return False
        if len(word) == 1 and word.isupper() and word != "I":      # initial: "Robert J. Guthard"
            return False
        if len(word) >= 3 and lowered not in ("a.m", "p.m") and _DOTTED_ACRONYM_RE.match(word):   # "U.S."
            return False

    p = next_start
    while p < hi and text[p] in OPENERS:
        p += 1
    if p >= hi:
        return True
    following = text[p]
    if not (following.isupper() or following.isdigit()):
        return False                                               # "Wait... what?", '"Stop!" he said'
    attached_quote = any(c in "\"”’'»" for c in text[run_end:closers_end])
    if attached_quote and _looks_like_dialogue_tag(text, p, hi):
        return False                                               # '"Stop!" Alice said.'
    return True


def _sentence_spans(text: str, lo: int, hi: int) -> List[Tuple[int, int]]:
    """Sentence spans inside one paragraph text[lo:hi] (which has no leading/trailing whitespace)."""
    spans: List[Tuple[int, int]] = []
    start = lo
    i = lo
    while i < hi:
        if text[i] not in TERMINATORS:
            i += 1
            continue
        run_end = i + 1
        while run_end < hi and text[run_end] in TERMINATORS:
            run_end += 1
        closers_end = run_end
        while closers_end < hi and text[closers_end] in CLOSERS:
            closers_end += 1
        if closers_end >= hi:
            break                                                   # paragraph ends here
        if not text[closers_end].isspace():
            i = run_end                                             # "3.14", "Hello...world"
            continue
        next_start = closers_end
        while next_start < hi and text[next_start].isspace():
            next_start += 1
        if _is_boundary(text, i, run_end, closers_end, next_start, hi):
            spans.append((start, closers_end))
            start = next_start
            i = next_start
        else:
            i = closers_end
    spans.append((start, hi))
    return spans


def build_document(text: str) -> ChapterDocument:
    """Segments chapter text into paragraphs and sentences with exact character offsets."""
    paragraphs: List[Paragraph] = []
    sentence_index = 0
    for p_index, (p_start, p_end) in enumerate(_paragraph_spans(text)):
        p_id = f"p{p_index:04d}"
        sentences: List[Sentence] = []
        for s_start, s_end in _sentence_spans(text, p_start, p_end):
            sentences.append(Sentence(
                id=f"s{sentence_index:04d}", index=sentence_index, paragraph_id=p_id,
                start=s_start, end=s_end, text=text[s_start:s_end]))
            sentence_index += 1
        paragraphs.append(Paragraph(
            id=p_id, index=p_index, start=p_start, end=p_end, text=text[p_start:p_end],
            sentences=tuple(sentences)))
    document = ChapterDocument(text=text, paragraphs=tuple(paragraphs))
    document.validate()
    return document
