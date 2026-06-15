"""Pose detector (ONNX) + hands-rubbing hand-hygiene detector.

Upgrades the camera path's `hand_hygiene` signal from a static "hygiene zone"
ROI to the actual VISUAL SIGNATURE of hand rubbing: both wrists close together
and moving, sustained over time. Runs the YOLOv8-pose model exported to ONNX
(onnxruntime + opencv only -- no torch), so it stays deploy-light like the role
detector.

The detector is STREAMING + stateful: feed it per-frame wrists, it tracks the
ongoing rub and emits a `hand_hygiene` event WITH its measured duration when the
rub ends -> feeds the protocol's `min_duration_s` rule ("rua tay >= 10s").
"""
from __future__ import annotations

import math
import os

import cv2
import numpy as np

from . import config

IMGSZ = 640
KP_L_WRIST, KP_R_WRIST = 9, 10

_session = None
_load_failed = False


def _load():
    global _session, _load_failed
    if _session is not None or _load_failed:
        return _session
    try:
        import onnxruntime as ort  # type: ignore
    except ImportError:
        _load_failed = True
        return None
    path = config.POSE_ONNX_PATH
    if not path.exists():
        _load_failed = True
        return None
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.intra_op_num_threads = min(4, os.cpu_count() or 4)
    _session = ort.InferenceSession(str(path), sess_options=so,
                                    providers=["CPUExecutionProvider"])
    return _session


def available() -> bool:
    return _load() is not None


def _letterbox(frame):
    h, w = frame.shape[:2]
    r = min(IMGSZ / h, IMGSZ / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    canvas = np.full((IMGSZ, IMGSZ, 3), 114, np.uint8)
    top, left = (IMGSZ - nh) // 2, (IMGSZ - nw) // 2
    canvas[top:top + nh, left:left + nw] = cv2.resize(frame, (nw, nh))
    blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None]
    return np.ascontiguousarray(blob, np.float32) / 255.0, r, left, top


def detect_wrists(frame, conf_thresh=0.4, iou=0.5):
    """Per-person wrists -> [{box, score, wl|None, wr|None}] in frame coords.

    Pose ONNX output is (1, 56, 8400): 4 box + 1 score + 17*(x,y,conf).
    """
    sess = _load()
    if sess is None:
        return []
    blob, r, left, top = _letterbox(frame)
    out = sess.run(None, {sess.get_inputs()[0].name: blob})[0]
    preds = out[0].T  # (8400, 56)
    scores = preds[:, 4]
    keep = scores >= conf_thresh
    preds, scores = preds[keep], scores[keep]
    if len(preds) == 0:
        return []
    cx, cy, ww, hh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    boxes_xywh = np.stack([cx - ww / 2, cy - hh / 2, ww, hh], 1).tolist()
    idxs = cv2.dnn.NMSBoxes(boxes_xywh, scores.tolist(), conf_thresh, iou)
    if len(idxs) == 0:
        return []
    persons = []
    for i in np.array(idxs).flatten():
        p = preds[i]
        x1 = (p[0] - p[2] / 2 - left) / r
        y1 = (p[1] - p[3] / 2 - top) / r
        x2 = (p[0] + p[2] / 2 - left) / r
        y2 = (p[1] + p[3] / 2 - top) / r

        def kp(k):
            base = 5 + k * 3
            if p[base + 2] < 0.3:
                return None
            return [float((p[base] - left) / r), float((p[base + 1] - top) / r)]
        persons.append({"box": [float(x1), float(y1), float(x2), float(y2)],
                        "score": float(scores[i]),
                        "wl": kp(KP_L_WRIST), "wr": kp(KP_R_WRIST)})
    return persons


class RubDetector:
    """Streaming hands-rubbing -> hand_hygiene events with duration.

    Rub signature per frame: a person has BOTH wrists, they are close together
    (gap < CLOSE_FRAC of the person-box diagonal), and the hands are MOVING
    (midpoint travels across recent frames -> distinguishes rubbing from hands
    merely clasped still). A sustained run >= MIN_S becomes one hand_hygiene
    event; its length is the measured wash duration.
    """
    CLOSE_FRAC = 0.30      # wrist gap < this * person diagonal -> "together"
    MIN_S = 1.0            # ignore runs shorter than this
    MOVE_PX = 1.0          # avg midpoint travel/frame to count as "rubbing"
    GAP_S = 0.6            # bridge brief excursions above CLOSE_FRAC / dropouts
    PATIENT_PAD_FRAC = 0.20  # pad patient box (covers the bed) when excluding

    def __init__(self):
        self.run_start = None
        self.last_seen = None
        self.mids = []     # recent (t, midx, midy) for motion check

    def update(self, persons, t, patient_boxes=None):
        """Feed one frame; return (start_t, end_t) if a rub just ENDED, else None.

        patient_boxes (optional, from the role detector) disambiguates rubbing
        from "both hands working ON a patient" (e.g. tucking a blanket): a rub
        whose hands fall inside a patient box is suppressed -- hand hygiene
        happens AWAY from the patient.
        """
        rubbing = False
        for p in persons:
            if p["wl"] is None or p["wr"] is None:
                continue
            x1, y1, x2, y2 = p["box"]
            diag = math.hypot(x2 - x1, y2 - y1) or 1.0
            gap = math.hypot(p["wl"][0] - p["wr"][0], p["wl"][1] - p["wr"][1])
            if gap / diag > self.CLOSE_FRAC:
                continue
            mx = (p["wl"][0] + p["wr"][0]) / 2
            my = (p["wl"][1] + p["wr"][1]) / 2
            # exclude hands over a patient (+ a margin for the bed around them)
            if patient_boxes:
                over = False
                for bx in patient_boxes:
                    pad = self.PATIENT_PAD_FRAC * math.hypot(bx[2] - bx[0], bx[3] - bx[1])
                    if bx[0] - pad <= mx <= bx[2] + pad and bx[1] - pad <= my <= bx[3] + pad:
                        over = True
                        break
                if over:
                    continue  # contact/manipulation, not hygiene
            self.mids.append((t, mx, my))
            self.mids = self.mids[-8:]
            rubbing = True
            break

        if rubbing:
            if self.run_start is None:
                self.run_start = t
            self.last_seen = t
            return None

        # not rubbing this frame: close an open run if the gap exceeded
        if self.run_start is not None and self.last_seen is not None \
                and t - self.last_seen > self.GAP_S:
            start, end = self.run_start, self.last_seen
            moved = self._moved()
            self.run_start = self.last_seen = None
            self.mids = []
            if end - start >= self.MIN_S and moved:
                return (start, end)
        return None

    def flush(self, t):
        """Close any open run at end of stream."""
        if self.run_start is not None and self.last_seen is not None:
            start, end = self.run_start, self.last_seen
            self.run_start = self.last_seen = None
            if end - start >= self.MIN_S and self._moved():
                return (start, end)
        return None

    def _moved(self):
        if len(self.mids) < 3:
            return False
        steps = [math.hypot(self.mids[i][1] - self.mids[i - 1][1],
                            self.mids[i][2] - self.mids[i - 1][2])
                 for i in range(1, len(self.mids))]
        return (sum(steps) / len(steps)) >= self.MOVE_PX
