# DEPLOY - Hand Hygiene Compliance Copilot

> Tai lieu nay giai thich **kien truc deploy** + **tung buoc** dua copilot len internet.
> Doc cho ca team biet "dang lam gi, vi sao". Setup chay LOCAL xem `HUONG_DAN_SU_DUNG.md`.

Owner: Hiep | Repo: `github.com/Michelia235/HCMS` | Branch: `analysis-hiep-2026-05-20`

---

## 0. TL;DR (lam gi, theo thu tu)

```
1. Backend  -> Render  (Docker, doc render.yaml)   -> co URL .onrender.com
2. Frontend -> Vercel  (root = copilot/frontend)   -> set VITE_API_BASE = URL Render
3. Quay lai Render -> set CORS_ORIGINS = URL Vercel
4. Test: mo URL Vercel -> upload 1 clip -> xem verdict + chat
```

Hai service mien phi, KHONG can the tin dung. Thoi gian ~30 phut.

---

## 1. KIEN TRUC DEPLOY (so do)

```
        nguoi dung
            │  (mo trinh duyet)
            ▼
   ┌─────────────────────┐        REST / fetch        ┌──────────────────────────┐
   │  VERCEL              │ ─────────────────────────▶ │  RENDER                  │
   │  frontend React+Vite │  POST /videos, /chat ...   │  backend FastAPI (Docker)│
   │  (static, CDN)       │ ◀───────────────────────── │  uvicorn app.main:app    │
   │  env: VITE_API_BASE  │        JSON ket qua        │  env: GEMINI_API_KEY     │
   └─────────────────────┘                            │       CORS_ORIGINS       │
                                                       └───────────┬──────────────┘
                                                                   │ goi VLM
                                                                   ▼
                                                          ┌─────────────────┐
                                                          │  Google Gemini  │
                                                          │  2.5-flash      │
                                                          └─────────────────┘
```

- **Frontend (Vercel)**: chi la static build (HTML/JS), khong co logic mat. Biet backend
  o dau qua bien `VITE_API_BASE` (build-time). Vercel serve qua CDN, mien phi.
- **Backend (Render)**: chay Docker image build tu `copilot/Dockerfile`. Nhan upload, sample
  frame, goi Gemini detect event, chay reasoner, tra verdict. Can secret `GEMINI_API_KEY`.
- **CORS**: trinh duyet chan request cross-origin tru khi backend cho phep. `CORS_ORIGINS`
  tren Render phai = dung URL Vercel thi frontend moi goi duoc API.

---

## 2. VI SAO CHON STACK NAY

| Quyet dinh | Ly do |
|------------|-------|
| Render cho backend | Free tier chay **Docker** that (opencv + onnxruntime nang, Vercel serverless khong hop). Co Blueprint doc `render.yaml` tu dong. |
| Vercel cho frontend | Vite static deploy 1-click, CDN nhanh, free. |
| Docker (khong buildpack) | Backend can system lib `libGL`/`libglib2` cho opencv -> Dockerfile kiem soat duoc (buildpack thi khong). |
| SQLite (khong Postgres) | MVP. Du cho demo. Postgres = v2 khi can persist that. |

---

## 3. CHUAN BI (da co san trong repo)

| File | Vai tro |
|------|---------|
| `copilot/Dockerfile` | build backend image (python3.11-slim + libGL + deps + code) |
| `render.yaml` (HCMS root) | Render Blueprint: khai bao service, env, healthcheck `/health` |
| `copilot/frontend/vercel.json` | cau hinh Vercel (SPA rewrite) |
| `copilot/frontend/.env.example` | mau bien `VITE_API_BASE` |
| `copilot/.env.example` | mau bien backend (GEMINI_API_KEY...) |

Tat ca da commit. **KHONG commit**: `.env` that, weights (`*.onnx`/`*.pt`), `copilot.sqlite`,
`uploads/`, `.venv/` (xem `copilot/.gitignore`).

---

## 4. BUOC 1 - BACKEND LEN RENDER

### 4.1. Chuan bi key
- Vao [Google AI Studio](https://aistudio.google.com/apikey) tao **GEMINI_API_KEY moi** (rotate).
  > Key cu da tung lo trong chat -> KHONG dung lai. Key chi dan vao Render secret, KHONG commit.

### 4.2. Tao service
1. Dang nhap [render.com](https://render.com) (login bang GitHub).
2. **New** -> **Blueprint**.
3. Chon repo `Michelia235/HCMS`, branch `analysis-hiep-2026-05-20`.
4. Render doc `render.yaml` -> tao service `hh-copilot-api` (runtime Docker, plan free).
5. Truoc khi **Apply**: o muc Environment, dien cac bien co `sync: false`:
   - `GEMINI_API_KEY` = key vua tao (secret, KHONG hien trong yaml).
   - `CORS_ORIGINS` = tam de `*` (se siet lai o Buoc 3 sau khi co URL Vercel).
6. **Apply** -> Render build Docker (~3-5 phut lan dau) -> chay.

### 4.3. Verify backend song
- Render cap URL dang `https://hh-copilot-api.onrender.com`.
- Mo `https://<URL>/health` -> phai tra `{"status":"ok"}` (healthcheck path trong yaml).
- **GHI LAI URL nay** -> dung cho Buoc 2.

> Bien env mac dinh trong `render.yaml`: `GEMINI_MODEL=gemini-2.5-flash`, `SAMPLE_EVERY_S=3.0`,
> `MAX_FRAMES=40`, `BATCH_SIZE=6`. Doi duoc trong dashboard khong can rebuild code.

---

## 5. BUOC 2 - FRONTEND LEN VERCEL

1. Dang nhap [vercel.com](https://vercel.com) (login GitHub).
2. **Add New** -> **Project** -> import `Michelia235/HCMS`.
3. **Root Directory** = `copilot/frontend` (QUAN TRONG, khong phai repo root).
   - Framework Preset: Vite (Vercel tu nhan).
4. **Environment Variables**: them
   - `VITE_API_BASE` = URL Render o Buoc 4.3 (vd `https://hh-copilot-api.onrender.com`, KHONG co `/` cuoi).
5. **Deploy** -> Vercel build (~1 phut) -> cap URL dang `https://<ten>.vercel.app`.

---

## 6. BUOC 3 - NOI 2 BEN (CORS)

1. Quay lai Render -> service `hh-copilot-api` -> **Environment**.
2. Sua `CORS_ORIGINS` = URL Vercel (vd `https://hh-copilot.vercel.app`, KHONG co `/` cuoi).
   - Nhieu origin thi ngan cach bang dau phay.
3. Save -> Render tu redeploy (~1 phut).

Xong. Mo URL Vercel -> upload clip -> verdict + chat chay qua backend Render.

---

## 7. GOTCHAS (PHAI BIET)

| Van de | Giai thich | Cach xu ly |
|--------|------------|------------|
| **CV grounding khong chay tren Render** | `best.onnx` (role model) bi gitignore (102MB, qua nang) -> backend **VLM-only**, khong co badge "CV-OK". | Chap nhan cho demo; hoac fetch weights qua git-lfs / tai tu Drive luc build (defer). |
| **SQLite + uploads reset** | Render free filesystem **ephemeral** -> moi redeploy hoac sleep mat het du lieu cu. | OK cho demo. Persist that = Render Disk (tra phi) hoac Postgres + S3. |
| **Backend "ngu" sau 15 phut** | Render free spin-down khi khong co request -> lan goi dau cham ~30-50s (cold start). | Binh thuong. Demo thi warm truoc bang `/health`. |
| **Quota Gemini free** | 2.5-flash free = ~5 req/phut + cap/ngay. 1 video ~4 req (batch 6 frame). | Demo it video thi du. Nhieu thi bat billing Google. |
| **CORS bi chan** | Frontend goi API loi "blocked by CORS". | `CORS_ORIGINS` tren Render phai khop CHINH XAC URL Vercel (khong `/` cuoi, dung https). |
| **VITE_API_BASE sai** | Frontend goi `127.0.0.1` thay vi Render. | Phai set env tren Vercel **truoc khi build**; doi env phai redeploy. |

---

## 8. CHI PHI

| Service | Plan | Phi |
|---------|------|-----|
| Render | Free web service | 0 (co spin-down + FS ephemeral) |
| Vercel | Hobby | 0 |
| Gemini | Free tier | 0 (gioi han req/phut + /ngay); billing neu vuot |

Tong = **0 dong** cho demo. Khong can the tin dung.

---

## 9. SAU KHI DEPLOY (next)

- [ ] Smoke test: `/health` 200 + upload 1 clip qua UI Vercel -> verdict dung.
- [ ] (Tuy chon) Tao Pull Request merge `analysis-hiep-2026-05-20` -> branch chinh khi team duyet.
- [ ] (v2) Persist that: Postgres + object storage cho uploads.
- [ ] (v2) Ship weights de bat CV grounding live tren server (git-lfs hoac fetch luc build).
- [ ] (v2) Auth + faceblur truoc khi xu ly video that (privacy PHI).

---

## Lien quan
- `HUONG_DAN_SU_DUNG.md` - chay local, dung UI, API reference, troubleshooting.
- `ARCHITECTURE.md` - kien truc ky thuat end-to-end.
- `render.yaml` (HCMS root) - Blueprint Render.
