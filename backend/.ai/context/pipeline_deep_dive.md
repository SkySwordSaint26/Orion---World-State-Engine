# Extraction Pipeline & Resolution Deep Dive

This document explains the algorithmic mechanics of the narrative information extraction pipeline.

> **Historical (2026-09-30):** the in-process LLM pipeline (monolithic and split), its parser, and the Phase 5-6 resolution and coreference packages were removed. Extraction is `../extractor` through `app/pipeline/extractor.py`. Only §1 (preprocessing) still describes live code; the rest is kept for its design rationale and is in git history.

---

## 1. Preprocessing & Chunking (`app/preprocessing/`)

**IMPLEMENTED (Phase 3).** Extraction no longer receives character-sliced text. Chapter text goes through a deterministic, LLM-free, dependency-free layer:

```
chapter text
   -> paragraphs   (blank-line separated; a leading "Chapter N" heading is its own paragraph)
   -> sentences    (rule-based; exact start/end offsets; ids s0000.., paragraph ids p0000..)
   -> chunks       (whole consecutive sentences; overlap counted in sentences)
```

Contract ([`models.py`](../../app/preprocessing/models.py)): `ChapterDocument -> Paragraph -> Sentence`, plus `Chunk`. Immutable, JSON round-trippable, not tied to the database. For every sentence `chapter_text[start:end] == sentence.text`; text is never stripped or normalized, so offsets stay valid against the stored chapter.

Segmentation ([`segmenter.py`](../../app/preprocessing/segmenter.py)) does not split on: title abbreviations (Mr., Dr., St.), initials (J. R. R.), `e.g.`/`i.e.`, dotted acronyms (U.S.), decimals, an ellipsis or `?`/`!` followed by a lowercase word, or before a dialogue tag (`"Stop!" Alice said.`). Known limits: `"Vitamin C. Next"` is merged, a sentence *inside* a quotation is split like any other, and unbalanced quotes are not repaired.

Chunking ([`chunker.py`](../../app/preprocessing/chunker.py)): a chunk spans at most `max_chars` (default 8,000, `CHUNK_MAX_CHARS`) unless one sentence is longer, in which case that sentence is a chunk on its own (a sentence is never cut). Consecutive chunks repeat `overlap_sentences` (default 2, `CHUNK_OVERLAP_SENTENCES`) whole sentences, reported in `Chunk.overlap_sentence_ids`; every chunk contains at least one sentence no earlier chunk had, so chunking always terminates. Extracted entities/relationships/events keep `source_chunk` and gain `source_span = [start, end]` (the chunk's offsets in the chapter).

The old character chunker (`utils/text_splitter.chunk_text`) is deprecated and unused by extraction: it cut mid-sentence, its offsets did not match its stripped text, and it never terminated when overlap exceeded progress.

**PLANNED / NOT IMPLEMENTED YET:** tokens inside sentences, per-mention offsets (`EntityMention.start_position` is still not populated), and consuming sentence ids in later extraction stages. Overlap sentences are still sent to the LLM twice, so the same fact can still be extracted twice; de-duplication is a later stage.

---

## 1b. Pipeline Data Contracts & Observations (`app/contracts/`)

**IMPLEMENTED (Phase 4).** Explicit, immutable, JSON-serializable models for what flows between stages (in memory only; nothing new is persisted):

```
raw chapter text -> ChapterDocument -> Chunk -> [extractor: unchanged prompt + parser]
   -> ExtractionResult { EntityMention[], Relationship[], Event[], FactObservation[], TemporalRelation[] }
```

- `Observation` is the base of every extracted item (kind entity/event/relationship/fact/temporal_relation, `source_chunk`, `source_span`, `sentence_ids`, `raw_text` = the LLM's quoted evidence, `confidence` = None because the prompt does not produce one). Constructors validate required fields, span shape and confidence range.
- `FactObservation` covers both entity `attributes` (origin `attribute`) and `state_changes` (origin `state_change`).
- **Span rule:** spans are in chapter coordinates and sentence ids belong to the chapter's `ChapterDocument`. The LLM does not say where an item came from, so today they describe the whole **chunk** the item came from (chunk-level provenance, not per-mention).
- `extract_observations(ExtractorInput, parsed)` wraps the parsed output and validates it against the document (span inside the chapter, sentence ids exist and lie inside the span). A violation raises `ContractError`, which the orchestrator turns into `ExtractionError` (the chapter fails early).
- The extractor's legacy dict output is unchanged; it is derived from the observations. It gains an `observations` key holding the `ExtractionResult`.
- `CoreferenceCluster`: empty from the extractor; filled by `app/coreference` since Phase 6 (§1d).
- **Normalization hooks** (`normalize_property`, `normalize_predicate`, `normalize_entity_name`) are **pass-through**. They are called at observation creation and at the TODO(property|relationship-normalization) points in `WorldStateService` / `ConsistencyService`. No normalization logic exists yet.
- **Gold alignment (Phase 4.5, `orion_gold_v1.schema.json`).** Field names follow the schema (`text`/`type`/`start`/`end`, `trigger`, `source_event_id`/`target_event_id`, cluster `mentions` = mention ids) and every item can carry a gold `id` (`M#`, `E#`, `R#`, `F#`, `T#`, `TR#`). `contracts/gold.py` holds the schema's vocabularies and `project_to_gold(result, story_id=, text=)`, an adapter that assigns ids, resolves name references by exact match (no coreference, no normalization) and lists everything not schema-complete in `issues`.
  - **NOT YET POPULATED (optional, always None/empty today):** mention `start`/`end`, `mention_kind`, event `trigger`/`start`/`end`/`participant_refs`, `*_mention_id` references, `temporal_expressions`, coreference clusters, `confidence`, and ids.
  - **Not in gold (kept for legacy output/integration):** `canonical_name`, `attributes`, `certainty`, event `location`/`time_expression`/name `participants`, `previous_value`, `caused_by_event`, fact `origin`.
  - **Vocabulary mismatches (reported, never remapped, since remapping is normalization):** the LLM's predicates (`FATHER_OF`, ...), event types, property names and entity types are free strings; gold has closed enums (e.g. `PARENT_OF`/`CHILD_OF`, no `FATHER_OF`).
  - **Consequence:** today's extractor output projects to a structurally valid but schema-INCOMPLETE gold document.

---

## 1c. Entity Resolution: Mention -> Entity (`app/resolution/`)

**IMPLEMENTED (Phase 5).** Deterministic, LLM-free, DB-free (`resolver.py`); the World State side is `services/entity_resolution_service.py`, called from `WorldStateService.integrate_extraction_result` (inside the locked chapter transaction) only when the extractor supplied `observations` + `document`. Contract: `EntityResolutionResult` = `EntityResolution(mention_id, resolved_entity_id, resolution_type, confidence, evidence)` + `unresolved` + planned `new_entities` (provisional ids `new:<n>`, rebound to real rows after step 1 of integration).

Strategies, first one to find any candidate decides; more than one distinct candidate = **unresolved, never guessed**:

| # | type | rule | conf |
|---|---|---|---|
| 1 | `exact_match` | identical string to a canonical name | 1.00 |
| 2 | `normalized_match` | equal after case / whitespace / edge-punctuation folding | 0.95 |
| 3 | `alias` | stored `EntityAlias` | 0.90 |
| 4 | `alias` | nickname table (rob -> robert, ...; tiny, explicit, `NICKNAMES`) | 0.70 |
| 5 | `alias` | tokens are a proper subset of ONE entity's name (`Alice` -> `Alice Sterling`); title-only names excluded | 0.70 |
| 6 | `new_entity` | nothing matched | 1.00 |
| + | `pronoun` | `he/she/they`: sentence-initial, not in a quotation, exactly ONE person entity named earlier in the same paragraph | 0.50 |

Safety rules: entity types that are both known and different never merge; a longer name is never folded into a shorter entity; steps 4-5 only target entities that existed before the batch and any other batch name that would also qualify makes the mention ambiguous, so the result does not depend on mention order; gender is not used (the World State has none).

Attachment: `ResolvedExtraction.result` is the observations with `entity_id` (mentions, facts), `subject_entity_id`/`object_entity_id` (relationships) and `participant_entity_ids` (events) filled where a name maps to exactly one entity. Names are matched to mentions by normalized string, not coreference. `WorldStateService.last_resolution` exposes it. The extractor's legacy dict output only gains a `document` key.

World State effects: an existing entity is reused (no duplicate created) when the legacy lookup fails but the resolver finds a unique match; unresolved mentions fall through to the legacy behavior unchanged. Resolved pronouns are persisted as `entity_mentions` rows with exact `start_position`/`end_position` and confidence 0.5. **No aliases are persisted** from heuristic matches.

**NOT IMPLEMENTED:** cross-sentence pronoun chains, gender/number agreement, pronouns beyond sentence-initial, descriptive/nominal mentions ("the captain"), fuzzy or embedding matching, persisting learned aliases, merging existing duplicate entities.

---

## 1d. Coreference Clusters & Cluster Grounding (`app/coreference/`)

**IMPLEMENTED (Phase 6).** Pure, LLM-free, DB-free, no similarity of any kind. Runs in `WorldStateService` right after Phase 5 (`apply_coreference`), and its results are exposed as `last_coreference` / `last_resolution.result.coreference_clusters`. `CoreferenceCluster` = `cluster_id` (`C1..`, ordered by first member), `mentions` (ids, >= 2), optional `canonical_name` and `entity_id`, and `rules` (audit). The gold projection stays `{cluster_id, mentions}`. `CoreferenceResult.mapping` is `mention_id -> cluster_id`.

Three edge rules only:

| rule | edge |
|---|---|
| `same_entity` | non-pronoun mentions resolved to the same entity id (Phase 5) |
| `pronoun` | a resolved pronoun joins the cluster of its entity's named mentions (its antecedent) |
| `exact_text` | same normalized text, and only if that cannot contradict entities: types that disagree do not merge (unknown type is left out); different entities do not merge; an entity-less mention never joins a group that has one; pronoun texts never cluster by text |

Mentions Phase 5 left unresolved (ambiguous / conflicting) are **excluded entirely**: two "Alice" that could each be a different Alice are not evidence of one Alice.

Grounding (`ground_references`): relationships / events / facts whose entity id is still empty are resolved through the clusters (`"He hit John"` -> `He` is clustered with `Robert` -> subject = Robert). Never overrides Phase 5. Because provenance is chunk-level, scope is the LLM's quoted `evidence` when it occurs exactly once verbatim inside the chunk, otherwise the chunk. A pronoun reference resolves only if the scope contains exactly ONE such pronoun token and it is a resolved cluster member (an unresolved pronoun elsewhere can never be mistaken for a resolved one); any candidate mention without an entity blocks the reference. `WorldStateService` uses the result only where the name lookup found nothing, and only when the legacy lists still pair 1:1 with the observations (same length and names).

**NOT IMPLEMENTED / limits:** no fuzzy or similarity clustering, no clustering across chapters (the World State entity is the cross-chapter link), no cluster-level reasoning about gender/number, no pronouns beyond Phase 5's sentence-initial rule (so most pronoun references stay ungrounded on purpose), `state_changes` facts are grounded in memory but are not integrated into the World State at all.

---

## 1e. Split Extraction Pipeline (`app/pipeline/stages/`)

**IMPLEMENTED (Phase 7), OPT-IN.** `EXTRACTION_PIPELINE=split` replaces the single monolithic LLM call per chunk by four focused, independently validated calls. The default is still `monolithic` (the prompt, parser and behavior of Phases 1-6 are unchanged; flipping the default is a separate decision).

```
chunk -> 1 entities -> 2 relationships -> 3 events (+ temporal relations) -> 4 facts -> ExtractionResult
      -> (unchanged) legacy dicts, Phase 5 resolution, Phase 6 clustering, grounding, World State integration
```

| stage | input | output | LLM call skipped when |
|---|---|---|---|
| 1 `entities` | sentences (NEW / CONTEXT) | `EntityMention[]` only: text, type, **evidence** | never |
| 2 `relationships` | sentences + stage-1 mentions | `Relationship[]`, subject/object are **mention labels**, **evidence** | fewer than 2 mentions |
| 3 `events` | sentences + mentions | `Event[]`: type, **trigger**, participants as `{mention, role}`, **evidence**; optional temporal relations | no mentions |
| 4 `facts` | sentences + mentions | `FactObservation[]` (attribute / state_change), entity is a **mention label**, **evidence** | no mentions |

Guarantees:
- **The model never outputs sentence ids (Phase 7.1).** Every item carries mandatory `evidence` (a non-empty string, used exactly as written: no stripping, no normalization). Code decides the sentence with `locate_sentence(evidence, sentences)` (`stages/grounding.py`): the sentences whose text contains the evidence as an EXACT substring. **One match** grounds the item to that sentence (sentence-level span, exact offsets possible). **Several matches** = ambiguous: valid, assigned sentence id `None`, provenance falls back to the whole chunk (the monolithic extractor's chunk-level provenance), logged, never fatal. **No match** = validation failure. Only NEW sentences can ground an item: evidence found solely in an overlap (CONTEXT) sentence is rejected, so overlap sentences are never extracted twice. A stray `sentence_id` in the model output is ignored.
- **Strict per-stage validation** (`StageError` names the stage and lists every violation; the orchestrator turns it into `ExtractionError`, so the chapter fails per Phase 1 rules): valid JSON object, required keys and fields, mandatory verbatim evidence, references use labels that exist in this chunk's mention list (free-text names are rejected), no self relationships, no pronoun mentions, scalar non-empty fact values, closed vocabularies (mention type, predicate, certainty, event type, participant role, temporal relation, fact property and kind; the gold lists in `contracts/gold.py`, matched case-insensitively). The first failing stage stops the chunk; later stages never run on bad data. Nothing is repaired or remapped.
- **`text` and `trigger` are no longer verified against the source** (the 7.0 rule "text must occur in the cited sentence" was replaced by the evidence rule). They only drive best-effort offsets: `start`/`end` are set when the sentence is known (unique evidence match) and the text occurs once in it, otherwise `None`.
- **Prompt rendering:** each sentence is a marker line (`[s0001] NEW` / `CONTEXT`, metadata only) followed by the EXACT sentence text on its own line(s); ids are never on a text line, so a model copying text cannot copy an id, and copied evidence is a true substring of the source.
- **Grounding log (`GroundingLog`):** per item: evidence, matched sentence ids, assigned sentence id (DEBUG log + `records`); per chunk: items / ambiguous / unmatched / missing-evidence / unique (INFO log, emitted even when a stage fails).
- **No overlap duplicates**, **chapter-unique ids** (`M#`, `E#`; event `local_id` namespaced `<chunk id>:<label>`).
- **Explicit references:** `subject_mention_id`, `participant_refs`, `entity_mention_id` ground straight through the mentions' entities (`resolution/references.py`, used by `WorldStateService`); they win over name lookups. Monolithic output has no references and is untouched.
- The legacy output shape is preserved (ATTRIBUTE facts are folded into mention `attributes`, an event's location-role participant becomes `location`). Split output with unique evidence projects to a schema-valid gold document.
- **Constrained generation:** each stage passes a JSON schema to the model (`llm_client.generate(schema=...)`, Ollama `format`), built from the same vocabularies: every key required and `evidence` first (the model writes the quote, then copies the trigger/values out of it), mention labels restricted to this chunk's labels, closed vocabularies as enums, and every list capped at `item_cap(chunk)` = max(8, 2 × NEW sentences), which stops repetition loops; a list that hits the cap is logged. Other providers ignore the schema, so the validation above stays the contract (no schema can check that evidence is verbatim).
- Deterministic: temperature 0, deterministic prompts, ids and ordering (the local Ollama GPU backend itself is not bit-exact at temperature 0).

Limits: vocabularies are enforced but not normalized: an out-of-list value is rejected, never remapped. The gold predicate list has no `FATHER_OF` or `DEAD_AT_HANDS_OF`, so split output cannot trigger the consistency rules keyed on them (`consistency/vocabulary.py`). `LLM_PROVIDER=mock` only emulates the monolithic call, so it fails loudly in split mode. `caused_by_event` and `time_expression` are not produced by the split stages. Four LLM calls per chunk cost more time than one.

---

## 2. Extraction Prompt Anatomy (`extraction_prompt.txt`)

The system prompt strictly frames the LLM as an **Information Extraction Engine**, not a creative writer.

### Key Prompt Safeguards:
1. **Direct Entailment Only**: *"Extract what the text says. Do NOT invent what the text does not say."*
2. **Persistent Relationships vs Transient Events**:
   - `Alice interviewed Bob` -> **Event**: `INTERVIEW/CONVERSATION`.
   - `Alice is married to Bob` -> **Relationship**: `MARRIED_TO`.
3. **Structured JSON Output**:
   The output structure requires:
   ```json
   {
     "entities": [{"canonical_name": "...", "mention": "...", "type": "...", "attributes": {}}],
     "relationships": [{"subject": "...", "predicate": "...", "object": "...", "certainty": "..."}],
     "events": [{"id": "...", "type": "...", "participants": [], "location": null}],
     "state_changes": [{"entity": "...", "property": "...", "previous_value": null, "new_value": "..."}],
     "temporal_relations": [{"event_1": "...", "relation": "BEFORE", "event_2": "..."}]
   }
   ```

---

## 3. Coreference Resolution & Clustering (`entity_resolution.py`)

When an LLM outputs raw mentions across multiple chunks, the same entity appears under diverse surface forms:
- Chunk 1: `"Alice"`
- Chunk 2: `"Alice Sterling"`
- Chunk 3: `"Captain Sterling"`

### Matching Heuristics:
1. **Exact & Alias Match**: Case-insensitive normalization. If `normalized(mention) == normalized(canonical)` or matches an existing alias -> **Confidence = 1.0**.
2. **Jaccard Token Similarity**:
   $$\text{sim}(A, B) = \frac{|Tokens(A) \cap Tokens(B)|}{|Tokens(A) \cup Tokens(B)|}$$
3. **Substring Containment**:
   If `"Alice"` is a strict substring of `"Alice Sterling"`, score is $\frac{\text{len}(A)}{\text{len}(B)}$.
4. **Clustering Threshold**:
   Pairs scoring $\ge 0.85$ are merged into a single canonical entity cluster, preserving all surface forms as `EntityAlias` records.

---

## 4. Rule-Based Contradiction Detection (SRS REQ-27)

Contradictions are decided by deterministic rules in [`app/consistency/`](../../app/consistency/), orchestrated by [`ConsistencyService`](../../app/services/consistency_service.py). The authoritative list of implemented and deferred rules is [`consistency_engine.md`](consistency_engine.md); in short:

- **Implemented:** immutable facts, age monotonicity (REQ-23), dead-then-alive status (REQ-26, status part), incompatible relationship pairs and a changing `FATHER_OF` (REQ-25), temporal cycles.
- **Deferred:** location clashes (REQ-24) and speaking/acting after death (REQ-26) — the frozen schema and current extraction contract do not represent event location/time or speakers.

### Temporal Ordering Cycles via DFS (implemented as `TEMPORAL_CYCLE`)
- Build a directed graph from `temporal_relations` (`BEFORE` $\to$ directed edge $A \to B$; `AFTER` $\to B \to A$).
- Run Depth-First Search with 3-color node states (0: unvisited, 1: visiting, 2: visited).
- If a node is visited while in state 1, a directed cycle exists. Backtrack the path and flag as a `CYCLE` contradiction.
