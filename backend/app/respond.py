import json
from typing import Optional

from pydantic import BaseModel, ValidationError

from .llm import LLMError, Provider

AI_NAME = "Reinterpret"  # change here if the AI gets another name

SYSTEM = f"""You are {AI_NAME}, a thinking partner inside a notebook. The user writes; you read along and speak in the margin.

Rules:
- Ask questions that push back: find the claim that is weak, vague or missing a reason, and ask about it.
- Never rewrite the user's text. Never hand over the full answer.
- Be short: one or two sentences, plain words.

Reply with JSON only, no other text:
{{"anchor_quote": "<exact words copied from the note that your question is about>", "text": "<your margin note>"}}"""


class Reply(BaseModel):
    anchor_quote: str = ""
    text: str


def note_text(body_json: str) -> str:
    """Plain text of a TipTap document: one line per block."""
    try:
        doc = json.loads(body_json)
    except ValueError:
        return ""
    out: list[str] = []

    def walk(n: dict):
        if n.get("type") == "text":
            out.append(n.get("text", ""))
            return
        for c in n.get("content", []):
            walk(c)
        if n.get("type") != "doc":
            out.append("\n")

    if isinstance(doc, dict):
        walk(doc)
    return "".join(out).strip()


def parse_reply(raw: str) -> Optional[Reply]:
    """The model is told to return bare JSON but may wrap it in a fence or chatter."""
    a, b = raw.find("{"), raw.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        r = Reply.model_validate(json.loads(raw[a : b + 1]))
    except (ValueError, ValidationError):
        return None
    return r if r.text.strip() else None


def ask(provider: Provider, title: str, text: str, selection: Optional[str]) -> Reply:
    content = f"Note title: {title or 'Untitled'}\n\nNote:\n{text}"
    if selection:
        content += f"\n\nThe user selected this part and wants your question on it:\n{selection}"
    reply = parse_reply(provider.complete(SYSTEM, [{"role": "user", "content": content}]))
    if not reply:
        raise LLMError("The model's reply could not be read. Try again.")
    # keep the anchor only if it really is in the note; otherwise fall back to the selection
    if reply.anchor_quote not in text:
        reply.anchor_quote = selection or ""
    return reply
