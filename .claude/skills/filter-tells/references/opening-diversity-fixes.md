# Fixing Low Opening Diversity

LLMs default to Subject-Verb-Object structure because it is the safest grammatically. Starting with "The" (the most common definite article) is the most stable way to build that structure. In a white paper, it creates a droning effect where every sentence reads like a feature-list entry rather than a cohesive argument.

The target: reduce "The"-initial sentences to below 15% of total sentences. Human technical writers typically land between 8-15%.

## Technique 1: Adverbial/Prepositional Shift

Move the condition, location, or circumstance to the front. The subject follows.

| Before (AI) | After (Human) |
|-------------|---------------|
| The protocol ensures data integrity across all nodes. | Across all nodes, the protocol ensures data integrity. |
| The orchestrator selects a tool from the catalog. | From the catalog, the orchestrator selects a tool. |
| The system handles failures through retry logic. | By design, the system handles failures through retry logic. |
| The agent records every tool call. | At each step, the agent records the tool call. |
| The controller delegates work to downstream agents. | In the control plane, the controller delegates work to downstream agents. |
| The model processes each request within a fixed time window. | Within a fixed time window, the model processes each request. |
| The planner evaluates constraints before selecting a path. | Before selecting a path, the planner evaluates constraints. |
| The network heals itself after a fiber cut. | After a fiber cut, the network heals itself. |

Prepositional openers to use: "Within...", "Under these conditions...", "By default...", "At runtime...", "From the perspective of...", "In practice...", "For each iteration...", "Before...", "After...", "During..."

## Technique 2: Gerund Lead

Start with the action (-ing form). Creates immediate momentum and emphasizes process over entity.

| Before (AI) | After (Human) |
|-------------|---------------|
| The engine optimizes the query before execution. | Optimizing the query before execution saves cycles. |
| The validator checks each artifact against the spec. | Checking each artifact against the spec catches regressions early. |
| The LLM translates specifications into code. | Translating specifications into code is probabilistic, not deterministic. |
| The controller batches requests to reduce overhead. | Batching requests reduces overhead without sacrificing latency. |
| The system retries failed calls with exponential backoff. | Retrying with exponential backoff prevents thundering-herd problems. |
| The planner decomposes high-level goals into subtasks. | Decomposing goals into subtasks makes each step independently testable. |

Use when: the *action* is more interesting than the *actor*.

## Technique 3: Infinitive Purpose Lead

Start with "To [verb]" to center the reader's goal. Effective in technical writing because it answers "why" before "what."

| Before (AI) | After (Human) |
|-------------|---------------|
| The administrator must configure the firewall rules first. | To secure the network, administrators configure the firewall rules first. |
| The orchestrator invokes the generator when no tool fits. | To handle situations no existing tool covers, the orchestrator invokes the generator. |
| The agent creates a checkpoint before each modification. | To enable backtracking, the agent creates a checkpoint before each modification. |
| The system logs every state transition. | To support post-mortem analysis, every state transition is logged. |
| The planner pre-validates inputs before calling the model. | To avoid wasted inference cycles, the planner pre-validates inputs. |
| The controller rate-limits outgoing API calls. | To protect downstream services, the controller rate-limits outgoing calls. |

## Technique 4: Subordinating Conjunction Lead

Start with "Although...", "While...", "Because...", "When...", "If...", "Once...", "Until..."

| Before (AI) | After (Human) |
|-------------|---------------|
| The LLM generates tokens probabilistically. | Because generation is probabilistic, validation must be deterministic. |
| The composition ceiling limits service architectures. | Although composition is powerful, it has a ceiling. |
| The harness re-runs until tests pass. | Until the tests pass, the harness re-runs the generation cycle. |
| The agent cannot proceed without a valid token. | If the token has expired, the agent cannot proceed. |
| The cache invalidates on every schema change. | When the schema changes, the cache invalidates immediately. |
| The system remains idle during low-traffic periods. | While traffic stays below threshold, the system remains idle. |

## Technique 5: Front-Weighting (Concept Lead)

Put the concept or the "meat" at the sentence start. Human experts front-weight what matters.

| Before (AI) | After (Human) |
|-------------|---------------|
| The primary driver here is scalability. | Scalability, not speed, drives the design. |
| The limitation of these generators is that they are fixed. | Fixed at compile time, these generators cannot produce new targets. |
| The difference between the two levels is scope. | Scope is what separates the two levels, not machinery. |
| The bottleneck in this pipeline is serialization. | Serialization, not compute, is the bottleneck. |
| The missing ingredient is feedback. | Feedback is what closed-loop systems add and open-loop ones lack. |
| The reason for this restriction is safety. | Safety, not convenience, motivates this restriction. |

## Technique 6: Demonstrative or Referential Lead

Replace "The X" with "This", "That", "Such", "Each", "Any", or a referential phrase that ties back to the prior sentence.

| Before (AI) | After (Human) |
|-------------|---------------|
| The agent then proceeds to the next task. | Next, it proceeds to another task. |
| The result is a validated artifact. | What emerges is a validated artifact. |
| The same loop handles both levels. | Both levels share this loop. |
| The constraints apply equally to all agents. | These constraints apply equally to all agents. |
| The pattern recurs in every autonomous system we studied. | Such patterns recur in every autonomous system we studied. |
| The timeout value depends on network conditions. | Each timeout value depends on network conditions at that moment. |

## Technique 7: Past Participial Phrase

Start with a past participle (-ed/-en form) that describes the subject. Creates a compact backstory before the main clause.

| Before (AI) | After (Human) |
|-------------|---------------|
| The controller was designed for resilience and handles cascading failures. | Designed for resilience, the controller handles cascading failures without operator intervention. |
| The API is constrained by backward compatibility requirements. | Constrained by backward compatibility, the API cannot adopt newer serialization formats. |
| The protocol was built on years of operational experience. | Built on years of operational experience, this protocol avoids the pitfalls of earlier attempts. |
| The model was trained on production logs and predicts failures accurately. | Trained on production logs, the model predicts failures with high accuracy. |
| The pipeline was optimized for throughput and sacrifices latency. | Optimized for throughput, the pipeline sacrifices latency on individual requests. |
| The interface was frozen in version 2 and cannot accept new parameters. | Frozen in version 2, the interface cannot accept new parameters without a breaking change. |

Use when: the subject has a relevant history, origin, or constraint that sets up the main point.

## Technique 8: Present Participial Phrase (as modifier)

Start with a present participle that modifies the subject — distinct from Technique 2 (gerund as subject). Here the -ing phrase is a dangling modifier resolved by the subject that follows.

| Before (AI) | After (Human) |
|-------------|---------------|
| The orchestrator recognizes that no tool fits and invokes the generator. | Recognizing that no existing tool fits, the orchestrator invokes the generator. |
| The system operates at scale and encounters novel failure modes daily. | Operating at scale, the system encounters novel failure modes daily. |
| The agent uses context from prior interactions to improve. | Drawing on context from prior interactions, each subsequent attempt improves. |
| The controller monitors all heartbeats and detects partition events. | Monitoring all heartbeats, the controller detects partition events within seconds. |
| The planner considers available resources and assigns tasks accordingly. | Considering available resources, the planner assigns tasks to minimize contention. |
| The validator runs assertions in parallel and reports the first failure. | Running assertions in parallel, the validator reports the first failure it encounters. |

Use when: two actions happen together and one is background/enabling for the other.

## Technique 9: Absolute Phrase

An independent noun phrase with its own participle, grammatically detached from the main clause. Compact and rhythmically distinctive.

| Before (AI) | After (Human) |
|-------------|---------------|
| The preconditions are all satisfied, so the agent proceeds to execution. | All preconditions satisfied, the agent proceeds to execution. |
| The state has been restored, and the controller resumes normal operation. | Its state restored, the controller resumes normal operation. |
| The timeouts were exhausted, so the system escalates to a human operator. | Timeouts exhausted, the system escalates to a human operator. |
| The buffers are full, so the ingestion pipeline drops new events. | Buffers full, the ingestion pipeline drops new events. |
| The quorum was lost, so writes are rejected until recovery. | Quorum lost, writes are rejected until recovery completes. |
| The configuration was locked, so the deployment proceeds with defaults. | Configuration locked, the deployment proceeds with defaults. |

Use when: a condition or state change enables the main action. Reads as clipped and authoritative.

## Technique 10: Nominal Clause Subject (What/How/Whether)

Replace "The X" with a clause that names the concept in action. Puts the reader inside the question before delivering the answer.

| Before (AI) | After (Human) |
|-------------|---------------|
| The coordination mechanism determines overall system throughput. | How agents coordinate determines overall system throughput. |
| The most important factor is state consistency. | What matters most is state consistency. |
| The decision about which tool to invoke depends on context. | Whether to invoke a tool depends entirely on context. |
| The frequency of polling shapes resource consumption. | How often the system polls shapes resource consumption. |
| The choice of serialization format affects interoperability. | Which serialization format you choose affects interoperability. |
| The presence of a human in the loop determines the autonomy level. | Whether a human remains in the loop determines the autonomy level. |

Use when: the "what" or "how" is more interesting than the named entity doing it.

## Technique 11: Rhetorical Question

Shift register to engage the reader directly. Effective at section transitions and when introducing counter-arguments.

| Before (AI) | After (Human) |
|-------------|---------------|
| The difference between L3 and L4 autonomy is scope of action. | What distinguishes L4 from L3? Scope of action. |
| The reason for this constraint is safety. | Why impose this constraint? Safety. |
| The value of closed-loop operation becomes clear under failure conditions. | When does closed-loop operation prove its value? Under failure conditions. |
| The question is whether agents can self-correct without human help. | Can agents self-correct without human help? That is the open question. |
| The real cost of this architecture is operational complexity. | Where does the real cost hide? In operational complexity. |
| The threshold for autonomous action varies by domain. | How much autonomy is enough? It depends on the domain. |

Use sparingly: 1-2 per section maximum. Overuse creates a FAQ tone.

## Technique 12: Comparative/Contrastive Phrase

Start with "Unlike...", "Rather than...", "More than...", or "Less obvious than...". Positions the subject against an alternative.

| Before (AI) | After (Human) |
|-------------|---------------|
| The agentic approach differs from traditional NMS by acting autonomously. | Unlike traditional NMS, the agentic approach acts without waiting for operator input. |
| The orchestrator does more than just route requests. | More than a request router, the orchestrator reasons about sequencing and dependencies. |
| The system polls less frequently than earlier designs. | Rather than polling continuously, the system reacts to events. |
| The new scheduler outperforms the round-robin approach. | Unlike round-robin, the new scheduler accounts for task weight. |
| The agent differs from a script in its ability to adapt mid-execution. | Where a script follows a fixed path, the agent adapts mid-execution. |
| The closed-loop design is less fragile than open-loop alternatives. | Less fragile than open-loop alternatives, the closed-loop design recovers without operator input. |

Use when: the contrast carries argumentative weight. Avoid if the comparison is trivial.

## Technique 13: Quantifier/Numeral Lead

Start with a quantity word: "Three", "Most", "Several", "Few", "Many", "No single", "One". Signals structure and scope.

| Before (AI) | After (Human) |
|-------------|---------------|
| The system faces several constraints at the physical layer. | Three constraints at the physical layer limit what software can achieve. |
| The implementations in production mostly use event-driven patterns. | Most production implementations use event-driven patterns. |
| The approaches all share a common limitation. | No single approach eliminates the need for human oversight entirely. |
| The design requires multiple redundant paths. | Two redundant paths are the minimum for failover. |
| The agents rarely agree on the first round of negotiation. | Few agents agree on the first round of negotiation. |
| The tests catch only a fraction of the edge cases. | Only a fraction of edge cases surface during testing. |

Use when: you can be specific about quantity, or when "most/few/no" carries real meaning.

## Technique 14: Appositive Lead

Start with a noun phrase that labels or reframes the subject before the main clause. Creates a "zoom-in" effect.

| Before (AI) | After (Human) |
|-------------|---------------|
| The latency budget is a key constraint that shapes the entire pipeline. | A hard constraint—the latency budget—shapes the entire pipeline. |
| The orchestrator is the single point of coordination in this architecture. | One component, the orchestrator, serves as the single point of coordination. |
| The retry logic is an often-overlooked factor in system reliability. | An often-overlooked factor, retry logic, determines whether transient faults become outages. |
| The intent engine is the bridge between business goals and network actions. | A bridge between business goals and network actions, the intent engine translates one into the other. |
| The feedback loop is what separates L4 from L3. | A distinguishing feature of L4, the feedback loop enables correction without human prompting. |
| The control plane is the most attack-prone surface in this design. | The most attack-prone surface in this design, the control plane requires hardened authentication. |

Use when: you want to introduce a concept with a characterization before naming it.

## Technique 15: Coordinating Conjunction (Stylistic)

Start with "But", "And", "Yet", "So", or "Or". Once considered informal, now standard in technical prose. Creates tight inter-sentence cohesion.

| Before (AI) | After (Human) |
|-------------|---------------|
| The architecture handles normal operation well. The edge cases remain problematic. | The architecture handles normal operation well. But edge cases remain problematic. |
| The agent succeeded on the first attempt. The result still needs validation. | The agent succeeded on the first attempt. Yet the result still needs validation. |
| The specification defines the interface. The implementation interprets it with latitude. | The specification defines the interface. And the implementation interprets it with latitude. |
| The test passed locally. The CI pipeline rejected it. | The test passed locally. But CI rejected it. |
| The latency target was met. The cost per request doubled. | The latency target was met. Yet cost per request doubled. |
| The protocol is simple. The failure modes are not. | The protocol is simple. Its failure modes are not. |

Use when: the second sentence contradicts, extends, or redirects the first. The conjunction signals the logical relationship.

---

## Application Rules

1. **Do not apply uniformly.** If every sentence uses a prepositional opener, you create a new pattern. Mix techniques across all 15.
2. **Preserve meaning.** Front-loading can shift emphasis. Make sure the new emphasis matches the argument's intent.
3. **Respect natural "The" usage.** Some sentences must start with "The" because the definite article is doing real work (introducing a previously established concept for the first time in a paragraph, or contrasting "the X" against "an X").
4. **Target density.** In a paragraph of 6 sentences, at most 1 should start with "The". In a full section, aim for < 15%.
5. **Check the result.** After rewriting, verify that opening diversity rose above 0.6 (60% unique first words).
6. **Layer techniques.** A single paragraph might use a rhetorical question (#11) to open, a participial phrase (#8) for the second sentence, a bare quantifier (#13) for the third, and a conjunction (#15) for the fourth. Variety within a paragraph matters more than variety across the document.

## Rewrite Prompt for Opening Diversity

Use this prompt when the structural scan flags `low-opening-diversity`:

```
The following text has {diversity_percent}% sentence-start uniformity. {count} of {total} sentences start with "The".

Rewrite this section to reduce "The" openings to below 15% of sentences.

TECHNIQUES TO USE (mix them across all 15 patterns — do not apply any one uniformly):

Reordering:
1. Prepositional phrase: "Within the...", "Under these conditions...", "At runtime..."
2. Temporal/conditional/concessive clause: "When...", "If...", "Although...", "Because..."

Subject transforms:
3. Gerund as subject: "Implementing...", "Scaling...", "Checking..."
4. Nominal clause: "What matters is...", "How X works determines..."
5. Quantifier/numeral: "Three factors...", "Most...", "No single..."

Opening modifiers:
6. Past participial: "Designed for...", "Constrained by...", "Built on..."
7. Present participial: "Recognizing this...", "Operating at...", "Drawing on..."
8. Absolute phrase: "All checks complete, ...", "Timeouts exhausted, ..."

Purpose and emphasis:
9. Infinitive purpose: "To achieve...", "To handle..."
10. Front-weighting: concept before actor — "Critical to this is..."

Engagement and contrast:
11. Rhetorical question: "Why does this matter?", "What distinguishes X?"
12. Comparative/contrastive: "Unlike...", "Rather than...", "More than..."
13. Appositive lead: "A key constraint—X—...", "One factor, often overlooked, ..."

Cohesion:
14. Demonstrative/referential: "This approach...", "Such constraints...", "These..."
15. Coordinating conjunction: "But...", "Yet...", "And..."

CONSTRAINTS:
- Maintain technical precision
- Preserve all meaning
- Do not introduce banned words or AI clichés
- Break the repetitive cadence without creating a new pattern
- Some "The" sentences are necessary; keep those where the article does real semantic work
- Do not overuse any single technique; aim for visible variety within each paragraph

TEXT TO REWRITE:
{text}
```

## Why This Matters for Detection

In white papers, "The" almost always precedes a technical noun (The API, The Database, The Framework, The Agent). When every sentence follows this pattern, the paper reads like a bulleted feature list rendered as prose. Human experts vary their syntax because they are constructing an *argument*, not *describing features*. The sentence structure reflects the logical flow: conditions come first when the condition is what matters, actions come first when the process is the point, purposes come first when motivation needs establishing.
