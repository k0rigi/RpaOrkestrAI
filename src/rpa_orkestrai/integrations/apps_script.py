"""Google Sheets through a small Apps Script web app: no Google Cloud project or JSON key.

The script is deployed from the spreadsheet by its owner ("Execute as: Me",
"Who has access: Anyone"), so the sheet itself stays private. Every request
carries a random token that only this Studio and the script know. The client
implements the same primitives as SheetsService, so all Sheets steps work.
"""

from __future__ import annotations

import json
import re
import secrets
import ssl
import time
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from ..errors import WorkflowError
from .sheets import SheetsService

SCRIPT_HOSTS = {"script.google.com", "script.googleusercontent.com"}
RESPONSE_LIMIT = 20 * 1024 * 1024
URL_PATTERN = re.compile(r"https://script\.google\.com/(?:a/macros/[A-Za-z0-9.-]+|macros)/s/[A-Za-z0-9_-]{20,}/exec")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{24,128}")

SCRIPT_TEMPLATE = r"""/**
 * RpaOrkestrAI — Google Sheets bağlantısı (Apps Script)
 *
 * Kurulum: Uzantılar → Apps Script → bu kodun tamamını yapıştırın → Kaydet →
 * Dağıt → Yeni dağıtım → Tür: Web uygulaması → Yürütme: Ben →
 * Erişimi olanlar: Herkes → Dağıt → izinleri onaylayın → Web uygulaması URL'sini
 * RpaOrkestrAI → Bağlantılar ve ayarlar → Google Sheets bölümüne yapıştırın.
 *
 * Tablonuz herkese açılmaz: betik sizin adınıza çalışır ve yalnız aşağıdaki
 * anahtarı bilen RpaOrkestrAI isteklerini kabul eder. Anahtarı paylaşmayın.
 */
const RPA_TOKEN = "__TOKEN__";

function doPost(e) {
  try {
    const request = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    if (!request.token || request.token !== RPA_TOKEN) {
      return reply_({ ok: false, error: "Güvenlik anahtarı eşleşmiyor." });
    }
    if (request.action === "ping") {
      const active = SpreadsheetApp.getActiveSpreadsheet();
      return reply_({ ok: true, version: 1, spreadsheet: active ? active.getName() : null });
    }
    const book = request.spreadsheet
      ? SpreadsheetApp.openById(request.spreadsheet)
      : SpreadsheetApp.getActiveSpreadsheet();
    if (!book) return reply_({ ok: false, error: "Tablo bulunamadı." });
    const sheet = book.getSheetByName(request.sheet);
    if (!sheet) return reply_({ ok: false, error: "Sayfa bulunamadı: " + request.sheet });
    if (request.action === "read") {
      return reply_({ ok: true, values: sheet.getRange(request.range).getDisplayValues() });
    }
    const lock = LockService.getScriptLock();
    lock.waitLock(20000);
    try {
      if (request.action === "write") {
        const values = request.values;
        const start = sheet.getRange(request.range);
        const target = sheet.getRange(start.getRow(), start.getColumn(), values.length, values[0].length);
        target.setValues(request.raw ? values.map(function (row) { return row.map(asText_); }) : values);
        SpreadsheetApp.flush();
        return reply_({ ok: true });
      }
      if (request.action === "append") {
        sheet.appendRow(request.raw ? request.values.map(asText_) : request.values);
        SpreadsheetApp.flush();
        return reply_({ ok: true });
      }
    } finally {
      lock.releaseLock();
    }
    return reply_({ ok: false, error: "Bilinmeyen işlem: " + request.action });
  } catch (error) {
    return reply_({ ok: false, error: String((error && error.message) || error) });
  }
}

// Text that Sheets would read as a formula, number or date is kept as typed.
function asText_(value) {
  if (typeof value !== "string") return value;
  const looksLikeData = /^[=+\-@]/.test(value) || /^\s*[-+]?[\d.,]+\s*$/.test(value) ||
    /^\d{1,4}[./-]\d{1,2}[./-]\d{1,4}/.test(value);
  return looksLikeData ? "'" + value : value;
}

function reply_(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}
"""


def new_token() -> str:
    return secrets.token_urlsafe(24)


def script_code(token: str) -> str:
    if not TOKEN_PATTERN.fullmatch(token or ""):
        raise ValueError("Geçersiz Apps Script anahtarı.")
    return SCRIPT_TEMPLATE.replace("__TOKEN__", token)


def validate_url(url: Any) -> str:
    url = str(url or "").strip()
    if not URL_PATTERN.fullmatch(url):
        raise ValueError("Apps Script adresi https://script.google.com/macros/s/…/exec biçiminde olmalıdır. "
                         "Dağıt → Dağıtımları yönet bölümündeki Web uygulaması URL'sini kopyalayın.")
    return url


class _GoogleOnly(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).hostname not in SCRIPT_HOSTS or urlsplit(newurl).scheme != "https":
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class AppsScriptSheets(SheetsService):
    def __init__(self, url: str, token: str, spreadsheet_id: str, worksheet: str = "Sheet1", *,
                 timeout: float = 60, opener: Any = None, attempts: int = 2):
        super().__init__("", spreadsheet_id, worksheet, timeout=min(timeout, 120))
        self.url = validate_url(url)
        if not TOKEN_PATTERN.fullmatch(token or ""):
            raise WorkflowError("Apps Script anahtarı eksik. Ayarlar → Google Sheets bölümünden yeniden oluşturun.")
        self.token, self.attempts = token, attempts
        if opener is None:
            import certifi

            opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
                                  _GoogleOnly())
        self.opener = opener

    def call(self, action: str, **payload: Any) -> dict:
        body = json.dumps({"token": self.token, "action": action, "spreadsheet": self.spreadsheet_id,
                           "sheet": self.worksheet_name, **payload}, ensure_ascii=False).encode("utf-8")
        for attempt in range(self.attempts):
            request = Request(self.url, data=body, method="POST",
                              headers={"Content-Type": "application/json", "User-Agent": "RpaOrkestrAI"})
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    raw = response.read(RESPONSE_LIMIT + 1)
                    content_type = response.headers.get("Content-Type", "")
                break
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt + 1 < self.attempts:
                    time.sleep(1.5)
                    continue
                raise WorkflowError(f"Apps Script {exc.code} hatası döndürdü. Dağıtımın Web uygulaması olarak "
                                    "yayımlandığını kontrol edin.") from exc
            except (URLError, OSError, ValueError) as exc:
                if attempt + 1 < self.attempts:
                    time.sleep(1.5)
                    continue
                raise WorkflowError("Apps Script adresine ulaşılamadı. İnternet bağlantısını ve adresi kontrol edin.") from exc
        if len(raw) > RESPONSE_LIMIT:
            raise WorkflowError("Apps Script yanıtı çok büyük; daha küçük bir aralık okuyun.")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            hint = ("Dağıtımda Erişimi olanlar: Herkes seçilmemiş olabilir." if "html" in content_type.lower()
                    else "Yanıt okunamadı.")
            raise WorkflowError(f"Apps Script bağlantısı kurulamadı. {hint}") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            error = result.get("error") if isinstance(result, dict) else None
            raise WorkflowError(f"Apps Script: {error or 'işlem tamamlanamadı'}")
        return result

    def ping(self) -> dict:
        return self.call("ping")

    def _connect(self) -> Any:
        return self

    def get_range(self, a1: str) -> list[list[Any]]:
        self._address(a1)
        values = self.call("read", range=a1).get("values") or []
        return [list(row) for row in values]

    def get_cell(self, address: str) -> str | None:
        self._address(address, cell=True)
        values = self.get_range(address)
        value = values[0][0] if values and values[0] else None
        return None if value in (None, "") else value

    def update_range(self, a1: str, values: Sequence[Sequence[Any]], *, raw: bool = True) -> Any:
        self._address(a1)
        if isinstance(values, (str, bytes)) or not values:
            raise ValueError("Sheet values must be a non-empty matrix.")
        if any(isinstance(row, (str, bytes)) or not row for row in values):
            raise ValueError("Each matrix row must be a non-empty sequence.")
        if len({len(row) for row in values}) != 1:
            raise ValueError("Sheet matrix rows must have equal lengths.")
        return self.call("write", range=a1, values=[list(row) for row in values], raw=raw)

    def append_row(self, values: Sequence[Any]) -> Any:
        if isinstance(values, (str, bytes)) or not values:
            raise ValueError("Provide a non-empty row of values.")
        return self.call("append", values=list(values), raw=True)

    def close(self) -> None:
        pass
