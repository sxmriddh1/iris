"""Orchestration: responses -> candidates -> registry verification -> scored findings."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable, Iterable

from .extract import extract_candidates
from .ledger import Ledger
from .models import Candidate, Ecosystem, Finding, LLMResponse, Outcome, Verdict
from .normalize import normalize
from .registry import RegistryClient
from .scoring import ScoringConfig, score_record

_ORDER = {Verdict.HIGH: 0, Verdict.NEEDS_REVIEW: 1, Verdict.UNRESOLVED: 2, Verdict.UNKNOWN: 3, Verdict.LOW: 4}


def _obs(c: Candidate) -> dict:
    return {"model": c.model, "prompt_id": c.prompt_id, "timestamp": c.timestamp,
            "command": c.command, "spec": c.spec}


def analyze(
    responses: Iterable[LLMResponse],
    registry: RegistryClient,
    ledger: Ledger,
    cfg: ScoringConfig = ScoringConfig(),
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> list[Finding]:
    groups: "OrderedDict[tuple[str, str], list[Candidate]]" = OrderedDict()
    malformed: "OrderedDict[tuple[str, str], list[Candidate]]" = OrderedDict()

    for resp in responses:
        for c in extract_candidates(resp):
            canon = None if c.note else normalize(c.ecosystem, c.raw_name)
            bucket, key = (groups, (c.ecosystem.value, canon)) if canon else (malformed, (c.ecosystem.value, c.raw_name))
            bucket.setdefault(key, []).append(c)

    findings: list[Finding] = []
    stamp = now().isoformat().replace("+00:00", "Z")

    for (eco_v, raw), cands in malformed.items():
        findings.append(Finding(
            ecosystem=eco_v, name=raw, outcome=Outcome.MALFORMED.value, verdict=Verdict.UNKNOWN.value,
            risk_score=None, signals=[], observations=[_obs(c) for c in cands], registry={},
            notes=[cands[0].note or "Not a valid package name for this ecosystem; not sent to the registry."]))

    for (eco_v, name), cands in groups.items():
        eco = Ecosystem(eco_v)
        rec = registry.verify(eco, name)
        ledger.record(eco_v, name, rec.outcome, stamp)
        first_unres = ledger.first_unresolved(eco_v, name)
        score, verdict, signals, notes = score_record(rec, first_unres, cfg)
        findings.append(Finding(
            ecosystem=eco_v, name=name, outcome=rec.outcome.value, verdict=verdict.value,
            risk_score=score, signals=signals, observations=[_obs(c) for c in cands],
            registry={k: (v.value if hasattr(v, "value") else v) for k, v in rec.__dict__.items()},
            first_seen_unresolved=first_unres, notes=notes))

    findings.sort(key=lambda f: (_ORDER[Verdict(f.verdict)], -(f.risk_score or 0), f.name))
    return findings
