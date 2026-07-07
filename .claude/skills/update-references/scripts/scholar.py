#!/usr/bin/env python3
"""Google Scholar search helper for the update-references skill.

Searches Google Scholar via SerpAPI and maintains the same CSL-YAML reference
database as arxiv.py. Use this for papers not available on arXiv: conference
proceedings, journal articles, older publications.

Subcommands:
  search   Query Google Scholar and cross-reference against the YAML db.
           Prints a JSON list of candidates tagged new / known.
  fetch    Download a paper's PDF (if a direct link is available) and
           create/update its db entry. For papers without a direct PDF link,
           the entry is created with status: metadata-only.
  pending  Write <db-dir>/downloads-needed.md — a checklist of every
           metadata-only paper (any source) with its landing URL, for manual
           download.
  ingest   Attach a manually-downloaded PDF to an existing entry, convert it,
           and flip its status to downloaded. The inverse of fetch.
  list     Print the current db as JSON.

search and fetch require a SerpAPI key (--api-key or SERPAPI_KEY; the same key
as the idea-factory job-search skill). pending and ingest are local db
operations and need no key.

Stdlib only except PyYAML.
"""

import argparse
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import date

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Install with: python3 -m pip install --user pyyaml")

SERPAPI_URL = "https://serpapi.com/search.json"
USER_AGENT = "update-references-skill/1.0"


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


def make_citation_id(title, authors, year):
    family = ""
    if authors:
        first = authors[0]
        if isinstance(first, dict):
            family = first.get("family", "")
        else:
            family = parse_author_name(first).get("family", "")
    family = re.sub(r"[^\w]", "-", family.lower()).strip("-")
    title_words = title.split()
    slug = "-".join(w.lower() for w in title_words[:3] if w.isalpha())[:20]
    yr = str(year) if year else "nd"
    return f"{family}-{slug}-{yr}" if slug else f"{family}-{yr}"


def scholar_search(query, api_key, max_results=10):
    params = {
        "engine": "google_scholar",
        "q": query,
        "num": min(max_results, 20),
        "api_key": api_key,
    }
    url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    results = []
    for item in data.get("organic_results", [])[:max_results]:
        authors_raw = []
        pub_info = item.get("publication_info", {})
        if "authors" in pub_info:
            authors_raw = [a.get("name", "") for a in pub_info["authors"]]
        elif "summary" in pub_info:
            parts = pub_info["summary"].split(" - ")
            if parts:
                authors_raw = [a.strip() for a in parts[0].split(",")]

        year = None
        summary = pub_info.get("summary", "")
        year_match = re.search(r"\b(19|20)\d{2}\b", summary)
        if year_match:
            year = int(year_match.group())

        pdf_link = None
        for resource in item.get("resources", []):
            link = resource.get("link", "")
            if link.endswith(".pdf") or "pdf" in link.lower():
                pdf_link = link
                break

        results.append({
            "title": item.get("title", ""),
            "authors": authors_raw,
            "year": year,
            "snippet": item.get("snippet", ""),
            "url": item.get("link", ""),
            "pdf_url": pdf_link,
            "cited_by": item.get("inline_links", {}).get("cited_by", {}).get("total", 0),
            "position": item.get("position"),
        })
    return results


def cmd_search(args):
    api_key = args.api_key or os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit("SerpAPI key required. Pass --api-key or set SERPAPI_KEY.")
    results = scholar_search(args.query, api_key, args.max)
    known = index_by_title(load_db(args.db))
    out = []
    for r in results:
        norm = normalize_title(r["title"])
        prev = known.get(norm)
        out.append({
            "title": r["title"],
            "authors": r["authors"],
            "year": r["year"],
            "status": "known" if prev else "new",
            "db_status": prev.get("status") if prev else None,
            "snippet": r["snippet"],
            "url": r["url"],
            "pdf_url": r["pdf_url"],
            "cited_by": r["cited_by"],
        })
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_fetch(args):
    api_key = args.api_key or os.environ.get("SERPAPI_KEY")
    if not args.title:
        sys.exit("--title is required")

    csl_authors = [parse_author_name(a) for a in (args.authors or [])]
    year = args.year
    citation_id = make_citation_id(args.title, csl_authors, year)

    db_dir = os.path.dirname(os.path.abspath(args.db))
    pdf_path = None
    md_path = None

    if args.url and (args.url.endswith(".pdf") or "pdf" in args.url.lower()):
        pdf_dir = os.path.join(db_dir, "pdfs")
        os.makedirs(pdf_dir, exist_ok=True)
        safe = re.sub(r"[^\w.-]", "-", citation_id)
        pdf_path = os.path.join(pdf_dir, f"{safe}.pdf")
        req = urllib.request.Request(args.url, headers={"User-Agent": USER_AGENT})
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
                md_path = os.path.join(papers_dir, f"{safe}.md")
                with open(md_path, "w") as mf:
                    mf.write(md_content)

    entries = load_db(args.db)
    known = index_by_title(entries)
    existing = known.get(normalize_title(args.title))

    container = args.venue or ""

    record = {
        "id": existing["id"] if existing else citation_id,
        "type": "article",
        "title": args.title,
        "author": csl_authors if csl_authors else [],
        "container-title": container,
        "URL": args.page_url or args.url or "",
        "issued": {"year": year} if year else {},
        "source": "scholar",
        "status": "downloaded" if pdf_path else "metadata-only",
        "added": str(date.today()),
    }
    if pdf_path:
        record["pdf_path"] = os.path.relpath(pdf_path, db_dir)
    if md_path:
        record["md_path"] = os.path.relpath(md_path, db_dir)

    if existing:
        for keep in ("summary_file", "topics", "relevance", "added", "arxiv_id"):
            if keep in existing:
                record.setdefault(keep, existing[keep])
        record["added"] = existing.get("added", record["added"])
        norm = normalize_title(args.title)
        entries = [record if normalize_title(p.get("title", "")) == norm else p
                   for p in entries]
    else:
        entries.append(record)
    save_db(args.db, entries)
    print(json.dumps({"pdf_path": pdf_path, "md_path": md_path, "meta": record},
                     indent=2, ensure_ascii=False))


def _format_authors(authors):
    """Render a CSL author list as 'Given Family, Given Family' for display."""
    names = []
    for a in authors or []:
        if isinstance(a, dict):
            given = a.get("given", "").strip()
            family = a.get("family", "").strip()
            names.append(f"{given} {family}".strip())
        elif a:
            names.append(str(a))
    return ", ".join(n for n in names if n)


def cmd_pending(args):
    """Write a manual-download checklist of every metadata-only paper.

    Scans the whole database (all sources, not just Scholar) for entries that
    could not be downloaded, and writes <db-dir>/downloads-needed.md with a
    clickable landing URL for each so the user can fetch the PDFs by hand and
    hand them back via `ingest`. Also prints the same set as JSON.
    """
    db_dir = os.path.dirname(os.path.abspath(args.db))
    entries = load_db(args.db)
    pending = [e for e in entries if e.get("status") == "metadata-only"]
    out_path = os.path.join(db_dir, "downloads-needed.md")

    lines = ["# Papers to download manually", ""]
    if pending:
        lines.append(
            "These papers could not be downloaded automatically (paywalled or on "
            "a platform without an open link). Download each PDF, then hand it "
            "back with:")
        lines.append("")
        lines.append("```")
        lines.append("scholar.py ingest --db <db> --id <id> --file <path-to.pdf>")
        lines.append("```")
        lines.append("")
        for e in pending:
            title = e.get("title", "(untitled)")
            url = e.get("URL", "")
            authors = _format_authors(e.get("author"))
            year = (e.get("issued") or {}).get("year")
            venue = e.get("container-title", "")
            meta = " · ".join(str(x) for x in (authors, venue, year) if x)
            link = f"[{title}]({url})" if url else title
            lines.append(f"- [ ] `{e.get('id', '')}` — {link}")
            if meta:
                lines.append(f"  {meta}")
    else:
        lines.append("Nothing pending — every paper in the database has been "
                     "downloaded or summarized.")
    lines.append("")

    os.makedirs(db_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    report = [{
        "id": e.get("id"),
        "title": e.get("title"),
        "url": e.get("URL"),
        "container-title": e.get("container-title"),
        "year": (e.get("issued") or {}).get("year"),
    } for e in pending]
    print(json.dumps({"count": len(pending),
                      "list_file": os.path.relpath(out_path, db_dir),
                      "pending": report}, indent=2, ensure_ascii=False))


def cmd_ingest(args):
    """Attach a manually-downloaded PDF to an existing metadata-only entry.

    The inverse of `fetch`: takes a local file the user already downloaded,
    copies it into <db-dir>/pdfs/, converts it to markdown, and flips the
    entry's status to `downloaded`.
    """
    if not args.id and not args.title:
        sys.exit("--id or --title is required")
    if not os.path.exists(args.file):
        sys.exit(f"file not found: {args.file}")

    db_dir = os.path.dirname(os.path.abspath(args.db))
    entries = load_db(args.db)

    idx = None
    for i, e in enumerate(entries):
        if args.id and e.get("id") == args.id:
            idx = i
            break
        if args.title and normalize_title(e.get("title", "")) == normalize_title(args.title):
            idx = i
            break
    if idx is None:
        sys.exit(f"no db entry matches {'--id ' + args.id if args.id else '--title ' + args.title!r}")

    entry = entries[idx]
    safe = re.sub(r"[^\w.-]", "-", entry.get("id", "paper"))
    pdf_dir = os.path.join(db_dir, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"{safe}.pdf")
    shutil.copyfile(args.file, pdf_path)

    md_path = None
    md_content = _convert_pdf(pdf_path)
    if md_content and md_content.strip():
        papers_dir = os.path.join(db_dir, "papers")
        os.makedirs(papers_dir, exist_ok=True)
        md_path = os.path.join(papers_dir, f"{safe}.md")
        with open(md_path, "w") as mf:
            mf.write(md_content)

    entry["pdf_path"] = os.path.relpath(pdf_path, db_dir)
    if md_path:
        entry["md_path"] = os.path.relpath(md_path, db_dir)
    entry["status"] = "downloaded"
    entries[idx] = entry
    save_db(args.db, entries)
    print(json.dumps({"id": entry.get("id"),
                      "pdf_path": entry.get("pdf_path"),
                      "md_path": entry.get("md_path"),
                      "status": entry["status"]}, indent=2, ensure_ascii=False))


def cmd_list(args):
    print(json.dumps(load_db(args.db), indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Google Scholar research helper")
    p.add_argument("--db", default="references.yaml",
                   help="path to the CSL-YAML reference database (default: references.yaml)")
    p.add_argument("--api-key", default=None,
                   help="SerpAPI key (or set SERPAPI_KEY env var)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="search Google Scholar and dedupe against db")
    s.add_argument("--query", required=True, help="search query")
    s.add_argument("--max", type=int, default=10)
    s.set_defaults(func=cmd_search)

    f = sub.add_parser("fetch", help="add a Scholar result to the db, optionally downloading its PDF")
    f.add_argument("--title", required=True, help="paper title")
    f.add_argument("--authors", nargs="*", help="author names, e.g. 'Given Family'")
    f.add_argument("--year", type=int, help="publication year")
    f.add_argument("--url", help="PDF or page URL to download from")
    f.add_argument("--page-url", help="the paper's landing page URL (for the CSL URL field)")
    f.add_argument("--venue", help="journal or conference name")
    f.set_defaults(func=cmd_fetch)

    pd = sub.add_parser("pending",
                        help="write a manual-download checklist of metadata-only papers")
    pd.set_defaults(func=cmd_pending)

    ing = sub.add_parser("ingest",
                         help="attach a manually-downloaded PDF to an existing entry")
    ing.add_argument("--id", help="citation id of the db entry to attach to")
    ing.add_argument("--title", help="title of the db entry (if no --id)")
    ing.add_argument("--file", required=True, help="path to the downloaded PDF")
    ing.set_defaults(func=cmd_ingest)

    l = sub.add_parser("list", help="print the db as JSON")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
