# The `writing-voice/` Directory Contract

Any writing repository may carry a `writing-voice/` directory of exemplar
samples that define the target voice for text generated in that repository.
The prose skills read it: `de-ai` measures drafts against it and steers
rewrites toward it, and `match-voice` accepts it as a curated exemplar source.
The contract is generic — the same layout works in any repository.

## Layout

```
writing-voice/
  manifest.yaml                 the contract below
  <Author>-<Year>-<slug>.md     one markdown file per exemplar
  .voice-profile.json           generated cache (gitignorable)
```

One markdown file per exemplar, plus the manifest. Sample files carry prose,
not markup scaffolding — a converted paper is fine, a LaTeX source is not
(convert it first).

## `manifest.yaml`

```yaml
purpose: >
  What these samples are for, in this repository.
updated: '2026-07-25'
target_document: the work whose voice these samples define
roles:
  author-voice: Written or co-written by the repository owner before the
    generative-AI era; the primary voice to match.
  venue-voice: Not by the author, published before 2022 in the target venue's
    genre; establishes the register of the venue.
exemplars:
  - id: djukic-2007-icc-distributed-scheduling   # stable key
    file: Djukic-2007-distributed-link-scheduling-...md   # relative to writing-voice/
    role: author-voice                            # author-voice | venue-voice
    venue: IEEE ICC
    year: 2007
    source: papers/Djukic-2007-...md              # where the sample came from
    notes: Conference register; distributed-algorithm exposition, compact
      problem statement, simulation-backed claims.
```

Required per exemplar: `id`, `file`, `role`. `venue`, `year`, `source`, and
`notes` are recommended — `notes` is read by humans choosing exemplars and by
the anchor-retrieval step when ranking ties.

## Roles and precedence

`author-voice` is the voice to match; `venue-voice` supplies genre convention
where the author has no sample in that form. Tools prefer `author-voice`
anchors and fall back to `venue-voice`. A repository may carry only one role.

## Discovery

A tool given a file walks up from that file's directory to the repository root
looking for `writing-voice/`. Absent, behavior is unchanged — voice features
are additive, never required.

## Consumers

- **de-ai** — builds a baseline profile from the samples (metrics reported as
  distances from it, not only against fixed thresholds) and injects
  topically-nearest exemplar passages into rewrite and overshoot prompts as
  voice anchors.
- **match-voice** — accepts the manifest as a curated exemplar source, so a
  repository without a `references.yaml` corpus can still use persona
  extraction and comparison.

Reference implementation of the directory: `petar-djukic/autogenic-systems`
(`writing-voice/`, 28 exemplars — 24 `author-voice`, 4 `venue-voice`).
