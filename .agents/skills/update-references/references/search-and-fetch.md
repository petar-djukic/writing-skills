# Search and fetch mechanics

The per-backend detail for steps 2 and 3 of the workflow: which source to try
in what order, how deduplication works, and how each fetch path behaves. Kept
out of SKILL.md because it loads on every invocation and is needed only once a
search is actually running.

### 2. Search and dedupe

#### arXiv search

Run the helper. It queries arXiv and cross-references the database, tagging each
candidate `new`, `known` (already have this version), or `outdated` (a newer
version exists than the one on file):

```bash
$RUN <skill>/scripts/arxiv.py --db <db-path> search \
  --query "all:declarative agent state machine LLM" \
  --categories cs.AI cs.CL cs.LG \
  --sort relevance --max 15
```

- Build the `--query` from the work in step 1. arXiv query fields: `all:`,
  `ti:` (title), `abs:` (abstract), `au:` (author). Combine with `AND`/`OR`.
  Run two or three focused queries rather than one broad one — recall on arXiv
  is better from several sharp searches than one vague one.
- `--sort recent` surfaces the newest submissions; `relevance` (default) is
  better for an initial lit sweep.

#### Google Scholar search

For papers not on arXiv (conference proceedings, journals, older work), use
Google Scholar via SerpAPI:

```bash
$RUN <skill>/scripts/scholar.py --db <db-path> search \
  --query "declarative agent patterns finite state machines" \
  --max 10
```

The Scholar script uses the same `references.yaml` database and the same
deduplication logic. It requires a SerpAPI key — use the same key as the
`idea-factory` job-search skill (stored in
`idea-factory/.agents/skills/job-search/SKILL.md`). Set it via
`--api-key <key>` or the `SERPAPI_KEY` environment variable.

#### Semantic Scholar search

Semantic Scholar covers the same off-arXiv territory as Google Scholar
(conference proceedings, journals, older work) but needs no key, and it often
exposes an open-access PDF the skill can download and read directly — so prefer
it when a paper is not on arXiv:

```bash
$RUN <skill>/scripts/semantic_scholar.py --db <db-path> search \
  --query "declarative agent patterns finite state machines" \
  --max 10
```

It uses the same `references.yaml` database and deduplication logic (matching on
`arxiv_id` as well as title, so a paper already fetched from arXiv comes back
`known`). Each result flags whether an open-access PDF is available. The public
Graph API works with no key at a modest, shared rate limit; on a 429 the script
retries with backoff, then advises waiting or setting a key. An optional key
raises the limit — pass `--api-key <key>` or set `SEMANTIC_SCHOLAR_API_KEY`.

#### OpenAlex search and the hierarchical protocol

OpenAlex is the graph backbone: keyless with usable limits (set
`OPENALEX_MAILTO` or `--mailto` for the polite pool, ~10 req/s), 250M+ works
including IEEE, citation graph in-record, institutions as first-class
entities, and `fwci` (field-weighted citation impact, 1.0 = field average).

```bash
$RUN <skill>/scripts/openalex.py --db <db-path> search --query "..." --max 10
```

Keyword search is level 0. When the goal is coverage of a field rather than a
spot lookup, go hierarchical (snowball sampling):

1. **Hubs** — aggregate a broad seed into ranked key authors, pivotal papers,
   and surveys:
   ```bash
   $RUN <skill>/scripts/openalex.py --db <db-path> hubs --query "..." --max 40
   ```
   Pick by judgment: 2-3 key authors, 1-2 surveys, 1-2 pivotal papers. A
   survey is worth twenty keyword queries — its reference list is a curated
   bibliography.
2. **Drill one level** with per-level budget (<=10 fetches per level):
   ```bash
   $RUN <skill>/scripts/openalex.py --db <db-path> references --id W...      # what a survey/pivotal paper builds on
   $RUN <skill>/scripts/openalex.py --db <db-path> citations --id W...       # who builds on it since (catches recent work keywords miss)
   $RUN <skill>/scripts/openalex.py --db <db-path> author-papers --author-id A...
   ```
   Candidates come back ranked (cited_by, fwci) and dedupe-tagged.
3. **Rank and select** — prefer high fwci/cited_by; boost respected
   institutions (OpenAlex resolves them; treat as a boost, not a filter) and
   strong venues.
4. **Stop at saturation** — when a drill level returns mostly `known`, the
   corpus has converged; stop.
5. **Fetch with provenance** so the discovery path is preserved:
   ```bash
   $RUN <skill>/scripts/openalex.py --db <db-path> fetch --id W... \
     --discovered survey-references --via "Wang et al. 2024 survey"
   ```
   OA PDFs download directly; paywalled works (IEEE etc.) land
   `metadata-only` and flow into the pending/ingest manual loop.

Semantic Scholar remains an optional enricher (its keyless pool throttles
hard): when reachable, its `influentialCitationCount` sharpens the pivotal-
paper ranking; nothing in the protocol depends on it.

#### Picking candidates

Read the returned abstracts and pick the genuinely relevant papers. Don't
download everything that matches keywords — relevance to the current work is
the bar. Skip `known` papers. Re-fetch `outdated` ones (a new version may
change the conclusions).

### 3. Fetch the PDF

For each paper worth reading:

```bash
$RUN <skill>/scripts/arxiv.py --db <db-path> fetch --id 2310.12345
```

This downloads the latest-version PDF and writes a database entry with
`status: downloaded`. On a version bump it preserves any existing summary
metadata so you know it needs a re-read.

For Scholar results that have a direct PDF link, the scholar script can also
fetch:

```bash
$RUN <skill>/scripts/scholar.py --db <db-path> fetch \
  --title "Exact Paper Title" --url "https://example.com/paper.pdf"
```

For a Semantic Scholar result, fetch by its `paper_id` (from the search
output); the script downloads the open-access PDF when there is one and records
`downloaded`, otherwise records `metadata-only` with the landing URL:

```bash
$RUN <skill>/scripts/semantic_scholar.py --db <db-path> fetch --paper-id <s2id>
```

#### Papers that can't be downloaded

Some papers are paywalled or behind a login (IEEE Xplore, ACM, journals) and
land in the database as `status: metadata-only` — recorded, but not readable.
Collect them into a checklist you can hand to the user:

```bash
$RUN <skill>/scripts/scholar.py --db <db-path> pending
```

This writes `<db-dir>/downloads-needed.md`, one clickable landing URL per
paper. The user downloads the PDFs and hands each back; attach it to its entry
with `ingest`, which converts the PDF and flips the status to `downloaded`:

```bash
$RUN <skill>/scripts/scholar.py --db <db-path> ingest \
  --id <citation-id> --file ~/Downloads/paper.pdf
```

If the PDF has no matching entry yet, pass metadata and `ingest` registers a
new paper (converting and naming it): `ingest --file <pdf> --title "…"
--authors "Given Family" --year YYYY`. After `ingest`, the paper reads and
summarizes like any other. Prefer Semantic Scholar's open-access PDFs first —
they avoid this round-trip entirely.
