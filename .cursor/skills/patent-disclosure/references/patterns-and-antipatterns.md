# Patterns and anti-patterns

Four claim/description patterns that survive evaluation, five that fail,
each with the fix. Examples are domain-neutral; substitute the project's
own entities.

## Claim anatomy

A claim names a method or system and then enumerates limitations. Every
limitation must be supported in Section 6 and distinguished in Section 5:

```
"A method for validating requested actions using model-driven agents
that perform predictive what-if analysis, comprising:

1. receiving, by a request handler, an action request from a requester;
2. generating, by the request handler, an analysis sub-request and
   transmitting it to an analysis agent, wherein the analysis agent
   embeds a structured domain model;
3. determining, by the analysis agent, whether the request can be
   satisfied by issuing what-if queries over the domain model..."
```

Elements to support here: "model-driven agents" (why a model is
necessary), "predictive what-if analysis" (the algorithm), "structured
domain model" (its structure and purpose), and each numbered step
(implementation detail).

## Strong patterns

### 1. Novel data structure with technical purpose

"A domain-model data structure for request validation, comprising a
directed acyclic graph with nodes representing system entities and edges
representing typed relationships (depends_on, constrains, provides);
wherein nodes carry validation-relevant attributes enabling traversal
algorithms to compute request feasibility in O(n log n) time; wherein the
DAG structure guarantees no circular dependencies, preventing validation
deadlocks; and wherein edge weights represent constraint strength
enabling priority-based conflict resolution."

Why strong: specific structure, technical purpose, quantified complexity,
a named problem prevented, a capability enabled.

### 2. Multi-component system with novel interaction

"A distributed management system comprising: a first agent configured to
perform local optimization over an embedded domain model; a second agent
configured to validate proposed actions against a policy set; and a
coordination protocol wherein the first agent transmits a proposed action
with a model-derived justification, the second agent evaluates the
justification against policy constraints, and returns approval with a
residual constraint set the first agent incorporates into subsequent
optimization; wherein the justification enables policy evaluation without
exposing the optimization algorithm, preserving agent autonomy while
ensuring system-wide compliance."

Why strong: specific roles, a novel interaction (justification + residual
constraints), a named trade-off resolved (autonomy vs. compliance).

### 3. Hybrid algorithm with adaptive behavior

"A method for request translation comprising: maintaining a cache of
known request patterns mapped to execution logic; computing a similarity
score between an incoming request and cached patterns; if the score
exceeds threshold T, executing the mapped logic (fast path); otherwise
generating a dynamic prompt from the domain model, invoking a language
model, parsing the response into execution logic, executing it (adaptive
path), and caching successful logic; wherein T is adjusted from cache hit
rate and inference latency to balance response time and adaptability."

Why strong: hybrid of known strengths, adaptive threshold, computable
steps, explicit management of the latency/adaptability trade-off.

### 4. Cross-domain optimization with novel constraint handling

"A multi-agent optimization system wherein each agent optimizes one
domain under a local objective and constraint set; a coordination agent
maintains a global constraint graph of inter-domain dependencies; wherein
a proposed local optimization triggers graph traversal to identify
affected domains, computation of constraint-violation probability per
domain, and — above a threshold — a negotiation protocol in which agents
bid on constraint relaxation using utility functions, yielding
Pareto-optimal cross-domain solutions without a centralized objective or
global state synchronization."

Why strong: distributed and scalable, a novel probabilistic concept, an
economic protocol, global optimization without centralization.

## Anti-patterns

### 1. Generic AI application

Bad: "Collect data; apply machine learning; act on the outputs."
Why weak: no algorithm, no problem, obvious to try, Alice/Mayo bait.
Fix: name the model, features, output, the improvement over prior art,
and the technical constraint addressed.

### 2. Obvious combination

Bad: "System comprising module A (prior art), module B (prior art), and
module C (prior art), communicating via REST."
Why weak: no unexpected interaction; obvious to any engineer.
Fix: identify a novel interaction between the components, or a technical
integration problem solved non-obviously.

### 3. Business method in disguise

Bad: "Collect usage data; determine willingness to pay; adjust quality of
service to maximize revenue."
Why weak: the innovation is business logic; the technical elements are
conventional; abstract-idea rejection likely.
Fix: claim the specific technical mechanism enabling the goal, with a
technical effect beyond the business outcome.

### 4. Vague improvement

Bad: "Improving performance by optimizing configurations using
intelligent algorithms."
Why weak: every operative word is undefined; infringement undetectable.
Fix: which metric, which parameters, which algorithm, why better.

### 5. Result without method

Bad: "A system that achieves 99.99% uptime and zero-touch operation."
Why weak: claims the outcome, not the mechanism; outcomes are not
patentable.
Fix: describe and claim the specific technical mechanisms that produce
the result.
