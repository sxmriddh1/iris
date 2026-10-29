"""Contract tests: real iris-scout output must be accepted by this API, and name rules must agree."""
import pytest

pytest.importorskip("iris_scout")
from conftest import INGEST, READ, lookup  # noqa: E402
from iris_api.names import normalize as api_normalize  # noqa: E402
from iris_scout.export import build_payload  # noqa: E402
from iris_scout.ledger import Ledger  # noqa: E402
from iris_scout.models import Ecosystem, LLMResponse  # noqa: E402
from iris_scout.normalize import normalize as scout_normalize  # noqa: E402
from iris_scout.pipeline import analyze  # noqa: E402
from iris_scout.registry import FetchResult, RegistryClient  # noqa: E402

TRICKY = ["Requests", "my_pkg.name", "A--B", "", "-bad", "bad-", "has space", "a/b", "@Types/Node",
          "@/bad", "x" * 215, "UPPER_case.Mixed", "a", "@scope/name", "foo@1.0"]


@pytest.mark.parametrize("raw", TRICKY)
@pytest.mark.parametrize("eco", ["pypi", "npm"])
def test_name_normalization_matches_scout(eco, raw):
    assert api_normalize(eco, raw) == scout_normalize(Ecosystem(eco), raw)


def _fetcher(url, headers):
    import json
    if "requests" in url:
        doc = {"info": {"author": "K", "project_urls": {"Source": "https://github.com/psf/requests"}},
               "releases": {"1.0": [{"upload_time_iso_8601": "2012-01-01T00:00:00Z"}], "2.0": [{"upload_time_iso_8601": "2020-01-01T00:00:00Z"}]}}
        return FetchResult(200, json.dumps(doc).encode())
    return FetchResult(404, None, "HTTP 404")


def test_real_scout_output_round_trips_through_the_api(client):
    text = "pip install requests secure-token-validator\npip install git+https://github.com/x/y.git\nnpm i @Types/Node"
    resp = LLMResponse("p1", "q", "model-a", "2026-10-28T00:00:00Z", text)
    findings = analyze([resp], RegistryClient(_fetcher, sleep=lambda s: None), Ledger())
    payload = build_payload(findings, "test")

    r = client.post("/v1/findings", json=payload, headers=INGEST)
    assert r.status_code == 200, r.text
    res = r.json()
    assert len(res["rejected"]) == 1 and "malformed_outcome" in res["rejected"][0]["reason"]   # the git+ URL
    assert res["packages_created"] == len(findings) - 1

    got = {x["name"]: x for x in lookup(client, ("pypi", "requests"), ("pypi", "secure-token-validator"))}
    assert got["requests"]["verdict"] == "low_risk" and got["requests"]["models"] == ["model-a"]
    assert got["secure-token-validator"]["verdict"] == "unresolved"
    assert got["secure-token-validator"]["first_seen_unresolved"]            # ledger value crossed the boundary
    assert client.post("/v1/findings", json=payload, headers=INGEST).json()["assessments_added"] == 0   # idempotent
