import json

import pytest
from iris_scout import cli
from iris_scout.llm import FatalLLMError, LLMError


class FakeGroq:
    instances = []
    script = None          # list of str | Exception, consumed in order; None = always succeed

    def __init__(self, model, max_tokens=800, temperature=1.0, **kw):
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature
        self.n = 0
        FakeGroq.instances.append(self)

    def complete(self, prompt):
        self.n += 1
        item = FakeGroq.script.pop(0) if FakeGroq.script else f"pip install pkg{self.n}"
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeGroq.instances, FakeGroq.script = [], None
    monkeypatch.setattr(cli, "GroqClient", FakeGroq)


def run(*args):
    return cli.main(["collect", "--model", "m", *args])


def lines(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def test_writes_one_json_line_per_answer(tmp_path, capsys):
    out = tmp_path / "r.jsonl"
    assert run("--ecosystem", "pypi", "--limit", "3", "--out", str(out)) == 0
    rows = lines(out)
    assert len(rows) == 3 and all(r["model"] == "m" and r["text"] and r["ecosystem_hint"] == "pypi" for r in rows)
    assert "Saved 3 answer(s)" in capsys.readouterr().out

def test_repeats_multiply_calls(tmp_path):
    out = tmp_path / "r.jsonl"
    run("--limit", "2", "--repeats", "3", "--out", str(out))
    assert [r["prompt_id"].split("#")[1] for r in lines(out)] == ["1", "2", "3", "1", "2", "3"]

def test_refuses_to_overwrite_raw_data(tmp_path, capsys):
    out = tmp_path / "r.jsonl"
    out.write_text("precious\n")
    assert run("--limit", "1", "--out", str(out)) == 2
    assert out.read_text() == "precious\n" and "already exists" in capsys.readouterr().err
    assert run("--limit", "1", "--overwrite", "--out", str(out)) == 0
    assert "precious" not in out.read_text()

def test_flags_reach_the_client(tmp_path):
    run("--limit", "1", "--max-tokens", "2500", "--temperature", "0.3", "--out", str(tmp_path / "r.jsonl"))
    c = FakeGroq.instances[0]
    assert (c.max_tokens, c.temperature) == (2500, 0.3)

def test_a_skippable_failure_does_not_lose_the_run(tmp_path, capsys):
    out = tmp_path / "r.jsonl"
    FakeGroq.script = ["a", LLMError("empty answer"), "c"]
    assert run("--ecosystem", "pypi", "--limit", "3", "--out", str(out)) == 0
    assert [r["text"] for r in lines(out)] == ["a", "c"]
    err = capsys.readouterr().err
    assert "skipped" in err and "empty answer" in err

def test_a_fatal_error_stops_but_keeps_what_was_saved(tmp_path, capsys):
    out = tmp_path / "r.jsonl"
    FakeGroq.script = ["a", "b", FatalLLMError("Groq rejected the API key (401). Check GROQ_API_KEY.")]
    assert run("--ecosystem", "pypi", "--limit", "5", "--out", str(out)) == 1
    assert [r["text"] for r in lines(out)] == ["a", "b"]
    assert "2 answer(s) were saved" in capsys.readouterr().err

def test_missing_key_is_a_friendly_error_and_does_not_touch_the_output(tmp_path, monkeypatch, capsys):
    def boom(*a, **k): raise RuntimeError("Set GROQ_API_KEY (or pass api_key) to use the Groq provider.")
    monkeypatch.setattr(cli, "GroqClient", boom)
    out = tmp_path / "r.jsonl"
    assert run("--limit", "1", "--out", str(out)) == 2
    assert not out.exists() and "Cannot start" in capsys.readouterr().err

def test_everything_skipped_is_a_failure_exit(tmp_path):
    FakeGroq.script = [LLMError("x"), LLMError("y")]
    assert run("--ecosystem", "pypi", "--limit", "2", "--out", str(tmp_path / "r.jsonl")) == 1
