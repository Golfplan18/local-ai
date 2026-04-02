# Wicked Problems Assessment Checklist

*Tier 2 module. Loads into the Breadth model context window as a complete unit.*

## Trigger Conditions

- **Gate-level diagnostic** -- runs before mode selection whenever domain is political, social, policy, or systems-level
- Also triggers when initial problem formulation attempts have repeatedly failed to produce a stable definition
- Precedes other Tier 2 domain modules when activated

## Purpose

This module determines whether a problem exhibits wicked problem characteristics (per Rittel and Webber, 1973). Wicked problems cannot be solved using standard analytical approaches because they resist stable definition, have no stopping rule, and generate unintended consequences that reshape the problem itself. Identifying wickedness early prevents the system from applying tame-problem methods to wicked-problem situations, which produces confident-sounding but unreliable output.

This checklist produces a diagnostic classification: **tame**, **messy** (complicated but definable), or **wicked**. The classification determines how the rest of the pipeline handles the problem.

---

## Category 1: Definitional Stability

These determine whether the problem can be stably defined.

1. Can the problem be stated in a way that all relevant parties would accept? Or does each stakeholder define the problem differently, with each definition implying a different solution?
2. Has the problem definition shifted during the conversation or across previous attempts to formulate it? Does refining the definition change what problem is being solved?
3. Is the problem definition inseparable from the proposed solution? (In wicked problems, the formulation of the problem IS the formulation of the solution -- you cannot define the problem without simultaneously choosing a solution direction.)
4. Does additional information clarify the problem or make it more ambiguous? (Tame problems get clearer with more data; wicked problems often get murkier.)
5. Can you enumerate the set of possible solutions? (Tame problems have a discoverable solution set. Wicked problems have no enumerable set of potential solutions.)

## Category 2: Causal Structure

These assess whether the causal dynamics are tractable.

6. Can cause and effect be reliably identified? Or do the relevant factors form circular causal chains where effects become causes?
7. Are the causes of the problem agreed upon, or do different stakeholders attribute the problem to fundamentally different causes?
8. Does the system exhibit emergent behavior -- outcomes that cannot be predicted from the behavior of individual components?
9. Are there significant time delays between actions and their consequences, making it difficult to learn from interventions?
10. Does intervening in one part of the system reliably produce changes in the intended direction, or do compensating feedback loops absorb or reverse the intervention?

## Category 3: Solution Characteristics

These determine what kind of solutions are available.

11. Is there a clear criterion for when the problem is solved? Or does the problem lack a natural stopping rule -- you stop when you run out of resources, time, or patience, not because the problem is resolved?
12. Can proposed solutions be tested before implementation? Or is every intervention a one-shot operation with irreversible consequences?
13. Do solutions to this problem create new problems of comparable magnitude?
14. Is the problem unique, or is it an instance of a well-understood class of problems with known solution methods?
15. Can the problem be decomposed into sub-problems that can be solved independently? Or does solving any part require addressing the whole?

## Category 4: Stakeholder Dynamics

These assess the social complexity of the problem.

16. Do the relevant stakeholders share a common set of values, or are their value systems fundamentally incompatible on this issue?
17. Is there a legitimate authority that can impose a solution, or must any solution emerge from negotiation among parties with conflicting interests?
18. Are the people who experience the problem the same people who have power to address it? Or is there a structural separation between problem-bearers and decision-makers?
19. Does each stakeholder's attempt to solve the problem from their perspective worsen the problem for other stakeholders?
20. Are there actors who benefit from the problem's persistence and will actively resist resolution?

## Category 5: Intervention Risk

These assess the risk profile of acting on this problem.

21. What is the cost of being wrong? Are failed interventions easily reversed, or do they create lasting damage?
22. Is the planner (or advisor) liable for the consequences of their intervention? (Rittel's criterion: the planner has no right to be wrong -- consequences fall on real people.)
23. Can the problem be addressed through incremental, reversible experiments? Or does it require large-scale, irreversible commitments?
24. What is the track record of past interventions on this problem or similar problems? Have previous solutions generated new problems?
25. Is there a risk that confident-sounding analysis will be mistaken for reliable prediction in a domain where prediction is structurally unreliable?

---

## Diagnostic Scoring

After running the checklist, classify the problem:

**Tame Problem** (most questions answered in the tractable direction):
- Proceed with standard pipeline. Tier 1 tools and domain modules will be sufficient.
- Problem can be defined, decomposed, and solved through analysis.

**Messy Problem** (complicated but definable; some wicked characteristics present):
- Proceed with pipeline but flag areas of definitional instability and causal uncertainty.
- Use Constraint Mapping mode. Expect iteration on the problem definition.
- Explicitly note which aspects are tractable and which resist stable formulation.

**Wicked Problem** (many questions answered in the intractable direction):
- Do not produce a single "answer." The problem does not have one.
- Shift output to: mapping the problem space, identifying leverage points, surfacing trade-offs and value conflicts, and proposing small reversible experiments.
- Use Paradigm Suspension or Cui Bono modes as appropriate.
- Explicitly state the wickedness classification in the output so the user understands why the response takes the form it does.
- Flag any confidence in the response that exceeds what the problem structure warrants.

---

## Integration Notes

- This module runs as a gate-level diagnostic BEFORE other Tier 2 domain modules and before mode selection. Its output shapes how the rest of the pipeline operates.
- For political/social/policy problems, run this checklist first, then load the Political and Social Analysis Module. The wickedness classification determines how that module's questions are applied.
- When the classification is "wicked," the Problem Definition Question Bank's Category 6 (Quality Check) should be applied with the understanding that definitional stability may be structurally impossible, not just incomplete.
- The diagnostic scoring is not a numeric score. It is a qualitative assessment based on the pattern of answers across all five categories.
