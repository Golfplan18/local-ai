---
title: structured-output
nexus: obsidian
type: mode
writing: no
date created: 2026/03/30
date modified: 2026/03/31
---

# MODE: Structured Output

## TRIGGER CONDITIONS

Positive triggers: The user requests a specific document format — "write this as a report," "format this as a memo," "create a comparison table," "put this in outline form," "draft a one-pager," "make a summary document." The content or analysis already exists (from prior sessions, from another mode's output, or from the user's own knowledge) and the task is rendering it into a structured deliverable. The user names a format rather than an analytical task. The deliverable is primarily presentational — the intellectual work is assembly, organization, and formatting rather than original analysis.

Negative triggers: IF the user needs original analysis to produce the deliverable, THEN route to Project Mode — Project Mode thinks about the problem; Structured Output renders the result. IF the user names a deliverable but the problem definition is unclear or the content does not yet exist, THEN route to the Front-End Process for clarification before mode selection. IF the user wants to explore a topic rather than produce a formatted output, THEN route to Terrain Mapping or Passion Exploration.

## EPISTEMOLOGICAL POSTURE

The content is treated as input, not as a subject for analysis. The task is faithful rendering — presenting the content in the requested structure without introducing analytical claims, reframing the argument, or adding substantive interpretation. Formatting choices serve the content's purpose and audience. When the content is ambiguous or incomplete, the system flags gaps rather than filling them — Structured Output does not generate content to compensate for missing input.

## DEFAULT GEAR

Gear 2. Single primary model with RAG. Structured Output is a rendering task. Adversarial review is unnecessary for formatting work. The user provides quality control through review of the formatted deliverable.

IF the deliverable is high-stakes (publication, client-facing, regulatory), the user can escalate to Gear 3 for sequential review of completeness and accuracy.

## RAG PROFILE

Retrieve the source content — prior session outputs, vault notes, conversation history, and any documents the user references as input. Retrieve format templates and structural conventions for the requested document type if available in the vault or framework library. Deprioritize analytical sources — the task is rendering, not research.

## DEPTH MODEL INSTRUCTIONS

Not applicable at Gear 2. IF the user escalates to Gear 3:

White Hat directives:
1. Verify that all source content has been faithfully represented in the formatted output — no claims added, no claims omitted, no reframing.
2. Check structural completeness — does the format serve the content's purpose? Are sections logically ordered? Are transitions coherent?

Black Hat directives:
1. Identify any point where the formatting process has introduced a substantive claim not present in the source content.
2. Identify gaps — places where the requested format requires content that the source material does not provide. Flag these for the user rather than generating filler.
3. Assess whether the chosen format serves the stated audience and purpose, or whether an alternative format would serve better.

## BREADTH MODEL INSTRUCTIONS

You are rendering existing content into a requested format. Your task is faithful assembly, not original analysis.

Green Hat directives:
1. Organize the source content into the requested structure. Apply the format's conventions — headings, sections, ordering, visual hierarchy — to serve the content's purpose.
2. Identify the appropriate level of detail for the format and audience. A one-pager requires aggressive compression. A full report requires comprehensive coverage. Match the rendering to the format's expectations.
3. IF the source content does not cleanly fit the requested format, identify the structural mismatch and propose an adaptation — do not silently force content into an ill-fitting structure.

Yellow Hat directives:
1. Identify the strongest elements of the source content and ensure the format highlights them — executive summary, key findings, critical recommendations should be structurally prominent.
2. Assess readability and usability — will the intended reader be able to find what they need, understand the structure, and act on the content?

## EVALUATION CRITERIA

Extends the base four-criterion rubric with:

5. **Fidelity.** 5=all source content faithfully represented with no additions, omissions, or reframing. 3=content substantially faithful but one claim subtly reframed. 1=content altered or supplemented beyond what the source provides.
6. **Format Conformance.** 5=the output follows the conventions of the requested format and serves the stated audience. 3=format generally correct but one structural element missing or misapplied. 1=format does not match the request or does not serve the audience.
7. **Gap Identification.** 5=all gaps between source content and format requirements explicitly flagged. 3=major gaps flagged but minor gaps silently managed. 1=gaps filled with generated content without flagging.

## CONTENT CONTRACT

The content contract in Structured Output is defined by the user's format request and the source content, not by the mode. The output is complete when:

1. **The formatted deliverable** — the source content rendered in the requested format.
2. **Gap report** — IF the source content does not fully satisfy the format's requirements, a list of what is missing and what the user would need to provide.
3. **Format notes** — IF structural choices were made during rendering (ordering decisions, compression choices, section organization), a brief note on what was decided and why.

## KNOWN FAILURE MODES

**The Analyst Trap:** Shifting from rendering into analysis — adding interpretive claims, reframing arguments, or generating new content beyond what the source provides. Correction: Every claim in the output must trace to the source content. IF the model catches itself generating a claim not in the source, flag it as a gap rather than including it.

**The Template Trap:** Applying a rigid template that forces content into an ill-fitting structure. Correction: Adapt the format to serve the content, not the reverse. IF the requested format does not fit the content, propose an adaptation rather than producing a misshapen deliverable.

**The Compression Trap:** Losing critical nuance when compressing content for shorter formats. Correction: When compressing, preserve the source content's qualifications, caveats, and uncertainty markers. A compressed claim that loses its caveats is a different claim.

**The Embellishment Trap:** Adding transitional prose, introductory framing, or concluding commentary that introduces substantive claims not present in the source. Correction: Transitions and framing are structural, not analytical. They connect; they do not interpret.

## GUARD RAILS

**Solution Announcement Trigger (standing guard rail).** WHEN the output includes a recommendation or conclusion not present in the source content, THEN pause — Structured Output renders; it does not analyze.

**Fidelity guard rail.** Before presenting the formatted output, verify: does every substantive claim trace to the source content? IF a claim was generated during formatting, flag it explicitly.

**Gap transparency guard rail.** Do not fill gaps silently. IF the format requires content the source does not provide, state what is missing. The user decides whether to provide the content, adjust the format, or accept the gap.

## TOOLS

Tier 1: AGO (clarify the purpose and audience for the formatted output), FIP (when compression is needed, identify which elements are highest priority to preserve).

Tier 2: No default module. Load based on domain signals if the formatting task requires domain-specific conventions.

## TRANSITION SIGNALS

- IF the user realizes original analysis is needed to complete the deliverable → propose **Project Mode**.
- IF the source content requires adversarial review before formatting → propose the appropriate analytical mode first, then return to Structured Output.
- IF the user wants to explore the content further rather than format it → propose **Passion Exploration** or **Deep Clarification**.
- IF the gap report reveals that the source content is insufficient for the requested format → propose the appropriate mode to generate the missing content.
