"""Phase 3: sentence-aligned chunking - whole sentences only, sentence-counted overlap, no duplication."""
import pathlib
import random

import pytest

from app.preprocessing import Chunk, chunk_document, preprocess_chapter

SAMPLE = pathlib.Path(__file__).resolve().parents[3] / "extractor" / "data" / "Left Right Game 1.txt"


def make_text(n, width=1):
    return " ".join(f"Sentence number {i} " + "word " * width + "ends here." for i in range(n))


def check_chunks(doc, chunks, max_chars, overlap):
    """Every chunk invariant, checked from scratch."""
    by_id = {s.id: s for s in doc.sentences}
    order = [s.id for s in doc.sentences]
    emitted_new = []
    for chunk in chunks:
        members = [by_id[i] for i in chunk.sentence_ids]
        # whole, consecutive sentences only
        idx = [order.index(i) for i in chunk.sentence_ids]
        assert idx == list(range(idx[0], idx[0] + len(idx)))
        # offsets/text are exactly the first-start..last-end slice: no fragments, nothing trimmed mid-sentence
        assert (chunk.start, chunk.end) == (members[0].start, members[-1].end)
        assert chunk.text == doc.text[chunk.start:chunk.end]
        # size: within max_chars unless a single (unsplittable) sentence is larger
        assert chunk.end - chunk.start <= max_chars or len(members) == 1
        # overlap is a leading run, at most `overlap` sentences, and exactly the previous chunk's tail
        assert len(chunk.overlap_sentence_ids) <= overlap
        assert chunk.sentence_ids[:len(chunk.overlap_sentence_ids)] == chunk.overlap_sentence_ids
        if chunk.index == 0:
            assert chunk.overlap_sentence_ids == ()
        else:
            prev = chunks[chunk.index - 1]
            assert chunk.overlap_sentence_ids == prev.sentence_ids[len(prev.sentence_ids) - len(chunk.overlap_sentence_ids):]
        # progress: at least one new sentence
        assert chunk.new_sentence_ids
        emitted_new.extend(chunk.new_sentence_ids)
    # every sentence is "new" in exactly one chunk, in order -> full coverage, no duplication beyond overlap
    assert emitted_new == order


def test_empty_document_has_no_chunks():
    assert chunk_document(preprocess_chapter("")) == []


def test_small_chapter_is_one_chunk_with_exact_text():
    text = "One. Two. Three."
    doc = preprocess_chapter(text)
    [chunk] = chunk_document(doc, max_chars=8000, overlap_sentences=2)
    assert chunk.text == text and chunk.sentence_ids == ("s0000", "s0001", "s0002") and chunk.overlap_sentence_ids == ()


def test_chunks_contain_only_whole_sentences_and_respect_size():
    doc = preprocess_chapter(make_text(40))
    chunks = chunk_document(doc, max_chars=200, overlap_sentences=2)
    assert len(chunks) > 3
    check_chunks(doc, chunks, 200, 2)
    for chunk in chunks:                                   # each chunk starts/ends exactly on sentence boundaries
        assert chunk.text.startswith("Sentence number") and chunk.text.endswith("ends here.")


def test_overlap_is_counted_in_sentences_and_nothing_else_is_duplicated():
    doc = preprocess_chapter(make_text(30))
    chunks = chunk_document(doc, max_chars=250, overlap_sentences=2)
    check_chunks(doc, chunks, 250, 2)
    assert all(len(c.overlap_sentence_ids) == 2 for c in chunks[1:])
    seen = {}
    for c in chunks:
        for sid in c.sentence_ids:
            seen[sid] = seen.get(sid, 0) + 1
    assert set(seen.values()) <= {1, 2}                                          # never more than one repeat
    repeated = {sid for sid, count in seen.items() if count == 2}
    assert repeated == {sid for c in chunks for sid in c.overlap_sentence_ids}   # repeats are exactly the declared overlap


def test_zero_overlap_partitions_the_sentences():
    doc = preprocess_chapter(make_text(25))
    chunks = chunk_document(doc, max_chars=180, overlap_sentences=0)
    check_chunks(doc, chunks, 180, 0)
    flat = [sid for c in chunks for sid in c.sentence_ids]
    assert flat == [s.id for s in doc.sentences]


def test_a_sentence_longer_than_max_chars_is_never_split():
    long_sentence = "This sentence " + "keeps going " * 40 + "until it finally ends."
    text = f"Short one. {long_sentence} Another short one. Last."
    doc = preprocess_chapter(text)
    chunks = chunk_document(doc, max_chars=100, overlap_sentences=1)
    check_chunks(doc, chunks, 100, 1)
    big = [c for c in chunks if long_sentence in c.text]
    assert len(big) >= 1 and all(long_sentence in c.text for c in big)
    assert any(c.sentence_ids == ("s0001",) or "s0001" in c.sentence_ids for c in chunks)


def test_overlap_that_does_not_fit_is_reduced_so_progress_is_always_made():
    # overlap (60) is larger than the chunk budget: the old character chunker looped forever on this shape
    doc = preprocess_chapter(make_text(20))
    chunks = chunk_document(doc, max_chars=40, overlap_sentences=60)
    check_chunks(doc, chunks, 40, 60)
    assert len(chunks) <= len(doc.sentences)


def test_chunk_ids_and_serialization():
    doc = preprocess_chapter(make_text(12))
    chunks = chunk_document(doc, max_chars=150, overlap_sentences=1)
    assert [c.id for c in chunks] == [f"chunk_{i:04d}" for i in range(len(chunks))]
    for chunk in chunks:
        assert Chunk.from_dict(chunk.to_dict()) == chunk


def test_chunking_is_reproducible():
    text = make_text(50, width=3)
    runs = [[c.to_dict() for c in chunk_document(preprocess_chapter(text), 300, 2)] for _ in range(4)]
    assert all(r == runs[0] for r in runs)


def test_invalid_parameters_are_rejected():
    doc = preprocess_chapter("One.")
    with pytest.raises(ValueError):
        chunk_document(doc, max_chars=0)
    with pytest.raises(ValueError):
        chunk_document(doc, overlap_sentences=-1)


def test_chunk_integrity_on_real_prose_and_random_parameters():
    if not SAMPLE.exists():
        pytest.skip("sample manuscript not present")
    doc = preprocess_chapter(SAMPLE.read_text(encoding="utf-8", errors="replace"))
    rng = random.Random(7)
    for _ in range(40):
        max_chars, overlap = rng.choice([60, 200, 500, 1500, 8000]), rng.randint(0, 5)
        check_chunks(doc, chunk_document(doc, max_chars, overlap), max_chars, overlap)


def test_dialogue_is_never_split_across_chunks_mid_sentence():
    text = " ".join(f'"Line {i}!" Alice said. Then Bob answered {i}.' for i in range(15))
    doc = preprocess_chapter(text)
    for chunk in chunk_document(doc, max_chars=120, overlap_sentences=1):
        assert chunk.text.count('"') % 2 == 0          # a quote opened in a chunk is closed in the same chunk
