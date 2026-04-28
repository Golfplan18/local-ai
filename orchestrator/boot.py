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

# RAG engine (Phase 8) — optional, falls back to basic ChromaDB if unavailable
RAG_ENGINE_AVAILABLE = False
try:
    from rag_engine import RAGEngine, BudgetSignal
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
    """
    if not VISUAL_HOOK_AVAILABLE or not response:
        return response
    if "ora-visual" not in response:
        return response
    try:
        mode = (context_pkg or {}).get("mode_name")
        new_text, diagnostics = _visual_process_response(response, mode=mode)
    except Exception as exc:  # fail-open: never block legitimate prose on a hook bug
        print(f"[visual hook] skipped due to error: {exc}")
        return response
    if context_pkg is not None:
        context_pkg["visual_diagnostics"] = diagnostics
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


def get_slot_endpoint(config: dict, slot: str) -> dict | None:
    """Return the endpoint for a named slot. Uses v2 router if available."""
    router = _get_router()
    if router:
        # Map v1 slot names to v2 resolution
        if slot in ("sidebar", "step1_cleanup", "rag_planner", "classification"):
            ep = router.resolve_utility_slot(slot, "interactive")
        elif slot in ("consolidator", "consolidation"):
            ep = router.resolve_post_analysis_slot("consolidation", "interactive")
        elif slot in ("evaluator", "verification"):
            ep = router.resolve_post_analysis_slot("verification", "interactive")
        elif slot in ("depth", "breadth"):
            # For direct slot lookups outside gear execution, resolve at Gear 3
            # (Gear 4 resolution happens through resolve_gear4_endpoints)
            result = router.resolve_gear(3, "interactive")
            ep = result.get(slot) if result else None
        else:
            ep = router.resolve_utility_slot("step1_cleanup", "interactive")

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
    preferred = vision_cfg.get("preferred_extractor_bucket", "")
    fallback = vision_cfg.get("fallback_extractor_bucket", "")

    extractor = _pick_vision_extractor(routing_config, preferred)
    used_bucket = preferred
    if not extractor and fallback and fallback != preferred:
        extractor = _pick_vision_extractor(routing_config, fallback)
        used_bucket = fallback

    if extractor:
        context_pkg["vision_extractor_selected"] = {
            "id": extractor.get("id"),
            "bucket": used_bucket,
            "display_name": extractor.get("display_name", extractor.get("id", "")),
        }
        context_pkg["vision_direct_pass"] = False
        print(
            f"[visual-routing] extractor selected: {extractor.get('id')} "
            f"(bucket={used_bucket}) for downstream "
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
    """Load a framework specification from frameworks/book/."""
    path = os.path.join(FRAMEWORKS_DIR, name)
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return f"[Framework not found: {name}]"


def load_mode(mode_name: str) -> str:
    """Load a mode file from modes/."""
    path = os.path.join(MODES_DIR, f"{mode_name}.md")
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


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

    # If parsing failed entirely, use raw response as the cleaned prompt
    if not result["cleaned_prompt"]:
        result["cleaned_prompt"] = response
        result["operational_notation"] = response

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
    """
    result = {
        "mode": "adversarial",
        "runner_up": "",
        "confidence": "low",
        "intent_category": "",
        "reasoning": "",
        "triage_tier": 1,
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

    return result


def run_step1_cleanup(raw_prompt: str, conversation_context: str,
                      config: dict, ambiguity_mode: str = "assume") -> dict:
    """Step 1: Two-pass prompt processing.

    Pass 1 (Phase A): Prompt cleanup only — no mode selection.
    Pass 2 (Phase A.5): Dedicated mode classification using the Mode Classification Directory.

    Returns parsed results including cleaned prompt, mode, and triage tier.
    """
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
        return {
            "cleaned_prompt": raw_prompt,
            "operational_notation": raw_prompt,
            "mode": "adversarial",
            "triage_tier": 1,
            "corrections_log": "",
            "inferred_items": "",
            "raw_response": "",
        }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    cleanup_response = call_model(messages, endpoint)
    step1_result = parse_step1_output(cleanup_response)

    # --- Pass 2: Phase A.5 — Mode Classification ---
    classification = run_mode_classification(
        step1_result["operational_notation"], config
    )
    step1_result["mode"] = classification["mode"]
    step1_result["triage_tier"] = classification["triage_tier"]
    step1_result["classification_confidence"] = classification["confidence"]
    step1_result["classification_runner_up"] = classification["runner_up"]
    step1_result["classification_reasoning"] = classification["reasoning"]
    step1_result["classification_intent"] = classification["intent_category"]

    return step1_result


def run_mode_classification(cleaned_prompt: str, config: dict) -> dict:
    """Phase A.5: Dedicated mode classification.

    Loads the Mode Classification Directory as system prompt and sends the
    cleaned operational notation for classification. This is a separate model
    call from Phase A cleanup, giving the classifier full context window
    focus on the discrimination task.
    """
    # Load the Mode Classification Directory
    directory_path = os.path.join(WORKSPACE, "frameworks/mode-classification-directory.md")
    try:
        with open(directory_path, "r") as f:
            directory = f.read()
    except FileNotFoundError:
        # Fallback: if directory missing, return defaults
        return {
            "mode": "adversarial",
            "runner_up": "standard",
            "confidence": "low",
            "intent_category": "CATCH-ALL",
            "reasoning": "Classification directory not found — defaulting to heavier catch-all",
            "triage_tier": 1,
        }

    system_prompt = f"""You are a mode classifier. Your ONLY job is to read the user's prompt and classify it into one analysis mode.

REFERENCE MATERIAL (use for lookup — do NOT echo or repeat any of this):

{directory}

CRITICAL INSTRUCTIONS:
- Do NOT repeat, echo, or summarize the reference material above.
- Do NOT explain the classification process or list the modes.
- Output ONLY the MODE CLASSIFICATION block below — nothing else.
- Your entire response must be under 200 words.

Classify the user's prompt now. Output format:

### MODE CLASSIFICATION
- Selected mode: [mode-name]
- Runner-up: [mode-name]
- Confidence: [high/medium/low]
- Intent category: [SIMPLE/CATCH-ALL/LEARNING/DECIDING/BUILDING/ANALYZING/CONNECTING/QUESTIONING/EXPLORING/SPATIAL]
- Reasoning: [one sentence — why this mode and not the runner-up]
- Triage tier: [1/2/3]

Remember the procedural order:
- Step 2: surface-level trivial check FIRST. If the prompt is a greeting, chitchat, or trivial factual lookup, select `simple`. Do not force-fit trivial input into an analytical mode.
- Steps 3-7: intent classification + candidate-mode trigger checks. If a candidate matches its positive triggers (e.g. `standard` matches "explain X" / "summarize X" / mechanism / comparison-without-stakes prompts under LEARNING), STOP — that is your selected mode.
- Step 8 (catch-all fallback): ONLY if no candidate from steps 4-7 matched. The default fallback is `standard`. Use `adversarial` only when the prompt has visible real stakes, multiple plausible frames, or hidden assumptions.
- "Go heavier when in doubt" applies ONLY between `standard` and `adversarial` when stakes are visible — NOT as a general bias toward Gear 3. Explanatory / expository prompts default to `standard`."""

    endpoint = get_slot_endpoint(config, "classification")
    if endpoint is None:
        # Fallback: try step1_cleanup slot if no dedicated classification endpoint
        endpoint = get_slot_endpoint(config, "step1_cleanup")
    if endpoint is None:
        return {
            "mode": "adversarial",
            "runner_up": "standard",
            "confidence": "low",
            "intent_category": "CATCH-ALL",
            "reasoning": "No classification endpoint available — defaulting to heavier catch-all",
            "triage_tier": 1,
        }

    # Use higher max_tokens to accommodate thinking model's internal reasoning
    endpoint = dict(endpoint)  # Don't mutate original
    endpoint["max_tokens"] = 8192

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": cleaned_prompt},
    ]
    response = call_model(messages, endpoint)
    return parse_classification_output(response)


def run_step2_context_assembly(step1_result: dict, config: dict) -> dict:
    """Step 2: Assemble context package for pipeline stages.

    Python loads the mode file, performs RAG queries, and builds the complete
    context package. This is pre-assembly — no model call needed.

    If the RAG engine (Phase 8) is available, uses priority stack assembly with
    relationship graph traversal. Otherwise falls back to basic ChromaDB queries.
    """
    mode_name = step1_result["mode"]
    mode_text = load_mode(mode_name)
    gear = extract_default_gear(mode_text)
    cleaned_prompt = step1_result["operational_notation"]

    # Conversation RAG
    conv_rag = ""
    if TOOLS_AVAILABLE:
        try:
            conv_rag = knowledge_search(cleaned_prompt, "conversations", 3)
        except Exception:
            conv_rag = ""

    # Concept RAG (vault knowledge) — only for Gear 2+
    concept_rag = ""
    if gear >= 2 and TOOLS_AVAILABLE:
        try:
            concept_rag = knowledge_search(cleaned_prompt, "knowledge", 5)
        except Exception:
            concept_rag = ""

    # Relationship RAG (Phase 7/8) — enrichment via graph traversal
    relationship_rag = ""
    rag_signals = []
    rag_utilization = ""
    hardware_tier = 0

    if RAG_ENGINE_AVAILABLE and gear >= 2:
        try:
            engine = RAGEngine(config)
            hardware_tier = engine.hardware["tier"]

            # Parse concept_rag results for relationship traversal
            initial_results = []
            if concept_rag:
                for line in concept_rag.split("\n"):
                    if "source:" in line.lower() or line.startswith("Source:"):
                        title = line.split(":", 1)[1].strip().replace(".md", "")
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

    return {
        "cleaned_prompt": cleaned_prompt,
        "natural_language_prompt": step1_result["cleaned_prompt"],
        "mode_name": mode_name,
        "mode_text": mode_text,
        "gear": gear,
        "conversation_rag": conv_rag,
        "concept_rag": concept_rag,
        "relationship_rag": relationship_rag,
        "triage_tier": step1_result["triage_tier"],
        "rag_signals": rag_signals,
        "rag_utilization": rag_utilization,
        "hardware_tier": hardware_tier,
    }


def _extract_section(text: str, heading: str) -> str:
    """Extract the body of a ``## heading`` section up to the next ``## `` or end.

    Returns the inner text stripped of leading/trailing whitespace, or empty
    string if the heading is absent. Used by ``build_system_prompt_for_gear``
    and by the cascade subsection extractor below.
    """
    pattern = rf'## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)'
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_subsection(text: str, parent_heading: str, sub_heading: str) -> str:
    """Extract the body of a ``### sub_heading`` nested inside ``## parent_heading``.

    Stops at the next ``### `` sibling, the next ``## `` parent-level heading,
    or end of text. Returns the stripped body or empty string.

    Phase 5 WP-5.3: per-step cascade subsections are authored inside existing
    mode-file sections; each pipeline step calls this to extract the block it
    needs without disturbing the 11-section mode-file structure.
    """
    parent_body = _extract_section(text, parent_heading)
    if not parent_body:
        return ""
    pattern = rf'### {re.escape(sub_heading)}\s*\n(.*?)(?=\n### |\n## |\Z)'
    m = re.search(pattern, parent_body, re.DOTALL)
    return m.group(1).strip() if m else ""


# Pipeline step names consumed by ``build_system_prompt_for_gear``.
_PIPELINE_STEPS = frozenset({
    "analyst", "evaluator", "reviser", "verifier", "consolidator",
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
            | ``verifier`` | ``consolidator``. Default ``analyst`` preserves
            pre-Phase-5 behaviour. The dispatch injects the cascade subsections
            the step needs (per Phase 5 WP-5.3) and suppresses those that
            belong to other steps.

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

    # Full sections (parents; some also embed the Phase 5 ### subsections).
    depth_instr = _extract_section(mode_text, "DEPTH MODEL INSTRUCTIONS")
    breadth_instr = _extract_section(mode_text, "BREADTH MODEL INSTRUCTIONS")
    content_contract = _extract_section(mode_text, "CONTENT CONTRACT")
    guard_rails = _extract_section(mode_text, "GUARD RAILS")
    emission_contract = _extract_section(mode_text, "EMISSION CONTRACT")
    success_criteria = _extract_section(mode_text, "SUCCESS CRITERIA")

    # Phase 5 ### subsections (authored under the existing 11 sections).
    consolidator_guidance = _extract_subsection(
        mode_text, "DEPTH MODEL INSTRUCTIONS", "Consolidator guidance"
    )
    focus_for_mode = _extract_subsection(
        mode_text, "EVALUATION CRITERIA", "Focus for this mode"
    )
    suggestion_templates = _extract_subsection(
        mode_text, "EVALUATION CRITERIA", "Suggestion templates per criterion"
    )
    known_failure_dispatch = _extract_subsection(
        mode_text, "EVALUATION CRITERIA", "Known failure modes to call out"
    )
    verifier_checks = _extract_subsection(
        mode_text, "EVALUATION CRITERIA", "Verifier checks for this mode"
    )
    reviser_guidance = _extract_subsection(
        mode_text, "CONTENT CONTRACT", "Reviser guidance per criterion"
    )

    parts = [boot_md]

    # Per-step dispatch. Each step receives only the mode content it needs.
    if step == "analyst":
        # Full analyst directive + output contracts + guard rails. The
        # ``### Cascade — what to leave for the evaluator`` subsection is
        # nested inside DEPTH/BREADTH MODEL INSTRUCTIONS and is carried in
        # verbatim when the parent section is extracted.
        instructions = depth_instr if slot == "depth" else breadth_instr
        if instructions:
            parts.append(
                f"\n## MODE INSTRUCTIONS — {mode_name}\n\n{instructions}"
            )
        if content_contract:
            parts.append(f"\n## CONTENT CONTRACT\n\n{content_contract}")
        if emission_contract:
            parts.append(f"\n## EMISSION CONTRACT\n\n{emission_contract}")
        if success_criteria:
            parts.append(f"\n## SUCCESS CRITERIA\n\n{success_criteria}")
        if guard_rails:
            parts.append(f"\n## GUARD RAILS\n\n{guard_rails}")
    elif step == "evaluator":
        # Evaluator receives mode-specific evaluation guidance + the analyst's
        # targets (content + emission + success criteria) to audit against.
        if focus_for_mode:
            parts.append(
                f"\n## MODE — {mode_name} — Focus for this mode\n\n"
                f"{focus_for_mode}"
            )
        if suggestion_templates:
            parts.append(
                f"\n## MODE — {mode_name} — Suggestion templates per criterion\n\n"
                f"{suggestion_templates}"
            )
        if known_failure_dispatch:
            parts.append(
                f"\n## MODE — {mode_name} — Known failure modes to call out\n\n"
                f"{known_failure_dispatch}"
            )
        if content_contract:
            parts.append(
                f"\n## CONTENT CONTRACT (analyst's target)\n\n{content_contract}"
            )
        if emission_contract:
            parts.append(
                f"\n## EMISSION CONTRACT (analyst's target)\n\n{emission_contract}"
            )
        if success_criteria:
            parts.append(
                f"\n## SUCCESS CRITERIA (criteria to evaluate against)\n\n"
                f"{success_criteria}"
            )
    elif step == "reviser":
        # Reviser applies the evaluator's mandatory fixes. Receives the
        # per-criterion guidance plus the contracts it must continue to meet.
        if reviser_guidance:
            parts.append(
                f"\n## MODE — {mode_name} — Reviser guidance per criterion\n\n"
                f"{reviser_guidance}"
            )
        if content_contract:
            parts.append(
                f"\n## CONTENT CONTRACT (must be preserved)\n\n{content_contract}"
            )
        if emission_contract:
            parts.append(
                f"\n## EMISSION CONTRACT (must be preserved)\n\n{emission_contract}"
            )
        if success_criteria:
            parts.append(
                f"\n## SUCCESS CRITERIA (revision must meet)\n\n{success_criteria}"
            )
        if guard_rails:
            parts.append(f"\n## GUARD RAILS\n\n{guard_rails}")
    elif step == "verifier":
        # Verifier confirms mandatory-fix addressal. Mode-specific checks
        # layer on top of the universal V1-V8 floor (the universal checklist
        # lives in f-verify.md; loaded alongside this prompt by the pipeline
        # function).
        if verifier_checks:
            parts.append(
                f"\n## MODE — {mode_name} — Verifier checks for this mode\n\n"
                f"{verifier_checks}"
            )
        if success_criteria:
            parts.append(
                f"\n## SUCCESS CRITERIA (floor for verification)\n\n"
                f"{success_criteria}"
            )
        if emission_contract:
            parts.append(
                f"\n## EMISSION CONTRACT (reference)\n\n{emission_contract}"
            )
        if content_contract:
            parts.append(
                f"\n## CONTENT CONTRACT (reference)\n\n{content_contract}"
            )
    else:  # step == "consolidator"
        # Consolidator (Gear 4) reconciles Depth + Breadth output per the
        # mode's consolidator guidance. Content + emission + success contracts
        # are the targets for the consolidated output.
        if consolidator_guidance:
            parts.append(
                f"\n## MODE — {mode_name} — Consolidator guidance\n\n"
                f"{consolidator_guidance}"
            )
        if content_contract:
            parts.append(
                f"\n## CONTENT CONTRACT (target for consolidated output)\n\n"
                f"{content_contract}"
            )
        if emission_contract:
            parts.append(
                f"\n## EMISSION CONTRACT (target for consolidated output)\n\n"
                f"{emission_contract}"
            )
        if success_criteria:
            parts.append(
                f"\n## SUCCESS CRITERIA (target for consolidated output)\n\n"
                f"{success_criteria}"
            )

    # RAG (all steps benefit from conversation + knowledge + relationship context)
    if context_package["conversation_rag"]:
        parts.append(f"\n## CONVERSATION CONTEXT\n\n{context_package['conversation_rag']}")
    if context_package["concept_rag"]:
        parts.append(f"\n## KNOWLEDGE CONTEXT\n\n{context_package['concept_rag']}")
    if context_package.get("relationship_rag"):
        parts.append(f"\n## RELATIONSHIP CONTEXT\n\n{context_package['relationship_rag']}")
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
                 execution_context: str = "interactive") -> str:
    """Full orchestrated pipeline: Step 1 → Step 2 → Gear-appropriate execution → Output.

    For Gear 1-2: Single model with context package.
    For Gear 3: Sequential review (implemented in Phase 5).
    For Gear 4+: Parallel independent (implemented in Phase 6).

    execution_context: "interactive" (human at keyboard), "autonomous", or "agent".
    Controls whether Gear 4 can use commercial model overrides for parallel execution.
    """
    config = load_endpoints()

    # --- Step 1: Prompt Cleanup + Mode Selection ---
    # Build conversation context from recent history
    conv_context = ""
    if history:
        recent = [m for m in history[-6:] if m["role"] != "system"]
        conv_context = "\n".join(
            f"{m['role'].upper()}: {m['content'][:500]}" for m in recent
        )

    step1 = run_step1_cleanup(user_input, conv_context, config)

    # --- Step 2: Context Package Assembly ---
    context_pkg = run_step2_context_assembly(step1, config)
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
                          max_iterations: int = 10, images: list = None) -> str:
    """Inner agentic loop: call model, detect tool calls, execute, inject, repeat."""
    for iteration in range(max_iterations):
        # Pass images only on the first call
        response = call_model(messages, endpoint, images=images if iteration == 0 else None)
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            return strip_tool_calls(response)

        # Execute all tool calls
        tool_results = []
        for tc in tool_calls:
            result = execute_tool(tc["name"], tc["parameters"])
            tool_results.append(f"[Tool: {tc['name']}]\n{result}")

        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": f"[Tool results]\n" + "\n\n".join(tool_results)
        })

    return strip_tool_calls(response)


def _rag_tail(context_pkg: dict) -> str:
    """Shared RAG context suffix applied to every step prompt in Gears 3/4."""
    tail = ""
    conv_rag = context_pkg.get("conversation_rag") or ""
    concept_rag = context_pkg.get("concept_rag") or ""
    if conv_rag:
        tail += f"\n\n## CONVERSATION CONTEXT\n\n{conv_rag}"
    if concept_rag:
        tail += f"\n\n## KNOWLEDGE CONTEXT\n\n{concept_rag}"
    return tail


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
    """
    step_prompt = build_system_prompt_for_gear(
        context_pkg, slot=slot, step=step
    )
    if framework_name:
        framework_text = load_framework(framework_name)
        step_prompt = (
            f"{step_prompt}\n\n"
            f"## F-* UNIVERSAL SCAFFOLDING — {framework_name}\n\n"
            f"{framework_text}"
        )
    return step_prompt + _rag_tail(context_pkg)


def _verifier_passed(verifier_output: str) -> bool:
    """Phase 5 verifier contract: VERIFIED / VERIFIED WITH CORRECTIONS /
    VERIFICATION FAILED. 'VERIFIED' appearing without 'VERIFICATION FAILED'
    counts as pass; 'VERIFIED WITH CORRECTIONS' also passes (the
    corrections are already applied in the verifier's output).
    """
    return "VERIFIED" in verifier_output and "VERIFICATION FAILED" not in verifier_output


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
        return _run_model_with_tools(messages, endpoint, images=images)

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
        verified = _run_model_with_tools(verify_messages, breadth_endpoint)

        if _verifier_passed(verified) or cycle == MAX_VERIFY_CYCLES:
            break

        # Verifier rejected — reviser addresses the verifier's findings.
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

    return verified


def run_gear4(context_pkg: dict, config: dict, history: list = None,
              images: list = None, execution_context: str = "interactive") -> str:
    """Gear 4: Parallel independent analysis via Phase-5 cascade dispatch.

    Step 3 — Parallel Depth + Breadth analysts (mode DEPTH/BREADTH MODEL
             INSTRUCTIONS via step='analyst').
    Step 4 — Cross-evaluation: Breadth evaluates Depth's output; Depth
             evaluates Breadth's. Both use step='evaluator' + f-evaluate.md.
    Step 5 — Parallel reviser calls (step='reviser' + f-revise.md).
    Step 6 — Cross-verification with up to 2 correction cycles
             (step='verifier' + f-verify.md).
    Step 7 — Breadth consolidates (step='consolidator' + f-consolidate.md).
    Step 8 — Depth runs a final verifier over the consolidated output.

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

    # --- Step 3: Parallel analysts ---
    depth_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="analyst", framework_name=None
    )
    breadth_system = _assemble_step_prompt(
        context_pkg, slot="breadth", step="analyst", framework_name=None
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        depth_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": depth_system},
             {"role": "user", "content": cleaned_prompt}],
            depth_endpoint, images=images
        )
        breadth_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": breadth_system},
             {"role": "user", "content": cleaned_prompt}],
            breadth_endpoint, images=images
        )
        try:
            depth_analysis = depth_future.result()
        except Exception as e:
            depth_analysis = f"[Depth model error: {e}]"
        try:
            breadth_analysis = breadth_future.result()
        except Exception as e:
            breadth_analysis = f"[Breadth model error: {e}]"

    # --- Step 4: Cross-evaluation (universal contract, both directions) ---
    eval_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="evaluator",
        framework_name="f-evaluate.md",
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        eval_a_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": eval_system},
             {"role": "user", "content": (
                 f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                 f"## ANALYST OUTPUT (Depth stream)\n\n{depth_analysis}\n\n"
                 "Evaluate per the universal seven-section contract."
             )}],
            breadth_endpoint
        )
        eval_b_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": eval_system},
             {"role": "user", "content": (
                 f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                 f"## ANALYST OUTPUT (Breadth stream)\n\n{breadth_analysis}\n\n"
                 "Evaluate per the universal seven-section contract."
             )}],
            depth_endpoint
        )
        try:
            breadth_eval_of_depth = eval_a_future.result()
        except Exception as e:
            breadth_eval_of_depth = f"[Evaluation error: {e}]"
        try:
            depth_eval_of_breadth = eval_b_future.result()
        except Exception as e:
            depth_eval_of_breadth = f"[Evaluation error: {e}]"

    # --- Step 5: Parallel revisers (mirror contract) ---
    revise_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="reviser",
        framework_name="f-revise.md",
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        depth_revise_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": revise_system},
             {"role": "user", "content": (
                 f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                 f"## YOUR ORIGINAL ANALYSIS\n\n{depth_analysis}\n\n"
                 f"## EVALUATOR'S CRITIQUE\n\n{breadth_eval_of_depth}\n\n"
                 "Revise per the universal reviser output contract."
             )}],
            depth_endpoint
        )
        breadth_revise_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": revise_system},
             {"role": "user", "content": (
                 f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                 f"## YOUR ORIGINAL ANALYSIS\n\n{breadth_analysis}\n\n"
                 f"## EVALUATOR'S CRITIQUE\n\n{depth_eval_of_breadth}\n\n"
                 "Revise per the universal reviser output contract."
             )}],
            breadth_endpoint
        )
        try:
            revised_depth = depth_revise_future.result()
        except Exception as e:
            revised_depth = f"[Revision error: {e}]"
        try:
            revised_breadth = breadth_revise_future.result()
        except Exception as e:
            revised_breadth = f"[Revision error: {e}]"

    # --- Step 6: Cross-verification with up to 2 correction cycles ---
    verify_system = _assemble_step_prompt(
        context_pkg, slot="depth", step="verifier",
        framework_name="f-verify.md",
    )

    MAX_VERIFY_CYCLES = 2
    for cycle in range(MAX_VERIFY_CYCLES + 1):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            verify_depth_future = executor.submit(
                _run_model_with_tools,
                [{"role": "system", "content": verify_system},
                 {"role": "user", "content": (
                     f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                     f"## REVISED DEPTH ANALYSIS\n\n{revised_depth}\n\n"
                     f"## EVALUATOR'S MANDATORY FIXES\n\n"
                     f"{breadth_eval_of_depth}\n\n"
                     "Run V1-V8 + mode-specific verifier checks. Conclude "
                     "VERIFIED / VERIFIED WITH CORRECTIONS / VERIFICATION "
                     "FAILED."
                 )}],
                breadth_endpoint
            )
            verify_breadth_future = executor.submit(
                _run_model_with_tools,
                [{"role": "system", "content": verify_system},
                 {"role": "user", "content": (
                     f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
                     f"## REVISED BREADTH ANALYSIS\n\n{revised_breadth}\n\n"
                     f"## EVALUATOR'S MANDATORY FIXES\n\n"
                     f"{depth_eval_of_breadth}\n\n"
                     "Run V1-V8 + mode-specific verifier checks. Conclude "
                     "VERIFIED / VERIFIED WITH CORRECTIONS / VERIFICATION "
                     "FAILED."
                 )}],
                depth_endpoint
            )
            try:
                depth_verdict = verify_depth_future.result()
            except Exception as e:
                depth_verdict = f"VERIFIED\n[Verification error, auto-pass: {e}]"
            try:
                breadth_verdict = verify_breadth_future.result()
            except Exception as e:
                breadth_verdict = f"VERIFIED\n[Verification error, auto-pass: {e}]"

        depth_passed = _verifier_passed(depth_verdict)
        breadth_passed = _verifier_passed(breadth_verdict)

        if (depth_passed and breadth_passed) or cycle == MAX_VERIFY_CYCLES:
            break

        futures = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            if not depth_passed:
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
            if not breadth_passed:
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
    consolidate_messages = [
        {"role": "system", "content": consolidate_system},
        {"role": "user", "content": (
            f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
            f"## DEPTH STREAM OUTPUT (revised)\n\n{revised_depth}\n\n"
            f"## BREADTH STREAM OUTPUT (revised)\n\n{revised_breadth}\n\n"
            "Reconcile per the mode's consolidator guidance and the "
            "universal F-Consolidate contract. Emit the consolidated "
            "analysis plus a CONTINUITY PROMPT."
        )},
    ]
    consolidated = _run_model_with_tools(consolidate_messages, breadth_endpoint)

    # --- Step 8: Depth runs final verifier over the consolidation ---
    final_verify_messages = [
        {"role": "system", "content": verify_system},
        {"role": "user", "content": (
            f"## ORIGINAL QUERY\n\n{cleaned_prompt}\n\n"
            f"## CONSOLIDATED OUTPUT TO VERIFY\n\n{consolidated}\n\n"
            f"## DEPTH FINAL (for comparison)\n\n{revised_depth}\n\n"
            f"## BREADTH FINAL (for comparison)\n\n{revised_breadth}\n\n"
            "Verify the consolidated output per V1-V8 plus mode-specific "
            "verifier checks."
        )},
    ]
    verified = _run_model_with_tools(final_verify_messages, depth_endpoint)

    return verified


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
    # For browser endpoints, take the last user message
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if images:
        # Browser endpoints are text-only — note attached images
        img_note = ", ".join(img["name"] for img in images)
        last_user = f"[User attached {len(images)} image(s): {img_note}]\n\n{last_user}"
    service = endpoint.get("service", "claude")
    if TOOLS_AVAILABLE:
        return browser_evaluate(service, last_user)
    return "[Error] browser_evaluate tool not available"


def parse_tool_calls(text: str) -> list[dict]:
    """Extract all <tool_call> blocks from model output."""
    pattern = r'<tool_call>\s*<n>(.*?)</n>\s*<parameters>(.*?)</parameters>\s*</tool_call>'
    matches = re.findall(pattern, text, re.DOTALL)
    calls = []
    for name, params_str in matches:
        try:
            params = json.loads(params_str.strip())
        except json.JSONDecodeError:
            params = {"raw": params_str.strip()}
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


def execute_tool(name: str, params: dict) -> str:
    """Dispatch tool call through unified dispatcher.

    Legacy tools (code_execute, continuity_save, queue_read) are handled
    directly; all others route through dispatcher.py for permission gating,
    path validation, command classification, and audit logging.
    """
    if not TOOLS_AVAILABLE:
        return "[Tools unavailable — import failed at startup]"

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
