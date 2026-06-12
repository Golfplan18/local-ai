#!/usr/bin/env python3
"""campaign_run.py — Comparative Evaluation Campaign runner (2026-06-12).

Reproducible capture harness for the 198-technique campaign described in
the vault doc "Working — Campaign Run Plan 2026-06-06" and published on
ora-ai.app. For each selected technique it takes prompt #1 (the prime)
and runs it through four pipelines, capturing text, visual artifact,
token usage, and cost:

  premium      — Ora server, campaign-premium configuration (gear 4)
  qwen9b       — Ora server, campaign-qwen9b (qwen/qwen3.5-9b in every slot)
  optimum      — Ora server, campaign-optimum configuration (gear 4)
  optimum-plus — campaign-optimum with ONE upgraded cell: the flagship in
                 the consolidation slot (step 7). Data lane for the
                 "spend your money on the consolidator" hypothesis
                 (experiment 2026-06-12); whether it ships as a preset
                 default is decided AFTER the sweep.
  single-pass  — ONE bare API call to the flagship model, no harness.
                 The flagship is whatever the premium configuration's
                 big-1 slot picked (auto-selected by the same picker
                 algorithm that baked the configs).

Subcommands
-----------
  bake-configs   Re-bake the premium/optimum presets with the live picker
                 algorithm, copy them to campaign-premium / campaign-optimum,
                 generate campaign-qwen9b, stamp rag_isolation=web_only on
                 all three, and snapshot per-model pricing.
  list           Parse the corpus; print counts + technique ids.
  run            Execute the sweep. --techniques all | some | id[,id...]
                 --pipelines premium,qwen9b,optimum,single-pass
                 Resumable: completed (technique, pipeline) pairs are
                 skipped on re-run via the manifest.
  aggregate      Build cost tables (per pipeline + grand total) from the
                 manifest → cost-summary.md / cost-summary.json.
  render-doc     Assemble the long capture document (one section per
                 technique: prompt, then the four answers + visuals).
  all            bake-configs → run → aggregate → render-doc.

Reproducibility notes for third parties
---------------------------------------
* Requires a running Ora server (./start.sh) and the trigger-prompt
  corpus markdown (default: the vault copy; pass --corpus to point at
  the published copy downloaded from ora-ai.app).
* `bake-configs` derives the model picks from YOUR registry/catalog via
  the same auto-populate algorithm the Models pane uses — so the run
  reflects the models available to you at run time. The pricing snapshot
  in campaign-configs-snapshot.json records what was picked and at what
  per-1M rates.
* single-pass needs an API key: the flagship's direct vendor key when
  you have one (e.g. Anthropic), else your OpenRouter key.
* PNG rasterization needs `pip install playwright && playwright install
  chromium`. Without it the run still captures SVG.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
CONFIG_DIR = ORA_HOME / "config"
CONFIGURATIONS_DIR = CONFIG_DIR / "configurations"
CAMPAIGN_DIR = ORA_HOME / "data" / "campaign"
CAPTURES_DIR = CAMPAIGN_DIR / "captures"
MANIFEST_PATH = CAMPAIGN_DIR / "campaign-manifest.jsonl"
SNAPSHOT_PATH = CAMPAIGN_DIR / "campaign-configs-snapshot.json"
TRACES_DIR = ORA_HOME / "data" / "pipeline-traces"
RENDER_ENVELOPE_JS = (
    ORA_HOME / "server" / "static" / "ora-visual-compiler" / "tools" / "render-envelope.js"
)
DEFAULT_CORPUS = Path(os.path.expanduser(
    "~/Documents/vault/Reference — Trigger Prompt Corpus.md"))
DEFAULT_SERVER = "http://localhost:5000"

ORA_PIPELINES = {
    "premium": "campaign-premium",
    "qwen9b": "campaign-qwen9b",
    "optimum": "campaign-optimum",
    "optimum-plus": "campaign-optimum-plus",
}
ALL_PIPELINES = ["premium", "qwen9b", "optimum", "optimum-plus", "single-pass"]

# Same pattern orchestrator/visual_adversarial.py uses to find envelopes.
VISUAL_FENCE = re.compile(r"```ora-visual\s*\n(.*?)\n```", re.DOTALL)

# The 'some' subset: a representative spread for a quick self-verification
# run — 4 analysis modes, 4 visual tools, 4 high-recognition lenses.
# 12 techniques × 4 pipelines = 48 captures (vs 792 for the full sweep).
SOME_SUBSET = [
    # analysis modes
    "argument-audit", "cui-bono", "decision-under-uncertainty", "wicked-problems",
    # visual tools
    "ach-matrix", "bow-tie-diagram", "causal-loop-diagram", "decision-tree",
    # lenses
    "anchoring", "availability-heuristic", "incentives", "second-order-thinking",
]

# All ten cell paths a campaign configuration carries (mirrors the
# qwen-9b-only layout — gear2_rag_lookup is optional and inherits).
QWEN9B_CELL_PATHS = [
    ("utility", "step1_cleanup"),
    ("utility", "classification"),
    ("utility", "rag_planner"),
    ("analysis", "gear4", "depth"),
    ("analysis", "gear4", "breadth"),
    ("analysis", "gear3", "depth"),
    ("analysis", "gear3", "breadth"),
    ("post_analysis", "consolidation"),
    ("post_analysis", "verification"),
    ("post_analysis", "formatter"),
]
QWEN9B_MODEL = "qwen/qwen3.5-9b"

RAG_NOTE = ("CAMPAIGN-RAG-BYPASS — campaign configurations run with "
            "rag_isolation=web_only so captures reflect a clean install "
            "(no vault/conversation RAG), reproducible by third parties.")

# Subscription-premium (decision 2026-06-12): the premium lane can run on
# the user's Claude subscription via the local Claude Code CLI instead of
# the metered API — same models, zero marginal dollars, throughput
# governed by the subscription's rolling rate windows. Opus carries the
# big + post-analysis slots; Haiku the fast + utility slots (single-family
# adversarial pair — the cross-vendor diversity tradeoff is deliberate).
CLAUDE_CODE_OPUS = "claude-code:claude-opus-4.8"
CLAUDE_CODE_HAIKU = "claude-code:claude-haiku-4.5"
CLAUDE_CODE_ENDPOINTS = [
    {"id": CLAUDE_CODE_OPUS, "model_id": "claude-opus-4-8",
     "display_name": "Claude Opus 4.8 (subscription via Claude Code)",
     "api_equivalent": "anthropic/claude-opus-4.8"},
    {"id": CLAUDE_CODE_HAIKU, "model_id": "claude-haiku-4-5",
     "display_name": "Claude Haiku 4.5 (subscription via Claude Code)",
     "api_equivalent": "anthropic/claude-haiku-4.5"},
]
SUBSCRIPTION_PIPELINES = {"premium"}  # lanes that ride the subscription
                                      # when --premium subscription baked


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─── Corpus parsing ───────────────────────────────────────────────────────


@dataclass
class Technique:
    id: str
    kind: str            # "mode" | "visual" | "lens"
    intended_mode: str
    prompt: str


_BACKTICK_ID = re.compile(r"`([^`]+)`")


def parse_corpus(path: Path) -> list[Technique]:
    """Parse the trigger-prompt corpus into (id, kind, intended_mode,
    prompt #1) records.

    Section shapes (verified against the 2026-06-06 corpus):
      ## Modes (by territory)  → entries at ####, mode line "**Intended mode:**"
      ## Visual tools          → entries at ###,  mode line "**Routes to:**"
      ## Lenses                → entries at ####, mode line "**Host mode:**"
    Prompt #1 is the first numbered list item ("1. …") in the entry.
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.split("\n")

    section = None          # None | mode | visual | lens
    entry_id = None
    entry_kind = None
    entry_mode = None
    entry_prompt = None
    out: list[Technique] = []

    def _flush():
        nonlocal entry_id, entry_mode, entry_prompt
        if entry_id:
            if not entry_mode or not entry_prompt:
                raise ValueError(
                    f"corpus entry `{entry_id}` is missing "
                    f"{'a mode line' if not entry_mode else 'prompt #1'}")
            out.append(Technique(entry_id, entry_kind, entry_mode, entry_prompt))
        entry_id = entry_mode = entry_prompt = None

    for line in lines:
        if line.startswith("## "):
            _flush()
            h = line[3:].strip()
            if h.startswith("Modes"):
                section = "mode"
            elif h.startswith("Visual tools"):
                section = "visual"
            elif h.startswith("Lenses"):
                section = "lens"
            else:
                section = None
            continue
        if section is None:
            continue
        # Entry headings: visual tools sit at ###; modes/lenses at ####
        # (### inside those sections is a territory grouping, not an entry).
        is_entry = (
            (section == "visual" and line.startswith("### `"))
            or (section in ("mode", "lens") and line.startswith("#### `"))
        )
        if is_entry:
            _flush()
            m = _BACKTICK_ID.search(line)
            entry_id = m.group(1) if m else None
            entry_kind = section
            continue
        if entry_id is None:
            continue
        if entry_mode is None:
            for marker in ("**Intended mode:**", "**Routes to:**", "**Host mode:**"):
                if line.startswith(marker):
                    m = _BACKTICK_ID.search(line[len(marker):])
                    if m:
                        entry_mode = m.group(1)
                    break
        if entry_prompt is None and re.match(r"^1\.\s+", line):
            entry_prompt = re.sub(r"^1\.\s+", "", line).strip()
    _flush()
    return out


def select_techniques(all_techniques: list[Technique], spec: str) -> list[Technique]:
    """Resolve --techniques: 'all' | 'some' | comma-separated ids."""
    by_id = {t.id: t for t in all_techniques}
    if spec == "all":
        return list(all_techniques)
    if spec == "some":
        wanted = SOME_SUBSET
    else:
        wanted = [s.strip() for s in spec.split(",") if s.strip()]
    missing = [w for w in wanted if w not in by_id]
    if missing:
        raise SystemExit(
            f"unknown technique id(s): {', '.join(missing)} — "
            f"run `campaign_run.py list` for the full catalog")
    return [by_id[w] for w in wanted]


# ─── Configuration baking ────────────────────────────────────────────────


def _load_registry_pricing() -> dict:
    """id → {input_per_million_usd, output_per_million_usd} from the live
    registry. Missing pricing → nulls (cost rows show 'unpriced')."""
    reg_path = CONFIG_DIR / "model-registry.json"
    out: dict = {}
    try:
        models = json.loads(reg_path.read_text()).get("models") or {}
    except Exception:
        return out
    for mid, m in models.items():
        p = m.get("pricing") or {}
        ipt, opt = p.get("input_per_token"), p.get("output_per_token")
        out[mid] = {
            "input_per_million_usd": round(ipt * 1e6, 4) if ipt is not None else None,
            "output_per_million_usd": round(opt * 1e6, 4) if opt is not None else None,
        }
    return out


def _stamp_campaign_fields(config: dict, name: str, source: str) -> dict:
    config["name"] = name
    config["preset_lineage"] = "campaign"
    config["rag_isolation"] = "web_only"
    config["_rag_isolation_note"] = RAG_NOTE
    config["_campaign_source"] = source
    config["_campaign_baked_at"] = _now_iso()
    return config


def _config_models(config: dict) -> dict:
    """The five card-visible model picks (2 big, 2 fast, 1 small)."""
    cells = config.get("cells") or {}
    def cell(*path):
        node = cells
        for k in path:
            node = (node or {}).get(k) or {}
        return node.get("primary") if isinstance(node, dict) else None
    return {
        "big1": cell("analysis", "gear4", "depth"),
        "big2": cell("analysis", "gear4", "breadth"),
        "fast1": cell("analysis", "gear3", "depth"),
        "fast2": cell("analysis", "gear3", "breadth"),
        "small": cell("utility", "step1_cleanup"),
    }


def _poke_router_reload(server: str = DEFAULT_SERVER) -> bool:
    """Ask the running server to reload its singleton Router after this
    process edited routing-config.json on disk. An EMPTY per-slot merge
    (``POST /config/routing/slots`` with ``{"slots": {}}``) changes
    nothing but runs the route's save + router-reload hook — the same
    hook the Settings panel autosave uses. Best-effort: when the server
    is down (bake before start), startup loads fresh anyway."""
    try:
        req = urllib.request.Request(
            f"{server}/config/routing/slots",
            data=json.dumps({"slots": {}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
        reloaded = bool(out.get("router_reloaded"))
        if not reloaded:
            print("[bake] server saved config but router reload reported "
                  "False — restart the server before a subscription run")
        return reloaded
    except Exception as exc:
        print(f"[bake] router reload poke skipped ({str(exc)[:120]}) — "
              f"if the server was already running, restart it to pick up "
              f"the new endpoints")
        return False


def ensure_claude_code_endpoints() -> None:
    """Register the subscription (Claude Code CLI) endpoints in
    routing-config.json when absent. Their ids live outside the catalog
    namespace, so the automatic endpoint sync preserves them."""
    rc_path = CONFIG_DIR / "routing-config.json"
    rc = json.loads(rc_path.read_text())
    by_id = {(e.get("id") or e.get("name")): e for e in rc.get("endpoints") or []}
    added = 0
    for spec in CLAUDE_CODE_ENDPOINTS:
        if spec["id"] in by_id:
            continue
        rc["endpoints"].append({
            "id": spec["id"],
            "type": "api",
            "status": "active",
            "enabled": True,
            "provider": "anthropic",
            "display_name": spec["display_name"],
            "service": "claude-code",
            "model_id": spec["model_id"],
            "dispatch": "subscription",
            "vision_capable": True,
            "context_window": 200000,
            "capabilities": {"tool_access": False, "file_system_access": False,
                             "web_access": False,
                             "retrieval_approach": "pre-assembled"},
            "_note": ("Subscription execution via the local Claude Code CLI "
                      "(claude -p). Zero marginal API cost; campaign cost "
                      "tables price its tokens at the API-equivalent rate."),
        })
        added += 1
    if added:
        tmp = rc_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rc, indent=2) + "\n")
        os.replace(tmp, rc_path)
        print(f"[bake] registered {added} claude-code subscription endpoint(s)")
        if _poke_router_reload():
            print("[bake] running server reloaded its router")


def build_subscription_premium() -> dict:
    """The user-specified subscription premium: Opus 4.8 in both big
    slots + all post-analysis cells; Haiku 4.5 in the fast pair and the
    utility cells. No fallbacks — a failed call fails loudly (and the
    fidelity gate keeps any drift out of the captures)."""
    def cell(mid):
        return {"primary": mid, "fallback": []}
    cells = {
        "utility": {
            "step1_cleanup": cell(CLAUDE_CODE_HAIKU),
            "classification": cell(CLAUDE_CODE_HAIKU),
            "rag_planner": cell(CLAUDE_CODE_HAIKU),
            "gear2_rag_lookup": cell(CLAUDE_CODE_HAIKU),
        },
        "analysis": {
            "gear4": {"depth": cell(CLAUDE_CODE_OPUS),
                      "breadth": cell(CLAUDE_CODE_OPUS)},
            "gear3": {"depth": cell(CLAUDE_CODE_HAIKU),
                      "breadth": cell(CLAUDE_CODE_HAIKU)},
        },
        "post_analysis": {
            "consolidation": cell(CLAUDE_CODE_OPUS),
            "verification": cell(CLAUDE_CODE_OPUS),
            "formatter": cell(CLAUDE_CODE_OPUS),
        },
    }
    return {
        "name": "campaign-premium",
        "description": (
            "Subscription premium: Claude Opus 4.8 in both big slots and "
            "all post-analysis cells, Claude Haiku 4.5 in fast + utility — "
            "executed through the user's Claude subscription via the local "
            "Claude Code CLI (service=claude-code), not the metered API. "
            "Single-family adversarial pair by deliberate tradeoff. Cost "
            "tables report API-equivalent token pricing."),
        "diversity_override": False,
        "cells": cells,
        "toggles": {"adversarial_diversity": True, "vision_only": False},
    }


def build_optimum_plus(optimum_config: dict, consolidator_id: str) -> dict:
    """Exact duplicate of campaign-optimum with ONE change: the
    consolidation primary (step 7 — the call that reads both adversarial
    streams and writes what the user sees) becomes the flagship. Every
    other field — fallback chains included — stays identical (user spec
    2026-06-12). A throttled flagship falling back to the chain is caught
    by the fidelity gate's required-subscription-models check, not by
    emptying the chain."""
    import copy
    cfg = copy.deepcopy(optimum_config)
    cfg["cells"]["post_analysis"]["consolidation"]["primary"] = consolidator_id
    cfg["description"] = (
        "Optimum+ — exact duplicate of campaign-optimum with one change: "
        f"the consolidation primary is {consolidator_id}. Captures whether "
        "a premium consolidator alone lifts the cheap pipeline's "
        "deliverable (experiment 2026-06-12: 11-0-1 for the variant).")
    return cfg


def bake_configs(rebake_presets: bool = True, premium_mode: str = "api") -> dict:
    """Build the three campaign configurations + the pricing snapshot.

    premium/optimum come from a FRESH preset bake (the picker algorithm
    against the live catalog + probe-verified registry), then copied to
    campaign-* names so later pane edits / re-bakes can't drift the
    campaign mid-run. qwen9b is generated (single model in every cell).

    ``premium_mode``: "api" (picker-baked, metered) or "subscription"
    (Opus/Haiku through the user's Claude subscription via Claude Code;
    cost tables then carry API-equivalent pricing for that lane).
    """
    sys.path.insert(0, str(ORA_HOME))
    from orchestrator import active_configuration as ac

    if rebake_presets:
        baked = ac.bake_missing_presets(force=True)
        print(f"[bake] presets re-baked from live catalog: {baked}")

    snapshot: dict = {"baked_at": _now_iso(), "configs": {},
                      "premium_mode": premium_mode}
    pricing = _load_registry_pricing()
    # claude-code ids price at their API twin's rate (API-equivalent).
    for spec in CLAUDE_CODE_ENDPOINTS:
        eq = pricing.get(spec["api_equivalent"])
        if eq:
            pricing[spec["id"]] = dict(eq, cost_basis="api_equivalent")
            pricing[spec["model_id"]] = pricing[spec["id"]]

    pairs = [("optimum", "campaign-optimum")]
    if premium_mode == "api":
        pairs.insert(0, ("premium", "campaign-premium"))
    else:
        ensure_claude_code_endpoints()
        config = build_subscription_premium()
        _stamp_campaign_fields(config, "campaign-premium",
                               source="subscription:opus-4.8+haiku-4.5")
        (CONFIGURATIONS_DIR / "campaign-premium.json").write_text(
            json.dumps(config, indent=2) + "\n")
        models = _config_models(config)
        snapshot["configs"]["campaign-premium"] = {
            "models": models,
            "pricing": {m: pricing.get(m) for m in set(filter(None, models.values()))},
            "cost_basis": "api_equivalent",
        }
        print(f"[bake] campaign-premium (subscription): {models}")

    for preset, campaign_name in pairs:
        src = CONFIGURATIONS_DIR / f"{preset}.json"
        config = json.loads(src.read_text())
        config["description"] = (
            f"Campaign copy of the auto-baked '{preset}' preset "
            f"(picker algorithm, {config.get('_auto_populate_metadata', {}).get('preset', preset)}). "
            f"Frozen for the Comparative Evaluation Campaign; not re-baked by the pane.")
        _stamp_campaign_fields(config, campaign_name, source=f"preset:{preset}")
        (CONFIGURATIONS_DIR / f"{campaign_name}.json").write_text(
            json.dumps(config, indent=2) + "\n")
        models = _config_models(config)
        snapshot["configs"][campaign_name] = {
            "models": models,
            "pricing": {m: pricing.get(m) for m in set(filter(None, models.values()))},
        }
        print(f"[bake] {campaign_name}: {models}")

    # campaign-optimum-plus — optimum with the flagship in the ONE cell the
    # 2026-06-12 experiment showed concentrates intelligence-per-dollar:
    # consolidation (step 7). Captured as its own lane so the full-sweep
    # data exists BEFORE deciding whether the optimum preset default
    # changes (n=12 verdict: 11-0-1 for the variant, ~+$0.25/run).
    # The consolidator is premium's big-1 AS PICKED — in subscription mode
    # that is the claude-code endpoint (user spec 2026-06-12: "the Opus 4.8
    # from my subscription account"), so the 198 consolidation calls cost
    # zero marginal dollars and the tables price them API-equivalent (†).
    # Third parties baking with --premium api get the metered flagship.
    consolidator_id = snapshot["configs"]["campaign-premium"]["models"]["big1"]
    opt_plus = build_optimum_plus(
        json.loads((CONFIGURATIONS_DIR / "campaign-optimum.json").read_text()),
        consolidator_id)
    _stamp_campaign_fields(opt_plus, "campaign-optimum-plus",
                           source=f"optimum+consolidator:{consolidator_id}")
    (CONFIGURATIONS_DIR / "campaign-optimum-plus.json").write_text(
        json.dumps(opt_plus, indent=2) + "\n")
    models_plus = _config_models(opt_plus)
    plus_ids = set(filter(None, models_plus.values())) | {consolidator_id}
    snapshot["configs"]["campaign-optimum-plus"] = {
        "models": dict(models_plus, consolidator=consolidator_id),
        "pricing": {m: pricing.get(m) for m in plus_ids},
    }
    print(f"[bake] campaign-optimum-plus: optimum + consolidation→{consolidator_id}")

    # campaign-qwen9b — one model, every cell, no fallbacks.
    cells: dict = {}
    for path in QWEN9B_CELL_PATHS:
        node = cells
        for k in path[:-1]:
            node = node.setdefault(k, {})
        node[path[-1]] = {"primary": QWEN9B_MODEL, "fallback": []}
    qwen = {
        "name": "campaign-qwen9b",
        "description": (
            "Single-model campaign configuration: qwen/qwen3.5-9b in every "
            "slot via OpenRouter — the full-precision twin of the local "
            "OptiQ 4-bit MLX bundle anyone can download from Hugging Face. "
            "Demonstrates what Ora's architecture lifts a 9B model to. "
            "No fallbacks: if the model fails, the step genuinely degrades."),
        "diversity_override": False,
        "cells": cells,
        "toggles": {"adversarial_diversity": True, "vision_only": False},
    }
    _stamp_campaign_fields(qwen, "campaign-qwen9b", source="generated:qwen3.5-9b")
    (CONFIGURATIONS_DIR / "campaign-qwen9b.json").write_text(
        json.dumps(qwen, indent=2) + "\n")
    snapshot["configs"]["campaign-qwen9b"] = {
        "models": _config_models(qwen),
        "pricing": {QWEN9B_MODEL: pricing.get(QWEN9B_MODEL)},
    }
    print(f"[bake] campaign-qwen9b: {QWEN9B_MODEL} in all {len(QWEN9B_CELL_PATHS)} cells")

    # The single-pass flagship = premium's big-1 pick, and it FOLLOWS the
    # premium execution mode: subscription bake → the bare control call
    # also rides the subscription (same model, same serving stack; cost
    # tables price it API-equivalent). Third parties running the
    # downloadable framework bake with --premium api and get the metered
    # call instead.
    flagship = snapshot["configs"]["campaign-premium"]["models"]["big1"]
    snapshot["single_pass_flagship"] = {
        "model_id": flagship,
        "pricing": pricing.get(flagship),
    }
    print(f"[bake] single-pass flagship (premium big-1): {flagship}")

    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"[bake] snapshot → {SNAPSHOT_PATH}")
    return snapshot


# ─── Manifest (resume + retry bookkeeping) ───────────────────────────────


def load_manifest() -> dict:
    """(technique, pipeline) → latest record."""
    done: dict = {}
    if MANIFEST_PATH.exists():
        for line in MANIFEST_PATH.read_text().splitlines():
            try:
                rec = json.loads(line)
                done[(rec["technique"], rec["pipeline"])] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return done


_MANIFEST_LOCK = __import__("threading").Lock()


def append_manifest(rec: dict) -> None:
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    with _MANIFEST_LOCK:
        with open(MANIFEST_PATH, "a") as f:
            f.write(json.dumps(rec) + "\n")


# ─── Ora-pipeline capture (POST /chat — synchronous, file-as-truth) ──────

# Oversight-health banners the server prepends to assistant replies when
# its meta-layer daemon looks stale. Operational noise, not part of the
# answer — strip from captures. (Pipeline degradation signals are NOT
# stripped: those describe the run itself and belong in the record.)
_OVERSIGHT_BANNER = re.compile(
    r"^> [^\n]*\*\*Meta-layer oversight[^\n]*\n(?:>[^\n]*\n)*\s*---\s*\n+",
)


def strip_system_banners(text: str) -> str:
    out = text.lstrip("\n")
    while True:
        m = _OVERSIGHT_BANNER.match(out)
        if not m:
            return out
        out = out[m.end():].lstrip("\n")


def run_ora_pipeline(server: str, config_name: str, technique: Technique,
                     conv_id: str, timeout: int = 2400) -> dict:
    """One pipeline run. Returns {text, trace_dir} or raises RuntimeError.

    V3 protocol (file-as-source-of-truth, 2026-04-30): ``POST /chat``
    runs the pipeline SYNCHRONOUSLY and replies once with
    ``{"status": "ok"|"errored", "conversation_id", "chunk_id", ...}`` —
    no SSE, no streaming. The final user-facing text (post-visual-hook,
    so suppressed envelopes are gone and synthesized repairs spliced in)
    is then read from the conversation API.
    """
    payload = {
        "message": technique.prompt,
        "panel_id": conv_id,
        "history": [],
        "config_name": config_name,
        "manual_mode_selection": technique.intended_mode,
    }
    req = urllib.request.Request(
        f"{server}/chat", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read())
    if d.get("status") != "ok":
        raise RuntimeError(
            f"pipeline {d.get('status') or 'failed'}: "
            f"{str(d.get('failure_summary') or d)[:300]}")
    with urllib.request.urlopen(f"{server}/api/conversation/{conv_id}",
                                timeout=60) as r:
        conv = json.loads(r.read())
    assistant = [m for m in (conv.get("messages") or [])
                 if m.get("role") == "assistant"]
    if not assistant:
        raise RuntimeError("no assistant message in conversation after run")
    text = strip_system_banners(assistant[-1].get("content") or "")
    if not text.strip():
        raise RuntimeError("empty assistant response")
    return {"text": text, "trace_dir": _latest_trace_dir(conv_id)}


def _latest_trace_dir(conv_id: str) -> str | None:
    base = TRACES_DIR / conv_id
    if not base.is_dir():
        return None
    turns = sorted(p.name for p in base.iterdir() if p.is_dir())
    return str(base / turns[-1]) if turns else None


def price_usage_records(trace_dir: str | None, rate_map: dict) -> float | None:
    """Price a trace's usage.jsonl against a rate map (endpoint_id /
    model_id → {input_per_million_usd, output_per_million_usd}).

    Fallback for lanes whose endpoint ids aren't in the model registry —
    the subscription endpoints (claude-code:*) cost $0 marginal, so the
    campaign prices their tokens at the API-equivalent rate to keep the
    published comparison honest."""
    if not trace_dir or not rate_map:
        return None
    path = Path(trace_dir) / "usage.jsonl"
    if not path.exists():
        return None
    total, any_priced = 0.0, False
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rate = (rate_map.get(rec.get("endpoint_id"))
                or rate_map.get(rec.get("model_id")))
        if not rate or rate.get("input_per_million_usd") is None:
            continue
        total += ((rec.get("prompt_tokens") or 0) / 1e6
                  * rate["input_per_million_usd"]
                  + (rec.get("completion_tokens") or 0) / 1e6
                  * rate["output_per_million_usd"])
        any_priced = True
    return round(total, 6) if any_priced else None


def read_trace_cost(trace_dir: str | None) -> dict:
    """Totals from the trace's cost-summary.json (rates embedded at run
    time — the de-facto price snapshot per run)."""
    empty = {"prompt_tokens": 0, "completion_tokens": 0, "total_cost_usd": None,
             "models": []}
    if not trace_dir:
        return empty
    path = Path(trace_dir) / "cost-summary.json"
    if not path.exists():
        return empty
    try:
        cs = json.loads(path.read_text())
    except json.JSONDecodeError:
        return empty
    totals = cs.get("totals") or {}
    return {
        "prompt_tokens": totals.get("prompt_tokens", 0),
        "completion_tokens": totals.get("completion_tokens", 0),
        "total_cost_usd": totals.get("total_cost_usd"),
        "models": [r.get("model_id") for r in (cs.get("models") or [])],
    }


# ─── Fidelity gate: only the specified models may serve ─────────────────


def load_expected_primaries(config_name: str) -> set:
    """Every cell primary in the campaign configuration — the ONLY models
    allowed to record usage during a run. Fallback-chain entries are
    deliberately excluded: a 429/throttle that cascades to a fallback
    model invalidates the capture (the comparison is between SPECIFIED
    model sets, not whatever happened to answer)."""
    config = json.loads((CONFIGURATIONS_DIR / f"{config_name}.json").read_text())
    expected: set = set()

    def walk(node):
        if isinstance(node, dict):
            if "primary" in node:
                if node.get("primary"):
                    expected.add(node["primary"])
            else:
                for v in node.values():
                    walk(v)
    walk(config.get("cells") or {})
    return expected


_OK_FINISH = {"", "stop", "end_turn", "stop_sequence", "eos", "none"}


def _finish_ok(finish_reason) -> bool:
    """Normalize the per-wrapper finish_reason shapes (OpenAI 'stop',
    Anthropic 'end_turn', Gemini's enum repr 'FinishReason.STOP') and
    answer whether the call terminated normally."""
    if finish_reason is None:
        return True
    s = str(finish_reason).split(".")[-1].strip().lower()
    return s in _OK_FINISH


def verify_trace_fidelity(trace_dir: str | None, expected: set) -> dict:
    """Audit a completed run's trace against the configured primaries.

    Checks:
      1. Every usage.jsonl record's endpoint_id is one of the expected
         primaries (a fallback model serving = violation). Direct-vendor
         and OpenRouter transports record the same endpoint_id, so a
         same-model transport fallback passes — only a MODEL substitution
         fails.
      2. No step file recorded ok=false (silent step degradation).
      3. finish_reason anomalies (length/content_filter/429 markers) are
         surfaced as warnings — the step may have self-healed, but the
         reviewer should know.

    Returns {ok, violations, warnings, executed} — executed is
    endpoint_id → call count for the manifest record.
    """
    result = {"ok": False, "violations": [], "warnings": [], "executed": {}}
    if not trace_dir:
        result["violations"].append({"kind": "no_trace",
                                     "detail": "no trace directory found"})
        return result
    tdir = Path(trace_dir)
    usage_path = tdir / "usage.jsonl"
    if not usage_path.exists():
        result["violations"].append({"kind": "no_usage",
                                     "detail": "trace has no usage.jsonl"})
        return result
    for line in usage_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = rec.get("endpoint_id") or rec.get("model_id") or "?"
        result["executed"][eid] = result["executed"].get(eid, 0) + 1
        if eid not in expected:
            result["violations"].append({
                "kind": "unexpected_model", "model": eid,
                "step_hint": rec.get("step_hint"),
                "service": rec.get("service")})
        fr = rec.get("finish_reason")
        if not _finish_ok(fr):
            result["warnings"].append({
                "kind": "finish_reason", "model": eid,
                "finish_reason": str(fr), "step_hint": rec.get("step_hint")})
    for step_file in sorted(tdir.glob("step*.json")):
        try:
            d = json.loads(step_file.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict) and "ok" in d and d.get("ok") is False:
            result["violations"].append({
                "kind": "step_failed", "step": step_file.stem,
                "detail": str(d.get("reason"))[:200]})
    # Subscription primaries MUST have executed. They dispatch only via
    # the claude-code CLI (no same-id transport fallback), so their
    # absence from the census means a throttle handed their step to a
    # fallback-chain model — undetectable above when that model is a
    # legitimate primary of some OTHER cell (e.g. optimum-plus: a
    # throttled Opus consolidator falling back to the gemini big-2).
    for mid in expected:
        if mid.startswith("claude-code:") and mid not in result["executed"]:
            result["violations"].append({
                "kind": "required_model_missing", "model": mid,
                "detail": "subscription primary never executed — its step "
                          "was served by a fallback or skipped"})
    result["ok"] = not result["violations"]
    return result


# ─── Single-pass flagship (bare API call, usage captured) ────────────────


def _keyring_get(name: str) -> str | None:
    try:
        import keyring
        return keyring.get_password("ora", name)
    except Exception:
        return None


def resolve_flagship_endpoint(flagship_id: str) -> dict:
    """Find the routing-config endpoint for the flagship id (registered by
    the endpoint sync; dispatch=direct when the vendor key exists)."""
    rc = json.loads((CONFIG_DIR / "routing-config.json").read_text())
    for ep in rc.get("endpoints") or []:
        if (ep.get("id") or ep.get("name")) == flagship_id:
            return ep
    raise SystemExit(
        f"no endpoint registered for flagship {flagship_id!r} — open the "
        f"Models pane and hit Refresh (runs the endpoint sync), then retry")


def _single_pass_claude_code(endpoint: dict, prompt: str,
                             timeout: int) -> dict:
    """Bare flagship call through the Claude Code CLI (subscription).
    Mirrors boot's claude-code service: no system prompt, no tools,
    usage from the requested model's modelUsage entry, served-model
    verified."""
    import subprocess
    model_id = endpoint.get("model_id") or "claude-opus-4-8"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cli = os.environ.get("ORA_CLAUDE_CODE_BIN") or "claude"
    r = subprocess.run(
        [cli, "-p", "--model", model_id, "--output-format", "json",
         "--tools", ""],
        input=prompt, capture_output=True, text=True, timeout=timeout,
        env=env)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:300]
        kind = "rate-limited: " if ("limit" in err.lower()
                                    or "rate" in err.lower()) else ""
        raise RuntimeError(f"claude-code {kind}{err}")
    d = json.loads(r.stdout)
    if d.get("is_error"):
        err = str(d.get("result") or "")[:300]
        kind = "rate-limited: " if "limit" in err.lower() else ""
        raise RuntimeError(f"claude-code {kind}{err}")
    mu = d.get("modelUsage") or {}
    main_key = next((k for k in mu if k.startswith(model_id)), None)
    if mu and main_key is None:
        raise RuntimeError(
            f"single-pass fidelity: requested {model_id}, served {sorted(mu)}")
    usage = (mu.get(main_key) or {}) if main_key else {}
    top = d.get("usage") or {}
    return {"text": d.get("result") or "",
            "prompt_tokens": usage.get("inputTokens",
                                       top.get("input_tokens", 0)),
            "completion_tokens": usage.get("outputTokens",
                                           top.get("output_tokens", 0)),
            "model_id": model_id,
            "served_model": main_key or model_id,
            "via": "claude-code-subscription"}


def single_pass_call(endpoint: dict, prompt: str, max_tokens: int = 16000,
                     timeout: int = 600) -> dict:
    """Bare one-model call with usage capture. Returns
    {text, prompt_tokens, completion_tokens, model_id, via}."""
    service = endpoint.get("service")
    model_id = endpoint.get("model_id") or endpoint.get("id")
    if service == "claude-code":
        return _single_pass_claude_code(endpoint, prompt, timeout)
    if service == "claude":
        key = _keyring_get("anthropic-api-key") or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("no Anthropic API key (keyring ora/anthropic-api-key)")
        body = {"model": model_id, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read())
        text = "".join(b.get("text", "") for b in d.get("content") or []
                       if b.get("type") == "text")
        usage = d.get("usage") or {}
        served = d.get("model") or model_id
        if not served.startswith(model_id):
            # Fidelity: the API must serve the requested model (a dated
            # variant of it is fine: claude-opus-4-8-20260301 etc.).
            raise RuntimeError(f"single-pass fidelity: requested {model_id}, "
                               f"served {served}")
        return {"text": text, "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "model_id": model_id, "served_model": served,
                "via": "anthropic-direct"}
    # Everything else (incl. service openai/gemini without special-casing
    # their bare-completion APIs) goes through OpenRouter under the
    # canonical slug — the third-party-reproducible floor.
    key = _keyring_get("openrouter-api-key") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no OpenRouter API key (keyring ora/openrouter-api-key)")
    slug = endpoint.get("openrouter_fallback_model_id") or endpoint.get("id")
    body = {"model": slug, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read())
    choice = (d.get("choices") or [{}])[0]
    usage = d.get("usage") or {}
    served = d.get("model") or slug
    if served not in (slug, slug.split(":", 1)[0]):
        # Fidelity: OpenRouter must serve the requested slug, not a
        # router-substituted sibling.
        raise RuntimeError(f"single-pass fidelity: requested {slug}, "
                           f"served {served}")
    return {"text": (choice.get("message") or {}).get("content") or "",
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "model_id": slug, "served_model": served, "via": "openrouter"}


def price_single_pass(rec: dict, pricing: dict | None) -> float | None:
    if not pricing or pricing.get("input_per_million_usd") is None:
        return None
    return round(
        rec["prompt_tokens"] / 1e6 * pricing["input_per_million_usd"]
        + rec["completion_tokens"] / 1e6 * pricing["output_per_million_usd"], 6)


# ─── Visual capture: extract → SVG → PNG ─────────────────────────────────


def extract_visuals(text: str) -> tuple[str, list[str]]:
    """Split the final response into (prose-with-placeholder, envelope
    JSON strings). The input is the POST-hook text the user saw, so
    suppressed envelopes are already gone and synthesized repairs are
    already spliced in."""
    envelopes = [m.group(1) for m in VISUAL_FENCE.finditer(text)]
    prose = VISUAL_FENCE.sub("*(visual rendered — see artifact)*", text).strip()
    return prose, envelopes


def render_svg(envelope_json: str, out_svg: Path) -> bool:
    """Envelope JSON → SVG via the compiler's node CLI. Fail-soft."""
    if not RENDER_ENVELOPE_JS.exists():
        return False
    try:
        r = subprocess.run(
            ["node", str(RENDER_ENVELOPE_JS)], input=envelope_json,
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and r.stdout.strip().startswith("<"):
            out_svg.write_text(r.stdout)
            return True
        print(f"    [visual] render-envelope failed rc={r.returncode}: "
              f"{(r.stderr or '')[:200]}")
    except Exception as exc:
        print(f"    [visual] render-envelope error: {exc}")
    return False


def render_visuals_browser(server: str, envelopes: list[str],
                           out_dir: Path, width: int = 1400) -> tuple[int, int]:
    """Render envelopes with the REAL compiler in real Chromium and
    rasterize each artifact — the exact render Ora's visual pane shows
    (browser layout + the app's theme), unlike the jsdom CLI whose
    missing getBBox degrades geometry. Loads the V3 app once (it boots
    the full compiler incl. schema-validated Ajv), calls
    ``OraVisualCompiler.compileWithNav`` per envelope, injects the SVG
    into a clean host styled by the app's stylesheet, and element-
    screenshots it at 2× scale. Returns (svg_count, png_count).
    Raises ImportError when Playwright is unavailable (caller falls back
    to the jsdom SVG-only path)."""
    from playwright.sync_api import sync_playwright

    theme_css = ""
    theme_path = (ORA_HOME / "server" / "static" / "ora-visual-compiler"
                  / "ora-visual-theme.css")
    if theme_path.exists():
        theme_css = theme_path.read_text()

    svg_n = png_n = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(device_scale_factor=2, color_scheme="dark",
                          viewport={"width": width + 120, "height": 1400})
        page.goto(f"{server}/", wait_until="networkidle", timeout=60000)
        page.wait_for_function(
            "window.OraVisualCompiler && window.OraVisualCompiler.compileWithNav",
            timeout=30000)
        # The app page doesn't link the compiler's theme stylesheet (the
        # visual pane styles artifacts through its own layer), so inject
        # it — without it every SVG fill defaults to black. color_scheme
        # 'dark' above activates the theme's dark-mode variable block, so
        # rasters match Ora's dark UI.
        page.evaluate(
            """(css) => {
                const s = document.createElement('style');
                s.id = 'campaign-visual-theme';
                s.textContent = css;
                document.head.appendChild(s);
            }""", theme_css)
        for vi, env in enumerate(envelopes, start=1):
            (out_dir / f"visual-{vi}.json").write_text(env)
            result = page.evaluate(
                """async (envJson) => {
                    let env;
                    try { env = JSON.parse(envJson); }
                    catch (e) { return {svg: '', errors: ['envelope_parse: ' + e.message]}; }
                    let r;
                    try {
                        r = window.OraVisualCompiler.compileWithNav(env);
                        if (r && typeof r.then === 'function') r = await r;
                    } catch (e) { return {svg: '', errors: ['compile_threw: ' + e.message]}; }
                    return {
                        svg: (r && r.svg) || '',
                        errors: ((r && r.errors) || []).map(
                            e => (e.code || '') + ': ' + String(e.message || '').slice(0, 200)),
                    };
                }""", env)
            if not result.get("svg"):
                print(f"    [visual] compile failed: "
                      f"{'; '.join(result.get('errors') or [])[:300]}")
                continue
            (out_dir / f"visual-{vi}.svg").write_text(result["svg"])
            svg_n += 1
            ok = page.evaluate(
                """([markup, w]) => {
                    let host = document.getElementById('campaign-raster-host');
                    if (!host) {
                        host = document.createElement('div');
                        host.id = 'campaign-raster-host';
                        host.style.cssText =
                            'position:fixed;left:0;top:0;z-index:999999;' +
                            'background:var(--ora-vis-bg, #1A1E24);' +
                            'padding:24px;width:max-content;';
                        document.body.appendChild(host);
                    }
                    host.innerHTML = markup;
                    const svg = host.querySelector('svg');
                    if (!svg) return false;
                    svg.style.width = w + 'px';
                    svg.style.height = 'auto';
                    svg.style.display = 'block';
                    return true;
                }""", [result["svg"], width])
            if ok:
                page.wait_for_timeout(200)  # font/layout settle
                el = page.query_selector("#campaign-raster-host")
                if el:
                    el.screenshot(path=str(out_dir / f"visual-{vi}.png"))
                    png_n += 1
        b.close()
    return svg_n, png_n


# ─── The sweep ────────────────────────────────────────────────────────────


def run_sweep(args) -> int:
    techniques = select_techniques(parse_corpus(Path(args.corpus)), args.techniques)
    pipelines = [p.strip() for p in args.pipelines.split(",") if p.strip()]
    unknown = [p for p in pipelines if p not in ALL_PIPELINES]
    if unknown:
        raise SystemExit(f"unknown pipeline(s): {unknown}; choose from {ALL_PIPELINES}")

    if not SNAPSHOT_PATH.exists():
        raise SystemExit("run `campaign_run.py bake-configs` first")
    snapshot = json.loads(SNAPSHOT_PATH.read_text())
    flagship = (snapshot.get("single_pass_flagship") or {}).get("model_id")
    flagship_pricing = (snapshot.get("single_pass_flagship") or {}).get("pricing")
    flagship_ep = resolve_flagship_endpoint(flagship) if "single-pass" in pipelines else None

    # Preflight: server reachable + campaign configs present.
    if any(p in ORA_PIPELINES for p in pipelines):
        try:
            urllib.request.urlopen(f"{args.server}/api/model-registry/reach/status",
                                   timeout=10)
        except Exception as exc:
            raise SystemExit(f"Ora server not reachable at {args.server} ({exc}) — ./start.sh first")
        for p in pipelines:
            cfg = ORA_PIPELINES.get(p)
            if cfg and not (CONFIGURATIONS_DIR / f"{cfg}.json").exists():
                raise SystemExit(f"missing {cfg}.json — run bake-configs")
        # The server's Router singleton caches routing-config AND named
        # configurations from process start / first use. Campaign configs
        # baked or edited after that are invisible until a reload — twice
        # observed live: 'claude-code:… not registered' (subscription
        # endpoints), and a whole-lane fidelity wipeout where the server
        # executed a previous bake's optimum models against the current
        # file's expected set. Always poke before any Ora-lane sweep.
        _poke_router_reload(args.server)

    # Fidelity expectations per Ora pipeline: only these models may
    # record usage during a run. Loaded once up front so a config edit
    # mid-sweep can't shift the goalposts between runs.
    expected_primaries = {
        p: load_expected_primaries(cfg) for p, cfg in ORA_PIPELINES.items()
        if p in pipelines
    }

    # Rate map for API-equivalent pricing of lanes the registry can't
    # price (subscription endpoints): union of every config's bake-time
    # pricing snapshot + the flagship's.
    rate_map: dict = {}
    for c in (snapshot.get("configs") or {}).values():
        for mid, rate in (c.get("pricing") or {}).items():
            if rate:
                rate_map[mid] = rate
    fp = (snapshot.get("single_pass_flagship") or {})
    if fp.get("pricing"):
        rate_map[fp.get("model_id")] = fp["pricing"]

    subscription_lanes = (
        {p for p in pipelines if p in SUBSCRIPTION_PIPELINES}
        if snapshot.get("premium_mode") == "subscription" else set())
    # Single-pass follows the premium execution mode: a claude-code
    # flagship makes the control lane a subscription lane too (serial +
    # window-paced, API-equivalent pricing).
    if (flagship or "").startswith("claude-code:") and "single-pass" in pipelines:
        subscription_lanes.add("single-pass")

    done = load_manifest()
    force = bool(getattr(args, "force_rerun", False))
    todo = [(t, p) for t in techniques for p in pipelines
            if force or (done.get((t.id, p)) or {}).get("status") != "ok"]
    total = len(techniques) * len(pipelines)
    print(f"[run] {len(techniques)} techniques × {len(pipelines)} pipelines = "
          f"{total} captures ({total - len(todo)} already complete, {len(todo)} to run)")
    if args.limit:
        todo = todo[: args.limit]
        print(f"[run] --limit {args.limit} → running {len(todo)} this invocation")
    if args.dry_run:
        for t, p in todo:
            print(f"  would run: {t.id} × {p}")
        return 0

    ctx = {
        "flagship_ep": flagship_ep,
        "flagship_pricing": flagship_pricing,
        "expected_primaries": expected_primaries,
        "rate_map": rate_map,
        "subscription_lanes": subscription_lanes,
    }

    # Lane-parallel execution: each pipeline is a lane; lanes always run
    # concurrently (they hit disjoint providers); --concurrency adds
    # workers WITHIN the API lanes. Subscription lanes stay at 1 worker —
    # the rolling rate window is the bottleneck, and pacing handles it.
    import queue as _queue
    import threading as _threading

    by_pipe: dict[str, list] = {}
    for t, p in todo:
        by_pipe.setdefault(p, []).append(t)
    lanes = {}
    for p, items in by_pipe.items():
        q: _queue.Queue = _queue.Queue()
        for t in items:
            q.put(t)
        workers = 1 if p in subscription_lanes else max(1, args.concurrency)
        lanes[p] = (q, min(workers, len(items)))

    progress = {"done": 0, "failures": 0, "lock": _threading.Lock()}

    def _lane_worker(pipe: str, q: "_queue.Queue") -> None:
        while True:
            try:
                tech = q.get_nowait()
            except _queue.Empty:
                return
            ok = _execute_capture(tech, pipe, args, ctx)
            with progress["lock"]:
                progress["done"] += 1
                if not ok:
                    progress["failures"] += 1
                done_n, fail_n = progress["done"], progress["failures"]
            print(f"[run] progress {done_n}/{len(todo)}"
                  + (f" ({fail_n} failed)" if fail_n else ""), flush=True)

    threads = []
    for pipe, (q, workers) in lanes.items():
        for _ in range(workers):
            th = _threading.Thread(target=_lane_worker, args=(pipe, q),
                                   daemon=True)
            th.start()
            threads.append(th)
    for th in threads:
        th.join()

    failures = progress["failures"]
    print(f"[run] complete — {len(todo) - failures} ok, {failures} failed "
          f"(failed pairs re-run on the next invocation)")
    return 1 if failures else 0


def _wait_for_subscription_window(max_wait_s: int = 86400) -> None:
    """Block until the Claude subscription accepts calls again. Probes
    with a tiny Haiku completion; on a rate-limit reply, sleeps 15 min
    and re-probes (the 5-hour rolling windows and weekly caps mean a
    long sweep simply pauses instead of failing or falling back to the
    metered API)."""
    import subprocess
    cli = os.environ.get("ORA_CLAUDE_CODE_BIN") or "claude"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    waited = 0
    while True:
        try:
            r = subprocess.run(
                [cli, "-p", "--model", "claude-haiku-4-5",
                 "--output-format", "text", "--tools", ""],
                input="Reply with exactly: OK", capture_output=True,
                text=True, timeout=180, env=env)
            blob = ((r.stdout or "") + (r.stderr or "")).lower()
            if r.returncode == 0 and "limit" not in blob:
                return
        except Exception:
            pass
        if waited >= max_wait_s:
            raise RuntimeError(
                f"subscription window did not reopen within {max_wait_s}s")
        print("    [pacing] subscription window closed — sleeping 15 min",
              flush=True)
        time.sleep(900)
        waited += 900


def _execute_capture(tech: Technique, pipe: str, args, ctx: dict) -> bool:
    """One (technique, pipeline) capture: run, fidelity-gate, persist,
    manifest. Returns True on an accepted capture. Thread-safe (manifest
    writes locked; per-capture output dir is exclusive to this pair)."""
    out_dir = CAPTURES_DIR / tech.id / pipe
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"[{pipe}] {tech.id}"
    print(f"{tag} …", flush=True)
    started = time.time()
    rec = {"technique": tech.id, "kind": tech.kind, "mode": tech.intended_mode,
           "pipeline": pipe, "at": _now_iso(), "attempts": 0}
    last_err = None
    for attempt in (1, 2):  # one retry on transient failure
        rec["attempts"] = attempt
        try:
            if pipe in ctx["subscription_lanes"]:
                # Don't start a long pipeline run into a closed window.
                _wait_for_subscription_window()
            if pipe == "single-pass":
                sp = single_pass_call(ctx["flagship_ep"], tech.prompt)
                cost = price_single_pass(sp, ctx["flagship_pricing"])
                (out_dir / "answer.md").write_text(sp["text"])
                (out_dir / "cost.json").write_text(json.dumps({
                    "model_id": sp["model_id"], "via": sp["via"],
                    "prompt_tokens": sp["prompt_tokens"],
                    "completion_tokens": sp["completion_tokens"],
                    "pricing_per_million": ctx["flagship_pricing"],
                    "total_cost_usd": cost}, indent=2))
                rec.update(status="ok", cost_usd=cost,
                           prompt_tokens=sp["prompt_tokens"],
                           completion_tokens=sp["completion_tokens"],
                           visuals=0, via=sp["via"],
                           executed_models={sp["served_model"]: 1})
                if sp["via"] == "claude-code-subscription":
                    rec["cost_basis"] = "api_equivalent"
            else:
                conv_id = f"campaign-{tech.id}-{pipe}"
                res = run_ora_pipeline(args.server, ORA_PIPELINES[pipe],
                                       tech, conv_id, timeout=args.timeout)
                # Fidelity gate BEFORE the capture counts: every model
                # that recorded usage must be a configured primary — a
                # 429/throttle cascade to a fallback model, or a silently
                # failed step, invalidates the run.
                fidelity = verify_trace_fidelity(
                    res["trace_dir"], ctx["expected_primaries"][pipe])
                rec["executed_models"] = fidelity["executed"]
                rec["fidelity_warnings"] = fidelity["warnings"]
                if not fidelity["ok"]:
                    raise RuntimeError(
                        "fidelity violations: "
                        + json.dumps(fidelity["violations"][:6]))
                prose, envelopes = extract_visuals(res["text"])
                (out_dir / "answer.md").write_text(prose)
                n_png = 0
                if envelopes:
                    try:
                        _, n_png = render_visuals_browser(
                            args.server, envelopes, out_dir)
                    except ImportError:
                        # No Playwright: jsdom SVG only, no raster.
                        for vi, env in enumerate(envelopes, start=1):
                            (out_dir / f"visual-{vi}.json").write_text(env)
                            render_svg(env, out_dir / f"visual-{vi}.svg")
                    except Exception as vex:
                        print(f"{tag} [visual] browser render failed "
                              f"({str(vex)[:200]}); jsdom SVG fallback")
                        for vi, env in enumerate(envelopes, start=1):
                            (out_dir / f"visual-{vi}.json").write_text(env)
                            render_svg(env, out_dir / f"visual-{vi}.svg")
                cost = read_trace_cost(res["trace_dir"])
                if cost["total_cost_usd"] is None:
                    equiv = price_usage_records(res["trace_dir"],
                                                ctx["rate_map"])
                    if equiv is not None:
                        cost["total_cost_usd"] = equiv
                        rec["cost_basis"] = "api_equivalent"
                if res["trace_dir"]:
                    src = Path(res["trace_dir"]) / "cost-summary.json"
                    if src.exists():
                        (out_dir / "cost.json").write_text(src.read_text())
                rec.update(status="ok", trace_dir=res["trace_dir"],
                           cost_usd=cost["total_cost_usd"],
                           prompt_tokens=cost["prompt_tokens"],
                           completion_tokens=cost["completion_tokens"],
                           visuals=len(envelopes), visuals_png=n_png)
            rec["wall_seconds"] = round(time.time() - started, 1)
            append_manifest(rec)
            cost_str = (f"${rec.get('cost_usd'):.4f}" if rec.get("cost_usd")
                        else "unpriced")
            if rec.get("cost_basis") == "api_equivalent":
                cost_str += " (API-equivalent)"
            executed = rec.get("executed_models") or {}
            models_str = (" — models: " + ", ".join(
                f"{m}×{n}" for m, n in sorted(executed.items()))
                ) if executed else ""
            warn_str = (f" — {len(rec.get('fidelity_warnings') or [])} warning(s)"
                        if rec.get("fidelity_warnings") else "")
            print(f"{tag} ok in {rec['wall_seconds']}s — {cost_str}, "
                  f"{rec.get('visuals', 0)} visual(s){models_str}{warn_str}")
            return True
        except Exception as exc:
            last_err = str(exc)[:400]
            print(f"{tag} attempt {attempt} failed: {last_err}")
            # A rate-limited subscription mid-run: wait for the window
            # before the retry instead of burning it immediately.
            if "rate-limited" in last_err and pipe in ctx["subscription_lanes"]:
                try:
                    _wait_for_subscription_window()
                except RuntimeError:
                    break
            time.sleep(5)
    rec.update(status="failed", error=last_err,
               wall_seconds=round(time.time() - started, 1))
    append_manifest(rec)
    return False


# ─── Aggregation: cost tables ────────────────────────────────────────────


def aggregate() -> dict:
    done = load_manifest()
    snapshot = json.loads(SNAPSHOT_PATH.read_text()) if SNAPSHOT_PATH.exists() else {}
    per: dict = {}
    for (tech, pipe), rec in done.items():
        if rec.get("status") != "ok":
            continue
        row = per.setdefault(pipe, {"runs": 0, "prompt_tokens": 0,
                                    "completion_tokens": 0, "cost_usd": 0.0,
                                    "unpriced_runs": 0, "visuals": 0,
                                    "wall_seconds": 0.0,
                                    "api_equivalent_runs": 0})
        row["runs"] += 1
        row["prompt_tokens"] += rec.get("prompt_tokens") or 0
        row["completion_tokens"] += rec.get("completion_tokens") or 0
        row["visuals"] += rec.get("visuals") or 0
        row["wall_seconds"] += rec.get("wall_seconds") or 0
        if rec.get("cost_basis") == "api_equivalent":
            row["api_equivalent_runs"] += 1
        if rec.get("cost_usd") is None:
            row["unpriced_runs"] += 1
        else:
            row["cost_usd"] += rec["cost_usd"]

    grand = {"runs": sum(r["runs"] for r in per.values()),
             "cost_usd": round(sum(r["cost_usd"] for r in per.values()), 4),
             "prompt_tokens": sum(r["prompt_tokens"] for r in per.values()),
             "completion_tokens": sum(r["completion_tokens"] for r in per.values())}
    summary = {"generated_at": _now_iso(), "per_pipeline": per, "grand_total": grand}
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    (CAMPAIGN_DIR / "cost-summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lines = ["# Campaign cost summary", "",
             f"_Generated {summary['generated_at']}_", ""]
    # Per-configuration model + rate descriptions (capture-time snapshot).
    cfgs = (snapshot.get("configs") or {})
    if cfgs:
        lines += ["## Configurations (models + per-1M rates at bake time)", ""]
        for cname, c in cfgs.items():
            models = c.get("models") or {}
            lines.append(f"### {cname}")
            lines.append("")
            lines.append("| slot | model | $/1M in | $/1M out |")
            lines.append("|---|---|---|---|")
            for slot in ("big1", "big2", "fast1", "fast2", "small"):
                m = models.get(slot)
                pr = (c.get("pricing") or {}).get(m) or {}
                lines.append(
                    f"| {slot} | {m or '—'} | "
                    f"{pr.get('input_per_million_usd', '—')} | "
                    f"{pr.get('output_per_million_usd', '—')} |")
            lines.append("")
        fp = snapshot.get("single_pass_flagship") or {}
        if fp:
            pr = fp.get("pricing") or {}
            lines += [f"### single-pass flagship", "",
                      f"`{fp.get('model_id')}` — "
                      f"${pr.get('input_per_million_usd', '?')}/1M in, "
                      f"${pr.get('output_per_million_usd', '?')}/1M out", ""]
    lines += ["## Per-pipeline totals", "",
              "| pipeline | runs | prompt tok | completion tok | visuals | wall (min) | cost (USD) | **$ / run** | **min / run** |",
              "|---|---|---|---|---|---|---|---|---|"]
    any_equiv = False
    for pipe in ALL_PIPELINES:
        r = per.get(pipe)
        if not r:
            continue
        unpriced = f" ({r['unpriced_runs']} unpriced)" if r["unpriced_runs"] else ""
        equiv = "†" if r.get("api_equivalent_runs") else ""
        any_equiv = any_equiv or bool(equiv)
        per_run_cost = r["cost_usd"] / r["runs"] if r["runs"] else 0.0
        per_run_min = r["wall_seconds"] / 60 / r["runs"] if r["runs"] else 0.0
        lines.append(
            f"| {pipe}{equiv} | {r['runs']} | {r['prompt_tokens']:,} | "
            f"{r['completion_tokens']:,} | {r['visuals']} | "
            f"{r['wall_seconds']/60:.1f} | ${r['cost_usd']:.4f}{unpriced} | "
            f"**${per_run_cost:.4f}** | **{per_run_min:.1f}** |")
    per_run_grand = grand["cost_usd"] / grand["runs"] if grand["runs"] else 0.0
    lines += ["",
              f"**Grand total: {grand['runs']} runs — ${grand['cost_usd']:.4f}** "
              f"({grand['prompt_tokens']:,} prompt + {grand['completion_tokens']:,} "
              f"completion tokens) — **${per_run_grand:.4f} per run**", ""]
    if any_equiv:
        lines += ["† executed on the Claude subscription via Claude Code "
                  "(zero marginal dollars); cost shown is the API-equivalent "
                  "price of the tokens consumed.", ""]
    (CAMPAIGN_DIR / "cost-summary.md").write_text("\n".join(lines))
    print(f"[aggregate] → {CAMPAIGN_DIR / 'cost-summary.md'}")
    return summary


# ─── Capture document ────────────────────────────────────────────────────

DOC_PIPELINE_ORDER = [
    ("premium", "Premium (Ora, gear 4)"),
    ("qwen9b", "Qwen 3.5 9B (Ora, gear 4 — single 9B model)"),
    ("optimum", "Optimum (Ora, gear 4)"),
    ("optimum-plus", "Optimum+ (Ora, gear 4 — flagship consolidator)"),
    ("single-pass", "Single-pass flagship (bare model, no harness)"),
]


def render_doc(corpus_path: Path) -> Path:
    techniques = parse_corpus(corpus_path)
    done = load_manifest()
    kind_label = {"mode": "Analysis mode", "visual": "Visual tool", "lens": "Lens"}
    lines = ["# Comparative Evaluation Campaign — captures", "",
             f"_Assembled {_now_iso()}. One section per technique: the prime "
             f"prompt, then the four pipeline answers. Visuals are embedded "
             f"as PNG (SVG + envelope JSON sit alongside in captures/)._", ""]
    included = 0
    for tech in techniques:
        recs = {p: done.get((tech.id, p)) for p, _ in DOC_PIPELINE_ORDER}
        if not any((r or {}).get("status") == "ok" for r in recs.values()):
            continue
        included += 1
        lines += [f"## `{tech.id}` — {kind_label.get(tech.kind, tech.kind)} "
                  f"(mode: `{tech.intended_mode}`)", "",
                  f"> {tech.prompt}", ""]
        for pipe, label in DOC_PIPELINE_ORDER:
            rec = recs.get(pipe)
            if not rec or rec.get("status") != "ok":
                lines += [f"### {label}", "", "_not captured_", ""]
                continue
            cost = rec.get("cost_usd")
            meta = (f"{rec.get('prompt_tokens', 0):,} in / "
                    f"{rec.get('completion_tokens', 0):,} out tokens · "
                    + (f"${cost:.4f}" if cost is not None else "unpriced")
                    + f" · {rec.get('wall_seconds', 0):.0f}s")
            lines += [f"### {label}", "", f"_{meta}_", ""]
            cap = CAPTURES_DIR / tech.id / pipe
            answer = cap / "answer.md"
            if answer.exists():
                lines += [answer.read_text().strip(), ""]
            for png in sorted(cap.glob("visual-*.png")):
                rel = png.relative_to(CAMPAIGN_DIR)
                lines += [f"![{tech.id} visual]({rel})", ""]
        lines.append("---")
        lines.append("")
    out = CAMPAIGN_DIR / "campaign-capture.md"
    out.write_text("\n".join(lines))
    print(f"[render-doc] {included} technique sections → {out}")
    return out


# ─── CLI ─────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Comparative Evaluation Campaign runner.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("bake-configs", help="Bake campaign-premium/-optimum/-qwen9b + pricing snapshot.")
    sp.add_argument("--no-rebake", action="store_true",
                    help="Copy the presets as-is instead of re-baking them first.")
    sp.add_argument("--premium", choices=("api", "subscription"), default="api",
                    help="Premium lane execution: 'api' (picker-baked, metered) "
                         "or 'subscription' (Opus 4.8 big + Haiku 4.5 fast/small "
                         "via the local Claude Code CLI on your subscription; "
                         "cost tables show API-equivalent pricing).")
    sp.set_defaults(func=lambda a: (bake_configs(
        rebake_presets=not a.no_rebake, premium_mode=a.premium), 0)[1])

    sp = sub.add_parser("list", help="Parse the corpus; print counts + ids.")
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("run", help="Execute the sweep (resumable).")
    sp.add_argument("--techniques", default="all",
                    help="'all' | 'some' (12-technique sampler) | comma-separated ids")
    sp.add_argument("--pipelines", default=",".join(ALL_PIPELINES))
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.add_argument("--server", default=DEFAULT_SERVER)
    sp.add_argument("--timeout", type=int, default=2400, help="per-run seconds")
    sp.add_argument("--limit", type=int, default=0, help="cap runs this invocation")
    sp.add_argument("--concurrency", type=int, default=1,
                    help="workers WITHIN each API lane (lanes always run in "
                         "parallel; subscription lanes stay at 1 — the rate "
                         "window is their bottleneck).")
    sp.add_argument("--force-rerun", action="store_true",
                    help="Ignore completed manifest entries for the selected "
                         "scope (re-capture after a config change).")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=run_sweep)

    sp = sub.add_parser("aggregate", help="Cost tables from the manifest.")
    sp.set_defaults(func=lambda a: (aggregate(), 0)[1])

    sp = sub.add_parser("render-doc", help="Assemble the capture document.")
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.set_defaults(func=lambda a: (render_doc(Path(a.corpus)), 0)[1])

    sp = sub.add_parser("all", help="bake-configs → run → aggregate → render-doc.")
    sp.add_argument("--techniques", default="all")
    sp.add_argument("--pipelines", default=",".join(ALL_PIPELINES))
    sp.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    sp.add_argument("--server", default=DEFAULT_SERVER)
    sp.add_argument("--timeout", type=int, default=2400)
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--concurrency", type=int, default=1)
    sp.add_argument("--force-rerun", action="store_true")
    sp.add_argument("--premium", choices=("api", "subscription"), default="api")
    sp.set_defaults(func=cmd_all)

    return p


def cmd_list(args) -> int:
    techs = parse_corpus(Path(args.corpus))
    by_kind: dict = {}
    for t in techs:
        by_kind.setdefault(t.kind, []).append(t.id)
    for kind in ("mode", "visual", "lens"):
        ids = by_kind.get(kind, [])
        print(f"{kind}: {len(ids)}")
        for i in ids:
            print(f"  {i}")
    print(f"total: {len(techs)}")
    missing_some = [s for s in SOME_SUBSET if s not in {t.id for t in techs}]
    if missing_some:
        print(f"WARNING: 'some' subset ids not in corpus: {missing_some}")
    return 0


def cmd_all(args) -> int:
    bake_configs(premium_mode=getattr(args, "premium", "api"))
    rc = run_sweep(args)
    aggregate()
    render_doc(Path(args.corpus))
    return rc


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
