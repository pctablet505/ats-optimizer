"""Tests for Phase 1: DB models, config, and API health check."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import Config, load_config
from src.database import Base, init_db
from src.models import ApplicationLog, Job, Resume, SearchRun


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def engine():
    """Create an in-memory SQLite database for testing."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Create a new DB session for a test."""
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    sess = Session()
    yield sess
    sess.close()


# ── Config Tests ─────────────────────────────────────────────

class TestConfig:
    def test_default_config(self):
        """Config should load with sensible defaults."""
        config = Config()
        assert config.app.name == "ATS Optimizer"
        assert config.database.url == "sqlite:///data/ats_optimizer.db"
        assert config.llm.provider == "stub"
        assert config.scoring.min_ats_score == 70

    def test_load_config_from_file(self, tmp_path):
        """Config should load from a YAML file."""
        yaml_file = tmp_path / "test_config.yaml"
        yaml_file.write_text(
            "app:\n  name: 'Test App'\ndatabase:\n  url: 'sqlite:///test.db'\n"
        )
        config = load_config(yaml_file)
        assert config.app.name == "Test App"
        assert config.database.url == "sqlite:///test.db"
        # Other sections should use defaults
        assert config.llm.provider == "stub"

    def test_load_config_missing_file(self, tmp_path):
        """Config should return defaults if file doesn't exist."""
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.app.name == "ATS Optimizer"


# ── Model Tests ──────────────────────────────────────────────

class TestJobModel:
    def test_create_job(self, session):
        """Should create a Job and persist it."""
        job = Job(
            title="Backend Engineer",
            company="Acme Corp",
            location="Remote",
            url="https://example.com/job/123",
            source="linkedin",
            match_score=85.5,
        )
        session.add(job)
        session.commit()

        fetched = session.query(Job).first()
        assert fetched is not None
        assert fetched.title == "Backend Engineer"
        assert fetched.company == "Acme Corp"
        assert fetched.status == "NEW"
        assert fetched.match_score == 85.5
        assert fetched.discovered_at is not None

    def test_job_default_status(self, session):
        """New jobs should default to status=NEW."""
        job = Job(title="SWE", company="X", url="https://x.com/1", source="indeed")
        session.add(job)
        session.commit()
        assert session.query(Job).first().status == "NEW"

    def test_job_unique_url(self, session):
        """Two jobs with the same URL should violate unique constraint."""
        j1 = Job(title="A", company="B", url="https://same.com", source="linkedin")
        j2 = Job(title="C", company="D", url="https://same.com", source="indeed")
        session.add(j1)
        session.commit()
        session.add(j2)
        with pytest.raises(Exception):
            session.commit()


class TestResumeModel:
    def test_create_resume(self, session):
        """Should create a Resume for a job."""
        job = Job(title="SWE", company="X", url="https://x.com/1", source="linkedin")
        session.add(job)
        session.commit()

        resume = Resume(
            name="Tailored Resume",
            target_job_id=job.id,
            file_path="/data/resumes/resume_1.pdf",
            ats_score=82.0,
        )
        session.add(resume)
        session.commit()

        fetched = session.query(Resume).first()
        assert fetched.name == "Tailored Resume"
        assert fetched.ats_score == 82.0
        assert fetched.job.title == "SWE"

    def test_job_resume_relationship(self, session):
        """Job.resumes should return related resumes."""
        job = Job(title="SWE", company="X", url="https://x.com/2", source="linkedin")
        session.add(job)
        session.commit()

        r1 = Resume(name="v1", target_job_id=job.id)
        r2 = Resume(name="v2", target_job_id=job.id)
        session.add_all([r1, r2])
        session.commit()

        session.refresh(job)
        assert len(job.resumes) == 2


class TestApplicationLogModel:
    def test_create_log(self, session):
        """Should log an application attempt."""
        job = Job(title="SWE", company="X", url="https://x.com/3", source="linkedin")
        session.add(job)
        session.commit()

        log = ApplicationLog(
            job_id=job.id,
            portal="linkedin",
            status="SUCCESS",
            duration_seconds=45.2,
            questions_answered=[{"q": "Years of exp?", "a": "5", "source": "qa_bank"}],
        )
        session.add(log)
        session.commit()

        fetched = session.query(ApplicationLog).first()
        assert fetched.status == "SUCCESS"
        assert fetched.duration_seconds == 45.2
        assert fetched.questions_answered[0]["q"] == "Years of exp?"


class TestSearchRunModel:
    def test_create_search_run(self, session):
        """Should record a search run."""
        run = SearchRun(
            portal="linkedin",
            search_query="backend engineer python",
            jobs_found=25,
            jobs_new=18,
        )
        session.add(run)
        session.commit()

        fetched = session.query(SearchRun).first()
        assert fetched.portal == "linkedin"
        assert fetched.jobs_found == 25
        assert fetched.jobs_new == 18
