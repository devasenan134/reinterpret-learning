import { useEffect, useRef } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import { BubbleMenu } from '@tiptap/react/menus'
import StarterKit from '@tiptap/starter-kit'
import { Color, TextStyle } from '@tiptap/extension-text-style'
import Placeholder from '@tiptap/extension-placeholder'
import { api, type Note, type Status, type Trigger } from './api'
import { Slash } from './slash'

const COLORS = ['', '#8a8a85', '#e9a35c', '#e5675f', '#e6c35c', '#7fc58a', '#6fa8e8', '#b48ae8']

function parse(s?: string) {
  try {
    const d = JSON.parse(s || '')
    return d && d.type === 'doc' ? d : ''
  } catch {
    return ''
  }
}

type Props = { note: Note; busy: boolean; idle: boolean; pace: number; onStatus: (s: Status) => void; onSaved: (n: Note) => void; onAsk: (selection?: string, trigger?: Trigger) => void }

export default function Editor({ note, busy, idle, pace, onStatus, onSaved, onAsk }: Props) {
  const pending = useRef<Partial<Pick<Note, 'title' | 'body_json'>>>({})
  const timer = useRef<number>(undefined)
  const idleTimer = useRef<number>(undefined)
  const lastIdleText = useRef('')
  const paceRef = useRef(pace)
  paceRef.current = pace

  const flush = async (): Promise<boolean> => {
    clearTimeout(timer.current)
    const p = pending.current
    if (!Object.keys(p).length) return true
    pending.current = {}
    try {
      onSaved(await api.patchNote(note.id, p))
      onStatus('saved')
      return true
    } catch {
      pending.current = { ...p, ...pending.current } // keep it so the next edit retries
      onStatus('error')
      return false
    }
  }
  const queue = (p: typeof pending.current) => {
    Object.assign(pending.current, p)
    onStatus('saving')
    clearTimeout(timer.current)
    timer.current = window.setTimeout(flush, 600)
  }
  const flushRef = useRef(flush)
  useEffect(() => {
    flushRef.current = flush
  })
  useEffect(() => () => void flushRef.current(), []) // switching notes must not lose the last edit

  const editor = useEditor({
    extensions: [StarterKit, TextStyle, Color, Slash, Placeholder.configure({ placeholder: "Write anything. Type '/' for blocks." })],
    content: parse(note.body_json),
    onUpdate: ({ editor }) => {
      queue({ body_json: JSON.stringify(editor.getJSON()) })
      clearTimeout(idleTimer.current)
      idleTimer.current = window.setTimeout(() => void idleRef.current(), paceRef.current * 1000) // reading pace: a moment after you stop typing
    },
    editorProps: {
      handleKeyDown: (_v, e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
          e.preventDefault()
          void questionRef.current()
          return true
        }
        return false
      },
    },
  })

  // the server reads the saved note, so save first; skip asking if saving failed
  const question = async () => {
    if (!editor || busy || !(await flush())) return
    const { from, to } = editor.state.selection
    onAsk(from === to ? undefined : editor.state.doc.textBetween(from, to, ' '))
  }
  const explain = async () => {
    if (!editor || busy || !(await flush())) return
    const { from, to } = editor.state.selection
    if (from !== to) onAsk(editor.state.doc.textBetween(from, to, ' '), 'explain')
  }
  // "Reads along": after a pause, if the text changed since last time, let it speak up (it may stay quiet)
  const onIdle = async () => {
    if (!editor || !idle || busy) return
    const text = editor.getText()
    if (text.trim().length < 40 || text === lastIdleText.current) return
    if (!(await flush())) return
    lastIdleText.current = text
    onAsk(undefined, 'idle')
  }
  const questionRef = useRef(question)
  const idleRef = useRef(onIdle)
  useEffect(() => {
    questionRef.current = question
    idleRef.current = onIdle
  })
  useEffect(() => () => clearTimeout(idleTimer.current), [])

  const b = (label: string, active: boolean, run: () => void, title?: string) => (
    <button key={label} className={active ? 'on' : ''} title={title ?? label} onMouseDown={(e) => { e.preventDefault(); run() }}>{label}</button>
  )

  return (
    <>
      <input
        className="title"
        defaultValue={note.title}
        placeholder="Untitled"
        onChange={(e) => queue({ title: e.target.value })}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); editor?.commands.focus('start') } }}
      />
      {editor && (
        <BubbleMenu editor={editor} className="bubble">
          <div className="row">
            {b('T', editor.isActive('paragraph'), () => editor.chain().focus().setParagraph().run(), 'Text')}
            {([1, 2, 3, 4] as const).map((l) => b(`H${l}`, editor.isActive('heading', { level: l }), () => editor.chain().focus().toggleHeading({ level: l }).run()))}
            {b('❝', editor.isActive('blockquote'), () => editor.chain().focus().toggleBlockquote().run(), 'Quote')}
            {b('•', editor.isActive('bulletList'), () => editor.chain().focus().toggleBulletList().run(), 'Bulleted list')}
            {b('1.', editor.isActive('orderedList'), () => editor.chain().focus().toggleOrderedList().run(), 'Numbered list')}
          </div>
          <div className="row">
            {b('B', editor.isActive('bold'), () => editor.chain().focus().toggleBold().run(), 'Bold')}
            {b('I', editor.isActive('italic'), () => editor.chain().focus().toggleItalic().run(), 'Italic')}
            {b('U', editor.isActive('underline'), () => editor.chain().focus().toggleUnderline().run(), 'Underline')}
            {b('S', editor.isActive('strike'), () => editor.chain().focus().toggleStrike().run(), 'Strikethrough')}
            {b('<>', editor.isActive('code'), () => editor.chain().focus().toggleCode().run(), 'Inline code')}
            {b('{ }', editor.isActive('codeBlock'), () => editor.chain().focus().toggleCodeBlock().run(), 'Code block')}
          </div>
          <div className="row">
            {COLORS.map((c) => (
              <button
                key={c}
                className={'swatch' + ((editor.getAttributes('textStyle').color ?? '') === c ? ' on' : '')}
                style={{ color: c || undefined }}
                onMouseDown={(e) => { e.preventDefault(); const ch = editor.chain().focus(); if (c) ch.setColor(c).run(); else ch.unsetColor().run() }}
              >A</button>
            ))}
          </div>
          <div className="row">
            <button className="question" disabled={busy} onMouseDown={(e) => { e.preventDefault(); void question() }}>
              Question this <kbd>⌘↵</kbd>
            </button>
            <button className="question" disabled={busy} onMouseDown={(e) => { e.preventDefault(); void explain() }}>
              Explain this
            </button>
          </div>
        </BubbleMenu>
      )}
      <EditorContent editor={editor} className="body" />
    </>
  )
}
