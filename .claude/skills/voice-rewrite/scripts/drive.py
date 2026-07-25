#!/usr/bin/env python3
"""drive.py — orchestrate the voice-rewrite pipeline over a whole article.

Stages per prose paragraph: retrieve anchors -> rewrite (Ollama) -> gate
(verify.py mechanical checks + de-ai lexical scan), with failure-classified
retries. Assembles gate-passing rewrites into a sibling draft file.

The driver applies the MECHANICAL gate only. Meaning entailment is a judgment
call and stays with the reviewing model (references/prompts.md); the emitted
draft is a set of candidates, not an accepted result.

Paragraph extraction and the coverage audit come from de-ai's
md_paragraphs.py, the canonical extractor shared by the prose skills: every
body line is classified (prose / heading / figure / table / code / reference /
blockquote / list / rule / blank), and a nonempty unaccounted list means the
parser skipped prose.

Usage:
  python3 drive.py --article <path.md> [--model gemma4:12b] [--out <path>]
                   [--retries 2] [--min-words 12] [--temperature 0.7]
                   [--coverage-only]
"""
import argparse, json, os, re, subprocess, sys, tempfile

SK = os.path.dirname(os.path.abspath(__file__))
DEAI = os.path.normpath(os.path.join(SK, "..", "..", "de-ai", "scripts", "detect-lexical.sh"))

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
    """The canonical extractor lives in de-ai (GH-167): one parser, so a block
    this driver treats as prose is the same block the metrics and anchors see."""
    sibling = os.path.normpath(os.path.join(SK, "..", "..", "de-ai", "scripts"))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        import md_paragraphs
        return md_paragraphs
    except ImportError as e:
        sys.exit(f"could not import de-ai md_paragraphs.py from {sibling}: {e}")


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
    ap.add_argument("--model", default=os.environ.get("VOICE_REWRITE_MODEL", "gemma4:12b"))
    ap.add_argument("--endpoint", default=os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434"))
    ap.add_argument("--out", help="draft path (default: <article>.vr-draft.md)")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--min-words", type=int, default=12)
    ap.add_argument("--temperature", default="0.7")
    ap.add_argument("--coverage-only", action="store_true",
                    help="parse + coverage audit only; no model calls")
    a = ap.parse_args()

    art = os.path.abspath(a.article)
    out = a.out or re.sub(r"\.md$", ".vr-draft.md", art)
    lines, fm_close, paras, coverage, unaccounted = parse_paragraphs(art, a.min_words)

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

    work = tempfile.mkdtemp(prefix="voice-rewrite-")
    results = []
    for n, (s, e, txt) in enumerate(paras, 1):
        rec = {"n": n, "lines": [s, e], "words": len(txt.split()), "orig": txt}
        if rec["words"] < a.min_words:
            rec["status"] = "skipped-short"; results.append(rec); continue
        pf = f"{work}/p{n:02d}.orig.txt"; open(pf, "w").write(txt)
        aj = run(["python3", f"{SK}/retrieve.py", "--text", pf, "--for", art, "--json"])
        at = run(["python3", f"{SK}/retrieve.py", "--text", pf, "--for", art])
        ajf = f"{work}/p{n:02d}.anchors.json"; open(ajf, "w").write(aj.stdout or "[]")
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
          "and de-ai over the assembled file.")


if __name__ == "__main__":
    main()
