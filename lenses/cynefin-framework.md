---
lens_id: cynefin-framework
name: Cynefin Framework
lens_type: catalog
applicability: [decision-classification, response-strategy, complexity-diagnosis]
foundational: false
source: "Snowden, David J. and Mary E. Boone (2007). A Leader's Framework for Decision Making. Harvard Business Review 85(11):68-76."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - catalog
  - decision
  - complexity
---

# Cynefin Framework

## Trigger

Invoked from within decision-classification and response-strategy modes when an analyst is choosing how to engage a situation and the situation type is ambiguous — when best practices from one context are failing in another, when a team is debating between extensive planning and rapid experimentation, or when a crisis has rendered familiar playbooks useless. The host mode supplies the situation under analysis; the lens supplies the four-domain classification (Simple, Complicated, Complex, Chaotic, plus Disorder) and the response-type appropriate to each, preventing the dominant failure mode of treating complex situations as merely complicated.

## Core Structure

Cynefin classifies situations by the visibility of the relationship between cause and effect. The classification determines the appropriate response style; mismatching domain and response is the central failure mode the framework prevents. The catalog has four named domains plus a fifth (Disorder) marking the state of not yet knowing which of the four applies.

1. **Simple (Clear).** Cause-and-effect relationships are obvious to anyone. The right response is sense-categorize-respond, applying best practice. Manifests in well-understood operations: a misconfigured config file, a known billing inquiry, a documented production process. The domain is stable but vulnerable to complacency, which can collapse it directly into Chaotic.

2. **Complicated.** Cause-and-effect relationships are discoverable but require expertise; multiple correct answers may exist. The right response is sense-analyze-respond, applying good or expert practice. Manifests in engineered systems requiring diagnosis: an aircraft malfunction, a complex legal question, a performance regression in production code. Experts can map the system; the answer exists but is not visible to non-experts.

3. **Complex.** Cause-and-effect relationships are visible only in retrospect, not in advance. The right response is probe-sense-respond, applying emergent practice. Manifests in living systems and human collectives: an organizational culture shift, a market response to a new product category, an unexplained cascade across microservices. The system must be tested via small probes; analysis cannot precede experiment.

4. **Chaotic.** No discernible cause-and-effect relationships exist; the system is in turbulence. The right response is act-sense-respond — act first to establish stability, then diagnose. Manifests in acute crisis: an active security breach, a natural-disaster response, a sudden organizational collapse. Novel practice may be required; the priority is to move from chaos to a domain (typically Complex) where structured response can begin.

5. **Disorder.** The state of not knowing which of the four domains the situation occupies. The fifth domain marks the analyst's epistemic state, not the situation itself. The right response is to break the situation into parts and classify each separately, retreating to a default decision style only when classification is impossible.

The dominant failure pattern is treating Complex situations as Complicated — applying expert analysis and detailed planning to a system whose cause-effect structure is emergent rather than discoverable. The error compounds because the additional analysis produces apparent precision that misleads the planning, while the underlying emergent dynamics continue to generate unpredictable behavior.

## Application Steps

1. Characterize the situation by asking: is the cause-effect relationship obvious, discoverable, emergent, or absent?
2. Map to a domain — Simple, Complicated, Complex, Chaotic, or (provisionally) Disorder.
3. Choose the appropriate response style for that domain (best practice, good practice, emergent practice, novel practice).
4. Watch for boundary transitions: a Simple system can collapse into Chaotic if complacency sets in; a Chaotic system can be stabilized into Complex through initial action.
5. Resist the temptation to force a situation into a simpler domain because the simpler response is more comfortable.

## Detection Signals

- A team is debating extensive planning versus rapid experimentation.
- Best practices from one context are failing in a new context.
- Experts disagree on diagnosis and prescribed solution.
- A crisis has made the environment unpredictable and previous playbooks seem useless.
- Leadership is demanding a predictive plan for something inherently emergent.

## Critical Questions

- Has the cause-effect visibility been honestly assessed, or has the analyst defaulted to the domain that is most comfortable to operate in?
- If the situation is Complex, has it been mistakenly framed as Complicated because the team has expert resources available and wants to use them?
- Are the boundary risks being monitored — is the Simple system at risk of complacency-driven collapse, is the Chaotic situation being stabilized rather than re-chaoticized?
- In Disorder, has each sub-component been classified separately, or is the analyst treating the whole as one undifferentiated mass?

## Common Failure Modes

- **Complex-as-Complicated** — Detection signal: extensive analysis is being applied to an emergent system; planning produces apparent precision that does not predict outcomes. Correction: switch to probe-sense-respond and expect the response style to feel less rigorous than it should.
- **Domain-comfort selection** — Detection signal: the analyst defaults to the domain whose response style they prefer, regardless of the situation's actual cause-effect visibility. Correction: classify by the situation, not by the available toolkit.
- **Frozen-in-Disorder** — Detection signal: the team is paralyzed because they cannot classify; no response is initiated. Correction: classify by parts; default to a tentative classification and monitor for evidence of misclassification.

## Source Citations

- Snowden, David J. and Mary E. Boone (2007). A Leader's Framework for Decision Making. *Harvard Business Review* 85(11):68-76.
- Kurtz, Cynthia F. and David J. Snowden (2003). The new dynamics of strategy: Sense-making in a complex and complicated world. *IBM Systems Journal* 42(3):462-483.
- Snowden, David J. (2002). Complex acts of knowing: Paradox and descriptive self-awareness. *Journal of Knowledge Management* 6(2):100-111.
