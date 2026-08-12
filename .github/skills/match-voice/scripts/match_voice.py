#!/usr/bin/env python3
"""Unified paragraph-level entry point for the match-voice skill.

    result = match_voice_paragraph(text, voice_dir="/path/to/writing-voice")
    if result["accepted"]:
        print(result["rewritten"])

Chains retrieve -> rewrite (Ollama) -> verify (mechanical gate) with
failure-classified retries. The existing scripts (retrieve.py, rewrite.py,
verify.py) stay as-is; this module imports from them.
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _import_sibling(name):
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    return __import__(name)


def _restore_full_bold(original, candidate):
    """Re-apply **full bold** lines the model may have dropped."""
    orig_lines = original.split("\n")
    cand_lines = candidate.split("\n")
    if len(orig_lines) != len(cand_lines):
        return candidate
    out = []
    for o, c in zip(orig_lines, cand_lines):
        if o.startswith("**") and o.endswith("**") and not c.startswith("**"):
            out.append(f"**{c.strip('* ')}**")
        else:
            out.append(c)
    return "\n".join(out)


NUM_NOTE = ("Do not change numbers, citation keys, technical terms, "
            "or proper nouns — copy them verbatim.")
MARKUP_NOTE = ("Preserve markdown markup: **bold**, *italic*, `code`, "
               "and [links](url) must appear in the output exactly as "
               "in the input.")
DASH_NOTE = "Preserve em-dashes (—) and en-dashes (–); do not downgrade them."
COPY_NOTE = "Stay closer to the original wording while matching the voice."

DEAI = os.path.normpath(os.path.join(HERE, "..", "..", "filter-tells",
                                     "scripts", "detect-lexical.sh"))


def match_voice_paragraph(text, voice_dir=None, article_path=None,
                          model="gemma4:12b",
                          endpoint="http://localhost:11434",
                          temperature=0.7, retries=2,
                          role=None, anchor_tags=None, stratum=None):
    """Rewrite a single paragraph to match the repository's voice.

    Returns a dict:
        accepted   bool   whether the gate passed
        rewritten  str    the accepted rewrite, or None
        findings   list   verify findings on the last attempt
        attempts   int    how many attempts were made
        warnings   list   soft warnings (register, similarity)
        anchors    list   anchor records used
    """
    retrieve = _import_sibling("retrieve")
    rewrite_mod = _import_sibling("rewrite")
    verify_mod = _import_sibling("verify")

    rflags = []
    if voice_dir:
        rflags += ["--voice-dir", voice_dir]
    elif article_path:
        rflags += ["--for", article_path]
    if role:
        rflags += ["--role", role]
    if stratum:
        rflags += ["--stratum", stratum]
    if anchor_tags:
        rflags += ["--tags", anchor_tags]

    import tempfile
    work = tempfile.mkdtemp(prefix="match-voice-para-")
    orig_path = os.path.join(work, "orig.txt")
    with open(orig_path, "w") as f:
        f.write(text)

    aj = subprocess.run(
        [sys.executable, os.path.join(HERE, "retrieve.py"),
         "--text", orig_path, *rflags, "--json"],
        capture_output=True, text=True)
    at = subprocess.run(
        [sys.executable, os.path.join(HERE, "retrieve.py"),
         "--text", orig_path, *rflags],
        capture_output=True, text=True)

    anchors_json_path = os.path.join(work, "anchors.json")
    with open(anchors_json_path, "w") as f:
        f.write(aj.stdout or "[]")
    anchors_text = at.stdout or ""

    try:
        payload = json.loads(aj.stdout or "[]")
        recs = payload.get("anchors", payload) if isinstance(payload, dict) else payload
        anchor_info = [{"file": x.get("file"), "role": x.get("role"),
                        "score": x.get("score")} for x in recs]
    except (json.JSONDecodeError, AttributeError, TypeError):
        anchor_info = []

    note = None
    last_findings = []
    for attempt in range(1 + retries):
        candidate = rewrite_mod.rewrite(
            text, anchors_text, endpoint=endpoint, model=model,
            temperature=temperature, retry_note=note or "")
        if not candidate or not candidate.strip():
            return {"accepted": False, "rewritten": None, "findings": [],
                    "attempts": attempt + 1, "warnings": [], "anchors": anchor_info}

        candidate = _restore_full_bold(text, candidate.strip())

        cand_path = os.path.join(work, "cand.txt")
        with open(cand_path, "w") as f:
            f.write(candidate)

        vr = verify_mod.verify(text, candidate, anchors_json_path)
        de = subprocess.run(["bash", DEAI, cand_path],
                            capture_output=True, text=True)

        warnings = []
        if de.returncode != 0:
            warnings.append("register")
        if vr.get("similarity"):
            warnings.append("similarity")

        if vr.get("clean", False):
            return {"accepted": True, "rewritten": candidate,
                    "findings": vr.get("findings", []),
                    "attempts": attempt + 1, "warnings": warnings,
                    "anchors": anchor_info}

        last_findings = vr.get("findings", [])
        notes = []
        finding_types = {f.get("type", "") for f in last_findings}
        if finding_types & {"numbers", "citations", "terms"}:
            notes.append(NUM_NOTE)
        if "markup" in finding_types:
            notes.append(MARKUP_NOTE)
        if "dashes" in finding_types:
            notes.append(DASH_NOTE)
        note = " ".join(notes) or COPY_NOTE

    return {"accepted": False, "rewritten": None, "findings": last_findings,
            "attempts": 1 + retries, "warnings": [], "anchors": anchor_info}
