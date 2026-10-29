"""Registry verification for PyPI and npm.

Outcome mapping (this is the heart of the "404 is a signal, not a verdict" rule):
  200            -> VERIFIED
  404            -> UNRESOLVED          (note: deleted/yanked-whole packages also 404)
  429 / 5xx / network error / timeout (after retries) -> VERIFICATION_FAILED
  other 4xx / bad JSON                                 -> VERIFICATION_FAILED
Errors are NEVER reported as hallucinations.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from . import __version__
from .models import Ecosystem, Outcome, RegistryRecord
from .normalize import npm_url_name

USER_AGENT = f"iris-scout/{__version__} (defensive supply-chain research)"
_REPO_RE = re.compile(r"(github\.com|gitlab\.com|bitbucket\.org|codeberg\.org|sr\.ht)", re.I)


@dataclass
class FetchResult:
    status: Optional[int]            # None = no HTTP response (network error)
    body: Optional[bytes] = None
    error: str = ""
    retry_after: Optional[float] = None


class Fetcher(Protocol):
    def __call__(self, url: str, headers: dict[str, str]) -> FetchResult: ...


def urllib_fetcher(url: str, headers: dict[str, str], timeout: float = 15.0) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return FetchResult(r.status, r.read())
    except urllib.error.HTTPError as e:
        ra = e.headers.get("Retry-After") if e.headers else None
        try:
            ra_f = float(ra) if ra else None
        except ValueError:
            ra_f = None
        return FetchResult(e.code, None, f"HTTP {e.code}", ra_f)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return FetchResult(None, None, f"{type(e).__name__}: {e}")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_ts(s: str) -> datetime:
    """Parse ISO 8601 with or without trailing Z / fractional seconds, as UTC."""
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class RegistryClient:
    def __init__(
        self,
        fetcher: Fetcher = urllib_fetcher,
        max_retries: int = 3,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._fetch, self._retries, self._backoff = fetcher, max_retries, backoff
        self._sleep, self._now = sleep, now
        self._cache: dict[tuple[str, str], RegistryRecord] = {}

    # ------------------------------------------------------------------ public
    def verify(self, eco: Ecosystem, name: str) -> RegistryRecord:
        key = (eco.value, name)
        if key not in self._cache:
            self._cache[key] = self._verify(eco, name)
        return self._cache[key]

    # ---------------------------------------------------------------- internals
    def _url(self, eco: Ecosystem, name: str) -> str:
        if eco is Ecosystem.PYPI:
            return f"https://pypi.org/pypi/{name}/json"
        return f"https://registry.npmjs.org/{npm_url_name(name)}"

    def _get_with_retries(self, url: str) -> FetchResult:
        res = FetchResult(None, None, "not attempted")
        for attempt in range(self._retries + 1):
            res = self._fetch(url, {"Accept": "application/json"})
            retryable = res.status is None or res.status == 429 or res.status >= 500
            if not retryable or attempt == self._retries:
                return res
            delay = res.retry_after if res.retry_after else self._backoff * (2 ** attempt)
            self._sleep(min(delay, 30.0))
        return res

    def _verify(self, eco: Ecosystem, name: str) -> RegistryRecord:
        rec = RegistryRecord(eco, name, Outcome.VERIFICATION_FAILED, checked_at=_iso(self._now()))
        res = self._get_with_retries(self._url(eco, name))
        rec.http_status = res.status
        if res.status == 404:
            rec.outcome = Outcome.UNRESOLVED
            return rec
        if res.status != 200 or res.body is None:
            rec.error = res.error or f"unexpected status {res.status}"
            return rec
        try:
            doc = json.loads(res.body)
        except (ValueError, UnicodeDecodeError) as e:
            rec.error = f"invalid JSON: {e}"
            return rec
        try:
            (self._fill_pypi if eco is Ecosystem.PYPI else self._fill_npm)(rec, doc)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            rec.error = f"unexpected registry document shape: {e}"
            return rec
        rec.outcome = Outcome.VERIFIED
        return rec

    @staticmethod
    def _fill_pypi(rec: RegistryRecord, doc: dict) -> None:
        info = doc.get("info") or {}
        times: list[str] = []
        versions_with_files = 0
        for files in (doc.get("releases") or {}).values():
            if files:
                versions_with_files += 1
                times += [f["upload_time_iso_8601"] for f in files if f.get("upload_time_iso_8601")]
        if not times:   # fall back to files of the latest release
            times = [f["upload_time_iso_8601"] for f in doc.get("urls") or [] if f.get("upload_time_iso_8601")]
            versions_with_files = versions_with_files or (1 if times else 0)
        if times:
            ts = sorted(parse_ts(t) for t in times)
            rec.first_release, rec.last_release = _iso(ts[0]), _iso(ts[-1])
        rec.release_count = versions_with_files
        # Many well-known projects leave `author` blank and only fill the *_email fields.
        people = [info.get("author"), info.get("maintainer"),
                  info.get("author_email"), info.get("maintainer_email")]
        rec.maintainers = sorted({p.strip() for p in people if p and p.strip()})
        urls = list((info.get("project_urls") or {}).values()) + [info.get("home_page") or ""]
        repo = next((u for u in urls if u and _REPO_RE.search(u)), None)
        rec.repo_url, rec.has_source_repo = repo, bool(repo)
        rec.summary = (info.get("summary") or "")[:200]

    @staticmethod
    def _fill_npm(rec: RegistryRecord, doc: dict) -> None:
        time_map = doc.get("time") or {}
        versions = doc.get("versions") or {}
        if time_map.get("created"):
            rec.first_release = _iso(parse_ts(time_map["created"]))
        latest = (doc.get("dist-tags") or {}).get("latest")
        if latest and time_map.get(latest):
            rec.last_release = _iso(parse_ts(time_map[latest]))
        rec.release_count = len(versions)
        rec.maintainers = [m.get("name") for m in doc.get("maintainers") or [] if m.get("name")]
        repo = doc.get("repository")
        url = repo.get("url") if isinstance(repo, dict) else repo
        rec.repo_url, rec.has_source_repo = url, bool(url)
        rec.summary = (doc.get("description") or "")[:200]
        scripts = (versions.get(latest) or {}).get("scripts") or {} if latest else {}
        rec.install_hooks = any(k in scripts for k in ("preinstall", "install", "postinstall"))
