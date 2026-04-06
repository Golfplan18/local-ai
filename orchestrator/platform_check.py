"""Platform detection and engine validation.

Checks whether the configured inference engine matches the current platform.
On Apple Silicon → MLX. Everything else → Ollama.
Runs at startup and auto-corrects endpoints.json if needed.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess

WORKSPACE = os.path.expanduser("~/local-ai/")
ENDPOINTS_JSON = os.path.join(WORKSPACE, "config/endpoints.json")
ENDPOINTS_TEMPLATE = os.path.join(WORKSPACE, "config/endpoints.json.template")


def detect_platform() -> dict:
    """Detect the current platform and available inference engine."""
    info = {
        "os": platform.system(),           # Darwin, Linux, Windows
        "arch": platform.machine(),        # arm64, x86_64, AMD64
        "apple_silicon": False,
        "has_nvidia_gpu": False,
        "recommended_engine": "ollama",
    }

    # Apple Silicon detection
    if info["os"] == "Darwin" and info["arch"] == "arm64":
        info["apple_silicon"] = True
        info["recommended_engine"] = "mlx"

    # NVIDIA GPU detection (Linux/Windows)
    if info["os"] in ("Linux", "Windows"):
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
            info["has_nvidia_gpu"] = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return info


def check_engine_available(engine: str) -> bool:
    """Check if the specified engine is actually installed."""
    if engine == "mlx":
        try:
            subprocess.run(
                ["python3", "-c", "import mlx_lm"],
                capture_output=True, timeout=10,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    elif engine == "ollama":
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    return False


def validate_and_fix_endpoints() -> list[str]:
    """Check endpoints.json against the current platform.

    If local endpoints use the wrong engine for this platform,
    auto-correct them and return a list of warning messages.

    Returns:
        List of warning/info messages (empty if everything is fine).
    """
    messages = []
    plat = detect_platform()
    recommended = plat["recommended_engine"]

    if not os.path.exists(ENDPOINTS_JSON):
        # No endpoints.json — create from template if available
        if os.path.exists(ENDPOINTS_TEMPLATE):
            messages.append(
                f"[platform] No endpoints.json found. Copy the template and configure "
                f"your models. Recommended engine for this platform: {recommended}"
            )
        return messages

    try:
        with open(ENDPOINTS_JSON) as f:
            config = json.load(f)
    except Exception as e:
        messages.append(f"[platform] Could not read endpoints.json: {e}")
        return messages

    modified = False
    endpoints = config.get("endpoints", [])

    for ep in endpoints:
        if ep.get("type") != "local":
            continue

        engine = ep.get("engine", "ollama")

        # Resolve "auto" engine to the recommended engine for this platform
        if engine == "auto":
            ep["engine"] = recommended
            engine = recommended
            messages.append(
                f"[platform] Endpoint '{ep.get('name', 'unknown')}': "
                f"engine 'auto' resolved to '{recommended}' for {plat['os']} ({plat['arch']})"
            )
            modified = True

        # Check for engine/platform mismatch
        if engine == "mlx" and not plat["apple_silicon"]:
            old_name = ep.get("name", "unknown")
            ep["engine"] = "ollama"
            # Convert model path to Ollama model name if it's a file path
            model = ep.get("model", "")
            if "/" in model and not model.startswith("http"):
                # MLX path like ~/local-ai/models/gpt-oss-120b → keep as-is but warn
                messages.append(
                    f"[platform] Endpoint '{old_name}': switched engine mlx → ollama. "
                    f"Model path '{model}' may need updating to an Ollama model name "
                    f"(e.g., 'llama3:70b'). Run 'ollama list' to see available models."
                )
            # Update endpoint name if it contains 'mlx'
            if "mlx" in ep.get("name", ""):
                ep["name"] = ep["name"].replace("mlx", "ollama")
            # Add Ollama URL if missing
            if "url" not in ep:
                ep["url"] = "http://localhost:11434"
            modified = True

        elif engine == "ollama" and plat["apple_silicon"]:
            # Ollama on Apple Silicon works fine, but MLX is recommended
            if not check_engine_available("ollama") and check_engine_available("mlx"):
                ep["engine"] = "mlx"
                if "mlx" not in ep.get("name", ""):
                    ep["name"] = ep["name"].replace("ollama", "mlx")
                messages.append(
                    f"[platform] Endpoint '{ep.get('name')}': switched engine ollama → mlx "
                    f"(Ollama not found, MLX available on this Apple Silicon Mac)."
                )
                modified = True

    # Update slot_assignments and routing if endpoint names changed
    if modified:
        # Update any references to old endpoint names
        for section in ("slot_assignments", "routing"):
            mapping = config.get(section, {})
            for key, val in list(mapping.items()):
                if "mlx" in val and not plat["apple_silicon"]:
                    mapping[key] = val.replace("mlx", "ollama")
                elif "ollama" in val and plat["apple_silicon"] and not check_engine_available("ollama"):
                    mapping[key] = val.replace("ollama", "mlx")

        if config.get("default_endpoint") and "mlx" in config["default_endpoint"] and not plat["apple_silicon"]:
            config["default_endpoint"] = config["default_endpoint"].replace("mlx", "ollama")

        # Write the corrected config
        try:
            with open(ENDPOINTS_JSON, "w") as f:
                json.dump(config, f, indent=2)
            messages.append(
                f"[platform] endpoints.json auto-corrected for {plat['os']} ({plat['arch']}). "
                f"Engine: {recommended}. Review config/endpoints.json to set your model names."
            )
        except Exception as e:
            messages.append(f"[platform] Could not write corrected endpoints.json: {e}")

    if not modified and not messages:
        messages.append(
            f"[platform] {plat['os']} {plat['arch']} — engine: {recommended} — config OK"
        )

    return messages


def startup_check() -> list[str]:
    """Run all platform checks at startup. Returns list of messages to display."""
    msgs = validate_and_fix_endpoints()

    plat = detect_platform()
    engine = plat["recommended_engine"]

    if not check_engine_available(engine):
        if engine == "mlx":
            msgs.append(
                "[platform] WARNING: MLX (mlx-lm) is not installed. "
                "Install it with: pip3 install mlx-lm"
            )
        elif engine == "ollama":
            msgs.append(
                "[platform] WARNING: Ollama is not installed. "
                "Install it from https://ollama.com or run: curl -fsSL https://ollama.com/install.sh | sh"
            )

    return msgs
