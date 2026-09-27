import pytest


class LicensedForTests:
    """Studio tests exercise the local API; the license gate has its own tests."""

    def __init__(self, *args, **kwargs):
        pass

    def allowed(self):
        return True

    def status(self):
        return {"state": "valid", "message": "", "online": True, "remembered": True,
                "license": {"user": "test", "full_name": "Test", "company": "Test",
                            "ends_on": None, "valid_until": None}}

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture(autouse=True)
def licensed_studio(request, monkeypatch):
    if "real_license" not in request.keywords:
        monkeypatch.setattr("rpa_orkestrai.app.LicenseService", LicensedForTests)
