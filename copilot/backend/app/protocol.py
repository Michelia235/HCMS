"""Protocol = the hospital-editable compliance POLICY, loaded from JSON.

This separates POLICY (what counts as compliant -- durations, ordering, hand
state, thresholds) from the ENGINE (reasoner.py) and the PERCEPTION (what the
camera can detect). A hospital edits a JSON file -- no code, no model retrain --
as long as it only references events the perception layer already produces.

Schema (see agent/protocol/who_5_moments.json):

  hand_state.clean_on / dirty_on   events that make hands clean / contaminated
  flags.<name>.set_on / clear_on   sticky "pending" flags (e.g. fluid_pending)
  rules[]                          one finding-producing rule each:
    id, name, moment?(WHO code)
    on            : trigger event type(s)
    opportunity   : true  -> emit COMPLIANT when satisfied (counts in score)
                    false -> emit only when VIOLATED (conditional opportunity)
    require       : exactly one check:
        {"hands": "clean"}                      hands must be clean at trigger
        {"flag_clear": "<flag>"}                flag must NOT be set
        {"flag_set":   "<flag>"}                flag MUST be set
        {"min_duration_s": <n>}                 trigger event lasted >= n s
        {"hygiene_before_next": [<events>]}     a clean_on event occurs before
                                                any listed event (forward look)
        {"hygiene_within_before_s": <n>}        a clean_on event within n s
                                                BEFORE the trigger
    severity      : high | medium | low
    ok / bad      : explanation text for compliant / violation
  aggregate[]                      post-hoc threshold/count rules:
    id, name, metric (compliance_rate | violation_count |
    violation_count_for), op (lt|le|gt|ge), value, severity, [rule_id]
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field

from . import config


class HandState(BaseModel):
    clean_on: list[str] = Field(default_factory=list)
    dirty_on: list[str] = Field(default_factory=list)


class Flag(BaseModel):
    set_on: list[str] = Field(default_factory=list)
    clear_on: list[str] = Field(default_factory=list)


class Rule(BaseModel):
    id: str
    name: str = ""
    moment: Optional[str] = None
    on: list[str]
    opportunity: bool = False
    require: dict = Field(default_factory=dict)
    severity: str = "low"
    ok: str = ""
    bad: str = ""


class AggregateRule(BaseModel):
    id: str
    name: str = ""
    metric: str                      # compliance_rate | violation_count | violation_count_for
    op: str                          # lt | le | gt | ge
    value: float
    rule_id: Optional[str] = None    # for violation_count_for
    severity: str = "medium"
    bad: str = ""


class Protocol(BaseModel):
    name: str = "Protocol"
    version: str = "1.0"
    description: str = ""
    hand_state: HandState = Field(default_factory=HandState)
    flags: dict[str, Flag] = Field(default_factory=dict)
    rules: list[Rule] = Field(default_factory=list)
    aggregate: list[AggregateRule] = Field(default_factory=list)


def load(path: Union[str, Path]) -> Protocol:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Protocol(**data)


@lru_cache(maxsize=1)
def default() -> Protocol:
    """The active protocol (config.PROTOCOL_JSON_PATH, default = WHO 5 Moments)."""
    return load(config.PROTOCOL_JSON_PATH)
