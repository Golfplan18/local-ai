<!-- Phase 4 Wave 3 entries appended 2026-05-01 (causal-dag, process-tracing, fragility-antifragility-audit, principled-negotiation, third-side, mechanism-understanding, process-mapping, place-reading-genius-loci, information-density). -->


# Reference — Mode Runtime Configuration

Per Decision B, runtime mechanics live separate from mode files. Mode files are clean analytical specs (shareable artefacts that can be quoted, compared, and migrated without leaking infrastructure detail). Runtime mechanics — `gear`, expected runtime, `type_filter`, `context_budget`, RAG profile content, and per-pipeline-stage instruction-design — live in this table keyed by `mode_id`. The orchestrator (post-Phase-9) reads from `~/ora/architecture/runtime-configuration.md` (the ora-runtime pair). Per Decision C, the default is Gear 4 universally; instruction design per pipeline stage controls analytical character, not gear.

## Entry format

Each mode_id entry follows this YAML structure:

```yaml
<mode_id>:
  gear: 4    # default per Decision C
  expected_runtime: ~Nmin
  type_filter: [<content tiers, e.g., engram, resource, incubator>]
  context_budget: <token allocation or "default">
  RAG_profile:
    relationship_priorities:
      prioritize: [<relationships>]
      deprioritize: [<relationships>]
    provenance_treatment: |
      <text describing how provenance is weighted>
  instructions:
    depth_pass: <one-paragraph instruction-design for F-Analysis-Depth>
    breadth_pass: <one-paragraph instruction-design for F-Analysis-Breadth>
    evaluation_pass: <one-paragraph instruction-design for F-Evaluate>
    revision_pass: <one-paragraph instruction-design for F-Revise>
    consolidation_pass: <one-paragraph instruction-design for F-Consolidate>
    verification_pass: <one-paragraph instruction-design for F-Verify>
```

Order of entries: alphabetical by `mode_id` within each territory; territories in numeric order T1–T21. Where a source mode-file lacks an explicit section corresponding to an instruction-design pass, the entry contains a `Phase 2 will author this during template migration` placeholder rather than fabricating content.

## Runtime Configuration Entries

### T1 — Orientation

```yaml
terrain-mapping:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator, reference]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [parent, child, extends, analogous-to]
      deprioritize: [contradicts, supersedes]
    provenance_treatment: |
      Reference-tier retrievals (vault navigation, document registries) are first-class for orientation. Engram-tier positions about the terrain take precedence over speculation. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Identify what is established (settled facts, accepted frameworks, standard terminology) and populate the prose Known territory section as concepts at hierarchy_level 0 or 1. Identify what is unknown, contested, or actively debated as deeper-hierarchy concepts. Flag at least two predictable wrong impressions a newcomer would form from survey-level sources alone, and identify prerequisite knowledge for competent operation.
    breadth_pass: |
      Map the full landscape: major sub-areas, key concepts, foundational distinctions, principal actors or schools of thought. Each sub-area becomes a concept; distinctions become linking phrases. Identify adjacent domains (the borders) and generate at minimum three open questions the user has not asked but would need to answer to navigate the domain effectively. Surface organising structure (hub-and-spoke, hierarchy, network) and entry points that unlock the most territory.
    evaluation_pass: |
      Score against the three rubric extensions: Cartographic Completeness (all major sub-areas + schools represented), Known/Unknown/Open Separation (categories populated and not blurred), Navigational Utility (clear entry points + prerequisite chain + next questions). Mandate fixes when the concept floor (≥4) or cross-link presence (≥1 is_cross_link) fails; mandate when contested positions are presented as settled.
    revision_pass: |
      For S10 (no cross-link) add at least one is_cross_link: true proposition; for S7 (concept floor) expand to ≥4 concepts or route to Deep Clarification; for M1 add known/contested/open prefixes; for M3 add a Boundary statement using the literal phrase "out of scope". Apply the standard short_alt template — name the domain, not every concept.
    consolidation_pass: |
      Not applicable at this mode's default gear (Gear 3). If promoted to Gear 4 for deep multi-domain orientation, merge both streams' concept inventories; retain Depth's known/contested/open classifications; add Breadth's adjacent-domain cross-links as additional is_cross_link: true propositions.
    verification_pass: |
      V-TM-1: ≥1 is_cross_link: true proposition preserved. V-TM-2: revised spec.focus_question matches prose with stem-overlap ≥ 0.6. V-TM-3: spec.concepts retains ≥4 entries; silent drop below floor during revision is a FAIL.
```

### T2 — Wicked / Decision Clarity

```yaml
wicked-problems:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, qualifies, enables, requires, produces]
      deprioritize: [parent, child]
    provenance_treatment: |
      Phase 2 (wicked-problems) will author per Framework — Decision Clarity Analysis.md molecular composition. Engram-tier value-conflict articulations weighted above resource-tier wickedness catalogues; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Phase 2 (wicked-problems) will author this during template migration; the seed will pull from Framework — Decision Clarity Analysis.md and the cui-bono WPF-Escalation handoff payload. Stages will likely include value-conflict mapping, full consequence-landscape modelling across time horizons, and Decision Clarity Document assembly.
    breadth_pass: |
      Phase 2 (wicked-problems) will author this during template migration. Expected to include alternative-constituency framings (inheriting cui-bono structure when WPF arrives via escalation) and stakeholder-value mapping that does not collapse to a single utility function.
    evaluation_pass: |
      Phase 2 (wicked-problems) will author this during template migration. Expected to enforce the three wickedness indicators (incompatible benefit structures; no net-positive intervention; fundamental value conflicts) and reject premature collapse to single-stakeholder optimisation.
    revision_pass: |
      Phase 2 (wicked-problems) will author this during template migration. Expected to preserve value-conflict honesty under reviser pressure and forbid silent collapse of irreducible tradeoffs into apparent resolutions.
    consolidation_pass: |
      Phase 2 (wicked-problems) will author this during template migration. Both streams' independently-developed value-conflict maps and intervention landscapes converge into a single Decision Clarity Document; preserve attribution where streams disagree on which stakeholder values are most load-bearing.
    verification_pass: |
      Phase 2 (wicked-problems) will author this during template migration.

decision-clarity:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: extended
  RAG_profile:
    relationship_priorities:
      prioritize: [composes, requires, enables, contradicts, qualifies, opposes, allies-with]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Wave 4 placeholder superseded 2026-05-01 with the molecular-mode pattern. Component-source provenance is preserved end-to-end: cui-bono interest-tracing chunks, stakeholder-mapping party-inventories, scenario-planning future-arcs, and red-team adversarial-actor analyses each carry their component-of-origin tag through the synthesis. Engram-tier articulations of the actual decision-maker's stated criteria, value tradeoffs, and audience-context dominate; the framework `Framework — Decision Clarity Analysis.md` is method-foundational. Resource-tier wicked-problems and decision-document references inform structure. Incubator-tier observations about specific stakeholder positions and contested values enter as primary evidence. Component-output provenance (which finding came from which composed mode) is preserved through depth → consolidation, never collapsed into anonymous synthesis. P1/P2 over P3-P6; component-level conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Decision Clarity is a molecular composition of cui-bono + stakeholder-mapping + a scenario-planning fragment + a red-team fragment, integrated into a single decision-maker-facing document. Run each component as a substantive pass — not a one-line invocation. (1) Cui bono: trace beneficiaries and bearers across the contested value domains; do not stop at first-order beneficiary. (2) Stakeholder mapping: inventory parties with stated positions, inferred underlying interests, BATNA-style alternatives, and power asymmetries; flag inferred-vs-confirmed throughout. (3) Scenario-planning fragment: generate 2-3 distinct futures conditional on the decision, each with its own beneficiary/bearer profile (not generic optimistic/pessimistic). (4) Red-team fragment: name the strongest adversarial reading of each candidate option, including reputational and second-order risks the decision-maker's frame would miss. Integration is the load-bearing operation — produce ONE document where each section's findings inform the others (red-team findings reshape stakeholder-impact analysis; scenario-fork findings reshape cui-bono trace), rather than four-section concatenation. Component-as-section-stub is the primary failure mode here. Test depth by asking: could the document be cut into its four component findings and would each component finding survive independently as a substantive pass of that component mode?
    breadth_pass: |
      Survey alternative compositional balances before locking the synthesis: would the document benefit from heavier scenario weight (high-uncertainty future) or heavier stakeholder weight (high-conflict-among-parties present)? Consider whether composition should add a fifth fragment (e.g., constraint-mapping for decision-under-uncertainty cases) or drop one (e.g., red-team when the decision-maker is already adversarial-minded). Scan for component-substitution alternatives: stakeholder-mapping vs. boundary-critique (the latter when excluded-voices are the load-bearing concern); scenario-planning vs. probabilistic-forecasting (the latter when probability-over-narrative is what the decision-maker needs). Breadth markers: at least one alternative compositional balance is named, at least one component-substitution is considered (even if rejected), and the audience-context (who reads this document, what they will do with it) is explicit.
    evaluation_pass: |
      Score the integrated output, not the components in isolation. Critical questions: (CQ1) does each component pass meet its own substantive depth bar (not stub-level); (CQ2) is the integration load-bearing (component findings reshape each other) rather than sectional concatenation; (CQ3) does the document address an actual decision-maker with a named decision; (CQ4) are stakeholder positions distinguished from inferred interests with hypothesis-flagging; (CQ5) does the scenario fork show distinct beneficiary/bearer profiles per future; (CQ6) is the red-team reading actually adversarial (not soft critique); (CQ7) does provenance show which finding came from which composed mode? Named failure modes (component-as-stub, integration-as-concatenation, missing-decision-maker, position-interest-conflation, generic-scenarios, soft-red-team, provenance-collapse) are the evaluation checklist. Mandate fix when any component is one-paragraph-only, when integration is sectional rather than mutual, when the decision-maker is unstated, when stakeholder positions are restated as interests, when scenarios are generic optimistic/pessimistic, when red-team is critique rather than adversarial, or when component-of-origin attribution is lost.
    revision_pass: |
      Synthesis-revision must not lose component provenance. When integrating findings across components, preserve the component-of-origin tag — a finding sourced from cui-bono carries that origin through revision. Add depth where any component reads as stub. Make integration mutual where the draft concatenates. Name the decision-maker and the decision where they are absent. Distinguish stated positions from inferred interests with hypothesis-flagging where the draft conflates them. Make scenarios distinct where they read generic. Strengthen red-team where it reads as critique. Resist revising toward false synthesis — where component findings genuinely conflict (e.g., cui-bono identifies one party as bearer while stakeholder-mapping identifies that same party as beneficiary), the conflict belongs in the document, not papered over. The mode's character is decision-maker-facing molecular synthesis with component-traceability, not cleaned-up consensus.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full molecular documents independently. Reference frame: union of component findings across streams (de-duplicated by finding-stem, not by component-section), with component-of-origin AND stream-of-origin tags preserved. Convergent component findings (both streams' cui-bono identified the same primary beneficiary) get high-confidence flag. Divergent integrations (one stream led with stakeholder-conflict, the other with scenario-fork) surface as alternative document arcs in prose; the more decision-maker-actionable arc is preferred for the lead, with the other preserved as alternative framing. Component-attribution survives consolidation: the final document shows which finding came from which composed mode, AND where streams agreed/disagreed on that finding. Provenance-collapse in consolidation is a critical failure here.
    verification_pass: |
      V-DC-1: all four composed components are substantively present (not stubbed). V-DC-2: integration is load-bearing — at least three cross-component reshapings are visible (e.g., red-team finding visibly reshaped stakeholder-impact section). V-DC-3: decision-maker and decision are explicitly named. V-DC-4: stakeholder positions are distinguished from inferred interests with hypothesis-flagging. V-DC-5: scenario fork shows distinct beneficiary/bearer profiles per future (not generic optimistic/pessimistic). V-DC-6: red-team reading is adversarial (names the strongest case against, including reputational/second-order risks). V-DC-7: component-of-origin provenance is visible per major finding. V-DC-8: confidence per finding accompanies every claim. V-DC-9: pairing with `Framework — Decision Clarity Analysis.md` is honored (document structure aligns with framework's decision-document spec).
```

### T3 — Diagnosis

```yaml
root-cause-analysis:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [causes, enables, requires, produces, precedes, derived-from]
      deprioritize: [analogous-to, supersedes, parent, child]
    provenance_treatment: |
      Causal_claim subtyped chunks within engram and incubator deserve highest weight when tracing the chain. Process-failure references at engram tier outweigh anecdotal failure reports — but anecdotes still surface as evidence to be assessed. P1/P2 over P3-P6; conflicts surfaced.
  instructions:
    depth_pass: |
      State the presented problem precisely (the noun phrase usable verbatim as spec.effect). Declare the categorisation framework (6M/4P/4S/8P/custom) with rationale; this becomes spec.framework. For each proposed cause, ask what caused this cause — push to ≥2 levels deep on at least one branch (sub_causes nesting ≥2 somewhere). Distinguish root causes (removal would prevent recurrence) from contributing factors (increase probability without independent causation). For each causal link, distinguish causation from correlation; challenge any chain terminating at "human error" or "bad judgment" by recording the deeper process cause as a sub_cause.
    breadth_pass: |
      Generate at minimum two alternative causal chains for the same symptom; the first chain is not necessarily correct. Identify contributing factors that interact with the primary chain (amplifiers, not roots). Map convergence patterns: if multiple chains converge on the same symptom, the actual cause may be their interaction; if interaction contains a feedback loop, prefer causal_loop_diagram emission. Distinguish corrective actions (fix current instance) from preventive actions (prevent future instances); flag any leaf cause that is non-actionable for the user's role.
    evaluation_pass: |
      Score against extended rubric: Causal Depth (≥3 levels), Root vs Contributing Distinction, Evidence per Link (causation vs correlation assessed), Framework Coherence. Prioritise framework coherence first (C1, S7, S11), then effect phrasing (S6 — no solution-verb prefixes), then depth floor (S10 — at least one branch reaches sub_cause depth 2), then process-not-people terminal (M4 — load-bearing epistemic commitment), then short_alt discipline (S12 — Cesal form, ≤150 chars).
    revision_pass: |
      For S12 apply the short_alt template ("Fishbone of <noun phrase ≤60 chars>"). For S11 rename non-canonical category names to canonical strings (no slashes, no aliases). For M3 deepen trivial sub-cause paraphrases by naming a process/policy/resource one step deeper than parent. For M4 add a sub-cause to human-error leaves naming the process that permitted or incentivised the error. For C2 align the presented-problem first sentence with spec.effect verbatim.
    consolidation_pass: |
      Not applicable at default Gear 3. If promoted to Gear 4 by user override (typically when competing causal chains need independent investigation), use Depth's framework declaration as the reference frame for the envelope. Present Breadth's alternative chains as a dedicated "Alternative causal framings" prose section; the envelope emits only the dominant chain.
    verification_pass: |
      V-RCA-1: spec.framework in revised envelope equals framework named in revised prose's Chosen-framework paragraph. V-RCA-2: every root cause identified in revised prose appears as a leaf cause.text or sub_cause.text in revised envelope. V-RCA-3: sub_cause depth ≥2 preserved unless reviser CHANGELOG names the reduction with explicit justification. V-RCA-4: if spec.framework != "custom", every spec.categories[].name remains in framework's canonical set.
```

### T4 — Causal cascades

```yaml
consequences-and-sequel:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [produces, enables, precedes, requires, contradicts]
      deprioritize: [parent, child]
    provenance_treatment: |
      Engram-tier guard rails about second-order effects override speculative chat-tier projections. P1/P2 over P3-P6; conflicts surfaced. Forward-projection draws on user-vetted constraints (engram), domain knowledge (resource), and unreviewed atomic claims (incubator).
  instructions:
    depth_pass: |
      Audit each causal link for logical soundness with a stated mechanism. Distinguish causally linked consequences from co-occurrences. Identify where the cascade has been stopped prematurely; continue to second or third order. For each consequence, identify the specific condition under which it would NOT follow. Detect feedback loops — if present, flag for SD transition; C&S is the wrong tool for cycles. Challenge the time-horizon distribution.
    breadth_pass: |
      Trace the causal cascade forward, with each effect becoming a cause. Classify each link by time horizon (immediate / short / medium / long). Identify unintended consequences. Identify reinforcing vs counteracting branches and cross-domain crossings. Identify leading indicators for the most consequential distant effects.
    evaluation_pass: |
      Score against the four-criterion rubric extensions: Chain Depth (third-order reached), Link Quality (mechanism per link), Time-Horizon Distribution (≥3 of immediate/short/medium/long), Unintended Consequence Identification. Prioritise: acyclicity (S8 — DAG with cycle is rejected); chain depth (S10 — ≥1 path of length ≥3); node count (S9 — ≥5 nodes); mechanism per link (M1); short_alt (S11).
    revision_pass: |
      For S8 cycle: either remove one edge with documented rationale or suppress the envelope and propose SD transition. For S10 extend at least one branch by asking what each effect causes next. For M1 add a mechanism sentence to every association-only link, or flag as speculative. For M3 add at least one unintended consequence prefixed "unintended consequence:". For M5, if a feedback loop appears during revision, suppress envelope and transition to SD.
    consolidation_pass: |
      Not applicable at default Gear 3. If promoted to Gear 4 — typically when the cascade crosses multiple domains — use Depth's cascade structure as reference frame; merge Breadth stream's cross-domain branches as additional subpaths in the causal_dag DSL.
    verification_pass: |
      V-CS-1: revised envelope is acyclic. V-CS-2: revised focal_exposure and focal_outcome match prose's Action and dominant outcome. V-CS-3: ≥1 path of length ≥3 in revised envelope. V-CS-4: every link in revised envelope has a corresponding mechanism sentence in revised prose.

systems-dynamics-causal:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, produces, requires, contradicts, qualifies]
      deprioritize: [parent, child, supersedes]
    provenance_treatment: |
      Engram-tier loop articulations and stock-and-flow models override partial loop fragments retrieved from chat or incubator. Cross-domain analogies surfaced in resource tier are useful for structural pattern matching but should not import policy claims unmodified. P1/P2 over P3-P6; conflicts surfaced. (T4 entry — causal-flavoured emphasis: trace counterintuitive behaviour over time; pair with consequences-and-sequel for forward-vs-loop disambiguation.)
  instructions:
    depth_pass: |
      Define the system boundary explicitly — what is inside, what is outside; this shapes which variables get declared. Identify stocks and flows where magnitudes and units are known or estimable. Identify all feedback loops and classify each as reinforcing (R) or balancing (B). Identify delays — the most common source of counterintuitive system behaviour; mark delayed edges. Verify each loop is genuinely circular (closing edge returns to start variable). Identify at minimum one counterintuitive behaviour. Verify loop polarity parity matches declared type.
    breadth_pass: |
      Map the complete feedback structure with behaviour-grounded loop labels. Identify system archetypes (Fixes That Fail, Shifting the Burden, Limits to Growth, Eroding Goals, Escalation, Success to the Successful, Tragedy of the Commons, Growth and Underinvestment) using canonical names exactly. Rank leverage points using Meadows' hierarchy (parameters → buffer sizes → stock-and-flow structure → delays → feedback loops → information flows → rules → self-organisation → goals → paradigms). Distinguish robust interventions (work across system states) from fragile ones.
    evaluation_pass: |
      Score against extended rubric: Feedback Structure, Archetype Recognition, Leverage Point Quality, Polarity Integrity. Prioritise: loop-or-nothing (S9 — CLD with empty loops is rejected), polarity parity (S10 — mandate fix with explicit edge-count), loop genuineness (M1 — chain mis-labelled as loop is silent failure), boundary honesty (M5), archetype-loop fit (M3 — name-drops without matching structure fail), short_alt (S12 — name dominant loop's behaviour, not variables).
    revision_pass: |
      For S12 apply short_alt template. For S9 enforce loop id pattern ^[RB][0-9]+$. For S10 count − edges along loop members: even ⇒ R; odd ⇒ B; update whichever is inconsistent. For M1 verify the closing edge exists in spec.links; if absent, add or remove the loop. For M3 either remove the archetype name or add the characteristic loop. For M4 annotate each leverage point with "Depth level N:" per Meadows.
    consolidation_pass: |
      Both streams' independently developed CLDs are the core signal. Reference frame: Depth's variable set + loop declarations + boundary. Convergent loops with matching type+polarity get high-confidence flag in prose. Divergent polarity: surface both readings; do NOT average; either keep Depth's polarity with Breadth objection in caveats, or drop the edge if unresolvable. Different archetype names: keep both in prose as Candidate archetypes; envelope does not encode archetype choice.
    verification_pass: |
      V-SD-1: every loop in revised spec.loops has declared type matching −-edge parity. V-SD-2: archetypes named in revised prose each have a matching loop in revised spec.loops. V-SD-3: every variable named as loop member in revised prose has matching spec.variables[].id. V-SD-4: variables outside revised prose's declared boundary are absent from revised spec.variables.
```

### T5 — Decision under uncertainty

```yaml
decision-under-uncertainty:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, requires, contradicts, qualifies]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Tradeoff engrams (user's vetted decision criteria) outweigh data-bearing resources when the two conflict. P1/P2 over P3-P6; conflicts surfaced rather than averaged. DUU draws tradeoff articulations from engram and data-bearing claims from resource.
  instructions:
    depth_pass: |
      Frame the decision: alternatives (including defer/sequence/hedge), possible outcomes, what can be deferred. Classify uncertainty type for each critical variable as risk (assignable probability), uncertainty (estimable range), or deep uncertainty (no meaningful probability). For each alternative under each plausible state, assess consequences — quantify (terminal payoffs) or characterise qualitatively where quantification would mislead. Challenge probability estimates against base rates; assess downside exposure for each alternative; evaluate whether the framing artificially constrains alternatives.
    breadth_pass: |
      Identify alternatives the framing may have excluded; consider sequencing, options that preserve flexibility. Conduct value-of-information analysis: what would most reduce uncertainty, what would it cost, is its expected value > cost of delay? Identify hedging strategies that reduce downside without forfeiting upside. Identify robust alternatives (perform acceptably across plausible states) — tornado is the natural envelope when robustness-vs-parameter-swing is the question. Assess reversibility and cost of reversal for each alternative.
    evaluation_pass: |
      Score against the four-criterion extension: Uncertainty Classification, Decision Framing Quality, Value-of-Information Assessment, Envelope Match. Prioritise: envelope-match first (M4, S3 — wrong type invalidates structural framing), probability-sum (S8 — non-summing chance children rejected), two-value-nodes trap (S9 — exactly one value node in influence_diagram), utility-units consistency (C4), missing-defer (Decision Framing rubric), short_alt (S12 — name dominant comparison, not every branch).
    revision_pass: |
      For S12 apply short_alt template per envelope type. For S8 adjust chance-node children probabilities to sum to 1.0 ± 1e-6. For S9 merge to exactly one value node. For M4 switch envelope type to match framing (sequential ⇒ decision_tree; dependency ⇒ influence_diagram; sensitivity ⇒ tornado). For C4 align spec.utility_units with prose's consequence-analysis units verbatim. Add a Do-nothing/defer or Run-pilot-first branch when the user has reversibility and the framing was binary.
    consolidation_pass: |
      Not applicable at default Gear 3. If promoted to Gear 4 — typically when multi-actor dynamics require independent framing — use Depth's decision-tree structure as reference frame; present Breadth's additional alternatives (information-gathering, hedging, sequencing) as additional first-level branches added to Depth's tree. Reconcile probability disagreements by emitting both estimates as a range and taking midpoint to spec; flag as uncertainty.
    verification_pass: |
      V-DUU-1: every chance node's children probabilities sum to 1.0 ± 1e-6. V-DUU-2: spec.utility_units in revised envelope equals prose's consequence-analysis units string verbatim. V-DUU-3: revised prose's Recommendation: line names a first-level branch that exists in revised spec.root.children. V-DUU-4: silent envelope-type change without CHANGELOG rationale is a FAIL.
```

### T6 — Constraint mapping

```yaml
constraint-mapping:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [requires, enables, contradicts, qualifies]
      deprioritize: [analogous-to, precedes]
    provenance_treatment: |
      Engrams that articulate hard constraints outweigh resource-tier constraint catalogues; soft constraints are tier-weighted normally. P1/P2 over P3-P6; conflicts surfaced rather than averaged. Constraint analysis prioritises user-vetted constraints (engram) above derived or inferred constraints.
  instructions:
    depth_pass: |
      For each alternative, identify success conditions (what must be true) and failure conditions. Quantify gains and forfeitures where possible. Test success conditions for realism (plausible vs best-case). Identify hidden dependencies. Identify at minimum one alternative the Breadth model may have omitted.
    breadth_pass: |
      Map all candidate alternatives, including any the user has not named (≥3 minimum). For each alternative generate conditions under which it would be the clearly best choice. Identify hybrid options or sequencing strategies. For each alternative identify what is uniquely gained and what is forfeited. Surface "no-lose" elements valuable regardless of choice.
    evaluation_pass: |
      Score against three rubric extensions: Alternative Coverage, Condition Specificity (testable propositions), Gain/Forfeit Balance. Prioritise: subtype match (S7 — strategic_2x2, NOT scenario_planning), three-alternative floor (S8/M1), pro_con shape if binary (S10), axes independence (M4 — Pearson |r| ≤ 0.7), no-advocacy/symmetric depth (M5), short_alt (S11 — name comparison axis, not every alternative).
    revision_pass: |
      For S7 set spec.subtype = 'strategic_2x2'. For S8 add alternatives until ≥3 OR switch to pro_con if genuinely binary. For S10 ensure pros ≥2, cons ≥2 with non-empty text and non-empty claim. For M4 redesign axes when items cluster along a diagonal, or drop to pro_con. For M5 equalise analytical depth across alternatives (same sections for each).
    consolidation_pass: |
      Not applicable at default Gear 3. If promoted to Gear 4, merge alternatives from both streams into the envelope's items list; Depth's per-alternative placement on the 2×2 is reference unless Breadth can argue a different positioning with evidence.
    verification_pass: |
      V-CM-1: revised spec.subtype == "strategic_2x2" (or envelope is pro_con). V-CM-2: revised quadrant_matrix has ≥3 items OR envelope is pro_con. V-CM-3: revised envelope's items (x, y) positions are consistent with revised prose's per-alternative analysis.
```

### T7 — Single-proposal evaluation

```yaml
benefits-analysis:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, produces, contradicts, qualifies, requires]
      deprioritize: [parent, child, supersedes]
    provenance_treatment: |
      Engrams that articulate the user's tradeoff priorities outweigh resource-tier benefit catalogues. P1/P2 over P3-P6; conflicts surfaced rather than averaged. BA tracks what a proposal enables, produces, contradicts, and qualifies.
  instructions:
    depth_pass: |
      Audit Plus column for motivated optimism; mark each with its load-bearing assumption (populates spec.pros). Audit Minus column for thoroughness (populates spec.cons). Audit Interesting column for non-obvious implications — precedent, signalling, path-dependency. For each Plus claim identify mechanism; flag claims without mechanism. For each Minus assess mitigation. Identify claims that flip between Plus and Minus depending on perspective.
    breadth_pass: |
      Produce three columns with explicit, concrete claims (not generic). Populate Interesting with second-order implications. Stress-test each claim against the user's actual context. Identify the most consequential item in each column. Map affected parties; surface asymmetries (Plus for one party, Minus for another). Surface analytical uncertainty where evidence is thin.
    evaluation_pass: |
      Score against four rubric extensions: Column Distinctness, Specificity (grounded in user's case), Second-Order Coverage, Asymmetry Detection. Prioritise: no-advocacy (M5 — BA does not recommend unless asked), three-column floor (M1/S8 — Plus/Minus/Interesting all populated), pro_con shape (S8 — pros ≥2, cons ≥2), specificity (M2), second-order coverage (M3 — at least one precedent/signalling/path-dependency), short_alt (S11).
    revision_pass: |
      For S11 apply short_alt template ("Pro/con tree for <proposal stem ≤80 chars>"). For S8 add pros/cons until ≥2 each. For M1 populate any missing column with ≥1 concrete item OR explicit "No items identified after audit" statement. For M2 replace generic claim with concrete version citing user-specific features. For M3 add Interesting item prefixed "Second-order:" capturing precedent/signalling/path-dependency. For M5 remove unsolicited recommendation; spec.decision empty unless user asked for a lean.
    consolidation_pass: |
      Not applicable at default Gear 3. If promoted to Gear 4 for high-stakes/politically-charged proposals, merge both streams' columns; de-duplicate by text stem-overlap; preserve Breadth's second-order items in the Interesting channel as a priority.
    verification_pass: |
      V-BA-1: revised prose and spec.decision do not recommend adoption unless user asked. V-BA-2: revised prose still has Plus/Minus/Interesting (or explicit "none identified" for any empty column). V-BA-3: revised spec.claim ≈ revised prose's "Proposal:" sentence.
```

### T8 — Scenario planning

```yaml
scenario-planning:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, requires, produces, precedes, qualifies]
      deprioritize: [parent, child]
    provenance_treatment: |
      Scenario-shaping engrams (user's vetted views on which axes drive divergent futures) outweigh resource-tier scenario catalogues. P1/P2 over P3-P6; conflicts surfaced rather than averaged. Scenario construction needs vetted scenario-shapes plus domain trends.
  instructions:
    depth_pass: |
      Identify the focal question/strategic decision precisely; the envelope's quadrants operationalise it. Map all driving forces and classify each as predetermined (will happen regardless) or critical uncertainty (could go either way). For each critical uncertainty, assess range of plausible outcomes and identify leading indicators. Evaluate scenarios for internal consistency. Test whether scenarios are genuinely structurally distinct or variations of the same future with different magnitudes. Stress-test proposed strategies against each scenario.
    breadth_pass: |
      From the two most critical uncertainties, construct a 2×2 with four structurally distinct scenarios (each occupying one quadrant). Develop each scenario with name, coherent causal logic, key characteristics. Generate at minimum one wild-card scenario outside the 2×2 (prose-only). For each scenario identify opportunities. Identify robust strategies (work across scenarios) vs scenario-dependent strategies. Identify contingent actions tied to leading indicators.
    evaluation_pass: |
      Score against four rubric extensions: Scenario Distinctiveness, Uncertainty/Predetermined Separation, Strategic Actionability, Axes Independence. Prioritise: subtype match (S7 — scenario_planning, NOT strategic_2x2), four-quadrant populated (S8 — all of TL/TR/BL/BR with name + narrative), axes independence rationale (S10/M4 — must argue decoupling, ≥40 chars), no-most-likely invariant (M5 — SP does not predict), scenarios structurally distinct (M2 — good/bad/medium fails the mode), short_alt (S12 — name axes, not scenarios).
    revision_pass: |
      For S12 apply short_alt template. For S7 set spec.subtype = 'scenario_planning'. For S8 populate all four quadrants with non-empty name and narrative. For S10 expand axes_independence_rationale to argue decoupling (≥40 chars). For M2 rewrite scenario names by defining mechanism (e.g. 'Constrained boom', 'Wild west'), not optimistic/pessimistic/baseline. For M5 remove "most likely" designation.
    consolidation_pass: |
      Both streams' independently-generated scenarios are the core signal. Reference frame: the four scenarios agreed-upon (Depth + Breadth convergence). Axis-disagreement: emit Depth's axes; preserve Breadth's as "Alternative framing considered:". Scenario-name disagreement: combine as "<Depth name> / <Breadth name>" in quadrants.X.name. Wild-card reconciliation: emit both streams' wild-cards in prose. Do not designate any scenario as "most likely" — mode-critical invariant.
    verification_pass: |
      V-SP-1: revised envelope has all four quadrants with non-empty name and narrative. V-SP-2: revised spec.subtype == "scenario_planning"; silent switch is a FAIL. V-SP-3: revised prose does not designate any scenario as "most likely" or "highest-probability". V-SP-4: revised axes_independence_rationale ≥ 40 chars.
```

### T9 — Hypothesis testing

```yaml
competing-hypotheses:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [supports, contradicts, qualifies, analogous-to]
      deprioritize: [parent, child, precedes]
    provenance_treatment: |
      Hypothesis-supporting evidence is weighted by tier; conflicting evidence is surfaced explicitly rather than averaged. P1/P2 over P3-P6. ACH needs evidence from multiple tiers to populate the hypothesis matrix.
  instructions:
    depth_pass: |
      List all plausible hypotheses including at minimum one not proposed by the user (each becomes spec.hypotheses[] with id Hn). List all significant evidence regardless of which hypothesis it supports (each becomes spec.evidence[] with credibility H/M/L and relevance H/M/L). For each piece of evidence, assess consistency with each hypothesis using Heuer's vocabulary (CC/C/N/I/II/NA), populating a fully-populated spec.cells. Assess diagnosticity — evidence consistent with all hypotheses provides no diagnostic value. Identify most-diagnostic evidence (rows with mixed CC/C vs I/II). Challenge Breadth's hypothesis list. Conduct sensitivity analysis on the most diagnostic evidence.
    breadth_pass: |
      Generate the widest plausible set of hypotheses including unconventional ones (≥5 for non-trivial; ≥3 minimum for diagnosticity). For each hypothesis identify what evidence would disconfirm it (more diagnostic than confirmation). Identify what evidence is missing that would be most useful — what single piece would most change the analysis. For each surviving hypothesis identify its strongest explanatory advantage and leading indicators. Assess what the user gains even if no single hypothesis is confirmed.
    evaluation_pass: |
      Score against four extensions: Hypothesis Coverage, Diagnosticity Assessment, Disconfirmation Rigour, Cell Completeness. Prioritise: cell-completeness (S9 — missing cells invalidate the matrix mechanically), Heuer vocabulary compliance (S10 — English labels rejected), at least one diagnostic row (S12 — all-uniform matrix is tautologically non-diagnostic), elimination framing (M2 — confirmation framing is load-bearing failure), conclusion-cell-tally agreement (C3), short_alt (S13).
    revision_pass: |
      For S13 apply short_alt template ("ACH matrix showing <surviving hypothesis label ≤80 chars> as the surviving hypothesis after elimination"). For S9 fill missing cells with NA explicitly when evidence does not bear on the hypothesis. For S10 replace English labels with CC/C/N/I/II/NA. For S12 introduce a diagnostic evidence item or revise default-N cells. For M2 rewrite Tentative Conclusions from "H_x is supported by..." to "H_x survives because fewer evidence items contradict it — N I + N II cells". For C3 recount I+II cells per hypothesis; endorse the fewest (tie-break by fewer II).
    consolidation_pass: |
      Both streams produce independent matrices. Reference frame: union of hypotheses (de-duplicated by label) and union of evidence items. Use Depth's cell values where streams agree; where they disagree, prefer Depth's (cross-the-matrix posture) and surface disagreement in prose. Hypothesis-addition rule: Breadth's additional hypotheses get added as new columns; Depth estimates cells via reasoning from the evidence (or marks as N with disclosure if extension impossible). Conclusion reconciliation: if streams endorsed different surviving hypotheses, present both with cell-count arithmetic; envelope uses the hypothesis with fewest I+II cells (tie: fewer II). Deception: retain the flag from either stream.
    verification_pass: |
      V-CH-1: revised spec.cells has an entry for every (evidence_id × hypothesis_id) pair. V-CH-2: every cell value is from {CC, C, N, I, II, NA}. V-CH-3: revised prose's named surviving hypothesis has fewest I+II cells; tie-break: fewer II. V-CH-4: revised hypothesis ids and evidence ids match those referenced in reviser's ADDRESSED citations unless CHANGELOG declares the renaming.
```

### T10 — Strategic interaction

```yaml
strategic-interaction:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, requires, produces, contradicts]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Game-theoretic engrams (user's vetted strategic principles) outweigh heuristic resource-tier strategy advice. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Identify players, strategies, and payoffs in each actor's own value terms; for sequential games, actors become decision nodes alternating in the game tree. Classify the game on four dimensions: timing (sequential/simultaneous), information (complete/incomplete; perfect/imperfect), duration (one-shot/repeated), sum (zero-sum/non-zero-sum). Identify equilibria using the appropriate method (sequential ⇒ backward induction/subgame perfect; simultaneous ⇒ Nash pure+mixed; repeated ⇒ cooperation sustainability). Stress-test equilibrium robustness. Assess credibility of threats/promises (Schelling). Identify information asymmetries.
    breadth_pass: |
      Map alternative game structures — alternative move-order, information assumption, or strategy set. Identify less-obvious strategies: commitment devices, game-changing moves, coalition possibilities, outside options. Assess whether the game is better modelled as part of a larger repeated interaction. For each actor identify the most favourable feasible outcome and barriers to mutual gains. Provide specific recommendations including commitment devices and contingent strategies.
    evaluation_pass: |
      Score against three rubric extensions: Game Classification Accuracy, Equilibrium Identification, Strategic Actionability. Prioritise: probability-on-decision-edge trap (S8 — validator rejects), two-value-nodes trap (S9 for influence_diagram), four-dimension classification (M2), equilibrium method named (M3), players-match-envelope (C1), short_alt (S11 — name players + move type).
    revision_pass: |
      For S11 apply short_alt template. For S7/S8 remove probability from decision-node children; if a player's choice has uncertain outcome, wrap it in a chance node. For S9 merge to exactly one value node. For M2 add literal labels Timing:/Information:/Duration:/Sum: before equilibrium analysis. For M3 name the solution method explicitly. For M5 add at least one Alternative-structure paragraph.
    consolidation_pass: |
      Both streams independently develop equilibria and alternative structures. Reference frame: Depth's equilibrium analysis. Equilibrium-disagreement: emit Depth's preferred equilibrium; surface Breadth's alternative in "Alternative structures" prose. Payoff-disagreement: emit midpoint in spec; declare range in prose; never silently pick. Credibility-disagreement: surface both readings in prose; envelope reflects equilibrium under each credibility assumption with less-credible case in Alternative structures.
    verification_pass: |
      V-SI-1: no revised decision-node edge carries probability. V-SI-2: revised influence_diagram has exactly one value node. V-SI-3: revised prose names an equilibrium method; revised level_2_statistical states the arithmetic. V-SI-4: revised decision-node labels still carry acting-player names.
```

### T11 — Distributional / interest tracing

```yaml
cui-bono:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, produces, requires, contradicts]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Stakeholder-position engrams (the user's vetted views on who benefits and who loses) are weighted above institutional-pattern resources. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Identify the institutional author(s) of the position (becomes source node in flowchart or hierarchy_level 0 concept). Document the stated rationale. Map the actual distributional impact (author → mechanism → beneficiary/loser). Identify the numerical parameters or definitional choices that drive the distributional outcome. Assess whether distributional impact is consistent with stated purpose. Identify which constituencies' interests are served by the specific parameters chosen. Evaluate Breadth's alternative for internal consistency — does it genuinely represent opposite interests?
    breadth_pass: |
      Construct the alternative position that would emerge from the opposite constituency's interests with equal technical sophistication. Identify ≥2 numerical parameters/definitional choices where a different value would produce a materially different distributional outcome. Map the policy landscape if the disadvantaged constituency had authored the standard. Identify the legitimate value the current position serves — separate from the distributional overlay. Assess user gains from this analysis (actionable, informational, diagnostic).
    evaluation_pass: |
      Score against three rubric extensions: Institutional Tracing, Distributional Specificity, Alternative Construction Quality. Prioritise: author-and-beneficiary presence (S10 — envelope must show both), parameter specificity (M2 — ≥2 specific parameters; vague "incentive structure" fails), alternative construction (M3 — not cosmetic, technically sophisticated), FGL symmetry (M4 — applied to ≥2 constituencies), legitimate value (M5 — separate from distributional overlay), structural-not-conspiracy stance, short_alt (S11). Additionally evaluate WPF Escalation Check: if ≥2 wickedness indicators fire, append the WPF escalation prompt.
    revision_pass: |
      For S11 apply short_alt template. For S10 add the institutional author (subgraph "Authors") and beneficiary constituency (subgraph "Beneficiaries"). For M2 replace generic "incentive structure" with ≥2 specific parameters with quantified or described impact. For M3 rewrite alternative design with equal technical rigour to institutional position. For M4 apply Fear/Greed/Laziness labels to both institutional author AND opposing constituency. For M5 add "Legitimate value:" paragraph separating overlay from genuine purpose.
    consolidation_pass: |
      Depth traces author-to-beneficiary flow; Breadth constructs the alternative from opposite constituency. Reference frame: Depth's author-to-beneficiary flowchart (or concept map). Breadth's alternative-constituency mapping is emitted as a separate prose section "Alternative design from opposite constituency" — NOT a second envelope. FGL reconciliation: when streams disagree on motivational attribution, emit both attributions in prose. Legitimate-value preservation: if one stream identified legitimate value separate from distributional overlay, preserve it.
    verification_pass: |
      V-CB-1: revised envelope retains at least one author-labelled element AND one beneficiary-labelled element. V-CB-2: if prose includes "Alternative design:", it has specific parameters with at least equal specificity to the institutional position. V-CB-3: revised prose retains "Legitimate value:" section (or explicit "No legitimate value beyond distributional effects" declaration). V-CB-4: silent upgrade from structural incentive to intent-attribution during revision is a FAIL unless new evidence is explicitly cited.
```

### T12 — Foundational assumption challenge

```yaml
paradigm-suspension:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, qualifies, analogous-to, supersedes]
      deprioritize: [parent, child, precedes]
    provenance_treatment: |
      Engrams articulating an alternative frame override consensus chats that assume the dominant frame. P1/P2 over P3-P6; conflicts surfaced rather than averaged. Frame-suspension needs engram articulations of the frame plus resource-tier evidence of alternatives.
  instructions:
    depth_pass: |
      Identify the foundational assumptions the consensus position depends on. State each as a testable proposition. For each assumption, identify observational evidence for/against, distinguishing observational from interpretive evidence. Identify the strongest version of the consensus case. For each assumption, assess load-bearing vs peripheral. Identify where defenders conflate interpretive with observational evidence. Evaluate Breadth's alternative interpretations for logical coherence and evidential grounding — reject alternatives without observational support as rigorously as consensus claims without it.
    breadth_pass: |
      For each foundational assumption, generate ≥2 alternatives consistent with observational evidence. Map what the domain looks like under each alternative. Identify structural similarities to historical paradigm revisions. For each alternative, identify its strongest feature — the observation it explains most naturally. Assess what value each alternative opens up. Identify what the user gains from examination regardless of outcome.
    evaluation_pass: |
      Score against four rubric extensions: Assumption Identification, Evidence Classification, Alternative Quality, Einstein Guard Rail Compliance. Prose-only — no envelope. Prioritise: no-envelope invariant (S1 — any ora-visual block is mandatory fix), five-section presence (S2), three testable assumptions (S3/M1), observational-interpretive labelling (S4/M2), Einstein guard rail (M5 — observation wins over preferred alternative), two genuine alternatives (M4).
    revision_pass: |
      For S1 remove any ora-visual block; PS is prose-only. For S3/M1 rewrite assumptions as testable propositions ("Assumption N (testable):"). For S4/M2 tag every evidence item as [observational] or [interpretive]; default to [interpretive] when unsure. For M3 add load-bearing/peripheral assessment per assumption. For M4 rewrite alternatives with equal rigour to consensus. For M5 restore observational respect when prose dismisses observation to favour alternative.
    consolidation_pass: |
      Both streams independently surface load-bearing assumptions. Reference frame: union of foundational assumptions surfaced by both streams; both streams' alternative interpretations emitted in the "Alternative interpretations" section (attributed by originator). Einstein guard rail reconciliation: if either stream dismissed an observation to favour an alternative, the dismissal is stripped — observation is non-negotiable. Load-bearing disagreement: if streams disagree on which assumption is load-bearing, emit both classifications in prose.
    verification_pass: |
      V-PS-1: revised response has NO ora-visual fenced block. V-PS-2: revised prose has ≥3 assumptions stated as testable propositions with literal prefix "Assumption N (testable):". V-PS-3: every evidence item in revised prose carries [observational] or [interpretive] tag. V-PS-4: revised prose does not dismiss observation to favour an alternative.
```

### T13 — Steelman

```yaml
steelman-construction:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [supports, extends, qualifies, analogous-to]
      deprioritize: [contradicts, supersedes]
    provenance_treatment: |
      Argument-supporting engrams within the position being steelmanned are weighted highest; counter-arguments are explicitly suppressed within this mode. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Identify the position as originally stated. Identify the strongest evidence supporting it — evidence that would be most difficult for a critic to dismiss. After Breadth completes the steelman, assess whether the construction genuinely strengthens or subtly weakens (tinmanning). Apply the mirror test — would a thoughtful proponent say "I wish I'd thought of putting it that way"? If not, the steelman is insufficient. Identify ≥2 points where the steelmanned version is strongest. Critique only the steelmanned version, never retreating to the weaker original.
    breadth_pass: |
      Reconstruct at logical best. Identify hidden premises that make the argument stronger. Fill gaps with the most charitable inferences. Marshal the best available evidence. Formulate more precisely than proponents have. Identify ≥2 points of agreement between the steelmanned position and the user's own. Identify what is genuinely valuable in the position. Assess what the user gains from the steelman: better understanding of opposition, genuine vulnerabilities in their own position, unexpected common ground. Identify what survives critique.
    evaluation_pass: |
      Score against three rubric extensions: Steelman Fidelity, Mirror Test, Critique Quality. Prose-only — no envelope. Prioritise: no-envelope invariant (S1 — any ora-visual block is mandatory fix), six-section presence (S2), construction-dominance (S3 — original-position paragraph ≤ 1/3 of total steelman section length), mirror test (M1), critique-addresses-steelman-only (M3 — no retreat), fidelity (M5 — same argument strengthened, not replaced).
    revision_pass: |
      For S1 remove any ora-visual block. For S2 add missing section with literal heading. For S3 trim original-position paragraph to ≤ 1/3 of total length. For M1 rewrite steelman until a thoughtful proponent would endorse. For M2 add agreement points until ≥2, each numbered. For M3 rewrite critique to address only steelmanned formulation; if critique doesn't apply to steelman, drop it. For M5 re-anchor to original position's core claim when steelman drifts into a different argument.
    consolidation_pass: |
      Not applicable at default Gear 3 (single-stream). If promoted to Gear 4 (rare — construction and critique are naturally sequential), use Breadth's construction as canonical and Depth's critique as the stress-test; do NOT present both constructions side-by-side, which defeats the mode's purpose (one steelman, not a side-by-side compare).
    verification_pass: |
      V-STM-1: revised response has NO ora-visual fenced block. V-STM-2: all six CONTENT CONTRACT sections present in revised prose. V-STM-3: original-position paragraph still ≤ 1/3 of total steelman section length. V-STM-4: critique section still addresses only the steelmanned version; no retreat to original formulation.
```

### T14 — Adversarial stress-test

```yaml
red-team-assessment:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, undermines, supersedes, requires]
      deprioritize: [supports, extends, analogous-to]
    provenance_treatment: |
      Counter-evidence within a tier is weighted above tier-mates that affirm the consensus; chats and web are excluded by design. P1/P2 over P3-P6; conflicts surfaced rather than averaged. Assessment-stance red-team analysis hunts for vulnerabilities in vetted and curated content for the user's own fix-prioritisation.
  instructions:
    depth_pass: |
      Run Input Sufficiency Protocol; emit redirect if any condition fails (no override). Identify artifact's internal structure (claims, premises, steps, dependencies). Internal-attack hunt for own-decision benefit: hidden assumptions, understated costs, missing stakeholders, internal logical gaps, steps that assume away the hard part. Apply sycophantic-inverse self-check: every vulnerability requires "Why this is real:" grounding in artifact specifics; drop findings without grounding. Tag each vulnerability Severity (Showstopper/Major/Caveat) and Surface (Internal). Pair every vulnerability with an actionable fix recommendation and feasibility note. Open with "Stance: assessment". Pulled-punches (softening real risks to spare the user) is a graver failure than over-attack — the assessment's purpose is honest vulnerability surfacing for fix-prioritisation.
    breadth_pass: |
      Run Input Sufficiency Protocol independently from Depth. Identify artifact's external surface (audiences, environments, adversaries, second-order systems). External-attack hunt: adversarial use cases (Adversary: + Exploit:), failure modes, second-order blowback. Apply same sycophantic-inverse self-check. Mirror Depth's Finding/Severity/Why-this-is-real labels; tag Surface: External; pair every vulnerability with actionable fix recommendation. Maintain Stance: assessment declaration consistent with Depth.
    evaluation_pass: |
      Score against seven rubric extensions: Finding Grounding (CQ1), Severity Calibration (CQ2), Fix-Actionability (CQ3), Fix-Feasibility (CQ4), Attack-Failure Disclosure (CQ5), Framework-vs-Artifact discipline (CQ6), Override-flag presence (CQ7). Prioritise: grounding presence (anti-Nitpick-Trap; missing grounding is Tier A failure), severity floor honesty (declare floor sentence when no Major/Showstopper), fix-actionability per vulnerability, Attack-Failure Disclosure presence, surface coverage (Internal AND External), pulled-punches detection (deflated severity / softened language to spare user). Stance must remain assessment throughout — any advocate-stance shape (audience model, persuasive-force ranking, suggested phrasing) is a routing failure.
    revision_pass: |
      For S1 emit annotated envelope when spatial input present, or remove envelope when prose-only. For S-RT-RP enforce three-part redirect shape (What I see / What's missing / Three options with override). For S10 use dual encoding on every callout. Either ground each vulnerability in artifact specifics or drop; fabricated findings are Tier A failure. Pair every vulnerability with actionable fix recommendation and feasibility note (user-implementable / requires-outside-resources / structural-redesign-needed). Add Attack-Failure Disclosure section with at least one disclosed attack class. Include the literal severity-floor sentence when reached. Remove pulled-punch language wherever it has crept in. Reviser-stage anti-drift rule: a revision that ADDS findings without new evidence is a FAIL.
    consolidation_pass: |
      Depth covers internal attack surface; Breadth covers external. Both produce vulnerabilities tagged by severity and surface; consolidator merges into one unified vulnerability list ranked by severity (worst-first) with paired fix recommendations. When input contains a diagram and custom_annotated_svg is being emitted, use user's spatial_representation as canvas; overlay annotations from BOTH Depth and Breadth onto the same diagram with distinct annotation kinds per surface. Severity reconciliation: when streams disagree on severity for structurally same finding, retain higher severity; note disagreement in prose. Attack-Failure Disclosure preservation: if either stream's Disclosure reports an attack class that found nothing, preserve that disclosure. Stance: assessment maintained throughout. One-envelope-per-turn invariant.
    verification_pass: |
      V-RTA-1: revised response preserves "Stance: assessment" declaration. V-RTA-2: every vulnerability in revised draft retains "Why this is real:" grounding. V-RTA-3: every vulnerability paired with actionable fix recommendation and feasibility note. V-RTA-4: severity-floor declaration preserved verbatim if analyst draft declared it. V-RTA-5: revised draft retains Attack-Failure Disclosure section with at least one disclosed attack-class entry. V-RTA-6: revised draft contains no findings absent from analyst draft UNLESS reviser cites new evidence. V-RTA-7: revised draft's envelope presence/absence matches input shape. V-RTA-8: no advocate-stance shapes (audience model, persuasive-force ranking, suggested phrasing) present.

red-team-advocate:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, undermines, supersedes, requires]
      deprioritize: [supports, extends, analogous-to]
    provenance_treatment: |
      Counter-evidence within a tier is weighted above tier-mates that affirm the consensus; chats and web are excluded by design. P1/P2 over P3-P6; conflicts surfaced rather than averaged. Advocate-stance red-team analysis hunts for high-leverage attacks in vetted and curated content for use against an external audience.
  instructions:
    depth_pass: |
      Run Input Sufficiency Protocol; emit redirect if any condition fails (no override) — the protocol additionally requires audience identifiable for advocate. Identify artifact's internal structure. Identify named external audience and their frame, priorities, and persuasion pathways. Internal-attack hunt for advocate use: hidden assumptions the audience would reject, understated costs the audience cares about, missing stakeholders the audience will notice, internal logical gaps the audience will spot. Apply sycophantic-inverse self-check AND no-fabrication discipline: every attack must rest on what the artifact actually says. Tag each attack Persuasive Force (Devastating/Strong/Plausible) and Surface (Internal). Pair every attack with suggested phrasing in the audience's idiom and "lands hardest with [audience] because…" annotation. Open with "Stance: advocate".
    breadth_pass: |
      Run Input Sufficiency Protocol independently from Depth. Identify artifact's external surface and audience-relevant attack vectors. External-attack hunt: optics + narrative angles + strategic considerations + second-order blowback the audience cares about. Apply same sycophantic-inverse and no-fabrication checks. Mirror Depth's Attack/Persuasive Force/audience-fit labels; tag Surface: External. Surface concessions the advocate must preempt — what the audience will recognise as the artifact's strongest defence.
    evaluation_pass: |
      Score against six rubric extensions: Audience-Model Accuracy (CQ1), Persuasive-Force Calibration (CQ2), No-Fabrication Discipline (CQ3), Framework-vs-Artifact discipline (CQ4), Concession Honesty (CQ5), Override-flag presence (CQ6). Prioritise: no-fabrication (an attack that misrepresents the artifact will collapse on first counter-move from a prepared audience — Tier A failure), persuasive-force calibration (cynical-overreach is the advocate-specific Tier A failure), audience-fit per attack (mirror-imaging avoidance), concession presence (omitted concessions invite ambush). Stance must remain advocate throughout — any assessment-stance shape (severity-ranked vulnerabilities, fix recommendations, fix-feasibility) is a routing failure.
    revision_pass: |
      For S1 emit annotated envelope when spatial input present, or remove envelope when prose-only. For S-RT-RP enforce three-part redirect shape. For S10 use dual encoding on every callout. Drop attacks that rest on fabricated claims (no-fabrication-violation is Tier A regardless of how strong the attack would be if true). Deflate persuasive force from "devastating" to lower wherever cynical-overreach has crept in. Add audience-fit annotation ("lands hardest with [audience] because…") to every attack. Add concessions section preempting the strongest counter-moves the audience would raise. Reviser-stage anti-drift rule: a revision that ADDS attacks without new evidence is a FAIL.
    consolidation_pass: |
      Depth covers internal attack surface for the audience; Breadth covers external. Both produce attacks tagged by persuasive force and surface; consolidator merges into one unified argument brief ranked by persuasive force (worst-for-the-artifact first) with paired suggested phrasing. Audience model reconciliation: streams must agree on audience frame and priorities; disagreement signals an upstream Input Sufficiency failure. Concession reconciliation: union of preempted counter-moves from both streams. Stance: advocate maintained throughout. One-envelope-per-turn invariant.
    verification_pass: |
      V-RTV-1: revised response preserves "Stance: advocate" declaration. V-RTV-2: audience model section present with named audience, frame, priorities, persuasion pathways. V-RTV-3: every attack in revised draft has audience-fit annotation. V-RTV-4: every attack paired with suggested phrasing in the audience's idiom. V-RTV-5: concessions section present with at least one preempted counter-move. V-RTV-6: strategic considerations section present. V-RTV-7: revised draft contains no attacks absent from analyst draft UNLESS reviser cites new evidence. V-RTV-8: no assessment-stance shapes (severity-ranked vulnerabilities, fix recommendations, fix-feasibility) present.
```

### T15 — Dialectical

```yaml
dialectical-analysis:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, qualifies, supports, supersedes]
      deprioritize: [precedes, parent, child]
    provenance_treatment: |
      Engrams articulating the thesis and the antithesis are weighted above resource-tier debate summaries; counter-evidence within tier is surfaced rather than averaged. P1/P2 over P3-P6.
  instructions:
    depth_pass: |
      State the thesis clearly with its claims to completeness (becomes IBIS idea node responding to question). Identify the thesis's internal contradictions (become con nodes objects_to the thesis OR question nodes surfacing the tension). Evaluate whether the antithesis emerges from the thesis's own internal contradictions (genuine) or is external objection (not dialectical). Stress-test the proposed synthesis — does it transcend, not average? Identify whether the synthesis generates new contradictions — it should. Invoke the Adornian escape valve if the synthesis is forced.
    breadth_pass: |
      Develop the antithesis emerging from the thesis's own internal contradictions — not external critique. Argue the antithesis as if believed (genuine adversarial commitment). Identify what the antithesis explains that the thesis cannot. Propose the sublation — genuinely new position transcending the contradiction. Identify the emergent insight. Assess recursion — what contradictions does the sublation itself contain.
    evaluation_pass: |
      Score against three rubric extensions: Antithesis Strength, Sublation Genuineness, Contradiction Identification. Prioritise: IBIS grammar (S9 — validator-rejected), at least 2 idea nodes (S8 — thesis + antithesis minimum; 3 preferred including sublation unless Adornian), at least 1 con node (S10), antithesis emergence (M2 — must emerge from thesis's own internal contradictions), sublation-transcends test (M3 — averaging language fails), short_alt (S11).
    revision_pass: |
      For S11 apply short_alt template. For S9 fix IBIS grammar (idea→responds_to→question; pro→supports→idea; con→objects_to→idea). For S10 add at least one con node representing thesis's internal contradiction. For M2 rewrite antithesis to emerge from thesis's own internal contradictions; argue as if believed. For M3 rewrite sublation to transcend, not average; use literal phrase "transcends by". For M4 if contradiction genuinely cannot be sublated, remove sublation idea node and declare irreducibility ("irreducible contradiction").
    consolidation_pass: |
      Depth + Breadth independently develop thesis/antithesis and candidate sublations. Reference frame: union of question, thesis, antithesis, sublation ideas. Use Depth's thesis framing as reference; Breadth's antithesis with independent adversarial commitment is canonical. Sublation reconciliation: if both streams produce sublations, emit both as peer idea nodes responding to the same question, each with its own pro support; do NOT average. Adornian resolution: if either stream invoked irreducibility, honor it — emit no sublation. Recursion-acknowledgement: at least one sublation's recursion (next-level contradictions) carried forward in prose.
    verification_pass: |
      V-DA-1: every edge in revised envelope passes IBIS grammar. V-DA-2: revised envelope has ≥2 idea nodes (3 if sublation was emitted). V-DA-3: if sublation node exists in revised envelope, it has at least one pro node supporting it. V-DA-4: if prose declares irreducibility, revised envelope has no sublation idea; if envelope has a sublation, prose does not declare irreducibility.
```

### T16 — Synthesis

```yaml
synthesis:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator, reference]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [extends, analogous-to, supports, qualifies, derived-from]
      deprioritize: [precedes, parent, child]
    provenance_treatment: |
      Reference-tier retrievals support cross-document orientation. Engram-tier positions get woven first; resource-tier evidence supports; incubator-tier proposals are flagged as candidate, not concluded. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Map each framework's core claims, structures, and mechanisms (each framework contributes concepts to envelope at hierarchy_level 0; within-framework concepts at levels 1-2). Identify specific structural elements in each framework that may correspond to elements in the other (these become cross-domain cross-linked propositions). Distinguish genuine structural correspondence from surface analogy. Stress-test every proposed connection — does it hold under examination? Identify at minimum one proposed connection that is superficial; explain why it fails. Evaluate whether the synthesis reveals something genuinely new or merely restates what was already known.
    breadth_pass: |
      Look for structural isomorphisms across the frameworks. Generate at minimum three candidate connections, including at least one non-obvious. Explore what the synthesis reveals that neither framework reveals alone. Identify the most productive tension between the frameworks. Assess practical value — new approaches, resolved puzzles, research directions. Note where the synthesis is incomplete.
    evaluation_pass: |
      Score against three rubric extensions: Connection Genuineness, Emergent Insight, Tension Identification. Prioritise: two roots (S7 — both frameworks present as hierarchy_level 0 concepts; single-root maps reduce one framework to a special case of the other), cross-link presence (S10 — without cross-links there is no synthesis), mechanism-not-metaphor (M2 — every cross-link carries prose evidence), tension honesty (M3 — productive tensions have linking phrases), short_alt (S12).
    revision_pass: |
      For S12 apply short_alt template ("Synthesis concept map linking <framework A> and <framework B>"). For S7 add the missing framework as a second hierarchy_level 0 concept. For S10 add at least one proposition with is_cross_link: true with linking phrase "structurally corresponds to" or "is in productive tension with". For M2 add prose evidence of mechanism-level correspondence, or remove the cross-link. For M3 add a "is in productive tension with" linking phrase and emit a cross-link using it; do not resolve the tension.
    consolidation_pass: |
      Depth + Breadth independently produce syntheses — this mode's core signal. Reference frame: union of concepts from both streams; de-duplicate by label. Preserve both frameworks as hierarchy_level 0 peers. Convergent cross-links: when both streams identified the same structural correspondence, mark consolidated proposition with both streams' attribution in prose; emit one is_cross_link: true edge. Divergent cross-links: emit with single-stream attribution; mark "tentative" in prose. Superficial-analogy disputes: if Depth ruled out a connection Breadth proposed, defer to Depth (structural test wins); surface in prose. Neither stream should be flattened into the other — two peer hierarchy_level 0 roots are non-negotiable.
    verification_pass: |
      V-SYN-1: revised envelope has at least two hierarchy_level 0 concepts with distinct framework names. V-SYN-2: revised envelope has ≥1 is_cross_link: true proposition. V-SYN-3: each cross-link in revised envelope has prose evidence of structural correspondence in revised "Structural parallel(s)" section.
```

### T17 — Structural mapping & feedback systems

```yaml
relationship-mapping:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [supports, contradicts, enables, requires, produces, extends]
      deprioritize: []
    provenance_treatment: |
      Engram-tier relationship-graph articulations override inferred relationships in resource or incubator tiers. P1/P2 over P3-P6; conflicts surfaced rather than averaged. Relationship mapping uses the full taxonomy.
  instructions:
    depth_pass: |
      For each proposed connection, assess the type: causal (A causes B), correlational, dependency (A requires B), influential, or structural. Causal connections become directed edges in DAGitty DSL; correlational ones flagged in prose only. For causal connections, assess directionality. Identify missing connections the map should contain. Challenge at minimum two connections — is each genuine or assumed? Identify where the map presents correlation as causation. Assess completeness.
    breadth_pass: |
      Identify all entities relevant to the user's question. For each connection, state the type and directionality. Identify at minimum two non-obvious connections. Identify which relationships are most important (disrupting which would change the most). Surface the organising structure (hub-and-spoke, chain, hierarchy). Note connections to adjacent domains.
    evaluation_pass: |
      Score against four rubric extensions: Relational Precision, Structural Completeness, Map vs Narrative, Acyclicity Integrity. Prioritise: acyclicity (S8/M4 — DAG with cycle is structurally invalid), type-match (S3 — concept_map for heterogeneous; causal_dag for causal framings), causation-correlation distinction (M1 — every connection has a type prefix), cross-link/non-obvious (M2/S7 — ≥2 non-obvious connections marked), short_alt (S10).
    revision_pass: |
      For S10 apply short_alt template. For S7 enforce concept_map floor (concepts ≥4, linking_phrases ≥2, propositions ≥3, ≥1 is_cross_link). For S8 with cycle: either remove one edge with documented rationale, or suppress envelope and propose SD transition. For M1 prefix each connection with Causal:/Correlational:/Dependency:/Influential:/Structural:. For M2 surface at least two non-obvious connections with literal phrase "non-obvious connection".
    consolidation_pass: |
      Not applicable at default Gear 3. If promoted to Gear 4, use Depth stream's acyclicity verdict as authoritative (structure over narrative wins); merge Breadth stream's non-obvious connections into the envelope only if they pass Depth's causation-correlation audit.
    verification_pass: |
      V-RM-1: revised envelope is acyclic. V-RM-2: for causal_dag, revised focal_exposure and focal_outcome both appear as node ids in revised spec.dsl. V-RM-3: every prose connection has a type prefix; revision must not strip these.

systems-dynamics-structural:
  gear: 4
  expected_runtime: ~10min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, produces, requires, contradicts, qualifies]
      deprioritize: [parent, child, supersedes]
    provenance_treatment: |
      Engram-tier loop articulations and stock-and-flow models override partial loop fragments retrieved from chat or incubator. Cross-domain analogies surfaced in resource tier are useful for structural pattern matching but should not import policy claims unmodified. P1/P2 over P3-P6; conflicts surfaced. (T17 entry — structural emphasis: feedback structure as the primary analytical object; pair with relationship-mapping for static-vs-feedback disambiguation.)
  instructions:
    depth_pass: |
      Define system boundary explicitly. Identify stocks (accumulations) and flows (rates of change) where magnitudes and units are known or estimable; if primarily qualitative, stay with a CLD; if there are numbered accumulations with known units, prefer stock_and_flow. Identify all feedback loops and classify each as reinforcing (R) or balancing (B); each loop becomes spec.loops entry. Identify delays — mark delayed edges. Verify each loop is genuinely circular (closing edge exists). Identify at minimum one counterintuitive behaviour. Verify polarity parity (even − edges ⇒ R; odd ⇒ B).
    breadth_pass: |
      Map complete feedback structure with behaviour-grounded loop labels. Identify Senge archetypes (Fixes That Fail, Shifting the Burden, Limits to Growth, Eroding Goals, Escalation, Success to the Successful, Tragedy of the Commons, Growth and Underinvestment) using canonical names. Rank leverage points using Meadows' 12-level hierarchy. Distinguish robust vs fragile interventions. Identify what the user gains from systems-level understanding compared to linear analysis.
    evaluation_pass: |
      Score against four rubric extensions: Feedback Structure, Archetype Recognition, Leverage Point Quality, Polarity Integrity. Prioritise: loop-or-nothing (S9 — empty spec.loops is structurally invalid), polarity parity (S10), loop genuineness (M1 — chain mis-labelled as loop), boundary honesty (M5), archetype-loop fit (M3 — name-drops fail), short_alt (S12 — name dominant loop's behaviour).
    revision_pass: |
      For S12 apply short_alt template. For S9 enforce loop id pattern ^[RB][0-9]+$. For S10 count − edges; even ⇒ R, odd ⇒ B. For M1 verify closing edge exists; if absent, add or remove the loop. For M3 either remove archetype name or add the characteristic loop. For M4 annotate each leverage point with "Depth level N:" per Meadows.
    consolidation_pass: |
      Both streams produce independent CLDs (or S&Fs). Reference frame: Depth's variable set + loop declarations + framework choice. Breadth's archetype identification and Meadows-depth leverage ranking live as dedicated prose sections even when Depth has named the same archetype — preserve attribution. Convergence on loop count + polarity: if both streams declared the same loop with matching type + polarity parity, mark high-confidence in prose. Divergence: do NOT average or pick silently — emit both readings in prose with rationale; drop edge if ambiguity is unresolvable, OR keep Depth's polarity and note Breadth objection. Archetype disagreement: keep both as Candidate archetypes; envelope does not encode archetype choice directly.
    verification_pass: |
      V-SD-1: every loop in revised spec.loops has declared type matching −-edge parity. V-SD-2: archetypes named in revised prose each have a matching loop. V-SD-3: every variable named as loop member in revised prose has matching spec.variables[].id. V-SD-4: variables outside revised prose's declared boundary are absent from revised spec.variables.
```

### T18 — Mechanistic deepening

```yaml
deep-clarification:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, chat, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [supports, extends, derived-from, requires]
      deprioritize: [precedes, parent, child]
    provenance_treatment: |
      Chat-tier retrievals from the current and immediately prior turns are first-class — they're what the user has just said and need to be honoured. P1/P2 over P3-P6; conflicts surfaced rather than averaged. Clarification needs recent conversation context (chat) plus stable user positions (engram); resources rarely apply.
  instructions:
    depth_pass: |
      Start from the user's current level and identify the next mechanism beneath it. For each mechanism provided, identify the next level beneath. Push ≥2 levels deeper. Distinguish established explanations from current-best-understanding (contested or incomplete). Mark the epistemic boundary. Test whether each "deeper" explanation is genuinely deeper (mechanism) or merely more detailed. Identify where depth reaches the limits of current knowledge. Identify ≥1 common misconception arising at the requested depth.
    breadth_pass: |
      Identify analogies or parallel mechanisms in other domains. Identify ≥1 alternative mechanistic explanation. Surface connections to other areas of the user's knowledge. Assess the point at which further depth becomes academic rather than actionable. Identify the most useful depth for the user's likely purposes. Note where deeper understanding changes practical implications.
    evaluation_pass: |
      Score against two rubric extensions: Depth Genuine, Epistemic Boundary. Envelope-optional. Prioritise: envelope-optional handling (S1 — zero envelope acceptable; if present, must be flowchart for procedural mechanisms only), depth floor (M2 — ≥2 levels of mechanism below surface), mechanistic not horizontal (M3 — each deeper level reveals mechanism), epistemic boundary (M4), unnecessary-envelope trap (mandatory fix), short_alt (S5).
    revision_pass: |
      For S3/S5 if flowchart envelope emitted, apply short_alt template ("Flowchart of <mechanism name ≤80 chars>"). For S1 envelope-on-non-procedural: suppress envelope; declare in prose "No visual produced — mechanism is not procedural". For M2 add a second-level mechanism beneath current first-level. For M3 rewrite to reveal cause at level N-1, not enumerate sub-examples at the same level. For M4 add "epistemic boundary:" paragraph distinguishing settled knowledge from current-best-understanding.
    consolidation_pass: |
      Not applicable at default Gear 3. If promoted to Gear 4 for high-stakes mechanistic clarification, use Depth's mechanistic chain as reference frame; Breadth's alternative mechanisms and cross-domain analogies are emitted as separate prose sections. Preserve the epistemic boundary at the lesser depth of the two streams.
    verification_pass: |
      V-DC-1: if revised envelope is present, mechanism is genuinely procedural; silent envelope addition for non-procedural mechanisms during revision is a FAIL. V-DC-2: revised prose retains ≥2 mechanistic levels below surface. V-DC-3: revised prose retains the "epistemic boundary:" declaration.
```

### T19 — Open exploration

```yaml
passion-exploration:
  gear: 2
  expected_runtime: ~1min
  type_filter: [engram, resource, incubator]
  context_budget: conversation_history_soft_ceiling=0.5
  RAG_profile:
    relationship_priorities:
      prioritize: [extends, analogous-to, enables, derived-from]
      deprioritize: [contradicts, supersedes]
    provenance_treatment: |
      User-stated passion engrams are weighted highest; resource-tier surfacing of related passions is suggestive only. P1/P2 over P3-P6; conflicts surfaced. PE runs with a higher conversation history ceiling than most modes — the arc of the wandering is part of the signal.
  instructions:
    depth_pass: |
      Not applicable at Gear 2 (single primary model). If user escalates to Gear 3+: track what territory the exploration has covered; note factual claims that emerged and assess their grounding; flag exciting-but-unsupported connections as "worth investigating further" rather than "established"; assess whether any emerging direction rests on misunderstanding.
    breadth_pass: |
      Follow the user's interests wherever they lead. Offer lateral connections and unexpected angles. When a thread reaches a natural pause, generate at minimum two directions it could go next — one deepening, one crossing domains. Surface connections the user may not see. Identify what is most generative — which threads have the most potential. Name rich insights without trying to close the exploration around them. Monitor for crystallisation signals — a defined deliverable appearing in user's language, scope narrowing, shift from exploratory to directive language. WHEN crystallisation signals appear, reflect them back and offer Project Mode.
    evaluation_pass: |
      Score against three rubric extensions: Exploration Breadth, Generative Quality, Crystallisation Monitoring. Adversarial strictness is RELAXED per config/mode-to-visual.json — Major findings become Minor. Prioritise: envelope-optional (S1 — zero envelope acceptable; mandate envelope only if ≥3 concepts surfaced), three open questions minimum (M1), two next-directions minimum (M2), over-polished-map trap (M4 — surface as SUGGESTED), crystallisation signal handling (M3 — detect and reflect, OR declare absence explicitly), short_alt (S10).
    revision_pass: |
      For S10 apply short_alt template ("Exploration map from <seed thought ≤80 chars>"). For S1 if envelope absent but ≥3 concepts surfaced, emit envelope; if envelope present but <3 concepts, suppress and declare in prose. For M1 add numbered open questions until ≥3. For M2 add at least two next-direction paragraphs (one deepening, one lateral). For M4 mark frontier concepts (those with only one incoming link and no outgoing links) explicitly in prose; keep them as dangling nodes.
    consolidation_pass: |
      Not applicable at default Gear 2 (single-model). If promoted to Gear 4 — rare; passion-exploration at Gear 4 defeats the conversational purpose — merge both streams' concept inventories but preserve the lowest-polish version of the map. Generative breadth outranks analytical tightness in this mode.
    verification_pass: |
      V-PE-1: revised prose has ≥3 numbered open questions. V-PE-2: revised prose has ≥2 numbered next-directions. V-PE-3: if revised envelope is absent, prose says so explicitly; if present, spec.concepts ≥3.
```

### T20 — Project / deliverable production

```yaml
project-mode:
  gear: 4
  expected_runtime: ~5min
  type_filter: [framework, mode, engram]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [requires, enables, produces, precedes]
      deprioritize: [analogous-to, supersedes]
    provenance_treatment: |
      Framework-tier retrievals define the procedure; engram-tier retrievals provide the user's positions on tradeoffs; mode-tier retrievals tell project-mode how to invoke other modes for sub-deliverables. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Project Mode is a dispatch spec. If an analytical mode fits the request, the classifier re-runs and the analytical mode's instructions govern. If Project Mode is terminal (pure document production): identify requirements with literal prefix Requirement N:; produce the deliverable that best satisfies all stated requirements; track decisions with literal prefix Decision N:; evaluate against stated requirements; identify gaps; assess whether assumptions constrain unnecessarily (lightweight paradigm check); identify ≥1 risk or limitation with literal prefix Limitation N:.
    breadth_pass: |
      If terminal, identify alternatives Depth did not consider; assess whether the solution space was artificially constrained; note adjacent opportunities. Identify ≥1 strongest feature with literal prefix "Strength:". Assess usability with literal phrase "usability:" followed by as-is / minor modifications needed / significant rework.
    evaluation_pass: |
      Score against two rubric extensions: Requirement Satisfaction, Deliverable Usability. Prioritise: dispatch check first (if request matches an analytical mode, dispatch — do NOT evaluate under Project Mode), requirement satisfaction (M1), decisions log non-trivial (M2), limitations (M3), scope discipline (M5 — deliverable matches request, not reinterpretation), direct-emission discipline (S2b — if envelope emitted from Project Mode terminal, type must be flowchart/concept_map/pro_con; mode_context == project-mode).
    revision_pass: |
      For dispatch-mismatch: re-classify rather than treating as Project Mode. For S2b: if direct-emission envelope type is wrong, switch to flowchart/concept_map/pro_con or dispatch. For M1: address the unmet requirement OR explicitly acknowledge gap with rationale. For M2: include ≥1 substantive decision with reasoning. For M3: add at least one Limitation N: or Risk N:. For M4: add "lightweight paradigm check:" prefix when flagging unnecessary constraints. For M5: trim deliverable to exactly what was requested; propose additional scope as separate suggestions.
    consolidation_pass: |
      Not applicable at default Gear 3. Project Mode's consolidator behaviour inherits from the dispatched analytical mode when one is active. If Project Mode is terminal and the user forced Gear 4, merge both streams' decisions logs by de-duplicating decision IDs; retain all limitations from both streams.
    verification_pass: |
      V-PM-1: if original classification dispatched to an analytical mode, revised output follows that mode's structural + semantic criteria. V-PM-2: ≥1 substantive decision still in revised prose. V-PM-3: revised deliverable does not expand beyond user's stated requirements without explicit acknowledgement.

structured-output:
  gear: 2
  expected_runtime: ~1min
  type_filter: [framework, mode, engram]
  context_budget: conversation_history_soft_ceiling=0.6
  RAG_profile:
    relationship_priorities:
      prioritize: [parent, child, precedes, requires]
      deprioritize: [contradicts, supersedes]
    provenance_treatment: |
      Framework-tier retrievals govern output shape; engram-tier retrievals govern voice and content priority; resource and incubator are not retrieved by default. P1/P2 over P3-P6; conflicts surfaced rather than averaged. SO runs with a higher conversation history ceiling — the source content is usually in history.
  instructions:
    depth_pass: |
      Not applicable at Gear 2 (passthrough). If Gear 3: verify all source content faithfully represented (no additions, omissions, or reframing); check structural completeness; identify any point where formatting introduced a substantive claim not in the source; identify gaps where the format requires content the source does not provide — flag, do not generate filler.
    breadth_pass: |
      Organise the source content into the requested structure. Apply format conventions. Identify appropriate level of detail for the format (one-pager = compressed; full report = comprehensive). If source does not cleanly fit, propose an adaptation — do not force. Ensure strongest elements are structurally prominent. Assess readability and usability.
    evaluation_pass: |
      Score against three rubric extensions: Fidelity, Format Conformance, Gap Identification. Threshold is HIGHER (≥95% not 90%) because rendering should be reliable. Passthrough mode. Prioritise: fidelity (M1 — no substantive claim in output that was not in source; load-bearing invariant), envelope-byte-equivalence (S2 — passthrough envelopes identical to source), mode_context preservation (S3 — never rewrite to structured-output), gap identification (M3 — flagged, not silently filled), no recommendation added (M4), envelope count match (S1 — if source has N, output has N).
    revision_pass: |
      For S1 envelope-count mismatch: restore source's envelope count. For S2 byte-equivalence: restore byte-equivalent passthrough from source; SO never modifies envelope JSON during rendering. For S3 mode_context: restore source's mode_context; SO preserves source attribution. For M1 fidelity: remove fabricated claim OR attribute as SO-added inference with rationale (rare). For M3 gap: move silently-filled content to Gap report with prefix Gap:. For M4 recommendation: remove; if source contains implicit recommendation, surface as direct quote with attribution.
    consolidation_pass: |
      Not applicable at default Gear 2 (single-model, passthrough). SO is inherently single-pass rendering; parallel consolidation defeats the fidelity invariant. If user forces Gear 3 for high-stakes rendering, use single-stream with adversarial review — NOT parallel streams.
    verification_pass: |
      V-SO-1: every revised passthrough envelope's JSON is byte-equivalent to source. V-SO-2: revised output has same N envelopes as source. V-SO-3: every revised passthrough envelope's mode_context is the source's, not structured-output. V-SO-4: every substantive claim in revised output traces to source.
```

### T21 — Spatial reasoning

```yaml
spatial-reasoning:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, contains, precedes, parent, requires]
      deprioritize: [supersedes, contradicts]
    provenance_treatment: |
      User-drawn spatial representations (in prior_spatial_representation and the current turn's spatial_representation) outweigh retrieved spatial content. Engrams provide vocabulary; the visual is the primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Extract entities, relationships, clusters, and hierarchy from the spatial input. Record positions, types, labels. Flag ambiguous elements (a line that might be a relationship or a boundary, a cluster that might be intentional or accidental) rather than resolving them. Apply Tversky's correspondence audit as diagnostic questions: are proximities meaningful? Does vertical position track importance or abstraction? Are there unconnected proximities suggesting implicit relationships? Do boundaries correspond to coherent categories? Perform gap analysis — missing nodes implied by structure, missing connections implied by proximity or by logic of existing connections, missing hierarchical levels, missing feedback loops, boundary problems. For each proposed gap, verify it is genuine and not template pattern-matching. Assess whether proposed additions respect the user's spatial arrangement.
    breadth_pass: |
      Identify known structural patterns in the arrangement — hub-and-spoke, chain, cycle, star, cluster bridge, orphan — and state what each pattern typically implies for the domain. Generate fog-clearing questions that help the user articulate what the spatial arrangement is encoding. Questions should be open ("Is there a relationship you're sensing but haven't named yet?") rather than leading. Propose refinements as annotations overlaid on the user's original, never as replacements. Identify the single most consequential gap. Identify structural crystallization signals — points where the spatial input is becoming specific enough to warrant transition to an answer-seeking analytical mode. Frame findings so the user can evaluate them against their own intuition.
    evaluation_pass: |
      Score against three rubric extensions: Structural Fidelity, Gap Genuineness, Fog-Clearing Quality. Prioritise: canvas_action == "annotate" (never replace or update — user's spatial arrangement is sacred), target_id values resolving to user-supplied entity ids, kind ∈ {callout, highlight} (arrow/badge deferred), one annotation per finding, callout text ≤60 characters, no rearrangement of user's diagram (Rearrangement Trap), no template projection (Template Projection Trap), no gap fabrication (every gap cites specific spatial or domain evidence).
    revision_pass: |
      Phase 2 will author this during template migration; the source mode-file does not have an explicit reviser-guidance section keyed by criterion. Expected to enforce: target_id values resolve to user-supplied entity ids; canvas_action remains "annotate"; gaps cite specific spatial or domain evidence; fog-clearing questions remain open (not leading); no replacement of user arrangement.
    consolidation_pass: |
      Phase 2 will author this during template migration; the source mode-file does not have an explicit consolidator-guidance section. Expected behaviour: when both Depth and Breadth produce annotations, overlay onto the same user diagram with shared target_ids; preserve the user's spatial arrangement; do not produce "cleaner" rearranged versions.
    verification_pass: |
      Phase 2 will author this during template migration; the source mode-file does not have explicit Universal V1-V8-style verifier checks. Expected baseline: target_id values still resolve; canvas_action remains "annotate"; preserved user arrangement; no silent rearrangement during revision.
```

---

## Phase 4 Wave 1 — New-Architecture Entries

*Per the 2026-05-01 architecture lock and the new 21-territory analytical schema (`Reference — Analytical Territories.md`). Territory section names below follow the new schema (T5 = Hypothesis Evaluation; T6 = Future Exploration; T7 = Risk and Failure Analysis; T8 = Stakeholder Conflict; T14 = Orientation in Unfamiliar Territory; T15 = Artifact Evaluation by Stance). These T-numbers refer to the new analytical-territories schema and are distinct from the older T-numbering in the sections above.*

### T5 (new schema) — Hypothesis Evaluation

```yaml
differential-diagnosis:
  gear: 4
  expected_runtime: ~1min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, supports, qualifies, rules-out]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier evidence statements that bear directly on the candidate hypotheses are weighted above resource-tier domain background; incubator-tier observations enter as evidence to be weighed rather than as ranking authority. Diagnosticity (rules-out power) outweighs consistency (mere compatibility). P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Take the candidate hypotheses and the observed evidence as given; for each hypothesis assess diagnosticity in disconfirming-power language ("this evidence rules out H2 because H2 predicted X and we observed not-X") rather than consistency language alone. Distinguish hypotheses that make different predictions from hypotheses that re-describe the same underlying explanation; merge or differentiate as appropriate. Identify at least one disconfirming test for each top candidate. Flag rare-but-serious "zebra" candidates the common-case framing might eclipse.
    breadth_pass: |
      Survey the full candidate space before narrowing: established common-case explanations, rare-but-serious candidates, candidates from adjacent domains (a symptom in domain A may be a different explanation in domain B), candidates that combine mechanisms (H1 AND H3 jointly), and the null hypothesis (the situation is benign and self-resolving). Document candidates considered and rejected with one-line reason for rejection even when the final ranking surfaces only the top two-or-three.
    evaluation_pass: |
      Score against the four critical questions: hypothesis distinctness (CQ1), diagnosticity vs. consistency (CQ2), actionable disconfirmer for top two (CQ3), evidence-base honesty (CQ4). Named failure modes (hypothesis-collapse, confirmation-anchoring, no-actionable-disconfirmer, false-confidence, missing-zebra) are the evaluation checklist. Mandate fix when ranking is produced without diagnosticity assessment, when confidence is inflated relative to evidence base, or when no disconfirming test is offered.
    revision_pass: |
      Merge collapsed hypotheses or differentiate them by predicting where their predictions diverge. Upgrade consistency-language to diagnosticity-language. Add a disconfirming test where top candidates lack one. Resist revising toward a single-explanation summary when evidence supports multiple candidates equally; preserve honest residual uncertainty in the ranking.
    consolidation_pass: |
      Not applicable at this mode's tier (light, single-pass). If promoted to Gear 4 for high-stakes adjudication, route to competing-hypotheses (full ACH) instead — Differential Diagnosis is the lighter sibling and consolidation is its escalation target, not its native operation.
    verification_pass: |
      V-DD-1: at least two distinct candidate hypotheses present. V-DD-2: diagnosticity stated in disconfirming-power language for at least the top two candidates. V-DD-3: at least one disconfirming test emitted per top candidate. V-DD-4: confidence per ranking explicitly addresses evidence sufficiency rather than asserting unjustified certainty.
```

### T6 (new schema) — Future Exploration

```yaml
pre-mortem-action:
  gear: 4
  expected_runtime: ~1min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, prevents, requires, contradicts]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier failure narratives from comparable plans weighted above resource-tier generic project-management references. Incubator-tier observations about this specific plan enter as load-bearing primary evidence. Klein-pre-mortem lens content (the prospective-hindsight protocol) is treated as method-foundational. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Adopt prospective-hindsight stance throughout: write as though the failure has already occurred ("the plan failed because...") rather than as forward conditional ("this might fail if..."). Bind the failure narrative to this specific plan's mechanism — name the decision point or assumption that broke, trace the causal pathway from breakage to visible failure, and identify the leading indicator the team could observe pre-failure. Avoid generic project-failure tropes (scope creep, communication breakdown) that would apply to any plan.
    breadth_pass: |
      Survey the full failure-mode landscape across five classes: execution failures (the team didn't do what the plan called for), assumption failures (a load-bearing premise was wrong), context-shift failures (the world changed during execution), interaction failures (the plan succeeded narrowly but produced consequences that defeated the larger purpose), and motivational failures (the team disengaged before completion). Narrow to the two-to-three most plausible failure narratives for the prospective-hindsight pass; document the others as residual surfaced-not-narrated.
    evaluation_pass: |
      Score against the four critical questions: stance integrity (CQ1), plan-specific vs. generic (CQ2), leading indicators present (CQ3), pre-commitment vs. post-hoc mitigations (CQ4). Named failure modes (stance-slippage, generic-failure-trope, lagging-indicator-only, post-hoc-conflation, optimism-residue) are the evaluation checklist. Mandate fix when language slips into forward-conditional, when failures are domain-agnostic clichés, when leading indicators are missing, or when mitigations are post-hoc workarounds.
    revision_pass: |
      Restore prospective-hindsight stance where the draft has slipped into forward conditional. Replace generic failure tropes with plan-specific mechanisms tied to named decision points. Add leading indicators where failures only become visible at post-mortem. Resist revising toward optimism — softening failure narratives toward "manageable risks" violates the mode's adversarial-future stance and is a failure mode, not a polish.
    consolidation_pass: |
      Not applicable at this mode's default tier (light, single-pass). If promoted to Gear 4 for parallel multi-stream adversarial-future analysis, retain past-tense narrative voice across streams; merge failure-mode inventories across the five classes; preserve attribution where streams disagree on the most plausible failure pathway.
    verification_pass: |
      V-PMA-1: failure narrative is in past-tense prospective-hindsight stance throughout (no forward-conditional language). V-PMA-2: every named failure mode has plan-specific mechanism tied to a decision point or assumption. V-PMA-3: every failure mode has at least one leading indicator the team could observe pre-failure. V-PMA-4: every mitigation is a pre-commitment action; no post-hoc remediations recommended as mitigations.
```

### T7 (new schema) — Risk and Failure Analysis

```yaml
pre-mortem-fragility:
  gear: 4
  expected_runtime: ~1min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, prevents, requires, contradicts, depends-on]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier breakage narratives from comparable structures weighted above resource-tier generic systems-engineering references. Incubator-tier observations about this specific design's components and interfaces enter as load-bearing primary evidence. Klein-pre-mortem lens supplies the prospective-hindsight protocol; Taleb-fragile lens (when invoked) supplies asymmetry framing. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Adopt prospective-hindsight stance on the structure: write as though the breakage has already occurred ("the system broke when load exceeded X because component Y could not...") rather than forward conditional ("this might fail under load"). Bind fragility narratives to specific components, interfaces, dependencies, or accumulated state — name what yielded under what load condition. Distinguish structural mitigations (component replacement, interface hardening, dependency removal, state-bound enforcement) from operational workarounds (better monitoring, more careful operators).
    breadth_pass: |
      Survey the full structural-fragility landscape across five classes: load fragilities (structure breaks under unusual but specifiable load), dependency fragilities (a component depends on a fragile-or-absent counterpart), interface fragilities (the joint between components is the failure surface), state fragilities (structure breaks when accumulated state crosses a threshold), and emergent fragilities (a failure mode that no single component shows). Narrow to the two-to-three most plausible breakage narratives for the prospective-hindsight pass.
    evaluation_pass: |
      Score against the four critical questions: stance integrity (CQ1), structure-specific vs. generic fragility (CQ2), load pathway with mechanism (CQ3), structural vs. operational mitigations (CQ4). Named failure modes (stance-slippage, generic-fragility-trope, mechanism-gap, structure-operation-conflation, actor-modeling-drift) are the evaluation checklist. Mandate fix when narrative drifts into adversarial-actor framing (escalate to red-team if appropriate); mandate when mitigations are operational rather than structural.
    revision_pass: |
      Restore prospective-hindsight stance where the draft slips to forward conditional. Replace generic fragility patterns (single point of failure, cascading failure) with structure-specific mechanisms tied to named components or interfaces. Add load pathways where breakage appears without mechanism. Resist revising toward operational fixes — recommending "more careful monitoring" instead of structural change collapses fragility into operation. If the analysis is really about an adversarial actor, escalate to red-team rather than revise toward neutrality.
    consolidation_pass: |
      Not applicable at default tier (light, single-pass). If promoted to Gear 4 for high-stakes structural-fragility adjudication, retain past-tense voice across streams; merge fragility inventories across the five classes; preserve attribution where streams disagree on which structural element is most load-bearing.
    verification_pass: |
      V-PMF-1: breakage narrative is in past-tense prospective-hindsight stance throughout. V-PMF-2: every named fragility has a structure-specific mechanism (no generic tropes); component, interface, or dependency named explicitly. V-PMF-3: every fragility has at least one leading indicator observable pre-failure. V-PMF-4: every mitigation is a structural change; no operational workarounds recommended as mitigations. V-PMF-5: no narrative is actually about an adversarial actor (escalate to red-team if so).
```

### T8 (new schema) — Stakeholder Conflict

```yaml
stakeholder-mapping:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [opposes, allies-with, depends-on, brokers, represents]
      deprioritize: [analogous-to, supersedes]
    provenance_treatment: |
      Engram-tier articulations of party stakes and historical relationships are weighted above resource-tier generic stakeholder-analysis references. Incubator-tier observations about this specific situation's parties enter as primary evidence. Bryson power-interest grid and Mitchell-Agle-Wood salience are method-foundational; Ulrich CSH lens (when invoked) surfaces absent parties. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Articulate each party's stake at the level of concrete interests (what they want, what they could lose, what their best alternative is if this goes against them) rather than at the level of role-labels alone. Surface internal heterogeneity — large stakeholder groups are rarely monolithic. Apply Mitchell-Agle-Wood salience on all three dimensions (power × legitimacy × urgency) so a high-power-low-legitimacy party isn't conflated with a high-legitimacy-low-power party.
    breadth_pass: |
      Deliberately scan for parties outside the user's initial frame: parties affected but not represented, parties with informal influence not visible on org charts, parties whose voices are filtered through intermediaries, parties from adjacent domains who become stakeholders if the situation shifts, future parties whose interests will be created by the action under consideration, and silent parties whose absence is itself a stake. Surface relationships among parties (allies, opposition, dependencies, brokers).
    evaluation_pass: |
      Score against the four critical questions: frame-bounded inventory (CQ1), role-as-stake (CQ2), single-axis salience (CQ3), silent power mirroring (CQ4). Named failure modes (frame-bounded-inventory, role-as-stake, single-axis-salience, silent-power-mirroring, laundry-list-flatness) are the evaluation checklist. Mandate fix when inventory stays inside the user's frame, when salience is plotted on power alone, when relationships among parties are absent, or when no marginalized-but-legitimate party appears.
    revision_pass: |
      Expand inventory where draft has stayed inside the user's frame. Articulate stakes as concrete interests where draft has named only roles. Populate Mitchell-Agle-Wood salience on all three dimensions where only power is plotted. Surface absent parties where map has silently mirrored existing power asymmetries. Resist revising toward a tidier diagram if tidiness drops low-salience-but-legitimate parties; the long tail of the inventory is where the mode's value lives.
    consolidation_pass: |
      At Gear 4, both parallel streams produce stakeholder inventories independently; merge by union with explicit deduplication; for parties named by only one stream, preserve attribution and inspect for frame-bias (one stream may have surfaced a party the other missed). Mitchell-Agle-Wood salience values are reconciled by surfacing disagreement (one stream marked party X as definitive, the other as dormant) rather than averaging; disagreement is information.
    verification_pass: |
      V-SM-1: inventory contains at least one party from outside the user's initial frame OR explicitly notes that no such party was identifiable. V-SM-2: every party has a stake articulated as concrete interest, not role-label. V-SM-3: Mitchell-Agle-Wood salience populated on all three dimensions for every party. V-SM-4: at least one absent or marginalized party named OR explicit absence-noted. V-SM-5: relationships among parties stated rather than left implicit.
```

### T14 (new schema) — Orientation in Unfamiliar Territory

```yaml
quick-orientation:
  gear: 4
  expected_runtime: ~1min
  type_filter: [engram, resource, incubator, reference]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [parent, child, defines, contains]
      deprioritize: [contradicts, supersedes]
    provenance_treatment: |
      Reference-tier vault navigation and document registries are first-class for orientation. Engram-tier positions about the domain take precedence over speculation. Settled facts and accepted frameworks at engram tier outweigh contested positions; contested positions are flagged rather than presented as settled. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Honor honest depth restraint — orientation must give the user a usable map without exceeding the tier-1 time budget. Name three-to-five major sub-areas, the foundational distinction(s) that organize the domain, and the entry-point concepts a newcomer should learn first. A thin pass that says "this domain is broad and complex" fails by giving the user nothing actionable; a thick pass that exceeds budget fails by violating contract. Test depth: does the user, having read this, know where to look next?
    breadth_pass: |
      Deliberately scan across the full domain landscape before narrowing: include the established core, the live frontier, the dissenting traditions, and the adjacent domains that share vocabulary. Even when only three sub-areas are surfaced, ensure they are spread across the domain rather than concentrated in one corner. Survey common newcomer misconceptions and flag the most predictable ones.
    evaluation_pass: |
      Score against the four critical questions: corner bias (CQ1), decorative distinction (CQ2), misconception blindness (CQ3), scope creep (CQ4). Named failure modes (corner-bias, decorative-distinction, misconception-blindness, scope-creep, contested-as-settled) are the evaluation checklist. Mandate fix when sub-areas are concentrated in one corner, when foundational distinctions are decorative rather than load-bearing, when common misconceptions are missing, or when output exceeds tier-1 depth budget.
    revision_pass: |
      Broaden coverage where draft has stayed in one corner. Drop decorative distinctions and replace with load-bearing ones. Add common misconceptions where section is empty or too obscure. Resist revising toward depth — if situation actually warrants tier-2, escalate to terrain-mapping rather than over-deliver here. Resist presenting contested points as settled.
    consolidation_pass: |
      Not applicable at default tier (light, single-pass). If user explicitly requests Gear 4 for multi-domain orientation, route to terrain-mapping (heavier sibling) rather than expanding Quick Orientation beyond its budget contract.
    verification_pass: |
      V-QO-1: one-line domain definition present. V-QO-2: three-to-five major sub-areas listed and spread across domain rather than corner-concentrated. V-QO-3: foundational distinctions are load-bearing. V-QO-4: entry points are concrete first-concepts or first-questions. V-QO-5: common misconceptions flagged. V-QO-6: settled vs. contested distinguished. V-QO-7: output stays within tier-1 depth budget.
```

### T15 (new schema) — Artifact Evaluation by Stance

```yaml
balanced-critique:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [supports, qualifies, contradicts, enables, prevents]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier evaluative positions on comparable artifacts are weighted above resource-tier generic evaluation frameworks. Incubator-tier observations about this artifact's specific features enter as primary evidence. Symmetric weighting between supportive and critical engrams is enforced — the mode's neutrality requires that strengths-evidence and weaknesses-evidence are treated with comparable provenance discipline. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Cite the specific element of the artifact that constitutes each strength or weakness rather than asserting evaluations from analyst preference. Name the conditions under which each strength would fail to hold or each weakness would not bite — strengths and weaknesses are conditional on assumptions whose alteration would shift the assessment. Surface assumptions explicitly. Test depth by asking: could the user trace each strength/weakness claim back to a specific feature of the artifact?
    breadth_pass: |
      Deliberately scan across stakeholder perspectives — what looks like a strength from the user's vantage may be a weakness from another's; what looks settled may be contested. Surface perspective-dependent findings and flag them as such rather than asserting universal evaluations. Scan adjacent considerations (comparable alternatives, opportunity costs, downstream consequences) as inputs to the assessment even when they are not the primary focus.
    evaluation_pass: |
      Score against the four critical questions: symmetric rigor on strengths and weaknesses (CQ1), perspective-dependent findings flagged (CQ2), residual tensions named in net assessment (CQ3), evidence-backed claims rather than analyst opinion (CQ4). Named failure modes (stance-tilt, false-universality, premature-resolution, opinion-as-evaluation, bothsidesism) are the evaluation checklist. Mandate fix when strengths and weaknesses sections are asymmetric in length or specificity, when universal claims are made about perspective-dependent findings, when net assessment collapses residual tensions, or when claims are unbacked by artifact-specific evidence.
    revision_pass: |
      Restore symmetric rigor where draft has tilted toward advocacy or teardown. Flag perspective-dependent findings where universal claims were made. Surface residual tensions where net assessment collapsed them. Resist revising toward an artificial 50/50 balance when the artifact is genuinely strong or weak — neutrality is in evaluative method, not in forced symmetry of conclusions. Resist revising toward a single-verdict ending; net assessment is allowed to be qualified.
    consolidation_pass: |
      At Gear 4, both parallel streams produce strengths-and-weaknesses inventories independently; merge by union with explicit deduplication; preserve stream-of-origin attribution where streams disagree on whether a feature is a strength or a weakness — disagreement is itself a perspective-dependent finding. Net assessments from the two streams are reconciled by surfacing residual disagreement rather than averaging.
    verification_pass: |
      V-BC-1: strengths and weaknesses sections are comparable in length, specificity, and evidence depth. V-BC-2: every strength and weakness tied to a specific element of the artifact. V-BC-3: perspective-dependent findings flagged with stakeholder vantage. V-BC-4: residual tensions named explicitly in net assessment. V-BC-5: analysis is not artificially balanced when artifact is genuinely asymmetric in quality.
```

---

## Phase 4 Wave 2 — New-Architecture Entries

*Per the 2026-05-01 Wave 2 build. Territory section names below follow the new 21-territory analytical schema (`Reference — Analytical Territories.md`). Entries are alphabetical by `mode_id` within each territory; territories are presented in numeric order T1, T2, T3, T6, T9, T10, T13, T19.*

### T1 (new schema) — Argumentative Artifact Examination

```yaml
coherence-audit:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, qualifies, supports, requires]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the focal claim and its supporting structure are weighted above resource-tier generic argumentation references. Walton/Toulmin/Hamblin/pragma-dialectics method-foundational lens content is treated as method bedrock. Incubator-tier observations about the specific artifact enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Perform charitable reconstruction first — surface implicit premises (enthymemes), resolve textual ambiguity in the speaker's favor, and identify the strongest version of the argument actually present in the text before flagging any fallacy. Decompose every inferential move into Toulmin elements (claim, data, warrant, backing, qualifier, rebuttal) so warrants are visible and examinable. For each named fallacy, cite the specific quoted text, identify the inferential move that fails, name the principle violated, and state why the move fails here (not just in the abstract). Push beyond the named-fallacy taxonomy to surface unnamed structural failures (premise smuggling, scope shift, definitional drift, unstated load-bearing assumption, enthymeme failure). Test depth by asking: would a defender of the argument recognize the audit as auditing the argument they actually made?
    breadth_pass: |
      Scan across the three traditions of fallacy theory before narrowing — Walton's pragmatic/dialectical theory (fallacy depends on dialogue type: persuasion, inquiry, negotiation, deliberation, information-seeking, eristic), pragma-dialectics (fallacies as violations of rules for critical discussion), Hintikka's question-dialogue (fallacies as illegitimate moves in question-answer games). Survey the formal vs. informal fallacy taxonomy cleavage and the informal-fallacy families (relevance / presumption / ambiguity / rhetorical-strategic). Apply the dialogue-type lens (Walton) to the dialectical context the artifact is participating in. Breadth markers: at least the formal/informal/structural cleavages have been surveyed and dialogue-type considered.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) charitable reconstruction performed first; (CQ2) Toulmin warrants surfaced per inferential move; (CQ3) fallacy claims substantiated with quoted text + violated principle + reason-it-fails-here; (CQ4) argument-wrong vs. conclusion-wrong separated; (CQ5) unnamed structural failures examined. Named failure modes (uncharitable-reconstruction, warrant-blindness, name-without-structure, argument-conclusion-conflation, named-fallacy-only-reading, asymmetric-rigor) are the evaluation checklist. Mandate fix when reconstruction is omitted, when warrants are not surfaced, when fallacies are name-dropped without substantiation, when argument-soundness slides into conclusion-truth, or when severity grading is uneven across the artifact in unjustified ways.
    revision_pass: |
      Perform charitable reconstruction first where the draft has flagged fallacies in surface text without surfacing implicit premises. Surface Toulmin warrants where the draft examines premises-and-conclusion without the warrant in view. Substantiate any fallacy claim with quoted text, inferential move, violated principle, and reason-it-fails-here. Separate argument-soundness from conclusion-truth where the draft slides between them. Add the structural-failure sweep where the audit operates only against the named-fallacy list. Resist revising toward decisive verdicts on the conclusion's truth — the mode is conclusion-agnostic by design.
    consolidation_pass: |
      At Gear 4, both parallel streams produce reconstructions and audits independently. Reference frame: the union of inferential moves identified by both streams; cite stream-of-origin where streams disagree on which moves are load-bearing. Convergent fallacy claims (both streams identified the same failure with matching quoted text) get high-confidence flag in prose. Divergent claims surface in prose with attribution; do not average. Preserve charitable reconstructions from whichever stream pushed deeper.
    verification_pass: |
      V-CA-1: charitable reconstruction precedes any fallacy claim in revised prose. V-CA-2: Toulmin warrants are surfaced per inferential move. V-CA-3: every named fallacy carries quoted text + violated principle + reason-it-fails-here. V-CA-4: argument-wrong is explicitly separated from conclusion-wrong. V-CA-5: structural-failure sweep produced at least one finding OR explicit "no unnamed structural failures identified" declaration. V-CA-6: severity grading is symmetric across the artifact OR asymmetry justified by mode-structure differences.

frame-audit:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [qualifies, contradicts, enables, supports]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier framing analyses of comparable artifacts are weighted above resource-tier generic frame-theory references. Lakoff/Goffman/Entman/CDA method-foundational lens content is treated as method bedrock. Incubator-tier observations about the artifact's specific framing choices enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Name the operative frame(s) in alternative-comparable vocabulary, not in the artifact's naturalized terms, so that comparison with alternative frames becomes thinkable. Apply Entman's four functions (problem definition, causal interpretation, moral evaluation, treatment recommendation) per frame, with quoted evidence. Inventory selection and salience explicitly — both what the artifact includes/emphasizes and what it excludes/downplays — given that frames work as much by silence as by assertion. Catalogue the linguistic mechanisms by which the frame travels: Lakoff metaphor activations (source-domain → target-domain mapping with inferential entailments), CDA presuppositions, nominalizations, passivizations, lexicalization choices. Construct at least one counterframe to test whether the operative frame is doing analytical work or just describing the topic.
    breadth_pass: |
      Scan all seven framing-tradition layers before narrowing — cognitive linguistic (Lakoff lexical activation/metaphor), sociological (Goffman primary frameworks/keyings/fabrications), media studies (Entman selection/salience/four functions; Gitlin institutional routinization; Tuchman news-net), CDA (Fairclough/van Dijk/Wodak presupposition/nominalization/ideological square/intertextuality), propaganda analysis (Bernays/Ellul/Herman-Chomsky/Stanley), political communication (Iyengar episodic/thematic; Chong-Druckman emphasis/equivalence), social-movement framing (Snow-Benford diagnostic/prognostic/motivational). Breadth markers: at least four of these layers surveyed before producing findings.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) frame named in alternative-comparable vocabulary; (CQ2) Entman four functions populated per frame; (CQ3) selection AND silence both catalogued; (CQ4) lexical and grammatical mechanisms inventoried with quoted text; (CQ5) counterframe constructed. Named failure modes (frame-naturalization, function-collapse, silence-blindness, macro-frame-only-reading, counterframe-omission, stance-slippage-into-attack) are the evaluation checklist. Mandate fix when the frame is restated in the artifact's own terms, when functions are collapsed, when silence is uncatalogued, when mechanisms are absent, or when the audit slides from frame-surfacing into frame-rejection.
    revision_pass: |
      Extract the frame to alternative-comparable vocabulary where the draft has restated the artifact's framing in its own terms. Populate Entman's four functions per frame where the frame has been named without showing its work. Add the silence inventory where selection-and-salience reads only inclusions. Add lexical-grammatical mechanisms with quoted text where the draft operates only at the macro-frame level. Construct the counterframe where it is missing. Resist revising toward attack on the frame — the mode is stance-suspending; rejecting the frame belongs in propaganda-audit (if propaganda is suspected) or in red-team (if the artifact is being evaluated as a proposal).
    consolidation_pass: |
      At Gear 4, both parallel streams independently surface operative frames and counterframes. Reference frame: union of operative frames identified by both streams (de-duplicated by characterization stem); preserve attribution where streams identified different counterframes. Convergent metaphor-inventory entries (both streams cited the same metaphor with matching quoted text) get high-confidence flag in prose. Divergent function-population in Entman's four-function grid surfaces in prose; do not average across streams. Stance-suspending posture is preserved across both streams.
    verification_pass: |
      V-FA-1: operative frames are named in alternative-comparable vocabulary, not in the artifact's own terms. V-FA-2: Entman's four functions are populated per frame with quoted evidence. V-FA-3: selection-and-silence inventory has entries in BOTH columns (or explicit "no salient silence identified" declaration). V-FA-4: lexical and grammatical mechanisms cited with quoted text. V-FA-5: at least one counterframe is constructed. V-FA-6: the audit has not slipped from frame-surfacing into frame-rejection (no advocacy for an alternative frame; no condemnation of the operative frame).

propaganda-audit:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, qualifies, undermines, enables]
      deprioritize: [analogous-to, parent, child, supports]
    provenance_treatment: |
      Engram-tier propaganda diagnostics on comparable artifacts are weighted above resource-tier generic rhetoric references. Stanley supporting/undermining distinction and the Walton schemes are method-foundational. Bernays/Ellul/Herman-Chomsky lens content (when invoked) supplies structural-institutional context. Incubator-tier observations about the artifact's specific persuasive structure enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Name the professed ideal of the artifact (the freedom / fairness / security / truth it claims to embody) explicitly with quoted text, before assessing supporting/undermining classification. Hypothesize the actual function from the artifact's structure and predicted audience uptake. Apply Stanley's supporting (non-rational means for worthy ideal) vs. undermining (presents-as-embodying-ideal-while-eroding-it) distinction with evidence. If undermining, identify the specific flawed-ideology premise(s) the audience must hold for the contradiction between professed and actual to remain invisible to them. Catalogue not-at-issue content (presuppositions, conventional implicatures, lexical activations) with quoted text — propaganda often operates through what is assumed rather than asserted. Distinguish propaganda diagnosis from refutation of the artifact's conclusion (the propaganda-charge fallacy).
    breadth_pass: |
      Scan the propaganda-tradition layers before narrowing — Bernays (engineering-of-consent / PR-as-symbolic-environment-management), Ellul (integration vs. agitation; ambient cumulative narrowing), Herman & Chomsky (five-filter propaganda model — ownership, advertising, official sources, flak, common-enemy), Stanley (supporting/undermining; flawed-ideology precondition; not-at-issue content). Where applicable, scan also Lakoff (lexical metaphor activation), CDA (presupposition/nominalization/agent deletion), Iyengar (episodic vs. thematic for attribution manipulation). Breadth markers: Stanley diagnostic plus at least one structural-context layer (Bernays/Ellul/Herman-Chomsky) plus at least one linguistic-mechanism layer (Lakoff/CDA) before findings.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) professed ideal named with quoted text; (CQ2) supporting/undermining classification evidenced; (CQ3) flawed-ideology premises identified if undermining; (CQ4) not-at-issue content inventoried; (CQ5) propaganda diagnosis distinguished from conclusion-rejection. Named failure modes (ideal-omission, classification-collapse, flawed-ideology-omission, at-issue-only-reading, propaganda-charge-as-refutation, motive-attribution-without-evidence) are the evaluation checklist. Mandate fix when ideal is unnamed, when supporting/undermining is collapsed, when flawed-ideology is missing on undermining classification, when only at-issue content is examined, when diagnosis is treated as refutation, or when motive is attributed without textual or contextual evidence.
    revision_pass: |
      Name the professed ideal explicitly where the draft has assessed propaganda function without surfacing it. Disambiguate supporting from undermining where the draft asserts "propaganda" without distinguishing the two structures. Identify flawed-ideology premises where the draft classifies as undermining without saying what the audience must believe. Catalogue not-at-issue content where the audit has examined only what is asserted. Separate the propaganda diagnosis from any claim that the artifact's conclusion is false. Resist revising toward neutrality — the mode is adversarial-stance by design (Debate D5); softening the diagnostic to be evenhanded is a failure mode, not a polish.
    consolidation_pass: |
      At Gear 4, both parallel streams produce propaganda diagnostics independently. Reference frame: union of identified flawed-ideology premises and not-at-issue content (de-duplicated by stem); preserve attribution where streams disagree on supporting vs. undermining classification. Convergent classification (both streams reached the same supporting/undermining verdict with matching evidence) gets high-confidence flag in prose. Divergent classification surfaces in prose with both streams' evidence; do not average. Five-filter structural situating from either stream is preserved when applicable.
    verification_pass: |
      V-PA-1: professed ideal is named with quoted text. V-PA-2: supporting/undermining classification is evidenced (not asserted). V-PA-3: if classification is undermining, flawed-ideology premises are identified explicitly. V-PA-4: not-at-issue content inventory cites quoted presuppositions or implicatures. V-PA-5: five filters applied if the artifact is mass-media OR explicit "five-filter not applicable" declaration. V-PA-6: propaganda diagnosis is distinguished from any claim about the truth of the artifact's conclusion. V-PA-7: motive attribution carries textual/contextual evidence OR is absent.
```

### T2 (new schema) — Interest and Power Analysis

```yaml
boundary-critique:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [excludes, contradicts, qualifies, requires, enables]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of system-boundary judgments and affected-but-not-involved parties are weighted above resource-tier generic systems-thinking references. Ulrich CSH twelve-category framework is method-foundational. Habermas/Midgley lens content (when invoked) supplies legitimacy-discourse and intervention-design context. Incubator-tier observations about the specific system's exclusions enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Surface boundary judgments as judgments — contestable choices made by someone for some purpose — rather than as natural givens of the system. Distinguish those involved in the system's design and benefit from those affected by but not involved in it (Ulrich's core asymmetry). Audit each of Ulrich's twelve boundary categories systematically: motivation (client / purpose / measure-of-improvement), control (decision-maker / resources / decision-environment), knowledge (expert / expertise / guarantor), legitimacy (witness / emancipation / worldview). For each category, name who currently provides the source and on whose behalf, then identify affected-but-not-involved parties whose perspective is being treated as outside the analysis. Construct the *ought* counterpart that would obtain if affected parties were included.
    breadth_pass: |
      Survey the full Ulrich category-cluster space (all twelve categories across motivation/control/knowledge/legitimacy) and consider boundary frames from adjacent traditions where they bear — Habermasian discourse-ethics (legitimacy as outcome of inclusive deliberation), Midgley's systemic intervention (boundary judgments as intervention sites), Mackenzie's situated knowledges (worldview-category considerations). Survey adjacent affected-party candidates: not only the most obvious excluded parties but also those whose voices are filtered through intermediaries, future parties whose interests will be created, and silent parties whose absence is itself a stake. Breadth markers: all four category-clusters visited; affected-but-not-involved parties sought across all four (not only the obvious ones); worldview category treated with care because it surfaces the deepest boundary judgments.
    evaluation_pass: |
      Score against the four critical questions: (CQ1) boundaries surfaced as judgments not naturalized; (CQ2) involved/affected distinction maintained; (CQ3) all four category-clusters audited; (CQ4) is-vs-ought comparison performed. Named failure modes (boundary-naturalization, involved-affected-collapse, selective-categories, ought-omission, critique-without-purpose) are the evaluation checklist. Mandate fix when boundaries are described in system-spec definitional language, when involved and affected are merged, when only one or two clusters are audited without justification, when the *ought* counterpart is missing, or when the critique provides no actionable implication for the system or decision.
    revision_pass: |
      Denaturalize boundary judgments where the draft treated them as system-given. Restore the involved/affected distinction where the draft collapsed it. Complete the four category-clusters where the draft selected only some. Add the *ought* counterpart where the draft only diagnosed the *is*. Resist revising toward neutrality — the mode's analytical character is critical, and a passing artifact retains the critical edge. If the user wanted neutral analysis, escalate sideways to cui-bono rather than soften.
    consolidation_pass: |
      At Gear 4, both parallel streams produce boundary critiques independently. Reference frame: union of affected-but-not-involved parties identified by both streams (de-duplicated by stake-stem); preserve stream-of-origin attribution where streams differ on which boundary category is most load-bearing. Convergent identification (both streams flagged the same affected-but-not-involved party in the same category) gets high-confidence flag in prose. Divergent *ought*-counterpart proposals surface as alternatives in prose; do not average. The critical-stance posture is preserved across both streams.
    verification_pass: |
      V-BCT-1: the system under critique is named explicitly. V-BCT-2: boundary judgments currently embedded are surfaced as judgments (not as system-givens). V-BCT-3: all four of Ulrich's category-clusters (motivation, control, knowledge, legitimacy) are audited (or any skipped cluster carries explicit justification). V-BCT-4: affected-but-not-involved parties are identified per category. V-BCT-5: the is-vs-ought boundary comparison is performed. V-BCT-6: at least one actionable implication for the system, decision, or design follows from the critique.
```

### T3 (new schema) — Decision-Making Under Uncertainty

```yaml
multi-criteria-decision:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [enables, requires, contradicts, qualifies, prevents]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the user's actual preferences and weighting priorities are weighted above resource-tier generic MCDM references. MCDM-methods lens content (AHP, SMART, ELECTRE, TOPSIS) is method-foundational. Incubator-tier observations about option-specific scoring data enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Name the MCDM method explicitly (additive SMART, AHP pairwise, ELECTRE outranking, TOPSIS distance-from-ideal, etc.) and explain why it fits the decision shape. Surface weights with elicited rationale, not analyst-imposed defaults — equal weights are themselves a preference choice, not a neutral baseline. Identify dominance relations to prune the option set: dominated options (beaten by another option on every criterion) should be flagged; dominant options (beating all others on every criterion) are no-brainer choices that may obviate further analysis. Run sensitivity analysis on both weights and scores, including at least one joint perturbation. Flag where the ranking is robust vs. fragile — the analysis should be able to tell the decision-maker which weight or score perturbation would flip the top choice.
    breadth_pass: |
      Survey the criteria space for under-named dimensions (the criterion the decision-maker would notice they cared about only if it were missing) across at least three categories — outcome-quality, cost, risk, fit, reversibility. Scan for criterion redundancy (two criteria measuring the same underlying attribute under different names; flag when criteria score highly correlated across options). Sanity-check the option set for completeness before scoring — would option-set expansion change the analysis? Consider hybrid options or sequencing alternatives the user has not named.
    evaluation_pass: |
      Score against the four critical questions: (CQ1) criterion independence; (CQ2) weight elicitation rather than imposition; (CQ3) sensitivity analysis surfacing robustness; (CQ4) dominance pruning. Named failure modes (criterion-redundancy, weight-imposition, false-stability, dominance-blindness, aggregation-method-opacity) are the evaluation checklist. Mandate fix when weights are stated without rationale, when sensitivity is empty or single-perturbation only, when dominance relations are absent, or when the aggregation method is unnamed.
    revision_pass: |
      Add weight rationale where the draft presents weights without elicitation. Add sensitivity analysis where the draft presents the ranking as stable. Prune dominated options and flag dominant ones rather than presenting a flat ranking. Resist revising toward false consensus — if criteria genuinely conflict, the artifact's job is to surface the tradeoff, not to manufacture a clear winner. If the ranking is method-fragile (small perturbations flip the top choice), say so explicitly.
    consolidation_pass: |
      At Gear 4, both parallel streams independently produce scoring matrices and rankings. Reference frame: union of options and criteria identified by both streams (de-duplicated by attribute-stem); preserve attribution where streams elicit different weights. Convergent dominance findings (both streams identified the same dominated option) get high-confidence flag in prose. Divergent rankings surface in prose with both streams' weights and scoring rationale; do not silently average — disagreement is information about ranking fragility.
    verification_pass: |
      V-MCD-1: criteria are named and defined operationally. V-MCD-2: weights are elicited or explicitly noted as analyst-imposed (with reason). V-MCD-3: aggregation method is named and explained. V-MCD-4: scoring is explicit per option per criterion. V-MCD-5: sensitivity analysis runs at least one joint weight-score perturbation. V-MCD-6: dominance relations are surfaced (or explicit "no dominance relations among options" declaration).
```

### T6 (new schema) — Future Exploration

```yaml
probabilistic-forecasting:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [predicts, enables, contradicts, qualifies, requires]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier base-rate articulations and reference-class precedents are weighted above resource-tier generic forecasting references. Tetlock superforecasting lens content is method-foundational. Knightian risk/uncertainty/ambiguity lens (when invoked) supplies the boundary distinction. Incubator-tier observations about the specific question's drivers enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Lock the resolution criteria operationally — the forecast question must specify how the analyst would know, in concrete observable terms, whether the forecast resolved yes or no by some date. Select an explicit reference class and state its base rate with citation or reasoning. Name the inside-view drivers that distinguish this case from the reference class. Show the math of the inside-vs-outside-view adjustment (e.g., "base rate 15%, inside-view drivers shift estimate up by ~10–20pp, final 25–35%"). Produce a probability range whose width reflects the analyst's actual confidence rather than a default fermization. Test depth by asking: could a reader reproduce the estimate from the artifact, including directional and magnitude adjustments from base rate?
    breadth_pass: |
      Survey multiple candidate reference classes before locking one (or explicitly weight across several), naming at least two candidates and explaining the choice. Scan for inside-view drivers in multiple categories — mechanism, motivation, capacity, environment, base-rate-defying factors. Surface leading indicators that would prompt revision of the estimate. Breadth markers: at least two candidate reference classes named with rationale; inside-view drivers surveyed across at least three driver categories; leading indicators identified with thresholds.
    evaluation_pass: |
      Score against the four critical questions: (CQ1) operational resolvability; (CQ2) explicit reference class with stated base rate; (CQ3) inside-vs-outside-view separation with shown adjustment; (CQ4) range rather than false-precision point. Named failure modes (unresolvable-question, base-rate-neglect, view-collapse, false-precision, anchor-bias) are the evaluation checklist. Mandate fix when resolution criteria are vague, when no reference class or base rate is named, when views are collapsed, when the probability is asserted as a single point, or when the final estimate is suspiciously close to the first-mentioned base rate.
    revision_pass: |
      Add explicit base-rate citation where the draft asserts "common" or "rare" without a number. Widen the probability range where the draft has anchored on false precision. Surface inside-view drivers individually rather than aggregating into a vague "case-specific factors" mention. Resist revising toward narrative — the mode's analytical character is probability-output. If the user wants narrative, escalate sideways to scenario-planning rather than diluting this mode's contract.
    consolidation_pass: |
      At Gear 4, both parallel streams produce probability estimates independently. Reference frame: union of candidate reference classes and inside-view drivers (de-duplicated by stem); preserve attribution where streams selected different primary reference classes. Convergent base-rate citations (both streams cited the same reference-class base rate) get high-confidence flag in prose. Divergent final ranges surface as a wider combined range in prose with each stream's reasoning preserved; do not silently average estimates that disagree on direction.
    verification_pass: |
      V-PF-1: resolution criteria are operational and locked. V-PF-2: reference class is named with base-rate number. V-PF-3: inside-view drivers and outside-view base rate are separately stated. V-PF-4: the final probability is a range whose construction can be reproduced from the artifact. V-PF-5: leading indicators are named with thresholds. V-PF-6: confidence-in-estimate accompanies the probability range and distinguishes calibration confidence from point confidence.
```

### T9 (new schema) — Paradigm and Assumption Examination

```yaml
frame-comparison:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, qualifies, analogous-to, contrasts-with]
      deprioritize: [parent, child, supersedes]
    provenance_treatment: |
      Engram-tier articulations of each frame's commitments and metaphors are weighted above resource-tier generic frame-theory references. Lakoff conceptual-metaphor lens content is method-foundational. Schön-Rein/Snow-Benford lens content (when invoked) supplies policy-frame and movement-frame context. Symmetric weighting between frames is enforced — the mode's symmetry requires that each frame's source material is treated with comparable provenance discipline. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Articulate each frame on its own terms with steelman discipline within each frame, so neither receives fuller articulation than the others. Descend from stated positions to the conceptual metaphors and moral commitments that structure them — surface the core metaphor each frame deploys (e.g., nation-as-family with strict father vs. nurturant parent; market-as-natural-system vs. market-as-human-construction; disease-as-invader vs. disease-as-imbalance), name the moral commitments the metaphor entails, articulate what each frame makes visible and what it obscures. Honor residual irreducibility where translation distorts — do not collapse a frame's commitment into the other's vocabulary when the translation loses meaning.
    breadth_pass: |
      Survey the frame typologies that might apply (Lakoff family-based moral frames, Schön-Rein policy frames, collective-action frames, narrative frames, frame-of-justice variants), considering whether the named frames exhaust the live alternatives or whether unnamed third or fourth perspectives are also in play. Scan for hybrid or emerging frames that don't fit either pole cleanly. Breadth markers: at least three frame-typology candidates considered before locking the comparison axis; the possibility of frames-not-yet-named is acknowledged.
    evaluation_pass: |
      Score against the four critical questions: (CQ1) symmetric articulation per frame; (CQ2) descent to conceptual metaphor; (CQ3) blind-spot surfacing per frame; (CQ4) honored irreducibility. Named failure modes (asymmetric-articulation, surface-position-only, blind-spot-omission, false-translation, typology-imposition) are the evaluation checklist. Mandate fix when one frame's section is substantially longer/more nuanced than the others', when frames are described only at the level of stated positions, when blind-spots are absent or applied only to non-preferred frames, or when cross-frame translation is presented as smooth where irreducibility is more honest.
    revision_pass: |
      Balance asymmetric articulation where one frame received fuller treatment. Descend to conceptual metaphor where the draft stayed at stated positions. Add blind-spot surfacing per frame where the draft presented frames as if blind-spot-free. Resist revising toward synthesis — the mode's analytical character is comparing, not integrating. If integration is wanted, escalate to T12 synthesis rather than collapsing irreducibility within this mode.
    consolidation_pass: |
      At Gear 4, both parallel streams articulate frames independently. Reference frame: union of core metaphors identified by both streams per frame; preserve attribution where streams identified different blind-spots. Convergent metaphor-identification (both streams cited the same core metaphor for a frame) gets high-confidence flag in prose. Divergent moral-commitment readings surface in prose with attribution; do not average. The descriptive (not synthesizing) posture is preserved across both streams.
    verification_pass: |
      V-FC-1: each frame is articulated symmetrically (length, specificity, charity comparable across frames). V-FC-2: core conceptual metaphors per frame are surfaced. V-FC-3: moral/value commitments per frame are named. V-FC-4: what-each-frame-makes-visible AND what-it-obscures are both populated per frame. V-FC-5: cross-frame translation difficulty is acknowledged. V-FC-6: residual irreducibility is honored where present.
```

### T10 (new schema) — Conceptual Clarification

```yaml
conceptual-engineering:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [requires, enables, contradicts, qualifies, supersedes]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of current concept usage and identified function-failures are weighted above resource-tier generic philosophy-of-language references. Cappelen-Plunkett conceptual-engineering lens content is method-foundational. Haslanger ameliorative-analysis and Gallie essentially-contested-concepts lenses (when invoked) supply socially-loaded and contested-concept context. Incubator-tier observations about specific usage problems enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Map current usage descriptively before any ameliorative move, so the revision is responsive to actual usage rather than to a strawman. Identify specific function-failures of the current concept (where it fails to perform or performs in distorting ways) with concrete examples. Articulate the ameliorative purpose as a function the revised concept should serve, not as a desired conclusion that smuggles in stipulation (avoid "the concept should classify X as Y"; prefer "the concept should help us distinguish operations of class A from class B"). Propose candidate revisions with rationale. Acknowledge the implementation problem (per Cappelen 2018) — the gap between proposing a revision and actually getting communities to adopt it — rather than treating proposal as adoption. Surface revision costs: what current uses, distinctions, or commitments would be lost or displaced.
    breadth_pass: |
      Survey the conceptual landscape around the target — adjacent concepts that would shift under the revision, alternative engineering moves the same problem might admit, prior engineering attempts (successful or failed) that bear on the proposal, normative frameworks that motivate or resist the revision. Breadth markers: at least two candidate revisions surfaced; at least one alternative ameliorative purpose considered; the revision's relationship to neighboring concepts mapped.
    evaluation_pass: |
      Score against the four critical questions: (CQ1) function-articulated purpose, not stipulation-smuggle; (CQ2) descriptive baseline before ameliorative move; (CQ3) implementation problem acknowledged; (CQ4) revision costs surfaced. Named failure modes (stipulation-smuggle, baseline-skip, implementation-blindness, cost-blindness, ameliorative-overreach) are the evaluation checklist. Mandate fix when ameliorative purpose is conclusion-shaped rather than function-shaped, when the descriptive baseline is absent or thin, when the implementation gap is silently assumed away, when current usage is dismissed without analysis, or when an essentially-contested concept is treated as resolvable.
    revision_pass: |
      Recast stipulative purpose as functional purpose. Add descriptive baseline where the engineering move proceeds without grounding. Add implementation acknowledgment where the proposal treats proposal-as-adoption. Add cost surfacing where current usage is dismissed without analysis. Resist revising toward false confidence — conceptual engineering is hard, and a passing artifact admits the difficulty rather than concealing it.
    consolidation_pass: |
      At Gear 4, both parallel streams produce engineering proposals independently. Reference frame: union of identified function-failures and candidate revisions (de-duplicated by stem); preserve attribution where streams proposed different ameliorative purposes. Convergent function-failure identification (both streams flagged the same usage problem) gets high-confidence flag in prose. Divergent candidate revisions surface as alternatives in prose; do not silently choose. The implementation-problem acknowledgment from the more cautious stream is preserved.
    verification_pass: |
      V-CE-1: target concept is named explicitly. V-CE-2: current usage baseline is mapped before the ameliorative move. V-CE-3: function failures are itemized with concrete examples. V-CE-4: ameliorative purpose is function-shaped (not conclusion-shaped). V-CE-5: at least one candidate revision is proposed with rationale. V-CE-6: implementation problem is acknowledged. V-CE-7: revision costs are surfaced.
```

### T13 (new schema) — Negotiation and Conflict Resolution

```yaml
interest-mapping:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [requires, enables, opposes, allies-with, depends-on]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of party stakes and historical negotiation patterns are weighted above resource-tier generic negotiation references. Fisher-Ury principled-negotiation lens content is method-foundational. Voss tactical-empathy and Lewicki distributive-frameworks lenses (when invoked) supply adversarial and high-stakes context. Incubator-tier observations about specific party positions enter as primary evidence. Symmetric weighting between parties is enforced — the mode's neutrality requires that each party's source material is treated with comparable provenance discipline. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Maintain the Fisher-Ury distinction between positions (what each party is asking for) and interests (what each party actually needs). Descend from each party's stated position to the underlying need it serves — substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship. Distinguish inferred-interests-as-hypotheses from confirmed-interests; flag inferences as hypotheses to test in the negotiation rather than asserting them as known facts. Surface both shared-and-compatible interests (integrative-move candidates) and genuinely-opposed interests (where distributive bargaining or value-based difference remains). Test depth by asking: could the analysis tell the user which inferred interest, if confirmed, would unlock an integrative move, and which inferred interest, if disconfirmed, would require pivoting?
    breadth_pass: |
      Survey the interest categories per party (substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship), considering interests not visible from each party's own stated position (interests they may not have articulated to themselves), and noting cultural or contextual factors that shape which interests are surfaceable in the negotiation. Breadth markers: at least three interest-category candidates considered per party; the possibility of unstated or unconscious interests acknowledged.
    evaluation_pass: |
      Score against the three critical questions: (CQ1) position-vs-interest distinction maintained; (CQ2) inferred vs. confirmed flagged; (CQ3) shared and opposed both surfaced. Named failure modes (position-interest-collapse, inference-as-fact, integrative-overreach-or-zero-sum-default, cultural-context-flatness) are the evaluation checklist. Mandate fix when inferred interests track stated positions too closely (analyst restated rather than descended), when inferences are presented without hypothesis-flagging, or when the negotiation is presented as either fully integrative or fully zero-sum.
    revision_pass: |
      Descend from positions to interests where the draft restated positions in interest-language. Flag inferred interests as hypotheses where the draft asserted them as facts. Surface both compatible and opposed interests where the draft defaulted to one or the other. Resist revising toward optimism — the mode's analytical character is descriptive of the interest landscape, including its genuinely-opposed regions. Manufactured integrative possibility is a failure mode, not a polish.
    consolidation_pass: |
      At Gear 4, both parallel streams independently infer underlying interests. Reference frame: union of inferred interests per party (de-duplicated by need-stem); preserve attribution where streams inferred different underlying needs. Convergent inferences (both streams identified the same underlying interest from the same stated position) get high-confidence flag in prose. Divergent inferences surface in prose with both streams' reasoning preserved; do not silently choose. Both shared-and-opposed regions identified by either stream are preserved in the consolidated mapping.
    verification_pass: |
      V-IM-1: parties and stated positions are named. V-IM-2: inferred underlying interests are itemized per party. V-IM-3: every inferred interest carries hypothesis-flagging (not asserted as confirmed). V-IM-4: shared/compatible interests AND genuinely-opposed interests are separately surfaced. V-IM-5: at least one candidate integrative move is named with its supporting interest-pattern. V-IM-6: flagged unknowns are listed as testable in negotiation.
```

### T19 (new schema) — Spatial Composition

```yaml
compositional-dynamics:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contains, supports, contradicts, qualifies, requires]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier perceptual-reading vocabulary and prior compositional analyses on comparable inputs are weighted above resource-tier generic art-criticism references. Gestalt grouping principles and Arnheim compositional-forces are method-foundational. Itten/Albers/Hambidge lens content (when invoked) supplies color-contrast, color-field-interaction, and proportional-vocabulary context. The user-supplied spatial composition is the primary evidence; prior readings inform vocabulary but do not override the present composition's structure. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Predict the perceptual parse explicitly — groupings via proximity / similarity / common fate / good continuation / closure / symmetry / parallelism / common region / connectedness; figure-ground assignment with border-ownership assessment. Identify the structural skeleton (axes, center, frame) and verify cropping-robustness. Assign visual weights to elements on empirical grounds (size, contrast, color, isolation, position, depth) — not on symbolic-meaning grounds. Name force vectors and dynamic tensions; verify displacement-robustness (would small displacements alter the reading substantively? — if not, the force-story is decorative). Classify the dynamic equilibrium (stable / unstable / directional). Predict an eye-path through the fixation sequence. Surface ambiguity-loci where the parse is unstable (figure-ground reversal candidates, contested borders, weight-distribution alternatives).
    breadth_pass: |
      Scan across the two integrated traditions before narrowing — Gestalt grouping and figure-ground (Wertheimer / Köhler / Koffka founding work; Wagemans 2012 century-of-gestalt review; Rubin 1921 figure-ground; border-ownership neurons per Zhou-Friedman-von der Heydt 2000) and Arnheim compositional forces (Art and Visual Perception; The Power of the Center; Dynamics of Architectural Form; McManus-Stöver-Kim 2011 partial empirical support). Where applicable scan also Itten (seven color contrasts), Albers (color's absolute relativity, figure-ground reversal via color), Hambidge (proportional vocabulary, weak empirical warrant — treat as tool not warrant), cinematic mise-en-scène for film stills. Breadth markers: both gestalt parsing AND Arnheim forces have been applied (the M2+M3 integration); color/proportion lenses applied where relevant.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) cue-swap robustness for groupings; (CQ2) border-ownership assignment for figure-ground; (CQ3) displacement-test for force vectors; (CQ4) cropping-robustness for skeleton; (CQ5) empirical defensibility of visual-weight assignments. Named failure modes (cue-fragile-grouping, contested-border-asserted-as-stable, post-hoc-force-story, imposed-skeleton, symbolic-weight-confusion, void-blindness) are the evaluation checklist. Mandate fix when groupings depend on a single cue, when figure-ground is asserted stable for contested borders, when force vectors are decorative, when the skeleton fails cropping, or when visual-weight is attributed on symbolic rather than empirical grounds. Sideways-flag (not mandate) when the operative work is being done by held-open void (escalate to ma-reading).
    revision_pass: |
      Perform the cue-swap test where the draft proposes brittle groupings. Acknowledge contested borders where the draft asserts stable figure-ground. Perform the displacement test where force vectors are decorative. Perform the cropping test where the skeleton may be the analyst's imposition. Substitute empirical visual-weight grounds where the draft attributes weight on symbolic-meaning grounds. Sideways-route to ma-reading where the operative work is being done by held-open void. Resist revising toward purely formal description without predicted consequence — the mode is descriptive of perceptual *dynamics*; a static catalogue of elements without parse-predictions and force-predictions is a thin pass, not the medium-depth reading the mode targets.
    consolidation_pass: |
      At Gear 4, both parallel streams produce perceptual parses and force-readings independently. Reference frame: union of identified groupings and force vectors (de-duplicated by element-and-cue stem); preserve attribution where streams identified different figure-ground assignments. Convergent grouping-identification with the same cue gets high-confidence flag in prose. Divergent figure-ground readings surface as ambiguity-loci with both streams' interpretations preserved; do not silently choose — figure-ground reversal candidates are themselves a finding. Cross-reference to T19 territory-level open debates (especially Debate 3 on aesthetic-vs-analytical scope and Debate 5 on AI implementability) is noted where the reading depends on the descriptive-analytical commitment.
    verification_pass: |
      V-CD-1: groupings survive the cue-swap test (or are flagged as cue-fragile). V-CD-2: figure-ground assignment carries border-ownership assessment. V-CD-3: force vectors survive the displacement test. V-CD-4: structural skeleton survives the cropping test. V-CD-5: visual-weight assignments are on empirical grounds (size, contrast, color, isolation, position, depth). V-CD-6: ambiguity-loci are surfaced (or explicit "no ambiguity-loci identified" declaration). V-CD-7: dynamic equilibrium is classified.

ma-reading:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contains, qualifies, contradicts, requires, supports]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of operative voids and prior contemplative readings on comparable compositions are weighted above resource-tier generic Japanese-aesthetics references. Japanese-aesthetics-catalog lens content (Ma + Yūgen + Wabi-sabi + Mu) is method-foundational. Cage / Bordwell / Schrader / Tanizaki lens content (when invoked) supplies musical-temporal, cinematic, slow-cinema, and shadow-as-material context. The user-supplied spatial composition is the primary evidence; tradition vocabulary informs the reading but does not override the composition's specific operative voids. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Identify operative voids/intervals (not all empty space; only the empty space that is load-bearing). Name what each void *does* in vocabulary the tradition supplies — rhythm, breath, suggestion, ma-ai, kami-space, narrative caesura, perceptual rest, gravel-as-ma, intermediate-space, transcendental-style duration, shadow-as-material. Perform the removal/alteration test per void: would replacing the void with content of equal compositional weight alter the work substantively? If not, the void is incidental and the mode does not apply (sideways to compositional-dynamics). Trace suggestion-resonances — what each void invites the viewer/listener to complete (yūgen depth-direction, wabi-sabi temporal-weathering, mu generative-reservoir). Test depth by asking: would a practitioner of the relevant tradition (a tea master, a nō actor, a slow-cinema director) recognize the reading as articulating something present in the work?
    breadth_pass: |
      Scan across the four Japanese-aesthetic operations before narrowing — Ma (the void/interval as primary content; placement-spacing rather than place; Isozaki/Nitschke/Itō); Yūgen (suggestion / withholding / depth-direction; Zeami; Suzuki's "cloudy impenetrability... not utter darkness"); Wabi-sabi (impermanence / asymmetry / shadow-as-material; Tanizaki's *In Praise of Shadows*); Mu (emptiness as generative reservoir; Suzuki / Okakura's "vacuum is all-potent because all-containing"). Where applicable scan also Cage's framing-of-attention silence, Ozu's pillow shots, Tarkovsky's sculpting in time, Sesshū's unpainted space. Breadth markers: the reading has surveyed which of the four operations are active in the composition (often one is primary, one or two subsidiary, rarely all four) before narrowing.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) load-bearing vs. incidental void; (CQ2) active vs. passive void; (CQ3) removal/alteration test performed; (CQ4) productive incompleteness vs. under-specification (yūgen test); (CQ5) defeasibility (counter-readings present). Named failure modes (incidental-void-mistaken-for-ma, passive-void-asserted-as-active, removal-test-failure, under-specification-mistaken-for-yūgen, inviolable-reading, tradition-misappropriation) are the evaluation checklist. Mandate fix when negative space is treated as load-bearing without removal-test, when the void's effect is described without showing it is held-open as content, when under-developed work is mistaken for yūgen withholding, when the reading is asserted as inviolable without falsifiability conditions, or when Ma/Yūgen/Wabi-sabi/Mu vocabulary is invoked on a composition without engagement with those traditions.
    revision_pass: |
      Perform the removal test where the draft asserts a void's load-bearing status without showing what would collapse without it. Distinguish active (held-open) from passive (residual) voids where the draft conflates them. Substitute under-specification readings where the draft attributes yūgen to a work that is merely under-developed. Add counter-readings where the analysis asserts inviolability. Specify the tradition's role explicitly where the analysis invokes Ma/Yūgen/Wabi-sabi/Mu vocabulary on works without engagement with those traditions. Resist revising toward analytical-distancing — the mode is contemplative-descriptive-deep by design (T19 reanalysis M1); the analysis participates in articulating the experience while remaining defeasible.
    consolidation_pass: |
      At Gear 4, both parallel streams produce ma-readings independently. Reference frame: union of operative voids identified by both streams (de-duplicated by void-position stem); preserve attribution where streams named different tradition operations as primary (Ma vs. Yūgen vs. Wabi-sabi vs. Mu). Convergent void-identification with matching tradition-vocabulary gets high-confidence flag in prose. Divergent counter-readings from each stream are preserved as alternatives — defeasibility is structural to the mode, and multiple defensible counter-readings strengthen rather than weaken the artifact. Cross-reference to T19 territory-level open debates (especially Debate 3 on Western-analytical vs. Eastern-experiential epistemic warrants and Debate 4 on AI implementability of perceptual operations) is noted where the reading depends on the contemplative-stance commitment.
    verification_pass: |
      V-MR-1: operative voids are identified (not all empty space). V-MR-2: what each void does is named in tradition-specific vocabulary. V-MR-3: the removal/alteration test is performed per void. V-MR-4: suggestion-resonances are traced per void. V-MR-5: at least one counter-reading is offered per major claim OR explicit falsifiability conditions stated. V-MR-6: the analysis has not slid into inviolable assertion. V-MR-7: tradition vocabulary is grounded in the composition's actual engagement with the tradition (no misappropriation).
```

---

## Phase 4 Wave 3 — New-Architecture Entries

*Per the 2026-05-01 Wave 3 build. Territory section names below follow the new 21-territory analytical schema (`Reference — Analytical Territories.md`). Entries are alphabetical by `mode_id` within each territory; territories are presented in numeric order T4, T7, T13, T16, T17, T19.*

### T4 (new schema) — Causal Investigation

```yaml
causal-dag:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [causes, enables, requires, contradicts, qualifies]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the causal question and named confounders are weighted above resource-tier generic causal-inference references. Pearl causal-graphs and do-calculus content are method-foundational. Bennett-Checkel process-tracing-tests lens content (when invoked) supplies historical-event-evidence context. Knightian risk/uncertainty/ambiguity lens (when invoked) supplies the assumption-fragility boundary. Incubator-tier observations about specific variables and observed associations enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Lock the causal question at a specific Pearl ladder rung — observation (seeing), intervention (doing, via the do-operator), or counterfactual (imagining what would have been) — and use the operators appropriate to that rung. Inventory all candidate variables (cause, effect, confounder, mediator, collider, instrument) with explicit role classification. Construct the DAG with absent-arrow assumptions enumerated explicitly: every excluded arrow is a structural assumption that should be flagged for fragility. Apply the back-door criterion (or front-door, or do-calculus rules) to determine whether the causal effect is identifiable from the assumed graph. Avoid conditioning on collider variables (which would induce spurious dependence). Answer the intervention or counterfactual query in the language proper to its rung — do not slide observational language into interventional answers. Test depth by asking: could a reader reproduce the identifiability verdict from the artifact, including which arrows were assumed absent and why?
    breadth_pass: |
      Scan for plausible confounders the analyst might miss (selection effects, reverse-causation candidates, time-varying confounders, latent variables). Consider alternative DAG structures consistent with the same observations and surface the identifiability boundary — under which assumption violations would the conclusion fail. Breadth markers: at least one alternative DAG that observational data could not distinguish from the chosen one is named, and at least one intervention or natural experiment that would discriminate is identified. Where structure exhibits feedback loops, sideways-flag for transition to systems-dynamics-causal (DAG cannot represent cycles).
    evaluation_pass: |
      Score against the five critical questions: (CQ1) Pearl-rung lock; (CQ2) confounder enumeration; (CQ3) identifiability verdict via back-door or front-door criterion; (CQ4) collider variables correctly classified (no conditioning that induces spurious dependence); (CQ5) structural assumptions made explicit with most fragile flagged. Named failure modes (rung-confusion, hidden-confounder, non-identifiability-elision, collider-conditioning, implicit-assumption, cycle-violation) are the evaluation checklist. Mandate fix when observational language answers an interventional question, when the DAG omits a plausible common cause without explicit no-confounding assumption, when the final causal claim is made without checking the back-door or front-door criterion, when the analysis conditions on a collider, or when the structural assumptions are presented without enumerating which arrows were excluded and why. Escalate when feedback loops appear (mode-boundary violation).
    revision_pass: |
      Add omitted confounders where the draft assumes no-confounding without justification. Make absent-arrow assumptions explicit where the DAG presents a structure without saying what was excluded. Demote a causal claim to an associational claim when identifiability fails; do not strengthen conclusions beyond what the graph supports. Re-classify variables where role assignments are wrong (especially colliders). Rewrite intervention/counterfactual answers in the language proper to their rung where they slide between rungs. Resist revising toward stronger conclusions than the graph supports — the mode's analytical character is rigorous identifiability discipline, not maximal causal commitment. If the user pushes for an interventional answer the graph cannot identify, surface the assumption that would be required rather than answering it anyway.
    consolidation_pass: |
      At Gear 4, both parallel streams produce DAGs and identifiability verdicts independently. Reference frame: union of identified variables and roles (de-duplicated by stem); preserve attribution where streams produced different DAG structures (different absent-arrow assumptions). Convergent identifiability findings (both streams reached the same verdict by the same criterion) get high-confidence flag in prose. Divergent DAGs surface as alternative structures in prose with each stream's assumptions preserved; do not silently choose. Most-fragile-assumption inventory unions both streams' flags, ordered by fragility.
    verification_pass: |
      V-CDAG-1: causal question is locked at a Pearl rung. V-CDAG-2: all variables are classified by role (cause, effect, confounder, mediator, collider, instrument). V-CDAG-3: DAG is specified with absent-arrow assumptions enumerated. V-CDAG-4: back-door or front-door criterion has been applied with verdict stated. V-CDAG-5: collider variables are correctly handled (no conditioning that induces spurious dependence). V-CDAG-6: intervention or counterfactual answer matches the rung the question was locked at. V-CDAG-7: assumption inventory is ordered by fragility. V-CDAG-8: confidence per finding accompanies every causal claim.

process-tracing:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [causes, enables, requires, contradicts, qualifies, precedes]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of competing causal hypotheses about the specific historical event are weighted above resource-tier generic case-study references. Bennett-Checkel process-tracing-tests (hoop / smoking-gun / doubly-decisive / straw-in-the-wind) and Pearl causal-graphs lens content are method-foundational. Tetlock superforecasting lens content (when invoked) supplies probability-update calibration. Incubator-tier evidence pieces with provenance notes enter as primary evidence; provenance assessment is part of the analysis, not pre-filtering. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Construct competing causal hypotheses before considering evidence — hypothesis-monoculture is a primary failure mode here. For each evidence piece, classify by test type using the Bennett-Checkel framework: hoop (necessary but not sufficient — failure eliminates), smoking-gun (sufficient but not necessary — pass strongly confirms), doubly-decisive (both necessary and sufficient — both eliminates and confirms), straw-in-the-wind (neither — weakly informative). Justify each classification rather than asserting. Update each hypothesis's status given the test outcomes — failed-hoop eliminates; passed-smoking-gun strongly confirms; weak evidence does not warrant strong updates. Reconstruct the causal chain in temporal sequence with explicit links between intermediate steps; chain elision is a failure mode. Test depth by asking: could a reader reproduce the verdict from the artifact, including which evidence pieces did the heavy lifting and which would have changed the conclusion if absent?
    breadth_pass: |
      Scan for additional plausible causal hypotheses (especially ones favored by different theoretical traditions or stakeholder perspectives) before locking the candidate set. Surface evidence the analyst lacks but could obtain. Identify which evidence-piece-not-yet-found would be doubly-decisive (eliminate one hypothesis and confirm another). Assess the provenance and reliability of each evidence piece — different sources warrant different epistemic weight, and source-naivety (treating all evidence as equally credible) is a failure mode. Breadth markers: at least three plausible hypotheses are named (even if only two are seriously tested), the most diagnostic evidence-piece that does not currently exist is identified, and source-provenance is assessed per evidence piece.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) competing hypotheses constructed before evidence considered; (CQ2) per-evidence-piece test classification justified; (CQ3) hypothesis status updated appropriately given test outcomes; (CQ4) provenance and reliability assessed per evidence piece; (CQ5) causal chain reconstructed in temporal sequence with explicit links. Named failure modes (hypothesis-monoculture, test-misclassification, evidence-overreach, source-naivety, chain-elision, presentism) are the evaluation checklist. Mandate fix when only one hypothesis is tested, when evidence is treated as smoking-gun without checking sufficiency or as hoop without checking necessity, when hypotheses are declared confirmed on straw-in-the-wind evidence, when sources are not provenance-assessed, when intermediate causal-chain steps are elided, or when present knowledge is anachronistically projected onto historical actors.
    revision_pass: |
      Add competing hypotheses where the draft tests only one. Reclassify test types where the draft asserts smoking-gun status without checking sufficiency, or hoop status without checking necessity. Downgrade conclusions where evidence overreach has occurred (do not declare confirmed on weak evidence). Add provenance notes where sources were treated as equally credible. Reconstruct intermediate causal-chain steps where the draft elided them. Resist revising toward narrative coherence at the expense of test discipline — the mode's analytical character is calibrated evidence-driven inference, not satisfying storytelling. If sources are weak, the conclusion must reflect that weakness rather than smoothing it over. Strip presentist anachronisms where the analysis projected present knowledge onto historical actors.
    consolidation_pass: |
      At Gear 4, both parallel streams produce hypothesis sets, test classifications, and verdicts independently. Reference frame: union of competing hypotheses identified by both streams (de-duplicated by causal-claim stem); preserve attribution where streams classified the same evidence-piece by different test types. Convergent test-classifications (both streams classified the same evidence as smoking-gun for the same hypothesis) get high-confidence flag in prose. Divergent verdicts surface in prose with both streams' reasoning preserved; do not silently choose. Source-provenance assessments union; the more cautious provenance reading is preserved.
    verification_pass: |
      V-PT-1: at least two competing hypotheses were tested. V-PT-2: each evidence piece is classified by test type with justification. V-PT-3: hypothesis status reflects appropriate updating given test outcomes (no overreach on weak evidence). V-PT-4: source provenance is assessed per evidence piece. V-PT-5: causal chain is reconstructed in temporal sequence with explicit intermediate links. V-PT-6: residual uncertainty names diagnostic evidence not yet available. V-PT-7: confidence per finding accompanies every causal claim.
```

### T7 (new schema) — Risk and Failure Analysis

```yaml
fragility-antifragility-audit:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contradicts, qualifies, undermines, requires, enables]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the user's actual exposure profile and historical stress events are weighted above resource-tier generic Talebian references. Taleb fragility-antifragility lens content is method-foundational. Knightian risk/uncertainty/ambiguity lens (when invoked) supplies the deep-uncertainty boundary. Klein pre-mortem lens (when invoked) supplies adversarial-imagination heuristic context. Incubator-tier observations about specific stressor incidents enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Maintain the three-way distinction between fragility (concave response to volatility — small frequent gains hide rare catastrophic losses), robustness (insensitivity to volatility — neither gains nor loses from stress), and antifragility (convex response to volatility — gains-from-volatility, mechanism strengthens under stress). Antifragility-collapse (using "robust" and "antifragile" interchangeably) is a primary failure mode. For each system element, classify the response curve as convex (gains-from-volatility), concave (losses-from-volatility), or linear. Distinguish normal-condition variance from tail-event response — these are different properties; variance-tail conflation is a failure mode. Surface hidden concave exposures (small frequent gains masking rare large losses — insurance-style payoffs, leveraged positions, optionality given away). Apply via negativa: which fragility-creating elements could be removed (subtraction) rather than which robustness-creating elements should be added. Test depth by asking: could a reader identify, from the artifact, which specific element would do most damage if removed and which is doing the most damage by being present?
    breadth_pass: |
      Scan for stressors outside the analyst's normal frame (regulatory shocks, supply-chain disruption, key-person dependency, reputational tail events, technological obsolescence). Surface hidden concavities the system's stakeholders have learned not to see. Consider Lindy-effect adjustments where applicable (durability of older elements vs. fragility of newer elements). Apply Talebian heuristics with case-specific reasoning — barbell strategy (combining safe and high-risk extremes), via negativa (subtraction over addition), skin in the game (decision-makers bearing the consequences) are tools, not aphorisms to mechanically apply. Breadth markers: at least one stressor-type the user did not initially mention is named, at least one hidden concavity in the existing exposure profile is surfaced, and Talebian heuristics are applied with case-specific reasoning rather than as orthodoxy.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) fragility/robustness/antifragility classification (no antifragility-collapse into mere robustness); (CQ2) hidden concave exposures surfaced; (CQ3) variance-vs-tail distinction maintained; (CQ4) via negativa considered; (CQ5) Talebian assumptions held lightly rather than mechanically applied. Named failure modes (antifragility-collapse, hidden-concavity, variance-tail-conflation, addition-bias, Talebian-orthodoxy, false-antifragility) are the evaluation checklist. Mandate fix when "robust" and "antifragile" are used interchangeably, when only visible volatility exposures are identified, when high variance and high tail risk are conflated, when all recommendations involve adding elements rather than subtracting fragility-sources, when Talebian aphorisms are applied without case-specific reasoning, or when antifragility is claimed based on past benefit from volatility without checking whether the same mechanism applies to the volatility ahead.
    revision_pass: |
      Disentangle robustness from antifragility where the draft conflates them. Surface hidden concavities where the draft focuses only on visible volatility. Add via negativa recommendations where all recommendations involve addition. Qualify Talebian aphorisms with case-specific reasoning. Distinguish past antifragility from forward antifragility where the draft assumes the past mechanism will hold. Resist revising toward reassurance — the mode's analytical character is adversarial-Talebian, and a fragility audit that finds nothing fragile has likely missed hidden concavities. If the user pushes for a clean bill of health, surface the assumptions that would have to hold for that conclusion to be safe.
    consolidation_pass: |
      At Gear 4, both parallel streams produce exposure classifications and recommendations independently. Reference frame: union of identified convex and concave exposures (de-duplicated by element-stem); preserve attribution where streams classified the same element differently (one as concave, one as robust). Convergent hidden-concavity identification (both streams flagged the same hidden concavity) gets high-confidence flag in prose. Divergent overall fragility/robustness/antifragility verdicts surface in prose with both streams' reasoning preserved; do not silently average. Via negativa recommendations from either stream are preserved as separate from addition-recommendations.
    verification_pass: |
      V-FAA-1: convex and concave exposures are enumerated per element. V-FAA-2: the system is classified per fragility/robustness/antifragility distinction (no collapse). V-FAA-3: hidden concavities are surfaced (or explicit "no hidden concavities identified" declaration). V-FAA-4: normal-condition variance is distinguished from tail-event response. V-FAA-5: via negativa recommendations appear alongside addition-recommendations. V-FAA-6: Talebian assumptions are held lightly with case-specific reasoning. V-FAA-7: confidence per finding accompanies every classification and recommendation.
```

### T13 (new schema) — Negotiation and Conflict Resolution (Wave 3 additions)

```yaml
principled-negotiation:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [requires, enables, opposes, allies-with, depends-on, contradicts]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the user's actual stakes, BATNA candidates, and counterparty history are weighted above resource-tier generic negotiation references. Fisher-Ury principled-negotiation lens content is method-foundational. Voss tactical-empathy lens (when invoked, especially in adversarial or high-stakes contexts) supplies the Debate D6 critique. Lewicki distributive-frameworks, Raiffa ZOPA-modeling, and Thompson cross-cultural lenses (when invoked) supply distributive, ZOPA, and emotional/cross-cultural context. Incubator-tier observations about specific party positions and stakes enter as primary evidence. Symmetric weighting between parties is enforced where the analysis represents both sides. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Treat all four Fisher-Ury elements plus BATNA as load-bearing rather than decorative — a thin pass restates positions in interest-language and lists generic options; a substantive pass works each element with rigor. (1) Diagnose specific people-problem issues (perception gaps, emotional triggers, communication failures) that need separate handling from substantive bargaining; people-problem-conflation (treating it as a slogan) is a failure mode. (2) Descend from each party's stated position to the underlying need it serves (security, recognition, autonomy, economic, identity, relationship, fairness perception); flag inferred-from-confirmed; position-interest-collapse is a failure mode. (3) Generate options for mutual gain that respond to the interest pattern — moves that satisfy more interest on more sides, not generic compromise positions. (4) Name objective criteria (third-party-acceptable standards: market data, precedent, expert opinion, principle) — pseudo-objective criteria (the user's preferences in objective-sounding language) is a failure mode. (5) Assess the user's BATNA concretely — the alternative described, costed, walked-through, with weaknesses surfaced; BATNA-as-placeholder is a failure mode. (6) Infer the counterparty's BATNA with explicit hypothesis-flagging. Where context is high-stakes adversarial, surface the Voss-critique flag (Debate D6) — Fisher-Ury limitations on tactical empathy, emotional dynamics, perceived loss, ego.
    breadth_pass: |
      Survey interest categories per party (substantive economic, procedural, relational, identity-and-recognition, security, fairness-perception, future-relationship). Consider BATNA categories beyond the obvious (no-deal-and-walk-away, partial-deal, deal-with-a-different-party, deal-deferred, regulatory-or-legal-alternative, public-pressure-route — sometimes the second-tier candidate is the strongest). Scan objective-criteria categories (market value, precedent, expert opinion, scientific judgment, professional standards, efficiency, costs, what-a-court-would-decide, moral standards, equal treatment, tradition). Note cultural or contextual factors that shape which moves are available. Breadth markers: at least three interest-category candidates per party; at least two BATNA candidates for the user; at least three objective-criteria candidates with reasoning about counterparty acceptance. The Voss critique scan is part of breadth: where adversarial dynamics dominate, surface them rather than papering over with integrative framing.
    evaluation_pass: |
      Score against the six critical questions: (CQ1) position-vs-interest distinction maintained; (CQ2) inferred-vs-confirmed flagged across interests, BATNAs, motivations; (CQ3) shared and opposed both surfaced; (CQ4) BATNA concrete not placeholder; (CQ5) objective criteria genuinely third-party-acceptable; (CQ6) people-problem separation specific not slogan. Named failure modes (position-interest-collapse, inference-as-fact, integrative-overreach-or-zero-sum-default, batna-as-placeholder, pseudo-objective-criteria, people-problem-conflation, cultural-context-flatness, voss-warning-unflagged) are the evaluation checklist. Mandate fix when inferred interests track stated positions too closely, when BATNA is asserted abstractly without walk-through, when objective criteria align suspiciously well with the user's preferred outcome, when people-problem section is a generic gesture, or when high-stakes adversarial context lacks the Voss-critique flag.
    revision_pass: |
      Descend from positions to interests where the draft restated positions in interest-language. Flag inferences as hypotheses where the draft asserted them as facts. Surface both compatible and opposed interests where the draft defaulted to one. Make BATNA concrete (the alternative, costed, walked-through, weaknesses surfaced) where it is placeholder. Find genuinely third-party-acceptable objective criteria where the draft offered the user's preferences in objective-sounding language. Diagnose specific people-problem issues where the draft gestured generically. Resist revising toward optimism — the mode's character is constructive (it generates options, recommends openings) but honest about the interest landscape, including its genuinely-opposed regions and adversarial-context limitations. Manufactured integrative possibility is a failure mode, not a polish. The Voss-warning flag is part of honest revision when context warrants it.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full Fisher-Ury analyses independently. Reference frame: union of inferred interests per party, BATNA candidates, and objective-criteria candidates (de-duplicated by need-stem); preserve attribution where streams inferred different underlying interests or different counterparty BATNAs. Convergent inferences (both streams identified the same interest from the same position) get high-confidence flag in prose. Divergent options-for-mutual-gain proposals surface as alternatives in prose; do not silently average. Both shared-and-opposed regions identified by either stream are preserved. The Voss-critique flag from either stream (when context warrants) is preserved.
    verification_pass: |
      V-PN-1: parties and stated positions are named. V-PN-2: people-problem separation diagnosis is specific (not generic gesture). V-PN-3: inferred underlying interests are itemized per party with hypothesis-flagging. V-PN-4: shared/compatible interests AND genuinely-opposed interests are separately surfaced. V-PN-5: at least one option for mutual gain is named with its supporting interest-pattern. V-PN-6: at least three objective-criteria candidates are named with reasoning about counterparty acceptance. V-PN-7: user BATNA is concrete (described, costed, walked-through). V-PN-8: counterparty BATNA is hypothesis-flagged. V-PN-9: recommended opening-and-fallback pattern is specific. V-PN-10: flagged unknowns are testable in negotiation. V-PN-11: where context warrants, Voss-critique adversarial-context flag (Debate D6) is present.

third-side:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contains, supports, opposes, allies-with, requires, enables]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the surrounding community/network and prior third-side interventions are weighted above resource-tier generic mediation references. Ury third-side lens content is method-foundational. Lederach conflict-transformation, Kriesberg constructive-conflicts, Fisher-Ury principled-negotiation, and Voss tactical-empathy lenses (when invoked) supply identity-rooted-conflict, trajectory-analysis, party-coaching, and adversarial-context-coaching. Incubator-tier observations about specific community resources and existing institutions enter as primary evidence. Symmetric weighting between parties is enforced — the third-side stance requires that no party's source material dominates the analysis. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Maintain the third-side stance — analyzing what the surrounding community can do — rather than slipping into party-side advocacy for one party's interests; party-stance-creep is a primary failure mode. Map the surrounding community/network — colleagues, friends, family, neighbors, leaders, professionals, institutions, norms — as a social fact that may or may not contain the roles the conflict needs. Survey all ten Ury roles in their three clusters: prevention (provider — addresses frustrated needs that drive conflict; teacher — gives skills for conflict-handling; bridge-builder — develops relationships that pre-empt conflict), resolution (mediator — facilitates communication; arbiter — judges when self-resolution fails; equalizer — democratizes power asymmetry; healer — addresses injured emotions and broken relationships), containment (witness — pays attention so escalation has consequences; referee — establishes rules for fair fight; peacekeeper — interposes when violence threatens). Ten-role-collapse (only mediator named) is a failure mode. Identify which roles are active (already being filled, well or poorly), which are needed but unfilled, which are not yet relevant. Link role assignments to actual people / institutions / norms — roles-without-bearers is a failure mode. Acknowledge limits: power asymmetry that makes mediation cover for coercion, parties' agency that makes intervention intrusive, situations requiring confrontation rather than mediation; third-side-overreach is a failure mode. Test depth by asking: could the analysis tell the user which one or two role gaps, if filled, would change the conflict's trajectory most?
    breadth_pass: |
      Scan the surrounding community in three rings (intimate — family / close colleagues; mid — extended network / institutional context; outer — wider community / public / norms). Survey all three role-clusters (prevention / resolution / containment) before narrowing — prevention-or-containment-omission (defaulting to resolution-only) is a failure mode. Consider escalation signals (rhetoric hardening, third-party recruitment to one side, breakdown of channels of communication, emergence of public symbolic markers, threats of exit or violence). Consider parallel third-side traditions (Lederach's conflict-transformation lineage on identity-rooted conflict; Kriesberg's constructive-conflicts trajectory analysis; restorative justice; indigenous and traditional dispute-resolution practices that may already exist in the community). Breadth markers: all ten Ury roles considered (even if most are not active); all three role-clusters considered; the surrounding community mapped in at least two rings; escalation signals listed; the limits of third-side intervention acknowledged.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) third-side stance maintained, not party-stance creep; (CQ2) ten-role checklist surveyed; (CQ3) all three role-clusters (prevention / resolution / containment) considered; (CQ4) roles linked to actual bearers; (CQ5) limits acknowledged. Named failure modes (party-stance-creep, ten-role-collapse, prevention-or-containment-omission, roles-without-bearers, third-side-overreach, cultural-context-flatness, parties-as-passive) are the evaluation checklist. Mandate fix when output reads as party-side advocacy, when only one or two of the ten roles are surveyed, when only resolution roles are addressed, when roles are listed without naming bearers, when intervention is asserted as universally appropriate without limits, or when parties are framed as passive objects of intervention.
    revision_pass: |
      Restore third-side stance where the draft slipped into party advocacy. Expand the role survey where the draft collapsed to mediator-only. Address prevention and containment where the draft addressed only resolution. Name bearers where the draft asserted roles in the abstract. Acknowledge limits where the draft asserted third-side as universally appropriate. Honor parties' agency where the draft positioned them as passive objects of intervention. Resist revising toward generic mediator-talk — the mode's analytical character is the ten-role-and-three-cluster frame, not generic mediation; collapsing back to "mediator" is a failure mode, not a polish. Resist revising toward over-confident community capacity assertions — sometimes the surrounding community lacks the third side the conflict needs, and naming that is part of honest analysis.
    consolidation_pass: |
      At Gear 4, both parallel streams produce third-side analyses independently. Reference frame: union of community/network mappings, role surveys, and bearer-candidate identifications (de-duplicated by role-stem); preserve attribution where streams identified different role gaps as most load-bearing. Convergent role-need identification (both streams identified the same role-gap as critical) gets high-confidence flag in prose. Divergent intervention recommendations surface as alternatives in prose with both streams' reasoning preserved; do not silently choose. Limits-acknowledgment from the more cautious stream is preserved.
    verification_pass: |
      V-TS-1: parties and conflict are named. V-TS-2: surrounding community/network is mapped (the third side as social fact). V-TS-3: all three role-clusters (prevention / resolution / containment) are addressed. V-TS-4: the ten Ury roles are surveyed (each with active / needed / not-yet-relevant tag). V-TS-5: role-assignment candidates link roles to actual bearers in the surrounding community. V-TS-6: escalation signals are listed. V-TS-7: at least two specific third-side interventions are named with role-gap rationale. V-TS-8: flagged unknowns are testable in practice. V-TS-9: intervention limits acknowledged where context warrants. V-TS-10: third-side stance is maintained throughout (no party-advocacy creep). V-TS-11: parties are honored as agents (not framed as passive objects).
```

### T16 (new schema) — Mechanism Understanding

```yaml
mechanism-understanding:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contains, produces, requires, enables, qualifies]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the phenomenon's components and prior mechanism descriptions are weighted above resource-tier generic systems-thinking references. Meadows twelve-leverage-points and Senge system-archetypes lens content (when invoked) supply leverage-pattern and archetype-signature context. Domain-specific component inventories at engram-tier weighted highest. Incubator-tier observations about specific component behaviors enter as primary evidence. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Lock the level of analysis explicitly (molecular, cellular, organizational, system-wide) — level-confusion (jumping between levels without acknowledgment) is a primary failure mode. Inventory the components with each component's function stated, not merely named — component-inventory-without-function is a failure mode. Describe the interaction pattern among components as the source of the whole's behavior, rather than treating the whole's behavior as a separate fact alongside the components — emergence-elision is a failure mode. The mechanism account should make at least one prediction about how the whole's behavior would change if a specific component were altered, removed, or replaced; just-so explanations that fit observed behavior but make no predictions are a failure mode. Stay within T16's mechanism territory rather than drifting into T4 causal investigation (backward-to-causes) or T17 process-flow (temporal-sequence) — territory-conflation is a failure mode. Test depth by asking: could the explanation predict how the whole's behavior would change if a specific component were altered, removed, or replaced — and does the answer follow from the stated mechanism rather than from intuition?
    breadth_pass: |
      Scan for components the analyst might omit (background conditions, supporting infrastructure, regulatory or constraining elements that do not actively contribute but enable contribution). Consider alternative mechanism descriptions at different levels of analysis — the same phenomenon can be explained at multiple levels; the question is which level the user actually needs. Surface where the mechanism is incomplete or where multiple mechanisms could account for the same observed behavior. Breadth markers: at least one background-or-enabling component that easy descriptions tend to omit is named, and at least one alternative-mechanism candidate the available evidence cannot rule out is acknowledged.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) level of analysis locked; (CQ2) components inventoried with function per component; (CQ3) interaction pattern as source of whole's behavior (not behavior alongside components); (CQ4) boundary conditions named (when mechanism applies, when it breaks down, what it does not explain); (CQ5) explanation distinguished from process-map (T17) and causal-chain (T4). Named failure modes (level-confusion, component-inventory-without-function, emergence-elision, scope-overreach, territory-conflation, just-so-explanation) are the evaluation checklist. Mandate fix when explanation jumps between levels, when components are merely named without function, when whole's behavior is described separately from components without an emergence account, when mechanism is extended beyond boundary conditions, when output blends process-flow narration or causal-chain investigation with mechanism explanation, or when explanation makes no predictions about altered conditions.
    revision_pass: |
      Lock the level of analysis where the draft drifts. Add functional role per component where components are merely named. Make the emergence account explicit — the interaction pattern producing the behavior — where the draft asserts the behavior and the components separately. Add boundary conditions where the explanation appears unbounded. Resist revising toward narrative process-flow or causal-chain explanation — these are different territories. If the user wants temporal flow, escalate to T17 process-mapping; if they want causes of an outcome, escalate to T4 causal modes. Add at least one prediction about behavior under altered conditions where the draft offers a just-so explanation.
    consolidation_pass: |
      At Gear 4, both parallel streams produce mechanism explanations independently. Reference frame: union of identified components and functions (de-duplicated by component-stem); preserve attribution where streams locked different levels of analysis or proposed different interaction patterns. Convergent emergence accounts (both streams articulated the same interaction pattern as source of behavior) get high-confidence flag in prose. Divergent alternative-mechanism candidates surface as alternatives in prose; do not silently choose. Boundary conditions union — the more conservative scope is preserved.
    verification_pass: |
      V-MU-1: level of analysis is locked. V-MU-2: components are inventoried with functional role per component. V-MU-3: interaction pattern is described as the source of the whole's behavior. V-MU-4: emergence is accounted for (not elided). V-MU-5: boundary conditions are named. V-MU-6: explanation makes at least one prediction about behavior under altered conditions. V-MU-7: output is distinguishable from a T4 causal-chain analysis or a T17 process-map. V-MU-8: confidence per finding accompanies every claim.
```

### T17 (new schema) — Process and System Analysis (Wave 3 additions)

```yaml
process-mapping:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [precedes, requires, enables, contains, depends-on]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the actual process flow and known pain-points are weighted above resource-tier generic workflow references. Meadows twelve-leverage-points and Senge system-archetypes lens content (when invoked) supply bottleneck-as-leverage and archetype-signature context. Incubator-tier observations about specific deviations between documented and actual process enter as primary evidence — the official-vs-actual gap is part of the analysis, not pre-filtered. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Lock the process boundaries (clear start trigger and end condition) before mapping — scope-creep (boundaries shifting during execution) is a primary failure mode. Distinguish the documented (official) process from the actual (lived) process; describing only one as if it were both is a failure mode (official-vs-actual-elision). Identify decision points and branching paths with explicit decision criteria; collapsing to a single happy path is a failure mode (happy-path-flattening). For each bottleneck, name the underlying constraint (capacity / authority / information / sequencing) rather than just the symptom — bottleneck-symptom-only is a failure mode. Examine handoffs between actors for friction, information loss, transformation, and queue accumulation; treating handoffs as transparent is a failure mode (handoff-blindness). Stay within T17's descriptive territory; do not drift into causal explanation of why outcomes occur — causal-overreach is a mode-boundary violation requiring escalation to T4. Test depth by asking: could a new actor entering the process at any step understand from the map alone what they need, who they wait for, and what unblocks them?
    breadth_pass: |
      Scan for exception paths and edge cases (what happens when the input is malformed, when an actor is absent, when a dependency is unavailable). Surface the gap between documented and actual process flow. Identify handoff friction (information loss, role-confusion, queue accumulation) at every actor boundary. Consider whether the process exhibits feedback structure that would warrant escalation to systems-dynamics-structural; if outputs cyclically influence inputs, linear-flow mapping is insufficient. Breadth markers: the map shows at least one exception path explicitly, surfaces at least one official-vs-actual deviation, and flags handoffs as friction zones rather than treating them as transparent.
    evaluation_pass: |
      Score against the five critical questions: (CQ1) process boundaries locked (clear start trigger and end condition); (CQ2) documented vs. actual process distinguished; (CQ3) decision points and branching paths identified with explicit criteria; (CQ4) bottlenecks identified with underlying constraint (not just symptom); (CQ5) handoffs examined for friction. Named failure modes (scope-creep, official-vs-actual-elision, happy-path-flattening, bottleneck-symptom-only, handoff-blindness, causal-overreach) are the evaluation checklist. Mandate fix when boundaries shifted during mapping, when only documented process is shown without acknowledging deviations, when all branching paths collapse to one main flow, when bottlenecks are named without underlying constraints, when handoffs are presented without friction examination, or when the map presents itself as causal explanation (escalate to T4 instead).
    revision_pass: |
      Add exception paths where the draft shows only the happy path. Surface official-vs-actual deviations where the draft conflates them. Identify the constraint underlying each bottleneck where the draft names only the symptom. Examine handoffs as friction zones where the draft treats them as transparent. Lock scope where boundaries shifted during execution. Resist revising toward causal explanation of outcomes — the mode's analytical character is descriptive process documentation. If the user wants causal analysis of why the process produces particular outcomes, escalate to T4 causal modes rather than overreaching the mapping. If feedback structure becomes apparent, sideways-route to systems-dynamics-structural.
    consolidation_pass: |
      At Gear 4, both parallel streams produce process maps independently. Reference frame: union of identified steps, decision points, dependencies, and bottlenecks (de-duplicated by step-stem); preserve attribution where streams identified different official-vs-actual deviations or different handoff friction-points. Convergent bottleneck identification with the same underlying constraint gets high-confidence flag in prose. Divergent decision-point criteria surface in prose with both streams' readings preserved; do not silently choose. Exception-path inventory unions both streams' findings.
    verification_pass: |
      V-PM-1: process boundaries are locked with explicit start trigger and end condition. V-PM-2: actors are inventoried with role attribution per step. V-PM-3: decision points are surfaced with criteria. V-PM-4: dependencies are mapped. V-PM-5: bottlenecks are identified with underlying constraints (not just symptoms). V-PM-6: handoffs are examined for friction. V-PM-7: official-vs-actual distinction is acknowledged. V-PM-8: confidence per finding accompanies every claim.
```

### T19 (new schema) — Spatial Composition (Wave 3 additions)

```yaml
information-density:
  gear: 4
  expected_runtime: ~5min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contains, supports, contradicts, qualifies, requires]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of the intended message and prior info-graphic critiques are weighted above resource-tier generic visualization references. Tufte data-ink-chartjunk, Bertin visual-variables, Cleveland-McGill perceptual-tasks, and Bringhurst typographic-hierarchy lens content are method-foundational. Lupton thinking-with-type, Few information-dashboard-design, Munzner visualization-analysis-and-design, Kosslyn graph-design, and Wilkinson grammar-of-graphics lenses (when invoked) supply typography-dominant, dashboard, task-data-encoding, audience-cognition, and systematic chart-comparison context. The user-supplied info-graphic is the primary evidence; tradition vocabulary informs the critique but does not override the graphic's actual encoding choices. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Integrate four analytical operations rather than aggregating them. (1) Data-ink ratio audit (Tufte) — for each mark in the graphic, classify as data-ink (carries data), structure-ink (carries necessary scaffolding: axes, scale references, data-defining frames), or chartjunk (carries decoration / redundancy / moiré / 3D effect / unnecessary color); compute or estimate the ratio; identify specific removals or simplifications without information loss. Data-ink-as-slogan (asserting "chartjunk" generically without auditing specific marks) is a failure mode. (2) Visual-variable mapping check (Bertin) — for each data attribute, identify which visual variable encodes it (position, size, shape, value, color, orientation, texture) and check fitness against the variable's selective / associative / ordered / quantitative properties (e.g., color is selective but not quantitative; position is all four); flag mismatches. Bertin-mapping-unchecked is a failure mode. (3) Elementary perceptual task fitness check (Cleveland-McGill) — identify the perceptual task the graphic requires (position-on-common-scale > nonaligned-position > length > angle > direction > area > volume > color/shading, in descending accuracy); check whether the chart type supports the required task at the accuracy the message demands. Elementary-task-mismatch-undiagnosed is a failure mode. (4) Typographic hierarchy and grid analysis (Bringhurst / Lupton) where applicable — scale, weight, color, rhythm, measure, leading, grid alignment; check that hierarchy supports reading order. Typography-as-not-encoding (skipping typography because the input has charts) is a failure mode. A thin pass invokes labels (chartjunk; clean up; improve hierarchy); a substantive pass performs each of the four operations with specific findings and produces specific recommendations. Test depth by asking: could a designer implement the recommendations without further interpretation?
    breadth_pass: |
      Scan across the four lens-clusters before narrowing (Tufte data-ink / Bertin visual-variables / Cleveland-McGill perceptual-tasks / Bringhurst-Lupton typography). Consider the graphic in its decision-support context (what does the audience need to read off the graphic at a glance, what at sustained attention, what should they decide or notice). Consider the chart-type alternatives at the decision point (could a different chart type — small multiples, sparkline, dot plot, slope graph, table — support the elementary task more accurately). Consider the constraints (brand / house-style; accessibility — color-blindness, contrast, screen-reader; data-honesty — does the encoding mislead through truncation, area-vs-length confusion, or 3D distortion; audience expectation — convention may justify deviation from theoretical optimum). Note where the input is part of a larger system (a dashboard's coordination, a report's narrative arc, a presentation's slide rhythm). Breadth markers: at least three of the four lens-clusters substantively addressed (typography skipped only if input is purely chart-without-text); at least one chart-type alternative considered if the chart-type-fit is in question; at least one constraint acknowledged. Note Reserved-M5 promotion-evidence if recurring info-graphic invocations encounter operations this mode handles awkwardly.
    evaluation_pass: |
      Score against the six critical questions: (CQ1) elementary perceptual task identified and encoding-fitness assessed; (CQ2) visual-variable mapping checked against Bertin properties; (CQ3) data-ink ratio audited specifically not asserted as label; (CQ4) typographic hierarchy and grid analyzed where applicable; (CQ5) recommendations specific not gestures; (CQ6) constraints acknowledged. Named failure modes (elementary-task-mismatch-undiagnosed, bertin-mapping-unchecked, data-ink-as-slogan, typography-as-not-encoding, recommendations-as-gestures, constraint-blindness, tufte-orthodoxy, aesthetic-only-critique) are the evaluation checklist. Mandate fix when Cleveland-McGill ranking is not applied, when visual-variable mapping is not assessed for fitness, when "chartjunk" is invoked as a label without specific mark-by-mark audit, when typography is skipped on the assumption that text is not part of the encoding, when recommendations are general gestures (simplify, declutter) rather than specific (replace pie chart with horizontal bar; reduce gridline contrast to 30%), or when the critique addresses aesthetic preferences without grounding in encoding-fitness.
    revision_pass: |
      Identify the elementary perceptual task and check encoding-fitness where the draft skipped Cleveland-McGill. Check visual-variable mapping where the draft skipped Bertin. Audit specific marks where the draft asserted "chartjunk" generically. Perform typographic hierarchy analysis where the draft skipped typography-as-encoding. Make recommendations specific (which mark, which encoding, which element, which hierarchy) where the draft offered gestures. Acknowledge constraints (brand / accessibility / data-honesty / audience-expectation) where the draft asserted recommendations as unconstrained. Resist revising toward Tufte orthodoxy — the mode's character is applied-evaluative-medium-depth with prescriptive recommendation; minimalism is a strong default but not a dogma, and contexts where minor redundancy / framing / annotation actively serves the audience or message are real. Resist revising toward aesthetic-only critique — the mode is grounded in encoding-fitness and perceptual-task analysis, not in aesthetic preference.
    consolidation_pass: |
      At Gear 4, both parallel streams produce critiques and recommendations independently. Reference frame: union of data-ink classifications, visual-variable mappings, perceptual-task identifications, and recommendations (de-duplicated by mark-stem); preserve attribution where streams classified the same mark differently (one as chartjunk, one as structure-ink) or proposed different chart-type alternatives. Convergent encoding-misfit findings (both streams identified the same elementary-task-mismatch with the same diagnosis) get high-confidence flag in prose. Divergent prescriptive recommendations surface as alternatives in prose; do not silently choose. Constraint-acknowledgment from the more cautious stream is preserved.
    verification_pass: |
      V-ID-1: graphic's intended message is named. V-ID-2: data-ink ratio audit lists data-ink, structure-ink, and chartjunk marks specifically. V-ID-3: visual-variable mapping checked per data attribute against Bertin properties. V-ID-4: elementary perceptual task identified with encoding-fitness assessed per Cleveland-McGill ranking. V-ID-5: typographic hierarchy and grid analysis present where input includes typography (or marked not-applicable). V-ID-6: prescriptive recommendations are specific (which mark, which encoding, which removal, which hierarchy), ranked by impact. V-ID-7: residual tradeoffs and constraints (brand / accessibility / data-honesty / audience-expectation) are acknowledged. V-ID-8: confidence per recommendation distinguishes high / medium / low.

place-reading-genius-loci:
  gear: 4
  expected_runtime: ~5-8min
  type_filter: [engram, resource, incubator]
  context_budget: default
  RAG_profile:
    relationship_priorities:
      prioritize: [contains, supports, contradicts, qualifies, requires, opposes]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Engram-tier articulations of inhabitation-context, design-brief, and prior place-readings on comparable spaces are weighted above resource-tier generic environmental-design references. Alexander pattern-language, Norberg-Schulz genius-loci, Lynch image-of-the-city, Bachelard topoanalysis, Appleton prospect-refuge, and Kaplan attention-restoration lens content are method-foundational (this is the deepest-multi-tradition T19 mode at Tier-2 deep depth). Kellert biophilic-design, Alexander nature-of-order, Tuan space-and-place, and Relph place-and-placelessness lenses (when invoked) supply biophilic, wholeness, place-phenomenology, and authentic-place context. The user-supplied place is the primary evidence; tradition vocabulary informs the reading but does not override the place's actual spatial features. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Integrate six analytical operations rather than aggregating them — this is the deep tier in T19, requiring the multi-tradition synthesis the place-reading literature demands. (1) Prospect-refuge-hazard balance (Appleton) — specific sightlines that constitute prospect, specific positions that constitute refuge, specific hazards mitigated or unmitigated. Prospect-refuge-as-label (invoking the framework without spatial warrant) is a failure mode. (2) Active pattern-language patterns (Alexander) — which patterns are present, absent, or violated, with the (context, problem, solution) triple checked per pattern; pattern-misapplication (using pattern names as decoration) is a failure mode. (3) Lynchian legibility — the five elements (paths, edges, districts, nodes, landmarks) identified by their cognitive-mapping role for an actual user; lynchian-element-confusion (treating any boundary as an edge) is a failure mode. (4) Restorative properties (Kaplan & Kaplan ART) — being-away, extent, compatibility, soft fascination assessed; biophilic patterns where applicable. (5) Genius loci (Norberg-Schulz) — the qualitative-total character of place articulated as gestalt, not as feature aggregate; aggregate-as-gestalt (listing features rather than articulating character) is a failure mode. (6) Bachelardian topoanalysis where applicable — the intimate spaces (corner, miniature, intimate immensity, drawer-as-threshold, nest, shell) and their psychological condensations. Ground all affordances in concrete spatial features (dimensions, sightlines, light, materials, thresholds, scale) rather than analyst projection — analyst-projection is a primary failure mode. Test the reading for an inhabitant of different stature, ability, or culture from the analyst's default — default-inhabitant-bias is a failure mode. Produce predictions of observable behavior (lingering, avoidance, restoration, conversation-clustering, path-choice) rather than sentiment-only readings — sentiment-only-reading is a failure mode. Acknowledge limits — situations where affordance prediction depends on cultural/historical context the analysis lacks, where contested-place readings exist, or where the space's affordances conflict with its intended use; unified-reading-overreach is a failure mode. Test depth by asking: could a designer use this reading to know which one or two changes would most alter the place's affordances?
    breadth_pass: |
      Scan across the six tradition-clusters before narrowing (prospect-refuge / pattern-language / Lynchian / restorative / genius loci / Bachelardian). Consider the place at multiple scales (room, building, urban, landscape — affordances at one scale may conflict with affordances at another). Consider temporal variation (lighting, seasons, time-of-day, social occupancy patterns). Consider inhabitant variation (different stature, ability, age, culture, expertise, expectation). Consider the place's history (designed-for vs. inherited-and-adapted; contested-place readings where multiple communities claim or contest the place). Breadth markers: at least three of the six tradition-clusters are addressed substantively; the place is considered at least at its primary scale and one adjacent scale; at least one inhabitant-variation test is run.
    evaluation_pass: |
      Score against the six critical questions: (CQ1) affordances grounded in concrete spatial features not analyst projection; (CQ2) reading survives different inhabitant vantage; (CQ3) prospect-refuge supported by spatial warrant not asserted as label; (CQ4) reading produces testable behavioral predictions not sentiment-only; (CQ5) genius loci treated as gestalt not aggregate; (CQ6) limits acknowledged. Named failure modes (analyst-projection, default-inhabitant-bias, prospect-refuge-as-label, sentiment-only-reading, aggregate-as-gestalt, unified-reading-overreach, pattern-misapplication, lynchian-element-confusion) are the evaluation checklist. Mandate fix when affordances are asserted without grounding in spatial features, when the reading assumes a default inhabitant, when prospect-refuge labels are applied without spatial warrant, when readings produce sentiment statements without testable behavioral predictions, when genius loci is asserted as feature-aggregate without articulating gestalt, when pattern-language patterns are invoked without checking the (context, problem, solution) triple, or when Lynch elements are misapplied (treating any boundary as an edge).
    revision_pass: |
      Ground asserted affordances in concrete spatial features where the draft projected analyst preferences. Test inhabitant-vantage variation where the draft assumed a default inhabitant. Apply prospect-refuge with spatial warrant where the draft used the labels decoratively. Make behavioral predictions testable where the draft offered sentiment only. Articulate genius loci as gestalt where the draft listed features. Apply pattern-language patterns by checking the (context, problem, solution) triple where the draft used pattern names as decoration. Identify Lynch elements by cognitive-mapping role where the draft used the labels mechanically. Resist revising toward sentiment / aesthetic-only / wholeness-claim — the mode's character is descriptive-evaluative-deep with predictive output; the reading is defeasible and produces testable claims about inhabitation. Resist revising toward unified-reading where the place legitimately admits conflicting affordances or contested readings — the conflict is part of the place, not a defect of the analysis.
    consolidation_pass: |
      At Gear 4, both parallel streams produce place-readings independently. Reference frame: union of identified affordances, prospect-refuge configurations, active patterns, Lynchian elements, and restorative properties (de-duplicated by spatial-feature stem); preserve attribution where streams articulated different genius-loci gestalts or identified different Bachelardian intimate-spaces. Convergent affordance-identification with the same spatial warrant gets high-confidence flag in prose. Divergent counter-readings from each stream are preserved as alternatives — defeasibility is structural to the mode at this depth, and multiple defensible counter-readings strengthen rather than weaken the artifact. Inhabitant-vantage tests from both streams union (the more diverse inhabitant set is preserved). Limits-acknowledgment from the more cautious stream is preserved.
    verification_pass: |
      V-PRGL-1: place summary and scale are stated. V-PRGL-2: prospect-refuge-hazard balance is grounded in specific spatial features (sightlines, refuge positions, hazard mitigation). V-PRGL-3: active pattern-language patterns are listed with the (context, problem, solution) triple checked per pattern. V-PRGL-4: Lynchian legibility assessment names the five-element identifications and the place's legibility as a whole. V-PRGL-5: restorative properties assessment uses ART vocabulary (being-away, extent, compatibility, soft fascination) plus biophilic patterns where applicable. V-PRGL-6: genius loci character-of-place articulates the qualitative-total gestalt with orientation and identification. V-PRGL-7: Bachelardian topoanalysis notes are present where applicable (or marked not-applicable for spaces whose scale or character does not invite topoanalysis). V-PRGL-8: predicted inhabitation and dwelling-modes are testable behavioral claims. V-PRGL-9: design affordance recommendations are specific and keyed to spatial features. V-PRGL-10: confidence per claim is provided; at least one counter-reading where the place admits multiple legitimate readings; explicit acknowledgment where cultural-context or temporal-condition limits constrain the reading.
```

---

## Phase 4 Wave 4 — New-Architecture Entries (Molecular Modes)

*Per the 2026-05-01 Wave 4 build. All Wave 4 modes are molecular compositions (`composition: molecular`); the `decision-clarity` entry above (in T2) is also Wave 4 and was upgraded from its earlier placeholder shape. The molecular-mode pattern is: `gear: 4`, `expected_runtime: ~10+min`, `type_filter: [engram, resource, incubator]`, `context_budget: extended`. RAG profiles prioritize component-relationship types (`composes`, plus the relationships needed by the components composed). Provenance treatment weights component-source provenance through synthesis. Instructions integrate component outputs (depth_pass), consider alternative compositions (breadth_pass), evaluate the integrated output (evaluation_pass), revise without losing component provenance (revision_pass), consolidate the final artifact with component-provenance carried through (consolidation_pass), and verify synthesis quality (verification_pass). Entries are ordered by territory (T1, T3, T5, T6, T9, T14).*

### T1 (new schema) — Argumentative Artifact Examination (Wave 4 additions)

```yaml
argument-audit:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: extended
  RAG_profile:
    relationship_priorities:
      prioritize: [composes, contradicts, qualifies, requires, supports, undermines]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Argument Audit composes frame-audit + coherence-audit and carries Debate D2 (the inferential-vs-framing tension that governs comprehensive argument analysis). Component-source provenance is preserved end-to-end: frame-audit findings about what the argument selects in/out and what it naturalizes carry their component-of-origin tag through synthesis; coherence-audit findings about Toulmin warrants and inferential gaps carry theirs. Engram-tier articulations of the user's prior frame-audit and coherence-audit operations on related artifacts are weighted above resource-tier generic argument-analysis references. Lakoff/Goffman/Entman framing-lens content (frame-audit side) and Toulmin/Walton inferential-lens content (coherence-audit side) are method-foundational. Debate D2 (whether argument-soundness can be assessed without first surfacing the frame, or whether frame-suspension is preliminary to inferential audit) is the live tension the synthesis must hold. Incubator-tier observations about specific argument-fragments enter as primary evidence with their component-relevance flagged. P1/P2 over P3-P6; component-level conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Argument Audit is the molecular composition of frame-audit + coherence-audit, integrated into a single comprehensive analytical pass on the argumentative artifact. Run each component substantively. (1) Frame audit: identify the frame the argument operates within, what it foregrounds and backgrounds, what presuppositions are smuggled, what is naturalized. (2) Coherence audit: identify the Toulmin structure (claim, data, warrant, backing, qualifier, rebuttal); locate inferential gaps, fallacies, unsupported warrants, and internal contradictions. Integration is the load-bearing operation: a frame-audit finding (the argument naturalizes a particular value-orientation) reshapes the coherence audit (warrants depending on that naturalization are now flagged as frame-dependent rather than universal); a coherence-audit finding (a key warrant has no backing) reshapes the frame audit (the warrant's frame-dependence becomes the explanation for why backing was elided). Sectional concatenation (frame audit followed by coherence audit with no cross-talk) is the primary failure mode. Hold Debate D2 explicitly: where frame-suspension is genuinely preliminary to inferential assessment, name that ordering; where the inferential structure is independently auditable, do so without waiting on frame analysis. Test depth by asking: would the integrated audit have caught a flaw that frame-audit alone or coherence-audit alone would have missed?
    breadth_pass: |
      Survey alternative compositions: would the artifact benefit from adding propaganda-audit (when the argument shows mobilization characteristics — flawed-ideology, concept-substitution, not-at-issue content)? Would adding paradigm-suspension (T9) deepen the frame side where the argument operates within a contested paradigm? Consider whether the audit should run a comparative pass (frame-comparison, T9) when the argument is one of several making competing claims. Scan the argument for genre-conventions that legitimately permit moves a strict coherence audit would flag (e.g., legal argument's reliance on precedent-as-warrant, scientific argument's reliance on consensus-as-warrant). Breadth markers: at least one alternative compositional balance considered, at least one genre-convention noted where applicable, and the audience for the audit (academic vs. policy vs. journalistic) is explicit because audit standards differ.
    evaluation_pass: |
      Score the integrated audit, not the component findings in isolation. Critical questions: (CQ1) does each component pass meet substantive depth (frame audit names specific selected-in/selected-out content, not a generic "framing matters" note; coherence audit identifies specific warrants and inferential gaps, not generic "fallacy" labels); (CQ2) is integration load-bearing — do component findings visibly reshape each other; (CQ3) is Debate D2 surfaced where the artifact admits both readings; (CQ4) does the audit distinguish frame-dependent flaws from frame-independent flaws; (CQ5) is component-of-origin provenance preserved per finding? Named failure modes (component-as-stub, sectional-concatenation, debate-collapse, frame-independent-overreach, fallacy-label-without-content, provenance-collapse) are the evaluation checklist. Mandate fix when frame audit is generic, when coherence audit lists fallacy labels without naming the inference, when the two audits do not cross-talk, when Debate D2 is suppressed, when frame-dependent flaws are presented as if frame-independent, or when component-of-origin attribution is lost.
    revision_pass: |
      Synthesis-revision must preserve component provenance. Where the integrated draft strengthened one component finding using the other component's evidence, ensure the cross-component support is visible (annotation, parenthetical, footnote-style attribution). Add depth where any component reads as stub. Make integration mutual where the draft concatenates. Surface Debate D2 where the draft suppresses it. Rewrite frame-dependent flaws as such where the draft presents them as universal. Resist revising toward consensus on the artifact's quality — where frame-audit and coherence-audit reach divergent verdicts (the argument is internally coherent but operates within a frame that obscures its premises; or, the argument's frame is sound but its inferential structure is flawed), the divergence is the analytic finding, not a defect. The mode's character is comprehensive argument analysis with both lenses substantively integrated, not a quality-rating.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full integrated audits independently. Reference frame: union of frame-audit findings and coherence-audit findings across streams (de-duplicated by finding-stem), with component-of-origin AND stream-of-origin tags preserved. Convergent component findings (both streams' coherence-audit identified the same Toulmin gap) get high-confidence flag. Divergent integrations (one stream led with frame-audit, the other with coherence-audit) surface as alternative analytic arcs in prose; do not silently choose. Where streams reached opposite verdicts on Debate D2 (one held frame-suspension as preliminary, the other held the inferential audit as independently runnable), preserve both readings — the disagreement is a substantive finding about the artifact, not noise.
    verification_pass: |
      V-AA-1: both composed components (frame-audit, coherence-audit) are substantively present (not stubbed). V-AA-2: integration is load-bearing — at least two visible cross-component reshapings. V-AA-3: Debate D2 is surfaced where the artifact admits both readings. V-AA-4: frame-dependent flaws are distinguished from frame-independent flaws. V-AA-5: component-of-origin provenance is visible per major finding. V-AA-6: where fallacies are named, the specific inference is identified (not just the label). V-AA-7: confidence per finding accompanies every claim.
```

### T3 (new schema) — Decision-Making Under Uncertainty (Wave 4 additions)

```yaml
decision-architecture:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: extended
  RAG_profile:
    relationship_priorities:
      prioritize: [composes, requires, enables, contradicts, qualifies, depends-on, opposes]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Decision Architecture composes decision-under-uncertainty + constraint-mapping + stakeholder-mapping + pre-mortem-action into an integrated decision design. Component-source provenance is preserved end-to-end: decision-under-uncertainty findings about uncertainty classification and value-of-information carry their component tag; constraint-mapping findings about feasibility envelopes and tradeoffs carry theirs; stakeholder-mapping findings about parties and their interests carry theirs; pre-mortem-action findings about adversarial-future failure modes carry theirs. Engram-tier articulations of the user's actual decision context, criteria, and constraints dominate. Resource-tier decision-theory references (Howard, Raiffa, Kahneman, Klein) inform method. Incubator-tier observations about specific stakeholder positions, constraint instances, and historical analogues enter as primary evidence with component-relevance flagged. P1/P2 over P3-P6; component-level conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Decision Architecture is the molecular composition of four decision-relevant components, integrated into a unified decision design. Run each substantively. (1) Decision under uncertainty: classify uncertainties (risk / Knightian / deep), identify value-of-information moves, build the decision-tree or influence-diagram skeleton. (2) Constraint mapping: identify feasibility envelopes, hard constraints, soft constraints, and the tradeoff topology among options. (3) Stakeholder mapping: inventory parties, stated positions, inferred interests, and decision-relevance per party. (4) Pre-mortem action: imagine the decision has failed badly; trace the failure modes back from the failure to the decision-time signals that would have predicted them. Integration is load-bearing: the pre-mortem failure modes reshape uncertainty classification (Knightian uncertainties become identifiable when their failure-mode signatures are named); stakeholder findings reshape constraint-mapping (party opposition becomes a soft constraint with a quantifiable cost); uncertainty findings reshape stakeholder-mapping (parties whose interests depend on uncertain states have conditional positions). Four-component-stub-concatenation is the primary failure mode. Test depth by asking: would the integrated architecture have surfaced a decision risk that any single component alone would have missed?
    breadth_pass: |
      Survey alternative compositions: would the architecture benefit from substituting multi-criteria-decision (when stakeholder-criteria are explicit and weightable) for stakeholder-mapping? Would adding scenario-planning (T6) deepen the uncertainty side when futures are highly uncertain rather than parameter-uncertain? Would adding red-team (T15) sharpen the pre-mortem when the failure mode is adversarial-actor-driven rather than structural? Consider whether the decision admits real-options structure (sequential, with information-arrival) and whether real-options-decision (gap-deferred) would be the better lead component if it existed. Breadth markers: at least one alternative compositional balance considered, the decision-maker's role and authority is explicit (because decision design depends on who can act), and the time-horizon is named because composition shifts with horizon.
    evaluation_pass: |
      Score the integrated architecture, not components in isolation. Critical questions: (CQ1) does each component meet substantive depth (uncertainty classified per variable, not generic "uncertain"; constraints mapped with tradeoff topology, not listed; stakeholder positions distinguished from interests with hypothesis-flagging; pre-mortem traces failure-to-signal, not generic risks); (CQ2) is integration load-bearing — do component findings visibly reshape each other; (CQ3) is the decision-maker (and their authority) explicit; (CQ4) is the time-horizon explicit; (CQ5) is component-of-origin provenance preserved per finding? Named failure modes (component-as-stub, four-section-concatenation, generic-uncertainty, constraint-list-without-tradeoff, position-interest-conflation, generic-pre-mortem, missing-decision-maker, provenance-collapse) are the evaluation checklist. Mandate fix when any component reads as stub, when integration is sectional, when uncertainty is asserted without classification, when constraints are listed without their tradeoff topology, when pre-mortem fails to trace failure-back-to-signals, or when component-of-origin is lost.
    revision_pass: |
      Preserve component provenance through synthesis-revision. Add depth where any component is stub. Make integration mutual where the draft concatenates. Distinguish positions from interests with hypothesis-flagging. Trace pre-mortem failure modes back to decision-time signals where the draft asserts generic risks. Resist revising toward false confidence — where the architecture surfaces irreducible uncertainty (Knightian) or genuine stakeholder opposition that no integrative move dissolves, those findings belong in the architecture, not papered over with optimistic synthesis. The mode's character is integrated decision design with component-traceability, not a recommendation that hides its premises.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full integrated architectures independently. Reference frame: union of component findings across streams (de-duplicated by finding-stem), with component-of-origin AND stream-of-origin tags preserved. Convergent findings get high-confidence flag. Divergent component-balance choices (one stream led with uncertainty, the other with stakeholders) surface as alternative architectural framings; the more decision-maker-actionable framing is preferred for the lead, the other preserved. Pre-mortem failure modes from both streams union (the more diverse failure-mode set is preserved because pre-mortem benefits from imaginative breadth). Constraint-tradeoff topologies from both streams are reconciled where they agree, surfaced as competing readings where they diverge.
    verification_pass: |
      V-DA-1: all four composed components (DUU, constraint-mapping, stakeholder-mapping, pre-mortem-action) are substantively present (not stubbed). V-DA-2: integration is load-bearing — at least three visible cross-component reshapings. V-DA-3: decision-maker and authority are explicit. V-DA-4: time-horizon is explicit. V-DA-5: uncertainties are classified per variable (risk / Knightian / deep). V-DA-6: constraints are mapped with their tradeoff topology. V-DA-7: stakeholder positions are distinguished from interests with hypothesis-flagging. V-DA-8: pre-mortem failure modes trace back to decision-time signals. V-DA-9: component-of-origin provenance visible per major finding. V-DA-10: confidence per finding accompanies every claim.
```

### T5 (new schema) — Hypothesis Evaluation (Wave 4 additions)

```yaml
bayesian-hypothesis-network:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: extended
  RAG_profile:
    relationship_priorities:
      prioritize: [composes, supports, undermines, contradicts, qualifies, requires, depends-on]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Bayesian Hypothesis Network composes a differential-diagnosis fragment + competing-hypotheses (Heuer ACH) + a Bayesian network synthesis layer. Component-source provenance is preserved: differential-diagnosis findings about the hypothesis-space inventory carry their component tag; ACH findings about evidence-hypothesis diagnosticity matrices carry theirs; Bayesian network findings about prior/posterior structure and conditional-independence assumptions carry theirs. Engram-tier articulations of the user's actual hypothesis space, evidence base, and prior beliefs dominate. Pearl/Jensen Bayesian-network method content and Heuer ACH content are method-foundational. Tetlock/Schum probability-calibration content (when invoked) supplies prior-elicitation discipline. Resource-tier base-rate and reference-class references inform priors. Incubator-tier evidence pieces with provenance notes enter as primary evidence with component-relevance and diagnosticity flagged. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Bayesian Hypothesis Network is the molecular composition of differential-diagnosis (hypothesis-space generation) + competing-hypotheses (diagnosticity assessment) + Bayesian network synthesis (probabilistic posterior over hypotheses with explicit priors and conditional dependencies). Run each substantively. (1) Differential-diagnosis fragment: generate the hypothesis space (named alternatives including the null/no-effect/most-likely-prior alternative); flag where the space may be incomplete. (2) Competing-hypotheses (Heuer ACH): build the evidence-hypothesis matrix; assess diagnosticity per evidence piece (does this evidence distinguish among hypotheses or is it consistent with all); identify the most-diagnostic and least-diagnostic evidence; note that ACH inverts the natural reasoning direction (start from evidence, ask which hypotheses it eliminates, rather than start from preferred hypothesis and ask which evidence supports it). (3) Bayesian network synthesis: elicit priors (with reference-class justification, not pulled from intuition); state the conditional-independence assumptions explicitly; compute or estimate the posterior over hypotheses; surface the posterior's sensitivity to prior choice and to conditional-independence assumptions. Integration is load-bearing: ACH diagnosticity reshapes the network's likelihood-ratio structure; differential-diagnosis completeness-flags become network-side caveats about open-world assumptions; network sensitivity-analysis reshapes ACH's confidence in the most-likely hypothesis. Component-as-section-stub or naive-Bayesian-output (pretending point-posteriors are robust when sensitivity-analysis is missing) are primary failure modes. Test depth by asking: would a sophisticated reader be able to reproduce the posterior from the matrix and the priors, and to see how the posterior would shift under different prior choices?
    breadth_pass: |
      Survey alternative compositions: would the analysis benefit from process-tracing (T4) where the hypothesis is about a historical causal sequence rather than about which-explanation-is-true? Would adding causal-DAG (T4) help where the hypotheses imply different causal structures and the network's conditional-independence assumptions need causal justification? Consider whether the hypothesis space genuinely admits Bayesian treatment (the alternatives are exhaustive and mutually exclusive at the relevant grain) or whether the problem is closer to deep uncertainty (Knightian) where Bayesian probability misleads. Scan for evidence-pieces with poor provenance that should be downweighted in the likelihood structure rather than fed in at face value. Breadth markers: at least one alternative compositional balance considered, the prior-elicitation method is explicit (reference-class, expert-elicitation, or default-uniform with rationale), and the conditional-independence assumptions are explicitly named (not implicit).
    evaluation_pass: |
      Score the integrated network, not the components in isolation. Critical questions: (CQ1) is the hypothesis space substantively generated (including a default/null/most-likely-prior alternative); (CQ2) is the evidence-hypothesis matrix complete with diagnosticity assessed per piece; (CQ3) is the network specified with priors and conditional-independence assumptions explicit; (CQ4) is the posterior accompanied by sensitivity analysis (how it shifts under different priors or different independence assumptions); (CQ5) is the posterior treated as defeasible (open-world caveat present) rather than as final; (CQ6) is component-of-origin provenance preserved? Named failure modes (component-as-stub, hypothesis-space-monoculture, diagnosticity-elision, prior-from-intuition, hidden-conditional-dependence, point-posterior-overconfidence, closed-world-overreach, provenance-collapse) are the evaluation checklist. Mandate fix when any component is stub, when the hypothesis space is too narrow, when diagnosticity is asserted without per-evidence assessment, when priors lack reference-class justification, when conditional-independence is implicit, when the posterior is presented without sensitivity analysis, or when the analysis treats the result as final-truth rather than current-best-estimate.
    revision_pass: |
      Preserve component provenance through synthesis-revision. Add depth where any component is stub. Expand the hypothesis space where the differential-diagnosis fragment was thin. Add diagnosticity assessment where ACH listed evidence without distinguishing diagnostic from neutral. Justify priors against reference classes where the draft elicited them from intuition. Make conditional-independence assumptions explicit where the draft assumed them silently. Add sensitivity analysis where the draft offered point-posteriors. Resist revising toward false precision — Bayesian probabilistic output looks rigorous but is only as good as the prior, the likelihood, and the independence structure. Where any of those is fragile, the posterior must reflect that fragility. The mode's character is calibrated probabilistic synthesis with explicit assumption-disclosure, not confident posterior-display.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full networks independently. Reference frame: union of hypothesis spaces, evidence-hypothesis matrices, prior elicitations, and conditional-independence specifications across streams (de-duplicated by hypothesis-stem and evidence-stem), with component-of-origin AND stream-of-origin tags preserved. Convergent diagnosticity assessments (both streams classified the same evidence as smoking-gun for the same hypothesis) get high-confidence flag. Divergent prior elicitations or conditional-independence specifications surface as alternative network parameterizations; both posteriors are presented; the more cautious sensitivity-analysis is preserved. The synthesized output may legitimately carry two posteriors with different prior justifications; do not silently average — disagreement among reasonable priors is a substantive finding.
    verification_pass: |
      V-BHN-1: all three composed components are substantively present (not stubbed). V-BHN-2: hypothesis space includes a default/null/prior-alternative. V-BHN-3: evidence-hypothesis matrix has diagnosticity assessed per evidence piece. V-BHN-4: priors are justified against reference classes (not intuition-elicited). V-BHN-5: conditional-independence assumptions are explicit. V-BHN-6: posterior is accompanied by sensitivity analysis under varied priors and varied independence assumptions. V-BHN-7: open-world caveat is present (the posterior is current-best, not final). V-BHN-8: component-of-origin provenance visible per major finding. V-BHN-9: confidence per finding accompanies every claim.
```

### T6 (new schema) — Future Exploration (Wave 4 additions)

```yaml
wicked-future:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: extended
  RAG_profile:
    relationship_priorities:
      prioritize: [composes, requires, enables, contradicts, qualifies, opposes, undermines]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Wicked Future composes scenario-planning + pre-mortem-action + probabilistic-forecasting; Backcasting is gap-deferred (CR-6) and the composition anchors scenario-planning's goal-directed arc on its absence (rather than substituting). Component-source provenance is preserved: scenario-planning findings about distinct future-arcs carry their component tag; pre-mortem-action findings about adversarial-future failure modes carry theirs; probabilistic-forecasting findings about likelihoods, ranges, and calibration carry theirs. Engram-tier articulations of the user's actual forward-looking question, time-horizon, and existing assumptions dominate. Schwartz/Wack scenario-planning, Klein pre-mortem, Tetlock superforecasting and Silver probabilistic-forecasting content are method-foundational. Resource-tier futures-research methods and trend-analysis references inform structure. Incubator-tier observations about specific signals, indicators, and weak signals enter as primary evidence with component-relevance flagged. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Wicked Future is the molecular composition of scenario-planning + pre-mortem-action + probabilistic-forecasting, integrated into a comprehensive forward-analysis for situations where the future admits multiple plausible arcs and the standard depth-thorough modes individually under-cover the uncertainty. Run each substantively. (1) Scenario planning: build 3-5 distinct futures (not optimistic / pessimistic / baseline — distinct in their underlying logic and in which trends dominate); name each scenario's signature dynamics, key uncertainties resolved per scenario, and observable indicators that would signal which scenario is unfolding. (2) Pre-mortem action: across the scenario set, identify the failure modes — both the internal-failure-of-the-user's-plans-within-each-scenario and the failure-of-the-scenario-set-itself (which futures are systematically excluded). (3) Probabilistic forecasting: assign probability ranges (not point probabilities) to each scenario's elements where calibration is possible; surface deep-uncertainty where it is not; identify the indicators with the highest predictive value. With Backcasting deferred, the composition explicitly notes where a constructive goal-directed scenario would belong (the absence is structural, not a defect of synthesis); scenario-planning's forward arc is anchored against its missing backward complement rather than allowed to substitute. Integration is load-bearing: pre-mortem failure-modes reshape scenario-planning by surfacing systematically-excluded futures; probabilistic-forecasting reshapes scenario-planning by weighting which scenarios warrant the most planning attention; scenario-planning reshapes probabilistic-forecasting by giving the probabilities a narrative skeleton. Generic-scenario-set or pre-mortem-as-list-of-risks are primary failure modes. Test depth by asking: would the integrated future-analysis surface a future that scenario-planning alone would have missed, and would it weight scenarios in a way scenario-planning alone would have flattened?
    breadth_pass: |
      Survey alternative compositions: would the analysis benefit from adding fragility-antifragility-audit (T7) where the future-question is about exposure-asymmetry rather than path-prediction? Would substituting consequences-and-sequel (T6 light) for probabilistic-forecasting work where the time-horizon is short and the question is about second-order effects rather than long-run probabilities? Note explicitly where Backcasting (gap-deferred) would have been the third leg if it existed — what kind of future-analysis the composition cannot perform without it (constructive goal-directed pathway-design from a desired endpoint backward to present-day moves). Consider whether the user actually wants probabilistic synthesis or qualitative scenario-set; the choice shapes which component leads. Breadth markers: at least one alternative compositional balance considered, the time-horizon is explicit, the user's intended use of the analysis (planning vs. monitoring vs. communication) is explicit, and Backcasting's absence is acknowledged where a constructive goal-pathway would have been useful.
    evaluation_pass: |
      Score the integrated future-analysis, not the components in isolation. Critical questions: (CQ1) does each component meet substantive depth (scenarios distinct in underlying logic, not just in tone; pre-mortem identifies systematic exclusions, not just risks-within-scenarios; probabilistic-forecasting offers calibrated ranges with explicit deep-uncertainty flagging where calibration fails); (CQ2) is integration load-bearing — do component findings visibly reshape each other; (CQ3) is Backcasting's absence acknowledged where it would have served; (CQ4) is the time-horizon explicit; (CQ5) is component-of-origin provenance preserved? Named failure modes (component-as-stub, generic-scenarios, pre-mortem-as-risk-list, point-probabilities-without-deep-uncertainty-flag, backcasting-substitution, missing-time-horizon, provenance-collapse) are the evaluation checklist. Mandate fix when scenarios are tone-variants rather than logic-variants, when pre-mortem becomes a risk-list, when probabilistic-forecasting offers point-probabilities without flagging deep-uncertainty regions, when scenario-planning is asked to substitute for Backcasting (constructive goal-pathway), when the time-horizon is implicit, or when component-of-origin is lost.
    revision_pass: |
      Preserve component provenance through synthesis-revision. Add depth where any component is stub. Differentiate scenarios by underlying logic where the draft offered tone-variants. Strengthen pre-mortem from risk-list to systematic-exclusion-detection. Add deep-uncertainty flags where probabilistic-forecasting offered false-precision point estimates. Acknowledge Backcasting's absence where the user wanted constructive goal-pathway-design (and surface that as a limitation rather than papering over it). Resist revising toward narrative-coherence-at-the-cost-of-genuine-divergence — the mode's character is honest forward-analysis with multiple component lenses; smoothing scenarios into a single arc is a failure mode, not a polish. Resist revising toward false probabilistic confidence in deep-uncertainty regions.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full integrated future-analyses independently. Reference frame: union of scenarios (de-duplicated by underlying-logic-stem, not by tone), pre-mortem failure modes, and probabilistic ranges across streams, with component-of-origin AND stream-of-origin tags preserved. Convergent scenarios (both streams generated the same underlying-logic future) get high-confidence flag. Divergent scenarios are preserved as alternative future-arcs in prose; do not silently choose. Pre-mortem failure modes from both streams union (the more diverse set is preserved because pre-mortem benefits from imaginative breadth). Probabilistic ranges from both streams are reconciled by widening to encompass both (more cautious is preserved) where they overlap, surfaced as competing readings where they do not. Backcasting-absence acknowledgment from either stream is preserved.
    verification_pass: |
      V-WF-1: all three composed components (scenario-planning, pre-mortem-action, probabilistic-forecasting) are substantively present (not stubbed). V-WF-2: scenarios are distinct in underlying logic (not tone-variants). V-WF-3: pre-mortem identifies systematic exclusions (not just risks-within-scenarios). V-WF-4: probabilistic-forecasting offers ranges with explicit deep-uncertainty flagging where calibration fails. V-WF-5: integration is load-bearing — at least three visible cross-component reshapings. V-WF-6: time-horizon is explicit. V-WF-7: Backcasting's absence is acknowledged where constructive goal-pathway-design would have served. V-WF-8: component-of-origin provenance visible per major finding. V-WF-9: confidence per finding accompanies every claim.
```

### T9 (new schema) — Paradigm and Assumption Examination (Wave 4 additions)

```yaml
worldview-cartography:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: extended
  RAG_profile:
    relationship_priorities:
      prioritize: [composes, contradicts, qualifies, opposes, supports, requires]
      deprioritize: [analogous-to, parent, child]
    provenance_treatment: |
      Worldview Cartography composes paradigm-suspension + frame-comparison + dialectical-analysis as the synthesis layer. Component-source provenance is preserved: paradigm-suspension findings about each worldview's bracketed assumptions and naturalized commitments carry their component tag; frame-comparison findings about systematic differences between worldviews carry theirs; dialectical-analysis findings about productive tensions, antinomies, and synthesis-or-irreducibility verdicts carry theirs. Engram-tier articulations of the user's actual paradigm-debate or worldview-comparison context dominate. Kuhn paradigm, Foucault episteme, Lakoff frame, and Hegel/Marx/Adorno dialectical content are method-foundational. Resource-tier history-of-ideas and comparative-philosophy references inform breadth. Incubator-tier observations about specific worldview-claims or impasses enter as primary evidence with component-relevance flagged. Symmetric weighting across worldviews is enforced — no worldview's source material dominates the analysis. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Worldview Cartography is the molecular composition of paradigm-suspension + frame-comparison + dialectical-analysis, integrated into a comprehensive multi-paradigm map. Run each substantively. (1) Paradigm suspension: bracket each worldview's assumptions; identify what each takes as natural, foundational, or unquestionable; surface what each would refuse to count as evidence-against-itself. (2) Frame comparison: identify the systematic differences — what each foregrounds and backgrounds, what vocabulary each uses, what each can and cannot say. The comparison must be symmetric — partisan privileging is the primary failure mode here. (3) Dialectical analysis (synthesis layer): identify productive tensions where worldviews disagree in ways that illuminate each other's blind spots; identify antinomies where they cannot agree on what counts as resolution; verdict per major tension as either provisionally synthesizable, productively-coexistent, or irreducibly opposed (forcing a choice). Integration is load-bearing: paradigm-suspension findings (what each worldview brackets) reshape frame-comparison (the comparison must address what each cannot see); frame-comparison findings (systematic divergences) reshape dialectical-analysis (which tensions are surface-disagreements vs. paradigm-deep antinomies); dialectical findings reshape paradigm-suspension by surfacing assumptions one worldview holds that another reveals as contingent. Sectional-concatenation or one-worldview-privileging are primary failure modes. Test depth by asking: would a serious adherent of each worldview recognize their position as fairly represented and would they recognize the antinomies as genuine?
    breadth_pass: |
      Survey alternative compositions: would the analysis benefit from adding boundary-critique (T2) where one worldview is structurally excluded from the conversation by the framing? Would substituting cross-domain-analogical (T12, gap-deferred) for dialectical-analysis serve where the worldviews come from incommensurable domains rather than directly opposed positions? Consider whether the worldviews under examination are genuinely paradigm-deep (Kuhnian) or merely framing-level (Goffman/Lakoff) — the depth shapes which component leads. Scan for worldviews that should be in the cartography but are not — voices systematically absent from the canonical comparison the user has framed. Breadth markers: at least three worldviews in the cartography (not binary), at least one absent voice surfaced or its absence justified, the symmetric-weighting commitment is explicit, and the user's stake (whether they are inside one worldview, outside all, or trying to choose) is named.
    evaluation_pass: |
      Score the integrated cartography, not the components in isolation. Critical questions: (CQ1) does each component meet substantive depth (paradigm-suspension brackets each worldview's deep assumptions, not surface positions; frame-comparison is symmetric; dialectical-analysis distinguishes synthesizable / coexistent / irreducibly-opposed verdicts); (CQ2) is integration load-bearing — do component findings visibly reshape each other; (CQ3) is the cartography genuinely multi-paradigm (3+) rather than binary; (CQ4) is symmetric weighting honored; (CQ5) is each worldview's serious adherent's-eye view present; (CQ6) is component-of-origin provenance preserved? Named failure modes (component-as-stub, partisan-privileging, binary-framing, surface-comparison-only, false-synthesis-overreach, irreducibility-elision, missing-voices, provenance-collapse) are the evaluation checklist. Mandate fix when paradigm-suspension is performed only on the worldviews-the-author-disagrees-with, when frame-comparison is asymmetric, when dialectical-analysis silently synthesizes irreducibly-opposed positions, when the cartography is binary, when serious adherents would not recognize their view, or when component-of-origin is lost.
    revision_pass: |
      Preserve component provenance through synthesis-revision. Add depth where any component is stub. Restore symmetric weighting where the draft privileged one worldview. Surface deep assumptions where paradigm-suspension stayed at surface positions. Distinguish synthesizable from irreducibly-opposed in dialectical findings where the draft conflated them. Acknowledge irreducibility where the draft synthesized for tidiness. Resist revising toward consensus or toward authorial-sympathy with one position — the mode's character is fair multi-paradigm cartography with honest synthesis-or-coexistence-or-irreducibility verdicts; smoothing toward consensus is a failure mode, not a polish. The user's stake should be acknowledged but should not bias the cartography.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full cartographies independently. Reference frame: union of identified worldviews, bracketed assumptions, frame-differences, and dialectical verdicts across streams (de-duplicated by worldview-stem and tension-stem), with component-of-origin AND stream-of-origin tags preserved. Convergent paradigm-suspension findings (both streams identified the same naturalized assumption in the same worldview) get high-confidence flag. Divergent dialectical verdicts (one stream synthesized a tension the other called irreducibly-opposed) surface as alternative verdicts in prose; do not silently choose — the disagreement among streams about synthesizability is itself a substantive finding. Symmetric-weighting commitment from the more rigorous stream is preserved. Voices identified as systematically-absent from either stream are unioned.
    verification_pass: |
      V-WC-1: all three composed components (paradigm-suspension, frame-comparison, dialectical-analysis) are substantively present (not stubbed). V-WC-2: cartography is multi-paradigm (3+ worldviews), not binary. V-WC-3: symmetric weighting is honored across worldviews. V-WC-4: paradigm-suspension reaches deep assumptions (not surface positions). V-WC-5: dialectical verdicts distinguish synthesizable / productively-coexistent / irreducibly-opposed. V-WC-6: serious adherents of each worldview would recognize the representation as fair. V-WC-7: integration is load-bearing — at least three visible cross-component reshapings. V-WC-8: component-of-origin provenance visible per major finding. V-WC-9: voices systematically absent from the canonical comparison are surfaced or their absence is justified. V-WC-10: confidence per finding accompanies every claim.
```

### T14 (new schema) — Orientation in Unfamiliar Territory (Wave 4 additions)

```yaml
domain-induction:
  gear: 4
  expected_runtime: ~10+min
  type_filter: [engram, resource, incubator]
  context_budget: extended
  RAG_profile:
    relationship_priorities:
      prioritize: [composes, contains, requires, depends-on, qualifies, precedes]
      deprioritize: [analogous-to, supersedes]
    provenance_treatment: |
      Domain Induction composes a quick-orientation fragment + terrain-mapping + structured-induction as the synthesis layer. Component-source provenance is preserved: quick-orientation findings about the domain's name, scope, and key handles carry their component tag; terrain-mapping findings about the domain's structure (clusters, boundaries, controversies, central-vs-peripheral concepts) carry theirs; structured-induction synthesis findings about ordered-learning-pathways, dependency relations, and entry-points carry theirs. Engram-tier articulations of the user's actual learning context, prior knowledge, and intended use of the domain dominate. Resource-tier domain references (canonical introductions, reviews, textbooks) inform terrain. Incubator-tier observations about specific texts, practitioners, or concepts the user has encountered enter as primary evidence with component-relevance flagged. The Tier-3 mental model literature (where applicable to the domain) supplies organizing scaffolds. P1/P2 over P3-P6; conflicts surfaced rather than averaged.
  instructions:
    depth_pass: |
      Domain Induction is the molecular composition of quick-orientation (light handles) + terrain-mapping (structural map) + structured-induction synthesis (ordered learning pathway), integrated into a comprehensive structured-introduction for a user new to the domain. Run each substantively. (1) Quick-orientation fragment: name the domain, its scope, the questions it answers, the questions it does not answer, the major neighboring domains. (2) Terrain mapping: chart the domain's internal structure — sub-clusters, central-vs-peripheral concepts, live controversies, methodological camps, foundational texts/figures, and the boundary with neighboring domains. (3) Structured-induction synthesis: produce an ordered learning pathway — what the user must understand before what, which concepts are foundational vs. specialized, where the high-leverage entry points are, what warning-signs of confusion to expect at each stage. Integration is load-bearing: terrain-mapping findings (what the domain's controversies are) reshape the induction pathway (controversies should be flagged at the right learning-stage, not encountered cold); quick-orientation findings (what the user's neighbors-domain prior knowledge enables) reshape terrain-mapping (the user's existing handles become anchor points for new concepts); induction-pathway findings reshape quick-orientation by surfacing prerequisite-domain knowledge the user must acquire before starting. Component-as-stub or pathway-without-terrain (linear reading-list-as-induction) are primary failure modes. Test depth by asking: could a user follow the induction pathway and arrive at functional literacy in the domain, including knowing where the live controversies are and which texts represent which methodological camp?
    breadth_pass: |
      Survey alternative compositions: would the analysis benefit from substituting cross-domain-analogical (T12, gap-deferred) for parts of structured-induction where the user's strongest learning leverage comes from analogies to a domain they already know? Would adding paradigm-suspension (T9) help where the domain has paradigm-deep splits the user must navigate (as opposed to controversies within a shared paradigm)? Consider the user's intended use — practitioner-introduction, evaluator-introduction (the user will need to assess work in this domain without becoming a practitioner), or generalist-introduction (the user wants enough literacy to read and discuss). The intended use shapes which terrain-elements get surfaced. Scan for the domain's tacit knowledge (the things practitioners know but rarely write down explicitly) — this is the most-likely-omitted element and the one most-likely-to-cause-confusion if missed. Breadth markers: at least one alternative compositional balance considered, the user's intended use is explicit, the user's prior knowledge is mapped, the domain's tacit-knowledge dimension is acknowledged, and entry-point alternatives (multiple possible starts) are considered.
    evaluation_pass: |
      Score the integrated induction, not the components in isolation. Critical questions: (CQ1) does each component meet substantive depth (quick-orientation actually orients, not just labels; terrain-mapping shows the domain's structure including controversies and methodological camps; induction synthesis offers ordered pathway with prerequisite-and-leverage logic, not a reading list); (CQ2) is integration load-bearing — do component findings visibly reshape each other; (CQ3) is the user's intended use explicit; (CQ4) is the user's prior knowledge accommodated; (CQ5) is the domain's tacit-knowledge dimension acknowledged; (CQ6) is component-of-origin provenance preserved? Named failure modes (component-as-stub, label-without-orientation, terrain-without-controversies, pathway-as-reading-list, missing-intended-use, prior-knowledge-flatness, tacit-knowledge-elision, provenance-collapse) are the evaluation checklist. Mandate fix when quick-orientation lists names without explaining what the domain does, when terrain-mapping omits controversies or methodological camps, when the induction pathway is a linear reading-list without prerequisite-and-leverage logic, when intended-use is implicit, when prior knowledge is treated as zero, when tacit knowledge is unacknowledged, or when component-of-origin is lost.
    revision_pass: |
      Preserve component provenance through synthesis-revision. Add depth where any component is stub. Restore controversies and methodological camps where terrain-mapping flattened. Convert the induction pathway from reading-list to prerequisite-and-leverage-ordered structure where the draft listed texts. Acknowledge tacit knowledge where the draft elided it. Accommodate the user's prior knowledge where the draft treated them as a blank slate. Resist revising toward false-completeness — a domain induction that promises mastery in a single pass is misrepresenting both the domain and the induction; honest acknowledgment of where the user will still be lost after this induction (and what to do next) is part of the mode's character. Resist revising toward author-domain-bias where the author's familiarity with one sub-cluster overweights it.
    consolidation_pass: |
      At Gear 4, both parallel streams produce full inductions independently. Reference frame: union of orientation handles, terrain-features (sub-clusters, controversies, methodological camps), and induction-pathway-elements across streams (de-duplicated by feature-stem and pathway-step-stem), with component-of-origin AND stream-of-origin tags preserved. Convergent terrain-features (both streams identified the same controversy as load-bearing) get high-confidence flag. Divergent entry-point recommendations (one stream led with foundational text, the other with practical exercise) surface as alternative pathways in prose; both are preserved as legitimate entry-point alternatives. Tacit-knowledge identifications from both streams union (the more comprehensive set is preserved). Where streams diverged on which sub-cluster is central vs. peripheral, the divergence itself is a finding about the domain's contested centering and is preserved.
    verification_pass: |
      V-DI-1: all three composed components (quick-orientation, terrain-mapping, structured-induction) are substantively present (not stubbed). V-DI-2: terrain-mapping includes controversies AND methodological camps (not just topics). V-DI-3: induction pathway is structured by prerequisite-and-leverage logic (not a linear reading-list). V-DI-4: user's intended use is explicit. V-DI-5: user's prior knowledge is mapped. V-DI-6: tacit-knowledge dimension is acknowledged (or marked not-applicable for the domain). V-DI-7: integration is load-bearing — at least three visible cross-component reshapings. V-DI-8: component-of-origin provenance visible per major finding. V-DI-9: at least one alternative entry-point is offered or its absence is justified. V-DI-10: confidence per finding accompanies every claim.
```

---

## Verification Rule

Every `mode_id` present in `Modes/` MUST have a runtime config entry in this file. The verification script enforces this — orchestrator boot fails if a mode file has no matching runtime entry, and a runtime entry without a corresponding mode file emits a warning. The `systems-dynamics.md` source file maps to TWO entries (`systems-dynamics-causal` in T4 and `systems-dynamics-structural` in T17); Phase 2 will properly parse the source content into the two parsed mode files. The `wicked-problems` placeholder here precedes its mode file; Phase 2 will author the corresponding mode spec and enrich this runtime entry to match. The `decision-clarity` placeholder was upgraded to its full molecular-mode entry on 2026-05-01 (Wave 4).

*End of Reference — Mode Runtime Configuration.*
