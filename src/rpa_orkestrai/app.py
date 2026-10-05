"""Loopback-only HTTP interface shared by the browser and native desktop shell."""

from __future__ import annotations

import json
import math
import platform
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__, autostart, template_bundle
from .catalog import ACTION_DEFINITIONS, library_catalog
from .config import Settings
from .engine import ARTIFACT_TYPES, RunManager, WorkflowError, validate_workflow
from .guide import QUICK_GUIDE
from .instance import identity
from .licensing import OPEN_PATHS, LicenseError, LicenseService, LicenseUnavailable
from .locking import WorkspaceLock
from .models import (
    AutostartRequest,
    DesktopPickRequest,
    FavoriteRequest,
    LicenseLoginRequest,
    PathRequest,
    PointerRequest,
    RecordRequest,
    RunRequest,
    Schedule,
    ScheduleInput,
    ScheduleSettings,
    SecretRequest,
    StepTestRequest,
    TemplateCropRequest,
    WindowCheckRequest,
    Workflow,
    WorkflowImport,
    WorkflowInput,
    now,
    uid,
)
from .scheduler import ScheduleBook, Scheduler, forecast, next_occurrence, planned, summary, upcoming
from .storage import Store
from .vault import Vault, VaultError

REQUEST_LIMIT = 2_000_000
# A flow file carries its reference images, so an import may be larger than other requests.
IMPORT_LIMIT = 16_000_000

LICENSE_STOPS = {
    "unverified": "Lisans uzun süredir doğrulanamadığı için akış durduruldu.",
    "session": "Bu bilgisayardaki oturum kapandığı için akış durduruldu.",
}


def create_app(settings: Settings | None = None, *, licensing: LicenseService | None = None) -> FastAPI:
    settings = settings or Settings()
    licensing = licensing or LicenseService(settings.data_dir)
    store = Store(settings.data_dir)
    manager = RunManager(settings, store)
    # The license is checked where work starts as well as at the API, and a flow that is running
    # when the Studio locks stops at its next step.
    manager.gate = licensing.allowed
    licensing.on_locked = lambda reason: manager.stop_active(
        LICENSE_STOPS.get(reason, "Lisans geçerliliğini yitirdiği için akış durduruldu."))
    from .desktop.pick_jobs import PickJobs
    from .desktop.targets import CaptureStore

    captures = CaptureStore()
    picks = PickJobs(manager, captures)
    from .desktop.recorder import RecordJobs
    from .desktop.windows import WindowService

    def recorder_view(stop, cancel):
        from .desktop.picker import native_available
        from .desktop.recorder import RecorderView

        return RecorderView(stop, cancel) if native_available() else None

    records = RecordJobs(manager, windows_factory=WindowService, view_factory=recorder_view)
    from .connections import Connections

    connections = Connections(settings.data_dir, settings)
    book = ScheduleBook(settings.data_dir)

    def workflow_name(workflow_id: str) -> str | None:
        try:
            return store.workflow(workflow_id).name
        except (KeyError, ValueError):
            return None

    def attention() -> None:
        # The desktop window sets this (native.py); in a browser there is nothing to bring forward.
        hook = getattr(settings, "bring_to_front", None)
        if hook:
            hook()

    def run_state(run_id: str) -> str | None:
        try:
            return store.run(run_id).status
        except (KeyError, ValueError):
            return None

    scheduler = Scheduler(book, start_run=lambda workflow_id: manager.start(store.workflow(workflow_id),
                                                                            trigger="schedule"),
                          allowed=licensing.allowed, busy=manager.busy, workflow_name=workflow_name,
                          attention=attention, run_state=run_state, stop_run=manager.stop_run)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with WorkspaceLock(settings.data_dir):
            store.recover_runs()
            licensing.start()
            scheduler.start()
            try:
                yield
            finally:
                scheduler.stop()
                licensing.stop()
                records.close()
                picks.close()
                manager.close()

    app = FastAPI(title="RpaOrkestrAI Studio", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.store, app.state.manager, app.state.settings = store, manager, settings
    app.state.picks, app.state.licensing, app.state.records = picks, licensing, records
    app.state.scheduler = scheduler
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # A hostile website must not be able to control the local mouse through a form/fetch.
        origin = request.headers.get("origin")
        if origin:
            try:
                parsed = urlsplit(origin)
            except ValueError:
                return JSONResponse({"detail": "Geçersiz kaynak."}, status_code=403)
            expected = urlsplit(str(request.base_url))
            if parsed.scheme != expected.scheme or parsed.netloc != expected.netloc:
                return JSONResponse({"detail": "Başka bir kaynaktan uygulamaya erişim engellendi."}, status_code=403)
        elif request.headers.get("sec-fetch-site") == "cross-site" and not (
            request.method == "GET" and request.url.path == "/"
            and request.headers.get("sec-fetch-mode") == "navigate"
        ):
            return JSONResponse({"detail": "Harici tarayıcı isteği engellendi."}, status_code=403)
        limit = IMPORT_LIMIT if request.url.path == "/api/workflows/import" else REQUEST_LIMIT
        too_large = JSONResponse({"detail": f"İstek en fazla {limit // 1_000_000} MB olabilir."}, status_code=413)
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Geçersiz istek uzunluğu."}, status_code=400)
        if content_length > limit:
            return too_large
        if request.method in {"POST", "PUT", "PATCH"}:
            received = bytearray()
            async for chunk in request.stream():
                received.extend(chunk)
                if len(received) > limit:
                    return too_large
            # BaseHTTPMiddleware reuses a cached body when forwarding to the route.
            request._body = bytes(received)
        path = request.url.path
        if path.startswith("/api/") and path not in OPEN_PATHS and not licensing.allowed():
            status = license_status()
            response = JSONResponse({"detail": status["message"] or "Devam etmek için RpaOrkestrAI hesabınızla giriş yapın.",
                                     "license": status}, status_code=403)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def not_found(request: Request, exc: KeyError):
        return JSONResponse({"detail": "Kayıt bulunamadı."}, status_code=404)

    @app.exception_handler(WorkflowError)
    async def invalid_workflow(request: Request, exc: WorkflowError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        # FastAPI's default validation errors echo the input, including submitted secrets.
        details = "; ".join(".".join(map(str, e["loc"])) + ": " + e["msg"] for e in exc.errors())
        return JSONResponse({"detail": details[:1500]}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/instance")
    def instance():
        return identity(settings.data_dir)

    def license_status():
        from .desktop.picker import native_available

        return {**licensing.status(), "can_quit": native_available()}

    @app.get("/api/license")
    def license_state():
        return license_status()

    @app.post("/api/license/login")
    def license_login(body: LicenseLoginRequest):
        try:
            licensing.login(body.username, body.password)
        except LicenseUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LicenseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return license_status()

    @app.post("/api/license/refresh")
    def license_refresh():
        licensing.refresh()
        return license_status()

    @app.post("/api/license/logout")
    def license_logout():
        licensing.logout()
        return license_status()

    @app.post("/api/license/quit", status_code=202)
    def quit_application():
        from .desktop.picker import close_native_window, native_available

        if not native_available():
            raise HTTPException(status_code=409, detail="Tarayıcıda çalışırken bu sekmeyi kapatabilirsiniz.")
        # Answer first; the window closes once the response has been sent.
        threading.Timer(0.3, close_native_window).start()
        return {"closing": True}

    @app.get("/api/bootstrap")
    def bootstrap():
        return {"platform": platform.system(), "version": __version__, "workflows": store.workflows(),
                "runs": store.runs(), "catalog": library_catalog(), "settings": settings.public(),
                "action_definitions": ACTION_DEFINITIONS + library_catalog(),
                "favorites": store.favorites(), "updates": update_status(), "connections": connections.list(),
                "quick_guide": QUICK_GUIDE}

    def update_status():
        from .update_service import source_status

        updater = getattr(settings, "desktop_updates", None)
        return updater.status() if updater is not None else source_status()

    @app.get("/api/updates")
    def updates():
        return update_status()

    @app.post("/api/updates/check")
    def check_updates():
        updater = getattr(settings, "desktop_updates", None)
        if updater is not None:
            updater.start()
        return update_status()

    @app.get("/api/catalog")
    def catalog():
        return library_catalog()

    @app.put("/api/favorites/{action_type}")
    def set_favorite(action_type: str, body: FavoriteRequest):
        return store.set_favorite(action_type, body.favorite)

    @app.get("/api/desktop/windows")
    def desktop_windows():
        from .desktop.windows import WindowError, WindowService

        try:
            return [window.result() for window in WindowService().list_windows()]
        except WindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/desktop/windows/check")
    def check_desktop_window(body: WindowCheckRequest):
        from .desktop.windows import WindowError, WindowService

        try:
            return WindowService().find(body.application, body.title, body.match, on_missing="continue")
        except WindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/desktop/pick/capabilities")
    def picker_capabilities():
        return {"native": picks.available()}

    @app.post("/api/desktop/pick", status_code=202)
    def start_desktop_pick(body: DesktopPickRequest):
        from .desktop.windows import WindowError

        try:
            return picks.start(body.model_dump(include={"application", "title", "match"}), body.mode, body.delay)
        except WindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/desktop/pick/{pick_id}")
    def desktop_pick_status(pick_id: str):
        return picks.status(pick_id)

    @app.delete("/api/desktop/pick/{pick_id}", status_code=204)
    def cancel_desktop_pick(pick_id: str):
        picks.cancel(pick_id)
        return Response(status_code=204)

    @app.post("/api/desktop/capture-window")
    def capture_desktop_window(body: WindowCheckRequest):
        from .desktop.controller import DesktopController
        from .desktop.windows import WindowError, WindowService

        try:
            with manager.desktop_setup():
                windows = WindowService()
                previous = next((w for w in windows.list_windows() if windows.backend.is_active(w)), None)
                target = windows.find(body.application, body.title, body.match)
                try:
                    window, image = windows.screenshot_window(target, DesktopController())
                    return captures.add(window, image)
                finally:
                    if previous is not None and previous.window_id != target.get("window_id"):
                        try:
                            windows.focus(previous.result())
                        except WindowError:
                            pass  # The capture remains valid; the user can switch back manually.
        except WindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail="Hedef seçimi şu anda kullanılamıyor. Çalışan akışı ve ekran izinlerini kontrol edin.") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Pencere görüntüsü alınamadı. Ekran izinlerini kontrol edin ve ERP'yi ana ekrana taşıyın.") from exc

    def while_studio_hidden(delay: int, work):
        """Hide the native Studio window during a countdown so the target app is visible."""
        from .desktop.picker import _host, _host_lock

        with _host_lock:
            host = _host
        studio = host[1] if host else None
        if studio is not None:
            studio.hide()
        try:
            import time

            time.sleep(delay)
            return work()
        finally:
            if studio is not None:
                studio.show()

    @app.post("/api/desktop/pointer")
    def read_pointer(body: PointerRequest):
        from .desktop.controller import DesktopController

        try:
            with manager.desktop_setup():
                x, y = while_studio_hidden(body.delay, lambda: DesktopController().position())
                return {"x": x, "y": y}
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail="Fare konumu şu anda alınamıyor. Çalışan akışı bekleyin.") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Fare konumu okunamadı. Ekran/erişilebilirlik izinlerini "
                                                        "kontrol edin.") from exc

    @app.post("/api/desktop/capture-screen")
    def capture_screen(body: PointerRequest):
        from .desktop.controller import DesktopController
        from .desktop.windows import WindowError, WindowInfo

        try:
            with manager.desktop_setup():
                def grab():
                    desktop = DesktopController()
                    image = desktop.screenshot()
                    screen = WindowInfo(0, 0, "Ekran", "Ana ekran", 0, 0, image.width, image.height)
                    return captures.add(screen, image)

                return while_studio_hidden(body.delay, grab)
        except WindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail="Ekran görüntüsü şu anda alınamıyor. Çalışan akışı bekleyin.") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Ekran görüntüsü alınamadı. Ekran Kaydı iznini kontrol edin.") from exc

    @app.post("/api/desktop/record", status_code=202)
    def start_recording(body: RecordRequest):
        from .desktop.windows import WindowError

        try:
            return records.start(delay=body.delay, record_waits=body.record_waits,
                                 relative_windows=body.relative_windows)
        except WindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc) if "kayıt" in str(exc).lower() else
                                "Kayıt şu anda başlatılamıyor. Çalışan akışı veya hedef seçimini bekleyin.") from exc

    @app.get("/api/desktop/record/{record_id}")
    def recording_status(record_id: str):
        return records.status(record_id)

    @app.post("/api/desktop/record/{record_id}/stop")
    def stop_recording(record_id: str):
        return records.stop(record_id)

    @app.delete("/api/desktop/record/{record_id}", status_code=204)
    def cancel_recording(record_id: str):
        records.cancel(record_id)
        return Response(status_code=204)

    @app.post("/api/desktop/choose-path")
    def choose_path(body: PathRequest):
        from .desktop.picker import _host, _host_lock

        with _host_lock:
            host = _host
        if host is None:
            raise HTTPException(status_code=409, detail="Dosya seçme penceresi masaüstü uygulamasında kullanılabilir; "
                                                        "tarayıcıda yolu elle yazın.")
        webview, window = host
        kinds = getattr(webview, "FileDialog", None)
        dialog = {"open": getattr(kinds, "OPEN", 10), "folder": getattr(kinds, "FOLDER", 20),
                  "save": getattr(kinds, "SAVE", 30)}[body.kind]
        chosen = window.create_file_dialog(dialog)
        if not chosen:
            return {"path": None}
        return {"path": chosen if isinstance(chosen, str) else chosen[0]}

    def template_folder() -> Path:
        return Path(settings.get("template_dir")).expanduser().resolve()

    @app.post("/api/desktop/templates", status_code=201)
    def save_template(body: TemplateCropRequest):
        from .desktop.windows import WindowError

        try:
            return captures.crop(**body.model_dump(), folder=template_folder())
        except WindowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=422, detail="Referans görsel kaydedilemedi. Şablon klasörünün yazma iznini kontrol edin.") from exc

    @app.delete("/api/desktop/captures/{capture_id}", status_code=204)
    def discard_capture(capture_id: str):
        captures.discard(capture_id)
        return Response(status_code=204)

    @app.get("/api/workflows")
    def list_workflows():
        return store.workflows()

    @app.post("/api/workflows", status_code=201)
    def create_workflow(body: WorkflowInput):
        workflow = Workflow(**body.model_dump())
        validate_workflow(workflow, ready=False)
        return store.save_workflow(workflow)

    @app.post("/api/workflows/import", status_code=201)
    def import_workflow(body: WorkflowImport):
        # Imported identity/timestamps are always replaced; import never starts a run.
        values = body.model_dump(exclude={"id", "created_at", "updated_at", "templates"})
        workflow = Workflow(**values)
        validate_workflow(workflow, ready=False)
        if body.templates:
            try:
                renamed = template_bundle.unpack(body.templates, template_folder())
            except template_bundle.TemplateError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except OSError as exc:
                raise HTTPException(status_code=422, detail="Referans görseller kaydedilemedi. Şablon klasörünün "
                                                            "yazma iznini kontrol edin.") from exc
            template_bundle.rename(workflow.steps, renamed)
        return store.save_workflow(workflow)

    @app.get("/api/workflows/{workflow_id}")
    def get_workflow(workflow_id: str):
        return store.workflow(workflow_id)

    @app.put("/api/workflows/{workflow_id}")
    def update_workflow(workflow_id: str, body: WorkflowInput):
        existing = store.workflow(workflow_id)
        workflow = Workflow(**body.model_dump(), id=existing.id, created_at=existing.created_at, updated_at=now())
        validate_workflow(workflow, ready=False)
        return store.save_workflow(workflow)

    @app.delete("/api/workflows/{workflow_id}", status_code=204)
    def delete_workflow(workflow_id: str):
        store.delete_workflow(workflow_id)
        # Its schedules would only fail from now on.
        book.remove_workflow(workflow_id)
        return Response(status_code=204)

    @app.post("/api/workflows/{workflow_id}/duplicate", status_code=201)
    def duplicate(workflow_id: str):
        workflow = store.workflow(workflow_id)
        workflow.id, workflow.created_at, workflow.updated_at = uid(), now(), now()
        workflow.name = workflow.name[:112] + " (kopya)"
        return store.save_workflow(workflow)

    @app.get("/api/workflows/{workflow_id}/export")
    def export_workflow(workflow_id: str):
        workflow = store.workflow(workflow_id)
        data = workflow.model_dump(mode="json")
        # A flow without notes stays readable by Studios that do not know them.
        if not data["notes"]:
            del data["notes"]
        # The reference images go along, so image steps work on the computer that imports the file.
        images = template_bundle.pack(workflow.steps, template_folder())
        if images:
            data["templates"] = images
        return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="akis-{workflow.id[:8]}.json"'})

    # ----- Zamanlayıcı: flows that run by themselves while the Studio is open -----------------
    def schedule_view(item: Schedule) -> dict:
        times = upcoming(item, datetime.now()) if item.enabled else []
        return {**item.model_dump(), "summary": summary(item), "workflow_name": workflow_name(item.workflow_id),
                "upcoming": [due.isoformat(timespec="minutes") for due in times]}

    def usual_minutes() -> dict[str, int]:
        """workflow id → how long its real runs usually take (median of the last five), in whole minutes."""
        lengths: dict[str, list[float]] = {}
        for run in store.runs():
            if run.status != "succeeded" or run.dry_run or run.test_step_id or not run.finished_at:
                continue
            seen = lengths.setdefault(run.workflow_id, [])
            if len(seen) < 5:
                took = datetime.fromisoformat(run.finished_at) - datetime.fromisoformat(run.started_at)
                seen.append(took.total_seconds() / 60)
        return {key: max(1, math.ceil(sorted(values)[len(values) // 2])) for key, values in lengths.items()}

    def plan_view() -> list[dict]:
        moment = datetime.now().replace(second=0, microsecond=0)
        return forecast(book.schedules(), usual_minutes(), moment, moment + timedelta(hours=24))

    def conflict_warnings(body: ScheduleInput, editing: str | None) -> list[str]:
        """What the next 7 days look like with this schedule among the others (usual run lengths)."""
        draft = Schedule(**body.model_dump())
        if not draft.enabled:
            return []
        minutes = usual_minutes()
        others = [item for item in book.schedules() if item.id != editing]
        moment = datetime.now().replace(second=0, microsecond=0)
        end = moment + timedelta(days=7)
        both = forecast(others + [draft], minutes, moment, end)
        alone = forecast(others, minutes, moment, end)
        names = {item.id: workflow_name(item.workflow_id) or "Silinmiş akış" for item in others}
        names[draft.id] = workflow_name(draft.workflow_id) or "Bu akış"
        warnings = []
        length = minutes.get(draft.workflow_id)
        if length is None:
            warnings.append("Akışın süresi henüz bilinmiyor; çakışmalar 1 dakika varsayılarak hesaplandı. Akış "
                            "birkaç kez çalıştıktan sonra uyarılar daha doğru olur.")
        elif draft.kind == "interval" and length >= draft.every_minutes:
            warnings.append(f"Akış genelde {length} dk sürüyor; her {draft.every_minutes} dakikada bir çalıştırılırsa "
                            "turlar birbirini bekler. Aralığı akışın süresinden uzun seçin.")
        if length and draft.max_duration and length > draft.max_duration:
            warnings.append(f"Akış genelde {length} dk sürüyor; en uzun çalışma süresi {draft.max_duration} dk "
                            "olduğu için büyük olasılıkla yarıda durdurulur.")

        def blockers(item: dict) -> set[str]:
            due = datetime.fromisoformat(item["due"])
            return {names[other["schedule_id"]] for other in both
                    if other["status"] == "runs" and other["schedule_id"] != item["schedule_id"]
                    and datetime.fromisoformat(other["start"]) <= due
                    < datetime.fromisoformat(other["start"]) + timedelta(minutes=other["minutes"])}

        mine = [item for item in both if item["schedule_id"] == draft.id]
        late = [item for item in mine if item["status"] == "runs" and item["delay"]]
        skipped = [item for item in mine if item["status"] == "skipped"]
        if late or skipped:
            who = sorted(set().union(*(blockers(item) for item in late + skipped)))
            parts = []
            if late:
                parts.append(f"{len(late)} kez başka akışların bitmesini bekleyecek "
                             f"(en fazla {max(item['delay'] for item in late)} dk)")
            if skipped:
                parts.append(f"{len(skipped)} kez {draft.max_delay} dakikadan fazla bekleyeceği için atlanacak")
            warnings.append("Önümüzdeki 7 günde bu zamanlama " + " ve ".join(parts) + "."
                            + (f" Çakıştığı akışlar: {', '.join(who)}." if who else ""))
        for other in others:
            def count(entries: list[dict], status: str, key: str = other.id) -> int:
                return sum(1 for item in entries if item["schedule_id"] == key
                           and (item["status"] == "skipped" if status == "skipped"
                                else item["status"] == "runs" and item["delay"]))
            delayed = count(both, "late") - count(alone, "late")
            dropped = count(both, "skipped") - count(alone, "skipped")
            if delayed > 0 or dropped > 0:
                effect = " ve ".join(text for text in (f"{delayed} kez gecikecek" if delayed > 0 else "",
                                                       f"{dropped} kez atlanacak" if dropped > 0 else "") if text)
                warnings.append(f"«{names[other.id]}» bu zamanlama yüzünden önümüzdeki 7 günde {effect}.")
        return warnings

    @app.get("/api/schedules")
    def list_schedules():
        return {"settings": book.settings().model_dump(), "schedules": [schedule_view(item) for item in book.schedules()],
                "pending": scheduler.pending(), "autostart": autostart.status(), "plan": plan_view(),
                "usual_minutes": usual_minutes()}

    @app.post("/api/schedules/preview")
    def preview_schedule(body: ScheduleInput, editing: str | None = None):
        return {"summary": summary(body),
                "upcoming": [due.isoformat(timespec="minutes") for due in upcoming(body, datetime.now())],
                "warnings": conflict_warnings(body, editing)}

    def check_schedule(body: ScheduleInput) -> None:
        if workflow_name(body.workflow_id) is None:
            raise HTTPException(status_code=404, detail="Zamanlanacak akış bulunamadı.")
        if body.enabled and next_occurrence(body, datetime.now()) is None:
            raise HTTPException(status_code=422, detail="Seçilen tarih ve saat geçmişte kaldı.")

    @app.post("/api/schedules", status_code=201)
    def create_schedule(body: ScheduleInput):
        check_schedule(body)
        try:
            schedule = book.add(planned(Schedule(**body.model_dump()), datetime.now()))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        scheduler.poke()
        return schedule_view(schedule)

    @app.put("/api/schedules/{schedule_id}")
    def update_schedule(schedule_id: str, body: ScheduleInput):
        check_schedule(body)
        changed = book.change(schedule_id, lambda item: planned(item.model_copy(update=body.model_dump()),
                                                                datetime.now()))
        if changed is None:
            raise HTTPException(status_code=404, detail="Zamanlama bulunamadı.")
        scheduler.poke()
        return schedule_view(changed)

    @app.delete("/api/schedules/{schedule_id}", status_code=204)
    def delete_schedule(schedule_id: str):
        if not book.remove(schedule_id):
            raise HTTPException(status_code=404, detail="Zamanlama bulunamadı.")
        return Response(status_code=204)

    @app.put("/api/schedule-settings")
    def update_schedule_settings(body: ScheduleSettings):
        return book.set_settings(body).model_dump()

    @app.get("/api/schedules/pending")
    def schedule_pending():
        return {"pending": scheduler.pending()}

    @app.post("/api/schedules/pending/{choice}")
    def answer_pending(choice: str):
        # The countdown before a scheduled run: İptal or Şimdi başlat.
        if choice not in {"cancel", "start"}:
            raise HTTPException(status_code=404, detail="Geçersiz seçim.")
        if not scheduler.answer(choice):
            raise HTTPException(status_code=409, detail="Başlamayı bekleyen zamanlanmış bir akış yok.")
        return {"pending": scheduler.pending()}

    # ----- Kayıtlı şifreler: names here, values only in the system password store --------------------
    vault = Vault(settings.data_dir)

    def vault_view() -> dict:
        return {"names": vault.names(), "supported": platform.system() in {"Darwin", "Windows"}}

    @app.get("/api/secrets")
    def list_secrets():
        return vault_view()

    @app.put("/api/secrets/{name}")
    def save_secret(name: str, body: SecretRequest):
        try:
            vault.set(name, body.value)
        except VaultError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return vault_view()

    @app.delete("/api/secrets/{name}")
    def delete_secret(name: str):
        try:
            removed = vault.delete(name)
        except VaultError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not removed:
            raise HTTPException(status_code=404, detail="Kayıtlı şifre bulunamadı.")
        return vault_view()

    @app.get("/api/autostart")
    def autostart_status():
        return autostart.status()

    @app.put("/api/autostart")
    def set_autostart(body: AutostartRequest):
        try:
            return autostart.set_enabled(body.enabled)
        except (RuntimeError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc) or "Başlangıç ayarı değiştirilemedi.") from exc

    @app.post("/api/workflows/{workflow_id}/run", status_code=202)
    def start_run(workflow_id: str, body: RunRequest):
        try:
            return manager.start(store.workflow(workflow_id), dry_run=body.dry_run)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/workflows/{workflow_id}/steps/{step_id}/test-plan")
    def step_test_plan(workflow_id: str, step_id: str):
        """What the test obtains by itself from earlier steps, and what the user has to enter."""
        from .engine import step_test_plan

        plan = step_test_plan(store.workflow(workflow_id), step_id)
        return {"prepare": [{"variable": entry["variable"], "kind": entry["kind"], "title": entry["title"],
                             "action": entry["step"].action} for entry in plan["prepare"]],
                "manual": plan["manual"], "manual_details": plan["manual_details"],
                "locatable": plan["locatable"], "external": plan["external"],
                "in_loop": plan["in_loop"]}

    @app.post("/api/workflows/{workflow_id}/steps/{step_id}/test", status_code=202)
    def test_step(workflow_id: str, step_id: str, body: StepTestRequest):
        try:
            return manager.start_step(store.workflow(workflow_id), step_id, body.variables, dry_run=body.dry_run,
                                      locate=body.locate)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/runs")
    def list_runs():
        return store.runs()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return store.run(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        return manager.cancel(run_id)

    @app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
    def download_artifact(run_id: str, artifact_id: str):
        run = store.run(run_id)
        artifact = next((a for a in run.artifacts if a.id == artifact_id), None)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Çıktı bulunamadı.")
        suffix = Path(artifact.name).suffix.lower()
        path = store.root / "artifacts" / run.id / f"{artifact.id}{suffix}"
        if suffix not in ARTIFACT_TYPES or not path.is_file():
            raise HTTPException(status_code=404, detail="Çıktı dosyası bulunamadı.")
        return FileResponse(path, media_type=ARTIFACT_TYPES[suffix], filename=artifact.name)

    @app.get("/api/settings")
    def get_settings():
        return settings.public()

    @app.put("/api/settings")
    def update_settings(body: dict = Body(...)):
        try:
            return settings.update(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/connections")
    def list_connections():
        return connections.list()

    @app.post("/api/connections", status_code=201)
    def create_connection(body: dict = Body(...)):
        try:
            return connections.create(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/api/connections/{connection_id}")
    def update_connection(connection_id: str, body: dict = Body(...)):
        try:
            return connections.update(connection_id, body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/connections/{connection_id}", status_code=204)
    def delete_connection(connection_id: str):
        connections.delete(connection_id)
        return Response(status_code=204)

    @app.post("/api/connections/apps-script-code")
    def connection_script_code(body: dict = Body(default={})):
        """Script for a spreadsheet. A new profile gets a fresh token; an existing one keeps its own."""
        from .integrations.apps_script import new_token, script_code

        connection_id = body.get("id")
        if connection_id:
            token = connections.get(connection_id)["config"].get("script_token")
            if body.get("renew") is True or not token:
                token = new_token()
                connections.update(connection_id, {"config": {"script_token": token}})
        else:
            token = new_token()
        return {"code": script_code(token), "token": token}

    @app.post("/api/connections/test")
    def test_connection(body: dict = Body(...)):
        from .integrations.apps_script import AppsScriptSheets
        from .integrations.sheets import normalize_spreadsheet_id

        kind = body.get("type")
        stored = connections.get(body["id"]) if body.get("id") else {"config": {}}
        try:
            config = connections._clean(kind, body.get("config") or {}, stored["config"]) if kind in {
                "google_sheets", "database"} else None
            if config is None:
                raise ValueError("Bağlantı türü geçersiz.")
            spreadsheet = body.get("spreadsheet") or ""
            if kind == "database":
                from .database.query import QueryDatabase, describe

                if not connections.ready({"type": "database", "config": config}):
                    raise ValueError("Sunucu ve kullanıcı adını (SQLite için dosyayı) girin.")
                try:
                    with QueryDatabase(config, timeout_seconds=15) as database:
                        database.ping()
                except (WorkflowError, ValueError):
                    raise
                except Exception as exc:
                    raise ValueError(describe(exc)) from exc
                return {"ok": True, "message": "Veritabanına bağlanıldı."}
            if config["method"] == "apps_script":
                client = AppsScriptSheets(config["script_url"], config["script_token"],
                                          normalize_spreadsheet_id(spreadsheet) if spreadsheet else "unused",
                                          body.get("sheet") or "Sayfa1", timeout=30)
                name = client.ping().get("spreadsheet")
                if spreadsheet:
                    client.get_range("A1")
                return {"ok": True, "message": f"Bağlantı çalışıyor{f': {name}' if name else ''}."}
            path = Path(config["credentials_path"]).expanduser()
            email = json.loads(path.read_text(encoding="utf-8")).get("client_email") if path.is_file() else None
            if not email:
                raise ValueError("Servis hesabı JSON dosyası bulunamadı veya geçersiz.")
            return {"ok": True, "message": f"Anahtar dosyası geçerli. Tablonuzu {email} ile Düzenleyen olarak "
                                           "paylaşın."}
        except (WorkflowError, ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Bağlantı kurulamadı. Adresi, kullanıcıyı ve ağ erişimini "
                                                        "kontrol edin.") from exc

    static = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static, html=True), name="studio")
    return app
