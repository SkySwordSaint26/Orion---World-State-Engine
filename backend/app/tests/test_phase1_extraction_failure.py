"""Phase 1A: a failed extraction run must fail the extraction run and job, and write no world state."""
import subprocess

from app.pipeline import extractor

ZERO = {"entities": 0, "aliases": 0, "mentions": 0, "facts": 0, "fact_versions": 0, "relationships": 0,
        "relationship_versions": 0, "events": 0, "event_participants": 0, "contradictions": 0}


def test_extractor_failure_fails_run_and_job_and_writes_no_world_state(phase1_env, monkeypatch):
    env = phase1_env
    monkeypatch.setattr(extractor.subprocess, "run",
                        lambda args, **kw: subprocess.CompletedProcess(args, 1, "", "CUDA out of memory"))
    data = env.make_world("A", chapters=1)

    result = env.execute(data["world_id"], data["job_id"], data["runs"][1])

    assert result["status"] == "failed"
    status, error = env.run(data["runs"][1]["run_id"])
    assert status == "failed" and "Extraction failed on chapter 1: CUDA out of memory" in error
    job = env.job(data["job_id"])
    assert job["status"] == "failed" and job["completed"] == 0
    assert env.world_rows(data["world_id"]) == ZERO
