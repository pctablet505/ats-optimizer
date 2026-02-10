"""Tests for Phase 3: ATS Analysis Engine."""

import pytest

from src.analyzer.keywords import (
    Keyword,
    extract_keywords,
    extract_keywords_with_importance,
    normalize_keyword,
)
from src.analyzer.scorer import ATSScorer, ScoreResult
from src.analyzer.suggestions import generate_suggestions
from src.llm.provider import StubProvider, get_llm_provider


# ── Sample texts ─────────────────────────────────────────────

SAMPLE_JD = """
Senior Backend Engineer — Acme Corp

We are looking for a Senior Backend Engineer to join our platform team.

Requirements:
- 5+ years of experience with Python
- Strong experience with FastAPI or Django
- PostgreSQL and Redis experience
- Familiarity with Docker and Kubernetes
- Experience with microservices architecture
- CI/CD pipelines (GitHub Actions, Jenkins)
- Strong understanding of REST APIs
- Experience with message queues (Kafka, RabbitMQ)

Nice to have:
- AWS or GCP experience
- Machine Learning exposure
- GraphQL experience

Responsibilities:
- Design and build scalable backend services
- Write clean, well-tested code
- Participate in code reviews and architectural decisions
- Mentor junior engineers
"""

GOOD_RESUME = """
Jane Doe
jane@email.com | +1-555-0100 | San Francisco, CA
linkedin.com/in/janedoe | github.com/janedoe

Professional Summary
Experienced backend engineer with 6 years building scalable Python services.
Expert in FastAPI, Django, PostgreSQL, and Redis. Passionate about clean
architecture and reliable distributed systems.

Technical Skills
Python, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS,
Kafka, REST APIs, Git, GitHub Actions, CI/CD, Microservices

Professional Experience

Senior Backend Engineer — TechCorp Inc. (2022 - Present)
• Designed and built a high-throughput event processing pipeline handling
  50K events/second using Python, Kafka, and PostgreSQL
• Led migration from monolithic Django app to FastAPI microservices,
  reducing P99 latency by 40%
• Implemented Redis-based caching layer that reduced database load by 60%
• Mentored 3 junior engineers through code reviews and pair programming

Software Engineer — StartupXYZ (2019 - 2022)
• Built RESTful APIs serving 10K daily active users using Django and PostgreSQL
• Developed automated deployment pipeline using Docker, GitHub Actions, and AWS
• Created real-time notification system using WebSockets and Redis Pub/Sub
• Wrote comprehensive test suites achieving 90%+ code coverage using pytest

Education
B.S. Computer Science — UC Berkeley (2019)

Certifications
- AWS Solutions Architect Associate (2023)
"""

WEAK_RESUME = """
John Smith
Looking for a job.

I have some experience with computers. I worked at a company before.
I know how to use Microsoft Word and Excel. I am a hard worker and
team player. References available upon request.
"""


# ── Keyword Extraction Tests ────────────────────────────────

class TestKeywordExtraction:
    def test_extract_from_jd(self):
        result = extract_keywords(SAMPLE_JD)
        names = [k.canonical for k in result.keywords]
        # Should find major technical terms
        assert any("Python" in n for n in names)
        assert any("Docker" in n for n in names)

    def test_extract_empty_text(self):
        result = extract_keywords("")
        assert len(result.keywords) == 0

    def test_normalize_keyword(self):
        assert normalize_keyword("python") == "Python"
        assert normalize_keyword("js") == "JavaScript"
        assert normalize_keyword("k8s") == "Kubernetes"
        assert normalize_keyword("postgresql") == "PostgreSQL"
        assert normalize_keyword("aws") == "AWS"

    def test_extract_with_importance(self):
        result = extract_keywords_with_importance(SAMPLE_JD)
        assert len(result) > 0
        # Each item should have required keys
        for kw in result:
            assert "keyword" in kw
            assert "importance" in kw
            assert kw["importance"] in ("high", "medium", "low")

    def test_skill_aliases(self):
        text = "We need someone who knows k8s, nodejs, and postgresql"
        result = extract_keywords(text)
        names = [k.canonical for k in result.keywords]
        assert "Kubernetes" in names
        assert "Node.js" in names
        assert "PostgreSQL" in names

    def test_max_keywords_limit(self):
        result = extract_keywords(SAMPLE_JD, max_keywords=5)
        assert len(result.keywords) <= 5


# ── ATS Scorer Tests ─────────────────────────────────────────

class TestATSScorer:
    def setup_method(self):
        self.scorer = ATSScorer()

    def test_good_resume_scores_high(self):
        result = self.scorer.score(GOOD_RESUME, SAMPLE_JD)
        assert result.overall_score >= 50  # Good resume should score well
        assert result.breakdown.keyword_match >= 50
        assert result.breakdown.section_completeness >= 50

    def test_weak_resume_scores_low(self):
        result = self.scorer.score(WEAK_RESUME, SAMPLE_JD)
        assert result.overall_score < 50  # Weak resume should score poorly

    def test_good_vs_weak(self):
        good = self.scorer.score(GOOD_RESUME, SAMPLE_JD)
        weak = self.scorer.score(WEAK_RESUME, SAMPLE_JD)
        assert good.overall_score > weak.overall_score

    def test_score_result_has_all_fields(self):
        result = self.scorer.score(GOOD_RESUME, SAMPLE_JD)
        assert hasattr(result.breakdown, "keyword_match")
        assert hasattr(result.breakdown, "section_completeness")
        assert hasattr(result.breakdown, "keyword_density")
        assert hasattr(result.breakdown, "experience_relevance")
        assert hasattr(result.breakdown, "formatting")
        assert isinstance(result.matched_keywords, list)
        assert isinstance(result.missing_keywords, list)

    def test_score_range(self):
        result = self.scorer.score(GOOD_RESUME, SAMPLE_JD)
        assert 0 <= result.overall_score <= 100
        assert 0 <= result.breakdown.keyword_match <= 100
        assert 0 <= result.breakdown.formatting <= 100

    def test_identical_texts_score_high(self):
        """A resume that IS the JD should score very high on keywords."""
        result = self.scorer.score(SAMPLE_JD, SAMPLE_JD)
        assert result.breakdown.keyword_match >= 80

    def test_to_dict(self):
        result = self.scorer.score(GOOD_RESUME, SAMPLE_JD)
        d = result.to_dict()
        assert "overall_score" in d
        assert "breakdown" in d
        assert "matched_keywords" in d
        assert "missing_keywords" in d

    def test_formatting_detects_issues(self):
        result = self.scorer.score(WEAK_RESUME, SAMPLE_JD)
        # Weak resume should have formatting issues
        assert len(result.formatting_issues) > 0

    def test_empty_resume(self):
        result = self.scorer.score("", SAMPLE_JD)
        assert result.overall_score < 30

    def test_empty_jd(self):
        result = self.scorer.score(GOOD_RESUME, "")
        # With empty JD, keyword match should be high (nothing to match against)
        assert result.breakdown.keyword_match == 100


# ── Suggestion Engine Tests ──────────────────────────────────

class TestSuggestionEngine:
    def setup_method(self):
        self.scorer = ATSScorer()

    def test_good_resume_gets_fewer_suggestions(self):
        result = self.scorer.score(GOOD_RESUME, SAMPLE_JD)
        suggestions = generate_suggestions(result)
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0  # Always at least one (overall assessment)

    def test_weak_resume_gets_critical_suggestions(self):
        result = self.scorer.score(WEAK_RESUME, SAMPLE_JD)
        suggestions = generate_suggestions(result)
        # Should have critical keyword suggestions
        critical = [s for s in suggestions if "CRITICAL" in s or "🔴" in s]
        assert len(critical) > 0

    def test_suggestions_are_strings(self):
        result = self.scorer.score(GOOD_RESUME, SAMPLE_JD)
        suggestions = generate_suggestions(result)
        for s in suggestions:
            assert isinstance(s, str)
            assert len(s) > 10  # Meaningful suggestion


# ── LLM Provider Tests ───────────────────────────────────────

class TestLLMProvider:
    def test_stub_provider_generates_text(self):
        provider = StubProvider()
        response = provider.generate("Write a professional summary")
        assert response.text
        assert "stub" in response.text.lower() or "stub" in response.provider

    def test_stub_provider_is_available(self):
        provider = StubProvider()
        assert provider.is_available() is True

    def test_stub_detects_summary_prompt(self):
        provider = StubProvider()
        response = provider.generate("Write a professional summary for a backend engineer")
        assert "software engineer" in response.text.lower() or "stub" in response.text.lower()

    def test_stub_detects_question_prompt(self):
        provider = StubProvider()
        response = provider.generate("Answer the following question: years of experience?")
        assert "stub" in response.text.lower()

    def test_get_llm_provider_default_is_stub(self):
        provider = get_llm_provider()
        assert isinstance(provider, StubProvider)


# ── Integration: API Endpoint Test ───────────────────────────

class TestAnalyzeAPI:
    def test_analyze_returns_real_score(self):
        """The /analyze/score endpoint should return real scores now."""
        from fastapi.testclient import TestClient
        from src.main import app

        client = TestClient(app)
        response = client.post(
            "/analyze/score",
            json={
                "resume_text": GOOD_RESUME,
                "job_description": SAMPLE_JD,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["overall_score"] > 0  # Should no longer return 0
        assert len(data["breakdown"]) == 5
        assert len(data["suggestions"]) > 0
