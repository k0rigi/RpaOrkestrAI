import threading
import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.desktop.pick_jobs import PickJobs
from rpa_orkestrai.desktop.targets import CaptureStore
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo
from rpa_orkestrai.engine import RunManager
from rpa_orkestrai.models import Step, Workflow
from rpa_orkestrai.storage import Store


def selection():
    picture = Image.new('RGB', (200, 120), 'white')
    ImageDraw.Draw(picture).rectangle((30, 30, 45, 45), fill='black')
    return {'window': WindowInfo(1, 2, 'ERP', 'Test ERP', 20, 30, 200, 120),
            'image': picture, 'x': 70, 'y': 80}


def wait_for(check):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.005)
    raise AssertionError('Picker worker did not finish')


@pytest.fixture
def setup(tmp_path):
    manager = RunManager(Settings(tmp_path / 'data', dotenv=False), Store(tmp_path / 'data'))
    captures = CaptureStore()
    picker = Mock()
    picker.pick.return_value = selection()
    jobs = PickJobs(manager, captures, picker_factory=lambda: picker, available=lambda: True)
    yield manager, captures, picker, jobs
    jobs.close()
    manager.close()


def test_session_reserves_desktop_before_worker_and_cancellation_releases_it(setup):
    manager, _, picker, jobs = setup
    entered = threading.Event()

    def picking(selector, mode, delay, *, cancel, on_state):
        on_state({'status': 'countdown', 'remaining': 5})
        entered.set()
        assert cancel.wait(2)
        raise InterruptedError()

    picker.pick.side_effect = picking
    job = jobs.start({'title': 'Test ERP'}, 'coordinates', 5)
    assert entered.wait(1)
    assert jobs.status(job['id'])['countdown'] == 5
    flow = Workflow(steps=[Step(action='core.wait', params={'seconds': 0})])
    with pytest.raises(RuntimeError, match='hedef seçimi'):
        manager.start(flow)
    with pytest.raises(RuntimeError):
        jobs.start({'title': 'Test ERP'}, 'coordinates', 5)
    with pytest.raises(RuntimeError):
        with manager.desktop_setup():
            raise AssertionError('Capture must remain blocked')
    jobs.cancel(job['id'])
    wait_for(lambda: manager._setup_cancel is None)
    with pytest.raises(KeyError):
        jobs.status(job['id'])
    manager.start(flow)
    wait_for(lambda: manager._active is None)


def test_completed_selection_requires_explicit_crop_and_saved_template_survives_delete(setup, tmp_path):
    manager, captures, picker, jobs = setup
    chosen = selection()
    chosen.update(crop={'x': 25, 'y': 25, 'width': 30, 'height': 30}, point={'x': 70, 'y': 80})
    picker.pick.return_value = chosen
    job = jobs.start({'title': 'Test ERP'}, 'image', 3)
    wait_for(lambda: manager._setup_cancel is None)
    status = jobs.status(job['id'])
    assert status['status'] == 'completed'
    assert status['result']['rectangle'] == chosen['crop']
    assert status['result']['point'] == chosen['point']
    assert not (tmp_path / 'templates').exists()
    saved = captures.crop(status['result']['capture']['id'], **chosen['crop'], folder=tmp_path / 'templates')
    jobs.cancel(job['id'])
    assert (tmp_path / 'templates' / saved['template']).exists()
    with pytest.raises(WindowError):
        captures.crop(status['result']['capture']['id'], **chosen['crop'], folder=tmp_path / 'templates')


def test_error_releases_reservation_and_does_not_return_raw_exception(setup):
    manager, _, picker, jobs = setup
    picker.pick.side_effect = ValueError('private driver details')
    job = jobs.start({'title': 'Test ERP'}, 'coordinates', 3)
    wait_for(lambda: manager._setup_cancel is None)
    status = jobs.status(job['id'])
    assert status['status'] == 'error'
    assert 'private' not in status['message']
    assert 'result' not in status


def test_unavailable_native_picker_never_reserves_desktop(setup):
    manager, _, picker, jobs = setup
    jobs.available = lambda: False
    with pytest.raises(WindowError, match='masaüstü'):
        jobs.start({'title': 'Test ERP'}, 'coordinates', 3)
    picker.pick.assert_not_called()
    assert manager._setup_cancel is None


def test_close_cancels_active_session_and_rejects_new_one(setup):
    manager, _, picker, jobs = setup
    entered = threading.Event()

    def picking(selector, mode, delay, *, cancel, on_state):
        entered.set()
        assert cancel.wait(2)
        raise InterruptedError()

    picker.pick.side_effect = picking
    jobs.start({'title': 'Test ERP'}, 'coordinates', 3)
    assert entered.wait(1)
    jobs.close()
    assert manager._setup_cancel is None
    with pytest.raises(RuntimeError):
        jobs.start({'title': 'Test ERP'}, 'coordinates', 3)


def test_picker_api_validates_origin_delay_and_result_contract(tmp_path):
    app = create_app(Settings(tmp_path / 'data', dotenv=False))
    jobs = app.state.picks
    jobs.available = lambda: True
    picker = Mock()
    picker.pick.return_value = selection()
    jobs.picker_factory = lambda: picker
    with TestClient(app) as client:
        assert client.get('/api/desktop/pick/capabilities').json() == {'native': True}
        payload = {'title': 'Test ERP', 'mode': 'coordinates', 'delay': 3}
        assert client.post('/api/desktop/pick', json=payload,
                           headers={'Origin': 'https://foreign.example'}).status_code == 403
        for delay in (True, 3.5, 4, 0, 30):
            assert client.post('/api/desktop/pick', json={**payload, 'delay': delay}).status_code == 422
        picker.pick.assert_not_called()
        response = client.post('/api/desktop/pick', json=payload)
        assert response.status_code == 202
        key = response.json()['id']
        wait_for(lambda: app.state.manager._setup_cancel is None)
        result = client.get('/api/desktop/pick/' + key).json()
        assert result['status'] == 'completed'
        assert result['result']['point'] == {'x': 70, 'y': 80}
        assert result['result']['capture']['image'].startswith('data:image/png;base64,')
        assert client.delete('/api/desktop/pick/' + key).status_code == 204
        assert client.get('/api/desktop/pick/' + key).status_code == 404
        assert client.delete('/api/desktop/pick/' + key).status_code == 204
        assert client.get('/api/runs').json() == []
