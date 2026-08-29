#!/usr/bin/env python3
"""
scripts/migrate-to-configurations.py

One-time migration: convert routing-config.json::pipelines (interactive/agent)
into named configuration files in config/configurations/.

Reads:  config/routing-config.json
Writes: config/configurations/user-pipeline.json       (from .pipelines.interactive)
        config/configurations/background-default.json  (from .pipelines.agent)

Each new configuration carries cells with primary + fallback[] + vision_substitute,
mirroring the structure the existing slots block already uses (preferred + fallback).

This is non-breaking — the old pipelines block stays intact. The Router cutover
happens in step 2d of the install Chunk 2 sequence.

The migration walks each old bucket chain (cell-level buckets, falling back to
section-level buckets when the cell is null) and flattens it to a primary +
fallback list — the first eligible endpoint becomes primary, the rest become
fallback in order. Behavior-equivalent to the old "walk buckets, return first
eligible" logic in Router.resolve_endpoint.

Identifier form: this migration uses the raw endpoint id from endpoints[]
so Router lookups work without a mapping layer. Canonical <provider>:<id>
form will be applied in Chunk 12 (schema cleanup finalization) where
endpoints[].id itself gets migrated.

Run from repo root:
    /opt/homebrew/bin/python3 scripts/migrate-to-configurations.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTING_CONFIG = REPO_ROOT / "config" / "routing-config.json"
CONFIG_DIR = REPO_ROOT / "config" / "configurations"

sys.path.insert(0, str(REPO_ROOT / "orchestrator"))
import runtime_paths as _rp

PIPELINE_TO_CONFIG_NAME = {
    "interactive": "user-pipeline",
    "agent": "background-default",
}

PIPELINE_DESCRIPTIONS = {
    "user-pipeline": "Default configuration for user-initiated chat. Migrated from routing-config.json::pipelines.interactive on the Chunk 2 cutover. Replace with an auto-populated configuration when Chunk 5 (auto-populate engine) lands.",
    "background-default": "Default configuration for automated processes (frameworks, scheduled tasks, project tools) when they don't specify their own. Migrated from routing-config.json::pipelines.agent on the Chunk 2 cutover.",
}


def lookup_id(endpoint):
    """Return the raw endpoint id used in routing-config.json::endpoints[].

    Configurations carry raw IDs (not a canonicalized form) so Router lookups
    against the endpoints array work without a mapping layer. Canonicalization
    of cloud ids to <provider>:<id> form is deferred to Chunk 12, where
    endpoints[].id itself gets migrated to canonical form.
    """
    return endpoint.get("id", "")


def is_eligible(endpoint):
    """Endpoint is selectable if enabled and active."""
    return (
        endpoint.get("enabled", True) and
        endpoint.get("status", "active") == "active"
    )


def walk_buckets(bucket_chain, buckets_dict, endpoints_by_id):
    """Walk a bucket chain, return canonical IDs of eligible endpoints in order.

    Mirrors Router.resolve_endpoint's bucket walk minus the per-call exclusions
    (excluded_ids, same_machine_block) which are runtime concerns, not
    migration-time concerns.
    """
    result = []
    seen = set()
    for bucket_name in bucket_chain or []:
        if bucket_name == "STOP":
            break
        for ep_id in buckets_dict.get(bucket_name, []):
            if not ep_id:  # skip empty placeholder strings
                continue
            ep = endpoints_by_id.get(ep_id)
            if ep and is_eligible(ep):
                cid = lookup_id(ep)
                if cid not in seen:
                    result.append(cid)
                    seen.add(cid)
    return result


def cell_to_picks(cell, default_buckets, buckets_dict, endpoints_by_id):
    """Convert a pipeline cell (or None) to {primary, fallback}.

    cell is None or {}: inherit default_buckets.
    cell has "buckets": use that chain instead.
    """
    if cell is None or not cell.get("buckets"):
        bucket_chain = default_buckets
    else:
        bucket_chain = cell.get("buckets")

    picks = walk_buckets(bucket_chain, buckets_dict, endpoints_by_id)
    if not picks:
        return None
    return {
        "primary": picks[0],
        "fallback": picks[1:],
    }


def get_vision_substitute(routing_config, context):
    """Get the vision-substitute model ID for a pipeline context.

    Today the per-context vision substitute lives in slots.image_extracts.{context}.
    """
    slots = routing_config.get("slots", {})
    image_extracts = slots.get("image_extracts", {})
    val = image_extracts.get(context)
    return val if isinstance(val, str) else None


def attach_vision(cell, vision_sub):
    """Mutate a cell dict to carry vision_substitute when one exists."""
    if cell and vision_sub:
        cell["vision_substitute"] = vision_sub
    return cell


def migrate_pipeline(pipeline_name, pipeline_def, routing_config):
    """Convert one pipeline definition to a configuration dict."""
    buckets = routing_config.get("buckets", {})
    endpoints_by_id = {ep["id"]: ep for ep in routing_config.get("endpoints", [])}
    config_name = PIPELINE_TO_CONFIG_NAME[pipeline_name]
    vision_sub = get_vision_substitute(routing_config, pipeline_name)

    util_block = pipeline_def.get("utility", {})
    util_default = util_block.get("buckets", [])
    util_cells = util_block.get("cells") or {}

    analysis = pipeline_def.get("analysis", {})
    gear4 = analysis.get("gear4", {})
    gear3 = analysis.get("gear3", {})

    post = pipeline_def.get("post_analysis", {})
    post_default = post.get("buckets", [])
    post_cells = post.get("cells") or {}

    return {
        "name": config_name,
        "description": PIPELINE_DESCRIPTIONS[config_name],
        "preset_lineage": "migrated",
        "cells": {
            "utility": {
                "step1_cleanup": attach_vision(
                    cell_to_picks(util_cells.get("step1_cleanup"), util_default, buckets, endpoints_by_id),
                    vision_sub,
                ),
                "classification": attach_vision(
                    cell_to_picks(util_cells.get("classification"), util_default, buckets, endpoints_by_id),
                    vision_sub,
                ),
                "rag_planner": attach_vision(
                    cell_to_picks(util_cells.get("rag_planner"), util_default, buckets, endpoints_by_id),
                    vision_sub,
                ),
            },
            "analysis": {
                "gear4": {
                    "depth": attach_vision(
                        cell_to_picks(gear4.get("depth"), [], buckets, endpoints_by_id),
                        vision_sub,
                    ),
                    "breadth": attach_vision(
                        cell_to_picks(gear4.get("breadth"), [], buckets, endpoints_by_id),
                        vision_sub,
                    ),
                },
                "gear3": {
                    "depth": attach_vision(
                        cell_to_picks(gear3.get("depth"), [], buckets, endpoints_by_id),
                        vision_sub,
                    ),
                    "breadth": attach_vision(
                        cell_to_picks(gear3.get("breadth"), [], buckets, endpoints_by_id),
                        vision_sub,
                    ),
                },
            },
            "post_analysis": {
                "consolidation": attach_vision(
                    cell_to_picks(post_cells.get("consolidation"), post_default, buckets, endpoints_by_id),
                    vision_sub,
                ),
                "verification": attach_vision(
                    cell_to_picks(post_cells.get("verification"), post_default, buckets, endpoints_by_id),
                    vision_sub,
                ),
                # formatter inherits from post_analysis until Chunk 10 reassigns
                # it to the Utility tier per the simplified Pipeline UI design.
                "formatter": attach_vision(
                    cell_to_picks(post_cells.get("formatter"), post_default, buckets, endpoints_by_id),
                    vision_sub,
                ),
            },
        },
    }


def validate(configurations, routing_config):
    """Print a summary so a human can spot-check the migration."""
    print()
    print("=== Migration summary ===")
    for cfg_name, cfg in configurations.items():
        print(f"\n  {cfg_name}:")
        cells = cfg["cells"]
        for section_name, section in cells.items():
            if section_name == "analysis":
                for gear_name, gear_cells in section.items():
                    for slot_name, cell in gear_cells.items():
                        if cell is None:
                            print(f"    {section_name}.{gear_name}.{slot_name}: NO ELIGIBLE ENDPOINTS")
                        else:
                            n_fallback = len(cell.get("fallback", []))
                            print(f"    {section_name}.{gear_name}.{slot_name}: primary={cell['primary']!r}, fallback={n_fallback} entries")
            else:
                for slot_name, cell in section.items():
                    if cell is None:
                        print(f"    {section_name}.{slot_name}: NO ELIGIBLE ENDPOINTS")
                    else:
                        n_fallback = len(cell.get("fallback", []))
                        print(f"    {section_name}.{slot_name}: primary={cell['primary']!r}, fallback={n_fallback} entries")


def main():
    if not ROUTING_CONFIG.exists():
        print(f"ERROR: {ROUTING_CONFIG} not found", file=sys.stderr)
        sys.exit(1)

    with open(ROUTING_CONFIG) as f:
        routing_config = json.load(f)

    pipelines = routing_config.get("pipelines", {})
    if not pipelines:
        print("ERROR: no pipelines block in routing-config.json", file=sys.stderr)
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    written = {}
    for pipeline_name, pipeline_def in pipelines.items():
        if pipeline_name not in PIPELINE_TO_CONFIG_NAME:
            print(f"WARNING: unknown pipeline '{pipeline_name}', skipping")
            continue

        config = migrate_pipeline(pipeline_name, pipeline_def, routing_config)
        config_name = PIPELINE_TO_CONFIG_NAME[pipeline_name]
        out_path = CONFIG_DIR / f"{config_name}.json"

        with _rp.locked_file(out_path):
            _rp.atomic_write_text(
                out_path, json.dumps(config, indent=2) + "\n", mode=0o644,
            )

        written[config_name] = config
        print(f"Wrote {out_path.relative_to(REPO_ROOT)}")

    validate(written, routing_config)


if __name__ == "__main__":
    main()
