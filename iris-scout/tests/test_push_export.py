import io
import json
import urllib.error

import pytest
from iris_scout.export import build_payload
from iris_scout.models import Finding
from iris_scout.push import push_findings


def f():
    return Finding("pypi", "x", "unresolved", "unresolved", None, [], [], {})


def test_build_payload_has_meta_and_findings():
    p = build_payload([f()], "src.jsonl")
    assert p["meta"]["total_findings"] == 1 and p["meta"]["run_id"] and p["findings"][0]["name"] == "x"


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_push_sends_key_and_json_and_returns_summary():
    seen = {}
    def opener(req, timeout):
        seen["url"], seen["key"], seen["body"] = req.full_url, req.get_header("X-api-key"), json.loads(req.data)
        return Resp(b'{"run_id": "abc", "packages_created": 1}')
    out = push_findings("http://h:1/", "secret", build_payload([f()]), opener=opener)
    assert seen["url"] == "http://h:1/v1/findings" and seen["key"] == "secret" and out["packages_created"] == 1

def test_push_surfaces_structured_api_errors():
    def opener(req, timeout):
        body = io.BytesIO(json.dumps({"error": {"code": "forbidden", "message": "needs ingest"}}).encode())
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, body)
    with pytest.raises(RuntimeError, match="403 forbidden: needs ingest"):
        push_findings("http://h", "k", {}, opener=opener)

def test_push_unreachable_is_a_clean_error():
    def opener(req, timeout): raise urllib.error.URLError("refused")
    with pytest.raises(RuntimeError, match="Could not reach"):
        push_findings("http://h", "k", {}, opener=opener)
