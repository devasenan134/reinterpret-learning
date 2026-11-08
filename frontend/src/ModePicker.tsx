import { useState } from 'react'
import type { Mode } from './api'

const MODES: { id: Mode; icon: string; name: string; hint: string }[] = [
  { id: 'reads_along', icon: '👀', name: 'Reads along', hint: 'Follows what you write and comments when it spots a problem.' },
  { id: 'on_request', icon: '✋', name: 'On request', hint: 'Silent until you select some text and press ⌘↵.' },
]

export default function ModePicker({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const [open, setOpen] = useState(false)
  const cur = MODES.find((m) => m.id === mode) ?? MODES[0]
  return (
    <div className="mode">
      <button className="mode-btn" onClick={() => setOpen(!open)}>
        {cur.icon} {cur.name} <span>▾</span>
      </button>
      {open && (
        <>
          <div className="mode-scrim" onClick={() => setOpen(false)} />
          <div className="mode-menu">
            {MODES.map((m) => (
              <button key={m.id} className={m.id === mode ? 'on' : ''} onClick={() => { setOpen(false); if (m.id !== mode) onChange(m.id) }}>
                <b>{m.icon} {m.name}</b>
                <small>{m.hint}</small>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
