"""Tiny SQLite ledger: remembers when a name was FIRST seen unresolved.

This is what makes the strongest signal possible: "registered AFTER we first saw the
name as unresolved". Phase 2 replaces this with the PostgreSQL service; the interface
(record / first_unresolved) is what the scorer depends on.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from .models import Outcome


class Ledger:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS seen (
                 ecosystem TEXT NOT NULL, name TEXT NOT NULL,
                 first_unresolved_at TEXT, last_unresolved_at TEXT,
                 times_unresolved INTEGER NOT NULL DEFAULT 0,
                 first_verified_at TEXT,
                 PRIMARY KEY (ecosystem, name))"""
        )
        self.db.commit()

    def record(self, ecosystem: str, name: str, outcome: Outcome, when: str) -> None:
        if outcome not in (Outcome.UNRESOLVED, Outcome.VERIFIED):
            return                      # failures and malformed names tell us nothing
        self.db.execute("INSERT OR IGNORE INTO seen (ecosystem, name) VALUES (?, ?)", (ecosystem, name))
        if outcome is Outcome.UNRESOLVED:
            self.db.execute(
                """UPDATE seen SET first_unresolved_at = COALESCE(first_unresolved_at, ?),
                   last_unresolved_at = ?, times_unresolved = times_unresolved + 1
                   WHERE ecosystem = ? AND name = ?""", (when, when, ecosystem, name))
        else:
            self.db.execute(
                """UPDATE seen SET first_verified_at = COALESCE(first_verified_at, ?)
                   WHERE ecosystem = ? AND name = ?""", (when, ecosystem, name))
        self.db.commit()

    def first_unresolved(self, ecosystem: str, name: str) -> Optional[str]:
        row = self.db.execute(
            "SELECT first_unresolved_at FROM seen WHERE ecosystem = ? AND name = ?", (ecosystem, name)
        ).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self.db.close()
