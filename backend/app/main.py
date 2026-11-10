from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .db import connect, seed
from .diagram import draw
from .llm import LLMError, get_provider
from .respond import ask, explain, note_text
from .respond import reply as llm_reply


def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_):
    conn = connect()
    seed(conn)
    conn.close()
    yield


app = FastAPI(title="Reinterpret", lifespan=lifespan)


@app.get("/api/health")
def health():
    connect().close()  # fails loudly if the database can't be opened
    return {"ok": True}


# ---- settings ----

DEFAULTS = {"default_mode": "reads_along", "reading_pace": "3", "theme": "dark", "text_size": "16", "ai_font": "serif", "ai_color": ""}


class SettingsPatch(BaseModel):
    default_mode: Optional[Literal["reads_along", "on_request"]] = None
    reading_pace: Optional[Literal["3", "6", "12"]] = None  # seconds of quiet before it speaks
    theme: Optional[Literal["dark", "light"]] = None
    text_size: Optional[Literal["15", "16", "18", "20"]] = None
    ai_font: Optional[Literal["serif", "sans"]] = None
    ai_color: Optional[Literal["", "#e9a35c", "#7fc58a", "#6fa8e8", "#b48ae8"]] = None


def _settings(db) -> dict:
    return {**DEFAULTS, **{r["key"]: r["value"] for r in db.execute("SELECT key, value FROM settings")}}


@app.get("/api/settings")
def get_settings(db=Depends(get_db)):
    return _settings(db)


@app.patch("/api/settings")
def patch_settings(body: SettingsPatch, db=Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():  # exclude_none keeps ai_color "" (it is not None)
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, v))
    db.commit()
    return _settings(db)


# ---- lenses ----

class LensIn(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r"\S")
    description: str = Field("", max_length=240)
    how_it_thinks: str = Field("", max_length=500)
    voice: Literal["plain", "warm", "blunt", "playful"] = "plain"
    frequency: Literal["rarely", "when_it_matters", "often"] = "when_it_matters"


def _lens(db, lens_id: int):
    row = db.execute("SELECT * FROM lenses WHERE id = ?", (lens_id,)).fetchone()
    if not row:
        raise HTTPException(404, "lens not found")
    return dict(row)


@app.get("/api/lenses")
def list_lenses(db=Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM lenses ORDER BY name, id")]


@app.get("/api/lenses/{lens_id}")
def get_lens(lens_id: int, db=Depends(get_db)):
    return _lens(db, lens_id)


@app.post("/api/lenses", status_code=201)
def create_lens(body: LensIn, db=Depends(get_db)):
    cur = db.execute("INSERT INTO lenses (name, description, how_it_thinks, voice, frequency) VALUES (?, ?, ?, ?, ?)", tuple(body.model_dump().values()))
    db.commit()
    return _lens(db, cur.lastrowid)


@app.put("/api/lenses/{lens_id}")
def update_lens(lens_id: int, body: LensIn, db=Depends(get_db)):
    _lens(db, lens_id)
    db.execute("UPDATE lenses SET name = ?, description = ?, how_it_thinks = ?, voice = ?, frequency = ? WHERE id = ?", (*body.model_dump().values(), lens_id))
    db.commit()
    return _lens(db, lens_id)


@app.delete("/api/lenses/{lens_id}", status_code=204)
def delete_lens(lens_id: int, db=Depends(get_db)):
    _lens(db, lens_id)
    db.execute("DELETE FROM lenses WHERE id = ?", (lens_id,))
    db.commit()


# ---- notes ----

class NotePatch(BaseModel):
    lens_id: Optional[int] = None
    title: Optional[str] = None
    body_json: Optional[str] = None
    folder_id: Optional[int] = None
    mode: Optional[Literal["reads_along", "on_request"]] = None
    instructions: Optional[str] = Field(None, max_length=1000)  # the note brief


class NoteNew(BaseModel):
    title: str = ""
    folder_id: Optional[int] = None


def _note(db, note_id: int):
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        raise HTTPException(404, "note not found")
    return dict(row)


@app.get("/api/notes")
def list_notes(db=Depends(get_db)):
    rows = db.execute(
        "SELECT id, title, folder_id, updated_at FROM notes ORDER BY updated_at DESC, id DESC"
    )
    return [dict(r) for r in rows]


@app.post("/api/notes", status_code=201)
def create_note(body: NoteNew, db=Depends(get_db)):
    cur = db.execute("INSERT INTO notes (title, folder_id, mode) VALUES (?, ?, ?)", (body.title, body.folder_id, _settings(db)["default_mode"]))
    db.commit()
    return _note(db, cur.lastrowid)


@app.get("/api/notes/{note_id}")
def get_note(note_id: int, db=Depends(get_db)):
    return _note(db, note_id)


@app.patch("/api/notes/{note_id}")
def patch_note(note_id: int, body: NotePatch, db=Depends(get_db)):
    _note(db, note_id)
    # A null title/body/mode would break a NOT NULL column.
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k in ("folder_id", "lens_id")}
    if fields.get("lens_id") is not None:
        _lens(db, fields["lens_id"])
    if fields:
        cols = ", ".join(f"{k} = ?" for k in fields)  # keys come from the model, not the client
        db.execute(
            f"UPDATE notes SET {cols}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*fields.values(), note_id),
        )
        db.commit()
    return _note(db, note_id)


@app.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: int, db=Depends(get_db)):
    _note(db, note_id)
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()


# ---- folders ----

class FolderIn(BaseModel):
    name: str


def _folder(db, folder_id: int):
    row = db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if not row:
        raise HTTPException(404, "folder not found")
    return dict(row)


@app.get("/api/folders")
def list_folders(db=Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM folders ORDER BY name")]


@app.post("/api/folders", status_code=201)
def create_folder(body: FolderIn, db=Depends(get_db)):
    cur = db.execute("INSERT INTO folders (name) VALUES (?)", (body.name,))
    db.commit()
    return _folder(db, cur.lastrowid)


@app.patch("/api/folders/{folder_id}")
def rename_folder(folder_id: int, body: FolderIn, db=Depends(get_db)):
    _folder(db, folder_id)
    db.execute("UPDATE folders SET name = ? WHERE id = ?", (body.name, folder_id))
    db.commit()
    return _folder(db, folder_id)


@app.delete("/api/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: int, db=Depends(get_db)):
    _folder(db, folder_id)
    db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))  # notes fall out of the folder, not deleted
    db.commit()


# ---- threads (the AI's margin notes) ----

def _thread(db, thread_id: int):
    row = db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
    if not row:
        raise HTTPException(404, "thread not found")
    t = dict(row)
    t["messages"] = [dict(m) for m in db.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY id", (thread_id,))]
    return t


@app.get("/api/notes/{note_id}/threads")
def list_threads(note_id: int, db=Depends(get_db)):
    _note(db, note_id)
    ids = db.execute("SELECT id FROM threads WHERE note_id = ? AND status != 'dismissed' ORDER BY id", (note_id,))
    return [_thread(db, r["id"]) for r in ids.fetchall()]


class AskIn(BaseModel):
    selection: Optional[str] = None
    trigger: Literal["ask", "idle", "explain", "diagram"] = "ask"


def get_llm():
    try:
        return get_provider()
    except LLMError as e:
        raise HTTPException(503, str(e))


@app.post("/api/notes/{note_id}/ask", status_code=201)
def ask_note(note_id: int, body: AskIn, db=Depends(get_db), llm=Depends(get_llm)):
    note = _note(db, note_id)
    lens = _lens(db, note["lens_id"]) if note["lens_id"] is not None else None
    idle = body.trigger == "idle"
    if idle and note["mode"] == "on_request":  # enforced here, not only in the UI
        raise HTTPException(409, "This note is set to On request.")
    text = note_text(note["body_json"])
    selection = (body.selection or "").strip() or None
    if body.trigger in ("explain", "diagram"):
        if not selection:
            raise HTTPException(400, f"Select some text to {'explain' if body.trigger == 'explain' else 'draw'}.")
        try:
            if body.trigger == "explain":
                out, kind, svg = explain(llm, note["title"], text, selection, note["instructions"], lens), "explanation", None
            else:
                (out, svg), kind = draw(llm, note["title"], text, selection, note["instructions"], lens), "diagram"
        except LLMError as e:
            raise HTTPException(502, str(e))
        cur = db.execute("INSERT INTO threads (note_id, anchor_quote, lens_id) VALUES (?, ?, ?)", (note_id, selection, note["lens_id"]))
        db.execute("INSERT INTO messages (thread_id, role, kind, text, svg) VALUES (?, 'ai', ?, ?, ?)", (cur.lastrowid, kind, out, svg))
        db.commit()
        return _thread(db, cur.lastrowid)
    if not text and not selection:
        if idle:
            return Response(status_code=204)
        raise HTTPException(400, "Write something first.")
    raised = tuple(r["anchor_quote"] for r in db.execute("SELECT anchor_quote FROM threads WHERE note_id = ?", (note_id,)))
    try:
        reply = ask(llm, note["title"], text, selection, idle, raised, note["instructions"], lens)
    except LLMError as e:
        raise HTTPException(502, str(e))
    if reply is None:
        return Response(status_code=204)
    cur = db.execute("INSERT INTO threads (note_id, anchor_quote, lens_id) VALUES (?, ?, ?)", (note_id, reply.anchor_quote, note["lens_id"]))
    db.execute(
        "INSERT INTO messages (thread_id, role, kind, text) VALUES (?, 'ai', 'question', ?)",
        (cur.lastrowid, reply.text),
    )
    db.commit()
    return _thread(db, cur.lastrowid)


class ReplyIn(BaseModel):
    text: str


@app.post("/api/threads/{thread_id}/reply")
def reply_thread(thread_id: int, body: ReplyIn, db=Depends(get_db), llm=Depends(get_llm)):
    t = _thread(db, thread_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Write a reply first.")
    if len(text) > 4000:
        raise HTTPException(400, "That reply is too long.")
    if t["status"] != "open":
        raise HTTPException(409, "This thread is closed. Reopen it to reply.")
    note = _note(db, t["note_id"])
    lens = _lens(db, note["lens_id"]) if note["lens_id"] is not None else None
    try:
        answer = llm_reply(llm, note["title"], note_text(note["body_json"]), t["anchor_quote"], [*t["messages"], {"role": "user", "text": text}], note["instructions"], lens)
    except LLMError as e:
        raise HTTPException(502, str(e))  # nothing saved, so the user can send the same text again
    db.execute("INSERT INTO messages (thread_id, role, kind, text) VALUES (?, 'user', 'text', ?)", (thread_id, text))
    db.execute("INSERT INTO messages (thread_id, role, kind, text) VALUES (?, 'ai', 'text', ?)", (thread_id, answer))
    db.commit()
    return _thread(db, thread_id)


class ThreadPatch(BaseModel):
    status: Literal["open", "resolved", "dismissed"]


@app.patch("/api/threads/{thread_id}")
def patch_thread(thread_id: int, body: ThreadPatch, db=Depends(get_db)):
    _thread(db, thread_id)
    db.execute("UPDATE threads SET status = ? WHERE id = ?", (body.status, thread_id))
    db.commit()
    return _thread(db, thread_id)
