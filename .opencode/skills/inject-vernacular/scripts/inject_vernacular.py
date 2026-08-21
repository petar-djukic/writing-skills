#!/usr/bin/env python3
"""Terminal vernacular stage — deterministic idiolect operators (GH-57/GH-59).

Reads the operator bank in writing-voice/idiolect.yaml and applies its
substitution/restoration operators to a draft, at the per-1000-word essay
targets, within the bank's +/-30% tolerance. Nothing here samples from a
model: every edit is a rule from the bank applied to text already present
in the document. That is why this stage may run LAST — after it, models
read but never write (the humanize pipeline invariant).

Substrate policy (idiolect.yaml, amended 2026-08-21): markers are written
directly into the text at target rates — no proposal tags, no diff
ceremony. The author's gate read is the filter; the machine-readable edit
log exists for the git-history survival analysis, not for review.

Span locks are enforced by the shared drivers: block-locked regions never
reach this script, and inline locks travel as [[LOCK-n]] anchor tokens no
operator pattern can match.

An optional verifier model MAY judge each edit (KEEP/DROP) but never
writes text — a dropped edit reverts, the mechanical output is otherwise
untouched. Requested-but-unreachable is an error, not a silent skip.

Operators implemented, keyed by marker id: colon-verdict (RESTORE/REDUCE),
em-dash (RESTORE/REDUCE), antithesis-not (RESTORE/REDUCE), kind-of
(delete excess, never inject), okay / you-know / right-tag (STRIP outside
quoted speech), so-initial (CAP), ai-connectives (SUBSTITUTE), maybe
(perhaps->maybe, cap), i-think (REDUCE receipts-first), sentence-length
(SPLIT over 30 words; MERGE is manual and never performed). probably and
be-able-to are RETAIN markers: structurally no-ops here, listed so the
report shows them as intentionally untouched. he-agent and
article-density need referent or part-of-speech judgment the bank itself
calls not machine-checkable; they are gate-read territory and this script
never attempts them.

Usage:
  inject_vernacular.py <file.md|file.yaml> [--voice-dir DIR]
      [--edit-log PATH] [--dry-run] [--json]
      [--verify] [--model MODEL] [--endpoint URL]
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

SK = os.path.dirname(os.path.realpath(__file__))
SHARED = os.path.normpath(os.path.join(SK, "..", "..", "..", "scripts"))
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

from idiolect import TOLERANCE, compile_marker, discover_voice_dir  # noqa: E402
import idiolect  # noqa: E402

SPLIT_WORDS = 30  # sentence-length operator: split threshold from the bank
DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
DEFAULT_MODEL = "gemma4:12b"


# --- idiolect bank -----------------------------------------------------------
# Bank access is shared (scripts/idiolect.py); the refusal policy is this
# stage's own — no bank, no defaults, no run.

def load_bank(voice_dir):
    markers = idiolect.load_markers(voice_dir)
    if markers is None:
        sys.exit(f"inject-vernacular: no idiolect.yaml in {voice_dir} — "
                 "this stage has no defaults; the operator bank is the "
                 "configuration. Run the Phase-1 extraction first.")
    if not markers:
        sys.exit(f"inject-vernacular: {os.path.join(voice_dir, 'idiolect.yaml')} "
                 "carries no markers list.")
    return markers


# --- measurement -------------------------------------------------------------

def word_count(texts):
    return sum(len(t.split()) for t in texts)


def marker_count(texts, rx):
    return sum(len(rx.findall(t)) for t in texts)


def rate(count, words):
    return count * 1000.0 / words if words else 0.0


def _quote_spans(text):
    return [m.span() for m in re.finditer(r'"[^"]*"', text)]


def _outside_quotes(text, start):
    return not any(a < start < b for a, b in _quote_spans(text))


def _recap_sentence_start(text, pos):
    """Capitalize the word at pos when it now begins a sentence."""
    head = text[:pos]
    if pos < len(text) and (pos == 0 or re.search(r"[.!?]\s+$", head)):
        return text[:pos] + text[pos].upper() + text[pos + 1:]
    return text


# --- the edit engine ---------------------------------------------------------

class Editor:
    """Applies operator edits to the paragraph texts, one instance at a
    time, recording full before/after per edit so the log replays the
    whole diff. The optional judge sees each edit and may DROP it; a
    dropped edit reverts and the engine moves to the next candidate."""

    def __init__(self, texts, judge=None):
        self.texts = texts
        self.judge = judge
        self.edits = []

    def apply(self, operator, idx, new_text, note=""):
        before = self.texts[idx]
        if new_text == before:
            return False
        kept = True
        if self.judge is not None:
            kept = self.judge(operator, before, new_text)
        entry = {"operator": operator, "paragraph": idx,
                 "before": before, "after": new_text, "kept": kept}
        if note:
            entry["note"] = note
        self.edits.append(entry)
        if kept:
            self.texts[idx] = new_text
        return kept

    def sub_counted(self, operator, pattern, repl, budget, reverse=False,
                    quotes_guard=False, delta_per_edit=1, note=""):
        """Apply pattern->repl one instance at a time until `budget` count
        units are added/removed or candidates run out. Candidates are taken
        in document order (or reverse); within a paragraph, applying from
        the last span backward keeps earlier offsets valid."""
        applied = 0
        rx = pattern if hasattr(pattern, "finditer") else re.compile(pattern)
        order = range(len(self.texts))
        if reverse:
            order = reversed(order)
        for idx in order:
            if applied >= budget:
                break
            # Back-to-front within a paragraph so earlier spans stay valid.
            matches = list(rx.finditer(self.texts[idx]))
            for m in reversed(matches):
                if applied >= budget:
                    break
                if quotes_guard and not _outside_quotes(self.texts[idx], m.start()):
                    continue
                text = self.texts[idx]
                expanded = m.expand(repl)
                new = text[:m.start()] + expanded + text[m.end():]
                new = _recap_sentence_start(new, m.start() + len(expanded))
                if self.apply(operator, idx, new, note):
                    applied += delta_per_edit
        return applied


# --- operators ---------------------------------------------------------------

def _budget(count, words, target, direction):
    """Edit budget in count units. direction: +1 restore toward target,
    -1 reduce toward target. Zero when inside tolerance."""
    target_count = target * words / 1000.0
    if direction > 0:
        if count >= target_count * (1 - TOLERANCE):
            return 0
        return max(0, int(round(target_count - count)))
    if count <= target_count * (1 + TOLERANCE):
        return 0
    return max(0, int(round(count - target_count)))


_COLON_JOIN = re.compile(
    r'([a-z0-9"\')\]])\.\s+(?:That is,|This means,?|In other words,)\s+')
_COLON_VERDICT_SPLIT = re.compile(r'(\w): +([a-z"\'])')


def op_colon_verdict(ed, marker, rx, words):
    count = marker_count(ed.texts, rx)
    target = marker["essay_target"]
    b = _budget(count, words, target, +1)
    if b:
        ed.sub_counted("colon-verdict", _COLON_JOIN, r"\1: ", b)
        return
    b = _budget(count, words, target, -1)
    if b:
        # No provenance for "latest-added": reduce from the document's end,
        # the deterministic stand-in. sub_counted expands a template and
        # this replacement upcases a group, so it runs directly.
        def split(m):
            return m.group(1) + ". " + m.group(2).upper()
        applied = 0
        for idx in reversed(range(len(ed.texts))):
            if applied >= b:
                break
            for m in reversed(list(_COLON_VERDICT_SPLIT.finditer(ed.texts[idx]))):
                if applied >= b:
                    break
                text = ed.texts[idx]
                new = text[:m.start()] + split(m) + text[m.end():]
                if ed.apply("colon-verdict", idx, new):
                    applied += 1


_PAREN_ASIDE = re.compile(r" \(([^()\n]{4,80})\)")
_DASH_ASIDE = re.compile(r"—([^—\n]{4,80})—")


def op_em_dash(ed, marker, rx, words):
    count = marker_count(ed.texts, rx)
    target = marker["essay_target"]
    b = _budget(count, words, target, +1)
    if b:
        # Each parenthetical-to-dash conversion adds two dashes.
        ed.sub_counted("em-dash", _PAREN_ASIDE, "—\\1—", b,
                       delta_per_edit=2)
        return
    b = _budget(count, words, target, -1)
    if b:
        ed.sub_counted("em-dash", _DASH_ASIDE, r" (\1)", b,
                       reverse=True, delta_per_edit=2)


def op_antithesis(ed, marker, rx, words):
    count = marker_count(ed.texts, rx)
    target = marker["essay_target"]
    b = _budget(count, words, target, +1)
    if b:
        ed.sub_counted("antithesis-not", r" rather than ", ", not ", b)
        remaining = b - sum(1 for e in ed.edits
                            if e["operator"] == "antithesis-not" and e["kept"])
        if remaining > 0:
            ed.sub_counted("antithesis-not", r" instead of ", ", not ", remaining)
        return
    b = _budget(count, words, target, -1)
    if b:
        ed.sub_counted("antithesis-not", r", not ", " rather than ", b,
                       reverse=True)


def op_kind_of(ed, marker, rx, words):
    count = marker_count(ed.texts, rx)
    b = _budget(count, words, marker["essay_target"], -1)
    if b:
        ed.sub_counted("kind-of", re.compile(r"\bkind of\s+", re.I), "", b,
                       reverse=True, quotes_guard=True,
                       note="excess over trace target deleted; never injected")


def op_strip(op_id, pattern):
    rx = re.compile(pattern, re.IGNORECASE)

    def op(ed, marker, _rx, words):
        # Target 0: every occurrence outside quoted speech goes.
        ed.sub_counted(op_id, rx, "", 10 ** 6, quotes_guard=True)
    return op


_RIGHT_TAG = re.compile(r",?\s*right\?")


def op_right_tag(ed, marker, rx, words):
    for idx in range(len(ed.texts)):
        for m in reversed(list(_RIGHT_TAG.finditer(ed.texts[idx]))):
            if not _outside_quotes(ed.texts[idx], m.start()):
                continue
            text = ed.texts[idx]
            new = text[:m.start()] + "." + text[m.end():]
            ed.apply("right-tag", idx, new)


_SO_INITIAL = re.compile(r"(^|[.!?]\s+)So,?\s+")


def op_so_initial(ed, marker, rx, words):
    count = marker_count(ed.texts, rx)
    b = _budget(count, words, marker["essay_target"], -1)
    if b:
        ed.sub_counted("so-initial", _SO_INITIAL, r"\1", b, reverse=True)


_HOWEVER = re.compile(r"(^|[.!?]\s+)However,\s+")
_AND_CONNECTIVES = re.compile(r"(^|[.!?]\s+)(?:Moreover|Furthermore|Additionally),\s+")


def op_ai_connectives(ed, marker, rx, words):
    ed.sub_counted("ai-connectives", _HOWEVER, r"\1But ", 10 ** 6)
    ed.sub_counted("ai-connectives", _AND_CONNECTIVES, r"\1And ", 10 ** 6)


_I_THINK = re.compile(r"\bI think(?: that)?[, ]\s*")
_RECEIPT = re.compile(r"\d|\[@")


def op_i_think(ed, marker, rx, words):
    # RESTORE needs the voice-critic's unhedged-prediction flags — a
    # judgment call, out of scope for a mechanical stage. REDUCE is
    # mechanical: hedges on receipted claims (a number or citation in the
    # same paragraph) go first, per the bank.
    count = marker_count(ed.texts, rx)
    b = _budget(count, words, marker["essay_target"], -1)
    if not b:
        return
    receipted = [i for i, t in enumerate(ed.texts) if _RECEIPT.search(t)]
    plain = [i for i in range(len(ed.texts)) if i not in set(receipted)]
    applied = 0
    for idx in receipted + plain:
        if applied >= b:
            break
        for m in reversed(list(_I_THINK.finditer(ed.texts[idx]))):
            if applied >= b:
                break
            text = ed.texts[idx]
            new = text[:m.start()] + text[m.end():]
            new = _recap_sentence_start(new, m.start())
            if ed.apply("i-think", idx, new, note="reduce, receipts-first"):
                applied += 1


def op_maybe(ed, marker, rx, words):
    ed.sub_counted("maybe", re.compile(r"\bPerhaps\b"), "Maybe", 10 ** 6)
    ed.sub_counted("maybe", re.compile(r"\bperhaps\b"), "maybe", 10 ** 6)
    count = marker_count(ed.texts, rx)
    b = _budget(count, words, marker["essay_target"], -1)
    if b:
        ed.sub_counted("maybe", re.compile(r"\bmaybe\s+", re.I), "", b,
                       reverse=True, quotes_guard=True)


_SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def op_sentence_split(ed, marker, rx, words):
    for idx in range(len(ed.texts)):
        changed = True
        while changed:
            changed = False
            for m in _SENTENCE.finditer(ed.texts[idx]):
                sent = m.group(0)
                if len(sent.split()) <= SPLIT_WORDS:
                    continue
                new_sent = _split_sentence(sent)
                if new_sent == sent:
                    continue
                text = ed.texts[idx]
                new = text[:m.start()] + new_sent + text[m.end():]
                if ed.apply("sentence-length", idx, new, note="split > 30 words"):
                    changed = True
                    break
            # one split per pass; re-scan so offsets stay honest


def _split_sentence(sent):
    semi = sent.find("; ")
    if semi != -1:
        head, tail = sent[:semi], sent[semi + 2:]
        return head + ". " + (tail[:1].upper() + tail[1:])
    mid = len(sent) // 2
    best, best_dist = None, None
    for cm in re.finditer(r", (and|but) ", sent):
        d = abs(cm.start() - mid)
        if best is None or d < best_dist:
            best, best_dist = cm, d
    if best is None:
        return sent
    conj = best.group(1).capitalize()
    return sent[:best.start()] + ". " + conj + " " + sent[best.end():]


# Dispatch table: marker id -> operator. RETAIN markers (probably,
# be-able-to) and not-machine-checkable ones (he-agent, article-density)
# are deliberately absent — the report lists them as untouched.
OPERATORS = {
    "colon-verdict": op_colon_verdict,
    "em-dash": op_em_dash,
    "antithesis-not": op_antithesis,
    "kind-of": op_kind_of,
    "okay": op_strip("okay", r"\bokay,?\s*"),
    "you-know": op_strip("you-know", r"\byou know,?\s*"),
    "right-tag": op_right_tag,
    "so-initial": op_so_initial,
    "ai-connectives": op_ai_connectives,
    "i-think": op_i_think,
    "maybe": op_maybe,
    "sentence-length": op_sentence_split,
}

RETAIN = {"probably", "be-able-to"}
NOT_MACHINE_CHECKABLE = {"he-agent", "article-density"}


# --- verifier ----------------------------------------------------------------

def ollama_judge(endpoint, model):
    """A judge that asks a local model KEEP or DROP per edit. The model
    only ever answers; its text is never spliced anywhere."""
    def judge(operator, before, after):
        prompt = (
            "An automated editor applied the deterministic operator "
            f"'{operator}' to a paragraph.\n\nBEFORE:\n{before}\n\n"
            f"AFTER:\n{after}\n\n"
            "Answer KEEP if the edit preserves meaning and reads as "
            "grammatical English. Answer DROP otherwise. One word only.")
        body = json.dumps({"model": model, "prompt": prompt,
                           "stream": False}).encode()
        req = urllib.request.Request(
            f"{endpoint}/api/generate", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
        except (urllib.error.URLError, OSError) as e:
            sys.exit(f"inject-vernacular: verifier requested but Ollama at "
                     f"{endpoint} is unreachable ({e}). No silent skip: run "
                     "without --verify or start the server.")
        return "KEEP" in resp.get("response", "").strip().upper()[:8]
    return judge


# --- driver ------------------------------------------------------------------

def run(path, voice_dir=None, judge=None):
    """Apply the bank to `path`'s paragraphs. Returns (doc, editor, report).
    Caller decides whether to save."""
    import prose_document
    voice_dir = voice_dir or discover_voice_dir(path)
    if not voice_dir:
        sys.exit("inject-vernacular: no writing-voice/ directory found "
                 f"walking up from {path}. This stage refuses to run "
                 "without the operator bank (idiolect.yaml).")
    markers = load_bank(voice_dir)
    doc = prose_document.ProseDocument.open(path)
    texts = [p.text for p in doc.paragraphs]
    ed = Editor(texts, judge=judge)
    words = word_count(texts)

    report = {"file": path, "words": words, "markers": {}}
    for mid, marker in markers.items():
        rx = compile_marker(marker)
        before_rate = rate(marker_count(texts, rx), words) if rx else None
        if mid in OPERATORS:
            OPERATORS[mid](ed, marker, rx, words)
            status = "applied"
        elif mid in RETAIN:
            status = "retained (never injected, never deleted)"
        elif mid in NOT_MACHINE_CHECKABLE:
            status = "gate-read territory (bank: not machine-checkable)"
        else:
            status = "no operator implemented"
        after_rate = rate(marker_count(ed.texts, rx), words) if rx else None
        report["markers"][mid] = {
            "target": marker.get("essay_target"),
            "rate_before": round(before_rate, 2) if before_rate is not None else None,
            "rate_after": round(after_rate, 2) if after_rate is not None else None,
            "status": status,
        }

    kept = [e for e in ed.edits if e["kept"]]
    for i, p in enumerate(doc.paragraphs):
        if ed.texts[i] != p.text:
            doc.replace(i, ed.texts[i])
    report["edits_total"] = len(ed.edits)
    report["edits_kept"] = len(kept)
    report["edits_dropped"] = len(ed.edits) - len(kept)
    return doc, ed, report


def main():
    ap = argparse.ArgumentParser(
        description="terminal vernacular stage: idiolect operators from "
                    "writing-voice/idiolect.yaml, substitution only")
    ap.add_argument("file")
    ap.add_argument("--voice-dir", help="writing-voice/ directory (default: walk up)")
    ap.add_argument("--edit-log", help="edit-log JSON path "
                    "(default: <file>.vernacular.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report and log, write nothing back")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="judge each edit with an Ollama model (KEEP/DROP); "
                    "the model never writes")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    a = ap.parse_args()

    judge = ollama_judge(a.endpoint, a.model) if a.verify else None
    doc, ed, report = run(a.file, voice_dir=a.voice_dir, judge=judge)

    log_path = a.edit_log or a.file + ".vernacular.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(ed.edits, f, indent=2)
    report["edit_log"] = log_path

    if not a.dry_run:
        doc.save()

    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{a.file}: {report['edits_kept']} edit(s) applied"
              f" ({report['edits_dropped']} dropped by verifier)"
              f"{' [dry-run]' if a.dry_run else ''}")
        for mid, m in report["markers"].items():
            tgt = "-" if m["target"] is None else m["target"]
            rb = "-" if m["rate_before"] is None else m["rate_before"]
            ra = "-" if m["rate_after"] is None else m["rate_after"]
            print(f"  {mid:<18} target {tgt!s:>5}  {rb!s:>6} -> {ra!s:>6}  {m['status']}")


if __name__ == "__main__":
    main()
