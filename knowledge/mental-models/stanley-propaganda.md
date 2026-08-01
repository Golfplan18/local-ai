---
lens_id: stanley-propaganda
name: Stanley Propaganda
lens_type: mental-model
applicability: [propaganda-audit]
foundational: true
source: "Stanley, Jason (2015). How Propaganda Works. Princeton University Press. Stanley, Jason (2018). How Fascism Works: The Politics of Us and Them. Random House."
date created: 2026-05-01
date modified: 2026-05-01
nexus:
  - ora
type: resource
tags:
  - lens
  - mental-model
  - propaganda
  - political-philosophy
---

# Stanley Propaganda

## Trigger

Invoked from within `propaganda-audit` (T1) when that mode needs Stanley's distinction between supporting and undermining propaganda, the flawed-ideology mechanism by which undermining propaganda achieves its effect, and the diagnostic protocol for identifying propagandistic moves in an artifact even when those moves are not explicit lies. The host mode supplies the artifact (speech, document, advertisement, policy text); the lens supplies the conceptual apparatus distinguishing legitimate persuasion from undermining propaganda and the diagnostic questions that surface concept-substitution, ideological exploitation, and the use of democratic vocabulary against democratic content.

## Core Structure

### Core Insight

Propaganda is not best characterized as lying or as overt manipulation. The most powerful propaganda works by *appearing* to argue for a goal — often a goal couched in democratic, liberal, or otherwise widely-endorsed vocabulary — while actually undermining the conditions for the kind of public reasoning that the vocabulary presupposes. Stanley distinguishes *supporting propaganda* (which advances a goal by methods consistent with the ideals the goal invokes) from *undermining propaganda* (which advances a goal by methods that erode the very ideals the goal invokes). Undermining propaganda is the more dangerous form because its diagnosis requires examining the conditions for reasoning, not just the propositional content of the propagandistic claim.

### Mechanism

The mechanism by which undermining propaganda achieves its effect, in Stanley's account, is *flawed ideology*. A flawed ideology is a body of beliefs an audience already holds, often unconsciously, that systematically distorts the audience's perception or reasoning about a domain. When the propagandist constructs a message that activates the flawed ideology, the message does not need to assert the ideology's content explicitly — the audience supplies that content from the existing belief structure. The propagandist needs only to deliver an utterance that, in conjunction with the audience's prior beliefs, produces the desired conclusion. This is why propaganda often appears innocuous to audiences who do not share the activated ideology and devastating to those who do: the work is being done by the audience, not (visibly) by the message.

The slogan that captures this mechanism: *you don't have to lie if the audience already has the flawed belief*. A speech that invokes "law and order" need not assert that any particular group is criminal; if the audience holds a flawed ideology associating that group with criminality, the inference is supplied automatically. The propagandist has not lied; the propagandist has activated the flawed belief in service of a political goal. The deniability is built into the mechanism — the propagandist can disclaim any racist content because none was stated, while reaping the political benefit of the activated association.

A second characteristic move of undermining propaganda is *concept substitution*. The propagandist takes a term whose received meaning carries normative weight (freedom, democracy, justice, security) and uses it in a way that substitutes a different (often opposing) content while retaining the term's normative endorsement. "Freedom" comes to mean freedom from regulation that protects others; "democracy" comes to mean rule by the propagandist's faction even when that faction lacks majority support; "security" comes to mean the suppression of dissent. The substitution is rarely defended as such — the new content is asserted as if it were the term's straightforward meaning. Concept substitution is undermining propaganda's principal mechanism for using democratic vocabulary against democratic content.

A third characteristic move is the *exploitation of pre-existing in-group/out-group structure*. Stanley's later work (*How Fascism Works*) emphasizes that fascist propaganda activates and intensifies pre-existing group hierarchies rather than creating them de novo. The hierarchies provide the ready-made flawed ideology the propagandist activates. This places ideology critique (identifying which flawed ideologies are present in the audience) as the prerequisite for propaganda audit (identifying how the artifact activates them).

The status of Stanley's theory is itself debated within political philosophy. Critics ask whether the supporting/undermining distinction is symmetric — whether the same diagnostic apparatus applies to political artifacts on the left as on the right (Stanley's worked examples are predominantly drawn from the right) — and whether the theory is descriptively neutral or itself politically directional. This is debate D5 in the Phase 5b architectural materials and surfaces here as a critical question. The lens is applied as a diagnostic apparatus regardless of the political directionality debate; the audit's verdict depends on the artifact's structure, not on the artifact's political alignment.

### Applicability Conditions

- The artifact uses normatively-loaded vocabulary (freedom, democracy, justice, security, equality, fairness, family, community, etc.) in a way that may not match the term's received meaning.
- The artifact appears to argue for a widely-endorsed goal but its supporting arguments are not visible — the audience seems to be supplying the inferential connection.
- The artifact relies on activating audience associations (with groups, with practices, with historical events) rather than on explicit propositional claims.
- The host mode is `propaganda-audit` and explicitly invokes this lens.
- The analyst notices that an artifact's persuasive force is disproportionate to its explicit content — a sign that the audience's prior beliefs are doing significant work.

### Common Misapplications

- Treating all persuasion as propaganda. Stanley distinguishes propaganda from legitimate persuasion; collapsing the distinction makes the apparatus useless.
- Treating supporting propaganda as automatically illegitimate. Supporting propaganda — speech that advances a goal by methods consistent with the invoked ideals — is part of normal political life; the apparatus targets undermining propaganda specifically.
- Identifying flawed ideology by analyst preference rather than by audience analysis. The flawed ideology that matters is the one the audience holds, not the one the analyst objects to. An audit grounded in the analyst's ideology critique applied to an audience that does not share it misidentifies the propagandistic mechanism.
- Treating the supporting/undermining distinction as symmetric across political alignments without examining the empirical question. The apparatus may apply symmetrically; the claim that it does requires demonstration in each case.
- Reducing concept substitution to ordinary semantic drift. Concepts evolve; not all evolution is propagandistic substitution. The diagnostic requires evidence that the substitution is doing political work and is being defended (or hidden) by appeal to the term's older normative endorsement.

### Related Models

- **Lakoff conceptual metaphor** — metaphorical mappings often supply the flawed ideology that propaganda activates; concept substitution often runs through metaphor shift.
- **Walton schemes** — appeal to popular opinion, ad hominem, slippery slope, and ad ignorantiam are the surface-level argumentative moves through which propagandistic content is often delivered; Walton's apparatus catches the moves, Stanley's catches the mechanism.
- **Cappelen-Plunkett conceptual engineering** — concept substitution can be analyzed as engineering done in bad faith (proposing a revision while pretending to describe current usage); the engineering apparatus and the propaganda apparatus diagnose the same kind of move from different angles.
- **Frame analysis (Goffman, Entman)** — propaganda often works at the frame level; a propagandistic frame activates the flawed ideology more effectively than any propositional claim.
- **Toulmin model** — undermining propaganda often features a vacant warrant — the inferential rule from grounds to claim is missing because the audience supplies it from prior belief; Toulmin's audit surfaces the gap.

## Application Steps

1. Receive the artifact from the host mode.
2. Identify the goal the artifact appears to advance and the vocabulary in which the goal is stated.
3. Test for concept substitution: does the artifact use normatively-loaded terms in a way that diverges from received meaning while retaining the term's normative endorsement? List each substitution found.
4. Test for flawed-ideology activation: identify the audience the artifact addresses; identify what flawed ideologies that audience plausibly holds; identify whether the artifact activates those ideologies through associations, juxtapositions, or vocabulary choice rather than through explicit claims.
5. Test for in-group/out-group exploitation: does the artifact intensify pre-existing group hierarchies in ways that supply the audience with conclusions the artifact does not explicitly state?
6. Distinguish supporting from undermining propaganda: does the artifact's method of advancing its goal preserve or erode the conditions for the kind of reasoning the goal's vocabulary presupposes?
7. Return the audit (concept substitutions, flawed-ideology activations, in-group/out-group exploitations, and supporting-vs-undermining verdict) to the host mode, with the directionality caveat (debate D5) noted where relevant.

## Detection Signals

- The artifact's persuasive force is disproportionate to its explicit content.
- Normatively-loaded vocabulary is being used in unusual ways while retaining normative endorsement.
- The artifact addresses an audience whose prior beliefs about a group or domain are doing inferential work the artifact does not explicitly perform.
- The artifact's defenders disclaim conclusions the audience nonetheless reliably draws.
- The artifact uses democratic vocabulary in support of conclusions that erode democratic conditions.
- The host mode is `propaganda-audit`.

## Critical Questions

- Does the artifact rely on flawed ideology that need not be stated? If yes, the mechanism is the activation of audience belief; the propagandistic move is the activation, not any explicit assertion.
- Does the artifact use democratic vocabulary against democratic content? If yes, the mechanism is concept substitution in the service of undermining the conditions the vocabulary presupposes.
- Is concept substitution at work — terms used in a sense that diverges from received meaning while trading on the received meaning's normative endorsement? Identify each substitution and the work it does.
- Is the flawed ideology being identified empirically (as a belief structure the audience actually holds) or is the analyst importing ideology critique the audience does not share? Audit verdicts grounded in the latter mistake the propagandistic mechanism.
- Does the supporting/undermining distinction apply symmetrically across political alignments in this case (debate D5)? The apparatus is applied as a diagnostic regardless of alignment; the directionality question is surfaced as a separate concern about the theory's neutrality, not as a defeater of the audit's structural findings.
- Has the audit distinguished propaganda from legitimate persuasion? Conflating the two makes the apparatus useless; the distinction is whether the methods preserve or erode the conditions for the kind of reasoning the invoked ideals presuppose.

## Common Failure Modes

- **Universal-propaganda inflation** — treating all persuasion as propaganda. Detection: the audit verdict is "propaganda" regardless of the artifact's structure. Correction: apply the supporting/undermining distinction; reserve "propaganda" for moves that erode the conditions for the kind of reasoning their vocabulary presupposes; ordinary persuasion that respects those conditions is not propaganda in Stanley's sense.
- **Analyst-ideology import** — identifying flawed ideology by analyst preference rather than by audience belief. Detection: the audit names ideologies the audience does not hold and ignores ideologies it does. Correction: identify the audience first; identify the audience's actual belief structure (through prior research, polling data, ethnography, or analytical inference from the artifact's audience-design); ground the flawed-ideology claim in audience belief, not analyst objection.
- **Directionality blindness** — applying the apparatus only to artifacts on one political side. Detection: the audit's worked examples cluster suspiciously on one alignment. Correction: surface debate D5 explicitly; apply the structural diagnostic to candidate artifacts regardless of alignment; report what the diagnostic finds.
- **Substitution overreach** — treating ordinary semantic evolution as concept substitution. Detection: the substitution claim cannot be cashed out in the term doing political work and being defended by appeal to the older endorsement. Correction: require evidence that the substitution is propagandistic (doing political work, hiding behind older normative weight), not merely linguistic (terms drift naturally).
- **Mechanism-blind classification** — classifying an artifact as propaganda based on its conclusion rather than its mechanism. Detection: the audit's verdict tracks the analyst's evaluation of the conclusion rather than the artifact's method. Correction: ground the verdict in the artifact's structural features (concept substitution, flawed-ideology activation, undermining of reasoning conditions), not in agreement or disagreement with what the artifact advocates.

## Source Citations

- Stanley, Jason (2015). *How Propaganda Works*. Princeton University Press. The book-length development of the supporting/undermining distinction and the flawed-ideology mechanism.
- Stanley, Jason (2018). *How Fascism Works: The Politics of Us and Them*. Random House. Extended application to fascist propaganda specifically; foregrounds the in-group/out-group exploitation mechanism.
- Stanley, Jason (2011). *Knowledge and Practical Interests*. Oxford University Press. Earlier work on the epistemic conditions the propaganda theory presupposes.
- Bernays, Edward L. (1928). *Propaganda*. Horace Liveright. The historical-foundational text from which Stanley's theoretical apparatus departs.
- Ellul, Jacques (1962/1965). *Propaganda: The Formation of Men's Attitudes*. Knopf. Influential European theoretical treatment with which Stanley engages indirectly.
- Herman, Edward S., and Noam Chomsky (1988). *Manufacturing Consent: The Political Economy of the Mass Media*. Pantheon. Structural-political-economic propaganda theory; complementary apparatus operating at the institutional level.
- Khoo, Justin (2017). "Code words in political discourse." *Philosophical Topics* 45(2):33-64. Direct engagement with Stanley's concept-substitution mechanism.
- Mendelberg, Tali (2001). *The Race Card: Campaign Strategy, Implicit Messages, and the Norm of Equality*. Princeton University Press. Empirical political science on flawed-ideology activation in U.S. campaign discourse.
- Related: Lakoff conceptual metaphor (the cognitive infrastructure propaganda often activates); Walton schemes (the dialectical surface of propagandistic moves); Cappelen-Plunkett conceptual engineering (the bad-faith engineering counterpart to good-faith engineering).
