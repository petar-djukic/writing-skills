"""Shared references-database access for the update-references skill.

Imported by arxiv.py, scholar.py, semantic_scholar.py, openalex.py and
keywords.py so every reader and writer of the shared database agrees on what
the file is. The five carried their own copies of load_db/save_db, and the
copies had already drifted — two were missing the `data is None` guard the
other three had.

The database is a CSL-YAML bibliography pandoc can consume directly
(--bibliography). Three shapes are accepted:

    - a bare sequence           the skill's own documented form
    - {"references": [...]}     what pandoc's documentation shows, and what an
                                existing pandoc bibliography looks like
    - {"papers": [...]}         the skill's earlier form

Anything else raises. It used to read as empty (GH-22): `arxiv.py reconcile`
on a references:-keyed file loaded zero entries, reported `checked: 0` and exit
0, and serialized `[]` over thirty hand-maintained entries. `checked: 0` reads
as "nothing needed fixing", not "I could not read your database".

Two guards, because they fail differently:

    load_db raises on a shape it does not recognize — loud, and at the read,
    before any work is done on a database that is not really empty.

    save_db refuses to write an empty database over a file that had entries.
    That is the backstop. load_db can only reject shapes it knows are wrong,
    and total silent loss is bad enough to be worth refusing at the write too,
    whatever produced the empty list — a future format, a half-written file, a
    caller that filtered everything away by mistake.

save_db also preserves the root key it found, so a references:-keyed file stays
references:-keyed and running a command twice is a no-op rather than a silent
reformat of someone's bibliography.
"""

import os
import shutil
import subprocess
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - matches the callers' own message
    raise SystemExit(
        "PyYAML is required. Install with: python3 -m pip install --user pyyaml")


# Root keys recognized on read, in the order they are looked for. The first one
# present wins, and the same key is written back.
ROOT_KEYS = ("references", "papers")


class DatabaseError(RuntimeError):
    """Base for every refusal here, so callers can exit on one type."""


class DatabaseFormatError(DatabaseError):
    """The file exists but is not a shape this skill recognizes."""


class EmptyWriteRefused(DatabaseError):
    """Writing would have emptied a database that had entries."""


def _parse(data, path):
    """Return (entries, root_key) for one parsed YAML document.

    root_key is None for the bare-sequence form.
    """
    if data is None:
        return [], None
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        for key in ROOT_KEYS:
            if key in data:
                value = data[key]
                if value is None:
                    return [], key
                if isinstance(value, list):
                    return value, key
                raise DatabaseFormatError(
                    "%s: '%s' must hold a sequence of entries, found %s. "
                    "Refusing to read it as empty." % (path, key, type(value).__name__))
        raise DatabaseFormatError(
            "%s: mapping has no recognized root key (%s). If this is a "
            "bibliography, give it one of those keys or make it a bare list. "
            "Refusing to read it as empty." % (path, ", ".join(ROOT_KEYS)))
    raise DatabaseFormatError(
        "%s: expected a sequence or a mapping, found %s. Refusing to read it "
        "as empty." % (path, type(data).__name__))


def _read(path):
    """(entries, root_key) from disk. A missing file is an empty bare list."""
    if not os.path.exists(path):
        return [], None
    with open(path) as f:
        data = yaml.safe_load(f)
    return _parse(data, path)


def load_db(path):
    """Every entry in the database at path.

    Raises DatabaseFormatError rather than returning [] for a shape it does not
    recognize, so an unreadable database never reads as an empty one.
    """
    entries, _ = _read(path)
    return entries


def save_db(path, entries, force=False):
    """Write entries to path, preserving the root key the file already used.

    Refuses to replace a non-empty database with an empty one unless force is
    set, and refuses to overwrite a file it cannot parse at all.
    """
    existing, root_key = [], None
    if os.path.exists(path):
        try:
            existing, root_key = _read(path)
        except DatabaseFormatError:
            if not force:
                raise
    if existing and not entries and not force:
        raise EmptyWriteRefused(
            "%s: refusing to write an empty database over %d existing "
            "entries. Pass force=True if that is really intended."
            % (path, len(existing)))

    payload = entries if root_key is None else {root_key: entries}
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True, width=100)
    normalize(path)


def normalize(path):
    """Rewrite path in yq's normal form.

    PyYAML and yq disagree about sequence indentation: PyYAML writes a sequence
    flush with its key, yq indents it. The difference is presentational — the
    parsed data is identical either way — but a database written by one and
    edited by the other reformats end to end, and on a thirty-thousand-line
    bibliography that buries the real change under tens of thousands of lines
    of noise.

    So yq decides the format. Normalizing after the write, rather than teaching
    PyYAML to match, keeps one definition of the format instead of a second
    implementation that drifts the moment either tool changes a default.

    Without yq the database is still written and still correct, only in the
    other style. That is worth a warning rather than a failure: the file is
    usable, but the next yq edit will reformat it.
    """
    if shutil.which("yq") is None:
        print(
            "update-references: yq not found, so %s is written in PyYAML's "
            "style rather than yq's normal form. It is valid either way; the "
            "next yq edit will reformat it whole." % path,
            file=sys.stderr)
        return
    result = subprocess.run(["yq", "-i", ".", path], capture_output=True, text=True)
    if result.returncode != 0:
        # Re-running yq on the path it just wrote should not fail. If it does,
        # say so rather than leaving the caller to discover a mangled file.
        print("update-references: yq could not normalize %s: %s"
              % (path, result.stderr.strip()), file=sys.stderr)
