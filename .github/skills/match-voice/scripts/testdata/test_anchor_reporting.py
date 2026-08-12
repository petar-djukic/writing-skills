#!/usr/bin/env python3
"""Offline tests for realized-anchor reporting and inert-filter detection (GH-233/234).

No network, no model. The corpus is a synthetic writing-voice/ built in a temp
directory, shaped like the one that produced the measured failure: a pool that
is mostly venue-voice, where a technical paragraph still selects author-voice
papers, so the pool line reads healthy while the selection does not.

Run: python3 <skill>/scripts/testdata/test_anchor_reporting.py
"""
import io
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(HERE), "..", "..", "match-structure", "scripts")))
import drive  # noqa: E402
import voice_anchors as va  # noqa: E402

PAPER = ("We consider the problem of distributed link scheduling in a wireless "
         "mesh network under a time-division access constraint. The optimization "
         "is formulated as a maximum-weight matching over the conflict graph, "
         "and we derive a bound on the achievable throughput of the resulting "
         "schedule. Simulation over a topology of twenty nodes confirms the "
         "analysis, with the scheduler converging within a bounded number of "
         "slots for every offered load we evaluated. The protocol requires no "
         "central coordinator and each node exchanges state only with its "
         "neighbours in the conflict graph.")

ESSAY = ("You are the one deciding what gets built and when. The tooling does "
         "not decide it for you, and anyone who tells you otherwise is selling "
         "something. I have watched teams hand that judgement to a process and "
         "then wonder why the process shipped the wrong thing. Keep the "
         "decision. Write the thing down, argue about it, and then go build it. "
         "That is the whole job and it does not get easier with better tools.")

# Essay-shaped, and shares vocabulary with ESSAY so retrieval can score it.
# A paragraph with no overlap scores zero everywhere and selects nothing, which
# is its own test below.
DRAFT = ("You are deciding what gets built and when, and the tooling does not "
         "decide it for you. Keep that judgement: write the thing down, argue "
         "about it with the team, and then go build it.")


class Args:
    """The subset of drive.py's parsed flags that anchor reporting reads."""

    def __init__(self, voice_dir, role=None, stratum=None, anchor_tags=None):
        self.voice_dir = voice_dir
        self.role = role
        self.stratum = stratum
        self.anchor_tags = anchor_tags


def build_corpus(tmp, all_pre_ai=True):
    """A writing-voice/ with 2 author-voice papers and 3 venue-voice essays."""
    vd = os.path.join(tmp, "writing-voice")
    os.makedirs(vd, exist_ok=True)
    rows = [
        ("Djukic-2007-scheduling.md", "author-voice", 2007, PAPER, None),
        ("Djukic-2009-rrm.md", "author-voice", 2009, PAPER, None),
        ("Yegge-2011-platforms.md", "venue-voice", 2011, ESSAY, ["clipped"]),
        ("DanLuu-2019-programming.md", "venue-voice", 2019, ESSAY, ["clipped"]),
        ("Evans-2020-wizard.md", "venue-voice", 2020, ESSAY, ["clipped"]),
    ]
    lines = ["purpose: test corpus", "exemplars:"]
    for fname, role, year, body, tags in rows:
        open(os.path.join(vd, fname), "w").write(body + "\n")
        lines += [f"  - id: {fname[:-3].lower()}",
                  f"    file: {fname}",
                  f"    role: {role}",
                  f"    year: {year}"]
        # all_pre_ai=False marks one sample AI-era, which is what makes
        # --stratum pre-ai an actual filter rather than a no-op.
        if not all_pre_ai and fname.startswith("Evans"):
            lines.append("    pre_ai: false")
        if tags:
            lines.append(f"    tags: [{', '.join(tags)}]")
    open(os.path.join(vd, "manifest.yaml"), "w").write("\n".join(lines) + "\n")
    return vd


def paras(*texts):
    """(start, end, text) triples, the shape parse_paragraphs returns."""
    return [(i * 2 + 1, i * 2 + 1, t) for i, t in enumerate(texts)]


def test_inert_stratum_is_detected():
    """Every diction-eligible sample pre-AI: --stratum pre-ai filters nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp, all_pre_ai=True)
        assert (len(va.sample_paths(vd)) ==
                len(va.sample_paths(vd, pre_ai=True)) == 5)
        got = drive.inert_filters(va, vd, Args(vd, stratum="pre-ai"))
        assert got == ["stratum=pre-ai"], got


def test_effective_stratum_is_not_flagged():
    """One AI-era sample, so the same flag IS steering and must stay quiet."""
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp, all_pre_ai=False)
        assert len(va.sample_paths(vd, pre_ai=True)) == 4
        assert drive.inert_filters(va, vd, Args(vd, stratum="pre-ai")) == []


def test_inert_role_and_tags_are_detected():
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        # Every venue-voice sample carries `clipped`, so within role=venue-voice
        # the tag filter removes nothing.
        got = drive.inert_filters(
            va, vd, Args(vd, role="venue-voice", anchor_tags="clipped"))
        assert "tags=clipped" in got, got


def test_no_filters_reports_nothing_inert():
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        assert drive.inert_filters(va, vd, Args(vd)) == []


def test_realized_mix_reports_what_was_selected():
    """The core of GH-233: a technical paragraph on a mostly-venue pool.

    The pool is 3 venue to 2 author. What retrieval picks for a paper-shaped
    paragraph is what matters, and it is not the pool ratio.
    """
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        pool = {r for _, r in va.sample_paths(vd)}
        assert pool == {"author-voice", "venue-voice"}
        roles, sources, sampled, total = drive.realized_mix(
            va, vd, Args(vd), paras(PAPER), limit=None)
        assert sampled == total == 1
        assert sum(roles.values()) > 0
        assert roles.get("author-voice", 0) >= 1, roles
        # Sources, not only roles: the GH-215 shape is "every anchor is a paper",
        # which a role count can hide.
        assert any("Djukic" in f for f in sources), dict(sources)


def test_role_filter_changes_the_realized_selection():
    """--role venue-voice on an essay-shaped paragraph draws the essays."""
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        roles, sources, _, _ = drive.realized_mix(
            va, vd, Args(vd, role="venue-voice"), paras(DRAFT), limit=None)
        assert set(roles) == {"venue-voice"}, dict(roles)
        assert not any("Djukic" in f for f in sources), dict(sources)


def test_forcing_a_topically_distant_role_selects_nothing():
    """Documents a real edge the report now makes visible.

    anchors() drops candidates that score zero, so forcing a role whose samples
    share no vocabulary with the paragraph returns no anchors at all — the
    rewrite would run unanchored. Under the old pool-only line this was
    invisible: the pool was non-empty, so the line looked healthy.
    """
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        assert len(va.sample_paths(vd, role="venue-voice")) == 3
        roles, _s, _sa, _t = drive.realized_mix(
            va, vd, Args(vd, role="venue-voice"), paras(PAPER), limit=None)
        assert sum(roles.values()) == 0, dict(roles)
        _d, out, _err = _provenance(vd, Args(vd, role="venue-voice"), paras(PAPER))
        assert "selected 0 anchors" in out, out


def test_realized_mix_respects_the_sample_limit():
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        _r, _s, sampled, total = drive.realized_mix(
            va, vd, Args(vd), paras(PAPER, ESSAY, PAPER), limit=2)
        assert (sampled, total) == (2, 3)


def _provenance(vd, args, ps, full=False):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        d = drive.anchor_provenance(args, os.path.join(vd, ".."), ps, full=full)
    return d, out.getvalue(), err.getvalue()


def test_provenance_prints_pool_and_selection_separately():
    """Both questions get answered, and labelled so they cannot be confused."""
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        _d, out, _err = _provenance(vd, Args(vd), paras(PAPER))
        assert "pool" in out, out
        assert "selected" in out, out
        assert "roles" in out and "top sources" in out, out


def test_provenance_states_how_many_paragraphs_it_sampled():
    """A sampled mix reported as complete is the defect this fixes, so the
    scope is always named."""
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        many = paras(*([PAPER, ESSAY] * 6))  # 12 > PREVIEW_PARAGRAPHS
        _d, out, _err = _provenance(vd, Args(vd), many, full=False)
        assert f"{drive.PREVIEW_PARAGRAPHS} of {len(many)} paragraphs" in out, out
        _d, out_full, _err = _provenance(vd, Args(vd), many, full=True)
        assert "every paragraph" in out_full, out_full


def test_provenance_warns_on_inert_filter():
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        _d, _out, err = _provenance(vd, Args(vd, stratum="pre-ai"), paras(PAPER))
        assert "INERT FILTER" in err and "stratum=pre-ai" in err, err


def test_provenance_no_longer_recommends_the_inert_flag():
    """GH-234: the old advice sent operators to --stratum pre-ai, which on this
    corpus cannot move the result. It must point at role/tags instead."""
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        _d, out, err = _provenance(vd, Args(vd), paras(PAPER))
        both = out + err
        assert "try --stratum pre-ai" not in both, both
        assert "MOSTLY author-voice" in err, err
        assert "--role venue-voice" in err, err


def test_provenance_warning_is_based_on_selection_not_pool():
    """Silent when the anchors actually chosen are venue-voice, even though the
    pool still holds the papers."""
    with tempfile.TemporaryDirectory() as tmp:
        vd = build_corpus(tmp)
        _d, _out, err = _provenance(vd, Args(vd), paras(ESSAY))
        assert "MOSTLY author-voice" not in err, err


def test_provenance_handles_a_missing_corpus():
    with tempfile.TemporaryDirectory() as tmp:
        args = Args(None)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            d = drive.anchor_provenance(args, os.path.join(tmp, "article.md"),
                                        paras(PAPER))
        assert d is None
        assert "no writing-voice/" in err.getvalue()


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("test_anchor_reporting: all assertions passed")


if __name__ == "__main__":
    main()
