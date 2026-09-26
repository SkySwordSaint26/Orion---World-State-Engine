"""
Phase 3 — coreference and pronouns, over the whole story (long-range context matters).

BookNLP (trained on fiction) returns clusters of character spans; chosen over Maverick and FCoref on the 4 gold
stories (docs/wse_extraction_plan.md, Phase 3). `link` maps them onto the document:
    - a span overlapping a Phase 2 mention becomes that mention (1:1, largest overlap first: the scorer's `align`)
    - an unmatched span whose head word is a pronoun becomes a new `pronominal` mention, typed from its cluster;
      a cluster of pronouns only is a character when personal ("I ... me ... my": the narrator), skipped when it has
      only "it"-like pronouns (nothing to type it by)
    - other unmatched spans are ignored: mention detection is Phase 2's job (adding them lowered its scores)
Then `merge` joins repeats of the same name that the model split or left unclustered, and names introduced as
"my / his / her ... name is X" (the model misses these: the narrator's "I" was never linked to "Evelyn").
"""
import csv
import re
import tempfile
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from app.evaluation.score import align
from wse.mentions import kind, spacy_nlp

Span = Tuple[int, int]
PERSONAL = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves", "you", "your", "yours",
            "yourself", "he", "him", "his", "himself", "she", "her", "hers", "herself", "they", "them", "their",
            "theirs", "themselves"}
BOOKNLP_MODELS = Path.home() / "booknlp_models"
NAMING = re.compile(r"\b(?:[Mm]y|[Hh]is|[Hh]er|[Tt]heir|[Oo]ur|[Yy]our) name(?:\s+is|\s+was|['’]s)\s+")


# ---------------------------------------------------------------- backends: text -> clusters of character spans
def strip_position_ids(model_dir: Path) -> None:
    """BookNLP's 2021 checkpoints carry `bert.embeddings.position_ids`, a buffer current transformers rebuilds and
    rejects on strict loading. Removing it loses no learned weight."""
    import torch
    for path in model_dir.glob("*.model"):
        state = torch.load(path, map_location="cpu")
        stale = [k for k in state if k.endswith("embeddings.position_ids")]
        if stale:
            for k in stale:
                del state[k]
            torch.save(state, path)


@cache
def _booknlp():
    from booknlp.booknlp import BookNLP
    params = {"pipeline": "entity,quote,event,coref", "model": "big"}   # coref requires quote attribution
    try:
        return BookNLP("en", params)
    except RuntimeError as exc:                     # first run: checkpoints just downloaded, not yet fixed
        if "position_ids" not in str(exc):
            raise
        strip_position_ids(BOOKNLP_MODELS)
        return BookNLP("en", params)


@cache
def booknlp_output(text: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """(tokens, entities) rows of BookNLP's output files for `text`; cached, since events reuse them."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "story.txt").write_text(text, encoding="utf-8")
        _booknlp().process(str(Path(tmp) / "story.txt"), tmp, "story")
        read = lambda ext: list(csv.DictReader((Path(tmp) / f"story.{ext}").open(encoding="utf-8"),
                                               delimiter="\t", quoting=csv.QUOTE_NONE))
        return read("tokens"), read("entities")


def booknlp_clusters(text: str) -> List[List[Span]]:
    tokens, entities = booknlp_output(text)
    clusters: Dict[str, List[Span]] = {}
    for e in entities:
        clusters.setdefault(e["COREF"], []).append((int(tokens[int(e["start_token"])]["byte_onset"]),
                                                    int(tokens[int(e["end_token"])]["byte_offset"])))
    return list(clusters.values())


# ---------------------------------------------------------------- clusters -> mentions + coreference_clusters
def link(doc: Dict[str, Any], clusters: Sequence[Sequence[Span]]) -> None:
    text, mentions = doc["text"], doc["mentions"]
    parsed = spacy_nlp()(text)
    keyed = {(i, j): sp for i, c in enumerate(clusters) for j, sp in enumerate(c)}
    to_mention = align(keyed, {m["mention_id"]: (m["start"], m["end"]) for m in mentions})
    by_id = {m["mention_id"]: m for m in mentions}
    used, pronoun_spans = set(), set()
    for i, cluster in enumerate(clusters):
        members = list(dict.fromkeys(to_mention[(i, j)] for j in range(len(cluster))
                                     if (i, j) in to_mention and to_mention[(i, j)] not in used))
        pronouns = list(dict.fromkeys(sp for j, sp in enumerate(cluster) if (i, j) not in to_mention
                                      and sp not in pronoun_spans and kind(parsed, *sp) == "pronominal"))
        types = Counter(by_id[m]["type"] for m in members)
        ctype = (types.most_common(1)[0][0] if types
                 else "character" if any(text[s:e].lower() in PERSONAL for s, e in pronouns) else None)
        if ctype is None or len(members) + len(pronouns) < 2:
            continue
        pronoun_spans.update(pronouns)
        for s, e in pronouns:
            m = {"mention_id": f"M{len(mentions) + 1}", "text": text[s:e], "type": ctype,
                 "mention_kind": "pronominal", "start": s, "end": e}
            mentions.append(m)
            members.append(m["mention_id"])
        if len(members) >= 2:
            used.update(members)
            doc["coreference_clusters"].append({"cluster_id": f"C{len(doc['coreference_clusters']) + 1}",
                                                "mentions": members})


def naming_links(doc: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(possessive pronoun, proper name) mention pairs for "my / his / her ... name is X"."""
    starts = {m["start"]: m for m in doc["mentions"]}
    links = []
    for match in NAMING.finditer(doc["text"]):
        owner, name = starts.get(match.start()), starts.get(match.end())
        if owner and name and owner["mention_kind"] == "pronominal" and name["mention_kind"] == "proper":
            links.append((owner["mention_id"], name["mention_id"]))
    return links


def merge(doc: Dict[str, Any], links: Sequence[Tuple[str, str]] = ()) -> None:
    """Join non-pronoun mentions with the same (case-folded) text and type, and every linked pair, into one cluster,
    merging the clusters they are in: models split long chains and leave repeats unclustered ("trees" ... "trees")."""
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    for c in doc["coreference_clusters"]:
        for m in c["mentions"][1:]:
            parent[find(m)] = find(c["mentions"][0])
    for a, b in links:
        parent[find(b)] = find(a)
    first: Dict[Tuple[str, str], str] = {}
    for m in doc["mentions"]:
        if m["mention_kind"] != "pronominal":
            key = (m["text"].casefold(), m["type"])
            parent[find(m["mention_id"])] = find(first.setdefault(key, m["mention_id"]))
    groups: Dict[str, List[str]] = {}
    for m in doc["mentions"]:
        groups.setdefault(find(m["mention_id"]), []).append(m["mention_id"])
    doc["coreference_clusters"] = [{"cluster_id": f"C{i}", "mentions": g}
                                   for i, g in enumerate((g for g in groups.values() if len(g) >= 2), 1)]


def coref(doc: Dict[str, Any]) -> None:
    link(doc, booknlp_clusters(doc["text"]))
    merge(doc, naming_links(doc))
