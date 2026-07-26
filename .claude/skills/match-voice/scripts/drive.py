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
            "delve, comprehensive, crucial). Do not trade it for chatty filler "
            "either: no just, actually, really, basically, simply, honestly. "
            "Plain declarative technical prose.")
MARKUP_NOTE = ("Reproduce the markdown formatting of the original exactly: every **bold** "
               "span, *italic* span, and `code` span, in the same places. If the "
               "paragraph opens with a bold sentence, your rewrite must open with a "
               "bold sentence too — it is a lead-in, not ordinary prose.")


def run(cmd, **kw):
    # errors="replace": a single non-UTF-8 byte from any child would
    # otherwise raise UnicodeDecodeError and take down the whole run.
    # Measured (GH-229): a published article with smart quotes killed
    # both arms of an A/B before either produced a line.
    return subprocess.run(cmd, capture_output=True, text=True,
                          errors="replace", **kw)


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


def report_register(article, draft):
    """Register markers before -> after, via the shared reporter (GH-222).

    One marker vocabulary everywhere: the numbers in issues and the numbers in
    run output are the same numbers. A falling AI score with rising markers is
    the GH-219/GH-220 failure — the objective met, the prose worse.
    """
    r = run([sys.executable, os.path.join(SHARED, "register_markers.py"),
             "--compare", article, draft])
    if r.returncode == 0 and r.stdout.strip():
        print()
        print(r.stdout.rstrip())
        if r.stderr.strip():
            print(r.stderr.rstrip(), file=sys.stderr)


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
    if a.anchor_tags:
        f += ["--tags", a.anchor_tags]
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
    n = len(va.sample_paths(d, role=a.role, pre_ai=pre, tags=tags))
    out = []
    if a.stratum and len(va.sample_paths(d, role=a.role, pre_ai=None, tags=tags)) == n:
        out.append(f"stratum={a.stratum}")
    if a.role and len(va.sample_paths(d, role=None, pre_ai=pre, tags=tags)) == n:
        out.append(f"role={a.role}")
    if tags and len(va.sample_paths(d, role=a.role, pre_ai=pre, tags=None)) == n:
        out.append(f"tags={a.anchor_tags}")
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
        for x in va.anchors(d, txt, k=3, role=a.role, pre_ai=pre, tags=tags):
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

    Returns the discovered voice directory, or None when there is none.
    """
    va = _voice_anchors_module()
    if va is None:
        print("anchors: match-structure not importable — cannot report the mix",
              file=sys.stderr)
        return None
    d = a.voice_dir or va.discover(article)
    if not d:
        print("anchors: no writing-voice/ found — the rewrite has no target "
              "register; run plain filter-tells instead", file=sys.stderr)
        return None

    pre, tags = _selection(a)
    paths = va.sample_paths(d, role=a.role, pre_ai=pre, tags=tags)
    mix = Counter(r for _, r in paths)
    filt = " ".join(x for x in (f"role={a.role}" if a.role else "",
                                f"stratum={a.stratum}" if a.stratum else "",
                                f"tags={a.anchor_tags}" if a.anchor_tags else "") if x)
    print(f"anchors: {len(paths)} exemplars available from {d}")
    print(f"         pool {dict(mix)}{'  [' + filt + ']' if filt else ''}")

    for name in inert_filters(va, d, a):
        print(f"         INERT FILTER {name} selects the whole pool — it is not "
              f"steering anything on this corpus", file=sys.stderr)

    if not paths:
        print("         NOTHING MATCHES THE FILTER — every rewrite will run "
              "without anchors", file=sys.stderr)
        return d
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
    ap.add_argument("--anchor-tags",
                    help="comma-separated register tags; similarity still "
                         "ranks WITHIN the selected pool. Use when the register "
                         "that fits is not the one topically nearest")
    ap.add_argument("--stratum", choices=["pre-ai", "ai-era"],
                    help="pre-ai restricts anchors to diction-safe samples "
                         "across roles. Inert on a corpus whose diction-eligible "
                         "samples are all pre-AI — the run says so when it is. "
                         "To steer register, reach for --role/--anchor-tags")
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
    a = ap.parse_args()

    art = os.path.abspath(a.article)
    out = a.out or re.sub(r"\.md$", ".vr-draft.md", art)
    lines, fm_close, paras, coverage, unaccounted = parse_paragraphs(art, a.min_words)
    # Long enough to be rewritten is the same bar the loop uses, so the reported
    # selection is the selection the run would actually make.
    rewritable = [p for p in paras if len(p[2].split()) >= a.min_words]
    anchor_provenance(a, art, rewritable, full=a.dry_run)

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
            # Repair before verifying, not at assembly time: the gate now checks
            # markup (GH-232), so a candidate the driver would have patched on
            # the way out has to be patched before the gate reads it, or the
            # repair and the check disagree about the same paragraph.
            cand_text = restore_full_bold(txt, rw.stdout.strip())
            cf = f"{work}/p{n:02d}.cand.txt"; open(cf, "w").write(cand_text)
            vf = run(["python3", f"{SK}/verify.py", "--original", pf, "--rewrite", cf,
                      "--anchors-json", ajf, "--json"])
            de = run(["bash", DEAI, cf])
            if vf.returncode == 0 and de.returncode == 0:
                rec["status"] = "accepted-mechanical"
                rec["cand"] = cand_text
                rec["attempt"] = attempt + 1
                break
            # classify for the retry note
            fj = vf.stdout if vf.stdout.strip().startswith("{") else "{}"
            notes = []
            if '"numbers"' in fj or '"citations"' in fj or '"terms"' in fj:
                notes.append(NUM_NOTE)
            if '"markup"' in fj:
                notes.append(MARKUP_NOTE)
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
        # The wholly-bold repair happens before the gate now, so an accepted
        # candidate already carries the markup it is going to carry.
        out_lines[s - 1:e] = [accept[n]]
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
