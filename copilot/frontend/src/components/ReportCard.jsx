import React from 'react'
import { MOMENT_LABEL, SEVERITY_META } from '../constants'

function CvBadge({ grounding }) {
  if (!grounding) return null
  const meta = {
    confirmed: { label: 'CV-OK', cls: 'bg-cyan-100 text-cyan-700 border-cyan-300',
                 title: 'YOLO xac nhan: tay nam trong vung benh nhan tai thoi diem nay' },
    unconfirmed: { label: 'CV-??', cls: 'bg-amber-100 text-amber-700 border-amber-300',
                   title: 'VLM bao tiep xuc nhung YOLO khong thay tay cham — can review' },
  }[grounding]
  if (!meta) return null
  return (
    <span title={meta.title}
      className={`ml-1 rounded border px-1 text-[9px] font-bold ${meta.cls}`}>
      {meta.label}
    </span>
  )
}

function ScoreGauge({ score }) {
  if (score == null) return <span className="text-slate-400">N/A</span>
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'text-green-600' : pct >= 50 ? 'text-amber-600' : 'text-red-600'
  return <span className={`text-4xl font-bold ${color}`}>{pct}%</span>
}

export default function ReportCard({ analysis }) {
  const findings = analysis?.findings || []
  const violations = findings.filter((f) => f.status === 'violation')
  const compliant = findings.filter((f) => f.status === 'compliant')

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">3. Bao cao compliance (WHO 5 Moments)</h2>

      <div className="mb-4 flex items-center justify-between rounded-lg bg-slate-50 p-3">
        <div>
          <p className="text-xs text-slate-500">Diem tuan thu</p>
          <ScoreGauge score={analysis?.compliance_score} />
        </div>
        <div className="text-right text-xs text-slate-500">
          <p><span className="font-semibold text-red-600">{violations.length}</span> vi pham</p>
          <p><span className="font-semibold text-green-600">{compliant.length}</span> dat</p>
        </div>
      </div>

      {violations.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase text-slate-400">Vi pham</p>
          {violations.map((f, i) => {
            const sev = SEVERITY_META[f.severity] || SEVERITY_META.low
            return (
              <div key={i} className={`rounded-lg border p-2 text-sm ${sev.color}`}>
                <div className="flex items-center justify-between">
                  <span className="font-semibold">
                    {f.rule_name || MOMENT_LABEL[f.moment] || f.rule_id || f.moment}
                    <CvBadge grounding={f.cv_grounding} />
                  </span>
                  <span className="text-[10px] font-bold">{sev.label} · t={f.at_t}s</span>
                </div>
                <p className="mt-0.5 text-xs opacity-90">{f.explanation}</p>
              </div>
            )
          })}
        </div>
      )}

      {compliant.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase text-slate-400">
            Dat ({compliant.length})
          </summary>
          <div className="mt-2 space-y-1">
            {compliant.map((f, i) => (
              <div key={i} className="rounded border border-green-200 bg-green-50 p-2 text-xs text-green-700">
                <span className="font-semibold">{f.rule_name || MOMENT_LABEL[f.moment] || f.rule_id || f.moment}</span>
                <CvBadge grounding={f.cv_grounding} /> · t={f.at_t}s — {f.explanation}
              </div>
            ))}
          </div>
        </details>
      )}

      {findings.length === 0 && (
        <p className="text-sm text-slate-400">Chua phat hien co hoi tuan thu nao.</p>
      )}
    </div>
  )
}
