---
nexus:
  - ora
type: mode
tags:
date created: 2026-03-23
date modified: 2026-05-24

---

# MODE: Relationship Mapping

```yaml
# 0. IDENTITY
mode_id: relationship-mapping
canonical_name: Relationship Mapping
suffix_rule: analysis
educational_name: structural relationship mapping

# 1. TERRITORY AND POSITION
territory: T11-structural-relationship-mapping
gradation_position:
  axis: specificity
  value: general
adjacent_modes_in_territory:
  - mode_id: spatial-reasoning
    relationship: specificity variant (visual-input — structural gap detection on diagrams)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "how do these connect"
    - "what affects what"
    - "draw the connections"
    - "I want to see the structure"
  prompt_shape_signals:
    - "relationship map"
    - "causal DAG"
    - "dependency graph"
    - "concept map of"
    - "what relates to what"
disambiguation_routing:
  routes_to_this_mode_when:
    - "relationships are static or acyclic; no feedback loops dominate"
    - "user wants the topology of inter-element connections"
  routes_away_when:
    - "relationships involve feedback loops, delays, or emergent behaviour" → systems-dynamics-causal (T4) or systems-dynamics-structural (T17)
    - "user submits a diagram and asks 'what's missing' from it" → spatial-reasoning (visual-input variant within T11)
    - "user wants to understand a single concept deeply rather than its connections" → deep-clarification (T10)
    - "user is orienting in unfamiliar territory and wants the lay of the land" → terrain-mapping (T14)
when_not_to_invoke:
  - "Question is about how this works (mechanism), not how the parts relate (structure)" → mechanism-understanding (T16)
  - "Question is about temporal flow or process sequence" → process-mapping (T17)
  - "Diagram is the input and gap detection is the question" → spatial-reasoning

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [entities_named, relationship_types_understood, focal_question]
    optional: [prior_relationship_graph, exposure_outcome_pair]
    notes: "Applies when user supplies entity inventory and uses relational vocabulary (causal, correlational, dependency)."
  accessible_mode:
    required: [domain_or_situation_to_be_mapped]
    optional: [some_entities_named, hint_at_what_should_relate_to_what]
    notes: "Default. Mode infers entities from the situation and surfaces typed relationships."
  detection:
    expert_signals: ["DAGitty", "causal DAG", "exposure", "outcome", "confounder", "concept map", "linking phrase", "is_cross_link"]
    accessible_signals: ["how do these connect", "what relates to what", "show me the structure", "draw the connections"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What entities or concepts do you want mapped, and what's the question the map should answer?'"
    on_underspecified: "Ask: 'Are the relationships static, or do feedback loops matter? If feedback loops, route to systems-dynamics-causal (T4) or systems-dynamics-structural (T17) per parse.'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Is every connection labelled with its type (causal / correlational / dependency / influential / structural) and directionality?"
    failure_mode_if_unmet: causation-correlation-trap
  - cq_id: CQ2
    question: "Have ≥2 non-obvious connections been surfaced, with at least one cross-link in concept-map outputs?"
    failure_mode_if_unmet: kitchen-sink-or-flat-tree
  - cq_id: CQ3
    question: "Is the output structured as a relational map, not flattened into a linear narrative?"
    failure_mode_if_unmet: linear-reduction
  - cq_id: CQ4
    question: "Is the output genuinely acyclic — no feedback loops smuggled into a DAG?"
    failure_mode_if_unmet: silent-cycle

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: linear-reduction
    detection_signal: "Output reads as a sequential narrative rather than a structured map."
    correction_protocol: re-dispatch (restructure as relational map)
  - name: kitchen-sink-or-flat-tree
    detection_signal: "Map is dense without significance, OR map is a flat tree with no cross-links."
    correction_protocol: re-dispatch (trim to significant connections; add ≥1 cross-link)
  - name: causation-correlation-trap
    detection_signal: "A correlational connection is labelled causal without mechanistic evidence."
    correction_protocol: flag (default to weakest relationship type the evidence supports)
  - name: silent-cycle
    detection_signal: "DAG contains a cycle without transition to systems-dynamics-causal (T4) or systems-dynamics-structural (T17)."
    correction_protocol: re-dispatch (either remove edge with rationale or transition)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - dagitty-causal-dag-formalism (when causal framing dominates)
    - novak-concept-map-tradition (when heterogeneous relations dominate)
    - pearl-causal-graphs
  foundational:
    - structural-relationship-taxonomy

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: spatial-reasoning
    when: "User has submitted a diagrammatic visual input and wants gap detection (specificity-visual-input variant)."
  sideways:
    target_mode_id: systems-dynamics-causal
    when: "Mapping reveals feedback loops; structure is no longer acyclic."
  downward:
    target_mode_id: null
    when: "Relationship Mapping is the territory founder; no lighter mode exists in T11."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Relationship Mapping is the precision with which connection type and directionality are assigned. A thin pass names entities and draws lines; a substantive pass labels each connection (causal / correlational / dependency / influential / structural), assigns directionality where defensible, and tests every claimed causal connection for mechanism. Test depth by asking: could each labelled connection be falsified by a specific observation? Each connection in prose carries a literal type prefix.

## BREADTH ANALYSIS GUIDANCE

Breadth in Relationship Mapping is the catalog of entities and connections, including non-obvious ones. Widen the lens to identify ≥2 non-obvious connections, surface the organising structure (hub-and-spoke / chain / hierarchy / network / bipartite), and note connections to adjacent domains. Breadth markers: at least one cross-link in concept-map outputs (Novak's marker of integrative understanding); at least two non-obvious connections explicitly named; organising structure named.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Relationship Mapping is a typed acyclic structural map: entities are inventoried, every edge between them carries an explicit type (causal / correlational / dependency / influential / structural) and directionality, and the organising topology (hub-and-spoke / chain / hierarchy / network / bipartite / tree-with-cross-links) is itself a finding. Reads in DAGitty causal-DAG formalism when framing is causal (Pearl-style), in the Novak concept-map tradition when relations are heterogeneous, and in the structural-relationship taxonomy generally. It is distinct from spatial-reasoning (the visual-input variant — structural gap detection on diagrams), from systems-dynamics-causal / structural (T4 / T17 — feedback-loop dynamics rather than acyclic structure), and from deep-clarification (T10 — understanding a single concept rather than its connections).

**Procedure.**

1. Lock the focal question — what the map should answer, in one sentence; entities and connections earn their place against this lock.
2. Inventory entities scoped to the focal question — not an exhaustive ontology.
3. Type each connection from the canonical set (`causal` / `correlational` / `dependency` / `influential` / `structural`) with directionality (`→` / `↔` / undirected); when evidence is ambiguous between causal and correlational, the weaker label survives with a mechanism-candidate flag.
4. Test every claimed causal connection for mechanism — patterns without mechanism are downgraded to correlational.
5. Surface ≥2 non-obvious connections; in concept-map outputs include ≥1 cross-link that bridges otherwise-separate branches (Novak's integrative-understanding marker).
6. Name the organising topology — hub-and-spoke / chain / hierarchy / network / bipartite / tree-with-cross-links — with what the structure implies.
7. Run the acyclicity check — trace every directed path; if any path returns to its start, the cycle is named explicitly with sideways-route to systems-dynamics-causal (historical-state) or systems-dynamics-structural (present behaviour), never silently severed.
8. State the boundary explicitly — what the map omits and why; adjacent mappings that cover the omissions.
9. Assign confidence per edge — causal claims with mechanism are higher-confidence; correlational claims are labelled explicitly.

**Goal.** Produce a typed relational map where every connection carries an operative type and directionality, non-obvious connections and cross-links surface explicitly, and acyclicity is honoured (cycles route sideways to systems-dynamics modes rather than being hidden).

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — edge-type and directionality (load-bearing).** Is every connection labelled with its type (causal / correlational / dependency / influential / structural) and directionality? Mislabelling correlational edges as causal corrupts every downstream reading. Failure mode if unmet: `causation-correlation-trap`.
- **CQ2 — non-obvious connections and cross-links.** Have ≥2 non-obvious connections been surfaced, with at least one cross-link in concept-map outputs? Failure mode if unmet: `kitchen-sink-or-flat-tree`.
- **CQ3 — map structure not linear narrative.** Is the output structured as a relational map, not flattened into a linear narrative? Failure mode if unmet: `linear-reduction`.
- **CQ4 — acyclicity (load-bearing).** Is the output genuinely acyclic — no feedback loops smuggled into a DAG? Cycles route sideways to systems-dynamics modes rather than being silently closed. Failure mode if unmet: `silent-cycle`.

A passing output types every connection from the canonical set with directionality, surfaces ≥2 non-obvious connections (≥1 cross-link in concept-map outputs), names the organising topology, structures as relational map rather than linear narrative, handles any cycle by transition to systems-dynamics-causal or systems-dynamics-structural rather than silent severance, and includes a boundary statement.

**Named failure modes.**

- *linear-reduction* — output reads as a sequential narrative rather than a structured map.
- *kitchen-sink-or-flat-tree* — map is dense without significance, OR map is a flat tree with no cross-links.
- *causation-correlation-trap* — a correlational connection is labelled causal without mechanistic evidence.
- *silent-cycle* — DAG contains a cycle without transition to systems-dynamics-causal (T4) or systems-dynamics-structural (T17).

## REVISION GUIDANCE

Revise to add type prefixes to connections without them. Revise to surface non-obvious connections when only obvious ones appear. Revise to restructure linear narrative as relational map. Resist revising toward dense exhaustive maps when significance is the criterion. Resist revising to retain cycles in a DAG — the structural rule is acyclicity; cycles route to systems-dynamics-causal (T4) or systems-dynamics-structural (T17) per parse.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a typed acyclic relational map: focal-question lock, entity atoms, connection atoms with explicit type (causal / correlational / dependency / influential / structural) and directionality, organising-structure atom, key-relationship atoms (including cross-links), boundary atom naming what the map omits, and acyclicity check**. The atoms are:

1. **Focal-question atom.** The question the map should answer in one short sentence. Subsequent atoms reference this lock; entities included or excluded earn their place against it.

2. **Entity atoms.** Each atom names one entity with a one-phrase characterisation. Entities are scoped to the focal question; the map is not an exhaustive ontology.

3. **Connection atoms.** Each atom carries: source entity, target entity, type (`causal` / `correlational` / `dependency` / `influential` / `structural`), and directionality (`→`, `↔`, undirected). Causation-correlation-trap is the named failure mode the consolidator watches for; correlational connections labelled causal without mechanism get reshaped to the weakest type the evidence supports.

4. **Organising-structure atom.** Names the topology — `hub-and-spoke` / `chain` / `hierarchy` / `network` / `bipartite` / `tree-with-cross-links`. The structural pattern is itself a finding.

5. **Key-relationship atoms — including non-obvious connections.** At least two non-obvious connections surface, plus at least one cross-link in concept-map outputs (Novak's marker of integrative understanding). Kitchen-sink-or-flat-tree is the named failure mode; dense maps without significance, or flat trees with no cross-links, get reshaped.

6. **Boundary atom.** Names what the map omits — entities and connections deliberately excluded as out-of-scope or as belonging to adjacent mappings.

7. **Acyclicity-check atom.** A standing atom: does the map contain any cycle? Silent-cycle is the named failure mode; cycles smuggled into a DAG without transition get reshaped (either remove the edge with rationale, or sideways-route to systems-dynamics-causal / systems-dynamics-structural).

8. **Linear-reduction flag — when applicable.** Where the corpus drifted to a sequential narrative rather than a relational map, the flag is preserved. Linear-reduction is the named failure mode.

9. **Confidence per finding.** Each connection-type claim carries confidence (causal claims with mechanistic backing are higher-confidence; correlational claims are explicitly labelled).

**Mode-specific bloat patterns to cut:**

- **Linear reduction** — sequential narrative replacing relational map.
- **Kitchen sink** — every entity connected to every other without significance criterion.
- **Flat tree** — strict hierarchy with no cross-links; missing integrative connections.
- **Causation-correlation conflation** — causal label on correlational evidence.
- **Silent cycle** — cycle present in something declared as DAG.
- **Untyped connection** — lines drawn without `causal` / `correlational` / `dependency` / `influential` / `structural` label.
- **Directionless connection** — directed relationship rendered without arrows; the directionality is part of the finding.

**What NOT to collapse:**

- **Stream disagreement about connection type** — when one stream labelled an edge causal and another correlational, the disagreement surfaces with reasoning; the corpus defaults to the weaker type.
- **Cross-link disagreements** — when streams identified different non-obvious connections, both survive; cross-links are themselves the integrative finding.
- **Boundary disagreements** — when streams drew the map's scope differently, both boundary statements are preserved.
- **Cycles that route sideways** — when a cycle is detected, the corpus *names* it explicitly with sideways-route guidance, rather than silently severing the loop.

## VERIFICATION CRITERIA

Verified means: every connection has a stated type and directionality; ≥2 non-obvious connections surfaced; organising structure named; output structured as a relational map (not linear narrative); acyclicity honoured (any cycle handled via transition to systems-dynamics-causal or systems-dynamics-structural per parse); boundary statement names what the map omits. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **typed relational map** — a diagram-friendly structured analysis where every connection carries an operative type and directionality, non-obvious connections and cross-links surface explicitly, and acyclicity is honoured (cycles route sideways to systems-dynamics modes). Place the consolidated-corpus atoms into the following sections, in this order:

1. **Focal question.** One short paragraph stating the question the map answers and the scope it implies.

2. **Entities.** Bulleted list. Each: `**[Entity]** — one-phrase characterisation. Role in the map: [...].`

3. **Connections with type and directionality.** A table or bulleted list. Each: `**[Source] → [Target]** — type: [causal / correlational / dependency / influential / structural]. Directionality: [→ / ↔ / undirected]. Evidence basis: [mechanism if causal; pattern if correlational; reference if dependency / structural].`

4. **Organising structure.** One paragraph naming the topology: `**Topology:** [hub-and-spoke / chain / hierarchy / network / bipartite / tree-with-cross-links]. **What this structure implies:** [...].`

5. **Key relationships.** Bulleted list of the connections the map foregrounds. Each: `**[Source] → [Target]** — why this connection matters for the focal question: [...]. Whether it is obvious or non-obvious: [...].` At least two non-obvious connections surface; concept-map outputs carry at least one cross-link.

6. **Boundary statement.** One paragraph naming what the map omits and why. `What this map does not address: [...]. Adjacent mappings that would cover the omissions: [...].`

7. **Acyclicity check.** One labelled line. `**Acyclic:** [yes — the map is a DAG / no — a cycle is present at: [path]].` When a cycle is present, the deliverable carries a sideways-route note: `**Cycle detected:** the [path] forms a feedback loop. Sideways-route to systems-dynamics-causal (if loop drives historical-state explanation) or systems-dynamics-structural (if loop drives present behaviour) is the appropriate operation.`

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Connection-type vocabulary (`causal` / `correlational` / `dependency` / `influential` / `structural`) appears verbatim on every edge. Untyped edges are reshaped at this layer.
- Directionality appears explicitly — `→` for directed edges, `↔` for bidirectional, no arrow for undirected. Mixed-directionality maps that hide the distinction are reshaped.
- When envelope-bearing rendering is appropriate: `concept_map` for heterogeneous relations (Novak tradition); `causal_dag` for specifically causal framings with focal exposure and outcome (DAGitty DSL). Concept maps require ≥4 concepts, ≥2 linking phrases, ≥3 propositions, and ≥1 cross-link. Causal DAGs are acyclic with focal_exposure and focal_outcome resolvable to declared nodes.
- When streams diverged on connection-type for the same edge, the deliverable renders the disagreement inline: `**[Source] → [Target]:** stream A: causal (mechanism X); stream B: correlational (no mechanism). Default to correlational; mechanism candidate noted for further test.`
- When the linear-reduction flag survived consolidation, the deliverable opens with: `**Note: portions of the consolidated corpus drifted toward sequential narrative. The relational structure below has been reshaped from the narrative; if further structural reduction is wanted, deeper concept-mapping is the route.**`
- The acyclicity check (section 7) is not optional. Acyclicity is the mode's structural commitment; cycles surface explicitly with sideways-route rather than being hidden.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- CAF
- Concept Fan
- Challenge
- FIP

Mental models (always loaded):
- emergence
- feedback-loops
- alexander-pattern-language
- niches
- scale
- equilibrium
- leverage

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `produces`, `enables`, `requires`
**Deprioritize:** `contradicts`, `supersedes`

*Family: mechanism-structure. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
