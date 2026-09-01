#!/usr/bin/env python3
"""Tighten an article through the second model family, pairs in-prompt.

The drafting model never rewrites here. GH-222 measured why: rules applied by
an instruction-tuned model pulled a paper excerpt to within distance 6.5 of
the AI-draft fingerprint — from 26.1 — overshooting the draft's own passive
rate on the way. The catalog's enforcement register and the assistant register
are the same place, so enforcement moves to a different model family shown
transformations instead of rules.

Per paragraph: run the checker, select the pairs for the rules that fired
(TS-01 always), prompt the Ollama model with pairs only, gate the result with
match-voice's verify.py (citations, numbers, meaning — compression is where
meaning goes), and keep the original wherever the gate fails. Register markers
print before -> after at the end; rising markers on a shrinking draft is the
GH-220 failure and the reason this driver exists.

Usage:
  tighten.py --article <path.md> [--model gemma4:12b] [--out <path>]
             [--retries 1] [--min-words 12] [--check-only]

No key, no endpoint: fails loudly. Never falls back to a drafting-model
rewrite — that would reintroduce the fingerprint this skill exists to avoid.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

SK = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
MATCH_VOICE = os.path.normpath(os.path.join(SK, "..", "..", "match-voice", "scripts"))
MATCH_STRUCTURE = os.path.normpath(os.path.join(SK, "..", "..", "match-structure", "scripts"))
PANGRAM = os.path.join(SHARED, "pangram.py")
PANGRAM_REPORT = os.path.join(SHARED, "pangram_report.py")

PROMPT = """Rewrite the paragraph below more tightly. Imitate these
transformations — they show wordy phrasing beside its tight form:

{pairs}

Rules for the rewrite:
- Preserve every number, citation marker (bracketed numbers and @-keys), and technical term exactly; never write a marker that is not already in the paragraph.
- Do not add information, opinions, or transitions.
- Do not shorten for its own sake: if a sentence is already tight, keep it.
- Output only the rewritten paragraph, nothing else.

PARAGRAPH:
{paragraph}
"""

LOCK_RULE = ("- Tokens like [[LOCK-1]] stand for hand-written text that must not "
             "change: copy each one exactly once, unchanged, in the sentence "
             "where it sits. Never remove, reword, duplicate, or invent one.")


def run(cmd, **kw):
    # errors="replace": a single non-UTF-8 byte from any child would
    # otherwise raise UnicodeDecodeError and take down the whole run.
    # Measured (GH-229): a published article with smart quotes killed
    # both arms of an A/B before either produced a line.
    return subprocess.run(cmd, capture_output=True, text=True,
                          errors="replace", **kw)


def _mods():
    for d in (SHARED, MATCH_VOICE, SK):
        if d not in sys.path:
            sys.path.insert(0, d)
    import prose_document, register_markers, pairs as pairs_mod, check_style
    return prose_document, register_markers, pairs_mod, check_style


def _sentence_stats(text):
    """Compute sentence_length_mean and sentence_length_stdev from prose text."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", text)
             if len(s.strip()) > 2]
    if not sents:
        return 0.0, 0.0
    lengths = [len(re.findall(r"\w+", s)) for s in sents]
    mean = sum(lengths) / len(lengths)
    var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return mean, var ** 0.5


def write_draft(doc, ext, out_lines, tightened, out):
    """Write accepted candidates into the draft at `out`; return the lines
    the sentence-floor advisory should measure.

    Both formats go back through the document model. YAML because ruamel
    round-trip keeps comments, key order, and structure — raw line splicing
    dropped bare prose over keys and block markers (GH-358). Markdown
    because replace() is where inline lock anchors are re-expanded into
    their bytes (GH-82): raw line splicing wrote the candidate as the model
    returned it, so a `[[LOCK-n]]` token would have landed in the draft as
    text. Descending order, so a replacement that changes later positions
    cannot shift earlier ones. `out_lines` is the buffer the markdown line
    splice used and is no longer read.

    A candidate whose anchor tokens do not match is refused by splice();
    its record is marked ``lock-refused`` and the paragraph keeps its
    original.
    """
    if not tightened:
        # Nothing accepted: emit the untouched source rather than a
        # re-emission, which for YAML normalizes wrapping and sequence
        # offsets and turns a no-op run into a noisy diff (GH-360).
        with open(out, "w", encoding="utf-8") as f:
            f.write(doc.raw)
        return _measure_lines(doc, ext)
    span_locks = _span_locks()
    for rec in sorted(tightened, key=lambda r: -r["n"]):
        try:
            doc.replace(rec["n"] - 1, rec["cand"])
        except span_locks.LockError as e:
            print(f"  LOCK-REFUSED p{rec['n']:02d}: {e}", file=sys.stderr)
            rec["status"] = "lock-refused"
            rec.pop("cand", None)
    doc.save_as(out)
    return _measure_lines(doc, ext)


def _measure_lines(doc, ext):
    """What the sentence-floor advisory measures: prose scalars for YAML,
    the file's own lines for markdown."""
    if ext in (".yaml", ".yml"):
        return [p.text for p in doc.paragraphs]
    return doc.text().split("\n")


def _span_locks():
    if SHARED not in sys.path:
        sys.path.insert(0, SHARED)
    import span_locks
    return span_locks


def _doc_sentence_stats(lines):
    """Sentence stats over a full document (list of lines), prose only."""
    for d in (SHARED,):
        if d not in sys.path:
            sys.path.insert(0, d)
    import md_paragraphs
    r = md_paragraphs.parse("\n".join(lines))
    prose = " ".join(txt for _, _, txt in r.paragraphs)
    return _sentence_stats(prose)


def pangram_scan(path, work, tag):
    """Build prose-only payload and scan. Same path as drive.py's pangram_scan.

    Returns (response_path, spans_path), or None on failure.
    """
    payload = os.path.join(work, f"{tag}.payload.txt")
    p = run([sys.executable, PANGRAM_REPORT, "payload", "--article", path,
             "--out", payload])
    if p.returncode != 0:
        print(f"pangram: {tag} payload failed — {(p.stderr or p.stdout).strip()[:200]}",
              file=sys.stderr)
        return None
    resp = os.path.join(work, f"{tag}.json")
    s = run([sys.executable, PANGRAM, "--text", payload, "--json"])
    if s.returncode != 0 or not s.stdout.strip():
        print(f"pangram: {tag} scan skipped — {(s.stderr or 'no response').strip()[:200]}",
              file=sys.stderr)
        return None
    open(resp, "w").write(s.stdout)
    return resp, os.path.splitext(payload)[0] + ".spans.json"


def pangram_delta(before, after):
    """Print Pangram before -> after using pangram_report report."""
    r = run([sys.executable, PANGRAM_REPORT, "report", "--response", after[0],
             "--spans", after[1], "--baseline", before[0],
             "--baseline-spans", before[1]])
    if r.returncode != 0:
        print(f"pangram: comparison failed — {(r.stderr or '').strip()[:200]}",
              file=sys.stderr)
        return
    print("\nexternal check (Pangram, article -> tightened):")
    print(r.stdout.rstrip())


def tighten_paragraph(text, fired_rules, model, endpoint, temperature, timeout):
    """One paragraph through the second model family. Returns the candidate."""
    _, _, pairs_mod, _ = _mods()
    plist = pairs_mod.for_rules(sorted(fired_rules))
    prompt = PROMPT.format(pairs=pairs_mod.as_prompt(plist), paragraph=text)
    if _span_locks().tokens_in(text):
        # The model has no other way to know [[LOCK-n]] is not prose (GH-82).
        prompt = prompt.replace("\nPARAGRAPH:\n", f"{LOCK_RULE}\n\nPARAGRAPH:\n")
    import rewrite as rw            # match-voice's Ollama client
    return rw.generate(prompt, endpoint=endpoint, model=model,
                       temperature=temperature, timeout=timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True)
    # TIGHTEN_STYLE_MODEL, not MATCH_VOICE_MODEL: this driver borrowed the
    # neighbor's env var along with its transport, which meant configuring
    # match-voice silently reconfigured tighten-style too. Cohere default per
    # the pipeline conversion (GH-193); gemma4:12b is the keyless/local
    # fallback.
    ap.add_argument("--model", default=os.environ.get(
        "TIGHTEN_STYLE_MODEL", "cohere:command-a-03-2025"))
    ap.add_argument("--endpoint", default=os.environ.get("OLLAMA_ENDPOINT",
                                                         "http://localhost:11434"))
    ap.add_argument("--out", help="default: <article>.tight.md")
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--min-words", type=int, default=12)
    ap.add_argument("--temperature", default="0.4")
    ap.add_argument("--timeout", type=int,
                    default=int(os.environ.get("TIGHTEN_STYLE_TIMEOUT", "300")))
    ap.add_argument("--check-only", action="store_true",
                    help="report per-paragraph rule findings; no model calls")
    ap.add_argument("--pangram", action="store_true",
                    help="run external detector before/after (requires key)")
    ap.add_argument("--sent-floor", nargs=2, type=float, metavar=("MEAN", "SD"),
                    help="minimum sentence_length_mean and stdev; logs an "
                         "advisory when candidates push below this floor")
    ap.add_argument("--venue",
                    help="venue profile name (writing-voice/venues/, GH-338): "
                         "its targets supply the sentence floor and its "
                         "hedge_policy sets the TS-08 threshold; explicit "
                         "--sent-floor still wins")
    ap.add_argument("--exclude-keys", nargs="*", default=None,
                    help="YAML key-path globs whose paragraphs skip rewriting "
                         "(default for YAML: section_goal, goals.*.goal, "
                         "acceptance.*, meta.*). Pass --exclude-keys with no "
                         "args to disable")
    ap.add_argument("--must-preserve", nargs="*", default=None,
                    help="exact phrases that must survive rewriting; verify.py "
                         "rejects candidates that lose any of them")
    a = ap.parse_args()

    pd, rm, _, cs = _mods()
    art = os.path.abspath(a.article)

    # Venue profile: tighten toward the venue's measured register, not the
    # global author floor. The profile's targets become the sentence floor —
    # the venue density is where tightening stops, never a level to shoot
    # past — and hedge_policy keys the TS-08 threshold (zero for the book
    # voice, calibrated for academic prose).
    hedge_stack = None
    if a.venue:
        if MATCH_STRUCTURE not in sys.path:
            sys.path.insert(0, MATCH_STRUCTURE)
        import venue_profile as vprof
        try:
            prof = vprof.resolve(start_path=art, venue=a.venue)
        except (FileNotFoundError, ValueError) as e:
            sys.exit(f"venue profile: {e}")
        hedge_stack = cs.HEDGE_POLICY_STACK.get(prof.get("hedge_policy"))
        targets = prof.get("targets") or {}
        if not a.sent_floor:
            mean = targets.get("sentence_length_mean")
            sd = targets.get("sentence_length_stdev")
            if mean is not None and sd is not None:
                a.sent_floor = [float(mean), float(sd)]
        print(f"venue: {prof['name']} (hedge_policy="
              f"{prof.get('hedge_policy')}, sent_floor="
              f"{a.sent_floor or 'unset'})")
        for w in prof.get("_warnings", []):
            print(f"venue profile warning: {w}", file=sys.stderr)
    ext = os.path.splitext(art)[1].lower()
    out = a.out or re.sub(r"\.(md|yaml|yml)$", ".tight\\1", art)
    if out == art:
        out = art + ".tight"
    doc = pd.ProseDocument.open(art)
    parsed = doc.to_parse_result()

    exclude = set()
    if ext in (".yaml", ".yml"):
        patterns = (a.exclude_keys if a.exclude_keys is not None
                    else pd.YAML_EXCLUDE_KEYS_DEFAULT)
        if patterns:
            exclude = pd.excluded_indices(doc.paragraphs, patterns)
            if exclude:
                print(f"exclude-keys: skipping {len(exclude)} contract-field "
                      f"paragraph(s): {sorted(exclude)}")

    # Findings per paragraph line-range, from the checker run once whole-file.
    all_findings = cs.check(art, hedge_stack=hedge_stack)
    by_para = {}
    for f in all_findings:
        for start, end, _ in parsed.paragraphs:
            if start <= f["line"] <= end:
                by_para.setdefault(start, set()).add(f["rule"])
                break

    if a.check_only:
        for start, end, txt in parsed.paragraphs:
            rules = sorted(by_para.get(start, []))
            print(f"  L{start:>4} {len(txt.split()):>4}w  "
                  f"{','.join(rules) if rules else '-'}  | {txt[:60]}")
        sys.exit(0)

    for d in (MATCH_VOICE,):
        if d not in sys.path:
            sys.path.insert(0, d)
    import rewrite as rw
    ok, msg = rw.check_server(a.endpoint, a.model)
    if not ok:
        sys.exit(msg)
    print(f"model: {msg}")

    work = tempfile.mkdtemp(prefix="tighten-")

    pangram_before = None
    if a.pangram:
        pangram_before = pangram_scan(art, work, "before")

    results, out_lines = [], list(parsed.lines)
    for n, (start, end, txt) in enumerate(parsed.paragraphs, 1):
        rec = {"n": n, "lines": [start, end], "words": len(txt.split()),
               "rules": sorted(by_para.get(start, []))}
        if rec["words"] < a.min_words:
            rec["status"] = "skipped-short"
            results.append(rec)
            continue
        if n in exclude:
            rec["status"] = "excluded-key"
            results.append(rec)
            continue
        pf = os.path.join(work, f"p{n:02d}.orig.txt")
        with open(pf, "w") as f:
            f.write(txt)
        status = "kept-original"
        aborted = False
        for attempt in range(1 + a.retries):
            try:
                cand = tighten_paragraph(txt, rec["rules"], a.model,
                                         a.endpoint, a.temperature, a.timeout)
            except RuntimeError as e:
                # The server was up at preflight; a transport failure now means
                # it is gone. Stop the run — remaining paragraphs keep their
                # originals, and nothing falls back to a drafting-model
                # rewrite.
                print(f"p{n:02d}: {e}", file=sys.stderr)
                for m, (s2, e2, t2) in enumerate(parsed.paragraphs[n:], n + 1):
                    results.append({"n": m, "lines": [s2, e2],
                                    "words": len(t2.split()),
                                    "status": "kept-original", "rules": []})
                aborted = True
                break
            if not cand or not cand.strip():
                break
            import verify as _vmod
            cand_clean = _vmod.normalize_ascii(cand.strip())
            # A candidate that dropped, duplicated, or invented a lock
            # anchor can never carry the locked bytes back (GH-82): retry
            # rather than let the gate judge prose that cannot be written.
            lock_fault = _span_locks().check_tokens(txt, cand_clean)
            if lock_fault:
                print(f"p{n:02d}: lock anchor fault, retrying: {lock_fault}",
                      file=sys.stderr)
                continue
            cf = os.path.join(work, f"p{n:02d}.cand.txt")
            with open(cf, "w") as f:
                f.write(cand_clean)
            vcmd = [sys.executable, os.path.join(MATCH_VOICE, "verify.py"),
                    "--original", pf, "--rewrite", cf, "--json"]
            if a.must_preserve:
                vcmd += ["--must-preserve"] + a.must_preserve
            v = run(vcmd)
            if v.returncode == 0:
                rec["cand"] = cand_clean
                status = "tightened"
                break
        rec["status"] = status
        results.append(rec)
        if aborted:
            break

    tightened = [r for r in results if r.get("cand")]
    locked = doc.locked_spans()      # read before write_draft mutates doc
    stats_lines = write_draft(doc, ext, out_lines, tightened, out)
    # The GH-57 invariant, checked on the bytes written rather than on the
    # path that wrote them (GH-82). Results are saved first so the model
    # calls are not lost to a driver bug.
    with open(out, encoding="utf-8") as f:
        missing = _span_locks().verify_preserved(locked, f.read())
    if missing:
        with open(os.path.join(work, "results.json"), "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nLOCK VIOLATION: {len(missing)} locked span(s) from {art} are "
              f"not byte-identical in {out}:", file=sys.stderr)
        for span in missing:
            print(f"  {span[:100]!r}", file=sys.stderr)
        print(f"results: {work}/results.json", file=sys.stderr)
        sys.exit(3)

    # Post-hoc floor: advisory — log candidates that push sentence stats below
    # the human band, but do not revert them (GH-268).
    if a.sent_floor and tightened:
        floor_mean, floor_sd = a.sent_floor
        cur_mean, cur_sd = _doc_sentence_stats(stats_lines)
        if cur_mean < floor_mean or cur_sd < floor_sd:
            below = []
            by_shortening = sorted(
                tightened,
                key=lambda r: r["words"] - len(r["cand"].split()),
                reverse=True)
            for rec in by_shortening:
                below.append(f"p{rec['n']:02d}")
            print(f"  sent-floor advisory: document below floor "
                  f"(floor: mean={floor_mean}, sd={floor_sd}, "
                  f"actual: mean={cur_mean:.1f}, sd={cur_sd:.1f}). "
                  f"Largest shorteners: {', '.join(below[:5])}")

    with open(os.path.join(work, "results.json"), "w") as f:
        json.dump(results, f, indent=2)

    # GH-209: persistent changed-paragraph sidecar for the scoped
    # filter-tells pass — results.json above lives in a mkdtemp the OS
    # reaps. 1-based md_paragraphs prose numbers.
    sidecar = out + ".tighten.json"
    with open(sidecar, "w") as f:
        json.dump({"changed_paragraphs": sorted(r["n"] for r in tightened)}, f)

    from collections import Counter
    print(f"draft: {out}\nwork:  {work}/results.json")
    print(f"changed-paragraph sidecar: {sidecar}")
    for k, v in sorted(Counter(r["status"] for r in results).items()):
        print(f"  {k}: {v}")

    # The point of the exercise: did the pass move toward the assistant
    # register? Markers before -> after, same vocabulary as every report.
    r = run([sys.executable, os.path.join(SHARED, "register_markers.py"),
             "--compare", art, out])
    if r.returncode == 0:
        print()
        print(r.stdout.rstrip())
        if r.stderr.strip():
            print(r.stderr.rstrip(), file=sys.stderr)

    if a.pangram and pangram_before:
        pangram_after = pangram_scan(out, work, "after")
        if pangram_after:
            pangram_delta(pangram_before, pangram_after)


if __name__ == "__main__":
    main()
