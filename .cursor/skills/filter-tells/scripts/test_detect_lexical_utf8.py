#!/usr/bin/env python3
"""Truncation tests for detect-lexical.sh. Run: python3 test_detect_lexical_utf8.py

No corpus, no detectors beyond the script itself, no network — synthetic
documents in a temp directory, each built so a multi-byte character straddles
one of the script's truncation widths.

Covers GH-3: the previews were cut with `head -c`, which counts bytes, so a cut
inside a multi-byte character emitted a partial sequence. The --json output
stopped being valid UTF-8 and drive.py died on it before producing any result,
which read as "the skill does not support Unicode". A byte-based cut is invisible
in ASCII fixtures, so every case here places a non-ASCII character on the cut.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "detect-lexical.sh")

# Widths the script truncates at: JSON hard issue, JSON ordinal, stdout print.
WIDTHS = (200, 160, 120)
FAILURES = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")
        FAILURES.append(name)


def straddle(prefix, width, tail="→ actuation follows."):
    """A line whose `tail` starts one byte before `width`, so a byte-based cut
    at `width` lands inside the multi-byte character that opens it."""
    pad = "x" * (width - 1 - len(prefix.encode("utf-8")))
    return prefix + pad + tail


def run(path, *args, env=None):
    """Run the script, returning (returncode, raw stdout bytes). Never text=True
    — decoding here would hide exactly the defect under test."""
    merged = dict(os.environ)
    merged.update(env or {})
    proc = subprocess.run(["bash", SCRIPT, path, *args],
                          capture_output=True, env=merged)
    return proc.returncode, proc.stdout


def write(tmp, name, body):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Fixture\n\n" + body + "\n")
    return path


def decodes(raw):
    try:
        raw.decode("utf-8")
        return True, ""
    except UnicodeDecodeError as e:
        return False, str(e)


def main():
    tmp = tempfile.mkdtemp(prefix="test-detect-lexical-")
    try:
        # "Crucially," is a false-emphasis tell, so the line is reported and
        # truncated at 200 (JSON) and 120 (stdout).
        for width in WIDTHS:
            doc = write(tmp, f"straddle{width}.md",
                        straddle("Crucially, ", width))

            _, out = run(doc, "--json")
            ok, detail = decodes(out)
            check(f"--json is valid UTF-8 with a character on the {width}-byte cut",
                  ok, detail)

            _, out = run(doc)
            ok, detail = decodes(out)
            check(f"stdout is valid UTF-8 with a character on the {width}-byte cut",
                  ok, detail)

        # The ordinal-sequence path builds its own preview at width 160.
        ordinals = ("First, the loader reads it. Second, the parser walks it. "
                    "Third, the writer emits it. ")
        doc = write(tmp, "ordinals.md", straddle(ordinals, 160))
        _, out = run(doc, "--json")
        ok, detail = decodes(out)
        check("ordinal-sequence preview is valid UTF-8", ok, detail)

        # The findings must survive the fix, not just the encoding.
        doc = write(tmp, "findings.md", straddle("Crucially, ", 200))
        _, out = run(doc, "--json")
        try:
            import json
            found = {f["category"] for f in json.loads(out.decode("utf-8"))}
        except Exception as e:  # noqa: BLE001 - reported, not raised
            found, e_detail = set(), str(e)
        else:
            e_detail = ""
        check("false-emphasis still reported after truncation",
              "false-emphasis" in found, e_detail or str(sorted(found)))

        # The fallback branch, unreachable on a machine that has a UTF-8 locale.
        env = {"FILTER_TELLS_TRUNC_LOCALE": "none"}
        doc = write(tmp, "fallback.md", straddle("Crucially, ", 200))
        _, out = run(doc, "--json", env=env)
        ok, detail = decodes(out)
        check("fallback truncation is valid UTF-8", ok, detail)
        check("fallback truncation drops the partial character",
              "→".encode("utf-8") not in out.split(b'"text"')[1][:260]
              if b'"text"' in out else False)

        # ASCII must be unaffected: a long ASCII line still truncates at exactly
        # 200 characters, so the fix changes encoding safety and nothing else.
        doc = write(tmp, "ascii.md", "Crucially, " + "x" * 400)
        _, out = run(doc, "--json")
        try:
            import json
            texts = [f["text"] for f in json.loads(out.decode("utf-8"))
                     if f["category"] == "false-emphasis"]
        except Exception:  # noqa: BLE001
            texts = []
        check("ASCII preview is exactly 200 characters",
              bool(texts) and len(texts[0]) == 200,
              str(len(texts[0])) if texts else "no false-emphasis finding")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
        return 1
    print("all truncation tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
