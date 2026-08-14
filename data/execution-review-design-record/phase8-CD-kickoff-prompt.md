# Phase 8 — fresh-session kickoff (land Chunk B, then Chunks C + D)

You are the **Execution Thread** on the Ora Execution Review build. Phases 1–7 are LANDED; **Phase 8 Chunk A LANDED** (`d7edb377`, PR #193); **Phase 8 Chunk B is at the CODE-REVIEW gate** (Rev 1, folded + re-checked). This session's job: **(1) land Chunk B once the judge approves it, then (2) drive Chunks C and D** — each design-addendum-gated then code-review-gated, exactly like every prior chunk.

**Read first, in order:**
- `/Users/oracle/ora-worktrees/HANDOFF-execution-review.md` — START at the top block ("PHASE 8 — CHUNK B Rev 1 … RE-DELIVERED TO THE GATE"). It has the current status, the landed-SHA chain, the carried gotchas. Everything under it is history (most-recent-first).
- `/Users/oracle/ora-worktrees/ora-execution-review-spec.md` — §4 (evidence classes as adapter FAMILIES), §5 (lanes), §7 (evidence-runner safety rules; orchestrated egress must route through a logging proxy or be denied), §11 (dirty-state modes), §14 (tiered persistence), §16 (three invariants), §17, §18, and the release-blocking Portability amendment near the top.
- `/Users/oracle/ora-worktrees/phase8-design.md` — the judge-approved design (Rev 4). **§8 is the sequencing contract**; **§4 = Chunk C** (adapter families); **§5 = Chunk D** (MSI wiring). The ⚖ Rev-3/Rev-4 blocks record folds that are binding.
- Your recalled memory `project_execution_review.md` (auto-loads) + `~/ora/CLAUDE.md` — **especially the Project Plugin Convention section, LOAD-BEARING for Chunk D**: Ora is a generic prototype; MSI-specific code goes in `~/sites/mainstreetindependent/ora-project/`, NEVER `~/ora/orchestrator/`. Any MSI wiring = generic seam in ora + recipe in ora-project. Also the vault-canonical rule.

**Environment / discipline (proven across A + B):**
- Repo `~/ora`, remote `origin` (ora-commons/ora); push `git push origin`. **User cannot open github.com links** — report PR **numbers** + **bare commit SHAs**, never URLs.
- Python is `/opt/homebrew/bin/python3`. Full suite: `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off /opt/homebrew/bin/python3 -m unittest discover -s orchestrator/tests`.
- **Never work in `~/ora`'s main checkout** — concurrent sessions switch branches there and the live server writes runtime files there. Always a pinned worktree under `/Users/oracle/ora-worktrees/`.
- `origin/main` advances via concurrent sessions — **FETCH FIRST**, branch/scout off CURRENT origin/main, rebase before landing.
- **The loop is LIVE in prod** (`ORA_EXECUTION_LOOP=1`); the live server picks up landed code on its next restart. `ORA_PROVENANCE_CLAIM_MAP` (Chunk A Level-2) stays unset. `ORA_EXEC_REVIEW_MUTATING` (Chunk B) is default-ON-with-loop.
- Working model per chunk: **design addendum → relay to judge → on approval implement in a fresh worktree → adversarial pre-check (Workflow: 3–5 lenses × per-finding verify; if verify agents are rate-limited, RE-VERIFY every finding + null vote BY HAND) → parity (fresh pre-edit baseline in the SAME worktree, diff sorted FAIL/ERROR lists, target ZERO NEW vs the ~27-failure environmental baseline [22 FAIL + 5 ERROR; ~3,982 tests as of a511e7c4]) → deliver impl packet to the CODE-REVIEW gate → NO commit until the judge approves → land per the git workflow.**
- **Land-per-git-workflow = ** re-fetch origin/main → rebase the branch onto it → `git add -A` (stage new files) → commit (end message `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`) → push → `gh pr create` → `gh pr merge <N> --squash --delete-branch` → delete the local branch → `git worktree remove … --force` + `git worktree prune` → fast-forward `~/ora` main **ff-only** (from a NON-main worktree; `git -C ~/ora merge --ff-only origin/main` fails if ~/ora is on main — use `git fetch` there or ff from another worktree) → smoke-import the landed modules → report PR# + bare SHA. **The user's git workflow is standing authorization** (commit/push/PR/squash-merge/delete-branch by default once verified) — but this project ALSO requires the judge's code-review approval before any commit.

---

## STEP 1 — Land Chunk B (do this once the judge has APPROVED Chunk B)

Chunk B (the isolated mutating-check actuator, design §3) lives in worktree
`/Users/oracle/ora-worktrees/phase8b-impl`, branch `execution-review-phase8b-impl`, **rebased onto
`a511e7c4`**, Rev-1 (code-review block folded + adversarial re-check folded). Durable:
`phase8b-impl-packet.md` (Rev 1) + `phase8b-impl.diff` (4 files, +1,089/−35; new
`orchestrator/tests/test_isolated_actuator.py`). Parity was FINAL-IDENTICAL (3,982 tests, 27 F+E,
zero new).

**If approved:** re-fetch → rebase onto current origin/main → land per the git workflow above.
Chunk B touches `orchestrator/evidence_runner.py`, `execution_loop.py`, `execution_packet.py` +
the new test file — if a concurrent session has landed anything touching those, resolve at rebase
(the legacy-path retrofit that already landed as `a511e7c4` did NOT overlap). Report PR# + SHA.
Then update the handoff top block + memory to "CHUNK B LANDED" and move to Step 2.

**If the judge instead returns findings:** fold them in the phase8b-impl worktree, run an
adversarial re-check over the fold, re-run parity (zero-new), re-deliver. NO commit until approval.

---

## STEP 2 — Chunk C (adapter families, design §4) — ADDENDUM FIRST

Chunk C generalizes the five §4 evidence classes into FAMILIES + project recipes; the code adapter
(Phase 5) is the trustworthy template; **it depends on Chunk B** (the vault family's checks run
through the isolated worktree). Scope (design §4, with the ⚖ Rev-3 folds binding):
- **Lane emission + filling become declared + dispatched (§4.1):** `route_lanes` keeps its two
  OBSERVED lanes; the other three (`run_observe`/`render_inspect`/`deploy_probe`) are DECLARED via
  an Evidence-Contract `lanes:` block + project recipes; `fill_evidence_lanes` generalizes to a
  per-lane **filler registry** keyed by lane name (diff_validate = existing; collect_provenance =
  Chunk A's filler; deploy_probe = §4.3; render_inspect = §4.4; run_observe = declared-only, no
  filler shipped — state it).
- **Notes/vault family (§4.2):** two generic check tools — `vault_frontmatter_lint` (strict YAML
  parse, malformed ≠ absent) + `vault_wikilink_check` (body `[[targets]]` vs a title universe).
  **⚖ Rev-3 REDESIGN (both empirically pinned):** ora code + the main `.git` are read-DENIED inside
  the sandbox, so the runnable check scripts are **self-contained single files in the target repo's
  own `.ora/tools/`** (ora ships the canonical templates + tests), and the title universe is a check
  INPUT the actuator pre-builds OUTSIDE the sandbox (`git ls-tree -r --name-only <delta_commit>` →
  `title-universe.txt` in run-tmp), never an in-check git call. In-place vault runs are SEC-2-refused
  → ALL vault checks route through the Chunk-B worktree (this is why C needs B, and Chunk B already
  ships `requires_isolated_worktree` routing for exactly this).
- **Deploy+probe family (§4.3):** probes are **instrumented in-harness READS, not sandboxed
  subprocesses** (the runner enforces network:deny only). A generic `deploy_probe` filler runs
  DECLARED probe specs (`{kind: page|sitemap|feed|headers|git_heartbeat, url_or_ref, must_contain?,
  max_age?}`) via `tools/web_fetch` / `_git`, recording one tool event per probe (§7 egress observed
  through the instrumented boundary). Tri-state verdicts PASS/FAIL/**INDETERMINATE**. **⚖ Rev-3:
  every recipe carries a MANDATORY `rollback` field** (a recovery ref or the explicit literal
  `none: <recovery contract>`), rendered with the results.
- **Render+inspect family (§4.4):** mechanical validity (parse/zip-open/header) is the evidence
  lane; perceptual quality stays a **judgment lane with `verdict: null`** (§5 category-error guard).
  Ship one generic `render_validity` tool + family README; deeper inspection is out of Phase 8.

**Judge P3 (binding):** no user-path literals — every path Ora-repo-root-derived / `runtime_paths.VAULT`-derived / target-repo-relative; add Windows-shaped fixtures. Decide whether `.ora/tools/*` needs `_PROTECTED_BASENAMES` protection (recommend yes).

**Do:** write a SHORT Chunk-C design addendum (final catalog/recipe schemas + the filler-registry
shape + the `.ora/tools` template/protection decision + the judge-P3 path derivations), relay it to
the judge as a light design check-in, and on approval implement. The vault catalog is a NEW file in
the vault repo (`<VAULT>/.ora/evidence.yaml`); `evidence.yaml` is already in `_PROTECTED_BASENAMES`.

---

## STEP 3 — Chunk D (MSI custom-path wiring, design §5) — ADDENDUM FIRST (fresh MSI scout)

**Depends on Chunk A** (the claim-to-source map pattern) **and Chunk C** (the deploy_probe family).
MSI repo `/Users/oracle/sites/mainstreetindependent` churns via concurrent sessions — **re-scout at
implementation time; pull/re-read before editing; stage only your own files.** Scope (design §5):
- **Generic seams in ora (project-agnostic):** (a) `model_dispatch.invoke_chat` gains optional
  boundary tool-event recording; (b) a new `execution_review.record_program_run(...)` entrypoint for
  programmatic/non-terminal runs — **⚖ Rev-3 CONTRACT (spec §16-2/§16-3, judge blocker fold):
  signals are FOLDED FROM THE RUN'S OWN EVENT LOG (a passed `ORA_TOOL_EVENTS_PATH` reference), never
  caller-narrated; evidence lanes filled ONLY by the registered fillers/recipes; caller free-text →
  `producer_claim`, rendered last, labeled unverified**. `enforcement_model` is caller-declared +
  vocabulary-validated (the honest exception — the regime is the integrator's knowledge, not
  derivable from the log).
- **MSI recipes in ora-project (project-specific):** instrument `backfill_orchestrator._call_openrouter`
  (the single chokepoint) with guarded boundary events (headless-systemd-safe); `publish_cycle`
  boundary events + post-publish deploy_probe recipe (async poll, never a gate); the MSI
  `.ora/evidence.yaml` (frontmatter-gate check + deploy_probe recipe with the mandatory rollback =
  the honest "none — next FULL build" value; the astro validation build is unrunnable as declared —
  gitignored node_modules + /tmp outDir — the addendum picks its honest shape); `invoke_real_gear4`
  calls `record_program_run` after `boot.run_gear4`; per-article source manifest from the fenced
  SOURCE ARTICLE blocks + verified-figures.json.
- **⚖ Rev-3 explicit D-addendum scope:** (i) **MSI loop reach** — wire the Phase-6 loop for the
  `invoke_real_gear4` path OR scope it out LOUDLY with rationale (silence is not an option); (ii)
  the **§6/§8 irreversible gate for publishing** — a published article is the canonical irreversible
  action; state the honest posture (boundary-observed + tier-stamped + deploy_probe as post-hoc
  evidence; zero-manual-labor forbids a per-article human gate); (iii) concurrent-process sink
  atomicity for multiple MSI systemd processes.
- **Zero-manual-labor invariant** (memory `feedback_zero_manual_labor`): no review queues, human
  gates, or manual placement in any recipe.

**Do:** fresh read-only MSI scout → SHORT Chunk-D design addendum (exact seam list + loop-reach
decision + irreversible-gate posture) → judge → implement → pre-check → parity → code-review → land.

---

## Carried gotchas (do NOT re-introduce)
- `reversible: true` at high-risk is the §6 post-hoc-routing gate — **spec-correct, don't "fix".**
- A redactor's / sanitizer's except-fallback must fail **CLOSED** (never return raw input) — the P7 lesson, re-confirmed in Chunk A.
- **`contextvars` do NOT cross `executor.submit`** — always `copy_context()` into worker threads (the Chunk-A judge-P1 blocker).
- **A load-bearing side-effect sweep must not sit behind a new early-return gate** (the Chunk-B re-check minor: the orphan-prune must run unconditionally).
- Chunk B / the isolated actuator and the (unrelated, still-unwired) **live gear-reinvocation actuator** both edit `execution_loop.py` — never run their implementation stages simultaneously with another session doing the same.
- Web-search cost is watched (memory `project_web_search_cost`) — provenance/probe work reuses fetched content, never adds gratuitous re-fetches.

## Explicitly NOT Phase 8
- Flipping `ORA_EXECUTION_LOOP` default / validating the live loop; wiring the LIVE gear-reinvocation actuator (the loop's revise step). That actuator RE-INVOKES the gear to revise a deliverable — distinct from Chunk B's isolated MUTATING-CHECK actuator.
- The judge's Chunk-A residual (legacy `~/ora` path literals) — a separate landed task (`a511e7c4` covered boot.py/web_search.py; any remainder is its own follow-up, not Phase 8).
