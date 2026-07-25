#!/usr/bin/env python3
"""Pangram AI-detection client — the one measurement from outside our denylist.

Every other de-ai detector was written by reading model output and writing down
what it does. That makes "the detectors stopped firing" a circular answer to
"did the rewrite work?" — de-ai grading its own homework. Pangram has never seen
our rules, so its verdict is evidence rather than an echo.

A Pangram result is an input to judgment, never a verdict. See the Verdict
Validity Rules in SKILL.md: a low fraction_ai does not certify a document any
more than a clean lexical scan does.

THIS UPLOADS THE DOCUMENT. The text is sent to a third party and retained —
every response carries a dashboard_link to the stored copy. Do not call this
without the per-document consent described in the writing-voice rule. An API key
in the environment says the user has an account, not that this document may
leave the machine.

API shape (https://docs.pangram.com/api-reference/ai-detection), async:
  POST /task           {"text": ..., "public_dashboard_link": false} -> task_id
  GET  /task/{id}      poll until stage is STAGE_SUCCESS or STAGE_FAILED

There is no single top-level AI score. The document-level result is three
fractions (ai / ai_assisted / human) plus overlapping per-window scores.

Usage:
  pangram.py --text <file>|-  [--api-key KEY] [--json] [--timeout 300]
  pangram.py --check          key present and endpoint reachable; spends nothing

Key: --api-key, else PANGRAM_API_KEY. Stdlib only.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("PANGRAM_ENDPOINT", "https://text.external-api.pangram.com")
DEFAULT_TIMEOUT = 300
POLL_START = 0.5
POLL_MAX = 5.0

# Documented status codes. Anything else falls through to a generic message —
# the docs specify no error body shape, so we never parse one.
STATUS_HELP = {
    400: "malformed request body",
    401: "x-api-key missing or invalid — check --api-key / PANGRAM_API_KEY",
    402: "insufficient credits on this Pangram account",
    403: "this API key does not own that task",
    404: "task does not exist (or expired)",
    413: "request exceeds the maximum billable units",
    415: "unsupported file type",
    422: "input text invalid — too short, or no analyzable text after preprocessing",
    429: "rate limit exceeded for this API key",
    500: "Pangram server error",
}


class PangramError(Exception):
    pass


def resolve_key(explicit=None):
    key = explicit or os.environ.get("PANGRAM_API_KEY")
    if not key:
        raise PangramError(
            "Pangram API key required. Pass --api-key or set PANGRAM_API_KEY.\n"
            "Without one, skip the external check — do not substitute a de-ai "
            "result for it.")
    return key.strip()


def _request(path, key, payload=None, timeout=30):
    """One HTTP call. Returns parsed JSON, or raises PangramError."""
    url = BASE.rstrip("/") + path
    data = None
    headers = {"x-api-key": key}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        hint = STATUS_HELP.get(e.code, "unexpected status")
        # The key must never reach the output, and an error body may echo the
        # request. Report the code and our own hint, not the server's echo.
        raise PangramError(f"HTTP {e.code} from {path}: {hint}")
    except urllib.error.URLError as e:
        raise PangramError(f"cannot reach {BASE}: {e.reason}")
    except json.JSONDecodeError:
        raise PangramError(f"{path} returned a non-JSON body")


def submit(text, key, timeout=30):
    """Create a detection task; returns task_id.

    public_dashboard_link is pinned False and deliberately not a flag: a public
    link is a second, louder disclosure than the upload, and nothing here needs
    one.
    """
    if not text.strip():
        raise PangramError("refusing to submit empty text")
    body = _request("/task", key, {"text": text, "public_dashboard_link": False},
                    timeout=timeout)
    task_id = body.get("task_id")
    if not task_id:
        raise PangramError(f"no task_id in response: {sorted(body)}")
    return task_id


def poll(task_id, key, timeout=DEFAULT_TIMEOUT, sleep=time.sleep):
    """Poll until terminal. Returns the success body.

    A failed analysis comes back as HTTP 200 with stage STAGE_FAILED, a zeroed
    body (fraction_ai 0.0, empty windows), and the reason only in `headline`.
    Checking the status code alone reads that as a flawless human document, so
    the stage is checked explicitly.
    """
    deadline = time.monotonic() + timeout
    wait = POLL_START
    while True:
        body = _request(f"/task/{task_id}", key)
        stage = body.get("stage", "")
        if stage == "STAGE_SUCCESS":
            return body
        if stage == "STAGE_FAILED":
            raise PangramError(
                f"analysis failed: {body.get('headline') or 'no reason given'}")
        if time.monotonic() >= deadline:
            raise PangramError(
                f"timed out after {timeout}s (last stage: {stage or 'unknown'}). "
                f"The scan may still be billed; task id {task_id}")
        sleep(wait)
        wait = min(wait * 1.5, POLL_MAX)


def analyze(text, key, timeout=DEFAULT_TIMEOUT, sleep=time.sleep):
    return poll(submit(text, key), key, timeout=timeout, sleep=sleep)


def summarize(body):
    """Human-readable one-block summary of a success body."""
    pct = lambda f: f"{float(f or 0.0) * 100:.1f}%"
    lines = [
        f"verdict:      {body.get('prediction_short') or '?'}"
        f"  ({body.get('headline') or 'no headline'})",
        f"AI:           {pct(body.get('fraction_ai'))}"
        f"   ({body.get('num_ai_segments', 0)} segments)",
        f"AI-assisted:  {pct(body.get('fraction_ai_assisted'))}"
        f"   ({body.get('num_ai_assisted_segments', 0)} segments)",
        f"human:        {pct(body.get('fraction_human'))}"
        f"   ({body.get('num_human_segments', 0)} segments)",
        f"windows:      {len(body.get('windows') or [])}",
    ]
    if body.get("dashboard_link"):
        lines.append(f"stored at:    {body['dashboard_link']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Pangram AI detection (uploads the text — see SKILL.md)")
    ap.add_argument("--text", help="file to analyze, or - for stdin")
    ap.add_argument("--api-key", help="Pangram key (or set PANGRAM_API_KEY)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--json", action="store_true",
                    help="emit the raw response (feeds pangram_report.py)")
    ap.add_argument("--check", action="store_true",
                    help="verify key and endpoint without submitting a document")
    a = ap.parse_args()

    try:
        key = resolve_key(a.api_key)
    except PangramError as e:
        sys.exit(str(e))

    if a.check:
        # Probe an id that cannot exist. A key problem answers 401/403 and a
        # good key answers 404 — so reachability and auth are both proven
        # without submitting a document or spending a credit.
        try:
            _request("/task/00000000-0000-0000-0000-000000000000", key)
            print("key accepted; endpoint reachable")
        except PangramError as e:
            msg = str(e)
            if "HTTP 404" in msg:
                print(f"key accepted; endpoint reachable ({BASE})")
            else:
                sys.exit(f"preflight failed: {msg}")
        return

    if not a.text:
        sys.exit("--text <file>|- is required (or use --check)")
    text = sys.stdin.read() if a.text == "-" else open(a.text, encoding="utf-8").read()

    try:
        body = analyze(text, key, timeout=a.timeout)
    except PangramError as e:
        sys.exit(str(e))

    print(json.dumps(body, indent=2, ensure_ascii=False) if a.json
          else summarize(body))


if __name__ == "__main__":
    main()
