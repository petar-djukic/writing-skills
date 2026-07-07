# Paper summary template

One file per paper, written to `<db-dir>/summaries/<stem>.md`, where `<stem>`
is the paper's human-friendly stem (`<Family>-<Year>-<title-slug>-<source>-<id>`).
The goal is a summary you can read in two minutes and trust without re-opening
the PDF — and that tells you, specifically, whether the paper is worth citing
in the current work.

Use this exact structure. Keep it dense; cut filler.

```markdown
---
arxiv_id: <id>
version: <n>
title: <title>
authors: [<author>, <author>, ...]
published: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
primary_category: <e.g. cs.AI>
abs_url: <https://arxiv.org/abs/...>
topics: [llm, agents, fsm, declarative-agents]
tags: [paper, llm-agents, ...]
date_summarized: <YYYY-MM-DD>
---

# <Title>

**Source:** [PDF](../pdfs/<stem>.pdf) · [full text](../papers/<stem>.md) · [source](<url>)

## TL;DR
Two or three sentences. What problem, what they did, what they found.

## Problem
The gap or question the paper addresses. State it as a problem, not a topic.

## Approach
How they tackle it. Name the method, the model(s), the setup. Enough that a
reader knows what was actually done, not just the framing.

## Key results
The findings that matter, with numbers where the paper gives them. Prefer
concrete figures over adjectives.

## Relevance to the current work
The part that justifies the download. Tie it to what is being worked on in
this directory — and, where it applies, to spindle's declarative agent
patterns / state-machine view of agent loops. If a result confirms or
contradicts something in the draft, say so. If it's only tangential, say
that too — an honest "low relevance" is more useful than a stretch.

## Limitations / open questions
What the paper doesn't show, where it's brittle, what you'd want before
relying on it.

## Follow-ups
Cited papers or directions worth chasing next (with arXiv ids if known).
```

Notes:
- `topics` should be drawn from the standing interests (llm, agents, fsm,
  declarative-agents) plus anything specific to the current work.
- `tags` and the `**Source:**` line are populated by `keywords.py tag` — leave
  them to the script; it merges keywords from the paper with `topics`, adds the
  `paper` root tag, and inserts the relative PDF/full-text/source links. Any
  tag you add by hand is preserved.
- Numbers beat adjectives. "61% of total cost" is worth more than "expensive."
- The relevance section is the reason this skill exists. Don't skip it.
