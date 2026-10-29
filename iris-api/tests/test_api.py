from datetime import datetime, timedelta, timezone

from conftest import ADMIN, HIGH, INGEST, READ, finding, lookup, make_client, payload
from iris_api.config import Settings
from iris_api.main import create_app
import pytest


# ---------------------------------------------------------------- ops, auth, errors
def test_health_needs_no_auth(client):
    assert client.get("/healthz").json()["status"] == "ok"

def test_fails_closed_without_keys():
    with pytest.raises(RuntimeError):
        create_app(Settings(database_url="sqlite://"))

def test_missing_and_bad_key_are_401(client):
    assert client.post("/v1/lookup", json={"packages": [{"ecosystem": "pypi", "name": "x"}]}).status_code == 401
    r = client.get("/v1/stats", headers={"X-API-Key": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"

def test_role_enforcement(client):
    assert client.post("/v1/findings", json=payload([finding()]), headers=READ).status_code == 403
    assert client.post("/v1/findings", json=payload([finding()]), headers=INGEST).status_code == 200
    review = {"ecosystem": "pypi", "name": "foo", "status": "allowlisted"}
    assert client.put("/v1/review", json=review, headers=INGEST).status_code == 403
    assert client.put("/v1/review", json=review, headers=ADMIN).status_code == 200

def test_validation_error_shape_and_request_id(client):
    r = client.post("/v1/findings", json={"findings": [{"name": "x"}]}, headers=INGEST)
    body = r.json()["error"]
    assert r.status_code == 422 and body["code"] == "validation_error" and body["details"] and body["request_id"]
    assert r.headers["X-Request-ID"] == body["request_id"]

def test_batch_limits(client):
    refs = [{"ecosystem": "pypi", "name": f"p{i}"} for i in range(201)]
    assert client.post("/v1/lookup", json={"packages": refs}, headers=READ).status_code == 422
    assert client.post("/v1/lookup", json={"packages": []}, headers=READ).status_code == 422

def test_rate_limit_returns_429_with_retry_after():
    c = make_client(rate_limit_per_min=3)
    for _ in range(3):
        assert c.get("/v1/stats", headers=READ).status_code == 200
    r = c.get("/v1/stats", headers=READ)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 and r.json()["error"]["code"] == "rate_limited"
    assert c.get("/v1/stats", headers=ADMIN).status_code == 200      # limits are per key

def test_unknown_route_uses_error_shape(client):
    assert client.get("/nope").json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------- ingestion
def test_ingest_is_idempotent(client):
    p = payload([finding("foo"), finding("bar", **HIGH)])
    a = client.post("/v1/findings", json=p, headers=INGEST).json()
    b = client.post("/v1/findings", json=p, headers=INGEST).json()
    assert (a["packages_created"], a["observations_added"], a["assessments_added"]) == (2, 2, 2)
    assert (b["packages_created"], b["packages_updated"], b["observations_added"], b["assessments_added"]) == (0, 2, 0, 0)
    s = client.get("/v1/stats", headers=READ).json()
    assert (s["packages"], s["observations"], s["assessments"]) == (2, 2, 2)

def test_names_are_normalized_on_ingest_and_lookup(client):
    client.post("/v1/findings", json=payload([finding("My_Lib")]), headers=INGEST)
    assert lookup(client, ("pypi", "MY.LIB"))[0]["found"] is True
    client.post("/v1/findings", json=payload([finding("@Types/Node", eco="npm")], run_id="r2"), headers=INGEST)
    d = client.get("/v1/package", params={"ecosystem": "npm", "name": "@types/NODE"}, headers=READ)
    assert d.status_code == 200 and d.json()["summary"]["name"] == "@types/node"

def test_malformed_and_invalid_names_are_rejected_not_stored(client):
    p = payload([finding("git+https://x/y.git", outcome="malformed", verdict="unknown"), finding("bad name!")])
    r = client.post("/v1/findings", json=p, headers=INGEST).json()
    assert {x["reason"].split(":")[0] for x in r["rejected"]} == {"malformed_outcome", "invalid_name"}
    assert client.get("/v1/stats", headers=READ).json()["packages"] == 0

def test_same_package_different_runs_accumulate_observations(client):
    o2 = [{"model": "m2", "prompt_id": "p9", "timestamp": "2026-10-29T00:00:00Z", "command": "pip install foo", "spec": ""}]
    client.post("/v1/findings", json=payload([finding("foo")], "r1"), headers=INGEST)
    client.post("/v1/findings", json=payload([finding("foo", obs=o2, checked_at="2026-10-29T00:00:00Z")], "r2"), headers=INGEST)
    r = lookup(client, ("pypi", "foo"))[0]
    assert r["observation_count"] == 2 and r["models"] == ["m1", "m2"]


# ---------------------------------------------------------------- the verdict rules
def test_unknown_package_is_not_assessed_never_low_risk(client):
    r = lookup(client, ("pypi", "never-heard-of-it"))[0]
    assert r["found"] is False and r["verdict"] == "not_assessed" and "NOT a safety signal" in r["notes"][0]
    assert lookup(client, ("pypi", "bad name!"))[0]["verdict"] == "not_assessed"

def test_history_latest_wins_and_first_seen_unresolved_is_preserved(client):
    client.post("/v1/findings", json=payload([finding("foo", first_unres="2026-10-28T00:00:00Z")], "r1"), headers=INGEST)
    h = finding("foo", checked_at="2026-11-04T00:00:00Z", first_unres="2026-10-28T00:00:00Z", **HIGH)
    client.post("/v1/findings", json=payload([h], "r2", "2026-11-04T00:00:00Z"), headers=INGEST)
    r = lookup(client, ("pypi", "foo"))[0]
    assert r["verdict"] == "high_risk" and r["risk_score"] == 75 and r["first_seen_unresolved"] == "2026-10-28T00:00:00Z"
    hist = client.get("/v1/package", params={"ecosystem": "pypi", "name": "foo"}, headers=READ).json()["assessment_history"]
    assert [a["verdict"] for a in hist] == ["high_risk", "unresolved"]

def test_outage_never_downgrades_a_known_verdict(client):
    client.post("/v1/findings", json=payload([finding("foo", checked_at="2026-11-04T00:00:00Z", **HIGH)], "r1"), headers=INGEST)
    out = finding("foo", outcome="verification_failed", verdict="unknown", checked_at="2026-11-05T00:00:00Z")
    client.post("/v1/findings", json=payload([out], "r2"), headers=INGEST)
    r = lookup(client, ("pypi", "foo"))[0]
    assert r["verdict"] == "high_risk" and r["latest_attempt_failed"] is True

def test_old_run_ingested_late_cannot_override_newer_knowledge(client):
    client.post("/v1/findings", json=payload([finding("foo", checked_at="2026-11-04T00:00:00Z", **HIGH)], "new"), headers=INGEST)
    client.post("/v1/findings", json=payload([finding("foo", checked_at="2026-10-01T00:00:00Z")], "old"), headers=INGEST)
    assert lookup(client, ("pypi", "foo"))[0]["verdict"] == "high_risk"

def test_stale_flag(client):
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    fresh = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    client.post("/v1/findings", json=payload([finding("old", checked_at=old), finding("new", checked_at=fresh)]), headers=INGEST)
    r = {x["name"]: x for x in lookup(client, ("pypi", "old"), ("pypi", "new"))}
    assert r["old"]["stale"] is True and r["new"]["stale"] is False

def test_first_unresolved_falls_back_to_assessment_time(client):
    client.post("/v1/findings", json=payload([finding("foo", checked_at="2026-10-20T00:00:00Z")]), headers=INGEST)
    assert lookup(client, ("pypi", "foo"))[0]["first_seen_unresolved"] == "2026-10-20T00:00:00Z"


# ---------------------------------------------------------------- analyst review
def test_review_overrides_verdict_and_is_audited(client):
    client.post("/v1/findings", json=payload([finding("foo", **HIGH)]), headers=INGEST)
    assert client.put("/v1/review", json={"ecosystem": "pypi", "name": "foo", "status": "allowlisted",
                                          "note": "internal fork"}, headers=ADMIN).json()["verdict"] == "allowlisted"
    r = client.put("/v1/review", json={"ecosystem": "pypi", "name": "foo", "status": "confirmed_malicious",
                                       "note": "exfil in setup.py"}, headers=ADMIN).json()
    assert r["verdict"] == "confirmed_malicious" and r["risk_score"] == 75
    ev = client.get("/v1/package", params={"ecosystem": "pypi", "name": "foo"}, headers=READ).json()["review_history"]
    assert [(e["old_status"], e["new_status"]) for e in ev] == [("allowlisted", "confirmed_malicious"), ("unreviewed", "allowlisted")]
    assert "ak" not in str(ev) and len(ev[0]["actor"]) == 8

def test_review_can_flag_a_package_scout_never_saw(client):
    r = client.put("/v1/review", json={"ecosystem": "npm", "name": "evil-pkg", "status": "confirmed_malicious"}, headers=ADMIN).json()
    assert r["found"] and r["verdict"] == "confirmed_malicious"

def test_review_invalid_name_422(client):
    r = client.put("/v1/review", json={"ecosystem": "pypi", "name": "bad name!", "status": "allowlisted"}, headers=ADMIN)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_name"


# ---------------------------------------------------------------- list / detail / stats
def seed(client):
    fs = [finding("a-high", **HIGH), finding("b-unres"), finding("c-npm", eco="npm", outcome="verified", verdict="low_risk", score=0)]
    client.post("/v1/findings", json=payload(fs), headers=INGEST)

def test_list_filters_and_pagination(client):
    seed(client)
    g = lambda **p: client.get("/v1/packages", params=p, headers=READ).json()
    assert g()["total"] == 3
    assert [i["name"] for i in g(verdict="high_risk")["items"]] == ["a-high"]
    assert [i["name"] for i in g(ecosystem="npm")["items"]] == ["c-npm"]
    assert g(limit=2)["total"] == 3 and len(g(limit=2)["items"]) == 2 and len(g(limit=2, offset=2)["items"]) == 1
    assert client.get("/v1/packages", params={"verdict": "bogus"}, headers=READ).status_code == 422
    client.put("/v1/review", json={"ecosystem": "pypi", "name": "never-scanned", "status": "unreviewed", "note": "x"}, headers=ADMIN)
    assert [i["name"] for i in g(verdict="not_assessed")["items"]] == ["never-scanned"]

def test_stats(client):
    seed(client)
    s = client.get("/v1/stats", headers=READ).json()
    assert s["by_verdict"] == {"high_risk": 1, "unresolved": 1, "low_risk": 1} and s["by_status"] == {"unreviewed": 3}
    assert s["last_ingest_at"]

def test_detail_404(client):
    r = client.get("/v1/package", params={"ecosystem": "pypi", "name": "nope"}, headers=READ)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
