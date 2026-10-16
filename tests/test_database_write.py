"""Veritabanında değişiklik yap: izinli tabloda tek komut, bağlı parametreler ve geri alınan aşırı değişiklik."""

import sqlite3
import threading

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.database.query import QueryDatabase, check_write
from rpa_orkestrai.engine import Executor, WorkflowError, validate_workflow
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store

TARGETS = ["dbo.faturalar", "faturalar", "dbo.sp_fatura_kapat"]


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "Şirket verisi" / "erp.db"
    path.parent.mkdir()
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE faturalar (no TEXT, tutar NUMERIC, durum TEXT);
            CREATE TABLE kullanicilar (ad TEXT);
            INSERT INTO faturalar VALUES ('F-1', 120, 'Bekliyor');
            INSERT INTO faturalar VALUES ('F-2', 80, 'Bekliyor');
            INSERT INTO faturalar VALUES ('F-3', 300, 'Tamam');
        """)
    connection.close()
    return path


def rows(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT no, tutar, durum FROM faturalar ORDER BY no").fetchall()


@pytest.fixture
def runner(tmp_path, database):
    settings = Settings(tmp_path / "data", dotenv=False)
    store = Store(settings.data_dir)
    run = Run(workflow_id="0" * 32, workflow_name="Test", department="Genel")
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))
    executor.connections.create({"name": "ERP", "type": "database", "config": {
        "engine": "sqlite", "path": str(database), "allow_write": True, "write_targets": "faturalar"}})
    return executor


def write(runner, sql, **params):
    workflow = Workflow(steps=[Step(action="database.execute", params={"query": sql, "output": "sonuc", **params})])
    validate_workflow(workflow)
    runner.execute(workflow)
    return runner.variables["sonuc"]


@pytest.mark.parametrize("sql,kind,target", [
    ("INSERT INTO faturalar (no) VALUES ('F-9')", "INSERT", "faturalar"),
    ("update [dbo].[faturalar] set durum = 'x' where no = 'F-1';", "UPDATE", "dbo.faturalar"),
    ("DELETE FROM dbo.faturalar WHERE no = 'F-1'", "DELETE", "dbo.faturalar"),
    ("MERGE INTO faturalar t USING (SELECT 1 AS a) s ON (1=0) WHEN NOT MATCHED THEN INSERT (no) VALUES ('x')",
     "MERGE", "faturalar"),
    ("EXEC dbo.sp_fatura_kapat @no = 'F-1'", "EXEC", "dbo.sp_fatura_kapat"),
    ("UPDATE faturalar SET not_ = 'drop table x; update' WHERE no = 'F-1' -- DELETE everything", "UPDATE", "faturalar"),
])
def test_allowed_write_statements_name_their_target(sql, kind, target):
    assert check_write(sql, TARGETS) == (kind, target)


@pytest.mark.parametrize("sql,reason", [
    ("UPDATE faturalar SET durum = 'x'", "WHERE"),
    ("DELETE FROM faturalar", "WHERE"),
    ("DROP TABLE faturalar", "DROP"),
    ("UPDATE faturalar SET durum = 'x' WHERE 1=1; DELETE FROM faturalar WHERE 1=1", "Tek bir komut"),
    ("EXEC ('DELETE FROM faturalar')", "dinamik"),
    ("EXEC sp_executesql N'DELETE FROM faturalar'", "SP_EXECUTESQL"),
    ("UPDATE kullanicilar SET ad = 'x' WHERE ad = 'y'", "değiştirilebilecek"),
    ("TRUNCATE TABLE faturalar", "TRUNCATE"),
    ("SELECT * FROM faturalar", "tek bir INSERT"),
    ("UPDATE f SET durum = 'x' FROM faturalar f WHERE f.no = 'F-1'", "değiştirilebilecek"),
    ("EXEC master.dbo.xp_cmdshell 'dir'", "XP_CMDSHELL"),
])
def test_dangerous_or_unlisted_writes_are_refused_before_running(sql, reason):
    with pytest.raises(WorkflowError) as error:
        check_write(sql, TARGETS)
    assert reason.casefold() in str(error.value).casefold()


def test_a_write_changes_one_record_with_bound_values(runner, database):
    runner.variables.update(durum="Kapandı", no="F-1")
    result = write(runner, "UPDATE faturalar SET durum = ${durum} WHERE no = ${no}")
    assert result == {"statement": "UPDATE", "target": "faturalar", "affected": 1, "rows": []}
    assert rows(database)[0] == ("F-1", 120, "Kapandı")
    # A quote in a value stays data; it never becomes part of the command.
    runner.variables.update(durum="x'; DELETE FROM faturalar WHERE '1'='1", no="F-2")
    write(runner, "UPDATE faturalar SET durum = ${durum} WHERE no = ${no}")
    assert len(rows(database)) == 3 and rows(database)[1][2] == "x'; DELETE FROM faturalar WHERE '1'='1"


def test_too_many_changed_rows_roll_back_and_zero_rows_stop_unless_allowed(runner, database):
    before = rows(database)
    with pytest.raises(WorkflowError, match="geri alındı"):
        write(runner, "UPDATE faturalar SET durum = 'Toplu' WHERE durum = 'Bekliyor'", max_rows=1)
    assert rows(database) == before
    with pytest.raises(WorkflowError, match="Hiçbir satır"):
        write(runner, "DELETE FROM faturalar WHERE no = 'YOK'")
    assert write(runner, "DELETE FROM faturalar WHERE no = 'YOK'", on_zero="continue")["affected"] == 0
    assert write(runner, "UPDATE faturalar SET durum = 'Toplu' WHERE durum = 'Bekliyor'", max_rows=5)["affected"] == 2
    assert write(runner, "INSERT INTO faturalar (no, tutar, durum) VALUES ('F-4', 10, 'Yeni')")["affected"] == 1
    assert len(rows(database)) == 4


def test_writing_needs_the_connection_permission_and_the_read_step_stays_read_only(tmp_path, database):
    config = {"engine": "sqlite", "path": str(database), "allow_write": False, "write_targets": ["faturalar"]}
    with QueryDatabase(config, read_only=False) as db:
        with pytest.raises(WorkflowError, match="izni kapalı"):
            db.execute("DELETE FROM faturalar WHERE no = 'F-1'", lambda name: None, 1)
    with QueryDatabase({**config, "allow_write": True}) as db:
        with pytest.raises(WorkflowError, match="yalnız okuma"):
            db.execute("DELETE FROM faturalar WHERE no = 'F-1'", lambda name: None, 1)
    assert len(rows(database)) == 3


def test_connection_requires_targets_when_writing_is_allowed(tmp_path):
    from rpa_orkestrai.connections import Connections

    connections = Connections(tmp_path)
    with pytest.raises(ValueError, match="en az bir tablo"):
        connections.create({"name": "ERP", "type": "database", "config": {"engine": "sqlite", "path": "/x.db",
                                                                          "allow_write": True}})
    with pytest.raises(ValueError, match="şema.ad"):
        connections.create({"name": "ERP", "type": "database", "config": {
            "engine": "sqlite", "path": "/x.db", "allow_write": True, "write_targets": "faturalar; DROP"}})
    created = connections.create({"name": "ERP", "type": "database", "config": {
        "engine": "sqlite", "path": "/x.db", "allow_write": True, "write_targets": "dbo.faturalar, dbo.sp_kapat"}})
    assert created["allow_write"] is True and created["write_targets"] == ["dbo.faturalar", "dbo.sp_kapat"]
