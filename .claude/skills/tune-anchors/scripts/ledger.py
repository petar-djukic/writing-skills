#!/usr/bin/env python3
"""Ledger schema and arm parser for tune-anchors.

An arm is a selection query over the writing-voice manifest — a set of kwargs
for voice_anchors.sample_paths(). Arms are expressed as short strings so the
CLI can accept them as comma-separated positional arguments:

  role=venue-voice         hard filter to one role
  pre_ai=true             restrict to diction-safe samples
  tags~clipped,economics  require at least one of these register tags

The ledger accumulates trial results across sessions so a corpus comparison
builds incrementally rather than requiring one monolithic run.

Usage as a library:
  from ledger import parse_arm, Ledger
"""

import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required (pixi env supplies it).")


# --- arm parsing -------------------------------------------------------------

_ARM_RE = re.compile(r"^(\w+)\s*([=~])\s*(.+)$")

VALID_KEYS = {"role", "pre_ai", "tags"}


def parse_arm(expr: str) -> dict:
    """Parse an arm expression into voice_anchors.sample_paths kwargs.

    Supported forms:
      role=venue-voice    -> {"role": "venue-voice"}
      role=author-voice   -> {"role": "author-voice"}
      pre_ai=true         -> {"pre_ai": True}
      pre_ai=false        -> {"pre_ai": False}
      tags~clipped        -> {"tags": ["clipped"]}
      tags~clipped,econ   -> {"tags": ["clipped", "econ"]}

    Returns a dict suitable for passing as **kwargs to sample_paths (with the
    keys it expects: role, pre_ai, tags).
    """
    expr = expr.strip()
    if not expr:
        raise ValueError("empty arm expression")
    m = _ARM_RE.match(expr)
    if not m:
        raise ValueError(f"cannot parse arm expression: {expr!r} "
                         f"(expected key=value or key~value)")
    key, op, val = m.group(1), m.group(2), m.group(3).strip()
    if key not in VALID_KEYS:
        raise ValueError(f"unknown arm key {key!r} (valid: {sorted(VALID_KEYS)})")

    if key == "role":
        if op != "=":
            raise ValueError(f"role requires '=' operator, got '{op}'")
        if val not in ("author-voice", "venue-voice"):
            raise ValueError(f"role must be author-voice or venue-voice, got {val!r}")
        return {"role": val}

    if key == "pre_ai":
        if op != "=":
            raise ValueError(f"pre_ai requires '=' operator, got '{op}'")
        if val.lower() in ("true", "1", "yes"):
            return {"pre_ai": True}
        if val.lower() in ("false", "0", "no"):
            return {"pre_ai": False}
        raise ValueError(f"pre_ai must be true or false, got {val!r}")

    if key == "tags":
        if op != "~":
            raise ValueError(f"tags requires '~' operator (contains), got '{op}'")
        tags = [t.strip() for t in val.split(",") if t.strip()]
        if not tags:
            raise ValueError("tags~ requires at least one tag")
        return {"tags": tags}

    raise ValueError(f"unhandled key {key!r}")


def parse_arms(exprs):
    """Parse a list of arm expression strings. Returns [(label, kwargs)]."""
    out = []
    for expr in exprs:
        kwargs = parse_arm(expr)
        out.append((expr.strip(), kwargs))
    return out


# --- ledger schema -----------------------------------------------------------

class Trial:
    """One (article, arm, run) entry in the ledger."""

    __slots__ = ("article", "arm", "model", "dry_run", "anchor_count",
                 "pool_size", "register_markers", "structural_metrics",
                 "detector_result", "draft_path")

    def __init__(self, article, arm, model=None, dry_run=False,
                 anchor_count=0, pool_size=0,
                 register_markers=None, structural_metrics=None,
                 detector_result=None, draft_path=None):
        self.article = article
        self.arm = arm
        self.model = model
        self.dry_run = dry_run
        self.anchor_count = anchor_count
        self.pool_size = pool_size
        self.register_markers = register_markers or {}
        self.structural_metrics = structural_metrics or {}
        self.detector_result = detector_result
        self.draft_path = draft_path

    def to_dict(self):
        d = {
            "article": self.article,
            "arm": self.arm,
            "model": self.model,
            "dry_run": self.dry_run,
            "anchor_count": self.anchor_count,
            "pool_size": self.pool_size,
        }
        if self.register_markers:
            d["register_markers"] = dict(self.register_markers)
        if self.structural_metrics:
            d["structural_metrics"] = dict(self.structural_metrics)
        if self.detector_result is not None:
            d["detector_result"] = self.detector_result
        if self.draft_path:
            d["draft_path"] = self.draft_path
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            article=d["article"],
            arm=d["arm"],
            model=d.get("model"),
            dry_run=d.get("dry_run", False),
            anchor_count=d.get("anchor_count", 0),
            pool_size=d.get("pool_size", 0),
            register_markers=d.get("register_markers"),
            structural_metrics=d.get("structural_metrics"),
            detector_result=d.get("detector_result"),
            draft_path=d.get("draft_path"),
        )


class Ledger:
    """Persistent YAML ledger of sweep trials.

    Append-only by convention: new trials are added, existing entries are only
    modified by verify (which fills in detector_result). The ledger accumulates
    across sessions.
    """

    def __init__(self, path=None):
        self.path = path
        self.trials = []

    def append(self, trial: Trial):
        self.trials.append(trial)

    def save(self, path=None):
        path = path or self.path
        if not path:
            raise ValueError("no path specified")
        data = {"version": 1, "trials": [t.to_dict() for t in self.trials]}
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False,
                      allow_unicode=True)
        self.path = path

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            ledger = cls(path)
            return ledger
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or not isinstance(data, dict):
            return cls(path)
        ledger = cls(path)
        for entry in data.get("trials") or []:
            ledger.trials.append(Trial.from_dict(entry))
        return ledger

    def trials_for_arm(self, arm_label):
        return [t for t in self.trials if t.arm == arm_label]

    def trials_for_article(self, article):
        return [t for t in self.trials if t.article == article]

    def arms(self):
        """Distinct arm labels in insertion order."""
        seen = set()
        out = []
        for t in self.trials:
            if t.arm not in seen:
                seen.add(t.arm)
                out.append(t.arm)
        return out

    def articles(self):
        """Distinct article paths in insertion order."""
        seen = set()
        out = []
        for t in self.trials:
            if t.article not in seen:
                seen.add(t.article)
                out.append(t.article)
        return out

    def update_detector(self, article, arm, result):
        """Fill in detector_result for matching trials."""
        for t in self.trials:
            if t.article == article and t.arm == arm:
                t.detector_result = result
