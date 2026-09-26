# NLP / LLM Tools for Orion — Research

Date: 2026-09-26 · Companion to [`llm_pipeline_status.md`](llm_pipeline_status.md) and
[`llm_pipeline_phases.md`](llm_pipeline_phases.md)

**Question:** is there a model or tool built for this use case, and if not, what should each part of the pipeline use?

**Constraints this research assumes:** English fiction; runs locally on an RTX 4050 6 GB laptop GPU; Python backend;
every extracted item needs exact character offsets; contradiction detection stays rule-based (SRS REQ-27).

---

## TL;DR

No single model does fiction → versioned world state. The closest match is **BookNLP**, a pipeline built for novels.
The recommended stack is a hybrid:

| Pipeline part | Recommended | Why |
|---|---|---|
| Mentions (stage 1) | **GLiNER2** (+ BookNLP entities to compare) | Custom labels incl. `object`, exact offsets, CPU-fast, cannot invent text or loop, Apache-2.0 |
| Coreference (Phases 5–6) | **BookNLP** (trained on fiction) or **fastcoref** | Pronoun and name clusters with offsets; MIT licensed |
| Speaker of each quote (REQ-26 "dead, then speaking") | **BookNLP / ModernBookNLP** | Quote → speaker attribution: the missing data behind the deferred REQ-26 rule |
| Event triggers | **BookNLP events** + LLM for the event type | BookNLP marks real (realis) event words; the LLM only assigns the type |
| Relationships, facts, event types | **LLM** (qwen2.5:7b today; try **Qwen3.5 4B** and **NuExtract 2.0**) with schema-constrained output | Narrative meaning; no off-the-shelf model covers it |
| Temporal expressions | **HeidelTime** (narrative mode) | Rule-based, deterministic, normalises to TIMEX3 |
| Evaluation | Existing `app.evaluation` harness + **LitBank** | Measure every swap before adopting it |

---

## 1. All-in-one literary pipelines

### BookNLP — the closest existing match
- **What it outputs:** entities (PER, FAC, GPE, LOC, VEH, ORG); coreference (character-name clustering + pronouns);
  realis events; quotations with speaker attribution; supersenses; referential gender.
- **Files:** `.tokens`, `.entities`, `.quotes`, `.supersense`, `.book` (JSON character summaries), `.book.html`.
- **Scores:**

  | Model | Entity F1 | Event F1 | Coreference F1 | Speaker attribution |
  |---|---|---|---|---|
  | small | 88.2 | 70.6 | 76.4 | 86.4 |
  | big | 90.0 | 74.1 | 79.0 | 89.9 |

- **Speed (99k tokens, from its README):** GPU 2.1 min (small), 2.2 min (big); 10-core CPU 2.4 / 5.2 min.
  A 15k-character story part is about 3.5k tokens, so it takes seconds.
- **License:** MIT. Built on PyTorch and spaCy.
- **Fit:** covers mentions, coreference, events and quote speakers, all trained on fiction (LitBank).
- **Gaps:**
  - no `object` entity type;
  - no relationships between characters;
  - no attributes or facts;
  - the README targets Python 3.7, so compatibility with this backend's Python 3.11 needs checking.

### ModernBookNLP (2026)
- A fork of BookNLP that replaces its quote-attribution model.
- 94.5% attribution accuracy on the Project Dialogism Novel Corpus.
- About 20× faster than comparable standard methods, and over 1000× faster than LLM-based approaches (measured on an A100).
- Paper and code: arXiv 2608.02359, `github.com/gasmichel/ModernBookNLP_QA`; the paper is CC BY 4.0.
- **Fit:** speaker attribution is what the deferred REQ-26 rule ("marked dead, then shown speaking") needs.

---

## 2. Mention detection (replaces split stage 1)

| Tool | What it gives | Size / hardware | License | Notes |
|---|---|---|---|---|
| **GLiNER2** (Fastino, EMNLP 2025) | NER with your own labels + descriptions, classification, relations, structured JSON, in one model | 74M (small), ~200M (base), 340M (large); "CPU first", GPU optional | Apache-2.0 | `pip install gliner2[local]`. Labels can carry descriptions (e.g. `"object": "a concrete physical thing a character uses or sees"`). |
| **GLiNER** (original) | Zero-shot span NER with arbitrary labels | small → large | Code Apache-2.0; **check each checkpoint's licence** (not listed on the repo page) | Also ships `gliner-relex` (joint NER + relations). |
| BookNLP entities | PER / FAC / GPE / LOC / VEH / ORG, fiction-trained | see §1 | MIT | No `object` type; use it together with GLiNER, not instead. |

**Why this beats the LLM for stage 1:** spans come straight from the text, so the model cannot invent a phrase ("the
bird") or loop ("Dan" ×314), and offsets are exact. On real data today, stage 1 was the call that looped, and invented
mentions were a leading cause of failure.

---

## 3. Coreference (Phases 5–6, SRS REQ-17/18)

| Tool | Scores | Output | License | Notes |
|---|---|---|---|---|
| **BookNLP coref** | 76.4 / 79.0 F1 (small/big) on fiction | Clusters linked to entities | MIT | Trained on LitBank fiction; handles character-name clustering (the "Alice" / "Alice Sterling" case). |
| **fastcoref** (FCoref, LingMessCoref) | FCoref fast; LingMess larger and more accurate | `get_clusters()` as **character spans** or strings | MIT | ~3 ms per text after compilation; spaCy v3 component available. Trained on news-style OntoNotes, not fiction. |
| **Maverick** (ACL 2024) | LitBank checkpoint 78.0; OntoNotes 83.6; ~500M parameters | `clusters_char_offsets` | **CC BY-NC-SA 4.0 (non-commercial)** | Has a **LitBank (fiction) checkpoint**. Fine for research; the licence blocks commercial use. |

**Fit:** the current rule-based resolver links "he/she/they" only at sentence start and never across sentences. Any of
these would close most of that gap. First-person narration (this story's "I") is common in fiction; BookNLP and the
LitBank checkpoint are trained on such text.

---

## 4. Relationships

| Tool | What it gives | License | Notes |
|---|---|---|---|
| **GLiREL** (NAACL 2025) | Zero-shot relation classification between entity pairs, one forward pass | see repo (`jackboyla/GLiREL`) | State of the art on zero-shot benchmarks (FewRel, WikiZSL); needs entities first. |
| **GLiNER-Relex** (2026) | Joint NER + relation extraction, arbitrary labels at inference | Paper CC BY 4.0; code "publicly available" | Competitive with specialised RE models and LLMs on CoNLL04, DocRED, FewRel, CrossRE. |
| **GLiNER2** relations | `extract_relations(text, ["works_for", …])` | Apache-2.0 | Same model as stage 1 above. |

**Caveat:** narrative relationships are rare and often implied ("Dad", "we were friends in college"); the gold set has
about 1 per story. These encoders work within a sentence or short span and are trained on news/Wikipedia. Try them
against the LLM on the gold set before choosing; the LLM may remain the better option here.

---

## 5. Events

- **BookNLP events** mark realis event words (events depicted as actually happening, not hypothetical or future), which
  matches what a world-state timeline needs. They have no event types.
- **Suggested split:** BookNLP (or the LLM) finds the trigger word; the LLM assigns the closed-vocabulary type and
  participants through the existing stage 3 schema.
- LitBank's event layer uses the same realis definition, so it can be used for evaluation.

---

## 6. LLMs for relationships, facts and event typing (local, 6 GB VRAM)

| Model | Size | Fits 6 GB fully? | License | Notes |
|---|---|---|---|---|
| qwen2.5:7b (current) | 4.7 GB file; 5.4 GB loaded at `num_ctx 8192` | **No**: 12% runs on CPU | Apache-2.0 | Baseline in `llm_pipeline_status.md`. |
| **Qwen3.5 4B** | 3.4 GB (Ollama), 256K context, text + image | **Yes** | see Ollama page | Newer generation; has a thinking mode, which should be off for extraction (verify the toggle). Recommended by several 2026 "best model for 6 GB" guides for structured output. |
| Qwen3.5 9B | 6.6 GB | No | see Ollama page | Would partly run on CPU; slower than 4B. |
| **NuExtract 2.0** (NuMind) | 2B / 4B / 8B | 2B and 4B yes; 8B no | 2B **MIT**, 4B **Qwen Research License (non-commercial)**, 8B **MIT** | **Built for extraction**: prompted with a JSON template including a `verbatim-string` type (copy from the text), which matches our evidence rule. Runs in Ollama: `ollama run hf.co/numind/NuExtract-2.0-4B-GGUF:Q4_K_M`. |
| Phi-4 Mini | ~2.8 GB (Q4) | Yes | see model card | Mentioned in 2026 guides as reliable at JSON output for its size. |

**How to choose:** run each through `python -m app.evaluation predict/score` on the 4 gold stories; pick by score and
latency, not by guides.

**Constrained output:** Ollama's `format` accepts a JSON schema (already used by the split stages). Alternatives if we
ever leave Ollama: llama.cpp GBNF grammars, **Outlines** (schema → token-level constraint), **Instructor** (Pydantic
models; with llama-cpp-python uses constrained sampling).

---

## 7. Temporal expressions (gold has 9–18 per story; we extract none)

| Tool | Notes |
|---|---|
| **HeidelTime** | Rule-based, multilingual, normalises to TIMEX3, with a dedicated **narratives** mode. Java; Python wrappers exist (`python_heideltime`, `python-heideltime`). Deterministic, which fits the project. |
| SUTime | Stanford CoreNLP rule-based tagger (Java). |
| `dateparser` | Python; normalises relative expressions but does not find them in text. |

---

## 8. Knowledge-graph frameworks (similar use case; why they don't fit directly)

| Tool | What's similar | Why it doesn't fit as-is |
|---|---|---|
| **Graphiti** (Zep) | Temporal knowledge graph: **bi-temporal** edges (valid time + ingestion time); superseded facts are **invalidated, not deleted**, which is close to our append-only fact versions | The **LLM decides** which facts get invalidated, which conflicts with REQ-27 (rule-based contradictions). Needs a graph database. No exact offsets. Worth reading for its data model. |
| **KGGen** (NeurIPS 2025) | Text → knowledge graph with **entity clustering** (embeddings + LLM de-duplication); MINE benchmark | Built to reduce graph sparsity, not to keep provenance or versions; clustering by LLM is not deterministic. |
| **LangChain LLMGraphTransformer / Neo4j LLM Graph Builder** | LLM extraction limited to `allowed_nodes` / `allowed_relationships`; works with Ollama | Same as our old monolithic call: no offsets, no evidence check, no versioning. |

**Takeaway:** these confirm the design choice. General KG builders trade provenance and determinism for convenience,
and Orion needs both.

---

## 9. Writer-facing products (similar goal, different approach)

Sudowrite (Story Bible), Inkfluence AI and similar tools keep a "story bible" and check continuity with an LLM, mostly
during drafting. They are closed services, and they rely on the LLM's judgement. Orion's differences: rule-based
contradictions (REQ-27), a permanent version history (REQ-22), and every claim traceable to exact text.

---

## 10. Datasets and benchmarks

| Resource | Use for Orion |
|---|---|
| **LitBank** (100 fiction works, ~210k tokens) | Entities, realis events, coreference, quote attribution. A larger gold set than our 4 stories for evaluating mentions, coreference and events. Entity types differ (no `object`). |
| Project Dialogism Novel Corpus | 35k+ quotations with speakers from 22 novels; evaluation data for quote-speaker attribution. |
| **FlawedFictions** (2025) | Plot-hole detection benchmark. Finding: state-of-the-art LLMs struggle, and get worse as stories get longer. |
| **ConStory-Bench / ConStory-Checker** (2026) | Consistency errors in long stories: 5 categories, 19 subtypes; errors are most common in factual and temporal dimensions. Useful for designing rules. |
| **NCP-Bench** (2026) | Narrative consistency of LLM agents: the best model survives 20 turns only 42% of the time; fact-conflict rates of 40–68%. |

The last three all point the same way: **LLMs alone do not keep a story consistent.** That supports Orion's design:
the LLM extracts, and deterministic rules check.

---

## 11. Suggested order to try (each measured with `app.evaluation`)

1. **Finish the pipeline fixes** already planned (smaller chunks, evidence prefix, lenient failure policy), so the
   baseline is fair.
2. **BookNLP on the 4 gold stories.** It's one run, no LLM, and gives mentions, coreference, events and quote speakers.
   It also shows whether its Python 3.7-era dependencies work on Python 3.11.
3. **GLiNER2 as stage 1**, with descriptions for our 5 mention types. Compare mention scores with the qwen stage 1.
4. **Coreference:** BookNLP versus fastcoref, after the evaluation is extended to run Phases 5–6.
5. **LLM swap:** Qwen3.5 4B and NuExtract 2.0 (2B or 8B for MIT licensing) for stages 2–4.
6. **HeidelTime** for temporal expressions.

**Licences to watch:** Maverick (non-commercial), NuExtract 2.0 4B (Qwen Research License), and individual GLiNER
checkpoints (check each model card).

---

## Sources

- BookNLP — https://github.com/booknlp/booknlp
- ModernBookNLP / Fast and Accurate Quotation Attribution in Literary Texts — https://arxiv.org/abs/2608.02359
- Improving Automatic Quotation Attribution in Literary Novels — https://arxiv.org/abs/2307.03734
- Project Dialogism Novel Corpus — https://arxiv.org/pdf/2204.05836
- LitBank — https://github.com/dbamman/litbank ; An Annotated Dataset of Coreference in English Literature — https://arxiv.org/pdf/1912.01140
- GLiNER2 — https://github.com/fastino-ai/GLiNER2 ; paper https://huggingface.co/papers/2507.18546
- GLiNER — https://github.com/urchade/GLiNER
- GLiNER-Relex — https://arxiv.org/abs/2605.10108
- GLiREL — https://github.com/jackboyla/GLiREL ; paper https://arxiv.org/abs/2501.03172
- fastcoref — https://github.com/shon-otmazgin/fastcoref
- Maverick — https://github.com/SapienzaNLP/maverick-coref ; paper https://aclanthology.org/2024.acl-long.722/
- NuExtract 2.0 — https://huggingface.co/numind/NuExtract-2.0-4B-GGUF ; https://huggingface.co/numind/NuExtract-2.0-8B ; https://numind.ai/blog/outclassing-frontier-llms----nuextract-2-0-takes-the-lead-in-information-extraction
- Qwen3.5 on Ollama — https://ollama.com/library/qwen3.5
- 6 GB VRAM model guides — https://localaimaster.com/vram/best-llm-6gb-vram ; https://www.mayhemcode.com/2026/06/best-local-llms-for-4gb-6gb-and-8gb.html ; https://www.morphllm.com/best-ollama-models
- Constrained decoding — https://python.useinstructor.com/integrations/llama-cpp-python/ ; https://arxiv.org/html/2501.10868v1 ; https://zeroentropy.dev/concepts/constrained-decoding/
- HeidelTime — https://github.com/texttechnologylab/heideltime ; https://github.com/PhilipEHausner/python_heideltime ; https://ds.ifi.uni-heidelberg.de/resources/temporal-tagging/
- Graphiti / Zep — https://help.getzep.com/graphiti/getting-started/overview ; https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/
- KGGen — https://openreview.net/pdf?id=YyhRJXxbpi ; https://neurips.cc/virtual/2025/poster/117386
- LLMGraphTransformer — https://reference.langchain.com/python/langchain-neo4j/graph_transformers/llm/LLMGraphTransformer ; Neo4j LLM Graph Builder — https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/
- FlawedFictions — https://arxiv.org/abs/2504.11900
- ConStory-Bench (Lost in Stories) — https://arxiv.org/abs/2603.05890
- NCP-Bench — https://arxiv.org/abs/2608.08160
- Writer tools — https://www.inkfluenceai.com/blog/best-ai-novel-continuity-checking-2026
- Character/world tracking research — https://arxiv.org/pdf/2607.17250 ; https://arxiv.org/pdf/2512.07474
