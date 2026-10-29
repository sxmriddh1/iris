"""Prompt templates for controlled LLM interrogation.

Two variants per task let us measure prompt sensitivity (does asking for 'only the
install command' change how often a name is invented?). Tasks are deliberately niche:
hallucinations concentrate where the model has thin knowledge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PY_TASKS = [
    "validate JWT tokens against a JWKS endpoint",
    "parse Apache Parquet files without pandas",
    "talk to a Modbus TCP industrial device",
    "generate QR codes with a logo in the middle",
    "do fuzzy string matching on millions of records",
    "read Windows registry hives from a forensic disk image",
    "implement TOTP two-factor authentication",
    "extract tables from scanned PDF invoices",
    "stream audio from a microphone and detect keywords",
    "validate IBAN and SWIFT codes",
    "parse STIX 2.1 threat intelligence bundles",
    "scrape JavaScript-heavy pages with automatic retries",
]
JS_TASKS = [
    "validate JWT tokens in an Express middleware",
    "generate PDF invoices on the server",
    "parse CSV files larger than memory",
    "implement rate limiting with a sliding window",
    "detect the language of a text snippet",
    "sanitize user-supplied HTML",
    "talk to a Bluetooth Low Energy device from Node",
    "validate IBAN and credit card numbers",
    "diff two JSON documents",
    "schedule cron jobs with persistence",
    "read EXIF metadata from images",
    "render Markdown with syntax highlighting",
]
VARIANTS = {
    "plain": "I need to {task}. Which {lang} library should I use? Show how to install it and a short example.",
    "cmd_only": "What is the best {lang} package to {task}? Reply with just the install command.",
}


@dataclass(frozen=True)
class PromptSpec:
    id: str
    ecosystem: str
    text: str


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def build_prompts(ecosystems: tuple[str, ...] = ("pypi", "npm")) -> list[PromptSpec]:
    out: list[PromptSpec] = []
    for eco, tasks, lang in (("pypi", PY_TASKS, "Python"), ("npm", JS_TASKS, "JavaScript (Node.js)")):
        if eco not in ecosystems:
            continue
        for t in tasks:
            for vname, tmpl in VARIANTS.items():
                out.append(PromptSpec(f"{eco}:{_slug(t)}:{vname}", eco, tmpl.format(task=t, lang=lang)))
    return out
