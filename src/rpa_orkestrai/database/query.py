"""Veritabanı sorgusu (read-only SELECT) and Veritabanında değişiklik yap (one guarded write statement).

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
             "eklemek, değiştirmek veya silmek için Veritabanında değişiklik yap adımını kullanın.")
# Writes: one INSERT/UPDATE/DELETE/MERGE or stored procedure call; schema changes, dynamic SQL and server
# commands are never run. The target must be on the connection's own list of tables and procedures.
NEVER_WORDS = ("DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE", "DENY", "OPENROWSET", "OPENDATASOURCE",
               "OPENQUERY", "SHUTDOWN", "BACKUP", "RESTORE", "DBCC", "RECONFIGURE", "SP_EXECUTESQL", "SP_CONFIGURE",
               "LOAD_FILE", "OUTFILE", "DUMPFILE", "KILL", "ATTACH", "DETACH", "PRAGMA", "VACUUM")
NEVER_PATTERN = re.compile(r"\b(" + "|".join(NEVER_WORDS) + r")\b|\bxp_\w+", re.IGNORECASE)
IDENTIFIER = r'(?:\[[^\]]+\]|"[^"]+"|`[^`]+`|[A-Za-z_][\w$#@]*)'
QUALIFIED = rf"{IDENTIFIER}(?:\s*\.\s*{IDENTIFIER}){{0,3}}"
WRITE_FORMS = {
    "INSERT": re.compile(rf"INSERT\s+(?:INTO\s+)?({QUALIFIED})", re.IGNORECASE),
    "UPDATE": re.compile(rf"UPDATE\s+(?:TOP\s*\(\s*\d+\s*\)\s+)?({QUALIFIED})\s+SET\b", re.IGNORECASE),
    "DELETE": re.compile(rf"DELETE\s+(?:TOP\s*\(\s*\d+\s*\)\s+)?(?:FROM\s+)?({QUALIFIED})\s+WHERE\b",
                         re.IGNORECASE),
    "MERGE": re.compile(rf"MERGE\s+(?:INTO\s+)?({QUALIFIED})", re.IGNORECASE),
    "EXEC": re.compile(rf"EXEC(?:UTE)?\s+(?:@\w+\s*=\s*)?({QUALIFIED})(?![\s]*\()", re.IGNORECASE),
    "CALL": re.compile(rf"CALL\s+({QUALIFIED})\s*\(", re.IGNORECASE),
}
WRITE_HELP = ("Veritabanında değişiklik yap adımı tek bir INSERT, UPDATE ... SET ... WHERE, DELETE FROM ... WHERE, "
              "MERGE veya saklı yordam (EXEC / CALL) komutu çalıştırır.")


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


def object_name(text: str) -> str:
    """dbo.[Fatura Satır] → dbo.fatura satır: quotes removed, case folded, for comparison only."""
    parts = re.findall(IDENTIFIER, text)
    return ".".join(part.strip('[]"`').strip().casefold() for part in parts)


def target_allowed(name: str, targets: list[str]) -> bool:
    """Exact match, or the same last part when one side omits the schema (dbo.Fatura ~ Fatura)."""
    wanted = name.split(".")
    for item in targets:
        allowed = object_name(item).split(".")
        if allowed == wanted or (allowed[-1] == wanted[-1] and (len(allowed) == 1 or len(wanted) == 1)):
            return True
    return False


def check_write(sql: str, targets: list[str]) -> tuple[str, str]:
    """The statement kind and target of one allowed write; anything else is refused before running."""
    # Comments go, string literals become a placeholder; quoted names stay for the target check.
    bare = TOKENS.sub(lambda m: " " if m.group(0)[:2] in ("--", "/*") else (" q " if m.group(0)[0] == "'" else m.group(0)),
                      sql).strip()
    while bare.endswith(";"):
        bare = bare[:-1].rstrip()
    if ";" in bare:
        raise WorkflowError("Tek bir komut yazın; noktalı virgülle ayrılmış birden fazla komut çalıştırılamaz.")
    found = NEVER_PATTERN.search(bare)
    if found:
        raise WorkflowError(f"“{found.group(0).upper()}” içeren komutlar çalıştırılmaz. {WRITE_HELP}")
    keyword = re.match(r"\(*\s*(\w+)", bare)
    kind = (keyword.group(1).upper() if keyword else "")
    kind = "EXEC" if kind == "EXECUTE" else kind
    form = WRITE_FORMS.get(kind)
    match = form.match(bare) if form else None
    if match is None:
        if kind in {"UPDATE", "DELETE"}:
            raise WorkflowError("UPDATE ve DELETE komutlarında tablo adından sonra SET / WHERE gelmelidir; WHERE'siz "
                                "komut tüm tabloyu değiştireceği için çalıştırılmaz.")
        if kind == "EXEC":
            raise WorkflowError("Saklı yordamı adıyla çağırın (EXEC dbo.yordam @p = ${deger}); dinamik SQL "
                                "çalıştırılmaz.")
        raise WorkflowError(WRITE_HELP)
    if kind in {"UPDATE", "DELETE"} and not re.search(r"\bWHERE\b", bare, re.IGNORECASE):
        raise WorkflowError("WHERE koşulu olmayan UPDATE veya DELETE çalıştırılmaz.")
    target = object_name(match.group(1))
    if not target_allowed(target, targets):
        raise WorkflowError(f"“{target}” bu bağlantıda değiştirilebilecek tablo veya yordamlar arasında değil. "
                            "Ayarlar → Bağlantılar'dan veritabanı bağlantısının listesine ekleyin.")
    return kind, target


def bind(sql: str, lookup: Callable[[str], Any], backslash_escapes: bool = False, *,
         guard: Callable[[str], Any] = check_read_only) -> tuple[str, dict[str, Any]]:
    """Replace ${name} with bound parameters (or escaped text inside quotes); the guard runs first."""
    guard(REFERENCE.sub("0", sql))
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

    def __init__(self, config: dict, timeout_seconds: float = 30, *, read_only: bool = True):
        self.config = config
        self.kind = config.get("engine") or "url"
        self.timeout = max(1, math.ceil(timeout_seconds))
        # A write engine is separate: the read engine's sessions stay read-only where the database allows it.
        self.read_only = read_only
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

            uri = target.resolve().as_uri() + ("?mode=ro" if self.read_only else "?mode=rw")
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
            elif backend == "mysql" and self.read_only:
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
        if self.read_only and name in {"postgresql", "oracle"}:
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

    def execute(self, sql: str, lookup: Callable[[str], Any], max_rows: int, *, on_zero: str = "error") -> dict:
        """One allowed write in its own transaction; too many or no changed rows roll it back."""
        import sqlalchemy as sa

        if self.read_only:
            raise WorkflowError("Bu veritabanı bağlantısı yalnız okuma için açıldı.")
        if not self.config.get("allow_write"):
            raise WorkflowError("Bu bağlantıda kayıt değiştirme izni kapalı. Ayarlar → Bağlantılar'da veritabanı "
                                "bağlantısını açıp Kayıt değiştirmeye izin ver seçeneğini ve tabloları belirleyin.")
        if not isinstance(sql, str) or not sql.strip():
            raise WorkflowError("SQL komutunu yazın.")
        if len(sql) > QUERY_LIMIT:
            raise WorkflowError("SQL komutu çok uzun.")
        targets = list(self.config.get("write_targets") or [])
        kind, target = check_write(REFERENCE.sub("0", sql), targets)
        engine = self.engine()
        statement, values = bind(sql, lookup, backslash_escapes=engine.dialect.name == "mysql",
                                 guard=lambda text: check_write(text, targets))
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                result = connection.execute(sa.text(statement), values)
                affected = result.rowcount if isinstance(result.rowcount, int) and result.rowcount >= 0 else None
                rows = records(list(result.keys()), iter(result.fetchmany(1001))) if result.returns_rows else []
                if affected is not None and affected > max_rows:
                    raise WorkflowError(f"Komut {affected} satırı değiştirecekti; sınır {max_rows}. Değişiklik geri "
                                        "alındı, hiçbir kayıt değişmedi.")
                if affected == 0 and on_zero == "error":
                    raise WorkflowError("Hiçbir satır değişmedi (koşula uyan kayıt yok). Akış durduruldu.")
                transaction.commit()
            except BaseException:
                transaction.rollback()
                raise
        return {"statement": kind, "target": target, "affected": affected, "rows": rows[:1000]}

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
