import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    with TestClient(app) as c:  # context manager runs startup (seeds Welcome)
        yield c


def test_welcome_note_seeded_once(client):
    notes = client.get("/api/notes").json()
    assert [n["title"] for n in notes] == ["Welcome to Reinterpret"]


def test_note_crud(client):
    n = client.post("/api/notes", json={"title": "a"}).json()
    got = client.patch(f"/api/notes/{n['id']}", json={"title": "b", "body_json": '{"x":1}'}).json()
    assert (got["title"], got["body_json"]) == ("b", '{"x":1}')
    assert client.delete(f"/api/notes/{n['id']}").status_code == 204
    assert client.get(f"/api/notes/{n['id']}").status_code == 404


def test_note_patch_can_clear_folder(client):
    f = client.post("/api/folders", json={"name": "f"}).json()
    n = client.post("/api/notes", json={"folder_id": f["id"]}).json()
    assert client.patch(f"/api/notes/{n['id']}", json={"folder_id": None}).json()["folder_id"] is None


def test_deleting_folder_keeps_notes(client):
    f = client.post("/api/folders", json={"name": "f"}).json()
    n = client.post("/api/notes", json={"folder_id": f["id"]}).json()
    client.delete(f"/api/folders/{f['id']}")
    assert client.get(f"/api/notes/{n['id']}").json()["folder_id"] is None


def test_rename_folder(client):
    f = client.post("/api/folders", json={"name": "f"}).json()
    assert client.patch(f"/api/folders/{f['id']}", json={"name": "g"}).json()["name"] == "g"


def test_db_connection_usable_from_another_thread(tmp_path, monkeypatch):
    # FastAPI opens the connection in one worker thread and runs the endpoint in another
    from concurrent.futures import ThreadPoolExecutor

    from app.main import get_db

    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    gen = get_db()
    conn = next(gen)
    with ThreadPoolExecutor(1) as ex:
        assert ex.submit(lambda: conn.execute("SELECT 1").fetchone()[0]).result() == 1
    gen.close()
