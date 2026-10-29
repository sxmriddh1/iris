"""Request/response contracts. FindingIn mirrors the JSON written by `iris-scout analyze --json`."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Eco = Literal["pypi", "npm"]
Outcome = Literal["verified", "unresolved", "verification_failed", "malformed"]
ScoutVerdict = Literal["low_risk", "needs_review", "high_risk", "unresolved", "unknown"]
Status = Literal["unreviewed", "confirmed_malicious", "false_positive", "allowlisted"]
MAX_FINDINGS, MAX_LOOKUP = 1000, 200


class SignalIO(BaseModel):
    name: str
    points: int
    detail: str = ""


class ObservationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str
    prompt_id: str
    timestamp: str
    command: str = ""
    spec: str = ""


class FindingIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ecosystem: Eco
    name: str = Field(min_length=1, max_length=256)
    outcome: Outcome
    verdict: ScoutVerdict
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    signals: list[SignalIO] = Field(default_factory=list)
    observations: list[ObservationIn] = Field(default_factory=list)
    registry: dict[str, Any] = Field(default_factory=dict)
    first_seen_unresolved: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class IngestMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_id: Optional[str] = Field(None, max_length=64)
    generated_at: Optional[str] = None
    version: Optional[str] = None


class IngestRequest(BaseModel):
    meta: IngestMeta = Field(default_factory=IngestMeta)
    findings: list[FindingIn] = Field(max_length=MAX_FINDINGS)


class Rejected(BaseModel):
    name: str
    reason: str


class IngestResult(BaseModel):
    run_id: str
    packages_created: int
    packages_updated: int
    observations_added: int
    assessments_added: int
    rejected: list[Rejected]


class PackageRef(BaseModel):
    ecosystem: Eco
    name: str = Field(min_length=1, max_length=256)


class LookupRequest(BaseModel):
    packages: list[PackageRef] = Field(min_length=1, max_length=MAX_LOOKUP)


class LookupResult(BaseModel):
    ecosystem: str
    name: str                      # normalized (or the raw input if it was invalid)
    found: bool
    verdict: str                   # see README verdict table
    risk_score: Optional[int] = None
    status: str = "unreviewed"
    status_note: str = ""
    stale: bool = False
    assessed_at: Optional[str] = None
    latest_attempt_failed: bool = False
    first_seen_unresolved: Optional[str] = None
    signals: list[SignalIO] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    observation_count: int = 0
    models: list[str] = Field(default_factory=list)


class LookupResponse(BaseModel):
    results: list[LookupResult]


class ReviewRequest(BaseModel):
    ecosystem: Eco
    name: str = Field(min_length=1, max_length=256)
    status: Status
    note: str = Field("", max_length=2000)


class PackageList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[LookupResult]


class PackageDetail(BaseModel):
    summary: LookupResult
    observations: list[dict[str, Any]]
    assessment_history: list[dict[str, Any]]
    review_history: list[dict[str, Any]]
