"""Naukri.com portal driver — Indian job market.

Inherits browser lifecycle, stealth, and pagination from BaseBrowserDriver.
Naukri search works without login (login gives richer results and enables Apply).

URL pattern:
    https://www.naukri.com/{keywords}-jobs-in-{location}?jobAge=7

Full JD strategy:
    Most Naukri job pages load the full description immediately; no "Show more"
    button to worry about. We use JS innerText on the JD container element.

Selectors are loaded from config/selectors/naukri.yaml.

NOTE: Naukri's DOM is less stable than LinkedIn's data-job-id approach.
      Multiple fallback selectors are used throughout so minor DOM changes
      don't break the pipeline. Tune selectors in naukri.yaml as needed.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from src.automation.drivers.base import BaseBrowserDriver, DiscoveredJob, SearchConfig

logger = logging.getLogger(__name__)

_SELECTORS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "selectors" / "naukri.yaml"
)


def _load_selectors() -> dict[str, Any]:
    if _SELECTORS_PATH.exists():
        with open(_SELECTORS_PATH) as fh:
            return yaml.safe_load(fh) or {}
    logger.warning("Naukri selectors not found: %s", _SELECTORS_PATH)
    return {}


class NaukriDriver(BaseBrowserDriver):
    """Naukri.com job search driver for the Indian job market.

    Search does not require login. For Indian roles (Bengaluru, Hyderabad, Pune,
    Delhi NCR, Mumbai) this portal is often richer than LinkedIn/Indeed.
    """

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: str = "data/browser_profiles/chrome_bot/naukri",
    ):
        super().__init__(headless=headless, user_data_dir=user_data_dir)
        self.sel = _load_selectors()

    # ── Abstract implementations ──────────────────────────────────────────────

    def driver_name(self) -> str:
        return "naukri"

    def _get_search_url(self, config: SearchConfig) -> str:
        """Build Naukri search URL.

        Naukri uses a path-based URL:
            /python-developer-jobs-in-bengaluru?jobAge=7&experience=3
        Keywords and location are lowercased and space→hyphen converted.
        """
        kw = "-".join(w.lower().replace(" ", "-") for w in config.keywords)
        loc = config.location.lower().replace(" ", "-")
        params = ["jobAge=7"]
        if config.experience_level:
            exp_map = {"entry": "0", "mid": "3", "senior": "6"}
            if exp := exp_map.get(config.experience_level):
                params.append(f"experience={exp}")
        return f"https://www.naukri.com/{kw}-jobs-in-{loc}?" + "&".join(params)

    async def _check_session(self) -> bool:
        """Navigate to Naukri homepage; check for logged-in user indicator.

        Returns True regardless — search works without login.
        """
        await self._page.goto(
            "https://www.naukri.com/", wait_until="domcontentloaded", timeout=30000
        )
        await self.sim.random_pause(2.0, 3.5)
        indicator = await self._page.query_selector(
            "[class*='nI-gNb-drawer__user'], .nI-gNb-user-text, [data-ga-track*='login-menu']"
        )
        if indicator:
            logger.info("Naukri: logged in")
        else:
            logger.info("Naukri: not logged in — search still works")
        return True  # Search works without authentication

    async def _extract_job_cards(self) -> list[DiscoveredJob]:
        """Parse job cards using multiple fallback selectors.

        Naukri has changed its card class names across product iterations.
        We try a priority list until we find cards, then use JS attribute
        reads for inner fields (more stable than class-based selectors).
        """
        search_sel = self.sel.get("search", {})

        # Priority order: newest → legacy → generic
        card_candidates = [
            search_sel.get("job_cards", ""),
            "article.jobTuple",
            ".cust-job-tuple",
            "[class*='job-tuple']",
            ".list.left-list article",
        ]
        card_sel = ""
        cards = []
        for candidate in card_candidates:
            if not candidate:
                continue
            found = await self._page.query_selector_all(candidate)
            if found:
                card_sel = candidate
                cards = found
                break

        if not cards:
            try:
                await self._page.wait_for_selector(
                    "article.jobTuple, .cust-job-tuple, [class*='job-tuple']",
                    timeout=8000,
                )
                for candidate in card_candidates[1:]:
                    cards = await self._page.query_selector_all(candidate)
                    if cards:
                        break
            except Exception:
                pass

        if not cards:
            logger.debug("Naukri: no job cards found")
            return []

        logger.debug("Naukri: %d cards with '%s'", len(cards), card_sel)

        title_sel = search_sel.get("job_card_title", ".title a, a.title, [class*='title'] a")
        company_sel = search_sel.get(
            "job_card_company", ".subTitle a, a.subTitle, [class*='company'] a, .comp-name"
        )
        location_sel = search_sel.get(
            "job_card_location",
            ".location span, [class*='location'] span, li.location, .loc-name",
        )

        jobs: list[DiscoveredJob] = []
        for card in cards:
            try:
                title_el = await card.query_selector(title_sel)
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                url = (await title_el.get_attribute("href") or "").strip()

                company_el = await card.query_selector(company_sel)
                company = (await company_el.inner_text()).strip() if company_el else ""

                location_el = await card.query_selector(location_sel)
                location = (await location_el.inner_text()).strip() if location_el else ""

                salary_el = await card.query_selector(
                    ".salary, [class*='salary'], .sal-wrap"
                )
                salary = (await salary_el.inner_text()).strip() if salary_el else ""

                if not (title and url):
                    continue
                if not url.startswith("http"):
                    url = "https://www.naukri.com" + url

                jobs.append(
                    DiscoveredJob(
                        title=title,
                        company=company,
                        url=url,
                        source="naukri",
                        location=location,
                        salary_range=salary,
                        external_id=url.rstrip("/").split("/")[-1],
                    )
                )
            except Exception as exc:
                logger.debug("Naukri card parse error: %s", exc)

        return jobs

    async def _has_next_page(self) -> bool:
        sel = self.sel.get("search", {}).get(
            "next_page_button", "a.fright.fs14.btn-secondary, a[class*='next']"
        )
        return await self._page.query_selector(sel) is not None

    async def _goto_next_page(self) -> None:
        """Navigate to next page — prefer href navigation over click (more reliable)."""
        for sel in [
            self.sel.get("search", {}).get("next_page_button", ""),
            "a.fright.fs14.btn-secondary",
            "a[class*='next']",
            "span[class*='next'] a",
        ]:
            if not sel:
                continue
            btn = await self._page.query_selector(sel)
            if not btn:
                continue
            href = await btn.get_attribute("href")
            if href:
                if not href.startswith("http"):
                    href = "https://www.naukri.com" + href
                await self._page.goto(href, wait_until="domcontentloaded", timeout=30000)
                return
            # No href — click the button
            await self.sim.human_move_and_click(self._page, sel)
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            return

    async def _get_full_jd_text(self) -> str:
        """Extract full job description text from a Naukri job detail page.

        Naukri typically renders the full JD immediately (no Show more button).
        We try several container selectors via JS innerText.
        """
        text: str = await self._page.evaluate(
            """
            () => {
                const selectors = [
                    '[class*="jd-desc"]',
                    '.job-desc',
                    '#job_description',
                    '.dang-inner-html',
                    '[class*="jobDescriptionSection"]',
                    '.jd-desc',
                    '.job-description-main-text',
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
        kw = " ".join(config.keywords) if config.keywords else "engineer"
        loc = config.location or "Bengaluru"
        return [
            DiscoveredJob(
                title=f"{kw.title()} Engineer",
                company="TechTalent India",
                url="https://www.naukri.com/job-listings-mock-n001",
                source="naukri",
                location=loc,
                description_text=f"Looking for {kw} engineer at a growing startup.",
                external_id="mock-n001",
            ),
            DiscoveredJob(
                title=f"Senior {kw.title()} Developer",
                company="InfyTech Solutions",
                url="https://www.naukri.com/job-listings-mock-n002",
                source="naukri",
                location=loc,
                description_text=f"Senior {kw} developer role with leadership responsibilities.",
                external_id="mock-n002",
            ),
        ]
