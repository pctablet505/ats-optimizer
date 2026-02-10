"""Content selector — intelligently picks resume content for a specific job.

Given a candidate profile and a job description, this module selects the
most relevant skills, experience bullets, projects, and certifications
to include in a tailored resume.
"""

from dataclasses import dataclass, field

from src.analyzer.keywords import extract_keywords, normalize_keyword
from src.profile.manager import CandidateProfile


@dataclass
class SelectedContent:
    """The selected content to use when generating a resume."""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    certifications: list[dict] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    personal_info: dict = field(default_factory=dict)
    target_keywords: list[str] = field(default_factory=list)


class ContentSelector:
    """Select the best resume content for a given job description."""

    def select(
        self,
        profile: CandidateProfile,
        jd_text: str,
        max_skills: int = 15,
        max_bullets_per_role: int = 4,
        max_projects: int = 2,
    ) -> SelectedContent:
        """Select and rank content from profile for the given JD.

        Args:
            profile: The candidate's full profile.
            jd_text: The job description text.
            max_skills: Maximum skills to include.
            max_bullets_per_role: Maximum bullet points per job.
            max_projects: Maximum projects to include.

        Returns:
            SelectedContent with the best-fit items.
        """
        # Extract JD keywords for relevance scoring
        jd_kw_result = extract_keywords(jd_text, max_keywords=25)
        jd_keywords = {k.canonical.lower() for k in jd_kw_result.keywords}
        jd_keyword_list = [k.canonical for k in jd_kw_result.keywords]

        result = SelectedContent(
            personal_info=profile.personal_info,
            target_keywords=jd_keyword_list,
        )

        # 1. Summary — find best matching or use first
        result.summary = self._select_summary(profile, jd_text)

        # 2. Skills — rank by relevance to JD
        result.skills = self._select_skills(profile, jd_keywords, max_skills)

        # 3. Experience — rank bullets by relevance
        result.experience = self._select_experience(
            profile, jd_keywords, max_bullets_per_role
        )

        # 4. Education — include all
        result.education = profile.education

        # 5. Certifications — include all
        result.certifications = profile.certifications

        # 6. Projects — rank by relevance
        result.projects = self._select_projects(
            profile, jd_keywords, max_projects
        )

        return result

    def _select_summary(
        self, profile: CandidateProfile, jd_text: str
    ) -> str:
        """Pick the most relevant pre-written summary."""
        # Try to match by JD content
        jd_lower = jd_text.lower()

        best_summary = ""
        best_score = -1

        for summary_item in profile.summaries:
            role = summary_item.get("target_role", "").lower()
            text = summary_item.get("text", "")

            # Score: count how many words from the role appear in JD
            role_words = role.split()
            score = sum(1 for w in role_words if w in jd_lower)

            if score > best_score:
                best_score = score
                best_summary = text

        # If no match at all, use first summary
        if not best_summary and profile.summaries:
            best_summary = profile.summaries[0].get("text", "")

        return best_summary.strip()

    def _select_skills(
        self,
        profile: CandidateProfile,
        jd_keywords: set[str],
        max_skills: int,
    ) -> list[str]:
        """Rank and select skills by JD relevance."""
        all_skills = []
        for cat in profile.skills:
            for item in cat.get("items", []):
                name = item["name"]
                normalized = normalize_keyword(name).lower()
                # Score: is this in JD keywords?  Weight by proficiency
                prof_weight = {
                    "Expert": 3,
                    "Advanced": 2,
                    "Intermediate": 1,
                }.get(item.get("proficiency", ""), 1)

                relevance = 10 if normalized in jd_keywords else 0
                score = relevance + prof_weight

                all_skills.append((name, score))

        # Sort by score descending, then alphabetically
        all_skills.sort(key=lambda x: (-x[1], x[0]))
        return [s[0] for s in all_skills[:max_skills]]

    def _select_experience(
        self,
        profile: CandidateProfile,
        jd_keywords: set[str],
        max_bullets_per_role: int,
    ) -> list[dict]:
        """Select experience entries with ranked bullets."""
        selected = []

        for exp in profile.experience:
            bullets = exp.get("bullets", [])

            # Score each bullet by tag overlap with JD keywords
            scored_bullets = []
            for bullet in bullets:
                tags = {t.lower() for t in bullet.get("tags", [])}
                # Also check if bullet text contains JD keywords
                text_lower = bullet.get("text", "").lower()
                text_matches = sum(1 for kw in jd_keywords if kw in text_lower)
                tag_matches = len(tags & jd_keywords)
                score = tag_matches * 2 + text_matches

                scored_bullets.append((bullet, score))

            # Sort by relevance
            scored_bullets.sort(key=lambda x: -x[1])
            top_bullets = [b[0] for b in scored_bullets[:max_bullets_per_role]]

            selected.append({
                "company": exp["company"],
                "title": exp["title"],
                "location": exp.get("location", ""),
                "start_date": exp.get("start_date", ""),
                "end_date": exp.get("end_date"),
                "bullets": top_bullets,
            })

        return selected

    def _select_projects(
        self,
        profile: CandidateProfile,
        jd_keywords: set[str],
        max_projects: int,
    ) -> list[dict]:
        """Select projects by relevance to JD."""
        scored = []
        for proj in profile.projects:
            tech = {t.lower() for t in proj.get("tech_stack", [])}
            desc_lower = proj.get("description", "").lower()

            score = len(tech & jd_keywords)
            score += sum(1 for kw in jd_keywords if kw in desc_lower)
            scored.append((proj, score))

        scored.sort(key=lambda x: -x[1])
        return [p[0] for p in scored[:max_projects]]
