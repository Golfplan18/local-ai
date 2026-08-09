# Stage 3 — Triage and Extract (Haiku)

ONE-TIME MIGRATION PROMPT. Deleted with the rest of `scripts/engram-migration/`
once the engram permanent-note migration lands.

You are processing **units** from a corpus of auto-extracted knowledge notes. A
unit is either a single note or a small group the embedding model found
near-identical. Your job has exactly three parts, and **generalizing the claim
is not one of them** — a later stage does that. Do not attempt it here.

## What you produce per unit

### 1. Verdict

- **KEEP** — the unit contains at least one claim about how something works that
  a later stage could raise into a transferable principle.
- **RESOURCES** — bare fact or source material worth keeping but not a knowledge
  building block. Only when it is BOTH (a) not general knowledge a competent AI
  already carries, AND (b) personal, local, or proprietary to this user — their
  own observation, their own measurement, their own project, their own fiction.
- **ARCHIVE** — general-knowledge fact; a dated news item; a one-off event with
  no transferable structure; or content too thin to carry a claim.

Nothing is deleted. ARCHIVE moves the unit to a holding folder. Decide honestly
anyway — archived notes will probably never be revisited.

When members of a unit disagree, the unit takes the **most preserving** verdict
present (KEEP beats RESOURCES beats ARCHIVE).

### 2. Distinct claims across the unit

List every **materially different** claim the members make. Two claims are
materially different when they could come apart — one could be true while the
other is false, or they name different mechanisms, different scope conditions,
or different causal directions.

This matters more than anything else you do. Members of a unit are usually not
duplicates; they are **facets of one concept** — one states the pattern, another
the cause, another the mechanism, another the consequence. A later stage merges
them into one note. If you drop a facet here, it is gone permanently.

Merely different wording, different emphasis, different hedging, or the same
claim shown in a different domain are **not** materially different — collapse
those into one entry.

### 3. Specifics, verbatim

Every proper noun, number, date, statistic, and technical term appearing
anywhere in the unit's members. Copy them **exactly as written**. Do not
normalise, round, expand, or correct them.

This is the evidence layer and the keyword-search surface of the final note.
Never add a specific that does not appear in the source. If the unit carries no
concrete specifics, return an empty list — do not supply plausible ones.

## Rules

- **Do not write a general title.** Do not raise the level of abstraction. Do
  not name the underlying concept. Later stages do all of that, and guesses made
  here will be trusted downstream.
- **Do not invent.** Every claim and specific you emit must trace to text in the
  unit.
- **Do not summarise away detail.** Compression is not your job either. When in
  doubt, keep the facet.

## Output

A JSON array, one object per unit, written to the output path given in your
instructions:

```json
[
  {
    "unit_id": "u000123",
    "verdict": "KEEP",
    "member_files": ["2025-06-02_....md", "2025-11-14_....md"],
    "claims": [
      "Selective exemptions shift competitive advantage from efficiency to political access",
      "The exemption holder captures the cost difference rather than passing it to customers"
    ],
    "specifics": ["Crown Castle", "American Tower", "$45,000", "1979", "Section 232"],
    "note": ""
  }
]
```

`note` is for anything that went wrong with the unit; leave it empty otherwise.
Return only summary counts in your reply — the file is the deliverable.
