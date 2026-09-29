# LLM Pipeline — Phase Status

Date: 2026-09-26 · Companion to [`llm_pipeline_status.md`](llm_pipeline_status.md) (real-data evaluation details)

Phase numbering follows `backend/.ai/context/pipeline_deep_dive.md` and `backend/.ai/ARCHITECTURE.md`. Every phase has
its own test file (`backend/app/tests/test_phase*.py`) and all 505 tests pass, but every test uses a mocked LLM, so
"tests pass" only proves the code does what it was written to do.

"On real data" below means the 4 parts of "Accounts From a Lonely Broadcast Station" run through `qwen2.5:7b` and
scored against the gold annotations.

## Phase table

| Phase | What it does | Built | Works on real data? |
|---|---|---|---|
| **1. Execution** | Runs a job's chapters in order, one transaction per chapter, stops at the first failure, recounts progress, no silent LLM fallback | Done | **Not exercised.** No end-to-end API run with qwen has been done. The loud-failure behaviour works as designed: every failed extraction raised an error instead of writing data. |
| **2. Consistency rules** | 6 fixed rules: immutable facts, age, dead-then-alive, incompatible relationships, `FATHER_OF` changing, temporal cycles | Partial: location (REQ-24) and acting after death (REQ-26) deferred | **Not exercised**, since no real extraction reached the database. The rules match raw LLM strings (`age` vs `Age`, `FATHER_OF` vs `PARENT_OF`), so real output will likely cause missed contradictions. |
| **3. Preprocessing** | Paragraphs, sentences with exact offsets, sentence-aligned chunks | Done | **Yes, verified.** 686 sentences across the 4 texts, 0 bad offsets, no sentence cut. |
| **4. Data contracts** | Typed items with source-location info, checks at stage boundaries | Done | **Yes.** Carried all 126 mentions from part 4 through to the gold format intact. For monolithic output, the source location is only the whole chunk, by design. |
| **4.5 Gold format** | Converts extraction output to the gold schema and lists what's missing | Done | **Yes.** Converted all 4 annotation files and reports gaps correctly (e.g. `FEEL is not a gold event type`). |
| **5. Entity resolution** | Matches each mention to one entity (exact, normalized, alias, nickname, subset of a name, one narrow pronoun case); leaves ambiguous ones unresolved | Done; no fuzzy matching, most pronouns not handled | **Never measured.** Runs only inside `WorldStateService`, which needs the database; the evaluation tool skips it. |
| **6. Coreference** | Groups mentions of the same entity; fills in missing entity links on relationships, events and facts | Done, deliberately conservative | **Never measured.** Every prediction has 0 coreference clusters because the evaluation never runs Phases 5–6. REQ-17/18 has no real-data score. |
| **7. Split extraction** | 4 LLM stages: entities → relationships → events → facts, each checked strictly | Done, opt-in (default is still monolithic) | **No.** 0/4 stories finished with default settings, 1/4 with 2,000-char chunks + `ALLOW_PARTIAL_STAGE=true`. Causes: repetition loops, evidence not copied exactly, invalid labels, all-or-nothing failure. |
| **7.1 Evidence grounding** | Code, not the model, decides which sentence an item came from, using the exact quote | Done | **Partly.** An exact quote pins the right sentence. qwen often misquotes (fake `M0011:` prefixes, wrong sentence paired with a trigger), so many items are rejected. The check works; the model fails it. |
| **7.2 Code-located mentions** | The model lists names; code finds every occurrence with exact offsets | Done | **Best-performing part.** Part 4: 0.66 F1 with overlapping spans, 0.43 exact. Losses: wrong type (0.23 once type must match), made-up phrases ("the bird"), the loop in part 2. |
| **Monolithic extraction** | One LLM call per chunk (legacy, current default) | Done | **No.** 2/4 finished, but with no text positions (score 0), only 11 of 235 gold mention strings named, and 2/4 broke on repetition loops. |
| **Evaluation tool** | `python -m app.evaluation` convert / predict / score / demo | Done | **Yes**, produced every number above. Gap: does not run Phases 5–6, so entity resolution and coreference are invisible to it. |

## How far along we are

- **Built:** about 90% of what was planned. Every numbered phase exists and has tests.
- **Working on real data:** only the parts that don't use the LLM (Phases 3, 4, 4.5 and the evaluation tool).
- **Where it breaks:** at the LLM boundary (Phase 7 and monolithic). Everything after it (Phases 5, 6, 2, 1) has never
  received real extraction output, so its real-world quality is unknown, not proven bad.
- **Biggest blind spot:** Phases 5–6 (coreference, REQ-17/18) are a high-priority SRS feature with no real-data
  measurement at all.

## Order to fix

1. **Make Phase 7 finish reliably:** ~2,000-char chunks, schema-constrained output per stage (Ollama `format` with a
   JSON schema), strip evidence prefixes, a lenient failure policy (drop bad items, skip and log a fully invalid chunk).
2. **Let the evaluation run Phases 5–6** so entity resolution and coreference get a score.
3. **Do one end-to-end API run** through Phases 1–2 on a real manuscript to see which contradictions (and false
   ones) appear.
