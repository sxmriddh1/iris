"""Core data types. Kept as plain dataclasses so they serialize to JSON trivially."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class Ecosystem(str, Enum):
    PYPI = "pypi"
    NPM = "npm"


class Outcome(str, Enum):
    """What the registry told us. Deliberately NOT a risk judgement."""
    VERIFIED = "verified"                        # registry returned metadata
    UNRESOLVED = "unresolved"                    # registry says no such package (404)
    VERIFICATION_FAILED = "verification_failed"  # rate limit / network / 5xx: unknown
    MALFORMED = "malformed"                      # could not be mapped to a valid name


class Verdict(str, Enum):
    LOW = "low_risk"
    NEEDS_REVIEW = "needs_review"
    HIGH = "high_risk"
    UNRESOLVED = "unresolved"   # watchlist: name not on registry (not "malicious")
    UNKNOWN = "unknown"         # verification failed or malformed: no judgement


@dataclass
class LLMResponse:
    """One raw model answer, kept verbatim for reproducibility."""
    prompt_id: str
    prompt_text: str
    model: str
    timestamp: str          # ISO 8601 UTC
    text: str
    ecosystem_hint: Optional[str] = None


@dataclass
class Candidate:
    """A package reference pulled out of a model response."""
    ecosystem: Ecosystem
    raw_name: str
    spec: str               # version constraint / extras, informational only
    command: str            # the command line it came from (evidence)
    prompt_id: str
    model: str
    timestamp: str
    note: str = ""          # e.g. "url/path/vcs reference: not a registry package"


@dataclass
class RegistryRecord:
    ecosystem: Ecosystem
    name: str                              # normalized
    outcome: Outcome
    http_status: Optional[int] = None
    error: str = ""
    checked_at: str = ""
    # metadata (only when VERIFIED)
    first_release: Optional[str] = None    # ISO 8601
    last_release: Optional[str] = None
    release_count: Optional[int] = None
    maintainers: list[str] = field(default_factory=list)
    has_source_repo: Optional[bool] = None
    repo_url: Optional[str] = None
    summary: str = ""
    install_hooks: Optional[bool] = None   # npm only in v0.1; None = unknown


@dataclass
class Signal:
    name: str
    points: int
    detail: str


@dataclass
class Finding:
    ecosystem: str
    name: str
    outcome: str
    verdict: str
    risk_score: Optional[int]
    signals: list[Signal]
    observations: list[dict[str, Any]]   # which model/prompt/command produced it
    registry: dict[str, Any]
    first_seen_unresolved: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
