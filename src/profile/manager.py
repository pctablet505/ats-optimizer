"""Candidate Profile Manager — load, save, update YAML profiles."""

from pathlib import Path
from typing import Any

import yaml

from src.config import PROJECT_ROOT


DEFAULT_PROFILE_PATH = PROJECT_ROOT / "data" / "profiles" / "candidate_profile.yaml"


class CandidateProfile:
    """In-memory representation of the candidate profile."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    # ── Accessors ────────────────────────────────────────────

    @property
    def personal_info(self) -> dict:
        return self.data.get("personal_info", {})

    @property
    def full_name(self) -> str:
        return self.personal_info.get("full_name", "")

    @property
    def email(self) -> str:
        return self.personal_info.get("email", "")

    @property
    def phone(self) -> str:
        return self.personal_info.get("phone", "")

    @property
    def location(self) -> str:
        return self.personal_info.get("location", "")

    @property
    def linkedin(self) -> str | None:
        return self.personal_info.get("linkedin")

    @property
    def github(self) -> str | None:
        return self.personal_info.get("github")

    @property
    def summaries(self) -> list[dict]:
        return self.data.get("summaries", [])

    @property
    def skills(self) -> list[dict]:
        return self.data.get("skills", [])

    @property
    def experience(self) -> list[dict]:
        return self.data.get("experience", [])

    @property
    def education(self) -> list[dict]:
        return self.data.get("education", [])

    @property
    def certifications(self) -> list[dict]:
        return self.data.get("certifications", [])

    @property
    def projects(self) -> list[dict]:
        return self.data.get("projects", [])

    @property
    def qa_bank(self) -> list[dict]:
        return self.data.get("qa_bank", [])

    # ── Derived helpers ──────────────────────────────────────

    def get_all_skill_names(self) -> list[str]:
        """Flatten all skills into a list of names."""
        names = []
        for category in self.skills:
            for item in category.get("items", []):
                names.append(item["name"])
        return names

    def get_skills_by_category(self, category: str) -> list[dict]:
        """Get skills for a specific category."""
        for cat in self.skills:
            if cat.get("category", "").lower() == category.lower():
                return cat.get("items", [])
        return []

    def get_summary_for_role(self, role: str) -> str | None:
        """Find a pre-written summary matching a target role."""
        role_lower = role.lower()
        for s in self.summaries:
            if role_lower in s.get("target_role", "").lower():
                return s.get("text")
        return None

    def get_all_bullets(self) -> list[dict]:
        """Get all experience bullets with company/title context."""
        result = []
        for exp in self.experience:
            for bullet in exp.get("bullets", []):
                result.append({
                    "text": bullet["text"],
                    "tags": bullet.get("tags", []),
                    "company": exp["company"],
                    "title": exp["title"],
                })
        return result

    def total_years_experience(self) -> int:
        """Estimate total years of experience from date ranges."""
        from datetime import date

        total_months = 0
        for exp in self.experience:
            start = exp.get("start_date", "")
            end = exp.get("end_date")

            if not start:
                continue

            try:
                start_parts = start.split("-")
                start_date = date(int(start_parts[0]), int(start_parts[1]), 1)

                if end:
                    end_parts = end.split("-")
                    end_date = date(int(end_parts[0]), int(end_parts[1]), 1)
                else:
                    end_date = date.today()

                months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
                total_months += max(0, months)
            except (ValueError, IndexError):
                continue

        return total_months // 12


class ProfileManager:
    """Manages loading, saving, and updating candidate profiles."""

    def __init__(self, profile_path: Path | None = None):
        self.path = profile_path or DEFAULT_PROFILE_PATH

    def load(self) -> CandidateProfile:
        """Load profile from YAML file."""
        if not self.path.exists():
            raise FileNotFoundError(f"Profile not found at {self.path}")

        with open(self.path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return CandidateProfile(data)

    def save(self, profile: CandidateProfile):
        """Save profile to YAML file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.dump(
                profile.data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    def update_section(self, section: str, data: Any):
        """Update a specific top-level section of the profile."""
        profile = self.load()
        profile.data[section] = data
        self.save(profile)
        return profile

    def exists(self) -> bool:
        """Check if a profile file exists."""
        return self.path.exists()
