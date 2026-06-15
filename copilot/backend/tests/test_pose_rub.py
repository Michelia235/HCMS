"""Synthetic tests for the hands-rubbing detector state machine (no model).

Feeds fabricated per-frame wrists so the RubDetector logic (hands-together +
motion + duration, patient-box suppression) is locked down without running pose
inference.
"""
from __future__ import annotations

import unittest

from app.pose_detect import RubDetector

BOX = [0.0, 0.0, 100.0, 200.0]  # person box, diag ~= 223


def person(mx, gap=4.0):
    """One person whose two wrists sit gap px apart, centred at x=mx, y=100."""
    return {"box": BOX, "wl": [mx - gap / 2, 100.0], "wr": [mx + gap / 2, 100.0]}


def feed(det, n=16, dt=0.1, moving=True, gap=4.0, patient=None):
    out = []
    for i in range(n):
        mx = 50.0 + (i % 4) * 3 if moving else 50.0   # jitter -> "rubbing"
        r = det.update([person(mx, gap)], i * dt, patient_boxes=patient)
        if r:
            out.append(r)
    # end of stream -> flush any open run (as stream_monitor does)
    r = det.flush(n * dt)
    if r:
        out.append(r)
    return out


class TestRub(unittest.TestCase):
    def test_sustained_rub_emits_event(self):
        evs = feed(RubDetector())
        self.assertEqual(len(evs), 1)
        s, e = evs[0]
        self.assertGreaterEqual(e - s, 1.0)

    def test_hands_apart_no_event(self):
        self.assertEqual(feed(RubDetector(), gap=90.0), [])

    def test_still_hands_no_event(self):
        # close together but NOT moving -> not rubbing
        self.assertEqual(feed(RubDetector(), moving=False), [])

    def test_suppressed_over_patient(self):
        # same rub motion but hands sit inside a patient box -> manipulation
        self.assertEqual(feed(RubDetector(), patient=[[0, 0, 100, 200]]), [])

    def test_short_rub_below_min_ignored(self):
        self.assertEqual(feed(RubDetector(), n=3), [])  # ~0.3s < MIN_S


if __name__ == "__main__":
    unittest.main(verbosity=2)
