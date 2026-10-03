"""A real self-closing message box on Windows: nobody clicks it, it answers timeout."""

import platform
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Windows message box")


def test_the_message_box_closes_itself_when_its_time_is_up():
    from rpa_orkestrai.actions.dialogs import message

    result = {}

    def show():
        result["answer"] = message(None, {"title": "RpaOrkestrAI test", "text": "Bu kutu kendiliğinden kapanır.",
                                          "buttons": "ok_cancel", "timeout": 1})

    started = time.monotonic()
    worker = threading.Thread(target=show, daemon=True)
    worker.start()
    worker.join(60)
    assert not worker.is_alive(), "Mesaj kutusu süresi dolduğu hâlde kapanmadı."
    assert result["answer"] == "timeout"
    assert time.monotonic() - started >= 0.9
