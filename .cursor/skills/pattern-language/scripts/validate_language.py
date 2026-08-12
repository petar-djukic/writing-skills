#!/usr/bin/env python3
"""Structural validator (and repair planner) for pattern-language.yaml files.

Enforces the structural half of references/format-spec.md:
- required top-level keys and per-pattern keys
- unique pattern ids and numbers; confidence in {0,1,2}
- grammar references resolve: bare ids to patterns in this file; `prefix:id`
  references allowed only when the file declares `extends`
- every examples[].cite resolves in `bibliography` (skipped when the file
  uses `bibliography_note` to delegate to an external references file)
- consequences carries both benefits and liabilities
- connectivity: no orphan patterns

Repair: `--fix-plan` prints a concrete suggested edit per finding. The script
NEVER writes the file — these files are comment-heavy (the header block IS
comments) and a PyYAML round-trip would destroy them. Apply the plan by
editing the file in place, then re-validate.

Usage: validate_language.py <pattern-language.yaml> [--json] [--fix-plan]
Exit: 0 valid, 1 findings, 2 usage/parse error.
"""

import difflib
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

RELATIONSHIP_TYPES_BLOCK = """\
  relationship_types:
    within: Larger patterns whose context this pattern helps complete.
    requires: Patterns that must already be in place for this one to hold.
    contains: Smaller patterns that complete or refine this one.
    enables: Patterns that this one makes possible.
    overlaps: Patterns that address a neighbouring force by a different means."""

CONFIDENCE_SCALE_BLOCK = """\
  confidence_scale:
    "2": Deep invariant; the same force is resolved the same way across many independent systems and prior literature.
    "1": Well supported by prior art, but the specific form presented here is more recent.
    "0": Tentative; corroboration is thin and the structure is largely from the single reference implementation."""

KEY_SKELETONS = {
    "also_known_as": "also_known_as: []",
    "intent": "intent: >\n      <one sentence: what the pattern does>",
    "context": "context: >\n      <the situation and larger patterns that must exist first>",
    "problem": "problem: >\n      <the headline tension, stated as a question of forces>",
    "forces": "forces:\n      - <pressure one>\n      - <pressure two, in tension with it>",
    "solution": "solution: >\n      Therefore: <imperative resolution>",
    "implementation": "implementation: >\n      <construction rules and checks>",
    "consequences": "consequences:\n      benefits:\n        - <what it buys>\n      liabilities:\n        - <what it costs>",
    "grammar": "grammar:\n      within: []\n      requires: []\n      contains: []\n      enables: []\n      overlaps: []",
    "examples": "examples:\n      - system: <independent system>\n        cite: <bibliography-key>\n        kind: external\n        note: <same forces, same resolution>",
}


def _prose_of(p):
    parts = []
    for k in ("intent", "context", "problem", "solution", "implementation", "syntax"):
        v = p.get(k)
        if isinstance(v, str):
            parts.append(v)
    return " ".join(parts).lower()


def validate(path):
    findings = []  # list of {"msg": ..., "plan": ...}

    def add(msg, plan=None):
        findings.append({"msg": msg, "plan": plan})

    try:
        doc = yaml.safe_load(open(path))
    except Exception as e:  # noqa: BLE001
        return [{"msg": f"PARSE: {e}", "plan": None}], None
    if not isinstance(doc, dict):
        return [{"msg": "PARSE: top level is not a mapping", "plan": None}], None

    for k in TOP_REQUIRED:
        if k not in doc:
            add(f"TOP: missing required key '{k}'",
                f"insert `{k}:` at top level (see assets/template.yaml for its shape)")

    conv = doc.get("conventions") or {}
    if "confidence_scale" not in conv:
        add("CONVENTIONS: missing confidence_scale",
            "insert under `conventions:`:\n" + CONFIDENCE_SCALE_BLOCK)
    if "relationship_types" not in conv:
        add("CONVENTIONS: missing relationship_types",
            "insert under `conventions:`:\n" + RELATIONSHIP_TYPES_BLOCK)

    patterns = doc.get("patterns") or []
    if not isinstance(patterns, list) or not patterns:
        add("PATTERNS: empty or not a list",
            "add a `patterns:` list; copy an entry from assets/template.yaml")
        return findings, doc

    has_extends = bool(doc.get("extends"))
    bib = doc.get("bibliography")
    bib_delegated = "bibliography_note" in doc and bib is None
    if bib is None and not bib_delegated:
        add("TOP: no bibliography and no bibliography_note",
            "add `bibliography:` (key -> {text, url?}) or `bibliography_note:` "
            "delegating to the repo's references file")

    ids, numbers = set(), set()
    for p in patterns:
        pid = p.get("id", "<missing-id>")
        for k in ENTRY_REQUIRED:
            if k not in p:
                plan = f"insert into the entry:\n{KEY_SKELETONS.get(k, k + ': <fill>')}"
                if k in ("forces", "consequences"):
                    plan += ("\n(content repair: forces/consequences need mining, "
                             "not boilerplate — see references/mining-guide.md)")
                add(f"{pid}: missing key '{k}'", plan)
        if "id" in p:
            if not ID_RE.match(str(p["id"])):
                kebab = re.sub(r"[^a-z0-9]+", "-", str(p["id"]).lower()).strip("-")
                add(f"{pid}: id is not kebab-case",
                    f"rename id to '{kebab}' and update every grammar reference to it")
            if p["id"] in ids:
                add(f"{pid}: duplicate id", "give one of the entries a distinct id")
            ids.add(p["id"])
        if "number" in p:
            if p["number"] in numbers:
                add(f"{pid}: duplicate number {p['number']}",
                    "renumber; numbers are the reading order (larger context "
                    "first), ids are the stable keys")
            numbers.add(p["number"])
        if p.get("confidence") not in (0, 1, 2):
            add(f"{pid}: confidence must be 0, 1, or 2 (got {p.get('confidence')!r})",
                "score from the external examples count: many independent -> 2; "
                "prior art but newer form -> 1; mostly reference impl -> 0")
        forces = p.get("forces") or []
        if isinstance(forces, list) and len(forces) < 2:
            add(f"{pid}: fewer than 2 forces — where is the tension?",
                "content repair: mine the competing pressures "
                "(references/mining-guide.md); do not pad with boilerplate")
        cons = p.get("consequences") or {}
        if not (isinstance(cons, dict) and cons.get("benefits") and cons.get("liabilities")):
            add(f"{pid}: consequences must carry both benefits and liabilities",
                "content repair: a pattern with no liabilities is advertising — "
                "name the cost (see mining-guide disqualifiers)")

    referenced = set()
    for p in patterns:
        pid = p.get("id", "<missing-id>")
        g = p.get("grammar") or {}
        for k in GRAMMAR_KEYS:
            if k not in g:
                add(f"{pid}: grammar missing '{k}'", f"insert `{k}: []` under grammar")
            for ref in (g.get(k) or []):
                ref = str(ref)
                if PREFIXED_RE.match(ref):
                    if not has_extends:
                        add(f"{pid}: prefixed reference '{ref}' but no `extends` declared",
                            "add a top-level `extends:` naming the sibling "
                            "language and its prefix (see format-spec.md)")
                elif ref not in ids:
                    close = difflib.get_close_matches(ref, ids, n=2)
                    add(f"{pid}: grammar.{k} references unknown id '{ref}'",
                        (f"did you mean {close}? " if close else "")
                        + "fix the reference or add the missing pattern")
                else:
                    referenced.add(ref)
        if any(g.get(k) for k in GRAMMAR_KEYS):
            referenced.add(p.get("id"))

        for ex in (p.get("examples") or []):
            if not isinstance(ex, dict):
                add(f"{pid}: example is not a mapping",
                    "each example is {system?, cite, kind, note}")
                continue
            for k in ("cite", "kind", "note"):
                if k not in ex:
                    add(f"{pid}: example missing '{k}'",
                        f"add `{k}:` to the example entry")
            # `system` is recommended; when absent the cite carries the
            # identity (ieee-tse style), so its absence alone is not a finding.
            if ex.get("kind") not in ("external", "internal", "sibling", None):
                add(f"{pid}: example kind '{ex.get('kind')}' not external|internal|sibling",
                    "use kind: external (recurrence evidence), internal "
                    "(reference impl), or sibling (another language's pattern)")
            cite = ex.get("cite")
            if cite and not bib_delegated and isinstance(bib, dict) and cite not in bib:
                close = difflib.get_close_matches(cite, list(bib.keys()), n=2)
                add(f"{pid}: cite '{cite}' not in bibliography",
                    (f"did you mean {close}? " if close else "")
                    + f"or insert under `bibliography:`:\n{cite}:\n"
                      "  text: \"<Author (Year). Title. Venue.>\"")

    orphans = (ids - referenced) if len(patterns) > 1 else set()
    by_id = {p.get("id"): p for p in patterns}
    for o in sorted(orphans):
        # grammar-wiring candidates: patterns whose prose mentions the orphan
        name_words = (by_id.get(o, {}).get("name", "") or o).lower()
        mentions = [p.get("id") for p in patterns
                    if p.get("id") != o and
                    (name_words in _prose_of(p) or o.replace("-", " ") in _prose_of(p))]
        add(f"{o}: orphan — appears in no grammar relation (its own or another pattern's)",
            (f"candidate connections — these patterns mention it: {mentions}; "
             if mentions else "")
            + "wire it via within/requires/contains/enables/overlaps, or drop it "
              "from the language (a pattern that connects to nothing is either "
              "the root or not part of the language)")

    return findings, doc


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    json_mode = "--json" in sys.argv
    fix_plan = "--fix-plan" in sys.argv
    if len(args) != 1:
        sys.exit(f"Usage: {sys.argv[0]} <pattern-language.yaml> [--json] [--fix-plan]")
    findings, doc = validate(args[0])
    n = len((doc or {}).get("patterns") or [])
    if json_mode:
        out = {"file": args[0], "patterns": n,
               "findings": [f["msg"] for f in findings]}
        if fix_plan:
            out["fix_plan"] = findings
        print(json.dumps(out, indent=2))
    else:
        print(f"{args[0]}: {n} patterns, {len(findings)} finding(s)")
        for f in findings:
            print(f"  - {f['msg']}")
            if fix_plan and f.get("plan"):
                for line in f["plan"].split("\n"):
                    print(f"      | {line}")
        if not findings:
            print("  valid")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
