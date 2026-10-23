"""
Extract a chapter with the extraction pipeline (../extractor, docs/wse_extraction_plan.md) and hand the
integration the plain dict it accepts (entities by name with their facts, relationships, events).

The pipeline runs in its own Python 3.12 venv with torch and the GPU, so it is called as a subprocess
(`python -m extractor run IN.txt OUT.json`) and returns an orion_gold_v1 document. It resolves mentions and
coreference within the chapter; entities join earlier chapters by name and alias (WorldStateService).
"""
import json
import os
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.config.logging import get_logger
from app.preprocessing import preprocess_chapter
from app.pipeline.cancellation import check_cancelled

logger = get_logger(__name__)

EXTRACTOR_DIR = Path(__file__).resolve().parents[3] / "extractor"
EXTRACTOR_PYTHON = EXTRACTOR_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
TIMEOUT_S = 900                                   # 2-6 min per chapter on the RTX 4050 (4 models load in turn)
ENTITY_TYPES = ("character", "location", "organization")
# ponytail: OTHER events (85% of the extractor's triggers, mostly noise) are left out of the world state; keep them if the
# timeline needs every verb
SKIP_EVENT_TYPES = {"OTHER"}


def run_extractor(
    text: str,
    chapter_number: int,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    """Chapter text -> the extractor's gold document. Raises on any failure (the chapter then fails, nothing is stored)."""
    with tempfile.TemporaryDirectory() as tmp:
        src, out, progress_file = Path(tmp) / "chapter.txt", Path(tmp) / "chapter.json", Path(tmp) / "progress.jsonl"
        src.write_text(text, encoding="utf-8")
        check_cancelled()
        with subprocess.Popen([str(EXTRACTOR_PYTHON), "-m", "extractor", "run", str(src), str(out),
                               "--story-id", f"chapter_{chapter_number}", "--progress-file", str(progress_file)],
                              cwd=EXTRACTOR_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONUTF8": "1"}) as process:
            deadline = time.monotonic() + TIMEOUT_S
            progress_offset = 0
            progress_buffer = ""

            def drain_progress() -> None:
                nonlocal progress_offset, progress_buffer
                if not progress or not progress_file.exists():
                    return
                with progress_file.open("r", encoding="utf-8") as stream:
                    stream.seek(progress_offset)
                    progress_buffer += stream.read()
                    progress_offset = stream.tell()
                lines = progress_buffer.split("\n")
                progress_buffer = lines.pop()
                for line in lines:
                    if not line:
                        continue
                    event = json.loads(line)
                    progress(event["stage"], event["completed"], event["total"])

            try:
                while True:
                    check_cancelled()
                    drain_progress()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(process.args, TIMEOUT_S)
                    try:
                        _, stderr = process.communicate(timeout=min(1, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                drain_progress()
            except BaseException:
                process.kill()
                process.communicate()
                raise
            if process.returncode != 0:
                raise RuntimeError(f"Extraction failed on chapter {chapter_number}: {stderr.strip()[-2000:]}")
        check_cancelled()
        return json.loads(out.read_text(encoding="utf-8"))


DETERMINERS = {"a", "an", "the", "his", "her", "my", "our", "their", "your", "its"}
IRREGULAR_PLURALS = {"children", "people", "men", "women", "folk", "folks", "family", "parents"}
_proper = lambda group: any(m.get("mention_kind") == "proper" for m in group)


def _bare(name: str) -> str:
    """'his wife' -> 'wife': the role noun without its determiner."""
    words = name.split()
    return " ".join(words[1:]) if len(words) > 1 and words[0].casefold() in DETERMINERS else name


def _plural(name: str) -> bool:
    """A nominal naming a group ('daughters', 'the children'). ponytail: English suffix check, not a lemmatizer"""
    last = name.split()[-1].casefold()
    return last in IRREGULAR_PLURALS or (last.endswith("s") and not last.endswith(("ss", "us", "is")))


MALE = {"father", "dad", "papa", "pa", "mr", "sir", "lord", "he", "him", "his", "himself", "husband", "son", "brother"}
FEMALE = {"mother", "mum", "mom", "mama", "ma", "step-mother", "stepmother", "mrs", "miss", "ms", "lady", "dame", "she",
          "her", "hers", "herself", "wife", "daughter", "sister"}
PRONOUNS = {"he", "him", "his", "himself", "she", "her", "hers", "herself"}


def gender(group: List[Dict[str, Any]]) -> Optional[str]:
    """'m' or 'f' for a coreference group, None when unclear. A role noun or title in a name decides ("his mother",
    "Mr. Bennet", "Lord Abbotsbury"); else the cluster's pronouns, when one gender has at least twice the other's."""
    named, pronoun = Counter(), Counter()
    for m in group:
        words = [w.strip(".,'’").casefold() for w in m["text"].split()]
        if len(words) == 1 and words[0] in PRONOUNS:
            pronoun["m" if words[0] in MALE else "f"] += 1
        elif words:
            for w in (words[0], words[-1]):                        # a title, or the role noun ("John's father")
                if w in MALE - PRONOUNS:
                    named["m"] += 1
                elif w in FEMALE - PRONOUNS:
                    named["f"] += 1
    for counts, least in ((named, 1), (pronoun, 2)):
        (top, n), *rest = counts.most_common(2) or [(None, 0)]
        if top and n >= least and n >= 2 * (rest[0][1] if rest else 0):
            return top
    return None


def parent_predicate(predicate: str, parent: List[Dict[str, Any]]) -> str:
    """PARENT_OF split by the parent's gender into the FATHER_OF / MOTHER_OF the world state and its one-father rule
    use (consistency/vocabulary.py); PARENT_OF when the gender is unclear. Other predicates unchanged."""
    if predicate != "PARENT_OF":
        return predicate
    return {"m": "FATHER_OF", "f": "MOTHER_OF"}.get(gender(parent), predicate)


def to_legacy(doc: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
    """The extractor's gold document -> the integration's dict. One entity per coreference cluster (or unclustered mention)
    of a character / location / organization type that has a proper name, or that a fact or relationship is about
    ("boss", "Dan’s mother"). Its name is its most frequent proper name (else nominal), the shorter on a tie since
    chapters mostly use the short form; other proper names are aliases, which is how later chapters find it."""
    mentions = {m["mention_id"]: m for m in doc["mentions"]}
    groups: List[List[Dict[str, Any]]] = [[mentions[i] for i in c["mentions"]] for c in doc["coreference_clusters"]]
    clustered = {i for c in doc["coreference_clusters"] for i in c["mentions"]}
    groups += [[m] for i, m in mentions.items() if i not in clustered]
    group_of = {m["mention_id"]: n for n, g in enumerate(groups) for m in g}
    about = {group_of[f["entity_mention_id"]] for f in doc["facts"]}
    about |= {group_of[r[k]] for r in doc["relationships"] for k in ("subject_mention_id", "object_mention_id")}

    names: Dict[int, str] = {}
    picked = []                                                    # (group, kind, proper names) per kept group
    for n, g in enumerate(groups):
        kind = Counter(m["type"] for m in g).most_common(1)[0][0]
        proper = Counter(m["text"] for m in g if m.get("mention_kind") == "proper")
        nominal = Counter(m["text"] for m in g if m.get("mention_kind") == "nominal")
        if kind not in ENTITY_TYPES or not (proper or (n in about and nominal)):
            continue
        name = max((proper or nominal).items(), key=lambda kv: (kv[1], -len(kv[0])))[0]   # tie: the shorter name
        if not proper and _plural(name):                           # "daughters", "children": a group, not a character
            continue
        names[n] = name
        picked.append((n, kind, proper))
    # A role noun alone ("wife") names nobody: call it after the named entity it is related to ("Mr. Bennet's wife")
    renamed = set()
    for r in doc["relationships"]:
        s, o = group_of[r["subject_mention_id"]], group_of[r["object_mention_id"]]
        for role, owner in ((s, o), (o, s)):
            if role in names and owner in names and role not in renamed and not _proper(groups[role]) \
                    and _proper(groups[owner]) and "'s " not in names[role]:     # "John's father" has its owner
                names[role] = f"{names[owner]}'s {_bare(names[role])}"
                renamed.add(role)
    ends = [(group_of[r["subject_mention_id"]], group_of[r["object_mention_id"]]) for r in doc["relationships"]]
    related = {g for s, o in ends if s in names and o in names for g in (s, o)}
    facts_on = {group_of[f["entity_mention_id"]] for f in doc["facts"]}
    by_name: Dict[str, Dict[str, Any]] = {}                        # groups with the same name are one entity
    for n, kind, proper in picked:
        if not proper and n not in related and n not in facts_on:  # its only relationship was to a dropped group
            del names[n]
            continue
        name = names[n]
        entity = by_name.setdefault(name, {"canonical_name": name, "type": kind, "mention": name, "aliases": [],
                                           "attributes": {}})
        entity["aliases"] = sorted(set(entity["aliases"]) | set(proper) - {name})
    for f in doc["facts"]:
        name = names.get(group_of[f["entity_mention_id"]])
        if name:                                                  # one value per property and chapter: the first
            by_name[name]["attributes"].setdefault(f["property"], f["value"])

    relationships = [{"subject": names[s], "predicate": parent_predicate(r["predicate"], groups[s]), "object": names[o]}
                     for r in doc["relationships"]
                     if (s := group_of[r["subject_mention_id"]]) in names and (o := group_of[r["object_mention_id"]]) in names]
    # two groups with one name are one entity: their relationships repeat ("John's mother MOTHER_OF John" twice)
    relationships = [dict(t) for t in dict.fromkeys(tuple(r.items()) for r in relationships)]

    sentences = list(preprocess_chapter(doc["text"]).iter_sentences())
    # one line: the book's hard line breaks ("heard that / Netherfield") would show in the timeline
    sentence_at = lambda i: " ".join(next((s.text for s in sentences if s.start <= i < s.end), "").split())
    events = []
    for e in doc["events"]:
        if e["type"] in SKIP_EVENT_TYPES:
            continue
        people = [(names[g], p["role"].upper()) for p in e["participants"]
                  if (g := group_of.get(p["mention_id"])) in names]
        events.append({"id": e["event_id"], "type": e["type"], "evidence": sentence_at(e["start"]),
                       "participants": [{"name": n, "role": r} for n, r in dict.fromkeys(people)]})
    kept = {e["id"] for e in events}
    temporal = [{"event_1": t["source_event_id"], "relation": t["relation"], "event_2": t["target_event_id"]}
                for t in doc["temporal_relations"] if {t["source_event_id"], t["target_event_id"]} <= kept]
    # Ephemeral source evidence for integration, never a fact or a database field.
    # Several source groups may collapse to one selected name: disagreement or an
    # unknown group must not silently become affirmative compatibility evidence.
    support = {}
    for n, name in names.items():
        support.setdefault(name.strip().casefold(), set()).add(gender(groups[n]))
    identity_evidence = {name: next(iter(values)) if len(values) == 1 else None
                         for name, values in support.items()}
    return {"chapter_number": chapter_number, "pipeline": "extractor", "entities": list(by_name.values()),
            "relationships": relationships, "events": events, "temporal_relations": temporal,
            "identity_evidence": identity_evidence}


def extract_chapter(
    text: str,
    chapter_number: int,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    doc = run_extractor(text, chapter_number, progress)
    result = to_legacy(doc, chapter_number)
    logger.info(f"Extractor chapter {chapter_number}: {len(result['entities'])} entities, "
                f"{sum(len(e['attributes']) for e in result['entities'])} facts, "
                f"{len(result['relationships'])} relationships, {len(result['events'])} events")
    return result
