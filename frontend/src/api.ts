export type Mode = 'reads_along' | 'on_request'
export type Note = { id: number; title: string; folder_id: number | null; updated_at: string; body_json?: string; mode?: Mode; instructions?: string }
export type Folder = { id: number; name: string }
export type Message = { id: number; role: string; kind: string; text: string }
export type ThreadStatus = 'open' | 'resolved' | 'dismissed'
export type Thread = { id: number; anchor_quote: string; status: ThreadStatus; messages: Message[] }
export class ApiError extends Error {
  detail?: string
}
export type Settings = { default_mode: Mode; reading_pace: string; theme: 'dark' | 'light'; text_size: string; ai_font: 'serif' | 'sans'; ai_color: string }
export type Trigger = 'ask' | 'idle' | 'explain'
export type Status = 'saved' | 'saving' | 'error'

async function send(method: string, url: string, body?: unknown) {
  const r = await fetch(url, {
    method,
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) {
    const d = await r.json().catch(() => null)
    const e = new ApiError(`${method} ${url}: ${r.status}`)
    if (typeof d?.detail === 'string') e.detail = d.detail // our own messages, safe to show
    throw e
  }
  return r.status === 204 ? null : r.json()
}

export const api = {
  notes: (): Promise<Note[]> => send('GET', '/api/notes'),
  note: (id: number): Promise<Note> => send('GET', `/api/notes/${id}`),
  newNote: (title = '', folder_id: number | null = null): Promise<Note> => send('POST', '/api/notes', { title, folder_id }),
  patchNote: (id: number, p: Partial<Pick<Note, 'title' | 'body_json' | 'folder_id' | 'mode' | 'instructions'>>): Promise<Note> => send('PATCH', `/api/notes/${id}`, p),
  deleteNote: (id: number) => send('DELETE', `/api/notes/${id}`),
  threads: (id: number): Promise<Thread[]> => send('GET', `/api/notes/${id}/threads`),
  // null = the model chose to stay quiet (idle only)
  ask: (id: number, selection?: string, trigger: Trigger = 'ask'): Promise<Thread | null> => send('POST', `/api/notes/${id}/ask`, { selection, trigger }),
  reply: (id: number, text: string): Promise<Thread> => send('POST', `/api/threads/${id}/reply`, { text }),
  patchThread: (id: number, status: ThreadStatus): Promise<Thread> => send('PATCH', `/api/threads/${id}`, { status }),
  settings: (): Promise<Settings> => send('GET', '/api/settings'),
  patchSettings: (p: Partial<Settings>): Promise<Settings> => send('PATCH', '/api/settings', p),
  folders: (): Promise<Folder[]> => send('GET', '/api/folders'),
  newFolder: (name: string): Promise<Folder> => send('POST', '/api/folders', { name }),
  renameFolder: (id: number, name: string): Promise<Folder> => send('PATCH', `/api/folders/${id}`, { name }),
  deleteFolder: (id: number) => send('DELETE', `/api/folders/${id}`),
}
