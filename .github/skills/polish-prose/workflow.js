// Copyright (c) 2026 Petar Djukic. All rights reserved. SPDX-License-Identifier: MIT
export const meta = {
  name: 'polish-prose',
  description: 'Polish one prose file: humanize it, then loop critics, rule-based fixes and cold review until a panel read of the final text changes nothing',
  whenToUse: 'Improve, polish, tighten or make better any prose a person reads end to end (essay, post, paper section, README, chapter): the humanize chain once, then reverse-outline, length pre-check, a critic panel answering the focus brief, critic-apply, cold review, ross read and voice-critic, re-reading until the text stops changing',
  phases: [
    { title: 'Preflight', detail: 'worktree branch, skill paths, focus file, baseline commit' },
    { title: 'Humanize', detail: 'the humanize chain, once' },
    { title: 'Review', detail: 'outline, length, panel, apply, cold review, ross, voice-critic; repeats while prose changes' },
    { title: 'Final read', detail: 'read-only panel on the shipping text when the round cap stopped the loop' },
    { title: 'Record', detail: 'generation note, sidecar sweep, report' },
  ],
}

const A = args || {}
const ART = A.article || A.file
if (!ART) throw new Error('polish-prose: args.article (path to the markdown file) is required')
const SK = A.skills_dir || 'skills'
const MAX = A.max_rounds || 3
const ROSS_FIX_ROUNDS = 2
const STEM = ART.replace(/\.md$/, '')
const DEFAULT_ROSTER = ['Levine', 'Didion', 'Hemingway']
const REQUIRED_SKILLS = ['humanize', 'reverse-outline', 'critic-panel', 'critic-apply', 'cold-review', 'voice-critic']

const NO_PROSE = 'You never write article prose yourself. Text changes only through the owning skill: rewrites go through the rewrite transport, deletions and verbatim reverts apply mechanically.'
const HYGIENE = `Before you return, delete every sidecar this stage created or consumed (reading copies, critic reports, sheets, *.applied.md, JSON reports), and only files whose names start with ${STEM}. The article file is the only file you may leave changed.`

const PREFLIGHT = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    reason: { type: 'string' },
    branch: { type: 'string' },
    missing: { type: 'array', items: { type: 'string' } },
    focus_file: { type: 'string' },
    focus_items: { type: 'array', items: { type: 'string' } },
    precheck_command: { type: 'string' },
    form: { type: 'string' },
    protected_spans: { type: 'array', items: { type: 'string' } },
    roster_name: { type: 'string' },
    roster: { type: 'array', items: { type: 'string' } },
    draft_rules: { type: 'array', items: { type: 'string' } },
    has_front_matter: { type: 'boolean' },
    has_voice_corpus: { type: 'boolean' },
    has_voice_constitution: { type: 'boolean' },
    baseline_sha: { type: 'string' },
  },
  required: ['ok', 'reason', 'branch', 'missing', 'focus_file', 'focus_items', 'precheck_command', 'form', 'protected_spans',
    'roster_name', 'roster', 'draft_rules', 'has_front_matter', 'has_voice_corpus', 'has_voice_constitution', 'baseline_sha'],
}

const HUMANIZE = {
  type: 'object',
  properties: {
    ran: { type: 'boolean' },
    seed_reach: { type: 'string' },
    stages: { type: 'array', items: { type: 'object', properties: { stage: { type: 'string' }, score: { type: 'string' } }, required: ['stage', 'score'] } },
    notes: { type: 'string' },
  },
  required: ['ran', 'seed_reach', 'stages', 'notes'],
}

const OUTLINE = {
  type: 'object',
  properties: {
    round_start_sha: { type: 'string' },
    cheap_paragraphs: { type: 'array', items: { type: 'integer' } },
    split_paragraphs: { type: 'array', items: { type: 'integer' } },
    eroded: { type: 'array', items: { type: 'string' } },
    copy_path: { type: 'string' },
    total_words: { type: 'integer' },
    flagged_paragraphs: { type: 'array', items: { type: 'string' } },
  },
  required: ['round_start_sha', 'cheap_paragraphs', 'split_paragraphs', 'eroded', 'copy_path', 'total_words', 'flagged_paragraphs'],
}

const SHEET = {
  type: 'object',
  properties: {
    sheet_path: { type: 'string' },
    convergent: { type: 'array', items: { type: 'object', properties: { passage: { type: 'string' }, why: { type: 'string' }, critics: { type: 'integer' } }, required: ['passage', 'why', 'critics'] } },
    paragraph_moves: { type: 'array', items: { type: 'string' } },
    classes: { type: 'array', items: { type: 'string' } },
    focus_answers: { type: 'array', items: { type: 'string' } },
    single_critic: { type: 'integer' },
  },
  required: ['sheet_path', 'convergent', 'paragraph_moves', 'classes', 'focus_answers', 'single_critic'],
}

const APPLY = {
  type: 'object',
  properties: {
    candidate_path: { type: 'string' },
    applied: { type: 'integer' },
    kept: { type: 'integer' },
    declined: { type: 'integer' },
    unapplied_convergent: { type: 'array', items: { type: 'string' } },
  },
  required: ['candidate_path', 'applied', 'kept', 'declined', 'unapplied_convergent'],
}

const COLD = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['ship as-is', 'ship with reverts', 'reject candidate'] },
    reverts: { type: 'array', items: { type: 'string' } },
    committed_sha: { type: 'string' },
  },
  required: ['verdict', 'reverts', 'committed_sha'],
}

const ROSS = {
  type: 'object',
  properties: {
    legs: { type: 'array', items: { type: 'string' } },
    convergent: { type: 'array', items: { type: 'string' } },
    reserved: { type: 'array', items: { type: 'string' } },
    sheet_path: { type: 'string' },
  },
  required: ['legs', 'convergent', 'reserved', 'sheet_path'],
}

const VOICE = {
  type: 'object',
  properties: {
    failed: { type: 'array', items: { type: 'string' } },
    flags: { type: 'array', items: { type: 'string' } },
  },
  required: ['failed', 'flags'],
}

const DIFF = {
  type: 'object',
  properties: {
    prose_changed: { type: 'boolean' },
    changed_lines: { type: 'integer' },
  },
  required: ['prose_changed', 'changed_lines'],
}

const RECORD = {
  type: 'object',
  properties: {
    committed_sha: { type: 'string' },
    sidecars_left: { type: 'array', items: { type: 'string' } },
  },
  required: ['committed_sha', 'sidecars_left'],
}

const list = (xs) => (xs && xs.length ? xs.map((x) => `- ${x}`).join('\n') : '(none)')

// ---------------------------------------------------------------- Preflight
phase('Preflight')
const pre = await agent(`Preflight for a polish-prose run on ${ART}. The file can be any prose a person reads end to end: an essay, post, paper section, README, or book chapter. ${A.validate_only ? 'VALIDATE ONLY: change nothing, commit nothing.' : ''}

1. Report the current git branch. ${A.validate_only ? 'This is a validate-only run, so any branch is acceptable.' : 'If it is main or master, set ok=false: this pipeline commits, and changes land only on worktree branches (loop workflow).'}
2. Check that ${ART} exists and that each of these skill files exists: ${REQUIRED_SKILLS.map((s) => `${SK}/${s}/SKILL.md`).join(', ')}. List any missing path in "missing" and set ok=false if any are missing.
3. Focus file: ${A.focus_file ? `use ${A.focus_file}.` : `walk up from the article's directory to the repository root looking for critic-focus.md; use the nearest one.`} If found, return its path, each named check as one string in focus_items (verbatim, one per check), and the deterministic pre-check command it names in precheck_command with {article} left as a placeholder. If none exists, return empty values: the panel then reads without a focus list, which is allowed.
4. Form: read the file to decide its form (how-to, essay, polemic, post, paper section, README, chapter, or the name of a constitution under constitutions/ that matches). ${A.form ? `The caller says the form is ${A.form}; use that.` : ''} If a constitution file exists for the form, return in protected_spans every span it requires that appears verbatim in the file (for a how-to: the bridge sentence, the learning-objectives paragraph, the "The steps" transition), quoted exactly. If a required span is missing from the file, say so in reason.
5. Roster: read the roster table in ${SK}/critic-panel/references/personas.md. ${A.roster ? `The caller asks for roster ${JSON.stringify(A.roster)}; use it (a roster name or a list of persona names).` : 'Use "book" for a book chapter, "article" for everything else.'} Return roster_name and the persona names in roster order.
6. The draft's own rules: per the "The draft's own rules" section of ${SK}/critic-panel/SKILL.md, list every rules file found beside or above the file (docs/constitutions/voice.yaml, docs/constitutions/argument.yaml, the chapter's SRD under docs/srd/, or a matching constitution under constitutions/) in draft_rules.
7. Optional stages: has_front_matter = the file starts with a YAML front-matter block; has_voice_corpus = a writing-voice/ directory with exemplars is found walking up from the file (humanize needs it); has_voice_constitution = writing-voice/voice-constitution.md is found the same way (voice-critic needs it).
8. ${A.validate_only ? 'Do not commit. Return baseline_sha as the current HEAD.' : `If ${ART} has uncommitted changes, commit them alone as "draft: <slug> (pre-pipeline baseline)". Return baseline_sha as HEAD after that.`}`,
  { label: 'preflight', schema: PREFLIGHT, effort: 'low' })

if (!pre || !pre.ok) {
  return { status: 'refused', reason: pre ? pre.reason : 'preflight agent failed', preflight: pre }
}
const CRITICS = pre.roster && pre.roster.length ? pre.roster : DEFAULT_ROSTER
const skipped = []
if (!pre.has_voice_corpus) skipped.push('humanize (no writing-voice/ corpus found)')
if (!pre.has_voice_constitution) skipped.push('voice-critic (no voice constitution found)')
if (!pre.has_front_matter) skipped.push('generation note (no front matter; the report is the record)')
log(`branch ${pre.branch}; form ${pre.form || 'unknown'}; roster ${pre.roster_name || 'article'} (${CRITICS.join(', ')}); focus file ${pre.focus_file || 'none (generic read)'}; ${pre.protected_spans.length} protected spans${skipped.length ? `; skipping: ${skipped.join('; ')}` : ''}`)
if (A.validate_only) {
  return { status: 'validated', roster: CRITICS, skipped, preflight: pre }
}

// ---------------------------------------------------------------- Humanize
phase('Humanize')
let hum = { ran: false, seed_reach: 'skipped', stages: [], notes: A.skip_humanize ? 'skip_humanize set by caller' : 'no writing-voice/ corpus found; humanize needs its exemplars' }
if (!A.skip_humanize && pre.has_voice_corpus) {
  hum = await agent(`Run the humanize skill on ${ART}: read ${SK}/humanize/SKILL.md and follow it end to end, exactly as written, including its stage order, its measurements, and its report. ${A.venue ? `Use venue mode with --venue ${A.venue}.` : ''}

Commit each stage's output as it lands, one commit per stage, with the stage name in the subject ("filter-tells: <slug>", "match-voice: <slug>", "tighten: <slug>", ...). Do not squash.
Respect locked spans and these protected spans verbatim:
${list(pre.protected_spans)}
If a model call fails on TLS certificates, point SSL_CERT_FILE at certifi's bundle; read API keys only through the repository's secrets convention and never print them.
${NO_PROSE}
${HYGIENE}
Return seed reach exactly as the skill reports it, each stage with its score, and anything the caller must know.`,
    { label: 'humanize', schema: HUMANIZE })
  if (!hum) return { status: 'failed', stage: 'humanize', preflight: pre }
  log(`humanize: seed reach ${hum.seed_reach}`)
}

// ---------------------------------------------------------------- Review
const focusBlock = pre.focus_items.length
  ? `FOCUS LIST. Answer every item explicitly, BY NAME, inside your ## Diagnosis, before your free read:\n${list(pre.focus_items)}`
  : 'No focus list was supplied for this repository: give your free read.'

async function panel(o, residue, round, tag) {
  const criticReports = await parallel(CRITICS.map((name) => () => agent(`You are the ${name} critic on a critic-panel Mode A read. Fresh context by design: you have not seen any other critic's report and must not look for one.

Read your persona brief (the ${name} entry) in ${SK}/critic-panel/references/personas.md; it states your kind (suggest or verdict). From ${SK}/critic-panel/SKILL.md read "The two report formats" (use your kind's format with its literal headings) and "Constraints" (the shared ones and your kind's). Then read the reading copy at ${o.copy_path}.
${pre.draft_rules.length ? `Judge against the draft's own rules, which outrank a generic standard:\n${list(pre.draft_rules)}` : ''}

${focusBlock}

Measured length: ${o.total_words} prose words. Paragraphs over the paragraph budget:
${list(o.flagged_paragraphs)}

${residue.length ? `Residue from the previous round. For each item, say in your Diagnosis whether it is still present:\n${list(residue)}` : ''}

Write your report to ${STEM}.critic-${name.toLowerCase()}.md and return only the word done.`,
    { label: `${tag} r${round}: ${name}`, phase: tag === 'final' ? 'Final read' : 'Review' })))
  if (criticReports.filter(Boolean).length < CRITICS.length) {
    log(`round ${round}: ${CRITICS.length - criticReports.filter(Boolean).length} critic(s) failed; merging what returned`)
  }
  return agent(`Merge the critic-panel reports for ${ART}: ${CRITICS.map((n) => `${STEM}.critic-${n.toLowerCase()}.md`).join(', ')} (skip any that does not exist).

Run ${SK}/critic-panel/scripts/converge.py on them with --out ${STEM}.critic-sheet.md --roster ${CRITICS.map((n) => n.toLowerCase()).join(',')}. If a report is refused as unparseable, fix only its headings and field labels to the literal format in ${SK}/critic-panel/SKILL.md (never its content) and re-run.

From the sheet and the reports return: every convergent passage (2+ critics) with its first words, the shared reason, and the critic count; the paragraph moves; the declared defect classes; the consensus answer to each focus-list item from the Diagnoses (one line each); and the single-critic suggestion count. Keep the critic reports and sheet on disk (the next stage reads the sheet) and return its path.`,
    { label: `${tag} r${round}: converge`, phase: tag === 'final' ? 'Final read' : 'Review', schema: SHEET, effort: 'low' })
}

const rounds = []
let residue = []
let stable = false
let lastSheet = null

for (let round = 1; round <= MAX; round++) {
  phase('Review')
  const outline = await agent(`Round ${round} start for ${ART}.

1. reverse-outline: read ${SK}/reverse-outline/SKILL.md. If the article carries no rst: markers, run annotate (session-model labelling, as the skill specifies) and validate; otherwise run audit against the existing markers and check --renumber. Then run rank. Commit marker changes as "reverse-outline: <slug>".
2. Return round_start_sha = HEAD after that commit, the paragraph numbers rank lists as cheap deletion candidates, the split paragraphs, and any paragraph audit marks eroded or changed.
3. Build the critics' reading copy with ${SK}/critic-panel/scripts/prepare_copy.py and return its path (leave it on disk for the critics).
4. ${pre.precheck_command ? `Run the length pre-check: ${pre.precheck_command.replace('{article}', ART)}. Return the prose word total and each flagged paragraph as one line (line number, word count, first words, over or DEFECT).` : 'No pre-check command was supplied; return total_words as the prose word count and an empty flagged list.'}
${NO_PROSE}`,
    { label: `r${round}: outline + length`, phase: 'Review', schema: OUTLINE, effort: 'low' })
  if (!outline) return { status: 'failed', stage: `round ${round} outline`, rounds }

  const sheet = await panel(outline, residue, round, 'panel')
  if (!sheet) return { status: 'failed', stage: `round ${round} converge`, rounds }
  lastSheet = sheet

  const applied = await agent(`Apply the converged critic sheet ${sheet.sheet_path} to ${ART} with the critic-apply skill: read ${SK}/critic-apply/SKILL.md and run its script as written.

Pass as protected spans (write them to a temporary spans file):
${list(pre.protected_spans)}
Pass --cheap-paragraphs ${outline.cheap_paragraphs.join(',') || '(none)'} from reverse-outline's rank.
Do NOT overwrite the article: leave the candidate at the skill's output path and return that path, the applied/kept/declined counts, and every convergent target that was not applied (first words plus the reason).
Then delete the three critic reports and the sheet (the counts you return are the record). ${NO_PROSE}`,
    { label: `r${round}: critic-apply`, phase: 'Review', schema: APPLY })
  if (!applied) return { status: 'failed', stage: `round ${round} critic-apply`, rounds }

  let cold = { verdict: 'ship as-is', reverts: [], committed_sha: outline.round_start_sha }
  if (applied.applied > 0) {
    cold = await agent(`Cold review, fresh context. You have not seen how the candidate was produced and must not ask.

Read ${SK}/cold-review/SKILL.md and its prompt template ${SK}/cold-review/references/review-prompt.md. Baseline: ${ART} as committed at ${outline.round_start_sha} (extract it with git show to a temporary file). Candidate: ${applied.candidate_path}. Run the skill's screen, review paragraph by paragraph as the template specifies, and decide with its closed vocabulary.

- ship as-is: replace ${ART} with the candidate.
- ship with reverts: run the skill's apply with your revert list and write the result over ${ART}.
- reject candidate: leave ${ART} untouched.
High-value targets: numbers, citations, quotations, and these protected spans:
${list(pre.protected_spans)}
If ${ART} changed, commit it as "critic-apply: <slug> (round ${round}, cold-reviewed)". Return the verdict, each revert as one line, and HEAD. ${HYGIENE}`,
      { label: `r${round}: cold review`, phase: 'Review', schema: COLD })
    if (!cold) return { status: 'failed', stage: `round ${round} cold review`, rounds }
  }

  phase('Review')
  const icebergLegs = await parallel(['a', 'b'].map((leg) => () => agent(`You are the Iceberg critic, leg ${leg}, in a critic-panel read of ${ART}. Fresh context by design: do not look for any other critic's report.

Read your persona brief, the "## Iceberg — The Inference Test" entry in ${SK}/critic-panel/references/personas.md, and "## Category 16: Warrant Tails" in ${SK}/filter-tells/references/cot-leakage-patterns.md; from ${SK}/critic-panel/SKILL.md read "The two report formats" (suggest format, literal headings) and "Constraints". Build your own reading copy of ${ART} as it stands now with ${SK}/critic-panel/scripts/prepare_copy.py, and sweep all of it: return every warrant tail that passes the removal test, with no cap. Replacement is CUT or the quoted span with words removed and none added.

Write the report to ${STEM}.critic-iceberg-${leg}.md, delete your reading copy, and return only: done, N suggestions.`,
    { label: `r${round}: iceberg ${leg}`, phase: 'Review' })))
  const iceberg = await agent(`Apply the Iceberg pass to ${ART}. Merge ${STEM}.critic-iceberg-a.md and ${STEM}.critic-iceberg-b.md with ${SK}/critic-panel/scripts/converge.py --roster iceberg-a,iceberg-b --out ${STEM}.iceberg-sheet.md, then run the critic-apply skill (${SK}/critic-apply/SKILL.md) on that sheet with these protected spans:
${list(pre.protected_spans)}
Convergent cuts and deletion-only trims apply directly with no model call; report any target that could not be placed (for example a span inside a list item, which critic-apply does not locate) instead of placing it by hand. Write the result over ${ART}, commit it as "iceberg: <slug> (round ${round})" if it changed, and return the applied/kept/declined counts and every convergent target left unapplied. ${HYGIENE}`,
    { label: `r${round}: iceberg apply`, phase: 'Review', schema: APPLY, effort: 'low' })
  log(`round ${round}: iceberg legs ${icebergLegs.filter(Boolean).length}/2, ${iceberg ? iceberg.applied : 0} warrant tails removed`)

  const fixRoss = round <= ROSS_FIX_ROUNDS
  const ross = await agent(`ross read (critic-panel Mode C) on ${ART}, round ${round}. Read the Mode C section of ${SK}/critic-panel/SKILL.md and follow its protocol exactly.

Run its session leg yourself from the --copy-only reading copy (forward-only, one sentence of lookback, every inference you had to make counts as a finding), then two cross-family Ollama legs with ${SK}/critic-panel/scripts/ross_read.py --model <name>, choosing two model families different from each other and from yours. Merge with converge.py.

${fixRoss
    ? `${round === 1 ? 'Fix findings convergent ACROSS families on non-reserved prose.' : 'Fix only regressions the previous round introduced that are convergent across families; nothing else.'} Apply them with the critic-apply skill (${SK}/critic-apply/SKILL.md) using the merged ross sheet, with the protected spans below. Before writing it over ${ART}, run ${SK}/cold-review/scripts/cold_review.py screen with the current article as baseline and the fixed text as candidate, and revert (with its apply) every paragraph where a number, citation or quotation drifted. Then write the result over ${ART} and commit it as "ross: <slug> (round ${round})".`
    : 'Read only this round: the batch cap (fix convergents in round 1, repair regressions in round 2, then stop) is reached. Change nothing.'}
Reserved, never fixed (report them): single-model findings, locked spans, rule tensions, the protected spans below, and any sentence the article's generation notes record as the author's own hand edit.
Protected spans:
${list(pre.protected_spans)}
Return the legs you ran (model names), every cross-family convergent finding as one line saying whether it was fixed, and the reserved items. ${NO_PROSE} ${HYGIENE}`,
    { label: `r${round}: ross read`, phase: 'Review', schema: ROSS })

  const voice = pre.has_voice_constitution
    ? await agent(`voice-critic on ${ART}: read ${SK}/voice-critic/SKILL.md and run its script read-only with the judge enabled and --form ${pre.form || 'essay'} --json. Return the dimensions that FAIL and each flagged span as one line (dimension, quoted span, line range). Never edit anything. ${HYGIENE}`,
      { label: `r${round}: voice-critic`, phase: 'Review', schema: VOICE, effort: 'low' })
    : { failed: [], flags: ['skipped: no voice constitution found'] }

  const diff = await agent(`Did round ${round} change the prose of ${ART}? Run git diff ${outline.round_start_sha} -- ${ART} and count added or removed lines, ignoring lines that are only rst: marker comments or whitespace. Return prose_changed and the count.`,
    { label: `r${round}: diff`, phase: 'Review', schema: DIFF, effort: 'low' })

  residue = [...applied.unapplied_convergent, ...sheet.paragraph_moves]
  rounds.push({
    round,
    words: outline.total_words,
    flagged_paragraphs: outline.flagged_paragraphs.length,
    convergent: sheet.convergent.length,
    focus_answers: sheet.focus_answers,
    classes: sheet.classes,
    applied: applied.applied,
    kept: applied.kept,
    declined: applied.declined,
    cold: cold.verdict,
    reverts: cold.reverts.length,
    iceberg: iceberg ? { applied: iceberg.applied, unapplied: iceberg.unapplied_convergent } : 'failed',
    ross: ross ? { legs: ross.legs, convergent: ross.convergent, reserved: ross.reserved } : 'failed',
    voice: voice || 'failed',
    prose_changed: diff ? diff.prose_changed : true,
    eroded: outline.eroded,
  })
  log(`round ${round}: ${sheet.convergent.length} convergent, ${applied.applied} applied, cold review ${cold.verdict}, prose ${diff && !diff.prose_changed ? 'unchanged' : 'changed'}`)

  if (diff && !diff.prose_changed) { stable = true; break }
}

// ---------------------------------------------------------------- Final read
let finalRead = null
if (!stable) {
  phase('Final read')
  log(`round cap ${MAX} reached with the text still changing: one read-only panel pass on the shipping text`)
  const o = await agent(`Prepare a read-only final panel read of ${ART}: build the reading copy with ${SK}/critic-panel/scripts/prepare_copy.py and return its path. ${pre.precheck_command ? `Run ${pre.precheck_command.replace('{article}', ART)} and return the total and flagged paragraphs.` : 'Return the prose word count and an empty flagged list.'} Return round_start_sha as HEAD and empty arrays for the reverse-outline fields. Change nothing.`,
    { label: 'final: copy + length', phase: 'Final read', schema: OUTLINE, effort: 'low' })
  if (o) {
    finalRead = await panel(o, residue, MAX + 1, 'final')
    if (finalRead) residue = [...finalRead.convergent.map((c) => `${c.passage} — ${c.why} (x${c.critics})`), ...finalRead.paragraph_moves]
  }
}

// ---------------------------------------------------------------- Record
phase('Record')
const record = await agent(`${pre.has_front_matter ? `Record this polish-prose run in ${ART}'s front matter generation: block, following the provenance conventions the repository already uses there (append an entry, or start the block if there is none; never rewrite earlier entries).` : `${ART} has no front matter, so write no generation note: skip straight to the sidecar sweep below, and commit only if a sidecar was tracked.`} The entry names the pipeline (polish-prose), humanize seed reach (${hum.seed_reach}), the number of review rounds (${rounds.length}), whether the loop ended on a stable read (${stable}), per-round applied/kept/declined counts and cold-review verdicts:
${rounds.map((r) => `round ${r.round}: applied ${r.applied}, kept ${r.kept}, declined ${r.declined}, cold ${r.cold}, convergent ${r.convergent}`).join('\n')}
and the residue still open:
${list(residue)}

Then delete every remaining sidecar whose name starts with ${STEM} other than the article itself (critic copies, reports, sheets, *.applied.md, *.outline.md, JSON reports), list any you could not delete, and commit the file as "polish-prose: <slug> (generation note)" if it changed. Return HEAD and the leftover list.`,
  { label: 'record', phase: 'Record', schema: RECORD, effort: 'low' })

return {
  status: stable ? 'stable' : 'round-cap',
  article: ART,
  roster: CRITICS,
  skipped,
  branch: pre.branch,
  baseline_sha: pre.baseline_sha,
  focus_file: pre.focus_file || null,
  humanize: hum,
  rounds,
  final_read: finalRead ? { convergent: finalRead.convergent, focus_answers: finalRead.focus_answers, classes: finalRead.classes } : null,
  residue,
  record,
}
