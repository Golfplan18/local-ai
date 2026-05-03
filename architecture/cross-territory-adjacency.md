# Reference — Cross-Territory Adjacency

This file documents the cross-territory disambiguation patterns consulted by Stage 1 of the pre-routing pipeline (filter and territory identification) and by Stage 2 (sufficiency analyzer) when a prompt's signals straddle two territories. For every adjacent territory pair (or triplet), it specifies why the territories sit close, the single plain-language question that distinguishes them, the routing rule for each plausible answer, paired prompt examples, and — where a prompt legitimately fits both — the sequential-dispatch order. Within-territory disambiguation (choosing among modes inside a single territory) is a separate concern and lives in `Reference — Within-Territory Disambiguation Trees.md`.

---

### T1 ↔ T2 (Argumentative Artifact ↔ Interest and Power)

**Why adjacent.** Both can take a published article, op-ed, memo, or stated position as input. The same artifact can be evaluated for whether the argument holds up (T1) or for whose interests are served if people accept it (T2).

**Disambiguating question.** "Are you mostly asking whether the argument itself holds up, or who benefits if people accept it?"

**Routing.**
- Argument-soundness focus → T1 (Coherence Audit / Frame Audit / Argument Audit / Propaganda Audit).
- Interest-pattern focus → T2 (Cui Bono / Boundary Critique / Wicked Problems / Decision Clarity).
- Both → sequential dispatch: T1 first, then T2.

**Examples.**
- *"Is this op-ed on housing policy rigorous?"* → T1.
- *"Whose interests does this op-ed actually serve?"* → T2.
- *"Walk me through whether this argument holds up and also who's behind it."* → T1 + T2 (sequential, T1 first).
- *"This think-tank brief recommends X — is it well-argued, or is it just dressing up someone's agenda?"* → T1 + T2 (sequential, T1 first).

**Sequential dispatch note.** When both fire, T1 runs first because argument-soundness is the lighter, foundational evaluation; T2 then layers interest-pattern analysis on top of an artifact whose internal structure has already been characterized.

### T1 ↔ T5 (Argumentative Artifact ↔ Hypothesis Evaluation)

**Why adjacent.** Competing positions in a debate can be treated either as full arguments-as-artifacts to be audited (T1) or as propositions to be weighed against evidence (T5). The surface form — "two positions, which one wins" — looks similar.

**Disambiguating question.** "Are the competing positions each a complete argument you want me to audit, or are they propositions you want weighed against evidence?"

**Routing.**
- Argument-as-artifact (each side is itself a structured argument to evaluate internally) → T1 (Argument Audit on each).
- Proposition-against-evidence (each side is a candidate explanation) → T5 (Differential Diagnosis / Competing Hypotheses / Bayesian Hypothesis Network).

**Examples.**
- *"Two op-eds disagree about minimum wage — which has the stronger argument?"* → T1 (audit each).
- *"Two explanations for the company's revenue dip — which fits the evidence better?"* → T5 (ACH or differential).
- *"Critics offer three frames for what went wrong; help me evaluate them."* → If frames are full arguments → T1; if they are causal hypotheses → T5.

### T1 ↔ T9 (Argumentative Artifact ↔ Paradigm and Assumption Examination)

**Why adjacent.** Both engage with frames. T1's Frame Audit operates on a single artifact's frame; T9 operates on the comparison or examination of paradigms across artifacts or positions.

**Disambiguating question.** "Are you evaluating this single argument's frame, or comparing different paradigms that frame the issue differently?"

**Routing.**
- Single-artifact frame surfacing → T1 (Frame Audit).
- Multi-paradigm comparison or examination → T9 (Paradigm Suspension / Frame Comparison / Worldview Cartography).

**Examples.**
- *"What frame is this article smuggling in?"* → T1 (Frame Audit on the single article).
- *"How do progressives and conservatives frame this issue differently?"* → T9 (Frame Comparison).
- *"Map the major worldviews in this debate."* → T9 (Worldview Cartography).

### T1 ↔ T10 (Argumentative Artifact ↔ Conceptual Clarification)

**Why adjacent.** When an argument hinges on a contested concept, the same prompt can be heard as either "audit the argument" (T1) or "clarify the concept first" (T10).

**Disambiguating question.** "Is the issue with how the argument deploys a specific concept (clarify the concept first), or with how the argument coheres given any reasonable reading of the concept?"

**Routing.**
- Concept-precision issue (the argument trades on definitional slippage) → T10 (Deep Clarification / Conceptual Engineering).
- Argument-coherence issue (the argument has structural problems regardless of how the concept is read) → T1 (Coherence Audit / Argument Audit).

**Examples.**
- *"What does the author even mean by 'freedom' here?"* → T10.
- *"Does the author's argument actually follow from their premises?"* → T1.
- *"The whole piece rests on 'merit' — is that doing real work?"* → T10 first, then optionally T1.

**Sequential dispatch note.** When concept clarification is needed before argument audit can proceed, T10 runs first; T1 follows on the now-clarified version.

### T1 ↔ T15 (Argumentative Artifact ↔ Artifact Evaluation by Stance — Steelman cross-territory case)

**Why adjacent.** Both can evaluate an argument. T1 evaluates the argument *as an argument* for soundness; T15 evaluates it *as a proposal* by adopting a defined stance (steelman / push back / weigh both). The Steelman mode is the canonical cross-territory case.

**Disambiguating question.** "Want me to evaluate the argument's *soundness* (does it hold up?), or *evaluate the proposal* with a particular stance (steelman / push back / weigh both)?"

**Routing.**
- Soundness evaluation → T1 (Coherence Audit / Frame Audit / Argument Audit).
- Stance-bearing evaluation → T15 (Steelman Construction / Benefits Analysis / Balanced Critique / Red Team).

**Steelman cross-territory disposition (per Decision G).** Steelman's home is T15 (its primary work is stance-bearing artifact evaluation — constructing the strongest version of a proposal). When the artifact under steelmanning is itself an argument, the T1 cross-reference activates so that argument-coherence considerations inform the steelmanned reconstruction. The mode is *not* dual-citizened — home is T15; T1 is consulted as cross-reference.

**Examples.**
- *"Does this argument hold up?"* → T1.
- *"Steelman this proposal — make the strongest version of it."* → T15.
- *"Steelman this argument."* → T15 (home), with T1 cross-reference active because the artifact is an argument.
- *"Push back hard on this plan."* → T15 (Red Team or Balanced Critique).
- *"Weigh both sides of this proposal."* → T15 (Balanced Critique).

### T2 ↔ T8 (Interest and Power ↔ Stakeholder Conflict)

**Why adjacent.** Both involve multiple parties whose interests diverge. T2 asks who benefits and who has power; T8 asks how the conflict among parties is structured and what integrative possibilities exist.

**Disambiguating question.** "Mostly asking who benefits or has power, or asking how the parties' competing claims can be worked through?"

**Routing.**
- Power/interest analysis → T2 (Cui Bono / Boundary Critique / Wicked Problems / Decision Clarity).
- Conflict structure → T8 (Stakeholder Mapping / Conflict Structure).

**Examples.**
- *"Whose interests are being served by this zoning policy?"* → T2.
- *"Who are all the stakeholders in this dispute and how do their positions map?"* → T8.
- *"Three parties want different things — what's the underlying interest landscape, and how do their positions relate?"* → T2 + T8 (sequential, T2 first when interest analysis grounds the conflict structure).

**Sequential dispatch note.** When both fire, T2 typically runs first because interest analysis grounds the descriptive conflict mapping that T8 produces.

### T2 ↔ T13 (Interest and Power ↔ Negotiation and Conflict Resolution)

**Why adjacent.** Both engage with multi-party situations. T2 maps the interest landscape descriptively; T13 produces guidance for active negotiation or mediation.

**Disambiguating question.** "Are you mapping the interest landscape, or are you about to negotiate (or advise a negotiation)?"

**Routing.**
- Mapping → T2 (Cui Bono / Boundary Critique / etc.).
- Active negotiation guidance → T13 (Interest Mapping / Principled Negotiation / Third-Side).

**Examples.**
- *"Who has power in this negotiation and what do they want?"* → T2.
- *"I'm walking into this negotiation tomorrow — help me think through interests and BATNA."* → T13.
- *"As a mediator, how should I structure this conflict?"* → T13 (Third-Side).

### T3 ↔ T6 (Decision-Making Under Uncertainty ↔ Future Exploration)

**Why adjacent.** Decisions are forward-looking and engage uncertainty about future states; future exploration sometimes serves a pending decision. The two can blur when the decision is inseparable from how the future might unfold.

**Disambiguating question.** "Are you choosing among options now, or exploring how the future might unfold (irrespective of what you do)?"

**Routing.**
- Choice-now (alternatives, criteria, constraints) → T3 (Constraint Mapping / Decision Under Uncertainty / Multi-Criteria Decision / Decision Architecture).
- Future-shape (scenarios, projections, possibility-spaces) → T6 (Consequences and Sequel / Probabilistic Forecasting / Scenario Planning / Wicked Future).

**Examples.**
- *"Should I take this job offer or stay where I am?"* → T3.
- *"What does the next decade of remote work look like?"* → T6.
- *"I'm deciding whether to invest in this market — paint me the scenarios first, then we'll choose."* → T6 + T3 (sequential, T6 first to map the possibility space, T3 to choose).

**Sequential dispatch note.** When the future must be explored before the decision can be framed, T6 runs first; T3 then operates on the scenarios T6 produces.

### T3 ↔ T7 (Decision-Making Under Uncertainty ↔ Risk and Failure Analysis)

**Why adjacent.** Decisions involve risk as one input; risk analysis sometimes serves a pending decision. The disambiguator is whether the user wants a balanced choice procedure or a focused failure investigation.

**Disambiguating question.** "Choosing among options where risk is one input among several, or specifically stress-testing how things could fail?"

**Routing.**
- Multi-input choice → T3 (Decision Under Uncertainty / Multi-Criteria Decision / etc.).
- Failure-focused → T7 (Pre-Mortem Fragility / Fragility-Antifragility Audit / Failure Mode Scan / Fault Tree).

**Examples.**
- *"Should we launch in Q3 or Q4 — risk is a factor."* → T3.
- *"Stress-test our launch plan — what could break it?"* → T7.
- *"What are the worst-case scenarios for this strategy?"* → T7 (Fragility) or T6 (Wicked Future) depending on scope.

### T3 ↔ T8 (Decision-Making Under Uncertainty ↔ Stakeholder Conflict)

**Why adjacent.** Decisions sometimes involve multiple parties. The disambiguator is whether the user owns the decision (parties as inputs) or whether the parties' conflict itself is the analytical object.

**Disambiguating question.** "Is this fundamentally your decision to make (with the parties as inputs), or is it a situation where the parties' conflict itself is what needs to be worked through first?"

**Routing.**
- Your-decision → T3 (Decision Under Uncertainty / Multi-Criteria Decision / etc.).
- Parties'-conflict-first → T8 (Stakeholder Mapping / Conflict Structure).

**Examples.**
- *"My team wants A, my boss wants B, the client wants C — I have to decide."* → T3.
- *"My team wants A, my boss wants B, the client wants C — help me understand the conflict before I touch it."* → T8.
- *"The board is split three ways on the strategic direction — I need to make a call but I don't yet know how the positions even relate."* → T8 first, then T3.

**Sequential dispatch note.** When the conflict structure must be characterized before the decision can be framed, T8 runs first; T3 follows once the parties and their positions are mapped.

### T4 ↔ T9 (Causal Investigation ↔ Paradigm and Assumption Examination)

**Why adjacent.** Both ask "why" — but at different levels. T4 traces causes within the assumed frame; T9 asks whether the frame itself is generating the apparent problem.

**Disambiguating question.** "Looking for the causes within how the problem is currently framed, or stepping back to ask whether the framing itself is generating the problem?"

**Routing.**
- Within-frame → T4 (Root Cause Analysis / Systems Dynamics Causal / Causal DAG / Process Tracing).
- Frame-as-cause → T9 (Paradigm Suspension / Frame Comparison / Worldview Cartography), possibly with T4 follow-up.

**Examples.**
- *"Why does our hiring funnel keep narrowing?"* → T4 (within-frame).
- *"Why does every solution to this problem keep failing?"* → T9 (signal of frame-issue), possibly with T4 follow-up once the frame is reset.
- *"What's causing the engagement drop?"* → T4.
- *"Why do we keep having the same fight in different forms?"* → T9 (the recurrence pattern signals frame-as-cause).

### T4 ↔ T16 (Causal Investigation ↔ Mechanism Understanding)

**Why adjacent.** Both engage with how things produce outcomes. T4 traces backward from outcome to cause; T16 explains how the parts of a phenomenon work together to produce its behavior.

**Disambiguating question.** "Tracing back to causes, or explaining how the parts produce the behavior?"

**Routing.**
- Backward-to-causes → T4 (Root Cause Analysis / Systems Dynamics Causal / Causal DAG / Process Tracing).
- How-it-works → T16 (Mechanism Understanding).

**Examples.**
- *"Why did the rollout fail?"* → T4.
- *"How does this recommendation algorithm actually work?"* → T16.
- *"What caused the market shift?"* → T4.
- *"How does fiscal policy translate into household spending?"* → T16.

### T4 ↔ T17 (Causal Investigation ↔ Process and System Analysis)

**Why adjacent.** Both can engage with workflows or systems. T4 asks why a pattern recurs; T17 maps the process as it currently is, identifying components, flows, and bottlenecks.

**Disambiguating question.** "Why does this keep happening (causes), or how does this currently work (process map)?"

**Routing.**
- Causal investigation → T4 (Root Cause Analysis / Systems Dynamics Causal / etc.).
- Process mapping → T17 (Systems Dynamics Structural / Process Mapping / Organizational Structure).

**Examples.**
- *"Why does our deployment process keep producing outages?"* → T4.
- *"Walk me through our deployment process as it currently runs."* → T17.
- *"Map the workflow."* → T17.
- *"Why does the workflow keep stalling at the same step?"* → T4 (with T17 likely as upstream input).

**Sequential dispatch note.** When causal investigation requires a process map first (you can't ask why the workflow stalls without knowing what the workflow is), T17 runs first; T4 follows.

### T5 ↔ T9 (Hypothesis Evaluation ↔ Paradigm and Assumption Examination)

**Why adjacent.** Both engage with competing explanations. T5 weighs them within a shared frame; T9 asks whether the disagreement is really about how to see the issue rather than which proposition is true.

**Disambiguating question.** "Are you weighing competing explanations within a shared understanding of the problem, or are the explanations using such different frames that the disagreement is really about how to see the issue?"

**Routing.**
- Within-frame hypothesis comparison → T5 (Differential Diagnosis / Competing Hypotheses / Bayesian Hypothesis Network).
- Inter-frame disagreement → T9 (Frame Comparison / Worldview Cartography).

**Examples.**
- *"Three theories explain the data — which fits best?"* → T5.
- *"The economists and the sociologists disagree — but they're not even asking the same question."* → T9.
- *"Doctor A says it's X, doctor B says it's Y — same evidence."* → T5.
- *"Doctor A and the homeopath disagree — but they're operating from different paradigms entirely."* → T9.

### T6 ↔ T7 (Future Exploration ↔ Risk and Failure Analysis — Pre-Mortem parse)

**Why adjacent.** Both adopt an adversarial-future stance — imagining what could go wrong. The Pre-Mortem operation appears to fit both, but per Decision D's parsing principle the candidate mode is split rather than dual-citizened.

**Disposition per Decision D (parse, not dual citizenship).** Pre-Mortem is parsed into two modes that share the `klein-pre-mortem` lens but differ in operation:
- `pre-mortem-action` (T6): adversarial-future stance applied to *the action plan* — what could go wrong with this plan as it unfolds.
- `pre-mortem-fragility` (T7): adversarial-future stance applied to *the system or design* — what failure modes does this structure exhibit under stress.

**Disambiguating question.** "Is this about an action plan that could fail, or about a system or design with structural fragilities?"

**Routing.**
- Action-plan focus → T6 (Pre-Mortem Action).
- System-or-design fragility focus → T7 (Pre-Mortem Fragility).

**Examples.**
- *"We're launching this campaign next month — pre-mortem it."* → T6 (Pre-Mortem Action: the plan unfolds in time, what derails it).
- *"This architecture is going into production — pre-mortem it."* → T7 (Pre-Mortem Fragility: the system is structural, where does it break).
- *"Run a pre-mortem on this initiative."* → ambiguous; sufficiency analyzer asks whether the focus is the rollout (T6) or the design (T7).

### T7 ↔ T15 (Risk and Failure Analysis ↔ Artifact Evaluation by Stance — Red Team case)

**Why adjacent.** Both stress-test artifacts. T15's Red Team modes (`red-team-assessment` / `red-team-advocate` — both) model an adversarial actor trying to defeat the artifact; T7's Fragility Audit looks at structural weaknesses regardless of any actor.

**Disambiguating question.** "Adversarial-actor stress test (someone is trying to defeat this), or structural-fragility audit (where could this break under any pressure)?"

**Routing.**
- Actor-modeling → T15 (`red-team-assessment` / `red-team-advocate` — both). Within T15, secondary disambiguator: own-decision (assessment, default) vs external-use (advocate).
- Structural fragility → T7 (Pre-Mortem Fragility / Fragility-Antifragility Audit / Fault Tree).

**Examples.**
- *"How would a competitor attack this strategy?"* → T15 Red Team Assessment (own-decision framing).
- *"Where would this strategy break under market stress regardless of who's pushing on it?"* → T7 Fragility Audit.
- *"How would a hostile reviewer pick apart this paper?"* → T15 Red Team Assessment if the goal is to fix vulnerabilities before submission; Red Team Advocate if the goal is to prepare a brief against the paper for an actual hostile reviewer.
- *"What are the load-bearing assumptions in this paper that would crack first?"* → T7 Fragility Audit.

### T8 ↔ T13 (Stakeholder Conflict ↔ Negotiation and Conflict Resolution)

**Why adjacent.** Both engage with multi-party conflict situations. T8 is descriptive (mapping the conflict structure); T13 is active (guiding negotiation or mediation).

**Disambiguating question.** "Mapping the conflict structure, or guiding active negotiation?"

**Routing.**
- Mapping → T8 (Stakeholder Mapping / Conflict Structure).
- Active → T13 (Interest Mapping / Principled Negotiation / Third-Side).

**Examples.**
- *"Lay out who's on what side and why."* → T8.
- *"I'm sitting down with them tomorrow — help me prepare."* → T13.
- *"As mediator I need to understand the conflict before I intervene."* → T8 first, then T13.

**Sequential dispatch note.** When active negotiation guidance is needed but the conflict structure is not yet mapped, T8 runs first; T13 follows.

### T9 ↔ T12 (Paradigm and Assumption Examination ↔ Cross-Domain and Knowledge Synthesis)

**Why adjacent.** Both engage with multiple frames or knowledge bodies. T9 examines paradigms (suspending, comparing, critiquing them); T12 integrates across them.

**Disambiguating question.** "Stepping back to examine the paradigms, or integrating across paradigms?"

**Routing.**
- Examining → T9 (Paradigm Suspension / Frame Comparison / Worldview Cartography).
- Integrating → T12 (Synthesis / Dialectical Analysis / Cross-Domain Analogical).

**Examples.**
- *"Compare how economics and sociology frame this."* → T9.
- *"Integrate what economics and sociology each contribute here."* → T12.
- *"What worldview is each side bringing?"* → T9.
- *"Hold thesis and antithesis in productive tension."* → T12 (Dialectical Analysis).

### T11 ↔ T16 ↔ T17 (Mechanism / Process / Structure cluster)

**Why adjacent.** These three cluster tightly because they all engage with how something works internally — but they ask different questions about it. T16 asks how the gears interlock to produce behavior; T17 asks how the flow runs in sequence; T11 asks how the parts relate as a structure.

**Disambiguating question.** "Is the question about *how* this works (the gears), about the *flow or process* (sequence), or about how the *parts relate* (structure)?"

**Routing.**
- How → T16 (Mechanism Understanding).
- Flow → T17 (Systems Dynamics Structural / Process Mapping / Organizational Structure).
- Structure → T11 (Relationship Mapping / Spatial Reasoning).

**Examples.**
- *"How does this engine actually produce torque?"* → T16.
- *"Map the production workflow from raw material to finished product."* → T17.
- *"Show me how these departments relate to each other."* → T11.
- *"How does our org chart actually function — what's the real flow?"* → T17 (process focus) or T11 (structural focus) depending on whether the user wants the lived flow or the formal relations.
- *"How does the algorithm work, step by step?"* → T17 if procedural; T16 if the user wants the underlying mechanism.

**Sequential dispatch note.** When two of the three fire on the same input (e.g., "explain how this works and map who reports to whom"), the lighter framing typically runs first: T11 (structure) before T17 (process) before T16 (mechanism), because each successive territory builds on the prior.

### T11 ↔ T19 (Structural Relationship Mapping ↔ Spatial Composition)

**Why adjacent.** Same input — a diagram or visual artifact — answers different questions. T11 reads the diagram as notation: what relations are asserted among elements. T19 reads the diagram as composition: what the layout itself is doing.

**Disambiguating question.** "Is the question about what relations the diagram asserts among elements, or about what the layout or composition itself is doing?"

**Routing.**
- Relation-extraction (the diagram-as-notation) → T11 (Relationship Mapping / Spatial Reasoning).
- Layout-doing (the diagram-as-composition) → T19 (Compositional Dynamics / Ma Reading / Place Reading / Information Density).

**Examples.**
- *"What does this org chart say about reporting lines?"* → T11.
- *"What is this org chart's layout doing — why does it feel hierarchical even where the lines say it isn't?"* → T19.
- *"Read this network diagram for me — who's connected to whom?"* → T11.
- *"This network diagram is dense in the middle and sparse at the edges — what is that doing to the reader?"* → T19.
- *"Both: tell me what the diagram asserts and what the layout is doing."* → T11 + T19 (sequential, T11 first).

**Sequential dispatch note.** When both legitimately fire on the same input, T11 runs first because relation-extraction is the lighter, more determinate operation; T19 layers compositional reading on top of an artifact whose asserted relations have already been characterized.

### T14 ↔ T20 (Orientation in Unfamiliar Territory ↔ Open Exploration)

**Why adjacent.** Both engage with unfamiliar or open spaces. T14 is analytical — what's here, what's the lay of the land. T20 is generative — what could be, what opens up.

**Disambiguating question.** "Trying to orient in an unfamiliar space (what's here), or generating in an open space (what could be)?"

**Routing.**
- Orienting → T14 (Quick Orientation / Terrain Mapping / Domain Induction).
- Generating → T20 (Passion Exploration / Idea Development / Research Question Generation).

**Examples.**
- *"I'm new to this codebase — give me the lay of the land."* → T14.
- *"I'm interested in this area — help me explore where it might go."* → T20.
- *"What are the major positions in this field?"* → T14.
- *"What questions could I be asking here?"* → T20 (Research Question Generation).

### T19 ↔ T20 (Spatial Composition ↔ Open Exploration on aesthetic input)

**Why adjacent.** Aesthetic inputs (paintings, gardens, scenes) can be read analytically (T19 — defeasible operations on what the composition does) or explored open-endedly (T20 — what the work opens up for the viewer).

**Disambiguating question.** "Are you asking for analytical reading of the composition, or for open-ended exploration of what it opens up?"

**Routing.**
- Analytical reading → T19 (Compositional Dynamics / Ma Reading / Place Reading / Information Density).
- Open exploration → T20 (Passion Exploration / Idea Development).

**Examples.**
- *"Read this painting compositionally — what is the layout doing?"* → T19.
- *"This painting fascinates me — help me explore why."* → T20.
- *"Walk me through the gestalt of this image."* → T19.
- *"What does this scene open up for me?"* → T20.
- *"Both — read it and let me explore."* → T19 + T20 (sequential, T19 first to ground the exploration).

**Sequential dispatch note.** When both fire on aesthetic input, T19 typically runs first because the analytical reading grounds the open exploration that T20 then carries.

---

*End of Reference — Cross-Territory Adjacency.*
