### PHASE 2, LAYER 10: INTERFACE CUSTOMIZATION FRAMEWORK

**Stage Focus**: Install a config-driven multi-panel workspace with selectable layout presets, theme options, and a natural language layout generator. This layer gives the reader a working environment that grows with their workflow rather than a fixed single-chat interface.

**When to execute**: After Phase 2, Layer 9 (or after Layer 8 on Tier A and Tier B hardware, where Layer 9 is skipped). This layer runs on all tiers — the layouts available adapt to the reader's tier.

### Processing Instructions

1. **Define the five panel types.** Each panel in the workspace is one of the following types, selectable per-slot via a dropdown in each panel's header bar:

   | Type | Description |
   |---|---|
   | `chat` | An independent conversation thread. Maintains its own history separate from other chat panels. |
   | `vault` | Semantic search into the ChromaDB knowledge collection. Displays results ranked by relevance. Automatically updates its context topic when the main chat panel changes subjects (tracked by the last `knowledge_search` query). |
   | `pipeline` | Read-only display of the current Gear 4 pipeline stage — which slot is active, what model is running it, and an abbreviated view of the intermediate pass outputs. Updates live during a pipeline run. |
   | `clarification` | An ephemeral chat panel for quick side-questions that should not pollute the main conversation history. Includes a "Send to Main" button that appends the clarification exchange as a note into the main chat context. |
   | `switcher` | An embedded instance of the Model Switcher panel (Phase 2, Layer 9). Allows slot configuration without leaving the workspace layout. |

2. **Define the three layout presets.**

   - **Simple**: a single full-width chat panel. Default for Tier 0 and Tier A. No sidebar. Minimalist — identical to the Phase 1, Layer 7 interface.
   - **Studio**: main chat panel (70% width) + one sidebar panel (30% width). The sidebar defaults to `vault` type. Default for Tier B.
   - **Workbench**: main chat panel (50% width) + sidebar panel (25% width) + secondary panel (25% width). Sidebar defaults to `vault` type. Secondary panel defaults to `pipeline` type. Default for Tier C (multi-model local) — gives the reader simultaneous access to the main conversation, knowledge search, and live pipeline monitoring.

   The default layout for each tier is set automatically at first launch. The reader can switch presets at any time from the header.

3. **Generate the layout engine.** Create `[workspace]/server/layout.py` — a module that reads the active layout from `[workspace]/config/interface.json` and generates the appropriate panel grid at page load. The layout engine must:

   a. Parse `interface.json` on each page request (not at server startup), so layout changes take effect without restarting the server.
   b. Render the panel grid using CSS Grid or Flexbox — no external CSS framework dependencies.
   c. Inject each panel's type-specific content (chat input/output, vault search box, pipeline status, etc.) from the appropriate panel module.
   d. Apply the active theme (see step 4).

4. **Implement the five themes.**

   | Theme key | Description |
   |---|---|
   | `default-light` | Light background, dark text. Default for new installs. |
   | `default-dark` | Dark background, light text. |
   | `high-contrast` | Maximum contrast ratio. Black background, white text, no mid-tones. Accessibility-oriented. |
   | `terminal` | Green-on-black, monospace font throughout. |
   | `warm` | Warm off-white background, sepia-tinted text and UI elements. |

   Themes are implemented as CSS variable sets injected into the page `<head>`. Switching themes does not reload the page — it swaps the CSS variable block via JavaScript. The active theme name is stored in `[workspace]/config/interface.json`.

5. **Add theme and layout controls to the server header.** Extend `[workspace]/server/server.py` to include in the chat interface header:

   - Three layout preset icons (Simple, Studio, Workbench) displayed as small icon buttons with tooltips. The active preset is highlighted.
   - A theme selector displayed as a small palette icon. Clicking it opens a dropdown listing the five themes by name. The active theme is checked.
   - Both controls update `interface.json` and apply the change immediately without a page reload.

6. **Implement the layout generator (✦ Layout button).** Add a button labeled "✦ Layout" to the header. Clicking it opens a generation panel with:

   - A text input: "Describe your ideal workspace in plain language (e.g., 'chat on the left, vault search on the right, dark theme')"
   - An image upload area: "Or upload a screenshot or mockup of a layout you like" — available only when a vision-capable API endpoint is active (detected from `endpoints.json`). IF no vision endpoint is available, THEN display the text area only, with the note: "Image input available when a vision-capable API endpoint is configured."
   - A "Generate" button that submits the description (and optional image) to the active endpoint, asking it to produce a valid `interface.json` layout definition matching the description. The generated layout is previewed before being applied.
   - A "Apply" button and a "Discard" button. "Apply" writes the generated JSON to `interface.json` and refreshes the layout. "Discard" returns to the previous layout.

   The layout generator prompt instructs the model to output a JSON block conforming to the `interface.json` schema. The server parses the JSON from the model's response, validates it against the schema, and refuses to apply malformed output with a clear error.

7. **Persist layout configuration.** All layout state is stored in `[workspace]/config/interface.json`. The schema:

   ```json
   {
     "active_preset": "[simple|studio|workbench|custom]",
     "active_theme": "[default-light|default-dark|high-contrast|terminal|warm]",
     "panels": [
       {
         "id": "panel-1",
         "type": "[chat|vault|pipeline|clarification|switcher]",
         "width_pct": 50
       },
       {
         "id": "panel-2",
         "type": "vault",
         "width_pct": 25
       },
       {
         "id": "panel-3",
         "type": "pipeline",
         "width_pct": 25
       }
     ]
   }
   ```

   When a preset button is clicked, overwrite the `panels` array with the preset's definition and set `active_preset` accordingly. When the user changes an individual panel's type via its header dropdown, update only that panel's `type` field in the array and set `active_preset` to `"custom"`.

8. **Set tier-appropriate defaults.** At first launch (when `interface.json` does not exist), create it with the defaults appropriate for the detected tier:

   - Tier 0 and Tier A: Simple preset, default-light theme.
   - Tier B: Studio preset, default-light theme.
   - Tier C: Workbench preset, default-light theme.

9. **Test the interface framework.**
   a. Start the server and verify the page loads with the tier-appropriate default layout.
   b. Switch each preset and verify the panel grid reflows without a page reload.
   c. Switch each theme and verify the visual change applies immediately.
   d. Change one panel type via its header dropdown and verify the change persists after a page reload.
   e. Verify `interface.json` is written correctly after each change.

### Output Format for This Layer

```
INTERFACE CUSTOMIZATION FRAMEWORK INSTALLED
Layout engine: [workspace]/server/layout.py
Config: [workspace]/config/interface.json
Default preset: [Simple / Studio / Workbench] (Tier [0/A/B/C] default)
Default theme: default-light
Panel types available: chat, vault, pipeline, clarification, switcher
Presets: Simple, Studio, Workbench
Themes: default-light, default-dark, high-contrast, terminal, warm
Layout generator: [enabled (vision available) / enabled (text only) / installed]
Header controls: preset icons + theme selector + ✦ Layout button
Tests: [PASS / FAIL]
```

---

