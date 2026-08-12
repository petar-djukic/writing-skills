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
#   AGENTS.md                              generated, concise root guidance for
#                                          Codex: the mandatory workflow plus
#                                          links to canonical rule files
#   .agents/skills/<cmd>/SKILL.md          each canonical command as a
#                                          Codex-discoverable command skill
#   .agents/skills/<name>/**               copied skill trees, with paths
#                                          rewritten to stay in .agents/
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

# Canonical command files: real files, never symlinks. A checkout may link
# another repository's commands into .claude/commands/ for local use — the
# coding workflow from coding-skills is the worked case — and the glob
# dereferences them, so they were copied into all four generated surfaces and
# --check then reported drift forever against the committed mirrors (GH-5).
# They belong to the repository that owns them.
canonical_commands() {
  local f
  for f in "$ROOT/.claude/commands/"*.md; do
    if [ -f "$f" ] && [ ! -L "$f" ]; then printf '%s\n' "$f"; fi
  done
  return 0
}

# First sentence of a file's opening paragraph. extract_description returns the
# first prose *line*, which is right for front-matter descriptions but stops
# mid-clause on a hard-wrapped rule file.
extract_summary() {
  awk '
    /^<!--/ { next }
    /^#/ { next }
    /^[[:space:]]*$/ { if (started) exit; next }
    { started=1; printf "%s ", $0 }
  ' "$1" | sed 's/  */ /g; s/ $//; s/\. .*/./'
}

# First markdown H1 of a file, without the hash; the file stem if it has none.
extract_title() {
  local t
  t="$(awk '/^# / { sub(/^# +/, ""); print; exit }' "$1")"
  [ -n "$t" ] || t="$(basename "$1" .md)"
  printf '%s' "$t"
}

build_stage() {
  local target cmdfile name cdesc
  for target in .cursor .opencode; do
    mkdir -p "$STAGE/$target/commands" "$STAGE/$target/skills"
    # commands: canonical body prefixed with front matter (description) so
    # Cursor/OpenCode display it. Files whose canonical form already has
    # front matter keep it (no double wrap). The skills prefix is rewritten
    # to this surface, as it is for the skills tree below: a command copied
    # verbatim still named .claude/skills/, so a repository mounting only
    # .cursor had commands pointing at a tree it had not linked (GH-4).
    while IFS= read -r cmdfile; do
      name="$(basename "$cmdfile")"
      if head -1 "$cmdfile" | grep -q '^---$'; then
        sed "s|\.claude/skills/|$target/skills/|g" "$cmdfile" \
          > "$STAGE/$target/commands/$name"
      else
        cdesc="$(extract_description "$cmdfile")"
        {
          printf -- '---\ndescription: "%s"\n---\n\n' "$cdesc"
          sed "s|\.claude/skills/|$target/skills/|g" "$cmdfile"
        } > "$STAGE/$target/commands/$name"
      fi
    done < <(canonical_commands)
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
  # front matter, so the prompt stands alone with no pointer to .claude. The
  # body takes the same rewrites as the skills copy below and as .agents —
  # omitting them here was GH-1/GH-4: a command that named a skill script by
  # its canonical path put a .claude/ string in the staged prompt, the
  # self-containment guard caught it, and the script aborted before writing
  # any mirror at all.
  local cmd desc
  while IFS= read -r cmd; do
    name="$(basename "$cmd" .md)"
    desc="$(extract_description "$cmd")"
    {
      printf -- '---\ndescription: "%s"\n---\n\n' "$desc"
      printf 'Execute the /%s command. The full workflow follows; treat any\n' "$name"
      printf 'text after the prompt invocation as its arguments ($ARGUMENTS).\n\n'
      command_body "$cmd" | sed \
        -e 's|\.claude/skills/|.github/skills/|g' \
        -e 's|\.claude/commands/|.github/prompts/|g' \
        -e 's|\.claude/rules/||g' \
        -e 's|\.claude/||g'
    } > "$STAGE/.github/prompts/$name.prompt.md"
  done < <(canonical_commands)

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
    # An empty skills directory leaves the glob unexpanded, and the literal
    # */ then reached awk as a filename. Found while testing the empty-area
    # guard above (GH-18); the same emptying that produced that case produces
    # this one.
    [ -d "$skilldir" ] || continue
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

  # -- Codex: .agents/skills + a concise root AGENTS.md --------------------
  # Codex discovers repository skills from .agents/skills. Project-local
  # .codex/prompts is a deprecated prompt format and .codex/skills is not a
  # discovery location, so neither is generated. AGENTS.md carries durable
  # repository guidance and links to canonical detail rather than inlining it.
  mkdir -p "$STAGE/.agents/skills"

  # Every canonical command becomes a Codex-discoverable command skill with the
  # complete workflow inline.
  while IFS= read -r cmd; do
    name="$(basename "$cmd" .md)"
    cdesc="$(extract_description "$cmd")"
    mkdir -p "$STAGE/.agents/skills/$name"
    {
      printf -- '---\nname: "%s"\ndescription: "%s"\n---\n\n' "$name" "$cdesc"
      printf '# %s command\n\n' "$name"
      printf 'Apply this command workflow. Treat any text after its invocation as the command input.\n\n'
      command_body "$cmd" | sed \
        -e 's|\.claude/skills/|.agents/skills/|g' \
        -e 's|\.claude/commands/|.agents/skills/|g' \
        -e 's|\.claude/rules/||g' \
        -e 's|\.claude/|.agents/|g'
    } > "$STAGE/.agents/skills/$name/SKILL.md"
  done < <(canonical_commands)

  # Reusable skill trees, with canonical path references rewritten to stay
  # inside .agents.
  (cd "$ROOT/.claude/skills" && find . -type f ! -path '*/__pycache__/*') | while IFS= read -r rel; do
    local src="$ROOT/.claude/skills/$rel"
    local dst="$STAGE/.agents/skills/$rel"
    mkdir -p "$(dirname "$dst")"
    sed \
      -e 's|\.claude/skills/|.agents/skills/|g' \
      -e 's|\.claude/commands/|.agents/skills/|g' \
      -e 's|\.claude/rules/||g' \
      -e 's|\.claude/|.agents/|g' \
      "$src" > "$dst"
    if [[ -x "$src" ]]; then chmod +x "$dst"; fi
  done

  # Root AGENTS.md: durable, concise repository guidance. Codex reads this for
  # repository-wide instructions; task detail lives in the linked canonical
  # sources and in the discovered skills, not inlined here.
  #
  # Everything below is enumerated from what this repository carries. It used
  # to be one fixed heredoc — the only part of this script not derived from
  # .claude/ — so after the split it named four commands and linked four rule
  # files that exist in coding-skills and not here (GH-5). A generated file
  # asserting things that are not true is worse than no file.
  local agents_names agents_count
  {
    cat <<'AGENTSEOF'
<!-- Generated by scripts/sync-mirrors.sh from the canonical sources — do not edit. -->

# Repository Instructions

Assistant configuration is canonical under `.claude/`. Codex discovers this
repository's skills from `.agents/skills/` (generated). Regenerate every
surface with `scripts/sync-mirrors.sh`; verify with `--check`.
AGENTSEOF

    # The issue → worktree → PR workflow is the rule only where the commands
    # implementing it are canonical here. A symlinked copy belongs to the
    # repository it came from and does not make this one's workflow.
    if [ -f "$ROOT/.claude/commands/gh-issue-pop.md" ] &&
       [ ! -L "$ROOT/.claude/commands/gh-issue-pop.md" ] &&
       [ -f "$ROOT/.claude/commands/do-work.md" ] &&
       [ ! -L "$ROOT/.claude/commands/do-work.md" ]; then
      cat <<'AGENTSEOF'

## Mandatory workflow: issue → worktree → pull request

All work goes through a GitHub issue and a pull request. Never commit to
`main` directly.

1. **File an issue first** — run the `gh-issue-push` skill. It enumerates
   every file the change touches before drafting, so nothing is missed.
   (Beads repositories use `bd-issue-push` instead.)
2. **Pop it into a worktree** — run the `gh-issue-pop` skill. All
   implementation happens inside the worktree at `../gh-<number>-<slug>`,
   never in the main checkout, which stays on `main`.
3. **Do the work** — run the `do-work` skill inside the worktree, once per
   sub-issue, until the epic is complete. It detects the tracker (GitHub
   issues or beads) and works either.
4. **Open the PR** — the pop skill's final phase opens it, records the actual
   lines of code against the estimate, and closes the issue on merge.

One issue per logical change; small fixes still need an issue. The only
exceptions are an emergency hotfix authorized in-session and `exp/*`
experiment branches, which never merge to `main`.
AGENTSEOF
    fi

    printf '\n## Skills and commands\n\n'
    printf 'Codex discovers both from `.agents/skills/`.\n\n'

    agents_names="$(
      for d in "$ROOT/.claude/skills/"*/; do
        [ -d "$d" ] || continue
        basename "$d"
      done | sort | awk '{printf "%s%s", sep, $0; sep=", "} END {print ""}'
    )"
    # find, not `ls -d .../*/`: an unmatched glob makes ls exit non-zero, and
    # under `set -o pipefail` that failed the assignment and aborted the whole
    # script before it printed anything — an empty .claude/skills produced a
    # silent exit 1 (GH-18). find reports an empty directory as zero results.
    agents_count="$(find "$ROOT/.claude/skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
    if [ -n "$agents_names" ]; then
      printf 'Reusable skills (%s): %s.\n\n' "$agents_count" "$agents_names"
    fi

    agents_names="$(canonical_commands | while IFS= read -r c; do
        basename "$c" .md
      done | sort | awk '{printf "%s%s", sep, $0; sep=", "} END {print ""}')"
    agents_count="$(canonical_commands | wc -l | tr -d ' ')"
    if [ -n "$agents_names" ]; then
      printf 'Command workflows (%s), each carrying its full workflow inline: %s.\n' \
        "$agents_count" "$agents_names"
    fi

    printf '\nPython-backed skills run in a pixi environment that ships beside them:\n'
    printf 'run `.agents/scripts/ensure-env.sh` once per machine, then invoke scripts\n'
    printf 'with `pixi run --manifest-path .agents/pixi.toml python <script>`.\n'
    if [ -f "$ROOT/.claude/rules/secrets.md" ]; then
      printf 'API credentials resolve through the repository'"'"'s gitignored `.secrets/`\n'
      printf 'directory, never from the skills tree — see the secrets rule below.\n'
    fi

    printf '\n## Conventions\n\n'
    printf 'These are summaries; the canonical rule files hold the detail.\n\n'
    local rulefile
    for rulefile in "$ROOT/.claude/rules/"*.md; do
      [ -f "$rulefile" ] || continue
      printf -- '- **%s** — %s See `.claude/rules/%s`.\n' \
        "$(extract_title "$rulefile")" \
        "$(extract_summary "$rulefile")" \
        "$(basename "$rulefile")"
    done

    printf '\nBefore committing, run the repository'"'"'s consistency check if it defines\n'
    printf 'one, and commit after each round of edits rather than accumulating them.\n'
  } > "$STAGE/AGENTS.md"

  # -- pixi environment ---------------------------------------------------
  # Ship the manifest, lockfile, and preflight into every surface so a
  # symlinked agent directory is self-provisioning. Verbatim copies:
  # ensure-env.sh is self-locating and the manifest is surface-agnostic, so
  # no path rewriting is needed (and nothing here references a sibling tree).
  local surface
  for surface in .cursor .opencode .github .agents; do
    mkdir -p "$STAGE/$surface/scripts"
    # Guarded, so a repository with no Python-backed skills stages no manifest
    # rather than dying here on a missing source — which would abort before the
    # FILES loop below could remove the stale mirror copies.
    [[ -f "$ROOT/.claude/pixi.toml" ]] && cp "$ROOT/.claude/pixi.toml" "$STAGE/$surface/pixi.toml"
    [[ -f "$ROOT/.claude/pixi.lock" ]] && cp "$ROOT/.claude/pixi.lock" "$STAGE/$surface/pixi.lock"
    # Every shared script, not a hardcoded filename: naming one file meant the
    # next script added to .claude/scripts/ was silently missing from all four
    # surfaces, and the skills that import it fell back to whatever else
    # answered to that name (GH-184, credentials.py).
    local f base
    for f in "$ROOT/.claude/scripts/"*; do
      [ -f "$f" ] || continue
      base="$(basename "$f")"
      cp "$f" "$STAGE/$surface/scripts/$base"
      case "$base" in
        *.sh|*.py) chmod +x "$STAGE/$surface/scripts/$base" ;;
      esac
    done
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
  ".agents/skills"
  ".agents/scripts"
)

# Single-file artifacts that live at a mirror root (cannot be a --delete area
# without endangering siblings).
FILES=(
  "AGENTS.md"
  ".github/copilot-instructions.md"
  ".cursor/pixi.toml"
  ".cursor/pixi.lock"
  ".opencode/pixi.toml"
  ".opencode/pixi.lock"
  ".github/pixi.toml"
  ".github/pixi.lock"
  ".agents/pixi.toml"
  ".agents/pixi.lock"
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

# Generated Codex skills must be self-contained: a skill tree may not escape
# to .claude/. (Root AGENTS.md deliberately links canonical rule files, so it
# is excluded from this check.)
leaks="$(grep -rnE '\.claude/' "$STAGE/.agents" 2>/dev/null || true)"
if [[ -n "$leaks" ]]; then
  echo "ERROR: .agents references the canonical .claude tree:" >&2
  echo "$leaks" | sed "s|^$STAGE/||" >&2
  exit 1
fi

drift=0
for area in "${AREAS[@]}"; do
  # An area with no canonical content stages as an empty directory, and git
  # cannot track one, so no committed tree can ever match it: --check would
  # report drift on every clean checkout and sync would leave stray empty
  # directories behind. coding-skills hit this on all seven skills/scripts
  # areas once the split emptied its .claude/skills and .claude/scripts
  # (coding-skills GH-381, ported here as GH-18). Empty stage against an
  # absent or empty target is agreement.
  if [[ -z "$(ls -A "$STAGE/$area" 2>/dev/null)" ]] &&
     [[ -z "$(ls -A "$ROOT/$area" 2>/dev/null)" ]]; then
    continue
  fi
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
  # A file absent from the stage is one the canonical tree no longer carries
  # (e.g. pixi manifests in a repository with no Python-backed skills): remove
  # the mirror copy rather than fail the sync.
  if [[ ! -f "$STAGE/$file" ]]; then
    if [[ "$MODE" == "check" ]]; then
      if [[ -f "$ROOT/$file" ]]; then drift=1; echo "DRIFT: $file (stale, no canonical source)"; fi
    else
      rm -f "$ROOT/$file"
    fi
    continue
  fi
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
