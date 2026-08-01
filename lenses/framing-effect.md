---
lens_id: framing-effect
name: Framing Effect
lens_type: mental-model
applicability: [bias-audit, communication-design, decision-presentation, persuasion-analysis]
foundational: false
source: "Tversky, Amos and Daniel Kahneman (1981). The framing of decisions and the psychology of choice. Science 211(4481):453-458."
date created: 2026-04-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - behavioral-economics
  - communication
---

# Framing Effect

## Trigger

Invoked from within bias-audit, communication-design, decision-presentation, and persuasion-analysis modes when an analyst observes that the same information presented differently is leading to different choices — a proposal that sounds dramatically better or worse depending on which statistics are highlighted, two people disagreeing about the same data because they are looking at different frames, or the suspicion that one's own preference is driven by the packaging rather than the content. The host mode supplies the decision and its presentation; the lens supplies the multi-frame restatement protocol that exposes whether the frame is doing the deciding and the strip-the-frame technique that converts to a neutral representation.

## Core Structure

### Core Insight

People respond differently to identical information depending on how it is presented — as a gain or a loss, as a percentage or an absolute number, as a survival rate or a mortality rate. The frame selects which aspects of reality become salient, and that salience drives the decision. Rational agents should be frame-invariant; humans are not. Kahneman and Tversky's Asian Disease Problem demonstrated that "200 saved out of 600" and "400 will die out of 600" produce opposite risk preferences despite being logically identical.

### Mechanism

Two cognitive features generate the bias. Attention selectivity: a frame highlights certain attributes (gains vs. losses, absolute vs. relative numbers, present vs. future) and suppresses others; the highlighted attributes dominate the decision because they are more salient. Loss aversion (in gain/loss framing specifically): a loss frame triggers risk-seeking behavior to avoid the loss, while a gain frame triggers risk-averse behavior to lock in the gain — even when the underlying expected values are identical. Together these produce systematic preference reversals across logically equivalent presentations.

### Applicability Conditions

- A decision is being presented and the wording or numerical format could plausibly bias the outcome.
- Multiple presentations of the same information are possible (gain vs. loss, absolute vs. relative, survival vs. mortality).
- The decision-maker has not already encountered both frames.
- The decision is high-stakes enough that frame-driven distortion would be costly.

### Common Misapplications

- Assuming any preference change between frames indicates pure bias, when in fact some frame differences carry genuine information (e.g., absolute numbers reveal magnitudes that percentages hide).
- Using the lens to dismiss any persuasive framing as manipulation, when in fact deliberate frame choice is also a legitimate communication tool when ethically applied.

### Related Models

- **Loss Aversion** — the underlying mechanism in gain/loss framing.
- **Anchoring** — adjacent reference-point manipulation through numerical anchors.
- **Choice Architecture (Thaler-Sunstein)** — the engineering discipline that uses framing intentionally.

## Application Steps

1. Restate the decision in at least two frames — gain vs. loss, absolute vs. relative, survival vs. mortality.
2. Check whether your preference changes between frames; if it does, the frame is doing the deciding.
3. Strip the frame: convert to a neutral representation (expected value, base rates, absolute numbers) and decide from there.
4. When communicating, choose the frame deliberately and ethically — know that you are influencing the outcome.
5. In group decisions, present both frames and force the group to reconcile any preference shift.

## Detection Signals

- The same data appears in different presentations producing different conclusions.
- A proposal sounds dramatically better or worse depending on which numbers are highlighted.
- Marketing, public health messaging, or policy communication is being designed and uptake will depend on framing.
- Two people disagree about the same data — they may be looking at different frames.
- The decision-maker's preference has shifted after a re-presentation of the same information.

## Critical Questions

- Has the decision been restated in at least two frames, or has only one been considered?
- When the preference changed between frames, was the change driven by frame distortion or by genuinely new salient information that one frame surfaced?
- Has the neutral-representation strip-down been completed, or has the analysis stopped at frame comparison?
- In communication design, is the chosen frame ethically defensible (informing without manipulating), or is it extractive?

## Common Failure Modes

- **Single-frame reasoning** — Detection signal: the decision is made without testing alternative frames. Correction: require at least two frames before commitment.
- **Strip-without-replacement** — Detection signal: the analyst dismisses framed presentations but offers no neutral representation. Correction: provide expected values, base rates, or absolute numbers as the neutral baseline.
- **Manipulation framing of all framing** — Detection signal: the lens is invoked to indict any deliberate frame choice. Correction: distinguish ethical informing-frames from extractive manipulation-frames; both exist.

## Source Citations

- Tversky, Amos and Daniel Kahneman (1981). The framing of decisions and the psychology of choice. *Science* 211(4481):453-458.
- Kahneman, Daniel and Amos Tversky (1979). Prospect theory: An analysis of decision under risk. *Econometrica* 47(2):263-291.
- Levin, Irwin P., Sandra L. Schneider, and Gary J. Gaeth (1998). All frames are not created equal: A typology and critical analysis of framing effects. *Organizational Behavior and Human Decision Processes* 76(2):149-188.
