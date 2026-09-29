"""Phase 3: extraction now consumes sentence-aligned chunks with exact offsets; nothing downstream changed."""
import ast
import pathlib

from app.pipeline import extractor as extractor_module
from app.pipeline.extractor import ExtractionOrchestrator
from app.pipeline.llm_client import llm_client
from app.preprocessing import preprocess_chapter

CHAPTER = (
    "Chapter 2: The Road\n"
    "Alice met Dr. Bob Smith at noon. \"Come here!\" she said. They walked to Silver Haven...\n\n"
    + " ".join(f'Bob asked question {i}? "Yes," Alice replied.' for i in range(60))
)


def capture_prompts(monkeypatch, payload='{"entities": [], "relationships": [], "events": []}'):
    prompts = []

    def fake_generate(prompt, system_prompt=None, json_mode=True, temperature=0.0, schema=None):
        prompts.append(prompt)
        return payload

    monkeypatch.setattr(llm_client, "generate", fake_generate)
    return prompts


def test_every_prompt_contains_exactly_one_sentence_aligned_slice_of_the_chapter(monkeypatch):
    prompts = capture_prompts(monkeypatch)
    monkeypatch.setattr(extractor_module, "CHUNK_MAX_CHARS", 400)
    result = ExtractionOrchestrator().extract_chapter(CHAPTER, chapter_number=2)

    document = preprocess_chapter(CHAPTER)
    meta = result["preprocessing"]["chunks"]
    assert len(prompts) == len(meta) > 3
    starts = {s.start for s in document.sentences}
    ends = {s.end for s in document.sentences}
    for prompt, chunk in zip(prompts, meta):
        body = CHAPTER[chunk["start"]:chunk["end"]]
        assert body in prompt                                           # extractor receives the exact slice
        assert chunk["start"] in starts and chunk["end"] in ends        # ... which starts/ends on sentence boundaries


def test_no_sentence_is_sent_twice_except_declared_overlap(monkeypatch):
    capture_prompts(monkeypatch)
    monkeypatch.setattr(extractor_module, "CHUNK_MAX_CHARS", 400)
    meta = ExtractionOrchestrator().extract_chapter(CHAPTER)["preprocessing"]["chunks"]
    counts = {}
    for chunk in meta:
        for sid in chunk["sentence_ids"]:
            counts[sid] = counts.get(sid, 0) + 1
    declared = {sid for chunk in meta for sid in chunk["overlap_sentence_ids"]}
    assert {sid for sid, n in counts.items() if n > 1} == declared
    assert set(counts) == {s.id for s in preprocess_chapter(CHAPTER).sentences}   # nothing skipped


def test_extracted_items_carry_chunk_provenance_with_exact_offsets(monkeypatch):
    payload = ('{"entities": [{"mention": "Alice", "canonical_name": "Alice", "type": "character", "attributes": {}}],'
               ' "relationships": [{"subject": "Alice", "predicate": "KNOWS", "object": "Bob"}],'
               ' "events": [{"id": "e1", "type": "MEETING", "participants": ["Alice"]}]}')
    capture_prompts(monkeypatch, payload)
    result = ExtractionOrchestrator().extract_chapter(CHAPTER)
    chunk = result["preprocessing"]["chunks"][0]
    for item in (result["raw_mentions"][0], result["relationships"][0], result["events"][0]):
        assert item["source_chunk"] == chunk["id"]
        assert item["source_span"] == [chunk["start"], chunk["end"]]
        assert CHAPTER[item["source_span"][0]:item["source_span"][1]].startswith("Chapter 2")


def test_extraction_output_shape_is_unchanged_for_downstream_stages(monkeypatch):
    capture_prompts(monkeypatch)
    result = ExtractionOrchestrator().extract_chapter("Alice ran. Bob stayed.", chapter_number=7)
    assert {"chapter_number", "entities", "raw_mentions", "relationships", "events",
            "state_changes", "temporal_relations"} <= set(result)
    assert result["chapter_number"] == 7 and result["preprocessing"]["sentences"] == 2


def test_empty_chapter_makes_no_llm_calls(monkeypatch):
    prompts = capture_prompts(monkeypatch)
    result = ExtractionOrchestrator().extract_chapter("  \n\n ")
    assert prompts == [] and result["entities"] == [] and result["preprocessing"]["chunks"] == []


def test_preprocessing_is_deterministic_end_to_end(monkeypatch):
    first = capture_prompts(monkeypatch)
    ExtractionOrchestrator().extract_chapter(CHAPTER)
    second = capture_prompts(monkeypatch)
    ExtractionOrchestrator().extract_chapter(CHAPTER)
    assert first == second


def test_preprocessing_package_uses_no_llm_or_network_code():
    forbidden = {"llm_client", "httpx", "openai", "ollama", "requests", "urllib", "spacy", "nltk", "torch"}
    for path in (pathlib.Path(__file__).resolve().parent.parent / "preprocessing").glob("*.py"):
        names = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names.update(p for a in node.names for p in a.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                names.update((node.module or "").split("."))
                names.update(a.name for a in node.names)
        assert not (names & forbidden), f"{path.name} imports {names & forbidden}"


def test_old_character_chunker_is_still_importable_for_compatibility():
    from app.utils.text_splitter import chunk_text
    assert chunk_text("One. Two.", max_chars=100, overlap=10)[0]["text"] == "One. Two."
