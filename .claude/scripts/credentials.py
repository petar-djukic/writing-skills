#!/usr/bin/env python3
"""Read API credentials from a gitignored .secrets/ in the consuming repository.

Named credentials.py, not secrets.py: `secrets` is a standard-library module
(token generation), and a local file of that name shadows it for every import
in the process. The directory is still .secrets/ — that is the user-facing
convention; only the module is renamed.

The skills are shared by symlink; the repository you run them in is yours. So
credentials live in your repository, never here, discovered by walking up from
the working directory — the same rule writing-voice/ uses.

Resolution order, most explicit first:

  1. an explicit value (a --api-key flag)
  2. the service's environment variable
  3. .secrets/keys.json (or .yaml) discovered by walking up

Existing flags and environment variables keep working; the file is a fallback,
so nothing that worked before changes.

Format is data, not shell — the scripts read it when they call the API rather
than depending on someone having sourced a file first:

  {"pangram": "...", "serpapi": "...", "semantic_scholar": "..."}

JSON is parsed with the standard library so the credential path carries no
dependency. YAML is accepted when PyYAML happens to be importable.

Refusals are deliberate. A .secrets/ that git is not ignoring, or that other
users on the machine can read, is not a safe place to keep a key, and loading
from one quietly is how a credential ends up committed. This module was written
after exactly that happened: a Claude OAuth token sat tracked and public in
sdd-hello-world for five months.

A key value is never returned in an error, never logged, and never printed.
Callers get the key or an exception naming the service and the paths searched.
"""

import json
import os
import subprocess

SECRETS_DIR = ".secrets"
FILENAMES = ("keys.json", "secrets.json", "keys.yaml", "keys.yml",
             "secrets.yaml", "secrets.yml")

# service -> conventional environment variable, so callers need only name the
# service and the two lookups cannot drift apart.
ENV_VARS = {
    "pangram": "PANGRAM_API_KEY",
    "serpapi": "SERPAPI_KEY",
    "semantic_scholar": "SEMANTIC_SCHOLAR_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}


class SecretsError(Exception):
    """Never carries a key value — only the service and where we looked."""


def discover(start_path=None):
    """Nearest .secrets/ walking up from start_path. None if there is none."""
    d = os.path.abspath(start_path or os.getcwd())
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        cand = os.path.join(d, SECRETS_DIR)
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _is_ignored(path):
    """True if git ignores path. None when git cannot answer.

    Unknown is not the same as safe, and the caller distinguishes them: a
    directory outside any repository has no git to protect it, which is fine,
    while a directory inside a repository that git is NOT ignoring is the case
    worth refusing.
    """
    try:
        r = subprocess.run(["git", "check-ignore", "-q", path],
                           cwd=os.path.dirname(os.path.abspath(path)) or ".",
                           capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        # Exit 1 means "not ignored" — but also means git ran, so check whether
        # we are even in a repository before calling it a problem.
        try:
            inside = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=os.path.dirname(os.path.abspath(path)) or ".",
                capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        return False if inside.stdout.strip() == "true" else None
    return None


def _check_safe(d):
    """Raise if this directory is not a safe place to keep a credential."""
    if _is_ignored(d) is False:
        raise SecretsError(
            f"{d} is inside a git repository and is NOT gitignored. Refusing to "
            f"read credentials from it — one `git add -A` would commit them. "
            f"Add '{SECRETS_DIR}/' to .gitignore first.")
    mode = os.stat(d).st_mode
    if mode & 0o077:
        raise SecretsError(
            f"{d} is readable by other users on this machine (mode "
            f"{oct(mode & 0o777)}). Run: chmod 700 {d}")


def load(secrets_dir=None, start_path=None, check=True):
    """Parsed credential mapping from the discovered .secrets/. {} if none."""
    d = secrets_dir or discover(start_path)
    if not d:
        return {}
    if check:
        _check_safe(d)
    for name in FILENAMES:
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                if name.endswith((".yaml", ".yml")):
                    try:
                        import yaml
                    except ImportError:
                        raise SecretsError(
                            f"{p} is YAML but PyYAML is not installed. Install "
                            f"it, or use keys.json instead.")
                    data = yaml.safe_load(f) or {}
                else:
                    data = json.load(f)
        except SecretsError:
            raise
        except Exception as e:
            # The parser may quote file content on error, and file content is
            # the keys. Report the path and the error type only.
            raise SecretsError(f"could not parse {p}: {type(e).__name__}")
        if not isinstance(data, dict):
            raise SecretsError(f"{p} must contain a mapping of service to key")
        return {k: v for k, v in data.items() if not str(k).startswith("_")}
    return {}


def resolve(service, explicit=None, env=None, start_path=None, required=True):
    """The key for `service`, by flag, then environment, then .secrets/.

    Raises SecretsError naming the service and every place searched — never a
    key value — when required and nothing is found.
    """
    if explicit:
        return explicit
    var = env or ENV_VARS.get(service, f"{service.upper()}_API_KEY")
    from_env = os.environ.get(var)
    if from_env:
        return from_env

    d = discover(start_path)
    val = load(secrets_dir=d, start_path=start_path).get(service) if d else None
    if isinstance(val, str) and val.strip():
        if "REPLACE" in val.upper() or val.strip().startswith("<"):
            raise SecretsError(
                f"'{service}' in {d} is still a placeholder. Paste the real key "
                f"in, or pass it on the command line.")
        return val
    if not required:
        return None
    where = f"{d}/{FILENAMES[0]}" if d else f"no {SECRETS_DIR}/ found above {os.getcwd()}"
    raise SecretsError(
        f"no API key for '{service}'. Looked at: --api-key, ${var}, {where}.")


def main():
    """Report what is configured. Prints service names and status, never keys."""
    import argparse
    ap = argparse.ArgumentParser(
        description="show which credentials are configured (never prints values)")
    ap.add_argument("--start", help="directory to search upward from")
    a = ap.parse_args()

    d = discover(a.start)
    if not d:
        print(f"no {SECRETS_DIR}/ found above {os.path.abspath(a.start or os.getcwd())}")
        return 0
    print(f"secrets: {d}")
    status = {True: "yes",
              False: "NO — refusing to read from it",
              None: "not in a git repository"}[_is_ignored(d)]
    print(f"gitignored: {status}")
    try:
        data = load(secrets_dir=d)
    except SecretsError as e:
        print(f"error: {e}")
        return 1
    if not data:
        print(f"no credential file found (looked for: {', '.join(FILENAMES)})")
        return 0
    for svc in sorted(data):
        v = str(data[svc])
        placeholder = "REPLACE" in v.upper() or v.startswith("<")
        print(f"  {svc:20} {'placeholder — not usable' if placeholder else 'set'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
