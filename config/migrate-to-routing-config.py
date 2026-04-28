#!/usr/bin/env python3
"""
Migrate endpoints.json (v1) to routing-config.json (v2).

Reads the current endpoints.json, models.json, and browser-models.json,
then produces a routing-config.json with:
  - Machine registry (auto-detected from local endpoints)
  - Endpoint registry with tier classifications
  - Buckets auto-populated from provider-database.json
  - Default pipeline configurations for interactive and agent contexts
  - Resource reservation defaults

Usage:
    python3 migrate-to-routing-config.py [--dry-run] [--output PATH]

    --dry-run   Print the result without writing to disk
    --output    Write to a specific path (default: routing-config.json in same directory)
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
ENDPOINTS_PATH = CONFIG_DIR / "endpoints.json"
MODELS_PATH = CONFIG_DIR / "models.json"
BROWSER_MODELS_PATH = CONFIG_DIR / "browser-models.json"
PROVIDER_DB_PATH = CONFIG_DIR / "provider-database.json"
OUTPUT_PATH = CONFIG_DIR / "routing-config.json"

# --- Tier classification helpers ---

# Map from v1 endpoint roles/tiers to v2 bucket tiers
ROLE_TO_TIER = {
    "depth": "local-large",
    "breadth": "local-large",
    "small": "local-small",
    "sidebar": "local-small",
}

# Browser service to default tier (based on typical subscription = flagship model)
BROWSER_SERVICE_DEFAULT_TIER = {
    "claude": "premium",
    "chatgpt": "premium",
    "gemini": "premium",
    "perplexity": "premium",
    "mistral": "premium",
    "grok": "premium",
    "copilot": "mid",
    "deepseek": "free",
    "poe": "free",
    "huggingchat": "free",
    "meta_ai": "free",
    "cohere": "free",
}

# Known training families by provider
PROVIDER_TO_FAMILY = {
    "anthropic": "claude",
    "openai": "gpt",
    "google": "gemini",
    "perplexity": "mixed",
    "mistral": "mistral",
    "microsoft": "gpt",
    "deepseek": "deepseek",
    "xai": "grok",
    "poe": "mixed",
    "huggingface": "llama",
    "meta": "llama",
    "cohere": "cohere",
    "moonshot": "qwen",
    "nousresearch": "llama",
    "qwen": "qwen",
}

# Map browser service names to provider names
SERVICE_TO_PROVIDER = {
    "claude": "anthropic",
    "chatgpt": "openai",
    "gemini": "google",
    "perplexity": "perplexity",
    "mistral": "mistral",
    "copilot": "microsoft",
    "deepseek": "deepseek",
    "grok": "xai",
    "poe": "poe",
    "huggingchat": "huggingface",
    "meta_ai": "meta",
    "cohere": "cohere",
    "openai": "openai",
}

RAM_OVERHEAD_PERCENT = 20


def detect_machine() -> dict:
    """Auto-detect the current machine's specs."""
    raw_hostname = platform.node().split(".")[0] or "localhost"
    # Clean hostname: lowercase, replace spaces/apostrophes, truncate
    clean_host = raw_hostname.lower().replace("'", "").replace(" ", "-")
    # Simplify common patterns
    for prefix in ["s-mac-studio", "s-macbook", "s-mac-mini", "s-imac"]:
        if prefix in clean_host:
            # Extract the machine type
            if "studio" in prefix:
                clean_host = "studio"
            elif "mini" in prefix:
                clean_host = "mini"
            elif "macbook" in prefix:
                clean_host = "macbook"
            elif "imac" in prefix:
                clean_host = "imac"
            break

    # Get total RAM via sysctl on macOS
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5
        )
        ram_bytes = int(result.stdout.strip())
        ram_gb = ram_bytes // (1024 ** 3)
    except Exception:
        ram_gb = 0

    usable_gb = int(ram_gb * (1 - RAM_OVERHEAD_PERCENT / 100))

    machine_id = f"{clean_host}-{ram_gb}"

    return {
        "id": machine_id,
        "display_name": f"{clean_host.title()}-{ram_gb}",
        "hostname": "localhost",
        "ram_gb": ram_gb,
        "usable_gb": usable_gb,
        "role": "primary",
        "connection": "local",
        "status": "connected",
    }


def classify_local_endpoint(ep: dict, model_info: dict | None, machine_id: str) -> dict:
    """Convert a v1 local endpoint to v2 format."""
    ram_gb = ep.get("ram_required_gb", 0)
    params = 0
    provider = "unknown"
    family = "unknown"

    if model_info:
        params = model_info.get("active_params_per_token", 0)
        # Infer provider from architecture note or id
        mid = model_info.get("id", "")
        if "hermes" in mid.lower():
            provider = "nousresearch"
            family = "llama"
        elif "kimi" in mid.lower():
            provider = "moonshot"
            family = "qwen"
        elif "deepseek" in mid.lower():
            provider = "deepseek"
            family = "llama"
        elif "qwen" in mid.lower():
            provider = "qwen"
            family = "qwen"

    # Tier based on parameter count
    tier = "local-large" if params >= 40 else "local-small"

    # Split RAM into resident and overhead (rough: 90% resident, 10% overhead)
    resident = int(ram_gb * 0.9) if ram_gb else 0
    overhead = ram_gb - resident if ram_gb else 0

    return {
        "id": ep["name"],
        "type": "local",
        "engine": ep.get("engine", "mlx"),
        "machine": machine_id,
        "model_path": ep.get("model", ""),
        "display_name": ep.get("model_name", ep["name"]),
        "provider": provider,
        "training_family": family,
        "tier": tier,
        "status": ep.get("status", "active"),
        "enabled": ep.get("status") == "active",
        "ram_resident_gb": resident,
        "ram_overhead_gb": overhead,
        "context_window": ep.get("context_window", 0),
        "parameters_b": params,
        "capabilities": {
            "tool_access": ep.get("tool_access", False),
            "file_system_access": ep.get("file_system_access", False),
            "web_access": ep.get("web_access", False),
            "retrieval_approach": ep.get("retrieval_approach", "pre-assembled"),
        },
    }


def classify_browser_endpoint(ep: dict, browser_models: dict) -> dict:
    """Convert a v1 browser endpoint to v2 format."""
    service = ep.get("service", "")
    provider = SERVICE_TO_PROVIDER.get(service, service)
    family = PROVIDER_TO_FAMILY.get(provider, "unknown")
    tier = BROWSER_SERVICE_DEFAULT_TIER.get(service, "mid")

    # Get selected model from browser-models.json
    selected_model = ""
    display_suffix = ""
    if service in browser_models:
        selected_model = browser_models[service].get("selected", "")
        # Find display name for selected model
        for m in browser_models[service].get("available", []):
            if m["id"] == selected_model:
                display_suffix = m["name"]
                break

    display_name = ep.get("model_name", "")
    if not display_name:
        service_names = {
            "claude": "Claude", "chatgpt": "ChatGPT", "gemini": "Gemini",
            "perplexity": "Perplexity", "mistral": "Mistral", "copilot": "Copilot",
            "deepseek": "DeepSeek", "grok": "Grok", "poe": "Poe",
            "huggingchat": "HuggingChat", "meta_ai": "Meta AI", "cohere": "Cohere",
        }
        base = service_names.get(service, service.title())
        display_name = f"{base} ({display_suffix})" if display_suffix else base

    return {
        "id": ep["name"],
        "type": "browser",
        "service": service,
        "session_path": ep.get("session_path", ""),
        "display_name": display_name,
        "provider": provider,
        "training_family": family,
        "selected_model": selected_model,
        "tier": tier,
        "status": ep.get("status", "active"),
        "enabled": ep.get("status") == "active",
        "capabilities": {
            "tool_access": ep.get("tool_access", False),
            "file_system_access": ep.get("file_system_access", False),
            "web_access": ep.get("web_access", True),
            "retrieval_approach": ep.get("retrieval_approach", "pre-assembled"),
        },
    }


def classify_api_endpoint(ep: dict, commercial_models: list[dict]) -> dict:
    """Convert a v1 API endpoint to v2 format."""
    service = ep.get("service", "")
    provider = SERVICE_TO_PROVIDER.get(service, service)
    family = PROVIDER_TO_FAMILY.get(provider, "unknown")

    # Determine tier from model and status
    model_id = ep.get("model", "")
    tier = "mid"  # default

    # Known free tier APIs
    if "flash" in model_id.lower() and provider == "google":
        tier = "free"
    elif "mini" in model_id.lower():
        tier = "fast"
    elif "haiku" in model_id.lower():
        tier = "fast"
    elif "opus" in model_id.lower() or "5.4" in model_id:
        tier = "premium"

    # Look up display name from commercial_models in models.json
    display_name = ""
    for cm in commercial_models:
        if cm.get("id") == ep["name"]:
            display_name = cm.get("display_name", "")
            break

    if not display_name:
        display_name = ep.get("model_name", model_id)

    return {
        "id": ep["name"],
        "type": "api",
        "service": service,
        "model_id": model_id,
        "display_name": display_name,
        "provider": provider,
        "training_family": family,
        "tier": tier,
        "status": ep.get("status", "active"),
        "enabled": ep.get("status") == "active",
        "notes": ep.get("notes", ""),
        "capabilities": {
            "tool_access": ep.get("tool_access", False),
            "file_system_access": ep.get("file_system_access", False),
            "web_access": ep.get("web_access", False),
            "retrieval_approach": ep.get("retrieval_approach", "pre-assembled"),
        },
    }


def build_buckets(endpoints: list[dict]) -> dict:
    """Build bucket lists from classified endpoints."""
    buckets = {
        "local-large": [],
        "local-small": [],
        "premium": [],
        "mid": [],
        "fast": [],
        "free": [],
    }

    for ep in endpoints:
        if ep["enabled"] and ep["tier"] in buckets:
            buckets[ep["tier"]].append(ep["id"])

    return buckets


def build_default_pipelines() -> dict:
    """Build default pipeline configurations."""
    return {
        "interactive": {
            "utility": {
                "buckets": ["local-small", "fast", "free"],
                "expanded": False,
                "cells": {
                    "step1_cleanup": None,
                    "rag_planner": None,
                },
            },
            "analysis": {
                "expanded": False,
                "gear4": {
                    "depth":   {"buckets": ["local-large", "premium", "mid"]},
                    "breadth": {"buckets": ["local-large", "premium", "mid"]},
                },
                "gear3": {
                    "depth":   None,
                    "breadth": None,
                },
            },
            "post_analysis": {
                "buckets": ["local-large", "premium", "mid"],
                "expanded": False,
                "cells": {
                    "consolidation": None,
                    "verification": None,
                },
            },
        },
        "agent": {
            "utility": {
                "buckets": ["local-small", "free"],
                "expanded": False,
                "cells": {
                    "step1_cleanup": None,
                    "rag_planner": None,
                },
            },
            "analysis": {
                "expanded": False,
                "gear4": {
                    "depth":   {"buckets": ["local-large", "fast", "free"]},
                    "breadth": {"buckets": ["local-large", "fast", "free"]},
                },
                "gear3": {
                    "depth":   None,
                    "breadth": None,
                },
            },
            "post_analysis": {
                "buckets": ["local-large", "fast", "free"],
                "expanded": False,
                "cells": {
                    "consolidation": None,
                    "verification": None,
                },
            },
        },
    }


def migrate() -> dict:
    """Run the full migration."""
    # Load v1 config files
    with open(ENDPOINTS_PATH) as f:
        v1 = json.load(f)

    models_data = {}
    if MODELS_PATH.exists():
        with open(MODELS_PATH) as f:
            models_data = json.load(f)

    browser_models = {}
    if BROWSER_MODELS_PATH.exists():
        with open(BROWSER_MODELS_PATH) as f:
            browser_models = json.load(f)

    # Build model lookup from models.json
    model_lookup = {}
    for m in models_data.get("local_models", []):
        model_lookup[m["id"]] = m

    commercial_models = models_data.get("commercial_models", [])

    # Detect current machine
    machine = detect_machine()

    # Convert endpoints
    v2_endpoints = []
    for ep in v1.get("endpoints", []):
        ep_type = ep.get("type", "")

        if ep_type == "local":
            model_info = model_lookup.get(ep["name"])
            v2_ep = classify_local_endpoint(ep, model_info, machine["id"])
            v2_endpoints.append(v2_ep)

        elif ep_type == "browser":
            v2_ep = classify_browser_endpoint(ep, browser_models)
            v2_endpoints.append(v2_ep)

        elif ep_type == "api":
            v2_ep = classify_api_endpoint(ep, commercial_models)
            v2_endpoints.append(v2_ep)

    # Build buckets from classified endpoints
    buckets = build_buckets(v2_endpoints)

    # Build default pipelines
    pipelines = build_default_pipelines()

    # Assemble v2 config
    v2_config = {
        "_schema_version": 2,
        "_note": "Model routing configuration. Generated by migrate-to-routing-config.py from endpoints.json v1.",
        "_migrated_from": str(ENDPOINTS_PATH),
        "machines": [machine],
        "endpoints": v2_endpoints,
        "buckets": buckets,
        "pipelines": pipelines,
        "reservation": {
            "enabled": True,
            "timeout_minutes": 30,
        },
        "constraints": {
            "mlx_parallel_same_machine": False,
            "ram_overhead_percent": RAM_OVERHEAD_PERCENT,
        },
        "ui_state": {
            "warnings_dismissed": [],
        },
        "paths": {
            "vault": v1.get("vault_path", ""),
            "conversations": v1.get("conversations_path", ""),
            "chromadb": v1.get("chromadb_path", ""),
        },
    }

    return v2_config


def main():
    dry_run = "--dry-run" in sys.argv
    output_path = OUTPUT_PATH

    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_path = Path(sys.argv[i + 1])

    if not ENDPOINTS_PATH.exists():
        print(f"Error: {ENDPOINTS_PATH} not found", file=sys.stderr)
        sys.exit(1)

    v2_config = migrate()

    if dry_run:
        print(json.dumps(v2_config, indent=2))
        print(f"\n--- Migration preview ---")
        print(f"Machines: {len(v2_config['machines'])}")
        print(f"Endpoints: {len(v2_config['endpoints'])}")
        for tier, models in v2_config["buckets"].items():
            print(f"Bucket '{tier}': {len(models)} models")
    else:
        # Back up existing routing-config.json if it exists
        if output_path.exists():
            backup = output_path.with_suffix(".json.bak")
            output_path.rename(backup)
            print(f"Backed up existing config to {backup}")

        with open(output_path, "w") as f:
            json.dump(v2_config, f, indent=2)
            f.write("\n")

        print(f"Migration complete: {output_path}")
        print(f"  Machines: {len(v2_config['machines'])}")
        print(f"  Endpoints: {len(v2_config['endpoints'])}")
        for tier, models in v2_config["buckets"].items():
            print(f"  Bucket '{tier}': {len(models)} models")


if __name__ == "__main__":
    main()
