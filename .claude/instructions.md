<!-- Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT -->

# Agent Instructions

Issue tracking uses GitHub Issues via the `gh` CLI. The `/do-work` and `/git-issue-pop` commands handle the full workflow: fetching issues, assigning tasks, tracking sub-issues, and opening pull requests.

## Pre-Commit Quality Gate

Before committing, run `mage analyze` and fix all reported YAML schema errors. The analyze target checks cross-artifact consistency (PRDs, use cases, test suites, roadmap) and validates YAML fields against Go structs. Unrecognized fields cause data loss in the measure prompt. Do not commit with analyze errors.

## Commit After Every Edit

After creating or editing any file, run `mage analyze`, fix any errors, then commit. Do not accumulate uncommitted changes across multiple turns. Each round of edits gets its own commit before responding to the user. This applies to all file types: code, docs, rules, config.

## Code Implementation

Go style and code standards are defined in `docs/constitutions/go-style.yaml` and `docs/constitutions/execution.yaml`. These are passed to Claude via the cobbler prompts and do not need to be duplicated here.

## Scaffolding

This repository scaffolds orchestration into target Go repositories.

- `mage scaffold:push <target>` installs the orchestrator (template, constitutions, prompts, config, go.mod wiring)
- `mage scaffold:pop <target>` removes all scaffolded files from the target
- Both accept `.` for the current directory, but self-targeting is blocked (push/pop refuse when the target resolves to the orchestrator repo)
- `configuration.yaml` is auto-created with defaults if missing when any mage target runs

## Documentation

Follow [rules/documentation-standards.md](rules/documentation-standards.md) (distilled from `docs/constitutions/design.yaml`):

- Specification-driven: specs are source of truth, code serves specs
- YAML-first for structured documents, markdown for prose
- Active voice, concise, no forbidden terms
- Traceability chain: Vision -> Architecture -> PRDs -> Use cases -> Test suites -> Code

For README files specifically, see [rules/readme-format.md](rules/readme-format.md).

## Constitutions (Full Reference)

- `docs/constitutions/planning.yaml` — Task sizing, issue structure, dependency ordering (measure phase)
- `docs/constitutions/execution.yaml` — Code standards, design patterns, traceability (stitch phase)
- `docs/constitutions/design.yaml` — Document types, format rules, completeness checklists (design phase)
- `docs/constitutions/go-style.yaml` — Go coding style, patterns, code review checklist
