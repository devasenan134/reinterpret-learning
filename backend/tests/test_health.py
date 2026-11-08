from fastapi.testclient import TestClient

from app.db import connect
from app.main import app


def test_health(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    assert TestClient(app).get("/api/health").json() == {"ok": True}


def test_schema_has_core_tables(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"folders", "lenses", "notes", "threads", "messages", "settings"} <= names
