# The four-axis evaluation framework

Patent professionals evaluate inventions on four dimensions before
allocating filing budget. A disclosure must address all four convincingly;
the skill's self-assessment (assets/checklist.md) scores each axis against
its target before a disclosure is called ready.

## Axis 1 — Novelty (target 8-10/10)

Novelty means the specific technical thing does not exist in prior art —
not that the general idea is fashionable.

**Novel (good):**
- Specific algorithms not described in the literature
- Unique data structures serving a technical purpose
- Novel coordination or communication protocols that solve a named problem
- New methods of integrating components (e.g. an LLM inside a control loop)
  where the integration itself is the contribution
- Specific architectural patterns with properties prior architectures lack

**Not novel (avoid):**
- Generic "use AI for X" (broadly known)
- Standard workflows from published frameworks or standards
- Conventional monitoring, alerting, orchestration
- Simple application of a known technique to a known problem without a
  new mechanism

**Prior-art search strategy:**

1. Standards bodies relevant to the domain (the project context file names
   them; if none, identify the bodies whose specifications an implementer
   in this domain would read).
2. Academic literature — delegate the search to the `update-references`
   skill: arXiv and Google Scholar queries built from the claim's key
   terms, results recorded in `references.yaml`.
3. Competitor patents — search assignees named in the project context;
   otherwise search the claim's key terms across Google Patents,
   Espacenet, USPTO, WIPO Patentscope.
4. Classification codes (CPC/IPC) for the domain, plus forward and
   backward citations of the closest hits.

**In the disclosure:** document the search in Section 3, identify the
closest prior art explicitly, articulate precisely what gap the invention
fills, and use comparison tables to make the differences scannable.

## Axis 2 — Non-obviousness (target 7-10/10)

The legal standard: would a skilled engineer, knowing the prior art, find
this obvious? The test is not whether they *could* arrive at it but
whether they *would* without inventive insight.

**Strong indicators:**
- **Unexpected results** — "prior art achieves a 30% reduction; this
  approach achieves 70% through mechanism X"
- **Overcomes technical prejudice** — the field assumed A was necessary;
  the invention proves B superior
- **Solves a long-standing problem** — a named difficulty the field has
  documented and not resolved
- **Synergistic combination** — components together produce capability
  neither has alone, and the interaction is the invention
- **Counter-intuitive approach** — adding apparent overhead improves the
  outcome, with a mechanism explaining why

**Weak indicators (avoid):**
- "Just apply machine learning" (obvious to try)
- "Use a modern framework" (engineering choice)
- "Combine known components" without unexpected interaction
- "Optimize an existing metric" without a novel method

**Claim-scope laddering.** Provide three scopes so the examiner can
narrow rather than reject:
- **Broad:** the fundamental architectural idea (highest value, highest
  obviousness risk)
- **Medium:** the key technical elements that create the non-obvious
  advantage
- **Narrow (fallback):** implementation specifics that ensure
  patentability

Example of narrowing (domain-neutral):
- Too broad: "A method for automating decisions using AI agents."
- Better: "A method for validating requested actions using model-driven
  agents that perform predictive what-if analysis over a structured
  domain model."
- Narrow: "…wherein the domain model comprises a graph with typed edges
  representing dependency relationships, and the agent generates queries
  over the graph dynamically from natural-language what-if questions."

**In the disclosure:** address obviousness explicitly in Section 5,
quantify improvements, explain the technical barriers overcome, describe
alternatives considered and why they fail, and provide the three claim
scopes.

## Axis 3 — Commercial value (target 7-10/10)

Three value categories; identify which the invention belongs to.

| Category | Revenue model | Indicator |
|---|---|---|
| Standards-essential (SEP) | FRAND licensing, high volume, low per-unit | The invention solves an interoperability problem, fits naturally in a standard (API, protocol, data model), or is already in draft contributions |
| Competitive blocking | Cross-licensing, defensive portfolio | Competitors must solve the same problem; the invention covers approaches they are likely to adopt |
| Foundational | Broad licensing across industries, long horizon | Creates a new capability class, applicable outside the origin domain, fundamental to a next-generation architecture |

**Licensee identification.** List primary (direct competitors and
customers in the origin domain), secondary (adjacent markets using the
same mechanism), and tertiary (industries the mechanism generalizes to).
Take names from the project context file; never invent market claims.

**Revenue framing:**

```
SEP value        = units/year x fee/unit x market coverage x essentiality
Blocking value   = competitor R&D saved + cross-license value + market protection
Foundational     = new market size x coverage x share x license rate
```

**In the disclosure:** Section 9 names licensee categories, estimates
applicability, explains why licensees need this, and flags standards-track
potential.

## Axis 4 — Patentable subject matter (target 8-10/10)

US law (Alice/Mayo) rejects abstract ideas even when novel; European law
requires technical character. Software and AI/ML claims face particular
scrutiny.

**Alice/Mayo two-step (US):**
1. Is the claim directed to an abstract idea? Abstract: business methods,
   mental processes, mathematical formulas, organizing information.
   Not abstract: specific technical implementations, improvements to
   computer or system functionality, novel data structures with a
   technical purpose.
2. If abstract, is there an inventive concept — concrete technical
   elements transforming the idea into a patent-eligible application?

**European technical-character test:** a technical problem, solved by
technical means, achieving a technical effect. Strong: improved
performance (latency, throughput, reliability), reduced resource
consumption, new technical capability, solved coordination problem.
Weak: business-process optimization, generic data processing, UI polish
without technical effect.

**Phrasing table:**

| Don't say | Say |
|---|---|
| "A method for optimizing systems using AI" | "A method reducing convergence time 40% through coordination protocol X" |
| "Organizing data for efficient retrieval" | "A graph structure enabling sub-100ms validation through pre-computed constraint paths" |
| "Automating decisions" | "An integration architecture maintaining closed-loop stability through bounded inference time and rollback" |
| "Applying machine learning to the problem" | "A conflict-resolution algorithm guaranteeing policy consistency across distributed domains" |

**Four strategies:**
1. **Tie to a specific technical problem** — a measured limitation, not a
   business need.
2. **Specify the technical implementation** — the algorithm, its inputs,
   its bounds.
3. **Claim the technical effect** — complexity bounds, latency numbers,
   consistency guarantees.
4. **Include the system architecture** — components, interfaces, delivery
   guarantees.

**In the disclosure:** Sections 2 and 4 establish the technical problem;
Sections 5-6 carry the implementation detail; quantify improvements;
diagram the architecture.

## Detectability (cross-cutting, scored in the rubric)

A patent is only valuable if infringement can be detected.

- **High (preferred):** standards-mandated interfaces, observable message
  patterns, response-time signatures, customer-visible features and API
  documentation.
- **Moderate:** reverse engineering, timing analysis, vendor marketing
  claims and publications.
- **Low (risky):** purely internal algorithms with no external
  manifestation — often better held as trade secrets.

Section 7 of the disclosure must describe observable behaviors at system
boundaries, standards-mandated elements if any, and a concrete testing
methodology for infringement.
