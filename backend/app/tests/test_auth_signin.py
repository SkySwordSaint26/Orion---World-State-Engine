"""Real authentication routes with an isolated database, never the author's account data."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.database import Base
from app.main import app


def test_registration_login_and_existing_account_errors_round_trip():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def isolated_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    credentials = {"email": "auth-flow@example.com", "password": "auth-test-password"}
    try:
        client = TestClient(app)
        created = client.post("/api/v1/auth/register", json=credentials)
        assert created.status_code == 201
        duplicate = client.post("/api/v1/auth/register", json=credentials)
        assert duplicate.status_code == 400 and "already exists" in duplicate.json()["detail"]
        assert client.post("/api/v1/auth/login", json={**credentials, "password": "incorrect"}).status_code == 401
        login = client.post("/api/v1/auth/login", json=credentials)
        assert login.status_code == 200
        current = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
        assert current.status_code == 200
        assert current.json()["id"] == created.json()["id"]
        assert current.json()["email"] == credentials["email"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
