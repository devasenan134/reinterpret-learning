from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from .db import connect, seed
from .llm import LLMError, get_provider
from .respond import ask, note_text


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


# ---- notes ----

class NotePatch(BaseModel):
    title: Optional[str] = None
    body_json: Optional[str] = None
    folder_id: Optional[int] = None


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
    cur = db.execute("INSERT INTO notes (title, folder_id) VALUES (?, ?)", (body.title, body.folder_id))
    db.commit()
    return _note(db, cur.lastrowid)


@app.get("/api/notes/{note_id}")
def get_note(note_id: int, db=Depends(get_db)):
    return _note(db, note_id)


@app.patch("/api/notes/{note_id}")
def patch_note(note_id: int, body: NotePatch, db=Depends(get_db)):
    _note(db, note_id)
    fields = body.model_dump(exclude_unset=True)
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
    t = dict(db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone())
    t["messages"] = [dict(m) for m in db.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY id", (thread_id,))]
    return t


@app.get("/api/notes/{note_id}/threads")
def list_threads(note_id: int, db=Depends(get_db)):
    _note(db, note_id)
    ids = db.execute("SELECT id FROM threads WHERE note_id = ? AND status != 'dismissed' ORDER BY id", (note_id,))
    return [_thread(db, r["id"]) for r in ids.fetchall()]


class AskIn(BaseModel):
    selection: Optional[str] = None


def get_llm():
    try:
        return get_provider()
    except LLMError as e:
        raise HTTPException(503, str(e))


@app.post("/api/notes/{note_id}/ask", status_code=201)
def ask_note(note_id: int, body: AskIn, db=Depends(get_db), llm=Depends(get_llm)):
    note = _note(db, note_id)
    text = note_text(note["body_json"])
    selection = (body.selection or "").strip() or None
    if not text and not selection:
        raise HTTPException(400, "Write something first.")
    try:
        reply = ask(llm, note["title"], text, selection)
    except LLMError as e:
        raise HTTPException(502, str(e))
    cur = db.execute("INSERT INTO threads (note_id, anchor_quote) VALUES (?, ?)", (note_id, reply.anchor_quote))
    db.execute(
        "INSERT INTO messages (thread_id, role, kind, text) VALUES (?, 'ai', 'question', ?)",
        (cur.lastrowid, reply.text),
    )
    db.commit()
    return _thread(db, cur.lastrowid)
