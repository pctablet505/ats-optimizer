"""Base portal driver interface for job search/apply automation."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Module-level helpers (shared by all portal drivers) ──────────────────────

def _playwright_available() -> bool:
    """Return True if the playwright package is importable."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _chrome_installed() -> bool:
    """Return True if real Chrome is installed at a well-known system path."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
    ]
    return any(os.path.exists(p) for p in candidates if p)


@dataclass
class DiscoveredJob:
    """A job discovered by a portal driver."""
    title: str
    company: str
    url: str
    source: str  # "linkedin", "indeed", "glassdoor"
    location: str = ""
    salary_range: str = ""
    description_text: str = ""
    external_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchConfig:
    """Parameters for a job search."""
    keywords: list[str] = field(default_factory=list)
    location: str = ""
    remote_only: bool = False
    experience_level: str = ""  # entry, mid, senior
    posted_within_days: int = 7
    max_results: int = 50
    salary_min: int | None = None


class BasePortalDriver(ABC):
    """Abstract base class for job portal drivers.

    Each portal (LinkedIn, Indeed, etc.) implements this interface
    to provide search and application capabilities.
    """

    @abstractmethod
    async def search(self, config: SearchConfig) -> list[DiscoveredJob]:
        """Search for jobs matching the given criteria.

        Args:
            config: Search parameters.

        Returns:
            List of discovered jobs.
        """
        ...

    @abstractmethod
    async def get_job_details(self, url: str) -> DiscoveredJob:
        """Fetch full details for a specific job listing.

        Args:
            url: The job listing URL.

        Returns:
            Job with full description_text populated.
        """
        ...

    @abstractmethod
    async def apply(self, job: DiscoveredJob, resume_path: str, answers: dict | None = None) -> dict:
        """Submit an application for a job.

        Args:
            job: The job to apply to.
            resume_path: Path to the tailored resume file.
            answers: Pre-answered questions (from Q&A bank).

        Returns:
            Dict with application result, e.g. {"status": "submitted", "confirmation_id": "..."}
        """
        ...

    @abstractmethod
    def driver_name(self) -> str:
        """Return the name/identifier for this driver."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the driver is configured and ready to use."""
        ...


# ── Shared browser automation base ───────────────────────────────────────────

class BaseBrowserDriver(BasePortalDriver):
    """Shared browser lifecycle, stealth, and pagination for all portal drivers.

    Subclasses implement 6 portal-specific abstract methods:
        driver_name()           — e.g. "linkedin"
        _get_search_url()       — build portal search URL
        _extract_job_cards()    — parse job cards from current results page
        _has_next_page()        — True if another results page exists
        _goto_next_page()       — navigate to the next results page
        _get_full_jd_text()     — extract full description from a job detail page
        _check_session()        — True if user is logged in (or login not required)

    Everything else — browser launch, playwright-stealth, pagination loop,
    JD fetching with lognormal delays, and scroll-to-read simulation — is
    handled here so portal drivers stay focused on their own selectors.
    """

    def __init__(self, headless: bool = False, user_data_dir: str = ""):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.sel: dict[str, Any] = {}   # populated by each subclass from YAML
        self._pw = None
        self._context = None
        self._page = None

        # Import lazily to avoid a hard dependency in tests that mock the browser
        from src.automation.human_simulator import HumanSimulator
        self.sim = HumanSimulator()

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    async def _start_browser(self) -> None:
        """Launch a persistent Chrome context with playwright-stealth applied.

        playwright-stealth patches ~12 fingerprint signals (navigator.webdriver,
        plugins, WebGL renderer, chrome.runtime, languages, iframe ContentWindow …)
        by injecting init scripts before every page load.
        """
        from playwright.async_api import async_playwright

        _stealth = None
        try:
            from playwright_stealth import Stealth
            _stealth = Stealth(init_scripts_only=True)
        except ImportError:
            logger.warning(
                "%s: playwright-stealth not installed; fingerprint masking disabled. "
                "Run: pip install playwright-stealth",
                self.driver_name(),
            )

        profile_dir = Path(self.user_data_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

        self._pw = await async_playwright().start()

        launch_kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1440,900",
            ],
            "viewport": {"width": 1440, "height": 900},
            "locale": "en-IN",
            "timezone_id": "Asia/Kolkata",
        }

        if _chrome_installed():
            launch_kwargs["channel"] = "chrome"
            logger.info("%s: using real Chrome (best fingerprint)", self.driver_name())
        else:
            logger.warning(
                "%s: real Chrome not found — using bundled Chromium (higher detection risk). "
                "Install Chrome from https://www.google.com/chrome/",
                self.driver_name(),
            )

        self._context = await self._pw.chromium.launch_persistent_context(
            str(profile_dir), **launch_kwargs
        )

        # Apply stealth to the persistent context — adds init scripts that run
        # before every new page in this context.
        if _stealth is not None:
            try:
                await _stealth.apply_stealth_async(self._context)
                logger.debug("%s: playwright-stealth applied", self.driver_name())
            except Exception as exc:
                logger.warning("%s: stealth apply failed: %s", self.driver_name(), exc)

        self._page = await self._context.new_page()

    async def _close_browser(self) -> None:
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._pw = self._context = self._page = None

    # ── Public API (concrete) ─────────────────────────────────────────────────

    async def search(self, config: "SearchConfig") -> list["DiscoveredJob"]:
        """Search for jobs. Returns stub data when Playwright is unavailable."""
        if not _playwright_available():
            logger.info("%s: Playwright unavailable — returning stub data", self.driver_name())
            return self._stub_jobs(config)

        try:
            await self._start_browser()
            if not await self._check_session():
                logger.warning(
                    "%s: not logged in. Run: python -m src.cli setup-browser --portal %s",
                    self.driver_name(), self.driver_name(),
                )
            return await self._run_search(config)
        except Exception as exc:
            logger.error("%s search error: %s", self.driver_name(), exc, exc_info=True)
            return []
        finally:
            await self._close_browser()

    async def get_job_details(self, url: str) -> "DiscoveredJob":
        """Fetch full job description from a single URL."""
        if not _playwright_available():
            return DiscoveredJob(
                title="", company="", url=url,
                source=self.driver_name(), description_text="stub",
            )
        try:
            await self._start_browser()
            await self._check_session()
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self.sim.random_pause(1.5, 2.5)
            await self.sim.scroll_to_read(self._page, reading_time=1.5)
            text = await self._get_full_jd_text()
            return DiscoveredJob(
                title="", company="", url=url,
                source=self.driver_name(), description_text=text,
            )
        except Exception as exc:
            logger.error("%s get_job_details error: %s", self.driver_name(), exc)
            return DiscoveredJob(title="", company="", url=url, source=self.driver_name())
        finally:
            await self._close_browser()

    async def apply(
        self,
        job: "DiscoveredJob",
        resume_path: str,
        answers: dict | None = None,
    ) -> dict:
        """Apply to a job. Subclasses override for portal-specific flows."""
        return {
            "status": "not_implemented",
            "job_url": job.url,
            "message": f"Apply not implemented for {self.driver_name()}",
        }

    async def is_available(self) -> bool:
        return True

    # ── Shared pagination + JD fetch logic ───────────────────────────────────

    async def _run_search(self, config: "SearchConfig") -> list["DiscoveredJob"]:
        """Generic search loop: build URL → scroll → paginate → fetch JDs."""
        rate = self.sel.get("rate_limits", {})
        max_jobs = min(config.max_results, rate.get("max_jobs_per_session", 25))

        url = self._get_search_url(config)
        logger.info("%s: GET %s", self.driver_name(), url)

        await self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await self.sim.random_pause(3.5, 6.0)
        await self.sim.scroll_to_read(self._page, reading_time=1.5)

        jobs: list[DiscoveredJob] = []
        page_num = 0

        while len(jobs) < max_jobs:
            page_num += 1
            new_jobs = await self._extract_job_cards()
            jobs.extend(new_jobs)
            logger.info(
                "%s page %d: %d cards → %d total",
                self.driver_name(), page_num, len(new_jobs), len(jobs),
            )

            if len(new_jobs) == 0 or len(jobs) >= max_jobs:
                break
            if not await self._has_next_page():
                logger.debug("%s: no next page — stopping", self.driver_name())
                break

            # Lognormal wait between pages (clusters around mean, occasional longer)
            await self.sim.random_pause(6.5, 11.0)
            await self._goto_next_page()
            await self.sim.random_pause(3.5, 6.0)

        result = jobs[:max_jobs]
        logger.info("%s: fetching full JDs for %d jobs", self.driver_name(), len(result))
        await self._fetch_descriptions(result)
        return result

    async def _fetch_descriptions(self, jobs: list["DiscoveredJob"]) -> None:
        """Navigate to each job's detail page and extract the full description."""
        rate = self.sel.get("rate_limits", {})
        base_delay = rate.get("job_detail_delay_ms", 5000) / 1000

        for i, job in enumerate(jobs):
            if job.description_text or not job.url:
                continue
            try:
                if i > 0:
                    # Staggered lognormal delays between consecutive JD fetches
                    await self.sim.random_pause(base_delay, base_delay + 3.5)

                await self._page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
                await self.sim.random_pause(2.0, 3.5)
                await self.sim.scroll_to_read(self._page, reading_time=1.2)

                job.description_text = await self._get_full_jd_text()
                logger.debug(
                    "  JD '%s': %s (%d chars)",
                    job.title,
                    "ok" if job.description_text else "empty",
                    len(job.description_text),
                )
            except Exception as exc:
                logger.debug("  JD fetch failed for %s: %s", job.url, exc)

    def _stub_jobs(self, config: "SearchConfig") -> list["DiscoveredJob"]:
        """Override in subclasses to return portal-specific stub data."""
        return []

    # ── Abstract: implemented by each portal driver ───────────────────────────

    @abstractmethod
    def driver_name(self) -> str:
        """Short identifier for this portal, e.g. 'linkedin', 'indeed', 'naukri'."""
        ...

    @abstractmethod
    def _get_search_url(self, config: "SearchConfig") -> str:
        """Build the search results URL for this portal."""
        ...

    @abstractmethod
    async def _extract_job_cards(self) -> list["DiscoveredJob"]:
        """Extract job listings from the current search results page."""
        ...

    @abstractmethod
    async def _has_next_page(self) -> bool:
        """Return True if a next-page button/link is present."""
        ...

    @abstractmethod
    async def _goto_next_page(self) -> None:
        """Navigate to the next page of search results."""
        ...

    @abstractmethod
    async def _get_full_jd_text(self) -> str:
        """Return full job description text from the current job detail page.

        Should click any "Show more" button before extracting, and use
        JS innerText (not inner_html) so CSS-hidden content is included
        only after it's revealed.
        """
        ...

    @abstractmethod
    async def _check_session(self) -> bool:
        """Return True if the browser session appears to be authenticated.

        Portals that don't require login (e.g. Naukri search, Indeed search)
        should return True unconditionally.
        """
        ...
