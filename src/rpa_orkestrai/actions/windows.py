"""Window management beyond input: focus, size, close, wait and read field values."""

from __future__ import annotations

from ..desktop.windows import WindowError, found_window
from ..errors import WorkflowError
from . import handler
from .common import choice, integer, number


def _window(p):
    try:
        return found_window(p.get("window"))
    except WindowError as exc:
        raise WorkflowError(str(exc)) from exc


@handler("window.activate")
def activate(ctx, p):
    return ctx.windows().activate(_window(p))


@handler("window.state")
def state(ctx, p):
    ctx.windows().set_state(_window(p), choice(p.get("state"), "Pencere işlemi", {"maximize", "minimize", "restore"}))
    ctx.wait(0.3)


@handler("window.move")
def move(ctx, p):
    values = [integer(p.get(key), label, -10_000, 20_000) for key, label in
              (("x", "X"), ("y", "Y"), ("width", "Genişlik"), ("height", "Yükseklik"))]
    return ctx.windows().move_resize(_window(p), *values)


@handler("window.close")
def close(ctx, p):
    ctx.windows().close(_window(p))


@handler("window.wait_close")
def wait_close(ctx, p):
    ctx.windows().wait_closed(_window(p), number(p.get("timeout", 30), "Bekleme süresi", 0, 3600))


@handler("window.read_field")
def read_field(ctx, p):
    try:
        return ctx.windows().read_field(_window(p), ctx.desktop(), **ctx.window_target(p))
    except WindowError:
        raise
    except ImportError as exc:
        raise WorkflowError("Pano erişimi için masaüstü otomasyon paketleri gerekir.") from exc
