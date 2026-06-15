"""Demo-safe mode: the events fixture loader replays a curated timeline instead
of calling the VLM, so a live demo can't die on a Gemini quota/outage."""
import json
import tempfile
import unittest
from pathlib import Path

from app import config, pipeline
from app.schemas import EventType


class TestEventsFixture(unittest.TestCase):
    def setUp(self):
        self._orig_dir = config.DEMO_FIXTURES_DIR
        self._orig_enabled = config.DEMO_FIXTURES_ENABLED
        self._tmp = tempfile.TemporaryDirectory()
        config.DEMO_FIXTURES_DIR = Path(self._tmp.name)
        config.DEMO_FIXTURES_ENABLED = True

    def tearDown(self):
        config.DEMO_FIXTURES_DIR = self._orig_dir
        config.DEMO_FIXTURES_ENABLED = self._orig_enabled
        self._tmp.cleanup()

    def _write(self, name, payload):
        (config.DEMO_FIXTURES_DIR / name).write_text(
            json.dumps(payload), encoding="utf-8")

    def test_loads_fixture_by_original_name(self):
        # uploads are saved as '<video_id>_<original>'; loader strips the prefix
        self._write("demo_compliant.mp4.events.json", {
            "duration_s": 14.0,
            "events": [
                {"type": "hand_hygiene", "start_t": 5.0, "confidence": 0.96},
                {"type": "touch_patient", "start_t": 10.0, "confidence": 0.95},
            ],
        })
        out = pipeline._load_events_fixture("uploads/abc123_demo_compliant.mp4")
        self.assertIsNotNone(out)
        duration, events = out
        self.assertEqual(duration, 14.0)
        self.assertEqual([e.type for e in events],
                         [EventType.hand_hygiene, EventType.touch_patient])

    def test_no_fixture_returns_none(self):
        self.assertIsNone(
            pipeline._load_events_fixture("uploads/abc123_unknown_clip.mp4"))

    def test_disabled_flag_skips_fixture(self):
        self._write("demo_compliant.mp4.events.json",
                    {"duration_s": 1.0, "events": []})
        config.DEMO_FIXTURES_ENABLED = False
        self.assertIsNone(
            pipeline._load_events_fixture("uploads/abc123_demo_compliant.mp4"))


if __name__ == "__main__":
    unittest.main()
