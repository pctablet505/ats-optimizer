"""Orchestrator — coordinates the full automated job application pipeline.

Ties together: job discovery, deduplication, scoring, resume generation,
and application submission.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.automation.drivers.base import BasePortalDriver, DiscoveredJob, SearchConfig
from src.automation.question_answerer import QuestionAnswerer
from src.discovery.deduplicator import Deduplicator
from src.discovery.scorer import JobProfileScorer
from src.generator.content_selector import ContentSelector
from src.generator.latex_renderer import generate_latex_resume
from src.profile.manager import CandidateProfile, ProfileManager

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Summary of a single pipeline run."""
    jobs_discovered: int = 0
    jobs_new: int = 0
    jobs_duplicates: int = 0
    jobs_scored: int = 0
    resumes_generated: int = 0
    applications_submitted: int = 0
    applications_failed: int = 0
    errors: list[str] = field(default_factory=list)


class Orchestrator:
    """Coordinates the full job application pipeline.

    Pipeline flow:
    1. Search for jobs using portal drivers
    2. Deduplicate against existing jobs
    3. Score new jobs against candidate profile
    4. Filter to jobs above minimum score
    5. Generate tailored resumes for top matches
    6. Submit applications (with question answering)
    """

    def __init__(
        self,
        drivers: list[BasePortalDriver],
        profile: CandidateProfile,
        output_dir: str | Path = "data/output",
        min_score: float = 50.0,
        auto_apply: bool = False,
        existing_urls: set[str] | None = None,
        # Pass qa kwargs through so Orchestrator callers can set work-auth etc.
        salary_expectation: str = "Negotiable, based on total compensation",
        notice_period: str = "Immediate / 30 days",
        work_authorization: str = "Yes, authorized to work",
        remote_preference: str = "Remote or Hybrid preferred; open to on-site",
        relocation: str = "Open to discussion",
    ):
        self.drivers = drivers
        self.profile = profile
        self.output_dir = Path(output_dir)
        self.min_score = min_score
        self.auto_apply = auto_apply
        self.existing_urls = existing_urls or set()

        self.deduplicator = Deduplicator()
        self.scorer = JobProfileScorer()
        self.content_selector = ContentSelector(use_llm=True)
        self.question_answerer = QuestionAnswerer(
            profile,
            salary_expectation=salary_expectation,
            notice_period=notice_period,
            work_authorization=work_authorization,
            remote_preference=remote_preference,
            relocation=relocation,
        )
        # Pre-build the base answers dict (static profile fields, no LLM calls)
        self._base_answers = self.question_answerer.build_answers_dict()

    async def run(self, search_config: SearchConfig) -> PipelineResult:
        """Execute the full pipeline.

        Args:
            search_config: Search parameters for all drivers.

        Returns:
            PipelineResult with summary statistics.
        """
        result = PipelineResult()

        # 1. Discover jobs from all drivers
        all_jobs: list[DiscoveredJob] = []
        for driver in self.drivers:
            try:
                if await driver.is_available():
                    jobs = await driver.search(search_config)
                    all_jobs.extend(jobs)
                    logger.info(f"{driver.driver_name()}: found {len(jobs)} jobs")
                else:
                    logger.warning(f"{driver.driver_name()}: not available, skipping")
            except Exception as e:
                error = f"{driver.driver_name()} search error: {e}"
                logger.error(error)
                result.errors.append(error)

        result.jobs_discovered = len(all_jobs)

        # 2. Deduplicate
        unique_jobs, duplicates = self.deduplicator.deduplicate(
            all_jobs, self.existing_urls
        )
        result.jobs_new = len(unique_jobs)
        result.jobs_duplicates = len(duplicates)

        # 3. Score and rank
        scored_jobs = self.scorer.score_and_rank(
            unique_jobs, self.profile, min_score=self.min_score
        )
        result.jobs_scored = len(scored_jobs)

        # 4. Generate resumes and optionally apply
        for job, score in scored_jobs:
            try:
                # Generate tailored resume as LaTeX PDF
                content = self.content_selector.select(
                    self.profile, job.description_text or job.title
                )
                resume_files = generate_latex_resume(
                    content,
                    self.output_dir / "resumes",
                    job_id=job.external_id or str(abs(hash(job.url)))[-8:],
                )
                result.resumes_generated += 1
                pdf_or_tex = resume_files.get("pdf") or resume_files.get("tex", "")
                logger.info(
                    f"Resume generated for {job.title} @ {job.company} "
                    f"(score={score:.0f}): {pdf_or_tex}"
                )

                # Apply if auto_apply is enabled
                if self.auto_apply:
                    await self._apply_to_job(job, resume_files, result)

            except Exception as e:
                error = f"Error processing {job.title} @ {job.company}: {e}"
                logger.error(error)
                result.errors.append(error)

        return result

    async def _apply_to_job(
        self,
        job: DiscoveredJob,
        resume_files: dict,
        result: PipelineResult,
    ):
        """Submit application for a specific job."""
        resume_path = str(resume_files.get("pdf") or resume_files.get("tex", ""))

        driver = self._get_driver_for_source(job.source)
        if not driver:
            result.errors.append(f"No driver for source: {job.source}")
            return

        try:
            # Build answers: start with static profile fields, then Q&A bank answers
            # for any expected questions from this portal's typical form.
            answers = dict(self._base_answers)

            apply_result = await driver.apply(job, resume_path, answers)
            status = apply_result.get("status", "unknown")

            if status in ("submitted", "stub_submitted"):
                result.applications_submitted += 1
                logger.info(
                    f"Applied to {job.title} @ {job.company} [{job.source}]: "
                    f"{apply_result.get('message', '')}"
                )
            elif status == "captcha":
                result.errors.append(
                    f"CAPTCHA blocked application to {job.title} @ {job.company}: "
                    f"{apply_result.get('message', '')}"
                )
                result.applications_failed += 1
            else:
                result.applications_failed += 1
                result.errors.append(
                    f"Apply failed for {job.title} @ {job.company}: "
                    f"{apply_result.get('message', status)}"
                )
        except Exception as e:
            result.applications_failed += 1
            result.errors.append(f"Apply error for {job.url}: {e}")

    def _get_driver_for_source(self, source: str) -> BasePortalDriver | None:
        """Find the portal driver matching a job source."""
        for driver in self.drivers:
            if driver.driver_name() == source:
                return driver
        return None
