import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from iris_scout.llm import FatalLLMError, GroqClient, LLMError, collect, read_jsonl, write_jsonl
from iris_scout.prompts import PromptSpec

KEY = "gsk_test_SECRET_123"


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def ok(text="pip install requests"):
    return Resp(json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]}).encode())


def http_error(code, retry_after=None):
    hdrs = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError("https://x", code, "msg", hdrs, io.BytesIO(b"{}"))


class FakeNet:
    """Scripted opener: each item is a Resp to return or an exception to raise."""
    def __init__(self, *script): self.script, self.requests = list(script), []
    def __call__(self, req, timeout):
        self.requests.append(req)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(net, **kw):
    sleeps = []
    c = GroqClient("test-model", api_key=KEY, opener=net, sleep=sleeps.append, **kw)
    return c, sleeps


# ---------------------------------------------------------------- happy path and request shape
def test_returns_the_answer_text():
    c, _ = client(FakeNet(ok("hello")))
    assert c.complete("hi") == "hello"

def test_request_has_bearer_auth_user_agent_and_the_prompt():
    net = FakeNet(ok())
    client(net)[0].complete("my prompt")
    req = net.requests[0]
    assert req.full_url == "https://api.groq.com/openai/v1/chat/completions" and req.get_method() == "POST"
    assert req.get_header("Authorization") == f"Bearer {KEY}"
    assert req.get_header("User-agent") and "python-urllib" not in req.get_header("User-agent").lower()
    assert req.get_header("Content-type") == "application/json"
    body = json.loads(req.data)
    assert body["model"] == "test-model" and body["messages"] == [{"role": "user", "content": "my prompt"}]
    assert "max_tokens" in body and "temperature" in body

def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        GroqClient("m")

def test_key_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert GroqClient("m").api_key == "from-env"


# ---------------------------------------------------------------- retries
def test_429_then_success_honours_retry_after():
    net = FakeNet(http_error(429, "2"), ok("done"))
    c, sleeps = client(net)
    assert c.complete("p") == "done" and sleeps == [2.0] and len(net.requests) == 2

def test_retry_after_is_capped():
    c, sleeps = client(FakeNet(http_error(429, "9999"), ok()))
    c.complete("p")
    assert sleeps == [60.0]

def test_without_retry_after_backoff_doubles():
    net = FakeNet(http_error(503), http_error(502), http_error(500), ok("fine"))
    c, sleeps = client(net)
    assert c.complete("p") == "fine" and sleeps == [1.0, 2.0, 4.0]

def test_persistent_429_gives_up_after_the_retry_limit():
    net = FakeNet(*[http_error(429) for _ in range(4)])
    c, sleeps = client(net, retries=3)
    with pytest.raises(RuntimeError, match="429 persisted"):
        c.complete("p")
    assert len(net.requests) == 4 and len(sleeps) == 3

def test_network_errors_are_retried_then_raised():
    c, sleeps = client(FakeNet(urllib.error.URLError("wifi down"), ok("back")))
    assert c.complete("p") == "back" and sleeps == [1]
    c2, _ = client(FakeNet(*[TimeoutError("slow") for _ in range(4)]), retries=3)
    with pytest.raises(RuntimeError, match="Could not reach Groq"):
        c2.complete("p")


# ---------------------------------------------------------------- errors that must not be retried
@pytest.mark.parametrize("code,hint", [(401, "GROQ_API_KEY"), (400, "model name"), (404, "model name"), (403, "403")])
def test_client_errors_fail_immediately_with_a_hint(code, hint):
    net = FakeNet(http_error(code), ok())
    c, sleeps = client(net)
    with pytest.raises(RuntimeError, match=hint) as ei:
        c.complete("p")
    assert len(net.requests) == 1 and sleeps == []
    assert KEY not in str(ei.value)

def test_the_key_never_appears_in_any_error():
    for item in (http_error(401), http_error(429), urllib.error.URLError("x"), Resp(b"not json"), Resp(b'{"choices": []}')):
        c, _ = client(FakeNet(*[item] * 5), retries=0)
        with pytest.raises(RuntimeError) as ei:
            c.complete("p")
        assert KEY not in str(ei.value)


# ---------------------------------------------------------------- bad answers are loud, never empty
@pytest.mark.parametrize("payload", [b'{"choices": []}', b"{}", b'{"choices": [{"message": {"content": null}, "finish_reason": "content_filter"}]}',
                                     b'{"choices": [{"message": {"content": "   "}}]}', b"<html>"])
def test_missing_or_blank_answer_raises(payload):
    c, _ = client(FakeNet(Resp(payload)))
    with pytest.raises(RuntimeError):
        c.complete("p")


# ---------------------------------------------------------------- real sockets: the actual urllib code path
class _Handler(BaseHTTPRequestHandler):
    seen = []
    script = []
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        _Handler.seen.append({"auth": self.headers.get("Authorization"), "ua": self.headers.get("User-Agent"),
                              "body": json.loads(self.rfile.read(n))})
        code, extra = _Handler.script.pop(0)
        payload = json.dumps({"choices": [{"message": {"content": "pip install flask"}}]}).encode() if code == 200 else b"{}"
        self.send_response(code)
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *a): pass


@pytest.fixture
def server():
    _Handler.seen, _Handler.script = [], []
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1/chat", _Handler
    srv.shutdown()


def test_real_http_round_trip_with_429_retry_after(server):
    url, h = server
    h.script = [(429, {"Retry-After": "1"}), (200, {})]
    sleeps = []
    c = GroqClient("m", api_key=KEY, sleep=sleeps.append)
    c.URL = url
    assert c.complete("what package?") == "pip install flask"
    assert sleeps == [1.0] and len(h.seen) == 2
    assert h.seen[0]["auth"] == f"Bearer {KEY}" and h.seen[0]["body"]["messages"][0]["content"] == "what package?"
    assert "python-urllib" not in h.seen[0]["ua"].lower()

def test_real_http_401_stops_at_once(server):
    url, h = server
    h.script = [(401, {})]
    c = GroqClient("m", api_key=KEY, sleep=lambda s: None)
    c.URL = url
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        c.complete("p")
    assert len(h.seen) == 1


# ---------------------------------------------------------------- collect() and JSONL (previously untested)
class Echo:
    model = "echo-model"
    def __init__(self): self.n = 0
    def complete(self, prompt): self.n += 1; return f"pip install pkg{self.n}"


def test_collect_repeats_and_numbers_each_prompt():
    specs = [PromptSpec("pypi:a:plain", "pypi", "q1"), PromptSpec("npm:b:cmd_only", "npm", "q2")]
    out = collect(Echo(), specs, repeats=3)
    assert [r.prompt_id for r in out] == ["pypi:a:plain#1", "pypi:a:plain#2", "pypi:a:plain#3",
                                          "npm:b:cmd_only#1", "npm:b:cmd_only#2", "npm:b:cmd_only#3"]
    assert all(r.model == "echo-model" and r.timestamp.endswith("Z") for r in out)
    assert out[0].prompt_text == "q1" and out[3].ecosystem_hint == "npm"

def test_jsonl_round_trip(tmp_path):
    out = collect(Echo(), [PromptSpec("p", "pypi", "q")], repeats=2)
    f = tmp_path / "r.jsonl"
    write_jsonl(out, str(f))
    assert read_jsonl(str(f)) == out

def test_read_jsonl_reports_the_bad_line(tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text('{"prompt_id": "x"}\n')
    with pytest.raises(ValueError, match="bad.jsonl:1"):
        read_jsonl(str(f))


# ---------------------------------------------------------------- failure policy: skip one, stop on all
@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_config_errors_are_fatal(code):
    c, _ = client(FakeNet(http_error(code)))
    with pytest.raises(FatalLLMError):
        c.complete("p")

@pytest.mark.parametrize("item", [http_error(429), http_error(503), Resp(b'{"choices": []}'), Resp(b"<html>"), urllib.error.URLError("x")])
def test_transient_errors_are_skippable_not_fatal(item):
    c, _ = client(FakeNet(*[item] * 5), retries=1)
    with pytest.raises(LLMError):
        c.complete("p")


class Flaky:
    """Fails on chosen call numbers with the given exception."""
    model = "flaky"
    def __init__(self, fail_at, exc):
        self.n, self.fail_at, self.exc = 0, set(fail_at), exc
    def complete(self, prompt):
        self.n += 1
        if self.n in self.fail_at:
            raise self.exc
        return f"pip install pkg{self.n}"


SPECS = [PromptSpec(f"p{i}", "pypi", f"q{i}") for i in range(5)]


def test_collect_skips_a_failed_prompt_and_keeps_going():
    errors, saved = [], []
    out = collect(Flaky({2, 4}, LLMError("empty answer")), SPECS, on_error=lambda pid, m: errors.append(pid), sink=saved.append)
    assert [r.prompt_id for r in out] == ["p0#1", "p2#1", "p4#1"] and out == saved
    assert errors == ["p1#1", "p3#1"]

def test_collect_stops_on_fatal_but_earlier_answers_were_already_saved():
    saved = []
    with pytest.raises(FatalLLMError):
        collect(Flaky({3}, FatalLLMError("bad key")), SPECS, sink=saved.append)
    assert [r.prompt_id for r in saved] == ["p0#1", "p1#1"]       # not lost

def test_collect_delay_waits_between_calls_only():
    sleeps = []
    collect(Echo(), SPECS[:3], delay=2.5, sleep=sleeps.append)
    assert sleeps == [2.5, 2.5]

def test_collect_reports_progress():
    seen = []
    collect(Echo(), SPECS[:2], repeats=2, on_progress=lambda n, t, pid, ch: seen.append((n, t, pid)))
    assert seen == [(1, 4, "p0#1"), (2, 4, "p0#2"), (3, 4, "p1#1"), (4, 4, "p1#2")]
