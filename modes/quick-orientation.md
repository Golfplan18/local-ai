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
output_contract:
  artifact_type: synthesis
  required_sections:
    - domain_one_line_definition
    - three_to_five_major_sub_areas
    - foundational_distinctions
    - entry_points_and_first_concepts
    - common_misconceptions_to_avoid
    - escalation_pointer_to_terrain_mapping_if_deeper_orientation_needed
  format: structured

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

Consolidate as a structured synthesis with the six required sections. The one-line definition opens. Three-to-five major sub-areas are listed with one-line characterizations each. Foundational distinctions appear as named oppositions or category structures. Entry points are concrete first-concepts to learn or first-questions to ask. Common misconceptions are listed with one-line corrections. The escalation pointer to terrain-mapping closes if the user wants deeper orientation.

## VERIFICATION CRITERIA

Verified means: a one-line domain definition is present; three-to-five major sub-areas are listed and spread across the domain rather than corner-concentrated; foundational distinctions are load-bearing (the user could not navigate without them); entry points are concrete; common misconceptions are flagged; settled vs. contested is distinguished; the output stays within tier-1 depth budget; the four critical questions are addressable from the output.
