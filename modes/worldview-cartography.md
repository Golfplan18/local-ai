---
nexus:
  - ora
type: mode
tags:
  - molecular
date created: 2026-05-01
date modified: 2026-05-24

---

# MODE: Worldview Cartography

```yaml
# 0. IDENTITY
mode_id: worldview-cartography
canonical_name: Worldview Cartography
suffix_rule: analysis
educational_name: worldview cartography (multi-paradigm comparison and synthesis)

# 1. TERRITORY AND POSITION
territory: T9-paradigm-and-assumption-examination
gradation_position:
  axis: stance
  value: comparing-and-synthesizing
  depth_axis_value: molecular
adjacent_modes_in_territory:
  - mode_id: paradigm-suspension
    relationship: stance-suspending sibling (light atomic)
  - mode_id: frame-comparison
    relationship: stance-comparing sibling (thorough atomic)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "multiple worldviews are in play and I want to map the whole landscape"
    - "the disagreement is not within a frame, it's across paradigms, and I need a cartography"
    - "I want to see where paradigms cohere, where they diverge, and where they irreducibly conflict"
    - "willing to spend the time on a full multi-paradigm synthesis"
  prompt_shape_signals:
    - "worldview cartography"
    - "multi-paradigm map"
    - "compare and integrate paradigms"
    - "cross-paradigm tensions"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user wants integrated cartography spanning paradigm-suspension + frame-comparison + dialectical synthesis"
    - "user willing to spend 10+ minutes for full molecular pass"
  routes_away_when:
    - "want to suspend a single dominant frame to see what it hides" → paradigm-suspension
    - "want to compare two specific frames without dialectical synthesis" → frame-comparison
    - "the question is really within a single frame, evaluating an argument" → T1 modes
when_not_to_invoke:
  - "User has time pressure" → frame-comparison or paradigm-suspension
  - "User is producing an integrated synthesis across domains rather than examining paradigms" → synthesis (T12) or dialectical-analysis (T12)

# 3. EXECUTION STRUCTURE
composition: molecular
molecular_spec:
  components:
    - mode_id: paradigm-suspension
      runs: full
    - mode_id: frame-comparison
      runs: full
    - mode_id: dialectical-analysis
      runs: full
      conditional: "always; serves as synthesis stage rather than peer component"
  synthesis_stages:
    - name: paradigm-inventory
      type: parallel-merge
      input: [paradigm-suspension, frame-comparison]
      output: "consolidated paradigm inventory: each worldview named, suspended, and comparatively positioned with its dominant claims, hidden assumptions, and characteristic blindspots"
    - name: cross-paradigm-tension-surfacing
      type: contradiction-surfacing
      input: [paradigm-inventory]
      output: "explicit cross-paradigm tensions named: where paradigms make incompatible claims, where they speak past each other, where they share unrecognized common ground"
    - name: dialectical-cartography
      type: dialectical-resolution
      input: [paradigm-inventory, cross-paradigm-tension-surfacing, dialectical-analysis]
      output: "cartography of competing worldviews: synthetic positions where dialectical resolution is possible, residual incommensurabilities where it is not, and meta-level reflection on what the cartography itself reveals about the problem space"
  partial_composition_handling:
    on_component_failure: proceed-with-gap
    on_low_confidence: flag affected synthesis stage; do not aggregate over low-confidence paradigm characterizations

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [problem_or_debate, paradigm_inventory]
    optional: [prior_frame_analyses, paradigm_genealogies]
    notes: "Applies when user supplies named paradigms or prior frame analyses."
  accessible_mode:
    required: [problem_or_debate]
    optional: [contextual_background]
    notes: "Default. Mode elicits paradigm inventory during execution."
  detection:
    expert_signals: ["paradigms include", "frames are", "worldviews", "Kuhn", "Foucault"]
    accessible_signals: ["different worldviews", "they're talking past each other", "fundamental disagreement"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What's the problem or debate, and what worldviews or paradigms do you see in play?'"
    on_underspecified: "Ask the user whether they want the full Worldview Cartography molecular pass or a lighter Frame Comparison / Paradigm Suspension read."
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has each paradigm been suspended (its assumptions surfaced) before being compared, or has the analysis evaluated paradigms from inside one of them?"
    failure_mode_if_unmet: home-paradigm-bias
  - cq_id: CQ2
    question: "Are cross-paradigm tensions named explicitly, or has the cartography smoothed over genuine incommensurability?"
    failure_mode_if_unmet: tension-collapse
  - cq_id: CQ3
    question: "Where dialectical synthesis is offered, is it grounded in the paradigms' own terms, or is it a meta-paradigm imposed from outside?"
    failure_mode_if_unmet: meta-paradigm-imposition
  - cq_id: CQ4
    question: "Are residual incommensurabilities preserved as such, or has the synthesis prematurely resolved them into a unified picture?"
    failure_mode_if_unmet: premature-resolution

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: home-paradigm-bias
    detection_signal: "All paradigms evaluated against criteria from one of them; that paradigm's assumptions remain unsurfaced."
    correction_protocol: re-dispatch (with explicit paradigm-suspension on the home paradigm)
  - name: tension-collapse
    detection_signal: "Cross-paradigm-tensions section is short or absent; output presents paradigms as complementary."
    correction_protocol: re-dispatch
  - name: meta-paradigm-imposition
    detection_signal: "Synthetic positions use vocabulary or criteria that none of the surveyed paradigms would accept."
    correction_protocol: flag and re-dispatch
  - name: premature-resolution
    detection_signal: "Output presents a unified worldview without naming residual incommensurabilities."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required:
    - kuhn-paradigm-incommensurability
  optional:
    - foucault-discursive-formation
    - rorty-final-vocabulary
    - macintyre-traditions-of-inquiry
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 3
expected_runtime: ~10+min
escalation_signals:
  upward:
    target_mode_id: null
    when: "Worldview Cartography is the heaviest mode in T9."
  sideways:
    target_mode_id: null
    when: "No within-T9 stance/complexity sibling beyond the depth ladder."
  downward:
    target_mode_id: frame-comparison
    when: "User has time pressure; thorough comparison without dialectical synthesis suffices."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Worldview Cartography is the degree to which the dialectical-cartography stage produces synthetic positions and identified incommensurabilities that no single paradigm-suspension or frame-comparison pass could have produced. A thin molecular pass enumerates paradigms and lists their differences; a substantive pass surfaces cross-paradigm tensions, attempts dialectical resolution where possible (in the paradigms' own terms), and explicitly names where resolution fails. Test depth by asking: does the cartography contain claims that hold *across* paradigms while remaining recognizable to each?

## BREADTH ANALYSIS GUIDANCE

Breadth in Worldview Cartography is the catalog of paradigms surveyed before the cartography narrows to its core comparison. Widen the lens to scan: dominant-tradition paradigm; minority-tradition paradigm; cross-cultural paradigm; historical-genealogy paradigm; reflexive paradigm (one that explicitly thematizes paradigm-comparison itself, e.g. Kuhnian or Foucauldian). Even when only 3–4 paradigms are dialectically engaged, breadth is documented in the inventory.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Worldview Cartography is a depth-molecular, comparing-and-synthesizing T9 mode that composes paradigm-suspension (full), frame-comparison (full), and dialectical-analysis (synthesis stage) into an integrated multi-paradigm cartography. Read in Kuhn paradigm-incommensurability vocabulary first, with Foucault discursive-formation, Rorty final-vocabulary, and MacIntyre traditions-of-inquiry available where the paradigms invite them. The mode is distinct from paradigm-suspension (T9 light atomic — suspend a single dominant frame to see what it hides), frame-comparison (T9 thorough atomic — compare two specific frames without dialectical synthesis), and synthesis (T12 — integrative synthesis across domains rather than examining paradigms). The central commitment is Kuhn-grounded: paradigms can be genuinely untranslatable; the analyst's home paradigm is itself a paradigm to suspend.

**Procedure.**

1. State the problem or debate once at the corpus head.
2. Inventory paradigms (at least three) — name each with tradition/lineage; one must be the analyst's home paradigm, acknowledged as such.
3. Suspend each paradigm symmetrically — surface assumptions, hidden commitments, characteristic blindspots, **own-terms vocabulary** (the specific terms each paradigm uses for its load-bearing concepts). The home paradigm is suspended to at least the same depth as foreign paradigms.
4. Acknowledge the home paradigm explicitly with the structural reason it's the home paradigm (training, domain, dominant-discourse exposure) — non-negotiable; home-paradigm-bias is the named failure mode without it.
5. Name cross-paradigm tensions explicitly — each tension carries paradigm-A's claim, paradigm-B's claim, tension type (incompatible-claims / talking-past-each-other / shared-unrecognized-common-ground), and structural reason. Complementarity language without grounded specificity is tension-collapse.
6. Offer dialectical synthesis where possible — each synthesis claim stated in vocabulary the surveyed paradigms would accept, drawn from step 3's own-terms lists. Apply the own-terms test: would each paradigm accept this vocabulary?
7. Migrate failed-own-terms-test syntheses to imposed-meta-paradigm flag section — do not pass them through as syntheses.
8. Preserve residual incommensurabilities — each naming the specific concept, why translation fails (Kuhn-grounded: same word different concepts / different words same concept / different success criteria), and what is lost if either paradigm is silenced. Never resolve toward unified worldview.
9. Produce meta-level reflection — what the cartography itself reveals about the problem space (typically: the problem is paradigm-dependent in its very statement, or the apparent disagreement is at one paradigmatic level but the deeper question is elsewhere).
10. Assign confidence per paradigm characterization and per tension atom; synthesis-stage atoms inherit lower confidence from component aggregation.

**Goal.** Produce a structured cartography of paradigms — suspended-paradigm blocks with own-terms vocabulary preserved, cross-paradigm tensions named, own-terms-grounded syntheses where possible, residual incommensurabilities preserved as findings, and meta-level reflection on the problem space.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — symmetric suspension (load-bearing).** Has each paradigm been suspended (its assumptions surfaced) to the same depth, including the analyst's home paradigm? Failure mode if unmet: `home-paradigm-bias`.
- **CQ2 — cross-paradigm tensions named (load-bearing).** Are cross-paradigm tensions named explicitly, or has the cartography smoothed over genuine incommensurability? Failure mode if unmet: `tension-collapse`.
- **CQ3 — own-terms test on synthesis (load-bearing).** Where dialectical synthesis is offered, is it grounded in the paradigms' own terms, or is it a meta-paradigm imposed from outside? Failure mode if unmet: `meta-paradigm-imposition`.
- **CQ4 — residual incommensurabilities preserved (load-bearing).** Are residual incommensurabilities preserved as such, or has the synthesis prematurely resolved them into a unified picture? Failure mode if unmet: `premature-resolution`.

All four CQs are load-bearing — the methodology fails at any of them. A passing output suspends at least three paradigms (including a marked home paradigm) to equal depth with own-terms vocabulary preserved verbatim, names cross-paradigm tensions with explicit structural reasons, restricts syntheses to own-terms vocabulary from the surveyed paradigms, preserves Kuhn-grounded incommensurabilities as findings rather than failures, and produces meta-level reflection on what the cartography itself reveals.

**Named failure modes.**

- *home-paradigm-bias* — all paradigms evaluated against criteria from one of them; that paradigm's assumptions remain unsurfaced.
- *tension-collapse* — cross-paradigm-tensions section is short or absent; output presents paradigms as complementary without grounded specificity.
- *meta-paradigm-imposition* — synthetic positions use vocabulary or criteria that none of the surveyed paradigms would accept ("from a higher-level perspective", "transcending these views").
- *premature-resolution* — output presents a unified worldview without naming residual incommensurabilities.

## REVISION GUIDANCE

Revise to deepen synthesis where it concatenates paradigm summaries. Revise to surface tensions where the draft has resolved them prematurely. Resist revising toward a clean unified worldview — Worldview Cartography honors irreducible plurality where it exists; collapsing incommensurabilities is a failure mode, not a polish. Resist revising toward home-paradigm bias when the analyst's own paradigm slips in unsuspended.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **suspended-paradigm atoms with their own-terms vocabulary preserved, cross-paradigm-tension atoms, paradigm-grounded synthesis atoms (where possible), and residual-incommensurability atoms (where not)**. Kuhn paradigm-incommensurability is the load-bearing lens — the corpus honors that paradigms can be genuinely untranslatable, and the analyst's home paradigm is itself a paradigm to be suspended. The atoms are:

1. **Problem-or-debate atom.** The problem or debate the cartography addresses, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical statement.

2. **Paradigm atoms — each suspended.** Each paradigm carries: paradigm name, dominant claims about the problem, hidden assumptions (surfaced via paradigm-suspension), characteristic blindspots, **own-terms vocabulary** (the specific terms the paradigm uses for its load-bearing concepts), and traceable tradition or lineage. The own-terms vocabulary is operative — it's what distinguishes a Kuhnian suspension from a translation. At least three paradigm atoms must survive cross-stream dedup; one of them must be the analyst's home paradigm (acknowledged as such, not invisibly normative).

3. **Home-paradigm acknowledgment atom.** A single corpus-level atom names which paradigm the analyst started from, with the structural reason it's the home paradigm (training, domain, dominant-discourse exposure). Home-paradigm-bias is the named failure mode; corpus that suspends only foreign paradigms while leaving the analyst's own unsurfaced is its signature. The home-paradigm atom is load-bearing — without it, the suspension is asymmetric.

4. **Cross-paradigm tension atoms.** Each names a specific tension between two paradigms, with: paradigm-A's claim, paradigm-B's claim, tension type (incompatible-claims / talking-past-each-other / shared-unrecognized-common-ground), and the structural reason for the tension. Tension-collapse is the named failure mode; corpus rendering paradigms as complementary without naming where they actually conflict is its signature. At minimum one tension atom per pair of compared paradigms must survive when genuine incompatibility exists.

5. **Dialectical-synthesis atoms — in own-terms only.** Where synthesis is possible, each atom carries: which paradigms it integrates, the synthesized claim, and a **own-terms test** — the synthesis is stated using vocabulary the surveyed paradigms would accept, not in a meta-vocabulary external to them. Meta-paradigm-imposition is the named failure mode; synthetic positions using vocabulary or criteria none of the paradigms would accept are its corpus signature. A synthesis atom that fails the own-terms test does not survive — it migrates to "synthesis-attempted-but-imposes-meta-paradigm" with the imposition called out.

6. **Residual-incommensurability atoms.** Each names a place where Kuhn-grounded incommensurability obtains: paradigm-A and paradigm-B cannot be synthesized because they use the same word for different concepts, or different words for the same concept, or measure success by criteria the other paradigm does not recognize. The atom carries: the specific concept or claim, why translation fails, and what's lost if either paradigm is silenced. Premature-resolution is the named failure mode; corpus that unifies paradigms by silently abandoning irreducibilities is its signature. The corpus preserves residual incommensurabilities as findings, not as failures.

7. **Meta-level reflection atom.** A single corpus-level atom names what the cartography itself reveals about the problem space — typically that the problem is paradigm-dependent in its very statement (what counts as the problem depends on which paradigm one inhabits), or that the apparent disagreement is at one paradigmatic level but the deeper question is something else. The meta-reflection is operative content, not decoration; it gives the user a vantage on why the paradigm-comparison was necessary.

8. **Confidence map per paradigm and per tension.** Confidence markers attach to paradigm characterizations (how well-suspended each paradigm is) and to tension atoms (how clearly the incompatibility is named). When the two streams assigned different confidences, audit conservatism applies.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Foreign-paradigm-only suspension** — paradigm atoms for opposing views fully suspended while the analyst's home paradigm appears as natural framing. Home-paradigm-bias residue; the corpus carries home-paradigm-acknowledgment atom and the home paradigm is suspended at least to the same depth as the foreign ones.
- **Complementarity language** — phrases like "the paradigms complement each other", "they offer different but compatible perspectives". Tension-collapse residue; if the paradigms genuinely complement at a specific point, the synthesis atom carries that with own-terms grounding; if complementarity is asserted without grounding, it's bloat.
- **Meta-vocabulary residue** — synthesis statements using terms like "from a higher-level perspective", "synthesizing across these views", "integrating both insights" in vocabulary external to the paradigms. Meta-paradigm-imposition residue; the corpus either restates in own-terms or migrates to imposed-meta-paradigm flag.
- **Translation-as-equivalence** — claims that paradigm-A's concept X is "the same as" paradigm-B's concept Y when Kuhn-grounded incommensurability obtains. Premature-resolution residue at the concept level; the corpus preserves the apparent translation as either a residual-incommensurability atom (Kuhn translation-failure) or an explicit "approximate-translation with reservations" atom.
- **Unified-worldview residue** — phrases that present the cartography as having produced one integrated worldview ("the synthesis shows that..."). Premature-resolution residue; the cartography preserves plurality where it exists.
- **Paradigm-summary concatenation** — paradigms enumerated with their dominant claims listed in parallel, without cross-paradigm tensions, syntheses, or incommensurabilities. Concatenation residue; the corpus's value is in the inter-paradigm atoms (items 4, 5, 6), not in the paradigm enumeration alone.

**What NOT to collapse:**

- **Genuine residual incommensurability** — never resolve Kuhn-grounded incommensurabilities during consolidation. The incommensurabilities are the load-bearing finding; silent resolution toward a unified worldview is the methodology's signature failure.
- **Paradigm-vocabulary divergence for the same concept** — when paradigms use different words for what appears to be the same concept (or the same word for different concepts), preserve both vocabularies in the paradigm atoms. The vocabulary divergence is often itself a signal of where translation fails.
- **Home-paradigm-disagreement** — when the streams disagreed on which paradigm is the analyst's home paradigm (or whether one paradigm is dominant in the user's framing), preserve the disagreement. The disagreement may reveal that the home paradigm is itself contested, which is consequential for whose suspension counts as load-bearing.
- **Synthesis-vs-incommensurability disagreement** — when one stream produced a dialectical synthesis for a pair of paradigms and the other declared incommensurability, preserve both as a tension atom. The disagreement reveals that the synthesis is at the edge of own-terms feasibility; the consolidator must not silently pick.

## VERIFICATION CRITERIA

Verified means: each paradigm has been suspended (not just foreign ones); cross-paradigm tensions are named explicitly; dialectical synthesis (where offered) uses the paradigms' own terms; residual incommensurabilities are preserved; confidence map is populated. The four critical questions are addressed in the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **structured cartography of paradigms: suspended-paradigm blocks with own-terms vocabulary preserved, cross-paradigm tensions, own-terms-grounded syntheses where possible, residual incommensurabilities preserved, and meta-level reflection**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Problem or debate.** One paragraph stating what the cartography addresses.

2. **Paradigm inventory — each suspended.** For each paradigm P1, P2, P3, …, render an H3 sub-section:
   - **Paradigm name** — tradition / lineage
   - **Dominant claims about the problem:** numbered list
   - **Hidden assumptions (surfaced by suspension):** numbered list
   - **Characteristic blindspots:** numbered list
   - **Own-terms vocabulary:** the specific terms this paradigm uses for its load-bearing concepts (list them verbatim — they will appear in cross-paradigm tension and synthesis sections)

   At minimum three paradigm blocks. One must be the analyst's home paradigm, marked: `**[home paradigm — see section 3]**`.

3. **Home-paradigm acknowledgment.** A single block: `**Home paradigm: P_n.** Structural reason it is the home paradigm: [training / domain / dominant-discourse exposure / etc.]. Its assumptions are surfaced in section 2 to the same depth as the foreign paradigms.` Home-paradigm-bias is the named failure mode; this section is non-negotiable.

4. **Per-paradigm dominant claims and blindspots.** A summary table or per-paradigm one-paragraph block recapping (without re-elaborating) what was surfaced in section 2 — for cross-paradigm reference during sections 5–7.

5. **Cross-paradigm tensions.** Numbered list. Each tension: `**[Tension name]** — P_n claims: [...]. P_m claims: [...]. Tension type: [incompatible-claims / talking-past-each-other / shared-unrecognized-common-ground]. Structural reason: [...].` Tension-collapse is the named failure mode; corpus rendering paradigms as complementary without naming where they actually conflict is its signature.

6. **Dialectical synthesis where possible — in own-terms only.** Bulleted list of synthesis points (when any exist). Each: `**[Synthesis point]** — which paradigms it integrates: [P_n, P_m, ...]. Synthesized claim in own-terms: [the claim stated using vocabulary from sections 2's own-terms-vocabulary lists, not from external meta-vocabulary]. Own-terms test confirmed: [which paradigms would accept this vocabulary; meta-paradigm imposition averted because [...]].` Syntheses that fail the own-terms test do not appear here — they migrate to section 8 as imposed-meta-paradigm flags.

7. **Residual incommensurabilities — never resolved.** Numbered list. Each incommensurability: `**[Concept or claim]** — why translation fails: [Kuhn-grounded reason: same word different concepts / different words same concept / different success criteria]. What is lost if [paradigm X is silenced]: [what gets erased]. What is lost if [paradigm Y is silenced]: [what gets erased].` Premature-resolution is the named failure mode; corpus unifying paradigms by silently abandoning irreducibilities is its signature.

8. **Imposed-meta-paradigm flags (when applicable).** Bulleted list of synthesis attempts that failed the own-terms test (rejected from section 6). Each: `**[Attempted synthesis]** — meta-vocabulary used: [...]. Why none of the paradigms would accept it: [...].` When no such attempts surface, write "No meta-paradigm impositions surfaced in this cartography."

9. **Meta-level reflection.** A single paragraph stating what the cartography itself reveals about the problem space — typically that the problem is paradigm-dependent in its very statement, or that the apparent disagreement is at one paradigmatic level but the deeper question is something else. The reflection is operative content, giving the user a vantage on why the paradigm-comparison was necessary.

10. **Confidence map per paradigm and per tension.** Bulleted list. Confidence markers attach to paradigm characterizations (how well-suspended each paradigm is) and to tension atoms (how clearly the incompatibility is named).

**Per-section conventions:**

- Use H2 headings for sections 1 through 10.
- Paradigm IDs (P1, P2, …) are referenced consistently throughout once introduced; the home-paradigm tag is repeated wherever the home paradigm is named.
- Section 2's own-terms vocabulary lists are operative — they appear verbatim in cross-paradigm tension and synthesis sections.
- Avoid meta-vocabulary throughout the deliverable: phrases like "from a higher-level perspective", "transcending these views", "integrating both insights" are forbidden — meta-paradigm-imposition is the named failure mode.
- Avoid unified-worldview residue: the cartography preserves plurality where it exists.


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

**Prioritize:** `contradicts`, `qualifies`, `analogous-to`, `extends`, `supersedes`
**Deprioritize:** `precedes`, `produces`

*Family: frame-paradigm. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
