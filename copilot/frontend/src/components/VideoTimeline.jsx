import React from 'react'
import { EVENT_META } from '../constants'

// Horizontal timeline 0..duration with event ticks + violation markers.
export default function VideoTimeline({ analysis, videoUrl, videoRef }) {
  const duration = analysis?.duration_s || 0
  const events = analysis?.events || []
  const violations = (analysis?.findings || []).filter((f) => f.status === 'violation')

  const pct = (t) => (duration > 0 ? Math.min(100, (t / duration) * 100) : 0)

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">2. Video & dong thoi gian</h2>

      {videoUrl ? (
        <video
          ref={videoRef}
          src={videoUrl}
          controls
          className="mb-4 w-full rounded-lg bg-black"
          style={{ maxHeight: 320 }}
        />
      ) : (
        <div className="mb-4 flex h-40 items-center justify-center rounded-lg bg-slate-100 text-sm text-slate-400">
          Chua co video
        </div>
      )}

      {/* event track */}
      <div className="relative mb-1 h-8 rounded bg-slate-100">
        {events.map((e) => {
          const meta = EVENT_META[e.type] || { color: '#64748b', label: e.type }
          return (
            <button
              key={e.id}
              title={`${meta.label} @ ${e.start_t}s (${e.evidence || ''})`}
              onClick={() => videoRef?.current && (videoRef.current.currentTime = e.start_t)}
              className="absolute top-1 h-6 w-1.5 -translate-x-1/2 rounded-sm"
              style={{ left: `${pct(e.start_t)}%`, backgroundColor: meta.color }}
            />
          )
        })}
      </div>
      {/* violation track */}
      <div className="relative h-4">
        {violations.map((v, i) => (
          <div
            key={i}
            title={`${v.moment} VI PHAM @ ${v.at_t}s: ${v.explanation}`}
            className="absolute top-0 h-0 w-0 -translate-x-1/2"
            style={{
              left: `${pct(v.at_t)}%`,
              borderLeft: '5px solid transparent',
              borderRight: '5px solid transparent',
              borderTop: '7px solid #dc2626',
            }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-slate-400">
        <span>0s</span>
        <span>{duration}s</span>
      </div>

      {/* legend */}
      <div className="mt-3 flex flex-wrap gap-2">
        {Object.entries(EVENT_META).map(([k, m]) => (
          <span key={k} className="flex items-center gap-1 text-[11px] text-slate-500">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: m.color }} />
            {m.label}
          </span>
        ))}
      </div>
    </div>
  )
}
