import pytest
from app.utils.text_splitter import split_into_chapters, chunk_text
from app.pipeline.resolution.fact_resolution import resolve_fact_update
from app.pipeline.resolution.relationship_resolution import resolve_relationship_update
from app.core.constants import FactStatus, RelationshipStatus

def test_split_into_chapters():
    text = (
        "Chapter 1: The Beginning\n"
        "It was the best of times.\n\n"
        "Chapter 2: The Middle\n"
        "Things began to shift."
    )
    chapters = split_into_chapters(text)
    assert len(chapters) == 2
    assert chapters[0][0] == 1
    assert "Beginning" in chapters[0][1]
    assert chapters[1][0] == 2
    assert "Middle" in chapters[1][1]

def test_split_into_chapters_fallback():
    text = "Just a short story with no chapter heading whatsoever."
    chapters = split_into_chapters(text)
    assert len(chapters) == 1
    assert chapters[0][0] == 1
    assert chapters[0][2] == text

def test_chunk_text():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = chunk_text(text, max_chars=30, overlap=5)
    assert len(chunks) >= 1
    assert all("chunk_id" in c for c in chunks)

def test_resolve_fact_update_no_change():
    status, con = resolve_fact_update("rank", "Captain", "Captain")
    assert status == FactStatus.ACTIVE.value
    assert con is None

def test_resolve_fact_update_contradiction():
    # eye_color is immutable -> contradiction
    status, con = resolve_fact_update("eye_color", "blue", "green", "Alice")
    assert status == FactStatus.CONTRADICTED.value
    assert con is not None
    assert "blue" in con["explanation"] and "green" in con["explanation"]

def test_resolve_relationship_update_conflict():
    status, con = resolve_relationship_update("ENEMY_OF", "FRIEND_OF", "Alice", "Bob")
    assert status == RelationshipStatus.CONTRADICTED.value
    assert con is not None
