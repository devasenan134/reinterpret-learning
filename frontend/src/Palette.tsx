import { useState } from 'react'
import type { Note } from './api'

type Props = { notes: Note[]; onOpen: (id: number) => void; onStart: (title: string) => void; onClose: () => void }

export default function Palette({ notes, onOpen, onStart, onClose }: Props) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const hits = notes.filter((n) => (n.title || 'Untitled').toLowerCase().includes(q.trim().toLowerCase()))
  const startable = q.trim() !== '' && !notes.some((n) => n.title.toLowerCase() === q.trim().toLowerCase())
  const total = hits.length + (startable ? 1 : 0)
  const go = (i: number) => (i < hits.length ? onOpen(hits[i].id) : onStart(q.trim()))

  return (
    <div className="scrim" onMouseDown={onClose}>
      <div className="palette" onMouseDown={(e) => e.stopPropagation()}>
        <input
          autoFocus
          placeholder="Search or create a note"
          value={q}
          onChange={(e) => { setQ(e.target.value); setSel(0) }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose()
            else if (e.key === 'ArrowDown') { e.preventDefault(); setSel((sel + 1) % Math.max(total, 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((sel - 1 + total) % Math.max(total, 1)) }
            else if (e.key === 'Enter' && total) go(sel)
          }}
        />
        {hits.map((n, i) => (
          <button key={n.id} className={i === sel ? 'on' : ''} onMouseDown={() => go(i)}>{n.title || 'Untitled'}</button>
        ))}
        {startable && (
          <button className={sel === hits.length ? 'on' : ''} onMouseDown={() => go(hits.length)}>Create a note “{q.trim()}”</button>
        )}
      </div>
    </div>
  )
}
