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

CONFIG_DIR = Path(__file__).parent.parent / "config"
ROUTING_CONFIG_PATH = CONFIG_DIR / "routing-config.json"
CONFIGURATIONS_DIR = CONFIG_DIR / "configurations"

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
        if config_dict:
            self.config = config_dict
        else:
            self._config_path = Path(config_path) if config_path else ROUTING_CONFIG_PATH
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
        self._machines = {m["id"]: m for m in self.config.get("machines", [])}
        self._buckets = self.config.get("buckets", {})
        self._diversity = (self.config.get("diversity") or {}).get("enabled", False)
        # Named-configuration cache (Chunk 2b). Cleared on reload so file
        # edits to config/configurations/*.json take effect on next call.
        self._configurations: dict = {}
        # models.json vision_capable lookup cache (Chunk 2e). Cleared on
        # reload so edits to models.json also take effect immediately.
        self._vision_lookup_cache = None

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

                return ep

        return first_busy_local

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
        """
        slots = GEAR_SLOTS.get(gear, [])
        assignments = {}

        for slot in slots:
            same_machine_block = None

            # For Gear 4: apply MLX parallel constraint
            if gear == 4 and slot == "breadth" and "depth" in assignments:
                depth_ep = assignments["depth"]
                if depth_ep.get("type") == "local":
                    same_machine_block = depth_ep.get("machine")

            # For breadth slot: prefer a different model than depth for diversity
            if slot == "breadth" and "depth" in assignments:
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

                # Check parallel safety for Gear 4
                if gear == 4:
                    depth = assignments.get("depth", {})
                    breadth = assignments.get("breadth", {})
                    both_local = (depth.get("type") == "local" and
                                  breadth.get("type") == "local")
                    same_machine = (depth.get("machine") == breadth.get("machine"))
                    result.parallel_safe = not (both_local and same_machine)
                    # Verification escape hatch: ORA_FORCE_GEAR4_PARALLEL=1
                    # bypasses the same-machine MLX block. Use only when
                    # you've confirmed the two local models fit in RAM
                    # simultaneously (e.g. M4 Max 128GB with the 70/72B pair).
                    import os as _os
                    if _os.environ.get("ORA_FORCE_GEAR4_PARALLEL") == "1":
                        result.parallel_safe = True

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

    def get_status(self) -> dict:
        """Get current system status: what would happen for each context and gear."""
        status = {
            "interactive": {},
            "agent": {},
        }

        for context in ["interactive", "agent"]:
            for gear in [4, 3, 2, 1]:
                routing = self.execute(gear, context)
                status[context][f"gear{gear}"] = {
                    "achievable": routing.gear == gear,
                    "effective_gear": routing.gear,
                    "assignments": {
                        slot: {
                            "id": ep.get("name", "?"),
                            "display_name": self._endpoints.get(
                                ep.get("name", ""), {}
                            ).get("display_name", ep.get("name", "?")),
                            "tier": self._endpoints.get(
                                ep.get("name", ""), {}
                            ).get("tier", "?"),
                        }
                        for slot, ep in routing.assignments.items()
                    },
                    "parallel_safe": routing.parallel_safe,
                    "warnings": [
                        {"level": w.level, "category": w.category, "message": w.message}
                        for w in routing.warnings
                    ],
                }

            # Utility resolution
            for slot in ["step1_cleanup", "rag_planner"]:
                ep = self.resolve_utility_slot(slot, context)
                ep_id = ep["id"] if ep else None
                status[context][slot] = {
                    "id": ep_id,
                    "display_name": ep.get("display_name", "?") if ep else "none",
                    "tier": ep.get("tier", "?") if ep else "none",
                }

        # Endpoint health
        status["endpoints"] = []
        for ep in self.config.get("endpoints", []):
            status["endpoints"].append({
                "id": ep["id"],
                "display_name": ep.get("display_name", ep["id"]),
                "type": ep.get("type"),
                "tier": ep.get("tier"),
                "status": ep.get("status"),
                "enabled": ep.get("enabled"),
                "machine": ep.get("machine", ""),
            })

        # Machine status
        status["machines"] = []
        for m in self.config.get("machines", []):
            # Calculate committed RAM
            committed = sum(
                ep.get("ram_resident_gb", 0) + ep.get("ram_overhead_gb", 0)
                for ep in self.config.get("endpoints", [])
                if ep.get("machine") == m["id"] and ep.get("enabled") and ep.get("type") == "local"
            )
            status["machines"].append({
                "id": m["id"],
                "display_name": m.get("display_name", m["id"]),
                "ram_gb": m.get("ram_gb", 0),
                "usable_gb": m.get("usable_gb", 0),
                "committed_gb": committed,
                "remaining_gb": m.get("usable_gb", 0) - committed,
                "role": m.get("role", ""),
                "status": m.get("status", "unknown"),
            })

        return status

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

        When the caller passes an explicit ``config_name``, honor it. Otherwise
        map the legacy ``context`` vocabulary through DEFAULT_CONFIG_FOR_CONTEXT.
        Returns None when no mapping exists — that signals the caller to fall
        back to the legacy bucket-walk path (vestigial after Chunk 2d but kept
        in place until Chunk 12).
        """
        if config_name is not None:
            return config_name
        return DEFAULT_CONFIG_FOR_CONTEXT.get(context)

    def _load_configuration(self, name: str) -> dict | None:
        """Load (and cache) a named configuration from config/configurations/.

        Returns the parsed dict or None if the file is missing or invalid.
        The cache is keyed on name; :meth:`reload` clears it so file edits
        take effect on the next call.
        """
        cached = self._configurations.get(name)
        if cached is not None:
            return cached

        path = CONFIGURATIONS_DIR / f"{name}.json"
        if not path.exists():
            print(f"[Router] configuration not found: {path}")
            return None

        try:
            with open(path) as f:
                cfg = json.load(f)
        except Exception as exc:
            print(f"[Router] failed to load configuration {name}: {exc}")
            return None

        self._configurations[name] = cfg
        return cfg

    def _slot_to_cell_path(self, slot: str, gear: int) -> list | None:
        """Map a slot name (plus optional gear) to a cell path inside
        a configuration's ``cells`` dict.

        Returns the list of keys to walk, or None if the slot has no
        cell mapping (caller treats this as "no endpoint available").
        """
        if slot in ("sidebar", "step1_cleanup", "rag_planner", "classification"):
            return ["utility", slot]
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
            ep = self._endpoints.get(ep_id)
            if not ep:
                continue
            if not ep.get("enabled", False):
                continue
            if ep.get("status") != "active":
                continue
            if ep_id in excluded_ids:
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
