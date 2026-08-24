# Out-of-Scope Findings — Ora Visual-Primary Campaign

### Controlled relation vocabulary
- Location: config/visual-schemas/specs/concept_map.json:25
- What is wrong: Relationship labels remain free text rather than a closed relation vocabulary, so a deterministic checker cannot distinguish faithful support from a plausible but incorrect semantic relation.
- Observable consequence: Semantic support verdicts remain unassessed; only construction-grounding, numeric grounding, and structural checks are available.
- Confidence: confirmed
- Rough size: needs investigation

### Drag-to-envelope write-back
- Location: server/static/ora-visual-compiler/native-excalidraw.js:13
- What is wrong: Scene edits do not write position or position-determining values back to the canonical visual envelope.
- Observable consequence: Types whose envelopes encode position must remain compiler-rendered; making them native would let a dragged drawing silently disagree with its source envelope.
- Confidence: confirmed
- Rough size: needs investigation

### Visual emission log lacks source identity
- Location: orchestrator/boot.py:2820
- What is wrong: Emission records inherit an optional conversation id, so a null id identifies neither a live turn nor a bench run and the two sources cannot be distinguished.
- Observable consequence: The log cannot support the claim that no live synthesis ever occurred; any conclusion that depends on that claim is unsupported.
- Confidence: confirmed
- Rough size: needs investigation
