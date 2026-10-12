"""Tarayıcıda seç: open the web steps' browser, let the person click an element, return its target.

A banner in the page has a Seçim modu switch, so the person can first browse and sign in. While
it is on, a click is captured instead of reaching the page. The target is chosen among what a
person would name it by (label, placeholder, button name, text) and only kept when, checked by
Playwright exactly as a run will look for it, it finds that one element and nothing else.
"""

from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..errors import WorkflowError
from .web_session import BROWSERS, TARGETS, Target, build_locator, check_url, choose_channel, launch

PICK_TIMEOUT = 600

OVERLAY = r"""
(() => {
  if (window.__rpaPickerReady) return;
  window.__rpaPickerReady = true;
  const top = window.top === window;
  let enabled = false, box = null, bar = null;  // off until the Studio answers: no accidental pick
  const style = (el, css) => { el.setAttribute("style", css); return el; };
  function ensure() {
    if (!document.body) return false;
    if (!box) {
      box = style(document.createElement("div"),
        "position:fixed;z-index:2147483646;pointer-events:none;border:2px solid #2340d9;" +
        "background:rgba(35,64,217,.12);border-radius:3px;display:none");
      box.dataset.rpaPicker = "1";
      document.documentElement.append(box);
    }
    if (top && !bar) {
      bar = style(document.createElement("div"),
        // A small corner panel: a full-width bar would cover the page's own top controls.
        "position:fixed;z-index:2147483647;right:16px;bottom:16px;max-width:360px;padding:10px 12px;" +
        "font:600 13px system-ui,sans-serif;line-height:1.35;background:#151a26;color:#f2efe7;border-radius:10px;" +
        "display:flex;gap:10px;align-items:center;box-shadow:0 4px 16px #0006");
      bar.dataset.rpaPicker = "1";
      const text = document.createElement("span");
      const toggle = document.createElement("button");
      style(toggle, "font:inherit;padding:4px 10px;border-radius:6px;border:0;background:#ffd23f;color:#151a26;cursor:pointer");
      const paint = () => {
        text.textContent = enabled
          ? "RpaOrkestrAI · Seçim açık: hedef öğeye tıklayın."
          : "RpaOrkestrAI · Seçim kapalı: gezinin veya giriş yapın, sonra seçimi açın.";
        toggle.textContent = enabled ? "Seçimi kapat" : "Seçimi aç";
        if (!enabled && box) box.style.display = "none";
      };
      toggle.addEventListener("click", (event) => { event.stopPropagation(); enabled = !enabled;
        window.__rpaSetMode(enabled); paint(); }, true);
      window.__rpaPaint = paint;
      bar.append(text, toggle);
      document.documentElement.append(bar);
      paint();
    }
    return true;
  }
  const ours = (el) => el && el.closest && el.closest("[data-rpa-picker]");
  // The switch lives in the Studio: it survives navigation (signing in) and reaches every frame.
  const on = () => enabled;
  window.__rpaGetMode().then((value) => { enabled = !!value; if (window.__rpaPaint) window.__rpaPaint(); });
  setInterval(() => window.__rpaGetMode().then((value) => { if (enabled !== !!value) {
    enabled = !!value; if (window.__rpaPaint) window.__rpaPaint(); } }), 500);
  const pickable = (el) => el.closest("input,select,textarea,button,a,label,summary,[role=button],[role=link]," +
    "[role=checkbox],[role=tab],[role=menuitem],[contenteditable=true]") || el;
  document.addEventListener("mousemove", (event) => {
    if (!ensure() || !on()) { if (box) box.style.display = "none"; return; }
    const el = event.target;
    if (ours(el)) return;
    const rect = pickable(el).getBoundingClientRect();
    Object.assign(box.style, { display: "block", left: rect.left + "px", top: rect.top + "px",
      width: rect.width + "px", height: rect.height + "px" });
  }, true);
  for (const kind of ["pointerdown", "mousedown", "mouseup", "click"]) {
    document.addEventListener(kind, (event) => {
      if (ours(event.target) || !on()) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (kind === "click") {
        // A DOM element cannot cross to Playwright: mark it; the Studio finds it by the mark and removes it.
        const token = Math.random().toString(36).slice(2) + Date.now().toString(36);
        pickable(event.target).setAttribute("data-rpa-picked", token);
        window.__rpaPicked(token);
      }
    }, true);
  }
  if (document.readyState !== "loading") ensure(); else document.addEventListener("DOMContentLoaded", ensure);
})();
"""

CANDIDATES = r"""
(el) => {
  const clean = (text) => (text || "").replace(/\s+/g, " ").trim();
  const short = (text) => { text = clean(text); return text && text.length <= 80 ? text : ""; };
  if (el.tagName === "LABEL" && el.control) el = el.control;
  const result = [];
  const add = (by, value) => { if (value && !result.some(c => c.by === by && c.value === value)) result.push({ by, value }); };
  const control = ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName);
  if (control) {
    const label = el.labels && el.labels[0] ? el.labels[0].innerText : "";
    add("label", short(el.getAttribute("aria-label")) || short(label));
    add("placeholder", short(el.getAttribute("placeholder")));
  }
  const role = el.getAttribute("role");
  if (el.tagName === "BUTTON" || el.tagName === "A" || role === "button" || role === "link" ||
      (el.tagName === "INPUT" && ["submit", "button"].includes(el.type))) {
    add("button", short(el.getAttribute("aria-label")) || short(el.innerText) || short(el.value));
  }
  if (!control) add("text", short(el.innerText));
  const css = (value) => (window.CSS && CSS.escape) ? CSS.escape(value) : value.replace(/["\\]/g, "\\$&");
  for (const name of ["data-testid", "data-test", "data-qa"]) {
    if (el.getAttribute(name)) add("css", `[${name}="${css(el.getAttribute(name))}"]`);
  }
  if (el.id && !/\d{4,}|^[a-f0-9-]{16,}$/i.test(el.id)) add("css", `#${css(el.id)}`);
  if (el.getAttribute("name")) add("css", `${el.tagName.toLowerCase()}[name="${css(el.getAttribute("name"))}"]`);
  const path = [];
  for (let node = el; node && node.nodeType === 1 && node !== document.documentElement; node = node.parentElement) {
    let part = node.tagName.toLowerCase();
    if (node.parentElement) {
      const same = [...node.parentElement.children].filter(c => c.tagName === node.tagName);
      if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
    }
    path.unshift(part);
    if (node.tagName === "BODY") break;
  }
  add("css", path.join(" > "));
  return { candidates: result, summary: `${el.tagName.toLowerCase()} · ${short(el.innerText) || short(el.value) || ""}` };
}
"""


def frame_selector(frame: Any) -> str:
    """CSS for the iframe holding frame, from its id or name; empty for the main page."""
    if frame.parent_frame is None:
        return ""
    element = frame.frame_element()
    found = element.evaluate("""f => f.id ? `iframe#${CSS.escape(f.id)}` :
        f.name ? `iframe[name="${CSS.escape(f.name)}"]` : ''""")
    if not found:
        raise WorkflowError("Seçilen öğe kimliksiz bir çerçevenin içinde; çerçeveyi CSS ile elle belirtin.")
    if frame.parent_frame.parent_frame is not None:
        raise WorkflowError("İç içe çerçevelerdeki öğeler seçilemiyor; hedefi elle yazın.")
    return found


def choose(page: Any, frame: Any, handle: Any) -> dict:
    """The first candidate that finds exactly this element, as a run will search for it."""
    from playwright.sync_api import Error as PlaywrightError

    described = handle.evaluate(CANDIDATES)
    selector = frame_selector(frame)
    for candidate in described["candidates"]:
        target = Target(by=candidate["by"], value=candidate["value"], exact=True, frame=selector, timeout_ms=1000)
        try:
            found = [item for item in build_locator(page, target).all() if item.is_visible()]
        except (WorkflowError, PlaywrightError):
            continue
        if len(found) == 1 and found[0].evaluate("(a, b) => a === b", handle):
            return {"by": target.by, "target": target.value, "exact": True, "frame": selector,
                    "summary": f"{TARGETS[target.by]}: {target.value}" + (f" · çerçeve {selector}" if selector else "")}
    raise WorkflowError("Öğe için sayfada tek olan bir hedef bulunamadı. Başka bir öğeyi veya üstündeki düğmeyi seçin.")


class WebPicks:
    """One Tarayıcıda seç at a time; it shares the desktop reservation with runs."""

    def __init__(self, manager: Any, profile: Path, *, timeout_ms: int = 30_000, attention: Any = None,
                 headless: bool = False, on_ready: Any = None):
        self.manager, self.profile, self.timeout_ms, self.attention = manager, Path(profile), timeout_ms, attention
        # Tests drive the page from the picker's own thread (sync Playwright is thread-bound).
        self.headless, self.on_ready = headless, on_ready
        self._lock = threading.RLock()
        self._job: dict | None = None

    def start(self, url: str, browser: str = "auto") -> dict:
        if url:
            check_url(url)
        if browser not in BROWSERS:
            raise WorkflowError("Tarayıcı seçimi geçersiz.")
        with self._lock:
            if self._job and not self._job["done"]:
                raise RuntimeError("Tarayıcıda seçim zaten açık; önce onu tamamlayın veya kapatın.")
            cancel = threading.Event()
            token = self.manager.reserve_desktop(cancel)
            job = {"public": {"id": uuid4().hex, "status": "starting", "message": "Tarayıcı açılıyor…"},
                   "cancel": cancel, "token": token, "done": False}
            self._job = job
            threading.Thread(target=self._work, args=(job, url, browser), daemon=True, name="rpa-web-picker").start()
            return copy.deepcopy(job["public"])

    def _update(self, job: dict, **values: Any) -> None:
        with self._lock:
            job["public"].update(values)

    def _work(self, job: dict, url: str, browser: str) -> None:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        runtime = context = None
        picked: list[tuple[Any, Any]] = []
        try:
            channel = choose_channel(browser)
            runtime = sync_playwright().start()
            context = launch(runtime, self.profile, channel, self.headless, self.timeout_ms)
            context.expose_binding("__rpaPicked", lambda source, token: picked.append((source, str(token))))
            mode = {"on": True}
            context.expose_binding("__rpaSetMode", lambda source, value: mode.update(on=bool(value)))
            context.expose_binding("__rpaGetMode", lambda source: mode["on"])
            context.add_init_script(OVERLAY)
            page = context.pages[0] if context.pages else context.new_page()
            if url:
                page.goto(url, wait_until="load")
            for frame in page.frames:
                frame.evaluate(OVERLAY)
            self._update(job, status="waiting", message="Tarayıcıda hedef öğeye tıklayın. Önce gezinmek veya giriş "
                                                        "yapmak için sağ alttaki Seçimi kapat düğmesini kullanın.")
            if self.on_ready is not None:
                self.on_ready(page)
            deadline = time.monotonic() + PICK_TIMEOUT
            while not picked:
                if job["cancel"].is_set():
                    raise InterruptedError()
                alive = [item for item in context.pages if not item.is_closed()]
                if not alive:
                    raise InterruptedError()
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                alive[-1].wait_for_timeout(200)
            source, token = picked[0]
            if not token.isalnum():
                raise WorkflowError("Seçim bilgisi okunamadı; yeniden deneyin.")
            handle = source["frame"].locator(f'[data-rpa-picked="{token}"]').element_handle(timeout=5000)
            handle.evaluate("element => element.removeAttribute('data-rpa-picked')")
            result = choose(source["page"], source["frame"], handle)
            result["url"] = source["page"].url
            self._update(job, status="completed", message=f"Seçildi: {result['summary']}", result=result)
        except InterruptedError:
            self._update(job, status="cancelled", message="Tarayıcıda seçim kapatıldı.")
        except TimeoutError:
            self._update(job, status="error", message="10 dakika içinde öğe seçilmedi; yeniden deneyin.")
        except WorkflowError as exc:
            self._update(job, status="error", message=str(exc))
        except PlaywrightError as exc:
            closed = "has been closed" in str(exc)
            self._update(job, status="cancelled" if closed else "error",
                         message="Tarayıcıda seçim kapatıldı." if closed else
                         f"Tarayıcıda seçim tamamlanamadı: {str(exc).splitlines()[0][:200]}")
        except Exception as exc:  # never leave the Studio waiting
            self._update(job, status="error", message=f"Tarayıcıda seçim tamamlanamadı: {exc}")
        finally:
            for resource, method in ((context, "close"), (runtime, "stop")):
                if resource is not None:
                    try:
                        getattr(resource, method)()
                    except Exception:
                        pass
            self.manager.release_desktop(job["token"])
            with self._lock:
                job["done"] = True
            if self.attention is not None and job["public"]["status"] == "completed":
                try:
                    self.attention()
                except Exception:
                    pass

    def status(self, key: str) -> dict:
        with self._lock:
            if not self._job or self._job["public"]["id"] != key:
                raise KeyError(key)
            return copy.deepcopy(self._job["public"])

    def cancel(self, key: str) -> None:
        with self._lock:
            if self._job and self._job["public"]["id"] == key:
                self._job["cancel"].set()

    def close(self) -> None:
        with self._lock:
            if self._job:
                self._job["cancel"].set()
