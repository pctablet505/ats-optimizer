"""ATS Optimizer CLI — run pipeline from the command line."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.automation.drivers.base import SearchConfig
from src.automation.drivers.linkedin import LinkedInDriver
from src.automation.drivers.indeed import IndeedDriver
from src.automation.orchestrator import Orchestrator
from src.notifications.notifier import NotificationManager
from src.profile.manager import ProfileManager, CandidateProfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("ats-optimizer")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ats-optimizer",
        description="ATS Optimizer — Automated Job Application Pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    # ── search ───────────────────────────────────────────
    search = sub.add_parser("search", help="Search and apply for jobs")
    search.add_argument("--keywords", nargs="+", required=True, help="Search keywords")
    search.add_argument("--location", default="", help="Job location filter")
    search.add_argument("--remote", action="store_true", help="Remote jobs only")
    search.add_argument("--min-score", type=float, default=50.0, help="Minimum match score (0-100)")
    search.add_argument("--auto-apply", action="store_true", help="Auto-submit applications")
    search.add_argument("--profile", default="data/profiles/candidate_profile.yaml", help="Profile YAML path")
    search.add_argument("--portals", nargs="+", default=["indeed"], choices=["linkedin", "indeed"], help="Job portals")
    search.add_argument("--max-results", type=int, default=50, help="Max results per portal")

    # ── profile ──────────────────────────────────────────
    profile_cmd = sub.add_parser("profile", help="Manage candidate profile")
    profile_cmd.add_argument("--show", action="store_true", help="Display current profile")
    profile_cmd.add_argument("--path", default="data/profiles/candidate_profile.yaml", help="Profile path")

    # ── analyze ──────────────────────────────────────────
    analyze = sub.add_parser("analyze", help="Score a resume against a job description")
    analyze.add_argument("--resume", required=True, help="Path to resume text file")
    analyze.add_argument("--jd", required=True, help="Path to job description text file")

    return parser


async def run_search(args):
    """Execute the search & apply pipeline."""
    notifier = NotificationManager()

    # Load profile
    pm = ProfileManager(Path(args.profile))
    if not pm.exists():
        logger.error(f"Profile not found: {args.profile}")
        notifier.notify_error(f"Profile file not found: {args.profile}")
        return 1

    profile = pm.load()
    logger.info(f"Loaded profile for: {profile.full_name}")

    # Build drivers
    drivers = []
    for portal in args.portals:
        if portal == "linkedin":
            drivers.append(LinkedInDriver())
        elif portal == "indeed":
            drivers.append(IndeedDriver())

    # Build search config
    config = SearchConfig(
        keywords=args.keywords,
        location=args.location,
        remote_only=args.remote,
        max_results=args.max_results,
    )

    # Run pipeline
    orch = Orchestrator(
        drivers=drivers,
        profile=profile,
        min_score=args.min_score,
        auto_apply=args.auto_apply,
    )

    logger.info(f"Starting search: keywords={args.keywords}, portals={args.portals}")
    result = await orch.run(config)

    # Report results
    notifier.notify_pipeline_complete(result)
    print(f"\n{'='*50}")
    print(f"  Jobs discovered : {result.jobs_discovered}")
    print(f"  New (unique)    : {result.jobs_new}")
    print(f"  Duplicates      : {result.jobs_duplicates}")
    print(f"  Scored ≥ {args.min_score:4.0f}  : {result.jobs_scored}")
    print(f"  Resumes made    : {result.resumes_generated}")
    print(f"  Applied         : {result.applications_submitted}")
    if result.errors:
        print(f"  Errors          : {len(result.errors)}")
        for e in result.errors:
            print(f"    • {e}")
    print(f"{'='*50}\n")

    return 0


def run_profile(args):
    """Display or manage the candidate profile."""
    pm = ProfileManager(Path(args.path))
    if not pm.exists():
        print(f"Profile not found at {args.path}")
        return 1

    profile = pm.load()
    if args.show:
        print(f"Name:           {profile.full_name}")
        print(f"Email:          {profile.email}")
        print(f"Location:       {profile.location}")
        print(f"Experience:     {profile.total_years_experience()} years")
        print(f"Skills:         {len(profile.get_all_skill_names())} skills")
        print(f"Summaries:      {len(profile.summaries)}")
        print(f"Experience:     {len(profile.experience)} roles")
        print(f"Education:      {len(profile.education)}")
        print(f"Certifications: {len(profile.certifications)}")
        print(f"Projects:       {len(profile.projects)}")
        print(f"Q&A bank:       {len(profile.qa_bank)} entries")
    return 0


def run_analyze(args):
    """Analyze a resume against a JD."""
    from src.analyzer.scorer import ATSScorer
    from src.analyzer.suggestions import generate_suggestions

    resume_text = Path(args.resume).read_text(encoding="utf-8")
    jd_text = Path(args.jd).read_text(encoding="utf-8")

    scorer = ATSScorer()
    result = scorer.score(resume_text, jd_text)
    suggestions = generate_suggestions(result)

    print(f"\n{'='*50}")
    print(f"  ATS Score: {result.overall_score:.1f}/100")
    print(f"{'='*50}")
    print(f"  Keyword Match      : {result.breakdown.keyword_match:.1f}")
    print(f"  Section Complete   : {result.breakdown.section_completeness:.1f}")
    print(f"  Keyword Density    : {result.breakdown.keyword_density:.1f}")
    print(f"  Experience Relev.  : {result.breakdown.experience_relevance:.1f}")
    print(f"  Formatting         : {result.breakdown.formatting:.1f}")
    print()
    if result.missing_keywords:
        print("  Missing Keywords:")
        for kw in result.missing_keywords[:10]:
            print(f"    • {kw['keyword']}")
    print()
    print("  Suggestions:")
    for s in suggestions:
        print(f"    {s}")
    print(f"{'='*50}\n")
    return 0


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "search":
        return asyncio.run(run_search(args))
    elif args.command == "profile":
        return run_profile(args)
    elif args.command == "analyze":
        return run_analyze(args)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
