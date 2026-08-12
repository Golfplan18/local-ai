"""
Model routing engine for Ora.

Resolves pipeline slots to endpoints using the bucket-based priority system
defined in routing-config.json. Handles:
  - Bucket resolution with ordered fallthrough
  - MLX parallel constraint (two local models on same machine)
  - Gear downgrade cascade
  - Warning generation (overkill, underkill, same-provider, swap risk)
  - V1 endpoint compatibility (returns dicts usable by call_model)

Usage:
    from orchestrator.router import Router

    router = Router()  # loads routing-config.json
    result = router.execute(requested_gear=4, context="interactive")

    # result.assignments: dict of slot -> endpoint
    # result.gear: int (may be lower than requested if downgraded)
    # result.warnings: list of warning dicts
    # result.parallel_safe: bool (for gear 4)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from . import runtime_paths as rp
except ImportError:  # direct script-style import from sys.path
    import runtime_paths as rp  # type: ignore

CONFIG_DIR = Path(__file__).parent.parent / "config"
ROUTING_CONFIG_PATH = CONFIG_DIR / "routing-config.json"
CONFIGURATIONS_DIR = CONFIG_DIR / "configurations"
_DEFAULT_CONFIGURATIONS_DIR = CONFIGURATIONS_DIR

DEFAULT_MACHINE_ID = "studio-128"

# Default configuration name when one is not explicitly provided.
# Maps from the legacy ``context`` parameter for backward compatibility.
DEFAULT_CONFIG_FOR_CONTEXT = {
    "interactive": "user-pipeline",
    "agent": "background-default",
    "autonomous": "background-default",
}

# Slots required at each gear level
GEAR_SLOTS = {
    4: ["depth", "breadth"],
    3: ["depth", "breadth"],
    2: ["primary"],
    1: ["sidebar"],
}

# Pipeline cell mapping: which config cell provides the bucket list for each slot at each gear
# When a cell is None, it inherits from the parent section's bucket list
SLOT_TO_CELL = {
    4: {
        "depth":  ("analysis", "gear4", "depth"),
        "breadth": ("analysis", "gear4", "breadth"),
    },
    3: {
        "depth":  ("analysis", "gear3", "depth"),
        "breadth": ("analysis", "gear3", "breadth"),
    },
    2: {
        "primary": ("utility", None, None),  # uses utility buckets for single-pass
    },
    1: {
        "sidebar": ("utility", None, None),
    },
}

# Slots that should use utility-tier models (overkill warning if premium/large used)
UTILITY_SLOTS = {"step1_cleanup", "rag_planner", "sidebar", "classification"}

# Slots that need capable models (underkill warning if small/free used)
ANALYSIS_SLOTS = {"depth", "breadth", "consolidation", "verification", "evaluator",
                  "consolidator", "primary"}

# Default overkill thresholds: these tiers trigger warnings in utility slots
OVERKILL_TIERS = {"local-premium", "premium", "mid"}

# Default underkill thresholds: these tiers trigger warnings in analysis slots
UNDERKILL_TIERS = {"local-fast", "free"}


@dataclass
class RoutingResult:
    """Result of a routing resolution."""
    gear: int
    assignments: dict = field(default_factory=dict)  # slot -> v1-compatible endpoint dict
    assignments_v2: dict = field(default_factory=dict)  # slot -> v2 endpoint dict
    warnings: list = field(default_factory=list)
    parallel_safe: bool = True
    downgraded: bool = False
    original_gear: int = 0
    halt_reason: str = ""


@dataclass
class Warning:
    """A routing warning."""
    level: str  # "info", "caution", "critical"
    category: str  # "overkill", "underkill", "same_provider", "same_model", "swap_risk", "no_fallback", "mlx_constraint"
    message: str
    slot: str = ""
    dismissible: bool = True


class Router:
    """Bucket-based model routing engine."""

    def __init__(self, config_path: str | Path | None = None, config_dict: dict | None = None):
        """Initialize router from config file or dict.

        Args:
            config_path: Path to routing-config.json. Defaults to standard location.
            config_dict: Pre-loaded config dict (takes precedence over file).

        When ``config_path`` is used (the production path), the Router
        remembers the path so :meth:`reload` can re-read the file
        without the caller needing to remember it. When ``config_dict``
        is used (the test path), the Router has no source to reload
        from and :meth:`reload` is a documented no-op.
        """
        # Remember the path so reload() can re-read it. None means "no
        # file-backed source — reload is a no-op."
        self._config_path: Path | None = None
        self._uses_default_config_path = False
        if config_dict:
            self.config = config_dict
        else:
            self._uses_default_config_path = config_path is None
            self._config_path = Path(config_path) if config_path else rp.routing_config_path()
            with open(self._config_path) as f:
                self.config = json.load(f)

        self._build_lookup_tables()

    def _build_lookup_tables(self) -> None:
        """Rebuild the derived lookup tables from ``self.config``.

        Called from ``__init__`` and from :meth:`reload` after the
        config dict is refreshed. Splitting this out keeps both
        paths honest about which fields the Router caches in memory.
        """
        self._endpoints = {ep["id"]: ep for ep in self.config.get("endpoints", [])}
        self._merge_models_json_local_endpoints()
        self._merge_codex_subscription_endpoints()
        self._endpoint_aliases = self._build_endpoint_aliases()
        self._machines = {m["id"]: m for m in self.config.get("machines", [])}
        self._buckets = self.config.get("buckets", {})
        self._diversity = (self.config.get("diversity") or {}).get("enabled", False)
        # Named-configuration cache (Chunk 2b). Cleared on reload so file
        # edits to config/configurations/*.json take effect on next call.
        self._configurations: dict = {}
        # models.json vision_capable lookup cache (Chunk 2e). Cleared on
        # reload so edits to models.json also take effect immediately.
        self._vision_lookup_cache = None

    def _merge_models_json_local_endpoints(self) -> None:
        """Expose discovered local models as runtime endpoints.

        The Models pane and hardware panel read discovered local models from
        config/models.json, while older routing-config endpoints can drift
        behind that list. Merge the discovered entries into the in-memory
        endpoint lookup so picking one in a configuration actually resolves at
        dispatch time. This is intentionally runtime-only; discovery remains
        the source of truth for the installed local set.
        """
        try:
            models_path = rp.overlay_path("config", "models.json")
            if not models_path.exists():
                return
            with open(models_path) as f:
                data = json.load(f)
        except Exception as exc:
            print(f"[Router] models.json local endpoint merge failed: {exc}")
            return

        for model in data.get("local_models", []) or []:
            model_id = model.get("id")
            if not model_id:
                continue
            model_path = model.get("path") or model.get("model_path") or ""
            ram_gb = model.get("ram_gb") or 0
            endpoint = dict(self._endpoints.get(model_id) or {})
            endpoint.update({
                "id": model_id,
                "type": "local",
                "engine": endpoint.get("engine") or "mlx",
                "machine": endpoint.get("machine") or DEFAULT_MACHINE_ID,
                "model_path": model_path,
                "display_name": model.get("display_name") or endpoint.get("display_name") or model_id,
                "provider": endpoint.get("provider") or "local",
                "tier": endpoint.get("tier") or self._local_tier_for_models_json_entry(model),
                "status": "active" if model_path and Path(model_path).exists() else "inactive",
                "enabled": bool(model_path and Path(model_path).exists()),
                "ram_resident_gb": ram_gb,
                "ram_overhead_gb": endpoint.get("ram_overhead_gb") or 0,
                "context_window": endpoint.get("context_window") or 32768,
                "parameters_b": model.get("parameters_b") or model.get("active_params_per_token"),
                "capabilities": endpoint.get("capabilities") or {
                    "tool_access": True,
                    "file_system_access": True,
                    "web_access": False,
                    "retrieval_approach": "agentic",
                },
                "vision_capable": bool(model.get("vision_capable", endpoint.get("vision_capable", False))),
                "_installed_local_model": True,
            })
            self._endpoints[model_id] = endpoint

    def _merge_codex_subscription_endpoints(self) -> None:
        """Expose connected ChatGPT/Codex models as runtime endpoints.

        A never-configured user must not pay the cost of starting the bundled
        Codex runtime.  The adapter's dedicated home is therefore the gate;
        connected-account and model truth remain SDK-managed and no discovered
        model is written into routing-config.json.
        """
        try:
            try:
                from orchestrator import codex_subscription
            except ImportError:
                import codex_subscription  # type: ignore
            if not codex_subscription.is_configured():
                return
            for endpoint in codex_subscription.model_endpoints():
                endpoint_id = endpoint.get("id")
                if endpoint_id:
                    self._endpoints[endpoint_id] = endpoint
        except Exception as exc:
            print(
                "[Router] ChatGPT subscription endpoint merge failed: "
                f"{type(exc).__name__}"
            )

    def _build_endpoint_aliases(self) -> dict[str, str]:
        """Return case-insensitive endpoint aliases for exact routing ids.

        The model catalog and provider endpoints do not always use the same
        spelling. MiniMax is the sharp edge: OpenRouter/catalog ids are
        ``minimax/minimax-m3`` while the direct provider endpoint is registered as
        ``minimax/MiniMax-M3``. Named configurations are edited from both sides,
        so a case-equivalent catalog id should resolve instead of silently
        falling through the chain.
        """
        aliases: dict[str, str] = {}
        for ep_id in self._endpoints:
            if isinstance(ep_id, str):
                aliases.setdefault(ep_id.lower(), ep_id)
        return aliases

    def _resolve_endpoint_id(self, ep_id: str) -> str:
        if ep_id in self._endpoints:
            return ep_id
        return self._endpoint_aliases.get(ep_id.lower(), ep_id)

    @staticmethod
    def _supports_explicit_interactive(endpoint: dict | None) -> bool:
        return bool(
            endpoint
            and endpoint.get("enabled") is not False
            and endpoint.get("status", "active") == "active"
            and endpoint.get("type") in ("local", "api")
        )

    def resolve_endpoint_by_id(self, endpoint_id: str) -> dict | None:
        """Resolve one explicit interactive model preference.

        Unlike slot resolution this does not walk a fallback chain. It still
        enforces the runtime eligibility floor so a saved preference cannot
        dispatch to a disabled, inactive, unsupported, or cooling endpoint.
        """
        if not isinstance(endpoint_id, str) or not endpoint_id.strip():
            return None
        resolved_id = self._resolve_endpoint_id(endpoint_id.strip())
        endpoint = self._endpoints.get(resolved_id)
        # call_model supports local and API transports. Browser-session models
        # require a different invocation surface and are not valid here.
        if not self._supports_explicit_interactive(endpoint):
            return None
        try:
            import endpoint_health
        except ImportError:
            from orchestrator import endpoint_health
        if endpoint_health.is_in_cooldown(resolved_id):
            return None
        return endpoint

    def list_interactive_endpoints(self) -> list[dict]:
        """List configured interactive choices without mutating health state.

        Cooldown is intentionally checked only by resolve_endpoint_by_id at
        dispatch time. Calling is_in_cooldown while rendering Settings can
        consume a half-open circuit-breaker probe before any model call occurs.
        """
        return [
            self._endpoints[endpoint_id]
            for endpoint_id in sorted(self._endpoints)
            if self._supports_explicit_interactive(
                self._endpoints[endpoint_id])
        ]

    @staticmethod
    def _local_tier_for_models_json_entry(model: dict) -> str:
        roles = set(model.get("recommended_roles") or [])
        if roles.intersection({"breadth", "depth", "evaluator", "consolidator"}):
            return "local-premium"
        ram = model.get("ram_gb")
        params = model.get("parameters_b")
        if params is None:
            params = model.get("active_params_per_token")
        try:
            params = float(params) if params is not None else None
        except (TypeError, ValueError):
            params = None
        if params is not None:
            if params <= 12 and (ram is None or ram <= 8):
                return "local-fast"
            if params <= 50:
                return "local-mid"
            return "local-premium"
        if ram is not None:
            if ram <= 8:
                return "local-fast"
            if ram <= 32:
                return "local-mid"
        return "local-premium"

    def reload(self) -> bool:
        """Re-read the routing-config file and rebuild lookup tables.

        Returns ``True`` when the reload landed cleanly, ``False`` when
        the Router has no file-backed source (constructed from a
        ``config_dict``) or when the file read / JSON parse failed
        (the previous in-memory config is preserved on failure so the
        live pipeline keeps running with the last-known-good state).

        Called by ``boot.reload_router()`` after the V3 Settings panel
        POSTs to ``/config/routing`` — without this hook, the singleton
        Router in :func:`boot._get_router` holds the original config in
        memory until the server is restarted, and bucket / model /
        slot changes from the panel are invisible to the running
        pipeline.
        """
        if self._config_path is None:
            return False
        try:
            if self._uses_default_config_path:
                self._config_path = rp.routing_config_path()
            with open(self._config_path) as f:
                new_config = json.load(f)
        except Exception as exc:  # pragma: no cover — exercised in tests via missing file
            # Keep the prior config in memory so the running pipeline
            # doesn't silently degrade. The caller logs the failure.
            print(f"[Router] reload failed (keeping prior config): {exc}")
            return False
        self.config = new_config
        self._build_lookup_tables()
        return True

    def resolve_endpoint(self, slot: str, gear: int, context: str,
                         excluded_ids: set | None = None,
                         same_machine_block: str | None = None,
                         config_name: str | None = None,
                         mutex_check: bool = True) -> dict | None:
        """Resolve a single slot to a v2 endpoint dict.

        Args:
            slot: The pipeline slot to fill (depth, breadth, sidebar, etc.)
            gear: Current gear level being attempted
            context: "interactive" or "agent" — when ``config_name`` is None,
                this is mapped to a default configuration via
                DEFAULT_CONFIG_FOR_CONTEXT (Chunk 2d cutover).
            excluded_ids: Endpoint IDs already assigned (for diversity)
            same_machine_block: Machine ID to block local endpoints from (MLX constraint)
            config_name: Named configuration in config/configurations/.
                When None, the effective configuration is derived from
                ``context``.
            mutex_check: When True (the default), local endpoints with a
                currently-held per-machine MLX mutex are skipped over and
                the next entry in the chain is tried. When every entry is
                either ineligible or a busy local, the first busy local
                encountered is returned so the caller's ``call_model``
                queues at the mutex (the spec's "no API fallback so we
                wait" path). Pass False for unit tests that need a
                deterministic resolution unaffected by global mutex state.

        Returns:
            v2 endpoint dict, or None if no eligible endpoint found.
        """
        excluded_ids = excluded_ids or set()
        effective_config = self._resolve_config_name(config_name, context)

        if effective_config is not None:
            return self._resolve_from_configuration(
                slot, gear, effective_config,
                excluded_ids=excluded_ids,
                same_machine_block=same_machine_block,
                mutex_check=mutex_check,
            )

        # ── Legacy bucket-walk path (retained as fallback when no
        # configuration is resolved — e.g. unknown context with no
        # explicit config_name). Chunk 12 removes this entirely.
        bucket_order = self._get_bucket_order(slot, gear, context)

        if not bucket_order:
            return None

        first_busy_local: dict | None = None
        for bucket_name in bucket_order:
            if bucket_name == "STOP":
                break

            model_ids = self._buckets.get(bucket_name, [])
            for ep_id in model_ids:
                ep = self._endpoints.get(ep_id)
                if not ep:
                    continue
                if not ep.get("enabled", False):
                    continue
                if ep.get("status") != "active":
                    continue
                if ep_id in excluded_ids:
                    continue

                # MLX parallel constraint: block local endpoints on the same machine
                if same_machine_block and ep.get("type") == "local":
                    if ep.get("machine") == same_machine_block:
                        continue

                if mutex_check and ep.get("type") == "local":
                    machine_id = ep.get("machine") or DEFAULT_MACHINE_ID
                    try:
                        import mlx_mutex
                    except ImportError:
                        from orchestrator import mlx_mutex
                    if mlx_mutex.is_machine_busy(machine_id):
                        if first_busy_local is None:
                            first_busy_local = ep
                        continue

                # Phase 2b circuit breaker: skip endpoints currently in
                # cooldown after repeated failures. After cooldown elapses
                # the next caller is allowed through as a probe — see
                # endpoint_health.is_in_cooldown for the half-open detail.
                try:
                    import endpoint_health
                except ImportError:
                    from orchestrator import endpoint_health
                if endpoint_health.is_in_cooldown(ep_id):
                    continue

                return ep

        return first_busy_local

    @staticmethod
    def _resolve_configuration_cell(config: dict, cell: object) -> dict | None:
        """Resolve an optional role reference in a project configuration."""
        if not isinstance(cell, dict):
            return None
        role = cell.get("role")
        if not role:
            return cell
        roles = config.get("roles")
        resolved = roles.get(role) if isinstance(roles, dict) else None
        return resolved if isinstance(resolved, dict) else None

    def resolve_gear(self, gear: int, context: str,
                     config_name: str | None = None) -> dict | None:
        """Resolve all slots for a gear level.

        Returns dict of {slot: v2_endpoint} or None if any required slot can't be filled.

        For multi-slot gears (3 and 4), the second slot prefers a different model
        than the first for adversarial diversity. Falls back to the same model if
        no alternative is available.

        ``config_name`` (Chunk 2b) routes the resolution through a named
        configuration in config/configurations/ rather than the legacy
        pipelines[context] block.

        Per-config ``diversity_override: false`` (added 2026-05-23) disables
        the adversarial-diversity exclusion for the breadth slot. Use case:
        single-model demo configurations where every slot is intentionally
        the same endpoint (e.g., qwen-9b-only proves Ora's pipeline lifts
        a single 9B model). Without the override, gear 4 would downgrade
        all the way to gear 2 (single-pass) because the breadth resolver
        excludes the depth id and no fallback survives.
        """
        slots = GEAR_SLOTS.get(gear, [])
        assignments = {}

        # Resolve per-config diversity policy. Defaults to the global
        # routing-config setting; an explicit per-config override wins.
        config_diversity = self._diversity
        if config_name:
            try:
                cfg_dict = self._load_configuration(config_name)
            except Exception:
                cfg_dict = None
            if isinstance(cfg_dict, dict) and "diversity_override" in cfg_dict:
                config_diversity = bool(cfg_dict["diversity_override"])

        for slot in slots:
            same_machine_block = None

            # For Gear 4: apply MLX parallel constraint
            if gear == 4 and slot == "breadth" and "depth" in assignments:
                depth_ep = assignments["depth"]
                if depth_ep.get("type") == "local":
                    same_machine_block = depth_ep.get("machine")

            # For breadth slot: prefer a different model than depth for diversity.
            # Skipped entirely when the config sets diversity_override: false —
            # in that case breadth resolves the same way depth did, which
            # lands on the same endpoint as configured.
            if config_diversity and slot == "breadth" and "depth" in assignments:
                depth_id = assignments["depth"]["id"]

                # First attempt: exclude the depth model
                ep = self.resolve_endpoint(
                    slot, gear, context,
                    excluded_ids={depth_id},
                    same_machine_block=same_machine_block,
                    config_name=config_name,
                )

                # When diversity is enforced, do NOT fall back to the same model.
                # This lets the gear downgrade cascade find a wider pool at lower gears.
                if ep is None and not self._diversity:
                    ep = self.resolve_endpoint(
                        slot, gear, context,
                        same_machine_block=same_machine_block,
                        config_name=config_name,
                    )
            else:
                ep = self.resolve_endpoint(
                    slot, gear, context,
                    same_machine_block=same_machine_block,
                    config_name=config_name,
                )

            if ep is None:
                return None

            assignments[slot] = ep

        return assignments

    def execute(self, requested_gear: int, context: str = "interactive",
                config_name: str | None = None) -> RoutingResult:
        """Full routing with gear downgrade cascade.

        Tries the requested gear first. If any slot can't be filled, drops
        one gear level and retries with wider eligibility. Continues until
        a gear works or all gears are exhausted.

        Args:
            requested_gear: The gear level requested by the mode file (1-4).
            context: "interactive" or "agent" (legacy).
            config_name: When provided, routes through the named configuration
                in config/configurations/<name>.json. Chunk 2b adds this; the
                ``context`` path remains for backward compatibility through
                Chunk 2d's cutover.

        Returns:
            RoutingResult with assignments, effective gear, warnings, etc.
        """
        result = RoutingResult(
            gear=requested_gear,
            original_gear=requested_gear,
        )

        for gear in range(requested_gear, 0, -1):
            assignments = self.resolve_gear(gear, context, config_name=config_name)

            if assignments is not None:
                result.gear = gear
                result.downgraded = (gear < requested_gear)
                result.assignments_v2 = assignments
                result.assignments = {
                    slot: self._to_v1_endpoint(ep)
                    for slot, ep in assignments.items()
                }

                # Gear-4 parallel-safety UI hint. Since the 2026-05-19
                # concurrency overhaul this no longer gates control flow
                # — run_gear4 always submits both analysts in parallel and
                # the per-machine MLX mutex (mlx_mutex.acquire inside
                # call_model) serializes them on same-machine all-local
                # setups. The flag is kept so the chat UI can surface
                # "Gear 4 (sequential, ~2x runtime)" when both endpoints
                # land on the same local machine. The prior
                # ORA_FORCE_GEAR4_PARALLEL env-var escape hatch became
                # redundant — the new default is "always run Gear 4 in
                # parallel; mutex handles serialization when needed".
                if gear == 4:
                    depth = assignments.get("depth", {})
                    breadth = assignments.get("breadth", {})
                    both_local = (depth.get("type") == "local" and
                                  breadth.get("type") == "local")
                    same_machine = (depth.get("machine") == breadth.get("machine"))
                    result.parallel_safe = not (both_local and same_machine)

                # Generate warnings
                result.warnings = self._generate_warnings(assignments, gear, context)

                return result

        # Nothing worked at any gear level
        result.gear = 0
        result.halt_reason = f"No endpoints available for any gear level (context={context})"
        return result

    def resolve_utility_slot(self, slot: str, context: str = "interactive",
                             config_name: str | None = None) -> dict | None:
        """Resolve a utility slot (step1_cleanup, rag_planner) directly.

        These slots don't participate in the gear system — they always use
        the utility bucket order regardless of gear.

        ``config_name`` (Chunk 2b/2d) routes through a named configuration;
        when None, derived from ``context``.
        """
        effective_config = self._resolve_config_name(config_name, context)
        if effective_config is not None:
            # Utility slots resolve at gear 1 for cell-path purposes.
            return self._resolve_from_configuration(slot, 1, effective_config)

        pipeline = self.config.get("pipelines", {}).get(context, {})
        utility = pipeline.get("utility", {})

        # Check for expanded cell-specific config
        cells = utility.get("cells", {})
        cell_config = cells.get(slot) if cells else None

        if cell_config and isinstance(cell_config, dict):
            bucket_order = cell_config.get("buckets", [])
        else:
            bucket_order = utility.get("buckets", [])

        for bucket_name in bucket_order:
            if bucket_name == "STOP":
                return None
            for ep_id in self._buckets.get(bucket_name, []):
                ep = self._endpoints.get(ep_id)
                if ep and ep.get("enabled") and ep.get("status") == "active":
                    return ep

        return None

    def resolve_post_analysis_slot(self, slot: str, context: str = "interactive",
                                   config_name: str | None = None) -> dict | None:
        """Resolve a post-analysis slot (consolidation, verification).

        Uses the post_analysis bucket order, or cell-specific config if expanded.

        ``config_name`` (Chunk 2b/2d) routes through a named configuration;
        when None, derived from ``context``.
        """
        effective_config = self._resolve_config_name(config_name, context)
        if effective_config is not None:
            # Post-analysis slots resolve at gear 4 for cell-path purposes
            # (the gear value here is just for routing; post_analysis cells
            # aren't gear-scoped).
            return self._resolve_from_configuration(slot, 4, effective_config)

        pipeline = self.config.get("pipelines", {}).get(context, {})
        post = pipeline.get("post_analysis", {})

        cells = post.get("cells", {})
        cell_config = cells.get(slot) if cells else None

        if cell_config and isinstance(cell_config, dict):
            bucket_order = cell_config.get("buckets", [])
        else:
            bucket_order = post.get("buckets", [])

        for bucket_name in bucket_order:
            if bucket_name == "STOP":
                return None
            for ep_id in self._buckets.get(bucket_name, []):
                ep = self._endpoints.get(ep_id)
                if ep and ep.get("enabled") and ep.get("status") == "active":
                    return ep

        return None

    def _post_analysis_candidate_ids(self, slot: str, context: str = "interactive",
                                     config_name: str | None = None,
                                     gear: int = 4) -> list:
        """Ordered endpoint-id candidates for a post-analysis slot, WITHOUT
        resolving (no mutex / circuit-breaker side effects): the cell's primary +
        fallback[] for a named configuration, else the legacy bucket-walk order.
        The family selector filters these; a pure config read."""
        effective_config = self._resolve_config_name(config_name, context)
        if effective_config is not None:
            return self.get_slot_chain(slot, gear, config_name=effective_config)
        pipeline = self.config.get("pipelines", {}).get(context, {})
        post = pipeline.get("post_analysis", {})
        cells = post.get("cells", {})
        cell_config = cells.get(slot) if cells else None
        bucket_order = (cell_config.get("buckets", [])
                        if isinstance(cell_config, dict) else post.get("buckets", []))
        ids: list = []
        for bucket_name in bucket_order:
            if bucket_name == "STOP":
                break
            for ep_id in self._buckets.get(bucket_name, []):
                ids.append(ep_id)
        return ids

    def resolve_different_family(self, slot: str, exclude_family: str | None,
                                 context: str = "interactive",
                                 config_name: str | None = None,
                                 gear: int = 4) -> dict | None:
        """§12 different-family verify SELECTOR (Execution Review Phase 6).

        Resolve a post-analysis slot (typically ``verification``) to an endpoint
        whose ``training_family`` DIFFERS from ``exclude_family`` (the executor's
        family) — the model-diversity governance rule: the lift comes from
        *uncorrelated blind spots*, so a verifier that shares the executor's family
        rubber-stamps it. Walks the slot's configured candidate chain (primary +
        fallbacks for a named config; the bucket-walk order otherwise), skipping
        ineligible (disabled / non-active) endpoints AND every candidate that is NOT
        a CONFIRMED different family.

        Returns a v1 endpoint dict, or ``None`` when no cross-family endpoint is
        configured/available — ``None`` is the signal for the caller's single-family
        graceful-degrade path (§12), never a silent breadth fallback (that fallback
        would defeat the requirement). An UNKNOWN executor family (empty) or an
        UNKNOWN candidate family yields ``None`` too: an unconfirmed difference must
        not be presented as cross-family assurance. Pure config read; never raises."""
        candidates = self.resolve_different_family_candidates(
            slot,
            exclude_family,
            context=context,
            config_name=config_name,
            gear=gear,
        )
        return candidates[0] if candidates else None

    def resolve_different_family_candidates(
        self,
        slot: str,
        exclude_family: str | None,
        context: str = "interactive",
        config_name: str | None = None,
        gear: int = 4,
    ) -> list[dict]:
        """Return the eligible cross-family candidate chain in profile order.

        The single-result selector remains the ordinary public resolution API.
        Execution Review also needs the remaining declared candidates so an
        unavailable verifier cannot suppress the Model Profile's failover chain.
        Every returned row has a confirmed family distinct from the executor.
        """
        try:
            exclude = (exclude_family or "").strip().lower()
            if not exclude:
                return []
            candidates = []
            for ep_id in self._post_analysis_candidate_ids(
                slot, context, config_name, gear
            ):
                if not ep_id:
                    continue
                resolved = self._resolve_endpoint_id(ep_id)
                ep = self._endpoints.get(resolved)
                if (
                    not ep
                    or not ep.get("enabled", False)
                    or ep.get("status") != "active"
                ):
                    continue
                fam = self._training_family(ep)
                if not fam or fam == exclude:
                    continue
                candidates.append(self._to_v1_endpoint(ep))
            return candidates
        except Exception:
            return []

    def resolve_full_pipeline(self, requested_gear: int,
                              context: str = "interactive",
                              config_name: str | None = None) -> dict:
        """Resolve the entire pipeline: utility + analysis + post-analysis.

        Returns a dict with all resolved slots and metadata.

        ``config_name`` (Chunk 2b) routes through a named configuration.
        """
        result = {}

        # Utility slots
        for slot in ["step1_cleanup", "rag_planner", "classification"]:
            ep = self.resolve_utility_slot(slot, context, config_name=config_name)
            result[slot] = self._to_v1_endpoint(ep) if ep else None

        # Analysis slots (with gear downgrade)
        analysis = self.execute(requested_gear, context, config_name=config_name)
        result["_analysis"] = analysis

        if analysis.gear >= 3:
            result["depth"] = analysis.assignments.get("depth")
            result["breadth"] = analysis.assignments.get("breadth")
        elif analysis.gear == 2:
            result["primary"] = analysis.assignments.get("primary")
        elif analysis.gear == 1:
            result["sidebar"] = analysis.assignments.get("sidebar")

        # Post-analysis slots
        for slot in ["consolidation", "verification"]:
            ep = self.resolve_post_analysis_slot(slot, context, config_name=config_name)
            result[slot] = self._to_v1_endpoint(ep) if ep else None

        return result

    # --- Private helpers ---

    # ── Chunk 2b: named-configuration resolution path ────────────────────
    #
    # When a caller passes ``config_name``, slot resolution reads from a
    # named configuration file in config/configurations/ (each cell holds
    # primary + fallback[] + vision_substitute) instead of walking the
    # legacy pipelines[context] → buckets[bucket_name] → endpoints[] chain.
    # The two paths coexist through Chunk 2d, after which the bucket walk
    # is retired.
    #
    # Slot-to-cell-path mapping (must stay in sync with get_slot_endpoint
    # in boot.py — the slot-name vocabulary is the contract):
    #
    #   sidebar / step1_cleanup / rag_planner / classification
    #       → cells.utility.<slot>
    #   depth / breadth
    #       → cells.analysis.gear{N}.<slot>
    #   consolidator / consolidation
    #       → cells.post_analysis.consolidation
    #   evaluator / verification
    #       → cells.post_analysis.verification
    #   formatter
    #       → cells.post_analysis.formatter
    #   primary  (gear 2 single-pass)
    #       → cells.analysis.gear3.depth  (mirrors the legacy fallback)

    # ── Chunk 2e: models.json as source of truth for vision_capable ──────
    #
    # vision_capable lives in two places today: routing-config.json::
    # endpoints[].vision_capable and models.json::{local_models,
    # commercial_models}[].vision_capable. They drift. Chunk 12 will
    # remove the field from routing-config.json::endpoints[]. Until then,
    # this helper centralizes the lookup with models.json preferred —
    # callers that go through it get the source-of-truth answer; callers
    # that read endpoint["vision_capable"] directly still work, they just
    # see the duplicated copy.

    def vision_capable_for_endpoint(self, endpoint_id: str) -> bool:
        """Return whether the endpoint can read images natively.

        Prefers models.json's value (source of truth per Chunk 2e).
        Falls back to routing-config.json::endpoints[].vision_capable
        when the model id isn't in models.json (e.g. browser endpoints).
        Defaults to False when neither has the field.
        """
        models_map = self._models_json_vision_lookup()
        if endpoint_id in models_map:
            return models_map[endpoint_id]
        ep = self._endpoints.get(endpoint_id, {})
        return bool(ep.get("vision_capable", False))

    def _models_json_vision_lookup(self) -> dict:
        """Cached id → vision_capable map sourced from config/models.json.

        Built lazily on first call; cleared by reload() via
        _build_lookup_tables.
        """
        cached = getattr(self, "_vision_lookup_cache", None)
        if cached is not None:
            return cached

        cache: dict = {}
        models_path = CONFIG_DIR / "models.json"
        try:
            with open(models_path) as f:
                data = json.load(f)
            for key in ("local_models", "commercial_models"):
                for m in data.get(key, []) or []:
                    mid = m.get("id")
                    if mid:
                        cache[mid] = bool(m.get("vision_capable", False))
        except Exception as exc:
            print(f"[Router] models.json vision-capable lookup failed: {exc}")

        self._vision_lookup_cache = cache
        return cache

    def _resolve_config_name(self, config_name: str | None, context: str) -> str | None:
        """Derive the effective configuration name.

        When the caller passes an explicit ``config_name``, honor it.
        Otherwise:
          - ``interactive`` context consults the user-chosen active
            configuration pointer (``~/ora/data/active-configuration.json``)
            so the Models pane's active-card selection drives dispatch.
            Falls back to the legacy "user-pipeline" default when the
            pointer is missing.
          - ``agent`` / ``autonomous`` keep the legacy mapping
            (``background-default``) — automated processes aren't
            user-steered through the active pointer.

        Returns None when no mapping exists — that signals the caller
        to fall back to the legacy bucket-walk path (vestigial after
        Chunk 2d but kept in place until Chunk 12).
        """
        if config_name is not None:
            return config_name
        if context == "interactive":
            # G1.16 — the active project's profile is an immutable snapshot,
            # not a late read of the mutable preset file.  A malformed/stale
            # binding fails closed instead of silently dropping to the global
            # profile and executing under different authority than the user
            # selected.  Explicit config_name above is the one-run override.
            try:
                from orchestrator import active_project as _ap
                from orchestrator import model_profiles as _mp
                nexus = _ap.get_active_project()
                resolved = _mp.resolve_effective_profile(project_nexus=nexus)
                return resolved["selected"]["runtime_name"]
            except ImportError:
                pass  # compatibility for partial/source-only installations
            try:
                from orchestrator import active_configuration as ac
                return ac.get_active_name()
            except Exception:
                # Defensive: if the pointer module fails for any
                # reason, fall through to the legacy default so chat
                # never breaks because of an active-pointer bug.
                pass
        return DEFAULT_CONFIG_FOR_CONTEXT.get(context)

    def _load_configuration(self, name: str) -> dict | None:
        """Load (and cache) a named configuration from config/configurations/.

        Returns the parsed dict or None if the file is missing or invalid.
        The cache is keyed on name; :meth:`reload` clears it so file edits
        take effect on the next call.
        """
        # G1.16 project bindings use a runtime-only token whose content comes
        # from the authenticated project snapshot.  It is never treated as a
        # filesystem path or accepted from the configuration directory.  It is
        # reauthenticated on every load rather than returned from the ordinary
        # configuration cache, so a stale token cannot survive a rebind.
        try:
            from orchestrator import model_profiles as _mp
            if name.startswith(_mp.LOCK_TOKEN_PREFIX):
                return _mp.load_project_locked_profile(name)
        except ImportError:
            pass

        cached = self._configurations.get(name)
        if cached is not None:
            return cached

        path = self._configuration_path(name)
        if not path.exists():
            if name == "msi-publication":
                raise RuntimeError(
                    f"MSI project-owned routing file does not exist: {path}")
            print(f"[Router] configuration not found: {path}")
            return None

        try:
            with open(path) as f:
                cfg = json.load(f)
        except Exception as exc:
            if name == "msi-publication":
                raise RuntimeError(
                    f"MSI project-owned routing file is invalid: {path}: {exc}"
                ) from exc
            print(f"[Router] failed to load configuration {name}: {exc}")
            return None

        self._configurations[name] = cfg
        return cfg

    def _configuration_path(self, name: str) -> Path:
        # MSI supplies its project-owned named configuration at runtime. This
        # applies only to the explicit MSI name; Ora's own profiles are intact.
        if name == "msi-publication":
            msi_path = os.environ.get("MSI_BACKGROUND_CONFIG_PATH", "").strip()
            msi_name = os.environ.get("MSI_GEAR4_CONFIG_NAME", "").strip()
            if msi_name != "msi-publication" or not msi_path:
                raise RuntimeError(
                    "MSI routing must set MSI_GEAR4_CONFIG_NAME=msi-publication "
                    "and MSI_BACKGROUND_CONFIG_PATH to its project-owned JSON")
            path = Path(msi_path).expanduser()
            if not path.is_file():
                raise RuntimeError(f"MSI routing file is missing: {path}")
            return path
        overlay_names = getattr(
            rp, "RUNTIME_OVERLAY_CONFIGURATION_NAMES", rp.PRESET_NAMES)
        if CONFIGURATIONS_DIR == _DEFAULT_CONFIGURATIONS_DIR and name in overlay_names:
            runtime = rp.configuration_runtime_path(name)
            if runtime.exists():
                return runtime
        return CONFIGURATIONS_DIR / f"{name}.json"

    def _slot_to_cell_path(self, slot: str, gear: int) -> list | None:
        """Map a slot name (plus optional gear) to a cell path inside
        a configuration's ``cells`` dict.

        Returns the list of keys to walk, or None if the slot has no
        cell mapping (caller treats this as "no endpoint available").
        """
        if slot in ("step1_cleanup", "rag_planner", "classification"):
            return ["utility", slot]
        if slot in ("fast", "gear2_rag_lookup"):
            # ``fast 1`` is persisted in two cells by active_configuration:
            # gear3.depth for sequential work and gear2_rag_lookup for the
            # single-pass RAG path. The runtime must resolve the latter
            # directly; aliasing ``fast`` to step1_cleanup silently discarded
            # the selected fast model on browser Gear-2 requests.
            return ["utility", "gear2_rag_lookup"]
        if slot == "sidebar":
            # ``sidebar`` is the project-tool entry point for utility-class
            # calls (small / cheap model). Configurations from auto-populate
            # carry step1_cleanup / classification / rag_planner cells but
            # no ``sidebar`` cell — they're functionally interchangeable.
            # Alias to step1_cleanup so invoke_chat(slot='sidebar') resolves
            # against the same model SMALL points at on the Models pane.
            return ["utility", "step1_cleanup"]
        if slot in ("depth", "breadth"):
            # Gear 1/2 don't have depth/breadth cells in a configuration;
            # the gear downgrade cascade in execute() handles those cases
            # by trying gear 3 first.
            effective_gear = gear if gear >= 3 else 3
            return ["analysis", f"gear{effective_gear}", slot]
        if slot in ("consolidator", "consolidation"):
            return ["post_analysis", "consolidation"]
        if slot in ("evaluator", "verification"):
            return ["post_analysis", "verification"]
        if slot == "formatter":
            return ["post_analysis", "formatter"]
        if slot == "primary":
            # Gear 2 single-pass historically falls through to a workhorse
            # bucket; mirror that by reading the gear3.depth cell.
            return ["analysis", "gear3", "depth"]
        return None

    def get_slot_chain(
        self,
        slot: str,
        gear: int,
        config_name: str | None = None,
    ) -> list[str]:
        """Return the configured fallback chain for a slot.

        Lists the endpoint ids the resolver would walk in order (primary
        + every fallback entry) without actually doing the resolution.
        Empty list when the configuration is unknown, the cell path is
        missing, or the cell is null.

        Used by the run_gear3 refusal path (S11, 2026-05-22) to name
        the specific chain the resolver tried and report each entry's
        circuit-breaker state to the user.
        """
        if not config_name:
            return []
        cfg = self._load_configuration(config_name)
        if cfg is None:
            return []
        cell_path = self._slot_to_cell_path(slot, gear)
        if cell_path is None:
            return []
        cur: object = cfg.get("cells", {})
        for key in cell_path:
            if not isinstance(cur, dict):
                return []
            cur = cur.get(key)
            if cur is None:
                return []
        cur = self._resolve_configuration_cell(cfg, cur)
        if not isinstance(cur, dict):
            return []
        chain: list[str] = []
        primary_id = cur.get("primary")
        if primary_id:
            chain.append(primary_id)
        for fb in cur.get("fallback") or []:
            if fb:
                chain.append(fb)
        return chain

    def _vision_input_chain(self) -> list[str]:
        """The GLOBAL vision-input backstop chain — endpoint ids (preferred
        first) from ``routing-config.json::slots.vision_input``.

        This is the vision-capable model(s) used when an image is present and a
        slot's configured primary/fallback chain would otherwise resolve to an
        image-blind model. It is a single global capability (configured in
        Settings → Visual → Advanced routing), NOT a per-analysis-config choice
        — it superseded the former per-cell ``vision_substitute`` field
        (2026-06-14). Empty list → no global slot configured; the caller falls
        back to a best-effort walk of the slot's own chain.
        """
        slot = (self.config.get("slots") or {}).get("vision_input") or {}
        if not isinstance(slot, dict):
            return []
        out: list[str] = []
        pref = slot.get("preferred")
        if isinstance(pref, str) and pref:
            out.append(pref)
        for fb in (slot.get("fallback") or []):
            if isinstance(fb, str) and fb and fb not in out:
                out.append(fb)
        return out

    def resolve_vision_fallback(
        self,
        slot: str,
        gear: int,
        context: str = "interactive",
        excluded_ids: set | None = None,
        config_name: str | None = None,
        mutex_check: bool = True,
    ) -> dict | None:
        """Resolve the fallback endpoint for a slot on an **image-bearing turn**,
        binding the cell's ``vision_substitute`` across the entire fallback
        chain.

        Used when an image is present and the slot MUST be able to read it. A
        plain fallback walk (``resolve_endpoint`` with ``excluded_ids``) can
        advance into a model that does not actually deliver the image to the
        provider — the breadth-slot defect surfaced by the 2026-06-01
        analytical-repertoire evaluation, where the gear-4 breadth vision
        primary failed and fell back to a model whose service path never
        attaches the image, so the analyst ran blind. A ``vision_capable`` flag
        is not sufficient to trust a chain entry, because image *delivery* is
        per-service (see ``call_api_endpoint``).

        The cell's ``vision_substitute`` is the model the configuration
        explicitly designates for the image case. This method binds it as *the*
        vision fallback for the whole chain:

          * When a ``vision_substitute`` is declared, it is the only fallback
            considered. If it is vision-capable, eligible, and not already in
            ``excluded_ids`` (i.e. not itself the just-failed endpoint), it is
            returned. Otherwise this returns ``None`` so the caller retries the
            current (sighted) endpoint rather than advancing into the generic
            fallback chain — which may carry image-blind entries.
          * When no ``vision_substitute`` is declared (legacy cells), it walks
            primary + fallback[] and returns the first vision-capable eligible
            entry — best effort, never worse than the plain walk.

        Returns a v2 endpoint dict, or ``None`` when no bound vision endpoint is
        available (the caller then reuses the current endpoint, which for a
        vision turn is the vision primary — so it stays sighted rather than
        falling back blind).
        """
        excluded = set(excluded_ids or set())
        chain = self._vision_input_chain()
        if chain:
            # A global vision-input slot is configured — it IS the vision
            # fallback. Try preferred then each fallback; never advance into the
            # generic chain (whose entries may be vision-capable yet image-blind
            # in delivery). An already-excluded (just-failed) or unavailable
            # entry is skipped; when none are eligible, return None so the caller
            # cleanly retries the sighted primary instead of dropping to a blind
            # chain entry.
            for sub_id in chain:
                if sub_id in excluded or not self.vision_capable_for_endpoint(sub_id):
                    continue
                sub_ep = self._endpoints.get(sub_id)
                if (sub_ep and sub_ep.get("enabled", False)
                        and sub_ep.get("status") == "active"):
                    return sub_ep
            return None
        # No global vision-input slot configured — best-effort walk of the
        # configured chain for the first vision-capable eligible entry. Each
        # non-vision hit is added to ``excluded`` so the next resolve_endpoint
        # call advances further down the chain; bounded so it cannot spin.
        chain_len = len(self.get_slot_chain(slot, gear, config_name))
        for _ in range(chain_len + 1):
            ep = self.resolve_endpoint(
                slot, gear, context,
                excluded_ids=excluded,
                config_name=config_name,
                mutex_check=mutex_check,
            )
            if ep is None:
                break
            ep_id = ep.get("id")
            if not ep_id:
                break
            if self.vision_capable_for_endpoint(ep_id):
                return ep
            excluded.add(ep_id)
        return None

    def _resolve_from_configuration(
        self,
        slot: str,
        gear: int,
        config_name: str,
        excluded_ids: set | None = None,
        same_machine_block: str | None = None,
        mutex_check: bool = True,
    ) -> dict | None:
        """Resolve a slot to a v2 endpoint dict using a named configuration.

        Walks the cell's primary + fallback[] in order, applying the same
        per-endpoint filters as the legacy bucket-walk path
        (enabled, status==active, excluded_ids, same_machine_block).

        ``mutex_check``: when True, local endpoints with a busy per-machine
        MLX mutex are skipped in favour of the next chain entry; the first
        busy local is returned only if every other entry is ineligible.
        """
        cfg = self._load_configuration(config_name)
        if cfg is None:
            return None

        cell_path = self._slot_to_cell_path(slot, gear)
        if cell_path is None:
            return None

        cur: object = cfg.get("cells", {})
        for key in cell_path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
            if cur is None:
                return None

        cur = self._resolve_configuration_cell(cfg, cur)
        if not isinstance(cur, dict):
            return None

        primary_id = cur.get("primary")
        fallback_ids = cur.get("fallback") or []
        candidates: list = []
        if primary_id:
            candidates.append(primary_id)
        candidates.extend(fallback_ids)

        excluded_ids = excluded_ids or set()
        first_busy_local: dict | None = None
        for ep_id in candidates:
            if not ep_id:
                continue
            resolved_ep_id = self._resolve_endpoint_id(ep_id)
            ep = self._endpoints.get(resolved_ep_id)
            if not ep:
                # Configured id has no matching endpoint in routing-config.
                # Continue the cascade (this is the publisher's chain — try
                # the next fallback) but log so audits surface drift between
                # the Models pane catalog and the routing-config registry.
                try:
                    print(
                        f"[router] config {config_name!r} slot={slot!r} "
                        f"references unknown endpoint id {ep_id!r} — "
                        f"continuing cascade to next fallback",
                        flush=True,
                    )
                except Exception:
                    pass
                continue
            if not ep.get("enabled", False):
                continue
            if ep.get("status") != "active":
                continue
            if ep_id in excluded_ids or resolved_ep_id in excluded_ids:
                continue
            if same_machine_block and ep.get("type") == "local":
                if ep.get("machine") == same_machine_block:
                    continue

            if mutex_check and ep.get("type") == "local":
                machine_id = ep.get("machine") or DEFAULT_MACHINE_ID
                try:
                    import mlx_mutex
                except ImportError:
                    from orchestrator import mlx_mutex
                if mlx_mutex.is_machine_busy(machine_id):
                    if first_busy_local is None:
                        first_busy_local = ep
                    continue

            # Phase 2b circuit breaker — skip endpoints in cooldown.
            try:
                import endpoint_health
            except ImportError:
                from orchestrator import endpoint_health
            if endpoint_health.is_in_cooldown(resolved_ep_id):
                continue

            return ep

        return first_busy_local

    # ── legacy bucket-walk path ──────────────────────────────────────────

    def _get_bucket_order(self, slot: str, gear: int, context: str) -> list:
        """Get the ordered bucket list for a given slot/gear/context."""
        pipeline = self.config.get("pipelines", {}).get(context, {})

        # Analysis slots: check gear-specific cells
        if slot in ("depth", "breadth"):
            analysis = pipeline.get("analysis", {})
            gear_key = f"gear{gear}" if gear >= 3 else "gear3"  # Gear 2/1 don't have depth/breadth
            gear_config = analysis.get(gear_key, {})

            if gear_config is None:
                # Inherit from gear4 when gear3 is null
                gear_config = analysis.get("gear4", {})

            cell = gear_config.get(slot, {}) if gear_config else {}
            if cell is None:
                # Inherit from the other gear level
                other_gear = "gear4" if gear_key != "gear4" else "gear3"
                other_config = analysis.get(other_gear, {})
                cell = other_config.get(slot, {}) if other_config else {}

            return cell.get("buckets", []) if isinstance(cell, dict) else []

        # Utility slots
        if slot in ("step1_cleanup", "rag_planner", "sidebar", "classification"):
            utility = pipeline.get("utility", {})
            cells = utility.get("cells", {})
            cell_config = cells.get(slot) if cells else None
            if cell_config and isinstance(cell_config, dict):
                return cell_config.get("buckets", [])
            return utility.get("buckets", [])

        # Post-analysis slots
        if slot in ("consolidation", "verification", "consolidator", "evaluator"):
            post = pipeline.get("post_analysis", {})
            cells = post.get("cells", {})
            cell_config = cells.get(slot) if cells else None
            if cell_config and isinstance(cell_config, dict):
                return cell_config.get("buckets", [])
            return post.get("buckets", [])

        # Gear 2 primary: use utility buckets (single model pass)
        if slot == "primary":
            utility = pipeline.get("utility", {})
            # For Gear 2, widen to include analysis-tier buckets
            analysis = pipeline.get("analysis", {})
            g3 = analysis.get("gear3") or analysis.get("gear4", {})
            depth_cell = g3.get("depth", {}) if g3 else {}
            return depth_cell.get("buckets", []) if isinstance(depth_cell, dict) else utility.get("buckets", [])

        return []

    def _to_v1_endpoint(self, ep: dict | None) -> dict | None:
        """Convert a v2 endpoint dict to v1 format compatible with call_model().

        call_model() dispatches on `type` and uses:
          - API: `service`, `model`
          - Local: `url`, `engine`, `model`
          - Browser: `service`, `session_path`
        """
        if not ep:
            return None

        v1 = {
            "name": ep["id"],
            "type": ep.get("type", ""),
            "status": ep.get("status", "active"),
            "training_family": self._training_family(ep),
        }

        if ep["type"] == "local":
            v1["engine"] = ep.get("engine", "mlx")
            v1["model"] = ep.get("model_path", "")
            v1["url"] = ep.get("url", "http://localhost:11434")
            v1["context_window"] = ep.get("context_window", 0)
            v1["ram_required_gb"] = ep.get("ram_resident_gb", 0) + ep.get("ram_overhead_gb", 0)
            v1["model_name"] = ep.get("display_name", "")
            v1["tool_access"] = ep.get("capabilities", {}).get("tool_access", False)
            v1["file_system_access"] = ep.get("capabilities", {}).get("file_system_access", False)
            v1["web_access"] = ep.get("capabilities", {}).get("web_access", False)
            v1["retrieval_approach"] = ep.get("capabilities", {}).get("retrieval_approach", "agentic")

        elif ep["type"] == "api":
            v1["service"] = ep.get("service", "")
            v1["model"] = ep.get("model_id", "")
            v1["dispatch"] = ep.get("dispatch", "")
            # Capacity metadata is part of the resolved endpoint, not a local-
            # only concern. Dropping it made every production API route look
            # like a 32k endpoint to the Dialogue packer; its real completion
            # reserve then consumed that fallback window and continuity fell
            # to zero. ``max_tokens`` is the existing v1 transport field;
            # catalogue-shaped aliases are retained and normalized into it.
            v1["context_window"] = (
                ep.get("context_window")
                or ep.get("context_length")
                or ep.get("max_context_length")
                or 0
            )
            output_cap = (
                ep.get("max_tokens")
                or ep.get("max_output_tokens")
                or ep.get("output_token_limit")
            )
            if isinstance(output_cap, int) and not isinstance(output_cap, bool) \
                    and output_cap > 0:
                v1["max_tokens"] = output_cap
            for key in ("max_output_tokens", "output_token_limit"):
                value = ep.get(key)
                if isinstance(value, int) and not isinstance(value, bool) \
                        and value > 0:
                    v1[key] = value
            v1["tool_access"] = ep.get("capabilities", {}).get("tool_access", False)
            v1["web_access"] = ep.get("capabilities", {}).get("web_access", False)
            v1["retrieval_approach"] = ep.get("capabilities", {}).get("retrieval_approach", "pre-assembled")

        elif ep["type"] == "browser":
            v1["service"] = ep.get("service", "")
            v1["session_path"] = ep.get("session_path", "")
            v1["tool_access"] = ep.get("capabilities", {}).get("tool_access", False)
            v1["web_access"] = ep.get("capabilities", {}).get("web_access", True)
            v1["retrieval_approach"] = ep.get("capabilities", {}).get("retrieval_approach", "pre-assembled")

        return v1

    @staticmethod
    def _training_family(ep: dict | None) -> str:
        """Return confirmed model-family metadata for diversity selection.

        Older catalogue rows carry ``training_family`` explicitly. Newer
        vendor-authoritative direct endpoints sometimes omit it even though their
        canonical provider is known. A direct provider is a valid family boundary;
        a generic transport (notably OpenRouter) is not, because it fronts many
        unrelated model families and must remain unknown.
        """
        if not isinstance(ep, dict):
            return ""
        explicit = str(ep.get("training_family") or "").strip().lower()
        if explicit:
            return explicit
        model = str(
            ep.get("model_id") or ep.get("model") or ep.get("id") or ""
        ).strip().lower()
        if "/" in model:
            model = model.rsplit("/", 1)[-1]
        model_aliases = (
            (("gpt-", "o1", "o3", "o4"), "gpt"),
            (("claude",), "claude"),
            (("gemini",), "gemini"),
            (("qwen",), "qwen"),
            (("glm",), "glm"),
            (("deepseek",), "deepseek"),
            (("minimax",), "minimax"),
            (("kimi", "moonshot"), "kimi"),
            (("grok",), "grok"),
            (("mistral", "codestral", "ministral"), "mistral"),
            (("llama",), "llama"),
        )
        for prefixes, family in model_aliases:
            if model.startswith(prefixes):
                return family
        provider = str(ep.get("provider") or "").strip().lower()
        service = str(ep.get("service") or "").strip().lower()
        candidate = provider or service
        if candidate in {"", "api", "browser", "local", "openrouter"}:
            return ""
        aliases = {
            "openai": "gpt",
            "anthropic": "claude",
            "google": "gemini",
            "xai": "grok",
            "alibaba": "qwen",
            "moonshot": "kimi",
        }
        return aliases.get(candidate, candidate)

    def _generate_warnings(self, assignments: dict, gear: int, context: str) -> list:
        """Generate warnings for a set of assignments."""
        warnings = []

        # Same-provider check for adversarial slots
        if "depth" in assignments and "breadth" in assignments:
            d = assignments["depth"]
            b = assignments["breadth"]

            if d.get("provider") == b.get("provider"):
                if d.get("id") == b.get("id"):
                    warnings.append(Warning(
                        level="caution",
                        category="same_model",
                        message=(
                            f"Depth and breadth are the same model ({d.get('display_name')}). "
                            f"Different system prompts provide structural independence, but "
                            f"shared weights may create blind spots."
                        ),
                        dismissible=True,
                    ))
                else:
                    warnings.append(Warning(
                        level="info",
                        category="same_provider",
                        message=(
                            f"Depth ({d.get('display_name')}) and breadth ({b.get('display_name')}) "
                            f"are from the same provider ({d.get('provider')}). Different providers "
                            f"reduce shared training blind spots."
                        ),
                        dismissible=True,
                    ))

            # Training family check
            if (d.get("training_family") == b.get("training_family")
                    and d.get("id") != b.get("id")):
                warnings.append(Warning(
                    level="info",
                    category="same_family",
                    message=(
                        f"Both models share the {d.get('training_family')} training lineage. "
                        f"Models from different families provide stronger adversarial diversity."
                    ),
                    dismissible=True,
                ))

        # Overkill check for utility slots
        for slot, ep in assignments.items():
            if slot in UTILITY_SLOTS and ep.get("tier") in OVERKILL_TIERS:
                warnings.append(Warning(
                    level="info",
                    category="overkill",
                    message=(
                        f"{ep.get('display_name')} in {slot} slot is overqualified. "
                        f"A smaller model handles this in 2-3 seconds. "
                        f"This model may take 10-15 seconds with no quality benefit."
                    ),
                    slot=slot,
                    dismissible=True,
                ))

        # Underkill check for analysis slots
        for slot, ep in assignments.items():
            if slot in ANALYSIS_SLOTS and ep.get("tier") in UNDERKILL_TIERS:
                warnings.append(Warning(
                    level="caution",
                    category="underkill",
                    message=(
                        f"{ep.get('display_name')} ({ep.get('tier')}) in {slot} slot "
                        f"may not reliably execute the adversarial analysis protocol. "
                        f"Expected: 40B+ local or mid-tier+ commercial."
                    ),
                    slot=slot,
                    dismissible=True,
                ))

        # Swap risk check for local models
        for slot, ep in assignments.items():
            if ep.get("type") != "local":
                continue
            machine_id = ep.get("machine", "")
            machine = self._machines.get(machine_id)
            if not machine:
                continue

            usable = machine.get("usable_gb", 0)
            # Sum all active local models on this machine
            committed = sum(
                e.get("ram_resident_gb", 0) + e.get("ram_overhead_gb", 0)
                for e in self.config.get("endpoints", [])
                if e.get("machine") == machine_id and e.get("enabled") and e.get("type") == "local"
            )
            headroom = usable - committed
            if headroom < 10:
                warnings.append(Warning(
                    level="caution",
                    category="swap_risk",
                    message=(
                        f"Machine {machine.get('display_name')} has only {headroom}GB headroom "
                        f"({committed}GB committed of {usable}GB usable). "
                        f"Swapping may cause latency under load."
                    ),
                    slot=slot,
                    dismissible=True,
                ))
                break  # One warning per machine is enough

        return warnings


def load_router(config_path: str | Path | None = None) -> Router:
    """Convenience function to create a Router from the standard config location."""
    return Router(config_path=config_path)
