#!/usr/bin/env python3
"""Offline tests for pangram.py. Run: python3 testdata/test_pangram.py

No network, no API key, no credits. Every HTTP call is stubbed, so the suite
stays runnable by anyone — which matters because the real API costs money per
call and the free tier is 4 scans a day.

Fixtures are transcribed from the documented examples at
https://docs.pangram.com/api-reference/ai-detection.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pangram as pg  # noqa: E402

SUCCESS = json.load(open(os.path.join(HERE, "pangram_success.json")))
FAILED = json.load(open(os.path.join(HERE, "pangram_failed.json")))


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
    finally:
        pg._request = orig

    print("test_pangram: all assertions passed (no network, no key)")


if __name__ == "__main__":
    main()
