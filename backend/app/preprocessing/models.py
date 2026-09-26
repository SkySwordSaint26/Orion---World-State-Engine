"""
Output contract of the deterministic preprocessing layer (no database, no LLM).

    ChapterDocument
      └─ Paragraph (id, start, end, text)
           └─ Sentence (id, paragraph_id, start, end, text)

All offsets are character offsets into ChapterDocument.text and satisfy, exactly:

    document.text[sentence.start:sentence.end] == sentence.text
    document.text[paragraph.start:paragraph.end] == paragraph.text

Text is never normalized or stripped, so offsets stay valid against the stored chapter text. Every
structure is immutable and round-trips through to_dict()/from_dict() (JSON-safe).
"""
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple


@dataclass(frozen=True)
class Sentence:
    id: str               # "s0000", unique and increasing within the chapter
    index: int            # 0-based position within the whole chapter
    paragraph_id: str
    start: int            # offset in chapter text, inclusive
    end: int              # offset in chapter text, exclusive
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "index": self.index, "paragraph_id": self.paragraph_id,
                "start": self.start, "end": self.end, "text": self.text}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sentence":
        return cls(data["id"], data["index"], data["paragraph_id"], data["start"], data["end"], data["text"])


@dataclass(frozen=True)
class Paragraph:
    id: str               # "p0000"
    index: int
    start: int
    end: int
    text: str
    sentences: Tuple[Sentence, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "index": self.index, "start": self.start, "end": self.end,
                "text": self.text, "sentences": [s.to_dict() for s in self.sentences]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Paragraph":
        return cls(data["id"], data["index"], data["start"], data["end"], data["text"],
                   tuple(Sentence.from_dict(s) for s in data["sentences"]))


@dataclass(frozen=True)
class Chunk:
    """A run of WHOLE, consecutive sentences, sized for one extraction request."""
    id: str                               # "chunk_0000"
    index: int
    sentence_ids: Tuple[str, ...]         # every sentence in the chunk, in order
    overlap_sentence_ids: Tuple[str, ...]  # leading sentences repeated from the previous chunk (subset of sentence_ids)
    start: int                            # start offset of the first sentence
    end: int                              # end offset of the last sentence
    text: str                             # exactly chapter_text[start:end]

    @property
    def new_sentence_ids(self) -> Tuple[str, ...]:
        return self.sentence_ids[len(self.overlap_sentence_ids):]

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "index": self.index, "sentence_ids": list(self.sentence_ids),
                "overlap_sentence_ids": list(self.overlap_sentence_ids),
                "start": self.start, "end": self.end, "text": self.text}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chunk":
        return cls(data["id"], data["index"], tuple(data["sentence_ids"]), tuple(data["overlap_sentence_ids"]),
                   data["start"], data["end"], data["text"])


@dataclass(frozen=True)
class ChapterDocument:
    text: str
    paragraphs: Tuple[Paragraph, ...]

    @property
    def sentences(self) -> Tuple[Sentence, ...]:
        return tuple(s for p in self.paragraphs for s in p.sentences)

    def sentence(self, sentence_id: str) -> Optional[Sentence]:
        for s in self.sentences:
            if s.id == sentence_id:
                return s
        return None

    def iter_sentences(self) -> Iterator[Sentence]:
        for p in self.paragraphs:
            yield from p.sentences

    def validate(self) -> None:
        """Raises ValueError unless every offset/id invariant of the contract holds."""
        n = len(self.text)
        seen_ids = set()
        previous_end = 0
        expected_index = 0
        for p_index, p in enumerate(self.paragraphs):
            if p.index != p_index or p.id != f"p{p_index:04d}":
                raise ValueError(f"paragraph {p.id}: bad id/index")
            if not (previous_end <= p.start < p.end <= n) or self.text[p.start:p.end] != p.text:
                raise ValueError(f"paragraph {p.id}: offsets do not match text")
            cursor = p.start
            for s in p.sentences:
                if s.index != expected_index or s.id != f"s{expected_index:04d}" or s.id in seen_ids:
                    raise ValueError(f"sentence {s.id}: bad id/index")
                if s.paragraph_id != p.id:
                    raise ValueError(f"sentence {s.id}: wrong paragraph")
                if not (cursor <= s.start < s.end <= p.end) or self.text[s.start:s.end] != s.text:
                    raise ValueError(f"sentence {s.id}: offsets do not match text")
                seen_ids.add(s.id)
                cursor = s.end
                expected_index += 1
            previous_end = p.end

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "paragraphs": [p.to_dict() for p in self.paragraphs]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterDocument":
        document = cls(data["text"], tuple(Paragraph.from_dict(p) for p in data["paragraphs"]))
        document.validate()
        return document

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "ChapterDocument":
        return cls.from_dict(json.loads(payload))
