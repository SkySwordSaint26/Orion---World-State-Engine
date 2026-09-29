"""
Sentence-aligned chunking. A chunk is a run of WHOLE consecutive sentences; overlap between consecutive
chunks is counted in sentences (never characters), so no sentence is ever cut and none is repeated except
as declared overlap.

Size rule: a chunk's span (first sentence start .. last sentence end) stays within max_chars, except that a
single sentence longer than max_chars becomes a chunk of its own (a sentence is never split).
Progress rule: every chunk contains at least one sentence that no earlier chunk contained.
"""
from typing import List

from app.preprocessing.models import ChapterDocument, Chunk


def chunk_document(document: ChapterDocument, max_chars: int = 8000, overlap_sentences: int = 2) -> List[Chunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_sentences < 0:
        raise ValueError("overlap_sentences must be >= 0")

    sentences = document.sentences
    n = len(sentences)
    chunks: List[Chunk] = []
    first_new = 0          # index of the first sentence not yet emitted as "new"
    previous_start = 0

    while first_new < n:
        # Largest overlap (<= overlap_sentences) that still leaves room for the first new sentence.
        overlap = 0
        if chunks:
            for candidate in range(min(overlap_sentences, first_new - previous_start), 0, -1):
                if sentences[first_new].end - sentences[first_new - candidate].start <= max_chars:
                    overlap = candidate
                    break
        start_index = first_new - overlap

        end_index = first_new + 1                                    # always take one new sentence
        while end_index < n and sentences[end_index].end - sentences[start_index].start <= max_chars:
            end_index += 1

        members = sentences[start_index:end_index]
        start, end = members[0].start, members[-1].end
        chunks.append(Chunk(
            id=f"chunk_{len(chunks):04d}",
            index=len(chunks),
            sentence_ids=tuple(s.id for s in members),
            overlap_sentence_ids=tuple(s.id for s in members[:overlap]),
            start=start,
            end=end,
            text=document.text[start:end],
        ))
        previous_start = start_index
        first_new = end_index

    return chunks
