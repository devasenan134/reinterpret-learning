"""LLM adapter. Providers take a system prompt and chat messages, return the reply text."""
import os
from typing import Protocol

import anthropic
import httpx2 as httpx


class LLMError(Exception):
    """Anything that stops us getting a usable reply. The message is safe to show the user."""


class Provider(Protocol):
    def complete(self, system: str, messages: list[dict]) -> str: ...


class AnthropicProvider:
    def __init__(self, model: str, api_key: str = "", effort: str = "", client=None):
        self.model = model
        self.effort = effort
        # no key given -> the SDK looks in ANTHROPIC_API_KEY / `ant auth login` itself
        self.client = client or anthropic.Anthropic(**({"api_key": api_key} if api_key else {}))

    def complete(self, system: str, messages: list[dict]) -> str:
        extra = {"output_config": {"effort": self.effort}} if self.effort else {}
        try:
            r = self.client.messages.create(
                model=self.model, max_tokens=8000, system=system, messages=messages, **extra
            )
        except anthropic.AnthropicError as e:
            raise LLMError(f"Claude request failed: {e}") from e
        if r.stop_reason == "refusal":
            raise LLMError("The model declined to answer this one.")
        text = "".join(b.text for b in r.content if b.type == "text")  # skips thinking blocks
        if not text.strip():
            raise LLMError("The model returned no text.")
        return text


class OpenAICompatProvider:
    """OpenAI, Ollama (http://localhost:11434/v1) or any /chat/completions server."""

    def __init__(self, model: str, base_url: str = "", api_key: str = "", client=None):
        self.model = model
        self.url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = client or httpx.Client(timeout=120)

    def complete(self, system: str, messages: list[dict]) -> str:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, *messages]}
        try:
            r = self.client.post(self.url, json=body, headers=self.headers)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM request failed: {e}") from e


def get_provider() -> Provider:
    kind = os.environ.get("LLM_PROVIDER", "anthropic")
    model = os.environ.get("LLM_MODEL", "")
    key = os.environ.get("LLM_API_KEY", "")
    if kind == "anthropic":
        # claude-opus-5-5 is the default; a cheaper model is a one-line change in .env
        return AnthropicProvider(model or "claude-opus-5-5", key, os.environ.get("LLM_EFFORT", ""))
    if kind == "openai_compat":
        if not model:
            raise LLMError("Set LLM_MODEL in .env for the openai_compat provider.")
        return OpenAICompatProvider(model, os.environ.get("LLM_BASE_URL", ""), key)
    raise LLMError(f"Unknown LLM_PROVIDER '{kind}'. Use anthropic or openai_compat.")
