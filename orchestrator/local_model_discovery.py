#!/usr/bin/env python3
"""Automatic discovery of MLX models in ~/ora/models/.

Replaces hand-curated entries in ``config/models.json``'s ``local_models``
array. Scans each subdirectory for a valid MLX ``config.json``, derives:

- id, display_name, path
- ram_gb (sum of *.safetensors sizes)
- type (``dense`` or ``moe``)
- architecture_note
- recommended_roles (by parameter-count rule table)
- parameters_b (estimated total parameters, including multimodal components)
- context_window (extracted from the model config when declared)
- active_params_per_token (total for dense; estimated for MoE)
- vision_capable

Integration: call ``refresh(write=True)`` to rewrite the ``local_models``
section in ``config/models.json``. The function preserves the
``commercial_models`` array and all top-level keys.

CLI: ``scripts/local_models.py rescan`` runs discovery and prints a
diff vs the current ``models.json`` state.

The motivating gap (2026-05-26): when local models are added or removed
from the directory, no part of the system noticed until a human edited
``models.json``. The V3 Models pane would still display deleted models
and miss new ones. This module closes that loop.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    from . import runtime_paths as _rp
except ImportError:  # direct script-style import from sys.path
    import runtime_paths as _rp  # type: ignore

# Defaults come from the path layer, so an ORA_HOME (or a worktree) is honored
# instead of always scanning and rewriting the ~/ora checkout.
DEFAULT_MODELS_DIR = _rp.local_models_dir()
DEFAULT_MODELS_JSON = _rp.models_json_path()
DEFAULT_ROUTING_CONFIG = _rp.routing_config_path()
TRASH_BIN = "/usr/bin/trash"


class LocalModelDiscoveryError(RuntimeError):
    """The installed-model directory could not be read authoritatively."""


class LocalModelDeleteError(ValueError):
    """A requested deletion target is not a currently discovered model."""

# Pipeline-role rule table by total parameter count (billions).
# Ranges align with the Ora slot taxonomy:
# - <5B = utility scale (classification, prompt cleanup)
# - 5–15B = small-fast (utility + sidebar)
# - 15–40B = mid-fast (sidebar, step1, rag)
# - 40B+ = large analyst (breadth, depth, evaluator, consolidator)
ROLE_RULES = [
    (5, ["classification"]),
    (15, ["classification", "step1_cleanup", "rag_planner", "sidebar"]),
    (40, ["sidebar", "step1_cleanup", "rag_planner"]),
    (float("inf"), ["breadth", "depth", "evaluator", "consolidator"]),
]

# ----------------------------------------------------------------------
# Per-config field extraction
# ----------------------------------------------------------------------


def _text_config(config: dict) -> dict:
    """Return the text-config block, falling back to the top level."""
    return config.get("text_config", config)


def _is_vision_capable(config: dict) -> bool:
    """Vision-capable when ANY of these signals is present.

    Multimodal MLX models follow one of three naming conventions:
    1. ``vision_config`` sub-config block
    2. ``image_token_id`` or ``image_token_index`` field
    3. ``architectures`` ending with ``ConditionalGeneration``

    Plain text-only models use ``ForCausalLM`` architectures and have
    no image token defined.
    """
    if "vision_config" in config:
        return True
    if "image_token_id" in config or "image_token_index" in config:
        return True
    text = _text_config(config)
    if "image_token_id" in text or "image_token_index" in text:
        return True
    for arch in config.get("architectures", []):
        if arch.endswith("ConditionalGeneration"):
            return True
    return False


def _is_moe(config: dict) -> bool:
    """MoE when num_experts / n_routed_experts / moe_intermediate_size
    is present in text_config, OR architecture/model_type contains 'moe'."""
    text = _text_config(config)
    for k in ("num_experts", "n_routed_experts", "moe_intermediate_size"):
        if k in text:
            return True
    if "moe" in config.get("model_type", "").lower():
        return True
    for arch in config.get("architectures", []):
        if "Moe" in arch:
            return True
    return False


def _quant_bits(config: dict) -> int:
    """Return the quantization bits (default 4 if unset)."""
    q = config.get("quantization") or config.get("quantization_config") or {}
    return int(q.get("bits", 4))


def _safetensors_bytes(model_dir: Path) -> int:
    """Sum the size of all *.safetensors files in the directory."""
    return sum(f.stat().st_size for f in model_dir.glob("*.safetensors"))


def _estimate_total_params_b(model_dir: Path, config: dict) -> float:
    """Estimate total parameter count in billions, from safetensors size.

    At 4-bit quantization, each param occupies ~0.5 bytes.
    So params ≈ safetensors_bytes × (8 / bits) / 1e9.

    More accurate than parsing the config layer-by-layer because:
    - it works for any architecture without per-arch math
    - it includes embeddings, vision tower, projection layers
    - quantization overhead is automatically reflected in file size
    """
    bytes_total = _safetensors_bytes(model_dir)
    if bytes_total == 0:
        return 0.0
    bits = _quant_bits(config)
    return bytes_total * 8.0 / bits / 1e9


def _extract_context_window(config: dict) -> int | None:
    """Extract a positive declared text context window without guessing."""
    keys = (
        "max_position_embeddings", "max_sequence_length", "max_seq_len",
        "seq_length", "sequence_length", "n_positions", "context_length",
        "model_max_length",
    )
    text = _text_config(config)
    for source in (text, config):
        for key in keys:
            value = source.get(key)
            try:
                context = int(value)
            except (TypeError, ValueError):
                continue
            if context > 0:
                return context
    return None


def _extract_active_params_b(dir_name: str, total_b: float, config: dict) -> float:
    """For MoE models, return active params per token.

    First tries the directory-name convention ``-A<N>B`` (e.g.,
    ``qwen3.5-122b-a10b-mxfp4`` → 10). Falls back to a config-based
    estimate using num_experts_per_tok / total_experts.

    For dense models, returns total_b unchanged.
    """
    if not _is_moe(config):
        return total_b

    # Convention: directory name contains "-aNB" or "aNb" where N is
    # active params in billions.
    m = re.search(r"-a(\d+)b\b", dir_name.lower())
    if m:
        return float(m.group(1))
    m = re.search(r"\ba(\d+)b\b", dir_name.lower())
    if m:
        return float(m.group(1))

    # Config-based fallback. For sparse MoE (8 of 128 experts active
    # etc.) FFN-routing ratio is the dominant factor; attention overhead
    # is small in comparison. Use the routing ratio directly as a
    # first-order estimate. (The prior 0.3 attention floor overestimated
    # active params on very-sparse MoE like GLM-4V's 8-of-128.)
    text = _text_config(config)
    n_per_tok = text.get("num_experts_per_tok") or text.get("num_experts_per_token")
    n_total = text.get("num_experts") or text.get("n_routed_experts")
    if n_per_tok and n_total:
        ffn_ratio = float(n_per_tok) / float(n_total)
        return round(total_b * ffn_ratio, 1)

    # If we can't determine it, return total — caller should treat
    # this as an upper bound.
    return total_b


def _recommended_roles(total_b: float) -> list[str]:
    """Map total param count to slot roles via the rule table."""
    for threshold, roles in ROLE_RULES:
        if total_b < threshold:
            return roles
    # Unreachable (last rule has inf threshold).
    return ROLE_RULES[-1][1]


def _slug(dir_name: str) -> str:
    """Build a stable id slug from the directory name."""
    return dir_name.lower().replace("_", "-")


def _make_display_name(dir_name: str, total_b: float, is_moe: bool,
                       vision: bool, bits: int) -> str:
    """Construct a human-readable display name.

    Strips quantization/format suffixes from the directory name to
    avoid duplication with the trailing bits_tag. Preserves common
    acronyms (MLX, MoE, GLM).
    """
    # Strip trailing quantization-format suffixes before titlecasing.
    # These become the bits_tag at the end of the name.
    suffixes_to_strip = ("-4bit", "_4bit", "-8bit", "_8bit", "-mxfp4",
                          "_mxfp4", "-mlx", "_mlx")
    base = dir_name
    for suffix in suffixes_to_strip:
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
    pretty = base.replace("-", " ").replace("_", " ").title()
    # Preserve common acronyms that titlecase breaks.
    for original, replacement in [
        ("Mlx", "MLX"),
        ("Moe", "MoE"),
        ("Glm", "GLM"),
        ("Mxfp4", "mxfp4"),
        ("Vl", "VL"),
        # "Opus" stays as "Opus"
    ]:
        pretty = pretty.replace(original, replacement)
    bits_tag = f"({bits}-bit)" if bits != 4 else "(4-bit)"
    arch_tag = "MoE" if is_moe else ""
    vis_tag = "Vision" if vision else ""
    parts = [pretty]
    for tag in (arch_tag, vis_tag, bits_tag):
        if tag and tag.lower() not in pretty.lower():
            parts.append(tag)
    return " ".join(p for p in parts if p)


def _make_arch_note(dir_name: str, total_b: float, active_b: float,
                    is_moe: bool, vision: bool, config: dict) -> str:
    """One-line architecture description."""
    arch_label = "MoE" if is_moe else "Dense"
    vis_label = " vision-capable" if vision else " text-only"
    base = f"{arch_label} ~{total_b:.0f}B{vis_label}"
    if is_moe and active_b < total_b:
        base += f", ~{active_b:.0f}B active per token"
    # Append the source model_name if present (some HF configs carry it).
    src = config.get("model_name") or config.get("_name_or_path")
    if src and not src.startswith("/"):
        base += f" — base: {src}"
    return base


# ----------------------------------------------------------------------
# Per-directory probe and full-directory scan
# ----------------------------------------------------------------------


def probe_model_dir(model_dir: Path) -> Optional[dict]:
    """Probe one MLX model directory; return a models.json entry, or None.

    Returns None when:
    - the directory doesn't contain config.json
    - the directory contains no .safetensors files
    - config.json is malformed

    The returned dict matches the historic local_models entry shape so
    callers can drop it directly into models.json.
    """
    config_path = model_dir / "config.json"
    if not config_path.is_file():
        return None

    try:
        with open(config_path) as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    safetensors_count = sum(1 for _ in model_dir.glob("*.safetensors"))
    if safetensors_count == 0:
        return None

    total_b = _estimate_total_params_b(model_dir, config)
    if total_b == 0:
        return None

    bits = _quant_bits(config)
    is_moe = _is_moe(config)
    vision = _is_vision_capable(config)
    active_b = _extract_active_params_b(model_dir.name, total_b, config)
    ram_gb = round(_safetensors_bytes(model_dir) / (1024 ** 3))

    return {
        "id": f"local-mlx-{_slug(model_dir.name)}",
        "display_name": _make_display_name(model_dir.name, total_b, is_moe, vision, bits),
        "path": str(model_dir.resolve()),
        "ram_gb": ram_gb,
        "type": "moe" if is_moe else "dense",
        "architecture_note": _make_arch_note(model_dir.name, total_b, active_b,
                                              is_moe, vision, config),
        "recommended_roles": _recommended_roles(total_b),
        "parameters_b": round(total_b, 1),
        "context_window": _extract_context_window(config),
        "active_params_per_token": int(round(active_b)),
        "vision_capable": vision,
    }


def scan_models_dir(models_dir: Path = DEFAULT_MODELS_DIR) -> list[dict]:
    """Walk a models directory and return one entry per valid MLX model.

    Subdirectories that aren't MLX models (no config.json, no
    safetensors, malformed JSON) are silently skipped. Non-LLM
    subdirectories like ``diffusers``, ``whisper``, ``loras`` are
    rejected by these checks automatically.

    Returns a list sorted by parameter count (smallest first), which
    matches the conventional models.json ordering.
    """
    models_dir = Path(models_dir).expanduser()
    try:
        if not models_dir.exists():
            raise LocalModelDiscoveryError(
                f"local models directory is missing: {models_dir}"
            )
        if not models_dir.is_dir():
            raise LocalModelDiscoveryError(
                f"local models path is not a directory: {models_dir}"
            )
        if not os.access(models_dir, os.R_OK | os.X_OK):
            raise LocalModelDiscoveryError(
                f"local models directory is unreadable: {models_dir}"
            )
        subdirs = sorted(models_dir.iterdir())
    except LocalModelDiscoveryError:
        raise
    except OSError as exc:
        raise LocalModelDiscoveryError(
            f"local models directory is unreadable: {models_dir}: {exc}"
        ) from exc

    entries = []
    for subdir in subdirs:
        # A symlink is not a physical direct child of the managed model
        # directory.  Ignoring it here also prevents one physical model from
        # appearing twice through a second symlinked name.
        if subdir.is_symlink() or not subdir.is_dir():
            continue
        entry = probe_model_dir(subdir)
        if entry is not None:
            entries.append(entry)

    # Sort by ram_gb (proxy for parameter count) so small models come first.
    entries.sort(key=lambda e: e.get("ram_gb", 0))
    return entries


def _canonical_path(value: str | Path) -> str:
    return str(Path(value).expanduser().resolve(strict=False))


def _load_static_local_endpoints(routing_config: Path | None) -> list[dict]:
    """Load configured local endpoints used to retain stable identities."""
    if routing_config is None:
        return []
    path = Path(routing_config).expanduser()
    if not path.exists():
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalModelDiscoveryError(
            f"could not read configured local endpoints from {path}: {exc}"
        ) from exc
    return [
        endpoint for endpoint in (data.get("endpoints") or [])
        if isinstance(endpoint, dict)
        and endpoint.get("type") == "local"
        and endpoint.get("id")
        and (endpoint.get("model_path") or endpoint.get("path"))
    ]


def reconcile_static_local_endpoints(
    discovered: list[dict],
    static_endpoints: list[dict],
) -> list[dict]:
    """Return one discovered row per path, retaining matching static identity.

    Physical paths are authoritative.  A configured endpoint contributes its
    stable id and curated metadata only when its canonical model path matches a
    directory found by the current scan.  Configured endpoints whose paths are
    absent therefore cannot create stale inventory rows.
    """
    endpoint_by_path: dict[str, dict] = {}
    for endpoint in static_endpoints:
        raw_path = endpoint.get("model_path") or endpoint.get("path")
        if not raw_path:
            continue
        endpoint_by_path.setdefault(_canonical_path(raw_path), endpoint)

    reconciled = []
    seen_paths: set[str] = set()
    for model in discovered:
        raw_path = model.get("path") or model.get("model_path")
        if not raw_path:
            continue
        canonical = _canonical_path(raw_path)
        if canonical in seen_paths:
            continue
        seen_paths.add(canonical)

        row = dict(model)
        row["path"] = canonical
        endpoint = endpoint_by_path.get(canonical)
        if endpoint:
            row["id"] = endpoint["id"]
            for key in (
                "display_name", "provider", "training_family", "tier",
                "context_window", "capabilities", "enabled", "status",
                "vision_capable", "machine", "engine", "ram_overhead_gb",
            ):
                if endpoint.get(key) is not None:
                    row[key] = endpoint[key]
        reconciled.append(row)
    return reconciled


def resolve_delete_target(
    model_id: str,
    discovered: list[dict],
    models_dir: Path = DEFAULT_MODELS_DIR,
) -> Path:
    """Resolve an id to a safe, current physical model directory.

    The returned directory must exist, must not be a symlink, and must be a
    canonical direct child of the managed models root.  Callers must pass the
    result of a fresh successful scan; an arbitrary path is never accepted.
    """
    if not isinstance(model_id, str) or not model_id.strip():
        raise LocalModelDeleteError("model_id is required")
    matches = [
        model for model in discovered
        if isinstance(model, dict) and model.get("id") == model_id.strip()
    ]
    if len(matches) != 1:
        raise LocalModelDeleteError(
            "model is not a currently discovered local model"
        )

    raw_target = matches[0].get("path") or matches[0].get("model_path")
    if not raw_target:
        raise LocalModelDeleteError("discovered model has no physical path")
    try:
        root = Path(models_dir).expanduser().resolve(strict=True)
        candidate = Path(raw_target).expanduser()
        if candidate.is_symlink():
            raise LocalModelDeleteError("symlink model directories cannot be deleted")
        target = candidate.resolve(strict=True)
    except LocalModelDeleteError:
        raise
    except (OSError, RuntimeError) as exc:
        raise LocalModelDeleteError(
            f"model directory is no longer current: {exc}"
        ) from exc

    if not root.is_dir():
        raise LocalModelDeleteError("local models root is not a directory")
    if target.parent != root:
        raise LocalModelDeleteError(
            "model directory is not a canonical direct child of the local models root"
        )
    if not target.is_dir():
        raise LocalModelDeleteError("model target is not a directory")
    return target


def move_model_to_trash(target: Path) -> subprocess.CompletedProcess:
    """Move one already-validated model directory to macOS Trash."""
    return subprocess.run(
        [TRASH_BIN, str(target)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


# ----------------------------------------------------------------------
# Public refresh API: rewrite the local_models section of models.json
# ----------------------------------------------------------------------


def refresh(
    models_json: Path = DEFAULT_MODELS_JSON,
    models_dir: Path = DEFAULT_MODELS_DIR,
    routing_config: Path | None = DEFAULT_ROUTING_CONFIG,
    write: bool = False,
    allow_shrink: bool = False,
) -> dict:
    """Run discovery and optionally rewrite the local_models section.

    Returns a dict::

        {
            "discovered": [list of new entries],
            "previous": [list of old entries],
            "added": [ids present in discovered, not previous],
            "removed": [ids present in previous, not discovered],
            "wrote": bool,
            "refused": str | None,   # why a requested write did not happen
        }

    When ``write=True``:
    - rewrites ``models_json`` with the new ``local_models`` array
    - preserves the ``commercial_models`` array and ALL top-level keys
    - a missing or unreadable directory raises LocalModelDiscoveryError before
      any write, preserving the last-known-good inventory
    - **a scan that finds FEWER models than the file already records refuses
      the write** unless ``allow_shrink=True``, and says so loudly

    That last rule exists because the missing-directory guard above only
    covers a directory that cannot be read at all. A directory that reads
    successfully but is not the real model store — a fresh git worktree whose
    ``models/`` holds one unrelated entry, a half-mounted volume, a partially
    synced machine — passes every existing check and silently replaces a good
    inventory with a truncated one. Because ``models.json`` is machine-local
    and gitignored there is no diff and no alarm; the damage surfaces much
    later as unrelated routing failures ("required model input exceeds
    endpoint-safe context capacity"), which is a very long way from the cause.

    Growing or holding steady is always safe to write. Only shrinking needs a
    human, because only shrinking can destroy a working configuration.
    Deliberately removing a model is exactly the case ``allow_shrink`` (and
    the CLI's ``--allow-shrink``) exists for.
    """
    discovered = reconcile_static_local_endpoints(
        scan_models_dir(models_dir),
        _load_static_local_endpoints(routing_config),
    )

    previous = []
    full_doc = {}
    if models_json.is_file():
        try:
            with open(models_json) as f:
                full_doc = json.load(f)
            previous = full_doc.get("local_models", [])
        except (OSError, json.JSONDecodeError):
            full_doc = {}
            previous = []

    prev_ids = {e.get("id") for e in previous}
    new_ids = {e.get("id") for e in discovered}

    result = {
        "discovered": discovered,
        "previous": previous,
        "added": sorted(new_ids - prev_ids),
        "removed": sorted(prev_ids - new_ids),
        "wrote": False,
        "refused": None,
    }

    if not write:
        return result

    if len(discovered) < len(previous) and not allow_shrink:
        result["refused"] = (
            f"discovery found {len(discovered)} local model(s) where "
            f"{os.fspath(models_json)} already records {len(previous)}; "
            f"keeping the recorded inventory. Scanned {os.fspath(models_dir)}. "
            f"Missing: {', '.join(result['removed']) or '(unnamed)'}. "
            "If the removal is intentional, re-run with allow_shrink=True "
            "(CLI: --write --allow-shrink)."
        )
        print(f"[local_model_discovery] REFUSED WRITE: {result['refused']}",
              file=sys.stderr, flush=True)
        return result

    full_doc["local_models"] = discovered
    # Track when discovery last ran so the V3 pane can show staleness.
    full_doc["_local_models_discovered_at"] = (
        Path(models_dir).stat().st_mtime
    )

    with open(models_json, "w") as f:
        json.dump(full_doc, f, indent=2)
        f.write("\n")

    result["wrote"] = True
    return result


# ----------------------------------------------------------------------
# CLI entry point
# ----------------------------------------------------------------------


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Discover MLX models in ~/ora/models/ and "
                    "update config/models.json."
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Rewrite the local_models section of models.json. "
             "Default is dry-run: print discovered entries only.",
    )
    parser.add_argument(
        "--models-dir", default=str(DEFAULT_MODELS_DIR),
        help="Directory to scan (default: ~/ora/models/)",
    )
    parser.add_argument(
        "--models-json", default=str(DEFAULT_MODELS_JSON),
        help="Path to models.json (default: ~/ora/config/models.json)",
    )
    parser.add_argument(
        "--allow-shrink", action="store_true",
        help="Permit a write that records FEWER models than models.json "
             "already holds. Without this, such a write is refused so a "
             "partial or wrong models directory cannot silently truncate a "
             "working inventory. Use it when the removal is deliberate.",
    )
    args = parser.parse_args()

    result = refresh(
        models_json=Path(args.models_json),
        models_dir=Path(args.models_dir),
        write=args.write,
        allow_shrink=args.allow_shrink,
    )

    print(f"Discovered: {len(result['discovered'])} model(s)")
    for e in result["discovered"]:
        roles = ",".join(e["recommended_roles"])
        print(f"  - {e['id']}  ({e['ram_gb']}GB, {e['type']}, "
              f"vision={e['vision_capable']}, roles={roles})")

    if result["added"]:
        print(f"Added: {', '.join(result['added'])}")
    if result["removed"]:
        print(f"Removed: {', '.join(result['removed'])}")
    if args.write:
        print(f"Wrote: {result['wrote']}")
        if result.get("refused"):
            print(f"REFUSED: {result['refused']}")
            return 1
    else:
        print("(dry-run; pass --write to update models.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
