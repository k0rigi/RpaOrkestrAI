"""Dosya uzantısı ve içerik denetimi: Dosya bilgisi adımı ve Kullanıcıya dosya seçtir."""

import platform
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

from rpa_orkestrai.actions import dialogs
from rpa_orkestrai.actions.files import info
from rpa_orkestrai.errors import WorkflowError
from rpa_orkestrai.file_types import content_matches, describe, detect, parse_extensions, problem

ZIP = b"PK\x03\x04" + b"\x00" * 40
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40
HTML = "<!DOCTYPE html><html><body>Oturumunuz sona erdi</body></html>".encode()


def ctx():
    logs = []
    return SimpleNamespace(log=logs.append, logs=logs)


def write(folder, name, content):
    file = folder / name
    file.write_bytes(content)
    return file


def test_extension_lists_are_read_leniently_and_checked():
    assert parse_extensions("xlsx, .XLS; *.csv  pdf|xlsx") == ["xlsx", "xls", "csv", "pdf"]
    assert parse_extensions("") == [] and parse_extensions(None) == [] and parse_extensions(["Txt"]) == ["txt"]
    for wrong in ("x-ls", "çsv", "a" * 16):
        with pytest.raises(WorkflowError, match="geçerli bir uzantı değil"):
            parse_extensions(wrong)


@pytest.mark.parametrize("name,content,kind,matches", [
    ("rapor.xlsx", ZIP, "zip", True),
    ("rapor.xls", OLE, "ole", True),
    ("rapor.xlsx", HTML, "html", False),  # the site's error page saved under the expected name
    ("rapor.xls", HTML, "html", False),
    ("fatura.pdf", b"%PDF-1.7\n", "pdf", True),
    ("fatura.pdf", b"", "empty", False),
    ("fatura.pdf", ZIP, "zip", False),
    ("liste.csv", "no;tutar\n1;12,5\n".encode(), "text", True),
    ("liste.csv", "﻿ad;şehir\nÇağrı;İzmir\n".encode("utf-8"), "text", True),
    ("liste.csv", "ad;şehir\nÇağrı;İzmir\n".encode("cp1254"), "text", True),
    ("liste.csv", "ad;şehir\n".encode("utf-16"), "text", True),
    ("liste.csv", b"", "empty", True),
    ("liste.csv", HTML, "html", False),
    ("sayfa.html", HTML, "html", True),
    ("veri.xml", b'<?xml version="1.0"?><a/>', "xml", True),
    ("resim.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "png", True),
    ("resim.jpg", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "png", False),
    ("ozel.abc", ZIP, "zip", None),  # an extension we do not know is never called wrong
    ("ikili.dat", b"\x00\x01\x02", "binary", False),
])
def test_content_is_recognised_from_the_first_bytes(tmp_path, name, content, kind, matches):
    file = write(tmp_path, name, content)
    assert detect(file) == kind
    data = describe(file)
    assert data["type"] == kind and data["content_matches"] is matches and data["extension"] == file.suffix[1:]


def test_problems_name_the_reason_in_turkish(tmp_path):
    data = describe(write(tmp_path, "rapor.xlsx", HTML))
    assert problem(data, ["xlsx"], False) == ""
    assert "içeriği web sayfası (HTML)" in problem(data, ["xlsx"], True)
    assert "izin verilenler: .pdf, .csv" in problem(data, ["pdf", "csv"], True)
    assert "uzantısız" in problem(describe(write(tmp_path, "BENIOKU", b"metin")), ["txt"], True)
    assert content_matches("xlsx", "unknown") is None


def test_file_info_reports_and_stops_or_continues(tmp_path):
    good = write(tmp_path, "Fatura Listesi.XLSX", ZIP)
    result = info(ctx(), {"path": str(good), "extensions": "xlsx, xls"})
    assert result["ok"] is True and result["allowed"] is True and result["extension"] == "xlsx"
    assert result["name"] == "Fatura Listesi.XLSX" and result["stem"] == "Fatura Listesi" and result["size"] == len(ZIP)
    assert result["problem"] == "" and result["exists"] is True and result["modified"]
    wrong = write(tmp_path, "rapor.xlsx", HTML)
    with pytest.raises(WorkflowError, match="Akış durduruldu"):
        info(ctx(), {"path": str(wrong), "extensions": "xlsx"})
    run = ctx()
    kept = info(run, {"path": str(wrong), "extensions": "xlsx", "on_problem": "continue"})
    assert kept["ok"] is False and "web sayfası" in kept["problem"] and run.logs == [kept["problem"]]
    # Content check off: only the extension counts.
    assert info(ctx(), {"path": str(wrong), "extensions": "xlsx", "check_content": False})["ok"] is True
    # No list: any extension is fine, the content still has to fit.
    assert info(ctx(), {"path": str(write(tmp_path, "not.txt", b"merhaba"))})["allowed"] is None
    missing = info(ctx(), {"path": str(tmp_path / "yok.csv"), "on_problem": "continue"})
    assert missing["exists"] is False and missing["ok"] is False and missing["extension"] == "csv"
    with pytest.raises(WorkflowError, match="Dosya bulunamadı"):
        info(ctx(), {"path": str(tmp_path / "yok.csv")})
    with pytest.raises(WorkflowError, match="klasör"):
        info(ctx(), {"path": str(tmp_path)})


@pytest.fixture
def chooser(monkeypatch):
    """The dialog is replaced; the answer is what the person would pick."""
    calls = []

    def answer(value):
        def mac(script, *arguments, timeout):
            calls.append(("mac", arguments))
            return value

        def windows(script, environment, timeout):
            calls.append(("windows", environment))
            return value

        monkeypatch.setattr(dialogs, "_osascript", mac)
        monkeypatch.setattr(dialogs, "run_windows_dialog", windows)
    return answer, calls


@pytest.mark.parametrize("system", ["Darwin", "Windows"])
def test_choose_file_offers_only_the_allowed_kinds_and_checks_the_choice(tmp_path, chooser, monkeypatch, system):
    answer, calls = chooser
    monkeypatch.setattr(dialogs.platform, "system", lambda: system)
    picked = write(tmp_path, "siparis.csv", b"no;tutar\n")
    answer(f"ok:{picked}")
    assert dialogs.choose_file(ctx(), {"extensions": ".CSV, xlsx", "folder": str(tmp_path)}) == str(picked)
    where, sent = calls[-1]
    if system == "Darwin":
        assert sent == ("Dosya seçin", str(tmp_path), "csv", "xlsx")
    else:
        assert sent["RPA_FILTER"] == "İzin verilen dosyalar (*.csv;*.xlsx)|*.csv;*.xlsx"
        assert sent["RPA_FOLDER"] == str(tmp_path)
    answer(f"ok:{write(tmp_path, 'not.txt', b'x')}")
    with pytest.raises(WorkflowError, match="izin verilen türde değil"):
        dialogs.choose_file(ctx(), {"extensions": "csv"})
    answer("cancel")
    with pytest.raises(WorkflowError, match="iptal"):
        dialogs.choose_file(ctx(), {"extensions": "csv"})
    assert dialogs.choose_file(ctx(), {"on_cancel": "continue"}) == ""
    count = len(calls)
    with pytest.raises(WorkflowError, match="Başlangıç klasörü bulunamadı"):
        dialogs.choose_file(ctx(), {"folder": str(tmp_path / "yok")})
    with pytest.raises(WorkflowError, match="geçerli bir uzantı"):
        dialogs.choose_file(ctx(), {"extensions": "x-y"})
    assert len(calls) == count  # nothing was shown for a wrong setting


def test_windows_filter_without_a_list_shows_every_file():
    assert dialogs.windows_filter([]) == "Tüm dosyalar (*.*)|*.*"


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows Open dialog")
def test_windows_open_dialog_script_and_filter_are_accepted_by_windows(tmp_path):
    output = dialogs.run_windows_dialog(dialogs.WINDOWS_CHOOSE_FILE, {
        "RPA_TITLE": "Fatura seçin", "RPA_FILTER": dialogs.windows_filter(["xlsx", "csv"]),
        "RPA_FOLDER": str(tmp_path), "RPA_CHECK_ONLY": "1"}, 120)
    assert output == "check:İzin verilen dosyalar (*.xlsx;*.csv)|*.xlsx;*.csv"


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS choose file")
def test_mac_choose_file_script_compiles(tmp_path):
    result = subprocess.run(["/usr/bin/osacompile", "-o", str(tmp_path / "sec.scpt"), "-e", dialogs.MAC_CHOOSE_FILE],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_unsupported_platform_says_so(monkeypatch):
    monkeypatch.setattr(dialogs.platform, "system", lambda: "Linux")
    with mock.patch.object(dialogs, "_osascript") as mac:
        with pytest.raises(WorkflowError, match="macOS ve Windows"):
            dialogs.choose_file(ctx(), {})
    mac.assert_not_called()
