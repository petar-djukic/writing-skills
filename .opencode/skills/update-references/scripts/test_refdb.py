#!/usr/bin/env python3
"""Tests for _refdb, the shared references-database access. Run:

    python3 test_refdb.py

No network, no fixtures on disk beyond a temp directory.

Covers GH-22: `arxiv.py reconcile` on a references:-keyed bibliography loaded
zero entries, reported success, and wrote [] over thirty hand-maintained
entries. Every case here is about a read that must not quietly produce an empty
database, or a write that must not quietly destroy one.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _refdb  # noqa: E402

import yaml  # noqa: E402

FAILURES = []

ENTRIES = [
    {"id": "boehm1986", "type": "article-journal", "title": "A spiral model"},
    {"id": "brooks1975", "type": "book", "title": "The Mythical Man-Month"},
]


def check(name, condition, detail=""):
    if condition:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s%s" % (name, ": " + str(detail) if detail else ""))
        FAILURES.append(name)


def write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write(text)
    return path


def raises(exc_type, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc_type:
        return True
    except Exception:  # noqa: BLE001 - a different failure is still a failure
        return False
    return False


BARE = "- id: boehm1986\n  type: article-journal\n- id: brooks1975\n  type: book\n"
KEYED = "references:\n- id: boehm1986\n  type: article-journal\n- id: brooks1975\n  type: book\n"
PAPERS = "papers:\n- id: boehm1986\n  type: article-journal\n- id: brooks1975\n  type: book\n"


def main():
    tmp = tempfile.mkdtemp(prefix="test-refdb-")
    try:
        # --- every accepted shape reads every entry -----------------------
        for label, text in (("bare list", BARE), ("references:", KEYED), ("papers:", PAPERS)):
            path = write(tmp, "read-%s.yaml" % label.strip(":").replace(" ", "-"), text)
            entries = _refdb.load_db(path)
            check("%s reads both entries" % label, len(entries) == 2, len(entries))

        # --- the shape round-trips ----------------------------------------
        for label, text, expect_key in (("bare list", BARE, None),
                                        ("references:", KEYED, "references"),
                                        ("papers:", PAPERS, "papers")):
            path = write(tmp, "trip-%s.yaml" % label.strip(":").replace(" ", "-"), text)
            _refdb.save_db(path, _refdb.load_db(path))
            with open(path) as f:
                reparsed = yaml.safe_load(f)
            got_key = None if isinstance(reparsed, list) else next(iter(reparsed))
            check("%s keeps its root key on save" % label, got_key == expect_key,
                  "got %r" % got_key)
            check("%s is unchanged by a second pass" % label,
                  len(_refdb.load_db(path)) == 2)

        # --- an unreadable shape raises, never reads as empty --------------
        for label, text in (("mapping with no known root key", "bibliography:\n- id: x\n"),
                            ("scalar document", "just a string\n"),
                            ("root key holding a mapping", "references:\n  id: x\n")):
            path = write(tmp, "bad-%d.yaml" % len(label), text)
            check("%s raises rather than reading empty" % label,
                  raises(_refdb.DatabaseFormatError, _refdb.load_db, path))

        # --- absent and genuinely empty files are still empty --------------
        check("missing file is an empty database",
              _refdb.load_db(os.path.join(tmp, "nope.yaml")) == [])
        check("empty file is an empty database",
              _refdb.load_db(write(tmp, "empty.yaml", "")) == [])
        check("root key with a null value is an empty database",
              _refdb.load_db(write(tmp, "null.yaml", "references:\n")) == [])

        # --- the write guard ----------------------------------------------
        path = write(tmp, "guard.yaml", KEYED)
        check("empty write over a populated database is refused",
              raises(_refdb.EmptyWriteRefused, _refdb.save_db, path, []))
        check("the refused write left the file alone", len(_refdb.load_db(path)) == 2)

        _refdb.save_db(path, [], force=True)
        check("force=True allows the empty write", _refdb.load_db(path) == [])

        path = write(tmp, "grow.yaml", KEYED)
        _refdb.save_db(path, ENTRIES + [{"id": "parnas1972", "type": "article-journal"}])
        check("a non-empty write still goes through", len(_refdb.load_db(path)) == 3)

        path = os.path.join(tmp, "fresh.yaml")
        _refdb.save_db(path, [])
        check("an empty write to a new file is allowed", _refdb.load_db(path) == [])

        check("unparseable existing file is not overwritten",
              raises(_refdb.DatabaseFormatError, _refdb.save_db,
                     write(tmp, "unreadable.yaml", "bibliography:\n- id: x\n"), ENTRIES))

        # --- end to end, the reported reproduction -------------------------
        arxiv = os.path.join(HERE, "arxiv.py")
        if os.path.exists(arxiv):
            path = write(tmp, "reconcile.yaml", KEYED)
            proc = subprocess.run([sys.executable, arxiv, "--db", path, "reconcile"],
                                  capture_output=True, text=True, cwd=tmp)
            check("reconcile preserves a references:-keyed database",
                  len(_refdb.load_db(path)) == 2,
                  "rc=%d %s" % (proc.returncode, proc.stderr[-200:]))

            # The command must also refuse loudly on a shape it cannot read,
            # rather than exiting 0 having written nothing useful.
            bad = write(tmp, "reconcile-bad.yaml", "bibliography:\n- id: x\n")
            proc = subprocess.run([sys.executable, arxiv, "--db", bad, "reconcile"],
                                  capture_output=True, text=True, cwd=tmp)
            check("reconcile exits non-zero on an unreadable database",
                  proc.returncode != 0, "rc=%d" % proc.returncode)
            check("reconcile leaves the unreadable file untouched",
                  open(bad).read() == "bibliography:\n- id: x\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("%d failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all refdb tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
