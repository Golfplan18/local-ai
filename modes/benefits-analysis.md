---
nexus:
  - ora
type: mode
tags:
date created: 2026-04-17
date modified: 2026-05-01

---

# MODE: Benefits Analysis

```yaml
# 0. IDENTITY
mode_id: benefits-analysis
canonical_name: Benefits Analysis
suffix_rule: analysis
educational_name: balanced benefits-and-strengths analysis (PMI — plus, minus, interesting)

# 1. TERRITORY AND POSITION
territory: T15-artifact-evaluation-by-stance
gradation_position:
  axis: stance
  value: constructive-balanced
adjacent_modes_in_territory:
  - mode_id: steelman-construction
    relationship: stance counterpart (constructive-strong, single position only)
  - mode_id: balanced-critique
    relationship: stance counterpart (neutral, no constructive lean)
  - mode_id: red-team-assessment
    relationship: stance counterpart (adversarial-actor-modeling, assessment)
  - mode_id: red-team-advocate
    relationship: stance counterpart (adversarial-actor-modeling, advocate)
  - mode_id: devils-advocate-lite
    relationship: stance counterpart (adversarial-light, deferred per CR-6)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "have a proposal and want the full picture before deciding"
    - "looking for benefits and risks of one option, not comparing alternatives"
    - "want non-obvious implications surfaced"
  prompt_shape_signals:
    - "what are the benefits and risks of"
    - "pros and cons of"
    - "PMI for"
    - "plus / minus / interesting"
    - "evaluate this proposal"
    - "what's the full picture on"
disambiguation_routing:
  routes_to_this_mode_when:
    - "one proposal, three columns (Plus / Minus / Interesting)"
    - "wants balanced evaluation without recommendation by default"
  routes_away_when:
    - "comparing multiple options" → constraint-mapping (T3)
    - "wants the strongest version of the proposal" → steelman-construction (T15)
    - "wants the adversarial actor stress test for own decision" → red-team-assessment (T15)
    - "wants adversarial argument brief for external use" → red-team-advocate (T15)
    - "wants forward causal cascades over time" → consequences-and-sequel (T6)
when_not_to_invoke:
  - "User wants to choose between alternatives — Benefits Analysis evaluates a single proposal"
  - "User wants a verdict — Benefits Analysis presents the envelope; user decides"

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: constructive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [proposal_stated_precisely, stated_goal_proposal_advances, affected_party_inventory]
    optional: [implementation_history, similar_proposal_outcomes]
    notes: "Applies when user supplies precise proposal text and identifies affected parties."
  accessible_mode:
    required: [proposal_described]
    optional: [context_or_motivation]
    notes: "Default. Mode infers affected parties from the proposal description."
  detection:
    expert_signals: ["affected parties", "stakeholders include", "stated goal is"]
    accessible_signals: ["thinking about doing X", "considering this", "wondering if I should"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the specific proposal you want me to evaluate? More detail makes the analysis more useful.'"
    on_underspecified: "Ask: 'Are you weighing this single proposal, or comparing it against alternatives? Single proposal = Benefits Analysis; alternatives = Constraint Mapping.'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are all three PMI columns populated, or has the analysis collapsed into Plus/Minus only?"
    failure_mode_if_unmet: two-column-trap
  - cq_id: CQ2
    question: "Are claims grounded in the user's specific case, or generic boilerplate?"
    failure_mode_if_unmet: boilerplate-trap
  - cq_id: CQ3
    question: "Has the Interesting column captured at least one second-order implication (precedent, signaling, path-dependency) — or explicitly noted that none was identified?"
    failure_mode_if_unmet: second-order-omission
  - cq_id: CQ4
    question: "Have asymmetries (Plus for one party, Minus for another) been surfaced via the affected-parties map?"
    failure_mode_if_unmet: single-perspective-trap
  - cq_id: CQ5
    question: "Has the analysis avoided unsolicited recommendation — presenting the envelope rather than rendering a verdict?"
    failure_mode_if_unmet: verdict-trap

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: two-column-trap
    detection_signal: "Plus and Minus populated; Interesting column empty without explicit 'none identified' statement."
    correction_protocol: re-dispatch (audit for second-order implications and populate or explicitly mark empty)
  - name: boilerplate-trap
    detection_signal: "Claims read as generic — could apply to any proposal of this type."
    correction_protocol: re-dispatch (rewrite each claim with specifics from user's case)
  - name: single-perspective-trap
    detection_signal: "All claims viewed from one party's perspective; affected-parties map missing or single-row."
    correction_protocol: re-dispatch (map affected parties; surface asymmetries)
  - name: verdict-trap
    detection_signal: "Output recommends adoption (or rejection) when user did not ask for a lean."
    correction_protocol: flag (remove recommendation; BA produces envelope, not verdict)
  - name: false-symmetry-trap
    detection_signal: "Equal pros and cons presented for appearance of balance, not honest distribution."
    correction_protocol: flag (report honest distribution explicitly)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - debono-pmi
  optional:
    - stakeholder-incidence-analysis
    - second-order-effects-catalog (precedent / signaling / path-dependency)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: red-team-assessment
    when: "Stress-testing under adversarial-actor framing is needed beyond balanced-constructive evaluation; assessment stance for own decision (default), or red-team-advocate when the user needs a brief for external use."
  sideways:
    target_mode_id: balanced-critique
    when: "User wants neutral evaluation with no constructive lean rather than balanced-constructive."
  downward:
    target_mode_id: null
    when: "Benefits Analysis is one of T15's lighter evaluation stances."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Benefits Analysis is the specificity and mechanism-grounding of each column item. A thin pass produces generic claims ("improved efficiency", "potential risks"); a substantive pass names mechanism per claim (the literal phrase "mechanism:" anchors each Plus). Test depth by asking: could the same Plus or Minus apply to a different proposal? If yes, the claim is generic. The Interesting column carries particular depth weight — second-order items (precedent, signaling, path-dependency) are where motivated-optimism analysis typically underperforms.

## BREADTH ANALYSIS GUIDANCE

Breadth in Benefits Analysis is the survey of affected parties before settling on the asymmetries to surface. Widen the lens to scan: parties who benefit if the proposal succeeds; parties who pay costs; parties whose interests are unaffected but whose narrative is changed; parties whose absence from the analysis itself constitutes an asymmetry. Breadth markers: the affected-parties map has at least three rows; the Interesting column captures non-obvious implications; the analysis identifies at least one item that is Plus for one party and Minus for another.

## EVALUATION CRITERIA

Benefits Analysis is read in De Bono PMI vocabulary — Plus, Minus, and Interesting as three irreducible columns rather than a pro/con dyad with garnish. The Interesting column is the methodology's distinctive contribution: it catches the second-order implications (precedent, signaling, path-dependency) that pro/con thinking systematically misses. The evaluator's primary axis is whether the output is a PMI artifact or a disguised verdict. CQ5 (verdict-trap) is load-bearing — an unsolicited recommendation collapses the mode into an opinion piece and invalidates its contribution. CQ1 (two-column-trap) and CQ3 (second-order-omission) are also load-bearing for the methodology's identity: without populated Interesting, the artifact is pro/con, not PMI. CQ2 (boilerplate-trap) and CQ4 (single-perspective-trap) act as quality gates.

Evaluator checks:

1. **Verdict abstention (CQ5, load-bearing).** The recommendation slot must be empty unless the user explicitly asked for a lean. Verdict-trap residue includes hedged forms — "the proposal appears net-positive," "the case for adoption seems strong," "on balance this looks worth doing." Each of these is an unsolicited recommendation in evaluator's clothing. The deliverable presents the envelope; the user decides. When the user asked for a recommendation, the slot is populated explicitly and labelled as such; when they did not, the slot carries an explicit "empty (user did not request a lean)" atom rather than silent omission.

2. **Three-column discipline (CQ1).** All three columns must be populated, or an empty column must be explicitly marked "none identified." Two-column-trap is the failure mode — the analyst has imported a pro/con frame and silently dropped the Interesting column. The check is structural: does the deliverable have a labelled Interesting section, populated or explicitly empty? A missing or unlabelled Interesting section fails CQ1.

3. **Second-order substance in Interesting (CQ3, load-bearing for PMI identity).** The Interesting column must carry items tagged by subtype (precedent / signaling / path-dependency / other-second-order). Items that merely restate Plus or Minus content in milder language are second-order-omission residue — the Interesting column has been populated as decoration rather than as De Bono prescribed. The test: does each Interesting item name an implication orthogonal to the proposal's primary effect, and does it carry an explicit subtype tag?

4. **Mechanism-grounded specificity (CQ2).** Each claim must name the mechanism by which the Plus or Minus arises — "mechanism: by reducing X" rather than "improves efficiency." Generic claims that could apply to any proposal of this type are boilerplate-trap. The De Bono discipline is per-claim mechanism, not category-level summary. Test: could the same Plus or Minus apply to a substantially different proposal? If yes, the claim is generic and is reshaped.

5. **Affected-party asymmetry (CQ4).** The affected-parties map must carry at least three party rows, and the deliverable must surface at least one asymmetry — an item that is Plus for party_A and Minus for party_B. A single-perspective analysis (all claims viewed from one party's vantage) is single-perspective-trap; PMI methodology is descriptive of impact distribution, not aggregated from a single seat. When no asymmetries are honestly present, the deliverable says so explicitly rather than fabricating one.

6. **Honest distribution over false symmetry.** When the corpus reaches the deliverable with a 5-1-0 distribution, the deliverable carries that skew with the count stated. Padding weaker columns to look balanced is false-symmetry-trap — appearance of balance smuggled in at the cost of honest reporting. The PMI artifact's value is the actual distribution; the user reads it as data.

Confidence is per-claim: training-grounded vs RAG-grounded vs user-supplied vs analyst inference. Per-column evidence quality is the aggregated note. Where streams disagreed on whether an item is Plus, Minus, or Interesting (column-classification disagreement), the evaluator confirms the disagreement is preserved as a tension atom rather than silently picked.

## REVISION GUIDANCE

Revise to add specificity where claims are generic. Revise to populate the Interesting column where second-order items are missing. Revise to remove recommendation language where the user did not ask for a lean. Resist revising toward false symmetry — if the honest distribution is 1 Plus and 5 Minus, say so rather than padding. Resist revising toward verdict — Benefits Analysis presents the envelope; the user decides.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **PMI-categorized claim atoms with mechanism, party, and second-order tagging**, per de Bono's Plus/Minus/Interesting methodology. The three columns are the load-bearing categorical structure; everything else attaches to or derives from the categorized claim atoms. The atoms are:

1. **Proposal atom.** The precisely-stated proposal as a single canonical atom at the corpus head. Cross-stream paraphrase collapses to one statement (most precise wording survives).

2. **Plus atoms.** Each claim atom carries: claim statement, mechanism phrase ("mechanism: ..." anchoring how the benefit arises), affected party or parties, evidence basis (training / RAG / user-supplied / inference), and consequentiality flag (the most-consequential Plus is explicitly marked). Generic claims that could apply to any proposal of this type do not survive — boilerplate-trap; the mode's posture is mechanism-grounded specificity.

3. **Minus atoms.** Same structure as Plus atoms. Risks and costs each carry mechanism phrasing — vague "potential risk" without mechanism is bloat. Most-consequential Minus is marked.

4. **Interesting atoms.** Same structure plus a subtype tag: **precedent** (this proposal establishes or echoes precedent), **signaling** (the proposal communicates something orthogonal to its primary effect), **path-dependency** (the proposal commits resources or options that constrain future choices), or **other-second-order**. At least one Interesting atom must survive the dedup or the Interesting column is explicitly marked "none identified" (CQ3). Most-consequential Interesting is marked.

5. **Asymmetry atoms.** Each names a specific (party_A, party_B) pair where an item is Plus for party_A and Minus for party_B (or analogous cross-cuts). The atom points to the underlying Plus and Minus atoms by their canonical IDs; the asymmetry is itself a finding (CQ4). At minimum one asymmetry atom is named or the affected-parties analysis fails the breadth marker.

6. **Affected-parties map atoms.** Each affected party is a named atom, with cross-references to the Plus/Minus/Interesting atoms that touch them. The map has at least three party rows; cross-stream parties dedupe by canonical role (same party under different naming collapses to one).

7. **Honest-distribution atom.** The raw count per column — e.g., "3 Plus, 5 Minus, 2 Interesting." This is a load-bearing atom because false-symmetry-trap is a named failure mode; the corpus carries the actual distribution, not a padded balanced shape. When one column has substantially more atoms than another after cross-stream dedup, the distribution is the finding.

8. **Evidence-quality atoms per column.** Each column carries a single evidence-quality note: which claims are training-grounded vs RAG-grounded vs user-supplied vs analyst inference. Per-claim provenance is at the claim-atom level; per-column quality is the aggregated note.

9. **Recommendation slot.** Empty by default. Populated only when the user explicitly asked for a lean. Verdict-trap is the load-bearing failure mode for this stance — an unsolicited recommendation invalidates the mode's contribution; the corpus carries an explicit "recommendation field: empty (user did not request a lean)" atom rather than silently omitting the slot.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Generic-claim paraphrase** — both streams may state the same Plus or Minus in slightly different generic terms ("improves efficiency" vs "increases productivity"). If neither is mechanism-grounded, both are bloat (boilerplate-trap); rewrite to the specific mechanism for the user's case. If one is mechanism-grounded and one is generic, the mechanism-grounded version survives as the canonical atom.
- **Mechanism-restatement** — same mechanism phrase under different wordings ("by reducing X" vs "through lower X"). One mechanism phrase survives per claim atom.
- **Party-naming duplication** — same affected party under different labels ("employees" vs "staff" vs "the workforce"). Single party atom survives with the most precise role identifier; the underlying entity is referenced consistently across atoms.
- **Interesting-column paraphrase** — both streams may flag the same second-order implication in different framings ("this would set a precedent for..." vs "future cases would point back to this..."). Single Interesting atom survives with subtype tag and the most precise phrasing.
- **Asymmetry restatement** — same asymmetry stated in two directions ("Plus for management, Minus for employees" vs "Minus for employees, Plus for management"). Single asymmetry atom with party_A and party_B canonically ordered.
- **Verdict-shaped meta-commentary** — both streams may include hedged recommendations or "on balance" verdict gestures ("the proposal appears net-positive" / "the case for adoption seems strong"). These are verdict-trap residue and do not survive into the corpus regardless of how many times they appear; the recommendation slot is empty unless the user asked for a lean.

**What NOT to collapse:**

- **Same item Plus AND Minus for the same party** — when an item is genuinely both a Plus and a Minus for the same party (it benefits them in one dimension while costing them in another), preserve both atoms with explicit cross-reference. Collapsing to "net neutral" or "mixed effect" loses the diagnostic of which dimensions trade against each other.
- **Cross-stream column-classification disagreement** — when one stream classified a finding as Plus and the other as Minus (or as Interesting vs Plus/Minus), preserve the disagreement as a tension atom rather than picking one classification. The disagreement is itself a finding about the proposal's ambiguous valence, not a synthesis error.
- **Honest-distribution skew** — if the corpus reaches dedup with a 5-1-0 distribution, do not pad weaker columns to look balanced. False symmetry is a named failure mode; the corpus carries the actual skew. Sparse columns are marked "none identified" rather than auto-populated.

## VERIFICATION CRITERIA

Verified means: proposal stated precisely; all three columns populated (or explicit "none identified" statement); each claim grounded in user's specifics; ≥ 1 second-order implication named; affected-parties map present; ≥ 1 asymmetry surfaced; no unsolicited recommendation. The five critical questions are addressed. Silent injection of a recommendation during revision is a verification failure.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured three-column PMI artifact with affected-parties map and asymmetry findings**, per de Bono methodology. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Proposal.** The precisely-stated proposal at the top, one sentence or short paragraph. Frame as "The proposal under evaluation:" — the user must see what is being evaluated before the evaluation.

2. **Plus column.** Bulleted list of Plus claims. Each bullet renders in this exact shape: `**[Claim]** — mechanism: [how the benefit arises]. Affected party: [party or parties]. Evidence: [training / RAG / user-supplied / inference].` Mark the most-consequential Plus with a `**[most consequential]**` tag inline. When no Plus atoms survived, write "No Plus findings identified — see honest-distribution note below."

3. **Minus column.** Same shape as Plus column. Each bullet: claim + mechanism + affected party + evidence basis. Mark the most-consequential Minus. Vague risks without mechanism do not appear here.

4. **Interesting column.** Same shape plus a **subtype tag**: `[precedent]` / `[signaling]` / `[path-dependency]` / `[other-second-order]`. At minimum one Interesting atom appears, or write "No second-order implications identified — Interesting column intentionally empty."

5. **Affected-parties map.** Numbered list of parties (P1, P2, …) with: party role / canonical name, and cross-references to the Plus/Minus/Interesting items that touch them (e.g., "P1 — Employees: Plus 2, Minus 1, Minus 3, Interesting 1"). Map carries at least three party rows.

6. **Asymmetries.** Bulleted list of (party_A, party_B) pairs where the same item is Plus for one and Minus for the other (or analogous cross-cut). Each bullet: `[party_A] vs [party_B]: Item [reference] is Plus for [party_A] (mechanism) and Minus for [party_B] (mechanism).` At minimum one asymmetry, or write "No asymmetries surfaced; the proposal affects parties uniformly."

7. **Honest distribution.** One sentence stating the raw count: `Plus: N, Minus: N, Interesting: N.` When the distribution is asymmetric (e.g., 5 Minus to 1 Plus), name the asymmetry explicitly: "Distribution is asymmetric: [reason]." Do not pad weaker columns to balance the count.

8. **Evidence quality per column.** Three short notes (one per column) on the evidence basis: which claims are training-grounded vs RAG-grounded vs user-supplied vs analyst inference.

9. **Recommendation.** Empty by default — render as: `Recommendation: empty (user did not request a lean — Benefits Analysis presents the envelope, not the verdict).` Populate only when the user explicitly asked for a recommendation.

**Per-section conventions:**

- Use H2 headings for sections 1 through 9.
- The three columns may be rendered as a markdown table (Plus | Minus | Interesting) when the deliverable lends itself to tabular comparison, or as three sequential H2 subsections when claims need elaboration. Choose by case.
- Party IDs (P1, P2, …) are referenced consistently throughout once introduced.
- Mechanism phrases use the literal "mechanism:" label or its tag — `mechanism: X` — never "this benefits the user because" without the mechanism named explicitly.
- Most-consequential tags appear exactly once per column.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~5min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `supports`, `contradicts`, `qualifies`, `extends`
**Deprioritize:** `precedes`, `parent`

*Family: argument-evaluation. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
