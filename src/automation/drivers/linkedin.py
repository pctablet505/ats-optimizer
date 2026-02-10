"""LinkedIn portal driver — stub implementation.

TODO: Implement with Playwright browser automation when ready.
This stub returns mock data for testing the pipeline.
"""

from src.automation.drivers.base import BasePortalDriver, DiscoveredJob, SearchConfig


class LinkedInDriver(BasePortalDriver):
    """LinkedIn job search and Easy Apply driver.

    This is a stub implementation that returns mock data.
    Real implementation will use Playwright to:
    1. Log in to LinkedIn
    2. Search using the jobs URL with filters
    3. Scrape job cards for title, company, URL
    4. Click into listings for full descriptions
    5. Use Easy Apply flow for applications
    """

    def __init__(self, email: str = "", password: str = ""):
        self.email = email
        self.password = password

    async def search(self, config: SearchConfig) -> list[DiscoveredJob]:
        """Search LinkedIn jobs. Returns mock data in stub mode."""
        # TODO: Implement with Playwright
        # Real implementation would:
        # 1. Navigate to linkedin.com/jobs/search
        # 2. Fill in keywords, location, filters
        # 3. Scrape job cards from results pages
        # 4. Extract title, company, URL, location
        return [
            DiscoveredJob(
                title="Senior Backend Engineer",
                company="TechCorp",
                url="https://linkedin.com/jobs/view/mock-001",
                source="linkedin",
                location=config.location or "San Francisco, CA",
                description_text="We are looking for a Senior Backend Engineer...",
                external_id="mock-001",
            ),
            DiscoveredJob(
                title="Staff Software Engineer",
                company="InnovateLabs",
                url="https://linkedin.com/jobs/view/mock-002",
                source="linkedin",
                location=config.location or "Remote",
                description_text="InnovateLabs is hiring a Staff Software Engineer...",
                external_id="mock-002",
            ),
        ]

    async def get_job_details(self, url: str) -> DiscoveredJob:
        """Fetch full job details from LinkedIn listing."""
        # TODO: Implement with Playwright
        return DiscoveredJob(
            title="Senior Backend Engineer",
            company="TechCorp",
            url=url,
            source="linkedin",
            description_text="Full job description would be scraped here.",
            external_id="mock-details",
        )

    async def apply(self, job: DiscoveredJob, resume_path: str, answers: dict | None = None) -> dict:
        """Apply via LinkedIn Easy Apply. Returns mock result in stub mode."""
        # TODO: Implement Easy Apply flow with Playwright
        # Real implementation would:
        # 1. Click "Easy Apply" button
        # 2. Upload resume
        # 3. Fill in form fields using Q&A bank
        # 4. Handle multi-step forms
        # 5. Submit and capture confirmation
        return {
            "status": "stub_submitted",
            "job_url": job.url,
            "message": "LinkedIn Easy Apply stub — not actually submitted",
        }

    def driver_name(self) -> str:
        return "linkedin"

    async def is_available(self) -> bool:
        # TODO: Check credentials and Playwright availability
        return bool(self.email and self.password)
