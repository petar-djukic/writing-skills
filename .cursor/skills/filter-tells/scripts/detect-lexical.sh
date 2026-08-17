#!/usr/bin/env bash
# detect-lexical.sh — Scan markdown files for AI writing giveaway words/phrases
# Usage: ./detect-lexical.sh <file-or-dir> [file-or-dir ...] [--json] [--lexicon=NAME]
#
# Accepts: single file, multiple files, directories (scans *.md, *.tex, and
# *.yaml recursively). YAML files are scanned through the line-aligned prose
# view (prose_document.py), so keys and comments never false-positive.
# Outputs line-numbered matches grouped by category.
# Exit code: 0 = clean, 1 = issues found, 2 = usage error
#
# --lexicon selects the venue lexicon (GH-337): newsletter (default) | book |
# industry | academic | none. Core categories fire for every venue; the
# venue-keyed categories are adjusted in the "Venue lexicons" block below.
# Consumers usually take the value from a venue profile's tell_lexicon field
# (see the writing-voice rule, "venues/").

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Character-safe truncation of the reported line previews (GH-3).
#
# head -c counts bytes, so a cut landing inside a multi-byte character emitted
# a partial sequence and the --json output stopped being valid UTF-8. drive.py
# reads it with text=True: in a UTF-8 locale that raises UnicodeDecodeError and
# the whole scan dies before producing a result, and in the C locale Python's
# surrogateescape hides it and the preview is silently mojibake. One arrow, en
# dash or curly quote anywhere in a document was enough for either.
#
# cut -c counts characters, but only in a UTF-8 locale — under LC_ALL=C both
# BSD and GNU cut fall back to counting bytes — so the locale is pinned to the
# truncation instead of inherited from the caller, leaving every other command
# in this script at the caller's locale.
# FILTER_TELLS_TRUNC_LOCALE overrides the search: a locale name pins that
# locale, and the value "none" forces the fallback below. The tests use it to
# reach a branch that would otherwise never run on a developer machine.
TRUNC_LOCALE=""
case "${FILTER_TELLS_TRUNC_LOCALE:-}" in
  none) ;;
  ?*)   TRUNC_LOCALE="$FILTER_TELLS_TRUNC_LOCALE" ;;
  *)
    for _loc in C.UTF-8 en_US.UTF-8; do
      if locale -a 2>/dev/null | grep -qx "$_loc"; then
        TRUNC_LOCALE="$_loc"
        break
      fi
    done
    unset _loc
    ;;
esac

# $1 = maximum characters; text on stdin.
truncate_chars() {
  if [[ -n "$TRUNC_LOCALE" ]]; then
    LC_ALL="$TRUNC_LOCALE" cut -c "1-$1"
  else
    # No UTF-8 locale on the system: cut to bytes, then drop any trailing run
    # of non-ASCII bytes. Ends the preview up to one character early rather
    # than ever emitting half a character.
    LC_ALL=C head -c "$1" | LC_ALL=C sed 's/[^ -~]*$//'
  fi
}

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <file-or-dir> [file-or-dir ...] [--json]" >&2
  exit 2
fi

# Separate flags from paths
JSON_MODE=""
LEXICON="${FILTER_TELLS_LEXICON:-newsletter}"
declare -a PATHS=()
for arg in "$@"; do
  if [[ "$arg" == "--json" ]]; then
    JSON_MODE="--json"
  elif [[ "$arg" == --lexicon=* ]]; then
    LEXICON="${arg#--lexicon=}"
  else
    PATHS+=("$arg")
  fi
done

case "$LEXICON" in
  newsletter|book|industry|academic|none) ;;
  *)
    echo "Unknown --lexicon: $LEXICON (newsletter|book|industry|academic|none)" >&2
    exit 2
    ;;
esac

if [[ ${#PATHS[@]} -eq 0 ]]; then
  echo "Usage: $0 <file-or-dir> [file-or-dir ...] [--json]" >&2
  exit 2
fi

# Resolve all paths into a list of .md/.tex/.yaml files
declare -a FILES=()
for p in "${PATHS[@]}"; do
  if [[ -d "$p" ]]; then
    while IFS= read -r -d '' f; do
      FILES+=("$f")
    done < <(find "$p" \( -name '*.md' -o -name '*.tex' -o -name '*.yaml' -o -name '*.yml' \) -type f -print0 | sort -z)
  elif [[ -f "$p" ]]; then
    FILES+=("$p")
  else
    echo "Error: Not found: $p" >&2
    exit 2
  fi
done

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "Error: No .md, .tex, or .yaml files found in the given paths." >&2
  exit 2
fi

GLOBAL_EXIT=0
ISSUES_FOUND=0
CANDIDATES_FOUND=0
declare -a RESULTS=()

# Conversational-filler hits per 500 words above which the scan FAILS. Empty by
# default, which means report the rate and fail on nothing.
#
# It is empty because calibration refused a value (GH-233). Measured on the
# reference venue-voice corpus — Dan Luu, Julia Evans, Krugman, Rands, Yegge,
# Fowler — published human essays run 2.1 to 15.6 filler per 500 words. That is
# not a defect; it is the register, and it is the register a punchy rewrite is
# aiming at. Meanwhile technical documentation in this repository runs 0.0 to
# 1.7, and the author's own articles 0.2 to 0.3. Any threshold that catches a
# rewrite drifting to 2.8 also condemns every essay in the anchor corpus.
#
# So the useful signal is movement, not level: a document whose own rate went
# 0.3 -> 2.8 regressed, and register_markers.py --compare is what says so. Set
# this variable to gate on an absolute level when you know the register you want.
FILLER_DENSITY_MAX="${FILLER_DENSITY_MAX:-}"

# --- Category: Chat-turn residue (assistant voice; highest severity) ---
# Text from the model's conversational wrapper committed into the document
# body. Not a style pattern — the assistant speaking. Any hit fails the scan;
# a hit in the last 3 lines of the file is near-certain residue (the classic
# trailing sign-off: "Want me to create a suggested author bio?").
CHAT_RESIDUE=(
  "want me to"
  "would you like me"
  "let me know if"
  "shall I "
  "hope this helps"
  "ready for substack"
  "I can also create"
  "I can also draft"
  "I can also write"
  "I can also add"
  "here's a suggested"
  "here is a suggested"
  "as an AI"
  "feel free to ask"
  "happy to help"
)

# --- Category: Banned adjectives/adverbs (from writing-style-guide.md) ---
BANNED_WORDS=(
  "critical" "critically"
  "key"
  "deliberate" "deliberatively"
  "correctly"
  # "sound" only in booster collocations, not as a predicate adjective
  # ("the mechanism is sound" is legitimate; "a sound foundation" is a tell).
  "sound foundation" "sound footing" "sound basis" "sound engineering"
  "sound principles" "on a sound" "technically sound"
  "strategic" "strategically"
  "precisely"
  "absolutely"
  "fundamental" "fundamentally"
  "breakthrough"
  "principled"
  "standards-aligned"
  "honest"
  "grounded"
  "concrete"
  "distinction"
  "cleanly" "neatly"
  "sharp" "sharpen" "sharpens"
  "underpins" "underpinning"
  "dovetails"
  "illuminates" "illuminating"
  "overarching"
  "interplay"
  "salient"
  "delineate" "delineating"
  "encapsulate" "encapsulates"
  "myriad"
  "plethora"
  "burgeoning"
  "nascent"
  "hinges on"
  "lands" "land"
  "seam" "seams"
  "unfalsifiable"
)

# --- Category: AI cliché phrases ---
AI_PHRASES=(
  "at the heart of"
  "earns its keep"
  "earn its keep"
  "earns their keep"
  # worth-tic family (substack-writing rules; bare forms subsume "it's worth noting")
  "worth noting"
  "worth noticing"
  "worth examining"
  "worth exploring"
  "worth questioning"
  "worth keeping"
  "worth preserving"
  "worth remembering"
  "worth asking"
  "worth watching"
  "worth reading"
  "worth sitting with"
  "worth pausing"
  "it's important to note"
  "it is important to note"
  "it bears mentioning"
  "let's consider"
  "let's break this down"
  "let's think about"
  "let me explain"
  "in this section, we will"
  "to put it differently"
  "simply put"
  "to put it simply"
  "in other words"
  "the question then becomes"
  "this raises the question"
  "which brings us to"
  "this brings us to"
  # question-is tic ("the question is", "the real question is", "the only question is")
  " question is"
  # substack-writing rules sync (GH-46) — see idea-factory .claude/rules/substack-writing.md
  "here's the thing"
  "here is the thing"
  "move the needle"
  "moving the needle"
  "here's what I learned"
  "here's what I've learned"
  "here is what I learned"
  "here’s what I learned"
  "here’s what I’ve learned"
  "here’s the thing"
  "let’s unpack"
  "spoiler alert"
  "let's unpack"
  "north star"
  "low-hanging fruit"
  "best practices"
  "game-chang"
  "game chang"
  "unlock"
  "one might argue"
  "some might say"
  "the key takeaway"
  "there are [0-9]+ main"
  "there are several"
  "this means that"
  "this implies that"
  "this suggests that"
  "this ensures that"
  "this enables"
  "this allows"
  "this provides"
  "this represents"
  "this highlights"
  "this underscores"
  "this demonstrates"
  "in summary"
  "in conclusion"
  "to summarize"
  "as mentioned earlier"
  "as noted above"
  "as discussed"
  "it should be noted"
  "it is evident"
  "it becomes clear"
  "it is clear that"
  "needless to say"
  "without a doubt"
  "undeniably"
  "undoubtedly"
  "unquestionably"
  "comprehensive"
  "holistic"
  "holistically"
  "robust"
  "robustly"
  "seamless"
  "seamlessly"
  "leverage"
  "leveraging"
  "utilize"
  "utilizing"
  "facilitate"
  "facilitating"
  "empower"
  "empowering"
  "enhance"
  "enhancing"
  "foster"
  "fostering"
  "navigate"
  "navigating"
  "landscape"
  "paradigm"
  "ecosystem"
  "synergy"
  "transformative"
  "cutting-edge"
  "state-of-the-art"
  "game-changing"
  "groundbreaking"
  "innovative"
  "revolutionize"
  "revolutionizing"
  "delve"
  "delving"
  "realm"
  "rippl"
  "tapestry"
  "multifaceted"
  "intricate"
  "intricacies"
  "nuanced"
  "nuances"
  "pivotal"
  "moreover"
  "furthermore"
  "additionally"
  "consequently"
  "nevertheless"
  "nonetheless"
  "henceforth"
  "thereby"
  "wherein"
  "thereof"
  "albeit"
  "inasmuch"
  "coupled with"
  "in tandem"
  "advent"
  "akin to"
  "renders"
  "warrants"
  "dictates"
  "speaks to"
  "constitutes"
  "manifests"
  "affords"
  "it is worth emphasizing"
  "it is no coincidence"
  "it is precisely this"
  "strikes a balance"
  "stands in contrast"
  "lends itself to"
  "gives rise to"
  "paves the way"
  "a testament to"
  "is tantamount to"
  "by the same token"
  "in light of"
  "in the context of"
  "in a manner that"
  "to that end"
  "to this end"
  "along these lines"
  "with this in mind"
  "bears emphasizing"
  "merits attention"
  "worthy of note"
  "the crux of the matter"
  "the key insight"
  "the upshot is"
  "the takeaway is"
  "what emerges is"
  "at a high level"
  "zooming out"
  "zooming in"
  "stepping back"
  "put differently"
  "stated differently"
  "viewed through this lens"
  "through the lens of"
  "taken together"
  "in doing so"
  "in this way"
  "in effect"
  "orthogonal"
  "non-trivial"
  "out of the box"
  "under the hood"
  "at scale"
  # shape-as-structure metaphor ("keeps the same shape", "has the shape of")
  "same shape"
  "has the shape of"
  "takes the shape of"
)

# --- Category: False emphasis adverbs ---
FALSE_EMPHASIS=(
  "crucially"
  "notably"
  "importantly"
  "significantly"
  "remarkably"
  "interestingly"
  "essentially"
  "at its core"
  "ultimately"
  "inherently"
  "particularly"
)

# --- Category: Mechanical transitions ---
MECHANICAL_TRANSITIONS=(
  "(^|[.!?] )first,"
  "(^|[.!?] )second,"
  "(^|[.!?] )third,"
  "(^|[.!?] )finally,"
  "(^|[.!?] )in addition,"
  "(^|[.!?] )on one hand"
  "(^|[.!?] )on the other hand"
  "(^|[.!?] )while this is true"
  "(^|[.!?] )having said that"
  "(^|[.!?] )that being said"
  "(^|[.!?] )with that in mind"
  "(^|[.!?] )with this in place"
  "(^|[.!?] )given this,"
  "(^|[.!?] )that said,"
  "(^|[.!?] )and so,"
  "(^|[.!?] )moving on"
  "(^|[.!?] )turning to"
  "(^|[.!?] )building on"
  "(^|[.!?] )to begin with"
)

# --- Category: Narrative pivot / stage-setting frames ---
# The model dramatizing its own exposition: staging a reveal instead of
# stating the fact ("this is where X comes in", "here's the kicker").
# These are the specific completions — rarely legitimate. The bare openers
# ("this is where", "that's where") are candidates below, since they also
# appear in plain descriptive prose. "." wildcards cover straight and
# curly apostrophes.
NARRATIVE_PIVOTS=(
  # stage-setting
  "comes into play"
  "come into play"
  "where .* comes in"
  "enters the picture"
  "enter the picture"
  "where the magic happens"
  "cue the"
  # manufactured reveal
  "here.s the kicker"
  "here is the kicker"
  "here.s the catch"
  "here is the catch"
  "here.s the twist"
  "there.s a catch"
  "plot twist"
  # discovery narrative
  "it turns out"
  "turns out,"
  "that.s when I realized"
  "that.s when it hit me"
  "little did I know"
  "fast forward"
  # reader poke
  "sound familiar"
  "let that sink in"
  "read that again"
  "you read that right"
  "we.ve all been there"
  # translation frame
  "in plain English"
  "long story short"
  "the short answer"
  "think of it as"
  "the beauty of"
  # epochal framing
  "gone are the days"
  "in a world where"
  "we live in a world"
  # significance narration (the model justifying its own point)
  "this matters because"
  "it matters because"
  "why this matters"
  "why it matters"
  "this lands because"
  "this is important because"
  "the reason this matters"
)

# --- Category: Narrative pivot candidates (broad, need LLM verification) ---
# Bare stage-setting openers. "This is where the function stores its
# state" is legitimate descriptive prose; "This is where agents come in"
# is a pivot. Carried to the semantic pass for the removal test.
NARRATIVE_PIVOT_CANDIDATES=(
  "this is where"
  "that.s where"
  "here.s where"
  "here.s why"
  "here.s how"
  "the best part"
  "this works because"
  '[.!?] Enter [A-Z]'
  # Announce-the-structure frame (GH-117): a quantified noun "organizing" the
  # document, then a colon and the actual claim. Delete the frame, state the
  # claim as a plain sentence. ERE (scan_candidates uses grep -E).
  '(^|[.!?] )(One|A single|Two|Three|Four|Five) [a-z]+ (organizes|structures|anchors|underpins|drives|governs|shapes|orders) (it|this|the [a-z]+)'
)

# --- Category: Marketing and hype vocabulary (venue-inappropriate jargon) ---
# Calibration: these are HUMAN-register words — keynote and press-release
# voice, not AI cadence. They flag as undefined jargon inadmissible in
# technical prose, not as AI tells; the report labels them accordingly.
MARKETING_JARGON=(
  "frontier model"
  "frontier models"
  "frontier agent"
  "frontier agents"
  "frontier AI"
  "cutting-edge"
  "cutting edge"
  "best-in-class"
  "industry-leading"
  "world-class"
  "next-generation"
  "next generation of"
  "revolutionary"
  "paradigm shift"
  "SOTA"
)

# --- Category: Ornate register (overshoot lexicon) ---
# The vocabulary the maximally-clever "LinkedIn voice" depends on. Fine
# individually (axis in a plot, residual in regression); the style needs them
# in clusters. Advisory in detection (density-scored); hard-forbidden during
# rewrite passes (see rewrite-instructions.md). Starving these words out
# forces plainer prose.
ORNATE_REGISTER=(
  # metaphor verbs (the epigram engines)
  " loads "
  "carries a"
  "carries the"
  " buys "
  "hired to"
  "manufacture"
  "forfeits"
  "inherits the"
  "narrates"
  "decides whether"
  "survives every"
  "survives a"
  " awaits"
  # abstract epigram nouns
  "the instrument"
  "a concession"
  "the price of"
  "the dial"
  "the menu"
  "affordance"
  "the split"
  "the construct"
  "the shape of"
  # rhetorical glue
  " merely "
  "(^|[.!?] )nor "
  "to the digit"
  # borrowed-metaphor adjectives
  "load-bearing"
  "first-class"
  "orthogonal"
  "brittle"
  # aphorism frames
  "is the .* not the"
  "is not a .* problem but"
  "buys .* with"
)

# --- Category: Conversational filler (density-scored) ---
# The register a rewrite escapes INTO once it leaves corporate vocabulary
# behind. Measured on two articles re-emitted with clipped venue anchors
# (GH-233): " just " went 1 -> 10 and 1 -> 15, " actually " 1 -> 7 and 0 -> 15,
# and the register gate passed every one of them. BANNED_WORDS holds the
# corporate class (leverage, robust) and FALSE_EMPHASIS the formal one
# (crucially, notably); neither holds these, so filler was the one machine
# register with no gate in front of it.
#
# Density, never a denylist. These are high-frequency legitimate English and the
# author's own prose carries them — the measured baseline is 1 occurrence, not
# 0. A per-hit match would fire on every human paragraph that uses "just" once,
# make the gate noise, and teach operators to ignore it. That is why they are
# not in FALSE_EMPHASIS already. What moved between original and draft was the
# rate, so the rate is what is scored.
CONVERSATIONAL_FILLER=(
  '\bjust\b'
  '\bactually\b'
  '\breally\b'
  '\bbasically\b'
  '\bsimply\b'
  '\bhonestly\b'
  '\bliterally\b'
  '\bpretty much\b'
  '\bkind of\b'
  '\bsort of\b'
  '\ba bit\b'
)

# --- Category: CoT structural patterns (definite) ---
COT_STRUCTURAL=(
  "is not a monolithic"
  "is not a simple"
  "is not a trivial"
  "is not a single"
  "is not merely"
  "is not just a"
  "is not simply a"
  "is not simply that"
  "are not merely"
  "are not just"
  "are not simply"
  "this is not a"
)

# --- Category: CoT candidates (broad, need LLM verification) ---
# These are common CoT scaffolding shapes but also appear in legitimate prose.
# Flagged as candidates for the semantic pass to confirm or dismiss.
# Patterns match after sentence boundaries (. ! ?) since markdown paragraphs
# are single long lines.
COT_CANDIDATES=(
  '[.!?] This .* is '
  '[.!?] These .* are '
  '[.!?] That .* is '
  '[.!?] It is a '
  '[.!?] It is the '
  '[.!?] It is an '
  'What .* is '
  'Consider '
  'not only .* but'
  '[Tt]wo distinct '
  '[Tt]hree .* together '
  '[Tt]here are [a-z]* [a-z]* that '
  '(^|[.!?] )[Ww]hile .*, '
  'whether .* or '
  # Gaps found reconciling this list against the catalog (GH-40). Each of the
  # three categories below stays out of the semantic pass precisely because it
  # is lexical — which only holds if the list is actually complete.
  #
  # Category 10, inverted wh-cleft. 'What .* is' matches the canonical order
  # only, so "Runtime generation IS WHAT separates a factory from a library"
  # read clean. Same construction, same tell, reversed.
  ' is what '
  ' are what '
  # Category 11, imperative example introduction. 'Consider' was the whole
  # list; these are the rest of the closed set.
  '(^|[.!?] )(Imagine|Picture|Suppose) '
  '[Tt]ake the case of'
  # Category 12, correlative conjunctions. 'not only ... but' was listed and
  # its twin was not.
  'not just .* but'
)

# --- Category: Editorializing adjectives (compressed-conversation class, GH-117) ---
# Adjectives that tell the reader how to feel about a result instead of stating
# it. Empty on their own; candidates for the semantic pass (a defended judgment
# is fine, a bare label is not). Word-boundary matched.
EDITORIALIZING=(
  'sobering'
  'striking'
  'remarkabl'
  'notabl'
  'crucially'
  'importantly'
  'interestingly'
  'tellingly'
  'surprisingly'
  'compelling'
  'profound'
)

# --- Category: Reader-psychology / invented-discourse (GH-135) ---
# Purpose sentences that stage a discourse the document never established, or
# narrate the reader's mental state. Candidates: the semantic pass asks whether
# the sentence references a discourse the document itself established or invents
# one. Fix is to write the unit as subject stating its function. ERE.
READER_DIRECTIVE=(
  'answer the objection'
  'convince the reader'
  'persuade the reader'
  'let the reader (watch|see|follow|observe|understand)'
  'show the reader'
  'the reader (sees|learns|comes away|will (see|notice|understand)|should)'
  'every (operator|reader|engineer|developer|practitioner|user) (raises|asks|wonders|expects|wants)'
  'the (question|objection) every'
  'help the reader'
  'give the reader'
)

# --- Category: Self-referential document meta-narration (GH-135) ---
# Trailing clauses describing the artifact's own structure or cross-references
# instead of stating content. Candidates for the semantic pass (a genuine
# roadmap sentence differs from a clause that only narrates layout). ERE.
META_NARRATION=(
  'stated here and'
  'cited by every section'
  'introduced above and revisited below'
  'throughout this (article|paper|section|document)'
  'as (each|every) section (shows|demonstrates)'
  'that (serves|follows|precedes) (them|it) '
  'as (we|discussed) (will (see|show)|above|below)'
  'in the sections? that follow'
  'the remainder of this (article|paper|section)'
  # Author-stance / scope narration (added 2026-08-09, from the loop-article
  # editing days): the writer negotiating scope with themselves in public, or
  # stating system facts from the author's chair. SANCTIONED EXCEPTIONS the
  # semantic pass must not flag: the bridge sentence ("...and this article
  # introduces it") and the learning-objectives paragraph ("In this article I
  # show you..."). Everything else in this register gets rewritten as a claim
  # about the system ("a human approves it before it exists"), not the author.
  'here (we|i|they) (deal|turn|cover|matter)'
  'this (article|piece|section) (covers|delivers|provides|is about)'
  'to be clear about'
  'what matters here'
  '(waiting )?for my (approval|review|sign-off)'
  'i walk through'
  'the other half of this'
  # Brief echo (GH-30, CoT Category 15): the writing brief restated as a
  # finding. Two of the seven sub-forms are lexical enough to be worth
  # candidates — the negative-scope restatement of a constraint, and an intent
  # adverb attached to a choice about the document. These sit looser than the
  # rest of this array on purpose: "by design" is ordinary English about a
  # subject, and "does not specify" is what a real specification says about a
  # real thing. The semantic pass (Prompt 4 category 8) applies the addressee
  # test; a gate here would be wrong. The sub-form that matters most — one
  # claim paraphrased once per file — has no lexical form at all, and is left
  # to brief_echo_repetition in detect-structural.py.
  '(prescribes|specifies|names|mandates) no\b'
  'does not (specify|prescribe|mandate|dictate)'
  'says nothing about'
  'is deliberately (a|an|the|not)'
  '(scope|treatment|selection) is deliberately'
  'on purpose'
  'by design'
  'for readability'
  'a reader who'
  'the text (marks|says|means|uses|calls)'
  '(instead of|not a) reprint'
)

# --- Venue lexicons (GH-337) ---
# The arrays above are the DEFAULT (newsletter) lexicon — the lists this
# script has always carried. Core categories are venue-independent and never
# change: chat residue, AI clichés, mechanical transitions, narrative pivots,
# marketing jargon, ornate register, conversational filler, CoT candidates,
# editorializing, reader-directive, meta-narration.
#
# Venue-keyed categories:
#   BANNED_WORDS    the newsletter register list ("critical", "fundamental",
#                   "key"...). It must not fire on a methods section — these
#                   words are ordinary academic vocabulary.
#   FALSE_EMPHASIS  academic keeps its statistical vocabulary: "significantly"
#                   and "particularly" carry technical meaning in a results
#                   section and are dropped from the academic lexicon.
#   ACADEMIC_TELLS  template phrases specific to machine-written papers;
#                   scanned only under --lexicon=academic.
#
# book and industry currently share the newsletter lists at the lexical layer:
# the book delta (first-person rules, zero-tolerance hedging) and the industry
# delta (BLUF structure) are prose/structural rules, not word lists — they
# live in tighten-style's hedge policy and the semantic pass, not here.
ACADEMIC_TELLS=()
case "$LEXICON" in
  newsletter|book|industry) ;;
  academic)
    BANNED_WORDS=()
    FALSE_EMPHASIS=(
      "crucially"
      "notably"
      "importantly"
      "remarkably"
      "interestingly"
      "at its core"
      "ultimately"
      "inherently"
    )
    # Paper-template tells only. Phrases the core lists already carry
    # ("delve", "pivotal", "this underscores", "it is important to note")
    # are NOT repeated here — one hit per tell, not two.
    ACADEMIC_TELLS=(
      "showcase" "showcases" "showcasing"
      "garnered significant"
      "in recent years, there has been"
      "a comprehensive overview"
      "novel framework" "novel approach" "novel method"
      "holds great promise"
      "pave the way" "paves the way" "paving the way"
    )
    ;;
  none)
    BANNED_WORDS=()
    FALSE_EMPHASIS=()
    ;;
esac

scan_patterns() {
  local category="$1"
  shift
  local patterns=("$@")

  # ${patterns[@]+...}: a venue lexicon may empty a category (e.g. academic
  # empties BANNED_WORDS), and bash 3.2 under set -u crashes on expanding an
  # empty array — same guard as the RESULTS expansion below (GH-190).
  for pattern in ${patterns[@]+"${patterns[@]}"}; do
    # Case-insensitive grep with line numbers. -E (ERE), matching
    # scan_candidates: a gating pattern needs alternation to say "line start OR
    # sentence boundary", and markdown paragraphs are single long lines, so
    # without it a ^-anchored tell fires only on a paragraph's first sentence
    # (GH-43).
    #
    # Safe across the gating arrays because they are literal strings: of 345
    # patterns, 344 hold no ERE metacharacter and read identically under either
    # dialect. The one that does — AI_PHRASES' 'there are [0-9]+ main' — was
    # written as ERE and silently mismatched under BRE, where + is literal: it
    # matched "there are 5+ main" and never "there are 3 main".
    # test_scan_dialect.py holds both halves of that.
    local matches
    matches=$(grep -inE "$pattern" "$FILE" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
      ISSUES_FOUND=1
      while IFS= read -r line; do
        local lineno="${line%%:*}"
        local content="${line#*:}"
        if [[ "$JSON_MODE" == "--json" ]]; then
          RESULTS+=("{\"line\": $lineno, \"category\": \"$category\", \"pattern\": \"$(echo "$pattern" | tr -d '\000-\010\013\014\016-\037' | sed 's/\\/\\\\/g; s/"/\\"/g')\", \"text\": \"$(echo "$content" | tr -d '\000-\010\013\014\016-\037' | sed 's/\\/\\\\/g; s/"/\\"/g' | truncate_chars 200)\"}")
        else
          printf "  L%-4s [%s] %s\n" "$lineno" "$pattern" "$(echo "$content" | truncate_chars 120)"
        fi
      done <<< "$matches"
    fi
  done
}

# Like scan_patterns but advisory-only: does not set ISSUES_FOUND.
# These need LLM verification before acting on them.
scan_candidates() {
  local category="$1"
  shift
  local patterns=("$@")

  # Same empty-array guard as scan_patterns.
  for pattern in ${patterns[@]+"${patterns[@]}"}; do
    # -E (ERE) so candidate patterns may use alternation groups
    local matches
    matches=$(grep -inE "$pattern" "$FILE" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
      CANDIDATES_FOUND=1
      while IFS= read -r line; do
        local lineno="${line%%:*}"
        local content="${line#*:}"
        if [[ "$JSON_MODE" == "--json" ]]; then
          RESULTS+=("{\"line\": $lineno, \"category\": \"$category\", \"severity\": \"candidate\", \"pattern\": \"$(echo "$pattern" | tr -d '\000-\010\013\014\016-\037' | sed 's/\\/\\\\/g; s/"/\\"/g')\", \"text\": \"$(echo "$content" | tr -d '\000-\010\013\014\016-\037' | sed 's/\\/\\\\/g; s/"/\\"/g' | truncate_chars 200)\"}")
        else
          printf "  L%-4s [%s] %s\n" "$lineno" "$pattern" "$(echo "$content" | truncate_chars 120)"
        fi
      done <<< "$matches"
    fi
  done
}

run_on_file() {
  local DISPLAY="$1"
  local FILE="$1"
  # LaTeX input: grep the line-preserving prose view so command names, comments,
  # and macro args don't false-positive. --aligned keeps source line numbers.
  local TEX_TMP=""
  if [[ "$DISPLAY" == *.tex ]]; then
    TEX_TMP="$(mktemp)"
    python3 "$SCRIPT_DIR/detex.py" --aligned "$DISPLAY" > "$TEX_TMP" 2>/dev/null || true
    FILE="$TEX_TMP"
  fi
  # YAML input: grep the line-aligned prose view so keys, comments, and
  # structure don't false-positive. prose_document.py needs ruamel.yaml, so
  # prefer the agent pixi env when present; a failed extraction is an error,
  # never a silent fall-through to grepping raw YAML.
  local YAML_TMP=""
  if [[ "$DISPLAY" == *.yaml || "$DISPLAY" == *.yml ]]; then
    YAML_TMP="$(mktemp)"
    local -a PROSE_PY=(python3)
    local MANIFEST="$SCRIPT_DIR/../../../pixi.toml"
    if command -v pixi >/dev/null 2>&1 && [[ -f "$MANIFEST" ]]; then
      PROSE_PY=(pixi run --manifest-path "$MANIFEST" python)
    fi
    if ! "${PROSE_PY[@]}" "$SCRIPT_DIR/../../../scripts/prose_document.py" \
        --aligned "$DISPLAY" > "$YAML_TMP" 2>"$YAML_TMP.err"; then
      echo "Error: could not extract prose from $DISPLAY:" >&2
      cat "$YAML_TMP.err" >&2
      rm -f "$YAML_TMP" "$YAML_TMP.err"
      exit 2
    fi
    rm -f "$YAML_TMP.err"
    FILE="$YAML_TMP"
  fi
  # Markdown input: figure scaffolding is out of scope (GH-321). Image embeds
  # and figure-caption lines are non-prose to the rest of the pipeline
  # (prose_document.py classifies them separately), so the lexical scan must
  # not report them. Lines are blanked, not deleted, so every reported line
  # number still refers to the real file.
  local MD_TMP=""
  if [[ "$DISPLAY" == *.md ]]; then
    MD_TMP="$(mktemp)"
    sed -E -e 's/^!\[.*$//' -e 's/^\*\*Figure .*$//' "$FILE" > "$MD_TMP"
    FILE="$MD_TMP"
  fi
  ISSUES_FOUND=0
  CANDIDATES_FOUND=0
  RESULTS=()

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo "=== Lexical AI Detection: $DISPLAY (lexicon: $LEXICON) ==="
    echo ""
    echo "--- Chat-Turn Residue (assistant voice — any hit fails the scan) ---"
  fi
  scan_patterns "chat-residue" "${CHAT_RESIDUE[@]}"

  # Position weighting: a residue match in the last 3 lines is near-certain
  # (the trailing assistant sign-off). Flag it CRITICAL explicitly.
  local tail_text
  tail_text=$(tail -n 3 "$FILE")
  for pattern in "${CHAT_RESIDUE[@]}"; do
    if echo "$tail_text" | grep -iq "$pattern"; then
      ISSUES_FOUND=1
      if [[ "$JSON_MODE" == "--json" ]]; then
        RESULTS+=("{\"line\": -1, \"category\": \"chat-residue-tail\", \"pattern\": \"$(echo "$pattern" | tr -d '\000-\010\013\014\016-\037' | sed 's/\\/\\\\/g; s/"/\\"/g')\", \"text\": \"match within final 3 lines — near-certain assistant sign-off\"}")
      else
        printf "  CRITICAL: \"%s\" appears in the FINAL 3 LINES — near-certain assistant sign-off. Delete it.\n" "$pattern"
      fi
    fi
  done

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Banned Words ---"
  fi
  scan_patterns "banned-word" ${BANNED_WORDS[@]+"${BANNED_WORDS[@]}"}

  if [[ ${#ACADEMIC_TELLS[@]} -gt 0 ]]; then
    if [[ "$JSON_MODE" != "--json" ]]; then
      echo ""
      echo "--- Academic Template Tells ---"
    fi
    scan_patterns "academic-tell" "${ACADEMIC_TELLS[@]}"
  fi

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- AI Cliché Phrases ---"
  fi
  scan_patterns "ai-cliche" "${AI_PHRASES[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- False Emphasis ---"
  fi
  scan_patterns "false-emphasis" ${FALSE_EMPHASIS[@]+"${FALSE_EMPHASIS[@]}"}

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Mechanical Transitions ---"
  fi
  scan_patterns "mechanical-transition" "${MECHANICAL_TRANSITIONS[@]}"

  # Ordinal walkthrough sequences: "First, ... Second, ..." starting at
  # sentence boundaries anywhere in a paragraph (markdown paragraphs are
  # single lines, so the line-anchored ^first, patterns miss nearly all of
  # them). A single "First," is legitimate; flag a line only when 2+
  # DISTINCT ordinals open sentences in it.
  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Ordinal Walkthrough Sequences (2+ distinct ordinals per paragraph) ---"
  fi
  local lineno=0
  while IFS= read -r line; do
    lineno=$((lineno + 1))
    local distinct
    # grep exits 1 on no match; under set -euo pipefail every stage needs a
    # guard, and grep -c always emits exactly one number.
    distinct=$(printf '%s\n' "$line" \
      | { grep -oiE '(^|[.!?:] +)(first|second|third|fourth|fifth|finally),' || true; } \
      | { grep -oiE '(first|second|third|fourth|fifth|finally)' || true; } \
      | tr '[:upper:]' '[:lower:]' | sort -u | { grep -c . || true; })
    if [[ "$distinct" -ge 2 ]]; then
      ISSUES_FOUND=1
      if [[ "$JSON_MODE" == "--json" ]]; then
        RESULTS+=("{\"line\": $lineno, \"category\": \"ordinal-sequence\", \"pattern\": \"First,/Second,/...\", \"text\": \"$(echo "$line" | tr -d '\000-\010\013\014\016-\037' | sed 's/\\/\\\\/g; s/"/\\"/g' | truncate_chars 160)\"}")
      else
        printf "  L%-4s [%s distinct ordinals] %s\n" "$lineno" "$distinct" "$(echo "$line" | truncate_chars 120)"
      fi
    fi
  done < "$FILE"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- CoT Structural Patterns ---"
  fi
  scan_patterns "cot-structural" "${COT_STRUCTURAL[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Narrative Pivot / Stage-Setting Frames ---"
  fi
  scan_patterns "narrative-pivot" "${NARRATIVE_PIVOTS[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Narrative Pivot Candidates (needs LLM verification) ---"
  fi
  scan_candidates "narrative-pivot-candidate" "${NARRATIVE_PIVOT_CANDIDATES[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Marketing/Hype Vocabulary (venue-inappropriate jargon, NOT an AI tell) ---"
  fi
  scan_patterns "venue-jargon" "${MARKETING_JARGON[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Ornate Register (overshoot lexicon; density-scored) ---"
  fi
  scan_candidates "ornate-register" "${ORNATE_REGISTER[@]}"

  # Ornate-register density per 500 words. Above ~4/500w the clever register
  # is the document's default voice, not an occasional flourish. All
  # occurrences are listed above either way so a rewrite pass knows what to
  # starve out.
  #
  # Counted with -o piped through wc, not with -c (GH-242). `grep -c` counts
  # matching LINES, and a markdown paragraph is one long line, so three
  # flourishes in one paragraph scored as one. Bundling -o with -c does not
  # dependably fix it: the answer varies by grep implementation, and on this
  # machine (ugrep 7.5.0) the same `-ioc` call returned occurrences from a
  # shell and lines from inside this script. A density that depends on which
  # grep is installed is not a measurement. -E matches scan_candidates above,
  # so a pattern written with alternation counts the way it is listed.
  local ornate_total=0
  for pattern in "${ORNATE_REGISTER[@]}"; do
    local c
    c=$({ grep -ioE "$pattern" "$FILE" 2>/dev/null || true; } | wc -l | tr -d ' ')
    [[ -n "$c" ]] && ornate_total=$((ornate_total + c))
  done
  local file_words
  file_words=$(wc -w < "$FILE")
  if [[ "$file_words" -gt 0 ]]; then
    local ornate_density
    ornate_density=$(awk "BEGIN {printf \"%.1f\", $ornate_total / $file_words * 500}")
    if [[ "$JSON_MODE" != "--json" ]]; then
      echo ""
      echo "  Ornate-register density: ${ornate_density}/500w (flag above 4.0)"
    fi
    if awk "BEGIN {exit !($ornate_density > 4.0)}"; then
      ISSUES_FOUND=1
      if [[ "$JSON_MODE" == "--json" ]]; then
        RESULTS+=("{\"line\": 0, \"category\": \"ornate-register-density\", \"pattern\": \"density\", \"text\": \"${ornate_density} per 500w exceeds 4.0\"}")
      fi
    fi
  fi

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Conversational Filler (density-scored) ---"
  fi
  scan_candidates "conversational-filler" "${CONVERSATIONAL_FILLER[@]}"

  # Filler density per 500 words. The measured separation is wide: the two
  # hand-edited originals sat at 0.3 and 0.2 per 500w, their machine rewrites at
  # 2.8 and 6.8. The threshold sits below both rewrites and well above ordinary
  # human usage, so an author who writes "just" now and then is not flagged.
  #
  # Occurrences, not matching lines: `grep -c` counts lines, and a markdown
  # paragraph is one long line, so ten "just" in a paragraph would count once.
  # `-o | wc -l` is the same number on BSD and GNU grep; `-oc` is not.
  local filler_total=0
  for pattern in "${CONVERSATIONAL_FILLER[@]}"; do
    local fc
    # `|| true` inside the pipeline: grep exits 1 on no match, and with
    # `set -o pipefail` that would abort the scan mid-category.
    fc=$({ grep -ioE "$pattern" "$FILE" 2>/dev/null || true; } | wc -l | tr -d ' ')
    [[ -n "$fc" ]] && filler_total=$((filler_total + fc))
  done
  local filler_words
  filler_words=$(wc -w < "$FILE")
  if [[ "$filler_words" -gt 0 ]]; then
    local filler_density
    filler_density=$(awk "BEGIN {printf \"%.1f\", $filler_total / $filler_words * 500}")
    if [[ -z "$FILLER_DENSITY_MAX" ]]; then
      # Reported, not judged. A level says which register this is, not whether
      # it is wrong; compare against the document's own earlier rate for that.
      if [[ "$JSON_MODE" != "--json" ]]; then
        echo ""
        echo "  Conversational-filler density: ${filler_density}/500w (advisory; "
        echo "  set FILLER_DENSITY_MAX to gate, or compare with register_markers.py)"
      else
        RESULTS+=("{\"line\": 0, \"category\": \"conversational-filler-density\", \"severity\": \"candidate\", \"pattern\": \"density\", \"text\": \"${filler_density} per 500w (advisory)\"}")
      fi
    else
      if [[ "$JSON_MODE" != "--json" ]]; then
        echo ""
        echo "  Conversational-filler density: ${filler_density}/500w (flag above ${FILLER_DENSITY_MAX})"
      fi
      if awk "BEGIN {exit !($filler_density > $FILLER_DENSITY_MAX)}"; then
        ISSUES_FOUND=1
        if [[ "$JSON_MODE" == "--json" ]]; then
          RESULTS+=("{\"line\": 0, \"category\": \"conversational-filler-density\", \"pattern\": \"density\", \"text\": \"${filler_density} per 500w exceeds ${FILLER_DENSITY_MAX}\"}")
        fi
      fi
    fi
  fi

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- CoT Candidates (needs LLM verification) ---"
  fi
  scan_candidates "cot-candidate" "${COT_CANDIDATES[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Editorializing Adjectives (compressed-conversation; verify in semantic pass) ---"
  fi
  scan_candidates "editorializing" "${EDITORIALIZING[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Reader-Psychology / Invented Discourse (verify in semantic pass) ---"
  fi
  scan_candidates "reader-directive" "${READER_DIRECTIVE[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Self-Referential Meta-Narration (verify in semantic pass) ---"
  fi
  scan_candidates "meta-narration" "${META_NARRATION[@]}"

  if [[ "$JSON_MODE" == "--json" ]]; then
    echo "["
    local first=true
    # ${RESULTS[@]+...}: bash 3.2 (macOS default) treats expanding an EMPTY
    # array as unbound under set -u, so a document with zero lexical hits —
    # the cleanest possible input — crashed here with exit 1. The eval then
    # excluded those documents as failures (GH-190), silently biasing every
    # rate against clean prose. Found by GH-190's failure diagnostics.
    for r in ${RESULTS[@]+"${RESULTS[@]}"}; do
      if [[ "$first" == "true" ]]; then
        echo "  $r"
        first=false
      else
        echo "  ,$r"
      fi
    done
    echo "]"
  fi

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    if [[ $ISSUES_FOUND -eq 0 && $CANDIDATES_FOUND -eq 0 ]]; then
      echo "✓ No lexical AI patterns detected."
    elif [[ $ISSUES_FOUND -eq 0 && $CANDIDATES_FOUND -eq 1 ]]; then
      echo "~ No definite issues, but CoT candidates found above. Verify in semantic pass."
    else
      echo "✗ Lexical AI patterns found. Review above."
    fi
  fi

  if [[ $ISSUES_FOUND -eq 1 ]]; then
    GLOBAL_EXIT=1
  fi

  if [[ -n "$TEX_TMP" ]]; then rm -f "$TEX_TMP"; fi
  if [[ -n "$MD_TMP" ]]; then rm -f "$MD_TMP"; fi
  if [[ -n "$YAML_TMP" ]]; then rm -f "$YAML_TMP"; fi
  return 0
}

# --- Main: iterate over all resolved files ---
for FILE in "${FILES[@]}"; do
  run_on_file "$FILE"
  if [[ ${#FILES[@]} -gt 1 && "$JSON_MODE" != "--json" ]]; then
    echo ""
  fi
done

exit $GLOBAL_EXIT
