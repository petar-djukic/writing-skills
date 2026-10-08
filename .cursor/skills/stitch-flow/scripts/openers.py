#!/usr/bin/env python3
# Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT
"""openers.py -- locate weak discourse joints between consecutive paragraphs.

Prints, per section, the chain of joints: the last sentence of paragraph N
against the first sentence of paragraph N+1, flagging joints where the opener
neither shares a content word with the previous paragraph's close nor starts
with a connective, demonstrative, or pronoun. Also reports near-duplicate
definitional sentences and the paragraph word-count spread.

The script locates; the reader decides. A flagged joint is a place to look,
not a defect: a deliberate hard cut at a section turn is legitimate.

Usage: openers.py <file.md> [<file.md> ...]

stdlib only; markdown in, report out, nothing written.
"""
import re
import sys

STOPWORDS = frozenset("""
a an and are as at be been both but by can could do does each for from had
has have here how if in into is it its may more most no not of on one only
or our so than that the their them then there these they this those to two
under was we what when where which while who will with would
""".split())

CONNECTIVE = re.compile(
    r'^(That|This|These|Those|Both|Neither|Such|It|They|But|So|Yet|'
    r'And|Then|There|Here|The same|What|Where|When|Written down|'
    r'Between them|From th|At th|Of th|In th|On th|With th)\b')


def strip_comments(text):
    return re.sub(r'<!--.*?-->', '', text, flags=re.S)


def sentences(paragraph):
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z("“])', paragraph.strip())
    return [p.strip() for p in parts if p.strip()]


def content_words(text):
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def blocks(text):
    """Yield (kind, content) blocks: heading | para | skip."""
    for raw in re.split(r'\n\s*\n', text):
        stripped = raw.strip()
        if not stripped:
            continue
        first = stripped.split('\n')[0].lstrip()
        if first.startswith('#'):
            yield 'heading', stripped.lstrip('#').strip()
        elif first.startswith(('|', '![', 'Table:', '```', '---')):
            yield 'skip', stripped
        elif first.startswith('- '):
            yield 'skip', stripped        # a list is a block, not a joint
        else:
            yield 'para', ' '.join(l.strip() for l in stripped.split('\n'))


def weak(prev_para, opener):
    if CONNECTIVE.match(opener):
        return False
    tail = ' '.join(sentences(prev_para)[-2:])
    return not (content_words(opener[:120]) & content_words(tail))


def definitional(sentence):
    return re.match(r'^(A|An|The)?\s*[A-Z][\w -]{0,40}\b(is|are)\b', sentence)


def report(path):
    text = strip_comments(open(path).read())
    section = '(start)'
    prev = None
    joints = flagged = 0
    counts = []
    defs = []
    print(f'== {path}')
    for kind, content in blocks(text):
        if kind == 'heading':
            section = content
            prev = None
            continue
        if kind == 'skip':
            prev = None                   # an exhibit resets the chain
            continue
        counts.append(len(content.split()))
        first = sentences(content)[0]
        if definitional(first):
            defs.append((section, first))
        if prev is not None:
            joints += 1
            mark = 'WEAK' if weak(prev, first) else 'ok  '
            if mark == 'WEAK':
                flagged += 1
            tail = sentences(prev)[-1]
            print(f'  [{mark}] {section}')
            print(f'     ...{tail[-80:]}')
            print(f'     >> {first[:100]}')
        prev = content
    pairs = []
    for i in range(len(defs)):
        for j in range(i + 1, len(defs)):
            a, b = content_words(defs[i][1]), content_words(defs[j][1])
            if a and b and len(a & b) / min(len(a), len(b)) > 0.6:
                pairs.append((defs[i], defs[j]))
    for (sa, da), (sb, db) in pairs:
        print(f'  [DUP ] {sa} / {sb}')
        print(f'     {da[:90]}')
        print(f'     {db[:90]}')
    if counts:
        print(f'  joints: {joints}, weak: {flagged}; paragraph words '
              f'min/median/max: {min(counts)}/'
              f'{sorted(counts)[len(counts)//2]}/{max(counts)}')
    return flagged


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    total = sum(report(p) for p in sys.argv[1:])
    print(f'total weak joints: {total}')


if __name__ == '__main__':
    main()
