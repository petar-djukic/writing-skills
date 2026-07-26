#!/usr/bin/env python3
"""Tests for ledger.py — arm parsing and ledger round-trip.

Run: python3 testdata/test_ledger.py
"""
import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import ledger  # noqa: E402


def test_parse_arm():
    # role=venue-voice
    assert ledger.parse_arm("role=venue-voice") == {"role": "venue-voice"}
    assert ledger.parse_arm("role=author-voice") == {"role": "author-voice"}
    assert ledger.parse_arm("  role = venue-voice  ") == {"role": "venue-voice"}

    # pre_ai=true/false
    assert ledger.parse_arm("pre_ai=true") == {"pre_ai": True}
    assert ledger.parse_arm("pre_ai=false") == {"pre_ai": False}
    assert ledger.parse_arm("pre_ai=True") == {"pre_ai": True}
    assert ledger.parse_arm("pre_ai=1") == {"pre_ai": True}
    assert ledger.parse_arm("pre_ai=0") == {"pre_ai": False}
    assert ledger.parse_arm("pre_ai=yes") == {"pre_ai": True}

    # tags~value
    assert ledger.parse_arm("tags~clipped") == {"tags": ["clipped"]}
    assert ledger.parse_arm("tags~clipped,economics") == {"tags": ["clipped", "economics"]}
    assert ledger.parse_arm("tags~a, b, c") == {"tags": ["a", "b", "c"]}

    print("  parse_arm: 12 cases passed")


def test_parse_arm_errors():
    errors = 0
    for bad in ("", "garbage", "unknown=x", "role~venue", "pre_ai~true",
                "tags=clipped", "role=invalid", "pre_ai=maybe", "tags~"):
        try:
            ledger.parse_arm(bad)
            print(f"  FAIL: {bad!r} should have raised ValueError")
            errors += 1
        except ValueError:
            pass
    assert errors == 0, f"{errors} invalid expressions did not raise"
    print("  parse_arm errors: 9 cases correctly rejected")


def test_parse_arms():
    exprs = ["role=venue-voice", "tags~clipped", "pre_ai=true"]
    got = ledger.parse_arms(exprs)
    assert len(got) == 3
    assert got[0] == ("role=venue-voice", {"role": "venue-voice"})
    assert got[1] == ("tags~clipped", {"tags": ["clipped"]})
    assert got[2] == ("pre_ai=true", {"pre_ai": True})
    print("  parse_arms: passed")


def test_ledger_roundtrip():
    tmp = tempfile.mkdtemp(prefix="test-ledger-")
    try:
        path = os.path.join(tmp, "ledger.yaml")

        # Write
        lg = ledger.Ledger(path)
        lg.append(ledger.Trial(
            article="article-a.md",
            arm="role=venue-voice",
            model="gemma4:12b",
            dry_run=False,
            anchor_count=15,
            pool_size=42,
            register_markers={"passive_per_1k": 2.1, "filler_per_500": 0.8},
            structural_metrics={"sentence_length_std": 9.2, "dash_density_per_500w": 1.4},
            detector_result=None,
        ))
        lg.append(ledger.Trial(
            article="article-a.md",
            arm="tags~clipped",
            model="gemma4:12b",
            dry_run=False,
            anchor_count=9,
            pool_size=21,
            register_markers={"passive_per_1k": 1.5, "filler_per_500": 3.2},
            structural_metrics={"sentence_length_std": 7.8},
            detector_result=23.5,
        ))
        lg.save()

        # Read back
        lg2 = ledger.Ledger.load(path)
        assert len(lg2.trials) == 2

        t0 = lg2.trials[0]
        assert t0.article == "article-a.md"
        assert t0.arm == "role=venue-voice"
        assert t0.model == "gemma4:12b"
        assert t0.dry_run is False
        assert t0.anchor_count == 15
        assert t0.pool_size == 42
        assert t0.register_markers["passive_per_1k"] == 2.1
        assert t0.register_markers["filler_per_500"] == 0.8
        assert t0.structural_metrics["sentence_length_std"] == 9.2
        assert t0.detector_result is None

        t1 = lg2.trials[1]
        assert t1.arm == "tags~clipped"
        assert t1.detector_result == 23.5

        # Append preserves prior entries
        lg2.append(ledger.Trial(
            article="article-b.md", arm="pre_ai=true", dry_run=True,
            anchor_count=6, pool_size=28))
        lg2.save()
        lg3 = ledger.Ledger.load(path)
        assert len(lg3.trials) == 3
        assert lg3.trials[2].article == "article-b.md"
        assert lg3.trials[2].dry_run is True

        print("  ledger round-trip: passed (write, read, append, re-read)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ledger_queries():
    lg = ledger.Ledger()
    lg.append(ledger.Trial(article="a.md", arm="role=venue-voice"))
    lg.append(ledger.Trial(article="a.md", arm="tags~clipped"))
    lg.append(ledger.Trial(article="b.md", arm="role=venue-voice"))

    assert lg.arms() == ["role=venue-voice", "tags~clipped"]
    assert lg.articles() == ["a.md", "b.md"]
    assert len(lg.trials_for_arm("role=venue-voice")) == 2
    assert len(lg.trials_for_article("a.md")) == 2
    print("  ledger queries: passed")


def test_update_detector():
    lg = ledger.Ledger()
    lg.append(ledger.Trial(article="a.md", arm="tags~clipped"))
    lg.append(ledger.Trial(article="a.md", arm="role=venue-voice"))

    lg.update_detector("a.md", "tags~clipped", 17.3)
    assert lg.trials[0].detector_result == 17.3
    assert lg.trials[1].detector_result is None
    print("  update_detector: passed")


def test_load_missing_file():
    lg = ledger.Ledger.load("/nonexistent/path/ledger.yaml")
    assert len(lg.trials) == 0
    print("  load missing file: passed (returns empty ledger)")


def test_tightened_field():
    """The tightened flag round-trips through the ledger."""
    tmp = tempfile.mkdtemp(prefix="test-tightened-")
    try:
        path = os.path.join(tmp, "ledger.yaml")
        lg = ledger.Ledger(path)

        lg.append(ledger.Trial(article="a.md", arm="arm-a", model="test",
                               tightened=True))
        lg.append(ledger.Trial(article="b.md", arm="arm-b", model="test",
                               tightened=False))
        lg.append(ledger.Trial(article="c.md", arm="arm-c", model="test"))
        lg.save()

        lg2 = ledger.Ledger.load(path)
        assert lg2.trials[0].tightened is True
        assert lg2.trials[1].tightened is False
        assert lg2.trials[2].tightened is False

        d = lg2.trials[0].to_dict()
        assert d["tightened"] is True
        d2 = lg2.trials[1].to_dict()
        assert "tightened" not in d2, "False tightened should be omitted"

        print("  tightened field: passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_parse_arm()
    test_parse_arm_errors()
    test_parse_arms()
    test_ledger_roundtrip()
    test_ledger_queries()
    test_update_detector()
    test_load_missing_file()
    test_tightened_field()
    print("test_ledger: all assertions passed")


if __name__ == "__main__":
    main()
