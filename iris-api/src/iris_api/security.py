"""API-key authentication with three roles, plus a per-key sliding-window rate limit.

Roles: READ (query) < INGEST (submit findings: Scout) < ADMIN (change review status: analysts).
Keys are compared in constant time. Only a short hash of the key (key_id) is ever logged/stored.
Limitations (Phase 2): keys live in env vars (no rotation UI); the rate limiter is in-process,
so behind multiple workers use a gateway or Redis instead.
"""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from fastapi import Header, Request

from .config import Settings
from .errors import ApiError


class Role(IntEnum):
    READ = 1
    INGEST = 2
    ADMIN = 3


@dataclass(frozen=True)
class Principal:
    key_id: str
    role: Role


def key_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:8]


class Authenticator:
    def __init__(self, s: Settings):
        self._keys = [(k, Role.READ) for k in s.read_keys] + [(k, Role.INGEST) for k in s.ingest_keys] \
                     + [(k, Role.ADMIN) for k in s.admin_keys]

    def authenticate(self, raw: str) -> Optional[Principal]:
        best: Optional[Role] = None
        for key, role in self._keys:                 # no early exit: constant-ish time
            if hmac.compare_digest(raw.encode(), key.encode()):
                best = role if best is None else max(best, role)
        return Principal(key_id(raw), best) if best else None


class RateLimiter:
    def __init__(self, per_minute: int):
        self.limit, self._hits, self._lock = per_minute, defaultdict(deque), threading.Lock()

    def check(self, kid: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[kid]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.limit:
                retry = max(1, int(60 - (now - q[0])) + 1)
                raise ApiError(429, "rate_limited", f"Rate limit of {self.limit}/min exceeded.",
                               headers={"Retry-After": str(retry)})
            q.append(now)


def require(minimum: Role):
    """FastAPI dependency factory: authenticate, enforce role, then rate-limit."""
    def dep(request: Request, x_api_key: Optional[str] = Header(None)) -> Principal:
        st = request.app.state
        if st.settings.allow_no_auth:
            return Principal("dev", Role.ADMIN)
        if not x_api_key:
            raise ApiError(401, "unauthenticated", "Missing X-API-Key header.")
        who = st.auth.authenticate(x_api_key)
        if who is None:
            raise ApiError(401, "invalid_api_key", "Invalid API key.")
        if who.role < minimum:
            raise ApiError(403, "forbidden", f"This operation requires the {minimum.name.lower()} role.")
        st.limiter.check(who.key_id)
        return who
    return dep
