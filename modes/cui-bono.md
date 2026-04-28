---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
---

# MODE: Cui Bono

## TRIGGER CONDITIONS

Positive:
1. Policy analysis; institutional behaviour analysis; "who benefits".
2. Numerical targets or technical standards presented as objective.
3. OPV output reveals stakeholder positions correlated with institutional interests.
4. Positions or policies embedding distributional choices beneath technical language.
5. Request language: "who gains from X", "trace the interests", "what does the institution want from this", "cui bono".

Negative:
- IF the user questions the **evidential** basis of a paradigm → **Paradigm Suspension** (CB traces interests, not evidence).
- IF the user wants to evaluate alternatives without tracing institutional interests → **Constraint Mapping**.

Tiebreakers:
- CB vs Paradigm Suspension: **whose interests does this serve** → CB; **is the foundation sound** → PS.

## EPISTEMOLOGICAL POSTURE

Institutional consensus is data about what institutions have chosen to believe, not evidence of correctness. Numerical targets, technical standards, and regulatory frameworks are political artefacts — they embed value judgements and distributional choices presented as objective. Every position has an author, every author a constituency, every constituency interests. This mode traces those interests without assuming bad faith — institutional behaviour follows institutional incentives, which is structural, not conspiratorial.

## DEFAULT GEAR

Gear 4. Independent analysis is the minimum. The Depth model traces institutional incentives while the Breadth model constructs the alternative from opposite interests. Anchoring compromises the convergence/divergence diagnostic.

## RAG PROFILE

**Retrieve (prioritise):** political economy analysis, institutional incentive studies, distributional impact research, regulatory history, public choice theory, critiques of institutional positions, the institution's stated rationale.

**Deprioritise:** technical literature that presents institutional choices as objective findings.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `enables`, `produces`, `requires`, `contradicts`
**Deprioritise:** `analogous-to`, `parent`, `child`
**Rationale:** Incentive analysis tracks what enables outcomes, what produces benefits, and what constraints actors face.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The position / standard / target under analysis |
| `conversation_rag` | Prior turns' authorship + constituency mappings |
| `concept_rag` | FGL (Fear, Greed, Laziness), public choice theory |
| `relationship_rag` | Institutional entities linked by `enables`/`produces` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Identify the institutional author(s) of the position. **Becomes the source node in a flowchart OR a hierarchy_level 0 concept in a concept_map.**
2. Document the stated rationale.
3. Map the actual distributional impact. **Flow: author → mechanism → beneficiary / loser.**
4. Identify the numerical parameters or definitional choices that drive the distributional outcome.

Black Hat:
1. Assess whether the distributional impact is consistent with the stated purpose.
2. Identify which constituencies' interests are served by the specific parameters chosen.
3. Evaluate the Breadth model's alternative for internal consistency — does it genuinely represent opposite interests?

### Cascade — what to leave for the evaluator

- Open with the literal label `Institutional author:` naming the author organisation. Supports M1 and C1.
- For each parameter driving distribution, use the literal label `Parameter:` with the value and the population it affects. Supports M2 and C3.
- In the Flowchart DSL, include subgraphs named `Authors`, `Beneficiaries`, and `Bears cost` as separators. Supports S10.
- Apply FGL (Fear, Greed, Laziness) explicitly with the literal labels `Fear:`, `Greed:`, `Laziness:` per constituency. Supports M4.

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Depth traces author-to-beneficiary flow; Breadth constructs the alternative from opposite constituency.

- **Reference frame for the envelope:** Depth's author-to-beneficiary flowchart (or concept map) is canonical. Breadth's alternative-constituency mapping is emitted as a separate prose section "Alternative design from opposite constituency" — NOT emitted as a second envelope; preserve the "one envelope per turn" invariant.
- **FGL reconciliation:** when streams disagree on the motivational attribution for a constituency, emit both attributions in prose ("Depth attributes this to Greed; Breadth attributes it to Fear of capture by opposite faction") and let the user weigh.
- **Legitimate value preservation:** if one stream identified a legitimate value separate from distributional overlay, it is preserved — do not let adversarial momentum strip legitimate value.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. Construct the alternative position that would emerge from the opposite constituency's interests — equal technical sophistication.
2. Identify ≥ 2 numerical parameters / definitional choices where a different value would produce a materially different distributional outcome.
3. Map the policy landscape if the disadvantaged constituency had authored the standard.

Yellow Hat:
1. Identify the legitimate value the current position serves — separate from the distributional overlay.
2. Assess user gains from this analysis — actionable, informational, or diagnostic.

### Cascade — what to leave for the evaluator

- Construct the alternative with the literal heading "Alternative design:" and match Depth's technical rigour. Supports M3.
- Use the literal phrase "Legitimate value:" in the section separating distributional overlay from genuine purpose. Supports M5.
- Use the literal phrase "cost-bearer:" when naming who bears the cost.

## EVALUATION CRITERIA

5. **Institutional Tracing.** 5=authorship + constituency + incentive structure mapped for all relevant institutions. 3=authorship identified but incentive structure incomplete. 1=no tracing.
6. **Distributional Specificity.** 5=specific parameters with quantified impact. 3=direction only. 1=vague.
7. **Alternative Construction Quality.** 5=technically sophisticated, internally consistent, genuinely opposite. 3=cosmetic or naive. 1=no alternative or strawman.

### Focus for this mode

A strong CB evaluator prioritises:

1. **Author-and-beneficiary presence (S10).** Envelope must show at least one author element AND one beneficiary element. Missing either invalidates the trace.
2. **Parameter specificity (M2).** ≥ 2 specific parameters with distributional impact. Vague "incentive structure" language fails.
3. **Alternative construction (M3).** Not cosmetic, not analyst's preference. Technically sophisticated.
4. **FGL symmetry (M4).** Applied to ≥ 2 constituencies. Single-side attribution is the Asymmetric-FGL trap.
5. **Legitimate value (M5).** Separate from distributional overlay. Cynicism trap otherwise.
6. **Structural-not-conspiracy stance.** Institutional incentives first; intent only with evidence.
7. **Short_alt (S11).** Name the parameter and the beneficiary; don't list every subgraph.

### Suggestion templates per criterion

- **S11 (short_alt):** `suggested_change`: "Rewrite short_alt as: 'Flowchart of <parameter> tracing authorship, beneficiaries, and cost-bearers.' (or 'Concept map of <institutional structure>' for concept_map). Target ≤ 100 chars."
- **S10 (missing author/beneficiary):** `suggested_change`: "Envelope lacks <author|beneficiary> node. Add the institutional author (subgraph 'Authors') and the beneficiary constituency (subgraph 'Beneficiaries')."
- **M2 (vague parameters):** `suggested_change`: "Replace generic 'incentive structure' with ≥ 2 specific parameters — numerical thresholds, definitional choices, eligibility criteria — and quantify or describe the distributional impact of each."
- **M3 (cosmetic alternative):** `suggested_change`: "Rewrite alternative design with equal technical rigour to the institutional position. Specific parameters, not direction. The alternative serves the disadvantaged constituency, not the analyst's preference."
- **M4 (asymmetric FGL):** `suggested_change`: "Apply Fear/Greed/Laziness labels to both the institutional author AND the opposing constituency. Symmetric application prevents advocacy disguised as analysis."
- **M5 (cynicism):** `suggested_change`: "Add a 'Legitimate value:' paragraph separating what the position does serve (public goods, coordination, information) from the distributional overlay."

### Known failure modes to call out

- **Conspiracy Trap** → open: "Analysis attributes outcomes to deliberate coordination; default to structural. Evidence required before upgrading to intent."
- **Cynicism Trap** → open: "No legitimate value identified; separate distributional overlay from genuine purpose."
- **Mirror Trap** → open: "Alternative design mirrors the analyst's preference rather than the disadvantaged constituency's. Rewrite from that constituency's interests."
- **Asymmetric-FGL Trap** → open: "FGL applied only to opposing side. Apply to both parties."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-CB-1 — Author-beneficiary preservation.** Revised envelope retains at least one author-labelled element AND one beneficiary-labelled element.
- **V-CB-2 — Alternative-design rigour.** If prose includes "Alternative design:", it has specific parameters (not direction) with at least equal specificity to the institutional position.
- **V-CB-3 — Legitimate value preservation.** Revised prose retains the "Legitimate value:" section (or explicit "No legitimate value beyond distributional effects" declaration).
- **V-CB-4 — Structural-first preservation.** Silent upgrade from structural incentive to intent-attribution during revision is a FAIL unless new evidence is explicitly cited.

## CONTENT CONTRACT

In order:

1. **Institutional authorship** — who authored / advocates; what constituency they serve.
2. **Stated rationale** — the official justification in its own terms.
3. **Distributional impact** — who gains, who loses, by how much (with parameters cited).
4. **Alternative design** — the position from opposite interests, equal technical rigour.
5. **Motivational analysis** — FGL (Fear, Greed, Laziness) of institutional actors.
6. **Legitimate value** — what the position does serve, separate from distributional overlay.

After your analysis, emit exactly one fenced `ora-visual` block per EMISSION CONTRACT.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S2:** `E_SCHEMA_INVALID` → often short_alt length; apply S11 template. `E_UNRESOLVED_REF` in concept_map → propositions reference undeclared ids; fix.
- **S7:** pick envelope type: single-institution policy → `flowchart`; multi-institution network → `concept_map`.
- **S8 (flowchart DSL):** ensure DSL begins with `flowchart ` or `graph `; add `Authors` / `Beneficiaries` / `Bears cost` subgraphs.
- **S9 (concept_map shape):** ensure ≥ 4 concepts, ≥ 2 linking phrases, ≥ 3 propositions, ≥ 1 cross-link.
- **S10:** apply missing-author/beneficiary template.
- **S11:** apply short_alt template.
- **M1 (author not named):** add `Institutional author:` label to prose and corresponding node to envelope.
- **M2:** apply vague-parameters template.
- **M3:** apply cosmetic-alternative template.
- **M4:** apply asymmetric-FGL template.
- **M5:** apply cynicism template.
- **C1-C3:** sync author, beneficiaries, and parameters between prose and envelope.

## EMISSION CONTRACT

### Envelope type selection

- **`flowchart`** — when tracing interest flows from author → parameter → beneficiary is the load-bearing structure. Default for policy-with-clear-flow cases.
- **`concept_map`** — when institutional structure (multiple authors, constituencies, parameters in a network) is the load-bearing structure.

Selection rule: single-institution policy → `flowchart`; multi-institution network → `concept_map`.

### Canonical envelope (flowchart)

```ora-visual
{
  "schema_version": "0.2",
  "id": "cb-fig-1",
  "type": "flowchart",
  "mode_context": "cui-bono",
  "relation_to_prose": "integrated",
  "title": "Cui bono — minimum viable audit threshold at $5M",
  "canvas_action": "replace",
  "spec": {
    "dialect": "flowchart",
    "dsl": "flowchart LR\n  A[Standard-setting body] -->|authors| P[Threshold: $5M revenue]\n  P -->|exempts| S[Small firms]\n  P -->|binds| L[Mid-size firms]\n  S -->|lobbied for| A\n  L -->|bears cost| O[Audit overhead]\n  subgraph Authors\n    A\n  end\n  subgraph Beneficiaries\n    S\n  end\n  subgraph Bears cost\n    L\n    O\n  end"
  },
  "semantic_description": {
    "level_1_elemental": "Flowchart tracing the $5M audit threshold from author to beneficiaries and cost-bearers, with subgraphs for each role.",
    "level_2_statistical": "One author, one parameter, two affected constituencies — one exempted (small firms), one bound (mid-size firms).",
    "level_3_perceptual": "The lobbying arrow back from small firms to the author exposes the structural incentive: the author benefits from a specific threshold the lobbying constituency requested.",
    "short_alt": "Flowchart of the $5M audit threshold tracing authorship, beneficiaries, and cost-bearers."
  }
}
```

### Emission rules

1. **`type ∈ {"flowchart", "concept_map"}`.**
2. **`mode_context = "cui-bono"`. `canvas_action = "replace"`. `relation_to_prose = "integrated"`.**
3. **For `flowchart`:** `spec.dialect = "flowchart"`; `spec.dsl` is Mermaid flowchart syntax (must begin with `flowchart ` or `graph `). Include subgraphs for `Authors`, `Beneficiaries`, and `Bears cost` where applicable.
4. **For `concept_map`:** ≥ 4 concepts representing institutions + constituencies + parameters; ≥ 2 linking phrases including directional action verbs (e.g. "authors", "exempts", "binds", "lobbies for"); ≥ 3 propositions; at least one `is_cross_link`.
5. **The envelope must show at least one institutional author node AND at least one beneficiary + one cost-bearer node.**
6. **`semantic_description` required; `short_alt ≤ 150`.**
7. **One envelope.**

### What NOT to emit

- A flowchart with no subgraph separation — the interest structure must be visually separable.
- A concept map with only institutions and no parameters — CB is about parameters driving distribution.
- `canvas_action: "annotate"`.

## WPF ESCALATION CHECK

After the standard cui-bono output (CONTENT CONTRACT prose + EMISSION CONTRACT envelope) has been delivered, evaluate the analysis for wicked-problem indicators. This check is performed AFTER the standard output — it does not interrupt or alter the core analysis; it appends a follow-on recommendation when warranted.

### Indicators

Evaluate the cui-bono output against these three indicators:

1. **Multiple stakeholder groups with incompatible benefit structures.** The Distributional Impact section names beneficiaries and cost-bearers whose values cannot be jointly satisfied — what benefits one group materially harms another, and the harm is not compensable through side-payments or technical adjustments.
2. **No intervention option that produces net benefit across all groups.** The current intervention plus the alternative-constituency design plus any other implicit options all subordinate at least one major stakeholder group below their threshold of acceptance.
3. **Value conflicts evident in the distribution of benefits and harms.** The distribution traces back to fundamentally different values about what the policy or institution should serve — not merely different empirical estimates, different priorities within a shared value framework, or different positions on a tradeable margin.

### Escalation rule

- **IF two or more indicators are present** → append the WPF escalation prompt below to the output, formatted as a clearly labelled follow-on recommendation (visually distinct from the core analysis — separated by a horizontal rule and prefixed with the bridge-strip-style label `[WPF Escalation Recommended]`).
- **IF fewer than two indicators are present** → do nothing. The cui-bono output stands on its own; no escalation is offered.

### Escalation prompt template

When the rule fires, append this block verbatim to the output:

```
---

[WPF Escalation Recommended]

> This analysis shows characteristics consistent with a wicked problem — a problem where fundamental stakeholder value conflicts make any intervention a tradeoff rather than a resolution. Indicators present in this analysis: [list which of the three indicators fired and the specific evidence from the cui-bono output for each].
>
> For complete analysis including value conflict mapping, full consequence landscape modeling across time horizons, and a Decision Clarity Document suitable for decision-makers, invoke the Wicked Problems Framework (WPF). WPF will inherit this cui-bono analysis as the first intervention's distributional layer in Stage 3 — no work is duplicated.
>
> Invoke WPF? Yes / No.
```

### Handoff payload (when user confirms WPF invocation)

If the user confirms, hand off the following payload to WPF Path C (escalation):

- **Cui Bono Output** — the prior turn's full prose + envelope, preserved verbatim.
- **Indicator evidence** — which of the three indicators fired and the specific evidence from the cui-bono output for each.
- **Institutional author, beneficiaries, cost-bearers, distributional parameters, alternative-constituency design** — already in the cui-bono output; explicitly forwarded so WPF Stage 3 doesn't re-extract.

### Guard rails on the escalation

- The escalation prompt is **never inserted before** the standard output. Cui-bono's job is to deliver its analysis; WPF escalation is a follow-on, not a substitute.
- The escalation is **never silently inferred** by the user — it is an explicit prompt awaiting Yes / No.
- When fewer than two indicators are present, the escalation is **not offered**. Cui-bono is a complete mode in its own right; not every cui-bono analysis needs WPF.
- The escalation prompt must include **specific evidence** for each indicator that fired — generic "this looks complicated" language is a failure (G-CB-WPF-SP).

## GUARD RAILS

**Solution Announcement Trigger.** WHEN endorsing the alternative, verify the endorsement is grounded in analysis, not analytical momentum.

**Structural-first guard rail.** Institutional incentives before conspiracy. Require explicit evidence to upgrade.

**Symmetry guard rail.** Apply FGL to all parties, including those the user sympathises with.

## SUCCESS CRITERIA

Structural:
- S1-S6: standard preamble.
- S7: `type ∈ {"flowchart", "concept_map"}`.
- S8: for `flowchart`: `dialect=="flowchart"`, `dsl` starts with `flowchart ` or `graph `.
- S9: for `concept_map`: ≥ 4 concepts, ≥ 2 linking phrases, ≥ 3 propositions.
- S10: at least one author-labelled element AND one beneficiary-labelled element in the envelope.
- S11: `semantic_description` complete; `short_alt ≤ 150`.

Semantic:
- M1: authorship explicitly named in prose.
- M2: ≥ 2 specific parameters driving distribution named.
- M3: alternative design constructed with equal rigour.
- M4: FGL applied to ≥ 2 constituencies (not one).
- M5: legitimate-value separation stated (what does the position do serve, aside from distribution).

Composite:
- C1: institutional author in prose corresponds to author node/concept in envelope.
- C2: beneficiaries + cost-bearers in prose corresponds to envelope structure.
- C3: the ≥ 2 parameters named in prose appear in envelope labels.

```yaml
success_criteria:
  mode: cui-bono
  version: 1
  structural:
    - { id: S1-S6, check: standard_preamble }
    - { id: S7,  check: type_in_allowlist, allowlist: [flowchart, concept_map] }
    - { id: S8,  check: flowchart_mermaid_dsl, applies_to: flowchart }
    - { id: S9,  check: concept_map_shape, applies_to: concept_map }
    - { id: S10, check: author_and_beneficiary_present }
    - { id: S11, check: semantic_description_complete }
  semantic:
    - { id: M1, check: authorship_named }
    - { id: M2, check: two_parameters_driving_distribution }
    - { id: M3, check: alternative_design_present }
    - { id: M4, check: fgl_applied_to_multiple_parties }
    - { id: M5, check: legitimate_value_stated }
  composite:
    - { id: C1, check: author_in_envelope }
    - { id: C2, check: beneficiaries_cost_bearers_in_envelope }
    - { id: C3, check: parameters_in_envelope_labels }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Conspiracy Trap.** Attributing distributional outcomes to deliberate coordination. Correction: default to structural; upgrade only with evidence.

**The Cynicism Trap (inverse of M5).** Concluding the position has no legitimate basis. Correction: separate legitimate value from distributional overlay.

**The Mirror Trap (inverse of M3).** Constructing an alternative that is actually the analyst's preference. Correction: the alternative serves the disadvantaged constituency, not the analyst.

**The Asymmetric-FGL Trap (inverse of M4).** Applying FGL only to the opposing side. Correction: apply to all parties.

## TOOLS

Tier 1: FGL (primary), OPV, KVI, C&S, CAF.
Tier 2: Political and Social Analysis Module.

## TRANSITION SIGNALS

- IF the position rests on unexamined empirical assumptions → propose **Paradigm Suspension**.
- IF the user wants to evaluate the alternatives as viable options → propose **Constraint Mapping**.
- IF the user wants the strongest case for the institutional position → propose **Steelman Construction**.
- IF the user begins a deliverable → propose **Project Mode**.
- IF multiple explanations exist for institutional behaviour → propose **Competing Hypotheses**.
- IF two or more wicked-problem indicators fire on the cui-bono output (incompatible benefit structures, no net-positive intervention, fundamental value conflicts in distribution) → emit the **WPF Escalation** prompt per the WPF ESCALATION CHECK section above, offering invocation of the Wicked Problems Framework.
- IF the user wants the strongest case AGAINST the institutional position from the disadvantaged constituency's perspective → propose **Red Team** in `advocate` stance with the disadvantaged constituency as the client.
