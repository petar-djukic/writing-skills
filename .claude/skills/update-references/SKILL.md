---
name: update-references
description: >-
  Find, download, read, and summarize research papers related to the work in the
  current directory. Searches arXiv and Google Scholar. Maintains a CSL-YAML
  reference database (references.yaml) compatible with pandoc's --bibliography
  flag, so the same file serves both the skill and document builds. Triggers:
  update references, refresh the bibliography, find papers, related work,
  literature review, what's been published on, recent papers, cite sources for,
  background reading, summarize this paper, search scholar.
---

# Update references (research paper search)

This skill turns "find me what's been written about this" into a small,
repeatable pipeline: read what the user is working on, search arXiv (and
optionally Google Scholar) for related papers, download the relevant ones, read
them, write a summary per paper, and keep a CSL-YAML database so work is never
repeated and versions stay current.

The standing interests are LLMs, AI agents, finite state machines, and
declarative agent patterns — the territory of spindle
(github.com/petar-djukic/spindle), a Go state-machine engine for agentic loops.
Lean toward those topics, but always sharpen the search using whatever the
current working directory is actually about.

## Where things live

This skill is context-aware. It runs from the directory the user is working in,
and it stores its outputs there — not in a fixed global location. Resolve paths
like this:

- **Database:** `references.yaml` under the current working directory, unless
  an existing one is already nearby (look for a `references.yaml` at or above
  the CWD and reuse it). Pass the chosen path as `--db` to every script call so
  search, fetch, and record all agree. If only a legacy `arxiv/papers.yaml`
  exists, the scripts read it transparently and convert on next write.
- **PDFs:** `<db-dir>/pdfs/` (transient — they exist to be read; they don't need
  to be committed). The script resolves this **relative to the database**, not
  the current directory, so PDFs land next to the db even when run from
  elsewhere.
- **Papers (markdown):** `<db-dir>/papers/<arxiv-id>vN.md` — `fetch` converts
  each PDF to markdown automatically (best-effort via `pymupdf4llm`), preserving
  headings, tables, and math. Papers are readable in any editor or tool.
- **Summaries:** `<db-dir>/summaries/<arxiv-id>-<short-slug>.md`, one file per
  paper.

If the user names a directory or an existing database, use that instead. Because
every output path is derived from `--db`, passing an absolute `--db` keeps all
artifacts together regardless of the working directory.

## The database format

The database is CSL-YAML — a bare YAML list with no root key. Each entry has
standard CSL fields that pandoc understands (`id`, `type`, `title`, `author`,
`container-title`, `URL`, `issued`) plus skill-internal fields (`status`,
`version`, `pdf_path`, `arxiv_id`, etc.) that pandoc ignores. This means the
file is directly usable as `pandoc --bibliography references.yaml` with no
conversion step.

An entry looks like:

```yaml
- id: lee-meta-harness-2026
  type: article
  title: "Meta-Harness: End-to-End Optimization of Model Harnesses"
  author:
    - family: Lee
      given: Yoonho
  container-title: arXiv preprint arXiv:2603.28052
  URL: https://arxiv.org/abs/2603.28052
  issued:
    year: 2026
  arxiv_id: "2603.28052"
  version: 1
  status: downloaded
  pdf_path: pdfs/2603.28052v1.pdf
  md_path: papers/2603.28052v1.md
```

The `id` field is a pandoc citation key (used as `@lee-meta-harness-2026` in
markdown). The script generates it from the first author's family name and the
publication year. The `arxiv_id` field is the base arXiv identifier used for
deduplication and version tracking.

## The workflow

### 1. Understand the current work first

Before searching, read what's in the working directory — a draft paper, notes,
an outline, existing summaries. The search is only as good as its query, and the
query should come from the actual problem the user is working on, not just the
standing topic list. If the directory is empty or the intent is unclear, ask the
user what angle they care about (one question, then proceed).

### 2. Search and dedupe

#### arXiv search

Run the helper. It queries arXiv and cross-references the database, tagging each
candidate `new`, `known` (already have this version), or `outdated` (a newer
version exists than the one on file):

```bash
python3 <skill>/scripts/arxiv.py --db <db-path> search \
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
python3 <skill>/scripts/scholar.py --db <db-path> search \
  --query "declarative agent patterns finite state machines" \
  --max 10
```

The Scholar script uses the same `references.yaml` database and the same
deduplication logic. It requires a SerpAPI key — use the same key as the
`idea-factory` job-search skill (stored in
`idea-factory/.claude/skills/job-search/SKILL.md`). Set it via
`--api-key <key>` or the `SERPAPI_KEY` environment variable.

#### Picking candidates

Read the returned abstracts and pick the genuinely relevant papers. Don't
download everything that matches keywords — relevance to the current work is
the bar. Skip `known` papers. Re-fetch `outdated` ones (a new version may
change the conclusions).

### 3. Fetch the PDF

For each paper worth reading:

```bash
python3 <skill>/scripts/arxiv.py --db <db-path> fetch --id 2310.12345
```

This downloads the latest-version PDF and writes a database entry with
`status: downloaded`. On a version bump it preserves any existing summary
metadata so you know it needs a re-read.

For Scholar results that have a direct PDF link, the scholar script can also
fetch:

```bash
python3 <skill>/scripts/scholar.py --db <db-path> fetch \
  --title "Exact Paper Title" --url "https://example.com/paper.pdf"
```

### 4. Read and summarize

Read the markdown conversion that `fetch` produced — its path is in the
`md_path` field of the fetch output and the db entry
(`<db-dir>/papers/<arxiv-id>vN.md`). If the markdown file is missing (e.g. an
older fetch before markdown conversion was available), run `repair` first to
regenerate it. Then write a summary file following
`references/summary-template.md` exactly. The summary's job is to let the user
decide, in two minutes, whether to cite the paper — so the "Relevance to the
current work" section carries the weight. Tie findings back to the current draft
and, where it fits, to spindle's state-machine / declarative-agent view. Prefer
the paper's own numbers over adjectives. An honest "low relevance" beats a
stretch.

Name the file `<db-dir>/summaries/<id>-<short-slug>.md`.

### 5. Record it

Close the loop so the database reflects reality:

```bash
python3 <skill>/scripts/arxiv.py --db <db-path> record --id 2310.12345 \
  --summary-file summaries/2310.12345-short-slug.md \
  --topics llm agents fsm declarative-agents \
  --relevance "One line on why it matters to this work."
```

This flips the entry to `status: summarized`. The database is now the
single source of truth: re-running a search later will mark these papers
`known` and skip them.

### 6. Report back

Summarize what was found: how many candidates, how many were new vs. already
known, which were summarized, and a one-line takeaway per paper with a link to
its summary file. Point out the two or three most relevant to the current work.

### Repair

If papers were fetched before markdown conversion was available, or if markdown
files are missing for any reason, run `repair` to regenerate them from the PDFs:

```bash
python3 <skill>/scripts/arxiv.py --db <db-path> repair
```

This walks every entry in the database, checks for a missing `md_path`, and
re-converts the PDF if it exists on disk. It also migrates legacy `text_path`
entries by adding the `md_path` field. Prints a JSON summary of what it did.

## Dependencies

PyYAML (`python3 -m pip install --user pyyaml`) is required. `pymupdf4llm` is
recommended for PDF-to-markdown conversion that preserves headings, tables, and
math; `pypdf` is the fallback (plain text only). If neither is installed,
fetch still downloads the PDF and just skips the conversion. Everything else is
Python stdlib plus the arXiv public API — no key needed. Be a good citizen: the
script already retries with backoff; don't hammer the API with huge `--max`
values in a tight loop.

Google Scholar search requires a SerpAPI key (same key as the idea-factory
job-search skill).
