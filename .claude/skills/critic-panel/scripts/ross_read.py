#!/usr/bin/env python3
"""Run one leg of the ross comprehension read (GH-264).

The instrument is a protocol, not a persona: a cold reader moving strictly
forward, allowed one sentence of lookback, who must report every inference
they made even when confident of it. The persona text comes from
references/personas.md; this script welds it to the protocol, hands both a
reading copy whose figures carry the alt text a reader actually sees, and
writes a verdict-format report converge.py can parse.

Two legs:
  --copy-only          build the reading copy for the fresh-context Claude leg
  --model <name>       run one Ollama leg against localhost (OLLAMA_ENDPOINT
                       overrides) and write <stem>.critic-ross-<model>.md

Read-only by contract: the article file is never written. Standard library
only, so the runner works outside the pixi environment.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

import prepare_copy

PERSONAS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "references", "personas.md")

# The reader every leg simulates. One definition, so a roster of models is
# varying the reader's simulator, never the reader.
READER = ("The reader: a software engineer who clicked a link from a feed, "
          "has never read this publication, and has not read this article "
          "before. They read once, forward, at normal speed.")

# The protocol is the whole trick: a model grading by whether IT can resolve a
# sentence resolves everything. Forcing it to report its own inferences is
# what surfaces the places a person stops.
PROTOCOL = """The problem this run exists to solve: you are a language model, and you resolve things a person does not. You link a pronoun to something forty words back, fill a skipped step, and supply the meaning of a coined phrase from the surrounding pattern, all without noticing. A person stops, or skims on with a vague sense of having missed something. So do not grade the text by whether you can work out what it means. Apply this procedure:

1. Read strictly forward, paragraph by paragraph. Do not use anything later in the piece to understand an earlier sentence.
2. For every sentence, ask: could the person name what this refers to right now, using only the sentence itself and the one just before it? Check especially: this, that, these, those, it, both, neither, "the X" naming something not yet introduced, the opening sentence of each paragraph and section, and any sentence right after a chart.
3. Any time you had to infer, look back more than one sentence, or draw on how such essays usually go, treat that as a finding even if you are confident of the answer. Your confidence is not evidence that the reader followed.
4. Flag metaphors or coined phrases used as though already defined, jargon with no gloss for this reader, and sentences that sound like a conclusion but give the reader nothing they could repeat to a colleague. For that last kind, say what claim you can extract, or say there is none.
5. In each finding, state what the reader knows at that point and what the sentence assumes they know."""

FORMAT = """Quote every passage verbatim from the text. Do not dispute numbers. Also note, in two sentences at most, what genuinely works on a first read.

Use exactly this format, in document order:

## Diagnosis
<three sentences>
## Findings
### 1
Passage: <verbatim>
Finding: <what the reader knows vs what is assumed, in Ross's terms>
Fix: <described, never written as replacement prose>
(continue numbering)
## Defect classes
### A
Class: <the pattern>
Instance: <verbatim>
Sweep: <scope to check>
## Verdict
The reader loses the thread at <passage>. <knows vs assumes>. The fix: <fix>."""

CHART_NOTE = ("Text marked [CHART THE READER SEES: ...] stands in for an "
              "image. A person sees that chart at that point; the wording "
              "inside the brackets is not prose in the article.")


def ross_persona(path=None):
    """The Harold Ross section of the persona file, verbatim."""
    text = open(path or PERSONAS).read()
    m = re.search(r"## Harold Ross.*?(?=\n## |\Z)", text, re.S)
    if not m:
        raise SystemExit("personas.md carries no Harold Ross section")
    return m.group(0)


def reading_copy(article):
    """prepare_copy's output with each [figure] carrying its alt text.

    Critics must judge what the reader sees: a bare [figure] hides exactly
    the numbers the prose around it refers to.
    """
    text = open(article).read()
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    alts = re.findall(r"!\[(.*?)\]\(", body, re.S)
    copy = prepare_copy.prepare(text)
    placeholders = copy.count("[figure]")
    if placeholders != len(alts):
        raise SystemExit(
            f"{article}: {len(alts)} figure alt texts but {placeholders} "
            "[figure] placeholders; the copy would mislabel a chart")
    for alt in alts:
        copy = copy.replace("[figure]", "[CHART THE READER SEES: " + alt + "]", 1)
    return copy


def prompt(article, personas_path=None):
    persona = ross_persona(personas_path)
    text = reading_copy(article)
    return (
        "You are one read-only critic on a newsletter essay. You never write "
        "replacement prose.\n\n" + persona + "\n\n" + CHART_NOTE + "\n\n" +
        READER + "\n\n" + PROTOCOL + "\n\n" + FORMAT + "\n\nTHE ESSAY:\n\n" + text)


def report_path(article, model):
    stem = os.path.splitext(article)[0]
    slug = re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")
    return f"{stem}.critic-ross-{slug}.md"


def run_ollama(article, model, endpoint, num_predict, personas_path=None,
               opener=None):
    """One Ollama leg. Returns the report text; raises on a starved report.

    Thinking models spend their budget before the report: kimi-k2.6 burned a
    12,000-token num_predict entirely on thinking and returned zero content,
    which is why the default budget is 60,000 and an empty content field is a
    hard error naming the remedy rather than an empty report on disk.
    """
    body = json.dumps({
        "model": model, "stream": False,
        "messages": [{"role": "user", "content": prompt(article, personas_path)}],
        "options": {"num_ctx": 32768, "temperature": 0.2,
                    "num_predict": num_predict},
    }).encode()
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/chat", body,
        {"Content-Type": "application/json"})
    response = json.load((opener or urllib.request.urlopen)(request))
    message = response.get("message", {})
    content = message.get("content", "")
    if not content.strip():
        thinking = len(message.get("thinking") or "")
        raise SystemExit(
            f"{model} returned no report ({thinking} thinking characters, "
            f"done_reason {response.get('done_reason')}); raise --num-predict "
            "past the model's thinking budget")
    return content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("article")
    ap.add_argument("--copy-only", action="store_true",
                    help="write the injected reading copy and stop")
    ap.add_argument("--model", help="Ollama model for this leg")
    ap.add_argument("--out", help="override the output path")
    ap.add_argument("--num-predict", type=int, default=60000)
    args = ap.parse_args()
    if args.copy_only == bool(args.model):
        ap.error("exactly one of --copy-only and --model")
    if args.copy_only:
        out = args.out or os.path.splitext(args.article)[0] + ".critic-ross-copy.md"
        with open(out, "w") as f:
            f.write(reading_copy(args.article))
    else:
        endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
        report = run_ollama(args.article, args.model, endpoint, args.num_predict)
        out = args.out or report_path(args.article, args.model)
        with open(out, "w") as f:
            f.write(report)
    print(out)


if __name__ == "__main__":
    main()
