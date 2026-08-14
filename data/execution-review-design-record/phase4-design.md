# Execution Review — Phase 4 Design Packet (Evaluation-lane router + polymorphic output + packet-to-review renderer)

*Status: DESIGN GATE. No code written. Mirrors how Phases 2 and 3 opened —
seam scout of the landed substrate → design mapped to the spec → adversarial
completeness-critic pass (folded, ⚖ below) → deliver to the judge.
Implementation waits for the judge's design approval, then lands in a fresh
worktree off current `origin/main`.*

Spec: `/Users/oracle/ora-worktrees/ora-execution-review-spec.md` — Phase 4 is
§15 ("Evaluation-lane router + polymorphic output + packet renderer") resting on
§5 (route by evaluation unit; `evidence_lanes` vs `judgment_lanes` structurally
separate), §9 (the ExecutionPacket schema — tier-optional blocks,
frontmatter-is-a-flat-index, large artifacts referenced not inlined), §12
(governance: the packet-to-review renderer that presents mechanical evidence
first and the producer claim last labeled unverified; findings tagged
plan/execution; reviewer-invented tests tagged; model-family diversity), §6 (the
two clocks + the `output_type`-vs-observed consistency check), and the §1/§2
self-evidencing reframe. Substrate scouted **read-only** in the pinned worktree
`/Users/oracle/ora-worktrees/phase4-scout` @ `0dda6ac6` (current `origin/main`,
the Phase-3 landing).

---

## 0. The one-paragraph statement of Phase 4

Phases 1–3 built the *observation* substrate: every terminal turn now folds an
after-clock `route_observed` event carrying **both** §6 signals — signal 1
(`any_mutation` / `max_mutability`, "what it changed") and signal 2
(`source_read_suspected` + `source_read_channels` + `source_candidate_reads`,
"what it read as a source"). Phase 4 is the first phase that makes the *output
polymorphic*: it introduces an `ExecutionPacket` type alongside the plain-text
artifact the pipeline returns today, a **packet-to-review renderer** (§12) that
converts a packet into review text with mechanical evidence first and the
producer's claim last (labeled an *unverified claim*), and an **evaluation-lane
router** (§5) that maps the two folded signals onto `evidence_lanes` (mechanical,
each owed a real verdict) kept **structurally separate** from `judgment_lanes`
(interpretive, `verdict: null` by construction). It also **installs** the §6
`output_type`-vs-observed consistency assertion that Phase 3 recorded the inputs
for but deferred. The load-bearing constraint the whole design serves: this is
**"same downstream machinery, richer output," not a second pipeline** — the
renderer targets the *existing* evaluator/verifier prompt-assembly path, the
packet is constructed at the *existing* terminal fold point, and text behaviour
stays byte-identical by default. Phase 4 does **not** generate real evidence
(that is Phase 5's `.ora/evidence.yaml` runner), does not build the
claim-to-source map (Phase 8), and does not wire the full dual-verify-on-evidence
loop (Phase 6).

**An honesty note the adversarial pass forced to the front (see ⚖).** Three of
these four deliverables are, in P4, *built and test-covered but not exercised by a
live turn* — and the packet says so plainly rather than describing dormant
capabilities in the present tense. Because the packet is born at the terminal —
*after* every in-gear review has already run on the raw draft string — the
**renderer** governs no live P4 review (its evidence-first protection is proven by
a test that feeds a rendered packet into the real evaluator/verifier prompt shape,
not by any live verifier consuming a packet); the **consistency assertion** fires
on zero live turns (no mode declares `output_type` in P4, so its operand is always
`unknown`); and the **lane router**'s evidence/judgment separation is real *in the
packet type* but does not change the one live verdict path (`_verifier_passed`
still grades the whole draft). What runs live in P4 is the **construction of a real
packet at the two gear terminals** (type + router + consistency note recorded on
real turns); what is tested-but-unwired is the *review* of that packet. That is the
correct Phase-4 line — build the type, the renderer, the router, and the assertion
as the seam the later phases pour real content through — stated without overclaim.

---

## 1. Substrate scout — evidence (file:line, all @ `0dda6ac6`)

### 1.1 Where "output" is typed today — the §15 "locate where output is typed" task
`run_gear3` (`orchestrator/boot.py:11031`) returns a **plain `str`**
(`deliverable`, `boot.py:11602-11609` — the extracted `## REVISED DRAFT` or a
fallback to the full `revised_analysis`). `run_gear4` (`boot.py:11663`) returns a
**plain `str`** (`formatted`, `boot.py:13003`). Gear 4 falls back to
`run_gear3(...)` when a stream degrades (`boot.py:11739`, `:11867`). The callers
receive an untyped string:
- `boot.py:9376` `response = run_gear3(...)`; `boot.py:9385` `response = run_gear4(...)`.
- `server/server.py:2911` (gear3) / `:2919` (gear4), same shape.

That string flows untyped to the terminal, where two things happen in order:
1. `record_route_observed(..., output_text=response)` — `boot.py:9416-9420`
   (server twins at `server.py:2841`, `:2957`, `:3270`, `:3278`, `:3720`,
   `:3739`, `:3796`; framework path `framework_elicitation.py:328`). This folds
   the tool-event log into the two signals (§1.4).
2. `route_output(response, output_target, context_pkg)` — `boot.py:9424`; the
   deliverable is emitted to screen/file.

**The output typing point is therefore the gear return + the terminal
`response`/`deliverable`/`formatted` variable** — a bare `str` today. There is no
`TextArtifact` / `ExecutionPacket` / `evidence_lane` / `judgment_lane` symbol
anywhere in `orchestrator/` or `server/` (grep-verified: zero hits). "Type the
output" means: give that terminal string a companion polymorphic form.

### 1.2 The in-gear render seam — where the *reviewer* consumes the artifact (§12 attach point)
The evaluator / reviser / verifier / consolidator / formatter each receive the
**system** prompt from the shared `build_system_prompt_for_gear(context_package,
slot, step)` (`boot.py:8467`; per-step dispatch at `:8587` analyst, `:8663`
evaluator [`pass`], `:8668` reviser, `:8673` verifier [`pass`], `:8678`
consolidator, `:8688` formatter). The **artifact under review** is *not* in the
system prompt — it is interpolated into the **user** message by hand-built
f-strings at (up to) six sites (all in `boot.py`):

| stage | gear-3 site | gear-4 site(s) | header the artifact rides under |
|---|---|---|---|
| evaluator | `11212-11221` | `11906-11937` | `## ANALYST OUTPUT` / `## ANALYST OUTPUT (Depth/Breadth stream)` |
| reviser | `11286-11307` | `12030-12073` | `## YOUR ORIGINAL ANALYSIS` + `## EVALUATOR'S CRITIQUE` |
| verifier | `11379-11415` | `12214-12285` | `## REVISED ANALYSIS (reviser output)` / `## REVISED {DEPTH,BREADTH} ANALYSIS` |
| consolidator | — | `12530-12566` | two revised streams fenced with `---` |
| formatter | — | `12654-12676` | `## CONSOLIDATED CORPUS` |
| quality gate | `11520` | `12806-12808` | `## CANDIDATE ANALYSIS` / `## CANDIDATE DELIVERABLE` |

There is **no single choke point** today — the draft string is dropped into each
user message directly. This is exactly where the §12 renderer attaches: the point
where the artifact string becomes review input is the point where
`TextArtifact`-vs-`ExecutionPacket` polymorphism decides *what the reviewer
sees*. The shared banner-fence helper `_fenced(label, body, note)`
(`boot.py:8420-8429`, `=== LABEL === / === END LABEL ===`) is the existing
convention the renderer should reuse (banner fences are syntactically distinct
from `#` headings, so they never collide with retrieved-content headings).

### 1.3 The single-verdict verify path — §5 mapping surface
The one canonical verdict parser is `_verifier_passed(verifier_output) -> bool`
(`boot.py:9939-9966`), which calls `_extract_structured_verdict` (line-anchored
`VERDICT: PASS` / `FAIL` / `BROKEN`, with a legacy `VERIFIED` fallback).
- Gear 3: **one** verdict per revision cycle (`passed = _verifier_passed(verified)`,
  `boot.py:~11428`); PASS or structurally-sound BROKEN unblocks, real-FAIL
  re-revises.
- Gear 4: **two** verdicts per cycle — `depth_verdict` / `breadth_verdict`
  (`boot.py:~12323-12324`) — but these are the two **adversarial streams**
  (depth vs breadth), *not* two evaluation-lane kinds. Both are mechanical
  PASS/FAIL. A separate final quality gate reuses the same parser
  (`gate_passed = _verifier_passed(gate_out)`, `boot.py:~12831`).

**Consequence for §5:** today every verify verdict is a *mechanical pass/fail* on
the whole draft. There is no structural place where an interpretive target
("is this satire landing") is prevented from receiving a mechanical verdict — the
protection §5 demands (`judgment_lanes` with `verdict: null` by construction) does
not exist yet. The depth/breadth split is an adversarial-diversity axis, orthogonal
to the evidence-vs-judgment axis Phase 4 introduces; the design must not conflate
them.

### 1.4 The two after-clock signals — where they live now
`fold_route_observed(events_path, *, conversation_id, turn_ts, output_text)`
(`orchestrator/risk_gate.py:548-647`) returns the `signals` dict
(`risk_gate.py:565-570`):
`any_mutation`, `max_mutability`, `reads_present`, `max_sensitivity`,
`max_egress`, `gate_outcomes`, `events_scanned`, **`source_read_suspected`**,
**`source_read_channels`**, **`source_candidate_reads`**,
`source_candidate_reads_truncated`. Signal 2 is computed at `:635-640` (strong
channel + any non-empty output ⇒ suspected; ambiguous-local + substantive output
⇒ suspected). The source-read allowlist + actually-ran filter is
`_source_read_kind` (`:131`); the public-safe descriptor projection is
`_public_safe_candidates` (`:162`); the substantive-output floor is
`_output_is_substantive` (`:186`).

`record_route_observed(turn_key, risk_tier, *, output_text)`
(`risk_gate.py:983-1036`) folds, computes the one Phase-2 `divergence` note
(`:1001-1007`), and records the `route_observed` event with
`source_read_suspected` **promoted top-level** (`:1031`) plus the full
`route_signals` block (`:1025-1033`). **Both §6 signals now read cleanly off one
dict:** `any_mutation` (signal 1) and `source_read_suspected` (signal 2).

**Load-bearing scout finding:** `record_route_observed` **returns**
`{"signals": ..., "divergence": ...}` (`:1034`) — and that return is
**discarded at all 11 call sites** (grep-verified). The signals are recorded to
the tool-event log but no runtime code consumes the return. So a Phase-4 lane
router can consume the signals **at the terminal, from the already-available
return value**, without re-folding — the fold has already run.

### 1.5 The consistency-assertion seam — §6 `output_type`-vs-observed
`output_type` does **not exist as a first-class field** anywhere in
`orchestrator/` or `server/` — the only occurrence is the comment at
`risk_gate.py:1002` ("no output_type until Phase 4"). The Phase-2 `divergence`
check (`risk_gate.py:1001-1007`) only compares *tier vs mutability* (a
light/standard turn that mutated beyond its tier). The §6 declared-vs-observed
misroute check — a "text" task that changed files or grounded claims, or an
"execution" task that produced neither — has **both its inputs present now**
(`any_mutation` + `source_read_suspected`) but **no `output_type` to compare
against**. This is the field Phase 4 introduces (§9 frontmatter `output_type`) and
the assertion Phase 4 turns on (record-only; §2/P4 below). `task_fingerprint`
already threads an `output_target` (`risk_gate.py:395`, `:408`, `:834`) — but that
is the emission destination (screen/file/both), **not** the §9 `output_type`
hint; they must not be conflated.

### 1.6 Custom prompt-assembly paths — the §15 Phase-0 audit, re-run @ `0dda6ac6`
The shared assembly a Phase-4 change reaches "for free" is
`build_system_prompt_for_gear` (system prompt) + the six in-gear user-prompt
interpolation sites (§1.2), both in `~/ora/orchestrator/boot.py`. The paths that
build their **own** Gear-3/4 prompts and will **not** inherit the polymorphic
change (confirmed against the live MSI plugin `~/sites/mainstreetindependent/
ora-project/`, and consistent with memory [[project-msi-custom-gear-paths]]):

| # | path | file | inherits shared assembly? | note |
|---|---|---|---|---|
| 1 | `write_column` (author→review→revise) | `tools/gear3_orchestrator.py` | ❌ hardcoded review + revise prompts | own evaluator/reviser contract |
| 2 | backfill author + polish | `tools/backfill_orchestrator.py` | ❌ `STRICT_HAIKU_PROMPT_PREFIX` + `POLISH_SYSTEM_PROMPT` | direct OpenRouter call, not `run_gear{3,4}` |
| 3 | `construct_system_prompt` | `scripts/article_generator.py` | ❌ hand-assembled from vault files | single-pass author, no verify |
| 4 | post-gear merge/format (`integrate_best`, `format_fix`, `select_best`, …) | `tools/msi_run_gear4.py` | ❌ custom merge/repair prompts | runs *after* `run_gear4` |
| 5 | `invoke_real_gear4` | `tools/msi_run_gear4.py` | ⚠️ **partial** — delegates steps 3–8 to `boot.run_gear4` | analysts/verifiers DO see the shared assembly (via a synthesized mode); only the post-gear edits are custom |

All four files carry a **separate copy** of the fence convention
(`tools/prompt_fences.py`, which its own docstring says "Mirrors Ora core's
`build_system_prompt_for_gear` `_fenced`") — so even the fencing does not
auto-sync. The §15 warning applies in full: a beautiful core polymorphism that
the real MSI workload bypasses. **How Phase 4 handles this is a scope decision,
not a silent omission — see P6.**

### 1.7 Existing tests / the parity surface
`orchestrator/tests/test_risk_gate.py` — `TestRouteObserved` (Phase 2, 5 tests) +
`TestSourceReadSignal` (Phase 3, 28 tests) assert the `signals` shape and the
source-read fold. `test_risk_gate_pipeline.py` mocks `record_route_observed`
wholesale. `test_tool_events.py` has the truncation-survival test for the routing
verdict. **Additive discipline (proven in Phase 3):** no runtime consumer reads
the `signals` dict outside `risk_gate` + tests, so new keys are safe; but a
*return-shape* change to `record_route_observed` or a *type* change to the gear
returns would ripple to those tests and every caller — argues for the
terminal-only, additive construction in P1/P5. Environmental parity baseline
(inherited): **22 failures + 5 errors** (lens-integrity, retry-fallback,
openai-images, mode-relationship-priorities, user-settings, visual-routing — all
pre-existing, none related to this project); full suite ~3663 tests at the
Phase-3 landing.

---

## 2. The design

The pipeline order is the fact that shapes everything: **the gear runs its verify
stages *during* production (steps 4–8) and returns a `str`; the two route signals
are folded only *at the terminal*, after the gear returns** (§1.1, §1.4). So the
existing in-gear verify has already run by the time the signals exist. Three
candidate architectures follow from that; the design recommends the first and
names the other two so the judge sees what was rejected and why.

- **Architecture A (recommended) — terminal packet + library renderer, seam install
  deferred.** Build the `ExecutionPacket` type, the renderer, and the lane router as
  one library; **construct the packet live at the two gear terminals** from the
  already-folded signals (§1.4), guarded to real deliverables; install the
  consistency assertion as a **record**. The renderer's "the existing review logic
  accepts it" is proven by a test that feeds a rendered packet into the real
  evaluator/verifier user-prompt shape — **the six in-gear interpolation sites are
  NOT edited in P4** (that install is Phase-6 scaffolding; editing six live review
  sites to add a branch no P4 turn exercises is parity risk for zero P4 benefit —
  the adversarial pass was decisive on this, ⚖ arch-L1-4). No new live model-review
  call. This is the faithful reading of "same downstream machinery, richer output —
  not a second pipeline," and it keeps parity clean the way Phases 1–3 did (additive,
  opt-in, text default byte-identical).
- **Architecture B (rejected) — mid-run fold + live in-gear packet review.** Fold
  the signals at the verify step so the in-gear verifier reviews the rendered
  packet live. Rejected: it invents a *third* observation clock the spec does not
  have (before-risk / after-route are the only two, §6), it changes live verify
  behaviour on every gear-3/4 turn (parity risk), and the evidence available
  mid-run is only what the analyst/reviser did so far — it collapses Phases 4, 5,
  and 6 into one.
- **Architecture C (rejected) — packet as a pure persistence record.** Construct
  the packet only for the durable record and never touch review. Rejected:
  under-delivers Phase 4 — it skips the §12 renderer "accepted by the review
  logic" and the §5 lane router, which are the phase's named deliverables.

Everything below is Architecture A.

### P1 — The `ExecutionPacket` data shape (tier-optional, §9), constructed at the terminal
A single new consolidated module `orchestrator/execution_packet.py` (one file per
the vault consolidated-files rule — the packet dataclass, the two lane types, the
renderer, and the lane router are one cohesive unit; a split would need
justification it does not have). It holds:

- `@dataclass ExecutionPacket` with **tier-optional** fields mirroring §9. Empty
  structures are **not fabricated** (§9): `planning` is absent at `light`,
  single-pass at `standard`, dual at `high-risk`+; `verification` is one reviewer
  at low tiers, dual (different family) higher. A `light` packet with no
  `planning` and one reviewer is *correct*, not incomplete.
- **Frontmatter is a flat index** (§9): a `frontmatter() -> dict` method returns
  only small flat scalars — `task_id`, `created`, `modified`, `status`,
  `output_type`, `risk_tier`, `reversible`, `tags`. **No large nested blob** goes
  in the header.
- **Large artifacts are referenced, never inlined** (§9): the `execution.delta`,
  `execution.tool_events`, and any diff/log/transcript are stored as a **path or
  ref string** (e.g. the trace-dir path already in scope at the terminal), never
  the blob. The packet stays greppable and diff-friendly.
- **Every §9 block is reserved in the type, even when P4 does not populate it**
  (the "carry the shape, defer the wiring" discipline — folding ⚖ spec-L1-1/-2/-4).
  A block Phase 4 cannot fill is present as a tier-optional/placeholder field, so a
  later phase *fills* it rather than *retrofits the type* (a schema change with
  blast radius — the exact anti-pattern the design avoids for evidence_lanes). The
  full block list, and what P4 puts in each:
  - `task` — instruction / constraints / non_goals (from `context_pkg`). **Live.**
  - `planning` — reserved, **absent** at light / unpopulated in P4 (no planning
    stage is built until Phase 6; §8).
  - `execution` — `enforcement_model` (see below), `mode` / `state_before` /
    `state_after` **reserved but unfilled** (the §11 dirty-state protocol + state
    snapshots are Phase-5 adapter concerns — ⚖ spec-L1-4); `delta` (a *reference* +
    the folded `any_mutation`/`max_mutability` summary); `source_reads` (the folded
    `source_candidate_reads` — the public-safe descriptors Phase 3 already
    redaction-proofed); `producer_claim` = the deliverable string the gear
    returned; `known_limitations` empty in P4.
  - `evidence_lanes` / `judgment_lanes` — from the router (P3); in P4 the evidence
    lanes are **declared but unfilled** (no runner yet — Phase 5).
  - `verification` — the scoped in-gear text verdict (see below), with
    `reviewer_a` / `reviewer_b` (family identity) and `confidence` **reserved but
    unfilled**, and `findings[].class` / `invented_tests[].kind` reserved. The
    §12 single-family-degrade governance rule (lower `confidence`, record which
    family reviewed, escalate on high-risk) is the load-bearing thing this block
    must be *able to express*; P4 reserves the fields and defers the computation
    to the Phase-6 loop (⚖ spec-L1-2/-8).
  - `loop` — `iteration` / `stop_condition` / `escalation{reason,
    abandoned_attempt_branch}` **reserved but unpopulated** (the loop is Phase 6;
    without the field a P4 reader cannot tell "converged in zero iterations" from
    "the field does not exist yet" — ⚖ spec-L1-1).
  - `persistence.tier` / `redacted` — placeholders; the actual tiered persistence
    is Phase 7.
- **`enforcement_model` is not hardcoded** (⚖ spec-L1-3, guarding the §17
  "enforcement can be overclaimed" trap). For a core gear run built at the core
  terminal the honest value is `in_harness` — but the field carries a **stated
  contract tied to §7's two-enforcement-model honesty**: it records what the
  substrate can actually attest for *this* turn, and any orchestrated / opaque-shell
  / MSI-custom path that later produces a packet **must set it correctly** (a TODO
  the P6 enumeration owns), never inherit a blanket `in_harness`.
- **The `verification` block is sourced honestly, and its provenance was the
  sharpest ⚖ finding (arch-L1-1).** The in-gear verdict (`_verifier_passed` →
  `passed` / `depth_passed` / `breadth_passed` / `gate_passed`) is **function-local
  to `run_gear{3,4}` and is NOT reachable at the terminal** — the gears return only
  the `str` deliverable (verified: no verdict-bearing `context_pkg` assignment
  exists today). So P4 **threads the verdict + verifier text out via `context_pkg`**
  (already mutated in place inside the gears and in scope at the terminal — the same
  mechanism Phase 2 used for `risk_tier` / `_route_turn_ts`), a side channel that
  needs **no gear return-type change** (preserving OQ3). And per ⚖ arch-L1-5 the
  block is **scope-labeled**: it is a *text-review verdict that does not cover
  state-change or provenance evidence*, so a green in-gear PASS can never render as
  covering the mechanical evidence lanes (see P2). If the judge prefers not to touch
  the gears at all, the fallback is to scope the block down to "a trace reference
  exists" and drop the verdict — but threading is cheap and more faithful to §9
  (OQ8).
- **Construction site — split by path class, and guarded (⚖ arch-L1-2/-3).** The
  original "built at every `record_route_observed` site" was wrong: of the ~11
  terminal sites, only **two** — the real gear terminals `boot.py:9416` (CLI) and
  `server.py:2957` (pipeline stream) — have `context_pkg` + `mode_meta` + the
  threaded verdict in scope to build the *full* packet. The direct-stream sites
  (`server.py:3720/3739/3796`, no `context_pkg`) and the framework sites
  (`server.py:3270/3278`, `boot.py:9198` — before `context_pkg` exists;
  `framework_elicitation.py:328`) cannot. And **four sites are holds / early
  returns** (`boot.py:9296`, `server.py:2841`, `server.py:3720`, the framework
  exception paths) that ran no gear and pass no `output_text` — building a packet
  there would produce a **misleading** packet (`producer_claim` = a hold refusal,
  the consistency assertion firing on a turn that was *blocked before it ran*). So
  `build_execution_packet(...)` runs **only** at the two gear terminals, **only
  when `output_text` is a real deliverable** (not `None`, not a hold reply). Every
  other terminal path records signals exactly as today with **no packet** — stated
  as a design decision, not a silent degrade. (Direct-stream / framework packets
  are a Phase-5+ concern when those paths adopt the type.)
- **Best-effort, but not silent (⚖ adv-L1-4).** Construction never raises (a
  failure never touches the deliverable `route_output` emits) — but a caught
  construction exception **stamps a distinguishable marker**
  (`packet_construction_failed=true`, via the existing `tool_events._note_failure`
  idiom) so a crash is observably different from a turn that legitimately had no
  packet. Swallowing the exception must not also swallow the fact that it happened.

### P2 — The packet-to-review renderer (§12 evidence-first / claim-last) + the polymorphic seam
- `render_for_review(packet) -> str` emits review text in a **fixed order** that
  physically enforces "evidence over claims" (§12, and the §1/§2 self-evidencing
  reframe made concrete — the renderer is the "demote the report to a claim"
  move):
  1. **TASK + acceptance criteria** (the setpoint). When no acceptance criteria
     exist (light tier / no planning stage in P4), the renderer says so
     **loudly** — `=== NO ACCEPTANCE CRITERIA DECLARED — evidence cannot be judged
     sufficient against a setpoint ===` — never a silent omission (⚖ spec-L1-7).
     A silently-absent setpoint lets the reviewer default to judging the artifact on
     its own fluency, the exact §1/§2 self-evidencing failure the renderer exists to
     prevent; the same "make the missing thing loud" rule the design applies to
     empty evidence lanes applies to the missing setpoint.
  2. **MECHANICAL EVIDENCE FIRST** — a `=== OBSERVED EVIDENCE ===` fence: *what
     changed* (`any_mutation` / `max_mutability` / delta ref) and *what was read
     as a source* (`source_read_channels` / public-safe `source_candidate_reads`).
     When Phase 5 fills `evidence_lanes[].result`, those render here too. In P4
     the lanes are declared-but-unfilled and render as **"evidence not yet
     generated"** — never as "sufficient/passed" (a declared-empty lane must never
     read as a green check). The scope-labeled in-gear verdict (P1) renders here
     too, as a **`=== TEXT-REVIEW VERDICT (does not cover state changes or
     provenance) ===`** line — so a green in-gear PASS sitting next to unfilled
     evidence lanes can never be read as covering the mechanical evidence it never
     saw (⚖ arch-L1-5).
  3. **PRODUCER CLAIM LAST** — a `=== UNVERIFIED PRODUCER CLAIM (weigh against the
     evidence above; do not treat as established) ===` fence wrapping the
     `producer_claim`. Its position and its label are the enforcement: a fluent
     claim cannot out-argue a failing check because the reviewer meets the
     evidence first and the claim explicitly framed as unverified.
- The renderer **reuses `_fenced`** (`boot.py:8420`) so it composes with the
  existing banner-fence convention.
- **The renderer is a tested-but-unwired deliverable in P4, stated plainly (⚖
  arch-L1-4 / adv-L1-2 — the buildability crux the design gate turns on).** Because
  the packet is born at the terminal, *after* every in-gear review has run on the
  raw draft string, **no live P4 verifier ever consumes a packet.** The design
  therefore proves "the existing review logic accepts an `ExecutionPacket`" the
  honest way — a **library helper `_format_artifact_for_review(artifact) -> str`**
  (`str` → returned unchanged; `ExecutionPacket` → `render_for_review`) plus a
  **test that feeds a rendered-packet string into the *real* evaluator/verifier
  user-prompt builder** and asserts it is well-formed review text that drops into
  the exact shape §1.2 uses. **P4 does NOT edit the six in-gear interpolation
  sites** — installing an `isinstance` branch that no live P4 turn exercises is
  parity risk (a slip at any of six live review sites regresses text review) for
  zero P4 behaviour; that six-site install is Phase-6 scaffolding and lands with
  Phase 6, when a live path first hands review a packet. (This retires the earlier
  draft's "install at six sites, inert by default" — the adversarial pass was right
  that it was dead-in-P4 code at live-site risk.)
- **The str branch is a side-effect-free identity**, not merely value-unchanged:
  `return artifact` with no logging, no normalization, no fold, no packet attempt
  (⚖ adv-L1-6). This matters because `msi_run_gear4.invoke_real_gear4` delegates
  steps 3–8 to `boot.run_gear4` and is the one live path that would route through
  the helper if it is ever wired in; a pure identity makes P6's "unaffected"
  guarantee a contract, not a hope, and a test asserts the `str` path makes no
  telemetry/fold calls.
- §12 also names two review-metadata rules the packet's `verification` block must
  *carry the shape for*, even though populating them is the Phase-6 loop:
  findings tagged **`plan_level` vs `execution_level`**, and reviewer-invented
  tests tagged **`acceptance`/`regression`/`diagnostic`/`exploratory`**. P4 adds
  the fields to the schema (so the packet can hold them) without wiring the
  routing that consumes them — and a P4-populated finding mapped from the in-gear
  verdict carries **`class: null`** (untagged), the honest value, because the
  current verifier produces no plan/execution fork; defaulting it to
  `execution_level` would fabricate a routing signal the Phase-6 loop does not yet
  own (⚖ spec-L1-8).

### P3 — The evaluation-lane router — structurally separate from judgment (§5)
- `route_lanes(signals, output_type, mode_meta) -> (evidence_lanes,
  judgment_lanes)` maps the **two folded signals** to lanes (route by evaluation
  unit, not whole task — §5):
  - `any_mutation` (signal 1) ⇒ an `EvidenceLane(lane="diff_validate" |
    "run_observe", target="state_change")` — a delta exists, mechanical evidence
    is owed. Declared in P4; Phase 5's runner fills `generated_by` / `result` /
    `sufficient`.
  - `source_read_suspected` (signal 2) ⇒ an `EvidenceLane(lane="collect_provenance",
    target="grounded_claims")` — claims drawn from sources, provenance owed.
    Declared in P4; the claim-to-source map that fills it is Phase 8.
  - **Neither fired** ⇒ no evidence lane; the packet degrades to plain text review
    (§6 "degrades gracefully … no separate classifier, no wrong-pipeline risk").
- **`EvidenceLane` carries `generated_by`** (the command(s) actually run) as a
  first-class field distinct from `result` / `sufficient` (⚖ spec-L1-6). It is
  empty in P4 and filled by Phase 5's runner — but reserving it now is what lets a
  lane result be tied back to a *declared catalog command* (§10) rather than an
  executor self-report; without it Phase 5 has nowhere to record which declared
  check produced a result, and the renderer has no field to show "this result came
  from THIS command." For the `collect_provenance` lane, the §4/§9 claim-to-source /
  snapshot sub-fields are likewise **reserved and deferred to Phase 8**, not
  invented now.
- **Judgment lanes are NOT derived from the signals.** They come from a mode's
  declared interpretive targets (voice, taste, persuasion). Most modes declare
  none in P4, so most packets carry an empty `judgment_lanes` list — that is
  correct.
- **Structural separation is enforced by TYPE, not convention:**
  `@dataclass EvidenceLane` has `generated_by` / `result` / `sufficient` (a real
  verdict); `@dataclass JudgmentLane` has `critique` and **no verdict field at
  all** (`verdict` is absent by construction, not a settable field it might
  inherit — §5). A matter of taste *cannot* be handed a mechanical pass/fail
  because the type has nowhere to put one.
- **The `sufficient` invariant is pinned at the DATA layer, not just the renderer
  (⚖ adv-L1-5).** `sufficient` is **tri-state** — `unfilled` / `true` / `false` —
  and an `unfilled` lane (every P4 evidence lane) is **not falsy-safe to skip**: it
  must be treated as *evidence owed but not produced* (equivalent to `false`) by
  **every** consumer, and "all lanes sufficient" over an **empty** `evidence_lanes`
  list is **not** "passed." This closes the machine-readable analogue of the
  green-check misread: the renderer-string rule ("evidence not yet generated")
  protects the human's eyes, but Phase 5's runner and Phase 6's stop rule read
  `sufficient` directly — an `unfilled`-reads-as-truthy aggregation would be the
  executor getting a free pass by omission (§16-2). Pinned now, in the phase that
  defines the type; a test asserts a stop-rule-style aggregation over
  declared-but-unfilled lanes does not return "sufficient."
- **Scope of the separation claim (⚖ adv-L1-3).** The type-level separation is
  unbypassable *in the packet data model* — but P4 leaves the one **live** verdict
  path (`_verifier_passed` on the whole draft, `boot.py:9939`) untouched, so on a
  real turn a judgment-bound target ("is this satire landing") is still swept into
  the single mechanical `VERDICT: PASS/FAIL`. P4 delivers **the type that makes the
  Phase-6 routing possible** — sending judgment targets to `judgment_lanes` and away
  from `_verifier_passed` — and does **not** by itself stop a matter of taste from
  receiving a live mechanical verdict. This is §1.3's finding, unchanged for live
  turns until the loop is wired; the design must not let "unbypassable at the data
  layer" be misread as "Phase 4 closes the live leak."

### P4 — The §6 consistency assertion — record, not enforce
- Extend the terminal `divergence` computation (`risk_gate.py:1001-1007`) with the
  §6 declared-vs-observed check, now that both inputs exist:
  - declared `output_type == "text"` **and** (`any_mutation` **or**
    `source_read_suspected`) ⇒ note "declared text, observed reality contact"
    (under-review risk).
  - declared `output_type == "execution"` **and** neither signal ⇒ note "declared
    execution, observed no delta and no source read" (over-heavy).
- **Record only.** The note is appended to the existing `divergence` field (or a
  sibling `consistency` note) on the `route_observed` event and carried on the
  packet. **Not enforced** — this is faithful to §6 ("post-hoc routing lives only
  inside reversible tiers"; irreversible is *already* gated before the run by
  Phase 2's hold, which P4 does not touch) and to the spec's Phase-4 language (a
  consistency *check*, surfaced not blocked). Enforcement — re-routing a misrouted
  task into the execution treatment — is the Phase-6 loop.
- **`output_type` source + default (a real design call):** P4 introduces
  `output_type` as the §9 hint. Its default is **unset / `"unknown"`**, not
  `"text"` — so the assertion is **dormant until a hint is actually declared**. A
  `"text"` default would flag *every* RAG-grounded analytical turn as a misroute
  (every gear-2+ turn trips signal 2 — Phase 3's §3 finding), which is noise, not
  signal. Observed reality stays primary (§6: `output_type` is "a hint that sets
  initial expectations, not a gate"). Whether modes should start declaring
  `output_type` is Open Question 2.
- **The frontmatter `output_type` is the raw declared hint and is NEVER rewritten
  to match observation (⚖ spec-L1-5).** §9's "observed reality overrides" is made
  *visible in the packet*, not asserted once and lost: the frontmatter keeps the
  declared hint, the observed reality-contact character lives in the execution /
  route-signal block, and the consistency note is the artifact that reconciles
  them. A later phase must not "correct" the hint to match observation — doing so
  would destroy the record of the original misroute, which is the one thing the
  consistency check exists to preserve for the Phase-6 re-route decision.
- **Honest status: installed and test-covered, dormant on every live P4 turn (⚖
  adv-L1-1 / arch-L1-6).** Because no mode declares `output_type` in P4 (OQ2
  recommends leaving it unset), the assertion's operand is `unknown` on 100% of
  live turns and it **fires only in unit tests that inject an `output_type`**. This
  is stated, not smuggled: §0 no longer says the assertion "turns on" as a live
  capability. "Unset-by-default keeps it from being noise" and "it delivers no live
  firing in P4" are both true and are not in tension once named. If the judge wants
  one real firing path to exercise the record→packet plumbing end-to-end on a live
  turn, OQ2's alternative (seed 2–3 modes' `output_type`) is the lever.

### P5 — "Same downstream machinery, richer output" — additive, opt-in, default-inert (NOT a second pipeline)
The commitment §15 makes explicit, honored the way Phases 1–3 were:
- The gears still return `str` (plus a scoped verdict threaded on `context_pkg` —
  P1). `_format_artifact_for_review(str)` is a **side-effect-free identity**. No new
  live model call. **No edit to the six in-gear review sites in P4** (that install
  is Phase-6 scaffolding — P2). No return-type change to `run_gear{3,4}` (that would
  ripple to every caller incl. the server twins and `msi_run_gear4` — §1.7, and
  see OQ3). The packet is constructed **at the two gear terminals only**, guarded to
  real deliverables (P1), and its construction **never raises** (with an observable
  failure marker — P1).
- The `route_observed` event gains additive fields (the consistency note; an
  optional packet ref) — additive-key-safe by the Phase-3 finding that nothing
  outside `risk_gate` + tests reads the dict. **Any field that must survive a
  byte-truncated oversized event** (the packet ref, the consistency note) is added
  to the `tool_events` truncation keep-set (`tool_events.py:551-557`), which today
  keeps `risk_tier`/`divergence`/`source_read_suspected` but **drops the whole
  `route_signals` block** — otherwise the ref vanishes on exactly the large turns
  most worth recording (⚖ adv-L1-4). Where a field is deliberately non-durable on
  truncation, the packet-on-disk is the source of truth and the design says so.
- The ExecutionPacket is a richer *form* of the same terminal output, targeting the
  same prompt-assembly seam — **not a parallel Gear-3/4**. This sentence belongs in
  the module docstring and the packet, per the spec's request that the boundary be
  stated so no future reader misreads it.

### P6 — The custom-path reach problem (§15 Phase-0) — scope + deferral, stated not silent
The packet type + renderer + router live in `~/ora` core (P1/P2). The five MSI
custom paths (§1.6) will **not** inherit them for free. Phase 4's handling, and why
it is correct rather than an omission:
- Phase 4 **edits no live review site at all** (P2 drops the six-site install) and
  constructs the packet only at the two core gear terminals (P1), so the MSI custom
  paths — which build their own prompts and, except `invoke_real_gear4`, never
  touch `run_gear{3,4}` — are **untouched, not merely unregressed**. They adopt the
  packet form when the **MSI adapter work lands, which memory pins to Phase 8**
  (project-plugin convention: MSI-specific code stays in
  `~/sites/mainstreetindependent/ora-project/`, never in `~/ora/orchestrator/`).
- The one partial path, `invoke_real_gear4` (`msi_run_gear4.py`), delegates steps
  3–8 to `boot.run_gear4`. Because P4 (a) does not install the seam at the six
  in-gear sites and (b) keeps the library helper's `str` branch a side-effect-free
  identity (⚖ adv-L1-6), `invoke_real_gear4` is **provably unaffected by contract**,
  not by hope. It is the single path to re-check first if a future phase wires the
  in-gear seam live.
- **Deliverable of P4 here:** the enumeration itself (this table) recorded in the
  packet + module docstring, so the Phase-8 MSI adapter has an exact worklist and
  no path is silently left reviewing prose the old way.

---

## 3. Design consequences the judge should weigh explicitly

1. **What runs live in P4 vs what is tested-but-unwired — the line the adversarial
   pass sharpened.** *Live on real turns:* packet **construction** at the two gear
   terminals (the type is a real object, the lane router runs, the consistency
   *note computation* runs — though its `output_type` operand is `unknown`, so it
   emits nothing). *Tested-but-unwired:* the **renderer** (no live P4 verifier
   consumes a packet — the packet is born after the in-gear reviews finish), the
   **consistency assertion firing** (no mode declares `output_type`), and the
   **evidence/judgment separation as a live guarantee** (the live `_verifier_passed`
   path is untouched). The design states this split plainly (§0) rather than
   describing dormant capabilities as live. If the judge wants any of these exercised
   on a real turn, OQ1 (flip one live review path) and OQ2 (seed a few modes'
   `output_type`) are the levers — each imports a slice of Phase-6 wiring and parity
   risk.
2. **The in-gear verdict is not free at the terminal — it must be threaded, and it
   is a text-only verdict.** The `verification` block depends on a verdict that is
   function-local to the gears (arch-L1-1); P4 threads it via `context_pkg` and
   scope-labels it "text-review only" so a green PASS can't masquerade as covering
   the mechanical evidence (arch-L1-5). If the judge rejects the extra `context_pkg`
   mutation, the fallback is a trace-reference-only verification block (OQ8).
3. **The depth/breadth adversarial split is not the evidence/judgment split.**
   §1.3 — gear-4's two verdicts are two *analytical streams*, not two *lane
   kinds*. The lane router (P3) adds an orthogonal axis. The design keeps them
   separate; conflating them would let a judgment target inherit a stream verdict.
4. **Declared-empty evidence lanes are a contract, not a green check — at the data
   layer, not just the renderer.** In P4 an `evidence_lane` has no `result`/
   `sufficient` (Phase 5 fills them). The renderer shows it as "evidence not yet
   generated," AND every code consumer treats `unfilled` as `false` and an empty
   `evidence_lanes` list as *not* passed (P3). This is the §16-2 guard holding even
   before the runner exists — for machine aggregation, not just human eyes.
5. **`output_type` defaulting to unset is what keeps the consistency assertion
   from becoming noise — and also means it fires on zero live turns.** Both are
   true; the packet names the trade rather than celebrating only the first half
   (⚖ adv-L1-1). Unset-by-default makes it a real signal only where a hint is
   declared; in P4 no hint is declared, so it is test-only-firing (§0, P4, OQ2).
6. **Terminal-only construction avoids a return-type blast radius, but is not
   uniform across paths.** Keeping the gears returning `str` and wrapping at the
   terminal means zero change to the ~dozen call sites — but the full packet is
   buildable at only the **two** gear terminals (context_pkg + threaded verdict in
   scope) and must be guarded off hold/early-return/direct-stream/framework paths
   (P1, ⚖ arch-L1-2/-3), not built uniformly at all 11 `record_route_observed`
   sites as the first draft implied.

---

## 4. Scope boundary — what Phase 4 deliberately does NOT do
- **No real evidence generation.** No `.ora/evidence.yaml`, no evidence runner, no
  executed checks — the `evidence_lanes` are declared, not filled (Phase 5).
- **No claim-to-source map, no precise `source_read` labeling** (Phase 8) — the
  `collect_provenance` lane is declared; its provenance content stays the Phase-3
  `source_candidate_reads` descriptors.
- **No live model-review of a packet, no full loop.** No dual-verify-on-evidence,
  no revision router, no escalation-with-linked-branch (Phase 6). The
  `verification` block's `plan_level`/`execution_level`, invented-test tags,
  `confidence`, reviewer-family, and the `loop` block are *reserved schema fields*,
  not wired routing/computation.
- **No edit to the six in-gear review interpolation sites.** The polymorphic seam
  helper exists as a library function proven by test; the in-gear install is
  Phase-6 scaffolding (P2, ⚖ arch-L1-4). P4 touches no live review-prompt site.
- **No packet on non-gear-terminal or hold/early-return paths.** Direct-stream,
  framework, and every hold/error terminal record signals exactly as today with no
  packet (P1, ⚖ arch-L1-2/-3). Those paths adopt the type in Phase 5+.
- **No Phase-5 adapter fields populated.** `execution.mode`/`state_before`/
  `state_after` and `evidence_lane.generated_by` are reserved in the type but
  filled by Phase 5's runner, not P4.
- **No before-clock change.** The risk tier, the irreversible hold, and the
  criteria pass are Phase 2 and untouched. The consistency assertion is
  record-only (P4).
- **No enforcement of the misroute** — surfaced, not blocked (§6).
- **No MSI adapter work** — the custom paths are enumerated (P6) and deferred to
  Phase 8; `~/ora` core stays project-agnostic.
- **No new redaction surface** — the packet's `source_reads` reuse the Phase-3
  public-safe `source_candidate_reads`; the packet carries no field that could
  hold unredacted secret/sensitive content. Large artifacts are referenced, not
  inlined (§9), so no blob crosses a persistence boundary in P4.

---

## 5. Test + parity plan
- **New unit tests** (a new `orchestrator/tests/test_execution_packet.py` +
  additions to `test_risk_gate.py`):
  - packet shape: tier-optional blocks absent/present per tier; **every §9 block
    reserved** (`loop`, `verification.confidence`/`reviewer_a`/`reviewer_b`,
    `execution.mode`/`state_before`/`state_after`, `evidence_lane.generated_by`)
    present-but-unfilled; `frontmatter()` returns only flat scalars; large artifacts
    held as refs not blobs.
  - renderer: evidence-first / claim-last ordering; the producer claim carries the
    "unverified" label; a declared-empty evidence lane renders as "not yet
    generated," never sufficient; **missing acceptance criteria render as the loud
    "NO ACCEPTANCE CRITERIA DECLARED" banner**, never silently omitted (spec-L1-7);
    **the in-gear verdict renders as the scoped "TEXT-REVIEW VERDICT (does not cover
    …)" line**, never an unqualified green check (arch-L1-5); output composes with
    `_fenced` and never collides with `#` headings in the body.
  - acceptance-by-test (the renderer's core P4 proof): a **rendered-packet string
    drops cleanly into the *real* evaluator/verifier user-prompt builder** and is
    well-formed review text (arch-L1-4) — this is how "the review logic accepts an
    `ExecutionPacket`" is proven without editing the six live sites.
  - polymorphic seam library fn: `_format_artifact_for_review(str)` is a
    **side-effect-free identity** (byte-identical value AND makes no telemetry/fold
    calls — adv-L1-6); `_format_artifact_for_review(packet)` yields the rendered
    view.
  - lane router: `any_mutation` ⇒ diff/run evidence lane; `source_read_suspected`
    ⇒ provenance lane; neither ⇒ no evidence lane (text degrade); `JudgmentLane`
    has no verdict field (structural-separation assertion); **`sufficient` is
    tri-state and an aggregation over declared-but-unfilled or empty lanes does NOT
    return "sufficient"** (adv-L1-5).
  - verification sourcing: the in-gear verdict is **threaded via `context_pkg`** and
    read at the terminal (arch-L1-1); a P4 finding carries **`class: null`**
    (spec-L1-8).
  - construction site + guard: full packet built **only** at the two gear terminals
    with a real deliverable; **no packet** on a hold reply / `output_text is None` /
    direct-stream / framework path (arch-L1-2/-3); a caught construction failure
    **stamps `packet_construction_failed`** (observably ≠ "no packet" — adv-L1-4).
  - consistency assertion: text+mutation ⇒ note; text+source-read ⇒ note;
    execution+neither ⇒ note; `output_type` unset ⇒ **no** note (dormant default,
    the live-P4 case); the frontmatter `output_type` is **never rewritten** by
    observation (spec-L1-5); record-only (no tier change, no enforcement).
  - truncation survival: any packet-ref / consistency field that must persist is in
    the `tool_events` keep-set and survives a byte-truncated oversized
    `route_observed` (adv-L1-4).
  - additive/back-compat: existing `TestRouteObserved` / `TestSourceReadSignal`
    shape assertions still pass; `record_route_observed` still returns the same
    top-level shape (new fields additive); construction never raises on a
    malformed turn (but is observable when it fails).
- **Parity:** run with `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`; capture a
  pre-edit baseline in the SAME implementation worktree, diff sorted FAIL/ERROR
  name lists pre-vs-post, target **zero new failures** against the 22F/5E
  environmental baseline.
- **Adversarial pre-check** before the review packet: a small Workflow over ONLY
  the changed logic (renderer ordering, seam no-op-on-str, lane type separation,
  consistency-assertion firing conditions, terminal construction never-raises);
  verify each finding against the code myself (the majority vote under-reports);
  fold the real ones; re-run focused + full parity; resubmit with diff + parity
  evidence.

---

## 6. Open questions for the judge
1. **How live should Phase 4 go? (the headline.)** *Recommended:* Architecture A —
   build the type + renderer + router + consistency assertion as a library;
   construct the packet live **only at the two gear terminals**; prove "the review
   logic accepts an `ExecutionPacket`" by a **test that feeds a rendered-packet
   string into the real evaluator/verifier prompt builder** (NOT by editing the six
   live in-gear sites — that install is Phase-6 scaffolding); no live model-review
   of a packet. This is honest about what runs live (construction) vs
   tested-but-unwired (the renderer, the assertion firing, the live judgment/
   evidence separation). *Alternative:* flip one live path (e.g. gear-4 terminal) to
   actually render + review a packet now — richer, gives the renderer one real
   firing, but imports Phase-6 loop-wiring and live-verify parity risk. Recommend A.
   The adversarial pass (⚖) was pointed: if the judge wants Phase 4 to be more than
   scaffolding, A+one-live-path is the minimal way to make the renderer non-inert.
2. **Should modes declare `output_type` now, or leave it unset?** *Recommended:*
   introduce `output_type` as a §9 hint defaulting to **unset/"unknown"** (the
   consistency assertion stays dormant until declared); observed signals remain
   primary. Populating mode-declared `output_type` (and thus arming the assertion
   broadly) can wait. Alternative: seed a few modes' `output_type` now to exercise
   the assertion end-to-end.
3. **Construct the packet at the terminal, or change `run_gear{3,4}` to return
   one?** *Recommended:* terminal-only — gears keep returning `str`, the packet
   wraps at the existing fold point, zero blast radius. A gear return-type change
   is cleaner conceptually but ripples to all callers, the server twins, and
   `msi_run_gear4` (§1.7). Recommend terminal-only.
4. **Declare empty evidence lanes in P4, or emit none until Phase 5 can fill
   them?** *Recommended:* declare-empty — a lane with an unfilled `result`
   documents the evidence owed and is the exact contract Phase 5's runner fills;
   the renderer shows it as "not yet generated," and the invariant "empty lane ≠
   sufficient" is test-enforced. Alternative: emit no evidence_lanes until they can
   carry a real verdict (less informative, but zero risk of an empty lane being
   misread).
5. **Consistency assertion — pure record, or feed something?** *Recommended:* pure
   record in P4 (append to `divergence`). Raising verify rigor or re-routing on a
   detected misroute is before-clock enforcement that §6 reserves and the Phase-6
   loop owns. Recommend defer.
6. **Judgment-lane population.** *Recommended:* define the `JudgmentLane` type +
   the structural separation now (the load-bearing §5 guarantee), but populate
   judgment lanes only from a mode-declared interpretive-target list — which most
   modes won't have in P4, so most packets carry an empty judgment block. Is
   "type + separation now, population later" the right P4 line, or should P4 also
   define where a mode declares its interpretive targets?
7. **Module location + provisional names.** *Recommended:*
   `orchestrator/execution_packet.py` (one consolidated file: dataclass + lane
   types + renderer + router). The `output_type` enum values
   (`text`/`execution`/`unknown`), the renderer's fence labels, and the lane
   `lane:` enum are provisional tuning/naming surfaces (flagged per house rule),
   retunable, not calibrated.
8. **Verification-block sourcing (raised by the adversarial pass).** The in-gear
   verdict is function-local to `run_gear{3,4}` and unreachable at the terminal.
   *Recommended:* **thread it out via `context_pkg`** (already mutated in place and
   in scope — the mechanism Phase 2 used for `risk_tier`/`_route_turn_ts`), so the
   `verification` block reflects the review that actually ran, scope-labeled
   "text-review only." A small in-gear mutation, no gear return-type change.
   *Alternative:* keep the gears completely untouched and scope the P4
   `verification` block down to "a trace reference exists" (drop the verdict) — less
   faithful to §9 but zero gear edit. Recommend threading.

---

## ⚖ Completeness-critic folds (adversarial pass — 4 diverse lenses × adversarial verify; 22 raw, 21 CONFIRMED, 1 correctly REJECTED)

The pass ran four diverse lenses (code-claim verifier / spec-completeness /
seam-integration-architecture / adversarial-design), each finding adversarially
verified against the pinned repo (`@0dda6ac6`) and the spec, returning **both**
confirmed and rejected findings so the rejected ones could be re-checked by hand.
I re-verified the three load-bearing findings against the code myself (the
architecture lens's two blockers and the truncation keep-set): all three
confirmed — no verdict-bearing `context_pkg` assignment exists (so the in-gear
verdict is unreachable at the terminal); `boot.py:9296` and the other hold sites
pass no `output_text` and return a hold string; and the `tool_events` keep-set
(`:551-557`) keeps `risk_tier`/`divergence`/`source_read_suspected` but **not**
`route_signals`.

**Folded (confirmed, real) — the load-bearing architecture + design folds:**
- **[architecture L1-1 — BLOCKER]** the `verification` block cannot "reflect the
  review that ran" because the in-gear verdict is function-local to `run_gear{3,4}`
  (they return only a `str`) and unreachable at the terminal. **Fold:** thread the
  verdict via `context_pkg` (P1 + OQ8), scope-labeled text-review-only.
- **[architecture L1-2 / L1-3 — BLOCKER / MAJOR]** "built at every
  `record_route_observed` site" was wrong: only the two gear terminals have
  `context_pkg`+`mode_meta` in scope; direct-stream/framework sites do not; four
  sites are holds/early-returns that would build a **misleading** packet (a hold
  refusal as `producer_claim`, the assertion firing on a blocked turn). **Fold:**
  construct only at the two gear terminals, guarded to real deliverables; no packet
  elsewhere (P1, §4, consequence 6).
- **[architecture L1-4 / adversarial L1-2 — MAJOR / BLOCKER]** installing the seam at
  the six in-gear sites is dead-in-P4 code at live-review-site parity risk (the
  packet is born at the terminal; no live P4 verifier ever sees a packet), and the
  renderer's evidence-first protection governs **no live P4 review**. **Fold:** drop
  the six-site install; prove acceptance by a rendered-string test into the real
  prompt builder; label the renderer tested-but-unwired in §0/P2; defer the install
  to Phase 6.
- **[architecture L1-5 — MAJOR]** the in-gear PASS (text-only) can contradict the
  terminal evidence (mutation/source-read) and render as a green check next to
  unfilled lanes — the §12 failure the phase exists to prevent, from inside. **Fold:**
  render it as a scoped "TEXT-REVIEW VERDICT (does not cover state changes or
  provenance)" (P2).
- **[adversarial L1-1 / architecture L1-6 — MAJOR / MINOR]** the consistency assertion
  fires on zero live P4 turns (no mode declares `output_type`) — a headline "turns
  on" deliverable that is test-only-firing. **Fold:** §0 reworded from "turns on" to
  "installs"; P4 + consequence 5 name the dormancy plainly; OQ2 offers the
  seed-modes lever.
- **[adversarial L1-3 — MAJOR]** "structural separation unbypassable at the data
  layer" is true of the packet but the live `_verifier_passed` path is untouched, so
  a judgment target still gets a mechanical verdict on real turns. **Fold:** scope the
  claim (P3) — P4 delivers the type that makes Phase-6 routing possible, it does not
  close the live leak.
- **[adversarial L1-4 — MAJOR]** never-raises silently swallows construction failures,
  and the truncation keep-set drops `route_signals` (so an added packet ref vanishes
  on oversized turns). **Fold:** stamp `packet_construction_failed` on a caught error
  (P1); add any must-survive field to the keep-set or declare it non-durable (P5).

**Folded (confirmed, real) — schema-completeness + precision:**
- **[spec L1-1/-2/-4/-6 — MAJOR/MINOR]** the §9 `loop` block, `verification.confidence`
  + `reviewer_a`/`reviewer_b` (the §12 single-family-degrade governance rule),
  `execution.mode`/`state_before`/`state_after` (§11), and `evidence_lane.generated_by`
  (§10) were all missing from the packet type. **Fold:** every §9 block is now
  reserved-but-unfilled in the type (P1/P3) so later phases fill rather than retrofit.
- **[spec L1-3 — MAJOR]** `enforcement_model: in_harness` was hardcoded (the §17
  overclaim trap). **Fold:** carries a §7-tied contract + a TODO for orchestrated/
  MSI-custom paths (P1).
- **[spec L1-5 — MINOR]** "observed reality overrides" (§9) was asserted, not visible.
  **Fold:** the frontmatter hint is never rewritten; the observed character lives in
  the signal block; the note reconciles them (P4).
- **[spec L1-7 — MINOR]** a missing setpoint was silently omitted. **Fold:** the
  renderer emits a loud "NO ACCEPTANCE CRITERIA DECLARED" banner (P2).
- **[spec L1-8 — NIT]** a P4 finding's `class` should be honest null, not defaulted
  `execution_level`. **Fold:** stated (P2).
- **[adversarial L1-5 — MINOR]** the "empty lane ≠ green check" rule was renderer-only;
  a machine aggregation could read `unfilled`/empty as truthy. **Fold:** `sufficient`
  is tri-state, pinned at the data layer, empty-list ≠ passed, test-enforced (P3).
- **[adversarial L1-6 — MINOR]** the seam's `str` branch was "unchanged" (a value
  claim), not side-effect-free; `invoke_real_gear4` is the one live path through it.
  **Fold:** side-effect-free identity by contract + a no-side-effect test (P2/P6).
- **[code-claims L1-1 — NIT]** the "(28, Phase 3)" test count was bound to the wrong
  pair. **Fold:** corrected to "TestRouteObserved (Phase 2, 5) + TestSourceReadSignal
  (Phase 3, 28)" (§1.7).

**Re-checked and correctly REJECTED (not folded):**
- *[code-claims L1-2]* — the `boot.py:~12323-12324` pin for `depth_verdict`/
  `breadth_verdict` "names a different statement than the symbols." False: those exact
  symbols appear verbatim on those lines as the arguments to `_verifier_passed`, and
  the packet's convention is to anchor verdict claims at the `_verifier_passed`
  resolution point (the load-bearing line for the §5 argument, since both streams run
  the *same* mechanical parser), not the raw assignment. The `~` is a deliberate
  "near here" pin. No reader is misled; not a defect.

**Net effect on the design:** the pass did not overturn Architecture A, but it
materially corrected its *buildability* (verdict must be threaded; construction is
two-terminals-guarded, not universal), *scope honesty* (the renderer + assertion are
tested-but-unwired, not live), and *schema completeness* (every §9 block reserved).
These are folded into P1–P6, §3, §4, §5, and OQ1/OQ8 above. No new blocker survives.
