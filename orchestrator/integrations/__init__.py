"""Provider integration modules for Phase 7 capability slots (WP-7.3.2).

Each module wires one external provider (OpenAI, Stability, Replicate)
into the capability registry by registering handlers for the slots it
fulfills. Module-level ``register(registry)`` functions are the entry
point — boot.py calls them after constructing the registry.

Sub-modules:
  * ``stability``  — WP-7.3.2b. Fulfills ``image_generates``,
    ``image_outpaints``, ``image_upscales`` via the Stability AI REST
    API (``api.stability.ai``). Authenticates via keyring service
    ``ora-stability``.
  * ``openai``     — WP-7.3.2a (sibling integration; not implemented
    here).
  * ``replicate``  — WP-7.3.2c (sibling integration; not implemented
    here).
"""
