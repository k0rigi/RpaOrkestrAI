from contextlib import closing
from unittest.mock import MagicMock

import pandas as pd
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mssql, postgresql

from rpa_orkestrai.database import ReadOnlyDatabase


def test_identifiers_and_allowlist_block_sql_input_before_connecting():
    with pytest.raises(ValueError):
        ReadOnlyDatabase("postgresql://localhost/db", {"items; DROP TABLE items": None})
    reader = ReadOnlyDatabase("postgresql://localhost/db", {"public.items": ["id", "name"]})
    with pytest.raises(PermissionError):
        reader.read_table("other.items")
    with pytest.raises(ValueError):
        reader.read_table("public.items", limit=reader.max_rows + 1)
    assert reader._engine is None


@pytest.mark.parametrize("dialect", [postgresql.dialect(), mssql.dialect()])
def test_queries_bind_values_and_only_project_permitted_columns(dialect):
    reader = ReadOnlyDatabase("postgresql://localhost/db", {"public.items": ["id", "name"]})
    malicious = "x'; DELETE FROM items; --"
    statement = reader._statement(None, "public.items", ["name"], {"name": malicious}, 25)
    compiled = statement.compile(dialect=dialect)
    assert malicious not in str(compiled)
    assert malicious in compiled.params.values()
    assert 25 in compiled.params.values()
    with pytest.raises(PermissionError):
        reader._statement(None, "public.items", ["secret"], None, None)
    with pytest.raises(PermissionError):
        reader._statement(None, "public.items", None, {"secret": "value"}, None)
    with pytest.raises(ValueError):
        reader._statement(None, "public.items", None, {"name": sa.text("NOW()")}, None)


@pytest.fixture
def sqlite_reader():
    # Inject only in tests to execute the generated SQL without a live server.
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE items (id INTEGER, name TEXT)")
        connection.execute(sa.text("INSERT INTO items (id, name) VALUES (:id, :name)"), [
            {"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}, {"id": 3, "name": None},
        ])
    reader = ReadOnlyDatabase("postgresql://localhost/db", {"items": ["id", "name"]}, max_rows=2)
    reader._engine = engine
    yield reader
    reader.close()


def test_reads_dataframe_with_bound_filters_nulls_and_cap(sqlite_reader):
    result = sqlite_reader.read_table("items", filters={"name": ["beta", None]})
    assert isinstance(result, pd.DataFrame)
    assert result["id"].tolist() == [2, 3]
    assert len(sqlite_reader.read_table("items")) == 2
    assert sqlite_reader.read_table("items", filters={"name": []}).empty
    assert sqlite_reader.read_table("items", filters={"name": None})["id"].tolist() == [3]


def test_chunks_release_connection_on_early_close(sqlite_reader):
    closed = []
    sa.event.listen(sqlite_reader._engine, "checkin", lambda *args: closed.append(True))
    with closing(sqlite_reader.iter_table("items", chunk_size=1)) as chunks:
        assert next(chunks)["id"].tolist() == [1]
        assert not closed
    assert closed == [True]


def test_postgresql_readonly_transaction_always_rolls_back():
    reader = ReadOnlyDatabase("postgresql://localhost/db", {"items": ["id"]})
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    reader._engine = engine
    connection = engine.connect.return_value.__enter__.return_value
    transaction = connection.begin.return_value
    with pytest.raises(RuntimeError), reader._connection():
        raise RuntimeError("read failed")
    connection.exec_driver_sql.assert_called_once_with("SET TRANSACTION READ ONLY")
    transaction.rollback.assert_called_once()
    engine.connect.return_value.__exit__.assert_called_once()


def test_unsupported_backend_is_rejected():
    reader = ReadOnlyDatabase("sqlite:///data.db", {"items": ["id"]})
    with pytest.raises(ValueError, match="PostgreSQL"):
        reader._get_engine()
