"""Track B7/B8 (MVP): copilot Q&A over stored analyses.

MVP uses RAG-lite: feed the relevant analysis JSON as context to Gemini and ask
in Vietnamese. Text-to-SQL over a real events table is the v2 upgrade (B8).
"""
from __future__ import annotations

import json

from . import db, gemini
from .schemas import ChatResponse, VideoAnalysis

SYSTEM = """Ban la tro ly IPC (kiem soat nhiem khuan). Tra loi NGAN GON bang tieng Viet
khong dau, CHI dua tren du lieu compliance duoi day. Neu du lieu khong du de tra loi,
noi ro la khong du du lieu. Luon trich timestamp/so vi pham cu the khi co the."""


def _context(analyses: list[VideoAnalysis], limit: int = 5) -> str:
    rows = []
    for a in analyses[:limit]:
        rows.append({
            "video_id": a.video_id,
            "duration_s": a.duration_s,
            "compliance_score": a.compliance_score,
            "violations": [
                {"rule": f.rule_id or (f.moment.value if f.moment else None),
                 "name": f.rule_name,
                 "moment": f.moment.value if f.moment else None,
                 "severity": (f.severity.value if f.severity else None),
                 "at_t": f.at_t, "why": f.explanation}
                for f in a.findings if f.status.value == "violation"
            ],
            "n_events": len(a.events),
        })
    return json.dumps(rows, ensure_ascii=False)


def answer(question: str, video_id: str | None = None) -> ChatResponse:
    if video_id:
        job = db.get(video_id)
        analyses = [job.result] if job and job.result else []
    else:
        analyses = db.list_results()

    if not analyses:
        return ChatResponse(answer="Chua co du lieu phan tich nao de tra loi.")

    prompt = f"{SYSTEM}\n\n=== DU LIEU ===\n{_context(analyses)}\n\n=== CAU HOI ===\n{question}"
    resp = gemini.generate(prompt)
    return ChatResponse(answer=(resp.text or "").strip())
