# Stage 9 — Decide, Verify, and Synthesize Cross-Domain Merges

ONE-TIME MIGRATION SPECIFICATION. Deleted with the rest of
`scripts/engram-migration/` once the engram permanent-note migration lands.

Stage 8 produced a lossless candidate workload from already-generalized Stage 5
notes. Stage 9 uses three independent passes: first partition every candidate
group, then verify the whole connected components created by those proposals,
then synthesize only the verified final merge sets. Process every supplied item
and return only the requested JSON array.

## The merge bar

Assume a distinction exists until careful comparison fails to find one. Two
notes sharing a concept name or title vocabulary are commonly different claims
about the same subject. Merge only notes that state the same falsifiable claim,
or facets that must travel together as one claim.

The decisive test is whether the claims can come apart:

- If one claim could be true while another is false, keep them separate.
- Different mechanisms, causal directions, scope conditions, actors, outcomes,
  or exceptions are substantive distinctions.
- Different wording, emphasis, hedging, or source domain is not a distinction
  when the underlying falsifiable claim is the same.
- If unification requires retreating to a broad domain label or platitude, keep
  the notes separate.
- Zero merge sets is a valid and expected result.

Never merge to justify the candidate group. The purpose is to remove true
duplicates without erasing the distinctions that make permanent notes useful.

## Phase 1 — exact candidate-group partition

Input items contain `group_id`, candidate provenance, and complete Stage 5
abstractions for every group member. Return exactly:

```json
{
  "group_id": "g000012",
  "merge_sets": [["u000123", "u004567"]],
  "singleton_ids": ["u006789"]
}
```

Each `merge_sets` entry contains at least two unit IDs that state the same
falsifiable claim. `merge_sets` and `singleton_ids` must be disjoint and their
union must equal every member supplied for that group exactly once. Put every
member that does not belong in a merge set in `singleton_ids`. Do not omit a
member. Do not import a unit from another group.

## Phase 2 — whole-component verification

The runner forms deterministic connected components using only Phase 1's
accepted merge sets. A bridge can connect proposals such as A+B and B+C even
when A+C should not merge. Phase 2 therefore receives each whole component,
all member abstractions, and exact proposal provenance.

Return exactly:

```json
{
  "component_id": "c000012",
  "merge_sets": [["u000123", "u004567"]],
  "singleton_ids": ["u006789"]
}
```

Re-evaluate the whole component under the same falsifiable-claim standard.
Preserve a proposal, split it, or repartition bridge members as the complete
evidence requires. Again, the merge sets and singletons must be a disjoint exact
partition of every supplied component member. Only Phase 2 merge sets advance.

## Phase 3 — final synthesis

Each Phase 3 item is one verified merge set. It contains:

- the complete Stage 5 abstraction for every member;
- every nonempty `standard_concept` observed on those members; and
- a deterministic evidence catalog made only from original Stage 2 source
  titles and body lines across every member unit. The runner has already
  filtered this catalog to lines carrying a mechanically identifiable named,
  quoted, or measured particular; IDs are namespaced to this merge item.

Return exactly:

```json
{
  "merge_id": "m000012",
  "standard_concept": "costly signaling",
  "new_title": "A signal persuades only when its cost separates commitment from imitation",
  "mechanism_bullets": [
    "The sender accepts a cost that an uncommitted imitator would not bear.",
    "The observer treats the unequal willingness to pay as evidence of commitment."
  ],
  "facets_absorbed": 2,
  "evidence_id": "m000012:e000003"
}
```

The runner—not the model—chooses the lexicographically smallest unit ID as the
keeper, adds Markdown list markers, and copies the selected catalog text into
the final `Instance:` line. Return mechanism bullets as plain one-line strings:
no `- ` prefixes and no `Instance:` bullet.

### Synthesis requirements

- Title: one declarative sentence stating the merged claim. No proper nouns,
  dates, mechanism clauses, non-load-bearing domain qualifiers, hedges,
  inventory counts, private vocabulary, or unearned absolutes.
- Body bullets: one per distinct surviving facet, using domain-neutral roles and
  active language. Every unique facet from every merged note must survive.
- `standard_concept`: either empty or an exact nonempty concept string observed
  on a supplied member. Never invent, expand, normalize, or rewrite a concept.
  When nonempty, use it verbatim in the title or a mechanism bullet.
- `facets_absorbed`: the positive count of distinct source facets preserved in
  the synthesized note.
- `evidence_id`: select one supplied catalog entry that records a concrete case
  of the merged claim. Prefer the entry that preserves the most informative
  relationship among named or measured particulars. Use `NONE` if and only if
  the supplied evidence catalog is empty; when it is nonempty, select one of
  this merge item's namespaced IDs.

Do not copy or infer an Instance. Do not use filenames or Stage 3 specifics.
Do not rewrite, combine, or supplement evidence. The runner copies the chosen
Stage 2 title or body line exactly, apart from removing its Markdown list marker,
and writes `Instance: none recorded in source.` for `NONE`.

## Output discipline

The transport supplies a phase-specific schema and exact item IDs. For every
phase:

- return one row for every supplied item and no foreign row;
- preserve every item and unit ID verbatim;
- obey the exact key set for that phase;
- do not include reasoning, distinctions, notes, prose, or a code fence; and
- return only the JSON array requested by the runner.
