"""Deterministic preprocessing: chapter text -> paragraphs -> sentences -> sentence-aligned chunks."""
from app.preprocessing.chunker import chunk_document
from app.preprocessing.models import ChapterDocument, Chunk, Paragraph, Sentence
from app.preprocessing.segmenter import build_document

preprocess_chapter = build_document

__all__ = ["ChapterDocument", "Paragraph", "Sentence", "Chunk", "build_document", "preprocess_chapter", "chunk_document"]
