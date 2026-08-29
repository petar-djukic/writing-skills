#!/usr/bin/env python3
"""Burstiness pass — raise sentence-length variance without changing meaning.

Burstiness is the coefficient of variation of sentence lengths. On a plain
stylometric model it is one of two editable features that separate human from
machine prose; the other is AI-phrase density, which filter-tells already
attacks. Nothing in the pipeline deliberately moved this one until now.

The measured effect (GH-129, one article, three arms, prose-only on Pangram
3.3.2):

    arm A baseline                       CV 0.621   Pangram 0.445
    arm B burstiness                     CV 0.690   Pangram 0.259
    arm C control, rhythm held           CV 0.621   Pangram 0.436

Arm C is why this script has a --control mode. A model pass that does not
change rhythm moved neither number, so the drop in B is the burstiness itself
rather than diction relaundering — and the only way to keep claiming that on a
new draft is to run the control alongside, every time.

The generating model is deliberately NOT Claude: prose diction goes to a
second family, per the pipeline's diction-vs-labelling split. Transport is the
Ollama HTTP API through match-voice's shared client, never `ollama run` — see
generate() in rewrite.py for what a captured pipe did to a thinking model's
output.

Ordering contract (GH-57): this is a pre-terminal stage. Locked spans are
excised before the model sees a paragraph and spliced back byte-identical,
and every candidate clears match-voice's verification gate before it is
spliced at all. A paragraph that fails any gate keeps its original text; the
run reports which and why, and never repairs a rejected candidate.

Usage:
  burstiness.py --article draft.md [--out draft-bursty.md]
                [--control] [--model gemma4:31b-cloud] [--endpoint URL]
                [--temperature 0.7] [--min-words 25] [--timeout 300]
                [--dry-run] [--json]

Exit: 0 the pass ran (whatever each paragraph's verdict), 1 a run-level
failure (unreachable model, unreadable article, locked span lost), 2 usage.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import rewrite as _rw          # noqa: E402  shared Ollama transport
import verify as _vf           # noqa: E402  the acceptance gate

DEFAULT_MODEL = os.environ.get("BURSTINESS_MODEL", "gemma4:31b-cloud")
DEFAULT_TIMEOUT = int(os.environ.get("BURSTINESS_TIMEOUT", "300"))

# Paragraphs below this have no rhythm to reshape: a two-sentence aside cannot
# alternate long and short without becoming a different paragraph.
DEFAULT_MIN_WORDS = 25

# Word-count band a candidate must land in. A burstiness rewrite splits
# sentences, so it grows; past 1.6x it is adding content, and below 0.5x it is
# summarising. Both are meaning changes the entailment gate would catch later
# and more expensively.
WORD_GROWTH_MAX = 1.6
WORD_SHRINK_MIN = 0.5

BAN_RULES = """- Never use em-dashes or en-dashes. Use periods, commas, or semicolons only.
- Do not use the "X, not Y" construction or tricolons. No new rhetorical flourish, no new AI tells.
- Keep the author's plain diction. Do not fancy up the words."""

BURSTINESS_SYSTEM = f"""You are an editor increasing the BURSTINESS of a paragraph: the variance in sentence length. Human prose alternates long and short sentences; machine prose is evenly paced. Your ONLY job is to vary sentence lengths harder while keeping the meaning identical.

Rules, all mandatory:
- Preserve meaning exactly. Change no facts, numbers, names, or citation markers like [1] [2] [@key].
- Do not add or remove information. Do not summarize.
- Split some long sentences into a long one plus a short punchy one. Occasionally use a deliberate short fragment.
- Keep at least one genuinely long sentence per paragraph so the contrast is real.
{BAN_RULES} Only reshape sentence boundaries and length.
- Output ONLY the rewritten paragraph. No preamble, no quotes, no explanation."""

CONTROL_SYSTEM = f"""You are an editor lightly copyediting a paragraph. Your ONLY job is to fix any awkwardness while keeping the meaning and sentence structure essentially the same.

Rules, all mandatory:
- Preserve meaning exactly. Change no facts, numbers, names, or citation markers like [1] [2] [@key].
- Do not add or remove information. Do not summarize.
- Do not change the sentence lengths or rhythm. Keep the same number of sentences.
{BAN_RULES}
- Output ONLY the rewritten paragraph. No preamble, no quotes, no explanation."""

# Appended only to paragraphs that actually carry an anchor token. Naming the
# token unconditionally teaches the model to produce one: on the first
# validation run, 6 of 21 paragraphs were rejected for inventing [[LOCK-n]] in
# a draft with zero locked spans (GH-129). A rule about a thing the text does
# not contain is an instruction to add it.
LOCK_RULE = ("\n\nThe text contains {n} token(s) of the form [[LOCK-n]]. Reproduce "
             "each one exactly as it appears, once each, in the same order. "
             "They are markers, not words: do not translate, rename, or "
             "invent them.")

LEAD_IN = re.compile(
    r"^\s*(?:rewritten paragraph|rewrite|output|paragraph|result|here(?:'s| is)"
    r"[^:\n]{0,40})\s*:\s*", re.IGNORECASE)

# The two banned constructions, as filter-tells defines them
# (detect-structural.py). Copied rather than imported: that module's filename
# is not importable, and its numbers are per-500-word densities calibrated on
# whole documents. What a gate needs is the opposite — did THIS paragraph gain
# one — so the shapes are shared and the arithmetic is not.
TRICOLON = re.compile(
    r"[^,.;:\n]{3,60},\s+[^,.;:\n]{3,60},\s+and\s+[^,.;:\n]{3,60}")
COMMA_NOT = re.compile(r",\s+not\s+[^,.?!]{3,40}[.?!]")
DASHES = re.compile(r"[—–]")


def _shared_scripts():
    """The shared root that carries prose_document and span_locks."""
    sibling = os.path.normpath(os.path.join(HERE, "..", "..", "..", "scripts"))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    return sibling


def _prose_document():
    sibling = _shared_scripts()
    try:
        import prose_document
        return prose_document
    except ImportError as e:
        sys.exit(f"could not import prose_document.py from {sibling}: {e}")


def _span_locks():
    _shared_scripts()
    import span_locks
    return span_locks


def _style():
    """match-structure's metrics engine, for the CV this pass exists to move."""
    sibling = os.path.normpath(
        os.path.join(HERE, "..", "..", "match-structure", "scripts"))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        import style
        return style
    except ImportError as e:
        sys.exit(f"could not import style.py from {sibling}: {e}")


def _prose_burstiness(style_mod, doc):
    """CV over the paragraphs the pass can touch, never the raw file.

    A document's headings, code fences, and table rows are not sentences, and
    counting them buries the number this pass exists to move: the first
    validation draft measured CV 1.399 whole-file against 0.503 prose-only.
    This is the same view pangram_report builds its payload from, so the two
    measurements compare.
    """
    prose = "\n\n".join(p.text for p in doc.paragraphs)
    return style_mod.burstiness_stats(style_mod.sentence_lengths(prose))


def build_prompt(paragraph, span_locks):
    prompt = f"Paragraph:\n{paragraph}\n\nRewritten paragraph:"
    n = len(span_locks.tokens_in(paragraph))
    if n:
        prompt = (f"Paragraph:\n{paragraph}" + LOCK_RULE.format(n=n)
                  + "\n\nRewritten paragraph:")
    return prompt


def normalize(text):
    """Strip the wrapper a model puts around an answer, and the banned dashes.

    Dash removal is a substitution, not a rejection: an em-dash is the
    cheapest way for a model to fake a rhythm change, and turning it into the
    sentence break it was imitating is the edit the pass wanted anyway. What
    survives normalization still faces the gate.
    """
    out = text.strip()
    out = LEAD_IN.sub("", out).strip()
    if len(out) > 1 and out[0] == out[-1] == '"' and out.count('"') == 2:
        out = out[1:-1].strip()
    out = out.replace(" — ", ". ").replace("—", ". ")
    out = out.replace(" – ", ", ").replace("–", ", ")
    out = re.sub(r"\.\s*\.", ".", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def defect_counts(text):
    """The banned constructions this pass may not introduce."""
    return {
        "tricolon": len(TRICOLON.findall(text)),
        "x-not-y": len(COMMA_NOT.findall(text)),
        "dash": len(DASHES.findall(text)),
    }


def added_defects(original, candidate):
    """Defect classes the candidate has more of than the original.

    A delta, never a level. The original is the author's text and may hold
    any of these on purpose; a pass that reshapes rhythm has no business
    removing them, and no business adding one either.
    """
    before, after = defect_counts(original), defect_counts(candidate)
    return {k: {"before": before[k], "after": after[k]}
            for k in before if after[k] > before[k]}


def sentence_count(style_mod, text):
    return len(style_mod.split_sentences(style_mod.strip_markdown(text)))


def judge(original, candidate, style_mod, span_locks, min_words=None):
    """Accept or reject one candidate. Returns (accepted, status).

    Fails closed: anything unrecognised is a rejection, and a rejected
    paragraph keeps its original text rather than being repaired.
    """
    status = {}
    if not candidate:
        return False, {"verdict": "rejected", "reason": "empty-response"}

    w_in, w_out = len(original.split()), len(candidate.split())
    status["words"] = {"before": w_in, "after": w_out}
    if w_out > w_in * WORD_GROWTH_MAX or w_out < w_in * WORD_SHRINK_MIN:
        status.update(verdict="rejected", reason="word-count-band")
        return False, status

    fault = span_locks.check_tokens(original, candidate)
    if fault:
        status.update(verdict="rejected", reason="lock-token", detail=fault)
        return False, status

    added = added_defects(original, candidate)
    if added:
        status.update(verdict="rejected", reason="added-defect-class",
                      detail=added)
        return False, status

    verdict = _vf.verify(original, candidate)
    fatal = _vf.checks_in(verdict, "fatal")
    if fatal:
        status.update(verdict="rejected", reason="gate",
                      detail=sorted(fatal),
                      findings=[f for f in verdict.get("findings", [])
                                if f.get("severity") == "fatal"])
        return False, status

    status["sentences"] = {"before": sentence_count(style_mod, original),
                           "after": sentence_count(style_mod, candidate)}
    status["verdict"] = "rewritten"
    return True, status


def run(article, out_path=None, control=False, model=DEFAULT_MODEL,
        endpoint=None, temperature=0.7, min_words=DEFAULT_MIN_WORDS,
        timeout=DEFAULT_TIMEOUT, dry_run=False, generate_fn=None):
    """Run the pass over every eligible paragraph. Returns the report dict."""
    pd = _prose_document()
    span_locks = _span_locks()
    style_mod = _style()
    endpoint = endpoint or _rw.DEFAULT_ENDPOINT
    system = CONTROL_SYSTEM if control else BURSTINESS_SYSTEM
    generate_fn = generate_fn or _rw.generate

    doc = pd.ProseDocument.open(article)
    before = _prose_burstiness(style_mod, doc)

    paragraphs = []
    for para in doc.paragraphs:
        row = {"index": para.index, "words": len(para.text.split())}
        if row["words"] < min_words:
            row["verdict"] = "skipped"
            row["reason"] = f"under {min_words} words"
            paragraphs.append(row)
            continue
        row["verdict"] = "eligible"
        paragraphs.append(row)

    eligible = [r for r in paragraphs if r["verdict"] == "eligible"]
    if dry_run:
        return {
            "article": article,
            "arm": "control" if control else "burstiness",
            "model": model,
            "dry_run": True,
            "paragraphs": paragraphs,
            "eligible": len(eligible),
            "burstiness": {"before": before},
        }

    ok, message = _rw.check_server(endpoint, model)
    if not ok:
        sys.exit(message)

    by_index = {r["index"]: r for r in paragraphs}
    for para in doc.paragraphs:
        row = by_index[para.index]
        if row["verdict"] != "eligible":
            continue
        try:
            raw = generate_fn(build_prompt(para.text, span_locks),
                              endpoint=endpoint, model=model,
                              temperature=temperature, timeout=timeout,
                              system=system, think=False)
        except RuntimeError as e:
            row.update(verdict="rejected", reason="generation-error",
                       detail=str(e))
            continue
        candidate = normalize(raw)
        accepted, status = judge(para.text, candidate, style_mod, span_locks)
        row.update(status)
        if accepted:
            try:
                doc.replace(para.index, candidate)
            except span_locks.LockError as e:
                row.update(verdict="rejected", reason="lock-splice",
                           detail=str(e))

    out_path = out_path or default_out(article, control)
    doc.save_as(out_path)

    written = open(out_path).read()
    lost = span_locks.verify_preserved(doc.locked_spans(), written)
    if lost:
        sys.exit(f"locked spans lost in {out_path}: {lost}. "
                 "The output is on disk and must not be used.")

    after = _prose_burstiness(style_mod, pd.ProseDocument.open(out_path))
    counts = {}
    for row in paragraphs:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    return {
        "article": article,
        "out": out_path,
        "arm": "control" if control else "burstiness",
        "model": model,
        "paragraphs": paragraphs,
        "counts": counts,
        "burstiness": {
            "before": before,
            "after": after,
            "delta": style_mod.burstiness_delta(before, after),
        },
    }


def default_out(article, control=False):
    stem, ext = os.path.splitext(article)
    return f"{stem}-{'control' if control else 'bursty'}{ext}"


def format_report(report):
    lines = [f"article: {report['article']}  arm: {report['arm']}  "
             f"model: {report['model']}"]
    if report.get("dry_run"):
        lines.append(f"dry run: {report['eligible']} of "
                     f"{len(report['paragraphs'])} paragraphs eligible")
    else:
        lines.append(f"out: {report['out']}")
        lines.append("  ".join(f"{k}={v}" for k, v in
                               sorted(report.get("counts", {}).items())))
    b = report["burstiness"]
    lines.append(f"CV before: {b['before']['cv']}")
    if b.get("after"):
        lines.append(f"CV after:  {b['after']['cv']}  "
                     f"(delta {b['delta']['cv']['delta']:+g})")
        if report["arm"] == "control" and abs(b["delta"]["cv"]["delta"]) > 0.02:
            lines.append("WARNING: the control arm moved CV by more than 0.02. "
                         "It is meant to hold rhythm, so it is no longer "
                         "isolating diction from burstiness — say so in the "
                         "report rather than reading the comparison as clean.")
    for row in report["paragraphs"]:
        if row["verdict"] in ("rejected", "skipped"):
            lines.append(f"  para {row['index']:>3}  {row['verdict']}: "
                         f"{row.get('reason', '')}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(
        description="Raise sentence-length burstiness through a second model family")
    p.add_argument("--article", required=True, help="markdown or YAML draft")
    p.add_argument("--out", default=None,
                   help="output path (default: <stem>-bursty<ext>, "
                        "or <stem>-control<ext> with --control)")
    p.add_argument("--control", action="store_true",
                   help="diction-only arm: same model, rhythm held. Run it "
                        "alongside the burstiness arm or the comparison "
                        "cannot attribute what moved.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--endpoint", default=None)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    p.add_argument("--dry-run", action="store_true",
                   help="report which paragraphs are eligible; call no model")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    if not os.path.exists(a.article):
        sys.exit(f"article not found: {a.article}")

    report = run(a.article, out_path=a.out, control=a.control, model=a.model,
                 endpoint=a.endpoint, temperature=a.temperature,
                 min_words=a.min_words, timeout=a.timeout, dry_run=a.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False) if a.json
          else format_report(report))


if __name__ == "__main__":
    main()
