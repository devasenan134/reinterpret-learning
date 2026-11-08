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
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


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
    assert parse_reply('{"text": "  "}') is None


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
