# Section-by-section writing guide

The disclosure has eleven sections (assets/disclosure-template.md is the
skeleton). This guide gives each section's purpose, structure, and the
link back to the claim. Write in the recommended order, not template
order.

## Recommended writing order

1. **Section 4 (Problem)** — start with a clear problem statement
2. **Section 5 (Summary)** — high-level solution concept
3. **Section 6 (Details)** — detailed implementation
4. **Section 2 (Context)** — background needed to understand the problem
5. **Section 3 (Prior art)** — search after knowing the solution
6. **Section 7 (Detectability)** — based on the implementation detail
7. **Sections 8-11** — metadata and supporting information

## The claim as north star

The claim (Section 1 / title page) is the legal boundary. Before writing
any section: read the claim, enumerate its limitations (the specific
technical elements), understand what is included and excluded, and verify
the material exists to support every limitation. Every section must
support, explain, or justify the claim; every numbered claim step needs
implementation detail in Section 6 and a distinguishing feature in
Section 5.

## Section 2 — Technical context

Only enough background to understand the problem. Include: the current
state of the field, the architectural elements the claim assumes, and a
definition for every technical term the claim uses. Avoid: describing the
invention (Sections 5-6), generic background, prior-art detail
(Section 3).

## Section 3 — Relevant state of the art

Three required subsections.

**A. Current technology summary** — existing solutions as a comparison
table:

| Prior art | Approach | Strengths | Weaknesses |
|---|---|---|---|
| (product/standard) | (mechanism) | (what it does well) | (the gap this invention fills) |

**B. Patent prior art** — for each relevant patent: number, assignee,
title, key claims, and an explicit "differs:" line.

**C. Non-patent literature** — standards, papers, reports: document ID,
title/authors, relevant sections with page numbers, and the "differs:"
line.

Be thorough — the examiner will search these sources. Never omit close
prior art; address it directly.

## Section 4 — Technical problem

The problem-statement formula:

```
Prior art approaches [X, Y, Z] suffer from [specific technical
limitation]. This manifests as [measurable negative consequence]. The
root cause is [technical explanation]. Specifically, [the technical
barrier in detail]. This creates the need for [specific technical
capability] that prior art does not provide.
```

Strong statements name the mechanism of failure and quantify the
consequence. Weak statements to avoid: "systems are complex and hard to
manage" (generic), "operators want automation" (business need), "current
systems are inefficient" (vague). Every claim element should answer some
part of this problem — if the claim includes a component, the problem
explains why that component is needed.

## Section 5 — Summary and distinguishing features

- **5.1 Solution overview** (2-3 paragraphs): what it is, how it works,
  how it solves Section 4's problem.
- **5.2 Distinguishing features**: a numbered list, each item naming the
  prior art it differs from and the mechanism of difference ("Unlike
  [prior art], our [component] does [mechanism], enabling [capability]").
- **5.3 Technical effects**: quantified improvements (performance,
  efficiency, reliability, cost).
- **5.4 Standards-essential elements** (if applicable): which features
  align with or are candidates for standardization.

Each claim element gets a corresponding distinguishing feature and effect.

## Section 6 — Detailed implementation

The section that determines claim supportability. Sufficient detail that
a skilled engineer could implement it.

- **6.1 System architecture** — logical and deployment diagrams:
  components, interfaces, data paths, control flow.
- **6.2 Component descriptions** — for each claimed component: purpose,
  structure, numbered operation steps, data structures (with schemas),
  and pseudocode for the key algorithms.
- **6.3 Interaction flows** — sequence diagrams for the happy path,
  error handling, and coordination scenarios.
- **6.4 Implementation alternatives** — variations that still achieve the
  inventive concept. Alternatives broaden coverage (harder to design
  around), pre-empt scope rejections, and show the concept is fundamental
  rather than implementation-bound.
- **6.5 Technical advantages** — WHY the benefits arise, mechanism by
  mechanism, with a comparison against prior-art latencies/costs.
- **6.6 Use cases** — concrete workflows exercising the invention.
- **6.7 Integration** — how the invention composes with the surrounding
  architecture and any related disclosures.

## Section 7 — Detectability

- **7.1 Observable behaviors at system boundaries** — message formats,
  API patterns, latency signatures distinguishable from prior approaches.
- **7.2 Standards-mandated elements** — interfaces that become mandatory
  and therefore observable if standardized.
- **7.3 Testing methodologies** — concrete black-box tests: input,
  observed behavior, what the observation proves about the internals.
- **7.4 Reverse-engineering indicators** — marketing claims,
  documentation, publications, competitor filings.
- **7.5 Risk assessment** — an explicit detectability score with
  reasoning.

## Section 8 — Use of generative AI

Transparency section (regulatory requirement in some jurisdictions). Two
distinct cases:

- **AI assisted the writing:** name the tool and version; state the human
  contributions (conception, technical design, prior-art analysis, claim
  drafting) versus AI contributions (drafting from human outlines,
  structuring, summarization); state that humans verified technical
  accuracy.
- **AI is part of the invention:** state that the inventive concept is
  HOW the model is integrated (architecture, constraints, guarantees),
  not the model itself — the model is a component like a database; the
  invention is the novel integration.

## Section 9 — Further comments

Product roadmap and planned usage; subject-matter experts who can support
examination; standardization plans; competitive intelligence; related
disclosures forming a patent family. Source all of this from the project
context file — never invent it.

## Section 10 — Keywords

Primary, secondary, and domain-specific keyword lists so the examiner
searches the right terminology. Include every significant technical term
from the disclosure and the industry-standard synonyms.

## Section 11 — Abbreviations

Alphabetized table of every abbreviation used. Omit abbreviations more
common than their expansions (HTTP, TCP/IP).

## Writing style

- Precise terminology, used consistently; define before use.
- Active voice; no ambiguous pronouns without clear antecedents.
- Patent-appropriate language: "comprising" (open-ended), "consisting of"
  (closed), "wherein" (adds limitation to an element); explicit causal
  verbs (causes, enables, prevents).
- No marketing language ("revolutionary", "groundbreaking"), no vague
  qualifiers ("efficient", "improved") without quantification, no
  unsupported superlatives. This overlaps the de-ai skill's venue-jargon
  category — run the finished disclosure through de-ai.
