import { Extension, type Editor } from '@tiptap/core'
import Suggestion from '@tiptap/suggestion'

type Item = { title: string; icon: string; run: (e: Editor) => void }

const ITEMS: Item[] = [
  { title: 'Text', icon: 'T', run: (e) => e.chain().setParagraph().run() },
  { title: 'Heading 1', icon: 'H1', run: (e) => e.chain().setHeading({ level: 1 }).run() },
  { title: 'Heading 2', icon: 'H2', run: (e) => e.chain().setHeading({ level: 2 }).run() },
  { title: 'Heading 3', icon: 'H3', run: (e) => e.chain().setHeading({ level: 3 }).run() },
  { title: 'Heading 4', icon: 'H4', run: (e) => e.chain().setHeading({ level: 4 }).run() },
  { title: 'Bulleted list', icon: '•', run: (e) => e.chain().toggleBulletList().run() },
  { title: 'Numbered list', icon: '1.', run: (e) => e.chain().toggleOrderedList().run() },
  { title: 'Quote', icon: '❝', run: (e) => e.chain().toggleBlockquote().run() },
  { title: 'Code block', icon: '</>', run: (e) => e.chain().toggleCodeBlock().run() },
]

export const Slash = Extension.create({
  name: 'slash',
  addProseMirrorPlugins() {
    return [
      Suggestion<Item>({
        editor: this.editor,
        char: '/',
        startOfLine: true,
        items: ({ query }) => ITEMS.filter((i) => i.title.toLowerCase().includes(query.toLowerCase())),
        command: ({ editor, range, props }) => {
          editor.chain().focus().deleteRange(range).run()
          props.run(editor)
        },
        render: () => {
          const el = document.createElement('div')
          el.className = 'slash'
          let items: Item[] = []
          let sel = 0
          let pick: (i: Item) => void = () => {}
          const draw = () => {
            el.replaceChildren(
              ...items.map((it, i) => {
                const b = document.createElement('button')
                b.className = 'slash-item' + (i === sel ? ' on' : '')
                const icon = document.createElement('span')
                icon.textContent = it.icon
                b.append(icon, it.title)
                b.onmousedown = (ev) => { ev.preventDefault(); pick(it) }
                return b
              }),
            )
          }
          const place = (rect: (() => DOMRect | null) | null | undefined) => {
            const r = rect?.()
            if (r) { el.style.left = `${r.left}px`; el.style.top = `${r.bottom + 6}px` }
          }
          return {
            onStart: (p) => { items = p.items; sel = 0; pick = p.command; document.body.append(el); draw(); place(p.clientRect) },
            onUpdate: (p) => { items = p.items; sel = 0; pick = p.command; draw(); place(p.clientRect) },
            onKeyDown: ({ event }) => {
              if (!items.length) return false
              if (event.key === 'ArrowDown') sel = (sel + 1) % items.length
              else if (event.key === 'ArrowUp') sel = (sel - 1 + items.length) % items.length
              else if (event.key === 'Enter') { pick(items[sel]); return true }
              else return false
              draw()
              return true
            },
            onExit: () => el.remove(),
          }
        },
      }),
    ]
  },
})
