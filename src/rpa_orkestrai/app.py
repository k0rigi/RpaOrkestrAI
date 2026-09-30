"""Loopback-only HTTP interface shared by the browser and native desktop shell."""

from __future__ import annotations

import platform
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .catalog import ACTION_DEFINITIONS, library_catalog
from .config import Settings
from .engine import ARTIFACT_TYPES, RunManager, WorkflowError, validate_workflow
from .instance import identity
from .licensing import OPEN_PATHS, LicenseError, LicenseService, LicenseUnavailable
from .locking import WorkspaceLock
from .models import (
    DesktopPickRequest,
    FavoriteRequest,
    LicenseLoginRequest,
    PathRequest,
    PointerRequest,
    RecordRequest,
    RunRequest,
    StepTestRequest,
    TemplateCropRequest,
    WindowCheckRequest,
    Workflow,
    WorkflowInput,
    now,
    uid,
)
from .storage import Store


def create_app(settings: Settings | None = None, *, licensing: LicenseService | None = None) -> FastAPI:
    settings = settings or Settings()
    licensing = licensing or LicenseService(settings.data_dir)
    store = Store(settings.data_dir)
    manager = RunManager(settings, store)
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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with WorkspaceLock(settings.data_dir):
            store.recover_runs()
            licensing.start()
            try:
                yield
            finally:
                licensing.stop()
                records.close()
                picks.close()
                manager.close()

    app = FastAPI(title="RpaOrkestrAI Studio", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.store, app.state.manager, app.state.settings = store, manager, settings
    app.state.picks, app.state.licensing, app.state.records = picks, licensing, records
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
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Geçersiz istek uzunluğu."}, status_code=400)
        if content_length > 2_000_000:
            return JSONResponse({"detail": "İstek en fazla 2 MB olabilir."}, status_code=413)
        if request.method in {"POST", "PUT", "PATCH"}:
            received = bytearray()
            async for chunk in request.stream():
                received.extend(chunk)
                if len(received) > 2_000_000:
                    return JSONResponse({"detail": "İstek en fazla 2 MB olabilir."}, status_code=413)
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
                "favorites": store.favorites(), "updates": update_status()}

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

    @app.post("/api/desktop/templates", status_code=201)
    def save_template(body: TemplateCropRequest):
        from .desktop.windows import WindowError

        try:
            return captures.crop(**body.model_dump(), folder=Path(settings.get("template_dir")).expanduser().resolve())
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
    def import_workflow(body: Workflow | WorkflowInput):
        # Imported identity/timestamps are always replaced; import never starts a run.
        values = body.model_dump(exclude={"id", "created_at", "updated_at"})
        workflow = Workflow(**values)
        validate_workflow(workflow, ready=False)
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
        return Response(workflow.model_dump_json(indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="akis-{workflow.id[:8]}.json"'})

    @app.post("/api/workflows/{workflow_id}/run", status_code=202)
    def start_run(workflow_id: str, body: RunRequest):
        try:
            return manager.start(store.workflow(workflow_id), dry_run=body.dry_run)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/workflows/{workflow_id}/steps/{step_id}/test", status_code=202)
    def test_step(workflow_id: str, step_id: str, body: StepTestRequest):
        try:
            return manager.start_step(store.workflow(workflow_id), step_id, body.variables, dry_run=body.dry_run)
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

    @app.post("/api/settings/apps-script/code")
    def apps_script_code(body: dict = Body(default={})):
        """Script to paste into the spreadsheet; a new token is created on request or when missing."""
        from .integrations.apps_script import new_token, script_code

        token = settings.get("sheets_script_token")
        if body.get("renew") is True or not token:
            token = new_token()
            settings.update({"sheets_script_token": token})
        return {"code": script_code(token), "settings": settings.public()}

    @app.post("/api/settings/apps-script/test")
    def apps_script_test(body: dict = Body(default={})):
        from .integrations.apps_script import AppsScriptSheets, validate_url
        from .integrations.sheets import normalize_spreadsheet_id

        try:
            url = validate_url(body.get("url") or settings.get("sheets_script_url"))
            spreadsheet = body.get("spreadsheet") or ""
            spreadsheet = normalize_spreadsheet_id(spreadsheet) if spreadsheet else "unused"
            client = AppsScriptSheets(url, settings.get("sheets_script_token"), spreadsheet,
                                      body.get("sheet") or "Sayfa1", timeout=30)
            result = client.ping()
            if body.get("spreadsheet"):
                client.get_range("A1")
        except (WorkflowError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        name = result.get("spreadsheet")
        return {"ok": True, "message": f"Bağlantı çalışıyor{f': {name}' if name else ''}."}

    @app.put("/api/settings")
    def update_settings(body: dict = Body(...)):
        try:
            return settings.update(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    static = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static, html=True), name="studio")
    return app
