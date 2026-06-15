import React, { useRef, useState } from 'react'

export default function UploadPanel({ onUpload, busy }) {
  const inputRef = useRef(null)
  const [name, setName] = useState('')

  function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setName(file.name)
    onUpload(file)
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">1. Tai video</h2>
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={handleFile}
        disabled={busy}
      />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        className="w-full rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
      >
        {busy ? 'Dang xu ly...' : 'Chon video'}
      </button>
      {name && <p className="mt-2 truncate text-xs text-slate-500">{name}</p>}
    </div>
  )
}
