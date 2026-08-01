---
lens_id: sensemaking
name: Sensemaking
lens_type: mental-model
applicability: [crisis-response, ambiguity-navigation, post-incident-analysis]
foundational: false
source: "Weick, Karl E. (1995). *Sensemaking in Organizations*. Sage; Weick (1993). 'The collapse of sensemaking in organizations: The Mann Gulch disaster.'"
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - organizational
  - crisis
---

# Sensemaking

## Trigger

Invoked from modes that analyze ambiguous situations, crisis response, or organizational identity disruption — when actors are struggling to construct a workable interpretation of what is happening and the established frameworks have broken down. The host mode supplies the situation and the actors; the lens supplies the action-and-narration discipline and the warning signs of sensemaking collapse.

## Core Structure

### Core Insight

People do not first understand a situation and then act — they act, observe the results, and then construct a plausible story that explains what is happening. Sensemaking is retrospective, social, and anchored in identity. Under extreme stress, the process can collapse entirely: people lose their framework for interpreting events and freeze. Karl Weick's analysis of the Mann Gulch disaster showed that when firefighters' roles dissolved, so did their ability to comprehend the fire and respond. "If people can stay in action, they can make sense of things; if they stop, confusion may overwhelm them."

### Mechanism

Sensemaking is grounded in identity (who we are determines what counts as relevant), retrospective (we make sense of what we have already done), social (shared narratives bootstrap understanding), and ongoing (sense is continuously updated). When identity and role structure dissolve under stress, the cognitive scaffolding for sensemaking collapses. Action generates data and preserves identity; freezing produces neither and accelerates collapse.

### Applicability Conditions

- The situation is genuinely ambiguous or novel.
- Established routines or procedures do not fully apply.
- Time and uncertainty are creating stress.
- Sense must be made socially, not just individually.

### Common Misapplications

- Treating sensemaking as inferior to "real" understanding rather than as the actual mechanism.
- Demanding pre-action understanding when sensemaking proceeds through action.
- Confusing sensemaking with rationalization (the latter is a failure mode).
- Ignoring identity and role structure as load-bearing for sensemaking.

### Related Models

- **OODA Loop** — the orient stage is where sensemaking is centrally located.
- **Cynefin Framework** — domain-typing that determines whether sensemaking or known procedure applies.
- **Psychological Safety** — what enables actors to voice partial sense without penalty.

### Worked example

During a major production outage, the on-call team assumes a database failure based on an initial alert. They spend forty minutes on database diagnostics while the actual cause — a misconfigured load balancer — goes uninvestigated. Their initial narrative ("this is a DB problem") filters out contradictory cues like healthy database metrics. A sensemaking-aware incident process would have required a cue audit at the fifteen-minute mark: "What evidence supports our current theory, and what evidence contradicts it?"

## Application Steps

1. Keep people acting — small, safe-to-fail actions generate data even when the big picture is unclear.
2. Encourage people to narrate what they are seeing and doing; shared stories build shared understanding.
3. Preserve role structure — when identities dissolve, sensemaking collapses with them.
4. Look for cues that update the current story; discard the story when cues no longer fit rather than forcing cues to fit.
5. After the event, reconstruct the timeline of what people believed at each moment, not just what they did.

## Detection Signals

- A situation is genuinely ambiguous — multiple interpretations are plausible and no one is sure what is happening.
- An established routine or procedure has broken down and the team is improvising.
- Stress or time pressure is causing people to freeze rather than adapt.
- A post-crisis review needs to understand why people acted as they did.
- Organizational change has disrupted roles and people are unsure what their job now requires.

## Critical Questions

- Is the team in action, generating data, or frozen?
- Are roles intact, or has the role structure dissolved under stress?
- Is the current narrative being updated by cues, or are cues being filtered to fit the narrative?
- Are dissenting interpretations being voiced and incorporated?
- Does the post-incident analysis reconstruct in-the-moment beliefs, or does it impose retrospective clarity?

## Common Failure Modes

- **Narrative lock-in** — early interpretation persists despite contradictory cues. Detection: investigation continues in original direction long after evidence stopped supporting it. Correction: build cue-audit checkpoints into incident response.
- **Sensemaking collapse** — actors freeze because they cannot interpret the situation. Detection: action stops, communication degrades. Correction: enforce small actions to restart the cycle; preserve role structure.
- **Retrospective rationalization** — post-hoc story makes the response sound coherent when it was not. Detection: timeline reconstruction shows the explanation could not have been known at the time. Correction: separate "what we knew when" from "what we know now."

## Source Citations

- Weick, Karl E. (1995). *Sensemaking in Organizations*. Sage Publications. Comprehensive theoretical treatment.
- Weick, Karl E. (1993). "The collapse of sensemaking in organizations: The Mann Gulch disaster." *Administrative Science Quarterly* 38(4):628-652. Foundational case study.
- Weick, Karl E. and Kathleen M. Sutcliffe (2007). *Managing the Unexpected*. Jossey-Bass. High-reliability application.
- Klein, Gary (1998). *Sources of Power*. MIT Press. Naturalistic-decision-making complement.
