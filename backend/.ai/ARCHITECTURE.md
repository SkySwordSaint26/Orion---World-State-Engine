# Orion World State Engine — System Architecture

This document provides a mechanistic, ground-truth explanation of the Orion backend architecture.

---

## 1. System Topology

```
                  ┌──────────────────────────────────────────────┐
                  │                 Web Browser                  │
                  │        (Frontend React / Zustand Store)      │
                  └───────────────────────┬──────────────────────┘
                                          │  HTTPS / REST API
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                FastAPI Server                                   │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    API Layer (Routes & Dependencies)                      │  │
│  │    /auth    /worlds    /manuscripts    /chapters    /jobs    /entities    │  │
│  │             /graph     /timeline       /contradictions       /chat        │  │
│  └──────────────────────────────────────┬────────────────────────────────────┘  │
│                                         │ Invokes                               │
│  ┌──────────────────────────────────────▼────────────────────────────────────┐  │
│  │                             Service Layer                                 │  │
│  │  - ManuscriptService   - ChapterService   - JobService    - EntityService │  │
│  │  - WorldStateService   - ConsistencyService (Rules)       - GraphService  │  │
│  │  - TimelineService     - ChatService                                      │  │
│  └──────────────────────┬───────────────────────────────┬────────────────────┘  │
│                         │ Calls                         │ Dispatches            │
│  ┌──────────────────────▼───────────────┐  ┌────────────▼────────────────────┐  │
│  │          Repository Layer            │  │     Background Task Runner      │  │
│  │   (Clean DB Query Abstractions)      │  │ (FastAPI BackgroundTasks or     │  │
│  └──────────────────────┬───────────────┘  │  Celery / Redis Worker)         │  │
│                         │                  └────────────┬────────────────────┘  │
└─────────────────────────┼───────────────────────────────┼───────────────────────┘
                          │                               │
                          ▼                               ▼
       ┌─────────────────────────────────────┐  ┌─────────────────────────────────┐
       │         PostgreSQL Database         │  │     LLM Extraction Pipeline     │
       │    (12 Tables, ACID, Versioned)     │  │  - Text Chunker (~8k chars)     │
       │  - users           - worlds         │  │  - Prompt Orchestrator          │
       │  - manuscripts     - chapters       │  │  - Ollama / OpenAI Provider     │
       │  - chapter_vers    - jobs           │  │  - JSON Sanitizer & Parser      │
       │  - extraction_runs - entities       │  │  - Coreference Clustering       │
       │  - facts           - relationships  │  │  - Fact/Relationship Resolvers │
       │  - events          - contradictions │  └─────────────────────────────────┘
       └─────────────────────────────────────┘
```

---

## 2. End-to-End Extraction Pipeline Lifecycle

When an author uploads a manuscript (or updates a chapter), the following state transitions occur:

```mermaid
sequenceDiagram
    autonumber
    actor Author as User / Frontend
    participant API as FastAPI Router
    participant MS as ManuscriptService
    participant Worker as Background Worker / Celery
    participant Pipe as ExtractionOrchestrator
    participant LLM as LLM Client (Ollama/OpenAI)
    participant WS as WorldStateService
    participant Rules as ConsistencyService
    participant DB as PostgreSQL

    Author->>API: POST /worlds/{id}/manuscripts (file upload)
    API->>MS: upload_manuscript(bytes, filename)
    MS->>DB: Save Manuscript, Chapters (1..N), ChapterVersion #1
    MS->>DB: Create ProcessingJob (status="queued", total=N)
    MS->>DB: Create ExtractionRun for each chapter
    MS-->>API: Return {job_id, manuscript_id, chapters_total}
    API-->>Author: 202 ACCEPTED (polling job_id)

    API->>Worker: dispatch_extraction_job(job_id)  (ONE task per job, not per chapter)

    loop Chapters in ascending order (stops at the first failure)
        Worker->>DB: Claim ExtractionRun (pending -> processing), Job = "processing"
        Worker->>Pipe: extract_chapter(text, chapter_num)
        Pipe->>Pipe: preprocess_chapter(text) then chunk_document(max_chars=8000, overlap=2 sentences)
        
        loop Per Chunk
            Pipe->>LLM: generate(prompt, json_mode=True)
            LLM-->>Pipe: raw_json_string
            Pipe->>Pipe: parse_and_validate_extraction(raw_json)
        end

        Pipe->>Pipe: cluster_mentions(raw_entities)
        Pipe-->>Worker: Aggregated extraction payload

        Worker->>DB: BEGIN integration transaction: lock world row, check earlier chapters are DONE
        Worker->>WS: integrate_extraction_result(world_id, data)  (flushes only, never commits)
        WS->>DB: Resolve / Create Entities & Aliases
        WS->>DB: Append FactVersions (ACTIVE, SUPERSEDED, CONTRADICTED)
        WS->>DB: Append RelationshipVersions
        WS->>DB: Insert Events & EventParticipants

        Worker->>Rules: run_checks(world_id, events, relations)
        Note over Rules: Deterministic checks (see context/consistency_engine.md):<br/>Immutable facts, age monotonicity (REQ-23), dead-then-alive status (REQ-26 status part)<br/>Incompatible / single-source relationships (REQ-25), temporal cycles<br/>DEFERRED: location clashes (REQ-24), acting after death (REQ-26)
        Rules->>DB: Insert detected Contradictions

        Worker->>DB: Mark ExtractionRun = "done" + COMMIT (one commit for the whole chapter)
        Worker->>DB: Job progress = recount of run statuses
    end

    Note over Worker,DB: Any exception -> ROLLBACK the chapter, run = "failed", later chapters skipped (failed)
    Note over Worker,DB: Job = "done" only when EVERY run is "done"; any failed run -> Job = "failed"
    Author->>API: GET /jobs/{job_id}/status
    API-->>Author: {status: "done", progress: N/N}
```

---

## 3. Structural Layers & Separation of Concerns

### Layer 1: API Layer (`app/api/`)
- **`deps.py`**: Injects request-scoped database sessions (`get_db`) and validates Bearer JWT tokens (`get_current_user`, `get_current_user_optional`).
- **`v1/routes/`**: Handles HTTP serialization, URL query parameters, status codes (201 Created, 202 Accepted, 204 No Content, 404 Not Found), and file uploads (`multipart/form-data`).

### Layer 2: Service Layer (`app/services/`)
- Pure Python business logic orchestrating multiple repositories and pipelines.
- Implements transaction boundaries and domain policies.
- Example: [`WorldStateService`](../app/services/world_state_service.py) does not write raw SQL; it coordinates [`EntityRepository`](../app/repositories/entity_repo.py), [`FactRepository`](../app/repositories/fact_repo.py), and [`ConsistencyService`](../app/services/consistency_service.py).

### Layer 3: Repository Layer (`app/repositories/`)
- Implements the Repository Pattern via [`BaseRepository[ModelType]`](../app/repositories/base.py).
- Provides type-safe CRUD operations (`get`, `get_all`, `create`, `update`, `delete`, `filter_by`).
- Specialized repositories encapsulate complex joins and query optimizations (e.g. `get_entity_with_facts` with `joinedload`).

### Layer 4: Pipeline Layer (`app/pipeline/`)
- **`extractor.py`**: the only extractor. Runs `../extractor` (encoder models + NuExtract, its own Python 3.12 venv and the GPU) as a subprocess per chapter and turns its orion_gold_v1 document into the dict `WorldStateService` integrates (entities by name with aliases and facts, relationships, events, temporal relations). An extraction failure fails the chapter run.
- **`llm_client.py`**: chat only (`ChatService`): local Ollama or OpenAI, with a canned answer when both fail or `LLM_PROVIDER=mock`.
- **`app/preprocessing/`** (deterministic, no LLM): paragraph/sentence segmentation with exact offsets and sentence-aligned chunking, used by ../extractor and `extractor.py`.
- **`app/contracts/`**: the gold-schema vocabularies (`gold.py`, used by ../extractor) and pass-through normalization hooks.
- **`resolution/fact_resolution.py`, `resolution/relationship_resolution.py`**: thin compatibility wrappers over the rule engine in `app/consistency/` (`resolve_fact_update`, `resolve_relationship_update`); integration itself calls `ConsistencyService`, which runs the deterministic `ConsistencyEngine`.
- **`app/consistency/`** (Layer 4b): controlled vocabulary, small independent rules, the LLM-free `ConsistencyEngine`, and the `ContradictionRecorder` (flush-only persistence with deduplication). Reference: [`context/consistency_engine.md`](context/consistency_engine.md).

### Layer 5: Worker Layer (`app/workers/`)
- Asynchronous execution engine powered by Celery and Redis.
- Executor: `EXTRACTION_EXECUTOR=celery` enqueues one `tasks.run_extraction_job` per job on the Celery worker (Redis required); `EXTRACTION_EXECUTOR=background` (default) runs the same `run_extraction_job` function through FastAPI `BackgroundTasks` for local dev without Redis. Chapter ordering does not depend on which executor is used. If Celery cannot be reached the job is marked failed and the API returns 503; there is no silent switch to the other executor.

---

## 3b. Extraction Execution Semantics

**IMPLEMENTED NOW (Phase 1)**
- One extraction job = one ordered runner (`run_extraction_job`): chapters run 1..N; the first failure stops the job and marks later runs `failed` ("Skipped ...").
- Chapter integration is one transaction: repositories used by integration flush (`commit=False`), and only `execute_chapter_extraction` commits, together with `ExtractionRun.status = done`. Any exception rolls the whole chapter back.
- Ordering gate: before integrating, a chapter checks that every lower-numbered chapter of the same manuscript that was submitted for extraction has its latest run `done`; otherwise the run fails without touching world state. Integration also locks the `worlds` row (`SELECT ... FOR UPDATE`, effective on PostgreSQL), so integrations within one world never interleave while different worlds stay independent.
- Job progress is a recount (`update_job_progress`), never an increment.
- Deterministic consistency engine (Phase 2): immutable-fact, age-monotonic, dead-then-alive, incompatible-relationship, single-source (`FATHER_OF`) and temporal-cycle rules, run inside the chapter transaction with deduplicated contradiction records. See [`context/consistency_engine.md`](context/consistency_engine.md).

**NOT IMPLEMENTED YET (planned future architecture, later phases)**
- Property, relationship and temporal **normalization** (not implemented; the rule engine currently sees raw stored names, direction-keyed relationships and single-chapter temporal data). Known limitations and their code markers: [`context/consistency_engine.md`](context/consistency_engine.md#known-limitations-read-before-relying-on-the-results).
- Consistency rules that are DEFERRED (location clashes REQ-24, speaking/acting after death REQ-26) because the frozen schema and current extraction contract cannot represent the required information. The implemented rules are listed in [`context/consistency_engine.md`](context/consistency_engine.md).
- World-aware entity resolution across chapters: ../extractor resolves mentions within a chapter; entities join earlier chapters by exact name or alias only.
- Deferred retry when an edit is submitted while earlier chapters of another job are still pending (it currently fails with a "blocked by" message and can be re-run).

---

## 4. Performance Budgets (SRS Section 5.1)

| Operation | Latency Budget | Architectural Strategy |
|---|---|---|
| **Single Chapter Extraction** | **≤ 10 seconds** | Stream chunks to quantized local model (or fast API); parallel chunk dispatch; token-safe boundaries. |
| **Contradiction Detection** | **≤ 5 seconds** | 100% deterministic Python in-memory graph algorithms (DFS cycle detection, hash table lookups). Zero LLM overhead. |
| **Character Chat Response** | **≤ 3 seconds** | Filtered context window (top 25 entities, active relations, recent events); low temperature (0.3). |
| **World Graph Retrieval** | **≤ 500 ms** | Optimized SQLAlchemy joined loads; degree calculation in single pass. |
