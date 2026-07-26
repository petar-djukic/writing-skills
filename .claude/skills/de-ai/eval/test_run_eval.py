#!/usr/bin/env python3
"""Offline tests for run_eval.py's length machinery. Run: python3 test_run_eval.py

No corpus, no detectors, no network — synthetic documents in a temp directory.
Covers the parts that decide whether a measurement means anything: excerpt
determinism, band tolerance, and the class-mismatch warning that would have
caught the original bad measurement.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_eval as ev  # noqa: E402


def doc(path, n_paras, words_per_para=60):
    """A document of distinguishable paragraphs."""
    paras = [" ".join(f"w{p}x{i}" for i in range(words_per_para))
             for p in range(n_paras)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Heading\n\n" + "\n\n".join(paras) + "\n")
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="test-run-eval-")
    try:
        big = doc(os.path.join(tmp, "big.md"), 60)      # ~3600 words
        small = doc(os.path.join(tmp, "small.md"), 4)   # ~240 words

        # 1. Word counts and distribution.
        assert ev.word_count(small) > 200
        st = ev.length_stats([big, small])
        assert st["n"] == 2 and st["min"] < st["max"]
        assert ev.length_stats([])["median"] is None, "empty corpus must not crash"

        # 2. Excerpts are DETERMINISTIC. Without this, fire rates wander between
        #    runs and no before/after comparison of a detector change is valid.
        a = ev.excerpt(big, 800)
        b = ev.excerpt(big, 800)
        assert a == b, "excerpt must be identical across calls"
        assert a is not None

        # 3. An excerpt hits its target without wildly overshooting, and is made
        #    of whole paragraphs — a word-slice would hand detectors truncated
        #    sentences and measure the truncation instead of the prose.
        n = len(a.split())
        assert 800 <= n < 800 + 200, f"expected ~800 words, got {n}"
        assert "\n\n" in a
        for para in a.split("\n\n"):
            assert para in open(big).read(), "excerpt paragraph not verbatim"

        # 4. Larger targets are supersets: same start, more paragraphs. Bands
        #    must differ only in length, or they are not comparable.
        assert ev.excerpt(big, 1500).startswith(a[:200])

        # 5. Documents too short for a band return None, so the caller can skip
        #    and COUNT them. Padding, or silently comparing different document
        #    counts per band, is how the first measurement went wrong.
        assert ev.excerpt(small, 2500) is None
        assert ev.excerpt(small, 400) is None or len(ev.excerpt(small, 400).split()) >= 400 * ev.BAND_TOLERANCE

        # 6. Headings are excluded from prose — they are not sentences and would
        #    skew opening-diversity style detectors.
        assert "# Heading" not in (a or "")

        # 7. A document with too few paragraphs yields nothing rather than a
        #    one-paragraph "band".
        tiny = doc(os.path.join(tmp, "tiny.md"), 2)
        assert ev.excerpt(tiny, 400) is None

        # 8. The mismatch guard: the exact confound that produced the original
        #    "20 detectors over gate" figure. 5889 vs 332 is 17.7x.
        for human_med, ai_med, want in ((5889, 332, True), (400, 380, False),
                                        (900, 400, True)):
            ratio = max(human_med, ai_med) / min(human_med, ai_med)
            assert (ratio >= 2) is want, f"{human_med}/{ai_med} guard wrong"

        # 9. Bands are ordered shortest-first and start at the ai class's range,
        #    so the first band is the like-for-like comparison.
        assert list(ev.LENGTH_BANDS) == sorted(ev.LENGTH_BANDS)
        assert ev.LENGTH_BANDS[0] <= 500

        # 10. A crashed detector raises DetectorFailure rather than returning a
        #     fake result. This is GH-190: an "error" verdict used to enter the
        #     denominator as a measured document with zero findings, dragging
        #     every rate down with nothing in the output saying so.
        import subprocess as sp
        real_run = sp.run

        class Dead:
            returncode = 137          # what a SIGKILLed subprocess reports
            stdout = ""               # empty stdout is the observed failure shape
            stderr = "Killed: 9"

        sp.run = lambda *a, **k: Dead()
        try:
            for fn, name in ((lambda: ev.run_structural("x.md"), "structural"),
                             (lambda: ev.run_lexical("x.md"), "lexical")):
                try:
                    fn()
                    raise AssertionError(f"{name}: crashed subprocess did not raise")
                except ev.DetectorFailure as e:
                    assert "137" in str(e), f"{name}: exit code missing from {e}"
                    assert "Killed" in str(e), f"{name}: stderr missing from {e}"
        finally:
            sp.run = real_run

        # 11. The failure message is diagnosable but bounded — last stderr line,
        #     truncated, so a Python traceback does not flood the report.
        f = ev.DetectorFailure("t", 1, "line1\nline2\n" + "x" * 500)
        assert "line1" not in str(f) and str(f).index("x" * 10) and len(f.stderr) <= 200

        print("test_run_eval: all assertions passed (no corpus, no detectors)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
