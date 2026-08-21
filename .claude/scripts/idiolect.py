#!/usr/bin/env python3
"""Shared idiolect.yaml access for the voice skills (GH-63).

One walk-up, one bank parser, one tolerance constant. Before this module,
inject-vernacular, voice-critic, and filter-tells' structural pass each
carried a private copy of the same three helpers — the divergent-splitters
bug class md_paragraphs.py documents, one directory over: a copy that
drifts changes which markers a consumer sees, and nobody audits the
drift. The bank's schema is owned by the Phase-1 extraction
(paper-stash); this module owns reading it.

Library:
  TOLERANCE                  the bank's essay_target_rule: +/-30% before
                             an operator or a calibrated flag fires
  discover_voice_dir(path)   walk up for writing-voice/; None if absent
  load_markers(voice_dir)    idiolect.yaml markers as {id: marker}, or
                             None when the dir or file is absent; parse
                             errors propagate (missing is a normal state,
                             malformed is not)
  compile_marker(marker)     the marker's regex field with its prose
                             annotation stripped; None when the field is
                             a description rather than a pattern
  load_calibration(voice_dir) author ceilings for filter-tells'
                             structural pass, or None

Policy stays with the consumers: inject-vernacular refuses to run
without a bank, voice-critic degrades that marker profile to a flag, and
filter-tells treats absence as the flat-threshold baseline. This module
only answers "what does the bank say".
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TOLERANCE = 0.30  # idiolect essay_target_rule: "+/-30% before an operator fires"


def discover_voice_dir(start_path):
    """Walk up from a file (or dir) looking for writing-voice/. None if
    absent — the same rule as match-structure's voice_anchors.discover."""
    d = os.path.abspath(str(start_path))
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        cand = os.path.join(d, "writing-voice")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_markers(voice_dir):
    """idiolect.yaml's markers as {id: marker}, or None when the directory
    or file is absent. An empty markers list returns {} (falsy) so callers
    can distinguish "no bank" from "bank with nothing in it"."""
    if not voice_dir:
        return None
    path = os.path.join(voice_dir, "idiolect.yaml")
    if not os.path.exists(path):
        return None
    import yaml
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {m["id"]: m for m in data.get("markers", [])}


def compile_marker(marker):
    """The bank's regex field, annotations stripped. The field carries
    prose notes after the pattern (" (case-insensitive; ...)"), and for
    some markers is a description with no pattern at all
    (sentence-length) — those return None."""
    spec = marker.get("regex", "")
    base, _, note = spec.partition(" (")
    flags = re.IGNORECASE if "case-insensitive" in note else 0
    try:
        return re.compile(base, flags)
    except re.error:
        return None


def load_calibration(voice_dir):
    """Author ceilings for filter-tells' structural pass, or None.

    Only markers present in the bank contribute — the idiolect's marker
    list drives the calibrated set. Mapping: colon-verdict -> colon
    density, em-dash -> dash density, antithesis-not -> the antithesis
    detector family. Missing or unparseable means no calibration, which
    is the unchanged flat-threshold behaviour, not an error.
    """
    try:
        markers = load_markers(voice_dir)
    except Exception:
        return None
    if not markers:
        return None
    cal = {"source": os.path.join(voice_dir, "idiolect.yaml")}
    for mid, key in (("colon-verdict", "colon_max_per_500"),
                     ("em-dash", "dash_max_per_500")):
        t = markers.get(mid, {}).get("essay_target")
        if isinstance(t, (int, float)):
            # bank rates are per 1000 words; the densities are per 500.
            cal[key] = t * (1 + TOLERANCE) / 2.0
    t = markers.get("antithesis-not", {}).get("essay_target")
    if isinstance(t, (int, float)):
        cal["antithesis_target_per_1000"] = t
        cal["antithesis_max_per_1000"] = t * (1 + TOLERANCE)
    return cal if len(cal) > 1 else None
