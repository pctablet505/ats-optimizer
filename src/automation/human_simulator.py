"""Human-like interaction simulator for browser automation.

Key principles:
  - Lognormal timing: most pauses are short, but occasionally long (like humans)
  - Mouse movement before clicks: generates real mousemove events via stepped paths
  - Scroll-to-read: scrolls through content at reading speed before extraction
  - Variable typing: accelerates/decelerates like real typing
"""

import math
import random
import asyncio


def _lognormal(mean: float, sigma: float = 0.45) -> float:
    """Draw from a lognormal distribution with the given mean (seconds).

    Humans are lognormal: most interactions are quick, but occasionally
    take much longer. Sigma=0.45 gives a realistic spread.
    """
    mu = math.log(max(mean, 0.001)) - (sigma ** 2) / 2
    return random.lognormvariate(mu, sigma)


class HumanSimulator:
    """Simulate human-like browser interaction patterns.

    Used by portal drivers to type, move mouse, scroll, and pause
    at realistic lognormal intervals to avoid bot detection.
    """

    def __init__(self, typing_speed_wpm: int = 55):
        # average chars per second at given WPM (5 chars/word)
        self.chars_per_second = (typing_speed_wpm * 5) / 60

    # ── Timing ────────────────────────────────────────────────

    async def random_pause(self, min_seconds: float = 0.8, max_seconds: float = 2.5):
        """Pause for a lognormal-distributed duration between min and max.

        Unlike uniform random, lognormal produces short pauses most of
        the time with occasional longer ones — matching real user behaviour.
        """
        mean = (min_seconds + max_seconds) / 2
        t = _lognormal(mean)
        # Clip to [min, max*1.5] to allow occasional long pauses but nothing absurd
        t = max(min_seconds, min(max_seconds * 1.5, t))
        await asyncio.sleep(t)

    async def think_pause(self):
        """Longer pause simulating reading / decision making (2–6s)."""
        await asyncio.sleep(_lognormal(3.5, 0.5))

    # ── Mouse + Click ─────────────────────────────────────────

    async def human_move_and_click(self, page, selector: str):
        """Move mouse to element along a stepped path, then click.

        Generates real mousemove events at each step, which browsers
        use to distinguish humans from scripts. Falls back to direct
        click if the element can't be located.
        """
        try:
            locator = page.locator(selector).first
            box = await locator.bounding_box()
            if box:
                # Target slightly randomised within element bounds
                tx = box["x"] + box["width"] * random.uniform(0.25, 0.75)
                ty = box["y"] + box["height"] * random.uniform(0.25, 0.75)
                # Add slight overshoot-and-correct (human cursor behaviour)
                steps = random.randint(12, 28)
                await page.mouse.move(
                    tx + random.uniform(-3, 3),
                    ty + random.uniform(-3, 3),
                    steps=steps,
                )
                await asyncio.sleep(_lognormal(0.08, 0.3))
                await page.mouse.click(tx, ty)
                await asyncio.sleep(_lognormal(0.15, 0.3))
                return
        except Exception:
            pass
        # Fallback: direct click
        await asyncio.sleep(_lognormal(0.2, 0.3))
        await page.click(selector)
        await asyncio.sleep(_lognormal(0.15, 0.3))

    async def click_with_delay(self, page, selector: str):
        """Convenience alias — move mouse to element and click."""
        await self.human_move_and_click(page, selector)

    # ── Typing ────────────────────────────────────────────────

    async def type_text(self, page, selector: str, text: str):
        """Type text with lognormal per-character delays.

        Includes occasional short hesitations (bursts + pauses).
        """
        await self.human_move_and_click(page, selector)

        burst_size = random.randint(3, 7)  # chars before a micro-pause
        burst_count = 0
        for char in text:
            delay_ms = int((_lognormal(1 / self.chars_per_second, 0.4)) * 1000)
            await page.type(selector, char, delay=max(30, delay_ms))
            burst_count += 1
            if burst_count >= burst_size:
                await asyncio.sleep(_lognormal(0.06, 0.5))
                burst_size = random.randint(2, 9)
                burst_count = 0
            # Occasional longer thinking pause
            if random.random() < 0.04:
                await asyncio.sleep(_lognormal(0.5, 0.5))

    # ── Scrolling ─────────────────────────────────────────────

    async def scroll_to_read(self, page, reading_time: float = 2.0):
        """Scroll through the page at a natural reading pace.

        Simulates a user actually reading the content rather than
        a script that navigates and immediately extracts data.
        reading_time: approximate seconds to spend scrolling (loosely).
        """
        try:
            scroll_height = await page.evaluate("document.documentElement.scrollHeight")
            viewport_h = await page.evaluate("window.innerHeight")
            if scroll_height <= viewport_h:
                # Short page — just pause to simulate reading
                await asyncio.sleep(_lognormal(reading_time, 0.4))
                return

            pos = 0
            while pos < scroll_height - viewport_h:
                # Scroll a random chunk (200–600px)
                chunk = random.randint(180, 520)
                pos = min(pos + chunk, scroll_height - viewport_h)
                await page.evaluate(
                    f"window.scrollTo({{top: {pos}, behavior: 'smooth'}})"
                )
                # Pause after each scroll chunk — lognormal centred ~0.7s
                await asyncio.sleep(_lognormal(0.65, 0.5))
                # Occasional longer pause (stopped to read something)
                if random.random() < 0.25:
                    await asyncio.sleep(_lognormal(1.2, 0.5))
        except Exception:
            await asyncio.sleep(_lognormal(reading_time, 0.4))

    async def scroll_page(self, page, direction: str = "down", amount: int = 300):
        """Single scroll step (legacy convenience method)."""
        actual = amount + random.randint(-60, 60)
        if direction == "up":
            actual = -actual
        await page.evaluate(f"window.scrollBy(0, {actual})")
        await asyncio.sleep(_lognormal(0.35, 0.4))

    def get_random_delay(self) -> float:
        """Synchronous lognormal delay value (seconds)."""
        return _lognormal(1.0)
