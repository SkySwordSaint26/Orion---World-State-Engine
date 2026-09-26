# LLM Extraction Pipeline — Status & Real-Data Evaluation

Date: 2026-09-26 · Model: `qwen2.5:7b` (Q4_K_M, Ollama) on an RTX 4050 6 GB laptop GPU (12% of the model offloaded to CPU)

> **Update 2026-09-27:** a new extraction pipeline in `WSE/` (encoder models + deterministic rules + NuExtract for
> facts) completes 4/4 stories and beats this pipeline on every metric. See
> [`wse_extraction_plan.md`](wse_extraction_plan.md), Phase 8.

**Bottom line:** the extraction architecture is well designed and thoroughly built, but on real data with qwen2.5:7b it
does not work yet. With default settings, 0 of 4 stories completed. The best configuration tried completed 1 of 4.

---

## 1. What the system does

Orion turns fiction manuscripts into a versioned "world state": characters, locations, objects, relationships, events
and facts, tracked per chapter. It then flags contradictions (age going down, dead character speaking, father changing)
using deterministic rules, never an LLM (SRS REQ-27). The LLM is used only for extraction (and character chat).

## 2. How extraction works

```
chapter → sentences with exact offsets → chunks of whole sentences (8,000 chars, 2-sentence overlap)
  → LLM, one of two modes:
     monolithic (default): one prompt per chunk returns everything as JSON
     split (opt-in):       4 calls per chunk: 1 entities → 2 relationships → 3 events → 4 facts
  → checks: every item must quote its evidence word-for-word from the text
  → rule-based entity matching → linking names to pronouns (one narrow case) → database → contradiction rules
```

- Mode is selected by `EXTRACTION_PIPELINE` (`monolithic` | `split`).
- In split mode the model only names things and quotes evidence; code finds exact positions. Invented or misquoted
  items are rejected. `ALLOW_PARTIAL_STAGE=true` drops invalid items instead of failing the stage.
- Output is scored against the gold annotations with `python -m app.evaluation` (`convert`, `predict`, `score`, `demo`).

Code: `backend/app/pipeline/` (extractor, LLM client, `stages/`, prompts), `backend/app/preprocessing/`,
`backend/app/contracts/`, `backend/app/resolution/`, `backend/app/coreference/`, `backend/app/evaluation/`.
Design details: `backend/.ai/context/pipeline_deep_dive.md`.

## 3. How much is built

| Part | State |
|---|---|
| Sentence splitting, chunking, typed data models, gold export, scoring tool | Done; all 505 tests pass (mocked LLM only) |
| Split 4-stage pipeline with evidence checks | Done, but opt-in; not the default |
| Entity matching / linking names and pronouns | Done, rule-based and deliberately conservative ("he" linked only at sentence start) |
| Contradiction rules | 6 rules; location clash (REQ-24) and acting after death (REQ-26) deferred |
| Standardising labels (predicates, event types, property names) | Not built; free-form LLM labels go straight into the database |
| Retries, output repair, handling model repetition loops | Not built |
| Git state | All of Phases 3–7 is **uncommitted** (`stages/`, `preprocessing/`, `resolution/`, `coreference/`, `evaluation/` untracked) |

## 4. Real-data results

Data: the 4 parts of "Accounts From a Lonely Broadcast Station" with the teammate gold annotations.

| Setup | Parts completed | Result |
|---|---|---|
| split, strict (default settings) | **0/4** | one bad item fails the whole chapter |
| split, partial (`ALLOW_PARTIAL_STAGE=true`) | **0/4** | repetition loop until the output limit, or every item in a chunk invalid |
| monolithic | 2/4 | produces no text positions, so every position-based score is 0; named 11 of 235 gold mention strings |
| split, partial, 2,000-char chunks | 1/4 (part 4) | scores below |

Scores for part 4 (split, partial, 2,000-char chunks):

| Metric | P | R | F1 |
|---|---|---|---|
| mentions (overlapping span) | 0.68 | 0.64 | 0.66 |
| mentions (exact span) | 0.44 | 0.42 | 0.43 |
| mentions (exact span + type) | 0.24 | 0.22 | 0.23 |
| event triggers (exact) | 0.19 | 0.23 | 0.21 |
| event triggers (exact + type) | 0.05 | 0.07 | 0.06 |
| event arguments | 0.03 | 0.02 | 0.02 |
| relationships | 0.00 | 0.00 | 0.00 |
| facts | 0.02 | 0.33 | 0.03 |

The gold set has only about 1 relationship and 2–3 facts per story, so those two metrics are noise either way.

Latency per chunk (median / max): stage 1 6s / 145s, stage 2 2s / 19s, stage 3 22s / 146s, stage 4 20s / 48s.
Part 4 took 595s end to end. The SRS budget is 10s per chapter.

## 5. Why it fails (most important first)

1. **Repetition loops on large chunks.** E.g. `{"text": "Dan", "type": "character"}` repeated 314 times until
   `OLLAMA_NUM_PREDICT` (4096) ran out, leaving invalid JSON. Hit both modes.
2. **Evidence not copied exactly.** qwen prefixes quotes with made-up ids (`"M0011: I'm twenty four…"`), reuses one
   trigger for unrelated quotes, and writes `M0` when labels start at `M1`.
3. **All-or-nothing failure.** One chunk where every item is invalid fails the whole chapter, even in partial mode.
4. **Free-form labels.** The model invents types like `FEEL`, `OATH`, `LEADS_TO`, `property: "type"`. The prompts
   suggest vocabularies but nothing enforces them.
5. **Speed.** Far over the SRS budget on this hardware.

## 6. Other finding

`llm_client.chat()` (character chat) still has a silent fallback: if Ollama fails it returns a canned "all entity
attributes and relationships have been verified. No critical timeline conflicts detected." That is a fabricated answer
shown to the user, the same class of problem already fixed in extraction.

## 7. Suggested next steps

1. Make small chunks (~2,000 chars) the default and pass Ollama's `repeat_penalty` option.
2. Strip id prefixes from evidence before the verbatim check.
3. Skip and log a fully invalid chunk instead of failing the whole chapter.
4. Enforce the label vocabularies in each stage's validation.
5. Remove the chat fallback.
6. Commit Phases 3–7.

## 8. Reproducing

From `backend/` with the venv active:

```bash
python -m app.evaluation convert ../accounts_from_a_lonely_broadcast_station_orion_annotation/*.json \
  --text-dir "../Accounts From a Lonely Broadcast Station" --out-dir GOLD
python -m app.evaluation predict --gold-dir GOLD --out-dir PRED --pipeline split --log-calls calls.jsonl
ALLOW_PARTIAL_STAGE=true python -m app.evaluation predict --gold-dir GOLD --out-dir PRED_PARTIAL --pipeline split
python -m app.evaluation score GOLD PRED
```

The 2,000-char run changed `app.pipeline.extractor.CHUNK_MAX_CHARS` in-process; there is no setting for it yet.

---

## 9. Update: schema-constrained split stages (2026-09-26)

Change: each split stage sends a JSON schema to Ollama (`format`): every key required, `evidence` first, mention
labels restricted to the chunk's labels, gold vocabularies as enums, lists capped at `max(8, 2 × NEW sentences)`.
Validation enforces the same vocabularies for providers that ignore the schema. Stage 3 is skipped when a chunk has
no mentions. Details: `backend/.ai/context/pipeline_deep_dive.md` §1e.

Same baseline setup (8,000-char chunks, 4 parts):

| | Before | After |
|---|---|---|
| split strict: parts completed | 0/4 | 0/4 (all remaining failures are evidence-related) |
| split partial: parts completed | 0/4 | 1/4 (part 3) |
| invalid JSON | 4 | 2 (see below) |
| trigger not in its own evidence | 8 | 1 (evidence-first ordering) |
| invalid labels / out-of-list values | occurred (`M0`, `FEEL`, …) | 0 (cannot be generated) |
| evidence not verbatim | 7 | 6 (unchanged: a schema cannot enforce a quote) |
| generation speed | ~100 chars/s | ~100 chars/s |

Part 3 (split partial) now scores mentions 0.59 F1 (overlapping spans), 0.38 exact, 0.31 typed; triggers 0.17.
Monolithic scored 0 on all of these for the same part.

**The 2 remaining invalid-JSON failures are output overflow, not a cap failure.** Part 1 facts looped (one evidence quote
×69), and part 2 events had 45 genuine events at ~350 chars each. Either way the 4,096-token output limit ran out
before the cap (up to 224 items on an 8,000-char chunk) could stop it. The cap only works when the chunk is small
enough that `2 × sentences` items fit in the output limit, so smaller chunks (~2,000 chars, cap ≈ 40) are now a
prerequisite, not an optional follow-up.

**Side effect:** the gold predicate list has no `FATHER_OF` or `DEAD_AT_HANDS_OF`, so split output can no longer
trigger the consistency rules keyed on them (`consistency/vocabulary.py`, REQ-25 "stated father changes").
