---
lens_id: practical-drift
name: Practical Drift
lens_type: mental-model
applicability: [post-mortem-analysis, safety-audit, organizational-risk]
foundational: false
source: "Snook, Scott A. (2000). *Friendly Fire: The Accidental Shootdown of U.S. Black Hawks over Northern Iraq*. Princeton University Press."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - safety
  - organizational
---

# Practical Drift

## Trigger

Invoked from modes that audit operational practice against documented procedure, conduct post-mortems, or evaluate the gap between official and actual workflow — when local adaptations have accumulated and the documented standard no longer describes how the work is done. The host mode supplies the procedure and the operational context; the lens supplies the local-rationality framework that explains why drift occurs and where it becomes dangerous.

## Core Structure

### Core Insight

Over time, the way work is actually done drifts away from the way it is officially prescribed. Each small deviation is locally rational — it saves time, accommodates reality, or works around a constraint — but the cumulative drift creates hidden vulnerabilities that only become visible when the system fails. Scott Snook coined the term analyzing the 1994 friendly-fire shootdown of two U.S. Army Black Hawks over Iraq: every unit involved had drifted from procedure in small ways, and the gaps aligned catastrophically.

### Mechanism

Local actors face local constraints (time, resources, conflicting demands) that the procedure designers did not fully anticipate. Each adaptation is rational at the local level and produces no immediate failure. Cross-unit assumptions that once held no longer hold, but the violations are invisible from any single vantage point because each unit only sees its own drift. When system-level coordination is needed, the gaps between drifted units align and the system fails in a way no single unit's drift could have caused.

### Applicability Conditions

- A documented procedure exists and was once followed.
- Multiple local actors or units operate under the procedure.
- Conditions have changed since the procedure was written, creating local pressure to adapt.
- Cross-unit coordination depends on the procedure's implicit assumptions.

### Common Misapplications

- Blaming individual actors for drift that the system invited.
- Treating drift as deliberate rule-breaking rather than local-rationality response.
- Trying to enforce the original procedure without addressing the conditions that drove drift.
- Confusing practical drift with normalization of deviance — they are related but distinct.

### Related Models

- **Normalization of Deviance** — what happens when drift becomes invisible to those inside the system.
- **Swiss Cheese Model** — what aligns when drift erodes the assumed safety properties of multiple units.
- **Normal Accident Theory** — the structural property of complex tightly-coupled systems that makes drift catastrophic.

### Worked example

A data center's backup procedure specifies nightly full backups with off-site replication verified weekly. Over two years, the team shifts to incremental-only backups because full backups slow overnight processing. The weekly verification check becomes monthly, then quarterly, then "when someone remembers." When a ransomware attack encrypts the primary storage, the team discovers the off-site replicas haven't been verified in four months and the most recent clean backup is 11 days old.

## Application Steps

1. Map the official procedure step by step.
2. Observe or interview to discover the actual practice — focus on where and why they diverge.
3. For each deviation, assess: is this an improvement on the procedure, or a latent risk?
4. Identify which deviations have been normalized — these are the most dangerous because no one flags them.
5. Either update the procedure to match the better practice or enforce the original — never leave the gap undocumented.

## Detection Signals

- Standard operating procedures exist but haven't been audited against actual practice recently.
- An incident reveals that "what we do" and "what the manual says" have diverged.
- Workarounds have become normalized — people no longer recognize them as deviations.
- A system has been running "fine" for a long time without a serious failure, creating complacency.
- Local pressures (time, resources) routinely require informal adaptations.

## Critical Questions

- Is the deviation locally rational, and what local pressure produced it?
- Does cross-unit coordination still work given the drift, or does it depend on assumptions no longer met?
- Has the procedure been updated to capture beneficial drift, or is the gap silent?
- What is the failure mode if the drifts in different units align?
- Is the procedure being enforced because it is correct, or because it is documented?

## Common Failure Modes

- **Individual blame** — attributing drift to negligence of specific actors. Detection: post-mortem fingers individuals rather than system. Correction: trace local conditions that produced the drift.
- **Re-enforcement without redesign** — reinstating the original procedure without addressing why drift occurred. Detection: drift returns within months. Correction: revise procedure to accommodate the conditions, or remove the conditions.
- **Drift-as-improvement amnesia** — losing track of which drifts are improvements and which are risks. Detection: no documented disposition for each observed deviation. Correction: produce a deviation register with explicit accept/reject decisions.

## Source Citations

- Snook, Scott A. (2000). *Friendly Fire*. Princeton University Press. Originating analysis.
- Snook, Scott A. and Jeffrey C. Connor (2005). "The price of progress: Structurally induced inaction." Working paper. Extension to organizational design.
- Vaughan, Diane (1996). *The Challenger Launch Decision*. University of Chicago Press. Related normalization-of-deviance frame.
- Reason, James (1997). *Managing the Risks of Organizational Accidents*. Ashgate. Broader context.
