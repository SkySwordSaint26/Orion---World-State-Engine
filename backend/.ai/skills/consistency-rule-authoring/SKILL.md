---
name: consistency-rule-authoring
description: Recipe for adding deterministic, rule-based contradiction checks per SRS REQ-23..28.
---

# Skill: Authoring Consistency & Contradiction Rules

Per **SRS REQ-27**, all contradiction detection must be **rule-based and shall not rely on a language model**.
Current rules and deferred ones: [`context/consistency_engine.md`](../../context/consistency_engine.md).

## 1. Architecture (`app/consistency/`)

| Piece | File | Rule of thumb |
|---|---|---|
| Vocabulary | `vocabulary.py` | A rule may only act on names listed here. Unknown properties/predicates never contradict. |
| Data types | `types.py` | Rules receive plain views (`FactCheck`, `RelationshipCheck`, `TemporalCheck`) and return `Finding`s. No ORM, no DB, no LLM. |
| Rules | `rules.py` | One small class per rule: `rule_id`, `applies(check)`, `evaluate(check)`. |
| Engine | `engine.py` | Routes a check to every applicable rule in a fixed order. |
| Persistence | `recorder.py` | Flush-only (`commit=False`) with deduplication. |
| Orchestration | `services/consistency_service.py` | Loads the affected rows incrementally, calls the engine, records findings. |

## 2. Adding a rule

1. Confirm the SRS requires it, that the frozen schema can represent every input it needs, and that the extraction output actually provides it. If not, record it as DEFERRED in `context/consistency_engine.md`; do not invent schema or inference.
2. Add any new controlled property/predicate to `vocabulary.py` (no synonym guessing).
3. Implement the rule class in `rules.py` and register it in `ConsistencyEngine`'s defaults.
4. Give the finding a `rule_id` (persisted as a `[RULE_ID]` explanation prefix), one of the existing `ContradictionType` values, and a fixed confidence.
5. Add pure unit tests in `app/tests/test_phase2_rules.py` (valid case, contradiction, mutable/unknown non-cases) and an integration test in `test_phase2_integration.py`.

Never commit inside a rule or the recorder: the chapter transaction is owned by `execute_chapter_extraction`.

## Verification
```bash
cd backend && .venv/bin/python -m pytest app/tests/test_phase2_rules.py app/tests/test_phase2_integration.py -v
```
