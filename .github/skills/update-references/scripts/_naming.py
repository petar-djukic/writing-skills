"""Shared file-naming and citation-key helpers for the update-references skill.

Imported by arxiv.py, scholar.py, and semantic_scholar.py so the naming
convention is byte-identical across every fetcher (and reproducible by the
migration in arxiv.py repair).

Two distinct schemes:

  paper_stem()   the rich, human-friendly stem shared by a paper's .pdf, .md,
                 and summary: <Family>-<Year>-<title-slug>-<source>-<id>.
                 Carries full provenance so the directory is browsable.

  citation_key() the short pandoc key: <family>-<year>, lowercase, no title
                 slug, with a letter suffix on collision (lee-2026, lee-2026a).
"""

import re
import string

STEM_MAX_LEN = 150


def _safe(text):
    """Collapse anything outside [A-Za-z0-9._-] to single hyphens."""
    return re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9._-]", "-", str(text))).strip("-")


def _family_token(family):
    """First-author family name for the file stem: alphanumeric, case kept.

    Multi-part surnames ("van der Berg") collapse to a single token
    ("vanderBerg"). Empty names become 'unknown'.
    """
    tok = re.sub(r"[^A-Za-z0-9]", "", family or "")
    return tok or "unknown"


def title_slug(title, max_words=8, max_len=60):
    """Lowercased, hyphen-joined slug of the first few title words."""
    words = re.findall(r"[A-Za-z0-9]+", (title or "").lower())
    slug = "-".join(words[:max_words])
    return slug[:max_len].strip("-")


def _source_tag(arxiv_id=None, version=None, doi=None, citation_id=None):
    """The <source>-<id> tail: arxiv (with version) > doi > scholar fallback."""
    if arxiv_id:
        ver = f"v{version}" if version else ""
        return f"arxiv-{_safe(arxiv_id)}{ver}"
    if doi:
        return f"doi-{_safe(doi)}"
    return f"scholar-{_safe(citation_id or 'unknown')}"


def paper_stem(family, year, title, arxiv_id=None, version=None, doi=None,
               citation_id=None, max_len=STEM_MAX_LEN):
    """Human-friendly stem shared by a paper's pdf, markdown, and summary."""
    fam = _family_token(family)
    yr = str(year) if year else "nd"
    slug = title_slug(title)
    src = _source_tag(arxiv_id, version, doi, citation_id)
    stem = "-".join(p for p in (fam, yr, slug, src) if p)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    return stem[:max_len].strip("-")


def citation_key(family, year, existing_ids):
    """Short pandoc key <family>-<year>, disambiguated against existing_ids.

    existing_ids is the set of ids already in the db (belonging to other
    papers). On collision, append a lowercase letter: lee-2026 -> lee-2026a.
    """
    fam = re.sub(r"[^a-z0-9]", "", (family or "").lower()) or "unknown"
    yr = str(year) if year else "nd"
    base = f"{fam}-{yr}"
    existing = set(existing_ids or ())
    if base not in existing:
        return base
    for suffix in string.ascii_lowercase:
        cand = f"{base}{suffix}"
        if cand not in existing:
            return cand
    i = 1
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"
