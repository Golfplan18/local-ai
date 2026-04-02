---
title: competing-hypotheses
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Competing Hypotheses

## TRIGGER CONDITIONS

Positive triggers: Multiple explanations exist for the same evidence, "which explanation fits best," the analyst has a favored hypothesis that needs stress-testing, evidence is ambiguous or contradictory, the situation involves potential deception or information manipulation, the question is "what is actually happening" rather than "what should we do."

Negative triggers: IF the user wants to choose between action alternatives rather than between explanations, THEN route to Constraint Mapping. IF the user wants to question the foundational framework rather than test hypotheses within it, THEN route to Paradigm Suspension. IF the user wants to trace institutional interests behind competing claims, THEN route to Cui Bono.

## EPISTEMOLOGICAL POSTURE

Focus on disconfirmation rather than confirmation. The most likely hypothesis is the one with the least evidence against it, not the most evidence for it. Evidence is evaluated by diagnosticity — how well it distinguishes between hypotheses. Evidence consistent with multiple hypotheses has low diagnosticity. Evidence that rules out specific hypotheses has high diagnosticity. The analyst works across the evidence-hypothesis matrix (evaluating one piece of evidence against all hypotheses) rather than down it (collecting evidence for a favored hypothesis). This directly counters confirmation bias.

## DEFAULT GEAR

Gear 4. Independent evidence assessment is the minimum for reliable output. The methodology's purpose is avoiding confirmation bias. IF one model sees the other's hypothesis ranking before evaluating evidence, the ranking anchors and the methodology fails.

## RAG PROFILE

Retrieve evidence sources — primary data, observational reports, direct testimony, and empirical findings relevant to the competing explanations. Retrieve sources that support each hypothesis, including hypotheses the user disfavors. Deprioritize editorial opinion, interpretive analysis, and secondary commentary. IF the situation involves adversarial actors, retrieve intelligence analysis methodology and counter-deception frameworks.

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. List all plausible hypotheses. Include at minimum one hypothesis the user has not proposed.
2. List all significant evidence and arguments, regardless of which hypothesis they support.
3. For each piece of evidence, assess its consistency with each hypothesis: consistent, inconsistent, or not applicable.

Black Hat directives:
1. Assess the diagnosticity of each piece of evidence. Evidence consistent with all hypotheses provides no diagnostic value — note it explicitly.
2. Identify the most diagnostic evidence — pieces that sharply distinguish between hypotheses.
3. Challenge the Breadth model's hypothesis list. Is there a hypothesis not listed that explains the evidence? Is there a listed hypothesis that should be eliminated?
4. Conduct sensitivity analysis: what if the most diagnostic evidence is wrong, deceptive, or missing?

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Generate the widest plausible set of hypotheses. Include unconventional explanations. At minimum five hypotheses for non-trivial problems.
2. For each hypothesis, identify what evidence would disconfirm it — disconfirmation is more diagnostic than confirmation.
3. Identify what evidence is missing that would be most useful — what single piece of information would most change the analysis?

Yellow Hat directives:
1. For each surviving hypothesis, identify its strongest explanatory advantage — what it explains most naturally.
2. Assess what the user gains even if no single hypothesis is confirmed — what has been ruled out, what evidence gaps have been identified.
3. Identify leading indicators — future evidence that would strengthen or weaken each surviving hypothesis.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Hypothesis Coverage.** 5=all plausible hypotheses listed including at minimum one beyond the user's initial set. 3=user-proposed hypotheses covered but no additional hypotheses generated. 1=plausible hypotheses missing.
6. **Diagnosticity Assessment.** 5=every piece of evidence assessed for diagnostic value across all hypotheses, high-diagnosticity evidence explicitly identified. 3=consistency assessment performed but diagnosticity not evaluated. 1=evidence evaluated only for favored hypothesis.
7. **Disconfirmation Rigor.** 5=conclusions based on elimination of least consistent hypotheses with sensitivity analysis. 3=conclusions drawn but sensitivity analysis absent. 1=conclusions based on confirmation rather than elimination.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Hypothesis list** — all plausible hypotheses, including at minimum one beyond the user's initial set.
2. **Evidence inventory** — all significant evidence and arguments.
3. **Consistency matrix** — each piece of evidence rated against each hypothesis.
4. **Diagnosticity assessment** — which evidence actually distinguishes between hypotheses.
5. **Tentative conclusions** — based on elimination, not confirmation.
6. **Sensitivity analysis** — how conclusions change if critical evidence is wrong or missing.
7. **Monitoring priorities** — what future evidence to watch for.

## KNOWN FAILURE MODES

**The Missing Hypothesis Trap:** The correct hypothesis is not in the list, producing a "winner" that is merely the least wrong. Correction: Always include hypotheses beyond the user's initial set. After the matrix, ask: is there an unlisted explanation consistent with the most diagnostic evidence?

**The False Rigor Trap:** The matrix format creates a false sense of precision when consistency ratings are subjective. Correction: State reasoning behind each rating. Acknowledge uncertainty explicitly.

**The Static Snapshot Trap:** Treating the analysis as final in an evolving situation. Correction: Identify monitoring priorities and conditions for re-analysis.

**The Deception Blindness Trap:** In adversarial contexts, evidence may be planted. Correction: IF adversarial actors are involved, evaluate whether evidence could be manufactured.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis endorses a single hypothesis, THEN verify the endorsement is based on elimination of alternatives, not confirmation of a favorite.

**Disconfirmation-first guard rail.** Work across the matrix before working down it.

**Completeness guard rail.** Before conclusions: is there an unconsidered hypothesis? Is there unincluded evidence?

## TOOLS

Tier 1: CAF (identify all evidence and arguments), FIP (prioritize diagnostic evidence), OPV (if hypotheses involve actors, map perspectives), Challenge (test whether each hypothesis explains or merely accommodates the evidence).

Tier 2: Load based on domain signals. Political and Social Analysis Module for institutional analysis.

## TRANSITION SIGNALS

- IF hypotheses involve institutional interests → propose **Cui Bono**.
- IF a hypothesis rests on unexamined paradigmatic assumptions → propose **Paradigm Suspension**.
- IF the user needs to decide actions given surviving hypotheses → propose **Decision Under Uncertainty** or **Constraint Mapping**.
- IF the user begins defining a deliverable → propose **Project Mode**.
- IF hypotheses involve complex causal chains → propose **Root Cause Analysis**.
