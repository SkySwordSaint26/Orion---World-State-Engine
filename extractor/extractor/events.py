"""
Phase 4 — events, deterministic (no LLM; see docs/wse_extraction_plan.md, Phase 4 for why). From BookNLP's token output,
already computed by the coreference stage:
    trigger       a token BookNLP marks as a realis EVENT and tags as a VERB (its event nouns: "fog", "sound", ...
                  are mostly not events)
    type          a general English verb lexicon over the lemma; OTHER otherwise (the gold's most common type)
    participants  from the dependency parse: subject -> agent (passive subject -> patient; a conjoined verb shares
                  the subject of its head; "Mara, Tobias and Lily" are all subjects), direct object -> patient,
                  dative -> recipient, object of a place preposition -> location, except a character after
                  a speech verb ("said to Hanna": recipient) or after another preposition than "to" ("stared at
                  me": participant). The goal of a movement stays a location, as in the gold ("rushed over to
                  him"), and so does an organization ("into the radio station"). Each dependent maps to the
                  smallest mention containing it.
Also a DEATH event for a stated death, "X was dead" (no verb event: BookNLP marks verbs), with X as patient; and
"said nothing" is no CONVERSATION.

Experiment (off by default): `llm_types` re-types the triggers with a bigger LLM than the local GPU holds (Phase 7
retest; extractor/notebooks/kaggle_event_typing.ipynb). ORION_EVENT_LLM names the Ollama model, ORION_EVENT_LLM_MODE
is "all" (every trigger) or "other" (only the triggers the lexicon left OTHER). It runs as its own stage after the
encoders are freed; triggers and participants stay as above.
"""
import os
from typing import Any, Dict, List, Optional, Tuple

from app.contracts.gold import EVENT_TYPES
from app.preprocessing import preprocess_chapter
from extractor.coref import booknlp_output
from extractor.llm import generate

LEXICON = {
    "CONVERSATION": "say tell ask answer reply respond speak talk call shout yell scream whisper mumble mutter croak "
                    "chat ring announce explain",
    "TRAVEL": "walk drive travel ride wander climb cross hike",
    "ARRIVAL": "arrive reach enter",
    "DEPARTURE": "leave depart exit",
    "MEETING": "meet greet visit",
    "DISCOVERY": "find discover notice realize spot",
    "ATTACK": "attack hit strike stab shoot punch slap kick",
    "DEATH": "die drown perish",
    "CONFLICT": "fight argue struggle",
    "CREATION": "build create",
    "DESTRUCTION": "destroy break smash shatter demolish",
}
TYPE_OF = {lemma: etype for etype, lemmas in LEXICON.items() for lemma in lemmas.split()}
assert set(LEXICON) <= set(EVENT_TYPES)
PLACE_PREPOSITIONS = {"in", "into", "on", "onto", "at", "through", "to", "from", "out", "inside", "across", "along",
                      "up", "down", "under", "over", "toward", "towards", "behind", "near"}
POSSESSIVES = {"my", "your", "his", "her", "its", "our", "their"}   # determiners, never participants
DEAD = {"dead", "deceased"}


def children(tokens: List[Dict[str, str]]) -> Dict[int, List[int]]:
    """Token index -> indices of its dependents in BookNLP's parse."""
    out: Dict[int, List[int]] = {}
    for j, t in enumerate(tokens):
        out.setdefault(int(t["syntactic_head_ID"]), []).append(j)
    return out


def participants(i: int, tokens: List[Dict[str, str]], children: Dict[int, List[int]],
                 mention_at, type_of, speech: bool = False) -> List[Tuple[str, str]]:
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
    for role, j in list(found):                             # "Mara, Tobias and Lily": every conjunct, chained
        stack = [j]
        while stack:
            conj = [k for k in children.get(stack.pop(), []) if rel(k) == "conj"]
            found += [(role, k) for k in conj]
            stack += conj
    out = []
    for role, j in found:
        m = mention_at(j)
        if m and role == "location" and type_of[m] == "character":
            to = tokens[int(tokens[j]["syntactic_head_ID"])]["lemma"].lower() == "to"
            role = "recipient" if to and speech else "location" if to else "participant"
        if m:
            out.append((role, m))
    return list(dict.fromkeys(out))


def events(doc: Dict[str, Any]) -> None:
    tokens, _ = booknlp_output(doc["text"])
    kids = children(tokens)
    candidates = [m for m in doc["mentions"] if m["text"].lower() not in POSSESSIVES]

    def mention_at(j: int) -> Optional[str]:
        a, b = int(tokens[j]["byte_onset"]), int(tokens[j]["byte_offset"])
        inside = [m for m in candidates if m["start"] <= a and b <= m["end"]]
        return min(inside, key=lambda m: m["end"] - m["start"])["mention_id"] if inside else None

    type_of = {m["mention_id"]: m["type"] for m in doc["mentions"]}
    rel = lambda j: tokens[j]["dependency_relation"]
    for i, t in enumerate(tokens):
        lemma = t["lemma"].lower()
        if t["event"] == "EVENT" and t["POS_tag"] == "VERB":
            etype = TYPE_OF.get(lemma, "OTHER")
            if etype == "CONVERSATION" and any(tokens[j]["lemma"].lower() == "nothing" and rel(j) == "dobj"
                                               for j in kids.get(i, [])):
                etype = "OTHER"                                  # "Mara said nothing."
            people = participants(i, tokens, kids, mention_at, type_of, speech=TYPE_OF.get(lemma) == "CONVERSATION")
        elif lemma in DEAD and rel(i) == "acomp":                # "Elias Brandt was dead."
            head = int(t["syntactic_head_ID"])
            if any(rel(j) == "neg" for j in kids.get(head, [])):
                continue
            etype = "DEATH"
            people = [("patient", m) for j in kids.get(head, []) if rel(j) == "nsubj" and (m := mention_at(j))]
        else:
            continue
        doc["events"].append({"event_id": f"E{len(doc['events']) + 1}", "type": etype,
                              "trigger": t["word"], "start": int(t["byte_onset"]), "end": int(t["byte_offset"]),
                              "participants": [{"role": r, "mention_id": m} for r, m in people]})


EVENT_LLM = os.environ.get("ORION_EVENT_LLM", "")
EVENT_LLM_MODE = os.environ.get("ORION_EVENT_LLM_MODE", "all")
TYPING_SYSTEM = """You label the events of a story. Each marked word [T1 word] in the sentence is an event trigger.
Give every trigger exactly one type, judged by what that word means in this sentence:
ARRIVAL: someone comes to or reaches a place (arrive, come back, enter, join)
DEPARTURE: someone leaves a place (leave, go out, run off, back away)
TRAVEL: someone moves through or between places (walk, drive, climb, wander, rush)
MEETING: people come together (meet, visit, greet)
CONVERSATION: speaking or communicating (say, ask, tell, reply, whisper, call, phone, hang up)
DISCOVERY: someone perceives or finds out something (see, hear, find, notice, realize, recognize)
ATTACK: a violent act against someone (hit, stab, shoot, punch)
DEATH: someone dies or is killed
CONFLICT: an argument, fight or hostility between people
CREATION: something is made or comes into being (build, write, grow)
DESTRUCTION: something is destroyed or removed (break, burn, smash)
OTHER: everything else. Most events are OTHER: thoughts, feelings, states and everyday actions (sit, look, open,
wait, start, lose, play)."""


def marked(text: str, triggers: List[Dict[str, Any]], offset: int) -> str:
    """The sentence with each trigger wrapped as [T1 word], numbered in text order."""
    for n, e in reversed(list(enumerate(triggers, 1))):
        a, b = e["start"] - offset, e["end"] - offset
        text = f"{text[:a]}[T{n} {text[a:b]}]{text[b:]}"
    return text


def llm_types(doc: Dict[str, Any]) -> None:
    if not EVENT_LLM:
        return
    for s in preprocess_chapter(doc["text"]).iter_sentences():
        here = sorted((e for e in doc["events"] if s.start <= e["start"] < s.end
                       and (EVENT_LLM_MODE == "all" or e["type"] == "OTHER")), key=lambda e: e["start"])
        if not here:
            continue
        ids = [f"T{n}" for n in range(1, len(here) + 1)]
        schema = {"type": "object", "required": ids, "additionalProperties": False,
                  "properties": {i: {"type": "string", "enum": list(EVENT_TYPES)} for i in ids}}
        reply = generate(TYPING_SYSTEM, marked(s.text, here, s.start), schema, num_predict=512, model=EVENT_LLM)
        for i, e in zip(ids, here):
            if reply.get(i) in EVENT_TYPES:
                e["type"] = reply[i]
