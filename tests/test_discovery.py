"""Tests for Phase 5: Job Discovery (Drivers, Dedup, Scoring)."""

import pytest
import asyncio

from src.automation.drivers.base import DiscoveredJob, SearchConfig
from src.automation.drivers.linkedin import LinkedInDriver
from src.automation.drivers.indeed import IndeedDriver
from src.discovery.deduplicator import Deduplicator, is_duplicate
from src.discovery.scorer import JobProfileScorer
from src.profile.manager import CandidateProfile


# ── Sample Data ──────────────────────────────────────────────

SAMPLE_PROFILE_DATA = {
    "personal_info": {"full_name": "Jane Doe"},
    "summaries": [{"target_role": "Backend Engineer", "text": "Experienced backend engineer."}],
    "skills": [
        {
            "category": "Languages",
            "items": [
                {"name": "Python", "proficiency": "Expert", "years": 6},
                {"name": "JavaScript", "proficiency": "Advanced", "years": 4},
            ],
        },
        {
            "category": "Frameworks",
            "items": [
                {"name": "FastAPI", "proficiency": "Expert", "years": 3},
                {"name": "Django", "proficiency": "Advanced", "years": 4},
            ],
        },
        {
            "category": "Tools",
            "items": [
                {"name": "Docker", "proficiency": "Advanced", "years": 4},
                {"name": "PostgreSQL", "proficiency": "Advanced", "years": 5},
                {"name": "Redis", "proficiency": "Advanced", "years": 3},
            ],
        },
    ],
    "experience": [
        {
            "company": "TechCorp",
            "title": "Senior Backend Engineer",
            "start_date": "2022-03",
            "end_date": None,
            "bullets": [
                {"text": "Built event pipeline", "tags": ["Python", "Kafka"]},
                {"text": "Led FastAPI migration", "tags": ["FastAPI", "microservices"]},
            ],
        },
    ],
    "education": [],
    "certifications": [],
    "projects": [
        {"name": "CLI Tool", "tech_stack": ["Python", "Click", "Docker"]},
    ],
    "qa_bank": [],
}


@pytest.fixture
def profile():
    return CandidateProfile(SAMPLE_PROFILE_DATA)


# ── Portal Driver Tests ─────────────────────────────────────

class TestLinkedInDriver:
    def test_driver_name(self):
        driver = LinkedInDriver()
        assert driver.driver_name() == "linkedin"

    def test_search_returns_jobs(self):
        driver = LinkedInDriver()
        config = SearchConfig(keywords=["python", "backend"], location="SF")
        jobs = asyncio.get_event_loop().run_until_complete(driver.search(config))
        assert len(jobs) > 0
        assert all(isinstance(j, DiscoveredJob) for j in jobs)
        assert all(j.source == "linkedin" for j in jobs)

    def test_get_job_details(self):
        driver = LinkedInDriver()
        job = asyncio.get_event_loop().run_until_complete(
            driver.get_job_details("https://linkedin.com/jobs/view/123")
        )
        assert isinstance(job, DiscoveredJob)
        assert job.source == "linkedin"

    def test_apply_returns_result(self):
        driver = LinkedInDriver()
        job = DiscoveredJob(
            title="Engineer", company="Acme", url="https://example.com", source="linkedin"
        )
        result = asyncio.get_event_loop().run_until_complete(
            driver.apply(job, "/path/to/resume.pdf")
        )
        assert "status" in result

    def test_available_without_creds(self):
        driver = LinkedInDriver()
        available = asyncio.get_event_loop().run_until_complete(driver.is_available())
        assert available is False

    def test_available_with_creds(self):
        driver = LinkedInDriver(email="test@test.com", password="pass")
        available = asyncio.get_event_loop().run_until_complete(driver.is_available())
        assert available is True


class TestIndeedDriver:
    def test_driver_name(self):
        driver = IndeedDriver()
        assert driver.driver_name() == "indeed"

    def test_search_returns_jobs(self):
        driver = IndeedDriver()
        config = SearchConfig(keywords=["python"])
        jobs = asyncio.get_event_loop().run_until_complete(driver.search(config))
        assert len(jobs) > 0
        assert all(j.source == "indeed" for j in jobs)

    def test_search_uses_keywords(self):
        driver = IndeedDriver()
        config = SearchConfig(keywords=["data", "engineer"])
        jobs = asyncio.get_event_loop().run_until_complete(driver.search(config))
        # Mock should incorporate keywords in title
        assert any("data" in j.title.lower() for j in jobs)


# ── Deduplication Tests ──────────────────────────────────────

class TestDeduplicator:
    def test_no_duplicates(self):
        dedup = Deduplicator()
        jobs = [
            DiscoveredJob(title="Backend Engineer", company="Acme", url="https://acme.com/1", source="linkedin"),
            DiscoveredJob(title="Frontend Dev", company="Beta", url="https://beta.com/1", source="indeed"),
        ]
        unique, dupes = dedup.deduplicate(jobs)
        assert len(unique) == 2
        assert len(dupes) == 0

    def test_url_duplicate(self):
        dedup = Deduplicator()
        jobs = [
            DiscoveredJob(title="Engineer", company="Acme", url="https://acme.com/job/1", source="linkedin"),
            DiscoveredJob(title="Engineer", company="Acme", url="https://acme.com/job/1", source="indeed"),
        ]
        unique, dupes = dedup.deduplicate(jobs)
        assert len(unique) == 1
        assert len(dupes) == 1

    def test_url_duplicate_with_existing(self):
        dedup = Deduplicator()
        jobs = [
            DiscoveredJob(title="Engineer", company="Acme", url="https://acme.com/job/1", source="linkedin"),
        ]
        existing = {"https://acme.com/job/1"}
        unique, dupes = dedup.deduplicate(jobs, existing_urls=existing)
        assert len(unique) == 0
        assert len(dupes) == 1

    def test_fuzzy_title_duplicate(self):
        dedup = Deduplicator(fuzzy_threshold=80)
        jobs = [
            DiscoveredJob(title="Senior Backend Engineer", company="Acme Corp", url="https://linkedin.com/1", source="linkedin"),
            DiscoveredJob(title="Sr. Backend Engineer", company="Acme Corp", url="https://indeed.com/1", source="indeed"),
        ]
        unique, dupes = dedup.deduplicate(jobs)
        # These should be considered duplicates due to fuzzy matching
        assert len(unique) + len(dupes) == 2

    def test_url_normalization(self):
        dedup = Deduplicator()
        jobs = [
            DiscoveredJob(title="A", company="B", url="https://acme.com/job/1/", source="a"),
            DiscoveredJob(title="A", company="B", url="https://Acme.com/job/1", source="a"),
        ]
        unique, dupes = dedup.deduplicate(jobs)
        assert len(unique) == 1

    def test_is_duplicate_helper(self):
        job = DiscoveredJob(title="X", company="Y", url="https://x.com/1", source="s")
        assert is_duplicate(job, {"https://x.com/1"}) is True
        assert is_duplicate(job, {"https://other.com"}) is False


# ── Job-Profile Scorer Tests ────────────────────────────────

class TestJobProfileScorer:
    def test_high_match(self, profile):
        scorer = JobProfileScorer()
        job = DiscoveredJob(
            title="Backend Engineer",
            company="TechCorp",
            url="https://example.com",
            source="linkedin",
            description_text="""
                We need a Senior Backend Engineer with:
                - Python expertise
                - FastAPI or Django experience
                - PostgreSQL and Redis
                - Docker containers
            """,
        )
        score = scorer.score(job, profile)
        assert score >= 30  # Should match reasonably well

    def test_low_match(self, profile):
        scorer = JobProfileScorer()
        job = DiscoveredJob(
            title="iOS Developer",
            company="MobileCo",
            url="https://example.com",
            source="linkedin",
            description_text="""
                We need an iOS Developer with:
                - Swift programming
                - UIKit and SwiftUI
                - Core Data
                - Xcode proficiency
            """,
        )
        score = scorer.score(job, profile)
        assert score < 30  # Should NOT match well

    def test_high_vs_low_match(self, profile):
        scorer = JobProfileScorer()
        backend_job = DiscoveredJob(
            title="Backend Engineer", company="A", url="https://a.com", source="x",
            description_text="Python FastAPI Django PostgreSQL Redis Docker experience required",
        )
        ios_job = DiscoveredJob(
            title="iOS Dev", company="B", url="https://b.com", source="x",
            description_text="Swift UIKit SwiftUI Core Data Xcode experience required",
        )
        backend_score = scorer.score(backend_job, profile)
        ios_score = scorer.score(ios_job, profile)
        assert backend_score > ios_score

    def test_empty_description(self, profile):
        scorer = JobProfileScorer()
        job = DiscoveredJob(
            title="Unknown", company="Unknown", url="https://x.com", source="x",
            description_text="",
        )
        assert scorer.score(job, profile) == 0.0

    def test_score_and_rank(self, profile):
        scorer = JobProfileScorer()
        jobs = [
            DiscoveredJob(title="iOS", company="A", url="https://a.com", source="x",
                          description_text="Swift UIKit needed"),
            DiscoveredJob(title="Backend", company="B", url="https://b.com", source="x",
                          description_text="Python Django PostgreSQL FastAPI needed"),
            DiscoveredJob(title="Full Stack", company="C", url="https://c.com", source="x",
                          description_text="Python React Docker needed"),
        ]
        ranked = scorer.score_and_rank(jobs, profile)
        # Backend job should rank highest
        assert ranked[0][0].title == "Backend"
        assert ranked[0][1] >= ranked[-1][1]

    def test_min_score_filter(self, profile):
        scorer = JobProfileScorer()
        jobs = [
            DiscoveredJob(title="iOS", company="A", url="https://a.com", source="x",
                          description_text="Swift UIKit iOS development"),
            DiscoveredJob(title="Backend", company="B", url="https://b.com", source="x",
                          description_text="Python Django PostgreSQL FastAPI needed"),
        ]
        ranked = scorer.score_and_rank(jobs, profile, min_score=25.0)
        # iOS job should be filtered out
        assert all(score >= 25.0 for _, score in ranked)
