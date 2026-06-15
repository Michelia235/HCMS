"""Build a hand-hygiene action-classification dataset from labeled clips.

Crops the HANDS region (around the pose wrists) from each labeled clip so the
classifier learns the ACTION (rubbing) rather than the room. Writes an
ImageFolder layout that ultralytics YOLOv8-cls trains on directly:

    data/hygiene_cls/{train,val}/{hand_hygiene,other}/*.jpg

Labels come from scripts/hygiene_labels.json (clip-level, or per-interval). This
is the SEED workflow -- point it at many annotated clips for a real dataset.

Run (system python with ultralytics+torch, OR backend venv for pose ONNX):
    python scripts/prep_hygiene_data.py
"""
from __future__ import annotations

import json
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import pose_detect  # noqa: E402

OUT = os.path.join(ROOT, "data", "hygiene_cls")
EVERY = 4               # sample every Nth frame
VAL_FRAC = 0.25
CROP_PAD = 0.6          # expand the wrist bbox by this fraction (hands+forearms)
MIN_CROP = 48           # skip tiny crops


def _in_interval(t, intervals):
    if intervals is None:
        return True
    return any(a <= t <= b for a, b in intervals)


def _hands_crop(frame, persons):
    """Tight box around all detected wrists, padded. None if no wrists."""
    pts = []
    for p in persons:
        for w in (p["wl"], p["wr"]):
            if w is not None:
                pts.append(w)
    if len(pts) < 1:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    w, h = max(x2 - x1, 20), max(y2 - y1, 20)
    px, py = w * CROP_PAD, h * CROP_PAD
    H, W = frame.shape[:2]
    cx1 = max(0, int(x1 - px)); cy1 = max(0, int(y1 - py))
    cx2 = min(W, int(x2 + px)); cy2 = min(H, int(y2 + py))
    if cx2 - cx1 < MIN_CROP or cy2 - cy1 < MIN_CROP:
        return None
    return frame[cy1:cy2, cx1:cx2]


def main():
    if not pose_detect.available():
        raise SystemExit("pose ONNX not available (perception/weight_v2/pose.onnx)")
    labels = json.load(open(os.path.join(HERE, "hygiene_labels.json"), encoding="utf-8"))
    counts = {}
    for item in labels["clips"]:
        clip = os.path.join(ROOT, "uploads", item["clip"])
        if not os.path.exists(clip):
            print(f"[skip] missing {item['clip']}")
            continue
        label = item["label"]
        intervals = item.get("intervals")
        cap = cv2.VideoCapture(clip)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        idx = saved = 0
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            if idx % EVERY == 0 and _in_interval(idx / fps, intervals):
                crop = _hands_crop(fr, pose_detect.detect_wrists(fr))
                if crop is not None:
                    split = "val" if (saved % int(1 / VAL_FRAC) == 0) else "train"
                    d = os.path.join(OUT, split, label)
                    os.makedirs(d, exist_ok=True)
                    cv2.imwrite(os.path.join(d, f"{item['clip']}_{idx}.jpg"), crop)
                    counts[(split, label)] = counts.get((split, label), 0) + 1
                    saved += 1
            idx += 1
        cap.release()
        print(f"[prep] {item['clip']:24s} -> {saved} hand-crops ({label})")
    print("\n[prep] dataset at", OUT)
    for k in sorted(counts):
        print(f"   {k[0]:5s}/{k[1]:13s} {counts[k]}")
    print("\nNOTE: tiny + few sources -> POC only. Add many clips/people for a real model.")


if __name__ == "__main__":
    main()
