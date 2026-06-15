# Hand Hygiene Compliance Copilot — Tai lieu End-to-End

> Tai lieu KY THUAT chi tiet toan bo he thong: tu video dau vao -> verdict WHO 5
> Moments + chat copilot. Bo tro cho `README.md` (tong quan) va
> `HUONG_DAN_SU_DUNG.md` (setup/run/deploy/UI). Doc nay tap trung vao
> **kien truc, data flow, va tung layer**.

---

## 0. He thong giai quyet van de gi

WHO dinh nghia **5 Moments for Hand Hygiene** — 5 thoi diem ma nhan vien y te
(HCW) BAT BUOC ve sinh tay:

| Moment | Khi nao | Loai |
|--------|---------|------|
| M1 | TRUOC khi cham benh nhan (BN) | truoc |
| M2 | TRUOC thu thuat vo trung (aseptic) | truoc |
| M3 | SAU nguy co tiep xuc dich co the | sau |
| M4 | SAU khi cham BN | sau |
| M5 | SAU khi cham moi truong quanh BN | sau |

Van de cot loi: **compliance la van de THOI GIAN** (trang thai tay sach/ban tai
dung thoi diem hanh dong), khong phai chi nhan dien 1 frame. => can mot
**temporal reasoner** chay tren chuoi event, khong phai 1 classifier anh.

San pham = **lop AI agent** dat tren core CV (HCMS, fork NurViD). No bien
**event timeline** thanh **verdict compliance** + tra loi chat bang ngon ngu tu
nhien.

---

## 1. So do end-to-end

```
                         VIDEO (.mp4/.avi)
                              |
        ┌─────────────────────┴───────────────────────┐
        |                                              |
   [A] VLM-on-frames                          [D] CV Perception Layer
   (vlm.py, Gemini)                           (perception/, YOLOv8, LOCAL)
        | sample frames -> batch                       | role_overlay.py:
        | -> Gemini vision -> raw events                |  best.pt (doctor/
        v                                               |  nurse/patient)
   [B] Timeline build                                   |  -> role boxes
   (timeline.py)                                        |  -> HCW<->patient
        | merge/dedupe -> Event[]                       |     contact_segments
        v                                               v
   [C] Deterministic Reasoner  <───── contact_segments (sidecar .contact.json)
   (reasoner.py, 5 Moments hand-state machine)
        | findings[] + compliance_score
        | + cv_grounding tag (confirmed/unconfirmed) tren tung finding
        v
   [E] FastAPI  (main.py)  ──/videos ──/videos/{id} ──/chat──┐
        | SQLite (db.py) luu job + result                     |
        v                                                     v
   [G] React Frontend                              [F] Chat Copilot (chat.py)
   (Upload / Timeline / ReportCard / Chat)          RAG-lite: analysis JSON
                                                    -> Gemini -> tra loi TV
```

Hai **lan detect doc lap** ([A] VLM ngu nghia + [D] CV khong gian) gap nhau o
reasoner [C]: VLM noi "co touch_patient luc t", CV noi "co thuc su HCW cham
PATIENT luc t" -> **cross-check**.

---

## 2. Data contract (`backend/app/schemas.py`)

Single source of truth (pydantic). Mirror `agent/schemas/event_schema.json`.

**Event** — 1 hanh vi quan sat duoc:
```
type: hand_hygiene | glove_on | glove_off | touch_patient |
      touch_surroundings | aseptic_procedure | body_fluid_exposure
start_t, end_t (s) | confidence (0..1) | frame_idx | evidence (text)
```

**ComplianceFinding** — 1 ket luan cho 1 Moment:
```
moment: M1..M5 | status: compliant|violation|not_applicable
severity: high|medium|low | at_t | evidence_event_ids[] | explanation
cv_grounding: "confirmed" | "unconfirmed" | None   <- tin hieu CV (muc 4)
```

**VideoAnalysis** = { video_id, duration_s, events[], findings[],
compliance_score } ; **compliance_score = compliant / tong so opportunity**.

---

## 3. Layer A — VLM-on-frames detector (`vlm.py`)

**Quyet dinh scale**: MVP KHONG train action model (SlowFast/I3D). Dung
**Gemini vision** doc truc tiep frame -> event. Re, nhanh, du cho demo.

Flow:
1. `sample_frames(video, every_s, max_frames)` — lay 1 frame moi `every_s` giay
   (default 3s), toi da `max_frames` (default 40).
2. Gom frame thanh **batch** (default 6 frame / request) — Gemini nhan nhieu
   anh / call -> tiet kiem quota free-tier.
3. `BATCH_PROMPT`: yeu cau Gemini, voi MOI frame, tra **STRICT JSON**
   `{"frames":[{"i":idx,"events":[{type,confidence,evidence}]}]}`. Prompt ep
   _conservative_ (vd chi bao `aseptic_procedure` khi thay ro kim/syringe).
4. `_gen()` — retry co backoff:
   - `429 RESOURCE_EXHAUSTED` (qua RPM): doi theo `retry in Xs` server goi y.
   - `503 UNAVAILABLE / 500` (overload tam thoi): exponential backoff.
   - **Khong** cuu duoc daily cap free-tier.
5. Loc theo `CONF_THRESHOLD` (0.6), map sang `Event`.

Output: `(duration_s, list[Event])`.

> Gotcha da gap: video co **caption chu** (training montage) -> Gemini doc chu
> thay vi nhin hanh vi. Demo phai dung clip KHONG caption. Shot rong de bi doc
> nham `touch_surroundings`; `hand_hygiene` chi bat tot tren close-up rua tay.

---

## 4. Layer B — Timeline build (`timeline.py`)

VLM emit nhieu event trung (cung hanh dong keo dai qua nhieu frame ke nhau, hoac
2 actor cung rua tay). Reasoner can **1 event / (type, cum-thoi-gian)**.

`build()`: sort theo (start_t, type); gom event cung `type` cach nhau
<= `MERGE_WINDOW_S` (6s) thanh 1 (mo rong `end_t`, giu confidence cao nhat); danh
lai `id` `evt_0000...`. MVP gia dinh **1 primary actor**.

---

## 5. Layer C — Config-driven compliance engine (`reasoner.py` + `protocol.py`)  ★ trai tim he thong

**Quyet dinh thiet ke (san pham y te)**: logic compliance la **DETERMINISTIC**,
KHONG giao cho LLM -> verdict **reproducible + auditable**. LLM chi dung o chat.

**POLICY-AS-CONFIG (2026-06-10)**: logic y te gio nam trong **file JSON benh vien
chinh duoc** (`agent/protocol/who_5_moments.json`, doi qua `PROTOCOL_JSON_PATH`),
KHONG hardcode. `reasoner.py` la **interpreter generic**; `protocol.py` = pydantic
schema + loader. Them luat "rua tay >= 10s" / thu tu / nguong = **sua JSON, khong
sua code, khong train lai model**.
- **RANH GIOI quan trong**: chi doi duoc luat tren EVENT da nhan dien duoc. Them
  QUAN SAT moi (vd "deo khau trang") -> van phai day detector (VLM vocab / CV).
- **Protocol schema**: `hand_state.clean_on/dirty_on` (event lam tay sach/ban);
  `flags.<ten>.set_on/clear_on` (co pending nhu fluid/surroundings); `rules[]` moi
  rule = `{id, moment?, on:[event], opportunity, require, severity, ok/bad}`.
- **require (1 trong)**: `{"hands":"clean"}` | `{"flag_clear/flag_set":"<flag>"}` |
  `{"min_duration_s":n}` | `{"hygiene_before_next":[events]}` (nhin TOI, = M4) |
  `{"hygiene_within_before_s":n}` (cua so thoi gian TRUOC trigger).
- **opportunity**: true -> emit COMPLIANT khi dat (tinh vao score); false -> chi
  emit khi VI PHAM (vd M3/M4/M5).
- **aggregate[]**: luat nguong/dem hau ky -> `compliance_rate` | `violation_count`
  | `violation_count_for:<rule_id>` voi op lt/le/gt/ge (vd canh bao ca truc < 80%).
- `ComplianceFinding` them `rule_id`+`rule_name`; `moment` gio Optional (None cho
  luat custom khong phai WHO). Vi du: `agent/protocol/hospital_example.json`.
- **28 unit test PASS**: 19 tai lap dung WHO-5 tu config + 9 cho rule type moi
  (min_duration, window, aggregate, custom-rule-no-moment).

### Hand-state machine
Trang thai `hands_clean ∈ {True, False, None}`:
- `hand_hygiene` -> **CLEAN** (reset: xoa contaminator, surroundings/fluid pending).
- `touch_patient | touch_surroundings | body_fluid_exposure | glove_off` ->
  **CONTAMINATED**.
- 1 Moment **COMPLIANT** khi tay CLEAN ngay tai thoi diem hanh dong; nguoc lai
  **VIOLATION**.

### Cach phat sinh tung Moment (duyet event theo thoi gian)
```
hand_hygiene        -> clean_state()
touch_patient       -> M1 (truoc cham BN: clean? compliant : violation/medium)
                       + neu surroundings_pending -> M5 violation/low
                       + neu fluid_pending        -> M3 violation/high
                       -> hands DIRTY, mo open_patient_contact
aseptic_procedure   -> M2 (clean? compliant : violation/high)
                       + neu fluid_pending        -> M3 violation/high
touch_surroundings  -> DIRTY, surroundings_pending = True
body_fluid_exposure -> DIRTY, fluid_pending = True
glove_off           -> DIRTY
glove_on            -> khong doi (bao ho, khong lam ban tay trong model nay)
```
**M4** (`_m4_pass`): sau moi `touch_patient`, neu hanh dong "sach" ke tiep
(touch_patient/aseptic) den TRUOC khi co `hand_hygiene` -> violation/low.

`compliance_score = #compliant / #opportunity` (opportunity = finding !=
not_applicable). Khong co opportunity -> score = None.

---

## 6. Layer D — CV Perception Layer (role-aware grounding)  ★ phan moi merge

### 6.1 Tai sao can
VLM la **ngu nghia** (semantic) nhung **khong co khong gian** (spatial): no "tin"
co touch_patient ma khong chung minh duoc tay AI cham AI. CV layer them
**bang chung khong gian doc lap** -> tang/giam do tin cay (confidence), KHONG doi
verdict (verdict van do reasoner quyet, de auditable).

### 6.2 Role detection model (tu CV engineer)
`perception/weight_v2/best.pt` — **YOLOv8m DETECT** fine-tune tu `yolov8m.pt`,
100 epochs, imgsz 640, tren custom hospital dataset.
- **Classes**: `{0: doctor, 1: nurse, 2: patient}` — detect ROLE truc tiep.
- Quality: mAP50 **0.78**, mAP50-95 0.55, P 0.88, R 0.70.
- Recall ~0.70 (miss ~30%) -> dung lam **confidence signal**, KHONG du tin cay
  de quyet verdict. Khop voi design.

### 6.3 `perception/role_overlay.py` (merge code)
Chay `best.pt` moi N frame (default every=3):
1. Ve **role box mau**: doctor=xanh duong, nurse=xanh la, patient=cam +
   confidence; banner "HCW-PATIENT CONTACT" khi co tiep xuc.
2. **Contact ROLE-AWARE**: tinh khoang cach box-box (chuan hoa theo duong cheo
   frame) giua HCW (doctor|nurse) va PATIENT. `dist <= NEAR_FRAC (0.03)` (hoac
   overlap = 0) -> "contact candidate". Merge frame lien tuc (gap <= 0.6s, bo
   blip < 0.3s) -> **contact_segments**.

> Day la nang cap so voi `proximity.py` cu (role-BLIND: "tay bat ky trong box
> bat ky"). Gio contact = "HCW thuc su lai gan PATIENT" — dung y nghia M1/M4.

3. Outputs:
   - `--out`     annotated mp4 (de demo/audit bang mat).
   - `--json`    per-frame roles + boxes (audit trail).
   - `--contact` `{contact_segments:[{start_t,end_t,min_dist,inside_box,kind}]}`
     — **CUNG SCHEMA** reasoner doc -> backend khong can sua.

### 6.4 Hai duong chay: precompute (offline) VA inline ONNX (live)
- **Offline (role_overlay.py)**: chay `best.pt` (ultralytics + torch, system
  python) -> annotated video + `.contact.json` precompute. Dung de tao demo /
  sidecar curated (sampling day hon, chat luong cao hon).
- **Inline ONNX (`backend/app/role_detect.py`)** — moi (#5): export `best.pt` ->
  `best.onnx`, chay bang **onnxruntime + opencv THOI** (KHONG torch/ultralytics)
  ngay trong backend. => ground **MOI video upload** tu dong, khong can sidecar.
  - YOLOv8 ONNX postproc tu viet: letterbox 640 -> infer -> output (1,7,8400)
    -> decode xywh + class score -> `cv2.dnn.NMSBoxes` -> scale ve toa do goc.
  - Lazy + optional: thieu onnxruntime hoac thieu `.onnx` -> `available()=False`
    -> VLM-only (graceful). KHONG bao gio lam fail job (try/except best-effort).
  - Cost: YOLOv8m@640 tren CPU ~0.5-0.6s/frame. Bound bang `ROLE_SAMPLE_EVERY_S`
    (0.4s ~ 2.5fps) + `ROLE_MAX_FRAMES` (80) -> toi da ~40s grounding/job.
  - int8 dynamic quant: model 99MB->26MB NHUNG CPU nay KHONG co int8 accel ->
    cham hon (4.8s/frame) -> BO, dung fp32.

> Deploy note: `best.onnx` (99MB) bi gitignore (`*.onnx`). De backend deploy
> co model: hoac (a) commit rieng/git-lfs, hoac (b) fetch tu Drive luc startup,
> hoac (c) bo qua -> deploy chay VLM-only. Local thi da co san -> live ngay.

### 6.6 Deep grounding: hand-in-box + tracking (`perception/track_grounding.py`)
Tang sau nhat — tra loi AI cham AI, BANG TAY NAO, theo THOI GIAN:
```
pose model (yolov8m-pose) + ByteTrack -> person ID ben vung + co tay (wrist)
role model (best.pt)                  -> doctor/nurse/patient
fuse IoU pose-box <-> role-box (PER FRAME)  -> moi nguoi biet role
contact = wrist cua HCW NAM TRONG box PATIENT  -> segment (hcw_id, patient_id, hand)
```
Manh hon 6.3 (box-overlap): `touch_patient` duoc chung minh boi 1 BAN TAY thuc su
vao vung benh nhan, gan voi HCW + patient cu the. Output: annotated mp4 (role#id
+ wrist + banner "HAND-IN-PATIENT a->b") + contact JSON reasoner-compatible.
- VERIFY: violation -> 3 hand-contact (HCW hand vao patient box luc ~1s va ~6-8s);
  compliant -> 1 hand-contact 9.1-13.9s va KHONG co luc rua tay (t=0-5s) = thu tu
  dung (hygiene TRUOC, contact SAU). Canh compliant la MULTI-PERSON (nhieu nurse
  + 1 patient) -> tracking xu ly da actor (vuot gia dinh single-actor).
- GOTCHA: role gan PER-FRAME (KHONG majority-theo-track) vi frame-skip (every=3)
  lam ByteTrack doi ID luc overlap -> vote bi nhiem. ID van flicker (best-effort
  metadata); contact (start/end) van dung. Role-model recall 0.70 -> co frame
  'unknown' + dau clip role co the lap (FP nhe). Giam bang every=1 (ByteTrack on
  dinh) + role conf cao hon. Cost: 2 model + track tren CPU ~offline only.

### 6.5 Reasoner tieu thu CV (`reasoner._apply_cv_grounding`)
```
voi moi finding thuoc {M1,M3,M4,M5} (cac moment neo vao touch_patient):
   tim touch_patient event tai at_t
   neu [start_t, end_t] cua event OVERLAP voi bat ky contact_segment:
        finding.cv_grounding = "confirmed"     # CV xac nhan
   nguoc lai:
        finding.cv_grounding = "unconfirmed"   # VLM noi co, CV khong thay
```
**Verdict KHONG doi** — chi gan them tag. `pipeline._load_contact_segments` tim
sidecar 2 noi: `<video_path>.contact.json`, hoac
`uploads/contacts/<ten_goc>.contact.json` (strip prefix `<video_id>_`). Khong co
-> VLM-only (graceful).

---

## 6b. Camera real-time path (streaming) — `perception/stream_monitor.py`

Cho deploy tren CAMERA (webcam / RTSP / file-as-stream). Khac path upload:
```
VideoCapture(source)  ->  moi frame: role detector ONNX (KHONG torch)
  touch_patient = HCW box ∩ patient box (debounce)
  hand_hygiene  = nguoi DWELL trong "hygiene zone" (ROI sink/dispenser)
                  -> DWELL TIME = duration -> dap ung luat "rua tay >= Xs"
  -> StreamReasoner.push(event)  ->  ALERT real-time (cung policy JSON)
```
- **`app/stream_reasoner.py`** = engine ONLINE (stateful) cua cung protocol:
  push tung event -> tra finding ngay. M4 (nhin toi) xu ly online bang
  "open_contact" marker. **8 test xac nhan khop verdict voi batch reasoner.**
- **hand_hygiene detector**: 2 mode (`--hygiene-mode`):
  - `zone`: nguoi DWELL trong ROI sink (config) -> dwell = duration.
  - `rub` (xin hon, `app/pose_detect.py`): pose ONNX (torch-free) -> 2 co tay
    SAT nhau + CHUYEN DONG + duration = chu ky cha tay. Suppress khi tay nam
    tren patient box (+pad bed) = thao tac chu KHONG phai hygiene. `RubDetector`
    streaming, 5 unit test. HAN CHE: van FP tren thao tac 2 tay canh giuong khi
    role miss patient (DEFAULT, dung trong production hien tai).
  - `cls` (action MODEL, future): pipeline train da co (scripts/
    prep_hygiene_data.py = crop vung TAY theo pose -> dataset ImageFolder;
    train_hygiene_cls.py = YOLOv8-cls -> ONNX hygiene_cls.onnx, gan thang vao
    camera path). DA smoke-test E2E (prep->train->export 5.5MB). **NHUNG val
    top-1 0.97 la AO: train/val cung clip/cung tay (data leakage) + chi 16 crop
    hygiene -> KHONG phai model that.** Can DATA THAT: Kaggle "Hand Wash Dataset"
    hoac quay+gan nhan ward footage nhieu nguoi/site. Pipeline = deliverable;
    model POC = vut di.
- VERIFY: stream demo_violation.mp4 -> phat hien `touch_patient` t=7.6s -> ban
  `ALERT [M1] violation` real-time. Throughput ~5fps tren CPU (every=3) -> CAN
  GPU/edge cho real-time that; kien truc thi chay E2E.

## 6c. Benchmark — `scripts/benchmark.py` (+ `benchmark_gt.json`)
Do o 2 cho loi that su nam:
1. **Policy/reasoner**: 15 kich ban event co label chuyen gia -> P/R/F1 moi rule
   + verdict accuracy. KET QUA: **100%** (deterministic, da test -> guard regression).
2. **CV perception** (4 clip, co negative): contact temporal **P=0.90 R=0.56
   F1=0.69**. Bat duoc FP: clip hygiene (khong co BN) van ra 3 bin contact ->
   role doi khi hallucinate patient. => CV = confidence signal, KHONG doi verdict.
3. **Hand-hygiene rub** (clip-level): **P=0.33 R=1.00** -> bat het rua tay that
   nhung FP tren canh da-nguoi canh giuong (khi role miss patient). => can action
   model train. **N nho = seed; them clip ward de co so lieu that.**

---

## 7. Layer F — Chat Copilot (`chat.py`)

RAG-lite: lay `VideoAnalysis` lien quan -> nen thanh JSON context -> nhet vao
prompt + cau hoi -> Gemini tra loi **tieng Viet khong dau, ngan gon, chi dua tren
du lieu**, trich timestamp/so vi pham. Co retry backoff cho `ServerError` (503).
v2 (defer): text-to-SQL tren bang event that.

---

## 8. Layer E — API surface (`main.py`, FastAPI)

| Method | Path | Vai tro |
|--------|------|---------|
| GET | `/health` | healthcheck (Render probe) |
| POST | `/videos` | upload video -> `{video_id, status:queued}`, xu ly **background** |
| GET | `/videos/{id}` | job status + result (events/findings/score) |
| POST | `/chat` | `{question, video_id?}` -> tra loi copilot |

Luu file: `uploads/{video_id}_{filename}`. Job + result luu **SQLite**
(`db.py`). CORS env-driven (`CORS_ORIGINS`).

---

## 9. Layer G — Frontend (`frontend/`, React+Vite+Tailwind)

- `UploadPanel.jsx` — upload + poll status.
- `VideoTimeline.jsx` — event timeline truc quan.
- `ReportCard.jsx` — score gauge + violations/compliant; **`CvBadge`**:
  `confirmed` -> badge cyan **CV-OK**, `unconfirmed` -> amber **CV-??**.
- `CopilotChat.jsx` — hoi-dap.
- `api.js` -> `VITE_API_BASE` (default `127.0.0.1:8077`).

---

## 10. Cau hinh (`config.py`, tu `copilot/.env`)

```
GEMINI_API_KEY   (gitignored)        GEMINI_MODEL = gemini-2.5-flash
SAMPLE_EVERY_S=3.0  MAX_FRAMES=40  CONF_THRESHOLD=0.6  BATCH_SIZE=6
CORS_ORIGINS=*  (prod: URL Vercel)
```
Thrifty cho free-tier khi iter: `SAMPLE_EVERY_S=5 MAX_FRAMES=6 BATCH_SIZE=8`
(1 request/job). Free-tier = **5 request/PHUT** -> de yen ~90s roi ban 1 phat.

---

## 11. Chay end-to-end

**Backend** (`copilot/backend`):
```
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8077
```
**Frontend** (`copilot/frontend`): `npm run dev` (vite :5173).

**CV grounding (precompute, may co torch)**:
```
python perception/role_overlay.py --video uploads/demo_violation.mp4 \
   --out uploads/demo_violation_roles.mp4 \
   --json uploads/demo_violation_roles_det.json \
   --contact uploads/contacts/demo_violation.mp4.contact.json
```
Upload clip cung ten -> reasoner tu nhat sidecar -> ReportCard hien **CV-OK**.

> Khi demo: upload clip GOC (KHONG upload ban `_roles`/`_yolo` overlay — se lam
> nhieu VLM).

**Unit tests** (reasoner = core y te, phai dung -> co truth-table test):
```
cd backend ; PYTHONPATH=. ..\.venv\Scripts\python.exe -m unittest tests.test_reasoner -v
```
`backend/tests/test_reasoner.py` — 19 case: M1..M5, hand-state transitions
(glove_on KHONG lam ban, glove_off lam ban), score edges (None khi khong co
opportunity), va CV grounding (confirmed/unconfirmed/None + verdict KHONG doi vi
CV). Stdlib unittest, khong them dependency, khong ship vao Docker image.

---

## 12. Trang thai Phase / Roadmap

| Phase | Noi dung | Trang thai |
|-------|----------|-----------|
| 0 | Setup + smoke test VLM | DONE |
| 1 | Backend (detect->timeline->reason->chat->API->SQLite) | DONE, E2E PASSED |
| 2 | Frontend (upload/timeline/report/chat) | DONE |
| 2.1 | CV perception **role-aware grounding** (merge weight_v2) | DONE |
| 3 | Deploy (Render backend + Vercel frontend) | artifacts san sang; con user-action |
| 4 | Train/iterate (custom detector, hand-level fusion, text-to-SQL) | defer |

**Con lai de deploy** (user-action): push GitHub -> Render Blueprint (set
`GEMINI_API_KEY`) -> Vercel (set `VITE_API_BASE` = URL Render) -> set
`CORS_ORIGINS` = URL Vercel. Caveat: Render free filesystem **ephemeral**
(sqlite/uploads reset moi redeploy).

---

## 13. Han che da biet (de minh bach)

1. **VLM doc caption**: clip co chu de bi sai -> dung clip khong caption.
2. **CV grounding chi cho clip da precompute** (`.contact.json`). Upload moi ma
   chua precompute -> VLM-only (graceful, khong loi).
3. **role_overlay = detect-only**: cho role box, KHONG co wrist/hand keypoint.
   Muon hand-level role-aware (tay HCW thuc su LOT vao box patient) -> chay them
   `yolov8m-pose.pt`, associate role theo IoU. (defer, muc 6.3 da du cho demo.)
4. **Recall role model ~0.70**: miss ~30% -> dung lam confidence, khong doi
   verdict (dung design).
5. **Free-tier 5 req/phut**: bottleneck khi iter nhanh.
6. **Single primary actor**: timeline gia dinh 1 actor chinh; canh nhieu HCW
   chua tach.
```
