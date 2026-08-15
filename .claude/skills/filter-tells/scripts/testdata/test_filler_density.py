#!/usr/bin/env python3
"""Tests for the conversational-filler density gate (GH-233).

The gate exists because a rewrite that escapes corporate vocabulary can land in
chatty filler and pass every other check. It is a RATE, not a denylist: "just"
and "actually" are ordinary English and the author's own prose carries them, so
the tests here pin both sides of the boundary. A denylist would have made the
low-rate cases fail too, which is the failure this design avoids.

Measured reference points, per 500 words:
  hand-edited originals   0.3 and 0.2
  their machine rewrites  2.8 and 6.8
  this repository's own documentation, 17 files   0.0 to 1.7

Run: python3 <skill>/scripts/testdata/test_filler_density.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SCAN = os.path.normpath(os.path.join(HERE, "..", "detect-lexical.sh"))
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "scripts"))
sys.path.insert(0, SHARED)
import register_markers as rm  # noqa: E402

# Deliberately dull, and checked against every other category in the scanner:
# this padding must contribute no findings of its own, or an exit-code
# assertion would be measuring the wrong thing.
PAD = ("The node sends a frame to the peer and the peer returns a receipt. "
       "The scheduler assigns one slot per node in each frame. ")
PAD_WORDS = len(PAD.split())

FILLER_SENTENCE = "You just point it at the work. "


def doc(words, filler_hits):
    """A document of about `words` words carrying exactly `filler_hits` filler."""
    body = FILLER_SENTENCE * filler_hits
    pad_needed = max(0, words - len(body.split()))
    body += PAD * (pad_needed // PAD_WORDS + 1)
    return "# Heading\n\n" + body + "\n"


def scan(text, env_extra=None):
    """(exit_code, stdout, density) for one scan of `text`."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "sample.md")
        open(p, "w").write(text)
        r = subprocess.run(["bash", SCAN, p], capture_output=True, text=True,
                           env=env)
    m = re.search(r"Conversational-filler density: ([\d.]+)/500w", r.stdout)
    return r.returncode, r.stdout, (float(m.group(1)) if m else None)


def scan_json(text):
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "sample.md")
        open(p, "w").write(text)
        r = subprocess.run(["bash", SCAN, p, "--json"], capture_output=True,
                           text=True)
    data = json.loads(r.stdout)
    rows = data if isinstance(data, list) else data.get("results", data)
    return r.returncode, rows


def test_padding_is_itself_clean():
    """Guards every other assertion in this file."""
    code, out, density = scan(doc(600, 0))
    assert density == 0.0, out
    assert code == 0, out


def test_measured_original_rate_does_not_fire():
    """0.25 per 500w — the rate the hand-edited articles actually sat at."""
    code, out, density = scan(doc(2000, 1))
    assert density is not None and density < 1.0, density
    assert code == 0, out


def test_essay_register_does_not_fail_the_scan():
    """The calibration that refused an absolute threshold.

    The reference venue-voice corpus runs 2.1 to 15.6 filler per 500 words in
    published human essays — Dan Luu, Evans, Krugman, Rands, Yegge. Those are
    the anchors a punchy rewrite is steering toward, so a scan that fails them
    is telling the operator the target register is the defect.
    """
    for hits in (6, 14, 30):          # roughly 3, 7, and 15 per 500w
        code, out, density = scan(doc(1000, hits))
        assert density > 2.0, density
        assert code == 0, (density, out)
        assert "advisory" in out, out


def test_density_is_reported_even_though_it_does_not_fail():
    """Advisory does not mean silent: a rewrite pass needs the number."""
    _c, rows = scan_json(doc(1000, 14))
    hits = [r for r in rows
            if r.get("category") == "conversational-filler-density"]
    assert len(hits) == 1, rows
    assert hits[0].get("severity") == "candidate", hits
    assert "advisory" in hits[0]["text"]


def test_occurrences_are_counted_not_lines():
    """A markdown paragraph is one long line.

    `grep -c` counts matching LINES, so ten "just" in a single paragraph would
    score as one and the gate would miss exactly the documents it is for.
    """
    one_line = "# H\n\n" + ("You just do it, " * 10) + "and that is all.\n"
    _code, _out, density = scan(one_line)
    words = len(one_line.split())
    # 10 hits, not 1: at ~35 words that is a very high rate either way, so
    # compare against the arithmetic rather than a magic number.
    assert abs(density - 10 / words * 500) < 0.6, (density, words)


def test_gate_is_opt_in_by_threshold():
    """Absolute gating is available for someone who knows the register they want,
    and off until they say so."""
    text = doc(1000, 6)                      # about 3 per 500w
    assert scan(text)[0] == 0                # advisory by default
    code, out, _d = scan(text, {"FILLER_DENSITY_MAX": "2.0"})
    assert code == 1, out
    assert "exceeds 2.0" in out or "flag above 2.0" in out
    code_high, out_high, _d = scan(text, {"FILLER_DENSITY_MAX": "9.0"})
    assert code_high == 0, out_high


def test_existing_categories_are_unaffected():
    """The new category must not change what the old ones report."""
    text = "# H\n\nWe leverage a robust and seamless approach here. " + PAD + "\n"
    _code, rows = scan_json(text)
    assert [r for r in rows if r.get("category") == "banned-word"], rows
    # The advisory density row is always emitted; what must not appear is a
    # filler finding that FAILS the scan.
    hard = [r for r in rows
            if r.get("category") == "conversational-filler-density"
            and r.get("severity") != "candidate"]
    assert not hard, rows


def test_filler_words_are_listed_as_candidates():
    """Advisory listing, so a rewrite pass knows what to starve out."""
    _code, rows = scan_json(doc(1000, 6))
    listed = [r for r in rows if r.get("category") == "conversational-filler"]
    assert listed, rows
    assert all(r.get("severity") == "candidate" for r in listed), listed


# --- the reporter half -------------------------------------------------------

def test_reporter_counts_filler():
    m = rm.markers("You just point it at the work and it actually works.")
    assert m["counts"]["filler"] == 2, m["counts"]
    assert m["filler_per_500"] > 0


def _at(rate_per_500):
    """A markers dict sitting at a chosen filler rate, for the movement tests."""
    words = 1000
    hits = round(rate_per_500 * words / 500)
    return rm.markers(("just " * hits) + " ".join(["word"] * (words - hits)))


def test_the_measured_regression_is_caught():
    """0.3 -> 2.8 and 0.2 -> 6.8, the two rewrites that prompted the check."""
    assert rm.filler_regressed(_at(0.3), _at(2.8)) is True
    assert rm.filler_regressed(_at(0.2), _at(6.8)) is True


def test_an_already_chatty_essay_is_not_a_regression():
    """Dan Luu at 3.8 edited to 4.0 has not degraded. This is the case an
    absolute threshold gets wrong and movement gets right."""
    assert rm.filler_regressed(_at(3.8), _at(4.0)) is False
    assert rm.filler_regressed(_at(8.1), _at(7.0)) is False


def test_noise_doubling_is_not_a_regression():
    """The floor: 0.1 -> 0.4 is a 4x rise on nothing."""
    assert rm.filler_regressed(_at(0.1), _at(0.4)) is False


def test_scanner_default_is_empty_so_nothing_is_gated_by_level():
    """Pins the calibration decision in the shell script itself: a future edit
    that restores an absolute default has to change this test and say why."""
    src = open(SCAN).read()
    assert 'FILLER_DENSITY_MAX="${FILLER_DENSITY_MAX:-}"' in src, \
        "detect-lexical.sh must not ship an absolute filler threshold"


def test_distance_still_uses_only_the_calibrated_four():
    """Filler is reported, not an axis: adding one would change every distance
    this function has reported, including the GH-229 figures."""
    plain = rm.markers("The orchestrator runs git, not the agents.")
    chatty = rm.markers("The orchestrator just runs git, not really the agents.")
    # The texts differ only in filler, so a four-axis distance must not move.
    assert rm.distance(plain, chatty) == 0.0, rm.distance(plain, chatty)
    assert chatty["counts"]["filler"] > plain["counts"]["filler"]


def test_zero_words_does_not_divide_by_zero():
    z = rm.markers("")
    assert z["filler_per_500"] == 0.0
    assert rm.filler_regressed(z, z) is False


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_filler_density: all assertions passed")


if __name__ == "__main__":
    main()
