#!/usr/bin/env python3
"""Venue profiles: named parameter bundles that make the prose skills reusable
across publishing venues (newsletter, technical essay, book, industry report,
academic paper).

A profile is one YAML file under `writing-voice/venues/`. It bundles every
choice the humanize pipeline otherwise asks for interactively: anchor query,
blueprint, structural step, register targets, citation format, tell lexicon,
and the gate list. The schema is documented in the repository rule
`writing-voice.md`, section "venues/ — venue profiles"; that
rule is the contract, this script is the loader and validator every consumer
skill (humanize, filter-tells, tighten-style, match-voice/match-outline)
imports or shells out to.

Profiles are named bundles, not a linear dial: register axes do not move
together across venues (the book profile removes all hedging while the
academic profile carries the most), so consumers must read fields, never
infer them from `level`.

Usage:
  venue_profile.py discover <file>                    # find writing-voice/venues/
  venue_profile.py list   [--voice-dir D | --for F]   # available venue names
  venue_profile.py show   --venue NAME [--voice-dir D | --for F]
  venue_profile.py validate <profile.yaml> [...]
  venue_profile.py bootstrap [--voice-dir D | --for F]
                             [--role R] [--tags a,b] [--stratum pre-ai|ai-era]
                             [--files f.md ...] [--venue NAME --write]
  venue_profile.py set-anchors --venue NAME [--voice-dir D | --for F]
                               (--arm "tags~clipped" | --role R --tags a,b ...)
                               [--composite X] [--note "..."]

`bootstrap` (GH-339) measures a corpus slice with match-structure's metrics
and emits the profile's `targets` block — profiles are measured, never
hand-written. `set-anchors` records a winning tune-anchors arm (or a hand
query) into the profile's `anchor_query` with provenance.
"""

import argparse
import json
import os
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required (pixi env supplies it).")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voice_anchors as va  # noqa: E402
import style  # noqa: E402

VENUES_SUBDIR = "venues"

STRUCTURAL_STEPS = {"match-outline", "tighten-style", "skip"}
CITATION_STYLES = {"numbered", "pandoc", "none"}
HEDGE_POLICIES = {"zero", "minimal", "calibrated"}
POV_VALUES = {"first-person", "third-person", "mixed-sidebars"}
TELL_LEXICONS = {"newsletter", "academic", "industry", "book", "none"}
GATE_NAMES = {"pangram", "pace", "register-composite",
              "citation-number-preservation", "audit-references"}
ROLES = {"author-voice", "venue-voice"}
STRATA = {"pre-ai", "ai-era"}

REQUIRED_FIELDS = ("name", "level", "structural_step", "citations",
                   "tell_lexicon", "hedge_policy", "gates")


# --- discovery ---------------------------------------------------------------

def venues_dir(voice_dir):
    return os.path.join(voice_dir, VENUES_SUBDIR)


def list_venues(voice_dir):
    d = venues_dir(voice_dir)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(d)
                  if f.endswith(".yaml") and not f.startswith("."))


def find_profile(start_path, venue):
    """Walk up from a file to writing-voice/venues/<venue>.yaml. None if absent.

    Reuses the writing-voice discovery rule, so a paper repository carrying its
    own writing-voice/venues/ resolves without any cross-repo configuration.
    """
    voice_dir = va.discover(start_path)
    if not voice_dir:
        return None
    cand = os.path.join(venues_dir(voice_dir), venue + ".yaml")
    return cand if os.path.exists(cand) else None


# --- loading and validation --------------------------------------------------

def load_profile(path):
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: profile must be a YAML mapping")
    data["_path"] = os.path.abspath(path)
    data["_voice_dir"] = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    return data


def normalize_gates(gates):
    """Gates may be bare names or mappings with a name key; return mappings."""
    out = []
    for g in gates or []:
        if isinstance(g, str):
            out.append({"name": g})
        elif isinstance(g, dict) and "name" in g:
            out.append(g)
        else:
            out.append({"name": None, "_raw": g})
    return out


def validate_profile(data, manifest=None):
    """Return (errors, warnings). Errors block use; warnings are advisory."""
    errors, warnings = [], []

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    if "level" in data and data["level"] not in (1, 2, 3, 4, 5):
        errors.append(f"level must be 1-5, got {data['level']!r}")
    if data.get("structural_step") not in STRUCTURAL_STEPS | {None}:
        errors.append(f"structural_step must be one of {sorted(STRUCTURAL_STEPS)}")
    if data.get("citations") not in CITATION_STYLES | {None}:
        errors.append(f"citations must be one of {sorted(CITATION_STYLES)}")
    if data.get("hedge_policy") not in HEDGE_POLICIES | {None}:
        errors.append(f"hedge_policy must be one of {sorted(HEDGE_POLICIES)}")
    if data.get("tell_lexicon") not in TELL_LEXICONS | {None}:
        errors.append(f"tell_lexicon must be one of {sorted(TELL_LEXICONS)}")
    if "pov" in data and data["pov"] not in POV_VALUES:
        errors.append(f"pov must be one of {sorted(POV_VALUES)}")

    for g in normalize_gates(data.get("gates")):
        if not g.get("name"):
            errors.append(f"unreadable gate entry: {g.get('_raw')!r}")
        elif g["name"] not in GATE_NAMES:
            errors.append(f"unknown gate: {g['name']!r} "
                          f"(known: {sorted(GATE_NAMES)})")

    aq = data.get("anchor_query")
    if aq is not None:
        if not isinstance(aq, dict):
            errors.append("anchor_query must be a mapping")
        else:
            if aq.get("role") and aq["role"] not in ROLES:
                errors.append(f"anchor_query.role must be one of {sorted(ROLES)}")
            if aq.get("stratum") and aq["stratum"] not in STRATA:
                errors.append(f"anchor_query.stratum must be one of {sorted(STRATA)}")
            tags = aq.get("tags")
            if tags is not None and (not isinstance(tags, list)
                                     or not all(isinstance(t, str) for t in tags)):
                errors.append("anchor_query.tags must be a list of strings")
            elif tags and manifest is not None:
                known = {str(t).lower() for ex in manifest
                         for t in (ex.get("tags") or [])}
                for t in tags:
                    if t.lower() not in known:
                        warnings.append(f"anchor_query tag matches no exemplar: {t!r}")

    targets = data.get("targets")
    if targets is not None:
        if not isinstance(targets, dict):
            errors.append("targets must be a mapping of metric -> number")
        else:
            for k, v in targets.items():
                if k not in style.METRIC_KEYS:
                    warnings.append(f"targets key not a match-structure metric: {k!r}")
                elif not isinstance(v, (int, float)):
                    errors.append(f"targets.{k} must be a number, got {v!r}")

    bp = data.get("blueprint")
    if bp and data.get("_voice_dir"):
        bp_path = os.path.join(data["_voice_dir"], "blueprints", bp)
        if not os.path.exists(bp_path):
            warnings.append(f"blueprint file not found: {bp_path}")

    return errors, warnings


def resolve(start_path=None, voice_dir=None, venue=None):
    """Load and validate a profile for a consumer. Raises on errors.

    Either start_path (walk-up discovery) or voice_dir must be given.
    """
    if voice_dir is None:
        if start_path is None:
            raise ValueError("need start_path or voice_dir")
        voice_dir = va.discover(start_path)
        if not voice_dir:
            raise FileNotFoundError(f"no writing-voice/ above {start_path}")
    path = os.path.join(venues_dir(voice_dir), venue + ".yaml")
    if not os.path.exists(path):
        avail = list_venues(voice_dir)
        raise FileNotFoundError(
            f"no venue profile {venue!r} in {venues_dir(voice_dir)} "
            f"(available: {avail or 'none'})")
    data = load_profile(path)
    manifest = va.load_manifest(voice_dir)
    errors, warnings = validate_profile(data, manifest=manifest)
    if errors:
        raise ValueError(f"{path}: " + "; ".join(errors))
    data["gates"] = normalize_gates(data.get("gates"))
    data["_warnings"] = warnings
    return data


# --- bootstrap: measured targets (GH-339) ------------------------------------

def bootstrap_targets(voice_dir=None, role=None, tags=None, stratum=None,
                      files=None):
    """Measure a corpus slice and return the profile's targets block.

    Returns a dict with targets / targets_std / targets_provenance keys, ready
    to merge into a venue profile. Selection is either an explicit file list
    or a manifest query (role/tags/stratum) against voice_dir.
    """
    import datetime
    if files:
        paths = [os.path.abspath(f) for f in files]
        corpus_desc = {"files": len(paths)}
    else:
        if not voice_dir:
            raise ValueError("need --voice-dir/--for or --files")
        pre_ai = None if stratum is None else (stratum == "pre-ai")
        selected = style.select_voice_corpus(
            voice_dir, role=role, tags=tags, pre_ai=pre_ai)
        paths = [p for _, p in selected]
        corpus_desc = {k: v for k, v in
                       (("role", role), ("tags", tags), ("stratum", stratum))
                       if v}
    if not paths:
        raise ValueError("corpus selection matched no files")

    profiles = [style.profile_file(p) for p in paths]
    agg = style.aggregate(profiles)
    targets = {k: v for k, v in agg["metrics"].items() if v is not None}
    targets_std = {k: v for k, v in agg["metrics_std"].items()
                   if v is not None}
    return {
        "targets": targets,
        "targets_std": targets_std,
        "targets_provenance": {
            "measured": datetime.date.today().isoformat(),
            "corpus": corpus_desc,
            "papers": len(paths),
            "total_words": agg["total_words"],
        },
    }


def merge_into_profile(path, updates):
    """Merge top-level keys into a profile YAML file, preserving the rest."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    data.update(updates)
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    with open(path, "w") as f:
        yaml.safe_dump(clean, f, sort_keys=False, allow_unicode=True)
    return clean


def arm_to_anchor_query(exprs):
    """Translate tune-anchors arm expressions into an anchor_query mapping.

    Reuses tune-anchors' own parser so the syntax cannot drift; pre_ai
    arms map onto the profile's stratum field.
    """
    ta = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "tune-anchors", "scripts"))
    if ta not in sys.path:
        sys.path.insert(0, ta)
    import ledger
    q = {}
    for expr in exprs:
        kw = ledger.parse_arm(expr)
        if "pre_ai" in kw:
            q["stratum"] = "pre-ai" if kw["pre_ai"] else "ai-era"
        if "role" in kw:
            q["role"] = kw["role"]
        if "tags" in kw:
            q.setdefault("tags", []).extend(kw["tags"])
    return q


# --- CLI ---------------------------------------------------------------------

def _voice_dir_from_args(args):
    if getattr(args, "voice_dir", None):
        return args.voice_dir
    if getattr(args, "for_file", None):
        d = va.discover(args.for_file)
        if not d:
            sys.exit(f"no writing-voice/ above {args.for_file}")
        return d
    sys.exit("need --voice-dir or --for")


def cmd_discover(args):
    voice_dir = va.discover(args.file)
    if not voice_dir:
        sys.exit(f"no writing-voice/ above {args.file}")
    print(json.dumps({"voice_dir": voice_dir,
                      "venues_dir": venues_dir(voice_dir),
                      "venues": list_venues(voice_dir)}, indent=2))


def cmd_list(args):
    voice_dir = _voice_dir_from_args(args)
    print(json.dumps({"voice_dir": voice_dir,
                      "venues": list_venues(voice_dir)}, indent=2))


def cmd_show(args):
    voice_dir = _voice_dir_from_args(args)
    try:
        data = resolve(voice_dir=voice_dir, venue=args.venue)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(str(e))
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_validate(args):
    failed = False
    for path in args.files:
        try:
            data = load_profile(path)
        except Exception as e:
            print(json.dumps({"file": path, "errors": [str(e)]}))
            failed = True
            continue
        voice_dir = data.get("_voice_dir")
        manifest = va.load_manifest(voice_dir) if voice_dir and os.path.isdir(
            voice_dir) else None
        errors, warnings = validate_profile(data, manifest=manifest)
        print(json.dumps({"file": path, "errors": errors,
                          "warnings": warnings}, indent=2))
        failed = failed or bool(errors)
    sys.exit(1 if failed else 0)


def cmd_bootstrap(args):
    voice_dir = None
    if args.voice_dir or args.for_file:
        voice_dir = _voice_dir_from_args(args)
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    try:
        block = bootstrap_targets(voice_dir=voice_dir, role=args.role,
                                  tags=tags, stratum=args.stratum,
                                  files=args.files)
    except ValueError as e:
        sys.exit(str(e))

    if args.write:
        if not args.venue:
            sys.exit("--write requires --venue")
        path = os.path.join(venues_dir(voice_dir), args.venue + ".yaml")
        if not os.path.exists(path):
            sys.exit(f"profile does not exist yet: {path} — author the "
                     f"profile first, then bootstrap its targets")
        merged = merge_into_profile(path, block)
        errors, warnings = validate_profile(
            dict(merged, _voice_dir=voice_dir),
            manifest=va.load_manifest(voice_dir))
        print(json.dumps({"written": path,
                          "papers": block["targets_provenance"]["papers"],
                          "errors": errors, "warnings": warnings}, indent=2))
        sys.exit(1 if errors else 0)
    print(yaml.safe_dump(block, sort_keys=False, allow_unicode=True))


def cmd_set_anchors(args):
    voice_dir = _voice_dir_from_args(args)
    path = os.path.join(venues_dir(voice_dir), args.venue + ".yaml")
    if not os.path.exists(path):
        sys.exit(f"no venue profile {args.venue!r} in {venues_dir(voice_dir)} "
                 f"(available: {list_venues(voice_dir) or 'none'})")

    import datetime
    if args.arm:
        try:
            q = arm_to_anchor_query(args.arm)
        except ValueError as e:
            sys.exit(f"bad arm expression: {e}")
        source = "tune-anchors"
    else:
        q = {}
        if args.role:
            q["role"] = args.role
        if args.tags:
            q["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
        if args.stratum:
            q["stratum"] = args.stratum
        if args.author:
            q["author"] = args.author
        if not q:
            sys.exit("nothing to record: give --arm or at least one of "
                     "--role/--tags/--stratum/--author")
        source = "hand"

    provenance = {"anchor_query_source": source,
                  "swept": datetime.date.today().isoformat()}
    if args.composite is not None:
        provenance["composite"] = args.composite
    if args.note:
        provenance["note"] = args.note

    merged = merge_into_profile(path, {"anchor_query": q,
                                       "provenance": provenance})
    errors, warnings = validate_profile(
        dict(merged, _voice_dir=voice_dir),
        manifest=va.load_manifest(voice_dir))
    print(json.dumps({"written": path, "anchor_query": q,
                      "provenance": provenance,
                      "errors": errors, "warnings": warnings}, indent=2))
    sys.exit(1 if errors else 0)


def main():
    p = argparse.ArgumentParser(description="Venue profile loader/validator")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="find writing-voice/venues/ from a file")
    d.add_argument("file")
    d.set_defaults(fn=cmd_discover)

    ls = sub.add_parser("list", help="list available venue profiles")
    ls.add_argument("--voice-dir")
    ls.add_argument("--for", dest="for_file")
    ls.set_defaults(fn=cmd_list)

    sh = sub.add_parser("show", help="load, validate, and print one profile")
    sh.add_argument("--venue", required=True)
    sh.add_argument("--voice-dir")
    sh.add_argument("--for", dest="for_file")
    sh.set_defaults(fn=cmd_show)

    v = sub.add_parser("validate", help="validate profile files")
    v.add_argument("files", nargs="+")
    v.set_defaults(fn=cmd_validate)

    b = sub.add_parser("bootstrap",
                       help="measure a corpus slice, emit the targets block")
    b.add_argument("--voice-dir")
    b.add_argument("--for", dest="for_file")
    b.add_argument("--role", choices=sorted(ROLES))
    b.add_argument("--tags", help="comma-separated register tags")
    b.add_argument("--stratum", choices=sorted(STRATA))
    b.add_argument("--files", nargs="+",
                   help="explicit file list instead of a manifest query")
    b.add_argument("--venue", help="profile name for --write")
    b.add_argument("--write", action="store_true",
                   help="merge the block into venues/<venue>.yaml")
    b.set_defaults(fn=cmd_bootstrap)

    sa = sub.add_parser("set-anchors",
                        help="record an anchor query into a profile")
    sa.add_argument("--venue", required=True)
    sa.add_argument("--voice-dir")
    sa.add_argument("--for", dest="for_file")
    sa.add_argument("--arm", action="append",
                    help="tune-anchors arm expression (repeatable); "
                         "e.g. tags~clipped, role=venue-voice, pre_ai=true")
    sa.add_argument("--role", choices=sorted(ROLES))
    sa.add_argument("--tags", help="comma-separated register tags")
    sa.add_argument("--stratum", choices=sorted(STRATA))
    sa.add_argument("--author")
    sa.add_argument("--composite", type=float,
                    help="register composite of the winning arm (from rank)")
    sa.add_argument("--note", help="free-text provenance note")
    sa.set_defaults(fn=cmd_set_anchors)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
