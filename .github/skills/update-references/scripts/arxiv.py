#!/usr/bin/env python3
"""arXiv research helper for the update-references skill.

Handles the deterministic, fiddly parts so the model can focus on reading
and summarizing: querying the arXiv API, parsing the Atom feed, downloading
PDFs, and maintaining a CSL-YAML reference database that dedupes papers and
tracks versions.

Subcommands:
  search   Query arXiv and cross-reference against the YAML db. Prints a
           JSON list of candidates, each tagged new / known / outdated.
  fetch    Download a paper's PDF, convert to markdown, and create/update
           its db entry (status: downloaded). Prints the local paths + metadata.
  record   Mark a paper as summarized: attach the summary file path and
           any topics/relevance notes. Call this after writing the summary.
  repair   Walk the database and re-convert any PDFs whose markdown file is
           missing. Migrates legacy text_path entries to md_path.
  list     Print the current db as JSON (for a quick overview).

The db is CSL-YAML — a bare YAML list of entries, each with an `id` field.
This is the same format pandoc uses for bibliographies, so the file is
directly usable as `--bibliography references.yaml`. Skill-internal fields
(status, version, pdf_path, etc.) are preserved but ignored by pandoc.

A paper's identity is its base arXiv id (e.g. 2310.12345), independent of
version. That is how we avoid downloading the same paper twice while still
noticing when a newer version (v2, v3, ...) appears.

Stdlib only except PyYAML (`pip install --user pyyaml`). pymupdf4llm is
recommended for PDF-to-markdown conversion; pypdf is the fallback.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

import _naming

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Install with: python3 -m pip install --user pyyaml")

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
API = "http://export.arxiv.org/api/query"
USER_AGENT = "update-references-skill/1.0 (https://github.com/petar-djukic/spindle)"


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #

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


def index_by_id(entries):
    """Index by base arXiv id (GH-140).

    Keys on the arxiv_id field when present — the citation id may be a legacy
    long form (shen-small-llms-are-2024) or a GH-87 short key (shen-2024), so
    it cannot serve as the arXiv lookup. Version-suffixed arxiv_ids get a
    base-form alias; the citation id is kept as a fallback for legacy dbs
    whose entries were keyed by the arXiv id itself.
    """
    idx = {}
    for p in entries:
        aid = str(p.get("arxiv_id") or "")
        if aid:
            idx[aid] = p
            idx.setdefault(re.sub(r"v\d+$", "", aid), p)
    for p in entries:
        idx.setdefault(str(p.get("id")), p)
    return idx


# --------------------------------------------------------------------------- #
# Author name helpers
# --------------------------------------------------------------------------- #

def parse_author_name(name):
    """Convert 'Given Family' or 'Family, Given' to CSL {family, given}."""
    name = name.strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        return {"family": parts[0], "given": parts[1] if len(parts) > 1 else ""}
    parts = name.rsplit(None, 1)
    if len(parts) == 2:
        return {"family": parts[1], "given": parts[0]}
    return {"family": name, "given": ""}


# --------------------------------------------------------------------------- #
# arXiv API
# --------------------------------------------------------------------------- #

def split_id(raw):
    """'http://arxiv.org/abs/2310.12345v2' -> ('2310.12345', 2)."""
    tail = raw.rstrip("/").split("/")[-1]
    m = re.match(r"(.+?)v(\d+)$", tail)
    if m:
        return m.group(1), int(m.group(2))
    return tail, 1


def parse_entry(entry):
    raw_id = entry.findtext(f"{ATOM}id", "")
    base_id, version = split_id(raw_id)
    authors = [a.findtext(f"{ATOM}name", "").strip()
               for a in entry.findall(f"{ATOM}author")]
    categories = [c.get("term") for c in entry.findall(f"{ATOM}category")]
    primary = entry.find(f"{ARXIV}primary_category")
    pdf_url = None
    abs_url = None
    for link in entry.findall(f"{ATOM}link"):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")
        if link.get("rel") == "alternate":
            abs_url = link.get("href")
    return {
        "id": base_id,
        "version": version,
        "title": " ".join(entry.findtext(f"{ATOM}title", "").split()),
        "authors": authors,
        "abstract": " ".join(entry.findtext(f"{ATOM}summary", "").split()),
        "published": entry.findtext(f"{ATOM}published", "")[:10],
        "updated": entry.findtext(f"{ATOM}updated", "")[:10],
        "primary_category": primary.get("term") if primary is not None else None,
        "categories": categories,
        "abs_url": abs_url or f"https://arxiv.org/abs/{base_id}",
        "pdf_url": pdf_url or f"https://arxiv.org/pdf/{base_id}v{version}",
    }


def api_request(params):
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    return b""


def api_search(query, max_results, categories=None, sort="relevance"):
    search_query = query
    if categories:
        cat_clause = " OR ".join(f"cat:{c}" for c in categories)
        search_query = f"({query}) AND ({cat_clause})"
    sort_map = {
        "relevance": "relevance",
        "recent": "submittedDate",
        "updated": "lastUpdatedDate",
    }
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_map.get(sort, "relevance"),
        "sortOrder": "descending",
    }
    raw = api_request(params)
    root = ET.fromstring(raw)
    return [parse_entry(e) for e in root.findall(f"{ATOM}entry")]


def api_get_ids(ids):
    """Fetch metadata for specific base ids via id_list (latest version)."""
    params = {"id_list": ",".join(ids), "max_results": len(ids)}
    raw = api_request(params)
    root = ET.fromstring(raw)
    return [parse_entry(e) for e in root.findall(f"{ATOM}entry")]


def _first_family(meta):
    """First author's family name from an arXiv metadata dict."""
    authors = meta.get("authors", [])
    if not authors:
        return ""
    first = authors[0]
    if isinstance(first, dict):
        return first.get("family", "")
    return parse_author_name(first).get("family", "")


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #

def cmd_search(args):
    results = api_search(args.query, args.max, args.categories, args.sort)
    known = index_by_id(load_db(args.db))
    out = []
    for r in results:
        prev = known.get(r["id"])
        if prev is None:
            status = "new"
        elif r["version"] > int(prev.get("version", 1)):
            status = "outdated"
        else:
            status = "known"
        out.append({
            "id": r["id"],
            "version": r["version"],
            "status": status,
            "have_version": int(prev["version"]) if prev else None,
            "db_status": prev.get("status") if prev else None,
            "title": r["title"],
            "authors": r["authors"],
            "published": r["published"],
            "updated": r["updated"],
            "primary_category": r["primary_category"],
            "abs_url": r["abs_url"],
            "pdf_url": r["pdf_url"],
            "abstract": r["abstract"],
        })
    print(json.dumps(out, indent=2, ensure_ascii=False))


def convert_pdf(pdf_path):
    """Best-effort PDF -> markdown. Tries pymupdf4llm, falls back to pypdf plain text."""
    try:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(pdf_path)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                parts.append("")
        return "\n".join(parts)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        return None
    try:
        from pdfminer.high_level import extract_text as _pm
        return _pm(pdf_path)
    except Exception:  # noqa: BLE001
        return None


def cmd_fetch(args):
    metas = api_get_ids([args.id])
    if not metas:
        sys.exit(f"No arXiv entry found for id {args.id}")
    meta = metas[0]
    db_dir = os.path.dirname(os.path.abspath(args.db))

    csl_authors = [parse_author_name(a) for a in meta["authors"]]
    year = int(meta["published"][:4]) if meta["published"] else None
    stem = _naming.paper_stem(_first_family(meta), year, meta["title"],
                              arxiv_id=meta["id"], version=meta["version"])

    pdf_dir = args.pdf_dir or os.path.join(db_dir, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"{stem}.pdf")
    req = urllib.request.Request(meta["pdf_url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(pdf_path, "wb") as f:
        f.write(r.read())

    md_path = None
    md_content = convert_pdf(pdf_path)
    if md_content and md_content.strip():
        papers_dir = os.path.join(db_dir, "papers")
        os.makedirs(papers_dir, exist_ok=True)
        md_path = os.path.join(papers_dir, f"{stem}.md")
        with open(md_path, "w") as mf:
            mf.write(md_content)

    entries = load_db(args.db)
    idx = index_by_id(entries)
    existing = idx.get(meta["id"])

    record = {
        "id": existing["id"] if existing
              else _naming.citation_key(_first_family(meta), year,
                                        {p["id"] for p in entries if p.get("id")}),
        "type": "article",
        "title": meta["title"],
        "author": csl_authors,
        "container-title": f"arXiv preprint arXiv:{meta['id']}",
        "URL": meta["abs_url"],
        "issued": {"year": year} if year else {},
        "arxiv_id": meta["id"],
        "version": meta["version"],
        "primary_category": meta["primary_category"],
        "categories": meta["categories"],
        "pdf_path": os.path.relpath(pdf_path, db_dir),
        "md_path": os.path.relpath(md_path, db_dir) if md_path else None,
        "status": "downloaded",
        "added": str(date.today()),
    }
    if existing:
        # Update in place (GH-140/GH-139): the paper was just downloaded, so
        # paths and version refresh; everything else is additive — CSL extras,
        # custom stamps, and openalex ranking/discovery blocks survive.
        prev_version = existing.get("version")
        existing["arxiv_id"] = meta["id"]
        existing["version"] = meta["version"]
        existing["pdf_path"] = os.path.relpath(pdf_path, db_dir)
        if md_path:
            existing["md_path"] = os.path.relpath(md_path, db_dir)
        for k in ("title", "author", "container-title", "URL", "issued",
                  "primary_category", "categories"):
            if not existing.get(k) and record.get(k):
                existing[k] = record[k]
        # status: forward from pre-read states; a version bump re-opens a
        # summarized entry (summary metadata stays — it flags the re-read).
        if existing.get("status") in (None, "metadata-only", "candidate",
                                      "needs-review"):
            existing["status"] = "downloaded"
        elif existing.get("status") == "summarized" and \
                prev_version is not None and meta["version"] > prev_version:
            existing["status"] = "downloaded"
        out = existing
    else:
        entries.append(record)
        out = record
    save_db(args.db, entries)
    print(json.dumps({"pdf_path": pdf_path, "md_path": md_path, "meta": out},
                     indent=2, ensure_ascii=False))


def cmd_record(args):
    entries = load_db(args.db)
    idx = {p.get("arxiv_id", p["id"]): p for p in entries}
    entry = idx.get(args.id)
    if not entry:
        entry = index_by_id(entries).get(args.id)
    if not entry:
        sys.exit(f"Paper {args.id} not in db. Run `fetch` first.")
    entry["status"] = "summarized"
    if args.summary_file:
        entry["summary_file"] = args.summary_file
    if args.topics:
        entry["topics"] = args.topics
    if args.relevance:
        entry["relevance"] = args.relevance
    eid = entry.get("arxiv_id", entry["id"])
    entries = [entry if p.get("arxiv_id", p["id"]) == eid else p for p in entries]
    save_db(args.db, entries)
    print(json.dumps(entry, indent=2, ensure_ascii=False))


def _entry_stem(entry):
    """The human-friendly file stem for a db entry, from its CSL fields."""
    authors = entry.get("author") or []
    family = ""
    if authors and isinstance(authors[0], dict):
        family = authors[0].get("family", "")
    year = (entry.get("issued") or {}).get("year")
    return _naming.paper_stem(family, year, entry.get("title", ""),
                              arxiv_id=entry.get("arxiv_id"),
                              version=entry.get("version"),
                              doi=entry.get("doi"),
                              citation_id=entry.get("id"))


_ARXIV_TAGGED = re.compile(r"arxiv-(\d{4}\.\d{4,5})(?:v(\d+))?", re.I)
_ARXIV_BARE = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?:v(\d+))?(?!\d)")


def _arxiv_id_from_name(name):
    """Recover an arXiv id (and version) from a filename, or (None, None)."""
    m = _ARXIV_TAGGED.search(name) or _ARXIV_BARE.search(name)
    if not m:
        return None, None
    return m.group(1), (int(m.group(2)) if m.group(2) else None)


def _pdf_metadata(pdf_abs):
    """Best-effort (title, author) from a PDF's embedded document info."""
    try:
        import pypdf
        info = pypdf.PdfReader(pdf_abs).metadata or {}
        title = (info.get("/Title") or "").strip()
        author = (info.get("/Author") or "").strip()
        return (title or None, author or None)
    except Exception:
        return (None, None)


def _convert_orphan_md(pdf_abs, stem, db_dir):
    """Convert a PDF to markdown under papers/<stem>.md; return the rel path."""
    md_content = convert_pdf(pdf_abs)
    if not md_content or not md_content.strip():
        return None
    papers_dir = os.path.join(db_dir, "papers")
    os.makedirs(papers_dir, exist_ok=True)
    md_abs = os.path.join(papers_dir, f"{stem}.md")
    with open(md_abs, "w") as mf:
        mf.write(md_content)
    return os.path.relpath(md_abs, db_dir)


def _reconcile_orphan(pdf_abs, entries, db_dir):
    """Import a PDF on disk that no db entry references.

    Returns one of 'imported', 'needs_review', or 'unregistered'.
    """
    fn = os.path.basename(pdf_abs)
    arxiv_id, _ver = _arxiv_id_from_name(fn)

    if arxiv_id:
        try:
            metas = api_get_ids([arxiv_id])
        except Exception:  # noqa: BLE001 — network/parse failure -> fall through
            metas = []
        if metas:
            meta = metas[0]
            year = int(meta["published"][:4]) if meta["published"] else None
            fam = _first_family(meta)
            stem = _naming.paper_stem(fam, year, meta["title"],
                                      arxiv_id=meta["id"], version=meta["version"])
            new_rel = os.path.join("pdfs", f"{stem}.pdf")
            new_abs = os.path.join(db_dir, new_rel)
            if os.path.abspath(new_abs) != os.path.abspath(pdf_abs):
                os.rename(pdf_abs, new_abs)
            md_rel = _convert_orphan_md(new_abs, stem, db_dir)
            existing = index_by_id(entries).get(meta["id"])
            if existing:
                # Already tracked (lost its file) — attach, don't duplicate.
                existing["pdf_path"] = new_rel
                if md_rel:
                    existing["md_path"] = md_rel
                existing.setdefault("status", "downloaded")
                return "imported"
            cid = _naming.citation_key(fam, year,
                                       {p["id"] for p in entries if p.get("id")})
            entries.append({
                "id": cid,
                "type": "article",
                "title": meta["title"],
                "author": [parse_author_name(a) for a in meta["authors"]],
                "container-title": f"arXiv preprint arXiv:{meta['id']}",
                "URL": meta["abs_url"],
                "issued": {"year": year} if year else {},
                "arxiv_id": meta["id"],
                "version": meta["version"],
                "primary_category": meta["primary_category"],
                "categories": meta["categories"],
                "pdf_path": new_rel,
                "md_path": md_rel,
                "status": "downloaded",
                "added": str(date.today()),
            })
            return "imported"

    # Tier 2: embedded PDF metadata (inferred — flagged needs-review).
    title, author = _pdf_metadata(pdf_abs)
    if title and author:
        fam = parse_author_name(author).get("family", "") or "unknown"
        # Key first, so the file stem's citation_id matches what _entry_stem
        # will later compute (keeps a subsequent reconcile a no-op).
        cid = _naming.citation_key(fam, None,
                                   {p["id"] for p in entries if p.get("id")})
        stem = _naming.paper_stem(fam, None, title, citation_id=cid)
        new_rel = os.path.join("pdfs", f"{stem}.pdf")
        new_abs = os.path.join(db_dir, new_rel)
        if os.path.abspath(new_abs) != os.path.abspath(pdf_abs):
            os.rename(pdf_abs, new_abs)
        md_rel = _convert_orphan_md(new_abs, stem, db_dir)
        entries.append({
            "id": cid,
            "type": "article",
            "title": title,
            "author": [parse_author_name(author)],
            "issued": {},
            "URL": "",
            "pdf_path": new_rel,
            "md_path": md_rel,
            "status": "needs-review",
            "source": "local-import",
            "added": str(date.today()),
        })
        return "needs_review"

    # Tier 3: unrecoverable.
    return "unregistered"


def _write_unregistered(db_dir, filenames):
    """List Tier-3 orphans with a ready-to-run ingest command per file."""
    out_path = os.path.join(db_dir, "unregistered-pdfs.md")
    if not filenames:
        if os.path.exists(out_path):
            os.remove(out_path)
        return
    lines = ["# PDFs that need metadata", "",
             "These files are in `pdfs/` but could not be identified. Register",
             "each with its metadata:", "", "```",
             "scholar.py ingest --db <db> --file <path> \\",
             "  --title \"…\" --authors \"Given Family\" --year YYYY", "```", ""]
    for fn in filenames:
        lines.append(f"- [ ] `pdfs/{fn}`")
    lines.append("")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))


def cmd_repair(args):
    entries = load_db(args.db)
    db_dir = os.path.dirname(os.path.abspath(args.db))
    checked = converted = skipped = 0
    for entry in entries:
        checked += 1
        pdf_rel = entry.get("pdf_path")
        if not pdf_rel:
            skipped += 1
            continue
        pdf_abs = os.path.join(db_dir, pdf_rel)
        if not os.path.exists(pdf_abs):
            skipped += 1
            continue
        md_rel = entry.get("md_path")
        needs_convert = not md_rel or not os.path.exists(os.path.join(db_dir, md_rel))
        if not needs_convert:
            continue
        md_content = convert_pdf(pdf_abs)
        if not md_content or not md_content.strip():
            skipped += 1
            continue
        papers_dir = os.path.join(db_dir, "papers")
        os.makedirs(papers_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(pdf_rel))[0]
        md_abs = os.path.join(papers_dir, f"{stem}.md")
        with open(md_abs, "w") as mf:
            mf.write(md_content)
        entry["md_path"] = os.path.relpath(md_abs, db_dir)
        converted += 1

    # Migration: rename existing pdf/markdown/summary files to the
    # human-friendly stem and update the db path fields. Idempotent — a file
    # already at its target name is left alone. Citation ids are NOT rewritten.
    renamed = 0
    for entry in entries:
        stem = _entry_stem(entry)
        for field, subdir, default_ext in (("pdf_path", "pdfs", ".pdf"),
                                           ("md_path", "papers", ".md"),
                                           ("summary_file", "summaries", ".md")):
            rel = entry.get(field)
            if not rel:
                continue
            old_abs = os.path.join(db_dir, rel)
            if not os.path.exists(old_abs):
                continue
            ext = os.path.splitext(rel)[1] or default_ext
            new_rel = os.path.join(subdir, f"{stem}{ext}")
            new_abs = os.path.join(db_dir, new_rel)
            if os.path.abspath(old_abs) == os.path.abspath(new_abs):
                continue
            os.makedirs(os.path.dirname(new_abs), exist_ok=True)
            os.rename(old_abs, new_abs)
            entry[field] = new_rel
            renamed += 1

    # Orphan import: PDFs in pdfs/ that no entry references. Recover metadata,
    # convert, name to the convention, and add an entry — so the database is
    # complete after a reconcile, not just consistent.
    imported = needs_review = 0
    unregistered = []
    pdfs_dir = os.path.join(db_dir, "pdfs")
    if os.path.isdir(pdfs_dir):
        tracked = {os.path.abspath(os.path.join(db_dir, e["pdf_path"]))
                   for e in entries if e.get("pdf_path")}
        for fn in sorted(os.listdir(pdfs_dir)):
            if not fn.lower().endswith(".pdf"):
                continue
            pdf_abs = os.path.join(pdfs_dir, fn)
            if os.path.abspath(pdf_abs) in tracked:
                continue
            result = _reconcile_orphan(pdf_abs, entries, db_dir)
            if result == "imported":
                imported += 1
            elif result == "needs_review":
                needs_review += 1
            else:
                unregistered.append(fn)
    _write_unregistered(db_dir, unregistered)

    save_db(args.db, entries)
    print(json.dumps({"checked": checked, "converted": converted,
                      "renamed": renamed, "imported": imported,
                      "needs_review": needs_review,
                      "unregistered": len(unregistered), "skipped": skipped},
                     indent=2))


def cmd_list(args):
    print(json.dumps(load_db(args.db), indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(description="arXiv research helper")
    p.add_argument("--db", default="references.yaml",
                   help="path to the CSL-YAML reference database (default: references.yaml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="search arXiv and dedupe against db")
    s.add_argument("--query", required=True, help="arXiv query, e.g. 'all:finite state machine agent'")
    s.add_argument("--max", type=int, default=15)
    s.add_argument("--categories", nargs="*", default=None,
                   help="restrict to categories, e.g. cs.AI cs.CL cs.LG")
    s.add_argument("--sort", choices=["relevance", "recent", "updated"], default="relevance")
    s.set_defaults(func=cmd_search)

    f = sub.add_parser("fetch", help="download a paper's PDF and record it in the db")
    f.add_argument("--id", required=True, help="base arXiv id, e.g. 2310.12345")
    f.add_argument("--pdf-dir", default=None,
                   help="where to save the PDF (default: <db-dir>/pdfs, alongside the database)")
    f.set_defaults(func=cmd_fetch)

    r = sub.add_parser("record", help="mark a paper as summarized")
    r.add_argument("--id", required=True)
    r.add_argument("--summary-file", help="path to the written summary markdown")
    r.add_argument("--topics", nargs="*", help="topic tags, e.g. llm agents fsm")
    r.add_argument("--relevance", help="one line on why it matters to the current work")
    r.set_defaults(func=cmd_record)

    rp = sub.add_parser("repair",
                        help="reconcile the db: convert, rename, and import orphan PDFs")
    rp.set_defaults(func=cmd_repair)
    rc = sub.add_parser("reconcile",
                        help="alias for repair — reconcile disk against the database")
    rc.set_defaults(func=cmd_repair)

    l = sub.add_parser("list", help="print the db as JSON")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
