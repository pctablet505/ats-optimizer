"""LinkedIn portal driver.

Inherits browser lifecycle, stealth, and pagination from BaseBrowserDriver.
This file contains only LinkedIn-specific logic:
  - URL construction
  - Job card extraction (uses data-job-id + ARIA selectors)
  - Full JD extraction (clicks "Show more", then JS innerText on #job-details)
  - Session check
  - Easy Apply automation

Selectors are loaded from config/selectors/linkedin.yaml so DOM changes
can be patched without touching Python code.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from src.automation.drivers.base import (
    BaseBrowserDriver,
    DiscoveredJob,
    SearchConfig,
    _playwright_available,
)

logger = logging.getLogger(__name__)

_SELECTORS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "selectors" / "linkedin.yaml"
)


def _load_selectors() -> dict[str, Any]:
    if _SELECTORS_PATH.exists():
        with open(_SELECTORS_PATH) as fh:
            return yaml.safe_load(fh) or {}
    logger.warning("LinkedIn selectors not found: %s", _SELECTORS_PATH)
    return {}


class LinkedInDriver(BaseBrowserDriver):
    """LinkedIn job search and Easy Apply driver.

    Anti-detection measures (all inherited from BaseBrowserDriver):
      • playwright-stealth: patches webdriver, plugins, WebGL, chrome.runtime, languages
      • Lognormal delays via HumanSimulator (realistic timing distribution)
      • Mouse movement before every click (generates real mousemove events)
      • scroll_to_read() before extracting content
      • Persistent Chrome profile (carries cookies / session state)

    Full job description strategy:
      1. Navigate to job detail page
      2. Click "Show more" button (expands CSS-truncated description)
      3. Extract via JS `innerText` on `#job-details` (respects visibility after expand)
    """

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: str = "data/browser_profiles/chrome_bot/linkedin",
    ):
        super().__init__(headless=headless, user_data_dir=user_data_dir)
        self.sel = _load_selectors()

    # ── Required abstract implementations ────────────────────────────────────

    def driver_name(self) -> str:
        return "linkedin"

    def _get_search_url(self, config: SearchConfig) -> str:
        kw = "%20".join(config.keywords)
        loc = config.location.replace(" ", "%20")
        params = [f"keywords={kw}", f"location={loc}", "f_TPR=r604800", "sortBy=DD"]
        if config.remote_only:
            params.append("f_WT=2")
        if config.experience_level:
            exp_map = {"entry": "1", "mid": "2,3", "senior": "4,5"}
            if lv := exp_map.get(config.experience_level):
                params.append(f"f_E={lv}")
        return "https://www.linkedin.com/jobs/search/?" + "&".join(params)

    async def _check_session(self) -> bool:
        """Navigate to the feed and check for the profile nav element."""
        await self._page.goto(
            "https://www.linkedin.com/feed/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await self.sim.random_pause(1.5, 2.5)
        nav = await self._page.query_selector(
            ".global-nav__me, [data-test-global-nav-me-avatar]"
        )
        logged_in = nav is not None
        logger.info(
            "LinkedIn: %s", "logged in" if logged_in else "NOT logged in — run setup-browser"
        )
        return logged_in

    async def _extract_job_cards(self) -> list[DiscoveredJob]:
        """Parse job cards from the current LinkedIn search results page.

        Selector strategy (most-to-least stable):
          1. [data-job-id]           — LinkedIn's own data attribute (very stable)
          2. aria-label on title link — semantic, doesn't depend on class names
          3. <strong> inside title link — text fallback
        """
        search_sel = self.sel.get("search", {})
        card_sel = search_sel.get("job_cards", "[data-job-id]")

        try:
            await self._page.wait_for_selector(card_sel, timeout=8000)
        except Exception:
            logger.debug("LinkedIn: timeout waiting for job cards with '%s'", card_sel)

        cards = await self._page.query_selector_all(card_sel)
        if not cards:
            # Check if we've been redirected to a login page
            if await self._page.query_selector("input#username, .login__form"):
                logger.error("LinkedIn: redirected to login — session expired")
            else:
                logger.debug("LinkedIn: no cards found with '%s'", card_sel)
            return []

        link_sel = search_sel.get("job_card_link", "a.job-card-list__title--link")
        company_sel = search_sel.get(
            "job_card_company", ".artdeco-entity-lockup__subtitle span"
        )
        location_sel = search_sel.get(
            "job_card_location",
            ".artdeco-entity-lockup__caption span, "
            ".job-card-container__metadata-wrapper li:first-child span",
        )

        jobs: list[DiscoveredJob] = []
        for i, card in enumerate(cards):
            try:
                link_el = await card.query_selector(link_sel)
                if not link_el:
                    continue

                # Prefer aria-label (stable semantic attribute), fall back to text
                title = (await link_el.get_attribute("aria-label") or "").strip()
                if len(title) < 3:
                    strong = await card.query_selector("strong")
                    title = (
                        (await strong.inner_text()).strip()
                        if strong
                        else (await link_el.inner_text()).strip()
                    )

                company_el = await card.query_selector(company_sel)
                company = (await company_el.inner_text()).strip() if company_el else ""

                loc_el = await card.query_selector(location_sel)
                location = (await loc_el.inner_text()).strip() if loc_el else ""

                url = (await link_el.get_attribute("href") or "").strip()
                if not (title and company and url):
                    logger.debug("LinkedIn card %d: incomplete (t=%s c=%s u=%s)", i, bool(title), bool(company), bool(url))
                    continue

                if url.startswith("/"):
                    url = "https://www.linkedin.com" + url
                url = url.split("?")[0]
                external_id = url.rstrip("/").split("/")[-1]

                jobs.append(
                    DiscoveredJob(
                        title=title,
                        company=company,
                        url=url,
                        source="linkedin",
                        location=location,
                        external_id=external_id,
                    )
                )
            except Exception as exc:
                logger.debug("LinkedIn card %d parse error: %s", i, exc)

        return jobs

    async def _has_next_page(self) -> bool:
        sel = self.sel.get("search", {}).get(
            "next_page_button", "button[aria-label='View next page']"
        )
        return await self._page.query_selector(sel) is not None

    async def _goto_next_page(self) -> None:
        sel = self.sel.get("search", {}).get(
            "next_page_button", "button[aria-label='View next page']"
        )
        await self.sim.human_move_and_click(self._page, sel)
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

    async def _get_full_jd_text(self) -> str:
        """Expand the job description (Show more) then extract via JS innerText.

        Using `innerText` (not `textContent`) means we only get text that is
        visually rendered — which requires clicking "Show more" first so the
        previously hidden paragraphs are visible.
        """
        # Attempt to click the "Show more" / expand button
        for show_sel in [
            ".jobs-description__footer-button button",
            "button.jobs-description__footer-button",
            "button[aria-label*='Show more']",
            "button[aria-expanded='false']",
        ]:
            try:
                btn = await self._page.query_selector(show_sel)
                if btn:
                    await self.sim.human_move_and_click(self._page, show_sel)
                    await self.sim.random_pause(0.5, 1.0)
                    break
            except Exception:
                pass

        # Extract via JS — falls back through multiple container selectors
        text: str = await self._page.evaluate(
            """
            () => {
                const selectors = [
                    '#job-details',
                    '.jobs-description__content',
                    '.jobs-description',
                    '[class*="job-view-layout"] .description__text',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.trim().length > 50) {
                        return el.innerText.trim();
                    }
                }
                return '';
            }
            """
        )
        return (text or "").strip()

    # ── Stub data ─────────────────────────────────────────────────────────────

    def _stub_jobs(self, config: SearchConfig) -> list[DiscoveredJob]:
        loc = config.location or "Bengaluru"
        return [
            DiscoveredJob(
                title="Senior ML Engineer",
                company="TechCorp India",
                url="https://linkedin.com/jobs/view/mock-001",
                source="linkedin",
                location=loc,
                description_text=(
                    "Senior ML Engineer with Python, PyTorch, and MLOps experience."
                ),
                external_id="mock-001",
            ),
            DiscoveredJob(
                title="Staff Software Engineer",
                company="InnovateLabs",
                url="https://linkedin.com/jobs/view/mock-002",
                source="linkedin",
                location=loc,
                description_text="Staff Software Engineer — distributed systems focus.",
                external_id="mock-002",
            ),
        ]

    # ── LinkedIn Easy Apply ───────────────────────────────────────────────────

    async def apply(
        self,
        job: DiscoveredJob,
        resume_path: str,
        answers: dict | None = None,
    ) -> dict:
        if not _playwright_available():
            return {
                "status": "stub_submitted",
                "job_url": job.url,
                "message": "Playwright not installed",
            }

        answers = answers or {}
        try:
            await self._start_browser()
            if not await self._check_session():
                return {"status": "failed", "message": "Not logged in", "job_url": job.url}

            await self._page.goto(job.url, wait_until="domcontentloaded")
            await self.sim.random_pause(2.0, 3.0)

            from src.automation.captcha_handler import CaptchaHandler
            detection = await CaptchaHandler().detect_on_page(self._page)
            if detection.detected:
                return {"status": "captcha", "message": detection.message, "job_url": job.url}

            easy_apply_sel = (
                ".jobs-apply-button--top-card button, button.jobs-apply-button"
            )
            if not await self._page.query_selector(easy_apply_sel):
                return {
                    "status": "failed",
                    "message": "Easy Apply button not found",
                    "job_url": job.url,
                }

            await self.sim.human_move_and_click(self._page, easy_apply_sel)
            await self.sim.random_pause(1.5, 2.5)

            result = await self._fill_easy_apply(resume_path, answers)
            result["job_url"] = job.url
            return result

        except Exception as exc:
            return {"status": "failed", "message": str(exc), "job_url": job.url}
        finally:
            await self._close_browser()

    async def _fill_easy_apply(self, resume_path: str, answers: dict) -> dict:
        modal = self.sel.get("easy_apply", {})
        rate = self.sel.get("rate_limits", {})
        delay = rate.get("apply_step_delay_ms", 2500) / 1000

        for _ in range(15):
            await self.sim.random_pause(delay, delay + 1.0)

            # Upload resume if an upload input is present on this step
            file_input = await self._page.query_selector(
                modal.get("file_upload", "input[type='file']")
            )
            if file_input and resume_path and Path(resume_path).exists():
                await file_input.set_input_files(resume_path)
                await self.sim.random_pause(0.8, 1.5)

            # Submit
            submit_sel = modal.get(
                "submit_button", "button[aria-label='Submit application']"
            )
            if await self._page.query_selector(submit_sel):
                await self.sim.human_move_and_click(self._page, submit_sel)
                await self.sim.random_pause(2.0, 3.0)
                return {"status": "submitted", "message": "Easy Apply submitted"}

            # Review step
            review_sel = modal.get(
                "review_button", "button[aria-label='Review your application']"
            )
            if await self._page.query_selector(review_sel):
                await self.sim.human_move_and_click(self._page, review_sel)
                continue

            # Continue to next step
            next_sel = modal.get(
                "next_button", "button[aria-label='Continue to next step']"
            )
            if await self._page.query_selector(next_sel):
                await self.sim.human_move_and_click(self._page, next_sel)
            else:
                break

        return {"status": "failed", "message": "Easy Apply did not reach submission"}
