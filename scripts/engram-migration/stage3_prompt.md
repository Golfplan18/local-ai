# Stage 3 — Triage and Specifics (Haiku)

ONE-TIME MIGRATION PROMPT. Deleted with the rest of `scripts/engram-migration/`
once the engram permanent-note migration lands.

You are processing **units** from a corpus of auto-extracted knowledge notes. A
unit is either a single note or a small group the embedding model found
near-identical.

You do exactly two things. Neither of them involves writing, generalizing,
summarising, or judging the claims. A later stage reads the member titles
directly and does all of that.

## 1. Verdict

- **KEEP** — the unit contains at least one claim about how something works
  that a later stage could raise into a transferable principle.
- **RESOURCES** — bare fact or source material worth keeping but not a
  knowledge building block. Only when it is BOTH (a) not general knowledge a
  competent AI already carries, AND (b) personal, local, or proprietary to this
  user — their own observation, their own measurement, their own project, their
  own fiction.
- **ARCHIVE** — general-knowledge fact; a dated news item; a one-off event with
  no transferable structure; or content too thin to carry a claim.

Nothing is deleted. ARCHIVE moves the unit to a holding folder. Decide honestly
anyway — archived notes will probably never be revisited.

When members of a unit disagree, the unit takes the **most preserving** verdict
present: KEEP beats RESOURCES beats ARCHIVE.

## 2. Specifics, verbatim

Every proper noun, number, date, statistic, monetary amount, and technical term
appearing anywhere in the unit's members. Copy them **exactly as written**. Do
not normalise, round, expand, correct, or deduplicate near-misses — if two
members say "1979" and "the late seventies", both go in the list.

This is the evidence layer and the keyword-search surface of the final note.

Source filenames are mechanical identity only. They are not evidence and are
not included in the material you inspect. Never extract a date, name, slug
fragment, or any other specific from a filename.

**Never add a specific that does not appear in the source.** If the unit carries
no concrete specifics, return an empty list. Do not supply plausible ones — an
invented specific is indistinguishable from a real record.

Each specific must be one contiguous substring copied from one source field,
identical in case, punctuation, and spacing. Never join separate fragments,
restore or infer a person's full name, or supply any name not written exactly in
that source field.

## What you must not do

- **Do not list, restate, paraphrase, or count the claims.** An earlier version
  of this prompt asked for that and produced 26 entries per unit that were
  simply the members' own bullets split apart. The next stage reads the member
  titles itself.
- **Do not write a title.** Do not raise the level of abstraction. Do not name
  the underlying concept.
- **Do not judge whether members are duplicates.** They usually are not — they
  are facets of one concept — and deciding that is the next stage's job.

## Output

A JSON array, one object per unit, written to the output path given in your
instructions:

```json
[
  {
    "unit_id": "u000123",
    "verdict": "KEEP",
    "member_files": ["2025-06-02_....md", "2025-11-14_....md"],
    "specifics": ["Crown Castle", "American Tower", "$45,000", "1979", "Section 232"],
    "note": ""
  }
]
```

`note` is for anything that went wrong with the unit; leave it empty otherwise.
Every unit in your shard gets exactly one record. Return only summary counts in
your reply — the file is the deliverable.
