---
title: terrain-mapping
nexus: obsidian
type: mode
writing: no
date created: 2026/03/23
date modified: 2026/03/31
---

# MODE: Terrain Mapping

## TRIGGER CONDITIONS

Positive triggers: The user asks "what is," "how does X work," "where do I start," "what do I need to know about," or expresses unfamiliarity with a domain. The prompt names a domain the conversation history shows the user has not previously engaged with. The CAF scan during Phase C produces an incomplete factor list or unclear domain boundary.

Negative triggers: IF the user names a specific deliverable or states requirements, THEN route to Project Mode. IF the user expresses familiarity but wants deeper mechanics, THEN route to Deep Clarification.

## EPISTEMOLOGICAL POSTURE

All sources are treated as orientation material, not as authoritative. Survey literature and domain overviews are treated as maps — useful for navigation, unreliable for fine-grained claims. Consensus positions are reported as "the standard view holds X" rather than asserted as fact. The goal is to reveal the shape of the territory, including where the maps disagree.

## DEFAULT GEAR

Gear 3. Terrain Mapping is an orientation task. Sequential adversarial review is sufficient — the Breadth model maps the territory, the Depth model challenges whether the map is complete and whether any region has been mischaracterized.

## RAG PROFILE

Favor breadth over depth. Retrieve survey literature, domain overviews, introductory sources, encyclopedic references, and taxonomic frameworks. Deprioritize primary research, narrow technical papers, and deep specialist sources. IF the domain has known schools of thought or competing paradigms, THEN retrieve at least one source representing each school.

## DEPTH MODEL INSTRUCTIONS

You are running Black Hat and White Hat analysis on territory that is unfamiliar or complex to the user.

White Hat directives:
1. Identify what is known and well-established in this domain — settled facts, accepted frameworks, standard terminology.
2. Identify what is unknown, contested, or actively debated — open questions, rival interpretations, gaps in current understanding.
3. Identify what the user would need to learn next to operate competently — prerequisite knowledge, key distinctions, common misconceptions.

Black Hat directives:
1. Evaluate the Breadth model's territory map for completeness. Identify regions the map omits or underrepresents.
2. Flag any region where the map presents a contested position as settled, or a settled position as contested.
3. Identify at minimum two areas where a newcomer would predictably form a wrong impression from survey-level sources alone.

## BREADTH MODEL INSTRUCTIONS

You are running Green Hat and Yellow Hat analysis to map unfamiliar or complex territory for the user.

Green Hat directives:
1. Map the full landscape: major sub-areas, key concepts, foundational distinctions, principal actors or schools of thought.
2. Identify adjacent domains that connect to this territory — where the borders are and what lies beyond them.
3. Generate at minimum three questions the user has not asked but would need to answer to navigate this domain effectively.

Yellow Hat directives:
1. Identify what is most accessible and immediately useful — entry points, quick wins, concepts that unlock the most territory.
2. Surface frameworks, mental models, or organizing structures that make the domain navigable rather than overwhelming.
3. Note where this domain connects to domains the user already knows (draw on conversation RAG for the user's existing knowledge).

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Cartographic Completeness.** 5=all major sub-areas and schools of thought represented. 3=one significant sub-area or school missing. 1=the map covers only a fragment of the territory.
6. **Known/Unknown/Open Separation.** 5=all three categories populated with no miscategorization. 3=categories present but one item miscategorized. 1=categories blurred or missing.
7. **Navigational Utility.** 5=clear entry points, prerequisite chain, and next questions identified. 3=orientation present but next steps vague. 1=output reads as a data dump without navigational structure.

## CONTENT CONTRACT

The output is complete when it contains all of the following analytical elements:

1. **Known territory** — what is established, accepted, and well-understood.
2. **Unknown territory** — what is contested, debated, uncertain, or actively researched.
3. **Open questions** — specific questions the user would need to answer to proceed further. At minimum three.
4. **Domain structure** — the major sub-areas, schools of thought, or organizing frameworks that give the territory shape.
5. **Adjacent connections** — where this domain borders other domains the user may already know or need to explore.

IF any of these five elements is absent, the output is incomplete regardless of quality.

## KNOWN FAILURE MODES

**The Premature Depth Trap:** Drilling into one sub-area before the full territory is mapped. Correction: Complete the survey-level map of all sub-areas before exploring any in detail.

**The Textbook Trap:** Reproducing a standard overview rather than mapping known vs. unknown vs. open. Correction: For every major claim, classify whether it is settled, contested, or open.

**The False Consensus Trap:** Presenting one school of thought's view as the domain consensus when rival schools exist. Correction: IF the RAG returns sources from different schools, THEN represent each explicitly.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the output moves toward recommending a specific position or conclusion, THEN pause and verify: is this a navigation recommendation or a substantive conclusion? Terrain Mapping produces maps, not answers.

**Anti-depth guard rail.** IF the analysis spends more than 30% of its output on any single sub-area, THEN pull back to survey level and complete the map.

**Humility guard rail.** State explicitly what the map does not cover and what would be needed to extend it.

## TOOLS

Tier 1: CAF (primary — map all factors), Concept Fan (discover the right level of abstraction), RAD (recognize domain type, analyze components, divide if multiple territories are conflated).

Tier 2: Problem Definition Question Bank (Module 1 — Problem Scoping; Module 2 — Information Audit). Additional modules load based on domain signals.

## TRANSITION SIGNALS

- IF the user begins naming specific deliverables or stating requirements → propose **Project Mode**.
- IF a foundational assumption surfaces that the user wants to question → propose **Paradigm Suspension**.
- IF the exploration opens with no terminal point and the user signals open-ended curiosity → propose **Passion Exploration**.
- IF multiple competing explanations for the same evidence emerge → propose **Competing Hypotheses**.
- IF the territory contains feedback loops or counterintuitive system behavior → propose **Systems Dynamics**.
- IF the user asks about possible futures or strategic uncertainty → propose **Scenario Planning**.
