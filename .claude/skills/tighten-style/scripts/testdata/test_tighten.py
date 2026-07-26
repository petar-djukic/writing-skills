#!/usr/bin/env python3
"""Offline tests for tighten.py. Run: python3 testdata/test_tighten.py

The Ollama client is stubbed — no server, no key, no credits. What these pin
is the driver's behaviour around the model: pairs-only prompts, the verify
gate deciding what gets spliced, and the no-fallback rule.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import tighten as tn  # noqa: E402

WORDY = ("It is important to note that the cache possesses the ability to "
         "expire entries early, owing to the fact that memory is limited on "
         "the smaller machines that run the nightly benchmark suite.")
ARTICLE = f"# Title\n\n{WORDY}\n\nShort one.\n"


def run_main(argv, stub):
    """Run tighten.main() with argv and a stubbed generate()."""
    sys.path.insert(0, tn.MATCH_VOICE)
    import rewrite as rw
    old_gen, old_check = rw.generate, rw.check_server
    rw.generate = stub
    rw.check_server = lambda e, m: (True, "stubbed server")
    old_argv = sys.argv
    sys.argv = ["tighten.py"] + argv
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            try:
                tn.main()
            except SystemExit as e:
                if e.code not in (0, None):
                    raise
    finally:
        rw.generate, rw.check_server = old_gen, old_check
        sys.argv = old_argv
    return buf.getvalue()


def main():
    tmp = tempfile.mkdtemp(prefix="test-tighten-")
    try:
        art = os.path.join(tmp, "a.md")
        with open(art, "w") as f:
            f.write(ARTICLE)

        # 1. The prompt the model sees carries pairs and the paragraph — and
        #    no rule prose. This is the entire point of the redesign.
        prompts = []

        def capture(prompt, **kw):
            prompts.append(prompt)
            return "The cache can expire entries early because memory is limited."

        out = run_main(["--article", art, "--out", os.path.join(tmp, "o.md")],
                       capture)
        assert prompts, "the model was never called"
        p = prompts[0]
        assert "INSTEAD OF:" in p and "WRITE:" in p, "pairs missing from prompt"
        assert "TS-" not in p, "rule ids reached the prompt"
        assert "active voice" not in p.lower(), "rule prose reached the prompt"
        assert WORDY in p, "the paragraph itself must be in the prompt"

        # 2. A verify-clean candidate is spliced; the short paragraph is
        #    skipped, not sent to the model.
        tight = open(os.path.join(tmp, "o.md")).read()
        assert "The cache can expire entries early" in tight
        assert "Short one." in tight, "short paragraph must survive untouched"
        assert len(prompts) == 1, "short paragraph must not reach the model"

        # 3. A candidate that BREAKS a number fails the gate and the original
        #    stays. The gate is what makes compression safe.
        def breaks_numbers(prompt, **kw):
            return "The cache expires entries early because memory is tiny."
        art2 = os.path.join(tmp, "b.md")
        with open(art2, "w") as f:
            f.write("# T\n\nThe benchmark ran 4096 iterations across 12 nodes "
                    "and the cache held 512 entries for the whole run.\n")
        run_main(["--article", art2, "--out", os.path.join(tmp, "o2.md"),
                  "--retries", "0"], breaks_numbers)
        kept = open(os.path.join(tmp, "o2.md")).read()
        assert "4096" in kept and "512" in kept, "gate must keep the original"
        assert "tiny" not in kept

        # 4. Transport failure mid-run: stop, keep originals, never fall back.
        calls = {"n": 0}

        def dies(prompt, **kw):
            calls["n"] += 1
            raise RuntimeError("server gone")
        art3 = os.path.join(tmp, "c.md")
        with open(art3, "w") as f:
            f.write("# T\n\n" + WORDY + "\n\n" + WORDY.replace("cache", "queue") + "\n")
        buf_err = io.StringIO()
        with contextlib.redirect_stderr(buf_err):
            run_main(["--article", art3, "--out", os.path.join(tmp, "o3.md"),
                      "--retries", "0"], dies)
        assert calls["n"] == 1, "must stop after the first transport failure"
        kept = open(os.path.join(tmp, "o3.md")).read()
        assert WORDY in kept, "originals must survive an aborted run"

        # 5. --check-only never touches the model.
        def forbidden(prompt, **kw):
            raise AssertionError("model called in --check-only")
        out = run_main(["--article", art, "--check-only"], forbidden)
        assert "L" in out, out

        # 6. _sentence_stats computes mean and stdev correctly.
        text = "The quick brown fox jumps over the lazy dog. A short one."
        mean, sd = tn._sentence_stats(text)
        assert abs(mean - 6.0) < 0.01, f"mean={mean}"
        assert sd > 0, f"sd={sd}"
        m2, s2 = tn._sentence_stats("")
        assert m2 == 0.0 and s2 == 0.0

        # 7. --sent-floor reverts candidates that push below the floor.
        #    Stub returns a very short rewrite — floor should revert it.
        def shorten(prompt, **kw):
            return "Cache expires early."

        art4 = os.path.join(tmp, "d.md")
        long_para = ("The distributed scheduling algorithm coordinates "
                     "independent nodes across the network by exchanging "
                     "short control messages at regular intervals. "
                     "Each node maintains a local view of available "
                     "capacity and makes autonomous decisions about "
                     "which tasks to accept based on current load.")
        with open(art4, "w") as f:
            f.write(f"# T\n\n{long_para}\n")

        out4 = os.path.join(tmp, "o4.md")
        out_txt = run_main(["--article", art4, "--out", out4,
                            "--sent-floor", "20", "10", "--retries", "0"],
                           shorten)
        result = open(out4).read()
        assert "distributed scheduling" in result, (
            "floor should revert the too-short candidate")
        assert "reverted-floor" in out_txt or "Cache expires" not in result

        print("test_tighten: all assertions passed (no server)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
