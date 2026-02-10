"""Tests for Phase 6: Application Automation."""

import pytest
import asyncio

from src.automation.question_answerer import QuestionAnswerer
from src.automation.human_simulator import HumanSimulator
from src.automation.captcha_handler import CaptchaHandler, CaptchaDetection
from src.automation.orchestrator import Orchestrator, PipelineResult
from src.automation.drivers.base import DiscoveredJob, SearchConfig
from src.automation.drivers.linkedin import LinkedInDriver
from src.automation.drivers.indeed import IndeedDriver
from src.profile.manager import CandidateProfile


# ── Sample Data ──────────────────────────────────────────────

PROFILE_DATA = {
    "personal_info": {
        "full_name": "Jane Doe",
        "email": "jane@email.com",
        "phone": "+1-555-0100",
        "location": "San Francisco, CA",
    },
    "summaries": [
        {"target_role": "Backend Engineer", "text": "Experienced backend engineer."},
    ],
    "skills": [
        {"category": "Languages", "items": [
            {"name": "Python", "proficiency": "Expert", "years": 6},
        ]},
    ],
    "experience": [
        {
            "company": "TechCorp",
            "title": "Senior Backend Engineer",
            "start_date": "2022-03",
            "end_date": None,
            "bullets": [
                {"text": "Built event pipeline with Python and Kafka", "tags": ["Python", "Kafka"]},
            ],
        },
    ],
    "education": [
        {"institution": "UC Berkeley", "degree": "B.S. CS", "graduation_date": "2019"},
    ],
    "certifications": [],
    "projects": [],
    "qa_bank": [
        {"question_pattern": "years of experience", "answer": "5"},
        {"question_pattern": "authorized to work", "answer": "Yes"},
        {"question_pattern": "require.*sponsorship|visa", "answer": "No"},
        {"question_pattern": "willing to relocate", "answer": "Yes"},
        {"question_pattern": "salary|compensation", "answer": "Open to discussion"},
        {"question_pattern": "gender|race|ethnicity|veteran|disability", "answer": "Prefer not to say"},
    ],
}


@pytest.fixture
def profile():
    return CandidateProfile(PROFILE_DATA)


# ── Question Answerer Tests ─────────────────────────────────

class TestQuestionAnswerer:
    def test_match_exact_pattern(self, profile):
        qa = QuestionAnswerer(profile)
        result = qa.answer("How many years of experience do you have?")
        assert result["answer"] == "5"
        assert result["source"] == "qa_bank"
        assert result["confidence"] > 0.9

    def test_match_regex_pattern(self, profile):
        qa = QuestionAnswerer(profile)
        result = qa.answer("Do you require visa sponsorship?")
        assert result["answer"] == "No"
        assert result["source"] == "qa_bank"

    def test_match_salary_question(self, profile):
        qa = QuestionAnswerer(profile)
        result = qa.answer("What is your expected compensation?")
        assert result["answer"] == "Open to discussion"

    def test_match_eeo_question(self, profile):
        qa = QuestionAnswerer(profile)
        result = qa.answer("What is your gender?")
        assert result["answer"] == "Prefer not to say"

    def test_unmatched_falls_to_llm_or_manual(self, profile):
        qa = QuestionAnswerer(profile)
        result = qa.answer("What is your favorite programming paradigm?")
        # Should fall through to LLM (stub) or manual
        assert result["source"] in ("llm", "manual")

    def test_batch_answers(self, profile):
        qa = QuestionAnswerer(profile)
        questions = [
            "How many years of experience?",
            "Are you authorized to work?",
            "What color is the sky?",
        ]
        answers = qa.answer_batch(questions)
        assert len(answers) == 3
        assert answers[0]["answer"] == "5"
        assert answers[1]["answer"] == "Yes"

    def test_empty_qa_bank(self):
        empty_profile = CandidateProfile({
            "personal_info": {"full_name": "Test"},
            "qa_bank": [],
        })
        qa = QuestionAnswerer(empty_profile)
        result = qa.answer("years of experience")
        assert result["source"] in ("llm", "manual")


# ── Human Simulator Tests ───────────────────────────────────

class TestHumanSimulator:
    def test_init_defaults(self):
        sim = HumanSimulator()
        assert sim.chars_per_second > 0
        assert sim.min_pause > 0
        assert sim.max_pause > sim.min_pause

    def test_custom_speed(self):
        sim = HumanSimulator(typing_speed_wpm=120)
        assert sim.chars_per_second > HumanSimulator().chars_per_second

    def test_get_random_delay(self):
        sim = HumanSimulator(min_pause_ms=100, max_pause_ms=500)
        delay = sim.get_random_delay()
        assert 0.1 <= delay <= 0.5

    def test_random_delay_varies(self):
        sim = HumanSimulator()
        delays = [sim.get_random_delay() for _ in range(10)]
        # Should not all be the same
        assert len(set(delays)) > 1


# ── CAPTCHA Handler Tests ───────────────────────────────────

class TestCaptchaHandler:
    def test_detect_recaptcha(self):
        handler = CaptchaHandler()
        html = '<div class="g-recaptcha" data-sitekey="abc"></div>'
        result = handler.detect(html)
        assert result.detected is True
        assert result.captcha_type == "recaptcha"

    def test_detect_hcaptcha(self):
        handler = CaptchaHandler()
        html = '<div class="h-captcha" data-sitekey="abc"></div>'
        result = handler.detect(html)
        assert result.detected is True
        assert result.captcha_type == "hcaptcha"

    def test_detect_cloudflare(self):
        handler = CaptchaHandler()
        html = '<div class="cf-turnstile"></div>'
        result = handler.detect(html)
        assert result.detected is True
        assert result.captcha_type == "cloudflare"

    def test_detect_generic_verify(self):
        handler = CaptchaHandler()
        html = '<p>Please verify you are human</p>'
        result = handler.detect(html)
        assert result.detected is True

    def test_no_captcha(self):
        handler = CaptchaHandler()
        html = '<html><body><h1>Job Application</h1><form>...</form></body></html>'
        result = handler.detect(html)
        assert result.detected is False

    def test_detection_result_message(self):
        handler = CaptchaHandler()
        html = '<div class="g-recaptcha"></div>'
        result = handler.detect(html)
        assert "manually" in result.message.lower()


# ── Orchestrator Tests ───────────────────────────────────────

class TestOrchestrator:
    def test_pipeline_discovery_only(self, profile):
        """Test pipeline with discovery but no auto-apply."""
        drivers = [IndeedDriver()]
        orch = Orchestrator(
            drivers=drivers,
            profile=profile,
            min_score=0.0,
            auto_apply=False,
        )
        config = SearchConfig(keywords=["python", "backend"])
        result = asyncio.get_event_loop().run_until_complete(orch.run(config))

        assert isinstance(result, PipelineResult)
        assert result.jobs_discovered > 0
        assert result.jobs_new > 0
        assert result.resumes_generated > 0
        assert result.applications_submitted == 0  # auto_apply is False

    def test_pipeline_with_auto_apply(self, profile):
        """Test full pipeline with auto-apply enabled."""
        drivers = [IndeedDriver()]
        orch = Orchestrator(
            drivers=drivers,
            profile=profile,
            min_score=0.0,
            auto_apply=True,
        )
        config = SearchConfig(keywords=["python"])
        result = asyncio.get_event_loop().run_until_complete(orch.run(config))

        assert result.jobs_discovered > 0
        assert result.applications_submitted > 0  # Stubs succeed

    def test_pipeline_dedup(self, profile):
        """Existing URLs should be filtered out."""
        drivers = [IndeedDriver()]
        orch = Orchestrator(
            drivers=drivers,
            profile=profile,
            existing_urls={"https://indeed.com/viewjob?jk=mock-i001"},
            min_score=0.0,
        )
        config = SearchConfig(keywords=["python"])
        result = asyncio.get_event_loop().run_until_complete(orch.run(config))

        assert result.jobs_duplicates >= 1

    def test_pipeline_min_score_filter(self, profile):
        """High min_score should filter out low-match jobs."""
        drivers = [IndeedDriver()]
        orch = Orchestrator(
            drivers=drivers,
            profile=profile,
            min_score=99.0,  # Very high threshold
        )
        config = SearchConfig(keywords=["swift", "ios"])  # Not in profile
        result = asyncio.get_event_loop().run_until_complete(orch.run(config))

        # Most/all jobs should be filtered by score
        assert result.resumes_generated <= result.jobs_scored

    def test_pipeline_multiple_drivers(self, profile):
        """Test with multiple drivers."""
        drivers = [LinkedInDriver(email="a@b.com", password="x"), IndeedDriver()]
        orch = Orchestrator(
            drivers=drivers,
            profile=profile,
            min_score=0.0,
        )
        config = SearchConfig(keywords=["python"])
        result = asyncio.get_event_loop().run_until_complete(orch.run(config))

        # Should discover from both drivers
        assert result.jobs_discovered >= 4  # 2 from each

    def test_pipeline_result_has_no_errors(self, profile):
        """Normal run should complete without errors."""
        drivers = [IndeedDriver()]
        orch = Orchestrator(drivers=drivers, profile=profile, min_score=0.0)
        config = SearchConfig(keywords=["python"])
        result = asyncio.get_event_loop().run_until_complete(orch.run(config))
        assert len(result.errors) == 0
