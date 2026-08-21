#!/usr/bin/env python3
"""Voice-critic — cold, read-only gatekeeper against the voice constitution.

filter-tells detects "sounds like a machine"; this critic detects "doesn't
sound like Petar" and "went too far". Rubric = voice-constitution.md,
rates = idiolect.yaml, both discovered by the writing-voice/ walk-up. The
critic returns per-dimension verdicts with flagged spans and NEVER edits —
it may run after the terminal inject-vernacular stage because reading is
all it does, and it is equally usable at any earlier gate; nothing in it
assumes pipeline position.

Five dimensions:

  stance        Expert-watching, curiosity not contempt (constitution §1).
                Judged; the deterministic screen only collects evidence.
  tom-device    Model stated -> predictions derived -> tested against the
                artifact (§2). Deterministic screen for the three parts,
                refined by the judge when one is given.
  disproportion One declared overrun present and protected (§ parent
                issue): computed from the span-lock report — the lock IS
                the declaration mechanism.
  marker-profile Computed, never judged: idiolect.yaml regex rates against
                essay targets, +/-30% tolerance. Same arithmetic as
                inject-vernacular, run as a check instead of an operator.
  snark-audit   Every instance scored on the constitution's L0-L5 scale;
                hard rules checked mechanically over the instances:
                receipt-first (evidence before the joke), safe-enemy
                (never a named living person), density caps per form
                (how-to 1 / essay 2 / polemic 3 per 1000 words, counting
                L1+). Instance identification and leveling need judgment;
                the hard-rule checks over the instances are computed.

The judge is a model used in read-only mode: it answers with verdicts,
levels, and quotes; its text is never spliced anywhere. Without a judge
the judged dimensions report UNJUDGED with their screen evidence — the
author gate adjudicates flags yes/no either way; the critic replaces
self-monitoring with a checklist, not with enforcement.

Usage:
  voice_critic.py <file.md|file.yaml> [--voice-dir DIR]
      [--form how-to|essay|polemic] [--report PATH] [--json]
      [--judge] [--model MODEL] [--endpoint URL]
Exit: 0 all PASS/UNJUDGED, 1 any FAIL, 2 usage.
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

TOLERANCE = 0.30
DENSITY_CAPS = {"how-to": 1.0, "essay": 2.0, "polemic": 3.0}
SAFE_TARGETS = {"artifact", "institution", "category", "dead", "past-self"}
DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
DEFAULT_MODEL = "gemma4:12b"

# A receipt, mechanically: a number, a percentage, a citation, or quoted
# material — the evidence classes §3/§4 accept ahead of a verdict.
_RECEIPT = re.compile(r'\d|%|\[@|"[^"]{8,}"')

# ToM-device screens (§2): the move has three parts. These find candidate
# evidence for each; they are a screen, not a verdict — the judge (or the
# author gate) says whether the device is actually executed.
_TOM_PARTS = {
    "model-stated": re.compile(
        r"\b(my model|the model of|I think|maybe I'm wrong|"
        r"here's (my|the) model|what (he|she|it|they) believe)", re.I),
    "prediction": re.compile(
        r"\b(predict|I expect|should (see|show|produce)|would expect|"
        r"the model says)", re.I),
    "tested": re.compile(
        r"\b(turned out|in fact|the (log|diff|transcript|artifact) shows|"
        r"checked against|and it did|and it did not|prediction (held|missed))",
        re.I),
}

_FIRST_PERSON = re.compile(r"\bI\b|\bmy\b", re.I)


# --- discovery (same walk as inject-vernacular / voice_anchors) --------------

def discover_voice_dir(start_path):
    d = os.path.abspath(start_path)
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        cand = os.path.join(d, "writing-voice")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_markers(voice_dir):
    import yaml
    path = os.path.join(voice_dir, "idiolect.yaml")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {m["id"]: m for m in data.get("markers", [])}


def compile_marker(marker):
    spec = marker.get("regex", "")
    base, _, note = spec.partition(" (")
    flags = re.IGNORECASE if "case-insensitive" in note else 0
    try:
        return re.compile(base, flags)
    except re.error:
        return None


# --- judges ------------------------------------------------------------------

class OllamaJudge:
    """Read-only model judge. Every method returns verdicts and quotes;
    nothing it produces is ever written into a document."""

    def __init__(self, endpoint=DEFAULT_ENDPOINT, model=DEFAULT_MODEL):
        self.endpoint = endpoint
        self.model = model

    def _ask(self, prompt):
        body = json.dumps({"model": self.model, "prompt": prompt,
                           "stream": False, "format": "json"}).encode()
        req = urllib.request.Request(
            f"{self.endpoint}/api/generate", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(json.loads(r.read())["response"])
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            sys.exit(f"voice-critic: judge requested but Ollama at "
                     f"{self.endpoint} failed ({e}). Run without --judge "
                     "or fix the server; there is no silent fallback.")

    def stance(self, text):
        """-> {"verdict": "PASS|FLAG", "note": str, "quotes": [str]}"""
        return self._ask(
            "Rubric: the voice is an expert watching someone build a thing "
            "they don't know how to build — curiosity, not contempt; at the "
            "bench, not the balcony; allowed to be wrong, required to show "
            "the artifact checked against.\n\nJudge whether this text holds "
            "that stance. Return JSON {\"verdict\": \"PASS\" or \"FLAG\", "
            "\"note\": one sentence, \"quotes\": up to 3 exact quotes of "
            "passages that break the stance (empty if PASS)}.\n\nTEXT:\n"
            + text)

    def tom(self, text):
        """-> same shape as stance()."""
        return self._ask(
            "Rubric: the piece should execute a theory-of-mind device — an "
            "explicit mental model of the other mind is stated, predictions "
            "are derived from it, and the predictions are tested against "
            "what that mind actually produced. Judge whether this text "
            "executes the device. Return JSON {\"verdict\": \"PASS\" or "
            "\"FLAG\", \"note\": one sentence, \"quotes\": up to 3 exact "
            "quotes (the model statement, a prediction, a test) or the "
            "missing parts named in the note}.\n\nTEXT:\n" + text)

    def snark(self, paragraph):
        """-> [{"quote": str, "level": 0-5, "target": category}]"""
        return self._ask(
            "Identify every instance of snark, irony, mockery, or contempt "
            "in this paragraph. Level scale: 1 dry aside, 2 pointed irony "
            "with receipt, 3 open mockery of an artifact, 4 contempt for a "
            "class, 5 ridicule of a person. Target categories: artifact, "
            "institution, category, dead, past-self, person. Return a JSON "
            "list [{\"quote\": exact text, \"level\": int, \"target\": "
            "category}]; [] if none.\n\nPARAGRAPH:\n" + paragraph)


# --- the critic --------------------------------------------------------------

def _span(p, quote, note):
    return {"start_line": p.start_line, "end_line": p.end_line,
            "quote": quote, "note": note}


class Critic:
    def __init__(self, path, voice_dir=None, form="essay", judge=None):
        import prose_document
        self.path = path
        self.form = form
        self.judge = judge
        vd = voice_dir or discover_voice_dir(path)
        if not vd:
            sys.exit("voice-critic: no writing-voice/ directory found "
                     f"walking up from {path}; the constitution and "
                     "idiolect.yaml are the rubric — nothing to judge "
                     "against without them.")
        self.constitution = os.path.join(vd, "voice-constitution.md")
        if not os.path.exists(self.constitution):
            sys.exit(f"voice-critic: {vd} has no voice-constitution.md; "
                     "the critic's rubric is that file, not built-in taste.")
        self.markers = load_markers(vd)
        self.doc = prose_document.ProseDocument.open(path)
        self.paras = self.doc.paragraphs
        self.words = sum(p.word_count for p in self.paras)
        self.text = "\n\n".join(p.text for p in self.paras)

    # -- judged dimensions ---------------------------------------------------

    def dim_stance(self):
        fp = len(_FIRST_PERSON.findall(self.text))
        evidence = [{"note": f"first-person density {fp} over "
                             f"{self.words} words"}]
        if self.judge:
            j = self.judge.stance(self.text)
            spans = []
            for q in j.get("quotes", []):
                p = self._locate(q)
                spans.append(_span(p, q, "stance break (judge)") if p else
                             {"quote": q, "note": "stance break (judge)"})
            return {"verdict": j.get("verdict", "FLAG"),
                    "note": j.get("note", ""), "spans": spans,
                    "evidence": evidence}
        return {"verdict": "UNJUDGED",
                "note": "stance needs a judge or the author gate",
                "spans": [], "evidence": evidence}

    def dim_tom(self):
        found, missing, spans = {}, [], []
        for part, rx in _TOM_PARTS.items():
            hit = None
            for p in self.paras:
                m = rx.search(p.text)
                if m:
                    hit = _span(p, m.group(0), f"{part} (screen)")
                    break
            if hit:
                found[part] = hit
                spans.append(hit)
            else:
                missing.append(part)
        if self.judge:
            j = self.judge.tom(self.text)
            return {"verdict": j.get("verdict", "FLAG"),
                    "note": j.get("note", ""),
                    "spans": spans, "missing_parts": missing}
        verdict = "PASS" if not missing else "FLAG"
        note = ("all three parts present (screen only)" if not missing else
                "missing " + ", ".join(missing) + " (screen; judge or "
                "author gate decides)")
        return {"verdict": verdict, "note": note, "spans": spans,
                "missing_parts": missing}

    # -- computed dimensions -------------------------------------------------

    def dim_disproportion(self):
        rep = self.doc.lock_report()
        n = len(rep["block_ranges"]) + sum(p["tokens"] for p in rep["inline"])
        if n == 0:
            return {"verdict": "FLAG", "spans": [],
                    "note": "no locked span: the declared overrun is either "
                            "absent or unprotected — locks are the "
                            "declaration mechanism"}
        spans = [{"start_line": s, "end_line": e, "quote": "",
                  "note": "block lock"} for s, e in rep["block_ranges"]]
        spans += [{"start_line": p["start_line"], "end_line": p["end_line"],
                   "quote": "", "note": f"{p['tokens']} inline lock(s)"}
                  for p in rep["inline"]]
        return {"verdict": "PASS", "spans": spans,
                "note": f"{n} locked span(s) present and driver-protected"}

    def dim_marker_profile(self):
        if not self.markers:
            return {"verdict": "FLAG", "spans": [], "markers": {},
                    "note": "no idiolect.yaml — rates cannot be computed"}
        out, flagged = {}, []
        for mid, marker in self.markers.items():
            target = marker.get("essay_target")
            rx = compile_marker(marker)
            if target is None or rx is None or mid == "sentence-length":
                continue
            count = sum(len(rx.findall(p.text)) for p in self.paras)
            rate = count * 1000.0 / self.words if self.words else 0.0
            lo, hi = target * (1 - TOLERANCE), target * (1 + TOLERANCE)
            if target == 0:
                status = "over" if count else "ok"
            else:
                status = ("ok" if lo <= rate <= hi else
                          "under" if rate < lo else "over")
            out[mid] = {"rate": round(rate, 2), "target": target,
                        "status": status}
            if status != "ok":
                flagged.append(f"{mid} {status} ({out[mid]['rate']} vs "
                               f"{target})")
        verdict = "PASS" if not flagged else "FLAG"
        return {"verdict": verdict, "markers": out, "spans": [],
                "note": "; ".join(flagged) or "all rates within tolerance"}

    # -- snark audit ---------------------------------------------------------

    def dim_snark(self):
        cap = DENSITY_CAPS[self.form]
        if not self.judge:
            return {"verdict": "UNJUDGED", "spans": [], "instances": [],
                    "note": "instance identification needs a judge; hard "
                            "rules run over judge-identified instances"}
        instances, violations = [], []
        for i, p in enumerate(self.paras):
            for inst in self.judge.snark(p.text):
                level = int(inst.get("level", 0))
                quote = inst.get("quote", "")
                target = inst.get("target", "")
                entry = {"paragraph": i, "start_line": p.start_line,
                         "end_line": p.end_line, "quote": quote,
                         "level": level, "target": target, "violations": []}
                if level >= 5:
                    entry["violations"].append(
                        "L5 ridicule of a person: never")
                if target and target not in SAFE_TARGETS:
                    entry["violations"].append(
                        f"unsafe target '{target}' (safe-enemy rule)")
                if level >= 1 and not self._receipt_before(i, quote):
                    entry["violations"].append(
                        "receipt-first: no evidence before the joke")
                instances.append(entry)
                violations.extend(entry["violations"])
        dens = (sum(1 for x in instances if x["level"] >= 1) * 1000.0
                / self.words) if self.words else 0.0
        over_cap = dens > cap
        if over_cap:
            violations.append(
                f"density {dens:.2f}/1000 exceeds the {self.form} cap {cap}")
        verdict = "FAIL" if violations else "PASS"
        return {"verdict": verdict, "instances": instances,
                "density_per_1000": round(dens, 2), "cap": cap,
                "spans": [x for x in instances if x["violations"]],
                "note": "; ".join(violations) or
                        f"{len(instances)} instance(s), all within rules"}

    def _receipt_before(self, para_idx, quote):
        """Evidence before the joke: a receipt earlier in the same
        paragraph, or anywhere in the preceding one."""
        text = self.paras[para_idx].text
        pos = text.find(quote) if quote else -1
        head = text[:pos] if pos > 0 else ""
        if _RECEIPT.search(head):
            return True
        if para_idx > 0 and _RECEIPT.search(self.paras[para_idx - 1].text):
            return True
        return False

    def _locate(self, quote):
        for p in self.paras:
            if quote and quote in p.text:
                return p
        return None

    # -- driver --------------------------------------------------------------

    def run(self):
        report = {
            "file": self.path,
            "form": self.form,
            "constitution": self.constitution,
            "words": self.words,
            "dimensions": {
                "stance": self.dim_stance(),
                "tom-device": self.dim_tom(),
                "disproportion": self.dim_disproportion(),
                "marker-profile": self.dim_marker_profile(),
                "snark-audit": self.dim_snark(),
            },
        }
        report["verdict"] = (
            "FAIL" if any(d["verdict"] == "FAIL"
                          for d in report["dimensions"].values()) else "PASS")
        return report


def render(report):
    lines = [f"{report['file']} [{report['form']}] — {report['verdict']}"]
    for name, d in report["dimensions"].items():
        lines.append(f"  {name:<16} {d['verdict']:<9} {d.get('note', '')}")
        for s in d.get("spans", []):
            loc = (f"L{s['start_line']}-{s['end_line']}"
                   if "start_line" in s else "?")
            q = (s.get("quote") or "")[:60]
            lines.append(f"    {loc:<12} {q}  [{s.get('note', '')}]")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="read-only voice critic against voice-constitution.md")
    ap.add_argument("file")
    ap.add_argument("--voice-dir")
    ap.add_argument("--form", choices=sorted(DENSITY_CAPS), default="essay")
    ap.add_argument("--report", help="write the JSON report here as well")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--judge", action="store_true",
                    help="use an Ollama model for the judged dimensions "
                    "(read-only: verdicts and quotes, never text)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    a = ap.parse_args()

    judge = OllamaJudge(a.endpoint, a.model) if a.judge else None
    report = Critic(a.file, voice_dir=a.voice_dir, form=a.form,
                    judge=judge).run()
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2) if a.json else render(report))
    sys.exit(1 if report["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
