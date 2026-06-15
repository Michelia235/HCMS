const BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8077'

export async function uploadVideo(file) {
  const fd = new FormData()
  fd.append('file', file)
  const r = await fetch(`${BASE}/videos`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error(`upload failed (${r.status})`)
  return r.json()
}

export async function getJob(videoId) {
  const r = await fetch(`${BASE}/videos/${videoId}`)
  if (!r.ok) throw new Error(`get job failed (${r.status})`)
  return r.json()
}

export async function chat(question, videoId) {
  const r = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, video_id: videoId || null }),
  })
  if (!r.ok) throw new Error(`chat failed (${r.status})`)
  return r.json()
}
