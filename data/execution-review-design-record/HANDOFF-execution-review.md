# Execution Review — Session Handoff (durable state, updated 2026-07-07)

Purpose: everything needed to resume if context is compacted/reset. This
captures the context-only reasoning trail across phases.

RESUME POINTER (2026-07-07 — CURRENT, authoritative; supersedes every "resume here first" tail below):
**Phases 1–7 + Phase 8 Chunks A/B/C ALL LANDED, AND the ora-side of Chunk D is now LANDED too.** A fresh
full-project judge review (2026-07-07) ran + a user-directed STABILIZATION PASS landed four PRs on
origin/main, now at `5bc44871`:
  • #197 `d17e8770` — F1 hotfix: closed the `source` shell side-door (was un-gated in bash_execute).
  • #198 `aa60c4c9` — Phase 8 Chunk D ora-side seam: `orchestrator/execution_review.py::record_program_run`
    (+ `tool_events.set_turn_context` reset token / `reset_turn_context`). enforcement_model mandatory+
    validated+refuse-on-invalid; signals folded from the run's own event log; persist-then-write.
  • #199 `ac74189c` — F2 (escalation branch now carries a per-turn trace_dir discriminator so a 2nd
    escalation in one conversation no longer force-overwrites the 1st, §13) + F3 (a content-withheld
    sensitive source is flagged `content_withheld` and excluded from the provenance mapper's offered set,
    §4 consulted≠used).
  • #200 `5bc44871` — low-item cleanup: F4 (SBPL now write/read-allows the per-run scratch $HOME), F5
    (corrected the stale "no caller passes sparse=" comment — the Chunk-C caller DOES; disclosed the benign
    worktreeConfig residue), F6 (render_validity.py `from __future__ import annotations` for py3.9), F8
    (added the Execution Review Subsystem section to ~/ora/CLAUDE.md).
**REMAINING = the MSI-side of Chunk D (separate MSI-repo landing):** instrument `_call_openrouter`; wire
`invoke_real_gear4` (per-run context via the token primitive; `record_program_run` AFTER final-output
selection across all 4 consolidation modes; `enforcement_model="boundary_only"`; restore context in
finally); publish boundary + `standing:true` deploy_probe recipe; MSI `.ora/evidence.yaml` at the astro
repo root + python frontmatter-gate; per-article manifest; MSI tests in ora-project/tests. Structurally the
four-chunk Phase 8 build is done ora-side; the project is treated as structurally complete pending the
MSI-side wiring + documentation. Historical gate trail (most-recent-first) below. NOTE: deep historical
blocks (Phase 4 design gate, Phase 3 landed, older Chunk-D addendum blocks) still carry stale "resume here
first" tails from when each was the top — ignore those;
THIS pointer is authoritative.

## PHASE 8 — CHUNK D (ora-side generic seam) IMPLEMENTED, AT THE CODE-REVIEW GATE (2026-07-06, resume here first)
**Chunk D design addendum APPROVED-WITH-CONDITIONS (Rev 3; both P2/P3 conditions carried into impl). The
GENERIC ora-side seam is IMPLEMENTED — NO commit; awaiting the CODE-REVIEW gate.** Worktree
`/Users/oracle/ora-worktrees/phase8d-impl` (branch `execution-review-phase8d-impl` off origin/main
`94547937`). Durable: `phase8d-impl-packet.md` (Rev 0) + `phase8d-impl.diff` (3 files, +396/−5, ws-clean).
**Shipped (ora-generic, NO MSI knowledge):** NEW `orchestrator/execution_review.py` = `record_program_run`
(signals FOLDED from the run's own `<trace_dir>/tool-events.jsonl` via `record_route_observed`, never
caller-narrated §16-3; `standing:true` deploy_probe/render_inspect lanes built from `catalog.recipes` →
`evidence_contract['lanes']`→`route_lanes`→`fill_declared_lanes` [judge P3]; `enforcement_model`
caller-mandatory+validated+refuse-on-invalid, override via populate_loop_fields; caller free-text →
producer_claim.known_limitations; **`persist_packet` THEN `write_packet` so the trace-local packet is
always written** [judge P2]; never-raises; stealth no-op) + `tool_events.set_turn_context` now RETURNS a
reset token (additive) + new `reset_turn_context(token)` (the per-run-context restore primitive for judge
P2). NEW `test_execution_review.py` (10 tests incl. a REAL end-to-end standing-deploy_probe git_heartbeat
fill). **Adversarial pre-check (3 lenses × verify, all Opus): ZERO findings.** Parity: baseline 4,035/27 →
post **4,045 tests (+10), FAIL/ERROR BYTE-IDENTICAL, ZERO new**; record_program_run is a library entrypoint
(no ora turn calls it → live behavior unchanged). **ON CODE-REVIEW APPROVAL:** re-fetch→rebase→branch→
commit→push→PR→squash-merge→cleanup→ff ~/ora main; report PR#+SHA. **THEN the MSI-side (separate MSI-repo
landing, next phase):** instrument `_call_openrouter`; wire `invoke_real_gear4` (per-run context via the
token primitive; `record_program_run` AFTER final-output selection across all 4 consolidation modes [P1];
restore context in finally [P2]; `enforcement_model="boundary_only"`); publish boundary + `standing:true`
deploy_probe recipe; MSI `.ora/evidence.yaml` at the astro repo root + python frontmatter-gate; per-article
manifest; MSI tests in ora-project/tests (re-pull MSI first, stage own files). If the judge returns
findings: fold in phase8d-impl, re-check, re-run parity, re-deliver — NO commit until approval. Below: the
Chunk-D addendum gate trail (historical):

## PHASE 8 — CHUNK D ADDENDUM Rev 3 (judge design check-in gate trail; superseded by the IMPLEMENTED block above)
**Chunk D (MSI custom-path wiring, design §5) — design addendum APPROVED-WITH-CONDITIONS (Rev 3; the judge
BLOCKED Rev 2 on 3 implementation-precision findings, all folded).** Durable: `/Users/oracle/ora-worktrees/phase8-D-addendum.md` (**Rev 3**).
**⚖ Rev-3 judge folds (all real, all precision):** (P1, the load-bearing one) the recording point moved
from "right after `boot.run_gear4`" to the END, after the FINAL output is selected across ALL four
consolidation modes (`corpus`/`integrate_best`/`select_best`/`analyzer_section_best`) — the last three
make ADDITIONAL `_call_openrouter` model calls after run_gear4 and return a DIFFERENT final prose, so
recording early folds an incomplete log + attests the wrong (pre-consolidation) output ("observed not
narrated" violation); `Gear4Halt` → no packet. (P2) `record_program_run` calls `persist_packet` THEN
`write_packet` (persist_packet only decides durable tier + writes ledger/note when promoted; the
trace-local `execution-packet.json` needs write_packet — so a `git_only`/`instrumentation:none` run still
leaves the trace packet). (P3) the standing-lane filter builds from `catalog.recipes` (which carry
`.standing`), NOT `lanes_from_catalog` (which drops standing). Judge confirmed the `invoke_chat`-seam drop
sound. Test plan gained per-consolidation-mode recording tests. A fresh 7-lens read-only scout
ran against ora `@94547937` (Chunk C landed) + MSI `@6f4055b2` (churns). **Rev 0 was APPROVED-WITH-
CONDITIONS 2026-07-05 but predated A/B/C landing;** the fresh scout forced material corrections → Rev 1
(re-delivered) → adversarial pre-check (3 lenses × verify, all Opus, ZERO null votes) folded 3
addendum-prose fixes → **Rev 2**.
**Headline scope corrections vs Rev 0:** (1) the generic `invoke_chat` model-event seam is DROPPED —
`boot.call_model` already records `model_call` for every `invoke_chat` call; the genuine gap is MSI's
raw-urllib `_call_openrouter` (an MSI recipe). So the ONLY new generic seam is `record_program_run`.
(2) `record_program_run` contract = signals FOLDED from the run's OWN per-run sink via
`risk_gate.fold_route_observed(<sink>)` (whole-file mode; `record_route_observed` can't take an arbitrary
path — pinned seam), caller free-text→`producer_claim`, `enforcement_model` caller-mandatory (validated,
overridden via `populate_loop_fields`; MSI = `boundary_only`, honestly under-claiming vs the in-harness
`model_call` events it folds). (3) the astro validation build is NOT an `.ora` check (heavy/node-dep/
network-under-sandbox → stays MSI-internal in publish_cycle); the MSI catalog declares only a PYTHON
frontmatter-gate (node not guaranteed on systemd PATH) + a `standing:true` deploy_probe recipe. (4)
`.ora/` at the ASTRO REPO ROOT (not ora-project). **The three ⚖ Rev-3 D-scope items decided:** (i) MSI
loop reach = RECORD not the loop (scoped out LOUDLY — no live actuator; async zero-manual-labor;
record_program_run already delivers the observability); (ii) publish irreversible-gate = boundary-
observed + tier-stamped, NO per-article human gate + NO gating manifest entry (zero-manual-labor); (iii)
sink atomicity = per-run sinks (O_APPEND atomic only <PIPE_BUF 4096; lines exceed it, no lock → per-run
files never contend + give distinct conversation_id + the fold source). **Rev-2 pre-check folds:** the
lane-attach mechanism (must go through `context_pkg['evidence_contract']['lanes']`→`route_lanes` in
`build_execution_packet`, THEN `fill_declared_lanes`; `lanes_from_catalog` alone attaches nothing +
needs a `standing` filter Chunk D adds); `output_type` mislabel (locked {unknown,text,execution};
irreversibility rides risk_tier + event mutability); the gear-4 sink holds in-harness `model_call`
events (call_api_endpoint), NOT `_call_openrouter` (gear≤3). Scout worktree phase8d-scout removed.
**NEXT: relay Rev 2 to the judge (light re-check). On clearance: implement `record_program_run` +
`Recipe.standing` wiring in ora (fresh worktree off CURRENT origin/main, pre-check, parity zero-new,
code-review gate, land), THEN the MSI recipes + `.ora/` in the MSI repo (re-pull first, stage only own
files, own suite). If the judge returns findings: fold in the addendum, re-verify, re-deliver — NO code
until it clears.** This completes the four-chunk Phase 8 build surface. Below: the Chunk-C landing
block (historical):

## PHASE 8 — CHUNK C LANDED (2026-07-06)
**Chunk C (adapter families, design §4) is LANDED: squash-merged as `94547937` (PR #196) on
origin/main; `~/ora` main fast-forwarded `157cfe31 → 94547937`; branch `execution-review-phase8c-impl`
deleted (local+remote); worktrees phase8c-impl + phase8c-scout removed + pruned. Vault-side `.ora/`
files landed SEPARATELY in the vault repo (`2d5b0a66` on Golfplan18/obsidian-vault main:
`.ora/evidence.yaml` + `.ora/tools/{vault_frontmatter_lint,vault_wikilink_check,README}.py` +
`wikilink-allowlist.txt`, scripts byte-identical to ora canonicals). Smoke: evidence_runner.Recipe /
execution_families fillers / LANE_FILLERS / deploy_probe manifest / case-folded `.ora` protection all
import + resolve clean on the landed tree.** Gate trail: design addendum Rev 4 (approve-with-conditions;
C1 per-kind probe manifest + explicit sensitivity:public, C2 git_heartbeat no-fetch, C3 in-place
title-universe = current tracked+untracked — all folded) → adversarial pre-check (5 lenses × verify,
all Opus, zero null votes: 1 real MINOR folded [render_inspect unrun→owed] + 3 verifier-refuted) →
code-review gate BLOCK on 1 P1 [deploy_probe sliced probes BEFORE execution → false-green on a
beyond-cap failure] → folded (run+count ALL probes; cap bounds stored rows only) + regression →
re-delivered → **APPROVE**. Final parity 4,035 tests, FAIL/ERROR byte-identical to the fresh 157cfe31
baseline (22F+5E=27), ZERO new (+53 tests); live-fire: vault frontmatter check ran `orchestrated`
under the real macOS sandbox end-to-end. Landed-phase SHAs now P8-A `d7edb377`(#193) · P8-B
`157cfe31`(#195) · P8-C `94547937`(#196).
**What is now LIVE:** the declared-lane families substrate (deploy_probe/render_inspect fillers +
`.ora/tools` check scripts + `.ora/` write-protection) ships on the server's next restart; it stays
NIL on live turns until a project catalog declares recipes AND a run explicitly targets that repo —
live-chat-turn vault reach is a NAMED follow-up (no pre-exec multi-repo targeting seam; memory
`project_exec_review_repo_targeting`). ora's own catalog declares no recipes, so the live surface is nil.
**NEXT = CHUNK D** (MSI custom-path wiring, design §5; addendum-first; depends on A's map pattern + C's
deploy_probe family). Step 3 of the kickoff prompt: fresh READ-ONLY MSI scout (the repo churns via
concurrent sessions — re-scout at impl time, pull/re-read before editing, stage only own files) → SHORT
D addendum (exact seam list + MSI loop-reach decision + the §6/§8 publish-irreversible-gate posture +
concurrent-process sink atomicity) → judge light design check-in → implement (generic seams in ora:
`invoke_chat` boundary events + `record_program_run` [signals FOLDED from the run's own event log, never
caller-narrated — §16-2/3]; MSI recipes in `~/sites/mainstreetindependent/ora-project/`, NEVER
`~/ora/orchestrator/` [plugin convention]) → pre-check → parity → code-review → land. Durable Chunk-C
artifacts: `phase8c-impl-packet.md` (Rev 1) + `phase8c-impl.diff`; vault-side files at
`phase8c-vault-files/` (now landed). Below: the Chunk-C gate trail (historical):

## PHASE 8 — CHUNK C Rev 1 (code-review P1 folded), RE-DELIVERED TO THE GATE (2026-07-06, resume here first)
**Chunk C (adapter families, design §4) IS IMPLEMENTED — NO commit; code-review gate BLOCKED Rev 0 on
1 P1, folded + re-delivered.** Worktree `/Users/oracle/ora-worktrees/phase8c-impl` (branch
`execution-review-phase8c-impl` off origin/main `157cfe31`). Durable: `phase8c-impl-packet.md` (Rev 1)
+ `phase8c-impl.diff` (15 files, +2,449/−59, ws-clean).
**⚖ Rev 1 — judge P1 (reproduced + folded):** `fill_deploy_probe_lane` sliced `probes[:_LANE_PROBE_CAP]`
BEFORE execution → sufficiency computed only from the capped subset (25 probes, 25th failing → 24 run,
`sufficient=True` false green, violating §4.3 "all declared probes must PASS"). Fixed: run + count EVERY
declared probe; `_LANE_PROBE_CAP` bounds ONLY the stored/rendered lane rows (`rows[:cap]`), never
execution/sufficiency; `verdict_counts` over all. Regression `test_failing_probe_beyond_render_cap_not_sufficient`.
Hand adversarial re-check over the fold: sound (all-egress recorded; recipe-declared probes = no model
amplification; render/scrub shapes unchanged). Parity re-run: **4,035 tests, FAIL/ERROR BYTE-IDENTICAL
to baseline, ZERO new.** NO other change. Rev-0 detail below (still accurate): Vault-side `.ora/` files staged at `/Users/oracle/ora-worktrees/phase8c-vault-files/`
for a SEPARATE landing in the vault repo AFTER the ora PR merges. Design addendum APPROVED WITH
CONDITIONS (all 3 P2 folded as Rev 4): `phase8-C-addendum.md`. Scout worktree `phase8c-scout` (detached
@ 157cfe31, deletable).
**Shipped:** catalog `inputs`/`scope` + `recipes:` schema + inputs-dir mechanism (evidence_runner);
isolated+in-place inputs builders (`--diff-filter=d` deletion-exclude, in-place title-universe =
current tracked+untracked) + sparse opt-in + `LANE_FILLERS` registry + `fill_declared_lanes` on BOTH
engaged branches (execution_loop); NEW `execution_families.py` (deploy_probe filler — tri-state, per-kind
`deploy_probe:<kind>` events w/ explicit sensitivity:public, git_heartbeat local-ref-only NO fetch,
mandatory rollback; render_inspect filler — in-place OR SEC-2-worktree routed); 5 per-kind manifest
entries + case-folded `is_protected_config_path` + `/.ora/` segment rule (tool_events); git-write-into-.ora
→ irreversible escalation (bash_execute); web_fetch `raw`/`timeout_s` + `status_code`/`headers`
(httpx tier); route_lanes `declared=`+dedup + deploy_probe/render_inspect render branches (execution_packet);
`verdict` structural key (execution_persistence); 3 self-contained `.ora/tools/` scripts + README.
**Adversarial pre-check (5 lenses × per-finding verify, all Opus, ZERO null votes):** 1 REAL folded
(MINOR: render_inspect marked an UNRUN check FAILED instead of owed → `if not results: return None`;
regression test added) + 3 correctly REJECTED (discarded-return HOLD; unreachable malformed-lane; dead
protected_config key — each verifier-refuted). **Parity: fresh baseline 3,982/27 in-worktree; post
4,034 tests, sorted FAIL/ERROR BYTE-IDENTICAL to baseline, ZERO new.** Live-fire: vault frontmatter check
ran `orchestrated` under the REAL macOS sandbox reading ORA_CHECK_INPUTS, correctly FAILed a malformed note.
**ON CODE-REVIEW APPROVAL:** re-fetch → rebase → branch commit→push→PR→squash-merge→delete branch→prune
worktree→ff ~/ora main; report PR#+SHA; THEN land vault `.ora/` files (pull→copy→commit→push, own files);
THEN Chunk D. GOTCHA: Chunk C touches execution_loop.py — coordinate with any concurrent actuator-wiring.
**If the judge returns findings:** fold in phase8c-impl, adversarial re-check the fold, re-run parity
(zero-new), re-deliver — NO commit until approval. Prior gate trail (design check-in) below:

## PHASE 8 — CHUNK C DESIGN APPROVED (with conditions folded) (superseded by the IMPLEMENTED block above)
**Chunk C (adapter families, design §4) — design addendum APPROVED WITH CONDITIONS by the judge; all three
P2 conditions folded as Rev 4.**
Durable: `/Users/oracle/ora-worktrees/phase8-C-addendum.md` (**Rev 4**). Impl worktree
`/Users/oracle/ora-worktrees/phase8c-impl` (branch `execution-review-phase8c-impl` off origin/main
`157cfe31`). Read-only scout worktree `phase8c-scout` (detached @ 157cfe31, scout-only/deletable).
**Judge check-in verdict: APPROVE WITH CONDITIONS, no blockers.** Three P2 conditions, all folded (Rev 4):
(C1) `deploy_probe:<kind>` needs PER-KIND manifest entries (exact-match lookup won't resolve a single
`deploy_probe`) + explicit `sensitivity:public` on each event (`_redact_for_record` keys off the event
field, default secret) + per-kind survival tests; (C2) `git_heartbeat.fetch:true` is NOT read-only →
REMOVED from Chunk C (local-ref inspection only; live-fetch deferred to Chunk D w/ honest write axes);
(C3) in-place `title_universe` used the OLD tree (`git ls-tree <before_head>`) → false-dangles the turn's
new notes → now `git ls-files --cached --others --exclude-standard` (current tracked+untracked) + a
two-new-linked-notes regression.
**Rev 3 = adversarial pre-check fold.** A 4-lens critic × per-finding-verify workflow ran; the
code-fidelity lens + 2 verifiers DIED on a Fable-5 rate-limit mid-run → their findings + BOTH null
votes were RE-VERIFIED BY HAND against 157cfe31 (never trust a null vote). **10 distinct findings
folded (1 BLOCKER + 5 MAJOR + 4 MINOR); 1 correctly rejected.** Headliners:
- **BLOCKER — vault family UNREACHABLE on a live turn** (hand-confirmed): nothing sets
  `context_pkg['repo_root']`; `ORA_PROJECT_ROOT` is subprocess-only; both planning seams call
  `apply_evidence_contract` with no repo_root; server cwd = `~/ora` (has its own `.ora/evidence.yaml`)
  → `discover_repo_root`/`discover_catalog` ALWAYS land on ora. And live reach is architecturally hard
  (pre-exec base captured at planning against the cwd-default repo, before the touched repo is known).
  Fold (§3.0): vault family reachable via EXPLICIT repo_root (tests + programmatic/recipe runs +
  Chunk D's record_program_run); live-chat-turn reach = a NAMED follow-up (distinct pre-exec multi-repo
  targeting + base-capture seam), NOT a families-chunk rider. New memory `project_exec_review_repo_targeting`.
- **MAJOR** — `/.ora/` protection was case-bypassable on macOS (`normcase` no-op on darwin, APFS
  case-insensitive → `.ORA/` evades; existing `_PROTECTED_BASENAMES` shares the defect) AND blind to
  git-mediated writes (`git mv/checkout/restore` into `.ora/` surface no write path) → §6 rewritten
  (case-fold the protected-path key + escalate git write-subcommands touching `/.ora`; honest residual =
  §12 verify-stage closure disclosed).
- **MAJOR** — `changed_files` builder listed DELETED paths → scripts open-fail → false-FAIL →
  `ran_and_failed` → false human escalation on routine vault delete/rename turns → §2.2 pins
  `git diff --name-only --diff-filter=d` + a script-side skip-missing belt.
- **MAJOR** — declared lanes never filled on the source-read-only branch (returns before run_capture;
  fill_ctx.capture undefined) → §2.3 adds `fill_declared_lanes` on BOTH engaged branches (capture may be None).
- **MAJOR (null-vote, hand-confirmed)** — `inputs_dir` builder placement misassigned (`delta_commit`
  born inside run_isolated_checks, not the caller) + `title_universe` had no in-place derivation → §2.2
  pins the isolated builder in run_isolated_checks, the in-place builder (HEAD-based) in run_capture.
- MINORs: §1 wrong sandbox-read-surface claim (allow-default, not exact-worktree) corrected; sparse
  durably writes `extensions.worktreeConfig` into the vault `.git/config` (idempotent, disclosed §3.5);
  render_inspect on SEC-2 repos structurally refused → §5 routes it through the isolated worktree.
- REJECTED (fair): "how run_loop gets the catalog is unpinned" — re-parse-per-seam is the landed idiom,
  behaviorally inert under the no-recipe→owed rule.
**What the addendum pins:** §2 lane-declaration + filler-registry (both engaged branches) + check-INPUTS
mechanism w/ pinned builder placement; §3 vault family (deployment, deleted-path handling, catalog,
REACHABILITY, sparse residue); §4 deploy_probe + mandatory web_fetch extension + rollback; §5
render_validity + SEC-2 routing; §6 `.ora/` protection (case-fold + git-route); §7 judge-P3 paths +
Windows fixtures. §10 = 7 judge items headed by the reachability decision.
**NEXT: relay Rev 3 to the judge (light design check-in). On clearance: implement Chunk C per design §8
(fresh worktree off CURRENT origin/main — re-fetch first; A/B pattern), adversarial pre-check, parity
ZERO-NEW vs ~27 (22F/5E; ≈3,982 tests @ 157cfe31 — re-measure fresh), code-review gate, land per the
git workflow (ora repo THEN vault `.ora/` files). THEN Chunk D (fresh MSI scout + its own addendum).**
If the judge returns findings: fold in the addendum, re-verify, re-deliver — NO code until it clears.
Carried gotchas unchanged. Below: the Chunk-B landing block (historical):


## PHASE 8 — CHUNK B LANDED (2026-07-05, resume here first)
**Chunk B (isolated mutating-check actuator, design §3) is LANDED: squash-merged as `157cfe31`
(PR #195) on origin/main; `~/ora` main fast-forwarded `a511e7c4 → 157cfe31`; branch
`execution-review-phase8b-impl` deleted (local+remote); worktree phase8b-impl removed + pruned;
landed-tree smoke: `tree_commit_at`/`create_isolated_worktree`/`run_isolated_checks`/
`requires_isolated_worktree` all import.** Code-review gate: **APPROVE-WITH-CONDITION** (Rev 0 →
BLOCK on 2 real findings [P1 test portability: no-backend platforms would FAIL not skip; P2 honest
observability: isolated.ran=True even when the runner refused every check] → both folded, Rev 1 →
3-lens adversarial re-check folded 1 more REAL minor [the new no-backend gate short-circuited the
backend-independent crash-residue orphan-prune sweep → prune moved above the gate] → judge
approve-with-condition [one `/tmp` test literal] → folded before commit). Landed-phase SHAs now
P8-A `d7edb377`(#193) · P8-B `157cfe31`(#195). Final parity 3,982 tests, 27F/E identical to the
fresh `a511e7c4` baseline, ZERO new; 20 real-git+real-sandbox integration tests + 211 focused pass.
**What is now LIVE:** the loop is on (`ORA_EXECUTION_LOOP=1`), so on the server's NEXT RESTART, a
turn against a repo whose catalog declares a `mutates:true` check will run it in a disposable
worktree; ora's own catalog declares NO mutating checks so the live surface stays nil until a
project catalog adds one. Kill-switch `ORA_EXEC_REVIEW_MUTATING` (default ON with the loop).
**NEXT = CHUNK C** (adapter families, design §4; addendum-first; depends on B's worktree routing) →
then Chunk D (MSI wiring, §5). Full next-steps in the kickoff prompt (Step 2). Durable Chunk-B
artifacts: `phase8b-impl-packet.md` (Rev 1) + `phase8b-impl.diff`. Below: the pre-landing Rev-1
gate trail (historical):

## PHASE 8 — CHUNK B Rev 1 (code-review BLOCK folded + re-check), RE-DELIVERED TO THE GATE (superseded by the LANDED block above)
**⚖ Rev 1:** the judge BLOCKED Rev 0 with 2 findings, both real, both folded, then a 3-lens
adversarial re-check over the fold folded 1 more. **NO commit; re-delivered to the code-review
gate.** (P1 portability) the 3 "runs-isolated-and-passes" integration tests assumed an enforcing
`network:deny` backend and would FAIL not skip on no-backend Windows/CI → `@skipUnless` gate
(non-probing capability predicate) + a direct no-backend deferral test. (P2 honest observability)
`run_isolated_checks` stamped `isolated.ran=True` even when the runner refused every check unrun →
up-front `_batch_has_enforcing_backend` gate (defer WITHOUT a pointless worktree) + a belt
(`isolated.ran` True only when a check genuinely ran) + reworded caller reason. Re-check (opus
verifiers): **1 REAL minor folded** — the new gate short-circuited the backend-INDEPENDENT
crash-residue orphan-prune sweep on no-backend turns (narrowing the ref-less-snapshot-unpin
guarantee) → prune moved ABOVE the gate + regression test; 1 REJECTED (import-time probe — verifier
found only a mild off-mac single-probe, folded anyway as cheap hardening: non-probing test
predicate). Design-spec-fidelity lens: ZERO findings. **Rebased onto current origin/main `a511e7c4`
(legacy-path PR #194 landed, boot.py/web_search.py — zero overlap, clean rebase).** Parity FINAL at
the a511 base: **3,982 tests, sorted FAIL/ERROR IDENTICAL to the fresh a511 baseline (22F+5E=27),
ZERO new**; focused 211 pass. Durable: `phase8b-impl-packet.md` (Rev 1) + `phase8b-impl.diff`
(4 files, +1,089/−35). ON APPROVAL: re-fetch → rebase if needed → branch→commit→push→PR→
squash-merge→delete branch→prune worktree→ff ~/ora main; report PR#+SHA. THEN Chunks C+D behind
their addenda. GOTCHA: Chunk B + the actuator-wiring follow-up both edit execution_loop.py — never
run simultaneously. **FRESH-SESSION KICKOFF PROMPT (land Chunk B on approval → Chunks C + D, fully
self-contained): `/Users/oracle/ora-worktrees/phase8-CD-kickoff-prompt.md`.** Rev-0 implementation
detail below (still accurate):

## PHASE 8 — CHUNK B IMPLEMENTED, AT THE CODE-REVIEW GATE (Rev 0, superseded by the Rev-1 block above)
**Chunk B (isolated mutating-check actuator, design §3) IS IMPLEMENTED — NO commit; awaiting the
CODE-REVIEW gate.** Worktree `/Users/oracle/ora-worktrees/phase8b-impl` (branch
`execution-review-phase8b-impl` off origin/main `d7edb377` = the Chunk-A landing). Durable:
`phase8b-impl-packet.md` (Rev 0) + `phase8b-impl.diff` (4 files, +921/−35: evidence_runner.py
lifecycle primitives, execution_loop.py run_capture split + routing, execution_packet.py
whitelist, NEW test_isolated_actuator.py — 17 real-git+real-sandbox tests). Built: `tree_commit_at`
(ref-less delta commit via throwaway index — captures untracked files), `create_isolated_worktree`
(scratch, sparse, platform-split pre-flight), `remove_isolated_worktree` (containment-guarded),
`prune_orphan_worktrees` (owner-resolving cross-repo GC-unpin), `inplace_checks_refused`/
`requires_isolated_worktree` (SEC-2 routing: vault-class repos run ALL checks isolated),
`run_isolated_checks` (prune→temp-commit→worktree→run mode=clean_worktree→finally remove),
kill-switch `ORA_EXEC_REVIEW_MUTATING` (default ON w/ loop, OQ-7), caller-declared clean_worktree
(§3.4), narrowed PARTIAL note, isolated_checks/delta_attribution observability. Adversarial
pre-check (4 lenses×verify; **session limit killed 10 verify agents + 1 whole lens mid-run →
every null vote hand-re-verified + the regression lens hand-run**): **6 REAL folded incl. 1
BLOCKER** (Windows misroute: `\` is SBPL-unsafe by char set → every off-mac repo misrouted into
the worktree path then deferred → fixed via `inplace_checks_refused` keyed on
`_macos_sandbox_available` + platform-split worktree pre-flight) **and 1 MAJOR** (cross-repo
orphan sweep stranded the OWNER repo's `.git/worktrees` metadata → its detached HEAD PINNED the
ref-less snapshot against GC → fixed with gitdir-pointer owner resolution + per-owner prune,
empirically pinned) + 4 minors (mutates-flag honesty on deferred events, hardcoded interpreter in
tests, sparse `extensions.worktreeConfig` residue disclosed, bare-runner fallback); **4 REJECTED
with reasons**. Live-path probe: the sandboxed mutating check ran `orchestrated` + zero residue on
the REAL `~/ora/scratch` location. Parity FINAL: **3,968 tests, sorted FAIL/ERROR IDENTICAL to the
`d7edb377` baseline (22F+5E=27), ZERO new**; focused 208 pass. **CONCURRENCY: the legacy-path
cleanup task runs in parallel on this repo (boot.py/tools/web_search.py — ZERO overlap with this
diff); re-fetch + rebase at landing (its PR may land first).** ON CODE-REVIEW APPROVAL:
re-fetch → rebase → branch→commit→push→PR→squash-merge→delete branch→prune worktree→ff ~/ora main;
report PR#+SHA. THEN Chunks C+D (behind their short pre-implementation addenda). GOTCHA carried:
Chunk B and the actuator-wiring follow-up BOTH edit execution_loop.py — never run simultaneously.
Below: the Chunk-A landing block (historical):

## PHASE 8 — CHUNK A LANDED (2026-07-05)
**Chunk A (collect_provenance lane + claim-to-source map + web-read library guard) is LANDED:
squash-merged as `d7edb377` (PR #193) on origin/main; `~/ora` main fast-forwarded
`38a7eccd → d7edb377`; branch `execution-review-phase8a-impl` deleted (local+remote); worktree
phase8a-impl removed + pruned; landed-tree smoke: execution_provenance/execution_loop/tool_events
import clean.** Code-review gate: FULL APPROVAL, zero findings (judge verified against the
worktree: guard-in-modules, worker context propagation, Level-1-never-sufficient, handback
suppression, live-packet-untouched; base current; 386 focused tests green on their run;
`git diff --check` clean). Judge residual (non-blocking): legacy `~/ora` path assumptions in
older substrate (boot.py, tools/web_search.py) — tracked as a SEPARATE task, not Phase 8.
NOTE: the live server picks up Chunk A's observation seams on its NEXT RESTART (start.sh
process). Level 2 mapping stays dormant (`ORA_PROVENANCE_CLAIM_MAP` unset).
**NEXT = CHUNK B — the isolated mutating-check actuator** (design-approved at Rev 4, §3:
worktree lifecycle w/ ref-less delta_commit carrier, `requires_isolated_worktree` routing for
SEC-2 repos, mode="clean_worktree" runs, marker replacement, PARTIAL-note narrowing; ora-only).
Same working model: fresh worktree off CURRENT origin/main (re-fetch — now ≥ `d7edb377`),
adversarial pre-check, parity ZERO-NEW (baseline now 3,951 tests / 27F+E @ d7edb377),
code-review gate, land. GOTCHA: Chunk B and the actuator-wiring follow-up BOTH edit
execution_loop.py — never run simultaneously. C/D stay behind their short addenda.
Durable Chunk-A artifacts: `phase8a-impl-packet.md` (Rev 0) + `phase8a-impl.diff`. Below:
the pre-landing gate trail (historical):

## PHASE 8 — DESIGN APPROVED (Rev 4) · CHUNK A IMPLEMENTED, AT THE CODE-REVIEW GATE (superseded by the LANDED block above)
**Rev 4 design APPROVED by the judge** ("Rev 4 clears the A/B design delta. Implementation can
proceed, with the code-review gate expected to verify the ContextVar propagation, stealth
suppression, byte-budget event splitting, and absence of fallback call-site recording.").
**Chunk A (collect_provenance + claim-to-source map + library guard) IS IMPLEMENTED — NO commit;
awaiting the CODE-REVIEW gate.** Worktree `/Users/oracle/ora-worktrees/phase8a-impl` (branch
`execution-review-phase8a-impl` off origin/main `38a7eccd`). Durable: `phase8a-impl-packet.md`
(Rev 0) + `phase8a-impl.diff` (15 files, +2,152/−57; NEW `orchestrator/execution_provenance.py`
+ NEW `test_execution_provenance.py` [40 tests incl. both judge-P1 conditions + the bare-submit
negative control]). Adversarial pre-check (4 lenses × verify, 26 agents): 17 REAL → 12 distinct
defects ALL folded w/ regression tests (headliners: relationship-lane parser was a no-op;
dispatcher web events bypassed sanitize_url; Level-2 accepted citations of unseen sources →
false-sufficient reachable; durable scrub blanked every web URL ref) + 1 self-caught deviation
(OQ-3 was missing the `not any_mutation` guard) + 3 correctly REJECTED. Judge's four named
verification points are all test-covered. Parity FINAL: 3,951 tests, sorted FAIL/ERROR lists
IDENTICAL to the pre-edit baseline (22F+5E=27), ZERO new; focused 204 pass. ON CODE-REVIEW
APPROVAL: re-fetch, rebase, branch→commit→push→PR→squash-merge→delete branch→prune worktree→
ff ~/ora main; report PR# + bare SHA. THEN Chunk B (isolated actuator — approved, ora-only);
C/D stay behind their addenda. NOTE: actuator-wiring follow-up and Chunk B both edit
execution_loop.py — never run their impl stages simultaneously. Design-gate trail below:

## PHASE 8 DESIGN GATE — Rev 2 PASSED · Rev 3 delta-check BLOCKED (1 P1 + 2 P2) · Rev 4 folded + re-delivered (superseded: Rev 4 APPROVED — see block above)
**Rev 4 (latest):** the judge's delta-check on Rev 3 blocked with 3 findings, all reproduced
against code and folded. (P1, stealth-severity — corrected a WRONG Rev-3 claim): claim-verify
ThreadPoolExecutor workers have an EMPTY `_TURN_CTX` ContextVar and `get_turn_context`'s env
fallback is IMPORT-TIME module state (None in-server) — guard events from workers would misfile
to the global sink with conversation_id None + stealth False (stealth turns' web reads WRITTEN).
Fold: adopt `web_consultation._ctx_submit` copy_context idiom (web_consultation.py:785-794) at
every executor boundary reaching the guard + 2 required tests (worker event → TURN trace sink
w/ conversation_id; stealth worker records NOTHING). (P2a): §2.3 stale Rev-1 call-site language
removed — ONE contract: guard inside tools/web_search.py + tools/web_fetch.py, no call-site
helpers, residual boundary = non-library reads (MSI raw urllib → Chunk D). (P2b): reads[]
batching now BYTE-budgeted (~6KB soft budget, per-`what` 512-char cap + hash tail, batch_part
splits; long-URL tests: every line < MAX_LINE_BYTES=8000, zero descriptors lost) — the ≤24
count cap did not guarantee the byte-length truncation rule. Prior trail below:
**Design packet: `/Users/oracle/ora-worktrees/phase8-design.md` (Rev 3). NO code written.**
Trail: Rev 0 (Execution Thread: 8-agent substrate scout + packet; scout worktree `phase8-scout`
detached @ `35ca7369`, scout-only/deletable) → the 5-lens × per-finding-verify critic fleet
launched but hit the session usage limit mid-verify → a DIFFERENT account/session did a
smaller hand-critique in lieu (Rev 1: 3 precision folds; confirmed base advance `35ca7369` →
`38a7eccd` [PR #192 = ORA_EXECUTION_LOOP activation via start.sh — **the loop + Phase-7
persistence are LIVE now**] touches only start.sh, all anchors hold) → judge **Rev 2
APPROVE-WITH-CONDITIONS: Chunks A+B approved for implementation; C+D behind short addenda**;
OQ decisions recorded in the packet header (headline: OQ-5 = context-aware LIBRARY GUARD in
web_fetch/web_search, not call-site; OQ-3 ledger_line only for explicitly-unsupported claims;
OQ-6 content-only hash; judge P3 → Chunk-C addendum: no user-path literals).
**THEN the presumed-lost critic fleet COMPLETED post-gate: 36 findings; after hand-verifying
every rate-limit-killed null vote (never trust a null vote) → 33 REAL / 3 rejected, 4 BLOCKERS
— ALL folded as Rev 3** (⚖-marked in place): (1) Level-1 sufficiency false-True + mapped≠supported
→ per-row `support_status` + `claims_total: null` at Level 1 (never sufficient without Level-2
judgment); (2) escalation handback rendered the LIVE packet → durable-summary render suppresses
lane content, fail-closed; (3) vault family structurally unrunnable (SEC-2 refuses in-place,
actuator routed only mutating checks) → `requires_isolated_worktree` routes ALL SEC-2-repo
checks through the Chunk-B worktree; (4) `record_program_run` accepted caller-narrated
signals/lane-fills (§16-2/3 violation) → signals folded from the run's own event log, lanes
only via registered fillers, caller text = unverified producer_claim. Majors: rename to
`execution_provenance.py` (orchestrator/provenance.py EXISTS — live RAG weights module),
registry `injected` flag (all_chunks ⊃ prompt-injected via max_chars truncation), URL
sanitization (sig=/X-Amz-Signature=/X-Goog-Signature=/key= missing from scrub patterns) + 8KB
reads[] event batching, ref-less temp commit definitive (crash-pinned-ref residue), self-contained
`.ora/tools/` check scripts + out-of-sandbox title-universe input (ora code + main .git are
read-DENIED inside the SBPL sandbox), deploy_probe mandatory `rollback` field (§4), MSI astro
flagship check unrunnable as declared (gitignored node_modules + /tmp outDir), MSI loop-reach +
publish-irreversible-gate posture made explicit D-addendum scope, mixed-turn INFORMATIONAL
provenance render (keeps OQ-4's stop-rule deferral true through the verify prompt).
**NEXT: relay the Rev-4 header block + the ⚖ Rev-4 §2.3/§9 sections to the judge (re-check of
the blocked delta-check). On clearance: implement Chunk A (fresh worktree off CURRENT
origin/main ≥ `38a7eccd`, re-fetch first), adversarial pre-check, parity ZERO-NEW vs 27
(22F/5E; 3910 tests @ 35ca7369 baseline), code-review gate, land per git workflow.** Carried
gotchas unchanged (`reversible:true` @high-risk spec-correct; a redactor's except-fallback
fails CLOSED; §12-vs-§13 escalation split; contextvars do NOT cross executor.submit — always
copy_context). Below: Phase-7 landing.

## PHASE 7 LANDED — 2026-07-05
**Phases 1–7 are LANDED on `ora-commons/ora` main.** Phase 7 (tiered persistence, spec §14)
squash-merged as **`35ca7369` (PR #191)**; `~/ora` main fast-forwarded `b4b257dd → 35ca7369`;
branch `execution-review-phase7-impl` deleted (local+remote); both worktrees (phase7-impl +
phase7-scout) removed + pruned. Landed-phase SHAs: P1 `20438071` (#174) · P2 `2ead4450` (#176) ·
P3 `0dda6ac6` (#178) · P4 `1ab1438a` (#179) · P5 `ffea2b4e` (#185) · P6 `8ae29eb3` (#188) ·
P7 `35ca7369` (#191). Durable artifacts persist: `phase7-design.md` (Rev 3),
`phase7-impl-packet.md` (⚖ Rev 1), `phase7-impl.diff`.

**Gate trail:** design Rev 0 → completeness-critic (9 REAL folds pre-delivery: sensitive-freetext
blocker, conversation_id-empty-in-prod blocker, +7) → judge BLOCK (non-git store not actually
git-ignored) → Rev 2 → APPROVE-WITH-CONDITIONS (effective-ignore test + rebase) → Rev 3. Impl →
adversarial pre-check caught + folded a planning-block redaction leak (all 4 lenses converged) →
judge BLOCK (P1 fail-OPEN redaction: except returned the original packet → written durably;
P3 fixture paths) → Rev 1 fold (fail-CLOSED: redactor→None, persist withholds every durable write;
+ self-found second fail-open in `_scrub_free_text`; 3 regression tests; re-check of the fold: ZERO
findings) → APPROVE-WITH-CONDITIONS (landing hygiene + env-hermetic test — both done). Final
parity 3910 tests, 27F/E identical to baseline, ZERO new (+41 tests).

**⚡ ACTIVATED 2026-07-05 — the loop + persistence are LIVE (`38a7eccd`, PR #192).**
`ORA_EXECUTION_LOOP=1` exported in start.sh (the ORA_DELIVERABLE_SCRUB launcher-flag pattern);
server restarted with the flag verified in its process env. Validation before the flip: full-suite
A/B flag-ON vs flag-OFF in the identical environment — 3910 tests, failure lists byte-identical
(flag provably inert); live smoke — a real gear-4 turn (root-cause mode, web consult + claim verify
+ quality gate) reached the terminal, wrote the packet with `tier: git_only`, zero durable residue,
zero exceptions. **The revision actuator remains unwired (`actuator=None`): a failed verify
escalates to the Paused queue rather than self-revising — the one remaining follow-up.**

**🔎 LIVE-VALIDATION FINDING → PHASE 8 (§16-3 dispatcher-blindness class):** the gear-4
web-consultation path (step-2 consult + step-4.5 claim verify) performs web reads OUTSIDE the
instrumented tool layer — the smoke turn's tool-events.jsonl held 27 events, ALL model_call/telemetry,
ZERO read events despite web consultation demonstrably running (trace files present). So
`source_read_suspected` can NEVER fire from the pipeline's own web-consult channel; only
instrumented channels (rag_read when RAG retrieves content, dispatcher web/file tools) trigger it.
Phase 8's collect_provenance workstream must instrument or capture this channel — it is where the
source CONTENT + URLs for snapshots/excerpts live anyway (already in the Phase-8 scout list).

**What is now LIVE vs remaining:**
- Every packet carries a §14 tier (`git_only` default at build); durable writes fire on loop turns.
  The store `data/execution-records/` (ledger + per-conversation notes) is git-ignored (verified
  live), stealth-purged by closeout Layer 10 → `execution_persistence.purge_conversation`,
  retention-exempt-by-omission.
- Redaction is FAIL-CLOSED end to end; the tier truth table + three-layer scrub are fully
  unit-covered (39 tests) incl. Windows-shaped fixtures + the `git check-ignore` behavior guard.
- **NEXT (unscheduled, user's call):** (a) the Phase-6/7 follow-ups — validate live, then flip
  `ORA_EXECUTION_LOOP` to default-ON (activates the loop AND Phase-7 durable persistence in one
  flag) + wire the live gear-reinvocation actuator (OQ1); (b) Phase 8 — `collect_provenance`
  claim-to-source map, the isolated mutating actuator (`git worktree add` → apply delta → run →
  remove), MSI custom-path loop wiring, generalize adapters. Carried gotchas: `reversible:true`
  at high-risk is spec-correct; the §12-vs-§13 escalation split is subtle; a redactor's
  except-fallback must fail CLOSED (the P7 lesson).
- **Small P7 leftover (design OQ6, deliberately deferred):** the escalation handback's
  `packet_ref` still points at the TRACE-LOCAL packet JSON (retention-swept after 30d), not the
  Phase-7 durable note an escalated turn now always earns. A one-line rewire candidate for
  Phase 8 or the follow-ups.
- **The Phase 8 kickoff prompt for a fresh session is saved at
  `/Users/oracle/ora-worktrees/phase8-kickoff-prompt.md`.**
Below is the Phase-6 landing block (historical):

## PHASE 6 LANDED / PHASE 7 NEXT — 2026-07-04 (superseded by the PHASE 7 LANDED block above)
**Phases 1–6 are LANDED on `ora-commons/ora` main.** Phase 6 (Wire the loop + governance +
stop rule, spec §15) squash-merged as **`8ae29eb3` (PR #188)**; `~/ora` main fast-forwarded
`ffea2b4e → 8ae29eb3`; branch `execution-review-phase6-impl` deleted (local+remote); both
worktrees (phase6-impl + phase6-scout) removed + pruned. Landed-phase SHAs: P1 `20438071`
(#174) · P2 `2ead4450` (#176) · P3 `0dda6ac6` (#178) · P4 `1ab1438a` (#179) · P5 `ffea2b4e`
(#185) · P6 `8ae29eb3` (#188). Durable Phase-6 artifacts persist: `phase6-design.md`,
`phase6-impl-packet.md` (Revisions 1+2 documented), `phase6-impl.diff`.

**Phase-6 code-review gate trail (all judge findings real, reproduced, folded):** Rev 0 →
judge BLOCK (3 P1 loop-correctness) → Rev 1 → judge BLOCK (1 follow-on §13 P1: base-unknown
null-branch) → Rev 2 (+2 self-adversarial-re-check folds) → judge APPROVE-WITH-2-CONDITIONS
(P3 stale base-unknown wording cleanup + rebase — both done). Final parity 3869 tests, 27F/E
identical to baseline, ZERO new; 186 focused tests.

**What is now LIVE vs deferred (READ THIS before Phase 7):**
- The loop is **wired but flag-gated OFF** behind `ORA_EXECUTION_LOOP` (default OFF → the
  terminal + planning seam are byte-identical to Phase 4, so parity holds). `actuator=None`
  for the first landing (no live gear re-invocation) per OQ1 + the validate-then-default-ON
  rollout. **Phase-6 follow-ups (NOT Phase 7): validate + flip the flag to default-ON; wire a
  live gear-reinvocation actuator.**
- The ExecutionPacket **stays `trace_local`** (Phase 6 never promotes to durable). `loop.status
  = "escalated"` is recorded but not promoted. **This is exactly what Phase 7 builds.**
- Deferred to Phase 8 (do NOT do in Phase 7): `collect_provenance` claim-to-source map;
  the isolated mutating actuator (`git worktree add` → apply delta → run → remove); MSI's own
  loop wiring; generalizing adapters.

**NEXT = PHASE 7 — Tiered persistence (spec §14 + §15 Phase 7).** Start with a DESIGN packet +
STOP for the judge's DESIGN gate (mirror every prior phase: scout read-only → design →
completeness-critic → judge design gate → on approval implement in a fresh worktree off CURRENT
origin/main → adversarial pre-check → parity zero-new → code-review gate → land). Scope: implement
`git_only` / `ledger_line` / `durable_note` with the promotion rule (promote only when the packet is
genuinely informative — it **escalated**, **failed to converge**, or carries a **plan-level finding**
worth remembering; routine clean passes stay in git history) + **sensitivity-driven redaction before
any durable write** (§7 axis: nothing `secret` ever present, anything `sensitive` scrubbed) + route
retention through the existing memory-pruning discipline rather than duplicating it. The Phase-6
`persistence` packet block (`tier` / `redacted`, `execution_packet.py`) is RESERVED for exactly this.
The kickoff prompt for a fresh Phase-7 session is at `/Users/oracle/ora-worktrees/phase7-kickoff-prompt.md`.
Below is the Phase-6 pre-landing history (design gate → code-review revisions):

## PHASE 6 DESIGN GATE — PASSED 2026-07-04 (APPROVE-WITH-CONDITIONS, both folded; NEXT = IMPLEMENTATION) (superseded by the LANDED block above)
**Phase 6 (Wire the loop + governance + stop rule, spec §15) DESIGN GATE is CLEARED.** Trail: Rev 0
delivered → judge BLOCKED (3 findings) → all folded (Rev 1) → re-delivered → judge
**APPROVE-WITH-CONDITIONS (2 conditions)** → both folded (Rev 2) → design is judge-approved for
implementation. NO code written yet. Durable design: `/Users/oracle/ora-worktrees/phase6-design.md`
(862 lines; ⚖ Revision-2 + Revision-1 blocks document all folds).
**JUDGE'S 2 REV-1 APPROVAL CONDITIONS, both folded (⚖ Rev-2):** (P1) removed the `clean_worktree`
contradiction — Phase 6 **never** passes `mode="clean_worktree"` against the user's live checkout;
a `mutates:true` required check is a Phase-8-deferred capability (needs the isolated actuator:
`git worktree add` at base → apply `delta_ref` → run → remove), recorded as DEFERRED (loud marker +
observed event) and NOT escalate-forcing; Phase 6's live evidence is the NON-mutating catalog checks
(build/lint/typecheck/read-only test). The P4 escalate-precision now separates a RAN-and-FAILED
check (escalate) from an environment/scope REFUSAL/deferral (record + degrade). (P2) the
pre-execution snapshot is TIER-INDEPENDENT — decoupled from the `standard+` `apply_evidence_contract`
seam; captured whenever a repo is discoverable before any mutation-capable actuator, at EVERY tier
(`light` included — spec §192/§8: light gets basic evidence = repo catalog checks; at light Capture
runs the catalog directly, no bespoke Contract).
**NEXT = IMPLEMENTATION (the code-review gate follows).** Implement in a FRESH worktree off CURRENT
origin/main (RE-FETCH first — origin/main advances via concurrent sessions), adversarial pre-check
over the changed logic, parity (diff sorted FAIL/ERROR name lists, ZERO new vs 22F/5E = 27
environmental baseline), then deliver the impl packet to the CODE-REVIEW gate (NO commit until the
judge approves the code). The build: a new loop controller (terminal-anchored + planning-stage
pre-execution snapshot seam) + `populate_loop_fields` + the different-family verify selector (leverage
`training_family` + `router._generate_warnings`) + the plan/exec revision router + stop rule +
escalation-branch primitive (`evidence_runner._git` from the stashed pre-exec base) + the Capture
driver (snapshot_before at planning → run_contract non-mutating → fill_evidence_lanes →
contract_sufficient) + tests (`test_execution_loop.py`) — anchored at `boot.py:9429` / `server.py:2979`.
Rev-0 detail below (core call + scout findings unchanged):
**JUDGE'S 3 REV-0 FINDINGS, all folded (⚖ Rev-1):** (P0) a terminal-only design can't capture a
true `state_before` or a correct escalation-branch base — a `snapshot_before` READ at the terminal
is POST-execution (`_git_state` reads current HEAD, `evidence_runner.py:938`; gear @ `boot.py:9389`
runs before the terminal @ `9429`) → FOLDED: **Architecture A gains a PLANNING-STAGE pre-execution
state seam** — capture `snapshot_before` right after `apply_evidence_contract`, stash
`context_pkg["exec_review_state_before"]`, derive `state_before` + the escalation-branch base from
that stashed ref; a *committing* executor requires `clean_worktree` isolation for the unmerged
guarantee (Phase 6 never resets the user's branch to fake one). (P1) the stop rule wrongly narrowed
spec §364 "no high-severity finding remains" to `execution_level` only → FOLDED: **no high-severity
finding of ANY class** may remain; plan-level high-severity routes to planners until resolved or
cap-escalated. (P1) source-read churn — `source_read_suspected` engaged the loop but its
`collect_provenance` lane is Phase-8-owed → never sufficient → escalate every source-read turn →
FOLDED: the loop **escalates only on FAILED/REFUSED declared evidence or a persistent high-severity
finding; an owed/empty lane** (`collect_provenance` Phase-8, or a `repo_less` no-catalog contract)
**records a LOUD deferred marker + degrades to the text review, never escalating** (resolves OQ6);
the full converge/escalate loop is driven by adapted lanes only (`diff_validate` now).
Rev-0 detail below (still valid — the core call + scout findings are unchanged): Scouted read-only in the pinned worktree
`/Users/oracle/ora-worktrees/phase6-scout` (detached @ `ffea2b4e` = current origin/main
= the Phase-5 landing / PR #185; origin/main has NOT advanced past Phase 5 — Phase 6
branches off `ffea2b4e`).
**CORE DESIGN CALL: Architecture A — a terminal-anchored loop CONTROLLER that engages
ONLY on non-self-evidencing turns.** The loop (plan → execute → Capture → dual-family
verify → revision router → stop/escalate) is assembled from parts already present (§4
"same downstream machinery, NOT a second pipeline"): planning = the already-live
`apply_criteria`+`apply_evidence_contract`; execute+revise actuator = existing
`run_gear3`/`run_gear4`; Capture tool = Phase-5 `evidence_runner`; review surface =
Phase-4 `render_for_review`. Anchored at the terminal (`boot.py:9429` / `server.py:2979`,
continuing Phase 4's terminal choice + lowest-regression through MSI-inherited
`invoke_real_gear4`); gated on the already-folded `_ro['signals']`
(`any_mutation` or `source_read_suspected`), so the common self-evidencing turn is
byte-identical (zero regression) and the loop fires only on reality-contact turns.
**Standout scout findings (all @ffea2b4e, hand-verified):** (1) `render_for_review`
(`execution_packet.py:236`) + the runner driver surface (`snapshot_before`/`run_contract`/
`snapshot_after`/`fill_evidence_lanes`/`contract_sufficient`) are genuinely WIRE-not-build;
`contract_sufficient`+`all_evidence_sufficient` correctly treat refused/absent/empty as NOT
sufficient. (2) **The §12 model-family substrate ALREADY exists** — every endpoint carries
`training_family`, and `router._generate_warnings` (`router.py:1228`) already DETECTS
same-family (advisory-only); Phase 6 adds a SELECTOR + single-family DETECTOR, not new
metadata. (3) The packet is built at the TERMINAL after the gear's own prose verify;
`build_execution_packet` leaves `planning=None`/`loop=None`/`execution.mode/state_*=None`/
`enforcement_model="in_harness"` (literal "TODO owned by the P6 enumeration") + reserved-empty
`verification.reviewer_a/b/findings/invented_tests/confidence` → Phase 6 FILLS exactly these
via a new `populate_loop_fields`. (4) **CORRECTION (hand-found):** all gear steps route through
`_run_model_with_tools` (`_call_with_supplement`→`_call_with_retry`, `boot.py:10830`/`10900`)
and `any_mutation` folds gear-independently (`risk_gate.py:602`) — so the gate keys on the
OBSERVED signal, NOT a "gears 3-4 write prose" presumption. (5) §15 Phase-0 audit: the loop
reaches the core pipeline + MSI's `invoke_real_gear4` (by-construction once the terminal
controller lands); MSI's custom Gear-3 (`gear3_orchestrator`) never flows through the terminal
→ stays Phase 8.
**Adversarial completeness-critic (5 diverse lenses × per-finding verify; 42 raw findings).**
The verify stage was largely rate-limited (the known hazard) so I re-verified every finding by
hand. ~28 were the SAME "loop/selector/router/test-file doesn't exist yet" observation —
correctly REJECTED (design-gate scope, not defects; they confirm the build map). **8 real
design-level folds applied:** the gear-independent mutation correction + explicit gate
mechanism (P0); escalation handback is a REFERENCE not inlined `producer_claim` into the
durable Paused queue (P4, grounded in `PausedEntry.context_summary` + stealth-skip);
Contract-AWARE mode selection (a `mutates:true` required check forces `clean_worktree` else
honest escalation, P1); escalation-branch-vs-secrets note (P4); explicit self-evidencing gate
signal (P0); the gear-3 `failed-then-redone-unreviewed` status handling (P7); packet-write
last-writer-wins concurrency note (§3); MSI inheritance framing (§1.7). 10 open questions for
the judge, headed by **OQ1 — the terminal-wrapper (A, recommended) vs in-gear-Capture (B)
architecture fork** (mirrors Phase 4's "how live should P4 go?").
**GOTCHA carried (do NOT "fix"):** the packet's `reversible` flag is the §6 post-hoc-routing
gate; high-risk IS `reversible:true` — spec-correct.
**ON JUDGE APPROVAL:** implement in a FRESH worktree off *current* origin/main (RE-FETCH —
origin/main advances via concurrent sessions), adversarial pre-check over the changed logic,
parity (diff sorted FAIL/ERROR name lists, ZERO new vs the 22F/5E = 27 environmental baseline),
land per git workflow (branch → commit → push → PR → squash-merge → delete branch + prune
worktree → ff ~/ora main; report PR# + bare SHA). The `phase6-scout` worktree is scout-only +
detached @ `ffea2b4e`, safe to delete + recreate at implementation time.
Below is the Phase-5 LANDED block:

## PHASE 5 LANDED 2026-07-04 (superseded as resume pointer by the Phase-6 block above)
**Phase 5 (Code adapter + `.ora/evidence.yaml` catalog + ENFORCE-OR-REFUSE evidence
runner + planning-stage Evidence Contract + dirty-state modes, spec §15) is LANDED:
squash-merged as `ffea2b4e` (PR #185) on origin/main; ~/ora main fast-forwarded to
`ffea2b4e`; both phase5 worktrees (phase5-impl + phase5-scout) removed, local+remote
branch deleted, pruned.** The code-review gate approved after Rev 0 (5 findings) →
Rev 1 (all 5 folded) → approve-with-3-conditions → Rev 2 (all 3 folded) →
approve-with-1-condition (base `cmd` type-check) → folded → full approval. An
adversarial pre-check + fold-recheck along the way found + I fixed **2
EMPIRICALLY-REPRODUCED sandbox exploits** (SBPL profile injection→network escape;
worktree-ancestor→vault re-expose, both verified blocked live vs real sandbox-exec)
+ ~10 more real defects. Rebased cleanly onto current origin/main (the Phase-1-4
portability retrofit PR#181 + docs PRs #182-184 had landed). Final parity 3800 tests,
27F/E identical to baseline, ZERO new; +62 evidence_runner tests.
**Landed substrate Phase 5 shipped:** new `orchestrator/evidence_runner.py`
(catalog parse/validate extending the Phase-1 vocabulary + requiring `redact`;
ENFORCE-OR-REFUSE `run_check` — a check runs ONLY under a backend that VERIFIABLY
enforces its declared network policy [macOS sandbox-exec / native Linux `unshare -rn`
= `orchestrated`; a declared `ORA_EVIDENCE_SANDBOX` wrapper = `declared-sandbox`,
operator-attested, a reject-only egress probe refuses a demonstrated passthrough]
else REFUSES cleanly, never runs unenforced; every outcome records an
`evidence_check` tool-event; direct `tool_events.gate`; own credential-stripping
platform-aware clean env; SBPL-unsafe/ancestor-worktree refusal; git dirty-state
snapshots; `fill_evidence_lanes`); `.ora/evidence.yaml` (Ora's own catalog,
shell-free `argv`, both `network:deny`); `apply_evidence_contract` wired LIVE +
UNCONDITIONAL at both planning seams (boot.py + server.py, standard+, additive);
`tool_events.ENFORCEMENT` += `declared-sandbox`.
**NEXT = Phase 6 (spec §15): Wire the loop + governance + stop rule** — dual plan →
converged brief + contract → single executor → mechanical CAPTURE (drive the
Phase-5 runner) → dual VERIFY (different model family + single-family fallback,
findings tagged plan_level/execution_level, invented tests tagged) → revision router
→ termination + escalation with the linked UNMERGED branch. Phase 6 makes LIVE the
two pieces built-but-unwired: the Phase-4 renderer (`render_for_review`, never wired
into a live review) + the Phase-5 runner (drives no check until Phase 6). Same
working model: design gate → code-review gate → land; FRESH worktree off CURRENT
origin/main (it advances frequently via concurrent sessions — FETCH first).
**The Phase-6 kickoff prompt is at `/Users/oracle/ora-worktrees/phase6-kickoff-prompt.md`.**
GOTCHA carried: a declared-wrapper check is honestly `declared-sandbox` NEVER
`orchestrated` (black box unverifiable); the packet's `reversible` flag is the §6
post-hoc-routing gate (high-risk IS reversible:true — spec-correct, don't "fix").
Below is the Phase-5 design + impl detail:

## PHASE 5 DESIGN APPROVED + IMPLEMENTED 2026-07-04 (superseded by the LANDED block above)
**DESIGN GATE APPROVED-WITH-CONDITIONS** (Rev 2 enforce-or-refuse). Judge resolved
OQ13: ship `ORA_EVIDENCE_SANDBOX` as the first-class Windows enforcement route +
native Linux `unshare -rn` only if capability-probed and safely degrades to refuse;
no check may run under an unenforced `network:deny`. Two P2 conditions folded into
the design (stale consequence-6 "outside private roots" sentence + Rev-1 fold-log
marked historical). **IMPLEMENTED** in fresh worktree
`/Users/oracle/ora-worktrees/phase5-impl` (branch `execution-review-phase5-impl`
off origin/main `82553162`; baseline clean 22F/5E = 27, 3721 tests). Durable diff:
`/Users/oracle/ora-worktrees/phase5-impl.diff`.
**Shipped:** new `orchestrator/evidence_runner.py` (catalog parse/validate extending
the Phase-1 vocabulary + requiring `redact`; ENFORCE-OR-REFUSE runner; generalized
macOS sandbox profile with the repo-read re-allow; own credential-stripping
platform-aware clean env; direct-gate integration; planning-stage Contract producer
repo-less-capable; git dirty-state snapshots; additive lane-fill); `.ora/evidence.yaml`
(Ora's own catalog, shell-free `argv`, both `network:deny`); the planning-seam wiring
(boot.py + server.py, FLAG-GATED `ORA_EVIDENCE_CONTRACT` OFF = byte-identical live,
validate-then-default-on); `test_evidence_runner.py` (58 tests incl. mac-gated real
network-deny + Windows sims).
**Adversarial pre-check (2 lenses) + fold-recheck FOUND 2 EMPIRICALLY-REPRODUCED
security exploits + 7 more real defects — ALL FOLDED + re-verified live:** (SEC-1)
SBPL profile INJECTION via unescaped worktree path → network escape + false
`orchestrated` → `sandbox_worktree_unsafe()` refuses SBPL-unsafe paths; (SEC-2)
worktree ancestor-of-vault RE-EXPOSED the vault → refuse ancestor worktrees +
`_macos_profile` re-denies nested private roots (both verified BLOCKED live vs real
sandbox-exec); (SEC-3) mutates:true escaped under default mode=None → refuse unless
mode=='clean_worktree' exactly; (SEC-4, reworked twice) a declared wrapper recorded
false `orchestrated`, and my FIRST probe was itself unsound (offline false-positive
+ argv-shape divergence, both reproduced) → FINAL: a wrapper is honestly
`enforcement_model: declared-sandbox` (operator-ATTESTED, NEVER `orchestrated`) +
a REJECT-ONLY attributive probe refuses only a DEMONSTRATED online passthrough
(baseline-OPEN+wrapped-OPEN); both re-check findings verified closed; (SEC-5)
env:inherit leaked SSH_AUTH_SOCK → dropped, always credential-stripped; (PORT-1)
shell:true always refused on POSIX → /bin/sh on POSIX; (PORT-2) unshare cache not
platform-keyed → platform-gated first. **KEY honest-labeling insight: a black-box
declared wrapper can't be verified for all argvs, so it's NEVER `orchestrated` —
only `declared-sandbox` (§7/§17 no-overclaim).** FINAL PARITY: +52 net new tests
(3773 total), 27 FAIL/ERROR identical to baseline, ZERO new. Diff 5 files +1551
ws-clean. Impl packet `/Users/oracle/ora-worktrees/phase5-impl-packet.md`.
**CODE-REVIEW GATE blocked Rev 0 with 5 real findings (judge-verified, incl. an
empty tool-event sink) → ALL FOLDED (Rev 1) + a focused re-check found 2 more
(both folded):** (P1-1) Contract was flag-gated OFF → removed the gate, runs
UNCONDITIONALLY in the live planning path (standard+) at both seams, additive
never-raises (parity clean with it ON); (P1-2) checks left NO tool-event (gate()
records only on block, refusals returned directly) → `run_check` wraps
`_run_check_impl` + `_record_check_event` = exactly ONE `evidence_check` event per
outcome (verified: previously-empty sink now records it; no double-record — the
gate only records on block and the runner only gates a non-None backend that always
allows); (P1-3) gate axes hardcoded `orchestrated` → per-backend
`_ENFORCEMENT_MODEL` + added `declared-sandbox` to `tool_events.ENFORCEMENT`;
(P2-1) ORA_EVIDENCE_SANDBOX `raw.split()` broke on Program-Files spaces → shlex
+ (re-check catch: posix=False RETAINS quotes) a balanced-quote strip on the nt
branch, verified under simulated os.name=nt; (P2-2) per-platform variants not
matched-pair-validated → require matched windows+posix pair + type-check argv(list)
/cmd(str). FINAL PARITY (Rev 1) +58, zero new. **THEN the code-review gate returned
APPROVE-WITH-3-CONDITIONS on Rev 1 (I had re-delivered Rev 1 unchanged, not seeing
the 3 conditions) → Rev 2 RESOLVED all 3:** (P2) run_contract's missing-catalog
check bypassed tool-event recording → now calls `_record_check_event` (verified: an
`evidence_check:ghost` event lands in the sink); (P2) packet stale "flag-gated OFF"
/"52 tests" text → all corrected (wiring is UNCONDITIONAL now, counts updated);
(P3) validate_check accepted malformed execution-form combos → now rejects mixing
argv/cmd families, a `cmd` without `shell:true`, and `shell:true` without a cmd
form (shipped catalog still validates). FINAL PARITY +61 net new (3782 total),
27F/E=baseline, ZERO new; diff 6 files +1755/-1 ws-clean. Impl packet updated
(§3.6). **NEXT: DELIVERED the conditions-resolved packet + diff; awaiting the
judge's confirmation of full approval, THEN land per git workflow (branch→PR→
squash-merge→delete branch+prune worktree→ff ~/ora main; report PR# + SHA). NO
commit until confirmed.** Below is the Rev-2 design detail:

## PHASE 5 DESIGN GATE — REVISION 2 (enforce-or-refuse) 2026-07-04 (design detail, now approved)
**Rev 1 (portability) was BLOCKED again:** it tried to RUN `network:deny` checks
off-mac under `boundary_only` while honestly labeling them unenforced — the judge
ruled (correctly) that honest labeling does not make an unenforced constraint
true; §7 (spec:186) + §15 (spec:394) require checks to run UNDER their declared
constraints. **Rev 2 = ENFORCE-OR-REFUSE:** a check runs ONLY under a backend that
actually enforces its declared network policy — macOS `sandbox-exec`, a **declared
`ORA_EVIDENCE_SANDBOX` wrapper (now a FIRST-CLASS supported Windows path** — WSL /
container / Windows Sandbox), or native Linux `unshare -rn` — recording
`enforcement_model: orchestrated`; where no enforcing backend exists the check
**REFUSES cleanly** (`skipped`+`skip_reason`), NEVER run unenforced. The
`boundary_only`-runs-off-mac path is RETIRED. "Runs on Windows" now = the runner
machinery (parse/validate/discover/Contract/git-state, pure Python) runs
everywhere + check execution runs under a declared `ORA_EVIDENCE_SANDBOX` (like
`shell:true` needs `ORA_POSIX_SHELL`); without it, network-constrained checks
refuse (the judge-accepted "revisit what runs on Windows for the shipped catalog").
Also fixed the two stale `enforcement_model: orchestrated` overclaims (§1.7 :290 /
CheckResult :677 — now correct because unenforceable checks refuse) + the OQ11
scratch-location slip (`SCRATCH_DIR` is inside `~/ora`/`$HOME`; the per-run re-allow
is what works). OQ13 reframed to "how much enforcing backend to ship" (universal
`ORA_EVIDENCE_SANDBOX` + optional native Linux `unshare -rn`). Design is 1293 lines;
⚖ Revision-2 block documents the folds. **NOTE:** the judge's last relayed message
was a `try-again` RE-SEND of the Rev-1 verdict (busy service) — its line numbers
(544/1033/281/659/1015) point to superseded Rev-1 content; Rev 2 already resolves
all three. NEXT: judge re-review of Rev 2. Below is the Rev-1 detail:

## PHASE 5 DESIGN GATE — REVISION 1 (portability) 2026-07-04 (superseded by Rev 2 above)
**SPEC AMENDED — Cross-Platform Portability is now RELEASE-BLOCKING for Phase 5.**
The judge blocked the Phase-5 design Rev 0 on a new spec amendment ("Amendment —
Cross-Platform Portability Is Release-Blocking", spec §~9-23): all Phase 5 work
must run on macOS AND Windows (no hardcoded mac/user paths → runtime_paths/pathlib
/tempfile; no POSIX-shell-on-Windows → ORA_POSIX_SHELL, refuse-not-cmd.exe; guard
POSIX-only APIs; catalog commands not Mac-only → platform-neutral subprocess or
declared per-platform variants; every path root from runtime plumbing; Windows-sim
tests, not skip-green; **every review packet needs a "Portability" section**). The
amended spec is synced to BOTH `~/Downloads/ora-execution-review-spec.md` AND the
durable copy `/Users/oracle/ora-worktrees/ora-execution-review-spec.md` (432 lines).
**Rev 1 folded all 5 judge findings** (⚖ Revision-1 block in the design): platform
`_sandbox_backend` (macOS sandbox-exec=`orchestrated`; Windows/Linux
prevention-by-absence=`boundary_only`, honest — the runner RUNS off-mac now, no
longer fail-closes); shell-free `argv` catalog (subprocess shell=False) + `cmd`
+`shell:true` via ORA_POSIX_SHELL + `argv_windows`/`argv_posix` variants; the
Evidence Contract COMMITTED to run LIVE at planning (spec §15 requires it; repo-root
via env+pathlib, repo-less-Contract fallback); Windows-behaviour simulation tests
(ntpath/PureWindowsPath, mirroring Phase-1 test_portability.py); the required §7
Portability section. Also folded a clean-env-Windows-vars gap (`_clean_env` sets
POSIX HOME/TMPDIR, omits USERPROFILE/TEMP/SystemRoot/COMSPEC/PATHEXT → platform-aware
clean env). Leans on Phase-1's shipped portability substrate
(`_posix_shell_path`/ORA_POSIX_SHELL, `runtime_paths`, `test_portability.py`, the
`boundary_only` enforcement label) — NOTE the off-mac `boundary_only` EXECUTION
path is genuinely NEW build work (Phase 1's `_sandbox_backend` fails closed
off-mac; the runner diverges to RUN, honestly weaker). A focused portability
adversarial pass (2 lenses; 7 folded / 7 correctly rejected) then sharpened the
off-mac honesty — folded: the runner must build its OWN credential-stripping clean
env (NOT `bash_execute._clean_env`, which leaks `SSH_AUTH_SOCK`); `SCRATCH_DIR` is
INSIDE `~/ora`/`$HOME` (not "outside private roots" — the per-run re-allow is what
works); off-mac `network:deny` is NOT enforced + writes NOT contained (recorded
honestly, not overclaimed); catalog `argv` operand slash-paths rely on the invoked
tool's slash-tolerance. The rejected 7 CONFIRMED the load-bearing claims exact
(gate-direct, `sys.executable`, `git worktree add` on empty mkdtemp dir, reqs
6/7). NEXT: re-deliver Rev 1 → judge design-gate re-review. Below is the (still-valid) Rev-0 scout + design
detail:

**Phase 5 (Code adapter + `.ora/evidence.yaml` catalog + evidence runner +
planning-stage Evidence Contract + dirty-state modes, spec §15) DESIGN PACKET is
written, adversarially reviewed, portability-revised, and DELIVERED to the judge;
NO code written.** Durable design:
`/Users/oracle/ora-worktrees/phase5-design.md` (~1050 lines). Scouted read-only in
the pinned worktree `/Users/oracle/ora-worktrees/phase5-scout` (detached @
`82553162`, current origin/main).
**Core design call: Architecture A — trustworthy runner LIBRARY + shipped `~/ora`
catalog; live check-execution deferred to the Phase-6 loop (NO auto-run at the
gear terminal).** One consolidated new module `orchestrator/evidence_runner.py`
(catalog parse+validate + runner + sandbox-run + Contract producer + dirty-state /
state-snapshot helpers). Fills the Phase-4-reserved
`EvidenceLane.generated_by/result/sufficient` + `execution.mode/state_before/
state_after` for the **diff+validate lane ONLY** (§15 "one adapter, trustworthy
first"); collect_provenance stays declared (Phase 8).
**Standout scout findings (all @82553162):** Phase 1 already PRE-SEEDED the runner
vocabulary — `tool_events.EVIDENCE_RUNNER_DEFAULTS` (:983) + `validate_check_declaration`
(:994) + `evidence.yaml` in `_PROTECTED_BASENAMES` (:267, so the catalog is
WRITE-GATED — an executor can't silently weaken a check); the shell profiler
`bash_execute` FAILS `python3 -m unittest`/`npm test`/`node` CLOSED (:456-488) with
the literal comment "*until the Phase-5 evidence runner can run them under real
constraints*" (Phase 5 IS the pre-designated sanctioned path); the Evidence
Contract mirrors `risk_gate.apply_criteria` (:935, wired boot.py:9304 /
server.py:2846) at the same planning step; `code_execute`'s sandbox-exec profile is
the reuse primitive; NO git-worktree/diff/clean-tree primitive exists (Phase 5
builds it, mirroring `engram_promotion._git`). The terminal packet build is at
boot.py:9432 / server.py:2969 (`construct_and_write`, writes trace-local).
**Adversarial completeness-critic (4 lenses × verify; 45 raw → 26 folded / 19
correctly rejected).** Many verify agents hit server-side rate-limiting, so the two
BLOCKER/MAJOR survivors were re-verified against the code by hand. KEY FOLDS: (1)
[BLOCKER] the sandbox reuse is NOT a write-root swap — `code_execute._sandbox_profile`
denies ALL reads under `$HOME`/`~/ora`/vault/conversations, so a check can't read
its own repo; the runner's profile must re-allow reads of the specific
repo_root/worktree (prefer a fresh worktree OUTSIDE private-deny roots),
`cwd=worktree` (OQ11). (2) [MAJOR] the runner must call `tool_events.gate(...,
interactive_approver=None)` DIRECTLY, not `dispatcher.dispatch()` — dispatch's
default `approve-each` (dispatcher.py:364) installs an `input()` prompt that a
programmatic runner would hang on. (3) [MAJOR] the "wire the live Contract at
planning" lever is blocked by no repo_root in scope at the planning seam → keep it
library-only. (4) [MAJOR] "green ≠ honest test": the write-protected catalog fixes
the check's cmd STRING, not the model-editable code the cmd invokes —
grading-your-own-homework is closed by acceptance criteria + verify authoring
(Phase 6), not the runner alone. Plus network:local dropped to refused-in-P5
(sandbox has no localhost scoping), mutates:false→reversible_write, on_unknown +
network refusals are RUNNER logic not gate behaviour, ~/ora catalog is
parse+validate-only (its `discover` would recurse), and a batch of citation fixes.
12 open questions for the judge (headed by library-vs-live-run, the sandbox
read-side approach OQ11, gate-direct-vs-dispatch).
**GOTCHA carried forward (do NOT "fix"):** the packet's `reversible` frontmatter
flag is the §6 post-hoc-routing gate (irreversible-tier vs not), so high-risk is
intentionally `reversible: true` — spec-correct.
**ON JUDGE APPROVAL:** implement in a FRESH worktree off *current* origin/main
(re-fetch — origin/main was `82553162` at design time), adversarial pre-check over
the changed logic, parity (diff sorted FAIL/ERROR name lists, zero new vs the 22F/5E
environmental baseline), land per git workflow (branch → commit → push → PR →
squash-merge → delete branch + prune worktree → ff ~/ora main). The `phase5-scout`
worktree is scout-only + detached, safe to delete + recreate at implementation time.

## PHASE 4 LANDED 2026-07-04 (superseded as resume pointer by the Phase-5 block above)
**Phase 4 (Evaluation-lane router + polymorphic ExecutionPacket + packet-to-review
renderer, spec §15) is LANDED: squash-merged as `1ab1438a` (PR #179) on
origin/main; ~/ora main fast-forwarded to `1ab1438a`; both phase4 worktrees
(phase4-impl + phase4-scout) removed, local + remote branch deleted, pruned.** The
code-review gate approved after Revision 1 (2 folds: gear-3 stale-verdict clear +
observable packet-construction failures). Final: +58 tests, full parity 3721
tests, 22F/5E identical to baseline, ZERO new. Durable artifacts persist in the
parent dir (survived worktree removal): `/Users/oracle/ora-worktrees/
phase4-design.md`, `phase4-impl-packet.md`, `phase4-impl.diff`.
**Landed substrate Phase 4 shipped:** new `orchestrator/execution_packet.py`
(ExecutionPacket + EvidenceLane/JudgmentLane + render_for_review +
_format_artifact_for_review + route_lanes + consistency_note + build/write/
construct_and_write); `risk_gate.record_route_observed(declared_output_type=)`
records output_type + consistency (no packet ref on route_observed);
tool_events keep-set has output_type/consistency; run_gear3/4 thread the verdict
label onto `context_pkg['execution_review']`; the two gear terminals
(boot.py run_pipeline, server.py _run_pipeline_from_step2) build the packet
trace-local guarded to a real deliverable + non-stealth.
**NEXT = Phase 5 (spec §15):** Code adapter + `.ora/evidence.yaml` catalog (with
runner constraints) + the evidence runner that executes it mechanically + the
planning-stage Evidence Contract + the three dirty-state modes (clean_worktree /
review_dirty_diff / continue_user_changes). Phase 5 FILLS the declared-empty
evidence lanes (generated_by/result/sufficient) + the §11 execution.mode/
state_before/state_after fields Phase 4 reserved. Same working model: design gate
→ code-review gate → land; fresh worktree off current origin/main. NOTE: the
`reversible` frontmatter flag is the §6 post-hoc-routing gate (irreversible-tier
vs not) — do not "fix" high-risk to non-reversible (spec-correct as shipped).
**CURRENT origin/main TIP = `82553162`** (PR #180, a tiny post-Phase-4 chore that
gitignored the per-machine runtime data artifacts — data/tool-events.jsonl,
data/execution-approvals.json[.lock], data/active-project.json,
data/custom-styles.json, data/archive/; no code change). Phase 5 branches off
`82553162`, not `1ab1438a`. The Phase-5 kickoff prompt is saved beside this file
at `/Users/oracle/ora-worktrees/phase5-kickoff-prompt.md`.

## PHASE 4 IMPLEMENTED — code-review gate, REVISION 1 2026-07-04 (superseded by the LANDED block above)
**Design approved-with-4-conditions → IMPLEMENTED → judge blocked Rev 0 with 2
narrow findings → both FOLDED + regression-tested (Rev 1) → clean full parity → NO
commit (awaiting the judge's re-review).**
REVISION 1 folds (judge's 2 findings): (F1) gear-3 quality-gate FAIL fires a redo
(boot.py ~11571-11593) producing a NEW unreviewed deliverable, but
execution_review still held the pre-redo FAIL → fixed: inside the redo block,
overwrite with {verdict:None, scope:'text_review', status:'failed-then-redone-
unreviewed'}; packet verification carries `status`; renderer shows a TEXT-REVIEW
STATUS fence when there's no verdict. Gear-4 verified free of the bug (range(3)
loop, 2 redo types, every ship path re-gates). (F2) build/write packet failures
were a silent None → fixed: new `_mark_failure(err, where)` stamps
tool_events._note_failure on any caught BUILD/WRITE exception
(execution_packet_construct / _write / _construct_and_write), while intentional
skips (no trace_dir / empty output / signals None) stamp NOTHING — the judge's
required distinction; each of the 3 disjoint paths stamps exactly once. Rev-1
adversarial pre-check: 1 nit (one-stamp invariant under-asserted + 2 untested
paths) → folded (assertEqual(before+1) + write-path + wrapper-path tests). Rev-1
tests: +58 net new (test_execution_packet 55 + test_quality_gate
TestGear3VerdictThreadForPacket 3); full parity **3721 tests, 22F/5E identical to
baseline, ZERO new**. Diff 7 files, +1037/-9, ws-clean. Below is the Rev-0 detail:

**Design approved-with-4-conditions → IMPLEMENTED → adversarial pre-check folded →
clean full parity → NO commit (awaiting the judge's code-review verdict).**
Worktree `/Users/oracle/ora-worktrees/phase4-impl` (branch
`execution-review-phase4-impl` off origin/main `0dda6ac6`; baseline a clean
22F/5E). Durable packet `/Users/oracle/ora-worktrees/phase4-impl-packet.md`; diff
`/Users/oracle/ora-worktrees/phase4-impl.diff` (6 files, +885/-9, ws-clean).
Core: **Architecture A — terminal packet + library renderer, seam install
deferred.** New consolidated `orchestrator/execution_packet.py` (ExecutionPacket
+ EvidenceLane/JudgmentLane + renderer + lane router + consistency note +
builder/writer). Packet built at the single run_pipeline / pipeline-stream terminal
(boot.py ~9416, server.py ~2957) reached by EVERY non-hold gear, guarded to a real
deliverable + trace dir + non-stealth. Text default byte-identical; the six in-gear
review sites are NOT edited.
ALL 4 judge conditions met: (1) ORDERING — record_route_observed folds ONCE +
records route_observed first; packet built SEPARATELY from the returned signals;
NO packet ref on route_observed. (2) STORAGE — packet is trace-local only
(persistence.tier=trace_local), inherits stealth/no-packet, never vault/durable
(Phase 7 owns that). (3) OUTPUT_TYPE — terminal passes declared_output_type
(default 'unknown'); raw hint recorded verbatim, NEVER rewritten from observation;
consistency note is record-only + dormant on live turns. (4) VERDICT THREAD —
run_gear3/4 stash the verdict LABEL ONLY onto context_pkg['execution_review']
(namespaced, no raw verifier text, scope-labeled text-review-only, not read by any
prompt assembly). All 8 open-question answers honored.
Adversarial pre-check (3 lenses × verify; 4 raw findings): folded P4-1 (docstring
"two gear terminals" → accurate "single terminal reached by every non-hold gear" +
non-gate paths carry honest null verdict) + P4-2 (added a defensive `if signals is
None: return None` guard, though unreachable today) + F2 (added a §6 clarifying
comment — `reversible = risk_tier != "irreversible"` is spec-correct: `reversible`
gates post-hoc routing and high-risk IS reversible; the verifier's proposed fix
would be WRONG). F1 (verdict=None on non-gate paths) re-verified as honest, not a
defect (documented). Tests +49 (test_execution_packet.py); full parity **3712
tests, 22F/5E identical to baseline, ZERO new failures**.
ON JUDGE APPROVAL: land per git workflow — branch already off CURRENT origin/main
(re-check origin/main hasn't advanced; rebase if it has), commit → push → PR →
squash-merge → delete branch + prune the phase4-impl worktree (+ the deletable
phase4-scout worktree) → fast-forward ~/ora main. If the judge blocks: fold in the
same worktree, re-run adversarial pre-check + parity, resubmit.
 Durable per-phase artifacts live in this same
directory (`/Users/oracle/ora-worktrees/`): `ora-execution-review-spec.md` (the
spec), `phase2-design.md`, `phase3-design.md`, `phase3-impl-packet.md`,
`phase3-impl.diff`, and now `phase4-design.md` (the Phase-4 design packet awaiting
the judge). Read-only scout worktree at `/Users/oracle/ora-worktrees/phase4-scout`
(detached @ `0dda6ac6`, deletable). The Phase-1-era `phase1-*.diff` /
`baseline-failures.txt` files beside them are historical.

## PHASE 4 DESIGN GATE — DELIVERED 2026-07-04 (resume here first)
**Phase 4 (Evaluation-lane router + polymorphic ExecutionPacket + packet-to-review
renderer, spec §15) DESIGN PACKET is written, adversarially reviewed, and DELIVERED
to the judge; NO code written; awaiting the design-gate verdict.** Durable design:
`/Users/oracle/ora-worktrees/phase4-design.md`. Scouted read-only in the pinned
worktree `/Users/oracle/ora-worktrees/phase4-scout` (detached @ `0dda6ac6`, current
origin/main / the Phase-3 landing).
Core design call: **Architecture A — terminal packet + library renderer, seam
install deferred.** Build `ExecutionPacket` + renderer + lane router as one
consolidated module (`orchestrator/execution_packet.py`); construct the packet live
at the TWO gear terminals only (`boot.py:9416`, `server.py:2957`), guarded to real
deliverables; the six in-gear review sites are NOT edited in P4 (that install is
Phase-6 scaffolding). "Same downstream machinery, richer output — NOT a second
pipeline"; text default byte-identical.
Substrate facts (all @0dda6ac6): gears return a bare `str` (`deliverable`/
`formatted`); the artifact enters review as the USER prompt at 6 hand-built
f-string sites (no single choke point); both §6 signals now ride `route_observed`
(`any_mutation` + `source_read_suspected`) and `record_route_observed`'s return is
DISCARDED at all 11 call sites (a lane router can consume it with no re-fold);
`output_type` does not exist yet (only a comment at `risk_gate.py:1002`); the
single verdict parser is `_verifier_passed` (`boot.py:9939`). §15 Phase-0 audit
confirmed the MSI custom paths (`gear3_orchestrator`/`backfill_orchestrator`/
`article_generator`/`msi_run_gear4`) build their own prompts via a separate
`prompt_fences.py` and won't inherit — `invoke_real_gear4` is the one partial path
(delegates steps 3–8 to `boot.run_gear4`). MSI adapter work stays deferred to
Phase 8.
Ran an adversarial completeness-critic (4 lenses × verify; 22 raw → 21 CONFIRMED /
1 correctly REJECTED) and folded all real findings — notably TWO architecture
blockers verified by hand against the code: (1) the in-gear verdict is
function-local and unreachable at the terminal → thread it via `context_pkg`,
scope-labeled text-review-only; (2) the packet is only buildable at the two gear
terminals and must be guarded off hold/early-return/direct-stream/framework paths
(building on a hold would misrender a refusal as a producer claim). Also folded:
drop the six-site seam install (dead-in-P4 code at live-site risk; prove acceptance
by a rendered-string test); the renderer + consistency assertion are honestly
tested-but-unwired in P4 (no live verifier sees a packet; no mode declares
output_type); every §9 block (loop/confidence/reviewer-family/mode/state_before-
after/generated_by) reserved-but-unfilled so later phases fill not retrofit; a
construction-failure marker (never-raises must stay observable). 8 open questions
for the judge (headed by "how live should P4 go?" and OQ8 verification-block
sourcing). ON JUDGE APPROVAL: implement in a FRESH worktree off *current*
origin/main, adversarial pre-check over the changed logic, parity (diff sorted
FAIL/ERROR name lists, zero new vs the 22F/5E environmental baseline), land per git
workflow. The `phase4-scout` worktree is scout-only + detached — safe to delete +
recreate at implementation time.

## PHASE 3 LANDED 2026-07-04 (resume here first)
**Phase 3 (Universal capture, spec §15) is LANDED: squash-merged as `0dda6ac6`
(PR #178) on origin/main; ~/ora main fast-forwarded; both phase3 worktrees
removed, local + remote branches deleted, pruned.** The code-review gate
approved-with-one-narrow-condition — MCP reads had been classified `ambiguous`
(so they hit the 24-char substantive floor and a terse MCP-grounded answer like
"Yes." didn't suspect); fixed to `always`/strong per the §6 over-route asymmetry
(+2 tests). Final: +29 tests, full parity 3663 tests zero-new-failures. Durable
artifacts persist in the parent dir (survived worktree removal):
`/Users/oracle/ora-worktrees/phase3-design.md`, `phase3-impl-packet.md`,
`phase3-impl.diff`.
**NEXT = Phase 4 (spec §15):** evaluation-lane router (`evidence_lanes` vs
`judgment_lanes` structurally separate) + `ExecutionPacket` alongside
`TextArtifact` via the packet-to-review renderer (evidence first, producer claim
last, labeled unverified) + the `output_type`-vs-observed consistency assertion
Phase 3 deferred (its inputs — `source_read_suspected` + `any_mutation` — are
now recorded on every `route_observed`). Same working model: design gate →
code-review gate → land; fresh worktree off CURRENT origin/main each phase.

## PHASE 3 IMPLEMENTED — code-review gate 2026-07-03 (superseded by the LANDED block above)
**Design approved-with-2-conditions → IMPLEMENTED → adversarial pre-check folded
→ clean full parity → NO commit (awaiting the judge's code-review verdict).**
Worktree `/Users/oracle/ora-worktrees/phase3-impl` (branch
`execution-review-phase3-impl` off origin/main `aec67200` — PR#177 landed the
Barb capabilities.json sync, so the old test_capability_registry drift is gone;
baseline is a clean 22F/5E). Durable packet
`/Users/oracle/ora-worktrees/phase3-impl-packet.md`; diff
`/Users/oracle/ora-worktrees/phase3-impl.diff` (7 files, +529/-19, ws-clean).
BOTH judge conditions met: (1) explicit source-action allowlist + actually-ran
filter (exit.ok + gate allowed/approved) + telemetry/blocked exclusion in
`risk_gate._source_read_kind`; (2) no private→public leak — `record_route_observed`
stamps sensitivity=folded max CAPPED at 'sensitive' (never secret) +
`_public_safe_candidates` keeps `what` only from public reads + verdict promoted
top-level and into the tool_events truncation keep-set. All 6 open-Q answers
honored (Q4 = boot.py framework return-in-finally refactored to capture the
output var). Adversarial pre-check: 6 findings, all confirmed → folded 4 real
(MCP read channel under-route; secret-stamp contract; short-output strong-channel
asymmetry; truncation of the routing verdict) + accepted 1 (web_search query
nit). +27 tests; full parity 3661 tests, ZERO new failures. ON JUDGE APPROVAL:
land per git workflow — branch off CURRENT origin/main, commit → push → PR →
squash-merge → delete branch + prune both phase3 worktrees (scout
`/Users/oracle/ora-worktrees/phase3` + impl). If the judge blocks: fold in the
same worktree, re-run adversarial pre-check + parity, resubmit.

## PHASE 3 DESIGN GATE — DELIVERED 2026-07-03 (superseded by the block above)
**Phase 3 (Universal capture, spec §15) DESIGN PACKET is written and DELIVERED
to the judge; NO code written; awaiting the design-gate verdict.** Durable
design: `/Users/oracle/ora-worktrees/phase3-design.md`. Scouted read-only in
the pinned worktree `/Users/oracle/ora-worktrees/phase3` (branch
`execution-review-phase3` off origin/main `2ead4450`; ~/ora's main checkout was
on a concurrent chip's branch `fix/barb-cartoon-capability-sync` — the exact
mid-session switch hazard, so a pinned worktree was used).
Core delta: Phase 2's `route_observed` already ships signal 1 (what-changed) and
a raw `reads_present` boolean; Phase 3 turns `reads_present` into §6 SIGNAL 2 —
the source-read over-approximation ("did the output make claims about material
it read?", excluding local_context_read) — recorded as additive
`source_read_suspected`/`source_read_channels`/`source_candidate_reads`, with the
precise per-claim source_read labeling + claim-to-source map (§4) handed off as a
seam to Phase 8 (NOT built now). Substrate facts verified: `fold_route_observed`
(risk_gate.py:429-484) + `record_route_observed` (820-849) take NO output → add
optional `output_text` kwarg; output is in scope at all 13 terminal record sites
EXCEPT boot.py:9194 (framework return-in-finally; server twin server.py:3277 has
result_text); no runtime consumer of the signals dict outside risk_gate+tests
(additive keys safe); stealth suppresses the whole record. Ran an adversarial
completeness-critic (4 lenses × verify; 21 raw → 19 confirmed / 2 correctly
rejected) and folded all real findings — notably a BLOCKER that the draft
write-dominated local-read tie-break was unsound (fold-wide `max_mutability`
clears genuine source reads via unrelated or even blocked writes) → flipped to
"over-approximate all ambiguous local reads." 6 open questions await the judge
(local-read tie-break A/B; invisible search/list/shell reads; RAG breadth across
gears; the one framework return-in-finally path; stealth non-observation;
provisional constants + concurrent-sibling window). ON JUDGE APPROVAL: implement
in a FRESH worktree off *current* origin/main, adversarial pre-check over the
changed fold, parity (diff sorted FAIL/ERROR name lists, zero new), land per git
workflow. The `execution-review-phase3` worktree/branch is scout-only and
uncommitted — safe to delete + recreate at implementation time.

## PHASE 1+2 LANDING HISTORY (superseded — the live resume pointer is the PHASE 3 LANDED block at the top)
**PHASE 1 LANDED (commit 20438071, PR #174) AND PHASE 2 LANDED (commit
2ead4450, PR #176) — both on ora-commons/ora main. Phase 2 branch
execution-review-phase2 deleted (remote+local); the /Users/oracle/ora-
worktrees/phase2 worktree removed + pruned; ~/ora main fast-forwarded to
2ead4450 (risk_gate.py present).** Phase 2 was approved after 4 judge
revisions + a rebase-onto-current-main landing condition; rebased cleanly
onto 6a666a79 (the MSI "Barb cartoon image slot" commit), focused
framework/risk suites 186/186 post-rebase, zero Phase-2 conflict.
(Historical NEXT, now DONE: Phase 3 — Universal capture — started with a design
packet, cleared the design + code-review gates, and LANDED as `0dda6ac6` /
PR #178; see the top block. Phase 2 shipped `route_observed`; Phase 3
formalized the source-read over-approximation + universal capture per §7/§15.)
KNOWN main-branch drift (NOT ours, flag to MSI): commit 6a666a79 added
`image_generates_barb_cartoon` to config/routing-config.json but NOT
config/capabilities.json → test_capability_registry sync check fails on main
until the capabilities.json side is added (Barb voice work — a spawned chip
task_9482d7fb is fixing it in a separate session; once it lands, the two
test_capability_registry failures clear from the baseline).

### KEY FACTS FOR A FRESH SESSION (Phase 3)
- Spec (durable copy): /Users/oracle/ora-worktrees/ora-execution-review-spec.md
  (Phase 3 = §15 "Universal capture" + §7 read-taxonomy over-approximation;
  the source-read signal, deferred-labelling, provenance seam to §4).
- Working model: THIS thread implements; a SEPARATE judge thread reviews at
  gates; the user relays packets both ways. NO commit until the judge
  approves. Phase 3 opens with a DESIGN gate (design packet first, no code).
- Never work in ~/ora's main checkout (concurrent MSI/chip sessions switch
  branches there). Use a fresh git worktree off current origin/main. Python
  = /opt/homebrew/bin/python3. Run suites with
  ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off; parity = diff sorted FAIL/ERROR
  name lists branch-vs-base (base = the worktree's fork point), zero NEW.
- Proven loop each revision: fix → small adversarial Workflow over ONLY the
  changed logic → verify findings against code yourself (the majority vote
  under-reports; several real defects were "rejected" then confirmed) → fold
  → re-run focused + full parity → resubmit with diff + parity evidence.
- Landed substrate Phase 3 builds on: tool_events.py (event recorder + gate +
  turn ctx incl. risk_tier + global_sink_path), risk_gate.py (route_observed
  fold already reads the tool-event log for what-changed/reads-present),
  dispatcher.py (per-call axis resolution incl. reads[] with content hashes),
  the §4 provenance/claim-to-source-map is the downstream consumer.
--- (Phase 2 build history, for the record) ---
Phase 2 = new module orchestrator/risk_gate.py (classifier + inline/sticky
/risk + task fingerprint + tokens + task-gate marker + irreversible hold +
route_observed
+ criteria pass); wired into boot.run_pipeline, server _pipeline_stream/
_run_pipeline_from_step2/_direct_stream, tool_events ctx field,
resolution_chain + slash_commands task_gate kind dispatch,
conversation_closeout Layer 6b stealth token purge, framework_elicitation
_produce_deliverable hold, build_system_prompt_for_gear criteria injection.
9 judge conditions all folded (see phase2-design.md ⚖ section). Tests:
test_risk_gate.py (52) + test_risk_gate_pipeline.py (6) = 58; full 3621,
only 2 new-vs-baseline = environmental capability_registry (live ~/ora
config drift, not my diff). ADVERSARIAL PRE-CHECK folded 4 real defects the
workflow majority-vote refuted but I verified against code: (1) BLOCKER
fail-open — evaluate_hold raised on token-store I/O error → wrapper
proceeded; now evaluate_hold never raises + FAILS CLOSED for irreversible,
and the hold is evaluated before any other fallible step; (2) MAJOR
framework approve never worked (mint under real conv, consume under None) →
task tokens FINGERPRINT-scoped (fp binds conv), mint+consume both conv=None;
(3) MAJOR double-approval → two live tokens → grant removes existing unused
token for the fp first (te.remove_unused_tokens), strict one-shot; (4) MINOR
/risk high rejected → tier aliases. Broadened Stage-A patterns for realistic
irreversible phrasings (ship-to-prod, email-as-verb, wire money, cut a
release, go-live). Durable impl diff (10 files,+1770/-20, whitespace-clean).
REVISION 2 (2026-07-03) — judge blocked commit with 5 real integration
findings my logic-focused pre-check missed; all folded: (P1) stealth
task-token purge couldn't match — tokens stored conversation_id=None; now
grant STORES the granting conv (closeout Layer 6b matches) while consume is
fingerprint-only (te.consume_token_by_fingerprint). (P1) framework
interactive deliverable approval stranded — hold reply dropped the
ora-framework marker; now the task-gate payload carries resume={fw,mode}
(data, no nested '-->') and handle_task_gate_reply "1" re-attaches the
reconstructed marker (framework_elicitation.elicitation_marker) so the flow
re-enters. (P1) route_observed not turn-scoped on global sink — now a
turn-start now_ts() is captured at the before-clock and passed as turn_ts.
(P2) inline /risk lost on direct fallback — _direct_stream gained a
risk_override param (threaded from the bypass fallback) AND strips inline
/risk itself. (P2) risk_tier not propagated — record() stamps ctx.risk_tier
on events; project_registry exports ORA_RISK_TIER. THEN a Rev-2 adversarial
pre-check confirmed a BLOCKER in my own P1-framework fix: the token was
fingerprinted from the summarizer's deliverable_input, which re-runs
nondeterministically on the continue-turn → fingerprint drift → approved
token never matched → re-hold loop. FOLDED: _produce_deliverable now
fingerprints by the STABLE framework+mode identity (classifies tier from
content, but the task identity is fw/mode, not the volatile bullets). Parity:
3625 tests, only 2 environmental capability_registry, zero code regressions;
+62 risk_gate tests. Durable diff regenerated (11 files,+1990/-27, clean).
REVISION 3 (2026-07-03) — judge blocked Rev-2 with 3 more framework-flow
findings; all folded: (F1) framework approval token too broad across
conversations — now conversation_id is threaded continue_elicitation →
_produce_deliverable (boot conversation_id / server panel_id) and bound into
the stable framework+mode fingerprint. (F2) sidebar /approve stranded
framework deliverables — the hold reply now carries BOTH the ora-task-gate
AND ora-framework markers (siblings), so a queue/sidebar approval + single
"continue" falls through the task-gate handler to is_continuation and
re-enters; card event persists resume. (F3) route_observed missing on
framework terminal paths — added to boot + server framework one-shots and
_produce_deliverable (try/finally, turn_ts before execution). THEN a Rev-3
adversarial pre-check confirmed 2 minors (folded) + 1 rejected-but-real
(folded): (a) the hold reply leaked into the elicitation summarizer input —
_format_conversation now skips any turn carrying the task-gate marker
wholesale; (b) server framework route_observed folded ZERO events (framework
paths never seeded turn ctx → events had conv=None) — now set_turn_context
seeds conversation_id+tier at all 3 framework exec sites; (c) _direct_stream
MAX_ITERATIONS overrun didn't record route_observed — added. Accepted+noted:
terminal orphan (conversation_id=None) framework token is conversation-
agnostic (single-user, no other session to leak to; the chat multi-conv
risk is bound). Parity: 3630 tests, 2 environmental only, zero code
regressions; durable diff 11 files +2195/-31.
REVISION 4 (2026-07-03) — judge: framework token still scoped to
conversation+framework+mode, not the specific held instance → a materially
different LATER deliverable in the same conversation reused a live approval.
FIX evolved through the adversarial loop: (v1) per-hold nonce CARRIED in the
marker — but the Rev-4 adversarial pre-check + my re-analysis found carrying
lets an approve-then-PIVOT inherit the live token (the exact reuse). (v2,
FINAL) a CONTENT nonce recomputed every turn = sha1 of the normalized WORD
MULTISET of the whole deliverable text (all \w+ tokens lowercased+sorted):
bullet/word REORDER drift → same nonce (approved deliverable still produces,
no re-hold); MATERIALLY different words → distinct nonce → distinct token →
holds (no carried value to inherit → closes the pivot reuse); hashing the
whole text (not just bullets) means empty-fact deliverables aren't a constant
nonce. Removed the now-unused carried-nonce machinery (held_hnonce params +
held_hnonce_from_history). Rev-4b adversarial pre-check: 0 confirmed, 4
rejected; folded 2 on merits — empty-bullets constant-nonce (resolved by
hashing whole text) + drift robustness (word-multiset absorbs word reorder,
not just bullet reorder) — and the scaffolding-leak minor (_format_conversation
now also skips ✅/❌ approval/cancel replies). ACCEPTED+documented tradeoff:
genuine word-SUBSTITUTION drift (rare) → a SAFE re-hold (user re-approves, no
reuse), chosen over the carried-nonce's pivot hole. Parity: 3634 tests, 2
environmental only, zero code regressions; durable diff 11 files +2260/-31.
NEXT: RESUBMIT Revision 4 packet → judge → (if approved) land per git
workflow. The superseded design-gate packet: Full design (post
seam-scout + completeness-critic folds):
/Users/oracle/ora-worktrees/phase2-design.md. Highlights: deterministic
two-stage risk_tier (turn-head pattern floor + optional mode `## RISK
TIER` heading; light default for analytical turns, fail-to-high-risk on
assignment error); tier rides step1_result + turn-ctx field + ORA_RISK_TIER
env; tier=irreversible pre-run hold at the pre-executor chokepoints
(server funnel entry reading step1 as data — NOT ctx, which seeds later;
_direct_stream head; boot pre-gear; framework branches which today never
seed ctx at all); hold reuses Paused-queue kind='task_gate' + marker
"1"-reply resume + fingerprint-scoped consume-on-resume task token
(sha1(conversation_id|prompt-fingerprint), 15-min TTL provisional);
clarification-enrichment recheck at the funnel; route_observed fold
recorded at turn end (no output_type comparison — doesn't exist until
Phase 4); criteria pass (sidebar slot) for floored standard+ turns only;
5 open questions incl. light-vs-standard default and MSI-custom-path
deferral. Working model unchanged: judge approval → then code in a FRESH
worktree off 20438071 (never ~/ora's main checkout). Spec durable copy:
/Users/oracle/ora-worktrees/ora-execution-review-spec.md.

## SPEC LOCATION (restored 2026-07-03)
The spec `~/Downloads/ora-execution-review-spec.md` had gone missing from
disk. It was reconstructed verbatim from the original thread's context
(that thread read the full file at session start) and restored to BOTH
`~/Downloads/ora-execution-review-spec.md` and a durable copy
`/Users/oracle/ora-worktrees/ora-execution-review-spec.md` (416 lines, 18
sections). Use the durable copy if Downloads is cleared again. Phase 2 is
scoped by spec sections 6 and 8.

## Where the work lives
- Worktree: `/Users/oracle/ora-worktrees/execution-review` (branch
  `execution-review` off `b5e629cd`, **UNCOMMITTED** — judge said do not commit).
- Baseline compare worktree: `/Users/oracle/ora-worktrees/baseline-b5e629cd`
  (pristine, same commit; delete when done).
- Latest diff: `scratchpad/phase1-final-v6.diff` (23 files, +3906/-101).
- Baseline failure set (for parity): `scratchpad/baseline-failures.txt`
  (22 failures + 5 errors — all pre-existing live-model/config tests).
- Full suite parity confirmed repeatedly: 3494 tests, baseline-identical,
  ZERO new failures. New instrumentation tests: 140 across 3 files.
- Spec: `~/Downloads/ora-execution-review-spec.md`.

## Working model
This thread IMPLEMENTS; a separate judge thread reviews at gates. User relays
packets both ways. **No commit / no Phase 2 until judge approves.** Each judge
round has found real gaps; the reliable pattern = apply fix → run a small
adversarial workflow over the changed logic → fold confirmed findings BEFORE
resubmitting.

## Phase 1 = instrumentation + capability gate. Files created/changed
NEW: orchestrator/tool_events.py (recorder + capability manifest + gate +
approval tokens + evidence-check vocab); orchestrator/tools/code_execute.py
(sandbox-exec runner); 3 test files (test_tool_events / test_dispatcher_gate /
test_shell_profiles).
CHANGED: dispatcher.py (gate-before-permission + per-call axis resolution +
MCP branch relocation + per-path escalation + record); boot.py (call_model
events, step-2 RAG events, legacy-tool registration, dead _code_execute
removed); tools/bash_execute.py (SHELL_PROFILES, path extraction, cwd
tracking); tools/search_files.py (secret-descendant withholding); hooks.py,
media_capture.py, project_registry.py, capability_registry.py,
tools/engram_promotion.py, tools/subagent.py, oversight_queue.py,
resolution_chain.py, slash_commands.py, oversight_health.py,
retention_sweeper.py, conversation_closeout.py, server/server.py,
config/mcp-servers.json.

## Security review rounds (all CLOSED, in the diff+tests)
- R1 impl review (3-lens): redirect `echo x > config/hooks/y` bypassed
  protected-config gate → `_command_target_paths` + dispatcher per-path
  escalation. Plus: bash/code_execute secret reads gate; _direct_stream
  stealth context; _queued_hashes clear-on-resolve; MCP declared axes;
  code_execute sandbox denies secret-dir reads; telemetry→oversight_health.
  Also the missing `import time` cascade + the sys.path test-isolation trap
  (MUST use Path(__file__).resolve().parent.parent, not relative insert).
- R2 (judge): search_files/list_directory sensitivity; script/package runners
  (npm/node/python3/pip/brew) fail-closed; code_execute denies ALL $HOME
  reads; approval tokens require exact conversation match.
- R3 (judge + adversarial pre-check found 4 more): bare-filename operands
  (`cat id_rsa`) surfaced + cwd-resolved; archive/transform readers surface
  secret INPUT operands; `-f` program files surfaced; `.pem/.key/env.local/
  private_keys/keys/creds` added to boundary-anchored resolver; viewers
  (less/nl/od/base64) added to read profiles (were over-gating);
  search_files centralized on resolver (secrets_of_success.md stays visible).
- R4 (judge): in-command `cd`/`pushd`/`popd` + env-prefix hid relative reads →
  effective-cwd tracking across segments; unmodelable cd (`$VAR`,`-`,empty
  popd) + relative read = fail closed.
- R5 (judge): archive OUTPUT into protected path (`tar czf <prot>/x.tgz`)
  escaped (only reads surfaced) → surface archive operands as BOTH read+write;
  proactively did mkdir/touch/mkfifo/rmdir + yt-dlp.
- R6 (judge): curl/wget download OUTPUT flags (-o/-O/--output-dir/-P) weren't
  writes + downloads mis-classified read → fixed extraction + classify
  saving-download as reversible_write. Whole-class audit: every gate-passing
  write-producer now gates on a protected-path output.

## Key invariants (do not regress)
- Gate runs BEFORE and independently of permission mode (auto-approve can't
  carry irreversible/unknown/secret/sensitive).
- Path sensitivity centralized in tool_events.resolve_path_sensitivity
  (boundary-anchored regex) — single source of truth for shell gate +
  search_files. Fail-closed default for unknown actions {irreversible,secret}.
- enforcement_model: in_harness / boundary_only / orchestrated (code_execute
  only, mac-sandbox only). Never claim orchestrated off-mac.

## CURRENT STATE: portability review (judge made it a release blocker 2026-07-03)
Delivered a READ-ONLY portability audit + design packet; AWAITING JUDGE
REVIEW before any edits. No code changed for portability yet.

### Audit findings
- B1 BLOCKER: `import fcntl` top-level in tool_events.py:38 (also pre-existing
  oversight_actions.py:39) → module import crashes on Windows → all tools dead.
- W1 SECURITY: secret/protected regexes anchor on `/`; Windows realpath returns
  `\` → patterns don't fire → gate silently fails. DEMONSTRATED:
  `C:\Users\alice\.ssh\id_rsa` and `\.aws\credentials` → NOT matched.
- F1: code_execute uses mac sandbox-exec (code_execute.py:30); already
  fail-closes when absent → Windows safe-by-default but must be DECLARED
  unavailable, never counted cross-platform.
- F2: shell profiler models POSIX grammar + shlex POSIX mode; Windows cmd/
  PowerShell differ → must fail closed on Windows unless POSIX shell declared.
- W2: search_files still shells to Unix `grep` (search_files.py:53) → errors on
  Windows.
- P1: hardcoded WORKSPACE=~/ora, VAULT=~/Documents/vault, CONVERSATIONS,
  _PRIVATE_ROOTS in dispatcher.py:37-40 + tool_events.py:50,282. Existing
  central layer to REUSE: orchestrator/runtime_paths.py (ORA_HOME env-override,
  CONFIG_DIR, DATA_DIR) — lacks vault/conversations/scratch, not consumed yet.
- T1: 3 new test suites are POSIX-only, no Windows-path coverage.

### Design (mapped to judge's 8 constraints)
1/2/P1: extend runtime_paths.py (add VAULT/CONVERSATIONS/SCRATCH, env-override,
  Windows defaults %USERPROFILE%); tool_events+dispatcher import from it.
3/4/W1: add normalize_for_match(path) = realpath+expanduser then
  replace('\\','/').lower(); run ALL sensitivity/protected checks through it
  (regexes then match both separators + Win drive/user-profile paths).
B1: guarded fcntl import + shared locked_file() (POSIX flock / Windows
  msvcrt.locking); approvals file → lock-free atomic os.replace. Share the
  helper so oversight_actions.file_lock adopts it too.
5/F2: resolve_shell_profile fail-closed on os.name=='nt' without declared
  POSIX shell (ORA_POSIX_SHELL/WSL/git-bash); POSIX grammar POSIX-only. Do NOT
  claim cross-platform shell support.
6/F1: _sandbox_backend() abstraction; code_execute mac-only in Phase 1,
  explicitly gated/unavailable elsewhere; enforcement never orchestrated off-mac.
W2: replace grep subprocess with Python-native os.walk+regex (keep the
  secret-descendant post-filter); optional rg/grep fast-path.
7/8: Windows-path tests via ntpath/PureWindowsPath (feed `C:\...\.ssh\id_rsa`
  etc., assert via normalizer) runnable on mac/Linux CI; mac tests stay POSIX
  fixtures; production code drops mac-only path/command deps.

### Phasing recommendation given to judge
Must-fix-blocking: B1, W1, path-layer+normalizer, W2. Gate-as-unavailable
(allowed): F1 (code_execute mac-only), F2 (Windows shell fail-closed).

### PORTABILITY IMPLEMENTED 2026-07-03 (judge approved-with-conditions)
Latest diff: scratchpad/phase1-portability.diff (26 files, +4382/-147).
Full parity: 3510 tests = baseline 22F/5E, ZERO new; +16 portability tests
(orchestrator/tests/test_portability.py). POSIX security verified unweakened.
Changes:
- runtime_paths.py: single low-dep source — added VAULT/CONVERSATIONS/SCRATCH/
  LOGS + *_STR string forms (env-overridable ORA_VAULT/ORA_CONVERSATIONS/
  ORA_SCRATCH); `norm_key()` (os.path.normcase over realpath) for startswith;
  cross-platform `locked_file()` (guarded fcntl / msvcrt / best-effort).
- tool_events.py: dropped top-level fcntl; imports roots from runtime_paths;
  `_matchable()` (forward-slash lowercased) for REGEX; `_cmp_key()`
  (norm_key then '/'-normalized) for startswith — all classification runs
  through these so Windows `\` paths + case fold correctly. _PRIVATE_ROOTS/
  _PROTECTED_* rebuilt as cmp_keys; approvals lock → runtime_paths.locked_file
  (kept locking per condition 2; atomic os.replace retained). `.env` pattern
  broadened to catch `*.env` (not `.venv`).
- oversight_actions.py: file_lock delegates to runtime_paths.locked_file
  (removed its own top-level fcntl — was an Ora-wide Windows crash; my gate
  queue calls it).
- bash_execute.py: `_posix_shell_available()`; resolve_shell_profile fails
  closed (unknown, profile='non-posix-shell') on Windows w/o ORA_POSIX_SHELL.
- code_execute.py: `_sandbox_backend()` (darwin+sandbox-exec only); imports
  cleanly on any platform; unavailable→gated off-mac; enforcement never
  orchestrated off-mac; explicit platform message.
- search_files.py: `_grep_available()` gate; `_iter_matches_python()` fallback
  (os.walk+regex) used on Windows / when grep absent / ORA_SEARCH_PY=1; BOTH
  backends pass through _path_is_shielded (withholding preserved).
- dispatcher.py: WORKSPACE/VAULT/CONVERSATIONS/LOG_DIR from runtime_paths.
NOTE: pre-existing mac-only bits NOT in Phase-1 scope (flagged, not fixed):
media_capture.py ffmpeg /opt/homebrew fallback + avfoundation; bash_execute
classify_command sensitive_dirs (/System etc., harmless — extra POSIX gating).
STATUS: awaiting judge review of the portability implementation.

## REVISION 7 (2026-07-03) — judge portability findings + adversarial folds
Judge blocked commit with 3 findings + 1 cleanup; all fixed, then the
adversarial pre-check (4 finders / 2-refuter verify per finding, 11 raw →
4 confirmed) folded 4 more demonstrated gaps. All in the diff:
- [P1] MCP vault path: config/mcp-servers.json vault-fs arg is now
  "${ORA_VAULT}"; mcp_client.py expands ${ORA_HOME}/${ORA_VAULT}/
  ${ORA_CONVERSATIONS}/${ORA_SCRATCH} in command/args/env at launch (env
  var wins over runtime_paths default; unknown placeholders left verbatim);
  mcp_client WORKSPACE/MCP_REGISTRY from runtime_paths.
- [P1] Execution-shell coupling (bash_execute): ORA_POSIX_SHELL must be a
  REAL shell executable (absolute isfile, or shutil.which-resolvable name;
  flag-style values rejected → counts as no declaration). On Windows,
  execute_command runs [shell, "-c", cmd] with shell=False for foreground
  AND background; without a valid shell it REFUSES (returns error, never
  falls back to cmd.exe — profiled grammar and executing shell can't
  diverge). POSIX path byte-identical to before.
- [P2] Queue roots: oversight_actions / oversight_queue / oversight_events
  (the gate's failure telemetry rides that bus) derive from
  runtime_paths.DATA_DIR.
- code_execute.SCRATCH_DIR from runtime_paths.SCRATCH_DIR_STR.
ADVERSARIAL FOLDS (each demonstrated live before fixing):
- NEW tool_events.global_sink_path() — env ORA_TOOL_EVENTS_PATH read at
  CALL time, else DATA_DIR default — single source shared by the writer
  (_sink_path), the stealth purge (conversation_closeout Layer 6a now
  imports it) and retention rotation (ROTATABLE_JSONL entry), so purge and
  rotation always target the file record() writes.
- conversation_closeout Layer 9 scrub: targets from runtime_paths at call
  time (was hardcoded ~/ora/data/oversight → silent no-op under ORA_HOME).
- Peer-writer splits closed (my root-move had created reader/writer splits):
  oversight_relationships (events/actions logs), redefinition_handler
  (reeval-queue; oversight_queue reads it), compaction.py (compaction log;
  retention rotates it), retention_sweeper all roots — all runtime_paths.
- code_execute sandbox: NEW _PRIVATE_DENY_ROOTS (WORKSPACE/VAULT_STR/
  CONVERSATIONS_STR, fallback expanduser defaults) appended to the
  file-read deny list in _sandbox_profile — a vault relocated OUTSIDE
  $HOME stays unreadable (was demonstrated readable + stdout-exfiltrable
  while axes still claimed sensitivity=private/egress=none/orchestrated).
Tests: +20 net new (Windows execution-shell coupling incl. real /bin/sh
run under simulated nt; MCP placeholder expansion/relocation + no-hardcoded-
user-path scan of checked-in config; root-agreement assertions; sandbox
deny-profile + live mac denial regression; Layer-6a relocated-sink purge).
2 existing Layer-9 tests re-pointed from os.path.expanduser side_effect to
patching runtime_paths.DATA_DIR_STR + ORA_TOOL_EVENTS_PATH (mechanism
change was required by the fix; assertions unchanged).
Adversarial-rejected, flagged-not-fixed: Windows _clean_env omits
SystemRoot/COMSPEC (real-Windows spawn may fail — VISIBLY, fail-closed, no
misclassification); oversight_router router.jsonl stays old-root (writer-
only, self-contained); watcher heartbeat/pointer files (writer+reader
agree with each other, pre-existing); ORA_POSIX_SHELL naming a non-shell
executable (operator-owned, validated-executable is the enforceable line).

## REVISION 8 (2026-07-03) — MCP stdio Windows receive + adversarial folds
Judge blocked on one [P1]: mcp_client._recv waited on the subprocess pipe
with select.select — Windows select supports only sockets, so every stdio
MCP init fails on PCs. Fix: connect() starts a daemon reader thread
(_start_reader) pumping stdout lines into a bounded queue.Queue via
blocking readline; _recv drains via Queue.get(timeout=deadline-remaining);
no select anywhere (static test asserts no `import select`).
ADVERSARIAL FOLDS (2 attackers / 2-refuter verify; 8 raw → 5 confirmed,
4 distinct, all demonstrated live):
- Popen pins encoding="utf-8", errors="replace" (MCP stdio is UTF-8 by
  spec; bare text=True = locale ANSI codepage on Windows ≤3.14 → first
  non-ASCII response killed or mojibake'd the stream; with replace, a bad
  line at worst fails json.loads and is skipped).
- One malformed line no longer kills the pump permanently (was: bare
  except → silent EOF sentinel → connection dead though server healthy).
  Pump read errors are logged to stderr, never swallowed.
- Persistent _reader_eof flag: after stream end, _recv drains leftovers
  non-blocking and answers None IMMEDIATELY on every later call (was:
  one-shot sentinel → each subsequent call stalled its full timeout —
  30s per call_tool; old select-on-EOF answered in ~0ms).
- _RECV_QUEUE_MAXLINES=10_000 bound (PROVISIONAL constant): full queue
  blocks the reader → OS pipe fills → server write-blocks — restores the
  old 64KB pipe backpressure (demonstrated: chatty server grew parent RSS
  ~443MB in 3s unbounded).
Adversarial-rejected (pre-existing / not worsened): failed-initialize
leaves subprocess running + a parked daemon thread; repeated connect() on
one MCPConnection object (no caller does).
Tests: +9 in TestMcpStdioWindowsPortability (select-rejects-pipes
simulation via real pipe + patched select raising; timeout immediacy;
notification/blank/non-JSON skipping; EOF + repeated-instant-EOF; bad-bytes
survival; Popen encoding kwargs; bounded queue; no-select static check).
Focused 4-suite count: 184 (judge's 175 + 9). Full suite 3539 = baseline
22F/5E, zero new. Packet correction: Rev-7 packet said "191/191" for the
focused suites — arithmetic, not a measurement; correct was 175.

## Post-landing follow-ups (tracked, judge-confirmed NON-blocking)
- Pre-existing hardcoded `~/ora` paths in conversation_closeout.py outside
  the gate/MCP substrate (e.g. conversation-manifest / indexing-failures
  sinks in other purge layers) — move onto runtime_paths AFTER Phase 1
  lands (a chip now would edit files in this uncommitted diff and
  conflict). Same family: oversight_router router.jsonl, watcher
  heartbeat/pointer files, oversight_health/daily_note roots.
- Windows _clean_env in bash_execute omits SystemRoot/COMSPEC/PATHEXT —
  real-Windows process spawn under a declared POSIX shell may fail
  (visibly, fail-closed); harden when a Windows host is available to test.

## Cleanup chips already spawned (separate sessions, done): stale oversight
watcher, ~/ora/CLAUDE.md stale refs, MSI docstrings. MSI adapter work deferred
to Phase 8 until the Barb McGowan voice lands.
