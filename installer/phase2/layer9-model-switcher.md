### PHASE 2, LAYER 9: MODEL SWITCHER MODULE

**Stage Focus**: Install a UI panel that lets the user configure which model fills each role in the multi-model pipeline, with live RAM budget display and quick presets. This layer executes only on Tier C (Sovereign) hardware where multiple large models can run concurrently.

**When to execute**: After Phase 2, Layer 8 (Documentation and Verification). Skip gracefully on Tier A and Tier B hardware with the note: "The Model Switcher is available on Tier C (64GB+ RAM). Your current hardware supports a single local model. This layer will activate automatically if you upgrade."

**Why this layer exists**: Earlier versions of this framework described a Gear 5 concept — a separate pipeline stage for cross-company adversarial evaluation. That concept is retired. Adversarial diversity is now a model selection choice: the reader decides which models fill which pipeline roles. The Model Switcher Module is the interface for that decision.

### Processing Instructions

1. **Verify Tier C eligibility.** IF AVAILABLE_MODEL_RAM is less than 48 GB, THEN skip this layer with a graceful message. The threshold is 48 GB because the switcher's value is most apparent when at least two mid-size models can be held in RAM simultaneously.

2. **Generate the switcher panel** at `[workspace]/server/panels/model-switcher.html` and the backing controller at `[workspace]/server/panels/model-switcher.py`. The panel exposes six pipeline slot assignments, one per role in the Gear 4 multi-model pipeline:

   | Slot | Role | Description |
   |---|---|---|
   | `sidebar` | Sidebar | The model that responds in the always-on sidebar context |
   | `step1_cleanup` | Step 1 Cleanup | Normalizes and clarifies raw user input before the main pipeline |
   | `breadth` | Breadth | Generates the initial wide-ranging response |
   | `depth` | Depth | Refines and deepens the breadth pass |
   | `evaluator` | Evaluator | Adversarial critic — ideally from a different family than breadth/depth |
   | `consolidator` | Consolidator | Synthesizes all prior passes into the final output |

3. **Populate the slot selector.** For each slot, render a dropdown listing all endpoints currently registered in `[workspace]/config/endpoints.json`. Local model endpoints appear with their parameter count and estimated RAM footprint. Browser and API endpoints are listed with their service name. The dropdown must render the current assignment as the selected option.

4. **Implement live RAM budget display.** Below the slot grid, display a RAM budget bar:

   - Total RAM available for models: `AVAILABLE_MODEL_RAM` (75% of total system RAM).
   - RAM currently assigned: sum of estimated RAM for all slots with a local model assigned. If two or more slots share the same local model, count that model's RAM only once.
   - Remaining headroom: total minus assigned.
   - Update in real time as the user changes slot assignments — no page reload required.

5. **Grey out models that won't fit.** When the user opens a slot's dropdown, calculate whether adding that model would push the total assigned RAM over `AVAILABLE_MODEL_RAM`. IF it would, THEN render the option greyed out with a tooltip: "Adding this model would exceed your RAM budget ([X] GB remaining)." The user can still force-select a greyed option — the display is advisory, not blocking.

6. **Warn on adversarial role conflict.** The evaluator slot provides its value by checking the breadth and depth passes from a different perspective. IF the user assigns the same model family to both the `evaluator` slot and either the `breadth` or `depth` slot, THEN display an inline warning beneath the evaluator dropdown: "Same model family as Breadth/Depth — adversarial value reduced. For maximum diversity, assign a model from a different provider or training lineage." This is a soft warning, not a block.

7. **Implement four quick presets.** Add a row of preset buttons above the slot grid:

   - **All Local**: assigns the best available local model (highest RAM-fitting option) to all six slots.
   - **Local + Cloud Evaluator**: assigns the primary local model to breadth, depth, and consolidator; assigns the best available browser or API endpoint to evaluator; assigns the primary local model to sidebar and step1_cleanup.
   - **All Cloud**: assigns the best available browser or API endpoint to all slots. Useful for Tier 0 or when testing without a local model.
   - **Maximum Diversity**: assigns models to maximize cross-family diversity within the RAM budget. Breadth and depth get the two largest local models that fit. Evaluator gets the best cloud endpoint. Consolidator gets the same model as depth. Sidebar and step1_cleanup get the smallest local model that fits. IF only one local model is available, assign it to breadth, depth, and consolidator; cloud to evaluator; local to sidebar and step1_cleanup.

   Applying a preset immediately populates all six dropdowns and updates the RAM budget bar. The reader can then adjust individual slots before saving.

8. **Persist configuration.** Save slot assignments to two files:

   a. Append a `slot_assignments` key to `[workspace]/config/endpoints.json`:

      ```json
      "slot_assignments": {
        "sidebar": "[endpoint_name]",
        "step1_cleanup": "[endpoint_name]",
        "breadth": "[endpoint_name]",
        "depth": "[endpoint_name]",
        "evaluator": "[endpoint_name]",
        "consolidator": "[endpoint_name]"
      }
      ```

   b. Write a `[workspace]/config/models.json` file that records, for each assigned endpoint, its display name, model identifier, provider family, estimated RAM, and whether it is local or cloud. This file is the canonical reference for the pipeline orchestrator to identify which model is in which role.

9. **Integrate into the chat server header.** Modify `[workspace]/server/server.py` to expose a settings button (⚙) in the top-right corner of the chat interface header. Clicking the button opens the model switcher panel as an overlay or side drawer without navigating away from the conversation. Add keyboard shortcut Cmd+M (macOS) / Ctrl+M (Windows/Linux) to open and close the panel.

10. **Test the switcher.** Apply the "All Local" preset, save, restart the chat server, and verify the server reads the `slot_assignments` key from `endpoints.json` on startup. Send a test message that would route through the pipeline. Confirm the server's log identifies the correct endpoint for each slot.

### Output Format for This Layer

```
MODEL SWITCHER INSTALLED
Panel: [workspace]/server/panels/model-switcher.html
Controller: [workspace]/server/panels/model-switcher.py
Slot assignments saved to: config/endpoints.json (slot_assignments), config/models.json
RAM budget display: [functional]
Presets available: All Local, Local + Cloud Evaluator, All Cloud, Maximum Diversity
Header integration: ⚙ button + Cmd+M shortcut
Switcher test: [PASS / FAIL]
```

---

