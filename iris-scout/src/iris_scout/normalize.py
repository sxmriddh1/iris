"""Name normalization and validation per ecosystem."""
from __future__ import annotations

import re
from typing import Optional

from .models import Ecosystem

_PYPI_VALID = re.compile(r"^([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9])$")
_NPM_VALID = re.compile(r"^(@[A-Za-z0-9~-][A-Za-z0-9._~-]*/)?[A-Za-z0-9~-][A-Za-z0-9._~-]*$")


def normalize_pypi(name: str) -> str:
    """PEP 503: lowercase, runs of - _ . collapse to a single -."""
    return re.sub(r"[-_.]+", "-", name).lower()


def normalize(ecosystem: Ecosystem, raw: str) -> Optional[str]:
    """Return the canonical name, or None if it cannot be a valid package name."""
    raw = raw.strip()
    if not raw:
        return None
    if ecosystem is Ecosystem.PYPI:
        if not _PYPI_VALID.match(raw):
            return None
        return normalize_pypi(raw)
    if len(raw) > 214 or not _NPM_VALID.match(raw):
        return None
    return raw.lower()


def npm_url_name(name: str) -> str:
    """Scoped names need the slash percent-encoded in registry URLs."""
    return name.replace("/", "%2F")
