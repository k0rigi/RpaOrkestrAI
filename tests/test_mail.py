"""E-posta gönder: a real SMTP conversation with a local server; nothing is sent twice."""
import base64
import email
import email.policy
import socketserver
import threading
from types import SimpleNamespace

import pytest

from rpa_orkestrai.actions.mail import send
from rpa_orkestrai.connections import Connections
from rpa_orkestrai.errors import WorkflowError


class FakeSmtp(socketserver.StreamRequestHandler):
    """Just enough ESMTP: EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT."""

    def write(self, line):
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self):
        server = self.server
        self.write("220 test ESMTP")
        while True:
            line = self.rfile.readline().decode().rstrip("\r\n")
            if not line:
                return
            verb = line.split(" ", 1)[0].upper()
            server.commands.append(verb)
            if verb == "EHLO":
                self.write("250-test")
                self.write("250 AUTH PLAIN")
            elif verb == "AUTH":
                user, password = base64.b64decode(line.split()[2]).split(b"\0")[1:]
                ok = (user.decode(), password.decode()) == server.account
                self.write("235 ok" if ok else "535 bad credentials")
            elif verb == "MAIL":
                self.write("250 ok")
            elif verb == "RCPT":
                address = line.split(":", 1)[1].strip("<> ")
                if address in server.refuse:
                    self.write("550 no such user")
                else:
                    server.recipients.append(address)
                    self.write("250 ok")
            elif verb == "DATA":
                self.write("354 go")
                data = []
                while (chunk := self.rfile.readline()) != b".\r\n":
                    data.append(chunk)
                server.messages.append(b"".join(data))
                self.write("250 queued")
            elif verb == "QUIT":
                self.write("221 bye")
                return
            else:
                self.write("250 ok")


@pytest.fixture
def smtp():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeSmtp)
    server.daemon_threads = True
    server.commands, server.recipients, server.messages, server.refuse = [], [], [], set()
    server.account = ("rpa@firma.com", "gizli-sifre")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def context(tmp_path, smtp, **config):
    connections = Connections(tmp_path)
    connections.create({"type": "smtp", "name": "Bildirim", "config": {
        "host": "127.0.0.1", "port": str(smtp.server_address[1]), "security": "none",
        "user": "rpa@firma.com", "password": "gizli-sifre", "sender": "rpa@firma.com",
        "sender_name": "RPA Çağrı", **config}})
    logs = []
    return SimpleNamespace(connections=connections, log=lambda message, **kw: logs.append(message)), logs


def test_sends_once_with_turkish_subject_body_and_attachment(tmp_path, smtp):
    attachment = tmp_path / "iade özeti.csv"
    attachment.write_text("no;tutar\n1;10,50", encoding="utf-8")
    ctx, logs = context(tmp_path, smtp)
    result = send(ctx, {"to": "a@firma.com; b@firma.com", "cc": "c@firma.com", "bcc": "gizli@firma.com",
                        "subject": "Fatura 1069 işlendi", "body": "Merhaba,\nİşlem tamamlandı: ğüşıöç",
                        "attachments": str(attachment)})
    assert result["sent"] and result["to"] == ["a@firma.com", "b@firma.com", "c@firma.com", "gizli@firma.com"]
    assert smtp.commands.count("DATA") == 1 and "AUTH" in smtp.commands
    message = email.message_from_bytes(smtp.messages[0], policy=email.policy.default)
    assert message["Subject"] == "Fatura 1069 işlendi" and message["Cc"] == "c@firma.com"
    assert "Bcc" not in message  # blind copies are delivered but never listed
    assert message["From"].addresses[0].display_name == "RPA Çağrı"
    parts = list(message.iter_attachments())
    assert message.get_body().get_content().replace("\r\n", "\n").strip() == "Merhaba,\nİşlem tamamlandı: ğüşıöç"
    assert parts[0].get_filename() == "iade özeti.csv" and parts[0].get_content() in {
        "no;tutar\n1;10,50", b"no;tutar\n1;10,50"}


def test_refused_recipient_is_reported_and_others_delivered(tmp_path, smtp):
    smtp.refuse.add("yok@firma.com")
    ctx, logs = context(tmp_path, smtp)
    result = send(ctx, {"to": "a@firma.com, yok@firma.com", "subject": "Deneme"})
    assert result["to"] == ["a@firma.com"] and result["refused"] == ["yok@firma.com"]
    assert any("reddetti" in line for line in logs)


@pytest.mark.parametrize("params,match", [
    ({"to": "", "subject": "x"}, "en az bir"),
    ({"to": "a b@firma.com", "subject": "x"}, "geçerli"),
    ({"to": "a@firma.com", "subject": "x\nBcc: z@x.com"}, "satır sonu"),
    ({"to": "a@firma.com", "subject": "x", "attachments": "/yok/dosya.pdf"}, "bulunamadı"),
])
def test_invalid_mail_is_not_sent(tmp_path, smtp, params, match):
    ctx, _ = context(tmp_path, smtp)
    with pytest.raises(WorkflowError, match=match):
        send(ctx, params)
    assert smtp.messages == []


def test_wrong_password_explains_app_passwords_and_sends_nothing(tmp_path, smtp):
    ctx, _ = context(tmp_path, smtp, password="yanlis-sifre")
    with pytest.raises(WorkflowError, match="uygulama şifresi"):
        send(ctx, {"to": "a@firma.com", "subject": "x"})
    assert smtp.messages == [] and "MAIL" not in smtp.commands


def test_connection_keeps_password_private_and_requires_valid_sender(tmp_path):
    connections = Connections(tmp_path)
    profile = connections.create({"type": "smtp", "name": "Bildirim", "config": {
        "host": "smtp.firma.com", "security": "ssl", "user": "rpa@firma.com", "password": "gizli-sifre",
        "sender": "rpa@firma.com"}})
    assert profile["has_password"] and "password" not in profile and profile["port"] == "465" and profile["ready"]
    assert "gizli-sifre" in connections.secrets()
    # A blank password keeps the stored one; another account must type its own.
    updated = connections.update(profile["id"], {"config": {"host": "smtp.firma.com", "user": "rpa@firma.com",
                                                            "sender": "rpa@firma.com", "security": "ssl"}})
    assert updated["has_password"]
    moved = connections.update(profile["id"], {"config": {"host": "smtp.baska.com", "user": "rpa@firma.com",
                                                          "sender": "rpa@firma.com", "security": "ssl"}})
    assert not moved["has_password"]
    with pytest.raises(ValueError, match="Gönderen"):
        connections.create({"type": "smtp", "name": "Kötü", "config": {"host": "x", "sender": "adres"}})


@pytest.mark.parametrize("security,expected", [("starttls", ["SMTP", "starttls", "login", "send", "quit"]),
                                               ("ssl", ["SMTP_SSL", "login", "send", "quit"])])
def test_encrypted_connections_verify_certificates(tmp_path, monkeypatch, security, expected):
    import smtplib
    import ssl

    calls = []

    class Server:
        def __init__(self, host, port, timeout=None, context=None):
            calls.append("SMTP_SSL" if context else "SMTP")
            if context:
                assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname

        def starttls(self, context):
            assert context.verify_mode == ssl.CERT_REQUIRED
            calls.append("starttls")

        def login(self, user, password):
            calls.append("login")

        def send_message(self, message, to_addrs):
            calls.append("send")
            return {}

        def quit(self):
            calls.append("quit")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(smtplib, "SMTP", Server)
    monkeypatch.setattr(smtplib, "SMTP_SSL", Server)
    ctx, _ = context(tmp_path, SimpleNamespace(server_address=("127.0.0.1", 2525)), security=security)
    send(ctx, {"to": "a@firma.com", "subject": "Şifreli"})
    assert calls == expected
