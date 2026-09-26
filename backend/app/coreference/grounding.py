"""
Cluster-based grounding (Phase 6): give relationships / events / facts an entity id through mention clusters when
the Phase 5 name lookup could not ("He hit John": `He` is in a cluster with `Robert` -> subject = Robert).

Only ids that are still None are filled; ids Phase 5 set are never changed. A reference resolves only when it is
unambiguous:
  * scope = the observation's quoted evidence when it occurs EXACTLY ONCE verbatim inside its chunk span,
    otherwise the whole chunk span;
  * candidates = mentions whose text (or canonical name) equals the reference and lie in scope; pronoun mentions
    must lie inside the scope by their own exact offsets;
  * for pronoun references (he/she/they) the scope must contain exactly ONE such pronoun token, so an
    unresolved pronoun elsewhere can never be mistaken for a resolved one;
  * every candidate must belong to a cluster (or be resolved) with the SAME entity id; a candidate without an
    entity (ambiguous mention) blocks the resolution.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.contracts import EntityMention, ExtractionResult, Observation
from app.coreference.clusterer import CoreferenceResult, build_clusters
from app.resolution.models import is_provisional
from app.resolution.resolver import ResolvedExtraction, name_key

PRONOUN_WORDS = ("he", "she", "they")


def locate_evidence(text: str, evidence: str, span: Tuple[int, int]) -> Optional[Tuple[int, int]]:
    """(start, end) of `evidence` if it occurs exactly once, verbatim, inside `span`; else None."""
    if not evidence or not evidence.strip():
        return None
    lo, hi = span
    hits, pos = [], text.find(evidence, lo, hi)
    while pos != -1 and len(hits) < 2:
        hits.append(pos)
        pos = text.find(evidence, pos + 1, hi)
    return (hits[0], hits[0] + len(evidence)) if len(hits) == 1 else None


def _scope(obs: Observation, document: Any) -> Tuple[int, int]:
    if document is not None:
        located = locate_evidence(document.text, obs.raw_text, obs.source_span)
        if located:
            return located
    return obs.source_span


def _in_scope(m: EntityMention, scope: Tuple[int, int]) -> bool:
    if m.start is not None:                                  # own exact offsets (pronoun mentions)
        return scope[0] <= m.start and m.end <= scope[1]
    return m.source_span[0] < scope[1] and scope[0] < m.source_span[1]   # chunk-level: overlap


def _entity_for_reference(
    name: str, obs: Observation, mentions: Sequence[EntityMention], coref: CoreferenceResult, document: Any
) -> Optional[str]:
    key = name_key(name)
    if not key:
        return None
    scope = _scope(obs, document)
    if key in PRONOUN_WORDS:
        if document is None:
            return None
        tokens = re.findall(rf"(?<![\w'’-]){key}(?![\w'’-])", document.text[scope[0]:scope[1]], re.IGNORECASE)
        if len(tokens) != 1:
            return None                                       # zero or several: cannot tell which one is meant
        cands = [m for m in mentions if m.mention_kind == "pronominal" and name_key(m.text) == key
                 and _in_scope(m, scope)]
    else:
        cands = [m for m in mentions if m.mention_kind != "pronominal"
                 and key in (name_key(m.text), name_key(m.canonical_name)) and _in_scope(m, scope)]
    if not cands:
        return None
    ids = set()
    for m in cands:
        cluster = coref.cluster_of(m.id)
        ids.add((cluster.entity_id if cluster and cluster.entity_id else m.entity_id) or None)
    return next(iter(ids)) if len(ids) == 1 else None   # a None (ambiguous mention) makes the set differ or be None


def ground_references(
    result: ExtractionResult, coref: CoreferenceResult, document: Any = None
) -> ExtractionResult:
    """Fill still-empty entity ids of relationships, events and facts through the clusters."""
    mentions = list(result.entity_mentions)

    def look(name: str, obs: Observation) -> Optional[str]:
        return _entity_for_reference(name, obs, mentions, coref, document)

    return replace(
        result,
        relationships=tuple(replace(
            r, subject_entity_id=r.subject_entity_id or look(r.subject, r),
            object_entity_id=r.object_entity_id or look(r.object, r)) for r in result.relationships),
        events=tuple(replace(
            e, participant_entity_ids=tuple(
                (e.participant_entity_ids[i] if e.participant_entity_ids else None) or look(p, e)
                for i, p in enumerate(e.participants))) for e in result.events),
        facts=tuple(replace(f, entity_id=f.entity_id or look(f.entity, f)) for f in result.facts))


def apply_coreference(resolved: ResolvedExtraction, document: Any = None) -> Tuple[ResolvedExtraction, CoreferenceResult]:
    """Phase 5 output -> clusters -> cluster-grounded observations (`result.coreference_clusters` is filled)."""
    excluded = [u.mention_id for u in resolved.resolution.unresolved]
    coref = build_clusters(resolved.result.entity_mentions, excluded)
    grounded = ground_references(replace(resolved.result, coreference_clusters=coref.clusters), coref, document)
    return replace(resolved, result=grounded), coref
