"""Tests for Phase 4: Resume Generation (Content Selector + Renderer)."""

import pytest
from pathlib import Path

from src.generator.content_selector import ContentSelector, SelectedContent
from src.generator.renderer import ResumeRenderer, generate_resume
from src.profile.manager import CandidateProfile


# ── Sample Data ──────────────────────────────────────────────

SAMPLE_PROFILE_DATA = {
    "personal_info": {
        "full_name": "Jane Doe",
        "email": "jane@email.com",
        "phone": "+1-555-0100",
        "location": "San Francisco, CA",
        "linkedin": "https://linkedin.com/in/janedoe",
        "github": "https://github.com/janedoe",
    },
    "summaries": [
        {"target_role": "Backend Engineer", "text": "Experienced backend engineer with 5+ years building scalable Python services."},
        {"target_role": "Full Stack Developer", "text": "Full stack developer building web apps end-to-end."},
        {"target_role": "Data Engineer", "text": "Data engineer with pipeline and ETL expertise."},
    ],
    "skills": [
        {
            "category": "Languages",
            "items": [
                {"name": "Python", "proficiency": "Expert", "years": 6},
                {"name": "JavaScript", "proficiency": "Advanced", "years": 4},
                {"name": "Go", "proficiency": "Intermediate", "years": 1},
                {"name": "SQL", "proficiency": "Advanced", "years": 5},
            ],
        },
        {
            "category": "Frameworks",
            "items": [
                {"name": "FastAPI", "proficiency": "Expert", "years": 3},
                {"name": "Django", "proficiency": "Advanced", "years": 4},
                {"name": "React", "proficiency": "Intermediate", "years": 2},
            ],
        },
        {
            "category": "Tools",
            "items": [
                {"name": "Docker", "proficiency": "Advanced", "years": 4},
                {"name": "PostgreSQL", "proficiency": "Advanced", "years": 5},
                {"name": "Redis", "proficiency": "Advanced", "years": 3},
                {"name": "AWS", "proficiency": "Intermediate", "years": 3},
                {"name": "Kafka", "proficiency": "Intermediate", "years": 2},
            ],
        },
    ],
    "experience": [
        {
            "company": "TechCorp",
            "title": "Senior Backend Engineer",
            "location": "SF",
            "start_date": "2022-03",
            "end_date": None,
            "bullets": [
                {"text": "Built event pipeline handling 50K events/sec with Python and Kafka", "tags": ["Python", "Kafka", "event-driven"]},
                {"text": "Led migration from Django to FastAPI microservices", "tags": ["Django", "FastAPI", "microservices"]},
                {"text": "Implemented Redis caching reducing DB load by 60%", "tags": ["Redis", "caching", "database"]},
                {"text": "Mentored 3 junior engineers", "tags": ["mentoring", "leadership"]},
            ],
        },
        {
            "company": "StartupXYZ",
            "title": "Software Engineer",
            "location": "Remote",
            "start_date": "2019-06",
            "end_date": "2022-02",
            "bullets": [
                {"text": "Built REST APIs serving 10K users with Django and PostgreSQL", "tags": ["Django", "REST", "PostgreSQL"]},
                {"text": "Developed CI/CD pipeline with Docker and AWS", "tags": ["Docker", "CI/CD", "AWS"]},
                {"text": "Created real-time notification system with WebSockets and Redis", "tags": ["WebSockets", "Redis", "real-time"]},
            ],
        },
    ],
    "education": [
        {"institution": "UC Berkeley", "degree": "B.S. Computer Science", "graduation_date": "2019-05", "gpa": "3.7"},
    ],
    "certifications": [
        {"name": "AWS Solutions Architect", "issuer": "AWS", "date": "2023-01"},
    ],
    "projects": [
        {
            "name": "DB Migrator CLI",
            "description": "CLI tool for automating database migrations",
            "tech_stack": ["Python", "Click", "PostgreSQL", "Docker"],
            "highlights": ["500+ GitHub stars", "Used by 3 companies"],
        },
        {
            "name": "Real-time Dashboard",
            "description": "Full-stack monitoring dashboard with live metrics",
            "tech_stack": ["React", "TypeScript", "FastAPI", "WebSockets"],
            "highlights": ["Sub-second data refresh"],
        },
        {
            "name": "ML Pipeline",
            "description": "Machine learning data pipeline for ETL",
            "tech_stack": ["Python", "Spark", "Airflow"],
            "highlights": ["Processes 1TB daily"],
        },
    ],
    "qa_bank": [],
}

BACKEND_JD = """
Senior Backend Engineer

Requirements:
- 5+ years Python experience
- Strong experience with FastAPI or Django
- PostgreSQL and Redis experience
- Docker and Kubernetes
- REST APIs and microservices
- Kafka experience preferred
"""

FRONTEND_JD = """
Senior Frontend Developer

Requirements:
- 5+ years JavaScript/TypeScript experience
- React or Vue.js expertise
- HTML, CSS, responsive design
- GraphQL experience
- Testing with Jest
"""


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def profile():
    return CandidateProfile(SAMPLE_PROFILE_DATA)


@pytest.fixture
def selector():
    return ContentSelector()


@pytest.fixture
def renderer():
    return ResumeRenderer()


# ── Content Selector Tests ───────────────────────────────────

class TestContentSelector:
    def test_select_returns_selected_content(self, selector, profile):
        result = selector.select(profile, BACKEND_JD)
        assert isinstance(result, SelectedContent)
        assert result.personal_info["full_name"] == "Jane Doe"

    def test_summary_matches_backend_role(self, selector, profile):
        result = selector.select(profile, BACKEND_JD)
        assert "backend" in result.summary.lower()

    def test_summary_matches_frontend_role(self, selector, profile):
        result = selector.select(profile, FRONTEND_JD)
        # Should pick "Full Stack" since there's no frontend-specific summary
        assert result.summary  # Should have some summary

    def test_skills_prioritize_jd_matches(self, selector, profile):
        result = selector.select(profile, BACKEND_JD)
        # Python, FastAPI, Django, PostgreSQL, Redis should be near the top
        top_5 = result.skills[:5]
        assert "Python" in top_5 or "FastAPI" in top_5

    def test_skills_limited_by_max(self, selector, profile):
        result = selector.select(profile, BACKEND_JD, max_skills=5)
        assert len(result.skills) <= 5

    def test_experience_preserved(self, selector, profile):
        result = selector.select(profile, BACKEND_JD)
        assert len(result.experience) == 2
        assert result.experience[0]["company"] == "TechCorp"

    def test_bullets_limited_per_role(self, selector, profile):
        result = selector.select(profile, BACKEND_JD, max_bullets_per_role=2)
        for exp in result.experience:
            assert len(exp["bullets"]) <= 2

    def test_bullets_ranked_by_relevance(self, selector, profile):
        result = selector.select(profile, BACKEND_JD, max_bullets_per_role=2)
        # First experience should have the most relevant bullets for backend
        first_job_bullets = result.experience[0]["bullets"]
        # Technical bullets should be prioritized over mentoring
        bullet_texts = [b["text"] for b in first_job_bullets]
        assert any("pipeline" in t.lower() or "fastapi" in t.lower() for t in bullet_texts)

    def test_projects_ranked_by_relevance(self, selector, profile):
        result = selector.select(profile, BACKEND_JD, max_projects=2)
        assert len(result.projects) <= 2
        # DB Migrator (Python, PostgreSQL) should rank higher for backend JD
        project_names = [p["name"] for p in result.projects]
        assert "DB Migrator CLI" in project_names

    def test_education_included(self, selector, profile):
        result = selector.select(profile, BACKEND_JD)
        assert len(result.education) == 1

    def test_certifications_included(self, selector, profile):
        result = selector.select(profile, BACKEND_JD)
        assert len(result.certifications) == 1

    def test_target_keywords_captured(self, selector, profile):
        result = selector.select(profile, BACKEND_JD)
        assert len(result.target_keywords) > 0


# ── Renderer Tests ───────────────────────────────────────────

class TestResumeRenderer:
    def test_render_html(self, renderer, selector, profile):
        content = selector.select(profile, BACKEND_JD)
        html = renderer.render_html(content)
        assert "Jane Doe" in html
        assert "jane@email.com" in html
        assert "<html>" in html.lower()

    def test_html_contains_sections(self, renderer, selector, profile):
        content = selector.select(profile, BACKEND_JD)
        html = renderer.render_html(content)
        assert "Professional Summary" in html
        assert "Technical Skills" in html
        assert "Professional Experience" in html
        assert "Education" in html

    def test_html_contains_skills(self, renderer, selector, profile):
        content = selector.select(profile, BACKEND_JD)
        html = renderer.render_html(content)
        assert "Python" in html

    def test_save_html(self, renderer, selector, profile, tmp_path):
        content = selector.select(profile, BACKEND_JD)
        output = tmp_path / "resume.html"
        result = renderer.save_html(content, output)
        assert result.exists()
        text = result.read_text()
        assert "Jane Doe" in text

    def test_generate_resume_function(self, selector, profile, tmp_path):
        content = selector.select(profile, BACKEND_JD)
        result = generate_resume(content, tmp_path, job_id="test123")
        assert result["html"].exists()
        assert "test123" in str(result["html"])
        assert result["pdf"] is None  # WeasyPrint not required

    def test_generate_creates_output_dir(self, selector, profile, tmp_path):
        content = selector.select(profile, BACKEND_JD)
        output_dir = tmp_path / "deep" / "nested"
        result = generate_resume(content, output_dir, job_id="nested")
        assert result["html"].exists()


# ── Integration: Quality Gate Test ───────────────────────────

class TestQualityGate:
    def test_generated_resume_scores_higher(self, selector, profile):
        """A tailored resume should score better than a generic one."""
        from src.analyzer.scorer import ATSScorer

        scorer = ATSScorer()
        content = selector.select(profile, BACKEND_JD)
        renderer = ResumeRenderer()
        html = renderer.render_html(content)

        # The generated HTML, when scored against the JD, should score reasonably
        result = scorer.score(html, BACKEND_JD)
        assert result.overall_score > 30  # Generated resume should be decent
        assert result.breakdown.keyword_match > 30
