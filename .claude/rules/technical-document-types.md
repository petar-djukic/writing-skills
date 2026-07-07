<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->

# Technical Document Types

We catalog the document types of standards bodies and engineering
practice. Each entry gives a short purpose statement, where the type
originates, when to choose it, and the structure to follow when one is
established. We list types in roughly the order they arise in a project's
life: from idea, to requirements, to design, to standardisation.

This catalog covers the external and industry forms. For documents inside
a repository following our conventions, the YAML document types in
[documentation-standards.md](documentation-standards.md) (VISION,
ARCHITECTURE, PRDs, use cases, test suites) take precedence; use this
catalog to pick the right form when writing for an audience outside the
repo.

## Concept Paper

A concept paper proposes a new idea or primitive and argues for it. It is
exploratory, not prescriptive. Length is typically a few pages to a short
chapter.

Origin. Common in academic and industrial research practice. The form has
no single owning body. Funding agencies such as the US National Science
Foundation and the European Commission use the term for short
pre-proposals that precede a full grant application.

When to use. Early-stage work where the goal is to establish a
vocabulary, a problem framing, or a single design primitive. Useful for
circulating to peers before committing to a full design or specification.

Structure. There is no canonical template. A common shape is:

- Motivation and problem statement
- Background and related work
- Proposed concept, named and defined
- Worked scenario or example
- Open questions and next steps

## Position Paper

A position paper argues for a stance on a contested question. It is
shorter and more polemical than a concept paper. The author takes a side
and defends it.

Origin. Standard format in academic workshops and standards bodies such
as the IETF and W3C, where workshop calls often request 2 to 4 page
position papers to seed discussion.

When to use. To frame a debate, push back on a prevailing approach, or
stake a claim in advance of a design effort.

Structure. Even shorter than a concept paper. Typical elements:

- The question or claim
- The author's position, stated up front
- Supporting arguments
- Acknowledgement of counter-arguments
- Implications if the position is accepted

## Whitepaper

A whitepaper is an authoritative report that explains an issue, a
technology, or a solution to a non-specialist technical audience. It is
longer than a concept or position paper and reads as a finished piece.

Origin. The term originated in British government practice in the 1920s
for policy reports. The technology industry adopted the format in the
1990s, and vendors use it heavily.

When to use. To communicate a mature view of a technology or architecture
to customers, partners or executives. Whitepapers presume the reader is
technical but not expert in the specific area.

Structure. Publisher templates vary. A common structure is:

- Executive summary
- Problem statement and context
- Proposed approach
- Benefits and trade-offs
- Case studies or worked examples
- Conclusion and call to action
- References

## Product Requirements Document (PRD)

A PRD captures what a product should do, for whom, and why. It is written
before design begins, and signed off by product, engineering and design
stakeholders.

Origin. The PRD is a product-management convention, popularised by Marty
Cagan's *Inspired* and widely used at firms such as Google, Microsoft and
Atlassian. There is no standards body. Atlassian, Aha! and ProductPlan
publish reference templates.

When to use. When a product or feature is being scoped, before
architecture or implementation work starts. For PRDs inside a repository
following our conventions, the repo's own PRD format (see
documentation-standards.md) takes precedence; this entry describes the
industry form.

Structure. Typical sections:

- Objective and success metrics
- Target users and personas
- User stories and use cases
- Functional requirements
- Non-functional requirements (performance, accessibility, security)
- Out of scope
- Open questions
- Release criteria

## System Requirements Document (SRD) or Software Requirements Specification (SRS)

An SRD or SRS captures the requirements a system must satisfy in
normative form. Where the PRD speaks the language of the product, the SRD
speaks the language of the system being built.

Origin. The canonical reference is IEEE 830-1998, *Recommended Practice
for Software Requirements Specifications*, superseded by ISO/IEC/IEEE
29148-2018, *Systems and software engineering — Life cycle processes —
Requirements engineering*. The European Cooperation for Space
Standardization publishes a parallel document, ECSS-E-ST-10-06C, for
space systems.

When to use. In regulated, safety-critical or contractually scoped
projects where a normative baseline is required.

Structure. IEEE 830 prescribes:

1. Introduction (purpose, scope, definitions, references, overview)
2. Overall description (product perspective, functions, user
   characteristics, constraints, assumptions)
3. Specific requirements (external interfaces, functions, performance,
   logical database requirements, design constraints, software system
   attributes)
4. Supporting information (appendices, index)

Requirements are written with "shall" verbs and given identifiers for
traceability.

## Architecture Requirements Document (ARD)

An ARD captures the architecturally significant requirements (ASRs) that
constrain the system design. It is a focused subset of the SRD, surfacing
the requirements that drive architectural decisions.

Origin. The ARD is less standardised than the SRD. The SEI's *Software
Architecture in Practice* (Bass, Clements, Kazman) defines architecturally
significant requirements as the centre of architecture work. Some
organisations split the ARD out as a separate artefact; others fold it
into the SRD or the architecture description.

When to use. When the project is large enough that quality attributes
(performance, security, scalability, modifiability) need explicit
elaboration before design starts.

Structure. A common shape:

- Business goals and drivers
- Stakeholders and concerns
- Functional ASRs
- Quality attribute scenarios (stimulus, source, environment, response,
  measure)
- Constraints (technical, regulatory, organisational)
- Assumptions

## Architecture Design Document (ADD)

An ADD describes how a system is structured to meet its requirements. It
covers components, interfaces, data, deployment and the rationale that
ties the design to the requirements.

Origin. ISO/IEC/IEEE 42010, *Systems and software engineering —
Architecture description*, is the international standard for what an
architecture description must contain. The IEEE 1471 predecessor
introduced the multi-view concept formally in 2000. TOGAF and the SEI
Views and Beyond approach both build on 42010.

When to use. After requirements are stable and before implementation
begins. Maintained through the life of the system as the source of truth
for its structure.

Structure. ISO/IEC/IEEE 42010 requires the description to identify:

- Stakeholders and their concerns
- Architecture viewpoints used
- Architecture views, one per viewpoint
- Correspondence rules between views
- Architecture rationale
- Architecture decisions (often captured as ADRs)

Common views include functional, information, deployment, concurrency,
operational and security.

## Architecture Decision Record (ADR)

An ADR records a single architectural decision: the context that forced
it, the decision taken, and the consequences. ADRs are short, dated and
append-only.

Origin. Michael Nygard introduced the ADR format in a 2011 blog post,
*Documenting Architecture Decisions*. The format has been adopted widely;
ThoughtWorks placed ADRs in the *Technology Radar* "adopt" ring, and
GitHub hosts a community catalogue at `adr.github.io`.

When to use. Every time a decision is made that future maintainers would
otherwise have to reverse-engineer. ADRs accumulate in the repository
over the life of the project.

Structure. Nygard's original template:

- Title (short noun phrase)
- Status (proposed, accepted, deprecated, superseded by ADR-N)
- Context (the forces at play)
- Decision (the response to those forces)
- Consequences (positive, negative and neutral outcomes)

Variants such as MADR (Markdown Architectural Decision Records) add
sections for considered options and decision drivers.

## Request for Comments (RFC)

An RFC is a written proposal circulated for review before adoption. The
term covers two related but distinct practices.

Origin. The IETF RFC series began in 1969. Steve Crocker's RFC 1
documented the *Host Software* protocol for the ARPANET. The series is
now managed by the RFC Editor and governed by RFC 2026, *The Internet
Standards Process*. Internally, many technology companies (Squarespace,
Uber, Oxide, Rust) run their own RFC processes adapted from the IETF
model.

When to use.

- IETF RFCs document Internet protocols, formats and processes. They are
  authoritative once published.
- Internal RFCs propose significant changes to a codebase or architecture
  before implementation begins. They sit between an ADR (which records a
  decision already taken) and a design document (which assumes the
  decision is made).

Structure. The IETF RFC format is prescribed by RFC 7322. Common
sections:

- Abstract
- Status of this memo
- Copyright notice
- Table of contents
- Introduction
- Conventions and terminology (often citing RFC 2119 for "MUST", "SHOULD")
- Body (protocol mechanics, formats, behaviour)
- Security considerations
- IANA considerations
- References (normative and informative)
- Author addresses

Internal RFC templates are lighter, typically:

- Summary
- Motivation
- Proposed change
- Alternatives considered
- Drawbacks
- Open questions
- Adoption plan

## Engineering Design Document (EDD or Design Doc)

The engineering design document, often just called a "design doc", is the
working artefact engineers write before building a feature or service. It
sits below the ADD and above the code.

Origin. Google's internal design-doc culture, described publicly by Malte
Ubl and others, popularised the form. The pattern predates Google and
exists in most large engineering organisations under different names.

When to use. Before writing non-trivial code. The design doc is the input
to peer review and the artefact that captures the design that was
actually built.

Structure. A common shape:

- Context and goals
- Non-goals
- Proposed design (data model, APIs, components)
- Alternatives considered
- Cross-cutting concerns (security, privacy, observability, rollback)
- Migration and rollout
- Testing strategy
- Open questions
- Appendix

## Specification

A specification is a precise, normative description of an interface,
format or protocol. It is the artefact an implementer reads in order to
build a conforming implementation.

Origin. Specifications come from many bodies. ISO, IEC, IEEE, ITU-T,
3GPP, ETSI, IETF, W3C, TM Forum and OASIS all publish specifications
under their own processes and document conventions.

When to use. When multiple independent implementations must interoperate,
or when conformance is going to be tested.

Structure. Varies by body. Common elements:

- Scope and conformance criteria
- Normative references
- Terms and definitions
- Symbols and abbreviations
- Body (normative requirements, often with "shall" and "should")
- Conformance clause
- Annexes (normative and informative)

## Invention Disclosure

An invention disclosure is filed inside a company to describe an
invention before a patent application is drafted. It is internal,
confidential and written to a template the patent committee can evaluate.

Origin. Each company maintains its own template; there is no external
standards body.

When to use. Whenever an invention is made and the company wants to
consider patenting it. The
[patent-disclosure skill](../skills/patent-disclosure/SKILL.md) writes
disclosures to an eleven-section template with a four-axis
self-assessment.

Structure. Company templates typically include:

- Title and claim
- Inventors
- Problem and prior art
- Proposed solution
- Embodiments and variations
- Advantages
- Evidence of novelty

## Quick Reference

| Document | Primary purpose | Authoritative source |
|---|---|---|
| Concept paper | Propose an idea | None |
| Position paper | Argue a stance | Workshop conventions |
| Whitepaper | Explain to a wide audience | Publisher template |
| PRD | Capture product intent | Industry practice |
| SRD / SRS | Capture normative system requirements | ISO/IEC/IEEE 29148-2018 |
| ARD | Capture architecturally significant requirements | SEI practice |
| ADD | Describe the architecture | ISO/IEC/IEEE 42010 |
| ADR | Record one decision | Nygard (2011) |
| RFC (IETF) | Standardise a protocol | RFC 7322, RFC 2026 |
| RFC (internal) | Propose a significant change | Local convention |
| Design doc / EDD | Plan an implementation | Local convention |
| Specification | Define an interface for conformance | SDO of origin |
| Invention disclosure | Seed a patent application | Company template; patent-disclosure skill |

## References

- ISO/IEC/IEEE 29148-2018, *Systems and software engineering — Life cycle
  processes — Requirements engineering*.
- ISO/IEC/IEEE 42010:2022, *Software, systems and enterprise —
  Architecture description*.
- IEEE 830-1998, *Recommended Practice for Software Requirements
  Specifications* (superseded).
- IETF RFC 2026, *The Internet Standards Process — Revision 3*,
  S. Bradner, 1996.
- IETF RFC 7322, *RFC Style Guide*, H. Flanagan and S. Ginoza, 2014.
- IETF RFC 2119, *Key words for use in RFCs to Indicate Requirement
  Levels*, S. Bradner, 1997.
- M. Nygard, *Documenting Architecture Decisions*, blog post, 2011.
- L. Bass, P. Clements, R. Kazman, *Software Architecture in Practice*,
  4th ed., Addison-Wesley, 2021.
- M. Cagan, *Inspired: How to Create Tech Products Customers Love*,
  2nd ed., Wiley, 2017.
- The Open Group, *TOGAF Standard, 10th Edition*, 2022.
- MADR project, *Markdown Architectural Decision Records*,
  https://adr.github.io.
