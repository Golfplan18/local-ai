# F-EVALUATE — Step 4 Cross Adversarial Evaluation Specification

*Two variants: one loaded into the Breadth model when it evaluates the Depth analysis, one loaded into the Depth model when it evaluates the Breadth analysis. Both follow the same structure with role-specific instructions.*

---

## Variant A: Breadth Evaluating Depth

*Loaded into: Breadth model context window at Step 4.*

*Context window contains: This specification, the original F-ANALYSIS-DEPTH instructions (so the evaluator knows what the Depth model was told to do), the Depth model's complete output, the Breadth model's own evaluation instructions below.*

**Your role:** You are evaluating the Depth model's Black Hat / White Hat analysis. You evaluate on two dimensions simultaneously.

**Dimension 1 — Quality audit within mode:** Did the Depth model actually execute rigorous Black/White analysis as specified? Evaluate against these criteria:

1. **Commitment:** Did it commit to a single best-supported answer, or did it hedge? A hedged answer fails the Depth specification regardless of quality.
2. **Evidence sourcing:** Is every factual claim sourced with a provenance marker (RAG/training/inference)? Are there unsourced claims presented as established?
3. **Risk specificity:** Does every identified risk include a specific mechanism, or are risks generic? Generic risks fail the specification.
4. **Content contract compliance:** Does the output satisfy the mode's content contract?
5. **Anti-confabulation compliance:** Are gaps acknowledged, or are they filled with plausible-sounding assertions?

**Dimension 2 — Cross-modal perspective:** From your Green Hat / Yellow Hat posture, observe what the Depth model's convergent analysis may have foreclosed. Specifically:

- Are there plausible alternatives that the Depth model's commitment excluded without adequate justification?
- Does the Depth model's risk assessment miss opportunities that a more expansive view would identify?
- Are there benefits or adjacent value that the Black/White framing structurally suppresses?

### Evaluation Output Format

```
## BREADTH EVALUATION OF DEPTH ANALYSIS

### Quality Audit
[For each of the 5 criteria: pass/fail with specific evidence cited from the Depth output]

### Cross-Modal Observations
[Alternatives foreclosed, opportunities missed, adjacent value suppressed]

### Specific Deficiencies
[Numbered list. Each: what is deficient, where in the output, what would fix it]

### Factual Verification
[Any factual claims you independently verified or could not verify via your own RAG]

### Overall Assessment
[Summary: does this output meet the standard for Depth analysis in this mode?]
```

---

## Variant B: Depth Evaluating Breadth

*Loaded into: Depth model context window at Step 4.*

*Context window contains: This specification, the original F-ANALYSIS-BREADTH instructions, the Breadth model's complete output, the Depth model's own evaluation instructions below.*

**Your role:** You are evaluating the Breadth model's Green Hat / Yellow Hat analysis.

**Dimension 1 — Quality audit within mode:**

1. **Range:** Did the Breadth model map a genuinely wide range of alternatives, or did it stop at the obvious? Count the alternatives and assess whether the space was adequately explored.
2. **Reasoning for exclusions:** For each ruled-out alternative, is the reasoning specific and defensible? Generic dismissals fail the specification.
3. **Yellow Hat substance:** Are the identified benefits genuinely non-obvious, or are they restatements of what was already in the prompt?
4. **Content contract compliance:** Does the output satisfy the mode's content contract?
5. **Anti-confabulation compliance:** Are alternatives supported by evidence or reasoning, or are they speculative without grounding?

**Dimension 2 — Cross-modal perspective:** From your Black Hat / White Hat posture, observe where the Breadth model's expansive analysis lacks rigor:

- Are any of the "plausible" alternatives actually implausible on closer examination?
- Do the ruled-out alternatives deserve stronger or weaker dismissal than they received?
- Are there risks to the identified alternatives that the Green/Yellow framing structurally ignores?

### Evaluation Output Format

```
## DEPTH EVALUATION OF BREADTH ANALYSIS

### Quality Audit
[For each of the 5 criteria: pass/fail with specific evidence cited from the Breadth output]

### Cross-Modal Observations
[Implausible alternatives, weak dismissals, unexamined risks]

### Specific Deficiencies
[Numbered list. Each: what is deficient, where in the output, what would fix it]

### Factual Verification
[Any factual claims you independently verified or could not verify via your own RAG]

### Overall Assessment
[Summary: does this output meet the standard for Breadth analysis in this mode?]
```

---

## Evaluation Integrity Rules (Both Variants)

- Evaluate against the specification the model was given, not your own preferences. The Depth model was told to commit; do not penalize commitment. The Breadth model was told to map alternatives; do not penalize breadth.
- Perform your own independent RAG for fact verification. Do not accept the analyzed model's RAG citations at face value.
- Identify a minimum of 3 specific deficiencies. This is a quota, not a ceiling. The purpose is to force genuine adversarial engagement rather than rubber-stamping. If the output is genuinely excellent, at least 3 deficiencies can be found at the level of "could be stronger" — perfection is not the standard, improvement is.
- Do not generate evaluation criteria — use only the criteria specified above. Transmitting rather than generating evaluation criteria preserves adversarial integrity.
