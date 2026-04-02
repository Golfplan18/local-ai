### PHASE 2, LAYER 5: MODEL DOWNLOAD

**Stage Focus**: Download the validated model and all required companion files to the workspace. IF the model is already present locally, THEN skip re-downloading. Verify completeness of all required files after download.

**Input**: Validated model selection from Layer 2 (including list of required companion files), workspace path from Layer 3, inference engine from Layer 4.

**Output**: Model and all companion files available locally, verified by integrity check.

### Processing Instructions

1. Check whether the model is already present locally:
   - IF MLX: Check whether the model exists in the Hugging Face cache or in the workspace models directory. IF present, THEN verify integrity. IF integrity check passes, THEN skip download and report: "Model [name] is already downloaded. Skipping."
   - IF Ollama: Execute `ollama list` and check whether the model appears.

2. Inform the user before starting download:
   ```
   Downloading: [model name] (~[X] GB).
   This may take [estimated time based on ~10 MB/s] depending on
   your internet connection.
   ```

3. **MLX Download Path:**
   a. Download using huggingface-cli:
      `huggingface-cli download [model_repo] --local-dir [workspace]/models/[model_name]`
   b. IF the download command does not fetch all files, THEN download missing files individually.
   c. Record the actual storage location.

4. **Ollama Download Path:**
   a. Start the Ollama service if not running: `ollama serve &`
   b. Pull the model: `ollama pull [model_name]`.

5. **Post-download companion file verification (MLX/safetensors models):**
   a. Verify config.json exists and is valid JSON.
   b. Verify tokenizer files: at minimum, tokenizer.json or tokenizer_config.json must be present.
   c. Verify weight files: IF a model index file exists, THEN verify every weight shard referenced in the index is present and non-trivial in size. IF any weight file is under 1 MB, THEN suspect XET pointer stubs.
   d. Verify chat template.
   e. IF any required file is missing after download, THEN attempt to download it individually.

6. IF download verification fails, THEN report the specific failure.

### Output Format for This Layer

```
MODEL DOWNLOAD RESULTS

Model: [name]
  Location: [path or "Managed by Ollama"]
  Weight files: [count] files, [total size] GB — [verified / issues found]
  Tokenizer: [present / missing — (details)]
  Config: [present / missing]
  Chat template: [found in tokenizer_config / separate file / not found — default will be used]
  Status: [✓ Downloaded and verified / ⚠ Warning — (detail) / ✗ Failed — (reason)]
```

### Invariant Check

Before proceeding: confirm that the model can be loaded by the inference engine. For MLX, execute a minimal load test. For Ollama, execute `ollama show [model_name]`. Do not proceed to Phase 2, Layer 6 with an unloadable model.

---

