"""Tests for FastAPI endpoints (Phase 1)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import Job


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def test_app():
    """Create a fresh FastAPI app with an in-memory test database."""
    # Create in-memory DB with StaticPool so it persists across connections
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    # Import app and override its get_db dependency
    from src.main import app, get_db

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield app, TestSession
    app.dependency_overrides.clear()


@pytest.fixture
def client(test_app):
    """Create a test HTTP client."""
    app, _ = test_app
    return TestClient(app)


@pytest.fixture
def seeded_client(test_app):
    """Create a test client with seeded data."""
    app, TestSession = test_app
    session = TestSession()
    jobs = [
        Job(title="Backend Engineer", company="Acme", url="https://acme.com/1", source="linkedin", match_score=90.0, status="NEW"),
        Job(title="Frontend Dev", company="Beta", url="https://beta.com/1", source="indeed", match_score=60.0, status="NEW"),
        Job(title="DevOps Engineer", company="Gamma", url="https://gamma.com/1", source="linkedin", match_score=75.0, status="APPLIED"),
    ]
    session.add_all(jobs)
    session.commit()
    session.close()
    return TestClient(app)


# ── Health Check Tests ───────────────────────────────────────

class TestHealthCheck:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "ATS Optimizer" in data["app"]


# ── Job Endpoint Tests ───────────────────────────────────────

class TestJobEndpoints:
    def test_list_jobs_empty(self, client):
        response = client.get("/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["jobs"] == []

    def test_list_jobs_with_data(self, seeded_client):
        response = seeded_client.get("/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    def test_list_jobs_filter_by_status(self, seeded_client):
        response = seeded_client.get("/jobs?status=APPLIED")
        data = response.json()
        assert data["total"] == 1
        assert data["jobs"][0]["title"] == "DevOps Engineer"

    def test_list_jobs_filter_by_source(self, seeded_client):
        response = seeded_client.get("/jobs?source=indeed")
        data = response.json()
        assert data["total"] == 1

    def test_list_jobs_filter_by_min_score(self, seeded_client):
        response = seeded_client.get("/jobs?min_score=75")
        data = response.json()
        assert data["total"] == 2  # 90 and 75

    def test_get_job_by_id(self, seeded_client):
        jobs = seeded_client.get("/jobs").json()["jobs"]
        job_id = jobs[0]["id"]

        response = seeded_client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["id"] == job_id

    def test_get_job_not_found(self, client):
        response = client.get("/jobs/999")
        assert response.status_code == 404

    def test_update_job_status(self, seeded_client):
        jobs = seeded_client.get("/jobs").json()["jobs"]
        job_id = jobs[0]["id"]

        response = seeded_client.patch(f"/jobs/{job_id}", json={"status": "SKIPPED"})
        assert response.status_code == 200
        assert response.json()["status"] == "SKIPPED"

    def test_update_job_notes(self, seeded_client):
        jobs = seeded_client.get("/jobs").json()["jobs"]
        job_id = jobs[0]["id"]

        response = seeded_client.patch(f"/jobs/{job_id}", json={"notes": "Interesting role"})
        assert response.status_code == 200
        assert response.json()["id"] == job_id


# ── Analysis Endpoint Tests ──────────────────────────────────

class TestAnalysisEndpoints:
    def test_analyze_stub(self, client):
        """Stubbed analysis endpoint should return a valid response."""
        response = client.post(
            "/analyze/score",
            json={
                "resume_text": "Python developer with 5 years experience",
                "job_description": "Looking for a Python backend engineer",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "overall_score" in data
        assert "breakdown" in data
        assert "suggestions" in data
