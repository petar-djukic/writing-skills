#!/usr/bin/env python3
"""Tests for tune_anchors.py rank and verify commands.

Run: python3 testdata/test_rank_verify.py

Exercises ranking logic, blind mode, disagreement detection, and budget guard.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import ledger  # noqa: E402
import tune_anchors  # noqa: E402


def _make_ledger(tmp, trials):
    lg = ledger.Ledger()
    for t in trials:
        lg.append(t)
    path = os.path.join(tmp, "ledger.yaml")
    lg.save(path)
    return path


def test_rank_ordering():
    """Arms with lower register magnitude rank first."""
    tmp = tempfile.mkdtemp(prefix="test-rank-order-")
    try:
        path = _make_ledger(tmp, [
            ledger.Trial(article="a.md", arm="bad-arm", model="test",
                         register_markers={"passive_per_1k": 15.0,
                                           "agentive_per_1k": 5.0,
                                           "nominalization_per_1k": 60.0,
                                           "connectives_per_1k": 4.0,
                                           "filler_per_500": 5.0}),
            ledger.Trial(article="a.md", arm="good-arm", model="test",
                         register_markers={"passive_per_1k": 2.0,
                                           "agentive_per_1k": 0.5,
                                           "nominalization_per_1k": 10.0,
                                           "connectives_per_1k": 0.5,
                                           "filler_per_500": 0.2}),
            ledger.Trial(article="a.md", arm="mid-arm", model="test",
                         register_markers={"passive_per_1k": 8.0,
                                           "agentive_per_1k": 2.0,
                                           "nominalization_per_1k": 30.0,
                                           "connectives_per_1k": 2.0,
                                           "filler_per_500": 1.5}),
        ])

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            blind = False
        with redirect_stdout(buf):
            tune_anchors.cmd_rank(FakeArgs())

        output = buf.getvalue()
        lines = [l.strip() for l in output.split("\n") if l.strip().startswith(("1.", "2.", "3."))]
        assert len(lines) == 3
        assert "good-arm" in lines[0], f"good-arm should rank 1st: {lines}"
        assert "mid-arm" in lines[1], f"mid-arm should rank 2nd: {lines}"
        assert "bad-arm" in lines[2], f"bad-arm should rank 3rd: {lines}"
        assert "best arm: good-arm" in output
        print("  rank ordering: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rank_blind_mode():
    """Blind mode hides arm labels, shows hashes, shuffles."""
    tmp = tempfile.mkdtemp(prefix="test-rank-blind-")
    try:
        path = _make_ledger(tmp, [
            ledger.Trial(article="a.md", arm="arm-alpha", model="test",
                         register_markers={"passive_per_1k": 5.0,
                                           "nominalization_per_1k": 20.0}),
            ledger.Trial(article="a.md", arm="arm-beta", model="test",
                         register_markers={"passive_per_1k": 3.0,
                                           "nominalization_per_1k": 15.0}),
        ])

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            blind = True
        with redirect_stdout(buf):
            tune_anchors.cmd_rank(FakeArgs())

        output = buf.getvalue()
        assert "arm-alpha" not in output, "blind mode must not show arm labels"
        assert "arm-beta" not in output, "blind mode must not show arm labels"
        assert "best arm" not in output, "blind mode must not reveal winner"
        # Should contain hash-like labels (8 hex chars)
        import re
        hashes = re.findall(r'[0-9a-f]{8}', output)
        assert len(hashes) >= 2, f"expected hash labels in blind output: {output}"
        print("  rank blind mode: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rank_disagreement_low_distance_high_detector():
    """Flags when register distance is low but detector score is high."""
    tmp = tempfile.mkdtemp(prefix="test-rank-disagree-")
    try:
        path = _make_ledger(tmp, [
            ledger.Trial(article="a.md", arm="suspicious", model="test",
                         register_markers={"passive_per_1k": 1.0,
                                           "agentive_per_1k": 0.2,
                                           "nominalization_per_1k": 5.0,
                                           "connectives_per_1k": 0.3,
                                           "filler_per_500": 0.1},
                         detector_result=75.0),
        ])

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            blind = False
        with redirect_stdout(buf):
            tune_anchors.cmd_rank(FakeArgs())

        output = buf.getvalue()
        assert "WARNING" in output, f"expected disagreement warning: {output}"
        assert "disagree" in output.lower()
        print("  disagreement (low distance, high detector): passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rank_disagreement_high_distance_low_detector():
    """Flags when register distance is high but detector score is low."""
    tmp = tempfile.mkdtemp(prefix="test-rank-disagree2-")
    try:
        path = _make_ledger(tmp, [
            ledger.Trial(article="a.md", arm="also-suspicious", model="test",
                         register_markers={"passive_per_1k": 20.0,
                                           "agentive_per_1k": 5.0,
                                           "nominalization_per_1k": 80.0,
                                           "connectives_per_1k": 4.0,
                                           "filler_per_500": 0.5},
                         detector_result=5.0),
        ])

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            blind = False
        with redirect_stdout(buf):
            tune_anchors.cmd_rank(FakeArgs())

        output = buf.getvalue()
        assert "WARNING" in output, f"expected disagreement warning: {output}"
        print("  disagreement (high distance, low detector): passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_verify_budget_refuses():
    """Verify exits when scans needed exceed budget."""
    tmp = tempfile.mkdtemp(prefix="test-verify-budget-")
    try:
        path = _make_ledger(tmp, [
            ledger.Trial(article="a.md", arm="arm-x", model="test",
                         register_markers={"passive_per_1k": 3.0,
                                           "nominalization_per_1k": 15.0}),
            ledger.Trial(article="b.md", arm="arm-y", model="test",
                         register_markers={"passive_per_1k": 5.0,
                                           "nominalization_per_1k": 25.0}),
        ])

        class FakeArgs:
            ledger = path
            top = 5
            budget = 0
        try:
            tune_anchors.cmd_verify(FakeArgs())
            assert False, "should have exited on budget"
        except SystemExit as e:
            assert "budget" in str(e)
        print("  verify budget guard: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_verify_nothing_to_scan():
    """Verify with all results filled does nothing."""
    tmp = tempfile.mkdtemp(prefix="test-verify-nothing-")
    try:
        path = _make_ledger(tmp, [
            ledger.Trial(article="a.md", arm="arm-x", model="test",
                         register_markers={"passive_per_1k": 3.0},
                         detector_result=25.0),
        ])

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            top = 3
            budget = 10
        with redirect_stdout(buf):
            tune_anchors.cmd_verify(FakeArgs())

        assert "nothing to scan" in buf.getvalue()
        print("  verify nothing to scan: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_register_magnitude():
    """The magnitude function produces correct ordering."""
    low = tune_anchors._register_magnitude({
        "passive_per_1k": 2.0, "agentive_per_1k": 0.5,
        "nominalization_per_1k": 10.0, "connectives_per_1k": 0.5})
    high = tune_anchors._register_magnitude({
        "passive_per_1k": 15.0, "agentive_per_1k": 5.0,
        "nominalization_per_1k": 60.0, "connectives_per_1k": 4.0})
    zero = tune_anchors._register_magnitude({})

    assert zero == 0.0, f"empty markers should be zero, got {zero}"
    assert low < high, f"low markers ({low}) should be less than high ({high})"
    assert low > 0, f"non-zero markers should produce positive magnitude"
    print("  register magnitude: passed")


def test_rank_skips_dry_run_trials():
    """Dry-run trials (no register markers) are excluded from ranking."""
    tmp = tempfile.mkdtemp(prefix="test-rank-skip-dry-")
    try:
        path = _make_ledger(tmp, [
            ledger.Trial(article="a.md", arm="dry-arm", dry_run=True,
                         anchor_count=10, pool_size=20),
            ledger.Trial(article="a.md", arm="full-arm", model="test",
                         register_markers={"passive_per_1k": 3.0,
                                           "nominalization_per_1k": 15.0,
                                           "filler_per_500": 1.0}),
        ])

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()

        class FakeArgs:
            ledger = path
            blind = False
        with redirect_stdout(buf):
            tune_anchors.cmd_rank(FakeArgs())

        output = buf.getvalue()
        assert "1 arms" in output, f"should only rank 1 arm: {output}"
        assert "full-arm" in output
        assert "dry-arm" not in output
        print("  rank skips dry-run trials: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_register_magnitude()
    test_rank_ordering()
    test_rank_blind_mode()
    test_rank_disagreement_low_distance_high_detector()
    test_rank_disagreement_high_distance_low_detector()
    test_rank_skips_dry_run_trials()
    test_verify_budget_refuses()
    test_verify_nothing_to_scan()
    print("test_rank_verify: all assertions passed")


if __name__ == "__main__":
    main()
