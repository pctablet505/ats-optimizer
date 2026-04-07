"""ATS Optimizer CLI — run pipeline from the command line.

Credentials (never hard-code these):
  LinkedIn   : LINKEDIN_EMAIL, LINKEDIN_PASSWORD (optional — profile cookies preferred)
  Indeed     : INDEED_EMAIL, INDEED_PASSWORD (optional; Indeed works without login)
  Grok LLM   : GROK_API_KEY
  Headless   : BROWSER_HEADLESS=false to watch the browser (recommended initially)
  Profile dir: BROWSER_USER_DATA_DIR to override default browser profile path

Job-application kwargs (read from env):
  SALARY_EXPECTATION  — e.g. "₹25L–₹35L CTC"
  NOTICE_PERIOD       — e.g. "30 days"
  WORK_AUTHORIZATION  — e.g. "Yes, Indian citizen"
  REMOTE_PREFERENCE   — e.g. "Remote preferred"

Quick-start:
  1. python -m src.cli setup-browser   # opens browser for manual login
  2. python -m src.cli test-llm        # verify Grok API key works
  3. python -m src.cli search --keywords "ML Engineer" --location "Bengaluru" --portals linkedin
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from src.automation.drivers.base import SearchConfig
from src.automation.orchestrator import Orchestrator
from src.notifications.notifier import NotificationManager
from src.profile.manager import ProfileManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("ats-optimizer")

# Default browser profile for the bot (dedicated, not your main Chrome profile)
_DEFAULT_PROFILE_DIR = str(Path("data/browser_profiles/chrome_bot").resolve())


def _get_headless() -> bool:
    return os.environ.get("BROWSER_HEADLESS", "false").lower() != "false"


def _get_profile_dir() -> str:
    return os.environ.get("BROWSER_USER_DATA_DIR", _DEFAULT_PROFILE_DIR)


def _build_drivers(portals: list[str]) -> list:
    """Build portal drivers using the dedicated browser profile."""
    headless = _get_headless()
    profile_base = _get_profile_dir()

    drivers = []
    for portal in portals:
        if portal == "linkedin":
            from src.automation.drivers.linkedin import LinkedInDriver
            drivers.append(LinkedInDriver(
                headless=headless,
                user_data_dir=os.path.join(profile_base, "linkedin"),
            ))
        elif portal == "indeed":
            from src.automation.drivers.indeed import IndeedDriver
            drivers.append(IndeedDriver(
                headless=headless,
                user_data_dir=os.path.join(profile_base, "indeed"),
            ))
        elif portal == "naukri":
            from src.automation.drivers.naukri import NaukriDriver
            drivers.append(NaukriDriver(
                headless=headless,
                user_data_dir=os.path.join(profile_base, "naukri"),
            ))
    return drivers



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ats-optimizer",
        description="ATS Optimizer — Automated Job Application Pipeline",
        epilog="Run 'python -m src.cli setup-browser' first to log in to portals.",
    )
    sub = parser.add_subparsers(dest="command")

    # ── setup-browser ─────────────────────────────────────
    sub.add_parser(
        "setup-browser",
        help="Open browser with bot profile so you can log in to LinkedIn/Indeed manually",
    )

    # ── test-llm ─────────────────────────────────────────
    sub.add_parser("test-llm", help="Verify Grok API key and model are working")

    # ── search ───────────────────────────────────────────
    search = sub.add_parser("search", help="Search jobs, score them, generate tailored resumes")
    search.add_argument("--keywords", nargs="+", required=True, help="Search keywords")
    search.add_argument("--location", default="", help="Job location (e.g. 'Bengaluru')")
    search.add_argument("--remote", action="store_true", help="Remote jobs only")
    search.add_argument("--min-score", type=float, default=50.0, help="Minimum match score 0-100")
    search.add_argument("--auto-apply", action="store_true", help="Auto-submit applications")
    search.add_argument("--profile", default="data/profiles/candidate_profile.yaml")
    search.add_argument(
        "--portals", nargs="+", default=["linkedin"],
        choices=["linkedin", "indeed", "naukri"],
        help="Job portals to search (naukri = Indian market)",
    )
    search.add_argument("--max-results", type=int, default=25, help="Max results per portal")
    search.add_argument(
        "--salary", default=os.environ.get("SALARY_EXPECTATION", "Open to discussion"),
        help="Salary expectation for application forms",
    )
    search.add_argument(
        "--notice-period", default=os.environ.get("NOTICE_PERIOD", "1 month"),
        help="Notice period for application forms",
    )

    # ── profile ──────────────────────────────────────────
    profile_cmd = sub.add_parser("profile", help="View candidate profile")
    profile_cmd.add_argument("--show", action="store_true", help="Display current profile")
    profile_cmd.add_argument("--path", default="data/profiles/candidate_profile.yaml")

    # ── analyze ──────────────────────────────────────────
    analyze = sub.add_parser("analyze", help="ATS score a resume against a JD")
    analyze.add_argument("--resume", required=True, help="Path to resume text file")
    analyze.add_argument("--jd", required=True, help="Path to job description text file")

    # ── generate ─────────────────────────────────────────
    gen = sub.add_parser("generate", help="Generate a tailored LaTeX/PDF resume for a JD")
    gen.add_argument("--jd", required=True, help="Path to job description text file")
    gen.add_argument("--profile", default="data/profiles/candidate_profile.yaml")
    gen.add_argument("--output", default="data/output/resumes", help="Output directory")
    gen.add_argument("--no-llm", action="store_true", help="Skip LLM (faster, rule-based only)")

    return parser


# ── Command handlers ──────────────────────────────────────────

async def run_setup_browser(args):
    """Open real Chrome with the bot profile so the user can log in manually."""
    from playwright.async_api import async_playwright

    profile_dir = Path(_get_profile_dir()) / "linkedin"
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  BROWSER SETUP — Manual Login")
    print(f"{'='*60}")
    print(f"  Profile dir: {profile_dir}")
    print()
    print("  1. A Chrome window will open.")
    print("  2. Log in to LinkedIn (and Indeed if you use it).")
    print("  3. Close the browser when done.")
    print("  4. Your session is saved — future runs reuse it.")
    print(f"{'='*60}\n")

    from src.automation.drivers.base import _chrome_installed
    launch_kwargs = dict(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    if _chrome_installed():
        launch_kwargs["channel"] = "chrome"
        print("Using real Chrome.")
    else:
        print("Real Chrome not found — using Playwright Chromium.")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(str(profile_dir), **launch_kwargs)
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/login")
        print("Browser open. Log in then close the window.")
        # Wait until user closes the browser
        try:
            await context.wait_for_event("close", timeout=0)
        except Exception:
            pass
        await context.close()

    print("\nBrowser session saved. You can now run 'search'.\n")
    return 0


def run_test_llm(args):
    """Verify Grok API key and model are reachable."""
    import time
    from src.llm.provider import get_llm_provider, StubProvider

    print(f"\n{'='*55}")
    print("  LLM Provider Test")
    print(f"{'='*55}")

    provider = get_llm_provider()
    print(f"  Provider : {type(provider).__name__}")

    if isinstance(provider, StubProvider):
        print("  Status   : STUB (no API key set or provider config missing)")
        print("  Action   : export GROK_API_KEY=<your_key> and retry")
        print(f"{'='*55}\n")
        return 1

    print(f"  Key      : {os.environ.get('GROK_API_KEY','')[:8]}...")
    print("  Testing API call...")
    t0 = time.time()
    try:
        resp = provider.generate(
            "Reply with exactly: OK",
            max_tokens=10,
            system_prompt="You are a test responder. Reply with exactly what is requested.",
        )
        elapsed = time.time() - t0
        print(f"  Response : {resp.text!r}")
        print(f"  Model    : {resp.model}")
        print(f"  Tokens   : {resp.tokens_used}")
        print(f"  Latency  : {elapsed:.2f}s")
        print("  Status   : OK ✓")
    except Exception as e:
        print(f"  Status   : FAILED — {e}")
        print(f"{'='*55}\n")
        return 1

    print(f"{'='*55}\n")
    return 0


async def run_search(args):
    """Execute the search + score + generate resume pipeline."""
    notifier = NotificationManager()

    pm = ProfileManager(Path(args.profile))
    if not pm.exists():
        logger.error(f"Profile not found: {args.profile}")
        return 1

    profile = pm.load()
    logger.info(f"Profile: {profile.full_name} ({profile.total_years_experience()} yrs exp)")

    if not os.environ.get("GROK_API_KEY"):
        logger.warning(
            "GROK_API_KEY not set — resume summaries will use rule-based fallback. "
            "Set GROK_API_KEY for LLM-tailored resumes."
        )

    drivers = _build_drivers(args.portals)
    if not drivers:
        logger.error("No portal drivers configured.")
        return 1

    config = SearchConfig(
        keywords=args.keywords,
        location=args.location,
        remote_only=args.remote,
        max_results=args.max_results,
    )

    work_auth = os.environ.get("WORK_AUTHORIZATION", "Yes, authorized to work in India")
    remote_pref = os.environ.get("REMOTE_PREFERENCE", "Remote or Hybrid preferred; open to on-site")

    orch = Orchestrator(
        drivers=drivers,
        profile=profile,
        min_score=args.min_score,
        auto_apply=args.auto_apply,
        salary_expectation=args.salary,
        notice_period=args.notice_period,
        work_authorization=work_auth,
        remote_preference=remote_pref,
    )

    logger.info(f"Searching: {args.keywords} | portals={args.portals} | max={args.max_results}")
    result = await orch.run(config)

    notifier.notify_pipeline_complete(result)
    print(f"\n{'='*55}")
    print(f"  Jobs discovered   : {result.jobs_discovered}")
    print(f"  New (unique)      : {result.jobs_new}")
    print(f"  Duplicates skipped: {result.jobs_duplicates}")
    print(f"  Scored >= {args.min_score:.0f}     : {result.jobs_scored}")
    print(f"  Resumes generated : {result.resumes_generated}")
    if args.auto_apply:
        print(f"  Applications sent : {result.applications_submitted}")
        print(f"  Apply failures    : {result.applications_failed}")
    if result.errors:
        print(f"  Errors            : {len(result.errors)}")
        for e in result.errors[:5]:
            print(f"    • {e}")
    print(f"{'='*55}\n")
    return 0


def run_generate(args):
    """Generate a tailored LaTeX PDF resume for a specific JD."""
    import hashlib
    from src.generator.content_selector import ContentSelector
    from src.generator.latex_renderer import generate_latex_resume

    pm = ProfileManager(Path(args.profile))
    if not pm.exists():
        print(f"Profile not found: {args.profile}")
        return 1
    profile = pm.load()

    jd_text = Path(args.jd).read_text(encoding="utf-8")
    jd_hash = hashlib.md5(jd_text.encode()).hexdigest()[:8]

    if not os.environ.get("GROK_API_KEY") and not args.no_llm:
        logger.warning("GROK_API_KEY not set — using rule-based content selection.")

    selector = ContentSelector(use_llm=not args.no_llm)
    content = selector.select(profile, jd_text)

    files = generate_latex_resume(content, args.output, job_id=jd_hash)
    print(f"\n{'='*55}")
    print(f"  Profile   : {profile.full_name}")
    print(f"  Summary   : {content.summary[:80]}...")
    print(f"  Skills    : {len(content.skills)} selected")
    print(f"  Roles     : {len(content.experience)}")
    print(f"  .tex file : {files.get('tex', 'N/A')}")
    print(f"  PDF       : {files.get('pdf') or '(compile failed — see .tex)' }")
    if files.get("error"):
        print(f"  Error     : {files['error']}")
    print(f"{'='*55}\n")
    return 0


def run_profile(args):
    """Display candidate profile."""
    pm = ProfileManager(Path(args.path))
    if not pm.exists():
        print(f"Profile not found at {args.path}")
        return 1
    profile = pm.load()
    if args.show:
        print(f"\n{'='*50}")
        print(f"  Name:           {profile.full_name}")
        print(f"  Email:          {profile.email}")
        print(f"  Phone:          {profile.phone}")
        print(f"  Location:       {profile.location}")
        print(f"  Experience:     {profile.total_years_experience()} years")
        print(f"  LinkedIn:       {profile.linkedin or 'N/A'}")
        print(f"  GitHub:         {profile.github or 'N/A'}")
        print(f"  Skills:         {len(profile.get_all_skill_names())} skills")
        print(f"  Summaries:      {len(profile.summaries)}")
        print(f"  Roles:          {len(profile.experience)}")
        print(f"  Education:      {len(profile.education)}")
        print(f"  Certifications: {len(profile.certifications)}")
        print(f"  Projects:       {len(profile.projects)}")
        print(f"  Q&A bank:       {len(profile.qa_bank)} entries")
        print(f"{'='*50}\n")
    return 0


def run_analyze(args):
    """ATS score a resume against a JD and show suggestions."""
    from src.analyzer.scorer import ATSScorer
    from src.analyzer.suggestions import generate_suggestions

    resume_text = Path(args.resume).read_text(encoding="utf-8")
    jd_text = Path(args.jd).read_text(encoding="utf-8")

    scorer = ATSScorer()
    result = scorer.score(resume_text, jd_text)
    suggestions = generate_suggestions(result)

    print(f"\n{'='*55}")
    print(f"  ATS Score: {result.overall_score:.1f}/100")
    print(f"{'='*55}")
    print(f"  Keyword Match       : {result.breakdown.keyword_match:.1f}")
    print(f"  Section Completeness: {result.breakdown.section_completeness:.1f}")
    print(f"  Keyword Density     : {result.breakdown.keyword_density:.1f}")
    print(f"  Experience Relev.   : {result.breakdown.experience_relevance:.1f}")
    print(f"  Formatting          : {result.breakdown.formatting:.1f}")
    if result.missing_keywords:
        print()
        print("  Missing Keywords:")
        for kw in result.missing_keywords[:12]:
            imp = kw.get("importance", "")
            print(f"    • {kw['keyword']}  [{imp}]")
    print()
    print("  Suggestions:")
    for s in suggestions:
        print(f"    {s}")
    print(f"{'='*55}\n")
    return 0


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "setup-browser":
        return asyncio.run(run_setup_browser(args))
    elif args.command == "test-llm":
        return run_test_llm(args)
    elif args.command == "search":
        return asyncio.run(run_search(args))
    elif args.command == "generate":
        return run_generate(args)
    elif args.command == "profile":
        return run_profile(args)
    elif args.command == "analyze":
        return run_analyze(args)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
