"""Job deduplication engine — prevent processing duplicate job listings."""

from urllib.parse import urlparse
from rapidfuzz import fuzz

from src.automation.drivers.base import DiscoveredJob


class Deduplicator:
    """Detect and filter duplicate job listings across sources.

    Uses a combination of URL normalization, title+company fuzzy matching,
    and external ID checks.
    """

    def __init__(self, fuzzy_threshold: int = 85):
        """Initialize deduplicator.

        Args:
            fuzzy_threshold: Minimum fuzzy match ratio (0-100) to consider
                a title+company pair as duplicate. Default 85.
        """
        self.fuzzy_threshold = fuzzy_threshold

    def deduplicate(
        self,
        new_jobs: list[DiscoveredJob],
        existing_urls: set[str] | None = None,
    ) -> tuple[list[DiscoveredJob], list[DiscoveredJob]]:
        """Filter duplicates from a list of newly discovered jobs.

        Args:
            new_jobs: List of newly discovered jobs.
            existing_urls: URLs of jobs already in the database.

        Returns:
            Tuple of (unique_jobs, duplicate_jobs).
        """
        existing_urls = existing_urls or set()
        unique: list[DiscoveredJob] = []
        duplicates: list[DiscoveredJob] = []
        seen_normalized: set[str] = set()
        seen_keys: set[str] = set()

        # Normalize existing URLs
        normalized_existing = {self._normalize_url(u) for u in existing_urls}

        for job in new_jobs:
            # 1. Check URL-based dedup
            norm_url = self._normalize_url(job.url)
            if norm_url in normalized_existing or norm_url in seen_normalized:
                duplicates.append(job)
                continue

            # 2. Check title+company fuzzy match against already-seen
            key = f"{job.title.lower()}|{job.company.lower()}"
            is_dupe = False
            for seen_key in seen_keys:
                if fuzz.ratio(key, seen_key) >= self.fuzzy_threshold:
                    is_dupe = True
                    break

            if is_dupe:
                duplicates.append(job)
                continue

            # Not a duplicate
            unique.append(job)
            seen_normalized.add(norm_url)
            seen_keys.add(key)

        return unique, duplicates

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison.

        Strips tracking parameters, fragments, trailing slashes.
        """
        parsed = urlparse(url)

        # Remove common tracking query params
        path = parsed.path.rstrip("/")

        # Reconstruct without query/fragment for simple comparison
        return f"{parsed.scheme}://{parsed.netloc}{path}".lower()


def is_duplicate(job: DiscoveredJob, existing_urls: set[str]) -> bool:
    """Quick check if a single job is a duplicate."""
    dedup = Deduplicator()
    unique, _ = dedup.deduplicate([job], existing_urls)
    return len(unique) == 0
