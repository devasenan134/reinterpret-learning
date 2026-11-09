import { useState } from 'react'
import Diagram from './Diagram'
import type { Thread, ThreadStatus } from './api'

type Props = {
  threads: Thread[]
  thinking: boolean
  onReply: (t: Thread, text: string) => Promise<boolean>
  onStatus: (t: Thread, s: ThreadStatus) => void
}

function Card({ t, onReply, onStatus }: { t: Thread; onReply: Props['onReply']; onStatus: Props['onStatus'] }) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const send = async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    if (await onReply(t, text)) setDraft('') // on failure the text stays so it can be sent again
    setSending(false)
  }
  return (
    <div className={'thread' + (t.status === 'resolved' ? ' resolved' : '')}>
      {t.anchor_quote && <q>{t.anchor_quote}</q>}
      {t.messages.map((m) => m.svg ? (
        <Diagram key={m.id} svg={m.svg} captions={m.text.split('\n')} />
      ) : (
        <p key={m.id} className={m.role === 'user' ? 'mine' : ''}>{m.text}</p>
      ))}
      {t.status === 'open' && (
        <input
          className="write-back"
          placeholder={sending ? 'Thinking…' : 'Reply…'}
          value={draft}
          disabled={sending}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void send() }}
        />
      )}
      <div className="thread-actions">
        {t.status === 'open' ? <button onClick={() => onStatus(t, 'resolved')}>Resolve</button> : <button onClick={() => onStatus(t, 'open')}>Reopen</button>}
        <button onClick={() => onStatus(t, 'dismissed')}>Dismiss</button>
      </div>
    </div>
  )
}

export default function Margin({ threads, thinking, onReply, onStatus }: Props) {
  if (!threads.length && !thinking) return null
  return (
    <aside className="margin">
      {threads.map((t) => <Card key={t.id} t={t} onReply={onReply} onStatus={onStatus} />)}
      {thinking && <div className="thread thinking">Thinking…</div>}
    </aside>
  )
}
