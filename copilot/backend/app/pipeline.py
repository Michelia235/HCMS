"""Orchestrates the full analysis: sample -> detect -> timeline -> reason."""
from __future__ import annotations

import json
from pathlib import Path

from . import config, db, reasoner, role_detect, timeline, vlm
from .schemas import Event, JobStatus, VideoAnalysis


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


def _original_name(video_path: str) -> str:
    """Uploads are saved as '<video_id>_<original>'; recover the original name
    (video_id is hex with no underscore) so fixtures can be keyed by clip name."""
    name = Path(video_path).name
    return name.split("_", 1)[1] if "_" in name else name


def _load_events_fixture(video_path: str) -> tuple[float, list[Event]] | None:
    """Demo-safe replay: if a curated events fixture exists for this clip, return
    (duration_s, events) and skip the live VLM entirely. None -> run the VLM.

    Lookup (when DEMO_FIXTURES enabled):
      1. '<video_path>.events.json'                      (per-upload sidecar)
      2. '<DEMO_FIXTURES_DIR>/<original_filename>.events.json'  (committed)
    """
    if not config.DEMO_FIXTURES_ENABLED:
        return None
    candidates = [
        Path(str(video_path) + ".events.json"),
        config.DEMO_FIXTURES_DIR / f"{_original_name(video_path)}.events.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            events = [Event(**e) for e in data.get("events", [])]
        except (ValueError, OSError, TypeError):
            return None
        return float(data.get("duration_s", 0.0)), events
    return None


def analyze(video_path: str, video_id: str,
            every_s: float | None = None,
            max_frames: int | None = None) -> VideoAnalysis:
    fixture = _load_events_fixture(video_path)
    if fixture is not None:
        duration, raw = fixture
    else:
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
