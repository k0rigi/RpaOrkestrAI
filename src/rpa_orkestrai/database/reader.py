"""DataFrame reads with allowlisted identifiers and bound filter values.

The SQL Server login MUST be provisioned with SELECT-only permissions. There is
no SQL Server equivalent of PostgreSQL's read-only transaction. This adapter
never accepts SQL text; it is an additional guard, not a permissions boundary.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SCALARS = (str, bytes, int, float, bool, date, datetime, Decimal, UUID)


class ReadOnlyDatabase:
    """Lazy SQLAlchemy engine restricted to configured schema/table/columns.

    Example: ``ReadOnlyDatabase(url, {"public.IASSALITEM": ["ID", "MATERIAL"]})``.
    Use schema-qualified table keys in production. ``None`` permits all columns
    of that particular table. Filters support equality, NULL and list-based IN.
    Neither table names nor values are interpolated into SQL strings.

    timeout_seconds bounds pool acquisition, connection establishment and each
    query (not the entire workflow). PostgreSQL uses libpq connect_timeout and
    server statement_timeout; SQL Server uses pyodbc login timeout and the
    DBAPI connection's query timeout. Only psycopg/psycopg2 and pyodbc drivers
    are supported so these limits cannot silently become ineffective.
    """

    def __init__(
        self,
        url: str,
        allowed_tables: Mapping[str, Sequence[str] | None],
        max_rows: int = 10_000,
        *,
        timeout_seconds: float = 30,
        connect_args: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(url, str) or not url:
            raise ValueError("A database connection URL is required.")
        if type(max_rows) is not int or not 1 <= max_rows <= 1_000_000:
            raise ValueError("max_rows must be an integer between 1 and 1,000,000.")
        if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be positive, finite and no greater than 300.")
        if not allowed_tables:
            raise ValueError("At least one allowed table is required.")
        self._url = url
        self.max_rows = max_rows
        self.timeout_seconds = float(timeout_seconds)
        self.allowed_tables: dict[str, tuple[str, ...] | None] = {}
        for table, columns in allowed_tables.items():
            self._split_table(table)
            if columns is not None:
                if isinstance(columns, (str, bytes)) or not columns:
                    raise ValueError("Allowed columns must be a non-empty sequence or None.")
                for column in columns:
                    self._identifier(column)
                if len(set(columns)) != len(columns):
                    raise ValueError("Allowed columns must be unique.")
            self.allowed_tables[table] = tuple(columns) if columns is not None else None
        self._connect_args = dict(connect_args or {})
        self._engine: Any = None

    @staticmethod
    def _identifier(value: str) -> str:
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError("Only simple SQL identifiers are supported.")
        return value

    @classmethod
    def _split_table(cls, value: str) -> tuple[str | None, str]:
        if not isinstance(value, str):
            raise ValueError("Table must be a configured table name.")
        parts = value.split(".")
        if len(parts) not in (1, 2):
            raise ValueError("Use table or schema.table names.")
        for part in parts:
            cls._identifier(part)
        return (parts[0], parts[1]) if len(parts) == 2 else (None, parts[0])

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                import sqlalchemy as sa
            except ImportError as exc:
                raise RuntimeError("Install the database dependencies to read a database.") from exc
            url = sa.engine.make_url(self._url)
            backend = url.get_backend_name()
            if backend not in {"postgresql", "mssql"}:
                raise ValueError("Only PostgreSQL and SQL Server are supported.")
            if url.drivername == "postgresql":
                url = url.set(drivername="postgresql+psycopg")
            driver = url.get_driver_name()
            timeout = math.ceil(self.timeout_seconds)
            connection_options = dict(self._connect_args)
            if backend == "postgresql":
                if driver not in {"psycopg", "psycopg2"}:
                    raise ValueError("PostgreSQL requires the psycopg or psycopg2 driver.")
                connection_options["connect_timeout"] = timeout
                existing_options = connection_options.get("options", url.query.get("options", ""))
                statement_timeout = math.ceil(self.timeout_seconds * 1_000)
                connection_options["options"] = f"{existing_options} -c statement_timeout={statement_timeout}".strip()
            else:
                if driver != "pyodbc":
                    raise ValueError("SQL Server requires the pyodbc driver.")
                connection_options["timeout"] = timeout
            engine = sa.create_engine(
                url, pool_pre_ping=True, hide_parameters=True,
                pool_timeout=self.timeout_seconds, connect_args=connection_options,
            )
            if backend == "mssql":
                def set_query_timeout(dbapi_connection: Any, connection_record: Any) -> None:
                    dbapi_connection.timeout = timeout

                # Run before SQLAlchemy's initial dialect queries as well.
                sa.event.listen(engine, "connect", set_query_timeout, insert=True)
            self._engine = engine
        return self._engine

    @contextmanager
    def _connection(self, *, streaming: bool = False) -> Iterator[Any]:
        engine = self._get_engine()
        with engine.connect() as connection:
            # Always roll back, including successful reads and generator.close().
            transaction = connection.begin()
            try:
                if engine.dialect.name == "postgresql":
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                if streaming:
                    connection = connection.execution_options(stream_results=True)
                yield connection
            finally:
                transaction.rollback()

    def _limit(self, limit: int | None) -> int:
        if limit is None:
            return self.max_rows
        if type(limit) is not int or not 1 <= limit <= self.max_rows:
            raise ValueError(f"limit must be between 1 and {self.max_rows}.")
        return limit

    @staticmethod
    def _validate_value(value: Any) -> None:
        if value is not None and not isinstance(value, _SCALARS):
            raise ValueError("Filters accept scalar values, NULL, or lists of scalar values.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite numeric filters are not supported.")

    def _statement(
        self, connection: Any, table: str, columns: Sequence[str] | None,
        filters: Mapping[str, Any] | None, limit: int | None,
    ) -> Any:
        import sqlalchemy as sa

        if table not in self.allowed_tables:
            raise PermissionError("Table is not present in the database allowlist.")
        row_limit = self._limit(limit)
        schema, name = self._split_table(table)
        permitted = self.allowed_tables[table]
        if permitted is None:
            relation = sa.Table(name, sa.MetaData(), schema=schema, autoload_with=connection)
            permitted = tuple(relation.c.keys())
        else:
            relation = sa.Table(
                name, sa.MetaData(), *(sa.Column(c) for c in permitted), schema=schema,
            )
        selected = tuple(columns) if columns is not None else permitted
        if not selected or isinstance(columns, (str, bytes)):
            raise ValueError("columns must be a non-empty sequence.")
        for column in (*selected, *(filters or {}).keys()):
            self._identifier(column)
            if column not in permitted:
                raise PermissionError("Column is not present in the database allowlist.")
        query = sa.select(*(relation.c[column] for column in selected))
        for key, value in (filters or {}).items():
            column = relation.c[key]
            if isinstance(value, (list, tuple, set, frozenset)):
                if len(value) > 1_000:
                    raise ValueError("An IN filter may contain at most 1,000 values.")
                for item in value:
                    self._validate_value(item)
                non_null = [item for item in value if item is not None]
                predicate = column.in_(non_null)
                if None in value:
                    predicate = sa.or_(predicate, column.is_(None))
            else:
                self._validate_value(value)
                predicate = column.is_(None) if value is None else column == value
            query = query.where(predicate)
        return query.limit(row_limit)

    def read_table(
        self, table: str, columns: Sequence[str] | None = None,
        filters: Mapping[str, Any] | None = None, limit: int | None = None,
    ) -> Any:
        """Return one bounded pandas DataFrame. Never accepts SQL text."""
        if table not in self.allowed_tables:
            raise PermissionError("Table is not present in the database allowlist.")
        self._limit(limit)
        import pandas as pd

        with self._connection() as connection:
            return pd.read_sql_query(self._statement(connection, table, columns, filters, limit), connection)

    def iter_table(
        self, table: str, columns: Sequence[str] | None = None,
        filters: Mapping[str, Any] | None = None, limit: int | None = None,
        *, chunk_size: int = 1_000,
    ) -> Iterator[Any]:
        """Yield DataFrames within max_rows; close the generator on early exit.

        ``with contextlib.closing(db.iter_table(...)) as chunks: ...`` releases
        the connection immediately if a caller stops before reading every chunk.
        """
        if table not in self.allowed_tables:
            raise PermissionError("Table is not present in the database allowlist.")
        self._limit(limit)
        if type(chunk_size) is not int or not 1 <= chunk_size <= self.max_rows:
            raise ValueError("chunk_size must be positive and no greater than max_rows.")
        import pandas as pd

        with self._connection(streaming=True) as connection:
            chunks = pd.read_sql_query(
                self._statement(connection, table, columns, filters, limit), connection,
                chunksize=chunk_size,
            )
            try:
                yield from chunks
            finally:
                close = getattr(chunks, "close", None)
                if close:
                    close()

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> ReadOnlyDatabase:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
