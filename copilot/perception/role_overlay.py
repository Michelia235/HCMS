"""Role-aware perception layer for the Compliance Copilot (v2.1).

This MERGES the CV engineer's trained role detector (weight_v2/best.pt, a
YOLOv8m fine-tuned on a hospital dataset -> classes {doctor, nurse, patient})
into the perception layer. It supersedes the role-blind pose proximity:
instead of "any hand inside any person box", contact is now ROLE-AWARE --
a healthcare worker (doctor|nurse) box touching/overlapping a PATIENT box.

That is the spatial evidence behind a `touch_patient` event, and it is what
lets the reasoner's CV grounding mean "an HCW actually approached the patient"
rather than "two people were near each other".

Three outputs (any subset):
  * annotated mp4   (--out)      role-colored boxes + CONTACT link
  * detections JSON (--json)     per-frame roles + boxes (audit trail)
  * contact JSON    (--contact)  HCW<->patient contact_segments, in the SAME
                                 schema the backend reasoner already consumes
                                 (start_t/end_t/min_dist/inside_box) + roles.

Run (env with ultralytics + torch; here = system python):
  python copilot/perception/role_overlay.py \
      --video   copilot/uploads/demo_violation.mp4 \
      --out     copilot/uploads/demo_violation_roles.mp4 \
      --json    copilot/uploads/demo_violation_roles_det.json \
      --contact copilot/uploads/demo_violation.contact.json
"""
from __future__ import annotations

import argparse
import json
import math
import os

import cv2
import numpy as np
from ultralytics import YOLO

DEFAULT_WEIGHTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "weight_v2", "best.pt"
)

HCW_ROLES = {"doctor", "nurse"}
PATIENT_ROLE = "patient"

# BGR colors per role for the overlay.
ROLE_COLOR = {
    "doctor": (255, 120, 0),    # blue
    "nurse": (0, 200, 0),       # green
    "patient": (0, 140, 255),   # orange
}

# Contact tuning -- mirrors proximity.py so behaviour is consistent.
# An HCW box is a "contact candidate" when its normalised gap to a patient
# box is below this (0 = boxes overlap). ~3% of the frame diagonal.
NEAR_FRAC = 0.03
MERGE_GAP_S = 0.6   # bridge gaps up to this when merging frames into a segment
MIN_SEG_S = 0.3     # drop sub-this blips (unless boxes actually overlapped)


def _box_box_dist(a, b):
    """Euclidean gap between two axis-aligned boxes; 0 if they overlap."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(bx1 - ax2, ax1 - bx2, 0.0)
    dy = max(by1 - ay2, ay1 - by2, 0.0)
    return math.hypot(dx, dy)


def _frame_contact(persons, diag):
    """Min normalised HCW->patient box gap in one frame.

    Returns (min_norm_dist, hcw_idx, patient_idx) or None when the frame lacks
    an HCW+patient pair. 0.0 means an HCW box overlaps a patient box.
    """
    best = None
    for i, a in enumerate(persons):
        if a["role"] not in HCW_ROLES:
            continue
        for j, b in enumerate(persons):
            if b["role"] != PATIENT_ROLE:
                continue
            d = _box_box_dist(a["box"], b["box"]) / diag
            if best is None or d < best[0]:
                best = (d, i, j)
    return best


def compute_segments(detections, width, height, fps):
    """Per-frame contact marks -> merged HCW<->patient contact segments."""
    diag = math.hypot(width, height)
    marks = []  # (t, is_contact, norm_dist)
    for fr in detections:
        res = _frame_contact(fr["persons"], diag)
        if res is None:
            marks.append((fr["t"], False, None))
        else:
            marks.append((fr["t"], res[0] <= NEAR_FRAC, res[0]))

    segs, cur = [], None
    for t, is_c, nd in marks:
        if is_c:
            if cur is None:
                cur = {"start_t": t, "end_t": t, "min_dist": nd}
            elif t - cur["end_t"] <= MERGE_GAP_S:
                cur["end_t"] = t
                cur["min_dist"] = min(cur["min_dist"], nd)
            else:
                segs.append(cur)
                cur = {"start_t": t, "end_t": t, "min_dist": nd}
    if cur is not None:
        segs.append(cur)

    segs = [s for s in segs
            if s["end_t"] - s["start_t"] >= MIN_SEG_S or s["min_dist"] == 0.0]
    for s in segs:
        s["start_t"] = round(s["start_t"], 2)
        s["end_t"] = round(s["end_t"], 2)
        s["min_dist"] = round(s["min_dist"], 4)
        s["inside_box"] = s["min_dist"] == 0.0
        s["kind"] = "hcw_patient"  # role-aware provenance
    return segs


def _draw(frame, persons, in_contact):
    for p in persons:
        x1, y1, x2, y2 = [int(v) for v in p["box"]]
        col = ROLE_COLOR.get(p["role"], (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
        cv2.putText(frame, f"{p['role']} {p['conf']:.2f}", (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)
    if in_contact:
        cv2.putText(frame, "HCW-PATIENT CONTACT", (10, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2, cv2.LINE_AA)
    return frame


def run(video, out_path, json_path, contact_path, weights, every, conf_thresh):
    model = YOLO(weights)
    names = model.names
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    diag = math.hypot(w, h)

    writer = None
    if out_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, fps / every, (w, h))

    detections = []
    idx = 0
    print(f"[role] {os.path.basename(video)}  {w}x{h} {fps:.0f}fps {n_total}f  "
          f"every={every} conf={conf_thresh}  classes={names}")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            res = model.predict(frame, conf=conf_thresh, verbose=False)[0]
            persons = []
            if res.boxes is not None and len(res.boxes):
                boxes = res.boxes.xyxy.cpu().numpy()
                clss = res.boxes.cls.cpu().numpy().astype(int)
                confs = res.boxes.conf.cpu().numpy()
                for box, c, cf in zip(boxes, clss, confs):
                    persons.append({
                        "role": names[int(c)],
                        "conf": round(float(cf), 3),
                        "box": [round(float(v), 1) for v in box],
                    })
            t = idx / fps
            cres = _frame_contact(persons, diag)
            detections.append({"frame": idx, "t": round(t, 2),
                               "n_persons": len(persons), "persons": persons})
            if writer is not None:
                in_c = cres is not None and cres[0] <= NEAR_FRAC
                writer.write(_draw(frame.copy(), persons, in_c))
        idx += 1

    cap.release()
    if writer is not None:
        writer.release()
        print(f"[role] annotated video -> {out_path}")

    if json_path:
        json.dump({"video": os.path.basename(video), "fps": fps,
                   "width": w, "height": h, "classes": names,
                   "n_frames_processed": len(detections),
                   "detections": detections},
                  open(json_path, "w", encoding="utf-8"), indent=2)
        print(f"[role] detections json -> {json_path}")

    segs = compute_segments(detections, w, h, fps)
    role_counts = {}
    for d in detections:
        for p in d["persons"]:
            role_counts[p["role"]] = role_counts.get(p["role"], 0) + 1
    print(f"[role] frames={len(detections)}  role_dets={role_counts}  "
          f"contact_segments={len(segs)}")
    for s in segs:
        tag = "OVERLAP" if s["inside_box"] else f"min_dist={s['min_dist']}"
        print(f"   HCW<->patient {s['start_t']}-{s['end_t']}s  ({tag})")

    if contact_path:
        json.dump({"video": os.path.basename(video), "source": "role_overlay",
                   "near_frac": NEAR_FRAC, "contact_segments": segs},
                  open(contact_path, "w", encoding="utf-8"), indent=2)
        print(f"[role] contact json -> {contact_path}")
    return detections, segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--contact", default="")
    ap.add_argument("--weights", default=DEFAULT_WEIGHTS)
    ap.add_argument("--every", type=int, default=3, help="process every Nth frame")
    ap.add_argument("--conf", type=float, default=0.35)
    a = ap.parse_args()
    run(a.video, a.out, a.json, a.contact, a.weights, a.every, a.conf)


if __name__ == "__main__":
    main()
