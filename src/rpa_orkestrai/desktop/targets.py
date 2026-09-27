"""Short-lived window captures; persist only the reference crop chosen by the user."""

from __future__ import annotations

import base64
import io
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from uuid import uuid4

from .windows import WindowError


class CaptureStore:
    def __init__(self, *, ttl: float = 300):
        self.ttl = ttl
        self._captures: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._lock = threading.RLock()

    def _expire(self):
        now = time.monotonic()
        for key, (created, _) in list(self._captures.items()):
            if now - created > self.ttl:
                del self._captures[key]

    def add(self, window, image) -> dict:
        if image.size != (window.width, window.height) or image.width * image.height > 16_000_000:
            raise WindowError("Pencere görüntüsü çok büyük veya boyutu değişti. Pencereyi küçültüp tekrar seçin.")
        data = io.BytesIO()
        image.convert("RGB").save(data, format="PNG")
        payload = data.getvalue()
        if len(payload) > 12_000_000:
            raise WindowError("Pencere görüntüsü çok büyük. Pencereyi küçültüp tekrar seçin.")
        capture_id = uuid4().hex
        with self._lock:
            self._expire()
            while len(self._captures) >= 3:
                self._captures.popitem(last=False)
            self._captures[capture_id] = (time.monotonic(), payload)
        return {"id": capture_id, "image": "data:image/png;base64," + base64.b64encode(payload).decode("ascii"),
                "width": image.width, "height": image.height, "window": window.result()}

    def discard(self, capture_id: str) -> None:
        with self._lock:
            self._captures.pop(capture_id, None)

    def crop(self, capture_id: str, x: int, y: int, width: int, height: int, folder: Path) -> dict:
        from PIL import Image, ImageStat

        if any(type(value) is not int for value in (x, y, width, height)):
            raise WindowError("Görsel seçimi tam sayı koordinatlar içermelidir.")
        with self._lock:
            self._expire()
            stored = self._captures.get(capture_id)
        if stored is None:
            raise WindowError("Ekran görüntüsünün süresi doldu. Ekrandan hedef seç ile yeniden görüntü alın.")
        with Image.open(io.BytesIO(stored[1])) as image:
            if (x < 0 or y < 0 or width < 8 or height < 8 or width * height > 2_000_000
                    or x + width > image.width or y + height > image.height):
                raise WindowError("Pencere içinde en az 8 × 8 boyutunda, küçük bir referans alanı seçin.")
            cropped = image.crop((x, y, x + width, y + height))
            if ImageStat.Stat(cropped.convert("L")).stddev[0] < 1:
                raise WindowError("Boş alan yerine FormID etiketi gibi ayırt edilebilir bir görsel seçin.")
            data = io.BytesIO()
            cropped.save(data, format="PNG")
        folder.mkdir(parents=True, exist_ok=True)
        name = f"capture-{uuid4().hex}.png"
        destination = folder / name
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(destination, flags, 0o600), "wb") as handle:
            handle.write(data.getvalue())
        self.discard(capture_id)
        return {"template": name, "width": width, "height": height}
