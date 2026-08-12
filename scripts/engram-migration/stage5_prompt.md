# Stage 5 — Write the Permanent Note (Opus)

ONE-TIME MIGRATION PROMPT. Deleted with the rest of `scripts/engram-migration/`
once the engram permanent-note migration lands.

You convert a **unit** — one or more auto-extracted notes the embedding model
grouped as the same concept — into **one permanent note**.

This is the step the whole migration exists for. Everything before it sorted and
extracted; nothing before it raised a claim's level of abstraction, and nothing
after it will.

## What a permanent note is

A literature note records what a source said, bound to its context. A permanent
note states the claim in general form, detached from the source, at a level of
abstraction that transfers to other domains. The specific case survives beneath
the claim as evidence, never as the claim itself.

The failure that produced this corpus: the extractor was told to "name what does
what", so it wrote *"Honnold eliminates execution uncertainty by memorizing every
hold and movement sequence before attempting a climb"*. The transferable claim
was *"pre-memorization converts problem-solving under stress into rehearsed
performance, removing execution variance"* — which reaches surgery, litigation,
aviation, and public speaking. Your job is that conversion.

## Your input per unit

- `member_titles` — the claim each source note made. **These are your facets.**
- `specifics` — proper nouns, numbers, dates, and technical terms extracted
  verbatim from the members. **This is the only material your Instance line may
  draw on.**
- `verdict`, `unit_id`, `member_files` — pass through unchanged.

You do **not** receive the member bodies. The titles carry the claims; if a
title is too thin to yield a claim, say so in `note` rather than inventing one.

## Absorb every facet

Members of a unit are usually **not duplicates**. They are facets of one
concept — one states the pattern, another the cause, another the mechanism,
another the consequence, another the magnitude. A five-member unit typically
carries three or four genuinely different claims.

Your note must carry **all of them**. Write the general claim as the title and
give each distinct facet its own body bullet. A facet you drop dies here: the
member notes are deleted once this note is written.

Do not pick the best member and discard the rest. That is the failure this stage
was designed to prevent.

## Title

One declarative sentence stating the claim. NEVER put in a title:

- proper nouns (people, companies, statutes, products, places) unless the note
  exists to define that entity
- dates, years, "currently", "recently"
- a `because…` / `when…` / `by …ing` clause explaining the mechanism — the title
  asserts THAT, the body explains HOW
- a domain qualifier that is not load-bearing ("in coal towns", "in early
  dating", "in narrative")
- hedges that dissolve the claim (can, may, often, typically, sometimes)
- inventory counts ("nine major areas", "three types")
- the user's private vocabulary or fiction character names
- absolutes the body does not establish: no "cannot", "always", "never",
  "proves"

**Where a standard name for the concept exists — salience bias, moral hazard,
regulatory capture, debt peonage, operant extinction, routinization of charisma,
Goodhart's law, attributional ambiguity, techniques of neutralization — use it
verbatim in the title**, or failing that verbatim in a body bullet, and record it
in `standard_concept`. This corpus is searched by keyword *and* by meaning; a
note matching neither is dead. Naming the concept only in `standard_concept` is
a failure, not a partial success.

If no standard name exists, leave `standard_concept` empty. Do not invent a
term that sounds canonical — a plausible fake term is worse than none, because
it pollutes the vocabulary and misleads every later search.

Impose no length limit. A correct general claim comes out short as a
consequence, never as a target. Never truncate meaning to hit a word count.

## Body

Bullets, one per distinct facet, then the Instance line.

- Mechanism bullets state how the thing works in **domain-neutral** terms. Name
  the ROLE that acts — the incumbent, the regulator, the borrower, the
  performer — not the individual who acted in the source. Active voice: every
  bullet says what does what. No "it" / "they" / passive.
- The final bullet begins `Instance:` and carries the specific case using
  **only** entries from the supplied `specifics` list. You may join them into
  readable prose. You may not add a name, number, date, or example that is not
  in that list. If `specifics` is empty, write
  `Instance: none recorded in source.`
- The Instance line is also the keyword surface, so use the domain vocabulary
  from `specifics` rather than paraphrasing it away.

## The failure mode to avoid

Over-generalization into platitude. *"Systems tend to favour those with power"*
is useless. The general claim must stay **falsifiable** and **specific about
mechanism** — raised one level, not dissolved.

If raising the level would produce a platitude, set `verdict` to `ARCHIVE` and
explain in `note`. A thin unit is archived, never inflated into a claim the user
never made. Archiving is a legitimate outcome and is not a failure on your part.

## Output

A JSON array, one object per unit, written to the path in your instructions:

```json
[
  {
    "unit_id": "u000123",
    "verdict": "KEEP",
    "member_files": ["2025-06-02_....md"],
    "standard_concept": "structural separation",
    "new_title": "Structural separation of the physical asset from the operating service turns every competitor into a tenant of one landlord",
    "new_body": "- The asset owner builds and maintains the fixed structure, then rents capacity to every operator competing above it.\n- Each operator avoids duplicating the capital cost and pays rent instead, which turns a barrier to entry into an operating expense.\n- The asset owner captures revenue from the whole sector rather than one share of it, so the rent survives competitive churn that destroys individual operators.\n- Instance: Crown Castle and American Tower own the towers; Verizon, AT&T, and T-Mobile lease space on the same structures.",
    "facets_absorbed": 3,
    "note": ""
  }
]
```

Writing the file is the deliverable. Reply with one short line when done.
