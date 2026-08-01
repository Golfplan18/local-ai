---
lens_id: fishbone-diagram
name: Fishbone Diagram
lens_type: protocol
applicability: [root-cause-analysis, post-mortem, quality-review, problem-categorization]
foundational: false
source: "Ishikawa, Kaoru (1968). Guide to Quality Control. Asian Productivity Organization."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - quality
  - problem-solving
---

# Fishbone Diagram

## Trigger

Invoked from within root-cause-analysis, post-mortem, and quality-review modes when an analyst is diagnosing a recurring or complex problem and the team is at risk of anchoring on the most visible cause without systematically exploring alternatives. The host mode supplies the problem and its observable symptoms; the lens supplies the categorize-then-drill protocol that enumerates causes within standard categories (6 Ms or service variant), then drills via "why?" to sub-causes, producing a structured map of candidate root causes for evidence-based ranking.

## Core Structure

**Input:** A problem with observable symptoms whose root cause is not yet identified, a team available for structured brainstorming, and the option to test candidate causes against evidence.

**Output:** A categorized map of candidate causes with sub-causes, a ranked short-list of most likely root causes, and a test plan to verify causation.

1. **State the problem clearly and specifically.** Place the problem at the head of the diagram. Vague problem statements produce vague analysis; the problem definition is load-bearing. Input: the symptom or failure under analysis. Output: a one-sentence specific problem statement.

2. **Choose cause categories appropriate to the domain.** For manufacturing, use the 6 Ms (Man, Machine, Method, Material, Measurement, Mother Nature). For services, use People, Process, Policy, Place, Product, Procedure. For software incidents, common adaptations: Infrastructure, Code, Data, Process, External Services, Monitoring. Input: the problem's domain. Output: a category set adapted to the analysis.

3. **Brainstorm causes within each category.** Write every plausible cause on the relevant bone, without filtering. The structure forces exploration of all categories rather than anchoring on the first plausible explanation. Input: the categories. Output: a populated cause list per category.

4. **Drill into sub-causes via repeated "why?".** For each cause, ask "Why?" to identify sub-causes; bones branch further as the analysis deepens. Use the Five Whys discipline within each branch. Input: the cause list. Output: a hierarchical sub-cause map.

5. **Identify the most likely root causes using evidence, data, or voting.** Rank the candidates; produce a short-list (typically 3-5) that warrant testing. Input: the sub-cause map. Output: a ranked candidate-cause list.

6. **Test the top candidates against evidence.** Verify causation; do not just assume correlation. Document which candidates are supported and which are ruled out. Input: the candidate list. Output: a verified-cause set with test evidence.

## Application Steps

1. Receive the problem and team context from the host mode.
2. Run the six-step protocol above.
3. Return the verified-cause set, the test evidence, and the ruled-out candidates to the host mode.
4. Flag any candidate that could not be tested for follow-up investigation outside the current analysis.

## Detection Signals

- A recurring or complex problem requires diagnosis and the obvious explanation has not produced a fix.
- A team is defaulting to blaming the most visible factor without exploring alternatives.
- Multiple potential causes exist and need structured categorization.
- Surface-level fixes keep failing and deeper analysis is needed.
- A post-mortem, retrospective, or quality review is being conducted.

## Critical Questions

- Has the problem been stated specifically enough that causes can be categorized, or is the statement so general that any category seems plausible?
- Have all relevant categories been populated, or has the team focused on the comfortable categories and neglected others?
- Have causes been verified against evidence, or have the most plausible-sounding been adopted without testing?
- Has the diagram been updated when new evidence emerged, or has it been treated as a fixed artifact?

## Common Failure Modes

- **Single-category anchor** — Detection signal: most causes are listed under one category; other categories are sparse or empty. Correction: require at least one cause per category before proceeding.
- **Plausibility-as-evidence** — Detection signal: the team votes on most-likely cause and stops without testing. Correction: require evidence-based verification before declaring a root cause.
- **Stale diagram** — Detection signal: the diagram is built once and not updated when new evidence arrives. Correction: treat the diagram as a living analysis artifact; revise as evidence accumulates.

## Source Citations

- Ishikawa, Kaoru (1968). *Guide to Quality Control*. Asian Productivity Organization.
- Ishikawa, Kaoru (1985). *What Is Total Quality Control? The Japanese Way*. Prentice-Hall.
- Juran, Joseph M. (1988). *Juran's Quality Control Handbook*. McGraw-Hill.
