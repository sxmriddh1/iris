"""Send a findings payload to the Iris API (Phase 2). Standard library only."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable


def push_findings(base_url: str, api_key: str, payload: dict, timeout: float = 60.0,
                  opener: Callable = urllib.request.urlopen) -> dict:
    """POST payload to {base_url}/v1/findings. Returns the API's ingest summary.
    Raises RuntimeError with the API's structured error message on failure."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/findings", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": api_key})
    try:
        with opener(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())["error"]
            raise RuntimeError(f"Iris API {e.code} {err['code']}: {err['message']}") from None
        except (ValueError, KeyError):
            raise RuntimeError(f"Iris API HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Iris API at {base_url}: {e.reason}") from None
