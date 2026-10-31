"""LLM clients. The engine only needs `complete(prompt) -> text`, so providers are pluggable.

- GroqClient: calls the Groq chat-completions API using only the standard library.
Add other providers by implementing the same two attributes.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Iterable, Protocol

from .models import LLMResponse
from .prompts import PromptSpec


class LLMError(RuntimeError):
    """One request failed in a way that may not repeat (empty answer, outage). Skipping it is reasonable."""


class FatalLLMError(RuntimeError):
    """The same failure would hit every request (bad key, wrong model). The whole run must stop."""


class LLMClient(Protocol):
    model: str
    def complete(self, prompt: str) -> str: ...


class GroqClient:
    """Groq chat-completions client (OpenAI-compatible). Standard library only.

    `opener` and `sleep` are parameters so tests can fake the network and skip real waiting.
    """
    URL = "https://api.groq.com/openai/v1/chat/completions"
    RETRYABLE = (429, 500, 502, 503, 504)      # transient: worth trying again
    MAX_WAIT = 60.0

    def __init__(self, model, api_key=None, max_tokens=800, temperature=1.0, retries=3,
                 opener=urllib.request.urlopen, sleep=time.sleep):
        self.model = model
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("Set GROQ_API_KEY (or pass api_key) to use the Groq provider.")
        self.max_tokens, self.temperature, self.retries = max_tokens, temperature, retries
        self.opener, self.sleep = opener, sleep

    def complete(self, prompt: str) -> str:
        body = json.dumps({
            "model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.api_key}",
                   "User-Agent": "iris-scout/0.1"}      # Python's default UA is sometimes blocked (403)
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(self.URL, data=body, headers=headers, method="POST")
            try:
                with self.opener(req, timeout=60) as r:
                    raw = r.read()
            except urllib.error.HTTPError as e:
                if e.code in self.RETRYABLE and attempt < self.retries:
                    self.sleep(self._delay(e, attempt))
                    continue
                kind = FatalLLMError if e.code in (400, 401, 403, 404) else LLMError
                raise kind(self._http_message(e.code, attempt)) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < self.retries:
                    self.sleep(2 ** attempt)
                    continue
                raise LLMError(f"Could not reach Groq after {attempt + 1} attempts: {e}") from None
            try:
                doc = json.loads(raw)
            except ValueError:
                raise LLMError("Groq returned a response that is not valid JSON.") from None
            return self._extract(doc)
        raise RuntimeError("unreachable")        # the loop always returns or raises

    def _delay(self, e: urllib.error.HTTPError, attempt: int) -> float:
        """Prefer the server's Retry-After; otherwise back off 1s, 2s, 4s..."""
        ra = e.headers.get("Retry-After") if e.headers else None
        try:
            if ra is not None:
                return min(max(float(ra), 0.0), self.MAX_WAIT)
        except ValueError:
            pass
        return float(2 ** attempt)

    def _http_message(self, code: int, attempt: int) -> str:
        """Never includes the API key."""
        if code == 401:
            return "Groq rejected the API key (401). Check GROQ_API_KEY."
        if code == 403:
            return "Groq refused the request (403). Check the key and your access, then try again."
        if code in (400, 404):
            return f"Groq returned {code}. Check the model name ({self.model!r}); it may be retired or misspelled."
        if code in self.RETRYABLE:
            return f"Groq error {code} persisted after {attempt + 1} attempts."
        return f"Groq returned HTTP {code}."

    @staticmethod
    def _extract(doc: dict) -> str:
        choices = doc.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content")) if choices else None
        if not isinstance(text, str) or not text.strip():
            reason = choices[0].get("finish_reason") if choices else "no choices"
            raise LLMError(f"Groq returned no answer text ({reason}).")   # loud, never an empty string
        return text


def collect(client: LLMClient, prompts: Iterable[PromptSpec], repeats: int = 1, sink=None, on_error=None,
            on_progress=None, delay: float = 0.0, sleep=time.sleep) -> list[LLMResponse]:
    """Ask every prompt `repeats` times. Repeats matter: they measure how stable a hallucinated
    name is, which is what makes it exploitable.

    - A request that fails with LLMError is reported via on_error and skipped; the run continues.
    - FatalLLMError (bad key, wrong model) propagates: retrying 700 times would not help.
    - sink(response) is called after EVERY success, so the caller can save as it goes and a crash
      or Ctrl+C never loses the answers already paid for.
    """
    jobs = [(p, i) for p in prompts for i in range(repeats)]
    out: list[LLMResponse] = []
    for n, (p, i) in enumerate(jobs, 1):
        pid = f"{p.id}#{i + 1}"
        if delay and n > 1:
            sleep(delay)
        try:
            text = client.complete(p.text)
        except LLMError as e:
            if on_error:
                on_error(pid, str(e))
            continue
        r = LLMResponse(prompt_id=pid, prompt_text=p.text, model=client.model,
                        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        text=text, ecosystem_hint=p.ecosystem)
        out.append(r)
        if sink:
            sink(r)
        if on_progress:
            on_progress(n, len(jobs), pid, len(text))
    return out


def write_jsonl(responses: Iterable[LLMResponse], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in responses:
            f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")


def read_jsonl(path: str) -> list[LLMResponse]:
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            try:
                out.append(LLMResponse(**d))
            except TypeError as e:
                raise ValueError(f"{path}:{n}: bad response record: {e}") from e
    return out
