#!/usr/bin/env python3
# Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT
"""Standalone test for openers.py: exits non-zero on failure."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = """# Section One

The manifest holds the team and pins each role. Review happens on the manifest's diff.

That diff is also where an audit starts. The reviewer reads it before anything runs.

A gate is a check another role performs. Nothing passes without it.

# Section Two

A gate is a check that another role performs on a change. It stands before production.

<!-- a comment between paragraphs must not break the chain -->
The sandbox replays the change against acceptance criteria. Fidelity bounds what it proves.
"""


def main():
    with tempfile.NamedTemporaryFile('w', suffix='.md', delete=False) as f:
        f.write(SAMPLE)
        path = f.name
    out = subprocess.run(
        [sys.executable, os.path.join(HERE, 'openers.py'), path],
        capture_output=True, text=True).stdout
    os.unlink(path)
    checks = [
        # joint 1: "That diff" is a connective/demonstrative opener -> ok
        ('[ok  ]' in out, 'connective opener should pass'),
        # joint 2: "A gate is..." after the diff/audit paragraph -> weak
        ('[WEAK]' in out, 'freestanding thesis opener should flag'),
        # the two near-identical gate definitions -> duplicate
        ('[DUP ]' in out, 'duplicate definitional sentences should flag'),
        # comment between paragraphs must not reset or crash the chain
        ('sandbox replays' in out, 'paragraph after comment is in the chain'),
        ('total weak joints:' in out, 'summary line present'),
    ]
    failed = [msg for okay, msg in checks if not okay]
    if failed:
        print(out)
        for msg in failed:
            print('FAIL:', msg)
        sys.exit(1)
    print('test_openers: ok')


if __name__ == '__main__':
    main()
