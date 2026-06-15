# DEMO RUNBOOK - Hand Hygiene Compliance Copilot

> Kich ban demo TIN CAY cho thay / nguoi xem. Co **DEMO-SAFE MODE** -> demo
> KHONG chet giua chung khi Gemini het quota hay mat mang. Doc 5 phut truoc khi trinh.

Thoi luong: ~7-10 phut. Chuan bi: ~5 phut.

---

## 0. THONG DIEP CHINH (noi cau nay dau tien)

> "He thong bien camera benh vien thanh mot **auditor ve sinh tay 24/7**: tu dong
> phat hien hanh vi, doi chieu **WHO 5 Moments**, va bao vi pham NGAY LUC xay ra -
> kem giai thich co the kiem chung, khong phai hop den."

Ba diem khac biet can nhan:
1. **Suy luan compliance = DETERMINISTIC** (rule ro rang, auditable) - khong phai LLM doan.
2. **Policy-as-config**: doi luat/thoi gian/nguong (vd "rua tay >= 10s") chi sua **JSON**, khong train lai.
3. **Real-time tren camera**: alert ngay khi cham benh nhan ma chua ve sinh tay.

---

## 1. CHUAN BI TRUOC DEMO (lam 1 lan)

```powershell
# Terminal 1 - BACKEND (demo-safe mode bat san)
cd D:\Dizim\HCMS\copilot
$env:DEMO_FIXTURES = "1"        # replay ket qua co san cho clip demo -> KHONG goi Gemini
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8077

# Terminal 2 - FRONTEND
cd D:\Dizim\HCMS\copilot\frontend
npm run dev        # mo http://127.0.0.1:5173
```

Checklist truoc khi bat dau:
- [ ] `http://127.0.0.1:8077/health` tra `{"status":"ok"}`
- [ ] Frontend mo duoc o `http://127.0.0.1:5173`
- [ ] Co san 2 clip demo: `copilot/uploads/demo_compliant.mp4`, `copilot/uploads/demo_violation.mp4`
- [ ] Co san video camera: `copilot/demo/out/camera_demo_violation.mp4` (xem muc 4 de tao)

> **DEMO-SAFE MODE la gi**: khi `DEMO_FIXTURES=1`, voi 2 clip demo da biet, pipeline
> **replay ket qua chuan tu `demo/fixtures/`** thay vi goi Gemini. => ket qua luon
> giong nhau, KHONG phu thuoc quota/mang. Clip moi (la) van chay VLM that nhu binh thuong.

---

## 2. KICH BAN PHAN A - WEB APP (4-5 phut)

### Buoc 1: Ca TUAN THU
1. Keo tha `demo_compliant.mp4` vao o Upload -> nhan phan tich.
2. Doi vai giay -> **Report card** hien:
   - **Compliance score = 1.0** (xanh)
   - Moment **M1 [compliant]** - "Tay sach (da ve sinh) ngay truoc khi cham BN."
3. Noi: *"Y ta ve sinh tay luc t=5s, roi cham benh nhan t=10s -> dung Moment 1."*

### Buoc 2: Ca VI PHAM
1. Upload `demo_violation.mp4`.
2. Report card:
   - **Compliance score = 0.0** (do)
   - Moment **M1 [violation] medium** - "Tay khong sach truoc khi cham BN (chua ve sinh tay)."
3. Noi: *"O day cham benh nhan luc t=4s nhung KHONG co ve sinh tay truoc -> M1 vi pham.
   He thong chi thang timestamp + ly do."*

### Buoc 3: COPILOT CHAT (diem an tuong)
Go vao chat (chon dung video vi pham), hoi:
- *"Video nay co vi pham gi khong?"* -> tra loi chi ra M1 vi pham + thoi diem.
- *"Tai sao bi tinh la vi pham?"* -> giai thich theo guideline.
- (Tuy chon) hoi 1 cau khong co du lieu -> no **tu choi tra loi** ("khong du du lieu") - cho thay no khong bia.

---

## 3. KICH BAN PHAN B - CAMERA REAL-TIME (2-3 phut)

Cach 1 (an toan nhat): **mo san video da render** `demo/out/camera_demo_violation.mp4`.
- Tren video: box vai tro (nurse/patient) + banner verdict; den giay ~7.5s hien
  **ALERT M1 violation** ngay khi tay cham benh nhan.
- Noi: *"Day la luong CAMERA: detect online tung frame, bao vi pham NGAY LUC xay ra -
  dung dung policy WHO nhu ban bao cao offline."*

Cach 2 (live, neu tu tin): chay truc tiep tren webcam hoac clip:
```powershell
cd D:\Dizim\HCMS\copilot
$env:PYTHONPATH = "backend"
# webcam (0) voi vung ve sinh tay = pixel x1,y1,x2,y2 (cho noi co binh rua tay)
.\.venv\Scripts\python.exe perception\stream_monitor.py --source 0 --zone 20,20,200,460
```
Alert in ra console NGAY khi co touch_patient / hygiene theo policy.

---

## 4. (TAO LAI VIDEO CAMERA DEMO neu can)

```powershell
cd D:\Dizim\HCMS\copilot
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe perception\stream_monitor.py `
  --source uploads\demo_violation.mp4 --out demo\out\camera_demo_violation.mp4 --every 2
```
> Video la binary regenerable -> KHONG commit vao git (xem `.gitignore`). Tao local khi can.
> Muon demo ca CA TUAN THU tren camera: can `--zone` chi vung binh rua tay/bon rua
> (toa do pixel cua clip) de detector bat duoc hanh vi ve sinh tay.

---

## 5. (TUY CHON) PHAN C - POLICY-AS-CONFIG (1 phut, cho thay nhin sau)

Mo `agent/protocol/who_5_moments.json` va `agent/protocol/hospital_example.json`.
- Noi: *"Toan bo luat compliance nam o JSON nay: hand-state, min-duration (rua tay >= 10s),
  thu tu, nguong theo ca truc. Benh vien doi quy trinh -> sua JSON, KHONG dung den code/model."*
- Vi du `hospital_example.json` co them luat `HW_MIN` (rua >= 10s) + `SHIFT_RATE < 0.8`.

---

## 6. FALLBACK / SU CO

| Tinh huong | Xu ly |
|------------|-------|
| Gemini bao 429 / het quota | KHONG sao voi 2 clip demo (DEMO_FIXTURES replay, khong goi API). Clip la moi thi tranh upload luc demo. |
| Backend khong len | Kiem tra port 8077 trong (`Get-NetTCPConnection -LocalPort 8077`); restart Terminal 1. |
| Frontend goi sai API | `frontend/.env` -> `VITE_API_BASE=http://127.0.0.1:8077`; restart `npm run dev`. |
| Upload xong khong ra ket qua | Xem log Terminal 1; neu la clip la + het quota -> dung clip demo (co fixture). |
| Camera (stream_monitor) cham | CPU ~9 fps; demo bang VIDEO da render san (muc 3 cach 1) cho muot. |

---

## 7. CAU HOI THAY HAY HOI + TRA LOI NGAN

- **"Do co chinh xac khong?"** -> "Lop suy luan compliance la deterministic (auditable),
  do duoc 100% tren policy test. Lop thi giac (CV) recall ~0.70 -> dung lam **tin hieu
  confidence**, KHONG tu y doi verdict. Co benchmark trong `scripts/benchmark.py`."
- **"Privacy benh nhan?"** -> "MVP dung video mau. Production: faceblur truoc khi xu ly +
  trien khai on-prem/edge -> du lieu khong roi benh vien." (xem `PILOT_PROPOSAL.md`)
- **"Khac gi camera AI thuong?"** -> "No khong chi detect, ma **suy luan quy trinh WHO 5
  Moments theo thoi gian** + giai thich + chat - va luat la config, khong phai hard-code."
- **"Trien khai that ra sao?"** -> dua `PILOT_PROPOSAL.md` (ke hoach trial 1 khoa/phong, 2-4 tuan).

---

## Lien quan
- `PILOT_PROPOSAL.md` - de xuat trien khai thu tai benh vien (chao moi).
- `ARCHITECTURE.md` - chi tiet ky thuat end-to-end.
- `DEPLOY.md` - dua app len internet (Render + Vercel).
