"""Tests for config-driven rule types beyond the WHO-5 hand-state core.

Locks down the new protocol primitives (min_duration_s, hygiene_within_before_s,
aggregate threshold/count) so a hospital editing JSON gets predictable results.
Uses an in-line Protocol object so the tests don't depend on a file on disk.
"""
from __future__ import annotations

import unittest

from app import reasoner
from app.protocol import Protocol
from app.schemas import Event, Status

BASE = {
    "hand_state": {"clean_on": ["hand_hygiene"],
                   "dirty_on": ["touch_patient", "glove_off"]},
    "flags": {},
}


def ev(t, start, end=None):
    return Event(id="e", type=t, start_t=float(start), end_t=end, confidence=1.0)


def run(specs, proto_dict):
    events = [ev(*s) for s in specs]
    for i, e in enumerate(events):
        e.id = f"evt_{i}"
    return reasoner.evaluate(events, protocol=Protocol(**proto_dict))


def by_rule(findings, rid):
    return [f for f in findings if f.rule_id == rid]


class TestMinDuration(unittest.TestCase):
    PROTO = {**BASE, "rules": [
        {"id": "HW_MIN", "name": "wash >=10s", "on": ["hand_hygiene"],
         "opportunity": True, "require": {"min_duration_s": 10}, "severity": "high"}]}

    def test_short_wash_violates(self):
        f, _ = run([("hand_hygiene", 0, 5)], self.PROTO)
        self.assertEqual(by_rule(f, "HW_MIN")[0].status, Status.violation)

    def test_long_wash_compliant(self):
        f, _ = run([("hand_hygiene", 0, 12)], self.PROTO)
        self.assertEqual(by_rule(f, "HW_MIN")[0].status, Status.compliant)

    def test_missing_end_treated_as_zero(self):
        f, _ = run([("hand_hygiene", 0, None)], self.PROTO)
        self.assertEqual(by_rule(f, "HW_MIN")[0].status, Status.violation)


class TestWindow(unittest.TestCase):
    PROTO = {**BASE, "rules": [
        {"id": "WIN", "name": "wash within 60s before touch", "on": ["touch_patient"],
         "opportunity": False, "require": {"hygiene_within_before_s": 60},
         "severity": "medium"}]}

    def test_recent_hygiene_ok_no_finding(self):
        f, _ = run([("hand_hygiene", 0, 3), ("touch_patient", 30)], self.PROTO)
        self.assertEqual(by_rule(f, "WIN"), [])

    def test_stale_hygiene_violates(self):
        f, _ = run([("hand_hygiene", 0, 3), ("touch_patient", 80)], self.PROTO)
        self.assertEqual(by_rule(f, "WIN")[0].status, Status.violation)

    def test_no_prior_hygiene_violates(self):
        f, _ = run([("touch_patient", 10)], self.PROTO)
        self.assertEqual(by_rule(f, "WIN")[0].status, Status.violation)


class TestAggregate(unittest.TestCase):
    PROTO = {**BASE, "rules": [
        {"id": "M1", "moment": "M1", "on": ["touch_patient"], "opportunity": True,
         "require": {"hands": "clean"}, "severity": "medium"}],
        "aggregate": [
            {"id": "SHIFT", "name": "rate<0.8", "metric": "compliance_rate",
             "op": "lt", "value": 0.8, "severity": "high", "bad": "low rate"}]}

    def test_threshold_fires_when_rate_low(self):
        # one dirty touch -> rate 0.0 < 0.8 -> aggregate violation
        f, score = run([("touch_patient", 5)], self.PROTO)
        self.assertEqual(score, 0.0)
        self.assertEqual(by_rule(f, "SHIFT")[0].status, Status.violation)

    def test_threshold_silent_when_rate_high(self):
        f, score = run([("hand_hygiene", 0, 1), ("touch_patient", 5)], self.PROTO)
        self.assertEqual(score, 1.0)
        self.assertEqual(by_rule(f, "SHIFT"), [])


class TestCustomRuleHasNoMoment(unittest.TestCase):
    def test_rule_id_set_moment_none(self):
        proto = {**BASE, "rules": [
            {"id": "HW_MIN", "on": ["hand_hygiene"], "opportunity": True,
             "require": {"min_duration_s": 10}, "severity": "high"}]}
        f, _ = run([("hand_hygiene", 0, 3)], proto)
        finding = by_rule(f, "HW_MIN")[0]
        self.assertEqual(finding.rule_id, "HW_MIN")
        self.assertIsNone(finding.moment)


if __name__ == "__main__":
    unittest.main(verbosity=2)
