"""Transparent, rule-based risk scoring. No ML, no hidden weights.

Every point in a score comes from a named Signal with a human-readable detail, so a
verdict can always be explained. Weights are STARTING VALUES to be calibrated on a
labeled dataset (see README: evaluation plan); do not treat them as validated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .models import Outcome, RegistryRecord, Signal, Verdict
from .popular import closest_popular
from .registry import parse_ts


@dataclass(frozen=True)
class ScoringConfig:
    w_registered_after_unresolved: int = 40
    w_young_package: int = 15
    w_few_releases: int = 10
    w_no_repo: int = 10
    w_no_maintainer_info: int = 5
    w_name_similarity: int = 10
    w_install_hooks: int = 10
    young_days: int = 30
    needs_review_at: int = 30
    high_at: int = 60


def score_record(
    rec: RegistryRecord,
    first_unresolved: Optional[str],
    cfg: ScoringConfig = ScoringConfig(),
) -> tuple[Optional[int], Verdict, list[Signal], list[str]]:
    """Return (score, verdict, signals, notes). Score is None unless VERIFIED."""
    notes: list[str] = []

    if rec.outcome is Outcome.UNRESOLVED:
        notes.append("Not found on the registry. May be private, deleted, mis-parsed or hallucinated; "
                     "this is a watchlist entry, not evidence of malice.")
        near = closest_popular(rec.ecosystem, rec.name)
        if near:
            notes.append(f"Did you mean '{near[0]}'? (edit distance {near[1]})")
        return None, Verdict.UNRESOLVED, [], notes

    if rec.outcome is not Outcome.VERIFIED:
        notes.append(f"Could not verify ({rec.error or rec.outcome.value}); no judgement made.")
        return None, Verdict.UNKNOWN, [], notes

    sig: list[Signal] = []
    checked = parse_ts(rec.checked_at) if rec.checked_at else datetime.now(timezone.utc)
    first = parse_ts(rec.first_release) if rec.first_release else None

    if first_unresolved and first and first > parse_ts(first_unresolved):
        days = (first - parse_ts(first_unresolved)).days
        sig.append(Signal("registered_after_unresolved", cfg.w_registered_after_unresolved,
                          f"Name was first seen unresolved on {first_unresolved[:10]}; "
                          f"first release appeared {days} day(s) later."))
    if first:
        age = (checked - first).days
        if age < cfg.young_days:
            sig.append(Signal("young_package", cfg.w_young_package, f"First release {age} day(s) ago."))
    else:
        notes.append("No release date available; age signals skipped.")
    if rec.release_count is not None and rec.release_count <= 1:
        sig.append(Signal("few_releases", cfg.w_few_releases, f"{rec.release_count} release(s) published."))
    if rec.has_source_repo is False:
        sig.append(Signal("no_source_repo", cfg.w_no_repo, "No source repository link in metadata."))
    if not rec.maintainers:
        sig.append(Signal("no_maintainer_info", cfg.w_no_maintainer_info, "No maintainer/author listed."))
    near = closest_popular(rec.ecosystem, rec.name)
    if near:
        sig.append(Signal("name_similarity", cfg.w_name_similarity,
                          f"Within edit distance {near[1]} of popular package '{near[0]}'."))
    if rec.install_hooks:
        sig.append(Signal("install_hooks", cfg.w_install_hooks,
                          "Latest version defines preinstall/install/postinstall scripts."))

    total = min(100, sum(s.points for s in sig))
    verdict = Verdict.HIGH if total >= cfg.high_at else Verdict.NEEDS_REVIEW if total >= cfg.needs_review_at else Verdict.LOW
    return total, verdict, sig, notes
