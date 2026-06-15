"""Hand<->patient proximity signal for the Compliance Copilot (v2).

Turns the per-frame YOLO detections (yolo_overlay.py output) into a LOCAL CV
grounding signal for the temporal reasoner: a "contact candidate" exists when
one person's hand falls inside (or very near) ANOTHER person's body box. That is
the spatial evidence behind a `touch_patient` event -- something the VLM-only
MVP had to take on faith.

Two outputs:
  * contact segments  (time spans where a cross-person hand-in-box persists)
  * fusion report     (optional): for each VLM contact-type event, is there an
    overlapping contact segment? -> CONFIRMED / UNCONFIRMED; plus contact
    segments the VLM missed.

Run:
  python copilot/perception/proximity.py \
      --det    copilot/uploads/demo_violation_det.json \
      --events copilot/uploads/result_violation.json \
      --out    copilot/uploads/demo_violation_contact.json
"""
from __future__ import annotations

import argparse
import json
import math

# VLM event types that assert hand<->person contact (what we can ground).
CONTACT_EVENT_TYPES = {"touch_patient", "body_fluid_exposure"}

# A hand is a "contact candidate" when its normalised distance to another
# person's box is below this (0 = inside the box). ~3% of the frame diagonal.
NEAR_FRAC = 0.03
# Bridge gaps up to this many seconds when merging frames into a segment.
MERGE_GAP_S = 0.6
# Drop segments shorter than this (de-noise single-frame blips).
MIN_SEG_S = 0.3


def _point_box_dist(px, py, box):
    """Euclidean distance from point to axis-aligned box; 0 if inside."""
    x1, y1, x2, y2 = box
    dx = max(x1 - px, 0, px - x2)
    dy = max(y1 - py, 0, py - y2)
    return math.hypot(dx, dy)


def _frame_contact(persons, diag):
    """Min normalised cross-person hand->box distance in one frame.

    Returns (min_norm_dist, owner_idx, target_idx) or None if <2 persons /
    no hands. min_norm_dist == 0 means a hand is inside another person's box.
    """
    best = None
    for i, owner in enumerate(persons):
        hands = [owner[k] for k in ("hand_l", "hand_r") if k in owner]
        for j, target in enumerate(persons):
            if i == j:
                continue
            for hx, hy in hands:
                d = _point_box_dist(hx, hy, target["box"]) / diag
                if best is None or d < best[0]:
                    best = (d, i, j)
    return best


def compute_segments(det):
    diag = math.hypot(det["width"], det["height"])
    fps = det["fps"]
    marks = []  # (t, is_contact, norm_dist)
    for fr in det["detections"]:
        res = _frame_contact(fr["persons"], diag) if fr["n_persons"] >= 2 else None
        if res is None:
            marks.append((fr["t"], False, None))
        else:
            marks.append((fr["t"], res[0] <= NEAR_FRAC, res[0]))

    # merge contiguous contact frames into segments (bridge small gaps)
    segs = []
    cur = None
    for t, is_c, nd in marks:
        if is_c:
            if cur is None:
                cur = {"start_t": t, "end_t": t, "min_dist": nd}
            elif t - cur["end_t"] <= MERGE_GAP_S:
                cur["end_t"] = t
                cur["min_dist"] = min(cur["min_dist"], nd)
            else:
                segs.append(cur)
                cur = {"start_t": t, "end_t": t, "min_dist": nd}
        # non-contact frame: keep cur open until gap exceeded (handled above)
    if cur is not None:
        segs.append(cur)

    segs = [s for s in segs if s["end_t"] - s["start_t"] >= MIN_SEG_S
            or s["min_dist"] == 0.0]
    for s in segs:
        s["start_t"] = round(s["start_t"], 2)
        s["end_t"] = round(s["end_t"], 2)
        s["min_dist"] = round(s["min_dist"], 4)
        s["inside_box"] = s["min_dist"] == 0.0
    return segs


def _overlap(a0, a1, b0, b1):
    return max(a0, b0) <= min(a1, b1)


def fuse(events, segs):
    """Cross-check VLM contact events against CV contact segments."""
    rows = []
    used = set()
    for e in events:
        if e.get("type") not in CONTACT_EVENT_TYPES:
            continue
        e0 = e["start_t"]
        e1 = e["end_t"] if e.get("end_t") is not None else e0
        hit = None
        for k, s in enumerate(segs):
            if _overlap(e0, e1, s["start_t"], s["end_t"]):
                hit = k
                used.add(k)
                break
        rows.append({
            "event": e["type"], "t": [e0, e1],
            "cv": "CONFIRMED" if hit is not None else "UNCONFIRMED",
            "seg": segs[hit] if hit is not None else None,
        })
    missed = [s for k, s in enumerate(segs) if k not in used]
    return rows, missed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--det", required=True, help="yolo_overlay detections JSON")
    ap.add_argument("--events", default="", help="VLM result JSON (for fusion)")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    det = json.load(open(a.det, encoding="utf-8"))
    segs = compute_segments(det)
    print(f"[prox] {det['video']}  contact segments = {len(segs)}")
    for s in segs:
        tag = "INSIDE-box" if s["inside_box"] else f"min_dist={s['min_dist']}"
        print(f"   contact {s['start_t']}-{s['end_t']}s  ({tag})")

    out = {"video": det["video"], "near_frac": NEAR_FRAC, "contact_segments": segs}

    if a.events:
        r = json.load(open(a.events, encoding="utf-8"))
        events = r.get("result", r).get("events", [])
        rows, missed = fuse(events, segs)
        print("\n[prox] fusion vs VLM contact events:")
        for row in rows:
            extra = f" -> seg {row['seg']['start_t']}-{row['seg']['end_t']}s" if row["seg"] else ""
            print(f"   {row['event']} @t={row['t']}  [{row['cv']}]{extra}")
        if missed:
            print("   CV contact NOT reported by VLM:")
            for s in missed:
                print(f"      {s['start_t']}-{s['end_t']}s")
        out["fusion"] = {"events": rows,
                         "cv_only_contacts": missed}

    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"), indent=2)
        print(f"\n[prox] -> {a.out}")


if __name__ == "__main__":
    main()
