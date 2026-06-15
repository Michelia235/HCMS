"""Track B4: turn raw per-frame detections into a clean event timeline.

The VLM emits multiple events per frame (e.g. doctor + nurse both washing) and
the same ongoing action repeats across adjacent sampled frames. For the MVP we
assume a single primary actor and collapse duplicates so the reasoner sees one
event per (type, time-cluster).
"""
from __future__ import annotations

from .schemas import Event

# events of the same type within this many seconds are treated as one ongoing action
MERGE_WINDOW_S = 6.0


def build(events: list[Event]) -> list[Event]:
    if not events:
        return []
    ordered = sorted(events, key=lambda e: (e.start_t, e.type.value))

    merged: list[Event] = []
    # keep the highest-confidence representative per (type, cluster)
    last_by_type: dict[str, Event] = {}
    for e in ordered:
        prev = last_by_type.get(e.type.value)
        if prev is not None and e.start_t - prev.start_t <= MERGE_WINDOW_S:
            # same ongoing action: extend interval, keep best confidence/evidence
            prev.end_t = e.start_t
            if e.confidence > prev.confidence:
                prev.confidence = e.confidence
                prev.evidence = e.evidence
            continue
        merged.append(e)
        last_by_type[e.type.value] = e

    merged.sort(key=lambda e: e.start_t)
    for i, e in enumerate(merged):
        e.id = f"evt_{i:04d}"
    return merged
