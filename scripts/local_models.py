#!/usr/bin/env python3
"""Local-model selection and download (install Chunk 8).

Preserves the load-bearing logic from the retired natural-language layer set
(installer/phase2/layer2-model-selection.md, deleted; see git history):
  - RAM-tier scheme with AVAILABLE = total_RAM × 0.75
  - Dense-preference rule (MoE rejected at Tier 3+ for reasoning slots)
  - RAM estimation by parameter count × quantization-bits/8 + 2GB overhead
  - 4-bit primary; 8-bit for Tier 4 when RAM headroom permits

Extends with:
  - 3-bit support (Chunk 8 plan addition) so Full Local fits in 64GB at Tier 4
  - Hardware tier classification (≤32GB / 32-64GB / 64GB+ / 128GB+)
  - Recommended-models lookup per tier (curated; user may override)
  - Wrapper around huggingface_hub.snapshot_download for the actual fetch

This module is usable standalone (CLI: ``scripts/local_models.py``) and
also gets invoked by ``scripts/install.py models`` as a reusable
subcommand so users can swap / add / remove local models any time after
the initial install.

Hardware tier mapping (per the 2026-05-18 design conversation):

  ≤32GB RAM   → small_only       — local utility only; workhorses go cloud
  32-64GB     → workhorse_choice — single 70B OR (medium + small) options
  64GB+       → full_local       — Full Local pipeline available
                                    (3-bit option for tight fits)
  128GB+      → adversarial      — Full Local + Adversarial Diversity on

The promotional framing the design conversation landed on: "permanently
free local AI at 64GB; OpenRouter is the upgrade path, not the floor."
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"
LOCAL_MODELS_STATE = REPO_ROOT / "config" / "local-models.json"

# RAM-tier scheme — preserved from the retired layer set (git history holds
# installer/phase2/layer2-model-selection.md).
# AVAILABLE_MODEL_RAM = total_RAM × 0.75 (25% OS overhead).
USABLE_RAM_FRACTION = 0.75


@dataclass
class ModelRecommendation:
    """A recommended local model for a given hardware tier."""
    id: str                       # HuggingFace repo id, e.g. "Qwen/Qwen2.5-7B-Instruct"
    display_name: str
    parameters_b: float
    quantization: str             # "4-bit" / "3-bit" / "8-bit" / "16-bit"
    role: str                     # "utility" / "workhorse_a" / "workhorse_b"
    architecture: str = "dense"   # "dense" / "moe" — dense preferred
    notes: str = ""


@dataclass
class HardwareTier:
    """Classified hardware tier with the deployment options it unlocks."""
    name: str                     # "small_only" / "workhorse_choice" / "full_local" / "adversarial"
    total_ram_gb: float
    available_ram_gb: float
    description: str
    options: list[str] = field(default_factory=list)


# RAM estimation formulas (from layer2-model-selection.md):
#   4-bit: param_count_b × 0.5 GB + 2 GB overhead
#   8-bit: param_count_b × 1.0 GB + 2 GB overhead
#   16-bit: param_count_b × 2.0 GB + 2 GB overhead
# Chunk 8 addition:
#   3-bit: param_count_b × 0.375 GB + 2 GB overhead (extends Tier 4 reach)
QUANT_BYTES_PER_PARAM = {
    "3-bit": 0.375,
    "4-bit": 0.5,
    "8-bit": 1.0,
    "16-bit": 2.0,
}
RAM_OVERHEAD_GB = 2.0


# ─── Hardware detection ──────────────────────────────────────────────────


def get_total_ram_gb() -> float:
    """Detect total system RAM in GB. Uses sysctl on macOS, /proc/meminfo
    on Linux, wmic on Windows."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            return int(out.stdout.strip()) / (1024 ** 3)
        except (subprocess.SubprocessError, ValueError):
            return 0.0
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024 ** 2)
        except (OSError, ValueError):
            return 0.0
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            # second line carries the byte count
            lines = [l.strip() for l in out.stdout.split("\n") if l.strip()]
            if len(lines) >= 2:
                return int(lines[1]) / (1024 ** 3)
        except (subprocess.SubprocessError, ValueError):
            return 0.0
    return 0.0


def estimate_ram_required_gb(parameters_b: float, quantization: str) -> float:
    """Estimate inference RAM for a model. Param-count × bytes-per-param +
    overhead. Use the same formulas as Layer 2's user-specified-mode
    validation (Step 5)."""
    bpp = QUANT_BYTES_PER_PARAM.get(quantization, 0.5)
    return parameters_b * bpp + RAM_OVERHEAD_GB


def classify_hardware(total_ram_gb: float) -> HardwareTier:
    """Map total RAM to the user-facing deployment tier (per the 2026-05-18
    design conversation, NOT the original installer tiers — those still
    inform validation but the user-facing buckets are coarser)."""
    available = total_ram_gb * USABLE_RAM_FRACTION

    if total_ram_gb < 32:
        return HardwareTier(
            name="small_only",
            total_ram_gb=total_ram_gb,
            available_ram_gb=available,
            description=(
                "Local utility model only. Workhorse calls route to OpenRouter. "
                "Lowest-cost path; suitable for laptops and small desktops."
            ),
            options=["Local utility (7-9B, 4-bit) + cloud workhorses"],
        )

    if total_ram_gb < 64:
        return HardwareTier(
            name="workhorse_choice",
            total_ram_gb=total_ram_gb,
            available_ram_gb=available,
            description=(
                "One large workhorse model fits, OR a medium-plus-small pair. "
                "Cloud workhorses remain an option for the slots you don't fill locally."
            ),
            options=[
                "Local Workhorse (single 70B, 4-bit)",
                "Local Mid+Small (medium for one workhorse, small for utility)",
                "Cloud workhorses with local utility only (defer to ≤32GB tier behaviour)",
            ],
        )

    if total_ram_gb < 128:
        return HardwareTier(
            name="full_local",
            total_ram_gb=total_ram_gb,
            available_ram_gb=available,
            description=(
                "Full Local pipeline available. Single workhorse model handles "
                "depth + breadth (no adversarial diversity, but fresh model "
                "calls don't remember prior turns — diversity gain is marginal). "
                "3-bit quantization available for tight fits at 64GB."
            ),
            options=[
                "Full Local (single workhorse, 4-bit)",
                "Full Local 3-bit (extends model reach with degradation warning)",
                "Hybrid (local utility + cloud workhorses for highest quality)",
            ],
        )

    return HardwareTier(
        name="adversarial",
        total_ram_gb=total_ram_gb,
        available_ram_gb=available,
        description=(
            "Full Local + Adversarial Diversity. Two different large workhorse "
            "models (different families) run in parallel for cross-evaluation. "
            "Default for this tier."
        ),
        options=[
            "Full Local + Adversarial Diversity (two large workhorses, 4-bit)",
            "Full Local single-workhorse (turn off adversarial diversity)",
            "Hybrid (local utility + cloud workhorses)",
        ],
    )


# ─── Recommended models (curated; user may override) ─────────────────────


# Curated recommendations per tier. Open-weights dense models preferred.
# IDs are HuggingFace repo identifiers. MLX-converted variants noted in
# the model id when available.
TIER_RECOMMENDATIONS: dict[str, list[ModelRecommendation]] = {
    "small_only": [
        ModelRecommendation(
            id="mlx-community/Qwen2.5-7B-Instruct-4bit",
            display_name="Qwen 2.5 7B Instruct (4-bit MLX)",
            parameters_b=7,
            quantization="4-bit",
            role="utility",
            notes="Dense; tool-calling-capable; ~5.5GB RAM.",
        ),
    ],
    "workhorse_choice": [
        ModelRecommendation(
            id="mlx-community/Meta-Llama-3.1-70B-Instruct-4bit",
            display_name="Llama 3.1 70B Instruct (4-bit MLX)",
            parameters_b=70,
            quantization="4-bit",
            role="workhorse_a",
            notes="Single workhorse for both depth and breadth; ~37GB RAM.",
        ),
        ModelRecommendation(
            id="mlx-community/Qwen2.5-27B-Instruct-4bit",
            display_name="Qwen 2.5 27B Instruct (4-bit MLX)",
            parameters_b=27,
            quantization="4-bit",
            role="workhorse_a",
            notes="Medium workhorse + small utility option; ~16GB RAM.",
        ),
        ModelRecommendation(
            id="mlx-community/Qwen2.5-7B-Instruct-4bit",
            display_name="Qwen 2.5 7B Instruct (4-bit MLX)",
            parameters_b=7,
            quantization="4-bit",
            role="utility",
            notes="Companion utility for the medium-workhorse path.",
        ),
    ],
    "full_local": [
        ModelRecommendation(
            id="mlx-community/Meta-Llama-3.1-70B-Instruct-4bit",
            display_name="Llama 3.1 70B Instruct (4-bit MLX)",
            parameters_b=70,
            quantization="4-bit",
            role="workhorse_a",
            notes="Workhorse for depth + breadth; ~37GB RAM.",
        ),
        ModelRecommendation(
            id="mlx-community/Qwen2.5-7B-Instruct-4bit",
            display_name="Qwen 2.5 7B Instruct (4-bit MLX)",
            parameters_b=7,
            quantization="4-bit",
            role="utility",
            notes="Utility for cleanup/classification/RAG planner; ~5.5GB RAM.",
        ),
    ],
    "adversarial": [
        ModelRecommendation(
            id="mlx-community/Meta-Llama-3.1-70B-Instruct-4bit",
            display_name="Llama 3.1 70B Instruct (4-bit MLX)",
            parameters_b=70,
            quantization="4-bit",
            role="workhorse_a",
            notes="Depth + consolidation workhorse; Llama family.",
        ),
        ModelRecommendation(
            id="mlx-community/Qwen2.5-72B-Instruct-4bit",
            display_name="Qwen 2.5 72B Instruct (4-bit MLX)",
            parameters_b=72,
            quantization="4-bit",
            role="workhorse_b",
            notes="Breadth + verification workhorse; Qwen family for diversity.",
        ),
        ModelRecommendation(
            id="mlx-community/Qwen2.5-7B-Instruct-4bit",
            display_name="Qwen 2.5 7B Instruct (4-bit MLX)",
            parameters_b=7,
            quantization="4-bit",
            role="utility",
            notes="Utility for cleanup/classification/RAG planner.",
        ),
    ],
}


def recommend_models_for_tier(tier_name: str) -> list[ModelRecommendation]:
    return TIER_RECOMMENDATIONS.get(tier_name, [])


# ─── State persistence ──────────────────────────────────────────────────


def load_local_models_state() -> dict:
    """Load config/local-models.json. Returns an empty shell on missing file."""
    if not LOCAL_MODELS_STATE.exists():
        return {"installed": [], "selected": {}}
    try:
        with open(LOCAL_MODELS_STATE) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"installed": [], "selected": {}}


def save_local_models_state(state: dict) -> None:
    LOCAL_MODELS_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_MODELS_STATE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


# ─── HuggingFace download ────────────────────────────────────────────────


def download_model(
    repo_id: str, target_dir: Path | None = None, dry_run: bool = False,
) -> Path | None:
    """Download a HuggingFace repo into MODELS_DIR. Returns the local path
    (or None on dry-run / failure).

    Uses huggingface_hub.snapshot_download — handles auth, resume, partial
    fetch. The model lands at MODELS_DIR / <repo-name-flat>/.

    Gated models (Llama, Mistral, some Qwen): user must accept the license
    on huggingface.co AND have a token in $HF_TOKEN (or have run
    `huggingface-cli login`). Errors with a guidance message on auth failure.
    """
    target = target_dir or (MODELS_DIR / repo_id.replace("/", "__"))

    if dry_run:
        print(f"  [dry-run] would download {repo_id} → {target}")
        return None

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("  ✗ huggingface_hub not installed. Run: pip install huggingface_hub")
        return None

    target.mkdir(parents=True, exist_ok=True)
    try:
        path = snapshot_download(
            repo_id=repo_id,
            local_dir=str(target),
            local_dir_use_symlinks=False,
        )
        print(f"  ✓ downloaded {repo_id} → {path}")
        return Path(path)
    except Exception as exc:
        msg = str(exc).lower()
        if "401" in msg or "403" in msg or "gated" in msg:
            print(f"  ✗ {repo_id} requires acceptance of the license on huggingface.co")
            print(f"    1. Visit https://huggingface.co/{repo_id} and accept the license")
            print("    2. Set HF_TOKEN in your environment (or run: huggingface-cli login)")
        else:
            print(f"  ✗ download failed: {exc}")
        return None


# ─── CLI ─────────────────────────────────────────────────────────────────


def render_tier_summary(tier: HardwareTier) -> str:
    lines = [
        f"Detected: {tier.total_ram_gb:.0f} GB RAM total ({tier.available_ram_gb:.0f} GB usable for models)",
        f"Tier: {tier.name}",
        f"",
        f"  {tier.description}",
        f"",
        f"Available options:",
    ]
    for opt in tier.options:
        lines.append(f"  - {opt}")
    return "\n".join(lines)


def render_recommendations(tier_name: str) -> str:
    recs = recommend_models_for_tier(tier_name)
    if not recs:
        return "  (No curated recommendations for this tier)"
    lines = ["", "Recommended models for this tier:"]
    for r in recs:
        ram = estimate_ram_required_gb(r.parameters_b, r.quantization)
        lines.append(
            f"  - {r.display_name:50s} "
            f"role={r.role:12s} ~{ram:.1f} GB RAM"
        )
        lines.append(f"      repo: {r.id}")
        if r.notes:
            lines.append(f"      note: {r.notes}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Ora local-model selection and download.")
    parser.add_argument("--dry-run", action="store_true", help="Preview, no download.")
    parser.add_argument("--auto", action="store_true", help="Auto-download all tier recommendations without confirmation.")
    parser.add_argument("--show-only", action="store_true", help="Print tier + recommendations and exit (no download prompt).")
    args = parser.parse_args()

    print("Ora local-model selection (install Chunk 8)")
    print()

    total_ram = get_total_ram_gb()
    if total_ram <= 0:
        print("✗ Could not detect system RAM. Aborting.")
        sys.exit(1)

    tier = classify_hardware(total_ram)
    print(render_tier_summary(tier))
    print(render_recommendations(tier.name))
    print()

    if args.show_only:
        return

    recs = recommend_models_for_tier(tier.name)
    if not recs:
        print("No recommendations to download.")
        return

    # Validate each recommendation fits the RAM budget
    over_budget = []
    for r in recs:
        needed = estimate_ram_required_gb(r.parameters_b, r.quantization)
        if needed > tier.available_ram_gb:
            over_budget.append((r, needed))
    if over_budget:
        print("⚠ The following recommendations exceed available RAM:")
        for r, needed in over_budget:
            print(f"  - {r.display_name} needs ~{needed:.1f} GB; have {tier.available_ram_gb:.1f} GB")
        print("  Consider the 3-bit option for Tier 4 or pick the medium-workhorse path for Tier 3.")
        print()

    if args.dry_run or (not args.auto and sys.stdin.isatty()):
        if not args.auto:
            try:
                response = input("Download these recommendations? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if response not in ("y", "yes"):
                print("Cancelled.")
                return
    elif not args.auto:
        # Non-interactive without --auto: just print and exit
        print("Run with --auto to download non-interactively.")
        return

    state = load_local_models_state()
    for r in recs:
        path = download_model(r.id, dry_run=args.dry_run)
        if path is not None and not args.dry_run:
            entry = {
                "id": r.id,
                "display_name": r.display_name,
                "parameters_b": r.parameters_b,
                "quantization": r.quantization,
                "role": r.role,
                "local_path": str(path),
            }
            state.setdefault("installed", []).append(entry)

    if not args.dry_run and state.get("installed"):
        save_local_models_state(state)
        print()
        print(f"✓ Local models state written to {LOCAL_MODELS_STATE}")


if __name__ == "__main__":
    main()
