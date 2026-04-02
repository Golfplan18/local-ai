### PHASE 2, LAYER 2: MODEL SELECTION

**Stage Focus**: Help the user understand their options and select the right model — or select one automatically if the user prefers. Then validate the selection against hardware constraints, estimating RAM requirements from parameter count and quantization level (never from file size).

**Input**: Hardware profile from Layer 1, plus any user-specified model from the Input Contract.

**Output**: A validated model selection containing: model name, Hugging Face repository URL or Ollama identifier, parameter count, quantization level, estimated RAM requirement at inference (calculated from parameters, not file size), estimated disk footprint, model format, download source, list of required companion files, and validation status.

### Determine Selection Mode

IF the user provided a specific model name or URL, THEN enter User-Specified Mode (Section 2.2).

IF the user requested automatic selection, THEN enter Auto-Selection Mode (Section 2.3).

IF the user requested exploration, THEN enter Model Exploration Mode (Section 2.1) first, then proceed to either User-Specified or Auto-Selection after the user makes a decision.

IF the user's intent is unclear, THEN enter Model Exploration Mode.

---

#### 2.1 Model Exploration Mode

This mode helps users understand what AI models are, what their options are, and how to choose. There is no limit to the number of questions the user can ask. The exploration ends when the user makes a selection decision or asks the framework to choose for them.

**Entry point.** Present the following, then wait for the user's response:

```
Before selecting a model, it helps to understand your options.
I can guide you through this, or you can tell me what you already know.

Which best describes where you are?

A) I have a specific model I want to install.
   (Give me the Hugging Face URL, repository name, or model name.)

B) I know roughly what I want but need help choosing.
   (I'll ask about your use case and recommend options.)

C) I'm new to this and want to understand my options.
   (I'll explain what AI models are, what's available, and help
   you figure out what's right for you.)

D) Just pick the best model for my hardware.
   (I'll select automatically based on your specs.)
```

**IF the user selects A:** Record the model identifier and proceed to User-Specified Mode (Section 2.2).

**IF the user selects D:** Proceed to Auto-Selection Mode (Section 2.3).

**IF the user selects B or C:** Begin the structured exploration below, then continue answering any follow-up questions the user asks. Do not impose a question limit.

**Structured Exploration Sequence:**

The following topics are covered in order, but the user may skip ahead, ask tangential questions, or go deeper on any topic. Answer every question fully and accurately. Use plain language. Technical terms should be defined when first introduced.

**Topic 1 — What is an AI model?**
Briefly explain: a model is a large file (or set of files) containing the patterns an AI learned during training. It runs on the user's machine using an inference engine. Different models have different capabilities, sizes, and specialties. Explain that "running locally" means no data leaves their computer.

**Topic 2 — What do you want to use it for?**
Ask the user about their intended use case. Common categories: general conversation and questions, writing and editing, coding and technical work, analysis and research, creative projects, domain-specific work (legal, medical, financial). The answer informs which model families and sizes are most appropriate.

**Topic 3 — Model families and what makes them different.**
Cover the major open-weight model families the user is likely to encounter, tailored to what is current at the time of execution. Use web search to identify current leading models if needed. For each relevant family, explain in one or two sentences: who makes it, what it is known for, and what size range it comes in. Families to address include (but are not limited to):
- Llama (Meta) — widely used, strong general-purpose
- Qwen (Alibaba) — strong multilingual and reasoning
- Mistral/Mixtral (Mistral AI) — efficient, strong instruction following
- DeepSeek (DeepSeek AI) — strong reasoning, includes distilled variants
- GPT-oss / abliterated variants (community derivatives of OpenAI architecture) — uncensored, strong generation, require special chat templates
- Gemma (Google) — smaller models with strong benchmark performance
- Phi (Microsoft) — small but capable

**Topic 4 — Model sizes and what they mean for performance.**
Explain parameter counts in plain language. Rough guidance: 1–3B parameters (basic tasks, fast, low resource), 7–9B (solid general use, runs on 16GB RAM), 14–32B (strong reasoning and writing, needs 32–64GB RAM), 70B+ (near-frontier quality, needs 64GB+ RAM). Explain that bigger is generally more capable but requires more RAM and runs slower. Connect to the user's available RAM from the hardware evaluation.

**Topic 5 — Quantization: trading precision for speed and size.**
Explain in plain language: quantization reduces the precision of the model's numbers from 16-bit to 8-bit or 4-bit, dramatically reducing RAM requirements with modest quality loss. At 4-bit quantization, a model needs roughly half a gigabyte of RAM per billion parameters. At 8-bit, roughly one gigabyte per billion parameters. At 16-bit (full precision), roughly two gigabytes per billion parameters. Plus 1–2 GB overhead for the inference engine.

Explain common quantization labels: Q4_K_M, Q5_K_M, Q8_0 (GGUF naming), 4bit, 8bit (MLX naming), GPTQ, AWQ, MXFP4 (other formats). The user does not need to memorize these, but should know that "4-bit" or "Q4" means smaller and faster, "8-bit" or "Q8" means higher quality but bigger.

**Note on tool calling and model size:** Reliable tool calling requires a model of sufficient size and capability — as a rough guide, 13B+ at 4-bit quantization, or 7B at 8-bit. Users at Scout tier with 8GB RAM may encounter the Local Model Tool Reliability Trap with very small models. Flag this when selecting models at the lower end of the hardware capability range.

**Topic 6 — Dense vs. Mixture of Experts (MoE).**
Explain briefly: dense models use all their parameters for every response (deeper reasoning per token). MoE models activate only a subset of parameters per token (faster, broader associative reach). A 120B MoE model with 5.7B active parameters runs more like a 6B dense model in speed but draws from 120B parameters of knowledge. Most users will encounter both types.

**Topic 7 — Practical considerations on Hugging Face.**
Explain what the user will see when browsing Hugging Face: repository names, model cards, file listings, download counts, community ratings. Warn about XET pointers. Explain required companion files. The framework handles this automatically, but users should know it exists.

**After the structured topics, open the floor:**
```
Those are the key concepts. Based on your hardware ([X] GB RAM,
[platform]), you can run models up to approximately [X]B parameters
at 4-bit quantization, or [X]B parameters at 8-bit.

Do you have questions about any of this? Want me to look up specific
models? Or are you ready to choose?

You can:
- Name a specific model or paste a Hugging Face link
- Tell me your use case and I'll recommend options
- Ask me to pick the best general-purpose model for your hardware
- Ask more questions — take as long as you need
```

**Continue answering questions until the user makes a selection decision.** When the user makes a decision: record the decision and proceed to User-Specified Mode (if they named a model) or Auto-Selection Mode (if they asked for automatic selection).

---

#### 2.2 User-Specified Mode

The user has named a specific model. The framework validates it against hardware constraints and ensures all required files are available.

Calculate AVAILABLE_MODEL_RAM = total RAM × 0.75.

**Step 1: Resolve the model identifier.**

IF the user provided a Hugging Face URL, THEN extract the repository identifier (organization/model-name).
IF the user provided a repository identifier, THEN use it directly.
IF the user provided an Ollama model name AND APPLE_SILICON = false, THEN use the Ollama identifier directly and skip to Step 4.

**Step 2: Determine actual model parameters and RAM requirement.**

This is the critical step. Do not estimate RAM from file size.

a. Fetch the model's `config.json` from the Hugging Face repository.
b. Extract the parameter count. Look for fields in this order of preference:
   - `num_parameters` (if present, use directly)
   - Calculate from architecture fields: `hidden_size`, `num_hidden_layers`, `intermediate_size`, `num_attention_heads`, `vocab_size`.
   - IF neither method works, THEN check the model card (README.md) for stated parameter count.
   - IF parameter count cannot be determined, THEN warn the user and proceed with caution.

c. Detect XET pointers. IF detected, THEN note: "This repository uses XET external storage. Estimating from parameter count instead."

d. Determine quantization level. Check the repository name, config.json, and model card. IF no quantization detected, THEN assume 16-bit (full precision).

e. Estimate RAM at inference:
   - 4-bit quantization: parameter_count × 0.5 GB per billion + 2 GB overhead
   - 8-bit quantization: parameter_count × 1.0 GB per billion + 2 GB overhead
   - 16-bit (full precision): parameter_count × 2.0 GB per billion + 2 GB overhead
   - For MoE models: use total parameter count for disk estimation, use active parameter count for RAM estimation.

**Step 3: Determine format compatibility.**

IF APPLE_SILICON = true, THEN the inference engine will be MLX. Models must be available in MLX format (safetensors with MLX-compatible configuration). IF the specified model is not in MLX format, THEN search Hugging Face for an MLX-converted version.

IF APPLE_SILICON = false, THEN the inference engine will be Ollama. Models must be available through the Ollama library or as GGUF files.

**Step 4: Identify required companion files.**

For MLX/safetensors models, verify the repository contains:
- config.json (required)
- tokenizer.json and/or tokenizer_config.json (required — at least one must be present)
- All weight files referenced in the model index
- Chat template: check tokenizer_config.json for a `chat_template` field. IF absent, warn the user (non-fatal).

For GGUF models: verify the GGUF file is present and non-trivial in size.

For Ollama models: Ollama manages all companion files internally.

**Step 5: Validate against hardware constraints.**

a. Validate disk space: IF estimated disk footprint exceeds 80% of available disk space, THEN report and ask whether to proceed.

b. Validate RAM: IF estimated RAM at inference exceeds AVAILABLE_MODEL_RAM, THEN report the constraint and offer alternatives.

**Step 6: Present validation results and wait for confirmation.**

```
MODEL VALIDATION RESULTS

Model: [name]
  Repository: [URL]
  Parameters: [count] ([dense / MoE with X active])
  Quantization: [level]
  Format: [MLX / GGUF / Ollama]
  Estimated size on disk: ~[X] GB
  Estimated RAM at inference: ~[X] GB
  Available model RAM: [X] GB (headroom after model: [X] GB)
  Required companion files: [list — all present / missing: (list)]
  Chat template: [found / not found — default will be used]
  Tool calling: [reliable at this size / may require explicit prompting — see Local Model Tool Reliability Trap]
  Status: [✓ Validated / ⚠ Warning — (reason) / ✗ Incompatible — (reason)]

Shall I proceed with downloading this model?
```

---

#### 2.3 Auto-Selection Mode

Calculate AVAILABLE_MODEL_RAM = total RAM × 0.75.

**Tier Selection:**

- **Tier 1 — Minimum viable (AVAILABLE_MODEL_RAM 6–11 GB):** 3–7B parameters at 4-bit. Note: tool calling may require explicit prompting at this tier.
- **Tier 2 — Capable (AVAILABLE_MODEL_RAM 12–23 GB):** 7–14B parameters at 4-bit.
- **Tier 3 — Strong (AVAILABLE_MODEL_RAM 24–47 GB):** 30–70B parameters at 4-bit.
- **Tier 4 — Professional (AVAILABLE_MODEL_RAM 48–95 GB):** 70B+ parameters at 4-bit or 8-bit.
- **Tier 5 — Multi-model (AVAILABLE_MODEL_RAM 96+ GB):** Two large models simultaneously. Inform the user that multi-model adversarial pipelines are covered in the book's architecture chapters.

**Specific Model Selection:**

Search for the current best-rated open-weight model at the target size for the user's platform. Prioritize models with strong community adoption, benchmark performance, and broad compatibility.

IF the coding agent cannot determine the current best model, THEN default to:
- Tier 1: Qwen3 family, smallest available at 4-bit
- Tier 2: Qwen3 or Llama family, medium size at 4-bit
- Tier 3: Qwen3, Llama, or Mistral family, large size at 4-bit
- Tier 4–5: Largest available high-quality open model at the appropriate quantization

After selecting, run the same validation steps from User-Specified Mode (Steps 2–6).

### Output Format for This Layer

```
MODEL SELECTION ([Auto / User-specified])
Model: [name and version]
Repository: [URL]
Parameters: [count] ([dense / MoE])
Quantization: [level]
Format: [MLX / GGUF / Ollama]
Estimated size on disk: ~[X] GB
Estimated RAM at inference: ~[X] GB (calculated from [X]B parameters × [formula])
Available model RAM: [X] GB (headroom: [X] GB)
Required companion files: [all present / list of files]
Chat template: [status]
Tool calling reliability: [reliable / may require explicit prompting]
Source: [Hugging Face URL / Ollama library]
[IF auto-selected:] Tier: [1-5]
Rationale: [one sentence explaining why this model was selected]
```

Display the selection to the user and wait for confirmation before proceeding.

### Invariant Check

Before proceeding: confirm that the model's RAM estimate was calculated from parameter count and quantization level, not from file size. Confirm the model identifier, format, and list of required companion files are recorded for Layer 5.

---

