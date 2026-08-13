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
from contextlib import redirect_stderr, redirect_stdout

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

    # --- an orphan whose stem is already taken (GH-32) ----------------------
    # The same failure as the collision above, on the path the GH-28 fix did
    # not reach. A stray untracked copy of a paper already in the database —
    # what a re-download leaves behind — identifies as its tracked twin and was
    # renamed straight over it, reported as a successful import.
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        # The entry carries the arXiv id, so its stem is the arxiv- form it is
        # already filed under and the migration leaves it alone. Without that
        # the migration renames it to the scholar- form first, freeing the name
        # and making the adoption legitimate — which is not the case under test.
        db = build(tmp, [entry("hopper-2024", "Hopper", 2024,
                               "A Study of Orphan Recovery",
                               "pdfs/Hopper-2024-a-study-of-orphan-recovery-"
                               "arxiv-2401.00001v1.pdf",
                               arxiv_id="2401.00001", version="1")],
                   extra_pdfs=["2401.00001.pdf"])
        tracked_abs = os.path.join(tmp, _refdb.load_db(db)[0]["pdf_path"])
        with open(tracked_abs, "w") as f:
            f.write("THE REAL PAPER\n")
        with open(os.path.join(tmp, "pdfs", "2401.00001.pdf"), "w") as f:
            f.write("STRAY COPY\n")
        arxiv.api_get_ids = lambda ids: [{
            "id": "2401.00001", "version": "1", "published": "2024-01-02",
            "title": "A Study of Orphan Recovery", "abs_url": "http://x/abs",
            "authors": ["Grace Hopper"],
            "primary_category": "cs.DC", "categories": ["cs.DC"],
            "summary": "s", "pdf_url": "http://x/pdf",
        }]
        err = io.StringIO()
        with redirect_stderr(err):
            summary = repair(db)

        with open(tracked_abs) as f:
            check("a stray copy does not overwrite the tracked paper",
                  f.read().strip() == "THE REAL PAPER", summary)
        check("the refused adoption is counted, not reported as an import",
              summary["imported"] == 0 and summary.get("collisions") == 1, summary)
        check("the refusal names the file on stderr",
              "2401.00001.pdf" in err.getvalue(), err.getvalue().strip()[:120])
        check("the stray copy is left on disk for the curator",
              os.path.exists(os.path.join(tmp, "pdfs", "2401.00001.pdf")))
        check("no path dangles after a refused adoption", paths_resolve(db) == [],
              paths_resolve(db))
        # The markdown is the second casualty: converting after the rename
        # would have written the stray file's text over the tracked entry's.
        md_rel = _refdb.load_db(db)[0].get("md_path")
        if md_rel:
            with open(os.path.join(tmp, md_rel)) as f:
                check("the tracked entry's markdown is not rewritten from the stray",
                      "Converted" in f.read())

        second = repair(db)
        check("a refused adoption is refused again, not churned",
              second.get("collisions") == 1 and second["imported"] == 0, second)
        arxiv.api_get_ids = lambda ids: []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- the same guard on the embedded-metadata path (arxiv.py:485) --------
    # Driven directly rather than through cmd_repair, because two tier-2 scans
    # cannot collide by derivation: citation_key disambiguates the second id to
    # hopper-nda, which lands in the stem's scholar- tag, so the two stems
    # differ. The guard here is defensive — it fires when the destination
    # exists for some other reason, such as a file left by an interrupted run —
    # and an untestable guard is one that rots, so it is exercised as a unit.
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        os.makedirs(os.path.join(tmp, "pdfs"))
        arxiv._pdf_metadata = lambda path: ("An Inferred Title", "Grace Hopper")
        orphan = os.path.join(tmp, "pdfs", "scan.pdf")
        with open(orphan, "w") as f:
            f.write("THE SCAN\n")
        taken = os.path.join(tmp, "pdfs",
                             "Hopper-nd-an-inferred-title-scholar-hopper-nd.pdf")
        with open(taken, "w") as f:
            f.write("ALREADY THERE\n")

        entries = []
        err = io.StringIO()
        with redirect_stderr(err):
            result = arxiv._reconcile_orphan(orphan, entries, tmp)

        check("a tier-2 orphan whose name is taken is refused",
              result == "collision", result)
        check("the refusal adds no entry", entries == [], entries)
        with open(taken) as f:
            check("the occupying file is untouched", f.read().strip() == "ALREADY THERE")
        with open(orphan) as f:
            check("the refused scan stays where it is", f.read().strip() == "THE SCAN")
        check("the tier-2 refusal is reported on stderr", "scan.pdf" in err.getvalue(),
              err.getvalue().strip()[:120])
        arxiv._pdf_metadata = lambda path: (None, None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- what keeps _convert_orphan_md safe (GH-31) -------------------------
    # It writes papers/<stem>.md with no clobber check, which reads like the
    # GH-28 bug one file type over. It is not, and the reason is ordering: the
    # migration loop runs first and has already moved every live entry's
    # markdown to that entry's own stem, so the name an orphan derives is
    # either free or belongs to the same paper. The two cases below are that
    # argument as assertions. They exist because the property is invisible in
    # the code — swap the two loops and the clobber becomes real, with nothing
    # else in this file failing.
    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        stem = "Doe-2025-a-study-of-things-arxiv-2501.12345v1"
        # A different paper is parked on the name the orphan will derive.
        db = build(tmp, [entry("other-1999", "Other", 1999, "Something Else",
                               "pdfs/other.pdf", "papers/%s.md" % stem)],
                   extra_pdfs=["2501.12345.pdf"])
        with open(os.path.join(tmp, "papers", "%s.md" % stem), "w") as f:
            f.write("A DIFFERENT PAPER'S MARKDOWN\n")
        arxiv.api_get_ids = lambda ids: [{
            "id": "2501.12345", "version": "1", "published": "2025-01-15",
            "title": "A Study of Things", "abs_url": "http://x/abs",
            "authors": ["Jane Doe"], "primary_category": "cs.SE",
            "categories": ["cs.SE"], "summary": "s", "pdf_url": "http://x/pdf",
        }]
        repair(db)
        got = _refdb.load_db(db)
        other = [e for e in got if e["id"] == "other-1999"][0]
        with open(os.path.join(tmp, other["md_path"])) as f:
            check("the migration moves a bystander's markdown clear of an import",
                  f.read().strip() == "A DIFFERENT PAPER'S MARKDOWN",
                  other.get("md_path"))
        check("the bystander's markdown is filed under its own stem",
              other["md_path"] == "papers/Other-1999-something-else-scholar-"
                                  "other-1999.md", other.get("md_path"))
        check("no path dangles after the import", paths_resolve(db) == [],
              paths_resolve(db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    tmp = tempfile.mkdtemp(prefix="test-repair-")
    try:
        # The other half: when the name genuinely is shared, it is the same
        # paper — an entry that lost its PDF — and rewriting its markdown from
        # the recovered file is the point, not a loss. A clobber guard here
        # would suppress this.
        stem = "Doe-2025-a-study-of-things-arxiv-2501.12345v1"
        db = build(tmp, [{"id": "doe-2025", "type": "article",
                          "title": "A Study of Things",
                          "author": [{"family": "Doe", "given": "Jane"}],
                          "issued": {"year": 2025}, "arxiv_id": "2501.12345",
                          "version": "1", "md_path": "papers/%s.md" % stem}],
                   extra_pdfs=["2501.12345.pdf"])
        with open(os.path.join(tmp, "papers", "%s.md" % stem), "w") as f:
            f.write("STALE MARKDOWN\n")
        summary = repair(db)
        got = _refdb.load_db(db)[0]

        check("an entry that lost its PDF gets it back, not a duplicate",
              len(_refdb.load_db(db)) == 1 and got.get("pdf_path"), summary)
        with open(os.path.join(tmp, got["md_path"])) as f:
            check("its markdown is rewritten from the recovered PDF",
                  "Converted" in f.read(), got.get("md_path"))
        check("no path dangles after the recovery", paths_resolve(db) == [],
              paths_resolve(db))
        arxiv.api_get_ids = lambda ids: []
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
