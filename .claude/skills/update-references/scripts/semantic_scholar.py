#!/usr/bin/env python3
"""Semantic Scholar search helper for the update-references skill.

Searches the Semantic Scholar Graph API and maintains the same CSL-YAML
reference database as arxiv.py and scholar.py. Use this for papers not on
arXiv: conference proceedings, journal articles, older work. Unlike scholar.py
(which needs a SerpAPI key), the Semantic Scholar Graph API works with no key
at a modest rate limit, and it often exposes an open-access PDF link the skill
can download and read directly — reducing the pile of papers that end up
metadata-only.

Subcommands:
  search   Query Semantic Scholar and cross-reference against the YAML db.
           Prints a JSON list of candidates tagged new / known, each flagging
           whether an open-access PDF is available.
  fetch    Download a paper's open-access PDF (if available) and create/update
           its db entry. Papers without an open-access PDF are recorded with
           status: metadata-only and their landing URL, so scholar.py pending
           lists them for manual download.
  list     Print the current db as JSON.

An API key is optional. Pass via --api-key or set SEMANTIC_SCHOLAR_API_KEY to
raise the rate limit; it is sent as the x-api-key header.

Stdlib only except PyYAML.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import _naming

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Install with: python3 -m pip install --user pyyaml")

API_BASE = "https://api.semanticscholar.org/graph/v1"
USER_AGENT = "update-references-skill/1.0"
FIELDS = "title,authors,year,venue,abstract,openAccessPdf,externalIds,citationCount,url"


def load_db(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "papers" in data:
        return data["papers"]
    return []


def save_db(path, entries):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(entries, f, sort_keys=False, allow_unicode=True, width=100)


def index_by_title(entries):
    return {normalize_title(e.get("title", "")): e for e in entries if e.get("title")}


def index_by_arxiv(entries):
    return {e["arxiv_id"]: e for e in entries if e.get("arxiv_id")}


def normalize_title(title):
    return re.sub(r"\s+", " ", title.lower().strip())


def _convert_pdf(pdf_path):
    """Best-effort PDF -> markdown. Tries pymupdf4llm, falls back to pypdf."""
    try:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(pdf_path)
    except ImportError:
        pass
    except Exception:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        return "\n".join(parts)
    except Exception:
        return None


def parse_author_name(name):
    name = name.strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        return {"family": parts[0], "given": parts[1] if len(parts) > 1 else ""}
    parts = name.rsplit(None, 1)
    if len(parts) == 2:
        return {"family": parts[1], "given": parts[0]}
    return {"family": name, "given": ""}


def _first_family(authors):
    """First author's family name from a list of names or CSL author dicts."""
    if not authors:
        return ""
    first = authors[0]
    if isinstance(first, dict):
        return first.get("family", "")
    return parse_author_name(first).get("family", "")


def _api_get(path, params, api_key, retries=4):
    """GET a Graph API endpoint with backoff on rate limiting."""
    url = f"{API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["x-api-key"] = api_key
    delay = 2.0
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            # 429 (rate limit) and 5xx are worth retrying; others are fatal.
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            if e.code == 429:
                sys.exit(
                    "Semantic Scholar rate limit (HTTP 429) after retries. The "
                    "keyless pool is shared and throttles hard — wait a minute "
                    "and retry, or set SEMANTIC_SCHOLAR_API_KEY / --api-key for a "
                    "higher limit (request one at "
                    "https://www.semanticscholar.org/product/api)."
                )
            sys.exit(f"Semantic Scholar API error (HTTP {e.code}): {e.reason}")
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            sys.exit(f"Semantic Scholar request failed: {e.reason}")
    return {}


def _record_from_item(item):
    """Normalize a Graph API paper object into the fields the db needs."""
    authors = [parse_author_name(a.get("name", "")) for a in item.get("authors", [])]
    ext = item.get("externalIds") or {}
    oa = item.get("openAccessPdf") or {}
    return {
        "paper_id": item.get("paperId", ""),
        "title": item.get("title", ""),
        "authors": authors,
        "year": item.get("year"),
        "venue": item.get("venue", ""),
        "abstract": item.get("abstract", "") or "",
        "url": item.get("url", ""),
        "open_access_pdf": oa.get("url"),
        "arxiv_id": ext.get("ArXiv"),
        "doi": ext.get("DOI"),
        "cited_by": item.get("citationCount", 0),
    }


def semantic_search(query, api_key, max_results=10, year=None):
    params = {"query": query, "limit": min(max_results, 100), "fields": FIELDS}
    if year:
        params["year"] = year
    data = _api_get("paper/search", params, api_key)
    return [_record_from_item(it) for it in data.get("data", [])[:max_results]]


def _lookup(paper_id, api_key):
    data = _api_get(f"paper/{urllib.parse.quote(paper_id, safe='')}",
                    {"fields": FIELDS}, api_key)
    return _record_from_item(data) if data else None


def _dedupe_status(rec, by_title, by_arxiv):
    """Return the existing db entry for this record, or None."""
    if rec.get("arxiv_id") and rec["arxiv_id"] in by_arxiv:
        return by_arxiv[rec["arxiv_id"]]
    return by_title.get(normalize_title(rec.get("title", "")))


def cmd_search(args):
    api_key = args.api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    results = semantic_search(args.query, api_key, args.max, args.year)
    entries = load_db(args.db)
    by_title = index_by_title(entries)
    by_arxiv = index_by_arxiv(entries)
    out = []
    for r in results:
        prev = _dedupe_status(r, by_title, by_arxiv)
        out.append({
            "paper_id": r["paper_id"],
            "title": r["title"],
            "authors": r["authors"],
            "year": r["year"],
            "venue": r["venue"],
            "status": "known" if prev else "new",
            "db_status": prev.get("status") if prev else None,
            "snippet": r["abstract"][:300],
            "url": r["url"],
            "open_access_pdf": r["open_access_pdf"],
            "arxiv_id": r["arxiv_id"],
            "cited_by": r["cited_by"],
        })
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_fetch(args):
    api_key = args.api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if not args.paper_id and not args.title:
        sys.exit("--paper-id or --title is required")

    if args.paper_id:
        rec = _lookup(args.paper_id, api_key)
        if not rec:
            sys.exit(f"paper not found: {args.paper_id}")
    else:
        found = semantic_search(args.title, api_key, 5)
        norm = normalize_title(args.title)
        rec = next((r for r in found if normalize_title(r["title"]) == norm), None)
        if not rec:
            sys.exit(f"no exact-title match for: {args.title}")

    db_dir = os.path.dirname(os.path.abspath(args.db))
    entries = load_db(args.db)
    by_title = index_by_title(entries)
    by_arxiv = index_by_arxiv(entries)
    existing = _dedupe_status(rec, by_title, by_arxiv)
    citation_id = (existing["id"] if existing
                   else _naming.citation_key(_first_family(rec["authors"]), rec["year"],
                                             {p["id"] for p in entries if p.get("id")}))
    stem = _naming.paper_stem(_first_family(rec["authors"]), rec["year"], rec["title"],
                              arxiv_id=rec.get("arxiv_id"), doi=rec.get("doi"),
                              citation_id=citation_id)

    pdf_path = None
    md_path = None

    if rec.get("open_access_pdf"):
        pdf_dir = os.path.join(db_dir, "pdfs")
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{stem}.pdf")
        req = urllib.request.Request(rec["open_access_pdf"],
                                     headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(pdf_path, "wb") as f:
                f.write(r.read())
        except Exception as e:
            print(f"Warning: could not download PDF: {e}", file=sys.stderr)
            pdf_path = None

        if pdf_path:
            md_content = _convert_pdf(pdf_path)
            if md_content and md_content.strip():
                papers_dir = os.path.join(db_dir, "papers")
                os.makedirs(papers_dir, exist_ok=True)
                md_path = os.path.join(papers_dir, f"{stem}.md")
                with open(md_path, "w") as mf:
                    mf.write(md_content)

    record = {
        "id": citation_id,
        "type": "article",
        "title": rec["title"],
        "author": rec["authors"],
        "container-title": rec["venue"] or "",
        "URL": rec["url"] or "",
        "issued": {"year": rec["year"]} if rec["year"] else {},
        "source": "semantic-scholar",
        "status": "downloaded" if pdf_path else "metadata-only",
        "added": str(date.today()),
    }
    if rec.get("arxiv_id"):
        record["arxiv_id"] = rec["arxiv_id"]
    if rec.get("doi"):
        record["doi"] = rec["doi"]
    if pdf_path:
        record["pdf_path"] = os.path.relpath(pdf_path, db_dir)
    if md_path:
        record["md_path"] = os.path.relpath(md_path, db_dir)

    if existing:
        for keep in ("summary_file", "topics", "relevance", "added", "arxiv_id"):
            if keep in existing:
                record.setdefault(keep, existing[keep])
        record["added"] = existing.get("added", record["added"])
        eid = existing.get("id")
        entries = [record if p.get("id") == eid else p for p in entries]
    else:
        entries.append(record)
    save_db(args.db, entries)
    print(json.dumps({"pdf_path": pdf_path, "md_path": md_path, "meta": record},
                     indent=2, ensure_ascii=False))


def cmd_list(args):
    print(json.dumps(load_db(args.db), indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Semantic Scholar research helper")
    p.add_argument("--db", default="references.yaml",
                   help="path to the CSL-YAML reference database (default: references.yaml)")
    p.add_argument("--api-key", default=None,
                   help="Semantic Scholar API key (or set SEMANTIC_SCHOLAR_API_KEY); optional")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="search Semantic Scholar and dedupe against db")
    s.add_argument("--query", required=True, help="search query")
    s.add_argument("--max", type=int, default=10)
    s.add_argument("--year", help="publication year filter, e.g. 2020 or 2018-2024")
    s.set_defaults(func=cmd_search)

    f = sub.add_parser("fetch",
                       help="add a paper to the db, downloading its open-access PDF if any")
    f.add_argument("--paper-id", help="Semantic Scholar paperId (or DOI:/ARXIV: prefixed id)")
    f.add_argument("--title", help="paper title (exact match) if no paper-id")
    f.set_defaults(func=cmd_fetch)

    l = sub.add_parser("list", help="print the db as JSON")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
