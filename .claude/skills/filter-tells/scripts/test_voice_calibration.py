#!/usr/bin/env python3
"""Offline tests for the author-baseline calibration in detect-structural.py
(GH-57 sub-issue #61).

The contract under test: constructions native to the author (per
writing-voice/idiolect.yaml) flag only ABOVE the author-calibrated
ceiling; everything else, and every repository without an idiolect file,
keeps the flat thresholds byte-for-byte.
Run: python3 <skill>/scripts/test_voice_calibration.py
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location(
    "detect_structural", os.path.join(HERE, "detect-structural.py"))
ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ds)

BANK = """\
purpose: test bank
markers:
- id: colon-verdict
  regex: '\\w: +[A-Za-z"'']'
  essay_target: 5.5
- id: em-dash
  regex: '—|--'
  essay_target: 8.0
- id: antithesis-not
  regex: ', not '
  essay_target: 1.5
"""


def make_voice(tmp, bank=BANK):
    vd = os.path.join(tmp, "writing-voice")
    os.makedirs(vd, exist_ok=True)
    with open(os.path.join(vd, "idiolect.yaml"), "w") as f:
        f.write(bank)
    return vd


# ~250 words, em-dashes at the author's essay rate (2 per 250 words is
# 4.0 per 500 — over the flat strict 2.0, under the calibrated 5.2), one
# colon-verdict, varied sentence lengths, no other tells.
JOURNAL_SAMPLE = """\
The build finished at four and the report landed in the queue before anyone
had asked for it. I read the first section twice — the numbers were the same
numbers the vendor quoted in March — and then went looking for the raw log
instead of trusting the summary table. The log told a different story: the
retry counter had wrapped twice during the night window. Nobody noticed
because the dashboard averages over six hours, and a wrapped counter averaged
over six hours looks like a quiet system. We spent the morning replaying the
window at one-minute resolution. The replay showed the same wrap at the same
offset on both nodes, which ruled out the disk and pointed at the driver.
That took until lunch. After lunch the vendor call went the way vendor calls
go, and by three we had a patched driver running in the staging ring. The
staging ring held through the evening peak. I wrote the incident note the
same night while the details were still warm, because notes written the next
day describe a different incident, cleaner and shorter and more inevitable
than the one that happened. The note runs nine hundred words and names four people
who caught things the tooling missed. The tooling gets a ticket. The people
got the afternoon off, which the tooling has never once asked for. Tomorrow
we drain the queue and watch the counter with the averaging turned off, the
way it should have been watched from the start of the quarter.
"""

# Same register, one more dash pushes density to ~6 per 500 — above even
# the author ceiling of 5.2.
OVER_CEILING = JOURNAL_SAMPLE.replace(
    "and by three we had a patched driver",
    "and by three — after two false starts — we had a patched driver")

ANTITHESIS_SAMPLE = """\
The scheduler was the obvious suspect and the first two days went to it.
The problem is not the scheduler. It is the queue ahead of it. We proved
that with a replay that held the scheduler fixed while the queue depth
varied, and the latency curve followed the queue alone through every run.
The second week repeated the shape. The bottleneck is not the network.
It is the serializer. Both findings survived a second replay on the other
cluster, and both moved the fix one layer up from where the tickets had
been filed for a month. The tickets were wrong in the same direction both
times, which says something about how the dashboards partition blame. The
dashboards attribute waiting to whichever component the waiter calls next,
and that attribution is a design choice someone made a decade ago under
different traffic. Nobody has looked at it since. We filed the third
ticket against the dashboard itself and attached both replays, the queue
sweep and the serializer trace, so the next person starts one layer up.
"""


def _types(result):
    return [i["type"] for i in result["issues"]]


def test_load_calibration():
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp)
        cal = ds.load_calibration(vd)
        assert abs(cal["colon_max_per_500"] - 5.5 * 1.3 / 2) < 1e-9
        assert abs(cal["dash_max_per_500"] - 8.0 * 1.3 / 2) < 1e-9
        assert abs(cal["antithesis_max_per_1000"] - 1.95) < 1e-9
        assert cal["antithesis_target_per_1000"] == 1.5
        assert cal["source"].endswith("idiolect.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp, bank="purpose: x\nmarkers:\n- id: em-dash\n"
                                   "  regex: '—|--'\n  essay_target: 8.0\n")
        cal = ds.load_calibration(vd)
        assert "dash_max_per_500" in cal
        assert "colon_max_per_500" not in cal, "marker list drives the set"
    assert ds.load_calibration(None) is None
    with tempfile.TemporaryDirectory() as tmp:
        assert ds.load_calibration(tmp) is None, "no idiolect.yaml -> None"
    print("  load_calibration: ok")


def test_flat_behavior_unchanged_without_calibration():
    r = ds.analyze(JOURNAL_SAMPLE, "strict")
    assert "dash-heavy" in _types(r), \
        "author-rate dashes must flag under the flat strict threshold"
    r2 = ds.analyze(JOURNAL_SAMPLE, "strict", calibration=None)
    assert _types(r) == _types(r2), "calibration=None must change nothing"
    print("  flat_behavior_unchanged_without_calibration: ok")


def test_journal_register_must_not_flag_calibrated():
    with tempfile.TemporaryDirectory() as tmp:
        cal = ds.load_calibration(make_voice(tmp))
    r = ds.analyze(JOURNAL_SAMPLE, "strict", calibration=cal)
    assert "dash-heavy" not in _types(r), \
        "author-rate dashes must NOT flag above the calibrated ceiling"
    assert "colon-heavy" not in _types(r)
    print("  journal_register_must_not_flag_calibrated: ok")


def test_above_ceiling_still_flags_with_annotation():
    with tempfile.TemporaryDirectory() as tmp:
        cal = ds.load_calibration(make_voice(tmp))
    r = ds.analyze(OVER_CEILING, "strict", calibration=cal)
    dash = [i for i in r["issues"] if i["type"] == "dash-heavy"]
    assert dash, "above the author ceiling must still flag"
    assert dash[0]["calibration"] == "author-ceiling"
    assert "author-calibrated ceiling" in dash[0]["detail"]
    assert "not to zero" in dash[0]["detail"]
    print("  above_ceiling_still_flags_with_annotation: ok")


def test_antithesis_reduce_toward_target():
    flat = ds.analyze(ANTITHESIS_SAMPLE, "strict")
    assert any(t.startswith("antithesis") for t in _types(flat)), \
        "fixture must trip the flat antithesis gate"
    with tempfile.TemporaryDirectory() as tmp:
        cal = ds.load_calibration(make_voice(tmp))
    r = ds.analyze(ANTITHESIS_SAMPLE, "strict", calibration=cal)
    summary = [i for i in r["issues"]
               if i["type"] == "antithesis-over-ceiling"]
    assert summary, "calibrated antithesis flag needs the summary issue"
    assert "Reduce toward" in summary[0]["detail"]
    assert "not to zero" in summary[0]["detail"]
    pairs = [i for i in r["issues"] if i["type"].startswith("antithesis-")
             and i["type"] != "antithesis-over-ceiling"]
    assert pairs and all(i.get("calibration") == "author-ceiling"
                         for i in pairs)
    print("  antithesis_reduce_toward_target: ok")


def test_calibration_never_lowers_flat_threshold():
    tiny = ("purpose: x\nmarkers:\n- id: colon-verdict\n"
            "  regex: '\\w: +[A-Za-z]'\n  essay_target: 0.5\n")
    with tempfile.TemporaryDirectory() as tmp:
        cal = ds.load_calibration(make_voice(tmp, bank=tiny))
    # Ceiling 0.325/500 sits below the flat strict 3.0; the flat wins.
    text = JOURNAL_SAMPLE  # colon density ~2.0/500, under flat
    r = ds.analyze(text, "strict", calibration=cal)
    assert "colon-heavy" not in _types(r), \
        "a low author ceiling must never make the check stricter than flat"
    print("  calibration_never_lowers_flat_threshold: ok")


def test_cli_discovery_and_opt_out():
    script = os.path.join(HERE, "detect-structural.py")
    with tempfile.TemporaryDirectory() as tmp:
        make_voice(tmp)
        draft = os.path.join(tmp, "draft.md")
        with open(draft, "w", encoding="utf-8") as f:
            f.write(JOURNAL_SAMPLE)
        r = subprocess.run([sys.executable, script, draft],
                           capture_output=True, text=True)
        assert "Calibration: author baseline" in r.stdout
        assert "dash-heavy" not in r.stdout
        r2 = subprocess.run([sys.executable, script, draft,
                             "--no-voice-calibration"],
                            capture_output=True, text=True)
        assert "Calibration:" not in r2.stdout
        assert "dash-heavy" in r2.stdout
    print("  cli_discovery_and_opt_out: ok")


def main():
    test_load_calibration()
    test_flat_behavior_unchanged_without_calibration()
    test_journal_register_must_not_flag_calibrated()
    test_above_ceiling_still_flags_with_annotation()
    test_antithesis_reduce_toward_target()
    test_calibration_never_lowers_flat_threshold()
    test_cli_discovery_and_opt_out()
    print("test_voice_calibration: all assertions passed")


if __name__ == "__main__":
    main()
