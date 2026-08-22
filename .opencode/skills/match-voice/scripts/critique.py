#!/usr/bin/env python3
"""critique.py — critique-repair harness for match-voice (GH-77, sub-issue B).

The GH-189 measured run rewrote 71 paragraphs and a cold entailment review
kept 15: the driver accepted whatever cleared the mechanical gate and handed
79% of the model's output to a human to throw away. Every failure class in
those 56 reverts is detectable against the ORIGINAL paragraph — by a regex
or by a critic model — before anything is accepted. This module is that
step: pass 1 rewrites, the critique sees original and candidate and returns
a structured verdict, and a 'repair' verdict sends the candidate back once
with the critique rendered as explicit constraints.

Two sources feed one verdict. The mechanical fields are computed here with
no model: protected terms lost (term_swaps), banned words the candidate
introduced, antithesis and tricolon counts that rose against the original,
double-quoted spans that did not survive verbatim. The model supplies what
no regex can — meaning_deltas and register_drift — through the same
rewrite.generate transport the rewrite uses, so the timeout guidance and the
no-Claude-fallback rule are shared. A model answer that does not parse is
recorded, not acted on: the pass-1 candidate proceeds to the gate exactly as
it did before this module existed. Never a silent reject.

Library:
  load_banned(path)                        the filter-tells BANNED_WORDS + AI_PHRASES
  mechanical(original, candidate, protected_terms, banned)
  parse_model(text)                        -> dict or None
  merge(mech, model)                       -> verdict accept|repair|reject
  critique(original, candidate, protected_terms, banned, generate)
  render_constraints(critique)             -> text for the pass-2 prompt
  summarize_passes(results)                -> run-level counts for the report
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import protected_terms as _pt  # noqa: E402

DEAI = os.path.normpath(os.path.join(HERE, "..", "..", "filter-tells", "scripts",
                                     "detect-lexical.sh"))

VERDICTS = ("accept", "repair", "reject")

# Staged contrast: "not X, but Y" / "X, not Y" / "rather than". Counted, not
# forbidden — the original may contrast; what fails is a rise.
_ANTITHESIS = re.compile(
    r"\bnot\b[^.;:!?]{1,60}?,\s*(?:but|it is|it's|rather)\b"
    r"|,\s*not\s+\w"
    r"|\brather than\b", re.I)
# Three coordinated items: "A, B, and C" with short items.
_TRICOLON = re.compile(r"\b[\w'-]+(?:\s+[\w'-]+){0,2},\s+[\w'-]+(?:\s+[\w'-]+){0,2},\s+and\s+[\w'-]+")
_QUOTED = re.compile(r'"([^"\n]{3,}?)"')
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def load_banned(path=DEAI):
    """The banned adjective/adverb list and the AI-cliché phrases from
    filter-tells' lexical detector, read from the script itself so there is
    one list. Unreadable → [] and the caller reports the gap."""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    out = []
    for name in ("BANNED_WORDS", "AI_PHRASES"):
        m = re.search(name + r"=\((.*?)\n\)", text, re.S)
        if not m:
            continue
        body = re.sub(r"#[^\n]*", "", m.group(1))
        out.extend(re.findall(r'"([^"]+)"', body))
    return sorted(set(out), key=str.lower)


def _count(rx, text):
    return len(rx.findall(text))


def _present_words(text, words):
    found = []
    for w in words:
        if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", text, re.I):
            found.append(w)
    return found


def mechanical(original, candidate, protected_terms=None, banned=None):
    """The critique fields no model is needed for."""
    lost = _pt.lost(original, candidate, protected_terms or [])
    new_banned = sorted(set(_present_words(candidate, banned or []))
                        - set(_present_words(original, banned or [])), key=str.lower)
    o_q = _QUOTED.findall(original)
    quoted_lost = [q for q in o_q if q not in candidate]
    return {
        "term_swaps": [{"from": t, "to": None} for t in lost],
        "banned_words": new_banned,
        "new_antithesis": _count(_ANTITHESIS, candidate) > _count(_ANTITHESIS, original),
        "new_tricolon": _count(_TRICOLON, candidate) > _count(_TRICOLON, original),
        "quoted_span_changes": quoted_lost,
    }


CRITIQUE_PROMPT = """You are a cold reviewer judging whether a REWRITE of one paragraph is faithful to the ORIGINAL. You do not rewrite anything. Answer with a single JSON object and nothing else.

ORIGINAL:
{original}

REWRITE:
{candidate}

PROTECTED TERMS (terms of art the rest of the article refers back to; a synonym breaks the chain):
{terms}

Judge:
1. meaning_deltas: every claim that is weakened, strengthened, dropped, added, inverted, or re-scoped. A hypothetical made definite is a delta. A hedge removed or added is a delta. Quote the span.
2. term_swaps: every protected term or term of art replaced by a synonym, as {{"from": "...", "to": "..."}}.
3. register_drift: true if the rewrite trades the original's specific, concrete wording for generic or smoothed prose (e.g. "fluent and confident" -> "read smooth, self-assured").
4. verdict: "accept" if nothing above applies; "repair" if the problems are fixable by a second rewrite told exactly what to keep; "reject" if the rewrite inverts or loses the paragraph's point.

Output format, exactly:
{{"meaning_deltas": ["..."], "term_swaps": [{{"from": "...", "to": "..."}}], "register_drift": false, "verdict": "accept"}}"""


def build_prompt(original, candidate, protected_terms=None):
    mine = _pt.terms_in(original, protected_terms or [])
    return CRITIQUE_PROMPT.format(original=original, candidate=candidate,
                                  terms="; ".join(mine) if mine else "(none)")


def parse_model(text):
    """The model's JSON object, or None. Tolerates a ```json fence and
    leading prose before the first brace; nothing else is repaired."""
    if not text:
        return None
    s = _FENCE.sub("", text.strip())
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(s[start:i + 1])
                except json.JSONDecodeError:
                    return None
                return data if isinstance(data, dict) else None
    return None


def merge(mech, model):
    """One verdict from two sources. Model 'reject' wins; any mechanical
    finding or a model 'repair' means repair; otherwise accept. An unparsed
    model answer contributes nothing and is named in source.model."""
    out = dict(mech)
    out["meaning_deltas"] = []
    out["register_drift"] = False
    mech_hits = [k for k, v in mech.items() if v]
    model_hits = []
    if model is None:
        model_hits = ["unparsed"]
        model_verdict = None
    else:
        deltas = model.get("meaning_deltas") or []
        out["meaning_deltas"] = [str(d) for d in deltas if d]
        out["register_drift"] = bool(model.get("register_drift"))
        for sw in model.get("term_swaps") or []:
            if isinstance(sw, dict) and sw.get("from"):
                frm, to = str(sw["from"]), sw.get("to")
                existing = next((t for t in out["term_swaps"]
                                 if t["from"].lower() == frm.lower()), None)
                if existing:
                    existing["to"] = existing["to"] or (str(to) if to else None)
                else:
                    out["term_swaps"].append({"from": frm, "to": str(to) if to else None})
        model_verdict = str(model.get("verdict", "")).lower()
        if model_verdict not in VERDICTS:
            model_verdict = None
            model_hits.append("unrecognized-verdict")
        if out["meaning_deltas"]:
            model_hits.append("meaning_deltas")
        if out["register_drift"]:
            model_hits.append("register_drift")
        if model.get("term_swaps"):
            model_hits.append("term_swaps")
    model_findings = [h for h in model_hits
                      if h in ("meaning_deltas", "register_drift", "term_swaps")]
    if model_verdict == "reject":
        verdict = "reject"
    elif mech_hits or model_verdict == "repair" or model_findings:
        # A model that lists a delta but still says accept is overruled:
        # the finding is what the repair prompt needs, the verdict is not.
        verdict = "repair"
    else:
        verdict = "accept"
    out["verdict"] = verdict
    out["source"] = {"mechanical": mech_hits, "model": model_hits,
                     "model_verdict": model_verdict}
    return out


def critique(original, candidate, protected_terms=None, banned=None, generate=None):
    """The full verdict. `generate(prompt) -> text` is the model call
    (rewrite.generate bound to the critic model); None skips the model and
    the verdict is mechanical only, reported as such."""
    mech = mechanical(original, candidate, protected_terms, banned)
    raw, error = None, None
    if generate is not None:
        try:
            raw = generate(build_prompt(original, candidate, protected_terms))
        except RuntimeError as e:
            # A critic that fails to answer is recorded and treated as
            # unparsed: the candidate goes to the gate, the error goes in
            # the log. Never a silent discard, never a silent accept either.
            error = str(e)
    model = parse_model(raw) if generate is not None else {}
    out = merge(mech, model)
    if generate is None:
        out["source"]["model"] = ["skipped"]
    if error:
        out["error"] = error
    out["raw"] = raw
    return out


def render_constraints(crit):
    """The critique as explicit constraints for the pass-2 prompt. Each line
    names one thing to keep or undo; nothing here is a style directive."""
    lines = []
    for sw in crit.get("term_swaps") or []:
        if sw.get("to"):
            lines.append(f"Keep the word {sw['from']!r}; do not replace it with {sw['to']!r}.")
        else:
            lines.append(f"Keep the word {sw['from']!r} exactly as the original uses it.")
    for d in crit.get("meaning_deltas") or []:
        lines.append(f"Meaning changed: {d} Restore the original claim, including its hedging and scope.")
    if crit.get("register_drift"):
        lines.append("Keep the original's specific wording; do not smooth it into generic prose.")
    for b in crit.get("banned_words") or []:
        lines.append(f"Do not use the word {b!r}; the original did not.")
    if crit.get("new_antithesis"):
        lines.append("Do not stage a contrast the original did not have (no 'not X, but Y').")
    if crit.get("new_tricolon"):
        lines.append("Do not add a three-item list the original did not have.")
    for q in crit.get("quoted_span_changes") or []:
        lines.append(f'The phrase in quotation marks must survive verbatim: "{q}".')
    return " ".join(lines)


def summarize_passes(results):
    """Run-level counts for the report and the manifest. Records without a
    critique (--no-critique, or the pre-harness path) count as pass 1."""
    s = {"pass1_accepted": 0, "pass2_accepted": 0, "repaired": 0,
         "rejected_critique": 0, "critique_unparsed": 0, "critiqued": 0}
    for r in results:
        crit = r.get("critique")
        if crit:
            s["critiqued"] += 1
            if "unparsed" in (crit.get("source") or {}).get("model", []):
                s["critique_unparsed"] += 1
            if crit.get("verdict") == "repair":
                s["repaired"] += 1
        if r.get("status") == "rejected-critique":
            s["rejected_critique"] += 1
        if r.get("status") == "accepted-mechanical":
            if r.get("pass") == 2:
                s["pass2_accepted"] += 1
            else:
                s["pass1_accepted"] += 1
    return s


def main():
    import argparse
    ap = argparse.ArgumentParser(description="critique one rewrite against its original")
    ap.add_argument("--original", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--protected-terms", metavar="FILE")
    ap.add_argument("--model", help="critic model; omit for the mechanical fields only")
    ap.add_argument("--endpoint", default=os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434"))
    a = ap.parse_args()
    terms = _pt.read_terms(a.protected_terms) if a.protected_terms else None
    gen = None
    if a.model:
        import rewrite
        gen = lambda prompt: rewrite.generate(prompt, endpoint=a.endpoint,  # noqa: E731
                                              model=a.model, temperature=0.0)
    out = critique(open(a.original).read(), open(a.candidate).read(), terms,
                   load_banned(), gen)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
