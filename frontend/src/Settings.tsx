import type { Settings } from './api'

const ROWS: { key: keyof Settings; label: string; options: [string, string][] }[] = [
  { key: 'default_mode', label: 'New notes start as', options: [['reads_along', 'Reads along'], ['on_request', 'On request']] },
  { key: 'reading_pace', label: 'Reading pace', options: [['3', 'Quick'], ['6', 'Relaxed'], ['12', 'Slow']] },
  { key: 'theme', label: 'Theme', options: [['dark', 'Dark'], ['light', 'Light']] },
  { key: 'text_size', label: 'Text size', options: [['15', 'S'], ['16', 'M'], ['18', 'L'], ['20', 'XL']] },
  { key: 'ai_font', label: 'AI font', options: [['serif', 'Serif'], ['sans', 'Sans']] },
  { key: 'ai_color', label: 'AI colour', options: [['', 'Default'], ['#e9a35c', 'Amber'], ['#7fc58a', 'Green'], ['#6fa8e8', 'Blue'], ['#b48ae8', 'Purple']] },
]

export default function SettingsPanel({ s, onChange, onClose }: { s: Settings; onChange: (p: Partial<Settings>) => void; onClose: () => void }) {
  return (
    <div className="scrim" onClick={onClose}>
      <div className="settings" onClick={(e) => e.stopPropagation()}>
        <h3>Settings</h3>
        {ROWS.map((r) => (
          <div key={r.key} className="srow">
            <span>{r.label}</span>
            <div>
              {r.options.map(([v, name]) => (
                <button key={v} className={s[r.key] === v ? 'on' : ''} onClick={() => onChange({ [r.key]: v })}>{name}</button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
