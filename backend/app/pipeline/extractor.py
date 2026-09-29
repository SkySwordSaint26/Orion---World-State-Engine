import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.contracts import ContractError, ExtractionResult, ExtractorInput, extract_observations, validate_result
from app.contracts.mapping import (
    legacy_entities, legacy_events, legacy_relationships, legacy_state_changes, legacy_temporal_relations,
)
from app.config.settings import settings
from app.pipeline.llm_client import llm_client
from app.pipeline.stages import IdCounters, StageError, extract_chunk_split
from app.pipeline.parsers.extraction_parser import parse_and_validate_extraction
from app.pipeline.resolution.entity_resolution import cluster_mentions
from app.preprocessing import chunk_document, preprocess_chapter
from app.config.logging import get_logger

logger = get_logger(__name__)

PROMPT_FILE = Path(__file__).parent / "prompts" / "extraction_prompt.txt"

def load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "Extract structured entities, relationships, and events into strict JSON."


class ExtractionError(RuntimeError):
    """Raised when a chunk's LLM output cannot be parsed at all (not merely partially invalid)."""


# Extraction input size. Chunks are built from whole sentences (see app/preprocessing); the overlap is
# counted in sentences (roughly the old 400 characters).
CHUNK_MAX_CHARS = 8000
CHUNK_OVERLAP_SENTENCES = 2


PIPELINES = ("monolithic", "split")


class ExtractionOrchestrator:
    def __init__(self, pipeline: Optional[str] = None):
        self.system_prompt = load_system_prompt()
        self._pipeline = pipeline  # None = read settings.EXTRACTION_PIPELINE on every call

    @property
    def pipeline(self) -> str:
        mode = (self._pipeline or settings.EXTRACTION_PIPELINE or "monolithic").strip().lower()
        if mode not in PIPELINES:
            raise ExtractionError(f"Unknown EXTRACTION_PIPELINE {mode!r}; expected one of {list(PIPELINES)}")
        return mode

    def extract_chapter(
        self,
        chapter_text: str,
        chapter_number: int = 1,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Processes a full chapter's text: chunks it, sends to LLM, parses,
        and aggregates entities, relationships, and events.
        """
        # Deterministic preprocessing (no LLM): paragraphs -> sentences with exact offsets -> sentence-aligned
        # chunks. chunk.text == chapter_text[chunk.start:chunk.end], so every extracted item can be traced
        # back to an exact span of the chapter.
        document = preprocess_chapter(chapter_text)
        chunks = chunk_document(document, max_chars=CHUNK_MAX_CHARS, overlap_sentences=CHUNK_OVERLAP_SENTENCES)
        logger.info(
            f"Chapter {chapter_number}: {len(document.paragraphs)} paragraphs, {len(document.sentences)} sentences, "
            f"{len(chunks)} chunks for extraction."
        )

        result = ExtractionResult(chapter_number=chapter_number)
        mode = self.pipeline
        split_ids = IdCounters()

        for idx, chunk in enumerate(chunks):
            if mode == "split":
                # Phase 7: four focused, independently validated stages instead of one monolithic call.
                try:
                    chunk_result = extract_chunk_split(chunk, document, split_ids, chapter_number)
                    validate_result(chunk_result, document)
                except (StageError, ContractError) as exc:
                    raise ExtractionError(
                        f"Chapter {chapter_number}, chunk {idx + 1}/{len(chunks)}: split extraction failed: {exc}"
                    ) from exc
                result = result.merge(chunk_result)
                if progress_callback:
                    progress_callback(idx + 1, len(chunks))
                continue

            chunk_prompt = (
                f"Extract structured world state information from the following passage.\n\n"
                f"CHUNK [{idx + 1}/{len(chunks)}]:\n"
                f"-----------------------------------------\n"
                f"{chunk.text}\n"
                f"-----------------------------------------\n"
                f"Output strictly valid JSON matching the instructions."
            )

            raw_output = llm_client.generate(
                prompt=chunk_prompt,
                system_prompt=self.system_prompt,
                json_mode=True,
                temperature=0.0
            )

            parsed, errors = parse_and_validate_extraction(raw_output)
            if errors:
                # The parser only reports errors when the output is unusable as a whole
                # (invalid JSON / not an object). Treating that as an empty chunk would let a
                # chapter finish "successfully" with silently missing data.
                raise ExtractionError(
                    f"Chapter {chapter_number}, chunk {idx + 1}/{len(chunks)}: unusable LLM output: {errors}"
                )

            # Phase 4: wrap the parsed output into typed observations (span + sentence ids propagated from
            # the chunk) and validate them at this boundary; invalid output fails the chapter early.
            try:
                chunk_result = extract_observations(
                    ExtractorInput(document=document, chunk=chunk, chapter_number=chapter_number), parsed)
            except ContractError as exc:
                raise ExtractionError(
                    f"Chapter {chapter_number}, chunk {idx + 1}/{len(chunks)}: extraction contract violated: {exc}"
                ) from exc
            result = result.merge(chunk_result)

            if progress_callback:
                progress_callback(idx + 1, len(chunks))

        # The legacy dict shape below is unchanged; it is now derived from the observations.
        all_raw_entities = legacy_entities(result)

        # Cluster duplicate entities across chunks
        clustered_entities = cluster_mentions(all_raw_entities)

        return {
            "chapter_number": chapter_number,
            "pipeline": mode,
            "entities": clustered_entities,
            "raw_mentions": all_raw_entities,
            "relationships": legacy_relationships(result),
            "events": legacy_events(result),
            "state_changes": legacy_state_changes(result),
            "temporal_relations": legacy_temporal_relations(result),
            "observations": result,
            "document": document,  # Phase 5: entity resolution needs paragraphs/sentences (in-memory only)
            "preprocessing": {
                "paragraphs": len(document.paragraphs),
                "sentences": len(document.sentences),
                "chunks": [
                    {"id": c.id, "start": c.start, "end": c.end, "sentence_ids": list(c.sentence_ids),
                     "overlap_sentence_ids": list(c.overlap_sentence_ids)}
                    for c in chunks
                ],
            },
        }

# Global instance
orchestrator = ExtractionOrchestrator()
