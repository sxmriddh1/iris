import pytest
from fastapi.testclient import TestClient

from iris_api.config import Settings
from iris_api.main import create_app

READ, INGEST, ADMIN = {"X-API-Key": "rk"}, {"X-API-Key": "ik"}, {"X-API-Key": "ak"}


def make_client(**kw):
    s = Settings(database_url="sqlite://", read_keys=("rk",), ingest_keys=("ik",), admin_keys=("ak",), **kw)
    return TestClient(create_app(s), raise_server_exceptions=False)


@pytest.fixture
def client():
    return make_client()


def finding(name="foo", eco="pypi", outcome="unresolved", verdict="unresolved", score=None, signals=None,
            checked_at="2026-10-28T00:00:00Z", first_unres=None, obs=None, **registry):
    return {"ecosystem": eco, "name": name, "outcome": outcome, "verdict": verdict, "risk_score": score,
            "signals": signals or [],
            "observations": obs if obs is not None else [
                {"model": "m1", "prompt_id": "p1", "timestamp": "2026-10-28T00:00:00Z",
                 "command": f"pip install {name}", "spec": ""}],
            "registry": {"checked_at": checked_at, **registry}, "first_seen_unresolved": first_unres, "notes": []}


def payload(findings, run_id="run-1", generated_at="2026-10-28T00:00:00Z"):
    return {"meta": {"run_id": run_id, "generated_at": generated_at}, "findings": findings}


def lookup(client, *refs, headers=READ):
    r = client.post("/v1/lookup", json={"packages": [{"ecosystem": e, "name": n} for e, n in refs]}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["results"]


HIGH = dict(outcome="verified", verdict="high_risk", score=75,
            signals=[{"name": "registered_after_unresolved", "points": 40, "detail": "d"}])
