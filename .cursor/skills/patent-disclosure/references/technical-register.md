# Technical register: anthropomorphic and casual vocabulary replacements

The principle: **components perform operations; they do not converse,
gesture, or possess.** Drafts written conversationally personify system
components — they ask, answer, hold, hand off, stand up, honour. A patent
disclosure needs the formal technical verb, and where the protocol
distinguishes roles, the role-precise one: the source log for this
reference replaced "asks" with *queries* for discovery but *requests* for
a service consumer, because the verb encodes the claim-relevant role.

Sweep Sections 5-6 against these tables after drafting and before
self-assessment. Check the term-of-art exception (end of this file)
before each replacement.

## 1. Conversational verbs (component-as-speaker)

| Casual | Technical |
|---|---|
| asks (discovery) | queries |
| asks (service consumer) | requests |
| asked for | requested |
| answers (provider) | returns |
| answers (producer) | serves |
| tells / informs | notifies, signals, transmits to |
| talks to / speaks with | communicates with, exchanges messages with |
| listens for | monitors, receives |
| hears | receives |
| knows | stores, maintains, has access to |
| remembers | persists, retains, caches |
| forgets | discards, evicts, invalidates |
| understands / sees / notices | parses, detects, identifies |
| realizes / figures out | determines, computes |
| decides | selects, determines (keep "decides" only for explicit decision logic) |
| wants / needs | requires |
| expects | requires, is configured to receive |
| trusts | authenticates, accepts as valid |
| promises / agrees | guarantees, commits to (protocol sense) |
| refuses / complains | rejects, returns an error |

## 2. Hand and body metaphors

| Casual | Technical |
|---|---|
| hands to / hands off / hands over | supplies to, transfers to, delegates to |
| grabs / picks up | retrieves, acquires, obtains |
| holds | stores, maintains, retains |
| holds and authors no X | does not generate or store X |
| reaches for / reaches into | accesses, retrieves from |
| touches | accesses, modifies |
| points at / points to | references, addresses |
| drops / throws away | discards |
| juggles | multiplexes, schedules, manages concurrently |
| walks through / steps through | iterates over, traverses |

## 3. Lifecycle casualisms

| Casual | Technical |
|---|---|
| stands up / spins up / fires up / brings up | instantiates, initializes, deploys, starts |
| keeps (running) | maintains |
| tears down / brings down / winds down | releases, terminates, deallocates, shuts down |
| kicks off | initiates, triggers |
| wakes up / goes to sleep | activates, resumes / suspends, idles |
| dies / is killed | fails, terminates, is terminated |

## 4. Motion and location casualisms

| Casual | Technical |
|---|---|
| arrives at | enters, is received by |
| goes out / go straight out | is transmitted, proceeds directly |
| comes back | is returned |
| lands in | is written to, is delivered to |
| lives in / sits in / sits behind | resides in, is stored in, is deployed behind |
| hops / travels | traverses, is forwarded |

## 5. Weak and possessive constructions

| Casual | Technical |
|---|---|
| lets | enables, permits (prefer enables) |
| gets | obtains, retrieves, receives |
| puts | writes, stores, places |
| makes sure | ensures, verifies |
| takes care of / deals with | manages, processes |
| comes up with | generates, derives |
| ends up / turns out | results in, is determined to be |
| authors | generates, produces |
| its product is / its job is | the result is / it is configured to |
| in charge of | manages, is responsible for |
| honoured / respects | enforced, complies with |
| obeys | conforms to, enforces |
| ignores | discards, disregards, does not process |

## 6. Idioms and figurative phrases

Delete these or replace with the named mechanism:

| Idiom | Replacement |
|---|---|
| under the hood / behind the scenes | name the internal mechanism |
| out of the box | by default, without configuration |
| on the fly | at run time, dynamically |
| the heavy lifting | the computation / the processing (name it) |
| plumbing / wiring / glue | the integration layer (name it) |
| moving parts | components |
| sanity check | validation check |
| happy path | nominal case |
| bells and whistles | (delete; enumerate the features or omit) |
| silver bullet / low-hanging fruit | (delete; state the actual claim) |
| day one / out of the gate | at deployment, at initialization |
| a bunch of / a lot of | quantify |

## Term-of-art exception

Metaphorical terms that ARE the standard vocabulary of the domain stay:
handshake, listener, heartbeat, master/worker, kill (POSIX signals),
spin up (where the platform documentation uses it), circuit breaker,
backpressure, hop (networking), sticky (sessions), backoff.

The test: **if the governing standard, RFC, or platform documentation
uses the term, it is the precise term** — replacing it would reduce
precision, not increase it. When in doubt, check the citation the passage
relies on and adopt its vocabulary; this is the same source-terminology
rule the four-axis framework applies to prior art. A replacement that
makes the examiner reach for a dictionary where the standard already
supplied the word is a regression.

## Companion-disclosure independence

(Applied in Section 9 and anywhere related disclosures appear; the rule
lives in section-guide.md.) Never describe a related disclosure as
something this invention "builds on", "borrows from", or "reuses" —
dependency language weakens both patents' independent standing. Accepted
phrasings: "a companion disclosure in the same portfolio", "operates in
the setting of", "applies the same structure". Each disclosure stands
alone.
