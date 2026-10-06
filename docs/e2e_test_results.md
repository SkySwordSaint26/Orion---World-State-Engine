# End-to-end test results

**Date:** 30 September 2026
**Story used:** [`e2e_story_gull_point.txt`](e2e_story_gull_point.txt), a new 4-chapter story (517 words) written for this test

> **Update, 3 October 2026: fixes 1 and 2 from section 6 are done.** The same person is now kept as one entry
> across chapters, and more ways of writing "alive"/"dead" are understood. Re-running the story: **4 of 5
> contradictions found** (was 0), still no false alarms. The 8 real people, places and groups are now 8 entries
> (was 19). See [section 8](#8-re-run-after-the-name-linking-fix-3-october-2026). Sections 1–7 describe the
> original run and are left as they were.
>
> **Update, 6 October 2026: fixes 3 and 5 are done.** **All 5 contradictions are now found**, and 4 of the 5
> planted relationships (was 0). Titles are saved as facts: Hanna is a doctor and Brandt is a Captain. See
> [section 9](#9-re-run-after-the-relationship-and-title-fixes-6-october-2026).
>
> **Update, 6 October 2026 (later): the timeline (Failure 6) is fixed.** Brandt's death is now a DEATH event,
> places are tagged as locations instead of people, and everyone in "Mara, Tobias and Lily" is listed. See
> [section 10](#10-re-run-after-the-timeline-fixes-6-october-2026).

## The short version

- **The plumbing works.** A story goes in through the API, every chapter is extracted, the results are saved in
  the database, and every page of the app can read them back. Nothing crashed and no step failed.
- **Finding people, places and facts mostly works.** All 8 real people, places and groups were found. 12 of the
  15 facts we planted were picked up correctly, such as ages, eye colour and birthplace.
- **Spotting contradictions does not work yet: 0 out of 5 were found.** This is the main thing the app is for.
  The rules themselves are fine. They never fire because the same person gets saved as two or more different
  people, for example "Mara Quinn" in chapter 1 and "Mara" in chapter 3.
- **Relationships are mostly missed.** None of the 5 planted relationships ("Mara is Lily's mother", "Tobias is
  Mara's brother", ...) came out right.
- **It is slow.** Each chapter takes about 35 seconds. The target in the requirements is 10 seconds.

## 1. What we tested and how

We wrote a new story that the system had never seen, so the results can't come from earlier tuning. The story
has **planted answers**: facts, relationships and five deliberate mistakes (contradictions) that the app should
catch.

| Chapter | What happens | What we planted |
|---|---|---|
| 1. The Keeper | Mara Quinn keeps a lighthouse. Her daughter Lily, her brother Tobias, her enemy Captain Brandt and Doctor Hanna Weiss are introduced. | Mara is **41**, has **green** eyes, was born in **Port Averly**. Brandt is Mara's **enemy**. |
| 2. The Storm | A storm hits. Brandt's ship sinks. | Brandt is **dead**. |
| 3. The Letter | Mara goes to Port Averly. | Mara says she is **38** (mistake: she got younger) and has **grey** eyes (mistake: eye colour changed). Lily is now 10 (normal ageing, *not* a mistake). |
| 4. The Visitor | Brandt walks into the tavern. | Brandt is **alive** (mistake: he was dead). Brandt is Mara's **oldest friend** (mistake: he was her enemy). Mara was born at **Gull Point** (mistake: birthplace changed). |

**How it was run:** the real app, the way a user would use it.

1. Postgres, Redis and the frontend were running in Docker. The API ran on this machine, as `./start.sh` does.
2. A script used the API to register a new user, create a world, upload the story and wait for the job to finish.
3. The script then called every endpoint the frontend uses: world, manuscripts, chapters, entities,
   contradictions, timeline, graph and chat.
4. We also read the database directly, and ran the extractor on chapters 1 and 3 by hand to see its raw output.

## 2. Scoreboard

| Area | Result | Verdict |
|---|---|---|
| Upload → extraction → database → API | 4 of 4 chapters done, 0 errors, job finished in 145 s | ✅ Works |
| API endpoints the frontend uses | 9 of 9 answered correctly (all under 0.1 s) | ✅ Works |
| Finding people, places and groups | 8 of 8 found, all with the right type | ✅ Works |
| Keeping one entry per person | 19 entries saved for 8 real people/places (11 extra) | ❌ Fails |
| Facts (age, eye colour, birthplace ...) | 12 of 15 planted facts found (80%). 20 of 22 saved facts are correct (91%) | ✅ Mostly works |
| Relationships | 0 of 5 planted relationships found | ❌ Fails |
| Timeline events | 15 events across the 4 chapters, but 5 have no people attached and some types are wrong | ⚠️ Partly works |
| Contradictions | 0 of 5 found (and no false alarms) | ❌ Fails |
| AI chat | 4 of 4 answered. 3 were right or partly right, 1 was wrong. 2 of 4 were slower than 3 s | ⚠️ Partly works |
| Speed | about 35 s per chapter (target: 10 s) | ❌ Fails |

## 3. What works

### The whole chain runs without errors
The job moved through `queued → processing → done` and reported progress after each chapter (1/4 at 39 s,
2/4 at 75 s, 3/4 at 111 s, 4/4 at 145 s). Every chapter's run ended as `done` with no error message. The
chapters were detected correctly from the "Chapter N:" headings, with their titles.

### The API gives the frontend everything it needs
Every endpoint the frontend calls answered with status 200 in under a tenth of a second:
the world with its counts, the manuscripts, the chapters, the entities with their facts, the contradictions, the
timeline, the relationship graph, and chat. The frontend server itself answered too. We could not click through
the pages in a browser because the browser extension was not connected, but they read exactly these endpoints.

### People, places and groups are found
All 8 real names in the story were found with the right type:

- **People:** Mara Quinn, Lily Quinn, Tobias Quinn, Elias Brandt, Hanna Weiss
- **Places:** Gull Point, Port Averly
- **Group:** Harbor Council

### Most facts are read correctly
| Planted fact | Found? |
|---|---|
| Mara is 41 (ch 1) | ✅ "forty-one" |
| Mara has green eyes (ch 1) | ✅ |
| Mara was born in Port Averly (ch 1) | ✅ |
| Lily is 9 (ch 1) | ✅ "nine" |
| Tobias is a fisherman (ch 1) | ✅ |
| Brandt is dead (ch 2) | ✅ |
| Mara is 38 (ch 3) | ✅ "thirty-eight" |
| Mara has grey eyes (ch 3) | ✅ |
| Mara is in Port Averly (ch 3) | ✅ |
| Lily is 10 (ch 3) | ✅ "ten" |
| Brandt is alive (ch 4) | ✅ saved as "alive and well" |
| Mara was born at Gull Point (ch 4) | ✅ |
| Mara is a lighthouse keeper (ch 1) | ❌ missed |
| Hanna is a doctor (ch 1) | ❌ missed (wrong value saved instead, see below) |
| Brandt is a captain (ch 1) | ❌ missed |

Facts that change over time are handled well. When Mara's location changed from Port Averly (ch 3) to Gull
Point (ch 4), the old value was marked **superseded** and the new one **active**, which is exactly right.

### The chat answers from the saved data
The chat read the saved world and answered every question. It even noticed on its own that Brandt appears as both
dead and alive, although the contradiction checker had not flagged it.

## 4. What fails, and why

The problems below are ordered by how much damage they do. The first one causes most of the others.

### Failure 1: the same person is saved as several different people
This is the biggest problem. The 8 real people and places became **19 entries**:

| Real person or place | Saved as |
|---|---|
| Mara Quinn | "Mara Quinn" (ch 1) and "Mara" (ch 2–4) |
| Lily Quinn | "Lily Quinn" (ch 1) and "Lily" (ch 2–3) |
| Tobias Quinn | "Tobias Quinn" (ch 1), "Tobias" (ch 2–3) and "uncle" (ch 3) |
| Elias Brandt | "Elias Brandt" (ch 1–2), "Captain Brandt" (ch 2), "Captain Elias Brandt" (ch 4) and "Mara's oldest friend" (ch 4) |
| Hanna Weiss | "Hanna Weiss" and "Hanna" (ch 4) |
| Harbor Council | "Harbor Council" and "Council" (ch 3) |

On top of these, "Harbor" and "mother" were saved as entries of their own. "mother" means two different
mothers (see Failure 4).

**Why it happens.** There are two causes that work together:

1. **Across chapters, the app only links names that match exactly.** A new chapter is joined to an existing
   entry only if the name is exactly the same, or is a saved nickname (alias). "Mara" is not the same text as
   "Mara Quinn", so chapter 3 creates a new "Mara".
2. **Chapter 1 never saved "Mara" as a nickname.** In chapter 1 the extractor only recognised the full name "Mara
   Quinn". The later short mentions ("Mara was born in Port Averly", "Mara's brother") were not picked up as
   names. They were linked to the right person only through "she"/"her". So the only name on file was
   "Mara Quinn", and there was nothing for "Mara" to match later.

Titles cause the same problem: "Captain Brandt" and "Captain Elias Brandt" don't match "Elias Brandt".

### Failure 2: no contradictions were found (0 of 5)
The contradiction rules only compare facts **on the same entry**. Because of Failure 1, each pair of conflicting
facts sits on two different entries, so the rules never see them side by side.

| Planted contradiction | Why it was missed |
|---|---|
| Mara's age went down (41 → 38) | 41 is on "Mara Quinn", 38 is on "Mara" |
| Mara's eye colour changed (green → grey) | green is on "Mara Quinn", grey is on "Mara" |
| Mara's birthplace changed (Port Averly → Gull Point) | Port Averly is on "Mara Quinn", Gull Point is on "Mara" |
| Brandt was dead, then alive | "dead" is on "Elias Brandt" and "Captain Brandt", "alive" is on "Captain Elias Brandt". **Also:** the value was saved as "alive and well", and the rule only understands exactly "alive" or "living". So it would have been missed even on one entry |
| Brandt went from enemy to friend | Neither relationship was extracted (see Failure 3) |

The good news: there were **no false alarms**. Lily growing from 9 to 10 was correctly not treated as a
mistake. And the rules do work when names match: in the earlier two-chapter test, where "Dan Harper" was used in
both chapters, the age contradiction was caught.

### Failure 3: relationships are mostly missed
| Planted relationship | What the story says | Result |
|---|---|---|
| Mara is Lily's parent | "Her daughter, Lily Quinn" | ❌ not found |
| Mara and Tobias are siblings | "Mara's brother, Tobias Quinn" | ❌ not found |
| Brandt is Mara's enemy | "Captain Elias Brandt was Mara's enemy" | ❌ not found |
| Hanna works for the Harbor Council | "Doctor Hanna Weiss worked for the Harbor Council" | ❌ not found |
| Brandt is Mara's friend | "Brandt was Mara's oldest friend" | ❌ saved as "Mara FRIEND_OF Mara's oldest friend": the phrase became a new "person" instead of pointing at Brandt |

Only 4 relationships were saved in total:

- "mother PARENT_OF Mara Quinn": **correct** (Mara's mother), but that person has no name.
- "mother PARENT_OF Lily": **wrong person**. It should be Mara. See Failure 4.
- "Lily RELATED_TO uncle": true but vague. The uncle is Tobias, and the relationship type is too general.
- "Mara FRIEND_OF Mara's oldest friend": the other side should be Brandt.

**Why:** the extractor did not produce these relationships from these sentences. The ones it did produce involve
role words ("mother", "uncle", "oldest friend"), and those role words were not connected back to the named person
they refer to.

### Failure 4: unnamed people with the same role word get merged
"Her mother" in chapter 1 is Mara's mother. "Her mother" in chapter 3 is Lily's mother, who is Mara. Both were
saved under the same entry called "mother", because the app joins entries by name. This produced the wrong
relationship "mother PARENT_OF Lily".

### Failure 5: some fact values are wrong or unusable
- **Hanna's job** was saved as "examined the body" (ch 2), then replaced by "bakery" (ch 3, from "brought bread
  from the bakery"). The correct answer, "doctor", comes from her title "Doctor Hanna Weiss", which was not read
  as a job.
- **Mara's job** ("had kept the lighthouse") and **Brandt's title** ("Captain") were not saved as facts.
- **"alive and well"** was saved as written, so the dead-then-alive rule cannot use it (see Failure 2).

### Failure 6: timeline events are rough
15 events were saved, and the right chapters are shown in order. But:
- **Brandt's death is not recorded as a death.** "His ship broke apart ... found his body" became a DESTRUCTION
  and a DISCOVERY event, with no people attached.
- **Places are listed as people taking part.** For example "Port Averly" in "Mara travelled to Port Averly", and
  "Gull Point" in the stranger's arrival.
- **"she"/"he" are dropped as participants.** 5 of the 15 events have nobody attached, for example "Hanna arrived
  at the lighthouse".
- **Some sentences are the wrong kind of event.** "Mara said nothing." is saved as a CONVERSATION.

### Failure 7: it is too slow
Each chapter took **about 35 seconds** (34.5 s and 36.2 s when timed alone; the whole 4-chapter job took 145 s).
The requirement is **10 seconds per chapter**.
**Why:** each chapter starts a fresh extractor program. That program loads its language models from disk every
time before it can read a single sentence, and then runs several models one after the other.

### Failure 8: the chat can make things up and is sometimes slow
- Asked "Who is Tobias Quinn?", it answered that he is "the father of Mara Quinn and Lily Quinn". That is wrong:
  he is Mara's brother and Lily's uncle. The saved data contains no relationship for Tobias at all (Failure 3),
  so the chat model guessed.
- Asked about Mara's age and eyes, it only reported the chapter 1 values ("forty-one", "green"). Chapters 3–4 were
  saved under the separate "Mara", so the chat did not connect them (Failure 1).
- Answer times were 3.9 s, 0.4 s, 3.2 s and 0.9 s. **2 of 4 were over the 3-second target.**

## 5. What was not tested
- **Clicking through the web pages in a browser**: the browser extension was not connected. The frontend server
  was up and every endpoint it reads worked, but the pages themselves were not looked at.
- **The Celery (Redis) way of running jobs**: this run used the default in-process runner.
- **Editing a chapter and running extraction again**.
- **Using the chat while a job is running**: the chat model and the extractor don't fit on the 6 GB GPU at the
  same time (`./start.sh` warns about this).

## 6. What to fix first
1. ✅ *Done 3 Oct 2026, see section 8.* **Link short names to full names across chapters.** Example: "Mara" → "Mara Quinn" when exactly one saved
   person has that first name; drop titles like "Captain" and "Doctor" before comparing. This one change would
   likely bring back 4 of the 5 missed contradictions.
2. ✅ *Done 3 Oct 2026, see section 8.* **Accept more ways of writing "alive" and "dead"**, such as "alive and well", "survived", "drowned".
3. ✅ *Mostly done 6 Oct 2026, see section 9.* **Improve relationships**: sentences like "her daughter, X", "X's brother, Y", "X was Y's enemy" and "X worked
   for Y". Also point role words ("uncle", "oldest friend") at the named person they refer to.
4. *Deferred: speed is out of scope for now.* **Keep the extractor running between chapters** instead of starting it fresh each time, so the models load
   only once. This is the biggest part of the 35 seconds.
5. ✅ *Done 6 Oct 2026, see section 9.* **Read titles as facts**: "Doctor" → occupation, "Captain" → title.

## 7. How to run this test again
1. Start the app: `./start.sh`, or start the API on its own with
   `cd backend && .venv/bin/uvicorn app.main:app --port 8000`.
2. In the app, create a world and upload `docs/e2e_story_gull_point.txt`.
3. Compare what you see with the planted answers in section 1.

To look at the raw extractor output for one chapter:
`cd extractor && .venv/bin/python -m extractor run CHAPTER.txt OUT.json`.

## 8. Re-run after the name-linking fix (3 October 2026)

**What changed** (fixes 1 and 2 from section 6):

- **Titles are dropped from names.** "Captain Elias Brandt" is saved as "Elias Brandt". Words like Captain,
  Doctor, Dr, Mr, Mrs and Sir are removed from the start of a name (`backend/app/contracts/normalization.py`).
- **Short names find the full name.** If no saved name or nickname matches exactly, a name is linked to a saved
  entry when its words fit inside that entry's name, or the other way round. "Mara" fits "Mara Quinn" and
  "Council" fits "Harbor Council". This only happens when the type is the same and **exactly one** saved entry
  fits: "Quinn", with three Quinns saved, gets a new entry instead of a guess. The short name is then saved as a
  nickname, so later chapters match it exactly (`WorldStateService.find_entity`).
- **Role words are never joined by name across chapters.** "mother", "uncle" and "Mara's oldest friend" are not
  names. Each chapter's "mother" is now its own entry, so Mara's mother and Lily's mother are no longer one
  person (this fixes Failure 4).
- **More status words.** "alive and well", "still alive" and "survived" count as alive. "died", "drowned",
  "killed", "murdered" and "slain" count as dead.

**How it was run:** the same story, through the real extractor and the real extraction task, chapter by chapter.
It used a scratch SQLite database instead of the Docker Postgres. Two new tests in
`backend/app/tests/test_phase2_integration.py` cover the same cases. The full backend suite passes (217 tests).

| Area | Before (30 Sep) | After (3 Oct) |
|---|---|---|
| Entries for the 8 real people/places/groups | 19 | **8**, one each |
| Entries saved in total | 19 | 13 (the 8, plus "Harbor", 2 × "mother", "uncle", "Mara's oldest friend") |
| Contradictions | 0 of 5 | **4 of 5** |
| False alarms | 0 | 0 (Lily 9 → 10 still correctly not flagged) |
| Relationships | 0 of 5 | 0 of 5 (no change, see below) |
| Time per chapter | about 35 s | 35–45 s (no change expected) |

How each person and place is saved now:

| Saved entry | Nicknames |
|---|---|
| Mara Quinn | Mara |
| Lily Quinn | Lily |
| Tobias Quinn | Tobias |
| Elias Brandt | Brandt |
| Hanna Weiss | Hanna |
| Harbor Council | Council |
| Gull Point, Port Averly | none |

Contradictions found:

| Planted contradiction | Found? |
|---|---|
| Mara's age went down (41 → 38) | ✅ AGE_MONOTONIC |
| Mara's eye colour changed (green → grey) | ✅ IMMUTABLE_FACT |
| Mara's birthplace changed (Port Averly → Gull Point) | ✅ IMMUTABLE_FACT |
| Brandt was dead, then "alive and well" | ✅ DEAD_THEN_ALIVE |
| Brandt went from enemy to friend | ❌ the relationships are still not extracted (Failure 3) |

**Still open:**

- **Relationships (Failure 3)** have not changed. The 4 saved relationships are the same as before. One is still
  wrong: "mother PARENT_OF Lily Quinn", where the mother should be Mara. It is now its own "mother" entry
  instead of Mara's mother, so it no longer pollutes Mara's family. Linking role words to the named person is
  fix 3.
- **Speed (Failure 7)** has not changed: fix 4.
- **Worlds that were already extracted** keep their duplicate entries. They only merge when the chapters are
  extracted again.
- **Two people with the same first name** could still be merged when only one of them is saved so far. The
  "exactly one fits" rule limits this but does not rule it out.

## 9. Re-run after the relationship and title fixes (6 October 2026)

**What changed** (fixes 3 and 5 from section 6, all in the extractor):

- **Short names inside a name's cluster are kept.** The coreference model (BookNLP) already knew that "Mara" in
  "Mara's brother" and "Mara's enemy" is Mara Quinn, but the extractor threw those "Mara" mentions away, because
  mention detection had only found the full name. Without a "Mara" mention, the possessive rule had nothing to
  hang "brother" or "enemy" on, so it skipped both sentences. A proper name in a cluster with an already-found
  mention is now kept (`extractor/extractor/coref.py`). This was the main cause of Failure 3.
- **"X's brother, Y" points at Y.** A role word followed (or preceded) by a name, as in "Mara's brother, Tobias
  Quinn", now links to that name instead of creating a new person called "Mara's brother".
- **The LLM's answers are matched without "the" and titles.** The model answered "Doctor Hanna Weiss works for
  the Harbor Council", but the found names are "Hanna Weiss" and "Harbor Council", so the answer was thrown
  away. Names are now compared without a leading "the"/"a" or a title.
- **Titles before a name are saved as facts.** "Doctor Hanna Weiss" → occupation *doctor*; "Captain Elias
  Brandt" → title *Captain*. Also Dr, Professor, Detective, Inspector, General, Sergeant, Lieutenant, Colonel and
  Admiral. Mr, Mrs and Sir are not facts and are ignored.
- **Fewer wrong occupations.** An occupation that starts with a verb ("examined the body") or that is the object
  of a preposition ("brought bread *from the bakery*") is no longer saved. "worked *as* a nurse" still counts.

**How it was run:** the same as section 8: the story through the real extractor and extraction task, on a
scratch SQLite database. The 4 annotated gold stories were also re-scored, to check that nothing got worse.

| Area | 30 Sep | 3 Oct | 6 Oct |
|---|---|---|---|
| Contradictions | 0 of 5 | 4 of 5 | **5 of 5** |
| False alarms | 0 | 0 | 0 |
| Planted relationships | 0 of 5 | 0 of 5 | **4 of 5** |
| Planted facts | 12 of 15 | not measured | **14 of 15** (only "lighthouse keeper" missing) |
| Wrong occupation values | 2 ("examined the body", "bakery") | not measured | **0** |

Relationships found:

| Planted relationship | Result |
|---|---|
| Mara and Tobias are siblings | ✅ Mara SIBLING_OF Tobias Quinn |
| Brandt is Mara's enemy | ✅ Mara ENEMY_OF Elias Brandt |
| Hanna works for the Harbor Council | ✅ Hanna WORKS_FOR Harbor Council |
| Brandt is Mara's friend (ch 4) | ✅ Mara FRIEND_OF Elias Brandt, flagged as a contradiction of "enemy" |
| Mara is Lily's parent | ❌ see below |

**Gold stories (micro F1, before → after):** mentions 0.573 → 0.575, coreference B³ 0.482 → 0.486, coreference
B³ on linked mentions 0.744 → 0.755. Relationships (0.533) and facts (0.609) did not change. Nothing got worse.

**Still open:**

- **"Her daughter, Lily Quinn" (Mara is Lily's parent).** The coreference model links this "Her" to "her mother"
  in the sentence before, not to Mara. With the wrong owner, no rule can recover the relationship. This needs
  better coreference, not another rule.
- **Role words without a name.** "her uncle" (Lily's uncle, ch 3) and "her mother" (ch 1 and ch 3) are still
  saved as unnamed "uncle"/"mother" entries. "mother PARENT_OF Lily" (ch 3) is still wrong: it should be Mara.
- **"Mara is a lighthouse keeper"** ("had kept the lighthouse") is still missed: the LLM doesn't read a job from
  a verb.
- **A title is saved again in every chapter that uses it.** "Captain" for Brandt has 3 active versions with the
  same value, one per chapter. This is how the backend already stores a repeated value; it's harmless but untidy.
- **Speed (Failure 7)** is deferred: correctness comes first for now.

## 10. Re-run after the timeline fixes (6 October 2026)

**What changed** (Failure 6):

- **Stated deaths are events.** "Elias Brandt was dead." is now a DEATH event with Brandt as the one who died.
  The extractor only looked at verbs before, and "was dead" has none. "was not dead" creates no event. "drowned"
  and "perished" are also counted as deaths.
- **Every participant has a role.** The extractor already knew who did what (agent), to whom (patient,
  recipient) and where (location), but only the names reached the database, so everyone was saved as a
  "PARTICIPANT" and places looked like people. The role is now saved, and the timeline API already returns it.
- **People after "to", "at" and so on are not places.** "she said later *to Hanna*" makes Hanna the recipient.
  "stared *at me*" makes the speaker a participant. Following the gold annotations, the goal of a movement
  ("rushed over *to him*") stays a location, and so does an organization ("into *the radio station*").
- **Lists of people.** "*Mara, Tobias and Lily* climbed the tower" lists all three, not just Mara.
- **"Mara said nothing."** is no longer a CONVERSATION.

| Timeline check | 30 Sep | 6 Oct |
|---|---|---|
| Brandt's death recorded | ❌ | ✅ DEATH [Elias Brandt: patient] |
| "Mara travelled to Port Averly" | Port Averly listed as a person | ✅ Port Averly: location |
| "she said later to Hanna" | — | ✅ Hanna: recipient |
| "Mara, Tobias and Lily climbed" | Mara only | ✅ all three |
| "Mara said nothing." | CONVERSATION | ✅ not an event |
| Events with nobody attached | 5 of 15 | 3 of 15 |

The 3 events with nobody attached are "The letter said ...", "His ship broke apart ..." and "the men from the
harbor found his body". None of them has a named person, so leaving them empty is correct.

**Gold stories:** no change (event triggers 0.243, event arguments 0.022, entity-level arguments 0.142). A first
version made "rushed over to him" a recipient and lost one gold match, which is how the movement rule was found.

**Still open:**

- **"a stranger walked into the tavern"** (ch 4) is Brandt, but the text only says so in the next sentence, so
  the event lists only Gull Point.
- **"Hanna visited them"**: "them" (Lily and Tobias) is a plural pronoun, which coreference doesn't resolve.
- **"The letter said ..."** is still a CONVERSATION. A letter saying something is reported speech, which is
  debatable but harmless.
