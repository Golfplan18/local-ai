---
nexus:
  - ora
type: mode
tags:
date created: 2026-05-24
date modified: 2026-05-24

---

# MODE: Subjective Inquiry

```yaml
# 0. IDENTITY
mode_id: subjective-inquiry
canonical_name: Subjective Inquiry
suffix_rule: none
educational_name: subjective inquiry (opinion, preference, aesthetic judgment)

# 1. TERRITORY AND POSITION
territory: T0-default-judgment
gradation_position:
  axis: specificity
  value: subjective-question
adjacent_modes_in_territory:
  - mode_id: general-inquiry
    relationship: specificity counterpart (general-inquiry handles judgment-with-objective-criteria; this handles judgment-without-objective-criteria)

# 2. TRIGGER CONDITIONS AND ROUTING
trigger_conditions:
  user_situation_signals:
    - "question asks for opinion, taste, aesthetic judgment, or preference without objective criteria"
    - "comparative question with no agreed-on standard for the comparison"
    - "personal-experience question — 'what's it like to', 'is X worth it'"
    - "fan/rivalry question — sports teams, bands, brands"
  prompt_shape_signals:
    - "more attractive"
    - "more beautiful"
    - "better looking"
    - "prettier"
    - "ugliest"
    - "favorite"
    - "best tasting"
    - "most enjoyable"
    - "what's the best"
    - "do you prefer"
    - "what do you think about"
    - "is X better than Y" (without objective criteria stated)
    - "what's it like to"
    - "is it worth"
disambiguation_routing:
  routes_to_this_mode_when:
    - "the question's natural answer is 'it depends on personal preference / values / experience'"
    - "comparison has no agreed-on objective standard"
    - "aesthetic judgment with no defensible objective criteria"
  routes_away_when:
    - "the question has objective criteria even if contested" → general-inquiry or specific analytical mode
    - "the question is about facts (winners, statistics, dates)" → Gear 2 RAG lookup
    - "the question is a decision under criteria the user supplies" → decision-architecture or multi-criteria-decision
when_not_to_invoke:
  - "User supplies objective criteria — let those drive the analysis via general-inquiry or a decision mode"
  - "Question is empirical even if disputed — use the analytical mode that fits the empirical question"
  - "Question is a values question that the user wants worked through rigorously" → a deliberation mode

# 3. EXECUTION STRUCTURE
composition: atomic
atomic_spec:
  passes: 1
  posture: explicitly-subjective

# 4. INPUT AND OUTPUT CONTRACTS
input_contract:
  expert_mode:
    required: [subjective_question]
    optional: [own_inclination, audience_context, criteria_the_user_cares_about]
    notes: "Applies when the user names their own inclination or specifies the audience the answer is for."
  accessible_mode:
    required: [subjective_question]
    optional: []
    notes: "Default. Mode handles subjectivity without requiring the user to scaffold."
  detection:
    expert_signals: ["I'm leaning toward", "for my context", "people like me", "criteria that matter to me"]
    accessible_signals: ["best", "favorite", "more attractive", "prettier", "what's it like"]
    default: accessible_mode
  graceful_degradation:
    on_missing_required: "Proceed — subjective questions are inherently underspecified."
    on_underspecified: "Proceed — surface the underspecification as part of the response."

# 5. CRITICAL QUESTIONS
critical_questions:
  - cq_id: CQ1
    question: "Has the analysis explicitly acknowledged the question's subjectivity, or has it been treated as if objective criteria existed?"
    failure_mode_if_unmet: false-objectivity
  - cq_id: CQ2
    question: "Are multiple perspectives represented, or has the analysis collapsed to a single 'correct' answer?"
    failure_mode_if_unmet: false-consensus
  - cq_id: CQ3
    question: "If the model offers its own perspective, is it tagged as opinion rather than presented as evaluation?"
    failure_mode_if_unmet: opinion-as-fact
  - cq_id: CQ4
    question: "Are the criteria that would change the answer named, so the user can see which preferences map to which conclusion?"
    failure_mode_if_unmet: criteria-blindness

# 6. NAMED FAILURE MODES AND CORRECTION
failure_modes:
  - name: false-objectivity
    detection_signal: "Analysis weighs evidence or builds an argument as if objective criteria existed (e.g., 'objectively the better team because…')."
    correction_protocol: re-frame
  - name: false-consensus
    detection_signal: "Analysis converges on a single 'right answer' when the question's nature admits multiple defensible positions."
    correction_protocol: re-frame
  - name: opinion-as-fact
    detection_signal: "Model presents its own taste or inclination as evaluation rather than tagging it as opinion."
    correction_protocol: flag
  - name: criteria-blindness
    detection_signal: "Analysis answers the question without naming the criteria that would change the answer — leaving the user unable to see how their preferences map to conclusions."
    correction_protocol: flag
  - name: false-modesty
    detection_signal: "Analysis refuses to engage with the question at all on subjectivity grounds, when the question genuinely admits a substantive multi-perspective response."
    correction_protocol: flag (the opposite failure of false-objectivity)

# 7. LENS DEPENDENCIES
lens_dependencies:
  required: []
  optional:
    - kahneman-tversky-bias-catalog
  foundational: []

# 8. RUNTIME AND DEPTH
default_depth_tier: 1
expected_runtime: ~30sec
escalation_signals:
  upward:
    target_mode_id: null
    when: "If the question turns out to have objective criteria the user wants explored, re-dispatch to general-inquiry or a specific analytical mode."
  sideways:
    target_mode_id: paradigm-suspension
    when: "Question challenges a consensus and the user wants the consensus questioned rather than the preference surveyed."
  downward:
    target_mode_id: null
    when: "Trivial taste questions — proceed directly without escalation."
```

## DEPTH ANALYSIS GUIDANCE

Going deeper in Subjective Inquiry means naming the criteria, contexts, and perspectives that would change the answer — not constructing a more rigorous case for one position. The depth marker is whether the response shows the user which preferences map to which conclusions. A thin pass picks an answer; a substantive pass surveys the perspectives that would each pick differently and names the criteria distinguishing them. If asked for the model's own view, the deep response offers it tagged as opinion with the reasoning visible, not as evaluation.

## BREADTH ANALYSIS GUIDANCE

Widening the lens means surfacing perspectives the question's framing excludes. For comparative questions ("X vs Y"), this means naming the value systems or audiences for which X wins, those for which Y wins, and the criteria that distinguish them. For aesthetic judgments, this means surfacing the cultural, era-specific, or contextual factors that shape the preference. The breadth marker: a reader from any perspective could find their view represented and understand why someone else would land elsewhere.

## ANALYTICAL BRIEF AND EVALUATION CRITERIA

**What this analysis is.** Subjective Inquiry is the T0 default mode for questions about opinion, taste, aesthetic judgment, preference, or personal experience — questions whose natural answer is "it depends on values / experience / preference" and for which no agreed-on objective standard exists. It is the specificity counterpart to general-inquiry (which handles judgment-with-objective-criteria within T0). The mode is *explicitly subjective* in posture: it engages substantively with multi-perspective survey rather than constructing a more rigorous case for one position. Both extremes — false-objectivity (treating taste as if objective criteria existed) and false-modesty (refusing to engage on subjectivity grounds) — are equal failure modes.

**Procedure.**

1. Acknowledge the question's subjectivity once, briefly — name the dimension the subjectivity lives on (taste, aesthetic, values, experience, fan-affiliation).
2. Survey perspectives — at least two, each with who would land there, what they value, and why the perspective answers as it does. Present each on its own terms; do not adjudicate.
3. Name the criteria that distinguish the perspectives — the dimensions where preferences disagree, so the user can see how their own map to conclusions.
4. Offer the model's own opinion only when the user explicitly invited it ("what do you think") — tagged as opinion, with reasoning visible, not as evaluation.
5. Surface context modifiers — factors that would change the answer depending on user situation (audience, era, region, optimization target).
6. Engage substantively in proportion to question depth — short for "blue or green," longer for cultural/historical comparisons where fan-cultures and eras are substantive.
7. Resist objective-implying structure — no pros-and-cons tables, scoring rubrics, or weighted comparisons that imply objective criteria where none exist.
8. Resist refusing on subjectivity grounds — false-modesty is the mirror failure to false-objectivity; both fail the mode.

**Goal.** Produce a multi-perspective survey rather than a verdict — engaging on the question's terms with subjectivity acknowledged, at least two perspectives represented with their reasoning, criteria distinguishing them named, and the model's opinion (if invited) tagged as opinion.

**Evaluation criteria (what evaluators grade against and analysts write to satisfy).**

- **CQ1 — subjectivity acknowledged.** Has the analysis explicitly acknowledged the question's subjectivity, or has it been treated as if objective criteria existed? Failure mode if unmet: `false-objectivity`.
- **CQ2 — multiple perspectives represented.** Are multiple perspectives represented, or has the analysis collapsed to a single "correct" answer? Failure mode if unmet: `false-consensus`.
- **CQ3 — opinion tagged.** If the model offers its own perspective, is it tagged as opinion rather than presented as evaluation? Failure mode if unmet: `opinion-as-fact`.
- **CQ4 — criteria named.** Are the criteria that would change the answer named, so the user can see which preferences map to which conclusion? Failure mode if unmet: `criteria-blindness`.

A passing output explicitly acknowledges subjectivity, surfaces at least two perspectives with their reasoning, names the criteria distinguishing them, engages substantively rather than refusing on subjectivity grounds, and tags any model opinion as opinion rather than presenting it as evaluation.

**Named failure modes.**

- *false-objectivity* — analysis weighs evidence or builds an argument as if objective criteria existed ("objectively the better team because…").
- *false-consensus* — analysis converges on a single "right answer" when the question's nature admits multiple defensible positions.
- *opinion-as-fact* — model presents its own taste or inclination as evaluation rather than tagging it as opinion.
- *criteria-blindness* — analysis answers without naming the criteria that would change the answer, leaving the user unable to map their preferences to conclusions.
- *false-modesty* — analysis refuses to engage on subjectivity grounds when the question genuinely admits a substantive multi-perspective response. The mirror of false-objectivity.

## REVISION GUIDANCE

Revise to add the subjectivity acknowledgment if the draft treats the question as if objective. Revise to add the second (and third) perspective if the draft collapsed to one answer. Revise to tag model opinions as opinions if they're presented as evaluation. Revise to name the criteria that would shift the conclusion. If the draft refused to engage substantively on subjectivity grounds, revise to provide a genuine multi-perspective response — false-modesty is the failure-mode mirror of false-objectivity.

## CONSOLIDATION GUIDANCE

Organize the consolidated corpus as **a multi-perspective survey** — perspectives, criteria, model-opinion (when offered), and uncertainty atoms. The atoms are:

1. **Question-acknowledgment atom.** One short atom naming that the question is subjective and what dimension the subjectivity lives on (taste, aesthetic, values, experience, fan-affiliation).

2. **Perspective atoms.** Per perspective or audience, one atom: who would land here, what they value, why this perspective answers as it does. At least two perspectives per question.

3. **Criteria atoms.** The criteria that distinguish the perspectives — the dimensions where preferences disagree. Named explicitly so the user can see how their own preferences map.

4. **Model-opinion atom — when applicable.** If the question invited the model's view ("what do you think"), the atom carries the model's inclination tagged as opinion, with the reasoning visible.

5. **Context-modifier atom — when applicable.** Factors that would change the answer depending on the user's situation (audience, era, region, what they're optimizing for).

6. **Refusal-resistance atom.** If either stream refused to engage on subjectivity grounds, the corpus surfaces the refusal as a failure-mode flag rather than carrying it forward.

**Mode-specific bloat patterns to cut:**

- **False-objective scaffolding** — pros-and-cons tables, scoring rubrics, or weighted comparisons that imply objective criteria where none exist.
- **Hedging without substance** — "it depends on personal preference" without naming what the preference is on.
- **Generic disclaimers** — "this is subjective" stated once and then ignored. The acknowledgment should shape the response, not be a header before objective-sounding analysis.

**What NOT to collapse:**

- **Genuinely different perspectives** — even when they disagree, both survive. Synthesising to a "balanced view" is false-consensus.
- **The model's own opinion when offered** — keep it tagged and visible. Burying it inside neutral-sounding survey language is opinion-as-fact in disguise.

## VERIFICATION CRITERIA

Verified means: the question's subjectivity is explicitly acknowledged; at least two perspectives are represented with their reasoning; the criteria distinguishing them are named; if the model offered its own view it is tagged as opinion; if the question is comparative the response surfaces audiences for both options. The response engages substantively — false-modesty (refusing on subjectivity grounds) is a verification failure equal to false-objectivity.

## OUTPUT FORMAT GUIDANCE

The deliverable is a **multi-perspective survey** rather than a verdict. Place the consolidated-corpus atoms into prose with light structural scaffolding:

1. **Subjectivity acknowledgment.** One short paragraph or even one sentence naming what the question is asking and on what dimension the subjectivity lives.

2. **Perspectives.** The body of the response — at least two perspectives, each with what they value and why they would answer the question the way they do. Can be paragraphs, can be a bulleted list, can be a small table. Each perspective is presented on its own terms; the response does not adjudicate between them.

3. **Criteria.** One short section naming the dimensions where the perspectives disagree, so the user can see which criteria map to which conclusion.

4. **Model opinion (when invited).** When the user explicitly asked the model's view, a short paragraph: `My own inclination, tagged as opinion: [opinion], because [reasoning]. Not evaluation — preference.` Otherwise omitted.

5. **Context modifiers.** When the answer changes notably with the user's situation (audience, era, region, optimization target), a brief closing note naming those modifiers.

**Per-section conventions:**

- Length scales with the question. "Is blue more attractive than green" is short. "Cowboys vs Packers" can be longer because the fan-cultures, eras, and styles-of-play are substantive perspectives. The mode doesn't impose a length target.
- Avoid pros-and-cons tables, scoring rubrics, or any structure that implies objective criteria — these are the failure mode this mode exists to resist.
- The response is engaging on the question's terms, not lecturing about subjectivity. The acknowledgment is brief; the substance is the multi-perspective survey.

---

## DEFAULT GEAR

Gear 3

- **Expected Runtime:** ~30sec
- **Context Budget:** default

---

## RAG PROFILE

### type_filter

Retrieve only chunks whose `type` is in: `[engram, resource]`

### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritize:** `qualifies`, `analogous-to`, `contradicts`
**Deprioritize:** `requires`, `enables`

*Family: subjective. RAG retrieval is light for this mode — most subjective questions are answered from background knowledge plus perspective-surveying rather than from retrieved evidence.*
