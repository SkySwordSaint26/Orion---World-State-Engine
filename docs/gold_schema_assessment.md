# Orion gold schema and annotations: assessment and v1.1 proposal

2026-09-30

## Summary

Both hold Orion back, in different ways. The schema works as a span-annotation format, but it can't express four
things the SRS requires, so it falls short as the contract that feeds the world state. The annotations are the bigger
problem today: they are too small and too noisy to trust the scores they produce.

- **Schema:** fine for mentions, coreference, events and time expressions. Missing: father vs mother (REQ-25), a fixed
  dead/alive status (REQ-26), who speaks each line of dialogue (REQ-26, REQ-37), and where each fact is stated
  (REQ-21, REQ-29).
- **Annotations:** 14 facts and 7 relationships in one story, about 69% of occurrences marked, no pronouns, and known
  errors. One fact moves recall by 7 points.
- **Proposal:** a v1.1 schema with six small additions, agreed with the schema's owner, and new annotation aimed at
  what the contradiction rules consume.

## Context

`orion_gold_v1.schema.json` does two jobs. It is the format of the hand-made gold annotations, and it is the output
format of the WSE extraction pipeline, whose results feed the world state and its contradiction rules.

- **Pipeline:** each chapter goes through extraction, then into the world state, then through deterministic
  contradiction rules (REQ-27: no language model decides a contradiction).
- **Scoring:** WSE output is scored against the gold for the 4 parts of "Accounts From a Lonely Broadcast Station"
  (`python -m extractor score`).
- **The rules** (`backend/app/consistency`) check: age going down; a character alive after being marked dead; a
  changed value for birth place, date of birth, origin, eye color or species; conflicting relationships (FRIEND_OF vs
  ENEMY_OF, ENEMY_OF vs MARRIED_TO); and a character's father changing.

The schema describes itself as "text-grounded annotations, not resolved world-state records". That is a sound choice
for annotation. The gaps below appear only because the same schema is also the contract the world state consumes.

## Schema gaps

Four SRS requirements need information the schema cannot hold. Two further gaps are not SRS conflicts but matter for
fiction.

| Requirement | What it needs | What the schema has | Effect today |
|---|---|---|---|
| REQ-25: "a character's stated father changing" | Father and mother told apart | `PARENT_OF` only | The backend rule is keyed on `FATHER_OF`, which extraction can never produce, so it never fires |
| REQ-26: "marked as dead, then shown speaking later" | A fixed dead/alive status, and who speaks each quote | `status` is free text (`in extreme danger`, `unconscious`); no quotes or speakers | The rule needs a DEAD value that no extractor is required to produce; "shown speaking" can't be represented |
| REQ-37: the character chat answers from "extracted dialogue" | Dialogue attributed to a speaker | No quotes or speakers | Nothing to build a character's dialogue from |
| REQ-21 / REQ-29: record a fact, show where it came from | The position of each fact and relationship in the text | Only an entity mention; no evidence span | No source sentence to show; scoring has to match values exactly (`dark` vs `moppy dark`) |

**Whether a statement is true in the story.** Nothing marks a fact as asserted, denied, hypothetical, dreamt or
reported. Rose's dream in part 2, a character's lie, or "I don't think he's dead" would all be recorded as plain facts.
For contradiction detection, a character lying would then be flagged as a contradiction.

**Identity across chapters.** Each chapter is its own document with its own mention and cluster IDs. The gold
therefore cannot check that part 1's Evelyn and part 3's unnamed narrator are the same person, which is exactly what
the world state depends on.

## Annotation problems

The current annotations can show roughly whether extraction works, but they cannot separate a real improvement from
noise.

| Problem | Detail | Effect on scores |
|---|---|---|
| Too small | 14 facts and 7 relationships (after corrections), all from one story, one author, one first-person narrator | One fact moves recall by 7 points; rules may fit this story only |
| Incomplete mentions | About 69% of occurrences of annotated names marked; pronouns never marked; `mention_kind` almost never set | Real but unmarked mentions count as errors, so precision is understated |
| Broken spans | 25 spans cut inside words (placed by substring search) | Those mentions can't be matched exactly |
| Broken references | 19 coreference-cluster members point at mention IDs that don't exist | Left out of coreference scoring |
| Temporal | Every time expression typed `other`; no temporal relations at all | Only time-expression spans can be scored |
| Fact and relationship errors | Found on 2026-09-30, see below | Correct output was scored as wrong |
| Not in the schema's format | Original files use other key names (`entity_mentions`, `start_offset`) | Need a converter (`python -m app.evaluation convert`) |

Corrections made on 2026-09-30, kept in `extractor/data/gold_corrections.json` rather than in the converted files:

- **Removed** `Evelyn occupation radio DJ` in parts 2 and 3: "DJ" does not appear in those chapters.
- **Removed** `Evelyn WORKS_FOR Dan` in part 3: backwards, since Dan is her part-timer and both work for the boss.
- **Merged** the `Dan` and `Daniel` clusters in part 3: one person.
- **Added** 5 facts and 4 relationships stated in the texts (for example Rose's age, Dan's mother, Dan and Evelyn
  working for the boss), and changed Daniel's location in part 2 to the text's own words, "the radio station".

Every corrected item carries an evidence quote, checked against the text when scoring. The corrections are one
reader's judgement and still need review.

## Proposed v1.1 changes

Six additions, all optional fields or new list items, so every valid v1.0 file stays valid under v1.1.

| # | Change | Closes | Cost to annotate |
|---|---|---|---|
| 1 | `FATHER_OF` and `MOTHER_OF` predicates beside `PARENT_OF` | REQ-25 | Low: a different label |
| 2 | Optional `status_value` on `status` facts: `ALIVE`, `DEAD`, `MISSING`, `INJURED`, `UNCONSCIOUS`, `OTHER`; free-text `value` kept | REQ-26 | Low: one dropdown |
| 3 | A `quotes` list: span plus `speaker_mention_id` | REQ-26, REQ-37 | Medium: every quote in a story |
| 4 | Optional `evidence` span (`start`, `end`) on facts and relationships | REQ-21, REQ-29 | Low: select the sentence |
| 5 | Optional `assertion` on facts, relationships and events: `asserted` (default), `negated`, `hypothetical`, `reported` | False contradictions from dreams, lies, denials | Low: default covers most items |
| 6 | Optional `entity_key` on coreference clusters, the same string for the same character in every chapter | Testing identity across chapters | Low: one name per cluster |

Example of a v1.1 fact, relationship and quote from part 4:

```json
{
  "facts": [
    {"fact_id": "F2", "entity_mention_id": "M001", "property": "status",
     "value": "missing", "status_value": "MISSING",
     "evidence": {"start": 16840, "end": 16880}, "assertion": "asserted"}
  ],
  "relationships": [
    {"relationship_id": "R1", "subject_mention_id": "M007", "predicate": "FRIEND_OF",
     "object_mention_id": "M001", "evidence": {"start": 612, "end": 643}}
  ],
  "quotes": [
    {"quote_id": "Q1", "start": 1502, "end": 1550, "speaker_mention_id": "M003"}
  ],
  "coreference_clusters": [
    {"cluster_id": "C010", "mentions": ["M001", "M128"], "entity_key": "jennifer_cook"}
  ]
}
```

Offsets in the example are illustrative, not measured.

Left out on purpose: normalized time values for temporal expressions, and links from events to time expressions. No
current rule uses them.

## Annotation plan

New annotation should cover what the contradiction rules consume, on more varied text. Marking every mention and event
by hand costs the most and pays off least for the product.

1. **Review the 2026-09-30 corrections** in `extractor/data/gold_corrections.json`: 14 facts and 7 relationships, each with
   its quote.
2. **Annotate 2 or 3 new stories** by other authors, at least one in the third person. Mark only facts, relationships,
   status, quotes with speakers and evidence spans. Skip mentions and events.
3. **Write a planted-contradiction set**: 4 to 6 short chapters that each break one rule, with an answer key.
    - age going down;
    - a dead character speaking later;
    - eye color changing;
    - friends becoming enemies with no explanation;
    - a father changing;
    - one control: a character lying or dreaming, which must not be flagged.
4. **Keep the existing 4 stories** for mention, coreference and event scores, with the known defects noted.

The planted set measures what matters for the product: whether a real contradiction is found end to end, and whether a
false one is avoided. Scoring for step 2 needs a small change, because `gold_corrections.json` currently names entities
through gold mentions.

## Open questions

For the teammate who owns the schema:

- [ ] Are the six additions acceptable as optional fields, or should any be required in v1.1?
- [ ] Should `status_value` be a closed list, and are `ALIVE`, `DEAD`, `MISSING`, `INJURED`, `UNCONSCIOUS`, `OTHER`
  the right values?
- [ ] Keep `PARENT_OF` alongside `FATHER_OF` / `MOTHER_OF` for when the text doesn't say which, or replace it?
- [ ] Who annotates the new stories and the planted-contradiction set, and which stories?
- [ ] Should the original annotation files be fixed at the source (the 25 cut spans and 19 broken references), or
  corrected only in the converter?
