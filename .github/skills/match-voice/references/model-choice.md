# Model choice

Which Ollama model to rewrite with, and why. Read once when setting up or when
changing models; the default works without it.

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
