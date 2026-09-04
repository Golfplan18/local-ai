"""
resilience.py — Orchestrator Resilience and Degradation (Phase 14)

Two components:
  14.1 — KV cache release between sequential model calls (Gear 4 on constrained hardware)
  14.2 — Graceful gear degradation logic with signaling

Degradation is always signaled, never silent. Uses Budget Signals 1-4.

Usage:
    from orchestrator.tools.resilience import (
        check_hardware_constraints, get_degradation_path,
        should_release_kv_cache,
    )
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 14.1 — KV Cache Release
# ---------------------------------------------------------------------------

def get_available_ram_gb() -> float | None:
    """Get available RAM in GB on macOS, or ``None`` when unknown."""
    try:
        result = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        lines = result.stdout.strip().split('\n')
        page_size_match = re.search(
            r"page size of\s+(\d+)\s+bytes", lines[0], re.IGNORECASE,
        )
        if page_size_match is None:
            return None
        page_size = int(page_size_match.group(1))

        free_pages = 0
        inactive_pages = 0
        for line in lines:
            if 'Pages free' in line:
                free_pages = int(line.split(':')[1].strip().rstrip('.'))
            elif 'Pages inactive' in line:
                inactive_pages = int(line.split(':')[1].strip().rstrip('.'))

        if free_pages <= 0 and inactive_pages <= 0:
            return None
        available_bytes = (free_pages + inactive_pages) * page_size
        return available_bytes / (1024 ** 3)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def get_total_ram_gb() -> float | None:
    """Get total system RAM in GB, or ``None`` when unsupported/failed."""
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        total = int(result.stdout.strip()) / (1024 ** 3)
        return total if total > 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _resident_ram_gb(endpoint: dict | None) -> float | None:
    """Read the current endpoint RAM fields without legacy slot estimates."""
    if not isinstance(endpoint, dict):
        return None
    try:
        resident = float(endpoint.get("ram_resident_gb"))
        overhead = float(endpoint.get("ram_overhead_gb") or 0)
    except (TypeError, ValueError):
        return None
    total = resident + overhead
    return total if total > 0 else None


def _selected_model_identity(endpoint: dict | None) -> str:
    if not isinstance(endpoint, dict):
        return ""
    return str(
        endpoint.get("model_id")
        or endpoint.get("model")
        or endpoint.get("model_path")
        or endpoint.get("id")
        or endpoint.get("name")
        or ""
    )


def should_release_kv_cache(
    config: dict,
    depth_endpoint: dict | None = None,
    breadth_endpoint: dict | None = None,
) -> bool:
    """
    Determine if KV cache should be released between sequential Gear 4 model calls.

    Returns True when hardware cannot hold two large models simultaneously in RAM.
    On the M4 Max with 128GB, this is unlikely unless running very large models.
    """
    # The old caller supplied only ``config`` before the router had selected
    # the real endpoints.  That path is intentionally a no-op now: profile
    # declarations are not execution facts.
    if not isinstance(depth_endpoint, dict) or not isinstance(breadth_endpoint, dict):
        return False
    if depth_endpoint.get("type") != "local" or breadth_endpoint.get("type") != "local":
        return False
    depth_model = _selected_model_identity(depth_endpoint)
    breadth_model = _selected_model_identity(breadth_endpoint)
    if not depth_model or not breadth_model or depth_model == breadth_model:
        return False
    depth_ram = _resident_ram_gb(depth_endpoint)
    breadth_ram = _resident_ram_gb(breadth_endpoint)
    available = get_available_ram_gb()

    # Unknown probe/model facts never become a fabricated capacity decision.
    # The scheduler remains conservative via ``can_parallel=False`` below;
    # destructive cache action requires a known threshold crossing.
    if depth_ram is None or breadth_ram is None or available is None:
        return False
    return (depth_ram + breadth_ram) > available * 0.8


def release_kv_cache(endpoint: dict, *, mlx_evictor=None) -> bool:
    """
    Release KV cache for a model via Ollama API.
    This allows the next model to use the freed memory.
    """
    if not isinstance(endpoint, dict) or endpoint.get("type") != "local":
        return False
    engine = str(endpoint.get("engine") or "ollama").lower()
    if engine == "auto":
        import platform
        engine = (
            "mlx"
            if platform.system() == "Darwin" and platform.machine() == "arm64"
            else "ollama"
        )
    if engine == "mlx":
        model_path = endpoint.get("model_path") or endpoint.get("model")
        if not model_path or mlx_evictor is None:
            return False
        try:
            return bool(mlx_evictor(model_path))
        except Exception:
            return False
    if engine != "ollama":
        return False
    model_name = endpoint.get("model") or endpoint.get("model_id")
    if not model_name:
        return False
    try:
        import requests
        response = requests.post(
            str(endpoint.get("url") or "http://localhost:11434").rstrip("/")
            + "/api/generate",
            json={"model": model_name, "keep_alive": 0},
            timeout=10,
        )
        return bool(response.ok)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 14.2 — Graceful Gear Degradation
# ---------------------------------------------------------------------------

@dataclass
class DegradationState:
    """Current degradation state for a gear."""
    gear: int
    degradation_level: int = 0  # 0 = ideal, 1-3 = increasingly degraded
    reason: str = ""
    signals: list[int] = field(default_factory=list)  # Budget signal numbers fired
    fallback_gear: int | None = None  # gear to fall back to, if applicable
    context_reduction_pct: int = 0  # percentage of context reduction applied


def check_hardware_constraints(config: dict) -> dict:
    """
    Assess current hardware constraints for gear execution.

    Returns:
        dict with keys: ram_available_gb, ram_total_gb, ram_pressure (bool),
        models_loaded (int), context_window_budget, can_parallel (bool)
    """
    total_ram = get_total_ram_gb()
    available_ram = get_available_ram_gb()
    ram_known = total_ram is not None and available_ram is not None
    ram_pressure = (
        available_ram < (total_ram * 0.3) if ram_known else True
    )

    # Count active models (check Ollama)
    models_loaded = 0
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/ps", timeout=5)
        if resp.ok:
            data = resp.json()
            models_loaded = len(data.get("models", []))
    except Exception:
        pass

    return {
        "ram_available_gb": (
            round(available_ram, 1) if available_ram is not None else None
        ),
        "ram_total_gb": round(total_ram, 1) if total_ram is not None else None,
        "ram_known": ram_known,
        "ram_pressure": ram_pressure,
        "models_loaded": models_loaded,
        "can_parallel": bool(
            ram_known and not ram_pressure and available_ram > 20
        ),
    }


def get_degradation_path(gear: int, config: dict) -> DegradationState:
    """
    Determine the degradation path for a given gear based on current constraints.

    Gear 4 degradation:
      0 — Ideal: true parallel, both models, independent agentic retrieval
      1 — RAM pressure: rapid sequential (same packages, adversarial integrity preserved)
      2 — Window pressure: reduced RAG, compression applied, Signals 1-2
      3 — Severe: automatic fallback to Gear 3

    Gear 3 degradation:
      0 — Ideal: sequential review (Breadth → Depth → Breadth)
      1 — Reduced context per step, compression applied
      2 — Fallback to Gear 2

    Gear 1-2: no degradation path (already minimal)
    """
    constraints = check_hardware_constraints(config)
    state = DegradationState(gear=gear)

    if gear >= 4:
        if not constraints["ram_known"]:
            state.degradation_level = 1
            state.reason = (
                "RAM capacity is unknown because the system probe failed or "
                "is unsupported. Using conservative serialized execution."
            )
            state.signals = [1]
            return state
        if not constraints["can_parallel"]:
            if constraints["ram_pressure"]:
                state.degradation_level = 1
                state.reason = (
                    f"RAM pressure detected ({constraints['ram_available_gb']}GB available). "
                    f"Switching to rapid sequential execution — adversarial integrity preserved."
                )
                state.signals = [1]  # Signal 1: approaching budget limit
            else:
                state.degradation_level = 0
                state.reason = "Ideal: true parallel execution available"
        else:
            state.degradation_level = 0
            state.reason = "Ideal: true parallel execution available"

        # Check if further degradation needed
        if constraints["ram_pressure"] and constraints["ram_available_gb"] < 10:
            state.degradation_level = 2
            state.reason = (
                f"Severe RAM pressure ({constraints['ram_available_gb']}GB available). "
                f"Reduced context window, compression applied."
            )
            state.signals = [1, 2]  # Signals 1-2
            state.context_reduction_pct = 30

        if constraints["ram_available_gb"] < 5:
            state.degradation_level = 3
            state.reason = (
                f"Critical RAM ({constraints['ram_available_gb']}GB available). "
                f"Falling back to Gear 3."
            )
            state.signals = [1, 2, 4]  # Signal 4: severe degradation
            state.fallback_gear = 3

    elif gear == 3:
        if not constraints["ram_known"]:
            state.degradation_level = 1
            state.reason = (
                "RAM capacity is unknown because the system probe failed or "
                "is unsupported. Keeping the sequential pipeline and using "
                "conservative context handling."
            )
            state.signals = [1]
            state.context_reduction_pct = 20
            return state
        if constraints["ram_pressure"]:
            state.degradation_level = 1
            state.reason = "Reduced context per step due to RAM pressure"
            state.signals = [1]
            state.context_reduction_pct = 20

        if constraints["ram_available_gb"] < 8:
            state.degradation_level = 2
            state.reason = "Falling back to Gear 2 due to severe constraints"
            state.signals = [1, 2]
            state.fallback_gear = 2

    return state


def format_degradation_signal(state: DegradationState) -> str:
    """
    Format degradation state as a human-readable signal for the output.
    This signal is included in the pipeline output so the user knows
    what happened.
    """
    if state.degradation_level == 0:
        return ""

    parts = [
        f"[DEGRADATION SIGNAL — Gear {state.gear}, Level {state.degradation_level}]",
        state.reason,
    ]

    if state.fallback_gear:
        parts.append(f"Automatic fallback to Gear {state.fallback_gear}")

    if state.context_reduction_pct > 0:
        parts.append(f"Context reduced by {state.context_reduction_pct}%")

    if state.signals:
        parts.append(f"Budget signals fired: {', '.join(str(s) for s in state.signals)}")

    return "\n".join(parts)



if __name__ == "__main__":
    print("Orchestrator Resilience and Degradation (Phase 14)")
    print()

    # Show current hardware state
    total = get_total_ram_gb()
    available = get_available_ram_gb()
    if total is None or available is None:
        print("Hardware: RAM capacity unknown (probe failed or unsupported)")
        print("RAM pressure: UNKNOWN — conservative scheduling applies")
    else:
        print(f"Hardware: {total:.0f}GB total RAM, {available:.1f}GB available")
        print(f"RAM pressure: {'YES' if available < total * 0.3 else 'no'}")
    print()

    print("Gear 4 degradation levels:")
    print("  0 — Ideal: true parallel execution")
    print("  1 — RAM pressure: rapid sequential (adversarial integrity preserved)")
    print("  2 — Window pressure: reduced RAG + compression (Signals 1-2)")
    print("  3 — Severe: automatic fallback to Gear 3 (Signal 4)")
    print()
    print("Gear 3 degradation levels:")
    print("  0 — Ideal: sequential review")
    print("  1 — Reduced context per step")
    print("  2 — Fallback to Gear 2")
