import pytest

from test_ask import Fake, Q, client, note_with, use


LENS = {"name": "Skeptic", "description": "Find weak claims.", "how_it_thinks": "Ask for evidence.", "voice": "blunt", "frequency": "when_it_matters"}


def attach(client, frequency="when_it_matters"):
    lens = client.post("/api/lenses", json={**LENS, "frequency": frequency}).json()
    nid = note_with(client, "Nobody reads them.")
    assert client.patch(f"/api/notes/{nid}", json={"lens_id": lens["id"], "instructions": "Keep it useful."}).status_code == 200
    return nid, lens["id"]


def test_lens_crud_and_note_selection(client):
    assert client.get("/api/lenses").json() == []
    nid, lid = attach(client)
    assert client.get(f"/api/lenses/{lid}").json() == {**LENS, "id": lid}
    assert client.get("/api/lenses").json()[0]["id"] == lid
    updated = {**LENS, "name": "Coach", "voice": "warm"}
    assert client.put(f"/api/lenses/{lid}", json=updated).json() == {**updated, "id": lid}
    assert client.patch(f"/api/notes/{nid}", json={"title": "New title"}).json()["lens_id"] == lid
    assert client.patch(f"/api/notes/{nid}", json={"lens_id": None}).json()["lens_id"] is None
    assert client.patch(f"/api/notes/{nid}", json={"lens_id": 999}).status_code == 404
    assert client.get(f"/api/notes/{nid}").json()["lens_id"] is None
    assert client.delete(f"/api/lenses/{lid}").status_code == 204
    assert client.get(f"/api/lenses/{lid}").status_code == 404
    assert client.put(f"/api/lenses/{lid}", json=LENS).status_code == 404
    assert client.delete(f"/api/lenses/{lid}").status_code == 404


@pytest.mark.parametrize("field,value", [("voice", "loud"), ("frequency", "always"), ("name", " "), ("name", "x" * 81), ("description", "x" * 241), ("how_it_thinks", "x" * 501), ("voice", None)])
def test_lens_validation(client, field, value):
    lid = client.post("/api/lenses", json=LENS).json()["id"]
    for method, url in [(client.post, "/api/lenses"), (client.put, f"/api/lenses/{lid}")]:
        assert method(url, json={**LENS, field: value}).status_code == 422
    assert client.get(f"/api/lenses/{lid}").json()[field] == LENS[field]


def test_lens_and_brief_reach_every_call_and_threads(client):
    nid, lid = attach(client)
    f = Fake([Q, "A reply.", "An explanation.", '{"steps": [{"label": "One"}, {"label": "Two"}]}', "YES", '{"anchor_quote": "", "text": "Another point?"}'])
    use(f)
    thread = client.post(f"/api/notes/{nid}/ask", json={}).json()
    assert thread["lens_id"] == lid
    assert client.post(f"/api/threads/{thread['id']}/reply", json={"text": "Why?"}).status_code == 200
    for trigger in ("explain", "diagram", "idle"):
        r = client.post(f"/api/notes/{nid}/ask", json={"trigger": trigger, "selection": "Nobody"})
        assert r.status_code == 201
        assert r.json()["lens_id"] == lid
    assert len(f.calls) == 6
    for system, _ in f.calls:
        for expected in ("Skeptic", "Find weak claims.", "Ask for evidence.", "blunt", "Keep it useful."):
            assert expected in system


def test_deleting_lens_keeps_notes_threads_and_defaults(client):
    nid, lid = attach(client)
    use(Fake(Q))
    tid = client.post(f"/api/notes/{nid}/ask", json={}).json()["id"]
    assert client.delete(f"/api/lenses/{lid}").status_code == 204
    assert client.get(f"/api/notes/{nid}").json()["lens_id"] is None
    threads = client.get(f"/api/notes/{nid}/threads").json()
    assert threads[0]["id"] == tid and threads[0]["lens_id"] is None
    assert len(threads[0]["messages"]) == 1
    f = Fake("A reply.")
    use(f)
    assert client.post(f"/api/threads/{tid}/reply", json={"text": "And?"}).status_code == 200
    assert "Reviewer:" not in f.calls[0][0]
    assert "Keep it useful." in f.calls[0][0]
    use(Fake(Q))
    assert client.post(f"/api/notes/{nid}/ask", json={}).json()["lens_id"] is None


@pytest.mark.parametrize("frequency,gate", [("rarely", "factual error"), ("when_it_matters", "conclusion or recommendation"), ("often", None)])
def test_frequency_only_changes_idle_gate(client, frequency, gate):
    nid, _ = attach(client, frequency)
    f = Fake(Q if gate is None else ["NO", Q])
    use(f)
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == (201 if gate is None else 204)
    assert len(f.calls) == 1
    if gate:
        assert gate in f.calls[0][0]
    assert client.post(f"/api/notes/{nid}/ask", json={}).status_code == 201
    assert len(f.calls) == 2


def test_often_still_checks_mode_and_repeats(client):
    nid, _ = attach(client, "often")
    f = Fake(Q)
    use(f)
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 201
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 204
    client.patch(f"/api/notes/{nid}", json={"mode": "on_request"})
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 409
    assert len(f.calls) == 2


def test_reply_uses_current_note_lens(client):
    nid, lid = attach(client)
    use(Fake(Q))
    tid = client.post(f"/api/notes/{nid}/ask", json={}).json()["id"]
    other = client.post("/api/lenses", json={**LENS, "name": "Coach"}).json()["id"]
    client.patch(f"/api/notes/{nid}", json={"lens_id": other})
    f = Fake("ok")
    use(f)
    assert client.post(f"/api/threads/{tid}/reply", json={"text": "Hi"}).json()["lens_id"] == lid
    assert "Reviewer: Coach" in f.calls[0][0]


@pytest.mark.parametrize("frequency", ["rarely", "when_it_matters"])
def test_idle_gate_yes_saves_thread(client, frequency):
    nid, lid = attach(client, frequency)
    f = Fake(["YES", Q])
    use(f)
    r = client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"})
    assert r.status_code == 201 and r.json()["lens_id"] == lid
    assert len(f.calls) == 2
