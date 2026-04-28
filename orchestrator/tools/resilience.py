"""
resilience.py — Orchestrator Resilience and Degradation (Phase 14)

Three components:
  14.1 — KV cache release between sequential model calls (Gear 4 on constrained hardware)
  14.2 — Graceful gear degradation logic with signaling
  14.3 — API fallback configuration for Playwright access

Degradation is always signaled, never silent. Uses Budget Signals 1-4.

Usage:
    from orchestrator.tools.resilience import (
        check_hardware_constraints, get_degradation_path,
        should_release_kv_cache, get_fallback_endpoint
    )
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 14.1 — KV Cache Release
# ---------------------------------------------------------------------------

def get_available_ram_gb() -> float:
    """Get available RAM in GB on macOS."""
    try:
        # macOS: use vm_stat to estimate available memory
        result = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split('\n')
        page_size = 16384  # Apple Silicon default

        free_pages = 0
        inactive_pages = 0
        for line in lines:
            if 'Pages free' in line:
                free_pages = int(line.split(':')[1].strip().rstrip('.'))
            elif 'Pages inactive' in line:
                inactive_pages = int(line.split(':')[1].strip().rstrip('.'))

        available_bytes = (free_pages + inactive_pages) * page_size
        return available_bytes / (1024 ** 3)
    except Exception:
        return 128.0  # Conservative default for M4 Max


def get_total_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip()) / (1024 ** 3)
    except Exception:
        return 128.0


def should_release_kv_cache(config: dict) -> bool:
    """
    Determine if KV cache should be released between sequential Gear 4 model calls.

    Returns True when hardware cannot hold two large models simultaneously in RAM.
    On the M4 Max with 128GB, this is unlikely unless running very large models.
    """
    total_ram = get_total_ram_gb()

    # Check if two models are assigned to Gear 4 slots
    slot_assignments = config.get("slot_assignments", {})
    depth_model = slot_assignments.get("depth", "")
    breadth_model = slot_assignments.get("breadth", "")

    if depth_model == breadth_model:
        return False  # Same model, no need to release

    # Estimate combined RAM requirement from endpoint configs
    endpoints = config.get("endpoints", [])
    depth_ram = 0
    breadth_ram = 0

    for ep in endpoints:
        name = ep.get("name", "")
        ram = ep.get("ram_required_gb", 0)
        if name == depth_model:
            depth_ram = ram
        if name == breadth_model:
            breadth_ram = ram

    combined = depth_ram + breadth_ram
    available = get_available_ram_gb()

    # Release KV cache if combined requirement exceeds 80% of available RAM
    if combined > 0 and combined > available * 0.8:
        return True

    # Also release if total RAM is under 32GB (low-end hardware)
    if total_ram < 32:
        return True

    return False


def release_kv_cache(model_name: str):
    """
    Release KV cache for a model via Ollama API.
    This allows the next model to use the freed memory.
    """
    try:
        import requests
        # Ollama: unload model to free memory
        requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "keep_alive": 0},
            timeout=10,
        )
    except Exception:
        pass  # Best-effort cache release


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
    ram_pressure = available_ram < (total_ram * 0.3)  # <30% available = pressure

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
        "ram_available_gb": round(available_ram, 1),
        "ram_total_gb": round(total_ram, 1),
        "ram_pressure": ram_pressure,
        "models_loaded": models_loaded,
        "can_parallel": not ram_pressure and available_ram > 20,
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


# ---------------------------------------------------------------------------
# 14.3 — API Fallback Configuration
# ---------------------------------------------------------------------------

def get_fallback_endpoint(config: dict, primary_endpoint: dict) -> dict | None:
    """
    Get a fallback endpoint for a given primary endpoint.

    If the primary is a browser (Playwright) endpoint, find an API endpoint
    for the same service. If the primary is an API endpoint, find a browser
    endpoint (less common, but supported).

    Returns None if no fallback is available.
    """
    primary_type = primary_endpoint.get("type", "")
    primary_service = primary_endpoint.get("service", "")

    # Determine what type of fallback to look for
    if primary_type == "browser":
        fallback_type = "api"
    elif primary_type == "api":
        fallback_type = "browser"
    else:
        return None  # Local endpoints don't need fallback

    endpoints = config.get("endpoints", [])
    for ep in endpoints:
        if (ep.get("type") == fallback_type and
            ep.get("service") == primary_service and
            ep.get("status") == "active" and
            ep.get("name") != primary_endpoint.get("name")):
            return ep

    return None


def try_with_fallback(messages: list, primary_endpoint: dict, config: dict,
                      call_fn, images: list = None) -> tuple[str, dict]:
    """
    Try calling the primary endpoint; if it fails, fall back to the
    alternate access method for the same service.

    Returns:
        (response_text, endpoint_used)
    """
    try:
        response = call_fn(messages, primary_endpoint, images=images)
        if response and not response.startswith("[Error]"):
            return response, primary_endpoint
    except Exception:
        pass

    # Primary failed — try fallback
    fallback = get_fallback_endpoint(config, primary_endpoint)
    if fallback:
        try:
            response = call_fn(messages, fallback, images=images)
            if response and not response.startswith("[Error]"):
                # Log the fallback
                _log_fallback(primary_endpoint, fallback)
                return response, fallback
        except Exception:
            pass

    return "[Error] Both primary and fallback endpoints failed", primary_endpoint


def _log_fallback(primary: dict, fallback: dict):
    """Log a fallback event."""
    log_dir = os.path.expanduser("~/ora/logs/")
    os.makedirs(log_dir, exist_ok=True)

    from datetime import datetime
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "endpoint_fallback",
        "primary": primary.get("name", ""),
        "primary_type": primary.get("type", ""),
        "fallback": fallback.get("name", ""),
        "fallback_type": fallback.get("type", ""),
        "service": primary.get("service", ""),
    }

    import json
    log_file = os.path.join(log_dir, f"fallback-{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    print("Orchestrator Resilience and Degradation (Phase 14)")
    print()

    # Show current hardware state
    total = get_total_ram_gb()
    available = get_available_ram_gb()
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
