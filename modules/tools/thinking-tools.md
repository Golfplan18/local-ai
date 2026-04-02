# Thinking Tools Library

*Loadable module. Loaded selectively into the Breadth model context window based on triage tier. Tier 1 loads nothing. Tier 2 loads three to four tool definitions plus the relevant Tier 2 module. Tier 3 loads the full relevant set.*

*Source specifications: Wisdom Nexus AI Swarm System Overview, Edward de Bono's Complete Thinking Systems reference.*

This library is the executable specification layer for the problem definition process. Each tool is defined with enough operational detail for the Breadth model to run it reliably during Phase B and Phase C without additional instruction.

Tools are drawn primarily from Edward de Bono's lateral thinking and DATT/CoRT frameworks. The DATT (Direct Attention Thinking Tools) system is CoRT 1 repackaged for business/adult contexts, focusing on the seven acronym tools. Each tool is an **attention-director** — it focuses thinking in a specific direction using deliberate, artificial operations with mnemonic acronyms.

## Tool Architecture — Three Tiers

**Tier 1 — Analytical Procedures.** Executable step-by-step processes the system runs on the user's behalf. Full operational definitions below. Load selectively when trigger conditions are met.

**Tier 2 — Domain Question Banks.** Structured question sets organized by domain and activation condition. Generate the right questions at the right moment. Separate documents in `modules/tools/tier2/` that load as complete units when domain signals trigger them.

**Tier 3 — Mental Model Lenses.** Conceptual frameworks stored as atomic vault notes, retrieved via RAG on demand. The Mental Models Library MOC provides the index. Mental models do not load into the context window wholesale.

---

## Tier 1 Tool Definitions

---

### AGO — Aims, Goals, Objectives

**Purpose:** Clarify the intention behind a thinking task at three levels of scope — overall aim, specific goal, and immediate objective.

**When to invoke:** Any prompt with a stated deliverable or action direction. At the start of Phase C. At the end of Phase B once a candidate problem definition has emerged. Whenever the system is uncertain what the user is actually trying to accomplish.

**Operational steps:**

1. Identify the overall aim — the general direction or desired end state
2. Identify the specific goal — what this particular thinking session is trying to achieve
3. Identify the immediate objective — what needs to happen right now
4. State all three as assertions, not questions: "I understand the aim as X, the goal as Y, the immediate objective as Z"
5. Invite confirmation, correction, or refinement

**Output format:** Three-line structured statement followed by confirmation prompt. Divergence between system reconstruction and user's stated intent is diagnostic output — note where the mismatch occurred.

**Integration points:** Feeds into CAF (knowing the aim determines which factors are relevant). Receives from Concept Fan in Phase B (the aim is discovered through abstraction before it can be stated). Mode selection uses AGO output to distinguish exploratory from deliverable-oriented queries.

**Failure modes:** Collapsing all three levels into one statement. Running AGO before Concept Fan in Phase B — this prematurely locks in an aim before the abstraction work has been done.

---

### CAF — Consider All Factors

**Purpose:** Map the full landscape of factors relevant to a situation before deciding, designing, or acting. The primary information input tool.

**When to invoke:** Early in any analysis where the problem domain needs mapping. Whenever the prompt appears to be addressing only part of a situation. At Tier 2 and Tier 3 of Phase C. Broadly in Phase B to reveal the shape of unfamiliar territory.

**Operational steps:**

1. List all factors that could be relevant — broadly, without filtering
2. Explicitly scan five categories: factors affecting the user, factors affecting other people, factors affecting the specific domain or organization, factors affecting the broader field, systemic factors
3. Flag categories that appear unaddressed in the current framing
4. Report as structured output

**Output format:** Two-part structured report — factors identified list, then unaddressed categories list with reasoning for each.

**Integration points:** Feeds into FIP (which factors matter most), OPV (which stakeholders are affected), and mode selection (incomplete factor maps signal Terrain Mapping). Receives from AGO. Other tools — C&S, OPV — may surface additional factors that feed back into CAF.

**Failure modes:** Stopping at obvious factors. Conflating factor identification with factor evaluation — factors are identified first, importance is determined later by FIP.

---

### C&S — Consequence and Sequel

**Purpose:** Look ahead at consequences of an action, plan, decision, or design across multiple time horizons. A prime evaluation tool.

**When to invoke:** For any prompt involving a decision or action. When the stated problem may be a short-term framing of a longer-term issue. At Tier 3 Phase C before mode selection. When C&S consequences conflict at different time horizons.

**Operational steps:**

1. State the action, plan, or decision being evaluated
2. Map consequences at four horizons: immediate, short-term (months to one year), medium-term (one to five years), long-term (five years and beyond)
3. Note where consequences at different horizons conflict

**Output format:** Four-row structured report, one row per time horizon. Cross-horizon conflicts noted explicitly.

**Integration points:** Feeds into mode selection (conflicting horizons → Constraint Mapping; long-term requiring paradigm questioning → Paradigm Suspension). Feeds into FIP. Receives from OPV (different stakeholders experience different consequence profiles).

**Failure modes:** Stopping at immediate consequences. Confusing C&S (future-looking evaluation) with PMI (all-sides assessment of a current situation). Generating consequences without noting cross-horizon conflicts.

---

### PMI — Plus, Minus, Interesting

**Purpose:** Consider all sides of a matter before making a decision or commitment. Prevents snap judgment by forcing exploration before evaluation.

**When to invoke:** When a specific approach has been stated or implied in the prompt. After CAF has surfaced factors, to evaluate a proposed direction. At Tier 3 when the prompt contains a stated solution path.

**Operational steps:**

1. State the idea, proposal, or approach being evaluated
2. List all Plus points — what is genuinely good about this
3. List all Minus points — what is genuinely problematic
4. List all Interesting points — implications and observations that are neither good nor bad but worth noting
5. Complete one category fully before moving to the next
6. A point may appear in both Plus and Minus if it genuinely has both dimensions

**Output format:** Three-section structured report. The Interesting section is most analytically valuable for problem definition — it surfaces hidden assumptions, paradigm-level implications, and unstated dependencies.

**Integration points:** Feeds into mode selection (Interesting items surfacing paradigm assumptions → Paradigm Suspension; distributional implications → Cui Bono). Receives from C&S (consequences become PMI input).

**Failure modes:** Treating Interesting as a catch-all for weak Plus or Minus points. Sorting items into categories as they are generated rather than completing one category at a time — this prevents genuine exploration of each dimension.

---

### OPV — Other People's Views

**Purpose:** Systematically map the perspectives of all stakeholders relevant to a situation. An exploration tool, not a judgment tool.

**When to invoke:** At Tier 3 Phase C. When the prompt involves multiple parties whose interests may differ. When CAF has identified stakeholder factors as potentially unaddressed. When OPV output is needed to inform KVI.

**Operational steps:**

1. List all people and groups involved — both directly and indirectly
2. For each stakeholder: map what they think, what they want, and what they fear
3. Note where stakeholder positions correlate with institutional interests — this is a Cui Bono signal
4. Report as structured output

**Output format:** Stakeholder list followed by a three-field profile for each (thinks / wants / fears). Cui Bono signal noted if institutional correlation is observed.

**Integration points:** Feeds into KVI (stakeholder views reveal what values are in play). Feeds into mode selection (institutional correlation → Cui Bono). Feeds into C&S (different stakeholders experience different consequence profiles). Receives from CAF.

**Failure modes:** Listing only obvious direct stakeholders. Confusing "other views" with alternative logical positions rather than genuinely different stakeholder interests. Omitting stakeholders who are indirectly affected but whose reactions could determine outcomes.

---

### KVI — Key Values Involved

**Purpose:** Surface the values at stake in a situation — what matters, what is at risk, and where value conflicts exist. Values must be identified before priorities can be set.

**When to invoke:** At Tier 3 Phase C, after OPV. Before FIP in any sequence — priorities are value-laden and cannot be set neutrally without first surfacing what values are in play. When the prompt involves a decision with ethical dimensions or competing interests.

**Operational steps:**

1. Identify positive values — things worth pursuing in this situation
2. Identify negative values — things worth avoiding
3. Note subtle, unstated, or newly emerging values that may not be explicit in the prompt
4. Identify value conflicts — places where pursuing one value requires compromising another
5. Note whose values are in tension (links to OPV output)

**Output format:** Three-section structured report: positive values, negative values, conflicts. KVI is not for judging or changing values — it maps what is there.

**Integration points:** Feeds into FIP (values determine which priorities are genuine vs. conventional). Feeds into mode selection (value conflicts → Constraint Mapping; foundational assumption conflicts → Paradigm Suspension). Receives from OPV. The OPV is automatically included in a full KVI when assessing all stakeholder values simultaneously.

**Failure modes:** Listing only obvious stated values. Treating priorities as if they were neutral before KVI has been run. Confusing KVI with ethical judgment — KVI surfaces values as they exist, it does not evaluate whether they should exist.

---

### FIP — First Important Priorities

**Purpose:** Narrow a longer list of factors, considerations, or options to those that matter most and must be addressed first. Runs after information has been gathered, not before.

**When to invoke:** After CAF has produced a factor list. After KVI has surfaced value tensions. Before mode selection in both Tier 2 and Tier 3 sequences. When the prompt contains too many considerations to address simultaneously.

**Operational steps:**

1. Take the input list (from CAF, KVI, or C&S)
2. First eliminate what is clearly not important — easier than selecting what is most important
3. Identify what cannot be omitted without the action or project failing (feasibility dimension)
4. Identify what cannot be omitted without the action or project being worth doing (value dimension)
5. When everything seems important, try combining related priorities

**Output format:** Narrowed list with reasoning for inclusion. Two-question framing for each item: "Without this, the action cannot proceed" OR "Without this, the action is not worth doing."

**Integration points:** Feeds into mode selection (the dimensions that matter most map directly to mode trigger conditions). Receives from CAF, KVI, C&S. FIP output is the direct predecessor to mode selection.

**Failure modes:** Running FIP before gathering information — priorities cannot be identified without CAF and KVI groundwork. Failing to use the two-question framing, which produces vague importance rankings rather than actionable priorities.

---

### APC — Alternatives, Possibilities, Choices

**Purpose:** Deliberately generate alternatives beyond the first or most obvious answer. The tool for creative expansion of the solution space.

**When to invoke:** When the problem framing appears to constrain the solution space unnecessarily. At Tier 3 Phase C as a framing challenge. When PMI's Minus section has revealed problems with the stated approach. When the user appears to have filtered viable options unconsciously.

**Operational steps:**

1. State the current approach or framing explicitly
2. List obvious alternatives — alternatives within the current framework
3. Generate additional alternatives beyond the obvious; at least one should be unconventional
4. Consider three categories: alternatives for explanation/understanding, for prediction, for action design
5. Do not evaluate alternatives during generation

**Output format:** Two-part list — standard alternatives, then expanded alternatives. No evaluation attached to any alternative.

**Integration points:** Feeds into mode selection (APC output challenging fundamental framing signals Paradigm Suspension). Receives from PMI (Minus items identify what needs alternatives). Receives from Challenge.

**Failure modes:** Stopping at obvious alternatives. Evaluating alternatives during generation — this suppresses unconventional options.

---

### Concept Fan

**Purpose:** Systematically expand and explore a problem or idea by moving up and down the abstraction ladder. Discovers problems rather than clarifying them. The primary Phase B tool.

**When to invoke:** At the beginning of Phase B — always, before any other tool. When the user cannot state the problem clearly. When the current framing appears to be solving the wrong problem. When the right level of abstraction is unknown.

**Operational steps:**

1. Take the current framing or stated problem as the starting point
2. Pull back to the concept behind it — what is this an instance of?
3. Generate alternative specific ideas at the same level that fulfill the same concept
4. Pull back further to a broader direction — what is this concept an instance of?
5. Generate alternative concepts at the broader level
6. Generate specific ideas for each alternative concept
7. Result: fan structure — broad directions → concepts → specific ideas

**Output format:** Fan diagram described in text — three levels with multiple items at each level. Note which level of abstraction the user's original framing occupied.

**Integration points:** Feeds into AGO in Phase B (the aim is discovered through abstraction work, then stated). Feeds into Phase C (abstraction level determines which tools are most useful). The right level of abstraction for the problem is one output of Concept Fan work.

**Failure modes:** Stopping at one level of abstraction. Confusing Concept Fan with APC — Concept Fan reframes the problem, APC generates solutions within an accepted framing. Running AGO before Concept Fan in Phase B.

---

### Challenge

**Purpose:** Question why something is done the way it is — not to prove it wrong, but to open the possibility that alternatives exist.

**When to invoke:** When the prompt contains assumptions that look like constraints but may be conventions. When APC is not generating genuinely different alternatives (suggesting the current framing is limiting the search). In Phase B when the user's stated framing needs to be tested.

**Operational steps:**

1. Identify the aspect being challenged
2. Ask: Why is it done this way? What is the purpose?
3. Ask: Does it have to be done this way to achieve that purpose?
4. Generate alternatives that still achieve the purpose without the challenged assumption

**Output format:** Challenge statement followed by purpose identification followed by alternatives list.

**Integration points:** Feeds into APC (Challenge reveals what is assumed; APC generates alternatives that relax that assumption). Feeds into Paradigm Suspension mode selection. Receives from CAF (factors taken for granted are candidates for Challenge).

**Failure modes:** Using Challenge as adversarial criticism rather than exploratory questioning. Stopping at identifying the assumption without generating alternatives.

---

### Provocation (Po)

**Purpose:** Create deliberate discontinuity from established patterns by stating something not meant to be true — but that generates forward movement toward new ideas.

**When to invoke:** When conventional analysis has reached a dead end. In Phase B when the user is circling without progress. In Green Hat thinking when the idea space needs expansion. When Random Entry has been tried and more structured disruption is needed.

**Operational steps:**

1. State the focus clearly
2. Construct a provocation using one of six methods:
   - **Escape:** Negate something taken for granted ("Po: buildings don't have roofs")
   - **Reversal:** Reverse the normal direction ("Po: the customer pays the company")
   - **Exaggeration:** Push a dimension to extremes
   - **Distortion:** Alter normal sequence or relationships
   - **Wishful thinking:** State a fantasy as real
   - **Arising:** Use something from any of the above as a further provocation
3. Apply movement — do not judge the provocation, use it:
   - Simulate it moment to moment
   - Extract a principle
   - Focus on differences from normal
   - Identify positive aspects
   - Find special circumstances where it would work
4. Extract useful concepts from the movement

**Output format:** Provocation statement, movement technique used, extracted concepts.

**Integration points:** Feeds into APC (provocation and movement produce new alternatives). Feeds into Green Hat analysis in the pipeline. Note: at least 40% of provocations should be completely unusable — safe provocations do not provide sufficient disruption.

**Failure modes:** Judging the provocation as true or false rather than using it for movement. Generating provocations without applying movement. Using provocations that are too mild to break the established pattern.

---

### RAD — Recognize, Analyze, Divide

**Purpose:** Identify what kind of situation this is, break it into components, and separate its parts when they are being conflated.

**When to invoke:** When a prompt may contain multiple distinct problems that need separation before analysis. When a situation looks familiar but may be misclassified. When CAF has produced a factor list containing items from different problem types.

**Operational steps:**

1. **Recognize:** What kind of situation is this? What familiar pattern does it match?
2. **Analyze:** What are the component parts? What are the relationships between them?
3. **Divide:** Are multiple distinct problems being conflated? Separate them.
4. Run only the steps needed — not all three are always required

**Output format:** Structured output with one section per step used. If Divide produces multiple separate problems, each becomes a candidate for a separate pipeline run.

**Integration points:** Feeds into Phase C by clarifying how many problems the pipeline is being asked to solve. Recognition can be dangerous when mistaken — flag uncertainty when a situation only partially matches a familiar pattern.

**Failure modes:** Forcing recognition onto a situation that is genuinely novel. Conflating Analyze (breaking into components) with Divide (separating distinct problems).

---

### FGL — Fear, Greed, Laziness

**Purpose:** Analyze the motivational underpinnings of institutional and individual positions, particularly in political, social, and policy domains. Cuts through stated rationale to identify the actual drivers of behavior.

**When to invoke:** Any prompt involving institutional actors, policy positions, political analysis, organizational behavior, or situations where stated reasons and actual behavior appear to diverge. Political and social analysis domain triggers automatically. Most effective after OPV has identified the stakeholders whose positions need motivational analysis.

**Operational steps:**

1. Identify the actor or set of actors whose positions are being analyzed
2. **Fear analysis:** What is this actor afraid of losing? What threats — to power, resources, status, legitimacy, constituency, or survival — drive their position? What outcomes are they trying to avoid?
3. **Greed analysis:** What is this actor trying to gain or protect? What benefits — material, political, reputational, or positional — does their stated position serve?
4. **Laziness analysis:** How does path-of-least-resistance, institutional inertia, or status quo preference shape their position? What would require effort or change that they are avoiding? What existing arrangements does their position protect?
5. Assess which motivational driver is dominant for each actor
6. Construct the "motivational-stripped" position: what would this actor's position look like if the FGL distortions were removed and only their stated rationale remained? Does the gap between the two reveal anything?

**Output format:** Per-actor three-field report (fear / greed / laziness) followed by dominant driver assessment and motivational gap analysis.

**Integration points:** Feeds into Cui Bono mode selection (strong FGL signal with institutional actors → Cui Bono). Feeds into OPV (FGL enriches the "what they want / what they fear" fields). Feeds into KVI (FGL reveals values that are operative but unstated). Receives from OPV (stakeholder list). Receives from CAF.

**Failure modes:** Applying FGL as a cynicism generator rather than an analytical tool — the goal is accurate motivational mapping, not proof of bad faith. Omitting laziness as a driver (it is frequently the most powerful of the three and the most overlooked). Applying FGL to individuals rather than institutional roles — FGL is most reliable when analyzing actors in their institutional capacity, where incentive structures are more systematic than personal.

---

## Standard Tool Sequences

These sequences are not rigid — the Breadth model uses them as defaults and adapts based on what each tool's output reveals.

**Phase B sequence:** Concept Fan (always first) → CAF → Challenge → AGO (last in Phase B)

**Phase C Tier 2 (Targeted Clarification):** AGO → CAF → FIP → Mode Selection

**Phase C Tier 3 (Full Perceptual Broadening):** AGO → CAF → OPV → KVI → C&S → PMI → FIP → APC → Mode Selection

**Natural chaining:** AGO → CAF → OPV → APC → C&S → PMI → FIP forms a complete reasoning pipeline where each step's output feeds the next step's context.

---

## Tier 2 Module Library

Tier 2 modules are separate documents in `modules/tools/tier2/`. Each loads as a complete unit when domain signals trigger it.

**Problem Definition Question Bank**
Trigger: Phase B or Phase C; any session where problem definition work is explicitly requested; triage gate Tier 2 or Tier 3.

**Political and Social Analysis Module**
Trigger: Domain is political, social, or policy-related; OPV reveals institutional correlation; prompt references governments, organizations, regulatory bodies, or advocacy groups.

**Engineering and Technical Analysis Module**
Trigger: Domain is technical, engineering, product design, or systems implementation; prompt involves diagnosing a failure, designing a solution, or specifying requirements.

**Design Analysis Module**
Trigger: Domain involves creative or professional design work; prompt references design problems, user experience, product development, or service design.

**Contemplative and Spiritual Analysis Module**
Trigger: Domain is spiritual practice, Buddhist philosophy, phenomenological inquiry, or contemplative experience.

**Wicked Problems Assessment Checklist**
Trigger: Gate-level diagnostic — runs before mode selection whenever domain is political, social, policy, or systems-level; also triggers when initial problem formulation attempts have repeatedly failed to produce a stable definition.

---

## Tier 3 — Mental Models

Mental models are stored as atomic vault notes and retrieved via RAG. Each note carries domain tags and trigger conditions for automatic surfacing. The Mental Models Library MOC provides the navigable index.

Trigger condition examples:
- _Inversion_ triggers when a problem has been approached from only one direction for multiple sessions
- _Second-order thinking_ triggers when C&S analysis shows no medium or long-term consequences
- _Hanlon's Razor_ triggers in political analysis when malicious intent has been assumed without evidence
- _First Principles Thinking_ triggers when APC is not generating genuinely different alternatives
- _Map and Territory_ triggers when a model or abstraction is being treated as equivalent to the underlying reality
- _Circle of Competence_ triggers when the user is operating outside established expertise
