"""
CRAWL — Human Behavior Simulation
Mimics organic user behavior to avoid bot detection.
Uses Gaussian distributions instead of uniform random for realistic timing.
"""

import random
import math
from playwright.async_api import Page


class HumanBehavior:
    """
    Simulates human-like browsing behavior:
    - Natural mouse movements with Bézier curves
    - Gaussian-distributed delays
    - Variable scroll patterns
    - Random pauses and micro-interactions
    """

    def __init__(self, speed_factor: float = 1.0):
        """
        Args:
            speed_factor: Multiplier for all delays. 
                          1.0 = normal, 0.5 = faster, 2.0 = more cautious
        """
        self.speed_factor = speed_factor

    # ── Delays ──────────────────────────────────────

    def _gaussian_delay(self, mean: float, std: float, minimum: float = 0.3) -> float:
        """Generate a human-like delay from a Gaussian distribution."""
        delay = max(minimum, random.gauss(mean, std))
        return delay * self.speed_factor

    async def human_wait(self, page: Page, short: bool = False):
        """Wait a human-like duration. Short waits for between-action pauses."""
        if short:
            delay = self._gaussian_delay(1.2, 0.5, 0.5)
        else:
            delay = self._gaussian_delay(3.5, 1.5, 1.0)
        await page.wait_for_timeout(int(delay * 1000))

    async def micro_pause(self, page: Page):
        """Tiny pause between rapid actions (like a human processing information)."""
        delay = self._gaussian_delay(0.4, 0.15, 0.1)
        await page.wait_for_timeout(int(delay * 1000))

    # ── Mouse Movement ──────────────────────────────

    async def random_mouse_movement(self, page: Page, movements: int = 0):
        """
        Move the mouse randomly across the viewport in a natural way.
        Uses Bézier-like curves instead of straight lines.
        """
        if movements == 0:
            movements = random.randint(2, 5)

        viewport = page.viewport_size or {"width": 1280, "height": 800}

        for _ in range(movements):
            # Target position with padding from edges
            target_x = random.randint(100, viewport["width"] - 100)
            target_y = random.randint(100, viewport["height"] - 100)

            # Move in small steps to simulate a curve
            steps = random.randint(8, 20)
            for step in range(steps):
                progress = step / steps
                # Add slight wobble (humans don't move in perfect lines)
                wobble_x = random.gauss(0, 3)
                wobble_y = random.gauss(0, 3)
                # Ease-in-out curve
                ease = (1 - math.cos(progress * math.pi)) / 2
                
                x = int(target_x * ease + wobble_x)
                y = int(target_y * ease + wobble_y)
                
                await page.mouse.move(x, y)
                await page.wait_for_timeout(random.randint(5, 25))

            await self.micro_pause(page)

    async def human_click(self, page: Page, selector: str):
        """
        Click an element with human-like behavior:
        1. Move mouse to element (with natural curve)
        2. Brief hover pause
        3. Click with slight delay
        """
        element = page.locator(selector)
        box = await element.bounding_box()

        if box:
            # Don't click exact center — humans rarely do
            x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
            y = box["y"] + box["height"] * random.uniform(0.25, 0.75)

            # Move to element
            await page.mouse.move(x, y, steps=random.randint(10, 25))
            # Hover pause (humans read/confirm before clicking)
            await page.wait_for_timeout(int(self._gaussian_delay(0.3, 0.15, 0.1) * 1000))
            # Click
            await page.mouse.click(x, y)
        else:
            # Fallback to standard click if we can't get bounding box
            await element.click()

        await self.micro_pause(page)

    # ── Scrolling ───────────────────────────────────

    async def human_scroll(self, page: Page, direction: str = "down"):
        """
        Scroll the page in a human-like way:
        - Variable scroll distances
        - Sometimes scroll back up slightly (humans do this)
        - Random pauses mid-scroll
        """
        if direction == "down":
            # Main scroll
            distance = random.randint(300, 900)
            await page.mouse.wheel(0, distance)
            await page.wait_for_timeout(int(self._gaussian_delay(0.8, 0.3, 0.3) * 1000))

            # 20% chance to scroll back up slightly (reconsidering/re-reading)
            if random.random() < 0.2:
                back_distance = random.randint(50, 200)
                await page.mouse.wheel(0, -back_distance)
                await page.wait_for_timeout(int(self._gaussian_delay(1.0, 0.4, 0.3) * 1000))

            # Occasional longer pause (reading content)
            if random.random() < 0.15:
                await page.wait_for_timeout(int(self._gaussian_delay(3.0, 1.0, 1.0) * 1000))
        else:
            distance = random.randint(200, 600)
            await page.mouse.wheel(0, -distance)
            await page.wait_for_timeout(int(self._gaussian_delay(0.6, 0.2, 0.2) * 1000))

    # ── Tab / Focus Simulation ──────────────────────

    async def simulate_tab_switch(self, page: Page):
        """
        Simulate a tab switch (blur + focus events).
        Real users frequently switch tabs while waiting.
        """
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await page.wait_for_timeout(int(self._gaussian_delay(2.0, 1.0, 0.5) * 1000))
        await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        await self.micro_pause(page)

    async def random_interaction(self, page: Page):
        """
        Perform a random benign interaction to appear more human:
        - Move mouse randomly
        - Hover over a random element
        - Small scroll
        """
        action = random.choice(["mouse", "scroll", "hover"])

        if action == "mouse":
            await self.random_mouse_movement(page, movements=1)
        elif action == "scroll":
            await self.human_scroll(page, random.choice(["down", "up"]))
        elif action == "hover":
            # Hover over a random link on the page
            links = await page.locator("a").count()
            if links > 0:
                idx = random.randint(0, min(links - 1, 10))
                try:
                    await page.locator("a").nth(idx).hover(timeout=2000)
                    await self.micro_pause(page)
                except Exception:
                    pass

    # ── Reading Simulation ───────────────────────────

    async def simulate_reading(self, page: Page, word_count: int = 200):
        """
        Simulate reading a page by pausing for a duration proportional
        to the estimated word count. Average reading speed: ~250 wpm.
        """
        reading_time = (word_count / 250.0) * self.speed_factor
        # Add variance (some paragraphs are skimmed, others read carefully)
        actual_time = self._gaussian_delay(reading_time, reading_time * 0.3, 0.5)
        await page.wait_for_timeout(int(actual_time * 1000))

    async def typing_simulation(self, page: Page, selector: str, text: str):
        """
        Type text into an input field with human-like timing.
        Each character has a variable delay to mimic real typing.
        """
        element = page.locator(selector)
        await element.click()
        await self.micro_pause(page)

        for char in text:
            await element.type(char, delay=random.randint(50, 180))
            # Occasional longer pause (thinking about next character)
            if random.random() < 0.05:
                await page.wait_for_timeout(random.randint(200, 600))

    async def browsing_session(self, page: Page):
        """
        Run a sequence of natural human behaviors to build a believable
        browsing session before the actual scraping begins.
        """
        actions = random.sample(
            ["mouse", "scroll", "hover", "read", "tab_switch"],
            k=random.randint(2, 4),
        )

        for action in actions:
            if action == "mouse":
                await self.random_mouse_movement(page, movements=random.randint(1, 3))
            elif action == "scroll":
                await self.human_scroll(page, "down")
                if random.random() < 0.3:
                    await self.human_scroll(page, "up")
            elif action == "hover":
                await self.random_interaction(page)
            elif action == "read":
                await self.simulate_reading(page, word_count=random.randint(50, 200))
            elif action == "tab_switch":
                if random.random() < 0.3:
                    await self.simulate_tab_switch(page)
