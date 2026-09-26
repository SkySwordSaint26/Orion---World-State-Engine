# WSE Extraction Pipeline v2 — Phase Plan

Date: 2026-09-26 · Research basis: [`nlp_tools_research.md`](nlp_tools_research.md) · Baseline:
[`llm_pipeline_status.md`](llm_pipeline_status.md)

**Goal:** complete extraction only. From a story's text, produce a full `orion_gold_v1` document: typed mentions
(with `mention_kind`), coreference clusters, events (trigger, type, participants), relationships, facts, temporal
expressions and temporal relations, all with exact offsets. World-state integration, contradictions and the API are
out of scope.

**Decisions (2026-09-26)**
- The old WSE prototype (commit `76cbb07`) is deleted; `WSE/` holds only the new pipeline. The old code stays
  recoverable from git history.
- Orion is **non-commercial**, so non-commercial model licences are allowed: Maverick's coreference model (LitBank
  checkpoint) and NuExtract 2.0 4B are candidates.

**Ground rules**
- The current pipeline (`backend/`) stays as it is. New code lives in `WSE/`.
- **No duplicated logic.** WSE imports these backend modules from `../backend`; they are stdlib-only (verified in a bare
  Python 3.12):
  - `app.preprocessing`: sentences and paragraphs with exact offsets, chunking;
  - `app.contracts.gold`: the closed vocabularies;
  - `app.evaluation`: `convert`, `score`, `schema_errors`.
- **Output = the gold format**, so both pipelines are scored by the same scorer on the same 4 stories.
- **Encoder models for spans, LLM only for meaning.** Every LLM call is schema-constrained (Ollama `format`).
- **One model on the GPU at a time** (6 GB; qwen2.5:7b alone takes 5.4 GB). Encoder stages run first; LLM stages
  follow.
- **Every phase ends with measured numbers**, recorded in this doc, and one small test for its non-trivial logic.

## Layout

```
WSE/
  wse/
    __main__.py    CLI: predict (gold dir → pred dir), score
    pipeline.py    runs the stages in order on one story; owns the gold document being built
    mentions.py    phase 2
    coref.py       phase 3
    events.py      phase 4
    relations.py   phase 5 (relationships + facts)
    temporal.py    phase 6
    llm.py         the one Ollama call: prompt + JSON schema → parsed JSON (stdlib urllib)
    evaluate.py    coreference metric + pronoun-aware mention scoring, on top of the backend scorer
  tests/
  requirements.txt  (own venv, Python 3.12)
```

One module per stage; no base classes or registries.

## Baselines to beat (current backend pipeline, qwen2.5:7b)

| Metric | Best so far | Where |
|---|---|---|
| Stories completed | 1/4 | split + partial |
| mentions_overlap F1 | 0.59 / 0.66 | part 3 / part 4 |
| mentions_typed F1 | 0.31 / 0.23 | part 3 / part 4 |
| triggers_exact F1 | 0.17 / 0.21 | part 3 / part 4 |
| triggers_typed F1 | 0.08 / 0.06 | part 3 / part 4 |
| event_arguments F1 | 0.03 / 0.02 | part 3 / part 4 |
| coreference | never measured | — |
| temporal expressions | 0 (not extracted) | — |
| Latency | 137–595 s per story part | — |

---

## Phase 0 — Environment and tool check (no pipeline code)

**Do:**
- Create the `WSE/.venv` venv (Python 3.12) and install torch with CUDA, `gliner2`, `fastcoref` and `booknlp`
  (BookNLP brings spaCy; it also requires tensorflow).
- Run each tool once on part 1 and record: install problems, VRAM use, time, and a sample of the output.

**Decide:**
- **BookNLP: go or no-go.** It is the only fiction-trained option for coreference and events. If it won't install or
  run, the fallback is fastcoref for coreference and LLM trigger detection for events.
- Whether GLiNER2 runs on CPU or GPU, based on measured speed.

**Done when:** every tool has either run on part 1 or been ruled out with a recorded reason.

## Phase 1 — Skeleton and evaluation loop

**Do:**
- `wse predict --gold-dir G --out-dir P` writes one gold document per story (empty lists at first). It uses backend
  preprocessing for sentences and offsets.
- `wse score G P` runs the backend scorer plus two WSE additions:
  - a **coreference metric** (B³ over gold clusters; the backend scorer has none);
  - **pronoun-aware mention scoring**: pronoun mentions are scored separately, because the gold never annotates
    pronouns. Otherwise every correct pronoun would count as a false positive.

**Done when:** an empty prediction is schema-valid (backend `schema_errors`) and scores 0 on every metric; one test
covers the coreference metric.

## Phase 2 — Mentions (proper + nominal)

**Do:**
- Run GLiNER2 over sentence windows, with our 5 types as labels and a one-line description each.
- `mention_kind`: `proper` or `nominal`, decided from the spaCy part-of-speech of the span's head word.
- Compare against BookNLP entities, and against GLiNER2 + BookNLP combined. Keep whichever scores best.

**Done when:** 4/4 stories complete, and on all 4:
- `mentions_overlap` F1 is at or above the baseline (0.59–0.66);
- `mentions_typed` F1 is clearly above it (0.23–0.31).

## Phase 3 — Coreference and pronouns

**Do:**
- Compare over the whole story, not per chunk (coreference needs long-range context): BookNLP coreference, Maverick
  (LitBank fiction checkpoint, CPU, word offsets aligned back to the text) and fastcoref FCoref. Keep whichever
  scores best.
- Add pronoun mentions (`mention_kind: pronominal`), including first-person "I" for the narrator.
- Align coreference spans to the phase-2 mentions by span overlap.
- Build `coreference_clusters` from mention ids.

**Done when:** the coreference metric is measured on all 4 stories (the first number ever for REQ-17/18), and every
cluster member is a mention id in the document.

## Phase 4 — Events

**Do:**
- Triggers come from BookNLP realis events, giving exact word offsets. If BookNLP was ruled out in Phase 0, an LLM
  stage finds triggers and code checks them against the text.
- One schema-constrained LLM call per chunk assigns each trigger a type (`EVENT_TYPES`) and participants. Participants
  are limited to the mention ids in that trigger's sentence; roles come from `PARTICIPANT_ROLES`.
- The model never writes offsets or free text that has to match the source.

**Done when:** on all 4 stories, `triggers_exact`, `triggers_typed` and `event_arguments` beat the baseline
(0.17–0.21 / 0.06–0.08 / 0.02–0.03).

## Phase 5 — Relationships and facts

**Do:**
- First LLM stage in the pipeline, so it brings back the GPU handoff Phase 4 built and removed (see Phase 4 results):
  free the encoder models before the LLM stage, and unload the LLM (`keep_alive: 0`) after it.
- A schema-constrained LLM call per chunk, working with **entities**: the chunk's mentions grouped by coreference
  cluster, one label per entity.
- It outputs relationships (`PREDICATES`) and facts (`FACT_PROPERTIES`). Each item cites its sentence by choosing
  from an enum of the chunk's sentence ids; free-text evidence is not used, which removes the quoting failures.
- Code picks the subject and object mention ids from within that sentence.
- Also run GLiNER2 relation extraction and keep whichever scores better.

**Done when:** both metrics are measured on all 4 stories and the outputs are reviewed by hand. The gold has only
about 1 relationship and 2–3 facts per story, so the scores alone can't judge quality.

## Phase 6 — Temporal expressions and relations

**Do:**
- Temporal expressions: add GLiNER2 labels for the gold types (`absolute_time`, `relative_time`, `duration`,
  `sequence_marker`), reusing the Phase 2 model. Try HeidelTime (Java plus TreeTagger) only if GLiNER2 scores
  poorly.
- Temporal relations: a schema-constrained LLM call over pairs of events in the same or adjacent sentences
  (`TEMPORAL_RELATIONS`).

**Done when:** `temporal_expressions` is measured on all 4 stories (gold has 9–18 per story). Temporal relations can't
be scored, since the gold has none; review them by hand.

## Phase 7 — LLM comparison

**Do:** run the LLM stages (4–6) with qwen2.5:7b, Qwen3.5 4B, and NuExtract 2.0 4B (fits fully on the GPU).
Record scores and latency.

**Done when:** one model is chosen from the evaluation numbers and recorded here with the reason.

## Phase 8 — Full comparison and handover

**Do:**
- Run the complete pipeline on all 4 stories and compare with the backend pipeline on every metric and on latency.
- Write up what's ready to feed into the backend's world-state integration.

**Done when:** the comparison table is in this doc and the go/no-go for integration is stated.

---

## Out of scope (for now)

- World-state integration, contradictions, API, database.
- Quote-speaker attribution (ModernBookNLP). The gold schema has no field for it; it's needed later for REQ-26.
- Fine-tuning. The gold set is too small.
- LitBank as a second evaluation set. Add it if the 4 stories prove too few or too noisy.

## Risks

| Risk | Mitigation |
|---|---|
| BookNLP's dependencies (tensorflow, older transformers) don't install on 3.12 | Phase 0 go/no-go; fallbacks named in Phases 3–4 |
| Encoders and the LLM compete for 6 GB of VRAM | Run stages in order, release the encoder models before LLM stages, or run the encoders on CPU |
| Gold is noisy (~69% of occurrences annotated, 25 spans cut inside words, no pronouns) | Pronoun-aware scoring; read `gold_excluded`; review by hand where the gold is thin |
| Licences | Project is non-commercial (decided), so Maverick and NuExtract 4B are allowed; revisit if that changes |
| Encoder models are trained on news/Wikipedia | Measure first; LitBank-trained BookNLP is the fiction-specific option |

## Results log

### Phase 0 — done (2026-09-26)

Environment: `WSE/.venv`, Python 3.12, torch 2.14.0 with CUDA 13.0 on the RTX 4050; versions pinned in
`WSE/requirements.txt`. Tests ran on part 1 (2,973 words); scores use the backend scorer against gold.

| Tool | Runs? | Time (part 1) | VRAM | Result |
|---|---|---|---|---|
| **GLiNER2 large** | yes | 1.3 s GPU / 15.8 s CPU (+ load) | 3.1 GB | Mentions F1: overlap **0.61**, exact **0.55**, typed **0.39**; 0 bad offsets. Beats qwen's best (0.43 exact, 0.31 typed), which never finished part 1. |
| GLiNER2 base | yes | 0.8 s GPU / 6.3 s CPU | 1.7 GB | overlap 0.56, exact 0.49, typed 0.33 |
| **BookNLP big** | yes, after 2 fixes | 3.1 s (+ 88 s first load, incl. downloads) | 1.7 GB | 0 offset mismatches. Coreference looks good (narrator `I/me/my`; `an old man → He/His/him`). **Events:** 127 triggers (gold 37), trigger F1 0.19. **Mentions weak:** exact 0.12, typed 0.10 (includes articles; no `object` type). |
| **FCoref** | yes | 0.5 s (+ 6 s load) | 0.6 GB | 58 clusters; also clusters objects (`the fog … It`, `the song … it`); spans clean |
| **Maverick (LitBank)** | yes, on CPU only | 30 s CPU (+ 12 s load) | GPU runs out of memory (>5.6 GB) | Richest clusters (narrator ×178; station `It/here/this place/the tower/the building`; town; old man). Its `clusters_char_offsets` are broken, so offsets must come from aligning its word offsets to the text. |
| LingMessCoref | **no** | — | — | Current `transformers` has no default attention implementation for Longformer (it would need `attn_implementation="eager"` passed in). Dropped: FCoref covers the fastcoref option. |

**Decisions**
- **BookNLP: GO**, for coreference and event triggers, not for mentions.
- **Mentions: GLiNER2 large** on the GPU (fall back to base if VRAM gets tight).
- **Coreference:** BookNLP, Maverick (CPU) and FCoref all go into the Phase 3 comparison.
- One model on the GPU at a time: the peak so far is 3.1 GB, which fits.

**Fixes the tools need (reproduce in Phase 1 setup)**
1. `pip install --no-deps booknlp`: its declared `tensorflow` dependency is never imported, and tensorflow's protobuf
   requirement conflicts with Maverick's `protobuf==3.20`.
2. `setuptools<81`: BookNLP imports `pkg_resources`.
3. BookNLP checkpoints (`~/booknlp_models/*.model`): remove the stale `bert.embeddings.position_ids` key once.
   Current `transformers` rebuilds it, and strict loading rejects it. Done by hand in Phase 0; automated in Phase 3
   with the first code that loads BookNLP.
4. Maverick: its Lightning checkpoint needs `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`, which disables PyTorch's
   "weights only" safety check. Acceptable only for this known published checkpoint.

### Phase 1 — done (2026-09-26)

Built in `WSE/`:
- `wse/__init__.py`: puts `../backend` on the import path, so WSE reuses its modules without copying them.
- `wse/pipeline.py`: `extract(story_id, text)` builds the gold document, runs `STAGES` (empty for now) and fails loudly
  on any schema violation (backend `schema_errors`).
- `wse/evaluate.py`: backend scorer, plus pronoun-aware mention scoring and `coreference_b3` (standard entity-overlap
  B-cubed; mentions aligned by span).
- `wse/__main__.py`: `python -m wse predict --gold-dir G --out-dir P` and `python -m wse score G P`.
- `tests/test_phase1.py`: 6 tests (B³ identical/merge/empty cases, pronouns, gold defects, empty output is
  schema-valid).
- Gold set: `WSE/data/gold/` (generated with the backend converter; command in `wse/__main__.py`).

Checks:
- Empty prediction: 0 on every metric (micro average over 4 stories).
- Gold scored against itself: `coreference_b3` 1.0 on every story. `mentions_exact` precision is 0.958 because the
  scorer excludes the 17 broken gold spans.

**Gold defect found:** 19 gold coreference-cluster members (8 / 10 / 1 / 0 per part) reference mention ids that don't
exist in the gold mentions. The metric leaves them out and reports them as `gold_missing`.

Changes to the plan: no `run` command yet (`predict` covers evaluation; add `run` when a non-gold story needs it). The
BookNLP checkpoint fix moves to Phase 3.

### Phase 2 — done (2026-09-26)

Built: `wse/mentions.py`, registered as the first stage in `wse/pipeline.py`:
- GLiNER2 large, the library's long-document windows, threshold 0.5.
- One mention per span (the most confident type wins); pronouns dropped (Phase 3 owns them).
- `mention_kind` from spaCy's part of speech for the span's head word.
- Test: `tests/test_phase2.py`.

Chosen on all 4 stories (micro F1: overlap / exact / typed):

| Variant | Overlap | Exact | Typed |
|---|---|---|---|
| Library long windows, th 0.5, generic labels | 0.624 | 0.582 | 0.402 |
| Paragraph windows (best threshold, 0.6) | 0.555 | 0.512 | 0.350 |
| **Long windows, th 0.5, labels stating the annotation conventions** (animals are characters; weather/nature/media are `other`; doors/stairs are locations; general wording, nothing story-specific) | 0.604 | 0.558 | **0.471** |
| … + BookNLP non-pronoun mentions GLiNER missed (articles stripped) | 0.570 | 0.520 | 0.441 |

Pipeline run: **4/4 stories complete**, 1–2 s per story (+ ~11 s model load once). Micro F1 over 4 stories:
overlap **0.619**, exact **0.572**, typed **0.483** (precision 0.40–0.51, recall 0.61–0.79).

Against the qwen baseline (the only parts qwen finished):

| | Part 3: WSE / qwen | Part 4: WSE / qwen |
|---|---|---|
| overlap F1 | 0.543 / 0.590 | 0.632 / 0.661 |
| exact F1 | 0.474 / 0.377 | 0.598 / 0.431 |
| typed F1 | 0.416 / 0.311 | 0.496 / 0.231 |

**Done criteria:**
- 4/4 stories complete: **met**.
- Typed F1 clearly above baseline: **met** (+0.11 / +0.27).
- Overlap at or above baseline: **missed by 0.03–0.05**. WSE's recall is higher (part 4: 0.83 vs 0.64) but its
  precision is lower (0.51 vs 0.68).

**Why precision is low:** most unmatched predictions are real concrete mentions the annotator did not mark (`desk`,
`chair`, `glass`, `teeth`, `scalpels`, `Grandma`, `flannel shirt`). About a quarter are missed occurrences of forms
the gold does annotate (`headset`, `ground`, `stairs`). The gold marks salient entities, not every entity. Tuning the
threshold to match one annotator's sense of salience would be overfitting. If salience matters for the product, the
Phase 3 coreference chains are a principled signal for it (entities mentioned repeatedly).

### Phase 3 — done (2026-09-26)

Built: `wse/coref.py`, registered as the second stage:
- BookNLP (big) over the whole story; its output is cached per text, since Phase 4's events reuse it.
- `link()` maps coreference spans onto Phase 2 mentions (the scorer's `align`) and adds pronoun mentions, typed from
  their cluster. A pronoun-only chain is a character when personal; an "it"-only chain is skipped; no orphan
  pronouns.
- `merge_same_text()`: joins non-pronoun mentions with the same text and type (a union-find over mention ids).
- The BookNLP checkpoint fix is automated (`strip_position_ids` runs if loading fails on the stale key).
- `wse/evaluate.py` adds `coreference_b3_linked`: B³ on only the mentions both sides have (linking quality apart from
  the gold's selective mention annotation).
- Tests: `tests/test_phase3.py` (4).
- Maverick and FCoref were removed from the code and the venv after losing the comparison.

Comparison on the 4 stories (micro B³ F1; linked-only in parentheses as P / R / F1):

| Backend | Model only | + same-text merge |
|---|---|---|
| (no model) | — | 0.483 (0.90 / 0.60 / 0.72) |
| **BookNLP** | 0.376 (0.97 / 0.26 / 0.41) | **0.488 (0.90 / 0.65 / 0.75)** |
| FCoref | 0.396 (0.86 / 0.36 / 0.51) | 0.443 (0.79 / 0.67 / 0.73) |
| Maverick (CPU, 35 s/story) | 0.374 (0.79 / 0.31 / 0.44) | 0.447 (0.78 / 0.66 / 0.72) |

Pipeline run (mentions + coreference), 4/4 stories. ~5 s per story on GPU; the first story takes 31 s including
model loads.

| | Part 1 | Part 2 | Part 3 | Part 4 | Micro |
|---|---|---|---|---|---|
| coreference_b3 F1 | 0.357 | 0.598 | 0.370 | 0.581 | **0.488** |
| coreference_b3_linked F1 | 0.653 | 0.837 | 0.592 | 0.823 | **0.750** (P 0.895) |
| pronoun mentions added | 213 | 364 | 200 | 341 | 1,118 |

Mention scores are unchanged from Phase 2 (coreference never alters named mentions).

**What the gold cannot show:** it has no pronouns and its clusters are mostly repeated strings (`door`, `nest`,
`fog`). So "merge only" nearly ties the models, and pronoun linking (REQ-17) is unmeasured. Hand check of part 4's
largest clusters:
- narrator `I/me/my/myself` (263 mentions);
- `Dan/Daniel + he/him/his`, plus the `I/you` in Dan's own dialogue (BookNLP's coreference is quote-aware);
- `we/us/our`;
- object chains (`nest`, `fog`, `fire escape → it`).

This is the first coreference number for Orion.

### Phase 4 — done (2026-09-26): events are deterministic

**Change from the plan:** the plan had the LLM assign event types and participants. On real data qwen2.5:7b made
both **worse than no LLM at all**, so events are deterministic. Phase 7 can retest a stronger LLM on typing, on top of
these triggers.

Built: `wse/events.py`, registered as the third stage:
- triggers are BookNLP tokens marked as realis EVENT and tagged VERB (reusing the coreference run's cached output);
- type from a general English verb lexicon over the lemma (nothing story-specific), `OTHER` otherwise;
- participants from BookNLP's dependency parse: subject → agent, passive subject → patient, a conjoined verb shares
  its head's subject, direct object → patient, dative → recipient, object of a place preposition → location.
  Possessive determiners are never participants.

`wse/evaluate.py` adds `event_arguments_entity`: (event, role, entity) through coreference clusters, because the gold
names a participant by any mention of the entity ("Evelyn" for "*I* started").

Gold ceiling: BookNLP proposes 726 triggers for 187 gold events. Only 90 match exactly (103 overlap), so trigger
recall is capped near 0.5. 68% of gold events are `OTHER`.

Comparison (micro F1 over the 4 stories unless noted):

| Variant | Trigger exact | Trigger typed | Args (mention) | Args (entity) |
|---|---|---|---|---|
| LLM v1: qwen labels type + participants per 1,500-char chunk, `NONE` drops | 0.253 | 0.100 | 0.012 | 0.049 |
| LLM v2: inline `[T3 word]` markers, `OTHER`-default prompt, role conventions (parts 1+3) | 0.183 | 0.050 | 0.011 | 0.021 |
| LLM v2, one call per sentence (parts 1+3) | 0.237 | 0.066 | 0.008 | 0.023 |
| B0: all BookNLP triggers, `OTHER`, no LLM | 0.200 | 0.138 | 0 | 0 |
| B2: verb triggers + dependency participants | 0.243 | 0.172 | 0.022 | 0.070 |
| **B4: B2 + verb lexicon types (chosen)** | **0.243** | **0.195** | **0.022** | **0.070** |

Why the LLM lost:
- It avoided `OTHER`: gold `OTHER` became `DESTRUCTION`/`CREATION`/`TRAVEL`/`ATTACK`.
- It dropped 37 of the 90 gold-matching triggers as `NONE`, including plain actions (`smacked`, `sank`, `slammed`,
  `fallen`); with ~20 triggers per chunk it lost track of which id was which.
- Prompt fixes made it more conservative, not more accurate.

Pipeline run (mentions + coreference + events): 4/4 stories, **45 s for all 4** (the qwen version: 13 min).
Mention and coreference scores are unchanged.

| Per part | Trigger exact | Trigger typed | Args (mention) | Args (entity) |
|---|---|---|---|---|
| Part 1 | 0.205 | 0.189 | 0.033 | 0.046 |
| Part 2 | 0.250 | 0.210 | 0.030 | 0.096 |
| Part 3 (qwen baseline) | 0.255 (0.167) | 0.184 (0.083) | **0.000 (0.026)** | 0.028 |
| Part 4 (qwen baseline) | 0.250 (0.206) | 0.192 (0.059) | 0.023 (0.022) | 0.084 |

**Done criteria:** trigger exact and typed beat the baseline on parts 3 and 4: **met**. Mention-level arguments:
**tied on part 4, missed on part 3**. Arguments are the weakest part: only 86 triggers match the gold, and the gold
often names a participant the sentence doesn't contain.

**Lessons for the LLM phases:**
- The 6 GB GPU holds the encoders or qwen2.5:7b, not both. Free the encoder models before an LLM stage.
- Ollama keeps a model loaded for 5 minutes, so unload it (`keep_alive: 0`) before the next story's encoders load.
  Otherwise the encoders run out of memory, which happened in this phase's first run.
- Treat a reply with `done_reason == "length"` as an error.
- Deleted until Phase 5 needs them again: `wse/llm.py` and the GPU-release stages.

### Phase 5 — done (2026-09-27): relationships and facts with NuExtract 2.0 4B

The gold has only **4 relationships and 11 facts** in total, so every approach was also judged by reading each kept
item.

| Approach (4 stories) | Facts kept | Right by hand | Gold facts matched | Relationships |
|---|---|---|---|---|
| qwen2.5:7b, entity labels `E1…` + sentence ids | 41 | ~10% | 2 | none produced |
| qwen2.5:7b, entity names in the schema, values ≤ 40 chars | 25 | ~12% | 2 | none produced |
| Qwen3.5 4B (thinking off), same code | 32 | ~15% | 2 | 9, ~half plausible |
| GLiNER2 fact spans + relations (± parse attachment, type rules) | 42–54 | ~20–25% | 1–3 | 9–25, ~half plausible after type rules |
| NuExtract 2.0 4B, one combined template | 3 | 3/3 | 2 | 3 (returned nothing for parts 1–3) |
| **NuExtract 2.0 4B, people and relationship templates separately (chosen)** | **6** | **5/6** | **4** | 6–8, ~5 of 8 plausible |

Built: `wse/relations.py`, registered after the encoder stages with the GPU handoff in `wse/pipeline.py`
(`release_encoders` → `relations` → `release_llm`):
- per 2,000-char chunk, two NuExtract calls:
  - `people`: name + every fact property as `verbatim-string`;
  - `relationships`: subject and object verbatim, relation from the gold predicates;
- code grounding:
  - names must be the text of a character or organization mention in the chunk;
  - values must occur in the chunk (≤ 40 chars; the source's exact characters are kept);
  - no self-relations; duplicates removed;
  - facts and relationships are recorded on the entity's named mention.
- `wse/llm.py` takes a JSON schema or `"json"` as the output format, plus a `THINK` switch for reasoning models.
- Test: `tests/test_phase5.py`.

Setup (in `WSE/requirements.txt`): `ollama pull hf.co/…` fails on the Hugging Face CDN redirect, and the GGUF's chat
template is Jinja, which Ollama can't use. So the GGUF is downloaded with `huggingface_hub`, symlinked into `WSE/`
(git-ignored) and registered with `ollama create nuextract2-4b -f nuextract.Modelfile`, which supplies a ChatML
template.

Pipeline run (all stages so far), 4/4 stories, **2.5 min for all 4** (35–40 s each, including model loads). Micro:
**facts P 0.67 / R 0.36 / F1 0.47** (was 0.11–0.29 with the other approaches); relationships 0/6 against 4 gold. Earlier
stages unchanged.

**Follow-ups, fixed (2026-09-27):**
- **Coreference naming rule** (`wse/coref.py`: `naming_links`, merged by `merge`): "my / his / her … name is X" joins
  the proper name X to the possessive pronoun's cluster. On the 4 stories it fired 3 times, all correct:
  - `My name is Evelyn` → the narrator;
  - `His name is Daniel` → Dan / coworker;
  - `My name is Rose` → the `My` in her own dialogue.
  Effects:
  - entity-level event arguments 0.070 → 0.083 (the narrator's "I" now maps to Evelyn);
  - linked B³ 0.750 → 0.743, strict B³ 0.488 → 0.480, because the gold keeps `Evelyn` and `coworker` apart from the
    merged entities (a gold convention, not a wrong merge).
- **Symmetric and inverse relations:** `wse/relations.py` defines `SYMMETRIC` predicates (`FRIEND_OF`, `ENEMY_OF`,
  `SIBLING_OF`, `MARRIED_TO`, `ALLY_OF`, `KNOWS`, `RELATED_TO`) and `INVERSE` (`CHILD_OF` = reversed `PARENT_OF`);
  `canonical()` folds both.
  - Extraction keeps "A FRIEND_OF B" and "B FRIEND_OF A" once.
  - `wse/evaluate.py` adds `relationships_entity`: entity-level through predicted clusters, both sides canonical.
    Tested; on this run no reversed pair occurred, so relationships still match 0 of the 4 gold ones.
  - The backend has no symmetry data yet (TODO in `consistency/vocabulary.py`), so WSE owns it for now.
- Tests: 17 (naming rule, canonical form, symmetric matching and deduplication).
- Still needed: a larger fact and relationship gold set before tuning this stage further.

### Phase 6 — done (2026-09-27): temporal expressions and relations, no LLM

Built: `wse/temporal.py`, registered after events and before the GPU goes to the LLM (it reuses the loaded GLiNER2
model):
- **expressions:** GLiNER2 spans labelled with the gold's temporal types (`absolute_time`, `relative_time`,
  `duration`, `sequence_marker`), threshold 0.5;
- **relations:** from BookNLP's dependency parse, between two extracted events:
  - a clause introduced by `before` / `until` (BEFORE), `after` (AFTER) or `while` (DURING), attached to another event;
  - or the same marker as a preposition before a verb ("after leaving…");
  - `when` and `as` are skipped as ambiguous.
- Refactors, to reuse without duplicating: `mentions.gliner_spans(text, labels, threshold)` and
  `mentions.best_type()`; `events.children()` (the parse's dependents).
- Test: `tests/test_phase6.py`.

Gold facts: every gold temporal expression is typed `other` (the converter's default for missing types), so only
spans are scored. The gold's boundaries are inconsistent (`At midnight` and `at noon` include the preposition;
`nine o'clock` and `Last week` don't), which caps exact scores. The gold has **no temporal relations**.

Expression options (4 stories, exact span F1; overlap-matched gold out of 55):

| Option | Exact P / R / F1 | Overlap-matched |
|---|---|---|
| **GLiNER2, 4 typed labels, th 0.5 (chosen: gives the gold's types, model already loaded)** | 0.30 / 0.29 / 0.294 | 24 |
| GLiNER2, th 0.3 / 0.6 | 0.27 / 0.35 / 0.304 · 0.35 / 0.29 / 0.317 | 29 · 21 |
| spaCy `en_core_web_sm` DATE/TIME | 0.23 / 0.35 / 0.279 | 33 |
| spaCy + GLiNER2 union | 0.22 / 0.36 / 0.274 | 35 |

Missed are mostly relative and sequence phrases (`In moments`, `After a while`, `Until then`, `for a long time`). Many
"extras" are real times the gold didn't mark (`Three weeks ago`, `eighty minutes`, `Wednesday`, `June`); some are junk
(`104.6 F.M.`, a bare `day`).

Pipeline run (all stages), 4/4 stories, 2.5 min for all 4. Micro: **temporal expressions P 0.30 / R 0.30 / F1 0.299**
(was 0: never extracted). Other metrics unchanged.

**Temporal relations: 10 found, 10 correct by hand**, e.g. `watched` DURING `came` ("all the while it came closer"),
`shook` BEFORE `dropping`, `darting` BEFORE `saw` ("until he saw me"), `cleaned` BEFORE `sat` ("Before I sat down… I
cleaned myself up"), `reading` AFTER `stopped`. Recall is deliberately limited to explicit markers.

**All gold schema lists are now filled.** Complete extraction exists end to end, without the LLM except for facts
and relationships.

### Phase 7 — done (2026-09-27): LLM comparison

Local models tried: qwen2.5:7b (Q4, 4.7 GB, 9% CPU-offloaded on the 6 GB GPU), Qwen3.5 4B (3.4 GB, thinking off),
NuExtract 2.0 4B (Q4 GGUF, extraction-tuned). Every comparison used the same 4 gold stories; the LLM stage was the
only difference.

| Stage | qwen2.5:7b | Qwen3.5 4B | NuExtract 2.0 4B | Non-LLM | Chosen |
|---|---|---|---|---|---|
| Event types (typed F1, fixed triggers) | 0.100 (types + participants, per chunk) | 0.161 (per sentence, inline markers; hybrid 0.164) | 0.093 | **verb lexicon 0.195** | verb lexicon |
| Event participants (entity F1) | 0.049 | — | — | **parse rules 0.070 → 0.083** | parse rules |
| Facts (hand precision / gold matches) | ~12% / 2 | ~15% / 2 | **5 of 6 / 4 (F1 0.47)** | GLiNER2 ~20–25% / 1–3 | NuExtract |
| Relationships | none produced | ~half plausible | ~half plausible | GLiNER2 ~half after type rules | NuExtract |
| Temporal relations | — | — | — | **parse markers, 10/10 by hand** | parse markers (no gold to compare an LLM against) |

Event typing (Phase 7 experiment, per-sentence calls with inline `[T1 word]` markers, OTHER-default prompt):
- Qwen3.5 4B: 303 calls, 163 s. It defaults to OTHER now but over-assigns CONVERSATION (113 of 532).
- NuExtract: 303 calls, 57 s. It's an extractor, not a classifier (ARRIVAL 102 of 532).
- Neither beats the lexicon, alone or as a hybrid.

**Decision:** NuExtract 2.0 4B is the only LLM in the pipeline (facts and relationships). Everything else is encoder
models plus deterministic rules, which beat every local LLM tried, on the stages where they were compared.
- The `THINK` option added for Qwen3.5 was removed with it.
- `qwen3.5:4b` stays installed in Ollama but is unused (`ollama rm qwen3.5:4b` frees 3.4 GB).

### Phase 8 — done (2026-09-27): full comparison and handover

Final WSE run: all stages, clean run, **4/4 stories in 2 min 30 s** (32–40 s per story, including model loads).
Scores identical to Phase 6, so the pipeline is reproducible. 19 tests pass.

Every saved backend run, re-scored with the WSE scorer (micro F1 over the 4 stories; a failed story scores as empty):

| Run | Stories done | Mentions exact | Mentions typed | Mentions overlap | Coref B³ linked | Triggers exact | Triggers typed | Args (entity) | Rels (entity) | Facts | Time exprs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Backend split, strict (default settings) | 0/4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Backend split, partial (schema-constrained) | 1/4 | 0.104 | 0.086 | 0.162 | 0 | 0.042 | 0.021 | 0.006 | 0 | 0 | 0 |
| Backend split, partial, 2,000-char chunks | 1/4 | 0.217 | 0.116 | 0.333 | 0 | 0.112 | 0.032 | 0.016 | 0 | 0.026 | 0 |
| Backend monolithic | 2/4 | 0 (no offsets) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **WSE** | **4/4** | **0.572** | **0.483** | **0.619** | **0.743** | **0.243** | **0.195** | **0.083** | 0 | **0.471** | **0.299** |

Latency: WSE 2.5 min for all 4 stories; backend 10–13 min for 4 stories, while finishing at most 2.

The evaluator also got two robustness fixes while scoring the backend's output: items without offsets, and
relationships missing an end, now score as unmatched instead of crashing (as in the backend scorer). Regression test
in `tests/test_phase1.py`.

**What is still weak (measured):**
- Relationships: 0 of 4 gold; about half plausible by hand.
- Event participants: 0.083.
- Event triggers: recall capped near 0.5 by BookNLP's candidates.
- The gold is small and selective, so precision is understated for mentions, and relationships/facts can't be tuned
  yet.

### Go / no-go: GO, with the WSE pipeline as a separate extraction worker

WSE is the better extractor on every measured dimension and the only one that completes on real stories. Integrating
it into the backend's world state needs:

1. **Gold → `ExtractionResult` adapter** (backend side). `integrate_extraction_result` consumes the backend's own
   `ExtractionResult` + legacy dicts; `contracts/gold.py` only converts the other way (`project_to_gold`). The adapter
   maps WSE mentions, clusters, events (`participant_refs`), relationships and facts (`*_mention_id`) and temporal
   relations onto the contracts, then the existing `legacy_*` mappers produce the legacy dicts. WSE's clusters can
   replace the backend's Phase 5–6 name heuristics for linking mentions within a chapter.
2. **A process boundary.** WSE runs in its own Python 3.12 venv with torch and CUDA; the backend runs Python 3.14.
   The backend worker would call WSE per chapter. Needs a `python -m wse run` entry for a single chapter's text
   (deferred in Phase 1 as not yet needed; it is now) or a small local HTTP service.
3. **Number words in ages** (backend `consistency/vocabulary.parse_age`): WSE keeps values verbatim (`twenty four`),
   which `parse_age` returns as None, so REQ-23 would never fire on them. A small, deterministic word-to-number step
   is needed.
4. **Relationship vocabulary.**
   - The consistency rule for a changing father is keyed on `FATHER_OF`, which the gold vocabulary (and therefore
     WSE) does not have (`PARENT_OF` only).
   - Symmetric/inverse metadata exists only in WSE (`relations.SYMMETRIC`, `INVERSE`) and should move into the
     backend vocabulary.
5. **Latency vs the SRS budget of 10 s per chapter:** 32–40 s per story here, mostly model loading. On the 6 GB GPU
   the encoders and NuExtract can't stay loaded together.
   - A persistent worker that processes a manuscript's chapters stage by stage (load each model once) is the upgrade
     path; it is marked in `pipeline.release_encoders`.
   - A larger GPU removes the swapping.
6. **Commit the work.** Backend Phases 3–7 and all of `WSE/` are still uncommitted.
7. **A larger fact / relationship gold set** before tuning those stages further.
