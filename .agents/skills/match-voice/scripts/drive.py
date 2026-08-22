#!/usr/bin/env python3
"""drive.py — orchestrate the match-voice pipeline over a whole article.

Stages per prose paragraph: retrieve anchors -> rewrite (Ollama) -> gate
(verify.py mechanical checks + filter-tells lexical scan), with failure-classified
retries. Assembles gate-passing rewrites into a sibling draft file.

The driver applies the MECHANICAL gate only. Meaning entailment is a judgment
call and stays with the reviewing model (references/prompts.md); the emitted
draft is a set of candidates, not an accepted result.

Paragraph extraction uses ProseDocument (prose_document.py), which dispatches
on file extension: markdown files use md_paragraphs.py internally, YAML files
use ruamel.yaml. The to_parse_result() adapter preserves the tuple shape the
driver expects.

Two article-level guards run before the loop (GH-77, protected_terms.py):
the protected-term list — the article's referent chain, derived once to
<stem>.protected-terms.txt beside the article (hand-editable, never
overwritten), sent to the rewrite model as a keep-verbatim rule and checked
by the gate as a fatal loss — and the canonical-block registry
(writing-voice/canonical-blocks.txt or --canonical-blocks), whose paragraphs
never reach the model at all.

Per paragraph the loop is two-pass (GH-77, critique.py): pass 1 rewrites,
a critique judges the candidate against the original (mechanical fields plus
a critic model), a 'repair' verdict sends it back once with the critique as
explicit constraints, a 'reject' keeps the original, and the mechanical gate
runs after whichever pass produced the candidate. results.json records both
passes and the critique; the report prints pass-1 vs pass-2 acceptance.

With --pangram the driver also measures whether the rewrite worked, scanning
the article before it starts and the draft when it finishes (GH-212). The
baseline has to be captured first because it cannot be reconstructed once the
paragraphs are replaced — which is why this belongs in the driver and not in a
procedure someone is expected to remember afterwards.

Usage:
  python3 drive.py --article <path.md|path.yaml> [--model gemma4:12b] [--out <path>]
                   [--retries 2] [--min-words 12] [--temperature 0.7]
                   [--coverage-only] [--pangram]
                   [--protected-terms <file> | --no-protected-terms]
                   [--canonical-blocks <file>]
                   [--critic-model MODEL | --no-critique]
"""
import argparse, json, os, re, subprocess, sys, tempfile
from collections import Counter

SK = os.path.dirname(os.path.realpath(__file__))
DEAI = os.path.normpath(os.path.join(SK, "..", "..", "filter-tells", "scripts", "detect-lexical.sh"))
SHARED = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
PANGRAM = os.path.join(SHARED, "pangram.py")
PANGRAM_REPORT = os.path.join(SHARED, "pangram_report.py")
FILTER_TELLS = os.path.normpath(os.path.join(SK, "..", "..", "filter-tells", "scripts"))

COPY_NOTE = ("Write the paragraph entirely in your own words. The example passages are a "
             "STYLE guide only — do NOT reuse any run of more than a few words from them. "
             "Match the register, not the wording.")
NUM_NOTE = ("Preserve every number and figure exactly as written in the original. Do not "
            "add, remove, renumber, or invent any number. Do not turn prose into a "
            "numbered or bulleted list.")
REG_NOTE = ("Avoid corporate and AI-typical vocabulary (leverage, robust, seamless, "
            "delve, comprehensive, crucial). Do not trade it for chatty filler "
            "either: no just, actually, really, basically, simply, honestly. "
            "Plain declarative technical prose.")
DASH_NOTE = ("You added an em-dash the original did not have. Keep the original's "
             "punctuation: no new em-dashes, and do not convert a comma or colon "
             "into one. Do not manufacture antithesis either — no \"X is not Y, "
             "it is Z\" unless the original already contrasted them.")
MARKUP_NOTE = ("Reproduce the markdown formatting of the original exactly: every **bold** "
               "span, *italic* span, and `code` span, in the same places. If the "
               "paragraph opens with a bold sentence, your rewrite must open with a "
               "bold sentence too — it is a lead-in, not ordinary prose.")
TERM_NOTE = ("You dropped the protected term(s) {terms}. These words carry the "
             "article's referent chain across paragraphs; a synonym breaks it. "
             "Keep each one verbatim.")


def _protected_terms_module():
    if SK not in sys.path:
        sys.path.insert(0, SK)
    import protected_terms
    return protected_terms


def _critique_module():
    if SK not in sys.path:
        sys.path.insert(0, SK)
    import critique
    return critique


def _rewrite_module():
    if SK not in sys.path:
        sys.path.insert(0, SK)
    import rewrite
    return rewrite


def term_note(verify_json):
    """The retry note for protected-term losses, naming the terms, or None."""
    try:
        data = json.loads(verify_json)
    except (json.JSONDecodeError, TypeError):
        return None
    lost = [f["detail"].split(":", 1)[1].strip()
            for f in data.get("findings", []) if f.get("check") == "protected-term"]
    return TERM_NOTE.format(terms=", ".join(lost)) if lost else None


def run(cmd, **kw):
    # errors="replace": a single non-UTF-8 byte from any child would
    # otherwise raise UnicodeDecodeError and take down the whole run.
    # Measured (GH-229): a published article with smart quotes killed
    # both arms of an A/B before either produced a line.
    return subprocess.run(cmd, capture_output=True, text=True,
                          errors="replace", **kw)


def default_out(art):
    """Draft path beside the article, extension-aware (GH-349).

    The old .md-only substitution returned the input path unchanged for any
    other extension, so a YAML article's draft overwrote the article.
    """
    stem, ext = os.path.splitext(art)
    return f"{stem}.vr-draft{ext}"


def manifest_path(out):
    """Provenance path beside the draft, appended to the draft's stem.

    Never substituted for the extension (GH-349): substitution left
    manifest == out for non-.md drafts, overwriting the finished draft.
    """
    manifest = os.path.splitext(out)[0] + ".generation.yaml"
    if manifest == out:
        manifest = out + ".generation.yaml"
    return manifest


def _prose_document():
    """ProseDocument factory — handles both markdown and YAML files."""
    sibling = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        import prose_document
        return prose_document
    except ImportError as e:
        sys.exit(f"could not import prose_document.py from {sibling}: {e}")


def pangram_scan(path, work, tag):
    """Build the prose-only payload for one file and scan it.

    Returns (response_path, spans_path), or None when the payload or the scan
    fails — no key, no credits, no network. A failure here is reported and the
    rewrite continues: the measurement is an outcome check, never a gate.
    """
    payload = os.path.join(work, f"{tag}.payload.txt")
    p = run(["python3", PANGRAM_REPORT, "payload", "--article", path, "--out", payload])
    if p.returncode != 0:
        print(f"pangram: {tag} payload failed — {(p.stderr or p.stdout).strip()[:200]}",
              file=sys.stderr)
        return None
    resp = os.path.join(work, f"{tag}.json")
    s = run(["python3", PANGRAM, "--text", payload, "--json"])
    if s.returncode != 0 or not s.stdout.strip():
        print(f"pangram: {tag} scan skipped — {(s.stderr or 'no response').strip()[:200]}",
              file=sys.stderr)
        return None
    open(resp, "w").write(s.stdout)
    return resp, os.path.splitext(payload)[0] + ".spans.json"


STRUCTURAL = os.path.normpath(os.path.join(SK, "..", "..", "filter-tells",
                                           "scripts", "detect-structural.py"))
# The three the rewrite was measured degrading (GH-243). Reported from
# detect-structural.py rather than recomputed here: two implementations of
# "dash density" would drift, and the numbers in issues have to be the numbers
# in run output.
STRUCT_KEYS = ("sentence_length_std", "dash_density_per_500w",
               "contrast_flip_per_500w")


def _structural(path):
    """The tracked metrics for one file, or {} when they cannot be read."""
    r = run([sys.executable, STRUCTURAL, path, "--json"])
    if r.returncode not in (0, 1) or not r.stdout.strip():
        return {}
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {}
    rec = data[0] if isinstance(data, list) and data else data
    m = (rec or {}).get("metrics", {}) if isinstance(rec, dict) else {}
    # Only the metrics that were actually scored. A short document skips them,
    # and keys carrying None would defeat the caller's "nothing to compare"
    # guard and print a row of n/a instead of staying quiet.
    return {k: m[k] for k in STRUCT_KEYS if m.get(k) is not None}


def report_structural(article, draft):
    """Print the three rhythm metrics before -> after.

    A falling detector score with these moving the wrong way is the GH-219
    pattern, and antithesis is the one the house rules forbid outright — so a
    rewrite that manufactures it has to be visible in the run, not discovered by
    a hand measurement afterwards.
    """
    before, after = _structural(article), _structural(draft)
    shared = [k for k in STRUCT_KEYS if k in before and k in after]
    if not shared:
        return
    print("\nrhythm (article -> draft):")
    for k in shared:
        b, a = before[k], after[k]
        # std falling means flatter; the other two rising means more of what the
        # house rules limit.
        worse = (a < b) if k == "sentence_length_std" else (a > b)
        print(f"  {k:26} {b:>6} -> {a:<6}{'  WORSE' if worse else ''}")


# Relative-increase ceilings, article -> draft, on per_1000 rates. Advisory:
# the gate governs fidelity; nothing hard-fails a run for style drift. The
# calibrating case is gpt-oss --no-anchors doubling passives (4.1 -> 8.6),
# which the plain UP arrow reported identically to a 0.1 uptick (GH-324).
GUARD_THRESHOLDS = {"passive": 0.50, "nominalization": 0.25, "filler": 0.50}
# A metric rising from zero has no relative increase; warn only when the
# draft's rate is visible on its own.
GUARD_ZERO_FLOOR = 2.0


def readability_guard(before_per_1000, after_per_1000):
    """WARN records for register metrics that degraded past their threshold."""
    warns = []
    for metric, limit in GUARD_THRESHOLDS.items():
        b, a = before_per_1000.get(metric), after_per_1000.get(metric)
        if b is None or a is None or a <= b:
            continue
        if b == 0:
            if a >= GUARD_ZERO_FLOOR:
                warns.append({"metric": metric, "before": b, "after": a,
                              "rise_pct": None,
                              "threshold_pct": round(limit * 100)})
            continue
        rise = (a - b) / b
        if rise > limit:
            warns.append({"metric": metric, "before": b, "after": a,
                          "rise_pct": round(rise * 100, 1),
                          "threshold_pct": round(limit * 100)})
    return warns


def report_register(article, draft):
    """Register markers before -> after, via the shared reporter (GH-222).

    One marker vocabulary everywhere: the numbers in issues and the numbers in
    run output are the same numbers. A falling AI score with rising markers is
    the GH-219/GH-220 failure — the objective met, the prose worse.

    Returns the readability-guard warnings (GH-324) so the manifest records
    them; [] when clean or when the markers cannot be read.
    """
    r = run([sys.executable, os.path.join(SHARED, "register_markers.py"),
             "--compare", article, draft])
    if r.returncode == 0 and r.stdout.strip():
        print()
        print(r.stdout.rstrip())
        if r.stderr.strip():
            print(r.stderr.rstrip(), file=sys.stderr)
    j = run([sys.executable, os.path.join(SHARED, "register_markers.py"),
             "--compare", article, draft, "--json"])
    if j.returncode != 0 or not j.stdout.strip():
        return []
    try:
        data = json.loads(j.stdout)
    except json.JSONDecodeError:
        return []
    warns = readability_guard(data.get("before", {}).get("per_1000", {}),
                              data.get("after", {}).get("per_1000", {}))
    if warns:
        print("readability guard:")
        for w in warns:
            rise = "from zero" if w["rise_pct"] is None else f"+{w['rise_pct']}%"
            print(f"  WARN {w['metric']} {w['before']} -> {w['after']} /1000w "
                  f"({rise}, threshold +{w['threshold_pct']}%)")
    else:
        print("readability guard: clean")
    return warns


def pangram_delta(before, after):
    """Print fraction_ai before -> after and the still-flagged worklist.

    The worklist ends with a ready-to-paste --paragraphs selection (GH-322):
    span order and drive.py paragraph order are the same md_paragraphs
    segmentation, so the k-th prose paragraph in the diff is paragraph k here.
    """
    r = run(["python3", PANGRAM_REPORT, "report", "--response", after[0],
             "--spans", after[1], "--baseline", before[0],
             "--baseline-spans", before[1]])
    if r.returncode != 0:
        print(f"pangram: comparison failed — {(r.stderr or '').strip()[:200]}",
              file=sys.stderr)
        return
    print("\nexternal check (Pangram, article -> draft):")
    print(r.stdout.rstrip())
    j = run(["python3", PANGRAM_REPORT, "report", "--response", after[0],
             "--spans", after[1], "--baseline", before[0],
             "--baseline-spans", before[1], "--json"])
    if j.returncode != 0 or not j.stdout.strip():
        return
    try:
        diff = json.loads(j.stdout)
    except json.JSONDecodeError:
        return
    flagged = [i + 1 for i, p in enumerate(diff.get("paragraphs") or [])
               if p.get("flagged")]
    if flagged:
        print(f'next pass: --paragraphs "{compress_ranges(flagged)}"')


def compress_ranges(indices):
    """'1,3-5,9' from sorted 1-based indices — the --paragraphs input syntax."""
    out, i = [], 0
    idx = sorted(indices)
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and idx[j + 1] == idx[j] + 1:
            j += 1
        out.append(str(idx[i]) if i == j else f"{idx[i]}-{idx[j]}")
        i = j + 1
    return ",".join(out)


def parse_paragraph_selection(spec, total):
    """Set of 1-based paragraph indices from 'N,M-K' syntax.

    Raises ValueError on malformed pieces, descending ranges, or indices
    outside 1..total, so the caller can refuse the run before any model call.
    """
    chosen = set()
    for piece in (p.strip() for p in spec.split(",")):
        if not piece:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", piece)
        if not m:
            raise ValueError(f"malformed paragraph selection: '{piece}'")
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        if lo > hi:
            raise ValueError(f"descending range: '{piece}'")
        if lo < 1 or hi > total:
            raise ValueError(f"'{piece}' outside 1..{total}")
        chosen.update(range(lo, hi + 1))
    if not chosen:
        raise ValueError("empty paragraph selection")
    return chosen


def anchor_flags(a):
    """Anchor-selection flags to forward to retrieve.py."""
    f = []
    if a.voice_dir:
        f += ["--voice-dir", a.voice_dir]
    if a.role:
        f += ["--role", a.role]
    if a.stratum:
        f += ["--stratum", a.stratum]
    if a.anchor_tags:
        f += ["--tags", a.anchor_tags]
    if a.author:
        f += ["--author", a.author]
    return f


PREVIEW_PARAGRAPHS = 5


def _voice_anchors_module():
    stylo = os.path.normpath(os.path.join(SK, "..", "..", "match-structure", "scripts"))
    if stylo not in sys.path:
        sys.path.insert(0, stylo)
    try:
        import voice_anchors as va
        return va
    except ImportError:
        return None


def _selection(a):
    """(pre_ai, tags) as voice_anchors wants them, from the parsed flags."""
    pre = (True if a.stratum == "pre-ai"
           else False if a.stratum == "ai-era" else None)
    return pre, (a.anchor_tags.split(",") if a.anchor_tags else None)


def inert_filters(va, d, a):
    """Which anchor-selection flags remove nothing on THIS corpus.

    A filter that excludes no sample is not a control, and an operator following
    a document that calls it one gets the failure it was supposed to prevent
    (GH-234: `--stratum pre-ai` on a corpus deepened until every diction-eligible
    sample is pre-AI). Reported by name, at the point it is applied.
    """
    pre, tags = _selection(a)
    author = getattr(a, "author", None)
    n = len(va.sample_paths(d, role=a.role, pre_ai=pre, tags=tags, author=author))
    out = []
    if a.stratum and len(va.sample_paths(d, role=a.role, pre_ai=None, tags=tags, author=author)) == n:
        out.append(f"stratum={a.stratum}")
    if a.role and len(va.sample_paths(d, role=None, pre_ai=pre, tags=tags, author=author)) == n:
        out.append(f"role={a.role}")
    if tags and len(va.sample_paths(d, role=a.role, pre_ai=pre, tags=None, author=author)) == n:
        out.append(f"tags={a.anchor_tags}")
    if author and len(va.sample_paths(d, role=a.role, pre_ai=pre, tags=tags, author=None)) == n:
        out.append(f"author={author}")
    return out


def realized_mix(va, d, a, paras, limit=None):
    """Run retrieval for real and report what it SELECTED, not what was available.

    The pool line cannot catch a bad selection (GH-233). On a corpus that is 80%
    venue-voice, a how-to paragraph still drew two IEEE papers out of three
    anchors — the GH-215 failure, on a pool assembled to prevent it, with a mix
    line that showed nothing wrong because nothing about the pool was wrong.

    Returns (roles, sources, sampled, total) where sampled is how many
    paragraphs were actually retrieved for. A sampled count reported as if it
    were complete would be the same defect this function exists to fix, so the
    caller prints it.
    """
    pre, tags = _selection(a)
    chosen = paras if limit is None else paras[:limit]
    roles, sources = Counter(), Counter()
    for _s, _e, txt in chosen:
        for x in va.anchors(d, txt, k=3, role=a.role, pre_ai=pre, tags=tags,
                            author=getattr(a, "author", None)):
            roles[x.get("role", "?")] += 1
            sources[x.get("file", "?")] += 1
    return roles, sources, len(chosen), len(paras)


def anchor_provenance(a, article, paras, full=False):
    """Print the anchor pool AND the realized selection, BEFORE rewriting.

    Two different questions, and only the second one predicts the output: the
    pool says what retrieval may reach, the selection says what it chose. GH-215
    was invisible until an operator re-ran retrieval by hand after a
    25-paragraph rewrite; GH-233 was invisible because the pool was reported
    instead of the selection. Both are cheap to answer up front.

    Returns the discovered voice directory. Exits when there is no corpus
    (GH-308): a rewrite with no target register produces something nobody
    asked for, and --no-anchors is how you say you meant it. Returns None only
    when match-structure is not importable, which is a reporting gap rather
    than a missing target.
    """
    va = _voice_anchors_module()
    if va is None:
        print("anchors: match-structure not importable — cannot report the mix",
              file=sys.stderr)
        return None
    d = a.voice_dir or va.discover(article)
    if not d:
        sys.exit("anchors: no writing-voice/ found — the rewrite has no target "
                 "register. Use --no-anchors to run without voice steering, or "
                 "run plain filter-tells instead")

    pre, tags = _selection(a)
    author = getattr(a, "author", None)
    paths = va.sample_paths(d, role=a.role, pre_ai=pre, tags=tags, author=author)
    mix = Counter(r for _, r in paths)
    filt = " ".join(x for x in (f"role={a.role}" if a.role else "",
                                f"stratum={a.stratum}" if a.stratum else "",
                                f"tags={a.anchor_tags}" if a.anchor_tags else "",
                                f"author={author}" if author else "") if x)
    weight = va.AUTHOR_VOICE_DICTION_WEIGHT
    print(f"anchors: {len(paths)} exemplars available from {d}")
    print(f"         pool {dict(mix)}{'  [' + filt + ']' if filt else ''}")
    print(f"         author-voice weight {weight}x (diction mode)")

    for name in inert_filters(va, d, a):
        print(f"         INERT FILTER {name} selects the whole pool — it is not "
              f"steering anything on this corpus", file=sys.stderr)

    if not paths:
        sys.exit(f"anchors: NOTHING MATCHES THE FILTER"
                 f"{'  [' + filt + ']' if filt else ''} — 0 exemplars in pool. "
                 f"Use --no-anchors to run without voice steering")
    if not paras:
        return d

    roles, sources, sampled, total = realized_mix(
        va, d, a, paras, None if full else PREVIEW_PARAGRAPHS)
    scope = ("every paragraph" if sampled == total
             else f"{sampled} of {total} paragraphs")
    print(f"         selected {sum(roles.values())} anchors over {scope}")
    print(f"         roles {dict(roles)}")
    top = ", ".join(f"{f} x{n}" for f, n in sources.most_common(5))
    print(f"         top sources {top}")

    # Roles alone hide the GH-215 shape: {'venue-voice': 2, 'author-voice': 1}
    # looks balanced while every anchor is an IEEE paper. Judge on what was
    # chosen, which is why this warning moved off the pool.
    picked = sum(roles.values())
    if picked and roles.get("author-voice", 0) * 2 >= picked and not a.role:
        print("         MOSTLY author-voice anchors were SELECTED; if this draft "
              "wants punch rather than precision, select the register explicitly "
              "with --role venue-voice and/or --anchor-tags", file=sys.stderr)
    return d


def _yaml_scalar(v):
    """Quote only what YAML would otherwise misread. Hand-rolled on purpose:
    this script is stdlib-only so it runs outside the pixi environment."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if s == "" or any(c in s for c in ":#[]{},&*!|>%@`\"'\n") or s[0] in "-? ":
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _pangram_summary(response_path):
    """All three fractions, segment counts, and mean window score from a saved response."""
    try:
        with open(response_path) as f:
            r = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    windows = r.get("windows") or []
    scores = [w["ai_assistance_score"] for w in windows
              if w.get("ai_assistance_score") is not None]
    mean_ws = round(sum(scores) / len(scores), 4) if scores else None
    return {
        "fraction_ai": r.get("fraction_ai"),
        "fraction_ai_assisted": r.get("fraction_ai_assisted"),
        "fraction_human": r.get("fraction_human"),
        "num_ai": r.get("num_ai_segments", 0),
        "num_ai_assisted": r.get("num_ai_assisted_segments", 0),
        "num_human": r.get("num_human_segments", 0),
        "mean_window_score": mean_ws,
        "num_windows": len(windows),
    }


def write_manifest(path, a, voice_dir, results, pangram=None, guard=None):
    """Run provenance beside the draft, in the shape a front-matter block wants.

    The anchor set is the single most important input to a rewrite — it is what
    pulled the prose toward one register rather than another — and until now it
    lived only in a results.json inside a mkdtemp that the OS reaps (GH-236).
    Everything here is already known or already computed; this is persistence
    and a dedup, not new analysis.
    """
    seen, anchor_files = set(), []
    for r in results:
        for x in r.get("anchors") or []:
            f = x.get("file")
            if f and f not in seen:
                seen.add(f)
                anchor_files.append(f)
    counts = Counter(r["status"] for r in results)
    tags = [t.strip() for t in a.anchor_tags.split(",")] if a.anchor_tags else []

    out = ["# Generated by match-voice/scripts/drive.py — run provenance.",
           "match_voice:",
           f"  model: {_yaml_scalar(a.model)}",
           f"  voice_dir: {_yaml_scalar(voice_dir)}",
           f"  no_anchors: {str(a.no_anchors).lower()}",
           f"  anchor_author: {_yaml_scalar(getattr(a, 'author', None))}",
           f"  anchor_role: {_yaml_scalar(a.role)}",
           f"  anchor_tags: [{', '.join(_yaml_scalar(t) for t in tags)}]",
           f"  stratum: {_yaml_scalar(a.stratum)}",
           f"  style_note: {_yaml_scalar(getattr(a, 'style_note', '') or None)}",
           f"  paragraphs: {_yaml_scalar(getattr(a, 'paragraphs', '') or None)}",
           "  anchor_files:"]
    out += [f"    - {_yaml_scalar(f)}" for f in anchor_files] or ["    []"]
    out.append("  result: {accepted: %d, kept_original: %d, skipped_short: %d, "
               "rewrite_error: %d, gate_error: %d, unselected: %d, "
               "excluded_key: %d, canonical: %d}"
               % (counts.get("accepted-mechanical", 0),
                  counts.get("kept-original", 0),
                  counts.get("skipped-short", 0),
                  counts.get("rewrite-error", 0),
                  counts.get("gate-error", 0),
                  counts.get("unselected", 0),
                  counts.get("excluded-key", 0),
                  counts.get("canonical", 0)))
    pt = getattr(a, "_protected", None)
    if pt:
        out.append("  protected_terms:")
        out.append(f"    path: {_yaml_scalar(pt['path'])}")
        out.append(f"    count: {pt['count']}")
        out.append(f"    derived: {str(pt['derived']).lower()}")
    else:
        out.append("  protected_terms: null")
    out.append(f"  canonical_blocks: {_yaml_scalar(getattr(a, '_canonical_path', None))}")
    crit = getattr(a, "_critique", None)
    if crit:
        out.append("  critique:")
        out.append(f"    model: {_yaml_scalar(crit.get('model'))}")
        for k in ("pass1_accepted", "pass2_accepted", "repaired",
                  "rejected_critique", "critique_unparsed", "critiqued"):
            out.append(f"    {k}: {crit.get(k, 0)}")
    else:
        out.append("  critique: null")
    if pangram:
        before, after = pangram
        out.append("  pangram:")
        out.append("    scope: prose-only")
        for label, p in [("before", before), ("after", after)]:
            if p is None:
                out.append(f"    {label}: null")
            else:
                out.append(f"    {label}:")
                out.append(f"      fraction_ai: {p['fraction_ai']}")
                out.append(f"      fraction_ai_assisted: {p['fraction_ai_assisted']}")
                out.append(f"      fraction_human: {p['fraction_human']}")
                out.append(f"      num_ai: {p['num_ai']}")
                out.append(f"      num_ai_assisted: {p['num_ai_assisted']}")
                out.append(f"      num_human: {p['num_human']}")
                mws = p['mean_window_score']
                out.append(f"      mean_window_score: {mws if mws is not None else 'null'}")
                out.append(f"      num_windows: {p['num_windows']}")
    if guard:
        out.append("  guard:")
        for w in guard:
            rise = w["rise_pct"] if w["rise_pct"] is not None else "from-zero"
            out.append(f"    - {{metric: {w['metric']}, before: {w['before']}, "
                       f"after: {w['after']}, rise_pct: {rise}, "
                       f"threshold_pct: {w['threshold_pct']}}}")
    open(path, "w").write("\n".join(out) + "\n")
    return anchor_files


def compose_note(style_note, failure_note):
    """The note for one rewrite attempt: standing style directive first,
    failure-classified retry note after it, either alone when the other is
    absent, empty string when both are."""
    return " ".join(p for p in (style_note, failure_note) if p)


def classify_gate_crash(returncode, stdout, stderr):
    """The gate-error record for a verify.py CRASH, or None on the normal path.

    A crash is a missing verdict, not a rejection: verify.py exits nonzero
    with a JSON verdict when it rejects, and with a traceback and no JSON when
    it breaks. Treating the two the same shipped no-op runs as successes
    (GH-318) — every rewrite silently discarded, reason '?'.
    """
    if returncode != 0 and not stdout.strip().startswith("{"):
        return {"status": "gate-error",
                "err": (stderr or "verify.py produced no verdict").strip()[:200]}
    return None


def restore_full_bold(original, candidate):
    """Re-wrap a candidate whose original was a single wholly-bold paragraph.

    A deterministic repair, and deliberately narrow. When the original is bold
    from end to end the emphasis belongs to the whole block, so restoring it
    cannot attach it to the wrong span. A leading bold sentence is the opposite
    case — where the lead-in ends up in the rewrite is not knowable here, so
    that one is the gate's business (GH-232) and gets retried, not patched.
    """
    o, c = original.strip(), candidate.strip()
    if o.startswith("**") and o.endswith("**") and not c.startswith("**"):
        return "**" + c + "**"
    return candidate


def assemble_draft(art, lines, accept, rng, out):
    """Write accepted candidates into the draft at `out`.

    YAML goes back through the document model (GH-358): ruamel round-trip
    keeps comments, key order, and structure — raw line splicing would drop
    bare prose over keys and block markers. Markdown keeps bottom-up line
    splicing. Descending order both ways, so a replacement that changes
    later paragraph indices cannot shift earlier ones. `accept` maps the
    1-based paragraph number to its candidate text; `rng` maps it to the
    (start, end) line span the markdown splice uses.
    """
    if art.lower().endswith((".yaml", ".yml")):
        doc = _prose_document().ProseDocument.open(art)
        if not accept:
            # Nothing accepted: emit the untouched source rather than a
            # ruamel re-emission, which normalizes wrapping and sequence
            # offsets and turns a no-op run into a noisy diff (GH-360).
            open(out, "w").write(doc.raw)
            return
        for n in sorted(accept, reverse=True):
            doc.replace(n - 1, accept[n])
        doc.save_as(out)
        return
    out_lines = list(lines)
    for n in sorted(accept, reverse=True):
        s, e = rng[n]
        # The wholly-bold repair happens before the gate now, so an accepted
        # candidate already carries the markup it is going to carry.
        out_lines[s - 1:e] = [accept[n]]
    open(out, "w").write("\n".join(out_lines))


def parse_paragraphs(path, min_words):
    """Return (lines, fm_close, paragraphs, coverage, unaccounted, doc).

    Uses ProseDocument for both markdown and YAML files, with the
    to_parse_result() adapter for backward-compat tuple shape.
    """
    pd = _prose_document()
    doc = pd.ProseDocument.open(path)
    r = doc.to_parse_result()
    return r.lines, r.fm_close, r.paragraphs, r.coverage, r.unaccounted, doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--model", default=os.environ.get("MATCH_VOICE_MODEL", "gemma4:12b"))
    ap.add_argument("--endpoint", default=os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434"))
    ap.add_argument("--out", help="draft path (default: <stem>.vr-draft<ext> "
                                  "beside the article)")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--min-words", type=int, default=12)
    ap.add_argument("--temperature", default="0.7")
    ap.add_argument("--style-note", default="",
                    help="standing style directive sent to the rewrite model "
                         "on EVERY attempt, e.g. 'active voice, plain "
                         "diction'; retries append their failure note to it")
    ap.add_argument("--paragraphs", default="",
                    help="rewrite only these 1-based paragraph indices "
                         "('3,7,12-15'); the rest pass through untouched. The "
                         "run report prints the next-pass selection to paste "
                         "here")
    ap.add_argument("--voice-dir",
                    help="exemplar corpus (default: discover writing-voice/ "
                         "upward from the article)")
    ap.add_argument("--role", choices=["author-voice", "venue-voice"],
                    help="hard filter anchors to one role")
    ap.add_argument("--anchor-tags",
                    help="comma-separated register tags; similarity still "
                         "ranks WITHIN the selected pool. Use when the register "
                         "that fits is not the one topically nearest")
    ap.add_argument("--stratum", choices=["pre-ai", "ai-era"],
                    help="pre-ai restricts anchors to diction-safe samples "
                         "across roles. Inert on a corpus whose diction-eligible "
                         "samples are all pre-AI — the run says so when it is. "
                         "To steer register, reach for --role/--anchor-tags")
    ap.add_argument("--author", help="hard pin anchors to a named author "
                                     "(case-insensitive match against the "
                                     "exemplar author field)")
    ap.add_argument("--no-anchors", action="store_true",
                    help="run without voice anchors; skip retrieval entirely")
    ap.add_argument("--coverage-only", action="store_true",
                    help="parse + coverage audit only; no model calls")
    ap.add_argument("--dry-run", action="store_true",
                    help="run retrieval for EVERY paragraph, report the anchors "
                         "it selects, and exit without calling the model. The "
                         "pre-run line samples a few paragraphs; this is the "
                         "whole article")
    ap.add_argument("--pangram", action="store_true",
                    help="measure the rewrite against an external detector. "
                         "UPLOADS this article and the draft to a third party "
                         "that retains them; passing the flag is the consent, "
                         "and it is asked for per document. Costs two scans.")
    ap.add_argument("--exclude-keys", nargs="*", default=None,
                    help="YAML key-path globs whose paragraphs skip rewriting "
                         "(default for YAML: section_goal, goals.*.goal, "
                         "acceptance.*, meta.*). Pass --exclude-keys with no "
                         "args to disable")
    ap.add_argument("--must-preserve", nargs="*", default=None,
                    help="exact phrases that must survive rewriting; verify.py "
                         "rejects candidates that lose any of them")
    ap.add_argument("--protected-terms", metavar="FILE",
                    help="protected-term list (default: <stem>.protected-terms.txt "
                         "beside the article, derived on first run and never "
                         "overwritten)")
    ap.add_argument("--no-protected-terms", action="store_true",
                    help="run without the referent-chain guard")
    ap.add_argument("--canonical-blocks", metavar="FILE",
                    help="canonical-block registry (default: writing-voice/"
                         "canonical-blocks.txt found walking up from the article); "
                         "matching paragraphs never reach the model")
    ap.add_argument("--critic-model",
                    help="model that critiques each pass-1 candidate against its "
                         "original (default: the rewrite model; a second family "
                         "is the better choice when one is pulled)")
    ap.add_argument("--no-critique", action="store_true",
                    help="single-shot path: rewrite, gate, done — no critique, "
                         "no repair pass")
    a = ap.parse_args()

    if a.no_anchors and any([a.role, a.anchor_tags, a.stratum, a.author]):
        ap.error("--no-anchors contradicts --role/--anchor-tags/--stratum/--author")

    art = os.path.abspath(a.article)
    out = os.path.abspath(a.out) if a.out else default_out(art)
    if out == art:
        sys.exit(f"refusing to overwrite the article: --out resolves to the "
                 f"input path ({art}); pass a different --out")
    lines, fm_close, paras, coverage, unaccounted, doc = parse_paragraphs(art, a.min_words)

    pd = _prose_document()
    exclude = set()
    ext = os.path.splitext(art)[1].lower()
    if ext in (".yaml", ".yml"):
        patterns = (a.exclude_keys if a.exclude_keys is not None
                    else pd.YAML_EXCLUDE_KEYS_DEFAULT)
        if patterns:
            exclude = pd.excluded_indices(doc.paragraphs, patterns)
            if exclude:
                print(f"exclude-keys: skipping {len(exclude)} contract-field "
                      f"paragraph(s): {sorted(exclude)}")

    pt = _protected_terms_module()
    texts = [p[2] for p in paras]
    canonical_patterns, canonical_path = pt.load_canonical(a.canonical_blocks, art)
    a._canonical_path = canonical_path
    canonical = pt.canonical_indices(texts, canonical_patterns) if canonical_patterns else set()
    if canonical_path:
        print(f"canonical blocks: {len(canonical)} paragraph(s) match "
              f"{canonical_path}: {sorted(canonical)}")
    protected_path = None
    a._protected = None
    if not a.no_protected_terms:
        terms, protected_path, derived = pt.load_or_derive(art, texts, a.protected_terms)
        a._protected = {"path": protected_path, "count": len(terms), "derived": derived}
        print(f"protected terms: {len(terms)} "
              f"({'derived, written to' if derived else 'loaded from'} {protected_path})")

    # Validated before any scan or model call: an invalid selection must cost
    # nothing.
    selection = None
    if a.paragraphs:
        try:
            selection = parse_paragraph_selection(a.paragraphs, len(paras))
        except ValueError as e:
            print(f"--paragraphs: {e}", file=sys.stderr)
            sys.exit(2)
    # Long enough to be rewritten is the same bar the loop uses, so the reported
    # selection is the selection the run would actually make.
    rewritable = [p for p in paras if len(p[2].split()) >= a.min_words]
    if a.no_anchors:
        print("anchors: --no-anchors set, skipping retrieval entirely")
        voice_dir = None
    else:
        voice_dir = anchor_provenance(a, art, rewritable, full=a.dry_run)

    from collections import Counter
    cats = Counter(coverage.values())
    print(f"coverage: {dict(sorted(cats.items()))}")
    print(f"prose paragraphs: {len(paras)}")
    if unaccounted:
        print(f"WARNING — unclassified body lines (parser skipped these): {unaccounted}",
              file=sys.stderr)
    if a.coverage_only:
        for n, (s, e, txt) in enumerate(paras, 1):
            w = len(txt.split())
            tag = "short-skip" if w < a.min_words else "rewrite"
            print(f"  p{n:02d} L{s:>4} {w:>4}w {tag:10} | {txt[:60]}")
        sys.exit(1 if unaccounted else 0)
    if a.dry_run:
        if a.pangram:
            work = tempfile.mkdtemp(prefix="match-voice-")
            print(f"\nexternal check: scanning {os.path.basename(art)}")
            bl = pangram_scan(art, work, "before")
            if bl:
                r = run(["python3", PANGRAM_REPORT, "report",
                         "--response", bl[0], "--spans", bl[1]])
                if r.returncode == 0:
                    print(r.stdout.rstrip())
            else:
                print("external check: pangram scan failed", file=sys.stderr)
        print("\ndry run: anchors above are the real selection for every "
              "rewritable paragraph. No model was called and no draft written.")
        sys.exit(1 if unaccounted else 0)

    work = tempfile.mkdtemp(prefix="match-voice-")

    # Baseline first: once the paragraphs are replaced the article's reading is
    # gone, and a comparison discovered later is simply unavailable.
    baseline = None
    if a.pangram:
        print(f"external check: scanning {os.path.basename(art)} for a baseline")
        baseline = pangram_scan(art, work, "before")
        if baseline is None:
            print("external check: no baseline, so the comparison is skipped; "
                  "the rewrite runs unchanged", file=sys.stderr)

    # The critic is checked before the first paragraph, like the rewrite
    # model: requested and unreachable is a hard error, never a silent skip.
    critic = None
    critique_mod = _critique_module()
    banned = critique_mod.load_banned()
    critic_model = a.critic_model or a.model
    if not a.no_critique:
        rwm = _rewrite_module()
        ok, msg = rwm.check_server(a.endpoint, critic_model)
        if not ok and a.critic_model:
            sys.exit(f"critic: {msg}")
        if ok:
            critic = lambda prompt: rwm.generate(prompt, endpoint=a.endpoint,  # noqa: E731
                                                 model=critic_model, temperature=0.0)
            print(f"critique: on, critic model {critic_model}"
                  f"{'' if banned else ' (banned-word list unreadable; mechanical banned check off)'}")
        else:
            # The default critic IS the rewrite model, and its absence is
            # reported per paragraph as rewrite-error — the run goes on so
            # the forensics land in the manifest as they always have, with
            # the mechanical critique alone (source.model: skipped).
            print(f"critic: {msg}\ncritique: mechanical fields only — no critic "
                  "model reachable", file=sys.stderr)
    else:
        print("critique: off (--no-critique); single-shot rewrite and gate")
    protected_terms_list = (_protected_terms_module().read_terms(protected_path)
                            if protected_path else [])

    results = []
    for n, (s, e, txt) in enumerate(paras, 1):
        rec = {"n": n, "lines": [s, e], "words": len(txt.split()), "orig": txt}
        if n in canonical:
            rec["status"] = "canonical"; results.append(rec); continue
        if rec["words"] < a.min_words:
            rec["status"] = "skipped-short"; results.append(rec); continue
        if selection is not None and n not in selection:
            rec["status"] = "unselected"; results.append(rec); continue
        if n in exclude:
            rec["status"] = "excluded-key"; results.append(rec); continue
        pf = f"{work}/p{n:02d}.orig.txt"; open(pf, "w").write(txt)
        if a.no_anchors:
            ajf = f"{work}/p{n:02d}.anchors.json"; open(ajf, "w").write("[]")
            rec["anchors"] = []
            atf = f"{work}/p{n:02d}.anchors.txt"; open(atf, "w").write("")
        else:
            rflags = anchor_flags(a)
            aj = run(["python3", f"{SK}/retrieve.py", "--text", pf, "--for", art,
                      *rflags, "--json"])
            at = run(["python3", f"{SK}/retrieve.py", "--text", pf, "--for", art, *rflags])
            ajf = f"{work}/p{n:02d}.anchors.json"; open(ajf, "w").write(aj.stdout or "[]")
            try:
                payload = json.loads(aj.stdout or "[]")
                recs = payload.get("anchors", payload) if isinstance(payload, dict) else payload
                rec["anchors"] = [{"file": x.get("file"), "role": x.get("role"),
                                   "score": x.get("score"), "weighted": x.get("weighted")}
                                  for x in recs]
            except (json.JSONDecodeError, AttributeError, TypeError):
                rec["anchors"] = []
            atf = f"{work}/p{n:02d}.anchors.txt"; open(atf, "w").write(at.stdout or "")
        note = None
        for attempt in range(1 + a.retries):
            cmd = ["python3", f"{SK}/rewrite.py", "--text", pf, "--anchors", atf,
                   "--model", a.model, "--endpoint", a.endpoint,
                   "--temperature", a.temperature]
            # The standing style note rides on every attempt; a retry's
            # failure-classified note is appended after it, so neither
            # displaces the other.
            sent_note = compose_note(a.style_note, note)
            if sent_note:
                cmd += ["--retry-note", sent_note]
            if protected_path:
                cmd += ["--protected-terms", protected_path]
            rw = run(cmd)
            if rw.returncode != 0 or not rw.stdout.strip():
                rec["status"] = "rewrite-error"; rec["err"] = (rw.stderr or "")[:200]
                break
            # Repair before verifying, not at assembly time: the gate now checks
            # markup (GH-232), so a candidate the driver would have patched on
            # the way out has to be patched before the gate reads it, or the
            # repair and the check disagree about the same paragraph.
            cand_text = restore_full_bold(txt, rw.stdout.strip())
            import verify as _vmod
            cand_text = _vmod.normalize_ascii(cand_text)
            # Pass 1 -> critique -> (repair | reject | accept). Only the
            # first attempt is critiqued; gate retries after it keep the
            # pass label of the candidate they are repairing.
            if attempt == 0 and not a.no_critique:
                rec["pass1"] = cand_text
                crit = critique_mod.critique(txt, cand_text, protected_terms_list,
                                             banned, critic)
                rec["critique"] = {k: v for k, v in crit.items() if k != "raw"}
                rec["pass"] = 1
                if crit["verdict"] == "reject":
                    rec["status"] = "rejected-critique"
                    break
                if crit["verdict"] == "repair":
                    constraints = critique_mod.render_constraints(crit)
                    cmd2 = [c for c in cmd if c not in ("--retry-note", sent_note)] \
                        + ["--retry-note", compose_note(a.style_note, constraints)]
                    rw2 = run(cmd2)
                    if rw2.returncode == 0 and rw2.stdout.strip():
                        cand_text = _vmod.normalize_ascii(
                            restore_full_bold(txt, rw2.stdout.strip()))
                        rec["pass2"] = cand_text
                        rec["pass"] = 2
                    else:
                        rec["pass2"] = None
                        rec["pass2_error"] = (rw2.stderr or "")[:200]
            cf = f"{work}/p{n:02d}.cand.txt"; open(cf, "w").write(cand_text)
            vcmd = ["python3", f"{SK}/verify.py", "--original", pf, "--rewrite", cf,
                    "--anchors-json", ajf, "--json"]
            if a.must_preserve:
                vcmd += ["--must-preserve"] + a.must_preserve
            if protected_path:
                vcmd += ["--protected-terms", protected_path]
            vf = run(vcmd)
            crash = classify_gate_crash(vf.returncode, vf.stdout, vf.stderr)
            if crash:
                rec.update(crash)
                break
            de = run(["bash", DEAI, cf])
            fj = vf.stdout if vf.stdout.strip().startswith("{") else "{}"
            warnings = []
            if de.returncode != 0:
                warnings.append("register")
            if '"similarity"' in fj:
                warnings.append("similarity")
            if vf.returncode == 0:
                rec["status"] = "accepted-mechanical"
                rec["cand"] = cand_text
                rec["attempt"] = attempt + 1
                if warnings:
                    rec["warnings"] = warnings
                break
            # classify for the retry note — only hard checks reach here
            notes = []
            if '"numbers"' in fj or '"citations"' in fj or '"terms"' in fj:
                notes.append(NUM_NOTE)
            if '"markup"' in fj:
                notes.append(MARKUP_NOTE)
            if '"dashes"' in fj:
                notes.append(DASH_NOTE)
            tn = term_note(fj)
            if tn:
                notes.append(tn)
            note = " ".join(notes) or COPY_NOTE
            rec["status"] = "kept-original"
            rec["last_fail"] = {"verify": json.loads(fj) if fj != "{}" else vf.stdout[:150],
                                "deai": de.returncode}
        results.append(rec)

    # assemble
    accept = {r["n"]: r["cand"] for r in results if r.get("cand")}
    rng = {r["n"]: tuple(r["lines"]) for r in results}
    assemble_draft(art, lines, accept, rng, out)
    json.dump(results, open(f"{work}/results.json", "w"), indent=2)

    from collections import Counter as C
    print(f"\ndraft: {out}\nwork:  {work}/results.json")
    for k, v in sorted(C(r["status"] for r in results).items()):
        print(f"  {k}: {v}")
    for r in results:
        if r["status"] == "kept-original":
            f = r.get("last_fail", {})
            v = f.get("verify")
            why = ",".join(x.get("check", "?") for x in v.get("findings", [])) \
                if isinstance(v, dict) else "?"
            print(f"  kept p{r['n']:02d} (L{r['lines'][0]}): {why}")
        if r["status"] == "gate-error":
            print(f"  GATE-ERROR p{r['n']:02d} (L{r['lines'][0]}): {r.get('err', '?')}")
        if r.get("warnings"):
            print(f"  advisory p{r['n']:02d} (L{r['lines'][0]}): "
                  f"{','.join(r['warnings'])}")
    if not a.no_critique:
        summary = critique_mod.summarize_passes(results)
        summary["model"] = critic_model
        a._critique = summary
        print(f"critique: pass 1 accepted {summary['pass1_accepted']}, "
              f"pass 2 accepted {summary['pass2_accepted']}, "
              f"repaired {summary['repaired']}, "
              f"rejected {summary['rejected_critique']}, "
              f"unparsed {summary['critique_unparsed']} "
              f"(of {summary['critiqued']} critiqued)")
        for r in results:
            if r["status"] == "rejected-critique":
                c = r.get("critique", {})
                why = "; ".join(c.get("meaning_deltas") or []) or ",".join(
                    (c.get("source") or {}).get("mechanical") or []) or "?"
                print(f"  rejected p{r['n']:02d} (L{r['lines'][0]}): {why[:120]}")
    else:
        a._critique = None
    gate_errors = [r for r in results if r["status"] == "gate-error"]
    if gate_errors:
        print(f"\nWARNING: the verification gate CRASHED on {len(gate_errors)} "
              "paragraph(s) — those rewrites were never judged, only discarded. "
              "Fix the gate before trusting this draft.", file=sys.stderr)
    print("\nMechanical gate only. Before accepting the draft: run the meaning-"
          "entailment review (references/prompts.md) on each accepted paragraph, "
          "and filter-tells over the assembled file.")

    # Unconditional, unlike the Pangram section below: this is local, costs
    # nothing, and uploads nothing. A rewrite that flattened rhythm or
    # manufactured antithesis should be visible from the run that did it rather
    # than from a hand measurement weeks later (GH-243).
    report_structural(art, out)

    # The outcome measure, last because it is the result of the run. Without a
    # baseline there is nothing to compare, so the second scan is not spent.
    pangram_pair = None
    guard_warns = []
    if not a.pangram:
        print("\nexternal check: skipped (no --pangram). The gate proves the "
              "candidates kept their citations, numbers, and meaning; it cannot "
              "say whether the prose stopped reading as machine-written.")
    elif not baseline:
        print("\nexternal check: skipped — no baseline was captured, so there is "
              "nothing to compare this draft against.")
    else:
        after = pangram_scan(out, work, "after")
        if after:
            pangram_delta(baseline, after)
            # Beside the score, never instead of it: the two moving in
            # opposite directions is the whole GH-219 finding.
            guard_warns = report_register(art, out)
            pangram_pair = (_pangram_summary(baseline[0]), _pangram_summary(after[0]))
        else:
            print(f"\nexternal check: the draft scan failed. The baseline stands "
                  f"at {baseline[0]}, so a later scan of this draft can still be "
                  f"compared against it.")

    # Last, so it can record the Pangram numbers when there are any. Written
    # beside the draft rather than into the temp dir, which the OS reaps.
    manifest = manifest_path(out)
    used = write_manifest(manifest, a, voice_dir, results, pangram_pair,
                          guard=guard_warns)
    print(f"\nprovenance: {manifest}")
    print(f"  {len(used)} distinct exemplars anchored this draft")

    # After the manifest, so the forensics survive: when the gate crashed on
    # every rewritable paragraph, nothing was ever verified and the "draft" is
    # a copy of the input. Success would present that copy as a rewrite.
    gated = [r for r in results
             if r["status"] not in ("skipped-short", "unselected", "excluded-key")]
    if gated and all(r["status"] == "gate-error" for r in gated):
        sys.exit("gate-error on every paragraph: the verification gate never "
                 "ran. The draft is an untouched copy — do not use it.")


if __name__ == "__main__":
    main()
