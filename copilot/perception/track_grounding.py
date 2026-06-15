"""Deep grounding: hand-in-box contact with tracking + role fusion (v3).

Goes beyond box-overlap (role_overlay.py) to answer WHO touched WHOM, WITH WHICH
HAND, OVER TIME:

  pose model (yolov8m-pose) + ByteTrack  ->  persistent person IDs + wrists(hands)
  role model (best.pt)                   ->  doctor / nurse / patient labels
  fuse by box-IoU + temporal majority    ->  tracked persons that KNOW their role
  contact = an HCW's wrist INSIDE a PATIENT's box
                                         ->  typed segments (hcw_id, patient_id, hand)

Why this is stronger grounding: a `touch_patient` is now backed by an actual
HAND entering the patient's body region (not merely two boxes overlapping), and
it is attributed to a specific tracked HCW and patient.

This is the OFFLINE/precompute path (tracking needs ultralytics + torch). It
emits an annotated mp4 + a contact JSON whose `contact_segments` are
reasoner-compatible (start_t/end_t) so the backend CV grounding keeps working,
with richer who-touched-whom metadata attached.

Run (system python with ultralytics + torch):
  python copilot/perception/track_grounding.py \
      --video   copilot/uploads/demo_violation.mp4 \
      --out     copilot/uploads/demo_violation_track.mp4 \
      --contact copilot/uploads/contacts/demo_violation.mp4.contact.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter, defaultdict

import cv2
import numpy as np
from ultralytics import YOLO

POSE_WEIGHTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "yolov8m-pose.pt")
ROLE_WEIGHTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "weight_v2", "best.pt")

KP_L_WRIST, KP_R_WRIST = 9, 10
HCW_ROLES = {"doctor", "nurse"}
PATIENT_ROLE = "patient"

ROLE_COLOR = {"doctor": (255, 120, 0), "nurse": (0, 200, 0),
              "patient": (0, 140, 255), "unknown": (160, 160, 160)}

IOU_ASSIGN = 0.25      # min IoU pose-box <-> role-box to attach a role
KP_CONF = 0.3          # min wrist keypoint confidence
BOX_PAD_FRAC = 0.02    # expand patient box by this frac of diagonal (hand at edge)
MERGE_GAP_S = 0.6
MIN_SEG_S = 0.3


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _point_in_box(px, py, box, pad):
    x1, y1, x2, y2 = box
    return (x1 - pad) <= px <= (x2 + pad) and (y1 - pad) <= py <= (y2 + pad)


def _role_boxes(role_model, frame, conf):
    res = role_model.predict(frame, conf=conf, verbose=False)[0]
    out = []
    names = role_model.names
    if res.boxes is not None and len(res.boxes):
        for box, c in zip(res.boxes.xyxy.cpu().numpy(),
                          res.boxes.cls.cpu().numpy().astype(int)):
            out.append((names[int(c)], [float(v) for v in box]))
    return out


def _collect(video, pose_model, role_model, every, conf):
    """Pass 1 (inference): per-frame tracked persons, role assigned PER FRAME.

    Role comes from per-frame pose-box <-> role-box IoU (accurate even when
    people overlap). We deliberately do NOT take a per-track role majority:
    frame-skipping destabilises ByteTrack IDs during overlap, so a track's
    votes get contaminated. Track IDs are kept only as best-effort identity.
    """
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []   # [{t, persons:[{id,role,box,wl,wr}]}]
    idx = 0
    print(f"[track] {os.path.basename(video)} {w}x{h} {fps:.0f}fps every={every}")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            res = pose_model.track(frame, persist=True, tracker="bytetrack.yaml",
                                   verbose=False)[0]
            rboxes = _role_boxes(role_model, frame, conf)
            persons = []
            if res.boxes is not None:
                boxes = res.boxes.xyxy.cpu().numpy()
                ids = (res.boxes.id.cpu().numpy().astype(int)
                       if res.boxes.id is not None else np.arange(len(boxes)))
                kxy = res.keypoints.xy.cpu().numpy() if res.keypoints is not None else None
                kcf = res.keypoints.conf.cpu().numpy() if res.keypoints is not None else None
                for k, (box, tid) in enumerate(zip(boxes, ids)):
                    pb = [float(v) for v in box]
                    best_role, best_iou = "unknown", IOU_ASSIGN
                    for rname, rbox in rboxes:
                        i = _iou(pb, rbox)
                        if i >= best_iou:
                            best_role, best_iou = rname, i
                    wl = wr = None
                    if kxy is not None and kcf is not None:
                        if kcf[k][KP_L_WRIST] > KP_CONF:
                            wl = [float(kxy[k][KP_L_WRIST][0]), float(kxy[k][KP_L_WRIST][1])]
                        if kcf[k][KP_R_WRIST] > KP_CONF:
                            wr = [float(kxy[k][KP_R_WRIST][0]), float(kxy[k][KP_R_WRIST][1])]
                    persons.append({"id": int(tid), "role": best_role,
                                    "box": pb, "wl": wl, "wr": wr})
            frames.append({"t": round(idx / fps, 2), "persons": persons})
        idx += 1
    cap.release()
    return frames, (w, h, fps)


def _contacts(frames, diag):
    """Per-frame HCW-wrist-in-patient-box -> merged contact segments.

    Each frame's contacts are recorded with the (hcw_id, patient_id, hand) seen
    that frame; contiguous contact frames merge into a segment whose identity is
    the modal triple. The reasoner only needs start_t/end_t, so grounding is
    robust to ID noise; the who-touched-whom metadata is best-effort.
    """
    pad = BOX_PAD_FRAC * diag
    marks = []  # (t, [ (hcw_id, patient_id, hand), ... ])
    for fr in frames:
        patients = [p for p in fr["persons"] if p["role"] == PATIENT_ROLE]
        hcws = [p for p in fr["persons"] if p["role"] in HCW_ROLES]
        frame_hits = []
        for hcw in hcws:
            for hand, wv in (("L", hcw["wl"]), ("R", hcw["wr"])):
                if wv is None:
                    continue
                for pat in patients:
                    if _point_in_box(wv[0], wv[1], pat["box"], pad):
                        frame_hits.append((hcw["id"], pat["id"], hand))
        marks.append((fr["t"], frame_hits))

    segs, cur, cur_hits = [], None, None
    for t, hits in marks:
        if hits:
            if cur is None:
                cur, cur_hits = [t, t], list(hits)
            elif t - cur[1] <= MERGE_GAP_S:
                cur[1] = t
                cur_hits.extend(hits)
            else:
                segs.append((cur[0], cur[1], cur_hits))
                cur, cur_hits = [t, t], list(hits)
    if cur is not None:
        segs.append((cur[0], cur[1], cur_hits))

    out = []
    for s, e, hits in segs:
        if e - s < MIN_SEG_S and not math.isclose(s, e):
            continue
        hid, pid, hand = Counter(hits).most_common(1)[0][0]
        out.append({"start_t": round(s, 2), "end_t": round(e, 2),
                    "min_dist": 0.0, "inside_box": True, "kind": "hand_in_patient",
                    "hcw_id": hid, "patient_id": pid, "hand": hand})
    out.sort(key=lambda s: s["start_t"])
    return out


def _annotate(video, out_path, frames, segs, fps, every):
    """Pass 2 (decode only): draw per-frame roles + hands + active contacts."""
    by_t = {fr["t"]: fr for fr in frames}
    cap = cv2.VideoCapture(video)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                             fps / every, (w, h))
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            fr = by_t.get(round(idx / fps, 2))
            if fr is not None:
                for p in fr["persons"]:
                    col = ROLE_COLOR.get(p["role"], ROLE_COLOR["unknown"])
                    x1, y1, x2, y2 = [int(v) for v in p["box"]]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                    cv2.putText(frame, f"{p['role']}#{p['id']}", (x1, max(0, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)
                    for wv in (p["wl"], p["wr"]):
                        if wv is not None:
                            cv2.circle(frame, (int(wv[0]), int(wv[1])), 7,
                                       (0, 255, 255), 2)
                t = round(idx / fps, 2)
                active = [s for s in segs if s["start_t"] <= t <= s["end_t"]]
                for k, s in enumerate(active):
                    cv2.putText(frame,
                                f"HAND-IN-PATIENT {s['hcw_id']}->{s['patient_id']} ({s['hand']})",
                                (10, 26 + 24 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (255, 0, 255), 2, cv2.LINE_AA)
            writer.write(frame)
        idx += 1
    cap.release()
    writer.release()
    print(f"[track] annotated -> {out_path}")


def run(video, out_path, contact_path, every, conf):
    pose_model = YOLO(POSE_WEIGHTS)
    role_model = YOLO(ROLE_WEIGHTS)
    frames, (w, h, fps) = _collect(video, pose_model, role_model, every, conf)
    diag = math.hypot(w, h)
    segs = _contacts(frames, diag)

    roles_seen = Counter(p["role"] for fr in frames for p in fr["persons"])
    print(f"[track] role_dets={dict(roles_seen)} hand_contacts={len(segs)}")
    for s in segs:
        print(f"   HCW#{s['hcw_id']} -> patient#{s['patient_id']} hand-{s['hand']} "
              f"{s['start_t']}-{s['end_t']}s")

    if out_path:
        _annotate(video, out_path, frames, segs, fps, every)
    if contact_path:
        json.dump({"video": os.path.basename(video), "source": "track_grounding",
                   "contact_segments": segs},
                  open(contact_path, "w", encoding="utf-8"), indent=2)
        print(f"[track] contact json -> {contact_path}")
    return segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--contact", default="")
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--conf", type=float, default=0.35)
    a = ap.parse_args()
    run(a.video, a.out, a.contact, a.every, a.conf)


if __name__ == "__main__":
    main()
