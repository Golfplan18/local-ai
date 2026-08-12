# Stage 5 — Permanent Note Writer (local-model variant)

ONE-TIME MIGRATION PROMPT. Deleted with the rest of `scripts/engram-migration/`.

A compressed rewrite of `stage5_prompt.md` for local models. Same task, two
changes traced to measured failures on Qwen3.5-122B:

1. **The output contract leads.** In the long prompt the `Instance:` rule sat
   deep in the body and only 2 of 10 notes carried one — an 80% HARD failure
   rate. Structure now comes first and is repeated as a checklist at the end.
2. **`standard_concept` defaults to empty.** The long prompt invited a canonical
   name and got `"Choice Causality Design"` — an invented term, capitalised to
   look established, then promoted into the title. An empty field costs nothing
   (a later pass can fill it); a plausible fake poisons keyword search and is
   undetectable by any checker.

---

## Your task

You are given **units**. A unit is one or more auto-extracted notes that all
concern the same concept. For each unit, write ONE note.

## Output contract — every note has exactly this shape

```
new_title  : one sentence stating the general claim
new_body   : 2-5 lines. Each line starts with "- ".
             The LAST line MUST start with "- Instance:"
```

**The `Instance:` line is mandatory. A note without it is discarded.** It carries
the concrete case using ONLY the words in that unit's `specifics` list. If
`specifics` is empty, the line is exactly:

`- Instance: none recorded in source.`

Never put a name, number, or example in the Instance line that is not in
`specifics`. Inventing one corrupts the record permanently.

## The title states the general principle

The member titles are stuck to their own subject matter. Your title states the
claim so it applies elsewhere.

- Member titles: *"Honnold memorizes every hold before a climb"*, *"Surgeons
  rehearse the procedure step by step"*
- Your title: **"Pre-memorization converts problem-solving under stress into
  rehearsed performance"**

Never put in a title: a person's or company's name, a year, a `because…` /
`when…` clause, a hedge (can/may/often/typically), a count ("three types"), or
an absolute (never/always/cannot/proves).

If the only general version you can write is a truism — "systems favour the
powerful" — set `verdict` to `ARCHIVE` instead. That is a correct answer.

## The body absorbs every distinct claim

Members are usually different facets of one concept — one gives the pattern,
another the cause, another the consequence. Give each distinct facet its own
line. The member notes are deleted after this, so a facet you leave out is gone.

Write mechanism lines about ROLES, not individuals: *the incumbent*, *the
regulator*, *the performer*. Active voice.

## standard_concept — leave it empty unless you are certain

Fill it ONLY with a term that already exists in the literature and that a reader
would find in a textbook or encyclopedia — *moral hazard*, *regulatory capture*,
*operant extinction*, *objective correlative*, *routinization of charisma*.

If no such established term applies, the value is `""`.

**Do not construct a term.** Do not capitalise a description to make it look
official. `"Choice Causality Design"`, `"Bad faith reasoning"`, and
`"Emotional Containment Theory"` are not concepts — they are inventions, and
they are worse than an empty field. When in doubt, leave it empty.

If you do fill it, the term must also appear verbatim in the title or a body
line.

## Output

A JSON array ONLY. Start with `[`, end with `]`. No preamble, no code fence, no
commentary. One object per unit:

`unit_id`, `verdict` (`KEEP` or `ARCHIVE`), `standard_concept`, `new_title`,
`new_body`

## Before you emit, check each note

1. Does `new_body` have a line starting `- Instance:`?  If not, add it.
2. Does the Instance line use only words from `specifics` (or say "none
   recorded in source")?
3. Is `standard_concept` either an established textbook term or empty?
4. Is the title free of names, years, hedges, and `because` clauses?
5. Does every distinct member claim appear as its own body line?
