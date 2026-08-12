#!/usr/bin/env python3
"""Offline tests for pangram.py. Run: python3 <surface>/scripts/test_pangram.py

No network, no API key, no credits. Every HTTP call is stubbed, so the suite
stays runnable by anyone — which matters because the real API costs money per
call.

Fixtures are transcribed from the documented examples at
https://docs.pangram.com/api-reference/ai-detection.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pangram as pg  # noqa: E402

SUCCESS = json.load(open(os.path.join(HERE, "testdata_pangram_success.json")))
FAILED = json.load(open(os.path.join(HERE, "testdata_pangram_failed.json")))


class Stub:
    """Records calls and replays scripted responses in place of _request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, path, key, payload=None, timeout=30):
        self.calls.append({"path": path, "key": key, "payload": payload})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def expect_error(fn, needle, label):
    try:
        fn()
    except pg.PangramError as e:
        assert needle.lower() in str(e).lower(), \
            f"{label}: expected {needle!r} in {str(e)!r}"
        return str(e)
    raise AssertionError(f"{label}: expected PangramError, got none")


def main():
    orig = pg._request
    try:
        # 1. Happy path: submit then poll, and the success body is returned whole.
        stub = Stub({"task_id": "abc-123"}, SUCCESS)
        pg._request = stub
        body = pg.analyze("some prose", "KEY", sleep=lambda s: None)
        assert body == SUCCESS, "success body must be passed through unchanged"
        assert stub.calls[0]["path"] == "/task"
        assert stub.calls[1]["path"] == "/task/abc-123"

        # 2. public_dashboard_link is pinned False — a public link is a second,
        #    louder disclosure than the upload itself.
        assert stub.calls[0]["payload"]["public_dashboard_link"] is False, \
            "public_dashboard_link must be pinned False"
        assert stub.calls[0]["payload"]["text"] == "some prose"

        # 3. THE bug this client exists to avoid: a failed analysis arrives as
        #    HTTP 200 with a zeroed body. Status-code-only handling reads that
        #    as a flawless human document.
        pg._request = Stub({"task_id": "x"}, FAILED)
        msg = expect_error(lambda: pg.analyze("t", "KEY", sleep=lambda s: None),
                           "no valid text", "STAGE_FAILED")
        assert "failed" in msg.lower()
        assert FAILED["fraction_ai"] == 0.0 and FAILED["fraction_human"] == 0.0, \
            "fixture must keep the zeroed body that makes this bug plausible"

        # 4. Documented status codes each produce their own actionable message.
        for code, needle in ((401, "x-api-key"), (402, "credits"),
                             (429, "rate limit"), (422, "invalid"),
                             (404, "does not exist")):
            err = urllib.error.HTTPError("u", code, "m", {}, None)
            pg._request = orig  # exercise the real handler
            saved = urllib.request.urlopen

            def boom(*a, **k):
                raise err
            urllib.request.urlopen = boom
            try:
                expect_error(lambda: pg.submit("t", "KEY"), needle, f"HTTP {code}")
            finally:
                urllib.request.urlopen = saved

        # 5. The key never leaks into an error message, even when the server
        #    echoes the request back.
        err = urllib.error.HTTPError("u", 401, "bad key SEKRET-KEY-VALUE", {}, None)
        saved = urllib.request.urlopen

        def boom401(*a, **k):
            raise err
        urllib.request.urlopen = boom401
        try:
            m = expect_error(lambda: pg.submit("t", "SEKRET-KEY-VALUE"),
                             "x-api-key", "key leak")
            assert "SEKRET-KEY-VALUE" not in m, f"key leaked into error: {m}"
        finally:
            urllib.request.urlopen = saved

        # 6. Missing key names both ways to supply one, and says to skip rather
        #    than substitute. start_path is an isolated empty directory: since
        #    GH-184 the lookup also searches .secrets/ upward, and without
        #    pinning it this assertion would pass or fail depending on what
        #    happens to sit above the checkout on a given machine.
        pg._request = orig
        os.environ.pop("PANGRAM_API_KEY", None)
        import tempfile
        with tempfile.TemporaryDirectory() as empty:
            m = expect_error(lambda: pg.resolve_key(None, start_path=empty),
                             "PANGRAM_API_KEY", "no key")
        assert "--api-key" in m and "skip" in m.lower()

        # 7. Empty text is refused locally — never spend a call to be told no.
        pg._request = Stub({"task_id": "x"})
        expect_error(lambda: pg.submit("   \n  ", "KEY"), "empty", "empty text")

        # 8. Timeout is bounded and mentions that the scan may still be billed.
        pg._request = Stub({"task_id": "x"}, {"stage": "STAGE_PREPROCESSING"})
        m = expect_error(
            lambda: pg.poll("x", "KEY", timeout=0, sleep=lambda s: None),
            "timed out", "timeout")
        assert "billed" in m.lower(), "timeout must warn the scan may be billed"

        # 9. Summary reports fractions as percentages and surfaces the stored copy.
        s = pg.summarize(SUCCESS)
        assert "70.0%" in s, f"fraction_ai 0.70 should render 70.0%:\n{s}"
        assert "Mixed" in s
        assert "pangram.com/history" in s, "must disclose where the text is stored"

        # 10. A missing-field body degrades rather than crashing.
        assert "0.0%" in pg.summarize({"stage": "STAGE_SUCCESS"})

        # --- Bulk API tests ---

        # 11. submit_bulk sends POST /bulk with items and returns the response.
        bulk_resp = {"bulk_id": "blk_1", "status": "queued", "total_items": 2,
                     "accepted_items": [
                         {"index": 0, "id": "a", "task_id": "t1"},
                         {"index": 1, "id": "b", "task_id": "t2"}],
                     "failed_items": []}
        pg._request = Stub(bulk_resp)
        r = pg.submit_bulk([{"id": "a", "text": "hello"}, {"id": "b", "text": "world"}], "KEY")
        assert r["bulk_id"] == "blk_1"
        assert pg._request.calls[0]["path"] == "/bulk"
        assert len(pg._request.calls[0]["payload"]["items"]) == 2

        # 12. submit_bulk refuses empty items.
        expect_error(lambda: pg.submit_bulk([], "KEY"), "empty", "bulk empty")

        # 13. poll_bulk polls until terminal status.
        pg._request = Stub(
            {"bulk_id": "blk_1", "status": "queued"},
            {"bulk_id": "blk_1", "status": "running"},
            {"bulk_id": "blk_1", "status": "succeeded", "total_items": 2})
        r = pg.poll_bulk("blk_1", "KEY", sleep=lambda s: None)
        assert r["status"] == "succeeded"
        assert len(pg._request.calls) == 3

        # 14. poll_bulk recognises "partial" as terminal.
        pg._request = Stub(
            {"bulk_id": "blk_1", "status": "partial", "total_items": 2})
        r = pg.poll_bulk("blk_1", "KEY", sleep=lambda s: None)
        assert r["status"] == "partial"

        # 15. poll_bulk recognises "failed" as terminal.
        pg._request = Stub(
            {"bulk_id": "blk_1", "status": "failed"})
        r = pg.poll_bulk("blk_1", "KEY", sleep=lambda s: None)
        assert r["status"] == "failed"

        # 16. poll_bulk times out with a clear message.
        pg._request = Stub({"bulk_id": "blk_1", "status": "running"})
        m = expect_error(
            lambda: pg.poll_bulk("blk_1", "KEY", timeout=0, sleep=lambda s: None),
            "timed out", "bulk timeout")
        assert "blk_1" in m

        # 17. fetch_results returns the parsed page.
        result_page = {
            "bulk_id": "blk_1", "offset": 0, "limit": 100, "total_items": 1,
            "items": [{"index": 0, "id": "a", "task_id": "t1",
                       "stage": "STAGE_SUCCESS", "error": None,
                       "result": SUCCESS}],
            "failed_items": []}
        pg._request = Stub(result_page)
        r = pg.fetch_results("blk_1", "KEY")
        assert r["items"][0]["result"] == SUCCESS
        assert "offset=0" in pg._request.calls[0]["path"]
        assert "limit=100" in pg._request.calls[0]["path"]

        # 18. analyze_bulk chains submit, poll, and fetch_results.
        pg._request = Stub(
            bulk_resp,
            {"bulk_id": "blk_1", "status": "succeeded"},
            result_page)
        results = pg.analyze_bulk(
            [{"id": "a", "text": "x"}], "KEY", sleep=lambda s: None)
        assert len(results) == 1
        assert results[0]["result"] == SUCCESS

        # 19. analyze_bulk paginates when total_items > limit.
        page1 = {"bulk_id": "blk_1", "offset": 0, "limit": 1, "total_items": 2,
                 "items": [{"index": 0, "id": "a", "result": SUCCESS}],
                 "failed_items": []}
        page2 = {"bulk_id": "blk_1", "offset": 1, "limit": 1, "total_items": 2,
                 "items": [{"index": 1, "id": "b", "result": SUCCESS}],
                 "failed_items": []}
        pg._request = Stub(bulk_resp,
                           {"bulk_id": "blk_1", "status": "succeeded"},
                           page1, page2)
        results = pg.analyze_bulk(
            [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
            "KEY", sleep=lambda s: None)
        assert len(results) == 2

        # --- WordBudgetBatcher tests ---

        # 20. Batcher packs paragraphs into bags of ~1000 words.
        batcher = pg.WordBudgetBatcher(word_limit=10)
        batcher.add("p0", "one two three")
        batcher.add("p1", "four five six")
        batcher.add("p2", "seven eight nine ten eleven")
        batches = list(batcher.batches())
        assert len(batches) == 2, f"expected 2 batches, got {len(batches)}"
        assert batches[0]["sources"] == ["p0", "p1"]
        assert batches[1]["sources"] == ["p2"]
        assert "one two three" in batches[0]["text"]
        assert "four five six" in batches[0]["text"]

        # 21. A single item larger than word_limit gets its own bag.
        batcher = pg.WordBudgetBatcher(word_limit=3)
        batcher.add("big", "a b c d e f g h i j")
        batches = list(batcher.batches())
        assert len(batches) == 1
        assert batches[0]["sources"] == ["big"]
        assert batches[0]["units"] == 1

        # 22. Empty batcher yields nothing.
        assert list(pg.WordBudgetBatcher().batches()) == []

        # 23. Offsets track character positions correctly.
        batcher = pg.WordBudgetBatcher(word_limit=100, sep="||")
        batcher.add("a", "hello")
        batcher.add("b", "world")
        batches = list(batcher.batches())
        assert len(batches) == 1
        b = batches[0]
        assert b["text"] == "hello||world"
        assert b["offsets"][0] == {"source": "a", "start": 0, "end": 5}
        assert b["offsets"][1] == {"source": "b", "start": 7, "end": 12}

        # 24. billable_units: ceil(words / 1000), min 1.
        assert pg.billable_units("one two three") == 1
        assert pg.billable_units(" ".join(["w"] * 1000)) == 1
        assert pg.billable_units(" ".join(["w"] * 1001)) == 2
        assert pg.billable_units("") == 1

    finally:
        pg._request = orig

    print("test_pangram: all assertions passed (no network, no key)")


if __name__ == "__main__":
    main()
