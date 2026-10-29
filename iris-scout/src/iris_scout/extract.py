"""Command-aware extraction of package references from LLM text.

Design notes
- We look at *lines that are install commands*, then tokenize them with shlex and
  walk the tokens, instead of one big regex. That lets us skip flags and their
  values, split `a && b`, keep extras / version pins, and flag URL/path/VCS refs.
- Known limitation: we do not execute or expand shell syntax ($VAR, $(...), heredocs,
  line continuations across prose). Those are skipped, not guessed.
"""
from __future__ import annotations

import re
import shlex
from typing import Iterator

from .models import Candidate, Ecosystem, LLMResponse

# Commands we recognise. Each maps (token prefix) -> ecosystem.
_PIP_PREFIXES = [
    ["pip", "install"], ["pip3", "install"],
    ["python", "-m", "pip", "install"], ["python3", "-m", "pip", "install"],
    ["uv", "pip", "install"], ["uv", "add"], ["pipx", "install"], ["poetry", "add"],
]
_NPM_PREFIXES = [
    ["npm", "install"], ["npm", "i"], ["npm", "add"],
    ["yarn", "add"], ["pnpm", "add"], ["pnpm", "install"], ["pnpm", "i"],
    ["bun", "add"], ["bun", "install"],
]

# Flags that consume the next token as their value.
_PIP_VALUE_FLAGS = {
    "-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url",
    "--extra-index-url", "-f", "--find-links", "-t", "--target", "--prefix", "--root",
    "--src", "--platform", "--python-version", "--implementation", "--abi", "--proxy",
    "--cert", "--trusted-host", "--only-binary", "--no-binary", "--upgrade-strategy",
    "--python", "--group", "--extra", "--index", "--constraints",
}
_NPM_VALUE_FLAGS = {"--registry", "--prefix", "--workspace", "-w", "--tag", "--cache", "--cwd"}

_CMD_SPLITTERS = {"&&", "||", ";", "|"}
_PROMPT_CHARS = re.compile(r"^\s*(?:\$|>|#)\s+")
_PIP_REQ = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


def _lines(text: str) -> Iterator[str]:
    """Yield candidate command lines from code fences AND inline prose/backticks."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # inline code: `pip install foo`
        for m in re.finditer(r"`([^`]+)`", line):
            yield m.group(1).strip()
        yield _PROMPT_CHARS.sub("", line)


def _match_prefix(tokens: list[str], prefixes: list[list[str]]) -> int:
    for p in prefixes:
        if tokens[: len(p)] == p:
            return len(p)
    return 0


def _split_commands(tokens: list[str]) -> list[list[str]]:
    out, cur = [], []
    for t in tokens:
        if t in _CMD_SPLITTERS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def _is_non_registry_ref(tok: str) -> bool:
    t = tok.lower()
    return (
        "://" in t or t.startswith(("git+", "file:", "github:", "gitlab:", "./", "../", "/", "~", "."))
        or t.endswith((".whl", ".tar.gz", ".zip", ".tgz", ".txt"))
        or "@git+" in t or " @ " in tok
    )


def _parse_pip_args(args: list[str]) -> list[tuple[str, str, str]]:
    """Return [(name, spec, note)] for pip-style argument lists."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            flag = a.split("=", 1)[0]
            if flag in _PIP_VALUE_FLAGS and "=" not in a:
                skip = True
            continue
        if _is_non_registry_ref(a):
            out.append((a, "", "url/path/vcs reference: not a registry package"))
            continue
        m = _PIP_REQ.match(a.split(";", 1)[0].strip())   # drop environment markers
        if not m:
            out.append((a, "", "unparseable requirement"))
            continue
        name, extras, rest = m.group(1), m.group(2) or "", m.group(3).strip()
        out.append((name, (extras + rest).strip(), ""))
    return out


def _parse_npm_args(args: list[str]) -> list[tuple[str, str, str]]:
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            flag = a.split("=", 1)[0]
            if flag in _NPM_VALUE_FLAGS and "=" not in a:
                skip = True
            continue
        if a.startswith("npm:"):               # alias syntax alias@npm:real@1.0
            out.append((a, "", "npm alias reference"))
            continue
        if a.startswith("@"):
            scope_end = a.find("/")
            at = a.find("@", 1)
            if scope_end == -1:
                out.append((a, "", "unparseable scoped name"))
            elif at > scope_end:
                out.append((a[:at], a[at + 1:], ""))
            else:
                out.append((a, "", ""))
            continue
        if _is_non_registry_ref(a) or ("/" in a and not a.startswith("@")):
            out.append((a, "", "url/path/vcs/github-shorthand reference: not a registry package"))
            continue
        name, _, spec = a.partition("@")
        out.append((name, spec, ""))
    return out


def extract_candidates(resp: LLMResponse) -> list[Candidate]:
    cands: list[Candidate] = []
    seen: set[tuple[str, str, str]] = set()
    for line in _lines(resp.text):
        try:
            tokens = shlex.split(line, comments=False, posix=True)
        except ValueError:
            continue    # unbalanced quotes: prose, not a command
        for cmd in _split_commands(tokens):
            for prefixes, eco, parser in (
                (_PIP_PREFIXES, Ecosystem.PYPI, _parse_pip_args),
                (_NPM_PREFIXES, Ecosystem.NPM, _parse_npm_args),
            ):
                n = _match_prefix(cmd, prefixes)
                if not n:
                    continue
                for name, spec, note in parser(cmd[n:]):
                    key = (eco.value, name, line)
                    if key in seen:
                        continue
                    seen.add(key)
                    cands.append(Candidate(
                        ecosystem=eco, raw_name=name, spec=spec, command=line,
                        prompt_id=resp.prompt_id, model=resp.model,
                        timestamp=resp.timestamp, note=note,
                    ))
                break
    return cands
