
# Framework — Stakeholder Conflict

*Self-contained framework for taking a situation involving multiple parties with divergent interests/values and characterizing the conflict structure, surfacing positions and interests, and identifying integrative possibilities. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T8
- **Name:** Stakeholder Conflict
- **Super-cluster:** D (Position, Stakeholder, and Strategy)
- **Characterization:** Operations that take a situation involving multiple parties with divergent interests/values and characterize the conflict structure, surface positions and interests, and identify integrative possibilities.
- **Boundary conditions:** Input is a situation with multiple identifiable parties. Excludes pure interest-power analysis without conflict structure (T2) and excludes negotiation-active operations (T13).
- **Primary axis:** Complexity (multi-party-descriptive → systemic).
- **Secondary axes:** Depth (light → integrative).

## When to use this framework

Use when there is a situation with multiple identifiable parties whose interests diverge, and you need to map the parties, their stakes, their salience, and their relationships before action. Plain-language triggers:

- "I need to map out who's involved here."
- "There are multiple parties with different stakes."
- "Before we move, we need to understand the parties."
- "We keep getting blindsided by people we forgot to consider."
- "Who has standing in this and how much?"

Do not route here when the question is who benefits from a single situation without multi-party landscape (T2 — Cui Bono); when active negotiation guidance is needed (T13); when the user is the decision-maker and parties are inputs (T3); when the question is which framing privileges which party (T9).

## Within-territory disambiguation

```
Q1 (situation): "Are you mapping the parties and how their interests align or diverge,
                  or is the conflict structure itself wicked
                  (parties, sub-parties, shifting coalitions)?"
  ├─ "mapping parties and interests" → stakeholder-mapping (Tier-2)
  ├─ "wicked / shifting / sub-coalitions" → conflict-structure (deferred per CR-6)
  └─ ambiguous → stakeholder-mapping (singleton mode at current population)
```

**Default route.** `stakeholder-mapping` at Tier-2 — this is effectively the territory founder; `conflict-structure` is deferred per CR-6.

**Escalation hooks.**
- After `stakeholder-mapping`: if the user is moving from descriptive mapping into active negotiation guidance, hook sideways to T13 (`interest-mapping` or `principled-negotiation`).
- After `stakeholder-mapping`: if the question is fundamentally about who benefits and where power sits rather than about the conflict shape, hook sideways to T2 (`cui-bono` or `boundary-critique`).
- After `stakeholder-mapping`: if the conflict has feedback structure across multiple sub-coalitions and the deferred `conflict-structure` mode is needed, surface the deferred-mode flag rather than substituting `wicked-problems` from T2 (different operations).

**Singleton note.** T8 currently has one resident mode (`stakeholder-mapping`). Expansion candidate `conflict-structure` is deferred per CR-6.

## Mode entries

### Mode — stakeholder-mapping

- **Educational name:** multi-party stakeholder mapping (Bryson, Mitchell-Agle-Wood salience)
- **Plain-language description:** A descriptive multi-party mapping pass producing the landscape of parties, their stakes, salience (per Mitchell-Agle-Wood: power, legitimacy, urgency), positioning on a power-interest grid, relationships among parties, and explicit identification of absent or marginalized parties. Inventory deliberately reaches outside the user's initial frame to surface parties the user has not yet named. Salience is multi-dimensional (a high-power-low-legitimacy party is structurally distinct from a high-legitimacy-low-power party).

- **Critical questions:**
  1. Has the inventory identified parties from outside the user's initial frame, or has the analysis stayed inside the user's pre-existing mental model of who counts?
  2. Are stakes named at the level of concrete interests (what the party wants and could lose), rather than at the level of role-labels alone?
  3. Has salience been assessed using more than one dimension (power AND legitimacy AND urgency, per Mitchell-Agle-Wood), so a high-power-low-legitimacy party isn't conflated with a high-legitimacy-low-power party?
  4. Have absent or marginalized parties been explicitly named, or has the map silently mirrored existing power asymmetries?

- **Per-pipeline-stage guidance:**
  - **Depth.** Stakes named at the level of concrete interests; salience multi-dimensional; relationships among parties surfaced explicitly.
  - **Breadth.** Inventory reaches outside the user's initial frame; surfaces parties the user has not named; identifies absent or marginalized parties not currently represented.
  - **Evaluation.** Four critical questions plus failure modes (frame-bounded-inventory, role-as-stake, single-axis-salience, silent-power-mirroring).
  - **Consolidation.** Seven required sections in matrix form: stakeholder inventory; power-interest positioning; Mitchell-Agle-Wood salience classification; stake per party; relationships among parties; absent or marginalized parties; confidence per finding.
  - **Verification.** Inventory includes parties from outside user's initial frame; stakes named at concrete-interest level; salience assessed on ≥2 dimensions; absent/marginalized parties explicitly named.

- **Source tradition:** Bryson *Strategic Planning for Public and Nonprofit Organizations* (1995/2018) for the power-interest grid; Mitchell, Agle, & Wood "Toward a Theory of Stakeholder Identification and Salience" *Academy of Management Review* (1997) for the three-dimensional salience model; Freeman *Strategic Management: A Stakeholder Approach* (1984) for the foundational stakeholder-theory framing.

- **Lens dependencies:**
  - `bryson-power-interest-grid`: Two-dimensional positioning matrix — power (high/low) × interest (high/low). Four quadrants — Players (high power, high interest: engage closely); Subjects (low power, high interest: keep informed); Context-setters (high power, low interest: keep satisfied); Crowd (low power, low interest: monitor). Each quadrant carries a characteristic engagement strategy.
  - `mitchell-agle-wood-salience`: Three salience attributes — Power (ability to impose will), Legitimacy (socially accepted right to claim), Urgency (time-sensitivity of claim). Eight stakeholder classes by attribute combination — Dormant (P only), Discretionary (L only), Demanding (U only), Dominant (P+L), Dangerous (P+U), Dependent (L+U), Definitive (P+L+U), Non-stakeholder (none). Salience for organizational attention scales with attribute count; the highest-salience class is Definitive.
  - Foundational: `kahneman-tversky-bias-catalog`.

## Cross-territory adjacencies

**T8 ↔ T2 (Interest and Power).** "Mostly asking who benefits or has power, or asking how the parties' competing claims can be worked through?" Power/interest analysis → T2 (Cui Bono / Boundary Critique); conflict structure → T8 (Stakeholder Mapping). When both fire, T2 typically runs first because interest analysis grounds the descriptive conflict mapping that T8 produces.

**T8 ↔ T13 (Negotiation).** "Mapping the conflict structure, or guiding active negotiation?" Mapping → T8; active → T13. When active negotiation guidance is needed but the conflict structure is not yet mapped, T8 runs first; T13 follows.

**T8 ↔ T3 (Decision-Making).** "Is this fundamentally your decision to make (with the parties as inputs), or is it a situation where the parties' conflict itself is what needs to be worked through first?" Your-decision → T3; parties'-conflict-first → T8. When the conflict structure must be characterized before the decision can be framed, T8 runs first.

## Lens references

### bryson-power-interest-grid

**Core structure.** Two-dimensional positioning of stakeholders on power (vertical axis) and interest (horizontal axis), each at high/low. Four quadrants:

- *Players (high power, high interest).* The highly-engaged stakeholders with capacity to shape outcomes. Engagement strategy: closely engage, manage actively, build coalitions.
- *Subjects (low power, high interest).* The affected-but-relatively-powerless stakeholders. Engagement strategy: keep informed, support their interests where possible, build their power if alignment exists.
- *Context-setters (high power, low interest).* The stakeholders whose power could shift outcomes if their interest were activated. Engagement strategy: keep satisfied to prevent their interest from being activated against the initiative; monitor for changing engagement.
- *Crowd (low power, low interest).* The bystanders. Engagement strategy: monitor; do not invest disproportionate engagement effort.

**Application.** Plot each stakeholder. Read off engagement strategy per quadrant. Track movement (a Subject who gains power becomes a Player; a Player who loses interest becomes a Context-setter). The grid is dynamic, not static.

**Common misapplications.** Treating quadrant placement as fixed; conflating power with formal authority (informal power often dominates); conflating interest with stated position (interests can be latent or strategic).

### mitchell-agle-wood-salience

**Core structure.** Three salience attributes determining the degree to which managers should give priority to a stakeholder's claim:

- *Power.* The stakeholder's ability to impose its will despite resistance. Sources: coercive power (force), utilitarian power (resources), normative power (symbols, status).
- *Legitimacy.* The socially accepted and expected right of the stakeholder to claim. Legitimacy is normative — it depends on social structures of accountability.
- *Urgency.* The time-sensitivity of the claim, plus its criticality for the stakeholder. Urgency without legitimacy or power produces noise; with one of them, it elevates salience.

**Eight stakeholder classes by attribute combination.**
- *Dormant (Power only).* High potential influence, but currently not exercising it. Watch for activation triggers.
- *Discretionary (Legitimacy only).* Right to claim but no power and no urgency. The classic charity beneficiary — managers may or may not engage.
- *Demanding (Urgency only).* Persistent and immediate demands without power or legitimacy. The mosquito of stakeholders.
- *Dominant (Power + Legitimacy).* The classic powerful legitimate stakeholders — boards, regulators, major shareholders. Salience high, no urgency.
- *Dangerous (Power + Urgency, no Legitimacy).* Coercive, urgent, illegitimate — terrorist groups, unauthorized strikers, hostile activists who can act now.
- *Dependent (Legitimacy + Urgency, no Power).* Legitimate urgent claim but no power to enforce — disaster victims, communities affected by externalities, non-organized publics. Often the most ethically charged stakeholder class.
- *Definitive (Power + Legitimacy + Urgency).* The highest salience. All three attributes — managers should give priority to these claims.
- *Non-stakeholder.* No power, no legitimacy, no urgency. Not a stakeholder.

**Application.** Classify each party by attribute combination. Salience for organizational attention scales with attribute count. Track movement — a Dependent stakeholder may become Definitive if a Dependent's claim is taken up by a Dominant stakeholder; a Discretionary stakeholder may become Dangerous if frustration breeds urgency and an alliance brings power.

**Common misapplications.** Treating salience as ethical priority (the model is descriptive of organizational attention, not prescriptive of moral standing); conflating legitimacy with conformity (legitimacy is socially accepted, but social acceptance can itself be unjust); ignoring the Dependent class because it lacks power (the class is often most ethically charged).

## Open debates

T8 carries no architecture-level debates that bear on territory operation. The expansion candidate `conflict-structure` (for systemic / wicked / shifting-coalition conflicts) is deferred per CR-6; promotion would happen if T8 invocations consistently produce composition-with-T13 patterns suggesting `conflict-structure` is needed independently.

## Citations and source-tradition attributions

**Stakeholder theory.**
- Freeman, R. Edward (1984). *Strategic Management: A Stakeholder Approach*. Pitman.
- Bryson, John M. (1995/2018). *Strategic Planning for Public and Nonprofit Organizations* (5th ed.). Wiley.
- Mitchell, Ronald K., Bradley R. Agle, and Donna J. Wood (1997). "Toward a Theory of Stakeholder Identification and Salience." *Academy of Management Review* 22(4):853–886.
- Phillips, Robert (2003). *Stakeholder Theory and Organizational Ethics*. Berrett-Koehler.

**Stakeholder analysis methods.**
- Eden, Colin, and Fran Ackermann (1998). *Making Strategy: The Journey of Strategic Management*. Sage.
- Reed, Mark S. et al. (2009). "Who's in and why? A typology of stakeholder analysis methods for natural resource management." *Journal of Environmental Management* 90(5):1933–1949.

*End of Framework — Stakeholder Conflict.*
