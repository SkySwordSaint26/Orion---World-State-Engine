"""Phase 2: each consistency rule in isolation (pure functions, no database, no LLM)."""
import itertools

import pytest

from app.consistency import vocabulary as vocab
from app.consistency.engine import ConsistencyEngine
from app.consistency.rules import (
    AgeMonotonicRule, DeadThenAliveRule, ImmutableFactRule, IncompatiblePredicateRule,
    SingleValuedIncomingRule, TemporalCycleRule,
)
from app.consistency.types import (
    FactCheck, FactVersionView, RelationshipCheck, RelationshipVersionView, TemporalCheck,
)

ACTIVE, SUPERSEDED, CONTRADICTED = "ACTIVE", "SUPERSEDED", "CONTRADICTED"


def fv(value, chapter=None, status=ACTIVE, vid=None):
    return FactVersionView(vid or f"fv-{value}-{chapter}", value, status, chapter)


def fact_check(prop, new, *history, entity="Alice"):
    return FactCheck(entity, vocab.normalize_property(prop), new, tuple(history))


# ------------------------------------------------------------------ vocabulary
def test_property_kinds_come_from_the_controlled_vocabulary():
    for name in ("eye_color", "birth_place", "date_of_birth", "origin", "species", "Eye Color", "eye-color"):
        assert vocab.property_kind(name) is vocab.PropertyKind.IMMUTABLE
    for name in ("age", "location", "status"):
        assert vocab.property_kind(name) is vocab.PropertyKind.MUTABLE
    for name in ("favorite_color", "eye_colour", "hair", ""):
        assert vocab.property_kind(name) is vocab.PropertyKind.UNKNOWN  # synonyms are NOT guessed


def test_age_parsing_is_strict():
    assert vocab.parse_age("30") == 30 and vocab.parse_age(30) == 30 and vocab.parse_age(" 45 years old ") == 45
    for junk in ("thirty", "about 40", "1985", "-3", None, True, 3.5, "", "151"):
        assert vocab.parse_age(junk) is None


# ----------------------------------------------------------------- immutable facts
def test_immutable_same_value_is_not_a_contradiction():
    check = fact_check("eye_color", fv("blue", 2), fv("blue", 1))
    assert ImmutableFactRule().evaluate(check) == []


def test_immutable_value_comparison_ignores_case_and_whitespace():
    assert ImmutableFactRule().evaluate(fact_check("eye_color", fv(" Blue ", 2), fv("blue", 1))) == []


def test_immutable_different_value_is_a_contradiction_with_both_versions_referenced():
    old = fv("blue", 1, vid="old-1")
    new = fv("green", 2, vid="new-1")
    findings = ImmutableFactRule().evaluate(fact_check("eye_color", new, old))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "IMMUTABLE_FACT" and f.contradiction_type == "FACT_FACT"
    assert (f.old_fact_version_id, f.new_fact_version_id) == ("old-1", "new-1")
    assert "blue" in f.explanation and "green" in f.explanation and "Alice" in f.explanation
    assert f.stored_explanation.startswith("[IMMUTABLE_FACT] ")


def test_immutable_rule_compares_against_active_version_only():
    history = (fv("blue", 1, status=SUPERSEDED), fv("green", 2, status=CONTRADICTED), fv("blue", 3))
    assert ImmutableFactRule().evaluate(fact_check("eye_color", fv("blue", 4), *history)) == []
    assert len(ImmutableFactRule().evaluate(fact_check("eye_color", fv("green", 4), *history))) == 1


def test_immutable_rule_ignores_blank_values_and_missing_history():
    assert ImmutableFactRule().evaluate(fact_check("eye_color", fv("blue", 1))) == []
    assert ImmutableFactRule().evaluate(fact_check("eye_color", fv("", 2), fv("blue", 1))) == []
    assert ImmutableFactRule().evaluate(fact_check("eye_color", fv("blue", 2), fv(None, 1))) == []


@pytest.mark.parametrize("prop", ["location", "status", "age", "favorite_color", "job_title", "rank"])
def test_mutable_and_unknown_properties_never_trigger_the_immutable_rule(prop):
    check = fact_check(prop, fv("B", 2), fv("A", 1))
    assert ImmutableFactRule().applies(check) is False
    assert ConsistencyEngine(fact_rules=[ImmutableFactRule()]).check_fact(check) == []


def test_unknown_property_produces_no_findings_from_the_default_engine():
    engine = ConsistencyEngine()
    assert engine.check_fact(fact_check("favorite_color", fv("green", 2), fv("blue", 1))) == []
    assert engine.check_fact(fact_check("location", fv("Berlin", 2), fv("Paris", 1))) == []  # REQ-24 deferred


# --------------------------------------------------------------------------- age
def test_age_increase_and_same_age_are_valid():
    rule = AgeMonotonicRule()
    assert rule.evaluate(fact_check("age", fv("31", 2), fv("30", 1))) == []
    assert rule.evaluate(fact_check("age", fv("30", 2), fv("30", 1))) == []


def test_age_decrease_across_chapters_is_a_contradiction():
    findings = AgeMonotonicRule().evaluate(fact_check("age", fv("30", 5, vid="n"), fv("40", 3, vid="o")))
    assert len(findings) == 1
    assert (findings[0].old_fact_version_id, findings[0].new_fact_version_id) == ("o", "n")
    assert "decreased" in findings[0].explanation and findings[0].confidence < 1.0


def test_age_in_the_same_chapter_is_not_compared():
    assert AgeMonotonicRule().evaluate(fact_check("age", fv("30", 3), fv("40", 3))) == []


def test_age_uses_the_nearest_earlier_chapter():
    history = (fv("20", 1), fv("50", 4))
    assert AgeMonotonicRule().evaluate(fact_check("age", fv("45", 6), *history)) != []      # 45 < 50 (chapter 4)
    assert AgeMonotonicRule().evaluate(fact_check("age", fv("51", 6), *history)) == []


def test_age_older_than_a_later_chapter_is_a_contradiction_when_an_earlier_chapter_is_reextracted():
    findings = AgeMonotonicRule().evaluate(fact_check("age", fv("60", 2), fv("40", 5, vid="later")))
    assert len(findings) == 1 and findings[0].old_fact_version_id == "later"


def test_age_rule_ignores_unparseable_unchaptered_and_rejected_versions():
    rule = AgeMonotonicRule()
    assert rule.evaluate(fact_check("age", fv("thirty", 5), fv("40", 3))) == []
    assert rule.evaluate(fact_check("age", fv("30", None), fv("40", 3))) == []
    assert rule.evaluate(fact_check("age", fv("30", 5), fv("40", None))) == []
    assert rule.evaluate(fact_check("age", fv("30", 5), fv("40", 3, status=CONTRADICTED))) == []


# -------------------------------------------------------------------- dead -> alive
def test_dead_then_alive_in_a_later_chapter_is_a_contradiction():
    findings = DeadThenAliveRule().evaluate(fact_check("status", fv("alive", 5, vid="n"), fv("Dead", 3, vid="o")))
    assert len(findings) == 1 and findings[0].rule_id == "DEAD_THEN_ALIVE"
    assert (findings[0].old_fact_version_id, findings[0].new_fact_version_id) == ("o", "n")


def test_dead_then_other_status_is_not_flagged():
    rule = DeadThenAliveRule()
    assert rule.evaluate(fact_check("status", fv("wounded", 5), fv("dead", 3))) == []   # outside controlled values
    assert rule.evaluate(fact_check("status", fv("dead", 5), fv("dead", 3))) == []
    assert rule.evaluate(fact_check("status", fv("alive", 3), fv("dead", 3))) == []      # same chapter
    assert rule.evaluate(fact_check("status", fv("alive", 2), fv("dead", 3))) == []      # alive BEFORE death is fine


def test_alive_then_dead_is_valid_but_dead_before_an_existing_later_alive_is_flagged():
    rule = DeadThenAliveRule()
    assert rule.evaluate(fact_check("status", fv("dead", 5), fv("alive", 3))) == []
    assert len(rule.evaluate(fact_check("status", fv("dead", 2), fv("alive", 6)))) == 1


# ------------------------------------------------------------------- relationships
def rv(predicate, status=ACTIVE, vid=None, source="src-1", name="Alice"):
    return RelationshipVersionView(vid or f"rv-{predicate}", vocab.normalize_predicate(predicate), status, None, source, name)


def rel_check(new, pair_history=(), incoming=(), subject="Alice", obj="Bob"):
    return RelationshipCheck(subject, obj, new, tuple(pair_history), tuple(incoming))


def test_first_relationship_and_repeated_relationship_are_valid():
    rule = IncompatiblePredicateRule()
    assert rule.evaluate(rel_check(rv("FRIEND_OF"))) == []
    assert rule.evaluate(rel_check(rv("FRIEND_OF"), [rv("FRIEND_OF")])) == []


@pytest.mark.parametrize("old,new", [
    ("ENEMY_OF", "FRIEND_OF"), ("FRIEND_OF", "ENEMY_OF"),
    ("ENEMY_OF", "MARRIED_TO"), ("MARRIED_TO", "ENEMY_OF"),
    ("DEAD_AT_HANDS_OF", "ALLY_OF"), ("ALLY_OF", "DEAD_AT_HANDS_OF"),
])
def test_explicitly_incompatible_pairs_are_contradictions(old, new):
    findings = IncompatiblePredicateRule().evaluate(rel_check(rv(new, vid="n"), [rv(old, vid="o")]))
    assert len(findings) == 1
    f = findings[0]
    assert f.contradiction_type == "RELATIONSHIP_RELATIONSHIP" and f.rule_id == "RELATIONSHIP_INCOMPATIBLE"
    assert (f.old_relationship_version_id, f.new_relationship_version_id) == ("o", "n")


@pytest.mark.parametrize("old,new", [
    ("KNOWS", "ENEMY_OF"), ("ENEMY_OF", "KNOWS"), ("FRIEND_OF", "MARRIED_TO"),
    ("COLLEAGUE_OF", "MARRIED_TO"), ("FRIEND_OF", "ALLY_OF"), ("WORKS_FOR", "ENEMY_OF"),
])
def test_semantically_different_but_undeclared_pairs_are_not_contradictions(old, new):
    assert IncompatiblePredicateRule().evaluate(rel_check(rv(new), [rv(old)])) == []


def test_predicates_are_compared_after_normalization_not_as_raw_text():
    assert len(IncompatiblePredicateRule().evaluate(rel_check(rv("friend of"), [rv("Enemy-Of")]))) == 1


def test_superseded_history_is_not_the_reference():
    assert IncompatiblePredicateRule().evaluate(rel_check(rv("FRIEND_OF"), [rv("ENEMY_OF", status=SUPERSEDED)])) == []


def test_second_father_for_the_same_child_is_flagged():
    other = rv("FATHER_OF", vid="old-father", source="bob", name="Bob")
    new = rv("FATHER_OF", vid="new-father", source="carl", name="Carl")
    findings = SingleValuedIncomingRule().evaluate(rel_check(new, incoming=[other], subject="Carl", obj="Dave"))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "RELATIONSHIP_SINGLE_SOURCE" and f.confidence < 1.0
    assert (f.old_relationship_version_id, f.new_relationship_version_id) == ("old-father", "new-father")
    assert "Bob" in f.explanation and "Carl" in f.explanation


def test_same_father_or_other_predicates_are_not_flagged_by_the_single_source_rule():
    rule = SingleValuedIncomingRule()
    same_father = rv("FATHER_OF", source="bob")
    assert rule.evaluate(rel_check(rv("FATHER_OF", source="bob"), incoming=[same_father])) == []
    assert rule.applies(rel_check(rv("FRIEND_OF", source="carl"))) is False
    assert rule.evaluate(rel_check(rv("FATHER_OF", source="carl"), incoming=[rv("FATHER_OF", status=SUPERSEDED, source="bob")])) == []
    assert rule.evaluate(rel_check(rv("FATHER_OF", source="carl"), incoming=[rv("MOTHER_OF", source="bob")])) == []


# ---------------------------------------------------------------------------- temporal
def temporal(pairs, events=None, extra=()):
    relations = tuple((a, "BEFORE", b) for a, b in pairs) + tuple(extra)
    ids = events if events is not None else sorted({x for pair in pairs for x in pair})
    return TemporalCheck(tuple(ids), relations)


def test_single_and_chained_relations_are_valid():
    assert TemporalCycleRule().evaluate(temporal([("A", "B")])) == []
    assert TemporalCycleRule().evaluate(temporal([("A", "B"), ("B", "C")])) == []


def test_duplicate_relations_are_valid():
    assert TemporalCycleRule().evaluate(temporal([("A", "B"), ("A", "B"), ("A", "B")])) == []


def test_direct_cycle_is_a_contradiction():
    findings = TemporalCycleRule().evaluate(temporal([("A", "B"), ("B", "A")]))
    assert len(findings) == 1
    assert findings[0].contradiction_type == "CYCLE" and findings[0].confidence == 1.0
    assert "A -> B -> A" in findings[0].explanation
    assert findings[0].event_refs == ("B", "A")


def test_indirect_cycle_is_a_contradiction():
    findings = TemporalCycleRule().evaluate(temporal([("A", "B"), ("B", "C"), ("C", "A")]))
    assert len(findings) == 1 and "A -> B -> C -> A" in findings[0].explanation


def test_unrelated_chains_are_valid():
    assert TemporalCycleRule().evaluate(temporal([("A", "B"), ("B", "C"), ("X", "Y"), ("Y", "Z")])) == []


def test_cycle_inside_one_chain_does_not_taint_an_unrelated_chain():
    findings = TemporalCycleRule().evaluate(temporal([("A", "B"), ("B", "A"), ("X", "Y")]))
    assert len(findings) == 1 and "X" not in findings[0].explanation


def test_after_relation_and_mixed_directions_are_handled():
    # "A AFTER B" is B -> A; together with "A BEFORE B" that is a cycle
    check = TemporalCheck(("A", "B"), (("A", "AFTER", "B"), ("A", "BEFORE", "B")))
    assert len(TemporalCycleRule().evaluate(check)) == 1
    assert TemporalCycleRule().evaluate(TemporalCheck(("A", "B"), (("A", "AFTER", "B"),))) == []


def test_simultaneous_unknown_events_and_self_loop():
    assert TemporalCycleRule().evaluate(TemporalCheck(("A", "B"), (("A", "SIMULTANEOUS", "B"), ("B", "SIMULTANEOUS", "A")))) == []
    assert TemporalCycleRule().evaluate(TemporalCheck(("A",), (("A", "BEFORE", "GHOST"), ("GHOST", "BEFORE", "A")))) == []
    assert len(TemporalCycleRule().evaluate(TemporalCheck(("A",), (("A", "BEFORE", "A"),)))) == 1


def test_temporal_findings_do_not_depend_on_input_order():
    relations = [("A", "B"), ("B", "C"), ("C", "A"), ("X", "Y"), ("Y", "X")]
    baseline = None
    for ordering in itertools.islice(itertools.permutations(relations), 24):
        events = list(reversed(sorted({x for p in ordering for x in p})))
        result = [(f.explanation, f.event_refs) for f in TemporalCycleRule().evaluate(temporal(list(ordering), events))]
        baseline = baseline or result
        assert result == baseline and len(result) == 2


# ---------------------------------------------------------------------------- engine
def test_engine_routes_by_rule_applicability_and_has_no_hidden_rules():
    engine = ConsistencyEngine()
    assert [r.rule_id for r in engine.fact_rules] == ["IMMUTABLE_FACT", "AGE_MONOTONIC", "DEAD_THEN_ALIVE"]
    assert [r.rule_id for r in engine.relationship_rules] == ["RELATIONSHIP_INCOMPATIBLE", "RELATIONSHIP_SINGLE_SOURCE"]
    assert [r.rule_id for r in engine.temporal_rules] == ["TEMPORAL_CYCLE"]
    assert ConsistencyEngine(fact_rules=[], relationship_rules=[], temporal_rules=[]).check_fact(
        fact_check("eye_color", fv("green", 2), fv("blue", 1))) == []
