#!/usr/bin/env python3
"""Tests for tune_anchors.py sweep (dry-run mode).

Run: python3 testdata/test_sweep.py

Exercises the dry-run path which calls voice_anchors.anchors() directly —
no Ollama, no Pangram, no cost. Uses a synthetic writing-voice corpus.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import ledger  # noqa: E402
import tune_anchors  # noqa: E402

# Same controlled corpus as voice_anchors tests
PUNCHY = (
    "Ship it. The tool runs git, not the agents, and that is the whole rule "
    "here. Agents branch when they should not. Agents merge when nobody asked. "
    "Agents lose work in ways you find out about later. Let the orchestrator "
    "run git and the entire class of problem simply goes away for good.\n\n"
    "Worktrees are cheap. Branches are cheap. Losing an afternoon of agent "
    "output because two of them raced on the same index is not cheap at all, "
    "so keep git in one place and let the agents do the work they are good at "
    "instead of fighting each other over the repository state.\n")
ACADEMIC = (
    "We evaluate the proposed scheduler under offered load and report the "
    "median latency across twenty independent runs of the experiment. The "
    "variance across runs is small enough that the median is representative "
    "of the underlying distribution for the configurations we consider here.\n\n"
    "The scheduling algorithm allocates one slot per link per frame, and we "
    "prove convergence under the stated assumptions on the arrival process. "
    "Simulation results confirm the analysis for network sizes up to sixty "
    "four nodes, with the delay bound holding in every configuration tested.\n")


def setup_corpus(tmp):
    """Create a synthetic writing-voice corpus and an article."""
    vd = os.path.join(tmp, "writing-voice")
    os.makedirs(vd)
    with open(os.path.join(vd, "punchy.md"), "w") as f:
        f.write(PUNCHY)
    with open(os.path.join(vd, "academic.md"), "w") as f:
        f.write(ACADEMIC)
    with open(os.path.join(vd, "manifest.yaml"), "w") as f:
        f.write("""exemplars:
  - id: punchy
    file: punchy.md
    role: venue-voice
    tags: [clipped, diction]
  - id: academic
    file: academic.md
    role: author-voice
""")
    # Article to sweep over (must be in or below the writing-voice parent)
    art = os.path.join(tmp, "article.md")
    with open(art, "w") as f:
        f.write("---\ntitle: Test Article\n---\n\n")
        f.write("Let the orchestrator run git, not the agents, because agents "
                "race on the index and lose work in ways you discover later. "
                "The whole class of problem goes away when one tool owns the "
                "repository state and the agents do everything else.\n\n")
        f.write("We measure latency under offered load across twenty runs of "
                "the scheduling experiment. The variance is small enough that "
                "the median represents the distribution for every configuration "
                "we tested in the simulation campaign.\n")
    return vd, art


def test_dry_run_produces_ledger():
    tmp = tempfile.mkdtemp(prefix="test-sweep-")
    try:
        vd, art = setup_corpus(tmp)
        out = os.path.join(tmp, "ledger.yaml")

        # Redirect stdout
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            tune_anchors._sweep_dry_run(
                voice_dir=vd,
                articles=[art],
                arms=[("role=venue-voice", {"role": "venue-voice"}),
                      ("tags~clipped", {"tags": ["clipped"]})],
                k=3,
                out_path=out,
            )

        # Verify ledger was written
        lg = ledger.Ledger.load(out)
        assert len(lg.trials) == 2, f"expected 2 trials, got {len(lg.trials)}"

        t0 = lg.trials[0]
        assert t0.article == "article.md"
        assert t0.arm == "role=venue-voice"
        assert t0.dry_run is True
        assert t0.anchor_count > 0, "should have selected some anchors"
        assert t0.pool_size > 0

        t1 = lg.trials[1]
        assert t1.arm == "tags~clipped"
        assert t1.dry_run is True

        # The output should mention the articles and arms
        output = buf.getvalue()
        assert "article.md" in output
        assert "role=venue-voice" in output

        print("  dry-run produces ledger: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_empty_pool_skipped():
    tmp = tempfile.mkdtemp(prefix="test-sweep-empty-")
    try:
        vd, art = setup_corpus(tmp)
        out = os.path.join(tmp, "ledger.yaml")

        import io
        from contextlib import redirect_stdout, redirect_stderr
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            tune_anchors._sweep_dry_run(
                voice_dir=vd,
                articles=[art],
                arms=[("tags~nonexistent", {"tags": ["nonexistent"]})],
                k=3,
                out_path=out,
            )

        lg = ledger.Ledger.load(out)
        assert len(lg.trials) == 0, "empty pool should produce no trial"
        assert "EMPTY POOL" in buf.getvalue()
        print("  empty pool skipped: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ledger_accumulates():
    tmp = tempfile.mkdtemp(prefix="test-sweep-accum-")
    try:
        vd, art = setup_corpus(tmp)
        out = os.path.join(tmp, "ledger.yaml")

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        # First sweep
        with redirect_stdout(buf):
            tune_anchors._sweep_dry_run(vd, [art],
                                        [("role=venue-voice", {"role": "venue-voice"})],
                                        k=3, out_path=out)
        lg = ledger.Ledger.load(out)
        assert len(lg.trials) == 1

        # Second sweep appends
        buf = io.StringIO()
        with redirect_stdout(buf):
            tune_anchors._sweep_dry_run(vd, [art],
                                        [("role=author-voice", {"role": "author-voice"})],
                                        k=3, out_path=out)
        lg = ledger.Ledger.load(out)
        assert len(lg.trials) == 2, f"expected 2, got {len(lg.trials)}"
        assert lg.trials[0].arm == "role=venue-voice"
        assert lg.trials[1].arm == "role=author-voice"
        print("  ledger accumulates across sweeps: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rank_sorts_by_distance():
    """Synthetic ledger with known markers; rank should sort by distance."""
    lg = ledger.Ledger()
    # Arm A: high passive/nominalization (farther from human)
    lg.append(ledger.Trial(
        article="a.md", arm="arm-far", model="test",
        register_markers={"passive_per_1k": 8.0, "agentive_per_1k": 2.0,
                          "nominalization_per_1k": 6.0, "connectives_per_1k": 3.0,
                          "filler_per_500": 1.0}))
    # Arm B: low passive/nominalization (closer to human)
    lg.append(ledger.Trial(
        article="a.md", arm="arm-near", model="test",
        register_markers={"passive_per_1k": 1.0, "agentive_per_1k": 0.5,
                          "nominalization_per_1k": 2.0, "connectives_per_1k": 0.5,
                          "filler_per_500": 0.3}))

    tmp = tempfile.mkdtemp(prefix="test-rank-")
    try:
        path = os.path.join(tmp, "ledger.yaml")
        lg.save(path)

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            blind = False
        with redirect_stdout(buf):
            tune_anchors.cmd_rank(FakeArgs())

        output = buf.getvalue()
        # arm-near should rank first (lower distance)
        lines = output.strip().split("\n")
        ranked = [l for l in lines if l.strip().startswith(("1.", "2."))]
        assert "arm-near" in ranked[0], f"arm-near should rank first: {ranked}"
        assert "arm-far" in ranked[1], f"arm-far should rank second: {ranked}"
        print("  rank sorts by distance: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_verify_budget_guard():
    """Verify refuses when top > budget."""
    lg = ledger.Ledger()
    lg.append(ledger.Trial(
        article="a.md", arm="arm-a", model="test",
        register_markers={"passive_per_1k": 2.0, "nominalization_per_1k": 3.0}))
    lg.append(ledger.Trial(
        article="b.md", arm="arm-b", model="test",
        register_markers={"passive_per_1k": 1.0, "nominalization_per_1k": 2.0}))

    tmp = tempfile.mkdtemp(prefix="test-verify-")
    try:
        path = os.path.join(tmp, "ledger.yaml")
        lg.save(path)

        class FakeArgs:
            ledger = path
            top = 5
            budget = 0  # cannot afford any scans
        try:
            tune_anchors.cmd_verify(FakeArgs())
            assert False, "should have exited"
        except SystemExit as e:
            assert "budget" in str(e), f"expected budget error, got: {e}"
        print("  verify budget guard: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_extract_markers():
    """_extract_markers produces flat keys matching _RANK_KEYS."""
    tmp = tempfile.mkdtemp(prefix="test-extract-")
    try:
        prose = os.path.join(tmp, "sample.md")
        with open(prose, "w") as f:
            f.write("The algorithm was evaluated under offered load. "
                    "Results are summarized by the authors. "
                    "The implementation of the optimization "
                    "provides a significant improvement over baseline.\n")

        SHARED_DIR = os.path.normpath(os.path.join(SCRIPTS, "..", "..", "..", "scripts"))
        if SHARED_DIR not in sys.path:
            sys.path.insert(0, SHARED_DIR)
        import register_markers as rm

        result = tune_anchors._extract_markers(rm, prose)

        assert "passive_per_1k" in result, f"missing passive_per_1k: {result}"
        assert "agentive_per_1k" in result
        assert "nominalization_per_1k" in result
        assert "connectives_per_1k" in result
        assert "filler_per_500" in result
        for k, v in result.items():
            assert isinstance(v, float), f"{k} should be float, got {type(v)}"

        mag = tune_anchors._register_magnitude(result)
        assert mag > 0, f"sample prose should have nonzero magnitude: {mag}"
        print(f"  extract_markers: passed (magnitude={mag})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_dry_run_produces_ledger()
    test_empty_pool_skipped()
    test_ledger_accumulates()
    test_rank_sorts_by_distance()
    test_verify_budget_guard()
    test_extract_markers()
    print("test_sweep: all assertions passed (no network, no Ollama)")


if __name__ == "__main__":
    main()
