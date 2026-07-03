---
name: update-references
description: >-
  Find, download, read, and summarize arXiv papers related to the work in the
  current directory, with a focus on LLMs, AI agents, finite state machines,
  and declarative agent patterns (as in the spindle state-machine engine).
  Maintains a YAML reference database so the same paper is never downloaded
  twice and newer versions are picked up automatically. Use this whenever the
  user wants to update references, research the literature, find related/recent
  papers, do a lit review, build a bibliography, catch up on a topic, or check
  what's new on arXiv — even if they don't say "arXiv" explicitly. Triggers:
  update references, refresh the bibliography, find papers, related work,
  literature review, what's been published on, recent papers, cite sources for,
  background reading, summarize this paper.
---

# Update references (arXiv research)

This skill turns "find me what's been written about this" into a small,
repeatable pipeline: read what the user is working on, search arXiv for related
papers, download the relevant ones, read them, write a summary per paper, and
keep a YAML database so work is never repeated and versions stay current.

The standing interests are LLMs, AI agents, finite state machines, and
declarative agent patterns — the territory of spindle
(github.com/petar-djukic/spindle), a Go state-machine engine for agentic loops.
Lean toward those topics, but always sharpen the search using whatever the
current working directory is actually about.

## Where things live

This skill is context-aware. It runs from the directory the user is working in,
and it stores its outputs there — not in a fixed global location. Resolve paths
like this:

- **Database:** `arxiv/papers.yaml` under the current working directory, unless
  an existing one is already nearby (look for a `papers.yaml`, `references.yaml`,
  or an `arxiv/` directory at or above the CWD and reuse it). Pass the chosen
  path as `--db` to every script call so search, fetch, and record all agree.
- **PDFs:** `<db-dir>/pdfs/` (transient — they exist to be read; they don't need
  to be committed). The script resolves this **relative to the database**, not
  the current directory, so PDFs land next to the db even when run from
  elsewhere.
- **Text:** `<db-dir>/text/<arxiv-id>vN.txt` — `fetch` writes a plain-text
  sidecar of each PDF automatically (best-effort), so papers are readable even
  where the Read tool can't render PDFs.
- **Summaries:** `<db-dir>/summaries/<arxiv-id>-<short-slug>.md`, one file per
  paper.

If the user names a directory or an existing database, use that instead. Because
every output path is derived from `--db`, passing an absolute `--db` keeps all
artifacts together regardless of the working directory.

## The workflow

### 1. Understand the current work first

Before searching, read what's in the working directory — a draft paper, notes,
an outline, existing summaries. The search is only as good as its query, and the
query should come from the actual problem the user is working on, not just the
standing topic list. If the directory is empty or the intent is unclear, ask the
user what angle they care about (one question, then proceed).

### 2. Search and dedupe

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
- Read the returned abstracts and pick the genuinely relevant papers. Don't
  download everything that matches keywords — relevance to the current work is
  the bar. Skip `known` papers. Re-fetch `outdated` ones (a new version may
  change the conclusions).

### 3. Fetch the PDF

For each paper worth reading:

```bash
python3 <skill>/scripts/arxiv.py --db <db-path> fetch --id 2310.12345
```

This downloads the latest-version PDF to `arxiv/pdfs/` and writes a database
entry with `status: downloaded`. On a version bump it preserves any existing
summary metadata so you know it needs a re-read.

### 4. Read and summarize

Read the PDF with the Read tool. If the Read tool cannot render PDFs in this
environment (it needs poppler/`pdftoppm`), read the plain-text sidecar `fetch`
wrote instead — its path is in the `text_path` field of the fetch output and the
db entry (`<db-dir>/text/<arxiv-id>vN.txt`). Then write a summary file following
`references/summary-template.md` exactly. The summary's job is to let the user
decide, in two minutes, whether to cite the paper — so the "Relevance to the
current work" section carries the weight. Tie findings back to the current draft
and, where it fits, to spindle's state-machine / declarative-agent view. Prefer
the paper's own numbers over adjectives. An honest "low relevance" beats a
stretch.

Name the file `arxiv/summaries/<arxiv-id>-<short-slug>.md`.

### 5. Record it

Close the loop so the database reflects reality:

```bash
python3 <skill>/scripts/arxiv.py --db <db-path> record --id 2310.12345 \
  --summary-file arxiv/summaries/2310.12345-short-slug.md \
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

## The database

`papers.yaml` is a list under `papers:`. Each entry is keyed by its base arXiv
id (version-independent), which is how dedup and version tracking work — the id
is the identity, the version is a property of it. The script owns this file;
read it freely, but prefer editing it through `fetch`/`record` so the schema
stays consistent. `list` prints it as JSON for a quick overview:

```bash
python3 <skill>/scripts/arxiv.py --db <db-path> list
```

## Dependencies

PyYAML (`python3 -m pip install --user pyyaml`) is required. `pypdf` (or
`pdfminer.six`) is optional but recommended — `fetch` uses it to write the
text sidecar so papers are readable without poppler; if neither is installed,
fetch still downloads the PDF and just skips the sidecar. Everything else is
Python stdlib plus the arXiv public API — no key needed. Be a good citizen: the script
already retries with backoff; don't hammer the API with huge `--max` values in
a tight loop.
