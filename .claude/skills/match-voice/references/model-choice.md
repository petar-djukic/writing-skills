# Model choice

Which model to rewrite with, and why. Read once when setting up or when
changing models; the default works without it.

**Default (GH-145): `cohere:command-a-03-2025`.** The GH-138/142 bake-off found
it drives a draft toward human where the gemma family raises the Pangram score,
and after the 422-retry fix it runs clean through the gate. It is a hosted API
(needs `COHERE_API_KEY`/`COHERE_SECRETS_FILE`, bills per token, sends the draft
off the machine). The table below is now the **local / no-egress fallback**
reference — set `--model gemma4:12b` (or `MATCH_VOICE_MODEL`) on a keyless
machine or when the draft must stay local. Full Cohere reasoning:
[cohere-bakeoff.md](./cohere-bakeoff.md).

**Model choice (GH-163 bake-off, 10 models on one paragraph with identical
anchors, judged on voice fidelity plus the full gate):**

| Use | Model | Why |
|---|---|---|
| Local default | `gemma4:12b` | best local everywhere: faithful near-verbatim pass, no term or claim damage |
| Local, 32 GB Apple Silicon | `gemma4:31b-mlx` | the 31b tier without egress (inferred from the cloud row, not separately bake-offed) |
| Cloud, best overall | `gemma4:31b-cloud` | restructures naturally, preserves every term and claim, no flags |
| Cloud, second opinion | `kimi-k2.6:cloud` | minimal and judicious — edits least, damages nothing |

**Prefer local when the machine can hold the model.** Rewriting operates on
unpublished draft prose, and the cloud rows send every paragraph off the
machine to buy quality that a big-memory Mac already has locally. Reach for
cloud when the memory is not there, or for the second opinion.

The 31b row wants roughly 32 GB of unified memory: an mlx build of that tier
is a ~20 GB weight file, and context and the rest of the system go on top.
Measured on an M2 Max with 32 GB, where the comparable `qwen3.6:35b-mlx`
occupies 21 GB and runs. At 16 GB, stay on `gemma4:12b` (7.6 GB); a model that
does not fit swaps, and a rewrite that takes minutes per paragraph is a
rewrite nobody runs. `ollama list` shows the size before you commit to it.

The two cloud models are complementary: one rewrites well, the other knows
when not to. `mistral-large-3` editorializes (trips the register scan);
`glm-5.2` and `deepseek-v4-flash` are safe but flatten deliberate rhythm.
**`llama3.1:8b` ranked last** — it destroyed a term of art and weakened a
claim while passing the mechanical gate, which is precisely why the semantic
half of the gate is not optional.

A first `ollama pull` of a cloud model can fail transiently; an immediate
retry succeeds.

## Cohere (GH-138)

A later bake-off added Cohere's command-a models against these incumbents, through the real driver. Summary: `command-a-03-2025` won the Pangram axis decisively (drove a 0.744 draft to 0.246, where gemma4:31b *raised* it to 1.000) but failed often through the gate (integration-level, likely fixable). Full report: [cohere-bakeoff.md](./cohere-bakeoff.md).

`command-a-plus-05-2026` was disqualified there for chain-of-thought leakage, and that disqualification no longer stands (GH-155). Cohere separates reasoning into its own content block; reading blocks by type keeps it out of the prose (GH-154), and the model is no longer refused. GH-156 measured the two against each other on a real draft: `command-a-plus-05-2026` was cleanest of any arm (18/19 paragraphs fully clean, zero runaway rewrites, 9/9 citations) in the single-message shape the code already uses, against 15/19 for `command-a-03-2025`. GH-160 then covered the register axis: on Pangram, command-a-plus and command-a-03 tie (0.884 vs 0.876 fraction_ai from a 1.000 baseline — the only two models of four to move a saturated draft at all), and command-a-plus stays mechanically cleaner. The GH-145 default stands: register shows no gain that would justify a reasoning model's scratchpad cost per paragraph. command-a-plus is a legitimate alternative for a run where mechanical cleanliness matters more than tokens.
