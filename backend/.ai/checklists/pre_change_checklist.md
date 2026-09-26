# Pre-Change Checklist

Run through this checklist **before** writing or modifying code.

---

## 1. Requirements & Scope
- [ ] Have I identified the relevant requirement in [`docs/srs.md`](../../../docs/srs.md) or [`srs_requirements_matrix.md`](../context/srs_requirements_matrix.md)?
- [ ] Is this change aligned with the [Rules](backend/.ai/RULES.md) (e.g. deterministic contradiction checks, immutable facts, tenant isolation)?

## 2. Architectural Impact
- [ ] Does this change require modifying SQLAlchemy models?
  - If yes, follow [`database-migration`](../skills/database-migration/SKILL.md) and prepare an Alembic migration.
- [ ] Does this change affect existing API contracts used by the frontend store ([`useWorldStore.ts`](../../../Frontend/src/store/useWorldStore.ts))?
  - If yes, verify response fields remain backward-compatible.

## 3. Test Baseline
- [ ] Run the existing test suite:
  ```bash
  PYTHONPATH=backend pytest app/tests/ -q
  ```
  Confirm all tests pass *before* making edits.
