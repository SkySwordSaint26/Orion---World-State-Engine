# Orion Backend — System Overview

This document describes the runtime components, technical stack decisions, and execution environments of the backend.

---

## 1. Technology Stack & Rationale

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| **Web Framework** | FastAPI | 0.110+ | High performance, native async/await, OpenAPI generation, typed Pydantic validation. |
| **Validation / Schemas** | Pydantic | 2.6+ | Pydantic V2 Rust core gives 5-10x faster serialization; strict model validation. |
| **ORM / Database Access** | SQLAlchemy | 2.0+ | Modern 2.0-style queries, strong relational mapping, ACID transactions, PostgreSQL support. |
| **Database Engine** | PostgreSQL | 15+ | Reliable relational storage, JSONB columns, foreign key cascade constraints. |
| **Task Queue** | Celery | 5.3+ | Distributed task worker for long-running extraction jobs spanning multi-chapter manuscripts. |
| **Message Broker** | Redis | 7.0+ | In-memory pub/sub and result backend for Celery queues. |
| **Local LLM Engine** | Ollama (Llama 3.1:8b) | — | Zero-cloud cost, privacy-preserving, fast local inference for narrative text extraction. |
| **Testing** | Pytest / AnyIO | 8.0+ | Fast unit and integration tests with in-memory SQLite and mock LLM support. |

---

## 2. Dual Execution Modes

To ensure the backend is equally enjoyable to develop locally (zero dependencies) as it is in a production cluster, two execution pathways exist:

```
[Manuscript / Chapter Ingestion]
                │
        Is Celery & Redis
           Available?
          /          \
     YES /            \ NO (Local Dev / Offline Tests)
        ▼              ▼
[Celery Task Queue]   [FastAPI BackgroundTasks]
  run_extraction_job_task   run_extraction_job()
        │              │
        └───────┬──────┘
                ▼
  [World State Integration]
```

1. **Production / Docker Mode**:
   - `EXTRACTION_EXECUTOR=celery`: each job is dispatched as ONE Celery task (`run_extraction_job_task`), which runs the job's chapters in order.
   - Redis manages the queue. Different jobs/worlds can run concurrently across worker instances; chapters within a job never do.
2. **Local Dev / Single Process Mode**:
   - `EXTRACTION_EXECUTOR=background` (default): the same `run_extraction_job` function executes via FastAPI's native `BackgroundTasks`, so Redis is not needed.
   - The choice is explicit configuration. If the configured executor is unreachable the job fails (API returns 503); the system does not silently switch executors.

---

## 3. Storage Layout

Physical file artifacts (uploaded manuscript text, chapter version snapshots) are managed by [`file_handler.py`](../../app/utils/file_handler.py):

```
backend/storage/
├── worlds/
│   └── <world_id>/
│       └── <uuid>_manuscript.txt     # Original uploaded manuscript file
└── chapters/
    └── <manuscript_id>/
        ├── <uuid>_ch_1_original.txt  # Snapshot of Chapter 1 text
        └── <uuid>_ch_1_rev.txt       # Snapshot of edited Chapter 1 text
```

---

## 4. Documentation References

- **Software Requirements Specification (SRS v1.0)**: [`docs/srs.md`](../../../docs/srs.md)
- **REST API Reference & Endpoint Specifications**: [`docs/api.md`](../../../docs/api.md)
- **Database Schema Reference**: [`backend/.ai/context/db_schema_reference.md`](db_schema_reference.md)
- **API Contracts (AI Agent context)**: [`backend/.ai/context/api_contracts.md`](api_contracts.md)

