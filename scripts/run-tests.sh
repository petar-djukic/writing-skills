#!/usr/bin/env bash
# run-tests.sh — run every test under .claude/ in the pixi environment.
#
# The tests are discovered, never listed. A hardcoded list is how .claude/
# scripts lost credentials.py from all four surfaces for a month (GH-184), and
# the same mistake here would be a suite that quietly stops covering something.
# Discovery has its own failure mode — matching nothing and passing — so zero
# tests found is an error, not a green run.
#
# Each file is a standalone script that exits non-zero on failure; there is no
# test framework and none is wanted. Two of them were stale for months because
# nothing ran them (GH-26).
#
# Both roots are searched. Discovery covered .claude/skills only, so the six
# test files beside the shared modules in .claude/scripts had never run once
# (GH-45) — the same shape as GH-26, one directory over. A narrow root is a
# hardcoded list wearing a find.
#
# Usage:
#   scripts/run-tests.sh            run everything
#   scripts/run-tests.sh <pattern>  run only tests whose path matches
#
# Requires the pixi environment: run .claude/scripts/ensure-env.sh once.

set -uo pipefail          # not -e: a failing test must be recorded, not fatal

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/.claude/pixi.toml"
PATTERN="${1:-}"

if ! command -v pixi >/dev/null 2>&1; then
  echo "run-tests: pixi is not on PATH. Run .claude/scripts/ensure-env.sh first." >&2
  exit 1
fi
if [[ ! -f "$MANIFEST" ]]; then
  echo "run-tests: no pixi manifest at $MANIFEST" >&2
  exit 1
fi

tests=()
while IFS= read -r t; do
  [[ -n "$PATTERN" && "$t" != *"$PATTERN"* ]] && continue
  tests+=("$t")
done < <(find "$ROOT/.claude/skills" "$ROOT/.claude/scripts" \
              -name 'test_*.py' -not -path '*/__pycache__/*' | sort)

if [[ ${#tests[@]} -eq 0 ]]; then
  if [[ -n "$PATTERN" ]]; then
    echo "run-tests: no test matched '$PATTERN'." >&2
  else
    echo "run-tests: discovered no tests under .claude/skills. Either the tree" >&2
    echo "moved or the discovery is wrong — passing here would be worse." >&2
  fi
  exit 1
fi

failed=()
for t in "${tests[@]}"; do
  rel="${t#"$ROOT"/}"
  if output="$(pixi run --manifest-path "$MANIFEST" python "$t" 2>&1)"; then
    printf '  ok    %s\n' "$rel"
  else
    printf '  FAIL  %s\n' "$rel"
    printf '%s\n' "$output" | sed 's/^/          /' | tail -15
    failed+=("$rel")
  fi
done

echo
if [[ ${#failed[@]} -gt 0 ]]; then
  echo "${#failed[@]} of ${#tests[@]} failed:"
  printf '  %s\n' "${failed[@]}"
  exit 1
fi
echo "all ${#tests[@]} tests passed"
