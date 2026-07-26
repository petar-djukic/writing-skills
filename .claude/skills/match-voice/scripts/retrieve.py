#!/usr/bin/env python3
"""Anchor-passage retrieval for match-voice.

Built once, imported twice: the retrieval implementation lives in the stylometry
skill's voice_anchors.py (GH-156) and this is a thin wrapper that adds the
prompt-ready rendering this pipeline needs. Every agent surface carries the
full skill set, so the sibling import resolves wherever the skill is
installed.

The writing-voice/ directory contract (manifest schema, author-voice /
venue-voice roles, discovery) is documented in the repository rule of the
same name.

Usage:
  retrieve.py --text <file>|- [--voice-dir D | --for <draft>] [-k 3] [--json]
"""

import argparse
import json
import os
import sys


def _voice_anchors():
    sibling = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "..", "match-structure", "scripts"))
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    try:
        import voice_anchors
        return voice_anchors
    except ImportError as e:
        sys.exit(f"could not import voice_anchors.py from {sibling}: {e}")


def render(anchors):
    """Prompt-ready anchor block: numbered passages with provenance."""
    if not anchors:
        return "(no voice anchors available)"
    out = []
    for i, a in enumerate(anchors, 1):
        out.append(f"[Anchor {i} — {a['role']}, {a['file']}]\n{a['text']}")
    return "\n\n".join(out)


def main():
    p = argparse.ArgumentParser(description="retrieve voice anchors for a passage")
    p.add_argument("--text", required=True, help="file with the passage, or -")
    p.add_argument("--voice-dir")
    p.add_argument("--for", dest="for_file", help="discover writing-voice/ from this file")
    p.add_argument("-k", type=int, default=3)
    p.add_argument("--role", choices=["author-voice", "venue-voice"],
                   help="hard filter to one role")
    p.add_argument("--stratum", choices=["pre-ai", "ai-era"],
                   help="pre-ai restricts to diction-safe samples across roles")
    p.add_argument("--json", action="store_true", help="emit the raw anchor records")
    args = p.parse_args()

    va = _voice_anchors()
    voice_dir = args.voice_dir
    if not voice_dir:
        ref = args.for_file or (args.text if args.text != "-" else os.getcwd())
        voice_dir = va.discover(ref)
        if not voice_dir:
            sys.exit(f"no writing-voice/ found from {ref}; match-voice requires "
                     "exemplars (see the writing-voice contract)")

    passage = sys.stdin.read() if args.text == "-" else open(args.text).read()
    got = va.anchors(voice_dir, passage, k=args.k, role=args.role,
                     pre_ai=(True if args.stratum == "pre-ai"
                             else False if args.stratum == "ai-era" else None))
    if args.json:
        print(json.dumps({"writing_voice": voice_dir, "anchors": got},
                         indent=2, ensure_ascii=False))
    else:
        print(render(got))


if __name__ == "__main__":
    main()
