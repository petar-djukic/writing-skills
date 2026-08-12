#!/usr/bin/env python3
"""Offline tests for credentials.py. Run: python3 <surface>/scripts/test_credentials.py

Builds throwaway repositories in a temp directory. No network, no real keys,
and nothing here reads the machine's actual .secrets/.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import credentials as sec  # noqa: E402

SENTINEL = "sk-SENTINEL-VALUE-THAT-MUST-NEVER-BE-PRINTED"


def git(d, *args):
    subprocess.run(["git", *args], cwd=d, capture_output=True, check=False)


def make_repo(tmp, name, gitignore=".secrets/\n", keys=None, fname="keys.json"):
    d = os.path.join(tmp, name)
    os.makedirs(d)
    git(d, "init", "-q")
    if gitignore is not None:
        open(os.path.join(d, ".gitignore"), "w").write(gitignore)
    if keys is not None:
        sd = os.path.join(d, ".secrets")
        os.makedirs(sd, mode=0o700)
        p = os.path.join(sd, fname)
        with open(p, "w") as f:
            if fname.endswith((".yaml", ".yml")):
                f.write("\n".join(f"{k}: {v}" for k, v in keys.items()))
            else:
                json.dump(keys, f)
        os.chmod(sd, 0o700)
    return d


def expect(fn, needle, label):
    try:
        fn()
    except sec.SecretsError as e:
        assert needle.lower() in str(e).lower(), \
            f"{label}: wanted {needle!r} in {str(e)!r}"
        return str(e)
    raise AssertionError(f"{label}: expected SecretsError, got none")


def main():
    tmp = tempfile.mkdtemp(prefix="test-secrets-")
    try:
        # 1. Found by walking up from a nested directory.
        r = make_repo(tmp, "ok", keys={"pangram": SENTINEL})
        deep = os.path.join(r, "a", "b", "c")
        os.makedirs(deep)
        assert sec.discover(deep) == os.path.join(r, ".secrets")
        assert sec.resolve("pangram", start_path=deep) == SENTINEL

        # 2. Precedence: flag beats env beats file. Existing usage must not
        #    change behaviour just because a file now exists.
        os.environ["PANGRAM_API_KEY"] = "from-env"
        try:
            assert sec.resolve("pangram", explicit="from-flag", start_path=deep) == "from-flag"
            assert sec.resolve("pangram", start_path=deep) == "from-env"
        finally:
            del os.environ["PANGRAM_API_KEY"]
        assert sec.resolve("pangram", start_path=deep) == SENTINEL

        # 3. THE refusal this module exists for: a .secrets/ inside a repo that
        #    git is not ignoring. Loading quietly from one is how a credential
        #    gets committed.
        bad = make_repo(tmp, "unignored", gitignore="*.log\n",
                        keys={"pangram": SENTINEL})
        m = expect(lambda: sec.load(start_path=bad), "not gitignored", "unignored")
        assert SENTINEL not in m, "key leaked into the refusal message"
        assert ".gitignore" in m, "refusal should say how to fix it"

        # 4. World-readable directory is refused, with the chmod to run.
        loose = make_repo(tmp, "loose", keys={"pangram": SENTINEL})
        os.chmod(os.path.join(loose, ".secrets"), 0o755)
        m = expect(lambda: sec.load(start_path=loose), "readable by other users", "perms")
        assert "chmod 700" in m and SENTINEL not in m

        # 5. No key anywhere: the error names every place searched, and no value.
        empty = make_repo(tmp, "empty", keys={})
        m = expect(lambda: sec.resolve("pangram", start_path=empty),
                   "no api key", "missing")
        assert "--api-key" in m and "PANGRAM_API_KEY" in m

        # 6. Placeholders are refused rather than sent to an API as if real.
        ph = make_repo(tmp, "placeholder", keys={"pangram": "REPLACE-AFTER-ROTATING"})
        expect(lambda: sec.resolve("pangram", start_path=ph), "placeholder", "placeholder")

        # 7. required=False returns None instead of raising.
        assert sec.resolve("pangram", start_path=empty, required=False) is None

        # 8. A malformed file reports the path and error type, never content —
        #    the content is the keys, and parsers love to quote it.
        broke = make_repo(tmp, "broken", keys={"pangram": SENTINEL})
        open(os.path.join(broke, ".secrets", "keys.json"), "w").write(
            '{"pangram": "' + SENTINEL + '"')          # truncated JSON
        m = expect(lambda: sec.load(start_path=broke), "could not parse", "malformed")
        assert SENTINEL not in m, "key leaked through a parser error"

        # 9. Keys starting with _ are comments, not services.
        c = make_repo(tmp, "comment",
                      keys={"_comment": "notes", "pangram": SENTINEL})
        assert set(sec.load(start_path=c)) == {"pangram"}

        # 10. YAML works when PyYAML is available; skipped cleanly when not.
        try:
            import yaml  # noqa: F401
            y = make_repo(tmp, "yaml", keys={"pangram": SENTINEL}, fname="keys.yaml")
            assert sec.resolve("pangram", start_path=y) == SENTINEL
        except ImportError:
            print("  (PyYAML absent — YAML case skipped)")

        # 11. No .secrets/ anywhere: empty mapping, no exception. Absent config
        #     is a normal state, not an error.
        bare = make_repo(tmp, "bare")
        assert sec.load(start_path=bare) == {}

        # 12. Outside any git repository there is no gitignore to check, and
        #     that is fine — unknown must not be treated as unsafe.
        plain = os.path.join(tmp, "nogit")
        os.makedirs(os.path.join(plain, ".secrets"), mode=0o700)
        json.dump({"pangram": SENTINEL},
                  open(os.path.join(plain, ".secrets", "keys.json"), "w"))
        assert sec.resolve("pangram", start_path=plain) == SENTINEL

        print("test_credentials: all assertions passed (no network, no real keys)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
