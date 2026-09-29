"""
Deterministic, constrained mention -> entity resolution (Phase 5). No LLM, no embeddings, no fuzzy scoring.

Per name, strategies run in strict order and the FIRST one that finds any candidate decides; if that
strategy finds more than one distinct entity the mention is left UNRESOLVED (never guessed):

  1. exact_match       identical string to a canonical name                          confidence 1.00
  2. normalized_match  equal after case / whitespace / edge-punctuation folding      0.95
  3. alias             a stored alias                                                0.90
  4. alias (nickname)  a listed nickname of a formal first name (rob -> robert)      0.70
  5. alias (short)     the name's tokens are a proper subset of ONE entity's tokens  0.70
                       ("Alice" -> "Alice Sterling"); title-only names are excluded.
                       Steps 4-5 only target entities that existed BEFORE the batch, and any other name in
                       the batch that would also qualify makes the mention ambiguous (order independence).
  6. new_entity        nothing matched                                               1.00
  +  pronoun           see `_resolve_pronouns`                                       0.50

A candidate whose entity type conflicts with the mention's type (both known, different) is never matched.
The resolver is incremental: entities it decides are new join the working index, so later mentions with the same
name (exact / normalized) reuse them. Nothing else is learned mid-batch, so the outcome does not depend on order.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.contracts import EntityMention, ExtractionResult, assign_ids
from app.resolution.models import (
    EntityResolution, EntityResolutionResult, KnownEntity, NewEntity, ResolutionType, UnresolvedMention,
    is_provisional,
)

# Formal first names for common nicknames. Deliberately tiny and explicit: every entry is auditable.
NICKNAMES: Dict[str, str] = {
    "rob": "robert", "robbie": "robert", "bob": "robert", "bobby": "robert",
    "bill": "william", "will": "william", "liz": "elizabeth", "beth": "elizabeth",
    "tom": "thomas", "jim": "james", "kate": "katherine", "kit": "christopher",
}
TITLES = {"mr", "mrs", "ms", "miss", "dr", "sir", "lord", "lady", "captain", "king", "queen", "prince",
          "princess", "professor", "father", "mother", "master", "the"}
PERSON_TYPES = {"character", "person"}
PRONOUN_START = re.compile(r"(he|she|they)(?![\w'’-])", re.IGNORECASE)

CONF_EXACT, CONF_NORMALIZED, CONF_ALIAS, CONF_HEURISTIC, CONF_NEW, CONF_PRONOUN = 1.0, 0.95, 0.90, 0.70, 1.0, 0.50


def name_key(name: Optional[str]) -> str:
    """Case / whitespace / edge-punctuation folding used for every comparison."""
    return " ".join((name or "").casefold().split()).strip(" .,;:!?\"'“”‘’()")


def _tokens(name: str) -> Tuple[str, ...]:
    return tuple(t for t in re.split(r"[\s\-]+", name_key(name)) if t)


def _types_compatible(a: str, b: str) -> bool:
    a, b = (a or "unknown").lower(), (b or "unknown").lower()
    return "unknown" in (a, b) or a == b


@dataclass
class _Entry:
    id: str
    canonical: str
    type: str
    aliases: List[str]


class _Outcome:
    __slots__ = ("kind", "entry", "confidence", "evidence")

    def __init__(self, kind: str, entry: Optional[_Entry] = None, confidence: float = 0.0, evidence: str = ""):
        self.kind, self.entry, self.confidence, self.evidence = kind, entry, confidence, evidence  # kind: match|ambiguous|none


def _decide(hits: Sequence[_Entry], rtype: ResolutionType, conf: float, evidence: str) -> Optional[Tuple[_Outcome, ResolutionType]]:
    distinct = {h.id: h for h in hits}
    if not distinct:
        return None
    if len(distinct) > 1:
        return _Outcome("ambiguous", evidence=f"{len(distinct)} candidates: " + ", ".join(sorted(h.canonical for h in distinct.values()))), rtype
    return _Outcome("match", next(iter(distinct.values())), conf, evidence), rtype


def _match(
    name: str, mtype: str, entries: Sequence[_Entry], known_ids: Set[str], batch: Sequence[_Entry]
) -> Tuple[_Outcome, Optional[ResolutionType]]:
    """`batch` holds one pseudo entry per distinct name mentioned in this batch. Heuristic strategies (nickname,
    short form) may only TARGET entities that existed before the batch, but every other batch name counts as a
    competing candidate: that makes the outcome independent of mention order."""
    pool = [e for e in entries if _types_compatible(mtype, e.type)]
    stripped, key = name.strip(), name_key(name)
    if not key:
        return _Outcome("none"), None

    steps = (
        (lambda: [e for e in pool if e.canonical == stripped], ResolutionType.EXACT_MATCH, CONF_EXACT,
         f"identical to canonical name {stripped!r}"),
        (lambda: [e for e in pool if name_key(e.canonical) == key], ResolutionType.NORMALIZED_MATCH, CONF_NORMALIZED,
         f"{stripped!r} equals canonical name after case/format normalization"),
        (lambda: [e for e in pool if any(name_key(a) == key for a in e.aliases)], ResolutionType.ALIAS, CONF_ALIAS,
         f"{stripped!r} is a stored alias"),
    )
    for find, rtype, conf, evidence in steps:
        decided = _decide(find(), rtype, conf, evidence)
        if decided:
            return decided[0], rtype

    toks = _tokens(name)
    formal = NICKNAMES.get(key) if len(toks) == 1 else None
    known_pool = [e for e in pool if e.id in known_ids]
    known_keys = {name_key(e.canonical) for e in known_pool}
    rivals = [b for b in batch if _types_compatible(mtype, b.type) and name_key(b.canonical) not in known_keys]

    def heuristic(pred, evidence):
        hits = [e for e in known_pool if pred(e)]
        if not hits:
            return None
        rival_hits = [b for b in rivals if pred(b)]
        decided = _decide(hits + rival_hits, ResolutionType.ALIAS, CONF_HEURISTIC, evidence)
        return decided[0] if decided else None

    if formal:
        out = heuristic(lambda e: _tokens(e.canonical)[:1] == (formal,), f"nickname {key!r} -> {formal!r}")
        if out:
            return out, ResolutionType.ALIAS
    if toks and not set(toks) <= TITLES:
        tokset = set(toks)
        out = heuristic(lambda e: tokset < set(_tokens(e.canonical)),
                        f"{stripped!r} is a short form of one entity's name")
        if out:
            return out, ResolutionType.ALIAS
    return _Outcome("none"), None


# ------------------------------------------------------------------------------------------- result object
@dataclass(frozen=True)
class ResolvedExtraction:
    """Observations with entity ids attached, plus the resolution record. Ids may be provisional until `rebind`."""

    result: ExtractionResult
    resolution: EntityResolutionResult
    name_map: Dict[str, str]  # name_key -> entity id, only for names that map to exactly one entity

    def entity_for_name(self, name: str) -> Optional[str]:
        return self.name_map.get(name_key(name))

    def rebind(self, mapping: Dict[str, str]) -> "ResolvedExtraction":
        """Replace provisional ids by the ids of the rows created for them."""
        sub = lambda x: mapping.get(x, x) if x else x  # noqa: E731
        res = self.resolution
        new_res = EntityResolutionResult(
            resolutions=tuple(replace(r, resolved_entity_id=sub(r.resolved_entity_id)) for r in res.resolutions),
            unresolved=res.unresolved,
            new_entities=tuple(replace(n, entity_id=sub(n.entity_id)) for n in res.new_entities))
        r = self.result
        new_result = replace(
            r,
            entity_mentions=tuple(replace(m, entity_id=sub(m.entity_id)) for m in r.entity_mentions),
            relationships=tuple(replace(x, subject_entity_id=sub(x.subject_entity_id),
                                        object_entity_id=sub(x.object_entity_id)) for x in r.relationships),
            events=tuple(replace(e, participant_entity_ids=tuple(sub(i) for i in e.participant_entity_ids))
                         for e in r.events),
            facts=tuple(replace(f, entity_id=sub(f.entity_id)) for f in r.facts))
        return ResolvedExtraction(new_result, new_res, {k: sub(v) for k, v in self.name_map.items()})


def _build_name_map(mentions: Sequence[EntityMention], mapping: Dict[str, str]) -> Dict[str, str]:
    seen: Dict[str, Set[str]] = {}
    for m in mentions:
        eid = mapping.get(m.id or "")
        if not eid or m.mention_kind == "pronominal":
            continue
        for name in (m.text, m.canonical_name):
            seen.setdefault(name_key(name), set()).add(eid)
    return {k: next(iter(v)) for k, v in seen.items() if k and len(v) == 1}


def _attach(result: ExtractionResult, mapping: Dict[str, str], name_map: Dict[str, str]) -> ExtractionResult:
    look = lambda n: name_map.get(name_key(n))  # noqa: E731
    return replace(
        result,
        entity_mentions=tuple(replace(m, entity_id=mapping.get(m.id or "")) for m in result.entity_mentions),
        relationships=tuple(replace(r, subject_entity_id=look(r.subject), object_entity_id=look(r.object))
                            for r in result.relationships),
        events=tuple(replace(e, participant_entity_ids=tuple(look(p) for p in e.participants))
                     for e in result.events),
        facts=tuple(replace(f, entity_id=look(f.entity)) for f in result.facts))


# ------------------------------------------------------------------------------------------- main entry point
def resolve_entities(
    result: ExtractionResult, known: Iterable[KnownEntity] = (), document: Any = None
) -> ResolvedExtraction:
    """Resolve every EntityMention of `result` against `known` (existing World State) and earlier mentions."""
    result = assign_ids(result)
    entries = [_Entry(k.id, k.canonical_name, (k.entity_type or "unknown").lower(), list(k.aliases)) for k in known]
    resolutions: List[EntityResolution] = []
    unresolved: List[UnresolvedMention] = []
    new_entities: List[NewEntity] = []
    known_ids = {e.id for e in entries}
    batch: List[_Entry] = []
    for m in result.entity_mentions:
        k = name_key(m.canonical_name or m.text)
        if k and k not in {name_key(b.canonical) for b in batch}:
            batch.append(_Entry(f"batch:{k}", (m.canonical_name or m.text).strip(), (m.type or "unknown").lower(), []))

    for m in result.entity_mentions:
        mtype = (m.type or "unknown").lower()
        names: List[str] = []
        for n in (m.canonical_name, m.text):
            if name_key(n) and name_key(n) not in [name_key(x) for x in names]:
                names.append(n)

        outcomes = [(n, *_match(n, mtype, entries, known_ids, batch)) for n in names]
        matches = [(n, o, t) for n, o, t in outcomes if o.kind == "match"]
        ambiguous = [(n, o) for n, o, _ in outcomes if o.kind == "ambiguous"]
        ids = {o.entry.id for _, o, _ in matches}

        if len(ids) > 1:
            unresolved.append(UnresolvedMention(m.id, "conflicting matches: " + "; ".join(
                f"{n!r} -> {o.entry.canonical!r}" for n, o, _ in matches)))
        elif ambiguous:
            unresolved.append(UnresolvedMention(m.id, "ambiguous: " + "; ".join(f"{n!r}: {o.evidence}" for n, o in ambiguous)))
        elif matches:
            n, o, t = max(matches, key=lambda x: x[1].confidence)
            resolutions.append(EntityResolution(m.id, o.entry.id, t, o.confidence, o.evidence))
        else:
            prov = f"new:{len(new_entities) + 1}"
            canonical = (m.canonical_name or m.text).strip()
            entry = _Entry(prov, canonical, mtype, [])
            entries.append(entry)
            new_entities.append(NewEntity(prov, canonical, mtype, m.id))
            resolutions.append(EntityResolution(m.id, prov, ResolutionType.NEW_ENTITY, CONF_NEW,
                                                f"no existing entity matches {canonical!r}"))

    pronoun_mentions: List[EntityMention] = []
    if document is not None:
        pronoun_mentions, pronoun_res = _resolve_pronouns(result, resolutions, entries, document)
        resolutions.extend(pronoun_res)

    resolution = EntityResolutionResult(tuple(resolutions), tuple(unresolved), tuple(new_entities))
    mapping = resolution.mapping
    name_map = _build_name_map(result.entity_mentions, mapping)
    attached = _attach(result, mapping, name_map)
    if pronoun_mentions:
        attached = replace(attached, entity_mentions=attached.entity_mentions + tuple(
            replace(p, entity_id=mapping[p.id]) for p in pronoun_mentions))
    return ResolvedExtraction(attached, resolution, name_map)


# ------------------------------------------------------------------------------------------- pronouns
def _occurrences(text: str, name: str) -> List[Tuple[int, int]]:
    if not name.strip():
        return []
    pat = re.compile(r"(?<![\w])" + re.escape(name.strip()) + r"(?![\w])")
    return [(m.start(), m.end()) for m in pat.finditer(text)]


def _inside_quote(text: str, pos: int) -> bool:
    before = text[:pos]
    return before.count('"') % 2 == 1 or before.count("“") > before.count("”")


def _resolve_pronouns(
    result: ExtractionResult, resolutions: Sequence[EntityResolution], entries: Sequence[_Entry], document: Any
) -> Tuple[List[EntityMention], List[EntityResolution]]:
    """
    Very conservative. A pronoun (he / she / they) is resolved only when ALL hold:
      * it is the first word of a sentence and not inside a quotation;
      * exactly ONE distinct person entity (type character/person) is named earlier in the same paragraph;
    otherwise it is left alone. Gender is unknown to the World State, so it is not used.
    Names searched are the resolved mentions' surface texts plus their entity's canonical name and aliases.
    """
    by_id = {e.id: e for e in entries}
    mention_by_id = {m.id: m for m in result.entity_mentions}
    names_of: Dict[str, Set[str]] = {}
    for r in resolutions:
        ent, m = by_id.get(r.resolved_entity_id), mention_by_id.get(r.mention_id)
        if ent is None or m is None or ent.type not in PERSON_TYPES:
            continue
        names_of.setdefault(ent.id, set()).update({ent.canonical, m.text, m.canonical_name, *ent.aliases})

    mentions_out: List[EntityMention] = []
    res_out: List[EntityResolution] = []
    if not names_of:
        return mentions_out, res_out

    used = {m.id for m in result.entity_mentions}
    counter = 0
    for paragraph in document.paragraphs:
        ptext, pstart = paragraph.text, paragraph.start
        occ = {eid: [(pstart + s, pstart + e) for name in names for s, e in _occurrences(ptext, name)]
               for eid, names in names_of.items()}
        for sentence in paragraph.sentences:
            hit = PRONOUN_START.match(sentence.text)
            if not hit or _inside_quote(ptext, sentence.start - pstart):
                continue
            candidates = {eid for eid, spans in occ.items() if any(end <= sentence.start for _, end in spans)}
            if len(candidates) != 1:
                continue
            eid = next(iter(candidates))
            counter += 1
            while f"M{len(used) + counter}" in used:
                counter += 1
            mid = f"M{len(used) + counter}"
            start, end = sentence.start, sentence.start + hit.end()
            ante = max((s for s, e in occ[eid] if e <= sentence.start), default=None)
            mentions_out.append(EntityMention(
                id=mid, text=sentence.text[:hit.end()], type=by_id[eid].type, mention_kind="pronominal",
                start=start, end=end, canonical_name=by_id[eid].canonical,
                source_chunk="resolver:pronoun", source_span=(sentence.start, sentence.end),
                sentence_ids=(sentence.id,)))
            res_out.append(EntityResolution(
                mid, eid, ResolutionType.PRONOUN, CONF_PRONOUN,
                f"only person named earlier in the paragraph: {by_id[eid].canonical!r} (at {ante})"))
    return mentions_out, res_out
