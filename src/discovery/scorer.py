"""Job-profile match scorer — rank discovered jobs by profile fit."""

from src.analyzer.keywords import extract_keywords, normalize_keyword
from src.automation.drivers.base import DiscoveredJob
from src.profile.manager import CandidateProfile


class JobProfileScorer:
    """Score how well a discovered job matches the candidate profile.

    Uses keyword overlap between JD and candidate skills/experience
    to produce a 0-100 match score.
    """

    def score(self, job: DiscoveredJob, profile: CandidateProfile) -> float:
        """Calculate match score between a job and a candidate profile.

        Args:
            job: The discovered job with description text.
            profile: The candidate's full profile.

        Returns:
            Match score from 0.0 to 100.0.
        """
        if not job.description_text:
            return 0.0

        # Extract JD keywords
        jd_kws = extract_keywords(job.description_text, max_keywords=25)
        jd_set = {k.canonical.lower() for k in jd_kws.keywords}

        if not jd_set:
            return 50.0  # Neutral if JD has no extractable keywords

        # Build candidate keyword set from profile
        candidate_keywords = set()

        # Skills
        for skill in profile.get_all_skill_names():
            candidate_keywords.add(normalize_keyword(skill).lower())

        # Experience tags
        for bullet in profile.get_all_bullets():
            for tag in bullet.get("tags", []):
                candidate_keywords.add(normalize_keyword(tag).lower())

        # Project tech stacks
        for proj in profile.projects:
            for tech in proj.get("tech_stack", []):
                candidate_keywords.add(normalize_keyword(tech).lower())

        # Calculate overlap
        overlap = jd_set & candidate_keywords
        score = (len(overlap) / len(jd_set)) * 100

        return min(round(score, 1), 100.0)

    def score_and_rank(
        self,
        jobs: list[DiscoveredJob],
        profile: CandidateProfile,
        min_score: float = 0.0,
    ) -> list[tuple[DiscoveredJob, float]]:
        """Score and rank a list of jobs by profile fit.

        Args:
            jobs: List of discovered jobs.
            profile: The candidate profile.
            min_score: Minimum score to include in results.

        Returns:
            List of (job, score) tuples, sorted by score descending.
        """
        scored = []
        for job in jobs:
            s = self.score(job, profile)
            if s >= min_score:
                scored.append((job, s))

        scored.sort(key=lambda x: -x[1])
        return scored
