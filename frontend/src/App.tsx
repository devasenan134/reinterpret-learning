import { useEffect, useState } from 'react'
import { api, type Folder, type Note, type Status } from './api'
import Editor from './Editor'
import Palette from './Palette'
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

  const guard = async (fn: () => Promise<void>) => {
    try { setError(''); await fn() } catch { setError('Could not reach the server.') }
  }

  useEffect(() => {
    guard(async () => {
      const [n, f] = await Promise.all([api.notes(), api.folders()])
      setNotes(n); setFolders(f); setActiveId(n[0]?.id ?? null)
    })
  }, [])

  useEffect(() => {
    if (activeId === null) { setNote(null); return }
    guard(async () => setNote(await api.note(activeId)))
  }, [activeId])

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setPalette(true) }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [])

  const newNote = (title = '', folderId: number | null = null) => guard(async () => {
    const n = await api.newNote(title, folderId)
    setNotes((l) => [n, ...l]); setNote(n); setActiveId(n.id); setPalette(false)
  })

  return (
    <div className={'app' + (open ? ' side-open' : '')}>
      <header className="top">
        <button className="icon" aria-label="Menu" onClick={() => setOpen(!open)}>{open ? '✕' : '☰'}</button>
        <span className="logo">reinterpret</span>
      </header>
      {open && (
        <Sidebar
          notes={notes} folders={folders} activeId={activeId} status={status}
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
        <div className="col">
          {note && note.id === activeId ? (
            <Editor
              key={note.id}
              note={note}
              onStatus={setStatus}
              onSaved={(n) => setNotes((l) => l.map((x) => (x.id === n.id ? { ...x, title: n.title, updated_at: n.updated_at } : x)))}
            />
          ) : (
            !error && <button className="empty" onClick={() => newNote()}>New note</button>
          )}
        </div>
      </main>
      {palette && <Palette notes={notes} onOpen={(id) => { setActiveId(id); setPalette(false) }} onStart={(t) => newNote(t)} onClose={() => setPalette(false)} />}
      {error && <div className="toast">{error}</div>}
    </div>
  )
}
