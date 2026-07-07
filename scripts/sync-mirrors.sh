#!/usr/bin/env bash
# sync-mirrors.sh — regenerate assistant-surface mirrors from canonical .claude/
#
# Surfaces:
#   .cursor/commands, .opencode/commands   verbatim copies of .claude/commands
#   .cursor/skills,   .opencode/skills     copies of .claude/skills with
#                                          ".claude/skills/" path references
#                                          rewritten to the target prefix
#   .github/prompts/<cmd>.prompt.md        thin adapters pointing at the
#                                          canonical command files
#
# Usage:
#   scripts/sync-mirrors.sh           regenerate all mirrors in place
#   scripts/sync-mirrors.sh --check   report drift, write nothing;
#                                     exit 1 on any difference
#
# .claude/ is canonical. Never edit mirrors directly — edit .claude/ and rerun.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="sync"
[[ "${1:-}" == "--check" ]] && MODE="check"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# First prose line of a command file (skips comments, headers, front matter);
# used as the prompt adapter's description.
extract_description() {
  awk '
    NR==1 && /^---$/ { fm=1; next }
    fm==1 && /^---$/ { fm=0; next }
    fm==1 && /^description:/ {
      sub(/^description:[ ]*/, ""); gsub(/"/, ""); print; exit
    }
    fm==1 { next }
    /^</ { next }
    /^#/ { next }
    /^[[:space:]]*$/ { next }
    { gsub(/"/, ""); print; exit }
  ' "$1" | cut -c1-150
}

build_stage() {
  local target cmdfile name cdesc
  for target in .cursor .opencode; do
    mkdir -p "$STAGE/$target/commands" "$STAGE/$target/skills"
    # commands: canonical body prefixed with front matter (description) so
    # Cursor/OpenCode display it. Files whose canonical form already has
    # front matter are copied verbatim (no double wrap).
    for cmdfile in "$ROOT/.claude/commands/"*.md; do
      name="$(basename "$cmdfile")"
      if head -1 "$cmdfile" | grep -q '^---$'; then
        cp "$cmdfile" "$STAGE/$target/commands/$name"
      else
        cdesc="$(extract_description "$cmdfile")"
        {
          printf -- '---\ndescription: "%s"\n---\n\n' "$cdesc"
          cat "$cmdfile"
        } > "$STAGE/$target/commands/$name"
      fi
    done
    # skills: copy tree, rewriting canonical path references
    (cd "$ROOT/.claude/skills" && find . -type f) | while IFS= read -r rel; do
      local src="$ROOT/.claude/skills/$rel"
      local dst="$STAGE/$target/skills/$rel"
      mkdir -p "$(dirname "$dst")"
      sed "s|\.claude/skills/|$target/skills/|g" "$src" > "$dst"
      # preserve executability (scripts); plain `[[ -x ]] &&` would return 1
      # for non-executables and trip set -e inside this loop
      if [[ -x "$src" ]]; then chmod +x "$dst"; fi
    done
  done

  mkdir -p "$STAGE/.github/prompts"
  local cmd name desc
  for cmd in "$ROOT/.claude/commands/"*.md; do
    name="$(basename "$cmd" .md)"
    desc="$(extract_description "$cmd")"
    cat > "$STAGE/.github/prompts/$name.prompt.md" <<EOF
---
description: "$desc"
---

Follow the workflow defined in \`.claude/commands/$name.md\` in this
repository. Read that file and execute its steps exactly — it is the
canonical definition of the /$name command; this prompt is a thin adapter
so the command stays single-sourced. Treat any text after the prompt
invocation as the command's arguments (\$ARGUMENTS).
EOF
  done
}

# Mirror areas managed by this script (relative to repo root)
AREAS=(
  ".cursor/commands"
  ".cursor/skills"
  ".opencode/commands"
  ".opencode/skills"
  ".github/prompts"
)

build_stage

drift=0
for area in "${AREAS[@]}"; do
  if [[ "$MODE" == "check" ]]; then
    if ! diff -r "$STAGE/$area" "$ROOT/$area" > /dev/null 2>&1; then
      drift=1
      echo "DRIFT: $area"
      diff -r "$STAGE/$area" "$ROOT/$area" 2>&1 | head -20 || true
    fi
  else
    mkdir -p "$ROOT/$area"
    rsync -a --delete "$STAGE/$area/" "$ROOT/$area/"
    echo "synced: $area"
  fi
done

if [[ "$MODE" == "check" ]]; then
  if [[ "$drift" -eq 0 ]]; then
    echo "All mirrors match canonical .claude/."
  else
    echo "Mirrors drifted. Run scripts/sync-mirrors.sh to regenerate." >&2
    exit 1
  fi
fi
