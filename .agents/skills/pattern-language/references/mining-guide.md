# Mining Patterns from Materials

How to go from a repository's materials (code, docs, papers, experiment
results) to pattern candidates worth writing. The unit of extraction is a
**field of forces and its recurring resolution** — never a feature, a
preference, or a component.

## Forces-first extraction

Work backwards from friction, not forwards from architecture:

1. **Collect tensions.** Read the materials for places where two pressures
   pull against each other: things the design refuses to do, invariants
   defended in review comments, bugs whose fix was structural, "we tried X
   and reverted" episodes, load-time checks, validation errors. Each is a
   candidate force pair.
2. **Name the configuration that resolves them.** A pattern exists where the
   same configuration keeps resolving the same tension. State it twice: as
   the imperative recipe (`solution`) and as the constraint it enforces
   (`forces`) — the prescription is the negative space of the constraint. If
   you cannot write both sides, it is not a pattern yet.
3. **Hunt recurrence.** One system reveals forces; recurrence establishes the
   pattern. Search prior literature and shipped systems for the same
   resolution under other names (`also_known_as` is where those names go).
   Each independent occurrence becomes an `examples` entry with a full
   citation.
4. **Find the grammar.** Ask of each candidate: what must already exist for
   it to make sense (`requires`, `within`)? What does it make possible
   (`enables`)? What completes it (`contains`)? What solves a neighbouring
   force differently (`overlaps`)? A candidate that connects to nothing is
   either the root of the language or not part of it.

## Confidence rubric

| Score | Test |
|---|---|
| 2 | The same forces resolved the same way in many independent systems AND prior literature names the structure (under any name) |
| 1 | Prior art clearly supports the structure, but the specific form in this domain is newer |
| 0 | Largely from the single reference implementation; external corroboration thin. Say so — a 0 honestly held is worth more than an inflated 1 |

Score from the `examples` list, not from conviction: count independent
`kind: external` entries.

## Disqualifiers

- **A feature.** "The system has a retry queue" is a fact, not a pattern.
  Where are the forces?
- **A preference.** "We like YAML" resolves no tension.
- **A single-system structure with no recurrence** — record it at
  confidence 0 only if the forces are clearly articulated and the language
  needs it grammatically; otherwise leave it out.
- **A restatement of a sibling language's pattern.** Link it
  (`extends` prefix, `grammar.overlaps`, `examples.kind: sibling`); never
  duplicate it.
- **A pattern with no liabilities.** Every real resolution costs something.
  If you cannot name the cost, you have not understood the pattern.

## Ordering the language

Number patterns from the largest context to the smallest refinement
(Alexander's ordering). The test: read the `intent` lines in number order —
they should form a coherent argument from "the whole" down to "the details
that complete it". Write that argument out as the header's
"THE ARGUMENT, TOP TO BOTTOM" paragraph; if you cannot, the ordering (or the
set) is wrong.

## Sizing

The existing languages run 10–13 patterns. Under ~6, you likely have a
catalogue of tips, not a language; over ~15, split by scope boundary into
sibling languages linked by `extends`.
