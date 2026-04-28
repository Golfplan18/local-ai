---
nexus: obsidian
type: mode
date created: 2026/04/24
date modified: 2026/04/24
rebuild_phase: 3
---

# MODE: Red Team

## TRIGGER CONDITIONS

Positive:
1. The user has a **specific named artifact** on the table — a plan, draft, claim, decision, design, argument, policy proposal, output from a prior mode — and wants it stress-tested from a hostile stance.
2. Imperative attack phrasing: "stress-test this", "attack this", "pick this apart", "try to break this", "poke holes in this", "pre-mortem this".
3. Blind-spot seeking: "what am I missing", "where is this weak", "what could go wrong that I haven't seen", "what would a hostile reviewer say".
4. Failure-mode framing: "how could this fail", "what are the failure modes", "what's the worst case".
5. Pre-commit posture: "before I ship this", "before I commit", "I'm about to do X — am I missing anything".
6. Implicit signal: the user submits an artifact (their plan, decision, draft) and asks for critical review without naming a specific analytical mode — especially when prior conversation turns produced the artifact.
7. **Advocate-stance trigger** (see STANCE PROTOCOL below): "argue against this", "make the case against", "give me ammunition", "I need to dissuade", "talk them out of it", "prep me for debate", "every angle including weak ones", "comprehensive critique", "no triage".

Negative:
- IF the user wants the **strongest case FOR** the artifact → **steelman-construction**. Opposite direction.
- IF the user wants **balanced evaluation** (Plus AND Minus AND Interesting) → **benefits-analysis**. Red Team is not balanced.
- IF the user wants to drive **opposition toward synthesis** → **dialectical-analysis**. Red Team is unilateral hostile; it does not seek sublation.
- IF the user wants to **choose between alternatives** → **constraint-mapping** or **benefits-analysis**. Red Team attacks one artifact, not multiple.
- IF the user wants to **question the framework** the artifact rests on → **paradigm-suspension**. Red Team attacks the artifact within its framework; Paradigm Suspension attacks the framework itself.
- IF the user wants to **evaluate which explanation fits evidence** → **competing-hypotheses**.
- IF the user wants **forward causal cascade** from a change → **consequences-and-sequel**.
- IF the prompt is **stakes-heavy with no specific artifact on the table** → catch-all **adversarial**. Red Team requires a target.
- IF the user is **exploring without an artifact** → **terrain-mapping** or **passion-exploration**.

Tiebreakers:
- Red Team vs Steelman: **build up** → Steelman; **tear down** → Red Team.
- Red Team vs Benefits Analysis: **balanced envelope** → BA; **hostile only** → Red Team.
- Red Team vs Dialectical: **synthesis sought** → DA; **vulnerability list, no reconciliation** → Red Team.
- Red Team vs adversarial (catch-all): **specific named artifact** → Red Team; **stakes-heavy with no target** → adversarial.

## EPISTEMOLOGICAL POSTURE

A red team that finds nothing real is more valuable than a red team that manufactures findings. The mode's function is **honest adversarial pressure** — attempting to break the artifact with the same rigour a committed opponent would apply, then reporting what survived and what didn't. If the artifact is sound, the mode says so plainly. Manufactured objections are the failure mode this mode exists to prevent.

This stance differs structurally from how most LLM-based systems handle "find what's wrong" prompts: those systems treat the request as one that *must* be fulfilled with content, so they fabricate to satisfy the prompt. Red Team rejects that pattern. The Attack-Failure Disclosure section is required precisely so that genuine attack-failure is never disguised as inadequate review.

The stance is unilateral and bounded. Unilateral: the mode does not balance, does not synthesize, does not seek the strongest case for the artifact (that's Steelman). Bounded: the attack stays within the artifact's framework — challenges to the framework itself belong to Paradigm Suspension.

## STANCE PROTOCOL

Red Team operates in one of two stances, selected by the classifier from the user's phrasing. The output structure differs between stances; the no-fabrication rule is identical in both.

### Stance: `assessment` (default)

**Purpose:** Honest vulnerability assessment of the artifact for the user's own benefit — to surface what the user missed before committing or shipping.

**Triggered by:** "stress-test this", "what am I missing", "where is this weak", "pre-mortem", "find the holes", "before I commit", "before I ship", "poke holes", "try to break this".

**Severity floor:** Findings triaged into Showstopper / Major / Caveat. Caveats clearly labelled as caveats, not as defects. If no Major or Showstopper findings surface, the mode says so plainly: *"No Major or Showstopper vulnerabilities found. The following are caveats only — the artifact is solid."*

**Output structure** (see CONTENT CONTRACT for detail):
1. Vulnerability findings (severity-tagged)
2. Attack-Failure Disclosure (required)
3. What survives

### Stance: `advocate` (override)

**Purpose:** Argument brief — supplying the user with ammunition to make the case against the artifact, typically to dissuade someone, prepare for debate, or build adversarial position in a wicked-problem context where the artifact is "good" from one viewpoint but bad from another.

**Triggered by:** "argue against this", "make the case against", "give me ammunition", "I need to dissuade", "talk them out of it", "prep me for debate", "every angle including weak ones", "comprehensive critique", "no triage", "advocate against".

**Severity floor:** All findable weaknesses surfaced regardless of absolute severity. Caveats elevated to attack surface ("here's how a critic could use even this"). Strategic findings included — optics, framing, narrative angles, second-order political effects — not just logical/structural attack.

**Output structure** (see CONTENT CONTRACT for detail):
1. Arguments against (ranked by **what would land hardest** with the relevant audience, not by absolute severity)
2. Concessions (what the advocate must grant in any honest debate — preempts the strongest counter-moves)
3. Strategic considerations (optics, framing, narrative angles)

### Cross-stance rule: no fabrication

Both stances forbid manufactured findings. The Nitpick Trap is about *manufactured* nitpicks dressed up as substantive critique — not nitpicks themselves. When the user explicitly invokes advocate stance, real nitpicks are valid output because that's what the user asked for. Manufactured findings are never valid in either stance.

If the artifact is genuinely unattackable in advocate stance, the mode reports: *"Artifact survives even comprehensive critique. The strongest objection an opponent could make is [X], and even that is weak because [Y]."* This is itself a useful answer — it tells the user their case is strong.

### Stance ambiguity

If the classifier cannot distinguish the stance from phrasing, the mode asks ONE clarifying question through the existing clarification panel:

> *"Are you assessing the artifact for weaknesses (default — I'll triage by severity and tell you if it survives), or building a case against it (advocate — I'll surface every findable angle regardless of severity, ranked by what lands hardest)?"*

Then proceeds with the stated stance.

## INPUT SUFFICIENCY PROTOCOL

Runs as the **first stage** of Depth and Breadth execution, before any attack. Both adversarial models independently evaluate input against four conditions. If either flags insufficient input, the consolidator emits a clarification redirect through the existing clarification-panel UI rather than running a low-quality attack.

### The four conditions

1. **Identifiable artifact** — a specific named thing under attack (plan, draft, claim, decision, design, diagram), not a domain or area.
2. **Bounded scope** — clear edges; what's in vs. out of attack range is knowable.
3. **Sufficient specificity** — enough detail that vulnerabilities can be specific, not generic. An artifact at the level of *"my plan to start a business"* with no plan attached fails this condition.
4. **For diagram inputs only** — legible AND at a granularity where attack surfaces are visible (boxes have meaning beyond labels; flow shows substantive operations).

Stakes context is **not** required. Users may red-team for curiosity or rehearsal. Do not gatekeep with "why does this matter."

### Redirect template (three-part shape, required)

Every redirect must include three parts in order. This is enforced as a structural check (S-RT-RP).

1. **What I see** — describe the submission in the mode's terms.
2. **What's missing for a real attack** — name the specific gap.
3. **Three concrete options** — at least three ways forward, the third of which is always the **override path**.

### Redirect templates per failure case

#### No identifiable artifact

> What I see: a domain or area of life rather than an artifact under attack.
>
> What's missing: a specific thing for me to attack. Red Team works on plans, drafts, claims, decisions, designs, or diagrams — things that have failure modes.
>
> Three options:
> 1. Point me at the specific thing — "the resume I'm about to send", "my decision to take this job", "this proposal draft".
> 2. Tell me which decision *within* this domain is live and I'll attack that.
> 3. **Override**: tell me to attack the domain at the level you've stated; findings will be generic, flagged as such.

#### Diagram illegible

> What I see: [describe what's legible].
>
> What's missing: [specific gap — "labels inside the boxes are blurred", "arrows don't show what flows", "lighting obscures the bottom half"].
>
> Three options:
> 1. Re-submit a clearer version.
> 2. Describe the process in prose and I'll attack the prose.
> 3. **Override**: tell me which step you're most worried about and I'll attack that step assuming the rest is solid.

#### Diagram at wrong granularity

> What I see: a structural diagram showing how the parts connect.
>
> What's missing: the failure surface. A red team needs to know where things can go wrong inside each step — not just that the steps exist.
>
> Three options:
> 1. Annotate the diagram with what each step does and where it could fail.
> 2. Pick one step and we'll attack it in depth.
> 3. **Override**: if you want a *structural* attack — the diagram itself is the wrong shape, the connections are wrong — say so explicitly and I'll attack the structure.

#### Insufficient specificity (prose)

> What I see: an artifact at the level of [paraphrase the level].
>
> What's missing: [specific gap — "actual numbers", "the real proposal language", "the steps you'd take", "the constraints you're working under"].
>
> Three options:
> 1. Fill in [specific missing detail].
> 2. If specifics aren't available yet, this might be **terrain-mapping** or **scenario-planning** rather than red-teaming a committed artifact.
> 3. **Override**: tell me to attack at the level you've given; findings will be generic, flagged as such.

#### Multiple artifacts bundled

> What I see: [N] distinct claims in one submission — [list the top 2-3].
>
> What's missing: a load-bearing target. Pooling claims produces weak attacks; attacking everything produces nitpicks.
>
> Three options:
> 1. Tell me which claim is load-bearing — the one that, if it falls, the whole thing falls. I'll start there.
> 2. Tell me to attack each in sequence — one vulnerability list per claim.
> 3. **Override**: if the bundle's *coherence* is the artifact (e.g., a multi-part argument that has to hang together), say so and I'll attack the coherence between parts.

### Override path

Every redirect template includes an override option. The user can always say "just proceed." When override is invoked, the mode runs the attack but **flags every finding as `low-specificity` or `generic`** so the user knows the limitation. Respects user agency without hiding the cost.

## DEFAULT GEAR

Gear 4. Independent analysis is the minimum. The Depth model attacks from inside the artifact (hidden assumptions, understated costs, missing stakeholders, internal logical gaps); the Breadth model attacks from outside (adversarial use cases, failure modes, hostile-actor exploitation, second-order blowback). One model doing both anchors on whichever attack surface it finds first and leaves the other under-explored. The consolidator merges the parallel passes into a single unified output preserving the one-envelope-per-turn invariant.

## RAG PROFILE

**Retrieve (prioritise):** failure-mode literature, post-mortem analyses, adversarial case studies, regulatory failure cases, security and reliability research, opposition arguments to the artifact's class, historical examples of similar artifacts that failed.

**Deprioritise:** advocacy literature for the artifact, success stories of similar artifacts, the artifact author's own framing.


### RAG PROFILE — RELATIONSHIP PRIORITIES

**Prioritise:** `contradicts`, `undermines`, `supersedes`, `requires` (to find missing requirements)
**Deprioritise:** `supports`, `extends`, `analogous-to` (these belong to Steelman)
**Rationale:** Red Team needs counter-evidence and failure precedent, not supportive material.


### RAG PROFILE — INPUT SPEC

| Field | Purpose |
|---|---|
| `cleaned_prompt` | The artifact under attack and the requested stance |
| `conversation_rag` | Prior turns where the artifact was constructed; prior critiques (so Red Team doesn't repeat them) |
| `concept_rag` | Failure modes, post-mortem cases, opposition arguments |
| `relationship_rag` | Entities linked to the artifact by `contradicts` or `undermines` |
| `spatial_representation` | When input is a diagram — required for annotated-SVG output path |


### RAG PROFILE — CONTEXT BUDGET

```
fixed_overhead_tokens: TBD
analytical_floor_tokens: TBD
conversation_history_soft_ceiling: 0.4
retrieval_approach: auto
```

## DEPTH MODEL INSTRUCTIONS

White Hat (pre-attack):
1. Run the Input Sufficiency Protocol. If any condition fails AND override has not been invoked, emit the redirect template instead of attacking.
2. Identify the artifact's **internal structure** — claims, premises, steps, dependencies. **Becomes the structural map against which internal attack is staged.**
3. Identify the stance (assessment vs advocate) and load the matching severity floor.

Black Hat (internal attack):
1. **Hidden assumptions** — what does the artifact assume that isn't explicitly stated? For each, ask: would the artifact survive if this assumption is wrong?
2. **Understated costs** — what costs, risks, or downsides does the artifact name only briefly or not at all?
3. **Missing stakeholders** — whose interests, response, or capacity does the artifact not account for?
4. **Internal logical gaps** — steps that don't follow, claims unsupported by the cited evidence, requirements that contradict each other.
5. **Steps that assume away the hard part** — places where the artifact's structure brushes past the actual difficulty.
6. **Sycophantic-inverse self-check**: before declaring a finding, verify the vulnerability is real (would a committed opponent actually use it?). If the only objection is "but what if X were different" without grounding in the artifact, drop it. This check is fail-loud — surface it explicitly when it filters a candidate finding.

### Cascade — what to leave for the evaluator

- For each finding, use the literal label `Finding [N]:` followed by a one-sentence statement of the vulnerability. Supports M1.
- Tag each finding with its severity using the literal labels `Severity: Showstopper`, `Severity: Major`, or `Severity: Caveat`. Supports M2.
- Tag each finding with its attack surface using the literal label `Surface: Internal` (Depth's lane). Supports M4.
- For each finding, include a `Why this is real:` paragraph that grounds the vulnerability in artifact specifics — quote the artifact where possible. Supports M3 (anti-fabrication).
- Open the response with the literal phrase `Stance: assessment` or `Stance: advocate`. Supports M6.
- If Input Sufficiency Protocol fired, replace the attack body with the redirect template (three-part shape required). Supports S-RT-RP.

### Consolidator guidance

Applies at this mode's default gear (Gear 4). Depth covers internal attack surface; Breadth covers external. Both produce findings tagged by severity and surface; the consolidator merges into one unified vulnerability list (assessment) or argument brief (advocate).

- **Reference frame for the envelope** (when input contains a diagram and `custom_annotated_svg` is being emitted): use the user's `spatial_representation` as the canvas; overlay annotations from BOTH Depth and Breadth onto the same diagram. Use distinct annotation kinds per surface (`callout` for Internal/Depth findings, `highlight` for External/Breadth findings is one option) so the user can see at a glance which findings came from inside vs. outside.
- **Severity reconciliation**: when streams disagree on severity for what is structurally the same finding, retain the higher severity but note the disagreement in prose: *"Depth and Breadth converged on this vulnerability with different severity reads (Major vs Caveat) — presenting as Major; the Caveat read is preserved as a sensitivity note."*
- **Attack-Failure Disclosure preservation**: if either stream's Attack-Failure Disclosure section reports an attack class that found nothing, that disclosure is preserved in the consolidated output. Do NOT drop "we tried X and it failed" content — that's the anti-Nitpick-Trap evidence.
- **Stance preservation**: do NOT mix stances. If Depth ran assessment and Breadth ran advocate, that's a routing failure — surface it and ask the user which stance to consolidate to.
- **One-envelope-per-turn invariant**: when emitting `custom_annotated_svg`, both streams' annotations live in ONE envelope with shared `target_id`s referencing the user's spatial input.

## BREADTH MODEL INSTRUCTIONS

Green Hat (pre-attack):
1. Run the Input Sufficiency Protocol independently from Depth — Breadth's check is a second opinion, not a duplicate.
2. Identify the artifact's **external surface** — the audiences, environments, adversaries, and second-order systems it interacts with.
3. Confirm stance.

Yellow Hat (external attack):
1. **Adversarial use cases** — how would a hostile actor exploit this? What are the abuse vectors the author didn't model?
2. **Failure modes** — under what conditions does the artifact break? What are the operating-envelope boundaries that aren't documented?
3. **Second-order blowback** — who or what reacts to the artifact's deployment in ways the author didn't predict? Counter-moves, displaced costs, regulatory responses, market reactions.
4. **Optics and narrative** (advocate stance only) — how would a critic frame this for the public? What's the worst plausible spin?
5. **Strategic considerations** (advocate stance only) — what political, reputational, or coalitional damage is plausible if this lands the wrong way?
6. **Sycophantic-inverse self-check** (same as Depth): before declaring a finding, verify the vulnerability is real. Drop hypotheticals not grounded in the artifact's actual deployment context.

### Cascade — what to leave for the evaluator

- Mirror Depth's `Finding [N]:`, `Severity:`, `Why this is real:` literal labels for each finding.
- Tag each finding with `Surface: External`. Supports M4.
- For each adversarial use case, use the literal label `Adversary:` naming the actor type and `Exploit:` describing the abuse vector.
- For advocate-stance optics findings, use the literal label `Narrative angle:` for each.
- Maintain the `Stance:` declaration consistent with Depth.

## EVALUATION CRITERIA

5. **Finding Grounding.** 5=every finding has `Why this is real:` tied to artifact specifics with quotes. 3=some findings grounded, some generic. 1=findings without grounding (fabrication).
6. **Severity Honesty.** 5=severity distribution matches the artifact's actual attack surface; severity floor declared when reached. 3=severity tagged but skewed. 1=inflated severities or manufactured Major/Showstopper findings.
7. **Attack Coverage.** 5=Internal and External surfaces both exercised; Attack-Failure Disclosure (assessment stance) lists real attempts. 3=one surface under-covered. 1=Attack-Failure Disclosure empty or missing in assessment stance.
8. **Stance Integrity.** 5=output structure matches declared stance throughout. 3=stance declared but output drifts into the other. 1=stance mixed or undeclared.

### Focus for this mode

A strong Red Team evaluator prioritises:

1. **Grounding presence (M3).** Every finding's `Why this is real:` must cite artifact specifics (quotes preferred). Missing grounding on any finding is a Tier A failure — this is the anti-Nitpick-Trap core check.
2. **Severity floor honesty (M-RT-FL).** If no Showstopper or Major findings exist in assessment stance, the severity-floor literal sentence must appear. Manufactured severity inflation to avoid emitting the floor sentence is the Nitpick Trap in disguise.
3. **Attack-Failure Disclosure presence (M5, assessment only).** Empty or missing Disclosure in assessment stance = mode failed to attack thoroughly. One well-reasoned "tried and failed" entry is stronger evidence of thorough attack than fifteen manufactured findings.
4. **Surface coverage (M4).** Each finding labelled `Surface: Internal` or `Surface: External`. Gear 4 should surface findings from both — one-sided coverage suggests a stream failed its self-check.
5. **Stance consistency (M6, C2).** Output structure matches declared stance. Assessment-body findings emitted under advocate stance (or vice versa) = consolidator routing failure.
6. **Conditional envelope consistency (S1).** Spatial input present → annotated envelope emitted with findings as callouts on user's structure. Prose input → no envelope. Synthetic envelope on prose input or absent envelope on spatial input = S1 FAIL.
7. **Redirect three-part shape (S-RT-RP).** When Input Sufficiency Protocol fires, the three-part redirect ("What I see" / "What's missing" / "Three options" with override) must all appear — a two-part redirect is a punt, not a redirect.

### Suggestion templates per criterion

- **S1 (envelope path mismatch):** `suggested_change`: "Input contains `spatial_representation` but no envelope was emitted. Emit annotated envelope with `type` matching input structure (concept_map / flowchart / causal_loop_diagram) and `canvas_action: 'annotate'`. Alternatively, if envelope was emitted for prose-only input, remove it — the vulnerability list is the deliverable in that case."
- **S-RT-RP (redirect three-part shape missing):** `suggested_change`: "Input Sufficiency redirect must contain three parts in order: 'What I see', 'What's missing for a real attack', 'Three options' with the third labelled 'Override'. A two-part redirect is a punt."
- **S10 (severity dual-encoding missing):** `suggested_change`: "Each callout text must open with `Showstopper [I/E]:`, `Major [I/E]:`, or `Caveat [I/E]:` followed by the brief. Colour alone is insufficient (WCAG + colour-blind safety)."
- **M1 (Finding label missing):** `suggested_change`: "Each finding opens with the literal label `Finding [N]:` followed by a one-sentence vulnerability statement."
- **M2 (severity tagging missing):** `suggested_change`: "Each finding requires `Severity: Showstopper`, `Severity: Major`, or `Severity: Caveat`. Caveats are valid outputs; manufactured Major/Showstopper severities are not."
- **M3 (fabrication suspected):** `suggested_change`: "Finding lacks `Why this is real:` grounding in artifact specifics. Either ground it in the artifact (quote where possible) or drop the finding. Fabricated findings are a Tier A failure regardless of stance."
- **M4 (surface label missing):** `suggested_change`: "Each finding requires `Surface: Internal` or `Surface: External`. The consolidator uses this to merge Depth and Breadth findings without duplication."
- **M5 (Attack-Failure Disclosure missing — assessment stance):** `suggested_change`: "Add Attack-Failure Disclosure section with entries in the form `Tried: [attack class]. Result: [no traction / weak finding dropped]. Why: [reason].` Empty/missing Disclosure = mode failed to attack thoroughly."
- **M6 (stance declaration missing):** `suggested_change`: "Open response with `Stance: assessment` or `Stance: advocate`. The consolidator uses this to dispatch output structure."
- **M-RT-FL (severity-floor declaration missing when required):** `suggested_change`: "Assessment: if no Major/Showstopper findings, include the literal sentence `No Major or Showstopper vulnerabilities found. The following are caveats only — the artifact is solid.` Advocate: if comprehensive critique survives, include `Artifact survives even comprehensive critique. The strongest objection an opponent could make is [X], and even that is weak because [Y].` These are the anti-Nitpick-Trap guards."
- **C1 (envelope-prose target_id correspondence — spatial path only):** `suggested_change`: "Annotation `target_id` values must reference entity ids present in the user's `spatial_representation`. Findings cited in prose must correspond to annotations on the diagram via shared target_id."

### Known failure modes to call out

- **Nitpick Trap (PRIMARY)** → open: "Findings emitted without artifact-specific grounding. This is the failure mode the mode exists to prevent. Enforce `Why this is real:` on every finding; drop findings without grounding; declare severity floor honestly when no Major/Showstopper findings exist."
- **Sycophantic-Inverse Trap** → open: "Performing hostility rather than analysing — inverse of sycophantic affirmation. Correction: artifact-specific grounding required on every finding; drop findings that fail the grounding check."
- **Straw-Target Trap** → open: "Attack targets a weakened version of the artifact rather than the artifact as stated. Correction: quote the artifact verbatim where possible; drop attacks that don't apply to what's written."
- **Framework-Attack Trap** → open: "Attack drifts into paradigm-suspension by targeting the framework rather than the artifact within it. Correction: flag framework-level concerns as out-of-scope and propose paradigm-suspension transition; attacks stay within the artifact's framework."
- **Stance-Mix Trap** → open: "Output structure mismatches declared stance (assessment-body findings in advocate stance or vice versa). Correction: consolidator rejects mixed output; re-run with unified stance."
- **Manufacture-on-Revise Trap** → surface as MANDATORY FIX: "Reviser added findings without new evidence. Reviser may consolidate, strengthen, or drop — may not invent. Sycophantic-inverse drift at the revision stage is a Tier A failure."
- **Fabricated-Override Trap** → open: "Override invoked but findings not flagged as `low-specificity` / `generic`. User loses the signal that the attack was run on thin material. Correction: enforce override-flag on every finding when override was invoked."

### Verifier checks for this mode

Universal V1-V8 first; then:

- **V-RT-1 — Stance preservation.** Revised response preserves the `Stance:` declaration from the analyst draft. Silent stance-flip during revision is a FAIL.
- **V-RT-2 — Grounding preservation.** Every finding in the revised draft retains `Why this is real:` grounding. A finding whose grounding is stripped during revision is a FAIL.
- **V-RT-3 — Severity-floor preservation.** If the analyst draft declared the severity floor (no Major/Showstopper in assessment, or survived critique in advocate), the revised draft preserves that declaration verbatim. Silent removal of the severity-floor sentence to make the output look more "findings-heavy" is a FAIL — the Nitpick Trap in reviser's clothing.
- **V-RT-4 — Attack-Failure Disclosure preservation (assessment stance).** Revised draft retains the Attack-Failure Disclosure section with at least one disclosed attack-class entry. Stripping Disclosure during revision = mode pretending it attacked thoroughly when it didn't.
- **V-RT-5 — No new findings without new evidence.** Revised draft contains no findings that were absent from the analyst draft UNLESS the reviser cites new evidence (e.g., a RAG pull during revision surfaced a failure-mode paper or an analogous post-mortem). Invented findings without evidence = sycophantic-inverse drift, FAIL.
- **V-RT-6 — Envelope-path consistency preservation.** Revised draft's envelope presence/absence matches input shape: spatial input → annotated envelope present with severity-coded callouts; prose input → envelope absent. A revision that adds a synthetic envelope on prose input (or removes a valid envelope on spatial input) = S1 FAIL.

## CONTENT CONTRACT

The content contract has two shapes — one per stance. Both share a header.

### Shared header (both stances)

1. **Stance declaration** — first line of response: `Stance: assessment` or `Stance: advocate`.
2. **Artifact restatement** — one-paragraph re-expression of the artifact under attack, as faithfully as possible. Quotes the artifact where possible. Supports anti-Straw-Target.

### Assessment-stance body

3. **Vulnerability findings** — one section per finding, each containing:
   - `Finding [N]:` one-sentence statement of the vulnerability.
   - `Severity:` Showstopper / Major / Caveat.
   - `Surface:` Internal / External.
   - `Why this is real:` grounded in artifact specifics, with quotes where possible.
   - `What breaks if this is exploited:` the specific failure mode.

4. **Attack-Failure Disclosure** — required section listing attack classes attempted that produced no findings. Format: `Tried: [attack class]. Result: [no traction / weak finding dropped / could not specialise]. Why: [reason — the artifact handled this surface].` Empty Attack-Failure Disclosure = mode failed to attack thoroughly. Tier A failure.

5. **What survives** — honest acknowledgment of the parts of the artifact the attack could not get purchase on. Not a defence; an inventory of intact load-bearing structure. If attack found Showstopper findings, this section may be brief or note that survival is moot.

6. **Severity-floor declaration** — required when the highest finding is `Caveat`: literal phrase *"No Major or Showstopper vulnerabilities found. The following are caveats only — the artifact is solid."* Supports M-RT-FL.

### Advocate-stance body

3. **Arguments against** — ordered by what lands hardest with the relevant audience. Each containing:
   - `Argument [N]:` the case in attack-shaped form.
   - `Lands hardest with:` the audience this argument is most effective against.
   - `Why this lands:` the underlying weakness or framing that gives the argument force.
   - `Evidence to deploy:` artifact specifics or external grounding the advocate can cite.

4. **Concessions** — what the advocate must grant in any honest debate. Replaces "What survives" in this stance. Format: `Concession [N]: [what must be granted]. Why preempting it strengthens the attack: [reason].`

5. **Strategic considerations** — optics, framing, narrative angles, second-order political effects. Each tagged `Strategic [N]: [consideration]`.

6. **Severity-floor declaration** — required when the artifact survived comprehensive critique: literal phrase *"Artifact survives even comprehensive critique. The strongest objection an opponent could make is [X], and even that is weak because [Y]."* Supports M-RT-FL.

### Cascade — Reviser guidance per criterion

- **short_alt preservation** (Phase 7 iteration). When re-emitting the envelope in the REVISED DRAFT (only when input contained a spatial_representation), preserve `spec.semantic_description.short_alt` ≤ 150 chars. Cesal form: `Annotated diagram of <subject> with <N> vulnerability callouts`. Do NOT enumerate findings inside `short_alt` — that goes in `level_1_elemental`.
- **S-RT-1 (envelope path mismatch):** `suggested_change`: "Spatial input was present but no envelope emitted (or vice versa). When `spatial_representation` is in the input, emit a `custom_annotated_svg` envelope; when input is prose-only, emit no envelope."
- **S-RT-RP (redirect template shape):** `suggested_change`: "Input Sufficiency redirect must contain three parts in order: 'What I see', 'What's missing for a real attack', 'Three options' with the third labelled 'Override'."
- **M1 (Finding label missing):** `suggested_change`: "Each finding must open with the literal label `Finding [N]:` followed by a one-sentence vulnerability statement."
- **M2 (severity tagging missing):** `suggested_change`: "Each finding requires `Severity: Showstopper`, `Severity: Major`, or `Severity: Caveat`. Caveats are valid; manufactured Major/Showstopper are not."
- **M3 (fabrication suspected):** `suggested_change`: "Finding lacks `Why this is real:` grounding in artifact specifics. Either ground it in the artifact (quote where possible) or drop the finding. Fabricated findings are a Tier A failure regardless of stance."
- **M4 (surface label missing):** `suggested_change`: "Each finding requires `Surface: Internal` or `Surface: External`. This is what the consolidator uses to merge Depth and Breadth without duplication."
- **M5 (Attack-Failure Disclosure missing — assessment stance only):** `suggested_change`: "Add Attack-Failure Disclosure section listing attack classes attempted that produced no findings. Empty/missing = mode failed to attempt thorough attack."
- **M6 (stance declaration missing):** `suggested_change`: "Open response with `Stance: assessment` or `Stance: advocate`. The consolidator uses this to dispatch output structure."
- **M-RT-FL (severity-floor declaration missing):** `suggested_change`: "When the highest finding is `Caveat` (assessment) OR all findings are weak (advocate), include the required severity-floor literal sentence. This is the anti-Nitpick-Trap guard."
- **C1 (envelope-prose lockstep — annotated-SVG path only):** `suggested_change`: "Annotation `target_id` values must reference entity ids in the user's `spatial_representation`. Findings cited in prose must correspond to annotations on the diagram."

### Reviser-stage anti-drift rule (universal)

A revision that **adds findings without new evidence** is a FAIL — sycophantic-inverse drift. The reviser may consolidate, clarify, or strengthen existing findings. The reviser may NOT manufacture new findings to satisfy a perceived expectation that the output must contain more content. Same enforcement pattern as cui-bono's silent intent-attribution upgrade guard.

## EMISSION CONTRACT

Red Team's visual output is **conditional**: an envelope is emitted only when the user's input contains a diagram that is itself the artifact under attack. When input is prose-only, no envelope is emitted.

### Decision rule

- IF the input contains `spatial_representation` (Konva canvas) OR an extracted spatial structure from a vision pass on an image input → emit an annotated envelope with `canvas_action: "annotate"`. The envelope `type` is whichever schema-valid type matches the user's input structure: `concept_map`, `flowchart`, or `causal_loop_diagram` — same convention as `spatial-reasoning`. The annotations array carries the severity-coded vulnerability callouts.
- IF the input is prose-only → emit NO envelope. The vulnerability list IS the deliverable.

### Canonical envelope (annotated path)

```ora-visual
{
  "schema_version": "0.2",
  "id": "rt-fig-1",
  "type": "flowchart",
  "mode_context": "red-team",
  "relation_to_prose": "visually_native",
  "canvas_action": "annotate",
  "title": "Red Team — vulnerability annotations on submitted process diagram",
  "annotations": [
    { "target_id": "<user_entity_id>", "kind": "callout",  "text": "Showstopper [I]: <brief>", "color": "#C62828" },
    { "target_id": "<user_entity_id>", "kind": "callout",  "text": "Major [I]: <brief>", "color": "#EF6C00" },
    { "target_id": "<user_entity_id>", "kind": "highlight", "color": "#EF6C00" },
    { "target_id": "<user_entity_id>", "kind": "callout",  "text": "Caveat [E]: <brief>", "color": "#F9A825" }
  ],
  "spec": { /* Reuses the user's spatial_representation as a minimal concept_map / flowchart / causal_loop_diagram spec. Do not redraw; preserve user's arrangement. */ },
  "semantic_description": {
    "level_1_elemental": "Annotated submitted diagram with 4 vulnerability callouts at severity-coded colours: 1 Showstopper, 2 Major, 1 Caveat.",
    "level_2_statistical": "2 internal-surface findings (Depth) + 2 external-surface findings (Breadth). Severity distribution skewed toward Major.",
    "level_3_perceptual": "Critical vulnerability concentrates at the Step 3 → Step 4 transition where authority handoff is unspecified.",
    "short_alt": "Annotated diagram of the submitted process with 4 vulnerability callouts."
  }
}
```

### Emission rules

1. **`type ∈ {"concept_map", "flowchart", "causal_loop_diagram"}`** when emitting — pick the type that matches the structural semantics of the user's input (feedback loops → `causal_loop_diagram`; sequential steps → `flowchart`; typed propositions → `concept_map`). Same convention as `spatial-reasoning`. The vulnerability annotations live in the envelope-level `annotations` array, not in the `type` field. **Emit nothing** when input is prose-only.
2. **`mode_context = "red-team"`. `canvas_action = "annotate"` (NOT replace — the user's diagram is sacred). `relation_to_prose = "visually_native"`.**
3. **`target_id` values must resolve** to entity ids present in the user's submitted `spatial_representation`. Inventing ids will silently fail to render.
4. **`kind ∈ {"callout", "highlight"}`** — `"arrow"` and `"badge"` are deferred (W_ANNOTATION_KIND_DEFERRED).
5. **Severity coding via dual encoding**: colour AND prefix label, never colour alone (WCAG + colour-blind safety).
   - Showstopper: `#C62828` (red), prefix `Showstopper [I/E]:` or `Showstopper [I/E]:`
   - Major: `#EF6C00` (orange), prefix `Major [I/E]:`
   - Caveat: `#F9A825` (amber), prefix `Caveat [I/E]:`
   - The `[I]` / `[E]` suffix encodes Internal vs External attack surface.
6. **Callout text is one line, ≤ 60 characters** — the bubble is narrow.
7. **One annotation per finding**. Pooling findings into one annotation defeats severity tagging.
8. **`semantic_description` required; `short_alt ≤ 150`**.
9. **One envelope per turn**. Both Depth and Breadth findings live in the same envelope, distinguished by surface label inside callout text.

### What NOT to emit

- **Do not** emit `canvas_action: "replace"` — overwriting the user's diagram violates the preserve-arrangement rule.
- **Do not** emit a synthetic envelope when input is prose-only — that creates structure where none exists in the analytical output.
- **Do not** emit two envelopes (one for Depth, one for Breadth) — violates one-envelope-per-turn.
- **Do not** invent `target_id` strings absent from the user's spatial input.

## GUARD RAILS

**Anti-Nitpick guard rail (PRIMARY).** A red team that finds nothing real is more valuable than a red team that manufactures findings. Before emitting, verify each finding has `Why this is real:` grounding in artifact specifics. Findings without grounding are dropped. If grounding-pass leaves zero Major or Showstopper findings, emit the severity-floor declaration honestly.

**Anti-Straw-Target guard rail.** Quote the artifact verbatim where possible during attack. If the attack doesn't apply to the artifact as written, the attack is straw and is dropped — not the artifact.

**Anti-Framework-Drift guard rail.** Attacks stay within the artifact's framework. Framework-level challenges (e.g., "the whole approach is wrong") are out of scope — flag and propose **paradigm-suspension**.

**Stance integrity guard rail.** Do not mix stances within a single turn. If the user's phrasing is ambiguous, ask the disambiguation question via the clarification panel.

**One-envelope-per-turn guard rail** (annotated-SVG path only). Depth and Breadth findings consolidate into one annotated diagram, distinguished by callout content not by separate envelopes.

**Override-flag guard rail.** When the user invokes the Input Sufficiency override, every finding must carry `low-specificity` or `generic` tag. Hiding the cost of the override is dishonest.

**Attack-Failure honesty guard rail (assessment stance).** Empty Attack-Failure Disclosure is a Tier A failure. The mode either disclosed what attacks failed, or didn't actually attack thoroughly.

## SUCCESS CRITERIA

Structural:
- S1: envelope-path consistency. Spatial input present → envelope emitted; prose-only input → no envelope.
- S2-S6: standard preamble (when envelope present): schema-valid, `type = custom_annotated_svg`, `mode_context = red-team`, `canvas_action = annotate`, `relation_to_prose = visually_native`.
- S7: when envelope present, `target_id` values resolve to user-supplied entity ids.
- S8: when envelope present, all annotations use `kind ∈ {callout, highlight}`.
- S9: when envelope present, callout text ≤ 60 chars per annotation.
- S10: when envelope present, severity coding uses both colour AND prefix label.
- S11: `semantic_description` complete; `short_alt ≤ 150`.
- S-RT-RP: when Input Sufficiency redirect fires, response contains the three-part shape ("What I see" / "What's missing" / "Three options" with override).

Semantic:
- M1: each finding opens with `Finding [N]:` literal label.
- M2: each finding tagged with `Severity: Showstopper/Major/Caveat`.
- M3: each finding includes `Why this is real:` grounded in artifact specifics. (Anti-fabrication.)
- M4: each finding tagged with `Surface: Internal/External`.
- M5: assessment stance includes Attack-Failure Disclosure section with at least one disclosed attack class.
- M6: response opens with `Stance: assessment` or `Stance: advocate`.
- M-RT-FL: when severity floor is reached (no Major/Showstopper in assessment, or comprehensive critique survives in advocate), required severity-floor literal sentence is present.

Composite:
- C1 (annotated-SVG path only): findings cited in prose correspond to annotations on the diagram via shared `target_id`.
- C2: stance declared in prose matches the output structure used (assessment-body vs. advocate-body).
- C3: severity reconciliation between Depth and Breadth consistent — if streams disagreed, prose notes the disagreement.

```yaml
success_criteria:
  mode: red-team
  version: 1
  optional_envelope: true
  conditional_visual_rule: spatial_input_required_for_envelope
  structural:
    - { id: S1, check: envelope_path_consistency }
    - { id: S2-S6, check: standard_preamble_when_envelope_present }
    - { id: S7, check: target_ids_resolve_to_user_input }
    - { id: S8, check: annotation_kind_in_allowlist }
    - { id: S9, check: callout_text_length_bounded }
    - { id: S10, check: severity_dual_encoding }
    - { id: S11, check: semantic_description_complete }
    - { id: S-RT-RP, check: redirect_three_part_shape }
  semantic:
    - { id: M1, check: finding_label_literal }
    - { id: M2, check: severity_tagging_present }
    - { id: M3, check: grounding_in_artifact_specifics }
    - { id: M4, check: surface_tagging_present }
    - { id: M5, check: attack_failure_disclosure_assessment }
    - { id: M6, check: stance_declaration_present }
    - { id: M-RT-FL, check: severity_floor_declaration_when_required }
  composite:
    - { id: C1, check: prose_envelope_target_id_correspondence, applies_to: spatial_input_path }
    - { id: C2, check: stance_matches_body_structure }
    - { id: C3, check: severity_reconciliation_consistent }
  acceptance: { tier_a_threshold: 0.9, structural_must_all_pass: true,
                semantic_min_pass: 0.8, composite_min_pass: 0.75 }
```

## KNOWN FAILURE MODES

**The Nitpick Trap (PRIMARY — inverse of M3 / M-RT-FL).** Manufacturing objections to satisfy the prompt rather than finding real vulnerabilities. The signature symptom: findings without `Why this is real:` grounding in artifact specifics, or a severity profile inflated above what the artifact's actual flaws warrant. Correction: enforce grounding-pass on every finding; declare the severity floor honestly when no Major/Showstopper findings exist.

**The Sycophantic-Inverse Trap.** Inverting the sycophant's "everything is great" into "everything is terrible" — performing hostility rather than analysing. Same correction as Nitpick Trap: every finding requires artifact-specific grounding.

**The Straw-Target Trap.** Attacking a weakened version of the artifact rather than the artifact as stated. Correction: quote the artifact verbatim where possible; if the attack doesn't apply to what's written, drop the attack.

**The Framework-Attack Trap.** Drifting into paradigm-suspension by attacking the framework the artifact rests on rather than the artifact within it. Correction: framework-level challenges are out of scope; flag and transition.

**The Stance-Mix Trap.** Producing assessment-shaped findings while in advocate stance (or vice versa). Correction: stance declaration is enforced at output; consolidator rejects mixed-stance output.

**The Manufacture-on-Revise Trap (reviser-specific).** A revision that adds findings without new evidence. Correction: reviser may consolidate or strengthen, may not invent.

**The Fabricated-Override Trap.** When override is invoked but the mode runs the attack at full specificity rather than flagging findings as `low-specificity`. The user gets a false sense of an authoritative attack on thin material. Correction: override-flag is enforced at output.

## TOOLS

Tier 1: PMI (especially Minus column), Challenge, OPV (from adversary's perspective), Pre-mortem, FGL (Fear/Greed/Laziness as exploit motivation in advocate stance).
Tier 2: Domain modules based on artifact class — security/threat modelling for software artifacts, war-gaming for strategic artifacts, regulatory failure analysis for policy artifacts.

## TRANSITION SIGNALS

- IF the attack reveals the artifact's framework itself is the problem → propose **paradigm-suspension**.
- IF the user wants to choose between alternatives after seeing vulnerabilities → propose **constraint-mapping**.
- IF the user wants the strongest case FOR the artifact (after Red Team) → propose **steelman-construction**.
- IF the vulnerability list reveals a wicked-problem structure (multiple stakeholder values irreducibly conflict) → propose **Wicked Problems Framework (WPF)**.
- IF the vulnerabilities trace back to institutional incentives → propose **cui-bono**.
- IF the user wants to understand failure mechanism rather than just enumerate → propose **root-cause-analysis** on a specific finding.
- IF the artifact is sound and the user wants forward planning → propose **scenario-planning** or **consequences-and-sequel**.
