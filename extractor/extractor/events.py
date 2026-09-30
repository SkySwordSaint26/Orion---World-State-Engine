"""
Phase 4 — events, deterministic (no LLM; see docs/wse_extraction_plan.md, Phase 4 for why). From BookNLP's token output,
already computed by the coreference stage:
    trigger       a token BookNLP marks as a realis EVENT and tags as a VERB (its event nouns: "fog", "sound", ...
                  are mostly not events)
    type          a general English verb lexicon over the lemma; OTHER otherwise (the gold's most common type)
    participants  from the dependency parse: subject -> agent (passive subject -> patient; a conjoined verb shares
                  the subject of its head), direct object -> patient, dative -> recipient, object of a place
                  preposition -> location. Each dependent maps to the smallest mention containing it.
"""
from typing import Any, Dict, List, Optional, Tuple

from app.contracts.gold import EVENT_TYPES
from extractor.coref import booknlp_output

LEXICON = {
    "CONVERSATION": "say tell ask answer reply respond speak talk call shout yell scream whisper mumble mutter croak "
                    "chat ring announce explain",
    "TRAVEL": "walk drive travel ride wander climb cross hike",
    "ARRIVAL": "arrive reach enter",
    "DEPARTURE": "leave depart exit",
    "MEETING": "meet greet visit",
    "DISCOVERY": "find discover notice realize spot",
    "ATTACK": "attack hit strike stab shoot punch slap kick",
    "DEATH": "die",
    "CONFLICT": "fight argue struggle",
    "CREATION": "build create",
    "DESTRUCTION": "destroy break smash shatter demolish",
}
TYPE_OF = {lemma: etype for etype, lemmas in LEXICON.items() for lemma in lemmas.split()}
assert set(LEXICON) <= set(EVENT_TYPES)
PLACE_PREPOSITIONS = {"in", "into", "on", "onto", "at", "through", "to", "from", "out", "inside", "across", "along",
                      "up", "down", "under", "over", "toward", "towards", "behind", "near"}
POSSESSIVES = {"my", "your", "his", "her", "its", "our", "their"}   # determiners, never participants


def children(tokens: List[Dict[str, str]]) -> Dict[int, List[int]]:
    """Token index -> indices of its dependents in BookNLP's parse."""
    out: Dict[int, List[int]] = {}
    for j, t in enumerate(tokens):
        out.setdefault(int(t["syntactic_head_ID"]), []).append(j)
    return out


def participants(i: int, tokens: List[Dict[str, str]], children: Dict[int, List[int]],
                 mention_at) -> List[Tuple[str, str]]:
    rel = lambda j: tokens[j]["dependency_relation"]
    subjects = [j for j in children.get(i, []) if rel(j) in ("nsubj", "nsubjpass")]
    if not subjects and rel(i) == "conj":                    # "I ran to the desk and picked it up"
        subjects = [j for j in children.get(int(tokens[i]["syntactic_head_ID"]), []) if rel(j) == "nsubj"]
    found = [("patient" if rel(j) == "nsubjpass" else "agent", j) for j in subjects]
    for j in children.get(i, []):
        if rel(j) == "dobj":
            found.append(("patient", j))
        elif rel(j) == "dative":
            found.append(("recipient", j))
        elif rel(j) == "prep" and tokens[j]["lemma"].lower() in PLACE_PREPOSITIONS:
            found += [("location", k) for k in children.get(j, []) if rel(k) == "pobj"]
    return list(dict.fromkeys((role, m) for role, j in found if (m := mention_at(j))))


def events(doc: Dict[str, Any]) -> None:
    tokens, _ = booknlp_output(doc["text"])
    kids = children(tokens)
    candidates = [m for m in doc["mentions"] if m["text"].lower() not in POSSESSIVES]

    def mention_at(j: int) -> Optional[str]:
        a, b = int(tokens[j]["byte_onset"]), int(tokens[j]["byte_offset"])
        inside = [m for m in candidates if m["start"] <= a and b <= m["end"]]
        return min(inside, key=lambda m: m["end"] - m["start"])["mention_id"] if inside else None

    for i, t in enumerate(tokens):
        if t["event"] != "EVENT" or t["POS_tag"] != "VERB":
            continue
        doc["events"].append({"event_id": f"E{len(doc['events']) + 1}", "type": TYPE_OF.get(t["lemma"].lower(), "OTHER"),
                              "trigger": t["word"], "start": int(t["byte_onset"]), "end": int(t["byte_offset"]),
                              "participants": [{"role": r, "mention_id": m}
                                               for r, m in participants(i, tokens, kids, mention_at)]})
