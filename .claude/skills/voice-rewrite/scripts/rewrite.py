#!/usr/bin/env python3
"""Ollama client for voice-rewrite: rewrite paragraphs against voice anchors.

The rewriting model is deliberately NOT Claude. Claude judges (verify.py plus
the entailment check in the skill loop); a second model family produces the
prose, so the output decorrelates from Claude's own lexical fingerprints
instead of Claude grading its own homework.

Ollama is a soft dependency with no silent fallback: if the endpoint is
unreachable or the model is missing, this exits nonzero with remediation. The
skill must report that and stop — falling back to a Claude rewrite would
defeat the decorrelation the pipeline exists for.

Defaults to local llama3.1:8b. A cloud model is a one-flag swap
(--model glm-5.2:cloud), since Llama variants are local-pull only.

Usage:
  rewrite.py --text <file>|- --anchors <file>|-- [--model llama3.1:8b]
             [--endpoint http://localhost:11434] [--temperature 0.7]
             [--retry-note "..."] [--json]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("VOICE_REWRITE_MODEL", "llama3.1:8b")

PROMPT = """You are rewriting one paragraph so it sounds like the author of the anchor passages below. The anchors are the author's own published prose.

VOICE ANCHORS (match this register — sentence rhythm, vocabulary, directness):
{anchors}

RULES:
1. Preserve every fact, number, unit, and citation key EXACTLY as written. Citation keys look like [@key] or \\citep{{key}} — copy them verbatim, never reword or drop them.
2. Preserve the meaning completely. Do not add claims, do not remove claims.
3. Rewrite only this one paragraph. Do not merge it with others, do not split the topic, do not add a heading.
4. Match the anchors' voice, but do NOT copy phrases from them — write the same content in that register.
5. Output ONLY the rewritten paragraph. No preamble, no explanation, no quotes around it.
{retry_note}
PARAGRAPH TO REWRITE:
{paragraph}"""


def check_server(endpoint, model):
    """Return (ok, message). Never falls back — the caller must stop on False."""
    try:
        req = urllib.request.Request(f"{endpoint}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as r:
            tags = json.loads(r.read())
    except urllib.error.URLError as e:
        return False, (f"Ollama unreachable at {endpoint} ({e.reason}). "
                       "Start it with `ollama serve`, or set --endpoint / "
                       "OLLAMA_ENDPOINT. voice-rewrite does not fall back to "
                       "Claude: that would defeat its purpose.")
    except Exception as e:  # noqa: BLE001
        return False, f"Ollama check failed at {endpoint}: {e}"
    names = [m.get("name", "") for m in tags.get("models", [])]
    if model not in names:
        return False, (f"model '{model}' not available on {endpoint}. "
                       f"Pull it with `ollama pull {model}`, or pick one of: "
                       f"{', '.join(names[:8])}")
    return True, f"{endpoint} ready, model {model}"


def rewrite(paragraph, anchors, endpoint=DEFAULT_ENDPOINT, model=DEFAULT_MODEL,
            temperature=0.7, retry_note="", timeout=180):
    prompt = PROMPT.format(anchors=anchors, paragraph=paragraph,
                           retry_note=(f"\nRETRY GUIDANCE: {retry_note}\n"
                                       if retry_note else ""))
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }).encode()
    req = urllib.request.Request(f"{endpoint}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.URLError as e:
        sys.exit(f"Ollama request failed: {e.reason}. voice-rewrite stops here "
                 "(no Claude fallback by design).")
    out = (data.get("response") or "").strip()
    # models sometimes wrap the answer in quotes or a lead-in line
    if out.startswith('"') and out.endswith('"') and out.count('"') == 2:
        out = out[1:-1].strip()
    return out


def main():
    p = argparse.ArgumentParser(description="Ollama paragraph rewrite in the author's voice")
    p.add_argument("--text", required=True, help="file with the paragraph, or -")
    p.add_argument("--anchors", help="file with the rendered anchor block")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--retry-note", default="",
                   help="guidance added on a retry after a failed gate")
    p.add_argument("--check", action="store_true", help="probe server/model and exit")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    ok, msg = check_server(args.endpoint, args.model)
    if not ok:
        print(msg, file=sys.stderr)
        sys.exit(2)
    if args.check:
        print(json.dumps({"ok": True, "detail": msg}, indent=2))
        return

    paragraph = sys.stdin.read() if args.text == "-" else open(args.text).read()
    anchors = open(args.anchors).read() if args.anchors else "(no anchors provided)"
    out = rewrite(paragraph.strip(), anchors, args.endpoint, args.model,
                  args.temperature, args.retry_note)
    if args.json:
        print(json.dumps({"model": args.model, "rewrite": out}, indent=2,
                         ensure_ascii=False))
    else:
        print(out)


if __name__ == "__main__":
    main()
