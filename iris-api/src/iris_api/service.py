"""Business logic: ingestion, lookup, review. No HTTP concerns in here.

Key rules (each one is tested):
- Re-ingesting the same run is a no-op (idempotent): observations by hash, assessments by (package, run).
- Only CONCLUSIVE assessments (verified/unresolved) define a package's current verdict. A later
  registry outage (verification_failed) never downgrades a High Risk verdict to "unknown".
- Assessments are ordered by when the registry was CHECKED, not when we received them, so an
  old file ingested late cannot overwrite newer knowledge.
- Unknown packages are "not_assessed", never "low_risk". Absence of evidence is not safety.
- Analyst status overrides the automated verdict (confirmed_malicious / allowlisted).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings
from .errors import ApiError
from .models import Assessment, Observation, Package, ReviewEvent, utcnow
from .names import normalize
from .schemas import (IngestRequest, IngestResult, LookupResult, PackageDetail, PackageList, PackageRef,
                      Rejected, ReviewRequest, SignalIO)

CONCLUSIVE = ("verified", "unresolved")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse(s: Optional[str], fallback: datetime) -> datetime:
    if not s:
        return fallback
    try:
        return _aware(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except ValueError:
        return fallback


def _iso(dt: datetime) -> str:
    return _aware(dt).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def obs_key(model: str, prompt_id: str, ts: str, command: str) -> str:
    return hashlib.sha256("\x1f".join((model, prompt_id, ts, command)).encode()).hexdigest()


# ------------------------------------------------------------------ queries
def latest_assessments(db: Session, package_ids: list[int], conclusive_only: bool) -> dict[int, Assessment]:
    if not package_ids:
        return {}
    q = select(Assessment.id, func.row_number().over(
        partition_by=Assessment.package_id,
        order_by=(Assessment.assessed_at.desc(), Assessment.id.desc())).label("rn")
    ).where(Assessment.package_id.in_(package_ids))
    if conclusive_only:
        q = q.where(Assessment.outcome.in_(CONCLUSIVE))
    sub = q.subquery()
    stmt = select(Assessment).join(sub, sub.c.id == Assessment.id).where(sub.c.rn == 1)
    return {a.package_id: a for a in db.scalars(stmt)}


def _obs_stats(db: Session, ids: list[int]) -> tuple[dict[int, int], dict[int, list[str]]]:
    if not ids:
        return {}, {}
    counts = dict(db.execute(select(Observation.package_id, func.count()).where(
        Observation.package_id.in_(ids)).group_by(Observation.package_id)).all())
    models: dict[int, list[str]] = {}
    for pid, m in db.execute(select(Observation.package_id, Observation.model).where(
            Observation.package_id.in_(ids)).distinct()).all():
        models.setdefault(pid, []).append(m)
    return counts, {k: sorted(v) for k, v in models.items()}


def _result(pkg: Package, concl: Optional[Assessment], anyx: Optional[Assessment],
            count: int, models: list[str], st: Settings, now: datetime) -> LookupResult:
    assessed = _aware(concl.assessed_at) if concl else None
    if pkg.status == "confirmed_malicious":
        verdict = "confirmed_malicious"
    elif pkg.status in ("allowlisted", "false_positive"):
        verdict = "allowlisted"
    else:
        verdict = concl.verdict if concl else "not_assessed"
    failed = bool(anyx and anyx.outcome == "verification_failed"
                  and (concl is None or _aware(anyx.assessed_at) > _aware(concl.assessed_at)))
    return LookupResult(
        ecosystem=pkg.ecosystem, name=pkg.name, found=True, verdict=verdict,
        risk_score=concl.risk_score if concl else None, status=pkg.status, status_note=pkg.status_note,
        stale=bool(assessed and now - assessed > timedelta(days=st.stale_days)),
        assessed_at=_iso(assessed) if assessed else None, latest_attempt_failed=failed,
        first_seen_unresolved=pkg.first_seen_unresolved,
        signals=[SignalIO(**s) for s in (concl.signals if concl else [])],
        notes=list(concl.notes) if concl else [], observation_count=count, models=models)


def _results_for(db: Session, pkgs: list[Package], st: Settings, now: datetime) -> list[LookupResult]:
    ids = [p.id for p in pkgs]
    concl, anyx = latest_assessments(db, ids, True), latest_assessments(db, ids, False)
    counts, models = _obs_stats(db, ids)
    return [_result(p, concl.get(p.id), anyx.get(p.id), counts.get(p.id, 0), models.get(p.id, []), st, now)
            for p in pkgs]


# ------------------------------------------------------------------ ingest
def _get_or_create(db: Session, eco: str, name: str, now: datetime) -> tuple[Package, bool]:
    find = select(Package).where(Package.ecosystem == eco, Package.name == name)
    pkg = db.scalar(find)
    if pkg:
        return pkg, False
    try:
        with db.begin_nested():                     # savepoint: a concurrent insert must not kill the batch
            pkg = Package(ecosystem=eco, name=name, first_seen_at=now, last_seen_at=now)
            db.add(pkg)
            db.flush()
        return pkg, True
    except IntegrityError:
        return db.scalar(find), False


def ingest(db: Session, req: IngestRequest, now: Optional[datetime] = None) -> IngestResult:
    now = now or utcnow()
    run_id = req.meta.run_id or uuid.uuid4().hex
    batch_time = _parse(req.meta.generated_at, now)
    created = updated = obs_added = ass_added = 0
    rejected: list[Rejected] = []

    for f in req.findings:
        if f.outcome == "malformed":
            rejected.append(Rejected(name=f.name, reason="malformed_outcome: not a registry package"))
            continue
        name = normalize(f.ecosystem, f.name)
        if name is None:
            rejected.append(Rejected(name=f.name, reason="invalid_name"))
            continue
        pkg, is_new = _get_or_create(db, f.ecosystem, name, now)
        created, updated = created + is_new, updated + (not is_new)
        pkg.last_seen_at = now

        assessed_at = _parse(f.registry.get("checked_at"), batch_time)
        if f.first_seen_unresolved:
            if pkg.first_seen_unresolved is None or f.first_seen_unresolved < pkg.first_seen_unresolved:
                pkg.first_seen_unresolved = f.first_seen_unresolved
        elif f.outcome == "unresolved" and pkg.first_seen_unresolved is None:
            pkg.first_seen_unresolved = _iso(assessed_at)

        have = set(db.scalars(select(Observation.obs_key).where(Observation.package_id == pkg.id)))
        for o in f.observations:
            k = obs_key(o.model, o.prompt_id, o.timestamp, o.command)
            if k in have:
                continue
            have.add(k)
            db.add(Observation(package_id=pkg.id, obs_key=k, run_id=run_id, model=o.model[:128],
                               prompt_id=o.prompt_id[:256], observed_at=o.timestamp[:40],
                               command=o.command, spec=o.spec[:256]))
            obs_added += 1

        if not db.scalar(select(Assessment.id).where(Assessment.package_id == pkg.id, Assessment.run_id == run_id)):
            db.add(Assessment(package_id=pkg.id, run_id=run_id, outcome=f.outcome, verdict=f.verdict,
                              risk_score=f.risk_score, signals=[s.model_dump() for s in f.signals],
                              notes=f.notes, registry_data=f.registry, assessed_at=assessed_at))
            ass_added += 1
        db.flush()
    db.commit()
    return IngestResult(run_id=run_id, packages_created=created, packages_updated=updated,
                        observations_added=obs_added, assessments_added=ass_added, rejected=rejected)


# ------------------------------------------------------------------ lookup / read
def lookup(db: Session, refs: list[PackageRef], st: Settings, now: Optional[datetime] = None) -> list[LookupResult]:
    now = now or utcnow()
    wanted: list[tuple[PackageRef, Optional[str]]] = [(r, normalize(r.ecosystem, r.name)) for r in refs]
    keys = {(r.ecosystem, n) for r, n in wanted if n}
    pkgs: dict[tuple[str, str], Package] = {}
    for eco in {e for e, _ in keys}:
        names = [n for e, n in keys if e == eco]
        for p in db.scalars(select(Package).where(Package.ecosystem == eco, Package.name.in_(names))):
            pkgs[(p.ecosystem, p.name)] = p
    built = {(r.ecosystem, r.name): r for r in _results_for(db, list(pkgs.values()), st, now)}
    out: list[LookupResult] = []
    for ref, norm in wanted:
        if norm is None:
            out.append(LookupResult(ecosystem=ref.ecosystem, name=ref.name, found=False, verdict="not_assessed",
                                    notes=["Invalid package name for this ecosystem."]))
        elif (ref.ecosystem, norm) in built:
            out.append(built[(ref.ecosystem, norm)])
        else:
            out.append(LookupResult(ecosystem=ref.ecosystem, name=norm, found=False, verdict="not_assessed",
                                    notes=["Iris has no record of this package. This is NOT a safety signal."]))
    return out


def package_detail(db: Session, eco: str, raw_name: str, st: Settings, now: Optional[datetime] = None) -> PackageDetail:
    now = now or utcnow()
    name = normalize(eco, raw_name)
    pkg = db.scalar(select(Package).where(Package.ecosystem == eco, Package.name == name)) if name else None
    if pkg is None:
        raise ApiError(404, "not_found", "No such package in Iris.")
    summary = _results_for(db, [pkg], st, now)[0]
    obs = db.scalars(select(Observation).where(Observation.package_id == pkg.id)
                     .order_by(Observation.id.desc()).limit(50)).all()
    hist = db.scalars(select(Assessment).where(Assessment.package_id == pkg.id)
                      .order_by(Assessment.assessed_at.desc(), Assessment.id.desc()).limit(20)).all()
    rev = db.scalars(select(ReviewEvent).where(ReviewEvent.package_id == pkg.id)
                     .order_by(ReviewEvent.id.desc()).limit(50)).all()
    return PackageDetail(
        summary=summary,
        observations=[dict(model=o.model, prompt_id=o.prompt_id, observed_at=o.observed_at, command=o.command,
                           spec=o.spec, run_id=o.run_id) for o in obs],
        assessment_history=[dict(run_id=a.run_id, outcome=a.outcome, verdict=a.verdict, risk_score=a.risk_score,
                                 assessed_at=_iso(a.assessed_at), signals=a.signals) for a in hist],
        review_history=[dict(actor=r.actor, old_status=r.old_status, new_status=r.new_status, note=r.note,
                             at=_iso(r.created_at)) for r in rev])


def list_packages(db: Session, st: Settings, eco: Optional[str], verdict: Optional[str],
                  status: Optional[str], limit: int, offset: int, now: Optional[datetime] = None) -> PackageList:
    now = now or utcnow()
    rn = select(Assessment.id.label("aid"), func.row_number().over(
        partition_by=Assessment.package_id,
        order_by=(Assessment.assessed_at.desc(), Assessment.id.desc())).label("rn")
    ).where(Assessment.outcome.in_(CONCLUSIVE)).subquery()
    latest = select(Assessment.package_id.label("pid"), Assessment.verdict.label("v")
                    ).join(rn, rn.c.aid == Assessment.id).where(rn.c.rn == 1).subquery()
    base = select(Package).outerjoin(latest, latest.c.pid == Package.id)
    if eco:
        base = base.where(Package.ecosystem == eco)
    if status:
        base = base.where(Package.status == status)
    if verdict == "not_assessed":
        base = base.where(latest.c.v.is_(None))
    elif verdict:
        base = base.where(latest.c.v == verdict)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    pkgs = db.scalars(base.order_by(Package.last_seen_at.desc(), Package.id.desc()).limit(limit).offset(offset)).all()
    return PackageList(total=total, limit=limit, offset=offset, items=_results_for(db, list(pkgs), st, now))


def stats(db: Session) -> dict:
    rn = select(Assessment.id.label("aid"), func.row_number().over(
        partition_by=Assessment.package_id,
        order_by=(Assessment.assessed_at.desc(), Assessment.id.desc())).label("rn")
    ).where(Assessment.outcome.in_(CONCLUSIVE)).subquery()
    latest = select(Assessment.package_id.label("pid"), Assessment.verdict.label("v")
                    ).join(rn, rn.c.aid == Assessment.id).where(rn.c.rn == 1).subquery()
    by_verdict = {(v or "not_assessed"): c for v, c in db.execute(
        select(latest.c.v, func.count()).select_from(Package).outerjoin(latest, latest.c.pid == Package.id)
        .group_by(latest.c.v)).all()}
    by_status = dict(db.execute(select(Package.status, func.count()).group_by(Package.status)).all())
    last = db.scalar(select(func.max(Assessment.created_at)))
    return {"packages": db.scalar(select(func.count(Package.id))) or 0,
            "observations": db.scalar(select(func.count(Observation.id))) or 0,
            "assessments": db.scalar(select(func.count(Assessment.id))) or 0,
            "by_verdict": by_verdict, "by_status": by_status,
            "last_ingest_at": _iso(last) if last else None}


# ------------------------------------------------------------------ review (analyst)
def review(db: Session, req: ReviewRequest, actor: str, now: Optional[datetime] = None) -> ReviewEvent | None:
    now = now or utcnow()
    name = normalize(req.ecosystem, req.name)
    if name is None:
        raise ApiError(422, "invalid_name", "Invalid package name for this ecosystem.")
    pkg, _ = _get_or_create(db, req.ecosystem, name, now)
    changed = pkg.status != req.status or (req.note and req.note != pkg.status_note)
    event = None
    if changed:
        event = ReviewEvent(package_id=pkg.id, actor=actor, old_status=pkg.status,
                            new_status=req.status, note=req.note, created_at=now)
        db.add(event)
        pkg.status, pkg.status_note = req.status, req.note
    db.commit()
    return event
