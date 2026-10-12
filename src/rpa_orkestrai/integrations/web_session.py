"""Web steps: the computer's own Edge or Chrome, driven by Playwright from one worker thread.

No browser is downloaded: Windows always has Microsoft Edge; on macOS Chrome or Edge is used.
A separate profile in the workspace keeps sign-ins between runs without touching the person's
own browser profile. Targets are found by what a person sees (text, label, placeholder, button
name) or by CSS; a target matching more than one element is never clicked or filled.
"""

from __future__ import annotations

import platform
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..errors import WorkflowError

BROWSERS = {"auto": "Otomatik", "msedge": "Microsoft Edge", "chrome": "Google Chrome"}
TARGETS = {"text": "Görünen metin", "label": "Alan etiketi", "placeholder": "Alandaki silik yazı",
           "button": "Düğme veya bağlantı adı", "css": "CSS seçici"}


def installed(channel: str) -> bool:
    system = platform.system()
    if system == "Darwin":
        names = {"chrome": "Google Chrome.app", "msedge": "Microsoft Edge.app"}
        return any((root / names[channel]).exists() for root in (Path("/Applications"), Path.home() / "Applications"))
    if system == "Windows":
        import os

        folders = [os.environ.get(name, "") for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        relative = {"chrome": Path("Google/Chrome/Application/chrome.exe"),
                    "msedge": Path("Microsoft/Edge/Application/msedge.exe")}[channel]
        return any(folder and (Path(folder) / relative).exists() for folder in folders)
    return False


def choose_channel(choice: str) -> str:
    if choice not in BROWSERS:
        raise WorkflowError("Tarayıcı seçimi geçersiz.")
    order = [choice] if choice != "auto" else (["msedge", "chrome"] if platform.system() == "Windows"
                                               else ["chrome", "msedge"])
    for channel in order:
        if installed(channel):
            return channel
    wanted = BROWSERS[choice] if choice != "auto" else "Microsoft Edge veya Google Chrome"
    raise WorkflowError(f"{wanted} bu bilgisayarda bulunamadı. Tarayıcıyı kurun veya adımda diğer tarayıcıyı seçin.")


class WebSession:
    def __init__(self, profile: Path, *, timeout_ms: int, cancel: threading.Event | None = None):
        self.profile = Path(profile)
        self.timeout_ms = timeout_ms
        self.cancel = cancel
        self.channel: str | None = None
        self._runtime: Any = None
        self._context: Any = None
        self._page: Any = None
        self._owner: int | None = None

    # ----- lifecycle --------------------------------------------------------------------
    def _check_thread(self) -> None:
        if self._owner is not None and self._owner != threading.get_ident():
            raise RuntimeError("A web session must be used by its owning workflow thread.")

    def open(self, url: str, *, browser: str = "auto", headless: bool = False) -> str:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise WorkflowError("Adres http:// veya https:// ile başlamalıdır.")
        if parsed.username or parsed.password:
            raise WorkflowError("Adresin içine kullanıcı adı veya şifre yazmayın; Web alanını doldur adımını kullanın.")
        self._check_thread()
        if self._page is None:
            self._start(choose_channel(browser), headless)
        self._run(lambda: self._page.goto(url, wait_until="load", timeout=self.timeout_ms), "Sayfa açılamadı")
        return str(self._page.url)

    def _start(self, channel: str, headless: bool) -> None:
        from playwright.sync_api import sync_playwright

        self._owner = threading.get_ident()
        self.profile.mkdir(parents=True, exist_ok=True)
        try:
            self._runtime = sync_playwright().start()
            self._context = self._runtime.chromium.launch_persistent_context(
                str(self.profile), channel=channel, headless=headless, no_viewport=not headless,
                accept_downloads=False, args=[] if headless else ["--start-maximized"])
            self._context.set_default_timeout(self.timeout_ms)
            self._context.set_default_navigation_timeout(self.timeout_ms)
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self.channel = channel
        except Exception as exc:
            self.close()
            message = str(exc)
            if "ProcessSingleton" in message or "user data directory is already in use" in message.lower():
                raise WorkflowError("Web adımlarının tarayıcı profili başka bir pencerede açık. Önceki RpaOrkestrAI "
                                    "tarayıcı penceresini kapatıp yeniden deneyin.") from exc
            raise WorkflowError(f"{BROWSERS[channel]} başlatılamadı: {message.splitlines()[0][:300]}") from exc

    @property
    def page(self) -> Any:
        self._check_thread()
        if self._page is None:
            raise WorkflowError("Önce Web sayfası aç adımıyla bir sayfa açın.")
        return self._page

    def close(self) -> None:
        for name, method in (("_context", "close"), ("_runtime", "stop")):
            resource = getattr(self, name)
            setattr(self, name, None)
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception:
                    pass
        self._page = None
        self._owner = None

    def __enter__(self) -> WebSession:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ----- targets ----------------------------------------------------------------------
    def locator(self, by: str, value: str, *, exact: bool = False) -> Any:
        if by not in TARGETS:
            raise WorkflowError("Hedefi bulma yöntemi geçersiz.")
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise WorkflowError("Hedef boş olamaz.")
        page = self.page
        if by == "text":
            return page.get_by_text(value, exact=exact)
        if by == "label":
            return page.get_by_label(value, exact=exact)
        if by == "placeholder":
            return page.get_by_placeholder(value, exact=exact)
        if by == "button":
            return page.get_by_role("button", name=value, exact=exact).or_(
                page.get_by_role("link", name=value, exact=exact))
        return page.locator(value)

    def single(self, by: str, value: str, *, exact: bool, timeout_ms: int, visible: bool = True) -> Any:
        """Wait for exactly one (visible) match; more than one is never guessed between.

        Reading accepts an element that is merely present: an empty result line has no height.
        """
        import time

        found = self.locator(by, value, exact=exact)
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if self.cancel is not None and self.cancel.is_set():
                raise InterruptedError("Web adımı iptal edildi.")
            matching = self._run(lambda: [item for item in found.all() if not visible or item.is_visible()],
                                 "Sayfa okunamadı")
            if len(matching) == 1:
                return matching[0]
            if len(matching) > 1:
                raise WorkflowError(f"“{value}” sayfada {len(matching)} öğeyle eşleşti; hangisinin kullanılacağı belirsiz, "
                                    "işlem yapılmadı. Tam eşleşmeyi açın veya daha ayırt edici bir hedef yazın.")
            if time.monotonic() >= deadline:
                raise WorkflowError(f"“{value}” ({TARGETS[by].lower()}) sayfada bulunamadı. Sayfanın yüklendiğini ve "
                                    "hedefin görünür olduğunu kontrol edin.")
            self.page.wait_for_timeout(200)

    def _run(self, action: Any, label: str) -> Any:
        from playwright.sync_api import Error as PlaywrightError

        try:
            return action()
        except PlaywrightError as exc:
            first = str(exc).splitlines()[0][:300]
            if "Target page, context or browser has been closed" in str(exc) or "has been closed" in first:
                raise WorkflowError("Tarayıcı penceresi kapatıldı; Web sayfası aç adımıyla yeniden açın.") from exc
            raise WorkflowError(f"{label}: {first}") from exc

    # ----- actions ----------------------------------------------------------------------
    def click(self, by: str, value: str, *, exact: bool, timeout_ms: int) -> None:
        item = self.single(by, value, exact=exact, timeout_ms=timeout_ms)
        # Never retried: a second click can submit a form twice.
        self._run(lambda: item.click(timeout=timeout_ms), "Tıklanamadı")

    def fill(self, by: str, value: str, text: str, *, exact: bool, timeout_ms: int) -> None:
        item = self.single(by, value, exact=exact, timeout_ms=timeout_ms)
        self._run(lambda: item.fill(text, timeout=timeout_ms), "Alan doldurulamadı")

    def read(self, by: str, value: str, *, exact: bool, timeout_ms: int) -> str:
        item = self.single(by, value, exact=exact, timeout_ms=timeout_ms, visible=False)

        def content() -> str:
            tag = item.evaluate("element => element.tagName").lower()
            return item.input_value() if tag in {"input", "textarea", "select"} else item.inner_text()

        return str(self._run(content, "Metin okunamadı"))

    def select(self, by: str, value: str, option: str, *, exact: bool, timeout_ms: int) -> str:
        item = self.single(by, value, exact=exact, timeout_ms=timeout_ms)
        labels = self._run(lambda: item.evaluate(
            "element => element.tagName === 'SELECT' ? [...element.options].map(o => o.label.trim()) : null"),
            "Liste okunamadı")
        if labels is None:
            raise WorkflowError("Hedef bir açılır liste (select) değil; seçenek için Web öğesine tıkla adımını kullanın.")
        from ..actions.common import fold

        # Turkish-aware: "iade" finds "İade edildi" (str.casefold turns İ into i + a combining dot).
        matches = [label for label in labels if label == option.strip()] or (
            [] if exact else [label for label in labels if fold(option.strip()) in fold(label)])
        if len(matches) != 1:
            shown = ", ".join(labels[:15])
            raise WorkflowError(f"“{option}” seçeneği listede {'bulunamadı' if not matches else 'birden fazla kez geçiyor'};"
                                f" seçilmedi. Seçenekler: {shown}")
        self._run(lambda: item.select_option(label=matches[0], timeout=timeout_ms), "Seçilemedi")
        return matches[0]
