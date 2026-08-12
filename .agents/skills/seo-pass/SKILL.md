---
name: "seo-pass"
description: "Run an SEO analysis on a published or draft article, identify the search queries it should rank for, and apply concrete edits — subtitle rewrites, n"
---

# seo-pass command

Apply this command workflow. Treat any text after its invocation as the command input.

# Command: SEO Pass

## Goal

Run an SEO analysis on a published or draft article, identify the search queries it should rank for, and apply concrete edits — subtitle rewrites, named-entity insertions, internal links, alt text — that improve Google discoverability without compromising voice.

## Usage

```
/seo-pass [filename]
```

- **No parameter**: list the 10 most recently published articles, ask which one to analyze
- **With filename**: run the SEO pass on the specified article (matches by partial filename, like `publish-article`)

## Why This Exists

The first confirmed Google referral hit was "What Five Coding Agents Taught Me About Building My Own" — a comparative/technical article whose title contains terms recruiters and tooling-curious readers actually search for. Most other articles use intentionally literary titles ("Pull the Lever," "The Squeeze," "Drinking Your Milkshake") that fit the Muriel-Wilkins voice but are invisible to search.

The voice rule is firm: titles stay literary. The SEO work happens in places that don't compromise voice — subtitles, body, headers, links, alt text. This skill targets only those levers.

## Definitions

**Search intent**: the query a reader would type into Google to land on this article. Articles can have multiple intents — informational ("how does X work"), comparative ("X vs Y"), tooling ("best Y for Z"), problem-solving ("why does X fail").

**Searchable term**: a phrase that appears in real search queries. Tool names (Aider, OpenHands, Crush), company names (Oracle, Anthropic), technical concepts ("agent harness," "RAG chatbot," "tool selection"), and paper/framework names are searchable. Literary phrasing ("the squeeze," "drinking your milkshake," "pull the lever") is not.

**Voice-safe edit**: a change that adds searchable terms without violating the writing repository's voice rules — no banned words, no AI-recognizable patterns, no corporate filler.

## Process

### 1. Read the Article and Identify the Topic

- Read the full article including YAML front matter
- Summarize the article's core topic in one sentence ("This article compares the edit, tool selection, and termination strategies of Aider, OpenHands, and Crush")
- Identify the named entities in the article: tools, companies, papers, people, technical concepts
- Note the article's date and whether it's published (in `substack/[YEAR]/`) or a draft (in `substack/[YEAR]/drafts/`)

### 2. Generate Candidate Search Queries

Based on the topic and named entities, list 8-15 search queries someone might type to land on this article. Group by intent:

- **Informational**: "how does X work," "what is X"
- **Comparative**: "X vs Y," "comparing X tools"
- **Tooling**: "best X for Y," "X review"
- **Problem-solving**: "why does X fail," "X error"
- **Recruiter-relevant**: "X expert," "X architect," "X engineer"

Do NOT generate queries that don't match the article's actual content. The point is to surface the article for queries it can credibly answer, not to attract bounces.

### 3. Optional: Validate Queries with Web Search

For 2-3 of the most promising queries, run a web search and check:

- Do real results show up for this query?
- Are the top results similar in scope to this article?
- Is there an obvious gap the article could fill?

Skip this step if the queries are obviously real (tool names, company names, well-known technical terms). Run it for queries that feel speculative.

### 4. Audit the Current SEO State

Check each lever and report present/missing:

| Lever | Check |
|---|---|
| Title | Does it contain searchable terms? (Often no — literary titles are intentional) |
| Subtitle | Does it contain searchable terms? (Substack renders this as the Google meta description) |
| First paragraph | Are the named entities mentioned in the first 100 words? |
| Headers (H2) | Do section headers contain search-relevant terms or are they literary? |
| Named entities | Are tools/companies/papers/people named explicitly, or referred to obliquely? |
| Internal links | Does the article link to other published articles? Does any other article link to it? |
| Image alt text | Does the lead image (and any others) have descriptive alt text? |
| Tags | Are the YAML tags searchable terms? |

### 5. Propose Edits

For each gap, propose a specific, voice-safe edit. Show before/after for each. Order by leverage:

1. **Subtitle rewrite** (highest leverage — Google meta description). Propose 2-3 alternatives that contain searchable terms while preserving the article's framing.
2. **First-paragraph named-entity insertion**. If the article references "the recent layoffs" without naming Oracle, propose adding "Oracle's" inline. Show the exact wording.
3. **Header tweaks** (medium leverage). If a section is titled "The Trust Decision" but is about edit strategies in coding agents, propose "The Edit Strategy Trust Decision" or similar. Don't rewrite headers that already contain search terms.
4. **Internal links** (free, compounds over time). Suggest 1-3 specific places to link to other published articles using descriptive anchor text. Verify the linked articles exist and have URLs.
5. **Image alt text** (small but free). For any image without alt text, propose descriptive alt text that includes the article's main searchable terms.
6. **Tag updates** (small). If the YAML `tags` field is generic, propose 2-3 more specific tags.

### 6. Voice Check

Before applying any edit, run it through the voice rules below. The
writing repository may carry its own `rules/substack-writing.md`
(discovered by walking up from the article); where it does, it wins and
extends this list. Where it does not, these four still apply, and
`filter-tells` measures the first three:

- No banned words (critical, key, deliberate, strategic, leverage-as-verb, etc.)
- No corporate filler (ecosystem, at scale, move the needle, unlock, north star, etc.)
- No AI-recognizable patterns (parallelism, repetitive phrasing, excessive dashes)
- No fake parallel structure or generic listicle vibes

If a proposed edit would violate the voice rules, revise it. If no voice-safe version exists, drop the edit and explain why.

### 7. Apply Edits with Confirmation

Show the user the proposed edits as a punch list. Apply them with confirmation:

```
Proposed edits for [article]:

1. Subtitle (current: "...") → (proposed: "...")
2. First paragraph: insert "Oracle's" before "layoffs announcement"
3. Internal link: in section X, link "cobbler-scaffold" to its dedicated article
4. Alt text on lead image: "Hand-drawn diagram of the agent loop and harness boundary"

Apply all? Apply selected? Skip?
```

Apply only what the user approves. Do not bundle voice-risky edits with safe ones.

### 8. Report

After applying, summarize:

- What changed and why
- What was left alone (and why — voice constraint, no clear win, etc.)
- Which queries the article is now positioned to rank for
- What to monitor: check Substack post-level stats in 2-4 weeks for google.com referrals on this article

## What NOT to Do

- **Do not rewrite the title.** Titles are voice-load-bearing. Petar's literary titles are intentional.
- **Do not rewrite paragraphs to insert keywords.** Insert named entities surgically; do not paraphrase prose for SEO.
- **Do not stuff keywords.** Google penalizes obvious keyword stuffing. Each searchable term should appear in a context where it would naturally fit.
- **Do not propose changes for articles where the topic isn't search-friendly.** Some articles serve regulation, not readership — see [project_substack_growth.md](.memory/project_substack_growth.md) for the goal split. Macro/connection-making articles ("The Strategy That Arrived After the Layoffs," "The Squeeze") may not have search-friendly content. If the audit finds nothing search-relevant, say so and stop.
- **Do not change article URLs.** Substack URLs are permanent after publication. Do not propose edits that depend on changing the slug.
- **Do not violate the voice rules.** When in doubt, drop the edit.

## Reference Files

- `rules/substack-writing.md` — voice rules, banned words, prohibited patterns. Supplied by the writing repository, not by this one; absent, `filter-tells` covers the banned words and the AI patterns.
- `.memory/project_substack_growth.md` — goal stack (readership now leads), search vs. regulation tension, the Five Coding Agents data point

## Success Criteria

A successful SEO pass:

- [ ] Subtitle contains at least 2 searchable terms relevant to the article's topic
- [ ] Named entities appear in the first 100 words
- [ ] At least one internal link to a related published article (when one exists)
- [ ] Lead image has descriptive alt text
- [ ] No voice rules violated
- [ ] User confirmed each applied edit
- [ ] Report identifies target queries and monitoring plan

## Example Workflow

```bash
# Run on a specific article
/seo-pass the-loop-is-the-easy-part

# Output:
# Topic: How the agent loop is small but the harness around it is where the engineering lives.
# Named entities: Aider, OpenHands, Crush, Press, cobbler-scaffold, Russell & Norvig, Sutton's bitter lesson, Rice's theorem
#
# Candidate queries (8):
#   - "coding agent architecture"
#   - "Aider vs OpenHands vs Crush"
#   - "agent harness design"
#   - "tool selection coding agent"
#   - "agent termination strategies"
#   - "edit strategy coding agent"
#   - "building a coding agent"
#   - "fuzzy matching agent edits"
#
# Audit:
#   - Title: literary, no search terms (LEAVE)
#   - Subtitle: "Every coding agent has the same core loop. The hard problems are everything around it." — already strong, has "coding agent" (KEEP, minor enhancement possible)
#   - Named entities: present in body, but Aider/OpenHands/Crush appear in paragraph 5 — could move earlier
#   - Headers: "The Edit Problem," "The Tool Problem," "The Termination Problem" — literary, propose adding "in Coding Agents" suffix to one
#   - Internal links: none yet — should link to "What Five Coding Agents Taught Me" and "What Does $33 Buy You"
#   - Alt text: lead image has none
#
# Proposed edits: [list with before/after]
# Apply?
```

## Notes

- The skill assumes the article is already well-written. SEO work is the last 5% — it doesn't fix a bad article.
- The Google traffic data is one signal among many. Don't optimize all articles for SEO — only the ones whose content is genuinely search-relevant. The rest serve regulation, voice development, or LinkedIn-driven readership.
- After the pass, set a reminder to check Substack post-level stats for `google.com` referrals 2-4 weeks later. If the edits are working, that referrer count should increase.
- The first time this skill runs against the catalog, expect to find similar gaps across many articles (no internal links, missing alt text, generic tags). Subsequent passes should find fewer issues per article.
