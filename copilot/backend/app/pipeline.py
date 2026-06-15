"""Orchestrates the full analysis: sample -> detect -> timeline -> reason."""
from __future__ import annotations

import json
from pathlib import Path

from . import db, reasoner, role_detect, timeline, vlm
from .schemas import JobStatus, VideoAnalysis


def _read_contact_json(path: Path) -> list[dict] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("contact_segments") or None
    except (ValueError, OSError):
        return None


def _load_contact_segments(video_path: str) -> list[dict] | None:
    """Optional YOLO proximity grounding, precomputed by perception/proximity.py.

    Lookup order:
      1. '<video_path>.contact.json'  (per-upload sidecar, hand-curated)
      2. 'uploads/contacts/<original_filename>.contact.json'  (keyed by the
         uploaded file name, stripping the random '<video_id>_' prefix) -- lets
         a precomputed clip be grounded no matter what video_id it gets.
      3. Inline ONNX role detector (role_detect.py) -- runs live for ANY upload
         when onnxruntime + the .onnx model are present (no torch needed).
    None in all -> VLM-only reasoning (graceful).
    """
    vp = Path(video_path)
    sidecar = Path(str(video_path) + ".contact.json")
    if sidecar.exists():
        return _read_contact_json(sidecar)
    # strip '<video_id>_' prefix (video_id is hex, no underscore)
    original = vp.name.split("_", 1)[1] if "_" in vp.name else vp.name
    by_name = vp.parent / "contacts" / f"{original}.contact.json"
    if by_name.exists():
        return _read_contact_json(by_name)
    if role_detect.available():
        try:
            return role_detect.contact_segments(video_path) or None
        except Exception:  # noqa: BLE001 - grounding is best-effort, never fatal
            return None
    return None


def analyze(video_path: str, video_id: str,
            every_s: float | None = None,
            max_frames: int | None = None) -> VideoAnalysis:
    duration, raw = vlm.detect_events(video_path, every_s=every_s, max_frames=max_frames)
    events = timeline.build(raw)
    findings, score = reasoner.evaluate(events, _load_contact_segments(video_path))
    return VideoAnalysis(video_id=video_id, duration_s=duration,
                         events=events, findings=findings, compliance_score=score)


def run_job(video_path: str, video_id: str) -> None:
    """Background-task entrypoint: updates DB as it progresses."""
    try:
        db.set_status(video_id, JobStatus.processing)
        analysis = analyze(video_path, video_id)
        db.set_result(video_id, analysis)
    except Exception as e:  # noqa: BLE001 - surface to client via job status
        db.set_status(video_id, JobStatus.error, message=str(e))
