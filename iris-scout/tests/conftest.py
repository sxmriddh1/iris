import json
from datetime import datetime, timezone

from iris_scout.registry import FetchResult


class FakeFetcher:
    """Scripted registry. `routes` maps URL -> FetchResult or list of FetchResults (consumed in order)."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, headers):
        self.calls.append(url)
        r = self.routes.get(url, FetchResult(404, None, "HTTP 404"))
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        return r


def pypi_doc(first="2020-01-01T00:00:00Z", versions=5, repo="https://github.com/a/b", author="Ann"):
    rel = {f"1.{i}": [{"upload_time_iso_8601": first if i == 0 else "2024-01-01T00:00:00.000000Z"}] for i in range(versions)}
    return json.dumps({"info": {"name": "x", "author": author, "maintainer": None, "summary": "s",
                                "project_urls": {"Source": repo} if repo else {}, "home_page": ""},
                       "releases": rel, "urls": []}).encode()


def npm_doc(created="2019-01-01T00:00:00.000Z", versions=3, repo="git+https://github.com/a/b.git", hooks=False):
    vs = {f"1.{i}.0": {"scripts": {"postinstall": "node x.js"} if (hooks and i == versions - 1) else {}} for i in range(versions)}
    t = {"created": created, "modified": "2024-01-01T00:00:00.000Z", f"1.{versions-1}.0": "2024-01-01T00:00:00.000Z"}
    return json.dumps({"name": "x", "description": "d", "dist-tags": {"latest": f"1.{versions-1}.0"},
                       "versions": vs, "time": t, "maintainers": [{"name": "ann"}],
                       "repository": {"url": repo} if repo else None}).encode()


NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)
