"""Capability slot registry (WP-7.0.1).

A *capability slot* is a named role one or more models can fulfill —
``image_generates``, ``image_edits``, ``image_outpaints`` and the rest of
the §11.5 catalog. This module is the runtime registry: it loads the slot
contracts from ``~/ora/config/capabilities.json``, lets providers register
themselves against a slot, validates inbound calls against the slot's
declared contract, and dispatches to the registered handler.

Design notes
------------

* **Generalizes the existing ``vision_extraction`` mechanism.** The Phase 4
  bucket-routing for vision-capable models lives in
  ``boot.route_for_image_input`` and uses
  ``routing_config['vision_extraction']`` plus per-endpoint
  ``vision_capable: true`` flags. This module is the same pattern lifted
  to a generic, named-capability framework: instead of one hard-coded
  ``vision_extraction`` entry, ``capabilities.json`` defines N slots and
  ``routing-config.json``'s ``slots`` block declares preferred + fallback
  per slot.

* **Contract-validated dispatch.** Each slot declares ``required_inputs``,
  ``optional_inputs``, ``output``, ``execution_pattern``, and
  ``common_errors`` (per §11.5 / sibling spec §2). ``invoke()`` rejects
  calls missing required inputs *before* the handler runs, so providers
  never see malformed input. Optional-input defaults are filled in
  automatically.

* **Stub-only in WP-7.0.1.** Provider wiring (DALL-E, Stability,
  Replicate) lives in WP-7.3.2 / WP-7.3.3 / WP-7.3.4. This module ships
  with the registry, the dispatcher, and an empty provider table — the
  test suite registers fakes and exercises the dispatch pathway.

Public API
----------

``CapabilityRegistry(config_path=None, routing_config=None)``
    Loader. Reads ``capabilities.json`` (and optionally
    ``routing-config.json``'s ``slots`` block) and exposes the slot
    catalog.

``registry.list_slots()``                — names of all defined slots.
``registry.get_contract(slot_name)``     — contract dict for one slot.
``registry.register_provider(slot_name, provider_id, handler)``
    Bind a callable that fulfills the slot. ``handler(inputs: dict) -> Any``.
``registry.invoke(slot_name, inputs, provider_id=None)``
    Validate ``inputs`` against the slot's contract; resolve a provider
    (explicit ``provider_id`` overrides routing-config preferred);
    call the handler with the validated input dict; return its result.

Errors are raised as ``CapabilityError`` with a ``code`` matching the
slot's declared ``common_errors`` taxonomy where applicable, or one of
the registry-level codes documented on the exception class.
"""
from __future__ import annotations

import json
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CONFIG_DIR = Path(__file__).parent.parent / "config"
CAPABILITIES_JSON = CONFIG_DIR / "capabilities.json"
ROUTING_CONFIG_JSON = CONFIG_DIR / "routing-config.json"

try:
    from orchestrator import runtime_paths as _runtime_paths
except ImportError:  # flat import context (orchestrator on sys.path)
    try:
        import runtime_paths as _runtime_paths  # type: ignore
    except ImportError:  # pragma: no cover — registry still loads unexpanded
        _runtime_paths = None  # type: ignore


def _read_config_json(path) -> dict:
    """Read a checked-in config file and resolve its ``${ORA_*}``
    placeholders, so a clone at any location reads real paths out of a
    file that carries none. See runtime_paths.expand_placeholders."""
    with open(path) as f:
        loaded = json.load(f)
    if _runtime_paths is None:
        return loaded
    return _runtime_paths.expand_placeholders(loaded)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class CapabilityError(Exception):
    """Raised by the registry on contract violation, missing provider,
    or handler failure.

    ``code`` is one of:
      * Registry-level: ``unknown_slot``, ``missing_required_input``,
        ``unsupported_input_type``, ``no_provider_registered``,
        ``provider_not_found``, ``handler_failed``.
      * Slot-level: any code declared in the slot's ``common_errors``
        list (e.g., ``model_unavailable``, ``no_mask_drawn``).

    ``attempts`` records the provider-fallback chain that led to this
    error when ``invoke()`` walked routing-config's fallback list before
    surfacing the failure. Each entry is the dict shape documented on
    :class:`InvocationResult.attempts`. Empty when the error wasn't
    produced by a fallback-walking ``invoke()`` call.
    """

    def __init__(
        self,
        code: str,
        message: str,
        slot: str | None = None,
        attempts: list[dict] | None = None,
    ):
        self.code = code
        self.slot = slot
        self.attempts = list(attempts) if attempts else []
        super().__init__(f"[{code}] {message}" if not slot else f"[{slot}:{code}] {message}")


# ---------------------------------------------------------------------------
# Result wrappers
# ---------------------------------------------------------------------------

@dataclass
class InvocationResult:
    """Return value from ``registry.invoke()``.

    ``output`` is the handler's return (image bytes, text string, list,
    etc., per the slot's ``output.type``). ``provider_id`` is which
    provider actually answered. ``execution_pattern`` echoes the slot
    contract — async slots return immediately with a job-handle in
    ``output`` (the WP-7.6 async layer interprets this).

    ``attempts`` records the fallback chain that led to this result.
    Each entry is a dict::

        {
            "provider_id": str,        # provider that was tried
            "succeeded": bool,         # True for the final entry on
                                       # successful result; False for
                                       # earlier entries that raised
                                       # a fallback-triggering error.
            "error_code": str | None,  # CapabilityError.code on failure;
                                       # None on the succeeded entry.
            "error_message": str | None,
        }

    For a single-provider success, ``attempts`` has one entry with
    ``succeeded=True``. For a Slot-1 refusal → Slot-2 success, it has
    two entries (the first with ``succeeded=False`` and the slot-level
    refusal code, the second with ``succeeded=True``).
    """
    slot: str
    provider_id: str
    output: Any
    execution_pattern: str
    inputs_used: dict = field(default_factory=dict)
    attempts: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class CapabilityRegistry:
    """Runtime registry of capability slots and their providers."""

    # Input types declared in capabilities.json _input_types. Used as a
    # *light* type sanity check at invocation time — full schema-style
    # validation lives in the parameter-panel UI (WP-7.3.1) and the
    # provider integrations (WP-7.3.2). Here we only catch obvious type
    # mismatches that would otherwise fail mysteriously inside the handler.
    _ACCEPTED_INPUT_TYPES = {
        "text", "image-ref", "image-bytes", "mask", "direction-list",
        "count", "float", "enum", "images-list",
    }

    def __init__(
        self,
        config_path: str | Path | None = None,
        config_dict: dict | None = None,
        routing_config: dict | None = None,
    ):
        """Load the slot catalog.

        Parameters
        ----------
        config_path : str | Path | None
            Path to ``capabilities.json``. Defaults to the standard
            location.
        config_dict : dict | None
            Pre-loaded capabilities dict (takes precedence over file).
            Used in tests.
        routing_config : dict | None
            Optional pre-loaded ``routing-config.json`` dict. When
            present, ``invoke()`` consults its ``slots`` block to pick a
            provider when the caller doesn't specify ``provider_id``.
        """
        if config_dict is not None:
            self.config = config_dict
        else:
            path = Path(config_path) if config_path else CAPABILITIES_JSON
            self.config = _read_config_json(path)

        self._slots: dict[str, dict] = self.config.get("slots", {})
        self._routing_config = routing_config or {}

        # provider_id -> {slot_name -> handler}
        self._providers: dict[str, dict[str, Callable]] = {}
        # slot_name -> [provider_id, ...] in registration order
        self._slot_providers: dict[str, list[str]] = {}

    # --- Catalog ---------------------------------------------------------

    def list_slots(self) -> list[str]:
        """Return all defined slot names in insertion order."""
        return list(self._slots.keys())

    def has_slot(self, slot_name: str) -> bool:
        return slot_name in self._slots

    def get_contract(self, slot_name: str) -> dict:
        """Return the full contract dict for ``slot_name``.

        Raises ``CapabilityError(unknown_slot)`` when the slot doesn't
        exist.
        """
        if slot_name not in self._slots:
            raise CapabilityError(
                "unknown_slot",
                f"No capability slot named '{slot_name}'. Defined slots: "
                f"{', '.join(sorted(self._slots.keys()))}",
            )
        return self._slots[slot_name]

    def required_inputs(self, slot_name: str) -> list[dict]:
        return list(self.get_contract(slot_name).get("required_inputs", []))

    def optional_inputs(self, slot_name: str) -> list[dict]:
        return list(self.get_contract(slot_name).get("optional_inputs", []))

    def execution_pattern(self, slot_name: str) -> str:
        return self.get_contract(slot_name).get("execution_pattern", "sync")

    def common_errors(self, slot_name: str) -> list[dict]:
        return list(self.get_contract(slot_name).get("common_errors", []))

    # --- Provider registration ------------------------------------------

    def register_provider(
        self,
        slot_name: str,
        provider_id: str,
        handler: Callable[[dict], Any],
    ) -> None:
        """Bind ``handler`` to fulfill ``slot_name`` for ``provider_id``.

        ``handler(inputs: dict) -> output`` is invoked at dispatch time
        with the validated + default-filled input dict. The handler's
        return value becomes the slot's ``output``.

        Raises ``CapabilityError(unknown_slot)`` if the slot is not
        defined in ``capabilities.json``.
        """
        if slot_name not in self._slots:
            raise CapabilityError(
                "unknown_slot",
                f"Cannot register provider '{provider_id}' against undefined "
                f"slot '{slot_name}'. Add the slot to capabilities.json first.",
            )

        if not callable(handler):
            raise CapabilityError(
                "handler_failed",
                f"Handler for slot '{slot_name}', provider '{provider_id}' "
                f"is not callable (got {type(handler).__name__}).",
                slot=slot_name,
            )

        self._providers.setdefault(provider_id, {})[slot_name] = handler
        self._slot_providers.setdefault(slot_name, [])
        if provider_id not in self._slot_providers[slot_name]:
            self._slot_providers[slot_name].append(provider_id)

    def providers_for(self, slot_name: str) -> list[str]:
        """Return registered provider ids for ``slot_name`` in
        registration order."""
        return list(self._slot_providers.get(slot_name, []))

    def has_provider(self, slot_name: str, provider_id: str) -> bool:
        return provider_id in self._providers and slot_name in self._providers[provider_id]

    # --- Dispatch -------------------------------------------------------

    def resolve_provider(self, slot_name: str) -> str | None:
        """Pick the provider id for ``slot_name`` using routing-config.

        Returns the first entry of :meth:`resolve_provider_chain` — i.e.
        the preferred provider if registered, else the first registered
        fallback, else the first registered provider, else ``None``.
        Kept for back-compat with callers that just want "which provider
        will be tried first."
        """
        chain = self.resolve_provider_chain(slot_name)
        return chain[0] if chain else None

    def resolve_provider_chain(self, slot_name: str) -> list[str]:
        """Build the ordered provider chain for ``slot_name``.

        Returns ``[preferred, *fallback_in_order]``, restricted to
        providers actually registered against the slot (unregistered ids
        in routing-config are silently skipped — the slot stays visible
        with whatever providers ARE present). When the routing-config
        names no providers (or names none that are registered), falls
        back to the list of registered providers in insertion order so
        stub tests work with no routing-config.

        Deduplicated: if ``preferred`` also appears in ``fallback``, it
        only shows up once (at the preferred position).

        This is the chain :meth:`invoke` walks when a fallback-triggering
        ``CapabilityError`` comes back from an earlier entry.
        """
        slots_cfg = (self._routing_config or {}).get("slots", {}) or {}
        slot_cfg = slots_cfg.get(slot_name) or {}

        seen: set[str] = set()
        chain: list[str] = []

        preferred = slot_cfg.get("preferred")
        if preferred and self.has_provider(slot_name, preferred):
            chain.append(preferred)
            seen.add(preferred)

        for fb in slot_cfg.get("fallback", []) or []:
            if fb in seen:
                continue
            if self.has_provider(slot_name, fb):
                chain.append(fb)
                seen.add(fb)

        if chain:
            return chain

        # Nothing in routing-config matched — fall back to the registered
        # providers in insertion order so stub tests work with no
        # routing-config.
        return list(self.providers_for(slot_name))

    # Default set of slot-level error codes that signal "the next
    # provider might succeed where this one didn't." Per-slot
    # ``routing-config.json[slots][<name>][fallback_on]`` overrides this.
    _DEFAULT_FALLBACK_TRIGGERING_CODES: frozenset[str] = frozenset({
        "prompt_rejected",
        "model_unavailable",
        "quota_exceeded",
    })

    def fallback_triggering_codes(self, slot_name: str) -> frozenset[str]:
        """Return the set of CapabilityError codes that cause
        :meth:`invoke` to advance to the next provider in the chain.

        Per-slot override: ``routing-config.json``'s
        ``slots[<name>].fallback_on`` field. Missing/None → default set.
        Explicit empty list ``[]`` → fail-fast (no fallback for that
        slot, even on the default codes — useful for ``video_generates``
        / ``style_trains`` where a silent retry would double-charge).
        """
        slots_cfg = (self._routing_config or {}).get("slots", {}) or {}
        slot_cfg = slots_cfg.get(slot_name) or {}
        override = slot_cfg.get("fallback_on")
        if override is None:
            return self._DEFAULT_FALLBACK_TRIGGERING_CODES
        # An explicit empty list disables fallback for this slot entirely.
        return frozenset(str(code) for code in override)

    def invoke(
        self,
        slot_name: str,
        inputs: dict,
        provider_id: str | None = None,
    ) -> InvocationResult:
        """Dispatch ``inputs`` to the slot's handler, walking the
        routing-config provider chain on fallback-triggering errors.

        Validates ``inputs`` against the slot's contract, fills in
        defaults for unsupplied optional inputs, builds the provider
        chain (preferred → fallback in order), and calls the first
        provider's handler. If that handler raises a ``CapabilityError``
        whose ``code`` is in :meth:`fallback_triggering_codes` for this
        slot, advances to the next provider in the chain. Repeats until
        a provider succeeds or the chain is exhausted.

        ``InvocationResult.attempts`` records every provider tried,
        marked succeeded / failed with the slot-level error code.
        When the chain is exhausted, raises the **last** error with
        ``.attempts`` populated, so the caller can surface the chain
        (e.g., "Slot 1 refused for content_policy → Slot 2 unavailable
        → no providers left").

        When ``provider_id`` is given explicitly, fallback is disabled —
        the caller is making a deliberate provider choice and any error
        is surfaced verbatim. Non-fallback-triggering errors (input
        validation, ``handler_failed``, etc.) are also raised verbatim
        without trying the next provider.
        """
        contract = self.get_contract(slot_name)

        if not isinstance(inputs, dict):
            raise CapabilityError(
                "missing_required_input",
                f"Slot '{slot_name}' invoked with non-dict inputs "
                f"(got {type(inputs).__name__}).",
                slot=slot_name,
            )

        # Validate required inputs.
        validated = dict(inputs)
        for spec in contract.get("required_inputs", []):
            field_name = spec["name"]
            if field_name not in validated or validated[field_name] is None:
                raise CapabilityError(
                    "missing_required_input",
                    f"Slot '{slot_name}' requires input '{field_name}' "
                    f"({spec.get('type', 'unknown')}): "
                    f"{spec.get('description', '')}",
                    slot=slot_name,
                )

            # Light type check on declared types.
            declared_type = spec.get("type")
            if declared_type and declared_type not in self._ACCEPTED_INPUT_TYPES:
                raise CapabilityError(
                    "unsupported_input_type",
                    f"Slot '{slot_name}' declares unsupported input type "
                    f"'{declared_type}' for '{field_name}'.",
                    slot=slot_name,
                )

        # Fill in defaults for optional inputs.
        for spec in contract.get("optional_inputs", []):
            field_name = spec["name"]
            if field_name not in validated:
                if "default" in spec:
                    validated[field_name] = spec["default"]

        # Build the provider chain. Explicit provider_id disables
        # fallback — the caller is asking for that exact provider.
        if provider_id is not None:
            if not self.has_provider(slot_name, provider_id):
                raise CapabilityError(
                    "provider_not_found",
                    f"Provider '{provider_id}' is not registered against "
                    f"slot '{slot_name}'. Registered: "
                    f"{', '.join(self.providers_for(slot_name)) or 'none'}",
                    slot=slot_name,
                )
            chain = [provider_id]
        else:
            chain = self.resolve_provider_chain(slot_name)

        if not chain:
            raise CapabilityError(
                "no_provider_registered",
                f"No provider is registered for slot '{slot_name}'. "
                f"Configure a model in Settings → or register a stub.",
                slot=slot_name,
            )

        triggering = self.fallback_triggering_codes(slot_name)
        attempts: list[dict] = []
        last_exc: CapabilityError | None = None

        for idx, candidate in enumerate(chain):
            handler = self._providers[candidate][slot_name]
            try:
                output = handler(validated)
            except CapabilityError as exc:
                attempts.append({
                    "provider_id": candidate,
                    "succeeded": False,
                    "error_code": exc.code,
                    "error_message": str(exc),
                })
                last_exc = exc
                # Only advance to the next provider when (a) fallback is
                # enabled (chain length > 1 from routing-config OR no
                # explicit provider_id) and (b) the error is in the
                # triggering set. Explicit-provider_id chains have
                # length 1 so this loop naturally terminates after the
                # first attempt.
                if exc.code in triggering and idx + 1 < len(chain):
                    continue
                # No more providers to try, or non-triggering error.
                break
            except Exception as exc:  # pragma: no cover — surfaced as handler_failed
                wrapped = CapabilityError(
                    "handler_failed",
                    f"Provider '{candidate}' raised an unhandled exception "
                    f"while fulfilling slot '{slot_name}': {exc}",
                    slot=slot_name,
                )
                attempts.append({
                    "provider_id": candidate,
                    "succeeded": False,
                    "error_code": "handler_failed",
                    "error_message": str(wrapped),
                })
                last_exc = wrapped
                # handler_failed is NOT in the default triggering set, so
                # this normally terminates the chain. If an operator has
                # opted handler_failed in via fallback_on, honor that.
                if "handler_failed" in triggering and idx + 1 < len(chain):
                    continue
                break
            else:
                # Success — record and return.
                attempts.append({
                    "provider_id": candidate,
                    "succeeded": True,
                    "error_code": None,
                    "error_message": None,
                })
                self._record_tool_event(slot_name, candidate, attempts, True)
                return InvocationResult(
                    slot=slot_name,
                    provider_id=candidate,
                    output=output,
                    execution_pattern=contract.get("execution_pattern", "sync"),
                    inputs_used=validated,
                    attempts=attempts,
                )

        # Chain exhausted (or terminated on a non-triggering error).
        # Re-raise the last error tagged with the full attempts chain
        # so the caller can render "tried X, then Y, then Z" telemetry.
        assert last_exc is not None  # the loop only exits via break
        last_exc.attempts = attempts
        self._record_tool_event(slot_name, None, attempts, False)
        raise last_exc

    @staticmethod
    def _record_tool_event(slot_name: str, provider_id: str | None,
                           attempts: list[dict], ok: bool) -> None:
        """Execution Review Phase 1: one tool-event per slot invocation —
        the seam where external image/video APIs actually execute. Slots
        are declared, contract-validated actions; their classification is
        CAPABILITY_SLOT_AXES (external egress, recoverable local artifact),
        with per-slot overrides possible in the manifest. Unregistered slot
        names never reach here (get_contract raises)."""
        try:
            try:
                import tool_events as _te
            except ImportError:
                from orchestrator import tool_events as _te
            axes = _te.CAPABILITY_SLOT_AXES
            _te.record({
                "event": "capability_slot",
                "action": f"capability_slot:{slot_name}",
                "category": axes["category"], "mutability": axes["mutability"],
                "sensitivity": axes["sensitivity"], "egress": axes["egress"],
                "mutated": ok,
                "args_redacted": {"provider": provider_id or "",
                                  "attempts": [a.get("provider_id")
                                               for a in attempts]},
                "exit": {"ok": ok,
                         "reason": "" if ok else
                         (attempts[-1].get("error_code") or "")[:120]},
                "gate": {"decision": "allowed",
                         "why": "declared capability slot"},
                "enforcement_model": axes["enforcement"],
            })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

def resolve_slot_inheritance(routing_config: dict) -> dict:
    """Materialize ``inherits`` / ``append_fallback`` / ``prepend_fallback``
    / ``exclude_inherited`` directives in routing-config.json so every slot
    ends up with a fully explicit ``preferred`` + ``fallback`` list.

    Directives may be declared in either the publisher's
    ``routing-config.json::slots`` or in a project's manifest under
    ``capability_slots[].routing`` (the project's directives are merged
    into the in-memory routing config by
    :func:`merge_project_capability_slots` before this resolver runs).

    Per-slot directives::

      "some_slot": {
        "inherits": "parent_slot",
        "append_fallback": ["extra-provider"]
      }

    becomes, after resolution::

      "some_slot": {
        "preferred": "<whatever parent_slot.preferred is>",
        "fallback": [...parent_slot.fallback..., "extra-provider"]
      }

    Rules:
      * ``inherits`` names the parent slot to copy ``preferred`` +
        ``fallback`` from.
      * ``preferred`` declared on the child wins over the parent's.
      * ``fallback`` declared on the child replaces the parent's wholesale
        (so a child can opt out of the parent's chain entirely).
      * ``exclude_inherited`` filters the parent's chain — any provider
        whose id is in this list is dropped before prepend/append apply,
        and if the parent's preferred is in the list, the child's
        effective preferred falls through to whatever the prepend/append
        layers supply.
      * ``prepend_fallback`` / ``append_fallback`` are *additive* to the
        effective (post-inheritance) ``fallback`` list, in order
        prepend → inherited → append. Neither is filtered by
        ``exclude_inherited`` — the child explicitly added them.
      * Inheritance is single-level (no transitive resolution); cycles
        and missing parents are silent no-ops so a malformed config can't
        brick the whole registry.
      * Non-slot directives (``_note``, etc.) on the child are preserved.

    Mutates ``routing_config`` in place AND returns it for convenience.
    """
    if not isinstance(routing_config, dict):
        return routing_config
    slots = routing_config.get("slots")
    if not isinstance(slots, dict):
        return routing_config

    for child_name, child_cfg in list(slots.items()):
        if not isinstance(child_cfg, dict):
            continue
        parent_name = child_cfg.get("inherits")
        prepend = list(child_cfg.get("prepend_fallback", []) or [])
        append = list(child_cfg.get("append_fallback", []) or [])
        exclude = set(child_cfg.get("exclude_inherited", []) or [])
        if not parent_name and not prepend and not append:
            continue

        parent_cfg = slots.get(parent_name) if parent_name else None
        if parent_name and not isinstance(parent_cfg, dict):
            parent_cfg = {}

        # preferred: child's wins; else inherit parent's (unless excluded).
        # If the parent's preferred is in the exclusion list, fall through
        # to whatever the child's prepend/append/inherited-fallback supplies.
        effective_preferred = child_cfg.get("preferred")
        if effective_preferred is None and isinstance(parent_cfg, dict):
            parent_preferred = parent_cfg.get("preferred")
            if parent_preferred and parent_preferred not in exclude:
                effective_preferred = parent_preferred

        # fallback: child's explicit replaces; else inherit parent's
        # (filtered through the exclusion list)
        if "fallback" in child_cfg:
            inherited_fallback = list(child_cfg.get("fallback") or [])
        elif isinstance(parent_cfg, dict):
            inherited_fallback = [
                pid for pid in (parent_cfg.get("fallback") or [])
                if pid not in exclude
            ]
        else:
            inherited_fallback = []

        # Compose: prepend → inherited → append, deduplicated in order.
        # prepend and append are NOT filtered by exclude — those are
        # explicitly added by the child, so the child meant them.
        composed: list[str] = []
        seen: set[str] = set()
        for pid in (*prepend, *inherited_fallback, *append):
            if pid in seen:
                continue
            composed.append(pid)
            seen.add(pid)

        child_cfg["preferred"] = effective_preferred
        child_cfg["fallback"] = composed
        child_cfg.pop("inherits", None)
        child_cfg.pop("prepend_fallback", None)
        child_cfg.pop("append_fallback", None)
        child_cfg.pop("exclude_inherited", None)

    return routing_config


def merge_project_capability_slots(
    capabilities: dict,
    routing_config: dict | None,
    projects: list,
) -> None:
    """Merge project-declared `capability_slots` into the core capability
    catalog and the in-memory routing config (Plugin Convention §12).

    Mutates ``capabilities['slots']`` and ``routing_config['slots']`` in
    place. ``projects`` is an iterable of :class:`project_registry.Project`
    instances (typed loosely to avoid a hard import dependency at call sites).

    Collision rules (§"Collision rules"):
      * **Project shadows core** — a project declares a slot name that
        also exists in core ``capabilities.json``. Allowed: project's
        contract + routing replaces core's. Info-level diagnostic.
      * **Project shadows project** — two registered projects declare the
        same slot name. Hard error at load: the slot is dropped from all
        of them, with a clear diagnostic naming each project. Operator
        decides which project to unregister.

    Publisher override (§"Publisher override"): when a project's `routing`
    block is present, it is merged into ``routing_config['slots']`` only
    if no entry already exists there. The publisher's
    ``routing-config.json`` was loaded before this merge runs, so its
    entries are already present — and therefore win. A diagnostic is
    emitted when a project's routing is overridden by the publisher.
    """
    slots_catalog = capabilities.setdefault("slots", {})
    routing_slots = None
    if routing_config is not None:
        routing_slots = routing_config.setdefault("slots", {})

    # Pass 1: detect project-shadows-project collisions across all projects.
    seen_by_project: dict[str, list[str]] = {}
    for project in projects:
        for slot_name in getattr(project, "capability_slots", {}):
            seen_by_project.setdefault(slot_name, []).append(project.nexus)
    collided: set[str] = {name for name, nexuses in seen_by_project.items() if len(nexuses) > 1}
    for slot_name in sorted(collided):
        print(
            f"[capability_registry] Slot '{slot_name}' is declared by multiple "
            f"projects ({seen_by_project[slot_name]}); dropping from all of them. "
            f"Unregister one of the projects to resolve the collision."
        )

    # Pass 2: merge non-collided slots from each project, in nexus order
    # (matches list_projects's sorted order so diagnostics are deterministic).
    for project in projects:
        for slot_name, slot in getattr(project, "capability_slots", {}).items():
            if slot_name in collided:
                continue
            if slot_name in slots_catalog:
                print(
                    f"[capability_registry] Project '{project.nexus}' shadows "
                    f"core slot '{slot_name}' (project's contract + routing wins)"
                )
            slots_catalog[slot_name] = dict(slot.contract)
            if routing_slots is None or not slot.routing:
                continue
            if slot_name in routing_slots:
                print(
                    f"[capability_registry] Project '{project.nexus}' routing for "
                    f"slot '{slot_name}' overridden by publisher's "
                    f"routing-config.json::slots entry"
                )
                continue
            routing_slots[slot_name] = dict(slot.routing)


def load_registry(
    config_path: str | Path | None = None,
    routing_config_path: str | Path | None = None,
    pointer_dir: str | None = None,
) -> CapabilityRegistry:
    """Load a CapabilityRegistry from the standard config locations.

    ``routing_config_path`` is consulted for the ``slots`` block;
    omitting it disables preferred/fallback resolution and the registry
    falls back to first-registered-provider order in
    ``resolve_provider``.

    Project-declared ``capability_slots`` (Plugin Convention §12) are
    merged into the core catalog and the in-memory routing config via
    :func:`merge_project_capability_slots` before inheritance resolution
    runs. The merge is silent when no projects are registered or none of
    them declare slots — so this path is a no-op for forks that don't use
    the project plugin mechanism.

    Slot-inheritance directives (``inherits`` / ``prepend_fallback`` /
    ``append_fallback``) are resolved at load time via
    :func:`resolve_slot_inheritance` so the registry only sees fully
    materialized ``preferred`` + ``fallback`` lists.
    """
    # 1. Load core capabilities.json into a dict we can mutate.
    cap_path = Path(config_path) if config_path else CAPABILITIES_JSON
    capabilities = _read_config_json(cap_path)

    # 2. Load publisher routing-config.json (publisher's preferences).
    #
    #    Resolve through runtime_paths like every other reader/writer of
    #    this file: the Visual pane's /config/routing/slots endpoints and
    #    boot's chat Router use the runtime overlay
    #    (data/runtime/config/routing-config.json) when it exists.
    #    Before 2026-07-01 this hardcoded the SEED config, so capability
    #    dispatch and the pane read DIFFERENT files — nothing saved in
    #    the Visual tab ever reached actual image/video routing.
    routing_config = None
    rc_default = ROUTING_CONFIG_JSON
    if routing_config_path is None:
        try:
            from orchestrator import runtime_paths as _rp
        except ImportError:  # flat import context (orchestrator on sys.path)
            try:
                import runtime_paths as _rp  # type: ignore
            except ImportError:
                _rp = None
        if _rp is not None:
            try:
                rc_default = _rp.routing_config_path()
            except Exception:
                rc_default = ROUTING_CONFIG_JSON
    if routing_config_path is not None or Path(rc_default).exists():
        rc_path = Path(routing_config_path) if routing_config_path else Path(rc_default)
        try:
            routing_config = _read_config_json(rc_path)
        except Exception:
            routing_config = None

    # 2b. Materialize seed defaults into all-empty slots. An overlay slot
    #     with preferred=null and fallback=[] (e.g. cleared in the pane,
    #     or nulled by the pre-2026-07-01 non-hermetic endpoint test)
    #     used to silently dispatch in provider-registration order —
    #     an accidental, undocumented chain. Treat "all-empty" as "use
    #     the shipped default" instead: copy preferred/fallback from the
    #     seed config so behavior is the documented default chain.
    #     In-memory only — the overlay file is not rewritten. Applies
    #     only on DEFAULT path resolution: a caller passing an explicit
    #     routing_config_path (tests, project sandboxes) controls its
    #     config completely and gets no seed injection.
    if (routing_config is not None and routing_config_path is None
            and ROUTING_CONFIG_JSON.exists()):
        try:
            _rc_resolved = Path(rc_default)
            if _rc_resolved.resolve() != ROUTING_CONFIG_JSON.resolve():
                with open(ROUTING_CONFIG_JSON) as f:
                    _seed_slots = (json.load(f) or {}).get("slots") or {}
                _live_slots = routing_config.setdefault("slots", {})
                for _name, _seed_cfg in _seed_slots.items():
                    if not isinstance(_seed_cfg, dict):
                        continue
                    if not (_seed_cfg.get("preferred") or _seed_cfg.get("fallback")):
                        continue  # seed itself has no chain for this slot
                    _cur = _live_slots.get(_name)
                    if _cur is None:
                        _live_slots[_name] = dict(_seed_cfg)
                    elif (isinstance(_cur, dict)
                          and not _cur.get("preferred")
                          and not _cur.get("fallback")
                          and not _cur.get("inherits")):
                        _merged = dict(_cur)
                        _merged["preferred"] = _seed_cfg.get("preferred")
                        _merged["fallback"] = list(_seed_cfg.get("fallback") or [])
                        _live_slots[_name] = _merged
        except Exception:
            pass  # defaults are best-effort; never block registry load

    # 3. Merge project-declared capability_slots (Plugin Convention §12).
    #    Defensive: if project_registry isn't importable for any reason,
    #    skip silently so the registry still loads.
    try:
        from orchestrator.project_registry import list_projects as _list_projects
        projects = (
            _list_projects(pointer_dir=pointer_dir)
            if pointer_dir is not None
            else _list_projects()
        )
    except Exception:
        projects = []
    if projects and any(getattr(p, "capability_slots", None) for p in projects):
        if routing_config is None:
            routing_config = {"slots": {}}
        merge_project_capability_slots(capabilities, routing_config, projects)

    # 4. Resolve inheritance directives over the merged routing config.
    if routing_config is not None:
        resolve_slot_inheritance(routing_config)

    # 5. Construct the registry from the merged data.
    registry = CapabilityRegistry(
        config_dict=capabilities, routing_config=routing_config,
    )

    # Local-first default: auto-register the offline diffusers provider
    # so every route gets it without per-route imports. Defensive — if
    # the integration module isn't on the path, or its dependencies
    # aren't installed, we silently skip and the resolver falls through
    # to whatever API providers each route registers explicitly.
    try:
        import sys as _sys
        _integrations_dir = str(CONFIG_DIR.parent / "orchestrator" / "integrations")
        if _integrations_dir not in _sys.path:
            _sys.path.insert(0, _integrations_dir)
        import local_diffusers as _local_diffusers
        _local_diffusers.register(registry)
    except Exception:
        pass

    return registry


def _register_image_generation_providers(registry: CapabilityRegistry) -> None:
    """Register every production provider for the image-generation slot.

    ``load_registry`` already installs the optional local provider.  The API
    providers are kept lazy so importing the registry never requires their
    SDKs or credentials.  Registration itself performs no provider call.
    """
    for module_name in ("openai_images", "gemini_images", "openrouter_images"):
        try:
            module = __import__(module_name)
            module.register(registry)
        except Exception:
            # A missing optional SDK removes only that provider from the
            # configured chain. ``invoke`` fails loudly when none remain.
            continue


def _generated_image_format(data: bytes) -> tuple[str, str]:
    """Verify provider output is a real raster image and return MIME/suffix."""
    signatures = (
        (data.startswith(b"\x89PNG\r\n\x1a\n"), "image/png", "png"),
        (data.startswith(b"\xff\xd8\xff"), "image/jpeg", "jpg"),
        (data.startswith((b"GIF87a", b"GIF89a")), "image/gif", "gif"),
        (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
         "image/webp", "webp"),
        (len(data) >= 12 and data[4:8] == b"ftyp"
         and data[8:12] in (b"avif", b"avis"), "image/avif", "avif"),
    )
    detected = next(((mime, suffix) for matches, mime, suffix in signatures if matches), None)
    if detected is None:
        raise CapabilityError(
            "handler_failed",
            "The image provider returned bytes that are not a supported image.",
            slot="image_generates",
        )
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except ImportError:
        # Signature validation remains available in minimal installations.
        pass
    except Exception as exc:
        raise CapabilityError(
            "handler_failed",
            f"The image provider returned an unreadable image: {exc}",
            slot="image_generates",
        ) from exc
    return detected


def invoke_image_generation(
    inputs: dict,
    *,
    provider_id: str | None = None,
) -> tuple[InvocationResult, bytes, str, str]:
    """Invoke the production image slot with its canonical routing semantics.

    An explicit ``provider_id`` is passed straight to ``CapabilityRegistry``
    and therefore disables fallback.  Omitting it uses the saved preferred
    and fallback chain.  Mock or placeholder providers/results are rejected
    even if they contain valid image bytes.
    """
    registry = load_registry()
    _register_image_generation_providers(registry)
    result = registry.invoke("image_generates", inputs, provider_id=provider_id)
    output = result.output
    provider = str(result.provider_id or "")
    provider_marker = provider.strip().lower()
    if (provider_marker in {"mock", "placeholder"}
            or provider_marker.startswith(
                ("mock-", "mock:", "placeholder-", "placeholder:")
            )
            or (isinstance(output, dict)
                and any(
                    output.get(key) is True
                    for key in ("mock", "mocked", "placeholder")
                ))):
        raise CapabilityError(
            "handler_failed",
            "Mock or placeholder image output cannot satisfy image generation.",
            slot="image_generates",
            attempts=result.attempts,
        )
    if not isinstance(output, (bytes, bytearray)):
        raise CapabilityError(
            "handler_failed",
            "The image provider did not return image bytes.",
            slot="image_generates",
            attempts=result.attempts,
        )
    image_bytes = bytes(output)
    mime_type, suffix = _generated_image_format(image_bytes)
    return result, image_bytes, mime_type, suffix


def resolve_image_provider_override(
    requested: str | None,
    model_profile_locks: dict | None,
) -> str | None:
    """Apply the active project's image lock without silent substitution."""
    override = str(requested or "").strip() or None
    locked = (model_profile_locks or {}).get("image_model")
    locked = str(locked).strip() if isinstance(locked, str) else ""
    if locked:
        if override is not None and override != locked:
            raise CapabilityError(
                "model_profile_image_lock_conflict",
                f"The active project's Model Profile locks image generation to {locked!r}.",
                slot="image_generates",
            )
        return locked
    return override
