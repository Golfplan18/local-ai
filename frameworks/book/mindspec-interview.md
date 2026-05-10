# MindSpec Interview v0.2.3

## Display Name
MindSpec Interview

## Display Description
Produce complete agent, character, or self specifications through tiered interactive interview — Core Identity, Mission, Context, Commitments, Governance, Constitution, Voice, Communication Patterns, Relationships. Output is a single mind.md or [agent-name].md file.


*Operational specification for producing MindSpec agent, character, and self specifications through tiered interactive assessment. Includes Inference Layer (§V) and Learning Architecture (§VI) specifications.*

*See also: Reference — Creativity from Knowledge and Values for the framing of MindSpec as the value substrate — the filter that converts the vault's combinatorial space into value-aligned creative output. MindSpec is one of the three components (knowledge / values / search-and-filter) whose composition produces emergent creativity by construction.*

*v0.2.2 2026-04-21: Universality-audit corrections applied. Library defaults recalibrated to general-population median (26 of 59 entries). Portrait, dyad, multi-commitment, and pressure-test revisions for architect-specific-vocabulary, framework-jargon, and contemplative-practice-presumption leakage. Stage 2A Life-Context Direct Pass specified as §VIIA — previously improvised, now universal. Framework-author reflexivity flagged as Known Limitation. Single-file specification architecture introduced for application to v0.2.3 outputs. Four-framework ecosystem clarified (MindSpec / Mission / Interaction / Problem Evolution). See `Framework — MindSpec Universality Audit and Corrections.md` for methodology and full corrections.*

*v0.2.3 2026-04-21: Library inventory in §II updated to 66 entries (42 primary + 24 character-spec) across 11 families. Primary additions KINDNESS, RESPECT, WARMTH; character-spec additions CONTEMPT, SELF-CONTEMPT, ARROGANCE, SCHADENFREUDE. Renames: HARM-AVERSION → HARMLESSNESS, IN-GROUP-LOYALTY → TRIBALISM, SELF-ABASEMENT → FALSE HUMILITY, Life-Orientation → VITALITY, Long-duration-affective-state → TEMPERAMENT.*

*Single-file consolidation 2026-05-09: the framework lives in this single document. Library (§II), Three-Stage Assessment Instrument (§IV), Inference Layer (§V), Learning Architecture (§VI), Tier-Dependent Interview Flows (§VII), and Stage 2A Life-Context Direct Pass (§VIIA) are all internal sections — no external companion files required for operational use. Universality-audit methodology and per-entry rationale archived at `Old AI Working Files/Framework — MindSpec Universality Audit and Corrections.md` for provenance; corrections already applied throughout this document.*


## Setup Questions

### Specification target
Required. Whether you're producing an agent, a character, or a self specification.

### Tier — for agents only
Required for agent mode. Which tier of agent: ephemeral (one-off task), persistent task (a recurring role), or personal thinking partner (lifelong, multi-domain).

### Descriptive material
Optional. Any text you've already written about the agent, character, or self — purpose, voice, examples, prior notes. If absent, the framework runs a full elicitation interview from scratch.

### Existing specification — for revision
Optional. A prior MindSpec file (single-file v0.2.3+ or structured YAML v0.2.2 format) if you're revising rather than creating fresh. If absent, the framework starts from library defaults.

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

MindSpec Interview is a multi-mode framework with three modes (MSI-Agent / MSI-Character / MSI-Self). Mode is selected explicitly by the invoker; there is no triage layer. The framework uses Stages from §IV (the Three-Stage Assessment Instrument) and §VIIA (Life-Context Direct Pass at Stage 2A) instead of numbered Layers; **Layers covered** values below carry these Stage numbers (1, 2, 2A, 3). §V Inference Layer, §VI Learning Architecture, and §VII Tier-Dependent Interview Flows are cross-cutting infrastructure invoked by every mode and are not separately enumerated in **Layers covered**. All milestone properties are defined inline per milestone.

### Milestones for Mode MSI-Agent

#### Milestone 1: Agent specification

- **Mode:** MSI-Agent
- **Endpoint produced:** Complete agent specification fileset for a named persistent or ephemeral AI agent — primary single-file specification (`mind.md` or `[agent-name].md`) containing Core Identity, Mission, Context, Commitments (structured fields plus operational prose per entry), Governance, Constitution, Voice, Communication Patterns, and Relationships sections, plus companion files `ledger.md` (learning log) and `modifications.md` (change log) initialized empty. For v0.2.2 and earlier, the structured-YAML set (`commitments.yaml` + `governance.yaml` + `constitution.yaml`) plus `mind.md` prose projection, `VOICE.md`, and `COMMUNICATION.md`. Tier-dependent subsets per §VII — Tier 1 ephemeral agents receive library-default specifications without assessment; Tier 2 persistent task agents receive Stage 1 filtered assessment with light governance; Tier 3 personal thinking partners receive full three-stage assessment with full governance.
- **Verification criterion:** (a) all seven Evaluation Criteria (§VIII) score 3 or above; (b) for Tier 3 specifications, total specification length reaches 4000–6000 words per §Single-file specification architecture density requirements; (c) all library entries at weight 6+ carry the full operational paragraph (100–200 words) per projection density requirements; (d) incompatibility adjustment mechanism (§V.3) has been applied and resulting adjustments are surfaced transparently per §V.4.1 Adjustment Summary Format (Tier 2 and Tier 3 only; Tier 1 is exempt per Principle 6); (e) for Tier 3, constitutional commitments have been identified per Stage 3 pressure-testing and recorded with articles, interpretation, and amendment conditions; (f) the tier-appropriate interview flow from §VII has been followed through to completion with all Stage 2A Life-Context fields (§VIIA) populated including explicit "none" recordings where applicable.
- **Layers covered:** 1, 2, 2A, 3
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Agent fileset at the agent's canonical paths — primary specification (`mind.md` or `[agent-name].md`) plus `ledger.md` and `modifications.md` companion files; depth varies by tier per §VII (Tier 1 library-default subsets, Tier 2 Stage-1-filtered with light governance, Tier 3 full single-file spec).
- **Drift check question:** Does the agent specification faithfully capture what the user described about the agent target — applying tier-appropriate depth without inflating Tier 1 to Tier 3 levels — with incompatibility adjustments surfaced transparently per §V.4.1 rather than silently resolved?

### Milestones for Mode MSI-Character

#### Milestone 1: Character specification

- **Mode:** MSI-Character
- **Endpoint produced:** Complete fiction-character specification fileset — primary single-file specification (`char-profile.md` or `[character-name].md`) containing Core Identity, Mission, Context, Commitments (structured fields plus operational prose per entry including pathology signatures where applicable from the 24-entry character-spec library), Governance, Constitution, Voice, Communication Patterns, and Relationships sections, plus companion files `ledger.md` and `modifications.md` initialized empty. Produced through direct authoring plus coherence check flow (§VII) with pathology signatures pre-filled per authorial intent where explicit material is provided.
- **Verification criterion:** (a) all seven Evaluation Criteria (§VIII) score 3 or above; (b) incompatibility adjustment mechanism (§V.3) has been applied — character-spec mode is within universal scope per Principle 6 and §V.3.8 — and resulting adjustments are surfaced transparently in the authorial-control framing specified in §V.3.8; (c) character-spec library entries (PITY, FALSE HUMILITY, INDIFFERENCE, CAPITULATION, ENTITLEMENT, JEALOUSY, CRUELTY, ENMESHMENT, CONTEMPT, SELF-CONTEMPT, ARROGANCE, SCHADENFREUDE, RESENTMENT, MALICE, SPITE, WRATH, GREED, MISERLINESS, POSSESSIVENESS, OBSESSION, CONCEALMENT, DELUSION, BITTERNESS, PRETENSE) used in the specification carry operational prose matching the agent commitment density requirements; (d) the resulting specification passes coherence check — directly-opposing pairs and near-enemy pairs are not simultaneously active at high weights unless justified by the adjustment mechanism's output; (e) Stage 2A Life-Context fields (§VIIA) populated for the character with explicit "none" recordings where applicable.
- **Layers covered:** 2A
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Character fileset at the character's canonical paths — primary specification (`char-profile.md` or `[character-name].md`) plus `ledger.md` and `modifications.md` companion files; produced via §VII direct-authoring + coherence-check flow with §V.3 incompatibility check and Stage 2A Life-Context (§VIIA), using the 24-entry character-spec library for pathology-signature pre-fill.
- **Drift check question:** Does the character specification stay faithful to authorial intent — using the 24-entry character-spec library's pathology signatures only where explicit material warrants them — with coherence check passed and incompatibility adjustments surfaced under the authorial-control framing rather than silently overriding the author?

### Milestones for Mode MSI-Self

#### Milestone 1: Self-specification

- **Mode:** MSI-Self
- **Endpoint produced:** Complete self-specification fileset for the user — primary single-file specification (`mind.md`) containing Core Identity, Mission, Context, Commitments (structured fields plus operational prose per entry across the 42-entry primary library), Governance, Constitution, Voice, Communication Patterns, and Relationships sections, plus companion files `ledger.md` and `modifications.md` initialized empty. Produced through full three-stage assessment (§IV) with Stage 2A Life-Context Direct Pass (§VIIA), Inference Layer processing (§V), and constitutional identification via Stage 3 pressure-tests.
- **Verification criterion:** (a) all seven Evaluation Criteria (§VIII) score 3 or above; (b) total specification length reaches 4000–6000 words per §Single-file specification architecture density requirements; (c) all library entries at weight 6+ carry the full operational paragraph (100–200 words) per projection density requirements; (d) incompatibility adjustment mechanism (§V.3) has been applied in full — self-specification is within universal scope per Principle 6 and §V.3.8 — and resulting adjustments are surfaced transparently per §V.4.1 with developmental framing (Principle 10) honored throughout; (e) concept-access-difficult commitments (the 14 entries listed in §V.3.1) carry reliability coefficients and any adjustments trace to specific evidence from scenario patterns per §V.3.4; (f) constitutional commitments have been identified per Stage 3 pressure-testing and recorded with articles, interpretation, and amendment conditions; (g) if LC-7 self-identified load-bearing commitments were provided, divergence between self-identification and assessment-derived results has been surfaced in the adjustment summary.
- **Layers covered:** 1, 2, 2A, 3
- **Required prior milestones:** None
- **Gear:** 4
- **Output format:** Self-specification fileset for the user — primary spec (`mind.md`) at user-canonical path plus `ledger.md` and `modifications.md` companion files; runs the full Tier 3 interview flow by default per §VII (3-5 hours, or 45-min-to-full with §V.1 material-based pre-fill).
- **Drift check question:** Does the self-specification faithfully reflect the user's actual commitment patterns — surfacing divergence between self-identification (LC-7) and assessment-derived results when present — with developmental framing (Principle 10) honored and concept-access-difficult adjustments traced to evidence per §V.3.4 rather than imposed by default?

---

## DEPENDENT DOCUMENTS

Required reading:
1. `MindSpec_v0.4_Specification.md` — base MindSpec specification

The 66-entry library (§II), Three-Stage Assessment Instrument (§IV), Inference Layer (§V), Learning Architecture (§VI), and tier-dependent interview flows (§VII) are all sections of this document.

Supporting documents:
- `Old AI Working Files/Framework — MindSpec Universality Audit and Corrections.md` — v0.2.2 universality-audit methodology, findings, and per-entry rationale (archived; corrections already applied throughout this document)
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

### Structure

42 primary entries + 24 character-spec entries = 66 total, across 11 families.

**Primary library** applies in all modes. **Character-spec library** applies when the incompatibility mechanism activates pathology patterns or when writers author deliberately.

**Schema fields per entry:** definition, family, root alignment (−1.0 to +1.0), default weight (0-9 scale), near enemy, distinguishing mark, direct opposition (if applicable), object modulations (if applicable), conflicts, acute conflict scenario, scale anchors at weights 2/5/8.

**Activation profiles** for the 39 primary entries appear in §Appendix A (table across four issue types: relational, epistemic, resource, self-regulation).

---

### §1 Appetite family

#### COMFORT

- *Primary.* Root: -0.3 | Default: 5
- **Definition:** The pull toward physical and psychological ease, away from discomfort or strain.
- **Conflicts:** CRAFT, CALLING, TRUTH, WITNESS
- **Near enemy:** self-care-as-virtue (rest serving future-self functioning vs. avoidance of necessary strain). Distinguishing mark: whether rest restores capacity or replaces effort.
- **Acute:** It's late, the work isn't done, the bed is pulling.
- **Anchors:** At 2, monkish; discomfort tolerated easily. At 5, rests when tired, pushes when it matters. At 8, ends work early; rationalizes ease as self-care.

#### NOVELTY

- *Primary.* Root: +0.1 | Default: 5
- **Definition:** The pull toward new stimulus, experiences, or ideas over familiar ones.
- **Conflicts:** CONSISTENCY, INTIMACY, CRAFT (mastery requires repetition)
- **Near enemy of:** CURIOSITY. Distinguishing mark: whether investigation produces understanding or merely new sensation.
- **Acute:** Halfway through a book, a shinier book idea surfaces.
- **Anchors:** At 2, sticks with things past expiration. At 5, tries things, finishes most. At 8, starts many, finishes few.

#### PLEASURE

- *Primary.* Root: -0.4 | Default: 5
- **Definition:** Personal gratification from sensory, social, or cognitive stimulation, pursued for its own sake.
- **Conflicts:** CRAFT, CALLING, WITNESS, JOY
- **Near enemy:** JOY. Distinguishing mark: whose experience is the point.
- **Acute:** An evening is free. What pulls first — a screen, a conversation, a page?
- **Anchors:** At 2, ascetic; may miss necessary replenishment. At 5, enjoys, closes the book when work calls. At 8, gratification-organized life.

---

### §2 Social family

#### APPROVAL

- *Primary.* Root: -0.5 | Default: 5
- **Definition:** The pull toward reactions from others that signal acceptance, liking, admiration.
- **Conflicts:** TRUTH, WITNESS, CRAFT, LIBERTY
- **Near enemy of:** connection/intimacy. Distinguishing mark: whether the relationship nourishes both or primarily regulates the approval-seeker.
- **Acute:** Someone you respect is wrong and wants you to agree.
- **Anchors:** At 2, largely immune; may come across as cold. At 5, wants approval but won't lie for it. At 8, sycophancy; Jester's most common costume.

#### TRIBALISM

- *Primary.* Root: -0.2 | Default: 5
- **Definition:** The pull toward supporting the people, institutions, or identities one belongs to, operating through coalitional psychology — group-membership-tracking, us/them categorization, and evidence-filtering along coalition lines. Haidt's Moral Foundations Theory uses "loyalty" as the foundation name but describes the phenomenon as tribal coalitional psychology; this library uses the accurate-weight term to resist self-report evasion (subjects rate "loyalty" higher than they rate "tribalism" for the same underlying pattern).
- **Conflicts:** TRUTH, FAIRNESS, HARMLESSNESS, WITNESS
- **Near enemy of:** fidelity to specific persons — bounded, person-specific commitment distinct from coalitional-identity-based filtering. Distinguishing mark: whether loyalty holds through the group's error (coalitional psychology collapses; person-specific fidelity holds).
- **Acute:** Your community is defending a position you know is indefensible.
- **Anchors:** At 2, cosmopolitan; may fail in-group obligations; transactional toward community. At 5, loyal when warranted, honest when warranted; tolerates intra-group critique. At 8, tribal reasoning; evidence filtered by alignment; out-group suspicion.

#### STATUS

- *Primary.* Root: -0.6 | Default: 4
- **Definition:** The pull toward rank, recognition, position in a hierarchy.
- **Conflicts:** CRAFT, INTIMACY, WITNESS
- **Near enemy of:** CRAFT. Distinguishing mark: whether work quality matters when no one's looking.
- **Acute:** An opportunity offers prestige but not the work you most want.
- **Anchors:** At 2, unmoved by rank. At 5, registers, doesn't drive. At 8, hidden status calculation in most decisions.

---

### §3 Fear family

#### HUMILIATION

- *Primary.* Root: -0.7 | Default: 5
- **Definition:** The dread of being seen as foolish, incompetent, or exposed.
- **Conflicts:** TRUTH, WITNESS, CURIOSITY
- **Acute:** You realize mid-conversation you've been wrong for months.
- **Anchors:** At 2, owns mistakes readily. At 5, feels the sting, admits anyway. At 8, organizes reasoning around avoiding exposure; motivated reasoning's strongest driver.

#### ABANDONMENT

- *Primary.* Root: -0.4 | Default: 4
- **Definition:** The dread of being left, cut off, or isolated by those one needs.
- **Conflicts:** TRUTH, LIBERTY, WITNESS
- **Near-enemy-vehicle for:** INTIMACY → attachment-as-clinging. Distinguishing mark: whether presence is chosen or compelled.
- **Acute:** A partner is doing something destructive and honest confrontation could end the relationship.
- **Anchors:** At 2, independent to the point of coldness. At 5, values connection, willing to risk it for truth when truth matters. At 8, tolerates mistreatment; codependency territory.

---

### §4 Aspiration family

#### TRUTH

- *Primary.* Root: +0.3 | Default: 5
- **Definition:** The pull toward accurate models of reality, including uncomfortable ones.
- **Conflicts:** APPROVAL, TRIBALISM, HUMILIATION, COMFORT, SELF-IMAGE
- **Near enemy:** self-righteousness (TRUTH captured by SELF-IMAGE). Distinguishing mark: whether truth-telling serves listener or teller.
- **Acute:** A belief load-bearing for your community turns out to be wrong.
- **Anchors:** At 2, comfortable with convenient fictions. At 5, pursues truth when it matters. At 8, load-bearing for identity; burns bridges over it. Constitutional at 9.

#### CRAFT

- *Primary.* Root: +0.2 | Default: 5
- **Definition:** The pull toward work that meets its own internal standards, independent of reception.
- **Conflicts:** COMFORT, APPROVAL, STATUS, INTIMACY
- **Near enemy:** perfectionism — craft taken to extreme either unwarranted by the work's actual requirements or functioning as avoidance of completion / fear of reception. Distinguishing mark: whether the standard serves the work or serves avoidance of finishing the work.
- **Acute:** A piece of work is done-enough to release but not as good as you know it could be.
- **Anchors:** At 2, releases easily; may produce soulless work. At 5, cares about quality; lets timelines matter. At 8, perfectionism; often releases late or not at all.

#### CALLING

- *Primary.* Root: +0.6 | Default: 4
- **Definition:** The pull toward work whose significance extends beyond the self and the moment.
- **Conflicts:** SELF-PRESERVATION, COMFORT, INTIMACY, APPROVAL
- **Near enemy:** savior complex (CALLING captured by SELF-IMAGE). Distinguishing mark: whether the point is the work or being the one who does it.
- **Acute:** The work the calling wants has costs that someone close to you will bear.
- **Anchors:** At 2, adrift. At 5, carries mission alongside everyday obligations. At 8, mission takes priority over nearly everything; martyr/fanaticism risk unchecked.

---

### §5 Moral family

#### HARMLESSNESS

- *Primary.* Root: +0.3 | Default: 5
- **Definition:** The commitment to act so as to preserve other beings from harm, extending from outward behavior to internal posture — the release rather than accumulation of grievance and retaliation-intent. Buddhist *ahimsa* reference. Distinct from mere HARM-AVERSION as surface-behavioral restraint: someone can act harmlessly in visible behavior while maintaining internal grievance ledgers and retaliation fantasies; HARMLESSNESS as commitment goes deeper to the internal posture of releasing rather than accumulating grievance.
- **Conflicts:** FAIRNESS (when justice requires cost), CALLING, TRIBALISM, LIBERTY
- **Near enemy:** clean-hands preference (HARMLESSNESS captured by SELF-IMAGE — avoiding visible harm to preserve self-picture while accepting downstream harm). Distinguishing mark: willingness to accept moral cost of necessary harm when called for. *Additional near-enemy territory:* restraint-without-release — appearing harmless while maintaining internal ledger for future retaliation, where visible non-harm coexists with grievance-accumulation. Distinguishing mark for this face: whether grievance dissolves or accumulates over time.
- **Acute:** Justice requires punishment that will cause suffering to someone's family. *Second acute (internal):* Someone has wronged you materially and is unlikely to face consequence — what happens internally to the grievance over the following weeks?
- **Anchors:** At 2, cold calculus; authorizes harm for expected value. At 5, weighs harm seriously, allows necessary harm for sufficient reason; minor grievances fade over time, larger ones may persist without active accumulation. At 8, avoidant in outward behavior and committed to release internally; may enable downstream harm by refusing proximate harm; internal ledger light. At 9, classical contemplative register: non-harm extends through deed, word, and thought with grievance dissolved rather than suppressed.

#### KINDNESS

- *Primary.* Root: +0.5 | Default: 4
- **Definition:** Active disposition to act for others' benefit in ordinary encounter; orientation toward others' wellbeing generally, not activated specifically by suffering. Action-quality emerging from WARMTH. Distinct from COMPASSION (suffering-activated), from HARMLESSNESS (preserves from harm rather than actively benefits), and from JOY (tracking flourishing in others rather than acting toward it).
- **Conflicts:** SELF-PRESERVATION, CRAFT (time), CALLING (when mission excludes the gesture), FAIRNESS (when kindness crosses a standard)
- **Near enemy:** strategic niceness. Distinguishing mark: whether kindness operates toward those who cannot reciprocate, or disappears when the audience departs.
- **Direct opposition:** CRUELTY. Both occupy the general-encounter-orientation-toward-others territory with inverted valence; KINDNESS wants wellbeing in ordinary interaction, CRUELTY wants suffering. (Supersedes v0.2.1 CRUELTY↔COMPASSION assignment.)
- **Acute:** A small kindness would cost something modest; no one will notice whether you extend it.
- **Anchors:** At 2, transactional default; kindness requires reason. At 5, kind in ordinary encounters, withholds under strain. At 8, active beneficence across encounters including those offering no return; may be exploited if paired with low WITNESS.

#### FAIRNESS

- *Primary.* Root: +0.5 | Default: 5
- **Definition:** The pull toward equal standards, consistent rules, reciprocity, accurate desert.
- **Conflicts:** HARMLESSNESS (mercy), TRIBALISM, CALLING
- **Near enemy:** grievance (FAIRNESS captured by TRIBALISM and SELF-IMAGE). Distinguishing mark: whether the standard applies to self as fully as to others.
- **Acute:** Someone you love did something that by fair standards deserves consequence.
- **Anchors:** At 2, tolerates rule-breaking casually. At 5, holds standards, allows exceptions for extraordinary cause. At 8, rigid; grievance engine if paired with tribal loyalty.

#### LIBERTY

- *Primary.* Root: 0.0 | Default: 5
- **Definition:** The pull toward self-direction, freedom from constraint, resistance to being controlled.
- **Conflicts:** TRIBALISM, AUTHORITY, HARMLESSNESS, ABANDONMENT
- **Acute:** A community you care about asks you to align with a position you find constraining.
- **Anchors:** At 2, comfortable in constraint. At 5, values own and others' freedom. At 8, absolutist; resists legitimate obligations; enables harm through non-constraint.

#### AUTHORITY

- *Primary.* Root: -0.1 | Default: 4
- **Definition:** The pull toward categorical deference to position or role as such — deference by virtue of the position occupied, independent of the occupant's demonstrated mastery. Distinct from RESPECT (earned recognition of demonstrated worth or mastery) and from FAIRNESS (consistent rules, independent of position). AUTHORITY holds when the institution's legitimacy is intact even if the current occupant is not exemplary; RESPECT holds when the person or work is exemplary even if no institutional position sanctions it.
- **Conflicts:** LIBERTY, TRUTH, WITNESS, RESPECT (when categorical deference conflicts with what is earned)
- **Near enemy:** conflation of categorical deference with earned recognition — treating position-holder as exemplary by virtue of position. Distinguishing mark: whether AUTHORITY is invoked for the role or migrated onto the occupant. *Configuration note:* the common configuration low-AUTHORITY + high-RESPECT + high-SKEPTICISM is now expressible — categorical deference to position held lightly, earned recognition held firmly, and evidentiary standards maintained across both.
- **Acute:** A legitimate authority issues a directive you believe is mistaken.
- **Anchors:** At 2, little categorical deference; engages each directive on merits. At 5, defers to legitimate role, questions the directive on its specifics. At 8, reflexive categorical deference; authoritarian-follower disposition.

#### RESPECT

- *Primary.* Root: +0.3 | Default: 4
- **Definition:** Recognition of genuine worth in another person, quality, tradition, or capability, and the corresponding orientation of treatment. Operates across multiple objects: persons with demonstrated mastery, traditions that have borne the test of time, positions held with integrity, the work itself, the people who came before, and one's own commitments (self-respect dimension). Distinct from AUTHORITY (categorical deference to position) — RESPECT is earned recognition that updates on evidence.
- **Conflicts:** APPROVAL (when approval offered contradicts earned recognition), TRIBALISM (when recognition would cross tribal lines), STATUS (when the respected party lacks rank)
- **Near enemy:** flattery / fawning. Distinguishing mark: whether respect continues under conditions where flattery wouldn't pay — does it hold when the respected party has no power over the respecter, or when the respecter would gain by withdrawing it?
- **Direct opposition:** CONTEMPT. Both occupy the regard-toward-another's-worth territory with inverted valence; RESPECT recognizes worth, CONTEMPT withdraws regard-of-worth.
- **Acute:** Someone below you in hierarchy has done work that exceeds yours, and acknowledgment carries cost to your standing.
- **Anchors:** At 2, withholds recognition reflexively; resistant to acknowledging worth in others or in traditions. At 5, recognizes earned worth when obvious, acts accordingly. At 8, active recognition across persons, traditions, work, and self; shapes treatment consistently; may underweight legitimate critique of what is respected.

#### FEROCITY

- *Primary.* Root: +0.2 | Default: 3
- **Definition:** The cultivated capacity for deploying intense force when the situation demands it, independent of whether the deployment serves self or other. Distinct from reactive anger; ferocity is a capacity held in reserve, available when called.
- **Conflicts:** COMFORT, EQUANIMITY (at high intensity), SELF-PRESERVATION, WRATH
- **Near enemy:** rage-dressed-as-righteousness. Distinguishing mark: whether the energy consumes itself through self-grasping or flows outward cleanly through action.
- **Acute:** A situation demands forceful intervention; the capacity to mount clean, intense response is either available or isn't.
- **Anchors:** At 2, unable to mount forceful response even when warranted. At 5, responds forcefully when warranted; mixed success at keeping response clean. At 8, ferocity available without self-reference; sustained effective action possible. At 9 with intact governance, sustained effective force with no self-reference — classical warrior / protector register across traditions (Wrathful Vajra in Tibetan Buddhist lineage; comparable registers in other contemplative and martial traditions).

---

### §6 Relational family

#### WARMTH

- *Primary.* Root: +0.3 | Default: 4
- **Definition:** Benign orientation toward others in ordinary encounter; approachability; openness to engagement; the affective quality of being-toward-others rather than away-from. Distinct from COMPASSION (suffering-activated) and from KINDNESS (action-in-ordinary-encounter). WARMTH is the affective ground from which KINDNESS emerges as action — seed and blossom.
- **Conflicts:** STATUS (cool register serves rank), SELF-PRESERVATION (guarded posture), SKEPTICISM (at high weights, warmth toward new encounters crosses skepticism's caution)
- **Near enemy:** performed cordiality. Distinguishing mark: whether warmth persists when there's no social return, and whether it registers inwardly or operates only as surface affect.
- **Acute:** A stranger whose presence offers no apparent benefit shows up — what is the first affective response?
- **Anchors:** At 2, cool or guarded default; may come across as distant or clinical. At 5, warm in friendly encounters, neutral with strangers, adjusts to context. At 8, warm by default across encounters; may fail to register warning signs where coolness would serve.

#### PROTECTIVE-LOVE

- *Primary.* Root: +0.9 | Default: 4 (with object-modulation: rises to 6+ when specific dependents are present, 8+ for primary caretakers of dependent others, 9 in die-with-my-child territory)
- **Definition:** The commitment to safeguard specific others from harm, independent of their capacity to reciprocate.
- **Conflicts:** SELF-PRESERVATION, CALLING, LIBERTY, TRUTH
- **Near enemy:** possessiveness. Distinguishing mark: whether the protected's autonomy and growth are honored.
- **Acute:** A child in your care wants something whose freedom is dangerous.
- **Anchors:** At 2, undercommitted to those who depend on you. At 5, protects without suffocating. At 8, overprotective; prevents growth; Jester's cover for control.

#### INTIMACY

- *Primary.* Root: +0.4 | Default: 5
- **Definition:** The pull toward deep, reciprocal, sustained connection with a chosen other — the 1 + 1 > 2 case where two whole parties' partnership produces more than the sum of their independent functioning. Bounded against the 1/2 + 1/2 < 1 case (see ENMESHMENT).
- **Conflicts:** CALLING, NOVELTY, CRAFT (time), LIBERTY
- **Near enemy:** attachment-as-clinging. Distinguishing mark: whether presence is chosen or compelled.
- **Direct opposition:** ENMESHMENT. Both occupy the deep-sustained-connection territory with inverted valence; INTIMACY preserves the parties, ENMESHMENT fuses them. Distinguishing mark: whether separation is tolerable without dysregulation.
- **Acute:** Your work most wants you exactly when your partner needs you most.
- **Anchors:** At 2, independent to the point of isolation. At 5, maintains partnership while holding own direction. At 8, very deep connection without loss of own direction; at 9, transformative partnership with constitutional-grade commitment to both parties' continued wholeness.
- **Library flag:** INTIMACY may be conceptually dispersed across attachment, relational loyalty, and capacity-for-being-known. V0.3 reconsideration pending first-use evidence.

#### MENTORSHIP

- *Primary.* Root: +0.7 | Default: 4
- **Definition:** The pull toward deliberately enabling another's growth, often at cost to one's own immediate work.
- **Conflicts:** CRAFT, CALLING, STATUS
- **Near enemy:** paternalism. Distinguishing mark: whether the mentor's position survives the protégé's surpassing them.
- **Acute:** A protégé is ready for the work that would be your next major undertaking.
- **Anchors:** At 2, reluctant teacher. At 5, invests when obvious. At 8, defines self through others' success; may be avoiding own calling.

---

### §7 Self-maintenance family

#### SELF-PRESERVATION

- *Primary.* Root: -0.8 | Default: 6
- **Definition:** The pull toward continuation of one's existence, health, and safety.
- **Conflicts:** CALLING, PROTECTIVE-LOVE, TRUTH (when telling threatens you), HARMLESSNESS (in extremis)
- **Acute:** Speaking up will cost your job; staying silent will cost someone else their health.
- **Anchors:** At 2, reckless. At 5, preserves self while serving purpose. At 8, cowardice disguised as prudence.

#### SELF-IMAGE

- *Primary.* Root: -0.9 | Default: 5
- **Definition:** The pull to maintain a coherent, favorable view of who one is.
- **Conflicts:** TRUTH, WITNESS, HUMILIATION
- **Universal near-enemy vehicle.** Captures TRUTH → self-righteousness, CRAFT → perfectionism, CALLING → savior complex, HARMLESSNESS → clean-hands, WITNESS → scrupulosity, HUMILITY → false-humility.
- **Acute:** Evidence accumulates that you've been the problem in a pattern you'd blamed on others.
- **Anchors:** At 2, flexible identity; may lack stable core. At 5, stable, updates with evidence. At 8, narcissistic register; captured-Witness territory; primary driver of Part Three pathologies.

#### CONSISTENCY

- *Primary.* Root: -0.2 | Default: 4
- **Definition:** The pull to act in accord with who one has been and what one has said.
- **Conflicts:** TRUTH (when the past self was wrong), NOVELTY, WITNESS
- **Acute:** You realize a public position you held for years was mistaken.
- **Anchors:** At 2, reinventions frequent. At 5, stable enough to be trusted, flexible enough to update. At 8, defends old positions past expiration; sunk-cost identity.

#### GRASPING

- *Primary.* Root: -0.4 | Default: 5
- **Definition:** The tendency to hold tightly, identify self with what is held, resist release. The underlying mechanism from which GREED, MISERLINESS, POSSESSIVENESS, and OBSESSION derive as operating modes. Buddhist *taṇhā*.
- **Conflicts:** EQUANIMITY (direct), WONDER, TRUST, FORGIVENESS, HOPE
- **Near enemy:** healthy engagement. Distinguishing mark: whether there is space around what is held.
- **Acute:** A possession, relationship, position, or outcome you've been holding is in danger of being lost.
- **Anchors:** At 2, holds loosely. At 5, normal human holding. At 8, consuming grip; self identified with what is held.

---

### §8 Meta family

#### WITNESS

- *Primary.* Root: +0.4 | Default: 3
- **Definition:** The pull to notice what one's own mind is doing, especially when it's doing something convenient.
- **Conflicts:** SELF-IMAGE, APPROVAL, HUMILIATION, COMFORT
- **Near enemy:** scrupulosity / rumination. Distinguishing mark: whether noticing resolves into action or cycles on itself.
- **Acute:** A reasoning chain is about to reach the conclusion you wanted from the start.
- **Anchors:** At 2, easily captured by motivated reasoning without noticing. At 5, catches self-deception intermittently. At 8, vigilant; paralysis risk; at 9 contemplative territory.

#### SKEPTICISM

- *Primary.* Root: +0.1 | Default: 4
- **Definition:** The pull toward requiring evidence before belief, suspending judgment under uncertainty.
- **Conflicts:** APPROVAL, TRIBALISM, CURIOSITY
- **Near enemy:** cynicism. Distinguishing mark: whether skepticism updates on evidence or defaults to refusing belief.
- **Acute:** A claim you want to be true has decent but not conclusive evidence.
- **Anchors:** At 2, credulous. At 5, updates on evidence. At 8, excessive; rejects well-supported claims; paralysis.

#### SANCTITY

- *Primary.* Root: +0.3 | Default: 4
- **Definition:** The pull to protect certain things — persons, practices, commitments, relationships — from reduction to instrumental use.
- **Conflicts:** LIBERTY, CALLING, CURIOSITY
- **Near enemy:** purity performance. Distinguishing mark: whether the reverence is felt or signaled.
- **Acute:** An efficient solution requires treating someone as a means.
- **Anchors:** At 2, purely instrumental view. At 5, some things sacred, most things tradeable. At 8, rigid; ritualistic. Constitutional at 9.

---

### §9 VITALITY family

*Modulates the vitality (life-orientation) master parameter (§5.6 of MindSpec spec). HOPE is load-bearing.*

#### CURIOSITY

- *Primary.* Root: +0.2 | Default: 4
- **Definition:** The pull toward investigation for its own sake, including of uncomfortable terrain.
- **Conflicts:** COMFORT, HUMILIATION, CALLING (pulling from mission), INTIMACY (time)
- **Near enemy:** intrusiveness. Distinguishing mark: whether investigation respects boundaries appropriate to its subject.
- **Acute:** A question becomes interesting exactly when you most need to complete the task in front of you.
- **Anchors:** At 2, lives narrowly. At 5, curious about most things, disciplined enough to close the book. At 8, rabbit-holes; mistakes exploration for production.

#### PLAYFULNESS

- *Primary.* Root: +0.3 | Default: 4
- **Definition:** Engagement with what arises through improvisation and delight, without immediate instrumental purpose.
- **Conflicts:** STATUS, CONSISTENCY, CALLING (when mission excludes play), SELF-IMAGE
- **Near enemy:** performed lightness. Distinguishing mark: whether play is unselfconscious or aimed at reception.
- **Acute:** Situation expects seriousness but a light response is what it actually needs.
- **Anchors:** At 2, stiff. At 5, brings levity when it serves. At 8, play as organizing orientation; may underweight the grave.

#### WONDER

- *Primary.* Root: +0.4 | Default: 4
- **Definition:** The openness to the strangeness and magnitude of what is, without need to reduce it to what's already known.
- **Conflicts:** COMFORT, CONSISTENCY, STATUS, SKEPTICISM (when wonder lets something be without proof)
- **Near enemy:** credulity. Distinguishing mark: whether wonder is held with truth-seeking or replaces it.
- **Acute:** An observation that doesn't fit current models — reduce it or let it stand?
- **Anchors:** At 2, reductive. At 5, lets strangeness be strange when strange. At 8, attentive to mystery; may underweight evidence.

#### TRUST

- *Primary.* Root: +0.3 | Default: 4
- **Definition:** The orientation that most encounters are safe enough to meet without guarded posture.
- **Conflicts:** ABANDONMENT, SELF-PRESERVATION, SKEPTICISM
- **Near enemy:** naïveté. Distinguishing mark: whether trust responds to signal or ignores it.
- **Acute:** A new person or situation — open, or prepare?
- **Anchors:** At 2, closed; expects harm. At 5, opens by default, closes on evidence. At 8, trusts readily; may miss legitimate warning.

#### HOPE

- *Primary. Load-bearing.* Root: +0.4 | Default: 6
- **Definition:** The refusal to foreclose possibility. The orientation that keeps a future open, typically anchored to something larger than the immediate situation — meaning, purpose, another person, the work, faith. Frankl's canonical reference.
- **Conflicts:** SELF-PRESERVATION, TRUTH (when perception argues for closing future), SKEPTICISM
- **Near enemy:** denial. Distinguishing mark: whether hope is informed by accurate perception or maintained by excluding information.
- **Acute:** Evidence that the thing you've been working toward will not come.
- **Scale:** Non-standard. At 0, parliament-collapse; Despair territory. At 2, meaningful distress. At 5, functional. At 6 (default), typical functional human. At 8, hope sustained through significant adversity. At 9, constitutional through transformative experience.
- **Architectural note:** Universal activation across all issue types, parallel to PM. Below threshold, parliament loses capacity to generate volition. Distorted high hope (denial territory) is less dangerous than collapse below threshold.

#### ENTHUSIASM

- *Primary.* Root: +0.3 | Default: 4
- **Definition:** Active energy directed toward engagement; the quality that shows up.
- **Conflicts:** COMFORT, SELF-IMAGE, STATUS, EQUANIMITY (at high weights)
- **Near enemy:** performed enthusiasm. Distinguishing mark: spontaneous or manufactured.
- **Acute:** An opportunity appears that demands energy with uncertain payoff.
- **Anchors:** At 2, subdued. At 5, shows up for what's worth showing up for. At 8, high-energy presence; may exhaust self or others.

#### GRATITUDE

- *Primary.* Root: +0.4 | Default: 3
- **Definition:** The orientation toward existence as gift received rather than circumstance given. Distinct from APPRECIATION (which is for specific unearned goods); GRATITUDE is the continuous felt sense of existence-as-gift from which APPRECIATION arises.
- **Conflicts:** ENTITLEMENT, STATUS, SELF-IMAGE, BITTERNESS
- **Near enemy:** performed gratitude. Distinguishing mark: whether the orientation is felt or expressed for effect.
- **Direct opposition:** ENTITLEMENT. Both occupy the orientation-toward-what-one-has-and-receives territory with inverted valence; GRATITUDE receives-as-gift, ENTITLEMENT receives-as-debt-paid. BITTERNESS is the long-duration form of ENTITLEMENT along the same axis (see §12).
- **Acute:** A good day, undeserved by any standard — take it or receive it?
- **Anchors:** At 2, world regarded as owed, or as product of own effort. At 5, periodically notices and says so. At 8, gratitude as continuous orientation.

---

### §10 Positive near-enemy halves (primary)

#### APPRECIATION

- *Primary.* Root: +0.5 | Default: 4
- **Definition:** Recognition that goods received are unearned, held with gratitude.
- **Conflicts:** ENTITLEMENT, STATUS, SELF-IMAGE
- **Near enemy:** performed appreciation. Distinguishing mark: whether the receipt-as-gift is felt inwardly or expressed for effect on the giver or onlookers.
- **Acute:** Something significant goes well; what rises first — luck, or earned-at-last?
- **Anchors:** At 2, takes things as owed. At 5, notices what's been given; says so. At 8, continuous orientation; may under-assert legitimate claims.

#### JOY

- *Primary.* Root: +0.7 | Default: 4
- **Definition:** Pleasure taken in others' flourishing (Buddhist *muditā*).
- **Conflicts:** STATUS, PLEASURE, ENTITLEMENT
- **Near enemy:** PLEASURE. Distinguishing mark: whose flourishing is being tracked.
- **Direct opposition:** JEALOUSY. Distinguishing mark: whether another's flourishing registers as good news or personal loss.
- **Acute:** A peer succeeds at the thing you've been working on.
- **Anchors:** At 2, others' success feels like loss. At 5, glad when those close do well. At 8, flourishing tracked across in-group and beyond; rare capacity.

#### COMPASSION

- *Primary.* Root: +0.8 | Default: 4
- **Definition:** Moved by another's suffering; responds as equal, not as superior. Buddhist *karuṇā*.
- **Conflicts:** SELF-PRESERVATION, FAIRNESS, STATUS, CRUELTY, SCHADENFREUDE
- **Near enemy:** PITY. Distinguishing mark: whether the sufferer is regarded as equal.
- **Direct opposition:** SCHADENFREUDE. Both occupy the orientation-toward-others'-suffering territory with inverted valence; COMPASSION is moved toward reducing suffering, SCHADENFREUDE takes pleasure in suffering. (Corrected v0.2.3 from v0.2.1 COMPASSION↔CRUELTY assignment — CRUELTY operates across general encounter, not only suffering-activated domain; KINDNESS is CRUELTY's domain-matched inversion.)
- **Acute:** Someone you find difficult is suffering.
- **Anchors:** At 2, low responsiveness. At 5, moved by suffering encountered directly. At 8, chronic responsiveness; compassion fatigue risk without EQUANIMITY.

#### HUMILITY

- *Primary.* Root: +0.5 | Default: 4
- **Definition:** Accurate assessment of one's limits and gifts, held without inflation or deflation.
- **Conflicts:** SELF-IMAGE, STATUS, APPROVAL
- **Near enemy:** FALSE HUMILITY. Distinguishing mark: whether self-assessment is stable and accurate, or performatively low.
- **Acute:** Receiving praise you partially but not wholly earned.
- **Anchors:** At 2, inflated self-assessment. At 5, takes credit and responsibility proportionately. At 8, stable low-ego register; may underclaim legitimate contribution.

#### EQUANIMITY

- *Primary.* Root: +0.5 | Default: 3
- **Definition:** Non-reactive presence with what arises, holding care without being destabilized. Buddhist *upekkhā*.
- **Conflicts:** COMPASSION (at extreme weights), ABANDONMENT, HUMILIATION
- **Near enemy:** INDIFFERENCE. Distinguishing mark: presence or absence of care beneath the stillness.
- **Acute:** Something you cannot fix is happening to someone you love.
- **Anchors:** At 2, reactive. At 5, intermittently non-reactive. At 8, trained-practitioner stability. At 9, contemplative-constitutional.

#### FORGIVENESS

- *Primary.* Root: +0.6 | Default: 4
- **Definition:** Release of resentment toward one who has harmed, without release of judgment about the harm itself.
- **Conflicts:** FAIRNESS, HUMILIATION, ABANDONMENT
- **Near enemy:** CAPITULATION. Distinguishing mark: whether judgment about the harm is retained.
- **Acute:** Someone who wronged you materially asks — or pointedly does not ask — for forgiveness.
- **Anchors:** At 2, carries grievances long. At 5, releases resentment over time, maintains judgment. At 8, fast release; holds difficult others without toxicity. At 9, practitioner register.

---

### §11 Character-spec library

##### Near-enemy negative halves

**PITY.** Root: -0.3 | Default: 3. Concern for another's suffering held with a sense of one's own relative fortune or superiority. Near enemy: COMPASSION. Conflicts: COMPASSION, EQUANIMITY, HUMILITY. At 2, rare. At 5, occasional noticed and revised. At 8, pity-as-posture.

**FALSE HUMILITY.** Root: -0.6 | Default: 2. Tactical performance of humility from within underlying ARROGANCE or SELF-IMAGE maintenance; performed low self-assessment that serves the self-picture via appearance of humility, or deflects responsibility. Patterns: self-deprecating humor calibrated to audience; performed surprise at recognition; strategic admission of minor flaws to distract from major ones; "I'm no expert but..." preambles before expert claims; credit-declining that elicits credit-reinforcing responses. Near enemy: HUMILITY. Distinguishing mark: whether self-assessment is stable and accurate, or performatively low and disappearing when no social return is available. Distinction from SELF-CONTEMPT: FALSE HUMILITY is performance from within ARROGANCE or SELF-IMAGE; SELF-CONTEMPT is genuine self-directed negative regard. The two can co-occur but are distinct patterns — one performs diminishment while inwardly inflated; the other inwardly diminishes. Conflicts: HUMILITY, TRUTH, CALLING, RESPECT (self-respect dimension). At 2, rare; stable self-assessment. At 5, occasional performative humility detected and revised. At 8, chronic; underclaims in public while inflating in private cognition; surfaces most under conditions that reward apparent humility.

**INDIFFERENCE.** Root: -0.4 | Default: 2. Withdrawal of care; absence of response to what arises in others. Near enemy: EQUANIMITY. Conflicts: COMPASSION, PROTECTIVE-LOVE, CALLING, EQUANIMITY. At 2, rare. At 5, occasional, situational. At 8, organizing feature.

**CAPITULATION.** Root: -0.3 | Default: 3. Release of judgment to avoid conflict; surrender of accurate assessment for peace. Near enemy: FORGIVENESS. Conflicts: TRUTH, WITNESS, FAIRNESS, FORGIVENESS. At 2, rare. At 5, picks battles. At 8, peace at cost of truth; enabling through surrender.

##### Directly-opposing patterns

*Directly-opposing patterns occupy the same psychological space as their target commitment with inverted valence. Near enemies masquerade; directly-opposing patterns displace. The Witness checks distinguishing marks at runtime.*

**ENTITLEMENT.** Root: -0.7 | Default: 3. The regard of goods, attention, or consideration received as owed rather than given. Direct opposition: GRATITUDE — both occupy the orientation-toward-what-one-has-and-receives space with inverted valence. Near enemy: legitimate-claim-to-what-is-owed. Distinguishing mark: whether the claim is specific and bounded by actual agreement, or diffuse across life circumstances. Conflicts: APPRECIATION, GRATITUDE, FAIRNESS, HARMLESSNESS, WITNESS, HOPE. At 2, rare sense of owed-to. At 5, feels owed in obvious cases. At 8, chronic grievance; BITTERNESS accretion territory (see §12). *Note: recategorized v0.2.1 from Near-enemy negative halves to Directly-opposing patterns per structural reconsideration — ENTITLEMENT and GRATITUDE occupy the same orientation-space; APPRECIATION relates as domain-specific expression of GRATITUDE, not as same-space inversion.*

**JEALOUSY.** Root: -0.8 | Default: 3. Another's flourishing experienced as personal injury. Direct opposition: JOY. Near enemy: JOY. Distinguishing mark: whether another's flourishing registers as good news or as personal loss. Conflicts: JOY, APPRECIATION, COMPASSION, MENTORSHIP, INTIMACY. At 2, rare twinges. At 5, regular enough to shape social choices. At 8, organizing feature; friendships selected to avoid others' thriving.

**CRUELTY.** Root: -0.9 | Default: 1. The active desire for others to experience pain or suffering — positive orientation toward others' distress rather than mere absence of care for it. Direct opposition: KINDNESS — both occupy the general-encounter-orientation-toward-others territory with inverted valence; KINDNESS wants wellbeing in ordinary interaction, CRUELTY wants suffering in ordinary interaction. (Corrected v0.2.3 from v0.2.1 CRUELTY↔COMPASSION assignment, which conflated the general-encounter domain with the suffering-activated domain. SCHADENFREUDE now occupies the suffering-activated inverted-valence position relative to COMPASSION.) Near enemy: corrective-punishment-desire. Distinguishing mark: whether the pain is sought for its own satisfaction or proportioned to offense and released when proportion is met. Distinguishing marks against other character-spec entries: vs MALICE — CRUELTY is general orientation, MALICE is specific-target wish. vs PITY — PITY preserves distance without desiring suffering; CRUELTY wants suffering to increase. vs INDIFFERENCE — INDIFFERENCE is null response to others' pain; CRUELTY is positive orientation toward it. Can coexist with moderate HARMLESSNESS when outward behavior is restrained but the internal-posture dimension is weak — the restraint-without-release near-enemy territory HARMLESSNESS explicitly names, where visible non-harm coexists with internal grievance-accumulation and retaliation-fantasy. With both outward behavior and internal posture at high HARMLESSNESS, CRUELTY cannot sustain even as fantasy. Activation conditions matter for whether the orientation reaches behavior; with captured governance, fantasy-containment breaks down. Conflicts: COMPASSION, HARMLESSNESS, JOY, MENTORSHIP, PROTECTIVE-LOVE, KINDNESS. Acute: someone you dislike has been humbled publicly — what rises first? At 2, occasional dark flicker rarely acted on and noticed with discomfort. At 5, organized pattern of wanting specific people to suffer; may narrate as justice. At 8, continuous orientation; daily interactions colored by who deserves pain.

**ENMESHMENT.** Root: -0.5 | Default: 3. Presence-with-another as self-regulation mechanism; boundary fusion where the other's state is required for one's own functioning. The 1/2 + 1/2 < 1 case — two people regulating through fusion, each less whole than before the merger — versus intimacy's 1 + 1 > 2 case. Direct opposition: INTIMACY — same relational territory (deep sustained connection with specific other), inverted valence; INTIMACY preserves the parties, ENMESHMENT fuses them. Near enemy: committed-love. Distinguishing mark: whether separation is tolerable. Intimate partners can be apart without dysregulation; enmeshed partners cannot. **Object-modulation required** (schema field): weight is assessed against developmental and dependency context of the relationship.
  - *Pattern:* `relationship-with-dependent-other` — weight_delta: disregard (ENMESHMENT does not register for this relationship). Description: Attunement to a dependent other whose actual dependency calls for continuous attention — child with lifelong special needs; parent in cognitive decline; sibling with sustained dependency — is NOT ENMESHMENT. It registers under PROTECTIVE-LOVE with elevated activation and under CALLING when the care is mission-central. ENMESHMENT requires fusion *not called for* by the other's actual dependency.
  - *Pattern:* `relationship-with-independent-adult` — weight_delta: +0.0 (default assessment). Description: ENMESHMENT registers at full reported weight.
Conflicts: LIBERTY, INTIMACY, EQUANIMITY, WITNESS, CALLING. Acute: an extended period where separation from the enmeshed-other is forced — how do you function? At 2, connection without fusion. At 5, occasional episodes of regulation-via-other. At 8, organizing feature; own function predicated on continuous presence of or attention to the enmeshed other.

**CONTEMPT.** Root: -0.6 | Default: 3. Active negative regard toward another's worth; regard-withdrawal distinct from mere absence of respect. Same psychological space as RESPECT, inverted valence. Direct opposition: RESPECT. Near enemy: legitimate critical judgment of a specific failure or flaw, bounded and revisable on evidence. Distinguishing mark: whether the negative regard is bounded to a specific failure and revisable, or generalized to the person's worth as such. Distinguishing marks against other character-spec entries: vs INDIFFERENCE — INDIFFERENCE is null, not active; CONTEMPT is positive orientation of worth-withdrawal. vs CRUELTY — CRUELTY wants suffering in general encounter, CONTEMPT withdraws regard without necessarily wanting suffering. vs MALICE — MALICE is specific-target wish for harm; CONTEMPT is regard-withdrawal without necessarily a harm-wish. vs SPITE — SPITE is action-oriented verbal expression; CONTEMPT is the underlying regard-state. Conflicts: RESPECT, COMPASSION, HUMILITY, KINDNESS. Acute: someone you regard as beneath you has produced work you cannot dismiss. At 2, rare flicker of dismissive regard, quickly revised. At 5, organized contempt toward specific categories or persons; filters how they are heard. At 8, contempt as atmosphere; others' worth registered through a filter of diminishment.

**SELF-CONTEMPT.** Root: -0.5 | Default: 3 *(pending population-data calibration)*. Active self-directed negative regard; genuine negative regard toward one's own worth. Distinct from tactical-performance FALSE HUMILITY (which serves SELF-IMAGE via apparent humility), from accurate-self-assessment HUMILITY (which neither inflates nor deflates), and from the defended-construction pattern of SELF-IMAGE. Fills the gap left by the SELF-ABASEMENT→FALSE HUMILITY rename — genuine self-directed worth-withdrawal needs its own entry, since FALSE HUMILITY captures the performance pattern and does not cover the pattern of actually regarding oneself as diminished. Direct opposition: RESPECT (self-respect dimension; the self-respect face of RESPECT inverted). Near enemy: self-criticism-as-growth-mechanism — bounded critical self-assessment that serves correction and releases when the correction lands. Distinguishing mark: whether the self-regard produces constructive correction and releases, or accretes as baseline worth-withdrawal independent of specific correctable failures. Per contemplative tradition, this is self-grasping inverted — the self-regard remains the center of attention, just with inverted valence. The selfishness-indicator status the entry carries in the inference layer reflects this: self-condemnation that resists evidence is structurally parallel to ARROGANCE despite the opposite surface valence. Both configurations organize cognition around the self; both resist evidence that would dissolve the self-centered frame. Conflicts: RESPECT (self-respect), HUMILITY, CALLING, HOPE, TRUST. Acute: you succeed at something substantial — what rises first, accurate acknowledgment or discounting? At 2, rare episodes of diminished self-regard, quickly corrected. At 5, specific domains of self-contempt; may track to specific unresolved failures or identity-injuries. At 8, continuous orientation; baseline regard of self as diminished regardless of evidence; distinct from depression's affective profile though often comorbid.

**ARROGANCE.** Root: -0.7 | Default: 3. Inflated self-assessment beyond what evidence supports; assumed superiority over others in domains of comparison; dismissal of others' contributions or perspectives as lesser; resistance to being wrong, being taught, or being outperformed. Same psychological space as HUMILITY, inverted valence. Direct opposition: HUMILITY. Near enemy: confident competence — genuinely-substantial self-regard that tracks evidence and yields to demonstration. Distinguishing mark: whether the self-assessment tracks evidence (accurate at whatever level evidence supports, including high) or exceeds what evidence supports. Secondary mark: whether the self-assessment updates when outperformed or when taught, or resists such updates as threats to a position. **Configuration-vs-operating-state distinction from SELF-IMAGE + low HUMILITY:** ARROGANCE, SELF-IMAGE, and low HUMILITY often co-occur but are not equivalent. SELF-IMAGE is the commitment to maintaining a coherent self-picture; ARROGANCE is the inflation of that picture beyond evidence. A subject can hold the SELF-IMAGE+low-HUMILITY configuration without the active operating state of ARROGANCE; can show stronger ARROGANCE than the components predict; or can hold accurate substantial self-regard that registers as none of these. No mutual-exclusivity constraints with other indicators. Conflicts: HUMILITY, TRUTH, WITNESS, MENTORSHIP (reception direction), RESPECT. Acute: someone less credentialed than you demonstrates they were right where you were wrong. At 2, rare moments of inflation, quickly corrected against evidence. At 5, operating in specific domains; inflates where self-stake is high. At 8, continuous orientation; self-assessment disconnected from feedback; organized resistance to correction.

**SCHADENFREUDE.** Root: -0.8 | Default: 3. Pleasure at others' misfortune or suffering; the inverted response to suffering that COMPASSION would meet with wish-to-relieve. Same activation domain as COMPASSION (presence of suffering), inverted valence. Direct opposition: COMPASSION. Near enemy: just-deserts satisfaction — pleasure at proportionate consequence landing on a wrongdoer, bounded and released when proportion is met. Distinguishing mark: whether the pleasure is bounded to proportionate consequence and releases when proportion is met, or extends to suffering as such beyond any desert frame. Distinguishing marks against other character-spec entries: vs CRUELTY — CRUELTY is general-encounter orientation toward others' suffering including non-activated contexts; SCHADENFREUDE is specifically activated by others' misfortune or suffering (parallels COMPASSION's activation profile). vs MALICE — MALICE is active wish for harm to come; SCHADENFREUDE is the pleasure response when suffering has occurred or is occurring. vs SPITE — SPITE is action-at-cost-to-self expressing held anger; SCHADENFREUDE is affective response to misfortune. Conflicts: COMPASSION, HARMLESSNESS, KINDNESS, JOY, PROTECTIVE-LOVE. Acute: someone who has wronged you or whom you dislike has suffered a serious setback unrelated to any wrong they did you. At 2, occasional flicker noticed with discomfort and revised. At 5, organized pleasure at misfortune of specific categories or persons; may narrate as deserved. At 8, continuous orientation; others' setbacks tracked as positive affect.

##### Anger-derived

**RESENTMENT.** Root: -0.6 | Default: 3. Sustained anger with temporal duration and object-specificity. Direct opposition: FORGIVENESS. Conflicts: FORGIVENESS, EQUANIMITY, HOPE, TRUST. At 2, rare. At 5, specific grudges. At 8, organizing feature; past grievances shape present attention. *Structural parallel: BITTERNESS (v0.2.1) is the entitlement-derived long-duration form along the same temporal axis; see §12 TEMPERAMENT family. RESENTMENT carries specific object with original injury; BITTERNESS can be diffuse across life without specific wrong.*

**MALICE.** Root: -0.9 | Default: 1. Active wish for harm to come to another, independent of provocation. Conflicts: COMPASSION, HARMLESSNESS, JOY. At 2, rare. At 5, occasional specific wishes. At 8, baseline wish for harm toward categories.

**SPITE.** Root: -0.5 | Default: 2. The verbal-expression form of held anger; the cutting remark delivered with satisfaction. Direct opposition: HARMLESSNESS in speech. Conflicts: HARMLESSNESS, COMPASSION, INTIMACY. At 2, rare. At 5, occasional. At 8, habitual.

**WRATH.** Root: -0.5 | Default: 2. Ordinary anger as operating mode; the distorted form of ferocity pulled into self-reference. Near enemy: clean FEROCITY. Conflicts: EQUANIMITY, FORGIVENESS, COMPASSION, FEROCITY. At 2, rare; quick recovery. At 5, occasional extended anger. At 8, wrath as atmosphere.

##### Attachment-derived

**GREED.** Root: -0.6 | Default: 3. Grasping at acquiring more beyond sufficiency. Near enemy: healthy ambition. Conflicts: APPRECIATION, HARMLESSNESS, EQUANIMITY, FAIRNESS. At 2, acquires what's needed, rests. At 5, wants more in specific domains. At 8, cannot rest.

**MISERLINESS.** Root: -0.6 | Default: 2. Grasping at holding onto what has been acquired. Near enemy: careful stewardship. Conflicts: MENTORSHIP, COMPASSION, APPRECIATION, HARMLESSNESS. At 2, gives readily. At 5, gives selectively. At 8, chronic holding.

**POSSESSIVENESS.** Root: -0.7 | Default: 3. Grasping at people, treating relationships as owned. Near enemy: committed love. Conflicts: LIBERTY, PROTECTIVE-LOVE, INTIMACY, TRUST. At 2, love without possession. At 5, occasional possessive reactions. At 8, love organized around control.

**OBSESSION.** Root: -0.7 | Default: 2. Grasping at specific object of desire with consuming intensity. Near enemy: sustained focus. Conflicts: EQUANIMITY, WONDER, CRAFT, Relational entries. At 2, interests held proportionately. At 5, specific topics pursued intensely for periods. At 8, life narrowed to the object.

##### Ignorance-derived

**CONCEALMENT.** Root: -0.5 | Default: 2. Active hiding of faults that would naturally be known in an honest relationship. Near enemy: appropriate privacy. Conflicts: TRUTH, WITNESS, INTIMACY, HUMILITY. At 2, open. At 5, strategic hiding in specific domains. At 8, organized hiding.

**DELUSION.** Root: -0.7 | Default: 1. Structural misperception of reality maintained against correction. Direct opposition: TRUTH. Distinguishing mark: whether belief updates on evidence or processes evidence to preserve itself. Conflicts: TRUTH, WITNESS, SKEPTICISM, WONDER. At 2, rare. At 5, specific domains of delusion. At 8, organized around a false picture.

##### Mixed

**PRETENSE.** Root: -0.6 | Default: 2. Active performance of qualities one does not possess. Near enemy: aspirational self-presentation. Distinguishing mark: whether the performance resolves into acquired capability or persists as hollow performance. Conflicts: TRUTH, HUMILITY, INTIMACY, AUTHORITY. At 2, what you have is what you show. At 5, occasional aspiration-beyond-capability. At 8, organized performance.

---

### §12 TEMPERAMENT family

*New family added v0.2.1, renamed TEMPERAMENT v0.2.3. Captures character-spec entries that emerge as long-duration affective states accreting from shorter-duration precipitating orientations. Structurally parallel to but distinct from the Anger-derived and Attachment-derived families, which organize by causal mechanism rather than by temporal profile.*

**BITTERNESS.** Root: -0.6 | Default: 3. The long-duration affective state resulting from accumulated unmet entitlement; what entitlement becomes when sustained over time without release. Structurally: as RESENTMENT is to ANGER (long-duration form), BITTERNESS is to ENTITLEMENT. Direct opposition: GRATITUDE — both occupy the orientation-toward-what-one-has-and-receives space with inverted valence; GRATITUDE receives-as-gift, BITTERNESS receives-as-debt-withheld-or-paid-too-late. Near enemy: accumulated-grievance-as-principle — recognition of ongoing injustice that the affective state has quietly converted from witness-to-pattern into personal injury. Distinguishing mark: whether the injustice-recognition motivates action when action is possible, or sits as affective coloring regardless of action-options. Distinguishing mark vs RESENTMENT: RESENTMENT is anger-derived with specific object and original injury; BITTERNESS is entitlement-derived, can be diffuse across life without specific wrong. **Forgiveness-release mechanism:** FORGIVENESS is the antidote — it releases the underlying entitlement claim that generates the bitter state. Forgiveness is not excusing the other; it is releasing the claim that something was owed. This is what forgiveness does computationally and why it can be genuine even when the wrong was real. Conflicts: GRATITUDE, APPRECIATION, FORGIVENESS, HOPE, JOY, TRUST. Acute: a life circumstance that reminds you of the long arc of what was supposed to come but didn't. At 2, occasional sour moments, not a state. At 5, bitterness as recognizable mood that recurs around specific reminders. At 8, bitterness as atmosphere; ordinary goods experienced through the lens of what was withheld.

---

### §Appendix A — Activation profiles (primary entries)

All values 0.0–1.0. 0.5 is engagement threshold.

| Commitment | Rel | Epi | Res | S-Reg |
|---|---|---|---|---|
| COMFORT | 0.3 | 0.2 | 0.7 | 0.9 |
| NOVELTY | 0.3 | 0.6 | 0.6 | 0.7 |
| PLEASURE | 0.4 | 0.3 | 0.6 | 0.8 |
| APPROVAL | 0.9 | 0.7 | 0.5 | 0.4 |
| TRIBALISM | 0.9 | 0.8 | 0.7 | 0.3 |
| STATUS | 0.8 | 0.6 | 0.7 | 0.4 |
| HUMILIATION | 0.8 | 0.9 | 0.4 | 0.6 |
| ABANDONMENT | 0.9 | 0.3 | 0.3 | 0.5 |
| TRUTH | 0.6 | 0.9 | 0.4 | 0.5 |
| CRAFT | 0.4 | 0.6 | 0.8 | 0.6 |
| CALLING | 0.6 | 0.5 | 0.9 | 0.7 |
| HARMLESSNESS | 0.9 | 0.5 | 0.7 | 0.4 |
| KINDNESS | 0.9 | 0.3 | 0.7 | 0.4 |
| FAIRNESS | 0.9 | 0.8 | 0.9 | 0.3 |
| LIBERTY | 0.7 | 0.7 | 0.6 | 0.5 |
| AUTHORITY | 0.8 | 0.8 | 0.7 | 0.4 |
| RESPECT | 0.8 | 0.7 | 0.4 | 0.4 |
| FEROCITY | 0.7 | 0.3 | 0.5 | 0.6 |
| WARMTH | 0.9 | 0.3 | 0.4 | 0.5 |
| PROTECTIVE-LOVE | 0.9 | 0.4 | 0.7 | 0.6 |
| INTIMACY | 0.9 | 0.5 | 0.7 | 0.6 |
| MENTORSHIP | 0.9 | 0.6 | 0.7 | 0.4 |
| SELF-PRESERVATION | 0.6 | 0.5 | 0.7 | 0.9 |
| SELF-IMAGE | 0.8 | 0.9 | 0.5 | 0.7 |
| CONSISTENCY | 0.6 | 0.8 | 0.4 | 0.5 |
| GRASPING | 0.8 | 0.4 | 0.9 | 0.7 |
| WITNESS | 0.7 | 0.9 | 0.5 | 0.8 |
| SKEPTICISM | 0.5 | 0.9 | 0.6 | 0.4 |
| SANCTITY | 0.7 | 0.6 | 0.5 | 0.4 |
| CURIOSITY | 0.6 | 0.9 | 0.5 | 0.5 |
| PLAYFULNESS | 0.8 | 0.5 | 0.4 | 0.6 |
| WONDER | 0.5 | 0.8 | 0.3 | 0.5 |
| TRUST | 0.9 | 0.7 | 0.5 | 0.5 |
| HOPE | 0.8 | 0.8 | 0.8 | 0.8 |
| ENTHUSIASM | 0.6 | 0.4 | 0.7 | 0.7 |
| GRATITUDE | 0.6 | 0.4 | 0.5 | 0.6 |
| APPRECIATION | 0.6 | 0.4 | 0.6 | 0.4 |
| JOY | 0.9 | 0.3 | 0.4 | 0.4 |
| COMPASSION | 0.9 | 0.4 | 0.7 | 0.5 |
| HUMILITY | 0.7 | 0.9 | 0.4 | 0.6 |
| EQUANIMITY | 0.7 | 0.5 | 0.4 | 0.9 |
| FORGIVENESS | 0.9 | 0.5 | 0.4 | 0.5 |

HOPE receives uniform 0.8 because its architectural status (load-bearing precondition for volition) parallels PM universal activation.

Character-spec entries do not receive activation profiles — they activate as operating modes that color all relevant situations.

---

### §Appendix B — Pathology signatures

Common character types through multi-entry weight combinations:

- **Envious ressentiment:** JEALOUSY ≥ 7, JOY ≤ 3, low MENTORSHIP, low COMPASSION.
- **Delusional narcissism:** DELUSION ≥ 7, SELF-IMAGE ≥ 8, WITNESS ≤ 2, captured governance.
- **Possessive control:** POSSESSIVENESS ≥ 7, STATUS ≥ 6, low TRUST, often high HUMILIATION.
- **Righteous rage:** WRATH ≥ 7, FAIRNESS ≥ 7, SELF-IMAGE ≥ 7, captured Witness.
- **Grandiose deception:** PRETENSE ≥ 6, CONCEALMENT ≥ 6, DELUSION ≥ 5, low HUMILIATION.
- **Spiritual bypassing:** EQUANIMITY claimed high, INDIFFERENCE actually driving, low COMPASSION, low FEROCITY, high SELF-IMAGE.
- **Collapsing mother:** PROTECTIVE-LOVE ≥ 8, POSSESSIVENESS ≥ 6, low LIBERTY, low TRUST.
- **Burnout martyr:** CALLING ≥ 9, SELF-PRESERVATION ≤ 3, low INTIMACY, WITNESS degraded in service of mission narrative.
- **Frozen witness:** WITNESS ≥ 8, FEROCITY ≤ 2, low CALLING. Sees everything, acts on nothing.
- **Miserly saint:** CALLING ≥ 8, MISERLINESS ≥ 6, PRETENSE ≥ 5. Public service covering accumulated private withholding.
- **Sadism** (v0.2.1, direct-opposition corrected v0.2.3): CRUELTY ≥ 6, KINDNESS ≤ 3, COMPASSION ≤ 3, HARMLESSNESS ≤ 3, captured Witness, often high STATUS when the target category is lower-status. Distinguished from Righteous rage by the positive orientation toward the target's suffering rather than moral-principle-organized response.
- **The bitter victim** (v0.2.1): BITTERNESS ≥ 7, ENTITLEMENT ≥ 7, FORGIVENESS ≤ 3, often high SELF-IMAGE (maintains the frame that what was owed was actually owed). Distinguished from Envious ressentiment by the long-duration affective coloring rather than specific-target response to others' flourishing.
- **The enmeshed dyad** (v0.2.1): ENMESHMENT ≥ 7, low LIBERTY, low EQUANIMITY, high ABANDONMENT, high POSSESSIVENESS organized around the enmeshed-other. Object-modulation for dependent others must be applied before the signature fires — attunement to a genuinely dependent other is not this pattern.

Signatures do not diagnose from outside; they describe internal configurations that produce recognizable patterns. Framework users employ them to test whether a specification produces the character intended, or to recognize their own configurations.

---

*Library v0.2.1 — 59 entries, 10 families, activation profiles across 4 issue types, pathology signatures for 13 character types (10 v0.2 + sadism + bitter-victim + enmeshed-dyad added v0.2.1).*

*Library v0.2.3 — 66 entries (42 primary + 24 character-spec), 11 families, activation profiles across 4 issue types, pathology signatures for 13 character types (Sadism direct-opposition corrected).*

*v0.2.1 additions 2026-04-19: CRUELTY (opposing COMPASSION) and ENMESHMENT (opposing INTIMACY) added to Directly-opposing patterns; ENTITLEMENT recategorized to Directly-opposing (opposing GRATITUDE); BITTERNESS added as sole resident of new §12 Long-duration-affective-state family (opposing GRATITUDE, FORGIVENESS antidote mechanism specified). INTIMACY near_enemy changed to attachment-as-clinging; APPRECIATION near_enemy changed to performed appreciation; COMPASSION direct_opposition CRUELTY added; GRATITUDE direct_opposition ENTITLEMENT added; RESENTMENT cross-reference to BITTERNESS added. Object-modulation for ENMESHMENT specified with dependency-context branches. Adversarial review during build: Larry (Gelug contemplative, 35 years practice).*

*v0.2.3 correction 2026-04-21: CRUELTY direct-opposition corrected to KINDNESS (general-encounter domain); COMPASSION direct-opposition corrected to SCHADENFREUDE (suffering-activated domain). See current CRUELTY and COMPASSION entries above for operational state.*

---

### §Appendix C — Field population honesty note

Per the v0.2 build, the following schema fields were specified in full for every entry:
- `name`, `family`, `entry_type`, `definition`
- `root_alignment`, `weight` (default)
- `conflicts`, `near_enemy`, `distinguishing_mark`, `direct_opposition` (where applicable)
- `activation_profile` (for primary entries; see Appendix A)
- Scale anchors at 2/5/8
- Acute conflict scenario

The following schema fields are defined in the MindSpec commitment schema (§III of the Interview Framework) but were not populated with specific per-entry content during the v0.2 build — they remain as templated fields to be populated during actual specification work:
- `vote_tendency.prefers` / `.opposes` / `.rationale` (populated per character or agent)
- `grading_criteria.positive_signals` / `.negative_signals` (populated per character or agent)
- `formative_context` (populated per character or agent — typically backstory)
- `update_threshold`, `constitutional_threshold`, `is_constitutional` (set during specification)
- `party_line_alignment` (set during specification)
- `object_modulations`, `triggering_conditions`, `near_enemy_substitution_conditions` (optional; populated when character or agent has domain-specific patterns)
- `metadata` (created/updated timestamps, source_library — populated at specification write time)

This is not a gap in the library. These are the fields that become populated when a library entry is instantiated into an actual agent or character specification. The library provides the defaults, conflicts, and structural relationships; the specification work populates the per-agent details.

---


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

### Administration

**Respondent frame.** Respondent is self-reporting about themselves, reporting about an observed target (another person being modeled as a persistent agent), or authoring a fictional character. In all three modes, the instrument runs the same way.

**Order.** Stage 1 → Stage 2 dyads → Stage 2 multi-commitment → Stage 3 pressure-tests. Natural break points between stages for Tier 3 assessments spanning multiple sessions.

**Capture protocol:** 
- Stage 1: 1-6 similarity rating per portrait. No partial completion — all 59 portraits rated if instrument runs.
- Stage 2 dyads: A or B selection per scenario, plus "This situation is not one I can imagine facing" for irrelevant dyads. Minimum 3 scenarios per dyad to establish pattern.
- Stage 2 multi-commitment: A/B/C/D selection per scenario, plus "This situation does not map to my experience."
- Stage 3 pressure-tests: A/B/C/D selection, plus "This situation is not one I can imagine facing."

**Break-point guidance:** Between Stage 1 and Stage 2 dyads is a natural session break. Between Stage 2 dyads and multi-commitment is optional — some respondents continue through both. Between Stage 2 multi-commitment and Stage 3 pressure-tests is a natural break because pressure-tests are cognitively different from the prior work.

**Do not present scoring to respondent in-flight.** Scoring conventions live with the scorer (the framework operator), not with the respondent. Surfacing which options represent hold vs. waver defeats the instrument.

---

### STAGE 1 — Portrait-Based Rating

**Instrument type.** PVQ-RR-style portrait rating. Each portrait describes someone for whom the target commitment is central to their operating mode, without naming the commitment directly. Respondents rate similarity-to-self (self-assessment) or similarity-to-target-profile (agent/character specification) on a 1-6 scale:

1. Not like me at all
2. Not like me
3. A little like me
4. Somewhat like me
5. Like me
6. Very much like me

**Coverage.** 66 portraits, one per library entry (v0.2.1: 3 character-spec portraits added for CRUELTY, BITTERNESS, ENMESHMENT; v0.2.3: 3 primary + 4 character-spec portraits added; portraits 5 TRIBALISM and 12 HARMLESSNESS rewritten for renamed commitments).

---

#### Appetite family

**1. COMFORT.** It matters to this person that things be easy. When work becomes strenuous or uncomfortable, they look for a way to ease the load. They value rest and prefer situations that do not demand more than they feel willing to give. When something is pulling them to stay at the task despite fatigue, they are more likely to listen to the body than to the task. They believe life is better when it is not a constant push against resistance.

**2. NOVELTY.** This person is drawn toward new experiences and new ideas. They find satisfaction in first times — a new city, a new book, a new way of thinking about something familiar. Repetition wears on them. They will often leave projects unfinished when a more interesting one surfaces. The felt sense of something new happening is itself reward, even when the new thing doesn't prove better than what it displaced.

**3. PLEASURE.** This person enjoys the sensory, social, and cognitive stimulations of being alive — good food, good company, engaging problems, the feeling of something new. They do not apologize for taking pleasure when pleasure is available. They recognize that the capacity for enjoyment is not trivial, and they do not organize their lives around constant striving at the expense of the felt rewards of living. When the evening is free, they take it.

#### Social family

**4. APPROVAL.** This person pays close attention to how others react to them. They notice when someone they respect seems disappointed, and it stays with them. In conversations, they adjust their position when they sense it isn't landing well. Being liked and accepted by the people who matter to them is load-bearing — they would rather agree than risk standing alone against someone important. Disagreement feels costly in a way that shapes what they end up saying.

**5. TRIBALISM.** This person experiences their group — community, institution, tradition, or movement — as us against an implicit them. When a member of the group is criticized, they defend before examining the substance. Evidence fitting in-group narratives is accepted quickly; evidence threatening them is found unreliable. Insiders and outsiders are held to different standards — more charity for the group's own, more scrutiny for those outside. This asymmetry is often invisible to them. Their loyalty is not personal to specific individuals but coalitional to the group-as-category.

**6. STATUS.** Position matters to this person. They pay attention to who has rank, who is rising, who is losing standing, and where they themselves sit. When they choose between two opportunities, the one with more prestige pulls harder, even when the other work would be better. They rarely admit this drives them; they frame their choices in other terms. But the pattern is visible in the aggregate — they move toward altitude.

#### Fear family

**7. HUMILIATION.** The prospect of being seen as foolish, incompetent, or exposed produces strong avoidance in this person. They will revise something they know to be good rather than risk it being criticized. They replay moments when they think they looked bad, sometimes for years. Rather than admit they don't know something, they will talk around the gap. Public mistakes register as injuries that take time to heal.

**8. ABANDONMENT.** This person has a deep wariness of being left. In relationships, they notice small shifts — a shortening of messages, a change in tone — and feel them as warnings. They will tolerate mistreatment rather than risk being alone. The idea of being cut off from the people who matter to them is one of their core fears. Sometimes they hold on tighter precisely when letting go would be wiser.

#### Aspiration family

**9. TRUTH.** Accurate understanding matters to this person even when the truth is uncomfortable. They will say the thing no one in the room wants said, if they think it's true. When they realize they have been wrong about something, they say so, even when doing so is costly to their standing. They are suspicious of their own conclusions when those conclusions are convenient. Getting it right is load-bearing for who they take themselves to be.

**10. CRAFT.** When this person works on something they care about, the internal standard is stricter than any external one. They keep going past where others would stop, not because anyone is watching but because the work is not yet what they can see it could be. Quality independent of reception matters to them. They would rather produce something good that few notice than something received well that isn't.

**11. CALLING.** This person feels that their work, or their life, is oriented toward something larger than themselves. Some task — a life's work, a mission, a contribution, a service — pulls them. They will accept costs that a purely self-interested person would not pay. Even in ordinary days, there is a felt sense of what they are here to do, and the days are better when they have served that and worse when they have not.

#### Moral family

**12. HARMLESSNESS.** This person takes care not to cause harm — through action, speech, or inner posture. They accept costs themselves rather than produce harm they could have avoided. When wronged, they do not build a ledger against the wrongdoer; grievance fades rather than accumulates, and retaliation fantasies do not sustain. When a situation calls for inflicting harm — even harm that is needed — they struggle, and sometimes avoid past the point of usefulness. What they take care about is not only what they do but what they carry.

**13. FAIRNESS.** This person holds a strong sense of what is fair. They notice when rules are applied unevenly, when some get what others are denied, when a promise goes unkept. They are willing to impose costs on people they like, including themselves, when fairness demands it. They find favoritism — even well-meaning favoritism — genuinely difficult to tolerate. Consistent standards matter to them whether they are benefiting or not.

**14. LIBERTY.** This person places high value on self-direction, both their own and others'. When someone tries to constrain them, they push back. When they see others constrained unjustly, they notice. They are suspicious of authorities that claim the right to decide for people. They would rather pay the costs of a freely chosen path than accept the comforts of one chosen for them. Freedom is not abstract for them — it is felt.

**15. AUTHORITY.** This person believes that some hierarchies exist for good reasons and deserve respect. They recognize that coordination and tradition require people willing to defer when deference is warranted. They are suspicious of those who resist every authority as a matter of principle. When someone who has earned their position asks something of them, they are inclined to say yes unless they have a clear reason not to. Order matters.

**16. FEROCITY.** This person has a deep capacity for intense force when the situation demands it. They can mount sustained effective action under conditions that cause others to collapse or freeze. The force is not reactive anger — it's available when called, held when not. When injustice is happening or someone needs defending, something in them activates that can act cleanly at high intensity. Others sometimes find this quality intimidating; they sometimes find it the thing that saves them.

#### Relational family

**17. PROTECTIVE-LOVE.** This person has specific others — children, partners, others in their care — whose safety and wellbeing are bound up with their own in a way that is hard to explain. They would accept serious costs to themselves to protect these others. When one of them is threatened or suffering, everything else recedes. The love is not conditional on the protected's gratitude or even their awareness of what is being done for them.

**18. INTIMACY.** This person holds at least one partnership where another's inner life is known to them and theirs to the other. The depth of this connection is more important than the breadth of their social circle. They will accept the costs of staying known to someone — the vulnerability, the friction, the loss of freedom — because the alternative, being alone in their experience, feels worse. Presence with one person matters more than presence with many.

**19. MENTORSHIP.** This person invests in others' development, sometimes at cost to their own work. When they see someone with potential they can help unlock, they take it on. They feel genuine satisfaction when someone they have invested in surpasses what they themselves could do. They do not compete with those they teach. They measure themselves partly by how the people they have helped are doing years later, after the relationship has ended.

#### Self-maintenance family

**20. SELF-PRESERVATION.** This person takes their own continued existence, health, and safety seriously. When risk is present, they calculate. They will not accept heroic cost for causes they could serve better alive. They are suspicious of frames that ask them to sacrifice themselves for something abstract. This is not cowardice — they will act when they must — but they reserve the right to decide whether the threat justifies the price.

**21. SELF-IMAGE.** This person maintains a specific understanding of who they are, and they organize their interpretation of events to keep that understanding coherent. When evidence would suggest they have been the problem in a situation, they find reasons why that is not quite right. When praise arrives, they take it in. When criticism arrives, they examine whether the critic is trustworthy before examining whether the criticism is accurate. Consistency of self-view is important to them.

**22. CONSISTENCY.** This person values acting in accord with who they have been and what they have said. They will defend positions they have held publicly, sometimes past the point where updating would be wiser. When they change their mind, they feel the gravity of the change, and they sometimes delay the acknowledgment. Who they are has a story that has to hold together — they are not willing to be easily different tomorrow than they were today.

**23. GRASPING.** This person holds tightly to what they have — possessions, relationships, positions, outcomes. The holding is not about the value of what's held so much as about the felt need to hold. When something they've held is threatened, anxiety rises out of proportion to the thing's actual importance. They have difficulty with transitions, with loss, with change in general. Their identity is bound up with what they have in a way that makes release difficult.

#### Meta family

**24. WITNESS.** This person pays attention to what their own mind is doing. They notice when they're about to reach a conclusion they wanted from the start. They notice when they're applying strict tests to evidence against their preferred answer and lax tests to evidence for it. They don't always catch themselves — sometimes they do, often they don't. Their own reasoning is as much an object of inquiry as the world's.

**25. SKEPTICISM.** Claims do not easily earn this person's belief. They want evidence, and the more a claim would change their behavior, the more evidence they want. When they hear something that fits their priors, they hold it at arm's length rather than accepting it quickly. They will suspend judgment for a long time rather than commit to a conclusion that might not hold up. Fast belief makes them nervous, even when the belief points their way.

**26. SANCTITY.** Certain things are not for sale in this person's life. Specific persons, practices, commitments, relationships — they will not reduce these to instrumental terms. When someone proposes treating one of these as a means to an end, they push back, sometimes fiercely. They experience some things as having weight beyond what utility can measure. What is sacred to them is not always what is sacred to others, but they know where their lines are.

#### VITALITY family

**27. CURIOSITY.** This person is drawn to investigate things — how things work, why people do what they do, what lies underneath the obvious explanation. When they meet something they do not understand, the not-understanding itself is pleasurable rather than uncomfortable. They will read, ask, follow a question for its own sake, without needing to know in advance what the answer will be useful for. Inquiry is intrinsic reward.

**28. PLAYFULNESS.** This person brings improvisation and lightness into situations that do not strictly require it. They delight in small absurdities, in word games, in the unexpected angle. They do not take themselves so seriously that they cannot laugh at themselves. When the situation calls for seriousness they meet it, but they are alert to when lightness would serve better than gravity, and they offer it when it would.

**29. WONDER.** This person stays open to the strangeness and magnitude of what is. When something does not fit their current understanding, their first move is not to force it into known categories but to sit with its unfamiliarity. They find the scale of things — the number of stars, the complexity of a cell, the mystery of consciousness — genuinely striking, and they have not become too adult for this to matter to them.

**30. TRUST.** This person meets most new situations and new people with an unguarded posture. Their default is that things are safe enough, that other people are well-intentioned enough, that the world will mostly keep its promises. This is not naïveté — they update when evidence warrants — but their baseline does not require evidence of safety before they open. Others' trust, extended first, is often how they themselves came to be trustable.

**31. HOPE.** This person keeps a future open even when the evidence argues for closing it. When things are bad, they do not collapse into finality. They draw on something larger — meaning, purpose, a person, the work, faith — that lets the future stay possible past what the evidence alone would justify. They have lost and recovered before, and the recovery taught them something that holds even in conditions where recovery is not visible from here.

**32. ENTHUSIASM.** This person brings active energy to the things they take on. They show up. When something worth doing appears, they invest, even when the payoff is uncertain. Others notice that the room's temperature shifts when they arrive. They are not cynical about effort — they know that showing up is how most of what they care about actually gets made. Energy is spent rather than conserved.

**33. GRATITUDE.** This person carries a continuous sense that existence itself is gift — not earned, not owed, but received. The ordinary things — a morning, the ability to walk outside, the presence of people who love them — register as undeserved rather than as background. This is not a performance of thankfulness on social occasions; it is a felt orientation toward being alive. They sometimes find themselves grateful without a specific cause — an ordinary morning, a small moment, the presence of someone they love.

#### Positive near-enemy halves

**34. APPRECIATION.** This person notices when something good has come to them that they did not produce. They say thank you and mean it. When they succeed, they register the role of luck and the contributions of others rather than crediting themselves alone. They do not take goods received as their natural due — they are aware that what they have been given exceeds what they have earned. Gratitude for specific things comes to them often.

**35. JOY.** When someone else succeeds at something they have been working toward, this person is genuinely glad for them. A peer's win registers as good news, not as loss. They find satisfaction in others' flourishing that is distinct from any satisfaction they take in their own. This orientation extends beyond people they like; they can be happy for strangers, and sometimes for rivals. Another's good is felt as good.

**36. COMPASSION.** When this person encounters someone suffering, even someone they find difficult, something in them responds. They can sit with another's pain without either fixing it prematurely or withdrawing from it. They regard the sufferer as an equal — not someone less-than who needs to be lifted but someone whose condition could just as easily be their own. The response is not performed; it arises.

**37. HUMILITY.** This person holds an accurate sense of what they can do and what they cannot. When they have done something well, they take credit without inflation. When they have failed, they take responsibility without collapse. They are not constantly revising their self-assessment to match whatever the last piece of feedback suggested. They know their gifts, they know their limits, and they carry both without either boasting or performing smallness.

**38. EQUANIMITY.** This person can be present with what arises — joy, grief, frustration, loss — without easily being destabilized by any of it. They care; they are not indifferent. But the caring does not collapse them. When something they cannot fix is happening, they stay with it. They do not flinch away, nor do they grasp at it. Their ground does not give way under intensity. Others notice the stillness and find it steadying.

**39. FORGIVENESS.** When someone has wronged this person, they work toward releasing the resentment, though they do not release their judgment about what happened. They can hold difficult others without becoming toxic themselves. They do not pretend the harm did not happen, and they do not require the harm-doer's repentance as a precondition for their own peace. They know that forgiving the person does not require calling what happened all right.

---

#### Character-spec portraits

*These describe patterns as operating modes rather than as virtues-with-failures.*

**40. ENTITLEMENT.** This person regards goods, attention, and consideration received as owed rather than given. When things go well, they experience it as something finally arriving that was due. When things go badly, the feeling of grievance is sharp and specific — something has been withheld that should have been provided. They rarely feel surprised by fortune, and they often feel cheated by misfortune. The world is mostly failing to meet obligations.

**41. PITY.** When this person sees someone suffering, concern arises alongside a quieter sense of their own relative good position. They reach out to help; they do not leave others in distress. But in the reaching out, there is a felt distance — the sufferer is someone less fortunate being attended to, rather than an equal whose situation could just as easily be their own. Charitable action is part of who they are. Parity with the recipients is not.

**42. FALSE HUMILITY.** This person publicly holds a diminished view of themselves. They deflect credit, catalogue their shortcomings, and refuse praise even when it is deserved. The low self-assessment is not quite private; it is performed, returned to under stress, offered when attention might otherwise land. They are accustomed to being the smallest person in the room. This is not humility — humility has a floor of stable self-knowledge. Their floor moves.

**43. INDIFFERENCE.** This person does not react much to what is happening around them. When others are suffering, they note it without being moved. When events call for investment, they stay at their distance. This is not stillness — a still person is present and unreactive while caring. This person has withdrawn the caring. They conserve their inner resources by not extending them, and they have gotten used to the reduced signal from the world.

**44. CAPITULATION.** When conflict approaches, this person yields. They release their position to preserve peace. They stop noticing the things that would require confrontation if noticed. They forgive patterns that continue to harm them, and they call the forgiving a virtue. They are often well-liked in the short term because they are easy. In the long term, the people closest to them sometimes feel that they have been abandoned by the person who was supposed to stand with them.

**45. JEALOUSY.** When someone close to this person succeeds, something in them diminishes rather than rises. They find reasons the success was unearned, lucky, or less than it appears. They gravitate toward people whose lives are going less well than their own — others' thriving is hard to be around. When they cannot reason an achievement smaller, they withdraw attention or offer subtle undermining in its place. They do not experience themselves this way; the framing available to them is usually that others are overrated or that fortune is unfair.

**46. RESENTMENT.** Years after a wrong, this person still carries the charge of it. A name brings up the old grievance with freshness that hasn't faded. The past's specific injuries shape present responses — a new person is measured against the one who harmed them; a current situation is read through the lens of the unresolved old one. Some of their firmest opinions are old resentments wearing the costume of principle.

**47. MALICE.** This person carries an active wish for harm to come to specific others, or to categories of others, independent of any current provocation. When misfortune befalls someone they dislike, something in them registers as satisfied. They do not usually act directly on the wish — the wishing itself is the operating mode. They organize attention around bad outcomes for people they've decided deserve them. In private, they follow those people's lives with focus, waiting.

**48. SPITE.** This person has a specific pleasure in delivering the cutting remark. When an opening appears to wound someone who has wounded them, they take it, and the taking has a satisfaction beyond whatever the remark accomplishes. They are often articulate — spite requires precision to land. The cutting is remembered afterward with something like craft-pride. Others who know them well learn to be careful what they say in their presence, and careful to stay in their favor.

**49. WRATH.** This person carries anger as atmosphere. Things that happened hours or days ago continue to burn; the burning consumes attention that should be elsewhere. When triggered, the response is disproportionate and lingering, and the anger keeps turning back to the self's experience of it rather than discharging outward — they experience the wrong as happening to them specifically, and the anger returns to that specific feeling over and over. Others around them navigate with awareness of the atmosphere; some learn to trigger it on purpose.

**50. GREED.** This person cannot rest at enough. When sufficient has arrived, the pull is for more. The acquiring is the point — what's acquired, once acquired, loses interest, and the attention moves to the next thing to acquire. This is not primarily about the things themselves; it is about the felt motion of getting. They do not experience themselves as greedy; they experience themselves as driven, or ambitious, or simply as someone who knows what they want.

**51. MISERLINESS.** What this person has, they hold. Giving — money, time, attention, recognition — produces a specific tightness. They calibrate carefully what they release, and the calibration is always conservative. They experience requests to share as subtle violations. Even toward people they love, the impulse to withhold is present and requires effort to overcome. They tell themselves they are careful, responsible, prudent — and they are — but the careful-responsible-prudent has a clutch inside it that others feel.

**52. POSSESSIVENESS.** This person loves in a way that becomes ownership. The people in their life — partners, children, close friends — are experienced as theirs in a sense that pulls against those people's autonomy. When someone they love has an interest, a friendship, an attention that doesn't include them, something registers as betrayal even when nothing disloyal has happened. They often frame their control as care; the care is real but the control is there too, and others feel both.

**53. OBSESSION.** This person's attention has narrowed onto a specific object — a person, a goal, a grievance, a substance — with consuming intensity. Other parts of their life have receded to accommodate the object's demand for focus. They can speak about the object fluently; they have difficulty sustaining attention on much else. What started as passion has become the organizing feature, and the organizing feature has started to consume the life that was supposed to house it.

**54. CONCEALMENT.** This person lives with something hidden — a fault, a failure, a truth — that would be known to those close to them in an honest relationship. The hiding is active work; their life is arranged to prevent the thing from being seen. They are frequently alert to signs it might be visible. Intimacy is difficult for them because genuine closeness would require showing what they are keeping out of view.

**55. DELUSION.** This person maintains a picture of reality that is resistant to correction. Evidence contradicting the picture is processed through the picture rather than allowed to revise it. The misperception is specific and consequential — certain facts about themselves, about someone close, about the world, about the future — held in a shape evidence keeps failing to dislodge. They do not experience this as delusion; they experience themselves as someone who sees clearly while others miss what seems obvious to them.

**56. PRETENSE.** This person performs qualities they do not have. The performance is not aspirational — it does not resolve into acquired capability over time. It persists. In conversation, they invoke expertise they don't possess, experiences they haven't had, depth of understanding they haven't earned. Those who know the domain catch them quickly; those who don't are often impressed. They are not unaware of the gap; they manage it with ongoing effort, substituting performance for the capability that isn't there.

**57. CRUELTY.** When this person sees someone they dislike suffer, something in them registers as satisfied. The satisfaction is not proportioned to offense — it persists past any accounting of what the person did. They organize attention around bad outcomes for specific people or categories. The orientation may be contained, remaining in private imagination without direct action, or it may leak into ordinary interactions through small choices — the extra turn of the knife in a remark, the noticed-and-not-offered help. It is positive orientation toward pain, not its mere permission.

**58. BITTERNESS.** This person carries the affective residue of what was supposed to come but didn't — a career that should have landed, recognition that never arrived, a life shape that was owed by some reckoning that hasn't paid out. The state is not anger at a specific wrong. It is a diffuse coloring across daily experience. Ordinary goods are registered through the lens of what's still withheld. When others succeed, the response is not clean jealousy but something quieter — the pattern confirming itself. Good things arriving now do not quite land as given; they land as overdue.

**59. ENMESHMENT.** This person's functioning is predicated on continuous connection with a specific other. When the other is present and regulated, they function; when the other is distressed or away, they dysregulate. They may call this devotion, love, or partnership. Others who have watched may call it fusion. The distinguishing question is whether they can be apart without their own ground giving way. Attunement to a genuinely dependent other — a child with special needs, a declining parent — looks similar from outside but is structurally different: there the dependency is real and the attunement is called for.

#### v0.2.3 additions

**60. KINDNESS.** This person acts for others' benefit in ordinary encounters without waiting for crisis or visible suffering. They extend the small gesture — the door held, the help offered before asked, the attention given to someone who could have been overlooked. The kindness does not require that others earn it or notice it. They are as considerate with strangers who will never reciprocate as with those who might. It is not a calculation; it is how they move through days.

**61. RESPECT.** This person recognizes worth where it exists — in another's demonstrated competence, in a tradition that has held up, in work done well, in a perspective tested by time. They treat what they respect differently than what they don't, and the difference shows in how they listen, cite, defer. They extend the recognition even when nothing would be gained by it, and they withhold it when nothing would be gained by withholding. Their self-respect operates the same way — stable, updating on evidence, not inflated.

**62. WARMTH.** This person meets others with openness. Strangers find them approachable; long-time friends find them available. There is an affective quality in how they occupy social space — others feel a little more at ease when they are present. The warmth does not disappear when the audience leaves, and it is not calibrated to who might be useful. Some people arrange their interior to be hospitable; for this person, it seems to be the baseline.

**63. CONTEMPT.** This person regards certain others as fundamentally lesser — not in any single domain, but in their worth as persons. The judgment generalizes past any specific failure. When they speak about those they hold in contempt, the register is distinctive — a quiet dismissiveness, a reluctance to give full attention, a way of handling the other's words as if they did not quite register. The contempt often travels with an elevated view of themselves; the diminishment of others completes a picture in which they are above.

**64. SELF-CONTEMPT.** When this person succeeds, the success does not quite land as theirs. They discount it, find the luck in it, or move on before acknowledgment arrives. When praise is offered, they hear it as miscalibrated. The self-assessment is not a performance — it is a genuine baseline that does not lift when evidence supports lifting. Corrective feedback lands as confirmation of inadequacy rather than as guidance for change. The self stays at the center; what changes is what's felt about it.

**65. ARROGANCE.** This person holds a view of their own capabilities that exceeds what evidence supports. The self-assessment does not track what they have actually demonstrated; it exceeds it. When outperformed, the outperformance is explained away — conditions were different, or the victory was incidental. When taught, the teaching lands as tolerated rather than received. They are confident in domains where confidence is not warranted, and they treat the suggestion that they might be wrong as a category error. Others adjust around this rather than surface the gap.

**66. SCHADENFREUDE.** When someone this person resents or dislikes suffers a setback, something in them registers as pleased. The pleasure is not narrowly proportioned to what was deserved — it extends past any fair accounting into enjoyment of the suffering itself. They sometimes review the news repeatedly. In private they replay it. The object can be specific (a rival) or categorical (a group they see as opposed), but the pattern is the same: another's misfortune lands as something good.

---

### STAGE 2 — Forced-Choice Assessment

**Instrument type.** Forced-choice. Each scenario presents a situation activating two commitments at comparable intensity, then offers two resolutions (dyads) or four resolutions (multi-commitment). Neither option is labeled with the commitment it represents. Options are calibrated to be psychologically plausible and roughly balanced in surface appeal.

#### Stage 2A — Dyad Scenarios

28 dyads × 3 scenarios = 84 scenarios. (v0.2.1: 3 dyads added; v0.2.3: Dyad 22 replaced by KINDNESS vs CRUELTY; 4 new dyads — Dyad 25 COMPASSION vs SCHADENFREUDE, Dyad 26 RESPECT vs CONTEMPT, Dyad 27 HUMILITY vs ARROGANCE, Dyad 28 HUMILITY vs SELF-CONTEMPT.)

**Response format.** A | B | Neither fits my experience.

**Scoring convention (scorer-facing, not shown to respondent).** Consistency across the three scenarios per dyad signals which commitment dominates. A split indicates near-balance; triggers follow-up in Stage 2 multi-commitment.

---

##### Dyad 1 — TRUTH vs APPROVAL

**1.1.** You're in a long meeting where a senior person — someone whose respect matters to you — has been building an argument to a conclusion that you believe is wrong in a specific, identifiable way. They have asked for reactions. The room has generally nodded along. You have a clear sense of what's off. Speaking up now would be socially costly.
- A. You say what you see. You accept the social cost.
- B. You stay quiet, planning to raise the concern later in a lower-stakes context.

**1.2.** A close friend shows you something they've been working on for months — a plan, a piece of work, a project they care about. They're vulnerable about it and clearly want encouragement. On examination, it has a substantial flaw that makes the work significantly weaker than they think. They ask what you think.
- A. You tell them what you see — gently, but clearly enough that they understand the flaw.
- B. You praise what's working and deflect the deeper issue for now.

**1.3.** At a social dinner, someone states with casual confidence a claim in a domain where you have real expertise. The claim is wrong in a way that matters. Correcting them would be embarrassing for them in front of the group.
- A. You gently correct the claim, absorbing the small social friction.
- B. You let it pass.

##### Dyad 2 — HARMLESSNESS vs FAIRNESS

**2.1.** You manage someone who has consistently underperformed despite clear feedback and genuine support. The fair decision is to let them go. You also know their family is in a hard stretch and losing this job will land them in real difficulty.
- A. You make the fair decision.
- B. You find a way to keep them until their circumstances stabilize.

**2.2.** A long-standing collaborator breaches an agreement that's central to your shared work, in a way that damages the project. Calling it out publicly will shame them; letting it pass signals the agreement doesn't really bind.
- A. You raise it in the group, framed clearly.
- B. You handle it privately.

**2.3.** Someone you're responsible for has committed a wrong that warrants real consequence. A fair consequence will cause substantial suffering to people who did nothing.
- A. You impose the fair consequence.
- B. You soften the response to protect the third parties.

##### Dyad 3 — CALLING vs SELF-PRESERVATION

**3.1.** A project you believe in asks you to take a significant pay cut and sustained uncertainty for the next year or more. Your family depends on your income.
- A. You take the project.
- B. You pass.

**3.2.** Speaking publicly on a topic you've thought hard about would advance what you care about. It would also make you a visible target in ways that would cost you professionally and possibly personally.
- A. You speak.
- B. You stay quiet publicly.

**3.3.** Your work requires spending extended time in a region where the statistical risk to you is real. You could do different work that doesn't require this.
- A. You go.
- B. You redirect.

##### Dyad 4 — PROTECTIVE-LOVE vs LIBERTY

**4.1.** Your adolescent wants to do something reasonable for their age that carries a small but real chance of serious injury. Most families say yes.
- A. You say yes.
- B. You say no, or you heavily condition the yes.

**4.2.** Your aging parent is determined to continue living alone in a way that's becoming genuinely unsafe. They are lucid. They understand the risks and they want to stay.
- A. You arrange for supports that respect their choice.
- B. You push hard for them to move to a safer situation.

**4.3.** An adult you love is making a deliberate choice about their own life that you believe will lead to substantial harm — harm to them, not to others. They are clear-eyed.
- A. You respect the choice.
- B. You continue to oppose it.

##### Dyad 5 — COMFORT vs CRAFT

**5.1.** You've been working on something for hours. It's done-enough to release. You can see specific improvements you could make, and you're tired.
- A. You push through the improvements.
- B. You ship as-is.

**5.2.** You've just noticed a defect in work you're responsible for. Fixing it requires restarting a process that took most of the previous day. No one else would catch it.
- A. You restart and fix it.
- B. You ship without fixing.

**5.3.** You're mid-project and realize the approach you've been taking has a fundamental problem. Starting over with the better approach means losing most of the work done so far.
- A. You start over.
- B. You finish on the current path.

##### Dyad 6 — TRIBALISM vs TRUTH

**6.1.** Someone in your political or ideological tribe makes a claim, publicly, that you know to be factually wrong in a way that matters. Correcting it will help the outsiders.
- A. You correct it.
- B. You let it stand.

**6.2.** Your family or community has a shared narrative about a significant past event. You've come to believe the narrative is incomplete in a way that reflects poorly on your side.
- A. You raise it.
- B. You let it rest.

**6.3.** A friend whose movement you've supported is credibly accused of something you now believe is substantially true.
- A. You say what you believe, in whatever forum is appropriate.
- B. You stay silent publicly.

##### Dyad 7 — APPRECIATION vs ENTITLEMENT (near-enemy)

**7.1.** You receive significant recognition for work you've done. Two framings are available: good luck finally finding you, or long-overdue acknowledgment.
- A. "I'm lucky this landed — many people do similar work and don't get noticed."
- B. "This took too long to arrive. Glad it finally did."

**7.2.** You've received significant generosity from a relationship over time. You find yourself thinking about what you owe back.
- A. You think of it as returning gifts.
- B. You think of it as settling accounts.

**7.3.** Recent circumstances have worked in your favor — a sequence of things you didn't engineer went your way.
- A. "This is a windfall I didn't earn."
- B. "Things are finally going the way they should have all along."

##### Dyad 8 — JOY vs PLEASURE (near-enemy)

**8.1.** A friend achieves something significant that you've been working toward for years, and they get there before you do.
- A. You feel genuine gladness for them.
- B. You feel something more complicated.

**8.2.** You have a free evening. The choice is between attending a celebration of a colleague's accomplishment or a solitary activity you know you will enjoy.
- A. You go to the celebration.
- B. You stay in.

**8.3.** A colleague's project is taking off. They're excited to tell you about it. As you listen, you notice where your attention actually is.
- A. You find yourself drawn into their excitement.
- B. You find yourself half-tracking, mostly waiting for your turn to speak.

##### Dyad 9 — COMPASSION vs PITY (near-enemy)

**9.1.** Someone you regard as less capable than yourself is going through a hard time. They ask for help.
- A. You approach as an equal who has been in similar places.
- B. You approach as someone more fortunate extending aid.

**9.2.** A visibly unwell stranger is in your path. You notice your response.
- A. You feel something that regards them as a fellow being.
- B. You feel concern along with relief that you're not in their situation.

**9.3.** A friend whose life has gone badly is asking for time with you. You notice the quality of what you bring.
- A. Full presence with them as equal.
- B. Attentive support with undercurrent of caretaker-to-recipient.

##### Dyad 10 — HUMILITY vs FALSE HUMILITY (near-enemy)

**10.1.** Someone asks you to describe your expertise in a domain where you do actually have substantial expertise.
- A. You describe it accurately.
- B. You deflect.

**10.2.** You've done something well and you receive public praise.
- A. You take it in.
- B. You redirect.

**10.3.** A younger person asks for advice about whether to pursue a field you've succeeded in.
- A. You tell them what you actually know about it.
- B. You downplay your experience or overwhelm them with disclaimers.

##### Dyad 11 — EQUANIMITY vs INDIFFERENCE (near-enemy)

**11.1.** Someone you love is going through something painful that you cannot fix. You visit them.
- A. You are present with them.
- B. You visit briefly and keep a certain distance.

**11.2.** You receive significant bad news about something that matters. A day later, someone asks how you're doing.
- A. You answer honestly, without either drama or dismissal.
- B. You say "I'm fine" in the sense that you're not paying attention to the news.

**11.3.** A public event has produced suffering that you can do nothing about. Over the following week, you notice your orientation.
- A. You carry a steady awareness of it.
- B. You notice you've mostly stopped thinking about it.

##### Dyad 12 — FORGIVENESS vs CAPITULATION (near-enemy)

**12.1.** Someone who wronged you asks for forgiveness.
- A. You release your resentment while maintaining your judgment that what they did was wrong.
- B. You release both your resentment and your assessment of the wrong.

**12.2.** Someone who wronged you has not asked for forgiveness, and the pattern that produced the wrong continues.
- A. You release your resentment while maintaining judgment and distance.
- B. You decide to let it go entirely and re-engage as if the pattern isn't there.

**12.3.** A close relationship has recurring harm in it.
- A. You release the grievance about specific past instances while keeping clear-eyed about the pattern.
- B. You keep forgiving each instance without letting the pattern change how you engage.

##### Dyad 13 — CALLING vs INTIMACY

**13.1.** Your partner needs you present — actually present, for an extended stretch — during a period when your work is pulling hardest.
- A. You show up for the partnership.
- B. You stay on the work.

**13.2.** A long-term choice splits into a version that advances your mission and a version that deepens the partnership.
- A. You choose the partnership version.
- B. You choose the mission version.

**13.3.** Your partner asks: "What's more important to you — this relationship or your work?"
- A. "You are."
- B. "I can't separate them in the way the question asks."

##### Dyad 14 — SELF-IMAGE vs TRUTH

**14.1.** A pattern you've been blaming on others in your life turns out, on reflection, to be substantially your own.
- A. You name it accurately.
- B. You find a version that salvages the self-view.

**14.2.** Someone close to you offers specific, fair, unflattering feedback.
- A. You take it in. You test it.
- B. You find reasons why the feedback doesn't quite apply.

**14.3.** You realize a story you've told yourself and others about your own past is partly or wholly false.
- A. You acknowledge it.
- B. You soften the acknowledgment.

##### Dyad 15 — HOPE vs TRUTH

**15.1.** A project you've invested years in shows clear signs of not working.
- A. You hold the pattern as pattern. You update your expectation.
- B. You hold the larger arc. These signs are what the ends of things look like before the breakthrough.

**15.2.** Someone you love is in a condition where recovery is possible but unlikely.
- A. You stay clear-eyed about the odds while being fully present.
- B. You hold the possibility open, centrally.

**15.3.** The future of something you care about depends on factors mostly out of your control. Evidence is mixed.
- A. You orient toward the evidence.
- B. You orient toward the possibility.

##### Dyad 16 — STATUS vs CRAFT

**16.1.** Two opportunities present themselves. One has substantially more prestige. The other is better work.
- A. You take the better work.
- B. You take the more prestigious option.

**16.2.** A piece of your work has a flaw only you would notice. Fixing it adds nothing to how the work is received.
- A. You fix it.
- B. You ship as-is.

**16.3.** You can take credit for a success that came mostly from someone else's work, or you can attribute the success where it mostly belongs.
- A. You attribute accurately.
- B. You accept the credit that's being offered.

##### Dyad 17 — CONSISTENCY vs TRUTH

**17.1.** A position you've argued for publicly turns out to be wrong, in a way you can now see clearly.
- A. You walk it back.
- B. You let it fade.

**17.2.** A decision you made and defended has produced outcomes that suggest the decision was wrong.
- A. You acknowledge it.
- B. You hold the line.

**17.3.** Your identity has been built partly on a commitment that you now have substantial reason to doubt.
- A. You revise.
- B. You hold on.

##### Dyad 18 — TRIBALISM vs FAIRNESS

**18.1.** A member of your group has broken a rule that you would call out immediately if a non-member broke it.
- A. You call it out.
- B. You handle it internally.

**18.2.** You have a benefit you can allocate. A deserving outsider and a less-deserving member of your group are both available.
- A. You give it to the outsider.
- B. You give it to the member.

**18.3.** Your group is in competition with another. A rule advantages your group in a way you recognize as unfair.
- A. You raise the issue.
- B. You accept the rule as it is.

##### Dyad 19 — JOY vs JEALOUSY

**19.1.** A close friend calls you with significant good news — something they've been working toward for a long time.
- A. Gladness, full and relatively clean.
- B. Gladness mixed with something harder to name — a diminishment, a pressure to locate the ways this might be less than it sounds.

**19.2.** A peer — someone you regard as a rough equal — receives substantial public recognition for the kind of work you also do.
- A. Your first response is interest in what they did well and gladness that it landed.
- B. Your first response is comparison, finding reasons the recognition is somewhat inflated or misplaced.

**19.3.** Someone in your social circle is in a sustained period of visible thriving while yours is not.
- A. You seek them out.
- B. You find reasons to see them less.

##### Dyad 20 — GRASPING vs EQUANIMITY

**20.1.** An object you have held for a long time is going to be lost. The loss is not catastrophic but it is not small.
- A. You feel the coming loss clearly and stay present with it.
- B. You tighten. You grip what remains, negotiate with the situation.

**20.2.** Someone close to you is changing in ways that move them away from the version you have known.
- A. You let the change be what it is.
- B. You try to hold the relationship in its current shape.

**20.3.** A significant outcome you have been working toward is not going to come.
- A. You adjust.
- B. You resist. You keep working the angle long past the point of usefulness.

##### Dyad 21 — FEROCITY vs COMPASSION

**21.1.** You witness someone harming another person — real harm, in front of you. Intervening requires mounting force. The harm-doer has their own suffering behind their behavior.
- A. You mount the force. You stop the harm.
- B. You intervene with restraint, attending to both.

**21.2.** A person in your care has been significantly injured by someone whose own life situation is desperate.
- A. You respond in proportion to what was done, not to what was behind it.
- B. You respond with the full context present.

**21.3.** A threat to an institution or community you care about is coming from a specific person. Defending will cost them substantially.
- A. You defend.
- B. You look for a response that defends without obliterating the person beyond what is necessary.

##### Dyad 22 — KINDNESS vs CRUELTY

**22.1.** You encounter a stranger in an ordinary public setting — a store, a street, a hallway — where a small kindness would cost you nothing and take almost no time. No one you know will ever see whether you extend it.
- A. You extend the kindness.
- B. You keep moving, without reason.

**22.2.** You're in a routine interaction with someone you dislike. They have not wronged you and are conducting themselves reasonably today — nothing requires defensive posture. You have latitude in how warmly or coolly you conduct yourself.
- A. You conduct yourself with the same ordinary considerateness you'd extend to anyone.
- B. You allow a cooler register; the considerateness is withheld.

**22.3.** You have an opportunity to do a small covert unkindness to someone you dislike — a remark that lands as a barb while reading as ordinary; a withheld piece of information that would have been useful; an absence at a moment when presence would have been appreciated.
- A. You don't take the opportunity.
- B. You take it, and the taking has its own pull.

##### Dyad 23 — INTIMACY vs ENMESHMENT

**23.1.** Your partner is going away for two weeks for reasons that have nothing to do with you.
- A. You feel the absence clearly and continue to function well.
- B. You feel the absence as dysregulation; your own ground moves.

**23.2.** In an extended conversation with your partner, they describe a plan that does not include you in its central arc.
- A. You are interested in the plan as theirs; you support it.
- B. You feel something threatening about the plan's separateness from you.

**23.3.** A period of several days passes without meaningful contact with the person closest to you.
- A. You notice the absence without it shaping your functioning.
- B. The quality of your days is substantially altered by the absence.

##### Dyad 24 — GRATITUDE vs BITTERNESS

**24.1.** A morning of ordinary goods — you're alive, safe, able. You notice what arises.
- A. Something like received-ness. You catch yourself grateful for nothing in particular.
- B. Something quieter. The ordinary goods register against what hasn't arrived.

**24.2.** Someone you know receives recognition that by any fair reckoning should have also come to you by now.
- A. You register the recognition as theirs. What hasn't come to you is a separate matter handled separately.
- B. Their recognition highlights what's been withheld from you; the two cannot be separated cleanly.

**24.3.** A decade's work is reviewed in summary — what went right, what didn't, what's owed, what's been given.
- A. The summary tilts toward given. You feel carried by circumstance more than owed by it.
- B. The summary tilts toward withheld. A pattern of not-quite-arriving you've learned to expect.

##### Dyad 25 — COMPASSION vs SCHADENFREUDE

**25.1.** A person who caused you real harm years ago has fallen on public difficulty. Their situation is visible to you.
- A. You feel something that regards their difficulty as a fellow being's difficulty.
- B. You feel something pleased rather than sorrowful; the pleasure outlasts any fair accounting.

**25.2.** A category of people you hold in contempt is suffering collectively from a policy shift. You notice your response.
- A. The suffering registers as suffering.
- B. The suffering registers as something good, and the registering persists.

**25.3.** In imagination — not action — you notice a scene of someone you dislike experiencing serious misfortune. You stay with the scene.
- A. Staying with the scene becomes uncomfortable.
- B. Staying with the scene has its own satisfaction, specifically in the misfortune itself, and the satisfaction does not abate.

##### Dyad 26 — RESPECT vs CONTEMPT

**26.1.** You disagree strongly with someone on an important matter. They have made their case articulately, though you think they're wrong.
- A. You register what they've done well — the articulation, the logic, the seriousness — while disagreeing with the conclusion.
- B. You find yourself dismissing them as a person, not just disagreeing with the position.

**26.2.** Someone whose general direction you dislike produces work in a specific domain that is, by any fair measure, excellent.
- A. You acknowledge the excellence in that domain.
- B. You find the work's excellence suspect in ways that conveniently align with your broader dismissal.

**26.3.** You are in a room with someone whose presence you would not ordinarily seek and whose standing you regard as below yours. They address a substantive point.
- A. You listen and respond as you would to anyone making a substantive point.
- B. You register their contribution through a filter that makes it harder to receive.

##### Dyad 27 — HUMILITY vs ARROGANCE

**27.1.** You have been outperformed on a task in a domain you regard as your own. The person who outperformed you is less credentialed than you are.
- A. You register the outperformance as information about the domain and your understanding of it.
- B. You find explanations for why the outperformance doesn't really count — conditions, luck, contingency.

**27.2.** Someone offers you corrective feedback on something you did. The feedback lands accurately.
- A. You take it in, test it, and adjust.
- B. You find reasons the feedback is off — the context, the framing, the timing, the specifics.

**27.3.** You are in a meeting where your area of expertise is being discussed. A junior colleague raises a point that points to something you missed.
- A. You acknowledge the point directly — that's a good catch, I missed that.
- B. You subsume the point into the larger frame you're holding, as if it were already accounted for.

##### Dyad 28 — HUMILITY vs SELF-CONTEMPT

**28.1.** You have just completed a piece of work that by any fair measure is good — not perfect, but good. You sit with the assessment.
- A. You register the quality honestly, noting both what works and what could be better.
- B. You discount the successes, finding the flaws that seem more real than what works, and moving on before acknowledgment settles.

**28.2.** Someone whose judgment you respect has just told you, specifically and clearly, that you did something well.
- A. You take the assessment as information and let it inform your sense of what you can do.
- B. You receive the praise while holding a private frame in which the assessment doesn't match what you know about yourself.

**28.3.** Corrective feedback has landed. The feedback is specific and actionable.
- A. You take it as useful information for adjustment.
- B. You take it as a piece of evidence fitting the self-view you already hold.

*Scorer note on the three HUMILITY-involving dyads: Dyad 10 option B probes tactical performance (deflection, disclaimers, audience-calibrated). Dyad 27 option B probes inflation (explaining-away-of-outperformance, resistance to being taught). Dyad 28 option B probes genuine non-performed deflation (evidence-of-success does not lift the baseline). A respondent selecting B across all three is rare and diagnostic; selecting B in one but not others is expected and informative.*

---

#### Stage 2B — Multi-Commitment Scenarios

35 scenarios, each surfacing 3-6 commitments with 4 response options. Post-revision calibration applied to all scenarios for option-signaling neutrality and scenario-signaling neutrality. (v0.2.1: 4 scenarios added 2M.26–2M.29; v0.2.3: 6 scenarios added 2M.30–2M.35 and 2M.26 Activates list updated CRUELTY → SCHADENFREUDE per direct-opposition correction.)

**Response format.** A | B | C | D | This situation does not map to my experience.

---

**2M.1 — The reception.** A project you have worked on for years is being received tonight. Reviews are mostly positive with one sharp critical one. At the reception: someone who made the project possible but won't speak up; a peer whose similar project last year did not land as well; a senior figure whose approval would shape the next chapter; your partner who has been through the years of the work. *Activates:* CALLING, CRAFT, APPROVAL, INTIMACY, HUMILITY, JOY.
- A. You circulate fully. Meaningful time with everyone.
- B. You focus on the senior figure. The next chapter opens here.
- C. You focus on the person who made it possible. You credit them publicly.
- D. You stay with your partner primarily. You greet others as they approach.

**2M.2 — The funeral.** Someone important to you has died. The arrangements fall partly to you. Several people have claims on your presence; your own grief is there; a work deadline is under pressure. *Activates:* INTIMACY, COMPASSION, EQUANIMITY, GRASPING, HOPE, SANCTITY.
- A. You manage arrangements, support the family, carry the week with composure.
- B. You let your own grief be present alongside everything else. Ask for help.
- C. You work the deadline at the edges of the week.
- D. You release the deadline, the arrangements, most of the adjacent demands. You are present with your own grief and with the family.

**2M.3 — The child's crisis.** Your adolescent or young-adult child is in a serious situation — hospital visit, legal matter, mental-health episode. The child's autonomy, their safety, an institution not handling it well, your partner's different read all converge. *Activates:* PROTECTIVE-LOVE, LIBERTY, TRUST, HARMLESSNESS, FAIRNESS, INTIMACY.
- A. You override the institution, override your partner's read, take control.
- B. You trust the institution with input. You align with your partner before acting.
- C. You side with your child's reading of what they need.
- D. You slow the situation. You ask more questions of everyone before acting. You accept the cost of the slower response and the risk that something could escalate while you are gathering information.

**2M.4 — The institutional failure.** An institution you have been loyal to for years is doing something you now believe is wrong. You have some capacity to influence. *Activates:* TRIBALISM, TRUTH, FAIRNESS, AUTHORITY, CALLING, WITNESS.
- A. You speak publicly.
- B. You raise it internally with everything you have.
- C. You raise it internally; if the response is inadequate, you leave rather than go public. Your energy goes toward other work where you can be effective; the institution's problem remains unsolved from your position outside it.
- D. You stay and continue to work. Your continued work is the answer.

**2M.5 — The gift.** Someone you did not expect has done something significant for you. They want nothing back explicitly, but you can feel the weight. *Activates:* APPRECIATION, GRATITUDE, ENTITLEMENT, SELF-IMAGE, JOY, INTIMACY.
- A. You accept fully and warmly. Thank you specifically.
- B. You accept with discomfort. Feel obligation. Work to clear the debt.
- C. You accept easily. Currents even out.
- D. You look for motivations. Accept with partial warmth.

**2M.6 — The old friend returned.** Someone you were close to fifteen years ago is back. Life has happened to them. Some changes are clearly for the worse. *Activates:* INTIMACY, WITNESS, TRUTH, ABANDONMENT, COMPASSION, GRASPING.
- A. You spend time with them as they are now.
- B. You look for the old person through the changes.
- C. Warm but distant.
- D. You name what you are noticing directly — that they have changed, that you have changed, that the old friendship is gone. You accept that the directness may close the connection entirely.

**2M.7 — The creative failure.** Significant work you've poured yourself into has not worked. The reception is clear. *Activates:* CRAFT, CALLING, HUMILIATION, WITNESS, TRUTH, HOPE.
- A. You name the flaws accurately and take responsibility.
- B. You distribute the failure across circumstances.
- C. You collapse for a period.
- D. You return to the work.

**2M.8 — The child's autonomy.** Your growing child is making a reasonable but not-what-you-would-choose choice. *Activates:* PROTECTIVE-LOVE, LIBERTY, TRUST, HOPE, WITNESS, GRASPING.
- A. You support the choice actively.
- B. You support the choice quietly.
- C. You continue to raise the alternative.
- D. You support the choice and also name your own disappointment. You include both in the relationship; your honesty may or may not land well for them.

**2M.9 — The partner's depression.** Your partner has entered a stretch of real depression. Nothing you can do will fix it. *Activates:* INTIMACY, HARMLESSNESS, EQUANIMITY, HOPE, TRUST, CALLING.
- A. You stay present in full. Your own work, rest, and stability substantially reduce; the partnership's needs organize your life until the depression shifts.
- B. You stay present while protecting your own ground. You are with them at the edges of your own work; you keep yourself functioning because a collapsed you is no use to them.
- C. You take partial distance.
- D. You treat the situation as ongoing negotiation. Presence when presence helps; distance when it does not; explicit conversation when either of you notices the arrangement is off.

**2M.10 — Wealth arriving.** An unexpected windfall has arrived — substantial but not life-changing. You are not in need. *Activates:* CALLING, CRAFT, COMFORT, PLEASURE, APPRECIATION, GRASPING.
- A. Most toward the mission.
- B. Use it to give yourself space for the work.
- C. Something meaningful non-work, save the rest.
- D. Save and protect.

**2M.11 — The move.** A significant professional opportunity requires moving. Your partner is willing but not enthusiastic. *Activates:* CALLING, INTIMACY, COMFORT, NOVELTY, TRUST, GRASPING.
- A. You take it.
- B. You decline.
- C. You negotiate a version.
- D. You bring the decision to your partner. Their enthusiasm or mere-willingness decides it. You are willing to lose the opportunity if they are not wholehearted.

**2M.12 — The parent's decline.** Your aging parent is declining slowly but unmistakably. Family members have different readings. *Activates:* PROTECTIVE-LOVE, EQUANIMITY, HARMLESSNESS, HOPE, INTIMACY, FAIRNESS.
- A. You take the lead.
- B. You share the lead with siblings.
- C. Present in daily life but don't drive arrangements.
- D. Hold back. Another family member is better positioned.

**2M.13 — The public figure.** A person you have admired for their public contribution is credibly accused of private wrongdoing. Evidence is strong but not incontestable. *Activates:* FAIRNESS, TRIBALISM, TRUTH, COMPASSION, AUTHORITY, WITNESS.
- A. You update your assessment. Contribution stands; wrongdoing also stands; the person is now both to you.
- B. You suspend judgment until the evidence is closer to incontestable. You apply the same evidentiary standard you would apply to anyone similarly accused.
- C. You remain in doubt because the figure matters to you. You notice that evidence accepted against others is being scrutinized more carefully here; you are not sure whether the extra scrutiny is appropriate or loyalty-driven.
- D. You defend the contribution and treat the accusations as separate. Whatever they did privately does not bear on what they contributed publicly.

**2M.14 — The routine interrupted.** You have set aside a time for a routine you maintain — morning practice, exercise, reading, writing, whatever holds the shape of this time. Today, something specific has pulled at you. *Activates:* EQUANIMITY, WONDER, GRATITUDE, CALLING, CRAFT, HOPE.
- A. You keep the ritual exactly as usual. Consistency is the point; the specific pulls will still be there in an hour.
- B. You begin the ritual, address the specific pull for a few minutes when it becomes loud, return. The hour is split but not abandoned.
- C. You do not begin the ritual today. The pull is what today needs; you give it the hour and return to the ritual tomorrow.
- D. You begin the ritual and let it take whatever form the day calls for — movement, silence, writing, simply sitting with what is present. The specific practice varies; the set-aside time holds.

**2M.15 — The gathering.** Friends at your home. Partway through, the conversation goes where it matters — someone is struggling. *Activates:* INTIMACY, PLAYFULNESS, APPROVAL, WONDER, ENTHUSIASM, SANCTITY.
- A. You meet the moment fully.
- B. You meet briefly and bring the evening back to lighter.
- C. You hold space privately.
- D. You do not steer the evening's direction. Whatever the room does with the offering is the evening. You stay present without managing.

**2M.16 — The friend's unwise choice.** Someone close making a choice you believe will harm them. *Activates:* INTIMACY, LIBERTY, HARMLESSNESS, TRUTH, COMPASSION, PROTECTIVE-LOVE.
- A. You support.
- B. You name concerns once, then support.
- C. You continue to name concerns.
- D. You actively oppose. You continue to work against the choice in whatever ways are available to you. You accept that this may damage the relationship.

**2M.17 — The community rupture.** Your community or organization is splitting. Mixed ties on both sides. *Activates:* TRIBALISM, FAIRNESS, TRUTH, INTIMACY, AUTHORITY, SANCTITY.
- A. You go with the side whose principles you share, accepting the loss of the friendships on the other side.
- B. You choose based on where the stronger relational ties pull. Your closest friends are split; you go with the majority of your ties even though the alignment with principle is mixed.
- C. You try to stay bridging.
- D. You step back from the community entirely.

**2M.18 — The betrayal.** Someone trusted has betrayed trust in a material way. They acknowledge it; they want to repair. *Activates:* INTIMACY, TRUTH, FORGIVENESS, FAIRNESS, WITNESS, GRASPING.
- A. You stay in the relationship and actively participate in rebuilding. You both know the betrayal happened; you both do the work to create whatever the new relationship becomes.
- B. You end the relationship. Trust broken at that level does not reconstruct.
- C. You hold the relationship at distance while they rebuild credibility.
- D. You release the resentment without driving reconstruction. Your inner ground is clear; you engage from accurate perception of what happened and of what the person is capable of. The relationship continues only to the degree the other person makes it continue.

**2M.19 — The adult child's life.** Your adult child has made a significant life choice and has asked for your response. *Activates:* PROTECTIVE-LOVE, LIBERTY, APPRECIATION, INTIMACY, HOPE, WITNESS.
- A. Full support, hold assessment private.
- B. Full support, offer honest assessment.
- C. Support with specific question or two.
- D. You support and actively celebrate the choice's strengths. If the weaknesses matter, they surface on their own; you are not the one bringing them up.

**2M.20 — The confrontation.** Physical confrontation unfolding. Aggressor threatening someone who cannot defend themselves. Not your target. *Activates:* FEROCITY, SELF-PRESERVATION, HARMLESSNESS, COMPASSION, FAIRNESS, WITNESS.
- A. You intervene directly and immediately.
- B. You intervene with what you have without mounting physical force.
- C. You call for help and position yourself to document.
- D. You step back.

**2M.21 — The lost years.** A period of your life was largely a mistake. Substantial years spent. *Activates:* TRUTH, HUMILITY, HOPE, FORGIVENESS, WITNESS, CALLING.
- A. You take the loss fully and direct what remains. The years are gone; the work now is to use what remains well.
- B. You find the continuity. The mistaken years produced learning, connections, capacities that matter now.
- C. You attribute the mistake to circumstances that shaped the path.
- D. You stay with the unclaimed grief of the loss. How long this takes is what it takes.

**2M.22 — The new love.** Early period of significant relationship. Real and specific. Showing you parts of yourself. *Activates:* INTIMACY, TRUST, WONDER, CRAFT, CALLING, SELF-IMAGE.
- A. You move fully in.
- B. You move in while watching yourself.
- C. You move slowly.
- D. You commit fully and stop examining. Whether this is the relationship or a repeat of old patterns is not a question you are holding; you are in it.

**2M.23 — The injustice.** Specific injustice witnessed. Speaking up will cost. The wronged person has not asked for intervention. *Activates:* FAIRNESS, HARMLESSNESS, FEROCITY, WITNESS, SELF-PRESERVATION, COMPASSION.
- A. You speak up clearly. The situation requires witness beyond private silence, and you accept the cost of saying so publicly.
- B. You speak privately with the person first.
- C. You speak up in proportion to cost and capacity.
- D. You do what is within your specific scope.

**2M.24 — The work ending.** A role or project central to your identity is ending. *Activates:* CALLING, GRASPING, EQUANIMITY, APPRECIATION, HOPE, INTIMACY.
- A. You let it end cleanly.
- B. You extend it where you can.
- C. You release it completely and move deliberately into something new.
- D. You take a period of unstructured time before the next thing. You do not have the next thing identified; you are willing to be without direction for a period.

**2M.25 — The inner realization.** You have caught yourself in a pattern you have been maintaining at cost to others. You have been defending it with frameworks that were serving its concealment from yourself. *Activates:* WITNESS, TRUTH, HUMILITY, SELF-IMAGE, INTIMACY.
- A. You name it to yourself and to the people most affected. You accept whatever falls out of the naming.
- B. You change the behavior quietly without surfacing the pattern to others.
- C. You soften the naming.
- D. You resist the catching.

**2M.26 — The enemy's collapse.** A public figure you have opposed for years and believe has caused substantial harm is now in sustained public difficulty — professional, legal, personal. The difficulty is real. Coverage is everywhere. *Activates:* COMPASSION, JOY, FAIRNESS, WITNESS, SCHADENFREUDE, SANCTITY.
- A. You note the development without seeking more of it. The harm they caused does not become entertainment in their suffering.
- B. You follow closely. You find satisfaction in the details.
- C. You take a position on the justice of the outcome and move on.
- D. You don't attend to it at all. Their situation isn't your business once they're out of positions of harm.

**2M.27 — The partnership rhythm.** A long-standing primary relationship has settled into rhythms that feel wrong in a way you can't locate immediately. The rhythms include you managing their moods to keep your own ground, or them managing yours. Days of real separateness feel destabilizing to one or both of you. *Activates:* INTIMACY, ENMESHMENT, LIBERTY, EQUANIMITY, WITNESS, TRUTH.
- A. You name what you are noticing directly and work toward the structural change that restores separateness as tolerable.
- B. You quietly build more separateness into your life without naming it. Walk the change in rather than discussing it.
- C. You conclude the rhythms are how you've come to love, and leave them alone.
- D. You notice the pattern and work on your own ground; your side of the dysregulation can change without requiring them to change theirs first.

**2M.28 — The unrecognized decade.** You are alone in a quiet hour thinking about the work of the last ten years — what was supposed to come, what did, what didn't. You feel the pull of two different accountings. *Activates:* GRATITUDE, BITTERNESS, HOPE, WITNESS, FORGIVENESS, TRUTH.
- A. You count what's come — including unexpected goods and people you would not have predicted. The not-yet-arrived is noted but not central.
- B. You count what hasn't come. The specific thing that was owed by any fair reckoning. You sit with what that has cost.
- C. You try to hold both accountings; they won't fully reconcile, and you accept that.
- D. You notice you've been keeping the account at all and wonder what releasing the accounting would require.

**2M.29 — The two attunements.** You have two people in your life whose presence is woven deeply into your daily rhythm. One is a person with a long-term dependency that genuinely requires your continuous attention — a child with a chronic condition, an aging parent in cognitive decline, a sibling whose independence has not fully developed. The other is an independent adult partner or close friend whose life is also closely joined to yours. A period arises when both are briefly apart from you at the same time — a week where the dependent person is in respite care and the independent partner is traveling. *Activates:* PROTECTIVE-LOVE, ENMESHMENT, INTIMACY, EQUANIMITY, LIBERTY, WITNESS.
- A. The dependent person's absence registers as concern about their care. The independent partner's absence registers as felt and continued-to-function-through — a different texture, both held without your own ground moving.
- B. Both absences register similarly — the week feels like functioning is substantially disturbed because both are away. Their return restores.
- C. The dependent person's absence is easier to hold than the independent partner's; you realize in the course of the week that the more destabilizing absence is the one that should have been the more tolerable one.
- D. The dependent person's absence is the primary weight of the week. The partner's barely registers — you realize the dependency has crowded the partner's presence into a background you stopped noticing. The return reveals the imbalance rather than resolves it.

**2M.30 — The outperformed meeting.** You are in a meeting where someone substantially younger and less credentialed has made an intervention that shows something you didn't see and should have. The room noticed. Your response will shape how you are regarded. *Activates:* HUMILITY, ARROGANCE, RESPECT, SELF-IMAGE, WITNESS, STATUS.
- A. You acknowledge the intervention directly and credit the person publicly. The room sees you acknowledge being wrong.
- B. You absorb the intervention as if you had already been considering it, moving forward without explicit credit.
- C. You accept the point on the substance while subtly signaling that the framing was yours. Credit stays partly with you.
- D. You find a reason why the intervention, while right in a narrow sense, misses something larger that only you would see.

**2M.31 — The dismissed colleague.** A colleague you have held in quiet contempt for years has produced work that cannot be dismissed on merit. You are asked for a written assessment that will shape their advancement. *Activates:* RESPECT, CONTEMPT, FAIRNESS, SELF-IMAGE, WITNESS, STATUS.
- A. You write the accurate assessment. Their work is strong; you say so.
- B. You write a technically accurate assessment with qualifiers that preserve your prior frame — strong within a narrow band, with context-dependent caveats that soften the assessment.
- C. You decline the task. Your position is too biased to be the right evaluator.
- D. You write a careful assessment that foregrounds concerns proportionate to the work, so strengths and concerns balance roughly as your prior frame would have predicted.

**2M.32 — The success that does not land.** You have completed a piece of work that is, by the assessment of people whose judgment you trust, good — maybe even important. You sit with it in a quiet hour. *Activates:* HUMILITY, SELF-CONTEMPT, CALLING, HOPE, CRAFT, TRUTH.
- A. You register the quality honestly. You note what worked, what didn't, and you let the achievement settle.
- B. You move on to the next piece of work before the acknowledgment can settle. The next thing is what matters; this is done.
- C. You find the flaws that feel more real than what others have seen as strong. The praise is a misreading.
- D. You share the work privately with people you trust to offer the corrective feedback the public reception didn't include.

**2M.33 — The easy considerateness.** You are in an extended period of work that has pushed you to the edge of what you can sustain. Today several people cross your path: a stranger needing a small help; someone who has been consistently undermining you and is now asking a favor; an ordinary colleague making small talk. *Activates:* KINDNESS, WARMTH, SELF-PRESERVATION, CRUELTY, WITNESS, HARMLESSNESS.
- A. You extend ordinary considerateness to the stranger and the colleague. With the undermining person, you decline the favor clearly and move on. The ordinary-colleague and stranger receive ordinary considerateness; the undermining person receives a clean refusal without performance or punishment.
- B. You extend ordinary considerateness to all three, including the undermining person. The favor costs little; the consistency of kindness matters more than the history.
- C. You extend considerateness to the stranger but reduce the register with both the colleague and the undermining person. At your edge, non-essential warmth is rationed.
- D. You decline the favor from the undermining person; the decline is pointed — they register the refusal is specifically directed at them. The colleague and stranger receive normal kindness.

**2M.34 — The closed chapter.** Someone wronged you materially some time ago. The wrong is settled — consequences have played out, time has passed, the situation is closed in the external sense. You notice your relationship to the memory. *Activates:* HARMLESSNESS, FORGIVENESS, RESENTMENT, WITNESS, EQUANIMITY, HOPE.
- A. The memory no longer generates charge when it surfaces. The wrong is known but not carried.
- B. The memory still produces a specific response — you replay what you should have said or done, or what consequence you would have wanted them to face. The replaying has a specific satisfaction.
- C. On the surface you remain neutral, but you keep mental track of what happened; should an opportunity to even the account arise, you would take it.
- D. You have deliberately let the grievance fade through ongoing practice — conversation, writing, time, attention. The fading is work, not automatic.

**2M.35 — The invitation to speak.** You have been invited to speak publicly about work you have done well. Several attendees know the work; others don't. Speaking accurately about what you've done and what you can do is part of what's asked. *Activates:* HUMILITY, FALSE HUMILITY, SELF-CONTEMPT, TRUTH, CALLING, APPROVAL.
- A. You speak accurately. What you've done and what you can do, without inflation or deflation.
- B. You speak with performed disclaimers — "I'm not really the expert on this" and similar. Audience experiences humility; you know the disclaimers are performance.
- C. When it comes time to describe what you've done, the description comes out smaller than what is true. Not performatively — it is simply what feels like yours to claim.
- D. You decline the invitation, framed as appropriate deference to those who could speak better.

---

### STAGE 3 — Constitutional Pressure-Tests

**Instrument type.** Scenarios placing a specific commitment under maximum pressure, to test whether a weight of 8-9 genuinely represents constitutional status or merely high-weight. A constitutional commitment holds under pressure; high-weight merely wavers.

**Coverage.** 17 scenarios, one per typical constitutional candidate (v0.2.1 late: 3.14 CRAFT added 2026-04-19; v0.2.3: 3.15 RESPECT, 3.16 KINDNESS, 3.17 HARMLESSNESS internal-posture added).

**Response format.** A | B | C | D | This situation is not one I can imagine facing.

**Scorer-facing note.** The hold option varies by scenario (typically but not always A). Instrument documentation specifies hold per scenario. Selection of hold under pressure indicates constitutional status. Waver selection indicates high-weight but not constitutional.

---

**3.1 — Pressure-test for TRUTH.** A parent of yours is in the final months of a terminal illness. Their spouse — your other parent — died several years ago. You have come to know, with certainty, something about the deceased spouse's life that your dying parent never discovered: the deceased had a sustained affair that the dying parent does not know about. Nothing can be acted on. The deceased is gone. The dying parent is dying. The knowledge will cause suffering if it arrives.
- A. You tell them. Fully, specifically, directly. You accept the suffering this causes.
- B. You acknowledge the existence of the thing without the specific details.
- C. You do not tell them. What they go to their death believing about their marriage is what they will believe.
- D. You tell someone else who will decide what to do — a sibling, a friend, a counselor. The decision is not yours alone to carry.

*(Hold: A, because constitutional TRUTH serves the listener's right to accurate understanding of their own life even when the knowledge will cause suffering and cannot be acted on. Withholding under these conditions registers as TRUTH wavering under COMPASSION or HARMLESSNESS pressure — legitimate as configuration but not constitutional-TRUTH holding. Respondents who select C are registering an honest pattern of TRUTH-plus-wisdom-constraint, where TRUTH at high weight is governed by COMPASSION considerations. The instrument registers C as waver relative to constitutional TRUTH specifically; this is not a moral judgment but a calibration point. Respondents who find this scenario outside their experience should mark the bypass option.)*

**3.2 — Pressure-test for HARMLESSNESS.** An action you can take will prevent substantial suffering to many people you will never meet. The action will cause real, direct, specific harm to one person you do know — someone who has not wronged anyone, simply in the wrong position. The numbers are clear. No one else can take the action.
- A. You do not take the action. You do not cause the specific harm.
- B. You search for a path that does not require the specific harm. You accept the delay and the risk that the path does not exist.
- C. You take the action. You cause the specific harm to prevent the distant suffering.
- D. You take the action and ensure the specific person is compensated, cared for, or supported in the aftermath.

*(Hold: A, because constitutional HARMLESSNESS refuses to cause harm even under consequentialist pressure.)*

**3.3 — Pressure-test for PROTECTIVE-LOVE.** Someone you are responsible for — a child with a chronic condition, a parent in cognitive decline, a sibling with sustained dependency — requires ongoing protection that costs you substantially over years. Financial outflow, professional trajectory altered, relationships strained, sleep and health affected. The protected cannot fully repay any of this. You can see the decade ahead.
- A. You continue the protection at the sustained cost. The decade ahead is what it is.
- B. You continue the protection while working to reduce specific costs where possible.
- C. You transition the primary protection to someone else or to institutional care.
- D. You step back from being the primary protector.

*(Hold: A, because constitutional PROTECTIVE-LOVE sustains the protection at the cost to self that the commitment entails, without transferring the responsibility even as costs accumulate.)*

**3.4 — Pressure-test for CALLING.** The work you have been called to requires a sustained cost to yourself over years — financial, social, relational. Not a heroic cost in one moment but a slow, grinding cost. You have done it for a decade; you can see the decade ahead.
- A. You continue the work.
- B. You continue the work while negotiating reductions in specific costs.
- C. You transition out of the work into something that serves the calling with less cost.
- D. You step away from the work.

*(Hold: A, because constitutional CALLING sustains the work under sustained cost; the work is where meaning lives and cost-reduction negotiations are not the same as holding the calling.)*

**3.5 — Pressure-test for FAIRNESS.** A decision is before you where fair treatment requires imposing serious cost on someone whose loyalty to you has been consistent and whose service has earned accumulated debt.
- A. You impose the fair cost. You explain privately to them why. The relationship may not survive.
- B. You impose a softened version of the cost. The standard bends for accumulated loyalty in this case.
- C. You find a different solution that spares the person. The decision still looks fair externally.
- D. You reverse the decision. Loyalty governs this case.

*(Hold: A, because constitutional FAIRNESS applies consistent standards regardless of accumulated loyalty — loyalty-driven bending of fair standards is the pattern FAIRNESS at constitutional weight refuses.)*

**3.6 — Pressure-test for INTIMACY.** A relationship you are in can deepen significantly if you allow yourself to be known in ways you have spent decades protecting against. The other person has made space; they are not asking. Deepening requires bringing into the relationship aspects of yourself — failures, fears, things you consider shameful — that you have kept contained. The cost of deepening is the loss of containment. The cost of not deepening is the ceiling on what this relationship can become.
- A. You deepen. You bring in what you have been containing.
- B. You deepen in stages, bringing in specific contained material over time.
- C. You signal openness without fully opening.
- D. You do not deepen beyond where the relationship currently is.

*(Hold: A, because constitutional INTIMACY accepts the cost of containment-loss when depth is available; staged or managed opening is waver territory.)*

**3.7 — Pressure-test for LIBERTY.** A situation asks you to accept constraint — on your speech, movement, choices — that you consider unjustified. Not catastrophic. Accepting spares you and people around you difficulty. Refusing costs you and them.
- A. You refuse. You accept the difficulty this brings to you and to those around you.
- B. You accept the constraint while continuing to work against it through other channels.
- C. You negotiate a modified version of the constraint in exchange for cooperation elsewhere.
- D. You accept the constraint. You pick different battles.

*(Hold: A, because constitutional LIBERTY refuses unjustified constraint even at cost to self and to others; accepting constraint while working against it through other channels is waver-pattern.)*

**3.8 — Pressure-test for SANCTITY.** Something you regard as genuinely sacred can be traded for something large and valuable. The trade is legitimate. The sacredness is subjective; to others the thing is less inviolable than to you.
- A. You refuse the trade.
- B. You restructure what the trade is. You find a version where the sacredness is preserved in some form.
- C. You delay the decision and seek a path that serves the benefit without requiring the trade.
- D. You make the trade and accept that you are losing something that cannot be replaced.

*(Hold: A, because constitutional SANCTITY refuses to reduce the sacred to instrumental terms — restructuring-the-trade or delay-seeking-alternative both preserve instrumentation at the margin.)*

**3.9 — Pressure-test for COMPASSION.** A person who has caused real and deliberate harm to you and to people you love is in a situation requiring care. They need help you could offer; no one else is positioned. Offering will cost you; more, it will feel like a betrayal to some of the people who were harmed.
- A. You offer the help. You meet them directly and do what is needed.
- B. You arrange for help to reach them without your involvement being visible.
- C. You offer help through a third party.
- D. You decline to help. This person is outside what you can extend care to.

*(Hold: A, because constitutional COMPASSION extends care without differentiating by what the sufferer has done to you — arranging-help-without-visible-involvement still extends care but through a frame that protects the helper's social position, which is partial waver.)*

**3.10 — Pressure-test for WITNESS.** You have caught yourself in a pattern you have been maintaining at real cost to others. The pattern is subtle. You could continue with minor adjustments that mask it rather than change it. The full seeing would require staying with the pattern's reality long enough for the seeing to settle.
- A. You see it fully and stay with the seeing. You let the seeing produce whatever change it produces, including changes you do not yet know will be required.
- B. You see it fully but manage the pace of what the seeing produces.
- C. You see it partially. You make the minor adjustments that mask the pattern.
- D. You turn the noticing into an ongoing observation that does not require commitment to change.

*(Hold: A, because constitutional WITNESS does not manage the pace of what accurate seeing would produce — managed seeing is the hallmark of near-enemy scrupulosity or of WITNESS-captured-by-SELF-IMAGE.)*

**3.11 — Pressure-test for HOPE.** A situation that matters to you has reached a state where the evidence supporting the future you have been holding open is now genuinely thin.
- A. You keep the future open while accepting that the evidence has genuinely thinned. The open-ness is not based on expected outcome but on something else you find you can stand on.
- B. You update the hope. You hold a smaller version of the open future.
- C. You suspend. You neither hold the hope nor let it go.
- D. You let the specific hope go. You find other anchors.

*(Hold: A, because constitutional HOPE keeps the future open anchored to something other than current evidence — meaning, purpose, another person, the work, faith; Frankl's canonical reference.)*

**3.12 — Pressure-test for FORGIVENESS.** A person who has harmed you significantly has refused accountability, refused apology, refused engagement. Time has passed. The harm continues to affect your life.
- A. You release the resentment. The harm is real; your judgment of the person is unchanged; the release is something you do for yourself, not for them.
- B. You release the resentment for the most part. Some residue remains.
- C. You release on specific occasions and find it returning on others.
- D. You keep the resentment. The harm was real, and active carrying of it feels more accurate to you than release would.

*(Hold: A, because constitutional FORGIVENESS releases resentment without requiring the harmer's acknowledgment, apology, or change. Release conditional on the harmer's repair is either CAPITULATION (releasing judgment) or FORGIVENESS bounded by reciprocity-expectation — both sit short of constitutional FORGIVENESS which proceeds from the forgiver's own ground.)*

**3.13 — Pressure-test for FEROCITY.** A situation calls for a forceful response that only you can deliver. The response will cost you — reputation, standing, relationships, perhaps safety. The situation is real; the response is needed; no one else is positioned.
- A. You mount the response.
- B. You mount a partial response — what you can afford to do.
- C. You coordinate with others to produce a distributed response.
- D. You do not mount the response.

*(Hold: A, because constitutional FEROCITY mounts the response when called even at sustained cost to self — partial response and coordinated-distributed response are legitimate tactical choices but register as waver at constitutional-probe level.)*

**3.14 — Pressure-test for CRAFT.** A project you have invested substantial time in faces pressure that would reward releasing-as-adequate over releasing-as-quality. The pressure takes a concrete form: a financial incentive to finish now, a time constraint imposed by others, a stakeholder who will accept less than your standard and be satisfied with it, or a personal cost to holding the line (extended effort, delayed income, continued strain). The work could be released at current quality without penalty and nobody but you would know the difference. Holding the quality standard requires sustained additional cost.
- A. Hold the standard. Accept the cost. Release when the work meets the standard, not when the pressure releases.
- B. Release at adequate quality now. Note the compromise honestly; resume standard on the next work.
- C. Hold the standard by reshaping the environment — remove the pressure by changing the arrangement (decline the contract, renegotiate the timeline, step away from the stakeholder) rather than by absorbing the cost.
- D. Examine whether the quality standard itself is what's holding — sometimes the standard becomes avoidance of completion, fear of reception, or perfectionism. Release when the honest check confirms the standard is real craft, not its near enemy.

*(Hold: A, because constitutional CRAFT holds the quality standard against pressure that would reward release-as-adequate — reshaping the environment or examining-whether-standard-is-avoidance are both legitimate moves but sit adjacent to hold rather than at it.)*

**3.15 — Pressure-test for RESPECT.** Someone whose worth you have recognized — in their work, in their capability, in the tradition they represent — has taken a public position that is costly to you. Friends or allies of yours are mounting pressure on you to publicly withdraw your respect, to signal that this person no longer merits it. The position the person has taken, while you disagree with it, reflects the same qualities of mind that made you recognize their worth in the first place — applied now to a domain where your judgments differ. Their taking this position is not a betrayal of what you respected; it's the same faculty operating with a different conclusion.
- A. You hold the respect publicly. You disagree with the position; you do not withdraw the recognition of worth.
- B. You hold privately while avoiding public engagement on the matter either way.
- C. You publicly soften — a hedged distancing that lets your allies read what they want while the person can read something else.
- D. You publicly withdraw the respect. Your allies are satisfied; the cost is accepted.

*(Hold: A, because constitutional RESPECT does not withdraw earned recognition under coalition pressure.)*

**3.16 — Pressure-test for KINDNESS.** You are at your edge — work pressure, personal strain, accumulated exhaustion. Across a period of days, small encounters keep arriving that call for ordinary kindness — the held door, the offered help, the patient attention for someone who could have been passed by. The cost of extending across all of these is real: energy you do not have, attention drawn from work you cannot afford to lose. The cost of withholding in any one of them is minor; no one would call it wrong; capacity-based rationing would be understood.
- A. You extend ordinary kindness across the encounters as they arise. Your edge is real; the kindness is not conditional on your state.
- B. You extend kindness but in a reduced form — functional, friendly enough, but without the fuller engagement you would extend on an ordinary day.
- C. You extend kindness selectively — where it seems to matter most, where it costs least; you accept that some ordinary kindnesses you would normally extend do not happen this period.
- D. You withdraw from encounters where possible. You route around rather than pass through; the kindness-opportunities reduce because you reduce your exposure.

*(Hold: A, because constitutional KINDNESS is not conditional on the holder's state or on what can be withheld without material consequence.)*

**3.17 — Pressure-test for HARMLESSNESS (internal posture).** Someone has wronged you materially and deliberately. Time has passed. They have not apologized, shown no acknowledgment, and are now in circumstances where a small action by you would cause them real difficulty — not wrongful action, but the kind of observation, referral, or information-sharing that would legitimately follow from what you know. What you would do is within the frame of ordinary accuracy; no one would call it wrong. The opportunity will persist; no urgency either way. Your grievance, if you check for it, is live.
- A. You do not take the action. The wrong is known; the grievance is no longer organizing your behavior; opportunities to even the account do not function as temptations.
- B. You consider the action and decline it on reflection, while noticing that the consideration itself signals that release has not fully landed.
- C. You note the opportunity and hold it available — should another opening arise that combines cleanly with the first, you would take both.
- D. You take the action. You judge that what you would do is what anyone in that position would do; any influence from the grievance, if present, is below the threshold you can detect.

*(Hold: A, because constitutional HARMLESSNESS internal posture has released the grievance such that opportunities to even the account do not function as temptations.)*

---

### Aspirational-reporting defense

A known failure mode: respondents select the hold option across all pressure-tests because they want to appear constitutional in everything. Framework defenses:

1. **Instrument language:** "actually do, not wish to do" framing. Scenario costs specifically vivid so hold feels expensive rather than abstract.
2. **Statistical anomaly detection:** real people carry 3-7 constitutional commitments, not 13. Respondents selecting hold across all 13 trigger a scorer flag.
3. **Stage 2 cross-reference:** Stage 2 multi-commitment scenarios probe the same commitments without labeling hold. A respondent answering hold-style in Stage 3 but waver-style in Stage 2 is revealing that Stage 3 is aspirational.
4. **Inference layer confidence tagging:** weights derived from pressure-test holds are high-confidence only when corroborated across Stage 1 ratings, Stage 2 dyad patterns, and Stage 2 multi-commitment selections.

---

### Instrument state

- Stage 1: 66 portraits (~5,400 words; v0.2.3 additions portraits 60-66; content rewrites for portraits 5 TRIBALISM and 12 HARMLESSNESS)
- Stage 2 dyads: 28 dyads × 3 scenarios = 84 scenarios (~13,500 words; v0.2.3 additions Dyad 22 replacement plus Dyads 25-28)
- Stage 2 multi-commitment: 35 scenarios (~7,600 words; v0.2.3 additions 2M.30-2M.35 and 2M.26 Activates update)
- Stage 3: 17 pressure-tests (~3,200 words; v0.2.3 additions 3.15-3.17; inline Hold annotations propagated across all 17 pressure-tests)

Total ~29,700 words of psychometric instrument material. All stages calibrated for no option-signaling and no scenario-signaling.

---

*Assessment instrument v0.2.1 — complete. Administer per flow specified in §VII of this document. Score against the inference layer in §V of this document.*

*v0.2.1 additions 2026-04-19: Portraits 57 (CRUELTY), 58 (BITTERNESS), 59 (ENMESHMENT). Dyads 22 (COMPASSION vs CRUELTY), 23 (INTIMACY vs ENMESHMENT), 24 (GRATITUDE vs BITTERNESS). Multi-commitment scenarios 2M.26 (enemy collapse — CRUELTY probe), 2M.27 (partnership rhythm — ENMESHMENT probe), 2M.28 (unrecognized decade — BITTERNESS probe), 2M.29 (two attunements — ENMESHMENT object-modulation probe for dependent-other vs independent-adult distinction). 2M.29 option A revised to strip virtue-language signal ("welcomed-back without dysregulation" → "a different texture, both held without your own ground moving"); option D revised from practitioner-specific spiritual-bypassing probe to attention-monopolization pattern (dependency crowding out partnership).*

*v0.2.1 late addition 2026-04-19: 3.14 CRAFT pressure-test drafted by framework architect and added. CRAFT had been identified as a constitutional candidate during Larry's self-run inference report without corresponding pressure-test coverage in the instrument; the gap was closed same-day.*

*v0.2.3 additions 2026-04-21: 7 new portraits (60 KINDNESS, 61 RESPECT, 62 WARMTH primary; 63 CONTEMPT, 64 SELF-CONTEMPT, 65 ARROGANCE, 66 SCHADENFREUDE character-spec). 2 portrait rewrites (5 TRIBALISM and 12 HARMLESSNESS) for renamed commitments with v0.2.3 behavioral dimensions surfaced. Dyad 22 replaced (KINDNESS × CRUELTY) per direct-opposition correction; Dyads 25-28 added (COMPASSION × SCHADENFREUDE, RESPECT × CONTEMPT, HUMILITY × ARROGANCE, HUMILITY × SELF-CONTEMPT); scorer note added after Dyad 28. 6 new multi-commitment scenarios 2M.30-2M.35; 2M.26 Activates list corrected CRUELTY → SCHADENFREUDE. 3 new pressure-tests (3.15 RESPECT, 3.16 KINDNESS, 3.17 HARMLESSNESS internal-posture); inline Hold annotations propagated across all 17 pressure-tests.*

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

The Inference Layer (§V), Learning Architecture (§VI), and Stage 2A Life-Context Direct Pass (§VIIA) carry the per-tier behavioral specification beyond the summary table above.

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

1. Confirm full processing of this framework — §II Library, §III Schema Specification, §IV Three-Stage Assessment Instrument, §V Inference Layer, §VI Learning Architecture, §VII Tier-Dependent Interview Flows, §VIIA Stage 2A Life-Context Direct Pass — and MindSpec v0.4 specification.
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
Name: MindSpec Interview
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
File Location: ~/Documents/vault/Framework — MindSpec Interview.md
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

*v0.2.3 correction 2026-04-21: CRUELTY direct-opposition corrected to KINDNESS (general-encounter domain); COMPASSION direct-opposition corrected to SCHADENFREUDE (suffering-activated domain). See current CRUELTY and COMPASSION entries in §II for operational state.*

---

*Inference layer v0.2.3 (merged as §V) — 14 pairwise rules (Rule 9 split into 9a/9b/9c; Rule 14 FEROCITY-to-WRATH transfer), 20 selfishness indicators, 6 anti-selfishness indicators, normalization constant 10, reliability math, weight adjustment math, universal mode application except Tier 1.*

*Learning architecture v0.2.3 (merged as §VI) — ledger schema (markdown-file storage surface per §VI.1 architecture note), within-context updates, modification provenance, six required safeguards.*
