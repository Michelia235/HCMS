"""Compliance benchmark: measures the two places error actually lives.

  1. POLICY/REASONER  -- run the engine on expert-labeled event timelines and
     score which rule-violations it raises vs ground truth (precision/recall/F1
     per rule + overall verdict accuracy). Deterministic, no API cost.
  2. CV PERCEPTION    -- run the live role detector on demo clips and compare
     detected HCW<->patient contact intervals against hand-labeled true
     intervals (temporal precision/recall over time bins).

Ground truth: scripts/benchmark_gt.json. The clip set is a SEED (N=2) -- the
deliverable is the reusable harness; grow N by annotating more ward clips.

Run (backend venv, from copilot/):
  set PYTHONPATH=backend
  .venv\\Scripts\\python.exe scripts\\benchmark.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import reasoner  # noqa: E402
from app.schemas import Event, Status  # noqa: E402


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def bench_scenarios(gt) -> None:
    print("=" * 64)
    print("1) POLICY / REASONER  -- violation detection on labeled timelines")
    print("=" * 64)
    tp = fp = fn = 0
    verdict_ok = 0
    per_rule = Counter()  # rule -> [tp, fp, fn] via three counters
    rule_tp, rule_fp, rule_fn = Counter(), Counter(), Counter()
    for sc in gt["scenarios"]:
        events = []
        for i, spec in enumerate(sc["events"]):
            etype, start = spec[0], spec[1]
            end = spec[2] if len(spec) > 2 else None
            events.append(Event(id=f"e{i}", type=etype, start_t=float(start),
                                end_t=end, confidence=1.0))
        findings, _ = reasoner.evaluate(events)
        pred = Counter(f.rule_id for f in findings if f.status == Status.violation)
        gold = Counter(sc["expect_violations"])
        for rule in set(pred) | set(gold):
            t = min(pred[rule], gold[rule])
            rule_tp[rule] += t
            rule_fp[rule] += max(0, pred[rule] - gold[rule])
            rule_fn[rule] += max(0, gold[rule] - pred[rule])
            tp += t
            fp += max(0, pred[rule] - gold[rule])
            fn += max(0, gold[rule] - pred[rule])
        if bool(pred) == bool(gold):
            verdict_ok += 1
        else:
            print(f"   [verdict miss] {sc['name']}: pred={dict(pred)} gold={dict(gold)}")

    n = len(gt["scenarios"])
    print(f"\n  scenarios: {n}   verdict accuracy: {verdict_ok}/{n} "
          f"= {verdict_ok / n:.0%}")
    print("  per-rule violation detection:")
    for rule in sorted(set(rule_tp) | set(rule_fp) | set(rule_fn)):
        p, r, f = _prf(rule_tp[rule], rule_fp[rule], rule_fn[rule])
        print(f"     {rule:8s}  P={p:.2f} R={r:.2f} F1={f:.2f}  "
              f"(tp={rule_tp[rule]} fp={rule_fp[rule]} fn={rule_fn[rule]})")
    p, r, f = _prf(tp, fp, fn)
    print(f"  MICRO-AVG  P={p:.2f} R={r:.2f} F1={f:.2f}")


def bench_cv(gt, bin_s=0.2) -> None:
    print("\n" + "=" * 64)
    print("2) CV PERCEPTION  -- HCW<->patient contact vs hand-labeled intervals")
    print("=" * 64)
    try:
        from app import role_detect
        import cv2
    except ImportError as e:
        print(f"   skipped (deps missing: {e})")
        return
    if not role_detect.available():
        print("   skipped (role .onnx model not available)")
        return

    tp = fp = fn = 0
    for item in gt["cv_contact"]:
        clip = os.path.join(ROOT, "uploads", item["clip"])
        if not os.path.exists(clip):
            print(f"   [missing] {item['clip']}")
            continue
        segs = role_detect.contact_segments(clip) or []
        cap = cv2.VideoCapture(clip)
        dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 25))
        cap.release()
        truth = item["true_intervals"]
        ctp = cfp = cfn = 0
        t = 0.0
        while t < dur:
            in_pred = any(s["start_t"] <= t <= s["end_t"] for s in segs)
            in_true = any(a <= t <= b for a, b in truth)
            if in_pred and in_true:
                ctp += 1
            elif in_pred and not in_true:
                cfp += 1
            elif in_true and not in_pred:
                cfn += 1
            t += bin_s
        p, r, f = _prf(ctp, cfp, cfn)
        print(f"   {item['clip']:22s} P={p:.2f} R={r:.2f} F1={f:.2f}  "
              f"(seg={len(segs)} tp={ctp} fp={cfp} fn={cfn} bins)")
        tp += ctp; fp += cfp; fn += cfn
    p, r, f = _prf(tp, fp, fn)
    print(f"   MICRO-AVG  P={p:.2f} R={r:.2f} F1={f:.2f}")
    print("   NOTE: N=2 clips = seed only; annotate more for a real estimate.")


def bench_hygiene(gt) -> None:
    print("\n" + "=" * 64)
    print("3) HAND-HYGIENE  -- pose hands-rubbing detector (clip-level)")
    print("=" * 64)
    if "hygiene_detection" not in gt:
        print("   (no hygiene ground truth)")
        return
    try:
        from app import pose_detect, role_detect
        import cv2
    except ImportError as e:
        print(f"   skipped (deps missing: {e})")
        return
    if not pose_detect.available():
        print("   skipped (pose .onnx not available)")
        return

    tp = fp = fn = tn = 0
    for item in gt["hygiene_detection"]:
        clip = os.path.join(ROOT, "uploads", item["clip"])
        if not os.path.exists(clip):
            print(f"   [missing] {item['clip']}")
            continue
        det = pose_detect.RubDetector()
        cap = cv2.VideoCapture(clip)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        idx, fired = 0, False
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            if idx % 3 == 0:
                pboxes = [r["box"] for r in role_detect.detect_frame(fr)
                          if r["role"] == "patient"] if role_detect.available() else None
                if det.update(pose_detect.detect_wrists(fr), idx / fps,
                              patient_boxes=pboxes or None):
                    fired = True
            idx += 1
        if det.flush(idx / fps):
            fired = True
        cap.release()
        gold = item["has_hygiene"]
        mark = "OK " if fired == gold else "MISS"
        print(f"   [{mark}] {item['clip']:24s} detected={fired} truth={gold}")
        if fired and gold:
            tp += 1
        elif fired and not gold:
            fp += 1
        elif gold and not fired:
            fn += 1
        else:
            tn += 1
    p, r, f = _prf(tp, fp, fn)
    print(f"   P={p:.2f} R={r:.2f} F1={f:.2f}  (tp={tp} fp={fp} fn={fn} tn={tn})")
    print("   NOTE: FP = bedside two-handed tasks; trained action model is the real fix.")


def main():
    gt = json.load(open(os.path.join(HERE, "benchmark_gt.json"), encoding="utf-8"))
    bench_scenarios(gt)
    bench_cv(gt)
    bench_hygiene(gt)


if __name__ == "__main__":
    main()
