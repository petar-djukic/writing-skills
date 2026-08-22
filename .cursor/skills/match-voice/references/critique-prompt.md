# match-voice Critique Prompt (GH-77)

The critique is the step between pass 1 and the mechanical gate. It sees the
ORIGINAL and the CANDIDATE and returns a verdict, never prose. `critique.py`
holds the template; this file documents it and the verdict schema the driver
acts on.

## Why a critique at all

The GH-189 measured run: 71 of 125 paragraphs rewritten, a cold entailment
review kept 15. Every one of the 56 reverts fell into a class detectable
against the original paragraph before acceptance — term-of-art swaps that
broke a referent chain, register degradation to generic prose, canonical
text rewritten, meaning inversions, refrain drift, banned words and staged
contrasts. The single-shot driver detected none of them; it ran the
mechanical gate and handed the rest to a human.

## Two sources, one verdict

| field | source | how |
|---|---|---|
| `term_swaps` | mechanical + model | protected terms lost (from the article's list); the model may name the replacement |
| `banned_words` | mechanical | filter-tells `BANNED_WORDS` + `AI_PHRASES`, read from `detect-lexical.sh` — words the candidate introduced and the original lacked |
| `new_antithesis` | mechanical | staged-contrast count rose against the original |
| `new_tricolon` | mechanical | three-item coordinated list count rose |
| `quoted_span_changes` | mechanical | a double-quoted span in the original that does not survive verbatim |
| `meaning_deltas` | model | claims weakened, strengthened, dropped, added, inverted, re-scoped; hedges changed; a hypothetical made definite |
| `register_drift` | model | specific wording smoothed into generic prose |
| `verdict` | merged | model `reject` wins; any mechanical finding or a model `repair` → `repair`; otherwise `accept` |

`source` records which side contributed (`{mechanical: [...], model: [...],
model_verdict}`), so a run can be read for whether the model is adding
anything the regexes did not.

## The prompt (sent through `rewrite.generate`, temperature 0)

```
You are a cold reviewer judging whether a REWRITE of one paragraph is
faithful to the ORIGINAL. You do not rewrite anything. Answer with a single
JSON object and nothing else.

ORIGINAL:
{original}

REWRITE:
{candidate}

PROTECTED TERMS (...):
{terms}

Judge:
1. meaning_deltas: ...
2. term_swaps: ...
3. register_drift: ...
4. verdict: "accept" | "repair" | "reject"

Output format, exactly:
{"meaning_deltas": [...], "term_swaps": [{"from": "...", "to": "..."}],
 "register_drift": false, "verdict": "accept"}
```

## What the driver does with it

- `accept` — the candidate goes to the mechanical gate as before.
- `repair` — one more rewrite, with `render_constraints()` appended to the
  prompt after the standing style note: *keep the word 'exposure'; do not
  replace it with 'justification'. Meaning changed: … Restore the original
  claim. The phrase in quotation marks must survive verbatim: "…".* The
  repaired candidate goes to the gate. Pass 2 is not critiqued again; the
  gate is the backstop it already was.
- `reject` — the original is kept, status `rejected-critique`, critique in
  the record.
- Unparseable model output — verdict `accept` with `source.model:
  ["unparsed"]`; the pass-1 candidate proceeds to the gate exactly as the
  pre-harness driver would have sent it. A critic that fails to answer
  never silently discards a rewrite.

`results.json` carries `pass1`, `critique`, `pass2` (or null), `pass` (which
pass the accepted candidate came from) per paragraph, and the run report
prints `critique: pass 1 accepted N, pass 2 accepted M, repaired R, rejected
X, unparsed U`. If pass 2 does not beat pass 1 the numbers say so — that is
a finding to record against the prompt, not a failure to hide.

## Flags

`--critic-model` (default: the rewrite model; a second family per the
two-model rule is the better choice when available), `--no-critique` for the
single-shot path. A critic model that is requested and unreachable is a hard
error before the first paragraph, like the rewrite model.
