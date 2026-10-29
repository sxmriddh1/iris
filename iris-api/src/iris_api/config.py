"""Settings from environment variables. Fail closed: no API keys configured = refuse to start."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _keys(var: str) -> tuple[str, ...]:
    return tuple(k.strip() for k in os.environ.get(var, "").split(",") if k.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./iris.db"
    read_keys: tuple[str, ...] = ()       # may query
    ingest_keys: tuple[str, ...] = ()     # may query + submit findings (Scout)
    admin_keys: tuple[str, ...] = ()      # may also change review status (analysts)
    stale_days: int = 7                   # an assessment older than this is flagged stale
    rate_limit_per_min: int = 120         # per API key, in-memory (single process)
    allow_no_auth: bool = False           # dev only

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///./iris.db"),
            read_keys=_keys("IRIS_READ_KEYS"), ingest_keys=_keys("IRIS_INGEST_KEYS"),
            admin_keys=_keys("IRIS_ADMIN_KEYS"),
            stale_days=int(os.environ.get("IRIS_STALE_DAYS", "7")),
            rate_limit_per_min=int(os.environ.get("IRIS_RATE_LIMIT_PER_MIN", "120")),
            allow_no_auth=os.environ.get("IRIS_ALLOW_NO_AUTH") == "1",
        )

    def validate(self) -> None:
        if not (self.read_keys or self.ingest_keys or self.admin_keys):
            raise RuntimeError("No API keys configured. Set IRIS_READ_KEYS / IRIS_INGEST_KEYS / IRIS_ADMIN_KEYS.")
