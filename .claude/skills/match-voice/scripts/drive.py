#!/usr/bin/env python3
"""drive.py — orchestrate the match-voice pipeline over a whole article.

Stages per prose paragraph: retrieve anchors -> rewrite (Ollama) -> gate
(verify.py mechanical checks + filter-tells lexical scan), with failure-classified
retries. Assembles gate-passing rewrites into a sibling draft file.

The driver applies the MECHANICAL gate only. Meaning entailment is a judgment
call and stays with the reviewing model (references/prompts.md); the emitted
draft is a set of candidates, not an accepted result.

Paragraph extraction and the coverage audit come from md_paragraphs.py, the
canonical extractor shared by the prose skills: every body line is classified
(prose / heading / figure / table / code / reference / blockquote / list / rule
/ blank), and a nonempty unaccounted list means the parser skipped prose.

With --pangram the driver also measures whether the rewrite worked, scanning
the article before it starts and the draft when it finishes (GH-212). The
baseline has to be captured first because it cannot be reconstructed once the
paragraphs are replaced — which is why this belongs in the driver and not in a
procedure someone is expected to remember afterwards.

Usage:
  python3 drive.py --article <path.md> [--model gemma4:12b] [--out <path>]
                   [--retries 2] [--min-words 12] [--temperature 0.7]
                   [--coverage-only] [--pangram]
"""
import argparse, json, os, re, subprocess, sys, tempfile
from collections import Counter

SK = os.path.dirname(os.path.abspath(__file__))
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
            "delve, comprehensive, crucial). Plain declarative technical prose.")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _md_paragraphs():
    """One canonical extractor (GH-167), at the shared scripts root (GH-196):
    a block this driver treats as prose is the same block the metrics and the
    anchors see."""
    sibling = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        import md_paragraphs
        return md_paragraphs
    except ImportError as e:
        sys.exit(f"could not import md_paragraphs.py from {sibling}: {e}")


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


def register_metrics(path):
    """The local register numbers that move opposite to a falling AI score."""
    r = run(["python3", os.path.join(FILTER_TELLS, "detect-structural.py"),
             path, "--json"])
    try:
        d = json.loads(r.stdout)
        if isinstance(d, list):
            d = d[0]
        m = d.get("metrics", {})
    except (json.JSONDecodeError, IndexError, AttributeError):
        return {}
    return {k: m[k] for k in ("passive_enabling_per_500w", "salad_rate_per_100",
                              "opening_diversity") if k in m}


def report_register(article, draft):
    """Print register metrics before -> after, and flag divergence.

    A falling AI score with worsening register is the GH-219 failure: the
    objective met, the prose worse. Printing both together is what makes that
    visible instead of something you notice a week later.
    """
    b, a = register_metrics(article), register_metrics(draft)
    if not b or not a:
        return
    print("\nlocal register (lower is plainer, except opening_diversity):")
    worse = []
    for k in sorted(set(b) & set(a)):
        arrow = "->"
        bad = (a[k] > b[k]) if k != "opening_diversity" else (a[k] < b[k])
        print(f"  {k:26} {b[k]} {arrow} {a[k]}{'   WORSE' if bad else ''}")
        if bad:
            worse.append(k)
    if worse:
        print("  A falling AI score with worsening register is the score-only "
              "optimum, not a better draft — check the anchors (SKILL.md).",
              file=sys.stderr)


def pangram_delta(before, after):
    """Print fraction_ai before -> after and the still-flagged worklist."""
    r = run(["python3", PANGRAM_REPORT, "report", "--response", after[0],
             "--spans", after[1], "--baseline", before[0],
             "--baseline-spans", before[1]])
    if r.returncode != 0:
        print(f"pangram: comparison failed — {(r.stderr or '').strip()[:200]}",
              file=sys.stderr)
        return
    print("\nexternal check (Pangram, article -> draft):")
    print(r.stdout.rstrip())


def anchor_flags(a):
    """Anchor-selection flags to forward to retrieve.py."""
    f = []
    if a.voice_dir:
        f += ["--voice-dir", a.voice_dir]
    if a.role:
        f += ["--role", a.role]
    if a.stratum:
        f += ["--stratum", a.stratum]
    return f


def anchor_provenance(a, article):
    """Print which exemplars the anchors will be drawn from, BEFORE rewriting.

    The whole failure in GH-215 was invisible until the operator ran retrieve.py
    by hand after a 25-paragraph rewrite and found every anchor was an IEEE
    paper. Printing the mix first costs nothing and makes that obvious.
    """
    stylo = os.path.normpath(os.path.join(SK, "..", "..", "match-structure", "scripts"))
    if stylo not in sys.path:
        sys.path.insert(0, stylo)
    try:
        import voice_anchors as va
    except ImportError:
        print("anchors: match-structure not importable — cannot report the mix",
              file=sys.stderr)
        return
    d = a.voice_dir or va.discover(article)
    if not d:
        print("anchors: no writing-voice/ found — the rewrite has no target "
              "register; run plain filter-tells instead", file=sys.stderr)
        return
    pre = (True if a.stratum == "pre-ai"
           else False if a.stratum == "ai-era" else None)
    paths = va.sample_paths(d, role=a.role, pre_ai=pre)
    mix = Counter(r for _, r in paths)
    filt = " ".join(x for x in (f"role={a.role}" if a.role else "",
                                f"stratum={a.stratum}" if a.stratum else "") if x)
    print(f"anchors: {len(paths)} exemplars from {d}")
    print(f"         {dict(mix)}{'  [' + filt + ']' if filt else ''}")
    if not paths:
        print("         NOTHING MATCHES THE FILTER — every rewrite will run "
              "without anchors", file=sys.stderr)
    elif mix.get("author-voice", 0) == len(paths) and not a.role:
        # The GH-215 shape: an all-papers corpus behind a draft that may not
        # want academic register.
        print("         all author-voice; if this draft wants punch rather than "
              "precision, try --stratum pre-ai", file=sys.stderr)


def parse_paragraphs(path, min_words):
    """Return (lines, fm_close, paragraphs, coverage, unaccounted).

    Thin wrapper over the canonical extractor; signature preserved so the
    driver and its --coverage-only output are unchanged.
    """
    r = _md_paragraphs().parse_file(path)
    return r.lines, r.fm_close, r.paragraphs, r.coverage, r.unaccounted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    ap.add_argument("--model", default=os.environ.get("MATCH_VOICE_MODEL", "gemma4:12b"))
    ap.add_argument("--endpoint", default=os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434"))
    ap.add_argument("--out", help="draft path (default: <article>.vr-draft.md)")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--min-words", type=int, default=12)
    ap.add_argument("--temperature", default="0.7")
    ap.add_argument("--voice-dir",
                    help="exemplar corpus (default: discover writing-voice/ "
                         "upward from the article)")
    ap.add_argument("--role", choices=["author-voice", "venue-voice"],
                    help="hard filter anchors to one role")
    ap.add_argument("--stratum", choices=["pre-ai", "ai-era"],
                    help="pre-ai restricts anchors to diction-safe samples "
                         "across roles — use it when the draft needs punch and "
                         "the corpus is mostly papers")
    ap.add_argument("--coverage-only", action="store_true",
                    help="parse + coverage audit only; no model calls")
    ap.add_argument("--pangram", action="store_true",
                    help="measure the rewrite against an external detector. "
                         "UPLOADS this article and the draft to a third party "
                         "that retains them; passing the flag is the consent, "
                         "and it is asked for per document. Costs two scans.")
    a = ap.parse_args()

    art = os.path.abspath(a.article)
    out = a.out or re.sub(r"\.md$", ".vr-draft.md", art)
    lines, fm_close, paras, coverage, unaccounted = parse_paragraphs(art, a.min_words)
    anchor_provenance(a, art)

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

    results = []
    for n, (s, e, txt) in enumerate(paras, 1):
        rec = {"n": n, "lines": [s, e], "words": len(txt.split()), "orig": txt}
        if rec["words"] < a.min_words:
            rec["status"] = "skipped-short"; results.append(rec); continue
        pf = f"{work}/p{n:02d}.orig.txt"; open(pf, "w").write(txt)
        rflags = anchor_flags(a)
        aj = run(["python3", f"{SK}/retrieve.py", "--text", pf, "--for", art,
                  *rflags, "--json"])
        at = run(["python3", f"{SK}/retrieve.py", "--text", pf, "--for", art, *rflags])
        ajf = f"{work}/p{n:02d}.anchors.json"; open(ajf, "w").write(aj.stdout or "[]")
        # Which exemplars anchored THIS paragraph, with scores, so a bad mix is
        # diagnosable from results.json instead of by re-running retrieval.
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
            if note:
                cmd += ["--retry-note", note]
            rw = run(cmd)
            if rw.returncode != 0 or not rw.stdout.strip():
                rec["status"] = "rewrite-error"; rec["err"] = (rw.stderr or "")[:200]
                break
            cf = f"{work}/p{n:02d}.cand.txt"; open(cf, "w").write(rw.stdout.strip())
            vf = run(["python3", f"{SK}/verify.py", "--original", pf, "--rewrite", cf,
                      "--anchors-json", ajf, "--json"])
            de = run(["bash", DEAI, cf])
            if vf.returncode == 0 and de.returncode == 0:
                rec["status"] = "accepted-mechanical"
                rec["cand"] = rw.stdout.strip()
                rec["attempt"] = attempt + 1
                break
            # classify for the retry note
            fj = vf.stdout if vf.stdout.strip().startswith("{") else "{}"
            notes = []
            if '"numbers"' in fj or '"citations"' in fj or '"terms"' in fj:
                notes.append(NUM_NOTE)
            if '"similarity"' in fj:
                notes.append(COPY_NOTE)
            if de.returncode != 0:
                notes.append(REG_NOTE)
            note = " ".join(notes) or COPY_NOTE
            rec["status"] = "kept-original"
            rec["last_fail"] = {"verify": json.loads(fj) if fj != "{}" else vf.stdout[:150],
                                "deai": de.returncode}
        results.append(rec)

    # assemble
    accept = {r["n"]: r["cand"] for r in results if r.get("cand")}
    rng = {r["n"]: tuple(r["lines"]) for r in results}
    out_lines = list(lines)
    for n in sorted(accept, reverse=True):
        s, e = rng[n]
        orig = "\n".join(out_lines[s - 1:e])
        cand = accept[n]
        if orig.strip().startswith("**") and orig.strip().endswith("**") \
                and not cand.strip().startswith("**"):
            cand = "**" + cand.strip() + "**"
        out_lines[s - 1:e] = [cand]
    open(out, "w").write("\n".join(out_lines))
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
            if f.get("deai"):
                why = (why + "," if why else "") + "register"
            print(f"  kept p{r['n']:02d} (L{r['lines'][0]}): {why}")
    print("\nMechanical gate only. Before accepting the draft: run the meaning-"
          "entailment review (references/prompts.md) on each accepted paragraph, "
          "and filter-tells over the assembled file.")

    # The outcome measure, last because it is the result of the run. Without a
    # baseline there is nothing to compare, so the second scan is not spent.
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
            report_register(art, out)
        else:
            print(f"\nexternal check: the draft scan failed. The baseline stands "
                  f"at {baseline[0]}, so a later scan of this draft can still be "
                  f"compared against it.")


if __name__ == "__main__":
    main()
