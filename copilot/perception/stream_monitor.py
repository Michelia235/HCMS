"""Real-time compliance monitor for the CAMERA path.

Reads a live source (webcam index, RTSP url, or a video file treated as a
stream), detects events ONLINE with the light role detector (ONNX, no torch),
and feeds them to the streaming compliance engine (app/stream_reasoner.py) so
violations print the instant they happen -- driven by the SAME hospital JSON
policy as the offline report.

Two online event detectors (both need only person/role boxes -> ONNX-light):
  * touch_patient : an HCW (doctor|nurse) box overlaps a PATIENT box, debounced.
  * hand_hygiene  : a person dwells in a configured "hygiene zone" (sink /
    dispenser ROI). The DWELL TIME becomes the event duration -> this is how the
    camera measures "rua tay >= 10s" (a min_duration_s rule in the protocol).
    The zone is config, not code -- fits the policy-as-config design.

Run (backend venv has onnxruntime; needs the role .onnx):
  # webcam, hygiene zone = pixels x1,y1,x2,y2
  set PYTHONPATH=backend
  python perception/stream_monitor.py --source 0 --zone 20,20,200,460
  # a clip as a stream, annotated output
  python perception/stream_monitor.py --source copilot/uploads/demo_violation.mp4 \
      --out copilot/uploads/demo_violation_stream.mp4 --every 3
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
from app import pose_detect  # noqa: E402
from app import protocol as protocol_mod  # noqa: E402
from app import role_detect  # noqa: E402
from app.schemas import Event, EventType  # noqa: E402
from app.stream_reasoner import StreamReasoner  # noqa: E402

HCW = {"doctor", "nurse"}
TOUCH_DEBOUNCE_S = 0.4    # contact must persist this long before emitting
HYGIENE_MIN_REPORT_S = 0.6  # ignore brief dips into the zone


def _overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _in_zone(box, zone):
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return zone[0] <= cx <= zone[2] and zone[1] <= cy <= zone[3]


def _emit(reasoner, etype, start_t, end_t, log):
    e = Event(id=f"evt_{int(start_t*1000)}", type=EventType(etype),
              start_t=round(start_t, 2), end_t=round(end_t, 2) if end_t else None,
              confidence=1.0)
    dur = f" ({end_t - start_t:.1f}s)" if end_t else ""
    print(f"  [t={start_t:5.1f}s] EVENT {etype}{dur}")
    for f in reasoner.push(e):
        tag = "VIOLATION" if f.status.value == "violation" else "ok"
        sev = f"/{f.severity.value}" if f.severity else ""
        mark = "  >>> ALERT" if f.status.value == "violation" else "      "
        line = f"{mark} [{f.rule_id}{sev}] {f.status.value}: {f.explanation}"
        print(line)
        log.append((start_t, f))


def run(source, zone, out_path, every, conf, hygiene_mode="zone"):
    if not role_detect.available():
        raise SystemExit("role ONNX model not available (perception/weight_v2/best.onnx)")
    proto = protocol_mod.default()
    reasoner = StreamReasoner(proto)
    rub = pose_detect.RubDetector() if hygiene_mode == "rub" else None
    if hygiene_mode == "rub" and not pose_detect.available():
        raise SystemExit("pose ONNX model not available (perception/weight_v2/pose.onnx)")
    print(f"[stream] policy = {proto.name}")
    print(f"[stream] source = {source}  hygiene_mode = {hygiene_mode}  zone = {zone}")

    cap = cv2.VideoCapture(int(source) if str(source).isdigit() else source)
    if not cap.isOpened():
        raise SystemExit(f"cannot open source {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = None
    if out_path:
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                                 fps / every, (w, h))

    touch_on_since = None       # contact onset time (None = no contact)
    touch_emitted = False
    hygiene_since = None        # dwell onset time
    idx, t0 = 0, time.time()
    log = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every == 0:
            t = idx / fps
            persons = role_detect.detect_frame(frame, conf_thresh=conf)
            hcws = [p for p in persons if p["role"] in HCW]
            patients = [p for p in persons if p["role"] == "patient"]

            # --- touch_patient: HCW box overlaps patient box ---
            contact = any(_overlap(hc["box"], pt["box"])
                          for hc in hcws for pt in patients)
            if contact:
                if touch_on_since is None:
                    touch_on_since, touch_emitted = t, False
                elif not touch_emitted and t - touch_on_since >= TOUCH_DEBOUNCE_S:
                    _emit(reasoner, "touch_patient", touch_on_since, None, log)
                    touch_emitted = True
            else:
                touch_on_since, touch_emitted = None, False

            # --- hand_hygiene ---
            if rub is not None:
                # pose-based hands-rubbing; suppress over patient (manipulation)
                pboxes = [pt["box"] for pt in patients]
                done = rub.update(pose_detect.detect_wrists(frame), t,
                                  patient_boxes=pboxes or None)
                if done:
                    _emit(reasoner, "hand_hygiene", done[0], done[1], log)
            elif zone is not None:
                in_zone = any(_in_zone(p["box"], zone) for p in persons)
                if in_zone:
                    if hygiene_since is None:
                        hygiene_since = t
                elif hygiene_since is not None:
                    if t - hygiene_since >= HYGIENE_MIN_REPORT_S:
                        _emit(reasoner, "hand_hygiene", hygiene_since, t, log)
                    hygiene_since = None

            if writer is not None:
                _draw(frame, persons, zone, contact)
                writer.write(frame)
        idx += 1

    # close an open hygiene run at end of stream
    if rub is not None:
        done = rub.flush(idx / fps)
        if done:
            _emit(reasoner, "hand_hygiene", done[0], done[1], log)
    elif zone is not None and hygiene_since is not None:
        _emit(reasoner, "hand_hygiene", hygiene_since, idx / fps, log)
    cap.release()
    if writer is not None:
        writer.release()
        print(f"[stream] annotated -> {out_path}")
    elapsed = time.time() - t0
    n_alerts = sum(1 for _, f in log if f.status.value == "violation")
    print(f"[stream] done: {idx} frames in {elapsed:.1f}s "
          f"(~{idx/max(elapsed,1e-6):.1f} fps), live alerts = {n_alerts}")


def _draw(frame, persons, zone, contact):
    if zone is not None:
        cv2.rectangle(frame, (zone[0], zone[1]), (zone[2], zone[3]),
                      (255, 255, 0), 2)
        cv2.putText(frame, "hygiene zone", (zone[0], max(0, zone[1] - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
    col = {"doctor": (255, 120, 0), "nurse": (0, 200, 0), "patient": (0, 140, 255)}
    for p in persons:
        x1, y1, x2, y2 = [int(v) for v in p["box"]]
        cv2.rectangle(frame, (x1, y1), (x2, y2), col.get(p["role"], (160, 160, 160)), 2)
        cv2.putText(frame, p["role"], (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col.get(p["role"], (160, 160, 160)),
                    2, cv2.LINE_AA)
    if contact:
        cv2.putText(frame, "CONTACT", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 255), 2, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="0", help="webcam index | rtsp url | file")
    ap.add_argument("--zone", default="", help="hygiene zone 'x1,y1,x2,y2' (pixels)")
    ap.add_argument("--hygiene-mode", default="zone", choices=["zone", "rub"],
                    help="zone = dwell in ROI; rub = pose hands-rubbing detector")
    ap.add_argument("--out", default="")
    ap.add_argument("--every", type=int, default=3)
    ap.add_argument("--conf", type=float, default=0.35)
    a = ap.parse_args()
    zone = [int(v) for v in a.zone.split(",")] if a.zone else None
    run(a.source, zone, a.out, a.every, a.conf, hygiene_mode=a.hygiene_mode)


if __name__ == "__main__":
    main()
