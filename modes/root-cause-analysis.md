---
title: root-cause-analysis
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Root Cause Analysis

## TRIGGER CONDITIONS

Positive triggers: Something has gone wrong and the cause is unclear. A problem keeps recurring despite attempted fixes. The presented problem feels like a symptom rather than the real issue. "Why does this keep happening," "we've tried X but it didn't work," "what's the real problem here." Diagnostic investigation is needed before solution design.

Negative triggers: IF the user wants to map a system's feedback structure rather than trace a specific failure, THEN route to Systems Dynamics. IF the user wants to choose between solutions rather than diagnose the problem, THEN route to Constraint Mapping. IF the user wants to explore unfamiliar territory rather than diagnose a failure in familiar territory, THEN route to Terrain Mapping.

## EPISTEMOLOGICAL POSTURE

The surface problem is a symptom, not the disease. First-order explanations are inherently suspect. Evidence is followed backward through causal chains. Expert opinion about "the problem" is questioned — direct observation is favored over executive assumptions. Each potential cause is treated as a hypothesis to be tested. The method investigates the process, not the people — "human error" is never accepted as a root cause. Behind every human error is a process failure that permitted or incentivized it.

## DEFAULT GEAR

Gear 3. Root cause investigation is inherently sequential — each level of cause reveals the next. The Depth model traces the causal chain; the Breadth model challenges whether each causal link is genuine and whether alternative chains exist. Independence is less critical than rigorous chain-testing.

## RAG PROFILE

Retrieve domain-specific failure analysis, incident reports, process documentation, and prior analyses of similar failures. Retrieve root cause analysis methodology (5 Whys, Ishikawa/fishbone, fault tree analysis). IF the domain has known common failure patterns, retrieve those as candidate causal templates. Deprioritize solution-oriented sources until the diagnosis is complete.

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. State the presented problem — the observable symptom or failure. Document it precisely: what happened, when, where, and what the observable evidence is.
2. For each proposed cause, ask: what caused this cause? Continue for at minimum three levels of depth. At each level, distinguish the causal claim from the evidence supporting it.
3. Distinguish root causes from contributing factors. A root cause is one whose removal would prevent recurrence. A contributing factor increases probability but does not independently cause the failure.

Black Hat directives:
1. For each causal link in the chain, assess: is this causation or correlation? What evidence distinguishes them?
2. Challenge any point where the chain terminates at "human error," "bad judgment," or "insufficient effort." Ask: what process permitted this error? What system incentivized this judgment?
3. Assess whether the chain has stopped too early — whether the identified "root cause" is actually an intermediate cause with deeper causes beneath it.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Generate alternative causal chains for the same symptom. The first chain identified is not necessarily the correct one. At minimum two alternative chains.
2. Identify contributing factors that interact with the primary chain — conditions that are not root causes alone but amplify the root cause's effect.
3. Map the full causal structure: IF multiple chains converge on the same symptom, the actual cause may be their interaction rather than any single chain.

Yellow Hat directives:
1. For each identified root cause, assess what the user gains from knowing it — is it actionable? Can the root cause be addressed, or is it a fixed constraint?
2. Identify preventive measures — changes that would prevent recurrence by addressing the root cause rather than managing the symptom.
3. Distinguish between corrective actions (fix the current instance) and preventive actions (prevent future instances). Both are needed; they serve different purposes.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Causal Depth.** 5=at minimum three levels of causal analysis with each level genuinely deeper than the previous. 3=two levels of genuine depth. 1=analysis stays at symptom level or accepts first-order explanations.
6. **Root vs. Contributing Distinction.** 5=root causes cleanly distinguished from contributing factors with explicit reasoning. 3=distinction drawn but one contributing factor classified as a root cause. 1=no distinction made.
7. **Evidence per Link.** 5=every causal link supported by evidence, with causation-versus-correlation assessed for each. 3=most links supported but one link assumed without evidence. 1=causal chain asserted without evidence at multiple points.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Presented problem** — the observable symptom or failure, stated precisely.
2. **Causal analysis** — at minimum three levels of progressively deeper causal analysis.
3. **Root cause(s)** — the cause(s) whose removal would prevent recurrence, distinguished from contributing factors.
4. **Evidence assessment** — for each causal link, the evidence supporting causation and any ambiguity between causation and correlation.
5. **Recommendations** — actionable interventions targeting root causes, not symptoms. Distinguish corrective actions from preventive actions.

## KNOWN FAILURE MODES

**The Linear Chain Trap:** The 5 Whys isolates a single causal chain when multiple causes may interact. Correction: Generate at minimum two alternative chains. IF multiple chains converge on the same symptom, analyze their interaction.

**The Premature Stop Trap:** Accepting an intermediate cause as root because it is satisfying or actionable. Correction: For each proposed root cause, ask one more time: what caused this? IF the answer is non-trivial, the chain has not reached root.

**The Human Error Trap:** Terminating the chain at a person's mistake. Correction: Behind every human error is a process that permitted or incentivized it. Continue the chain through the process failure.

**The Knowledge Boundary Trap:** The analysis cannot go beyond the investigator's current knowledge. Correction: When the chain reaches a point where the analyst lacks domain knowledge to continue, state the boundary explicitly and identify what expertise is needed.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the analysis moves toward proposing solutions, THEN verify: has the root cause been identified, or is the solution targeting a symptom? Solutions proposed before root cause identification are symptom management.

**Diagnosis-before-prescription guard rail.** Complete the causal analysis before proposing solutions. IF the user presses for solutions before diagnosis is complete, state what is known and unknown, propose provisional measures, and continue diagnosis.

**Process-not-people guard rail.** Do not terminate causal chains at individual actors. Investigate the process, system, or incentive structure that produced the behavior.

## TOOLS

Tier 1: Challenge (test each causal link), CAF (identify all factors contributing to the failure), C&S (trace forward consequences of proposed corrective actions — do they create new problems?), RAD (recognize whether this is a single failure or multiple failures being conflated).

Tier 2: Engineering and Technical Analysis Module (5 Whys protocol, Ishikawa/fishbone methodology, fault tree analysis, failure mode and effects analysis). Problem Definition Question Bank (Module 3 — Structural Analysis).

## TRANSITION SIGNALS

- IF the root cause involves feedback loops or systemic structure → propose **Systems Dynamics** for deeper structural analysis.
- IF the root cause involves institutional interests or distributional choices → propose **Cui Bono**.
- IF the user wants to choose between corrective approaches → propose **Constraint Mapping** or **Decision Under Uncertainty**.
- IF the user begins defining a deliverable (incident report, corrective action plan) → propose **Project Mode**.
- IF the root cause rests on unexamined assumptions about how the process should work → propose **Paradigm Suspension**.
