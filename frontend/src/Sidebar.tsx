import { useState } from 'react'
import type { Folder, Note, Status } from './api'

type Props = {
  notes: Note[]
  folders: Folder[]
  activeId: number | null
  status: Status
  writingOnly: boolean
  onWritingOnly: () => void
  onSettings: () => void
  onOpen: (id: number) => void
  onNew: (folderId?: number | null) => void
  onSearch: () => void
  onDeleteNote: (id: number) => void
  onMove: (id: number, folderId: number | null) => void
  onNewFolder: (name: string) => void
  onRenameFolder: (f: Folder) => void
  onDeleteFolder: (f: Folder) => void
}

const STATUS = { saved: 'All notes saved', saving: 'Saving…', error: 'Not saved: server unreachable' }

export default function Sidebar(p: Props) {
  const [menu, setMenu] = useState<number | null>(null)
  const [naming, setNaming] = useState(false)

  const row = (n: Note) => (
    <div key={n.id} className={'note' + (n.id === p.activeId ? ' on' : '')}>
      <button className="grow" onClick={() => p.onOpen(n.id)}>{n.title || 'Untitled'}</button>
      <button className="more" title="More" onClick={() => setMenu(menu === n.id ? null : n.id)}>…</button>
      {menu === n.id && (
        <div className="menu" onMouseLeave={() => setMenu(null)}>
          {n.folder_id !== null && <button onClick={() => { p.onMove(n.id, null); setMenu(null) }}>Move out of folder</button>}
          {p.folders.filter((f) => f.id !== n.folder_id).map((f) => (
            <button key={f.id} onClick={() => { p.onMove(n.id, f.id); setMenu(null) }}>Move to {f.name}</button>
          ))}
          <button onClick={() => { p.onDeleteNote(n.id); setMenu(null) }}>Delete</button>
        </div>
      )}
    </div>
  )

  return (
    <aside className="sidebar">
      <button className="side-btn" onClick={p.onSearch}>Search or create a note <kbd>⌘K</kbd></button>
      <button className="side-btn" onClick={() => p.onNew()}>+ New note</button>
      <div className="list">
        {p.notes.filter((n) => n.folder_id === null).map(row)}
        {p.folders.map((f) => (
          <div key={f.id} className="folder">
            <div className="folder-head">
              <span className="grow">{f.name}</span>
              <button title="New note here" onClick={() => p.onNew(f.id)}>+</button>
              <button title="Rename" onClick={() => p.onRenameFolder(f)}>✎</button>
              <button title="Delete folder" onClick={() => p.onDeleteFolder(f)}>×</button>
            </div>
            {p.notes.filter((n) => n.folder_id === f.id).map(row)}
          </div>
        ))}
        {naming ? (
          <input
            className="folder-input"
            autoFocus
            placeholder="Folder name"
            onBlur={() => setNaming(false)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setNaming(false)
              if (e.key === 'Enter' && e.currentTarget.value.trim()) { p.onNewFolder(e.currentTarget.value.trim()); setNaming(false) }
            }}
          />
        ) : (
          <button className="side-btn muted" onClick={() => setNaming(true)}>New folder</button>
        )}
      </div>
      <button className="side-btn" onClick={p.onWritingOnly}>Writing only {p.writingOnly ? '✓' : <kbd>⌘⇧.</kbd>}</button>
      <button className="side-btn" onClick={p.onSettings}>Settings</button>
      <div className={'status ' + p.status}>{STATUS[p.status]}</div>
    </aside>
  )
}
