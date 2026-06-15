# HAND HYGIENE COMPLIANCE COPILOT - PLAN


> San pham tren core HCMS (fork NurViD). Core CV tra ve "cai gi xay ra, luc nao";
> AI agent layer suy luan compliance theo WHO 5 Moments + giao dien.
> MVP truoc, deploy duoc, huong startup. Stack: FastAPI + React.

Ngay bat dau: 2026-06-01 | Owner hien tai: Hiep (solo) | Branch: analysis-hiep-2026-05-20

---

## 0. Y TUONG 1 CAU

```
CV core (YOLOv8/VLM)  ->  event timeline  ->  AI AGENT  ->  verdict + giai thich + chat
                          [{t,"wash"},        (LLM+RAG)     "M2 VI PHAM: tiem t=14s nhung
                           {t,"touch"},                      rua tay cuoi t=2s, sau do cham
                           {t,"inject"}]                     ban t=9s -> tay khong sach"
```

Feature MVP:
- **A. Compliance Reasoner**: doc timeline, doi chieu WHO 5 Moments (RAG guideline), xuat vi pham + severity + giai thich.
- **B. Copilot Chat**: hoi tu nhien tren event DB (text-to-SQL).
- C. Auto-report (sau MVP).

---

## 1. QUYET DINH SCALE (de MVP khong bi block)

| Van de | Quyet dinh MVP | v2 (sau) |
|--------|----------------|----------|
| Detect event | VLM-on-frames (gpt-4o-mini vision) sample thua | YOLOv8 local (team da chot) + VLM judge ca borderline |
| Model CV team | KHONG cho train SlowFast/YOLO | Hiep train YOLOv8 sau khi MVP xong |
| DB | SQLite | Postgres + queue |
| Privacy | faceblur.py truoc khi gui VLM, dung video mau | edge/on-prem |
| Cost | sample 1 frame/giay + quanh doan motion lon | CV local re, VLM chi judge |

---

## 2. KIEN TRUC

```
FRONTEND (React+Vite+Vercel)
  Upload | Video player + timeline markers | Report card | Copilot chat
            | REST / SSE
BACKEND (FastAPI)
  POST /videos      upload + tao job
  GET  /videos/{id} trang thai + ket qua
  POST /chat        copilot Q&A (text-to-SQL)
  pipeline: sample frames -> faceblur -> VLM detect -> timeline
            -> Compliance Agent (LLM + RAG who_5_moments.md) -> SQLite
            | LLM API (gpt-4o-mini)        | storage local -> S3
```

---

## 3. ROADMAP (≈ 3-4 tuan -> deploy)

```
PHASE 0  Setup & contract        (2-3 ngay)  [DONE] scaffold + schema + protocol + VLM validated
PHASE 1  Backend MVP             (1 tuan)     [DONE] pipeline + reasoner + API tested (chua co B2 faceblur)
PHASE 2  Frontend MVP            (1 tuan)     [DONE] React+Vite, npm build sach (152kB). TRACK F0-F4 xong.
PHASE 3  Deploy                  (2-3 ngay)   <-- TIEP THEO (sau khi live e2e pass)
PHASE 4  Iterate: YOLOv8 train, analytics, auth, auto-report, B2 faceblur, B
8 text-to-SQL

## QUOTA / COST (quan trong)
- Gemini free tier = 20 requests/NGAY/model. gemini-2.0-* bi khoa (limit:0) -> dung gemini-2.5-flash.
- FIX da lam: BATCH detect nhieu frame/1 request (BATCH_SIZE=6). 1 video 70s @3s ~24 frame -> ~4 request.
  Free tier xu ~5 video/ngay. Logic batch da validate (mock); LIVE e2e cho quota reset (mai) hoac bat billing.
- Action user: (a) ROTATE Gemini key (da lo trong chat), (b) can nhac bat billing cho video that.
```

## VALIDATION NOTES (2026-06-01)
- VLM detect (gemini-2.5-flash) tren hand_hygiene.avi: event hop ly lam sang, conf 0.8-1.0.
- CAVEAT 1: video la TRAINING MONTAGE co caption ("Before aseptic procedure") -> Gemini doc ca chu
  -> accuracy that (chi nhin hinh) chua do duoc. Can clip KHONG caption + 1 encounter lien tuc.
- CAVEAT 2: aseptic_procedure bi over-detect (gan nhu moi frame) -> score=0.125 la ARTIFACT, KHONG
  phan anh compliance that. Reasoner logic dung; input chua chuan. Fix: tune prompt (chi flag aseptic
  khi co kim/ong tiem/thay bang ro rang) + dung video 1 ca benh thuc.

---

## 4. CHIA TASK THEO TRACK (de sau giao nguoi)

Owner = [HIEP] hien tai. O trong de giao sau.

### TRACK B - Backend / Pipeline / Agent
- [x] B0  Scaffold FastAPI + config + .env loader                          [HIEP] (config.py, main.py)
- [x] B1  Frame sampler (opencv): video -> list frame + timestamp          [HIEP] (vlm.sample_frames)
- [ ] B2  Faceblur integ (dung tools/faceblur.py cua repo)                 [    ] CON LAI - privacy
- [x] B3  VLM event detector: frame -> Event[] (Gemini 2.5-flash)          [HIEP] (vlm.detect_events)
- [x] B4  Timeline builder: gom event, merge trung, sort theo t            [HIEP] (timeline.build)
- [x] B5  Compliance Reasoner: DETERMINISTIC hand-state engine (5 Moments) [HIEP] (reasoner.evaluate)
- [x] B6  SQLite store (videos/result_json)                                [HIEP] (db.py)
- [x] B7  Endpoints: /health /videos POST/GET /chat + CORS                 [HIEP] (main.py, tested)
- [ ] B8  Text-to-SQL tool cho copilot chat (v2; MVP dung RAG-lite JSON)   [    ] DEFER v2

> Quyet dinh: compliance LOGIC deterministic (reproducible/auditable cho y te),
> LLM chi dung cho chat layer (chat.py RAG-lite). Text-to-SQL = v2.

### TRACK F - Frontend (React)  [DONE - frontend/, npm build sach]
- [x] F0  Vite + Tailwind(CDN) skeleton + API client (api.js)             [HIEP]
- [x] F1  Upload page + progress (UploadPanel + poll job)                 [HIEP]
- [x] F2  Video player + timeline markers (VideoTimeline)                 [HIEP]
- [x] F3  Report card (score gauge, vi pham, giai thich) (ReportCard)     [HIEP]
- [x] F4  Copilot chat (CopilotChat; MVP request/response, SSE = v2)      [HIEP]

### TRACK M - ML / CV (v2, sau MVP)
- [ ] M0  Label tap nho event (wash/touch/inject/glove) tren video mau     [    ]
- [ ] M1  Train YOLOv8 detect event (Hiep)                                 [HIEP]
- [ ] M2  Thay VLM-detect bang YOLOv8 local, VLM chi judge borderline      [HIEP]
- [ ] M3  Eval: precision/recall event, agreement vs VLM                   [    ]

### TRACK D - DevOps / Deploy
- [ ] D0  Dockerfile backend                                              [    ]
- [ ] D1  Deploy backend (Render/Railway/Fly/Oracle ARM)                  [    ]
- [ ] D2  Deploy frontend Vercel + noi env                               [    ]
- [ ] D3  CORS, secrets, 1 video demo san                                [    ]

---

## 5. PHASE 0 DELIVERABLE (dang lam)
- [x] Repo structure copilot/
- [x] event_schema.json + schemas.py (pydantic)
- [x] who_5_moments.md (protocol RAG)
- [x] scripts/test_vlm.py (sample frame hand_hygiene.avi -> VLM detect)
- [ ] Chay test_vlm.py thanh cong (can OPENAI_API_KEY)

---

## 6. RISKS
| Risk | Mitigation |
|------|------------|
| VLM detect sai event (false event) | prompt chat che + confidence threshold + B4 merge; v2 dung YOLOv8 |
| Cost VLM cao | sample thua, chi frame quanh motion; v2 CV local |
| Privacy PHI | faceblur truoc khi gui; MVP dung video mau |
| Agent suy luan sai compliance | rule ro trong who_5_moments.md + cite evidence event |
