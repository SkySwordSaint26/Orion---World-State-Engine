"""Phase 3: deterministic sentence/paragraph segmentation, offset integrity, serialization, reproducibility."""
import json
import pathlib
import random

import pytest

from app.preprocessing import ChapterDocument, preprocess_chapter

SAMPLE = pathlib.Path(__file__).resolve().parents[3] / "extractor" / "data" / "Left Right Game 1.txt"


def sentences(text):
    return [s.text for s in preprocess_chapter(text).sentences]


def assert_integrity(text):
    """The full offset contract, checked from scratch (independent of ChapterDocument.validate)."""
    doc = preprocess_chapter(text)
    covered = []
    last_end = 0
    for p in doc.paragraphs:
        assert text[p.start:p.end] == p.text
        for s in p.sentences:
            assert text[s.start:s.end] == s.text, (s.id, s.text)          # exact offsets
            assert s.text == s.text.strip() and s.text                     # no fragments of whitespace
            assert s.start >= last_end                                     # ordered, non-overlapping
            assert p.start <= s.start and s.end <= p.end
            covered.extend(range(s.start, s.end))
            last_end = s.end
    # every non-whitespace character belongs to exactly one sentence (nothing lost, nothing duplicated)
    assert len(covered) == len(set(covered))
    assert {i for i, c in enumerate(text) if not c.isspace()} <= set(covered)
    return doc


# ---------------------------------------------------------------- simple sentences
def test_simple_sentences():
    assert sentences("Alice ran home. Bob stayed. Was it over? Yes! Not yet.") == [
        "Alice ran home.", "Bob stayed.", "Was it over?", "Yes!", "Not yet."]


def test_text_without_terminal_punctuation_is_one_sentence():
    assert sentences("No punctuation here") == ["No punctuation here"]
    assert sentences("First one. Trailing fragment") == ["First one.", "Trailing fragment"]


def test_empty_and_whitespace_only_text():
    for text in ("", "   \n\n\t  "):
        doc = preprocess_chapter(text)
        assert doc.paragraphs == () and doc.sentences == ()


def test_leading_and_trailing_whitespace_is_excluded_but_offsets_stay_absolute():
    text = "\n\n  Hello there.  General Kenobi!  \n\n"
    doc = assert_integrity(text)
    assert [s.text for s in doc.sentences] == ["Hello there.", "General Kenobi!"]
    assert doc.sentences[0].start == text.index("Hello")


# ------------------------------------------------------------------------ dialogue
def test_dialogue_tag_stays_attached_to_its_quote():
    assert sentences('"Stop!" Alice said. She ran.') == ['"Stop!" Alice said.', "She ran."]
    assert sentences('"Really?" she asked. "Yes."') == ['"Really?" she asked.', '"Yes."']


def test_lowercase_continuation_after_a_closing_quote_is_not_a_boundary():
    assert sentences('"Stop!" he said, and left. Then silence.') == ['"Stop!" he said, and left.', "Then silence."]
    assert sentences('"Come here," Alice said. "Now."') == ['"Come here," Alice said.', '"Now."']


def test_quote_followed_by_narration_is_a_boundary():
    assert sentences('"No." He shook his head.') == ['"No."', "He shook his head."]
    assert sentences('He whispered. "Go now." She went.') == ["He whispered.", '"Go now."', "She went."]


def test_curly_quotes_and_multi_sentence_speech():
    # sentences INSIDE a quotation are split like any others; "smiled" is not a speech verb, so narration starts a new one
    assert sentences("“I came. I saw.” Caesar smiled.") == ["“I came.", "I saw.”", "Caesar smiled."]
    assert sentences("“Stop!” Alice said. “Why?”") == ["“Stop!” Alice said.", "“Why?”"]


def test_dialogue_offsets_are_exact():
    assert_integrity('"Stop!" Alice said. "Why?" "Because." He left... She stayed.\n"Next line," Bob said.')


# ------------------------------------------------------------------- abbreviations
@pytest.mark.parametrize("text,expected", [
    ("Dr. Smith met Mr. Jones. They talked.", ["Dr. Smith met Mr. Jones.", "They talked."]),
    ("Mrs. Alice Brown left St. Louis. He stayed.", ["Mrs. Alice Brown left St. Louis.", "He stayed."]),
    ("Robert J. Guthard sat down. Nobody spoke.", ["Robert J. Guthard sat down.", "Nobody spoke."]),
    ("J. R. R. Tolkien wrote it. Fans agree.", ["J. R. R. Tolkien wrote it.", "Fans agree."]),
    ("Use fruit, e.g. apples, daily. Eat well.", ["Use fruit, e.g. apples, daily.", "Eat well."]),
    ("Pi is 3.14 exactly. Version 2.0 shipped.", ["Pi is 3.14 exactly.", "Version 2.0 shipped."]),
    ("He lives in the U.S. now. She left.", ["He lives in the U.S. now.", "She left."]),
    ("They met at 5 p.m. He was late.", ["They met at 5 p.m.", "He was late."]),
    ("So did I. Then we left.", ["So did I.", "Then we left."]),
])
def test_abbreviations_initials_and_numbers(text, expected):
    assert sentences(text) == expected
    assert_integrity(text)


# ---------------------------------------------------------------------- ellipses
def test_ellipses():
    assert sentences("Wait... what happened? He left... She stayed.") == ["Wait... what happened?", "He left...", "She stayed."]
    assert sentences("Well… maybe. Then… nothing.") == ["Well… maybe.", "Then… nothing."]
    assert sentences("It was over.... Really over.") == ["It was over....", "Really over."]
    assert sentences("Hello...world is odd. Yes.") == ["Hello...world is odd.", "Yes."]


def test_mixed_terminators():
    assert sentences("What?! No way. Really?? Yes.") == ["What?!", "No way.", "Really??", "Yes."]


# --------------------------------------------------------------------- paragraphs
def test_multi_paragraph_text():
    text = "First paragraph, first sentence. Second sentence.\n\nSecond paragraph starts here. It ends.\n\n\n\nThird."
    doc = assert_integrity(text)
    assert [len(p.sentences) for p in doc.paragraphs] == [2, 2, 1]
    assert [p.id for p in doc.paragraphs] == ["p0000", "p0001", "p0002"]
    assert [s.id for s in doc.sentences] == [f"s{i:04d}" for i in range(5)]
    assert doc.sentences[2].paragraph_id == "p0001"


def test_paragraph_without_terminal_punctuation_does_not_merge_with_the_next_paragraph():
    doc = assert_integrity("A heading-like line\n\nThen a sentence. And another.")
    assert [s.text for s in doc.sentences] == ["A heading-like line", "Then a sentence.", "And another."]


def test_single_newlines_are_whitespace_inside_a_sentence():
    text = "This sentence is hard\nwrapped across lines. Another one\nhere."
    assert sentences(text) == ["This sentence is hard\nwrapped across lines.", "Another one\nhere."]
    assert_integrity(text)


def test_blank_lines_containing_spaces_or_crlf_separate_paragraphs():
    text = "One.\r\n   \r\nTwo.\r\n\r\nThree."
    doc = assert_integrity(text)
    assert [p.text for p in doc.paragraphs] == ["One.", "Two.", "Three."]


def test_chapter_heading_is_its_own_paragraph_and_sentence():
    text = "Chapter 3: The Return\nAlice came home. It was late."
    doc = assert_integrity(text)
    assert [p.text for p in doc.paragraphs] == ["Chapter 3: The Return", "Alice came home. It was late."]
    for heading in ("Prologue\nIt began.", "CHAPTER IV\nIt began.", "Part One\nIt began."):
        assert len(preprocess_chapter(heading).paragraphs) == 2, heading


def test_ordinary_sentences_starting_with_heading_words_are_not_headings():
    for text in ("Part of him wanted to leave.\nHe stayed.", "Act quickly.\nThey ran.", "Book smart, she said.\nOk."):
        doc = preprocess_chapter(text)
        assert len(doc.paragraphs) == 1, text


# ------------------------------------------------------------------- offset integrity
CORPUS = [
    "Simple. Text. Here.",
    "Mixed “curly” and \"straight\" quotes. Alice said, “Hello.” Bob nodded.",
    "Ünïcödé text. Çà et là… Fin.",
    "Tabs\tand   multiple   spaces.  Two  spaces  after.",
    "Line one.\nLine two.\n\nNew para?\n",
    "a. b. c. D. E.",
    "1. First item. 2. Second item.",
    "Ends with quote: \"like this.\"",
    "((Nested (brackets.)) Then more.)",
    "  \t  ",
    "!!!",
    "...",
    ". . .",
]


@pytest.mark.parametrize("text", CORPUS)
def test_offset_integrity_on_edge_case_corpus(text):
    doc = assert_integrity(text)
    doc.validate()


def test_offset_integrity_on_real_prose_sample():
    if not SAMPLE.exists():
        pytest.skip("sample manuscript not present")
    text = SAMPLE.read_text(encoding="utf-8", errors="replace")
    doc = assert_integrity(text)
    assert len(doc.sentences) > 20
    longest = max(len(s.text) for s in doc.sentences)
    assert longest < 1500  # segmentation actually happened; no paragraph-sized "sentences"


def test_offset_integrity_on_seeded_random_text():
    pieces = ["Alice", "Dr.", "Mr.", "J.", "e.g.", "U.S.", "3.14", "said", "and", "he", "She", "\"Stop!\"", "“Why?”",
              "...", "…", ".", "!", "?", "\n", "\n\n", "  ", "'", "\"", "(", ")", "Ünï", "p.m.", "The", "the", "It's"]
    rng = random.Random(20260919)
    for _ in range(300):
        text = " ".join(rng.choice(pieces) for _ in range(rng.randint(1, 60)))
        assert_integrity(text)


# ------------------------------------------------------------ reproducibility / contract
def test_segmentation_is_reproducible():
    text = "Dr. Smith said, \"Stop!\" Alice ran... Bob didn't.\n\nNew paragraph. Ends."
    runs = [preprocess_chapter(text).to_json() for _ in range(5)]
    assert len(set(runs)) == 1


def test_document_round_trips_through_json_and_dict():
    text = "Chapter 1\nAlice ran. \"Stop!\" Bob said.\n\nThe end."
    doc = preprocess_chapter(text)
    assert ChapterDocument.from_json(doc.to_json()) == doc
    assert ChapterDocument.from_dict(json.loads(json.dumps(doc.to_dict()))) == doc
    payload = doc.to_dict()
    assert set(payload["paragraphs"][0]["sentences"][0]) == {"id", "index", "paragraph_id", "start", "end", "text"}


def test_validate_rejects_corrupted_documents():
    doc = preprocess_chapter("One. Two.")
    data = doc.to_dict()
    data["paragraphs"][0]["sentences"][1]["start"] += 1
    with pytest.raises(ValueError):
        ChapterDocument.from_dict(data)
    data = doc.to_dict()
    data["paragraphs"][0]["sentences"][0]["text"] = "Wrong."
    with pytest.raises(ValueError):
        ChapterDocument.from_dict(data)


def test_sentence_lookup_and_ids():
    doc = preprocess_chapter("One. Two.\n\nThree.")
    assert doc.sentence("s0002").text == "Three." and doc.sentence("nope") is None
    assert [s.index for s in doc.iter_sentences()] == [0, 1, 2]
