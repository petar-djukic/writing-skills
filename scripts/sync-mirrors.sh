#!/usr/bin/env bash
# sync-mirrors.sh — regenerate assistant-surface mirrors from canonical .claude/
#
# Surfaces:
#   .cursor/commands, .opencode/commands   verbatim copies of .claude/commands
#   .cursor/skills,   .opencode/skills     copies of .claude/skills with
#                                          ".claude/skills/" path references
#                                          rewritten to the target prefix
#   .github/prompts/<cmd>.prompt.md        self-contained prompt per command:
#                                          the full canonical command body,
#                                          inlined (not a pointer)
#   .github/prompts/<skill>.prompt.md      one prompt per skill, pointing at the
#                                          co-located .github/skills/<name>/
#   .github/skills/<name>/**               copies of .claude/skills with
#                                          references rewritten to .github/skills
#   .github/copilot-instructions.md        generated, self-contained: the
#                                          instructions and rules inlined
#   .codex/AGENTS.md                       generated, self-contained Codex
#                                          repository instructions
#   AGENTS.md                               root-level Codex discovery copy of
#                                          the generated repository instructions
#   .codex/prompts/<cmd>.md                full workflow per canonical command
#   .codex/skills/<name>/**                copied skill trees, with paths
#                                          rewritten to stay in .codex/
#   <surface>/pixi.toml, pixi.lock         the pixi environment manifest and
#                                          lockfile, copied into every surface
#   <surface>/scripts/ensure-env.sh        the self-locating env preflight,
#                                          copied into every surface
#
# The .github tree is designed to work as a bare symlink: `ln -s .github` into
# another repository gives Copilot working commands, instructions, and skills
# with no reference escaping the .github subtree.
#
# Usage:
#   scripts/sync-mirrors.sh           regenerate all mirrors in place
#   scripts/sync-mirrors.sh --check   report drift, write nothing;
#                                     exit 1 on any difference
#
# .claude/ is canonical. Never edit mirrors directly — edit .claude/ and rerun.

set -euo pipefail

# BSD sed can reject valid UTF-8 content under a non-UTF-8 locale. The mirror
# transformations are byte-preserving apart from their explicit path rewrites.
export LC_ALL=C

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

# Command body with a leading copyright comment and/or a leading front-matter
# block stripped, so it can be inlined beneath freshly generated front matter
# without producing a doubled "---" fence.
command_body() {
  awk '
    NR==1 && /^<!--/ { next }
    NR==1 && /^<\\!--/ { next }
    NR==1 && /^---$/ { fm=1; next }
    fm==1 && /^---$/ { fm=0; started=1; next }
    fm==1 { next }
    # skip blank lines before the first real content
    !started && /^[[:space:]]*$/ { next }
    { started=1; print }
  ' "$1"
}

# Inline the instructions/rules for copilot-instructions.md, dropping the
# copyright comment and rewriting every canonical path reference so nothing
# under .github points back at .claude/.cursor/.opencode.
inline_rules() {
  sed \
    -e '/<!-- Copyright/d' \
    -e '/<\\!-- Copyright/d' \
    -e 's|\.claude/skills/|.github/skills/|g' \
    -e 's|\.claude/commands/|.github/prompts/|g' \
    -e 's|\.claude/rules/||g' \
    -e 's|rules/||g' \
    -e 's|\.claude/||g' \
    "$1"
}

# Inline the instructions/rules for Codex's project guidance file. Codex uses
# AGENTS.md for durable repository conventions, so all required rules need to
# be present in the generated document rather than linked from .claude/.
inline_codex_rules() {
  sed \
    -e '/<!-- Copyright/d' \
    -e '/<\\!-- Copyright/d' \
    -e 's|\.claude/skills/|.codex/skills/|g' \
    -e 's|\.claude/commands/|.codex/prompts/|g' \
    -e 's|\.claude/rules/||g' \
    -e 's|rules/||g' \
    -e 's|\.claude/||g' \
    "$1"
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
    (cd "$ROOT/.claude/skills" && find . -type f ! -path '*/__pycache__/*') | while IFS= read -r rel; do
      local src="$ROOT/.claude/skills/$rel"
      local dst="$STAGE/$target/skills/$rel"
      mkdir -p "$(dirname "$dst")"
      sed "s|\.claude/skills/|$target/skills/|g" "$src" > "$dst"
      # preserve executability (scripts); plain `[[ -x ]] &&` would return 1
      # for non-executables and trip set -e inside this loop
      if [[ -x "$src" ]]; then chmod +x "$dst"; fi
    done
  done

  # -- .github: self-contained --------------------------------------------
  mkdir -p "$STAGE/.github/prompts" "$STAGE/.github/skills"

  # One prompt per command: the full canonical body inlined beneath generated
  # front matter, so the prompt stands alone with no pointer to .claude.
  local cmd desc
  for cmd in "$ROOT/.claude/commands/"*.md; do
    name="$(basename "$cmd" .md)"
    desc="$(extract_description "$cmd")"
    {
      printf -- '---\ndescription: "%s"\n---\n\n' "$desc"
      printf 'Execute the /%s command. The full workflow follows; treat any\n' "$name"
      printf 'text after the prompt invocation as its arguments ($ARGUMENTS).\n\n'
      command_body "$cmd"
    } > "$STAGE/.github/prompts/$name.prompt.md"
  done

  # Skills: copy each tree into .github/skills, rewriting every canonical path
  # reference so nothing under .github points outside it. Unlike the
  # .cursor/.opencode copies (which keep a sibling .claude/ and rewrite only
  # the skills prefix), the .github copy must also flatten .claude/commands and
  # .claude/rules mentions — those files are not carried by a bare symlink.
  (cd "$ROOT/.claude/skills" && find . -type f ! -path '*/__pycache__/*') | while IFS= read -r rel; do
    local src="$ROOT/.claude/skills/$rel"
    local dst="$STAGE/.github/skills/$rel"
    mkdir -p "$(dirname "$dst")"
    sed \
      -e 's|\.claude/skills/|.github/skills/|g' \
      -e 's|\.claude/commands/|.github/prompts/|g' \
      -e 's|\.claude/rules/||g' \
      -e 's|\.claude/||g' \
      "$src" > "$dst"
    if [[ -x "$src" ]]; then chmod +x "$dst"; fi
  done

  # One prompt per skill, pointing at the co-located skill tree. The reference
  # resolves inside .github, so it survives a bare symlink.
  local skilldir sname sdesc
  for skilldir in "$ROOT/.claude/skills/"*/; do
    sname="$(basename "$skilldir")"
    sdesc="$(extract_description "$skilldir/SKILL.md")"
    cat > "$STAGE/.github/prompts/$sname.prompt.md" <<EOF
---
description: "$sdesc"
---

Apply the $sname skill. Read \`.github/skills/$sname/SKILL.md\` and follow
its workflow, using the reference and asset files under
\`.github/skills/$sname/\`. Treat any text after the prompt invocation as
the skill's input.
EOF
  done

  # Self-contained Copilot instructions: inline the agent instructions and the
  # repository rules, with every .claude path rewritten away.
  {
    cat <<'EOF'
<!-- Generated by scripts/sync-mirrors.sh from the canonical sources — do not edit. -->

# GitHub Copilot Instructions

This file is self-contained: it inlines the agent instructions and the
repository rules so the `.github` tree works as a bare symlink into another
repository. Commands live in `.github/prompts/*.prompt.md` (full workflow
each) and skills in `.github/skills/`.

EOF
    echo "## Agent instructions"
    echo
    inline_rules "$ROOT/.claude/instructions.md"
    local rule
    for rule in "$ROOT/.claude/rules/"*.md; do
      echo
      inline_rules "$rule"
    done
  } > "$STAGE/.github/copilot-instructions.md"

  # -- .codex: self-contained ---------------------------------------------
  # Codex reads AGENTS.md for repository guidance. Commands are exposed as
  # prompt files, while reusable workflows retain their SKILL.md structure.
  mkdir -p "$STAGE/.codex/prompts" "$STAGE/.codex/skills"

  for cmd in "$ROOT/.claude/commands/"*.md; do
    name="$(basename "$cmd")"
    sed \
      -e 's|\.claude/skills/|.codex/skills/|g' \
      -e 's|\.claude/commands/|.codex/prompts/|g' \
      -e 's|\.claude/rules/||g' \
      -e 's|\.claude/|.codex/|g' \
      "$cmd" > "$STAGE/.codex/prompts/$name"
  done

  (cd "$ROOT/.claude/skills" && find . -type f ! -path '*/__pycache__/*') | while IFS= read -r rel; do
    local src="$ROOT/.claude/skills/$rel"
    local dst="$STAGE/.codex/skills/$rel"
    mkdir -p "$(dirname "$dst")"
    sed \
      -e 's|\.claude/skills/|.codex/skills/|g' \
      -e 's|\.claude/|.codex/|g' \
      "$src" > "$dst"
    if [[ -x "$src" ]]; then chmod +x "$dst"; fi
  done

  {
    cat <<'EOF'
<!-- Generated by scripts/sync-mirrors.sh from the canonical sources — do not edit. -->

# Repository Instructions

This file is generated from the canonical instructions and rules. The source
of truth is the repository's canonical assistant configuration; regenerate
the Codex mirror with
`scripts/sync-mirrors.sh` after changing canonical instructions, commands, or
skills. Reusable skills are in `.codex/skills/`, and equivalent command
workflows are in `.codex/prompts/`.

## Agent instructions

EOF
    inline_codex_rules "$ROOT/.claude/instructions.md"
    local codex_rule
    for codex_rule in "$ROOT/.claude/rules/"*.md; do
      echo
      inline_codex_rules "$codex_rule"
    done
  } > "$STAGE/.codex/AGENTS.md"

  cat > "$STAGE/.codex/README.md" <<'EOF'
<!-- Generated by scripts/sync-mirrors.sh from the canonical sources — do not edit. -->

# Codex Configuration

This is the generated Codex mirror of the canonical assistant configuration.
Do not edit files here directly. Update the canonical sources, then run
`scripts/sync-mirrors.sh`; use `scripts/sync-mirrors.sh --check` to verify
that all mirrors are current.

## Contents

- `AGENTS.md` — repository-wide instructions and rules for Codex.
- `prompts/` — complete equivalents of the canonical command workflows,
  including `gh-issue-push` and `gh-issue-pop`.
- `skills/` — reusable skills with canonical skill references rewritten
  to stay inside this directory.
- `pixi.toml`, `pixi.lock`, and `scripts/ensure-env.sh` — the portable Python
  environment used by skills that run scripts.

The GitHub issue → worktree → pull-request process remains mandatory. Start a
repository change with the `gh-issue-push` workflow, then use
`gh-issue-pop` before implementation.
EOF

  # Codex discovers repository instructions from the root-level AGENTS.md.
  # Keep the portable .codex tree complete too, so it can also be symlinked or
  # copied into another repository without losing its guidance.
  cp "$STAGE/.codex/AGENTS.md" "$STAGE/AGENTS.md"

  # -- pixi environment ---------------------------------------------------
  # Ship the manifest, lockfile, and preflight into every surface so a
  # symlinked agent directory is self-provisioning. Verbatim copies:
  # ensure-env.sh is self-locating and the manifest is surface-agnostic, so
  # no path rewriting is needed (and nothing here references a sibling tree).
  local surface
  for surface in .cursor .opencode .github .codex; do
    mkdir -p "$STAGE/$surface/scripts"
    cp "$ROOT/.claude/pixi.toml" "$STAGE/$surface/pixi.toml"
    cp "$ROOT/.claude/pixi.lock" "$STAGE/$surface/pixi.lock"
    cp "$ROOT/.claude/scripts/ensure-env.sh" "$STAGE/$surface/scripts/ensure-env.sh"
    chmod +x "$STAGE/$surface/scripts/ensure-env.sh"
  done
}

# Mirror directories managed by this script (relative to repo root). Each is
# owned wholesale (rsync --delete); root-level siblings like .opencode's
# node_modules are never listed, so they are left untouched.
AREAS=(
  ".cursor/commands"
  ".cursor/skills"
  ".cursor/scripts"
  ".opencode/commands"
  ".opencode/skills"
  ".opencode/scripts"
  ".github/prompts"
  ".github/skills"
  ".github/scripts"
  ".codex/prompts"
  ".codex/skills"
  ".codex/scripts"
)

# Single-file artifacts that live at a mirror root (cannot be a --delete area
# without endangering siblings).
FILES=(
  "AGENTS.md"
  ".github/copilot-instructions.md"
  ".codex/AGENTS.md"
  ".codex/README.md"
  ".cursor/pixi.toml"
  ".cursor/pixi.lock"
  ".opencode/pixi.toml"
  ".opencode/pixi.lock"
  ".github/pixi.toml"
  ".github/pixi.lock"
  ".codex/pixi.toml"
  ".codex/pixi.lock"
)

build_stage

# Self-containment guard: nothing under the staged .github may reference a
# sibling canonical tree, or the bare-symlink use case breaks. Checked before
# writing so a leak never lands on disk.
leaks="$(grep -rnE '\.(claude|cursor|opencode)/' "$STAGE/.github" 2>/dev/null || true)"
if [[ -n "$leaks" ]]; then
  echo "ERROR: .github references a sibling canonical tree (breaks symlink use):" >&2
  echo "$leaks" | sed "s|^$STAGE/||" >&2
  exit 1
fi

# The Codex mirror also has to be usable as a self-contained configuration
# tree: generated guidance, prompts, and skills may not escape to .claude/.
leaks="$(grep -rnE '\.claude/' "$STAGE/.codex" 2>/dev/null || true)"
if [[ -n "$leaks" ]]; then
  echo "ERROR: .codex references the canonical .claude tree:" >&2
  echo "$leaks" | sed "s|^$STAGE/||" >&2
  exit 1
fi

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

for file in "${FILES[@]}"; do
  if [[ "$MODE" == "check" ]]; then
    if ! diff "$STAGE/$file" "$ROOT/$file" > /dev/null 2>&1; then
      drift=1
      echo "DRIFT: $file"
      diff "$STAGE/$file" "$ROOT/$file" 2>&1 | head -20 || true
    fi
  else
    mkdir -p "$(dirname "$ROOT/$file")"
    cp "$STAGE/$file" "$ROOT/$file"
    echo "synced: $file"
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
