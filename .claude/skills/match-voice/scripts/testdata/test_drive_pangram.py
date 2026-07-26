#!/usr/bin/env python3
"""Offline tests for the driver's external-check wiring (GH-212).

No network, no API key, no credits: every subprocess call is stubbed. What is
asserted here is the ordering and the failure behaviour, because both are the
reason the measurement moved into the driver — a baseline captured after the
rewrite is not a baseline, and a detector outage must not cost anyone a
rewrite run.

Run: python3 <skill>/scripts/testdata/test_drive_pangram.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive  # noqa: E402


class Stub:
    """Replays scripted (returncode, stdout, stderr) triples for drive.run."""

    class R:
        def __init__(self, rc, out, err):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        rc, out, err = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return self.R(rc, out, err)


def flag(cmd, name):
    """The value following a flag, or None when the flag is absent."""
    return cmd[cmd.index(name) + 1] if name in cmd else None


def main():
    orig = drive.run
    work = tempfile.mkdtemp(prefix="test-drive-pangram-")
    try:
        # 1. Happy path: payload then scan, response written, spans derived from
        #    the payload path rather than guessed.
        drive.run = Stub((0, "payload: ok\n", ""), (0, '{"fraction_ai": 0.7}', ""))
        got = drive.pangram_scan("/tmp/article.md", work, "before")
        assert got is not None, "a clean payload + scan must return paths"
        resp, spans = got
        assert os.path.basename(resp) == "before.json"
        assert os.path.basename(spans) == "before.payload.spans.json", spans
        assert open(resp).read() == '{"fraction_ai": 0.7}', "response not saved verbatim"
        calls = drive.run.calls
        assert calls[0][2] == "payload" and flag(calls[0], "--article") == "/tmp/article.md"
        assert flag(calls[0], "--out").endswith("before.payload.txt")
        assert "--json" in calls[1], "the scan must emit JSON for the comparison"

        # 2. A payload failure never reaches the API. Spending a scan on a
        #    document we could not assemble is spending it on nothing.
        drive.run = Stub((1, "", "no prose paragraphs found"))
        assert drive.pangram_scan("/tmp/empty.md", work, "before") is None
        assert len(drive.run.calls) == 1, "must not scan after a failed payload"

        # 3. No key: pangram.py exits nonzero, and the driver returns None so the
        #    rewrite carries on. This is the normal state, not a degraded one.
        drive.run = Stub((0, "payload: ok\n", ""), (1, "", "Pangram API key required"))
        assert drive.pangram_scan("/tmp/article.md", work, "before") is None

        # 4. An empty body is a failure too — writing it would leave a response
        #    file that later reads as a successful scan of a zeroed document.
        drive.run = Stub((0, "payload: ok\n", ""), (0, "   \n", ""))
        assert drive.pangram_scan("/tmp/article.md", work, "after") is None
        assert not os.path.exists(os.path.join(work, "after.json"))

        # 5. The comparison carries BOTH span maps. The rewrite changes the text,
        #    so the draft's offsets do not index the article's payload; reusing
        #    one map would misattribute every paragraph.
        drive.run = Stub((0, "AI: 70.0% -> 15.0%   (-55.0pt)\n", ""))
        drive.pangram_delta(("before.json", "before.spans.json"),
                            ("after.json", "after.spans.json"))
        cmd = drive.run.calls[0]
        assert cmd[2] == "report"
        assert flag(cmd, "--response") == "after.json"
        assert flag(cmd, "--spans") == "after.spans.json"
        assert flag(cmd, "--baseline") == "before.json"
        assert flag(cmd, "--baseline-spans") == "before.spans.json", \
            "baseline spans must not default to the draft's"

        # 6. A failed comparison reports and returns; it does not raise into a
        #    run whose draft is already written.
        drive.run = Stub((1, "", "no such file"))
        drive.pangram_delta(("b.json", "b.spans.json"), ("a.json", "a.spans.json"))
    finally:
        drive.run = orig

    # 7. The flag exists, is opt-in, and says the upload out loud.
    import io
    import contextlib
    saved = sys.argv
    sys.argv = ["drive.py", "--help"]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            drive.main()
    except SystemExit:
        pass
    finally:
        sys.argv = saved
    help_text = buf.getvalue()
    assert "--pangram" in help_text, "the flag must be discoverable from --help"
    assert "UPLOADS" in help_text, "the help must state that the document leaves the machine"

    print("test_drive_pangram: all assertions passed (no network, no key)")


if __name__ == "__main__":
    main()
