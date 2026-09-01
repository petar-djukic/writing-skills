#!/usr/bin/env python3
"""Tests for standing Pangram consent (GH-210): grant discovery, env
precedence, and the should_score decision table — including the rule that
a venue whose gates omit pangram never uploads, grant or no grant."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import pangram


def _clear_env():
    os.environ.pop("PANGRAM_CONSENT", None)


def test_no_grant_by_default():
    _clear_env()
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "a.md")
        open(art, "w").write("x\n")
        granted, source = pangram.standing_consent(art)
        assert granted is False and source is None
    print("  no_grant_by_default: ok")


def test_file_grant_and_revoke():
    _clear_env()
    with tempfile.TemporaryDirectory() as tmp:
        vd = os.path.join(tmp, "writing-voice")
        os.makedirs(vd)
        sub = os.path.join(tmp, "articles")
        os.makedirs(sub)
        art = os.path.join(sub, "a.md")
        open(art, "w").write("x\n")
        cf = os.path.join(vd, pangram.CONSENT_FILE)
        open(cf, "w").write("# operator grant\nconsent: standing\ngranted: 2026-09-01\n")
        granted, source = pangram.standing_consent(art)
        assert granted is True and source == cf, (granted, source)
        open(cf, "w").write("consent: revoked\n")
        granted, source = pangram.standing_consent(art)
        assert granted is False and source == cf
    print("  file_grant_and_revoke: ok")


def test_env_precedence():
    with tempfile.TemporaryDirectory() as tmp:
        vd = os.path.join(tmp, "writing-voice")
        os.makedirs(vd)
        art = os.path.join(tmp, "a.md")
        open(art, "w").write("x\n")
        open(os.path.join(vd, pangram.CONSENT_FILE), "w").write("consent: standing\n")
        os.environ["PANGRAM_CONSENT"] = "off"
        granted, source = pangram.standing_consent(art)
        assert granted is False and "env" in source
        os.environ["PANGRAM_CONSENT"] = "standing"
        granted, source = pangram.standing_consent(art)
        assert granted is True and "env" in source
        _clear_env()
    print("  env_precedence: ok")


def test_should_score_table():
    _clear_env()
    with tempfile.TemporaryDirectory() as tmp:
        vd = os.path.join(tmp, "writing-voice")
        os.makedirs(vd)
        art = os.path.join(tmp, "a.md")
        open(art, "w").write("x\n")

        # no grant, no flags -> no scoring (unchanged behaviour)
        score, _ = pangram.should_score(start_path=art)
        assert score is False
        # explicit --pangram still works without a grant
        score, why = pangram.should_score(start_path=art, cli_pangram=True)
        assert score is True and "per-run" in why

        open(os.path.join(vd, pangram.CONSENT_FILE), "w").write("consent: standing\n")
        # grant -> scoring on by default
        score, why = pangram.should_score(start_path=art)
        assert score is True and "standing" in why
        # --no-pangram opts a run out of the grant
        score, _ = pangram.should_score(start_path=art, cli_no_pangram=True)
        assert score is False
        # a venue without the pangram gate never uploads, grant or no grant,
        # even over an explicit --pangram
        for kwargs in ({}, {"cli_pangram": True}):
            score, why = pangram.should_score(
                start_path=art, venue_gates=["register-composite"], **kwargs)
            assert score is False and "venue" in why, (score, why, kwargs)
        # a venue WITH the gate defers to the grant/flags
        score, _ = pangram.should_score(start_path=art, venue_gates=["pangram"])
        assert score is True
    print("  should_score_table: ok")


if __name__ == "__main__":
    test_no_grant_by_default()
    test_file_grant_and_revoke()
    test_env_precedence()
    test_should_score_table()
    print("all pangram-consent tests passed")
