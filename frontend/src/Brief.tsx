import { useState } from 'react'

const PRESETS = [
  'Push back hard on my reasoning.',
  'I am learning this. Point out gaps in my understanding.',
  'Only flag factual mistakes.',
  'This is a rough draft. Be gentle.',
]

export default function Brief({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)
  const save = (v: string) => { setDraft(v); if (v !== value) onSave(v) }
  return (
    <>
      <button className="mode-btn" onClick={() => setOpen(!open)}>📝 Brief{value.trim() ? ' ✓' : ''}</button>
      {open && (
        <div className="brief">
          <textarea
            rows={3}
            maxLength={1000}
            placeholder="What is this note for? How should the AI act?"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => save(draft.trim())}
          />
          <div className="chips">
            {PRESETS.map((p) => <button key={p} onClick={() => save(p)}>{p}</button>)}
          </div>
        </div>
      )}
    </>
  )
}
