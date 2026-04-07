"""Platform detection and engine resolution.

On Apple Silicon → MLX. Everything else → Ollama.
Resolves engine: "auto" in endpoints.json at startup.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess

WORKSPACE = os.path.expanduser("~/local-ai/")
ENDPOINTS_JSON = os.path.join(WORKSPACE, "config/endpoints.json")


def detect_platform() -> dict:
    """Detect the current platform and recommended inference engine."""
    info = {
        "os": platform.system(),        # Darwin, Linux, Windows
        "arch": platform.machine(),     # arm64, x86_64, AMD64
        "apple_silicon": False,
        "recommended_engine": "ollama",
    }
    if info["os"] == "Darwin" and info["arch"] == "arm64":
        info["apple_silicon"] = True
        info["recommended_engine"] = "mlx"
    return info


def get_system_ram_gb() -> float:
    """Get system RAM in GB, cross-platform."""
    system = platform.system()
    try:
        if system == "Darwin":
            r = subprocess.run(["sysctl", "-n", "hw.memsize"],
                               capture_output=True, text=True, timeout=5)
            return int(r.stdout.strip()) / (1024 ** 3)
        elif system == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / (1024 ** 2)
        elif system == "Windows":
            r = subprocess.run(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/value"],
                capture_output=True, text=True, timeout=5)
            for line in r.stdout.strip().splitlines():
                if "=" in line:
                    return int(line.split("=")[1]) / (1024 ** 3)
    except Exception:
        pass
    return 16.0  # safe fallback


def startup_check() -> list[str]:
    """Run platform checks at startup. Resolves auto engines. Returns messages."""
    msgs = []
    plat = detect_platform()
    recommended = plat["recommended_engine"]

    if not os.path.exists(ENDPOINTS_JSON):
        msgs.append(
            f"[platform] No endpoints.json found. Copy the template and configure "
            f"your models. Recommended engine: {recommended}"
        )
        return msgs

    try:
        with open(ENDPOINTS_JSON) as f:
            config = json.load(f)
    except Exception as e:
        msgs.append(f"[platform] Could not read endpoints.json: {e}")
        return msgs

    # Resolve any engine: "auto" entries
    modified = False
    for ep in config.get("endpoints", []):
        if ep.get("type") == "local" and ep.get("engine") == "auto":
            ep["engine"] = recommended
            if recommended == "ollama" and "url" not in ep:
                ep["url"] = "http://localhost:11434"
            msgs.append(f"[platform] {ep.get('name', '?')}: engine auto → {recommended}")
            modified = True

    if modified:
        try:
            with open(ENDPOINTS_JSON, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            msgs.append(f"[platform] Could not save endpoints.json: {e}")

    if not msgs:
        msgs.append(f"[platform] {plat['os']} {plat['arch']} — engine: {recommended} — OK")

    return msgs
