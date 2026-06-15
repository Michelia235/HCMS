"""Pydantic schemas - single source of truth for the Copilot data contract.

Mirrors agent/schemas/event_schema.json. Used by FastAPI endpoints, the VLM
detector, and the compliance reasoner.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    hand_hygiene = "hand_hygiene"
    glove_on = "glove_on"
    glove_off = "glove_off"
    touch_patient = "touch_patient"
    touch_surroundings = "touch_surroundings"
    aseptic_procedure = "aseptic_procedure"
    body_fluid_exposure = "body_fluid_exposure"


class Event(BaseModel):
    id: Optional[str] = None
    type: EventType
    start_t: float = Field(..., description="seconds from video start")
    end_t: Optional[float] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    frame_idx: Optional[int] = None
    evidence: Optional[str] = None


class Moment(str, Enum):
    M1 = "M1"  # before touching a patient
    M2 = "M2"  # before aseptic procedure
    M3 = "M3"  # after body fluid exposure
    M4 = "M4"  # after touching a patient
    M5 = "M5"  # after touching surroundings


class Status(str, Enum):
    compliant = "compliant"
    violation = "violation"
    not_applicable = "not_applicable"


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ComplianceFinding(BaseModel):
    # rule_id is the protocol rule that produced this finding (e.g. "M1",
    # "HW_MIN"). moment is the WHO 5-Moments code when the rule maps to one;
    # it is None for hospital-custom rules that aren't a WHO moment.
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    moment: Optional[Moment] = None
    status: Status
    severity: Optional[Severity] = None
    at_t: Optional[float] = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    explanation: str = ""
    # CV grounding from the YOLO proximity layer (perception/proximity.py):
    # "confirmed"   = a hand<->patient contact segment overlaps this moment,
    # "unconfirmed" = the VLM claimed contact but no CV segment backs it,
    # None          = not a patient-contact moment / no CV signal available.
    cv_grounding: Optional[str] = None


class VideoAnalysis(BaseModel):
    video_id: str
    duration_s: Optional[float] = None
    events: list[Event] = Field(default_factory=list)
    findings: list[ComplianceFinding] = Field(default_factory=list)
    compliance_score: Optional[float] = None  # compliant / total opportunities


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    error = "error"


class VideoJob(BaseModel):
    video_id: str
    status: JobStatus
    message: Optional[str] = None
    result: Optional[VideoAnalysis] = None


class ChatRequest(BaseModel):
    question: str
    video_id: Optional[str] = None  # None = ask across all videos


class ChatResponse(BaseModel):
    answer: str
    sql: Optional[str] = None  # text-to-SQL query used, for transparency
