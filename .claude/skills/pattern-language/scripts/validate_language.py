#!/usr/bin/env python3
"""Structural validator for pattern-language.yaml files.

Enforces the structural half of references/format-spec.md:
- required top-level keys and per-pattern keys
- unique pattern ids and numbers; confidence in {0,1,2}
- grammar references resolve: bare ids to patterns in this file; `prefix:id`
  references allowed only when the file declares `extends`
- every examples[].cite resolves in `bibliography` (skipped when the file
  uses `bibliography_note` to delegate to an external references file)
- consequences carries both benefits and liabilities
- connectivity: no orphan patterns (every pattern appears in at least one
  grammar relation, its own or another's)

Usage: validate_language.py <pattern-language.yaml> [--json]
Exit: 0 valid, 1 findings, 2 usage/parse error.
"""

import json
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required (pixi env supplies it).")

TOP_REQUIRED = ["title", "version", "based_on", "conventions", "patterns"]
ENTRY_REQUIRED = [
    "id", "number", "name", "confidence", "intent", "context", "problem",
    "forces", "solution", "consequences", "grammar", "examples",
]
GRAMMAR_KEYS = ["within", "requires", "contains", "enables", "overlaps"]
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PREFIXED_RE = re.compile(r"^[a-z0-9]+:[a-z0-9-]+$")


def validate(path):
    findings = []
    try:
        doc = yaml.safe_load(open(path))
    except Exception as e:  # noqa: BLE001
        return [f"PARSE: {e}"], None
    if not isinstance(doc, dict):
        return ["PARSE: top level is not a mapping"], None

    for k in TOP_REQUIRED:
        if k not in doc:
            findings.append(f"TOP: missing required key '{k}'")

    conv = doc.get("conventions") or {}
    if "confidence_scale" not in conv:
        findings.append("CONVENTIONS: missing confidence_scale")
    if "relationship_types" not in conv:
        findings.append("CONVENTIONS: missing relationship_types")

    patterns = doc.get("patterns") or []
    if not isinstance(patterns, list) or not patterns:
        findings.append("PATTERNS: empty or not a list")
        return findings, doc

    has_extends = bool(doc.get("extends"))
    bib = doc.get("bibliography")
    bib_delegated = "bibliography_note" in doc and bib is None
    if bib is None and not bib_delegated:
        findings.append("TOP: no bibliography and no bibliography_note")

    ids, numbers = set(), set()
    for p in patterns:
        pid = p.get("id", "<missing-id>")
        for k in ENTRY_REQUIRED:
            if k not in p:
                findings.append(f"{pid}: missing key '{k}'")
        if "id" in p:
            if not ID_RE.match(str(p["id"])):
                findings.append(f"{pid}: id is not kebab-case")
            if p["id"] in ids:
                findings.append(f"{pid}: duplicate id")
            ids.add(p["id"])
        if "number" in p:
            if p["number"] in numbers:
                findings.append(f"{pid}: duplicate number {p['number']}")
            numbers.add(p["number"])
        if p.get("confidence") not in (0, 1, 2):
            findings.append(f"{pid}: confidence must be 0, 1, or 2 "
                            f"(got {p.get('confidence')!r})")
        forces = p.get("forces") or []
        if isinstance(forces, list) and len(forces) < 2:
            findings.append(f"{pid}: fewer than 2 forces — where is the tension?")
        cons = p.get("consequences") or {}
        if not (isinstance(cons, dict) and cons.get("benefits") and cons.get("liabilities")):
            findings.append(f"{pid}: consequences must carry both benefits and liabilities")

    referenced = set()
    for p in patterns:
        pid = p.get("id", "<missing-id>")
        g = p.get("grammar") or {}
        for k in GRAMMAR_KEYS:
            if k not in g:
                findings.append(f"{pid}: grammar missing '{k}'")
            for ref in (g.get(k) or []):
                ref = str(ref)
                if PREFIXED_RE.match(ref):
                    if not has_extends:
                        findings.append(
                            f"{pid}: prefixed reference '{ref}' but no `extends` declared")
                elif ref not in ids:
                    findings.append(f"{pid}: grammar.{k} references unknown id '{ref}'")
                else:
                    referenced.add(ref)
        if any(g.get(k) for k in GRAMMAR_KEYS):
            referenced.add(p.get("id"))

        for ex in (p.get("examples") or []):
            if not isinstance(ex, dict):
                findings.append(f"{pid}: example is not a mapping")
                continue
            for k in ("cite", "kind", "note"):
                if k not in ex:
                    findings.append(f"{pid}: example missing '{k}'")
            # `system` is recommended; when absent the cite carries the
            # identity (ieee-tse style), so its absence alone is not a finding.
            if ex.get("kind") not in ("external", "internal", "sibling", None):
                findings.append(f"{pid}: example kind '{ex.get('kind')}' not "
                                "external|internal|sibling")
            cite = ex.get("cite")
            if cite and not bib_delegated and isinstance(bib, dict) and cite not in bib:
                findings.append(f"{pid}: cite '{cite}' not in bibliography")

    orphans = ids - referenced if len(patterns) > 1 else set()
    for o in sorted(orphans):
        findings.append(f"{o}: orphan — appears in no grammar relation "
                        "(its own or another pattern's)")

    return findings, doc


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    json_mode = "--json" in sys.argv
    if len(args) != 1:
        sys.exit(f"Usage: {sys.argv[0]} <pattern-language.yaml> [--json]")
    findings, doc = validate(args[0])
    n = len((doc or {}).get("patterns") or [])
    if json_mode:
        print(json.dumps({"file": args[0], "patterns": n,
                          "findings": findings}, indent=2))
    else:
        print(f"{args[0]}: {n} patterns, {len(findings)} finding(s)")
        for f in findings:
            print(f"  - {f}")
        if not findings:
            print("  valid")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
