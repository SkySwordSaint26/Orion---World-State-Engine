"""
Deterministic consistency rules. Each rule is a small, independent class that receives plain data
(see types.py) and returns Findings; none of them touches the database or an LLM.

    FactRule          ImmutableFactRule, AgeMonotonicRule, DeadThenAliveRule
    RelationshipRule  IncompatiblePredicateRule, SingleValuedIncomingRule
    TemporalRule      TemporalCycleRule
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.consistency import vocabulary as vocab
from app.consistency.types import (
    FactCheck, FactVersionView, Finding, RelationshipCheck, RelationshipVersionView, TemporalCheck
)
from app.core.constants import ContradictionType, FactStatus, RelationshipStatus

_ACCEPTED_FACT_STATUSES = (FactStatus.ACTIVE.value, FactStatus.SUPERSEDED.value)


def _accepted_with_chapter(history: Sequence[FactVersionView]) -> List[Tuple[int, int, FactVersionView]]:
    """(chapter_number, creation_index, version) for accepted versions that have a chapter."""
    return [
        (v.chapter_number, index, v)
        for index, v in enumerate(history)
        if v.status in _ACCEPTED_FACT_STATUSES and v.chapter_number is not None
    ]


# --------------------------------------------------------------------------------- fact rules
class FactRule(ABC):
    rule_id: str

    @abstractmethod
    def applies(self, check: FactCheck) -> bool: ...

    @abstractmethod
    def evaluate(self, check: FactCheck) -> List[Finding]: ...


class ImmutableFactRule(FactRule):
    """REQ-21/22 support: a single-valued property may not take a second, different value."""
    rule_id = "IMMUTABLE_FACT"
    confidence = 0.9

    def applies(self, check: FactCheck) -> bool:
        return vocab.property_kind(check.property_name) is vocab.PropertyKind.IMMUTABLE

    def evaluate(self, check: FactCheck) -> List[Finding]:
        if vocab.is_blank(check.new.value):
            return []
        references = [v for v in check.history if v.status == FactStatus.ACTIVE.value and not vocab.is_blank(v.value)]
        if not references:
            return []
        reference = references[-1]
        if vocab.values_equal(reference.value, check.new.value):
            return []
        return [Finding(
            rule_id=self.rule_id,
            contradiction_type=ContradictionType.FACT_FACT.value,
            explanation=(
                f"Direct contradiction for '{check.entity_name}': property '{check.property_name}' "
                f"was previously stated as '{reference.value}' but is now stated as '{check.new.value}'."
            ),
            confidence=self.confidence,
            old_fact_version_id=reference.version_id,
            new_fact_version_id=check.new.version_id,
        )]


class AgeMonotonicRule(FactRule):
    """
    REQ-23: a character's age must not go down as chapters progress. Compares the new age with the
    nearest earlier and nearest later chapter that holds a parseable age. Versions in the SAME chapter
    are never compared (no order inside a chapter), and there is no flashback marker in the data
    model, hence the reduced confidence.

    HEURISTIC: a flashback ("she was 12 then") looks exactly like an age decrease and WILL be flagged.
    Treat findings as candidates for review, not proof.
    """
    rule_id = "AGE_MONOTONIC"
    confidence = 0.7

    def applies(self, check: FactCheck) -> bool:
        return vocab.normalize_property(check.property_name) == vocab.AGE_PROPERTY

    def evaluate(self, check: FactCheck) -> List[Finding]:
        new_age = vocab.parse_age(check.new.value)
        chapter = check.new.chapter_number
        if new_age is None or chapter is None:
            return []

        aged = [(c, i, v, vocab.parse_age(v.value)) for c, i, v in _accepted_with_chapter(check.history)]
        aged = [entry for entry in aged if entry[3] is not None]
        earlier = [e for e in aged if e[0] < chapter]
        later = [e for e in aged if e[0] > chapter]

        findings: List[Finding] = []
        if earlier:
            c, _, version, age = max(earlier, key=lambda e: (e[0], e[1]))
            if new_age < age:
                findings.append(self._finding(
                    check, version,
                    f"Age of '{check.entity_name}' decreased: {age} in chapter {c}, but {new_age} in chapter {chapter}."))
        if later:
            c, _, version, age = min(later, key=lambda e: (e[0], e[1]))
            if new_age > age:
                findings.append(self._finding(
                    check, version,
                    f"Age of '{check.entity_name}' is {new_age} in chapter {chapter}, "
                    f"which is more than the {age} stated later in chapter {c}."))
        return findings

    def _finding(self, check: FactCheck, other: FactVersionView, text: str) -> Finding:
        return Finding(
            rule_id=self.rule_id,
            contradiction_type=ContradictionType.FACT_FACT.value,
            explanation=text,
            confidence=self.confidence,
            old_fact_version_id=other.version_id,
            new_fact_version_id=check.new.version_id,
        )


class DeadThenAliveRule(FactRule):
    """
    REQ-26 (status part): once a character's status is DEAD in an earlier chapter, a later chapter must
    not state them ALIVE (and the mirror case when a re-extracted earlier chapter says DEAD after a
    later ALIVE). Only the controlled status values dead/deceased and alive/living participate.
    """
    rule_id = "DEAD_THEN_ALIVE"
    confidence = 0.7

    def applies(self, check: FactCheck) -> bool:
        return vocab.normalize_property(check.property_name) == vocab.STATUS_PROPERTY

    def evaluate(self, check: FactCheck) -> List[Finding]:
        new_state = vocab.normalize_status(check.new.value)
        chapter = check.new.chapter_number
        if new_state is None or chapter is None:
            return []

        states = [(c, i, v, vocab.normalize_status(v.value)) for c, i, v in _accepted_with_chapter(check.history)]
        if new_state == "ALIVE":
            dead_before = [e for e in states if e[3] == "DEAD" and e[0] < chapter]
            if dead_before:
                c, _, version, _ = max(dead_before, key=lambda e: (e[0], e[1]))
                return [self._finding(check, version,
                        f"'{check.entity_name}' is stated as {check.new.value} in chapter {chapter}, "
                        f"but was already '{version.value}' in chapter {c}.")]
        else:
            alive_after = [e for e in states if e[3] == "ALIVE" and e[0] > chapter]
            if alive_after:
                c, _, version, _ = min(alive_after, key=lambda e: (e[0], e[1]))
                return [self._finding(check, version,
                        f"'{check.entity_name}' is stated as '{check.new.value}' in chapter {chapter}, "
                        f"but is still '{version.value}' in later chapter {c}.")]
        return []

    def _finding(self, check: FactCheck, other: FactVersionView, text: str) -> Finding:
        return Finding(
            rule_id=self.rule_id,
            contradiction_type=ContradictionType.FACT_FACT.value,
            explanation=text,
            confidence=self.confidence,
            old_fact_version_id=other.version_id,
            new_fact_version_id=check.new.version_id,
        )


# --------------------------------------------------------------------------- relationship rules
class RelationshipRule(ABC):
    rule_id: str

    @abstractmethod
    def applies(self, check: RelationshipCheck) -> bool: ...

    @abstractmethod
    def evaluate(self, check: RelationshipCheck) -> List[Finding]: ...


class IncompatiblePredicateRule(RelationshipRule):
    """
    REQ-25: the pair's current ACTIVE type may not be replaced by an explicitly incompatible one.

    NOT SYMMETRY-AWARE: only versions of the same ORDERED (source, target) pair are compared, so
    "Alice ENEMY_OF Bob" and "Bob FRIEND_OF Alice" (different relationship rows) are never compared.
    TODO(relationship-normalization): fold symmetric predicates (and map inverse predicates) into one
    canonical direction before evaluation, once the vocabulary declares which predicates are symmetric.
    """
    rule_id = "RELATIONSHIP_INCOMPATIBLE"
    confidence = 0.85

    def applies(self, check: RelationshipCheck) -> bool:
        return True

    def evaluate(self, check: RelationshipCheck) -> List[Finding]:
        active = [v for v in check.pair_history if v.status == RelationshipStatus.ACTIVE.value and v.predicate]
        if not active or not check.new.predicate:
            return []
        reference = active[-1]
        if reference.predicate == check.new.predicate:
            return []
        if frozenset({reference.predicate, check.new.predicate}) not in vocab.INCOMPATIBLE_PREDICATE_PAIRS:
            return []
        return [Finding(
            rule_id=self.rule_id,
            contradiction_type=ContradictionType.RELATIONSHIP_RELATIONSHIP.value,
            explanation=(
                f"Relationship conflict between '{check.subject_name}' and '{check.object_name}': "
                f"previous relationship '{reference.predicate}' is fundamentally incompatible with new '{check.new.predicate}'."
            ),
            confidence=self.confidence,
            old_relationship_version_id=reference.version_id,
            new_relationship_version_id=check.new.version_id,
        )]


class SingleValuedIncomingRule(RelationshipRule):
    """
    REQ-25 ("a character's stated father changing"): for predicates where a target can have only one
    source (FATHER_OF), a different source with the same ACTIVE predicate is a conflict. The data model
    cannot express an explanation (e.g. adoption), so the finding is a candidate with reduced confidence.
    """
    rule_id = "RELATIONSHIP_SINGLE_SOURCE"
    confidence = 0.6

    def applies(self, check: RelationshipCheck) -> bool:
        return check.new.predicate in vocab.SINGLE_VALUED_INCOMING_PREDICATES

    def evaluate(self, check: RelationshipCheck) -> List[Finding]:
        others = [
            v for v in check.incoming
            if v.status == RelationshipStatus.ACTIVE.value
            and v.predicate == check.new.predicate
            and v.source_entity_id != check.new.source_entity_id
        ]
        if not others:
            return []
        reference = others[-1]
        return [Finding(
            rule_id=self.rule_id,
            contradiction_type=ContradictionType.RELATIONSHIP_RELATIONSHIP.value,
            explanation=(
                f"'{check.object_name}' can have only one {check.new.predicate} source, but is now stated as "
                f"'{check.subject_name}' after previously being stated as '{reference.source_name}'."
            ),
            confidence=self.confidence,
            old_relationship_version_id=reference.version_id,
            new_relationship_version_id=check.new.version_id,
        )]


# -------------------------------------------------------------------------------- temporal rule
class TemporalRule(ABC):
    rule_id: str

    @abstractmethod
    def evaluate(self, check: TemporalCheck) -> List[Finding]: ...


class TemporalCycleRule(TemporalRule):
    """
    BEFORE/AFTER relations must form a DAG. Every distinct cycle is reported once, rotated to start at
    its smallest event id and explored in sorted order, so the same input always gives the same
    findings and the same text. SIMULTANEOUS and relations naming unknown events are ignored.

    SCOPE: one chapter's relations only. Temporal relations are not persisted, so a cycle that spans
    chapters is invisible. TODO(temporal-normalization): the rule itself is scope-agnostic; the input
    (event ids, stored relations) is what will change - see ConsistencyService.run_checks.
    """
    rule_id = "TEMPORAL_CYCLE"
    confidence = 1.0

    def evaluate(self, check: TemporalCheck) -> List[Finding]:
        nodes = sorted(set(check.event_ids))
        graph: Dict[str, Set[str]] = {n: set() for n in nodes}
        for first, relation, second in check.relations:
            if first not in graph or second not in graph:
                continue
            kind = str(relation or "").upper()
            if kind == "BEFORE":
                graph[first].add(second)
            elif kind == "AFTER":
                graph[second].add(first)

        cycles: List[Tuple[str, ...]] = []
        seen: Set[Tuple[str, ...]] = set()
        state = {n: 0 for n in nodes}  # 0 unvisited, 1 on current path, 2 finished

        def visit(node: str, path: List[str]) -> None:
            state[node] = 1
            path.append(node)
            for neighbor in sorted(graph[node]):
                if state[neighbor] == 0:
                    visit(neighbor, path)
                elif state[neighbor] == 1:
                    cycle = path[path.index(neighbor):]
                    pivot = cycle.index(min(cycle))
                    canonical = tuple(cycle[pivot:] + cycle[:pivot])
                    if canonical not in seen:
                        seen.add(canonical)
                        cycles.append(canonical)
            path.pop()
            state[node] = 2

        for node in nodes:
            if state[node] == 0:
                visit(node, [])

        where = f" in chapter {check.chapter_number}" if check.chapter_number is not None else ""
        return [
            Finding(
                rule_id=self.rule_id,
                contradiction_type=ContradictionType.CYCLE.value,
                explanation=f"Temporal ordering cycle detected{where}: {' -> '.join(cycle + (cycle[0],))}",
                confidence=self.confidence,
                event_refs=(cycle[-1], cycle[0]),   # the edge that closes the cycle
            )
            for cycle in cycles
        ]
