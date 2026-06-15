"""Validate the full pipeline (sample->detect->timeline->reason) without HTTP.

    set PYTHONPATH=backend
    python scripts/test_pipeline.py --every 10 --max-frames 8
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=r"D:\Dizim\hand_hygiene.avi")
    ap.add_argument("--every", type=float, default=10.0)
    ap.add_argument("--max-frames", type=int, default=8)
    args = ap.parse_args()

    a = pipeline.analyze(args.video, "test", every_s=args.every, max_frames=args.max_frames)

    print(f"duration={a.duration_s}s  score={a.compliance_score}  "
          f"events={len(a.events)}  findings={len(a.findings)}\n")
    print("=== TIMELINE (merged) ===")
    for e in a.events:
        print(f"  t={e.start_t:6.2f}  {e.type.value:<20} conf={e.confidence}")
    print("\n=== COMPLIANCE FINDINGS ===")
    for f in a.findings:
        sev = f.severity.value if f.severity else "-"
        print(f"  {f.moment.value} {f.status.value:<10} [{sev}] t={f.at_t}  {f.explanation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
