---
lens_id: walton-schemes-and-critical-questions
name: Walton Schemes and Critical Questions
lens_type: argumentation-scheme
applicability: [coherence-audit, frame-audit, argument-audit, propaganda-audit, competing-hypotheses, steelman-construction]
foundational: true
source: "Walton, Douglas, Chris Reed, and Fabrizio Macagno (2008). Argumentation Schemes. Cambridge University Press."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - argumentation-scheme
  - argumentation
---

# Walton Schemes and Critical Questions

## Trigger

Invoked from within `coherence-audit`, `frame-audit`, `argument-audit`, and `propaganda-audit` (T1) when those modes need a structured catalog of presumptive argument forms and their defeasibility conditions to classify and audit a piece of reasoning. Also invoked by `competing-hypotheses` (T5) when the analyst must score how well each hypothesis is supported by source-based or causal arguments, and by `steelman-construction` (T15) when a charitable reconstruction must conform to a recognized argument scheme rather than a reconstructed strawman. The host mode supplies an argument or claim; the lens supplies the named scheme it instantiates and the critical questions whose negative answers defeat it.

## Core Structure

A presumptive argument scheme is an argument form that is defeasibly valid: when its premise pattern is satisfied, the conclusion is plausibly supported, but the conclusion can be defeated by a negative answer to any of the scheme's critical questions. The catalog below covers the eleven highest-frequency schemes. Each row gives the scheme's name, the abstract premise pattern, the conclusion pattern, and the critical questions specific to that scheme. The schemes are grouped by family.

### Source-Based Schemes

| Scheme | Premise pattern | Conclusion pattern | Critical questions |
|---|---|---|---|
| Argument from Expert Opinion | E is an expert in domain D; E asserts that A is true; A is in D. | A is plausibly true. | (1) Is E a genuine expert in D? (2) Did E actually assert A? (3) Is A within D? (4) Is E reliable and free of conflicts of interest? (5) Do other experts agree? (6) Is the assertion grounded in evidence E can produce? |
| Argument from Position to Know | P is in a position to know about A (was present, has access, holds the role); P asserts A. | A is plausibly true. | (1) Is P actually in the position claimed? (2) Is P an honest source? (3) Did P actually assert A in the form reported? |
| Argument from Popular Opinion | A large majority of relevant people accept A. | A is plausibly true. | (1) Is the popular acceptance accurately reported? (2) Is the relevant population the right one for the question? (3) Is there independent evidence that the popular view tracks truth here, or is it a domain where popular opinion is a poor guide (specialized science, novel events, manipulated information environments)? |
| Argument from Commitment | At an earlier time, P committed to A; the present situation is relevantly similar. | P is committed to A now. | (1) Did P actually make the commitment? (2) Is the present situation relevantly similar? (3) Has P explicitly retracted the commitment? (4) Are there overriding considerations that release P from the commitment? |

### Causal and Sign Schemes

| Scheme | Premise pattern | Conclusion pattern | Critical questions |
|---|---|---|---|
| Argument from Cause to Effect | Generally, cause C produces effect E; C occurred (or will occur) in this case. | E occurred (or will occur). | (1) Is the causal generalization well-established? (2) Are there relevant intervening or counteracting causes? (3) Are the conditions in this case those under which the generalization holds? (4) Is the inference being run forward (predicting E from C) or backward (inferring C from E), and is that direction warranted? |
| Argument from Sign | Observation O is typically a sign of state-of-affairs S; O is observed. | S is plausibly the case. | (1) Is O really a reliable sign of S? (2) Are there alternative states that would also produce O? (3) Could O be produced by manipulation rather than by the genuine underlying state? |
| Slippery Slope | Action A initiates a sequence in which subsequent steps lead to outcome Z; Z is undesirable. | A should not be done. | (1) Is each step in the sequence actually likely to follow from the previous one? (2) Are there points in the chain where the sequence can be halted? (3) Is the eventual outcome Z genuinely undesirable, or is its undesirability assumed? (4) Is the slope being described as causal, logical, or sociological — and is that the right characterization? |

### Schemes Targeting Persons and Knowledge

| Scheme | Premise pattern | Conclusion pattern | Critical questions |
|---|---|---|---|
| Ad Hominem | P has bad character (or bad motives, or has acted badly); P asserts A. | A should be doubted. | (1) Is the character claim about P accurate? (2) Is the character defect relevant to the credibility of A? (3) Is there independent evidence about A that bypasses the appeal to P's character? (4) Is the attack targeting the person to deflect from the claim's substance (a fallacious move) or genuinely raising a credibility concern (a legitimate move)? |
| Argument from Analogy | Case C1 has properties P1, P2, ..., Pn and outcome O; case C2 has properties P1, P2, ..., Pn. | C2 plausibly has outcome O. | (1) Are C1 and C2 actually similar in the properties P1-Pn? (2) Are there relevant disanalogies that would block the inference? (3) Is the outcome O in C1 actually produced by the properties P1-Pn, or by something else not present in C2? |
| Argument from Ignorance | Proposition A has not been proven false (or no evidence against A has been produced). | A is plausibly true. | (1) Has there been a serious effort to find evidence against A? (2) In a domain where evidence-of-absence is reasonable to expect (well-studied, accessible), absence is meaningful; in a domain where it is not, the inference is weak. Which domain are we in? (3) Is the burden of proof properly allocated? In some contexts (e.g., criminal law), absence of disconfirming evidence supports the presumption; in others (e.g., scientific claims about unobserved phenomena), it does not. |

### Practical Reasoning

| Scheme | Premise pattern | Conclusion pattern | Critical questions |
|---|---|---|---|
| Practical Reasoning | Agent A has goal G; doing M is a means to G; A is in a position to do M. | A should do M. | (1) Are there alternative means to G besides M? (2) Are the alternatives more efficient, less costly, or less risky? (3) Does doing M have side-effects that defeat the goal or produce other goals worth more than G? (4) Is G itself the right goal, or is it a proxy for a deeper goal that other means would serve better? |

## Application Steps

1. Receive the argument or claim from the host mode.
2. Identify which named scheme(s) it instantiates by matching its premise and conclusion pattern to the rows above.
3. List the critical questions specific to that scheme.
4. Audit the argument by checking each critical question against the available evidence; mark each as supported, defeated, or unaddressed.
5. Return the scheme classification, the per-question audit, and the overall verdict (presumptively supported, defeated, or under-determined) to the host mode.

## Detection Signals

- An argument is being made that fits a recognizable presumptive form (someone cites an expert, draws an analogy, predicts a slope, etc.).
- The host mode needs to test an argument's strength rather than just summarize its content.
- A propaganda or framing artifact is invoking authority, popular opinion, or character claims and the analyst must locate the precise scheme to surface its defeasibility.
- A steelman construction is being prepared and the analyst needs to confirm the reconstructed argument fits a recognized scheme rather than a strawman.
- Mid-analysis, the analyst notices that an argument's conclusion is being treated as established when its premises only support it presumptively.

## Critical Questions

- Has the argument been classified to the right scheme? Misclassifying an argument from sign as an argument from cause to effect imports the wrong critical-question set and produces a misleading audit.
- Are the critical questions being applied to the actual premises in the argument, not to the analyst's reconstruction? An audit that defeats a steelmanned premise the arguer never offered is not a valid defeat.
- Is the scheme being treated as defeasible (presumptive) rather than as deductive? Treating a presumptive scheme as deductive invents fallacies where none exist; treating a deductive argument as presumptive invents legitimate doubts where none exist.
- Are unaddressed critical questions distinguished from defeated ones? An argument with unaddressed critical questions is under-determined, not refuted; the audit must mark this distinction clearly.
- Has the audit considered whether the argument is stacked from multiple schemes (cumulative case)? Arguments in practice often combine schemes (expert opinion plus sign plus analogy); the audit must address each component and the cumulative effect.

## Common Failure Modes

- **Scheme miscategorization** — assigning the argument to the wrong named scheme. Detection: the critical questions feel off-target or trivially satisfied/unsatisfied. Correction: re-read the argument and match its premise pattern more carefully; consult adjacent schemes in the same family.
- **Strawman reconstruction** — auditing a reconstructed argument the arguer did not make. Detection: the arguer would not recognize the form being audited as their argument. Correction: quote the original premises verbatim before classifying; run steelman construction first if the argument is fragmentary.
- **Defeasibility collapse** — treating an unaddressed critical question as a defeated one. Detection: the audit conclusion claims refutation but the questions actually flag absence of evidence on certain conditions. Correction: distinguish "premise-not-satisfied" (defeat) from "evidence-on-condition-not-supplied" (under-determination); report both states separately.
- **Cumulative-case blindness** — auditing each component of a multi-scheme argument in isolation and missing the strength of their conjunction. Detection: each component is rated weak, but the overall argument is intuitively strong. Correction: after per-component audit, assess whether the components are independent and whether their conjunction raises the conclusion's plausibility above any single component.
- **Authority confusion** — treating Argument from Expert Opinion and Argument from Position to Know as interchangeable. Detection: the audit applies expertise critical questions (E's domain) to a witness (P's location/role) or vice versa. Correction: distinguish expertise (knowledge of a domain) from position-to-know (access to a particular fact) and apply the matched critical-question set.

## Source Citations

- Walton, Douglas, Chris Reed, and Fabrizio Macagno (2008). *Argumentation Schemes*. Cambridge University Press. The canonical compendium of ~60 schemes with critical questions.
- Walton, Douglas (1996). *Argumentation Schemes for Presumptive Reasoning*. Lawrence Erlbaum. Earlier monograph establishing the presumptive-reasoning frame.
- Walton, Douglas (1995). *A Pragmatic Theory of Fallacy*. University of Alabama Press. The dialectical theory in which schemes and critical questions are situated.
- Macagno, Fabrizio, and Douglas Walton (2014). *Emotive Language in Argumentation*. Cambridge University Press. Extension to schemes involving emotive and value-laden language.
- Related: Toulmin model (claim/grounds/warrant/backing/qualifier/rebuttal — a complementary framework for analyzing single arguments rather than classifying argument types).
