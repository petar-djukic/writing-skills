# The `writing-voice/` Directory Contract

Any writing repository may carry a `writing-voice/` directory of exemplar
samples that define the target voice for text generated in that repository.
The prose skills read it: `filter-tells` measures drafts against it and steers
rewrites toward it, and `match-structure` accepts it as a curated exemplar source.
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

## Two independent axes

`role` says **whose voice** a sample is. `pre_ai` says **whether it is safe to
anchor diction on**. They are independent, and the second cannot be expressed
by the first:

| Stratum | role | anchor for |
|---|---|---|
| author papers, pre-AI | `author-voice` | diction, precision |
| peer essays, pre-AI | `venue-voice` | diction **and punch** |
| anything AI-era | either | genre and structure only, **never diction** |

`--role venue-voice` returns the pre-AI punch anchors and the AI-era samples
together — the ones that must never anchor diction. `--stratum pre-ai` cuts
across roles and returns only what is safe.

```yaml
- id: yegge-2011-google-platforms-rant
  file: Yegge-2011-stevey-s-google-platforms-rant.md
  role: venue-voice
  year: 2011
  pre_ai: true        # optional; absent, inferred from year < 2022
```

Prose written once generative AI was available may carry AI diction, which
makes it circular as a diction anchor. `pre_ai` is optional and the year infers
it, but an explicit value wins: where the line falls for a given piece is the
curator's knowledge, not arithmetic — a 2023 draft may predate their model
access, and a 2021 one may not.

## Roles and precedence

`author-voice` is the voice to match; `venue-voice` supplies genre convention
where the author has no sample in that form. Tools prefer `author-voice`
anchors and fall back to `venue-voice`. A repository may carry only one role.

## Discovery

A tool given a file walks up from that file's directory to the repository root
looking for `writing-voice/`. Absent, behavior is unchanged — voice features
are additive, never required.

## Consumers

- **filter-tells** — builds a baseline profile from the samples (metrics reported as
  distances from it, not only against fixed thresholds) and injects
  topically-nearest exemplar passages into rewrite and overshoot prompts as
  voice anchors.
- **match-structure** — accepts the manifest as a curated exemplar source, so a
  repository without a `references.yaml` corpus can still use persona
  extraction and comparison.
- **match-voice** — retrieves the same anchors and sends them with the
  paragraph to a second model family, then gates the candidate on citation and
  number preservation, meaning entailment, anchor similarity, and register. Its
  driver carries the before/after Pangram measurement, since the baseline can
  only be captured before the rewrite starts.
- **do-work** — its Prose workflow reads the manifest and the nearest samples
  before drafting, and scans the produced prose with filter-tells before committing,
  so a writing repository gets the rule from the workflow rather than from a
  per-repo note. Repositories without `writing-voice/` are unaffected.

- **Pangram check** — an optional external measurement, and the only consumer
  that sends text off the machine. Governed by the consent rule below.
- **filter-tells's eval harness** — uses the `author-voice` exemplars as the human
  class when calibrating detector false-positive rates. It reads them in place
  and records provenance rather than text, so a private corpus stays private;
  the skills directory is shared by symlink, and samples copied into it would
  be published with the skills. What belongs in the corpus is the curator's
  call, but the harness warns about exemplars dated after 2022, since prose
  written once generative AI was available is circular as ground truth for what
  human prose looks like.

Reference implementation of the directory: `petar-djukic/autogenic-systems`
(`writing-voice/`, 28 exemplars — 24 `author-voice`, 4 `venue-voice`).

## Uploading a draft to an external detector

Every other tool here runs locally. `match-voice` prefers a local model
precisely so unpublished prose stays on the machine. An external AI detector
breaks that deliberately, so it asks first — every time.

**Ask before every upload.** Name the file, name the destination
(`text.external-api.pangram.com`), and say that the text is retained and
reachable through a `dashboard_link` on the vendor's site. Proceed only on a
clear yes.

**Per document, every time.** Not once per session, not implied by a key. A key
in the environment says the user has an account with the vendor; it says
nothing about whether *this* document may leave the machine. Sessions cover
many files, and one blanket yes cannot be informed consent for a file the user
had not thought about yet. An upload cannot be taken back.

**Refuse some documents even with consent in hand.** Anything under embargo or
NDA, and any unpublished claim where disclosure could bear on prior art, gets
raised rather than uploaded. The user may still say yes; they should say it
knowing that.

**No key, or a declined prompt, means skip.** Say the check was skipped. Never
pass silently, and never present a local filter-tells result as though it were the
external one — the whole value of an outside detector is that it is outside.

**A result is evidence, not a verdict.** It never certifies a document on its
own; see filter-tells's Verdict Validity Rules.
