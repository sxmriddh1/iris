"""Popular-name lists and edit distance for typosquat / "did you mean" signals.

The bundled lists are SMALL starter sets. For real evaluation, replace them with a
current top-N download list (e.g. the public top PyPI packages dataset).
"""
from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Optional

from .models import Ecosystem


def edit_distance(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein distance, early-exit once it exceeds cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


@lru_cache(maxsize=None)
def load_popular(eco: Ecosystem) -> frozenset[str]:
    fn = "popular_pypi.txt" if eco is Ecosystem.PYPI else "popular_npm.txt"
    text = resources.files("iris_scout.data").joinpath(fn).read_text()
    return frozenset(l.strip().lower() for l in text.splitlines() if l.strip() and not l.startswith("#"))


def closest_popular(eco: Ecosystem, name: str, max_dist: int = 2, min_len: int = 5) -> Optional[tuple[str, int]]:
    """Nearest popular name within max_dist, excluding the name itself.
    Short names are skipped: with len < min_len almost everything is 'close'."""
    popular = load_popular(eco)
    if name in popular or len(name) < min_len:
        return None
    best: Optional[tuple[str, int]] = None
    for p in popular:
        d = edit_distance(name, p, max_dist)
        if d <= max_dist and (best is None or d < best[1]):
            best = (p, d)
    return best
