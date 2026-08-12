#!/usr/bin/env python3
"""Offline tests for the run-provenance manifest (GH-236).

The anchor set is what pulled a rewrite toward one register rather than another,
and it used to live only in a results.json inside a mkdtemp the OS reaps. These
tests pin the shape of the sibling manifest and the dedup, because the consumer
is a YAML front-matter block someone pastes into an article.

No network, no model. Run: python3 <skill>/scripts/testdata/test_manifest.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import drive  # noqa: E402

try:
    import yaml
except ImportError:  # the script itself is stdlib-only; the test is stricter
    yaml = None


class Args:
    def __init__(self, **kw):
        self.model = kw.get("model", "gemma4:31b-cloud")
        self.role = kw.get("role")
        self.anchor_tags = kw.get("anchor_tags")
        self.stratum = kw.get("stratum")
        self.no_anchors = kw.get("no_anchors", False)
        self.author = kw.get("author")


def results(*anchor_lists, statuses=None):
    """Result records carrying the anchor lists retrieval recorded."""
    out = []
    for i, files in enumerate(anchor_lists, 1):
        out.append({
            "n": i,
            "status": (statuses[i - 1] if statuses else "accepted-mechanical"),
            "anchors": [{"file": f, "role": "venue-voice", "score": 0.1}
                        for f in files],
        })
    return out


def write(tmp, args, res, voice_dir="/corpus/writing-voice", pangram=None):
    p = os.path.join(tmp, "article.vr-draft.generation.yaml")
    used = drive.write_manifest(p, args, voice_dir, res, pangram)
    return p, used, open(p).read()


def load(text):
    assert yaml is not None, "PyYAML needed to validate the emitted YAML"
    return yaml.safe_load(text)["match_voice"]


def test_manifest_is_valid_yaml_with_the_agreed_fields():
    with tempfile.TemporaryDirectory() as tmp:
        args = Args(role="venue-voice", anchor_tags="clipped", stratum="pre-ai")
        _p, _used, text = write(tmp, args, results(["Yegge-2011.md"]))
        m = load(text)
        assert m["model"] == "gemma4:31b-cloud"
        assert m["voice_dir"] == "/corpus/writing-voice"
        assert m["anchor_role"] == "venue-voice"
        assert m["anchor_tags"] == ["clipped"]
        assert m["stratum"] == "pre-ai"
        assert m["anchor_files"] == ["Yegge-2011.md"]


def test_anchor_files_are_deduped_across_paragraphs():
    """The run-level union is the field that matters; three paragraphs drawing
    the same exemplar is one entry."""
    with tempfile.TemporaryDirectory() as tmp:
        res = results(["A.md", "B.md"], ["B.md", "C.md"], ["A.md", "C.md"])
        _p, used, text = write(tmp, Args(), res)
        assert used == ["A.md", "B.md", "C.md"], used
        assert load(text)["anchor_files"] == ["A.md", "B.md", "C.md"]


def test_result_counts_come_from_the_statuses():
    with tempfile.TemporaryDirectory() as tmp:
        res = results(["A.md"], ["A.md"], [], [],
                      statuses=["accepted-mechanical", "kept-original",
                                "skipped-short", "rewrite-error"])
        _p, _used, text = write(tmp, Args(), res)
        assert load(text)["result"] == {"accepted": 1, "kept_original": 1,
                                        "skipped_short": 1, "rewrite_error": 1,
                                        "gate_error": 0, "unselected": 0,
                                        "excluded_key": 0}


def _pangram_dict(frac_ai=0.0, frac_human=1.0, mean_ws=0.25):
    return {"fraction_ai": frac_ai, "fraction_ai_assisted": 0.0,
            "fraction_human": frac_human, "num_ai": 0,
            "num_ai_assisted": 0, "num_human": 1,
            "mean_window_score": mean_ws, "num_windows": 1}


def test_pangram_block_records_its_scope():
    """The driver submits a prose-only payload, so these numbers will not match
    a whole-file scan. Saying so in the manifest is the point."""
    before = _pangram_dict(frac_ai=0.8, frac_human=0.2, mean_ws=0.676)
    after = _pangram_dict(frac_ai=0.1, frac_human=0.9, mean_ws=0.389)
    with tempfile.TemporaryDirectory() as tmp:
        _p, _u, text = write(tmp, Args(), results(["A.md"]),
                             pangram=(before, after))
        pg = load(text)["pangram"]
        assert pg["scope"] == "prose-only"
        assert pg["before"]["mean_window_score"] == 0.676
        assert pg["after"]["mean_window_score"] == 0.389
        assert pg["before"]["fraction_ai"] == 0.8
        assert pg["after"]["fraction_human"] == 0.9


def test_pangram_block_absent_without_the_flag():
    with tempfile.TemporaryDirectory() as tmp:
        _p, _u, text = write(tmp, Args(), results(["A.md"]))
        assert "pangram" not in load(text)


def test_no_anchors_is_an_empty_list_not_broken_yaml():
    """A run whose anchors all scored zero still emits a readable manifest."""
    with tempfile.TemporaryDirectory() as tmp:
        _p, used, text = write(tmp, Args(), results([], []))
        assert used == []
        assert load(text)["anchor_files"] == []


def test_unset_flags_are_null_not_the_string_none():
    with tempfile.TemporaryDirectory() as tmp:
        _p, _u, text = write(tmp, Args(), results(["A.md"]))
        m = load(text)
        assert m["anchor_role"] is None and m["stratum"] is None
        assert m["anchor_tags"] == []


def test_paths_with_yaml_metacharacters_survive():
    """A discovered voice_dir is an absolute path and a Windows-style or
    colon-carrying path would otherwise produce a nested mapping."""
    with tempfile.TemporaryDirectory() as tmp:
        _p, _u, text = write(tmp, Args(), results(["odd: name.md"]),
                             voice_dir="/a/b: c/writing-voice")
        m = load(text)
        assert m["voice_dir"] == "/a/b: c/writing-voice"
        assert m["anchor_files"] == ["odd: name.md"]


def test_multiple_tags_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        _p, _u, text = write(tmp, Args(anchor_tags="clipped, diction"),
                             results(["A.md"]))
        assert load(text)["anchor_tags"] == ["clipped", "diction"]


# --- end to end through main(), with every subprocess stubbed ----------------
#
# The driver's own convention (test_drive_pangram.py): replace drive.run so no
# child process executes. Doing this with a real endpoint would load a 7.6 GB
# model and rewrite paragraphs for nothing, which is not a test.

ANCHORS_JSON = json.dumps({
    "writing_voice": "/corpus/writing-voice",
    "anchors": [
        {"file": "Yegge-2011-platforms.md", "role": "venue-voice", "score": 0.11},
        {"file": "DanLuu-2019-programming.md", "role": "venue-voice", "score": 0.09},
    ],
})


class DispatchStub:
    """Answers drive.run by which script it was handed."""

    class R:
        def __init__(self, rc, out, err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if "retrieve.py" in joined:
            return self.R(0, ANCHORS_JSON if "--json" in cmd else "[Anchor 1]\ntext")
        if "rewrite.py" in joined:
            return self.R(0, "A rewritten paragraph that says the same thing.")
        if "verify.py" in joined:
            return self.R(0, '{"clean": true, "findings": []}')
        return self.R(0, "")            # detect-lexical.sh

    def ran(self, name):
        return any(name in " ".join(c) for c in self.calls)


def test_end_to_end_writes_the_manifest_beside_the_draft():
    sys.path.insert(0, HERE)
    import test_anchor_reporting as T

    with tempfile.TemporaryDirectory() as tmp:
        T.build_corpus(tmp)
        art = os.path.join(tmp, "article.md")
        open(art, "w").write("---\ntitle: T\n---\n\n# H\n\n"
                             + T.DRAFT + "\n\n" + T.ESSAY + "\n")
        stub = DispatchStub()
        orig_run, saved_argv = drive.run, sys.argv
        drive.run = stub
        sys.argv = ["drive.py", "--article", art, "--retries", "0",
                    "--role", "venue-voice", "--anchor-tags", "clipped"]
        try:
            drive.main()
        finally:
            drive.run, sys.argv = orig_run, saved_argv

        draft = os.path.join(tmp, "article.vr-draft.md")
        manifest = os.path.join(tmp, "article.vr-draft.generation.yaml")
        assert os.path.exists(draft), "no draft written"
        assert os.path.exists(manifest), "manifest did not land beside the draft"

        # No model was involved, and the manifest is still complete.
        assert stub.ran("rewrite.py") and not stub.ran("ollama")
        m = load(open(manifest).read())
        assert m["anchor_role"] == "venue-voice"
        assert m["anchor_tags"] == ["clipped"]
        assert m["voice_dir"].endswith("writing-voice")
        # Both paragraphs drew the same two exemplars: the union is deduped.
        assert m["anchor_files"] == ["Yegge-2011-platforms.md",
                                     "DanLuu-2019-programming.md"], m["anchor_files"]
        assert m["result"]["accepted"] == 2, m["result"]
        assert "pangram" not in m, "no --pangram, so no pangram block"


def test_end_to_end_manifest_survives_a_run_that_rewrote_nothing():
    """A failing model must still leave provenance: knowing which anchors were
    selected is most useful precisely when the run went badly."""
    sys.path.insert(0, HERE)
    import test_anchor_reporting as T

    class Failing(DispatchStub):
        def __call__(self, cmd, **kw):
            if "rewrite.py" in " ".join(cmd):
                self.calls.append(cmd)
                return self.R(1, "", "Ollama unreachable")
            return super().__call__(cmd, **kw)

    with tempfile.TemporaryDirectory() as tmp:
        T.build_corpus(tmp)
        art = os.path.join(tmp, "article.md")
        open(art, "w").write("# H\n\n" + T.DRAFT + "\n")
        orig_run, saved_argv = drive.run, sys.argv
        drive.run = Failing()
        sys.argv = ["drive.py", "--article", art, "--retries", "0"]
        try:
            drive.main()
        finally:
            drive.run, sys.argv = orig_run, saved_argv

        m = load(open(os.path.join(
            tmp, "article.vr-draft.generation.yaml")).read())
        assert m["result"]["rewrite_error"] == 1, m["result"]
        assert m["result"]["accepted"] == 0
        assert m["anchor_files"], "anchors were selected and must be recorded"


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_manifest: all assertions passed")


if __name__ == "__main__":
    main()
