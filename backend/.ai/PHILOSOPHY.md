# Engineering Philosophy & First Principles

> *"Simplicity is a prerequisite for reliability. Complex systems that work are invariably found to have evolved from simple systems that worked."*
> — Adapted from John Gall & Andrej Karpathy

This document outlines the intellectual framework and design heuristics governing the Orion World State Engine. Every AI agent writing code in this repository must internalize these principles.

---

## 1. First-Principles Thinking: What is This System?

At its core, the World State Engine bridges two fundamentally different computing paradigms:

```
[Raw Narrative Text]
       │
       ▼
 [LLM Extraction]         <--- Probabilistic, Stochastic, Fuzzy Pattern Matcher
       │
       ▼
 [Structured Tokens]      <--- Pydantic Schemas, Sanitized Dictionaries
       │
       ▼
[Relational State Engine] <--- Deterministic, ACID, Append-Only Graph
       │
       ▼
[Rule-Based Verification] <--- Algorithmic, Provable Consistency (SRS REQ-27)
```

1. **The Language Model is a Token Transducer, NOT a Database**:
   A language model predicts likely sequences of tokens. It does not "know" truth, it does not maintain transactional consistency, and it cannot be trusted to verify its own logic over time. We use the LLM for what it is brilliant at: reading messy prose and extracting structured entity/relation candidates into JSON.

2. **The Database is the Source of Truth**:
   The database records the physical, permanent state of the fictional universe. It must enforce relational constraints, foreign keys, timestamps, and version provenance.

3. **Consistency Verification is Deterministic (SRS REQ-27)**:
   **Never ask an LLM: *"Do these two facts contradict?"***
   Why? Because:
   - LLM answers are stochastic; re-running the check can give conflicting results.
   - LLMs suffer from recency and confirmation bias.
   - LLM calls are expensive and slow (latency budget: consistency detection must complete in ≤ 5 seconds per SRS 5.1).
   - In contrast, algorithmic Python code (age monotonicity, dead-then-alive status, incompatible relationships, temporal cycle DFS; geographic-overlap and acting-after-death rules are deferred, see `context/consistency_engine.md`) is deterministic, sub-millisecond, unit-testable, and provable.

---

## 2. The Software 2.0 / 3.0 Mindset

Andrej Karpathy defines Software 2.0/3.0 as systems written in neural network weights and prompted instructions rather than explicit C++ or Python loops. But mission-critical systems require **Software 1.0 scaffolding around Software 3.0 engines**:

- **Defensive Ingestion**: Expect the LLM to return markdown fences (` ```json `), trailing commas, missing keys, or capitalized booleans. Always sanitize through [`extraction_parser.py`](../app/pipeline/parsers/extraction_parser.py).
- **Hard Schema Boundaries**: Never pass raw LLM dictionaries directly to database models or frontend clients. Always validate through Pydantic schemas with `model_config = ConfigDict(from_attributes=True)`.
- **Grounded Closed-World Assumption (SRS REQ-37..38)**: When simulating a character in chat, the agent operates under a closed-book constraint. If a fact was not extracted from the manuscript, the character must state ignorance. Never allow the LLM to invent background lore.

---

## 3. Permanent State Immutability (SRS REQ-22 & Section 6)

In a fictional manuscript, truth is not static:
- In Chapter 1, Alice is 28 years old.
- In Chapter 10 (set 5 years later), Alice is 33 years old.
- In Chapter 15, an unedited draft mistakenly states Alice is 22 years old.

If you execute an SQL `UPDATE facts SET value = '22'`, you have permanently destroyed the world state history.
Instead, we treat state like **Git commits**:
- Every observation is an immutable version row (`fact_versions`, `relationship_versions`).
- The version records `chapter_id`, `extraction_run_id`, `status` (`ACTIVE`, `SUPERSEDED`, or `CONTRADICTED`), and `created_at`.
- You can query the world state at *any* chapter in time (SRS REQ-33) and diff changes between two chapters (SRS REQ-34).

---

## 4. Karpathy Code Heuristics

1. **Write "Hackable", Transparent Code**:
   Avoid deep inheritance hierarchies, dynamic metaclass sorcery, and obscure magical decorators. A developer or AI agent should be able to jump to a function definition, read 25 lines of plain Python, and completely understand what happens.
2. **Fail Visibly, Not Silently**:
   Do not write `try: ... except Exception: pass` or return `None` when something corrupts data. Log the failure, mark the job as `FAILED`, record the error message, and preserve diagnostic state.
3. **Keep Layer Boundaries Clean**:
   - **Route**: Parses HTTP request, checks dependencies, calls Service, returns Schema. No business logic.
   - **Service**: Implements business workflow, orchestrates repositories, runs validation. No raw SQL.
   - **Repository**: Encapsulates DB queries, filters, joined loads. No HTTP concepts.
   - **Pipeline**: Encapsulates LLM calls, chunking, and mention clustering. Decoupled from HTTP.

---

## 5. Catalog of Anti-Patterns (Zero Tolerance)

| Anti-Pattern | Why It Breaks the System | What to Do Instead |
|---|---|---|
| **Delegating Contradiction Logic to LLM** | Violates SRS REQ-27. Slow, non-deterministic, untestable. | Write deterministic rule functions in `consistency_service.py`. |
| **Silent In-Place SQL Updates on Facts** | Violates SRS REQ-22. Destroys historical timeline snapshots. | Append new `FactVersion` with status `ACTIVE`, `SUPERSEDED`, or `CONTRADICTED`. |
| **Packing Conflicting Values into Lists** | Packing `["blue", "green"]` into a single field hides contradictions. | Store each observation as a distinct version row linked to a `Contradiction` row. |
| **Missing Tenant Isolation (`user_id`)** | Violates SRS REQ-4 & 5.3. Allows User A to read/modify User B's project. | Filter every world, manuscript, and entity query by authorized `user_id`. |
| **Direct LLM Invocation in API Routes** | Freezes the HTTP worker, causing 60-second request timeouts. | Use Celery tasks or FastAPI `BackgroundTasks` with job status polling (`/jobs/{id}`). |
| **Skipping Alembic Migrations** | Causes database schema drift and runtime SQL `OperationalError`. | Always generate and commit an Alembic migration when modifying models. |
