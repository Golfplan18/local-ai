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
        raise last_exc


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

# Hardwired slot-inheritance relationships per Image Spec §5.8.1 v2.0
# (publisher direction 2026-05-13: "manage one chain in the UI; cartoon
# inherits + appends the LoRA").
#
# Why hardwired rather than file-declared: the Visual settings UI auto-
# saves routing-config.json on every edit, but doesn't understand the
# ``inherits`` / ``append_fallback`` schema — UI writes serialize each
# slot as standalone {preferred, fallback}, clobbering any inheritance
# directives. Encoding the well-known cartoon relationship in code means
# the UI can edit ``image_generates`` freely and the cartoon chain
# follows automatically — there's nothing in the JSON for the UI to
# overwrite. File-declared inheritance still works for slots not in this
# mapping (the resolver below applies both layers in order).
#
# Format: child_slot → (parent_slot, [appended_fallbacks], [excluded_inherited])
#
# The exclude_inherited list (per Image Spec §5.8.1 v2.2 publisher
# direction 2026-05-13) names providers the parent slot may legitimately
# carry but that don't belong in the child's cartoon chain. Concrete
# case: local-diffusers (Stable Diffusion 1.5) is a sensible last-resort
# floor for news photos (image_generates) — but it actively damages the
# cartoon path because (a) SD 1.5's CLIP tokenizer truncates anything
# over 77 tokens and Hector's prompts run 800+, (b) SD 1.5's aesthetic
# vocabulary doesn't include Nast cross-hatch, and (c) when SD 1.5
# "succeeds" it stops the cascade before the LoRA (which is trained on
# the exact Hector register and never refuses) gets reached. Excluding
# it from the cartoon path is the publisher's structural fix for "the
# LoRA never gets called" surfaced repeatedly across the 2026-05-13
# moderation-lottery test runs.
_HARDWIRED_SLOT_INHERITANCE: dict[str, tuple[str, list[str], list[str]]] = {
    "image_generates_cartoon": (
        "image_generates",
        ["civitai-hector-lora-v1"],
        ["local-diffusers"],
    ),
}


def resolve_slot_inheritance(routing_config: dict) -> dict:
    """Materialize ``inherits`` / ``append_fallback`` / ``prepend_fallback``
    directives in routing-config.json so every slot ends up with a fully
    explicit ``preferred`` + ``fallback`` list.

    Two inheritance sources, applied in order:

    (1) **Hardwired relationships** (``_HARDWIRED_SLOT_INHERITANCE``).
        Well-known parent/child pairs encoded in code so the relationship
        survives UI-driven config rewrites. The current entry is
        ``image_generates_cartoon`` inheriting from ``image_generates``
        and appending ``civitai-hector-lora-v1`` per Image Spec §5.8.1 v2.0.

    (2) **File-declared inheritance**. Per-slot directives in routing-
        config.json::

          "some_slot": {
            "inherits": "parent_slot",
            "append_fallback": ["extra-provider"]
          }

    becomes, after resolution:

      "image_generates_cartoon": {
        "preferred": "<whatever image_generates.preferred is>",
        "fallback": [...image_generates.fallback..., "civitai-hector-lora-v1"]
      }

    Rules:
      * ``inherits`` names the parent slot to copy ``preferred`` + ``fallback`` from.
      * ``preferred`` declared on the child wins over the parent's.
      * ``fallback`` declared on the child replaces the parent's wholesale
        (so a child can opt out of the parent's chain entirely). Note:
        for hardwired entries, the parent's chain is always used as the
        base — the hardwired child's existing fallback list is REPLACED
        rather than merged, since the UI's serialized standalone shape
        carries stale data when the parent's chain has been edited.
      * ``prepend_fallback`` / ``append_fallback`` are *additive* to the
        effective (post-inheritance) ``fallback`` list, in order
        prepend → inherited → append.
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

    # Layer 1: hardwired relationships. Inject the directives if the
    # slot exists; the merge logic below then materializes them.
    for child_name, (parent_name, append, exclude) in _HARDWIRED_SLOT_INHERITANCE.items():
        child_cfg = slots.get(child_name)
        if not isinstance(child_cfg, dict):
            # If the child slot doesn't exist at all, create it so the
            # cartoon chain is reachable even on a freshly-built config.
            child_cfg = {}
            slots[child_name] = child_cfg
        # Hardwire ALWAYS wins for the slots in the map, overriding any
        # standalone {preferred, fallback} the UI may have written.
        child_cfg["inherits"] = parent_name
        child_cfg["append_fallback"] = list(append)
        if exclude:
            child_cfg["exclude_inherited"] = list(exclude)
        # Wipe the standalone fields so the merge below treats parent's
        # chain as the source of truth (the UI's serialized standalone
        # values are stale for hardwired children).
        child_cfg.pop("preferred", None)
        child_cfg.pop("fallback", None)

    # Layer 2: per-slot materialization (handles both layer-1 injections
    # and any organically-declared inheritance).
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


def load_registry(
    config_path: str | Path | None = None,
    routing_config_path: str | Path | None = None,
) -> CapabilityRegistry:
    """Load a CapabilityRegistry from the standard config locations.

    ``routing_config_path`` is consulted for the ``slots`` block;
    omitting it disables preferred/fallback resolution and the registry
    falls back to first-registered-provider order in
    ``resolve_provider``.

    Slot-inheritance directives (``inherits`` / ``prepend_fallback`` /
    ``append_fallback``) are resolved at load time via
    :func:`resolve_slot_inheritance` so the registry only sees fully
    materialized ``preferred`` + ``fallback`` lists.
    """
    routing_config = None
    if routing_config_path is not None or ROUTING_CONFIG_JSON.exists():
        rc_path = Path(routing_config_path) if routing_config_path else ROUTING_CONFIG_JSON
        try:
            with open(rc_path) as f:
                routing_config = json.load(f)
        except Exception:
            routing_config = None
    if routing_config is not None:
        resolve_slot_inheritance(routing_config)
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
