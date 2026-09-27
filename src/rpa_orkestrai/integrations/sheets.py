"""Google Sheets operations using service-account credentials outside Git."""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

_T = TypeVar("_T")
_CELL = r"\$?[A-Za-z]{1,3}\$?[1-9][0-9]*"
_RETRY_STATUS = {429, 500, 502, 503, 504}


def normalize_spreadsheet_id(value: str) -> str:
    """Accept an ID or a Google Sheets sharing URL without fetching the URL."""
    error = "Provide a Google spreadsheet ID or an https://docs.google.com/spreadsheets/d/... URL."
    if not isinstance(value, str):
        raise ValueError(error)
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError(error)
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "docs.google.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            raise ValueError(error)
    except ValueError:
        raise ValueError(error) from None
    match = re.fullmatch(
        r"/spreadsheets/(?:u/[0-9]+/)?d/([A-Za-z0-9_-]+)(?:/(?:edit|view|preview|copy|htmlview))?/?",
        parsed.path,
    )
    if not match:
        raise ValueError(error)
    return match.group(1)


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
        spreadsheet_id = normalize_spreadsheet_id(spreadsheet_id)
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
        return [list(row) for row in self._retry(
            lambda: worksheet.get(a1, value_render_option="FORMATTED_VALUE"),
        )]

    def get_column(
        self, start_cell: str = "B2", max_rows: int = 100, empty_policy: str = "stop",
    ) -> list[dict[str, int | str]]:
        """Read at most max_rows physical rows for an ordered workflow loop.

        Google omits trailing empty rows but preserves interior empty rows. Keep
        each returned value's original row number so later steps can write a
        result beside the source cell, even when empty rows are skipped.
        """
        self._address(start_cell, cell=True)
        if type(max_rows) is not int or not 1 <= max_rows <= 1000:
            raise ValueError("max_rows must be an integer between 1 and 1000.")
        if empty_policy not in ("stop", "skip"):
            raise ValueError("empty_policy must be 'stop' or 'skip'.")
        match = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)", start_cell)
        assert match is not None  # Validated above, before opening a connection.
        column, first_row = match.group(1).upper(), int(match.group(2))
        rows = self.get_range(f"{column}{first_row}:{column}{first_row + max_rows - 1}")
        records: list[dict[str, int | str]] = []
        for offset, row in enumerate(rows[:max_rows]):
            value = "" if not row or row[0] is None else str(row[0])
            if not value.strip():
                if empty_policy == "stop":
                    break
                continue
            row_number = first_row + offset
            records.append({"row_number": row_number, "cell": f"{column}{row_number}", "value": value})
        return records

    def get_rows(
        self, *, start_row: int = 2, max_rows: int = 100,
        columns: Mapping[str, str] | None = None, key: str = "form_id",
        empty_policy: str = "stop",
    ) -> list[dict[str, int | str]]:
        """Read a bounded snapshot with named fields and optional blank values.

        Only the key field decides whether a row is empty. Other fields retain
        blank cells, allowing workflows to branch on a missing status without
        discarding the source record. Physical row numbers remain unchanged.
        """
        if type(start_row) is not int or not 1 <= start_row <= 1_000_000:
            raise ValueError("start_row must be an integer between 1 and 1000000.")
        if type(max_rows) is not int or not 1 <= max_rows <= 1000:
            raise ValueError("max_rows must be an integer between 1 and 1000.")
        last_row = start_row + max_rows - 1
        if last_row > 1_000_000:
            raise ValueError("The requested range must end at or before row 1000000.")
        if empty_policy not in ("stop", "skip"):
            raise ValueError("empty_policy must be 'stop' or 'skip'.")
        if columns is None:
            columns = {"form_id": "B", "status": "C"}
        if not isinstance(columns, Mapping) or not 1 <= len(columns) <= 32:
            raise ValueError("Map between 1 and 32 named fields to Sheets columns.")

        column_names: dict[str, str] = {}
        column_numbers: dict[str, int] = {}
        for field, column in columns.items():
            if (
                not isinstance(field, str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", field)
                or field in {"row_number", "__proto__", "prototype", "constructor"}
            ):
                raise ValueError("Use unique field names such as form_id or status; row_number is reserved.")
            if not isinstance(column, str) or not re.fullmatch(r"\$?[A-Za-z]{1,3}", column):
                raise ValueError("Map each field to a column letter such as B, C or AA.")
            normalized = column.lstrip("$").upper()
            if normalized in column_names.values():
                raise ValueError("Map each Sheets column only once.")
            column_names[field] = normalized
            number = 0
            for letter in normalized:
                number = number * 26 + ord(letter) - ord("A") + 1
            column_numbers[field] = number

        if not isinstance(key, str) or key not in column_names:
            raise ValueError("The key must name one of the mapped fields.")
        first_field = min(column_numbers, key=column_numbers.__getitem__)
        last_field = max(column_numbers, key=column_numbers.__getitem__)
        first_column = column_numbers[first_field]
        if column_numbers[last_field] - first_column >= 64:
            raise ValueError("Keep mapped columns within a span of 64 columns.")
        a1 = f"{column_names[first_field]}{start_row}:{column_names[last_field]}{last_row}"
        rows = self.get_range(a1)
        records: list[dict[str, int | str]] = []
        for offset, row in enumerate(rows[:max_rows]):
            record: dict[str, int | str] = {"row_number": start_row + offset}
            for field, number in column_numbers.items():
                index = number - first_column
                value = row[index] if index < len(row) else None
                record[field] = "" if value is None else str(value)
            if not str(record[key]).strip():
                if empty_policy == "stop":
                    break
                continue
            records.append(record)
        return records

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
