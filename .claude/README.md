<\!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->

# Claude Code Configuration

This directory contains custom instructions and rules for the Claude Code agent.

## Structure

```
.claude/
├── instructions.md           # Main agent instructions (always applied)
├── rules/                    # Rule files for specific contexts
│   ├── code-prd-architecture-linking.md
│   ├── documentation-standards.md
│   ├── git-workflow.md
│   ├── prd-format.md
│   ├── use-case-format.md
│   ├── crumb-format.md
│   ├── patent-disclosure-format.md
│   ├── vision-format.md
│   └── architecture-format.md
└── commands/                 # Command templates for common workflows
    ├── bootstrap.md
    ├── do-work.md
    ├── do-work-docs.md
    ├── do-work-code.md
    └── make-work.md
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
- **code-prd-architecture-linking.md**: Requirements for linking code to PRDs and architecture docs
- **documentation-standards.md**: Writing style, formatting, figures, and content quality rules
- **prd-format.md**: Product Requirements Document structure and guidelines
- **use-case-format.md**: Use case document structure (tracer bullets, demos)
- **crumb-format.md**: How to structure documentation vs code crumbs
- **vision-format.md**: Vision document structure and guidelines
- **architecture-format.md**: Architecture document structure and guidelines

### commands/
Workflow templates the agent can follow:

- **bootstrap.md**: Create initial VISION.yaml and ARCHITECTURE.yaml for new projects
- **do-work.md**: Router command to choose between docs and code workflows
- **do-work-docs.md**: Workflow for documentation tasks (PRDs, use cases, etc.)
- **do-work-code.md**: Workflow for implementation tasks
- **make-work.md**: Analyze project state and propose new work items

## How It Works

Claude Code automatically loads `instructions.md` when working in this repository. The agent can reference rules and commands as needed during work.

## Mirrored Configurations

This setup mirrors configurations in:
- `.cursor/` - for Cursor AI
- `.github/` - for GitHub Copilot

This ensures consistent behavior across all AI coding assistants.
