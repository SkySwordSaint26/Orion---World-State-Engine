"""
Document-level coreference clusters (Phase 6). Deterministic, LLM-free, DB-free, no similarity of any kind.

A cluster = mentions of ONE chapter that refer to the same entity. Only three high-precision rules create edges:

  same_entity  non-pronoun mentions already resolved to the same entity id (Phase 5)
  pronoun      a resolved pronoun joins the cluster of its entity's named mentions (its antecedent)
  exact_text   non-pronoun mentions with the same normalized text, ONLY when that cannot contradict the entities:
                 - a group whose known types disagree is not merged (unknown-type members are left out),
                 - a group whose mentions resolve to different entities is not merged,
                 - a mention without an entity is never merged into a group that has one (that would be a guess).
               Pronoun texts never cluster by text ("he" in two paragraphs is not one referent).

Mentions listed in `excluded` (Phase 5 declared them ambiguous or conflicting) never cluster, not even with an
identical string: two "Alice" that could each be a different Alice are not evidence of one Alice.
Clusters have >= 2 mentions; ids are C1.. ordered by the first member's position, members in mention order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.contracts import CoreferenceCluster, EntityMention
from app.resolution.resolver import name_key

RULE_EXACT, RULE_ENTITY, RULE_PRONOUN = "exact_text", "same_entity", "pronoun"


@dataclass(frozen=True)
class CoreferenceResult:
    clusters: Tuple[CoreferenceCluster, ...] = ()

    @property
    def mapping(self) -> Dict[str, str]:
        """mention_id -> cluster_id (only clustered mentions appear)"""
        return {m: c.cluster_id for c in self.clusters for m in c.mentions}

    def cluster_of(self, mention_id: str) -> Optional[CoreferenceCluster]:
        return next((c for c in self.clusters if mention_id in c.mentions), None)

    def to_dict(self) -> Dict[str, object]:
        return {"clusters": [c.to_dict() for c in self.clusters], "mapping": self.mapping}


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # the smaller index stays the root: deterministic


def _known_type(m: EntityMention) -> Optional[str]:
    t = (m.type or "").lower()
    return None if t in ("", "unknown") else t


def build_clusters(mentions: Sequence[EntityMention], excluded: Iterable[str] = ()) -> CoreferenceResult:
    """Group `mentions` (which must carry ids) into clusters. `entity_id` on a mention is optional."""
    mentions = list(mentions)
    if any(not m.id for m in mentions):
        raise ValueError("build_clusters needs mention ids (run app.contracts.assign_ids first)")
    skip: Set[str] = set(excluded)
    live = [i for i, m in enumerate(mentions) if m.id not in skip]
    pronoun = {i for i in live if mentions[i].mention_kind == "pronominal"}
    named = [i for i in live if i not in pronoun]

    uf = _UnionFind(len(mentions))
    edges: List[Tuple[int, int, str]] = []

    def link(a: int, b: int, rule: str) -> None:
        uf.union(a, b)
        edges.append((a, b, rule))

    # same_entity
    by_entity: Dict[str, List[int]] = {}
    for i in named:
        if mentions[i].entity_id:
            by_entity.setdefault(mentions[i].entity_id, []).append(i)
    for members in by_entity.values():
        for other in members[1:]:
            link(members[0], other, RULE_ENTITY)

    # pronoun -> antecedent cluster (its entity's named mentions)
    for i in sorted(pronoun):
        eid = mentions[i].entity_id
        if eid and eid in by_entity:
            link(by_entity[eid][0], i, RULE_PRONOUN)

    # exact_text
    by_text: Dict[str, List[int]] = {}
    for i in named:
        k = name_key(mentions[i].text)
        if k:
            by_text.setdefault(k, []).append(i)
    for group in by_text.values():
        known = {t for t in (_known_type(mentions[i]) for i in group) if t}
        subgroups = ([[i for i in group if _known_type(mentions[i]) == t] for t in sorted(known)]
                     if len(known) > 1 else [group])
        for sub in subgroups:
            entities = {mentions[i].entity_id for i in sub if mentions[i].entity_id}
            if len(entities) > 1:
                continue                                    # same string, different entities: never merge
            usable = [i for i in sub if mentions[i].entity_id] if entities else sub
            for other in usable[1:]:
                link(usable[0], other, RULE_EXACT)

    roots: Dict[int, List[int]] = {}
    for i in live:
        roots.setdefault(uf.find(i), []).append(i)
    rules_by_root: Dict[int, Set[str]] = {}
    for a, _b, rule in edges:
        rules_by_root.setdefault(uf.find(a), set()).add(rule)

    clusters: List[CoreferenceCluster] = []
    for root in sorted(r for r, members in roots.items() if len(members) >= 2):
        members = sorted(roots[root])
        entity_ids = {mentions[i].entity_id for i in members if mentions[i].entity_id}
        first_named = next((mentions[i] for i in members if i not in pronoun), None)
        clusters.append(CoreferenceCluster(
            cluster_id=f"C{len(clusters) + 1}",
            mentions=tuple(mentions[i].id for i in members),
            canonical_name=first_named.canonical_name if first_named else None,
            entity_id=next(iter(entity_ids)) if len(entity_ids) == 1 else None,
            rules=tuple(sorted(rules_by_root.get(root, ())))))
    return CoreferenceResult(tuple(clusters))
