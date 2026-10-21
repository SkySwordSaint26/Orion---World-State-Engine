"""Author cancellation, historical text restoration and trait persistence."""
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.chapter_version import ChapterVersion
from app.models.extraction_run import ExtractionRun
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.models.world import World
from app.pipeline import extractor
from app.pipeline.cancellation import cancel_requested, ExtractionCancelled
from app.services.chapter_service import ChapterService
from app.services.job_service import JobService
from app.workers.tasks.extraction_task import run_extraction_job
from app.workers.tasks import extraction_task
from app.workers.tasks.job_update_task import update_job_progress


@pytest.fixture
def studio(phase1_env, monkeypatch):
    env = phase1_env
    author_id = "studio-author"
    worlds = [env.make_world(tag, chapters=2) for tag in ("A", "B")]
    with env.Session() as db:
        db.add_all([User(id=author_id, email="studio@example.com", password_hash="x"),
                    User(id="other-author", email="other@example.com", password_hash="x")])
        for world, owner in zip(worlds, [author_id, "other-author"]):
            db.get(World, world["world_id"]).user_id = owner
        db.commit()

    def current_user():
        with env.Session() as db:
            user = db.get(User, author_id)
            db.expunge(user)
            return user

    def session():
        with env.Session() as db:
            yield db

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = session
    monkeypatch.setattr("app.api.v1.routes.chapters.dispatch_extraction_job", lambda *args: None)
    try:
        yield env, worlds, TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_cancel_queued_job_is_persistent_idempotent_and_scoped(studio):
    env, (world, foreign), client = studio
    path = f"/api/v1/jobs/{world['job_id']}/cancel"
    assert client.post(path).json()["status"] == "cancelled"
    assert client.post(path).json()["status"] == "cancelled"
    assert client.get(path.removesuffix("cancel") + "status").json()["status"] == "cancelled"
    assert client.post(f"/api/v1/jobs/{foreign['job_id']}/cancel").status_code == 404
    assert run_extraction_job(world["job_id"])["status"] == "cancelled"
    with env.Session() as db:
        update_job_progress(world["job_id"], db)
        assert db.get(ProcessingJob, world["job_id"]).status == "cancelled"
        assert {r.status for r in db.query(ExtractionRun).filter_by(processing_job_id=world["job_id"])} == {"cancelled"}
    assert env.world_rows(world["world_id"])["entities"] == 0


def test_cancel_during_extraction_keeps_completed_chapters_and_discards_active_result(studio, monkeypatch):
    env, (world, _), client = studio
    env.install_fake_extractor()
    original = extractor.extract_chapter

    def cancel_second(text, chapter):
        if chapter == 2:
            assert client.post(f"/api/v1/jobs/{world['job_id']}/cancel").status_code == 200
        return original(text, chapter)

    monkeypatch.setattr(extractor, "extract_chapter", cancel_second)
    assert run_extraction_job(world["job_id"])["status"] == "cancelled"
    assert env.integration_order == [1]
    with env.Session() as db:
        job = db.get(ProcessingJob, world["job_id"])
        assert job.status == "cancelled" and job.chapters_completed == 1


def test_cancel_between_chapter_commit_and_progress_rollup_counts_completed_work(studio, monkeypatch):
    env, (world, _), client = studio
    env.install_fake_extractor()

    def cancel_before_rollup(job_id, db):
        assert client.post(f"/api/v1/jobs/{job_id}/cancel").json()["progress_current"] == 1
        update_job_progress(job_id, db)

    monkeypatch.setattr(extraction_task, "update_job_progress", cancel_before_rollup)
    assert run_extraction_job(world["job_id"])["status"] == "cancelled"
    assert extraction_task.abort_pending_runs(world["job_id"], "A late failure") == 0
    assert env.integration_order == [1]
    with env.Session() as db:
        job = db.get(ProcessingJob, world["job_id"])
        assert job.status == "cancelled" and job.chapters_completed == 1
        assert {run.status for run in db.query(ExtractionRun).filter_by(processing_job_id=job.id)} == {"done", "cancelled"}


def test_cancellation_kills_and_reaps_the_extractor_subprocess(monkeypatch):
    calls = []

    class Process:
        args = ["extractor"]
        returncode = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def communicate(self, timeout=None):
            calls.append("communicate")
            if timeout is not None:
                raise subprocess.TimeoutExpired(self.args, timeout)
            return "", ""

        def kill(self):
            calls.append("kill")

    monkeypatch.setattr(extractor.subprocess, "Popen", lambda *args, **kwargs: Process())
    token = cancel_requested.set(lambda: len(calls) > 0)
    try:
        with pytest.raises(ExtractionCancelled):
            extractor.run_extractor("A chapter", 1)
    finally:
        cancel_requested.reset(token)
    assert calls == ["communicate", "kill", "communicate"]


def test_cancellation_stops_a_real_child_process_without_loading_models(tmp_path, monkeypatch):
    (tmp_path / "extractor.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(extractor, "EXTRACTOR_DIR", tmp_path)
    monkeypatch.setattr(extractor, "EXTRACTOR_PYTHON", sys.executable)
    processes = []
    started = []
    popen = subprocess.Popen

    def spawn(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        started.append(time.monotonic())
        return process

    monkeypatch.setattr(extractor.subprocess, "Popen", spawn)
    token = cancel_requested.set(lambda: bool(started) and time.monotonic() - started[0] >= 0.2)
    try:
        with pytest.raises(ExtractionCancelled):
            extractor.run_extractor("An isolated test chapter.", 1)
    finally:
        cancel_requested.reset(token)
    assert len(processes) == 1 and processes[0].poll() is not None


def test_restoring_history_appends_a_version_and_proposes_instead_of_overwriting(studio):
    env, (world, foreign), client = studio
    chapter = world["runs"][1]["chapter_id"]
    old = world["runs"][1]["chapter_version_id"]
    base = f"/api/v1/worlds/{world['world_id']}/chapters/{chapter}"
    original = client.get(f"{base}/versions/{old}").json()["content"]
    with env.Session() as db:
        ChapterService(db).update_chapter_content(chapter, "The changed chapter. [A]")
    response = client.post(f"{base}/versions/{old}/restore")
    assert response.status_code == 202
    versions = client.get(f"{base}/versions").json()
    assert [v["version_number"] for v in versions] == [3, 2, 1]
    assert sum(v["is_current"] for v in versions) == 1
    latest = client.get(base).json()
    assert latest["content"] == original and latest["latest_version"]["version_number"] == 3
    assert client.get(f"{base}/versions/{old}").json()["content"] == original
    assert env.world_rows(world["world_id"])["entities"] == 0
    with env.Session() as db:
        assert db.get(ProcessingJob, response.json()["job_id"]).job_type == "RE_EXTRACTION"
        version = db.get(ChapterVersion, old)
        assert not version.is_current
    foreign_version = foreign["runs"][1]["chapter_version_id"]
    assert client.get(f"{base}/versions/{foreign_version}").status_code == 404
    assert client.post(f"{base}/versions/{foreign_version}/restore").status_code == 404
    assert client.get(base.replace(world["world_id"], foreign["world_id"])).status_code == 404


def test_traits_round_trip_and_epub_is_rejected_before_storage(studio):
    _, (world, _), client = studio
    base = f"/api/v1/worlds/{world['world_id']}"
    entity = client.post(f"{base}/entities", json={"canonical_name": "Mara", "entity_type": "character"}).json()
    path = f"{base}/entities/{entity['id']}"
    assert client.put(path, json={"attributes": {"traits": ["Patient", "Observant"]}}).status_code == 200
    facts = client.get(path).json()["facts"]
    assert next(f for f in facts if f["property_name"] == "traits")["current_version"]["value"] == ["Patient", "Observant"]
    assert client.put(path, json={"attributes": {"traits": []}}).status_code == 200
    assert client.post(f"{base}/manuscripts", files={"file": ("book.epub", b"PK archive", "application/epub+zip")}).status_code == 415
