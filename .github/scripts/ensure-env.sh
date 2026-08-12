#!/usr/bin/env bash
# ensure-env.sh — provision the pixi-managed Python environment for the skills.
#
# This script is self-locating: it derives the agent directory from its own
# path, so the same script works whether it runs from .claude, .cursor,
# .opencode, or .github (each carries a copy of pixi.toml / pixi.lock beside a
# scripts/ directory). It is meant to be run when an agent opens a repository,
# before any skill that shells out to Python.
#
# Behaviour:
#   1. If pixi is on PATH, skip installation.
#   2. Otherwise install pixi via the official installer — unless
#      SKILL_ENV_NO_INSTALL is set, in which case report and exit non-zero.
#      The installer command is printed before it runs.
#   3. Run `pixi install` against the co-located manifest to materialize the
#      locked environment. Idempotent: a second run does no meaningful work.
#
# Exit codes: 0 on a ready environment; non-zero if provisioning is needed but
# blocked (e.g. SKILL_ENV_NO_INSTALL with pixi absent) or the install fails.

set -euo pipefail

# The agent directory is the parent of this script's scripts/ directory.
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$AGENT_DIR/pixi.toml"

if [[ ! -f "$MANIFEST" ]]; then
  echo "ensure-env: no pixi.toml at $MANIFEST — cannot provision." >&2
  exit 1
fi

PIXI_INSTALL_URL="https://pixi.sh/install.sh"

ensure_pixi() {
  if command -v pixi >/dev/null 2>&1; then
    return 0
  fi
  # pixi may already be installed to the default prefix but not yet on PATH.
  if [[ -x "$HOME/.pixi/bin/pixi" ]]; then
    export PATH="$HOME/.pixi/bin:$PATH"
    return 0
  fi
  if [[ -n "${SKILL_ENV_NO_INSTALL:-}" ]]; then
    echo "ensure-env: pixi is not installed and SKILL_ENV_NO_INSTALL is set." >&2
    echo "            Install pixi from $PIXI_INSTALL_URL, then re-run." >&2
    return 1
  fi
  echo "ensure-env: pixi not found; installing via: curl -fsSL $PIXI_INSTALL_URL | bash"
  curl -fsSL "$PIXI_INSTALL_URL" | bash
  export PATH="$HOME/.pixi/bin:$PATH"
  if ! command -v pixi >/dev/null 2>&1; then
    echo "ensure-env: pixi install did not put pixi on PATH; open a new shell or" >&2
    echo "            add \$HOME/.pixi/bin to PATH, then re-run." >&2
    return 1
  fi
}

ensure_pixi

# Materialize the locked environment. pixi install is a no-op when the env
# already matches the lockfile, so this stays fast on repeat runs.
echo "ensure-env: provisioning environment from $MANIFEST"
pixi install --manifest-path "$MANIFEST" >/dev/null
echo "ensure-env: ready. Run skill scripts with:"
echo "            pixi run --manifest-path \"$MANIFEST\" python <script> …"
