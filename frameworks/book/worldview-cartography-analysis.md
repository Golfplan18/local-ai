
# Worldview Cartography Analysis Framework

*A Framework for Producing a Cartography of Competing Worldviews — Each Worldview's Foundational Commitments Surfaced, Cross-Paradigm Tensions Named Explicitly, Dialectical Synthesis Where the Paradigms' Own Terms Permit, Residual Incommensurabilities Preserved as Such.*

*Version 1.0*

*Bridge Strip: `[WCA — Worldview Cartography]`*

---

## Architectural Note

This framework supports the `worldview-cartography` mode, the depth-molecular operation in T9 (paradigm and assumption examination). The mode file at `Modes/worldview-cartography.md` carries the locked spec — molecular_spec.components, critical_questions, output_contract.required_sections — sufficient for the orchestrator to dispatch the three component modes (`paradigm-suspension`, `frame-comparison`, `dialectical-analysis` as synthesis stage rather than peer component) and the three synthesis stages (paradigm-inventory, cross-paradigm-tension-surfacing, dialectical-cartography). This framework adds the procedural detail the spec does not carry: the elicitation prompts the orchestrator uses, the intermediate output formats, the per-stage quality gates, and the worked example showing the framework operating end-to-end.

The framework sits in T9's stance ladder above `paradigm-suspension` (T9 stance-suspending, atomic, single-frame surfacing) and `frame-comparison` (T9 stance-comparing, atomic, multi-frame side-by-side). It composes those siblings with `dialectical-analysis` (T12 stance-thesis-antithesis) as a synthesis stage to produce a cartography that names where paradigms cohere, where they diverge irreducibly, and where dialectical resolution is available in the paradigms' own terms. WCA is the heaviest analytical mode in T9.

---

## How to Use This File

This framework runs when multiple worldviews are in play and the user wants the whole landscape mapped — each paradigm articulated on its own terms (via paradigm-suspension), comparatively positioned (via frame-comparison), then dialectically engaged where engagement is possible. WCA's value is in the synthesis stages: cross-paradigm tensions named explicitly (where paradigms make incompatible claims, where they speak past each other, where they share unrecognized common ground) and dialectical synthesis grounded in the paradigms' own terms rather than imposed from a meta-paradigm.

WCA differs from paradigm-suspension (single-frame surfacing without comparison) and from frame-comparison (multi-frame comparison without dialectical synthesis). Use WCA when the question is genuinely cross-paradigm, the user wants integrated cartography, and the time investment for molecular pass is warranted.

Three invocation paths supported:

**User invocation:** the user invokes `worldview-cartography` directly with a problem or debate spanning multiple worldviews. The framework opens with brief progressive questioning to elicit the paradigm inventory.

**Pipeline-dispatched:** the four-stage pre-routing pipeline classifies the user's prompt as T9, depth-molecular, and dispatches WCA.

**Handoff from another mode:** frame-comparison or paradigm-suspension has surfaced multiple paradigms in genuine tension warranting integrative synthesis. The handoff package includes the prior analyses; WCA inherits them as a starting position.

## INPUT CONTRACT

WCA requires:

- **Problem or debate** — the question or contested terrain across worldviews ("free will across compatibilist, libertarian, and hard-determinist frames," "consciousness across physicalist and panpsychist views," "economic value across marginalist and labor-theory traditions"). Elicit if missing: *"What's the problem or debate, and what worldviews or paradigms do you see in play?"*

WCA optionally accepts:

- **Paradigm inventory** — if the user has named paradigms, the framework uses them as a seed and tests breadth (Stage 1 should suspend each, including the analyst's home paradigm).
- **Prior frame analyses** — if the user has done preliminary frame work, the framework uses it as input.
- **Paradigm genealogies** — if the user has historical depth on the paradigms (Kuhnian/Foucauldian/MacIntyrean lineages), the framework integrates it.

## STAGE PROTOCOL

### Stage 1 — Paradigm Suspension (runs: full)

**Purpose:** Suspend each paradigm in the inventory — surface its foundational assumptions as testable propositions, audit observational vs. interpretive evidence symmetrically, assess load-bearing vs. peripheral assumptions, generate alternative interpretations grounded in observation. This must be done for EACH paradigm, including the analyst's home paradigm (failure mode: home-paradigm-bias).

**Elicitation prompt (orchestrator → model):**
> "You are running the `paradigm-suspension` mode (full) as Stage 1 of a Worldview Cartography pass. The problem or debate is: [problem]. Paradigms in play: [list — at minimum, the user-named paradigms plus the analyst's home paradigm; surface additional paradigms if the user's inventory missed major candidates]. For EACH paradigm, run the full paradigm-suspension output: foundational assumptions stated as testable propositions (use literal prefix 'Assumption N (testable):'), evidence audit tagging each item as observational or interpretive (apply the same standard to all paradigms), load-bearing assessment per assumption, alternative interpretations grounded in observation, evaluation. The Einstein guard rail must be honored — observation wins over preferred alternative. Suspend the home paradigm with the same rigor as the foreign ones."

**Intermediate output format:**

```yaml
stage_1_output:
  per_paradigm_suspension:
    - paradigm_name: "<>"
      home_paradigm: true | false
      foundational_assumptions:
        - assumption_id: A1
          testable_proposition: "Assumption N (testable): <claim>"
          load_bearing: load-bearing | peripheral
          load_bearing_reasoning: "<one-line>"
      evidence_audit:
        - evidence_id: E1
          tag: observational | interpretive
          symmetric_with_other_paradigms: true | false
      alternative_interpretations:
        - interpretation: "<grounded in observational evidence>"
          historical_analogue: "<paradigm revision precedent if any>"
      evaluation: paradigm-supported | paradigm-weakened | indeterminate
```

**Quality gates:**
- Each paradigm in inventory has been suspended (CQ1 of worldview-cartography: home-paradigm-bias means home paradigm specifically must be suspended too).
- Foundational assumptions stated as testable propositions, not conclusions (CQ1 of paradigm-suspension: assumption-as-conclusion).
- Evidence tagging symmetric across paradigms (CQ2: asymmetric-evidence-standard).
- Einstein guard rail honored (CQ3).
- ≥2 alternative interpretations per paradigm grounded in observation (CQ4).

**Hand-off to Stage 2:** the per-paradigm suspensions become input to frame-comparison.

---

### Stage 2 — Frame Comparison (runs: full)

**Purpose:** Position the paradigms comparatively — articulate each frame on its own terms (steelman within frame), surface core conceptual metaphors per frame, name moral or value commitments per frame, identify what each frame makes visible and what it obscures, name cross-frame translation difficulty and residual irreducibility.

**Elicitation prompt (orchestrator → model):**
> "You are running the `frame-comparison` mode (full) as Stage 2 of a Worldview Cartography pass. Paradigms suspended in Stage 1: [list]. For each paradigm, articulate the frame on its own terms with steelman-mode rigor (a thoughtful proponent must recognize this as the strongest version of their frame). Produce the full frame-comparison output: frames named and described (parallel structure across all frames — symmetric articulation), core conceptual metaphors per frame (Lakoff-style descent from stated positions to underlying metaphors), moral or value commitments per frame, what each frame makes visible, what each frame obscures (per-frame blind spots), cross-frame translation difficulty (where translation works and where it distorts), residual irreducibility (where one frame's commitment cannot be cashed out in the other's vocabulary without loss). Asymmetric articulation is a failure mode — apply equal depth to each frame."

**Intermediate output format:**

```yaml
stage_2_output:
  per_frame:
    - frame_name: "<from Stage 1 paradigm names>"
      description: "<articulated on frame's own terms>"
      core_conceptual_metaphor: "<source-domain → target-domain mapping>"
      moral_value_commitments: "<list>"
      what_frame_makes_visible: "<list — selection-in>"
      what_frame_obscures: "<list — selection-out / blind spots>"
  cross_frame_translation:
    - frame_pair: [A, B]
      translation_works_for: "<concepts that translate cleanly>"
      translation_distorts_for: "<concepts where translation loses meaning>"
  residual_irreducibility:
    - irreducibility_id: I1
      description: "<one paragraph — the conceptual remainder that resists translation>"
      paradigms_involved: "<list>"
```

**Quality gates:**
- Each frame articulated symmetrically (CQ1 of frame-comparison: asymmetric-articulation).
- Core conceptual metaphors surfaced per frame (CQ2: surface-position-only).
- What-each-frame-obscures populated for all frames (CQ3: blind-spot-omission applies equally).
- Residual irreducibility named where present (CQ4: false-translation).

**Hand-off to Synthesis Stage 1:** the paradigm-inventory stage receives Stage 1's per-paradigm suspensions and Stage 2's per-frame positioning.

---

### Synthesis Stage 1 — Paradigm Inventory

**Type:** parallel-merge

**Inputs:** Stage 1 (paradigm-suspension), Stage 2 (frame-comparison)

**Synthesis prompt (orchestrator → model):**
> "Consolidate the paradigm inventory: each worldview named, suspended (with foundational assumptions, load-bearing assessment, evidence audit), and comparatively positioned (with core metaphor, moral commitments, what-it-makes-visible, what-it-obscures). The integration should make each paradigm legible AS a paradigm — the suspension tells us what the paradigm assumes, the comparison tells us what the paradigm selects. Produce a structured per-paradigm block that fuses both: dominant claims of the paradigm, its hidden assumptions (from suspension), its characteristic blindspots (from comparison). Do NOT dissolve any paradigm into another's vocabulary — the cartography respects each paradigm on its own terms."

**Output format:**

```yaml
paradigm_inventory:
  per_paradigm:
    - paradigm_name: "<>"
      dominant_claims: "<from frame description>"
      foundational_assumptions: "<from Stage 1 suspension — load-bearing ones>"
      core_conceptual_metaphor: "<from Stage 2 comparison>"
      moral_value_commitments: "<from Stage 2>"
      what_paradigm_makes_visible: "<from Stage 2>"
      characteristic_blindspots: "<from Stage 2 obscured + Stage 1 suspension>"
      residual_alternatives_consistent_with_observation: "<from Stage 1>"
```

**Quality gates:**
- Per-paradigm blocks have parallel structure (no asymmetric articulation).
- Each paradigm's hidden assumptions and blindspots both populated.
- No paradigm dissolved into another's vocabulary.

---

### Synthesis Stage 2 — Cross-Paradigm Tension Surfacing

**Type:** contradiction-surfacing

**Inputs:** Synthesis Stage 1 (paradigm inventory)

**Synthesis prompt (orchestrator → model):**
> "Name cross-paradigm tensions explicitly. For each pair (or N-tuple) of paradigms, identify: (a) where paradigms make INCOMPATIBLE claims (one's assertion is the other's denial — direct conflict); (b) where paradigms SPEAK PAST each other (each paradigm's question is a non-question for the other; the apparent disagreement is structural rather than substantive); (c) where paradigms SHARE UNRECOGNIZED COMMON GROUND (each holds a commitment the other would endorse if articulated cross-paradigm). Tension-collapse is a failure mode (CQ2 of worldview-cartography) — resist the temptation to present paradigms as complementary when they are not. Where tensions are genuine, name them. Where translation distortions create apparent tensions that dissolve under careful translation, name that too."

**Output format:**

```yaml
cross_paradigm_tensions:
  incompatible_claims:
    - tension_id: T1
      paradigms_involved: [A, B]
      claim_A: "<>"
      claim_B: "<denial of A's claim>"
      tension_type: direct-incompatibility
      resolution_in_paradigms_own_terms: possible | not-possible
  speak_past_each_other:
    - tension_id: T2
      paradigms_involved: [A, B]
      A_question: "<which is non-question for B>"
      B_question: "<which is non-question for A>"
      tension_type: structural-mismatch
  shared_unrecognized_common_ground:
    - tension_id: T3
      paradigms_involved: [A, B]
      shared_commitment: "<what both would endorse if articulated cross-paradigm>"
      why_unrecognized: "<vocabulary or methodological reason>"
```

**Quality gates:**
- Cross-paradigm tensions named explicitly (CQ2 of worldview-cartography: tension-collapse).
- Three classes of tension (incompatible / speak-past / shared-common-ground) considered.
- Tensions are genuine (not artifacts of translation distortion).

---

### Synthesis Stage 3 — Dialectical Cartography

**Type:** dialectical-resolution

**Inputs:** Synthesis Stage 1 (paradigm inventory), Synthesis Stage 2 (cross-paradigm tensions), `dialectical-analysis` mode (invoked as the synthesis-stage operation)

**Synthesis prompt (orchestrator → model):**
> "Run dialectical analysis ON the cross-paradigm tensions to produce the final cartography. For each Tension where dialectical resolution might be possible (incompatible claims with internal contradictions in each paradigm; shared common ground with synthesis potential), apply the `dialectical-analysis` mode's protocol: state the thesis (Paradigm A's claim), surface its internal contradictions, develop the antithesis (Paradigm B's claim emerging from those contradictions), produce a sublation OR honor irreducibility (Adornian escape valve). The sublation, where possible, must use the paradigms' own terms — meta-paradigm-imposition is a failure mode (CQ3 of worldview-cartography). For Tensions where dialectical synthesis fails (positions do not generate each other internally; sublation would be averaging not transcending), declare residual incommensurability explicitly. Add a meta-level reflection: what does the cartography itself reveal about the problem space? (Answer: which paradigms structurally cannot dialogue, which can synthesize, where the field is and isn't open to further development.)"

**Output format:**

```yaml
dialectical_cartography:
  per_tension_dialectical_treatment:
    - tension_id: T_n
      paradigms_involved: "<from Synthesis 2>"
      dialectical_attempt:
        thesis: "<paradigm A's claim>"
        thesis_internal_contradictions: "<from suspension>"
        antithesis: "<paradigm B's claim emerging from contradictions>"
        sublation_or_irreducibility: sublation | irreducibility
        sublation_in_paradigms_own_terms: "<if sublation: the synthetic position grounded in both paradigms' vocabulary>"
        irreducibility_declaration: "<if irreducibility: why dialectical synthesis fails here>"
        recursion_acknowledgement: "<if sublation: next-level contradictions the sublation generates>"
  residual_incommensurabilities:
    - description: "<irreducible plurality preserved>"
      paradigms_involved: "<>"
  meta_level_reflection:
    what_cartography_reveals: "<one paragraph about the problem space>"
    paradigms_that_structurally_cannot_dialogue: "<list>"
    paradigms_with_synthesis_potential: "<list>"
    field_open_to_further_development_at: "<where>"
```

**Quality gates:**
- Sublations use paradigms' own terms, not meta-paradigm vocabulary (CQ3 of worldview-cartography: meta-paradigm-imposition).
- Where sublation fails, irreducibility declared explicitly (CQ4: premature-resolution).
- Meta-level reflection present (this is what makes WCA more than a multi-paradigm summary).

---

## OUTPUT CONTRACT — Final Artifact Template

```markdown
[WCA — Worldview Cartography]

# Worldview Cartography for <problem or debate>

## Executive Summary
- **Problem or debate:** <one-sentence>
- **Paradigms surveyed:** <count> — <one-line characterizations>
- **Cross-paradigm tensions identified:** <count> — <breakdown by class>
- **Dialectical syntheses achieved:** <count> in paradigms' own terms.
- **Residual incommensurabilities preserved:** <count>.
- **Meta-level finding:** <one-sentence about what the cartography reveals>.

## 1. Paradigm Inventory
[For each paradigm:]
- **Paradigm <Name>** (<one-line characterization>)
  - **Dominant claims:** <list>
  - **Foundational (load-bearing) assumptions:** <list — testable form>
  - **Core conceptual metaphor:** <source-domain → target-domain mapping>
  - **Moral / value commitments:** <list>
  - **What this paradigm makes visible:** <list>
  - **Characteristic blindspots:** <list — what the paradigm structurally obscures>
  - **Alternative interpretations consistent with observation:** <list>

## 2. Per-Paradigm Dominant Claims and Blindspots
[Cross-cutting summary table for ease of reference:]
| Paradigm | Dominant Claim | Core Metaphor | What It Sees | What It Misses |
|----------|----------------|---------------|--------------|----------------|
| A | ... | ... | ... | ... |
| B | ... | ... | ... | ... |
| ... | ... | ... | ... | ... |

## 3. Cross-Paradigm Tensions
### 3a. Incompatible Claims (direct conflict)
- **Tension T1:** Paradigm A asserts X; Paradigm B denies X.
  - Resolution in paradigms' own terms: <possible / not-possible — see §4>

### 3b. Speak Past Each Other (structural mismatch)
- **Tension T2:** Paradigm A's question Q1 is a non-question for Paradigm B; Paradigm B's question Q2 is a non-question for Paradigm A.
  - Why: <vocabulary, methodological commitment, or framing-level difference>

### 3c. Shared Unrecognized Common Ground
- **Tension T3:** Both paradigms hold commitment C; neither articulates it cross-paradigm.
  - Why unrecognized: <reason>

## 4. Dialectical Synthesis Where Possible
[For each tension where dialectical synthesis is attempted:]
- **Tension T_n:** <paradigms involved>
  - Thesis (Paradigm A's claim): <statement>
  - Thesis's internal contradictions: <surfaced from Stage 1 suspension>
  - Antithesis (Paradigm B's claim, emerging from those contradictions): <statement>
  - Sublation in paradigms' own terms: <synthetic position using both paradigms' vocabulary>
  - Recursion (next-level contradictions the sublation generates): <named>

## 5. Residual Incommensurabilities
[Where dialectical synthesis fails — the irreducible plurality preserved as such:]
- **Incommensurability I1:** <description>
  - Paradigms involved: <list>
  - Why dialectical synthesis fails here: <reason — positions do not generate each other internally; sublation would average not transcend; meta-paradigm imposition would distort>
  - Adornian escape valve invoked: <yes — irreducibility is the honest finding>

## 6. Meta-Level Reflection
[What the cartography itself reveals about the problem space:]
- <One paragraph: paradigms that structurally cannot dialogue; paradigms with synthesis potential; where the field is open to further development; what the persistence of incommensurability tells us about the problem.>

## 7. Confidence Map
| Finding | Confidence | Reason |
|---------|------------|--------|
| Suspension of Paradigm A's home assumptions | high / medium / low | <how well-anchored> |
| Cross-frame translation distortion claim T2 | ... | <evidence rigor> |
| Sublation T1 in paradigms' own terms | ... | <whether proponents would recognize> |
| Residual incommensurability I1 declaration | ... | <thoroughness of synthesis attempts> |
```

## WORKED EXAMPLE WALKTHROUGH

**Opening prompt (user):** *"I want a real cartography of the consciousness debate. Physicalists, panpsychists, and idealists each claim the others are missing something fundamental. I want to see where they actually clash, where they're talking past each other, and where (if anywhere) they could synthesize."*

**Stage 1 output (paradigm-suspension on each):**
- **Physicalism** (home paradigm for most analytic philosophy of mind): Assumption A1 (load-bearing): "Consciousness is identical to or wholly determined by physical processes." Evidence audit: brain-lesion correlations, neural correlates of consciousness — observational; the inference from correlation to identity — interpretive (interpretive load is doing significant work). Alternative interpretation grounded in observation: same correlations consistent with consciousness as fundamental and brain as receiver/transducer. Einstein guard rail: observation supports correlation; identity claim is interpretation, not observation.
- **Panpsychism**: Assumption B1 (load-bearing): "Consciousness or proto-consciousness is fundamental and ubiquitous; complex consciousness emerges via combination." Evidence audit: explanatory parsimony argument vs. emergentism — interpretive; Galileo's distinction between primary/secondary qualities — observational/historical-philosophical context. Alternative interpretation: panpsychism's combination problem (how do micro-experiences combine into unified macro-experience) is itself a form of the hard problem, possibly insoluble.
- **Idealism**: Assumption C1 (load-bearing): "Consciousness or mind is fundamental; physical reality is appearance within or for consciousness." Evidence audit: Berkeley's epistemological argument (can only know perceptions) — interpretive but with observational anchor; the necessity of an experiencing subject for any observation — observational structurally. Alternative: cosmopsychism (one universal consciousness with individuated perspectives) vs. analytic idealism (Kastrup) vs. classical Berkeleyan idealism — multiple sub-paradigms within "idealism."

**Stage 2 output (frame-comparison):**
- Physicalism: core metaphor "mind-as-machine/computation" (Lakoff: BRAIN AS COMPUTER); moral commitments: epistemic humility about subjective experience, methodological naturalism, alignment with sciences. Visible: causal closure, neural mechanism. Obscures: phenomenal character, the "what it is like."
- Panpsychism: core metaphor "consciousness-as-fundamental-property" (analogous to MASS or CHARGE); moral commitments: explanatory unity, taking subjective experience seriously. Visible: combination problem, explanatory simplicity. Obscures: how micro-consciousness combines, why specific neural arrangements yield specific experiences.
- Idealism: core metaphor "physical-as-appearance-within-mind" (analogous to OBJECTS-IN-DREAM); moral commitments: epistemic primacy of experience, refusal to bracket the experiencing subject. Visible: necessity of subject for any account, intractability of explaining consciousness from non-consciousness. Obscures: intersubjective regularity, predictive success of physics.
- Cross-frame translation: physicalist "mental state" translates roughly into panpsychist "macro-conscious state with microphysical substrate"; but physicalist "physical state" does NOT translate cleanly into idealist vocabulary (idealism: "physical states are perceptual or experiential structures within mind"; physicalist: "no, physical states obtain mind-independently"). Residual irreducibility: the phenomenal character of subjective experience.

**Synthesis Stage 1 (paradigm inventory):** structured per-paradigm blocks per the template.

**Synthesis Stage 2 (cross-paradigm tensions):**
- **Incompatible claims:**
  - T1: Physicalism asserts "consciousness is wholly determined by physical processes"; Idealism asserts "physical processes are appearances within consciousness." Direct incompatibility.
  - T2: Physicalism (most variants) asserts "matter exists mind-independently"; Panpsychism agrees but disagrees on whether matter has experiential properties; Idealism denies mind-independent matter.
- **Speak past each other:**
  - T3: Physicalism's question "what physical mechanism produces consciousness?" is a non-question for Idealism (consciousness is not produced; it's fundamental). Idealism's question "how does anything appear within consciousness?" is a non-question for Physicalism (consciousness is the explanandum, not the explanans).
- **Shared unrecognized common ground:**
  - T4: All three paradigms commit to taking subjective experience as a real phenomenon to be explained (none is eliminativist). Panpsychism and Idealism additionally share commitment to consciousness as fundamental in some sense; the dispute is over WHERE consciousness is fundamental (everywhere vs. universally).

**Synthesis Stage 3 (dialectical cartography):**
- **Dialectical attempt on T1:** Thesis (Physicalism: consciousness wholly determined by physical processes). Internal contradictions: causal closure of the physical entails epiphenomenalism for consciousness (Kim's argument); the explanatory gap remains structurally intractable (Levine). Antithesis (Idealism: physical states are appearances within consciousness) — emerges from the contradiction in physicalism's epistemic position (we only access physical states through consciousness, so consciousness is epistemically prior). Sublation attempt: dual-aspect theory — there is one underlying nature with both physical and mental aspects; physical and mental are not reducible to each other but are co-fundamental aspects of one substance/process. Sublation in paradigms' own terms: physicalism gets the causal-closure machinery (physical aspect is causally complete); idealism gets the epistemic primacy (mental aspect is epistemically prior). Recursion: dual-aspect theory generates new contradictions about the relationship between aspects — this is the next dialectical stage, not the terminus.
- **Dialectical attempt on T2 (physicalism vs. panpsychism):** Thesis (matter is purely physical with no experiential properties). Internal contradictions: explanatory gap between physical processes and phenomenal experience. Antithesis (matter has experiential properties at fundamental level — panpsychism). Sublation: not clearly available — panpsychism is itself a candidate sublation of physicalism, not a stage above which further sublation lies; alternatively, this might be irreducibility, with panpsychism and physicalism representing two coherent options that the evidence underdetermines.
- **Residual incommensurability declared on T3:** physicalism's "what physical mechanism" question and idealism's "how anything appears in consciousness" question do not generate each other — they are structurally non-translatable questions. The Adornian escape valve is invoked: this is irreducibility, not pre-synthesis. The cartography preserves both questions as legitimate within their respective paradigms.
- **Meta-level reflection:** the cartography reveals (a) physicalism and idealism are dialectically engageable (dual-aspect theory is a real candidate sublation grounded in both); (b) physicalism and panpsychism may be at a stage where dialectical synthesis is not yet available — the field may need further empirical or conceptual development; (c) some questions are structurally non-translatable across paradigms and the honest finding is irreducibility, not premature synthesis.

## CAVEATS AND OPEN DEBATES

**Composition limit — home-paradigm bias.** The most subtle failure mode is the analyst's home paradigm slipping in unsuspended (CQ1: home-paradigm-bias). The framework requires that the home paradigm be suspended with the same rigor as the foreign ones. When the analyst is operating from within the analytic-philosophy tradition, physicalism is the home paradigm and must be suspended explicitly; when from within continental traditions, idealism or phenomenology may be home and must be suspended.

**Sublation in paradigms' own terms vs. meta-paradigm imposition.** The temptation to resolve tensions by introducing a third vocabulary (process philosophy, structural realism, etc.) that none of the surveyed paradigms would accept is strong; resist it (CQ3: meta-paradigm-imposition). The sublation must be recognizable AS a sublation by proponents of the paradigms involved, articulated in vocabulary they share or can endorse.

**Adornian escape valve discipline.** Honoring residual incommensurability is more honest than forcing premature resolution. Where dialectical synthesis fails, declare it (CQ4: premature-resolution). The cartography's value is in showing where the field is open to further development AND where it may not be.

**When to escalate sideways:** if during execution the user actually wants to choose between paradigms rather than map them, the operation is no longer cartographic. Route to a stance-bearing T15 mode (steelman per paradigm, then balanced-critique) downstream of WCA.

## QUALITY GATES (overall)

- All three components ran (paradigm-suspension per paradigm, frame-comparison, dialectical-analysis as synthesis stage).
- Home paradigm suspended with the same rigor as foreign ones.
- Cross-paradigm tensions named explicitly (no tension-collapse).
- Sublations grounded in paradigms' own terms (no meta-paradigm imposition).
- Residual incommensurabilities declared where dialectical synthesis fails (no premature resolution).
- Meta-level reflection present.
- Confidence map populated per finding (per paradigm, per tension).
- The four critical questions of `worldview-cartography` (home-paradigm-bias, tension-collapse, meta-paradigm-imposition, premature-resolution) are addressed.

## RELATED MODES AND CROSS-REFERENCES

- **Paired mode file:** `Modes/worldview-cartography.md`
- **Component mode files:**
  - `Modes/paradigm-suspension.md` (Stage 1)
  - `Modes/frame-comparison.md` (Stage 2)
  - `Modes/dialectical-analysis.md` (Synthesis Stage 3)
- **Sibling Wave 4 modes:** `Modes/argument-audit.md` (T1), `Modes/decision-architecture.md` (T3) — share the integrative-synthesis composition pattern.
- **Territory framework:** `Framework — Argumentative Artifact Examination.md` (T1 territory — adjacent treatment of frame-related work) and conceptual neighborhood with `Framework — Cross-Domain and Knowledge Synthesis.md`.
- **Lens dependencies:** kuhn-paradigm-incommensurability (required), foucault-discursive-formation (optional), rorty-final-vocabulary (optional), macintyre-traditions-of-inquiry (optional), hegelian-dialectic-aufheben (via dialectical-analysis), adornian-negative-dialectics (when irreducibility is in play), kahneman-tversky-bias-catalog (foundational).

*End of Worldview Cartography Analysis Framework.*
