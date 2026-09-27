"""Google Sheets operations using service-account credentials outside Git."""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

_T = TypeVar("_T")
_CELL = r"\$?[A-Za-z]{1,3}\$?[1-9][0-9]*"
_RETRY_STATUS = {429, 500, 502, 503, 504}


class SheetsService:
    """Lazy gspread service with safe retries for idempotent operations.

    append_row is deliberately issued only once: retrying an ambiguous network
    failure could append duplicates. Write formulas only via explicit RAW=False.
    """

    def __init__(
        self, credentials_path: str | Path, spreadsheet_id: str,
        worksheet: str = "Sheet1", *, max_attempts: int = 3,
        timeout: float = 30, backoff: float = 1,
    ) -> None:
        if not isinstance(spreadsheet_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet_id):
            raise ValueError("A Google spreadsheet ID (not its URL) is required.")
        if not worksheet or len(worksheet) > 100:
            raise ValueError("Provide a worksheet title of at most 100 characters.")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5.")
        if not 0 < timeout <= 120 or not 0 <= backoff <= 10:
            raise ValueError("Invalid Sheets timeout or retry backoff.")
        self.credentials_path = Path(credentials_path).expanduser()
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.backoff = backoff
        self._client: Any = None
        self._worksheet: Any = None

    @staticmethod
    def _address(address: str, *, cell: bool = False) -> str:
        pattern = _CELL if cell else rf"{_CELL}(?::{_CELL})?"
        if not isinstance(address, str) or not re.fullmatch(pattern, address):
            raise ValueError("Use a cell such as A1 or a bounded range such as A1:C10.")
        return address

    def _retry(self, operation: Callable[[], _T]) -> _T:
        for attempt in range(self.max_attempts):
            try:
                return operation()
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                # gspread uses requests; transport retries are safe for reads and
                # exact-range overwrites, never for append operations.
                import requests

                retryable = status in _RETRY_STATUS or isinstance(
                    exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
                )
                if not retryable or attempt + 1 >= self.max_attempts:
                    raise
                time.sleep(min(self.backoff * 2 ** attempt + random.uniform(0, self.backoff / 4), 30))
        raise AssertionError("Unreachable retry state.")

    def _connect(self) -> Any:
        if self._worksheet is None:
            if not self.credentials_path.is_file():
                raise FileNotFoundError("Google service-account credential file was not found.")
            import gspread

            if self._client is None:
                self._client = gspread.service_account(
                    filename=str(self.credentials_path),
                    scopes=["https://www.googleapis.com/auth/spreadsheets"],
                )
                self._client.set_timeout(self.timeout)
            self._worksheet = self._retry(
                lambda: self._client.open_by_key(self.spreadsheet_id).worksheet(self.worksheet_name),
            )
        return self._worksheet

    def get_cell(self, address: str) -> str | None:
        self._address(address, cell=True)
        worksheet = self._connect()
        return self._retry(lambda: worksheet.acell(address).value)

    def update_cell(self, address: str, value: Any, *, raw: bool = True) -> Any:
        self._address(address, cell=True)
        return self.update_range(address, [[value]], raw=raw)

    def get_range(self, a1: str) -> list[list[Any]]:
        self._address(a1)
        worksheet = self._connect()
        return [list(row) for row in self._retry(lambda: worksheet.get(a1))]

    def update_range(self, a1: str, values: Sequence[Sequence[Any]], *, raw: bool = True) -> Any:
        self._address(a1)
        if isinstance(values, (str, bytes)) or not values:
            raise ValueError("Sheet values must be a non-empty matrix.")
        if any(isinstance(row, (str, bytes)) or not row for row in values):
            raise ValueError("Each matrix row must be a non-empty sequence.")
        if len({len(row) for row in values}) != 1:
            raise ValueError("Sheet matrix rows must have equal lengths.")
        worksheet = self._connect()
        return self._retry(lambda: worksheet.update(values=[list(row) for row in values], range_name=a1, raw=raw))

    def append_row(self, values: Sequence[Any]) -> Any:
        if isinstance(values, (str, bytes)) or not values:
            raise ValueError("Provide a non-empty row of values.")
        return self._connect().append_row(list(values), value_input_option="RAW")

    def close(self) -> None:
        if self._client is not None:
            session = getattr(getattr(self._client, "http_client", None), "session", None)
            if session is not None:
                session.close()
        self._worksheet = None
        self._client = None

    def __enter__(self) -> SheetsService:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
