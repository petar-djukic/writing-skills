#!/usr/bin/env python3
"""No skill outside match-voice reads MATCH_VOICE_* (GH-198).

The borrowed-env pattern appeared three times (tighten-style model, GH-193;
tighten-style timeout and tune-anchors model, GH-198): configuring match-voice
silently reconfigured a neighbor. This greps the sources so it cannot return.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.normpath(os.path.join(HERE, "..", "..", ".."))


def test_match_voice_env_stays_home():
    offenders = []
    for root, dirs, files in os.walk(SKILLS):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, SKILLS)
            if rel.startswith("match-voice" + os.sep):
                continue
            src = open(path, encoding="utf-8", errors="replace").read()
            for m in re.finditer(r'environ(?:\.get)?\(\s*["\'](MATCH_VOICE_\w+)', src):
                offenders.append(f"{rel}: {m.group(1)}")
    assert not offenders, "\n".join(offenders)
    print("  match_voice_env_stays_home: ok")


def main():
    test_match_voice_env_stays_home()
    print("test_env_ownership: all assertions passed")


if __name__ == "__main__":
    main()
