"""Indeed portal driver — stub implementation.

TODO: Implement with Playwright browser automation when ready.
"""

from src.automation.drivers.base import BasePortalDriver, DiscoveredJob, SearchConfig


class IndeedDriver(BasePortalDriver):
    """Indeed job search and application driver.

    Stub implementation returning mock data.
    Real implementation will use Playwright to:
    1. Navigate to indeed.com
    2. Enter search keywords and location
    3. Scrape job cards from results
    4. Fetch full job descriptions
    5. Apply using Indeed's application flow
    """

    async def search(self, config: SearchConfig) -> list[DiscoveredJob]:
        """Search Indeed jobs. Returns mock data in stub mode."""
        # TODO: Implement with Playwright
        keyword_str = " ".join(config.keywords) if config.keywords else "developer"
        return [
            DiscoveredJob(
                title=f"{keyword_str.title()} Developer",
                company="DevShop Inc.",
                url="https://indeed.com/viewjob?jk=mock-i001",
                source="indeed",
                location=config.location or "New York, NY",
                description_text=f"Hiring a {keyword_str} developer for our team...",
                external_id="mock-i001",
            ),
            DiscoveredJob(
                title=f"Senior {keyword_str.title()} Engineer",
                company="BuildCo",
                url="https://indeed.com/viewjob?jk=mock-i002",
                source="indeed",
                location=config.location or "Remote",
                description_text=f"Senior {keyword_str} engineer needed...",
                external_id="mock-i002",
            ),
        ]

    async def get_job_details(self, url: str) -> DiscoveredJob:
        """Fetch full job details from Indeed listing."""
        # TODO: Implement with Playwright
        return DiscoveredJob(
            title="Software Developer",
            company="DevShop Inc.",
            url=url,
            source="indeed",
            description_text="Full job description would be scraped here.",
            external_id="mock-i-details",
        )

    async def apply(self, job: DiscoveredJob, resume_path: str, answers: dict | None = None) -> dict:
        """Apply via Indeed Apply. Returns mock result in stub mode."""
        # TODO: Implement apply flow with Playwright
        return {
            "status": "stub_submitted",
            "job_url": job.url,
            "message": "Indeed Apply stub — not actually submitted",
        }

    def driver_name(self) -> str:
        return "indeed"

    async def is_available(self) -> bool:
        # TODO: Check Playwright availability
        return True
