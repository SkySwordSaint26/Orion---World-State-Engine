"""Phase 1D: runs always end in a valid terminal state, jobs roll up correctly, nothing raises unbound errors."""
import pytest

from app.models.processing_job import ProcessingJob
from app.services.consistency_service import ConsistencyService
from app.workers.tasks import extraction_task
from app.workers.tasks.job_update_task import update_job_progress


def test_failure_before_extraction_run_exists_fails_job_without_unbound_errors(phase1_env):
    env = phase1_env
    env.install_fake_extractor()
    data = env.make_world("A", chapters=1)
    bogus = {**data["runs"][1], "run_id": "does-not-exist"}

    result = env.execute(data["world_id"], data["job_id"], bogus)

    assert result["status"] == "failed" and "ExtractionRun does-not-exist not found" in result["error"]
    job = env.job(data["job_id"])
    assert job["status"] == "failed" and "not found" in job["error"] and job["completed_at"] is not None
    assert env.run(data["runs"][1]["run_id"])[0] == "pending"  # the real run was never touched
    assert env.extract_calls == []


def test_failure_when_neither_run_nor_job_exist_does_not_raise(phase1_env):
    env = phase1_env
    result = extraction_task.execute_chapter_extraction(
        world_id="w", job_id="missing-job", extraction_run_id="missing-run",
        chapter_id="c", chapter_version_id="v"
    )
    assert result["status"] == "failed"


def test_failure_to_open_a_database_session_is_reported_not_raised(phase1_env, monkeypatch):
    def broken_session():
        raise ConnectionError("db down")

    monkeypatch.setattr(extraction_task, "SessionLocal", broken_session)
    result = extraction_task.execute_chapter_extraction("w", "j", "r", "c", "v")
    assert result["status"] == "failed" and "db down" in result["error"]


def test_failure_during_extraction_marks_run_and_job_failed(phase1_env):
    env = phase1_env
    env.install_fake_extractor()
    env.extract_fail.add(("A", 1))
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "failed"
    status, error = env.run(data["runs"][1]["run_id"])
    assert status == "failed" and "simulated extraction failure" in error
    job = env.job(data["job_id"])
    assert job["status"] == "failed" and "simulated extraction failure" in job["error"]
    assert job["completed"] == 0 and job["completed_at"] is not None


def test_failure_during_integration_marks_run_and_job_failed(phase1_env, monkeypatch):
    env = phase1_env
    env.install_fake_extractor()
    monkeypatch.setattr(ConsistencyService, "run_checks", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("integration exploded")))
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "failed"
    assert env.run(data["runs"][1]["run_id"])[0] == "failed"
    assert env.job(data["job_id"])["status"] == "failed"
    assert env.world_rows(data["world_id"])["entities"] == 0


def test_success_marks_run_and_single_chapter_job_done(phase1_env):
    env = phase1_env
    env.install_fake_extractor()
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "success"
    assert env.run(data["runs"][1]["run_id"]) == ("done", None)
    job = env.job(data["job_id"])
    assert job["status"] == "done" and job["completed"] == 1 and job["total"] == 1 and job["completed_at"] is not None


def test_multi_chapter_progress_is_a_recount_and_reaches_done_only_at_the_end(phase1_env):
    env = phase1_env
    env.install_fake_extractor()
    data = env.make_world("A", chapters=3)
    observed = []
    for chapter in (1, 2, 3):
        assert env.execute(data["world_id"], data["job_id"], data["runs"][chapter])["status"] == "success"
        job = env.job(data["job_id"])
        observed.append((job["completed"], job["status"]))

    assert observed == [(1, "processing"), (2, "processing"), (3, "done")]

    # re-running the rollup (e.g. duplicate status task) changes nothing: recount, not increment
    for _ in range(3):
        update_job_progress(data["job_id"])
    assert env.job(data["job_id"])["completed"] == 3


def test_failed_middle_chapter_means_job_never_reports_done(phase1_env):
    env = phase1_env
    env.install_fake_extractor()
    env.extract_fail.add(("A", 2))
    data = env.make_world("A", chapters=3)

    assert env.execute(data["world_id"], data["job_id"], data["runs"][1])["status"] == "success"
    assert env.execute(data["world_id"], data["job_id"], data["runs"][2])["status"] == "failed"
    assert env.execute(data["world_id"], data["job_id"], data["runs"][3])["status"] == "failed"  # blocked by chapter 2

    job = env.job(data["job_id"])
    assert job["status"] == "failed" and job["completed"] == 1
    assert env.integration_order == [1]


def test_rerunning_a_finished_run_is_skipped_and_never_integrates_twice(phase1_env):
    env = phase1_env
    env.install_fake_extractor()
    data = env.make_world("A", chapters=1)
    assert env.execute(data["world_id"], data["job_id"], data["runs"][1])["status"] == "success"
    rows = env.world_rows(data["world_id"])

    again = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert again["status"] == "skipped"
    assert env.world_rows(data["world_id"]) == rows
    assert env.integration_order == [1]
    assert env.run(data["runs"][1]["run_id"])[0] == "done"


def test_a_late_failure_after_commit_cannot_flip_a_done_run_to_failed(phase1_env, monkeypatch):
    env = phase1_env
    env.install_fake_extractor()
    data = env.make_world("A", chapters=1)
    monkeypatch.setattr(extraction_task, "update_job_progress", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rollup broke")))

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "success"
    assert env.run(data["runs"][1]["run_id"])[0] == "done"
    assert env.world_rows(data["world_id"])["entities"] == 2
