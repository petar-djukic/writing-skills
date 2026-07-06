# De-AI Detection Report

## File: {filename}
## Date: {date}
## Iteration: {iteration} of {max_iterations}

---

## Pass 0: Cold Read (Prompt 0, before scripts)

- Followable on one pass: {cold_followable}
- Register: {cold_register}
- Hardest sentences: {cold_hardest}
- COLD_VERDICT: {cold_verdict}

---

## Pass 1: Lexical Scan

| Line | Category | Pattern | Text |
|------|----------|---------|------|
{lexical_findings}

**Lexical Issues: {lexical_count}**

---

## Pass 2: Structural Analysis

### Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Sentence length std | {sent_std} | > {sent_threshold} | {sent_status} |
| Paragraph length std | {para_std} | > {para_threshold} | {para_status} |
| Opening diversity | {diversity} | > {div_threshold} | {div_status} |
| List ratio | {list_ratio} | < {list_threshold} | {list_status} |
| Colon density /500w | {colon_d} | < {colon_threshold} | {colon_status} |
| Dash density /500w | {dash_d} | < {dash_threshold} | {dash_status} |
| Plain sentence rate | {plain_rate} | > {plain_threshold} | {plain_status} |
| Punch clustering | {punch_clust} | < {punch_threshold} | {punch_status} |
| Salad rate /100 | {salad_rate} | < {salad_threshold} | {salad_status} |
| Ornate register /500w | {ornate_d} | < 4.0 | {ornate_status} |

### Repeated Formulae

| Phrase | Count | Files |
|--------|-------|-------|
{formulae_rows}

### Structural Issues

{structural_findings}

**Structural Issues: {structural_count}**
**Verdict: {structural_verdict}**

---

## Pass 3: Semantic Analysis (Opus)

### Vocabulary Predictability
- Overall Score: {vocab_score}/5
- High-predictability sentences: {high_pred_sentences}

### Burstiness
- Rhythm Score: {rhythm_score}/5
- Information Density Uniformity: {density_score}/5

### Cross-Sentence Surprise
- Mean Surprise: {surprise_mean}/5
- Longest Predictable Run: {pred_run} sentences

### CoT Leakage
- Total Leaks: {cot_count}
- Density: {cot_density} per 500 words
- Categories: {cot_categories}

### Definedness and Circularity (Prompt 8)
- Undefined terms: {undefined_terms}
- Circular claims: {circular_claims}
- Quantity mismatches: {quantity_mismatches}
- Venue-jargon hits (lexical): {venue_jargon_hits}
- Abstract/intro opener duplication: {opener_duplication}

### Paragraph Schema (Prompt 9 + proxies)
- Mean topic overlap / cohesion / subject churn: {schema_means}
- Low-topic paragraphs (proxy): {low_topic_paragraphs}
- MEAL defects (no main idea / evidence-first / link-only): {meal_defects}
- Incoherent claims (nonsense check): {incoherent_claims}

### Overshoot Assessment (Prompt 7)
- Overshoot Score: {overshoot_score}/100
- Confirmed punches: {confirmed_punches}
- Sentences to unpack: {salad_to_unpack}
- Formulae to consolidate: {formulae_consolidation}
- Overshoot Verdict: {overshoot_verdict}

---

## Integrated Assessment

Two-axis verdict — AI failure has a bland direction and an ornate direction;
state where the document sits on each:

- Bland axis (predictable vocabulary, uniform rhythm): {bland_axis}
- Ornate axis (uniform polish, epigrams, salads): {ornate_axis}

- **AI Probability: {ai_probability}%**
- **Confidence: {confidence}**
- **Primary Signals: {primary_signals}**

---

## Rewrite Targets (Priority Order)

{rewrite_targets}

---

## Convergence Status

| Iteration | Issues Found | Delta | Action |
|-----------|-------------|-------|--------|
{convergence_table}

**Status: {convergence_status}**
