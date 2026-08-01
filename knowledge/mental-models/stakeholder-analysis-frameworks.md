---
lens_id: stakeholder-analysis-frameworks
name: Stakeholder Analysis Frameworks
lens_type: catalog
applicability: [stakeholder-mapping]
foundational: false
source: "Bryson, John M. (2004). What to do when stakeholders matter. Public Management Review 6(1):21-53. Mitchell, Agle, Wood (1997). Toward a theory of stakeholder identification and salience. Academy of Management Review 22(4):853-886. Mendelow, A.L. (1991). Environmental Scanning: The Impact of the Stakeholder Concept. Proceedings of the Second International Conference on Information Systems."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - catalog
  - stakeholder
  - strategy
---

# Stakeholder Analysis Frameworks

## Trigger

Invoked from within `stakeholder-mapping` (T8) when that mode needs structured frameworks for identifying, classifying, and prioritizing stakeholders in a multi-party situation. The host mode supplies the situation, decision, or institutional change being analyzed; the lens supplies the catalog of named identification and classification frameworks the analyst can apply, singly or in combination, to produce a stakeholder map.

## Core Structure

The catalog enumerates the canonical frameworks for stakeholder identification and classification. Each is a named pattern with its structure, when it applies, and a brief operational note. Frameworks are listed roughly in order from most-cited to most-specialized; an analyst typically applies two or three in combination rather than picking one.

1. **Mitchell/Agle/Wood salience framework.** Three attributes — **power** (the stakeholder's ability to impose its will), **legitimacy** (the social acceptance of the stakeholder's claim), and **urgency** (the time-criticality and importance of the claim to the stakeholder). Stakeholders are classified into seven types based on which attributes they hold: **dormant** (power only), **discretionary** (legitimacy only), **demanding** (urgency only), **dominant** (power + legitimacy), **dangerous** (power + urgency), **dependent** (legitimacy + urgency), and **definitive** (all three). Salience to management equals the sum of attributes held; **definitive** stakeholders receive priority engagement. Used when the analyst needs to distinguish stakeholders who can act from stakeholders who only have a moral claim, or when stakeholder priority is contested. Operational note: attributes are dynamic — a dormant stakeholder who acquires legitimacy or urgency moves up the salience ladder.

2. **Mendelow power/interest grid.** A 2×2 matrix with **power** on one axis and **interest** (in this specific decision or issue) on the other. Quadrants: **high-power, high-interest** = manage closely (active engagement, frequent communication); **high-power, low-interest** = keep satisfied (avoid unnecessary mobilization); **low-power, high-interest** = keep informed (responsive communication without ceding decision rights); **low-power, low-interest** = monitor (minimal effort, periodic re-check). Used when the analyst needs to allocate finite engagement resources across many stakeholders, or when the question is "who gets a seat at which table."

3. **Bryson Power-versus-Interest grid.** A variant of Mendelow framed for strategic-management and public-administration contexts. Same 2×2 axes, but extended with explicit guidance on engagement protocols per quadrant and emphasis on the dynamics of stakeholder coalitions across quadrants. Used when the institutional context is public, multi-jurisdictional, or coalition-driven, and the engagement strategy must account for stakeholders shifting between quadrants over time.

4. **Stakeholder Influence Diagram.** A directed-graph visualization of stakeholders as nodes and influence relationships as arrows (who influences whom, in what direction, how strongly). The diagram surfaces indirect influence chains a flat list misses — for example, a low-salience stakeholder who has the ear of a high-salience one. Used when influence pathways are non-obvious, when coalition possibilities matter, or when the analyst suspects that nominal authority and actual influence diverge.

5. **Bryson Stakeholder Identification Protocol.** A five-step process: (1) **identify** stakeholders broadly, including absent and latent ones; (2) **classify** using salience, power/interest, or another framework above; (3) **analyze** each stakeholder's interests, stakes, and probable response to the proposed action; (4) **identify** alliances, coalitions, and conflicts among stakeholders; (5) **develop** a differentiated engagement strategy keyed to the classification and alliance structure. Used when the situation requires a complete stakeholder analysis rather than the ad-hoc application of one framework.

6. **Salience-over-time tracking.** Not a separate framework but an operational discipline applicable to any of the above: re-run the classification at decision points or whenever a triggering event occurs (a stakeholder acquires a new attribute, a coalition forms or breaks, an external event raises urgency). Used to prevent the static-salience failure mode (see below).

## Application Steps

1. Receive the situation, decision, or institutional change from the host mode.
2. Apply the **Bryson Stakeholder Identification Protocol** as the spine; use the other frameworks as tactical tools within its steps.
3. In the classify step, default to **Mitchell/Agle/Wood** when the question is salience and to **Mendelow / Bryson power-interest** when the question is engagement allocation; apply both when the situation is complex.
4. Construct a **Stakeholder Influence Diagram** when influence pathways are non-obvious or coalition possibilities matter.
5. Return the stakeholder map (classification + influence diagram + engagement strategy) to the host mode.

## Detection Signals

- The situation has multiple parties whose interests are not fully aligned.
- A policy decision affects heterogeneous groups whose stakes differ in kind, not just in degree.
- Institutional change is being considered with multiple constituencies, some represented and some not.
- The analyst notices the conversation defaulting to "the stakeholders" as a single homogeneous block when in fact distinct stakeholder types are present.
- Engagement resources are scarce and prioritization across stakeholders is contested.
- Coalition possibilities are being discussed without a structured map of who could ally with whom.

## Critical Questions

- Are stakeholders identified by stated position or by underlying interest? Position-based identification misses latent stakeholders who have not yet declared a position; interest-based identification surfaces them.
- Are absent stakeholders included? Stakeholders who would be affected but are not represented in the conversation (future generations, non-organized publics, those without procedural standing) are systematically under-counted unless the analyst actively scans for them.
- Is the salience classification re-checked after dynamic changes? A low-salience stakeholder may become high-salience overnight (acquiring power, legitimacy, or urgency); a static classification becomes a stale map.
- Is the framework choice matched to the question? Mitchell/Agle/Wood answers "who deserves attention"; Mendelow answers "where to spend engagement resources"; an Influence Diagram answers "who actually shapes outcomes." Mismatched framework yields a map that does not address the operational question.
- Are conflicts among stakeholders surfaced as well as alliances? An analysis that lists each stakeholder's interests in isolation, without mapping where interests collide, produces an engagement strategy blind to friction points.

## Common Failure Modes

- **Stated-stakeholder bias** — only stakeholders who self-identify get analyzed; those without organized voice are absent from the map. Detection: the stakeholder list correlates with which parties have communications staff. Correction: actively scan for affected-but-absent parties using the question "who would be affected by this decision who is not in the room?"
- **Static salience** — classifying stakeholders once and not revisiting as the situation evolves. Detection: the engagement strategy was set at project start and has not been re-checked despite changing circumstances. Correction: apply the salience-over-time tracking discipline; trigger a re-classification at named decision points.
- **Single-framework reduction** — using only Mendelow's grid when the situation calls for salience analysis, or only the Influence Diagram when prioritization matters. Detection: the stakeholder map answers a question the host mode did not ask, while the host mode's actual question goes unaddressed. Correction: apply the framework matched to the host's question; supplement with others as needed.
- **Coalition blindness** — listing stakeholders individually without mapping the alliance structure. Detection: the stakeholder map has no edges, only nodes. Correction: construct an Influence Diagram or run the alliances-and-conflicts step of Bryson's protocol explicitly.
- **Power-only proxy** — collapsing salience to power alone, ignoring legitimacy and urgency. Detection: the stakeholder ranking matches the org-chart hierarchy. Correction: re-apply Mitchell/Agle/Wood with attention to legitimacy and urgency as independent attributes.

## Source Citations

- Bryson, John M. (2004). "What to do when stakeholders matter: Stakeholder identification and analysis techniques." *Public Management Review* 6(1):21-53. Comprehensive review and operational protocol.
- Mitchell, Ronald K., Bradley R. Agle, and Donna J. Wood (1997). "Toward a theory of stakeholder identification and salience: Defining the principle of who and what really counts." *Academy of Management Review* 22(4):853-886. The salience framework and seven-type classification.
- Mendelow, Aubrey L. (1991). "Environmental scanning: The impact of the stakeholder concept." *Proceedings of the Second International Conference on Information Systems*. The power/interest grid.
- Freeman, R. Edward (1984). *Strategic Management: A Stakeholder Approach*. Pitman. The founding text establishing stakeholder theory as a strategic-management discipline; conceptual ancestor of the frameworks above.
- Related: Ulrich Critical Systems Heuristics (CSH) for the question of who should count as a stakeholder when standing is itself contested.
