"""Name normalization. Deliberately mirrors iris_scout.normalize: the API must not trust
clients (Guardian sends raw names), and a contract test keeps the two implementations in sync."""
from __future__ import annotations

import re
from typing import Optional

_PYPI_VALID = re.compile(r"^([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9])$")
_NPM_VALID = re.compile(r"^(@[A-Za-z0-9~-][A-Za-z0-9._~-]*/)?[A-Za-z0-9~-][A-Za-z0-9._~-]*$")


def normalize(ecosystem: str, raw: str) -> Optional[str]:
    raw = (raw or "").strip()
    if not raw:
        return None
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", raw).lower() if _PYPI_VALID.match(raw) else None
    if ecosystem == "npm":
        return raw.lower() if len(raw) <= 214 and _NPM_VALID.match(raw) else None
    return None
