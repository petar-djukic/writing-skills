#!/usr/bin/env python3
"""Ollama client for match-voice: rewrite paragraphs against voice anchors.

The rewriting model is deliberately NOT Claude. Claude judges (verify.py plus
the entailment check in the skill loop); a second model family produces the
prose, so the output decorrelates from Claude's own lexical fingerprints
instead of Claude grading its own homework.

Ollama is a soft dependency with no silent fallback: if the endpoint is
unreachable or the model is missing, this exits nonzero with remediation. The
skill must report that and stop — falling back to a Claude rewrite would
defeat the decorrelation the pipeline exists for.

Defaults to local gemma4:12b, the best local model in the GH-163 bake-off that
runs on any machine. Bigger is a one-flag swap: --model gemma4:31b-mlx on a
32 GB Apple Silicon box keeps the paragraphs on the machine, --model
gemma4:31b-cloud when the memory is not there. SKILL.md has the tiers.

Usage:
  rewrite.py --text <file>|- --anchors <file>|-- [--model gemma4:12b]
             [--endpoint http://localhost:11434] [--temperature 0.7]
             [--timeout 300]
             [--retry-note "..."] [--protected-terms <file>] [--json]
"""

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import protected_terms as _pt  # noqa: E402

DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
# Defaults chosen by the GH-163 bake-off (10 models, one draft paragraph,
# same anchors, judged on voice fidelity + gate + register scan):
# gemma4:12b was the best local; gemma4:31b-cloud the best overall, with
# kimi-k2.6:cloud a complementary second opinion (it edits least).
# llama3.1:8b ranked last — it destroyed a term of art and weakened a claim
# while passing the mechanical gate — and is no longer a default.
DEFAULT_MODEL = os.environ.get("MATCH_VOICE_MODEL", "gemma4:12b")
DEFAULT_TIMEOUT = int(os.environ.get("MATCH_VOICE_TIMEOUT", "300"))

PROMPT = """You are rewriting one paragraph so it sounds like the author of the anchor passages below. The anchors are the author's own published prose.

VOICE ANCHORS (match this register — sentence rhythm, vocabulary, directness):
{anchors}

RULES:
1. Preserve every fact, number, unit, and citation key EXACTLY as written. Citation keys look like [@key] or \\citep{{key}} — copy them verbatim, never reword or drop them.
2. Preserve the meaning completely. Do not add claims, do not remove claims.
3. Preserve the markdown formatting: every **bold** span, *italic* span, and `code` span stays, in the same place. If the paragraph opens with a bold sentence, your rewrite opens with a bold sentence — it is a lead-in, not ordinary prose.
4. Rewrite only this one paragraph. Do not merge it with others, do not split the topic, do not add a heading.
5. Match the anchors' voice, but do NOT copy phrases from them — write the same content in that register.
6. Do NOT manufacture antithesis. Never turn a plain statement into "X is not Y, it is Z" or "not X, but Y" unless the original already contrasts them. Stating the thing is stronger than staging a contrast.
7. Do NOT add em-dashes, and do not convert commas or colons into them. Keep the punctuation the original used.
8. Keep the sentence lengths uneven. If the original mixes a four-word sentence with a thirty-word one, the rewrite does too — do not even them out into a uniform middle length.
9. Output ONLY the rewritten paragraph. No preamble, no explanation, no quotes around it.
{protected}{retry_note}
PARAGRAPH TO REWRITE:
{paragraph}"""

# The article's referent chain (GH-77): only the terms THIS paragraph carries
# are listed, so the rule stays short and the model cannot be told to keep a
# word that is not there.
PROTECTED_RULE = ("10. Keep these words and phrases verbatim — they are terms of art "
                  "the rest of the article refers back to, and a synonym breaks the "
                  "chain: {terms}.\n")


def build_prompt(paragraph, anchors, retry_note="", protected_terms=None):
    """The exact prompt a rewrite sends. Factored out so the protected-term
    rule and the retry note can be tested without a model."""
    mine = _pt.terms_in(paragraph, protected_terms or [])
    protected = PROTECTED_RULE.format(terms="; ".join(mine)) if mine else ""
    return PROMPT.format(anchors=anchors, paragraph=paragraph, protected=protected,
                         retry_note=(f"\nRETRY GUIDANCE: {retry_note}\n"
                                     if retry_note else ""))


def check_server(endpoint, model):
    """Return (ok, message). Never falls back — the caller must stop on False."""
    try:
        req = urllib.request.Request(f"{endpoint}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as r:
            tags = json.loads(r.read())
    except urllib.error.URLError as e:
        return False, (f"Ollama unreachable at {endpoint} ({e.reason}). "
                       "Start it with `ollama serve`, or set --endpoint / "
                       "OLLAMA_ENDPOINT. match-voice does not fall back to "
                       "Claude: that would defeat its purpose.")
    except Exception as e:  # noqa: BLE001
        return False, f"Ollama check failed at {endpoint}: {e}"
    names = [m.get("name", "") for m in tags.get("models", [])]
    if model not in names:
        return False, (f"model '{model}' not available on {endpoint}. "
                       f"Pull it with `ollama pull {model}`, or pick one of: "
                       f"{', '.join(names[:8])}")
    return True, f"{endpoint} ready, model {model}"


def generate(prompt, endpoint=DEFAULT_ENDPOINT, model=DEFAULT_MODEL,
             temperature=0.7, timeout=DEFAULT_TIMEOUT):
    """One raw generation call. Raises RuntimeError; never falls back.

    Factored out of rewrite() (GH-225) so tighten-style's driver shares the
    transport, the timeout guidance, and the no-fallback rule instead of
    growing a second Ollama client.
    """
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": float(temperature)},
    }).encode()
    req = urllib.request.Request(f"{endpoint}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except socket.timeout:
        raise RuntimeError(
            f"Ollama timed out after {timeout}s on model '{model}'. A cold "
            "model load can take minutes (gemma4:12b measured ~210s cold). "
            "Raise the timeout or warm the model first with "
            f"`ollama run {model} ''`. No Claude fallback, by design.")
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), socket.timeout):
            raise RuntimeError(
                f"Ollama timed out after {timeout}s on model '{model}'. "
                f"Raise the timeout or warm the model first.")
        raise RuntimeError(f"Ollama request failed: {e.reason}. "
                           "No Claude fallback, by design.")
    out = (data.get("response") or "").strip()
    # models sometimes wrap the answer in quotes or a lead-in line
    if out.startswith('"') and out.endswith('"') and out.count('"') == 2:
        out = out[1:-1].strip()
    return out


def rewrite(paragraph, anchors, endpoint=DEFAULT_ENDPOINT, model=DEFAULT_MODEL,
            temperature=0.7, retry_note="", timeout=DEFAULT_TIMEOUT,
            protected_terms=None):
    prompt = build_prompt(paragraph, anchors, retry_note, protected_terms)
    try:
        return generate(prompt, endpoint=endpoint, model=model,
                        temperature=temperature, timeout=timeout)
    except RuntimeError as e:
        sys.exit(str(e))




def main():
    p = argparse.ArgumentParser(description="Ollama paragraph rewrite in the author's voice")
    p.add_argument("--text", required=True, help="file with the paragraph, or -")
    p.add_argument("--anchors", help="file with the rendered anchor block")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help="seconds to wait for the model (cold loads are slow; "
                        "env MATCH_VOICE_TIMEOUT)")
    p.add_argument("--retry-note", default="",
                   help="guidance added on a retry after a failed gate")
    p.add_argument("--protected-terms", metavar="FILE",
                   help="protected-term list (protected_terms.py); the terms "
                        "this paragraph carries are sent as a keep-verbatim rule")
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
    terms = _pt.read_terms(args.protected_terms) if args.protected_terms else None
    out = rewrite(paragraph.strip(), anchors, args.endpoint, args.model,
                  args.temperature, args.retry_note, timeout=args.timeout,
                  protected_terms=terms)
    if args.json:
        print(json.dumps({"model": args.model, "rewrite": out}, indent=2,
                         ensure_ascii=False))
    else:
        print(out)


if __name__ == "__main__":
    main()
