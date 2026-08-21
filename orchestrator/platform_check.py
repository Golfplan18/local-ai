"""Platform detection and engine resolution.

On Apple Silicon → MLX. Everything else → Ollama.
Resolves engine: "auto" in routing-config.json at startup.

Reads routing-config.json since install Chunk 12 step 6 (2026-05-19).
Prior behaviour read endpoints.json (v1); the v1 file is deleted in
step 7. Endpoint shape: identify by ``id`` (v2) with fallback to
``name`` (legacy v1).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess

try:
    from . import runtime_paths as _rp
except ImportError:  # direct script-style import from sys.path
    import runtime_paths as _rp  # type: ignore

# One source for the workspace root, so a clone that lives somewhere other
# than ~/ora (an ORA_HOME install, a worktree) reads its OWN config instead
# of silently reporting "no routing-config.json found".
WORKSPACE = os.path.join(_rp.WORKSPACE, "")
ROUTING_CONFIG_JSON = str(_rp.seed_path("config", "routing-config.json"))


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

    # D-02 crash recovery is independent of the experimental execution opt-in.
    # A parent may have died after granting a unique AppContainer SID; startup
    # must revoke that lease even when G1.13 returns to degraded/fail-closed mode.
    if plat["os"] == "Windows":
        try:
            try:
                import windows_appcontainer as _wac
            except ImportError:  # pragma: no cover
                from orchestrator import windows_appcontainer as _wac
            _wac.recover_pending()
        except Exception as exc:
            msgs.append(f"[platform] AppContainer recovery failed: {exc}")

    if not os.path.exists(ROUTING_CONFIG_JSON):
        msgs.append(
            f"[platform] No routing-config.json found. Copy the template and "
            f"configure your models. Recommended engine: {recommended}"
        )
        return msgs

    try:
        # Read RAW: this is a read-modify-write of one field (endpoints'
        # engine) and the file is saved back below. Expanding ${ORA_*} here
        # would bake this machine's absolute paths into the checked-in seed
        # on the next save — the very thing the placeholders exist to stop.
        with open(ROUTING_CONFIG_JSON) as f:
            config = json.load(f)
    except Exception as e:
        msgs.append(f"[platform] Could not read routing-config.json: {e}")
        return msgs

    # Resolve any engine: "auto" entries
    modified = False
    for ep in config.get("endpoints", []):
        if ep.get("type") == "local" and ep.get("engine") == "auto":
            ep["engine"] = recommended
            if recommended == "ollama" and "url" not in ep:
                ep["url"] = "http://localhost:11434"
            ep_label = ep.get("id") or ep.get("display_name") or ep.get("name", "?")
            msgs.append(f"[platform] {ep_label}: engine auto → {recommended}")
            modified = True

    if modified:
        try:
            with open(ROUTING_CONFIG_JSON, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            msgs.append(f"[platform] Could not save routing-config.json: {e}")

    if not msgs:
        msgs.append(f"[platform] {plat['os']} {plat['arch']} — engine: {recommended} — OK")

    return msgs
