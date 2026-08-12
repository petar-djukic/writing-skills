#!/usr/bin/env python3
"""Integration test for tune-anchors: sweep (dry-run) -> rank -> verify.

Run: python3 testdata/test_tune_anchors.py

Exercises all three commands in sequence using a synthetic corpus.
No Ollama, no Pangram key — dry-run for sweep, budget=0 for verify.
"""
import io
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import ledger  # noqa: E402
import tune_anchors  # noqa: E402

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


def setup(tmp):
    """Synthetic corpus + article."""
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
    art = os.path.join(tmp, "article.md")
    with open(art, "w") as f:
        f.write("---\ntitle: Integration Test\n---\n\n")
        f.write("Let the orchestrator manage git operations because agents "
                "race on the index and lose work in ways discovered later. "
                "One tool owns the repository state and the agents do the "
                "implementation work they are good at.\n\n")
        f.write("We measure scheduling latency under load across independent "
                "runs of the experiment and report the median as representative "
                "of the distribution for every configuration tested.\n")
    return vd, art


def main():
    tmp = tempfile.mkdtemp(prefix="test-integration-")
    try:
        vd, art = setup(tmp)
        ledger_path = os.path.join(tmp, "ledger.yaml")

        # --- Phase 1: sweep (dry-run) ---
        buf, err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            tune_anchors._sweep_dry_run(
                voice_dir=vd,
                articles=[art],
                arms=[("role=venue-voice", {"role": "venue-voice"}),
                      ("role=author-voice", {"role": "author-voice"})],
                k=3,
                out_path=ledger_path,
            )

        lg = ledger.Ledger.load(ledger_path)
        assert len(lg.trials) >= 1, f"sweep should produce trials, got {len(lg.trials)}"
        assert all(t.dry_run for t in lg.trials), "all should be dry-run"
        print(f"  phase 1 (sweep dry-run): {len(lg.trials)} trials recorded")

        # --- Phase 2: simulate full trials for ranking ---
        # Add synthetic full trials (as if sweep ran with a model)
        lg.append(ledger.Trial(
            article="article.md", arm="role=venue-voice", model="gemma4:12b",
            register_markers={"passive_per_1k": 3.0, "agentive_per_1k": 1.0,
                              "nominalization_per_1k": 20.0, "connectives_per_1k": 1.5,
                              "filler_per_500": 4.2}))
        lg.append(ledger.Trial(
            article="article.md", arm="role=author-voice", model="gemma4:12b",
            register_markers={"passive_per_1k": 5.0, "agentive_per_1k": 2.0,
                              "nominalization_per_1k": 35.0, "connectives_per_1k": 2.5,
                              "filler_per_500": 0.4}))
        lg.save(ledger_path)

        # --- Phase 3: rank ---
        buf = io.StringIO()

        class RankArgs:
            ledger = ledger_path
            blind = False
        with redirect_stdout(buf):
            tune_anchors.cmd_rank(RankArgs())

        rank_output = buf.getvalue()
        assert "2 arms" in rank_output, f"should rank 2 arms: {rank_output}"
        # venue-voice has lower passive/nom so should rank first
        lines = [l for l in rank_output.split("\n") if "1." in l]
        assert lines, "expected a ranked line"
        assert "role=venue-voice" in lines[0], \
            f"venue-voice should rank first (lower register magnitude): {lines[0]}"
        print(f"  phase 3 (rank): correct ordering")

        # --- Phase 4: verify (budget=0 should refuse) ---
        class VerifyArgs:
            ledger = ledger_path
            top = 2
            budget = 0
        try:
            tune_anchors.cmd_verify(VerifyArgs())
            assert False, "should have refused on budget"
        except SystemExit:
            pass
        print(f"  phase 4 (verify budget=0): correctly refused")

        # --- Phase 5: verify with nothing to scan ---
        lg2 = ledger.Ledger.load(ledger_path)
        for t in lg2.trials:
            if not t.dry_run:
                t.detector_result = 25.0
        lg2.save(ledger_path)

        buf = io.StringIO()

        class VerifyArgs2:
            ledger = ledger_path
            top = 2
            budget = 10
        with redirect_stdout(buf):
            tune_anchors.cmd_verify(VerifyArgs2())
        assert "nothing to scan" in buf.getvalue()
        print(f"  phase 5 (verify all filled): correctly skipped")

        print("test_tune_anchors: integration test passed (no network, no Ollama)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
