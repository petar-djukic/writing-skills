#!/usr/bin/env python3
"""OpenAlex backend for the update-references skill: hierarchical search.

OpenAlex (successor to Microsoft Academic Graph) is the backbone for the
hierarchical protocol: keyless, ~10 req/s on the polite pool (set --mailto or
OPENALEX_MAILTO), 250M+ works including IEEE, `referenced_works` in-record
(backward snowball = one request), institutions as first-class entities, and
field-weighted citation impact (fwci, 1.0 = field average).

Subcommands (all share references.yaml and its dedupe):
  search         works search; candidates tagged new/known with ranking signals
  hubs           aggregate a query's results into ranked KEY AUTHORS,
                 PIVOTAL PAPERS, and SURVEYS — the drill targets
  references     backward snowball: a work's referenced_works, ranked
  citations      forward snowball: works citing a work, ranked
  author-papers  a hub author's works, ranked
  fetch          resolve a work (by W-id or DOI), download the OA PDF when one
                 exists (else status: metadata-only -> pending/ingest loop),
                 and write the entry with persistent ranking/discovery markers
  list           print the db as JSON

Persistent markers written on fetch (skill-internal; pandoc ignores them):
  ranking:   cited_by, references_count, fwci, citation_percentile, venue,
             institutions, institution_types, retrieved
  discovery: method (seed-search|survey-references|forward-citations|
             author-drill), via (the hub it came through)

Stdlib + PyYAML; _naming for stems and citation keys.
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
    sys.exit("PyYAML is required (pixi env supplies it).")

API = "https://api.openalex.org"
USER_AGENT = "update-references-skill/1.0"
SELECT = ("id,doi,title,publication_year,cited_by_count,fwci,"
          "citation_normalized_percentile,referenced_works,authorships,"
          "primary_location,best_oa_location,type")


# --- db helpers (same shape as the sibling backends) ------------------------

def load_db(path):
    if not os.path.exists(path):
        return []
    data = yaml.safe_load(open(path))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "papers" in data:
        return data["papers"]
    return []


def save_db(path, entries):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(entries, f, sort_keys=False, allow_unicode=True, width=100)


def normalize_title(t):
    return re.sub(r"\s+", " ", (t or "").lower().strip())


def _convert_pdf(pdf_path):
    try:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(pdf_path)
    except Exception:  # noqa: BLE001
        pass
    try:
        import pypdf
        return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(pdf_path).pages)
    except Exception:  # noqa: BLE001
        return None


# --- API ---------------------------------------------------------------------

def _mailto(args):
    m = getattr(args, "mailto", None) or os.environ.get("OPENALEX_MAILTO")
    if not m:
        print("note: set --mailto or OPENALEX_MAILTO for the polite pool "
              "(~10 req/s); anonymous pool is slower", file=sys.stderr)
    return m


def _get(path, params, mailto, retries=3):
    if mailto:
        params = dict(params, mailto=mailto)
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    delay = 2.0
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            sys.exit(f"OpenAlex error (HTTP {e.code}) on /{path}: {e.reason}")
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            sys.exit(f"OpenAlex request failed: {e.reason}")


def _short_id(openalex_url):
    """https://openalex.org/W123 -> W123 (works for A/S/I ids too)."""
    return (openalex_url or "").rsplit("/", 1)[-1]


def _abstract_from_inverted(inv):
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def _norm_work(w):
    src = (w.get("primary_location") or {}).get("source") or {}
    oa = w.get("best_oa_location") or {}
    insts, inst_types, authors = [], [], []
    for a in (w.get("authorships") or []):
        au = a.get("author") or {}
        authors.append({"name": au.get("display_name", ""),
                        "id": _short_id(au.get("id", ""))})
        for inst in (a.get("institutions") or []):
            n = inst.get("display_name")
            if n and n not in insts:
                insts.append(n)
                inst_types.append(inst.get("type") or "?")
    pct = (w.get("citation_normalized_percentile") or {}).get("value")
    doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
    return {
        "openalex_id": _short_id(w.get("id", "")),
        "doi": doi,
        "title": w.get("title") or "",
        "year": w.get("publication_year"),
        "venue": src.get("display_name") or "",
        "type": w.get("type"),
        "cited_by": w.get("cited_by_count", 0),
        "fwci": w.get("fwci"),
        "citation_percentile": round(pct * 100, 1) if pct is not None else None,
        "references_count": len(w.get("referenced_works") or []),
        "referenced_works": [_short_id(x) for x in (w.get("referenced_works") or [])],
        "authors": authors,
        "institutions": insts[:6],
        "institution_types": inst_types[:6],
        "oa_pdf": oa.get("pdf_url"),
        "landing": oa.get("landing_page_url") or (w.get("doi") or ""),
    }


# --- dedupe ------------------------------------------------------------------

def _index(entries):
    by_title = {normalize_title(e.get("title", "")): e for e in entries if e.get("title")}
    by_doi = {e["doi"].lower(): e for e in entries if e.get("doi")}
    by_oid = {e["openalex_id"]: e for e in entries if e.get("openalex_id")}
    return by_title, by_doi, by_oid


def _known(rec, idx):
    by_title, by_doi, by_oid = idx
    if rec.get("openalex_id") and rec["openalex_id"] in by_oid:
        return by_oid[rec["openalex_id"]]
    if rec.get("doi") and rec["doi"].lower() in by_doi:
        return by_doi[rec["doi"].lower()]
    return by_title.get(normalize_title(rec.get("title", "")))


def _tag(records, db_path):
    idx = _index(load_db(db_path))
    out = []
    for r in records:
        prev = _known(r, idx)
        rr = dict(r)
        rr["status"] = "known" if prev else "new"
        rr["db_status"] = prev.get("status") if prev else None
        rr.pop("referenced_works", None)  # noisy in listings
        out.append(rr)
    return out


# --- subcommands ---------------------------------------------------------------

def cmd_search(args):
    params = {"search": args.query, "per-page": min(args.max, 50),
              "select": SELECT}
    if args.year:
        params["filter"] = f"publication_year:{args.year}"
    data = _get("works", params, _mailto(args))
    recs = [_norm_work(w) for w in data.get("results", [])[:args.max]]
    print(json.dumps(_tag(recs, args.db), indent=2, ensure_ascii=False))


def cmd_hubs(args):
    params = {"search": args.query, "per-page": min(args.max, 50), "select": SELECT}
    data = _get("works", params, _mailto(args))
    recs = [_norm_work(w) for w in data.get("results", [])]

    authors = {}
    for r in recs:
        for a in r["authors"]:
            if not a["id"]:
                continue
            d = authors.setdefault(a["id"], {"name": a["name"], "hits": 0,
                                             "total_cited_by": 0})
            d["hits"] += 1
            d["total_cited_by"] += r["cited_by"]
    key_authors = sorted(
        ({"author_id": k, **v} for k, v in authors.items() if v["hits"] >= 2),
        key=lambda x: (x["hits"], x["total_cited_by"]), reverse=True)[:8]

    pivotal = sorted(recs, key=lambda r: (r["cited_by"], r["fwci"] or 0),
                     reverse=True)[:8]
    surveys = [r for r in recs
               if r.get("type") == "review"
               or re.search(r"\b(survey|systematic review|taxonomy|"
                            r"literature review)\b", r["title"], re.I)]

    def slim(r):
        return {k: r[k] for k in ("openalex_id", "title", "year", "venue",
                                  "cited_by", "fwci", "references_count")}
    print(json.dumps({
        "query": args.query,
        "key_authors": key_authors,
        "pivotal_papers": [slim(r) for r in pivotal],
        "surveys": [slim(r) for r in surveys],
        "drill_next": "references --id <survey/pivotal W-id>; citations --id "
                      "<pivotal W-id>; author-papers --author-id <A-id>",
    }, indent=2, ensure_ascii=False))


def _ranked_list(recs, db_path, cap):
    recs = sorted(recs, key=lambda r: (r["cited_by"], r["fwci"] or 0), reverse=True)
    return _tag(recs[:cap], db_path)


def cmd_references(args):
    work = _get(f"works/{args.id}", {"select": "referenced_works,title"}, _mailto(args))
    refs = [_short_id(x) for x in (work.get("referenced_works") or [])]
    out = []
    for i in range(0, len(refs), 50):
        batch = "|".join(refs[i:i + 50])
        data = _get("works", {"filter": f"openalex:{batch}",
                              "per-page": 50, "select": SELECT}, _mailto(args))
        out.extend(_norm_work(w) for w in data.get("results", []))
    print(json.dumps({"of": work.get("title"), "total_references": len(refs),
                      "candidates": _ranked_list(out, args.db, args.max)},
                     indent=2, ensure_ascii=False))


def cmd_citations(args):
    data = _get("works", {"filter": f"cites:{args.id}",
                          "sort": "cited_by_count:desc",
                          "per-page": min(args.max, 50), "select": SELECT},
                _mailto(args))
    recs = [_norm_work(w) for w in data.get("results", [])]
    print(json.dumps({"citing": args.id, "total": data.get("meta", {}).get("count"),
                      "candidates": _ranked_list(recs, args.db, args.max)},
                     indent=2, ensure_ascii=False))


def cmd_author_papers(args):
    data = _get("works", {"filter": f"author.id:{args.author_id}",
                          "sort": "cited_by_count:desc",
                          "per-page": min(args.max, 50), "select": SELECT},
                _mailto(args))
    recs = [_norm_work(w) for w in data.get("results", [])]
    print(json.dumps({"author": args.author_id,
                      "candidates": _ranked_list(recs, args.db, args.max)},
                     indent=2, ensure_ascii=False))


def cmd_fetch(args):
    wid = args.id or (f"doi:{args.doi}" if args.doi else None)
    if not wid:
        sys.exit("--id W... or --doi ... required")
    w = _get(f"works/{wid}", {"select": SELECT}, _mailto(args))
    rec = _norm_work(w)

    db_dir = os.path.dirname(os.path.abspath(args.db))
    entries = load_db(args.db)
    existing = _known(rec, _index(entries))
    family = rec["authors"][0]["name"].split()[-1] if rec["authors"] else ""
    citation_id = (existing["id"] if existing
                   else _naming.citation_key(family, rec["year"],
                                             {p["id"] for p in entries if p.get("id")}))
    stem = _naming.paper_stem(family, rec["year"], rec["title"],
                              doi=rec["doi"], citation_id=citation_id)

    pdf_path = md_path = None
    if rec["oa_pdf"]:
        os.makedirs(os.path.join(db_dir, "pdfs"), exist_ok=True)
        pdf_path = os.path.join(db_dir, "pdfs", f"{stem}.pdf")
        try:
            req = urllib.request.Request(rec["oa_pdf"],
                                         headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r, open(pdf_path, "wb") as f:
                f.write(r.read())
            md = _convert_pdf(pdf_path)
            if md and md.strip():
                os.makedirs(os.path.join(db_dir, "papers"), exist_ok=True)
                md_path = os.path.join(db_dir, "papers", f"{stem}.md")
                open(md_path, "w").write(md)
        except Exception as e:  # noqa: BLE001
            print(f"Warning: OA pdf download failed: {e}", file=sys.stderr)
            pdf_path = None

    record = {
        "id": citation_id,
        "type": "article",
        "title": rec["title"],
        "author": [{"family": a["name"].split()[-1],
                    "given": " ".join(a["name"].split()[:-1])}
                   for a in rec["authors"] if a["name"]],
        "container-title": rec["venue"],
        "URL": rec["landing"] or "",
        "issued": {"year": rec["year"]} if rec["year"] else {},
        "source": "openalex",
        "openalex_id": rec["openalex_id"],
        "status": "downloaded" if pdf_path else "metadata-only",
        "added": str(date.today()),
        "ranking": {
            "cited_by": rec["cited_by"],
            "references_count": rec["references_count"],
            "fwci": rec["fwci"],
            "citation_percentile": rec["citation_percentile"],
            "venue": rec["venue"],
            "institutions": rec["institutions"],
            "institution_types": rec["institution_types"],
            "retrieved": str(date.today()),
        },
        "discovery": {
            "method": args.discovered or "seed-search",
            "via": args.via or "",
        },
    }
    if rec["doi"]:
        record["doi"] = rec["doi"]
    if pdf_path:
        record["pdf_path"] = os.path.relpath(pdf_path, db_dir)
    if md_path:
        record["md_path"] = os.path.relpath(md_path, db_dir)

    if existing:
        # Additive merge (GH-139): enrich in place, never delete or downgrade.
        # Everything already on the entry — status lifecycle, CSL fields
        # (volume/issue/page/publisher, uppercase DOI), custom stamps
        # (venue_verified, evidence_role, ...) — stays untouched.
        existing["openalex_id"] = rec["openalex_id"]
        existing["ranking"] = record["ranking"]          # refresh (dated)
        # discovery is provenance: keep the first record unless the caller
        # explicitly states a new path for this fetch.
        if "discovery" not in existing or args.discovered or args.via:
            existing["discovery"] = {"method": args.discovered or "seed-search",
                                     "via": args.via or ""}
        # fill CSL fields only where absent
        for k in ("title", "author", "container-title", "URL", "issued", "type"):
            if not existing.get(k) and record.get(k):
                existing[k] = record[k]
        # DOI: respect an existing uppercase-DOI (pandoc) or lowercase field
        if rec["doi"] and not existing.get("DOI") and not existing.get("doi"):
            existing["doi"] = rec["doi"]
        if pdf_path and not existing.get("pdf_path"):
            existing["pdf_path"] = os.path.relpath(pdf_path, db_dir)
        if md_path and not existing.get("md_path"):
            existing["md_path"] = os.path.relpath(md_path, db_dir)
        # status moves forward only: never off summarized/downloaded
        if pdf_path and existing.get("status") in (None, "metadata-only",
                                                   "candidate", "needs-review"):
            existing["status"] = "downloaded"
        elif not existing.get("status"):
            existing["status"] = "metadata-only"
        out = existing
    else:
        entries.append(record)
        out = record
    save_db(args.db, entries)
    print(json.dumps({"id": out["id"], "status": out.get("status"),
                      "pdf_path": out.get("pdf_path"),
                      "ranking": out["ranking"],
                      "discovery": out.get("discovery")},
                     indent=2, ensure_ascii=False))


def cmd_list(args):
    print(json.dumps(load_db(args.db), indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="OpenAlex hierarchical research helper")
    p.add_argument("--db", default="references.yaml")
    p.add_argument("--mailto", default=None,
                   help="email for the OpenAlex polite pool (or OPENALEX_MAILTO)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("--query", required=True)
    s.add_argument("--max", type=int, default=10)
    s.add_argument("--year", help="e.g. 2020 or 2018-2026")
    s.set_defaults(func=cmd_search)

    h = sub.add_parser("hubs", help="rank key authors, pivotal papers, surveys")
    h.add_argument("--query", required=True)
    h.add_argument("--max", type=int, default=40,
                   help="seed breadth to aggregate over")
    h.set_defaults(func=cmd_hubs)

    r = sub.add_parser("references", help="backward snowball (what it builds on)")
    r.add_argument("--id", required=True, help="OpenAlex W-id")
    r.add_argument("--max", type=int, default=15)
    r.set_defaults(func=cmd_references)

    c = sub.add_parser("citations", help="forward snowball (who builds on it)")
    c.add_argument("--id", required=True)
    c.add_argument("--max", type=int, default=15)
    c.set_defaults(func=cmd_citations)

    a = sub.add_parser("author-papers")
    a.add_argument("--author-id", required=True, help="OpenAlex A-id")
    a.add_argument("--max", type=int, default=15)
    a.set_defaults(func=cmd_author_papers)

    f = sub.add_parser("fetch")
    f.add_argument("--id", help="OpenAlex W-id")
    f.add_argument("--doi", help="DOI (alternative to --id)")
    f.add_argument("--discovered", default=None,
                   choices=["seed-search", "survey-references",
                            "forward-citations", "author-drill"],
                   help="how this paper was found (persisted as discovery.method)")
    f.add_argument("--via", default=None,
                   help="the hub it came through (persisted as discovery.via)")
    f.set_defaults(func=cmd_fetch)

    l = sub.add_parser("list")
    l.set_defaults(func=cmd_list)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
