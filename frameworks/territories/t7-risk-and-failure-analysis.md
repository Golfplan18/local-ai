
# Framework — Risk and Failure Analysis

*Self-contained framework for examining a plan, system, or design specifically for failure modes, vulnerabilities, fragilities, and tail risks. Compiled 2026-05-01 from territory entry, member mode specs, lens dependencies, and open debates.*

---

## Territory Header

- **Territory ID:** T7
- **Name:** Risk and Failure Analysis
- **Super-cluster:** C (Decision, Future, and Risk)
- **Characterization:** Operations that examine a plan, system, or design specifically for failure modes, vulnerabilities, fragilities, and tail risks.
- **Boundary conditions:** Input is a plan, system, or design. Question is *how could this fail*. Excludes general-future-exploration (T6 — broader question than failure) and excludes Red Team's adversarial-actor framing (T15 — about an adversary, not about structural fragility).
- **Primary axis:** Depth (FMEA-light → fault tree → fragility/antifragility molecular).
- **Secondary axes:** Specificity (technical-system risk vs. plan-risk vs. organizational-risk); stance (Talebian asymmetry vs. structural).

## When to use this framework

Use when the question is specifically how something could fail — a plan, a system, a design, a strategy. Plain-language triggers:

- "Where could this design break?"
- "What failure modes does this system exhibit?"
- "Which parts of this structure are load-bearing single points?"
- "If I were stress-testing this architecture, where would I look?"
- "Before we ship this design, what fragilities exist?"
- "I want to know how this responds to volatility, not just whether it survives normal conditions."
- "I need to distinguish things that break under stress from things that get stronger."
- "I'm worried about tail risks and asymmetric exposures."

Do not route here when the question is general-future-exploration broader than failure (T6); when modeling an adversarial actor trying to defeat the artifact (T15 — Red Team); when the failure has already happened and the question is now causal (T4); when the question shifts to choice among options where risk is one input among several (T3).

## Within-territory disambiguation

```
Q1 (specificity): "Is the question about an action plan that could fail,
                   or about a system or design with structural fragilities
                   (where could it break under any pressure)?"
  ├─ "action plan, what could go wrong before we commit" → pre-mortem-fragility
                                                            (cross-territory note:
                                                             parsed from pre-mortem;
                                                             action-plan variant
                                                             lives in T6)
  ├─ "system or design — structural fragility, asymmetric exposure" →
        fragility-antifragility-audit (Talebian)
  └─ ambiguous → pre-mortem-fragility with escalation to fragility-antifragility-audit

Q2 (depth, optional): "Want a quick scan for failure modes, or a thorough fault-tree
                        that traces how component failures propagate?"
  ├─ "quick scan" → failure-mode-scan (deferred per CR-6)
  ├─ "thorough fault tree" → fault-tree (deferred per CR-6)
  └─ ambiguous → use the mode selected in Q1

Q3 (stance, optional): "Are you specifically modeling an adversary trying to defeat this,
                         or asking where it could break under any pressure
                         (no adversary required)?"
  ├─ "adversary modeling" → cross-territory dispatch to T15 red-team-assessment / red-team-advocate
  └─ "any pressure / no adversary needed" → stay in T7
```

**Default route.** `pre-mortem-fragility` at Tier-2 when ambiguous (the lighter atomic mode; `fragility-antifragility-audit` is the heavier sibling with the full Talebian asymmetry treatment).

**Escalation hooks.**
- After `pre-mortem-fragility`: if the failure modes surfaced are structural and asymmetric rather than action-specific, hook upward to `fragility-antifragility-audit`.
- After either T7 mode: if an adversary is genuinely in the picture, hook sideways to T15 (`red-team-assessment` / `red-team-advocate`).
- After either T7 mode: if the failure has already happened and the question is now causal, hook sideways to T4.
- After either T7 mode: if the failure is a strategic-interaction failure, hook sideways to T18.

## Mode entries

### Mode — pre-mortem-fragility

- **Educational name:** pre-mortem on structural fragilities (Klein, Taleb adjacent)
- **Plain-language description:** An adversarial-future pass on a system, design, structure, architecture, or institution. Adopts prospective-hindsight stance — writes as though the breakage has already occurred and narrates it backward. Identifies structural fragilities (specific to this structure's components and dependencies, not generic system-failure tropes), traces load pathways from operating-envelope stresses to specific structural elements that yield, identifies leading indicators per fragility, and proposes structural mitigations distinguished from operational workarounds (fragility is a property of the structure rather than its operation). **Parsed sibling of `pre-mortem-action` (T6) per Decision D — they share `klein-pre-mortem` lens but differ in operation: `pre-mortem-fragility` operates on the system or design; `pre-mortem-action` operates on the action plan.**

- **Critical questions:**
  1. Has the analysis genuinely adopted prospective-hindsight stance on the system (writing as though the breakage has already occurred), or has it slipped into hedged forward-projection?
  2. Are the named fragilities specific to this structure's components and dependencies, or are they generic system-failure tropes (single point of failure, cascading failure) without structural specificity?
  3. Have load pathways been traced from operating-envelope stresses to specific structural elements that yield, or do the breakages appear without mechanism?
  4. Have structural mitigations been distinguished from operational workarounds, given that fragility is a property of the structure rather than its operation?

- **Per-pipeline-stage guidance:**
  - **Depth.** Prospective-hindsight stance maintained; fragilities specific to components/dependencies; load pathways traced; structural vs. operational mitigations distinguished.
  - **Breadth.** Scan fragilities across categories: load-bearing components, single-point dependencies, brittle interfaces, time-coupled failures, cascading-failure pathways, environmental-envelope edges.
  - **Evaluation.** Four critical questions plus failure modes (stance-slippage, generic-fragility-trope, mechanism-gap, structure-operation-conflation).
  - **Consolidation.** Seven required sections: imagined breakage narrative; structural fragility inventory; load pathways to breakage; leading indicators per fragility; structural mitigations; residual unmitigated fragilities; confidence per finding.

- **Source tradition:** Klein "Performing a Project Premortem" (2007) — same lens as T6's `pre-mortem-action`; structural-engineering tradition for the load-pathway framing; Reason *Human Error* (1990) for defensive-layer failure analysis.

- **Lens dependencies:**
  - `klein-pre-mortem`: Prospective-hindsight method — imagine the system has broken at some future point; narrate the breakage backward. (Same lens as T6 `pre-mortem-action`; the parsed difference is the object — system here, plan there.)
  - Optional: `reason-swiss-cheese-model` (when fragility crosses multiple defensive layers); structural-engineering load-path lenses.

### Mode — fragility-antifragility-audit

- **Educational name:** fragility / antifragility audit (Taleb convex-response-to-stressor)
- **Plain-language description:** A thorough Talebian audit classifying the system per fragility (concave response to stressor — losses dominate), robustness (linear response — survives but does not gain), or antifragility (convex response — *gains* from volatility within a range). Identifies convex exposures (where small frequent gains mask rare catastrophic losses requires inversion: the analysis surfaces *concave* exposures explicitly), distinguishes variance under normal conditions from tail-event response, applies via negativa (subtraction of fragility-creating elements rather than addition of robustness-creating elements), and holds the analyst's own Talebian assumptions lightly rather than applying them mechanically.

- **Critical questions:**
  1. Has the analysis classified the system per fragility / robustness / antifragility, or has it collapsed antifragility into mere robustness?
  2. Have concave exposures (where small frequent gains hide rare catastrophic losses) been surfaced explicitly, or has the analysis focused only on visible volatility?
  3. Has the analysis distinguished between (a) variance under normal conditions and (b) tail-event response, or has it conflated them?
  4. Has via negativa been considered (subtraction of fragility-creating elements rather than addition of robustness-creating elements)?
  5. Have the analyst's own Talebian assumptions (markets-are-fat-tailed, expert-prediction-is-poor, optionality-is-undervalued) been held lightly rather than mechanically applied?

- **Per-pipeline-stage guidance:**
  - **Depth.** Convex/concave exposure identification; tail-risk separation from normal variance; via negativa as primary mitigation framing.
  - **Breadth.** Stressor inventory across types (small frequent shocks, rare large shocks, regime changes, slow drift); consider Lindy effect (longer-surviving structures are more robust); barbell strategy as one robust response pattern.
  - **Evaluation.** Five critical questions plus failure modes (antifragility-collapse, hidden-concavity, variance-tail-conflation, addition-bias, Talebian-orthodoxy).
  - **Consolidation.** Nine required sections: system or strategy locked; stressor inventory; convex exposures identified; concave exposures identified; fragility/robustness/antifragility classification; tail-risk assessment; asymmetric-payoff findings; via negativa recommendations; confidence per finding.

- **Source tradition:** Taleb *The Black Swan* (2007); Taleb *Antifragile: Things That Gain from Disorder* (2012); Taleb *Skin in the Game* (2018); Mandelbrot *The (Mis)behavior of Markets* (2004) for fat-tailed distributions.

- **Lens dependencies:**
  - `taleb-convex-response`: Three-class system classification — fragile (concave response, losses from volatility), robust (linear, survives without gain), antifragile (convex, gains from volatility within a range). Distinct from prediction (the framework is response-based, not forecast-based).
  - `taleb-via-negativa`: Subtraction-based mitigation — remove the fragility-creating element rather than add a robustness-creating compensating mechanism. The compensating mechanism may itself be fragile or introduce concave exposure.
  - `taleb-barbell-strategy`: Combine very-safe (insurance against tail loss) with very-risky (capped downside, uncapped upside) while avoiding the middle (where most exposure is concentrated). Convex payoff structure.
  - `lindy-effect`: For non-perishable items (ideas, technologies, books), longer past survival predicts longer future survival. Useful as a prior for assessing structural robustness.

## Cross-territory adjacencies

**T7 ↔ T6 (Future Exploration — Pre-Mortem parse).** Pre-Mortem is parsed (per Decision D) into two modes that share the `klein-pre-mortem` lens but differ in operation:
- `pre-mortem-action` (T6): adversarial-future on *the action plan*.
- `pre-mortem-fragility` (T7): adversarial-future on *the system or design*.
Disambiguating question: "Is this about an action plan that could fail, or about a system or design with structural fragilities?"

**T7 ↔ T15 (Artifact Evaluation by Stance — Red Team case).** "Adversarial-actor stress test (someone is trying to defeat this), or structural-fragility audit (where could this break under any pressure)?" Actor-modeling → T15 Red Team; structural fragility → T7. Examples: "How would a competitor attack this strategy?" → T15 Red Team. "Where would this strategy break under market stress regardless of who's pushing on it?" → T7 Fragility Audit.

**T7 ↔ T4 (Causal Investigation).** When failure has already happened and the question is now causal, route to T4 (`root-cause-analysis` or `process-tracing`).

**T7 ↔ T18 (Strategic Interaction).** When the failure is a strategic-interaction failure (an equilibrium that breaks under specific conditions), route to T18.

## Lens references

### klein-pre-mortem

(See full description in `Framework — Future Exploration.md` Lens references — same lens applied to system/design rather than action plan.)

### taleb-convex-response

**Core insight.** Systems differ in how they respond to volatility. The classification is response-based, not forecast-based.

**Three classes.**
- *Fragile.* Concave response to stressor — losses dominate. Small frequent gains hide rare catastrophic losses. Examples: highly leveraged positions; just-in-time supply chains without buffers; reputational positions exposed to single tail events.
- *Robust.* Linear response — survives but does not gain. The system absorbs the stressor without breaking but also without improving. Examples: a well-built bridge; a diversified portfolio; a redundant system.
- *Antifragile.* Convex response — *gains* from volatility within a range. The system improves under stress. Examples: muscles strengthened by exercise; immune systems exposed to pathogens; optionality structures with capped downside and uncapped upside.

**Diagnostic question.** What does the system look like *after* a stressor relative to before? If worse → fragile. If unchanged → robust. If improved → antifragile.

**Application.** Classification grounds the analysis. Fragile systems need either reduction of stressor exposure (via negativa) or transformation toward robustness or antifragility. Robust systems may be over-engineered for current conditions but waste optionality. Antifragile systems should be preserved but their range of beneficial stress identified (excessive stress destroys even antifragile structures).

### taleb-via-negativa

**Core insight.** When the goal is robustness or antifragility, *subtraction* of fragility-creating elements often beats *addition* of robustness-creating compensating mechanisms. The compensating mechanism may itself be fragile or may introduce concave exposure not previously present.

**Application.** When asked "how do we make this more robust?", first ask "what could we remove that is currently making it fragile?" before adding mitigations. Remove single points of failure, brittle dependencies, time-coupling, leverage, opacity. Often the simplest robustness improvement is *not building* the fragility-creating element in the first place.

**Common misapplications.** Treating via negativa as a universal preference (some additions genuinely improve robustness); treating subtraction as cost-free (subtraction may remove valuable functionality alongside the fragility).

### taleb-barbell-strategy

**Core insight.** Combine very-safe positions (insurance against tail loss) with very-risky positions (capped downside, uncapped upside) while avoiding the middle (where most exposure is concentrated). The combination produces a convex payoff structure asymmetrically exposed to upside.

**Application.** Resource allocation: 80–90% in maximum-safety holdings (cash, treasuries) plus 10–20% in maximum-optionality positions (venture, options, asymmetric bets). The middle (moderate-risk moderate-return positions) is avoided because it concentrates exposure without convexity benefit.

**Common misapplications.** Applying the strategy where convex payoffs are not available (the very-risky portion may have capped upside in some domains); ignoring correlation between safe and risky positions (the safe portion must be uncorrelated with the risky portion's downside).

### lindy-effect

**Core insight.** For non-perishable items (ideas, technologies, books, institutions, recipes), longer past survival predicts longer future survival. A book in print for 100 years has higher expected remaining lifespan than a book in print for 10 years. The intuition: things that have survived have survived selection pressure; things that have not survived selection pressure are not present to be observed.

**Application.** Useful as a prior for assessing structural robustness of a candidate structure. New structures (recently engineered) lack the survival evidence; long-surviving structures have demonstrated robustness even where the mechanism is not understood. Bias the analysis toward Lindy-tested structures unless specific evidence overrides.

**Common misapplications.** Applying to perishable items (humans, organisms) — the Lindy effect is for non-perishables; treating Lindy as evidence of optimality (Lindy survival is evidence of robustness, not of optimality); ignoring environmental change (a structure that survived past selection may not survive a changed environment).

## Open debates

### Pre-Mortem parse note (Debate D8)

The Pre-Mortem operation appears to fit both T6 and T7. Per Decision D parsing principle, the candidate mode is split into two modes that share the `klein-pre-mortem` lens but differ in operation, rather than dual-citizened.

The parse:
- `pre-mortem-action` (T6): on the action plan.
- `pre-mortem-fragility` (T7): on the system or design.

This framework's home for the Pre-Mortem operation is T7's structural variant. T6's framework documents the action variant. Both modes coexist with shared lens; routing distinguishes by object (plan vs. system).

## Citations and source-tradition attributions

**Pre-mortem.**
- Klein, Gary (2007). "Performing a Project Premortem." *Harvard Business Review* (Sept).
- Klein, Gary (1998). *Sources of Power: How People Make Decisions*. MIT Press.

**Talebian risk theory.**
- Taleb, Nassim Nicholas (2007). *The Black Swan: The Impact of the Highly Improbable*. Random House.
- Taleb, Nassim Nicholas (2012). *Antifragile: Things That Gain from Disorder*. Random House.
- Taleb, Nassim Nicholas (2018). *Skin in the Game: Hidden Asymmetries in Daily Life*. Random House.
- Mandelbrot, Benoit, and Richard L. Hudson (2004). *The (Mis)behavior of Markets*. Basic Books.

**Failure-engineering tradition.**
- Reason, James (1990). *Human Error*. Cambridge University Press.
- Perrow, Charles (1984). *Normal Accidents: Living with High-Risk Technologies*. Basic Books.
- Petroski, Henry (1985). *To Engineer Is Human: The Role of Failure in Successful Design*. St. Martin's.

*End of Framework — Risk and Failure Analysis.*
