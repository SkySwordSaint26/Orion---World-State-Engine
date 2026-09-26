"""Phase 1C: within a manuscript chapter N never integrates before chapter N-1; worlds stay independent."""
from datetime import datetime, timedelta

import pytest
from fastapi import BackgroundTasks

from app.config.settings import settings
from app.models.extraction_run import ExtractionRun
from app.workers import dispatch
from app.workers.dispatch import ExtractionDispatchError, dispatch_extraction_job
from app.workers.tasks import extraction_task
from app.workers.tasks.extraction_task import run_extraction_job, run_extraction_job_task


def _reverse_submission_order(env, job_id):
    """Makes the run rows look as if chapter 3 was submitted first and chapter 1 last."""
    runs = env.runs_by_chapter(job_id)
    base = datetime.utcnow()
    with env.Session() as s:
        for offset, chapter in enumerate(sorted(runs, reverse=True)):
            s.get(ExtractionRun, runs[chapter]["run_id"]).created_at = base + timedelta(seconds=offset)
        s.commit()


def test_chapters_submitted_in_reverse_order_still_integrate_in_chapter_order(phase1_env):
    env = phase1_env
    env.install_fake_llm()
    data = env.make_world("A", chapters=3)
    _reverse_submission_order(env, data["job_id"])

    result = run_extraction_job(data["job_id"])

    assert result["status"] == "success"
    assert env.integration_order == [1, 2, 3]
    assert [c for _, c in env.llm_calls] == [1, 2, 3]
    assert env.job(data["job_id"])["status"] == "done"
    # the versioned fact history reflects chapter order too
    assert [v for v, _ in env.fact_statuses(data["world_id"], "SharedA", "rank")] == ["Rank1", "Rank2", "Rank3"]


def test_chapter_two_cannot_modify_world_state_before_chapter_one_completed(phase1_env):
    env = phase1_env
    env.install_fake_llm()
    data = env.make_world("A", chapters=2)

    # chapter 1's run exists but has not run (pending); someone executes chapter 2 directly
    result = env.execute(data["world_id"], data["job_id"], data["runs"][2])

    assert result["status"] == "failed"
    assert "blocked by: chapter 1" in result["error"]
    assert env.integration_order == []
    assert env.world_rows(data["world_id"])["entities"] == 0
    assert env.run(data["runs"][2]["run_id"])[0] == "failed"
    assert env.run(data["runs"][1]["run_id"])[0] == "pending"  # chapter 1 untouched and still runnable

    # once chapter 1 succeeds, a fresh chapter-2 run may integrate
    assert env.execute(data["world_id"], data["job_id"], data["runs"][1])["status"] == "success"
    assert env.integration_order == [1]


def test_failed_chapter_one_stops_the_job_and_chapter_two_is_never_integrated(phase1_env):
    env = phase1_env
    env.install_fake_llm()
    env.llm_fail.add(("A", 1))
    data = env.make_world("A", chapters=3)

    result = run_extraction_job(data["job_id"])

    assert result == {"status": "failed", "failed_chapter": 1, "skipped_runs": 2}
    assert env.integration_order == []
    assert env.llm_calls == [("A", 1)]  # chapters 2 and 3 were not even sent to the LLM
    assert env.world_rows(data["world_id"])["entities"] == 0
    assert env.run(data["runs"][1]["run_id"])[0] == "failed"
    for chapter in (2, 3):
        status, error = env.run(data["runs"][chapter]["run_id"])
        assert status == "failed" and "chapter 1 did not complete" in error
    job = env.job(data["job_id"])
    assert job["status"] == "failed" and job["completed"] == 0


def test_direct_chapter_two_execution_after_failed_chapter_one_is_blocked(phase1_env):
    env = phase1_env
    env.install_fake_llm()
    env.llm_fail.add(("A", 1))
    data = env.make_world("A", chapters=2)

    assert env.execute(data["world_id"], data["job_id"], data["runs"][1])["status"] == "failed"
    result = env.execute(data["world_id"], data["job_id"], data["runs"][2])

    assert result["status"] == "failed"
    assert "chapter 1 (latest run is 'failed')" in result["error"]
    assert env.integration_order == []
    assert env.world_rows(data["world_id"])["entities"] == 0


def test_separate_worlds_are_not_serialized_or_blocked_by_each_other(phase1_env):
    env = phase1_env
    env.install_fake_llm()
    env.llm_fail.add(("A", 1))  # world A's chapter 1 fails
    world_a = env.make_world("A", chapters=2)
    world_b = env.make_world("B", chapters=2)

    assert run_extraction_job(world_a["job_id"])["status"] == "failed"
    assert run_extraction_job(world_b["job_id"])["status"] == "success"

    assert env.job(world_a["job_id"])["status"] == "failed"
    assert env.job(world_b["job_id"])["status"] == "done"
    assert env.world_rows(world_a["world_id"])["entities"] == 0
    assert env.world_rows(world_b["world_id"])["entities"] == 3  # 2 heroes + 1 shared (reused across chapters)
    # world B's chapter numbers overlap world A's; world A's failed chapter 1 did not gate world B
    assert [t for t, _ in env.llm_calls] == ["A", "B", "B"]


def test_each_job_is_its_own_dispatch_unit_so_worlds_are_not_chained(phase1_env, monkeypatch):
    env = phase1_env
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "background")
    world_a = env.make_world("A", chapters=2)
    world_b = env.make_world("B", chapters=2)

    tasks = BackgroundTasks()
    assert dispatch_extraction_job(world_a["job_id"], tasks) == "background"
    assert dispatch_extraction_job(world_b["job_id"], tasks) == "background"

    # one runner per job (never one task per chapter), and jobs share no lock or chain
    assert [(t.func, t.args) for t in tasks.tasks] == [
        (run_extraction_job, (world_a["job_id"],)),
        (run_extraction_job, (world_b["job_id"],)),
    ]


def test_celery_executor_enqueues_one_ordered_task_per_job(phase1_env, monkeypatch):
    env = phase1_env
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "celery")
    published = []
    monkeypatch.setattr(run_extraction_job_task, "apply_async", lambda args=None, **kw: published.append(args))
    data = env.make_world("A", chapters=3)

    assert dispatch_extraction_job(data["job_id"]) == "celery"
    assert published == [[data["job_id"]]]


def test_celery_task_runs_the_ordered_job(phase1_env):
    env = phase1_env
    env.install_fake_llm()
    data = env.make_world("A", chapters=3)
    _reverse_submission_order(env, data["job_id"])

    outcome = run_extraction_job_task.apply(args=[data["job_id"]])  # eager: no broker needed

    assert outcome.get() == {"status": "success", "chapters": 3}
    assert env.integration_order == [1, 2, 3]


def test_celery_publish_failure_fails_the_job_and_does_not_fall_back_silently(phase1_env, monkeypatch):
    env = phase1_env
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "celery")

    def broker_down(*a, **k):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(run_extraction_job_task, "apply_async", broker_down)
    data = env.make_world("A", chapters=2)

    with pytest.raises(ExtractionDispatchError):
        dispatch_extraction_job(data["job_id"], BackgroundTasks())

    job = env.job(data["job_id"])
    assert job["status"] == "failed" and "redis unreachable" in job["error"]
    assert all(env.run(info["run_id"])[0] == "failed" for info in data["runs"].values())


def test_unknown_executor_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "carrier-pigeon")
    with pytest.raises(ExtractionDispatchError):
        dispatch_extraction_job("job-id", BackgroundTasks())
