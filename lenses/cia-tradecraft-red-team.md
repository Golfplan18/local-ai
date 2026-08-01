---
lens_id: cia-tradecraft-red-team
name: CIA Tradecraft Red Team
lens_type: protocol
applicability: [red-team-assessment, red-team-advocate]
foundational: true
source: "Central Intelligence Agency (2009). A Tradecraft Primer: Structured Analytic Techniques for Improving Intelligence Analysis. Zenko, Micah (2015). Red Team: How to Succeed by Thinking Like the Enemy. Basic Books. Hoffman, Bryce (2017). Red Teaming: How Your Business Can Conquer the Competition by Challenging Everything. Crown Business."
date created: 2026-05-01
date modified: 2026-06-17
nexus:
  - ora
type: resource
tags:
  - lens
  - protocol
  - intelligence-analysis
  - adversarial-reasoning
  - red-team
---

# CIA Tradecraft Red Team

## Trigger

Invoked from red-team modes when a high-stakes artifact, plan, analysis, or claim needs sanctioned adversarial examination before commitment or external argument. The host mode supplies the target and the purpose of the challenge; the lens supplies the red-team tradecraft discipline: attack the actual artifact, model the relevant adversary or audience, challenge assumptions, avoid fabricated objections, and disclose honest attack failures.

## Core Structure

### Core Insight

Red teaming is not generic criticism. It is a sanctioned adversarial role with a disciplined target, explicit audience, and evidence standard. Its value comes from making opposition legitimate enough to be honest while constraining that opposition tightly enough that it does not become performative hostility.

### Tradecraft Commitments

1. **Named target.** A red team attacks a specific artifact, plan, claim, system, or decision. Vague domains produce vague objections.
2. **Sanctioned role.** The adversarial stance must be authorized. Without sanction, critique is interpreted as personal opposition rather than institutional rigor.
3. **No fabrication.** Attacks must rest on what the target actually says, assumes, omits, or enables.
4. **Adversary/audience model.** The analyst must model the real actor, reviewer, or audience whose attack matters, not a generic critic.
5. **Assumption discipline.** Key assumptions are surfaced before attack paths are generated.
6. **Attack-failure disclosure.** If a plausible attack class produces no finding, the non-finding is reported rather than replaced with a weaker manufactured objection.

### Two Host Uses

- **Red Team Assessment** ranks vulnerabilities by severity for the artifact owner's own repair decisions.
- **Red Team Advocate** ranks attacks by persuasive force for use against the artifact before an external audience.

The tradecraft core is shared, but the ranking criterion changes. Assessment asks "what could break this?" Advocate asks "what could persuade this audience against it?"

### Source Tradition

The discipline draws on structured analytic techniques from intelligence tradecraft: Team A/Team B, Devil's Advocacy, Red Cell, Key Assumptions Check, What If Analysis, and Analysis of Competing Hypotheses. It also inherits older role-based dissent traditions, including the Catholic *Advocatus Diaboli*, Talmudic and Israeli intelligence practices of arguing the opposite case, and modern military/business red-team practice.

## Application Steps

1. Define the target precisely: artifact, plan, system, claim, decision, or argument.
2. Name the red-team purpose: owner-facing assessment or external-facing advocate brief.
3. Identify the relevant adversary, reviewer, institution, or audience.
4. Run a key-assumptions check on the target before generating attacks.
5. Generate attacks only from the target's actual content, omissions, dependencies, incentives, and exposed assumptions.
6. Rank findings by the host mode's criterion: severity for assessment, persuasive force for advocate.
7. Disclose attack classes that were considered and produced no honest finding.

## Detection Signals

- A high-stakes plan or artifact is about to be committed without structured opposition.
- The user asks what critics, adversaries, reviewers, competitors, regulators, or hostile audiences would say.
- A group has converged on one interpretation and needs sanctioned dissent.
- The artifact has only been reviewed by people who share its assumptions.
- The cost of being wrong exceeds the discomfort of adversarial examination.
- Groupthink, mirror-imaging, or assumption blindness is plausible.

## Critical Questions

- Is the target specific enough to attack without inventing a straw version?
- Is the adversarial role sanctioned and scoped, or is it merely unsanctioned negativity?
- Are attacks grounded in the target's actual claims, omissions, dependencies, or assumptions?
- Has the analyst modeled the relevant adversary or audience rather than a generic critic?
- Are severity and persuasive force kept distinct according to the selected host mode?
- Are honest non-findings disclosed instead of filled with weak attacks?

## Common Failure Modes

- **Straw-target attack** - Detection: the critique attacks a version of the artifact that the artifact does not actually assert. Correction: quote or paraphrase the exact target claim, dependency, or omission before attacking.
- **Sycophantic inverse** - Detection: the analysis performs hostility to prove independence. Correction: require evidence, mechanism, and audience relevance for every attack.
- **Mirror-imaging** - Detection: the imagined adversary shares the user's frame, priorities, or assumptions. Correction: model the adversary's incentives, language, and success criteria separately.
- **Unsanctioned dissent drift** - Detection: critique becomes interpersonal or politically unsafe because the role was not established. Correction: restate the sanctioned red-team purpose and target.
- **Ranking confusion** - Detection: assessment findings are ranked by rhetorical force or advocate attacks by repair severity. Correction: re-rank under the host mode's output contract.
- **Manufactured finding** - Detection: every attack category returns a finding even when evidence is thin. Correction: add attack-failure disclosure and preserve honest non-findings.

## Source Citations

- Central Intelligence Agency (2009). *A Tradecraft Primer: Structured Analytic Techniques for Improving Intelligence Analysis*.
- Zenko, Micah (2015). *Red Team: How to Succeed by Thinking Like the Enemy*. Basic Books.
- Hoffman, Bryce (2017). *Red Teaming: How Your Business Can Conquer the Competition by Challenging Everything*. Crown Business.
- Heuer, Richards J. Jr. (1999). *Psychology of Intelligence Analysis*. Center for the Study of Intelligence.
