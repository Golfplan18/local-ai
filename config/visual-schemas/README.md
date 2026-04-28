# Ora Visual Output Schemas — v0.2

JSON Schema 2020-12 definitions for the **Ora Visual Output Generation Protocol v0.2**. These schemas validate `ora-visual` spec blocks emitted by analytical models, both server-side (Python) and client-side (JavaScript), before any visual is rendered.

The authoritative specification is `Ora Visual Output Generation Protocol.md` in the vault. These schemas are the normative form of the informal schemas in that document.

## Purpose

- **Drift eliminator.** The discriminated union on `type` + `additionalProperties: false` + enum-constrained vocabularies closes off the majority of LLM schema drift at parse time (Protocol §2.1).
- **Fail-closed gate.** Any spec that does not validate is rejected before it reaches a renderer. "Render a degraded visual because a slot was allocated" is the wrong failure mode (Protocol §8.5 cardinal rule).
- **Shared contract.** A single source of truth for the Python integrity checker, the JavaScript render pipeline, the adversarial reviewer, and the vault edit surface.

## Directory layout

```
visual-schemas/
  envelope.json                   # Top-level envelope; discriminated union on `type`
  semantic_description.json       # Four-level description (Lundgard & Satyanarayan)
  spatial_representation.json     # Optional spatial-native layer (Tversky; §10.1)
  specs/
    comparison.json               # QUANT — bar / column / dot plot / slope
    time_series.json              # QUANT — line + band / fan / sparkline
    distribution.json             # QUANT — box / violin / strip / histogram
    scatter.json                  # QUANT — bivariate + annotation
    heatmap.json                  # QUANT — heatmap / small-multiple heatmap
    tornado.json                  # QUANT — sensitivity diagram (v0.2)
    causal_loop_diagram.json      # CAUSAL — CLD
    stock_and_flow.json           # CAUSAL — XMILE-aligned
    causal_dag.json               # CAUSAL — DAGitty DSL
    fishbone.json                 # CAUSAL — Ishikawa
    decision_tree.json            # DECISION — decision / probability tree
    influence_diagram.json        # DECISION — Howard-Matheson (v0.2)
    ach_matrix.json               # DECISION — Heuer ACH
    quadrant_matrix.json          # DECISION — 2x2 / scenario planning
    bow_tie.json                  # RISK — bow-tie (v0.2)
    ibis.json                     # ARGUMENT — IBIS
    pro_con.json                  # ARGUMENT — pro-con tree
    concept_map.json              # RELATIONAL — Novak concept map
    sequence.json                 # PROCESS — Mermaid sequenceDiagram
    flowchart.json                # PROCESS — Mermaid flowchart / swimlane
    state.json                    # PROCESS — Mermaid stateDiagram-v2
    c4.json                       # SPATIAL — Structurizr DSL
  examples/
    <type>.valid.json             # Minimal valid envelope per type
    <type>.invalid.json           # One-violation envelope per type (with _note)
```

## Loading the schemas

### Python

Use `jsonschema` ≥ 4.18 with the `referencing` library so inter-schema `$ref`s resolve.

```python
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path("~/ora/config/visual-schemas").expanduser()

def load(path):
    return json.loads(path.read_text())

resources = []
for p in [ROOT / "envelope.json",
          ROOT / "semantic_description.json",
          ROOT / "spatial_representation.json",
          *sorted((ROOT / "specs").glob("*.json"))]:
    schema = load(p)
    rel = p.relative_to(ROOT).as_posix()  # e.g. "specs/comparison.json"
    res = Resource(contents=schema, specification=DRAFT202012)
    # Bind under both the declared $id and the path used in $refs
    resources.append((schema["$id"], res))
    resources.append((rel, res))

registry = Registry().with_resources(resources)
validator = Draft202012Validator(load(ROOT / "envelope.json"), registry=registry)

errors = list(validator.iter_errors(spec_block))  # [] == valid
```

### JavaScript

Use Ajv 2020 (draft 2020-12 support).

```js
import Ajv2020 from "ajv/dist/2020.js";
import fs from "node:fs";
import path from "node:path";

const ROOT = "/Users/oracle/ora/config/visual-schemas";
const load = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf-8"));

const ajv = new Ajv2020({ strict: true, allErrors: true });
// Register every sub-schema by both its $id and its relative path so
// both styles of $ref in the envelope resolve.
const register = (relPath) => {
  const s = load(relPath);
  ajv.addSchema(s, s.$id);
  ajv.addSchema(s, relPath);
};
register("semantic_description.json");
register("spatial_representation.json");
for (const f of fs.readdirSync(path.join(ROOT, "specs"))) {
  register(path.posix.join("specs", f));
}

const validate = ajv.compile(load("envelope.json"));
const ok = validate(specBlock);
if (!ok) console.error(validate.errors);
```

## Adding a new visual type

1. **Update the Protocol document first.** Append a §3.x entry describing the informal schema, required fields, enums, and structural invariants. Nothing else in the system is source of truth.
2. **Write the new schema file** at `specs/<type>.json`. Follow the template:
   - `$schema: "https://json-schema.org/draft/2020-12/schema"`
   - `$id` matching the pattern `https://ora.local/schemas/specs/<type>.json`
   - `title`, `description` — human-readable, reference the Protocol section.
   - `type: "object"` with `additionalProperties: false` at every nesting level.
   - Enum constraints on every closed-vocabulary field (polarity, severity, credibility, type, kind, etc.).
   - `required` listing every mandatory field.
3. **Extend `envelope.json`**:
   - Add the new discriminator value to the top-level `type` enum.
   - Add a new `oneOf` branch wiring `{type: const "<new>"}` to `{spec: $ref "specs/<new>.json"}`.
4. **Add examples**: `examples/<type>.valid.json` and `examples/<type>.invalid.json` (the invalid example gets a `"_note"` at the top documenting the violation). Validate both with the envelope schema; the valid one must pass, the invalid one must fail.
5. **Wire the downstream integrity checker** to enforce the structural invariants the JSON Schema cannot express (see the list below).
6. **Update `README.md`** (this file): directory tree, type table.

## Constraints JSON Schema cannot express

The Protocol enforces several integrity rules that are **not** expressible in JSON Schema 2020-12. They are enforced by the downstream integrity checker:

| Type | Invariant |
|------|-----------|
| `causal_loop_diagram` | Every declared loop is a genuine cycle in the graph. Loop `type` (R/B) matches the parity of `-` polarities around the loop (even → R, odd → B). |
| `causal_loop_diagram` | `variables[].id` unique; every `links[].from/to` resolves to a declared variable id; no orphan nodes unless `allow_isolated: true`. |
| `stock_and_flow` | Every flow endpoint resolves to a stock or cloud; every stock has ≥ 1 attached flow; `info_links` form a DAG over auxiliaries; declared units are dimensionally consistent. |
| `causal_dag` | DAGitty DSL parses; graph is acyclic; `focal_exposure` and `focal_outcome` appear as nodes in the DSL. |
| `fishbone` | Depth ≤ 3. If `framework != custom`, category names drawn from the framework's canonical set (6M / 4P / 4S / 8P). Effect phrased as a problem, not a solution (soft lint). |
| `decision_tree` | Chance-node children's probabilities sum to 1 ± 1e-6. Decision nodes have ≥ 1 child. Terminals carry `payoff` when `mode=decision`. Decision-node edges carry no `probability`. Compiler computes rollback EV. |
| `influence_diagram` | Exactly one value node. No arcs into a decision from a later-decided node (temporal consistency when `temporal_order` provided). Functional-arc subgraph into the value node is acyclic. |
| `ach_matrix` | Every (evidence × hypothesis) cell populated. Non-diagnostic evidence flagged (rows where every cell is N or NA). Diagnosticity scoring per `scoring_method`. |
| `quadrant_matrix` | `items[].x/y` within axis bounds (expressed in schema: [0,1]). For `scenario_planning`, each quadrant `narrative` non-empty. Axes pairwise correlation |r| ≤ 0.7 (major warning). |
| `bow_tie` | At least one threat, one consequence (enforced in schema). Layout must preserve left/right symmetry; preventive controls only on threat→event pathways, mitigative only on event→consequence. |
| `ibis` | Grammar: `idea.responds_to → question`; `pro.supports → idea`; `con.objects_to → idea`; `question.questions → any`. Violations are blocking (Protocol §3.12). |
| `concept_map` | Every proposition's `from_concept`, `via_phrase`, `to_concept` resolves to declared concept/phrase ids. Soft warning if no proposition has `is_cross_link: true`. |
| `sequence`/`flowchart`/`state` | Mermaid DSL parses cleanly (bounded 2-retry repair loop). Flowchart decision nodes have ≥ 2 labelled, mutually exclusive, exhaustive outgoing edges. Sequence: every message has sender and receiver. State: initial state declared; unreachable states flagged. |
| `c4` | Structurizr DSL parses; no forward references; `spec.level` and the DSL contents do not mix C4 levels in a single view. |
| QUANT (all) | Tufte T-rules (§7.1): lie factor in [0.95, 1.05] (T1); zero baseline on bar/area (T2); dimensional conformance (T3); chartjunk blacklist (T5); labelling completeness (T7); scale-type disclosure (T8); banking to 45° (T10); caption+source+n present (T15). |
| QUANT (all) | Uncertainty layer required when `encoding.y` is a point-estimate of an inferential / forecast / decision-driving quantity. |
| QUANT (all) | Dual y-axes rejected unless mathematically linked. |

These are precisely the invariants that **make the technique worth using**. Protocol §2.4: "emitting Mermaid for everything" would drop all of them. The schemas here enforce the closed vocabularies and structural shape; the integrity checker enforces the semantic invariants.

## Example files

The `examples/` directory contains one minimal valid envelope and one deliberately-invalid envelope per type (44 files total). The invalid files carry a top-level `"_note"` documenting what's wrong with them — validators will additionally reject them on that `_note` key under `additionalProperties: false`, so the `_note` must be stripped before running the validator against the envelope. The test harness at `/tmp/build_examples.py` does this.

Run the harness:

```bash
/opt/homebrew/bin/python3 /tmp/build_examples.py
# VALID passing: 22/22
# INVALID failing: 22/22
# All 44 examples validated as expected.
```

## Versioning

- `schema_version` in every spec block is semver. Major version bumps are breaking; consumers fail-closed on unknown major versions.
- New v0.2 types (`tornado`, `influence_diagram`, `bow_tie`) are rejected under v0.1 compilers.
- The envelope `$id` points at `https://ora.local/schemas/envelope.json` — a stable namespace that the renderer treats as opaque.

## Envelope fields added in WP-2.4

- **`canvas_action`** — optional enum `["replace", "update", "annotate", "clear"]`. Hint to the visual panel's canvas state machine. `replace` clears the stage; `update` replaces `backgroundLayer` only (preserves `userInputLayer` + `annotationLayer`); `annotate` overlays into `annotationLayer` without touching `backgroundLayer`; `clear` empties the canvas with no new render. Default handling is client-side: `replace` for the first visual in a conversation, `update` for every subsequent visual.
- **`annotations`** — optional array of overlay descriptors keyed to SVG element ids. Each entry: `{target_id: string, kind: "callout" | "highlight" | "arrow" | "badge", text?: string, color?: string}`. `callout` and `highlight` render in WP-2.4; `arrow` and `badge` emit `W_ANNOTATION_KIND_DEFERRED` and resolve in WP-5.1.

## Protocol sections referenced

- §2.1–§2.3 — envelope structure and fields
- §2.4 — tiering
- §3.1–§3.16 — per-type schemas (informal; this directory is the normative form)
- §5 — `relation_to_prose` enum
- §6 — `canvas_action` semantics (WP-2.4)
- §7.1 — Tufte T-rules (drive required metadata)
- §8 — semantic description
- §10.1 — spatial_representation
