# Consistency / Contradiction Engine (SRS REQ-23 to REQ-31)

Single reference for what the deterministic consistency engine does **today**. Where another document
disagrees with this one, this one describes the code.

Principle: **the LLM produces observations; deterministic code decides whether they contradict.** Nothing
under `app/consistency/` or `services/consistency_service.py` imports or calls an LLM (enforced by a test).

## Structure

| Concern | Where |
|---|---|
| Rule definition + controlled vocabulary | [`app/consistency/vocabulary.py`](../../app/consistency/vocabulary.py), [`rules.py`](../../app/consistency/rules.py) |
| Rule evaluation (pure, no I/O) | [`app/consistency/engine.py`](../../app/consistency/engine.py) (`ConsistencyEngine`) |
| Contradiction persistence + dedupe | [`app/consistency/recorder.py`](../../app/consistency/recorder.py), `ContradictionRepository.find_existing` |
| Orchestration (loads rows, calls engine, records) | [`app/services/consistency_service.py`](../../app/services/consistency_service.py) |
| Where it runs | `WorldStateService.integrate_extraction_result`, inside the chapter's single transaction (no commit of its own) |

Checks are incremental: a fact check reads one entity+property, a relationship check reads one entity pair
(plus the target's incoming relationships for single-source predicates), the temporal check reads only the
current chapter's relations.

## IMPLEMENTED

| Rule id | Requirement | What it flags | Type / confidence |
|---|---|---|---|
| `IMMUTABLE_FACT` | REQ-21/22 support | A second, different value for `birth_place`, `date_of_birth`, `origin`, `eye_color`, `species` (compared with the current ACTIVE value, case/whitespace-insensitive) | `FACT_FACT` / 0.9 |
| `AGE_MONOTONIC` | REQ-23 | `age` lower than the nearest earlier chapter's age, or higher than the nearest later chapter's (re-extracted earlier chapter). Same-chapter, unparseable, unchaptered and rejected values are ignored | `FACT_FACT` / 0.7 |
| `DEAD_THEN_ALIVE` | REQ-26 (status part) | `status` dead/deceased in an earlier chapter, alive/living in a later one (and the mirror case) | `FACT_FACT` / 0.7 |
| `RELATIONSHIP_INCOMPATIBLE` | REQ-25 | Same ordered entity pair whose ACTIVE predicate is replaced by an explicitly incompatible one: `ENEMY_OF`/`FRIEND_OF`, `ENEMY_OF`/`MARRIED_TO`, `DEAD_AT_HANDS_OF`/`ALLY_OF` | `RELATIONSHIP_RELATIONSHIP` / 0.85 |
| `RELATIONSHIP_SINGLE_SOURCE` | REQ-25 ("stated father changing") | A second, different `FATHER_OF` source for the same target | `RELATIONSHIP_RELATIONSHIP` / 0.6 |
| `TEMPORAL_CYCLE` | (existing cycle protection) | `BEFORE`/`AFTER` relations of a chapter that form a cycle; deterministic output, one finding per distinct cycle | `CYCLE` / 1.0 |

Behaviour on a finding: the new version is stored with status `CONTRADICTED` (never deleted, REQ-22) and the
earlier ACTIVE version stays ACTIVE. With no finding, a changed value supersedes the old one as before.
Confidence values are fixed per rule (not calibrated).

Controlled vocabulary: rules only act on the names listed in `vocabulary.py`. Any other property or predicate is
UNKNOWN: it is versioned normally but can never create a contradiction. Names are normalized for case and
separators only (`Eye Color` -> `eye_color`, `friend of` -> `FRIEND_OF`); synonyms (`eye colour`, `dad`) are **not**
guessed. Mapping synonyms belongs to a later observation-normalization stage.

Persistence (existing schema only): `contradiction_type`, `old/new_fact_version_id` or
`old/new_relationship_version_id` (chapter is reachable through those rows), `event_id_a/b` (the two events
that close a cycle), `confidence`, `status`, `explanation`. The schema has no rule column, so every explanation
starts with `[RULE_ID] `. Duplicates (same rule, same conflicting rows, any status) are not re-created.

## KNOWN LIMITATIONS (read before relying on the results)

These are explicit gaps, each marked with a `TODO(...)` at the code location where the fix will go.

1. **Property normalization is NOT implemented.** Only case and separators are normalized, and only when a rule
   reads a stored name. Facts are *stored* under the raw LLM property name, so `Eye Color` and `eye_color` are two
   separate fact rows and a change between them is **not** detected (a test documents this). Synonyms
   (`eye colour`, `birthplace`) are not recognised. Insertion point: `WorldStateService.integrate_extraction_result`,
   before `get_or_create_fact` (`TODO(property-normalization)`).
2. **`AGE_MONOTONIC` is a heuristic.** It cannot distinguish a flashback from an age decrease (there is no
   flashback marker in the schema or extraction output), so it can misfire on flashbacks and non-linear
   narration. That is why its confidence is 0.7; treat findings as candidates for review. `DEAD_THEN_ALIVE` has
   the same weakness.
3. **Temporal consistency is single-chapter only.** `TEMPORAL_CYCLE` checks the relations extracted from the
   chapter being integrated. Temporal relations are not persisted, so cycles that span chapters are not seen, and
   chunk-local event ids can collide inside one chapter. Insertion point: the `TemporalCheck` built in
   `ConsistencyService.run_checks` (`TODO(temporal-normalization)`).
3b. There is no temporal *reasoning* (durations, dates, "time_expression" is dropped): only BEFORE/AFTER cycles.
4. **Relationship symmetry is not handled.** Relationships are keyed by direction, and no predicate is treated as
   symmetric, so `Alice ENEMY_OF Bob` vs `Bob FRIEND_OF Alice` are never compared. Predicate synonyms/inverses
   (`SON_OF` vs `FATHER_OF`) are not mapped either. Insertion points: the predicate read in
   `WorldStateService.integrate_extraction_result` and `IncompatiblePredicateRule`
   (`TODO(relationship-normalization)`).

To find every marker: `grep -rn "TODO(.*-normalization)" backend/app`.

## DEFERRED (required information is not represented by the frozen schema / current extraction contract)

| Rule | Why it is deferred |
|---|---|
| **REQ-24 location ("in two places at once")** | The `events` table has no location and no time; the extractor emits `location` and `time_expression` per event but integration cannot persist them. "Same time" is undecidable, and comparing `location` facts inside one chapter would flag ordinary travel. `location` is registered as MUTABLE with no rule. The `EVENT_LOCATION` type is reserved and unused. |
| **REQ-26 "speaking / acting after death"** | There is no speaker or dialogue attribution, `event_participants.role` is always `PARTICIPANT` (the deceased and the killer are indistinguishable in a `DEATH` event), and participation is not acting (funerals, memories, flashbacks). Only the status-fact part (`DEAD_THEN_ALIVE`) is implemented. |

## NOT SUPPORTED BY THE CURRENT DATA MODEL (limitations of the implemented rules)

- No flashback marker: `AGE_MONOTONIC` and `DEAD_THEN_ALIVE` can flag flashbacks, hence confidence 0.7.
- No way to record an explanation for a change ("adopted", "was resurrected"): REQ-25's "without explanation" cannot be evaluated, so `RELATIONSHIP_SINGLE_SOURCE` reports candidates (0.6).
- Temporal relations are not persisted, so cycles are detected within one chapter only, never across chapters.
- The extractor's event ids are local (`event_1` ...) and not namespaced per chunk, so two chunks of one chapter can collide; the temporal rule cannot tell such events apart. This is an extraction-contract problem for a later phase.
- Incompatible-pair and single-source checks are directional: `Alice ENEMY_OF Bob` and `Bob FRIEND_OF Alice` are different relationship rows and are not compared.
- Deduplication identity is (rule prefix in the text, type, version/event ids); a cycle with no persisted events falls back to exact explanation text, which includes the chapter number.
