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
# Retries for transient Ollama transport failures (dropped connection, timeout).
OLLAMA_MAX_RETRIES = int(os.environ.get("OLLAMA_MAX_RETRIES", "3"))

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
COHERE_MAX_RETRIES = int(os.environ.get("COHERE_MAX_RETRIES", "3"))

# Reasoning models are allowed here. Two guards used to refuse them — a name
# substring ("reasoning") and a denylist naming command-a-plus — both written
# when a scratchpad in the answer looked like a property of the model. It is
# not. Cohere separates reasoning into its own content block, and since GH-154
# this module reads blocks by type, so a thinking model's scratchpad cannot
# reach the returned prose whatever the model is called. The name guard could
# not have worked anyway: command-a-plus-05-2026 is a reasoning model whose name
# says nothing of the sort, which is why the denylist existed to patch it.
#
# What DOES put a scratchpad in the answer is starving the thinking budget.
# Measured 2026-08-29 on command-a-plus-05-2026, one passage, temperature 0.3:
#
#   thinking setting                    thinking block   answer block
#   (none sent — the default here)        3954-6310 ch      97-154 ch  clean
#   {"type": "disabled"}                        0 ch           91 ch   clean
#   {"type": "enabled", "token_budget": 1}      2 ch         6590 ch   SPILLED
#
# The last row opened "<EOS_TOKEN>We need to rewrite the passage:" — the GH-138
# signature exactly. Reasoning with nowhere to go goes into the answer. So the
# default is to send no `thinking` field at all, and a budget, if one is ever
# configured, is clamped to a floor well above the longest run observed.
COHERE_MIN_THINKING_BUDGET = int(os.environ.get("COHERE_MIN_THINKING_BUDGET", "8000"))
# Opt-in only, and not recommended: disabling thinking on a reasoning model
# gives a deterministic 422 INVALID_TOOL_GENERATION on a long prompt (7/7 across
# two probes on the 11k-character match-voice prompt; 4/4 clean on a short one).
# Unset sends no field, which is what every measured-clean run above did.
COHERE_THINKING = os.environ.get("COHERE_THINKING", "").strip().lower()
COHERE_THINKING_BUDGET = os.environ.get("COHERE_THINKING_BUDGET", "").strip()
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


# Cohere v2 returns the assistant turn as a list of TYPED content blocks. A
# reasoning model puts its scratchpad in a block of its own —
# {"type": "thinking", "thinking": ...} — beside the answer in
# {"type": "text", "text": ...}. Probed 2026-08-29 against
# command-a-plus-05-2026: 6541 characters of thinking sat beside 195 characters
# of prose, in two separate blocks. Cohere did the separation; nothing here has
# to parse it back out of the answer.
#
# Reading the "text" key off every block happened to drop the scratchpad, since
# a thinking block carries no such key. That was luck, not policy — a block kind
# Cohere adds later would vanish the same silent way. Select on `type` instead,
# and hand the scratchpad back to the caller rather than discarding it unnamed
# (GH-154).
COHERE_TEXT_BLOCK = "text"
COHERE_THINKING_BLOCK = "thinking"


def _cohere_blocks(parts):
    """Split a v2 content-block list into (text, thinking, other_types).

    `other_types` names the block kinds this code does not read, so an unknown
    one is reportable rather than silently swallowed. Never raises on shape: a
    malformed block is counted as unknown, not allowed to kill the call."""
    text, thinking, other = [], [], []
    for p in parts:
        if not isinstance(p, dict):
            other.append(type(p).__name__)
            continue
        kind = p.get("type")
        if kind == COHERE_TEXT_BLOCK:
            text.append(p.get("text") or "")
        elif kind == COHERE_THINKING_BLOCK:
            thinking.append(p.get("thinking") or "")
        else:
            other.append(str(kind))
    return "".join(text), "".join(thinking), other


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


def _cohere_thinking():
    """The `thinking` field for the request body, or None to send no field.

    None is the default and the measured-clean setting. A configured budget is
    clamped up to COHERE_MIN_THINKING_BUDGET: a budget the model cannot finish
    inside pushes the scratchpad into the answer, which is the one failure this
    whole path exists to avoid."""
    if COHERE_THINKING_BUDGET:
        try:
            want = int(COHERE_THINKING_BUDGET)
        except ValueError:
            raise RuntimeError(
                f"COHERE_THINKING_BUDGET must be an integer, got "
                f"{COHERE_THINKING_BUDGET!r}.")
        return {"type": "enabled",
                "token_budget": max(want, COHERE_MIN_THINKING_BUDGET)}
    if COHERE_THINKING == "disabled":
        return {"type": "disabled"}
    return None


def _cohere_http_error(e):
    """Read an HTTPError body once and return (error_type, message).

    Once: HTTPError.read() drains the stream, so a second call yields nothing.
    The old code read it only on the non-retry branch, which is why a retried
    422 was never classified."""
    try:
        payload = json.loads(e.read().decode("utf-8", "replace") or "{}")
    except Exception:  # noqa: BLE001
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    return (payload.get("error_type") or ""), (payload.get("message") or "")


def _cohere_generate(prompt, model, temperature, timeout, system=None,
                     thinking_out=None):
    """One raw Cohere v2 /chat call. Raises RuntimeError; never falls back.

    Same contract as the Ollama path in generate(): no Claude fallback, clear
    remediation on failure. Reference shape mirrors the substack
    burstiness-validation cohere_chat.py driver.
    """
    name = model[len(COHERE_PREFIX):]
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
    payload = {
        "model": name,
        "messages": messages,
        "temperature": float(temperature),
    }
    thinking = _cohere_thinking()
    if thinking is not None:
        payload["thinking"] = thinking
    body = json.dumps(payload).encode()

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
            # Read the body first: the decision to retry depends on what it
            # says, and it can only be read once. 422 is retryable in general
            # (GH-142: Cohere returns it intermittently on the long match-voice
            # prompt and the identical request then succeeds), but not every
            # 422 is the same animal. 400/401 stay non-retryable.
            error_type, msg = _cohere_http_error(e)
            if e.code == 422 and error_type == "INVALID_TOOL_GENERATION":
                # Deterministic, not transient: measured 7/7 on the 11k-character
                # match-voice prompt with thinking disabled, against 0/6 for the
                # same prompt with thinking left alone. Retrying spends three
                # requests and the backoff between them to fail identically.
                raise RuntimeError(
                    f"Cohere is refusing this request: HTTP 422 "
                    f"INVALID_TOOL_GENERATION "
                    f"on '{name}'. Measured cause: thinking disabled on a "
                    f"reasoning model with a long prompt — it is deterministic, "
                    f"so this is not retried. Unset COHERE_THINKING (the default "
                    f"sends no thinking field and does not hit this), or shorten "
                    f"the prompt. No Claude fallback, by design.")
            if e.code in (422, 429, 500, 502, 503, 504) and attempt < COHERE_MAX_RETRIES - 1:
                last = f"HTTP {e.code}{'/' + error_type if error_type else ''}"
                time.sleep(2 ** attempt)
                continue
            # Surface Cohere's own reason, which is what tells a content
            # rejection apart from a format bug.
            detail = f" ({error_type}: {msg[:120]})" if error_type or msg else ""
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
    raw, thinking, other = _cohere_blocks(parts)
    if thinking_out is not None:
        thinking_out.append(thinking)
    out = _sanitize_cohere_output(raw.strip())
    if out:
        return out
    # Empty output is a failed rewrite whichever way it happened, and the
    # driver already buckets it — classify_rewrite_error() keys on the phrase
    # "empty output", so every branch below keeps it. What differs is the rest
    # of the sentence, because "reasoned at length and answered nothing" and
    # "answered only meta-commentary" call for different fixes.
    extra = f" (unread block types: {', '.join(sorted(set(other)))})" if other else ""
    if raw.strip():
        raise RuntimeError(
            f"empty output from Cohere '{name}': {len(raw.strip())} characters of "
            f"text sanitized to nothing — the model returned meta-commentary "
            f"instead of a rewrite.{extra}")
    if thinking.strip():
        raise RuntimeError(
            f"empty output from Cohere '{name}': the model produced "
            f"{len(thinking.strip())} characters of reasoning and no answer text. "
            f"A thinking budget too small to finish in pushes the scratchpad into "
            f"the answer or leaves none; send no token_budget rather than a "
            f"tight one.{extra}")
    raise RuntimeError(
        f"empty output from Cohere '{name}': the response carried no text "
        f"blocks.{extra}")

PROMPT = """You are rewriting one paragraph so it sounds like the author of the anchor passages below. The anchors are the author's own published prose.

VOICE ANCHORS (match this register — sentence rhythm, vocabulary, directness):
{anchors}

RULES:
1. Preserve every fact, number, unit, and citation key EXACTLY as written. Citation markers are the bracketed @-keys and \\citep/\\citet commands already in the paragraph — copy each one verbatim, never reword or drop one, and never write a key that is not already there. (A rewrite once replaced a real key with the example key from this very rule, which is why this rule no longer shows one — GH-159.)
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
    """Return (ok, message) for a cohere: model. Does not spend a request.

    The key is the only hard requirement. Model families are no longer refused
    by name — see the COHERE_MIN_THINKING_BUDGET comment for why the reasoning
    guard and the denylist went away. A disabled-thinking setting is reported,
    since it is the one configuration measured to fail outright on a long
    prompt, and check_server runs before a batch rather than during it."""
    name = model[len(COHERE_PREFIX):]
    if not _cohere_key():
        return False, ("no Cohere API key. Set COHERE_API_KEY, or "
                       "COHERE_SECRETS_FILE to a JSON file with a 'cohere' key.")
    if COHERE_THINKING == "disabled":
        return True, (f"Cohere ready, model {name} — WARNING: COHERE_THINKING="
                      "disabled gives a deterministic 422 "
                      "INVALID_TOOL_GENERATION on prompts the size of "
                      "match-voice's. Unset it unless the prompts are short.")
    return True, f"Cohere ready, model {name}"


def generate(prompt, endpoint=DEFAULT_ENDPOINT, model=DEFAULT_MODEL,
             temperature=0.7, timeout=DEFAULT_TIMEOUT, system=None, think=None,
             thinking_out=None):
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

    ``thinking_out``, when a list is passed, receives the model's reasoning as
    a string — Cohere's ``thinking`` content blocks, or Ollama's ``thinking``
    field. It is never spliced into the returned prose; a caller that wants to
    log or inspect the scratchpad asks for it, and one that does not never sees
    it (GH-154).
    """
    if _is_cohere(model):
        return _cohere_generate(prompt, model, temperature, timeout, system,
                                thinking_out=thinking_out)
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
    # Bounded retry with backoff for transient transport failures. Ollama's
    # cloud endpoint drops connections mid-request (RemoteDisconnected, a
    # ConnectionError subclass); before this, one dropped connection killed a
    # whole filter-tells run — 12 semantic prompts plus 3 rewrite passes — with
    # no recovery (GH-147). A cold-load timeout is retried too; it usually is
    # not fixed by retrying, so the final message still points at the timeout.
    last = None
    for attempt in range(OLLAMA_MAX_RETRIES):
        req = urllib.request.Request(f"{endpoint}/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            break
        except socket.timeout:
            last = "timeout"
            if attempt < OLLAMA_MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(
                f"Ollama timed out after {timeout}s on model '{model}' "
                f"({OLLAMA_MAX_RETRIES} attempts). A cold model load can take "
                "minutes (gemma4:12b measured ~210s cold). Raise the timeout or "
                f"warm the model first with `ollama run {model} ''`. No Claude "
                "fallback, by design.")
        except ConnectionError as e:
            last = f"connection ({e.__class__.__name__})"
            if attempt < OLLAMA_MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(
                f"Ollama connection dropped on model '{model}' "
                f"({OLLAMA_MAX_RETRIES} attempts, {e.__class__.__name__}). "
                "No Claude fallback, by design.")
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), socket.timeout):
                last = "timeout"
                if attempt < OLLAMA_MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(
                    f"Ollama timed out after {timeout}s on model '{model}'. "
                    "Raise the timeout or warm the model first.")
            raise RuntimeError(f"Ollama request failed: {e.reason}. "
                               "No Claude fallback, by design.")
    else:  # pragma: no cover - loop always breaks or raises
        raise RuntimeError(f"Ollama failed after {OLLAMA_MAX_RETRIES} attempts "
                           f"on '{model}' ({last}).")
    if thinking_out is not None:
        thinking_out.append(data.get("thinking") or "")
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
