# Out-of-Scope Findings — Ora Visual-Primary Campaign

These are new findings recorded during this campaign. They are deliberately not implemented here because doing so would change the approved product boundary.

## Compiler-artifact editing and write-back

Position/value and deferred DSL outputs remain assistant-owned rendered artifacts. The user can preserve and annotate the surrounding scene, but dragging a compiler artifact does not rewrite the source envelope's values or positions. A future campaign would need a round-trip data contract, conflict handling, and persistence semantics before enabling that behavior.

## Visual feedback and critique

The campaign makes visual output durable and visible but does not add screenshot-based critique, image feedback loops, or automatic visual self-correction after rendering. Those require a separate quality contract and provider/cost policy; the normal turn path therefore remains headless and deterministic for noninteractive producers.

## Semantic vocabulary governance

The source-grounded fallback and native emitter validate structure and provenance, but they do not introduce a controlled domain vocabulary for concepts, relations, or support verdicts. Adding one would be a separate knowledge-governance decision rather than a renderer change.

## Native conversion of deferred DSL types

Flowchart, sequence, and state remain compiler-rendered deferred DSL types. Converting them into native Excalidraw primitives would require parsers, semantic preservation rules, and a separate regression surface, so this campaign keeps their existing SVG/artifact path.

## Automatic image-provider invocation from analytical turns

The analytical contract can carry an explicit image preference and the existing `image_generates` capability honors its configured provider chain, but this campaign does not make every analytical turn call an image provider. Provider failure is surfaced by the real capability route and the analytical visual authority falls back to a source-grounded concept map where an analytical visual is still required.
