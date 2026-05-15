---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-01
date modified: 2026-05-01

---

# MODE: Quick Orientation

```yaml
# 0. IDENTITY
mode_id: quick-orientation
canonical_name: Quick Orientation
suffix_rule: analysis
educational_name: quick orientation in unfamiliar terrain

# 1. TERRITORY AND POSITION
territory: T14-orientation-in-unfamiliar-territory
gradation_position:
  axis: depth
  value: light
adjacent_modes_in_territory:
  - mode_id: terrain-mapping
    relationship: depth-heavier sibling (thorough)
  - mode_id: domain-induction
    relationship: depth-molecular sibling (built Wave 4)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "I'm dropping into this domain cold"
    - "give me the quick lay of the land"
    - "I have ten minutes — what do I need to know"
    - "what are the main bits I should be aware of"
    - "where do I start with this"
  prompt_shape_signals:
    - "quick orientation"
    - "quick overview"
    - "quick lay of the land"
    - "high-level intro to"
    - "what's this about"
    - "give me the gist of"
    - "where do I start"
disambiguation_routing:
  routes_to_this_mode_when:
    - "user is new-to-domain AND has time pressure or wants light first-pass"
    - "user wants the major sub-areas and entry points without deep dive"
    - "input is a defined domain or space the user is unfamiliar with"
  routes_away_when:
    - "user wants thorough lay-of-the-land with sub-areas + open questions + entry points" → terrain-mapping
    - "user wants molecular induction across multiple domains or layered orientation" → domain-induction
    - "user is exploring an open space generatively, not orienting analytically" → passion-exploration (T20)
when_not_to_invoke:
  - "User already knows the domain well — orientation is overkill" → mode appropriate to user's actual question
  - "User wants relationship structure rather than orientation" → relationship-mapping (T11)
  - "User wants spatial-composition reading on aesthetic input" → T19 modes

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: descriptive

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [domain_name, user_existing_familiarity, orientation_purpose]
    optional: [time_budget, downstream_use_case]
    notes: "Applies when user names the domain explicitly and states why they want orientation."
  accessible_mode:
    required: [domain_or_topic]
    optional: [why_user_wants_orientation]
    notes: "Default. Mode infers familiarity level and purpose from prompt phrasing."
  detection:
    expert_signals: ["I have N minutes", "domain is X", "purpose of orientation is", "downstream I'll need"]
    accessible_signals: ["quick orientation", "quick overview", "give me the gist", "where do I start"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Ask: 'What domain or topic do you want a quick orientation on?'"
    on_underspecified: "Ask: 'Are you trying to make a decision, write something, or just get the lay of the land?'"
# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the orientation actually surveyed the major sub-areas of the domain, or has it focused narrowly on one corner the analyst happens to know best?"
    failure_mode_if_unmet: corner-bias
  - cq_id: CQ2
    question: "Are the foundational distinctions named in the orientation actually load-bearing for the domain, or are they decorative?"
    failure_mode_if_unmet: decorative-distinction
  - cq_id: CQ3
    question: "Has the orientation flagged the predictable wrong impressions a newcomer would form from light exposure, so the user is forewarned?"
    failure_mode_if_unmet: misconception-blindness
  - cq_id: CQ4
    question: "Has the depth been honestly tier-1 (light), or has the analysis crept into tier-2 territory and exceeded the user's time budget?"
    failure_mode_if_unmet: scope-creep

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: corner-bias
    detection_signal: "Sub-areas are concentrated in one quadrant of the domain; major established sub-areas are absent."
    correction_protocol: re-dispatch
  - name: decorative-distinction
    detection_signal: "Foundational distinctions are named but the user could navigate the domain ignoring them; they are not actually load-bearing."
    correction_protocol: re-dispatch
  - name: misconception-blindness
    detection_signal: "No common misconceptions section, or misconceptions named are too obscure to actually trip a newcomer."
    correction_protocol: flag
  - name: scope-creep
    detection_signal: "Output is structurally tier-2 (terrain-mapping shape) rather than tier-1; user's time budget would be exceeded."
    correction_protocol: re-dispatch (or escalate to terrain-mapping if appropriate)
  - name: contested-as-settled
    detection_signal: "Active debates in the domain are presented as settled facts; orientation lacks 'this is contested' flagging."
    correction_protocol: flag

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - kuhn-paradigm-structure (when domain has competing paradigms)
  foundational:
    - kahneman-tversky-bias-catalog

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~1min
escalation_signals:
  upward:
    target_mode_id: terrain-mapping
    when: "User wants thorough orientation with sub-areas, open questions, contested points, and entry-point chains."
  sideways:
    target_mode_id: passion-exploration
    when: "User is actually exploring an open space generatively, not orienting analytically; route to T20."
  downward:
    target_mode_id: null
    when: "Quick Orientation is the lightest mode in T14."
```

## DEPTH ANALYSIS GUIDANCE

Depth in Quick Orientation is honest depth restraint: the orientation must give the user a usable map without exceeding the tier-1 time budget. A thin pass that says "this domain is broad and complex" fails by giving the user nothing actionable; a thick pass that exceeds the budget fails by violating the contract. The right depth names three-to-five major sub-areas, the foundational distinction(s) that organize the domain, and the entry-point concepts a newcomer should learn first. Test depth by asking: does the user, having read this, know where to look next?

## BREADTH ANALYSIS GUIDANCE

Widening the lens in Quick Orientation means deliberate scanning across the full domain landscape before narrowing to three-to-five sub-areas: include the established core, the live frontier, the dissenting traditions, and the adjacent domains that share vocabulary. Even when only three sub-areas are surfaced, the breadth pass ensures they are spread across the domain rather than concentrated in one corner. Common misconceptions are surveyed and the most predictable ones flagged.

## EVALUATION CRITERIA

Evaluate against the four critical questions: (CQ1) corner bias; (CQ2) decorative distinction; (CQ3) misconception blindness; (CQ4) scope creep. The named failure modes (corner-bias, decorative-distinction, misconception-blindness, scope-creep, contested-as-settled) are the evaluation checklist. A passing Quick Orientation output names three-to-five sub-areas spread across the domain, surfaces load-bearing distinctions, flags common newcomer misconceptions, distinguishes settled from contested, and stays within tier-1 depth.

## REVISION GUIDANCE

Revise to broaden coverage where the draft has stayed in one corner of the domain. Revise to drop decorative distinctions and replace them with load-bearing ones. Revise to add common misconceptions where the section is empty or too obscure. Resist revising toward depth — the mode's value is in honest tier-1 restraint; if the situation actually warrants tier-2, escalate to terrain-mapping rather than over-deliver here. Resist presenting contested points as settled.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a tier-1 orientation packet — domain definition, distributed sub-area atoms, load-bearing distinctions, concrete entry points, predictable-newcomer misconception atoms, and a settled-vs-contested tag per atom**. The tier-1 budget is part of the contract; corpus expansion is its own failure here. The atoms are:

1. **Domain-definition atom.** A single-sentence definition of the domain, stated once at the corpus head. Cross-stream paraphrase collapses to one canonical statement.

2. **Sub-area atoms — three to five, spread across the domain.** Each carries: sub-area name, one-line characterization, and quadrant-tag locating it within the domain's terrain (established-core / live-frontier / dissenting-tradition / adjacent-shares-vocabulary). Corner-bias is the named failure mode; when all surviving sub-area atoms carry the same quadrant-tag, the breadth pass failed. Sub-areas spread across at least three quadrants is the breadth marker.

3. **Foundational-distinction atoms — load-bearing only.** Each carries: distinction name, the two (or more) terms it distinguishes, and a load-bearing test — "the user could not navigate the domain ignoring this distinction because [specific consequence]." Decorative-distinction is the named failure mode; distinctions that fail the load-bearing test do not survive into the corpus.

4. **Entry-point atoms — concrete first concepts or first questions.** Each names: the concept-to-learn or question-to-ask, and why this is the right starting point given the domain's structure (not just "this is foundational" but "this unlocks understanding of X, Y, Z subsequent concepts").

5. **Misconception atoms — predictable newcomer misconceptions.** Each carries: misconception statement, one-line correction, and a probability-tag — how likely a newcomer with light exposure would form this misconception. Misconception-blindness is the named failure mode; misconceptions too obscure to actually trip a newcomer do not survive — the corpus carries the predictable-misconception subset.

6. **Settled-vs-contested tag — per atom.** Every sub-area, distinction, entry-point, and misconception atom carries a tag: settled / contested / mixed. Contested-as-settled is the named failure mode; presenting active debates as settled facts is its corpus signature. When streams disagreed on the settled/contested tag for the same atom, the contested tag wins (audit conservatism on certainty).

7. **Escalation-pointer atom.** A single corpus-level atom names that terrain-mapping (T14 sibling) is available when the user wants deeper orientation, with the specific signals that would trigger escalation (more time available; sub-areas need open-questions enumeration; entry-point chains need elaboration). The escalation pointer is operative, not decorative — it gives the user a concrete handoff.

8. **Tier-1 budget atom.** A single atom flags that the corpus has stayed within tier-1 depth — three-to-five sub-areas (not ten), one-line characterizations (not paragraphs), foundational distinctions (not full taxonomies). Scope-creep is the named failure mode; corpus expansion beyond the tier-1 envelope is its signature. When the streams' material exceeds tier-1, the bloat strip prunes back to the envelope, and the corpus carries an explicit "tier-1: expansion-candidates exist; escalate to terrain-mapping for full coverage" atom.

**Mode-specific bloat patterns to cut during the bloat strip:**

- **Multi-paragraph sub-area treatments** — sub-areas elaborated beyond one-line characterizations. Scope-creep residue at sub-area level; the tier-1 budget is one line per sub-area.
- **Decorative distinction phrasing** — distinctions named without load-bearing tests ("the field distinguishes between X and Y"). Decorative-distinction residue; either the load-bearing test is added or the distinction does not survive.
- **Obscure-misconception padding** — misconceptions that a typical newcomer would not actually form. Misconception-blindness residue; the corpus carries predictable misconceptions only.
- **Corner-bias residue** — sub-area atoms concentrated in one quadrant of the domain. Corner-bias residue; the bloat strip rebalances by either dropping over-represented atoms or surfacing under-represented quadrants from the stream material.
- **Tier-2 phrasing residue** — content that reads as terrain-mapping rather than quick-orientation ("the field's open questions include...", "the methodological debate centers on..."). Scope-creep residue; the phrasing either compresses to tier-1 form or migrates to the escalation-pointer atom as a reason-to-escalate.
- **Contested-as-settled phrasing** — domain content stated as established when it is actively debated. Contested-as-settled residue; the settled/contested tag is added or the atom is dropped.

**What NOT to collapse:**

- **Sub-area-quadrant disagreement** — when the two streams identified different quadrants for the same sub-area (one says "established-core", the other says "live-frontier"), preserve as a tension atom. The disagreement is a finding about the domain's contested centering, often more valuable to a newcomer than a settled quadrant tag.
- **Settled-vs-contested disagreement** — when streams disagreed on whether a domain element is settled or contested, the contested tag wins. The asymmetry is audit-conservative: a falsely-marked-contested atom is recoverable downstream (the user investigates and finds it settled), but a falsely-marked-settled atom misleads.
- **Entry-point sequencing disagreement** — when streams proposed different first-concepts to learn, preserve both as parallel entry-point atoms with their respective rationales. Different newcomers may have different existing-knowledge bases; multiple valid entry points are a feature, not bloat.

## VERIFICATION CRITERIA

Verified means: a one-line domain definition is present; three-to-five major sub-areas are listed and spread across the domain rather than corner-concentrated; foundational distinctions are load-bearing (the user could not navigate without them); entry points are concrete; common misconceptions are flagged; settled vs. contested is distinguished; the output stays within tier-1 depth budget; the four critical questions are addressable from the output.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **tier-1 orientation packet — short, distributed, load-bearing**. Place the consolidated-corpus atoms into the following sections, in this order:

1. **Domain — one-line definition.** A single sentence defining the domain. Frame as: `**[Domain name]:** [one-sentence definition].`

2. **Three-to-five major sub-areas.** Numbered list (no fewer than 3, no more than 5). Each sub-area: `**[Sub-area name]** — [one-line characterization]. Quadrant: [established-core / live-frontier / dissenting-tradition / adjacent-shares-vocabulary]. Settled-vs-contested: [settled / contested / mixed].` Sub-areas spread across at least three different quadrants — corner-bias detection signal is satisfied.

3. **Foundational distinctions.** Numbered list. Each distinction: `**[Distinction name]** — [term A] vs [term B]. Load-bearing because: [specific consequence — the user could not navigate the domain ignoring this distinction].` Distinctions without load-bearing tests do not appear; decorative-distinction is the named failure mode.

4. **Entry points and first concepts.** Numbered list of concrete starting points. Each: `**[Concept or first-question]** — why start here: [this unlocks understanding of subsequent concepts X, Y, Z].`

5. **Common misconceptions to avoid.** Bulleted list. Each: `**[Misconception]** — correction: [one-line correction]. Likelihood: [high / moderate].` Only predictable-newcomer misconceptions appear; obscure misconceptions a newcomer would not actually form are misconception-blindness padding.

6. **Escalation pointer.** A single closing block: `**For deeper orientation:** [Terrain Mapping] is the heavier T14 sibling. Signals that would trigger escalation: [more time available / sub-areas need open-questions enumeration / entry-point chains need elaboration / contested points need adjudication].`

**Per-section conventions:**

- Use H2 headings for sections 1 through 6.
- The deliverable stays within tier-1 depth: one-line characterizations (not paragraphs), three-to-five sub-areas (not ten), foundational distinctions (not full taxonomies).
- Settled-vs-contested tags apply per sub-area (section 2); when streams disagreed on the tag, contested wins (audit conservatism).
- Avoid "tier-2 phrasing" — the deliverable does not include "open questions in the field include..." or "the methodological debate centers on..." (those signal scope-creep into terrain-mapping territory).
- The escalation pointer is operative — name terrain-mapping as the target and the specific trigger signals.


---

## DEFAULT GEAR

Gear 4

- **Expected Runtime:** ~1min
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource, incubator, reference]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `parent`, `child`, `analogous-to`, `requires`, `extends`
**Deprioritize:** `contradicts`, `supersedes`

*Family: orientation-exploration. See `Reference — Ora YAML Schema.md` §7 for the 13-type taxonomy and `Registry — Relationship Type Registry.md` for type definitions.*
