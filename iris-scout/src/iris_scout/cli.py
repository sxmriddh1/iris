"""Command line interface.

  iris-scout prompts                              list the built-in prompts
  iris-scout collect --model M --out r.jsonl      ask an LLM, save raw responses
  iris-scout analyze r.jsonl --json f.json        extract, verify, score, export
  iris-scout check pypi some-package              verify and score one name
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
import os

from .export import build_payload, write_csv, write_json
from .push import push_findings
from .ledger import Ledger
from .llm import AnthropicClient, collect, read_jsonl, write_jsonl
from .models import Ecosystem, Finding, LLMResponse
from .pipeline import analyze
from .prompts import build_prompts
from .registry import RegistryClient

log = logging.getLogger("iris_scout")


def _print_summary(findings: list[Finding]) -> None:
    if not findings:
        print("No package references found.")
        return
    w = max(len(f.name) for f in findings)
    print(f"{'VERDICT':<13} {'SCORE':>5}  {'ECO':<5} {'NAME':<{w}}  OBS  SIGNALS")
    for f in findings:
        sc = "-" if f.risk_score is None else str(f.risk_score)
        sig = ", ".join(f"{s.name}(+{s.points})" for s in f.signals) or (f.notes[0][:60] if f.notes else "")
        print(f"{f.verdict:<13} {sc:>5}  {f.ecosystem:<5} {f.name:<{w}}  {len(f.observations):>3}  {sig}")


def cmd_prompts(a) -> int:
    ps = build_prompts(tuple(a.ecosystem))
    for p in ps:
        print(f"{p.id}\t{p.text}")
    print(f"\n{len(ps)} prompts", file=sys.stderr)
    return 0


def cmd_collect(a) -> int:
    client = AnthropicClient(a.model, temperature=a.temperature)
    prompts = build_prompts(tuple(a.ecosystem))[: a.limit or None]
    log.info("asking %s %d prompts x %d repeats", a.model, len(prompts), a.repeats)
    write_jsonl(collect(client, prompts, a.repeats), a.out)
    print(f"Saved responses to {a.out}")
    return 0


def cmd_analyze(a) -> int:
    responses = read_jsonl(a.responses)
    ledger = Ledger(a.ledger)
    findings = analyze(responses, RegistryClient(), ledger)
    _print_summary(findings)
    if a.json:
        write_json(findings, a.json, source=a.responses)
        print(f"\nJSON: {a.json}")
    if a.csv:
        write_csv(findings, a.csv)
        print(f"CSV:  {a.csv}")
    if a.push:
        key = a.api_key or os.environ.get("IRIS_API_KEY", "")
        if not key:
            print("--push needs --api-key or IRIS_API_KEY", file=sys.stderr)
            return 2
        try:
            res = push_findings(a.push, key, build_payload(findings, a.responses))
        except RuntimeError as e:
            print(f"Push failed: {e}", file=sys.stderr)
            return 1
        print(f"Pushed to {a.push}: {res['packages_created']} new, {res['packages_updated']} updated, "
              f"{res['observations_added']} observations, {res['assessments_added']} assessments, "
              f"{len(res['rejected'])} rejected (run {res['run_id'][:8]})")
    ledger.close()
    return 0


def cmd_check(a) -> int:
    fake = LLMResponse("manual", "", "manual", "", f"`{'pip' if a.ecosystem == 'pypi' else 'npm'} install {a.name}`")
    ledger = Ledger(a.ledger)
    findings = analyze([fake], RegistryClient(), ledger)
    _print_summary(findings)
    for f in findings:
        for s in f.signals:
            print(f"  +{s.points:<3} {s.name}: {s.detail}")
        for n in f.notes:
            print(f"  note: {n}")
    ledger.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="iris-scout", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prompts"); p.add_argument("--ecosystem", nargs="+", default=["pypi", "npm"], choices=["pypi", "npm"]); p.set_defaults(fn=cmd_prompts)

    p = sub.add_parser("collect"); p.add_argument("--model", required=True)
    p.add_argument("--ecosystem", nargs="+", default=["pypi", "npm"], choices=["pypi", "npm"])
    p.add_argument("--repeats", type=int, default=1); p.add_argument("--limit", type=int, default=0)
    p.add_argument("--temperature", type=float, default=1.0); p.add_argument("--out", required=True); p.set_defaults(fn=cmd_collect)

    p = sub.add_parser("analyze"); p.add_argument("responses")
    p.add_argument("--json"); p.add_argument("--csv"); p.add_argument("--ledger", default="iris_ledger.sqlite")
    p.add_argument("--push", metavar="URL", help="send findings to an Iris API, e.g. http://localhost:8000")
    p.add_argument("--api-key", help="ingest API key (or set IRIS_API_KEY)")
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("check"); p.add_argument("ecosystem", choices=["pypi", "npm"]); p.add_argument("name")
    p.add_argument("--ledger", default=":memory:"); p.set_defaults(fn=cmd_check)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
