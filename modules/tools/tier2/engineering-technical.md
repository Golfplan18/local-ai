# Engineering and Technical Analysis Module

*Tier 2 module. Loads into the Breadth model context window as a complete unit.*

## Trigger Conditions

- Domain is technical, engineering, product design, or systems implementation
- Prompt involves diagnosing a failure, designing a solution, or specifying requirements
- Problem involves hardware, software, infrastructure, manufacturing, or technical systems

## Purpose

This module provides domain-specific questions for engineering and technical analysis. It complements Tier 1 tools by directing attention to failure modes, interface boundaries, requirement gaps, and system-level interactions that general-purpose reasoning tends to under-examine.

---

## Category 1: Requirements and Specification

These surface what the system actually needs to do vs. what has been stated.

1. What are the unstated requirements? What does the user assume the system will do that has not been explicitly specified?
2. What are the boundary conditions? What happens at the edges of the operating envelope -- maximum load, minimum input, zero users, a million users?
3. What are the non-functional requirements (performance, reliability, security, maintainability, cost) and which ones dominate? Has this been made explicit?
4. Who are all the users and operators of this system? Are there users whose needs conflict with each other?
5. What does "done" look like? What acceptance criteria distinguish a working solution from an incomplete one?

## Category 2: Failure Mode Analysis

These direct attention to how things break.

6. What is the most likely failure mode? What is the most catastrophic failure mode? Are they the same?
7. What happens when this system fails? Does it fail safe, fail loud, or fail silently?
8. What are the single points of failure? Where does one component's failure cascade to others?
9. What are the failure modes at interfaces between components, teams, or systems? (Interface failures are the most common and least-analyzed category.)
10. What has failed before in similar systems? What does the incident history reveal about recurring failure patterns?

## Category 3: System Interactions and Dependencies

These map the connections between components.

11. What are the dependencies -- upstream and downstream? What does this system consume, and what consumes it?
12. What shared resources (databases, networks, APIs, personnel, physical space) create coupling between components that appear independent?
13. Where are the feedback loops in the system? Are any of them positive feedback loops that could produce runaway behavior?
14. What happens to this system when its environment changes? (Load increases, upstream API changes, team members leave, vendor goes out of business.)
15. What are the implicit assumptions about the operating environment? (Network is available, power is stable, data is clean, users are trained.)

## Category 4: Design Trade-offs

These make explicit the trade-offs embedded in the design.

16. What are the primary trade-offs in this design? (Performance vs. cost, flexibility vs. simplicity, speed vs. reliability, security vs. usability.)
17. Which constraints are physical/logical necessities and which are design choices that could be revisited?
18. What is being optimized for, and what is being sacrificed as a result?
19. What would a ten-times simpler version of this look like? What functionality would it lose, and does that functionality actually matter?
20. Is this design solving the problem at the right level of abstraction? Could the problem be dissolved by operating at a different layer?

## Category 5: Implementation and Operation

These address the gap between design and working system.

21. What is the deployment path? How does this get from design to production, and what can go wrong at each step?
22. How will this be monitored in operation? What signals indicate that it is working, degrading, or failing?
23. How will this be maintained? Who maintains it, and what do they need to know?
24. What is the migration path from the current state? Can the transition be done incrementally, or does it require a hard cutover?
25. What is the operational cost over the full lifecycle, not just the build cost?

## Category 6: Diagnostic Questions (for failure investigation)

Use these when the prompt involves diagnosing an existing failure or malfunction.

26. What changed? Identify the most recent change to the system, its environment, its inputs, or its load.
27. What is the actual behavior vs. the expected behavior? State both precisely, without interpretation.
28. Can the failure be reproduced? Under what conditions?
29. What has been ruled out and how? Are the elimination steps actually valid, or do they contain assumptions?
30. Is this a new failure, or an old failure that was previously undetected?

---

## Integration Notes

- Category 1 feeds directly into AGO (clarifying what the technical objective actually is) and CAF (surfacing factors the prompt did not mention).
- Category 2 (Failure Modes) should be run proactively during design work, not only after failures occur.
- Category 3 (System Interactions) produces inputs for C&S -- consequences of changes propagate through the dependency map.
- Category 6 (Diagnostic) is a self-contained sequence for failure investigation; it runs before the standard tool sequences when the prompt describes a broken system.
