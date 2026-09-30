"""Phase 1C at the HTTP boundary: upload and edit dispatch ONE ordered job, not one task per chapter."""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_world, get_db
from app.config.settings import settings
from app.main import app
from app.models.user import User
from app.models.world import World
from app.workers.tasks.extraction_task import run_extraction_job_task


@pytest.fixture
def api(phase1_env):
    env = phase1_env
    with env.Session() as s:
        user = User(id="u-phase1", email="phase1@example.com", password_hash="x")
        world = World(name="API World", user_id=user.id)
        s.add_all([user, world])
        s.commit()
        world_id = world.id

    def override_db():
        db = env.Session()
        try:
            yield db
        finally:
            db.close()

    def override_world():
        with env.Session() as s:
            w = s.get(World, world_id)
            s.expunge(w)
            return w

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_world] = override_world
    yield env, world_id, TestClient(app)
    app.dependency_overrides.clear()


def _manuscript(chapters=3):
    return "\n\n".join(f"Chapter {n}: T{n}\nAlice walked. [A]" for n in range(1, chapters + 1)).encode()


def test_upload_runs_one_ordered_background_job(api, monkeypatch):
    env, world_id, client = api
    env.install_fake_extractor()
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "background")

    resp = client.post(f"/api/v1/worlds/{world_id}/manuscripts", files={"file": ("book.txt", _manuscript(), "text/plain")})

    assert resp.status_code == 202
    assert env.integration_order == [1, 2, 3]
    job = env.job(resp.json()["job_id"])
    assert job["status"] == "done" and job["completed"] == 3


def test_upload_returns_503_and_fails_the_job_when_celery_is_unreachable(api, monkeypatch):
    env, world_id, client = api
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "celery")
    monkeypatch.setattr(run_extraction_job_task, "apply_async", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("redis down")))

    resp = client.post(f"/api/v1/worlds/{world_id}/manuscripts", files={"file": ("book.txt", _manuscript(2), "text/plain")})

    assert resp.status_code == 503
    with env.Session() as s:
        from app.models.processing_job import ProcessingJob
        job = s.query(ProcessingJob).filter(ProcessingJob.world_id == world_id).one()
        assert job.status == "failed" and "redis down" in job.error_message


def test_chapter_edit_dispatches_a_single_chapter_job(api, monkeypatch):
    env, world_id, client = api
    env.install_fake_extractor()
    monkeypatch.setattr(settings, "EXTRACTION_EXECUTOR", "background")
    upload = client.post(f"/api/v1/worlds/{world_id}/manuscripts", files={"file": ("book.txt", _manuscript(2), "text/plain")})
    runs = env.runs_by_chapter(upload.json()["job_id"])
    env.integration_order.clear()

    resp = client.put(f"/api/v1/worlds/{world_id}/chapters/{runs[2]['chapter_id']}", json={"content": "Chapter 2: T2 edited\nAlice ran. [A]"})

    assert resp.status_code == 202 and resp.json()["status"] == "re_extraction_queued"
    assert env.integration_order == [2]
    assert env.job(resp.json()["job_id"])["status"] == "done"
