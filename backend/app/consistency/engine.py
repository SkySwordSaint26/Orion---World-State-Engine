from typing import List, Optional, Sequence

from app.consistency.rules import (
    AgeMonotonicRule, DeadThenAliveRule, FactRule, ImmutableFactRule, IncompatiblePredicateRule,
    RelationshipRule, SingleValuedIncomingRule, TemporalCycleRule, TemporalRule,
)
from app.consistency.types import FactCheck, Finding, RelationshipCheck, TemporalCheck


class ConsistencyEngine:
    """
    Rule evaluation only: routes a check to every rule that applies and concatenates their findings in
    a fixed order. It performs no I/O, so results depend only on the input.
    """

    def __init__(
        self,
        fact_rules: Optional[Sequence[FactRule]] = None,
        relationship_rules: Optional[Sequence[RelationshipRule]] = None,
        temporal_rules: Optional[Sequence[TemporalRule]] = None,
    ):
        self.fact_rules = list(fact_rules) if fact_rules is not None else [
            ImmutableFactRule(), AgeMonotonicRule(), DeadThenAliveRule()
        ]
        self.relationship_rules = list(relationship_rules) if relationship_rules is not None else [
            IncompatiblePredicateRule(), SingleValuedIncomingRule()
        ]
        self.temporal_rules = list(temporal_rules) if temporal_rules is not None else [TemporalCycleRule()]

    def check_fact(self, check: FactCheck) -> List[Finding]:
        findings: List[Finding] = []
        for rule in self.fact_rules:
            if rule.applies(check):
                findings.extend(rule.evaluate(check))
        return findings

    def check_relationship(self, check: RelationshipCheck) -> List[Finding]:
        findings: List[Finding] = []
        for rule in self.relationship_rules:
            if rule.applies(check):
                findings.extend(rule.evaluate(check))
        return findings

    def check_temporal(self, check: TemporalCheck) -> List[Finding]:
        findings: List[Finding] = []
        for rule in self.temporal_rules:
            findings.extend(rule.evaluate(check))
        return findings
