#!/usr/bin/env python3
"""arXiv research helper for the update-references skill.

Handles the deterministic, fiddly parts so the model can focus on reading
and summarizing: querying the arXiv API, parsing the Atom feed, downloading
PDFs, and maintaining a YAML reference database that dedupes papers and
tracks versions.

Subcommands:
  search   Query arXiv and cross-reference against the YAML db. Prints a
           JSON list of candidates, each tagged new / known / outdated.
  fetch    Download a paper's PDF and create/update its db entry
           (status: downloaded). Prints the local PDF path + metadata.
  record   Mark a paper as summarized: attach the summary file path and
           any topics/relevance notes. Call this after writing the summary.
  list     Print the current db as JSON (for a quick overview).

The db is plain YAML, keyed nowhere special — it's a list under `papers:`.
A paper's identity is its base arXiv id (e.g. 2310.12345), independent of
version. That is how we avoid downloading the same paper twice while still
noticing when a newer version (v2, v3, ...) appears.

Stdlib only except PyYAML (`pip install --user pyyaml`).
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
        return {"papers": []}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("papers", [])
    return data


def save_db(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=100)


def index_by_id(db):
    return {p["id"]: p for p in db.get("papers", [])}


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
        except Exception as e:  # noqa: BLE001
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
            status = "outdated"  # we have it, but a newer version exists
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


def extract_text(pdf_path):
    """Best-effort PDF -> text so the model can read papers even when the Read
    tool cannot render PDFs (no poppler). Tries pypdf, then pdfminer. Returns
    the text, or None if neither library is installed or extraction fails."""
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
    # Resolve output dirs relative to the DATABASE, not the CWD, so PDFs, text,
    # and summaries always sit together regardless of where the script is run.
    db_dir = os.path.dirname(os.path.abspath(args.db))
    pdf_dir = args.pdf_dir or os.path.join(db_dir, "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    safe = re.sub(r"[^\w.-]", "-", meta["id"])
    pdf_path = os.path.join(pdf_dir, f"{safe}v{meta['version']}.pdf")
    req = urllib.request.Request(meta["pdf_url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(pdf_path, "wb") as f:
        f.write(r.read())

    # Best-effort text sidecar for environments that can't render PDFs.
    text_path = None
    text = extract_text(pdf_path)
    if text and text.strip():
        text_dir = os.path.join(db_dir, "text")
        os.makedirs(text_dir, exist_ok=True)
        text_path = os.path.join(text_dir, f"{safe}v{meta['version']}.txt")
        with open(text_path, "w") as tf:
            tf.write(text)

    db = load_db(args.db)
    idx = index_by_id(db)
    entry = idx.get(meta["id"])
    record = {
        "id": meta["id"],
        "version": meta["version"],
        "title": meta["title"],
        "authors": meta["authors"],
        "published": meta["published"],
        "updated": meta["updated"],
        "primary_category": meta["primary_category"],
        "categories": meta["categories"],
        "abs_url": meta["abs_url"],
        "pdf_url": meta["pdf_url"],
        "pdf_path": os.path.relpath(pdf_path, db_dir),
        "text_path": os.path.relpath(text_path, db_dir) if text_path else None,
        "status": "downloaded",
        "added": str(date.today()),
    }
    if entry:
        # preserve summary metadata across a version bump
        for keep in ("summary_file", "topics", "relevance", "added"):
            if keep in entry and keep not in ("status",):
                record.setdefault(keep, entry[keep])
        record["added"] = entry.get("added", record["added"])
        db["papers"] = [record if p["id"] == meta["id"] else p for p in db["papers"]]
    else:
        db["papers"].append(record)
    save_db(args.db, db)
    print(json.dumps({"pdf_path": pdf_path, "text_path": text_path, "meta": record},
                     indent=2, ensure_ascii=False))


def cmd_record(args):
    db = load_db(args.db)
    idx = index_by_id(db)
    entry = idx.get(args.id)
    if not entry:
        sys.exit(f"Paper {args.id} not in db. Run `fetch` first.")
    entry["status"] = "summarized"
    if args.summary_file:
        entry["summary_file"] = args.summary_file
    if args.topics:
        entry["topics"] = args.topics
    if args.relevance:
        entry["relevance"] = args.relevance
    db["papers"] = [entry if p["id"] == args.id else p for p in db["papers"]]
    save_db(args.db, db)
    print(json.dumps(entry, indent=2, ensure_ascii=False))


def cmd_list(args):
    print(json.dumps(load_db(args.db), indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(description="arXiv research helper")
    p.add_argument("--db", default="arxiv/papers.yaml",
                   help="path to the YAML reference database (default: arxiv/papers.yaml)")
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

    l = sub.add_parser("list", help="print the db as JSON")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
