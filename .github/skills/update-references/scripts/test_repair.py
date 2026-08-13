#!/usr/bin/env python3
"""Tests for the file-moving paths in arxiv.py repair. Run:

    python3 test_repair.py

No network and no real PDFs: api_get_ids, _pdf_metadata and convert_pdf are
replaced by stubs, and the papers directory is synthetic. Everything else is
the real cmd_repair.

Covers GH-28. GH-22 was a read that failed quietly and a write that destroyed
the database; these are the paths that move *files*, and the guard added there
does nothing for them. The migration loop renames with os.rename, which
replaces its destination without a word, and nothing checked whether the
destination was already someone else's paper.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import types
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import arxiv  # noqa: E402
import _refdb  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s%s" % (name, ": " + str(detail) if detail else ""))
        FAILURES.append(name)


def entry(cid, family, year, title, pdf_rel, md_rel=None, **extra):
    e = {"id": cid, "type": "article-journal", "title": title,
         "author": [{"family": family, "given": "A."}],
         "issued": {"year": year}, "pdf_path": pdf_rel, "status": "downloaded"}
    if md_rel:
        e["md_path"] = md_rel
    e.update(extra)
    return e


def build(tmp, entries, extra_pdfs=()):
    """A synthetic paper directory: references.yaml, pdfs/, papers/."""
    os.makedirs(os.path.join(tmp, "pdfs"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "papers"), exist_ok=True)
    for e in entries:
        for field in ("pdf_path", "md_path"):
            rel = e.get(field)
            if not rel:
                continue
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write("content of %s\n" % rel)
    for name in extra_pdfs:
        with open(os.path.join(tmp, "pdfs", name), "w") as f:
            f.write("orphan %s\n" % name)
    db = os.path.join(tmp, "references.yaml")
    _refdb.save_db(db, entries)
    return db


def repair(db):
    """Run the real cmd_repair, returning its JSON summary."""
    args = types.SimpleNamespace(db=db)
    out = io.StringIO()
    with redirect_stdout(out):
        arxiv.cmd_repair(args)
    return json.loads(out.getvalue())


def install_stubs():
    """Replace the three functions that would need a network or a real PDF."""
    arxiv.convert_pdf = lambda path: "# Converted\n\nBody text.\n"
    arxiv._pdf_metadata = lambda path: (None, None)
    arxiv.api_get_ids = lambda ids: []


def paths_resolve(db):
    """Every pdf_path/md_path in the database points at a file that exists."""
    db_dir = os.path.dirname(os.path.abspath(db))
    missing = []
    for e in _refdb.load_db(db):
        for field in ("pdf_path", "md_path", "summary_file"):
            rel = e.get(field)
            if rel and not os.path.exists(os.path.join(db_dir, rel)):
                missing.append("%s:%s=%s" % (e.get("id"), field, rel))
    return missing


def main():
    install_stubs()

    # --- the migration rename (arxiv.py:577) --------------------------------
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        db = build(tmp, [entry("lamport-1978", "Lamport", 1978,
                               "Time Clocks and the Ordering of Events",
                               "pdfs/legacy-name.pdf", "papers/legacy-name.md")])
        summary = repair(db)
        check("migration renames the legacy file", summary["renamed"] >= 1, summary)
        check("no path dangles after the rename", paths_resolve(db) == [],
              paths_resolve(db))
        moved = _refdb.load_db(db)[0]["pdf_path"]
        check("the new name is the human-friendly stem",
              "Lamport-1978" in moved and "legacy-name" not in moved, moved)

        # --- running it twice is a no-op -----------------------------------
        before = _refdb.load_db(db)
        second = repair(db)
        check("a second repair renames nothing", second["renamed"] == 0, second)
        check("a second repair changes no entry", _refdb.load_db(db) == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- the orphan-with-arxiv-id path (arxiv.py:442) -----------------------
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        db = build(tmp, [], extra_pdfs=["2401.00001v1.pdf"])
        arxiv.api_get_ids = lambda ids: [{
            "id": "2401.00001", "version": "1", "published": "2024-01-02",
            "title": "A Study of Orphan Recovery", "abs_url": "http://x/abs",
            "authors": ["Grace Hopper"],
            "primary_category": "cs.DC", "categories": ["cs.DC"],
            "summary": "s", "pdf_url": "http://x/pdf",
        }]
        summary = repair(db)
        check("an arXiv orphan is imported", summary["imported"] == 1, summary)
        check("the orphan's paths resolve", paths_resolve(db) == [],
              paths_resolve(db))
        check("the orphan PDF was renamed to the stem",
              not os.path.exists(os.path.join(tmp, "pdfs", "2401.00001v1.pdf")))
        arxiv.api_get_ids = lambda ids: []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- the embedded-metadata path (arxiv.py:485) --------------------------
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        db = build(tmp, [], extra_pdfs=["scanned.pdf"])
        arxiv._pdf_metadata = lambda path: ("An Inferred Title", "Grace Hopper")
        summary = repair(db)
        check("a PDF with embedded metadata is flagged needs-review",
              summary["needs_review"] == 1, summary)
        check("the needs-review entry's paths resolve", paths_resolve(db) == [],
              paths_resolve(db))
        arxiv._pdf_metadata = lambda path: (None, None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- the unregistered listing and its removal (arxiv.py:511) ------------
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        db = build(tmp, [], extra_pdfs=["mystery.pdf"])
        listing = os.path.join(tmp, "unregistered-pdfs.md")
        summary = repair(db)
        check("an unidentifiable PDF is listed as unregistered",
              summary["unregistered"] == 1, summary)
        check("the listing file is written", os.path.exists(listing))

        os.remove(os.path.join(tmp, "pdfs", "mystery.pdf"))
        summary = repair(db)
        check("the listing is removed once no orphans remain",
              not os.path.exists(listing), summary)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- the stem collision (GH-28) -----------------------------------------
    # Two entries sharing a citation id — plausible in a hand-maintained
    # bibliography, which is exactly what GH-22 was about — resolve to the same
    # stem. os.rename replaces its destination silently, so one paper's PDF was
    # overwritten by the other's while both entries still pointed at a file
    # that existed. The database looked consistent; one paper was gone.
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        db = build(tmp, [
            entry("lee-2024", "Lee", 2024, "Consensus",
                  "pdfs/first.pdf", "papers/first.md"),
            entry("lee-2024", "Lee", 2024, "Consensus",
                  "pdfs/second.pdf", "papers/second.md"),
        ])
        with open(os.path.join(tmp, "pdfs", "first.pdf"), "w") as f:
            f.write("FIRST PAPER\n")
        with open(os.path.join(tmp, "pdfs", "second.pdf"), "w") as f:
            f.write("SECOND PAPER\n")

        summary = repair(db)
        check("a stem collision leaves every path resolving",
              paths_resolve(db) == [], paths_resolve(db))
        # Refusing quietly would be its own failure: the curator has a
        # duplicate citation id to fix and no way to know it. Two, not one —
        # the losing entry collides on its pdf and its markdown alike.
        check("a stem collision is counted in the summary",
              summary.get("collisions") == 2, summary)

        db_dir = os.path.dirname(os.path.abspath(db))
        contents = []
        for e in _refdb.load_db(db):
            rel = e.get("pdf_path")
            if rel and os.path.exists(os.path.join(db_dir, rel)):
                with open(os.path.join(db_dir, rel)) as f:
                    contents.append(f.read().strip())
        check("a stem collision does not destroy one of the PDFs",
              sorted(contents) == ["FIRST PAPER", "SECOND PAPER"], contents)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("%d failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all repair tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
