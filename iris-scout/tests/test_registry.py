from conftest import FakeFetcher, NOW, npm_doc, pypi_doc
from iris_scout.models import Ecosystem as E, Outcome
from iris_scout.registry import FetchResult, RegistryClient

P = "https://pypi.org/pypi/{}/json"
N = "https://registry.npmjs.org/{}"


def client(routes, **kw):
    f = FakeFetcher(routes)
    return RegistryClient(f, sleep=lambda s: None, now=lambda: NOW, **kw), f


def test_200_verified_with_metadata():
    c, _ = client({P.format("x"): FetchResult(200, pypi_doc(versions=3))})
    r = c.verify(E.PYPI, "x")
    assert r.outcome is Outcome.VERIFIED and r.release_count == 3
    assert r.first_release == "2020-01-01T00:00:00Z" and r.has_source_repo and r.maintainers == ["Ann"]

def test_404_is_unresolved_not_error():
    c, _ = client({})
    assert c.verify(E.PYPI, "nope").outcome is Outcome.UNRESOLVED

def test_429_then_success_retries_and_honours_backoff():
    sleeps = []
    f = FakeFetcher({P.format("x"): [FetchResult(429, None, "HTTP 429", 2.0), FetchResult(200, pypi_doc())]})
    c = RegistryClient(f, sleep=sleeps.append, now=lambda: NOW)
    assert c.verify(E.PYPI, "x").outcome is Outcome.VERIFIED and sleeps == [2.0]

def test_persistent_429_is_verification_failed_never_unresolved():
    c, f = client({P.format("x"): FetchResult(429, None, "HTTP 429")}, max_retries=2)
    r = c.verify(E.PYPI, "x")
    assert r.outcome is Outcome.VERIFICATION_FAILED and len(f.calls) == 3

def test_network_error_is_verification_failed():
    c, _ = client({P.format("x"): FetchResult(None, None, "URLError: down")}, max_retries=1)
    assert c.verify(E.PYPI, "x").outcome is Outcome.VERIFICATION_FAILED

def test_403_is_verification_failed():
    c, _ = client({P.format("x"): FetchResult(403, None, "HTTP 403")})
    assert c.verify(E.PYPI, "x").outcome is Outcome.VERIFICATION_FAILED

def test_bad_json_is_verification_failed():
    c, _ = client({P.format("x"): FetchResult(200, b"<html>")})
    r = c.verify(E.PYPI, "x")
    assert r.outcome is Outcome.VERIFICATION_FAILED and "JSON" in r.error

def test_results_are_cached_per_run():
    c, f = client({P.format("x"): FetchResult(200, pypi_doc())})
    c.verify(E.PYPI, "x"); c.verify(E.PYPI, "x")
    assert len(f.calls) == 1

def test_npm_scoped_url_encoding_and_hooks():
    c, f = client({N.format("@a%2Fb"): FetchResult(200, npm_doc(hooks=True))})
    r = c.verify(E.NPM, "@a/b")
    assert f.calls == [N.format("@a%2Fb")] and r.install_hooks is True and r.release_count == 3
    assert r.first_release == "2019-01-01T00:00:00Z"


def test_pypi_email_only_maintainer_still_counts():
    import json
    doc = json.loads(pypi_doc(author=None))
    doc["info"]["author_email"] = "Jane <jane@example.org>"
    c, _ = client({P.format("x"): FetchResult(200, json.dumps(doc).encode())})
    assert c.verify(E.PYPI, "x").maintainers == ["Jane <jane@example.org>"]
