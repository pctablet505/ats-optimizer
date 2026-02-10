"""CAPTCHA detection and handling.

Detects common CAPTCHA types and pauses automation to alert the user
for manual solving. V1 does NOT solve CAPTCHAs automatically.
"""

import re
from dataclasses import dataclass


@dataclass
class CaptchaDetection:
    """Result of CAPTCHA detection on a page."""
    detected: bool = False
    captcha_type: str = ""  # recaptcha, hcaptcha, cloudflare, unknown
    message: str = ""


class CaptchaHandler:
    """Detect CAPTCHAs and handle them by pausing for human intervention.

    In V1, the system pauses automation and notifies the user when a
    CAPTCHA is detected. It does NOT attempt to solve CAPTCHAs.
    """

    # Common CAPTCHA indicator patterns
    CAPTCHA_PATTERNS = [
        (r"recaptcha", "recaptcha"),
        (r"hcaptcha", "hcaptcha"),
        (r"g-recaptcha", "recaptcha"),
        (r"h-captcha", "hcaptcha"),
        (r"cf-turnstile", "cloudflare"),
        (r"captcha-container", "unknown"),
        (r"verify.*human", "unknown"),
        (r"not.*robot", "unknown"),
        (r"challenge-form", "unknown"),
    ]

    def detect(self, page_html: str) -> CaptchaDetection:
        """Check page HTML for CAPTCHA indicators.

        Args:
            page_html: The full HTML source of the page.

        Returns:
            CaptchaDetection with detection result.
        """
        html_lower = page_html.lower()

        for pattern, captcha_type in self.CAPTCHA_PATTERNS:
            if re.search(pattern, html_lower):
                return CaptchaDetection(
                    detected=True,
                    captcha_type=captcha_type,
                    message=f"CAPTCHA detected ({captcha_type}). Please solve it manually.",
                )

        return CaptchaDetection(detected=False)

    async def detect_on_page(self, page) -> CaptchaDetection:
        """Detect CAPTCHA on a Playwright page object.

        Args:
            page: Playwright page object.

        Returns:
            CaptchaDetection result.
        """
        html = await page.content()
        return self.detect(html)

    async def handle(self, page, timeout_seconds: int = 120) -> bool:
        """Wait for human to solve CAPTCHA.

        Polls the page periodically to check if the CAPTCHA has been
        solved. Returns True if solved within timeout, False otherwise.

        Args:
            page: Playwright page object.
            timeout_seconds: How long to wait before giving up.

        Returns:
            True if CAPTCHA was solved, False if timed out.
        """
        import asyncio

        elapsed = 0
        poll_interval = 3

        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            detection = await self.detect_on_page(page)
            if not detection.detected:
                return True  # CAPTCHA solved

        return False  # Timed out
