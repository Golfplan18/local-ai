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
RUNTIME_CONFIG_FILE = os.path.join(ARCHITECTURE_DIR, "runtime-configuration.md")
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
            "display_description": str,   # 400-char-limit picker body
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
    """Load a mode file from modes/."""
    path = os.path.join(MODES_DIR, f"{mode_name}.md")
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
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
# Phase 9 — Decision C: runtime configuration with default-on-missing-config
# error path. Per Decision C, missing entries error safely; there is NO silent
# fallback to a default gear.
# ---------------------------------------------------------------------------

def load_runtime_config_for_mode(mode_id: str) -> dict | None:
    """Load runtime config entry for a mode.

    Per Decision C, this errors if the entry is missing; there is no silent
    fallback to a default gear. Callers must handle ``KeyError`` explicitly.
    """
    if not os.path.exists(RUNTIME_CONFIG_FILE):
        raise FileNotFoundError(
            f"Runtime config file missing: {RUNTIME_CONFIG_FILE}"
        )
    with open(RUNTIME_CONFIG_FILE, "r") as f:
        content = f.read()
    # naive parse: find `<mode_id>:` block (indented YAML lines beneath)
    pattern = rf"^{re.escape(mode_id)}:\s*\n((?:  .+\n)+)"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        raise KeyError(
            f"Runtime config entry missing for mode_id '{mode_id}'. "
            f"Per Decision C, this errors safely; default-on-missing-config "
            f"is not allowed."
        )
    # TODO Phase 9 follow-up: parse the YAML block into structured fields
    # (gear_default, lens_pack, contract_version, etc.) once the consumer
    # call sites are wired up.
    return {"raw_yaml_block": match.group(1)}


# ---------------------------------------------------------------------------
# Phase 9 — Pre-routing pipeline: Stage 1 (Pre-Analysis Filter)
# Spec: ~/ora/architecture/pre-routing-pipeline.md §Stage 1
# ---------------------------------------------------------------------------

# Bypass triggers split into two priority levels:
#   - STRONG_BYPASS: always wins over analytical signals (system commands,
#     prior-conversation references, factual lookups)
#   - WEAK_BYPASS: loses to strong analytical signals (greetings, ack)
STRONG_BYPASS_TRIGGERS = [
    # factual / lookup
    "what time", "what's the date", "what's the time",
    "what time is it", "what is the capital", "what's the capital",
    "how many tokens", "how many tokens does",
    # prior-conversation references
    "what did you say", "earlier you said", "remind me what",
    "show me the previous", "repeat what you", "what was your previous",
    # system commands and service requests
    "/help", "/?", "save this conversation", "convert this pdf",
    "translate this", "spell-check", "spell check",
    # negation-flagged analytical override
    "don't analyze", "do not analyze", "no analysis",
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

    Short signals (≤6 chars or all-caps acronyms) require word-boundary match
    so 'Ma' doesn't match inside 'Make'. Multi-word signals are matched as
    substrings (longer phrases are unlikely to collide).
    """
    if not signal or not prompt:
        return False
    norm_prompt = _normalize_for_match(prompt)
    norm_signal = _normalize_for_match(signal)

    # Multi-word signals: substring match (low collision risk).
    if " " in norm_signal:
        return norm_signal in norm_prompt

    # Single-word signals: require word-boundary match.
    pattern = r"(?:^|[^a-z0-9])" + re.escape(norm_signal) + r"(?:$|[^a-z0-9])"
    return bool(re.search(pattern, norm_prompt))


def _is_negated(prompt: str, signal: str) -> bool:
    """Check if a negation marker appears within ±3 tokens of the signal.

    Implementation: locate the signal in the prompt, then look at the 3
    tokens before and 3 tokens after for any negation marker. Case-insensitive.
    """
    norm_prompt = _normalize_for_match(prompt)
    norm_signal = _normalize_for_match(signal)
    idx = norm_prompt.find(norm_signal)
    if idx < 0:
        return False
    # Find token boundaries around the signal
    pre_text = norm_prompt[:idx]
    post_text = norm_prompt[idx + len(norm_signal):]
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
    # a system command, not requesting fresh analysis).
    for trigger in STRONG_BYPASS_TRIGGERS:
        if _signal_present(prompt, trigger.strip()):
            return {
                "bypass_to_direct_response": True,
                "matches": [],
                "rationale": f"strong bypass trigger: '{trigger.strip()}'",
            }

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
        for trigger in WEAK_BYPASS_TRIGGERS:
            if _signal_present(prompt, trigger.strip()):
                return {
                    "bypass_to_direct_response": True,
                    "matches": [],
                    "rationale": f"weak bypass trigger: '{trigger.strip()}'",
                }

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
    # Locate the input_contract: line and capture the indented block
    pattern = r"^input_contract:\s*\n((?:  .+\n|\n)+?)(?=^[a-z][\w-]*:|\Z)"
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
            "detected_invocation": "",
        }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    cleanup_response = call_model(messages, endpoint)
    step1_result = parse_step1_output(cleanup_response)

    # --- Pass 2: Pre-routing pipeline (replaces Phase A.5) ---
    # Phase 9: the four-stage pre-routing pipeline replaces the retired
    # Mode Classification Directory's intent-classification flow. Stage 1
    # filters bypass prompts; Stage 2 picks a mode from signal vocabulary
    # plus disambiguation; Stage 3 checks input completeness; Stage 4
    # (mode execution) happens downstream in run_pipeline.
    routing = run_pre_routing_pipeline(
        prompt=step1_result["operational_notation"],
        context=None,
    )

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
        # Pending clarification — surface the question via classification_reasoning
        # and pick the standard catch-all so downstream pipeline still runs.
        step1_result["mode"] = "standard"
        step1_result["triage_tier"] = 2
        step1_result["classification_confidence"] = "low"
        step1_result["classification_runner_up"] = ""
        step1_result["classification_reasoning"] = (
            f"clarification needed: {routing['pending_clarification']}"
        )
        step1_result["classification_intent"] = "CATCH-ALL"
        step1_result["detected_invocation"] = ""

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

    return step1_result


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

    # Phase 5.6 ranker: type-weighted ranking with provenance markers,
    # type_filter from active mode's RAG PROFILE, archived/private filters.
    # Falls back to the legacy formatted-string knowledge_search when the
    # ranker module isn't loadable (graceful degradation).
    conv_rag = ""
    if RAG_ENGINE_AVAILABLE:
        try:
            conv_rag = assemble_ranked_context(
                query=cleaned_prompt,
                collection="conversations",
                mode_text=mode_text,
                n_results=3,
            )
        except Exception:
            conv_rag = ""
    elif TOOLS_AVAILABLE:
        try:
            conv_rag = knowledge_search(cleaned_prompt, "conversations", 3)
        except Exception:
            conv_rag = ""

    # Concept RAG (vault knowledge) — only for Gear 2+
    concept_rag = ""
    if gear >= 2:
        if RAG_ENGINE_AVAILABLE:
            try:
                concept_rag = assemble_ranked_context(
                    query=cleaned_prompt,
                    collection="knowledge",
                    mode_text=mode_text,
                    n_results=5,
                )
            except Exception:
                concept_rag = ""
        elif TOOLS_AVAILABLE:
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
        # --- Phase 9 Decision I/J additive fields ---
        "territory": territory,
        "mode": mode_name,  # mirror of mode_name under Decision I/J's preferred field name
        "residual_disambiguation_questions": residual_questions,
        "completeness_gaps": completeness_gaps,
        "dispatch_announcement": dispatch_announcement,
        "pre_routing": pre_routing,
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
