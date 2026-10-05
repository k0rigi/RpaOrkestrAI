"""Veritabanı sorgusu: one read-only SELECT on SQL Server, PostgreSQL, MySQL/MariaDB, Oracle or SQLite.

Flow values never become SQL text. ``${name}`` outside quotes is sent as a bound parameter
(a list becomes one parameter per item, for ``IN (${codes})``); inside quotes (``LIKE '%${name}%'``)
it is written as an escaped literal. Before running, the text must be a single SELECT/WITH
statement without write keywords, and the session is made read-only where the database allows
it. SQL Server has no read-only session: the database account must be read-only there.
"""

from __future__ import annotations

import math
import platform
import re
from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from ..errors import WorkflowError

ENGINES = {
    "mssql": ("SQL Server", 1433),
    "postgresql": ("PostgreSQL", 5432),
    "mysql": ("MySQL / MariaDB", 3306),
    "oracle": ("Oracle", 1521),
    "sqlite": ("SQLite (dosya)", None),
    "url": ("Bağlantı adresi (gelişmiş)", None),
}
# Preferred first: the newest Microsoft driver; "SQL Server" ships with every Windows.
ODBC_DRIVERS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server",
                "SQL Server Native Client 11.0", "SQL Server")
# A single statement starting with SELECT/WITH can still write (WITH … DELETE, SELECT … INTO), lock ERP rows
# (FOR UPDATE) or reach other servers; these words are refused outside quotes and comments.
WRITE_WORDS = ("INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT",
               "REVOKE", "DENY", "EXEC", "EXECUTE", "INTO", "OPENROWSET", "OPENDATASOURCE", "OPENQUERY")
WRITE_PATTERN = re.compile(r"\b(" + "|".join(WRITE_WORDS) + r")\b|\bxp_\w+", re.IGNORECASE)
REFERENCE = re.compile(r"\$\{([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\}")
# Comments, string literals and quoted names, in the order a SQL reader meets them.
TOKENS = re.compile(r"--[^\n]*|/\*.*?(?:\*/|$)|'(?:[^']|'')*(?:'|$)|\"[^\"]*(?:\"|$)|\[[^\]]*(?:\]|$)|`[^`]*(?:`|$)",
                    re.DOTALL)
QUERY_LIMIT = 100_000
ROW_LIMIT = 100_000
READ_ONLY = ("Veritabanı sorgusu yalnız okuma yapar: SELECT veya WITH ile başlayan tek bir sorgu yazın. Kayıt "
             "eklemek, değiştirmek veya silmek için bu adım kullanılamaz.")


def engine_label(config: dict) -> str:
    return ENGINES.get(config.get("engine") or "url", ENGINES["url"])[0]


def check_read_only(sql: str) -> None:
    """A single SELECT/WITH statement with no write keyword outside quotes and comments."""
    bare = TOKENS.sub(lambda m: " " if m.group(0)[:2] in ("--", "/*") else " q ", sql).strip()
    while bare.endswith(";"):
        bare = bare[:-1].rstrip()
    if ";" in bare:
        raise WorkflowError("Tek bir sorgu yazın; noktalı virgülle ayrılmış birden fazla komut çalıştırılamaz.")
    if not re.match(r"\(*\s*(SELECT|WITH)\b", bare, re.IGNORECASE):
        raise WorkflowError(READ_ONLY)
    found = WRITE_PATTERN.search(bare)
    if found:
        raise WorkflowError(f"{READ_ONLY} Sorguda “{found.group(0).upper()}” var.")


def bind(sql: str, lookup: Callable[[str], Any], backslash_escapes: bool = False) -> tuple[str, dict[str, Any]]:
    """Replace ${name} with bound parameters (or escaped text inside quotes); the guard runs first."""
    check_read_only(REFERENCE.sub("0", sql))
    values: dict[str, Any] = {}
    pieces: list[str] = []
    position = 0

    def parameter(value: Any) -> str:
        if isinstance(value, dict):
            raise WorkflowError("Sorguda bir kayıt (nesne) kullanılamaz; ${row.alan} gibi tek bir alan yazın.")
        if isinstance(value, list):
            if not value:
                raise WorkflowError("Sorgudaki liste boş; IN (${liste}) için en az bir değer gerekir.")
            if len(value) > 1000:
                raise WorkflowError("Sorgudaki liste en fazla 1000 değer içerebilir.")
            return ", ".join(parameter(item) for item in value)
        if isinstance(value, float) and not math.isfinite(value):
            raise WorkflowError("Sorguya sonsuz veya geçersiz sayı verilemez.")
        name = f"p{len(values)}"
        values[name] = value
        return f":{name}"

    def literal(match: re.Match) -> str:
        value = lookup(match.group(1))
        if isinstance(value, (dict, list)):
            raise WorkflowError("Tırnak içindeki ${…} yalnız metin veya sayı olabilir.")
        value = "" if value is None else str(value)
        if backslash_escapes:
            value = value.replace("\\", "\\\\")
        return value.replace("'", "''")

    for token in TOKENS.finditer(sql):
        pieces.append(REFERENCE.sub(lambda m: parameter(lookup(m.group(1))), _colons(sql[position:token.start()])))
        text = token.group(0)
        pieces.append(_colons(REFERENCE.sub(literal, text)) if text.startswith("'") else _colons(text))
        position = token.end()
    pieces.append(REFERENCE.sub(lambda m: parameter(lookup(m.group(1))), _colons(sql[position:])))
    return "".join(pieces), values


def _colons(part: str) -> str:
    """SQLAlchemy reads ":word" as a parameter; a colon the user wrote stays a colon (PostgreSQL ::int keeps)."""
    return re.sub(r"(?<![:\w\\]):(?=\w)", r"\\:", part)


def plain(value: Any) -> Any:
    """Database values as flow values (text, numbers, true/false, null)."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    read = getattr(value, "read", None)  # Oracle LOB
    if callable(read):
        return plain(read())
    return str(value)


def records(columns: list[str], rows: Iterator[tuple]) -> list[dict[str, Any]]:
    names: list[str] = []
    for column in columns:
        name, number = str(column or "sutun"), 2
        while name in names:
            name, number = f"{column}_{number}", number + 1
        names.append(name)
    return [{name: plain(value) for name, value in zip(names, row)} for row in rows]


class QueryDatabase:
    """A lazily created SQLAlchemy engine for one connection profile."""

    def __init__(self, config: dict, timeout_seconds: float = 30):
        self.config = config
        self.kind = config.get("engine") or "url"
        self.timeout = max(1, math.ceil(timeout_seconds))
        self._engine: Any = None

    # ----- connection -------------------------------------------------------------
    def url(self) -> Any:
        import sqlalchemy as sa

        c, kind = self.config, self.kind
        if kind == "url":
            if not c.get("url"):
                raise WorkflowError("Bağlantı adresi girilmemiş.")
            try:
                return sa.engine.make_url(c["url"])
            except Exception as exc:
                raise WorkflowError("Bağlantı adresi okunamadı. Biçim: tür+sürücü://kullanıcı:şifre@sunucu/veritabanı"
                                    ) from exc
        if kind == "sqlite":
            return sa.engine.URL.create("sqlite")
        host = str(c.get("host") or "").strip()
        if not host:
            raise WorkflowError("Veritabanı sunucusunun adını veya IP adresini girin.")
        port = c.get("port") or None
        named_instance = kind == "mssql" and "\\" in host
        port = None if named_instance and not port else int(port or ENGINES[kind][1])
        user, password, database = c.get("user") or None, c.get("password") or None, c.get("database") or None
        if kind == "mssql":
            if platform.system() == "Windows":
                return sa.engine.URL.create("mssql+pyodbc", user, password, host, port, database,
                                            query=self._odbc_options())
            return sa.engine.URL.create("mssql+pymssql", user, password, host, port, database)
        if kind == "postgresql":
            return sa.engine.URL.create("postgresql+psycopg", user, password, host, port, database)
        if kind == "mysql":
            return sa.engine.URL.create("mysql+pymysql", user, password, host, port, database,
                                        query={"charset": "utf8mb4"})
        return sa.engine.URL.create("oracle+oracledb", user, password, host, port,
                                    query={"service_name": database} if database else {})

    @staticmethod
    def _odbc_options() -> dict[str, str]:
        try:
            import pyodbc
        except ImportError as exc:
            raise WorkflowError("SQL Server sürücüsü (pyodbc) yüklenemedi.") from exc
        installed = set(pyodbc.drivers())
        driver = next((name for name in ODBC_DRIVERS if name in installed), None)
        if driver is None:
            raise WorkflowError("Bu bilgisayarda SQL Server ODBC sürücüsü bulunamadı. Microsoft ODBC Driver 18 for "
                                "SQL Server'ı kurun.")
        options = {"driver": driver}
        if driver == "ODBC Driver 18 for SQL Server":
            # Driver 18 encrypts by default and rejects the self-signed certificate of most in-house servers.
            options["TrustServerCertificate"] = "yes"
        return options

    def _create(self) -> Any:
        import sqlalchemy as sa

        url = self.url()
        backend, driver = url.get_backend_name(), url.get_driver_name()
        options: dict[str, Any] = {}
        if backend == "sqlite":
            target = Path(str(self.config.get("path") or url.database or "")).expanduser()
            if not target.is_file():
                raise WorkflowError(f"SQLite dosyası bulunamadı: {target}")
            import sqlite3

            uri = target.resolve().as_uri() + "?mode=ro"
            return sa.create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True, timeout=self.timeout,
                                                                                 check_same_thread=False))
        if backend == "postgresql":
            options = {"connect_timeout": self.timeout, "options": f"-c statement_timeout={self.timeout * 1000}"}
        elif backend == "mssql" and driver == "pyodbc":
            options = {"timeout": self.timeout}
        elif backend == "mssql" and driver == "pymssql":
            options = {"login_timeout": self.timeout, "timeout": self.timeout}
        elif backend == "mysql":
            options = {"connect_timeout": self.timeout, "read_timeout": self.timeout}
        elif backend == "oracle":
            options = {"tcp_connect_timeout": self.timeout}
        engine = sa.create_engine(url, pool_pre_ping=True, hide_parameters=True, pool_timeout=self.timeout,
                                  connect_args=options)

        def prepare(dbapi_connection: Any, _record: Any) -> None:
            if backend == "mssql" and driver == "pyodbc":
                dbapi_connection.timeout = self.timeout  # per query
            elif backend == "oracle":
                dbapi_connection.call_timeout = self.timeout * 1000
            elif backend == "mysql":
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SET SESSION TRANSACTION READ ONLY")

        sa.event.listen(engine, "connect", prepare, insert=True)
        return engine

    def engine(self) -> Any:
        if self._engine is None:
            self._engine = self._create()
        return self._engine

    def _read_only(self, connection: Any) -> None:
        name = connection.dialect.name
        if name in {"postgresql", "oracle"}:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    # ----- use --------------------------------------------------------------------
    def ping(self) -> None:
        import sqlalchemy as sa

        with self.engine().connect() as connection:
            transaction = connection.begin()
            try:
                self._read_only(connection)
                connection.scalar(sa.select(sa.literal(1)))
            finally:
                transaction.rollback()

    def query(self, sql: str, lookup: Callable[[str], Any], max_rows: int) -> tuple[list[dict], bool]:
        """Rows (at most max_rows) and whether more were left unread."""
        import sqlalchemy as sa

        if not isinstance(sql, str) or not sql.strip():
            raise WorkflowError("SQL sorgusunu yazın.")
        if len(sql) > QUERY_LIMIT:
            raise WorkflowError("SQL sorgusu çok uzun.")
        engine = self.engine()
        statement, values = bind(sql, lookup, backslash_escapes=engine.dialect.name == "mysql")
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                self._read_only(connection)
                result = connection.execute(sa.text(statement), values)
                if not result.returns_rows:
                    raise WorkflowError(READ_ONLY)
                rows = result.fetchmany(max_rows + 1)
                more = len(rows) > max_rows
                return records(list(result.keys()), iter(rows[:max_rows])), more
            finally:
                # Nothing a query does is ever kept.
                transaction.rollback()

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> QueryDatabase:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def describe(exc: Exception) -> str:
    """A short Turkish explanation of a driver error, without the password or the full SQL."""
    message = str(getattr(exc, "orig", None) or exc)
    lowered = message.lower()
    if any(word in lowered for word in ("login failed", "password authentication", "access denied", "ora-01017",
                                        "18456")):
        return "Veritabanı kullanıcı adı veya şifresi kabul edilmedi."
    if any(word in lowered for word in ("timeout", "timed out", "could not connect", "connection refused",
                                        "unable to connect", "network", "ora-12541", "ora-12170", "08001",
                                        "name or service not known", "nodename nor servname")):
        return ("Veritabanı sunucusuna ulaşılamadı. Sunucu adını, portu, ağ / VPN bağlantısını ve güvenlik duvarını "
                "kontrol edin.")
    if any(word in lowered for word in ("read-only", "read only", "readonly", "ora-01456")):
        return READ_ONLY
    first = message.strip().splitlines()[0] if message.strip() else type(exc).__name__
    return f"Veritabanı sorguyu çalıştıramadı: {first[:300]}"
