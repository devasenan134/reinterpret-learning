import type { Thread } from './api'

export default function Margin({ threads, asking }: { threads: Thread[]; asking: boolean }) {
  if (!threads.length && !asking) return null
  return (
    <aside className="margin">
      {threads.map((t) => (
        <div key={t.id} className="thread">
          {t.anchor_quote && <q>{t.anchor_quote}</q>}
          {t.messages.map((m) => (
            <p key={m.id}>{m.text}</p>
          ))}
        </div>
      ))}
      {asking && <div className="thread thinking">Thinking…</div>}
    </aside>
  )
}
