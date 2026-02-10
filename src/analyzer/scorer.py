"""ATS compatibility scorer — 5-component weighted scoring algorithm.

Scores a resume against a job description across 5 dimensions:
1. Keyword Match (40%) — How many JD keywords appear in the resume
2. Section Completeness (15%) — Does the resume have all expected sections
3. Keyword Density (15%) — Are keywords used at appropriate frequency
4. Experience Relevance (15%) — Do experience bullets match JD requirements
5. Formatting (15%) — ATS-friendly formatting checks
"""

from dataclasses import dataclass, field

from src.analyzer.keywords import (
    extract_keywords,
    extract_keywords_with_importance,
    normalize_keyword,
)


# ── Scoring weights ──────────────────────────────────────────

WEIGHTS = {
    "keyword_match": 0.40,
    "section_completeness": 0.15,
    "keyword_density": 0.15,
    "experience_relevance": 0.15,
    "formatting": 0.15,
}

# ── Expected resume sections ─────────────────────────────────

EXPECTED_SECTIONS = [
    "summary",
    "experience",
    "education",
    "skills",
]

OPTIONAL_SECTIONS = [
    "certifications",
    "projects",
]


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of ATS score."""
    keyword_match: int = 0
    section_completeness: int = 0
    keyword_density: int = 0
    experience_relevance: int = 0
    formatting: int = 0


@dataclass
class ScoreResult:
    """Complete ATS scoring result."""
    overall_score: int = 0
    breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[dict] = field(default_factory=list)
    formatting_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "breakdown": {
                "keyword_match": self.breakdown.keyword_match,
                "section_completeness": self.breakdown.section_completeness,
                "keyword_density": self.breakdown.keyword_density,
                "experience_relevance": self.breakdown.experience_relevance,
                "formatting": self.breakdown.formatting,
            },
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
            "formatting_issues": self.formatting_issues,
        }


class ATSScorer:
    """Score a resume against a job description for ATS compatibility."""

    def score(self, resume_text: str, jd_text: str) -> ScoreResult:
        """Calculate ATS compatibility score (0-100).

        Args:
            resume_text: Full text of the resume.
            jd_text: Full text of the job description.

        Returns:
            ScoreResult with overall score, breakdown, and details.
        """
        result = ScoreResult()
        breakdown = ScoreBreakdown()

        # 1. Keyword Match (40%)
        breakdown.keyword_match, matched, missing = self._score_keyword_match(
            resume_text, jd_text
        )
        result.matched_keywords = matched
        result.missing_keywords = missing

        # 2. Section Completeness (15%)
        breakdown.section_completeness = self._score_sections(resume_text)

        # 3. Keyword Density (15%)
        breakdown.keyword_density = self._score_keyword_density(
            resume_text, matched
        )

        # 4. Experience Relevance (15%)
        breakdown.experience_relevance = self._score_experience_relevance(
            resume_text, jd_text
        )

        # 5. Formatting (15%)
        breakdown.formatting, issues = self._score_formatting(resume_text)
        result.formatting_issues = issues

        # Calculate weighted overall score
        result.breakdown = breakdown
        result.overall_score = round(
            breakdown.keyword_match * WEIGHTS["keyword_match"]
            + breakdown.section_completeness * WEIGHTS["section_completeness"]
            + breakdown.keyword_density * WEIGHTS["keyword_density"]
            + breakdown.experience_relevance * WEIGHTS["experience_relevance"]
            + breakdown.formatting * WEIGHTS["formatting"]
        )

        return result

    def _score_keyword_match(
        self, resume_text: str, jd_text: str
    ) -> tuple[int, list[str], list[dict]]:
        """Score based on JD keywords found in resume.

        Returns:
            (score_0_100, matched_keywords, missing_keywords)
        """
        jd_keywords = extract_keywords_with_importance(jd_text, max_keywords=25)
        if not jd_keywords:
            return 100, [], []

        resume_lower = resume_text.lower()
        matched = []
        missing = []

        for kw_info in jd_keywords:
            keyword = kw_info["keyword"]
            if keyword.lower() in resume_lower:
                matched.append(keyword)
            else:
                missing.append(kw_info)

        if not jd_keywords:
            return 100, matched, missing

        # Weight high-importance keywords more heavily
        total_weight = 0
        matched_weight = 0
        for kw_info in jd_keywords:
            w = {"high": 3, "medium": 2, "low": 1}.get(kw_info["importance"], 1)
            total_weight += w
            if kw_info["keyword"] in matched:
                matched_weight += w

        score = round((matched_weight / total_weight) * 100) if total_weight > 0 else 0
        return min(score, 100), matched, missing

    def _score_sections(self, resume_text: str) -> int:
        """Score based on presence of expected resume sections."""
        resume_lower = resume_text.lower()
        found = 0
        total = len(EXPECTED_SECTIONS) + len(OPTIONAL_SECTIONS)

        for section in EXPECTED_SECTIONS:
            # Check for common variations of section headers
            variations = [
                section,
                section.replace("_", " "),
                section.upper(),
            ]
            if section == "summary":
                variations.extend(["professional summary", "objective", "about"])
            elif section == "experience":
                variations.extend(["work experience", "professional experience", "employment"])
            elif section == "education":
                variations.extend(["academic", "degree"])
            elif section == "skills":
                variations.extend(["technical skills", "core competencies", "technologies"])

            if any(v in resume_lower for v in variations):
                found += 1

        for section in OPTIONAL_SECTIONS:
            variations = [section, section.upper()]
            if section == "certifications":
                variations.extend(["certificates", "certification"])
            elif section == "projects":
                variations.extend(["personal projects", "side projects"])
            if any(v in resume_lower for v in variations):
                found += 1

        return round((found / total) * 100) if total > 0 else 0

    def _score_keyword_density(
        self, resume_text: str, matched_keywords: list[str]
    ) -> int:
        """Score based on keyword usage density (not too sparse, not stuffed)."""
        if not matched_keywords:
            return 50  # Neutral if no keywords to check

        words = resume_text.split()
        total_words = len(words)
        if total_words == 0:
            return 0

        resume_lower = resume_text.lower()
        total_occurrences = 0
        for kw in matched_keywords:
            total_occurrences += resume_lower.count(kw.lower())

        # Ideal density: 2-5% of total words should be keywords
        density = total_occurrences / total_words

        if density < 0.01:
            return 40  # Too sparse
        elif density <= 0.03:
            return 80  # Good density
        elif density <= 0.06:
            return 100  # Optimal
        elif density <= 0.10:
            return 80  # Slightly dense
        else:
            return 50  # Keyword stuffing

    def _score_experience_relevance(
        self, resume_text: str, jd_text: str
    ) -> int:
        """Score based on overlap between experience content and JD."""
        # Extract keywords from both
        resume_kws = extract_keywords(resume_text, max_keywords=20)
        jd_kws = extract_keywords(jd_text, max_keywords=20)

        resume_set = {k.canonical.lower() for k in resume_kws.keywords}
        jd_set = {k.canonical.lower() for k in jd_kws.keywords}

        if not jd_set:
            return 100

        overlap = resume_set & jd_set
        score = round((len(overlap) / len(jd_set)) * 100)
        return min(score, 100)

    def _score_formatting(self, resume_text: str) -> tuple[int, list[str]]:
        """Score based on ATS-friendly formatting.

        Returns:
            (score_0_100, list_of_issues)
        """
        issues = []
        score = 100

        # Check length (1-2 pages ≈ 300-800 words)
        word_count = len(resume_text.split())
        if word_count < 150:
            issues.append(f"Resume too short ({word_count} words). Aim for 300+ words.")
            score -= 20
        elif word_count > 1200:
            issues.append(f"Resume too long ({word_count} words). Keep under 800 words for 1-2 pages.")
            score -= 10

        # Check for contact info patterns
        has_email = bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', resume_text))
        has_phone = bool(re.search(r'[\+]?[\d\s\-\(\)]{7,15}', resume_text))
        if not has_email:
            issues.append("No email address found in resume.")
            score -= 10
        if not has_phone:
            issues.append("No phone number found in resume.")
            score -= 5

        # Check for bullet points or list markers
        has_bullets = bool(re.search(r'[•\-\*] ', resume_text))
        if not has_bullets:
            issues.append("No bullet points found. Use bullet points for experience items.")
            score -= 10

        # Check for dates (experience dating)
        has_dates = bool(re.search(r'\b20\d{2}\b', resume_text))
        if not has_dates:
            issues.append("No dates found. Include dates for experience and education.")
            score -= 10

        return max(score, 0), issues


# Module-level convenience import
import re
