# Orion World State Engine — AI Agent Entrypoint

Welcome, AI Agent. You are operating inside the **Orion World State Engine (WSE)** backend repository.

> **CRITICAL REPOSITORY CONTEXT**: This repository is a **fork**. All modifications must respect upstream safety, atomic commit hygiene, and strict schema versioning. Never commit haphazard, unverified code or hallucinated assumptions.

---

## The Mental Model in 30 Seconds

The World State Engine converts narrative fiction prose into a structured, queryable, versioned relational state while algorithmically tracking contradictions.

1. **Extraction is Probabilistic**: An LLM extracts entities, relationships, and events from chapter text into structured JSON.
2. **State Integration is Deterministic**: Mentions are clustered into canonical entities, facts are versioned rather than overwritten, and relationships are mapped.
3. **Consistency Verification is Rule-Based**: Per **SRS REQ-27**, contradiction detection **never** relies on an LLM to decide conflicts. It runs deterministic rules (immutable facts, age progression, dead-then-alive status, relationship conflicts, and DFS temporal cycles); location clashes and acting-after-death are deferred (see [`context/consistency_engine.md`](context/consistency_engine.md)).
4. **World State is Permanent**: Per **SRS REQ-22 & Section 6**, previously stored facts are never overwritten in SQL. All versions are retained forever.

---

## Fast Navigation Map

| Document | Description | When to Read |
|---|---|---|
| [**PHILOSOPHY.md**](PHILOSOPHY.md) | Andrej Karpathy-style first principles, Software 2.0/3.0 mindset, anti-patterns | Before designing or refactoring any component |
| [**ARCHITECTURE.md**](ARCHITECTURE.md) | Mechanistic breakdown of request flows, layers, and data pipelines | When understanding how pieces connect |
| [**RULES.md**](RULES.md) | Non-negotiable technical invariants, security boundaries, and performance budgets | **Mandatory** before modifying code |
| [**WORKFLOW.md**](WORKFLOW.md) | Git fork synchronization, branching strategy, atomic commits, PR guidelines | Before creating branches or committing code |
| [**DEBUGGING.md**](DEBUGGING.md) | Hypothesis-driven debugging protocol & catalog of known failure modes | Whenever an error or test failure occurs |

### Context Documents (`context/`)
- [**srs_requirements_matrix.md**](context/srs_requirements_matrix.md): Complete traceability matrix mapping SRS REQ-1 through REQ-51 to codebase modules.
- [**system_overview.md**](context/system_overview.md): System components, dependency layers, and execution modes.
- [**db_schema_reference.md**](context/db_schema_reference.md): Complete 12-table ER schema, foreign keys, cascade rules, and status enums.
- [**api_contracts.md**](context/api_contracts.md): REST endpoints, request/response schemas, frontend integration contracts.
- [**pipeline_deep_dive.md**](context/pipeline_deep_dive.md): Extraction prompt design, parser repair, coreference clustering, and rule engines.

### Actionable Skills (`skills/`)
- [**add-api-endpoint**](skills/add-api-endpoint/SKILL.md): Recipe to add a new REST route across all layers.
- [**database-migration**](skills/database-migration/SKILL.md): Recipe to update models and generate Alembic migrations safely.
- [**llm-pipeline-refinement**](skills/llm-pipeline-refinement/SKILL.md): Recipe to refine prompts, parsers, and resolution algorithms.
- [**consistency-rule-authoring**](skills/consistency-rule-authoring/SKILL.md): Recipe to author deterministic contradiction checks.
- [**celery-background-tasks**](skills/celery-background-tasks/SKILL.md): Recipe to add and test asynchronous background workers.
- [**test-driven-verification**](skills/test-driven-verification/SKILL.md): Recipe to write and run unit and integration tests.

### Specialized Agent Personas (`agents/`)
- [**backend-architect.md**](agents/backend-architect.md): System architecture, tenant isolation (REQ-4), and performance budgets.
- [**pipeline-engineer.md**](agents/pipeline-engineer.md): Prompt engineering, coreference resolution, and parsing robustness.
- [**consistency-auditor.md**](agents/consistency-auditor.md): Rule-based contradiction checks and graph cycle audits.
- [**test-sentinel.md**](agents/test-sentinel.md): Regression testing, mock isolation, and edge-case verification.

### Verification Checklists (`checklists/`)
- [**pre_change_checklist.md**](checklists/pre_change_checklist.md): Verify before editing code.
- [**pre_commit_checklist.md**](checklists/pre_commit_checklist.md): Verify before staging and committing.
- [**fork_sync_checklist.md**](checklists/fork_sync_checklist.md): Verify when pulling updates from upstream.

---

## Essential Developer Commands

```bash
# Activate virtual environment
cd backend
source .venv/bin/activate

# Run full test suite
PYTHONPATH=backend pytest app/tests/ -v

# Run single test file
PYTHONPATH=backend pytest app/tests/test_api.py -v

# Start FastAPI local server with reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery worker
celery -A app.workers.celery_app worker --loglevel=info
```
