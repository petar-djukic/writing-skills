<\!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->

# Claude Code Configuration

This directory contains custom instructions and rules for the Claude Code agent.

## Structure

```
.claude/
├── instructions.md           # Main agent instructions (always applied)
├── rules/                    # Rule files for specific contexts
│   ├── documentation-standards.md
│   ├── git-workflow.md
│   ├── pixi-python.md
│   ├── readme-format.md
│   └── technical-document-types.md
├── skills/                   # Model-invoked skills (not mirrored as commands)
│   ├── audit-references/
│   ├── de-ai/
│   ├── match-voice/
│   ├── patent-disclosure/
│   └── update-references/
└── commands/                 # Command templates for common workflows
    ├── align-specs.md
    ├── bd-issue-pop.md
    ├── bd-issue-push.md
    ├── bd-issue-show.md
    ├── bootstrap.md
    ├── do-work.md
    ├── do-work-docs.md
    ├── do-work-code.md
    ├── exp-start.md
    ├── exp-stop.md
    ├── gh-issue-pop.md
    ├── gh-issue-push.md
    ├── gh-issue-show.md
    ├── gh-release-push.md
    ├── make-work.md
    └── test-clone.md
```

## Files

### instructions.md
Main configuration file that Claude Code loads automatically. Contains:
- GitHub Issues tracking workflow
- Token tracking requirements
- Session completion checklist

### rules/
Context-specific rules that govern how the agent works:

- **git-workflow.md**: Issue tracking, worktree discipline, PR workflow
- **technical-document-types.md**: Catalog of external document types (concept paper through invention disclosure) with origins and structures
- **code-prd-architecture-linking.md**: Requirements for linking code to PRDs and architecture docs
- **documentation-standards.md**: Writing style, formatting, figures, and content quality rules
- **prd-format.md**: Product Requirements Document structure and guidelines
- **use-case-format.md**: Use case document structure (tracer bullets, demos)
- **crumb-format.md**: How to structure documentation vs code crumbs
- **vision-format.md**: Vision document structure and guidelines
- **architecture-format.md**: Architecture document structure and guidelines

### commands/
Workflow templates the agent can follow:

- **align-specs.md**: Align specifications across PRDs, use cases, and test suites
- **bd-issue-pop.md**: Pop a bead into a worktree, work on it, and open a PR (beads workflow)
- **bd-issue-push.md**: Create a bead with ripple-effect analysis (beads workflow)
- **bd-issue-show.md**: List or inspect beads in the current repository
- **bootstrap.md**: Create initial VISION.yaml and ARCHITECTURE.yaml for new projects
- **do-work.md**: Router command to choose between docs and code workflows
- **do-work-docs.md**: Workflow for documentation tasks (PRDs, use cases, etc.)
- **do-work-code.md**: Workflow for implementation tasks
- **exp-start.md**: Create or join an experiment branch in a worktree — local-only by default, or remote-backed (`--remote <owner/repo>`) with two-way `git subtree` sync under a deterministic prefix (`experiments/<slug>`), metadata recorded in `.exp-sync.yaml` on the branch so other machines can rejoin
- **exp-stop.md**: Conclude and delete an experiment branch; remote-backed experiments additionally show subtree sync state and warn that content pushed to the external repository survives local cleanup (external branch deletion is opt-in only)
- **gh-issue-pop.md**: Pop a GitHub issue into a worktree, decompose, and open a PR
- **gh-issue-push.md**: Create a GitHub issue with ripple-effect analysis
- **gh-issue-show.md**: List or inspect GitHub issues
- **gh-release-push.md**: Run the full release workflow: audit, test, tag, and push
- **make-work.md**: Analyze project state and propose new work items
- **test-clone.md**: Clone and test the repository in an isolated environment

## How It Works

Claude Code automatically loads `instructions.md` when working in this repository. The agent can reference rules and commands as needed during work.

## Mirrored Configurations

This setup is mirrored across assistant surfaces:

- `.cursor/` — Cursor AI: full mirror of `commands/` and `skills/` (skill-internal paths rewritten to `.cursor/skills/...`; commands carry generated front matter)
- `.opencode/` — OpenCode: full mirror of `commands/` and `skills/` (same treatment)
- `.github/` — GitHub Copilot: self-contained so it works as a bare symlink into another repository. `copilot-instructions.md` inlines the agent instructions and rules; `prompts/*.prompt.md` inline the full workflow of each command and one prompt per skill; `skills/` holds the skill trees with paths rewritten to `.github/skills/...`. Nothing under `.github/` references `.claude/`, `.cursor/`, or `.opencode/` — the sync enforces this and fails if a reference leaks

`.claude/` is canonical. Mirrors are generated, never edited directly: `scripts/sync-mirrors.sh` regenerates all of them, and `scripts/sync-mirrors.sh --check` reports drift (nonzero exit) without writing. Run the sync in the same change that edits commands or skills.
