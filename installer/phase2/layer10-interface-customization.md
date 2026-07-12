### PHASE 2, LAYER 10: INTERFACE CUSTOMIZATION FRAMEWORK

**Status 2026-07-12: retired legacy natural-language installer layer.** Do not execute this file as part of an installation. Use `scripts/install.py --profile solo`; this layer is retained as a historical architecture record for G3.32 reconciliation.

**Historical role:** The original layer described a config-driven, multi-panel workspace with Simple, Studio, and Workbench presets; five themes; and a natural-language layout generator. It would have created `server/layout.py`, `config/interface.json`, layout preset files, and legacy theme files. That architecture was not carried into the live V3 interface and is now explicitly retired.

## Retirement Disposition

An installer or reconciliation run **must not** recreate any of the following:

- `config/interface.json` or another runtime layout-state file
- `server/layout.py` or an equivalent server-side layout generator
- `config/layouts/` preset files or the retired `/api/layout` and `/api/layouts` endpoints
- the natural-language or screenshot-driven layout generator
- legacy themes under `config/themes/`
- legacy layout or theme controls that write the retired configuration

These are retirement constraints, not deferred installation work. Their absence is the expected current state.

## Current V3 Interface Architecture

The live interface is a code-defined V3 workspace:

- `server/index-v3.html` defines the shell and primary interface structure.
- `server/static/styles/` contains the token and component styles.
- `server/static/js/` contains interface behavior, including `v3-layout.js`.
- The layout is hardcoded in the V3 shell, styles, and scripts. There is no live config-driven preset system and no layout generator.
- The V3 Theme Library manages themes. Theme packages live under `server/static/themes/<theme-id>/` with `manifest.json` and `theme.css`.
- Theme discovery, installation, customization, export, and removal use the `/api/v3-themes/*` API family. Project-declared themes are included by the same aggregate list API.

Layout customization is therefore source customization: change the V3 shell, component styles, and behavior together, then test the resulting interface. Theme customization should use the Theme Library or a valid V3 theme package; it must not restore the retired theme directory or layout configuration.

## Reconciliation Instructions

When this historical layer is reviewed against a current installation:

1. Verify that the live root route serves `server/index-v3.html`.
2. Verify that no active code depends on `config/interface.json`, `config/layouts/`, `/api/layout`, `/api/layouts`, or legacy `config/themes/` assets.
3. Verify that the V3 Theme Library can list installed themes through `/api/v3-themes/list` and can apply a valid package from `server/static/themes/`.
4. Treat the removal of legacy layout endpoints, preset files, generator code, and themes as successful retirement, not missing implementation.
5. If a fork intentionally changes the workspace layout, document the changed V3 files and keep its executable installer and natural-language specification aligned through DCP.

## Verification Record

```text
INTERFACE CUSTOMIZATION RETIREMENT VERIFIED
Live shell: server/index-v3.html
Layout authority: V3 shell + server/static/styles/ + server/static/js/
Retired layout config: absent
Retired presets and generator: absent
Theme authority: V3 Theme Library
Theme packages: server/static/themes/<theme-id>/
Theme API: /api/v3-themes/*
Result: [PASS / FAIL]
```

---
