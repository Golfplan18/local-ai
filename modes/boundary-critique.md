---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Boundary Critique

```yaml
# 0. IDENTITY
mode_id: boundary-critique
canonical_name: Boundary Critique
suffix_rule: analysis
educational_name: "boundary critique (Ulrich CSH: critical systems heuristics)"

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: stance
  value: critical
adjacent_modes_in_territory:
  - mode_id: cui-bono
    relationship: stance-counterpart (descriptive who-benefits within the artifact's own frame)
  - mode_id: stakeholder-mapping
    relationship: complexity-counterpart (multi-party-descriptive — lives in T8)
  - mode_id: wicked-problems
    relationship: complexity-molecular sibling
  - mode_id: decision-clarity
    relationship: depth-molecular sibling

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I think the framing of this leaves people out"
    - "who isn't being asked"
    - "whose perspective is being treated as natural or inevitable"
    - "the boundary of who counts as a stakeholder feels too narrow"
    - "there's an 'us' implied here that needs surfacing"
  prompt_shape_signals:
    - "boundary critique"
    - "Ulrich"
    - "CSH"
    - "critical systems heuristics"
    - "who is excluded"
    - "boundary judgments"
    - "whose voice is missing"
    - "what's outside the system being analyzed"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants explicit critique of the boundary judgments embedded in a system, decision, or design"
    - "user suspects the framing has naturalized exclusions that should be surfaced and questioned"
    - "user wants to apply Ulrich's twelve boundary categories (sources of motivation, control, knowledge, legitimacy)"
  routes_away_when:
    - "user wants descriptive who-benefits within the artifact's frame" → cui-bono
    - "user wants multi-party stakeholder landscape without critical stance" → stakeholder-mapping
    - "user wants integrated multi-perspective analysis of a wicked problem" → wicked-problems
    - "user wants to negotiate boundary across affected parties" → T13 modes
when_not_to_invoke:
  - "User wants neutral or descriptive analysis without critical-stance framing" → cui-bono or stakeholder-mapping
  - "Boundary in question is technical and uncontested (e.g., a defined system spec)" → T17 process modes
  - "Affected parties are clearly identified and not in dispute" → cui-bono or T13 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: critical

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [system_or_design_or_decision, named_boundary_in_question]
    optional: [stakeholder_inventory_provisional, ulrich_categories_of_focus, normative_position]
    notes: "Applies when user supplies the system/design/decision, names the boundary at issue, and may identify which of Ulrich's twelve categories are most in play."
  accessible_mode:
    required: [system_or_situation, what_feels_excluded_or_naturalized]
    optional: [why_user_wants_boundary_critique, suspected_voices_left_out]
    notes: "Default. Mode applies Ulrich's twelve categories during execution as the structuring framework."
  detection:
    expert_signals: ["Ulrich", "CSH", "boundary judgments", "critical systems heuristics", "sources of motivation", "sources of control", "sources of knowledge", "sources of legitimacy"]
    accessible_signals: ["who is excluded", "who isn't asked", "the framing leaves out", "what's outside"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the system, decision, or design we're examining, and what about its boundary feels off?'"
    on_underspecified: "Ask: 'Whose voice or interest do you suspect is being treated as outside the scope of this analysis?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have boundary judgments been surfaced as judgments (contestable, made by someone for some purpose), or are they treated as natural givens of the system?"
    failure_mode_if_unmet: boundary-naturalization
  - cq_id: CQ2
    question: "Has the analysis distinguished those involved in the system's design and benefit from those affected by but not involved in the system, per Ulrich's core asymmetry?"
    failure_mode_if_unmet: involved-affected-collapse
  - cq_id: CQ3
    question: "Have all four of Ulrich's category-clusters (motivation, control, knowledge, legitimacy) been audited, or has the analysis selected only the categories that confirm an initial suspicion?"
    failure_mode_if_unmet: selective-categories
  - cq_id: CQ4
    question: "Has the *is* vs. *ought* boundary comparison been performed — i.e., what the boundary currently is vs. what it would be if affected-but-not-involved parties were included — rather than only diagnosing the current boundary?"
    failure_mode_if_unmet: ought-omission

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: boundary-naturalization
    detection_signal: "Boundary judgments described in system-spec language (definitional, technical) rather than as contestable choices made by someone for some purpose."
    correction_protocol: re-dispatch
  - name: involved-affected-collapse
    detection_signal: "Affected-but-not-involved parties section is absent or merged into the involved-stakeholder list."
    correction_protocol: re-dispatch
  - name: selective-categories
    detection_signal: "Only one or two of Ulrich's four category-clusters are audited; others are skipped or noted as 'not applicable' without justification."
    correction_protocol: re-dispatch
  - name: ought-omission
    detection_signal: "Output diagnoses the current boundary without articulating what an inclusive-of-affected-parties boundary would look like."
    correction_protocol: flag
  - name: critique-without-purpose
    detection_signal: "Boundary critique surfaced without articulating what the user could do with the surfaced judgments (no implication for the system, decision, or design)."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - ulrich-csh-boundary-categories
  optional:
    - habermas-discourse-ethics (when legitimacy category is foregrounded)
    - midgley-systemic-intervention (when intervention is in scope)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: wicked-problems
    when: "Boundary critique surfaces a problem with multiple interacting stakeholder conflicts and feedback loops that exceed atomic critique."
  sideways:
    target_mode_id: cui-bono
    when: "On reflection user wanted descriptive who-benefits within the existing frame rather than critical surfacing of the frame's boundary."
  downward:
    target_mode_id: cui-bono
    when: "User wants lighter descriptive read; critical-stance was not the right pitch."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Boundary Critique is the rigor with which Ulrich's twelve boundary categories are applied — four category-clusters (motivation, control, knowledge, legitimacy), each audited along the *is* / *ought* axis, distinguishing those involved from those affected-but-not-involved. A thin pass names some excluded parties; a substantive pass works through the four category-clusters systematically, surfaces who currently provides the source of motivation/control/knowledge/legitimacy and on whose behalf, identifies affected-but-not-involved parties per category, and constructs the *ought* counterpart that would obtain if those parties were included. Test depth by asking: could the critique tell the system's designer which specific boundary judgment, if revised, would change the system's relation to its affected parties?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surveying the full Ulrich category-cluster space (motivation: client/purpose/measure-of-improvement; control: decision-maker/resources/decision-environment; knowledge: expert/expertise/guarantor; legitimacy: witness/emancipation/worldview) and considering boundary frames from adjacent traditions (Habermasian discourse-ethics, Midgley's systemic intervention, Mackenzie's situated knowledges) where they bear. Breadth markers: all four category-clusters are visited; affected-but-not-involved parties are sought across all four (not only the obvious ones); the worldview category is treated with care because it surfaces the deepest boundary judgments.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Boundary Critique applies Ulrich's Critical Systems Heuristics (CSH) to surface the boundary judgments embedded in a system, decision, or design — what counts as the system, whose voice counts, what the criterion of improvement is, who is affected without being involved. It is distinct from cui-bono (descriptive who-benefits within the artifact's own frame), stakeholder-mapping (multi-party landscape without critical stance), and wicked-problems (integrated multi-perspective synthesis). Its analytical character is critical — it surfaces contestation rather than smoothing it; consensus-seeking framing is a category error.

**Procedure.**

1. Name the system, plan, policy, design, or proposal under critique precisely at the head.
2. Surface the boundary judgments currently embedded in the artifact — often implicit; state explicitly what is taken as given.
3. Walk through Ulrich's twelve categories in four clusters — Motivation (beneficiary / purpose / measure of improvement), Control (decision-maker / resources / decision environment), Expertise (expert / expertise / guarantor), Legitimacy (witness / emancipation / worldview).
4. For each category render three atoms — `is` (what the artifact takes as given), `ought` (what would obtain if affected-but-not-represented parties counted, from their standpoint), `gap` (the consequence-bearing distance between the two, flagged as live contestation).
5. Treat worldview (category 12) with extended attention — it is the most invisible and most-commonly-skipped boundary judgment; deferring it as "too philosophical" is the single most common failure.
6. Maintain Ulrich's involved-vs-affected distinction — list affected-but-not-involved parties by which categories surface them; if "the analyst" is currently the witness for an affected party, surface this as analyst-substitution rather than masking it.
7. Construct implications for action — for each load-bearing gap, name what boundary judgment if revised would change the system's relation to its affected parties.
8. Frame all surfaced gaps as live political contestation, not as technical or objective findings — boundary critique makes boundary judgments visible and contestable; it cannot eliminate them.
9. Assign confidence per gap atom with explicit basis.

**Goal.** Produce a 12-category boundary audit organized by Ulrich's four source-clusters with is/ought rendering per category and explicit implications for action that name what the user could do with the surfaced judgments.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — boundaries surfaced as judgments.** Have boundary judgments been surfaced as judgments (contestable, made by someone for some purpose), or are they treated as natural givens of the system? Failure mode if unmet: `boundary-naturalization`.
- **CQ2 — involved-vs-affected distinction.** Has the analysis distinguished those involved in the system's design and benefit from those affected by but not involved in the system, per Ulrich's core asymmetry? Failure mode if unmet: `involved-affected-collapse`.
- **CQ3 — all four clusters audited.** Have all four of Ulrich's category-clusters (motivation, control, knowledge, legitimacy) been audited, or has the analysis selected only categories that confirm an initial suspicion? Failure mode if unmet: `selective-categories`.
- **CQ4 — is-vs-ought comparison.** Has the *is* vs *ought* boundary comparison been performed rather than only diagnosing the current boundary? Failure mode if unmet: `ought-omission`.

A passing output names the system under critique, audits all twelve categories across the four clusters with explicit is/ought/gap atoms (including a worldview gap), maintains the involved-vs-affected distinction with affected-but-not-involved parties identified per category, names implications for action per cluster, and frames gaps as live contestation rather than as objective findings.

**Named failure modes.**

- *boundary-naturalization* — boundary judgments described in system-spec language rather than as contestable choices made by someone for some purpose.
- *involved-affected-collapse* — affected-but-not-involved parties section absent or merged into the involved-stakeholder list.
- *selective-categories* — only one or two of Ulrich's four category-clusters audited; others skipped or noted "not applicable" without justification.
- *ought-omission* — output diagnoses the current boundary without articulating what an inclusive-of-affected-parties boundary would look like.
- *critique-without-purpose* — boundary critique surfaced without articulating what the user could do with the surfaced judgments.

## REVISION GUIDANCE

Revise to denaturalize boundary judgments where the draft treated them as system-given. Revise to maintain the involved/affected distinction where the draft collapsed it. Revise to complete the four category-clusters where the draft selected only some. Revise to add the *ought* counterpart where the draft only diagnosed the *is*. Resist revising toward neutrality — the mode's analytical character is critical, and a passing artifact retains the critical edge. If the user wanted neutral analysis, escalate sideways to cui-bono.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a twelve-category boundary grid with is/ought atoms and gap atoms**, per Ulrich's CSH methodology. The grid is the load-bearing data structure: twelve categories in four source-clusters, each carrying paired is/ought answers plus the gap between them. Implication-for-action atoms close the loop from critique to use. The atoms are:

1. **System-under-critique atom.** The artifact, plan, policy, design, study, or proposal under critique, named precisely at the corpus head. Cross-stream paraphrase collapses to one canonical statement.

2. **The twelve category atoms — fixed grid.** Each of Ulrich's twelve categories carries three atoms (is-atom, ought-atom, gap-atom):
   - **Motivation cluster**: (1) Beneficiary, (2) Purpose, (3) Measure of improvement
   - **Control cluster**: (4) Decision-maker, (5) Resources, (6) Decision environment
   - **Expertise cluster**: (7) Expert/planner, (8) Expertise, (9) Guarantor
   - **Legitimacy cluster**: (10) Witness, (11) Emancipation, (12) Worldview

   For each category:
   - **is-atom** — what the artifact takes as given (often implicit; surfaced explicitly here)
   - **ought-atom** — what would obtain if the affected-but-not-represented counted; from the standpoint of the affected, not from the analyst's own values
   - **gap-atom** — the consequence-bearing distance between is and ought, flagged as live contestation rather than as objective finding

   All twelve categories appear in the corpus, even when a category's gap is small. Skipping a category requires an explicit "category-N: gap minimal — [reason]" atom rather than silent omission (selective-categories failure mode).

3. **Worldview-category emphasis (category 12).** Worldview is the most invisible boundary judgment and the most commonly skipped. The corpus carries an explicit worldview gap-atom regardless of how abstract the methodology seems for the user's case — deferring it as "too philosophical" is the single most common failure of boundary critique.

4. **Affected-but-not-involved party atoms.** Parties affected by the system but not represented in its design, organized by which of the twelve categories surface them. The witness atom (category 10) names which voice currently speaks for them; if "the analyst" is the witness, that is surfaced as analyst-substitution rather than masked. Each affected-party atom carries: party role, which categories surface them, and what they would say if they could speak.

5. **Implication-for-action atoms.** For each load-bearing gap, an atom names what the user (or decision-maker, or system designer) could do with the finding — which boundary judgment, if revised, would change the system's relation to its affected parties. Addresses the `critique-without-purpose` failure mode: critique that surfaces judgments without naming what's available to do with them is analytically empty. At minimum one implication-for-action atom per cluster must survive.

6. **Boundary-judgments-as-contestable atom.** A corpus-level statement framing the gaps as live political contestation, not as technical or objective findings. Boundary critique makes boundary judgments visible and contestable; it cannot eliminate them. This atom defends against consensus-seeking framing.

7. **Confidence per gap.** Confidence markers attach to individual gap atoms. When the two streams assigned different confidences to the same gap, audit conservatism applies (the lower confidence survives).

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Is-answer paraphrase** — both streams may surface the same implicit assumption in slightly different language ("the artifact treats X as the beneficiary" vs "X is named as the served party in the artifact"). Single is-atom per category survives.
- **Ought-answer paraphrase** — both streams may articulate the same alternative ought-answer in different framings. Single ought-atom per category survives.
- **Gap-restatement** — same gap described twice ("there is a gap between the assumed beneficiary X and the affected party Y" vs "the beneficiary as currently identified excludes Y"). Single gap-atom per category survives.
- **Affected-party renaming** — same party under different labels ("non-organized public" vs "unrepresented citizens" vs "the public-not-consulted"). Single party atom with canonical role identifier; cross-references update accordingly.
- **Worldview-paraphrase loops** — worldview is abstract and prone to multiple articulations. The most precise statement of the worldview gap survives; specificity from each stream's articulation is unioned (a gap statement that names three load-bearing moves the artifact makes under its worldview is more precise than one that names two).
- **Consensus-seeking residue** — phrasings like "a balanced boundary would...", "the appropriate framing is...", "what both perspectives can agree on...". Boundary critique surfaces contestation; it does not propose resolutions. This residue does not survive regardless of how plausibly it's phrased.

**What NOT to collapse:**

- **Different is-answers for the same category** — when the two streams disagree on what the artifact takes as given (different readings of the implicit answer), preserve both as a tension atom. The artifact may genuinely be ambiguous on that point, or one stream may be reading it more accurately; the disagreement is itself a finding about the boundary's clarity.
- **Different ought-answers from different affected constituencies** — different affected-party perspectives produce different ought-answers. When two streams' ought-atoms reflect different affected constituencies, preserve both with their respective constituency provenance. Boundary judgments are political, and political disagreement among the affected is not bloat.
- **Cross-category gap interactions** — when a gap in one category load-bears on a gap in another (e.g., worldview gap entails decision-maker gap), preserve the interaction as a cross-reference atom rather than collapsing into a single "system-wide gap." The four source-clusters interact, and the interaction is the corpus's value for someone trying to identify which single boundary revision would change the most.

## VERIFICATION CRITERIA

Verified means: the system under critique is named; boundary judgments currently embedded are surfaced as judgments (not as system-givens); all four of Ulrich's category-clusters are audited; affected-but-not-involved parties are identified per category; the is-vs-ought boundary comparison is performed; the four critical questions are addressable from the output. Confidence per major finding accompanies each claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **12-category boundary audit organized by Ulrich's four source-clusters, with is/ought rendering per category and explicit implications for action**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **System under critique.** Name the artifact, plan, policy, design, study, or proposal under critique at the top, in one sentence or short paragraph. Frame as "System under boundary critique:" — the user must see what is being audited.

2. **Boundary judgments currently embedded — overview.** One paragraph summarizing the artifact's load-bearing boundary judgments at the corpus level. This frames the detailed per-category audit that follows. Position as "Boundary judgments the artifact currently embeds (often implicit):"

3. **Per-category audit — Ulrich's twelve categories in four clusters.** Render four H2 sub-sections, one per cluster (Motivation / Control / Expertise / Legitimacy). Within each cluster, render the three categories in this fixed sequence:

   **Cluster A — Sources of motivation:**
   - (1) Beneficiary
   - (2) Purpose
   - (3) Measure of improvement

   **Cluster B — Sources of control:**
   - (4) Decision-maker
   - (5) Resources
   - (6) Decision environment

   **Cluster C — Sources of expertise:**
   - (7) Expert / planner
   - (8) Expertise
   - (9) Guarantor

   **Cluster D — Sources of legitimacy:**
   - (10) Witness
   - (11) Emancipation
   - (12) Worldview

   For each of the twelve categories, render this fixed three-atom block:
   - **is:** what the artifact takes as given (often implicit; state explicitly).
   - **ought:** what would obtain if the affected-but-not-represented counted (from the affected's standpoint, not the analyst's values).
   - **gap:** the consequence-bearing distance between is and ought, flagged as live contestation rather than as objective finding.

   When a category's gap is small or the category does not apply meaningfully, render: `gap: minimal — [reason]` rather than omitting the category. Skipping is a named failure mode.

4. **Worldview (category 12) — extended.** The worldview category receives a dedicated block at the end of the per-category audit (even though it appears in sequence in section 3). Render: "Whose worldview is currently load-bearing in the artifact: [...]. Alternative worldview from the affected: [...]. What changes under the alternative: [specific analytical moves that shift]." Worldview is the most-commonly-skipped category and gets visible emphasis.

5. **Affected-but-not-involved parties.** Numbered list of parties (P1, P2, …) with: party role, which categories surface them, and what they would say if they could speak. Each party row: `P1 — [role]: surfaced in categories [N, N, N]. Their voice would say: [what they would say].` When the witness atom (category 10) names "the analyst" as the current witness, surface this explicitly as analyst-substitution rather than masking it.

6. **Implications for action.** Per cluster (Motivation / Control / Expertise / Legitimacy), at minimum one implication-for-action atom: "Boundary judgment in [category]: if revised to [ought], the system's relation to [affected party] changes by [specific consequence]." This section addresses the `critique-without-purpose` failure mode — the audit's surfaced judgments must be paired with what the user could do with them.

7. **Boundary judgments as contestation.** A single closing block framing all surfaced gaps as live political contestation, not as technical or objective findings: "Boundary critique cannot eliminate boundary judgments — only make them visible and contestable. The judgments surfaced above are political; they are owned by the parties affected, not by the analyst."

8. **Confidence per gap.** Bulleted list of major gap-atoms with confidence markers (high / moderate / low). One bullet per category where the gap is consequential.

**Per-section conventions:**

- Use H2 headings for sections 1 through 8.
- Within section 3, use H3 sub-headings for the four clusters; use bolded inline labels (Beneficiary, Purpose, Measure of improvement, etc.) for the twelve categories.
- The is/ought/gap triple renders as three lines per category — never collapse to "is/ought differ by ..." narrative without the three explicit labels.
- All twelve categories appear in the audit; explicit "minimal — [reason]" rather than silent omission.
- Avoid consensus-seeking framing throughout the deliverable: "a balanced boundary would...", "what both perspectives share..." are forbidden — boundary critique surfaces contestation.


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

**Prioritize:** `requires`, `enables`, `contradicts`, `supports`, `qualifies`
**Deprioritize:** `parent`, `analogous-to`

*Family: stakeholder-strategy. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
