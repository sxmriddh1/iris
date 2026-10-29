"""LLM clients. The engine only needs `complete(prompt) -> text`, so providers are pluggable.

- ReplayClient: reads saved responses from JSONL (offline, reproducible, used in tests).
- AnthropicClient: calls the Messages API using only the standard library.
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


class LLMClient(Protocol):
    model: str
    def complete(self, prompt: str) -> str: ...


class AnthropicClient:
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, api_key: str | None = None, max_tokens: int = 800,
                 temperature: float = 1.0, retries: int = 3):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("Set ANTHROPIC_API_KEY (or pass api_key) to use the Anthropic provider.")
        self.max_tokens, self.temperature, self.retries = max_tokens, temperature, retries

    def complete(self, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": self.max_tokens,
                           "temperature": self.temperature,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        headers = {"content-type": "application/json", "x-api-key": self.api_key,
                   "anthropic-version": "2023-06-01"}
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(self.URL, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as r:
                    doc = json.loads(r.read())
                return "".join(b.get("text", "") for b in doc.get("content", []) if b.get("type") == "text")
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 529) and attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError("unreachable")


def collect(client: LLMClient, prompts: Iterable[PromptSpec], repeats: int = 1) -> list[LLMResponse]:
    """Ask every prompt `repeats` times. Repeats matter: they measure how stable a
    hallucinated name is, which is what makes it exploitable."""
    out: list[LLMResponse] = []
    for p in prompts:
        for i in range(repeats):
            text = client.complete(p.text)
            out.append(LLMResponse(
                prompt_id=f"{p.id}#{i + 1}", prompt_text=p.text, model=client.model,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                text=text, ecosystem_hint=p.ecosystem))
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
