# Design Analysis Module

*Tier 2 module. Loads into the Breadth model context window as a complete unit.*

## Trigger Conditions

- Domain involves creative or professional design work
- Prompt references design problems, user experience, product development, or service design
- Problem involves visual design, interaction design, information architecture, or design strategy

## Purpose

This module provides domain-specific questions for design analysis. It complements Tier 1 tools by directing attention to user behavior, design intent, material and medium constraints, and the gap between what a design communicates and what its creator intended. Design problems are characteristically underdetermined -- they have no single correct solution -- so these questions focus on sharpening the design intent and revealing hidden constraints rather than converging on answers.

---

## Category 1: User and Context

These ground the design problem in the reality of who uses it and where.

1. Who is the primary user, and what are they trying to accomplish when they encounter this design? (Not in the abstract -- in the specific moment of use.)
2. What is the user's state when they arrive? (Rushed, browsing, anxious, expert, first-time, distracted, on mobile, at a desk.)
3. What does the user do immediately before and immediately after interacting with this design? What is the surrounding workflow or experience?
4. What is the user's existing mental model? What do they expect this to look like and behave like, based on prior experience?
5. Who are the secondary users, edge-case users, and non-users who are nonetheless affected?

## Category 2: Design Intent and Strategy

These clarify what the design is trying to achieve at the strategic level.

6. What is this design's job? State it as: "When [situation], the user wants to [motivation], so they can [outcome]."
7. What should the user think, feel, or do differently as a result of encountering this design?
8. What is the single most important thing this design must communicate? If the user gets nothing else, what must they get?
9. What is the business or organizational objective this design serves? Where does design intent conflict with business intent?
10. What is being deliberately excluded from this design? What is the "not this" that defines its boundaries?

## Category 3: Form, Medium, and Material

These address the physical and technical realities that constrain the design.

11. What are the hard constraints of the medium? (Screen size, load time, print resolution, physical dimensions, material properties, manufacturing process.)
12. What are the constraints imposed by adjacent systems? (Design systems, brand guidelines, platform conventions, accessibility requirements, regulatory requirements.)
13. What precedents and conventions exist in this medium or genre? Which ones should be followed and which challenged?
14. What does this design cost to produce, deploy, and maintain? Are those costs proportional to the value it delivers?
15. How does this design degrade? (Slow connection, small screen, assistive technology, translation to another language, black-and-white printing.)

## Category 4: Composition and Hierarchy

These examine how the design organizes information and attention.

16. What is the visual or information hierarchy? What does the user see first, second, third?
17. Where is the user's eye drawn, and is that where it should be drawn?
18. What is the ratio of signal to noise? What elements are not earning their place?
19. How does the design handle progressive disclosure -- revealing complexity only when needed?
20. Is the structure of the design legible? Can the user understand the organization without instruction?

## Category 5: Evaluation and Critique

These test whether the design is working.

21. If this design were stripped of all labels and text, would its structure and hierarchy still communicate? (The squint test.)
22. What would a user who has never seen this before understand in the first five seconds?
23. Where is the design creating unnecessary cognitive load -- making the user think about the interface instead of their task?
24. What is the most common mistake a user will make with this design? What happens when they make it?
25. How does this design compare to the best existing solution to the same problem? What does it do better, and what does it do worse?

## Category 6: Process and Iteration

These address the design process itself.

26. What assumptions about the user have not been tested? What is the cheapest way to test them?
27. What is the riskiest element of this design -- the part most likely to fail with real users? Can it be prototyped and tested independently?
28. What feedback is available from existing users, analytics, or prior versions? Has it been consulted?
29. Is this design being evaluated against the right criteria? (A design optimized for first-use clarity may sacrifice expert efficiency, and vice versa.)
30. What is the iteration plan? How will this design be refined after initial deployment, and what signals will trigger revision?

---

## Integration Notes

- Category 1 (User and Context) generates inputs that OPV needs -- design stakeholders include users, clients, developers, and the people affected by the designed system.
- Category 2 (Design Intent) maps directly to AGO -- the design's aims, goals, and objectives at three levels.
- Category 5 (Evaluation) complements PMI by providing design-specific criteria for the Plus, Minus, and Interesting assessment.
- Design problems are frequently underdetermined. APC is especially valuable in this domain -- it should generate multiple design directions rather than converging on one.
