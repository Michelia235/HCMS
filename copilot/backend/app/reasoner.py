"""Config-driven compliance engine (was: hardcoded WHO 5 Moments).

The medical LOGIC now lives in a hospital-editable JSON protocol (protocol.py /
agent/protocol/who_5_moments.json), not in this code. This module is a generic
interpreter: it runs the protocol's hand-state machine + flags over the event
timeline and emits a finding per triggered rule. Adding "hand wash >= 10s" or a
new ordering rule is a JSON edit -- no code change, no model retrain -- as long
as the rule references events the perception layer already detects.

Still DETERMINISTIC and auditable (no LLM in the verdict). CV grounding from the
perception layer tags patient-contact findings with confirmed/unconfirmed
without changing the verdict.
"""
from __future__ import annotations

from . import protocol as protocol_mod
from .protocol import Protocol, Rule
from .schemas import ComplianceFinding, Event, Moment, Severity, Status

_VALID_MOMENTS = {m.value for m in Moment}


def evaluate(
    events: list[Event],
    contact_segments: list[dict] | None = None,
    protocol: Protocol | None = None,
) -> tuple[list[ComplianceFinding], float | None]:
    """Evaluate compliance of an event timeline against a protocol."""
    proto = protocol or protocol_mod.default()
    ev = sorted(events, key=lambda e: e.start_t)
    findings: list[ComplianceFinding] = []

    hands = "unknown"                       # unknown | clean | dirty
    flags = {name: False for name in proto.flags}

    for i, e in enumerate(ev):
        # 1) evaluate rules triggered by this event, using state BEFORE mutation
        for rule in proto.rules:
            if e.type.value not in rule.on:
                continue
            applies, satisfied = _check(rule, e, ev, i, hands, flags, proto)
            if not applies:
                continue
            if satisfied:
                if rule.opportunity:
                    findings.append(_finding(rule, e, Status.compliant, None, rule.ok))
            else:
                findings.append(_finding(rule, e, Status.violation,
                                         _sev(rule.severity), rule.bad))

        # 2) apply this event's state mutations
        for name, flag in proto.flags.items():
            if e.type.value in flag.set_on:
                flags[name] = True
            if e.type.value in flag.clear_on:
                flags[name] = False
        if e.type.value in proto.hand_state.clean_on:
            hands = "clean"
        if e.type.value in proto.hand_state.dirty_on:
            hands = "dirty"

    _apply_cv_grounding(findings, ev, contact_segments)

    opportunities = [f for f in findings if f.status != Status.not_applicable]
    score = (round(sum(f.status == Status.compliant for f in opportunities)
                   / len(opportunities), 3) if opportunities else None)

    # 3) aggregate / threshold rules (do NOT affect the per-event score)
    findings.extend(_aggregate(proto, findings, score))
    return findings, score


def _check(rule: Rule, e: Event, ev: list[Event], i: int,
           hands: str, flags: dict, proto: Protocol) -> tuple[bool, bool]:
    """Return (applies, satisfied) for a rule at event e. require has one key."""
    req = rule.require
    if "hands" in req:
        return True, hands == req["hands"]
    if "flag_clear" in req:
        return True, not flags.get(req["flag_clear"], False)
    if "flag_set" in req:
        return True, bool(flags.get(req["flag_set"], False))
    if "min_duration_s" in req:
        dur = (e.end_t - e.start_t) if e.end_t is not None else 0.0
        return True, dur >= float(req["min_duration_s"])
    if "hygiene_before_next" in req:
        targets = set(req["hygiene_before_next"])
        for nxt in ev[i + 1:]:
            if nxt.type.value in proto.hand_state.clean_on:
                return True, True          # cleaned before next contact -> ok
            if nxt.type.value in targets:
                return True, False         # contacted again without hygiene
        return False, False                # nothing follows -> not applicable
    if "hygiene_within_before_s" in req:
        window = float(req["hygiene_within_before_s"])
        for prev in reversed(ev[:i]):
            if prev.type.value in proto.hand_state.clean_on:
                return True, (e.start_t - prev.start_t) <= window
        return True, False                 # no prior hygiene at all
    # unknown require -> treat as not applicable (forward-compatible)
    return False, False


def _aggregate(proto: Protocol, findings: list[ComplianceFinding],
               score: float | None) -> list[ComplianceFinding]:
    out: list[ComplianceFinding] = []
    viols = [f for f in findings if f.status == Status.violation]
    ops = {"lt": lambda a, b: a < b, "le": lambda a, b: a <= b,
           "gt": lambda a, b: a > b, "ge": lambda a, b: a >= b}
    for agg in proto.aggregate:
        if agg.metric == "compliance_rate":
            metric = score
        elif agg.metric == "violation_count":
            metric = float(len(viols))
        elif agg.metric == "violation_count_for":
            metric = float(sum(f.rule_id == agg.rule_id for f in viols))
        else:
            continue
        if metric is None:
            continue
        if ops.get(agg.op, lambda a, b: False)(metric, agg.value):
            out.append(ComplianceFinding(
                rule_id=agg.id, rule_name=agg.name, moment=None,
                status=Status.violation, severity=_sev(agg.severity),
                explanation=agg.bad or f"{agg.metric} {agg.op} {agg.value}"))
    return out


# Moments anchored on a hand<->patient contact -- the ones the CV layer grounds.
_CONTACT_MOMENTS = {Moment.M1, Moment.M3, Moment.M4, Moment.M5}


def _seg_overlap(t0: float, t1: float, segs: list[dict]) -> bool:
    return any(max(t0, s["start_t"]) <= min(t1, s["end_t"]) for s in segs)


def _apply_cv_grounding(findings, ev, contact_segments) -> None:
    if not contact_segments:
        return
    from .schemas import EventType
    touches = {round(e.start_t, 3): e for e in ev if e.type == EventType.touch_patient}
    for f in findings:
        if f.moment not in _CONTACT_MOMENTS or f.at_t is None:
            continue
        e = touches.get(round(f.at_t, 3))
        if e is None:
            continue
        t1 = e.end_t if e.end_t is not None else e.start_t
        f.cv_grounding = "confirmed" if _seg_overlap(e.start_t, t1, contact_segments) else "unconfirmed"


def _finding(rule: Rule, e: Event, status: Status,
             severity: Severity | None, why: str) -> ComplianceFinding:
    moment = Moment(rule.moment) if rule.moment in _VALID_MOMENTS else None
    return ComplianceFinding(
        rule_id=rule.id, rule_name=rule.name, moment=moment, status=status,
        severity=severity, at_t=e.start_t,
        evidence_event_ids=[e.id] if e.id else [], explanation=why)


def _sev(name: str | None) -> Severity | None:
    try:
        return Severity(name) if name else None
    except ValueError:
        return None
