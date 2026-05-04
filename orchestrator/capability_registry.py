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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CONFIG_DIR = Path(__file__).parent.parent / "config"
CAPABILITIES_JSON = CONFIG_DIR / "capabilities.json"
ROUTING_CONFIG_JSON = CONFIG_DIR / "routing-config.json"


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
    """

    def __init__(self, code: str, message: str, slot: str | None = None):
        self.code = code
        self.slot = slot
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
    """
    slot: str
    provider_id: str
    output: Any
    execution_pattern: str
    inputs_used: dict = field(default_factory=dict)


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
            with open(path) as f:
                self.config = json.load(f)

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

        Order of consultation:
          1. ``routing_config['slots'][slot_name]['preferred']`` if registered.
          2. Each id in ``routing_config['slots'][slot_name]['fallback']``
             in order, skipping any not registered.
          3. First registered provider for the slot (insertion order).
          4. ``None`` when nothing is registered.
        """
        slots_cfg = (self._routing_config or {}).get("slots", {}) or {}
        slot_cfg = slots_cfg.get(slot_name) or {}

        preferred = slot_cfg.get("preferred")
        if preferred and self.has_provider(slot_name, preferred):
            return preferred

        for fb in slot_cfg.get("fallback", []) or []:
            if self.has_provider(slot_name, fb):
                return fb

        # Nothing in routing-config matched — fall back to the first
        # registered provider so stub tests work with no routing-config.
        registered = self.providers_for(slot_name)
        return registered[0] if registered else None

    def invoke(
        self,
        slot_name: str,
        inputs: dict,
        provider_id: str | None = None,
    ) -> InvocationResult:
        """Dispatch ``inputs`` to the slot's handler.

        Validates ``inputs`` against the slot's contract, fills in
        defaults for unsupplied optional inputs, picks a provider (per
        ``provider_id`` if given, else ``resolve_provider``), and calls
        the handler.

        Raises ``CapabilityError`` on any contract violation or provider
        absence; the registry never silently dispatches a malformed
        request.
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

        # Resolve provider.
        chosen = provider_id or self.resolve_provider(slot_name)
        if chosen is None:
            raise CapabilityError(
                "no_provider_registered",
                f"No provider is registered for slot '{slot_name}'. "
                f"Configure a model in Settings → or register a stub.",
                slot=slot_name,
            )
        if not self.has_provider(slot_name, chosen):
            raise CapabilityError(
                "provider_not_found",
                f"Provider '{chosen}' is not registered against slot "
                f"'{slot_name}'. Registered: "
                f"{', '.join(self.providers_for(slot_name)) or 'none'}",
                slot=slot_name,
            )

        handler = self._providers[chosen][slot_name]
        try:
            output = handler(validated)
        except CapabilityError:
            raise
        except Exception as exc:  # pragma: no cover — surfaced verbatim
            raise CapabilityError(
                "handler_failed",
                f"Provider '{chosen}' raised an unhandled exception while "
                f"fulfilling slot '{slot_name}': {exc}",
                slot=slot_name,
            ) from exc

        return InvocationResult(
            slot=slot_name,
            provider_id=chosen,
            output=output,
            execution_pattern=contract.get("execution_pattern", "sync"),
            inputs_used=validated,
        )


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

def load_registry(
    config_path: str | Path | None = None,
    routing_config_path: str | Path | None = None,
) -> CapabilityRegistry:
    """Load a CapabilityRegistry from the standard config locations.

    ``routing_config_path`` is consulted for the ``slots`` block;
    omitting it disables preferred/fallback resolution and the registry
    falls back to first-registered-provider order in
    ``resolve_provider``.
    """
    routing_config = None
    if routing_config_path is not None or ROUTING_CONFIG_JSON.exists():
        rc_path = Path(routing_config_path) if routing_config_path else ROUTING_CONFIG_JSON
        try:
            with open(rc_path) as f:
                routing_config = json.load(f)
        except Exception:
            routing_config = None
    registry = CapabilityRegistry(config_path=config_path, routing_config=routing_config)

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
