"""An author's decision survives fresh extraction versions and the next review."""
import pytest

from app.api.deps import get_current_user
from app.config.settings import settings
from app.main import app
from app.models.user import User
from app.pipeline import extractor
from app.services.consistency_service import ConsistencyService
from app.services.entity_service import EntityService
from app.services.proposal_service import ProposalService
from app.tests.test_phase1_api import api  # noqa: F401
from app.tests.test_phase2_integration import (  # noqa: F401
    chapter_data, contradictions, integrate, person, rel, temporal_chapter, world,
)


def fact_decision(env, w, choice="old", status="RESOLVED"):
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Arin", eye_color="dark brown")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Arin", eye_color="green")]))
    [conflict] = contradictions(env, w["world_id"])
    with env.Session() as session:
        ConsistencyService(session).resolve_contradiction(
            conflict["id"], status=status,
            preferred_fact_version_id=conflict[f"{choice}_fact_version_id"] if choice else None,
        )
    return conflict


def review(env, w, extraction):
    before = env.world_rows(w["world_id"])
    with env.Session() as session:
        result = ProposalService(session).build(
            w["world_id"], "review-again", w["runs"][2]["chapter_id"], 2, extraction,
        )
    assert env.world_rows(w["world_id"]) == before
    return result["proposals"]


@pytest.mark.parametrize("choice,replayed,accepted", [
    ("old", "green", "dark brown"),
    ("new", "dark brown", "green"),
])
def test_fact_decision_survives_new_versions_in_the_same_and_later_chapters(world, choice, replayed, accepted):
    env, w = world
    fact_decision(env, w, choice)

    for chapter in (2, 3):
        result = integrate(env, w["world_id"], w["runs"][chapter], chapter_data([person("Arin", eye_color=replayed)]))
        assert result["contradictions_found"] == 0
    assert [c["status"] for c in contradictions(env, w["world_id"])] == ["RESOLVED"]
    assert {value for value, status in env.fact_statuses(w["world_id"], "Arin", "eye_color")
            if status == "ACTIVE"} == {accepted}


@pytest.mark.parametrize("choice,replayed", [("old", " GREEN "), ("new", "DARK BROWN")])
def test_review_does_not_offer_a_decided_fact_again(world, choice, replayed):
    env, w = world
    fact_decision(env, w, choice)

    proposals = review(env, w, chapter_data([person("Arin", eye_color=replayed)]))

    assert not [p for p in proposals if p["kind"] == "fact" and p["change"] != "known"]


@pytest.mark.parametrize("status", ["RESOLVED", "DISMISSED"])
def test_acknowledged_or_dismissed_claim_is_not_offered_again(world, status):
    env, w = world
    fact_decision(env, w, choice=None, status=status)

    proposals = review(env, w, chapter_data([person("Arin", eye_color="green")]))

    assert not [p for p in proposals if p["kind"] == "fact" and p["change"] != "known"]


def test_a_new_value_still_proposes_and_generates_a_conflict(world):
    env, w = world
    fact_decision(env, w)

    proposals = review(env, w, chapter_data([person("Arin", eye_color="blue")]))
    [fact] = [p for p in proposals if p["kind"] == "fact"]
    assert fact["change"] == "changed" and fact["proposed"]["value"] == "blue"
    result = integrate(env, w["world_id"], w["runs"][3], chapter_data([person("Arin", eye_color="blue")]))
    assert result["contradictions_found"] == 1
    assert sorted(c["status"] for c in contradictions(env, w["world_id"])) == ["DETECTED", "RESOLVED"]


def test_the_same_values_for_another_character_are_still_checked(world):
    env, w = world
    fact_decision(env, w)
    integrate(env, w["world_id"], w["runs"][1], chapter_data([person("Tara", eye_color="dark brown")]))

    result = integrate(env, w["world_id"], w["runs"][2], chapter_data([person("Tara", eye_color="green")]))

    assert result["contradictions_found"] == 1


def test_a_decision_in_another_world_does_not_hide_a_conflict(world):
    env, w = world
    fact_decision(env, w)
    other = env.make_world("other", chapters=2)
    integrate(env, other["world_id"], other["runs"][1], chapter_data([person("Arin", eye_color="dark brown")]))

    result = integrate(env, other["world_id"], other["runs"][2], chapter_data([person("Arin", eye_color="green")]))

    assert result["contradictions_found"] == 1


def test_reopening_a_decision_restores_the_review_proposal(world):
    env, w = world
    conflict = fact_decision(env, w)
    with env.Session() as session:
        ConsistencyService(session).resolve_contradiction(conflict["id"], status="DETECTED")

    proposals = review(env, w, chapter_data([person("Arin", eye_color="green")]))

    assert any(p["kind"] == "fact" and p["change"] == "changed" for p in proposals)


def test_applying_an_old_review_cannot_recreate_a_decided_fact_conflict(world):
    env, w = world
    fact_decision(env, w)
    with env.Session() as session:
        entity = EntityService(session).list_entities(w["world_id"])[0]
        version = EntityService(session).add_fact(entity.id, "eye_color", "green")
        assert version.status == "CONTRADICTED"

    assert [c["status"] for c in contradictions(env, w["world_id"])] == ["RESOLVED"]
    assert {value for value, status in env.fact_statuses(w["world_id"], "Arin", "eye_color")
            if status == "ACTIVE"} == {"dark brown"}


def relationship_decision(env, w, choice):
    people = [person("Arin"), person("Tara")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Arin", "ENEMY_OF", "Tara")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data(people, [rel("Arin", "FRIEND_OF", "Tara")]))
    [conflict] = contradictions(env, w["world_id"])
    with env.Session() as session:
        ConsistencyService(session).resolve_contradiction(
            conflict["id"], preferred_relationship_version_id=conflict[f"{choice}_relationship_version_id"],
        )


@pytest.mark.parametrize("choice,replayed", [("old", "FRIEND_OF"), ("new", "ENEMY_OF")])
def test_relationship_decision_survives_new_extraction_versions(world, choice, replayed):
    env, w = world
    relationship_decision(env, w, choice)

    result = integrate(env, w["world_id"], w["runs"][3], chapter_data([], [rel("Arin", replayed, "Tara")]))

    assert result["contradictions_found"] == 0
    assert [c["status"] for c in contradictions(env, w["world_id"])] == ["RESOLVED"]


@pytest.mark.parametrize("choice,replayed", [("old", "FRIEND_OF"), ("new", "ENEMY_OF")])
def test_review_does_not_offer_a_decided_relationship_again(world, choice, replayed):
    env, w = world
    relationship_decision(env, w, choice)

    proposals = review(env, w, chapter_data([], [rel("Arin", replayed, "Tara")]))

    assert not [p for p in proposals if p["kind"] == "relationship" and p["change"] != "known"]


def test_a_relationship_decision_does_not_suppress_the_opposite_direction(world):
    env, w = world
    relationship_decision(env, w, "old")
    integrate(env, w["world_id"], w["runs"][1], chapter_data([], [rel("Tara", "ENEMY_OF", "Arin")]))
    proposals = review(env, w, chapter_data([], [rel("Tara", "FRIEND_OF", "Arin")]))
    assert any(p["kind"] == "relationship" and p["change"] == "changed" for p in proposals)

    result = integrate(env, w["world_id"], w["runs"][2], chapter_data([], [rel("Tara", "FRIEND_OF", "Arin")]))

    assert result["contradictions_found"] == 1


@pytest.mark.parametrize("choice,replayed", [("old", "Agastya"), ("new", "Devendra")])
def test_parentage_decision_is_respected_even_when_the_rejected_relationship_is_not_active(world, choice, replayed):
    env, w = world
    people = [person("Arin"), person("Devendra"), person("Agastya")]
    integrate(env, w["world_id"], w["runs"][1], chapter_data(people, [rel("Devendra", "FATHER_OF", "Arin")]))
    integrate(env, w["world_id"], w["runs"][2], chapter_data(people, [rel("Agastya", "FATHER_OF", "Arin")]))
    [conflict] = contradictions(env, w["world_id"])
    with env.Session() as session:
        ConsistencyService(session).resolve_contradiction(
            conflict["id"], preferred_relationship_version_id=conflict[f"{choice}_relationship_version_id"],
        )

    proposals = review(env, w, chapter_data([], [rel(replayed, "FATHER_OF", "Arin")]))
    assert not [p for p in proposals if p["kind"] == "relationship" and p["change"] != "known"]
    result = integrate(env, w["world_id"], w["runs"][3], chapter_data([], [rel(replayed, "FATHER_OF", "Arin")]))
    assert result["contradictions_found"] == 0


def test_a_temporal_decision_applies_to_its_chapter_but_not_another_chapters_events(world):
    env, w = world
    data = temporal_chapter([("e1", "BEFORE", "e2"), ("e2", "BEFORE", "e1")])
    integrate(env, w["world_id"], w["runs"][1], data)
    [conflict] = contradictions(env, w["world_id"])
    with env.Session() as session:
        ConsistencyService(session).resolve_contradiction(conflict["id"])

    assert integrate(env, w["world_id"], w["runs"][1], data)["contradictions_found"] == 0
    assert integrate(env, w["world_id"], w["runs"][2], data)["contradictions_found"] == 1


@pytest.mark.parametrize("choice,replayed,accepted", [
    ("old", "green", "dark brown"),
    ("new", "dark brown", "green"),
])
def test_resolve_then_reextract_through_the_api_does_not_offer_the_conflict_again(api, monkeypatch, choice, replayed, accepted):
    env, world_id, client = api
    colors = {1: "dark brown", 2: "green"}
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "background")
    monkeypatch.setattr(extractor, "extract_chapter", lambda text, chapter_number, progress=None:
                        chapter_data([person("Arin", eye_color=colors[chapter_number])]))
    app.dependency_overrides[get_current_user] = lambda: User(id="u-phase1", email="phase1@example.com")
    base = f"/api/v1/worlds/{world_id}"
    upload = client.post(f"{base}/manuscripts", files={
        "file": ("arin.txt", b"Chapter 1: Oath\nArin had dark brown eyes.\n\nChapter 2: Test\nArin had green eyes.", "text/plain")})
    assert upload.status_code == 202
    [conflict] = client.get(f"{base}/contradictions").json()
    resolved = client.post(f"{base}/contradictions/{conflict['id']}/resolve", json={
        "status": "RESOLVED", "preferred_fact_version_id": conflict[f"{choice}_fact_version_id"]})
    assert resolved.status_code == 200

    colors[2] = replayed
    chapter_id = env.runs_by_chapter(upload.json()["job_id"])[2]["chapter_id"]
    edit = client.put(f"{base}/chapters/{chapter_id}", json={"content": f"Arin has {replayed} eyes."})
    assert edit.status_code == 202
    proposals = client.get(f"/api/v1/jobs/{edit.json()['job_id']}/proposals")
    assert proposals.status_code == 200
    assert not [p for p in proposals.json()["proposals"] if p["kind"] == "fact" and p["change"] != "known"]
    assert client.get(f"{base}/contradictions?status=DETECTED").json() == []
    assert len(client.get(f"{base}/contradictions?status=RESOLVED").json()) == 1
    assert {value for value, status in env.fact_statuses(world_id, "Arin", "eye_color")
            if status == "ACTIVE"} == {accepted}
