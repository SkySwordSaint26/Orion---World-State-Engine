"""Phase 2: the rule engine wired into world-state integration, persistence, dedupe and the Phase 1 transaction."""
import ast
import pathlib

import pytest

from app.consistency import ConsistencyEngine
from app.models.contradiction import Contradiction
from app.models.entity import Entity
from app.models.fact import Fact, FactVersion
from app.pipeline import extractor
from app.pipeline.llm_client import llm_client
from app.services.consistency_service import ConsistencyService
from app.services.world_state_service import WorldStateService
from app.workers.tasks.extraction_task import run_extraction_job


# ------------------------------------------------------------------------------ helpers
def integrate(env, world_id, info, data, commit=True):
    with env.Session() as s:
        counts = WorldStateService(s).integrate_extraction_result(
            world_id, data, chapter_id=info["chapter_id"], chapter_version_id=info["chapter_version_id"])
        if commit:
            s.commit()
    return counts


def person(name, **attributes):
    return {"canonical_name": name, "type": "character", "attributes": attributes}


def chapter_data(entities=(), relationships=(), events=(), temporal=()):
    return {"entities": list(entities), "relationships": list(relationships),
            "events": list(events), "temporal_relations": list(temporal)}


def rel(subject, predicate, obj):
    return {"subject": subject, "predicate": predicate, "object": obj}


def contradictions(env, world_id):
    with env.Session() as s:
        rows = s.query(Contradiction).filter(Contradiction.world_id == world_id).order_by(Contradiction.created_at, Contradiction.id).all()
        return [{c: getattr(r, c) for c in (
            "id", "contradiction_type", "explanation", "confidence", "status", "old_fact_version_id",
            "new_fact_version_id", "old_relationship_version_id", "new_relationship_version_id",
            "event_id_a", "event_id_b")} for r in rows]


def rel_statuses(env, world_id, source, target):
    from app.models.relationship import Relationship, RelationshipVersion
    with env.Session() as s:
        src = s.query(Entity).filter_by(world_id=world_id, canonical_name=source).one()
        tgt = s.query(Entity).filter_by(world_id=world_id, canonical_name=target).one()
        r = s.query(Relationship).filter_by(source_entity_id=src.id, target_entity_id=tgt.id).one()
        versions = s.query(RelationshipVersion).filter_by(relationship_id=r.id).order_by(RelationshipVersion.created_at, RelationshipVersion.id).all()
        return [(v.relationship_type, v.status) for v in versions]


@pytest.fixture
def world(phase1_env):
    return phase1_env, phase1_env.make_world("W", chapters=3)


# -------------------------------------------------------------------------------- facts
def test_immutable_change_is_persisted_with_everything_the_schema_can_hold(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", eye_color="blue")]))
    counts = integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", eye_color="green")]))

    assert counts["contradictions_found"] == 1
    [c] = contradictions(env, w["world_id"])
    assert c["contradiction_type"] == "FACT_FACT" and c["status"] == "DETECTED" and c["confidence"] == 0.9
    assert c["explanation"].startswith("[IMMUTABLE_FACT] ") and "blue" in c["explanation"] and "green" in c["explanation"]
    assert c["old_fact_version_id"] and c["new_fact_version_id"] and c["old_fact_version_id"] != c["new_fact_version_id"]
    assert c["old_relationship_version_id"] is None and c["event_id_a"] is None
    # the referenced versions are the right ones, and chapter info is reachable through them
    with env.Session() as s:
        old, new = s.get(FactVersion, c["old_fact_version_id"]), s.get(FactVersion, c["new_fact_version_id"])
        assert (old.value, new.value) == ("blue", "green")
        assert old.chapter_id == w["runs"][1]["chapter_id"] and new.chapter_id == w["runs"][2]["chapter_id"]
    assert env.fact_statuses(w["world_id"], "Alice", "eye_color") == [("blue", "ACTIVE"), ("green", "CONTRADICTED")]


def test_immutable_same_value_is_not_a_contradiction(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", eye_color="blue")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", eye_color="Blue")]))
    assert contradictions(env, w["world_id"]) == []


def test_property_name_variants_are_normalized_before_rules_apply(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", **{"Eye Color": "blue"})]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", **{"eye-color": "green"})]))
    # different raw property names are different facts today (normalization of storage is a later stage),
    # so this must NOT be flagged: rules never guess that two spellings are the same property.
    assert contradictions(env, w["world_id"]) == []
    integrate(env, w["world_id"], w["runs"][3], chapter_data([person("Alice", **{"Eye Color": "green"})]))
    assert len(contradictions(env, w["world_id"])) == 1  # same raw name as chapter 1 -> normalized -> rule applies


def test_mutable_property_change_is_evolution_not_contradiction(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", location="Paris")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", location="Berlin")]))
    assert contradictions(env, w["world_id"]) == []
    assert env.fact_statuses(w["world_id"], "Alice", "location") == [("Paris", "SUPERSEDED"), ("Berlin", "ACTIVE")]


def test_unknown_property_change_is_evolution_and_never_a_contradiction(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", favorite_color="blue")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", favorite_color="green")]))
    assert contradictions(env, w["world_id"]) == []
    assert env.fact_statuses(w["world_id"], "Alice", "favorite_color") == [("blue", "SUPERSEDED"), ("green", "ACTIVE")]


def test_different_entities_with_the_same_property_do_not_conflict(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", eye_color="blue")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Bob", eye_color="green")]))
    assert contradictions(env, w["world_id"]) == []


def test_age_decrease_is_flagged_and_increase_is_not(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", age="40")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", age="41")]))
    assert contradictions(env, w["world_id"]) == []
    integrate(env, w["world_id"], w["runs"][3], chapter_data([person("Alice", age="30")]))
    [c] = contradictions(env, w["world_id"])
    assert c["explanation"].startswith("[AGE_MONOTONIC] ") and c["confidence"] == 0.7
    assert env.fact_statuses(w["world_id"], "Alice", "age") == [("40", "SUPERSEDED"), ("41", "ACTIVE"), ("30", "CONTRADICTED")]


def test_age_checked_against_a_later_chapter_when_an_earlier_one_is_reextracted(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][3], chapter_data([person("Alice", age="30")]))
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", age="50")]))
    assert len(contradictions(env, w["world_id"])) == 1


def test_dead_then_alive_is_flagged_but_dead_then_wounded_is_not(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", status="dead")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", status="wounded")]))
    assert contradictions(env, w["world_id"]) == []
    integrate(env, w["world_id"], w["runs"][3], chapter_data([person("Alice", status="alive")]))
    [c] = contradictions(env, w["world_id"])
    assert c["explanation"].startswith("[DEAD_THEN_ALIVE] ")


# ---------------------------------------------------------------------- relationships
def test_valid_and_repeated_relationships_are_clean(world):
    env, w = world
    people = [person("Alice"), person("Bob")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Alice", "FRIEND_OF", "Bob")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data(people, [rel("Alice", "FRIEND_OF", "Bob")]))
    assert contradictions(env, w["world_id"]) == []


def test_incompatible_relationship_change_is_flagged_with_version_references(world):
    env, w = world
    people = [person("Alice"), person("Bob")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Alice", "ENEMY_OF", "Bob")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data(people, [rel("Alice", "friend of", "Bob")]))
    [c] = contradictions(env, w["world_id"])
    assert c["contradiction_type"] == "RELATIONSHIP_RELATIONSHIP" and c["confidence"] == 0.85
    assert c["explanation"].startswith("[RELATIONSHIP_INCOMPATIBLE] ")
    assert c["old_relationship_version_id"] and c["new_relationship_version_id"] and c["old_fact_version_id"] is None
    assert rel_statuses(env, w["world_id"], "Alice", "Bob") == [("ENEMY_OF", "ACTIVE"), ("friend of", "CONTRADICTED")]


def test_knows_then_enemy_of_is_valid_evolution(world):
    env, w = world
    people = [person("Alice"), person("Bob")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Alice", "KNOWS", "Bob")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data(people, [rel("Alice", "ENEMY_OF", "Bob")]))
    assert contradictions(env, w["world_id"]) == []
    assert rel_statuses(env, w["world_id"], "Alice", "Bob") == [("KNOWS", "SUPERSEDED"), ("ENEMY_OF", "ACTIVE")]


def test_a_second_father_is_flagged_across_relationship_rows(world):
    env, w = world
    people = [person("Bob"), person("Carl"), person("Dave")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Bob", "FATHER_OF", "Dave")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data(people, [rel("Carl", "FATHER_OF", "Dave")]))
    [c] = contradictions(env, w["world_id"])
    assert c["explanation"].startswith("[RELATIONSHIP_SINGLE_SOURCE] ") and c["confidence"] == 0.6
    assert "Bob" in c["explanation"] and "Carl" in c["explanation"]
    assert rel_statuses(env, w["world_id"], "Carl", "Dave") == [("FATHER_OF", "CONTRADICTED")]
    assert rel_statuses(env, w["world_id"], "Bob", "Dave") == [("FATHER_OF", "ACTIVE")]


def test_same_father_restated_and_two_different_friends_are_clean(world):
    env, w = world
    people = [person("Bob"), person("Carl"), person("Dave")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Bob", "FATHER_OF", "Dave"), rel("Bob", "FRIEND_OF", "Dave")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data(people, [rel("Bob", "FATHER_OF", "Dave"), rel("Carl", "FRIEND_OF", "Dave")]))
    assert contradictions(env, w["world_id"]) == []


# ------------------------------------------------------------------------------ temporal
def temporal_chapter(relations, event_ids=("e1", "e2", "e3")):
    return chapter_data(
        [person("Alice")],
        events=[{"id": e, "type": "OTHER", "participants": ["Alice"], "evidence": f"event {e}"} for e in event_ids],
        temporal=[{"event_1": a, "relation": r, "event_2": b} for a, r, b in relations])


def test_temporal_cycle_is_persisted_with_the_closing_events(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][2], temporal_chapter([("e1", "BEFORE", "e2"), ("e2", "BEFORE", "e3"), ("e3", "BEFORE", "e1")]))
    [c] = contradictions(env, w["world_id"])
    assert c["contradiction_type"] == "CYCLE" and c["confidence"] == 1.0
    assert c["explanation"] == "[TEMPORAL_CYCLE] Temporal ordering cycle detected in chapter 2: e1 -> e2 -> e3 -> e1"
    assert c["event_id_a"] and c["event_id_b"] and c["event_id_a"] != c["event_id_b"]


def test_valid_and_unrelated_temporal_chains_create_nothing(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], temporal_chapter([("e1", "BEFORE", "e2"), ("e2", "BEFORE", "e3")]))
    integrate(env, w["world_id"], w["runs"][2], temporal_chapter([("e1", "BEFORE", "e2")], event_ids=("e1", "e2", "e3")))
    assert contradictions(env, w["world_id"]) == []


def test_the_same_local_event_ids_in_another_chapter_are_a_separate_contradiction(world):
    env, w = world
    cycle = [("e1", "BEFORE", "e2"), ("e2", "BEFORE", "e1")]
    integrate(env, w["world_id"], w["runs"][1], temporal_chapter(cycle))
    integrate(env, w["world_id"], w["runs"][2], temporal_chapter(cycle))
    assert len(contradictions(env, w["world_id"])) == 2


# --------------------------------------------------------------------------------- dedupe
def test_repeating_a_temporal_check_does_not_duplicate_the_contradiction(world):
    env, w = world
    events = [{"id": "e1"}, {"id": "e2"}]
    relations = [{"event_1": "e1", "relation": "BEFORE", "event_2": "e2"}, {"event_1": "e2", "relation": "BEFORE", "event_2": "e1"}]
    with env.Session() as s:
        service = ConsistencyService(s)
        first = service.run_checks(w["world_id"], events, relations)
        second = service.run_checks(w["world_id"], events, relations)
        s.commit()
    assert len(first) == 1 and second == []
    assert len(contradictions(env, w["world_id"])) == 1


def test_rechecking_the_same_fact_version_does_not_duplicate_the_contradiction(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", eye_color="blue")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", eye_color="green")]))
    with env.Session() as s:
        entity = s.query(Entity).filter_by(canonical_name="Alice").one()
        fact = s.query(Fact).filter_by(entity_id=entity.id, property_name="eye_color").one()
        green = next(v for v in s.query(FactVersion).filter_by(fact_id=fact.id) if v.value == "green")
        service = ConsistencyService(s)
        again = service.evaluate_fact_version(entity, fact, green)
        third = service.evaluate_fact_version(entity, fact, green)
        s.commit()
    assert len(again.findings) == 1 and again.created == [] and third.created == []
    assert len(contradictions(env, w["world_id"])) == 1


def test_a_dismissed_contradiction_is_not_raised_again_by_a_recheck(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", eye_color="blue")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Alice", eye_color="green")]))
    with env.Session() as s:
        s.query(Contradiction).update({"status": "DISMISSED"})
        s.commit()
        entity = s.query(Entity).filter_by(canonical_name="Alice").one()
        fact = s.query(Fact).filter_by(entity_id=entity.id, property_name="eye_color").one()
        green = next(v for v in s.query(FactVersion).filter_by(fact_id=fact.id) if v.value == "green")
        assert ConsistencyService(s).evaluate_fact_version(entity, fact, green).created == []
    assert [c["status"] for c in contradictions(env, w["world_id"])] == ["DISMISSED"]


# --------------------------------------------------------------- Phase 1 transaction boundary
def test_contradiction_detection_does_not_commit_on_its_own(world):
    env, w = world
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Alice", eye_color="blue")]))
    with env.Session() as s:
        WorldStateService(s).integrate_extraction_result(
            w["world_id"], chapter_data([person("Alice", eye_color="green")]),
            chapter_id=w["runs"][2]["chapter_id"], chapter_version_id=w["runs"][2]["chapter_version_id"])
        assert s.query(Contradiction).count() == 1           # visible inside the open transaction
        assert contradictions(env, w["world_id"]) == []       # invisible to any other connection
        s.rollback()
    assert contradictions(env, w["world_id"]) == []
    assert env.fact_statuses(w["world_id"], "Alice", "eye_color") == [("blue", "ACTIVE")]


def _eye_color_extractor(colors):
    """Extractor stub: Alice's eye colour per chapter, a fresh friend per chapter, and a relationship between them."""
    def extract_chapter(text, chapter_number):
        friend = f"Friend{chapter_number}"
        return chapter_data([person("Alice", eye_color=colors[chapter_number]), person(friend)],
                            [rel("Alice", "KNOWS", friend)])
    return extract_chapter


def test_contradictions_commit_together_with_the_chapter_and_run_status(world, monkeypatch):
    env, w = world
    monkeypatch.setattr(extractor, "extract_chapter", _eye_color_extractor({1: "blue", 2: "green", 3: "green"}))

    assert run_extraction_job(w["job_id"])["status"] == "success"

    # read through a fresh connection: both were committed with their chapters. Chapter 3 restates "green"
    # against the still-ACTIVE "blue", so it is a second, distinct contradiction (different new version).
    found = contradictions(env, w["world_id"])
    assert len(found) == 2 and all(c["explanation"].startswith("[IMMUTABLE_FACT] ") for c in found)
    assert found[0]["old_fact_version_id"] == found[1]["old_fact_version_id"]
    assert found[0]["new_fact_version_id"] != found[1]["new_fact_version_id"]
    assert env.job(w["job_id"])["status"] == "done"
    assert env.fact_statuses(w["world_id"], "Alice", "eye_color") == [
        ("blue", "ACTIVE"), ("green", "CONTRADICTED"), ("green", "CONTRADICTED")]


def test_a_consistency_failure_rolls_back_the_whole_chapter_and_keeps_earlier_state(world, monkeypatch):
    env, w = world
    monkeypatch.setattr(extractor, "extract_chapter", _eye_color_extractor({1: "blue", 2: "green", 3: "green"}))
    assert env.execute(w["world_id"], w["job_id"], w["runs"][1])["status"] == "success"
    assert env.execute(w["world_id"], w["job_id"], w["runs"][2])["status"] == "success"
    before_rows = env.world_rows(w["world_id"])
    before_contradictions = contradictions(env, w["world_id"])
    assert len(before_contradictions) == 1

    def boom(self, check):
        raise RuntimeError("relationship rule crashed")

    monkeypatch.setattr(ConsistencyEngine, "check_relationship", boom)
    result = env.execute(w["world_id"], w["job_id"], w["runs"][3])

    assert result["status"] == "failed" and "relationship rule crashed" in result["error"]
    assert env.world_rows(w["world_id"]) == before_rows                      # no Friend3, facts, relationship, mention...
    assert contradictions(env, w["world_id"]) == before_contradictions       # earlier committed contradiction intact
    assert env.fact_statuses(w["world_id"], "Alice", "eye_color") == [("blue", "ACTIVE"), ("green", "CONTRADICTED")]
    assert env.run(w["runs"][3]["run_id"])[0] == "failed"


def test_a_failure_after_a_contradiction_was_written_removes_that_contradiction_too(world, monkeypatch):
    env, w = world
    monkeypatch.setattr(extractor, "extract_chapter", _eye_color_extractor({1: "blue", 2: "green", 3: "green"}))
    assert env.execute(w["world_id"], w["job_id"], w["runs"][1])["status"] == "success"

    def boom(self, *a, **k):
        raise RuntimeError("temporal stage crashed")

    monkeypatch.setattr(ConsistencyService, "run_checks", boom)      # runs AFTER the eye-colour contradiction is flushed
    assert env.execute(w["world_id"], w["job_id"], w["runs"][2])["status"] == "failed"

    assert contradictions(env, w["world_id"]) == []
    assert env.fact_statuses(w["world_id"], "Alice", "eye_color") == [("blue", "ACTIVE")]


# ------------------------------------------------------------------------------- no LLM
FORBIDDEN = {"llm_client", "httpx", "openai", "ollama", "requests", "urllib"}


def _imports(path: pathlib.Path):
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(part for alias in node.names for part in alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            names.update(alias.name for alias in node.names)
    return names


def test_the_consistency_engine_imports_no_llm_or_network_code():
    app_dir = pathlib.Path(__file__).resolve().parent.parent
    files = list((app_dir / "consistency").glob("*.py")) + [
        app_dir / "services" / "consistency_service.py",
        app_dir / "pipeline" / "resolution" / "fact_resolution.py",
        app_dir / "pipeline" / "resolution" / "relationship_resolution.py",
    ]
    for f in files:
        assert not (_imports(f) & FORBIDDEN), f"{f.name} imports {_imports(f) & FORBIDDEN}"


def test_full_integration_with_every_rule_firing_never_touches_an_llm(world, monkeypatch):
    env, w = world

    def forbidden(*a, **k):
        raise AssertionError("an LLM was called by the consistency engine")

    for name in ("chat", "_chat_ollama", "_chat_openai"):
        monkeypatch.setattr(llm_client, name, forbidden)
    people = [person("Alice", eye_color="blue", age="40", status="dead"), person("Bob"), person("Carl")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Alice", "ENEMY_OF", "Bob"), rel("Alice", "FATHER_OF", "Carl")]))
    later = [person("Alice", eye_color="green", age="30", status="alive"), person("Bob"), person("Carl")]
    integrate(env, w["world_id"], w["runs"][2], chapter_data(later, [rel("Alice", "FRIEND_OF", "Bob"), rel("Bob", "FATHER_OF", "Carl")]))

    rules = sorted(c["explanation"].split("]")[0][1:] for c in contradictions(env, w["world_id"]))
    assert rules == ["AGE_MONOTONIC", "DEAD_THEN_ALIVE", "IMMUTABLE_FACT",
                     "RELATIONSHIP_INCOMPATIBLE", "RELATIONSHIP_SINGLE_SOURCE"]
