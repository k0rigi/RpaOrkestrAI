"""Synchronous Playwright session owned by one workflow worker thread."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class BrowserService:
    def __init__(
        self, headless: bool = True, timeout_ms: int = 30_000, *,
        browser_type: str = "chromium", viewport: tuple[int, int] = (1440, 900),
    ) -> None:
        if browser_type not in {"chromium", "firefox", "webkit"}:
            raise ValueError("Unsupported Playwright browser type.")
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 300_000:
            raise ValueError("Browser timeout must be between 1 and 300,000 ms.")
        if len(viewport) != 2 or any(type(v) is not int or not 200 <= v <= 10_000 for v in viewport):
            raise ValueError("Browser viewport must contain two sizes between 200 and 10,000.")
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.browser_type = browser_type
        self.viewport = viewport
        self._runtime: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._owner: int | None = None

    def _check_thread(self) -> None:
        if self._owner is not None and self._owner != threading.get_ident():
            raise RuntimeError("A browser session must be used and closed by its owning workflow thread.")

    def start(self) -> BrowserService:
        self._check_thread()
        if self._page is not None:
            return self
        from playwright.sync_api import sync_playwright

        self._owner = threading.get_ident()
        try:
            self._runtime = sync_playwright().start()
            self._browser = getattr(self._runtime, self.browser_type).launch(headless=self.headless)
            self._context = self._browser.new_context(
                viewport={"width": self.viewport[0], "height": self.viewport[1]},
                accept_downloads=False,
            )
            self._context.set_default_timeout(self.timeout_ms)
            self._context.set_default_navigation_timeout(self.timeout_ms)
            self._page = self._context.new_page()
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise
        return self

    @property
    def page(self) -> Any:
        self.start()
        return self._page

    @staticmethod
    def _selector(selector: str) -> str:
        if not isinstance(selector, str) or not selector.strip() or len(selector) > 4_096:
            raise ValueError("A non-empty browser selector of at most 4,096 characters is required.")
        return selector

    def goto(self, url: str, *, wait_until: str = "domcontentloaded") -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Browser navigation requires an HTTP or HTTPS URL.")
        if parsed.username or parsed.password:
            raise ValueError("Do not embed credentials in browser URLs.")
        if wait_until not in {"commit", "domcontentloaded", "load", "networkidle"}:
            raise ValueError("Invalid navigation wait state.")
        self.page.goto(url, wait_until=wait_until, timeout=self.timeout_ms)
        return str(self.page.url)

    def fill(self, selector: str, value: str) -> None:
        self.page.locator(self._selector(selector)).fill(str(value))

    def click(self, selector: str) -> None:
        # Never automatically retry mutations: clicking twice can submit twice.
        self.page.locator(self._selector(selector)).click()

    def text(self, selector: str) -> str:
        return str(self.page.locator(self._selector(selector)).inner_text())

    def wait_for(self, selector: str, *, state: str = "visible", timeout_ms: int | None = None) -> None:
        if state not in {"attached", "detached", "visible", "hidden"}:
            raise ValueError("Unsupported browser wait state.")
        duration = self.timeout_ms if timeout_ms is None else timeout_ms
        if type(duration) is not int or not 1 <= duration <= 300_000:
            raise ValueError("Wait timeout must be between 1 and 300,000 ms.")
        self.page.locator(self._selector(selector)).wait_for(state=state, timeout=duration)

    def screenshot(self, path: str | Path, *, full_page: bool = True) -> Path:
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(destination), full_page=full_page)
        return destination

    def close(self) -> None:
        self._check_thread()
        first_error: Exception | None = None
        for name, method in (("_context", "close"), ("_browser", "close"), ("_runtime", "stop")):
            resource = getattr(self, name)
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                finally:
                    setattr(self, name, None)
        self._page = None
        self._owner = None
        if first_error is not None:
            raise first_error

    def __enter__(self) -> BrowserService:
        return self.start()

    def __exit__(self, exc_type: Any, *_: Any) -> None:
        try:
            self.close()
        except Exception:
            if exc_type is None:
                raise
