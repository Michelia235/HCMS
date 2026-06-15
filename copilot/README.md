# Hand Hygiene Compliance Copilot

AI agent layer tren core HCMS: bien event timeline tu CV thanh **verdict compliance
theo WHO 5 Moments** + chat copilot. Stack: FastAPI + React. Xem `PLAN_COPILOT.md`.

## Cau truc
```
copilot/
  PLAN_COPILOT.md          ke hoach + chia task theo track
  agent/
    protocol/who_5_moments.md   rule compliance (RAG knowledge base)
    schemas/event_schema.json   contract event (json-schema)
  backend/
    app/schemas.py              pydantic schema (single source of truth)
    requirements.txt
  scripts/test_vlm.py           Phase 0 smoke test VLM-on-frames
  frontend/                     React (Phase 2)
```

## Chay thu nhanh
```powershell
cd D:\Dizim\HCMS\copilot
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item .env.example .env   # dien GEMINI_API_KEY
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe scripts\test_pipeline.py --every 10 --max-frames 8
```

## Tai lieu
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - tai lieu KY THUAT end-to-end: kien truc,
  data flow, tung layer (VLM detect -> timeline -> reasoner -> CV role-aware
  grounding -> chat -> API -> frontend), trang thai phase, han che.
- **[HUONG_DAN_SU_DUNG.md](HUONG_DAN_SU_DUNG.md)** - setup, chay local (backend+frontend),
  dung UI, API reference, troubleshooting.
- **[DEPLOY.md](DEPLOY.md)** - huong dan deploy CHI TIET (Render backend + Vercel frontend):
  kien truc, tung buoc, gotchas (CV grounding, ephemeral FS, CORS, quota), chi phi.
- **[DEMO.md](DEMO.md)** - kich ban demo (web app + camera real-time) + **demo-safe mode**
  (replay clip demo, khong chet quota Gemini) + cau hoi/tra loi.
- **[PILOT_PROPOSAL.md](PILOT_PROPOSAL.md)** - de xuat trien khai thu tai benh vien
  (chao moi): van de, giai phap, rieng tu, ke hoach trial, metric.
- `PLAN_COPILOT.md` - ke hoach + chia task theo track + roadmap.
