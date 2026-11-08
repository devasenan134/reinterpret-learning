# Reinterpret — plan

A self-hosted notebook where an AI reads what you write, questions it, explains it and draws diagrams in the margin. It never writes your notes for you.

## Features

| # | Feature | Milestone |
|---|---|---|
| 1 | Notes and folders, sidebar, search or create (⌘K), autosave | 1 ✅ |
| 2 | Rich text: headings, lists, quote, code, colours, `/` block menu | 1 ✅ |
| 3 | Question this (⌘↵): the AI pushes back on a selection or the whole note | 2 ✅ |
| 4 | Margin threads: reply, Resolve, Reopen, Dismiss | 3 ✅ |
| 5 | Mode per note: **Reads along** (comments after a pause) or **On request** (silent until asked) | 3 ✅ |
| 6 | Writing only (⌘⇧.): hide the margin | 3 ✅ |
| 7 | **Note brief**: a short text saying what the note is for or how the AI should act, with a few starter presets | 4 |
| 8 | Explain a selection | 4 |
| 9 | Settings: default mode, reading pace, where questions appear, light/dark, text size, AI font and colour | 4 |
| 10 | Step-by-step diagrams drawn in ink, step counter, enlarged view | 5 |
| 11 | **Lenses**: reviewer personas you create (name, description, how it thinks, voice, how often it speaks). A note picks one | 6 |
| 12 | Chat panel about the current note, with suggested questions | 7 |
| 13 | Voice input (hold ⌥), export to PDF / Word / Markdown, copy note, share | 7 |

Not planned: accounts, billing, teams. Single user, self-hosted.

## Stack

FastAPI + SQLite + pytest. React + Vite + TypeScript + TipTap.
LLM adapter with two providers: Anthropic, and OpenAI-compatible (OpenAI, Ollama, any server). Set in `.env`, which is never committed. Currently pointed at a self-hosted Qwen.

## Design rules

- The model returns JSON (`anchor_quote`, `text`). The server validates it and drops anything unreadable.
- "On request" is enforced on the server, not only in the UI.
- Small models cannot be told to stay silent. For idle replies a yes/no gate call decides first, and a check in code drops repeats of a point already raised.
- Diagrams will be SVG with one group per step. The server sanitizes it with an allowlist (no scripts, handlers or external links).
- Prompt rules that always apply: question rather than answer, but state a plain factual correction; never rewrite the user's text; keep it short.

## Milestones

0. Skeleton ✅  1. Notes, folders, editor ✅  2. LLM adapter and Question this ✅  3. Replies, modes, Writing only ✅
4. Note brief, explain, settings  5. Diagrams  6. Lenses  7. Chat, voice, export, polish

## Open

- What Share should do (link or export).
- Margin placement: threads are stacked at the top, not yet aligned with the sentence they are about.
- Look and feel: the dark theme and margin layout are close to the product this was inspired by. Decide how far to differ before polish.
