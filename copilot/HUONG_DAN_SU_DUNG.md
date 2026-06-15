# HUONG DAN SU DUNG - Hand Hygiene Compliance Copilot

> AI agent layer tren core HCMS: upload video -> VLM detect event -> timeline ->
> Compliance Reasoner (WHO 5 Moments) -> verdict + giai thich + chat copilot.
> Stack: **FastAPI (backend) + React/Vite (frontend) + Gemini VLM + SQLite**.

Muc luc:
1. [Tong quan he thong](#1-tong-quan-he-thong)
2. [Yeu cau truoc khi chay](#2-yeu-cau-truoc-khi-chay)
3. [Setup lan dau](#3-setup-lan-dau)
4. [Chay local (backend + frontend)](#4-chay-local)
5. [Dung giao dien web](#5-dung-giao-dien-web)
6. [API reference](#6-api-reference)
7. [Cau hinh (.env)](#7-cau-hinh-env)
8. [Test nhanh khong can UI](#8-test-nhanh)
9. [Deploy (Render + Vercel)](#9-deploy)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Tong quan he thong

```
 BROWSER (React :5173)            BACKEND (FastAPI :8077)            GEMINI VLM
 ─────────────────────           ───────────────────────           ──────────
 1. UploadPanel
    chon video ──POST /videos──▶ luu file + tao job (SQLite)
                ◀─ {video_id,        spawn BackgroundTask
                    "queued"}             │
                                          ▼ pipeline.run_job:
 2. App poll moi ~3s               (a) sample_frames  (opencv, moi N giay)
    ─GET /videos/{id}─▶ processing (b) detect_events  ─batch 6 frame─▶ VLM
                                       (co retry 429 + backoff 503) ◀─ events JSON
                                   (c) timeline.build (merge trung, sort theo t)
                                   (d) reasoner.evaluate  ← DETERMINISTIC engine
                ◀─ done +              (5 Moments, KHONG dung LLM -> auditable)
                   {events, findings, score}
 3. VideoTimeline  ← marker mau theo loai event
    ReportCard     ← score gauge + danh sach vi pham + giai thich
 4. CopilotChat
    hoi ──POST /chat──▶ chat.answer (RAG-lite tren result JSON + LLM)
         ◀─ answer
```

Diem mau chot ve thiet ke:
- **Compliance LOGIC la deterministic** (reasoner.py): rule-based hand-state engine theo
  WHO 5 Moments. Reproducible, auditable cho y te. LLM CHI dung o tang chat.
- **VLM chi lam detect event** (MVP). v2 se thay bang YOLOv8 local, VLM chi judge borderline.
- **Free-tier safe**: batch nhieu frame/1 request (BATCH_SIZE=6) de tiet kiem quota Gemini.

---

## 2. Yeu cau truoc khi chay

| Thanh phan | Phien ban da test | Ghi chu |
|-----------|-------------------|---------|
| Python    | 3.11              | cho backend |
| Node.js   | 22.x (npm 10)     | cho frontend |
| Gemini API key | -            | tao tai https://aistudio.google.com/apikey |
| OS        | Windows 11        | PowerShell; bash cung chay duoc |

`gemini-2.0-*` bi khoa free-tier (limit:0) -> dung **`gemini-2.5-flash`** (mac dinh).

---

## 3. Setup lan dau

### Backend
```powershell
cd D:\Dizim\HCMS\copilot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### Tao file .env
```powershell
Copy-Item .env.example .env
# Mo .env, dien GEMINI_API_KEY=AIza... (key that, KHONG commit)
```

### Frontend
```powershell
cd D:\Dizim\HCMS\copilot\frontend
npm install
Copy-Item .env.example .env   # VITE_API_BASE mac dinh = http://127.0.0.1:8077
```

---

## 4. Chay local

Can **2 terminal** (1 backend, 1 frontend).

### Terminal 1 - backend (port 8077)
```powershell
cd D:\Dizim\HCMS\copilot
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8077
```
Kiem tra: mo http://127.0.0.1:8077/health -> `{"status":"ok","model":"gemini-2.5-flash"}`.
API docs tu dong: http://127.0.0.1:8077/docs (Swagger UI).

> Meo tiet kiem quota khi demo: set sample thua truoc khi chay
> `$env:SAMPLE_EVERY_S = "10"; $env:MAX_FRAMES = "8"` (load_dotenv khong override env da set).

### Terminal 2 - frontend (port 5173)
```powershell
cd D:\Dizim\HCMS\copilot\frontend
npm run dev
```
Mo: **http://127.0.0.1:5173/**

---

## 5. Dung giao dien web

```
┌─────────────────────────────────────────────────────────┐
│  Hand Hygiene Compliance Copilot                         │
├─────────────────────────────────────────────────────────┤
│  [UploadPanel]   Keo tha / chon video .avi .mp4          │
│                  -> bam Upload -> hien progress "processing"│
├─────────────────────────────────────────────────────────┤
│  [VideoTimeline] thanh thoi gian + marker mau:           │
│     ● Ve sinh tay  ● Mang gang  ● Cham BN  ● Thu thuat... │
├─────────────────────────────────────────────────────────┤
│  [ReportCard]    Compliance score (0-1) + danh sach:     │
│     M1 VI PHAM [TRUNG BINH] t=40s: tay khong sach...      │
│     M2 DAT     t=40s: tay sach truoc thu thuat            │
├─────────────────────────────────────────────────────────┤
│  [CopilotChat]   Hoi tu nhien:                           │
│     > "Video nay co vi pham ve sinh tay khong?"          │
│     < "Co. 1 vi pham luc 40.0s: ..."                     │
└─────────────────────────────────────────────────────────┘
```

Luong dung:
1. **Upload** video (1 ca benh, ly tuong la KHONG co caption tren video — xem caveat o muc 10).
2. Doi status chuyen `queued -> processing -> done` (app tu poll ~3s/lan).
3. Xem **timeline** marker + **ReportCard** (score + vi pham + giai thich co cite thoi diem).
4. **Chat** hoi them ve ket qua (vi pham o dau, tai sao, moment nao...).

Y nghia score: ti le moment DAT / tong moment can danh gia. 0.5 = mot nua moment dat.

---

## 6. API reference

Base URL local: `http://127.0.0.1:8077`

| Method | Endpoint | Body | Tra ve |
|--------|----------|------|--------|
| GET  | `/health` | - | `{status, model}` |
| POST | `/videos` | multipart `file` | `{video_id, status:"queued"}` |
| GET  | `/videos/{id}` | - | `{video_id, status, message, result}` |
| POST | `/chat` | `{question, video_id?}` | `{answer, ...}` |

`status` cua job: `queued` -> `processing` -> `done` | `error` (xem `message` khi error).

`result` khi done:
```json
{
  "video_id": "4c1d98398a18",
  "duration_s": 70.0,
  "compliance_score": 0.5,
  "events": [
    {"id":"evt_0000","type":"hand_hygiene","start_t":10.0,
     "confidence":0.9,"frame_idx":290,"evidence":"Doctor rubbing hands..."}
  ],
  "findings": [
    {"moment":"M1","status":"violation","severity":"medium","at_t":40.0,
     "explanation":"Tay khong sach (dang trong chuoi thu thuat...)..."}
  ]
}
```

Loai event (`type`): `hand_hygiene`, `glove_on`, `glove_off`, `touch_patient`,
`touch_surroundings`, `aseptic_procedure`, `body_fluid_exposure`.

Moment WHO: `M1` truoc cham BN, `M2` truoc thu thuat vo trung, `M3` sau nguy co dich,
`M4` sau cham BN, `M5` sau cham moi truong.

---

## 7. Cau hinh (.env)

File `copilot/.env` (backend):

| Bien | Mac dinh | Y nghia |
|------|----------|---------|
| `GEMINI_API_KEY` | (bat buoc) | key Gemini, KHONG commit |
| `GEMINI_MODEL`   | `gemini-2.5-flash` | model VLM |
| `SAMPLE_EVERY_S` | `3.0` | lay 1 frame moi N giay |
| `MAX_FRAMES`     | `40` | tran so frame/video (chong quota chay) |
| `CONF_THRESHOLD` | `0.6` | bo event confidence thap hon |
| `BATCH_SIZE`     | `6` | so frame/1 request Gemini (tiet kiem quota) |
| `CORS_ORIGINS`   | `*` | prod: dat = URL frontend Vercel |

File `frontend/.env`:

| Bien | Mac dinh | Y nghia |
|------|----------|---------|
| `VITE_API_BASE` | `http://127.0.0.1:8077` | URL backend; prod = URL Render |

> Luu y quota: Gemini free tier ~20 request/NGAY/model. 1 video 70s @3s ~24 frame /
> BATCH 6 = ~4 request -> free tier xu ~5 video/ngay. Het quota -> loi 429, doi reset
> hom sau hoac bat billing.

---

## 8. Test nhanh

Chay full pipeline KHONG can HTTP (tien debug):
```powershell
cd D:\Dizim\HCMS\copilot
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe scripts\test_pipeline.py --every 10 --max-frames 8
```
In ra: duration, score, timeline event, findings. Day cung la cach validate quota/key
nhanh nhat (it request).

Test qua HTTP (backend dang chay):
```powershell
# health
curl http://127.0.0.1:8077/health
# upload + lay video_id
curl -F "file=@D:\Dizim\hand_hygiene.avi" http://127.0.0.1:8077/videos
# poll (thay <id>)
curl http://127.0.0.1:8077/videos/<id>
# chat
curl -X POST http://127.0.0.1:8077/chat -H "Content-Type: application/json" `
     -d '{\"question\":\"Co vi pham khong?\",\"video_id\":\"<id>\"}'
```

---

## 9. Deploy

Artifact da chuan bi san: `copilot/Dockerfile`, `render.yaml` (HCMS root),
`frontend/vercel.json`.

### Backend -> Render
1. **ROTATE Gemini key** truoc (key cu da lo trong chat).
2. Push HCMS len GitHub.
3. Render -> New -> **Blueprint** -> tro vao repo (doc `render.yaml`).
4. Set secret `GEMINI_API_KEY` (key MOI) trong dashboard.
5. Sau khi co URL Render -> nho dung cho buoc Vercel.

### Frontend -> Vercel
1. Vercel -> Import repo -> root = `copilot/frontend`.
2. Set env `VITE_API_BASE` = URL backend Render (vd `https://hh-copilot-api.onrender.com`).
3. Deploy. Sau do quay lai Render set `CORS_ORIGINS` = URL Vercel.

```
[GitHub] ──Blueprint──▶ [Render: hh-copilot-api]  ◀──CORS_ORIGINS──┐
                              ▲                                     │
                              │ VITE_API_BASE                       │
                         [Vercel: frontend] ─────────────────────-─┘
```

> CAVEAT Render free: filesystem **ephemeral** -> SQLite + uploads reset moi redeploy.
> OK cho demo; production can persistent disk hoac Postgres.

---

## 10. Troubleshooting

| Trieu chung | Nguyen nhan | Cach xu ly |
|-------------|-------------|------------|
| `429 RESOURCE_EXHAUSTED` | het quota Gemini ngay | doi reset hom sau / bat billing / tang `SAMPLE_EVERY_S` |
| `503 UNAVAILABLE` | Gemini qua tai tam thoi | da co exp-backoff trong vlm._gen, tu retry; neu van loi -> chay lai |
| `GEMINI_API_KEY` rong / 400 | chua dien .env | kiem tra `copilot/.env` co key dung |
| Frontend goi API fail (CORS) | sai `VITE_API_BASE` / `CORS_ORIGINS` | dam bao frontend tro dung URL backend; backend `CORS_ORIGINS` cho phep origin |
| opencv loi `libGL` khi deploy | thieu system lib | da xu ly trong Dockerfile (libgl1, libglib2.0-0) |
| score = 0.125 / aseptic over-detect | video la training-montage co caption (Gemini doc chu) | dung clip 1 ca benh KHONG caption; sample tho hon |
| Job ket `error` | xem field `message` cua `/videos/{id}` | check log uvicorn |

### Caveat ve do chinh xac (quan trong)
Video mau `hand_hygiene.avi` la **training-montage co phu de** ("Before aseptic
procedure"...) -> Gemini doc CA CHU tren video nen accuracy that (chi nhin hinh) chua do
duoc. De danh gia thuc: dung **clip 1 ca benh lien tuc, KHONG caption**.

---

## Lien quan
- `PLAN_COPILOT.md` - ke hoach + chia task theo track (B/F/M/D) + roadmap.
- `agent/protocol/who_5_moments.md` - rule WHO 5 Moments (knowledge base).
- `backend/app/reasoner.py` - deterministic compliance engine.
