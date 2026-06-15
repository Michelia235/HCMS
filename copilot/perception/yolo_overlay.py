"""YOLO perception layer for the Compliance Copilot (v2).

Pretrained YOLOv8-pose runs locally per frame to produce the *spatial* grounding
the VLM-on-frames MVP lacks: it draws person boxes + hand (wrist) markers ("cai
khoanh"), and emits a per-frame detections JSON the reasoner/VLM can lean on
(hand position, #persons). It does NOT classify hand-hygiene events by itself --
that stays with the temporal reasoner / VLM. See project_hcms_copilot memory.

Run (env that has ultralytics + torch; here = system python):
  python copilot/perception/yolo_overlay.py \
      --video copilot/uploads/demo_violation.mp4 \
      --out   copilot/uploads/demo_violation_yolo.mp4 \
      --json  copilot/uploads/demo_violation_det.json
"""
from __future__ import annotations

import argparse
import json
import os

import cv2
import numpy as np
from ultralytics import YOLO

# COCO-17 keypoint indices we care about for hand hygiene.
KP_L_WRIST, KP_R_WRIST = 9, 10
KP_L_ELBOW, KP_R_ELBOW = 7, 8
SKELETON_EDGES = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

DEFAULT_WEIGHTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "yolov8m-pose.pt"
)


def _draw(frame, boxes, kpts, kp_conf, conf_thresh):
    """Draw person boxes + skeleton + emphasised hand markers onto frame."""
    h, w = frame.shape[:2]
    for box, kp, kc in zip(boxes, kpts, kp_conf):
        x1, y1, x2, y2 = [int(v) for v in box]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
        cv2.putText(frame, "person", (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1, cv2.LINE_AA)
        # skeleton (thin)
        for a, b in SKELETON_EDGES:
            if kc[a] > conf_thresh and kc[b] > conf_thresh:
                pa = (int(kp[a][0]), int(kp[a][1]))
                pb = (int(kp[b][0]), int(kp[b][1]))
                cv2.line(frame, pa, pb, (255, 180, 0), 1, cv2.LINE_AA)
        # hands = wrists, emphasised
        for idx, label in ((KP_L_WRIST, "L"), (KP_R_WRIST, "R")):
            if kc[idx] > conf_thresh:
                cx, cy = int(kp[idx][0]), int(kp[idx][1])
                cv2.circle(frame, (cx, cy), 9, (0, 255, 255), 2)
                cv2.putText(frame, f"hand-{label}", (cx + 10, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1,
                            cv2.LINE_AA)
    return frame


def run(video, out_path, json_path, weights, every, conf_thresh):
    model = YOLO(weights)
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    writer = None
    if out_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, fps / every, (w, h))

    detections = []
    idx = 0
    print(f"[yolo] {os.path.basename(video)}  {w}x{h} {fps:.0f}fps "
          f"{n_total}f  every={every}  conf={conf_thresh}")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            res = model.predict(frame, conf=conf_thresh, verbose=False)[0]
            boxes = res.boxes.xyxy.cpu().numpy() if res.boxes is not None else np.empty((0, 4))
            if res.keypoints is not None and len(boxes):
                kpts = res.keypoints.xy.cpu().numpy()
                kp_conf = res.keypoints.conf.cpu().numpy()
            else:
                kpts = np.empty((0, 17, 2))
                kp_conf = np.empty((0, 17))

            t = idx / fps
            persons = []
            for box, kp, kc in zip(boxes, kpts, kp_conf):
                rec = {"box": [round(float(v), 1) for v in box]}
                for name, ki in (("hand_l", KP_L_WRIST), ("hand_r", KP_R_WRIST)):
                    if kc[ki] > conf_thresh:
                        rec[name] = [round(float(kp[ki][0]), 1),
                                     round(float(kp[ki][1]), 1)]
                persons.append(rec)
            detections.append({"frame": idx, "t": round(t, 2),
                               "n_persons": len(persons), "persons": persons})

            if writer is not None:
                writer.write(_draw(frame.copy(), boxes, kpts, kp_conf, conf_thresh))
        idx += 1

    cap.release()
    if writer is not None:
        writer.release()
        print(f"[yolo] annotated video -> {out_path}")
    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"video": os.path.basename(video), "fps": fps,
                       "width": w, "height": h,
                       "n_frames_processed": len(detections),
                       "detections": detections}, f, indent=2)
        print(f"[yolo] detections json -> {json_path}")
    n_with = sum(1 for d in detections if d["n_persons"] > 0)
    print(f"[yolo] frames processed={len(detections)} "
          f"with-person={n_with}")
    return detections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--weights", default=os.path.abspath(DEFAULT_WEIGHTS))
    ap.add_argument("--every", type=int, default=3, help="process every Nth frame")
    ap.add_argument("--conf", type=float, default=0.3)
    a = ap.parse_args()
    run(a.video, a.out, a.json, a.weights, a.every, a.conf)


if __name__ == "__main__":
    main()
