"""JSON and CSV export with run metadata for reproducibility."""
from __future__ import annotations

import csv
import json
import uuid
from collections import Counter
from datetime import datetime, timezone

from . import __version__
from .models import Finding


def build_payload(findings: list[Finding], source: str = "") -> dict:
    """The exact document written by --json and sent by --push (the Scout -> API contract)."""
    meta = {
        "tool": "iris-scout", "version": __version__, "run_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_responses": source,
        "counts": dict(Counter(f.verdict for f in findings)),
        "total_findings": len(findings),
    }
    return {"meta": meta, "findings": [x.to_dict() for x in findings]}


def write_json(findings: list[Finding], path: str, source: str = "") -> dict:
    payload = build_payload(findings, source)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return payload["meta"]


def write_csv(findings: list[Finding], path: str) -> None:
    cols = ["ecosystem", "name", "outcome", "verdict", "risk_score", "signals", "observations",
            "models", "first_release", "release_count", "repo_url", "first_seen_unresolved"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for x in findings:
            r = x.registry or {}
            w.writerow([x.ecosystem, x.name, x.outcome, x.verdict,
                        "" if x.risk_score is None else x.risk_score,
                        ";".join(f"{s.name}:{s.points}" for s in x.signals),
                        len(x.observations), ";".join(sorted({o["model"] for o in x.observations})),
                        r.get("first_release") or "", r.get("release_count") if r.get("release_count") is not None else "",
                        r.get("repo_url") or "", x.first_seen_unresolved or ""])
