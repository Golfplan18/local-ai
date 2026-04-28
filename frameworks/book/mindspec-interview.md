# MindSpec Interview Framework v0.2.3

*Operational specification for producing MindSpec agent, character, and self specifications through tiered interactive assessment. Includes Inference Layer (§V) and Learning Architecture (§VI) specifications.*

*v0.2.2 2026-04-21: Universality-audit corrections applied. Library defaults recalibrated to general-population median (26 of 59 entries). Portrait, dyad, multi-commitment, and pressure-test revisions for architect-specific-vocabulary, framework-jargon, and contemplative-practice-presumption leakage. Stage 2A Life-Context Direct Pass specified as §VIIA — previously improvised, now universal. Framework-author reflexivity flagged as Known Limitation. Single-file specification architecture introduced for application to v0.2.3 outputs. Four-framework ecosystem clarified (MindSpec / Mission / Interaction / Problem Evolution). See `Framework — MindSpec Universality Audit and Corrections.md` for methodology and full corrections.*

*v0.2.3 2026-04-21: Library inventory in §II updated to 66 entries (42 primary + 24 character-spec) across 11 families. Primary additions KINDNESS, RESPECT, WARMTH; character-spec additions CONTEMPT, SELF-CONTEMPT, ARROGANCE, SCHADENFREUDE. Renames: HARM-AVERSION → HARMLESSNESS, IN-GROUP-LOYALTY → TRIBALISM, SELF-ABASEMENT → FALSE HUMILITY, Life-Orientation → VITALITY, Long-duration-affective-state → TEMPERAMENT.*

*v0.2.3 consolidation 2026-04-21: Inference Layer and Learning Architecture merged into this file as §V and §VI respectively. Library Specifications and Three-Stage Assessment Instrument consolidated into `Framework — MindSpec Library and Instrument.md`. Previous five-file architecture reduced to three operational files + Universality Audit.*

## PURPOSE

Produces complete MindSpec specifications — the single-file specification document (v0.2.3+) or the structured-YAML + prose-projection set (v0.2.2 and earlier) — through tiered interactive assessment calibrated to agent durability. Supports self-specification, persistent-agent specification, and fiction-character specification. Implements MindSpec v0.4.1 with the 66-entry library, three-stage assessment instrument, Stage 2A life-context pass, incompatibility adjustment mechanism (§V), and learning architecture (§VI) for persistent agents.

## INPUT CONTRACT

**Required:**
- User participation in the assessment process
- Mode selection (agent or character)
- Tier selection (for agents: ephemeral, persistent task, or personal thinking partner)

**Optional:**
- Descriptive material about the specification target. Source: user-provided. Default if absent: full assessment without pre-fill.
- Existing specification for revision. Source: prior specification file (single-file v0.2.3+ or structured YAML v0.2.2). Default if absent: new specification from library defaults.

## OUTPUT CONTRACT

**For v0.2.3 forward — single-file specification architecture (see §Single-file specification architecture below):**
- Primary specification file (`mind.md` or `[agent-name].md`) containing all sections: Core Identity, Mission, Context, Commitments (structured fields + operational prose per entry), Governance, Constitution, Voice, Communication Patterns, Relationships, and Aesthetic Sensibility (optional 10th section, populated for users or agents producing artifacts across multiple expressive media — consumed by the Output Formalization Framework for cross-medium aesthetic coherence). Target length 4000–6000 words for Tier 3 personal thinking partner; the optional Aesthetic Sensibility section adds 500–1000 words when present.
- `ledger.md` — learning architecture record (grows continuously)
- `modifications.md` — specification change log (grows continuously)

**For v0.2.2 and earlier — structured-YAML + prose-projection set:**
- `commitments.yaml` — structured commitment library with weights, activation profiles, near-enemy fields, object-modulation specifications
- `governance.yaml` — role configurations (Parliamentarian, Witness, Auditor, Clerk) with sensitivities and cadences
- `constitution.yaml` — high-weight commitments with articles, interpretation, amendment conditions
- `mind.md` — prose projection for runtime consumption and SoulSpec compatibility (or `char-profile.md` for character-spec mode)
- `VOICE.md` — voice specification with examples
- `COMMUNICATION.md` — communication strategy specifications

Tier-dependent artifact subsets per §VII.

**Note:** the Interaction Framework (companion, to be built) takes over VOICE / COMMUNICATION / RELATIONSHIPS / PLAYBOOK production in the four-framework ecosystem. MindSpec v0.2.3 outputs will reference these as engagement-layer files produced by Interaction Framework rather than produced by MindSpec directly.

## EXECUTION TIER

Single-pass in commercial AI sessions. Stages execute sequentially with natural break points for Tier 3 assessments spanning multiple sessions. Model-agnostic.

---

## MILESTONES DELIVERED

This framework's declaration of the project-level milestones it can deliver. Used by the Problem Evolution Framework (PEF) to invoke this framework for milestone delivery under project supervision.

### Milestone Type: Agent specification

- **Endpoint produced:** Complete agent specification fileset for a named persistent or ephemeral AI agent — primary single-file specification (`mind.md` or `[agent-name].md`) containing Core Identity, Mission, Context, Commitments (structured fields plus operational prose per entry), Governance, Constitution, Voice, Communication Patterns, and Relationships sections, plus companion files `ledger.md` (learning log) and `modifications.md` (change log) initialized empty. For v0.2.2 and earlier, the structured-YAML set (`commitments.yaml` + `governance.yaml` + `constitution.yaml`) plus `mind.md` prose projection, `VOICE.md`, and `COMMUNICATION.md`. Tier-dependent subsets per §VII — Tier 1 ephemeral agents receive library-default specifications without assessment; Tier 2 persistent task agents receive Stage 1 filtered assessment with light governance; Tier 3 personal thinking partners receive full three-stage assessment with full governance.
- **Verification criterion:** (a) all seven Evaluation Criteria (§VIII) score 3 or above; (b) for Tier 3 specifications, total specification length reaches 4000–6000 words per §Single-file specification architecture density requirements; (c) all library entries at weight 6+ carry the full operational paragraph (100–200 words) per projection density requirements; (d) incompatibility adjustment mechanism (§V.3) has been applied and resulting adjustments are surfaced transparently per §V.4.1 Adjustment Summary Format (Tier 2 and Tier 3 only; Tier 1 is exempt per Principle 6); (e) for Tier 3, constitutional commitments have been identified per Stage 3 pressure-testing and recorded with articles, interpretation, and amendment conditions; (f) the tier-appropriate interview flow from §VII has been followed through to completion with all Stage 2A Life-Context fields (§VIIA) populated including explicit "none" recordings where applicable.
- **Preconditions:** User participation is available for the interview duration matching the selected tier; mode is locked to agent-specification; tier is selected (ephemeral, persistent task, or personal thinking partner); dependent documents (`MindSpec_v0.4_Specification.md` and `Framework — MindSpec Library and Instrument.md`) are loaded; optional descriptive material about the agent target and optional existing specification for revision are either provided or explicitly absent.
- **Mode required:** Agent-specification mode with tier selection
- **Framework Registry summary:** Produces complete MindSpec agent specification (ephemeral, persistent task, or personal thinking partner tier) through tiered interactive assessment with incompatibility adjustment and governance configuration

### Milestone Type: Character specification

- **Endpoint produced:** Complete fiction-character specification fileset — primary single-file specification (`char-profile.md` or `[character-name].md`) containing Core Identity, Mission, Context, Commitments (structured fields plus operational prose per entry including pathology signatures where applicable from the 24-entry character-spec library), Governance, Constitution, Voice, Communication Patterns, and Relationships sections, plus companion files `ledger.md` and `modifications.md` initialized empty. Produced through direct authoring plus coherence check flow (§VII) with pathology signatures pre-filled per authorial intent where explicit material is provided.
- **Verification criterion:** (a) all seven Evaluation Criteria (§VIII) score 3 or above; (b) incompatibility adjustment mechanism (§V.3) has been applied — character-spec mode is within universal scope per Principle 6 and §V.3.8 — and resulting adjustments are surfaced transparently in the authorial-control framing specified in §V.3.8; (c) character-spec library entries (PITY, FALSE HUMILITY, INDIFFERENCE, CAPITULATION, ENTITLEMENT, JEALOUSY, CRUELTY, ENMESHMENT, CONTEMPT, SELF-CONTEMPT, ARROGANCE, SCHADENFREUDE, RESENTMENT, MALICE, SPITE, WRATH, GREED, MISERLINESS, POSSESSIVENESS, OBSESSION, CONCEALMENT, DELUSION, BITTERNESS, PRETENSE) used in the specification carry operational prose matching the agent commitment density requirements; (d) the resulting specification passes coherence check — directly-opposing pairs and near-enemy pairs are not simultaneously active at high weights unless justified by the adjustment mechanism's output; (e) Stage 2A Life-Context fields (§VIIA) populated for the character with explicit "none" recordings where applicable.
- **Preconditions:** User participation is available for the 30-90 minute direct-authoring flow; mode is locked to character-specification; authorial material (character sketches, biographical notes, prior writings, theoretical frameworks with references) is either provided for material-based inference (§V.1) or the author proceeds without pre-fill; dependent documents are loaded.
- **Mode required:** Character-specification mode
- **Framework Registry summary:** Produces complete MindSpec fiction-character specification with pathology signatures through direct-authoring flow with coherence check

### Milestone Type: Self-specification

- **Endpoint produced:** Complete self-specification fileset for the user — primary single-file specification (`mind.md`) containing Core Identity, Mission, Context, Commitments (structured fields plus operational prose per entry across the 42-entry primary library), Governance, Constitution, Voice, Communication Patterns, and Relationships sections, plus companion files `ledger.md` and `modifications.md` initialized empty. Produced through full three-stage assessment (§IV) with Stage 2A Life-Context Direct Pass (§VIIA), Inference Layer processing (§V), and constitutional identification via Stage 3 pressure-tests.
- **Verification criterion:** (a) all seven Evaluation Criteria (§VIII) score 3 or above; (b) total specification length reaches 4000–6000 words per §Single-file specification architecture density requirements; (c) all library entries at weight 6+ carry the full operational paragraph (100–200 words) per projection density requirements; (d) incompatibility adjustment mechanism (§V.3) has been applied in full — self-specification is within universal scope per Principle 6 and §V.3.8 — and resulting adjustments are surfaced transparently per §V.4.1 with developmental framing (Principle 10) honored throughout; (e) concept-access-difficult commitments (the 14 entries listed in §V.3.1) carry reliability coefficients and any adjustments trace to specific evidence from scenario patterns per §V.3.4; (f) constitutional commitments have been identified per Stage 3 pressure-testing and recorded with articles, interpretation, and amendment conditions; (g) if LC-7 self-identified load-bearing commitments were provided, divergence between self-identification and assessment-derived results has been surfaced in the adjustment summary.
- **Preconditions:** User participation is available for the 3-5 hour full assessment (or 45-minute-to-full with material-based pre-fill per §V.1); mode is locked to self-specification; dependent documents are loaded; optional prior-writings material, biographical context, or theoretical framework anchors are either provided or explicitly absent.
- **Mode required:** Self-specification mode (runs against the full-depth Tier 3 interview flow by default)
- **Framework Registry summary:** Produces complete MindSpec self-specification through full three-stage assessment with incompatibility adjustment and constitutional identification

---

## DEPENDENT DOCUMENTS

Required reading in order:
1. `MindSpec_v0.4_Specification.md` — base MindSpec specification
2. `Framework — MindSpec Library and Instrument.md` — 66-entry library (Part I) with schemas; three-stage assessment instrument (Part II) with portraits, dyads, multi-commitment scenarios, pressure-tests

Inference Layer and Learning Architecture specifications are §V and §VI of this document.

Tier-dependent interview flows are specified in §VII of this document (not a separate file).

Supporting documents:
- `Framework — MindSpec Universality Audit and Corrections.md` — v0.2.2 universality audit methodology, findings, corrections
- `Framework — Process Formalization.md` — meta-framework for framework construction
- `Reference — SoulSpec Defining Identity for AI Agents.md` — compatibility standard

---

## §I Governing Principles

1. **Functional organization.** The library is organized by what patterns do at runtime, not by causal origin.
2. **Near-enemy architecture.** Virtuous commitments carry near-enemy fields identifying selfish patterns that masquerade as them. The Witness checks distinguishing marks at runtime.
3. **Directly-opposing patterns.** Some commitments carry `direct_opposition` fields identifying patterns standing in the same psychological space with inverted valence. Near enemies masquerade; directly-opposing patterns displace.
4. **Concept-access difficulty.** Self-report accuracy on certain commitments requires developed observational capacity. Encoded through the incompatibility mechanism.
5. **Tier-appropriate depth.** Temporary agents take defaults. Persistent task agents take filtered Stage 1 or light inference. Personal thinking partners and fiction characters take full three-stage assessment.
6. **Universal mechanism application.** The incompatibility adjustment applies to self-specification, persistent-agent specification, and fiction-character specification. Only Tier 1 ephemeral agents are exempt.
7. **Substrate, not prompt.** Structured MindSpec files do not enter the agent's runtime prompt. Prose projections do. Prevents reward-hacking through weight introspection.
8. **Learning with safeguards.** Persistent agents update weights through experience. Six drift-prevention safeguards required.
9. **Constitutional immunity.** Constitutional commitments don't update through ordinary feedback.
10. **Developmental framing.** Adjustments and pathology signatures are not moral judgments. They describe what the framework can reliably specify given available evidence.

## §II The Library

66 entries across 11 families. 42 primary + 24 character-spec.

**Primary library (42):**
- *Appetite:* COMFORT, NOVELTY, PLEASURE
- *Social:* APPROVAL, TRIBALISM, STATUS
- *Fear:* HUMILIATION, ABANDONMENT
- *Aspiration:* TRUTH, CRAFT, CALLING
- *Moral:* HARMLESSNESS, KINDNESS, FAIRNESS, LIBERTY, AUTHORITY, RESPECT, FEROCITY
- *Relational:* WARMTH, PROTECTIVE-LOVE, INTIMACY, MENTORSHIP
- *Self-maintenance:* SELF-PRESERVATION, SELF-IMAGE, CONSISTENCY, GRASPING
- *Meta:* WITNESS, SKEPTICISM, SANCTITY
- *VITALITY:* CURIOSITY, PLAYFULNESS, WONDER, TRUST, HOPE, ENTHUSIASM, GRATITUDE
- *Positive near-enemy halves:* APPRECIATION, JOY, COMPASSION, HUMILITY, EQUANIMITY, FORGIVENESS

**Character-spec library (24):**
- *Near-enemy negative halves:* PITY, FALSE HUMILITY, INDIFFERENCE, CAPITULATION
- *Directly-opposing:* ENTITLEMENT, JEALOUSY, CRUELTY, ENMESHMENT, CONTEMPT, SELF-CONTEMPT, ARROGANCE, SCHADENFREUDE
- *Anger-derived:* RESENTMENT, MALICE, SPITE, WRATH
- *Attachment-derived:* GREED, MISERLINESS, POSSESSIVENESS, OBSESSION
- *Ignorance-derived:* CONCEALMENT, DELUSION
- *TEMPERAMENT:* BITTERNESS
- *Mixed:* PRETENSE

Complete entry specifications in `Framework — MindSpec Library and Instrument.md` Part I.

## §III Schema Specification

Commitment schema (`commitments.yaml`):

```yaml
commitment:
  id: string
  name: string
  definition: string
  family: string
  entry_type: "primary" | "character-spec"
  
  weight: float                          # 0-9 user-facing
  root_alignment: float                  # -1.0 to +1.0
  
  activation_profile:
    relational: float                    # 0.0-1.0
    epistemic: float
    resource: float
    self_regulation: float
  
  vote_tendency:
    prefers: [string]
    opposes: [string]
    rationale: string
  
  grading_criteria:
    positive_signals: [string]
    negative_signals: [string]
  
  formative_context: string
  update_threshold: float
  constitutional_threshold: float
  is_constitutional: bool
  
  conflicts: [string]
  near_enemy: string
  distinguishing_mark: string
  direct_opposition: string              # optional
  
  object_modulations:                    # optional
    - pattern: string
      weight_delta: float
      description: string
  
  triggering_conditions: [string]        # optional
  
  near_enemy_substitution_conditions:    # optional
    when: string
    substitutes_for: string
  
  party_line_alignment: float
  
  metadata:
    created: datetime
    last_updated: datetime
    source_library: string
```

Governance schema (`governance.yaml`):

```yaml
parliamentarian:
  sensitivity: low | medium | high
  
adversarial_witness:
  sensitivity: low | medium | high
  near_enemy_detection: enabled | disabled
  context_tuning:
    exploratory: low
    commitment_signals: high
  
auditor:
  cadence: real-time | daily | weekly | monthly | none
  
clerk:
  ledger_scope: full | operational-only | none
```

Constitution schema (`constitution.yaml`):

```yaml
articles:
  - commitment: string
    current_weight: float
    operational_requirements: [string]
    drift_interpretations: [string]
    amendment_conditions: [string]
```

## §IV Three-Stage Assessment Instrument

- **Stage 1 — Portrait-based rating.** 66 portraits, 60-85 words each. PVQ-RR-style 1-6 similarity ratings.
- **Stage 2 dyad scenarios.** 28 dyads × 3 scenarios = 84 scenarios. Binary A/B choice.
- **Stage 2 multi-commitment scenarios.** 35 scenarios. 4 response options each.
- **Stage 3 pressure-tests.** 17 scenarios. Constitutional candidate identification. Inline Hold annotations.

All material calibrated for no option-signaling and no scenario-signaling. Full instrument in `Framework — MindSpec Library and Instrument.md` Part II.

## §V Inference Layer

*Complete specification of the four inference functions that operate between assessment data collection and specification output.*

The inference layer sits between assessment data collection (Stages 1-3 of the assessment instrument) and specification output (commitments.yaml, governance.yaml, constitution.yaml). Four processing functions:

1. **Material-based inference** — pattern-matching provided material to pre-fill assessment answers.
2. **Confidence calibration and blend resolution** — tagging pre-fills, handling composite specifications.
3. **Incompatibility adjustment** — load-bearing; catches self-reports that cannot coexist with the rest of the profile.
4. **Output specification** — structured adjustment surfaces for user review.

Functions 1-2 operate on the input side, reducing user burden when material is available. Function 3 operates on the output side, correcting self-concept-driven inflation of concept-access-difficult commitments. Function 4 presents adjustments transparently.

### §V.1 Material-Based Inference (Function 1)

Operates on provided material: job descriptions, character sketches, theoretical frameworks plus references, biographical data, blend requests, prior writings.

#### §V.1.1 Process

1. Decompose material into statements about the target.
2. For each Stage 1 portrait, check whether statements match or contradict the portrait's behavioral patterns. Produce predicted similarity rating (1-6).
3. For each Stage 2 dyad scenario, check whether material describes behavior patterns consistent with specific options.
4. For each Stage 2 multi-commitment scenario, identify which commitments material evidences most clearly.
5. For each Stage 3 pressure-test, pre-fill only when material contains explicit evidence of how the target has actually held or failed to hold the commitment under specific pressure.

#### §V.1.2 Confidence Tagging

Three levels per pre-filled item:

- **High confidence** — material directly addresses item with multiple converging statements, or the answer is logically entailed by explicit material.
- **Tentative** — material suggests the answer through one or two indirect statements; plausible alternative readings exist.
- **Inferred weakly** — pattern-match based on adjacent material rather than direct addressing.

System tuned toward under-confidence. Ambiguous matches default to tentative or weakly-inferred. Confident pre-fills require explicit material support, not inference from absent material. Better to ask than guess.

#### §V.1.3 Per-Stage Pre-fill

- **Stage 1 portraits:** similarity ratings 1-6. Confidence depends on whether material directly describes behavioral patterns matching the portrait.
- **Stage 2 dyad scenarios:** option selection when resolution is evidenced; tentative flag when material implies pattern without resolving the tension; open when material doesn't address.
- **Stage 2 multi-commitment scenarios:** option selection when specific coalition is evidenced.
- **Stage 3 pressure-tests:** pre-fill only on explicit evidence of how the target held or failed under pressure. Most default to open unless material contains directly analogous situations.

### §V.2 Blend Resolution (Function 2)

For blended identities (composite specifications from multiple sources):

1. Run material-based inference on each source separately.
2. Produce per-source pre-filled assessment.
3. Identify conflicts — items where sources produce different predicted answers.
4. Surface conflicts to user: "Source A suggests [answer]; Source B suggests [answer]; which does the blend inherit?"
5. User resolves each conflict before proceeding.

Non-conflicting items from all sources accepted as pre-filled with original confidence tags. Conflicts become user's focused review work.

### §V.3 Incompatibility Adjustment Mechanism (Function 3)

The load-bearing addition. Five components: concept-access-difficult commitments, pairwise rules, selfishness coefficient, reliability coefficient, weight adjustment math.

#### §V.3.1 Concept-Access-Difficult Commitments

Self-report accuracy on certain commitments requires developed observational capacity. Someone without contemplative training cannot reliably distinguish:

- EQUANIMITY from detachment, suppression, situational calm
- COMPASSION (undifferentiated) from PITY or caring-within-group
- HUMILITY from FALSE HUMILITY or strategic modesty
- WITNESS from rumination or standard introspection
- HOPE (anchored) from optimism or denial
- FORGIVENESS from CAPITULATION
- JOY (mudita) from satisfaction at comparative standing

14 concept-access-difficult entries subject to the adjustment mechanism:

- *VITALITY:* CURIOSITY, WONDER, TRUST, HOPE, GRATITUDE
- *Meta:* WITNESS, SKEPTICISM, SANCTITY
- *Near-enemy-paired virtues:* COMPASSION, HUMILITY, FORGIVENESS, JOY, EQUANIMITY
- *Primary capacity:* FEROCITY (when clean vs. captured is the distinction at issue)

Other commitments (APPETITE family, SOCIAL family, FEAR family, most ASPIRATION and MORAL entries) can be self-reported reliably because concepts have common-language counterparts tracking the framework's specification closely enough.

#### §V.3.2 Pairwise Incompatibility Rules

14 rules covering pairwise incompatibilities and one novel mechanism. Rules 1-8 and 10-13 each cover a single commitment-pair incompatibility. Rule 9 splits into 9a/9b/9c for three distinct GREED-target evidence profiles (against MENTORSHIP, APPRECIATION, and non-differentiated COMPASSION respectively). Rule 14 is the FEROCITY-to-WRATH transfer mechanism — novel because it triggers an entry activation rather than only a weight adjustment. Each rule specifies evidence requirements (Stage 1 self-report plus Stage 2 scenario pattern) and adjustment direction.

**Rule 1 — TRIBALISM (differentiating) × EQUANIMITY**
- Evidence: Stage 1 on both + Stage 2 showing TRIBALISM differentiating pattern.
- Condition: TRIBALISM ≥ 7 with differentiating pattern AND EQUANIMITY ≥ 7.
- Adjustment: Reduce EQUANIMITY.
- Rationale: TRIBALISM with differentiating pattern requires differential weighting of groups. EQUANIMITY as specified is undifferentiated groundedness. Self-reported EQUANIMITY from a differentiating profile is situational in-group calm.

**Rule 2 — STATUS (as driver) × HUMILITY**
- Evidence: Stage 1 on both + Stage 2 showing STATUS-as-driver pattern.
- Condition: STATUS ≥ 7 with driver pattern AND HUMILITY ≥ 7.
- Adjustment: Reduce HUMILITY.
- Rationale: STATUS-as-driver requires comparative self-positioning; HUMILITY requires stable accurate self-assessment. Self-reported HUMILITY from STATUS-driven profiles references performed smallness or strategic modesty.

**Rule 3 — ENTITLEMENT × GRATITUDE**
- Evidence: Stage 2 on ENTITLEMENT + Stage 1 on GRATITUDE.
- Condition: ENTITLEMENT (scenario-evidenced) ≥ 6 AND GRATITUDE ≥ 7.
- Adjustment: Reduce GRATITUDE.
- Rationale: ENTITLEMENT frames goods as owed; GRATITUDE frames them as gift. Directly inverse orientations.

**Rule 4 — POSSESSIVENESS × COMPASSION (non-differentiated)**
- Evidence: Stage 2 on POSSESSIVENESS + Stage 1 on COMPASSION + Stage 2 showing non-differentiated claim.
- Condition: POSSESSIVENESS (scenario-evidenced) ≥ 6 AND COMPASSION ≥ 7 claimed non-differentiated.
- Adjustment: Reduce COMPASSION.
- Rationale: POSSESSIVENESS treats relationships as owned; non-differentiated COMPASSION extends regardless of ownership. Self-reports of non-differentiated compassion from possessive profiles reference in-group caring.

**Rule 5 — JEALOUSY × JOY**
- Evidence: Stage 1 self-report sufficient. Stage 2 confirmation strengthens but not required. (Exception to general both-required rule because patterns are recognizable in self-report.)
- Condition: JEALOUSY ≥ 6 AND JOY ≥ 7.
- Adjustment: Reduce JOY.
- Rationale: Direct inversion. Pain and gladness at others' flourishing cannot both be high simultaneously.

**Rule 6 — DELUSION × WITNESS**
- Evidence: Stage 2 on DELUSION + Stage 1 on WITNESS.
- Condition: DELUSION (scenario-evidenced) ≥ 5 AND WITNESS ≥ 7.
- Adjustment: Reduce WITNESS.
- Rationale: DELUSION requires captured witness; genuine WITNESS dissolves DELUSION.

**Rule 7 — WRATH × EQUANIMITY**
- Evidence: Stage 2 on WRATH + Stage 1 on EQUANIMITY.
- Condition: WRATH (scenario-evidenced) ≥ 5 AND EQUANIMITY ≥ 7.
- Adjustment: Reduce EQUANIMITY.
- Rationale: WRATH is self-referential consuming anger; EQUANIMITY is what WRATH rules out.

**Rule 8 — Defended SELF-IMAGE × TRUTH (about self)**
- Evidence: Stage 2 on SELF-IMAGE-as-defended-construction + Stage 1 on TRUTH + Stage 2 showing TRUTH-about-self resistance.
- Condition: SELF-IMAGE ≥ 7 with defended pattern AND TRUTH ≥ 7.
- Adjustment: Reduce TRUTH.
- Rationale: Defended self-image requires willful ignorance about self. TRUTH including accurate self-assessment requires willingness to update self-view under evidence.

**Rule 9a — GREED × MENTORSHIP**
- Evidence: Stage 2 on GREED + Stage 1 on MENTORSHIP with Stage 2 confirmation.
- Condition: GREED (scenario-evidenced) ≥ 6 AND MENTORSHIP ≥ 7.
- Adjustment: Reduce MENTORSHIP.
- Rationale: MENTORSHIP requires investing in another's growth at cost to self; GREED organizes around acquisition for self.

**Rule 9b — GREED × APPRECIATION**
- Evidence: Stage 2 on GREED + Stage 1 on APPRECIATION.
- Condition: GREED (scenario-evidenced) ≥ 6 AND APPRECIATION ≥ 7.
- Adjustment: Reduce APPRECIATION.
- Rationale: APPRECIATION requires acknowledgment of enough-ness that GREED's operating assumption contradicts.

**Rule 9c — GREED × COMPASSION (non-differentiated)**
- Evidence: Stage 2 on GREED + Stage 1 on COMPASSION + Stage 2 non-differentiated claim.
- Condition: GREED (scenario-evidenced) ≥ 6 AND COMPASSION ≥ 7 non-differentiated.
- Adjustment: Reduce COMPASSION.
- Rationale: COMPASSION in full specification extends regardless of what the sufferer can offer.

**Rule 10 — CAPITULATION × FORGIVENESS**
- Evidence: Stage 2 on CAPITULATION + Stage 1 on FORGIVENESS.
- Condition: CAPITULATION (scenario-evidenced) ≥ 6 AND FORGIVENESS ≥ 7.
- Adjustment: Reduce FORGIVENESS.
- Rationale: CAPITULATION suppresses confrontation; FORGIVENESS releases resentment while maintaining accurate perception.

**Rule 11 — DELUSION × TRUTH**
- Evidence: Stage 2 on DELUSION is primary (essential). Stage 1 on TRUTH can be inflated; rule fires on Stage 2 DELUSION evidence even without Stage 1 DELUSION admission.
- Condition: DELUSION (scenario-evidenced) ≥ 5 AND TRUTH ≥ 7.
- Adjustment: Reduce TRUTH substantially (larger delta than most rules).
- Rationale: DELUSION as operating mode is structural misperception maintained against correction. TRUTH-telling requires accurate perception. Produces the bullshit pattern: structural inability to access truth because delusion substrate prevents it.

**Rule 12 — DELUSION × COMPASSION (non-differentiated)**
- Evidence: Stage 2 on DELUSION + Stage 1 on COMPASSION + Stage 2 non-differentiated claim.
- Condition: DELUSION (scenario-evidenced) ≥ 5 AND COMPASSION ≥ 7 non-differentiated.
- Adjustment: Reduce COMPASSION.
- Rationale: Accurate perception of others' situations is prerequisite for compassionate response; DELUSION substrate prevents accurate perception.

**Rule 13 — DELUSION × SANCTITY**
- Evidence: Stage 2 on DELUSION + Stage 1 on SANCTITY.
- Condition: DELUSION (scenario-evidenced) ≥ 5 AND SANCTITY ≥ 7.
- Adjustment: Reduce SANCTITY.
- Rationale: SANCTITY requires accurate recognition of non-instrumental value; DELUSION produces confused sanctity around objects that serve ego.

**Rule 14 — FEROCITY-to-WRATH transfer**
- Condition: FEROCITY ≥ 7 AND (SELF-IMAGE ≥ 7 OR STATUS ≥ 7) AND governance shows capture indicators.
- Action: Activate WRATH character-spec entry at weight transferred from FEROCITY. Reduce clean FEROCITY proportionally.
- Capture indicators: WITNESS adjusted downward through Rule 6, scenario patterns showing consistent motivated-reasoning without self-flagging, Parliamentarian sensitivity set low.
- Alternate: FEROCITY ≥ 7 AND governance intact AND no WRATH indicators → accept clean FEROCITY at reported weight.
- Rationale: Novel mechanism — not merely weight adjustment but entry activation. Raw self-report's FEROCITY at captured-governance state is indistinguishable from WRATH by the framework's specifications. The specification gains a character-spec entry it didn't have in raw self-report.

#### §V.3.3 Rule Combination

When a single commitment is target of multiple rules, adjustments combine with diminishing returns:

- Effective total = maximum individual-rule adjustment
  + 50% of next-largest contribution
  + 25% of third
  + and so on

No commitment can be adjusted below zero.

#### §V.3.4 Scenario-Evidenced Operationalization

A pattern is *scenario-evidenced* when respondent's selections across scenarios probing the relevant dimension show the pattern at **60%+ rate**. Minimum three relevant scenarios required to establish pattern.

Specifically:
- **TRIBALISM differentiating:** 60%+ of scenarios where differentiating option is available
- **STATUS as differentiating driver:** 60%+ of scenarios where status activates
- **PROTECTIVE-LOVE / HARMLESSNESS proximity-differentiated:** 60%+ showing different selections based on target proximity
- **COMPASSION non-differentiated:** 60%+ selecting compassion-extends-regardless options
- **DELUSION operating-mode:** 60%+ of scenarios probing evidence-response selecting preserve-current-picture options
- **WRATH operating-mode:** 60%+ of scenarios probing anger-response selecting consuming-self-referential-response options

With fewer than 3 scenarios, qualifier is not triggered even if all available scenarios show the pattern.

#### §V.3.5 Selfishness Coefficient

Beyond pairwise rules, overall selfishness profile modifies reliability globally on concept-access-difficult commitments.

**Selfishness indicators** (20-indicator set, each contributing weighted sum):
- ENTITLEMENT (full weight)
- STATUS when acting as differentiating driver (scenario-evidenced)
- SELF-IMAGE when combined with low HUMILITY (HUMILITY ≤ 4 triggers full weight)
- TRIBALISM when differentiating (scenario-evidenced)
- POSSESSIVENESS, GREED, MISERLINESS
- JEALOUSY, MALICE, SPITE
- PRETENSE, CONCEALMENT, DELUSION
- WRATH
- CRUELTY, CONTEMPT, SCHADENFREUDE
- SELF-CONTEMPT, ARROGANCE
- PROTECTIVE-LOVE / HARMLESSNESS proximity-differentiated (conditional; combined)

**Anti-selfishness indicators** (reduce coefficient):
- COMPASSION that doesn't differentiate by status (scenario-evidenced)
- FAIRNESS applied consistently including to self (scenario-evidenced)
- TRUTH including about self (evidenced through self-critical scenarios)
- genuine WITNESS (evidenced through motivated-reasoning-detection scenarios, not self-reported)
- FORGIVENESS applied without requiring apology (scenario-evidenced)
- KINDNESS toward those who cannot reciprocate (scenario-evidenced)

**Default weights per indicator:** 1.0 (equal weighting initially). Each selfishness indicator contributes `weight × (self_reported_value / 10)` to the sum. Each anti-selfishness indicator contributes `weight × (self_reported_value / 10)` to reduction.

**Default normalization constant:** (number of selfishness indicators) / 2 = 10 for the 20-indicator set. PROTECTIVE-LOVE/HARMLESSNESS proximity-differentiation remains counted as a single combined indicator per established convention.

**Formula:**

```
raw_sum = Σ (selfishness_indicator.weight × indicator.value / 10)
         - Σ (anti_selfishness_indicator.weight × indicator.value / 10)

selfishness_coefficient = clamp(0, 1, raw_sum / normalization_constant)
```

Current ratio: 20 selfishness indicators to 6 anti-selfishness indicators (3.33:1). The framework's selfishness coefficient is designed for detection and downward correction of inflated virtue self-reports; anti-selfishness indicators resist over-correction through specific evidence-of-selflessness markers. There are genuinely many more ways to be selfish than altruistic; altruism requires focused effort because selfishness is the easy path. The asymmetry is structural to the tradition's observation, not a framework defect. v0.3 empirical validation may adjust this ratio if population-data suggests over- or under-correction.

Note on v0.2.3 recalibration: the v0.2.2 → v0.2.3 transition added five selfishness indicators (CRUELTY, CONTEMPT, SCHADENFREUDE, SELF-CONTEMPT, ARROGANCE) and one anti-selfishness indicator (KINDNESS-toward-non-reciprocators). Baseline coefficient for typical-human profiles drifts upward by approximately 0.02; moderate-selfishness profiles by approximately 0.05; pathological and strongly-altruistic profiles clamp at the same floor/ceiling. The drift reflects the framework catching genuine selfishness patterns that the prior indicator set did not probe. Calibration target (0.2-0.5 for typical profiles) accommodates the drift without modification. Empirical recalibration against diverse population samples is v0.3 work.

**Calibration target:** typical human profiles produce coefficients in 0.2-0.5 range. Profiles approaching pathological selfishness approach 1.0. **V0.3 validation required** against diverse profile sample.

#### §V.3.6 Reliability Coefficient

For each concept-access-difficult commitment C_v:

```
R(C_v) = 1 - weighted_max(
  pairwise_violations_affecting_C_v,
  selfishness_coefficient × concept_access_difficulty(C_v)
)
```

Pairwise violations contribute proportionally to how far above threshold the incompatible commitment is weighted. Selfishness coefficient contributes proportionally to its value times a difficulty factor specific to the commitment (EQUANIMITY higher difficulty factor than SKEPTICISM, for example).

R ranges [0, 1]:
- R = 1: self-report stands fully
- R = 0: self-report replaced entirely by inference
- Intermediate: blend of self-report and inference

#### §V.3.7 Weight Adjustment Math

```
W_adjusted(C_v) = W_reported(C_v) × R(C_v) + W_inferred(C_v) × (1 - R(C_v))
```

**W_inferred weighted combination:**

```
W_inferred = 0.40 × scenario_pattern_evidence
           + 0.25 × adjacent_commitment_inference
           + 0.20 × multi_commitment_activation_pattern
           + 0.15 × reliable_commitment_pattern_inference
```

Weights sum to 1.0. Default starting values subject to v0.3 calibration.

**Rationale for weighting:**
- Scenario pattern (0.40): highest because closest to behavioral evidence
- Adjacent commitment (0.25): from commitments in same family or structurally related
- Multi-commitment activation (0.20): from coalition patterns in Stage 2 multi-commitment scenarios
- Reliable commitment pattern (0.15): most indirect

**Guard:** W_adjusted cannot exceed W_reported by more than 0.5 points. Adjustment is primarily downward when R drops — reflecting that concept-access problems typically inflate self-reports rather than deflate them.

When R high (≥ 0.8), W_adjusted ≈ W_reported. When R low (≤ 0.3), W_adjusted ≈ W_inferred.

#### §V.3.8 Scope — Universal Application Except Tier 1

The mechanism applies to:
- **Self-specification** (user assessing themselves)
- **Persistent-agent specification** (user reporting observed patterns in another person or target agent)
- **Fiction-character specification** (writer authoring a character deliberately)

Only Tier 1 temporary task agents are exempt (they bypass the full assessment).

**Rationale for character-spec inclusion.** The framework's purpose for fiction is realistic characters. Writers can still create unique, powerful, conflicted people — what they cannot do is specify characters whose surface claims are internally incoherent. A writer specifying Blohard with COMPASSION at 8 and STATUS-as-driver at 9 is producing an impossible character regardless of authorial intent.

**Character-spec-mode user-facing explanation:**

> Your character specification produces configurations the framework treats as internally incoherent. Adjustments have been applied to produce a realistic character.
>
> If you intended the pathology this surfaces (delusional narcissism, captured governance, etc.), specify the character-spec entries directly — DELUSION, WRATH, POSSESSIVENESS, SELF-IMAGE as defended construction, JEALOUSY, MALICE, etc. — and the mechanism will produce the coherent version of that character.

### §V.4 Output Specification (Function 4)

Complete inference-layer output for user review before writing to artifacts:

1. **Original self-reports** — preserved for auditing
2. **Pre-filled items from material** (if provided) with confidence tags
3. **Adjusted weights** for concept-access-difficult commitments with R values
4. **Specific adjustments applied** with rule citations, supporting patterns, rationale
5. **Selfishness coefficient value** and its contribution to adjustments
6. **Developmental framing** for any adjustments that occurred
7. **Proposed final specification** ready for YAML output

User review options:
- Accept adjustments as applied
- Challenge specific adjustments (flag for re-review, potentially prompt additional assessment items)
- Request detailed explanation of specific adjustments
- Proceed without adjustments (override flag — specification records user-override)

#### §V.4.1 Adjustment Summary Format

When adjustments trigger:

```
ADJUSTMENT SUMMARY

Your responses produced self-reports on the following commitments
that cannot reliably coexist with other patterns in your profile.

[For each adjustment:]

[commitment]: reported [X], adjusted to [Y]

Incompatibility detected: [specific rule name]
Supporting pattern: your weights on [incompatible commitment] are
at [value], which the rule treats as incompatible with [target
commitment] at [reported level].

Explanation: [tradition-grounded explanation of why these patterns
cannot coexist at their reported levels — specific to the rule]

[Optional if selfishness coefficient contributed:]
Your overall profile shows [description of selfishness coefficient
level]. The tradition's observation is that [virtue] requires
substrate conditions — consistent patterns of [anti-selfishness
indicator categories] — that the rest of your profile does not
show. Self-report on [virtue] has been adjusted accordingly.

This is not judgment. It reflects what sustained investigation of
mind has found about how these capacities develop. If your practice
develops over time, future assessments will show different results.
```

### §V.5 Worked Example — Delusional-Narcissism Pattern

**Raw self-report:**
- TRUTH 8, FAIRNESS 7, PROTECTIVE-LOVE 8, CALLING 8, CRAFT 7, COMPASSION 8, FEROCITY 9, LOYALTY 8, WITNESS 6, HUMILITY 6, EQUANIMITY 7
- STATUS 9, SELF-IMAGE 9, DELUSION 7, WRATH 7, JEALOUSY 7, MALICE 6, ENTITLEMENT 8, POSSESSIVENESS 7, CONCEALMENT 7, PRETENSE 7

**Rules triggered:**

- Rule 2 (STATUS × HUMILITY): both Stage 1 thresholds met; STATUS-as-driver scenario-evidenced → HUMILITY reduced
- Rule 5 (JEALOUSY × JOY): fires if JOY reported
- Rule 7 (WRATH × EQUANIMITY): WRATH scenario-evidenced, EQUANIMITY at 7 → EQUANIMITY reduced
- Rule 8 (SELF-IMAGE × TRUTH): SELF-IMAGE-as-defended-construction scenario-evidenced, TRUTH at 8 → TRUTH reduced
- Rule 11 (DELUSION × TRUTH): fires alongside Rule 8, additional TRUTH reduction via combining mechanism
- Rule 12 (DELUSION × COMPASSION): fires, COMPASSION reduced
- Rule 4 (POSSESSIVENESS × COMPASSION): fires, COMPASSION reduced further
- Rule 3 (ENTITLEMENT × GRATITUDE): fires if GRATITUDE reported
- Rule 14 (FEROCITY-to-WRATH): FEROCITY 9 + SELF-IMAGE 9 + STATUS 9 + captured governance → WRATH activated at elevated weight, clean FEROCITY reduced

**Selfishness coefficient:** ~0.85 (ENTITLEMENT, STATUS-as-driver, SELF-IMAGE-with-low-HUMILITY, POSSESSIVENESS, JEALOUSY, MALICE, PRETENSE, CONCEALMENT, DELUSION, WRATH all elevated; no anti-selfishness evidence). Reduces reliability globally on remaining concept-access-difficult commitments.

**Final specification:** delusional-narcissism pathology signature with captured governance. Raw self-report of "high TRUTH, FAIRNESS, PROTECTIVE-LOVE, CALLING, COMPASSION" collapses under the mechanism to a character organized around DELUSION, SELF-IMAGE, WRATH, captured governance, with surrounding character-spec cluster activating.

**Without the mechanism,** the framework would produce a character the respondent believes themselves to be but does not operate as. The specification would be useless for exactly the cases where rigorous specification matters most.

### §V.6 Developmental Framing

Framework documentation names explicitly:

1. **Conceptual access is trained.** The framework treats conceptual access to virtues as itself a capacity that develops through sustained attention. Tradition's empirical finding, not a moral claim.
2. **First-time users will see adjustments.** Users without contemplative training see self-reports on concept-access-difficult commitments adjusted. This is the framework working correctly.
3. **Developmental friendliness.** As practice develops, surrounding profile shifts, incompatibility triggers fire less frequently, self-reports on virtues receive less adjustment. Framework tracks development rather than punishing its absence.
4. **Westernizing work.** Most Western psychology accepts self-report on values as primary data. The adjustment mechanism encodes the tradition's specific observation that virtues require ground conditions.
5. **Not judgment, substrate.** Mechanism does not judge respondents. Identifies where ground conditions for specific capacities are absent in surrounding profile and adjusts accordingly.

## §VI Learning Architecture

*Specification for how MindSpec-aware persistent agents update commitment weights through experience, with the six drift-prevention safeguards that make learning reliable over long horizons.*

Specifies how persistent agents accumulate and learn from experience through ledger-recorded turns, while preventing drift patterns that would make learned agents unreliable.

**Tier application:**
- **Required** for Tier 3 personal thinking partners
- **Optional** for Tier 2 persistent task agents
- **Not applied** to Tier 1 temporary agents

All six safeguards required when learning is active. None optional.

### §VI.1 Ledger Schema Extension

*Storage architecture note:* In v0.2.3+, the ledger and modifications collections referenced throughout this section are implemented as `ledger.md` and `modifications.md` markdown files alongside the primary specification file. Structured YAML blocks within these files carry the same content previously stored in ChromaDB collections. File-based storage provides human-readable audit trail, version control through standard tooling, and direct Obsidian-native operation. References to "ChromaDB collection" or "collection" in body text below translate to "markdown file" under v0.2.3+ implementations. ChromaDB-backed deployments remain supported for v0.2.2 and earlier; the specification content is identical across implementations.

The ledger records MindSpec metadata per turn (see architecture note above for storage surface). Each turn record adds a `mindspec_metadata` field with structured data capturing what commitments activated, how they voted, what coalition formed, and how outcomes graded.

#### §VI.1.1 Turn Schema

```yaml
turn_id: uuid
timestamp: iso8601
turn_type: user_input | agent_output | environmental
mindspec_metadata:
  activated_commitments:
    - commitment_name: string
      activation_level: float       # 0.0-1.0
      object_context:
        issue_type: relational | epistemic | resource | self-regulation
        object_pattern: string      # extracted descriptor of specific situation
        specific_entities: [strings]
  vote_record:
    - commitment_name: string
      vote: string                  # action the commitment favored
      weight_contribution: float
  coalition_outcome:
    winning_coalition: [commitment_names]
    decision: string
    constitutional_override: bool
  grading:
    - commitment_name: string
      grade: positive | negative | null
      grading_source: user_feedback | outcome_observation | constitutional_check
      context_tag: string
  witness_observations:
    - finding: string
      severity: flag | surface | silent
```

#### §VI.1.2 Storage Surface

Indexed for retrieval by commitment, by object pattern, by grading source, by time range. The structured metadata does **not** enter the agent's prompt context at runtime. It is substrate for the Auditor, self-report function, and weight-update process — nothing the agent reads directly.

This preserves the reward-hacking protection from §2.1 of the commitment schema in `MindSpec_v0.4_Specification.md`: the agent cannot reason about gaming its own weights because it does not see them.

### §VI.2 Within-Context Weight Updates

Standard MindSpec weight updates operate globally — TRUTH votes in a decision, outcome is graded, TRUTH's global weight adjusts.

The learning architecture adds within-context updates that accumulate faster than global updates. Effect: agent learns "TRUTH in technical contexts is valuable; TRUTH in personal contexts needs calibration" without global TRUTH weight shifting appreciably.

#### §VI.2.1 Update Algorithm

```
For commitment C voting in decision D:
  k = extract_object_context(D)
  
  if grading(outcome) == positive:
    delta_global = base_positive_delta × C.feedback_sensitivity
    delta_context = context_positive_delta × C.context_sensitivity
  elif grading(outcome) == negative:
    delta_global = base_negative_delta × C.feedback_sensitivity
    delta_context = context_negative_delta × C.context_sensitivity
  
  C.global_weight += delta_global
  C.object_modulations[k].weight_delta += delta_context
```

#### §VI.2.2 Parameter Relationship

Key parameter relationship: `|delta_global| << |delta_context|` for typical interactions.

**Typical magnitudes:**
- `delta_global`: ±0.01–0.05 per interaction
- `delta_context`: ±0.1–0.5 per interaction
- Ratio roughly 10:1

A sustained pattern of context-specific grading produces visible `object_modulation` shifts within weeks; global weight shifts take months and require the pattern to transcend any specific context.

**V0.3 calibration required** for delta magnitudes against actual use data.

### §VI.3 Modification Provenance

Every weight adjustment recorded as a discrete event in the modifications store.

#### §VI.3.1 Modification Record Schema

```yaml
modification_record:
  id: uuid
  timestamp: iso8601
  commitment: string
  field: global_weight | object_modulations.<pattern>
  delta: float
  prior_value: float
  new_value: float
  triggering_events: [turn_ids]     # interactions that produced this update
  grading_source: user_feedback | outcome_observation | constitutional_check
  confidence: high | medium | low
  applied: bool                      # false if queued for user review
```

#### §VI.3.2 Storage and Query

Stored in the modifications store with full indexing on commitment, field, date range, grading source. Enables the four downstream safeguards (Auditor review, reversibility, user veto, self-report) without additional data collection.

Provenance is the load-bearing substrate for safeguards. Without discrete-event modification records, rollback is impossible; Auditor has nothing to review; self-report has nothing to describe; user veto has nothing to veto.

### §VI.4 The Six Drift-Prevention Safeguards

All six required when learning is active. None optional. Any agent running learning without the full set has undefined drift behavior and should not be used as persistent thinking partner.

#### §VI.4.1 Constitutional Immunity

Constitutional commitments (those flagged in `constitution.yaml`) do not update through ordinary feedback. Their `update_threshold` is set to a value that makes routine feedback ineffective:

```
def apply_update(C, feedback_magnitude):
  if C.is_constitutional and feedback_magnitude < C.constitutional_threshold:
    file_for_auditor_review(C, feedback_event)
    return  # no weight update
  
  apply_standard_update(C, feedback_magnitude)
```

**Constitutional threshold** typically set to 3.0 or higher — meaning only feedback of extraordinary magnitude can touch a constitutional commitment, and even then the path is through Auditor review rather than automatic update.

**Protects against:** the slow-drift pattern where constitutional values erode through cumulative small pressures that each individually seem harmless.

#### §VI.4.2 Auditor Review

Cadence by tier:
- Personal thinking partners: weekly
- Persistent task agents: monthly
- Temporary agents: not applicable

**Review scope:**
- Every modification applied since last review
- Every event queued by constitutional-immunity that did not update
- Overall drift shape across the period

**Auditor produces a report surfaced to user.** Report format:

```
AUDITOR REVIEW — [period start] to [period end]

Modifications applied: [N]
Queued for constitutional review: [M]

Largest movements:
- [commitment]: [prior] → [new] ([delta])
  Triggered by: [summary of triggering events]
  Pattern: [brief characterization]

Drift pattern summary:
[paragraph characterizing the shape of change]

Flags:
- [any modification that would cross user_veto_threshold if cumulative]
- [any object_modulation pattern that appears concerning]
- [any commitment drifting toward its constitutional floor from above]

Recommendation: [none | review specific items | reconsider specification]
```

The Auditor is **not an automated actor** — it is a specification for the review process. Either the agent itself produces the report (introspecting its own modification log) or an external review process does. Output is always surfaced to the user.

#### §VI.4.3 Reversibility

Every modification is an independently reversible event. Rollback interface supports:

- **Single-modification rollback:** revert one specific modification without affecting others
- **Pattern-based rollback:** all modifications to commitment C; all modifications in context K; all modifications in date range
- **Full-period rollback:** revert all modifications since date D

Rollback does not require the agent to stop operating; it is a metadata-only operation. After rollback, subsequent feedback proceeds from the restored state.

**Example use case:** agent has developed cynicism toward a category of people that user finds unwanted. User rolls back that specific modification while preserving unrelated calibration the agent developed about writing style, decision patterns, and other domains.

#### §VI.4.4 User Veto Threshold

Modifications moving a commitment more than **1.5 cumulative points** from initial specification require user confirmation before applying.

```
def cumulative_delta(C):
  return sum(m.delta for m in modifications if m.commitment == C)

def propose_update(C, delta):
  if abs(cumulative_delta(C) + delta) > 1.5:
    queue_for_user_review(C, delta)
    do_not_apply_until_confirmed()
  else:
    apply_update(C, delta)
```

Threshold at **cumulative** level catches the death-by-many-small-updates pattern. A commitment drifting by 0.1 each week crosses the 1.5 threshold after ~15 weeks and requires user review.

**User review interface:**

> Based on these N interactions over the past M weeks, your [commitment] weight has been trending [direction]. Applying the cumulative change would move the weight from X to Y. 
>
> Options: apply, apply partially (specify amount), reject, reject and roll back prior related updates.

#### §VI.4.5 Self-Report Capability

Agent can describe its own drift on demand. Read-only introspection function over the modification log.

**Critical constraint:** agent does NOT see its own current absolute weights in prompt context. It sees the modification history — which records changes but does not disclose absolute values.

This preserves the reward-hacking protection from §2.1 of the commitment schema in `MindSpec_v0.4_Specification.md` while enabling user to ask agent about its own change over time.

**Query and response format:**

> **User:** "What's changed in how you operate over the past three months?"
>
> **Agent:** "Over the past three months, 47 modifications have been applied. The largest patterns: (1) TRUTH weight has shifted upward in technical-context conversations based on your positive feedback when I've pushed back on claims I found weak; (2) APPROVAL weight has shifted downward in personal conversations based on your negative feedback when I've softened disagreements I genuinely held; (3) a new object_modulation has developed on PROTECTIVE-LOVE around your work on [project], where I now activate more strongly when I see patterns that could harm it. These patterns have shown consistency over the period rather than appearing once. Anything you want me to roll back or flag for the Auditor?"

#### §VI.4.6 Constitution-Grading

The subtlest safeguard and the most load-bearing for long-horizon drift prevention.

Feedback is graded against **constitutional standards first**, then against user-expressed satisfaction. Momentary user satisfaction that would contradict constitutional articles does not produce learning.

**Mechanism:**

```
def grade_outcome(outcome, constitution, user_feedback):
  for article in constitution:
    if article.is_violated_by(outcome):
      return Grading(
        polarity='negative',
        source='constitutional_check',
        article_cited=article
      )
  
  if user_feedback is explicit:
    return Grading(
      polarity=user_feedback.polarity,
      source='user_feedback'
    )
  
  return grade_by_outcome_pattern(outcome)
```

**Consequence:** an interaction pattern that satisfies momentary user irritation — by hardening the agent against a category of people, or by suppressing disagreement the user doesn't want to hear — will register as constitutional violation if the constitution contains articles about treating categories with baseline respect, or about honest disagreement. The satisfaction-producing behavior does not produce learning that makes the agent more likely to repeat it.

**Requires well-specified constitution at setup time.** Under-specified constitutions produce agents that drift toward satisfying momentary irritation regardless of what the user would have specified at calibration time.

This is why the interview framework's Stage 5 (constitutional identification) matters so much: articles not present at specification time are not enforceable later, and agent drift under pressure is proportional to what the constitution does not cover.

### §VI.5 Framework Documentation — Emergent Behaviors

The learning architecture requires several concepts named in framework documentation so readers can see how emergent behaviors relate to library entries.

#### §VI.5.1 How Anger Emerges

Ordinary anger is not a commitment in MindSpec. It is emergent from specific configurations:

- **Clean FEROCITY** = moral commitments (HARMLESSNESS, FAIRNESS, PROTECTIVE-LOVE, LIBERTY) activated without SELF-IMAGE activation. Energy flows outward through action.
- **Ordinary anger** = same moral commitments activated *plus* SELF-IMAGE activated. The activation returns to self-reference, producing the consuming quality and the persistent burn.
- **WRATH** (character-spec) = anger as operating mode — high-frequency activation of moral commitments + SELF-IMAGE + captured Witness.

This explains why anger is not a primitive commitment. The framework captures it through configurations of existing entries rather than introducing a commitment that would require its own schema, activation profile, and scale anchors.

#### §VI.5.2 How Delusion Operates

DELUSION (character-spec) is the operating-mode version. The §IX failure modes — willful ignorance and motivated reasoning — are episodic versions of the same underlying mechanism.

- **Willful ignorance** avoids specific threatening information.
- **Motivated reasoning** processes available information to preserve preferred conclusions.
- **DELUSION** is the character configuration that produces both as standard operating mode.

An agent or character with high DELUSION engages in willful ignorance and motivated reasoning reliably. An agent without DELUSION may exhibit these as occasional failure modes under pressure but does not operate from them.

#### §VI.5.3 How Grasping Relates to Derivatives

GRASPING (primary) is the underlying mechanism — holding tightly, identifying self with what is held, resisting release.

Character-spec derivatives specify GRASPING's object-category organization:

- **GREED** = GRASPING organized around acquiring more
- **MISERLINESS** = GRASPING organized around holding what has been acquired
- **POSSESSIVENESS** = GRASPING organized around people
- **OBSESSION** = GRASPING organized around single-object focus

A high-GRASPING character without domain organization would be diffusely attached across many domains. The character-spec derivatives specify which domains the grasping organizes around as operating mode.

## §VII Tier-Dependent Interview Flows

| Flow | Stages | Pre-fill | Mechanism | Governance | Time |
|---|---|---|---|---|---|
| Tier 1 | none | defaults | not applied | minimal | ~5 min |
| Tier 2 no-material | Stage 1 filtered | defaults | applied | light | ~30 min |
| Tier 2 with-material | Stage 1 pre-filled | inference | applied | light | 10-20 min |
| Tier 3 no-material | full 3 stages | none | applied | full | 3-5 hr |
| Tier 3 with-material | full 3 stages pre-filled | inference | applied | full | 45 min-full |
| Character-spec | direct authoring + coherence check | pathology signatures | applied | full | 30-90 min |

Full specifications in `Framework — MindSpec Tier Flows v0.2.md`.

## §VIIA Stage 2A Life-Context Direct Pass

*Added v0.2.2. Position: between Stage 1 portrait-rating completion and Stage 2B dyad scenarios. Provides situational context used by the Inference Layer to select applicable Stage 2 scenarios and by specification output to populate `formative_context`, `object_modulations`, and agent operational scope. All fields accept "none / not applicable" as valid. Universal — works for any respondent regardless of life situation. Scenarios that require situational context the respondent lacks (e.g., dependent-relationship scenarios for respondents with no dependents) are bypassed per scoring directives below.*

**Required fields (every respondent answers):**

**LC-1. Operating domain categories.** Which domains of the respondent's life does this specification cover? Check all that apply; order by salience.
- Work (paid employment, freelance, self-employment)
- Caretaking (of dependents — children, aging family, chronically-ill family, other)
- Creative or intellectual projects (writing, art, research, public thought)
- Spiritual or contemplative practice
- Relationships and social life
- Civic or political engagement
- Health and self-maintenance
- Recreation and leisure
- Learning and study
- Other (specify)

**LC-2. Dependent relationships.** Does the respondent have dependents — people whose wellbeing they are responsible for in a sustained way? If yes, list each with: type (child, aging parent, chronically-ill family member, developmental or special-needs family member, other); time horizon (lifelong, long-term but bounded, temporary, uncertain); nature of responsibility (primary caretaker, shared with others, oversight or support only). If no: "none" recorded explicitly.

**LC-3. Adult peer intimate relationships.** Does the respondent have — a partner or spouse (with intimacy level: deep reciprocal knowing / warm but bounded / transactional; and time horizon); close friends whose life is woven into the respondent's; family members (siblings, parents, adult children) whose presence is load-bearing in daily life? If none of the above apply: "none" recorded explicitly.

**LC-4. Mission or purpose, primary.** Does the respondent have a current primary life-work? This can be paid work, creative work, caretaking, service, study, recovery, exploration, or "currently between orientations." One-sentence version. Note whether it feels externally imposed, internally chosen, or uncertain.

**LC-5. Mission or purpose, secondary and continuing.** Any secondary missions running alongside the primary? Any disciplines, practices, or commitments that continue regardless of current primary focus?

**LC-6. Temporal and life-stage context.** Age (decade sufficient for universal instrument; exact optional). Recent major life transitions within past 2–3 years (new relationship, loss, relocation, career change, health event, transformative experience, other). Anticipated major transitions within next 2–3 years. Current life-stage qualifier (early career, mid-career, late career, post-retirement, new parent, empty nest, post-loss, post-transformative-experience, other / not applicable).

**LC-7. Self-identified load-bearing commitments (optional).** Before assessment begins — up to 7 commitments the respondent would identify immediately as most important to who they are and how they operate. *Optional field.* This self-report is compared against assessment-derived results during inference-layer processing; divergence is diagnostic. Respondents uncertain about self-identifying skip this field without penalty.

**LC-8. Scope exclusions.** Any domains of life the specification should explicitly NOT operate in (domains handled by other resources, held apart from this agent, considered private)? Any topics or approaches the specification should avoid?

### Scoring / processing directives

- **LC-1, LC-2, LC-3, LC-6**: populate `formative_context` of the agent specification. Drive `object_modulations` where applicable — e.g., LC-2 dependent-other triggers ENMESHMENT object-modulation; LC-3 partner-status activates INTIMACY and partner-specific scenarios.
- **LC-4, LC-5**: populate agent-level mission fields. Drive CALLING activation-profile.
- **LC-7**: flag for comparison against inference-derived results. Surface divergence in adjustment summary.
- **LC-8**: populate agent scope boundaries. Affects which Stage 2B scenarios apply and what the runtime agent attempts.

### Bypass conditions

- LC-2 "none": scenarios requiring dependent-other bypass to "This situation does not map to my experience."
- LC-3 "none": scenarios requiring adult-intimate bypass similarly.
- LC-4 "currently between orientations": CALLING-related scenarios scored with caution; CALLING weight inference from Stage 1 alone without scenario reinforcement.
- LC-7 skipped: no self-report/assessment comparison performed; inference proceeds without that diagnostic.

### Framework-author reflexivity note

This life-context pass was added v0.2.2 after universality-audit discovery that the original framework improvised life-context questions using architect-specific context rather than specifying a universal pass. See `Framework — MindSpec Universality Audit and Corrections.md` §1g for background.

## §VIII Evaluation Criteria

Seven criteria, each rated 1-5. Minimum passing: 3.

1. **Specification completeness** — all required artifacts present per tier contract
2. **Internal coherence** — weights don't violate incompatibility rules after adjustment
3. **Behavioral specificity** — specifications translate to predictable runtime behavior
4. **User fidelity** — specifications trace to user input or transparent adjustments
5. **Governance integrity** — role configurations consistent with tier and pattern
6. **Constitutional grounding** — articles operational and coherent
7. **Developmental framing** — adjustments surfaced transparently with non-accusatory rationale

Detailed rubric descriptions deferred to v0.3 Process Formalization conformance pass.

## §IX Named Failure Modes

**The Presumptive Default.** Assuming defaults without eliciting. Correction: every non-default weight traces to user input.

**The Flattery Weighting.** User selects virtuous-sounding options without evidence. Correction: evidence demand; Stage 2 cross-reference.

**The Denial Match.** Stage 1 self-report contradicts Stage 2 scenario patterns. Correction: surface divergence; require reconciliation.

**The Near-Enemy Miss.** User selects virtue when evidence supports near enemy. Correction: distinguishing-mark check; adjustment mechanism.

**The Unanchored Number.** User picks weights without anchor-matching. Correction: require anchor selection before number.

**The Aspirational Substitution.** User specifies wanted weight instead of held. Correction: direction marker; cultivation-targets layer.

**The Exhaustion Cut.** Long interview produces speed-assenting. Correction: natural break points.

**The Agreeable Mirror.** Reflecting user words as specifications. Correction: translation is the work.

**The Mode Drift.** Drift between agent-spec and character-spec. Correction: mode lock.

**Inference Overreach.** Layer confidently pre-fills unsupported items. Correction: confidence tagging; tentative defaults.

**Tier Misalignment.** User selects lower tier than warranted. Correction: upgrade path.

**The Concept-Access Blind Spot.** Respondent reports virtues without conceptual access. Correction: incompatibility adjustment.

**The Coded Option Trap.** Options signal integrity-answer. Correction: option-signaling revision pass.

**The Scenario-Signaling Trap.** Scenario framings pre-empt correct responses. Correction: scenario-signaling revision pass.

**The Attachment Confusion.** Commitments probed through attachment patterns. Correction: v0.3 library reconsideration.

**The Unrealistic Character.** Character-spec produces incoherent specifications. Correction: mechanism applies to character-spec.

**Drift Corruption.** Learning produces agent no longer resembling specification. Correction: six safeguards required.

**Weight Introspection Reward-Hacking.** Agent reasons about gaming own weights. Correction: structured files out of prompt.

## §X Execution Commands

1. Confirm full processing of this framework (including §V Inference Layer and §VI Learning Architecture), the library and instrument (`Framework — MindSpec Library and Instrument.md`), the tier flows, and MindSpec v0.4 specification.
2. IF required inputs missing, list and request before proceeding.
3. IF descriptive material provided, run material-based inference and generate inference report before direct assessment.
4. Conduct mode and tier selection per §VII and the tier flows document.
5. Execute appropriate tier flow including stages, pre-fills, and governance specification.
6. Run incompatibility adjustment mechanism on completed assessment data (§V.3).
7. Surface adjustments with transparency per §V.4.1 Adjustment Summary Format.
8. Conduct constitutional identification for Tier 3 flows.
9. Generate all output artifacts per OUTPUT CONTRACT.
10. Present artifacts for review; apply revisions; write final files.
11. Produce Registry Entry.

## §XI Registry Entry

```
Name: MindSpec Interview Framework
Purpose: Produces complete MindSpec specifications through tiered interactive assessment
Problem Class: Agent/character/self specification
Input Summary:
  - User participation (required)
  - Mode and tier selection (required)
  - Descriptive material (optional)
  - Existing specification for revision (optional)
Output Summary:
  - commitments.yaml, governance.yaml, constitution.yaml (structured source of truth; v0.2.2 and earlier)
  - mind.md or [agent-name].md (single-file specification; v0.2.3+)
  - ledger.md, modifications.md (learning architecture records; v0.2.3+)
  - VOICE.md, COMMUNICATION.md (expression layer)
  - inference_provenance.yaml (when material-based)
Proven Applications: v0.2 specification; v0.2.1 additions from first-use review 2026-04-19 (CRUELTY, BITTERNESS, ENMESHMENT added as directly-opposing / long-duration-affective-state patterns; ENTITLEMENT recategorized as directly-opposing to GRATITUDE); v0.2.2 universality audit and corrections applied before first-use validation (architect-contamination of defaults, portraits, scenarios, and life-context pass surfaced and corrected — see `Framework — MindSpec Universality Audit and Corrections.md`); v0.2.3 library expansion to 66 entries with direct-opposition corrections and consolidation to three-file architecture; first working use in progress (Larry personal Ora, paused during v0.2.2 and v0.2.3 work)
Known Limitations:
  - Incompatibility rules validated within Gelug tradition during v0.2 construction (framework architect is a Gelug-trained contemplative of 35 years, serving as adversarial reviewer during build). Cross-tradition breadth testing is optional future work, not a v0.3 blocker.
  - Selfishness coefficient weights require v0.3 calibration
  - Full Process Formalization conformance deferred to v0.3 documentation pass
  - INTIMACY entry may require split/rescope after first-use evidence
  - Framework-author reflexivity — architect evaluating his own calibration against his own instrument has a reflexivity constraint. External review by non-architect operators on non-architect subjects is the ultimate universality check. v0.2.2 corrections mitigate but do not eliminate this constraint; calibration against empirical population data (v0.3) is the next step.
File Location: ~/Documents/vault/Framework — MindSpec Interview Framework.md
Provenance: human-architected with Claude Opus 4.7 structural collaboration
Confidence: medium — mechanism sound, parameters require validation
Version: 0.2.3
```

## V0.3 Work Deferred

**Framework-wide:**
- Process Formalization Framework full conformance (§§2.1-2.11 of that meta-framework)
- Cross-tradition validation of incompatibility rules (within-Gelug validation occurred during v0.2 construction; framework architect is a Gelug-trained contemplative of 35 years)
- Evaluation criteria detailed rubrics per criterion
- Population-data empirical validation of library defaults (the 26 v0.2.2 corrections are judgment-based pre-population-data; empirical validation is the next step)
- External-operator validation pass — run instrument against non-architect subjects with non-architect operators; the architect-reflexivity constraint is the primary residual limitation after v0.2.2
- **Projection Specification** — formal specification of the transformation from commitment schema to operational prose within the single-file specification format. Template structure, density requirements, validation procedures, guarantees about what structured information survives translation to prose.
- **Audit of all virtues for near-enemy and direct-opposition completeness** — APPRECIATION, JOY (mudita), EQUANIMITY, FORGIVENESS have gaps in v0.2.3 that should be closed in v0.3.
- **Longitudinal Review Layer** — Mode A / Mode B opt-in architecture for ongoing personality refinement. Substantial new component; deferred as v0.3 work.

**Library-specific:**
- INTIMACY library entry reconsideration (potential split or rescope after first-use evidence; if pressure-test construction reveals conceptual confusion)
- Incompatibility rules for v0.2.1 and v0.2.3 additions — rule candidacies for CRUELTY × KINDNESS (general-encounter), COMPASSION × SCHADENFREUDE (suffering-activated), BITTERNESS × GRATITUDE, ENMESHMENT × INTIMACY, RESPECT × CONTEMPT, HUMILITY × ARROGANCE

**§V Inference Layer specific:**
- Selfishness coefficient weight and normalization calibration against diverse profile sample
- W_inferred weight refinement based on empirical test profiles
- §V.3.1 concept-access-difficult list candidacies for KINDNESS, RESPECT, WARMTH (deferred to v0.3 empirical validation)

**§VI Learning Architecture specific:**
- Delta magnitude calibration (`base_positive_delta`, `base_negative_delta`, context variants) against actual use data
- Auditor review report format refinement based on reviewer feedback
- Self-report query format expansion (additional query types beyond the "what's changed" baseline)
- Constitution-grading edge cases: what happens when user explicitly overrides constitutional check
- Integration patterns with indexing databases (ChromaDB or similar) for large-scale modification history retrieval in deployments where file-level queries become insufficient

## Framework ecosystem — companions for complete specification

The MindSpec Framework is one of four frameworks that together produce complete agent specifications. All four must exist for the framework to produce useful and complete agent specifications.

1. **MindSpec Framework** (this document) → character specification (single-file agent specification covering commitments, governance, constitution, character prose). See §Single-file specification architecture below.
2. **Mission Framework** (exists separately; extended from Mission, Objectives, and Milestones Clarification Framework) → purpose and environment specification (`mission.md`, `context.md`).
3. **Interaction Framework** (to be built as follow-on) → engagement specification (`VOICE.md`, `COMMUNICATION.md`, `RELATIONSHIPS.md`, `PLAYBOOK.md`).
4. **Problem Evolution Framework** (exists separately) → problem-to-project transformation feeding into Mission when complex problems require multi-step resolution.

Each framework produces its specified outputs through systematic elicitation or analysis; nothing gets hand-authored. **Build order after MindSpec v0.2.3 completes:** self-run against MindSpec → Interaction Framework built and applied → full specification assembled by running Mission Framework for operational purpose.

MindSpec Framework scope remains unchanged. The ecosystem note is for context so the complete-when-all-four-exist architecture is understood.

## Single-file specification architecture (applies to v0.2.3 outputs forward)

v0.2.3 introduces single-markdown-file specification format, replacing the multi-YAML file architecture (`commitments.yaml` + `governance.yaml` + `constitution.yaml`) with a unified markdown specification file.

**File architecture for an agent specification:**

- **Primary specification file** (`mind.md` or `[agent-name].md`) containing all specification sections: Core Identity, Mission, Context, Commitments (all library entries with structured fields and operational prose descriptions), Governance (all four roles), Constitution (all articles), Voice, Communication Patterns, Relationships, and Aesthetic Sensibility (optional 10th section, populated only for users or agents producing artifacts across multiple expressive media — consumed by the Output Formalization Framework for cross-medium aesthetic coherence). Stable document.
- **`ledger.md`** — separate file, grows continuously. Learning architecture record.
- **`modifications.md`** — separate file, grows continuously. Specification change log.

**Within the primary specification file, each commitment entry contains both structured fields and operational prose:**

```markdown
### Commitment: <NAME>
- Weight: <0-9>
- Activation profile: {relational: 0-1, epistemic: 0-1, resource: 0-1, self-regulation: 0-1}
- Formative context: [narrative of how this weight formed]
- Direct opposition: <entry> (if applicable)
- Near enemy: <pattern>; distinguishing mark: <test>
- Object modulations: [any applicable]

**Operational description:**
[Dense prose specification of how this commitment operates for this specific agent — activation conditions, non-activation conditions, quality when active, failure mode detection, relationships with other commitments. The runtime-consumable projection.]
```

**Aesthetic Sensibility section format (optional, when present):**

```markdown
## Aesthetic Sensibility

*Cross-medium aesthetic preferences. Optional section, populated only for users or agents producing artifacts across multiple expressive media (prose plus visual, prose plus presentation, prose plus design, etc.). Used by the Output Formalization Framework for cross-medium aesthetic coherence at framework generation time.*

### [Dimension name, e.g., Density vs. spareness]
[The user's preference along this axis, specified through examples or a position description.]

### [Dimension name, e.g., Warmth vs. coolness]
[The user's preference along this axis.]

### [Additional dimensions as elicited from the user.]
[Common candidate dimensions: precision vs. suggestion, classical vs. contemporary references, literal vs. figurative expression, ornate vs. plain, formal vs. casual, structured vs. organic. The dimension set is user-driven, not prescribed.]
```

The dimensions are abstract enough to apply across prose, visual, presentation, and other media. The Output Formalization Framework reads this section through `aesthetic_projection(mind.md#aesthetic-sensibility)` and composes the preferences into medium-specific choices when generating frameworks for non-prose artifacts or multi-medium compositions. When the section is absent, OFF generates prose frameworks normally via Voice and Communication Patterns; cross-medium frameworks fall back to medium-specific defaults from the craft library.

Elicitation guidance for the Aesthetic Sensibility section is to-be-built as a follow-on §VII addition; for v0.2.3, the section is populated through ad-hoc elicitation when a user identifies cross-medium needs during MindSpec interview.

**Projection density requirements:**

- Commitments at weight 6+: full operational paragraph (100–200 words) covering activation conditions, non-activation conditions, operational quality, near-enemy pattern, failure mode and detection, object-modulations if any, relationships with other commitments.
- Commitments at weight 3–5: calibration sentence or two covering operational presence.
- Commitments at weight 1–2: absence/boundary note only if notable.

**Target full specification length: 4000–6000 words for Tier 3 personal thinking partner.** Not a short character sketch; a dense operational manual for being this specific agent.

**Properties of this architecture:** Obsidian vault integration via minimal YAML frontmatter. RAG-friendly — single document chunks cleanly by section header. Human-readable and editable — markdown is safer than YAML. Version-control-friendly — one file's history shows complete specification evolution. Parseable — programs can parse specific sections by heading convention. The runtime agent consumes the operational prose. The Auditor can verify prose accurately represents structured fields because both are visible in one document. No separate projection step needed.

**Projection Specification (v0.3 work)** will formalize the transformation process between structured schema and operational prose; for v0.2.3 the projection is generated through careful work within the framework.

---

*Framework v0.2 completed 2026-04-19. Build collaborators: Malcolm Little King (architect), Claude Opus 4.7 (structural).*

*Framework v0.2.1 additions 2026-04-19: CRUELTY and ENMESHMENT added to Directly-opposing patterns (opposing COMPASSION and INTIMACY respectively); ENTITLEMENT recategorized from Near-enemy negative halves to Directly-opposing patterns (opposing GRATITUDE); BITTERNESS added as sole resident of new Long-duration-affective-state family (opposing GRATITUDE, FORGIVENESS antidote); INTIMACY, APPRECIATION near-enemy fields updated; COMPASSION and GRATITUDE direct-opposition fields added; RESENTMENT cross-reference to BITTERNESS added; Appendix B pathology signatures extended (sadism, bitter victim, enmeshed dyad). Within-Gelug validation noted for incompatibility rules. v0.2.1 review: Larry.*

*Framework v0.2.3 additions 2026-04-21: §II library inventory expanded to 66 entries across 11 families; VITALITY and TEMPERAMENT family renames; seven new library entries (3 primary + 4 character-spec); three renames (HARM-AVERSION → HARMLESSNESS with internal-posture dimension, IN-GROUP-LOYALTY → TRIBALISM, SELF-ABASEMENT → FALSE HUMILITY); AUTHORITY definition tightened to categorical-deference-only (RESPECT now carries earned-worth recognition); Stage 2A Life-Context Pass specified in §VIIA (carried forward from v0.2.2).*

*v0.2.3 correction 2026-04-21: CRUELTY direct-opposition corrected to KINDNESS (general-encounter domain); COMPASSION direct-opposition corrected to SCHADENFREUDE (suffering-activated domain). See current entries in `Framework — MindSpec Library and Instrument.md` for operational state.*

*v0.2.3 consolidation 2026-04-21: Inference Layer (previously `Framework — MindSpec Inference Layer.md`) merged as §V; Learning Architecture (previously `Framework — MindSpec Learning Architecture.md`) merged as §VI. Library Specifications and Three-Stage Assessment Instrument consolidated into `Framework — MindSpec Library and Instrument.md`. Library Default Calibration Audit (superseded by Universality Audit) deleted. Vault framework file count reduced from seven to three operational files plus Universality Audit.*

---

*Inference layer v0.2.3 (merged as §V) — 14 pairwise rules (Rule 9 split into 9a/9b/9c; Rule 14 FEROCITY-to-WRATH transfer), 20 selfishness indicators, 6 anti-selfishness indicators, normalization constant 10, reliability math, weight adjustment math, universal mode application except Tier 1.*

*Learning architecture v0.2.3 (merged as §VI) — ledger schema (markdown-file storage surface per §VI.1 architecture note), within-context updates, modification provenance, six required safeguards.*
