#!/usr/bin/env bash
# detect-lexical.sh — Scan markdown files for AI writing giveaway words/phrases
# Usage: ./detect-lexical.sh <file-or-dir> [file-or-dir ...] [--json]
#
# Accepts: single file, multiple files, directories (scans *.md recursively).
# Outputs line-numbered matches grouped by category.
# Exit code: 0 = clean, 1 = issues found, 2 = usage error

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <file-or-dir> [file-or-dir ...] [--json]" >&2
  exit 2
fi

# Separate flags from paths
JSON_MODE=""
declare -a PATHS=()
for arg in "$@"; do
  if [[ "$arg" == "--json" ]]; then
    JSON_MODE="--json"
  else
    PATHS+=("$arg")
  fi
done

if [[ ${#PATHS[@]} -eq 0 ]]; then
  echo "Usage: $0 <file-or-dir> [file-or-dir ...] [--json]" >&2
  exit 2
fi

# Resolve all paths into a list of .md files
declare -a FILES=()
for p in "${PATHS[@]}"; do
  if [[ -d "$p" ]]; then
    while IFS= read -r -d '' f; do
      FILES+=("$f")
    done < <(find "$p" -name '*.md' -type f -print0 | sort -z)
  elif [[ -f "$p" ]]; then
    FILES+=("$p")
  else
    echo "Error: Not found: $p" >&2
    exit 2
  fi
done

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "Error: No .md files found in the given paths." >&2
  exit 2
fi

GLOBAL_EXIT=0
ISSUES_FOUND=0
CANDIDATES_FOUND=0
declare -a RESULTS=()

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
  "sound"
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
  "sharp" "sharpen"
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
)

# --- Category: AI cliché phrases ---
AI_PHRASES=(
  "at the heart of"
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
  "^first,"
  "^second,"
  "^third,"
  "^finally,"
  "^in addition,"
  "^on one hand"
  "^on the other hand"
  "^while this is true"
  "^having said that"
  "^that being said"
  "^with that in mind"
  "^with this in place"
  "^given this,"
  "^that said,"
  "^and so,"
  "^moving on"
  "^turning to"
  "^building on"
  "^to begin with"
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
  # rhetorical glue
  " merely "
  "^nor "
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
  '^[Ww]hile .*, '
  'whether .* or '
)

scan_patterns() {
  local category="$1"
  shift
  local patterns=("$@")

  for pattern in "${patterns[@]}"; do
    # Case-insensitive grep with line numbers
    local matches
    matches=$(grep -in "$pattern" "$FILE" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
      ISSUES_FOUND=1
      while IFS= read -r line; do
        local lineno="${line%%:*}"
        local content="${line#*:}"
        if [[ "$JSON_MODE" == "--json" ]]; then
          RESULTS+=("{\"line\": $lineno, \"category\": \"$category\", \"pattern\": \"$(echo "$pattern" | sed 's/"/\\"/g')\", \"text\": \"$(echo "$content" | sed 's/"/\\"/g' | head -c 200)\"}")
        else
          printf "  L%-4s [%s] %s\n" "$lineno" "$pattern" "$(echo "$content" | head -c 120)"
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

  for pattern in "${patterns[@]}"; do
    local matches
    matches=$(grep -in "$pattern" "$FILE" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
      CANDIDATES_FOUND=1
      while IFS= read -r line; do
        local lineno="${line%%:*}"
        local content="${line#*:}"
        if [[ "$JSON_MODE" == "--json" ]]; then
          RESULTS+=("{\"line\": $lineno, \"category\": \"$category\", \"severity\": \"candidate\", \"pattern\": \"$(echo "$pattern" | sed 's/"/\\"/g')\", \"text\": \"$(echo "$content" | sed 's/"/\\"/g' | head -c 200)\"}")
        else
          printf "  L%-4s [%s] %s\n" "$lineno" "$pattern" "$(echo "$content" | head -c 120)"
        fi
      done <<< "$matches"
    fi
  done
}

run_on_file() {
  local FILE="$1"
  ISSUES_FOUND=0
  CANDIDATES_FOUND=0
  RESULTS=()

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo "=== Lexical AI Detection: $FILE ==="
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
        RESULTS+=("{\"line\": -1, \"category\": \"chat-residue-tail\", \"pattern\": \"$(echo "$pattern" | sed 's/"/\\"/g')\", \"text\": \"match within final 3 lines — near-certain assistant sign-off\"}")
      else
        printf "  CRITICAL: \"%s\" appears in the FINAL 3 LINES — near-certain assistant sign-off. Delete it.\n" "$pattern"
      fi
    fi
  done

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- Banned Words ---"
  fi
  scan_patterns "banned-word" "${BANNED_WORDS[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- AI Cliché Phrases ---"
  fi
  scan_patterns "ai-cliche" "${AI_PHRASES[@]}"

  if [[ "$JSON_MODE" != "--json" ]]; then
    echo ""
    echo "--- False Emphasis ---"
  fi
  scan_patterns "false-emphasis" "${FALSE_EMPHASIS[@]}"

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
        RESULTS+=("{\"line\": $lineno, \"category\": \"ordinal-sequence\", \"pattern\": \"First,/Second,/...\", \"text\": \"$(echo "$line" | sed 's/"/\\"/g' | head -c 160)\"}")
      else
        printf "  L%-4s [%s distinct ordinals] %s\n" "$lineno" "$distinct" "$(echo "$line" | head -c 120)"
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
  local ornate_total=0
  for pattern in "${ORNATE_REGISTER[@]}"; do
    local c
    c=$(grep -ioc "$pattern" "$FILE" 2>/dev/null || true)
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
    echo "--- CoT Candidates (needs LLM verification) ---"
  fi
  scan_candidates "cot-candidate" "${COT_CANDIDATES[@]}"

  if [[ "$JSON_MODE" == "--json" ]]; then
    echo "["
    local first=true
    for r in "${RESULTS[@]}"; do
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
}

# --- Main: iterate over all resolved files ---
for FILE in "${FILES[@]}"; do
  run_on_file "$FILE"
  if [[ ${#FILES[@]} -gt 1 && "$JSON_MODE" != "--json" ]]; then
    echo ""
  fi
done

exit $GLOBAL_EXIT
