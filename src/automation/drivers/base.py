"""Base portal driver interface for job search/apply automation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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
