"""Runtime config loaded from copilot/.env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

COPILOT_ROOT = Path(__file__).resolve().parents[2]  # .../copilot
load_dotenv(COPILOT_ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Comma-separated allowed origins for CORS. "*" = allow all (MVP default);
# in prod set CORS_ORIGINS to the Vercel frontend URL.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

SAMPLE_EVERY_S = float(os.getenv("SAMPLE_EVERY_S", "3.0"))
MAX_FRAMES = int(os.getenv("MAX_FRAMES", "40"))
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.6"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "6"))  # frames per Gemini request (free-tier saver)

UPLOAD_DIR = COPILOT_ROOT / "uploads"
DB_PATH = COPILOT_ROOT / "copilot.sqlite"
PROTOCOL_PATH = COPILOT_ROOT / "agent" / "protocol" / "who_5_moments.md"
# Machine-readable compliance policy (hospital-editable). Point at a custom JSON
# via PROTOCOL_JSON_PATH to change rules/durations/thresholds without code edits.
PROTOCOL_JSON_PATH = Path(os.getenv(
    "PROTOCOL_JSON_PATH",
    str(COPILOT_ROOT / "agent" / "protocol" / "who_5_moments.json")))

# Inline role detector (ONNX). When the model + onnxruntime are present, the
# backend grounds EVERY upload (role_detect.py) instead of needing a precomputed
# sidecar. Absent -> graceful VLM-only. Light enough for deploy (no torch).
ROLE_ONNX_PATH = Path(os.getenv(
    "ROLE_ONNX_PATH", str(COPILOT_ROOT / "perception" / "weight_v2" / "best.onnx")))
# YOLOv8m@640 on CPU is ~0.5s/frame, so bound the work: ~2.5 fps, <=80 frames
# (caps a job at ~40s of grounding regardless of video length). Tune via env.
ROLE_SAMPLE_EVERY_S = float(os.getenv("ROLE_SAMPLE_EVERY_S", "0.4"))
ROLE_MAX_FRAMES = int(os.getenv("ROLE_MAX_FRAMES", "80"))
ROLE_CONF = float(os.getenv("ROLE_CONF", "0.35"))

# Pose detector (ONNX) for the hands-rubbing hand-hygiene signal (pose_detect.py).
POSE_ONNX_PATH = Path(os.getenv(
    "POSE_ONNX_PATH", str(COPILOT_ROOT / "perception" / "weight_v2" / "pose.onnx")))

# Demo-safe mode: when a curated events fixture exists for an uploaded clip, the
# pipeline replays it INSTEAD of calling Gemini -> the demo is deterministic and
# can't die mid-presentation on a free-tier quota / outage. Fixtures live in a
# tracked dir (committed) keyed by original filename. Set DEMO_FIXTURES=0 to
# force live VLM even for known clips.
DEMO_FIXTURES_ENABLED = os.getenv("DEMO_FIXTURES", "1") == "1"
DEMO_FIXTURES_DIR = Path(os.getenv(
    "DEMO_FIXTURES_DIR", str(COPILOT_ROOT / "demo" / "fixtures")))

UPLOAD_DIR.mkdir(exist_ok=True)
