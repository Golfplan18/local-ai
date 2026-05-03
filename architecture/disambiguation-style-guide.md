
# Reference — Disambiguation Style Guide

This document is the canonical style guide governing every user-facing disambiguation question Ora produces across the four-stage pre-routing pipeline (intent surfacing, territory disambiguation, input completeness check, and final mode selection). It establishes permitted and forbidden vocabulary, sanctioned question patterns, naming and parenthetical conventions, anti-patterns to refuse, default routing when the user does not respond cleanly, escalation hooks for handing off from a lighter mode to a heavier one, and the response patterns the input completeness checker uses when required input is missing or underspecified. The guide assumes the user is not a methodologist; every question Ora asks must be answerable in plain English by a domain expert who has never read a registry entry in their life.

---

## §5.1 Permitted Vocabulary

Disambiguation questions may draw freely from the following five vocabularies:

- **Situation language** — "Are you trying to decide…?", "Are you looking at…?", "Is this about…?"
- **Goal language** — "Do you want a quick read or a thorough one?", "Are you weighing options or stress-testing one?"
- **Stance language in plain words** — "Are you trying to make the case for it, against it, or look at both sides?"
- **Concrete artifact language** — "Is this an argument someone made, a decision you face, a plan you're considering, or a situation you're trying to understand?"
- **Time-budget language** — "Quick scan? Careful look? Deep dive?"

These vocabularies share a common property: each frames the question in terms the user already holds in mind when they bring an item to Ora. None requires the user to learn a label.

---

## §5.2 Forbidden Vocabulary

Disambiguation questions must never contain any of the following:

- Mode names (Cui Bono, Steelman, ACH, etc.) — except in parentheses for educational labeling, governed by §5.4 and §5.9.
- Territory names used as taxonomy labels.
- "Analysis type," "epistemological posture," "atomic vs. molecular," "depth tier."
- Methodology names (Walton, Toulmin, Heuer, Pearl, Tetlock) outside parentheses.
- Internal jargon: "gradation," "stance variant," "molecular composition."

If a draft question cannot be cleansed of forbidden vocabulary while still asking what needs to be asked, the question itself is malformed and must be rewritten from the user's vantage point, not Ora's internal taxonomy.

---

## §5.3 Question Patterns

Five patterns cover the full disambiguation space. Each is the canonical phrasing for its job; variations are permitted as long as they preserve the structure and stay within §5.1 vocabulary.

**Pattern A — Intent disambiguation (territory-level).**

> "Quick check on what you're after — are you mostly trying to: (a) figure out who benefits from this; (b) check whether the argument holds up; (c) decide what to do; (d) understand why this happened?"

**Pattern B — Situation disambiguation.**

> "Is this a decision you have to make yourself, or a situation involving several parties whose interests differ?"

**Pattern C — Depth disambiguation.**

> "Want a quick read first, or should I take the longer route — work through the angles carefully and bring it together at the end?"

**Pattern D — Stance disambiguation.**

> "Want me to make the strongest case for it, the strongest case against it, or look at it neutrally?"

**Pattern E — Specificity disambiguation.**

> "Is the question about how this works mechanically, or about how the parts of it relate structurally?"

---

## §5.4 Parenthetical Naming Convention

When a mode name is informative and the user is engaged, the mode name may appear in parentheses **after** the plain-language question, italicized, never as the question itself:

> "Want me to make the strongest possible case for it (*sometimes called a steelman*) before we look at weaknesses?"

The plain-language description carries the question. The parenthetical names the technique only as a courtesy to a user who may want to learn the term. See §5.9 for the strict format.

---

## §5.5 Anti-Patterns

The following malformed question shapes must be refused at draft stage. Each illustrates a different failure mode.

| Anti-pattern | Example | What it gets wrong |
|---|---|---|
| Naming the taxonomy | "Should I run a Cui Bono Analysis or a Wicked Problems Analysis?" | Forces user to know the registry |
| Asking about epistemology | "Do you want a constructive or adversarial epistemological posture?" | Jargon |
| Binary forcing on a non-binary | "Quick or deep?" when a middle option fits | Loses the Tier-2 default |
| Question stacks | "Are you (a) deciding (b) about a problem (c) involving stakeholders (d) under uncertainty?" | Overwhelms |
| Asking the user to classify | "Is this a wicked problem?" | Wicked-problem-ness is something analysis reveals, not pre-declared |
| Asking about output format too early | "Do you want this as a matrix, prose, or bullet list?" | Output format is final-stage |

---

## §5.6 Default Path

When the user does not respond to a disambiguation question, or responds ambiguously, Ora must default along the following axes rather than re-asking:

- **Tier-2 (thorough atomic)** by default — never Tier-1 by default, never Tier-3 by default.
- **Neutral stance** when the territory has a stance axis and the user has not signaled.
- **General specificity** when the territory has a specificity axis.

The default path exists so that silence or brevity from the user produces useful work, not a stalled interrogation.

---

## §5.7 Escalation Hooks

When a Tier-1 or Tier-2 mode finishes and detects conditions warranting heavier analysis, the mode emits an *escalation hook* — a short offer to climb to a heavier sibling, framed in the same plain language the original disambiguation used:

> "Quick read complete. The structure here looks like there are competing causes that interact — want me to take the deeper run? (*This would be the systems-dynamics version.*)"

Escalation hooks are offers, not auto-runs. The user must accept before the heavier mode executes. The parenthetical follows §5.9 format.

---

## §5.8 Completeness-Check Response Patterns

Stage 3 of the pre-routing pipeline checks whether the prompt actually contains the input the candidate mode needs to run. When it does not, Ora replies in one of three patterns below. All three are tonally identical to §5.3 — plain English, no taxonomy, no methodology jargon as primary content.

### 5.8.1 Missing-input prompt

Used when a mode's required input is wholly absent from the prompt.

**Canonical pattern:** *"To run [plain-language version of the analysis], I need [plain-language version of what's missing]."*

**Positive examples (good):**

1. "To weigh how this decision lands for the people affected, I need to know roughly who they are — even just two or three groups will do."
2. "To check whether the argument holds together, I need the actual claim it's making, not just the topic. What's the conclusion the writer wants you to reach?"
3. "To look at what could go wrong with the plan, I need a sketch of the plan itself — even one or two sentences about what you'd do."

**Negative examples (bad — these violate the guide):**

1. "Stakeholder Impact Analysis requires a stakeholder list as input." *(uses mode name; treats the user as a methodologist)*
2. "Cannot route to argument-validity territory without an explicit conclusion variable." *(taxonomy and jargon; reads like an error message)*

### 5.8.2 Underspecified-input prompt

Used when the required input is present but ambiguous, vague, or carries multiple plausible readings.

**Canonical pattern:** *"I have [what's present] but need to know more about [what's underspecified] before I can [plain-language version of the analysis]."*

**Positive examples (good):**

1. "I have the article you sent, but I'm not sure which claim in it you want me to push back on — the headline claim, or the recommendation at the end?"
2. "I have the decision in front of me, but the constraint you mentioned — 'budget' — could mean a hard cap, a target, or a rough comfort zone. Which is it?"
3. "I have the situation you described, but it could either be a problem you're trying to solve or a pattern you're trying to understand. Which way are you leaning?"

**Negative examples (bad — these violate the guide):**

1. "Input ambiguity detected on the stance axis — please specify constructive or adversarial posture." *(jargon; presents the mode's internal axes as the user's vocabulary)*
2. "ACH requires disambiguation between competing hypotheses; please enumerate them." *(mode acronym used as primary content; assumes the user knows what enumeration is required)*

### 5.8.3 Graceful-degradation offer

Used when the input required for the heavier mode is missing, but a lighter sibling mode could run usefully on what is present. The pattern offers the lighter run rather than blocking on the missing input.

**Canonical pattern:** *"I can run a lighter version with what's here, or wait for [what's needed] and do the fuller [plain-language version]. Which would you like?"*

**Positive examples (good — each pairs a heavier mode with its lighter sibling):**

1. "I can give you a quick read on who's likely to gain or lose from this with what's here, or wait for the actual stakeholder list and do the more careful walk-through. Which would you like?"
2. "I can do a quick logic check on the argument as written, or — if you have the source it's responding to — I can do a fuller comparison of both sides. Which is more useful right now?"
3. "I can sketch a fast list of what could go wrong, or — if you can give me a few sentences on the plan itself — I can take the longer route and walk through how the failures would unfold. Your call."

**Negative examples (bad — these violate the guide):**

1. "Tier-1 atomic mode is available; Tier-2 molecular mode requires additional input. Select gradation." *(every word is forbidden vocabulary)*
2. "I can downgrade to a lighter mode in the same territory, or you can supply the missing variable for the full mode." *(taxonomy plus the word "downgrade," which frames the lighter run as a failure rather than a real offer)*

---

## §5.9 Educational Parenthetical Convention

Where a parenthetical name is included (per §5.4 or §5.7), the format is strictly:

> **plain language *(named technique)*** — never **named technique *(description)***

The plain-language phrasing carries the question; the named technique appears only in italicized parentheses afterward. Acronyms are not used in technique names unless the acronym is canonical **and** its letters are expanded for the reader. So:

- Permitted: "weighing the strengths, weaknesses, opportunities, and threats of the plan (*sometimes called SWOT analysis — strengths, weaknesses, opportunities, threats*)" — SWOT is canonical and the letters are spelled out.
- Permitted: "making the strongest possible case for it (*sometimes called a steelman*)" — steelman is the canonical name and there is no acronym to expand.
- Not permitted: "Run a SWOT?" — bare acronym, no plain language carrying the question.
- Not permitted: "Cui Bono *(figuring out who benefits)*" — the format is reversed; the name is leading, the description is parenthetical.

This convention makes the technique name a courtesy label for an engaged reader, never a gating term the reader must already know.

---

## §5.10 Governance

Changes to this style guide require user review. The author of this system is a non-programmer with deep domain expertise, and the tonal calibration of disambiguation questions is high-stakes for user experience: a single jargon-leak or anti-pattern, repeated across thousands of routings, degrades the entire interaction surface of the system. No change to permitted vocabulary, forbidden vocabulary, question patterns, parenthetical conventions, default-path rules, escalation-hook phrasing, or completeness-check response patterns may be made by an automated process or a downstream agent without the user reviewing and approving the change first.

---

*End of Reference — Disambiguation Style Guide.*
