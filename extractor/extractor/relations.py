"""
Phase 5 — relationships and facts with NuExtract 2.0 4B (a Qwen2.5-VL model tuned for extraction; setup in
requirements.txt). Chosen on the 4 gold stories over qwen2.5:7b, Qwen3.5 4B and GLiNER2 spans: by far the most precise
facts (docs/wse_extraction_plan.md, Phase 5).

First, without the LLM, possessive role nouns ("my boss", "Dan’s mother") give relationships (`role_pairs`), and
titles before a name ("Doctor Hanna Weiss") give facts (`title_facts`).
Then per chunk, two NuExtract calls in its own prompt layout (template, one made-up worked example, context), since
one combined template made it return nothing:
    people         name + every fact property, all `verbatim-string` (copied from the text)
    relationships  subject and object verbatim, relation from the gold predicates, and an evidence quote
Code grounds every answer and drops what fails:
    - a relationship's evidence must be in the chunk, name both ends and contain a cue word for the relation (`CUES`)
    - a name must be the text of a character or organization mention in the chunk (any case, without "the" or a title)
    - a value must occur in the chunk (the source's exact characters are kept) and be at most MAX_VALUE_CHARS long
    - no self-relationships; duplicates (same entities, predicate / property, value) are kept once, a relationship in
      its canonical form (`canonical`: "B FRIEND_OF A" repeats "A FRIEND_OF B")
The mention recorded for an entity is a named mention in its sentence, else the entity's first proper, then nominal
mention: facts and relationships are about the entity, and the gold names it ("Evelyn", not "I").
"""
import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from app.contracts.gold import FACT_PROPERTIES, PREDICATES
from app.contracts.normalization import normalize_entity_name
from app.preprocessing import chunk_document, preprocess_chapter
from extractor.llm import generate
from extractor.mentions import spacy_nlp

CHUNK_CHARS = 2000
MAX_VALUE_CHARS = 40
TYPES = ("character", "organization")       # the entities facts and relationships are about
SYSTEM = "You are NuExtract, an information extraction tool created by NuMind."
PEOPLE = {"people": [{"name": "verbatim-string", **{p: "verbatim-string" for p in FACT_PROPERTIES}}]}
SYMMETRIC = {"FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "MARRIED_TO", "ALLY_OF", "KNOWS", "RELATED_TO"}
INVERSE = {"CHILD_OF": "PARENT_OF"}          # "A CHILD_OF B" is "B PARENT_OF A"
RELATIONSHIPS = {"relationships": [{"subject": "verbatim-string", "relation": [p.lower() for p in PREDICATES],
                                    "object": "verbatim-string", "evidence": "verbatim-string"}]}
# Possessive role nouns state a relationship outright ("my boss", "Dan's mother", "Tom is her brother"), and NuExtract
# misses them: noun -> (predicate, True when the possessor is the subject).
_roles = lambda predicate, owner_first, *lemmas: {w: (predicate, owner_first) for w in lemmas}
ROLES = {**_roles("WORKS_FOR", True, "boss", "employer", "manager", "supervisor"),
         **_roles("WORKS_FOR", False, "employee", "assistant", "apprentice"),
         **_roles("PARENT_OF", False, "mother", "mom", "mum", "father", "dad", "parent"),
         **_roles("PARENT_OF", True, "son", "daughter", "child", "kid"),
         **_roles("SIBLING_OF", True, "brother", "sister", "sibling"),
         **_roles("MARRIED_TO", True, "wife", "husband", "spouse"),
         **_roles("FRIEND_OF", True, "friend", "buddy"),
         **_roles("ENEMY_OF", True, "enemy", "nemesis", "rival"),
         **_roles("RELATED_TO", True, "cousin", "aunt", "uncle", "niece", "nephew")}
IMPERSONAL = {"it", "this", "that", "there", "who", "which"}      # "It was my boss": the subject isn't the boss
# A title written before a name states a fact ("Doctor Hanna Weiss", "Captain Elias Brandt"), and NuExtract misses it.
# Honorifics (Mr, Mrs, Sir) say nothing: left out. ponytail: English titles only, extend the map for other stories
TITLE_FACTS = {"doctor": ("occupation", "doctor"), "dr": ("occupation", "doctor"),
               "professor": ("occupation", "professor"), "prof": ("occupation", "professor"),
               "detective": ("occupation", "detective"), "inspector": ("occupation", "inspector"),
               "capt": ("title", "Captain"),
               **{w: ("title", w.capitalize()) for w in ("captain", "general", "sergeant", "lieutenant", "colonel",
                                                          "admiral")}}
# Fact value checks (`fact_value`), from NuExtract's wrong answers on the gold stories (Phase 9 in the plan).
COLORS = {"black", "brown", "dark", "blond", "blonde", "red", "auburn", "ginger", "grey", "gray", "white", "silver",
          "golden", "gold", "fair", "light", "pale", "chestnut", "copper", "green", "blue", "hazel", "amber", "violet",
          "pink", "purple", "orange", "yellow", "raven", "jet"}
JOB_NOUNS = {"position", "job", "role", "career", "post", "gig"}   # "a radio DJ position": the modifier is the job
NOT_OCCUPATIONS = ({w for w, (predicate, _) in ROLES.items() if predicate != "WORKS_FOR"}
                   | {"coworker", "co-worker", "colleague", "partner", "neighbor", "neighbour", "roommate"})
UNCHECKED = {"age", "date_of_birth", "status"}                    # numbers, dates, free states: length check only
# A relationship is kept only if its evidence has a word that states it: NuExtract asserts FRIEND_OF, ALLY_OF and
# MARRIED_TO between any two people in a sentence (Phase 9 in the plan). Stems, matched at a word start.
# ponytail: keyword cues miss implied relations; a verifier model is the upgrade if recall matters more than precision
CUES = {
    "FRIEND_OF": ("friend", "buddy", "pal"), "ENEMY_OF": ("enem", "rival", "nemes", "hate"),
    "SIBLING_OF": ("brother", "sister", "sibling", "twin"),
    "PARENT_OF": ("mother", "father", "mom", "dad", "parent", "son", "daughter", "child"),
    "MARRIED_TO": ("married", "marry", "wife", "husband", "spouse", "wedding"),
    "ALLY_OF": ("ally", "allie", "alliance", "side with", "team"),
    "WORKS_FOR": ("boss", "employ", "work", "job", "hire", "part-timer", "coworker", "manager", "owner"),
    "MEMBER_OF": ("member", "joined", "belong"), "OWNS": ("own",),
    "KNOWS": ("know", "knew", "met ", "meet", "friend", "recogni"),
    "RELATED_TO": ("related", "cousin", "aunt", "uncle", "niece", "nephew", "grand", "family", "relative"),
}
CUES["CHILD_OF"] = CUES["PARENT_OF"]
FIRST_PERSON = ("i", "me", "my", "myself", "we", "us", "our")      # the narrator, alone or in a group
# One made-up worked example per template (NuExtract's "# Examples" section), never text from the gold stories.
EXAMPLE = ("Marta Lindqvist, a thirty-year-old nurse with short red hair, was still recovering from the crash when "
           "her brother Tomas drove her back to the farmhouse. \u2018Tomas will be your new farmhand,\u2019 old Mr. Hale "
           "told me. I nodded; I had known Marta since school, and I was the only vet in town.")
_person = lambda **kv: {"name": None, **{p: None for p in FACT_PROPERTIES}, **kv}
EXAMPLES = {
    "people": {"people": [_person(name="Marta Lindqvist", age="thirty", occupation="nurse", hair_color="red",
                                  status="recovering", location="the farmhouse"),
                          _person(name="Tomas", occupation="farmhand"), _person(name="I", occupation="vet")]},
    "relationships": {"relationships": [
        {"subject": "Tomas", "relation": "sibling_of", "object": "Marta Lindqvist",
         "evidence": EXAMPLE[:EXAMPLE.index(".") + 1]},
        {"subject": "Tomas", "relation": "works_for", "object": "Mr. Hale",
         "evidence": "\u2018Tomas will be your new farmhand,\u2019 old Mr. Hale told me."},
        {"subject": "I", "relation": "knows", "object": "Marta", "evidence": "I had known Marta since school"}]},
}


def canonical(subject: Any, predicate: str, obj: Any) -> Tuple[Any, str, Any]:
    """One form per relation: inverse predicates flipped, the two ends of a symmetric one in a fixed order."""
    if predicate in INVERSE:
        subject, predicate, obj = obj, INVERSE[predicate], subject
    if predicate in SYMMETRIC and str(obj) < str(subject):
        subject, obj = obj, subject
    return subject, predicate, obj


def entities(doc: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Entity key -> its mentions: one per coreference cluster, plus one per unclustered mention."""
    by_id = {m["mention_id"]: m for m in doc["mentions"]}
    groups = {c["cluster_id"]: [by_id[x] for x in c["mentions"]] for c in doc["coreference_clusters"]}
    clustered = {x for c in doc["coreference_clusters"] for x in c["mentions"]}
    groups.update({m["mention_id"]: [m] for m in doc["mentions"] if m["mention_id"] not in clustered})
    return groups


def name_key(name: str) -> str:
    """How an answer's name is matched to a mention's text: any case, without a leading article or title (NuExtract
    answers "the Harbor Council" and "Doctor Hanna Weiss" where the mentions are "Harbor Council", "Hanna Weiss")."""
    return normalize_entity_name(re.sub(r"^(?:the|a|an)\s+", "", name.strip(), flags=re.IGNORECASE)).casefold()


def _first(ms: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    return next((m for m in ms if m["mention_kind"] == kind), None)


def representative(ms: List[Dict[str, Any]], sentence: Any) -> Dict[str, Any]:
    here = [m for m in ms if sentence.start <= m["start"] < sentence.end]
    return (_first(here, "proper") or _first(here, "nominal") or _first(ms, "proper") or _first(ms, "nominal")
            or (here or ms)[0])


def _named(name: str, evidence: str) -> bool:
    words = FIRST_PERSON if name.strip().casefold() in FIRST_PERSON else (name.strip(),)
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", evidence, re.IGNORECASE) for w in words)


def stated(evidence: Any, text: str, predicate: str, *names: str) -> bool:
    """The evidence is a quote from the text that names every one of `names` (whole words, any case; a first-person
    pronoun stands for all of them) and has a cue word for the predicate."""
    if not (isinstance(evidence, str) and evidence.strip() and evidence.strip().casefold() in text.casefold()):
        return False
    cue = any(re.search(rf"(?<!\w){re.escape(c)}", evidence, re.IGNORECASE) for c in CUES[predicate])
    return cue and all(_named(n, evidence) for n in names)


def ask(template: Dict[str, Any], text: str) -> Dict[str, Any]:
    """NuExtract's own prompt layout (the chat template shipped in its GGUF): template, examples, context."""
    example = EXAMPLES.get(next(iter(template)))
    shots = (f"# Examples:\n## Input:\n{EXAMPLE}\n## Output:\n{json.dumps(example, ensure_ascii=False)}\n"
             if example else "")
    return generate(SYSTEM, f"# Template:\n{json.dumps(template, indent=4)}\n{shots}# Context:\n{text}", "json")


def fact_value(prop: str, span: Any) -> Optional[str]:
    """The value to record for a fact, or None to drop it. `span` is the value's occurrence in spaCy's parse.
    - colors are trimmed to their color words ("moppy dark" -> "dark"); none, no fact ("human" eyes)
    - other properties except UNCHECKED: no digits ("104.6 F.M."), and not cut from a longer noun phrase: the last
      word must not only modify a noun after the value ("weather" of "weather forecast"), except a job noun
    - an occupation isn't a relationship word ("coworker"), a verb ("announcing"), an action ("examined the body") or
      a preposition's object other than "as" ("bread from the bakery"; "worked as a nurse" is kept)"""
    if prop in ("hair_color", "eye_color"):
        words = [t for t in span if t.lower_ in COLORS]
        return span.doc.text[words[0].idx:words[-1].idx + len(words[-1])] if words else None
    if prop in UNCHECKED:
        return span.text
    last = span[-1]
    if any(c.isdigit() for c in span.text) or (last.dep_ == "compound" and last.head.i >= span.end
                                                and last.head.lower_ not in JOB_NOUNS):
        return None
    if prop == "occupation" and (last.lower_ in NOT_OCCUPATIONS or last.tag_ == "VBG" or span[0].tag_.startswith("VB")
                                 or (span.root.dep_ == "pobj" and span.root.head.lower_ != "as")):
        return None
    return span.text


def role_pairs(doc: Dict[str, Any], parsed: Any) -> List[Tuple[str, str, str]]:
    """(subject, predicate, object) mention ids from possessive role nouns (ROLES). The role's holder is the subject
    of "X is my brother", else the name in apposition ("my brother, X"), else the smallest mention of the noun without
    its possessor; with none, the noun gets a new character mention ("Dan’s mother": mention detection misses these),
    clustered by (noun, possessor's entity): "Dan’s mother" ... "his mother" is one person."""
    ms = doc["mentions"]
    cluster_of = {m: c["cluster_id"] for c in doc["coreference_clusters"] for m in c["mentions"]}
    next_id = lambda items, key: max((int(i[key][1:]) for i in items), default=0) + 1

    def smallest(tok: Any, without: Any = None) -> Optional[Dict[str, Any]]:
        a, b = tok.idx, tok.idx + len(tok)
        inside = [m for m in ms if m["start"] <= a and b <= m["end"]
                  and not (without is not None and m["start"] <= without.idx < m["end"])]
        return min(inside, key=lambda m: m["end"] - m["start"], default=None)

    out, created = [], {}
    for t in parsed:
        word = t.lower_[:-1] if t.tag_ == "NNS" and t.lower_.endswith("s") else t.lower_   # spacy_nlp has no lemmas
        role = ROLES.get(word)
        poss = next((c for c in t.children if c.dep_ == "poss"), None)
        owner = smallest(poss) if role and poss is not None else None
        if owner is None:
            continue
        subject = next((c for c in t.head.children if c.dep_ == "nsubj"), None) if t.dep_ == "attr" else None
        holder = smallest(subject) if subject is not None and subject.lower_ not in IMPERSONAL else None
        # the name in apposition: "Mara's brother, Tobias Quinn" / "Tobias Quinn, Mara's brother"
        appos = next((c for c in t.children if c.dep_ == "appos"), t.head if t.dep_ == "appos" else None)
        holder = holder or (smallest(appos) if appos is not None else None) or smallest(t, without=poss)
        if holder is None:
            start = poss.idx if poss.pos_ == "PROPN" else t.idx
            holder = {"mention_id": f"M{next_id(ms, 'mention_id')}", "text": doc["text"][start:t.idx + len(t)],
                      "type": "character", "mention_kind": "nominal", "start": start, "end": t.idx + len(t)}
            ms.append(holder)
            created.setdefault((word, cluster_of.get(owner["mention_id"], owner["mention_id"])), []).append(
                holder["mention_id"])
        predicate, owner_first = role
        a, b = (owner, holder) if owner_first else (holder, owner)
        out.append((a["mention_id"], predicate, b["mention_id"]))
    for ids in created.values():
        if len(ids) > 1:
            doc["coreference_clusters"].append(
                {"cluster_id": f"C{next_id(doc['coreference_clusters'], 'cluster_id')}", "mentions": ids})
    return out


def title_facts(doc: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(mention id, property, value) for a TITLE_FACTS title just before a character's name ("Doctor Hanna Weiss")
    or at the start of a mention that has one ("Captain Elias Brandt")."""
    out = []
    for m in doc["mentions"]:
        if m["type"] != "character" or m["mention_kind"] != "proper":
            continue
        first = m["text"].split()[0].rstrip(".")
        before = re.search(r"\b([A-Z][a-z]+)\.?\s+$", doc["text"][max(0, m["start"] - 20):m["start"]])
        word = first if first.lower() in TITLE_FACTS and first != m["text"] else before.group(1) if before else ""
        if word.lower() in TITLE_FACTS:
            out.append((m["mention_id"], *TITLE_FACTS[word.lower()]))
    return out


def relations(doc: Dict[str, Any]) -> None:
    parsed = spacy_nlp()(doc["text"])
    pairs = role_pairs(doc, parsed)
    document = preprocess_chapter(doc["text"])
    sentences = list(document.iter_sentences())
    groups = entities(doc)
    group_of = {m["mention_id"]: key for key, ms in groups.items() for m in ms}
    kind_of = {key: Counter(m["type"] for m in ms).most_common(1)[0][0] for key, ms in groups.items()}
    seen = set()

    def record(m: Dict[str, Any]) -> str:
        sentence = next(s for s in sentences if s.start <= m["start"] < s.end)
        return representative(groups[group_of[m["mention_id"]]], sentence)["mention_id"]

    def relate(a: Dict[str, Any], predicate: str, b: Dict[str, Any]) -> None:
        ga, gb = group_of[a["mention_id"]], group_of[b["mention_id"]]
        key = ("R", *canonical(ga, predicate, gb))
        if ga != gb and kind_of[ga] in TYPES and kind_of[gb] in TYPES and key not in seen:
            seen.add(key)
            doc["relationships"].append({"relationship_id": f"R{len(doc['relationships']) + 1}",
                                         "predicate": predicate, "subject_mention_id": record(a),
                                         "object_mention_id": record(b)})

    def fact(m: Dict[str, Any], prop: str, value: str) -> None:
        key = ("F", group_of[m["mention_id"]], prop, value.casefold())
        if key not in seen:
            seen.add(key)
            doc["facts"].append({"fact_id": f"F{len(doc['facts']) + 1}", "property": prop,
                                 "entity_mention_id": record(m), "value": value})

    by_id = {m["mention_id"]: m for m in doc["mentions"]}
    for a, predicate, b in pairs:
        relate(by_id[a], predicate, by_id[b])
    for mid, prop, value in title_facts(doc):          # before the LLM's facts: the backend keeps a chapter's first
        fact(by_id[mid], prop, value)

    for chunk in chunk_document(document, max_chars=CHUNK_CHARS, overlap_sentences=0):
        names: Dict[str, Dict[str, Any]] = {}                       # name_key(text) -> first matching mention
        for m in doc["mentions"]:
            if chunk.start <= m["start"] < chunk.end and kind_of[group_of[m["mention_id"]]] in TYPES:
                names.setdefault(name_key(m["text"]), m)
        if not names:
            continue
        find = lambda name: names.get(name_key(name)) if isinstance(name, str) else None

        for person in ask(PEOPLE, chunk.text).get("people") or []:
            m = find(person.get("name"))
            for prop in FACT_PROPERTIES if m else ():
                value = person.get(prop).strip() if isinstance(person.get(prop), str) else ""
                at = chunk.text.casefold().find(value.casefold()) if value else -1
                if at < 0 or len(value) > MAX_VALUE_CHARS:
                    continue
                span = parsed.char_span(chunk.start + at, chunk.start + at + len(value), alignment_mode="expand")
                value = fact_value(prop, span)
                if value:
                    fact(m, prop, value)

        for r in ask(RELATIONSHIPS, chunk.text).get("relationships") or []:
            a, b = find(r.get("subject")), find(r.get("object"))
            predicate = r.get("relation").upper() if isinstance(r.get("relation"), str) else ""
            if a and b and predicate in PREDICATES and stated(r.get("evidence"), chunk.text, predicate,
                                                              r["subject"], r["object"]):
                relate(a, predicate, b)
