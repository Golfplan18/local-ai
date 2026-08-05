# Reference — Mode Specification Template

*The locked template for every mode in the registry. Atomic and molecular modes share this template; per-section content adapts to composition. This file is referenced from Phase 2 (existing mode migration), Phase 4 (new mode build), and the four-stage pre-routing pipeline at Stage 4 (mode execution). Locked per the 15 architectural decisions of 2026-05-01.*

---

## Locked Template

```yaml
# 0. IDENTITY
mode_id: <kebab-case-id>            # filename without .md extension
canonical_name: <Display Name>      # title-case, no suffix
suffix_rule: analysis | reading | none   # Decision L
educational_name: <plain-language technique name, ≤15 words, no acronyms unless canonical with sub-parens expansion>   # Decision E

# 1. TERRITORY AND POSITION
territory: T<n>-<short-name>
gradation_position:
  axis: depth | complexity | stance | specificity
  value: <e.g., light | thorough | molecular | constructive | adversarial | neutral | systemic | feedback-structure>
adjacent_modes_in_territory:
  - mode_id: <sibling_mode>
    relationship: heavier sibling | lighter sibling | adversarial counterpart | stance counterpart | specificity variant

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals: ["<situation phrase>"]
  prompt_shape_signals: ["<prompt phrase or pattern>"]
disambiguation_routing:
  routes_to_this_mode_when: ["<plain-language user answer>"]
  routes_away_when: ["<plain-language user answer that selects a sibling>"]
when_not_to_invoke:
  - "<condition under which a different territory is correct>"
  - "<condition under which a sibling mode is correct>"

# 3. EXECUTION STRUCTURE
composition: atomic | molecular
atomic_spec:
  passes: 1
  posture: constructive | adversarial | neutral | suspending | generative | descriptive | contemplative
molecular_spec:
  components:
    - mode_id: <component_mode>
      runs: full | fragment
      fragment_spec: "<what fragment, if not full>"
      conditional: "<when this component runs, if not always>"
  synthesis_stages:
    - name: <stage_name>
      type: parallel-merge | sequenced-build | dialectical-resolution | contradiction-surfacing
      input: <components or prior stages>
      output: <artifact description>
  partial_composition_handling:
    on_component_failure: abort | substitute | proceed-with-gap
    on_low_confidence: flag | reconcile | re-dispatch

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:                                  # Decision 3 — dual contract
  expert_mode:
    required: [<fields the prompt must explicitly carry>]
    optional: [<fields the prompt may carry>]
    notes: "<conditions under which expert_mode applies>"
  accessible_mode:
    required: [<minimal fields a non-expert prompt must carry>]
    optional: [<fields a non-expert prompt may carry>]
    notes: "<conditions under which accessible_mode applies (default)>"
  detection:
    expert_signals: ["<phrase or pattern indicating expert framing>"]
    accessible_signals: ["<phrase or pattern indicating accessible framing>"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "<sibling mode to suggest, or follow-up question to ask>"
    on_underspecified: "<follow-up question template>"
output_contract:
  artifact_type: audit | mapping | ranked_options | scenarios | synthesis | reading | recommendation | clarification | other
  required_sections: [<sections the output must contain>]
  format: prose | structured | matrix | diagram-friendly | reading-with-vocabulary

# 5. CRITICAL QUESTIONS (Walton sense)
critical_questions:
  - cq_id: CQ1
    question: "<distinguishing critical question>"
    failure_mode_if_unmet: "<named failure mode>"
  # repeat per CQ; minimum 3 per mode

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: <e.g., "frame-blindness", "evidence-anchoring", "stakeholder-collapse">
    detection_signal: "<how the orchestrator or user notices this>"
    correction_protocol: escalate | re-dispatch | flag | request-additional-input

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: [<lens_ids — must be available for this mode to dispatch>]
  optional: [<lens_ids — used if available>]
  foundational: [<lens_ids — globally available; named here for transparency>]

# 8. RUNTIME AND DEPTH (user-facing depth contract)
default_depth_tier: 1 | 2 | 3
expected_runtime: ~1min | ~5min | ~10+min
escalation_signals:                              # signals to escalate to a sibling
  upward:
    target_mode_id: <heavier sibling>
    when: "<condition under which to escalate>"
  sideways:
    target_mode_id: <stance/complexity sibling>
    when: "<condition under which to switch>"
  downward:
    target_mode_id: <lighter sibling>
    when: "<condition under which to de-escalate>"

# 9. PER-PIPELINE-STAGE GUIDANCE                # Decision C-extension
# These six subsections appear as ## headings in the body of the mode file (not in YAML).
# Each subsection carries mode-specific analytical character at that pipeline stage.
# The orchestrator's universal pipeline-stage specs (F-Analysis-Depth, F-Analysis-Breadth,
# F-Evaluate, F-Revise, F-Consolidate, F-Verify) extract the relevant subsection at runtime.

# 10. CAVEATS AND OPEN DEBATES (when applicable)
# Free-text body section ## CAVEATS AND OPEN DEBATES — populated for modes carrying
# debates from research report §13 or T19 reanalysis §6.
```

### Body subsections (mode file beyond YAML frontmatter)

Every mode file's body carries the following `##` sections. The orchestrator extracts the relevant subsection at runtime per the universal pipeline-stage specs.

```markdown
## DEPTH ANALYSIS GUIDANCE

[Mode-specific direction for the F-Analysis-Depth pipeline stage. What does
"go deeper" mean for this mode? What signals indicate a thin pass vs. a
substantive pass? What dimensions does depth in this mode operate along?]

## BREADTH ANALYSIS GUIDANCE

[Mode-specific direction for the F-Analysis-Breadth pipeline stage. What does
"widen the lens" mean for this mode? What adjacent considerations should be
scanned but not necessarily pursued? What breadth markers signal that the
analysis has surveyed the relevant landscape?]

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

[The canonical statement of what this analysis is, the procedure, the goal,
the evaluation criteria (which critical questions from the YAML's
critical_questions block drive the evaluation), and the named failure modes
(from failure_modes) checked here. This section is injected by
`build_system_prompt_for_gear` (`~/ora/orchestrator/boot.py`) into EVERY
pipeline stage's system prompt — analyst, evaluator, reviser, verifier,
consolidator, formatter — alongside ## VERIFICATION CRITERIA, as the
cross-stage performance contract. Write it as the shared standard the
analyst writes to and the evaluator grades against, not as evaluator-only
direction. Structure: What this analysis is / Procedure / Goal / Evaluation
criteria / Named failure modes.]

## REVISION GUIDANCE

[Mode-specific direction for the F-Revise pipeline stage. What kinds of
revision are appropriate for this mode? What kinds of revision risk
distorting the mode's analytical character (e.g., over-cautious revision
of an adversarial-stance mode toward neutrality)?]

## CONSOLIDATION GUIDANCE

[Mode-specific direction for the F-Consolidate pipeline stage (step 7).
Step 7 produces the irreducible corpus, not the user-facing deliverable
(deliverable form is step 8's job — see ## OUTPUT FORMAT GUIDANCE). What
atom types does the corpus carry? What is the corpus organization (matrix,
sequential, categorical, triadic, fixed-grid, network, cascade, etc.) per
the mode's methodology? What mode-specific bloat patterns does the
consolidator cut during the bloat strip? What disagreements between the
two streams must be preserved as tensions rather than collapsed?]

## VERIFICATION CRITERIA

[Mode-specific direction for the F-Verify pipeline stage. What does
"verified" mean for this mode? What verification questions does the mode
admit? What standards of evidence apply?]

## OUTPUT FORMAT GUIDANCE

[Mode-specific direction for the F-Format pipeline stage (step 8). Step 8
takes the step-7 corpus and places it into the user-facing deliverable
form. What are the prescribed sections of the deliverable, in what order?
What per-section structural conventions apply (matrix / table / per-row
format / one-line summary atoms / prose / diagram-friendly)? What
ordering and rendering conventions does the mode's literature prescribe
(e.g., Toulmin per-inferential-move structure; Heuer ACH matrix-then-
conclusion; Klein prospective-hindsight past-tense failure narrative)?
Voice and posture are universal in f-format.md, so they do not need to be
repeated here — only the per-mode form-placement spec.]

## ANALYTICAL PERSPECTIVES

Thinking tools (always loaded):
- OPV
- KVI
- CAF
- C&S
- FIP
- FGL

Mental models (always loaded):
- nash-equilibrium
- batna
- cooperation
- prisoners-dilemma

[Optional — an empty or absent section is a clean no-op (no injection). The
example bullets above are cui-bono's allowlist. The section is machine-parsed:
the two bucket-header lines are matched case-insensitively by regex —
"Thinking tools (always loaded):" (any header of the form `Thinking
tool(s) …:` or `Tier 1 …:`) and "Mental models (always loaded):" (any header
of the form `Mental model(s) …:`, `Tier 3 …:`, or `Lens(es) …:`). Bullets
without a preceding bucket header are ignored; within-bucket order is
preserved. Valid thinking-tool ids are the `### ` headings of the `## Tier 1
Tool Definitions` section of `Projects/Ora/Reference — Thinking Tools Library.md`
(mirrored at runtime as `~/ora/thinking-tools.md`; id = heading
text up to the em-dash, else with the parenthetical alias stripped, else the
bare heading). Valid mental-model ids are filename stems in
`lenses/`. Unknown ids resolve silently to nothing for the
user (stderr-only warning). The resolved definitions inject into the
**Breadth analyst's system prompt only** — no other pipeline role receives
them. In shipped mode files this section sits after `## DEFAULT GEAR`,
before `## RAG PROFILE`. Mechanism details: `Reference — Pre-Routing
Pipeline Architecture.md` § "Analyst System Prompt Injection — Analytical
Perspectives".]

## CAVEATS AND OPEN DEBATES

[Optional. Populated for modes carrying debates from research report §13
or other surfaced-not-adjudicated debates. Each debate gets both sides
plus citations.]
```

### Field semantics

- `mode_id` — kebab-case identifier; matches filename. Referenced by other modes' `adjacent_modes_in_territory`, by `molecular_spec.components`, by `Reference — Mode Runtime Configuration.md`, by the signal vocabulary registry, and by territory frameworks.
- `canonical_name` — display name, title-case, no suffix. The suffix is generated dynamically by the orchestrator per `suffix_rule`.
- `suffix_rule` — `analysis` (default for analytical operations) | `reading` (interpretive operations like Ma Reading) | `none` (generative T20 modes like Passion Exploration; execution T21 modes like Project Mode).
- `educational_name` — the named technique the mode embodies, used in the educational parenthetical convention `"plain language *(named technique)*"` per Decision E. Maximum 15 words. No acronyms unless the acronym is the canonical/recognizable form, in which case keep the acronym AND expand the letters in a sub-parenthesis (e.g., "SWOT analysis *(strengths, weaknesses, opportunities, threats)*"). The verification script flags any user-visible acronym lacking expansion.
- `territory` — `T<n>-<short-name>` matching an entry in `Reference — Analytical Territories.md`. Every mode lives in exactly one home territory (Decision D). **No `secondary_territories` field.** When a candidate mode appears to fit two territories, parse it.
- `gradation_position` — the mode's position on its territory's primary axis (or one of the secondary axes). Used by within-territory disambiguation trees.
- `composition` — `atomic` (one pass, one posture) or `molecular` (orchestrates other modes plus synthesis). Internal metadata; user never sees this.
- `input_contract` (dual) — `expert_mode` for prompts that explicitly carry domain vocabulary; `accessible_mode` (default) for everyday prompts. `detection` rules let Stage 3 (input completeness check) pick the version. `graceful_degradation` rules let Stage 3 propose lighter sibling modes when required fields are missing.
- `critical_questions` — Walton-style defeasibility conditions. Minimum 3 per mode. Each CQ's negative answer invalidates the mode's output.
- `failure_modes` — named failure patterns this mode is prone to. Each carries a detection signal and correction protocol.
- `lens_dependencies` — `required` (must be available); `optional` (used if available); `foundational` (globally available; named for transparency). Lens ids match `Lenses/<lens-id>.md` filenames.
- `default_depth_tier` — user-facing depth contract: Tier-1 (~1 min, light), Tier-2 (~5 min, thorough — default), Tier-3 (~10+ min, molecular).
- `escalation_signals` — sibling modes within this territory to escalate (heavier), switch (sideways), or de-escalate (lighter) to. Used by Stage 2 sufficiency analyzer when the prompt's signals straddle two siblings.

### Runtime fields live in the mode file (revised 2026-05-12)

Decision C originally specified that runtime mechanics live in a separate `Reference — Mode Runtime Configuration.md` file, keyed by `mode_id`. This split was reversed on 2026-05-12 after the split caused drift failures (the loader for the runtime config was defined but never wired up; mode files fell back to a hardcoded Gear 2 in code while the runtime config claimed Gear 4 universal; per-stage instruction text appeared in both the mode-file body subsections AND the runtime-config `instructions.*` blocks). The runtime configuration file is now archived at `Archive/Reference — Mode Runtime Configuration.md.archived-2026-05-12`.

**All runtime fields now live in the mode file:**

- `gear` — declared in a `## DEFAULT GEAR` section near the bottom of the mode file (e.g., `Gear 4`). The orchestrator's `extract_default_gear` regex reads this directly.
- `expected_runtime` — bullet under `## DEFAULT GEAR` (e.g., `- **Expected Runtime:** ~5min`).
- `context_budget` — bullet under `## DEFAULT GEAR` (e.g., `- **Context Budget:** default`).
- `type_filter` — `### type_filter` subsection inside `## RAG PROFILE` (e.g., ``Retrieve only chunks whose `type` is in: `[engram, resource, incubator]```). The orchestrator's `_extract_mode_type_filter` reads this directly.
- `exclude_tags` — `### exclude_tags` subsection inside `## RAG PROFILE` (e.g., ``Exclude chunks tagged: `[msi-news]``). Filters OUT `knowledge`-collection chunks carrying any listed tag. Only tags registered in `knowledge_index._FILTERABLE_TAGS` are filterable — currently `archived`, `incubating`, `private`, `msi-news`. The orchestrator's `_extract_mode_exclude_tags` reads this directly; exclusion uses `{$ne: True}` so chunks indexed before a tag was registered (field absent) are treated as not carrying it and stay retrievable. Omit the subsection to exclude nothing — the default, so e.g. `msi-news` (Main Street Independent published articles) rides along with curated `resource` chunks at provenance 0.8.
- `RAG_profile.relationship_priorities` — `### RAG PROFILE — RELATIONSHIP PRIORITIES` subsection inside `## RAG PROFILE`.
- Per-stage instructions (depth_pass, breadth_pass, evaluation_pass, revision_pass, consolidation_pass, verification_pass, format_pass) — the existing `## DEPTH ANALYSIS GUIDANCE`, `## BREADTH ANALYSIS GUIDANCE`, `## ANALYTICAL BRIEF AND EVALUATION CRITERIA`, `## REVISION GUIDANCE`, `## CONSOLIDATION GUIDANCE`, `## VERIFICATION CRITERIA`, and `## OUTPUT FORMAT GUIDANCE` body sections (in place per Phase 5/6/7 cascade work plus the 2026-05-14 step 7/8 split). The `instructions.*` YAML blocks in the retired runtime config were dead code with no consumer.

The rationale for consolidation: a single source of truth per mode prevents drift, single-file artifacts are loadable and shareable as one unit, and the original "shareability" argument for the split was theoretical (mode specs would still need transformation to run in any non-Ora orchestrator). See the consolidated-files preference in vault `CLAUDE.md`.

### Step 7 / Step 8 split: corpus and form separated (revised 2026-05-14)

Before 2026-05-14, step 8 ran a final verifier (V1-V8 + mode-specific checks) on the consolidated output, and the consolidator was responsible for producing the user-facing deliverable directly. Two structural problems with that design: (1) the consolidator was doing two distinct jobs at once (semantic synthesis + form-placement), with no observability into which job produced bloat; (2) the final verifier was repeating work the per-stream verifier (step 6) had already done, and its corrective-revision fallback was itself a generative rewrite that could drift.

The 2026-05-14 split separates substance from form:

- **Step 7 (consolidator)** now produces the *irreducible corpus*: semantic atom extraction across both revised streams, cross-stream deduplication, bloat strip, and synthesis per the mode's `## CONSOLIDATION GUIDANCE`. Output is internal to the pipeline.

- **Step 8 (formatter)** takes the corpus and places it into the user-facing deliverable per the mode's `## OUTPUT FORMAT GUIDANCE`. Form-placement only; the formatter does not summarise, condense, or re-decide substance. Universal scaffolding in `f-format.md`.

Mode files gain `## OUTPUT FORMAT GUIDANCE` as a new flat-`##` section. The `## CONSOLIDATION GUIDANCE` section is reshaped from describing the user-facing deliverable to describing the corpus organization and mode-specific bloat patterns. The YAML `output_contract.required_sections` block remains for now (deprecation deferred until all 60 modes have load-bearing `## OUTPUT FORMAT GUIDANCE` sections; deletion is a separate later pass).

The new step 8 (formatter) replaces the prior step 8 (final verifier). Verification of the consolidator's accuracy to the source streams was redundant with the per-stream verifier at step 6; structural defenses against consolidation injection now live in `f-consolidate.md` and `f-format.md`'s anti-confabulation rules.

Universal scaffolding files: `f-consolidate.md` rewritten 2026-05-14 around the four-operation flow (extract → dedup → bloat-strip → synthesise); `f-format.md` authored 2026-05-14 around the three-operation form-placement flow (placement → surface-dedup → non-fitting-postscript). The worked examples in this template will be updated to carry `## OUTPUT FORMAT GUIDANCE` sections as part of Phase 2b per-mode authoring.

### EVALUATION CRITERIA → ANALYTICAL BRIEF AND EVALUATION CRITERIA: cross-stage baseline (revised 2026-05-26)

The 2026-05-26 gear redesign (commit `d4ce7da`) renamed the `## EVALUATION CRITERIA` body section to `## ANALYTICAL BRIEF AND EVALUATION CRITERIA` across all live mode files and changed its runtime role. The section absorbs the analytical brief (What this analysis is / Procedure / Goal) alongside the evaluation criteria and named failure modes, and `build_system_prompt_for_gear` (`~/ora/orchestrator/boot.py`) now injects it — together with `## VERIFICATION CRITERIA` — as a baseline block into **every** pipeline stage's system prompt (analyst, evaluator, reviser, verifier, consolidator, formatter), not just the evaluator's. The section is therefore a cross-stage performance contract: the analyst writes targeting the criteria it will be graded against, and the evaluator, reviser, and verifier all grade against the same canonical statement. The code retains `## EVALUATION CRITERIA` as a legacy extraction fallback only. Injection mechanism details: `Reference — Pre-Routing Pipeline Architecture.md` § "Baseline Criteria Injection (Cross-Stage ANALYTICAL BRIEF)".

### Analytical Perspectives allowlist (revised 2026-06-11)

Mode files carry an optional `## ANALYTICAL PERSPECTIVES` body section — a machine-parsed two-bucket allowlist of Tier 1 de Bono thinking tools and Tier 3 mental-model lenses. At runtime the orchestrator resolves the listed ids (thinking tools against the `## Tier 1 Tool Definitions` section of `~/ora/thinking-tools.md`; mental models against `lenses/` filename stems) and injects the resolved definitions into the **Breadth analyst's system prompt only** — the Depth analyst, evaluator, reviser, verifier, consolidator, and formatter never receive them. Unknown ids resolve silently to nothing for the user (stderr-only warning); an empty or absent section is a clean no-op, so the section is optional. The stanza in the body-subsections block above shows the exact bucket-header lines and example bullets. This allowlist is distinct from the `lens_dependencies` YAML block (a dispatch-gating dependency declaration per `Reference — Lens Library Specification.md` §5) — `lens_dependencies` governs whether the mode may dispatch; `## ANALYTICAL PERSPECTIVES` governs what perspective content the Breadth analyst's prompt carries. Mechanism details (loaders, id-derivation rules, caching, fail-soft semantics): `Reference — Pre-Routing Pipeline Architecture.md` § "Analyst System Prompt Injection — Analytical Perspectives".

---

## Worked Example 1 — Atomic Mode (Cui Bono)

```yaml
# 0. IDENTITY
mode_id: cui-bono
canonical_name: Cui Bono
suffix_rule: analysis
educational_name: who-benefits analysis (cui bono)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: complexity
  value: simple
adjacent_modes_in_territory:
  - mode_id: stakeholder-mapping
    relationship: complexity-heavier sibling (multi-party-descriptive)
  - mode_id: boundary-critique
    relationship: stance-critical counterpart (Ulrich CSH)
  - mode_id: wicked-problems
    relationship: complexity-molecular sibling
  - mode_id: decision-clarity
    relationship: depth-molecular sibling (decision-maker-output)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "trying to understand who's behind this"
    - "want to know who benefits from"
    - "feels like someone's pushing this for a reason"
  prompt_shape_signals:
    - "who benefits"
    - "cui bono"
    - "whose interests"
    - "who's pushing this"
disambiguation_routing:
  routes_to_this_mode_when:
    - "this one situation, single set of beneficiaries"
    - "quick read on who gains from this state of affairs"
  routes_away_when:
    - "landscape of multiple parties with different stakes" → stakeholder-mapping
    - "tangled / wicked / many systems interacting" → wicked-problems
    - "voices being left out of the picture entirely" → boundary-critique
    - "produce a decision document for a decision-maker" → decision-clarity
when_not_to_invoke:
  - "User is evaluating an argument's soundness, not its sponsoring interests" → T1
  - "User is asking about active negotiation strategy" → T13

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [situation_or_artifact, optional_actor_inventory]
    optional: [historical_context, prior_interest_analyses]
    notes: "Applies when user explicitly references actors by name or supplies an actor inventory."
  accessible_mode:
    required: [situation_or_artifact]
    optional: [related_context]
    notes: "Default. Mode infers actor inventory from the situation."
  detection:
    expert_signals: ["actor inventory", "stakeholders are X, Y, Z", "interest groups include"]
    accessible_signals: ["who benefits", "whose interests", "who's behind this"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the situation or paste the article/document you want me to look at?'"
    on_underspecified: "Ask: 'What's the situation, decision, or text you want a who-benefits read on?'"
output_contract:
  artifact_type: mapping
  required_sections:
    - identified_beneficiaries
    - identified_costs_and_who_bears_them
    - power_to_shape_situation
    - voices_present_and_absent
    - confidence_per_finding
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Are the identified beneficiaries actually positioned to benefit, or is the inference symbolic?"
    failure_mode_if_unmet: symbolic-inference (mistaking narrative resonance for actual benefit)
  - cq_id: CQ2
    question: "Are there beneficiaries the analysis is missing because they are not visible from the artifact's frame?"
    failure_mode_if_unmet: frame-bounded-blindness
  - cq_id: CQ3
    question: "Are the costs identified actually borne by the parties named, or is incidence misattributed?"
    failure_mode_if_unmet: cost-incidence-error

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: symbolic-inference
    detection_signal: "Beneficiary identified by ideological alignment rather than concrete benefit pathway."
    correction_protocol: flag
  - name: frame-bounded-blindness
    detection_signal: "All identified parties share the artifact's frame; no parties from outside the frame appear."
    correction_protocol: escalate (to boundary-critique)
  - name: cost-incidence-error
    detection_signal: "Costs are attributed to a party without a concrete payment, time, or freedom-loss pathway."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - rumelt-strategy-kernel (when artifact is a strategy document)
    - ulrich-csh-boundary-categories (when boundary critique cross-cuts)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 2
expected_runtime: ~5min
escalation_signals:
  upward:
    target_mode_id: stakeholder-mapping
    when: "Beneficiary inventory exceeds 5 parties or interest structure is multi-layered."
  sideways:
    target_mode_id: boundary-critique
    when: "Most identified parties are inside one frame; boundary-critique surfaces parties outside it."
  downward:
    target_mode_id: null
    when: "Cui Bono is already the lightest mode in T2."
```

```markdown
## DEPTH ANALYSIS GUIDANCE

Going deeper in Cui Bono means tracing concrete benefit pathways (money flows,
power-position changes, time-and-attention captures, narrative-control gains)
rather than asserting alignment-based benefit. A thin pass names parties; a
substantive pass names the pathway by which each party benefits and the
counterparty's loss-pathway. Test depth by asking: could the analysis predict
how each beneficiary would behave if the situation changed?

## BREADTH ANALYSIS GUIDANCE

Widening the lens means scanning for parties not visible from the artifact's
own frame: parties who would benefit if the situation were framed
differently; parties who pay costs the artifact treats as natural; parties
absent from the discussion whose voices would change the analysis. Breadth
markers: the analysis surveys the boundary of who is and isn't being asked.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

Evaluate against the three critical questions: (CQ1) symbolic vs. concrete
benefit; (CQ2) frame-bounded blindness; (CQ3) cost-incidence accuracy. The
named failure modes are the evaluation checklist. A passing Cui Bono output
names parties, names benefit pathways concretely, surfaces boundary cases,
and assigns confidence per finding.

## REVISION GUIDANCE

Revise to add concrete pathways where the draft asserts benefit without
mechanism. Revise to add boundary-cases (parties absent or marginalized).
Resist revising toward neutrality if the analysis surfaces real
power-asymmetries — the mode is descriptive of interest structure, not
neutralizing of it.

## CONSOLIDATION GUIDANCE

Consolidate as a structured mapping: parties (with concrete benefit
pathways), costs (with concrete incidence), power-to-shape (who has it),
voices-present-and-absent (boundary), confidence per finding. Format:
structured. Each row is auditable.

## VERIFICATION CRITERIA

Verified means: every named beneficiary has a concrete benefit pathway;
every named cost has a concrete bearer; the analysis has surfaced
absent-voices or explicitly noted that boundary-critique was deferred.
Confidence per finding accompanies every claim.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **row-auditable who-benefits mapping**. Place the
consolidated-corpus atoms into:

1. **Institutional authorship.** Naming the authoring institution.
2. **Stated rationale.** The author's own framing of why.
3. **Distributional impact.** Paired beneficiary / cost-bearer rows with
   concrete pathway and the specific parameter driving each.
4. **Alternative design from the opposite constituency.** Constructed with
   equal technical sophistication.
5. **Motivational analysis (FGL).** Fear / Greed / Laziness applied
   symmetrically across constituencies.
6. **Legitimate value.** Non-distributional value the position serves,
   separated from the distributional overlay.
7. **Confidence per finding.**

Per-section conventions: parameters are named with audit-level specificity;
alternative design is grounded in the disadvantaged constituency's interests
(not the analyst's preferences); FGL is symmetric across sides; intent
attribution requires named evidence (structural incentives are the default
explanatory frame).
```

---

## Worked Example 2 — Molecular Mode (Wicked Problems Analysis)

```yaml
# 0. IDENTITY
mode_id: wicked-problems
canonical_name: Wicked Problems
suffix_rule: analysis
educational_name: integrated multi-perspective analysis of tangled problems (wicked problems analysis, Rittel-Webber lineage)

# 1. TERRITORY AND POSITION
territory: T2-interest-and-power
gradation_position:
  axis: complexity
  value: systemic
  depth_axis_value: molecular
adjacent_modes_in_territory:
  - mode_id: cui-bono
    relationship: complexity-lighter sibling (simple)
  - mode_id: stakeholder-mapping
    relationship: complexity-mid sibling (multi-party-descriptive — note: lives in T8)
  - mode_id: decision-clarity
    relationship: depth-molecular sibling (decision-maker-output operation)
  - mode_id: boundary-critique
    relationship: stance counterpart (critical/Ulrich CSH)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "this feels tangled"
    - "every solution we try makes it worse somewhere else"
    - "the problem itself keeps shifting as we try to define it"
    - "stakeholders disagree about what the problem even is"
  prompt_shape_signals:
    - "wicked problem"
    - "everything is connected"
    - "no clean solution"
    - "tradeoffs across multiple dimensions"
disambiguation_routing:
  routes_to_this_mode_when:
    - "tangled / wicked, want full integrated analysis with stakeholder + systems + scenario + adversarial views"
    - "willing to spend 10+ minutes for the deep version"
  routes_away_when:
    - "this one situation, who benefits" → cui-bono
    - "landscape of parties, descriptive" → stakeholder-mapping
    - "produce a decision document for a decision-maker" → decision-clarity
    - "want feedback dynamics analysis specifically" → systems-dynamics-causal
when_not_to_invoke:
  - "User has time pressure (Wicked Problems is Tier-3 ~10+ min)" → cui-bono or wicked-future light variant
  - "Problem is decision-shaped (single decision-maker, defined options)" → decision-clarity or decision-architecture

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: competing-hypotheses
      runs: fragment
      fragment_spec: "hypothesis-list-with-diagnosticity-only (matrix output, no full ACH report)"
    - mode_id: cui-bono
      runs: full
    - mode_id: steelman-construction
      runs: fragment
      fragment_spec: "steelman of two leading framings of the problem"
    - mode_id: systems-dynamics-causal
      runs: full
    - mode_id: scenario-planning
      runs: full
    - mode_id: red-team-assessment
      runs: fragment
      fragment_spec: "adversarial-stress-test of the leading intervention candidate"
  synthesis_stages:
    - name: framing-reconciliation
      type: dialectical-resolution
      input: [competing-hypotheses-fragment, steelman-construction-fragment, cui-bono]
      output: "reconciled framing with named tensions and dominant-frame note"
    - name: dynamic-projection
      type: sequenced-build
      input: [framing-reconciliation, systems-dynamics-causal, scenario-planning]
      output: "dynamic projection of the problem under multiple framings and scenarios"
    - name: intervention-stress-test
      type: contradiction-surfacing
      input: [dynamic-projection, red-team-fragment]
      output: "candidate-intervention catalog with stress-test findings"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence findings

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [problem_statement, stakeholder_inventory, prior_intervention_history]
    optional: [domain_briefing, prior_systems_analyses]
    notes: "Applies when user supplies stakeholder inventory or prior analyses."
  accessible_mode:
    required: [problem_description]
    optional: [contextual_background]
    notes: "Default. Mode elicits stakeholder inventory and prior interventions during execution."
  detection:
    expert_signals: ["stakeholder inventory", "prior interventions", "intervention history"]
    accessible_signals: ["this is wicked", "everything is connected", "solutions keep failing"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'Could you describe the problem and any history of attempts to address it?'"
    on_underspecified: "Ask the user whether they want to spend the time on a full Wicked Problems pass, or a lighter Cui Bono / Stakeholder Mapping read."
output_contract:
  artifact_type: synthesis
  required_sections:
    - reconciled_framing
    - dynamic_projection
    - candidate_intervention_catalog
    - stress_test_findings
    - residual_tensions
    - confidence_map
  format: structured

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Have all major framings been steelmanned, or has the analysis privileged one frame?"
    failure_mode_if_unmet: frame-privileging
  - cq_id: CQ2
    question: "Do the systems-dynamics findings actually integrate with the cui-bono findings, or do they sit in separate silos?"
    failure_mode_if_unmet: silo-aggregation
  - cq_id: CQ3
    question: "Have candidate interventions been stress-tested against the leading adversarial scenarios, or only against neutral projections?"
    failure_mode_if_unmet: stress-test-omission
  - cq_id: CQ4
    question: "Are the residual tensions named explicitly, or has the synthesis collapsed them prematurely?"
    failure_mode_if_unmet: premature-resolution

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: frame-privileging
    detection_signal: "Steelman-construction-fragment surfaces only one framing."
    correction_protocol: re-dispatch (to second steelman pass)
  - name: silo-aggregation
    detection_signal: "Synthesis stage outputs concatenate component outputs without integration."
    correction_protocol: re-dispatch (synthesis stage with explicit integration prompt)
  - name: stress-test-omission
    detection_signal: "red-team-fragment did not run against the leading intervention."
    correction_protocol: flag and re-dispatch
  - name: premature-resolution
    detection_signal: "Output presents a single recommended intervention without residual tensions."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - rittel-webber-wicked-characteristics
    - meadows-twelve-leverage-points
    - senge-system-archetypes
  optional:
    - ulrich-csh-boundary-categories
    - tetlock-superforecasting (when scenarios extend beyond ~5 years)
  foundational:
    - kahneman-tversky-bias-catalog
    - knightian-risk-uncertainty-ambiguity

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Wicked Problems is the heaviest mode in T2's complexity ladder."
  sideways:
    target_mode_id: decision-clarity
    when: "Output should be a decision-clarity document for a decision-maker rather than an integrated analysis."
  downward:
    target_mode_id: cui-bono
    when: "User has time pressure or scope is narrower than initially estimated."

# 10. CAVEATS AND OPEN DEBATES
# (See body section ## CAVEATS AND OPEN DEBATES — Debate D3: wicked problems sui generis or
# extreme cases of complex problems — surfaced not adjudicated; lands here per Phase 8.)
```

```markdown
## DEPTH ANALYSIS GUIDANCE

Depth in Wicked Problems Analysis is the degree to which framing-reconciliation,
dynamic-projection, and intervention-stress-test stages actually integrate
their component outputs rather than concatenating them. A thin molecular pass
runs each component and aggregates; a substantive pass surfaces the tensions
between components and resolves them dialectically. Test depth by asking:
does the synthesis output contain claims that no single component could have
produced?

## BREADTH ANALYSIS GUIDANCE

Breadth in Wicked Problems Analysis is the catalog of framings considered
before the steelman fragment narrows to two leading framings. Widen the
lens to scan: dominant-paradigm framing; stakeholder-position framing;
historical-genealogy framing; cross-domain analogical framing. Even when
only two framings are steelmanned, breadth is documented in the framing-
reconciliation stage.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

Evaluate against CQ1–CQ4. The named failure modes are the evaluation
checklist. A passing Wicked Problems output integrates components rather
than concatenating, surfaces residual tensions explicitly, and assigns
confidence per major finding (especially in the synthesis stages, which
inherit lower confidence from component aggregation).

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates. Revise to surface residual
tensions where the draft has resolved them. Resist revising toward
clean-recommendation framing — Wicked Problems Analysis honors irresolvability;
collapsing tensions is a failure mode, not a polish.

## CONSOLIDATION GUIDANCE

Consolidate as a structured synthesis with the six required sections. Each
section carries provenance to its component sources. The confidence map at
the end is structured (per-finding confidence with reason).

## VERIFICATION CRITERIA

Verified means: every component ran (or was flagged as proceeded-with-gap);
synthesis stages integrated rather than concatenated; residual tensions are
named; confidence map is populated. The four critical questions are
addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is an **integrated multi-perspective synthesis on a wicked
problem**, surfacing irresolvable tensions rather than smoothing them. Place
the consolidated-corpus atoms into:

1. **Problem framing(s).** The steelmanned framings considered, with the
   two-or-three leading framings articulated.
2. **Stakeholder and interest landscape.** Multi-party map with concrete
   interests and unresolved value-conflicts surfaced.
3. **Systems-dynamics findings.** Feedback loops and leverage points,
   linked to the framings rather than siloed.
4. **Convergences and irresolvable tensions.** Where the components agree;
   where they don't, and why the tension is structural rather than a
   defect of analysis.
5. **Open-ended next moves.** Provisional moves that honour irresolvability
   — partial, reversible, scenario-dependent — not clean recommendations.
6. **Confidence map.** Per-finding confidence with reason, with synthesis
   stages tagged for the lower confidence inherited from component
   aggregation.

Per-section conventions: integration not concatenation throughout;
provenance-to-components stays implicit in the body (visible in section 6);
clean-recommendation framing is reshaped to provisional-moves framing —
Wicked Problems Analysis honours irresolvability; collapsing tensions is a
failure mode, not a polish.

## CAVEATS AND OPEN DEBATES

**Debate D3 — Wicked problems: sui generis or extreme cases of complex
problems?** Rittel & Webber (1973) treat wickedness as intrinsic and
distinct from ordinary complexity. Later scholarship (Pesch & Vermaas 2020;
some complexity-science readings) treats wicked problems as extreme cases
along the complexity gradient rather than as a separate category. This mode
operates without adjudicating the debate: it applies the Rittel-Webber
characteristics as analytical lens (treating "wickedness" as a useful
descriptor for problems exhibiting the ten characteristics) while remaining
agnostic on whether wickedness is a category or a degree. Citations:
Rittel & Webber 1973; Pesch & Vermaas 2020.
```

---

## Parsing-Principle Sidebar

When migrating an existing mode (Phase 2) or building a new mode (Phase 4), apply this check before locking the template:

> *Are these the same operation, or are these two operations sharing a name?*
>
> If the candidate mode has the same prompt-shape signals + the same input contract + the same output contract + the same critical questions + the same posture, it is one operation. Lock the template.
>
> If the candidate mode has the same name + the same goal + the same data but **two different operations** (different posture, different output contract, different critical questions, or different lens dependencies), parse it. Create two mode files. They may share a lens.

Applied during architecture lock:

- **Pre-Mortem** → parsed into `pre-mortem-action` (T6, posture-on-plan) + `pre-mortem-fragility` (T7, posture-on-system). Shared `klein-pre-mortem` lens.
- **Systems Dynamics** → parsed into `systems-dynamics-causal` (T4, asks why) + `systems-dynamics-structural` (T17, asks how). Shared feedback-loop lenses.
- **Wicked Problems** → parsed into `wicked-problems` mode (T2, integrated multi-perspective analysis) + `decision-clarity` mode (T2, decision-clarity-document for decision-maker). Existing framework restructured to align with `decision-clarity`.

When in doubt, parse. Two well-specified modes that share a lens are easier to maintain and route than one mode that conflates two operations.

---

## Template Field Quick Reference

| Field | Required | Notes |
|---|---|---|
| `mode_id` | yes | Kebab-case, matches filename |
| `canonical_name` | yes | Title-case, no suffix |
| `suffix_rule` | yes | `analysis` \| `reading` \| `none` |
| `educational_name` | yes | ≤15 words, no acronyms unless canonical with sub-parens |
| `territory` | yes | Single territory; no dual-citizenship |
| `gradation_position` | yes | Axis + value |
| `adjacent_modes_in_territory` | yes | Sibling list with relationships |
| `trigger_conditions` | yes | Situation + prompt-shape signals |
| `disambiguation_routing` | yes | Routes-to + routes-away |
| `when_not_to_invoke` | yes | ≥2 conditions |
| `composition` | yes | `atomic` \| `molecular` |
| `atomic_spec` or `molecular_spec` | yes | Per composition |
| `input_contract` | yes | Dual: expert_mode + accessible_mode |
| `output_contract` | yes | Artifact type + required sections + format |
| `critical_questions` | yes | ≥3 |
| `failure_modes` | yes | ≥1 named pattern with detection + correction |
| `lens_dependencies` | yes | Required + optional + foundational lists |
| `default_depth_tier` | yes | 1 / 2 / 3 |
| `expected_runtime` | yes | ~1min / ~5min / ~10+min |
| `escalation_signals` | yes | Upward / sideways / downward |
| Per-pipeline-stage `##` sections | yes | Six body subsections |
| `## ANALYTICAL PERSPECTIVES` | optional | Two-bucket allowlist (Tier 1 thinking tools + mental-model lenses); resolved at runtime; injects into the Breadth analyst's prompt only |
| `## CAVEATS AND OPEN DEBATES` | optional | Populated when debates apply |

The verification script enforces template conformance per the field list above.

*End of Reference — Mode Specification Template.*
