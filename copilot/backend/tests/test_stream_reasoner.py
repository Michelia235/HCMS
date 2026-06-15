"""StreamReasoner (camera path) must agree with the batch reasoner.

Same protocol, same verdict -- only the engine is online. We push events one by
one and check the raised findings match what the batch engine concludes, so the
real-time alerts are as trustworthy as the offline report.
"""
from __future__ import annotations

import unittest

from app import reasoner
from app.stream_reasoner import StreamReasoner
from app.schemas import Event, Status


def ev(t, start, end=None):
    return Event(id="e", type=t, start_t=float(start), end_t=end, confidence=1.0)


def seq(specs):
    events = [ev(*s) for s in specs]
    for i, e in enumerate(events):
        e.id = f"evt_{i}"
    return events


def stream_findings(events, proto=None):
    sr = StreamReasoner(proto)
    out = []
    for e in events:
        out.extend(sr.push(e))
    return out


def viol_keys(findings):
    return sorted((f.rule_id, round(f.at_t, 2)) for f in findings
                  if f.status == Status.violation)


class TestStreamMatchesBatch(unittest.TestCase):
    CASES = [
        [("touch_patient", 5)],
        [("hand_hygiene", 1), ("touch_patient", 5)],
        [("touch_surroundings", 2), ("touch_patient", 5)],
        [("touch_patient", 2), ("touch_patient", 8)],
        [("touch_patient", 2), ("hand_hygiene", 5), ("touch_patient", 8)],
        [("body_fluid_exposure", 2), ("aseptic_procedure", 5)],
        [("hand_hygiene", 1), ("touch_patient", 5), ("hand_hygiene", 9),
         ("aseptic_procedure", 12)],
        [("hand_hygiene", 1), ("glove_off", 3), ("touch_patient", 5)],
    ]

    def test_violations_match_batch(self):
        for specs in self.CASES:
            events = seq(specs)
            batch, _ = reasoner.evaluate(list(events))
            stream = stream_findings(list(events))
            self.assertEqual(viol_keys(stream), viol_keys(batch),
                             msg=f"mismatch on {specs}")


class TestLiveAlerts(unittest.TestCase):
    def test_alert_raised_at_the_triggering_event(self):
        sr = StreamReasoner()
        self.assertEqual(sr.push(ev("touch_surroundings", 2)), [])  # no alert yet
        alerts = sr.push(ev("touch_patient", 5))                    # now it fires
        rules = {f.rule_id for f in alerts if f.status == Status.violation}
        self.assertIn("M1", rules)
        self.assertIn("M5", rules)

    def test_clean_then_touch_no_violation(self):
        sr = StreamReasoner()
        sr.push(ev("hand_hygiene", 1))
        alerts = sr.push(ev("touch_patient", 5))
        self.assertTrue(all(f.status != Status.violation for f in alerts))


if __name__ == "__main__":
    unittest.main(verbosity=2)
