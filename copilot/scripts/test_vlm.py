r"""Phase 0 smoke test: sample frames from a video and ask a VLM (Gemini) to detect
hand-hygiene-relevant events, returning JSON conforming to event_schema.json.

Usage (PowerShell):
    $env:GEMINI_API_KEY = "..."
    python copilot/scripts/test_vlm.py --video D:\Dizim\hand_hygiene.avi --every 5 --max-frames 6

This is a throwaway proof that VLM-on-frames detection works end-to-end before
we wire it into FastAPI (Track B3). It does NOT do face blur yet (B2).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import cv2  # type: ignore

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:  # noqa: BLE001 - dotenv optional
    pass

PROMPT = """You are a clinical hand-hygiene observer analyzing ONE video frame.
Detect ONLY events from this vocabulary that you can actually see in the frame:
hand_hygiene, glove_on, glove_off, touch_patient, touch_surroundings,
aseptic_procedure, body_fluid_exposure.

Return STRICT JSON, no prose:
{"events": [{"type": "<one of the vocab>", "confidence": <0..1>, "evidence": "<short what you see>"}]}
If nothing relevant is visible, return {"events": []}.
Do not guess; only report what is visible."""


def encode_frame(frame) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("failed to jpeg-encode frame")
    return buf.tobytes()


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


def make_client():
    from google import genai  # type: ignore
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def detect(client, model: str, jpg: bytes) -> dict:
    from google.genai import types  # type: ignore
    resp = client.models.generate_content(
        model=model,
        contents=[
            PROMPT,
            types.Part.from_bytes(data=jpg, mime_type="image/jpeg"),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return json.loads(resp.text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=r"D:\Dizim\hand_hygiene.avi")
    ap.add_argument("--every", type=float, default=5.0, help="sample 1 frame every N seconds")
    ap.add_argument("--max-frames", type=int, default=6)
    ap.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    args = ap.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: set GEMINI_API_KEY (or put it in copilot/.env).", file=sys.stderr)
        return 2

    client = make_client()

    fps, frames = sample_frames(args.video, args.every, args.max_frames)
    print(f"video fps={fps:.1f}, sampled {len(frames)} frames, model={args.model}\n")

    timeline = []
    for frame_idx, t, frame in frames:
        try:
            result = detect(client, args.model, encode_frame(frame))
        except Exception as e:  # noqa: BLE001 - smoke test, surface any error
            print(f"  t={t:6.2f}s  ERROR: {e}")
            continue
        evs = result.get("events", [])
        for e in evs:
            e["start_t"] = round(t, 2)
            e["frame_idx"] = frame_idx
        timeline.extend(evs)
        label = ", ".join(f"{e['type']}({e.get('confidence', '?')})" for e in evs) or "-"
        print(f"  t={t:6.2f}s  {label}")

    print("\n=== TIMELINE (raw) ===")
    print(json.dumps(timeline, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
