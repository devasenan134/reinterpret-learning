import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS folders (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lenses (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  how_it_thinks TEXT NOT NULL DEFAULT '',
  voice TEXT NOT NULL DEFAULT 'plain',          -- plain | warm | blunt | playful
  frequency TEXT NOT NULL DEFAULT 'when_it_matters' -- rarely | when_it_matters | often
);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY,
  folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
  lens_id INTEGER REFERENCES lenses(id) ON DELETE SET NULL, -- NULL = the default voice
  title TEXT NOT NULL DEFAULT '',
  body_json TEXT NOT NULL DEFAULT '{}',
  mode TEXT NOT NULL DEFAULT 'reads_along',  -- reads_along | on_request
  instructions TEXT NOT NULL DEFAULT '',          -- the note brief
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS threads (
  id INTEGER PRIMARY KEY,
  note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  lens_id INTEGER REFERENCES lenses(id) ON DELETE SET NULL,
  anchor_block TEXT NOT NULL DEFAULT '',
  anchor_quote TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open'            -- open | resolved | dismissed
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                             -- user | ai
  kind TEXT NOT NULL DEFAULT 'text',              -- text | question | explanation | diagram
  text TEXT NOT NULL DEFAULT '',
  svg TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or os.environ.get("DB_PATH", "reinterpret.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
