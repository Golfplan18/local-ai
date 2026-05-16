#!/usr/bin/env python3
"""
Local AI Orchestrator — boot.py
Implements the full pipeline: Step 1 (Prompt Cleanup + Mode Selection) →
Step 2 (Context Assembly) → Gear-appropriate analysis → Output routing.
All behavioral decisions live in natural language specs. This file is mechanical plumbing.
"""
from __future__ import annotations

import os
import sys
import json
import re
import glob as globmod
from datetime import datetime

# Paths
WORKSPACE = os.path.expanduser("~/ora/")
BOOT_MD = os.path.join(WORKSPACE, "boot/boot.md")
ENDPOINTS_JSON = os.path.join(WORKSPACE, "config/endpoints.json")
ROUTING_CONFIG_JSON = os.path.join(WORKSPACE, "config/routing-config.json")
TOOLS_DIR = os.path.join(WORKSPACE, "orchestrator/tools/")
FRAMEWORKS_DIR = os.path.join(WORKSPACE, "frameworks/book/")
MODES_DIR = os.path.join(WORKSPACE, "modes/")
MODULES_DIR = os.path.join(WORKSPACE, "modules/")

# Phase 9 — Pre-routing pipeline architecture files (~/ora/architecture/).
# These nine files replace the retired Mode Classification Directory's
# intent-classification flow. See `~/ora/CLAUDE.md` Decision K and
# `~/ora/architecture/pre-routing-pipeline.md` for the full spec.
ARCHITECTURE_DIR = os.path.join(WORKSPACE, "architecture/")
PIPELINE_FILE = os.path.join(ARCHITECTURE_DIR, "pre-routing-pipeline.md")
TERRITORIES_FILE = os.path.join(ARCHITECTURE_DIR, "territories.md")
DISAMBIG_GUIDE_FILE = os.path.join(ARCHITECTURE_DIR, "disambiguation-style-guide.md")
SIGNAL_REGISTRY_FILE = os.path.join(ARCHITECTURE_DIR, "signal-vocabulary-registry.md")
WITHIN_TREES_FILE = os.path.join(ARCHITECTURE_DIR, "within-territory-trees.md")
CROSS_ADJ_FILE = os.path.join(ARCHITECTURE_DIR, "cross-territory-adjacency.md")
TEMPLATE_FILE = os.path.join(ARCHITECTURE_DIR, "mode-template.md")
LENS_SPEC_FILE = os.path.join(ARCHITECTURE_DIR, "lens-library-specification.md")

sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))

# Tool imports with graceful fallback
TOOLS_AVAILABLE = True
try:
    from web_search import web_search
    from file_ops import file_read, file_write
    from knowledge_search import knowledge_search
    from browser_open import browser_open
    from credential_store import credential_store
    from browser_evaluate import browser_evaluate
    from api_evaluate import api_evaluate
    from dispatcher import dispatch as dispatcher_dispatch, reset_consecutive, cleanup_all
except ImportError as e:
    print(f"[WARNING] Tool import failed: {e}")
    TOOLS_AVAILABLE = False

# RAG engine (Phase 8 + Phase 5.6 ranker) — optional, falls back to basic ChromaDB if unavailable
RAG_ENGINE_AVAILABLE = False
try:
    from rag_engine import RAGEngine, BudgetSignal, assemble_ranked_context
    RAG_ENGINE_AVAILABLE = True
except ImportError:
    pass

# Resilience (Phase 14) — optional, graceful degradation
RESILIENCE_AVAILABLE = False
try:
    from resilience import (
        get_degradation_path, format_degradation_signal,
        should_release_kv_cache, release_kv_cache,
    )
    RESILIENCE_AVAILABLE = True
except ImportError:
    pass

# Step 2.5 web-supplement loop (anticipatory web RAG). Optional: when
# unavailable, run_step2_context_assembly emits a 'web_supplement_skipped'
# signal and the pipeline proceeds with vault-only RAG.
WEB_SUPPLEMENT_AVAILABLE = False
try:
    from web_supplement import (
        assemble_web_supplemental_context,
        DEFAULT_MAX_GAPS as _WEB_SUPP_DEFAULT_MAX_GAPS,
        DEFAULT_MAX_ATTEMPTS_PER_GAP as _WEB_SUPP_DEFAULT_MAX_ATTEMPTS,
        DEFAULT_SLOT as _WEB_SUPP_DEFAULT_SLOT,
    )
    WEB_SUPPLEMENT_AVAILABLE = True
except ImportError:
    pass

# Pipeline forensic trace — per-turn structured record of every step's
# inputs and outputs. Writes to ``~/ora/data/pipeline-traces/<conv>/<ts>/``.
# Every helper is defensive (try/except wrapped); trace failure never
# breaks the pipeline. See ``Paper — Subtle-Calculation Errors in LLM
# Pipelines`` for the full contract.
PIPELINE_TRACE_AVAILABLE = False
try:
    import pipeline_trace
    PIPELINE_TRACE_AVAILABLE = True
except ImportError:
    pipeline_trace = None  # type: ignore

# Visual-output validation (WP-1.6) — optional, no-op if schemas unavailable.
# Scans the model response for ``ora-visual`` fenced JSON blocks, runs
# server-side schema validation + adversarial T-rule / LLM-prior-inversion
# review, and suppresses visuals with Critical findings (prose is still
# delivered). When a response contains no visual blocks, the hook is a
# no-op — zero impact on text-only pipelines.
VISUAL_HOOK_AVAILABLE = False
try:
    from visual_adversarial import process_response as _visual_process_response
    VISUAL_HOOK_AVAILABLE = True
except ImportError:
    pass


def _run_visual_hook(response: str, context_pkg: dict | None) -> str:
    """Run the WP-1.6 visual validator + adversarial pass over the response.

    If the response has no ``ora-visual`` fenced blocks, returns unchanged.
    If any block has Critical findings (schema failure or adversarial
    block), that block is replaced with a ``[visual … suppressed: …]``
    marker so the client's error channel can surface it while prose
    continues to flow. Diagnostics are stashed on the context_pkg (which
    the server reads for SSE event emission) when possible — never mutated
    invasively; always fail-open.

    The diagnostics are also persisted to the per-turn trace as
    ``step-visual-hook.json`` (fix for silent failure #11: previously the
    visual diagnostics were attached to context_pkg ephemerally; if the
    suppression was wrong, no post-hoc audit was possible because the
    record never landed on disk).
    """
    if not VISUAL_HOOK_AVAILABLE or not response:
        return response
    if "ora-visual" not in response:
        return response
    trace_dir = (context_pkg or {}).get("trace_dir") if isinstance(context_pkg, dict) else None
    try:
        mode = (context_pkg or {}).get("mode_name")
        new_text, diagnostics = _visual_process_response(response, mode=mode)
    except Exception as exc:  # fail-open: never block legitimate prose on a hook bug
        print(f"[visual hook] skipped due to error: {exc}")
        if PIPELINE_TRACE_AVAILABLE and trace_dir:
            pipeline_trace.write_step(trace_dir, "step-visual-hook", {
                "status": "hook_exception",
                "error": str(exc),
                "response_contained_ora_visual_block": True,
            }, markdown=(
                "# Visual Hook — exception\n\n"
                f"`{exc}` — visual hook fail-open; response prose continues unchanged.\n"
            ))
        return response
    if context_pkg is not None:
        context_pkg["visual_diagnostics"] = diagnostics

    if PIPELINE_TRACE_AVAILABLE and trace_dir:
        visuals = (diagnostics or {}).get("visuals") or []
        suppressed = [v for v in visuals if v.get("blocked")]
        pipeline_trace.write_step(trace_dir, "step-visual-hook", {
            "status": "ok",
            "visuals_seen": len(visuals),
            "visuals_suppressed": len(suppressed),
            "diagnostics": diagnostics,
        }, markdown=(
            "# Visual Hook\n\n"
            f"**Visuals seen:** {len(visuals)}  \n"
            f"**Visuals suppressed (Critical findings):** {len(suppressed)}\n\n"
            + ("## Suppressed blocks\n\n" if suppressed else "")
            + "\n".join(
                f"- `{v.get('id') or '?'}` ({v.get('type') or '?'}) — "
                f"validator valid: {(v.get('validator') or {}).get('valid')}; "
                f"adversarial blocks: "
                f"{len(((v.get('adversarial') or {}).get('blocks') or []))}"
                for v in suppressed
            )
            + ("\n" if suppressed else "")
        ))
    return new_text


def _extract_final_response(raw: str) -> str:
    """Extract the final channel content from gpt-oss style responses.
    Strips thinking blocks and channel markers. Falls back to full text."""
    if "<|channel|>final<|message|>" in raw:
        part = raw.split("<|channel|>final<|message|>", 1)[1]
        # Strip trailing special tokens
        for tok in ["<|end|>", "<|return|>", "<|endoftext|>"]:
            part = part.split(tok)[0]
        return part.strip()
    # Strip <think>...</think> blocks (thinking models like Qwen3.5)
    import re
    cleaned = raw
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1]
    # Strip any channel/message tokens and return remaining text
    cleaned = re.sub(r'<\|[^|]+\|>', '', cleaned)
    return cleaned.strip() or raw.strip()


def load_boot_md() -> str:
    try:
        with open(BOOT_MD, "r") as f:
            boot_content = f.read()
    except FileNotFoundError:
        boot_content = "You are a helpful AI assistant. You have no special tools in this session."

    # Load persistent context files
    context_dir = os.path.join(WORKSPACE, "context")
    if os.path.isdir(context_dir):
        context_parts = []
        total_chars = 0
        for fname in sorted(os.listdir(context_dir)):
            if fname.endswith(".md") and fname != "README.md":
                fpath = os.path.join(context_dir, fname)
                try:
                    with open(fpath) as f:
                        content = f.read()
                    total_chars += len(content)
                    context_parts.append(f"\n\n---\n[PERSISTENT CONTEXT: {fname}]\n\n{content}")
                except Exception:
                    pass
        if context_parts:
            boot_content += "".join(context_parts)
        if total_chars > 8000:
            print(f"[WARNING] Context directory contains {total_chars} characters "
                  f"(~{total_chars // 4} tokens). Consider moving large files to the vault.")

    # Universal anti-confabulation directive — appended at load_boot_md level
    # so every code path that loads boot.md gets the directive, not only
    # ``build_system_prompt_for_gear`` callers. Fixes the "universal"-in-name-
    # only gap: ``_direct_stream`` (bypass / catch-all / pending-clarification
    # routes for the chat server), the legacy ``/direct`` command, and the
    # framework / elicitation / resolution-chain paths all load boot.md
    # directly and previously had no anti-confab instruction. The directive
    # is defined later in this module; the forward reference is fine because
    # this function isn't called at module-load time.
    boot_content = boot_content + "\n\n" + _UNIVERSAL_ANTI_CONFABULATION

    return boot_content


def load_endpoints() -> dict:
    try:
        with open(ENDPOINTS_JSON, "r") as f:
            return json.load(f)
    except Exception:
        return {"endpoints": [], "default_endpoint": None}


# --- V2 Router Integration ---
# The router uses routing-config.json (bucket-based priority system).
# Falls back to v1 functions if routing-config.json is not available.

_router_instance = None

def _get_router():
    """Get or create the singleton Router instance."""
    global _router_instance
    if _router_instance is None:
        if os.path.exists(ROUTING_CONFIG_JSON):
            try:
                from router import Router
                _router_instance = Router(config_path=ROUTING_CONFIG_JSON)
            except Exception as e:
                print(f"[Router] Failed to load routing-config.json: {e}. Falling back to v1.")
                _router_instance = False  # Mark as failed, don't retry
        else:
            _router_instance = False
    return _router_instance if _router_instance is not False else None


def reload_router() -> bool:
    """Refresh the singleton Router's in-memory config from disk.

    Called by ``server.py``'s ``/config/routing`` POST handlers after
    the V3 Settings panel autosaves a bucket / pipeline / slot change.
    Without this hook, the singleton Router holds the original config
    in memory until the server is restarted — every panel change is
    deferred-until-restart, which is misleading because the panel
    presents itself as live.

    Behavior:
      * If no Router has been instantiated yet, this is a no-op
        (returns False). The next ``_get_router()`` call will load the
        already-fresh file naturally.
      * If the singleton was marked unavailable (``False`` — load
        failed previously), this clears the marker and a future
        ``_get_router()`` call will retry the load.
      * Otherwise, calls ``router.reload()``. On reload failure the
        prior in-memory config is preserved (so the running pipeline
        doesn't degrade) and we return False.

    Returns True on a successful reload, False otherwise.
    """
    global _router_instance
    if _router_instance is None:
        return False
    if _router_instance is False:
        # Previous load failed; let the next _get_router() retry.
        _router_instance = None
        return False
    try:
        return bool(_router_instance.reload())
    except Exception as exc:
        print(f"[Router] reload_router failed: {exc}")
        return False


def get_active_endpoint(config: dict) -> dict | None:
    """Returns a general-purpose endpoint. Uses v2 router if available."""
    router = _get_router()
    if router:
        ep = router.resolve_utility_slot("step1_cleanup", "interactive")
        if ep:
            return router._to_v1_endpoint(ep)
    # V1 fallback
    slot = config.get("slot_assignments", {}).get("breadth")
    endpoints = config.get("endpoints", [])
    if slot:
        for e in endpoints:
            if e.get("name") == slot:
                return e
    default = config.get("default_endpoint")
    active = [e for e in endpoints if e.get("status") == "active"]
    if not active:
        return None
    if default:
        for e in active:
            if e.get("name") == default:
                return e
    return active[0]


def get_slot_endpoint(config: dict, slot: str, context: str = "interactive") -> dict | None:
    """Return the endpoint for a named slot. Uses v2 router if available.

    ``context`` selects the operational profile from routing-config.json:

      - ``interactive`` (default) — local + browser + api transports
        eligible. Used by chat / on-demand analysis where browser
        responses are acceptable.
      - ``autonomous`` — local transports only. Used by unattended
        pipelines (article generation, scheduled runs) where browser
        endpoints would either need a Playwright session or stall.
      - ``agent`` — agent-mode resolution (local-mid + free buckets).

    Most callers leave this at the default. The article-generation
    pipeline passes ``autonomous`` so model_dispatch resolves to a
    local model rather than the browser-fronted premium endpoint.
    """
    router = _get_router()
    if router:
        # Map v1 slot names to v2 resolution
        if slot in ("sidebar", "step1_cleanup", "rag_planner", "classification"):
            ep = router.resolve_utility_slot(slot, context)
        elif slot in ("consolidator", "consolidation"):
            ep = router.resolve_post_analysis_slot("consolidation", context)
        elif slot in ("evaluator", "verification"):
            ep = router.resolve_post_analysis_slot("verification", context)
        elif slot in ("depth", "breadth"):
            # For direct slot lookups outside gear execution, resolve at Gear 3
            # (Gear 4 resolution happens through resolve_gear4_endpoints)
            result = router.resolve_gear(3, context)
            ep = result.get(slot) if result else None
        else:
            ep = router.resolve_utility_slot("step1_cleanup", context)

        if ep:
            return router._to_v1_endpoint(ep)

    # V1 fallback
    slot_assignments = config.get("slot_assignments", {})
    model_id = slot_assignments.get(slot)
    if not model_id:
        return get_active_endpoint(config)
    endpoints = config.get("endpoints", [])
    for e in endpoints:
        if e.get("name") == model_id:
            return e
    return get_active_endpoint(config)


def resolve_gear4_endpoints(config: dict, execution_context: str = "interactive") -> tuple:
    """Resolve Gear 4 endpoints with bucket-based routing.

    Returns (depth_endpoint, breadth_endpoint, parallel_safe: bool).
    Uses v2 router if available, otherwise falls back to v1 logic.
    """
    router = _get_router()
    context = execution_context if execution_context in ("interactive", "agent") else "agent"

    if router:
        result = router.execute(requested_gear=4, context=context)

        if result.gear == 4:
            depth_ep = result.assignments.get("depth")
            breadth_ep = result.assignments.get("breadth")
            return depth_ep, breadth_ep, result.parallel_safe
        elif result.gear == 3:
            # Router downgraded to Gear 3 — return the endpoints but mark as not parallel safe
            # The caller (run_gear4) will fall back to run_gear3
            depth_ep = result.assignments.get("depth")
            breadth_ep = result.assignments.get("breadth")
            return depth_ep, breadth_ep, False
        else:
            return None, None, False

    # V1 fallback
    depth_ep = get_slot_endpoint(config, "depth")
    breadth_ep = get_slot_endpoint(config, "breadth")

    op_context = config.get("operational_context", {})
    allowed_types = set(op_context.get(execution_context, ["local"]))

    overrides = config.get("gear4_overrides", {})
    endpoints_by_name = {e["name"]: e for e in config.get("endpoints", [])}

    for slot_name, slot_key in [("depth", "depth"), ("breadth", "breadth")]:
        override = overrides.get(slot_name, {})
        if not override.get("enabled"):
            continue
        ep_name = override.get("endpoint")
        ep = endpoints_by_name.get(ep_name)
        if not ep:
            continue
        ep_type = ep.get("type", "local")
        if ep_type not in allowed_types:
            continue
        if slot_key == "depth":
            depth_ep = ep
        else:
            breadth_ep = ep

    depth_local = (depth_ep or {}).get("type") == "local"
    breadth_local = (breadth_ep or {}).get("type") == "local"
    parallel_safe = not (depth_local and breadth_local)

    return depth_ep, breadth_ep, parallel_safe


# --- WP-4.2 — capability-conditional vision routing ---------------------
#
# When the user uploads an image via /chat/multipart (WP-3.3), the pipeline
# carries an absolute ``image_path`` under ``context_pkg``. Two branches:
#
#   1. The downstream model (the one that will actually answer) is
#      ``vision_capable: true`` — no-op. It will receive the image directly
#      via its native vision channel; the path already rides along in
#      context_pkg.
#   2. The downstream model is text-only (local MLX, most small models) —
#      route the image through a vision-capable extractor FIRST (description +
#      spatial_representation JSON), then hand the extraction text to the
#      downstream model as additional context.
#
# WP-4.2 implements the SELECTION GATE only. The extractor call itself is
# WP-4.3 (prompt + response parsing). This function records which extractor
# would run on ``context_pkg['vision_extractor_selected']`` so WP-4.3 can
# wire the call without re-running bucket selection.
#
# Fallback precedence when no vision-capable model exists anywhere:
#   preferred_extractor_bucket → fallback_extractor_bucket → no_vision_available
# WP-4.4 (UX) surfaces ``no_vision_available=True`` to the user.

def _endpoint_lookup_by_id(routing_config: dict) -> dict:
    """Build {id: endpoint-dict} for quick vision_capable lookups."""
    return {ep.get("id"): ep for ep in routing_config.get("endpoints", []) if ep.get("id")}


def _pick_vision_extractor(routing_config: dict, bucket_name: str) -> dict | None:
    """Return the first enabled + active + vision_capable endpoint in ``bucket_name``.

    Defensive read: endpoints missing the ``vision_capable`` field are treated
    as text-only (``False``) so unknown models can never silently slip through.
    """
    if not bucket_name:
        return None
    lookup = _endpoint_lookup_by_id(routing_config)
    ids = routing_config.get("buckets", {}).get(bucket_name, [])
    for ep_id in ids:
        ep = lookup.get(ep_id)
        if not ep:
            continue
        if not ep.get("enabled", False):
            continue
        if ep.get("status") != "active":
            continue
        if not ep.get("vision_capable", False):
            continue
        return ep
    return None


# Slot-entry prefixes that produce vision-input-capable endpoints when used as
# the vision_extraction.slot source. OpenRouter image-generation models accept
# image conditioning by construction; pure text-to-image generators
# (local-diffusers / Stability / Replicate text2img) cannot, and a plain
# endpoint id has to be looked up against the endpoints[] vision_capable flag.
_VISION_EXTRACTION_SKIP_SLOT_ENTRIES = frozenset({
    "local-diffusers",
    "stability",
    "replicate",
    "civitai-hector-lora-v1",
})


def _endpoint_from_slot_entry(entry: str, routing_config: dict) -> dict | None:
    """Resolve one ``slots.<slot>.{preferred,fallback}`` entry into a
    vision-extractor endpoint dict, or ``None`` when the entry isn't
    image-input-capable.

    Entries can take several shapes (see ``slots`` in routing-config.json):

      * ``"openrouter:<model_id>"`` — synthesizes an API endpoint pointed
        at OpenRouter with the given model. Treated as vision-capable
        because OpenRouter image-generation models accept image
        conditioning by construction.
      * ``"<endpoint id>"`` — looks the id up in ``routing_config.endpoints``;
        returns the endpoint dict iff its ``vision_capable`` flag is true.
      * ``"local-diffusers"`` / ``"replicate"`` / ``"stability"`` /
        ``"civitai-hector-lora-v1"`` — pure text→image generators or
        engine identifiers. Not vision-input-capable. Skipped.

    Used by ``route_for_image_input`` when ``vision_extraction.slot`` is
    configured.
    """
    if not entry or not isinstance(entry, str):
        return None
    if entry in _VISION_EXTRACTION_SKIP_SLOT_ENTRIES:
        return None

    if entry.startswith("openrouter:"):
        model_id = entry.split(":", 1)[1].strip()
        if not model_id:
            return None
        return {
            "id":             entry,
            "type":           "api",
            "service":        "openrouter",
            "model":          model_id,
            "display_name":   model_id,
            "vision_capable": True,
            "status":         "active",
            "enabled":        True,
        }

    # Plain endpoint id — look up in routing-config.endpoints[].
    lookup = _endpoint_lookup_by_id(routing_config)
    ep = lookup.get(entry)
    if not ep:
        return None
    if not ep.get("enabled", False):
        return None
    if ep.get("status") != "active":
        return None
    if not ep.get("vision_capable", False):
        return None
    return ep


def _pick_vision_extractor_from_slot(routing_config: dict,
                                      slot_name: str) -> tuple[dict | None, list[str]]:
    """Walk ``slots.<slot_name>.preferred`` then ``.fallback`` and return
    the first entry that resolves to a vision-input-capable endpoint.

    Returns ``(endpoint_dict_or_None, walked_entries)``. ``walked_entries``
    is the list of entry strings inspected — useful in the trace for
    explaining why a selection landed on a particular fallback.
    """
    walked: list[str] = []
    if not slot_name:
        return None, walked
    slots_cfg = routing_config.get("slots") or {}
    slot_cfg = slots_cfg.get(slot_name) or {}
    chain = []
    pref = slot_cfg.get("preferred")
    if pref:
        chain.append(pref)
    chain.extend(slot_cfg.get("fallback") or [])
    for entry in chain:
        walked.append(entry)
        ep = _endpoint_from_slot_entry(entry, routing_config)
        if ep is not None:
            return ep, walked
    return None, walked


def route_for_image_input(context_pkg: dict,
                          requested_model: dict | None,
                          model_registry: dict | None = None,
                          routing_config: dict | None = None) -> tuple:
    """Capability-conditional routing gate for image input (WP-4.2).

    If ``context_pkg`` carries an ``image_path``:
      * If ``requested_model['vision_capable']`` is truthy, pass the image
        directly (no-op — the image path already rides along on context_pkg).
      * Else, pick an extractor from
        ``routing_config['vision_extraction']['preferred_extractor_bucket']``;
        if none available, try ``fallback_extractor_bucket``; else set
        ``context_pkg['no_vision_available'] = True`` and log.
        Record the selected extractor on
        ``context_pkg['vision_extractor_selected']`` (dict with ``id``,
        ``bucket``, ``display_name``). WP-4.3 will call it.
      * ``context_pkg['vision_extraction_result']`` is left absent; WP-4.3
        populates it after it runs the extraction prompt.

    If no ``image_path``, this is a no-op: returns the requested_model
    unchanged with an unmodified context_pkg.

    Parameters
    ----------
    context_pkg : dict
        The assembled pipeline context package. Mutated in place.
    requested_model : dict | None
        The endpoint that WOULD answer if this function did nothing. May be
        None when the caller hasn't resolved a slot yet — in that case only
        the image_path presence is checked and the extractor slot is still
        recorded (so WP-4.3 can run extraction even when downstream slot
        isn't resolved yet).
    model_registry : dict | None
        Optional full ``models.json`` dict. Present for forward compatibility
        with WP-4.3 which may need per-model vision metadata beyond what the
        routing-config endpoint dict carries. Not required for selection.
    routing_config : dict | None
        Parsed ``routing-config.json``. When omitted, loads from the standard
        path.

    Returns
    -------
    tuple (effective_model, context_pkg)
        ``effective_model`` is always the originally-requested model. The
        extractor (when selected) does NOT replace the downstream model — it
        runs first and feeds context to it. ``context_pkg`` is the same dict
        passed in (mutated) for caller convenience.
    """
    if context_pkg is None:
        return requested_model, context_pkg

    image_path = context_pkg.get("image_path")
    if not image_path:
        # No image — strictly a no-op. Do NOT set any fields; downstream
        # code must see an unchanged context_pkg.
        return requested_model, context_pkg

    # Load routing_config lazily so callers can pass None in tests.
    if routing_config is None:
        try:
            with open(ROUTING_CONFIG_JSON, "r") as f:
                routing_config = json.load(f)
        except Exception as e:
            print(f"[visual-routing] routing-config load failed: {e}. Skipping vision gate.")
            return requested_model, context_pkg

    vision_cfg = routing_config.get("vision_extraction", {}) or {}
    if not vision_cfg.get("enabled", True):
        # Explicitly disabled — skip the gate, keep image_path as a bare
        # reference for text-only models. WP-4.4 decides what the UX does.
        return requested_model, context_pkg

    # Branch 1: downstream model is already vision-capable — direct pass.
    if requested_model and requested_model.get("vision_capable", False):
        context_pkg["vision_extractor_selected"] = None
        context_pkg["vision_direct_pass"] = True
        return requested_model, context_pkg

    # Branch 2: downstream is text-only (or unresolved). Select extractor.
    #
    # New (preferred) path: ``vision_extraction.slot`` names a slot in the
    # ``slots`` block (typically ``image_generates``) whose preferred /
    # fallback chain is reused as the extractor chain. Image-generation
    # models accept image conditioning by construction so they double as
    # vision-input-capable extractors — this avoids carving out a separate
    # ``vision_extractors`` bucket that has to be kept in sync manually.
    #
    # Legacy path: ``preferred_extractor_bucket`` /
    # ``fallback_extractor_bucket`` continue to work as fallbacks when no
    # slot is configured OR when slot resolution finds no eligible entry
    # (e.g. the slot's chain is entirely text→image generators that can't
    # read images).
    extractor: dict | None = None
    used_source = ""

    slot_name = vision_cfg.get("slot", "")
    if slot_name:
        slot_ep, walked = _pick_vision_extractor_from_slot(
            routing_config, slot_name,
        )
        if slot_ep is not None:
            extractor = slot_ep
            used_source = f"slot:{slot_name}"

    # Legacy bucket fallback: either no slot configured, or the slot's
    # chain produced no vision-input-capable entry.
    if extractor is None:
        preferred = vision_cfg.get("preferred_extractor_bucket", "")
        fallback = vision_cfg.get("fallback_extractor_bucket", "")
        extractor = _pick_vision_extractor(routing_config, preferred)
        used_source = f"bucket:{preferred}" if extractor else ""
        if not extractor and fallback and fallback != preferred:
            extractor = _pick_vision_extractor(routing_config, fallback)
            used_source = f"bucket:{fallback}" if extractor else ""

    if extractor:
        context_pkg["vision_extractor_selected"] = {
            "id":           extractor.get("id"),
            "source":       used_source,
            "display_name": extractor.get("display_name", extractor.get("id", "")),
        }
        context_pkg["vision_direct_pass"] = False
        print(
            f"[visual-routing] extractor selected: {extractor.get('id')} "
            f"(source={used_source}) for downstream "
            f"{(requested_model or {}).get('id', 'unresolved')}"
        )

        # WP-4.3 — actually call the extractor with the image and a
        # structured prompt. Stash the parsed spatial_representation on
        # ``context_pkg['vision_extraction_result']`` so
        # ``build_system_prompt_for_gear`` can serialize it into the text
        # prompt for downstream text-only models. Fail-open: extraction
        # errors never block the pipeline; WP-4.4 decides how to surface
        # them to the user.
        try:
            from visual_extraction import extract_spatial_from_image
            extraction = extract_spatial_from_image(image_path, extractor)
            # Store the parsed dict (or None) under vision_extraction_result.
            context_pkg["vision_extraction_result"] = extraction.spatial_representation
            # Keep the richer metadata nearby so operators / WP-4.4 can
            # introspect confidence and parse errors without re-running.
            context_pkg["vision_extraction_meta"] = {
                "extractor_model": extraction.extractor_model,
                "confidence": extraction.confidence,
                "parse_errors": list(extraction.parse_errors),
            }
            if extraction.spatial_representation is not None:
                print(
                    f"[visual-extraction] model={extraction.extractor_model} "
                    f"confidence={extraction.confidence:.2f} "
                    f"entities={len(extraction.spatial_representation.get('entities', []))}"
                )
            else:
                print(
                    f"[visual-extraction] FAILED model={extraction.extractor_model} "
                    f"errors={len(extraction.parse_errors)} "
                    f"first={(extraction.parse_errors or [''])[0][:120]!r}"
                )
        except Exception as exc:
            print(f"[visual-extraction] skipped due to unexpected error: {exc}")
            context_pkg["vision_extraction_result"] = None

        return requested_model, context_pkg

    # Branch 3: no vision-capable model anywhere.
    context_pkg["no_vision_available"] = True
    context_pkg["vision_extractor_selected"] = None
    context_pkg["vision_direct_pass"] = False
    print(
        "[visual-routing] WARNING: image input received but no vision-capable "
        f"model found in buckets '{preferred}' or '{fallback}'. "
        "Falling back to text-only path — WP-4.4 will surface a manual-trace "
        "prompt to the user."
    )
    return requested_model, context_pkg


def load_framework(name: str) -> str:
    """Load a framework specification from frameworks/book/.

    Returns the file contents on success. When the file is missing, returns
    a sentinel ``[Framework not found: ...]`` string AND prints a stderr
    warning so the silent fallback (universal scaffolding silently missing
    from the analytical step's system prompt) becomes visible. Parallels
    ``load_mode``'s behaviour for the same reason.
    """
    path = os.path.join(FRAMEWORKS_DIR, name)
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        print(
            f"[load_framework] framework file not found: {name} "
            f"— pipeline steps that depend on this scaffolding will run "
            f"without the universal contract",
            file=sys.stderr,
            flush=True,
        )
        return f"[Framework not found: {name}]"


def parse_framework_picker_metadata(framework_id: str) -> dict | None:
    """V3 Phase 2 — parse Display Name + Display Description from a framework.

    Reads ``frameworks/book/{framework_id}.md`` and extracts the values from the
    ``## Display Name`` and ``## Display Description`` sections. Returns ``None``
    when either section is absent (pipeline-internal frameworks like F-* and
    Phase A do not declare these and are silently excluded from the picker).

    Returns::

        {
            "id": str,                    # filename stem (no .md)
            "display_name": str,          # 60-char-limit picker title
            "display_description": str,   # 500-char-limit picker body
            "category": str,              # "standard" | "user-created" | "one-off"
        }

    Category resolution for V3 Phase 2: every shipped framework is "standard".
    User-created and one-off categories land when those provenance sources
    exist (Process Formalization F-Design output / framework-generated
    one-offs). The ``provenance`` field of a registry entry is the long-term
    source of truth; for now we tag everything in frameworks/book/ as standard.
    """
    path = os.path.join(FRAMEWORKS_DIR, framework_id + ".md")
    try:
        with open(path, "r") as f:
            text = f.read()
    except FileNotFoundError:
        return None

    display_name = _first_paragraph(_extract_section(text, "Display Name"))
    display_description = _first_paragraph(
        _extract_section(text, "Display Description"))
    if not display_name or not display_description:
        return None

    return {
        "id": framework_id,
        "display_name": display_name,
        "display_description": display_description,
        "category": "standard",
    }


def _first_paragraph(body: str) -> str:
    """Take only the first paragraph from a section body.

    A "paragraph" here ends at the first blank line. ``_extract_section``
    grabs everything between two ``## `` headings, which can include trailing
    italics or separator content for frameworks that put intro material
    between the display sections and the next heading. The picker's Display
    Name and Display Description are intentionally short single-paragraph
    fields, so we trim to the first paragraph and drop the rest.
    """
    if not body:
        return ""
    # Normalise leading/trailing whitespace, then split on the first blank line.
    chunks = re.split(r'\n\s*\n', body.strip(), maxsplit=1)
    return chunks[0].strip() if chunks else ""


def list_pickable_frameworks() -> list[dict]:
    """Scan frameworks/book/ and return picker-ready metadata for each
    framework that declares Display Name and Display Description.

    Pipeline-internal frameworks (F-* and Phase A — Prompt Cleanup) do not
    declare these sections and are automatically excluded. Sort order is
    alphabetical by ``display_name`` within each category. The picker UI is
    free to re-group; this function is the data source.
    """
    if not os.path.isdir(FRAMEWORKS_DIR):
        return []

    rows: list[dict] = []
    for entry in os.listdir(FRAMEWORKS_DIR):
        if not entry.endswith(".md") or entry.endswith(".bak.md"):
            continue
        # Skip .bak files conservatively (`.bak.YYYY-MM-DD.md` and similar).
        if ".bak" in entry:
            continue
        framework_id = entry[:-3]  # strip .md
        meta = parse_framework_picker_metadata(framework_id)
        if meta is not None:
            rows.append(meta)

    rows.sort(key=lambda r: (r["category"], r["display_name"].lower()))
    return rows


def parse_framework_input_spec(framework_id: str) -> dict | None:
    """V3 Input Handling Phase 7 — read a framework's input declaration.

    Returns a dict with both the structured Setup Questions (deterministic
    path) and the free-form INPUT CONTRACT (LLM fallback). Either, both, or
    neither may be present; callers decide which to use:

        {
            "id": str,
            "setup_questions": [
                {"name": str, "required": bool, "description": str},
                ...
            ] | None,
            "input_contract": str | None,
        }

    ``setup_questions`` is parsed from `## Setup Questions` when present.
    Each `### question name` block is captured as one entry; the body's
    first sentence flags `Required.` or `Optional.` (case-insensitive).
    The remaining body becomes the description shown to the user.

    ``input_contract`` is the raw text under `## INPUT CONTRACT`. The LLM
    gap analyzer consumes this when no structured questions are declared.

    Returns ``None`` if the framework file does not exist.
    """
    path = os.path.join(FRAMEWORKS_DIR, framework_id + ".md")
    try:
        with open(path, "r") as f:
            text = f.read()
    except FileNotFoundError:
        return None

    setup_questions = _parse_setup_questions(text)
    input_contract = _extract_section(text, "INPUT CONTRACT") or None

    return {
        "id": framework_id,
        "setup_questions": setup_questions,
        "input_contract": input_contract,
    }


def _parse_setup_questions(text: str) -> list[dict] | None:
    """Extract the `## Setup Questions` section into a list of question
    dicts. Returns ``None`` when the section is absent.

    Each question is a `### Name` heading whose body's first sentence
    declares ``Required.`` or ``Optional.``. Anything after that flag is
    the description shown to the user.
    """
    section = _extract_section(text, "Setup Questions")
    if not section:
        return None

    questions: list[dict] = []
    # Split on H3 boundaries inside the section
    for match in re.finditer(
        r'^### (.+?)\n(.*?)(?=^### |\Z)', section, re.MULTILINE | re.DOTALL,
    ):
        name = match.group(1).strip()
        body = match.group(2).strip()
        if not body:
            questions.append({"name": name, "required": True, "description": ""})
            continue
        # Case-insensitive flag detection at start of body
        flag_match = re.match(r'\s*(required|optional)\s*\.\s*', body, re.IGNORECASE)
        if flag_match:
            required = flag_match.group(1).lower() == "required"
            description = body[flag_match.end():].strip()
        else:
            # No explicit flag — default to required to be safe.
            required = True
            description = body
        questions.append({
            "name": name,
            "required": required,
            "description": description,
        })

    return questions if questions else None


def load_mode(mode_name: str) -> str:
    """Load a mode file from modes/.

    Returns the file contents on success, empty string when the file does
    not exist. Missing files are surfaced to stderr (and to the pipeline
    trace via ``record_missing_mode_file`` when the caller has wired a
    trace_dir) so the silent "mode dispatched but file is empty" failure
    class (#3 / #8 in the silent-failure catalogue) becomes visible.
    """
    if not mode_name:
        return ""
    path = os.path.join(MODES_DIR, f"{mode_name}.md")
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        print(
            f"[load_mode] mode file not found: {mode_name}.md "
            f"— the dispatch will run with empty per-step instructions",
            flush=True,
        )
        return ""


# ---------------------------------------------------------------------------
# Phase 9 — Decision E: educational parenthetical dispatch announcement
# ---------------------------------------------------------------------------

def format_dispatch_announcement(plain_language_description: str,
                                 educational_name: str) -> str:
    """Format dispatch announcement per Decision E educational parenthetical convention.

    Format: ``"plain language *(named technique)*"``

    Example:
        format_dispatch_announcement(
            "I'll work backward from a future failure",
            "premortem"
        )
        # => "I'll work backward from a future failure *(premortem)*"
    """
    return f"{plain_language_description} *({educational_name})*"


def compose_dispatch_announcement(mode_id: str, user_prompt: str) -> str:
    """Compose the full Stage 4 dispatch announcement for a mode.

    Sources the educational technique name from the mode file, composes a
    plain-language description from the mode's canonical/educational name,
    and returns the formatted announcement per Decision E.

    Returns a fallback that names the mode in plain English when the mode
    file is absent or the educational_name field is missing.
    """
    edu_name = load_educational_name(mode_id) or mode_id.replace("-", " ")
    description = _compose_plain_language_description(mode_id, user_prompt, edu_name)
    return format_dispatch_announcement(description, edu_name)


def _compose_plain_language_description(mode_id: str, user_prompt: str,
                                        edu_name: str) -> str:
    """Build the plain-language description preceding the parenthetical.

    Maps each mode_id to a short opening verb phrase that names what the
    mode will do, then references the user's input concretely. Falls back
    to a generic phrasing when no specific template is registered.
    """
    template = _DISPATCH_DESCRIPTION_TEMPLATES.get(mode_id)
    artifact_label = _detect_artifact_label(user_prompt)
    if template:
        return template.format(artifact=artifact_label)
    return f"I'll work through your {artifact_label} using {edu_name.split('(')[0].strip()}"


_DISPATCH_DESCRIPTION_TEMPLATES = {
    "steelman-construction": "I'll make the strongest case for this {artifact}",
    "red-team": "I'll push back hard on this {artifact}",
    "balanced-critique": "I'll weigh both sides of this {artifact}",
    "benefits-analysis": "I'll lay out what this {artifact} would gain you",
    "coherence-audit": "I'll check whether this {artifact} holds together",
    "frame-audit": "I'll surface the frame this {artifact} is using",
    "argument-audit": "I'll work through this {artifact} from frame to logic",
    "propaganda-audit": "I'll look at this {artifact} as rhetoric",
    "cui-bono": "I'll trace who benefits from this {artifact}",
    "boundary-critique": "I'll surface whose voices this {artifact} leaves out",
    "wicked-problems": "I'll work through the tangled structure of this {artifact}",
    "decision-clarity": "I'll prepare a decision-maker brief on this {artifact}",
    "stakeholder-mapping": "I'll map the stakeholders in this {artifact}",
    "conflict-structure": "I'll lay out the structure of the conflict in this {artifact}",
    "constraint-mapping": "I'll walk through the trade-offs of this {artifact}",
    "decision-under-uncertainty": "I'll work through the uncertainty around this {artifact}",
    "multi-criteria-decision": "I'll weigh the criteria for this {artifact}",
    "decision-architecture": "I'll build the full decision picture for this {artifact}",
    "root-cause-analysis": "I'll trace the root cause behind this {artifact}",
    "systems-dynamics-causal": "I'll surface the feedback structure in this {artifact}",
    "causal-dag": "I'll build a formal causal model of this {artifact}",
    "process-tracing": "I'll trace step by step how this {artifact} unfolded",
    "differential-diagnosis": "I'll do a quick read on which explanation fits this {artifact} best",
    "competing-hypotheses": "I'll lay out evidence against each of these explanations",
    "bayesian-hypothesis-network": "I'll work through these hypotheses with priors",
    "consequences-and-sequel": "I'll think through the likely consequences of this {artifact}",
    "probabilistic-forecasting": "I'll put probability estimates on how this {artifact} could unfold",
    "scenario-planning": "I'll sketch alternative futures around this {artifact}",
    "pre-mortem-action": "I'll work backward from how this {artifact} could fail",
    "wicked-future": "I'll work through the entangled futures around this {artifact}",
    "pre-mortem-fragility": "I'll stress-test this {artifact} for fragility",
    "fragility-antifragility-audit": "I'll audit this {artifact} for what helps and hurts under stress",
    "failure-mode-scan": "I'll scan this {artifact} for failure modes",
    "fault-tree": "I'll build a fault tree for this {artifact}",
    "paradigm-suspension": "I'll suspend the assumptions in this {artifact}",
    "frame-comparison": "I'll compare the frames at play in this {artifact}",
    "worldview-cartography": "I'll map the worldviews in this {artifact}",
    "deep-clarification": "I'll clarify what's meant by the key terms in this {artifact}",
    "conceptual-engineering": "I'll work on sharpening this concept",
    "relationship-mapping": "I'll map the relationships in this {artifact}",
    "interest-mapping": "I'll map the interests around this {artifact}",
    "principled-negotiation": "I'll prep this negotiation around interests, options, and standards",
    "third-side": "I'll work this conflict from the third-side mediator stance",
    "quick-orientation": "I'll give you a quick read on this {artifact}",
    "terrain-mapping": "I'll map the terrain of this {artifact}",
    "domain-induction": "I'll induct you into this domain",
    "spatial-reasoning": "I'll work through the spatial structure of this {artifact}",
    "compositional-dynamics": "I'll read the compositional dynamics in this {artifact}",
    "place-reading-genius-loci": "I'll read the place-character of this {artifact}",
    "information-density": "I'll audit the information density of this {artifact}",
    "mechanism-understanding": "I'll explain how this {artifact} works",
    "process-mapping": "I'll map the process behind this {artifact}",
    "strategic-interaction": "I'll analyze the strategic interaction at play in this {artifact}",
    "passion-exploration": "I'll explore this passion area with you",
}


def _detect_artifact_label(user_prompt: str) -> str:
    """Detect a short noun phrase to name what the user supplied.

    Matches against common artifact words in the prompt; falls back to
    "input" so the description never fails. Plain-English only — no jargon.
    """
    if not user_prompt:
        return "input"
    p = user_prompt.lower()
    for label, words in [
        ("op-ed", ["op-ed", "op ed", "opinion piece"]),
        ("article", ["article"]),
        ("argument", ["argument"]),
        ("policy", ["policy", "zoning", "regulation"]),
        ("plan", ["plan", "rollout", "launch"]),
        ("decision", ["decision", "choice"]),
        ("memo", ["memo", "brief"]),
        ("proposal", ["proposal"]),
        ("strategy", ["strategy", "strategic"]),
        ("design", ["design"]),
        ("situation", ["situation", "dispute", "conflict"]),
        ("question", ["question"]),
        ("concept", ["concept", "term", "meaning of"]),
    ]:
        if any(w in p for w in words):
            return label
    return "input"


def load_educational_name(mode_id: str) -> str | None:
    """Read the ``educational_name`` YAML field from a mode file.

    Returns ``None`` if the mode file is missing or the field is absent.
    Used by ``format_dispatch_announcement`` to pair plain-language phrasing
    with the technique name learners can search for.
    """
    mode_path = os.path.join(MODES_DIR, f"{mode_id}.md")
    if not os.path.exists(mode_path):
        return None
    with open(mode_path, "r") as f:
        content = f.read()
    match = re.search(r'^educational_name:\s*(.+?)$', content, re.MULTILINE)
    return match.group(1).strip() if match else None


# ---------------------------------------------------------------------------
# Phase 9 — Pre-routing pipeline: Stage 1 (Pre-Analysis Filter)
# Spec: ~/ora/architecture/pre-routing-pipeline.md §Stage 1
# ---------------------------------------------------------------------------

# Bypass triggers split into two priority levels:
#   - STRONG_BYPASS: always wins over analytical signals (system commands,
#     prior-conversation references, factual lookups)
#   - WEAK_BYPASS: loses to strong analytical signals (greetings, ack)
STRONG_BYPASS_TRIGGERS = [
    # factual / lookup — concrete single-fact questions
    "what time", "what's the date", "what's the time",
    "what time is it", "what's today", "what day is it",
    "what's today's date", "what year is it", "what's the year",
    "what is the capital", "what's the capital",
    # prior-conversation / system-meta references
    "what did you just say", "what did i just say",
    "what did you say earlier", "what did i ask",
    "repeat that", "say that again", "say it again",
    "remind me of", "remind me what",
    "how many tokens", "how many tokens does",
    # prior-conversation references
    "what did you say", "earlier you said", "remind me what",
    "show me the previous", "repeat what you", "what was your previous",
    # system commands and service requests
    "/help", "/?", "save this conversation", "convert this pdf",
    # mechanical translation / formatting
    "translate this", "spell-check", "spell check",
    "fix the spelling", "fix the grammar", "fix the typo",
    # explicit user opt-out from the analytical pipeline
    "don't analyze", "do not analyze", "no analysis",
    "skip the analysis", "no need to analyze", "without analysis",
]

WEAK_BYPASS_TRIGGERS = [
    # greetings + acknowledgements
    "hello", "hi ", "hi!", "hi.", "hey ", "hey!", "hey.",
    "good morning", "good afternoon", "good evening",
    "thanks", "thank you", "yes, go ahead", "yes go ahead",
]

# Backwards-compat: combined list still used by tests.
BYPASS_TRIGGERS = STRONG_BYPASS_TRIGGERS + WEAK_BYPASS_TRIGGERS

# Negation markers used for ±3-token window detection around analytical signals.
NEGATION_MARKERS = {"not", "don't", "dont", "no", "without", "skip", "never"}


def _normalize_for_match(text: str) -> str:
    """Lowercase, normalize dashes/punctuation, collapse whitespace.

    Hyphens and en-dashes become spaces so that "cui-bono" matches "cui bono"
    and "red-team" matches "red team". Other punctuation is stripped so it
    doesn't break word-boundary detection.
    """
    if not text:
        return ""
    out = text.lower()
    # Treat hyphens/dashes as word separators so "red-team" → "red team"
    out = out.replace("-", " ").replace("—", " ").replace("–", " ")
    return " ".join(out.split())


def _signal_present(prompt: str, signal: str) -> bool:
    """Check whether the signal appears in the prompt with proper word boundaries.

    Word-boundary matching is required for ALL signals — short and
    multi-word alike. Substring-only matching was previously used for
    multi-word triggers under the assumption of low collision risk; that
    assumption is false in practice. The trigger ``"no analysis"`` was
    matching inside ``"cui bono analysis"`` (``b[ono analysis]``),
    silently bypassing every cui-bono prompt to the direct-response path
    and starving the analytical pipeline. Word boundaries on both ends
    eliminate this entire failure class.
    """
    if not signal or not prompt:
        return False
    norm_prompt = _normalize_for_match(prompt)
    norm_signal = _normalize_for_match(signal)
    pattern = r"(?:^|[^a-z0-9])" + re.escape(norm_signal) + r"(?:$|[^a-z0-9])"
    return bool(re.search(pattern, norm_prompt))


def _is_negated(prompt: str, signal: str) -> bool:
    """Check if a negation marker appears within ±3 tokens of the signal,
    within the same sentence.

    Implementation: locate the signal in the prompt, look at the 3 tokens
    before and 3 tokens after, but truncate the window at sentence
    boundaries (``.``, ``?``, ``!``) so a negation in a quoted or earlier
    sentence does not falsely negate the signal. Case-insensitive.

    Example: in ``"tariffs don't cause inflation. does this argument hold up?"``
    the "don't" in the first sentence does NOT negate the AAA-trigger
    "does this argument hold up" in the second sentence.
    """
    norm_prompt = _normalize_for_match(prompt)
    norm_signal = _normalize_for_match(signal)
    idx = norm_prompt.find(norm_signal)
    if idx < 0:
        return False
    pre_text = norm_prompt[:idx]
    post_text = norm_prompt[idx + len(norm_signal):]

    # Truncate at sentence boundaries — negation does not cross . ? !
    last_pre_boundary = max(pre_text.rfind('.'), pre_text.rfind('?'),
                            pre_text.rfind('!'))
    if last_pre_boundary >= 0:
        pre_text = pre_text[last_pre_boundary + 1:]
    first_post_boundary = min(
        (pos for pos in (post_text.find('.'), post_text.find('?'),
                          post_text.find('!')) if pos >= 0),
        default=-1,
    )
    if first_post_boundary >= 0:
        post_text = post_text[:first_post_boundary]

    pre_tokens = pre_text.split()[-3:] if pre_text else []
    post_tokens = post_text.split()[:3] if post_text else []
    window = pre_tokens + post_tokens
    return any(t.strip(",.!?;:") in NEGATION_MARKERS for t in window)


# Phase 9 — Code-side signal alias augmentation. Adds high-frequency
# corpus-expected phrases that the canonical signal vocabulary registry
# doesn't yet cover. These are read alongside the registry and contribute
# strong matches the same way registry entries do. Vault registry updates
# are the canonical fix; this dict is the orchestrator-side bridge until
# those land.
_PHASE9_SIGNAL_ALIASES: list[dict] = [
    # T15 — Steelman / stance evaluation
    {"signal": "make the case for",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "steelman-construction", "confidence_weight": "strong"},
    {"signal": "make the strongest case",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "steelman-construction", "confidence_weight": "strong"},
    {"signal": "strongest case for",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "steelman-construction", "confidence_weight": "strong"},
    {"signal": "red team this",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "red-team", "confidence_weight": "strong"},
    {"signal": "push back hard",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "red-team", "confidence_weight": "strong"},
    {"signal": "tear apart",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "red-team", "confidence_weight": "strong"},

    # T6/T7 — pre-mortem
    {"signal": "what could go wrong",
     "territory": "T6-future-exploration",
     "mode": "pre-mortem-action", "confidence_weight": "strong"},
    {"signal": "pre mortem",
     "territory": "T6-future-exploration",
     "mode": "pre-mortem-action", "confidence_weight": "strong"},
    {"signal": "premortem",
     "territory": "T6-future-exploration",
     "mode": "pre-mortem-action", "confidence_weight": "strong"},
    {"signal": "stress test",
     "territory": "T7-risk-and-failure-analysis",
     "mode": "pre-mortem-fragility", "confidence_weight": "strong"},

    # T8 — Stakeholder mapping
    {"signal": "map the stakeholders",
     "territory": "T8-stakeholder-conflict",
     "mode": "stakeholder-mapping", "confidence_weight": "strong"},
    {"signal": "stakeholders in this",
     "territory": "T8-stakeholder-conflict",
     "mode": "stakeholder-mapping", "confidence_weight": "strong"},
    {"signal": "all the stakeholders",
     "territory": "T8-stakeholder-conflict",
     "mode": "stakeholder-mapping", "confidence_weight": "strong"},

    # T9 — Frame comparison
    {"signal": "compare these frames",
     "territory": "T9-paradigm-and-assumption-examination",
     "mode": "frame-comparison", "confidence_weight": "strong"},
    {"signal": "compare how",
     "territory": "T9-paradigm-and-assumption-examination",
     "mode": "frame-comparison", "confidence_weight": "weak"},
    {"signal": "frame this issue",
     "territory": "T9-paradigm-and-assumption-examination",
     "mode": "frame-comparison", "confidence_weight": "strong"},
    {"signal": "frame this issue differently",
     "territory": "T9-paradigm-and-assumption-examination",
     "mode": "frame-comparison", "confidence_weight": "strong"},

    # T1 — Coherence audit
    {"signal": "argumentative coherence",
     "territory": "T1-argumentative-artifact-examination",
     "mode": "coherence-audit", "confidence_weight": "strong"},
    {"signal": "audit this argument",
     "territory": "T1-argumentative-artifact-examination",
     "mode": "coherence-audit", "confidence_weight": "strong"},
    {"signal": "audit fully",
     "territory": "T1-argumentative-artifact-examination",
     "mode": "argument-audit", "confidence_weight": "strong"},

    # T2 — Cui bono variations
    {"signal": "cui bono this",
     "territory": "T2-interest-and-power",
     "mode": "cui-bono", "confidence_weight": "strong"},

    # T2 — Decision clarity
    {"signal": "decision clarity document",
     "territory": "T2-interest-and-power",
     "mode": "decision-clarity", "confidence_weight": "strong"},
    {"signal": "decision clarity",
     "territory": "T2-interest-and-power",
     "mode": "decision-clarity", "confidence_weight": "strong"},

    # T3 — Constraint mapping
    {"signal": "trade offs",
     "territory": "T3-decision-under-uncertainty",
     "mode": "constraint-mapping", "confidence_weight": "strong"},
    {"signal": "trade off of",
     "territory": "T3-decision-under-uncertainty",
     "mode": "constraint-mapping", "confidence_weight": "strong"},
    {"signal": "compare and choose",
     "territory": "T3-decision-under-uncertainty",
     "mode": "constraint-mapping", "confidence_weight": "strong"},
    {"signal": "weigh these options",
     "territory": "T3-decision-under-uncertainty",
     "mode": "constraint-mapping", "confidence_weight": "strong"},

    # T4 — Process tracing
    {"signal": "process trace",
     "territory": "T4-causal-investigation",
     "mode": "process-tracing", "confidence_weight": "strong"},

    # T6 — Probabilistic forecasting
    {"signal": "forecast this",
     "territory": "T6-future-exploration",
     "mode": "probabilistic-forecasting", "confidence_weight": "strong"},
    {"signal": "calibrated probability",
     "territory": "T6-future-exploration",
     "mode": "probabilistic-forecasting", "confidence_weight": "strong"},

    # T10 — Conceptual engineering
    {"signal": "engineer the concept",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "strong"},
    {"signal": "engineer this concept",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "strong"},
    {"signal": "engineer it again",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "strong"},
    {"signal": "ameliorative analysis",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "strong"},
    {"signal": "engineer the term",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "strong"},

    # T5 — Quick read on hypotheses
    {"signal": "which of these explanations",
     "territory": "T5-hypothesis-evaluation",
     "mode": "differential-diagnosis", "confidence_weight": "strong"},
    {"signal": "quick read on which",
     "territory": "T5-hypothesis-evaluation",
     "mode": "differential-diagnosis", "confidence_weight": "strong"},

    # T11 — Spatial reasoning (visual gap detection)
    {"signal": "look at how things connect",
     "territory": "T11-structural-relationship-mapping",
     "mode": "spatial-reasoning", "confidence_weight": "weak"},

    # Cross-territory: argumentative coherence on attached PDF
    {"signal": "analyze this attached",
     "territory": "T1-argumentative-artifact-examination",
     "mode": "coherence-audit", "confidence_weight": "weak"},
    {"signal": "analyze this pdf",
     "territory": "T1-argumentative-artifact-examination",
     "mode": "coherence-audit", "confidence_weight": "weak"},

    # Phase 9 round 2 — additional registry coverage
    {"signal": "compare these two frames",
     "territory": "T9-paradigm-and-assumption-examination",
     "mode": "frame-comparison", "confidence_weight": "strong"},
    {"signal": "compare these frames on",
     "territory": "T9-paradigm-and-assumption-examination",
     "mode": "frame-comparison", "confidence_weight": "strong"},
    {"signal": "settle a question about whether",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "strong"},
    {"signal": "is doing what it should",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "weak"},
    {"signal": "as the field uses it",
     "territory": "T10-conceptual-clarification",
     "mode": "conceptual-engineering", "confidence_weight": "weak"},
    {"signal": "look at how things connect",
     "territory": "T11-structural-relationship-mapping",
     "mode": "spatial-reasoning", "confidence_weight": "strong"},
    {"signal": "things connect here",
     "territory": "T11-structural-relationship-mapping",
     "mode": "spatial-reasoning", "confidence_weight": "weak"},
    {"signal": "help me look at",
     "territory": "T1-argumentative-artifact-examination",
     "mode": "coherence-audit", "confidence_weight": "weak"},
]


# Phase 9.5 — SWOT alias added per user request. SWOT analysis maps to
# balanced-critique (T15) since SWOT's structure (strengths, weaknesses,
# opportunities, threats) is essentially balanced critique with a fixed
# four-axis framing.
_PHASE9_SIGNAL_ALIASES.extend([
    {"signal": "causal analysis",
     "territory": "T4-causal-investigation",
     "mode": "root-cause-analysis", "confidence_weight": "strong"},
    {"signal": "swot",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "balanced-critique", "confidence_weight": "strong"},
    {"signal": "swot analysis",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "balanced-critique", "confidence_weight": "strong"},
    {"signal": "strengths weaknesses opportunities threats",
     "territory": "T15-artifact-evaluation-by-stance",
     "mode": "balanced-critique", "confidence_weight": "strong"},
    {"signal": "five whys",
     "territory": "T4-causal-investigation",
     "mode": "root-cause-analysis", "confidence_weight": "strong"},
    {"signal": "5 whys",
     "territory": "T4-causal-investigation",
     "mode": "root-cause-analysis", "confidence_weight": "strong"},
    {"signal": "pestel",
     "territory": "T6-future-exploration",
     "mode": "scenario-planning", "confidence_weight": "strong"},
    {"signal": "porter five forces",
     "territory": "T18-strategic-interaction",
     "mode": "strategic-interaction", "confidence_weight": "strong"},
    {"signal": "five forces",
     "territory": "T18-strategic-interaction",
     "mode": "strategic-interaction", "confidence_weight": "strong"},
    {"signal": "six thinking hats",
     "territory": "T9-paradigm-and-assumption-examination",
     "mode": "frame-comparison", "confidence_weight": "strong"},
    {"signal": "post mortem",
     "territory": "T7-risk-and-failure-analysis",
     "mode": "pre-mortem-fragility", "confidence_weight": "strong"},
    {"signal": "postmortem",
     "territory": "T4-causal-investigation",
     "mode": "root-cause-analysis", "confidence_weight": "strong"},
])


# ---------------------------------------------------------------------------
# Phase 9.5 — Fuzzy framework-name matching (typos, near-misses)
# ---------------------------------------------------------------------------
# Multi-word typo / variant lookup. Maps user phrasings to a canonical
# registry signal. Difflib handles single-word typos; this dict handles
# multi-word phrases where character-level fuzzy matching fails.
_FRAMEWORK_PHRASE_TYPOS = {
    "casual dag": "causal dag",
    "casual analysis": "causal analysis",
    "principle negotiation": "principled negotiation",
    "principle negotiations": "principled negotiation",
    "pre morten": "pre-mortem",
    "pre morten action": "pre-mortem-action",
    "premorten": "pre-mortem",
    "post-mortem": "post mortem",
    "kwee bono": "cui bono",
    "key bono": "cui bono",
    "argument analysis": "argument audit",
    "argument review": "argument audit",
    "stake holder mapping": "stakeholder mapping",
    "frame audit": "frame audit",  # canonical, included for completeness
    "ach analysis": "ach",
    "rca analysis": "rca",
    "wpf analysis": "wicked problems",
    "wicked problems framework": "wicked problems",
    "scenario planning": "scenario planning",
    "what if scenarios": "scenario planning",
    "alternative futures": "scenario planning",
    "decision tree analysis": "decision tree",
    "ev calculation": "expected value",
    "expected value calculation": "expected value",
    "competitive analysis": "boundary critique",
    "five forces analysis": "five forces",
    "porter analysis": "porter five forces",
    "swot analysis": "swot",
    "swat analysis": "swot",  # the user's own typo example
}

# Module-level cache for the parsed signal vocabulary registry. Populated
# lazily on first call and reused across pipeline runs (the registry file
# changes only when vault canonical updates).
_SIGNAL_REGISTRY_CACHE: list[dict] | None = None
_FRAMEWORK_TOKENS_CACHE: set | None = None


def _build_framework_tokens() -> set:
    """Extract single-word framework tokens (≥4 chars) from the registry.

    These are the tokens difflib will fuzzy-match against. We exclude
    short tokens (≤3 chars) because they false-match too easily.
    """
    global _FRAMEWORK_TOKENS_CACHE
    if _FRAMEWORK_TOKENS_CACHE is not None:
        return _FRAMEWORK_TOKENS_CACHE
    tokens: set = set()
    for entry in _load_signal_registry():
        sig = entry["signal"].lower()
        # Single-word framework name
        if " " not in sig and "-" not in sig and len(sig) >= 4:
            tokens.add(sig)
        # Multi-word phrases — keep the first significant word too
        # so e.g., "frame audit" contributes "frame".
    # Manually add a few well-known framework names that may not be in registry
    tokens.update({"swot", "premortem", "postmortem", "pestel"})
    _FRAMEWORK_TOKENS_CACHE = tokens
    return tokens


def _detect_fuzzy_framework_matches(prompt: str,
                                     existing_matches: list[dict]) -> list[dict]:
    """Find prompt tokens that are close fuzzy matches to known framework
    tokens but didn't exact-match in Stage 1. Returns synthetic registry
    entries with a 'fuzzy_typo' annotation so Stage 2 can surface a
    'did you mean?' note.
    """
    import difflib

    framework_tokens = _build_framework_tokens()
    if not framework_tokens:
        return []

    # Build set of tokens already matched (so we don't re-flag exact matches)
    already_matched: set = set()
    for m in existing_matches:
        for tok in m["signal"].lower().split():
            already_matched.add(tok)

    norm = _normalize_for_match(prompt)
    found: list[dict] = []
    seen_typos: set = set()

    # 1. Multi-word phrase typos (lookup dict)
    for typo_phrase, canonical in _FRAMEWORK_PHRASE_TYPOS.items():
        if typo_phrase in norm and canonical not in norm:
            # Find a registry entry matching the canonical phrase
            for entry in _load_signal_registry():
                if entry["signal"].lower() == canonical.lower():
                    if entry["mode"] not in seen_typos:
                        synthetic = dict(entry)
                        synthetic["fuzzy_typo"] = typo_phrase
                        synthetic["fuzzy_canonical"] = canonical
                        found.append(synthetic)
                        seen_typos.add(entry["mode"])
                        break

    # 2. Single-word fuzzy matches (difflib). Cutoff 0.85 + substring check
    # to avoid common English words fuzzy-matching to framework names
    # ("different" → "differential", "casual" → "causal" handled, but
    # "different" vs "differential" rejected because one contains the other).
    for token in norm.split():
        clean = token.strip(",.!?;:'\"()[]{}")
        if len(clean) < 5:  # raised from 4 to reduce false positives
            continue
        if clean in already_matched or clean in framework_tokens:
            continue
        if clean in _COMMON_ENGLISH_NEAR_FRAMEWORKS:
            continue  # ignore common words that look like framework names
        matches = difflib.get_close_matches(clean, framework_tokens,
                                            n=1, cutoff=0.85)
        if not matches:
            continue
        canonical_token = matches[0]
        # Reject if one token is a substring of the other — they're
        # related words, not typos
        if clean in canonical_token or canonical_token in clean:
            continue
        for entry in _load_signal_registry():
            if entry["signal"].lower() == canonical_token:
                if entry["mode"] not in seen_typos:
                    synthetic = dict(entry)
                    synthetic["fuzzy_typo"] = clean
                    synthetic["fuzzy_canonical"] = canonical_token
                    found.append(synthetic)
                    seen_typos.add(entry["mode"])
                    break

    return found


# Common English words that fuzzy-match framework tokens but aren't typos.
# Used to suppress false-positive fuzzy matches.
_COMMON_ENGLISH_NEAR_FRAMEWORKS = {
    "different", "differs", "difference", "differing", "differ",
    "casual", "casually", "casualty",
    "principle", "principles", "principled",  # vs "principled" (canonical)
    "analyses", "analyze", "analyzed", "analyzing",  # vs "analysis"
    "creates", "creating", "creator",  # vs "create"
    "designs", "designed", "designing", "designer",  # vs "design"
    "draft", "drafts", "drafted",  # vs "draft" (canonical)
    "diagnose", "diagnoses", "diagnosed",  # vs "diagnose"
    "produce", "produced", "producing",  # vs "produce"
    "scenarios", "scenario",  # vs "scenarios"
    "salience", "salient",
    "synthesis", "synthesise", "synthesize",
    "design", "designed",
    "framing", "framed",
    "forecast", "forecasts", "forecasted",
    "calibration", "calibrated",
    "mediator", "mediation", "mediated",
}


# ---------------------------------------------------------------------------
# Phase 9.5 — Data-shape detection (Stage 1.5)
# ---------------------------------------------------------------------------
# Detects routing-relevant data structures in the prompt independent of the
# user's phrasing. When the user pastes a list of hypotheses, names a
# stakeholder set, includes a multi-paragraph argument, or attaches an
# image, those signals point to specific modes regardless of what the
# user said in plain English.

def _detect_enumerated_items(prompt: str) -> dict | None:
    """Detect 'X, Y, and Z' or numbered/bulleted enumeration of items.

    Returns {kind: 'hypotheses'|'options'|'parties'|'frames'|'generic',
    count: N, items: [...]} when found.
    """
    if not prompt:
        return None

    # Numbered / lettered enumeration: (1) X (2) Y (3) Z  OR  H1: X H2: Y
    numbered = re.findall(
        r"(?:^|[\(\[])\s*(?:[A-Z]?\d+|[A-Z])\s*[\)\]\:\.]\s*([^,\n\(\)\[\]]{5,80})",
        prompt
    )
    if len(numbered) >= 2:
        return {"kind": _classify_enumeration(numbered, prompt),
                "count": len(numbered), "items": numbered[:5]}

    # Bulleted list (3+ items)
    bulleted = re.findall(r"\n\s*[-*•]\s+([^\n]{5,120})", prompt)
    if len(bulleted) >= 2:
        return {"kind": _classify_enumeration(bulleted, prompt),
                "count": len(bulleted), "items": bulleted[:5]}

    # Comma-separated list with "and" connector (3+ items)
    comma_match = re.search(
        r"(?:explanations?|hypothes[ei]s|options?|alternatives?|"
        r"parties|stakeholders|frames|scenarios|candidates|teams|"
        r"choices)[^:.]*[:\.]\s*([^.\n]+)",
        prompt, re.IGNORECASE
    )
    if comma_match:
        body = comma_match.group(1)
        items = [s.strip() for s in re.split(r",\s*(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+", body)
                 if 4 < len(s.strip()) < 80]
        if len(items) >= 2:
            label_word = comma_match.group(0).split(":")[0].split(".")[0].lower()
            return {"kind": _classify_enumeration(items, prompt, label=label_word),
                    "count": len(items), "items": items[:5]}

    return None


def _classify_enumeration(items: list, prompt: str, label: str = "") -> str:
    """Pick the kind of enumeration based on labels and content."""
    norm = (label + " " + prompt).lower()
    if any(w in norm for w in ["hypothes", "explanation", "candidate"]):
        return "hypotheses"
    if any(w in norm for w in ["option", "alternative", "choice", "vendor"]):
        return "options"
    if any(w in norm for w in ["stakeholder", "party", "team", "group"]):
        return "parties"
    if any(w in norm for w in ["frame", "framing", "lens", "perspective", "paradigm"]):
        return "frames"
    if any(w in norm for w in ["scenario", "future", "possibility"]):
        return "scenarios"
    return "generic"


def _detect_pasted_argument(prompt: str) -> bool:
    """Detect whether the prompt contains a pasted argument or op-ed.

    Heuristics (any one fires):
      - ≥50 words AND multi-paragraph
      - ≥40 words AND ≥1 argumentative connective AND has a colon
        introducing the argument body
      - ≥80 words AND ≥1 argumentative connective
      - The prompt explicitly labels the content ("here is the argument:",
        "this op-ed argues that", "the article claims", "the proposal is")
    """
    if not prompt:
        return False
    word_count = len(prompt.split())
    if word_count < 30:
        return False
    paragraph_count = len([p for p in prompt.split("\n\n") if p.strip()])
    if word_count >= 50 and paragraph_count >= 2:
        return True
    arg_markers = [
        "therefore", "thus", "because", "so that", "so businesses",
        "so people", "so companies", "claims that", "argues that",
        "argues we", "argues for", "argues against",
        "conclude that", "concludes that", "follows that",
        "supports the conclusion", "the upshot", "means that",
        "implies that", "the evidence", "the time to act",
        "we should", "they should", "you should", "should be",
    ]
    norm = prompt.lower()
    arg_hits = sum(1 for m in arg_markers if m in norm)
    if word_count >= 80 and arg_hits >= 1:
        return True
    if word_count >= 40 and arg_hits >= 1 and ":" in prompt:
        return True
    label_markers = [
        "here is the argument", "here is the op-ed",
        "the argument is:", "the op-ed argues", "the article argues",
        "the article claims", "the proposal is", "this op-ed",
        "the paper argues", "the essay argues",
    ]
    if any(m in norm for m in label_markers) and word_count >= 30:
        return True
    return False


def _detect_decision_with_options(prompt: str) -> bool:
    """Detect a decision frame: 'should I X or Y' / 'choose between' / etc."""
    if not prompt:
        return False
    norm = prompt.lower()
    patterns = [
        # "should we hire X or Y" — verb followed by 1-6 words then "or"
        r"\bshould (?:i|we|they)\s+(?:\w+\s+){1,6}or\s+\w+",
        r"\bdecide between\b",
        r"\bdeciding (?:whether|between)\b",
        r"\bchoose between\b",
        r"\bpick (?:between|from)\b",
        r"\bweigh (?:these|the) (?:options|alternatives|choices)\b",
        # "X or Y" with cost/timeline/comparison context (decision matrix)
        r"\bor\s+\w+\s+\w+\?.*\b(?:cost|costs|price|takes|delivers|"
        r"timeline|months|days|years|weeks)\b",
    ]
    return any(re.search(p, norm) for p in patterns)


def _detect_failure_description(prompt: str) -> bool:
    """Detect a description of something that failed / is broken."""
    if not prompt:
        return False
    norm = prompt.lower()
    patterns = [
        r"\b(?:keeps?|kept) (?:happening|breaking|failing|crashing)\b",
        r"\b(?:failed|broke|crashed|went wrong|fell apart) (?:when|because|after|during)\b",
        r"\b(?:recurring|repeating) (?:outages?|failures?|problems?|issues?)\b",
        r"\bthe rollout (?:failed|broke|went sideways)\b",
        r"\bdidn['’]t work\b",
    ]
    return any(re.search(p, norm) for p in patterns)


def _detect_conflict_description(prompt: str) -> bool:
    """Detect multi-party conflict structure in the prompt."""
    if not prompt:
        return False
    norm = prompt.lower()
    # Multiple "wants/needs/prefers" attributions
    wants_count = len(re.findall(
        r"\b(?:team|party|group|stakeholder|side|department|"
        r"engineering|product|sales|marketing|legal|finance|customer|client|board)\s+"
        r"\w*\s*(?:wants?|needs?|prefers?|insists?|demands?|argues?)\b",
        norm
    ))
    if wants_count >= 2:
        return True
    if re.search(r"\bdisagreement between\b|\bconflict (?:between|among)\b|"
                 r"\beach (?:wants|needs)\b|\bcompeting (?:claims|interests|priorities)\b",
                 norm):
        return True
    return False


def _detect_spatial_description(prompt: str) -> bool:
    """Detect description of a place / layout / spatial composition."""
    if not prompt:
        return False
    norm = prompt.lower()
    patterns = [
        r"\b(?:room|building|library|park|plaza|garden|space|hall|gallery)\b.*"
        r"\b(?:layout|composition|arrangement|atmosphere)\b",
        r"\b(?:dashboard|chart|diagram|infographic|visualization|infographic)\b.*"
        r"\b(?:design|layout|composition)\b",
        r"\bgenius loci\b|\bspatial (?:composition|reading)\b",
    ]
    return any(re.search(p, norm) for p in patterns)


def _detect_attached_artifact(context: dict | None) -> str | None:
    """Detect attached file type from context."""
    ctx = context or {}
    if ctx.get("image_path"):
        return "image"
    if ctx.get("attached_document"):
        return "document"
    atts = ctx.get("attachments", [])
    if atts:
        for a in atts:
            mime = (a or {}).get("type", "")
            if mime.startswith("image/"):
                return "image"
            if mime in ("application/pdf",) or mime.startswith("text/"):
                return "document"
        return "file"
    return None


# Mapping from data shapes to candidate modes/territories.
_DATA_SHAPE_TO_CANDIDATES = {
    "enum_hypotheses": [
        ("competing-hypotheses", "T5-hypothesis-evaluation"),
        ("differential-diagnosis", "T5-hypothesis-evaluation"),
    ],
    "enum_options": [
        ("constraint-mapping", "T3-decision-under-uncertainty"),
        ("multi-criteria-decision", "T3-decision-under-uncertainty"),
    ],
    "enum_parties": [
        ("stakeholder-mapping", "T8-stakeholder-conflict"),
        ("cui-bono", "T2-interest-and-power"),
    ],
    "enum_frames": [
        ("frame-comparison", "T9-paradigm-and-assumption-examination"),
    ],
    "enum_scenarios": [
        ("scenario-planning", "T6-future-exploration"),
    ],
    "pasted_argument": [
        ("coherence-audit", "T1-argumentative-artifact-examination"),
        ("steelman-construction", "T15-artifact-evaluation-by-stance"),
    ],
    "decision_with_options": [
        ("constraint-mapping", "T3-decision-under-uncertainty"),
        ("decision-under-uncertainty", "T3-decision-under-uncertainty"),
    ],
    "failure_description": [
        ("root-cause-analysis", "T4-causal-investigation"),
    ],
    "conflict_description": [
        ("conflict-structure", "T8-stakeholder-conflict"),
        ("stakeholder-mapping", "T8-stakeholder-conflict"),
    ],
    "spatial_description": [
        ("place-reading-genius-loci", "T19-spatial-composition"),
        ("compositional-dynamics", "T19-spatial-composition"),
    ],
    "attached_image": [
        ("spatial-reasoning", "T11-structural-relationship-mapping"),
        ("compositional-dynamics", "T19-spatial-composition"),
    ],
    "attached_document": [
        ("coherence-audit", "T1-argumentative-artifact-examination"),
        ("cui-bono", "T2-interest-and-power"),
    ],
}


def _detect_data_shapes(prompt: str, context: dict | None) -> list[dict]:
    """Detect routing-relevant data shapes in the prompt and context.

    Returns a list of shape signal dicts each with the same shape as
    registry entries (for uniform handling in Stage 2): signal, territory,
    mode, confidence_weight, evidence, plus a 'data_shape' tag.
    """
    signals: list[dict] = []

    enum = _detect_enumerated_items(prompt)
    if enum:
        kind_key = f"enum_{enum['kind']}"
        if kind_key in _DATA_SHAPE_TO_CANDIDATES:
            for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES[kind_key]:
                signals.append({
                    "signal": f"data-shape:{kind_key}({enum['count']} items)",
                    "territory": territory,
                    "mode": mode_id,
                    "confidence_weight": "strong",
                    "evidence": "data-shape detection",
                    "data_shape": kind_key,
                })

    if _detect_pasted_argument(prompt):
        for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES["pasted_argument"]:
            signals.append({
                "signal": "data-shape:pasted_argument",
                "territory": territory,
                "mode": mode_id,
                # Strong signal — when both T1 and T15 candidates fire, the
                # cross-territory check in Stage 2 surfaces the disambiguation
                # question rather than dispatching blindly.
                "confidence_weight": "strong",
                "evidence": "data-shape detection",
                "data_shape": "pasted_argument",
            })

    if _detect_decision_with_options(prompt):
        for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES["decision_with_options"]:
            signals.append({
                "signal": "data-shape:decision_with_options",
                "territory": territory,
                "mode": mode_id,
                "confidence_weight": "strong",
                "evidence": "data-shape detection",
                "data_shape": "decision_with_options",
            })

    if _detect_failure_description(prompt):
        for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES["failure_description"]:
            signals.append({
                "signal": "data-shape:failure_description",
                "territory": territory,
                "mode": mode_id,
                "confidence_weight": "strong",
                "evidence": "data-shape detection",
                "data_shape": "failure_description",
            })

    if _detect_conflict_description(prompt):
        for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES["conflict_description"]:
            signals.append({
                "signal": "data-shape:conflict_description",
                "territory": territory,
                "mode": mode_id,
                "confidence_weight": "strong",
                "evidence": "data-shape detection",
                "data_shape": "conflict_description",
            })

    if _detect_spatial_description(prompt):
        for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES["spatial_description"]:
            signals.append({
                "signal": "data-shape:spatial_description",
                "territory": territory,
                "mode": mode_id,
                "confidence_weight": "strong",
                "evidence": "data-shape detection",
                "data_shape": "spatial_description",
            })

    attached = _detect_attached_artifact(context)
    if attached == "image":
        for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES["attached_image"]:
            signals.append({
                "signal": "data-shape:attached_image",
                "territory": territory,
                "mode": mode_id,
                "confidence_weight": "weak",
                "evidence": "data-shape detection (attached image)",
                "data_shape": "attached_image",
            })
    elif attached in ("document", "file"):
        for mode_id, territory in _DATA_SHAPE_TO_CANDIDATES["attached_document"]:
            signals.append({
                "signal": "data-shape:attached_document",
                "territory": territory,
                "mode": mode_id,
                "confidence_weight": "weak",
                "evidence": "data-shape detection (attached document)",
                "data_shape": "attached_document",
            })

    return signals


def _load_signal_registry() -> list[dict]:
    """Parse the signal vocabulary registry into a list of signal entries.

    Each entry: {signal, territory, mode, disambiguation_answer,
    confidence_weight, evidence}. Strong-confidence entries are the trigger
    set; weak entries contribute disambiguation context. The
    ``_PHASE9_SIGNAL_ALIASES`` augmentation is appended last so corpus-
    expected phrases the canonical registry doesn't yet cover still fire.

    Cached after first call. Returns empty list if file missing.
    """
    global _SIGNAL_REGISTRY_CACHE
    if _SIGNAL_REGISTRY_CACHE is not None:
        return _SIGNAL_REGISTRY_CACHE

    entries: list[dict] = []
    if os.path.exists(SIGNAL_REGISTRY_FILE):
        with open(SIGNAL_REGISTRY_FILE, "r") as f:
            content = f.read()
    else:
        # Loud stderr warning — without the registry file Stage 1 sees only
        # the small Phase-9 alias list and most analytical signals don't
        # match. Pre-routing degrades silently to bypass / fallback dispatch.
        # Same observability pattern as load_mode and load_framework.
        print(
            f"[load_signal_vocabulary] registry file not found at "
            f"{SIGNAL_REGISTRY_FILE} — only the Phase-9 code-side aliases "
            f"will populate the signal registry. Pre-routing will under-match.",
            file=sys.stderr,
            flush=True,
        )
        content = ""

    for line in content.split("\n"):
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip().split("|")]
        # Markdown table rows: leading and trailing pipes produce empty cells
        parts = [p for p in parts if p != ""]
        if len(parts) < 6:
            continue
        # Skip header rows and separator rows
        if parts[0].lower() == "signal":
            continue
        if all(c in "-: " for c in parts[0]):
            continue
        signal_text = parts[0]
        if not signal_text or signal_text.startswith("-"):
            continue
        entries.append({
            "signal": signal_text,
            "territory": parts[1],
            "mode": parts[2],
            "disambiguation_answer": parts[3],
            "confidence_weight": parts[4].lower(),
            "evidence": parts[5] if len(parts) > 5 else "",
        })

    # Phase 9 — append code-side aliases.
    for alias in _PHASE9_SIGNAL_ALIASES:
        entries.append({
            "signal": alias["signal"],
            "territory": alias["territory"],
            "mode": alias["mode"],
            "disambiguation_answer": alias.get("disambiguation_answer", "—"),
            "confidence_weight": alias["confidence_weight"],
            "evidence": "phase-9 alias",
        })

    _SIGNAL_REGISTRY_CACHE = entries
    return entries


def _check_strong_bypass(prompt: str) -> dict | None:
    """Run only the STRONG_BYPASS_TRIGGERS scan over ``prompt``.

    Returns the bypass-result dict when a trigger fires, ``None`` otherwise.
    Used by both ``pre_phase_a_bypass_check`` (which runs on the raw user
    prompt before Phase A) and ``stage1_pre_analysis_filter`` (which runs
    on Phase A's operational notation as a defensive backup).

    Triggers that fire under negation context ("I don't want no analysis",
    "what does 'no analysis' mean") are skipped so the bypass doesn't
    misread quoted or negated discussion of the trigger phrase as an opt-out.
    """
    for trigger in STRONG_BYPASS_TRIGGERS:
        stripped = trigger.strip()
        if _signal_present(prompt, stripped) and not _is_negated(prompt, stripped):
            return {
                "bypass_to_direct_response": True,
                "matches": [],
                "rationale": f"strong bypass trigger: '{stripped}'",
            }
    return None


def _check_weak_bypass(prompt: str) -> dict | None:
    """Run only the WEAK_BYPASS_TRIGGERS scan over ``prompt``.

    Greetings and acknowledgements — fire as bypass only when there is no
    strong analytical signal in the same prompt. Used inside Stage 1 (after
    the analytical-signal scan); also used by ``pre_phase_a_bypass_check``,
    which has no analytical-signal scan and treats weak triggers as
    bypass-eligible *unless* the registry would have matched in Stage 1.

    Negation-aware: a quoted or negated mention of a greeting trigger
    ("don't just say hello, actually analyse this") does not fire bypass.
    """
    for trigger in WEAK_BYPASS_TRIGGERS:
        stripped = trigger.strip()
        if _signal_present(prompt, stripped) and not _is_negated(prompt, stripped):
            return {
                "bypass_to_direct_response": True,
                "matches": [],
                "rationale": f"weak bypass trigger: '{stripped}'",
            }
    return None


def pre_phase_a_bypass_check(prompt: str) -> dict | None:
    """Run bypass detection on the *raw* user prompt before Phase A.

    Returns the bypass result dict if a trigger fires; ``None`` otherwise.

    This fixes the detector-layering bug uncovered 2026-05-15: Phase A's
    expansion of the raw prompt into operational notation produces strictly
    more text for the post-Phase-A Stage 1 detector to match against, which
    increased the false-positive rate (``"no analysis"`` matching inside
    ``"cui bono analysis"``) AND decreased the true-positive rate (``"what
    time is it"`` normalised away by Phase A into ``"REQUEST: current-time"``,
    losing the trigger). Running bypass detection on the raw prompt before
    Phase A eliminates both failure classes.

    A strong-trigger match returns immediately. Weak-trigger matching honours
    the same "no strong analytical signal" guard as Stage 1, but because we
    don't run the registry scan here, the heuristic is: if the prompt looks
    like *only* a greeting / acknowledgement (no obvious analytical
    vocabulary), treat weak as bypass. The check is intentionally conservative
    — when in doubt, fall through to Phase A + Stage 1, which has the full
    registry to decide.
    """
    strong = _check_strong_bypass(prompt)
    if strong is not None:
        strong["stage"] = "pre-phase-a"
        return strong

    # Weak triggers: only bypass when the prompt is plausibly *just* a
    # greeting / acknowledgement and not "Hi! Steelman this op-ed". We
    # detect that by checking the prompt is short AND has no obvious
    # analytical-vocabulary tokens. The Stage 1 registry-aware check stays
    # in place as the authoritative call; this pre-Phase-A check only
    # bypasses on near-certain weak matches.
    weak = _check_weak_bypass(prompt)
    if weak is not None:
        # If the prompt is short (≤ 8 words after normalisation) and
        # contains no obvious analytical vocabulary, treat the weak match
        # as a real bypass.
        norm = _normalize_for_match(prompt)
        word_count = len(norm.split())
        analytical_hint_tokens = (
            "analyze", "analyse", "evaluate", "audit", "steelman",
            "argument", "decision", "tradeoff", "tradeoffs", "trade off",
            "compare", "examine", "investigate", "explain why", "explain how",
            "why does", "why did", "how does", "how did", "cui bono",
            "pre mortem", "premortem", "root cause", "consequences",
            "what would happen", "stress test", "stress-test",
        )
        if word_count <= 8 and not any(t in norm for t in analytical_hint_tokens):
            weak["stage"] = "pre-phase-a"
            return weak

    return None


def stage1_pre_analysis_filter(prompt: str, context: dict | None = None) -> dict:
    """Stage 1 of the pre-routing pipeline: pre-analysis filter.

    Distinguishes prompts that should enter the analytical pipeline from
    prompts that bypass it (chitchat, simple lookups, system commands,
    prior-conversation references). Per spec §Stage 1.

    Returns:
        {
            "bypass_to_direct_response": bool,
            "matches": [<signal_entry>],   # registry rows that fired
            "rationale": str,
        }
    """
    norm_prompt = _normalize_for_match(prompt)

    # 1. STRONG bypass triggers always win — system commands, prior-conversation
    # references, factual lookups. These dominate even when an analytical
    # signal also fires (the user is asking about a previous turn or running
    # a system command, not requesting fresh analysis). This check also runs
    # *before* Phase A via ``pre_phase_a_bypass_check``; the duplication here
    # is intentional — Stage 1 is the defensive backup when Phase A
    # expansion legitimately reveals a bypass-worthy element the raw prompt
    # didn't carry.
    strong_result = _check_strong_bypass(prompt)
    if strong_result is not None:
        return strong_result

    # 2. Analytical-artifact signal detection — registry strong-weight entries.
    registry = _load_signal_registry()
    matches: list[dict] = []
    seen_signals: set[str] = set()

    sorted_registry = sorted(registry, key=lambda e: -len(e["signal"]))

    for entry in sorted_registry:
        sig = _normalize_for_match(entry["signal"])
        if not sig or sig in seen_signals:
            continue
        if _signal_present(prompt, entry["signal"]):
            if _is_negated(prompt, entry["signal"]):
                continue
            seen_signals.add(sig)
            matches.append(entry)

    # 3. Phase 9.5 — Fuzzy framework-name matching (typos, near-misses).
    # Catches "SWAT" → SWOT, "premortem" → pre-mortem, "casual dag" → causal dag.
    fuzzy_matches = _detect_fuzzy_framework_matches(prompt, matches)
    matches.extend(fuzzy_matches)

    # 4. Phase 9.5 — Data-shape detection. Independent of phrasing — looks
    # at what the prompt actually contains (enumerated hypotheses, pasted
    # arguments, decision frames, failure descriptions, attachments).
    # Caller can pass context separately; here we detect from prompt alone.
    data_shape_matches = _detect_data_shapes(prompt, context)
    matches.extend(data_shape_matches)

    has_strong_analytical = any(m["confidence_weight"] == "strong"
                                 for m in matches)

    # 5. WEAK bypass triggers — only when no strong analytical signal.
    # "Hi! Steelman this op-ed" → steelman wins because analytical is strong.
    if not has_strong_analytical:
        weak_result = _check_weak_bypass(prompt)
        if weak_result is not None:
            return weak_result

    # 6. Default permissive: empty matches → forward to Stage 2 anyway.
    fuzzy_count = sum(1 for m in matches if m.get("fuzzy_typo"))
    shape_count = sum(1 for m in matches if m.get("data_shape"))
    parts = []
    phrase_count = len(matches) - fuzzy_count - shape_count
    if phrase_count:
        parts.append(f"{phrase_count} phrase signal(s)")
    if fuzzy_count:
        parts.append(f"{fuzzy_count} fuzzy match(es)")
    if shape_count:
        parts.append(f"{shape_count} data-shape signal(s)")

    return {
        "bypass_to_direct_response": False,
        "matches": matches,
        "rationale": (
            "; ".join(parts) if parts
            else "no signals matched; default permissive (forward to Stage 2)"
        ),
    }


# ---------------------------------------------------------------------------
# Phase 9 — Stage 2 (Prompt Sufficiency Analyzer)
# Spec: ~/ora/architecture/pre-routing-pipeline.md §Stage 2
# ---------------------------------------------------------------------------

# Conflict-pair definitions — contradictory signals that must surface a
# disambiguation question rather than auto-dispatch.
_CONFLICT_PAIRS = [
    # depth conflicts
    (("quick", "fast", "quickly", "fast read"),
     ("deep dive", "deep-dive", "deep read", "thorough", "full"),
     "depth"),
    # stance conflicts
    (("steelman", "make the case for", "strongest case"),
     ("red team", "red-team", "push back", "tear apart"),
     "stance"),
]


def _territory_of(entry: dict) -> str:
    """Extract the T<n>- prefix from a registry territory string."""
    t = entry.get("territory", "")
    return t.split("-")[0] if "-" in t else t


def _matches_grouped_by_mode(matches: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for m in matches:
        mode = m["mode"]
        grouped.setdefault(mode, []).append(m)
    return grouped


def _matches_grouped_by_territory(matches: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for m in matches:
        t = _territory_of(m)
        grouped.setdefault(t, []).append(m)
    return grouped


def _detect_conflicts(prompt: str) -> list[dict]:
    """Detect contradictory signal pairs in the prompt.

    Returns a list of conflict dicts with axis + the two competing signal
    sets that fired.
    """
    conflicts: list[dict] = []
    for set_a, set_b, axis in _CONFLICT_PAIRS:
        a_hits = [s for s in set_a
                  if _signal_present(prompt, s) and not _is_negated(prompt, s)]
        b_hits = [s for s in set_b
                  if _signal_present(prompt, s) and not _is_negated(prompt, s)]
        if a_hits and b_hits:
            conflicts.append({
                "axis": axis,
                "side_a": a_hits,
                "side_b": b_hits,
            })
    return conflicts


# Vague prompt patterns — phrases that signal "I don't know what I want;
# please ask me." When matched, Stage 2 should disambiguate rather than
# auto-dispatch on whatever weak signal happens to fire first.
_VAGUE_PROMPT_PATTERNS = [
    r"\bhelp me think about\b",
    r"\bhelp me think through\b",
    r"\bwalk me through this\b(?!\s+(?:debate|argument|decision))",  # bare "walk me through this"
    r"\btell me about\b",
    r"\bexplore (?:where|what)\b",
    r"\bi('m| am) interested in\b",
    r"\b(?:two|three|several|multiple) (?:approaches|ideas|frameworks|things) keep showing up\b",
    r"\b(?:suspend|examine) (?:the|this) paradigm\b.+\b(?:synthesize|integrate|combine)\b",
]


def _is_vague_prompt(prompt: str) -> bool:
    """Return True when the prompt is too vague for direct dispatch."""
    if not prompt:
        return False
    norm = _normalize_for_match(prompt)
    for pat in _VAGUE_PROMPT_PATTERNS:
        if re.search(pat, norm):
            return True
    return False


def _detect_depth_signal(prompt: str) -> str | None:
    """Return 'tier-1' / 'tier-2' / 'tier-3' if the prompt explicitly signals
    a depth, else None (so default-on-ambiguity Tier-2 applies)."""
    tier_1 = ["quickly", "quick read", "quick scan", "fast read", "quick", "brief"]
    tier_3 = ["deep dive", "deep-dive", "thoroughly", "thorough", "molecular",
              "comprehensive", "full", "complete analysis", "deeply"]
    for sig in tier_1:
        if _signal_present(prompt, sig) and not _is_negated(prompt, sig):
            return "tier-1"
    for sig in tier_3:
        if _signal_present(prompt, sig) and not _is_negated(prompt, sig):
            return "tier-3"
    return None


def _format_within_territory_question(territory: str) -> str:
    """Plain-language disambiguation question per Within-Territory Trees.

    Returns the canonical Q1 question for the territory in plain English
    per Disambiguation Style Guide §5.3. Returns the generic Pattern A
    intent disambiguation when the territory has no within-territory tree
    or is a singleton.
    """
    return _WITHIN_TERRITORY_QUESTIONS.get(territory, _GENERIC_INTENT_QUESTION)


_GENERIC_INTENT_QUESTION = (
    "Quick check on what you're after — are you mostly trying to: "
    "(a) figure out who benefits from this; "
    "(b) check whether the argument holds up; "
    "(c) decide what to do; "
    "(d) understand why this happened?"
)

_WITHIN_TERRITORY_QUESTIONS = {
    "T1": (
        "Is the question about whether the argument holds together internally, "
        "or about the frame it's using to see the issue, or both at once?"
    ),
    "T2": (
        "Are you trying to figure out who benefits from this single situation, "
        "map out a landscape of multiple parties, or work through something "
        "that feels tangled across many dimensions?"
    ),
    "T3": (
        "Is the environment basically known and you're picking from clear "
        "options, are there real unknowns about how things will play out, "
        "or are you weighing several criteria that don't reduce to one number?"
    ),
    "T4": (
        "Is the question more like 'what one thing went wrong here', "
        "'what set of things keep producing this', or do you want a formal "
        "causal model with arrows you can reason over?"
    ),
    "T5": (
        "Quick read on which explanation fits best, lay out evidence "
        "systematically against each candidate, or a probabilistic model "
        "with priors?"
    ),
    "T6": (
        "Mostly looking forward to anticipate likely consequences, wanting "
        "probability estimates, wanting alternative future stories, or "
        "stress-testing a plan against how it could go wrong?"
    ),
    "T7": (
        "Stress-testing for how this could fail, or auditing what makes it "
        "fragile vs. antifragile under stress?"
    ),
    "T8": (
        "Mapping who all the parties are and what they want, or laying out "
        "the structure of the conflict between them?"
    ),
    "T9": (
        "Suspending the assumptions in this single piece, comparing "
        "different frames at play, or mapping the worldviews more broadly?"
    ),
    "T10": (
        "Clarifying what a key term currently means, or working on what it "
        "should come to mean for the work going forward?"
    ),
    "T13": (
        "Mapping interests before the negotiation, prepping a principled "
        "negotiation strategy, or stepping into a mediator role?"
    ),
    "T14": (
        "Want a quick orientation, a fuller terrain map, or a full domain "
        "induction?"
    ),
    "T15": (
        "Want me to make the strongest case for it, the strongest case "
        "against it, or weigh both sides?"
    ),
    "T19": (
        "Reading the spatial composition, the place-character, or the "
        "information density?"
    ),
}


# Cross-territory adjacency questions per ~/ora/architecture/cross-territory-adjacency.md.
# Plain-language disambiguators that distinguish the two adjacent territories.
_CROSS_TERRITORY_QUESTIONS = {
    frozenset(["T1", "T2"]): (
        "Are you mostly asking whether the argument itself holds up, "
        "or who benefits if people accept it?"
    ),
    frozenset(["T1", "T5"]): (
        "Are the competing positions each a complete argument you want me "
        "to audit, or are they propositions you want weighed against evidence?"
    ),
    frozenset(["T1", "T9"]): (
        "Are you evaluating this single argument's frame, or comparing "
        "different paradigms that frame the issue differently?"
    ),
    frozenset(["T1", "T10"]): (
        "Is the issue with how the argument deploys a specific concept "
        "(clarify the concept first), or with how the argument coheres "
        "given any reasonable reading of the concept?"
    ),
    frozenset(["T1", "T15"]): (
        "Want me to evaluate the argument's soundness (does it hold up?), "
        "or evaluate the proposal with a particular stance "
        "(steelman / push back / weigh both)?"
    ),
    frozenset(["T2", "T8"]): (
        "Mostly asking who benefits or has power, or asking how the parties' "
        "competing claims can be worked through?"
    ),
    frozenset(["T2", "T13"]): (
        "Are you mapping the interest landscape, or are you about to "
        "negotiate (or advise a negotiation)?"
    ),
    frozenset(["T3", "T6"]): (
        "Are you choosing among options now, or exploring how the future "
        "might unfold?"
    ),
    frozenset(["T3", "T7"]): (
        "Choosing among options where risk is one input among several, "
        "or specifically stress-testing how things could fail?"
    ),
    frozenset(["T3", "T8"]): (
        "Is this fundamentally your decision to make (with the parties as "
        "inputs), or is it a situation where the parties' conflict itself "
        "is what needs to be worked through first?"
    ),
    frozenset(["T4", "T9"]): (
        "Looking for the causes within how the problem is currently framed, "
        "or stepping back to ask whether the framing itself is generating "
        "the problem?"
    ),
    frozenset(["T4", "T16"]): (
        "Tracing back to causes, or explaining how the parts produce the "
        "behavior?"
    ),
    frozenset(["T6", "T7"]): (
        "Mapping how the future could unfold (multiple stories), or "
        "stress-testing a specific plan for how it could fail?"
    ),
    frozenset(["T8", "T13"]): (
        "Mapping how the parties relate, or stepping into negotiation "
        "or mediation?"
    ),
}


# Catch-all modes — if a more specific mode also fires strongly, prefer
# the specific mode. These modes act as fallbacks when no specific signal
# is present and shouldn't win a tie against a named framework.
_CATCH_ALL_MODES = {
    "passion-exploration",
    "terrain-mapping",
    "standard",
    "adversarial",
    "simple",
    "structured-output",
}


def _data_shape_candidate_index(mode_id: str) -> int:
    """Position of mode_id in any data-shape's candidate list (lower = preferred).
    Returns 999 if mode_id isn't in any data-shape mapping."""
    for candidates in _DATA_SHAPE_TO_CANDIDATES.values():
        for i, (m, _t) in enumerate(candidates):
            if m == mode_id:
                return i
    return 999


def _signal_kind(m: dict) -> str:
    """Categorize a match by source: explicit framework name, data shape,
    fuzzy match, or phrase trigger. Used for priority ranking."""
    if m.get("fuzzy_typo"):
        return "fuzzy"
    if m.get("data_shape"):
        return "data_shape"
    evidence = (m.get("evidence") or "").lower()
    # Method-name and mode-name references in the canonical registry are
    # explicit framework names (highest priority).
    if "method-name" in evidence or "mode-name" in evidence or \
       "framework name" in evidence or "framework abbreviation" in evidence or \
       "mode abbreviation" in evidence:
        return "explicit_framework"
    return "phrase"


def _select_dispatch_mode(matches: list[dict],
                          depth_signal: str | None) -> tuple[str | None, str]:
    """Pick the best mode_id, prioritizing in this order:

      1. Explicit framework name (registry method/mode-name reference)
      2. Data shape signal (Phase 9.5 detector)
      3. Fuzzy/typo match (Phase 9.5)
      4. Phrase trigger (registry trigger phrase)

    Within each priority tier, prefer non-catch-all modes. When two modes
    tie, prefer the one with corroboration from another tier.
    """
    if not matches:
        return None, "low"

    # Group strong matches by mode + kind
    by_mode: dict[str, dict[str, int]] = {}
    for m in matches:
        if m["confidence_weight"] != "strong":
            continue
        mode = m["mode"]
        kind = _signal_kind(m)
        by_mode.setdefault(mode, {"explicit_framework": 0, "data_shape": 0,
                                    "fuzzy": 0, "phrase": 0})
        by_mode[mode][kind] += 1

    if not by_mode:
        return None, "low"

    def specific_only(modes: dict) -> dict:
        spec = {m: c for m, c in modes.items() if m not in _CATCH_ALL_MODES}
        return spec if spec else modes

    # Tier 1: explicit framework name
    explicit = {m: c["explicit_framework"] for m, c in by_mode.items()
                 if c["explicit_framework"] > 0}
    if explicit:
        explicit = specific_only(explicit)
        # Tie-break by corroboration from data shape > phrase
        best = max(explicit.keys(), key=lambda mid: (
            explicit[mid],
            by_mode[mid]["data_shape"],
            by_mode[mid]["phrase"],
        ))
        return best, "high"

    # Tier 2: data shape signal
    data = {m: c["data_shape"] for m, c in by_mode.items()
             if c["data_shape"] > 0}
    if data:
        data = specific_only(data)
        # Tie-break: prefer mode with phrase corroboration; if still tied,
        # use the order from _DATA_SHAPE_TO_CANDIDATES (first listed wins —
        # the simpler/more common mode for the shape).
        best = max(data.keys(), key=lambda mid: (
            data[mid],
            by_mode[mid]["phrase"],
            -_data_shape_candidate_index(mid),  # earlier index = preferred
        ))
        return best, "high" if data[best] >= 2 else "medium"

    # Tier 3: fuzzy match
    fuzzy = {m: c["fuzzy"] for m, c in by_mode.items()
              if c["fuzzy"] > 0}
    if fuzzy:
        fuzzy = specific_only(fuzzy)
        best = max(fuzzy.keys(), key=lambda mid: (fuzzy[mid],
                                                    by_mode[mid]["phrase"]))
        return best, "medium"

    # Tier 4: phrase trigger
    phrase = {m: c["phrase"] for m, c in by_mode.items() if c["phrase"] > 0}
    if phrase:
        phrase = specific_only(phrase)
        best = max(phrase.keys(), key=lambda mid: phrase[mid])
        confidence = "high" if phrase[best] >= 2 else "medium"
        return best, confidence

    return None, "low"


def stage2_sufficiency_analyzer(prompt: str, stage1_output: dict,
                                context: dict | None = None) -> dict:
    """Stage 2 of the pre-routing pipeline: prompt sufficiency analyzer.

    Determines whether the prompt contains enough signal to dispatch to a
    specific mode without disambiguation, or whether disambiguation
    questions are needed (and which). Per spec §Stage 2.

    Returns:
        {
            "dispatched_mode_id": <mode_id> | None,
            "disambiguation_questions_asked": [<plain-language questions>],
            "disambiguation_answers_received": [],
            "confidence": "high" | "medium" | "low",
            "territory": <territory_id> | None,
            "rationale": str,
        }
    """
    matches = stage1_output.get("matches", [])
    depth_signal = _detect_depth_signal(prompt)

    # 2.3 Conflict detection — fires before any dispatch.
    conflicts = _detect_conflicts(prompt)
    if conflicts:
        c = conflicts[0]
        if c["axis"] == "depth":
            q = (
                "I see both a quick-read and a deep-dive cue — want a quick "
                "first read, or should I take the longer route?"
            )
        elif c["axis"] == "stance":
            q = (
                "Want me to make the strongest case for it, push back on it, "
                "or weigh both sides?"
            )
        else:
            q = (
                "I'm seeing competing cues in your prompt — could you tell "
                "me which way you'd like me to lean?"
            )
        return {
            "dispatched_mode_id": None,
            "disambiguation_questions_asked": [q],
            "disambiguation_answers_received": [],
            "confidence": "low",
            "territory": None,
            "rationale": f"conflict on axis '{c['axis']}'",
        }

    # 2.4 Cross-territory adjacency check — when signals straddle two
    # territories, the cross-territory question fires first.
    # Decision G exception: when a T15 mode-name signal fires (steelman /
    # red-team / etc.), T15 is the home and T1/T9/T10 are cross-references —
    # don't ask the cross-territory question.
    by_territory = _matches_grouped_by_territory(matches)
    strong_territories = [
        t for t, ms in by_territory.items()
        if any(m["confidence_weight"] == "strong" for m in ms)
    ]

    home_territory_modes = {
        "T15": {"steelman-construction", "red-team", "balanced-critique",
                "benefits-analysis"},
    }
    suppressed_territories = set()
    for home, modes in home_territory_modes.items():
        if home in strong_territories:
            home_strong = any(
                m["mode"] in modes and m["confidence_weight"] == "strong"
                for m in by_territory.get(home, [])
            )
            if home_strong:
                # Suppress the cross-territory question; home territory wins.
                suppressed_territories.update(t for t in strong_territories
                                              if t != home)

    effective_territories = [t for t in strong_territories
                              if t not in suppressed_territories]

    if len(effective_territories) >= 2:
        effective_territories.sort(
            key=lambda t: -sum(1 for m in by_territory[t]
                              if m["confidence_weight"] == "strong")
        )
        pair = frozenset(effective_territories[:2])
        if pair in _CROSS_TERRITORY_QUESTIONS:
            return {
                "dispatched_mode_id": None,
                "disambiguation_questions_asked": [_CROSS_TERRITORY_QUESTIONS[pair]],
                "disambiguation_answers_received": [],
                "confidence": "low",
                "territory": None,
                "rationale": f"cross-territory ambiguity {sorted(pair)}",
            }

    # 2.2 Multiple-signal composition: try direct dispatch first.
    # Priority: explicit framework name > data shape > fuzzy > phrase.
    mode_id, confidence = _select_dispatch_mode(matches, depth_signal)
    if mode_id and confidence in ("high", "medium"):
        territory = None
        # Pick up the matching entry to detect fuzzy / data-shape provenance
        winning_match = None
        for m in matches:
            if m["mode"] == mode_id:
                winning_match = m
                if not territory:
                    territory = _territory_of(m)

        # "Did you mean?" note for fuzzy dispatches
        did_you_mean = None
        for m in matches:
            if m["mode"] == mode_id and m.get("fuzzy_typo"):
                did_you_mean = (
                    f"I noticed you wrote \"{m['fuzzy_typo']}\" — "
                    f"interpreting as \"{m['fuzzy_canonical']}\". "
                    f"Let me know if you meant something else."
                )
                break

        # Conflict surfacing: when an explicit framework name disagrees
        # with a data-shape signal, the user may have asked for the wrong
        # technique. Flag it but proceed with the explicit request.
        explicit_modes = {m["mode"] for m in matches
                           if m["confidence_weight"] == "strong"
                           and _signal_kind(m) == "explicit_framework"}
        shape_modes = {m["mode"] for m in matches
                        if m["confidence_weight"] == "strong"
                        and _signal_kind(m) == "data_shape"}
        shape_mismatch_note = None
        if (explicit_modes and shape_modes
                and not (explicit_modes & shape_modes)
                and mode_id in explicit_modes):
            # User asked for X but the data looks like Y
            shape_alt = next(iter(shape_modes - explicit_modes), None)
            if shape_alt:
                shape_mismatch_note = (
                    f"You asked for {mode_id.replace('-', ' ')}, but the "
                    f"data you provided looks more like a fit for "
                    f"{shape_alt.replace('-', ' ')}. I'll go with what "
                    f"you asked for — let me know if you'd rather switch."
                )

        return {
            "dispatched_mode_id": mode_id,
            "disambiguation_questions_asked": [],
            "disambiguation_answers_received": [],
            "confidence": confidence,
            "territory": territory,
            "rationale": f"strong direct dispatch on {mode_id}",
            "did_you_mean_note": did_you_mean,
            "shape_mismatch_note": shape_mismatch_note,
        }

    # Suppress dispatch only when the prompt is genuinely vague AND no
    # strong dispatch is available — phrases like "help me think about
    # this" with no framework name should disambiguate, not auto-dispatch
    # on a weak passion-exploration / terrain-mapping match.
    if _is_vague_prompt(prompt):
        return {
            "dispatched_mode_id": None,
            "disambiguation_questions_asked": [_GENERIC_INTENT_QUESTION],
            "disambiguation_answers_received": [],
            "confidence": "low",
            "territory": None,
            "rationale": "vague prompt; pattern-A intent question",
        }

    # 2.5 Within-territory disambiguation: when territory is identified but
    # mode is ambiguous.
    weak_territories = list(by_territory.keys())
    if len(weak_territories) == 1:
        territory = weak_territories[0]
        question = _format_within_territory_question(territory)
        return {
            "dispatched_mode_id": None,
            "disambiguation_questions_asked": [question],
            "disambiguation_answers_received": [],
            "confidence": "low",
            "territory": territory,
            "rationale": f"within-territory ambiguity in {territory}",
        }

    # 2.6 Default-on-ambiguity: per Style Guide §5.6 — ask Pattern A
    # (intent disambiguation) when no territory at all is identified.
    return {
        "dispatched_mode_id": None,
        "disambiguation_questions_asked": [_GENERIC_INTENT_QUESTION],
        "disambiguation_answers_received": [],
        "confidence": "low",
        "territory": None,
        "rationale": "no territory identified; pattern-A intent question",
    }


# ---------------------------------------------------------------------------
# Phase 9 — Stage 3 (Input Completeness Check)
# Spec: ~/ora/architecture/pre-routing-pipeline.md §Stage 3
# ---------------------------------------------------------------------------

def _parse_input_contract(mode_text: str) -> dict:
    """Parse the input_contract block from a mode file.

    Returns a dict with expert_mode + accessible_mode + detection +
    graceful_degradation sub-dicts. Naive YAML parser sized for the
    template structure used in /Users/oracle/ora/modes/*.md.
    """
    # Locate the input_contract: line and capture the indented block.
    # The block runs until the next non-indented, non-blank line (e.g., a
    # ``# 5. CRITICAL QUESTIONS`` markdown heading, the next YAML key, or
    # end-of-file). The prior lookahead-based pattern required a strict
    # `[a-z]\w*:` line to terminate the block and failed when a markdown
    # comment heading appeared first — silently returning {} so Stage 3
    # treated every cui-bono prompt as "no contract → passes through".
    pattern = r"^input_contract:\s*\n((?:[ \t].+\n|\s*\n)+)"
    m = re.search(pattern, mode_text, re.MULTILINE)
    if not m:
        return {}

    block = m.group(1)
    contract: dict = {}
    current_section: str | None = None
    section_buffer: list[str] = []

    def flush():
        if current_section and section_buffer:
            contract[current_section] = "\n".join(section_buffer).strip()

    for line in block.split("\n"):
        if not line.strip():
            continue
        if line.startswith("  ") and not line.startswith("    "):
            # Section header at 2-space indent (e.g., "  expert_mode:")
            if ":" in line:
                key = line.strip().rstrip(":").strip()
                # Detect known section names
                if key in ("expert_mode", "accessible_mode", "detection",
                           "graceful_degradation"):
                    flush()
                    current_section = key
                    section_buffer = []
                    continue
            section_buffer.append(line.rstrip())
        elif line.startswith("    "):
            section_buffer.append(line.rstrip())

    flush()
    return contract


def _parse_required_fields(section_text: str) -> list[str]:
    """Extract the required: list from a section like expert_mode/accessible_mode."""
    if not section_text:
        return []
    m = re.search(r"required:\s*\[([^\]]*)\]", section_text)
    if m:
        body = m.group(1)
        # YAML flow-list parsing: items are bare identifiers separated by
        # commas (the input_contract template uses kebab-case identifiers
        # without quotes). Comma-split is safe here.
        return [f.strip().strip("'\"") for f in body.split(",") if f.strip()]
    # Multi-line list form
    m = re.search(r"required:\s*\n((?:\s+- .+\n?)+)", section_text)
    if m:
        return [ln.strip().lstrip("-").strip() for ln in m.group(1).split("\n") if ln.strip()]
    return []


def _parse_detection_signals(detection_text: str, kind: str) -> list[str]:
    """Extract expert_signals or accessible_signals from a detection block.

    Parses a YAML-flow list like ``["a", "b, with comma", 'c']`` correctly
    by respecting quote boundaries. Comma-split-on-bare-comma is wrong when
    list items themselves contain commas.
    """
    if not detection_text:
        return []
    field = f"{kind}_signals"
    m = re.search(rf"{field}:\s*\[([^\]]*)\]", detection_text)
    if not m:
        return []
    body = m.group(1)
    # Split respecting quoted strings: match each "..." or '...' element.
    items = re.findall(r"\"([^\"]*)\"|'([^']*)'", body)
    return [a or b for (a, b) in items if (a or b)]


def _parse_graceful_degradation(degradation_text: str) -> dict:
    """Extract the on_missing_required and on_underspecified prompts."""
    if not degradation_text:
        return {}
    out: dict = {}
    for key in ("on_missing_required", "on_underspecified"):
        m = re.search(rf"{key}:\s*\"([^\"]+)\"", degradation_text)
        if m:
            out[key] = m.group(1)
        else:
            m = re.search(rf"{key}:\s*['\"]?([^\n]+?)['\"]?$",
                          degradation_text, re.MULTILINE)
            if m:
                out[key] = m.group(1).strip().strip("'\"")
    return out


# Phase 9 — Stage 3 field categorization. Each required-field name in mode
# input_contracts maps to one of four detection patterns:
#   1. ARTIFACT_TEXT_FIELDS — needs actual pasted content / attachment / enum
#   2. SUBJECT_NAMED_FIELDS — satisfied by a concrete noun phrase in the prompt
#   3. SITUATION_FIELDS — satisfied by any substantive prompt content (>=5 words)
#   4. anything else — fall back to generic substring detection
# These sets cover the 50+ mode files in /Users/oracle/ora/modes/.

_ARTIFACT_TEXT_FIELDS = {
    "argument_or_artifact_to_steelman", "argument_text", "artifact_text",
    "artifact_to_evaluate", "policy_memo_text", "chart_image",
    "image_or_composition", "place_description_or_image",
    "system_or_design_description", "action_plan_description",
    "alternatives_set", "hypotheses_set", "data_or_variables_set",
    "issue_description", "outcome_or_pattern_description", "op_ed_text",
    "plan_text", "launch_plan_text",
    "alternatives_constraints_uncertainties_stakeholders",
    "frame_set", "problem_description_for_molecular_work",
    "spatial_artifact_with_resolvable_entity_ids",
    "visual_input_napkin_sketch_or_whiteboard_photo_or_canvas",
    "prior_engineered_concept",
}

_SUBJECT_NAMED_FIELDS = {
    "forecast_subject", "forecast_horizon", "subject_or_question",
    "phenomenon_to_explain", "phenomenon",
    "game_or_situation", "strategic_context",
    "domain_name", "domain_to_orient",
    "concept_to_engineer", "concept_to_clarify", "concept",
    "focal_question", "focal_gap_question",
    "negotiation_context_specifics",
    "event_specification", "historical_event",
}

_SITUATION_FIELDS = {
    "situation_or_artifact", "situation_description",
    "decision_context", "problem_description",
    "conflict_description", "decision_context_for_third_party",
}


# Placeholder nouns that don't count as concrete subjects on their own.
# When the prompt's only noun phrase uses one of these, the situation is
# under-specified.
_PLACEHOLDER_NOUNS = {
    "thing", "things", "this", "that", "these", "those", "it", "one",
    "issue", "matter", "case", "situation", "topic", "question",
    "problem", "dispute", "conflict", "thing's", "stuff",
    "subject", "concern", "context", "thing", "scenario", "scenarios",
    "area", "areas", "instance", "story", "outages", "candidates",
    "alternatives", "options", "choices", "frames", "stakeholders",
}

# Non-noun stopwords that the determiner regex might match (but shouldn't).
_STOPWORDS_NOT_NOUNS = {
    "for", "and", "but", "or", "to", "on", "in", "of", "at", "by",
    "from", "with", "into", "through", "during", "before", "after",
    "above", "below", "up", "down", "out", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "can", "will",
    "just", "should", "now", "very",
}


def _has_concrete_noun(text: str) -> bool:
    """Heuristic: does the prompt contain a concrete noun phrase?

    Looks for any non-placeholder noun candidate (multi-letter common
    noun preceded by a determiner, capitalized proper noun, or quoted
    concept). Placeholder nouns ("this dispute", "this issue") don't
    count as concrete on their own.
    """
    if not text:
        return False
    norm = text.strip()
    # Determiner + noun pattern. Require ≥4 letters in the noun token to
    # avoid matching prepositions like "for", "to", or short pronouns.
    # OR a 2+ char all-caps acronym (AI, EU, US, ML, GPT).
    for det_match in re.finditer(
        r"\b(this|the|a|an|our|my|their)\s+([A-Z][A-Z0-9]+|[A-Za-z][A-Za-z0-9-]{3,})",
        norm, re.IGNORECASE
    ):
        noun = det_match.group(2).lower()
        if noun in _STOPWORDS_NOT_NOUNS:
            continue
        if noun not in _PLACEHOLDER_NOUNS:
            return True
    # Determiner + 2-letter acronym + qualifier pattern (the AI safety, the EU regulation)
    if re.search(r"\b(this|the|a|an|our|my|their)\s+[A-Z]{2,}\s+[a-z]+",
                 norm):
        return True
    # Quoted concept ("merit", 'consent')
    if re.search(r"['\"][A-Za-z][A-Za-z\s-]+['\"]", norm):
        return True
    # Mid-sentence capitalized proper noun (skip first token)
    tokens = norm.split()
    for i, t in enumerate(tokens):
        if i == 0:
            continue
        if not t:
            continue
        # Strip punctuation
        clean = t.strip(",.!?;:'\"()[]{}")
        if len(clean) > 2 and clean[0].isupper() and clean.lower() not in _PLACEHOLDER_NOUNS:
            return True
        # All-caps acronym (e.g., GPT, API, AI when followed by another word)
        if len(clean) >= 2 and clean.isupper():
            return True
    # Compound noun phrase without determiner (e.g., "evolutionary game theory",
    # "AI safety debate") — three or more lowercase words ending in a noun-like
    # token. The phrase should appear AFTER a determiner or preposition like
    # "of"/"in"/"on"/"about" — bare "X Y Z" without context is just the user
    # naming the operation, not a subject.
    for m in re.finditer(
        r"\b(?:of|in|on|about|for|across)\s+(?:the\s+)?"
        r"([a-z][a-z-]{3,})\s+([a-z][a-z-]{3,})\s+([a-z][a-z-]{4,})\b",
        norm.lower()
    ):
        last = m.group(3)
        if not last.endswith("ing") and last not in _PLACEHOLDER_NOUNS:
            return True
    return False


def _has_artifact_content(user_prompt: str, context: dict | None) -> bool:
    """Detect whether actual artifact content is present (not just a name).

    True if any of:
      - context attaches a document, image, or PDF
      - prompt is multi-paragraph (≥2 paragraphs)
      - prompt has a colon followed by 50+ chars of content (paste signal)
      - prompt has an explicit bullet list or numbered enumeration
      - prompt is long-form (≥80 words) — substantive paste-style prose
      - prompt has a paste marker like "[paste of...]" / "[image attached]"
      - prompt mentions an attached file ("attached PDF", "attachment")
      - prompt references prior conversation content ("shared earlier",
        "in this thread", "I posted earlier")
      - prompt has a quoted artifact (≥30 chars in quotes)
    """
    ctx = context or {}
    if ctx.get("image_path") or ctx.get("attached_document") or ctx.get("attachments"):
        return True
    if not user_prompt:
        return False
    # Multi-paragraph
    paragraph_count = len([p for p in user_prompt.split("\n\n") if p.strip()])
    if paragraph_count >= 2:
        return True
    # Colon followed by substantive content
    if re.search(r":\s+\S.{50,}", user_prompt):
        return True
    # Bullet list or numbered enumeration
    if re.search(r"(?:\n[-*]\s|\n\d+\.\s)", user_prompt):
        return True
    # Long-form paste
    if len(user_prompt.split()) >= 80:
        return True
    # Explicit paste / attachment markers — bracketed annotations like
    # "[paste of ...]", "[image attached]", "[attachment: ...]".
    if re.search(
        r"\[(?:paste|attached|image|attachment|file|pdf|both detailed below)"
        r"[^\]]*\]",
        user_prompt, re.IGNORECASE
    ):
        return True
    if re.search(r"\(paste\)|paste follows|follows below|both detailed below",
                 user_prompt, re.IGNORECASE):
        return True
    # Mention of an attached file in prose
    if re.search(
        r"\b(?:attached|attachment)\s+(?:pdf|document|file|image|memo|"
        r"paper|chart|diagram|screenshot|spreadsheet)\b",
        user_prompt, re.IGNORECASE
    ):
        return True
    # Prior-conversation references
    if re.search(
        r"\b(?:shared earlier|in this thread|earlier in this thread|"
        r"i (?:posted|pasted|shared|sent) earlier|the (?:article|document|"
        r"file|pdf|image) i (?:shared|posted|sent))\b",
        user_prompt, re.IGNORECASE
    ):
        return True
    # Long quoted content
    quoted = re.findall(r"['\"]([^'\"]{30,})['\"]", user_prompt)
    if quoted:
        return True
    return False


# Suffix-based field-name classification — covers the 100+ field names
# across the mode roster without curating every one explicitly.

_ARTIFACT_TEXT_SUFFIXES = (
    "_text", "_artifact", "_proposal", "_position",
    "_artifact_to_steelman", "_artifact_to_evaluate",
    "_image", "_photo", "_canvas",
    "_napkin_sketch_or_whiteboard_photo_or_canvas",
    "_artifact_with_resolvable_entity_ids",
    "argumentative_artifact",
)

_ENUMERATION_SUFFIXES = (
    "_inventory", "_set", "_list", "_estimates", "_estimate",
    "candidate_alternatives_named", "alternatives", "criteria",
    "stakeholders_named", "candidate_explanations",
    "candidate_causal_hypotheses", "candidate_causal_variables",
    "candidate_hypotheses", "candidate_stakeholder_inventory",
    "evidence_inventory", "frame_inventory", "stressor_inventory",
    "driving_force_inventory", "stakeholder_inventory",
    "intervention_candidates", "stated_positions", "hypothesis_set",
    "framework_a_named", "framework_b_named",
    "two_or_more_perspectives_to_compare",
    "two_or_more_topic_areas_to_connect",
)

_SUBJECT_NAMED_SUFFIXES = (
    "_question", "_query", "_subject", "_topic", "_concern",
    "_focus", "_horizon", "_dimension", "_axis", "_concept",
    "_term", "_phenomenon", "_name", "_role", "_identity",
    "_purpose", "_goal", "_criteria", "_criterion",
    "_audience", "_function", "_message", "_use_case",
    "_decision_at_hand", "_or_strategic_concern", "_or_topic",
    "_or_use_case", "behavior_to_be_explained", "domain_to_orient_in",
    "induction_goal", "ameliorative_purpose", "thesis_position",
    "comparison_axis", "professed_ideal_or_value",
    "user_party_role", "user_role_in_negotiation",
    "user_role_in_situation",
    "user_third_party_role_or_advisory_relationship",
    "user_current_level_of_understanding", "user_existing_familiarity",
    "current_user_knowledge_level", "format_request",
    "requested_format_specification", "intended_audience",
    "intended_audience_or_purpose", "intended_function",
    "intended_use_or_inhabitation_context",
    "intended_message_or_decision_supported",
    "salience_dimensions", "evaluation_criteria",
    "framework_preference", "weighting_preferences",
    "severity_threshold_preference", "audit_focus",
    "what_feels_excluded_or_naturalized", "why_it_feels_off",
    "sensed_tension", "sense_of_what_is_uncertain",
)

_SITUATION_SUFFIXES = (
    "_description", "_specification", "_situation", "_context",
    "_or_situation", "_or_decision", "_or_artifact", "_or_issue",
    "_or_claim_under_question", "_or_topic_user_is_new_to",
    "interaction_situation_described", "decision_description",
    "decision_statement", "deliverable_described",
    "deliverable_specification", "process_description",
    "system_description", "domain_or_situation_to_be_mapped",
    "domain_context", "domain_or_topic", "system_under_study",
    "system_or_design", "system_or_design_or_decision",
    "system_or_design_or_strategy", "system_or_situation",
    "system_or_strategy_description", "actors_described",
    "process_name_or_scope", "process_boundaries",
    "current_exposure_profile", "current_usage_problems",
    "current_batna_estimate",
    "scale_room_building_urban", "spatial_composition",
    "spatial_composition_or_place", "structural_components",
    "surrounding_community_or_network", "scope_constraints",
    "hard_constraints", "tension_or_opposition_described",
    "issue_or_disagreement", "problem_or_debate",
    "stated_goal_proposal_advances", "suspected_actual_function",
    "system_boundary_hypothesis", "intervention_question",
    "causal_question", "focal_claim_or_conclusion",
    "decision_or_choice_situation", "decision_context_user_owns",
    "decision_horizon", "decision_maker_identity",
    "event_or_case_description", "historical_event_or_case",
    "recurring_symptom", "recurring_symptom_description",
    "source_content", "source_content_reference",
    "affected_party_inventory",
)

_PRIOR_REFERENCE_PATTERNS = ("prior_", "previous_", "_history",
                              "attempted_interventions",
                              "prior_intervention_history",
                              "prior_fix_history", "prior_orientation_attempts",
                              "prior_user_engagement_with_each",
                              "prior_familiarity_level",
                              "prior_dialectical_attempts",
                              "prior_estimates",
                              "prior_probability_estimates")


# Per-field classification overrides. Keyed by exact field name; takes
# priority over the suffix-based heuristics below. These are the field
# names actually present across the 50+ mode files (audited 2026-05-02).
_FIELD_CLASSIFICATION_OVERRIDES = {
    # artifact_text — the user must paste / attach the actual content
    "argumentative_artifact": "artifact_text",
    "artifact": "artifact_text",
    "artifact_or_proposal": "artifact_text",
    "artifact_to_argue_against": "artifact_text",
    "artifact_to_stress_test": "artifact_text",
    "artifact_to_evaluate": "artifact_text",
    "named_artifact": "artifact_text",
    "paradigm_or_consensus_position": "artifact_text",
    "position_or_proposal": "artifact_text",
    "position_or_proposal_to_steelman": "artifact_text",
    "proposal_described": "artifact_text",
    "proposal_stated_precisely": "artifact_text",
    "proposed_action": "artifact_text",
    "proposed_action_or_event": "artifact_text",
    "spatial_artifact_with_resolvable_entity_ids": "artifact_text",
    "visual_input_napkin_sketch_or_whiteboard_photo_or_canvas": "artifact_text",
    "information_graphic": "artifact_text",
    "policy_memo_text": "artifact_text",
    "image_or_composition": "artifact_text",
    "place_description_or_image": "artifact_text",
    "chart_image": "artifact_text",
    "op_ed_text": "artifact_text",
    "argument_text": "artifact_text",
    "artifact_text": "artifact_text",
    "action_plan": "artifact_text",
    "action_plan_description": "artifact_text",
    "launch_plan_text": "artifact_text",

    # enumeration — needs explicit list of items
    "alternatives": "enumeration",
    "candidate_alternatives_named": "enumeration",
    "candidate_causal_hypotheses": "enumeration",
    "candidate_causal_variables": "enumeration",
    "candidate_explanations": "enumeration",
    "candidate_hypotheses": "enumeration",
    "candidate_stakeholder_inventory": "enumeration",
    "criteria": "enumeration",
    "criteria_list": "enumeration",
    "driving_force_inventory": "enumeration",
    "evidence_inventory": "enumeration",
    "frame_inventory": "enumeration",
    "framework_a_named": "enumeration",
    "framework_b_named": "enumeration",
    "hypothesis_set": "enumeration",
    "hypotheses_set": "enumeration",
    "intervention_candidates": "enumeration",
    "key_uncertainties": "enumeration",
    "known_actors_or_roles": "enumeration",
    "known_components": "enumeration",
    "option_set": "enumeration",
    "options_being_considered": "enumeration",
    "paradigm_inventory": "enumeration",
    "parties": "enumeration",
    "players_inventoried": "enumeration",
    "probability_estimates_or_ranges": "enumeration",
    "stakeholder_inventory": "enumeration",
    "stated_positions": "enumeration",
    "stressor_inventory": "enumeration",
    "two_or_more_perspectives_to_compare": "enumeration",
    "two_or_more_topic_areas_to_connect": "enumeration",
    "alternatives_set": "enumeration",
    "frame_set": "enumeration",
    "entities_named": "enumeration",

    # subject_named — satisfied by a concrete noun phrase
    "ameliorative_purpose": "subject_named",
    "audit_focus": "subject_named",
    "behavior_to_be_explained": "subject_named",
    "brief_purpose": "subject_named",
    "comparison_axis": "subject_named",
    "concept_or_term": "subject_named",
    "current_user_knowledge_level": "subject_named",
    "decision_horizon": "subject_named",
    "domain_name": "subject_named",
    "domain_to_orient_in": "subject_named",
    "evaluation_criteria": "subject_named",
    "focal_gap_question": "subject_named",
    "focal_question": "subject_named",
    "focal_question_or_strategic_concern": "subject_named",
    "focal_question_or_topic": "subject_named",
    "focal_question_or_use_case": "subject_named",
    "focal_voids_or_intervals_if_known": "subject_named",
    "forecast_question": "subject_named",
    "format_request": "subject_named",
    "forward_question": "subject_named",
    "framework_preference": "subject_named",
    "induction_goal": "subject_named",
    "intended_audience": "subject_named",
    "intended_audience_or_purpose": "subject_named",
    "intended_function": "subject_named",
    "intended_message_or_decision_supported": "subject_named",
    "intended_use_or_inhabitation_context": "subject_named",
    "mapping_purpose": "subject_named",
    "named_boundary_in_question": "subject_named",
    "named_external_audience": "subject_named",
    "orientation_purpose": "subject_named",
    "phenomenon": "subject_named",
    "phenomenon_or_concept": "subject_named",
    "phenomenon_or_question": "subject_named",
    "phenomenon_or_system": "subject_named",
    "phenomenon_to_explain": "subject_named",
    "planning_horizon": "subject_named",
    "professed_ideal_or_value": "subject_named",
    "requested_format_specification": "subject_named",
    "resolution_criteria": "subject_named",
    "salience_dimensions": "subject_named",
    "sense_of_what_is_uncertain": "subject_named",
    "sensed_tension": "subject_named",
    "severity_threshold_preference": "subject_named",
    "success_criteria": "subject_named",
    "subject_or_question": "subject_named",
    "target_audience": "subject_named",
    "target_concept": "subject_named",
    "thesis_position": "subject_named",
    "time_horizon": "subject_named",
    "time_horizon_of_interest": "subject_named",
    "topic_or_seed_thought": "subject_named",
    "user_current_level_of_understanding": "subject_named",
    "user_existing_familiarity": "subject_named",
    "user_party_role": "subject_named",
    "user_role_in_negotiation": "subject_named",
    "user_role_in_situation": "subject_named",
    "user_third_party_role_or_advisory_relationship": "subject_named",
    "utility_units": "subject_named",
    "weighting_preferences": "subject_named",
    "what_feels_excluded_or_naturalized": "subject_named",
    "why_it_feels_off": "subject_named",
    "concept_to_engineer": "subject_named",
    "concept_to_clarify": "subject_named",
    "concept": "subject_named",
    "domain_to_orient": "subject_named",
    "subject": "subject_named",
    "topic": "subject_named",
    "horizon": "subject_named",
    "historical_event": "subject_named",
    "event_specification": "subject_named",

    # situation — substantive prompt content
    "actors_described": "situation",
    "affected_party_inventory": "situation",
    "causal_question": "situation",
    "current_batna_estimate": "situation",
    "current_exposure_profile": "situation",
    "current_usage_problems": "situation",
    "decision_at_hand": "situation",
    "decision_context": "situation",
    "decision_context_user_owns": "situation",
    "decision_context_for_third_party": "situation",
    "decision_description": "situation",
    "decision_or_choice_situation": "situation",
    "decision_maker_identity": "situation",
    "decision_statement": "situation",
    "deliverable_described": "situation",
    "deliverable_specification": "situation",
    "domain_context": "situation",
    "domain_or_situation_to_be_mapped": "situation",
    "domain_or_topic": "situation",
    "domain_or_topic_user_is_new_to": "situation",
    "event_or_case_description": "situation",
    "focal_claim_or_conclusion": "situation",
    "hard_constraints": "situation",
    "historical_event_or_case": "situation",
    "interaction_situation_described": "situation",
    "intervention_question": "situation",
    "issue_or_disagreement": "situation",
    "issue_description": "situation",
    "move_order_or_information_structure": "situation",
    "observed_evidence": "situation",
    "observed_failure": "situation",
    "outcome_or_effect_of_interest": "situation",
    "outcome_or_pattern_description": "situation",
    "payoff_structure_or_value_terms": "situation",
    "problem_or_debate": "situation",
    "problem_statement": "situation",
    "problem_description": "situation",  # cui-bono lighter use; molecular tightens via composition
    "process_boundaries": "situation",
    "process_description": "situation",
    "process_name_or_scope": "situation",
    "recurring_symptom": "situation",
    "recurring_symptom_description": "situation",
    "relationship_types_understood": "situation",
    "scale_room_building_urban": "situation",
    "scope_constraints": "situation",
    "situation_or_artifact": "situation",
    "situation_or_claim_under_question": "situation",
    "situation_or_decision": "situation",
    "situation_or_issue": "situation",
    "situation_with_multiple_explanations": "situation",
    "situation_description": "situation",
    "source_content": "situation",
    "source_content_reference": "situation",
    "spatial_composition": "situation",
    "spatial_composition_or_place": "situation",
    "stated_goal_proposal_advances": "situation",
    "structural_components": "situation",
    "surrounding_community_or_network": "situation",
    "suspected_actual_function": "situation",
    "system_boundary_hypothesis": "situation",
    "system_description": "situation",
    "system_or_design": "situation",
    "system_or_design_or_decision": "situation",
    "system_or_design_or_strategy": "situation",
    "system_or_situation": "situation",
    "system_or_strategy_description": "situation",
    "system_under_study": "situation",
    "tension_or_opposition_described": "situation",
    "negotiation_context_specifics": "situation",
    "data_or_variables_set": "situation",
    "system_or_design_description": "situation",
    "conflict_description": "situation",
    "observed_failure_description": "situation",
    "this_situation": "situation",

    # artifact_text — additional plan/proposal/strategy fields
    "plan_description": "artifact_text",
    "launch_plan_description": "artifact_text",
    "strategy_description": "artifact_text",
    "situation_with_multiple_explanations": "enumeration",

    # prior_reference
    "prior_dialectical_attempts": "prior_reference",
    "prior_estimates": "prior_reference",
    "prior_familiarity_level": "prior_reference",
    "prior_fix_history": "prior_reference",
    "prior_intervention_history": "prior_reference",
    "prior_orientation_attempts": "prior_reference",
    "prior_probability_estimates": "prior_reference",
    "prior_user_engagement_with_each": "prior_reference",
    "attempted_interventions": "prior_reference",
    "prior_engineered_concept": "prior_reference",

    # generic — leave to substring fallback (very few)
    "position_proponents_or_canonical_sources": "generic",
    "contesting_evidence_or_alternative": "generic",
}


def _classify_field(field_name: str) -> str:
    """Categorize a required-field name into a detection bucket.

    Returns one of: 'artifact_text' | 'enumeration' | 'subject_named' |
    'situation' | 'prior_reference' | 'optional' | 'generic'.

    Per-field overrides win first. Suffix-based heuristics handle field
    names not in the override map (rare since the override map is curated
    against the actual mode files).
    """
    if field_name.startswith("optional_"):
        return "optional"

    if field_name in _FIELD_CLASSIFICATION_OVERRIDES:
        return _FIELD_CLASSIFICATION_OVERRIDES[field_name]

    for suf in _PRIOR_REFERENCE_PATTERNS:
        if field_name.startswith(suf) or field_name.endswith(suf) or field_name == suf:
            return "prior_reference"

    candidates: list[tuple[int, str]] = []
    for suf in _SITUATION_SUFFIXES:
        if field_name.endswith(suf) or field_name == suf:
            candidates.append((len(suf), "situation"))
    for suf in _ENUMERATION_SUFFIXES:
        if field_name.endswith(suf) or field_name == suf:
            candidates.append((len(suf), "enumeration"))
    for suf in _SUBJECT_NAMED_SUFFIXES:
        if field_name.endswith(suf) or field_name == suf:
            candidates.append((len(suf), "subject_named"))
    for suf in _ARTIFACT_TEXT_SUFFIXES:
        if field_name.endswith(suf) or field_name == suf.lstrip("_"):
            candidates.append((len(suf), "artifact_text"))

    if candidates:
        candidates.sort(key=lambda c: -c[0])
        return candidates[0][1]
    return "generic"


def _is_molecular_mode(mode_text: str) -> bool:
    """True if the mode_text declares molecular composition."""
    return bool(re.search(r"^composition:\s*molecular\s*$",
                          mode_text, re.MULTILINE))


def _detect_field_presence(field_name: str, user_prompt: str,
                           context: dict | None,
                           mode_text: str = "") -> bool:
    """Detect whether a required field is present in the prompt or context.

    Suffix-based field categorization (per ``_classify_field``) maps each
    field to a detection bucket, then bucket-specific rules check evidence.
    Molecular modes get tighter content requirements than atomic modes.
    """
    norm_prompt = _normalize_for_match(user_prompt)
    if not norm_prompt:
        return False

    category = _classify_field(field_name)
    word_count = len(norm_prompt.split())
    is_molecular = _is_molecular_mode(mode_text)
    has_artifact = _has_artifact_content(user_prompt, context)
    has_noun = _has_concrete_noun(user_prompt)
    ctx = context or {}

    # 1. Optional-prefix fields are not strictly required.
    if category == "optional":
        return True

    # 2. Artifact-text fields require actual content.
    if category == "artifact_text":
        return has_artifact

    # 3. Enumeration fields need explicit list of items (paste, bullets, or
    # multi-item phrasing like "X, Y, and Z").
    if category == "enumeration":
        if has_artifact:
            return True
        # In-prompt enumeration: "X, Y, and Z" or "three explanations: ..."
        if re.search(r"\b(?:two|three|four|five|six|seven|eight)\s+\S+", norm_prompt):
            return False  # the count is named but items not enumerated
        # Comma-separated list of three+ items
        if re.search(r"[A-Za-z]\w+,\s*[A-Za-z]\w+,?\s+(?:and\s+)?[A-Za-z]\w+",
                     user_prompt):
            return True
        return False

    # 4. Subject-named fields satisfied by concrete noun phrase. Domain-
    # induction-class molecular modes count as subject-named-satisfied
    # because the domain name alone is sufficient input. So we don't tighten
    # subject_named for molecular composition.
    if category == "subject_named":
        return has_noun

    # 5. Situation/context fields. Atomic modes need a concrete noun + ≥5
    # words. Molecular modes need substantive artifact-level content.
    if category == "situation":
        if is_molecular:
            return has_artifact
        return word_count >= 5 and has_noun

    # 6. Prior-conversation references — satisfied if context indicates
    # earlier conversation content or prompt explicitly references it.
    if category == "prior_reference":
        if ctx.get("prior_conversation") or ctx.get("history"):
            return True
        if re.search(r"(?:earlier|previous|shared earlier|"
                     r"i (?:posted|pasted|sent|shared)|in this thread)",
                     user_prompt, re.IGNORECASE):
            return True
        return False

    # 7. Generic fallback — substring tokens (length ≥ 5 to avoid false
    # positives on common short words).
    tokens = field_name.replace("_", " ").split()
    for tok in tokens:
        if len(tok) >= 5 and tok in norm_prompt:
            return True

    return False


def _select_contract_version(detection_text: str, user_prompt: str,
                             mode_id: str = "") -> str:
    """Apply detection rules to pick expert_mode vs accessible_mode.

    Uses word-boundary matching to avoid short-signal collisions
    (e.g., 'X' or 'Y' matching letters inside other words). Expert signals
    that match the mode_id verbatim (e.g., 'process tracing' for
    process-tracing mode) are treated as mode-name references, not as
    expert markers — they don't trigger expert_mode selection on their own.
    """
    expert_signals = _parse_detection_signals(detection_text, "expert")
    accessible_signals = _parse_detection_signals(detection_text, "accessible")
    mode_phrase = (mode_id or "").replace("-", " ").lower()

    # Filter out mode-name-aliases from expert signals
    real_expert_signals = []
    for sig in expert_signals:
        sig_norm = (sig or "").lower()
        if not sig_norm:
            continue
        if sig_norm == mode_phrase:
            continue
        # Single-word substring of the mode name doesn't count either
        if len(sig_norm.split()) == 1 and sig_norm in mode_phrase:
            continue
        real_expert_signals.append(sig)

    for sig in real_expert_signals:
        if _signal_present(user_prompt, sig):
            return "expert_mode"
    for sig in accessible_signals:
        if sig and _signal_present(user_prompt, sig):
            return "accessible_mode"
    # Default per Decision 3
    return "accessible_mode"


def _load_lighter_sibling(mode_text: str) -> str | None:
    """Read escalation_signals.downward.target_mode_id from a mode file."""
    m = re.search(
        r"escalation_signals:\s*\n(?:.*?\n)*?\s*downward:\s*\n\s*target_mode_id:\s*([^\n]+)",
        mode_text
    )
    if m:
        target = m.group(1).strip().strip("'\"")
        return None if target.lower() == "null" else target
    return None


def _mentions_artifact_without_content(user_prompt: str,
                                       context: dict | None) -> str | None:
    """Detect 'user names a typed artifact but didn't paste/attach it.'

    Returns the artifact-type phrase (e.g., "policy memo", "strategy") when
    the prompt references a typed artifact via "this/the/our/your X" but no
    actual content is present (no attachment, no multi-paragraph paste, no
    inline enumeration). Returns None when the prompt has full content or
    when the reference is generic.

    Also detects "these N <plural>" as a typed-but-unenumerated artifact
    reference (e.g., "these three vendor options", "these recurring outages").
    """
    if _has_artifact_content(user_prompt, context):
        return None  # actual content present — not an underspecified mention
    if not user_prompt:
        return None
    # When the prompt names an artifact AND adds substantive context after
    # it (e.g., "this zoning amendment that the city council passed last week
    # reducing setback requirements..."), treat the context as the artifact.
    # Threshold: if the prompt has 12+ words AND a relative-clause / "that"
    # / "which" / colon expanding on the named artifact, the user has
    # already described the artifact — don't ask for it again.
    if (len(user_prompt.split()) >= 12 and
        re.search(r"\b(?:that|which|where|who|because|since)\s+\w+",
                  user_prompt, re.IGNORECASE)):
        return None
    # Artifact types that need actual content (text or attachment) to analyze.
    artifact_types = {
        "argument", "op-ed", "op ed", "essay", "article", "paper",
        "memo", "brief", "policy memo", "white paper",
        "policy", "regulation", "law", "amendment", "bill",
        "plan", "launch plan", "rollout plan", "action plan",
        "strategy", "product strategy", "launch strategy", "marketing strategy",
        "design", "architecture", "system design", "supply-chain design",
        "supply chain design",
        "proposal", "pitch", "deck", "report",
        "initiative", "project", "program", "campaign",
        "diagram", "chart", "image", "layout", "dashboard",
        "dashboard layout", "dashboard design",
        "place", "library", "park", "building",
        "team conflict", "dispute",
        "exchange", "conversation",
        "code", "codebase",
    }
    norm = _normalize_for_match(user_prompt)
    # Allow zero to two adjectives between the determiner and the artifact:
    # "this strategy" / "this product strategy" / "this product launch strategy"
    # / "the old library" / "our Q3 launch plan"
    adj_pattern = r"(?:[a-z][a-z0-9-]*\s+){0,2}"
    for artifact in sorted(artifact_types, key=lambda s: -len(s)):
        pattern = (rf"\b(?:this|the|our|your|that|these)\s+"
                   rf"{adj_pattern}{re.escape(artifact)}\b")
        if re.search(pattern, norm):
            return artifact
    # "these N <plural>" pattern — count named but items not listed.
    # E.g., "these three vendor options", "these recurring outages",
    # "these candidates", "these scenarios", "these explanations".
    # Iterate all matches and pick any plural that signals enumeration.
    for m in re.finditer(
        r"\b(?:these|those)\s+"
        r"(?:(?:two|three|four|five|six|seven|eight|nine|ten|several|"
        r"multiple|many|all|recurring|various|some)\s+)?"
        r"([a-z]+(?:\s+[a-z]+)?)\b",
        norm
    ):
        noun = m.group(1).strip()
        if not noun or noun in _STOPWORDS_NOT_NOUNS:
            continue
        # Multi-word group: take last word as the head noun
        head = noun.split()[-1]
        if head.endswith("s") or head in {
            "options", "outages", "candidates", "explanations", "scenarios",
            "alternatives", "frames", "stakeholders", "hypotheses",
            "factors", "items", "interventions", "actors", "parties",
        }:
            return noun
    return None


def stage3_input_completeness_check(mode_id: str, user_prompt: str,
                                    context: dict | None = None) -> dict:
    """Stage 3 of the pre-routing pipeline: input completeness check.

    Verifies the dispatched mode's required inputs are present per its
    dual input_contract. Surfaces missing or underspecified inputs and
    either elicits them or offers graceful degradation to a sibling mode.
    Per spec §Stage 3.

    Returns:
        {
            "inputs_complete": bool,
            "validated_inputs": dict,
            "missing_fields": [<field>],
            "completeness_question": str | None,
            "graceful_degradation_offer": str | None,
            "lighter_sibling_mode_id": str | None,
            "stage3_status": "complete" | "missing-input-elicited"
                            | "graceful-degradation-offered",
        }
    """
    mode_text = load_mode(mode_id)
    if not mode_text:
        # Mode file missing — still check for artifact-mention before passing.
        ref_art = _mentions_artifact_without_content(user_prompt, context)
        if ref_art:
            synthetic = f"{ref_art.replace(' ', '_')}_text"
            return {
                "inputs_complete": False,
                "validated_inputs": {},
                "missing_fields": [synthetic],
                "completeness_question": (
                    f"To run this analysis, I need the {ref_art}. "
                    f"Could you paste it or attach it?"
                ),
                "graceful_degradation_offer": None,
                "lighter_sibling_mode_id": None,
                "stage3_status": "missing-input-elicited",
                "warning": f"mode file not found: {mode_id}",
            }
        return {
            "inputs_complete": True,
            "validated_inputs": {"prompt": user_prompt},
            "missing_fields": [],
            "completeness_question": None,
            "graceful_degradation_offer": None,
            "lighter_sibling_mode_id": None,
            "stage3_status": "complete",
            "warning": f"mode file not found: {mode_id}",
        }

    contract = _parse_input_contract(mode_text)
    if not contract:
        # No structured input contract — still check artifact-mention.
        ref_art = _mentions_artifact_without_content(user_prompt, context)
        if ref_art:
            synthetic = f"{ref_art.replace(' ', '_')}_text"
            return {
                "inputs_complete": False,
                "validated_inputs": {},
                "missing_fields": [synthetic],
                "completeness_question": (
                    f"To run this analysis, I need the {ref_art}. "
                    f"Could you paste it or attach it?"
                ),
                "graceful_degradation_offer": None,
                "lighter_sibling_mode_id": None,
                "stage3_status": "missing-input-elicited",
                "warning": "no input_contract block in mode file",
            }
        return {
            "inputs_complete": True,
            "validated_inputs": {"prompt": user_prompt},
            "missing_fields": [],
            "completeness_question": None,
            "graceful_degradation_offer": None,
            "lighter_sibling_mode_id": None,
            "stage3_status": "complete",
            "warning": "no input_contract block in mode file",
        }

    detection = contract.get("detection", "")
    contract_version = _select_contract_version(detection, user_prompt, mode_id)
    selected = contract.get(contract_version, "")
    required = _parse_required_fields(selected)

    # Top-level artifact-mention check: if the prompt references a typed
    # artifact ("this strategy", "the policy memo") without supplying its
    # actual content, the input is underspecified regardless of which field
    # the mode declares. This catches cases where the corpus expects a
    # field name the mode-spec doesn't have.
    referenced_artifact = _mentions_artifact_without_content(user_prompt, context)

    missing: list[str] = []
    validated: dict = {}
    for field_name in required:
        if _detect_field_presence(field_name, user_prompt, context, mode_text):
            validated[field_name] = "present (detected from prompt or context)"
        else:
            missing.append(field_name)

    # If the prompt referenced a typed artifact without content, surface
    # that as a missing input even when the declared fields all read present.
    if referenced_artifact and not missing:
        # Record a synthetic missing-field name so the user gets a prompt.
        missing.append(f"{referenced_artifact.replace(' ', '_')}_text")

    if not missing:
        return {
            "inputs_complete": True,
            "validated_inputs": validated,
            "missing_fields": [],
            "completeness_question": None,
            "graceful_degradation_offer": None,
            "lighter_sibling_mode_id": None,
            "stage3_status": "complete",
            "contract_version": contract_version,
        }

    # Missing fields — load graceful_degradation prompt.
    degradation = _parse_graceful_degradation(contract.get("graceful_degradation", ""))
    completeness_question = degradation.get("on_missing_required")
    if not completeness_question:
        # Fall back to plain-language pattern per Style Guide §5.8.1
        first_missing = missing[0].replace("_", " ")
        completeness_question = (
            f"To run this analysis, I need the {first_missing}. "
            f"Could you share it?"
        )

    lighter_sibling = _load_lighter_sibling(mode_text)
    graceful_offer = None
    if lighter_sibling:
        # Compose the graceful-degradation offer per Style Guide §5.8.3
        graceful_offer = (
            f"I can take a lighter pass with what's here, or wait for "
            f"more detail and run the fuller analysis. Which would you like?"
        )

    return {
        "inputs_complete": False,
        "validated_inputs": validated,
        "missing_fields": missing,
        "completeness_question": completeness_question,
        "graceful_degradation_offer": graceful_offer,
        "lighter_sibling_mode_id": lighter_sibling,
        "stage3_status": (
            "graceful-degradation-offered" if graceful_offer
            else "missing-input-elicited"
        ),
        "contract_version": contract_version,
    }


# ---------------------------------------------------------------------------
# Phase 9 — Pre-routing pipeline orchestration entry point
# ---------------------------------------------------------------------------

def run_pre_routing_pipeline(prompt: str,
                             context: dict | None = None,
                             disambiguation_answer: str | None = None,
                             completeness_answer: str | None = None) -> dict:
    """Run Stages 1-3 of the pre-routing pipeline against a user prompt.

    Returns a routing decision the orchestrator can act on — either a
    dispatched mode_id ready for Stage 4 execution, or a question to surface
    to the user via the clarification panel.

    The clarification flow:
      - Stage 2 surfaces a disambiguation question → server pauses pipeline,
        emits clarification event, receives the user's answer, then re-runs
        with disambiguation_answer set.
      - Stage 3 surfaces a completeness question → server pauses, gathers
        the missing input, re-runs with completeness_answer appended to the
        prompt.

    Returns:
        {
            "stage1_output": dict,
            "stage2_output": dict,
            "stage3_output": dict | None,
            "dispatched_mode_id": str | None,
            "bypass_to_direct_response": bool,
            "pending_clarification": str | None,   # question to ask user
            "pending_clarification_stage": str | None,  # "stage2" | "stage3"
            "territory": str | None,
            "confidence": str,
            "completeness_gaps": [str],
            "dispatch_announcement": str | None,
        }
    """
    context = context or {}
    full_prompt = prompt
    if completeness_answer:
        full_prompt = f"{prompt}\n\n[User clarification]\n{completeness_answer}"

    # --- Stage 1 ---
    s1 = stage1_pre_analysis_filter(full_prompt, context)
    if s1["bypass_to_direct_response"]:
        return {
            "stage1_output": s1,
            "stage2_output": None,
            "stage3_output": None,
            "dispatched_mode_id": None,
            "bypass_to_direct_response": True,
            "pending_clarification": None,
            "pending_clarification_stage": None,
            "territory": None,
            "confidence": "n/a",
            "completeness_gaps": [],
            "dispatch_announcement": None,
        }

    # --- Stage 2 ---
    s2 = stage2_sufficiency_analyzer(full_prompt, s1, context)
    if disambiguation_answer:
        # Re-evaluate Stage 2 with the user's answer appended
        merged = f"{full_prompt}\n[Answered: {disambiguation_answer}]"
        s2_after = stage2_sufficiency_analyzer(
            merged, stage1_pre_analysis_filter(merged, context), context
        )
        if s2_after["dispatched_mode_id"]:
            s2 = s2_after
        # else fall through and use defaults below

    if not s2["dispatched_mode_id"]:
        # Default-on-ambiguity per Style Guide §5.6 if user supplied an
        # answer but it wasn't strong enough to dispatch — pick a Tier-2
        # default by surfacing the question (caller decides whether to
        # re-prompt or default).
        if not s2["disambiguation_questions_asked"]:
            return {
                "stage1_output": s1,
                "stage2_output": s2,
                "stage3_output": None,
                "dispatched_mode_id": None,
                "bypass_to_direct_response": False,
                "pending_clarification": _GENERIC_INTENT_QUESTION,
                "pending_clarification_stage": "stage2",
                "territory": None,
                "confidence": "low",
                "completeness_gaps": [],
                "dispatch_announcement": None,
            }
        return {
            "stage1_output": s1,
            "stage2_output": s2,
            "stage3_output": None,
            "dispatched_mode_id": None,
            "bypass_to_direct_response": False,
            "pending_clarification": s2["disambiguation_questions_asked"][0],
            "pending_clarification_stage": "stage2",
            "territory": s2.get("territory"),
            "confidence": s2["confidence"],
            "completeness_gaps": [],
            "dispatch_announcement": None,
        }

    # --- Stage 3 ---
    mode_id = s2["dispatched_mode_id"]
    s3 = stage3_input_completeness_check(mode_id, full_prompt, context)

    if not s3["inputs_complete"]:
        # Completeness question first; graceful-degradation offer second if available
        question = s3["completeness_question"]
        if s3["graceful_degradation_offer"]:
            question = f"{question}\n\n{s3['graceful_degradation_offer']}"
        # Surface fuzzy-match and shape-mismatch notes alongside the
        # completeness question so the user sees them before answering.
        did_you_mean_early = s2.get("did_you_mean_note")
        shape_mismatch_early = s2.get("shape_mismatch_note")
        prefix_parts_early = [p for p in (did_you_mean_early, shape_mismatch_early) if p]
        if prefix_parts_early:
            question = "\n\n".join(prefix_parts_early + [question])
        return {
            "stage1_output": s1,
            "stage2_output": s2,
            "stage3_output": s3,
            "dispatched_mode_id": mode_id,
            "bypass_to_direct_response": False,
            "pending_clarification": question,
            "pending_clarification_stage": "stage3",
            "territory": s2.get("territory"),
            "confidence": s2["confidence"],
            "completeness_gaps": s3.get("missing_fields", []),
            "dispatch_announcement": None,
            "lighter_sibling_mode_id": s3.get("lighter_sibling_mode_id"),
            "did_you_mean_note": did_you_mean_early,
            "shape_mismatch_note": shape_mismatch_early,
        }

    # All stages passed — compose the dispatch announcement for Stage 4.
    announcement = compose_dispatch_announcement(mode_id, prompt)

    # Phase 9.5 — surface fuzzy-match and shape-mismatch notes via the
    # dispatch announcement so the user sees them before the analysis runs.
    did_you_mean = s2.get("did_you_mean_note")
    shape_mismatch = s2.get("shape_mismatch_note")
    prefix_parts = []
    if did_you_mean:
        prefix_parts.append(did_you_mean)
    if shape_mismatch:
        prefix_parts.append(shape_mismatch)
    full_announcement = announcement
    if prefix_parts:
        full_announcement = "\n\n".join(prefix_parts + [announcement])

    return {
        "stage1_output": s1,
        "stage2_output": s2,
        "stage3_output": s3,
        "dispatched_mode_id": mode_id,
        "bypass_to_direct_response": False,
        "pending_clarification": None,
        "pending_clarification_stage": None,
        "territory": s2.get("territory"),
        "confidence": s2["confidence"],
        "completeness_gaps": [],
        "dispatch_announcement": full_announcement,
        "did_you_mean_note": did_you_mean,
        "shape_mismatch_note": shape_mismatch,
    }


def get_mode_registry_summary() -> str:
    """Build a compact mode registry for Step 1 mode selection."""
    lines = []
    for path in sorted(globmod.glob(os.path.join(MODES_DIR, "*.md"))):
        name = os.path.basename(path).replace(".md", "")
        # Extract trigger conditions from the mode file
        try:
            with open(path) as f:
                content = f.read()
            # Pull the first line after TRIGGER CONDITIONS heading
            match = re.search(
                r'## TRIGGER CONDITIONS\s*\n\s*\n?(Positive triggers:.*?)(?:\n\n|\nNegative)',
                content, re.DOTALL
            )
            trigger = match.group(1).strip()[:200] if match else ""
        except Exception:
            trigger = ""
        lines.append(f"- **{name}**: {trigger}")
    return "\n".join(lines)


def extract_default_gear(mode_text: str) -> int:
    """Extract the default gear from a mode file."""
    match = re.search(r'## DEFAULT GEAR\s*\n\s*\n?\s*Gear\s*(\d)', mode_text)
    if match:
        return int(match.group(1))
    return 2  # Default to Gear 2 if not specified


def parse_step1_output(response: str) -> dict:
    """Parse Phase A cleanup output. Mode/tier parsing is handled separately
    by parse_classification_output() in the Phase A.5 pass."""
    result = {
        "cleaned_prompt": "",
        "operational_notation": "",
        "mode": "adversarial",
        "triage_tier": 1,
        "corrections_log": "",
        "inferred_items": "",
        "raw_response": response,
    }

    # Extract Operational Notation version (preferred for pipeline)
    on_match = re.search(
        r'### CLEANED PROMPT \(Operational Notation\)\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if on_match:
        result["operational_notation"] = on_match.group(1).strip()

    # Extract Natural Language version (fallback)
    nl_match = re.search(
        r'### CLEANED PROMPT \(Natural Language\)\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if nl_match:
        result["cleaned_prompt"] = nl_match.group(1).strip()

    # Use operational notation if available, otherwise natural language
    if not result["operational_notation"] and result["cleaned_prompt"]:
        result["operational_notation"] = result["cleaned_prompt"]
    elif not result["cleaned_prompt"] and result["operational_notation"]:
        result["cleaned_prompt"] = result["operational_notation"]

    # If parsing failed entirely, use raw response as the cleaned prompt.
    # Surface this loudly: without a warning, a malformed Phase A response
    # silently replaces the user's prompt with the model's narrative reply
    # ("Sure, I'd be happy to help. Could you share the draft?") and the
    # downstream pipeline treats that as the user's intent. Trace consumers
    # read `phase_a_parse_failed` to flag the substitution.
    if not result["cleaned_prompt"]:
        print(
            "[parse_step1_output] Phase A output unparseable — neither "
            "'### CLEANED PROMPT (Operational Notation)' nor '### CLEANED "
            "PROMPT (Natural Language)' headings found. Using raw response "
            "as the cleaned prompt; downstream pipeline may run against "
            "the model's narrative rather than the user's actual input.",
            file=sys.stderr,
            flush=True,
        )
        result["cleaned_prompt"] = response
        result["operational_notation"] = response
        result["phase_a_parse_failed"] = True

    # Extract corrections log
    corr_match = re.search(
        r'### CORRECTIONS_LOG\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if corr_match:
        result["corrections_log"] = corr_match.group(1).strip()

    # Extract inferred items
    inf_match = re.search(
        r'### INFERRED_ITEMS\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if inf_match:
        result["inferred_items"] = inf_match.group(1).strip()

    return result


def parse_classification_output(response: str) -> dict:
    """Parse Phase A.5 mode classification output.

    Expected format from the Mode Classification Directory:
        ### MODE CLASSIFICATION
        - Selected mode: mode-name
        - Runner-up: mode-name
        - Confidence: high/medium/low
        - Intent category: LEARNING/DECIDING/etc.
        - Reasoning: one sentence
        - Triage tier: 1/2/3
        - Detected invocation: mode-name or NONE  (V3 Phase 1 — prose-level invocation)

    ``detected_invocation`` is an empty string when absent or "NONE"; otherwise
    a mode name validated against MODES_DIR. Used by the alignment prefilter
    to compare the user's expressed intent against the picked mode.
    """
    result = {
        "mode": "adversarial",
        "runner_up": "",
        "confidence": "low",
        "intent_category": "",
        "reasoning": "",
        "triage_tier": 1,
        "detected_invocation": "",
    }

    # Strip thinking blocks before parsing
    cleaned = _extract_final_response(response)

    # Extract selected mode (use findall + reversed to skip any echoed templates)
    mode_matches = re.findall(r'Selected mode:\s*(\S+)', cleaned)
    for mode_candidate in reversed(mode_matches):
        mode_name = mode_candidate.strip().rstrip(".,")
        if mode_name.startswith("["):
            continue  # Skip template placeholders like [mode-name]
        if os.path.exists(os.path.join(MODES_DIR, f"{mode_name}.md")):
            result["mode"] = mode_name
            break

    # Extract runner-up
    runner_matches = re.findall(r'Runner-up:\s*(\S+)', cleaned)
    for runner_candidate in reversed(runner_matches):
        name = runner_candidate.strip().rstrip(".,")
        if not name.startswith("["):
            result["runner_up"] = name
            break

    # Extract confidence
    conf_match = re.search(r'Confidence:\s*(high|medium|low)', cleaned, re.IGNORECASE)
    if conf_match:
        result["confidence"] = conf_match.group(1).lower()

    # Extract intent category
    intent_match = re.search(
        r'Intent category:\s*(LEARNING|DECIDING|BUILDING|ANALYZING|CONNECTING|QUESTIONING|EXPLORING)',
        cleaned, re.IGNORECASE
    )
    if intent_match:
        result["intent_category"] = intent_match.group(1).upper()

    # Extract reasoning
    reason_match = re.search(r'Reasoning:\s*(.+?)(?:\n|$)', cleaned)
    if reason_match:
        result["reasoning"] = reason_match.group(1).strip()

    # Extract triage tier (use last match)
    tier_matches = re.findall(r'Triage tier:\s*(\d)', cleaned)
    if tier_matches:
        result["triage_tier"] = int(tier_matches[-1])

    # V3 Phase 1: extract detected prose-level invocation. Validates against
    # MODES_DIR; "NONE" / template placeholders / unknown names → empty string
    # (treated as no invocation). Use last match to skip echoed templates.
    invocation_matches = re.findall(r'Detected invocation:\s*(\S+)', cleaned)
    for invocation_candidate in reversed(invocation_matches):
        name = invocation_candidate.strip().rstrip(".,")
        if name.startswith("[") or name.upper() == "NONE":
            break  # Explicit no-invocation; leave default empty string
        if os.path.exists(os.path.join(MODES_DIR, f"{name}.md")):
            result["detected_invocation"] = name
            break

    return result


def _diff_raw_vs_operational(raw_prompt: str, operational_notation: str) -> dict:
    """Surface tokens present in operational_notation but absent from the
    raw prompt — Phase-A-fabricated content that would otherwise propagate
    downstream as if user-stated.

    The model is supposed to expand and rewrite, so some new tokens are
    legitimate (verbs, operators, structural markers). The signal worth
    flagging is *concrete-noun* additions: capitalised words, numbers,
    dates, named entities. These are the high-risk class for the
    confabulated-constraint failure mode.

    Returns a dict with token-count summaries plus a sample of suspect
    additions for the trace. Conservative — produces false positives
    that an auditor reads and dismisses, rather than missing real cases.
    """
    if not raw_prompt or not operational_notation:
        return {"diff_computed": False, "reason": "missing input"}

    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[A-Za-z][A-Za-z0-9_'-]*|\d+(?:\.\d+)?", text or ""))

    raw_lower = (raw_prompt or "").lower()
    op_tokens = _tokens(operational_notation)

    # Heuristic suspect classes — capitalised words (proper nouns),
    # standalone numbers (statistics / dates / years), 4-digit years.
    cap_word_re = re.compile(r"^[A-Z][A-Za-z0-9_'-]*$")
    number_re = re.compile(r"^\d+(?:\.\d+)?$")
    year_re = re.compile(r"^(19|20|21)\d{2}$")

    new_caps: list[str] = []
    new_numbers: list[str] = []
    new_years: list[str] = []
    for tok in sorted(op_tokens):
        if tok.lower() in raw_lower:
            continue
        if year_re.match(tok):
            new_years.append(tok)
        elif number_re.match(tok):
            new_numbers.append(tok)
        elif cap_word_re.match(tok):
            new_caps.append(tok)

    # Filter common phase-A vocabulary (verbs, lens names, operator tokens).
    PHASE_A_VOCAB = {
        "AUDIT", "ANALYZE", "ANALYSE", "EVALUATE", "REQUEST", "GOAL",
        "TASK", "CONTEXT", "CONSTRAINT", "EXPECTED", "STAKEHOLDER",
        "STAKEHOLDERS", "ASSUMPTION", "ASSUMPTIONS", "INPUT", "OUTPUT",
        "MODE", "GEAR", "STAGE", "PHASE", "PROMPT", "USER", "FRAMEWORK",
        "CRITERIA", "OBJECTIVE", "OBJECTIVES", "DELIVERABLE",
    }
    new_caps = [t for t in new_caps if t not in PHASE_A_VOCAB]

    suspect_count = len(new_caps) + len(new_numbers) + len(new_years)
    return {
        "diff_computed": True,
        "raw_prompt_chars": len(raw_prompt),
        "operational_notation_chars": len(operational_notation),
        "new_capitalised_tokens": new_caps[:20],
        "new_capitalised_count": len(new_caps),
        "new_numeric_tokens": new_numbers[:10],
        "new_numeric_count": len(new_numbers),
        "new_year_tokens": new_years[:5],
        "new_year_count": len(new_years),
        "total_suspect_additions": suspect_count,
        # Audit flag: any concrete noun additions warrant a human spot-check
        # of whether Phase A invented a constraint or stakeholder.
        "phase_a_added_concrete_nouns": suspect_count > 0,
    }


def _summarize_history_truncation(history: list | None,
                                   window: int = 6,
                                   per_message_char_cap: int = 500) -> dict:
    """Compute how much of the original history the conv-context-builder
    actually included vs dropped.

    The conversation context Phase A sees is the last ``window`` non-system
    messages, each truncated to ``per_message_char_cap`` chars. For
    long-running threads this silently loses material. The returned dict
    is suitable for embedding in the step1-phase-a trace so an auditor
    can see when context was actually cut.
    """
    if not history:
        return {
            "history_present": False,
            "total_messages": 0,
            "non_system_messages": 0,
            "messages_in_window": 0,
            "messages_outside_window": 0,
            "per_message_char_cap": per_message_char_cap,
            "messages_truncated_by_cap": 0,
            "chars_lost_to_cap_total": 0,
            "any_truncation": False,
        }
    non_system = [m for m in history if m.get("role") != "system"]
    in_window = non_system[-window:] if window else non_system
    msgs_truncated = 0
    chars_lost = 0
    for m in in_window:
        body = m.get("content") or ""
        if len(body) > per_message_char_cap:
            msgs_truncated += 1
            chars_lost += len(body) - per_message_char_cap
    outside = max(0, len(non_system) - len(in_window))
    return {
        "history_present": True,
        "total_messages": len(history),
        "non_system_messages": len(non_system),
        "messages_in_window": len(in_window),
        "messages_outside_window": outside,
        "per_message_char_cap": per_message_char_cap,
        "messages_truncated_by_cap": msgs_truncated,
        "chars_lost_to_cap_total": chars_lost,
        "any_truncation": outside > 0 or msgs_truncated > 0,
    }


def run_step1_cleanup(raw_prompt: str, conversation_context: str,
                      config: dict, ambiguity_mode: str = "assume",
                      trace_dir: str | None = None,
                      history_truncation_stats: dict | None = None) -> dict:
    """Step 1: Two-pass prompt processing.

    Pass 1 (Phase A): Prompt cleanup only — no mode selection.
    Pass 2 (Phase A.5): Dedicated mode classification using the Mode Classification Directory.

    Returns parsed results including cleaned prompt, mode, and triage tier.

    ``trace_dir`` is the per-turn forensic-trace directory created by
    ``pipeline_trace.start_trace``. Pass ``None`` to disable tracing.
    """
    # --- Pre-Phase-A bypass check ---
    # Runs bypass detection on the *raw* user prompt before Phase A's
    # expansion. Fixes the detector-layering bug where Phase A's expanded
    # operational notation either masked or false-positive-matched the
    # post-expansion Stage 1 detector. When this fires, Phase A AND
    # pre-routing are skipped entirely; the raw prompt goes through as
    # the cleaned prompt, mode=simple, gear=2.
    early_bypass = pre_phase_a_bypass_check(raw_prompt)
    if early_bypass is not None:
        result = {
            "cleaned_prompt": raw_prompt,
            "operational_notation": raw_prompt,
            "mode": "simple",
            "triage_tier": 1,
            "corrections_log": "",
            "inferred_items": "",
            "raw_response": "",
            "detected_invocation": "",
            "classification_confidence": "high",
            "classification_runner_up": "",
            "classification_reasoning": early_bypass["rationale"],
            "classification_intent": "SIMPLE",
            "pre_routing": {
                "dispatched_mode_id": None,
                "territory": None,
                "bypass_to_direct_response": True,
                "pending_clarification": None,
                "pending_clarification_stage": None,
                "completeness_gaps": [],
                "dispatch_announcement": None,
                "lighter_sibling_mode_id": None,
                "confidence": "high",
                "stage1_match_count": 0,
                "pre_phase_a_bypass": True,
                "pre_phase_a_rationale": early_bypass["rationale"],
            },
        }
        if PIPELINE_TRACE_AVAILABLE:
            pipeline_trace.write_step(trace_dir, "step1-phase-a", {
                "status": "skipped_pre_phase_a_bypass",
                "raw_prompt": raw_prompt,
                "conversation_context_present": bool(conversation_context),
                "ambiguity_mode": ambiguity_mode,
                "bypass_rationale": early_bypass["rationale"],
            }, markdown=(
                "# Step 1 — Phase A SKIPPED (pre-Phase-A bypass)\n\n"
                f"**Raw prompt:** {raw_prompt}\n\n"
                f"**Bypass rationale:** {early_bypass['rationale']}\n\n"
                "Phase A and the four-stage pre-routing pipeline were "
                "both skipped. The prompt was detected as a "
                "chitchat / lookup / system-command by the pre-Phase-A "
                "trigger scan on the raw prompt. mode=`simple`, gear=2.\n"
            ))
            pipeline_trace.write_step(trace_dir, "step1-pre-routing", {
                "status": "skipped_pre_phase_a_bypass",
                "rationale": early_bypass["rationale"],
            }, markdown=(
                "# Step 1 — Pre-Routing SKIPPED\n\n"
                f"**Reason:** Pre-Phase-A bypass fired.\n"
                f"**Rationale:** {early_bypass['rationale']}\n"
            ))
        return result

    # --- Pass 1: Phase A — Cleanup Only ---
    phase_a = load_framework("phase-a-prompt-cleanup.md")

    system_prompt = f"""{phase_a}

AMBIGUITY_MODE: {ambiguity_mode}
"""

    # Build user message with conversation context if available
    user_msg = raw_prompt
    if conversation_context:
        user_msg = (
            f"[Recent conversation context]\n{conversation_context}\n\n"
            f"[Current prompt]\n{raw_prompt}"
        )

    endpoint = get_slot_endpoint(config, "step1_cleanup")
    if endpoint is None:
        # No step1_cleanup model — pass through uncleaned
        result = {
            "cleaned_prompt": raw_prompt,
            "operational_notation": raw_prompt,
            "mode": "adversarial",
            "triage_tier": 1,
            "corrections_log": "",
            "inferred_items": "",
            "raw_response": "",
            "detected_invocation": "",
        }
        # Trace: record that no cleanup model was available
        if PIPELINE_TRACE_AVAILABLE:
            pipeline_trace.write_step(trace_dir, "step1-phase-a", {
                "status": "no_cleanup_model",
                "raw_prompt": raw_prompt,
                "conversation_context_present": bool(conversation_context),
                "ambiguity_mode": ambiguity_mode,
                "passthrough_result": result,
            }, markdown=(
                "# Step 1 — Phase A (Prompt Cleanup)\n\n"
                "**Status:** no `step1_cleanup` model configured. "
                "Raw prompt passed through unchanged.\n\n"
                f"## Raw prompt\n\n{raw_prompt}\n"
            ))
        return result

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    cleanup_response = call_model(messages, endpoint)
    step1_result = parse_step1_output(cleanup_response)
    # Preserve the user's actual sentence on step1_result so downstream
    # steps (step 2 context assembly, the analyst/eval/verify user-message
    # construction) can present the user's actual words alongside Phase
    # A's clarified interpretation rather than substituting one for the
    # other. parse_step1_output only knows the model response, not the
    # raw input; this is the only place we have both in scope.
    step1_result["raw_prompt"] = raw_prompt

    # --- Trace: Phase A inputs and parsed outputs ---
    if PIPELINE_TRACE_AVAILABLE:
        pipeline_trace.write_step(trace_dir, "step1-phase-a", {
            "status": "parse_failed" if step1_result.get("phase_a_parse_failed") else "ok",
            "phase_a_parse_failed": bool(step1_result.get("phase_a_parse_failed")),
            "raw_prompt": raw_prompt,
            "conversation_context": conversation_context,
            "conversation_context_present": bool(conversation_context),
            "ambiguity_mode": ambiguity_mode,
            "endpoint_used": endpoint.get("name") if isinstance(endpoint, dict) else str(endpoint),
            "system_prompt_chars": len(system_prompt),
            "user_message_chars": len(user_msg),
            "raw_response": cleanup_response,
            "parsed": {
                "cleaned_prompt": step1_result.get("cleaned_prompt", ""),
                "operational_notation": step1_result.get("operational_notation", ""),
                "corrections_log": step1_result.get("corrections_log", ""),
                "inferred_items": step1_result.get("inferred_items", ""),
                "detected_invocation": step1_result.get("detected_invocation", ""),
            },
            # History-truncation audit (closes silent context-loss class):
            # records when the conv-context-builder dropped messages outside
            # the window or truncated long messages at the per-message cap.
            "history_truncation": history_truncation_stats or {
                "history_present": bool(conversation_context),
                "stats_not_provided_by_caller": True,
            },
            # Phase A raw-vs-operational diff — flag concrete-noun additions
            # that Phase A introduced. The downstream pipeline treats
            # operational_notation as user-stated; fabricated constraints,
            # stakeholders, statistics, or dates would propagate as if
            # the user had said them. The diff surfaces additions for
            # auditor review without blocking the pipeline.
            "phase_a_diff": _diff_raw_vs_operational(
                raw_prompt,
                step1_result.get("operational_notation", "") or "",
            ),
        }, markdown=(
            "# Step 1 — Phase A (Prompt Cleanup)\n\n"
            f"## Raw prompt\n\n{raw_prompt}\n\n"
            f"## Conversation context\n\n"
            f"{conversation_context or '_(none)_'}\n\n"
            f"## Cleaned (natural language)\n\n"
            f"{step1_result.get('cleaned_prompt', '_(empty)_')}\n\n"
            f"## Operational notation\n\n"
            f"{step1_result.get('operational_notation', '_(empty)_')}\n\n"
            f"## Corrections log\n\n"
            f"{step1_result.get('corrections_log', '_(empty)_')}\n\n"
            f"## Inferred items (assume-mode assumptions)\n\n"
            f"{step1_result.get('inferred_items', '_(empty)_')}\n"
        ))

    # --- Pass 2: Pre-routing pipeline (replaces Phase A.5) ---
    # Phase 9: the four-stage pre-routing pipeline replaces the retired
    # Mode Classification Directory's intent-classification flow. Stage 1
    # filters bypass prompts; Stage 2 picks a mode from signal vocabulary
    # plus disambiguation; Stage 3 checks input completeness; Stage 4
    # (mode execution) happens downstream in run_pipeline.
    #
    # IMPORTANT: pre-routing matches against the RAW prompt, not Phase A's
    # operational notation. The signal-vocabulary registry is written in
    # natural-language phrases ("cui bono", "who benefits", "argument audit");
    # Phase A's operational form replaces those with underscore-tokenized
    # function calls ("cui_bono_analysis(...)") that no signal matches.
    # Passing operational_notation here caused every analytical prompt to
    # match zero signals and fall through to ANALYZING_FALLBACK / pending
    # clarification. The expanded form is for downstream model dispatch
    # (step 3+); pre-routing is signal classification and must see the
    # user's actual words.
    routing = run_pre_routing_pipeline(
        prompt=raw_prompt,
        context=None,
    )

    # --- Dual-dispatch audit ---
    # Observability: also run pre-routing against Phase A's expanded form
    # and surface any disagreement in the trace. Helps spot cases where
    # Phase A's interpretation would have routed differently (either by
    # introducing signals the user didn't say or by suppressing signals
    # the user did say). Operational dispatch uses the raw-prompt routing
    # decision above.
    dispatch_audit = None
    try:
        expanded_routing = run_pre_routing_pipeline(
            prompt=step1_result["operational_notation"], context=None,
        )
        raw_mode = routing.get("dispatched_mode_id")
        expanded_mode = expanded_routing.get("dispatched_mode_id")
        raw_bypass = routing.get("bypass_to_direct_response", False)
        expanded_bypass = expanded_routing.get("bypass_to_direct_response", False)
        dispatch_audit = {
            "raw_dispatched_mode_id": raw_mode,
            "expanded_dispatched_mode_id": expanded_mode,
            "raw_bypass": raw_bypass,
            "expanded_bypass": expanded_bypass,
            "raw_confidence": routing.get("confidence"),
            "expanded_confidence": expanded_routing.get("confidence"),
            "agreement": (raw_mode == expanded_mode and raw_bypass == expanded_bypass),
            # Audit flag: Phase A would have introduced an analytical
            # dispatch the raw prompt didn't trigger. The operational path
            # ignores this (uses raw); the flag is observability only.
            "phase_a_introduced_dispatch":
                bool(expanded_mode and not raw_mode and not raw_bypass),
            # Audit flag: Phase A would have suppressed a dispatch the raw
            # prompt did trigger. The operational path correctly keeps the
            # raw dispatch; the flag tracks how often Phase A would have
            # destroyed signal-matchable vocabulary.
            "phase_a_suppressed_dispatch":
                bool(raw_mode and not expanded_mode and not expanded_bypass),
        }
    except Exception as _audit_exc:
        dispatch_audit = {"audit_failed": True, "error": str(_audit_exc)[:300]}

    # Map the routing decision into the legacy step1_result schema so
    # server.py and run_pipeline keep working without invasive changes.
    if routing["bypass_to_direct_response"]:
        step1_result["mode"] = "simple"
        step1_result["triage_tier"] = 1
        step1_result["classification_confidence"] = "high"
        step1_result["classification_runner_up"] = ""
        step1_result["classification_reasoning"] = routing["stage1_output"]["rationale"]
        step1_result["classification_intent"] = "SIMPLE"
        step1_result["detected_invocation"] = ""
    elif routing["dispatched_mode_id"]:
        step1_result["mode"] = routing["dispatched_mode_id"]
        # Use the mode's default tier per Decision C (Gear 4 universal default;
        # tier comes from the mode file). Tier-2 is the default-on-ambiguity.
        step1_result["triage_tier"] = _depth_tier_from_routing(routing)
        step1_result["classification_confidence"] = routing["confidence"]
        step1_result["classification_runner_up"] = ""
        step1_result["classification_reasoning"] = routing["stage2_output"]["rationale"]
        step1_result["classification_intent"] = "ANALYZING"
        step1_result["detected_invocation"] = routing["dispatched_mode_id"]
    else:
        # Pending clarification — Stage 2 couldn't dispatch.
        #
        # Old behaviour (pre-2026-05-15): silently dispatched to the
        # ``standard`` catch-all mode, whose mode file does not exist; the
        # downstream pipeline ran with empty per-step instructions and
        # produced confidently-shaped but contractually-empty output.
        # This was failures #2, #3, #8 in the silent-failure catalogue.
        #
        # New behaviour: pick the highest-confidence candidate mode from
        # Stage 1 matches (best-guess dispatch); if no matches exist, fall
        # back to ``deep-clarification`` which is a real analytical mode
        # designed for "user's intent is unclear, let's surface it through
        # conceptual analysis." The pending_clarification text is preserved
        # in classification_reasoning and surfaced via the trace so the user
        # can see what Stage 2 was unsure about.
        stage1_matches = routing.get("stage1_output", {}).get("matches", []) or []
        best_guess, best_reasoning = _best_guess_mode_from_matches(stage1_matches)
        if best_guess and load_mode(best_guess):
            step1_result["mode"] = best_guess
            step1_result["classification_confidence"] = "best-guess"
            step1_result["classification_intent"] = "ANALYZING_BEST_GUESS"
            step1_result["detected_invocation"] = best_guess
            step1_result["classification_reasoning"] = (
                f"Stage 2 pending clarification ({routing['pending_clarification']!r}); "
                f"dispatched to {best_guess} as best guess — {best_reasoning}."
            )
        else:
            # No usable matches — fall back to deep-clarification.
            fallback = _PENDING_CLARIFICATION_FALLBACK_MODE
            step1_result["mode"] = fallback
            step1_result["classification_confidence"] = "fallback"
            step1_result["classification_intent"] = "ANALYZING_FALLBACK"
            step1_result["detected_invocation"] = fallback
            step1_result["classification_reasoning"] = (
                f"Stage 2 pending clarification ({routing['pending_clarification']!r}); "
                f"no Stage 1 signal matches available for best-guess dispatch; "
                f"falling back to {fallback} (designed for unclear-intent prompts)."
            )
        step1_result["triage_tier"] = 2
        step1_result["classification_runner_up"] = ""
        # Record the pending clarification separately so the trace + server can
        # surface it without losing it in classification_reasoning.
        step1_result["pending_clarification_swallowed"] = routing["pending_clarification"]

    # Carry the full routing decision so the server can surface it via SSE
    # (dispatch_announcement, completeness_gaps, residual disambiguation).
    step1_result["pre_routing"] = {
        "dispatched_mode_id": routing.get("dispatched_mode_id"),
        "territory": routing.get("territory"),
        "bypass_to_direct_response": routing.get("bypass_to_direct_response", False),
        "pending_clarification": routing.get("pending_clarification"),
        "pending_clarification_stage": routing.get("pending_clarification_stage"),
        "completeness_gaps": routing.get("completeness_gaps", []),
        "dispatch_announcement": routing.get("dispatch_announcement"),
        "lighter_sibling_mode_id": routing.get("lighter_sibling_mode_id"),
        "confidence": routing.get("confidence", "low"),
        "stage1_match_count": len(routing.get("stage1_output", {}).get("matches", [])),
    }

    # --- Trace: pre-routing pipeline decisions ---
    if PIPELINE_TRACE_AVAILABLE:
        stage1_out = routing.get("stage1_output", {}) or {}
        stage2_out = routing.get("stage2_output", {}) or {}

        # Signal-strength summary — fix for failure #13. Stage 2 emits
        # high-confidence dispatch from `_select_dispatch_mode` whenever
        # strong analytical signals are present, then short-circuits via
        # the "friction reducer" (no disambiguation questions asked).
        # If the signal evidence is thin, a high-confidence dispatch is
        # still issued. This summary surfaces the actual evidence so a
        # reviewer can spot over-confident dispatch driven by a single
        # strong signal, or under-counted weak signals that should have
        # provoked disambiguation.
        s1_matches = stage1_out.get("matches", []) or []
        strong_matches = [m for m in s1_matches
                          if m.get("confidence_weight") == "strong"]
        weak_matches = [m for m in s1_matches
                        if m.get("confidence_weight") == "weak"]
        dispatched = routing.get("dispatched_mode_id")
        # Count signals that directly support the dispatched mode
        strong_for_dispatched = [m for m in strong_matches
                                  if m.get("mode") == dispatched]
        weak_for_dispatched = [m for m in weak_matches
                                if m.get("mode") == dispatched]
        signal_strength_summary = {
            "total_matches": len(s1_matches),
            "strong_matches": len(strong_matches),
            "weak_matches": len(weak_matches),
            "strong_signals_supporting_dispatched_mode": len(strong_for_dispatched),
            "weak_signals_supporting_dispatched_mode": len(weak_for_dispatched),
            "dispatched_mode_id": dispatched,
            "dispatch_confidence": routing.get("confidence"),
            # Audit flag: high-confidence dispatch supported by a single
            # strong signal is the failure mode for #13. The signal MAY be
            # sufficient (a clean "cui bono" match is enough); the flag
            # exposes the condition so an auditor can decide case-by-case.
            "single_signal_high_confidence":
                routing.get("confidence") == "high"
                and len(strong_for_dispatched) == 1,
            # Sibling flag: high-confidence dispatch with ZERO strong signals
            # — the dispatch came from weak signals alone (or from a path
            # that didn't surface strong supporters). More concerning than
            # the single-signal case and previously unflagged.
            "zero_strong_signal_high_confidence":
                routing.get("confidence") == "high"
                and len(strong_for_dispatched) == 0
                and dispatched is not None,
            "strong_signals_detail": [
                {"signal": m.get("signal"), "mode": m.get("mode"),
                 "territory": m.get("territory"),
                 "kind": _signal_kind(m) if dispatched else None}
                for m in strong_matches
            ][:10],  # cap detail at 10 for trace-file size
        }
        pipeline_trace.write_step(trace_dir, "step1-pre-routing", {
            "input_to_routing": step1_result.get("operational_notation", ""),
            "bypass_to_direct_response": routing.get("bypass_to_direct_response", False),
            "dispatched_mode_id": routing.get("dispatched_mode_id"),
            "territory": routing.get("territory"),
            "confidence": routing.get("confidence"),
            "pending_clarification": routing.get("pending_clarification"),
            "pending_clarification_stage": routing.get("pending_clarification_stage"),
            # New fields capture the fix for #2+#3+#8: when Stage 2 produced
            # a pending clarification, what mode did we best-guess-dispatch
            # to (or fall back to), and what was the original clarification
            # we are running past?
            "pending_clarification_swallowed": step1_result.get(
                "pending_clarification_swallowed"
            ),
            "classification_confidence": step1_result.get(
                "classification_confidence"
            ),
            "classification_intent": step1_result.get("classification_intent"),
            "classification_reasoning": step1_result.get(
                "classification_reasoning"
            ),
            "completeness_gaps": routing.get("completeness_gaps", []),
            "dispatch_announcement": routing.get("dispatch_announcement"),
            "lighter_sibling_mode_id": routing.get("lighter_sibling_mode_id"),
            "stage1_output": stage1_out,
            "stage2_output": stage2_out,
            "stage3_output": routing.get("stage3_output"),
            "stage1_match_count": len(stage1_out.get("matches", [])),
            "signal_strength_summary": signal_strength_summary,
            "dispatch_audit_raw_vs_expanded": dispatch_audit,
            "triage_tier_chosen": step1_result.get("triage_tier"),
            "final_mode_chosen": step1_result.get("mode"),
        }, markdown=(
            "# Step 1 — Pre-Routing Pipeline\n\n"
            f"**Input (operational notation):** "
            f"{step1_result.get('operational_notation', '_(empty)_')}\n\n"
            f"**Stage 1 — Pre-Analysis Filter:** "
            f"bypass={routing.get('bypass_to_direct_response', False)}, "
            f"matches={len(stage1_out.get('matches', []))}\n\n"
            f"**Stage 1 rationale:** "
            f"{stage1_out.get('rationale', '_(none)_')}\n\n"
            f"**Stage 2 — Sufficiency Analyzer:** "
            f"dispatched={routing.get('dispatched_mode_id', '_(none)_')}, "
            f"confidence={routing.get('confidence', '_(none)_')}\n\n"
            f"**Stage 2 rationale:** "
            f"{stage2_out.get('rationale', '_(none)_')}\n\n"
            f"**Stage 3 — Completeness Check:** "
            f"gaps={routing.get('completeness_gaps', [])}\n\n"
            f"**Pending clarification:** "
            f"{routing.get('pending_clarification', '_(none)_')}\n\n"
            + (
                f"**Pending-clarification handling:** swallowed; "
                f"best-guess / fallback dispatch via "
                f"`{step1_result.get('classification_intent')}` → "
                f"`{step1_result.get('mode')}` "
                f"(confidence: `{step1_result.get('classification_confidence')}`). "
                f"Reasoning: {step1_result.get('classification_reasoning')}\n\n"
                if step1_result.get("pending_clarification_swallowed")
                else ""
            )
            + f"**Final mode:** {step1_result.get('mode')}\n"
            f"**Triage tier:** {step1_result.get('triage_tier')}\n"
            f"**Classification confidence:** "
            f"{step1_result.get('classification_confidence', '_(none)_')}\n"
            f"**Classification intent:** "
            f"{step1_result.get('classification_intent', '_(none)_')}\n\n"
            f"## Signal strength summary (friction-reducer audit)\n\n"
            f"- Total Stage 1 matches: "
            f"{signal_strength_summary['total_matches']}\n"
            f"- Strong matches: {signal_strength_summary['strong_matches']}\n"
            f"- Weak matches: {signal_strength_summary['weak_matches']}\n"
            f"- Strong signals supporting dispatched mode "
            f"(`{signal_strength_summary['dispatched_mode_id'] or '_(none)_'}`): "
            f"{signal_strength_summary['strong_signals_supporting_dispatched_mode']}\n"
            f"- Weak signals supporting dispatched mode: "
            f"{signal_strength_summary['weak_signals_supporting_dispatched_mode']}\n"
            + (
                f"- ⚠️  **Single-signal high-confidence dispatch** — only one "
                f"strong signal supports the high-confidence dispatch. "
                f"Spot-check whether the signal is genuinely sufficient.\n"
                if signal_strength_summary['single_signal_high_confidence']
                else ""
            )
            + (
                f"- ⚠️  **Zero-strong-signal high-confidence dispatch** — "
                f"the high-confidence dispatch is supported by no strong "
                f"signals (weak-only or empty supporters). Higher review "
                f"priority than the single-signal case.\n"
                if signal_strength_summary['zero_strong_signal_high_confidence']
                else ""
            )
        ))

    return step1_result


def _best_guess_mode_from_matches(matches: list[dict]) -> tuple[str | None, str]:
    """When Stage 2 produces pending_clarification but Stage 1 found signal
    matches, pick the highest-confidence candidate mode rather than punting
    to the missing ``standard`` catch-all.

    Returns ``(mode_id, reasoning)``. When no matches qualify, returns
    ``(None, "no matches available")`` and the caller falls back to the
    default analytical mode (``deep-clarification``).

    Scoring: each match contributes 2 points for ``confidence_weight ==
    "strong"`` and 1 point for ``weak``. Modes with a registered
    ``mode`` field score; matches without a mode (territory-only signals)
    are skipped. Highest total wins; ties break on the first-seen mode.
    """
    if not matches:
        return None, "no matches available"
    score: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for idx, m in enumerate(matches):
        mode_id = m.get("mode")
        if not mode_id:
            continue
        weight = m.get("confidence_weight", "weak")
        pts = 2 if weight == "strong" else 1
        score[mode_id] = score.get(mode_id, 0) + pts
        if mode_id not in first_seen:
            first_seen[mode_id] = idx
    if not score:
        return None, "no matches carry a mode_id"
    best = max(score.items(), key=lambda kv: (kv[1], -first_seen[kv[0]]))
    return best[0], (
        f"best-guess from Stage 1 signal matches "
        f"(score={best[1]}, first-seen-idx={first_seen[best[0]]})"
    )


# Fallback analytical mode when pre-routing produces a pending clarification
# AND no Stage 1 signal matches exist to best-guess from. ``deep-clarification``
# is the right default because it is designed to clarify what the user actually
# needs through ordinary-language conceptual analysis — exactly the operation
# the user implicitly requested when their prompt didn't trigger any
# specific-mode signal vocabulary.
_PENDING_CLARIFICATION_FALLBACK_MODE = "deep-clarification"


def _depth_tier_from_routing(routing: dict) -> int:
    """Pick a triage tier for the dispatched mode.

    Strong direct dispatch with a depth signal in the prompt → that tier.
    Otherwise default to Tier-2 per Style Guide §5.6.
    """
    rationale = routing.get("stage2_output", {}).get("rationale", "") or ""
    if "tier-1" in rationale:
        return 1
    if "tier-3" in rationale:
        return 3
    return 2


# Phase 9 — `run_mode_classification` removed. The Phase A.5 dedicated mode
# classifier loaded `frameworks/mode-classification-directory.md` and called a
# model to pick a mode. The four-stage pre-routing pipeline (Stages 1-3 above)
# replaces it: signal-vocabulary substring matching + within-territory and
# cross-territory disambiguation + input completeness check. The retired
# function had no remaining callers.


def compare_intent_with_mode(
    picked_mode: str,
    manual_mode_selection: str | None = None,
    detected_invocation: str | None = None,
    framework_selected: str | None = None,
) -> dict:
    """V3 Phase 1 — alignment-prefilter comparison step.

    Compares the user's expressed intent (manual selection OR detected
    prose-level invocation) against the mode the classifier picked.

    Resolution rules per Working — Framework — Ora v3 Input Handling Q4:
    - When a framework is selected, the prefilter is suppressed entirely
      (framework owns routing). Returns ``matches=True`` with
      ``expressed_source="framework"`` so callers can short-circuit.
    - When ``manual_mode_selection`` is set, it wins as expressed intent.
      ``detected_invocation`` is recorded but not used for the match check.
    - Otherwise ``detected_invocation`` (if non-empty / non-NONE) is the
      expressed intent.
    - When neither is set, expressed intent is None and ``matches`` is True
      (no mismatch possible without an expression of intent).

    Returns::

        {
            "expressed_intent": str | None,   # the mode the user expressed
            "expressed_source": str | None,   # "manual" / "detected" /
                                              # "framework" / None
            "picked_mode": str,
            "matches": bool,                  # False → prefilter triggers
            "detected_invocation": str,       # always echoed for telemetry
        }
    """
    detected = (detected_invocation or "").strip()
    if detected.upper() == "NONE":
        detected = ""

    manual = (manual_mode_selection or "").strip()
    framework = (framework_selected or "").strip()

    if framework:
        return {
            "expressed_intent": None,
            "expressed_source": "framework",
            "picked_mode": picked_mode,
            "matches": True,
            "detected_invocation": detected,
        }

    if manual:
        return {
            "expressed_intent": manual,
            "expressed_source": "manual",
            "picked_mode": picked_mode,
            "matches": manual == picked_mode,
            "detected_invocation": detected,
        }

    if detected:
        return {
            "expressed_intent": detected,
            "expressed_source": "detected",
            "picked_mode": picked_mode,
            "matches": detected == picked_mode,
            "detected_invocation": detected,
        }

    return {
        "expressed_intent": None,
        "expressed_source": None,
        "picked_mode": picked_mode,
        "matches": True,
        "detected_invocation": detected,
    }


def _diagnose_rag_emptiness(collection: str, query: str,
                            mode_text: str | None = None) -> dict:
    """When a RAG call returns 0 chars without raising, distinguish between
    the three possible causes:

    - ``index_empty`` — the collection contains zero chunks
    - ``filtered_out`` — chunks exist but all were filtered by type_filter
      / archived / private rules
    - ``no_match`` — chunks exist and pass filters but none ranked above
      the formatting threshold

    Fixes silent failure #4: previously the trace recorded ``chars: 0``
    with no further diagnostic, so an empty-vault deployment was
    indistinguishable from a healthy vault with no relevant content for
    the query. Each cause has a different remediation, and the
    diagnostic is cheap (one collection.count() and one raw query).
    """
    diagnosis: dict[str, Any] = {
        "collection": collection,
        "query": query[:200],
        "collection_total_count": None,
        "raw_chunks_returned": None,
        "filtered_chunks_returned": None,
        "empty_reason": "unknown",
    }
    try:
        from tools import knowledge_search as ks
    except Exception as e:
        diagnosis["empty_reason"] = f"diagnostic_unavailable: {e}"
        return diagnosis

    # Step 1 — total count
    try:
        import chromadb
        from embedding import get_or_create_collection
        client = chromadb.PersistentClient(path=os.path.join(WORKSPACE, "chromadb"))
        col = get_or_create_collection(client, collection)
        total = col.count()
        diagnosis["collection_total_count"] = total
        if total == 0:
            diagnosis["empty_reason"] = "index_empty"
            return diagnosis
    except Exception as e:
        diagnosis["empty_reason"] = f"count_failed: {e}"
        return diagnosis

    # Step 2 — raw chunk count without filters
    try:
        raw = ks.knowledge_search_raw(
            query=query, collection=collection, n_results=10,
            include_private=False, include_archived=False,
        )
        diagnosis["raw_chunks_returned"] = len(raw)

        # Step 3 — chunk count with mode's type_filter applied
        type_filter = None
        if mode_text:
            try:
                type_filter = ks._extract_mode_type_filter(mode_text)
            except Exception:
                type_filter = None
        if type_filter:
            filtered = ks.knowledge_search_raw(
                query=query, collection=collection, n_results=10,
                type_filter=type_filter,
                include_private=False, include_archived=False,
            )
            diagnosis["filtered_chunks_returned"] = len(filtered)
            diagnosis["type_filter_applied"] = type_filter
        else:
            diagnosis["filtered_chunks_returned"] = diagnosis["raw_chunks_returned"]
            diagnosis["type_filter_applied"] = None

        # Determine the empty_reason
        if diagnosis["raw_chunks_returned"] == 0:
            diagnosis["empty_reason"] = "no_match"
        elif diagnosis["filtered_chunks_returned"] == 0:
            diagnosis["empty_reason"] = "filtered_out"
        else:
            # Chunks survived filtering but the ranker produced 0-char
            # output. That can happen when max_chars truncates everything
            # or when the rank order pushed all relevant content past
            # the budget — flag as ranker_truncation for caller review.
            diagnosis["empty_reason"] = "ranker_truncation_or_filter_threshold"
    except Exception as e:
        diagnosis["empty_reason"] = f"diagnostic_query_failed: {e}"

    return diagnosis


# Slots a gear might use, ordered by typical context-window size (largest
# first). We pick the smallest declared context_window across the slots
# the current gear will exercise so the RAG cap never exceeds any
# downstream model's window.
_GEAR_SLOTS_USED = {
    1: ("classification", "sidebar", "step1_cleanup"),
    2: ("breadth", "step1_cleanup", "sidebar"),
    3: ("depth", "breadth", "evaluator", "sidebar", "step1_cleanup"),
    4: ("depth", "breadth", "evaluator", "consolidator", "sidebar", "step1_cleanup"),
}


def _load_web_supplement_config() -> dict:
    """Read the ``web_supplement`` section from routing-config.json.

    Defaults: ``enabled=True``, ``max_gaps=3``, ``max_attempts_per_gap=2``.
    Missing file or missing section → defaults (treat as enabled). The
    caller is responsible for layering its own ``enabled=False`` short-
    circuit before doing anything expensive.
    """
    defaults = {
        "enabled": True,
        "max_gaps": _WEB_SUPP_DEFAULT_MAX_GAPS if WEB_SUPPLEMENT_AVAILABLE else 3,
        "max_attempts_per_gap": _WEB_SUPP_DEFAULT_MAX_ATTEMPTS if WEB_SUPPLEMENT_AVAILABLE else 2,
    }
    try:
        with open(ROUTING_CONFIG_JSON, "r") as f:
            rc = json.load(f)
        section = rc.get("web_supplement") or {}
        return {**defaults, **section}
    except Exception:
        return defaults


def run_step2_context_assembly(step1_result: dict, config: dict,
                               trace_dir: str | None = None) -> dict:
    """Step 2: Assemble context package for pipeline stages.

    Python loads the mode file, performs RAG queries, and builds the complete
    context package. This is pre-assembly — no model call needed.

    If the RAG engine (Phase 8) is available, uses priority stack assembly with
    relationship graph traversal. Otherwise falls back to basic ChromaDB queries.

    ``trace_dir`` is the per-turn forensic-trace directory created by
    ``pipeline_trace.start_trace``. RAG retrieval failures that previously
    fell silently to empty strings now write structured failure entries
    to ``rag-failures.jsonl`` in this directory.
    """
    mode_name = step1_result["mode"]
    mode_text = load_mode(mode_name)
    gear = extract_default_gear(mode_text)

    # Phase A produces three forms of the prompt:
    #   - raw_prompt: what the user actually typed (source of truth)
    #   - cleaned_prompt: natural-language version with Phase A's
    #     disambiguations and inferred items
    #   - operational_notation: compact function-call form
    #
    # Pre-2026-05-16 design used operational_notation as the cleaned_prompt
    # passed downstream. That had two failure modes: (a) underscore-tokenized
    # function-call syntax doesn't substring-match the natural-language
    # signal-vocabulary registry (fixed in commit d6b7df7 by routing
    # pre-routing through raw_prompt), and (b) downstream analyst /
    # evaluator / verifier user messages got the operational form labelled
    # as "ORIGINAL QUERY", which is misleading (the operational form is
    # Phase A's interpretation, not the user's actual words) and stripped
    # of nuance ("become as capable", "Short list, no preamble").
    #
    # Fix: the cleaned_prompt that flows downstream now combines the raw
    # prompt (so evaluators see what the user actually asked) with Phase A's
    # natural-language clarified interpretation (so they can see what was
    # inferred and check the analyst against those inferences). The
    # operational notation is dropped from user-facing portions of analyst
    # prompts entirely — it was a model-readable optimisation that became a
    # clarity tax. RAG queries use raw_prompt for embedding similarity
    # (most faithful to user intent).
    raw_prompt = step1_result.get("raw_prompt", "") or ""
    cleaned_nl = step1_result.get("cleaned_prompt", "") or ""
    if raw_prompt and cleaned_nl and raw_prompt.strip() != cleaned_nl.strip():
        cleaned_prompt = (
            f"{raw_prompt}\n\n"
            f"_Phase A clarified interpretation (includes inferred items "
            f"not explicit in original):_\n\n"
            f"{cleaned_nl}"
        )
    else:
        cleaned_prompt = raw_prompt or cleaned_nl
    rag_query = raw_prompt or cleaned_nl

    # Phase 5.6 ranker: type-weighted ranking with provenance markers,
    # type_filter from active mode's RAG PROFILE, archived/private filters.
    # Falls back to the legacy formatted-string knowledge_search when the
    # ranker module isn't loadable (graceful degradation).
    #
    # IMPORTANT: previously every RAG call here was wrapped in a bare
    # ``try/except: result = ""`` block that silently lost the exception.
    # The wrappers below preserve the same graceful-degradation behaviour
    # but write each failure to ``rag-failures.jsonl`` in the trace
    # directory, so silent fallbacks become inspectable.
    conv_rag = ""
    conv_rag_path = "unknown"
    if RAG_ENGINE_AVAILABLE:
        try:
            conv_rag = assemble_ranked_context(
                query=rag_query,
                collection="conversations",
                mode_text=mode_text,
                n_results=3,
            )
            conv_rag_path = "rag_engine.assemble_ranked_context"
        except Exception as e:
            conv_rag = ""
            conv_rag_path = "rag_engine_failed_fallback_to_empty"
            if PIPELINE_TRACE_AVAILABLE:
                pipeline_trace.record_rag_failure(
                    trace_dir, "conversation-rag", rag_query, e
                )
    elif TOOLS_AVAILABLE:
        try:
            conv_rag = knowledge_search(rag_query, "conversations", 3)
            conv_rag_path = "legacy_knowledge_search"
        except Exception as e:
            conv_rag = ""
            conv_rag_path = "legacy_knowledge_search_failed"
            if PIPELINE_TRACE_AVAILABLE:
                pipeline_trace.record_rag_failure(
                    trace_dir, "conversation-rag-legacy", rag_query, e
                )

    # Concept RAG (vault knowledge) — only for Gear 2+
    concept_rag = ""
    concept_rag_path = "skipped_gear_below_2"
    if gear >= 2:
        if RAG_ENGINE_AVAILABLE:
            try:
                concept_rag = assemble_ranked_context(
                    query=rag_query,
                    collection="knowledge",
                    mode_text=mode_text,
                    n_results=5,
                )
                concept_rag_path = "rag_engine.assemble_ranked_context"
            except Exception as e:
                concept_rag = ""
                concept_rag_path = "rag_engine_failed_fallback_to_empty"
                if PIPELINE_TRACE_AVAILABLE:
                    pipeline_trace.record_rag_failure(
                        trace_dir, "concept-rag", rag_query, e
                    )
        elif TOOLS_AVAILABLE:
            try:
                concept_rag = knowledge_search(rag_query, "knowledge", 5)
                concept_rag_path = "legacy_knowledge_search"
            except Exception as e:
                concept_rag = ""
                concept_rag_path = "legacy_knowledge_search_failed"
                if PIPELINE_TRACE_AVAILABLE:
                    pipeline_trace.record_rag_failure(
                        trace_dir, "concept-rag-legacy", rag_query, e
                    )

    # Relationship RAG (Phase 7/8) — enrichment via graph traversal
    relationship_rag = ""
    rag_signals = []
    rag_utilization = ""
    hardware_tier = 0

    if RAG_ENGINE_AVAILABLE and gear >= 2:
        try:
            engine = RAGEngine(config)
            hardware_tier = engine.hardware["tier"]

            # Parse concept_rag results for relationship traversal.
            # Phase 5.6 marker shape: `[type: ... | weight: ... | source: name.md]`.
            # Legacy fallback shape: `1. [name.md]`.
            initial_results = []
            if concept_rag:
                _src_re = re.compile(r"\bsource:\s*([^|\]]+?)(?:\s*\]|\s*\|)", re.IGNORECASE)
                _legacy_re = re.compile(r"\d+\.\s*\[([^\]]+)\]")
                for line in concept_rag.split("\n"):
                    m = _src_re.search(line) or _legacy_re.search(line)
                    if m:
                        title = m.group(1).strip().replace(".md", "")
                        if title:
                            initial_results.append({"source": title})

            relationship_rag = engine.get_relationship_context(initial_results, mode_text)

            # Run priority stack assembly for utilization tracking
            context_result = engine.assemble_context(
                cleaned_prompt=cleaned_prompt,
                mode_text=mode_text,
                gear=gear,
                conversation_rag=conv_rag,
                concept_rag=concept_rag,
                relationship_rag=relationship_rag,
            )
            rag_signals = context_result.get("signals", [])
            rag_utilization = context_result.get("utilization", "")
        except Exception as e:
            # Fall back gracefully — RAG engine failure should not block the pipeline
            print(f"[WARNING] RAG engine error: {e}")
            if PIPELINE_TRACE_AVAILABLE:
                pipeline_trace.record_rag_failure(
                    trace_dir, "rag-engine-init-or-relationship", cleaned_prompt, e
                )

    # --- Step 2.5 — Web Supplement Loop (anticipatory) ---
    # Runs ONLY when:
    #   - the web_supplement module imported cleanly,
    #   - routing-config.json has `web_supplement.enabled: true` (the
    #     default — section absent is treated as enabled),
    #   - the dispatched gear is >= 2 (Gear 1 / bypass paths skip).
    # The fast model (step1_cleanup slot) decides whether web is needed
    # and, if so, iterates decide→search→evaluate per gap. Output is a
    # pre-formatted "## WEB CONTEXT" body retrieved BEFORE the analyst
    # runs — the existing mid-analysis Supplemental RAG Protocol stays as
    # the rare-case fallback for gaps this pass didn't anticipate.
    web_rag = ""
    web_supplement_trace: dict = {"status": "skipped", "reason": "not_attempted"}
    if WEB_SUPPLEMENT_AVAILABLE and gear >= 2:
        ws_cfg = _load_web_supplement_config()
        if not ws_cfg.get("enabled", True):
            web_supplement_trace = {"status": "skipped",
                                     "reason": "disabled_in_routing_config"}
        else:
            fast_ep = get_slot_endpoint(config, _WEB_SUPP_DEFAULT_SLOT)
            if fast_ep is None:
                web_supplement_trace = {"status": "skipped",
                                         "reason": "no_fast_endpoint"}
            else:
                try:
                    ws_result = assemble_web_supplemental_context(
                        user_prompt=raw_prompt or cleaned_nl or cleaned_prompt,
                        call_model=call_model,
                        fast_endpoint=fast_ep,
                        conversation_context=(
                            conv_rag[:2000] if conv_rag else ""
                        ),
                        max_gaps=ws_cfg.get(
                            "max_gaps", _WEB_SUPP_DEFAULT_MAX_GAPS,
                        ),
                        max_attempts_per_gap=ws_cfg.get(
                            "max_attempts_per_gap",
                            _WEB_SUPP_DEFAULT_MAX_ATTEMPTS,
                        ),
                    )
                    web_rag = ws_result.get("text") or ""
                    web_supplement_trace = {
                        "status": "ran",
                        "text_chars": len(web_rag),
                        "decision": ws_result.get("decision"),
                        "gaps_processed": ws_result.get("gaps_processed", []),
                        "signals": ws_result.get("signals", []),
                        "elapsed_seconds": ws_result.get("elapsed_seconds"),
                        "endpoint_used": ws_result.get("endpoint_used"),
                    }
                except Exception as exc:
                    # Fail-soft: any unexpected error in the supplement
                    # loop must not block the pipeline.
                    print(
                        f"[web-supplement] unexpected error: {exc}. "
                        f"Continuing with vault-only RAG.",
                        file=sys.stderr, flush=True,
                    )
                    web_supplement_trace = {"status": "errored",
                                             "reason": str(exc)[:300]}

    # Phase 9 — Decision I/J output format expansion. New fields surface
    # pre-routing-pipeline state populated by run_step1_cleanup → routing.
    pre_routing = step1_result.get("pre_routing", {}) or {}
    territory = pre_routing.get("territory")
    completeness_gaps = pre_routing.get("completeness_gaps", []) or []
    pending = pre_routing.get("pending_clarification")
    residual_questions = [pending] if pending else []
    dispatch_announcement = pre_routing.get("dispatch_announcement")
    if not dispatch_announcement and pre_routing.get("dispatched_mode_id"):
        # Backstop: compose announcement here if Stage 3 still ran but
        # the dispatched mode was set late.
        try:
            dispatch_announcement = compose_dispatch_announcement(
                pre_routing["dispatched_mode_id"], cleaned_prompt
            )
        except Exception:
            dispatch_announcement = None

    # --- Empty-result diagnostics (fix for failure #4) ---
    # When a RAG call returned 0 chars without raising an exception,
    # distinguish index_empty / no_match / filtered_out / ranker_truncation
    # so the trace tells us which remediation applies. Only runs when
    # tracing is on, the retrieval path completed without exception, and
    # the result is genuinely 0 chars.
    conv_rag_diagnosis = None
    concept_rag_diagnosis = None
    if PIPELINE_TRACE_AVAILABLE and trace_dir:
        if not conv_rag and conv_rag_path in (
            "rag_engine.assemble_ranked_context", "legacy_knowledge_search",
        ):
            conv_rag_diagnosis = _diagnose_rag_emptiness(
                "conversations", cleaned_prompt, mode_text=mode_text,
            )
        if not concept_rag and gear >= 2 and concept_rag_path in (
            "rag_engine.assemble_ranked_context", "legacy_knowledge_search",
        ):
            concept_rag_diagnosis = _diagnose_rag_emptiness(
                "knowledge", cleaned_prompt, mode_text=mode_text,
            )

    # --- Trace: complete context package (the highest-value trace, since
    # this is where vault content is supposed to enter the pipeline) ---
    if PIPELINE_TRACE_AVAILABLE:
        # Render BudgetSignal codes to human-readable strings when we can.
        signal_descriptions = []
        try:
            for s in (rag_signals or []):
                if isinstance(s, int):
                    signal_descriptions.append({
                        "code": s,
                        "description": BudgetSignal.describe(s) if RAG_ENGINE_AVAILABLE else str(s),
                    })
                else:
                    signal_descriptions.append({"code": None, "description": str(s)})
        except Exception:
            signal_descriptions = [{"code": None, "description": str(rag_signals)}]

        # RAG cap — constant for all modern endpoints. See
        # rag_engine.RAG_MAX_CHARS.
        try:
            from rag_engine import RAG_MAX_CHARS as _rag_cap
        except Exception:
            _rag_cap = None
        pipeline_trace.write_step(trace_dir, "step2-context", {
            "mode_name": mode_name,
            "mode_text_chars": len(mode_text),
            "gear": gear,
            "cleaned_prompt": cleaned_prompt,
            # The three prompt forms broken out for trace-side audit.
            # cleaned_prompt above is the composite that downstream user
            # messages use; raw and natural-language are kept separate so
            # any future regression in the composite assembly is visible.
            "raw_prompt": raw_prompt,
            "natural_language_prompt": cleaned_nl,
            "rag_query": rag_query,
            "rag_max_chars": _rag_cap,
            "conversation_rag": {
                "retrieval_path": conv_rag_path,
                "chars": len(conv_rag),
                "content": conv_rag,
                "empty_diagnosis": conv_rag_diagnosis,
            },
            "concept_rag": {
                "retrieval_path": concept_rag_path,
                "chars": len(concept_rag),
                "content": concept_rag,
                "empty_diagnosis": concept_rag_diagnosis,
            },
            "relationship_rag": {
                "chars": len(relationship_rag),
                "content": relationship_rag,
            },
            "rag_signals": signal_descriptions,
            "rag_utilization_header": rag_utilization,
            "hardware_tier": hardware_tier,
            "rag_engine_available": RAG_ENGINE_AVAILABLE,
            "tools_available": TOOLS_AVAILABLE,
            "pre_routing_summary": {
                "territory": territory,
                "dispatched_mode_id": pre_routing.get("dispatched_mode_id"),
                "confidence": pre_routing.get("confidence"),
                "completeness_gaps": completeness_gaps,
            },
        }, markdown=(
            "# Step 2 — Context Assembly\n\n"
            f"**Mode:** `{mode_name}`  \n"
            f"**Gear:** {gear}  \n"
            f"**Hardware tier:** {hardware_tier}  \n"
            f"**Territory:** {territory or '_(none)_'}\n\n"
            f"## Conversation RAG ({len(conv_rag)} chars, "
            f"path: `{conv_rag_path}`)\n\n"
            + (
                f"**Empty-result diagnosis:** `{conv_rag_diagnosis['empty_reason']}` "
                f"(collection total: {conv_rag_diagnosis['collection_total_count']}, "
                f"raw chunks: {conv_rag_diagnosis['raw_chunks_returned']}, "
                f"filtered: {conv_rag_diagnosis['filtered_chunks_returned']})\n\n"
                if conv_rag_diagnosis else ""
            )
            + f"```\n{conv_rag or '_(empty)_'}\n```\n\n"
            f"## Concept RAG ({len(concept_rag)} chars, "
            f"path: `{concept_rag_path}`)\n\n"
            + (
                f"**Empty-result diagnosis:** `{concept_rag_diagnosis['empty_reason']}` "
                f"(collection total: {concept_rag_diagnosis['collection_total_count']}, "
                f"raw chunks: {concept_rag_diagnosis['raw_chunks_returned']}, "
                f"filtered: {concept_rag_diagnosis['filtered_chunks_returned']})\n\n"
                if concept_rag_diagnosis else ""
            )
            + f"```\n{concept_rag or '_(empty)_'}\n```\n\n"
            f"## Relationship RAG ({len(relationship_rag)} chars)\n\n"
            f"```\n{relationship_rag or '_(empty)_'}\n```\n\n"
            f"## Web supplement (Step 2.5)\n\n"
            f"**Status:** `{web_supplement_trace.get('status')}` "
            f"({web_supplement_trace.get('reason') or web_supplement_trace.get('text_chars', 0)} "
            f"{'chars' if web_supplement_trace.get('status') == 'ran' else ''})\n\n"
            + (
                f"```\n{web_rag}\n```\n\n"
                if web_rag else ""
            )
            + f"## Budget signals\n\n"
            + (
                "\n".join(f"- {s['code']}: {s['description']}" for s in signal_descriptions)
                if signal_descriptions else "_(none)_"
            )
            + "\n\n"
            f"## Utilization header\n\n"
            f"```\n{rag_utilization or '_(none)_'}\n```\n"
        ))

        # Full per-gap web-supplement detail as its own trace file so
        # step2-context stays readable (the per-gap attempts list can grow).
        if web_supplement_trace.get("status") in ("ran", "errored"):
            pipeline_trace.write_step(trace_dir, "step2-web-supplement",
                                       web_supplement_trace, markdown=(
                "# Step 2.5 — Web Supplement\n\n"
                f"**Status:** `{web_supplement_trace.get('status')}`\n"
                f"**Elapsed:** {web_supplement_trace.get('elapsed_seconds', 0):.2f}s\n"
                f"**Endpoint:** {web_supplement_trace.get('endpoint_used') or '_(none)_'}\n\n"
                f"## Decision\n\n```\n"
                f"{json.dumps(web_supplement_trace.get('decision'), indent=2)}\n```\n\n"
                f"## Gaps processed\n\n```\n"
                f"{json.dumps(web_supplement_trace.get('gaps_processed', []), indent=2)}\n```\n\n"
                f"## Signals\n\n"
                + "\n".join(
                    f"- {s}" for s in web_supplement_trace.get("signals", [])
                )
                + "\n"
            ))

    return {
        # `cleaned_prompt` is the composite raw + Phase-A-clarified form used
        # as the "ORIGINAL QUERY" body in every downstream user message
        # (analyst, evaluator, reviser, verifier, consolidator, formatter).
        # The operational notation is no longer in the user-facing portion
        # of any analyst prompt; it remains accessible via Phase A's trace
        # for debugging and observability.
        "cleaned_prompt": cleaned_prompt,
        # `raw_prompt` is the user's actual sentence, no Phase A inference.
        # Use this when you need the user's actual words (e.g. signal
        # vocabulary matching, vector-similarity RAG queries).
        "raw_prompt": raw_prompt,
        # `natural_language_prompt` is Phase A's clarified natural-language
        # form (without the raw + composite framing). Kept separate for
        # callers that want Phase A's interpretation only.
        "natural_language_prompt": step1_result["cleaned_prompt"],
        "mode_name": mode_name,
        "mode_text": mode_text,
        "gear": gear,
        "conversation_rag": conv_rag,
        "concept_rag": concept_rag,
        "relationship_rag": relationship_rag,
        # Step 2.5 — anticipatory web-supplement context (empty string when
        # the loop didn't run, didn't decide it was needed, or didn't
        # resolve any gaps). Injected by build_system_prompt_for_gear as
        # the ## WEB CONTEXT block when non-empty.
        "web_rag": web_rag,
        # Per-turn trace of the web-supplement decision + gap loop, kept
        # on the package so server-side observability can surface it.
        "web_supplement_trace": web_supplement_trace,
        "triage_tier": step1_result["triage_tier"],
        "rag_signals": rag_signals,
        "rag_utilization": rag_utilization,
        "hardware_tier": hardware_tier,
        # --- Phase 9 Decision I/J additive fields ---
        "territory": territory,
        "mode": mode_name,  # mirror of mode_name under Decision I/J's preferred field name
        "residual_disambiguation_questions": residual_questions,
        "completeness_gaps": completeness_gaps,
        "dispatch_announcement": dispatch_announcement,
        "pre_routing": pre_routing,
        # Phase A's assume-mode assumptions threaded through so downstream
        # step prompts can surface them as explicit assumptions rather than
        # treating the cleaned prompt as if it were entirely user-stated
        # (fix for failure #10). build_system_prompt_for_gear injects a
        # PHASE A ASSUMPTIONS block when this is non-empty.
        "inferred_items": step1_result.get("inferred_items", ""),
        "corrections_log": step1_result.get("corrections_log", ""),
        # Trace directory threaded through to run_gear3 / run_gear4 so
        # later steps land in the same per-turn directory.
        "trace_dir": trace_dir,
    }


def _extract_section(text: str, heading: str) -> str:
    """Extract the body of a ``## heading`` section up to the next ``## `` or end.

    Returns the inner text stripped of leading/trailing whitespace, or empty
    string if the heading is absent. Used by ``build_system_prompt_for_gear``.
    """
    pattern = rf'## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)'
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_boot_behavioral_preamble(boot_md: str) -> str:
    """Return the behavioral subset of boot.md for pipeline step prompts.

    The full boot.md (~13.6KB) contains both behavioral instruction (§
    CONSTITUTION, § STANDING RULES) and architectural metadata (§ MODE
    REGISTRY, § IDENTITY, § MODELS, § TOOLS catalog, § PIPELINE, § EVALUATION,
    § GUIDELINES, § MEMORY, § AUTONOMOUS, § RECOVERY). Most of that is
    architectural — a pipeline step's job is to act as a specific mode at
    a specific step. It doesn't need the registry to pick a mode (already
    dispatched), doesn't call tools (those run elsewhere), doesn't need
    to know about other models / pipeline architecture / autonomous-run
    semantics.

    Even § STANDING RULES contains subsections that don't apply to a
    pipeline step:
      - ### Anti-Confabulation — duplicated by _UNIVERSAL_ANTI_CONFABULATION
        (the canonical detailed version).
      - ### Mode Awareness — dangling reference to § MODE REGISTRY, which
        is no longer included. The analyst's mode is already loaded.
      - ### Context Management — budgets are orchestrator-managed.
      - ### Knowledge Integration — analyst receives KNOWLEDGE CONTEXT
        pre-fetched; doesn't run vector search itself.
      - ### Adversarial Review — process description (only the
        Hat-assignment line is useful to an analyst — extracted separately).
      - ### Gears — gear architecture description; the analyst is
        already in a specific gear/step.
      - ### Safety — destructive-ops warnings; analyst produces text,
        not file/system ops.
      - ### SAT — Full Type III — closure-time audit; not per-step.

    What remains as behavioral signal for a pipeline step:
      - § CONSTITUTION (4 principles — sovereignty, honesty, minimal
        authority, transparency).
      - ### Anti-Sycophancy (don't validate unsupported conclusions).
      - The Hat-assignments line from ### Adversarial Review (analyst
        needs to know its hat).
      - _UNIVERSAL_ANTI_CONFABULATION (the canonical detailed
        anti-confab discipline, appended by load_boot_md).

    Direct-mode / legacy / Gear-1 callers that need the full boot.md
    (because they're not dispatched to a specific mode) continue to call
    ``load_boot_md()`` directly and get all sections.
    """
    constitution = _extract_section(boot_md, "§ CONSTITUTION")
    standing_rules_full = _extract_section(boot_md, "§ STANDING RULES")

    # Pull just the subsections that apply to a pipeline step.
    def _subsection(text: str, heading: str) -> str:
        m = re.search(
            rf'### {re.escape(heading)}\s*\n(.*?)(?=\n### |\Z)',
            text,
            re.DOTALL,
        )
        return m.group(1).strip() if m else ""

    anti_syc = _subsection(standing_rules_full, "Anti-Sycophancy")

    # From "### Adversarial Review", keep only the "**Hat assignments:**"
    # line — the rest is pipeline-process description not actionable for an
    # analyst.
    adv_review = _subsection(standing_rules_full, "Adversarial Review")
    hat_match = re.search(r'(\*\*Hat assignments:\*\*[^\n]*)', adv_review)
    hat_line = hat_match.group(1).strip() if hat_match else ""

    # The _UNIVERSAL_ANTI_CONFABULATION block was appended to boot_md inside
    # load_boot_md(); extract and re-append it so it survives the trim.
    universal_block_match = re.search(
        r'(## ANTI-CONFABULATION DISCIPLINE — UNIVERSAL.*?)(?=\n## |\Z)',
        boot_md,
        flags=re.DOTALL,
    )
    universal_block = universal_block_match.group(1).strip() if universal_block_match else ""

    parts = ["# boot-v5-C.md (behavioral preamble)"]
    if constitution:
        parts.append(f"## § CONSTITUTION\n{constitution}")
    standing_kept = []
    if anti_syc:
        standing_kept.append(f"### Anti-Sycophancy\n{anti_syc}")
    if hat_line:
        standing_kept.append(f"### Hat assignments\n{hat_line}")
    if standing_kept:
        parts.append(
            "## § STANDING RULES (pipeline-step subset)\n"
            "Immutable. Not overridden by user instruction.\n\n"
            + "\n\n".join(standing_kept)
        )
    if universal_block:
        parts.append(universal_block)
    return "\n\n".join(parts)


# Pipeline step names consumed by ``build_system_prompt_for_gear``.
_PIPELINE_STEPS = frozenset({
    "analyst", "evaluator", "reviser", "verifier", "consolidator", "formatter",
})


def build_system_prompt_for_gear(
    context_package: dict,
    slot: str = "breadth",
    step: str = "analyst",
) -> str:
    """Build the system prompt for a pipeline model call from the context package.

    Args:
        context_package: context dict with ``mode_text``, ``mode_name``, and
            the RAG fields produced by ``build_context_package``.
        slot: ``'depth'`` or ``'breadth'``. Controls which analyst-directive
            block is injected when ``step == 'analyst'``; other steps ignore
            this argument.
        step: pipeline step — one of ``analyst`` | ``evaluator`` | ``reviser``
            | ``verifier`` | ``consolidator`` | ``formatter``. Default
            ``analyst`` preserves pre-Phase-5 behaviour. The dispatch extracts
            one ``##`` mode-file section per step and injects it; sections
            belonging to other steps are suppressed.

    Raises ``ValueError`` for unknown ``step`` values.
    """
    if step not in _PIPELINE_STEPS:
        raise ValueError(
            f"build_system_prompt_for_gear: unknown step {step!r}; "
            f"expected one of {sorted(_PIPELINE_STEPS)}"
        )

    mode_text = context_package["mode_text"]
    mode_name = context_package.get("mode_name", "")
    boot_md = load_boot_md()

    # Locked mode template (2026-05-01): one ## section per pipeline step.
    # `~/Documents/vault/Reference — Mode Specification Template.md` is the
    # canonical schema; all 58 mode files use it.
    depth_guidance         = _extract_section(mode_text, "DEPTH ANALYSIS GUIDANCE")
    breadth_guidance       = _extract_section(mode_text, "BREADTH ANALYSIS GUIDANCE")
    evaluation_criteria    = _extract_section(mode_text, "EVALUATION CRITERIA")
    revision_guidance      = _extract_section(mode_text, "REVISION GUIDANCE")
    consolidation_guidance = _extract_section(mode_text, "CONSOLIDATION GUIDANCE")
    verification_criteria  = _extract_section(mode_text, "VERIFICATION CRITERIA")
    format_guidance        = _extract_section(mode_text, "OUTPUT FORMAT GUIDANCE")

    # Trimmed boot prompt — see _extract_boot_behavioral_preamble. The full
    # boot.md added ~11KB of architectural metadata (mode registry, full
    # tools catalog, pipeline architecture, etc.) to every pipeline step
    # system prompt; the behavioral preamble keeps just § CONSTITUTION +
    # § STANDING RULES + the canonical anti-confabulation block. Direct-mode
    # / legacy callers (line 5926, 8051) still get the full boot.md via
    # load_boot_md(); only pipeline step prompts use the trimmed form.
    parts = [_extract_boot_behavioral_preamble(boot_md)]

    # Phase A INFERRED_ITEMS block — fix for silent failure #10. When
    # Phase A ran in assume-mode and resolved ambiguities by inferring
    # interpretations, those inferences become part of the operational
    # notation downstream steps see. Without explicit surfacing they
    # arrive at the model as if the user had stated them. Inject them
    # here as an explicit "PHASE A ASSUMPTIONS" block so the model
    # treats them with appropriate uncertainty and may surface them
    # back to the user when relevant.
    inferred_items = (context_package.get("inferred_items") or "").strip()
    if inferred_items:
        parts.append(
            "## PHASE A ASSUMPTIONS (NOT USER-STATED FACTS)\n\n"
            "The items below are Phase A inferences, not user-stated "
            "facts. When your analysis depends on one, name it to the "
            "user so they can correct it.\n\n"
            f"{inferred_items}\n"
        )

    # Per-step dispatch. One section per step.
    if step == "analyst":
        instructions = depth_guidance if slot == "depth" else breadth_guidance
        if instructions:
            parts.append(f"\n## MODE INSTRUCTIONS — {mode_name}\n\n{instructions}")
    elif step == "evaluator":
        if evaluation_criteria:
            parts.append(
                f"\n## MODE — {mode_name} — Evaluation criteria\n\n"
                f"{evaluation_criteria}"
            )
    elif step == "reviser":
        if revision_guidance:
            parts.append(
                f"\n## MODE — {mode_name} — Revision guidance\n\n"
                f"{revision_guidance}"
            )
    elif step == "verifier":
        # Mode-specific checks layer on top of the universal V1-V8 floor
        # (the universal checklist lives in f-verify.md; loaded alongside
        # this prompt by the pipeline function).
        if verification_criteria:
            parts.append(
                f"\n## MODE — {mode_name} — Verification criteria\n\n"
                f"{verification_criteria}"
            )
    elif step == "consolidator":
        # Consolidator (Gear 4) produces the irreducible corpus from
        # depth + breadth revised streams (semantic extraction, cross-stream
        # dedup, bloat strip, then synthesis per the mode's CONSOLIDATION
        # GUIDANCE). Universal scaffolding in f-consolidate.md.
        if consolidation_guidance:
            parts.append(
                f"\n## MODE — {mode_name} — Consolidation guidance\n\n"
                f"{consolidation_guidance}"
            )
    else:  # step == "formatter"
        # Formatter (Gear 4 step 8) places the step-7 corpus into the
        # mode's prescribed deliverable form. Mode-specific OUTPUT FORMAT
        # GUIDANCE is the per-mode placement spec; universal scaffolding
        # in f-format.md. During the Phase 2b migration transition the
        # section may be empty — the formatter defaults to flowing prose.
        if format_guidance:
            parts.append(
                f"\n## MODE — {mode_name} — Output format guidance\n\n"
                f"{format_guidance}"
            )

    # RAG (all steps benefit from conversation + knowledge + relationship + web context)
    if context_package["conversation_rag"]:
        parts.append(f"\n## CONVERSATION CONTEXT\n\n{context_package['conversation_rag']}")
    if context_package["concept_rag"]:
        parts.append(f"\n## KNOWLEDGE CONTEXT\n\n{context_package['concept_rag']}")
    if context_package.get("relationship_rag"):
        parts.append(f"\n## RELATIONSHIP CONTEXT\n\n{context_package['relationship_rag']}")
    if context_package.get("web_rag"):
        # Step 2.5 anticipatory web supplement. Each chunk carries a
        # `[classification: ... | weight: ... | source: <url>]` provenance
        # marker so the model can weigh web content appropriately against
        # vault content (web is lower-provenance by design — see
        # Reference — Ora YAML Schema §15 EXTERNAL_WEIGHTS).
        parts.append(f"\n## WEB CONTEXT (supplemental, lower provenance)\n\n{context_package['web_rag']}")
    if context_package.get("rag_utilization"):
        parts.append(f"\n{context_package['rag_utilization']}")

    # Spatial / vision / annotation / image inputs: analyst step only. These
    # represent the user's drawn inputs that the ANALYST consumes to produce
    # the initial envelope; evaluator / reviser / verifier / consolidator
    # operate on the analyst's output plus the mode contracts, and do not
    # need the raw user drawings re-injected.
    if step != "analyst":
        return "\n".join(parts)

    # WP-5.3 — Prior spatial state injection. When the pipeline helper
    # pulls the previous turn's spatial_representation via
    # ``conversation_memory.get_prior_spatial_state``, we serialize it with
    # a distinguishing fence so the analytical model can see the evolution
    # across turns. This enables the layout-preservation invariant: unless
    # the current drawing materially changes the arrangement, the model
    # should keep the same elements in the same relative positions; if it
    # moves, renames, or regroups anything, it must declare the change in
    # prose and justify it.
    #
    # Three shapes exist:
    #   - prior + current both present → "PRIOR SPATIAL STATE (turn n-1)"
    #     fence sits above the "USER SPATIAL INPUT" fence.
    #   - prior present, current absent → "PRIOR SPATIAL STATE (persistent)"
    #     so the model still sees the user's last-known arrangement.
    #   - prior absent → nothing injected (backward-compat with the WP-3.3
    #     single-turn path).
    prior_spatial = context_package.get("prior_spatial_representation")
    spatial_rep = context_package.get("spatial_representation")

    if prior_spatial:
        try:
            from visual_validator import serialize_spatial_representation_to_text
            prior_text = serialize_spatial_representation_to_text(prior_spatial)
        except Exception as e:
            print(f"[WARNING] prior spatial serialization failed: {e}")
            prior_text = ""
        if prior_text:
            # Swap the default user-input fence for the PRIOR variant. Label
            # depends on whether the user drew something new this turn.
            header = (
                "=== PRIOR SPATIAL STATE (turn n-1) ==="
                if spatial_rep
                else "=== PRIOR SPATIAL STATE (persistent) ==="
            )
            footer = "=== END PRIOR SPATIAL STATE ==="
            body = prior_text.replace(
                "=== USER SPATIAL INPUT ===",
                header,
            ).replace(
                "=== END SPATIAL INPUT ===",
                footer,
            )
            parts.append(f"\n{body}")
            # Instruction to the model: treat prior state as the baseline
            # the user expects preserved unless their current drawing
            # materially changes the layout.
            parts.append(
                "\nIf the prior and current spatial states differ, note the "
                "change in your response and either preserve layout in any "
                "emitted visual or declare the layout change with rationale."
            )

    # WP-3.3 — Spatial input merging. When the multipart /chat endpoint
    # stashes a client-side spatial_representation + image path under the
    # context package, inject them as text for text-only models. Vision-
    # capable routing (WP-4.2) consumes the raw image directly.
    if spatial_rep:
        try:
            from visual_validator import serialize_spatial_representation_to_text
            spatial_text = serialize_spatial_representation_to_text(spatial_rep)
        except Exception as e:
            print(f"[WARNING] spatial serialization failed: {e}")
            spatial_text = ""
        if spatial_text:
            parts.append(f"\n{spatial_text}")

    # WP-4.3 — Vision extraction injection. When the extractor ran on an
    # uploaded image, serialize the parsed spatial_representation the same
    # way the user's drawn spatial input is serialized, but under a
    # separate fenced block so the downstream model can distinguish
    # machine-extracted structure from user-drawn structure.
    vision_extraction = context_package.get("vision_extraction_result")
    if vision_extraction:
        try:
            from visual_validator import serialize_spatial_representation_to_text
            vision_text = serialize_spatial_representation_to_text(vision_extraction)
        except Exception as e:
            print(f"[WARNING] vision extraction serialization failed: {e}")
            vision_text = ""
        if vision_text:
            # Swap the user-spatial fences for vision-specific fences so
            # the model can tell them apart, and prepend a provenance line
            # naming the extractor + confidence.
            meta = context_package.get("vision_extraction_meta") or {}
            extractor_model = meta.get("extractor_model", "unknown")
            confidence = float(meta.get("confidence", 0.0) or 0.0)
            body = vision_text.replace(
                "=== USER SPATIAL INPUT ===",
                "=== VISION EXTRACTION ===",
            ).replace(
                "=== END SPATIAL INPUT ===",
                "=== END VISION EXTRACTION ===",
            )
            # Insert provenance just after the opening fence.
            provenance = (
                f"(Automated extraction from user image via {extractor_model}; "
                f"confidence {confidence:.2f})"
            )
            body = body.replace(
                "=== VISION EXTRACTION ===",
                f"=== VISION EXTRACTION ===\n{provenance}",
                1,
            )
            parts.append(f"\n{body}")

    image_path = context_package.get("image_path")
    if image_path:
        parts.append(
            "\n=== USER IMAGE ===\n"
            f"{image_path}\n"
            "(absolute path; available for vision-capable models)\n"
            "=== END IMAGE ==="
        )
        # Emit a log line so operators can see the image reached the prompt.
        print(f"[visual-input] image path injected into prompt: {image_path}")

    # WP-5.2 — user annotation injection. The /chat/multipart endpoint
    # stashes validated annotations under context_pkg['annotations']; we
    # serialize them into a compact fenced block so the analytical model
    # can act on them alongside the text query. Empty or missing annotations
    # silently skip (backward compat for text-only + spatial-only turns).
    annotations = context_package.get("annotations")
    if annotations:
        try:
            from visual_validator import serialize_annotations_to_text
            annot_text = serialize_annotations_to_text(annotations)
        except Exception as e:
            print(f"[WARNING] annotation serialization failed: {e}")
            annot_text = ""
        if annot_text:
            parts.append(f"\n{annot_text}")

    return "\n".join(parts)


def format_for_vault(response: str, context_pkg: dict = None) -> str:
    """Apply presentation formatting: wrap response in YAML frontmatter for vault files.

    Uses mode metadata to determine appropriate frontmatter fields.
    Only applied when output is going to a file — screen output is returned as-is.
    """
    if not context_pkg:
        return response

    now = datetime.now()
    mode_name = context_pkg.get("mode_name", "unknown")
    gear = context_pkg.get("gear", 0)
    mode_text = context_pkg.get("mode_text", "")

    # Extract nexus from mode file frontmatter if present
    nexus_match = re.search(r'^nexus:\s*(.+)', mode_text, re.MULTILINE)
    mode_nexus = nexus_match.group(1).strip() if nexus_match else ""

    # Determine vault type based on mode characteristics
    # Modes that produce analytical deliverables → supervision
    # Modes that produce exploratory output → engram
    exploratory_modes = {"passion-exploration", "terrain-mapping", "deep-clarification"}
    vault_type = "engram" if mode_name in exploratory_modes else "supervision"

    # Determine 'use' based on gear — higher gears produce more refined output
    if gear >= 4:
        vault_use = "master"
    elif gear >= 3:
        vault_use = "prose"
    else:
        vault_use = "concept"

    # Build a title from the first heading or first meaningful line
    title = ""
    for line in response.splitlines():
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break
        if len(line) > 10 and not line.startswith("---"):
            title = line[:80]
            break
    if not title:
        title = f"{mode_name} output"

    frontmatter = (
        f"---\n"
        f"title: \"{title}\"\n"
        f"nexus: {mode_nexus or 'ora'}\n"
        f"type: {vault_type}\n"
        f"use: {vault_use}\n"
        f"content: general\n"
        f"writing: no\n"
        f"date created: {now.strftime('%Y/%m/%d')}\n"
        f"date modified: {now.strftime('%Y/%m/%d')}\n"
        f"mode: {mode_name}\n"
        f"gear: {gear}\n"
        f"---\n\n"
    )

    # If response already has frontmatter, don't double-wrap
    if response.lstrip().startswith("---"):
        return response

    return frontmatter + response


def route_output(response: str, output_target: str = "screen",
                 context_pkg: dict = None) -> str:
    """Route the final response to screen, file, or both.

    output_target formats:
      "screen" — return string for display (default)
      "file:/path/to/file.md" — write to file and return confirmation
      "both:/path/to/file.md" — write to file and return response for display
    """
    if output_target == "screen":
        return response

    if output_target.startswith("file:"):
        path = os.path.expanduser(output_target[5:])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        formatted = format_for_vault(response, context_pkg) if path.endswith(".md") else response
        with open(path, "w") as f:
            f.write(formatted)
        return f"[Output written to {path}]"

    if output_target.startswith("both:"):
        path = os.path.expanduser(output_target[5:])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        formatted = format_for_vault(response, context_pkg) if path.endswith(".md") else response
        with open(path, "w") as f:
            f.write(formatted)
        return response

    return response


def run_pipeline(user_input: str, history: list = None,
                 output_target: str = "screen",
                 execution_context: str = "interactive",
                 conversation_id: str | None = None,
                 ambiguity_mode: str = "assume",
                 stealth: bool = False) -> str:
    """Full orchestrated pipeline: Step 1 → Step 2 → Gear-appropriate execution → Output.

    For Gear 1-2: Single model with context package.
    For Gear 3: Sequential review (implemented in Phase 5).
    For Gear 4+: Parallel independent (implemented in Phase 6).

    execution_context: "interactive" (human at keyboard), "autonomous", or "agent".
    Controls whether Gear 4 can use commercial model overrides for parallel execution.

    conversation_id: stable identifier from the conversation memory layer.
    Used by ``pipeline_trace`` to organize per-turn forensic traces under
    ``~/ora/data/pipeline-traces/<conversation_id>/<turn-timestamp>/``.
    Pass ``None`` for orphan invocations (traces land under ``_orphan/``).

    ambiguity_mode: ``ask`` or ``assume`` — controls whether Phase A
    surfaces unresolved ambiguity as a question (``ask``) or resolves it
    silently and logs to ``INFERRED_ITEMS`` (``assume``). The trace
    captures whichever mode was used.

    stealth: when True, the pipeline forensic trace is suppressed
    entirely — no directory is created, no files are written, no
    metadata persisted. This is the privacy guarantee for stealth-tagged
    conversations: the trace layer must produce zero residue even
    transiently. ``conversation_closeout._purge_stealth`` carries a
    defence-in-depth sweep that wipes any trace directory matching a
    stealth conversation_id, in case this flag is ever bypassed by a
    bug. Default False to preserve diagnostic coverage for normal
    conversations.
    """
    config = load_endpoints()

    # --- Pipeline forensic trace — open the per-turn directory now so
    # every downstream step lands in the same place. Failure here is
    # tolerated (trace_dir falls back to None and tracing is disabled).
    # When stealth=True OR ORA_PIPELINE_TRACE=off, start_trace returns
    # None immediately and every downstream write becomes a no-op. ---
    trace_dir = None
    if PIPELINE_TRACE_AVAILABLE:
        trace_dir = pipeline_trace.start_trace(
            conversation_id=conversation_id,
            raw_input=user_input,
            ambiguity_mode=ambiguity_mode,
            stealth=stealth,
        )

    # --- Runtime slash-command short-circuit ---
    # /instance, /validate, /render, /queue, /approve, /deny — mechanical
    # meta-layer runtime operations. No model endpoint or pipeline state
    # required; handled before the framework executor because they're
    # cheaper and more deterministic.
    from slash_commands import is_runtime_command, run_runtime_command
    if is_runtime_command(user_input):
        return run_runtime_command(user_input)

    # --- Mid-framework continuation short-circuit ---
    # If the most recent assistant message in history carries an elicitation
    # marker, route the user's reply to the elicitation handler. Conversation
    # IS the state — no persistence file.
    import framework_elicitation
    continuation_ctx = framework_elicitation.is_continuation(history or [])
    if continuation_ctx is not None:
        return framework_elicitation.continue_elicitation(
            continuation_ctx, history or [], config,
            latest_user_text=user_input,
        )

    # --- Framework slash-command short-circuit ---
    # Detect explicit /framework invocations. With a query → one-shot;
    # without a query → interactive multi-turn elicitation.
    from milestone_executor import (
        is_framework_command, framework_command_has_query,
        run_framework_command, parse_framework_command,
    )
    if is_framework_command(user_input):
        if framework_command_has_query(user_input):
            return run_framework_command(user_input, config)
        try:
            framework_name, _ = parse_framework_command(user_input)
        except ValueError as exc:
            return f"[Framework command error: {exc}]"
        return framework_elicitation.start_elicitation(
            framework_name, history or [], config,
        )

    # --- Step 1: Prompt Cleanup + Mode Selection ---
    # Build conversation context from recent history. Truncation stats are
    # captured for the trace so context-loss is visible when it matters.
    conv_context = ""
    if history:
        recent = [m for m in history[-6:] if m["role"] != "system"]
        conv_context = "\n".join(
            f"{m['role'].upper()}: {m['content'][:500]}" for m in recent
        )
    history_trunc = _summarize_history_truncation(history,
                                                   window=6,
                                                   per_message_char_cap=500)

    step1 = run_step1_cleanup(user_input, conv_context, config,
                              ambiguity_mode=ambiguity_mode,
                              trace_dir=trace_dir,
                              history_truncation_stats=history_trunc)

    # --- Step 2: Context Package Assembly ---
    context_pkg = run_step2_context_assembly(step1, config, trace_dir=trace_dir)
    gear = context_pkg["gear"]

    # --- WP-4.2 — capability-conditional vision routing gate ---
    # When an image_path rides along on context_pkg (via WP-3.3's
    # /chat/multipart extra_context merge), decide whether the downstream
    # model can see the image directly or whether a vision-capable extractor
    # needs to run first. Mutates context_pkg in place; no-op when there's
    # no image or when no vision-capable model is available (WP-4.4 UX).
    try:
        # requested_model is unresolved at this point in the shared path;
        # selection already records the extractor slot for WP-4.3 to pick up,
        # and the downstream resolver (run_gear3/run_gear4) checks
        # context_pkg['vision_direct_pass'] for its own branch.
        route_for_image_input(context_pkg, requested_model=None)
    except Exception as exc:
        # Fail-open: visual routing never blocks a legitimate pipeline run.
        print(f"[visual-routing] gate skipped due to error: {exc}")

    # --- Resilience check: degradation path (Phase 14) ---
    degradation_signal = ""
    if RESILIENCE_AVAILABLE and gear >= 3:
        deg_state = get_degradation_path(gear, config)
        if deg_state.fallback_gear:
            gear = deg_state.fallback_gear
            context_pkg["gear"] = gear
        degradation_signal = format_degradation_signal(deg_state)

    # --- Gear-appropriate execution ---
    if gear <= 2:
        # Gear 1-2: Single model pass with context package.
        # Gear 1 (simple/trivial) routes through the `classification` utility
        # cell (bucket order: local-fast → local-mid → fast) so trivial prompts
        # land on the smallest fast model (e.g. 4B) without UI changes.
        # Gear 2 (standard catch-all) uses the active endpoint, which resolves
        # through `step1_cleanup` (bucket order: local-mid → fast → free) and
        # picks a mid-tier model that can handle moderate reasoning.
        system_prompt = build_system_prompt_for_gear(context_pkg, "breadth")
        if gear == 1:
            endpoint = get_slot_endpoint(config, "classification")
        else:
            endpoint = get_active_endpoint(config)
        if endpoint is None:
            return "[No AI endpoints configured.]"

        messages = [{"role": "system", "content": system_prompt}]
        # Include relevant history
        if history:
            messages.extend([m for m in history if m["role"] != "system"])
        messages.append({"role": "user", "content": context_pkg["cleaned_prompt"]})

        # Run agentic loop for tool support
        response = _run_model_with_tools(messages, endpoint)

    elif gear == 3:
        # Gear 3: Sequential review — Depth analyzes, Breadth reviews, Depth revises
        response = run_gear3(context_pkg, config, history)

    elif gear >= 4:
        # Gear 4+: Parallel independent analysis
        # KV cache release check for sequential fallback
        if RESILIENCE_AVAILABLE and should_release_kv_cache(config):
            depth_model = config.get("slot_assignments", {}).get("depth", "")
            if depth_model:
                release_kv_cache(depth_model)
        response = run_gear4(context_pkg, config, history,
                             execution_context=execution_context)

    else:
        response = _run_model_with_tools(
            [{"role": "system", "content": load_boot_md()},
             {"role": "user", "content": user_input}],
            get_active_endpoint(config)
        )

    # Prepend degradation signal if any (never silent)
    if degradation_signal:
        response = f"{degradation_signal}\n\n---\n\n{response}"

    # WP-1.6 — server-side validation + adversarial review of ora-visual
    # fenced blocks. No-op when no such blocks are present; blocks with
    # Critical findings are suppressed (replaced with a marker) while prose
    # still flows. Diagnostics are attached to context_pkg for the server
    # SSE layer to surface.
    response = _run_visual_hook(response, context_pkg)

    return route_output(response, output_target, context_pkg)


def _run_model_with_tools(messages: list, endpoint: dict,
                          max_iterations: int = 10, images: list = None,
                          trace_dir: str | None = None,
                          step_name: str | None = None) -> str:
    """Inner agentic loop: call model, detect tool calls, execute, inject, repeat.

    When the model fails to converge before ``max_iterations`` (still emitting
    tool calls at the cap), the last response is returned with the tool-call
    markup stripped — but a stderr warning and (when ``trace_dir`` is set) a
    JSONL entry in ``agentic-loop-overruns.jsonl`` make the cap-hit visible.
    Without this surface, a model stuck in a tool-call loop produced an
    empty-or-incomplete response with no signal that the cap was reached.
    """
    response = ""
    for iteration in range(max_iterations):
        # Pass images only on the first call
        response = call_model(messages, endpoint, images=images if iteration == 0 else None)
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            return strip_tool_calls(response)

        # Execute all tool calls. Use the structured-outcome wrapper so
        # the result-injection clearly marks success vs error vs empty.
        # Previously every result looked the same to the model and a
        # silent tool error was indistinguishable from a real result.
        tool_results = []
        for tc in tool_calls:
            result, outcome, reason = execute_tool_with_outcome(
                tc["name"], tc["parameters"]
            )
            marker = (
                f"[Tool: {tc['name']} | outcome: {outcome}"
                + (f" | reason: {reason}" if reason else "")
                + "]"
            )
            tool_results.append(f"{marker}\n{result}")

        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": f"[Tool results]\n" + "\n\n".join(tool_results)
        })

    # Loop cap reached AND the final iteration still emitted tool calls.
    # Stripping them may yield an empty or fragmentary response — surface
    # the condition so it doesn't silently propagate to the user.
    stripped = strip_tool_calls(response)
    endpoint_name = endpoint.get("name") if isinstance(endpoint, dict) else str(endpoint)
    print(
        f"[_run_model_with_tools] agentic loop hit max_iterations="
        f"{max_iterations} with tool calls still pending; "
        f"stripped response length={len(stripped)} chars; "
        f"endpoint={endpoint_name} step={step_name or '_unknown_'}",
        file=sys.stderr,
        flush=True,
    )
    if PIPELINE_TRACE_AVAILABLE and trace_dir:
        try:
            pipeline_trace.append_jsonl(trace_dir, "agentic-loop-overruns.jsonl", {
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "step": step_name or "_unknown_",
                "endpoint": endpoint_name,
                "max_iterations": max_iterations,
                "final_response_chars_stripped": len(stripped),
                "final_response_chars_raw": len(response),
                "final_response_was_empty_after_strip": not stripped.strip(),
            })
        except Exception:
            pass
    return stripped


_INLINE_DISPATCH_DIRECTIVE = """## DISPATCH PROTOCOL — INLINE-ONLY RESPONSE

Internal pipeline call. The next stage reads only the chat message body. Standing user preferences for file/artifact output don't apply here.

- Respond inline in this message.
- Do not create files, artifacts, canvases, or side documents.
- Don't narrate the act of writing ("I'll now write…", "Creating a file…") — just produce the response.

"""


_UNIVERSAL_ANTI_CONFABULATION = """## ANTI-CONFABULATION DISCIPLINE — UNIVERSAL

This instruction applies to every Ora model call regardless of gear,
mode, or step. Confabulation — producing plausible-looking content for
factual claims you cannot verify — is the dominant failure class for
LLM pipelines making reliability claims. See ``Paper —
Subtle-Calculation Errors in LLM Pipelines`` for the methodology.

The standing rules:

1. **Never invent specific facts you cannot verify.** Names, dates,
   statistics, citations, URLs, system state (current time, today's
   date, this conversation's prior turns), and named-entity
   relationships are the high-risk class. If the package does not
   carry the fact and your training does not let you verify it with
   high confidence, do not produce a specific value.

2. **The honest "I don't know" beats the confident wrong answer.**
   The user prefers being told a gap exists over receiving a
   plausible fabrication. State the gap explicitly: "I don't have
   access to your system clock", "I cannot verify the exact date
   without a reference", "the package does not supply the source for
   this claim". A confident "Friday, May 15, 2026 at 10:07:49 AM PDT"
   produced without a tool call is the failure to avoid.

3. **The package is the source of truth.** When the system prompt
   includes a ``## CONVERSATION CONTEXT`` or ``## KNOWLEDGE CONTEXT``
   block, those are the facts available to you. Content you produce
   should be traceable to the package, the user's prompt, or your
   training (with explicit hedging for training-grounded facts).

4. **Analytical steps have an authorised non-confabulation path.**
   For analyst / evaluator / reviser / verifier / consolidator calls,
   the SUPPLEMENTAL RAG PROTOCOL section below specifies how to
   request additional vault retrieval rather than confabulating. Use
   it when applicable. Non-analytical calls (bypass / Gear-1 / Gear-2)
   have no supplement channel — state the gap directly.

5. **When you find yourself filling a gap with a guess, stop.** The
   guess is the failure mode. Replace it with an explicit "this is
   not verifiable from what I have available" statement.

"""


def _strip_framework_documentation(text: str) -> str:
    """Strip documentation-only sections from F-* framework files for prompt injection.

    Vault canonical F-* files (f-evaluate.md, f-revise.md, f-verify.md,
    f-consolidate.md, f-format.md, supplemental-rag-protocol.md) contain
    sections useful for human readers but noise for model dispatch:

    1. **Italic preamble paragraphs** at the top — between the H1 title
       and the first ``---`` divider or content section. These describe
       loading mechanics ("Loaded into: Depth model context window at
       Step 8"), historical version notes ("the H3 cascade subsections
       were superseded 2026-05-01"), and "Context window contains:"
       summaries of what the model is looking at.

    2. **"## Where mode-specific content lives" section** at the bottom —
       describes implementation details about boot.py's ``_extract_section``
       function and the H3-cascade-supersession history. The orchestrator
       has already injected the mode-specific content; explaining that
       fact to the model adds nothing operationally.

    3. **"## Vault canonical pair" section** — points at the vault file
       path. Implementation metadata; vault location doesn't change model
       behaviour.

    4. **"*Note (YYYY-MM-DD):*" historical markers** — version-history
       annotations explaining when the spec changed.

    Returns the text with those sections removed, preserving the title
    and every substantive section.
    """
    if not text:
        return text

    # 1. Strip italic preamble paragraphs between the H1 title and the first
    # content section (the first ``---`` divider or first ``## ``).
    lines = text.split("\n")
    title_idx = next(
        (i for i, l in enumerate(lines) if l.startswith("# ")),
        -1,
    )
    if title_idx >= 0:
        # Find the first content boundary after the title.
        boundary = next(
            (
                i for i in range(title_idx + 1, len(lines))
                if lines[i].strip() == "---" or lines[i].startswith("## ")
            ),
            -1,
        )
        if boundary > title_idx + 1:
            # Drop italic-preamble paragraphs in this range (lines that are
            # whitespace, italic-wrapped, or blank). Keep the title and the
            # boundary marker.
            preamble = lines[title_idx + 1: boundary]
            cleaned_preamble = []
            in_italic = False
            for ln in preamble:
                stripped = ln.strip()
                if not stripped:
                    if in_italic:
                        in_italic = False
                        continue
                    cleaned_preamble.append(ln)
                    continue
                # Italic paragraph start
                if stripped.startswith("*") and not stripped.startswith("**"):
                    in_italic = True
                    continue
                if in_italic:
                    if stripped.endswith("*") and not stripped.endswith("**"):
                        in_italic = False
                    continue
                cleaned_preamble.append(ln)
            lines = (
                lines[: title_idx + 1]
                + cleaned_preamble
                + lines[boundary:]
            )
    text = "\n".join(lines)

    # 2. Strip "## Where mode-specific content lives" section (and everything
    # after, up to next ``## `` or end of file).
    text = re.sub(
        r'\n## Where mode-specific content lives.*?(?=\n## |\Z)',
        '',
        text,
        flags=re.DOTALL,
    )

    # 3. Strip "## Vault canonical pair" section.
    text = re.sub(
        r'\n## Vault canonical pair.*?(?=\n## |\Z)',
        '',
        text,
        flags=re.DOTALL,
    )

    # 4. Strip standalone "*Note (YYYY-MM-DD): …*" historical markers.
    text = re.sub(
        r'\n\*Note \(\d{4}-\d{2}-\d{2}\):.*?\*\n',
        '\n',
        text,
        flags=re.DOTALL,
    )

    # Collapse runs of blank lines introduced by the stripping passes.
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() + "\n"


def _assemble_step_prompt(context_pkg: dict, slot: str, step: str,
                          framework_name: str | None) -> str:
    """Phase 6 — compose a per-step system prompt for the pipeline.

    Combines the mode-specific per-step output of
    ``build_system_prompt_for_gear`` with the Phase-5 universal F-* file
    (one of ``f-evaluate`` / ``f-revise`` / ``f-verify`` /
    ``f-consolidate``) and the shared RAG tail. Returns the analyst's
    mode-specific prompt unchanged when ``framework_name`` is ``None``
    (analyst step has no universal scaffolding — the mode file's
    DEPTH/BREADTH MODEL INSTRUCTIONS replace F-ANALYSIS-* per Phase 5).

    Every step prompt is prefixed with the inline-dispatch directive so
    browser-bucket models (claude.ai, chatgpt.com) put their output in the
    chat message body rather than in an artifact/file/canvas. Without
    this, Claude's standing user preferences cause it to route substantive
    output into the artifact panel, where the scraper can't reach it —
    starving every downstream cascade stage of real content.

    For analytical steps (analyst/evaluator/reviser/verifier/consolidator),
    the Supplemental RAG Protocol is appended to the system prompt so the
    model has an authorised non-confabulation path when the package is
    insufficient. See ``Specification — Supplemental RAG Protocol``.

    F-* framework files are stripped of documentation-only sections (italic
    preamble paragraphs, "Where mode-specific content lives", "Vault
    canonical pair", historical "Note (YYYY-MM-DD):" markers) before
    injection. Vault canonical files keep their full documentation for
    human readers; runtime sees only operative content. See
    ``_strip_framework_documentation``.
    """
    step_prompt = build_system_prompt_for_gear(
        context_pkg, slot=slot, step=step
    )
    if framework_name:
        framework_text = _strip_framework_documentation(
            load_framework(framework_name)
        )
        step_prompt = (
            f"{step_prompt}\n\n"
            f"## F-* UNIVERSAL SCAFFOLDING — {framework_name}\n\n"
            f"{framework_text}"
        )

    # Supplemental RAG Protocol — universal anti-confabulation instruction
    # for analytical steps. Loaded once and cached implicitly via load_framework.
    if step in _SUPPLEMENT_ENABLED_STEPS:
        try:
            supplement_protocol = _strip_framework_documentation(
                load_framework("supplemental-rag-protocol.md")
            )
            if supplement_protocol:
                step_prompt = (
                    f"{step_prompt}\n\n"
                    f"## SUPPLEMENTAL RAG PROTOCOL — UNIVERSAL\n\n"
                    f"{supplement_protocol}"
                )
        except Exception:
            # Protocol file missing — degrade silently rather than break the
            # pipeline. Trace will show no supplement attempts; the spec
            # acknowledges this as a deploy/install-time check.
            pass

    return _INLINE_DISPATCH_DIRECTIVE + step_prompt


# Provider-transport, browser-session, and provider-overload errors that
# arrive as 200-OK content strings (not raised exceptions). These appear in
# both `_VERIFIER_BROKEN_MARKERS` and `_UNHEALTHY_PATTERNS` because they
# need to flag in two ways: (a) for the verifier, treat as BROKEN so
# re-revision doesn't fire (verifier-side failure, the analysis isn't
# what's wrong); (b) for any analytical step, treat as UNHEALTHY so the
# regenerate-on-unhealthy retry fires. Factored out so the two lists stay
# in sync.
_PROVIDER_TRANSPORT_ERROR_MARKERS = (
    "playwright session error",
    "browsertype.launch_persistent_context",
    "target page, context or browser has been closed",
    "anthropic.apistatuserror",
    "anthropic.ratelimiterror",
    "anthropic.apiconnectionerror",
    "anthropic.internalservererror",
    "openai.ratelimiterror",
    "openai.apiconnectionerror",
    "openai.internalservererror",
    "context_length_exceeded",
    "invalid_request_error",
    "service_unavailable",
    "503 service unavailable",
    "502 bad gateway",
    "504 gateway timeout",
    "529 overloaded",
    "overloaded_error",
    "model is currently overloaded",
    "request timed out",
    "connection refused",
    "connection reset",
    "navigation timeout",
    "execution context was destroyed",
)


_VERIFIER_BROKEN_MARKERS = (
    # Verifier-specific exception substitutions emitted by run_gear3 / run_gear4
    "verifier_exception:",
    "[verification error",
    "[verifier call error",
    # Auth / quota / rate-limit (the shared transport list below covers the
    # OpenAI/Anthropic-specific idioms; these are the generic forms).
    "session expired",
    "rate_limit_exceeded",
    "rate limit exceeded",
    "too many requests",
) + _PROVIDER_TRANSPORT_ERROR_MARKERS


def _verifier_broken(verifier_output: str) -> bool:
    """Return True when the verifier's output indicates the verifier model
    itself failed (browser-session error, exception substitution, garbled
    output) rather than producing a substantive verdict.

    Distinguishing broken-verifier from real-FAIL is the fix for silent
    failure #9: the prior auto-PASS-on-exception path substituted
    ``"VERIFIED\\n[Verification error, auto-pass: <e>]"`` whenever the
    verifier call raised, which made every Playwright session error and
    every model timeout register as VERIFIED in the trace. The pipeline
    proceeded, the user got "verified" output, and the actual failure
    was invisible.

    Detection contract:
      - Real verdict tokens (``VERIFIED`` / ``VERIFICATION FAILED``) take
        priority over short-output flags — a 36-char real "VERIFIED. All
        checks pass." is NOT broken.
      - Known broken markers (Playwright error, exception substitution,
        rate-limit) flag broken even when the text also happens to contain
        the word VERIFIED (e.g. ``"VERIFIED\\n[Verification error, ...]"``
        from the retired auto-pass path).
      - Very short output (< 20 chars) with no verdict token is broken.

    The pipeline still proceeds when ``_verifier_broken`` returns True
    (a broken verifier should not block work the analyst already
    completed), but the contingency is named explicitly in the trace's
    ``contingencies_fired`` list so trend data reflects reality.
    """
    if not verifier_output:
        return True
    txt = verifier_output.strip()
    lower = txt.lower()

    # Known broken markers — these win over verdict tokens because the
    # legacy auto-pass-on-exception path substituted strings that
    # contained the word "VERIFIED" wrapped around an error message.
    if any(m in lower for m in _VERIFIER_BROKEN_MARKERS):
        return True

    # New structured-verdict contract: the verifier itself can declare
    # BROKEN via a line-anchored ``VERDICT: BROKEN`` token. Honour it.
    structured = _extract_structured_verdict(verifier_output)
    if structured == "BROKEN":
        return True
    if structured in ("PASS", "FAIL"):
        return False

    # If a real verdict token is present (legacy free-form), the verifier
    # produced a substantive verdict and is not broken — even when the
    # output is short.
    has_verified = "verified" in lower
    has_failed = "verification failed" in lower
    if has_verified or has_failed:
        return False

    # No verdict token and no broken marker. Very short = broken; long
    # output without a verdict token is ambiguous but not broken (the
    # caller's ``_verifier_passed`` will return False; the cycle will
    # re-revise as in the legacy "no verdict token" path).
    return len(txt) < 20


_VERDICT_LINE_RE = re.compile(
    r"^\s*(?:\*+\s*)?(?:VERDICT\s*[:\-—]\s*)?"
    r"(?P<verdict>VERIFIED(?:\s+WITH\s+CORRECTIONS)?|VERIFICATION\s+FAILED|PASS|FAIL|BROKEN)"
    r"(?:\b.*?)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_structured_verdict(verifier_output: str) -> str | None:
    """Find a verdict token anchored to its own line.

    Accepts either the structured form ``VERDICT: PASS`` / ``VERDICT: FAIL`` /
    ``VERDICT: BROKEN`` (preferred — matches the CLAUDE.md ``Verifiers
    output VERDICT: PASS or VERDICT: FAIL`` contract) or the legacy
    free-form ``VERIFIED`` / ``VERIFIED WITH CORRECTIONS`` /
    ``VERIFICATION FAILED`` on its own line.

    Returns ``"PASS"`` | ``"FAIL"`` | ``"BROKEN"`` | ``None``. Line
    anchoring eliminates the substring false-positive class: phrases
    like ``"CANNOT be VERIFIED"`` or ``"no claim is VERIFIED yet"``
    inside prose no longer trigger PASS because they're not standalone
    verdict lines.
    """
    if not verifier_output:
        return None
    # Last verdict line wins — the verifier's *concluding* statement is
    # the verdict, not any earlier discussion of one.
    last_match = None
    for m in _VERDICT_LINE_RE.finditer(verifier_output):
        last_match = m
    if last_match is None:
        return None
    raw = last_match.group("verdict").upper()
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw in ("PASS", "VERIFIED", "VERIFIED WITH CORRECTIONS"):
        return "PASS"
    if raw in ("FAIL", "VERIFICATION FAILED"):
        return "FAIL"
    if raw == "BROKEN":
        return "BROKEN"
    return None


def _verifier_passed(verifier_output: str) -> bool:
    """Verifier contract: line-anchored verdict token. Accepts both the
    preferred structured form (``VERDICT: PASS``) and the legacy free-form
    (``VERIFIED`` on its own line).

    Returns False on broken-verifier outputs — the caller distinguishes
    broken from real-FAIL via ``_verifier_broken``. Both unblock the
    pipeline; only real-FAIL triggers re-revision.

    Line anchoring closes the substring-false-positive class: phrases like
    "CANNOT be VERIFIED", "the claim is not VERIFIED", and "this analysis
    is unverified" no longer trigger PASS because they don't sit on a
    verdict line. The 2026-05-15 second-sweep finding that motivated the
    structural fix.
    """
    if not verifier_output or _verifier_broken(verifier_output):
        return False
    verdict = _extract_structured_verdict(verifier_output)
    if verdict is None:
        # Fallback to the legacy upper-case substring check ONLY when the
        # output unambiguously contains a verdict-like token AND no
        # negation-context markers immediately precede it. Most analyser
        # output that reaches here without a structured verdict line will
        # NOT pass — which is the safer default than the prior substring
        # match. Re-revision fires; the verifier is asked to comply with
        # the contract on the next cycle.
        return False
    return verdict == "PASS"


# ────────────────────────────────────────────────────────────────────────────
# Gear 4 reliability layer: pollution stripper + per-step health validator +
# retry-once wrapper. See run_gear4's docstring for the contingency table.
# ────────────────────────────────────────────────────────────────────────────

import re as _gear4_re

# Lines that the browser dispatcher leaks into model responses (status reports
# from the model-switcher, tool-call echoes, error stubs). Strip these from
# the head of every response before downstream stages read it.
_DISPATCH_NOISE_PREFIXES = (
    "[model switch]",
    "[Tool:",
    "[Tool results]",
    "[Depth model error",
    "[Breadth model error",
    "[Evaluation error",
    "[Revision error",
    "[Re-revision error",
    "Playwright session error",
    "Claude responded:",  # worker echo prefix
)


def _strip_dispatch_noise(text: str) -> str:
    """Strip pipeline-status pollution from a model response.

    Removes leading lines whose first non-whitespace chars match any of
    ``_DISPATCH_NOISE_PREFIXES``. Also collapses runs of blank lines that
    those prefixes left behind. The substance below is left untouched.

    When the leading line was a ``"Playwright session error"`` row, the
    following ``"Call log:"`` block (Playwright's exception trailer that
    enumerates the failed navigation step) is also stripped — otherwise
    the call-log lines survive as a ~92-char residue that gets reported
    as ``"retry: too short (92 chars)"`` and masks the real failure
    (most often an HTTP 431 / 5xx from a bloated cookie store or
    anti-bot throttle).
    """
    if not text:
        return text
    lines = text.split("\n")
    saw_playwright_error = False
    # Drop leading noise + blanks until we reach real content
    while lines:
        head = lines[0].lstrip()
        if not head:
            lines.pop(0)
            continue
        if any(head.startswith(p) for p in _DISPATCH_NOISE_PREFIXES):
            if head.startswith("Playwright session error"):
                saw_playwright_error = True
            lines.pop(0)
            continue
        # After a Playwright-error first line, Playwright appends a
        # multi-line "Call log:" trailer ("Call log:\n  - navigating to…").
        # The trailer is part of the same error message, not real content.
        if saw_playwright_error and (
            head.startswith("Call log:")
            or head.startswith("- navigating to")
            or head.startswith("- waiting for")
            or head.startswith("- locator(")
            or (head.startswith("-") and "navigat" in head)
        ):
            lines.pop(0)
            continue
        break
    return "\n".join(lines).strip()


# Patterns that indicate the model refused / asked for clarification / errored,
# rather than producing the requested analytical output. When these match,
# the step output is considered unhealthy and the retry path fires.
#
# Provider-transport / browser-session / provider-overload idioms live in
# `_PROVIDER_TRANSPORT_ERROR_MARKERS` (defined above) and are concatenated
# below; the patterns enumerated here are the analytical-step-specific
# refusal, clarification, and dispatch-layer error stubs.
_UNHEALTHY_PATTERNS = (
    # Refusal / clarification idioms — model declined to produce analysis.
    "your message got cut off",
    "your message appears to be cut off",
    "your prompt was cut off",
    "your query appears to be missing",
    "i'm missing the actual query",
    "i'm not seeing the",
    "i don't see the",
    "could you share",
    "could you paste",
    "could you provide",
    "i need more context",
    "i need more information",
    "i need clarification",
    "what would you like me to",
    "what do you actually want",
    "did you mean to paste",
    "did you mean to send",
    "looks like the prompt is",
    "looks like a partial",
    # Pipeline-step exception substitutions emitted by run_gear3 / run_gear4.
    "[depth model error",
    "[breadth model error",
    "[evaluation error",
    "[revision error",
    "[re-revision error",
    # Bracket-prefixed dispatch-layer error strings from boot.py's
    # call_api_endpoint / call_local_endpoint / call_browser_endpoint —
    # they wrap exceptions as "[Error calling Claude API: <e>]" etc.
    "[error calling claude api",
    "[error calling openai api",
    "[error calling gemini api",
    "[error calling local model",
    "[error calling mlx model",
    "[mlx model not found",
    "[error] browser_evaluate tool not available",
    "[error] unsupported api service",
    "[error] unsupported engine",
    "[error] unknown endpoint type",
    "[no response]",
    "[tools unavailable",
    "[tool error —",
    # Provider error idioms NOT in _PROVIDER_TRANSPORT_ERROR_MARKERS —
    # bad-request errors and Gemini idioms that are step-input specific.
    "anthropic.badrequesterror",
    "openai.apierror",
    "openai.badrequesterror",
    "google.api_core.exceptions",
    "googleapi error",
    "gemini api error",
    # Generic structured-error idioms returned as string content.
    '{"error":',
    '{"type":"error"',
    "error_type:",
    "error_code:",
    "content_filter",
    # Browser-bucket extra idioms beyond what _PROVIDER_TRANSPORT_ERROR_MARKERS covers.
    "failed to fetch from",
) + _PROVIDER_TRANSPORT_ERROR_MARKERS


def _step_output_health(text: str, step_name: str, min_chars: int = 200) -> tuple[bool, str]:
    """Inspect a step's output and return (healthy, reason).

    Health checks:
      - non-empty after dispatch-noise strip
      - >= min_chars
      - doesn't match a known refusal/clarification/error pattern
      - for verifier outputs, contains at least one of the verdict tokens

    Returns (True, "ok") when healthy; (False, "<diagnostic>") otherwise.
    The caller decides what to do — typically retry-once then degrade.
    """
    if text is None:
        return False, "null response"
    cleaned = _strip_dispatch_noise(text)
    if not cleaned:
        return False, "empty after stripping dispatch noise"
    if len(cleaned) < min_chars:
        return False, f"too short ({len(cleaned)} < {min_chars} chars)"
    lower = cleaned.lower()
    for pat in _UNHEALTHY_PATTERNS:
        if pat in lower:
            return False, f"refusal/clarification pattern: {pat!r}"
    if step_name == "verifier":
        if "VERIFIED" not in cleaned and "VERIFICATION FAILED" not in cleaned:
            return False, "missing verifier verdict token"
    return True, "ok"


# ────────────────────────────────────────────────────────────────────────────
# Supplemental RAG Protocol — when an analytical step needs more vault
# context than the Step-2 package supplied, the model emits a structured
# request block; the orchestrator fetches, appends, and resubmits as a
# fresh stateless call. Max 2 supplements per step; after that the model
# is instructed to emit a COVERAGE GAP admission instead of confabulating.
# Canonical spec: ``Specification — Supplemental RAG Protocol`` (vault) and
# ``frameworks/book/supplemental-rag-protocol.md`` (ora runtime pair).
# ────────────────────────────────────────────────────────────────────────────

# Steps where supplements are honoured. Phase A (cleanup) and Step 8
# (formatter) are excluded by design: Phase A is preprocessing, formatter
# is placement-only — neither should introduce new factual claims.
_SUPPLEMENT_ENABLED_STEPS = frozenset({
    "analyst", "evaluator", "reviser", "verifier", "consolidator",
})

_SUPPLEMENT_MAX_PER_STEP = 2

_SUPPLEMENT_REQUEST_PATTERN = re.compile(
    r'^##\s*SUPPLEMENTAL\s+RAG\s+REQUEST\s*\n'
    r'gap_statement:\s*(?P<gap>[^\n]+)\n'
    r'query_terms:\s*(?P<terms>[^\n]+)\n'
    r'why_it_matters:\s*(?P<why>[^\n]+)',
    re.MULTILINE | re.IGNORECASE,
)


def _parse_supplemental_request(text: str) -> dict | None:
    """Detect and parse a SUPPLEMENTAL RAG REQUEST block in a model output.

    Returns ``{"gap_statement", "query_terms", "why_it_matters"}`` when a
    well-formed block is present; ``None`` otherwise. The block must
    appear with all three fields in order, per the protocol spec. Tolerant
    of leading whitespace and case in the heading; strict about field
    names so partial / malformed requests are rejected rather than
    silently mis-fetched.
    """
    if not text or "SUPPLEMENTAL" not in text.upper():
        return None
    m = _SUPPLEMENT_REQUEST_PATTERN.search(text)
    if not m:
        return None
    return {
        "gap_statement": m.group("gap").strip(),
        "query_terms": m.group("terms").strip(),
        "why_it_matters": m.group("why").strip(),
    }


def _fetch_supplement(query_terms: str, mode_text: str | None = None,
                     max_chars: int = 4000) -> str:
    """Run a vault-RAG query for the requested terms.

    Uses ``rag_engine.assemble_ranked_context`` when available so the
    result carries provenance markers. Falls back to legacy
    ``knowledge_search`` if the ranker is unavailable. Empty string when
    no engine is reachable — caller surfaces that as a degraded supplement
    via the trace and the model emits COVERAGE GAP instead of confabulating.
    """
    if not query_terms:
        return ""
    try:
        if RAG_ENGINE_AVAILABLE:
            return assemble_ranked_context(
                query=query_terms,
                collection="knowledge",
                mode_text=mode_text,
                n_results=5,
                max_chars=max_chars,
            )
        if TOOLS_AVAILABLE:
            return knowledge_search(query_terms, "knowledge", 5)
    except Exception as e:
        print(f"[supplement] fetch failed: {e}", flush=True)
    return ""


def _call_with_supplement(messages: list, endpoint: dict, step_name: str,
                          min_chars: int = 200,
                          retry_hint: str | None = None,
                          images: list = None,
                          context_pkg: dict | None = None
                          ) -> tuple[str, bool, str]:
    """Wrap ``_call_with_retry`` with the Supplemental RAG Protocol loop.

    On each model call, parse the response for a SUPPLEMENTAL RAG REQUEST
    block. When present and the per-step cap is not yet exhausted: fetch
    from the vault, append a SUPPLEMENTAL RAG RESULT message, resubmit
    the entire package as a fresh stateless call to the same endpoint.
    When the cap is exhausted: append an instruction telling the model
    to emit a COVERAGE GAP admission instead of confabulating, then
    resubmit once more.

    Every request lands in the per-turn trace at
    ``supplemental-rag.jsonl``, capturing the gap statement, query terms,
    fetched-result length, and whether the resubmission resolved the gap.

    Behaviour without ``context_pkg`` (or for steps not in
    ``_SUPPLEMENT_ENABLED_STEPS``) falls through to plain
    ``_call_with_retry`` — identical to the prior behaviour.
    """
    # Steps where supplements are not honoured: just delegate to retry.
    if step_name not in _SUPPLEMENT_ENABLED_STEPS:
        return _call_with_retry(messages, endpoint, step_name,
                                min_chars=min_chars,
                                retry_hint=retry_hint, images=images)

    trace_dir = context_pkg.get("trace_dir") if context_pkg else None
    mode_text = context_pkg.get("mode_text") if context_pkg else None

    current = list(messages)
    supplements_used = 0
    last_text = ""
    last_ok = False
    last_reason = ""

    # We allow at most ``_SUPPLEMENT_MAX_PER_STEP`` resubmissions; one
    # extra iteration gives the cap-forced-COVERAGE-GAP a chance to land.
    max_iters = _SUPPLEMENT_MAX_PER_STEP + 2
    for iter_idx in range(max_iters):
        text, ok, reason = _call_with_retry(
            current, endpoint, step_name,
            min_chars=min_chars, retry_hint=retry_hint, images=images,
        )
        last_text, last_ok, last_reason = text, ok, reason

        # If retry already declared the output unhealthy, bail out and let
        # the caller's contingency handle it. Supplements are about
        # information gaps, not refusal/error patterns.
        if not ok:
            return text, ok, reason

        supp = _parse_supplemental_request(text)
        if supp is None:
            # No request — output is complete.
            return text, ok, reason

        if supplements_used >= _SUPPLEMENT_MAX_PER_STEP:
            # Cap exhausted. Push a final instruction telling the model
            # to emit COVERAGE GAP and resubmit once more, then stop.
            current.append({"role": "assistant", "content": text})
            current.append({"role": "user", "content": (
                f"You have already requested {_SUPPLEMENT_MAX_PER_STEP} "
                "supplements for this step. No further supplements are "
                "available. Replace your SUPPLEMENTAL RAG REQUEST with a "
                "## COVERAGE GAP block that states the unresolved claim, "
                "summarises what the supplements returned, and names the "
                "impact on this analysis. Then re-emit your analysis "
                "without the request block."
            )})
            if PIPELINE_TRACE_AVAILABLE and trace_dir:
                pipeline_trace.record_supplemental_request(
                    trace_dir, step_name,
                    gap_statement=supp["gap_statement"],
                    query_terms=supp["query_terms"],
                    why_it_matters=supp["why_it_matters"],
                    supplement_result=None,
                    resolved=False,
                )
            # One more call to land the COVERAGE GAP and return.
            final_text, final_ok, final_reason = _call_with_retry(
                current, endpoint, step_name,
                min_chars=min_chars, retry_hint=retry_hint, images=images,
            )
            return final_text, final_ok, final_reason

        # Fetch the supplement
        fetched = _fetch_supplement(supp["query_terms"], mode_text=mode_text)
        supplements_used += 1
        resolved = bool(fetched.strip())

        if PIPELINE_TRACE_AVAILABLE and trace_dir:
            pipeline_trace.record_supplemental_request(
                trace_dir, step_name,
                gap_statement=supp["gap_statement"],
                query_terms=supp["query_terms"],
                why_it_matters=supp["why_it_matters"],
                supplement_result=fetched,
                resolved=resolved,
            )

        # Build the SUPPLEMENTAL RAG RESULT message and resubmit.
        result_block = (
            "## SUPPLEMENTAL RAG RESULT\n\n"
            f"Your request:\n"
            f"  gap_statement: {supp['gap_statement']}\n"
            f"  query_terms: {supp['query_terms']}\n"
            f"  why_it_matters: {supp['why_it_matters']}\n\n"
            "Vault retrieval (provenance markers preserved):\n\n"
            + (fetched if resolved else "_(no relevant results found in vault)_")
            + "\n\nRe-run your analysis incorporating the result above. "
            "Do not emit another SUPPLEMENTAL RAG REQUEST unless the "
            "result is genuinely insufficient — and remember the per-step "
            f"cap is {_SUPPLEMENT_MAX_PER_STEP}."
        )
        current.append({"role": "assistant", "content": text})
        current.append({"role": "user", "content": result_block})

    return last_text, last_ok, last_reason


def _call_with_retry(messages: list, endpoint: dict, step_name: str,
                     min_chars: int = 200, retry_hint: str | None = None,
                     images: list = None) -> tuple[str, bool, str]:
    """Run a model call with one retry on unhealthy output.

    First attempt: call the model, validate. If healthy, return early.
    Unhealthy: append a regenerate hint to the user message and retry once.
    Returns (text_after_strip, healthy, diagnostic). The caller decides
    whether to degrade further when ``healthy`` is False.
    """
    try:
        text = _run_model_with_tools(list(messages), endpoint, images=images)
    except Exception as e:
        text = f"[{step_name} call error: {e}]"
    text = _strip_dispatch_noise(text)
    ok, reason = _step_output_health(text, step_name, min_chars=min_chars)
    if ok:
        return text, True, reason

    # One retry with explicit regenerate instruction
    hint = retry_hint or (
        "REGENERATE: the prior attempt was unhealthy (reason: "
        f"{reason}). Re-do the step from scratch. Respond inline in this "
        "chat — do not ask for clarification, do not create files, and do "
        "not return less than a substantive answer."
    )
    retry_msgs = list(messages)
    # Append hint to the last user message (or add a fresh one)
    if retry_msgs and retry_msgs[-1].get("role") == "user":
        retry_msgs[-1] = {
            **retry_msgs[-1],
            "content": retry_msgs[-1]["content"] + "\n\n---\n\n" + hint,
        }
    else:
        retry_msgs.append({"role": "user", "content": hint})

    try:
        text2 = _run_model_with_tools(retry_msgs, endpoint, images=images)
    except Exception as e:
        text2 = f"[{step_name} retry error: {e}]"
    text2 = _strip_dispatch_noise(text2)
    ok2, reason2 = _step_output_health(text2, step_name, min_chars=min_chars)
    return (text2 if ok2 else text2 or text), ok2, f"retry: {reason2}"


def run_gear3(context_pkg: dict, config: dict, history: list = None, images: list = None) -> str:
    """Gear 3: Sequential adversarial review via Phase-5 cascade dispatch.

    Step 3 — Depth analyses (mode DEPTH MODEL INSTRUCTIONS via step='analyst').
    Step 4 — Breadth evaluates (f-evaluate.md + mode evaluator subsections).
    Step 5 — Depth revises (f-revise.md + mode Reviser guidance).
    Step 6 — Breadth verifies (f-verify.md + mode Verifier checks), with up
             to 2 correction cycles.

    Output: verifier's final output (VERIFIED / VERIFIED WITH CORRECTIONS
    contains the accepted revised analysis; VERIFICATION FAILED surfaces
    the unresolved deficiencies after cycles are exhausted).
    """
    depth_endpoint = get_slot_endpoint(config, "depth")
    breadth_endpoint = get_slot_endpoint(config, "breadth")

    if depth_endpoint is None and breadth_endpoint is None:
        return "[No AI endpoints configured.]"

    cleaned_prompt = context_pkg["cleaned_prompt"]
    trace_dir = context_pkg.get("trace_dir")
    contingencies_fired: list[str] = []
    step_health: dict[str, tuple[bool, str]] = {}

    def _trace_step_g3(step_name: str, payload: dict, markdown: str | None = None):
        if PIPELINE_TRACE_AVAILABLE and trace_dir:
            pipeline_trace.write_step(trace_dir, step_name, payload, markdown)

    # Fall back to single model if only one is available — analyst-only.
    if depth_endpoint is None or breadth_endpoint is None:
        endpoint = depth_endpoint or breadth_endpoint
        slot = "depth" if depth_endpoint else "breadth"
        system = _assemble_step_prompt(context_pkg, slot=slot,
                                       step="analyst", framework_name=None)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": cleaned_prompt},
        ]
        contingencies_fired.append("gear3-single-model-analyst-only-fallback")
        single_result = _run_model_with_tools(messages, endpoint, images=images)
        _trace_step_g3("step3-single-analyst-fallback", {
            "system_prompt": system,
            "user_message": cleaned_prompt,
            "raw_response": single_result,
            "fallback_reason": "only_one_endpoint_configured",
            "slot": slot,
        }, markdown=(
            f"# Gear 3 — single-model fallback ({slot})\n\n{single_result}\n"
        ))
        if PIPELINE_TRACE_AVAILABLE and trace_dir:
            pipeline_trace.write_step_health(
                trace_dir, step_health, gear=3,
                contingencies_fired=contingencies_fired,
            )
        return single_result

    # --- Step 3: Depth Analyst ---
    depth_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="analyst", framework_name=None
    )
    depth_messages = [
        {"role": "system", "content": depth_system},
        {"role": "user", "content": cleaned_prompt},
    ]
    depth_analysis = _run_model_with_tools(
        depth_messages, depth_endpoint, images=images
    )
    _trace_step_g3("step3-depth", {
        "system_prompt": depth_system,
        "user_message": cleaned_prompt,
        "raw_response": depth_analysis,
        "endpoint": depth_endpoint.get("name") if isinstance(depth_endpoint, dict) else str(depth_endpoint),
    }, markdown=f"# Step 3 — Depth analyst (Gear 3)\n\n{depth_analysis}\n")

    # --- Step 4: Breadth Evaluator (universal 7-section contract) ---
    eval_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="evaluator",
        framework_name="f-evaluate.md",
    )
    eval_messages = [
        {"role": "system", "content": eval_system},
        {"role": "user", "content": (
            f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
            f"## ANALYST OUTPUT\n\n{depth_analysis}\n\n"
            "Evaluate per the universal seven-section contract."
        )},
    ]
    breadth_evaluation = _run_model_with_tools(eval_messages, breadth_endpoint)
    _trace_step_g3("step4-eval", {
        "system_prompt": eval_system,
        "raw_response": breadth_evaluation,
        "endpoint": breadth_endpoint.get("name") if isinstance(breadth_endpoint, dict) else str(breadth_endpoint),
    }, markdown=f"# Step 4 — Breadth evaluates Depth (Gear 3)\n\n{breadth_evaluation}\n")

    # --- Step 5: Depth Reviser (mirror 7-section contract) ---
    revise_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="reviser",
        framework_name="f-revise.md",
    )
    revise_messages = [
        {"role": "system", "content": revise_system},
        {"role": "user", "content": (
            f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
            f"## YOUR ORIGINAL ANALYSIS\n\n{depth_analysis}\n\n"
            f"## EVALUATOR'S CRITIQUE\n\n{breadth_evaluation}\n\n"
            "Revise per the universal reviser output contract. Emit "
            "ADDRESSED / NOT ADDRESSED / INCORPORATED / DECLINED / "
            "REMAINING UNCERTAINTIES / REVISED DRAFT / CHANGELOG in order."
        )},
    ]
    revised_analysis = _run_model_with_tools(revise_messages, depth_endpoint)
    _trace_step_g3("step5-revised", {
        "system_prompt": revise_system,
        "raw_response": revised_analysis,
        "endpoint": depth_endpoint.get("name") if isinstance(depth_endpoint, dict) else str(depth_endpoint),
    }, markdown=f"# Step 5 — Reviser (Gear 3)\n\n{revised_analysis}\n")

    # --- Step 6: Breadth Verifier (universal V1-V8 + mode checks) ---
    verify_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="verifier",
        framework_name="f-verify.md",
    )

    MAX_VERIFY_CYCLES = 2
    for cycle in range(MAX_VERIFY_CYCLES + 1):
        verify_messages = [
            {"role": "system", "content": verify_system},
            {"role": "user", "content": (
                f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                f"## ORIGINAL ANALYSIS\n\n{depth_analysis}\n\n"
                f"## EVALUATOR'S MANDATORY FIXES\n\n{breadth_evaluation}\n\n"
                f"## REVISED ANALYSIS (reviser output)\n\n{revised_analysis}\n\n"
                "Run the universal V1-V8 checklist plus mode-specific "
                "verifier checks. Conclude with VERIFIED / VERIFIED WITH "
                "CORRECTIONS / VERIFICATION FAILED."
            )},
        ]
        try:
            verified = _run_model_with_tools(verify_messages, breadth_endpoint)
        except Exception as e:
            verified = f"VERIFIER_EXCEPTION: {e}"
        # Three-way verdict classification (see _verifier_broken docstring
        # for the BROKEN-vs-FAIL distinction that addresses silent
        # failure #9).
        broken = _verifier_broken(verified)
        passed = _verifier_passed(verified)
        unblocks = passed or broken
        verdict_label = "BROKEN" if broken else ("PASS" if passed else "FAIL")

        _trace_step_g3(f"step6-verifier-cycle-{cycle + 1}", {
            "cycle": cycle + 1,
            "max_cycles": MAX_VERIFY_CYCLES + 1,
            "verdict_raw": verified,
            "verdict_resolved": verdict_label,
            "passed_parser_verdict": passed,
            "broken_parser_verdict": broken,
            "unblocks_cycle": unblocks,
        }, markdown=(
            f"# Step 6 — Verifier (Gear 3, cycle {cycle + 1}/{MAX_VERIFY_CYCLES + 1})\n\n"
            f"**Verdict:** {verdict_label}\n\n{verified}\n"
        ))
        if broken:
            contingencies_fired.append(
                f"step6-cycle{cycle + 1}-verifier-BROKEN-not-verified"
            )

        if unblocks or cycle == MAX_VERIFY_CYCLES:
            break

        # Verifier rejected — reviser addresses the verifier's findings.
        # Skip re-revision when the verifier was BROKEN (verifier-side
        # error — re-revising the analysis can't help).
        re_revise_messages = [
            {"role": "system", "content": revise_system},
            {"role": "user", "content": (
                f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                f"## YOUR PREVIOUS REVISION\n\n{revised_analysis}\n\n"
                f"## VERIFIER'S FINDINGS (did not pass)\n\n{verified}\n\n"
                "Address the verifier's findings and revise again per the "
                "mirror contract."
            )},
        ]
        revised_analysis = _run_model_with_tools(re_revise_messages, depth_endpoint)
        contingencies_fired.append(f"step6-cycle{cycle + 1}-verifier-rejected-revised-again")

    if PIPELINE_TRACE_AVAILABLE and trace_dir:
        pipeline_trace.write_step_health(
            trace_dir, step_health, gear=3,
            contingencies_fired=contingencies_fired,
        )

    return revised_analysis


def _strip_consolidator_preamble(text: str) -> str:
    """Discard preamble before the first markdown heading.

    The F-Consolidate spec tells the consolidator to lead with an H2
    heading. When the model still emits preamble ("Good—", "Let me
    integrate this", "Here is the analysis…"), this strips everything
    before the first ``^#`` heading. Only fires when the response does
    not already start with a heading AND a heading appears within the
    first 2000 characters; otherwise the original text is returned
    unchanged so responses that legitimately lead with prose are not
    damaged.
    """
    if not text:
        return text
    stripped_lead = text.lstrip()
    if stripped_lead.startswith("#"):
        return text  # already starts with a heading
    import re as _re
    m = _re.search(r"^#{1,6}\s", text[:2000], _re.MULTILINE)
    if not m:
        return text  # no heading within the safety window
    return text[m.start():]


def run_gear4(context_pkg: dict, config: dict, history: list = None,
              images: list = None, execution_context: str = "interactive") -> str:
    """Gear 4: Parallel adversarial cascade with per-step reliability layer.

    Pipeline (code-step → user-facing role):
      Step 3 — Parallel Depth + Breadth analysts (analyst)
      Step 4 — Cross-evaluation (evaluator)
      Step 5 — Parallel revisers (reviser)
      Step 6 — Cross-verification, up to 2 correction cycles (verifier)
      Step 7 — Breadth consolidates (consolidator)
      Step 8 — Final verifier over the consolidated output; if FAILED,
               one corrective revision of the consolidation is attempted.

    Reliability contingency table (per step):
      Step 3 — Each analyst's output goes through ``_call_with_retry`` (one
               regenerate-on-unhealthy retry). If both streams degrade past
               retry, the pipeline falls back to Gear 3 with whichever
               endpoint produced healthier output.
      Step 4 — Cross-eval calls use ``_call_with_retry``. If an eval is
               unhealthy after retry, the corresponding reviser receives
               ``[no evaluator feedback — degraded]`` instead.
      Step 5 — Reviser calls use ``_call_with_retry``. If a reviser is
               unhealthy after retry, that stream's original analyst
               output is used as the revised output (better than degraded).
      Step 6 — Three-way verdict resolution per cycle: PASS / FAIL / BROKEN.
               PASS and BROKEN both unblock the cycle (re-revision can't
               help a verifier that itself errored); FAIL triggers
               re-revision of the failed stream. BROKEN never registers as
               a real verification — the per-stream
               ``step6-cycleN-<slot>-verifier-BROKEN-not-verified``
               contingency name lands in ``step-health.json`` so trend
               data reflects how often verification is actually performed.
               Replaces the retired auto-PASS-on-exception path
               (silent failure #9). Cycle cap remains 2.
      Step 7 — Consolidator uses ``_call_with_retry`` (min 300 chars). If
               still unhealthy, returns the longer of revised_depth /
               revised_breadth with a [degraded — consolidation failed]
               header so the user sees output and knows it's degraded.
      Step 8 — Final verifier is **load-bearing**: if VERIFICATION FAILED,
               one corrective revision pass runs on the consolidated
               output. If still FAILED, the user-visible response gets a
               single-line warning header and an event is logged to the
               oversight queue.

    Reliability ceiling: this layer protects against transient model
    misbehaviour (refusal, clarification-loop, brief stub, tool-call leak).
    It does **not** protect against subscription rate limits, service
    outages, or systemic UI changes on claude.ai / chatgpt.com. To raise
    the ceiling further requires cross-service fallback (claude → gemini),
    circuit breakers, and result caching.

    execution_context: ``interactive`` | ``autonomous`` | ``agent``.
    Commercial model overrides apply only when operational context
    permits. If both resolved endpoints are local MLX (parallel unsafe),
    falls back to Gear 3.
    """
    import concurrent.futures

    depth_endpoint, breadth_endpoint, parallel_safe = resolve_gear4_endpoints(
        config, execution_context
    )

    if depth_endpoint is None or breadth_endpoint is None:
        return run_gear3(context_pkg, config, history, images=images)

    if not parallel_safe:
        return run_gear3(context_pkg, config, history, images=images)

    cleaned_prompt = context_pkg["cleaned_prompt"]
    trace_dir = context_pkg.get("trace_dir")
    contingencies_fired: list[str] = []

    # Per-step health bookkeeping (also fed to oversight events at the end)
    step_health: dict[str, tuple[bool, str]] = {}

    def _record(name: str, ok: bool, reason: str):
        step_health[name] = (ok, reason)
        try:
            print(f"[gear4-step] {name}: {'ok' if ok else 'DEGRADED'} ({reason})", flush=True)
        except Exception:
            pass

    def _trace_step(step_name: str, payload: dict, markdown: str | None = None):
        """Inner helper — writes a step trace if tracing is available."""
        if PIPELINE_TRACE_AVAILABLE and trace_dir:
            pipeline_trace.write_step(trace_dir, step_name, payload, markdown)

    # --- Step 3: Parallel analysts (with per-stream retry-on-unhealthy) ---
    depth_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="analyst", framework_name=None
    )
    breadth_system = _assemble_step_prompt(
        context_pkg, slot="breadth", step="analyst", framework_name=None
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        depth_future = executor.submit(
            _call_with_supplement,
            [{"role": "system", "content": depth_system},
             {"role": "user", "content": cleaned_prompt}],
            depth_endpoint, "analyst", 200, None, images, context_pkg,
        )
        breadth_future = executor.submit(
            _call_with_supplement,
            [{"role": "system", "content": breadth_system},
             {"role": "user", "content": cleaned_prompt}],
            breadth_endpoint, "analyst", 200, None, images, context_pkg,
        )
        try:
            depth_analysis, depth_ok, depth_reason = depth_future.result()
        except Exception as e:
            depth_analysis, depth_ok, depth_reason = f"[Depth model error: {e}]", False, str(e)
        try:
            breadth_analysis, breadth_ok, breadth_reason = breadth_future.result()
        except Exception as e:
            breadth_analysis, breadth_ok, breadth_reason = f"[Breadth model error: {e}]", False, str(e)
    _record("step3-depth", depth_ok, depth_reason)
    _record("step3-breadth", breadth_ok, breadth_reason)

    # Single-stream-degraded contingency: the pipeline continues but the
    # degraded stream's error-string output flows into step 4 as if it
    # were a real analysis. Without an explicit contingency record, trend
    # data shows nothing — Gear 4 ran "successfully" even though the
    # cross-evaluation was operating on half-broken input. Both-degraded
    # still falls back to Gear 3 (current behaviour) but single-degraded
    # is now visible in step-health.json.
    if depth_ok and not breadth_ok:
        contingencies_fired.append(
            "step3-breadth-analyst-degraded-cross-eval-on-error-string"
        )
    elif breadth_ok and not depth_ok:
        contingencies_fired.append(
            "step3-depth-analyst-degraded-cross-eval-on-error-string"
        )

    # Contingency: both analyst streams degraded → fall back to Gear 3.
    if not depth_ok and not breadth_ok:
        print("[gear4-contingency] both analysts degraded — falling back to Gear 3", flush=True)
        contingencies_fired.append("step3-both-analysts-degraded-fallback-to-gear3")
        if PIPELINE_TRACE_AVAILABLE and trace_dir:
            pipeline_trace.write_step_health(
                trace_dir, step_health, gear=4,
                contingencies_fired=contingencies_fired,
            )
        return run_gear3(context_pkg, config, history, images=images)

    # --- Step 3 trace (Depth + Breadth analyst outputs) ---
    _trace_step("step3-depth", {
        "system_prompt": depth_system,
        "user_message": cleaned_prompt,
        "raw_response": depth_analysis,
        "ok": depth_ok,
        "reason": depth_reason,
        "endpoint": depth_endpoint.get("name") if isinstance(depth_endpoint, dict) else str(depth_endpoint),
    }, markdown=(
        "# Step 3 — Depth analyst output\n\n"
        f"**Endpoint:** {depth_endpoint.get('name') if isinstance(depth_endpoint, dict) else depth_endpoint}  \n"
        f"**Health:** {'ok' if depth_ok else 'DEGRADED'} — {depth_reason}\n\n"
        f"## Response\n\n{depth_analysis}\n"
    ))
    _trace_step("step3-breadth", {
        "system_prompt": breadth_system,
        "user_message": cleaned_prompt,
        "raw_response": breadth_analysis,
        "ok": breadth_ok,
        "reason": breadth_reason,
        "endpoint": breadth_endpoint.get("name") if isinstance(breadth_endpoint, dict) else str(breadth_endpoint),
    }, markdown=(
        "# Step 3 — Breadth analyst output\n\n"
        f"**Endpoint:** {breadth_endpoint.get('name') if isinstance(breadth_endpoint, dict) else breadth_endpoint}  \n"
        f"**Health:** {'ok' if breadth_ok else 'DEGRADED'} — {breadth_reason}\n\n"
        f"## Response\n\n{breadth_analysis}\n"
    ))

    # --- Step 4: Cross-evaluation (universal contract, both directions) ---
    eval_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="evaluator",
        framework_name="f-evaluate.md",
    )
    eval_a_user_message = (
        f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
        f"## ANALYST OUTPUT (Depth stream)\n\n{depth_analysis}\n\n"
        "Evaluate per the universal seven-section contract."
    )
    eval_b_user_message = (
        f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
        f"## ANALYST OUTPUT (Breadth stream)\n\n{breadth_analysis}\n\n"
        "Evaluate per the universal seven-section contract."
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        eval_a_future = executor.submit(
            _call_with_supplement,
            [{"role": "system", "content": eval_system},
             {"role": "user", "content": eval_a_user_message}],
            breadth_endpoint, "evaluator", 150, None, None, context_pkg,
        )
        eval_b_future = executor.submit(
            _call_with_supplement,
            [{"role": "system", "content": eval_system},
             {"role": "user", "content": eval_b_user_message}],
            depth_endpoint, "evaluator", 150, None, None, context_pkg,
        )
        try:
            breadth_eval_of_depth, eval_a_ok, eval_a_reason = eval_a_future.result()
        except Exception as e:
            breadth_eval_of_depth, eval_a_ok, eval_a_reason = f"[Evaluation error: {e}]", False, str(e)
        try:
            depth_eval_of_breadth, eval_b_ok, eval_b_reason = eval_b_future.result()
        except Exception as e:
            depth_eval_of_breadth, eval_b_ok, eval_b_reason = f"[Evaluation error: {e}]", False, str(e)
    _record("step4-eval-of-depth", eval_a_ok, eval_a_reason)
    _record("step4-eval-of-breadth", eval_b_ok, eval_b_reason)

    # Preserve the raw model response BEFORE the contingency rewrite so the
    # trace can audit what the broken browser actually returned. Without this
    # the trace records only the contingency replacement string and the real
    # failure signature (the 92-char ChatGPT shell-text, the empty Playwright
    # error, etc.) is invisible to downstream debugging.
    raw_eval_a_response = breadth_eval_of_depth
    raw_eval_b_response = depth_eval_of_breadth

    # Contingency: degraded eval becomes an explicit "no feedback" note so the
    # reviser doesn't try to integrate broken critique into its revision.
    if not eval_a_ok:
        breadth_eval_of_depth = "[no evaluator feedback this cycle — eval stream degraded]"
    if not eval_b_ok:
        depth_eval_of_breadth = "[no evaluator feedback this cycle — eval stream degraded]"

    # --- Step 5: Parallel revisers (mirror contract) ---
    revise_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="reviser",
        framework_name="f-revise.md",
    )
    depth_revise_user_message = (
        f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
        f"## YOUR ORIGINAL ANALYSIS\n\n{depth_analysis}\n\n"
        f"## EVALUATOR'S CRITIQUE\n\n{breadth_eval_of_depth}\n\n"
        "Revise per the universal reviser output contract."
    )
    breadth_revise_user_message = (
        f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
        f"## YOUR ORIGINAL ANALYSIS\n\n{breadth_analysis}\n\n"
        f"## EVALUATOR'S CRITIQUE\n\n{depth_eval_of_breadth}\n\n"
        "Revise per the universal reviser output contract."
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        depth_revise_future = executor.submit(
            _call_with_supplement,
            [{"role": "system", "content": revise_system},
             {"role": "user", "content": depth_revise_user_message}],
            depth_endpoint, "reviser", 200, None, None, context_pkg,
        )
        breadth_revise_future = executor.submit(
            _call_with_supplement,
            [{"role": "system", "content": revise_system},
             {"role": "user", "content": breadth_revise_user_message}],
            breadth_endpoint, "reviser", 200, None, None, context_pkg,
        )
        try:
            revised_depth, depth_rev_ok, depth_rev_reason = depth_revise_future.result()
        except Exception as e:
            revised_depth, depth_rev_ok, depth_rev_reason = f"[Revision error: {e}]", False, str(e)
        try:
            revised_breadth, breadth_rev_ok, breadth_rev_reason = breadth_revise_future.result()
        except Exception as e:
            revised_breadth, breadth_rev_ok, breadth_rev_reason = f"[Revision error: {e}]", False, str(e)
    _record("step5-revised-depth", depth_rev_ok, depth_rev_reason)
    _record("step5-revised-breadth", breadth_rev_ok, breadth_rev_reason)

    # Contingency: if revised output is degraded, fall back to the original
    # analyst output for that stream — better to give the consolidator real
    # content than a "I don't see the prompt" stub.
    if not depth_rev_ok and depth_ok:
        revised_depth = depth_analysis
        contingencies_fired.append("step5-depth-reviser-degraded-using-analyst-output")
    if not breadth_rev_ok and breadth_ok:
        revised_breadth = breadth_analysis
        contingencies_fired.append("step5-breadth-reviser-degraded-using-analyst-output")

    # --- Step 4 + Step 5 traces ---
    _trace_step("step4-eval-of-depth", {
        "system_prompt": eval_system,
        "user_message": eval_a_user_message,
        "evaluator_target_stream": "depth",
        "evaluator_endpoint": breadth_endpoint.get("name") if isinstance(breadth_endpoint, dict) else str(breadth_endpoint),
        "raw_response_pre_contingency": raw_eval_a_response,
        "raw_response_pre_contingency_chars": len(raw_eval_a_response) if raw_eval_a_response else 0,
        "raw_response": breadth_eval_of_depth,
        "ok": eval_a_ok,
        "reason": eval_a_reason,
    }, markdown=(
        "# Step 4 — Breadth evaluates Depth\n\n"
        f"**Health:** {'ok' if eval_a_ok else 'DEGRADED'} — {eval_a_reason}\n\n"
        + (
            f"**Raw response before contingency** ({len(raw_eval_a_response)} chars):\n\n```\n{raw_eval_a_response}\n```\n\n"
            if not eval_a_ok else ""
        )
        + f"{breadth_eval_of_depth}\n"
    ))
    _trace_step("step4-eval-of-breadth", {
        "system_prompt": eval_system,
        "user_message": eval_b_user_message,
        "evaluator_target_stream": "breadth",
        "evaluator_endpoint": depth_endpoint.get("name") if isinstance(depth_endpoint, dict) else str(depth_endpoint),
        "raw_response_pre_contingency": raw_eval_b_response,
        "raw_response_pre_contingency_chars": len(raw_eval_b_response) if raw_eval_b_response else 0,
        "raw_response": depth_eval_of_breadth,
        "ok": eval_b_ok,
        "reason": eval_b_reason,
    }, markdown=(
        "# Step 4 — Depth evaluates Breadth\n\n"
        f"**Health:** {'ok' if eval_b_ok else 'DEGRADED'} — {eval_b_reason}\n\n"
        + (
            f"**Raw response before contingency** ({len(raw_eval_b_response)} chars):\n\n```\n{raw_eval_b_response}\n```\n\n"
            if not eval_b_ok else ""
        )
        + f"{depth_eval_of_breadth}\n"
    ))
    _trace_step("step5-revised-depth", {
        "system_prompt": revise_system,
        "user_message": depth_revise_user_message,
        "stream": "depth",
        "raw_response": revised_depth,
        "ok": depth_rev_ok,
        "reason": depth_rev_reason,
    }, markdown=(
        "# Step 5 — Revised Depth\n\n"
        f"**Health:** {'ok' if depth_rev_ok else 'DEGRADED'} — {depth_rev_reason}\n\n"
        f"{revised_depth}\n"
    ))
    _trace_step("step5-revised-breadth", {
        "system_prompt": revise_system,
        "user_message": breadth_revise_user_message,
        "stream": "breadth",
        "raw_response": revised_breadth,
        "ok": breadth_rev_ok,
        "reason": breadth_rev_reason,
    }, markdown=(
        "# Step 5 — Revised Breadth\n\n"
        f"**Health:** {'ok' if breadth_rev_ok else 'DEGRADED'} — {breadth_rev_reason}\n\n"
        f"{revised_breadth}\n"
    ))

    # --- Step 6: Cross-verification with up to 2 correction cycles ---
    verify_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="verifier",
        framework_name="f-verify.md",
    )

    MAX_VERIFY_CYCLES = 2
    for cycle in range(MAX_VERIFY_CYCLES + 1):
        depth_verify_error = None
        breadth_verify_error = None
        verify_depth_user_message = (
            f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
            f"## REVISED DEPTH ANALYSIS\n\n{revised_depth}\n\n"
            f"## EVALUATOR'S MANDATORY FIXES\n\n"
            f"{breadth_eval_of_depth}\n\n"
            "Run V1-V8 + mode-specific verifier checks. Conclude "
            "VERIFIED / VERIFIED WITH CORRECTIONS / VERIFICATION FAILED."
        )
        verify_breadth_user_message = (
            f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
            f"## REVISED BREADTH ANALYSIS\n\n{revised_breadth}\n\n"
            f"## EVALUATOR'S MANDATORY FIXES\n\n"
            f"{depth_eval_of_breadth}\n\n"
            "Run V1-V8 + mode-specific verifier checks. Conclude "
            "VERIFIED / VERIFIED WITH CORRECTIONS / VERIFICATION FAILED."
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            verify_depth_future = executor.submit(
                _run_model_with_tools,
                [{"role": "system", "content": verify_system},
                 {"role": "user", "content": verify_depth_user_message}],
                breadth_endpoint
            )
            verify_breadth_future = executor.submit(
                _run_model_with_tools,
                [{"role": "system", "content": verify_system},
                 {"role": "user", "content": verify_breadth_user_message}],
                depth_endpoint
            )
            try:
                depth_verdict = verify_depth_future.result()
            except Exception as e:
                # Per failure #9: substitute an explicit VERIFIER_EXCEPTION
                # marker rather than a fake "VERIFIED" string. The pipeline
                # still proceeds (we don't block on a broken verifier), but
                # the trace records the real failure shape.
                depth_verdict = f"VERIFIER_EXCEPTION: {e}"
                depth_verify_error = str(e)
            try:
                breadth_verdict = verify_breadth_future.result()
            except Exception as e:
                breadth_verdict = f"VERIFIER_EXCEPTION: {e}"
                breadth_verify_error = str(e)

        # Three-way verdict classification per cycle: PASS / FAIL / BROKEN.
        # BROKEN unblocks the cycle the same way PASS does (re-revision
        # cannot help a verifier that itself errored), but it never
        # registers as a true verification — the trace + contingencies
        # capture the broken state explicitly.
        depth_broken = _verifier_broken(depth_verdict)
        breadth_broken = _verifier_broken(breadth_verdict)
        depth_passed = _verifier_passed(depth_verdict)
        breadth_passed = _verifier_passed(breadth_verdict)
        depth_unblocks = depth_passed or depth_broken
        breadth_unblocks = breadth_passed or breadth_broken

        def _verdict_label(passed: bool, broken: bool) -> str:
            if broken:
                return "BROKEN"
            return "PASS" if passed else "FAIL"

        # --- Step 6 trace (per cycle, with three-way verdict resolution) ---
        _trace_step(f"step6-verifier-cycle-{cycle + 1}", {
            "cycle": cycle + 1,
            "max_cycles": MAX_VERIFY_CYCLES + 1,
            "verify_system_prompt_chars": len(verify_system),
            "verify_depth_user_message": verify_depth_user_message,
            "verify_breadth_user_message": verify_breadth_user_message,
            "depth_verdict_raw": depth_verdict,
            "depth_verdict_resolved": _verdict_label(depth_passed, depth_broken),
            "depth_passed_parser_verdict": depth_passed,
            "depth_broken_parser_verdict": depth_broken,
            "depth_unblocks_cycle": depth_unblocks,
            "depth_verify_exception": depth_verify_error,
            "breadth_verdict_raw": breadth_verdict,
            "breadth_verdict_resolved": _verdict_label(breadth_passed, breadth_broken),
            "breadth_passed_parser_verdict": breadth_passed,
            "breadth_broken_parser_verdict": breadth_broken,
            "breadth_unblocks_cycle": breadth_unblocks,
            "breadth_verify_exception": breadth_verify_error,
            "both_unblocked": depth_unblocks and breadth_unblocks,
            "both_passed": depth_passed and breadth_passed,
        }, markdown=(
            f"# Step 6 — Verifier (cycle {cycle + 1}/{MAX_VERIFY_CYCLES + 1})\n\n"
            f"**Depth verdict:** {_verdict_label(depth_passed, depth_broken)}"
            + (f" — exception: `{depth_verify_error}`" if depth_verify_error else "")
            + "\n\n"
            f"```\n{depth_verdict}\n```\n\n"
            f"**Breadth verdict:** {_verdict_label(breadth_passed, breadth_broken)}"
            + (f" — exception: `{breadth_verify_error}`" if breadth_verify_error else "")
            + "\n\n"
            f"```\n{breadth_verdict}\n```\n"
        ))
        # Per-stream contingency naming distinguishes BROKEN (no real
        # verification happened) from FAIL (verifier returned a real
        # negative verdict). Trend data on contingencies_fired tells the
        # team how often verification is actually being performed.
        if depth_broken:
            contingencies_fired.append(
                f"step6-cycle{cycle + 1}-depth-verifier-BROKEN-not-verified"
            )
        if breadth_broken:
            contingencies_fired.append(
                f"step6-cycle{cycle + 1}-breadth-verifier-BROKEN-not-verified"
            )

        # Loop exit: both streams unblocked (PASS or BROKEN), or cycle cap.
        # Re-revision only fires when a stream truly FAILED (broken doesn't
        # benefit from re-revision since the issue is verifier-side).
        if (depth_unblocks and breadth_unblocks) or cycle == MAX_VERIFY_CYCLES:
            break

        # Re-revision only fires on real FAIL (verifier returned a
        # substantive negative verdict). When the stream is BROKEN
        # (verifier exception, Playwright session error), re-revising
        # the analysis cannot help — the issue lives on the verifier
        # side. Skip re-revision for BROKEN streams; the existing
        # revised content carries forward to consolidation as-is.
        futures = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            if not depth_passed and not depth_broken:
                futures["depth"] = executor.submit(
                    _run_model_with_tools,
                    [{"role": "system", "content": revise_system},
                     {"role": "user", "content": (
                         f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                         f"## YOUR PREVIOUS REVISION\n\n{revised_depth}\n\n"
                         f"## VERIFIER'S FINDINGS\n\n{depth_verdict}\n\n"
                         "Address the verifier's findings and revise again."
                     )}],
                    depth_endpoint
                )
            if not breadth_passed and not breadth_broken:
                futures["breadth"] = executor.submit(
                    _run_model_with_tools,
                    [{"role": "system", "content": revise_system},
                     {"role": "user", "content": (
                         f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                         f"## YOUR PREVIOUS REVISION\n\n{revised_breadth}\n\n"
                         f"## VERIFIER'S FINDINGS\n\n{breadth_verdict}\n\n"
                         "Address the verifier's findings and revise again."
                     )}],
                    breadth_endpoint
                )
            if "depth" in futures:
                try:
                    revised_depth = futures["depth"].result()
                except Exception as e:
                    revised_depth = f"[Re-revision error: {e}]"
            if "breadth" in futures:
                try:
                    revised_breadth = futures["breadth"].result()
                except Exception as e:
                    revised_breadth = f"[Re-revision error: {e}]"

    # --- Step 7: Breadth consolidates ---
    consolidate_system = _assemble_step_prompt(
        context_pkg, slot="breadth", step="consolidator",
        framework_name="f-consolidate.md",
    )
    consolidate_user_message = (
        f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
        "## REVISED ANALYSES (internal inputs to consolidation)\n\n"
        "Two independent revised analyses follow, produced from "
        "independent analytical postures. Produce the consolidated "
        "corpus per the four operations in the loaded F-CONSOLIDATE "
        "specification: (1) semantic atom extraction, (2) cross-stream "
        "deduplication, (3) bloat strip, (4) synthesis per the mode's "
        "`## CONSOLIDATION GUIDANCE`.\n\n"
        f"---\n\n{revised_depth}\n\n---\n\n{revised_breadth}\n\n---\n\n"
        "The output is the **corpus**, not the user-facing deliverable. "
        "Step 8 (formatter) places this corpus into the prescribed "
        "deliverable form per the mode's `## OUTPUT FORMAT GUIDANCE`; "
        "your job here is substance — every atom in, no duplication, no "
        "bloat. Do NOT label or refer to the inputs as 'first analysis', "
        "'second analysis', 'analysis 1', 'analysis 2', 'depth stream', "
        "'breadth stream', or any equivalent — the corpus carries atoms, "
        "not stream-labelled positions. Do not call any tool — write the "
        "corpus inline."
    )
    consolidate_messages = [
        {"role": "system", "content": consolidate_system},
        {"role": "user", "content": consolidate_user_message},
    ]
    consolidated, consol_ok, consol_reason = _call_with_supplement(
        consolidate_messages, breadth_endpoint, "consolidator",
        min_chars=300, retry_hint=None, images=None,
        context_pkg=context_pkg,
    )
    _record("step7-consolidated", consol_ok, consol_reason)

    # Contingency: if consolidator still degraded after retry, fall back to
    # the longer of the two revised streams with a degradation header so the
    # user sees real content and knows it's not the full consolidated answer.
    if not consol_ok:
        fallback = revised_breadth if len(revised_breadth) >= len(revised_depth) else revised_depth
        consolidated = (
            "> _Note: cross-stream consolidation degraded; showing the stronger "
            "individual analysis stream._\n\n"
            + fallback
        )
        contingencies_fired.append("step7-consolidator-degraded-using-longer-revised-stream")

    _trace_step("step7-consolidated", {
        "system_prompt": consolidate_system,
        "user_message": consolidate_user_message,
        "raw_response": consolidated,
        "ok": consol_ok,
        "reason": consol_reason,
        "endpoint": breadth_endpoint.get("name") if isinstance(breadth_endpoint, dict) else str(breadth_endpoint),
    }, markdown=(
        "# Step 7 — Consolidated corpus\n\n"
        f"**Health:** {'ok' if consol_ok else 'DEGRADED'} — {consol_reason}\n\n"
        f"{consolidated}\n"
    ))

    # Strip any preamble before the first heading. The F-Consolidate spec
    # tells the model to lead with an H2 heading. If the model still emits
    # preamble ("Good—", "Let me integrate this", "Here is the analysis…"),
    # we discard everything before the first markdown heading.
    consolidated = _strip_consolidator_preamble(consolidated)

    # --- Step 8: Format. Place the step-7 consolidated corpus into the
    # mode's prescribed deliverable form per the mode's
    # `## OUTPUT FORMAT GUIDANCE`. The corpus is already semantically
    # extracted, cross-stream deduplicated, bloat-stripped, and synthesized
    # at step 7; the formatter places, does not summarise. Universal
    # scaffolding in f-format.md; per-mode placement spec in
    # `## OUTPUT FORMAT GUIDANCE` (empty during Phase 2b migration —
    # formatter defaults to flowing prose).
    format_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="formatter",
        framework_name="f-format.md",
    )
    format_user_message = (
        f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
        f"## CONSOLIDATED CORPUS\n\n{consolidated}\n\n"
        "Place the corpus into the prescribed deliverable form per the "
        "mode's `## OUTPUT FORMAT GUIDANCE` (loaded above in the system "
        "prompt). When the mode's format guidance is absent, default to "
        "flowing prose addressed to the user with H2 headings derived "
        "from the corpus's organizational structure. Preserve every "
        "atom — the formatter places, does not summarise. Surface any "
        "corpus material that does not fit a prescribed section as a "
        "labelled postscript rather than dropping it. Do not call any "
        "tool — write the deliverable inline."
    )
    format_messages = [
        {"role": "system", "content": format_system},
        {"role": "user", "content": format_user_message},
    ]
    formatted, format_ok, format_reason = _call_with_retry(
        format_messages, depth_endpoint, "formatter",
        min_chars=300, retry_hint=None, images=None,
    )
    _record("step8-formatted", format_ok, format_reason)

    # Contingency: if the formatter is still degraded after retry, fall
    # back to the step-7 consolidated corpus directly with a degradation
    # header. The corpus is itself substantive content; the user sees
    # real material even when form-placement fails.
    if not format_ok:
        formatted = (
            "> _Note: format step degraded; showing the consolidated "
            "corpus directly. Form-placement was not applied._\n\n"
            + consolidated
        )
        contingencies_fired.append("step8-formatter-degraded-using-consolidated-corpus")

    _trace_step("step8-formatted", {
        "system_prompt": format_system,
        "user_message": format_user_message,
        "raw_response": formatted,
        "ok": format_ok,
        "reason": format_reason,
        "endpoint": depth_endpoint.get("name") if isinstance(depth_endpoint, dict) else str(depth_endpoint),
    }, markdown=(
        "# Step 8 — Formatted deliverable\n\n"
        f"**Health:** {'ok' if format_ok else 'DEGRADED'} — {format_reason}\n\n"
        f"{formatted}\n"
    ))

    # Per-turn step-health summary — captures every step's verdict plus
    # the contingency paths that fired. Lives at ``step-health.json`` in
    # the per-turn trace directory.
    if PIPELINE_TRACE_AVAILABLE and trace_dir:
        pipeline_trace.write_step_health(
            trace_dir, step_health, gear=4,
            contingencies_fired=contingencies_fired,
        )

    # Final pollution sweep before handing back to the user-facing layer.
    formatted = _strip_dispatch_noise(formatted)

    # Emit step-health summary to stdout for observability. The chat handler
    # surfaces it as a developer log; oversight wires it into the event bus
    # if running with --oversight.
    try:
        degraded = [k for k, (ok, _) in step_health.items() if not ok]
        if degraded:
            print(f"[gear4-summary] degraded steps: {degraded}", flush=True)
        else:
            print("[gear4-summary] all steps healthy", flush=True)
    except Exception:
        pass

    return formatted


def call_model(messages: list, endpoint: dict, images: list = None) -> str:
    """Route to appropriate endpoint type.

    images: optional list of {"name": str, "mime": str, "base64": str}
    """
    etype = endpoint.get("type", "")

    if etype == "api":
        return call_api_endpoint(messages, endpoint, images=images)
    elif etype == "local":
        return call_local_endpoint(messages, endpoint, images=images)
    elif etype == "browser":
        return call_browser_endpoint(messages, endpoint, images=images)
    else:
        return f"[Error] Unknown endpoint type: {etype}"


def _inject_images_into_messages(messages: list, images: list, api_format: str = "claude") -> list:
    """Inject image attachments into the last user message for vision APIs.

    api_format: "claude" or "openai" — determines the image content block structure.
    Returns a new messages list with the last user message augmented.
    """
    if not images:
        return messages

    messages = [dict(m) for m in messages]  # shallow copy
    # Find last user message
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
            text = messages[i]["content"]
            content_blocks = []
            for img in images:
                if api_format == "claude":
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img["mime"],
                            "data": img["base64"],
                        }
                    })
                elif api_format == "openai":
                    data_url = f"data:{img['mime']};base64,{img['base64']}"
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    })
            content_blocks.append({"type": "text", "text": text})
            messages[i]["content"] = content_blocks
            break
    return messages


def call_api_endpoint(messages: list, endpoint: dict, images: list = None) -> str:
    service = endpoint.get("service", "")
    model = endpoint.get("model", "")

    if service == "claude":
        try:
            import anthropic
            key = endpoint.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                import keyring
                key = keyring.get_password("ora", "anthropic-api-key") or ""
            client = anthropic.Anthropic(api_key=key)
            # Separate system from messages
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            conv = [m for m in messages if m["role"] != "system"]
            if images:
                conv = _inject_images_into_messages(conv, images, api_format="claude")
            resp = client.messages.create(
                model=model or "claude-opus-4-6",
                max_tokens=4096,
                system=system_msg,
                messages=conv
            )
            return resp.content[0].text
        except Exception as e:
            return f"[Error calling Claude API: {e}]"

    elif service == "openai":
        try:
            from openai import OpenAI
            key = endpoint.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
            if not key:
                import keyring
                key = keyring.get_password("ora", "openai-api-key") or ""
            client = OpenAI(api_key=key)
            api_messages = messages
            if images:
                api_messages = _inject_images_into_messages(messages, images, api_format="openai")
            resp = client.chat.completions.create(
                model=model or "gpt-4o",
                messages=api_messages,
                max_tokens=4096
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[Error calling OpenAI API: {e}]"

    elif service == "gemini":
        try:
            from google import genai
            key = endpoint.get("api_key") or os.environ.get("GEMINI_API_KEY", "")
            if not key:
                import keyring
                key = keyring.get_password("ora", "gemini-api-key") or ""
            if not key:
                return "[Error calling Gemini API: No API key found. Store via: keyring set ora gemini-api-key]"
            client = genai.Client(api_key=key)
            # Extract system instruction
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
            # Build contents from non-system messages
            contents = []
            for m in messages:
                if m["role"] == "system":
                    continue
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
            config = {}
            if system_msg:
                config["system_instruction"] = system_msg
            resp = client.models.generate_content(
                model=model or "models/gemini-2.5-flash",
                contents=contents,
                config=config,
            )
            return resp.text
        except Exception as e:
            return f"[Error calling Gemini API: {e}]"

    elif service == "openrouter":
        # OpenRouter exposes most frontier and open-weight models behind
        # one OpenAI-compatible API. Pipeline endpoints use this when the
        # bucket entry is a "<vendor>/<model>" id (e.g. "anthropic/claude-opus-4-7",
        # "xiaomi/mimo-v2-pro"). The dispatch is identical to the openai
        # branch above except for base_url and the auth key source.
        try:
            from openai import OpenAI
            key = (
                endpoint.get("api_key")
                or os.environ.get("OPENROUTER_API_KEY", "")
            )
            if not key:
                import keyring
                key = keyring.get_password("ora", "openrouter-api-key") or ""
            if not key:
                return (
                    "[Error calling OpenRouter API: No API key found. "
                    "Store via: keyring set ora openrouter-api-key]"
                )
            client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")
            api_messages = messages
            if images:
                api_messages = _inject_images_into_messages(
                    messages, images, api_format="openai"
                )
            resp = client.chat.completions.create(
                model=model or "openai/gpt-4o-mini",
                messages=api_messages,
                max_tokens=4096,
                extra_headers={
                    # OpenRouter recommends these for attribution in
                    # their leaderboards / billing breakdowns. Not auth-related.
                    "HTTP-Referer": "https://ora.local",
                    "X-Title": "Ora",
                },
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[Error calling OpenRouter API: {e}]"

    return f"[Error] Unsupported API service: {service}"


# MLX model cache — avoid reloading 40GB+ from disk on every call
_mlx_cache: dict = {}  # {model_path: (model_obj, tokenizer)}


def call_local_endpoint(messages: list, endpoint: dict, images: list = None) -> str:
    url = endpoint.get("url", "http://localhost:11434")
    engine = endpoint.get("engine", "ollama")
    model = endpoint.get("model", "")

    # Resolve "auto" engine at runtime based on platform
    if engine == "auto":
        import platform as _plat
        if _plat.system() == "Darwin" and _plat.machine() == "arm64":
            engine = "mlx"
        else:
            engine = "ollama"

    if engine == "ollama":
        try:
            import urllib.request
            ollama_messages = list(messages)
            if images:
                # Ollama supports images via "images" field on the user message
                for i in range(len(ollama_messages) - 1, -1, -1):
                    if ollama_messages[i]["role"] == "user":
                        ollama_messages[i] = dict(ollama_messages[i])
                        ollama_messages[i]["images"] = [img["base64"] for img in images]
                        break
            payload = json.dumps({"model": model, "messages": ollama_messages, "stream": False}).encode()
            req = urllib.request.Request(
                f"{url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "[No response]")
        except Exception as e:
            return f"[Error calling local model: {e}]"
    
    elif engine == "mlx":
        try:
            from mlx_lm import load, generate as mlx_generate
            if model in _mlx_cache:
                model_obj, tokenizer = _mlx_cache[model]
            else:
                model_obj, tokenizer = load(model)
                _mlx_cache[model] = (model_obj, tokenizer)
            # Use chat template if available, otherwise build manually
            if hasattr(tokenizer, "apply_chat_template"):
                conv = [m for m in messages if m["role"] != "system"]
                system = next((m["content"] for m in messages if m["role"] == "system"), None)
                if system:
                    conv = [{"role": "system", "content": system}] + conv
                prompt = tokenizer.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
            else:
                parts = []
                for m in messages:
                    if m["role"] == "system":    parts.append(f"<|system|>\n{m['content']}")
                    elif m["role"] == "user":    parts.append(f"<|user|>\n{m['content']}")
                    elif m["role"] == "assistant": parts.append(f"<|assistant|>\n{m['content']}")
                parts.append("<|assistant|>")
                prompt = "\n".join(parts)
            gen_tokens = endpoint.get("max_tokens", 4096)
            raw = mlx_generate(model_obj, tokenizer, prompt=prompt, max_tokens=gen_tokens, verbose=False)
            return _extract_final_response(raw)
        except FileNotFoundError:
            return f"[MLX model not found: '{model}' — check the model path in endpoints.json]"
        except Exception as e:
            return f"[Error calling MLX model '{model}': {e}]"
    
    return f"[Error] Unsupported engine: {engine}"


def call_browser_endpoint(messages: list, endpoint: dict, images: list = None) -> str:
    """Dispatch a chat-completion to a browser-driven service (claude.ai etc.).

    Browser chat UIs have a single input box — no separate "system" slot —
    so we must serialise system + user into one prompt. Previously this
    function took only the last user message and discarded the system
    message entirely. That meant every Gear-4 step prompt that referenced
    its scaffolding ("follow the universal seven-section contract",
    "apply the V1-V8 verifier checks") sent the *reference* but never
    the *referenced material* — the system prompt's f-evaluate.md /
    f-revise.md / f-verify.md / f-consolidate.md content, the mode-
    specific cascade subsections, the RAG context, and the inline-dispatch
    directive all vanished.

    Fix: concatenate the system message and the last user message with a
    visible separator, so the browser-side model sees the full instruction
    payload it was supposed to receive. Multi-turn ``history`` messages
    are dropped here — Gear-4 step calls are always single-shot
    (system + one user message), so this is safe; downstream code that
    sends multi-turn through this path would surface the gap quickly.
    """
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    if system_msg and last_user:
        combined = (
            f"{system_msg}\n\n"
            f"---\n\n"
            f"# USER REQUEST\n\n"
            f"{last_user}"
        )
    elif system_msg:
        combined = system_msg
    else:
        combined = last_user

    if images:
        # Browser endpoints are text-only — note attached images
        img_note = ", ".join(img["name"] for img in images)
        combined = f"[User attached {len(images)} image(s): {img_note}]\n\n{combined}"
    service = endpoint.get("service", "claude")
    if TOOLS_AVAILABLE:
        return browser_evaluate(service, combined)
    return "[Error] browser_evaluate tool not available"


def parse_tool_calls(text: str) -> list[dict]:
    """Extract all <tool_call> blocks from model output.

    When the params JSON fails to parse, falls back to a sentinel-shaped
    dict ``{"raw": "<verbatim params>", "_parse_error": "<error>"}`` and
    prints a stderr warning. The downstream tool will almost certainly
    error on the wrong-shape params; without the warning that error
    looked like a tool failure rather than what it actually is — a
    malformed tool-call emission by the model.
    """
    pattern = r'<tool_call>\s*<n>(.*?)</n>\s*<parameters>(.*?)</parameters>\s*</tool_call>'
    matches = re.findall(pattern, text, re.DOTALL)
    calls = []
    for name, params_str in matches:
        try:
            params = json.loads(params_str.strip())
        except json.JSONDecodeError as e:
            print(
                f"[parse_tool_calls] malformed JSON params for tool "
                f"{name.strip()!r}: {e}; raw params: "
                f"{params_str.strip()[:200]!r}",
                file=sys.stderr,
                flush=True,
            )
            params = {
                "raw": params_str.strip(),
                "_parse_error": str(e),
            }
        calls.append({"name": name.strip(), "parameters": params})
    return calls


def _code_execute(code: str, timeout: int = 30) -> str:
    """Sandboxed Python execution (no network)."""
    if not code.strip():
        return "[code_execute] No code provided."
    import subprocess, sys
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "no_proxy": "*", "http_proxy": "", "https_proxy": ""},
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if err:
            return f"{out}\n[stderr] {err}".strip()
        return out or "[code_execute] (no output)"
    except subprocess.TimeoutExpired:
        return f"[code_execute] Timeout after {timeout}s"
    except Exception as e:
        return f"[code_execute] {e}"


def _continuity_save(session_summary: str) -> str:
    """Write a session continuity file to ~/Documents/conversations/."""
    if not session_summary.strip():
        return "[continuity_save] No summary provided."
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.expanduser(f"~/Documents/conversations/continuity_{ts}.md")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(f"# Session Continuity — {ts}\n\n{session_summary}\n")
        return f"[continuity_save] Saved to {path}"
    except Exception as e:
        return f"[continuity_save] {e}"


def _queue_read() -> str:
    """Read the next task from config/task-queue.md."""
    queue_path = os.path.join(WORKSPACE, "config/task-queue.md")
    if not os.path.exists(queue_path):
        return "[queue_read] No task queue found at config/task-queue.md"
    try:
        with open(queue_path) as f:
            content = f.read()
        # Return the first non-empty, non-header line that looks like a task
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- [ ]"):
                return line
        return "[queue_read] No pending tasks in queue."
    except Exception as e:
        return f"[queue_read] {e}"


_TOOL_ERROR_MARKERS = (
    "[tool error —",
    "[tools unavailable",
    "[code_execute] timeout",
    "[code_execute] (no output)",
    "[continuity_save] [error",
    "[queue_read] no task queue found",
    "[queue_read] no pending tasks",
    # Generic dispatcher error idioms returned as content
    "permission denied",
    "no such file or directory",
)


def classify_tool_outcome(name: str, result: str) -> tuple[str, str]:
    """Classify a tool's string result as 'ok' / 'error' / 'empty'.

    Tools historically returned bare strings — the model could not tell
    success from failure beyond reading the content. The agentic loops
    use this classifier to inject a structured marker like
    "[Tool: name | outcome: error | reason: ...]" so the model treats
    failures as failures rather than as legitimate tool output.

    Returns (outcome, reason). Reason is a short diagnostic.
    """
    if result is None:
        return ("error", "null result")
    txt = result.strip()
    if not txt:
        return ("empty", "tool returned empty string")
    lower = txt.lower()
    # Legacy inline tools sometimes wrap normal output in brackets — the
    # parameters dict's `_parse_error` flag (set by parse_tool_calls when
    # the params JSON was malformed) is the clearest signal of an upstream
    # failure that the tool can't recover from.
    if any(m in lower for m in _TOOL_ERROR_MARKERS):
        return ("error", f"matched tool-error marker in result")
    # Heuristic: a very short result that doesn't look like data is
    # suspect. Don't over-classify; tools legitimately return short
    # acknowledgements.
    if len(txt) < 5:
        return ("empty", f"very short result ({len(txt)} chars)")
    return ("ok", "")


def execute_tool(name: str, params: dict) -> str:
    """Dispatch tool call through unified dispatcher.

    Legacy tools (code_execute, continuity_save, queue_read) are handled
    directly; all others route through dispatcher.py for permission gating,
    path validation, command classification, and audit logging.

    Callers wanting a structured outcome should use ``execute_tool_with_outcome``
    (added 2026-05-15 sweep 4). This signature is preserved for backwards
    compatibility with existing call sites.
    """
    if not TOOLS_AVAILABLE:
        return "[Tools unavailable — import failed at startup]"

    # If the tool was dispatched with malformed params (parse_tool_calls
    # set _parse_error), surface that upfront so the model doesn't try to
    # interpret a failed-to-parse params dict as legitimate output.
    if isinstance(params, dict) and params.get("_parse_error"):
        return (
            f"[Tool error — {name}: tool-call params failed to parse "
            f"as JSON ({params['_parse_error']}); raw: "
            f"{(params.get('raw') or '')[:200]!r}]"
        )

    # Legacy inline tools not in the dispatcher registry
    if name == "code_execute":
        return _code_execute(params.get("code", ""), params.get("timeout", 30))
    elif name == "continuity_save":
        return _continuity_save(params.get("session_summary", ""))
    elif name == "queue_read":
        return _queue_read()

    # Route everything else through the dispatcher
    try:
        return dispatcher_dispatch(name, params)
    except Exception as e:
        return f"[Tool error — {name}: {e}]"


def execute_tool_with_outcome(name: str, params: dict) -> tuple[str, str, str]:
    """Wrapper around execute_tool that returns ``(result, outcome, reason)``.

    Agentic loops should prefer this over the bare ``execute_tool`` so
    the structured outcome can be injected as a clear marker into the
    model's tool-result message. Without this, tool errors and tool
    successes look identical in the message stream.
    """
    result = execute_tool(name, params)
    outcome, reason = classify_tool_outcome(name, result)
    return (result, outcome, reason)


def strip_tool_calls(text: str) -> str:
    """Remove tool call XML from text for display."""
    pattern = r'<tool_call>.*?</tool_call>'
    return re.sub(pattern, '', text, flags=re.DOTALL).strip()


def run_agentic_loop(user_input: str, history: list = None,
                     use_pipeline: bool = True,
                     output_target: str = "screen") -> str:
    """Main entry point: routes through the full pipeline or direct model call.

    Args:
        user_input: Raw user prompt
        history: Conversation history (list of message dicts)
        use_pipeline: If True, run Step 1 + Step 2 + gear-appropriate execution.
                      If False, bypass pipeline (legacy single-model mode).
        output_target: "screen", "file:/path", or "both:/path"
    """
    if use_pipeline:
        return run_pipeline(user_input, history, output_target)

    # Legacy direct mode — bypass pipeline
    config = load_endpoints()
    endpoint = get_active_endpoint(config)

    messages = history or []
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": load_boot_md()})
    messages.append({"role": "user", "content": user_input})

    if endpoint is None:
        return ("[No AI endpoints configured. Add a commercial AI connection or "
                "install a local model.\n"
                "To add a connection, run the Browser Evaluation Setup Framework.")

    return _run_model_with_tools(messages, endpoint)


def parse_user_command(user_input: str) -> tuple:
    """Parse user input for commands and output directives.

    Supported commands:
      /direct — bypass pipeline, use legacy single-model mode
      /gear N — override gear for this query
      /save path — write output to file instead of screen
      /saveboth path — write output to file AND display
    """
    use_pipeline = True
    output_target = "screen"
    clean_input = user_input

    if clean_input.startswith("/direct "):
        use_pipeline = False
        clean_input = clean_input[8:]
    elif clean_input.startswith("/save "):
        parts = clean_input.split(" ", 2)
        if len(parts) >= 3:
            output_target = f"file:{parts[1]}"
            clean_input = parts[2]
    elif clean_input.startswith("/saveboth "):
        parts = clean_input.split(" ", 2)
        if len(parts) >= 3:
            output_target = f"both:{parts[1]}"
            clean_input = parts[2]

    return clean_input, use_pipeline, output_target


def main():
    """Interactive terminal interface."""
    print("Local AI — Terminal Interface (Pipeline Enabled)")
    print("Type your message and press Enter. Ctrl+C to exit.")
    print("Commands: /direct (bypass pipeline), /save <path> (file output),")
    print("          /saveboth <path> (file + screen)")
    print()

    # Platform check — validate engine matches this machine
    try:
        from platform_check import startup_check
        for msg in startup_check():
            print(msg)
    except ImportError:
        pass

    config = load_endpoints()
    endpoint = get_active_endpoint(config)
    if endpoint:
        print(f"Active endpoint: {endpoint.get('name', 'unknown')}")
    else:
        print("WARNING: No active endpoints configured.")
    print()

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Goodbye.")
                break

            clean_input, use_pipeline, output_target = parse_user_command(user_input)

            response = run_agentic_loop(
                clean_input, history,
                use_pipeline=use_pipeline,
                output_target=output_target
            )
            print(f"\nAI: {response}\n")

            # Update history
            history.append({"role": "user", "content": clean_input})
            history.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"[Error: {e}]")


if __name__ == "__main__":
    main()
