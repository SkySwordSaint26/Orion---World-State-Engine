"""Phase 1B: a chapter integrates all-or-nothing in ONE transaction owned by the extraction task."""
import pytest

from app.models.extraction_run import ExtractionRun
from app.repositories.event_repo import EventRepository
from app.services.consistency_service import ConsistencyService
from app.services.world_state_service import WorldStateService
from app.models.world import World


def test_integration_does_not_commit_on_its_own(phase1_env):
    env = phase1_env
    with env.Session() as s:
        world = World(name="W")
        s.add(world)
        s.commit()
        world_id = world.id

        WorldStateService(s).integrate_extraction_result(world_id, {
            "entities": [{"canonical_name": "Alice", "type": "character", "attributes": {"age": "30"}}],
            "relationships": [], "events": [],
        })
        # Visible inside the transaction, invisible to any other connection until the caller commits.
        assert s.query(__import__("app.models.entity", fromlist=["Entity"]).Entity).count() == 1
        assert env.world_rows(world_id)["entities"] == 0

        s.rollback()
    assert env.world_rows(world_id)["entities"] == 0


def test_successful_chapter_commits_all_expected_rows(phase1_env):
    env = phase1_env
    env.install_fake_extractor()
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "success"
    rows = env.world_rows(data["world_id"])
    assert rows["entities"] == 2 and rows["mentions"] == 2
    assert rows["facts"] == 2 and rows["fact_versions"] == 2
    assert rows["relationships"] == 1 and rows["relationship_versions"] == 1
    assert rows["events"] == 2 and rows["event_participants"] == 3
    assert env.run(data["runs"][1]["run_id"])[0] == "done"


def _committed_two_chapter_world(env):
    env.install_fake_extractor()
    data = env.make_world("A", chapters=2)
    assert env.execute(data["world_id"], data["job_id"], data["runs"][1])["status"] == "success"
    return data


def test_failure_halfway_through_integration_leaves_no_partial_chapter_state(phase1_env, monkeypatch):
    env = phase1_env
    data = _committed_two_chapter_world(env)
    world_id = data["world_id"]
    before = env.world_rows(world_id)
    assert before["events"] == 2

    # Chapter 2 creates its first event, then the second event creation blows up mid-integration.
    original = EventRepository.create_event
    calls = []

    def flaky(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("disk full while writing event 2")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(EventRepository, "create_event", flaky)
    result = env.execute(world_id, data["job_id"], data["runs"][2])

    assert result["status"] == "failed" and "disk full" in result["error"]
    assert len(calls) == 2  # the failure really happened after entities/facts/relationships/1 event were written
    # rollback removed entities, facts, relationships and events created by the failed integration ...
    assert env.world_rows(world_id) == before
    # ... including the in-place status change that superseded the previous version of a fact:
    assert env.fact_statuses(world_id, "SharedA", "rank") == [("Rank1", "ACTIVE")]
    status, error = env.run(data["runs"][2]["run_id"])
    assert status == "failed" and "disk full" in error


def test_failure_in_consistency_stage_rolls_back_everything(phase1_env, monkeypatch):
    env = phase1_env
    data = _committed_two_chapter_world(env)
    before = env.world_rows(data["world_id"])

    monkeypatch.setattr(ConsistencyService, "run_checks", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rule engine crashed")))
    result = env.execute(data["world_id"], data["job_id"], data["runs"][2])

    assert result["status"] == "failed"
    assert env.world_rows(data["world_id"]) == before


def test_previously_committed_state_is_untouched_by_a_failed_later_chapter(phase1_env, monkeypatch):
    env = phase1_env
    data = _committed_two_chapter_world(env)
    world_id = data["world_id"]
    before_facts = env.fact_statuses(world_id, "SharedA", "rank")
    before_age = env.fact_statuses(world_id, "HeroAB", "age")  # chapter 1's hero
    assert before_age == [("31", "ACTIVE")]

    monkeypatch.setattr(ConsistencyService, "run_checks", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    env.execute(world_id, data["job_id"], data["runs"][2])

    assert env.fact_statuses(world_id, "SharedA", "rank") == before_facts
    assert env.fact_statuses(world_id, "HeroAB", "age") == before_age
    assert env.fact_statuses(world_id, "HeroAC", "age") == []  # chapter 2's hero never appeared


def test_successful_second_chapter_commits_and_supersedes_previous_version(phase1_env):
    env = phase1_env
    data = _committed_two_chapter_world(env)
    result = env.execute(data["world_id"], data["job_id"], data["runs"][2])

    assert result["status"] == "success"
    assert env.fact_statuses(data["world_id"], "SharedA", "rank") == [("Rank1", "SUPERSEDED"), ("Rank2", "ACTIVE")]
