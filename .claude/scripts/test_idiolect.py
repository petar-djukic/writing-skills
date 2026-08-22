#!/usr/bin/env python3
"""Offline tests for idiolect.py, the shared idiolect.yaml access module
(GH-63), and for the one-implementation invariant: the three consumers
(inject-vernacular, voice-critic, detect-structural) must use these
functions, not private copies — a drifting copy changes which markers a
consumer sees, and nothing audits the drift.
Run: python3 <surface>/scripts/test_idiolect.py
"""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import idiolect  # noqa: E402

SKILLS = os.path.normpath(os.path.join(HERE, "..", "skills"))

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
- id: okay
  regex: '\\bokay\\b (case-insensitive)'
  essay_target: 0.0
- id: he-agent
  regex: '\\bhe\\b (case-insensitive; referent not machine-checkable)'
  essay_target: 1.5
substrate:
  policy: applied directly at target rates
  particles:
    table:
    - {serbian: 'zapravo / upravo', english: actually, talk: 5.8, journal: 1.7, marker: null}
  calques:
    attested:
    - {serbian: zapravo, english: 'actually (emphatic)'}
    proposed:
    - {serbian: konkretno, english: concretely}
"""


def make_voice(tmp, bank=BANK):
    vd = os.path.join(tmp, "writing-voice")
    os.makedirs(vd, exist_ok=True)
    if bank is not None:
        with open(os.path.join(vd, "idiolect.yaml"), "w") as f:
            f.write(bank)
    return vd


def test_discover_voice_dir():
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp)
        nested = os.path.join(tmp, "a", "b")
        os.makedirs(nested)
        draft = os.path.join(nested, "draft.md")
        with open(draft, "w") as f:
            f.write("x\n")
        assert idiolect.discover_voice_dir(draft) == vd
        assert idiolect.discover_voice_dir(nested) == vd
    with tempfile.TemporaryDirectory() as tmp:
        assert idiolect.discover_voice_dir(tmp) is None
    print("  discover_voice_dir: ok")


def test_load_markers():
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp)
        m = idiolect.load_markers(vd)
        assert set(m) == {"colon-verdict", "em-dash", "antithesis-not",
                          "okay", "he-agent"}
        assert m["colon-verdict"]["essay_target"] == 5.5
    assert idiolect.load_markers(None) is None
    with tempfile.TemporaryDirectory() as tmp:
        assert idiolect.load_markers(tmp) is None, "no idiolect.yaml -> None"
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp, bank="purpose: x\nmarkers: []\n")
        assert idiolect.load_markers(vd) == {}, "empty markers -> {}, not None"
    print("  load_markers: ok")


def test_compile_marker():
    rx = idiolect.compile_marker({"regex": "\\bokay\\b (case-insensitive)"})
    assert rx.search("It was OKAY today."), "annotation note must set re.I"
    rx = idiolect.compile_marker(
        {"regex": "\\bhe\\b (case-insensitive; referent not machine-checkable)"})
    assert rx.pattern == "\\bhe\\b", "everything after ' (' is annotation"
    rx = idiolect.compile_marker({"regex": ", not "})
    assert rx.flags & 2 == 0, "no annotation, no IGNORECASE"  # re.I == 2
    assert idiolect.compile_marker({"regex": "([unclosed"}) is None
    assert idiolect.compile_marker({}) is not None, \
        "missing field compiles as empty pattern; consumers gate by target"
    print("  compile_marker: ok")


def test_load_calibration():
    with tempfile.TemporaryDirectory() as tmp:
        cal = idiolect.load_calibration(make_voice(tmp))
        assert abs(cal["colon_max_per_500"] - 5.5 * 1.3 / 2) < 1e-9
        assert abs(cal["dash_max_per_500"] - 8.0 * 1.3 / 2) < 1e-9
        assert abs(cal["antithesis_max_per_1000"] - 1.95) < 1e-9
        assert cal["antithesis_target_per_1000"] == 1.5
        assert cal["source"].endswith("idiolect.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp, bank="purpose: x\nmarkers:\n- id: em-dash\n"
                                   "  regex: '—|--'\n  essay_target: 8.0\n")
        cal = idiolect.load_calibration(vd)
        assert "dash_max_per_500" in cal
        assert "colon_max_per_500" not in cal, "marker list drives the set"
    assert idiolect.load_calibration(None) is None
    with tempfile.TemporaryDirectory() as tmp:
        assert idiolect.load_calibration(tmp) is None
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp, bank=": not yaml : [\n")
        assert idiolect.load_calibration(vd) is None, \
            "malformed bank -> no calibration, not an error"
    print("  load_calibration: ok")


def test_load_substrate():
    with tempfile.TemporaryDirectory() as tmp:
        sub = idiolect.load_substrate(make_voice(tmp))
        assert sub["policy"].startswith("applied directly")
        assert sub["particles"]["table"][0]["journal"] == 1.7
        assert sub["calques"]["attested"][0]["serbian"] == "zapravo"
        assert sub["calques"]["proposed"][0]["serbian"] == "konkretno"
    assert idiolect.load_substrate(None) is None
    with tempfile.TemporaryDirectory() as tmp:
        assert idiolect.load_substrate(tmp) is None, "no idiolect.yaml -> None"
    with tempfile.TemporaryDirectory() as tmp:
        vd = make_voice(tmp, bank="purpose: x\nmarkers: []\n")
        assert idiolect.load_substrate(vd) == {}, \
            "bank without substrate -> {}, not None"
    print("  load_substrate: ok")


def _load(name, *rel):
    path = os.path.join(SKILLS, *rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_consumers_share_one_implementation():
    iv = _load("iv_gh63", "inject-vernacular", "scripts", "inject_vernacular.py")
    vc = _load("vc_gh63", "voice-critic", "scripts", "voice_critic.py")
    ds = _load("ds_gh63", "filter-tells", "scripts", "detect-structural.py")
    for mod, names in ((iv, ["discover_voice_dir", "compile_marker",
                             "load_substrate"]),
                       (vc, ["discover_voice_dir", "compile_marker",
                             "load_markers"]),
                       (ds, ["discover_voice_dir", "load_calibration"])):
        for name in names:
            assert getattr(mod, name) is getattr(idiolect, name), \
                f"{mod.__name__}.{name} is a private copy, not the shared one"
    assert iv.TOLERANCE == vc.TOLERANCE == ds.CALIBRATION_TOLERANCE \
        == idiolect.TOLERANCE
    print("  consumers_share_one_implementation: ok")


def main():
    test_discover_voice_dir()
    test_load_markers()
    test_compile_marker()
    test_load_calibration()
    test_load_substrate()
    test_consumers_share_one_implementation()
    print("test_idiolect: all assertions passed")


if __name__ == "__main__":
    main()
