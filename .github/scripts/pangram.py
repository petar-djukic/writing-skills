#!/usr/bin/env python3
"""Pangram AI-detection client — the one measurement from outside our denylist.

Every other filter-tells detector was written by reading model output and writing down
what it does. That makes "the detectors stopped firing" a circular answer to
"did the rewrite work?" — filter-tells grading its own homework. Pangram has never seen
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

  Single task:
    POST /task           {"text": ..., "public_dashboard_link": false} -> task_id
    GET  /task/{id}      poll until stage is STAGE_SUCCESS or STAGE_FAILED

  Bulk (https://docs.pangram.com/api-reference/bulk-api):
    POST /bulk           {"items": [{"id": ..., "text": ...}, ...]} -> bulk_id
    GET  /bulk/{id}      poll until status is succeeded/failed/partial
    GET  /bulk/{id}/results?offset=0&limit=100   paginated per-item results

Billing is per started 1,000-word block per item, minimum 1 unit per item.
WordBudgetBatcher packs text blobs into ~1,000-word bags so each bag costs
one unit instead of one per blob.

Usage:
  pangram.py --text <file>|-  [--api-key KEY] [--json] [--timeout 300]
  pangram.py --bulk <file>    items JSON; each {"id": ..., "text": ...}
  pangram.py --check          key present and endpoint reachable; spends nothing

Key: --api-key, else PANGRAM_API_KEY. Stdlib only.
"""

import argparse
import json
import math
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


def _secrets_module():
    """The shared credential loader (GH-184), a sibling since GH-212.

    Path computed from __file__, never written out: this tree is copied between
    agent surfaces, and a literal surface name would trip the .github
    self-containment guard.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)
    import credentials as _s
    return _s


def resolve_key(explicit=None, start_path=None):
    """--api-key, else PANGRAM_API_KEY, else .secrets/ in the working repo.

    start_path is where the .secrets/ search begins; tests pass an isolated
    directory so the result does not depend on whatever happens to sit above
    the checkout on a particular machine.
    """
    try:
        s = _secrets_module()
    except ImportError:
        key = explicit or os.environ.get("PANGRAM_API_KEY")
        if not key:
            raise PangramError(
                "Pangram API key required. Pass --api-key or set PANGRAM_API_KEY.")
        return key.strip()
    try:
        return s.resolve("pangram", explicit=explicit, start_path=start_path).strip()
    except s.SecretsError as e:
        raise PangramError(
            f"{e}\nWithout a key, skip the external check — do not substitute "
            f"a filter-tells result for it.")


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


# ---------------------------------------------------------------------------
# Bulk API
# ---------------------------------------------------------------------------

BULK_TERMINAL = frozenset({"succeeded", "failed", "partial"})


def billable_units(text):
    """How many billable units a text blob costs: ceil(words / 1000), min 1."""
    return max(1, math.ceil(len(text.split()) / 1000))


def submit_bulk(items, key, timeout=30):
    """POST /bulk with an items list. Returns the parsed 202 response.

    Each item must have "text"; "id" is optional but recommended.
    """
    if not items:
        raise PangramError("refusing to submit an empty bulk request")
    body = _request("/bulk", key, {"items": items}, timeout=timeout)
    if not body.get("bulk_id"):
        raise PangramError(f"no bulk_id in response: {sorted(body)}")
    return body


def poll_bulk(bulk_id, key, timeout=DEFAULT_TIMEOUT, sleep=time.sleep):
    """Poll GET /bulk/{id} until the job reaches a terminal status.

    Returns the status body. Terminal statuses: succeeded, failed, partial.
    """
    deadline = time.monotonic() + timeout
    wait = POLL_START
    while True:
        body = _request(f"/bulk/{bulk_id}", key)
        status = body.get("status", "")
        if status in BULK_TERMINAL:
            return body
        if time.monotonic() >= deadline:
            raise PangramError(
                f"bulk timed out after {timeout}s (last status: {status or 'unknown'}). "
                f"bulk_id {bulk_id}")
        sleep(wait)
        wait = min(wait * 1.5, POLL_MAX)


def fetch_results(bulk_id, key, offset=0, limit=100, timeout=30):
    """GET /bulk/{id}/results with pagination. Returns the parsed response."""
    return _request(f"/bulk/{bulk_id}/results?offset={offset}&limit={limit}",
                    key, timeout=timeout)


def analyze_bulk(items, key, timeout=DEFAULT_TIMEOUT, sleep=time.sleep):
    """Submit, poll, and fetch all results. Returns a list of result items.

    Each result item has the same shape as a single-task success body, nested
    under "result", plus "index", "id", "stage", and "error".
    """
    resp = submit_bulk(items, key)
    bulk_id = resp["bulk_id"]
    poll_bulk(bulk_id, key, timeout=timeout, sleep=sleep)
    all_items, offset = [], 0
    while True:
        page = fetch_results(bulk_id, key, offset=offset)
        all_items.extend(page.get("items") or [])
        all_items.extend(page.get("failed_items") or [])
        total = page.get("total_items", 0)
        if offset + (page.get("limit") or 100) >= total:
            break
        offset += page.get("limit") or 100
    return all_items


class WordBudgetBatcher:
    """Accumulate text blobs into bags of ~word_limit words each.

    Each bag becomes one bulk item, costing one billable unit. Without
    batching, each blob would cost one unit regardless of length.

    Usage:
        batcher = WordBudgetBatcher(word_limit=1000)
        for para_id, text in paragraphs:
            batcher.add(para_id, text)
        for batch in batcher.batches():
            # batch is {"id": "bag-0", "text": "...", "sources": [...],
            #           "offsets": [...]}
            submit_bulk([{"id": batch["id"], "text": batch["text"]}], key)
    """

    def __init__(self, word_limit=1000, sep="\n\n"):
        self._word_limit = word_limit
        self._sep = sep
        self._items = []

    def add(self, source_id, text):
        self._items.append((source_id, text))

    def batches(self):
        """Yield bags. Each bag holds paragraphs whose total words <= word_limit.

        A paragraph longer than word_limit gets its own bag (unavoidable —
        it costs ceil(words/1000) units either way).
        """
        bag_sources, bag_texts, bag_words = [], [], 0
        bag_num = 0
        for src_id, text in self._items:
            words = len(text.split())
            if bag_texts and bag_words + words > self._word_limit:
                yield self._emit(bag_num, bag_sources, bag_texts)
                bag_num += 1
                bag_sources, bag_texts, bag_words = [], [], 0
            bag_sources.append(src_id)
            bag_texts.append(text)
            bag_words += words
        if bag_texts:
            yield self._emit(bag_num, bag_sources, bag_texts)

    def _emit(self, bag_num, sources, texts):
        combined = self._sep.join(texts)
        offsets = []
        pos = 0
        for i, t in enumerate(texts):
            offsets.append({"source": sources[i], "start": pos, "end": pos + len(t)})
            pos += len(t) + len(self._sep)
        return {
            "id": f"bag-{bag_num}",
            "text": combined,
            "sources": list(sources),
            "offsets": offsets,
            "units": billable_units(combined),
        }


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
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--text", help="file to analyze, or - for stdin")
    g.add_argument("--bulk", help="JSON file of items [{id, text}, ...]")
    g.add_argument("--check", action="store_true",
                   help="verify key and endpoint without submitting a document")
    ap.add_argument("--api-key", help="Pangram key (or set PANGRAM_API_KEY)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--json", action="store_true",
                    help="emit the raw response (feeds pangram_report.py)")
    a = ap.parse_args()

    try:
        key = resolve_key(a.api_key)
    except PangramError as e:
        sys.exit(str(e))

    if a.check:
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

    if a.bulk:
        items = json.load(open(a.bulk, encoding="utf-8"))
        try:
            results = analyze_bulk(items, key, timeout=a.timeout)
        except PangramError as e:
            sys.exit(str(e))
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if not a.text:
        sys.exit("--text <file>|- or --bulk <file> is required (or use --check)")
    text = sys.stdin.read() if a.text == "-" else open(a.text, encoding="utf-8").read()

    try:
        body = analyze(text, key, timeout=a.timeout)
    except PangramError as e:
        sys.exit(str(e))

    print(json.dumps(body, indent=2, ensure_ascii=False) if a.json
          else summarize(body))


if __name__ == "__main__":
    main()
