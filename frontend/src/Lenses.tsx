import { useEffect, useState } from 'react'
import { api, ApiError, type Lens } from './api'

const EMPTY: Omit<Lens, 'id'> = { name: '', description: '', how_it_thinks: '', voice: 'plain', frequency: 'when_it_matters' }

export default function Lenses({ value, onChange }: { value: number | null; onChange: (id: number | null) => Promise<void> }) {
  const [lenses, setLenses] = useState<Lens[]>([])
  const [editing, setEditing] = useState(false)
  const [id, setId] = useState<number | null>(null)
  const [draft, setDraft] = useState(EMPTY)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof ApiError && e.detail || 'Could not save lenses. Try again.') }
    finally { setBusy(false) }
  }
  useEffect(() => {
    let active = true
    api.lenses().then((ls) => { if (active) setLenses(ls) }).catch(() => { if (active) setError('Could not load lenses. Try reopening this note.') })
    return () => { active = false }
  }, [])
  const current = lenses.find((l) => l.id === value)
  const edit = (lens?: Lens) => { setId(lens?.id ?? null); setDraft(lens ?? EMPTY); setEditing(true); setError('') }
  return (
    <>
      <select className="mode-btn" aria-label="Lens" value={value ?? ''} disabled={busy} onChange={(e) => void run(() => onChange(e.target.value ? Number(e.target.value) : null))}>
        <option value="">Default voice</option>
        {lenses.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
      </select>
      <button className="mode-btn" onClick={() => edit(current)}>{current ? 'Edit lens' : 'New lens'}</button>
      {current && <button className="mode-btn" onClick={() => edit()}>New lens</button>}
      {error && !editing && <span role="alert">{error}</span>}
      {editing && (
        <div className="scrim" onClick={() => { if (!busy) setEditing(false) }}>
          <form className="settings lens-form" role="dialog" aria-modal="true" onKeyDown={(e) => { if (e.key === 'Escape' && !busy) setEditing(false) }} aria-label={id === null ? 'New lens' : 'Edit lens'} onClick={(e) => e.stopPropagation()} onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              const saved = await api.saveLens(id, draft)
              setId(saved.id)
              setLenses(await api.lenses())
              await onChange(saved.id)
              setEditing(false)
            })
          }}>
            <h3>{id === null ? 'New lens' : 'Edit lens'}</h3>
            <label>Name<input autoFocus required maxLength={80} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label>Description<textarea maxLength={240} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
            <label>How it thinks<textarea maxLength={500} value={draft.how_it_thinks} onChange={(e) => setDraft({ ...draft, how_it_thinks: e.target.value })} /></label>
            <label>Voice<select value={draft.voice} onChange={(e) => setDraft({ ...draft, voice: e.target.value as Lens['voice'] })}>
              <option value="plain">Plain</option><option value="warm">Warm</option><option value="blunt">Blunt</option><option value="playful">Playful</option>
            </select></label>
            <label>How often it speaks<select value={draft.frequency} onChange={(e) => setDraft({ ...draft, frequency: e.target.value as Lens['frequency'] })}>
              <option value="rarely">Rarely</option><option value="when_it_matters">When it matters</option><option value="often">Often</option>
            </select></label>
            {error && <p role="alert">{error}</p>}
            <div className="chips">
              <button disabled={busy || !draft.name.trim()} type="submit">Save</button>
              <button disabled={busy} type="button" onClick={() => setEditing(false)}>Cancel</button>
              {id !== null && <button disabled={busy} type="button" onClick={() => {
                if (!confirm('Delete this lens? Notes and threads are kept.')) return
                void run(async () => {
                  await api.deleteLens(id)
                  setLenses((ls) => ls.filter((l) => l.id !== id))
                  if (value === id) await onChange(null)
                  setEditing(false)
                })
              }}>Delete</button>}
            </div>
          </form>
        </div>
      )}
    </>
  )
}
