#!/usr/bin/env python3
"""Entry points still import their shared modules when reached by symlink. Run:

    python3 test_symlink_imports.py

GH-45. The shared-scripts preamble computed its root from
`os.path.abspath(__file__)`, which normalises a relative path but does not
resolve symlinks. A repository that installs these skills the documented way —
symlinking the skills directory — therefore left `__file__` under its own
tree, and `../../../scripts` landed on a shared-scripts directory that does not
exist there:

    ModuleNotFoundError: No module named 'detex'

Nothing in this repository could catch it. Run from the canonical checkout
there is no symlink to resolve, `abspath` and `realpath` agree, and the suite
passes — the failure needs a second repository consuming the skills, which is
the normal installation and the one nothing exercised. So this test builds that
second repository: a temp directory whose skills directory is a symlink here,
with no shared-scripts directory of its own, and runs the real entry points
through it.

Why it asserts on the message rather than the exit status: several of these
scripts exit non-zero for unrelated reasons (a missing required argument, an
absent Ollama, no API key). A ModuleNotFoundError for a shared module is the
specific failure, and it is unambiguous.

Two kinds of check, because the end-to-end one alone is weaker than it looks.
Most of these scripts import their shared modules lazily, inside the function
that needs them, so running them with --help never reaches the import: against
the original abspath code only ONE of the ten entry points actually failed. The
end-to-end checks still earn their place — they are the real thing, and they
catch a lazy import becoming eager — but the invariant that holds for all 16
affected files is static, so it is asserted statically as well: a file that
computes the shared root must do it from realpath. That is also what fails when
someone adds a seventeenth file by copying an old preamble.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "skills"))

FAILURES = []

# One entry point per skill that reaches the shared directory. Each is invoked
# with an argument that makes it exit early — the import happens at module
# load, before any of this matters.
ENTRY_POINTS = [
    ("filter-tells", "scripts/detect-structural.py", ["--help"]),
    ("filter-tells", "scripts/drive.py", ["--help"]),
    ("audit-references", "scripts/extract_citations.py", ["--help"]),
    ("match-structure", "scripts/style.py", ["--help"]),
    ("match-voice", "scripts/drive.py", ["--help"]),
    ("tighten-style", "scripts/check_style.py", ["--help"]),
    ("tighten-style", "scripts/tighten.py", ["--help"]),
    ("tune-anchors", "scripts/tune_anchors.py", ["--help"]),
    ("update-references", "scripts/scholar.py", ["--help"]),
    ("update-references", "scripts/semantic_scholar.py", ["--help"]),
]


def check(name, condition, detail=""):
    if condition:
        print("  ok    %s" % name)
    else:
        print("  FAIL  %s%s" % (name, ": " + str(detail) if detail else ""))
        FAILURES.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="test-symlink-consumer-")
    try:
        # The consuming repository: skills by symlink, and deliberately no
        # shared-scripts directory of its own. That absence is the point — with
        # abspath the preamble resolves to it and finds nothing.
        claude = os.path.join(tmp, ".claude")
        os.makedirs(claude)
        os.symlink(SKILLS, os.path.join(claude, "skills"))
        check("the consumer has no shared-scripts directory of its own",
              not os.path.exists(os.path.join(claude, "scripts")))

        linked = os.path.join(claude, "skills")
        for skill, rel, args in ENTRY_POINTS:
            script = os.path.join(linked, skill, rel)
            if not os.path.exists(script):
                check("%s/%s exists" % (skill, rel), False, "not found")
                continue
            proc = subprocess.run([sys.executable, script] + args,
                                  capture_output=True, text=True, cwd=tmp)
            out = proc.stdout + proc.stderr
            bad = [l for l in out.splitlines()
                   if "ModuleNotFoundError" in l or "ImportError" in l]
            check("%s/%s imports through the symlink" % (skill, os.path.basename(rel)),
                  not bad, bad[:1])

        # --- the static invariant, which covers all 16 affected files ------ #
        # A file that walks up to the shared directory must start from
        # realpath. abspath leaves a symlinked __file__ in the consumer's tree
        # and the traversal exits the linked subtree, so it cannot come back.
        offenders = []
        for root, _dirs, files in os.walk(SKILLS):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                if '"..", "..", "..", "scripts"' not in text:
                    continue
                if "realpath(__file__)" not in text:
                    offenders.append(os.path.relpath(path, SKILLS))
        check("every file reaching the shared root starts from realpath",
              not offenders,
              "%d using abspath: %s" % (len(offenders), sorted(offenders)[:4]))

        # The arithmetic itself, stated directly: from the symlinked location a
        # shared-root computation must land on a directory that has the shared
        # modules in it.
        sample = os.path.join(linked, "filter-tells", "scripts",
                              "detect-structural.py")
        shared = os.path.normpath(os.path.join(
            os.path.dirname(os.path.realpath(sample)), "..", "..", "..", "scripts"))
        check("realpath from a symlinked script reaches the shared modules",
              os.path.exists(os.path.join(shared, "detex.py")), shared)
        stale = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(sample)), "..", "..", "..", "scripts"))
        check("abspath from the same script does not — the bug this pins",
              not os.path.exists(stale), stale)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print("%d failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all symlink import tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
