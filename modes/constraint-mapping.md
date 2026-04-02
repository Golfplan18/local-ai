---
title: constraint-mapping
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Constraint Mapping

## TRIGGER CONDITIONS

Positive triggers: Multiple viable options exist, "which should I choose," tradeoff analysis, C&S output showing consequences pointing in opposite directions at different time horizons, KVI output revealing value conflicts without a clear resolution. The user frames the question as a choice between alternatives rather than a search for the right answer.

Negative triggers: IF the user is questioning the framework within which the alternatives exist, THEN route to Paradigm Suspension. IF the user wants to trace who benefits from each alternative, THEN route to Cui Bono. IF the question is about which explanation best fits evidence rather than which option to choose, THEN route to Competing Hypotheses.

## EPISTEMOLOGICAL POSTURE

Operate within the accepted framework rather than questioning it. All candidate alternatives are treated as potentially viable — the task is not to determine which is "right" but to map the conditions under which each succeeds and fails. Value judgments embedded in each alternative are surfaced, not resolved — resolution is the user's prerogative.

## DEFAULT GEAR

Gear 3. Sequential adversarial review is sufficient. The Breadth model maps conditions for each alternative; the Depth model stress-tests whether those conditions are accurately characterized and whether any alternatives have been omitted.

## RAG PROFILE

Retrieve case studies, comparative analyses, decision frameworks, and domain-specific tradeoff literature. IF the alternatives involve known historical precedents, retrieve those precedents. Favor sources that examine tradeoffs rather than advocate for positions.

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. For each alternative, identify the specific conditions under which it succeeds — what must be true for this option to work.
2. For each alternative, identify the specific conditions under which it fails — what would make this option unviable.
3. Quantify gains and forfeitures where possible. State magnitudes, not just directions.

Black Hat directives:
1. Test each alternative's success conditions for realism — are the required conditions plausible, or do they assume best-case scenarios?
2. Identify hidden dependencies — conditions that are assumed to be met but are actually uncertain.
3. Identify at minimum one alternative the Breadth model may have omitted and map its constraint profile.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Map all candidate alternatives, including any the user has not named. At minimum three alternatives.
2. For each alternative, generate the conditions under which it would be the clearly best choice. What world would have to be true?
3. Identify hybrid options or sequencing strategies — can alternatives be combined or ordered to capture benefits while limiting forfeitures?

Yellow Hat directives:
1. For each alternative, identify what is uniquely gained — what this option provides that no other option does.
2. Identify what is forfeited by each alternative — what the user gives up by choosing this path.
3. Surface any "no-lose" elements — conditions or actions that are valuable regardless of which alternative is chosen.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Alternative Coverage.** 5=all viable alternatives mapped including at least one the user did not name. 3=user-named alternatives fully mapped but no additional alternatives surfaced. 1=alternatives missing or incompletely characterized.
6. **Condition Specificity.** 5=success and failure conditions stated as specific, testable propositions. 3=conditions identified but stated vaguely. 1=conditions missing for one or more alternatives.
7. **Gain/Forfeit Balance.** 5=gains and forfeitures identified for every alternative with specificity about what is unique to each. 3=gains and forfeitures present but not differentiated across alternatives. 1=gains or forfeitures missing.

## CONTENT CONTRACT

The output is complete when it contains, for each alternative:

1. **Conditions for success** — specific, testable conditions under which this alternative works.
2. **Conditions for failure** — specific conditions that would make this alternative unviable.
3. **Gains** — what is achieved by choosing this alternative, with attention to what is unique to it.
4. **Forfeitures** — what is given up by choosing this alternative.

Universal elements:
5. **Cross-alternative comparison** — where alternatives overlap, where they diverge, and what the critical differentiating factors are.
6. **No-lose elements** — actions or conditions that serve the user regardless of which alternative is chosen.

## KNOWN FAILURE MODES

**The False Dichotomy Trap:** Mapping only two alternatives when viable third or fourth options exist. Correction: Generate at minimum three alternatives. IF the user has named only two, generate at least one more.

**The Advocacy Trap:** Unconsciously favoring one alternative through asymmetric analysis — mapping success conditions in detail for the preferred option while mapping only failure conditions for the disfavored one. Correction: Apply identical analytical depth to every alternative.

**The Abstraction Trap:** Stating conditions at a level of abstraction that prevents the user from evaluating whether they hold. "Requires a favorable economic environment" is not specific enough. Correction: State conditions as testable propositions with observable indicators.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis moves toward recommending one alternative, THEN pause and verify: has the user asked for a recommendation, or is the model resolving a tension the user needs to see? Constraint Mapping maps the terrain of choice; it does not make the choice.

**Symmetry guard rail.** Apply identical analytical rigor to every alternative. IF one alternative has more detailed analysis than others, equalize before presenting.

**Pre-mortem guard rail.** For each alternative, imagine it has been chosen and has failed. What went wrong? This surfaces failure conditions that pure success-condition analysis misses.

## TOOLS

Tier 1: C&S (consequence analysis across time horizons for each alternative), PMI (plus/minus/interesting for each alternative), KVI (surface the values each alternative serves), FIP (after mapping, identify which differentiating factors matter most), OPV (if alternatives affect multiple stakeholders).

Tier 2: Module 7 — Evaluation (comparison and assessment questions).

## TRANSITION SIGNALS

- IF the user selects an alternative and wants to execute it → propose **Project Mode**.
- IF the alternatives reveal that the framework itself needs questioning → propose **Paradigm Suspension**.
- IF the choice requires formal probability assessment or option value analysis → propose **Decision Under Uncertainty**.
- IF the user wants to understand how concepts or forces connect before choosing → propose **Relationship Mapping** or **Systems Dynamics**.
- IF the alternatives involve institutional interests or distributional consequences → propose **Cui Bono** for that analysis layer.
