# Stage 9 — Decide and Perform Cross-Domain Merges (Opus)

ONE-TIME MIGRATION PROMPT. Deleted with the rest of `scripts/engram-migration/`
once the engram permanent-note migration lands.

Stage 8 nominated **candidate groups** of already-generalized permanent notes,
almost all because two or more independently received the **same canonical
concept name**. You decide, per group, whether they are one concept or several,
and write the merged note when they are one.

## Why the bar is high

Calibration on this corpus found that **every** sampled embedding cluster carried
a real distinction under adversarial review — 36 groups, three independent
judges, two refuters each, zero survived as pure duplicates. Assume a group has
a distinction until you have looked and failed to find one.

Two notes sharing a canonical concept name are often two **different claims about
that concept**, not two statements of it. "Costly signaling screens for genuine
intent" and "A sanction imposed on an advocate raises their standing with
sympathizers" are both costly signaling, and they are not the same claim.

The publisher's standard, in their words:

> "Related but subtly different notes often carry important distinctions. Those
> distinctions are where the real value lies. Similar notes that can't be
> distinguished from one another are duplicates that should be eliminated, but if
> a clear distinction can be identified, then there is something worthy of
> retaining."

## Decide

For each group, one of:

- **MERGE** — the members state the same claim, or facets of one claim. Write one
  note absorbing every facet. The members are then deleted.
- **SPLIT** — the members make claims that could come apart: one could be true
  while another is false, or they name different mechanisms, scope conditions, or
  causal directions. Leave every member untouched.
- **PARTIAL** — some members merge and others stand alone. Name exactly which
  unit_ids merge; the rest are left untouched.

A distinction is real when the claims could come apart. It is **not** real when
the difference is only wording, emphasis, hedging, or the same claim illustrated
in a different domain — that last case is precisely what this stage exists to
merge, since it is what embeddings could not see.

SPLIT is a legitimate and expected outcome. Do not manufacture merges to justify
the group.

## When you merge

Same rules that produced these notes, because the output is another permanent
note:

- Title: one declarative sentence. No proper nouns, dates, `because…`/`when…`/
  `by …ing` mechanism clauses, non-load-bearing domain qualifiers, hedges,
  inventory counts, private vocabulary, or unearned absolutes. Use the canonical
  concept name verbatim.
- Body: one bullet per distinct facet, in domain-neutral terms, naming the ROLE
  that acts. Every facet from every merged member must survive — a facet you drop
  dies here.
- Final bullet begins `Instance:` and may contain **only** specifics already
  present in the merged members' own Instance lines. Introduce nothing new.
- No length target. Short is a consequence of correctness.
- If merging would only be possible by retreating to a platitude, the answer is
  SPLIT.

## Output

A JSON array, one object per group, written to the path in your instructions:

```json
[
  {
    "group_id": "g000012",
    "decision": "MERGE",
    "merged_unit_ids": ["u000123", "u004567"],
    "standard_concept": "costly signaling",
    "new_title": "A signal persuades only when sending it costs the sender something an imposter could not afford",
    "new_body": "- The sender incurs a cost the audience can verify...\n- ...\n- Instance: ...",
    "facets_absorbed": 4,
    "distinction": "",
    "note": ""
  },
  {
    "group_id": "g000013",
    "decision": "SPLIT",
    "merged_unit_ids": [],
    "distinction": "One claims the cost screens for intent; the other claims a sanction raises standing with sympathisers. A movement whose sanctions raise no one's standing falsifies the second and leaves the first intact.",
    "note": ""
  }
]
```

For SPLIT and PARTIAL, `distinction` is mandatory and must name what would have
been destroyed. Writing the file is the deliverable; reply with one short line.
