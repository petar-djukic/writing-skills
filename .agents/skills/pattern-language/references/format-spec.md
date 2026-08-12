# pattern-language.yaml — Format Specification

Distilled from the three existing instances: `declarative-agents/design-patterns`
(the canonical, 11 patterns), `agent-failure-modes/aaai-2027` (extends the
canonical via the `da:` prefix; paper scaffolding), and
`agent-failure-modes/ieee-tse` (paper scaffolding with experiment bindings).
The tradition is Christopher Alexander, *A Pattern Language* (1977): the file
is a *language*, not a catalogue — each pattern names a field of forces and the
configuration that resolves them, and the grammar connects each pattern to the
larger ones that create its context and the smaller ones that complete it.

## The header comment block (required)

A `# ===` framed comment before the YAML, containing at minimum:

- **WHAT THIS FILE IS** — the language's subject and the Alexander tradition.
- **HOW TO READ EACH ENTRY** — the per-field legend (copy from the template
  and adjust for any extension fields).
- When the language is paper scaffolding: the **INTERNAL-ONLY RULE** — coined
  pattern names never appear in the paper's prose; each pattern carries a
  `paper` field saying where it lives in the draft and how it reads in
  natural language.
- When sibling languages exist: a **SCOPE BOUNDARY** naming what belongs to
  each sibling and the rule that a shared structure is linked
  (`grammar.overlaps`, `examples.kind: sibling`, or `extends`) and never
  restated.
- A **PROVENANCE** note when patterns come mostly from one reference
  implementation: a single system reveals forces but cannot establish
  recurrence; external examples carry that burden.
- Optionally, **THE ARGUMENT, TOP TO BOTTOM** — a one-paragraph walk through
  the numbered patterns showing the grammar as a single readable argument.

## Top-level keys

| Key | Required | Content |
|---|---|---|
| `title` | yes | "A Pattern Language for <domain>" |
| `version` | yes | integer, starts at 1 |
| `based_on` | yes | the Alexander 1977 citation (copy from template) |
| `extends` | when applicable | which sibling language this builds on and the reference prefix it uses (e.g. `"da:"`) |
| *domain summary* | recommended | a named block (e.g. `declarative_agent:`, `reliability_argument:`) defining the whole the language builds — summary, parts, a canonical example |
| `conventions` | yes | `confidence_scale` (0/1/2 definitions) and `relationship_types` (the five grammar relations) — copy from template verbatim |
| `patterns` | yes | the list (below) |
| `grammar_check` | optional | a note asserting connectivity (no orphan patterns; all references resolve) |
| `bibliography` | yes* | citation key → `{text, url?}`; *or `bibliography_note` pointing at an external references file (ieee-tse style, when the repo already keeps a references.yaml) |

## Per-pattern entry

Invariant keys, in this order:

| Key | Form | Content |
|---|---|---|
| `id` | kebab-case | stable machine key; grammar references use it |
| `number` | int, unique | position in the language; **larger/earlier → smaller/later** (Alexander's ordering: big context patterns first) |
| `name` | Title Case | the coined name |
| `also_known_as` | list | prior names for the same structure (may be empty) |
| `confidence` | 0, 1, or 2 | Alexandrian rank: 2 = deep invariant across many independent systems; 1 = well-supported, the specific form here is newer; 0 = tentative, largely from the reference implementation |
| `intent` | one sentence | what the pattern does |
| `context` | prose | the situation (and larger patterns) that must exist first |
| `problem` | prose, a question | the headline tension stated as a question of forces |
| `applicability` | prose | when to use it and when its cost is not justified (canonical instance; optional in scaffolding instances) |
| `forces` | list | the competing pressures held in balance — the CONSTRAINT side |
| `solution` | prose, imperative | the resolution ("therefore: do this") — the RECIPE side; recipe and constraint are one thing seen from two sides |
| `implementation` | prose | construction rules and checks that make it executable without other documents |
| `consequences` | `benefits:` + `liabilities:` lists | both required — a pattern with no liabilities is advertising |
| `grammar` | 5 lists | `within` / `requires` / `contains` / `enables` / `overlaps`, each a list of pattern ids (bare = this file; `prefix:id` = a sibling language named in `extends`) |
| `syntax` | one line | the pattern in combination — a "sentence" of the language (canonical instance) |
| `examples` | list of `{system, cite, kind, note}` | independent occurrences; `kind: external` (recurrence evidence) / `internal` (reference implementation) / `sibling` (another language's pattern); **every `cite` must resolve in the bibliography** |

Extension keys, by use:

| Key | When | Content |
|---|---|---|
| `paper` | paper scaffolding | where the pattern lives in the draft and its natural-language phrasing (the prose never uses the coined name) |
| `paper_sections` | paper scaffolding | list of section bindings, e.g. `["1 (framing)", "5 (specification structures)"]` |
| `experiments` | when the paper has experiments | which experiment exercises this pattern |
| `provenance` | optional | e.g. `[reference-implementation, external-corroboration]` |

## Grammar semantics

- `within`: larger patterns whose context this pattern helps complete.
- `requires`: patterns that must already be in place for this one to hold.
- `contains`: smaller patterns that complete or refine this one.
- `enables`: patterns this one makes possible.
- `overlaps`: patterns addressing a neighbouring force by a different means.

The language must form one connected graph — no orphan patterns. Reading the
numbers in order should reconstruct the argument (the header's "top to bottom"
paragraph is that reading, written out).

## Quality bar (what the existing instances actually do)

- Every pattern has 3+ forces and both benefits and liabilities.
- Confidence-2 patterns carry many external examples (the canonical's
  Machine Interpreter has 13); confidence-0 patterns say so plainly.
- Citations are full references (author, year, title, publisher/venue),
  not bare URLs; URLs supplement.
- Solutions are imperative and specific enough to check a design against;
  "consider using X" is not a solution.
- The file is self-contained: nothing requires an accompanying chapter to be
  understood.

## Validation

`scripts/validate_language.py <file>` enforces the structural half of this
spec: required keys, unique ids/numbers, confidence domain, grammar references
resolving (bare ids to this file; `prefix:` ids allowed when `extends` is
present), cites resolving in the bibliography (skipped under
`bibliography_note`), and consequences carrying both sides.
