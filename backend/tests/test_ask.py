import json
from types import SimpleNamespace as NS

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.llm import AnthropicProvider, LLMError, OpenAICompatProvider, get_provider
from app.main import app, get_llm
from app.respond import note_text, parse_reply


def doc(*paras):
    return json.dumps({"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paras]})


class Fake:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def complete(self, system, messages):
        self.calls.append((system, messages))
        r = self.reply.pop(0) if isinstance(self.reply, list) else self.reply  # a list answers one call at a time
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def note_with(client, *paras):
    n = client.post("/api/notes", json={"title": "t"}).json()
    client.patch(f"/api/notes/{n['id']}", json={"body_json": doc(*paras)})
    return n["id"]


def use(fake):
    app.dependency_overrides[get_llm] = lambda: fake


# ---- text and reply parsing ----

def test_note_text_one_line_per_block():
    assert note_text(doc("a b", "c")) == "a b\nc"
    assert note_text("{}") == "" and note_text("nope") == ""


def test_parse_reply_handles_fences_and_junk():
    ok = '```json\n{"anchor_quote": "x", "text": "why?"}\n```'
    assert parse_reply(ok).text == "why?"
    assert parse_reply("no json here") is None
    assert parse_reply('{"anchor_quote": "x"}') is None  # no text
    assert parse_reply('{"text": "  "}').text.strip() == ""  # ask() decides what blank means


# ---- endpoint ----

def test_ask_saves_thread_with_anchor(client):
    nid = note_with(client, "We drop onboarding emails.", "Nobody reads them.")
    fake = Fake('{"anchor_quote": "Nobody reads them.", "text": "How do you know?"}')
    use(fake)
    r = client.post(f"/api/notes/{nid}/ask", json={})
    assert r.status_code == 201
    t = r.json()
    assert t["anchor_quote"] == "Nobody reads them." and t["messages"][0]["text"] == "How do you know?"
    assert "Nobody reads them." in fake.calls[0][1][0]["content"]
    assert client.get(f"/api/notes/{nid}/threads").json()[0]["id"] == t["id"]


def test_bad_anchor_falls_back_to_selection(client):
    nid = note_with(client, "Alpha beta.")
    use(Fake('{"anchor_quote": "made up", "text": "q?"}'))
    t = client.post(f"/api/notes/{nid}/ask", json={"selection": "Alpha"}).json()
    assert t["anchor_quote"] == "Alpha"


def test_ask_empty_note_is_400(client):
    nid = client.post("/api/notes", json={}).json()["id"]
    use(Fake("unused"))
    assert client.post(f"/api/notes/{nid}/ask", json={}).status_code == 400


def test_unreadable_reply_is_502_and_saves_nothing(client):
    nid = note_with(client, "hello")
    use(Fake("sorry, no json"))
    assert client.post(f"/api/notes/{nid}/ask", json={}).status_code == 502
    assert client.get(f"/api/notes/{nid}/threads").json() == []


def test_provider_error_is_502(client):
    nid = note_with(client, "hello")
    use(Fake(LLMError("boom")))
    r = client.post(f"/api/notes/{nid}/ask", json={})
    assert r.status_code == 502 and r.json()["detail"] == "boom"


def test_missing_config_is_503(client, monkeypatch):
    nid = note_with(client, "hello")
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_MODEL", "")
    r = client.post(f"/api/notes/{nid}/ask", json={})
    assert r.status_code == 503 and "LLM_MODEL" in r.json()["detail"]


# ---- providers ----

def test_get_provider_picks_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_MODEL", "llama3")
    assert isinstance(get_provider(), OpenAICompatProvider)
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(LLMError):
        get_provider()


def test_openai_compat_request_and_reply():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers.get("authorization"), json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    p = OpenAICompatProvider("m", "http://x/v1/", "k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert p.complete("sys", [{"role": "user", "content": "u"}]) == "hi"
    assert seen["url"] == "http://x/v1/chat/completions" and seen["auth"] == "Bearer k"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_openai_compat_http_error_becomes_llmerror():
    p = OpenAICompatProvider("m", "http://x", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(LLMError):
        p.complete("s", [])


def stub_claude(content, stop="end_turn"):
    calls = []

    def create(**kw):
        calls.append(kw)
        return NS(content=content, stop_reason=stop)

    return NS(messages=NS(create=create)), calls


def test_anthropic_skips_thinking_blocks_and_sends_effort():
    c, calls = stub_claude([NS(type="thinking", text=""), NS(type="text", text="the reply")])
    assert AnthropicProvider("claude-x", effort="low", client=c).complete("s", []) == "the reply"
    assert calls[0]["output_config"] == {"effort": "low"} and calls[0]["model"] == "claude-x"


def test_anthropic_refusal_and_empty_are_errors():
    for stop, content in [("refusal", []), ("end_turn", [NS(type="thinking", text="")])]:
        c, _ = stub_claude(content, stop)
        with pytest.raises(LLMError):
            AnthropicProvider("m", client=c).complete("s", [])


def test_anthropic_without_credentials_says_what_to_do():
    def create(**kw):  # what the SDK raises when no key is configured
        raise TypeError("Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set.")

    with pytest.raises(LLMError, match="LLM_API_KEY"):
        AnthropicProvider("m", client=NS(messages=NS(create=create))).complete("s", [])


def test_anthropic_other_typeerrors_are_not_hidden():
    def create(**kw):
        raise TypeError("a real bug")

    with pytest.raises(TypeError):
        AnthropicProvider("m", client=NS(messages=NS(create=create))).complete("s", [])


def test_openai_compat_drops_qwen_think_blocks():
    body = {"choices": [{"message": {"content": '<think>maybe {"text": "x"} first</think>\n{"anchor_quote": "", "text": "why?"}'}}]}
    p = OpenAICompatProvider("m", "http://x", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))))
    assert parse_reply(p.complete("s", [])).text == "why?"


# ---- milestone 3: modes, idle trigger, replies, thread status ----

Q = '{"anchor_quote": "Nobody reads them.", "text": "How do you know?"}'


def start_thread(client):
    nid = note_with(client, "We drop emails. Nobody reads them.")
    use(Fake(Q))
    tid = client.post(f"/api/notes/{nid}/ask", json={}).json()["id"]
    return nid, tid


def test_note_mode_patch_and_bad_values(client):
    nid = client.post("/api/notes", json={}).json()["id"]
    assert client.get(f"/api/notes/{nid}").json()["mode"] == "reads_along"
    assert client.patch(f"/api/notes/{nid}", json={"mode": "on_request"}).json()["mode"] == "on_request"
    assert client.patch(f"/api/notes/{nid}", json={"mode": "nope"}).status_code == 422
    # a null title or mode must not wipe the column (they are NOT NULL)
    assert client.patch(f"/api/notes/{nid}", json={"title": None, "mode": None}).status_code == 200


def test_idle_is_rejected_when_note_waits_to_be_asked(client):
    nid = note_with(client, "Some claim.")
    client.patch(f"/api/notes/{nid}", json={"mode": "on_request"})
    fake = Fake(Q)
    use(fake)
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 409
    assert fake.calls == []  # the model was never called
    assert client.post(f"/api/notes/{nid}/ask", json={}).status_code == 201  # explicit ask still works


def test_idle_speaks_up_and_knows_what_was_raised(client):
    nid, _ = start_thread(client)
    fake = Fake(["YES", '{"anchor_quote": "", "text": "Second point?"}'])
    use(fake)
    r = client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"})
    assert r.status_code == 201
    system, msgs = fake.calls[1]  # call 0 is the yes/no gate
    assert "without being asked" in system
    assert "Already raised" in msgs[0]["content"] and "Nobody reads them." in msgs[0]["content"]


def test_idle_can_stay_quiet_but_explicit_ask_cannot(client):
    nid = note_with(client, "All fine here.")
    use(Fake(["YES", '{"anchor_quote": "", "text": ""}']))  # gate says speak, model has nothing
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 204
    assert client.get(f"/api/notes/{nid}/threads").json() == []
    use(Fake('{"anchor_quote": "", "text": ""}'))  # same reply, but asked by hand: not allowed to be empty
    assert client.post(f"/api/notes/{nid}/ask", json={}).status_code == 502


def test_idle_on_empty_note_skips_the_model(client):
    nid = client.post("/api/notes", json={}).json()["id"]
    fake = Fake(Q)
    use(fake)
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 204
    assert fake.calls == []


def test_reply_continues_the_thread(client):
    _, tid = start_thread(client)
    fake = Fake("Fair. What would change your mind?")
    use(fake)
    t = client.post(f"/api/threads/{tid}/reply", json={"text": "  Our open rate is 30%. "}).json()
    assert [(m["role"], m["text"]) for m in t["messages"]][1:] == [("user", "Our open rate is 30%."), ("ai", "Fair. What would change your mind?")]
    roles = [m["role"] for m in fake.calls[0][1]]
    assert roles == ["user", "assistant", "user"]  # providers need alternating turns


def test_failed_reply_saves_nothing(client):
    _, tid = start_thread(client)
    use(Fake(LLMError("down")))
    assert client.post(f"/api/threads/{tid}/reply", json={"text": "hi"}).status_code == 502
    use(Fake("ok"))
    assert len(client.post(f"/api/threads/{tid}/reply", json={"text": "hi"}).json()["messages"]) == 3  # 1 + the retry only


def test_reply_validation_and_closed_thread(client):
    _, tid = start_thread(client)
    use(Fake("ok"))
    assert client.post(f"/api/threads/{tid}/reply", json={"text": "   "}).status_code == 400
    assert client.post(f"/api/threads/{tid}/reply", json={"text": "x" * 4001}).status_code == 400
    client.patch(f"/api/threads/{tid}", json={"status": "resolved"})
    assert client.post(f"/api/threads/{tid}/reply", json={"text": "hi"}).status_code == 409
    assert client.post("/api/threads/999/reply", json={"text": "hi"}).status_code == 404


def test_resolve_reopen_dismiss(client):
    nid, tid = start_thread(client)
    assert client.patch(f"/api/threads/{tid}", json={"status": "resolved"}).json()["status"] == "resolved"
    assert [t["status"] for t in client.get(f"/api/notes/{nid}/threads").json()] == ["resolved"]  # still listed
    client.patch(f"/api/threads/{tid}", json={"status": "open"})
    assert client.patch(f"/api/threads/{tid}", json={"status": "bogus"}).status_code == 422
    client.patch(f"/api/threads/{tid}", json={"status": "dismissed"})
    assert client.get(f"/api/notes/{nid}/threads").json() == []


def test_idle_gate_no_means_one_cheap_call_and_silence(client):
    nid = note_with(client, "Had pasta for dinner.")
    fake = Fake(["no", Q])
    use(fake)
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 204
    assert len(fake.calls) == 1
    assert client.post(f"/api/notes/{nid}/ask", json={}).status_code == 201  # asking by hand skips the gate


def test_idle_never_repeats_a_raised_point(client):
    nid, _ = start_thread(client)  # raised "Nobody reads them."
    use(Fake(["YES", '{"anchor_quote": "Nobody reads them.", "text": "Again?"}']))
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "idle"}).status_code == 204
    assert len(client.get(f"/api/notes/{nid}/threads").json()) == 1


# ---- milestone 4: brief, explain, settings ----

def test_brief_reaches_every_prompt(client):
    nid = note_with(client, "Cats are mammals.")
    client.patch(f"/api/notes/{nid}", json={"instructions": "Be harsh."})
    f = Fake(['{"anchor_quote": "Cats", "text": "Why?"}', "ok", "A cat is a mammal."])
    use(f)
    t = client.post(f"/api/notes/{nid}/ask", json={}).json()
    client.post(f"/api/threads/{t['id']}/reply", json={"text": "because"})
    client.post(f"/api/notes/{nid}/ask", json={"trigger": "explain", "selection": "Cats"})
    assert all("Be harsh." in system for system, _ in f.calls)
    assert client.patch(f"/api/notes/{nid}", json={"instructions": "x" * 1001}).status_code == 422


def test_explain_makes_a_thread_and_needs_a_selection(client):
    nid = note_with(client, "Cats are mammals.")
    use(Fake("A cat is a warm-blooded animal."))
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "explain"}).status_code == 400
    t = client.post(f"/api/notes/{nid}/ask", json={"trigger": "explain", "selection": "mammals"}).json()
    assert t["anchor_quote"] == "mammals" and t["messages"][0]["kind"] == "explanation"
    use(Fake(LLMError("down")))
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "explain", "selection": "x"}).status_code == 502


def test_explain_works_in_on_request_mode(client):
    nid = note_with(client, "Cats.")
    client.patch(f"/api/notes/{nid}", json={"mode": "on_request"})
    use(Fake("fine"))
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "explain", "selection": "Cats"}).status_code == 201


def test_settings_defaults_patch_and_default_mode(client):
    assert client.get("/api/settings").json()["theme"] == "dark"
    s = client.patch("/api/settings", json={"theme": "light", "ai_color": "", "default_mode": "on_request"}).json()
    assert s["theme"] == "light" and s["default_mode"] == "on_request" and s["text_size"] == "16"
    assert client.patch("/api/settings", json={"theme": "pink"}).status_code == 422
    assert client.post("/api/notes", json={}).json()["mode"] == "on_request"  # new notes follow the setting


# ---- milestone 5: diagrams ----

def test_diagram_is_built_by_the_server_and_escaped(client):
    nid = note_with(client, "Light hits a leaf.")
    use(Fake('{"steps": [{"label": "<script>x</script>", "caption": "Light\\narrives"}, {"label": "Leaf", "caption": "It absorbs it."}]}'))
    t = client.post(f"/api/notes/{nid}/ask", json={"trigger": "diagram", "selection": "Light hits a leaf."}).json()
    m = t["messages"][0]
    assert m["kind"] == "diagram" and m["svg"].count('<g class="step">') == 2
    assert "<script" not in m["svg"] and "&lt;script&gt;" in m["svg"]
    assert m["text"].split("\n") == ["Light arrives", "It absorbs it."]  # one caption per step


def test_diagram_needs_selection_and_readable_reply(client):
    nid = note_with(client, "Leaf.")
    use(Fake("not json"))
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "diagram"}).status_code == 400
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "diagram", "selection": "Leaf."}).status_code == 502
    use(Fake('{"steps": [{"label": "only one"}]}'))  # a diagram needs at least two steps
    assert client.post(f"/api/notes/{nid}/ask", json={"trigger": "diagram", "selection": "Leaf."}).status_code == 502
    assert client.get(f"/api/notes/{nid}/threads").json() == []


def test_diagram_caps_steps_at_six(client):
    nid = note_with(client, "x")
    steps = ",".join('{"label": "s%d", "caption": "c"}' % i for i in range(9))
    use(Fake('{"steps": [%s]}' % steps))
    m = client.post(f"/api/notes/{nid}/ask", json={"trigger": "diagram", "selection": "x"}).json()["messages"][0]
    assert m["svg"].count('<g class="step">') == 6
