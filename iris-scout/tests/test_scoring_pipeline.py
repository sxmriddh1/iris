from conftest import FakeFetcher, NOW, npm_doc, pypi_doc
from iris_scout.ledger import Ledger
from iris_scout.models import Ecosystem as E, LLMResponse, Outcome, RegistryRecord, Verdict
from iris_scout.pipeline import analyze
from iris_scout.registry import FetchResult, RegistryClient
from iris_scout.scoring import score_record

P = "https://pypi.org/pypi/{}/json"


def rec(**kw):
    base = dict(ecosystem=E.PYPI, name="some-lib", outcome=Outcome.VERIFIED, checked_at="2026-10-28T00:00:00Z",
                first_release="2020-01-01T00:00:00Z", release_count=10, maintainers=["a"], has_source_repo=True)
    base.update(kw)
    return RegistryRecord(**base)


def test_established_package_is_low_zero():
    s, v, sig, _ = score_record(rec(), None)
    assert (s, v, sig) == (0, Verdict.LOW, [])

def test_the_worked_example_scores_85_high():
    r = rec(name="secure-token-validator", first_release="2026-10-22T00:00:00Z", release_count=1,
            has_source_repo=False, maintainers=["new"])
    s, v, sig, _ = score_record(r, "2026-10-01T00:00:00Z")
    assert s == 40 + 15 + 10 + 10 and v is Verdict.HIGH      # maintainer listed, so no +5
    assert {x.name for x in sig} == {"registered_after_unresolved", "young_package", "few_releases", "no_source_repo"}

def test_young_legit_package_with_repo_stays_low():
    r = rec(first_release="2026-10-14T00:00:00Z", release_count=1)
    s, v, _, _ = score_record(r, None)
    assert s == 25 and v is Verdict.LOW

def test_registered_before_first_unresolved_does_not_fire():
    s, _, sig, _ = score_record(rec(first_release="2026-09-01T00:00:00Z"), "2026-10-01T00:00:00Z")
    assert "registered_after_unresolved" not in {x.name for x in sig}

def test_unresolved_gets_watchlist_verdict_no_score_and_did_you_mean():
    r = RegistryRecord(E.PYPI, "reqeusts", Outcome.UNRESOLVED)
    s, v, sig, notes = score_record(r, None)
    assert s is None and v is Verdict.UNRESOLVED and sig == [] and any("requests" in n for n in notes)

def test_verification_failure_makes_no_judgement():
    s, v, _, _ = score_record(RegistryRecord(E.PYPI, "x", Outcome.VERIFICATION_FAILED, error="429"), None)
    assert s is None and v is Verdict.UNKNOWN

def test_typosquat_similarity_signal():
    s, _, sig, _ = score_record(rec(name="reqeusts"), None)
    assert "name_similarity" in {x.name for x in sig}

def test_npm_install_hooks_signal():
    s, _, sig, _ = score_record(rec(ecosystem=E.NPM, install_hooks=True), None)
    assert s == 10


def resp(text, pid="p1"):
    return LLMResponse(pid, "", "m", "2026-10-28T00:00:00Z", text)


def test_pipeline_end_to_end_and_ledger_signal_across_runs():
    ledger = Ledger()
    # Run 1: name does not exist -> unresolved, recorded in ledger.
    c1 = RegistryClient(FakeFetcher({}), sleep=lambda s: None, now=lambda: NOW)
    f1 = analyze([resp("pip install secure-token-validator")], c1, ledger, now=lambda: NOW)
    assert f1[0].verdict == "unresolved" and f1[0].first_seen_unresolved

    # Run 2 (a week later): attacker registered it 3 days ago -> strong signal fires.
    doc = pypi_doc(first="2026-10-30T00:00:00Z", versions=1, repo=None, author="newbie")
    c2 = RegistryClient(FakeFetcher({P.format("secure-token-validator"): FetchResult(200, doc)}),
                        sleep=lambda s: None, now=lambda: NOW.replace(month=11, day=2))
    f2 = analyze([resp("pip install secure-token-validator")], c2, ledger, now=lambda: NOW.replace(month=11, day=2))
    f = f2[0]
    assert f.outcome == "verified" and f.verdict == "high_risk"
    assert "registered_after_unresolved" in {s.name for s in f.signals}

def test_pipeline_dedupes_normalizes_and_orders():
    routes = {P.format("my-lib"): FetchResult(200, pypi_doc())}
    c = RegistryClient(FakeFetcher(routes), sleep=lambda s: None, now=lambda: NOW)
    out = analyze([resp("pip install My_Lib", "a"), resp("pip install my-lib", "b"),
                   resp("pip install git+https://x/y.git")], c, Ledger(), now=lambda: NOW)
    lib = next(f for f in out if f.name == "my-lib")
    assert len(lib.observations) == 2
    mal = next(f for f in out if f.outcome == "malformed")
    assert mal.verdict == "unknown" and "not a registry package" in mal.notes[0]

def test_registry_outage_never_yields_unresolved_finding():
    c = RegistryClient(FakeFetcher({P.format("x"): FetchResult(503, None, "HTTP 503")}),
                       max_retries=1, sleep=lambda s: None, now=lambda: NOW)
    out = analyze([resp("pip install x")], c, Ledger(), now=lambda: NOW)
    assert out[0].outcome == "verification_failed" and out[0].verdict == "unknown"

def test_ledger_ignores_failures():
    l = Ledger()
    l.record("pypi", "x", Outcome.VERIFICATION_FAILED, "2026-01-01T00:00:00Z")
    assert l.first_unresolved("pypi", "x") is None
    l.record("pypi", "x", Outcome.UNRESOLVED, "2026-01-02T00:00:00Z")
    l.record("pypi", "x", Outcome.UNRESOLVED, "2026-01-05T00:00:00Z")
    assert l.first_unresolved("pypi", "x") == "2026-01-02T00:00:00Z"
