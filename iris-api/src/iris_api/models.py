"""Relational schema.

packages      one row per (ecosystem, normalized name); holds the analyst status
observations  every time a model recommended the package (provenance); idempotent via obs_key
assessments   one row per Scout run per package: the history of what the registry said and how we scored it
review_events append-only audit log of analyst status changes
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Package(Base):
    __tablename__ = "packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    ecosystem: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(24), default="unreviewed")
    status_note: Mapped[str] = mapped_column(Text, default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    first_seen_unresolved: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    __table_args__ = (UniqueConstraint("ecosystem", "name", name="uq_package"),)


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), index=True)
    obs_key: Mapped[str] = mapped_column(String(64))        # sha256(model|prompt|time|command)
    run_id: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_id: Mapped[str] = mapped_column(String(256))
    observed_at: Mapped[str] = mapped_column(String(40))
    command: Mapped[str] = mapped_column(Text, default="")
    spec: Mapped[str] = mapped_column(String(256), default="")
    __table_args__ = (UniqueConstraint("package_id", "obs_key", name="uq_observation"),)


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(24))
    verdict: Mapped[str] = mapped_column(String(24))
    risk_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[list] = mapped_column(JSON, default=list)
    registry_data: Mapped[dict] = mapped_column("registry_json", JSON, default=dict)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))   # when the registry was checked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("package_id", "run_id", name="uq_assessment_run"),
                      Index("ix_assessment_latest", "package_id", "assessed_at"))


class ReviewEvent(Base):
    __tablename__ = "review_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(16))          # first 8 hex of sha256(api key); never the key
    old_status: Mapped[str] = mapped_column(String(24))
    new_status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
