export type Note = { id: number; title: string; folder_id: number | null; updated_at: string; body_json?: string }
export type Folder = { id: number; name: string }
export type Status = 'saved' | 'saving' | 'error'

async function send(method: string, url: string, body?: unknown) {
  const r = await fetch(url, {
    method,
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${method} ${url}: ${r.status}`)
  return r.status === 204 ? null : r.json()
}

export const api = {
  notes: (): Promise<Note[]> => send('GET', '/api/notes'),
  note: (id: number): Promise<Note> => send('GET', `/api/notes/${id}`),
  newNote: (title = '', folder_id: number | null = null): Promise<Note> => send('POST', '/api/notes', { title, folder_id }),
  patchNote: (id: number, p: Partial<Pick<Note, 'title' | 'body_json' | 'folder_id'>>): Promise<Note> => send('PATCH', `/api/notes/${id}`, p),
  deleteNote: (id: number) => send('DELETE', `/api/notes/${id}`),
  folders: (): Promise<Folder[]> => send('GET', '/api/folders'),
  newFolder: (name: string): Promise<Folder> => send('POST', '/api/folders', { name }),
  renameFolder: (id: number, name: string): Promise<Folder> => send('PATCH', `/api/folders/${id}`, { name }),
  deleteFolder: (id: number) => send('DELETE', `/api/folders/${id}`),
}
