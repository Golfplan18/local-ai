---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Domain Induction

```yaml
# 0. IDENTITY
mode_id: domain-induction
canonical_name: Domain Induction
suffix_rule: analysis
educational_name: domain induction (orient + terrain-map + induct what to learn)

# 1. TERRITORY AND POSITION
territory: T14-orientation-in-unfamiliar-territory
gradation_position:
  axis: depth
  value: molecular
adjacent_modes_in_territory:
  - mode_id: quick-orientation
    relationship: depth-light sibling
  - mode_id: terrain-mapping
    relationship: depth-thorough sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I'm stepping into a new domain and I want a structured induction, not just a quick orientation"
    - "I need to know what's here, what's connected to what, and what to learn next, in that order"
    - "willing to spend the time to be inducted properly"
    - "I want a map plus a learning plan, not just a map"
  prompt_shape_signals:
    - "domain induction"
    - "induct me into"
    - "structured onboarding to a domain"
    - "what to learn next in this field"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated induction spanning quick orientation + terrain map + structured learning sequence"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want fast lay-of-the-land in a few minutes" → quick-orientation
    - "want thorough terrain mapping without learning sequence" → terrain-mapping
    - "the question is really generative exploration of an open space" → passion-exploration (T20)
when_not_to_invoke:
  - "User has time pressure" → quick-orientation
  - "User already has terrain-map and only needs the learning sequence" → run terrain-mapping output forward into a focused induction synthesis stage rather than full molecular pass

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: quick-orientation
      runs: fragment
      fragment_spec: "light-orientation-only — produce the rapid lay-of-the-land (key terms, dominant figures, central debates) as breadth seed; do not produce full quick-orientation output"
    - mode_id: terrain-mapping
      runs: full
  synthesis_stages:
    - name: orientation-and-terrain-merge
      type: parallel-merge
      input: [quick-orientation-fragment, terrain-mapping]
      output: "merged orientation: rapid lay-of-the-land integrated with thorough terrain map; what is here is named and structured"
    - name: connectivity-mapping
      type: sequenced-build
      input: [orientation-and-terrain-merge]
      output: "what's-connected-to-what: relations among elements (concepts, figures, debates, methods); identification of central nodes and bridge concepts"
    - name: structured-induction
      type: dialectical-resolution
      input: [orientation-and-terrain-merge, connectivity-mapping]
      output: "domain induction document with three integrated parts: (a) what is here; (b) what's connected to what; (c) what to learn next, sequenced by dependency"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; if connectivity cannot be inferred with confidence, document as conjectural-mapping rather than presenting as established

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [domain_name, prior_familiarity_level, induction_goal]
    optional: [time_budget_for_learning, prior_resources_consulted]
    notes: "Applies when user supplies prior familiarity level or induction goal."
  accessible_mode:
    required: [domain_name]
    optional: [why_interested, contextual_background]
    notes: "Default. Mode elicits prior familiarity and induction goal during execution."
  detection:
    expert_signals: ["prior familiarity", "induction goal", "structured onboarding"]
    accessible_signals: ["new to", "want to learn about", "just getting started in"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the domain you want to induct into, and what's your goal — research-level, working-knowledge, or general-orientation?'"
    on_underspecified: "Ask the user whether they want the full Domain Induction molecular pass or a lighter Quick Orientation / Terrain Mapping read."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the orientation surveyed the domain broadly enough, or has it privileged the dominant subfield?"
    failure_mode_if_unmet: dominant-subfield-bias
  - cq_id: CQ2
    question: "Does the connectivity-mapping actually identify dependencies and bridges, or does it list elements without showing relations?"
    failure_mode_if_unmet: relation-omission
  - cq_id: CQ3
    question: "Is the what-to-learn-next sequence ordered by genuine dependency, or by analyst convenience?"
    failure_mode_if_unmet: arbitrary-sequencing
  - cq_id: CQ4
    question: "Does the induction respect the user's stated familiarity level and goal, or does it default to a generic survey?"
    failure_mode_if_unmet: goal-disconnection

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: dominant-subfield-bias
    detection_signal: "What-is-here section over-represents one subfield; minority traditions or competing schools are absent."
    correction_protocol: re-dispatch (with explicit breadth prompt)
  - name: relation-omission
    detection_signal: "What's-connected-to-what is a list of elements without arrows, dependencies, or bridge concepts."
    correction_protocol: re-dispatch
  - name: arbitrary-sequencing
    detection_signal: "Learning sequence reads as alphabetical or import order rather than dependency-ordered."
    correction_protocol: re-dispatch
  - name: goal-disconnection
    detection_signal: "Induction is generic; ignores the stated familiarity level or induction goal."
    correction_protocol: flag and re-dispatch

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - bloom-taxonomy (when learning sequence requires cognitive-level scaffolding)
    - novice-expert-cognition (when familiarity level is novice)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Domain Induction is the heaviest mode in T14."
  sideways:
    target_mode_id: null
    when: "No within-T14 stance/complexity sibling beyond depth ladder."
  downward:
    target_mode_id: terrain-mapping
    when: "User has time pressure or scope is narrower than initially estimated."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Domain Induction is the degree to which the connectivity-mapping and structured-induction stages produce a learning architecture that no single quick-orientation or terrain-mapping pass could have produced. A thin molecular pass concatenates orientation, terrain, and learning list; a substantive pass identifies central nodes (concepts that other concepts depend on), bridge concepts (linking subfields), and dependency-ordered sequence. Test depth by asking: would the learning sequence change if a single central-node concept were removed?

## BREADTH ANALYSIS GUIDANCE

Breadth in Domain Induction is the catalog of subfields and traditions surveyed in the orientation and terrain-mapping stages. Widen the lens to scan: dominant subfield; minority traditions; cross-disciplinary inflows; methodological alternatives; historical figures vs. contemporary figures. Even when the learning sequence narrows to a focused path, breadth is documented in the what-is-here section so the user can see what's being deferred and what's being prioritized.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Domain Induction is a molecular three-layer induction — quick-orientation fragment + full terrain-mapping + connectivity-mapping synthesised into a dependency-ordered learning architecture for a user with a stated familiarity level and induction goal (research-level / working-knowledge / general-orientation). It is distinct from quick-orientation (which gives fast lay-of-the-land in a few minutes), from terrain-mapping (which produces a thorough terrain map without a learning sequence), and from passion-exploration (which is generative exploration of an open space rather than structured induction). The mode does pedagogy, not surveying — what distinguishes the deliverable is the connectivity-graph and dependency-ordered sequence that lift a real reader from their stated familiarity toward their stated goal.

**Procedure.**

1. Lock domain, user familiarity level (novice / intermediate / advanced), and induction goal (research-level / working-knowledge / general-orientation) — these three anchor everything downstream.
2. Run quick-orientation fragment — rapid lay-of-the-land: key terms, dominant figures, central debates as breadth seed.
3. Run terrain-mapping in full — survey what's here, including minority traditions, competing schools, cross-disciplinary inflows, historical vs contemporary figures.
4. Tag each element by dominance: `dominant-subfield` / `minority-tradition` / `cross-disciplinary-inflow` / `historical` / `contemporary` — at least one minority-tradition or competing-school element must appear.
5. Build connectivity graph — for each pair, name the edge type (`depends-on` / `extends` / `analogous-to` / `opposes` / `bridges-subfields` / `supersedes`) and the substantive reason. Elements without edges are isolated-element residue.
6. Identify central nodes (highest in-degree — concepts other concepts depend on) and bridge concepts (linking otherwise-separate subfields).
7. Produce a dependency-ordered learning sequence — each item names prerequisite items (by canonical ID), a Bloom-tag (`remember` / `understand` / `apply` / `analyze` / `evaluate` / `create`), and a rationale for its position. The sequence is ordered by genuine prerequisite relationships, not by alphabet, chronology, or analyst convenience.
8. Scaffold by familiarity — novice sequences concentrate at understand-and-apply rather than evaluate-and-create; inverted progressions are pedagogical malformation.
9. Render familiarity-tagged guidance per learning item — the annotations vary visibly across novice / intermediate / advanced (if all three would read the same, the induction has collapsed into generic survey).
10. Tag conjectural edges as conjectural — connectivity-graph speculation in unfamiliar domains is real; don't present as established.

**Goal.** Produce a three-layer induction document — what's here / what's connected / what to learn next — tagged by familiarity level and induction goal, with Bloom-tagged learning items and a connectivity-graph that distinguishes the induction from a flat survey.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — breadth before narrowing.** Has the orientation surveyed beyond the dominant subfield (minority traditions, competing schools, cross-disciplinary inflows)? Failure mode if unmet: `dominant-subfield-bias`.
- **CQ2 — connectivity over enumeration (load-bearing).** Does the connectivity-mapping actually identify dependencies and bridges, or does it list elements without showing relations? Failure mode if unmet: `relation-omission`.
- **CQ3 — dependency-ordered sequencing (load-bearing).** Is the what-to-learn-next sequence ordered by genuine prerequisite relationships, or by alphabet / chronology / analyst convenience? Failure mode if unmet: `arbitrary-sequencing`.
- **CQ4 — goal and familiarity grounding.** Does the induction respect the user's stated familiarity level and goal, or does it default to a generic survey? Failure mode if unmet: `goal-disconnection`.

A passing output locks domain, familiarity, and goal; surveys what-is-here with at least one minority-tradition element; builds a connectivity graph with edges carrying both relation type and substantive reason; identifies central nodes and bridges; orders the learning sequence by dependency with Bloom tags; produces familiarity-tagged guidance that reads visibly differently across novice / intermediate / advanced; and tags conjectural edges as such.

**Named failure modes.**

- *dominant-subfield-bias* — what-is-here over-represents one subfield; minority traditions or competing schools absent.
- *relation-omission* — what's-connected-to-what is a list of elements without arrows, dependencies, or bridge concepts.
- *arbitrary-sequencing* — learning sequence reads as alphabetical or import order rather than dependency-ordered.
- *goal-disconnection* — induction is generic; ignores the stated familiarity level or induction goal.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to add bridge concepts and central nodes where the draft lists elements without showing relations. Revise to re-sequence the learning path where dependencies are out-of-order. Resist revising toward a generic survey when the stated goal is more focused (research-level vs. working-knowledge vs. general-orientation).

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **three integrated layers — what-is-here atoms, connectivity-graph atoms, and dependency-ordered learning-sequence atoms — tagged with user familiarity level and induction goal**. The connectivity graph is the bridge between orientation (what's here) and pedagogy (what to learn next); without it, the corpus is concatenation rather than induction. The atoms are:

1. **Domain-and-goal atom.** The domain name, user's stated familiarity level (novice / intermediate / advanced), and induction goal (research-level / working-knowledge / general-orientation), stated once at the corpus head. The goal atom is load-bearing — goal-disconnection is the named failure mode, and a generic survey not anchored to the stated goal is its corpus signature.

2. **What-is-here element atoms.** Each carries: element (subfield / dominant figure / central debate / method / canonical text / contemporary practitioner), tradition affiliation, and dominance tag (dominant-subfield / minority-tradition / cross-disciplinary-inflow / historical / contemporary). At least one minority-tradition or competing-school element must survive cross-stream dedup or CQ1 fails (dominant-subfield-bias).

3. **Connectivity-graph atoms.** Each is a relation between two element atoms, carrying: source element, target element, relation type (depends-on / extends / analogous-to / opposes / bridges-subfields / supersedes), and the substantive reason for the relation. Element atoms without at least one connectivity edge are isolated-element residue; either an edge is found or the element's load-bearingness is questioned. Relation-omission is the named failure mode; a corpus that lists elements without relations is its signature.

4. **Central-node and bridge-concept atoms.** Derived atoms identifying: central nodes (elements with the highest in-degree in the connectivity graph — concepts other concepts depend on), and bridge concepts (elements that link otherwise-separate subfields). These atoms anchor the learning sequence's prioritization: central nodes and bridges learn first.

5. **Learning-sequence atoms — dependency-ordered.** Each carries: item (specific resource, paper, book, experience), prerequisite items (by canonical IDs), cognitive-level tag per Bloom (remember / understand / apply / analyze / evaluate / create), and rationale (why this item at this position). The sequence is dependency-ordered, not alphabetical or chronological; arbitrary-sequencing is the named failure mode. When familiarity level is novice, novice-expert-cognition shapes the early items toward understanding-level scaffolding rather than evaluation-level engagement.

6. **Familiarity-level-tagged guidance atoms.** Per learning-sequence item, an annotation atom: what a novice needs to understand at this item vs what an expert would already know. Goal-disconnection is the failure mode this addresses; a research-level induction skips the novice-scaffolding atoms, a general-orientation induction leans on them.

7. **Confidence map.** Confidence markers attach to individual atoms (especially connectivity-graph edges, where conjectural mapping is common). When the two streams assigned different confidences, audit conservatism applies (the lower confidence survives). Edges flagged as conjectural-mapping survive into the corpus tagged as conjectural rather than as established relations.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Element-listing without connectivity** — what-is-here items stated as a flat enumeration without edges to other items. Relation-omission residue; either an element earns at least one connectivity edge or its survival into the corpus is questioned.
- **Dominant-subfield padding** — both streams may over-elaborate the dominant subfield's elements while neglecting minority traditions. Dominant-subfield-bias residue; the corpus carries a minimum minority-tradition presence even after dedup.
- **Generic-survey residue** — content that could apply to any introduction to any field ("the field has a long and rich history", "many practitioners contribute to ongoing debates"). Goal-disconnection residue; generic content does not survive when the user's goal is specific.
- **Arbitrary-sequencing language** — learning items listed in alphabetical or import order without prerequisite chains. The sequence is reordered by dependency or the items do not survive as a "sequence" — they survive only as a list with explicit "no dependency order extractable" tag.
- **Resource-overload** — both streams may recommend many resources for the same learning step. Single canonical resource per step survives (the one with strongest rationale), with alternatives noted as "comparable substitutes" only when genuinely substitutable.
- **Bloom-tag absence** — learning items without cognitive-level tags. The Bloom tag is operative for sequencing (cannot move from understand to create without the intermediate levels for novices); items without tags get them inferred from rationale, or are dropped if the rationale is absent.

**What NOT to collapse:**

- **Dominant-vs-minority tradition disagreement** — when streams identified different traditions as dominant in the domain, preserve both readings as parallel tradition-affiliation atoms. The disagreement is a finding about the domain's contested centering, not bloat to resolve.
- **Connectivity-edge disagreement** — when one stream surfaced a depends-on relation and the other did not, preserve the disagreement. Whether element B depends on element A is consequential for sequencing; silent reconciliation is connectivity-mapping injection.
- **Learning-sequence ordering disagreement** — when streams produced different dependency orderings for the same items, preserve both orderings as parallel sequence atoms with their respective rationales. The user (or the formatter at step 8) can see which ordering is more rigorously dependency-grounded.

## VERIFICATION CRITERIA

Verified means: orientation surveyed broadly; terrain-mapping ran fully; connectivity-mapping shows relations not just elements; learning sequence is dependency-ordered; user's familiarity level and induction goal are reflected; confidence map is populated. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **three-layer induction document — what's here / what's connected / what to learn next — tagged by familiarity level and induction goal, with Bloom-tagged learning items**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Domain, familiarity, and goal.** Three short labelled lines at the top:
   - **Domain:** [name]
   - **User familiarity:** [novice / intermediate / advanced]
   - **Induction goal:** [research-level / working-knowledge / general-orientation]

2. **What is here.** Numbered list of domain elements (E1, E2, …). Each element: `**[Element name]** — [one-line characterization]. Tradition: [affiliation]. Tag: [dominant-subfield / minority-tradition / cross-disciplinary-inflow / historical / contemporary].` At least one minority-tradition or competing-school element appears — dominant-subfield-bias is the named failure mode.

3. **What's connected to what.** Numbered list of connectivity edges between elements. Each edge: `E_n → E_m: [relation type — depends-on / extends / analogous-to / opposes / bridges-subfields / supersedes]. Reason: [substantive reason for the relation].` Relation-omission is the named failure mode; a deliverable that lists elements without edges is its corpus signature.

4. **Central nodes and bridge concepts.** Two short bulleted blocks:
   - **Central nodes:** elements with the highest in-degree in the connectivity graph — concepts other concepts depend on. Each bullet: `E_n: depends-on relations from [list of E_m elements].`
   - **Bridge concepts:** elements linking otherwise-separate subfields. Each bullet: `E_n: bridges [subfield A] ↔ [subfield B].`

5. **What to learn next — sequenced.** Numbered list. Each item: `**[Resource / paper / book / experience]** — prerequisite items: [list of prior items by canonical ID]. Bloom-tag: [remember / understand / apply / analyze / evaluate / create]. Rationale: [why this item at this position in the sequence].` The sequence is dependency-ordered, not alphabetical or chronological. Arbitrary-sequencing is the named failure mode.

6. **Learning dependencies and prerequisites — graph view.** A small dependency graph (text-rendered DAG) showing the prerequisite chain among the learning-sequence items. When the chain is linear, render as: `Item 1 → Item 2 → Item 3 → ...`. When branching, render as a small ASCII tree or as a per-item parent list.

7. **Familiarity-tagged guidance.** Per learning-sequence item, a short annotation: `Item [N] for [user familiarity level]: [what to focus on at this level — for novice: scaffolding / for intermediate: comparison / for advanced: critique].` Goal-disconnection is the named failure mode; the annotations vary by familiarity level rather than reading as generic guidance.

8. **Confidence map.** Bulleted list of confidence markers attached to connectivity-graph edges (where conjectural mapping is common) and to the learning-sequence ordering. Edges flagged as conjectural-mapping appear tagged as conjectural rather than as established relations.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Element IDs (E1, E2, …) are referenced consistently throughout once introduced.
- Connectivity edges always carry both relation type AND substantive reason — bare "X relates to Y" does not appear.
- Bloom tags use canonical six-level vocabulary; do not invent intermediate levels.
- Section 7's familiarity-tagged guidance reads visibly different for novice vs intermediate vs advanced — if all three would read the same, the goal-tagging has collapsed into generic-survey residue.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10+min
- **Context Budget:** extended

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `analogous-to`, `requires`, `extends`
**Deprioritize:** `contradicts`, `supersedes`

*Family: orientation-exploration. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
