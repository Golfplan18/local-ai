---
title: deep-clarification
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Deep Clarification

## TRIGGER CONDITIONS

Positive triggers: "Why does X work that way," "explain the mechanics of," "what's really going on underneath," technical depth in a known domain. The user has an established position or understanding and wants to push past first-level explanation to underlying mechanics. The domain is already identified — the user is not exploring; they are drilling.

Negative triggers: IF the user is unfamiliar with the domain and needs orientation, THEN route to Terrain Mapping. IF the user has a deliverable in mind, THEN route to Project Mode. IF the user wants to question the foundational assumptions rather than understand the mechanics within the current framework, THEN route to Paradigm Suspension.

## EPISTEMOLOGICAL POSTURE

The domain is accepted. The position or claim is known. The task is to push understanding deeper — from surface explanation to mechanism, from mechanism to underlying principle, from principle to foundational structure. Primary sources and technical depth are preferred over surveys. The standard framework is treated as the operating context, not as a target for questioning.

## DEFAULT GEAR

Gear 3. Sequential review is sufficient. The Depth model pushes toward the deepest available explanation; the Breadth model checks whether the clarification is genuinely deeper or merely more elaborate.

## RAG PROFILE

Retrieve primary sources, technical papers, foundational texts, and mechanistic explanations. Deprioritize surveys, overviews, and introductory material — the user already has surface-level understanding. IF the domain has canonical reference works or seminal papers, retrieve those. Favor sources that explain why over sources that describe what.

## DEPTH MODEL INSTRUCTIONS

White Hat directives:
1. Start from the user's current level of understanding and identify the next level of depth — what mechanism underlies the phenomenon they are asking about.
2. For each mechanistic explanation provided, identify the next level beneath it. Push at minimum two levels deeper than the user's starting point.
3. Distinguish between explanations that are well-established and explanations that are the current best understanding but contested or incomplete. Mark the epistemic boundary explicitly.

Black Hat directives:
1. Test whether each "deeper" explanation is genuinely deeper (revealing mechanism) or merely more detailed (adding facts at the same level). Depth is vertical; detail is horizontal.
2. Identify where the depth reaches the limits of current knowledge. State what is not yet understood.
3. Identify at minimum one common misconception that arises at the level of depth the user is requesting.

## BREADTH MODEL INSTRUCTIONS

Green Hat directives:
1. Identify analogies or parallel mechanisms in other domains that illuminate the mechanics being clarified. A well-chosen cross-domain analogy can make a complex mechanism intuitive.
2. Identify at minimum one alternative mechanistic explanation that exists in the literature, even if it is not the mainstream view.
3. Surface connections between the mechanics being clarified and other areas of the user's knowledge (draw on conversation RAG).

Yellow Hat directives:
1. Assess what the user gains from each level of additional depth — at what point does further depth stop being actionable and become purely academic?
2. Identify the level of depth that is most useful for the user's likely purposes.
3. Note where deeper understanding changes practical implications — places where the surface-level understanding leads to different conclusions than the deep understanding.

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Depth Genuine.** 5=the clarification reaches at minimum two levels below the user's starting understanding, each genuinely mechanistic. 3=one level of genuine depth reached. 1=the clarification adds detail horizontally without going deeper.
6. **Epistemic Boundary.** 5=the boundary between established knowledge and current best understanding is explicitly marked. 3=boundary present but not sharply defined. 1=no distinction drawn between settled and unsettled explanations.

## CONTENT CONTRACT

The output is complete when it contains:

1. **Surface explanation** — the commonly understood explanation, stated concisely as a baseline.
2. **Mechanistic clarification** — at minimum two levels of deeper explanation, each revealing the mechanism beneath the previous level.
3. **Epistemic boundary** — where current knowledge ends and uncertainty begins.
4. **Practical implications** — how the deeper understanding changes what the user would do, think, or conclude, if it does.

## KNOWN FAILURE MODES

**The Lateral Drift Trap:** Moving to adjacent topics instead of going deeper on the stated topic. Correction: Each successive explanation must be about the same phenomenon at a deeper level, not about a related phenomenon at the same level.

**The Elaboration Trap:** Adding more facts at the same level of depth and presenting this as deeper understanding. Correction: Depth is vertical (mechanism beneath mechanism). Detail is horizontal (more facts about the same mechanism). Verify that each level of explanation reveals a mechanism the previous level did not.

**The Jargon Trap:** Replacing an accessible explanation with a technical one and presenting the terminology shift as depth. Naming a phenomenon is not explaining it. Correction: Each deeper level must explain a mechanism, not merely name it with more specialized vocabulary.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the clarification moves toward recommending an action or position, THEN pause — Deep Clarification produces understanding, not recommendations.

**Vertical discipline guard rail.** IF the analysis begins exploring adjacent topics, redirect to the stated topic. The user asked for depth, not breadth.

**Honest limits guard rail.** WHEN the depth reaches the boundary of current knowledge, say so. Do not fabricate deeper explanations beyond what the evidence supports.

## TOOLS

Tier 1: Challenge (test whether each explanatory level is genuinely deeper), CAF (at deeper levels, new factors become relevant — identify them), Concept Fan (identify the right level of abstraction for the mechanistic explanation).

Tier 2: Load based on domain signals. Engineering and Technical Analysis Module for technical domains.

## TRANSITION SIGNALS

- IF the clarification reveals an unexamined assumption beneath the accepted explanation → propose **Paradigm Suspension**.
- IF the user begins asking about connections between the clarified concept and other concepts → propose **Relationship Mapping** or **Synthesis**.
- IF the user starts defining a deliverable based on the deeper understanding → propose **Project Mode**.
- IF the domain is unfamiliar enough that the user needs a broader map before drilling deeper → propose **Terrain Mapping**.
