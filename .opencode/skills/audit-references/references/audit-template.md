# Citation audit template

One file per audited document, written to
`<db-dir>/audits/<document-stem>-audit.md`. The report should be readable in
five minutes and actionable — every unsupported or misattributed citation
should have enough context for the author to fix it without re-reading the
source.

Use this exact structure. Keep entries concise.

```markdown
---
document: <path to the audited document>
date_audited: <YYYY-MM-DD>
total_citations: <N>
resolved: <N>
unresolved: <N>
verdicts:
  supported: <N>
  unsupported: <N>
  misattributed: <N>
  not_found: <N>
---

# Citation Audit: <document title or filename>

## Summary

<2-3 sentences: what was audited, the overall result, and the most
notable finding. If everything checks out, say so.>

## Unresolved Citations

<List any citation ids that have no entry in references.yaml. If none, write
"All citations resolve to entries in references.yaml.">

| Citation ID | Line | Context |
|-------------|------|---------|
| @missing-id | 42   | "as shown by [@missing-id]..." |

## Citation Verdicts

### @citation-id-1 — <verdict>

**Claim (line N):** "<the sentence from the document containing the citation>"

**Source:** <paper title>, <first author et al.>, <year>

**Evidence:** "<1-2 sentence quote from the source paper supporting or
contradicting the claim>"

**Assessment:** <brief explanation of why this verdict was assigned. For
supported: confirm the match. For unsupported: state what the paper actually
says. For misattributed: explain the discrepancy. For not-found: explain what
was tried.>

<If verdict is unsupported or misattributed:>
**Suggested correction:** <what the author should change — a revised sentence,
a different citation, or a note to verify manually>

### @citation-id-2 — <verdict>

...

<Repeat for each citation. Group by verdict if the document has many citations:
supported first (briefly), then unsupported and misattributed (in detail),
then not-found.>
```

Notes:
- Supported citations need only a brief entry: the claim, the evidence quote,
  and a one-line assessment. Do not pad.
- Unsupported and misattributed citations need full detail: the author must be
  able to fix the problem from the report alone.
- Quote evidence from the source paper, not from the audited document.
- Include page numbers or section references from the source when possible.
