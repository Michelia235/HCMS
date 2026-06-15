import React, { useState } from 'react'
import { chat } from '../api'

export default function CopilotChat({ videoId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)

  async function send() {
    const q = input.trim()
    if (!q || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: q }])
    setBusy(true)
    try {
      const res = await chat(q, videoId)
      setMessages((m) => [...m, { role: 'bot', text: res.answer }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'bot', text: `Loi: ${e.message}` }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">4. Copilot IPC</h2>

      <div className="mb-3 flex-1 space-y-2 overflow-y-auto" style={{ minHeight: 160, maxHeight: 320 }}>
        {messages.length === 0 && (
          <p className="text-xs text-slate-400">
            Hoi vi du: "Co bao nhieu vi pham?", "Vi pham nghiem trong nhat la gi?"
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
              m.role === 'user'
                ? 'ml-auto bg-sky-600 text-white'
                : 'bg-slate-100 text-slate-700'
            }`}
          >
            {m.text}
          </div>
        ))}
        {busy && <div className="text-xs text-slate-400">Dang nghi...</div>}
      </div>

      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="Hoi ve compliance..."
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none"
        />
        <button
          onClick={send}
          disabled={busy}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
        >
          Gui
        </button>
      </div>
    </div>
  )
}
