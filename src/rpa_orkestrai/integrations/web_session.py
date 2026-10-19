"""Web steps: the computer's own Edge or Chrome, driven by Playwright from one worker thread.

No browser is downloaded: Windows always has Microsoft Edge; on macOS Chrome or Edge is used.
A separate profile in the workspace keeps sign-ins between runs without touching the person's
own browser profile. Targets are found by what a person sees (text, label, placeholder, button
name) or by CSS, optionally inside a frame; a target matching more than one element is never
clicked, filled or read. A tab opened by the page (target=_blank, a popup) becomes the page the
next step works on, as a person would continue there.
"""

from __future__ import annotations

import json
import platform
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..errors import WorkflowError

BROWSERS = {"auto": "Otomatik", "msedge": "Microsoft Edge", "chrome": "Google Chrome"}
TARGETS = {"text": "Görünen metin", "label": "Alan etiketi", "placeholder": "Alandaki silik yazı",
           "button": "Düğme veya bağlantı adı", "css": "CSS seçici"}
KEYS = {"Enter", "Tab", "Escape", "Backspace", "Delete", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight",
        "PageDown", "PageUp", "Home", "End", "Space", "F5"}
MODIFIERS = {"": "", "mod": "ControlOrMeta", "shift": "Shift", "alt": "Alt"}
SCRIPT_RESULT_LIMIT = 5 * 1024 * 1024


@dataclass(frozen=True)
class Target:
    by: str
    value: str
    exact: bool = False
    frame: str = ""
    timeout_ms: int = 15_000


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


def check_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WorkflowError("Adres http:// veya https:// ile başlamalıdır.")
    if parsed.username or parsed.password:
        raise WorkflowError("Adresin içine kullanıcı adı veya şifre yazmayın; Web alanını doldur adımını kullanın.")
    return url


def build_locator(page: Any, target: Target) -> Any:
    """The Playwright locator for a target; used by runs and by Tarayıcıda seç alike."""
    if target.by not in TARGETS:
        raise WorkflowError("Hedefi bulma yöntemi geçersiz.")
    if not isinstance(target.value, str) or not target.value.strip() or len(target.value) > 4096:
        raise WorkflowError("Hedef boş olamaz.")
    scope = page.frame_locator(target.frame).first if target.frame else page
    value, exact = target.value, target.exact
    if target.by == "text":
        return scope.get_by_text(value, exact=exact)
    if target.by == "label":
        return scope.get_by_label(value, exact=exact)
    if target.by == "placeholder":
        return scope.get_by_placeholder(value, exact=exact)
    if target.by == "button":
        return scope.get_by_role("button", name=value, exact=exact).or_(
            scope.get_by_role("link", name=value, exact=exact))
    return scope.locator(value)


def launch(runtime: Any, profile: Path, channel: str, headless: bool, timeout_ms: int) -> Any:
    """A persistent context on the given browser; shared by runs and Tarayıcıda seç."""
    profile.mkdir(parents=True, exist_ok=True)
    try:
        context = runtime.chromium.launch_persistent_context(
            str(profile), channel=channel, headless=headless, no_viewport=not headless,
            accept_downloads=True, args=[] if headless else ["--start-maximized"])
    except Exception as exc:
        message = str(exc)
        if "ProcessSingleton" in message or "user data directory is already in use" in message.lower():
            raise WorkflowError("Web adımlarının tarayıcı profili başka bir pencerede açık. Önceki RpaOrkestrAI "
                                "tarayıcı penceresini kapatıp yeniden deneyin.") from exc
        raise WorkflowError(f"{BROWSERS[channel]} başlatılamadı: {message.splitlines()[0][:300]}") from exc
    context.set_default_timeout(timeout_ms)
    context.set_default_navigation_timeout(timeout_ms)
    return context


class WebSession:
    def __init__(self, profile: Path, *, timeout_ms: int, cancel: threading.Event | None = None):
        self.profile = Path(profile)
        self.timeout_ms = timeout_ms
        self.cancel = cancel
        self.channel: str | None = None
        self._runtime: Any = None
        self._context: Any = None
        self._page: Any = None
        self._opened: list[Any] = []
        self._owner: int | None = None
        self.notices: list[str] = []

    # ----- lifecycle --------------------------------------------------------------------
    def _check_thread(self) -> None:
        if self._owner is not None and self._owner != threading.get_ident():
            raise RuntimeError("A web session must be used by its owning workflow thread.")

    def open(self, url: str, *, browser: str = "auto", headless: bool = False) -> str:
        check_url(url)
        self._check_thread()
        if self._page is None:
            self._start(choose_channel(browser), headless)
        page = self.page
        self._run(lambda: page.goto(url, wait_until="load", timeout=self.timeout_ms), "Sayfa açılamadı")
        return str(page.url)

    def _start(self, channel: str, headless: bool) -> None:
        from playwright.sync_api import sync_playwright

        self._owner = threading.get_ident()
        try:
            self._runtime = sync_playwright().start()
            self._context = launch(self._runtime, self.profile, channel, headless, self.timeout_ms)
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._follow(self._page)
            self.channel = channel
        except Exception:
            self.close()
            raise

    def _follow(self, page: Any) -> None:
        """A tab this page opens (target=_blank, window.open) is where a person continues.

        Only the page's own popups count: the browser may open internal pages (Edge does for a
        download) that must never take over the work.
        """
        if getattr(page, "_rpa_followed", False):
            return
        page._rpa_followed = True
        page.on("popup", lambda popup: (self._opened.append(popup), self._follow(popup)))

    @property
    def page(self) -> Any:
        self._check_thread()
        if self._page is None:
            raise WorkflowError("Önce Web sayfası aç adımıyla bir sayfa açın.")
        opened = [page for page in self._opened if not page.is_closed()]
        self._opened.clear()
        if opened:
            self._page = opened[-1]
            self._run(lambda: self._page.wait_for_load_state("load", timeout=self.timeout_ms), "Yeni sekme yüklenemedi")
            self.notices.append(f"Sayfanın açtığı yeni sekmeye geçildi: {self._page.url}")
        elif self._page.is_closed():
            alive = [page for page in self._context.pages if not page.is_closed()]
            if not alive:
                raise WorkflowError("Tarayıcıda açık sekme kalmadı; Web sayfası aç adımıyla yeniden açın.")
            self._page = alive[-1]
            self.notices.append(f"Kapanan sekmenin yerine açık sekmeye geçildi: {self._page.url}")
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

    def _run(self, action: Any, label: str) -> Any:
        from playwright.sync_api import Error as PlaywrightError

        try:
            return action()
        except PlaywrightError as exc:
            first = str(exc).splitlines()[0][:300]
            if "Target page, context or browser has been closed" in str(exc) or "has been closed" in first:
                raise WorkflowError("Tarayıcı penceresi kapatıldı; Web sayfası aç adımıyla yeniden açın.") from exc
            if "Timeout" in first:
                raise WorkflowError(f"{label}: süre doldu.") from exc
            raise WorkflowError(f"{label}: {first}") from exc

    # ----- targets ----------------------------------------------------------------------
    def locator(self, target: Target) -> Any:
        return build_locator(self.page, target)

    def _matching(self, target: Target, visible: bool) -> list[Any]:
        found = self.locator(target)
        return self._run(lambda: [item for item in found.all() if not visible or item.is_visible()], "Sayfa okunamadı")

    def single(self, target: Target, *, visible: bool = True) -> Any:
        """Wait for exactly one (visible) match; more than one is never guessed between.

        Reading accepts an element that is merely present: an empty result line has no height.
        """
        deadline = time.monotonic() + target.timeout_ms / 1000
        while True:
            self._cancelled()
            matching = self._matching(target, visible)
            if len(matching) == 1:
                return matching[0]
            if len(matching) > 1:
                raise WorkflowError(f"“{target.value}” sayfada {len(matching)} öğeyle eşleşti; hangisinin kullanılacağı "
                                    "belirsiz, işlem yapılmadı. Tam eşleşmeyi açın veya daha ayırt edici bir hedef yazın.")
            if time.monotonic() >= deadline:
                where = " çerçevede" if target.frame else " sayfada"
                raise WorkflowError(f"“{target.value}” ({TARGETS[target.by].lower()}){where} bulunamadı. Sayfanın "
                                    "yüklendiğini ve hedefin görünür olduğunu kontrol edin.")
            self.page.wait_for_timeout(200)

    def _cancelled(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise InterruptedError("Web adımı iptal edildi.")

    # ----- element actions --------------------------------------------------------------
    def click(self, target: Target, kind: str = "single") -> None:
        item = self.single(target)
        page = self.page
        if kind == "hover":
            # Only moves the pointer over the element (menus that open on hover); nothing is pressed.
            self._run(lambda: item.hover(timeout=target.timeout_ms), "Öğenin üzerine gelinemedi")
            return

        def press() -> None:
            if kind == "double":
                item.dblclick(timeout=target.timeout_ms)
            elif kind in {"right", "middle"}:
                item.click(button=kind, timeout=target.timeout_ms)
            else:
                item.click(timeout=target.timeout_ms)

        # A link or form that opens another tab: wait for that tab, so the next step continues there.
        new_tab = kind == "single" and self._run(lambda: item.evaluate(
            "e => { const t = e.closest('a[target], form[target], area[target]');"
            " return !!t && !['', '_self', '_parent', '_top'].includes(t.target); }"), "Öğe okunamadı")
        # Never retried: a second click can submit a form twice.
        if new_tab:
            def click_and_wait() -> None:
                with page.expect_popup(timeout=target.timeout_ms):
                    press()

            self._run(click_and_wait, "Yeni sekme açılmadı")
        else:
            self._run(lambda: self._click_with_popup_watch(press, page, target, item), "Tıklanamadı")

    def _popup_client(self, item: Any, page: Any, target: Target) -> Any:
        from playwright.sync_api import Error as PlaywrightError

        if target.frame:
            handle = item.element_handle(timeout=target.timeout_ms)
            if handle is None:
                raise WorkflowError("Tıklanacak öğenin çerçevesi bulunamadı; işlem yapılmadı.")
            try:
                frame = handle.owner_frame()
            finally:
                handle.dispose()
            if frame is None:
                raise WorkflowError("Tıklanacak öğenin çerçevesi kapandı; işlem yapılmadı.")
            while frame is not None and frame != page.main_frame:
                self._cancelled()
                try:
                    return self._context.new_cdp_session(frame)
                except PlaywrightError as exc:
                    # Same-process frames share their ancestor's protocol session.
                    # Any other attach failure stops before the click.
                    if "does not have a separate CDP session" not in str(exc):
                        raise
                    frame = frame.parent_frame
        return self._context.new_cdp_session(page)

    def _click_with_popup_watch(self, press: Any, page: Any, target: Target, item: Any) -> None:
        """Wait for an observed window.open, not for a guessed destination or a fixed load delay."""
        from playwright.sync_api import Error as PlaywrightError

        # Playwright emits popup only after the initial HTTP response arrives.
        # Chromium's earlier windowOpen event tells us a popup is actually pending.
        # Chrome and Edge are the only supported browsers; no page scripts are replaced.
        client = self._popup_client(item, page, target)
        pending, opened = 0, 0

        def opening(_event: Any) -> None:
            nonlocal pending
            pending += 1

        def available(_popup: Any) -> None:
            nonlocal opened
            opened += 1

        client.on("Page.windowOpen", opening)
        page.on("popup", available)
        try:
            client.send("Page.enable")
            self._cancelled()
            deadline = time.monotonic() + target.timeout_ms / 1000
            press()  # Exactly once, including timeout/cancellation paths.
            # Preserve the short event-delivery grace for scripts scheduled by the click.
            # Slow network responses wait only when the browser observed a new window.
            # A frame from another site reports through its own browser process, which can take longer.
            if not pending and not opened:
                grace = 500 if target.frame else 150
                page.wait_for_timeout(min(grace, max(0, deadline - time.monotonic()) * 1000))
            while opened < pending:
                self._cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WorkflowError("Yeni sekme açılmadı: süre doldu; önceki sayfada işleme devam edilmedi.")
                page.wait_for_timeout(min(50, remaining * 1000))
            self._cancelled()
        finally:
            page.remove_listener("popup", available)
            try:
                client.detach()
            except PlaywrightError:
                pass  # Closing the page also closes its diagnostic session.

    def fill(self, target: Target, text: str) -> None:
        item = self.single(target)
        self._run(lambda: item.fill(text, timeout=target.timeout_ms), "Alan doldurulamadı")

    def read(self, target: Target) -> str:
        item = self.single(target, visible=False)

        def content() -> str:
            tag = item.evaluate("element => element.tagName").lower()
            return item.input_value() if tag in {"input", "textarea", "select"} else item.inner_text()

        return str(self._run(content, "Metin okunamadı"))

    def select(self, target: Target, option: str) -> str:
        item = self.single(target)
        labels = self._run(lambda: item.evaluate(
            "element => element.tagName === 'SELECT' ? [...element.options].map(o => o.label.trim()) : null"),
            "Liste okunamadı")
        if labels is None:
            raise WorkflowError("Hedef bir açılır liste (select) değil; seçenek için Web öğesine tıkla adımını kullanın.")
        from ..actions.common import fold

        # Turkish-aware: "iade" finds "İade edildi" (str.casefold turns İ into i + a combining dot).
        matches = [label for label in labels if label == option.strip()] or (
            [] if target.exact else [label for label in labels if fold(option.strip()) in fold(label)])
        if len(matches) != 1:
            shown = ", ".join(labels[:15])
            raise WorkflowError(f"“{option}” seçeneği listede {'bulunamadı' if not matches else 'birden fazla kez geçiyor'};"
                                f" seçilmedi. Seçenekler: {shown}")
        self._run(lambda: item.select_option(label=matches[0], timeout=target.timeout_ms), "Seçilemedi")
        return matches[0]

    def press(self, key: str, modifier: str = "", target: Target | None = None) -> None:
        if key not in KEYS or modifier not in MODIFIERS:
            raise WorkflowError("Tuş seçimi geçersiz.")
        combo = f"{MODIFIERS[modifier]}+{key}" if modifier else key
        if target is not None:
            item = self.single(target)
            self._run(lambda: item.press(combo, timeout=target.timeout_ms), "Tuşa basılamadı")
        else:
            page = self.page
            self._run(lambda: page.keyboard.press(combo), "Tuşa basılamadı")

    def upload(self, target: Target, files: list[Path]) -> None:
        item = self.single(target, visible=False)
        kind = self._run(lambda: item.evaluate("e => e.tagName === 'INPUT' ? e.type : e.tagName"), "Alan okunamadı")
        if str(kind).lower() != "file":
            raise WorkflowError("Hedef bir dosya seçme alanı (input type=file) değil; dosya yüklenmedi.")
        self._run(lambda: item.set_input_files([str(path) for path in files], timeout=target.timeout_ms),
                  "Dosya yüklenemedi")

    def download(self, target: Target, folder: Path, overwrite: bool) -> Path:
        item = self.single(target)
        page = self.page
        folder.mkdir(parents=True, exist_ok=True)

        def fetch() -> Any:
            with page.expect_download(timeout=target.timeout_ms) as waiting:
                item.click(timeout=target.timeout_ms)
            return waiting.value

        download = self._run(fetch, "İndirme başlamadı")
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", download.suggested_filename or "indirilen-dosya") or "indirilen-dosya"
        destination = folder / name
        if destination.exists() and not overwrite:
            stem, suffix, number = destination.stem, destination.suffix, 2
            while destination.exists():
                destination = folder / f"{stem} ({number}){suffix}"
                number += 1
        self._run(lambda: download.save_as(str(destination)), "İndirilen dosya kaydedilemedi")
        failure = download.failure()
        if failure:
            raise WorkflowError(f"İndirme tamamlanmadı: {failure}")
        return destination

    def read_table(self, target: Target, header: bool) -> list[dict]:
        from ..desktop.table_columns import column_names

        item = self.single(target, visible=False)
        rows = self._run(lambda: item.evaluate("""element => {
            const table = element.closest('table') || element.querySelector('table');
            if (!table) return null;
            return [...table.rows].map(row => [...row.cells].map(cell => cell.innerText.replace(/\\s+/g, ' ').trim()));
        }"""), "Tablo okunamadı")
        if rows is None:
            raise WorkflowError("Hedef bir tablonun içinde değil; tablodaki bir hücreyi veya tabloyu seçin.")
        rows = [row for row in rows if any(row)]
        width = max((len(row) for row in rows), default=0)
        rows = [row + [""] * (width - len(row)) for row in rows]
        titles, data = (rows[0], rows[1:]) if header and rows else ([], rows)
        names = column_names(titles, width)
        return [dict(zip(names, row)) for row in data]

    # ----- page actions -----------------------------------------------------------------
    def wait(self, condition: str, *, target: Target | None = None, text: str = "", timeout_ms: int) -> bool:
        """visible / hidden: the target; url: the address contains text. False when time runs out."""
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            self._cancelled()
            if condition == "url":
                met = text in str(self.page.url)
            else:
                count = len(self._matching(target, True))
                if count > 1 and condition == "visible":
                    raise WorkflowError(f"“{target.value}” sayfada {count} öğeyle eşleşti; daha ayırt edici bir hedef "
                                        "yazın.")
                met = count == 1 if condition == "visible" else count == 0
            if met:
                return True
            if time.monotonic() >= deadline:
                return False
            self.page.wait_for_timeout(250)

    def navigate(self, action: str) -> str:
        page = self.page
        calls = {"back": lambda: page.go_back(wait_until="load"), "forward": lambda: page.go_forward(wait_until="load"),
                 "reload": lambda: page.reload(wait_until="load")}
        if action not in calls:
            raise WorkflowError("Gezinme seçimi geçersiz.")
        self._run(calls[action], "Sayfada gezinilemedi")
        return str(page.url)

    def tab(self, action: str, text: str = "") -> str:
        self.page  # take a newly opened tab into account first
        pages = [page for page in self._context.pages if not page.is_closed()]
        if action == "close":
            if len(pages) < 2:
                raise WorkflowError("Tek sekme açık; kapatılmadı. Tarayıcı çalışma bitince kendisi kapanır.")
            self._run(self._page.close, "Sekme kapatılamadı")
            self._page = [page for page in pages if page is not self._page][-1]
            return str(self._page.url)
        if action in {"first", "last"}:
            chosen = [pages[0] if action == "first" else pages[-1]]
        elif action in {"title", "url"}:
            from ..actions.common import fold

            wanted = fold(text.strip())
            if not wanted:
                raise WorkflowError("Sekmenin başlığında veya adresinde geçen metni yazın.")
            chosen = [page for page in pages if wanted in fold(page.title() if action == "title" else page.url)]
        else:
            raise WorkflowError("Sekme seçimi geçersiz.")
        if len(chosen) != 1:
            raise WorkflowError(f"“{text}” {len(chosen)} sekmeyle eşleşti; tek bir sekme seçilebilir." if chosen
                                else f"“{text}” geçen bir sekme bulunamadı.")
        self._page = chosen[0]
        self._follow(self._page)
        self._run(lambda: self._page.bring_to_front(), "Sekmeye geçilemedi")
        return str(self._page.url)

    def screenshot(self, full_page: bool) -> bytes:
        page = self.page
        return self._run(lambda: page.screenshot(full_page=full_page), "Sayfa görüntüsü alınamadı")

    def script(self, code: str, argument: Any) -> Any:
        """The person's own JavaScript, as the body of async (girdi) => { … } in the page."""
        page = self.page
        source = f"async (girdi) => {{\n{code}\n}}"
        result = self._run(lambda: page.evaluate(source, argument), "JavaScript çalıştırılamadı")
        if len(json.dumps(result, ensure_ascii=False, default=str)) > SCRIPT_RESULT_LIMIT:
            raise WorkflowError("JavaScript sonucu 5 MB'ı aşıyor; daha küçük bir değer döndürün.")
        return result
