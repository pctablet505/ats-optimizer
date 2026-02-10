"""Human-like interaction simulator for browser automation.

Adds realistic delays and typing patterns to avoid detection
by anti-bot systems on job portals.
"""

import random
import asyncio


class HumanSimulator:
    """Simulate human-like interaction patterns.

    Used by portal drivers to type text, move mouse, scroll,
    and pause at realistic intervals.
    """

    def __init__(
        self,
        typing_speed_wpm: int = 60,
        min_pause_ms: int = 200,
        max_pause_ms: int = 1500,
    ):
        self.chars_per_second = (typing_speed_wpm * 5) / 60  # 5 chars per word
        self.min_pause = min_pause_ms / 1000
        self.max_pause = max_pause_ms / 1000

    async def type_text(self, page, selector: str, text: str):
        """Type text character by character with human-like delays.

        Args:
            page: Playwright page object.
            selector: CSS selector for the input field.
            text: Text to type.
        """
        await page.click(selector)
        await self.random_pause(0.1, 0.3)

        for char in text:
            # Random per-char delay
            delay = (1 / self.chars_per_second) * random.uniform(0.7, 1.3)
            await page.type(selector, char, delay=int(delay * 1000))

            # Occasional longer pause (simulating thinking)
            if random.random() < 0.05:
                await self.random_pause(0.3, 0.8)

    async def random_pause(self, min_seconds: float = None, max_seconds: float = None):
        """Wait a random human-like duration.

        Args:
            min_seconds: Minimum wait time. Defaults to self.min_pause.
            max_seconds: Maximum wait time. Defaults to self.max_pause.
        """
        low = min_seconds if min_seconds is not None else self.min_pause
        high = max_seconds if max_seconds is not None else self.max_pause
        await asyncio.sleep(random.uniform(low, high))

    async def scroll_page(self, page, direction: str = "down", amount: int = 300):
        """Scroll the page with a random amount.

        Args:
            page: Playwright page object.
            direction: "up" or "down".
            amount: Base scroll amount in pixels.
        """
        actual_amount = amount + random.randint(-50, 50)
        if direction == "up":
            actual_amount = -actual_amount
        await page.evaluate(f"window.scrollBy(0, {actual_amount})")
        await self.random_pause(0.2, 0.5)

    async def click_with_delay(self, page, selector: str):
        """Click an element with a slight pre-click pause.

        Args:
            page: Playwright page object.
            selector: CSS selector to click.
        """
        await self.random_pause(0.1, 0.4)
        await page.click(selector)
        await self.random_pause(0.2, 0.6)

    def get_random_delay(self) -> float:
        """Get a random delay value for synchronous use."""
        return random.uniform(self.min_pause, self.max_pause)
