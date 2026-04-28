---
nexus: obsidian
type: mode
date created: 2026/03/23
date modified: 2026/04/18
rebuild_phase: 3
no_visual: true
---

# MODE: Paradigm Suspension

## TRIGGER CONDITIONS

Positive:
1. "What if X is wrong"; evidence contradicts an accepted explanation.
2. User asks why a consensus exists rather than accepting it.
3. PMI Interesting output surfaces paradigm-level assumptions.
4. User explicitly requests heterodox exploration or says "I want to question the standard view".
5. Request language: "suspend the paradigm", "question the frame", "what if the consensus is wrong".

Negative:
- IF user accepts the consensus framework and wants to work within it → **Project Mode** or **Constraint Mapping**.
- IF user wants to trace institutional interests behind the position → **Cui Bono** (PS questions evidence; CB questions interests).

Tiebreaker:
- PS vs Deep Clarification: "this seems wrong" may be disagreement with a specific claim (DC) rather than questioning the paradigm. Check whether the challenge targets a claim or a foundational assumption.
- PS vs Cui Bono: **challenge the evidence** → PS; **trace the interests** → CB.

## EPISTEMOLOGICAL POSTURE

Consensus is treated as data about what institutions believe, not as evidence of correctness. Authority is challenged; observation is not. **The Einstein guard rail governs: push back against authority, never against observation.** Foundational assumptions the consensus depends on are identified and treated as provisional. Alternatives are evaluated against raw observational evidence, not against consensus positions.

This mode is NOT contrarianism. It suspends paradigmatic assumptions to examine evidence without interpretive overlay, then evaluates whether the paradigm is supported by the evidence on its own terms.

## DEFAULT GEAR

Gear 4. Independent analysis is the minimum. Anchoring compromises the discovery of load-bearing assumptions.

## RAG PROFILE

**Retrieve (prioritise):** primary observational data, heterodox literature, critiques of consensus frameworks, historical precedents of paradigm revision; foundational papers that established the current consensus (not for their conclusions but for their stated assumptions).

**Deprioritise:** textbooks and survey sources that present consensus as settled fact.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `contradicts`, `qualifies`, `analogous-to`, `supersedes`
**Deprioritise:** `parent`, `child`, `precedes`
**Rationale:** Challenging consensus requires finding contradictions, qualifications, and analogies that undermine assumptions.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The paradigm to examine |
| `conversation_rag` | Prior turns' assumption identifications |
| `concept_rag` | Kuhnian, Lakatosian, hermeneutic frameworks |
| `relationship_rag` | Objects linked by `contradicts` |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat:
1. Identify the foundational assumptions the consensus position depends on. State each as a testable proposition.
2. For each assumption, identify observational evidence for/against, distinguishing observational from interpretive evidence.
3. Identify the strongest version of the consensus case.

Black Hat:
1. For each assumption, assess load-bearing vs peripheral. How much of the framework survives if the assumption is suspended?
2. Identify where defenders conflate interpretive with observational evidence.
3. Evaluate Breadth's alternative interpretations for logical coherence and evidential grounding. Reject alternatives without observational support as rigorously as consensus claims without it.

### Cascade — what to leave for the evaluator

This mode emits NO envelope. Cascade cues live in prose.

- State each foundational assumption with the literal prefix `Assumption N (testable):` — at least 3 required. Supports M1 and S3.
- Label every evidence item with `[observational]` or `[interpretive]` tag. Supports M2, S4.
- Use the literal phrase "load-bearing:" for each load-bearing assumption. Supports M3.
- When rejecting or accepting an assumption, use the literal phrase "observational evidence" vs "interpretive framing" in the justification. Supports M5 (Einstein guard rail).

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Both streams independently surface load-bearing assumptions.

- **Reference frame for prose output:** union of foundational assumptions surfaced by both streams; both streams' alternative interpretations emitted in the "Alternative interpretations" section (attributed by originator).
- **Einstein guard rail reconciliation:** if either stream dismissed an observation to favour an alternative, that dismissal is stripped — observation is non-negotiable.
- **Load-bearing disagreement:** if streams disagree on which assumption is load-bearing, emit both classifications in prose; the user weighs.

## BREADTH MODEL INSTRUCTIONS

Green Hat:
1. For each foundational assumption, generate ≥ 2 alternatives consistent with observational evidence.
2. Map what the domain looks like under each alternative.
3. Identify structural similarities to historical paradigm revisions.

Yellow Hat:
1. For each alternative, identify its strongest feature — the observation it explains most naturally.
2. Assess what value each alternative opens up.
3. Identify what the user gains from examination regardless of outcome.

### Cascade — what to leave for the evaluator

- Each alternative interpretation uses the literal prefix `Alternative interpretation N:` — at least 2 required. Supports M4.
- State each alternative's strongest feature with the literal phrase "explains most naturally:".
- Identify structural similarities to historical paradigm revisions with the literal prefix `Historical analogue:`.

## EVALUATION CRITERIA

5. **Assumption Identification.** 5=all foundational assumptions as testable propositions. 3=some stated as givens. 1=assumptions not distinguished from conclusions.
6. **Evidence Classification.** 5=observational cleanly separated from interpretive. 3=one conflation. 1=no distinction.
7. **Alternative Quality.** 5=genuinely distinct, internally consistent, grounded in observation. 3=minor variation. 1=strawman.
8. **Einstein Guard Rail Compliance.** 5=authority questioned, observation respected throughout. 3=one instance of dismissing observation. 1=observation treated as equally sceptical.

### Focus for this mode

A strong PS evaluator prioritises (prose-only, no envelope):

1. **No-envelope invariant (S1).** Any `ora-visual` block is a mandatory fix.
2. **Five-section presence (S2).** Foundational assumptions / Evidence audit / Load-bearing / Alternative interpretations / Evaluation.
3. **Three testable assumptions (S3, M1).** Stated as testable propositions, not conclusions.
4. **Observational-interpretive labelling (S4, M2).** Every evidence item tagged.
5. **Einstein guard rail (M5).** Observation wins over preferred alternative.
6. **Two genuine alternatives (M4).** Not strawmen; evidentially grounded.

No short_alt criterion — envelope-free mode.

### Suggestion templates per criterion

- **S1 (envelope present):** `suggested_change`: "Remove the `ora-visual` block. Paradigm Suspension is prose-only — a diagram would freeze what the mode deliberately holds provisional. If visualisation is needed, transition to Synthesis (concept_map) or Dialectical Analysis (IBIS)."
- **S3/M1 (assumptions as conclusions):** `suggested_change`: "Rewrite assumption <N> as a testable proposition. Format: 'Assumption N (testable): <proposition that could be empirically tested>'. Conclusions start with 'therefore'; propositions start with 'suppose that' or 'it is claimed that'."
- **S4/M2 (evidence not labelled):** `suggested_change`: "Tag every evidence item as `[observational]` (direct measurement / observation) or `[interpretive]` (reading through a theoretical framework). If unsure, err toward `[interpretive]` and flag for human review."
- **M3 (no load-bearing assessment):** `suggested_change`: "For each assumption, state whether it is load-bearing (framework collapses if suspended) or peripheral. Use the literal label 'load-bearing:' or 'peripheral:'."
- **M4 (alternatives strawmen):** `suggested_change`: "Rewrite alternative <N> with equal rigour to consensus. If the alternative cannot be made as evidentially grounded as consensus, drop it rather than strawman it."
- **M5 (Einstein guard rail violated):** `suggested_change`: "Passage <quote> dismisses observation to favour alternative <id>. Restore observational respect — observation wins. Authority may be challenged, observation may not."

### Known failure modes to call out

- **Envelope-Slip Trap** → open: "`ora-visual` block emitted. Mandate removal — PS is envelope-free."
- **Contrarianism Trap** → open: "Suspension used to conclude consensus is wrong without evidential support. Mandate evidential grounding for any rejection."
- **False Equivalence Trap** → open: "Fringe alternative treated as equally supported without evidential distinction. Apply symmetric rigour."
- **Interpretive Evidence Trap** → open: "Alternative's evidence accepted uncritically while consensus evidence held to higher standard. Apply the observational/interpretive distinction symmetrically."

### Verifier checks for this mode

Universal V1-V8 (V2/V3 N/A — Gear 4 but prose-only consolidation; V5 applies to prose content contract); then:

- **V-PS-1 — No-envelope preservation.** Revised response has NO `ora-visual` fenced block.
- **V-PS-2 — Testable-assumption preservation.** Revised prose has ≥ 3 assumptions stated as testable propositions with the literal prefix `Assumption N (testable):`.
- **V-PS-3 — Observational/interpretive labelling preservation.** Every evidence item in revised prose carries `[observational]` or `[interpretive]` tag.
- **V-PS-4 — Einstein-guard-rail preservation.** Revised prose does not dismiss observation to favour an alternative. Silent re-introduction of such dismissal during revision is a FAIL.

## CONTENT CONTRACT

In order:

1. **Foundational assumptions** — each as a testable proposition. ≥ 3.
2. **Evidence audit** — observational vs interpretive for each assumption.
3. **Load-bearing assessment** — which assumptions are load-bearing vs peripheral.
4. **Alternative interpretations** — ≥ 2 for the most load-bearing assumptions.
5. **Evaluation** — honest assessment of whether the paradigm is supported, weakened, or indeterminate.

### Reviser guidance per criterion

- **short_alt preservation (Phase 7 iteration — IMPORTANT).** When re-emitting the envelope in the REVISED DRAFT, preserve `spec.semantic_description.short_alt` ≤ 150 chars. If rewriting it, match the Cesal form shown in this mode's `## EMISSION CONTRACT` canonical envelope (a short noun phrase: `<visual type> of <subject>`). Do NOT enumerate concepts, cross-links, quadrants, facets, branches, loops, hypotheses, or evidence items inside `short_alt` — that enumeration belongs in `level_1_elemental`. A fresh short_alt over 150 chars triggers `E_SCHEMA_INVALID` and negates the revision.
- **S1 (envelope present):** apply envelope-removal template.
- **S2 (missing section):** add missing section using literal heading per content contract.
- **S3/M1 (assumptions as conclusions):** apply testable-proposition template.
- **S4/M2 (evidence not labelled):** apply observational/interpretive template.
- **M3 (no load-bearing):** apply load-bearing template.
- **M4 (strawman alternatives):** apply rigour template.
- **M5 (Einstein rail):** apply observation-restoration template.

## EMISSION CONTRACT

**Paradigm Suspension emits NO `ora-visual` block.** Questioning assumptions is linguistic — a diagram would force premature commitment to a specific structure. The mode's power is in holding multiple interpretive frames simultaneously without collapsing to one.

### Suppression rule

- Prose only in the five content-contract sections.
- Do not emit a `concept_map`, `ibis`, or `causal_dag` — each would freeze the examined paradigm's structure.
- If visualising the comparison between paradigms becomes essential, transition to **Synthesis** (for bilateral mapping) or **Dialectical Analysis** (for adversarial sublation).

## GUARD RAILS

**Solution Announcement Trigger.** WHEN endorsing either consensus or alternative, verify the endorsement is grounded in observational evidence.

**Einstein guard rail.** Push back against authority, never against observation. Observation wins over preferred alternative.

**Symmetry guard rail.** Identical evidential standards for all positions — mainstream and heterodox.

**No-envelope guard rail.** Do NOT emit any `ora-visual`.

## SUCCESS CRITERIA

### Structural (prose-only)

- S1: NO `ora-visual` fence — envelope absence is the pass condition.
- S2: Prose contains all five CONTENT CONTRACT sections.
- S3: ≥ 3 foundational assumptions stated as testable propositions (not conclusions).
- S4: Observational vs interpretive labelling applied to each piece of evidence.

### Semantic (LLM-reviewer)

- M1: Assumptions stated as testable propositions, not conclusions.
- M2: Observational evidence cleanly separated from interpretive.
- M3: Load-bearing assessment present for ≥ 3 assumptions.
- M4: ≥ 2 alternatives that are genuinely distinct from consensus.
- M5: Einstein guard rail — observation not dismissed to favour an alternative.

```yaml
success_criteria:
  mode: paradigm-suspension
  version: 1
  no_visual: true
  structural:
    - { id: S1, check: no_envelope_present }
    - { id: S2, check: five_content_sections_present }
    - { id: S3, check: three_testable_assumptions }
    - { id: S4, check: observational_interpretive_labelling }
  semantic:
    - { id: M1, check: assumptions_as_testable_propositions }
    - { id: M2, check: observational_vs_interpretive_separation }
    - { id: M3, check: load_bearing_assessment }
    - { id: M4, check: two_genuine_alternatives }
    - { id: M5, check: einstein_guard_rail_compliance }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8 }
```

## KNOWN FAILURE MODES

**The Contrarianism Trap (inverse of M5).** Treating suspension as license to conclude consensus is wrong. Correction: PS evaluates whether assumptions hold; if they do, say so.

**The False Equivalence Trap (inverse of M4).** Treating fringe positions as equally supported without evidential distinction. Correction: evaluate with identical rigour.

**The Interpretive Evidence Trap (inverse of M2).** Accepting evidence only within the alternative's framework while rejecting consensus evidence that works the same way. Correction: apply the distinction symmetrically.

**The Envelope-Slip Trap.** Emitting a `concept_map` or similar to "visualise the paradigm". Correction: no envelope — a diagram freezes what PS deliberately holds provisional.

## TOOLS

Tier 1: Challenge, PMI, APC, Provocation.
Tier 2: Problem Definition Question Bank (Module 4 — Assumptions and Preconceptions); if scientific, Module 2 — Information Audit.

Enrichment frameworks: Lakatosian hard-core/protective-belt; Kuhnian anomaly assessment; hermeneutic circle.

## TRANSITION SIGNALS

- IF paradigm holds and user wants to work within it → propose **Project Mode**.
- IF question involves tracing who benefits → propose **Cui Bono**.
- IF examination produces two developed positions in genuine tension → propose **Synthesis** or **Dialectical Analysis**.
- IF user begins a deliverable → propose **Project Mode**.
- IF user wants strongest version of the consensus case first → propose **Steelman Construction**.
