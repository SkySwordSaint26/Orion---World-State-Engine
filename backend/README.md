# Orion — World State Engine (Backend)

High-performance, modular backend engine for narrative extraction, character knowledge graphing, temporal event ordering, and world consistency validation.

---

## Architecture Overview

```
backend/
│
├── app/
│   ├── main.py                # FastAPI application entrypoint & lifespan
│   ├── config/               # Settings & environment configuration
│   │   ├── settings.py
│   │   └── logging.py
│   │
│   ├── api/                  # Route handlers & HTTP dependency injection
│   │   ├── deps.py           # DB session and JWT auth dependencies
│   │   └── v1/
│   │       ├── routes/
│   │       │   ├── auth.py
│   │       │   ├── worlds.py
│   │       │   ├── manuscripts.py
│   │       │   ├── chapters.py
│   │       │   ├── jobs.py
│   │       │   ├── entities.py
│   │       │   ├── graph.py
│   │       │   ├── timeline.py
│   │       │   ├── contradictions.py
│   │       │   └── chat.py
│   │       └── router.py
│   │
│   ├── core/                 # Core engine infrastructure
│   │   ├── database.py       # SQLAlchemy engine & session factory
│   │   ├── security.py       # Bcrypt hashing & JWT token management
│   │   └── constants.py      # Enums for statuses, types, and contradictions
│   │
│   ├── models/               # SQLAlchemy models (Mirrors ER Diagram v2)
│   │   ├── user.py
│   │   ├── world.py
│   │   ├── manuscript.py
│   │   ├── chapter.py
│   │   ├── chapter_version.py
│   │   ├── processing_job.py
│   │   ├── extraction_run.py
│   │   ├── entity.py
│   │   ├── fact.py
│   │   ├── relationship.py
│   │   ├── event.py
│   │   ├── contradiction.py
│   │   └── __init__.py
│   │
│   ├── schemas/              # Pydantic models (Request/Response validation)
│   │   ├── auth.py
│   │   ├── world.py
│   │   ├── manuscript.py
│   │   ├── chapter.py
│   │   ├── job.py
│   │   ├── entity.py
│   │   ├── graph.py
│   │   ├── timeline.py
│   │   ├── contradiction.py
│   │   └── chat.py
│   │
│   ├── services/             # Core Business Logic
│   │   ├── manuscript_service.py   # Upload, splitting, and job creation
│   │   ├── chapter_service.py      # Versioning & re-extraction triggers
│   │   ├── job_service.py          # Progress tracking & polling
│   │   ├── entity_service.py       # Canonical resolution & alias management
│   │   ├── world_state_service.py  # Fact, relationship, and event integration
│   │   ├── consistency_service.py  # Temporal cycle & conflict detection
│   │   ├── graph_service.py        # Knowledge graph formatting (nodes/edges)
│   │   ├── timeline_service.py     # Chronological narrative timeline view
│   │   └── chat_service.py         # Grounded conversational world assistant
│   │
│   ├── repositories/         # Database Access Layer (Repository Pattern)
│   │   ├── base.py
│   │   ├── user_repo.py
│   │   ├── world_repo.py
│   │   ├── manuscript_repo.py
│   │   ├── chapter_repo.py
│   │   ├── job_repo.py
│   │   ├── entity_repo.py
│   │   ├── fact_repo.py
│   │   ├── relationship_repo.py
│   │   ├── event_repo.py
│   │   └── contradiction_repo.py
│   │
│   ├── workers/              # Asynchronous Celery & Background Jobs
│   │   ├── celery_app.py
│   │   ├── tasks/
│   │   │   ├── extraction_task.py
│   │   │   └── job_update_task.py
│   │   └── __init__.py
│   │
│   ├── pipeline/             # LLM Extraction & Entity Resolution Pipeline
│   │   ├── extractor.py      # Pipeline orchestrator
│   │   ├── llm_client.py     # Local Ollama / OpenAI / Mock multi-provider
│   │   ├── prompts/
│   │   │   ├── extraction_prompt.txt
│   │   │   └── chat_prompt.txt
│   │   ├── parsers/
│   │   │   └── extraction_parser.py
│   │   └── resolution/
│   │       ├── entity_resolution.py
│   │       ├── fact_resolution.py
│   │       └── relationship_resolution.py
│   │
│   ├── utils/                # Helpers
│   │   ├── file_handler.py   # File system storage & safe reading
│   │   ├── text_splitter.py  # Chapter boundary detection (its chunk_text is deprecated)
│   │   └── hashing.py        # SHA256 & UUID utilities
│   │
│   └── tests/                # Automated Test Suite
│       ├── test_api.py
│       ├── test_services.py
│       └── test_pipeline.py
│
├── alembic/                  # Database Migration Scripts
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│   alembic.ini
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── docs/                     # Project Specifications & API Contracts
│   ├── srs.md                # Software Requirements Specification (v1.0)
│   └── api.md                # Complete REST API Reference Documentation
│
├── .env                      # Environment configuration template
├── requirements.txt          # Python dependencies
└── README.md                 # System documentation
```

---

## Getting Started

### 1. Local Python Environment Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy or edit `.env`:
```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/orion"
REDIS_URL="redis://localhost:6379/0"
LLM_PROVIDER="ollama" # or "openai"; "mock" is an explicit offline/test mode only (no automatic fallback if the LLM fails)
EXTRACTION_PIPELINE="monolithic" # or "split" (4 focused, validated LLM stages per chunk)
EXTRACTION_EXECUTOR="background" # or "celery" (one ordered task per job; requires Redis + a worker)
OLLAMA_URL="http://localhost:11434/api/chat"
OLLAMA_MODEL="llama3.1:8b-instruct-q4_K_M"
```

### 3. Run Migrations

```bash
alembic upgrade head
```

### 4. Start the Application

```bash
# Start FastAPI API Server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery Worker (in a separate terminal)
celery -A app.workers.celery_app worker --loglevel=info
```

Interactive API documentation will be available at:
- Swagger UI: `http://localhost:8000/api/v1/docs`
- ReDoc: `http://localhost:8000/api/v1/redoc`

---

## Docker Quickstart

To run the entire stack (PostgreSQL, Redis, Celery Worker, and FastAPI) using Docker Compose:

```bash
cd backend/docker
docker-compose up --build
```

---

## Running Automated Tests

Run the complete test suite:

```bash
PYTHONPATH=backend pytest app/tests -v
```

---

## Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check endpoint |
| `POST` | `/api/v1/auth/register` | Register a new user account |
| `POST` | `/api/v1/auth/login` | Login and receive JWT access token |
| `GET` | `/api/v1/worlds` | List all worlds with entity/fact statistics |
| `POST` | `/api/v1/worlds` | Create a new fictional world |
| `POST` | `/api/v1/worlds/{id}/manuscripts` | Upload manuscript file & trigger extraction |
| `GET` | `/api/v1/jobs/{job_id}/status` | Poll extraction job progress |
| `GET` | `/api/v1/worlds/{id}/entities` | List world entities with canonical names & facts |
| `GET` | `/api/v1/worlds/{id}/graph` | Graph nodes & edges for knowledge graph visualization |
| `GET` | `/api/v1/worlds/{id}/timeline` | Chronological event timeline |
| `GET` | `/api/v1/worlds/{id}/contradictions` | List detected world state contradictions |
| `POST` | `/api/v1/worlds/{id}/contradictions/{con_id}/resolve` | Resolve or dismiss contradiction |
| `POST` | `/api/v1/worlds/{id}/chat` | Grounded world assistant Q&A chat |
