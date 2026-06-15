"""Truth-table tests for the deterministic WHO 5 Moments reasoner.

The reasoner is the auditable medical core, so its logic must be pinned down by
tests rather than trusted by inspection. Each case is a compact event sequence
with the findings (and CV grounding) we expect. Stdlib unittest only -- no extra
dependency, never shipped in the deploy image.

Run (from copilot/backend, env = copilot/.venv):
    set PYTHONPATH=.            # PowerShell: $env:PYTHONPATH="."
    ../.venv/Scripts/python.exe -m unittest tests.test_reasoner -v
"""
from __future__ import annotations

import unittest

from app import reasoner
from app.schemas import Event, Moment, Severity, Status


def ev(etype: str, t: float, end: float | None = None, conf: float = 1.0) -> Event:
    return Event(id=None, type=etype, start_t=float(t), end_t=end, confidence=conf)


def run(specs, segs=None):
    """Build events from (type, t[, end]) tuples and evaluate."""
    events = [ev(*s) if isinstance(s, tuple) else s for s in specs]
    # ids are assigned by callers' order; reasoner sorts by start_t internally
    for i, e in enumerate(events):
        e.id = f"evt_{i:04d}"
    return reasoner.evaluate(events, segs)


def by_moment(findings, moment):
    return [f for f in findings if f.moment == moment]


def one(findings, moment):
    fs = by_moment(findings, moment)
    assert len(fs) == 1, f"expected exactly one {moment}, got {len(fs)}: {fs}"
    return fs[0]


class TestMoment1(unittest.TestCase):
    def test_clean_before_patient_is_compliant(self):
        f, score = run([("hand_hygiene", 1), ("touch_patient", 5)])
        m1 = one(f, Moment.M1)
        self.assertEqual(m1.status, Status.compliant)
        self.assertEqual(score, 1.0)

    def test_unknown_start_is_violation_medium(self):
        f, score = run([("touch_patient", 5)])
        m1 = one(f, Moment.M1)
        self.assertEqual(m1.status, Status.violation)
        self.assertEqual(m1.severity, Severity.medium)
        self.assertEqual(score, 0.0)

    def test_dirty_from_surroundings_flags_m1_and_m5(self):
        f, _ = run([("touch_surroundings", 2), ("touch_patient", 5)])
        self.assertEqual(one(f, Moment.M1).status, Status.violation)
        m5 = one(f, Moment.M5)
        self.assertEqual(m5.status, Status.violation)
        self.assertEqual(m5.severity, Severity.low)


class TestMoment2(unittest.TestCase):
    def test_clean_before_aseptic_is_compliant(self):
        f, score = run([("hand_hygiene", 1), ("aseptic_procedure", 5)])
        m2 = one(f, Moment.M2)
        self.assertEqual(m2.status, Status.compliant)
        self.assertEqual(score, 1.0)

    def test_dirty_before_aseptic_is_violation_high(self):
        f, _ = run([("touch_patient", 2), ("aseptic_procedure", 5)])
        m2 = one(f, Moment.M2)
        self.assertEqual(m2.status, Status.violation)
        self.assertEqual(m2.severity, Severity.high)


class TestMoment3(unittest.TestCase):
    def test_fluid_then_patient_is_high(self):
        f, _ = run([("body_fluid_exposure", 2), ("touch_patient", 5)])
        m3 = one(f, Moment.M3)
        self.assertEqual(m3.status, Status.violation)
        self.assertEqual(m3.severity, Severity.high)

    def test_fluid_then_aseptic_is_high(self):
        f, _ = run([("body_fluid_exposure", 2), ("aseptic_procedure", 5)])
        self.assertEqual(one(f, Moment.M3).severity, Severity.high)


class TestMoment4(unittest.TestCase):
    def test_no_hygiene_between_two_patient_contacts(self):
        f, _ = run([("touch_patient", 2), ("touch_patient", 8)])
        m4 = one(f, Moment.M4)
        self.assertEqual(m4.status, Status.violation)
        self.assertEqual(m4.severity, Severity.low)

    def test_hygiene_between_contacts_no_m4(self):
        f, score = run([("touch_patient", 2), ("hand_hygiene", 5),
                        ("touch_patient", 8)])
        self.assertEqual(by_moment(f, Moment.M4), [])
        # first contact violation (unknown start), second compliant -> 0.5
        m1s = by_moment(f, Moment.M1)
        self.assertEqual({m.status for m in m1s},
                         {Status.violation, Status.compliant})
        self.assertEqual(score, 0.5)


class TestHandStateTransitions(unittest.TestCase):
    def test_glove_off_contaminates(self):
        f, _ = run([("hand_hygiene", 1), ("glove_off", 3), ("touch_patient", 5)])
        self.assertEqual(one(f, Moment.M1).status, Status.violation)

    def test_glove_on_does_not_contaminate(self):
        # asymmetry: putting gloves ON keeps hands clean in this model
        f, _ = run([("hand_hygiene", 1), ("glove_on", 3), ("touch_patient", 5)])
        self.assertEqual(one(f, Moment.M1).status, Status.compliant)

    def test_full_compliant_sequence_scores_one(self):
        f, score = run([("hand_hygiene", 1), ("touch_patient", 5),
                        ("hand_hygiene", 9), ("aseptic_procedure", 12)])
        self.assertEqual(one(f, Moment.M1).status, Status.compliant)
        self.assertEqual(one(f, Moment.M2).status, Status.compliant)
        self.assertEqual(score, 1.0)


class TestScoreEdges(unittest.TestCase):
    def test_no_opportunities_returns_none(self):
        # touching surroundings alone yields no Moment finding
        f, score = run([("touch_surroundings", 2)])
        self.assertEqual(f, [])
        self.assertIsNone(score)

    def test_score_is_fraction_of_opportunities(self):
        f, score = run([("touch_patient", 2), ("hand_hygiene", 5),
                        ("touch_patient", 8)])
        self.assertEqual(score, 0.5)


class TestCvGrounding(unittest.TestCase):
    SEG_HIT = [{"start_t": 4.0, "end_t": 6.0}]
    SEG_MISS = [{"start_t": 10.0, "end_t": 12.0}]

    def test_confirmed_when_segment_overlaps(self):
        f, _ = run([("touch_patient", 5)], segs=self.SEG_HIT)
        self.assertEqual(one(f, Moment.M1).cv_grounding, "confirmed")

    def test_unconfirmed_when_no_overlap(self):
        f, _ = run([("touch_patient", 5)], segs=self.SEG_MISS)
        self.assertEqual(one(f, Moment.M1).cv_grounding, "unconfirmed")

    def test_none_when_no_segments(self):
        f, _ = run([("touch_patient", 5)], segs=None)
        self.assertIsNone(one(f, Moment.M1).cv_grounding)

    def test_grounding_only_on_contact_moments(self):
        # M2 (aseptic) is not a patient-contact moment -> never CV-tagged
        f, _ = run([("hand_hygiene", 1), ("aseptic_procedure", 5)],
                   segs=self.SEG_HIT)
        self.assertIsNone(one(f, Moment.M2).cv_grounding)

    def test_verdict_unchanged_by_cv(self):
        # CV must NOT alter the deterministic verdict, only annotate it
        f0, s0 = run([("touch_patient", 5)])
        f1, s1 = run([("touch_patient", 5)], segs=self.SEG_HIT)
        self.assertEqual(s0, s1)
        self.assertEqual(one(f0, Moment.M1).status, one(f1, Moment.M1).status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
