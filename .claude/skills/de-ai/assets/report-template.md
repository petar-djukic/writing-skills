# De-AI Detection Report

## File: {filename}
## Date: {date}
## Iteration: {iteration} of {max_iterations}

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

---

## Integrated Assessment

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
