import { useEffect, useState } from 'react'
import { api, ApiError, type Folder, type Mode, type Note, type Settings, type Status, type Thread, type ThreadStatus, type Trigger } from './api'
import Brief from './Brief'
import Editor from './Editor'
import Margin from './Margin'
import ModePicker from './ModePicker'
import Palette from './Palette'
import SettingsPanel from './Settings'
import Sidebar from './Sidebar'

export default function App() {
  const [notes, setNotes] = useState<Note[]>([])
  const [folders, setFolders] = useState<Folder[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [note, setNote] = useState<Note | null>(null)
  const [open, setOpen] = useState(false)
  const [palette, setPalette] = useState(false)
  const [status, setStatus] = useState<Status>('saved')
  const [error, setError] = useState('')
  const [th, setTh] = useState<{ id: number; list: Thread[] }>({ id: 0, list: [] })
  const [asking, setAsking] = useState<Trigger | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [writingOnly, setWritingOnly] = useState(false)
  const threads = th.id === activeId ? th.list : [] // never show another note's margin

  const errMsg = (e: unknown) => (e instanceof ApiError && e.detail) || 'Could not reach the server.'
  const guard = async (fn: () => Promise<void>) => {
    try { setError(''); await fn() } catch (e) { setError(errMsg(e)) }
  }

  useEffect(() => {
    guard(async () => {
      const [n, f, s] = await Promise.all([api.notes(), api.folders(), api.settings()])
      setSettings(s); setNotes(n); setFolders(f); setActiveId(n[0]?.id ?? null)
    })
  }, [])

  useEffect(() => {
    if (activeId === null) { setNote(null); return }
    guard(async () => setNote(await api.note(activeId)))
  }, [activeId])

  useEffect(() => {
    if (activeId === null) return
    guard(async () => setTh({ id: activeId, list: await api.threads(activeId) }))
  }, [activeId])

  useEffect(() => {
    if (!settings) return
    const r = document.documentElement
    r.dataset.theme = settings.theme
    r.style.setProperty('--size', settings.text_size + 'px')
    r.style.setProperty('--ai-font', settings.ai_font === 'sans' ? 'var(--sans)' : 'var(--serif)')
    r.style.setProperty('--ai-color', settings.ai_color || 'var(--text)')
  }, [settings])

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setPalette(true) }
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === 'Period') { e.preventDefault(); setWritingOnly((v) => !v) }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [])

  const newNote = (title = '', folderId: number | null = null) => guard(async () => {
    const n = await api.newNote(title, folderId)
    setNotes((l) => [n, ...l]); setNote(n); setActiveId(n.id); setPalette(false)
  })

  const ask = async (selection?: string, trigger: Trigger = 'ask') => {
    if (activeId === null || asking) return
    const id = activeId
    setAsking(trigger)
    try {
      setError('')
      const t = await api.ask(id, selection, trigger)
      if (t) setTh((s) => (s.id === id ? { id, list: [...s.list, t] } : s))
    } catch (e) {
      if (trigger !== 'idle') setError(errMsg(e)) // background (idle) failures stay silent
    } finally {
      setAsking(null)
    }
  }

  const reply = async (t: Thread, text: string) => {
    try {
      setError('')
      const u = await api.reply(t.id, text)
      setTh((s) => ({ ...s, list: s.list.map((x) => (x.id === u.id ? u : x)) }))
      return true
    } catch (e) {
      setError(errMsg(e))
      return false
    }
  }

  const changeThread = (t: Thread, status: ThreadStatus) => guard(async () => {
    const u = await api.patchThread(t.id, status)
    setTh((s) => ({ ...s, list: status === 'dismissed' ? s.list.filter((x) => x.id !== t.id) : s.list.map((x) => (x.id === t.id ? u : x)) }))
  })

  const setMode = (mode: Mode) => note && guard(async () => {
    const n = await api.patchNote(note.id, { mode })
    setNote((p) => p && { ...p, mode: n.mode })
  })

  const setBrief = (instructions: string) => note && guard(async () => {
    const n = await api.patchNote(note.id, { instructions })
    setNote((p) => p && { ...p, instructions: n.instructions })
  })

  const changeSettings = (p: Partial<Settings>) => guard(async () => setSettings(await api.patchSettings(p)))

  const mode: Mode = note?.mode ?? 'reads_along'

  return (
    <div className={'app' + (open ? ' side-open' : '')}>
      <header className="top">
        <button className="icon" aria-label="Menu" onClick={() => setOpen(!open)}>{open ? '✕' : '☰'}</button>
        <span className="logo">reinterpret</span>
      </header>
      {open && (
        <Sidebar
          notes={notes} folders={folders} activeId={activeId} status={status}
          onSettings={() => setShowSettings(true)}
          writingOnly={writingOnly} onWritingOnly={() => setWritingOnly((v) => !v)}
          onOpen={setActiveId}
          onNew={(f) => newNote('', f ?? null)}
          onSearch={() => setPalette(true)}
          onDeleteNote={(id) => {
            if (!confirm('Delete this note?')) return
            guard(async () => {
              await api.deleteNote(id)
              const rest = notes.filter((n) => n.id !== id)
              setNotes(rest)
              if (id === activeId) setActiveId(rest[0]?.id ?? null)
            })
          }}
          onMove={(id, folder_id) => guard(async () => {
            const n = await api.patchNote(id, { folder_id })
            setNotes((l) => l.map((x) => (x.id === id ? n : x)))
          })}
          onNewFolder={(name) => guard(async () => { const f = await api.newFolder(name); setFolders((l) => [...l, f]) })}
          onRenameFolder={(f) => {
            const name = prompt('Folder name', f.name)?.trim()
            if (name) guard(async () => { const g = await api.renameFolder(f.id, name); setFolders((l) => l.map((x) => (x.id === f.id ? g : x))) })
          }}
          onDeleteFolder={(f) => {
            if (!confirm(`Delete folder "${f.name}"? Its notes are kept.`)) return
            guard(async () => {
              await api.deleteFolder(f.id)
              setFolders((l) => l.filter((x) => x.id !== f.id))
              setNotes((l) => l.map((n) => (n.folder_id === f.id ? { ...n, folder_id: null } : n)))
            })
          }}
        />
      )}
      <main className="page">
        {!writingOnly && <Margin threads={threads} thinking={asking !== null && asking !== 'idle'} onReply={reply} onStatus={changeThread} />}
        <div className="col">
          {note && note.id === activeId && (
            <div className="bar"><ModePicker mode={mode} onChange={setMode} /> <Brief key={note.id} value={note.instructions ?? ''} onSave={setBrief} /></div>
          )}
          {note && note.id === activeId ? (
            <Editor
              key={note.id}
              note={note}
              busy={asking !== null}
              idle={mode === 'reads_along' && !writingOnly}
              pace={Number(settings?.reading_pace ?? 3)}
              onAsk={ask}
              onStatus={setStatus}
              onSaved={(n) => setNotes((l) => l.map((x) => (x.id === n.id ? { ...x, title: n.title, updated_at: n.updated_at } : x)))}
            />
          ) : (
            !error && <button className="empty" onClick={() => newNote()}>New note</button>
          )}
        </div>
      </main>
      {showSettings && settings && <SettingsPanel s={settings} onChange={changeSettings} onClose={() => setShowSettings(false)} />}
      {palette && <Palette notes={notes} onOpen={(id) => { setActiveId(id); setPalette(false) }} onStart={(t) => newNote(t)} onClose={() => setPalette(false)} />}
      {error && <div className="toast" onClick={() => setError('')}>{error}</div>}
    </div>
  )
}
