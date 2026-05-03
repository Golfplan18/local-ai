# Lucide icon library — vendored

Vendored copy of [lucide-static](https://www.npmjs.com/package/lucide-static), the SVG-files-only distribution of [Lucide Icons](https://lucide.dev/). Used by Ora's visual pane toolbar system as the default icon library (per Phase 7 §11.3 "Default icon set" and §11.2 architectural-decisions row "Default icon library").

Vendored 2026-04-29 as part of WP-7.0.3.

## Files

| Path | Purpose |
| --- | --- |
| `LICENSE` | ISC license text (Lucide is ISC, equivalent to MIT for permissive purposes) |
| `VERSION` | Lucide version + provenance + refresh instructions, matching the Konva / D3 / Mermaid vendor convention |
| `icons/` | 1,952 individual SVG files (one per icon name); ~7.6 MB total |
| `icon-nodes.json` | Per-icon node tree (machine-readable, used by the tree-shake build) |
| `tags.json` | Per-icon semantic tag aliases (e.g. "image" → picture, photo, photography) |
| `names.json` | **Canonical Lucide name list** — the authoritative validator surface for WP-7.0.4 and downstream consumers |

## The canonical name list

`names.json` is the single source of truth for "is this a valid Lucide name." Its shape:

```json
{
  "version": "1.14.0",
  "count": 1952,
  "names": ["a-arrow-down", "a-arrow-up", "a-large-small", "accessibility", ...]
}
```

Generated from `ls icons/*.svg` at vendor time. Refreshing the vendored library refreshes this file (see `VERSION` for the full refresh procedure).

## Programmatic access

### Browser side (icon-resolver.js)

```js
await OraIconResolver.init();   // loads names.json + runtime/icon-set.json
OraIconResolver.isValidName('image');      // → true
OraIconResolver.isValidName('not-a-thing'); // → false
OraIconResolver.listNames();   // → all 1,952 sorted names
OraIconResolver.resolve('image');   // → SVG string
OraIconResolver.resolve('<svg ...>');   // inline SVG → returned as-is
OraIconResolver.resolve('bogus');   // → marked-fallback glyph
```

### Build side (lucide-tree-shake.js)

```js
const { _loadCanonicalNames } = require('~/ora/scripts/lucide-tree-shake.js');
const canonical = _loadCanonicalNames();
canonical.set.has('image');    // → true (Set<string> for O(1) lookup)
canonical.list;                 // → string[]
canonical.version;              // → "1.14.0"
```

## Consumers

Authored:

- `~/ora/server/static/icon-resolver.js` — name → SVG resolver with marked-fallback semantics
- `~/ora/scripts/lucide-tree-shake.js` — build script producing `~/ora/server/static/runtime/icon-set.json`
- `~/ora/server/static/ora-visual-compiler/tests/cases/icon-resolver.test.js` — 70-assertion test harness

Anticipated (later Phase 7 WPs, will reference this name list):

- WP-7.0.4 — toolbar pack JSON schema validator (cross-references this name set)
- WP-7.1.1 — toolbar registry and rendering
- WP-7.1.6 — five specialty toolbar definitions in `~/ora/config/toolbars/`
- WP-7.8.1 — four shipped customization packs in `~/ora/config/packs/`
