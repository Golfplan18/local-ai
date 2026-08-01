---
lens_id: mcdm-methods
name: Multi-Criteria Decision Making (MCDM) Methods
lens_type: catalog
applicability: [multi-criteria-decision]
foundational: false
source: "Saaty, Thomas L. (1980). The Analytic Hierarchy Process. McGraw-Hill. Keeney, Ralph L., and Howard Raiffa (1976). Decisions with Multiple Objectives. Wiley. Roy, Bernard (1968). Classement et choix en présence de points de vue multiples (la méthode ELECTRE). RIRO 8:57-75. Hwang, Ching-Lai, and Kwangsun Yoon (1981). Multiple Attribute Decision Making: Methods and Applications. Springer. Brans, Jean-Pierre, and Philippe Vincke (1985). A Preference Ranking Organisation Method (The PROMETHEE Method for MCDM). Management Science 31(6):647-656."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - catalog
  - decision
  - multi-criteria
---

# Multi-Criteria Decision Making (MCDM) Methods

## Trigger

Invoked from within `multi-criteria-decision` (T3) when that mode needs a structured catalog of named methods for ranking or selecting among alternatives across multiple, potentially conflicting criteria. The host mode supplies the alternatives, the criteria, and the decision context; the lens supplies the catalog of methods (with their assumptions, operational descriptions, strengths, and weaknesses) so the analyst can match the method to the decision rather than defaulting to one approach across all situations.

## Core Structure

The catalog enumerates the canonical Multi-Criteria Decision Making (MCDM) methods. Each is a named procedure with its operational description, when to use it, and its key strengths and weaknesses. Methods differ in (a) how preferences are elicited (ratings, pairwise comparisons, thresholds), (b) how criteria are aggregated (compensatory or non-compensatory), and (c) what assumptions they make about preference structure. An analyst typically selects one method per decision, but may run two as cross-checks when stakes are high.

1. **Analytic Hierarchy Process (AHP — Saaty).** Decompose the decision into a hierarchy: goal at the top, criteria below, alternatives at the bottom. Elicit weights via pairwise comparisons on a 1–9 scale ("how much more important is criterion A than criterion B?"). The eigenvector of the pairwise-comparison matrix yields the criterion weights; alternatives are similarly ranked by pairwise comparison within each criterion. Aggregate via weighted sum to produce a final ranking. **When to use:** decisions with hierarchical criteria, expert judgment available for pairwise comparisons, and stakeholder buy-in matters (the pairwise process is comprehensible). **Strengths:** consistency check (the method computes a consistency ratio flagging incoherent comparisons); accommodates qualitative and quantitative criteria; widely understood. **Weaknesses:** rank-reversal phenomenon (adding or removing alternatives can change the ranking of others); pairwise comparisons grow combinatorially with criteria count (n(n-1)/2 comparisons); 1–9 scale is psychologically anchored but lacks ratio-scale justification.

2. **Simple Multi-Attribute Rating Technique (SMART — Keeney-Raiffa, popularized by Edwards).** Define criteria; assign weights (summing to 1) by direct allocation or swing-weighting; rate each alternative on each criterion on a normalized scale (typically 0–100); compute weighted sum. The simplest of the additive-utility methods. **When to use:** decisions with a small number of well-defined criteria, weights and ratings can be elicited directly without pairwise overhead, and transparency to stakeholders matters. **Strengths:** computationally trivial; weights and ratings are directly interpretable; no rank-reversal under standard assumptions. **Weaknesses:** assumes preference independence among criteria (no interaction effects); fully compensatory (a high score on one criterion can offset a low score on another, even when stakeholders would prefer non-compensatory aggregation); weight elicitation is sensitive to framing (swing-weighting partially corrects this).

3. **ELimination Et Choix Traduisant la REalité (ELECTRE — Roy).** Outranking method. For each pair of alternatives (A, B), compute a concordance index (the weighted proportion of criteria on which A is at least as good as B) and a discordance index (whether B is so much better than A on any single criterion that this overrides the concordance). A outranks B when concordance is high and discordance is low. The outranking relation may be incomplete (some pairs may be incomparable) — this is a feature, not a bug. **When to use:** decisions where some criteria are vetos (a single criterion's failure cannot be compensated by other criteria's strengths); preference structure is non-compensatory; incomparability between alternatives is acceptable as an output. **Strengths:** non-compensatory aggregation matches many real preferences (e.g., safety-critical decisions); explicit veto thresholds; partial-order output reflects honest under-determination. **Weaknesses:** more parameters to elicit (concordance and discordance thresholds in addition to weights); partial-order output may not satisfy stakeholders demanding a complete ranking; multiple ELECTRE variants (I, II, III, IV) with different assumptions, requiring the analyst to choose among them.

4. **Weighted-Sum / Linear Additive.** The bare bones of compensatory MCDM. Assign weights to criteria (summing to 1); rate each alternative on each criterion on a common scale; compute the weighted sum per alternative; rank by weighted sum. Distinguished from SMART only by SMART's stricter weight-elicitation discipline; in practice weighted-sum is often used informally without swing-weighting. **When to use:** decisions where criteria are clearly independent and compensatory aggregation is acceptable, and where the simplicity of the method is a virtue (transparency to non-expert stakeholders). **Strengths:** maximum simplicity; no special software; output is a single number per alternative. **Weaknesses:** assumes preference independence (often false); fully compensatory (cannot represent veto criteria); sensitive to scale choice (changing the rating scale can change the ranking if scales are not properly normalized); offers no consistency check on weight elicitation.

5. **Technique for Order of Preference by Similarity to Ideal Solution (TOPSIS — Hwang-Yoon).** Define the ideal solution (best value on each criterion among the alternatives) and the anti-ideal solution (worst value on each criterion). Compute each alternative's Euclidean distance from both. Rank by the relative closeness coefficient: distance from anti-ideal divided by the sum of distances from ideal and anti-ideal. The alternative closest to ideal and farthest from anti-ideal ranks highest. **When to use:** decisions with quantitative criteria where the ideal/anti-ideal frame is meaningful (the ideal need not be achievable; it is a reference point); when geometric intuition about distance from best-possible is appropriate. **Strengths:** computationally simple; geometric interpretation is intuitive; handles many alternatives without combinatorial blowup. **Weaknesses:** requires quantitative criteria (qualitative criteria must be quantified, often arbitrarily); sensitive to the choice of normalization method; the Euclidean distance metric implicitly weighs all criteria equally in geometric space, which interacts with explicit weights in non-obvious ways.

6. **Preference Ranking Organization METHod for Enrichment of Evaluations (PROMETHEE — Brans-Vincke).** Outranking method like ELECTRE but with a different aggregation structure. For each pair of alternatives and each criterion, compute a preference function (six standard forms, including the "usual" all-or-nothing function and "linear" threshold-based functions) yielding a value in [0,1]. Aggregate across criteria using weights to compute a positive flow (how much each alternative is preferred to others) and a negative flow (how much it is dispreferred). PROMETHEE I yields a partial order; PROMETHEE II yields a complete order based on net flow. **When to use:** decisions with a mix of criteria types (some compensatory, some with thresholds), where the analyst wants finer control over how preference is computed than ELECTRE allows; when both partial-order (PROMETHEE I) and complete-order (PROMETHEE II) views are useful. **Strengths:** flexible preference functions accommodate diverse criterion behaviors; both partial and complete orderings available; visualization tools (GAIA plane) are well-developed. **Weaknesses:** more parameters than weighted-sum or SMART (preference function plus thresholds per criterion); choice of preference function can substantially affect ranking; same rank-reversal vulnerability as other outranking methods under some conditions.

## Application Steps

1. Receive the alternatives, criteria, and decision context from the host mode.
2. Match the method to the decision: pairwise-comparison hierarchical structure → Analytic Hierarchy Process; small criterion set with direct weighting → Simple Multi-Attribute Rating Technique; non-compensatory with veto criteria → ELimination Et Choix Traduisant la REalité or Preference Ranking Organization METHod for Enrichment of Evaluations; geometric ideal-anti-ideal framing → Technique for Order of Preference by Similarity to Ideal Solution; minimum-overhead transparent → weighted-sum.
3. Elicit the parameters required by the chosen method (weights, ratings, thresholds, preference functions).
4. Apply the method's aggregation procedure to produce the ranking.
5. Run sensitivity analysis: perturb weights and key parameters to identify how robust the ranking is to elicitation noise.
6. Optionally cross-check by running a second method on the same inputs; if rankings disagree substantially, surface the source of disagreement to the host mode.
7. Return the ranking, the elicited parameters, the sensitivity analysis, and any cross-method disagreement to the host mode.

## Detection Signals

- A decision has multiple alternatives that must be compared on multiple criteria.
- The criteria are not commensurable on a single dimension (cost, time, quality, risk all matter and have no obvious common unit).
- Stakeholders disagree on weights or on which alternative is best, and structured aggregation is needed to surface the disagreement's source.
- A decision is being made by intuition where structured analysis would expose hidden preference inconsistencies.
- Mid-analysis, the analyst notices that an apparently obvious alternative is dominant only because one criterion is being given implicit veto weight; explicit MCDM would surface this.

## Critical Questions

- Has the method been matched to the decision's preference structure? A compensatory method on a non-compensatory decision (veto criteria treated as offsettable) produces rankings stakeholders will reject.
- Are the criteria genuinely independent, or do they interact? Methods assuming independence misbehave under interaction; in such cases, multi-attribute utility theory with explicit interaction terms or fuzzy methods are better-fit.
- Has weight elicitation been done with a discipline (swing-weighting, pairwise comparison) rather than free-form allocation? Free-form weight allocation is highly sensitive to framing and produces low-reliability inputs.
- Has sensitivity analysis been performed? A ranking that is stable under modest weight perturbation is robust; one that flips with small changes is fragile and the fragility must be reported.
- Are the alternatives genuinely commensurable on each criterion? A criterion on which only some alternatives have ratings (others marked "N/A") cannot be aggregated; either restructure the criterion or exclude it.
- Does the chosen method allow the kind of incomparability the decision warrants? When two alternatives are genuinely incomparable (each strictly better on some criteria, each strictly worse on others), a method that forces a complete ranking imposes false precision; outranking methods (ELimination Et Choix Traduisant la REalité, Preference Ranking Organization METHod for Enrichment of Evaluations I) preserve honest incomparability.

## Common Failure Modes

- **Method-by-default** — using weighted-sum or Simple Multi-Attribute Rating Technique by reflex regardless of preference structure. Detection: the analyst did not consider whether veto criteria, criterion interaction, or incomparability matter. Correction: run the method-matching step (Application Step 2) explicitly.
- **Rank-reversal blindness** — using Analytic Hierarchy Process or other rank-reversal-prone methods without checking whether adding or removing alternatives changes existing rankings. Detection: stakeholders are surprised that the ranking changes when an alternative is excluded post-hoc. Correction: test rank stability under alternative inclusion/exclusion before committing to the ranking.
- **Weight elicitation by gut** — assigning weights without a discipline. Detection: weights are round numbers (10%, 20%, 30%, ...) summing conveniently to 100%. Correction: use swing-weighting or Analytic Hierarchy Process pairwise comparisons; document the elicitation procedure.
- **Sensitivity-analysis omission** — reporting a ranking without checking robustness. Detection: the ranking is treated as definitive; no perturbation analysis was done. Correction: perturb weights by ±20% and key ratings by their elicitation uncertainty; report rank stability.
- **Cross-method disagreement suppression** — running two methods, getting different rankings, and reporting only the preferred one. Detection: the second method's output is absent from the report. Correction: report both rankings and the source of disagreement; the disagreement is information, not noise.
- **Compensatory veto** — using a fully compensatory method (weighted-sum, Simple Multi-Attribute Rating Technique, Technique for Order of Preference by Similarity to Ideal Solution) when stakeholders treat at least one criterion as a veto. Detection: stakeholders reject the top-ranked alternative because of its score on a single criterion. Correction: switch to ELimination Et Choix Traduisant la REalité or Preference Ranking Organization METHod for Enrichment of Evaluations with explicit veto thresholds.

## Source Citations

- Saaty, Thomas L. (1980). *The Analytic Hierarchy Process*. McGraw-Hill. Originating text for Analytic Hierarchy Process.
- Saaty, Thomas L. (2008). "Decision making with the analytic hierarchy process." *International Journal of Services Sciences* 1(1):83-98. Compact methodological summary.
- Keeney, Ralph L., and Howard Raiffa (1976). *Decisions with Multiple Objectives: Preferences and Value Tradeoffs*. Wiley. Foundational text for multi-attribute utility theory, on which Simple Multi-Attribute Rating Technique builds.
- Edwards, Ward (1977). "How to use multiattribute utility measurement for social decisionmaking." *IEEE Transactions on Systems, Man, and Cybernetics* 7(5):326-340. Popularization of Simple Multi-Attribute Rating Technique.
- Roy, Bernard (1968). "Classement et choix en présence de points de vue multiples (la méthode ELECTRE)." *Revue d'Informatique et de Recherche Opérationnelle* 8:57-75. Originating ELimination Et Choix Traduisant la REalité paper.
- Roy, Bernard (1991). "The outranking approach and the foundations of ELECTRE methods." *Theory and Decision* 31:49-73. Methodological consolidation.
- Hwang, Ching-Lai, and Kwangsun Yoon (1981). *Multiple Attribute Decision Making: Methods and Applications*. Springer. Originating Technique for Order of Preference by Similarity to Ideal Solution.
- Brans, Jean-Pierre, and Philippe Vincke (1985). "A Preference Ranking Organisation Method (The PROMETHEE Method for MCDM)." *Management Science* 31(6):647-656. Originating Preference Ranking Organization METHod for Enrichment of Evaluations paper.
- Belton, Valerie, and Theodor J. Stewart (2002). *Multiple Criteria Decision Analysis: An Integrated Approach*. Springer. Standard graduate-level textbook surveying the methods and their relations.
- Related: decision trees (for sequential decisions under uncertainty rather than multi-criteria choice among current alternatives); cost-benefit analysis (for monetizable single-dimension reduction).
