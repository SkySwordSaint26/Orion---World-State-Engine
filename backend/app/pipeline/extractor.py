"""
Extract a chapter with the extraction pipeline (../extractor, docs/wse_extraction_plan.md) and hand the
integration the plain dict it accepts (entities by name with their facts, relationships, events).

The pipeline runs in its own Python 3.12 venv with torch and the GPU, so it is called as a subprocess
(`python -m extractor run IN.txt OUT.json`) and returns an orion_gold_v1 document. It resolves mentions and
coreference within the chapter; entities join earlier chapters by name and alias (WorldStateService).
"""
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from app.config.logging import get_logger
from app.preprocessing import preprocess_chapter

logger = get_logger(__name__)

EXTRACTOR_DIR = Path(__file__).resolve().parents[3] / "extractor"
EXTRACTOR_PYTHON = EXTRACTOR_DIR / ".venv" / "bin" / "python"
TIMEOUT_S = 900                                   # about 40 s per chapter on the RTX 4050, most of it model loading
ENTITY_TYPES = ("character", "location", "organization")
# ponytail: OTHER events (85% of the extractor's triggers, mostly noise) are left out of the world state; keep them if the
# timeline needs every verb
SKIP_EVENT_TYPES = {"OTHER"}


def run_extractor(text: str, chapter_number: int) -> Dict[str, Any]:
    """Chapter text -> the extractor's gold document. Raises on any failure (the chapter then fails, nothing is stored)."""
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "chapter.txt", Path(tmp) / "chapter.json"
        src.write_text(text, encoding="utf-8")
        done = subprocess.run([str(EXTRACTOR_PYTHON), "-m", "extractor", "run", str(src), str(out),
                               "--story-id", f"chapter_{chapter_number}"],
                              cwd=EXTRACTOR_DIR, capture_output=True, text=True, timeout=TIMEOUT_S)
        if done.returncode != 0:
            raise RuntimeError(f"Extraction failed on chapter {chapter_number}: {done.stderr.strip()[-2000:]}")
        return json.loads(out.read_text(encoding="utf-8"))


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
    by_name: Dict[str, Dict[str, Any]] = {}                        # groups with the same name are one entity
    for n, g in enumerate(groups):
        kind = Counter(m["type"] for m in g).most_common(1)[0][0]
        proper = Counter(m["text"] for m in g if m.get("mention_kind") == "proper")
        nominal = Counter(m["text"] for m in g if m.get("mention_kind") == "nominal")
        if kind not in ENTITY_TYPES or not (proper or (n in about and nominal)):
            continue
        name = max((proper or nominal).items(), key=lambda kv: (kv[1], -len(kv[0])))[0]   # tie: the shorter name
        names[n] = name
        entity = by_name.setdefault(name, {"canonical_name": name, "type": kind, "mention": name, "aliases": [],
                                           "attributes": {}})
        entity["aliases"] = sorted(set(entity["aliases"]) | set(proper) - {name})
    for f in doc["facts"]:
        name = names.get(group_of[f["entity_mention_id"]])
        if name:                                                  # one value per property and chapter: the first
            by_name[name]["attributes"].setdefault(f["property"], f["value"])

    relationships = [{"subject": names[s], "predicate": r["predicate"], "object": names[o]}
                     for r in doc["relationships"]
                     if (s := group_of[r["subject_mention_id"]]) in names and (o := group_of[r["object_mention_id"]]) in names]

    sentences = list(preprocess_chapter(doc["text"]).iter_sentences())
    sentence_at = lambda i: next((s.text for s in sentences if s.start <= i < s.end), "")
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
    return {"chapter_number": chapter_number, "pipeline": "extractor", "entities": list(by_name.values()),
            "relationships": relationships, "events": events, "temporal_relations": temporal}


def extract_chapter(text: str, chapter_number: int) -> Dict[str, Any]:
    doc = run_extractor(text, chapter_number)
    result = to_legacy(doc, chapter_number)
    logger.info(f"Extractor chapter {chapter_number}: {len(result['entities'])} entities, "
                f"{sum(len(e['attributes']) for e in result['entities'])} facts, "
                f"{len(result['relationships'])} relationships, {len(result['events'])} events")
    return result
