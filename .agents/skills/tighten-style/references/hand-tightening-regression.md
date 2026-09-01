# Hand-tightening regression (2026-07-26, worktrees article)

Evidence re-homed from write-article step 6g (GH-214/substack#297): why
the tightening pass must run through the rewrite transport and never by
hand. Four variants of the worktrees article — itself an AI draft:

| Variant | passive | salad | Pangram AI |
|---|---|---|---|
| **Full corpus, `--stratum pre-ai`** | **0.0** | **3.7** | **0.0%** |
| The published draft | 0.0 | 5.5 | 77.8% |
| Rewrite anchored on IEEE papers | 0.5 | 8.3 | 0.0% |
| Rewrite anchored on Yegge/Beck | 0.0 | 3.5 | 50.5% |
| Rewrite anchored on Beck only | — | 3.8 | 66.9% |
| Papers rewrite, hand-tightened by Claude | 0.0 | 7.5 | **77.9%** |
| Stratum rewrite, tightened via `tighten.py` | 0.0 | 6.5 | **0.0%** |

Hand-tightening the 0.0% draft — active voice, concrete verbs,
nominalizations removed, TS-01/02/04/09/15 — drove it back to 77.9%,
within a tenth of a point of the untouched draft. The tightening undid
the entire gain. The mechanism, in register markers per 1,000 words:

| Variant | passive | agentive | nominalization | connectives | AI% |
|---|---|---|---|---|---|
| The AI draft | 2.1 | 0.0 | 17.7 | 0.0 | 77.8% |
| Papers rewrite | **14.0** | **0.4** | **22.6** | **2.9** | 0.0% |
| Yegge/Beck rewrite | 2.7 | 0.0 | 17.0 | 0.4 | 50.5% |
| Papers + tightened | 2.2 | 0.0 | 17.5 | 0.0 | 77.9% |

The tightened row is the drafting model's row: passive 2.2 against 2.1,
nominalization 17.5 against 17.7, connectives and agentives at zero in
both. Those four markers *are* TS-02, TS-04, TS-01, and TS-15; a hand
pass deletes them by design and lands the text on the model's baseline.
Distance from the AI draft's full feature vector ranks perfectly inverse
to the score: papers 0.809 → 0.0%, Yegge/Beck 0.636 → 50.5%, tightened
0.623 → 77.9%.

The root cause is a convergence: Strunk and White's prescriptions and
RLHF-tuned assistant prose are now the same style. Instruction tuning
rewarded concise, active, concrete, unhedged writing, which is the rule
catalog this skill implements. "Improve the prose" and "make it look
machine-written" have become one operation — unless a different family
does the writing, which is what `tighten.py` enforces.

The escape is voice, not polish: the Yegge/Beck rewrite had the best
prose of the four by local metrics (salad 3.5 against the draft's 5.5)
and still sat at 50.5%, because it keeps a register of its own rather
than the generic-good one. Distinctiveness lowers the score; correctness
does not.

Two residuals `tighten.py` does not fix, seen on the same run:
`salad_rate` can *rise* as cutting words concentrates the filler left
behind (3.7 → 6.5), and list-scaffold openers ("Grouping serves two
primary purposes. First,") survive. Both are hand-edits, and hand-edits
cost score — make them deliberately, few, and re-measure.
