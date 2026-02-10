"""Tests for Phase 2: Candidate Profile System."""

import pytest
import yaml
from pathlib import Path

from src.profile.manager import CandidateProfile, ProfileManager


# ── Sample data ──────────────────────────────────────────────

SAMPLE_PROFILE = {
    "personal_info": {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+1-555-0100",
        "location": "San Francisco, CA",
        "linkedin": "https://linkedin.com/in/janedoe",
        "github": "https://github.com/janedoe",
    },
    "summaries": [
        {"target_role": "Backend Engineer", "text": "Experienced backend engineer with 5+ years."},
        {"target_role": "Full Stack Developer", "text": "Full stack developer with broad experience."},
    ],
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
    ],
    "experience": [
        {
            "company": "TechCorp",
            "title": "Senior Backend Engineer",
            "location": "SF",
            "start_date": "2022-03",
            "end_date": None,
            "bullets": [
                {"text": "Built event pipeline handling 50K events/sec", "tags": ["Python", "Kafka"]},
                {"text": "Led migration to microservices", "tags": ["FastAPI", "microservices"]},
            ],
        },
        {
            "company": "StartupXYZ",
            "title": "Software Engineer",
            "location": "Remote",
            "start_date": "2019-06",
            "end_date": "2022-02",
            "bullets": [
                {"text": "Built REST APIs serving 10K users", "tags": ["Django", "REST"]},
            ],
        },
    ],
    "education": [
        {"institution": "UC Berkeley", "degree": "B.S. Computer Science", "graduation_date": "2019-05"},
    ],
    "certifications": [
        {"name": "AWS Solutions Architect", "issuer": "AWS", "date": "2023-01"},
    ],
    "projects": [
        {"name": "CLI Tool", "description": "DB migration tool", "tech_stack": ["Python", "Click"]},
    ],
    "qa_bank": [
        {"question_pattern": "years of experience", "answer": "5"},
        {"question_pattern": "authorized to work", "answer": "Yes"},
    ],
}


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def profile():
    """Create a CandidateProfile from sample data."""
    return CandidateProfile(SAMPLE_PROFILE.copy())


@pytest.fixture
def profile_file(tmp_path):
    """Write sample profile to a temp YAML file."""
    path = tmp_path / "profile.yaml"
    with open(path, "w") as f:
        yaml.dump(SAMPLE_PROFILE, f, default_flow_style=False)
    return path


# ── CandidateProfile Tests ───────────────────────────────────

class TestCandidateProfile:
    def test_personal_info(self, profile):
        assert profile.full_name == "Jane Doe"
        assert profile.email == "jane@example.com"
        assert profile.location == "San Francisco, CA"
        assert profile.linkedin == "https://linkedin.com/in/janedoe"

    def test_summaries(self, profile):
        assert len(profile.summaries) == 2
        assert profile.summaries[0]["target_role"] == "Backend Engineer"

    def test_get_summary_for_role(self, profile):
        summary = profile.get_summary_for_role("Backend Engineer")
        assert summary is not None
        assert "backend" in summary.lower()

    def test_get_summary_for_role_partial_match(self, profile):
        summary = profile.get_summary_for_role("backend")
        assert summary is not None

    def test_get_summary_for_role_no_match(self, profile):
        assert profile.get_summary_for_role("Data Scientist") is None

    def test_get_all_skill_names(self, profile):
        names = profile.get_all_skill_names()
        assert "Python" in names
        assert "FastAPI" in names
        assert "Django" in names
        assert len(names) == 4

    def test_get_skills_by_category(self, profile):
        langs = profile.get_skills_by_category("Languages")
        assert len(langs) == 2
        assert langs[0]["name"] == "Python"

    def test_get_skills_by_category_not_found(self, profile):
        assert profile.get_skills_by_category("NonExistent") == []

    def test_experience(self, profile):
        assert len(profile.experience) == 2
        assert profile.experience[0]["company"] == "TechCorp"

    def test_get_all_bullets(self, profile):
        bullets = profile.get_all_bullets()
        assert len(bullets) == 3
        # Each bullet should have context
        assert bullets[0]["company"] == "TechCorp"
        assert bullets[0]["title"] == "Senior Backend Engineer"
        assert "tags" in bullets[0]

    def test_total_years_experience(self, profile):
        years = profile.total_years_experience()
        # TechCorp: ~3+ years (2022-03 to now), StartupXYZ: ~3 years (2019-06 to 2022-02)
        # Total should be ~6
        assert years >= 5  # At least 5 years total
        assert years <= 8  # But not unreasonably high

    def test_education(self, profile):
        assert len(profile.education) == 1
        assert profile.education[0]["institution"] == "UC Berkeley"

    def test_certifications(self, profile):
        assert len(profile.certifications) == 1

    def test_projects(self, profile):
        assert len(profile.projects) == 1
        assert profile.projects[0]["name"] == "CLI Tool"

    def test_qa_bank(self, profile):
        assert len(profile.qa_bank) == 2

    def test_empty_profile(self):
        """Profile with empty dict should return safe defaults."""
        profile = CandidateProfile({})
        assert profile.full_name == ""
        assert profile.get_all_skill_names() == []
        assert profile.get_all_bullets() == []
        assert profile.total_years_experience() == 0


# ── ProfileManager Tests ────────────────────────────────────

class TestProfileManager:
    def test_load_profile(self, profile_file):
        manager = ProfileManager(profile_file)
        profile = manager.load()
        assert profile.full_name == "Jane Doe"
        assert len(profile.skills) == 2

    def test_load_missing_file(self, tmp_path):
        manager = ProfileManager(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError):
            manager.load()

    def test_save_profile(self, tmp_path):
        path = tmp_path / "output.yaml"
        manager = ProfileManager(path)
        profile = CandidateProfile(SAMPLE_PROFILE.copy())
        manager.save(profile)

        # Re-load and verify
        loaded = manager.load()
        assert loaded.full_name == "Jane Doe"
        assert len(loaded.skills) == 2

    def test_update_section(self, profile_file):
        manager = ProfileManager(profile_file)

        # Update personal_info
        new_info = {"full_name": "John Smith", "email": "john@example.com"}
        updated = manager.update_section("personal_info", new_info)
        assert updated.full_name == "John Smith"

        # Verify persisted
        reloaded = manager.load()
        assert reloaded.full_name == "John Smith"

    def test_exists(self, profile_file, tmp_path):
        manager = ProfileManager(profile_file)
        assert manager.exists() is True

        manager2 = ProfileManager(tmp_path / "nope.yaml")
        assert manager2.exists() is False

    def test_save_creates_directories(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "profile.yaml"
        manager = ProfileManager(path)
        profile = CandidateProfile({"personal_info": {"full_name": "Test"}})
        manager.save(profile)
        assert path.exists()

    def test_round_trip_preserves_data(self, tmp_path):
        """Save and reload should preserve all data."""
        path = tmp_path / "roundtrip.yaml"
        manager = ProfileManager(path)

        original = CandidateProfile(SAMPLE_PROFILE.copy())
        manager.save(original)
        reloaded = manager.load()

        assert reloaded.full_name == original.full_name
        assert len(reloaded.skills) == len(original.skills)
        assert len(reloaded.experience) == len(original.experience)
        assert len(reloaded.qa_bank) == len(original.qa_bank)


# ── Parser Tests (basic, no real PDF/DOCX in test) ──────────

class TestParser:
    def test_extract_text_unsupported_format(self):
        from src.profile.parser import extract_text
        with pytest.raises(ValueError, match="Unsupported file format"):
            extract_text("resume.txt")

    def test_extract_text_pdf_not_found(self):
        from src.profile.parser import extract_text_from_pdf
        with pytest.raises(FileNotFoundError):
            extract_text_from_pdf("/nonexistent/resume.pdf")

    def test_extract_text_wrong_extension(self, tmp_path):
        from src.profile.parser import extract_text_from_pdf
        txt_file = tmp_path / "resume.txt"
        txt_file.write_text("hello")
        with pytest.raises(ValueError, match="Expected a .pdf"):
            extract_text_from_pdf(txt_file)
