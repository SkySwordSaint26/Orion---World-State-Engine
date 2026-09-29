"""
Phase 5 — relationships and facts with NuExtract 2.0 4B (a Qwen2.5-VL model tuned for extraction; setup in
requirements.txt). Chosen on the 4 gold stories over qwen2.5:7b, Qwen3.5 4B and GLiNER2 spans: by far the most precise
facts (docs/wse_extraction_plan.md, Phase 5).

Per chunk, two calls, since one combined template made it return nothing:
    people         name + every fact property, all `verbatim-string` (copied from the text)
    relationships  subject and object verbatim, relation from the gold predicates
Code grounds every answer and drops what fails:
    - a name must be the text of a character or organization mention in the chunk
    - a value must occur in the chunk (the source's exact characters are kept) and be at most MAX_VALUE_CHARS long
    - no self-relationships; duplicates (same entities, predicate / property, value) are kept once, a relationship in
      its canonical form (`canonical`: "B FRIEND_OF A" repeats "A FRIEND_OF B")
The mention recorded for an entity is a named mention in its sentence, else the entity's first proper, then nominal
mention: facts and relationships are about the entity, and the gold names it ("Evelyn", not "I").
"""
import json
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from app.contracts.gold import FACT_PROPERTIES, PREDICATES
from app.preprocessing import chunk_document, preprocess_chapter
from wse.llm import generate

CHUNK_CHARS = 2000
MAX_VALUE_CHARS = 40
TYPES = ("character", "organization")       # the entities facts and relationships are about
SYSTEM = "You are NuExtract, an information extraction tool created by NuMind."
PEOPLE = {"people": [{"name": "verbatim-string", **{p: "verbatim-string" for p in FACT_PROPERTIES}}]}
SYMMETRIC = {"FRIEND_OF", "ENEMY_OF", "SIBLING_OF", "MARRIED_TO", "ALLY_OF", "KNOWS", "RELATED_TO"}
INVERSE = {"CHILD_OF": "PARENT_OF"}          # "A CHILD_OF B" is "B PARENT_OF A"
RELATIONSHIPS = {"relationships": [{"subject": "verbatim-string", "relation": [p.lower() for p in PREDICATES],
                                    "object": "verbatim-string"}]}


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


def _first(ms: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    return next((m for m in ms if m["mention_kind"] == kind), None)


def representative(ms: List[Dict[str, Any]], sentence: Any) -> Dict[str, Any]:
    here = [m for m in ms if sentence.start <= m["start"] < sentence.end]
    return (_first(here, "proper") or _first(here, "nominal") or _first(ms, "proper") or _first(ms, "nominal")
            or (here or ms)[0])


def ask(template: Dict[str, Any], text: str) -> Dict[str, Any]:
    return generate(SYSTEM, f"# Template:\n{json.dumps(template, indent=4)}\n{text}", "json")


def relations(doc: Dict[str, Any]) -> None:
    document = preprocess_chapter(doc["text"])
    sentences = list(document.iter_sentences())
    groups = entities(doc)
    group_of = {m["mention_id"]: key for key, ms in groups.items() for m in ms}
    kind_of = {key: Counter(m["type"] for m in ms).most_common(1)[0][0] for key, ms in groups.items()}
    seen = set()

    def record(m: Dict[str, Any]) -> str:
        sentence = next(s for s in sentences if s.start <= m["start"] < s.end)
        return representative(groups[group_of[m["mention_id"]]], sentence)["mention_id"]

    for chunk in chunk_document(document, max_chars=CHUNK_CHARS, overlap_sentences=0):
        names: Dict[str, Dict[str, Any]] = {}                       # casefolded text -> first matching mention
        for m in doc["mentions"]:
            if chunk.start <= m["start"] < chunk.end and kind_of[group_of[m["mention_id"]]] in TYPES:
                names.setdefault(m["text"].casefold(), m)
        if not names:
            continue
        find = lambda name: names.get(name.strip().casefold()) if isinstance(name, str) else None

        for person in ask(PEOPLE, chunk.text).get("people") or []:
            m = find(person.get("name"))
            for prop in FACT_PROPERTIES if m else ():
                value = person.get(prop).strip() if isinstance(person.get(prop), str) else ""
                at = chunk.text.casefold().find(value.casefold()) if value else -1
                key = ("F", group_of[m["mention_id"]], prop, value.casefold())
                if at >= 0 and len(value) <= MAX_VALUE_CHARS and key not in seen:
                    seen.add(key)
                    doc["facts"].append({"fact_id": f"F{len(doc['facts']) + 1}", "property": prop,
                                         "entity_mention_id": record(m), "value": chunk.text[at:at + len(value)]})

        for r in ask(RELATIONSHIPS, chunk.text).get("relationships") or []:
            a, b = find(r.get("subject")), find(r.get("object"))
            predicate = r.get("relation").upper() if isinstance(r.get("relation"), str) else ""
            if not (a and b and predicate in PREDICATES) or group_of[a["mention_id"]] == group_of[b["mention_id"]]:
                continue
            key = ("R", *canonical(group_of[a["mention_id"]], predicate, group_of[b["mention_id"]]))
            if key not in seen:
                seen.add(key)
                doc["relationships"].append({"relationship_id": f"R{len(doc['relationships']) + 1}",
                                             "predicate": predicate, "subject_mention_id": record(a),
                                             "object_mention_id": record(b)})
