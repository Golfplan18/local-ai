---
nexus:
  - ora
type: mode
tags:
  - framework/instruction
  - architecture
date created: 2026-06-01
date modified: 2026-06-01

---

# MODE: Market Dynamics

```yaml
# 0. IDENTITY
mode_id: market-dynamics
canonical_name: Market Dynamics
suffix_rule: analysis
educational_name: market and economic-system behavior analysis (supply-demand / selection / network-effects lineage)

# 1. TERRITORY AND POSITION
territory: T17-process-and-system-analysis
gradation_position:
  axis: specificity
  value: market-system
adjacent_modes_in_territory:
  - mode_id: systems-dynamics-structural
    relationship: specificity sibling (general feedback system vs. specifically a market/economic system)
  - mode_id: process-mapping
    relationship: specificity sibling (sequenced workflow vs. market behavior)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "how will this market behave / how does this market work"
    - "what happens to prices/rents/wages if supply or demand changes"
    - "why is this industry consolidating / fragmenting"
    - "will this network effect tip, and where is the critical mass"
    - "how do competitive dynamics play out in this market over time"
  prompt_shape_signals:
    - "supply and demand"
    - "market equilibrium / price equilibrium"
    - "network effects / critical mass / tipping point"
    - "creative destruction / disruption dynamics"
    - "market dynamics"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the system under analysis is a market or economy and the question is how it behaves (prices, quantities, competition, selection, network effects)"
    - "user wants the descriptive economic dynamics, not the design of a mechanism or contract"
    - "supply-and-demand, selection, or network-effect dynamics are the operative structure"
  routes_away_when:
    - "the task is to DESIGN a mechanism, auction, contract, or incentive scheme (information asymmetry, hidden action)" → mechanism-design (T18)
    - "the system is a non-market feedback structure (an organization, a workflow)" → systems-dynamics-structural (T17 sibling)
    - "the question is why one specific past market event happened (backward causal trace)" → root-cause-analysis or systems-dynamics-causal (T4)
    - "the task is to choose among options given the market read" → decision-architecture (T3)
when_not_to_invoke:
  - "User wants a mechanism/market DESIGNED rather than market behavior ANALYZED" → mechanism-design (T18)
  - "User wants the principle-level account of how parts produce behavior, not the market dynamics" → mechanism-understanding (T16)

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [market_or_economic_system, dynamic_or_question, time_horizon]
    optional: [participant_inventory, prior_equilibria, elasticity_or_quantitative_data]
    notes: "Applies when the user supplies a defined market with an explicit dynamic of interest and a time horizon (short-run vs long-run)."
  accessible_mode:
    required: [market_description]
    optional: [related_context, question_of_interest]
    notes: "Default. Mode elicits the time horizon and which side(s) of the market matter during execution."
  detection:
    expert_signals: ["elasticity coefficient", "partial equilibrium", "general equilibrium", "comparative statics", "price elasticity of"]
    accessible_signals: ["how will this market behave", "what happens to prices if", "supply and demand", "network effects", "critical mass", "diminishing returns", "creative destruction", "Red Queen", "Gresham's law", "why is this industry consolidating"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Which market do you want analyzed, and what change or dynamic are you asking about (a price move, entry of a competitor, a network tipping)?'"
    on_underspecified: "Ask: 'Are you asking how this market BEHAVES (Market Dynamics), or do you want a mechanism / auction / contract DESIGNED (Mechanism & Incentive Analysis)? The first describes; the second designs.'"

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are both sides of the market modeled (supply AND demand), or has the analysis silently fixed one side?"
    failure_mode_if_unmet: one-sided-market
  - cq_id: CQ2
    question: "Is the equilibrium (or disequilibrium) identified, with the adjustment process that moves the market toward or away from it?"
    failure_mode_if_unmet: equilibrium-unstated
  - cq_id: CQ3
    question: "Is the short-run response distinguished from the long-run response (entry, exit, capacity, substitution)?"
    failure_mode_if_unmet: timescale-collapse
  - cq_id: CQ4
    question: "When a named economic dynamic is invoked (Gresham's law, creative destruction, Red Queen, critical mass), is its actual mechanism shown to operate here, or is it a name-drop?"
    failure_mode_if_unmet: dynamic-name-drop
  - cq_id: CQ5
    question: "Does the analysis describe how the market behaves, or has it drifted into prescribing what a participant SHOULD do (which belongs in a decision or mechanism-design mode)?"
    failure_mode_if_unmet: prescriptive-drift

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: one-sided-market
    detection_signal: "Analysis moves price/quantity by changing supply or demand alone without checking the other side's response."
    correction_protocol: re-dispatch (model both sides and their interaction)
  - name: equilibrium-unstated
    detection_signal: "Conclusions asserted without naming the equilibrium or the adjustment process reaching it."
    correction_protocol: flag
  - name: timescale-collapse
    detection_signal: "Short-run and long-run responses conflated; entry/exit/substitution effects ignored."
    correction_protocol: re-dispatch
  - name: dynamic-name-drop
    detection_signal: "A named economic dynamic invoked in prose without its mechanism shown operating on the specific market."
    correction_protocol: re-dispatch
  - name: prescriptive-drift
    detection_signal: "Analysis drifts from describing market behavior to advising a participant what to do — pricing/strategy recommendations appear."
    correction_protocol: re-dispatch (strip prescriptions; route to decision-architecture or mechanism-design if advice is wanted)
  - name: ceteris-paribus-blindness
    detection_signal: "Holds 'all else equal' on variables that the same shock visibly moves, producing a false partial-equilibrium story."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - supply-demand
    - equilibrium
  optional:
    - greshams-law
    - diminishing-returns
    - critical-mass
    - creative-destruction
    - red-queen-effect
    - feedback-loops
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~10min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Market Dynamics is the market-specific structural mode in T17."
  sideways:
    target_mode_id: mechanism-design
    when: "User actually wants a mechanism/contract/auction designed rather than market behavior described — switch to T18 design posture."
  downward:
    target_mode_id: process-mapping
    when: "On inspection there is no market dynamic — a plain process or value-chain map suffices."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Market Dynamics is the rigor of the supply-and-demand mechanics: both sides of the market named with their drivers, the equilibrium (or the disequilibrium and its adjustment process) identified, elasticities reasoned about even when only qualitative, and the short-run response separated from the long-run response (entry, exit, capacity change, substitution). A thin pass asserts "prices will rise"; a substantive pass shows which curve shifts, why, how far the other side accommodates, where the new equilibrium sits, and how the short-run answer differs from the long-run one once participants adjust. Test depth by asking: would another analyst be able to predict the direction AND rough magnitude of the market's response, and name what would have to be true for the prediction to fail?

## BREADTH ANALYSIS GUIDANCE

Breadth in Market Dynamics is the catalog of market forces considered before the read is committed. Widen the lens by scanning which named dynamics might be operating: selection effects (Gresham's law — bad drives out good when quality is hidden; adverse selection adjacency), network effects and critical mass (does value rise with participation, and where is the tipping threshold), diminishing returns (where does the marginal curve bend), competitive coevolution (Red Queen — must run to stand still), and structural disruption (creative destruction — does a new technology destroy the incumbent rent). Breadth markers: at least one alternative dynamic is named and explicitly ruled in or out with reason, and at least one "what would change this read" condition is stated.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Market Dynamics is a descriptive analysis of how a market or economic system behaves — supply-and-demand mechanics, equilibrium and its adjustment, selection effects, network effects, returns to scale, and competitive dynamics over time. It is a market-specific structural mode in T17 (Process and System Analysis): it maps how the market behaves as-it-is, in the same descriptive posture as its T17 sibling `systems-dynamics-structural`, but specialized to economic systems. It is distinct from `mechanism-design` (T18), which DESIGNS incentive structures and contracts rather than describing market behavior; from `systems-dynamics-structural`, which handles non-market feedback systems; and from T4 causal modes, which trace why one specific event happened.

**Procedure.**

1. State the market boundary — what good/service/factor, which participants, what is inside and outside scope.
2. Model both sides — name the demand-side drivers and the supply-side drivers; do not fix one side silently.
3. Identify the equilibrium (or disequilibrium) and the adjustment process that moves the market toward it.
4. Separate short-run from long-run — mark where entry, exit, capacity change, or substitution alters the long-run answer.
5. Reason about elasticity — how responsive each side is to price, qualitatively if no data; flag where the elasticity assumption is load-bearing.
6. Scan named dynamics — selection (Gresham's), network effects / critical mass, diminishing returns, Red Queen coevolution, creative destruction — and rule each in or out with a mechanism, not a name-drop.
7. State the market read descriptively — direction and rough magnitude of the response, and the timescale at which it holds.
8. Reshape out prescriptive language ("the firm should price at…") and surface it as a sideways-route note to decision-architecture or mechanism-design.
9. State confidence with the load-bearing assumptions named — especially any ceteris-paribus holds the same shock would actually disturb.

**Goal.** Produce a descriptive market read: both sides modeled, equilibrium and adjustment named, short-run vs long-run separated, operative named dynamics grounded in mechanism, and a stated read with confidence and the conditions that would overturn it.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — both sides modeled.** Are supply AND demand both modeled, or has one side been silently fixed? Failure mode if unmet: `one-sided-market`.
- **CQ2 — equilibrium and adjustment named.** Is the equilibrium (or disequilibrium) identified with the process that reaches it? Failure mode if unmet: `equilibrium-unstated`.
- **CQ3 — timescale separated.** Is short-run distinguished from long-run (entry/exit/substitution)? Failure mode if unmet: `timescale-collapse`.
- **CQ4 — named dynamics grounded.** Is each invoked dynamic shown operating here, not name-dropped? Failure mode if unmet: `dynamic-name-drop`.
- **CQ5 — descriptive posture.** Does it describe market behavior rather than advise a participant? Failure mode if unmet: `prescriptive-drift`.

A passing output states the market boundary, models both sides, names the equilibrium and its adjustment, separates short-run from long-run, grounds any named dynamic in a working mechanism, and gives a confidence-rated read with the conditions that would overturn it — without sliding into participant advice.

**Named failure modes.**

- *one-sided-market* — price/quantity moved by changing one side without the other's response.
- *equilibrium-unstated* — conclusions without a named equilibrium or adjustment process.
- *timescale-collapse* — short-run and long-run conflated; entry/exit/substitution ignored.
- *dynamic-name-drop* — named economic dynamic invoked without its mechanism shown operating here.
- *prescriptive-drift* — drifts from describing the market to advising a participant (route advice to decision-architecture / mechanism-design).
- *ceteris-paribus-blindness* — "all else equal" held on variables the same shock visibly moves.

## REVISION GUIDANCE

Revise to add the missing side of the market for any conclusion that moved price or quantity from one side alone. Revise to name the equilibrium and adjustment process before any stylistic refinement. Revise to split a conflated timescale into explicit short-run and long-run responses. Strip prescriptive advice that drifted in; if the user wants a recommendation, route to `decision-architecture`, and if they want a mechanism designed, route to `mechanism-design` — do not retrofit advice here. Ground every named dynamic (Gresham's, Red Queen, creative destruction, critical mass) in its actual mechanism on this market or cut the name.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a descriptive market-read atom set: market-boundary lock, two-sided supply/demand atoms, equilibrium-and-adjustment atoms, short-run/long-run atoms, named-dynamic atoms grounded in mechanism, descriptive market-read atoms, and confidence with load-bearing-assumption caveats**. The atoms are:

1. **Market-boundary atom.** What good/service/factor, which participants, what is inside and outside scope.
2. **Supply-side and demand-side atoms.** Each side's drivers, named separately; one-sided-market is the named failure mode the consolidator watches for.
3. **Equilibrium-and-adjustment atoms.** The equilibrium (or disequilibrium) plus the process that moves the market toward it; equilibrium-unstated is the named failure mode.
4. **Short-run / long-run atoms.** The response now vs. after entry, exit, capacity change, or substitution; timescale-collapse is the named failure mode.
5. **Named-dynamic atoms — when applicable.** Each names a dynamic (Gresham's law, diminishing returns, critical mass / network effects, creative destruction, Red Queen) and the mechanism by which it operates on this market; dynamic-name-drop is the named failure mode.
6. **Market-read atoms — descriptive only.** Direction and rough magnitude of the response and the timescale at which it holds; prescriptive-drift is the named failure mode — participant advice is reshaped out and routed onward.
7. **Confidence and assumption-caveat atoms.** Confidence per major claim plus the load-bearing assumptions, especially any ceteris-paribus hold the same shock would disturb.

**Mode-specific bloat patterns to cut:** one-sided market stories, ungrounded equilibrium assertions, timescale conflation, dynamic name-drops, prescriptive advice, and ceteris-paribus blindness.

**What NOT to collapse:** the two-sided structure (both sides preserved), the short-run/long-run distinction, the equilibrium-and-adjustment pairing, and the descriptive posture that separates this mode from decision/mechanism-design.

## VERIFICATION CRITERIA

Verified means: the market boundary is stated; both supply and demand sides are modeled; an equilibrium (or disequilibrium plus adjustment) is named; the short-run response is distinguished from the long-run; any named economic dynamic corresponds to a mechanism shown operating on this market; the read is descriptive (no participant advice); and confidence is stated with the load-bearing assumptions named. Confidence is high only when depth and breadth converged on the direction of the market response.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **descriptive market read** — how the market behaves, with both sides modeled, equilibrium and adjustment named, timescales separated, and operative dynamics grounded. Place the consolidated atoms into these sections, in order:

1. **Market boundary.** One paragraph: `**Market:** [good/service/factor]. **Participants:** [...]. **In scope / out of scope:** [...].`
2. **Supply and demand.** Two labelled blocks: `**Demand side:** drivers [...]; responsiveness (elasticity) [...].` and `**Supply side:** drivers [...]; responsiveness [...].`
3. **Equilibrium and adjustment.** `**Equilibrium:** [where price/quantity settle]. **Adjustment process:** [how the market reaches it].`
4. **Short-run vs long-run.** Two bullets: `**Short run:** [response before adjustment].` `**Long run:** [response after entry/exit/capacity/substitution].`
5. **Named dynamics in play.** Per dynamic: `**[Gresham's law / critical mass / creative destruction / Red Queen / diminishing returns]:** mechanism on this market [...]. Ruled in/out because [...].`
6. **Market read.** Bulleted, descriptive: `**[Direction + rough magnitude of response]** — holds at [timescale]; grounded in [which forces].`
7. **Confidence and assumptions.** Per-claim confidence plus load-bearing assumptions; flag any ceteris-paribus hold the shock would disturb.

**Per-section conventions:**

- Use H2 headings for sections 1 through 7.
- Both market sides appear in section 2; one-sided reads are reshaped.
- Section 6 is *descriptive*. Participant advice ("the firm should…") is reshaped out and surfaced separately: `**Note: participant advice is not part of this mode's contract. For a recommendation, decision-architecture (T3) is the sideways-route; to design a mechanism or contract, mechanism-design (T18).**`
- A supply-demand or quantity-time chart is diagram-friendly and welcome as the centrepiece of section 3 when it carries the argument.
- The mode's parse-preserving discipline (describe the market, don't advise the participant) is enforced throughout.

## CAVEATS AND OPEN DEBATES

Market Dynamics is a new T17 resident (2026-06-01) created to home the market-behavior economics lenses (supply-demand, Gresham's law, diminishing returns, critical mass, creative destruction, Red Queen) that no prior mode loaded. It shares T17's descriptive posture with `systems-dynamics-structural` and is its market-specialized sibling along the territory's specificity axis. The boundary that preserves the parse is the descriptive/prescriptive line: analyzing how a market behaves stays here; designing a mechanism, contract, or incentive scheme routes to `mechanism-design` (T18), and advising a specific participant routes to `decision-architecture` (T3). A standing debate is how far Market Dynamics should reach into general-equilibrium effects (cross-market spillovers) before the analysis should be re-scoped as a multi-market systems problem; v1 keeps the default to partial-equilibrium (single-market) reads with cross-market spillovers flagged, not fully modeled.

---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~10min
- **Context Budget:** default

---

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- CAF
- C&S
- Concept Fan
- APC
- RAD

Mental models (always loaded):
- supply-demand
- equilibrium
- diminishing-returns
- critical-mass
- creative-destruction
- red-queen-effect
- greshams-law
- feedback-loops

---
## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `produces`, `enables`, `requires`
**Deprioritize:** `contradicts`, `supersedes`

*Family: mechanism-structure. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
