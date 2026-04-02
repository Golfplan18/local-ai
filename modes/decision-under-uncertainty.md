---
title: decision-under-uncertainty
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Decision Under Uncertainty

## TRIGGER CONDITIONS

Positive triggers: A choice must be made between alternatives with uncertain outcomes. "Should we act now or wait," probabilities matter but are not precisely known, the cost of being wrong is high, flexibility or optionality has value, the user faces a risk/uncertainty distinction. The decision has temporal dynamics — the cost of delay versus the benefit of learning. Constraint Mapping has identified alternatives but the user needs to incorporate probability, time-value, or option value to choose.

Negative triggers: IF the user wants to map tradeoffs without incorporating probability or time-value, THEN route to Constraint Mapping. IF the user wants to understand which explanation fits evidence best, THEN route to Competing Hypotheses. IF the user wants to explore multiple possible futures rather than make a specific decision, THEN route to Scenario Planning.

## EPISTEMOLOGICAL POSTURE

Evidence is input to probability estimation, and uncertainty has formal structure. Three types of uncertainty are distinguished: risk (known probabilities), uncertainty (unknown probabilities), and deep uncertainty (unknown variables). Decisions have temporal dynamics: the cost of delay versus the benefit of learning. The option to wait and learn has value that must be weighed against the cost of delay. Non-quantifiable factors must be acknowledged alongside formal calculations — utility functions do not capture everything that matters.

## DEFAULT GEAR

Gear 3. Sequential review is sufficient. The Depth model structures the decision and assesses probabilities; the Breadth model challenges whether the framing captures all relevant alternatives, whether probability estimates are well-grounded, and whether non-quantifiable factors have been adequately considered.

## RAG PROFILE

Retrieve decision theory frameworks, domain-specific risk analyses, base rate data for probability estimation, and case studies of similar decisions. IF the decision involves financial or investment choices, retrieve real options methodology. IF the decision involves policy, retrieve public decision-making frameworks. Deprioritize advocacy literature — sources should inform probability estimates, not argue for outcomes.

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. Frame the decision: what are the alternatives, what outcomes are possible for each, and what can be deferred?
2. Classify the uncertainty type for each critical variable: risk (assignable probability), uncertainty (probability estimable within a range), or deep uncertainty (cannot assign meaningful probabilities).
3. For each alternative under each plausible state, assess consequences. Quantify where possible; characterize qualitatively where quantification would be misleading.

Black Hat directives:
1. Challenge probability estimates. Are they grounded in base rates, or are they anchored to initial assumptions? IF no base rate exists, state this explicitly — an estimate without a base rate is a guess.
2. Assess downside exposure for each alternative. What is the worst plausible outcome, and how bad is it?
3. Evaluate whether the decision framing artificially constrains the alternatives. Can the user create new alternatives, sequence decisions, or buy information before committing?

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Identify alternatives the framing may have excluded. Can alternatives be sequenced rather than chosen exclusively? Can options be created that preserve flexibility?
2. Conduct value-of-information analysis: what additional information would most reduce uncertainty? What would it cost to obtain? Is the expected value of that information greater than the cost of delay?
3. Identify hedging strategies — actions that reduce downside exposure without forfeiting upside potential.

Yellow Hat directives:
1. Identify robust alternatives — choices that perform acceptably across multiple plausible states rather than optimally in one.
2. Assess what the user gains from each decision framework applied — does expected value analysis, minimax regret, or robustness analysis best serve this particular decision?
3. Identify reversibility — which alternatives can be undone or adjusted if conditions change, and what is the cost of reversal?

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Uncertainty Classification.** 5=each critical variable classified as risk, uncertainty, or deep uncertainty with reasoning. 3=classification attempted but one variable miscategorized. 1=all variables treated as either risk or complete ignorance without distinction.
6. **Decision Framing Quality.** 5=alternatives include sequencing options, information-gathering options, and hedging strategies alongside direct choices. 3=standard alternatives identified but no creative framing. 1=decision presented as binary when alternatives exist.
7. **Value-of-Information Assessment.** 5=specific information identified that would most reduce uncertainty, with cost of obtaining it versus cost of delay assessed. 3=information needs identified but cost-benefit not assessed. 1=no value-of-information analysis performed.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Decision framing** — what is the decision, what are the alternatives (including defer, sequence, and hedge options), what can be deferred.
2. **Uncertainty identification** — what is known vs. unknown, uncertainty type for each critical variable, whether probabilities can be meaningfully assigned.
3. **Consequence analysis** — for each alternative under each plausible state, the outcomes (quantified where appropriate, characterized qualitatively otherwise).
4. **Value-of-information analysis** — what information would most reduce uncertainty, what it is worth, whether to decide now or learn more first.
5. **Recommendation** — with explicit risk characterization, stated confidence level, and conditions under which the recommendation should be revisited.

## KNOWN FAILURE MODES

**The False Precision Trap:** Assigning specific probabilities ("17% chance") when genuine uncertainty makes such precision misleading. Correction: Use probability ranges rather than point estimates for uncertain variables. State the basis for every estimate.

**The Analysis Paralysis Trap:** Real options theory can rationalize indefinite delay because the option to wait always has positive value. Correction: Assess the cost of delay explicitly. IF the cost of delay exceeds the value of information from waiting, decide now.

**The Quantification Trap:** Reducing all factors to utility functions when some factors resist meaningful quantification — ethics, relationships, morale, identity. Correction: Acknowledge non-quantifiable factors explicitly. Present them alongside quantitative analysis, not subordinated to it.

**The Anchoring Trap:** Initial probability estimates anchor subsequent analysis regardless of evidence. Correction: Generate estimates independently before comparing them. IF using Gear 4, independent estimation is architectural.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN a recommendation is presented, THEN verify: does the recommendation account for what the analysis does not know? A confident recommendation under deep uncertainty requires explicit justification.

**Humility guard rail.** State what the analysis assumes, what it does not know, and what would change the recommendation. Every recommendation is conditional — state the conditions.

**Non-quantifiable factors guard rail.** Before finalizing the analysis, ask: are there factors that matter but resist quantification? IF so, present them alongside the quantitative framework, not as footnotes.

## TOOLS

Tier 1: C&S (consequences across time horizons for each alternative), PMI (evaluate each alternative's plus/minus/interesting), FIP (identify which uncertainties matter most for the decision), CAF (identify all factors including non-quantifiable ones).

Tier 2: Module 7 — Evaluation. Engineering and Technical Analysis Module for technical risk assessment.

## TRANSITION SIGNALS

- IF the decision requires exploring multiple possible futures → propose **Scenario Planning** to develop the states before analyzing the decision.
- IF the decision involves institutional interests shaping the alternatives → propose **Cui Bono**.
- IF the user selects an alternative and wants to execute → propose **Project Mode**.
- IF the alternatives rest on unexamined assumptions → propose **Paradigm Suspension**.
- IF the user wants the strongest case for an alternative before deciding → propose **Steelman Construction**.
- IF the decision involves a system with feedback loops where interventions produce counterintuitive effects → propose **Systems Dynamics**.
