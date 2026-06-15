"""VLM-on-frames detector (Gemini). Track B1 + B3.

Batched: multiple frames are sent in ONE request (Gemini accepts many images per
call) to stay under the free-tier request/day cap. sample_frames() yields
(frame_idx, t_seconds, bgr_frame); detect_events() returns (duration_s, [Event]).
"""
from __future__ import annotations

import json

import cv2  # type: ignore

from . import config, gemini
from .schemas import Event, EventType

VOCAB = ("hand_hygiene, glove_on, glove_off, touch_patient, touch_surroundings, "
         "aseptic_procedure, body_fluid_exposure")

BATCH_PROMPT = f"""You are a clinical hand-hygiene observer. You are given several
video frames IN ORDER, each preceded by its label "Frame <i>:". For EACH frame,
detect ONLY events you can actually see from this vocabulary:
{VOCAB}.
Be conservative: only report aseptic_procedure when you clearly see a needle/syringe,
catheter, or wound/dressing being handled - not merely gloves or supplies.

Return STRICT JSON, no prose:
{{"frames": [{{"i": <frame index>, "events": [{{"type": "<vocab>", "confidence": <0..1>, "evidence": "<short>"}}]}}]}}
Include an entry for EVERY frame index shown, with an empty events list if nothing relevant."""

_VALID = {e.value for e in EventType}


def sample_frames(video_path: str, every_s: float, max_frames: int):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps * every_s)))
    idx, out = 0, []
    while len(out) < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            out.append((idx, idx / fps, frame))
        idx += 1
    cap.release()
    return fps, out


def _encode(frame) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("failed to jpeg-encode frame")
    return buf.tobytes()


def _detect_batch(jpgs: list[bytes]) -> dict[int, list[dict]]:
    from google.genai import types  # type: ignore

    contents: list = [BATCH_PROMPT]
    for i, jpg in enumerate(jpgs):
        contents.append(f"Frame {i}:")
        contents.append(types.Part.from_bytes(data=jpg, mime_type="image/jpeg"))

    resp = gemini.generate(contents, json_mode=True)
    try:
        parsed = json.loads(resp.text)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}
    out: dict[int, list[dict]] = {}
    for fr in parsed.get("frames", []):
        try:
            out[int(fr.get("i"))] = fr.get("events", []) or []
        except (TypeError, ValueError):
            continue
    return out


def detect_events(
    video_path: str,
    every_s: float | None = None,
    max_frames: int | None = None,
    conf_threshold: float | None = None,
    batch_size: int | None = None,
) -> tuple[float, list[Event]]:
    """Run the detector over a video. Returns (duration_s, events)."""
    every_s = config.SAMPLE_EVERY_S if every_s is None else every_s
    max_frames = config.MAX_FRAMES if max_frames is None else max_frames
    thr = config.CONF_THRESHOLD if conf_threshold is None else conf_threshold
    bs = config.BATCH_SIZE if batch_size is None else batch_size

    fps, frames = sample_frames(video_path, every_s, max_frames)
    events: list[Event] = []
    n = 0
    for start in range(0, len(frames), bs):
        batch = frames[start:start + bs]
        results = _detect_batch([_encode(f) for _, _, f in batch])
        for local_i, (frame_idx, t, _frame) in enumerate(batch):
            for raw in results.get(local_i, []):
                etype = raw.get("type")
                conf = float(raw.get("confidence", 0) or 0)
                if etype not in _VALID or conf < thr:
                    continue
                events.append(Event(
                    id=f"evt_{n:04d}", type=EventType(etype),
                    start_t=round(t, 2), confidence=conf,
                    frame_idx=frame_idx, evidence=raw.get("evidence")))
                n += 1
    duration_s = round((frames[-1][1] if frames else 0.0), 2)
    return duration_s, events
