import json
from xml.sax.saxutils import escape

from pydantic import BaseModel, Field, ValidationError

from .llm import LLMError, Provider
from .respond import AI_NAME, with_brief

DIAGRAM = f"""You are {AI_NAME}, a thinking partner inside a notebook. The user selected part of their note and wants it drawn as a short step-by-step diagram.
Split it into 3 to 6 steps, in order. Each step has a label of 2 to 4 words and one short caption sentence.

Reply with JSON only, no other text:
{{"steps": [{{"label": "<2-4 words>", "caption": "<one short sentence>"}}]}}"""

MAX_STEPS = 6
W, BOX, GAP = 280, 40, 30


class Step(BaseModel):
    label: str = Field(min_length=1)
    caption: str = ""


class Plan(BaseModel):
    steps: list[Step] = Field(min_length=2)


def parse_plan(raw: str) -> Plan | None:
    """The model is told to return bare JSON but may wrap it in a fence or chatter."""
    a, b = raw.find("{"), raw.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        p = Plan.model_validate(json.loads(raw[a : b + 1]))
    except (ValueError, ValidationError):
        return None
    p.steps = p.steps[:MAX_STEPS]
    for s in p.steps:
        s.label = s.label.strip()[:28]
        s.caption = " ".join(s.caption.split())[:200]  # one line: captions are stored joined by newlines
    return p


def build_svg(steps: list[Step]) -> str:
    """One <g class="step"> per step. Every string from the model goes through escape()."""
    out = []
    for i, s in enumerate(steps):
        y = i * (BOX + GAP) + 4
        arrow = f'<path d="M140 {y - GAP} V{y - 2} M134 {y - 8} L140 {y - 2} L146 {y - 8}"/>' if i else ""
        out.append(
            f'<g class="step">{arrow}<rect x="10" y="{y}" width="260" height="{BOX}" rx="8"/>'
            f'<text x="140" y="{y + 25}" text-anchor="middle" fill="currentColor" stroke="none">{escape(s.label)}</text></g>'
        )
    h = len(steps) * (BOX + GAP)
    return f'<svg viewBox="0 0 {W} {h}" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="1.5">{"".join(out)}</svg>'


def draw(provider: Provider, title: str, text: str, selection: str, brief: str = "", lens: dict | None = None) -> tuple[str, str]:
    """Returns (captions joined by newlines, svg)."""
    content = f"Note title: {title or 'Untitled'}\n\nNote:\n{text}\n\nDraw this part:\n{selection}"
    plan = parse_plan(provider.complete(with_brief(DIAGRAM, brief, lens), [{"role": "user", "content": content}]))
    if not plan:
        raise LLMError("The model's diagram could not be read. Try again.")
    return "\n".join(s.caption for s in plan.steps), build_svg(plan.steps)
