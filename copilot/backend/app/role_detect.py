"""Inline role detector (ONNX) -> live HCW<->patient contact grounding.

This is the LIGHT runtime of the CV engineer's role model: the YOLOv8m weights
are exported to ONNX and run here with onnxruntime + opencv ONLY (no torch /
ultralytics), so the backend can ground EVERY uploaded video instead of relying
on precomputed sidecars. Same role-aware logic as perception/role_overlay.py:
contact = a healthcare worker (doctor|nurse) box overlapping/near a PATIENT box.

Everything is optional and lazy: if onnxruntime or the .onnx model is missing,
`available()` is False and the pipeline falls back to VLM-only (graceful). The
verdict is never affected -- contact segments are only a confidence signal.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from . import config

# Class order baked into the exported model: {0: doctor, 1: nurse, 2: patient}
CLASS_NAMES = {0: "doctor", 1: "nurse", 2: "patient"}
HCW_ROLES = {"doctor", "nurse"}
PATIENT_ROLE = "patient"
IMGSZ = 640

# Contact tuning -- kept in sync with perception/role_overlay.py.
NEAR_FRAC = 0.03
MERGE_GAP_S = 0.6
MIN_SEG_S = 0.3

_session = None       # cached ort.InferenceSession
_load_failed = False  # remember a failed load so we don't retry every call


def _load():
    """Lazy-load the ONNX session; return None if unavailable."""
    global _session, _load_failed
    if _session is not None or _load_failed:
        return _session
    try:
        import onnxruntime as ort  # type: ignore
    except ImportError:
        _load_failed = True
        return None
    path = config.ROLE_ONNX_PATH
    if not path.exists():
        _load_failed = True
        return None
    import os
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # Modest thread count: all-cores oversubscribes when the API/other workers
    # share the box and actually slows inference.
    so.intra_op_num_threads = min(4, os.cpu_count() or 4)
    _session = ort.InferenceSession(
        str(path), sess_options=so, providers=["CPUExecutionProvider"])
    return _session


def available() -> bool:
    return _load() is not None


def _letterbox(frame):
    """Resize to IMGSZ keeping aspect ratio, pad to square. Returns blob + meta."""
    h, w = frame.shape[:2]
    r = min(IMGSZ / h, IMGSZ / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((IMGSZ, IMGSZ, 3), 114, dtype=np.uint8)
    top, left = (IMGSZ - nh) // 2, (IMGSZ - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None]  # BGR->RGB, HWC->CHW, batch
    blob = np.ascontiguousarray(blob, dtype=np.float32) / 255.0
    return blob, r, left, top


def detect_frame(frame, conf_thresh=0.35, iou=0.5):
    """Run the role detector on one BGR frame -> [{role, conf, box(xyxy)}]."""
    sess = _load()
    if sess is None:
        return []
    blob, r, left, top = _letterbox(frame)
    out = sess.run(None, {sess.get_inputs()[0].name: blob})[0]  # (1, 7, 8400)
    preds = out[0].T  # (8400, 7): cx, cy, w, h, score_doctor, score_nurse, score_patient
    scores = preds[:, 4:]
    cls = scores.argmax(axis=1)
    conf = scores.max(axis=1)
    keep = conf >= conf_thresh
    preds, cls, conf = preds[keep], cls[keep], conf[keep]
    if len(preds) == 0:
        return []
    # xywh (letterbox space) -> xyxy (original frame space)
    cx, cy, ww, hh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    x1 = (cx - ww / 2 - left) / r
    y1 = (cy - hh / 2 - top) / r
    x2 = (cx + ww / 2 - left) / r
    y2 = (cy + hh / 2 - top) / r
    boxes_xywh = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
    idxs = cv2.dnn.NMSBoxes(boxes_xywh, conf.tolist(), conf_thresh, iou)
    if len(idxs) == 0:
        return []
    idxs = np.array(idxs).flatten()
    persons = []
    for i in idxs:
        persons.append({
            "role": CLASS_NAMES.get(int(cls[i]), str(int(cls[i]))),
            "conf": round(float(conf[i]), 3),
            "box": [round(float(x1[i]), 1), round(float(y1[i]), 1),
                    round(float(x2[i]), 1), round(float(y2[i]), 1)],
        })
    return persons


def _box_box_dist(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(bx1 - ax2, ax1 - bx2, 0.0)
    dy = max(by1 - ay2, ay1 - by2, 0.0)
    return math.hypot(dx, dy)


def _frame_contact(persons, diag):
    best = None
    for a in persons:
        if a["role"] not in HCW_ROLES:
            continue
        for b in persons:
            if b["role"] != PATIENT_ROLE:
                continue
            d = _box_box_dist(a["box"], b["box"]) / diag
            if best is None or d < best:
                best = d
    return best


def _segments_from_marks(marks):
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
        s["kind"] = "hcw_patient"
    return segs


def contact_segments(video_path: str) -> list[dict] | None:
    """Sample a video, run the role detector, return HCW<->patient segments.

    None if the detector is unavailable or the video can't be read.
    """
    sess = _load()
    if sess is None:
        return None
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    diag = math.hypot(w, h)
    step = max(1, int(round(fps * config.ROLE_SAMPLE_EVERY_S)))
    conf = config.ROLE_CONF

    marks, idx, processed = [], 0, 0
    while processed < config.ROLE_MAX_FRAMES:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            persons = detect_frame(frame, conf_thresh=conf)
            d = _frame_contact(persons, diag)
            marks.append((round(idx / fps, 2), d is not None and d <= NEAR_FRAC, d))
            processed += 1
        idx += 1
    cap.release()
    return _segments_from_marks(marks)
