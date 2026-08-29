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

Defaults to cohere:command-a-03-2025 (the GH-138/142 bake-off winner on
Pangram; needs COHERE_API_KEY / COHERE_SECRETS_FILE). The GH-163 local models
are the no-egress fallback via --model or MATCH_VOICE_MODEL: gemma4:12b runs
anywhere, gemma4:31b-mlx keeps 31b-tier quality on a 32 GB Apple Silicon box,
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
import re
import socket
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import protected_terms as _pt  # noqa: E402

DEFAULT_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
# Default set by the GH-138/142 Cohere bake-off: command-a-03-2025 drove a
# non-saturated draft to ~0.49 Pangram where gemma4:31b RAISED it to 1.000
# (Pangram reads the common open families as AI; Cohere's rarer fingerprint
# reads as human), and after the 422-retry fix it runs fully clean through the
# gate. The author accepted its cost/egress tradeoff and flipped the default
# (GH-145). The GH-163 local models remain the no-egress fallback via --model
# or MATCH_VOICE_MODEL: gemma4:12b (best local), gemma4:31b-cloud (best Ollama
# overall), kimi-k2.6:cloud (edits least). A keyless environment MUST pass one
# of those, since a cohere: default with no key stops rather than falling back.
DEFAULT_MODEL = os.environ.get("MATCH_VOICE_MODEL", "cohere:command-a-03-2025")
DEFAULT_TIMEOUT = int(os.environ.get("MATCH_VOICE_TIMEOUT", "300"))

# Cohere is an opt-in cross-family backend, selected by a `cohere:` model-id
# prefix (e.g. --model cohere:command-a-03-2025). It routes to Cohere's hosted
# v2 /chat API instead of Ollama; every generative stage that calls generate()
# gets it for free. Defaults are unchanged — nothing routes here unless the
# model id asks for it. Rationale: the substack GH-269 confound test measured a
# cross-family fixer (Cohere) taking a filter-tells fix to 0.335/0.665 human
# where the session model produced 1.000, so a distinct non-Claude family is
# worth having in the toolbox. Adoption as a default is gated on the bake-off
# (writing-skills GH-138).
COHERE_PREFIX = "cohere:"
COHERE_ENDPOINT = os.environ.get("COHERE_ENDPOINT", "https://api.cohere.com/v2/chat")
# Denylisted Cohere families: they leak chain-of-thought and echo the prompt's
# own rules into the output on the long match-voice prompt (GH-138 bake-off:
# command-a-plus-05-2026 ballooned 1386 -> 2086 words of meta-commentary, and
# its low Pangram was a garbage-text artifact). The name-based reasoning guard
# does not catch them ("plus", not "reasoning"), so they are named here.
# command-a-03-2025 is NOT listed — it produced clean output.
COHERE_DENYLIST = ("command-a-plus",)
COHERE_MAX_RETRIES = int(os.environ.get("COHERE_MAX_RETRIES", "3"))
# Lines a leak-prone model emits instead of, or around, the rewrite: prompt-rule
# echoes and reasoning narration. Stripped as defense in depth even for allowed
# models; if stripping leaves nothing, the caller treats it as a failed rewrite.
# Deliberately NARROW: it must not touch legitimate prose that merely opens with
# a transition word ("Now the engine reads…", "So the validator runs…"). It
# matches only genuine meta — instruction echoes and first-person deliberation.
_COHERE_META = re.compile(
    r"^\s*(?:"
    r"(?:is|here is|this is|below is) the rewritten paragraph\b"
    r"|(?:rewritten paragraph|output|note|explanation)\s*:"
    r"|no preamble\b"
    r"|(?:now,?\s+|so,?\s+)?we (?:need to|should|must|will|have to)\b"
    r"|let me\b|let's\b"
    r"|i (?:will|need to|should|have) \w"
    r").*$",
    re.IGNORECASE)


def _sanitize_cohere_output(text):
    """Strip instruction-echo / reasoning-narration lines a leak-prone model
    mixes into the response (GH-138/GH-140). Defense in depth beside the
    denylist: keeps a stray meta line from a clean model out of the splice."""
    kept = [ln for ln in text.splitlines() if not _COHERE_META.match(ln)]
    return "\n".join(kept).strip()


def _cohere_key():
    """Cohere API key from COHERE_API_KEY, else the JSON file named by
    COHERE_SECRETS_FILE (key 'cohere'). Returns None if neither yields one.
    Never hardcoded; the key value never lives in this repo."""
    key = os.environ.get("COHERE_API_KEY")
    if key:
        return key.strip()
    path = os.environ.get("COHERE_SECRETS_FILE")
    if path and os.path.exists(path):
        try:
            with open(path) as fh:
                return (json.load(fh).get("cohere") or "").strip() or None
        except Exception:  # noqa: BLE001
            return None
    return None


def _is_cohere(model):
    return isinstance(model, str) and model.startswith(COHERE_PREFIX)


def _cohere_reasoning(model):
    """A reasoning/thinking Cohere variant, whose chain-of-thought would land in
    the captured response (the GH-129 lesson) — routed here only to be refused."""
    return "reasoning" in model[len(COHERE_PREFIX):].lower()


def _cohere_generate(prompt, model, temperature, timeout, system=None):
    """One raw Cohere v2 /chat call. Raises RuntimeError; never falls back.

    Same contract as the Ollama path in generate(): no Claude fallback, clear
    remediation on failure. Reference shape mirrors the substack
    burstiness-validation cohere_chat.py driver.
    """
    name = model[len(COHERE_PREFIX):]
    if _cohere_reasoning(model):
        raise RuntimeError(
            f"refusing Cohere reasoning model '{name}': thinking-model "
            "chain-of-thought contaminates the captured text (GH-129). Use a "
            "non-reasoning variant such as command-a-03-2025.")
    if any(bad in name for bad in COHERE_DENYLIST):
        raise RuntimeError(
            f"refusing denylisted Cohere model '{name}': it leaks reasoning and "
            "echoes the prompt's rules into the output on the match-voice prompt "
            "(GH-138), which the name-based reasoning guard does not catch. Use "
            "command-a-03-2025.")
    key = _cohere_key()
    if not key:
        raise RuntimeError(
            "no Cohere API key. Set COHERE_API_KEY, or COHERE_SECRETS_FILE to a "
            "JSON file with a 'cohere' key. match-voice does not fall back to "
            "Claude: that would defeat its purpose.")
    messages = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": name,
        "messages": messages,
        "temperature": float(temperature),
    }).encode()

    # Bounded retry with backoff for transient failures (429, 5xx, timeout).
    # A rewrite-error dropped a paragraph to its original on the first hiccup in
    # the GH-138 run; retrying recovers those. Non-transient errors (400/401)
    # raise immediately. No Claude fallback, by design.
    last = None
    for attempt in range(COHERE_MAX_RETRIES):
        req = urllib.request.Request(
            COHERE_ENDPOINT, data=body,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            # 422 is included empirically (GH-142): Cohere returns it
            # intermittently on the long match-voice prompt, and retrying the
            # identical request succeeds — so here it behaves as transient, not
            # as a permanent "unprocessable" verdict. 400/401 stay non-retryable.
            if e.code in (422, 429, 500, 502, 503, 504) and attempt < COHERE_MAX_RETRIES - 1:
                last = f"HTTP {e.code}"
                time.sleep(2 ** attempt)
                continue
            # Surface the response body: a 422 (Unprocessable Entity) carries
            # Cohere's reason (content filter, payload issue), which is what
            # tells a non-retryable content rejection apart from a format bug.
            detail = ""
            try:
                body_txt = e.read().decode("utf-8", "replace")
                msg = (json.loads(body_txt).get("message") if body_txt else "") or ""
                detail = f" ({msg[:120]})" if msg else ""
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"Cohere request failed: HTTP {e.code} on "
                               f"'{name}'{detail}. No Claude fallback, by design.")
        except socket.timeout:
            last = "timeout"
            if attempt < COHERE_MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(
                f"Cohere timed out after {timeout}s on model '{name}' "
                f"({COHERE_MAX_RETRIES} attempts). Raise the timeout or retry.")
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), socket.timeout) \
                    and attempt < COHERE_MAX_RETRIES - 1:
                last = "timeout"
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Cohere request failed: {e.reason}. "
                               "No Claude fallback, by design.")
    else:  # pragma: no cover - loop always breaks or raises
        raise RuntimeError(f"Cohere failed after {COHERE_MAX_RETRIES} attempts "
                           f"on '{name}' ({last}).")

    parts = (data.get("message") or {}).get("content") or []
    return _sanitize_cohere_output("".join(p.get("text", "") for p in parts).strip())

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
    if _is_cohere(model):
        return _check_cohere(model)
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


def _check_cohere(model):
    """Return (ok, message) for a cohere: model — key present and not a
    reasoning variant. Does not spend a request. Never falls back."""
    name = model[len(COHERE_PREFIX):]
    if _cohere_reasoning(model):
        return False, (f"refusing Cohere reasoning model '{name}': its "
                       "chain-of-thought contaminates captured text (GH-129). "
                       "Use command-a-03-2025.")
    if any(bad in name for bad in COHERE_DENYLIST):
        return False, (f"refusing denylisted Cohere model '{name}': it leaks "
                       "reasoning / prompt-rule echoes into the output on the "
                       "match-voice prompt (GH-138). Use command-a-03-2025.")
    if not _cohere_key():
        return False, ("no Cohere API key. Set COHERE_API_KEY, or "
                       "COHERE_SECRETS_FILE to a JSON file with a 'cohere' key.")
    return True, f"Cohere ready, model {model[len(COHERE_PREFIX):]}"


def generate(prompt, endpoint=DEFAULT_ENDPOINT, model=DEFAULT_MODEL,
             temperature=0.7, timeout=DEFAULT_TIMEOUT, system=None, think=None):
    """One raw generation call. Raises RuntimeError; never falls back.

    Factored out of rewrite() (GH-225) so tighten-style's driver shares the
    transport, the timeout guidance, and the no-fallback rule instead of
    growing a second Ollama client.

    ``system`` sends a system prompt alongside the user prompt. ``think``
    toggles Ollama's reasoning field: pass False for a thinking model whose
    chain-of-thought would otherwise land in the response. Both are omitted
    from the body when None, so a server that predates either field sees the
    request it saw before.

    Why the HTTP API and not `ollama run` (GH-129): gemma4:31b-cloud is a
    thinking model, and driving it through a captured pipe returned
    chain-of-thought plus terminal control codes and mid-word backspace
    artifacts. The corrupted text measured 0.428 on Pangram against 0.259 for
    the clean rerun, so the transport silently changed the finding.

    A ``cohere:`` model id routes to Cohere's hosted v2 /chat API instead
    (opt-in; the Ollama path stays the default). The signature is unchanged, so
    every stage that calls generate() can select Cohere without its own client.
    """
    if _is_cohere(model):
        return _cohere_generate(prompt, model, temperature, timeout, system)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": float(temperature)},
    }
    if system is not None:
        payload["system"] = system
    if think is not None:
        payload["think"] = bool(think)
    body = json.dumps(payload).encode()
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
