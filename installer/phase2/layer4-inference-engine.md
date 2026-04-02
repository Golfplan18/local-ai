### PHASE 2, LAYER 4: INFERENCE ENGINE INSTALLATION

**Stage Focus**: Ensure the appropriate inference engine is installed, current, and functional. IF already installed, THEN verify and update if needed rather than reinstalling.

**Input**: Hardware profile (specifically: APPLE_SILICON status, HAS_NVIDIA_GPU status, operating system).

**Output**: A working inference engine installation verified by a version check command.

### Processing Instructions

1. Select the inference engine:
   - IF APPLE_SILICON = true, THEN the target engine is MLX (`mlx-lm`).
   - IF APPLE_SILICON = false, THEN the target engine is Ollama.

2. **MLX Installation Path (Apple Silicon):**
   a. Check whether Python 3.10+ is installed: `python3 --version`.
      - IF Python is not installed or version is below 3.10, THEN install it via `brew install python` (install Homebrew first if needed: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`).
      - Before installing Homebrew, explain to the user: "Homebrew is a standard package manager for macOS. It is needed to install Python, which the AI inference engine requires. This is a one-time installation."
   b. Check whether MLX is already installed: `python3 -c "import mlx_lm; print(mlx_lm.__version__)"`.
      - IF mlx-lm is already installed, THEN report the installed version. Run `pip3 install --upgrade mlx-lm` to ensure it is current.
      - IF mlx-lm is not installed, THEN install it: `pip3 install mlx-lm`.
   c. Ensure huggingface-cli is available: `pip3 install --upgrade huggingface_hub`.
   d. Verify installation: `python3 -c "import mlx_lm; print('MLX-LM version:', mlx_lm.__version__)"`.
   e. IF verification fails, THEN report the specific error.

3. **Ollama Installation Path (Non-Apple Silicon):**
   a. Check whether Ollama is already installed: `ollama --version`.
      - IF Ollama is already installed, THEN report the installed version and proceed to verification.
      - IF Ollama is not installed, THEN install it:
        - IF macOS (Intel): `brew install ollama`
        - IF Linux: `curl -fsSL https://ollama.com/install.sh | sh`
        - IF Windows: Download the Ollama installer from the Ollama website and execute it.
   b. Verify installation: `ollama --version`.
   c. IF verification fails, THEN report the specific error.

### Output Format for This Layer

```
INFERENCE ENGINE STATUS
Engine: [MLX / Ollama]
Version: [version string]
Status: [Already installed (updated) / Already installed (current) / Newly installed]
Installation method: [pip / brew / curl / installer / pre-existing]
```

### Invariant Check

Before proceeding: confirm inference engine type matches APPLE_SILICON status from Layer 1. Confirm model format from Layer 2 is compatible with the installed engine (MLX engine → safetensors format; Ollama engine → GGUF or Ollama format).

---

