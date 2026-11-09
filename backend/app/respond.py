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


IDLE = """

You are reading along while the user writes, without being asked. Raise the single most important problem. Never repeat a point already raised."""

# Small models can't be told to stay silent, but they answer a yes/no question well. Examples keep it steady.
GATE = """You check notes. Reply with exactly one word, YES or NO.

YES means the note contains (1) a fact that is wrong, or (2) a conclusion or recommendation with no reason or evidence given.
NO means everything in it is either correct, plain description, or a conclusion that has reasons or numbers behind it.

Examples:
Note: I had pasta for dinner and watched a film. -> NO
Note: The Great Wall of China can be seen from the Moon. -> YES
Note: We should move everything to microservices. -> YES
Note: We should stop the weekly report because nobody opened it in the last 12 weeks, according to the logs. -> NO
Note: Water boils at 100 degrees Celsius at sea level. -> NO
Note: Humans only use 10 percent of their brains. -> YES"""

REPLY_SYSTEM = f"""You are {AI_NAME}, a thinking partner inside a notebook. The user is writing back to your margin note.
- If their answer holds up, say so in a few words, and push one step further only if it helps.
- If it does not, push back with one short question.
- Never rewrite their text. Plain words, one or two sentences. Plain text, no JSON."""


EXPLAIN = f"""You are {AI_NAME}, a thinking partner inside a notebook. The user selected part of their note and wants it explained.
Explain what it means in plain words, in two to four short sentences. Add one example only if it helps. If it is wrong, say so plainly.
Plain text, no JSON, no headings."""


def with_brief(system: str, brief: str) -> str:
    return system + (f"\n\nThe user's brief for this note, follow it:\n{brief.strip()}" if brief.strip() else "")


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
    return r


def ask(provider: Provider, title: str, text: str, selection: Optional[str], idle: bool = False, raised: tuple = (), brief: str = "") -> Optional[Reply]:
    """None means stay quiet (only allowed when idle)."""
    # shortcut: an extra model call on every idle pause, drop it if the model is strong enough to stay silent itself
    if idle and not provider.complete(GATE, [{"role": "user", "content": text}]).strip().upper().startswith("YES"):
        return None
    content = f"Note title: {title or 'Untitled'}\n\nNote:\n{text}"
    if selection:
        content += f"\n\nThe user selected this part and wants your question on it:\n{selection}"
    if raised:
        content += "\n\nAlready raised, do not repeat:\n" + "\n".join(f"- {q}" for q in raised if q)
    reply = parse_reply(provider.complete(with_brief(SYSTEM + (IDLE if idle else ""), brief), [{"role": "user", "content": content}]))
    if not reply:
        raise LLMError("The model's reply could not be read. Try again.")
    if not reply.text.strip():
        if idle:
            return None
        raise LLMError("The model had nothing to say. Try again.")
    # the model ignores "do not repeat", so check in code: same sentence as an existing thread -> stay quiet
    if idle and reply.anchor_quote and any(q and (q in reply.anchor_quote or reply.anchor_quote in q) for q in raised):
        return None
    # keep the anchor only if it really is in the note; otherwise fall back to the selection
    if reply.anchor_quote not in text:
        reply.anchor_quote = selection or ""
    return reply


def explain(provider: Provider, title: str, text: str, selection: str, brief: str = "") -> str:
    out = provider.complete(with_brief(EXPLAIN, brief), [{"role": "user", "content": f"Note title: {title or 'Untitled'}\n\nNote:\n{text}\n\nExplain this part:\n{selection}"}]).strip()
    if not out:
        raise LLMError("The model returned no text.")
    return out


def reply(provider: Provider, title: str, text: str, quote: str, messages: list[dict], brief: str = "") -> str:
    """Continue a margin thread. messages are {role: ai|user, text}, ending with the user's new reply."""
    first = f"Note title: {title or 'Untitled'}\n\nNote:\n{text}"
    if quote:
        first += f"\n\nYour margin note was about: {quote}"
    turns = [{"role": "user", "content": first}]
    turns += [{"role": "assistant" if m["role"] == "ai" else "user", "content": m["text"]} for m in messages]
    out = provider.complete(with_brief(REPLY_SYSTEM, brief), turns).strip()
    if not out:
        raise LLMError("The model returned no text.")
    return out
