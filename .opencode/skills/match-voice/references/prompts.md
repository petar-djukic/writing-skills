# match-voice Prompts

Two model families, two jobs. **Ollama rewrites; Claude judges.** The rewrite
prompt below is the one `rewrite.py` sends to the local model. The entailment
prompt is Claude's — it is the half of the gate no regex can do.

## Rewrite prompt (Ollama, in `rewrite.py`)

The template lives in the script so the client is self-contained. Its shape:

- **Voice anchors first** — the author's own passages, retrieved by topic. The
  instruction is to match their register, not to copy their phrases.
- **Preservation rules, stated as hard constraints** — citation keys verbatim
  (`[@key]`, `\citep{key}`), every number and unit, inline markup where it
  stands, no added or removed claims.
- **Anti-punch constraints** — no manufactured antithesis, no em-dash the
  original lacked, no evening out of sentence lengths. A model told to match a
  punchy register reaches for the most legible signals of punch it knows, and
  those three are the ones it reaches for (GH-243).
- **Scope** — one paragraph, no merging, no splitting, no headings.
- **Output discipline** — the paragraph alone, no preamble. Small models like
  to explain themselves; the client also strips a wrapping pair of quotes.

## Retry guidance (`--retry-note`)

When the gate rejects a rewrite, retry once with a note naming the specific
failure. Keep it concrete — a generic "try again" wastes the attempt.

| Gate failure | Retry note to pass |
|---|---|
| citation lost | `You dropped the citation [@key]. Reproduce every citation key exactly as it appears in the source paragraph.` |
| number altered/invented | `The number <n> changed. Copy all numbers and units exactly; do not round, convert, or add figures.` |
| technical term dropped | `You dropped the term <TERM>. Keep domain terms and acronyms as written.` |
| citation syntax changed | `You rewrote [@key] as \\citep{key}. Reproduce citations in the SAME syntax as the source paragraph — do not convert between pandoc and natbib.` |
| markup dropped | `Reproduce the markdown formatting exactly: every **bold**, *italic*, and \`code\` span, in the same places. A paragraph that opens with a bold sentence must still open with one — that is a lead-in, not ordinary prose.` |
| em-dash added | `You added an em-dash the original did not have. Keep the original's punctuation, and do not manufacture antithesis either — no "X is not Y, it is Z" unless the original already contrasted them.` |
| similarity violation | `You reused a long phrase from an anchor. Write the same content in that register using your own wording.` |
| register still off (filter-tells) | `The result still reads as generic AI prose (<flagged terms>). Follow the anchors' plainer rhythm and concrete vocabulary.` |
| conversational filler (rate rose against the original) | `You replaced corporate vocabulary with chatty filler — just/actually/really/basically went from <b> to <a> per 500 words. State the claim without the softener.` |

After the configured number of retries, keep the original paragraph and record
the failure. A kept original is a correct outcome, not an error — an 8B model
will not land every paragraph.

## Entailment judgment (Claude, per candidate)

Run this on every candidate that clears `verify.py`. It is the meaning half of
the gate: the mechanical checks prove the tokens survived, not that the claim
did.

```
You are judging whether a rewritten paragraph preserves the meaning of the
original. Answer for BOTH directions.

ORIGINAL:
{original}

REWRITE:
{rewrite}

1. FORWARD: Does every claim in the ORIGINAL follow from the REWRITE?
   List any claim that is weakened, dropped, or changed in scope.
2. BACKWARD: Does every claim in the REWRITE follow from the ORIGINAL?
   List any claim that is new, stronger, or asserts something the original
   only implied.
3. HEDGING: Did certainty change? ("may reduce" -> "reduces" is a violation;
   so is the reverse.)
4. ATTRIBUTION: Is every cited claim still attached to the same citation?

VERDICT: EQUIVALENT | DRIFTED
For DRIFTED, quote the specific span and say which direction failed.
```

`DRIFTED` is a gate failure: retry with the drift named, or keep the original.
Do not accept a rewrite that reads better but claims differently — that is the
failure mode this whole pipeline exists to prevent.

### Two inversions that cleared the mechanical gate

Both are from one run (GH-233), and both are why this judgment cannot be handed
to `verify.py`. Each preserves every number and reads more fluently than the
original.

> **original:** Five sentences became two, and nothing the reader needed went with them.
>
> **rewrite:** Five sentences were collapsed into two, and in the process, everything the reader actually needed was gone.

The original says the compression cost the reader nothing. The rewrite says it
cost the reader everything. Same numbers, same citations, opposite claim — and
nothing lexical distinguishes them, because the inversion lives in the
relationship between "nothing" and "went with them".

> **original:** The third pass needs a real reader.
>
> **rewrite:** The third pass requires a human reader.

Here "a real reader" meant a strong model, as the following sentence made
explicit. The rewrite resolved the ambiguity the wrong way and contradicted the
next paragraph. A paragraph is judged against the original, but its *referents*
live in the paragraphs around it: when the source is ambiguous, check what the
neighbours commit it to before accepting a reading.

## Register check (filter-tells)

The last gate step runs the filter-tells lexical scan on the candidate. A rewrite that
preserves meaning but arrives full of banned words has traded one machine
register for another. Treat hard flags as a gate failure; treat candidate
categories (editorializing, reader-directive, meta-narration) as advisory and
judge them against the anchors.
