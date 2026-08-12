---
title: Citation extraction fixture
---

# Forms that must round-trip

Single-key bracket [@djukic-2007] in a sentence.

Two keys in one bracket [@djukic-2007; @smith-2020] — the last one used to
come back truncated as well as whole.

Three keys [@a-2001; @b-2002; @c-2003] — the middle key truncated too, since
a semicolon follows it.

Inline @kazman-2021 mid-sentence.

Inline at the end of a sentence @nygard-2011.

Prefixed and suffixed [see @bass-2021, p. 42] locator.

Keys with internal punctuation must survive: [@doi:10.1234/xyz] and
[@smith.jones-2019].

An email address like nobody@example.com is not a citation.

```python
# A fenced block mentioning [@not-a-citation] must be ignored.
lookup = "@also-not-one"
```

Bracket that is not a citation [see chapter 4] stays out.
