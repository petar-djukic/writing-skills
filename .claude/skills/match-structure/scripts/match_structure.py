#!/usr/bin/env python3
"""Backward-compat shim — the section-level driver moved to match-outline.

All functions and the CLI are re-exported so existing callers and tests
continue to work. New code should import from match_outline directly.
"""

import os
import sys

_OUTLINE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "match-outline", "scripts"))
if _OUTLINE not in sys.path:
    sys.path.insert(0, _OUTLINE)

from match_outline import *  # noqa: F401,F403
from match_outline import (main, DEFAULT_MODEL, DEFAULT_ENDPOINT,
                           _is_claude, _is_passthrough, _count_paragraphs,
                           _strip_added_bold, _FM)

if __name__ == "__main__":
    main()
