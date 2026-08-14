# Phase 2 Design — Risk Gate + Two Clocks (spec §6/§8/§15-P2)

APPROVED WITH CONDITIONS by the judge 2026-07-03; the 9 conditions are folded
below (marked ⚖). Implementation target: main @ c3a76786 (Phase 1 #174 +
path-cleanup #175 landed). Worktree: `/Users/oracle/ora-worktrees/phase2`
(branch execution-review-phase2). Grounded in a 4-reader seam scout + a
completeness-critic pass (✦) + the judge's conditions (⚖).

## ⚖ Judge conditions folded (2026-07-03)

1. ⚖ **Default `standard`, not `light`, for ordinary dispatched/executor
   turns.** `light` only for trivial/self-contained text turns, runtime/meta
   commands, and explicit override. (Reverses the draft's recommendation;
   open question 1 resolved by the judge → standard.) See D1.
2. ⚖ **`/risk` semantics**: sticky `/risk` sets a default/FLOOR but may NOT
   downgrade a deterministic high-risk/irreversible floor on future turns;
   downgrading `irreversible` substitutes for the hold ONLY as an explicit
   per-turn action or the hold-card option, recorded as the task approval
   decision; per-call Phase 1 gates still fire. See D5.
3. ⚖ **Fingerprint binds more** than conversation_id|cleaned-prompt: enriched
   prompt + execution surface + mode/framework id + output target/directives
   + config/manual selections + attachment identifiers. Same task re-admits
   once; materially different task does not. See D4.
4. ⚖ **Framework elicitation final deliverables need explicit coverage** —
   `framework_elicitation._produce_deliverable()` (line 211) calls
   `execute_framework()` DIRECTLY (line 237), bypassing the server/boot
   framework branches. Seed the tier + hold there (or thread the decision
   in). Tests cover BOTH `/framework name query` and interactive
   final-deliverable turns. See D1/D4.
5. ⚖ **`/risk <tier> <task>` parsed before runtime slash dispatch AND before
   `/direct`/`/save` parsing** (parse_user_command runs at server.py:5815 in
   _invoke_pipeline, before _pipeline_stream's is_runtime_command at 3003 —
   inline /risk must be lifted at the very entry or it's swallowed).
   `/risk <tier>` with no task stays the sticky runtime command. See D5.
6. ⚖ **Criteria-pass failure must NOT silently execute as `light`** — surface
   the failure and hold/ask/require override. See D6.
7. ⚖ **`route_observed` best-effort on ALL terminal paths** — errors,
   holds/cancels, direct mode, clarification resume/skip, framework paths,
   terminal boot.run_pipeline. Fold scoped by a per-turn identifier / exact
   trace dir so overlapping conversation events can't contaminate. See D3.
8. ⚖ **MSI custom gear paths + daemons stay deferred to Phase 8** — Phase 2
   claims NO task-tier coverage for them; the Phase 1 per-call gate remains
   the enforcement backstop. See D1.
9. ⚖ **Stealth task-token purge is IN SCOPE for Phase 2.** See D4.

Grounded in a 4-reader seam scout of the landed code + one adversarial
completeness-critic pass (findings folded; changes marked ✦).

## Scope

Phase 2 delivers: (1) an upfront per-task `risk_tier`
(light|standard|high-risk|irreversible), assigned conservatively before the
run, user-overridable, recorded; (2) the two-clock wiring — tier decided
before the run, route signals recorded after the run from the Phase 1
tool-event log, with the hard boundary that tier=irreversible requires
recorded human approval BEFORE the executor runs; (3) the per-tier
criteria-source rule (criteria set prior to and separate from execution for
floored tiers; none at light).

NOT in Phase 2 (spec §15): source_read over-approximation (Phase 3), lane
routing/packet/output typing (Phase 4), Evidence Contract + catalog
(Phase 5), the assembled loop + dual planning + high-risk enforcement
machinery (Phase 6). ✦ Also explicitly deferred: tier-conditional changes to
the Phase 1 per-call block ladder (the earlier external_write-tightening
idea is CUT — it mutated Phase 1 gate semantics with invented policy;
high-risk enforcement weight arrives with Phase 6).

## Vocabulary

`risk_tier` everywhere (never bare "tier" — `triage_tier` already means
analytical depth at boot.py:6613). New queue kind: `task_gate`. New slash
command: `/risk`.

## D1. Tier assignment (the before-clock) — deterministic, no new model call

Turn start already pays exactly one model call (Phase A, step1_cleanup
slot); pre-routing stages are deterministic. The classifier adds zero model
calls:

- **Stage A — turn-head floor**: deterministic pattern table over the raw
  user input, run in `_pipeline_stream`'s turn head (before all
  short-circuits) and in `boot.run_pipeline`'s equivalent. Irreversible-
  class intents (prod deploy, email/SMS send, publish, payment, force-push,
  remote delete, DNS) floor `irreversible`; external-write-class intents
  floor `high-risk`. PROVISIONAL vocabulary, seeded from Phase 1's gate
  vocabulary, extended from observed gate events.
- **Stage B — mode floor**: optional `## RISK TIER` heading in mode files
  (extract_default_gear idiom, boot.py:5737). Absent → no floor. Shipped in
  the mode template only; NOT batch-added to the 58 modes (per-mode review
  discipline).
- **Default** (⚖ condition 1): ordinary dispatched/executor turns default
  **standard**. `light` is reserved for: turns the bypass guard sends to
  _direct_stream as trivial/self-contained text (chitchat, greetings,
  prior-conversation lookups), runtime/meta commands, and explicit user
  override. The self-evidencing analytical-text argument still holds for
  the *criteria* question (D6), but the default TIER is standard per the
  judge — safe default for non-trivial work; the per-call gate remains the
  tier-independent backstop and `route_observed` still records mutations.
- **Final tier** = max(Stage A, Stage B, sticky conversation override
  floor) with explicit user override (D5) winning.
- ✦ **Fail-mode (A2)**: if tier assignment throws, the turn runs at
  `high-risk` with a recorded `assignment_error` on the task_tier event and
  a visible warning line in the reply — never a silent fail-open to light.

✦ **Path coverage** (corrected; there are FIVE pre-step1 paths plus two
non-pipeline paths):
- runtime slash commands: EXEMPT (mechanical, no executor; gating the
  approval surface is circular).
- resolution-chain continuations: EXEMPT (commit already-queued decisions).
- manual-mode clarification continuation (server.py:3071): covered — it
  re-enters the funnel, where the hold + enrichment recheck (D4) sit.
- framework one-shot `/framework x q` AND elicitation deliverable turns:
  COVERED BY NEW WORK — these reach run_gear3/4 via milestone_executor,
  which builds its own context_pkg and never seeds turn ctx (critic A1).
  Phase 2 adds: turn-ctx seeding (conversation_id, stealth, risk_tier) +
  the pre-executor hold check in the framework dispatch branch on BOTH
  surfaces, before execute_framework's gear dispatch. Without this the
  tier carrier is empty on the framework path and the after-clock fold
  can't even correlate its events.
- `/direct` turns (✦ C3): Stage A runs at `_direct_stream`'s head too;
  the ctx re-seed at server.py:3534 gains a risk_tier parameter (today it
  REPLACES the whole ctx dict and would clobber a turn-head tier); the
  pipeline bypass fall-through threads the computed tier in.
- ✦ MSI custom gear paths + daemons (article_generator, backfill,
  gear3_orchestrator, msi_run_gear4) — OUT OF PHASE 2 SCOPE, explicitly:
  they run headless with no human to hold for; they stay under the
  per-call gate floor (which is tier-independent and already enforced).
  Task-tier adapters for them are Phase 8 work. (Open question 4.)

## D2. What each tier changes in Phase 2

- `light` — nothing new.
- `standard` — criteria pass (D6). Per-call gate unchanged.
- `high-risk` — criteria pass; tier recorded for Phase 6 to arm. ✦ No gate
  ladder changes (cut).
- `irreversible` — recorded human approval BEFORE the executor runs (D4)
  + criteria pass.

## D3. Carrying the tier + the after-clock

**Authoritative value**: `step1_result['risk_tier']` on the pipeline path
(rides `_pending_clarification` pause/resume verbatim); the hold check reads
it EXPLICITLY as data (✦ critic B1: the ContextVar ctx is seeded inside
step-2 assembly, i.e. AFTER the funnel entry where the hold sits, and a
pooled thread can carry the previous turn's ctx — the hold must never read
its trigger from ctx). ctx (`tool_events.set_turn_context`) gains a
`risk_tier` field seeded at the two existing seed sites + the new
framework-path seed, so the per-call gate and event records see it; child
processes get a fourth env var `ORA_RISK_TIER` beside the existing triple
(project_registry.py:915-936, get_turn_context fallback).

**Records**: a `task_tier` tool-event at assignment
{risk_tier, floors_fired, default_used, override:{by,from,to}|null,
assignment_error|null}; trace meta sidecar; `risk_tier` into
context_pkg.

**After-clock** (⚖ condition 7): a `route_observed` event folded from the
turn's tool-events: {any_mutation, max_mutability, reads_present,
max_sensitivity, max_egress, gate_outcomes}. `reads_present` is explicitly
NOT source_read (Phase 3). No output_type comparison — that field doesn't
exist until Phase 4; the one divergence check wired now is well-defined
today: a `standard`-or-lower turn with any_mutation beyond its tier logs a
tier-vs-observed note.
⚖ **Best-effort on ALL terminal paths, never raising**: normal convergence
(_invoke_pipeline), errors (wrapped so a failing turn still records what it
did before dying), holds/cancels (records the blocked outcome), direct mode
(_direct_stream end), clarification resume AND skip endpoints, the framework
one-shot + elicitation-deliverable paths, and terminal boot.run_pipeline
end. A single `record_route_observed(turn_key)` helper in risk_gate.py is
called from every terminal seam inside a try/except that never propagates.
⚖ **Scoped by exact trace dir** when present (the per-turn
tool-events.jsonl IS the bounded unit); for direct/global-sink turns
(trace_dir=None) the fold filters the global sink by (conversation_id, turn
timestamp window) — a `turn_key` = trace_dir or (conversation_id, turn_ts)
carried from the before-clock so overlapping conversation events never
contaminate a sibling turn's fold.

**Hard boundary**: the only pre-run block is tier=irreversible; everything
else observes after (post-hoc routing stays inside reversible tiers by
construction). The Phase 1 per-call gate remains the tier-independent
enforcement backstop.

## D4. The tier=irreversible pre-run hold

Placement: the pre-executor chokepoints — server funnel
`_run_pipeline_from_step2` entry (covers all four resume call sites:
3093/3452/10530/10612), `_direct_stream` head, boot.run_pipeline pre-gear,
and the framework dispatch branches (✦ A1). At the funnel entry the check
consumes `step1['risk_tier']` passed as data (✦ B1).

✦ **Enrichment recheck (C2)**: clarification answers are appended to the
prompt inside the funnel while step1 rides verbatim — so the funnel entry
re-runs the Stage-A table over the ENRICHED prompt and takes
max(step1.risk_tier, enrichment floor). "Summarize the plan" [light] +
answer "…then email it to the client list" holds correctly.

HOLD mechanics (reusing the Phase 1 stack; one new queue kind):
- Durable Paused card kind='task_gate' (kind-dispatch pattern:
  one guard branch in resolution_chain._maybe_commit_gate_entry and
  slash_commands._maybe_resolve_gate_entry_at, both delegating to a new
  tool_events.resolve_task_gate_entry; metadata inside event{} because
  PausedEntry drops unknown top-level keys; name pre-filled to skip the
  synchronous AI-naming call).
- Assistant reply emitted as a plain 'response' event (the only pause shape
  that reaches the /chat plain-HTTP client): "classified irreversible —
  reply 1 to approve, 2 to cancel, or /risk <tier> to override" + hidden
  marker `<!-- ora-task-gate: {"queue_id":…, "fp":…} -->`, detection slotted
  into the _pipeline_stream ladder beside resolution-chain.
- Parked resume state shaped like _pending_clarification (volatile,
  documented).

✦⚖ **Approval token (C1 redesign + condition 3)**: action='task_execute',
args_hash = sha1 over a STRUCTURED fingerprint, not just conversation_id +
cleaned prompt. The fingerprint binds (condition 3): conversation_id +
enriched prompt (post-clarification) + execution surface (chat|direct|
framework|terminal) + mode/framework id + output target/directives
(route_output target, /save form) + config name + manual model selections +
attachment identifiers (image content hashes) where present. Rationale: the
same task re-admits once (all binding fields identical); a materially
different task in the same conversation (different target, different
attachment, different mode) does NOT inherit the token. `_task_fingerprint()`
in risk_gate.py builds it from the turn's assembled parameters.
granted_via='tier-gate' (hold) or 'user-override' (explicit downgrade). TTL
PROVISIONAL 15 min. **Consume-on-resume** (one-shot): the proceeding run
consumes the token; an identical later task needs fresh approval.

✦ **Resume paths (B3)**:
- Origin-conversation "1" reply (marker path): commits the card, mints +
  immediately consumes the token, resumes the parked state synchronously —
  the full in-place resume.
- /approve N and the sidebar Approve button (which sends "1" into the
  DISCUSSION conversation, not the origin — verified): these mint the token
  and remove the card but cannot resume the parked generator. Their commit
  message says so: "approved — re-send the task (or say 'continue') in the
  origin conversation." The re-sent task recomputes the same fingerprint,
  finds the valid token, consumes it, and proceeds without a second hold.
  The same mechanism makes server-restart recovery honest: parked state is
  lost, the durable token survives, re-send admits.

✦ **Stealth (C4)**: no queue card (Phase 1 invariant). The marker carries
{fp, tier} only — no queue_id, no prompt text. The commit helper has a
stealth branch: "1" in the origin conversation mints + consumes the token
directly with no card lookup. Approvals.json entries are existence-only
metadata (action + hash + conversation_id) — and conversation_closeout
gains a small Layer: purge task-gate tokens matching the purged
conversation_id, keeping the stealth zero-residue promise (proposed as
in-scope; open question 5).

DENY/cancel: parked state dropped, card removed, gate event recorded.
The per-call gate still fires on the actual irreversible calls inside an
approved run — task-level intent approval + call-level specifics are two
different recorded decisions, both wanted.

## D5. User override (⚖ conditions 2 + 5)

Surfaces:
- (a) `/risk <tier> <task>` inline prefix — applies to THAT turn only.
  ⚖ Parsed at the very entry of the turn, BEFORE parse_user_command (which
  strips /direct //save at server.py:5815, inside _invoke_pipeline, ahead
  of _pipeline_stream) and BEFORE the is_runtime_command short-circuit
  (server.py:3003 / boot.py:9085) — otherwise inline /risk is swallowed as
  a mechanical command. Extraction lives in a new `strip_risk_prefix(input)`
  called first thing in _invoke_pipeline and boot.run_pipeline; the cleaned
  input flows onward, the override rides as a turn parameter.
- (b) `/risk <tier>` with NO task — sticky per-conversation, stored on the
  conversation envelope, cleared by `/risk auto`. Stays a runtime slash
  command (is_runtime_command surface).
- (c) hold-card option 3 ("proceed at high-risk instead").

⚖ **Floor-vs-override semantics (condition 2):**
- A sticky `/risk <tier>` sets a per-conversation DEFAULT/FLOOR. It may
  RAISE the working tier for future turns; it may NOT lower a deterministic
  Stage-A/Stage-B high-risk or irreversible floor on a later turn. Final =
  max(deterministic floors, sticky floor) then per-turn explicit override.
- Downgrading `irreversible` substitutes for the pre-run hold ONLY when it
  is an explicit per-turn action — inline `/risk <lower> <task>` on that
  turn, or hold-card option 3. A sticky prior `/risk` does NOT pre-authorize
  a future irreversible turn. When an explicit per-turn downgrade skips the
  hold, it is recorded as the task approval decision (a task_tier event with
  override provenance AND a `task_execute` token minted granted_via=
  'user-override', so the "recorded human approval" artifact exists exactly
  as it would from the hold).
- The per-call Phase 1 gate still fires on the actual irreversible calls
  regardless of any tier override (tier-independent backstop).
All overrides flagged once in the reply when lowering a floored tier
(user-owns-risk standing rule).

## D6. Per-tier criteria-source rule

✦ (Critic A3: the earlier "tool-bearing paths" filter was an upfront
will-it-use-tools pre-classifier — exactly what §6 rejects. Dropped.)

- `light`: no criteria step, by construction.
- `standard`+ (ALL such turns, no tool-availability filter): one
  criteria-setting pass (sidebar slot) runs at the pre-executor chokepoint,
  BEFORE the executor, producing acceptance_criteria from the instruction +
  mode contract; recorded to trace + tool-event; injected read-only into
  the executor prompt. Satisfies §16 point 1 in its single-family
  standard-tier form; dual-family criteria arrive with Phase 6.
- With standard as the default (⚖ condition 1), every ordinary dispatched
  turn pays this one small-model call — the judge's accepted cost floor.
- ⚖ **Criteria-generation failure does NOT fall through to light** (condition
  6): if the sidebar pass errors or returns empty, the turn does NOT proceed
  as if unfloored. It surfaces the failure and holds — for standard it
  degrades to a visible warning + proceeds only if the user re-confirms
  (question-as-response, same marker channel); for high-risk/irreversible it
  routes into the D4 hold. Recorded as a `criteria_error` on the task_tier
  event. Never a silent execute-as-light.

## Files touched

ONE new module `orchestrator/risk_gate.py` (pattern table + classifier +
fingerprint + hold/commit + route-signal fold + `## RISK TIER` extraction);
edits: boot.py (turn-head floor, step1 stamp, ctx seed field, pre-gear
hold, run-end route record, framework-branch seed+hold), server.py
(turn head, funnel-entry hold + enrichment recheck, _direct_stream Stage A
+ ctx tier, _invoke_pipeline + clarification-resume route record, marker
ladder entry, framework-branch seed+hold), tool_events.py (ctx field,
task-token grant/consume, resolve_task_gate_entry, closeout token purge
hook), milestone_executor.py (receive tier via ctx), resolution_chain.py +
slash_commands.py (one kind branch each; `/risk` handler),
oversight_queue serializer (expose kind), project_registry.py
(ORA_RISK_TIER), conversation_closeout.py (task-token purge), mode template
doc. Tests: new test_risk_gate.py + additions to
test_tool_events/test_dispatcher_gate/test_stealth_short_circuit_purge.

## Constraints honored

Runtime principle (all decisions at runtime); reuse-over-parallel (queue /
resolution / token / marker stacks reused — no parallel approval system);
vault YAML minimalism (no vault schema change); provisional constants
flagged (pattern table, light default, fingerprint normalization, 15-min
task-token TTL); consolidated files (one new module).

## Open questions — RESOLVED by the judge (2026-07-03)

1. Default tier → **standard** for ordinary dispatched/executor turns
   (condition 1). Light reserved for trivial text / meta / override.
2. Criteria pass → single sidebar-slot pass approved for standard+, with the
   condition-6 non-silent-failure requirement (D6).
3. Override-downgrade of `irreversible` → allowed only as an explicit
   per-turn action / hold-card option, recorded as the task approval
   decision (condition 2, D5).
4. MSI custom gear paths + daemons → deferred to Phase 8; Phase 2 claims no
   coverage; per-call gate is the backstop (condition 8, D1).
5. Stealth task-token purge → in scope for Phase 2 (condition 9, D4).
