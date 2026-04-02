"""Indeed portal driver.

Inherits browser lifecycle, stealth, and pagination from BaseBrowserDriver.
Indeed search works without login, so _check_session() always returns True.

Full JD strategy:
  1. Navigate to viewjob URL
  2. Click "Show more" if the description is truncated
  3. Extract via JS innerText on #jobDescriptionText

Selectors are loaded from config/selectors/indeed.yaml.
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
    Path(__file__).resolve().parents[3] / "config" / "selectors" / "indeed.yaml"
)


def _load_selectors() -> dict[str, Any]:
    if _SELECTORS_PATH.exists():
        with open(_SELECTORS_PATH) as fh:
            return yaml.safe_load(fh) or {}
    logger.warning("Indeed selectors not found: %s", _SELECTORS_PATH)
    return {}


class IndeedDriver(BaseBrowserDriver):
    """Indeed job search driver.

    Indeed does not require login for search results, so this driver
    works out-of-the-box without setup-browser (though logging in gives
    richer results and enables Indeed Apply).
    """

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: str = "data/browser_profiles/chrome_bot/indeed",
    ):
        super().__init__(headless=headless, user_data_dir=user_data_dir)
        self.sel = _load_selectors()

    def driver_name(self) -> str:
        return "indeed"

    def _get_search_url(self, config: SearchConfig) -> str:
        kw = "+".join(config.keywords)
        loc = config.location.replace(" ", "+")
        params = [f"q={kw}", f"l={loc}", "fromage=7", "sort=date"]
        if config.remote_only:
            params.append("remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11")
        if config.salary_min:
            params.append(f"salary={config.salary_min}")
        return "https://www.indeed.com/jobs?" + "&".join(params)

    async def _check_session(self) -> bool:
        return True  # Indeed search works without login

    async def _extract_job_cards(self) -> list[DiscoveredJob]:
        search_sel = self.sel.get("search", {})
        card_sel = search_sel.get("job_cards", "[data-jk]")
        try:
            await self._page.wait_for_selector(card_sel, timeout=8000)
        except Exception:
            for alt in [".result", ".tapItem", ".jobCard"]:
                if await self._page.query_selector(alt):
                    card_sel = alt
                    break

        cards = await self._page.query_selector_all(card_sel)
        if not cards:
            logger.debug("Indeed: no job cards found with '%s'", card_sel)
            return []

        title_sel = search_sel.get("job_card_title", "h2.jobTitle a, [data-jk] h2 a, .jobTitle a")
        company_sel = search_sel.get("job_card_company", "[data-testid='company-name'], .companyName")
        location_sel = search_sel.get("job_card_location", "[data-testid='text-location'], .companyLocation")

        jobs: list[DiscoveredJob] = []
        for card in cards:
            try:
                title_el = await card.query_selector(title_sel)
                if not title_el:
                    continue

                title = (await title_el.inner_text()).strip()
                company_el = await card.query_selector(company_sel)
                company = (await company_el.inner_text()).strip() if company_el else ""
                location_el = await card.query_selector(location_sel)
                location = (await location_el.inner_text()).strip() if location_el else ""
                salary_el = await card.query_selector(".estimated-salary, [data-testid='attribute_snippet_testid']")
                salary = (await salary_el.inner_text()).strip() if salary_el else ""

                href = (await title_el.get_attribute("href") or "").strip()
                external_id = ""
                if "jk=" in href:
                    external_id = href.split("jk=")[-1].split("&")[0]
                    url = f"https://www.indeed.com/viewjob?jk={external_id}"
                elif href.startswith("/"):
                    url = "https://www.indeed.com" + href
                    external_id = href.rstrip("/").split("/")[-1]
                elif href.startswith("http"):
                    url = href
                else:
                    continue

                if not (title and url):
                    continue

                jobs.append(DiscoveredJob(
                    title=title, company=company, url=url,
                    source="indeed", location=location,
                    salary_range=salary, external_id=external_id,
                ))
            except Exception as exc:
                logger.debug("Indeed card parse error: %s", exc)

        return jobs

    async def _has_next_page(self) -> bool:
        sel = self.sel.get("search", {}).get(
            "next_page_button", "[data-testid='pagination-page-next'], a[aria-label='Next Page']"
        )
        return await self._page.query_selector(sel) is not None

    async def _goto_next_page(self) -> None:
        sel = self.sel.get("search", {}).get(
            "next_page_button", "[data-testid='pagination-page-next'], a[aria-label='Next Page']"
        )
        await self.sim.human_move_and_click(self._page, sel)
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        await self._dismiss_popups()

    async def _get_full_jd_text(self) -> str:
        await self._dismiss_popups()

        for show_sel in [
            "button.show-more-less-html__button--more",
            "button[aria-expanded='false']",
            "#jobDescriptionText button",
        ]:
            try:
                btn = await self._page.query_selector(show_sel)
                if btn:
                    await self.sim.human_move_and_click(self._page, show_sel)
                    await self.sim.random_pause(0.5, 1.0)
                    break
            except Exception:
                pass

        text: str = await self._page.evaluate("""
            () => {
                const selectors = [
                    '#jobDescriptionText',
                    '[class*="jobsearch-jobDescriptionText"]',
                    '.jobsearch-jobDescriptionText',
                    '#job-description-container',
                    '.job_description',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.trim().length > 50) {
                        return el.innerText.trim();
                    }
                }
                return '';
            }
        """)
        return (text or "").strip()

    async def _dismiss_popups(self) -> None:
        for sel in [
            "button[id*='onetrust-accept']",
            ".icl-CloseButton",
            "[data-testid='modal-close-button']",
            "button[aria-label='close']",
        ]:
            try:
                btn = await self._page.query_selector(sel)
                if btn:
                    await btn.click()
                    await self.sim.random_pause(0.3, 0.5)
            except Exception:
                pass

    def _stub_jobs(self, config: SearchConfig) -> list[DiscoveredJob]:
        kw = " ".join(config.keywords) if config.keywords else "engineer"
        loc = config.location or "Remote"
        return [
            DiscoveredJob(
                title=f"{kw.title()} Developer", company="DevShop Inc.",
                url="https://indeed.com/viewjob?jk=mock-i001",
                source="indeed", location=loc,
                description_text=f"Looking for a {kw} developer.",
                external_id="mock-i001",
            ),
            DiscoveredJob(
                title=f"Senior {kw.title()} Engineer", company="BuildCo",
                url="https://indeed.com/viewjob?jk=mock-i002",
                source="indeed", location=loc,
                description_text=f"Senior {kw} engineer needed.",
                external_id="mock-i002",
            ),
        ]

    async def apply(self, job: DiscoveredJob, resume_path: str, answers: dict | None = None) -> dict:
        if not _playwright_available():
            return {"status": "stub_submitted", "job_url": job.url, "message": "Playwright not installed"}

        answers = answers or {}
        try:
            await self._start_browser()
            await self._page.goto(job.url, wait_until="domcontentloaded")
            await self.sim.random_pause(2.0, 3.0)
            await self._dismiss_popups()

            from src.automation.captcha_handler import CaptchaHandler
            detection = await CaptchaHandler().detect_on_page(self._page)
            if detection.detected:
                return {"status": "captcha", "message": detection.message, "job_url": job.url}

            apply_sel = self.sel.get("job_detail", {}).get("apply_button", "#indeedApplyButton")
            if not await self._page.query_selector(apply_sel):
                return {"status": "external", "message": "No Indeed Apply button", "job_url": job.url}

            await self.sim.human_move_and_click(self._page, apply_sel)
            await self.sim.random_pause(2.0, 3.0)

            result = await self._fill_apply_form(resume_path, answers)
            result["job_url"] = job.url
            return result
        except Exception as exc:
            return {"status": "failed", "message": str(exc), "job_url": job.url}
        finally:
            await self._close_browser()

    async def _fill_apply_form(self, resume_path: str, answers: dict) -> dict:
        form_sel = self.sel.get("apply_form", {})
        rate = self.sel.get("rate_limits", {})
        delay = rate.get("apply_delay_ms", 1500) / 1000

        frame = self._page
        iframe_el = await self._page.query_selector(
            form_sel.get("apply_iframe", "iframe[id^='indeedapply-iframe']")
        )
        if iframe_el:
            frame = await iframe_el.content_frame()

        await self.sim.random_pause(1.0, 2.0)

        file_input = await frame.query_selector(form_sel.get("resume_upload", "input[type='file']"))
        if file_input and resume_path and Path(resume_path).exists():
            await file_input.set_input_files(resume_path)
            await self.sim.random_pause(1.0, 2.0)

        field_map = {
            form_sel.get("name_input", "input[name='applicant.name']"): answers.get("name", ""),
            form_sel.get("email_input", "input[type='email']"): answers.get("email", ""),
            form_sel.get("phone_input", "input[type='tel']"): answers.get("phone", ""),
        }
        for sel, value in field_map.items():
            if value and sel:
                try:
                    inp = await frame.query_selector(sel)
                    if inp:
                        await inp.fill(value)
                        await self.sim.random_pause(0.2, 0.5)
                except Exception:
                    pass

        submit_sel = form_sel.get("submit_button", "button[type='submit']")
        continue_sel = form_sel.get("continue_button", "button[type='button'][id*='continue']")
        for _ in range(10):
            await self.sim.random_pause(delay, delay + 0.5)
            if await frame.query_selector(submit_sel):
                await frame.click(submit_sel)
                await self.sim.random_pause(2.0, 3.0)
                return {"status": "submitted", "message": "Application submitted via Indeed Apply"}
            cont = await frame.query_selector(continue_sel)
            if cont:
                await cont.click()
            else:
                break

        return {"status": "failed", "message": "Apply form did not complete"}
