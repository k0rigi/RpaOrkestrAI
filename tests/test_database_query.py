"""Veritabanı sorgusu: read-only SELECT with bound flow values, on SQLite for real and the other drivers by URL."""

import platform
import sqlite3
import sys
import threading
import types
from decimal import Decimal

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.connections import Connections
from rpa_orkestrai.database.query import QueryDatabase, bind, check_read_only, plain
from rpa_orkestrai.engine import Executor, WorkflowError, validate_workflow
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "Şirket verisi" / "erp.db"
    path.parent.mkdir()
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE faturalar (no TEXT, musteri TEXT, tutar NUMERIC, durum TEXT);
            INSERT INTO faturalar VALUES ('F-1', 'Çağrı Şule', 120.5, 'Bekliyor');
            INSERT INTO faturalar VALUES ('F-2', 'O''Brien', 80, 'Tamam');
            INSERT INTO faturalar VALUES ('F-3', 'Ege Üretim', 300, 'Bekliyor');
        """)
    connection.close()
    return path


@pytest.fixture
def runner(tmp_path, database):
    settings = Settings(tmp_path / "data", dotenv=False)
    store = Store(settings.data_dir)
    run = Run(workflow_id="0" * 32, workflow_name="Test", department="Genel")
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))
    executor.connections.create({"name": "ERP", "type": "database",
                                 "config": {"engine": "sqlite", "path": str(database)}})
    return executor


def query(runner, sql, before=(), **params):
    steps = [*before, Step(action="database.query", params={"query": sql, "output": "rows", **params})]
    workflow = Workflow(steps=steps)
    validate_workflow(workflow)
    runner.execute(workflow)
    return runner.variables["rows"]


# ----- read-only guard --------------------------------------------------------------------------
@pytest.mark.parametrize("sql", [
    "SELECT * FROM faturalar",
    "  select no from faturalar;  ",
    "WITH b AS (SELECT * FROM faturalar) SELECT * FROM b",
    "(SELECT 1)",
    "SELECT UPDATE_DATE, DELETED FROM t WHERE ad = 'insert into; drop table' -- update\n",
    'SELECT "Update" FROM [Delete] /* exec */',
])
def test_a_single_select_is_allowed(sql):
    check_read_only(sql)


@pytest.mark.parametrize("sql, word", [
    ("DELETE FROM faturalar", None),
    ("UPDATE faturalar SET durum = 'x'", None),
    ("SELECT 1; DROP TABLE faturalar", "Tek bir sorgu"),
    ("WITH x AS (SELECT 1) DELETE FROM faturalar", "DELETE"),
    ("SELECT * INTO yedek FROM faturalar", "INTO"),
    ("SELECT * FROM faturalar WITH (UPDLOCK) FOR UPDATE", "UPDATE"),
    ("SELECT * FROM OPENROWSET('SQLNCLI', 'x', 'y')", "OPENROWSET"),
    ("EXEC sp_who", None),
])
def test_writes_and_several_statements_are_refused(sql, word):
    with pytest.raises(WorkflowError) as caught:
        check_read_only(sql)
    assert word is None or word in str(caught.value)


# ----- flow values are bound, never pasted into SQL -------------------------------------------------
def test_values_become_parameters_lists_expand_and_quoted_values_are_escaped():
    values = {"durum": "Bekliyor", "kodlar": ["F-1", "F-3"], "ad": "O'Brien", "n": 5}
    statement, bound = bind("SELECT * FROM t WHERE durum = ${durum} AND no IN (${kodlar}) "
                            "AND ad LIKE '%${ad}%' AND x > ${n} AND saat = '12:30' AND y = a::int -- :not",
                            values.__getitem__)
    assert statement == ("SELECT * FROM t WHERE durum = :p0 AND no IN (:p1, :p2) AND ad LIKE '%O''Brien%' "
                         "AND x > :p3 AND saat = '12:30' AND y = a::int -- \\:not")
    assert bound == {"p0": "Bekliyor", "p1": "F-1", "p2": "F-3", "p3": 5}
    # MySQL also treats a backslash as an escape inside quotes.
    statement, _ = bind("SELECT * FROM t WHERE ad = '${ad}'", lambda name: "a\\' OR 1=1 --", backslash_escapes=True)
    assert statement == "SELECT * FROM t WHERE ad = 'a\\\\'' OR 1=1 --'"
    with pytest.raises(WorkflowError, match="liste boş"):
        bind("SELECT * FROM t WHERE no IN (${x})", lambda name: [])
    with pytest.raises(WorkflowError, match="kayıt"):
        bind("SELECT * FROM t WHERE no = ${x}", lambda name: {"a": 1})


def test_database_values_become_flow_values():
    from datetime import date, datetime

    assert plain(Decimal("12.50")) == 12.5 and plain(Decimal("3")) == 3 and type(plain(Decimal("3"))) is int
    assert plain(datetime(2026, 10, 5, 9, 30)) == "2026-10-05 09:30:00" and plain(date(2026, 1, 2)) == "2026-01-02"
    assert plain(b"\x01\xff") == "01ff" and plain(None) is None


# ----- a real query in a flow ----------------------------------------------------------------------
def test_a_query_reads_rows_with_values_from_the_flow(runner):
    rows = query(runner, "SELECT no, musteri, tutar FROM faturalar WHERE durum = ${durum} ORDER BY no",
                 before=[Step(action="core.set", params={"name": "durum", "value": "Bekliyor"})])
    assert rows == [{"no": "F-1", "musteri": "Çağrı Şule", "tutar": 120.5},
                    {"no": "F-3", "musteri": "Ege Üretim", "tutar": 300}]


def test_a_quote_in_a_value_cannot_change_the_query(runner):
    before = [Step(action="core.set", params={"name": "ad", "value": "x' OR '1'='1"})]
    assert query(runner, "SELECT no FROM faturalar WHERE musteri = ${ad}", before) == []
    assert query(runner, "SELECT no FROM faturalar WHERE musteri LIKE '%${ad}%'", before) == []
    before = [Step(action="core.set", params={"name": "ad", "value": "O'Brien"})]
    assert query(runner, "SELECT no FROM faturalar WHERE musteri = '${ad}'", before) == [{"no": "F-2"}]


def test_the_row_limit_keeps_the_first_rows_and_warns(runner):
    rows = query(runner, "SELECT no FROM faturalar ORDER BY no", max_rows=2)
    assert rows == [{"no": "F-1"}, {"no": "F-2"}]
    assert any("sınır 2" in event.message and event.level == "warning" for event in runner.run.events)


def test_the_database_file_is_opened_read_only(runner, database):
    # Even past the text check (here called directly), SQLite refuses to write.
    reader = QueryDatabase({"engine": "sqlite", "path": str(database)})
    with pytest.raises(Exception, match="readonly|read-only"), reader.engine().connect() as connection:
        connection.exec_driver_sql("DELETE FROM faturalar")
    reader.close()
    with pytest.raises(WorkflowError, match="yalnız okuma"):
        query(runner, "DELETE FROM faturalar")
    assert len(query(runner, "SELECT * FROM faturalar")) == 3


def test_a_query_can_feed_a_loop(runner):
    loop = Step(action="control.for_each", params={"items": "${rows}", "item_name": "row"},
                children=[Step(action="data.append", params={"name": "nolar", "value": "${row.no}"})])
    runner.execute(Workflow(steps=[
        Step(action="database.query", params={"query": "SELECT no FROM faturalar ORDER BY no", "output": "rows"}),
        loop]))
    assert runner.variables["nolar"] == ["F-1", "F-2", "F-3"]


def test_a_missing_file_or_connection_says_what_to_do(tmp_path, runner):
    runner.connections.update(runner.connections.list()[0]["id"], {"config": {"engine": "sqlite",
                                                                              "path": str(tmp_path / "yok.db")}})
    with pytest.raises(WorkflowError, match="SQLite dosyası bulunamadı"):
        query(runner, "SELECT 1")


# ----- connections: a form instead of an address ----------------------------------------------------
def test_a_database_connection_keeps_the_password_out_of_the_page_and_logs(tmp_path):
    connections = Connections(tmp_path)
    created = connections.create({"name": "Canias", "type": "database", "config": {
        "engine": "mssql", "host": "SUNUCU\\SQLEXPRESS", "database": "CANIAS", "user": "rpa", "password": "Çok-gizli1"}})
    assert created["ready"] and created["engine_label"] == "SQL Server" and created["has_password"]
    assert "Çok-gizli1" not in str(connections.list())
    assert "Çok-gizli1" in connections.secrets()
    # A blank password keeps the stored one; a new engine without one clears it.
    connections.update(created["id"], {"config": {"engine": "mssql", "host": "SUNUCU", "password": ""}})
    assert connections.get(created["id"])["config"]["password"] == "Çok-gizli1"
    connections.update(created["id"], {"config": {"engine": "postgresql", "password": ""}})
    assert connections.get(created["id"])["config"]["password"] == ""
    with pytest.raises(ValueError, match="Port"):
        connections.update(created["id"], {"config": {"engine": "postgresql", "port": "99999"}})


def test_each_engine_uses_a_bundled_driver(monkeypatch):
    base = {"host": "db", "database": "erp", "user": "rpa", "password": "p@ss:w/rd"}
    url = QueryDatabase({**base, "engine": "postgresql"}).url()
    assert (url.drivername, url.port, url.password) == ("postgresql+psycopg", 5432, "p@ss:w/rd")
    url = QueryDatabase({**base, "engine": "mysql", "port": "3307"}).url()
    assert (url.drivername, url.port, url.query["charset"]) == ("mysql+pymysql", 3307, "utf8mb4")
    url = QueryDatabase({**base, "engine": "oracle"}).url()
    assert (url.drivername, url.port, url.query["service_name"]) == ("oracle+oracledb", 1521, "erp")
    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(
        drivers=lambda: ["SQL Server", "ODBC Driver 18 for SQL Server"]))
    for system, driver in (("Windows", "mssql+pyodbc"), ("Darwin", "mssql+pymssql")):
        monkeypatch.setattr(platform, "system", lambda system=system: system)
        url = QueryDatabase({**base, "engine": "mssql", "host": "SUNUCU\\SQLEXPRESS"}).url()
        assert url.drivername == driver and url.host == "SUNUCU\\SQLEXPRESS" and url.port is None
    assert url.drivername == "mssql+pymssql"
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    url = QueryDatabase({**base, "engine": "mssql"}).url()
    assert url.query == {"driver": "ODBC Driver 18 for SQL Server", "TrustServerCertificate": "yes"} and url.port == 1433
    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(drivers=lambda: []))
    with pytest.raises(WorkflowError, match="ODBC Driver 18"):
        QueryDatabase({**base, "engine": "mssql"}).url()


def test_the_drivers_of_this_platform_load():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    sql_server = "mssql+pyodbc" if platform.system() == "Windows" else "mssql+pymssql"
    for scheme in ("postgresql+psycopg", sql_server, "mysql+pymysql", "oracle+oracledb"):
        sqlalchemy.create_engine(f"{scheme}://kullanici:sifre@localhost/veritabani").dispose()


def test_studio_tests_a_connection(tmp_path, database):
    from fastapi.testclient import TestClient

    from rpa_orkestrai.app import create_app

    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        ok = client.post("/api/connections/test", json={"type": "database", "config": {
            "engine": "sqlite", "path": str(database)}})
        assert ok.status_code == 200 and ok.json()["message"] == "Veritabanına bağlanıldı."
        missing = client.post("/api/connections/test", json={"type": "database", "config": {"engine": "mssql"}})
        assert missing.status_code == 422 and "Sunucu" in missing.json()["detail"]


def test_the_step_is_in_the_library_with_its_own_category():
    from rpa_orkestrai.catalog import BY_TYPE, library_catalog

    spec = next(item for item in library_catalog() if item["type"] == "database.query")
    assert spec["category"] == "Veritabanı" and spec["guide"]["how"]
    assert {field["name"]: field.get("raw") for field in spec["fields"]}["query"] is True
    assert "database.read" not in {item["type"] for item in library_catalog()} and "database.read" in BY_TYPE
