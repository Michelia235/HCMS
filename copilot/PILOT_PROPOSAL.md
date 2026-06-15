# DE XUAT TRIEN KHAI THU - Hand Hygiene Compliance Copilot

> Tro ly AI giam sat tuan thu ve sinh tay theo **WHO 5 Moments** tren camera san co.
> Tai lieu nay danh cho lanh dao benh vien / khoa Kiem soat nhiem khuan (IPC).

Lien he: Dang Quoc Hiep - dangquochiep2908@gmail.com | Ban thao trial (chua trien khai thuc te)

---

## 1. VAN DE

- Nhiem khuan benh vien (HAI) lam tang tu vong, ngay nam vien va chi phi. **Ve sinh tay
  dung cach la bien phap re va hieu qua nhat** de phong ngua.
- Cach do tuan thu hien nay = **quan sat truc tiep** (direct observation). No la "tieu chuan
  vang" nhung:
  - **Thien lech**: nhan vien biet bi quan sat thi lam tot hon (Hawthorne effect).
  - **Thua thot**: chi quan sat duoc mot ti le rat nho so moment thuc te trong ngay.
  - **Ton nhan luc**: can giam sat vien chuyen trach, kho duy tri 24/7.

=> Benh vien thieu so lieu tuan thu **khach quan, lien tuc, dien rong**.

---

## 2. GIAI PHAP

Bien camera san co thanh **auditor ve sinh tay 24/7**:

```
Camera khoa phong  ->  Phat hien hanh vi  ->  Suy luan WHO 5 Moments  ->  Bao cao + canh bao
(luong video)         (rua tay, cham BN,      (engine luat, deterministic)   + chat hoi-dap cho IPC
                       deo gang...)
```

- **Lien tuc & khong thien lech**: do moi ca, khong phu thuoc co giam sat vien dung do.
- **Co the kiem chung**: moi verdict kem **timestamp + ly do** theo guideline, khong phai hop den.
- **Tro ly chat cho IPC**: hoi tu nhien ("ca nao vi pham M1 hom nay?") tren du lieu da phan tich.

---

## 3. VI SAO KHAC CAC HE THONG "CAMERA AI" KHAC

| Dac diem | He thong nay |
|----------|--------------|
| Suy luan quy trinh | DETERMINISTIC theo WHO 5 Moments (auditable), khong de LLM doan verdict |
| Tuy bien quy trinh | **Policy-as-config**: doi luat / "rua tay >= 10s" / nguong ca truc = sua **JSON**, khong train lai model |
| Minh bach | Moi vi pham co bang chung su kien + thoi diem; CV chi la tin hieu confidence, khong tu doi ket luan |
| Rieng tu | Faceblur + trien khai on-prem/edge -> du lieu khong roi benh vien |

---

## 4. RIENG TU & AN TOAN (uu tien hang dau)

- **Faceblur** khuon mat truoc khi xu ly; co the chi giu **metadata su kien**, khong luu mat.
- **On-prem / edge**: xu ly ngay trong mang benh vien -> **video/PHI khong gui ra ngoai**.
- **Khong phai thiet bi y te / khong chan doan**: la cong cu **ho tro giam sat tuan thu**,
  khong dua quyet dinh lam sang.
- Tuan thu quy che du lieu & dao duc cua benh vien; can su dong y phu hop truoc khi quay.

---

## 5. TRIAL DE XUAT (2-4 tuan, pham vi nho)

**Pham vi**: 1 khoa/phong, 1-2 goc camera. Bat dau bang **footage da gan nac danh** (de-identified)
hoac 1 camera test - KHONG can ha tang lon.

| Tuan | Viec |
|------|------|
| 0 | Lay quy trinh ve sinh tay cua benh vien -> chuyen thanh `protocol.json`. Xac dinh "hygiene zone" (vi tri bon rua / binh sat khuan) tren khung hinh. |
| 1 | Chay tren footage mau -> hieu chinh detector + zone + nguong. |
| 2-3 | Chay song song voi quan sat thuong quy -> **so sanh** ket qua. |
| 4 | Bao cao: ti le tuan thu theo tung Moment, xu huong, do khop voi quan sat tay. |

**Benh vien can cung cap**:
1. Quy trinh / chinh sach ve sinh tay hien hanh.
2. Mot it footage khoa phong (da nac danh) HOAC cho dat 1 camera test 1 phong.
3. Nguoi dau moi IPC de doi chieu ket qua.

**Benh vien nhan duoc**:
- So lieu tuan thu **khach quan, lien tuc** ma quan sat tay khong the co.
- Phan tich theo tung Moment, theo ca/khu vuc, theo thoi gian.
- Bao cao danh gia tinh kha thi + do chinh xac tren chinh du lieu cua benh vien.

---

## 6. METRIC THANH CONG (thong nhat truoc)

- **Ti le tuan thu** tong va theo tung Moment (M1-M5).
- **Do khop** giua verdict cua he thong va quan sat tay (agreement / Cohen's kappa).
- **Do phu**: so moment do duoc/gio so voi quan sat tay (ky vong cao hon nhieu lan).
- **Thoi gian phan hoi**: tu hanh vi -> canh bao (real-time tren luong camera).

---

## 7. HIEN TRANG & GIOI HAN (noi that)

- **Da co (MVP chay duoc)**: pipeline detect -> timeline -> reasoner WHO 5 Moments (deterministic),
  CV grounding theo vai tro, **canh bao real-time tren camera**, chat copilot, giao dien web,
  benchmark + 36 unit test.
- **Gioi han hien tai**:
  - Lop thi giac (CV) recall ~0.70 -> dung lam **tin hieu confidence**, can hieu chinh theo goc camera/anh sang tung site.
  - Detect hanh vi ve sinh tay tot nhat o canh **can** (close-up); goc rong can them tuning/zone.
  - Chua co module auth/quan ly nguoi dung muc benh vien; faceblur la buoc bat buoc truoc khi xu ly du lieu that.
- **Lo trinh sau trial**: train model thi giac tren du lieu site, tang do phu da-camera, dashboard quan ly, tich hop bao cao IPC.

---

## 8. BUOC TIEP THEO

1. Hop 30 phut gioi thieu + xem demo (web app + camera real-time).
2. Thong nhat pham vi trial + metric + yeu cau du lieu/rieng tu.
3. Ky thoa thuan trial nho -> chay 2-4 tuan -> bao cao ket qua.

> Demo san sang trinh ngay: xem `DEMO.md`. Ky thuat chi tiet: `ARCHITECTURE.md`.
