# writing-skills

Claude Code skills that rewrite AI-drafted prose until it reads as human, measured against the Pangram detector, with reference management and citation auditing alongside.

An AI-generated draft reveals itself in three ways — rhetorical scaffolding, semantic tells, and the drafting model's lexical fingerprint — and fixing one leaves the other two untouched. The pipeline attacks all three in sequence — a structural pass reshapes the prose away from its source, a semantic pass erases the tells, and a cross-model diction pass strips the model's imprint — with a detector score recorded before and after each step. Verified on a published article: 100% AI to mixed, mean window score 0.993 to 0.576.

```mermaid
flowchart LR
    A[AI draft] --> B[tighten-style or match-outline]
    B --> C[filter-tells]
    C --> D[match-voice, second model family]
    D --> E[Pangram score]
    E -->|before/after recorded| A
```

## Scope and Status

The repository hosts 11 skills and 3 commands, canonical under `.claude/`. The prose pipeline consists of `humanize` (the three-step orchestrator), `filter-tells`, `match-voice`, `match-outline`, `match-structure`, `tighten-style`, and `tune-anchors`. Reference handling uses `update-references` and `audit-references`, which keep a CSL-YAML bibliography current and checked against retrieved sources. `patent-disclosure` populates an eleven-section invention-disclosure template, while `pattern-language` extracts Alexandrian pattern languages from repositories. The commands — `brainstorm-article`, `write-article`, `seo-pass` — drive an end-to-end article pipeline. History traces back to [coding-skills](https://github.com/petar-djukic/coding-skills), where these skills lived through August 2026; the coding commands remain there.

## Documentation

The pipeline is described in [How to Build a Writing Pipeline](https://meshintelligence.substack.com/p/how-to-build-a-writing-pipeline?utm_source=github&utm_campaign=writing-skills) — the three passes, why fixing one tell class leaves the others, and the detector scores before and after each step.

Two books draft their chapters through it: [agentic-coding-book](https://github.com/petar-djukic/agentic-coding-book) and [agentic-applications-book](https://github.com/petar-djukic/agentic-applications-book). Chapters run as articles first, so the skills here are what shapes them.

## Methodology

The target voice sits in a `writing-voice/` directory of exemplar prose — the contract is in [.claude/rules/writing-voice.md](.claude/rules/writing-voice.md). Skills gauge a draft's distance from that corpus, pull anchors from it, and gate every rewrite: a candidate must keep citations, numbers, and meaning, or the original remains. The external Pangram check is consent-gated per document; everything else runs locally against an Ollama endpoint.

## Repository Structure

```
.claude/skills/      the 11 skills, one directory each
.claude/commands/    brainstorm-article, write-article, seo-pass
.claude/rules/       writing-voice contract, technical document types
.claude/scripts/     shared plumbing: credentials, Pangram client, prose parsing
scripts/             mirror sync
```

## Environment

[pixi](https://pixi.sh/) manages Python dependencies. `pixi.toml` and `pixi.lock` ship in `.claude/`, and `.claude/scripts/ensure-env.sh` provisions the locked environment. Credentials (`pangram`, `serpapi`, `semantic_scholar`) resolve through a gitignored `.secrets/` directory per the contract in the skills' documentation; no credential is ever committed or printed.

## License

MIT. See [LICENSE](LICENSE).
