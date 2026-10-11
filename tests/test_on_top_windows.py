"""Always-on-top is changed on the WinForms window's own thread, from any thread, without hanging."""
import platform
import threading
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="WinForms window thread")


def test_on_top_from_worker_and_timer_threads_runs_on_the_form_thread():
    pytest.importorskip("clr")
    import clr

    clr.AddReference("System.Windows.Forms")
    import System.Windows.Forms as WinForms
    from System import Func, Type
    from System.Threading import ApartmentState, Thread, ThreadStart

    from rpa_orkestrai.native import set_on_top

    ready, state = threading.Event(), {}

    def run():
        form = WinForms.Form()
        form.Text = "RpaOrkestrAI üstte testi"
        state["form"], state["thread"] = form, threading.get_ident()
        form.Shown += lambda *args: ready.set()
        WinForms.Application.Run(form)

    ui = Thread(ThreadStart(run))
    ui.SetApartmentState(ApartmentState.STA)
    ui.Start()
    assert ready.wait(20), "WinForms window did not open"
    form = state["form"]
    window = SimpleNamespace(native=form)
    seen = []

    def read():
        seen.append((form.TopMost, threading.get_ident()))

    try:
        for value in (True, False, True):
            worker = threading.Thread(target=set_on_top, args=(window, value))
            worker.start()
            worker.join(10)
            assert not worker.is_alive(), "set_on_top hung"
            form.Invoke(Func[Type](read))
            assert seen[-1] == (value, state["thread"])
        # The countdown's timer thread releases it the same way.
        timer = threading.Timer(0.05, set_on_top, args=(window, False))
        timer.start()
        timer.join(10)
        form.Invoke(Func[Type](read))
        assert seen[-1][0] is False
    finally:
        form.Invoke(Func[Type](form.Close))
        ui.Join(10000)
