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
  dung UI, API reference, deploy (Render+Vercel), troubleshooting.
- `PLAN_COPILOT.md` - ke hoach + chia task theo track + roadmap.
