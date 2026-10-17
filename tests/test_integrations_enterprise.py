"""API, gelen e-posta, FTP ve mesajlaşma bağlantıları: ağsız sahteler veya bu bilgisayardaki sunucuyla."""

import base64
import json
import threading
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from rpa_orkestrai.connections import Connections
from rpa_orkestrai.errors import WorkflowError


@pytest.fixture
def server():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            length = int(self.headers.get("Content-Length") or 0)
            seen.append({"method": self.command, "path": self.path, "headers": dict(self.headers),
                         "body": self.rfile.read(length).decode() if length else ""})
            if self.path.startswith("/yonlen"):
                port = self.server.server_address[1]
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{port}/disarida" if self.path == "/yonlen-dis" else "/hedef")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps({"ok": True, "path": self.path}).encode()
            self.send_response(401 if self.path.startswith("/kapali") else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _answer

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield SimpleNamespace(url=f"http://127.0.0.1:{httpd.server_address[1]}", seen=seen)
    httpd.shutdown()


def api_profile(tmp_path, base, **config):
    connections = Connections(tmp_path)
    created = connections.create({"name": "ERP API", "type": "api", "config": {"base_url": base, **config}})
    return connections, connections.get(created["id"])


def run_request(connections, params):
    from rpa_orkestrai.actions.web import request

    ctx = SimpleNamespace(connections=connections)
    return request(ctx, {"method": "GET", "timeout": 5, "fail_on_error": True, **params})


@pytest.mark.parametrize("auth,config,expect", [
    ("bearer", {"token": "gizli-token-123"}, lambda h, p: h["Authorization"] == "Bearer gizli-token-123"),
    ("basic", {"user": "rpa", "password": "parola-9"},
     lambda h, p: h["Authorization"] == "Basic " + base64.b64encode(b"rpa:parola-9").decode()),
    ("api_key", {"api_key": "anahtar-7", "key_name": "X-Firma-Key"}, lambda h, p: h["X-Firma-Key"] == "anahtar-7"),
    ("api_key", {"api_key": "anahtar-7", "key_name": "key", "key_in": "query"}, lambda h, p: "key=anahtar-7" in p),
])
def test_api_connection_adds_credentials_to_a_path_on_its_own_server(tmp_path, server, auth, config, expect):
    connections, profile = api_profile(tmp_path, server.url + "/api/v2", auth=auth, headers={"Accept": "application/json"},
                                       **config)
    result = run_request(connections, {"connection": profile["id"], "url": "/siparisler/42?durum=acik"})
    assert result["status"] == 200 and result["body"]["path"].startswith("/api/v2/siparisler/42?durum=acik")
    request = server.seen[-1]
    assert expect(request["headers"], request["path"]) and request["headers"]["Accept"] == "application/json"
    public = json.dumps(connections.list()[0])
    secrets = [config[key] for key in ("token", "password", "api_key") if key in config]
    assert secrets and all(value not in public and value in connections.secrets() for value in secrets)


def test_credentials_are_never_sent_to_another_server_and_untouched_default_means_base(tmp_path, server):
    connections, profile = api_profile(tmp_path, server.url, auth="bearer", token="gizli-token-123")
    with pytest.raises(WorkflowError, match="sunucusunda değil"):
        run_request(connections, {"connection": profile["id"], "url": "https://saldirgan.example/topla"})
    assert run_request(connections, {"connection": profile["id"], "url": "https://"})["body"]["path"] == "/"
    with pytest.raises(WorkflowError, match="401"):
        run_request(connections, {"connection": profile["id"], "url": "/kapali"})
    # Without a connection the step behaves as before and adds nothing.
    assert run_request(connections, {"url": server.url + "/acik"})["status"] == 200
    assert "Authorization" not in server.seen[-1]["headers"]


def test_credentials_do_not_follow_a_redirect_to_another_server(tmp_path, server):
    connections, profile = api_profile(tmp_path, server.url, auth="bearer", token="gizli-token-123")
    assert run_request(connections, {"connection": profile["id"], "url": "/yonlen-ic"})["body"]["path"] == "/hedef"
    assert server.seen[-1]["headers"]["Authorization"] == "Bearer gizli-token-123"
    with pytest.raises(WorkflowError, match="başka bir sunucuya yönlendirdi"):
        run_request(connections, {"connection": profile["id"], "url": "/yonlen-dis"})
    assert all(item["path"] != "/disarida" for item in server.seen)


def test_api_connection_validation_and_secret_reuse(tmp_path):
    connections = Connections(tmp_path)
    for config, message in [({"base_url": "ftp://x"}, "https://"), ({"base_url": "https://u:p@x.com"}, "kullanıcı adı"),
                            ({"base_url": "https://x.com", "headers": {"Authorization": "Bearer a"}}, "kimlik doğrulama"),
                            ({"base_url": "https://x.com", "auth": "oauth2", "token_url": "http://x.com/t"}, "https://"),
                            ({"base_url": "https://x.com", "test_path": "https://y.com"}, "yol")]:
        with pytest.raises(ValueError, match=message):
            connections.create({"name": "API", "type": "api", "config": config})
    created = connections.create({"name": "API", "type": "api", "config": {
        "base_url": "https://erp.firma.com/api/", "auth": "bearer", "token": "t-1"}})
    assert created["base_url"] == "https://erp.firma.com/api" and created["ready"] and created["has_token"]
    same = connections.update(created["id"], {"config": {"base_url": "https://erp.firma.com/v2"}})
    assert same["has_token"]
    moved = connections.update(created["id"], {"config": {"base_url": "https://baska.com"}})
    assert not moved["has_token"] and not moved["ready"]


def test_oauth_client_credentials_token_is_cached(monkeypatch):
    from rpa_orkestrai.integrations import api

    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps({"access_token": "erisim-1", "expires_in": 3600}).encode()

    monkeypatch.setattr(api, "opener", lambda: SimpleNamespace(open=lambda request, timeout: calls.append(request) or Response()))
    profile = {"id": "p" * 32, "config": {"base_url": "https://erp.firma.com", "auth": "oauth2",
                                         "token_url": "https://kimlik.firma.com/token", "client_id": "rpa",
                                         "client_secret": "sir-1", "scope": "erp.write"}}
    for _ in range(2):
        url, headers = api.authorize(profile, "/v1/x", {}, 5)
        assert url == "https://erp.firma.com/v1/x" and headers["Authorization"] == "Bearer erisim-1"
    assert len(calls) == 1 and b"grant_type=client_credentials" in calls[0].data and b"scope=erp.write" in calls[0].data


def test_imap_folder_names_html_and_message_summary(tmp_path):
    from rpa_orkestrai.integrations.imap import folder_name, html_text, summary

    assert folder_name("INBOX") == '"INBOX"'
    assert folder_name("İşlenenler") == '"&ATABXw-lenenler"'
    assert folder_name("A&B") == '"A&-B"'
    assert html_text("<html><style>x{}</style><p>Merhaba</p><p>Fatura <b>12</b></p></html>") == "Merhaba\nFatura 12"
    message = EmailMessage()
    message["From"] = "Tedarikçi A.Ş. <fatura@tedarikci.com>"
    message["To"] = "rpa@firma.com"
    message["Subject"] = "Fatura F-12"
    message["Date"] = "Fri, 16 Oct 2026 10:00:00 +0300"
    message.set_content("Ekte fatura var.")
    message.add_attachment(b"%PDF-1", maintype="application", subtype="pdf", filename="../fatura F-12.pdf")
    (tmp_path / "fatura F-12.pdf").write_bytes(b"eski")
    result = summary(message, 7, attachment_folder=tmp_path)
    assert result["from"] == "fatura@tedarikci.com" and result["from_name"] == "Tedarikçi A.Ş."
    assert result["subject"] == "Fatura F-12" and result["text"].strip() == "Ekte fatura var."
    attachment = result["attachments"][0]
    assert attachment["name"] == "../fatura F-12.pdf" and attachment["path"] == str(tmp_path / "fatura F-12 (2).pdf")
    assert (tmp_path / "fatura F-12 (2).pdf").read_bytes() == b"%PDF-1" and (tmp_path / "fatura F-12.pdf").read_bytes() == b"eski"


class FakeIMAP:
    def __init__(self, messages):
        self.messages, self.stored, self.readonly = messages, [], None

    def select(self, folder, readonly=True):
        self.readonly = readonly
        return ("OK", [b"2"]) if folder == '"INBOX"' else ("NO", [b""])

    def response(self, name):
        return name, [b"55"]

    def uid(self, command, *args):
        if command == "SEARCH":
            return "OK", [b" ".join(str(uid).encode() for uid in self.messages)]
        if command == "STORE":
            self.stored.append(args)
            return "OK", []
        uid, what = int(args[0]), args[1]
        message = self.messages[uid]
        if "RFC822.SIZE" in what:
            return "OK", [f"{uid} (RFC822.SIZE 100)".encode()]
        return "OK", [(f"{uid} (BODY[] {{1}}".encode(), message.as_bytes()), b")"]

    def logout(self):
        pass


def message_with(subject, sender):
    message = EmailMessage()
    message["From"], message["Subject"] = sender, subject
    message.set_content(f"{subject} gövdesi")
    return message


def test_mail_read_step_filters_reads_without_marking_and_marks_only_when_asked(tmp_path, monkeypatch):
    from rpa_orkestrai.actions import mail
    from rpa_orkestrai.integrations import imap

    fake = FakeIMAP({3: message_with("Fatura F-1", "a@tedarikci.com"), 4: message_with("Toplantı", "b@firma.com"),
                     9: message_with("Fatura F-2", "a@tedarikci.com")})
    monkeypatch.setattr(imap, "connect", lambda config, timeout: fake)
    connections = Connections(tmp_path)
    created = connections.create({"name": "Faturalar", "type": "imap", "config": {
        "host": "imap.firma.com", "user": "rpa@firma.com", "password": "uygulama-sifresi"}})
    logs = []
    ctx = SimpleNamespace(connections=connections, log=lambda message, **kwargs: logs.append(message))
    result = mail.read(ctx, {"connection": created["id"], "subject_contains": "fatura", "max_messages": 5})
    assert [item["subject"] for item in result] == ["Fatura F-1", "Fatura F-2"] and fake.readonly is True
    assert fake.stored == [] and result[0]["text"].strip() == "Fatura F-1 gövdesi"
    result = mail.read(ctx, {"connection": created["id"], "max_messages": 1, "mark_read": True})
    assert len(result) == 1 and fake.readonly is False and fake.stored[-1][0] == "3"
    assert "okundu olarak işaretlendi" in logs[-1]


def test_ftp_paths_cannot_leave_the_start_folder_and_transfers_use_the_connection(tmp_path, monkeypatch):
    from rpa_orkestrai.actions import transfer
    from rpa_orkestrai.integrations import ftp

    with pytest.raises(WorkflowError, match="dışına"):
        ftp.remote("../gizli/x.txt")
    assert ftp.remote("/gelen/./fatura.xml") == "gelen/fatura.xml"
    files = {"gelen/fatura.xml": b"<f/>"}

    class FakeFTP:
        def mlsd(self, folder):
            return [(name.split("/")[-1], {"type": "file", "size": str(len(data))}) for name, data in files.items()
                    if name.startswith(folder.strip("./") or "")]

        def retrbinary(self, command, write):
            write(files[command.split(" ", 1)[1]])

        def storbinary(self, command, handle):
            files[command.split(" ", 1)[1]] = handle.read()

        def quit(self):
            pass

    monkeypatch.setattr(ftp, "connect", lambda config, timeout: FakeFTP())
    connections = Connections(tmp_path)
    created = connections.create({"name": "Banka", "type": "ftp", "config": {"host": "ftp.banka.com", "user": "rpa",
                                                                             "password": "p-1"}})
    ctx = SimpleNamespace(connections=connections, log=lambda *args, **kwargs: None)
    listed = transfer.ftp_transfer(ctx, {"connection": created["id"], "operation": "list", "remote_path": "gelen"})
    assert listed["items"][0]["name"] == "fatura.xml"
    target = tmp_path / "indir" / "fatura.xml"
    transfer.ftp_transfer(ctx, {"connection": created["id"], "operation": "download", "remote_path": "gelen/fatura.xml",
                                "local_path": str(target)})
    assert target.read_bytes() == b"<f/>" and not list(target.parent.glob("*.part"))
    with pytest.raises(WorkflowError, match="zaten var"):
        transfer.ftp_transfer(ctx, {"connection": created["id"], "operation": "download",
                                    "remote_path": "gelen/fatura.xml", "local_path": str(target)})
    upload = tmp_path / "giden.xml"
    upload.write_bytes(b"<g/>")
    transfer.ftp_transfer(ctx, {"connection": created["id"], "operation": "upload", "remote_path": "giden.xml",
                                "local_path": str(upload)})
    assert files["giden.xml"] == b"<g/>"


@pytest.mark.parametrize("service,check", [
    ("teams", lambda body: body["attachments"][0]["content"]["body"][1]["text"] == "Fatura işlendi"),
    ("slack", lambda body: body["text"] == "*Bildirim*\nFatura işlendi"),
    ("discord", lambda body: body["content"] == "Bildirim\nFatura işlendi"),
    ("generic", lambda body: body == {"title": "Bildirim", "text": "Fatura işlendi"}),
])
def test_messages_use_each_services_format(server, service, check):
    from rpa_orkestrai.actions.transfer import post_message

    assert post_message({"service": service, "url": server.url + "/hook"}, "Bildirim", "Fatura işlendi")["status"] == 200
    assert check(json.loads(server.seen[-1]["body"]))


def test_webhook_and_imap_connections_validate_their_fields(tmp_path):
    connections = Connections(tmp_path)
    with pytest.raises(ValueError, match="https://"):
        connections.create({"name": "Kanal", "type": "webhook", "config": {"service": "slack", "url": "http://x.com"}})
    hook = connections.create({"name": "Kanal", "type": "webhook", "config": {"service": "teams",
                                                                              "url": "https://x.logic.azure.com/abc"}})
    assert hook["ready"] and hook["has_url"] and "logic.azure" not in json.dumps(hook)
    with pytest.raises(ValueError, match="tırnak"):
        connections.create({"name": "Posta", "type": "imap", "config": {"host": "x", "folder": 'IN"BOX'}})
    box = connections.create({"name": "Posta", "type": "imap", "config": {"host": "imap.x.com", "user": "a",
                                                                          "password": "p", "security": "ssl"}})
    assert box["port"] == "993" and box["folder"] == "INBOX" and box["ready"]
