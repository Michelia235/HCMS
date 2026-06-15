"""Online (streaming) compliance engine for the CAMERA path.

The batch reasoner (reasoner.py) evaluates a whole video at once. A live camera
needs to react as each event arrives, so this is a STATEFUL interpreter of the
SAME protocol: push events one by one, get violations the instant they happen.

It honours the protocol's hand-state machine, flags, and per-event rules
(hands / flag / min_duration_s / hygiene_within_before_s). Forward-looking M4
("hygiene_before_next") is handled online via an open-contact marker: a patient
contact that is not cleaned before the next contact fires M4 at that moment.

Verdict stays deterministic; the same JSON policy as the batch engine drives it.
"""
from __future__ import annotations

from . import protocol as protocol_mod
from .protocol import Protocol
from .schemas import ComplianceFinding, Event, Moment, Severity, Status

_VALID_MOMENTS = {m.value for m in Moment}


class StreamReasoner:
    def __init__(self, protocol: Protocol | None = None):
        self.proto = protocol or protocol_mod.default()
        self.hands = "unknown"
        self.flags = {name: False for name in self.proto.flags}
        self.last_hygiene_t: float | None = None
        self.open_contact: Event | None = None   # touch not yet followed by hygiene
        # cache the forward-looking M4-style rules and their target sets
        self._fwd_rules = [(r, set(r.require["hygiene_before_next"]))
                           for r in self.proto.rules
                           if "hygiene_before_next" in r.require]

    def push(self, e: Event) -> list[ComplianceFinding]:
        """Feed one event; return findings (alerts) raised by it."""
        out: list[ComplianceFinding] = []
        et = e.type.value

        # 1) immediate (non-forward) rules, using state BEFORE mutation
        for rule in self.proto.rules:
            if et not in rule.on or "hygiene_before_next" in rule.require:
                continue
            applies, satisfied = self._check(rule, e)
            if not applies:
                continue
            if satisfied:
                if rule.opportunity:
                    out.append(self._finding(rule, e, Status.compliant, None, rule.ok))
            else:
                out.append(self._finding(rule, e, Status.violation,
                                         _sev(rule.severity), rule.bad))

        # 2) forward-looking M4: a new target contact while a contact is open
        for rule, targets in self._fwd_rules:
            if et in targets and self.open_contact is not None:
                out.append(self._finding(rule, self.open_contact, Status.violation,
                                         _sev(rule.severity), rule.bad))
                self.open_contact = None

        # 3) state mutations
        if et in self.proto.hand_state.clean_on:
            self.last_hygiene_t = e.start_t
            self.open_contact = None
        for name, flag in self.proto.flags.items():
            if et in flag.set_on:
                self.flags[name] = True
            if et in flag.clear_on:
                self.flags[name] = False
        if et in self.proto.hand_state.clean_on:
            self.hands = "clean"
        if et in self.proto.hand_state.dirty_on:
            self.hands = "dirty"
        # register a new open contact for forward M4 rules
        for rule, _ in self._fwd_rules:
            if et in rule.on:
                self.open_contact = e

        return out

    def _check(self, rule, e: Event) -> tuple[bool, bool]:
        req = rule.require
        if "hands" in req:
            return True, self.hands == req["hands"]
        if "flag_clear" in req:
            return True, not self.flags.get(req["flag_clear"], False)
        if "flag_set" in req:
            return True, bool(self.flags.get(req["flag_set"], False))
        if "min_duration_s" in req:
            dur = (e.end_t - e.start_t) if e.end_t is not None else 0.0
            return True, dur >= float(req["min_duration_s"])
        if "hygiene_within_before_s" in req:
            if self.last_hygiene_t is None:
                return True, False
            return True, (e.start_t - self.last_hygiene_t) <= float(req["hygiene_within_before_s"])
        return False, False

    def _finding(self, rule, e, status, severity, why) -> ComplianceFinding:
        moment = Moment(rule.moment) if rule.moment in _VALID_MOMENTS else None
        return ComplianceFinding(
            rule_id=rule.id, rule_name=rule.name, moment=moment, status=status,
            severity=severity, at_t=e.start_t,
            evidence_event_ids=[e.id] if e.id else [], explanation=why)


def _sev(name):
    try:
        return Severity(name) if name else None
    except ValueError:
        return None
