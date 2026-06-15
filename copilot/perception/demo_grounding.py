"""Demo: WHO 5 Moments verdict BEFORE vs AFTER YOLO proximity grounding.

Runs the deterministic reasoner on stored VLM events twice -- without and with
the CV contact segments -- and prints the findings side by side so you can see
the cv_grounding tag the perception layer adds. No Gemini calls.

Run (env with pydantic = copilot/.venv), PYTHONPATH=backend:
  python copilot/perception/demo_grounding.py \
      --events copilot/uploads/result_violation.json \
      --contact copilot/uploads/demo_violation_contact.json \
      --label VIOLATION
"""
from __future__ import annotations

import argparse
import json

from app import reasoner
from app.schemas import Event


def _load_events(path: str) -> list[Event]:
    r = json.load(open(path, encoding="utf-8"))
    raw = r.get("result", r).get("events", [])
    out = []
    for i, e in enumerate(raw):
        out.append(Event(
            id=e.get("id") or f"evt_{i:04d}",
            type=e["type"],
            start_t=e["start_t"],
            end_t=e.get("end_t"),
            confidence=e.get("confidence", 1.0),
            frame_idx=e.get("frame_idx"),
            evidence=e.get("evidence"),
        ))
    return out


def _print_findings(title, findings, score, show_cv):
    print(f"\n  {title}  (score={score})")
    if not findings:
        print("    (no opportunities)")
        return
    for f in findings:
        tag = ""
        if show_cv:
            g = f.cv_grounding or "-"
            mark = {"confirmed": "[CV-OK]", "unconfirmed": "[CV-??]"}.get(g, "[  -  ]")
            tag = f" {mark}"
        sev = f"/{f.severity.value}" if f.severity else ""
        print(f"    {f.moment.value} {f.status.value}{sev} @t={f.at_t}s{tag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--contact", required=True)
    ap.add_argument("--label", default="CLIP")
    a = ap.parse_args()

    events = _load_events(a.events)
    contact = json.load(open(a.contact, encoding="utf-8"))
    segs = contact.get("contact_segments", [])

    print("=" * 64)
    print(f"  {a.label}   contact segments from YOLO: "
          + ", ".join(f"{s['start_t']}-{s['end_t']}s" for s in segs))

    f0, s0 = reasoner.evaluate(events)                 # VLM-only (live MVP)
    f1, s1 = reasoner.evaluate(events, segs)           # + CV grounding

    _print_findings("BEFORE (VLM-only)", f0, s0, show_cv=False)
    _print_findings("AFTER (+ YOLO proximity grounding)", f1, s1, show_cv=True)

    # surface contacts CV saw but no touch_patient finding covers
    covered_t = {round(f.at_t, 1) for f in f1 if f.cv_grounding == "confirmed"}
    miss = [s for s in segs
            if not any(s["start_t"] <= t <= s["end_t"] for t in covered_t)]
    if miss:
        print("\n  CV contact NOT tied to any VLM contact event (possible miss):")
        for s in miss:
            print(f"    {s['start_t']}-{s['end_t']}s")


if __name__ == "__main__":
    main()
