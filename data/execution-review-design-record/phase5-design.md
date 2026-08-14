# Execution Review — Phase 5 Design Packet (Code adapter + `.ora/evidence.yaml` catalog + evidence runner + Evidence Contract + dirty-state modes)

*Status: DESIGN GATE — **REVISION 2** (portability, ENFORCE-OR-REFUSE). No code
written. Rev 0 was blocked on the spec's new release-blocking **Cross-Platform
Portability Amendment**; Rev 1 reworked to a cross-platform backend but tried to
**run** `network: deny` checks off-mac while honestly labeling them unenforced —
the judge (correctly) blocked that too: honest labeling does not make an
unenforced constraint true (§7/§15 require checks to run **under** their declared
constraints). **Rev 2 fixes this with ENFORCE-OR-REFUSE:** a check runs **only**
under a backend that actually enforces its declared network policy — macOS
`sandbox-exec`, a declared **`ORA_EVIDENCE_SANDBOX`** wrapper (now a first-class
supported Windows path — WSL / container / Windows Sandbox), or native Linux
`unshare -rn` — recording `enforcement_model: orchestrated`; where no enforcing
backend exists the check **refuses cleanly** (never run unenforced). The
`boundary_only`-runs-off-mac path is retired. Also fixes the two stale `orchestrated`
overclaims (now correct because unenforceable checks refuse) and the OQ11
scratch-location slip. Retains Rev-1's shell-free `argv` catalog, Contract-live-at-
planning, Windows-simulation tests, and §7 Portability section. Implementation
waits for the judge's design approval, then lands in a fresh worktree off current
`origin/main`.*

Spec: `/Users/oracle/ora-worktrees/ora-execution-review-spec.md` — Phase 5 is
§15 ("Code adapter + catalog + Evidence Contract + dirty-state") resting on
§10 (the load-bearing **catalog-vs-Evidence-Contract** distinction), §7 (the
evidence-runner safety rules — the runner is itself an executor governed by the
same capability manifest; the two enforcement models), §11 (the three
dirty-state modes), §4 (the evidence taxonomy — **diff+validate** is the lane
to get right first; "consulted ≠ used correctly"), §5 (route by evaluation
unit; the `evidence_lanes` Phase 5 fills), §9 (the ExecutionPacket fields Phase
5 populates), and §16 points 1 & 2 (acceptance criteria + the evidence recipe
declared **independently of the executor** — Phase 5 is where point 2 becomes
real). Substrate scouted **read-only** in the pinned worktree
`/Users/oracle/ora-worktrees/phase5-scout` @ `82553162` (current `origin/main`
— the Phase-4 landing + the gitignore chore #180).

---

## 0. The one-paragraph statement of Phase 5

Phase 4 made the output *polymorphic*: the `ExecutionPacket` type, the
evidence/judgment lane split, and a router that **declares** an evidence lane
from each fired §6 signal (`any_mutation` → `diff_validate`,
`source_read_suspected` → `collect_provenance`) — but every declared lane
carries `generated_by=[] / result=None / sufficient=None`, because **nothing
generates real evidence yet**. Phase 5 is the first phase that produces real
mechanical evidence, and it does so for exactly **one** lane — **diff+validate
for code** (§4, §15: "build the one adapter used daily and make it genuinely
trustworthy before generalizing"). It ships four cohesive pieces, all generic
`~/ora` core (the project-plugin convention keeps *project* catalogs per-repo,
but the **mechanism** is generic — kickoff-confirmed): (1) the
**`.ora/evidence.yaml` repo catalog** — a version-controlled, write-*protected*
declaration of *what checks exist and how they must run*, consuming the
vocabulary Phase 1 already pre-seeded (`tool_events.EVIDENCE_RUNNER_DEFAULTS` +
`validate_check_declaration`, and `evidence.yaml` already in
`_PROTECTED_BASENAMES`); (2) the **evidence runner** — a new programmatic
executor that runs a declared check *mechanically under its declared
constraints*, **cross-platform (macOS + Windows, per the release-blocking
portability amendment) on an ENFORCE-OR-REFUSE basis**: a check runs only under a
backend that actually enforces its declared network policy (macOS `sandbox-exec`;
a declared `ORA_EVIDENCE_SANDBOX` wrapper — the first-class Windows path; or native
Linux `unshare -rn`) → `enforcement_model: orchestrated`, and where no enforcing
backend is available it **refuses cleanly** rather than running unenforced — with
shell-free `argv` checks by default and `ORA_POSIX_SHELL` for the rare shell check,
**itself gated through the Phase-1 manifest** (§7), reusing Phase 1's portability
substrate (`ORA_POSIX_SHELL`, `runtime_paths`, the `test_portability.py`
Windows-simulation pattern, the `_sandbox_backend` dispatch shape); (3) the
**planning-stage Evidence Contract producer** — the sibling to Phase 2's
`risk_gate.apply_criteria`, run at the same prior-to-execution planning step,
that selects the *task-specific* subset of catalog checks + the bespoke probe +
the sufficiency bar (§10, §16-2); and (4) the **three dirty-state modes**
(`clean_worktree` / `review_dirty_diff` / `continue_user_changes`) with their
`state_before` / `state_after` git snapshot forms, filling the §11 fields Phase
4 reserved. The load-bearing sentence the whole design serves and states in
both code and packet: **a green evidence run means *nothing broke that you knew
to check* — it does NOT mean the executor solved the right problem** (§10,
§16-2). So an evidence lane's `sufficient` is judged against the **Evidence
Contract's** declared sufficiency, never self-asserted by the executor, and the
wrong-problem catch stays with the acceptance criteria (Phase 2) + the verify
stage (Phase 6).

**The honesty line, stated up front (mirrors Phase 4's §0, and forced again by
the adversarial pass — see ⚖).** Phase 5 does **not** wire the full
produce→capture→verify→revise loop — that is Phase 6. There is **no live
pipeline path in the current codebase that plans a code task, executes it, and
then needs capture**: that whole loop is Phase 6's to assemble. So Phase 5's
runner, like Phase 4's renderer, is **built and made trustworthy by test — real
check *execution* proven against a FIXTURE repo with a trivial check; `~/ora`'s
own shipped `.ora/evidence.yaml` exercised for parse+validate ONLY, never
*executed* (its `discover -s orchestrator/tests` would re-run the runner's own
tests → recursion, ⚖ seam-F5) — and driven live by the Phase-6 loop, not
auto-run at the gear terminal.** What Phase 5 ships that is *real and usable
today*: the catalog (a genuine, version-controlled artifact for the `~/ora`
repo), the runner library (exercised by tests that actually run a `python3` /
`node` check *in a fixture* under the sandbox — the very *class* of commands the
Phase-1 shell profiler **refuses**, deferring them in a code comment to "the
Phase-5 evidence runner"),
the Contract producer, and the dirty-state/state-snapshot machinery that fills
the Phase-4-reserved `execution.mode` / `state_before` / `state_after` and the
`EvidenceLane.generated_by` / `result` / `sufficient` fields. "The one adapter
used daily" (§15) means the code adapter is the **first real adapter built**
(vs notes/publish/data in Phase 8), not that it fires on every chat turn. Every
claim of what runs live vs what is tested-but-loop-driven is stated plainly, not
described in the present tense as if already wired.

---

## 1. Substrate scout — evidence (file:line, all @ `82553162`)

### 1.1 Where the Phase-4 `EvidenceLane` fields + `execution.mode/state_*` are meant to be filled — and nothing fills them today
`orchestrator/execution_packet.py` (Phase 4, landed):
- `EvidenceLane` (`:64-77`) carries `generated_by: list[str] = []`, `result: Any
  = None`, `sufficient: bool | None = None` — the docstring says outright
  "empty until Phase 5, so a lane result ties back to a declared catalog check
  rather than executor self-report."
- `route_lanes` (`:174-192`) **declares** an `EvidenceLane(target="state_change",
  lane="diff_validate")` when `signals["any_mutation"]`, and an
  `EvidenceLane(target="grounded_claims", lane="collect_provenance")` when
  `signals["source_read_suspected"]` — **but fills no result**. The diff_validate
  lane is exactly the one Phase 5 fills first; collect_provenance stays declared
  (its claim-to-source map is Phase 8).
- `build_execution_packet` (`:322-414`) sets `execution["mode"]=None,
  "state_before"=None, "state_after"=None` (`:361`, comment "§11 reserved (Phase
  5)"), and `execution["delta"]={"any_mutation":…, "max_mutability":…, "ref":
  trace_ref}` — a *summary of the fold*, not a generated diff. `evidence_lanes`
  comes straight from `route_lanes`, declared-empty.
- The machine-readable "empty ≠ passed" invariant is already pinned:
  `lane_is_sufficient` (`:91-94`, `None → not sufficient`) and
  `all_evidence_sufficient` (`:97-105`, empty list → **not** vacuously passed).
  Phase 5 fills `sufficient` through these — an unfilled or failed check must
  never read as green.

**The attach seam.** `build_execution_packet` calls `route_lanes` *internally*
and returns declared-empty lanes; it has no parameter through which a driver can
hand in *filled* lanes. So Phase 5 needs an **additive** way to attach a filled
lane without a signature break (P4-P5 back-compat). Two options (OQ):
add an optional `evidence_results=None` kwarg to `build_execution_packet` (when
present, fills the declared lanes; absent → Phase-4 behaviour), **or** a
free-standing `fill_evidence_lanes(packet, results)` helper the Phase-6 loop
calls after construction. Either is additive; the helper touches
`execution_packet.py` least.

### 1.2 The Phase-1 pre-seeded evidence-runner vocabulary — the seam Phase 5 pours into
This is the strongest scout finding: **Phase 1 already declared the runner's
constraint vocabulary and reserved the catalog filename**, so Phase 5 is filling
a pre-cut socket, not inventing one.
- `orchestrator/tool_events.py:983-990` `EVIDENCE_RUNNER_DEFAULTS = {"timeout":
  300, "working_dir": "<repo-root>", "env": "isolated", "network": "deny",
  "mutates": False, "on_unknown": "gated"}` — it **adapts** the §10 runner block
  (⚖ code-F2): it folds in the per-check `timeout`/`mutates` and, notably,
  **omits** `redact: by-sensitivity`, which §7/§10 make load-bearing — so Phase
  5's `validate_runner_block` must **add `redact`** to the runner-block schema.
- `tool_events.py:991` `_EVIDENCE_NETWORK = {"deny", "local", "allow"}`.
- `tool_events.py:994-1006` `validate_check_declaration(check) -> list[str]` —
  validates one `.ora/evidence.yaml` **check** entry: requires only `cmd`;
  validates `timeout` numeric-**if-present**, `mutates` boolean-**if-present**,
  and `network ∈ _EVIDENCE_NETWORK` (defaulting `deny`) (⚖ code-F3). The section
  header (`:980-981`) says: "declared now, runner is Phase 5; an undeclared
  check is un-runnable by construction."
- `tool_events.py:267` `_PROTECTED_BASENAMES = {"ora-project.json",
  "evidence.yaml"}`, and `.ora` is in `_PROTECTED_PREFIXES` (`:256`). So
  `is_protected_config_path` (`:270-282`) returns **True** for any write to
  `.ora/evidence.yaml`. **The catalog is write-gated already** — a **shell**
  redirect into `.ora/` escalates to protected-config at `dispatcher.py:602-610`,
  and a direct **file-tool** write (`file_write`/`file_edit`) at `:623-636`; both
  call `is_protected_config_path` (⚖ code-F1). This is load-bearing for integrity
  (§10/§16-2): an
  executor **cannot silently edit the catalog to skip or weaken a check**,
  which is the exact way "declared checks" would otherwise leak back into
  self-reporting.

Phase 5 adds only what is missing above this: the **discovery + parse** of the
file, a `runner:` **block** validator (Phase 1 validates a *check* entry, not
the runner block), and the **runner that executes** a validated check.

### 1.3 The runner-as-executor gate surface (§7) — how a programmatic check passes the same gate
- `tool_events.gate(action, axes, params=…, model_facing=…, interactive_approver=…)
  -> GateDecision` (`tool_events.py:836-…`). It **blocks fail-closed** on exactly
  four conditions (`:855-863`): `unknown`, `mutability=="irreversible"`,
  `sensitivity=="secret"`, and (model-facing) `sensitivity=="sensitive"`. Egress
  is *recorded*, not itself a block criterion. A block checks a one-shot token,
  then a live approver, then denies-and-queues.
- `dispatcher.dispatch(tool_name, parameters)` (`dispatcher.py:641-…`) is the
  higher-level entry: `_resolve_call_axes` → `gate` → run handler → record. The
  Explore scout confirmed **every `dispatch()` today is model-tool-call-driven
  except one** programmatic caller (`tool_selector.run_deterministic_tools`,
  `tool_selector.py:213`, supplemental RAG). So a **programmatic, non-model**
  dispatch caller is *not* unprecedented — the evidence runner would be the
  second.
- Consequence for the design: a check with `mutates:false, network:deny` resolves
  to axes `{category:execute, mutability:read/reversible_write, sensitivity:
  private, egress:none}` → **passes** the gate (none of the four block
  conditions). A `mutates:true` check under worktree isolation is
  `reversible_write` (cheaply undoable) → passes. An **undeclared** check
  (`on_unknown: gated`) or one the runner can't sandbox is treated `unknown` →
  **blocked, fail-closed** (and, being programmatic with no live human, **queues**
  rather than waits). The gate therefore *naturally* permits declared low-risk
  checks and refuses the dangerous ones — no new gate logic, just correct axes.

### 1.4 The shell profiler's explicit Phase-5 deferral — the sanctioned-path finding
`orchestrator/tools/bash_execute.py` is allowlist-with-profile (§7). It profiles
`git`/`npm`/`node`/`pip`/`brew` bases but **deliberately fails the test/build
runners closed**, with comments that name Phase 5 as the resolution:
- `:456-465` `python3`/`python` → `dict(_UNKNOWN)`: "*Fail closed until the
  Phase-5 evidence runner can run them under real constraints.*"
- `:476-484` `npm test`/`run`/`install` → `_UNKNOWN`: "*All execute opaque code
  → fail closed until Phase 5.*"
- `:486-488` `node` → `_UNKNOWN`; `:467-474` `pip install` → `_UNKNOWN`.
- `git` (`:437-454`): `worktree` is a **known reversible** subcommand
  (`_GIT_REVERSIBLE_SUBCOMMANDS`, `:201-204`), read subcommands
  (`status/log/diff/show/rev-parse/…`, `:197-200`) are `read`. So the **git
  primitives the dirty-state modes need — `worktree`, `diff`, `rev-parse`,
  `status`, `stash` — are already profiled and gate-clean**; only the opaque
  test/build *runners* are deferred to us.

This is the load-bearing seam: **Phase 5 is the pre-designated sanctioned path
for running `python3 -m unittest` / `npm test` / `node …` — the profiler
refuses them precisely because a model could edit `package.json` or a repo
`.py`; the runner is different only because its `cmd` comes from a
write-*protected* catalog and runs under the runner-block constraints** (timeout
/ working_dir / env isolation / network policy / redaction / `mutates`).

### 1.5 The planning-stage criteria hook — the Evidence Contract's exact sibling
`orchestrator/risk_gate.py`:
- `run_criteria_pass(instruction, mode_text, *, invoker) -> (criteria|None,
  err|None)` (`:911-932`) — a model-call callback (sidebar slot, injected for
  testability) that produces acceptance criteria **before** execution, "do not
  attempt the task." No-op when no invoker (offline/test).
- `apply_criteria(context_pkg, instruction, risk_tier, *, invoker) -> directive`
  (`:935-980`) — light → `None` (no planning stage); standard+ → run the pass,
  stash `context_pkg["acceptance_criteria"]`, record an `acceptance_criteria`
  tool-event; on genuine failure return `"HOLD:…"` (high-risk+) / `"WARN:…"`
  (standard), **never silently fall through to light** (condition 6).
- Wired at exactly two planning points: `boot.py:9304` and `server.py:2846`
  (`_crit = _rgate.apply_criteria(…)`); the criteria are read for injection at
  `boot.py:8925` (`context_package.get("acceptance_criteria")`).

**The Evidence Contract is the sibling produced at this same step** (§8, §10,
§16-2). Phase 5's `apply_evidence_contract(context_pkg, instruction, risk_tier,
catalog, *, invoker)` mirrors `apply_criteria` exactly: light → none;
standard+ → produce `{required_standard_checks, bespoke_probes, sufficiency}`,
stash `context_pkg["evidence_contract"]`, record an event. Both are "set by a
step **prior to and separate from** execution" (§16-1/2) — the criteria and the
recipe are the two planning artifacts, and they should be produced together.

### 1.6 Git substrate + the dirty-state mapping (§11) — what exists, what Phase 5 builds
Explore scout, confirmed by hand: **Ora has no git-worktree-isolation helper, no
diff/snapshot helper, and no "run checks in a clean tree" primitive.** What
exists to *mirror* (the reuse-over-parallel house rule):
- `orchestrator/tools/engram_promotion.py:102` `def _git(repo, args)` (a **list**
  param, not varargs — ⚖ code-F4/F8) — a `subprocess.run(["git","-C",repo,*args])`
  helper; `_repo_root_for()` (`:112`) uses `git rev-parse --show-toplevel` to
  detect repo root. This is the exact idiom the runner's git-state helper reuses.
- The macOS **sandbox** primitive is `code_execute.py` (§1.7 below) — the runner
  generalizes its `_sandbox_profile` from "python -c code" to "sh -c cmd" with
  the working_dir (the worktree) as the allowed write root.
- `git worktree` is profiled reversible (§1.4) — `clean_worktree` isolation is a
  fresh `git worktree add`, the same primitive this very workflow uses
  (`isolation: worktree`) and the discipline Phases 1–4 have used for every impl.

**State-snapshot forms** (§9: "git → commit/tree hash"): all three modes snapshot
git SHAs / tree-hashes (small, flat — they fit the packet frontmatter/body), and
the **diff is referenced** (a trace-dir path), never inlined (§9). Mapping:
- `clean_worktree` — `state_before` = the base commit SHA + tree hash of the
  worktree's branch-point; `state_after` = the post-execution commit-or-worktree
  tree hash; `delta.ref` = a `git diff <before>..<after>` written to the trace
  dir. Exact "before" ref, precise change under review (§11).
- `review_dirty_diff` — `state_before` = HEAD SHA + a content hash of the
  *pre-existing* uncommitted diff (the tree as review began); `state_after` =
  current working-tree hash; `delta.ref` = `git diff` of the uncommitted changes.
  No clean tree demanded.
- `continue_user_changes` — `state_before` = a recorded baseline that
  **includes** the user's changes (HEAD SHA + a snapshot/stash-ref hash of the
  user's dirty floor); `state_after` = current tree hash; `delta.ref` = only what
  the executor added *on top of* the user baseline. The user's work is the floor,
  never reverted (§11).

### 1.7 The sandbox primitive Phase 5 reuses (§7 orchestrated model)
`orchestrator/tools/code_execute.py` — the Phase-1 sandbox: `sandbox-exec` on
macOS with **network denied entirely** (`:97` `(deny network*)`), **writes
confined** to a scratch dir + TMPDIR (`:101-104`), **all reads of `$HOME` + every
Ora private root denied** (`:84-93` — the stdout-exfiltration close), a **clean
env** with no ambient credentials (`:108-116`), and `enforcement="orchestrated"`
in its axes (`:58-68`). Off-mac: no backend → `code_execute_axes` returns
`unknown=True` so the gate **fails closed** (`:62-68`), and enforcement is never
claimed "orchestrated." This is precisely the §7 orchestrated model
(sandbox + prevention-by-absence + egress-denied). The runner runs *opaque
shell/scripts* (a declared `npm test` runs `package.json`'s script, opaque to
Ora), so by §7 the runner is an **orchestrated sub-executor**: a check that RUNS
runs under a backend that enforces its declared constraints, so its evidence
records `enforcement_model: orchestrated` — and a check whose constraints **cannot**
be enforced on the platform **REFUSES** (carries `skipped=true` + `skip_reason`, no
enforcement claim), rather than running under a weaker model (Rev-2 enforce-or-refuse).
This is distinct from the packet's top-level `execution.enforcement_model`
(`in_harness` for the core gear run).

### 1.8 Custom prompt-assembly paths (§15 Phase-0 audit) — precisely which the runner reaches
Phase 4 re-ran the audit: the MSI custom paths (`tools/gear3_orchestrator.py`,
`tools/backfill_orchestrator.py`, `scripts/article_generator.py`,
`tools/msi_run_gear4.py`) build their own prompts and won't inherit shared
assembly. **Phase 5 is runner/catalog-centric, and the runner is a library that
auto-runs on no terminal path — so it reaches _none_ of the custom paths.** None
of them run build/test/lint checks; none call the runner. MSI adopts the code
adapter only when it ships **its own** `.ora/evidence.yaml` + adapter wiring,
which memory pins to **Phase 8**. The generic runner + catalog *mechanism* lives
in `~/ora/orchestrator/` (correct per the project-plugin convention — kickoff-
confirmed the mechanism is generic; a project's catalog file is per-repo data).
`~/ora` ships its *own* catalog as repo data (§2/P1). No `~/ora/orchestrator/`
code becomes project-specific.

### 1.9 Tests / the parity surface
No `.ora/` exists in `~/ora` or the MSI project yet (Phase 5 ships the first).
`.ora/evidence.yaml` is **not** gitignored (the chore #180 gitignored only
`data/pipeline-traces/` + per-machine runtime data) → the catalog is
version-controlled repo data (correct). PyYAML is available (`yaml.safe_load`
used across `corpus_parser`, `ped_parser`, `output_runtime`, etc.). Environmental
parity baseline (inherited): **22 failures + 5 errors** (lens-integrity,
retry-fallback, openai-images, mode-relationship-priorities, user-settings,
visual-routing — all pre-existing, none related to this project); full suite
~3721 tests at the Phase-4 landing.

---

## 2. The design

The fact that shapes everything (mirroring Phase 4's "the pipeline order is the
fact"): **there is no live code-task loop in the current pipeline** — plan →
execute → capture → verify → revise is assembled only in Phase 6. So Phase 5
cannot "run checks on a real code turn," because no real turn plans-then-executes
code today. Three architectures follow; the design recommends the first and names
the others so the judge sees what was rejected.

- **Architecture A (recommended) — trustworthy runner library + shipped catalog;
  live check-execution deferred to the Phase-6 loop.** Build the catalog
  parser, the runner, the sandbox-run primitive, the Contract producer, and the
  dirty-state/state-snapshot helpers as one consolidated library
  (`orchestrator/evidence_runner.py`), with a clean API the Phase-6 loop drives.
  Prove it trustworthy the honest way Phase 4 proved its renderer: **tests that
  actually run real checks** (`python3 -m unittest`, `node`) under the sandbox
  against a fixture repo *and* against `~/ora`'s own shipped
  `.ora/evidence.yaml`. Ship `~/ora`'s catalog as a real, usable artifact.
  Optionally (OQ1) wire the *cheap* Contract producer live at the planning stage
  (one model call + a catalog read — **no check execution**), so a
  standard+ code turn's `context_pkg["evidence_contract"]` is populated even in
  Phase 5. **Do NOT auto-run checks at the gear terminal** — running a repo's
  test suite on every mutation-bearing chat turn is the "mandatory rigor makes
  Ora unusable" failure (§8/§17) *and* the loop that consumes the evidence is
  Phase 6. Text default byte-identical; additive; parity clean the way Phases
  1–4 were.
- **Architecture B (rejected) — auto-run the runner at the gear terminal on every
  `any_mutation` turn.** Fill the declared diff_validate lane live wherever the
  Phase-4 packet is built. Rejected: it runs a repo's checks on every
  mutation-bearing chat turn (latency + cost + the §17 unusability failure), it
  needs the produce→capture→verify→revise loop it does not have (there is no
  planning-produced Contract on a generic mutation turn → nothing declares
  *which* checks matter → the runner would run the whole catalog blindly, the
  exact §10 "which tests to run becomes a runtime decision" leak), and it changes
  live behaviour on every gear turn (parity risk) for a capability Phase 6 owns.
- **Architecture C (rejected) — catalog + Contract only; no runner in Phase 5.**
  Ship the catalog schema + the Contract producer, defer the runner to Phase 6.
  Rejected: it under-delivers §15's "build the one adapter … make it genuinely
  trustworthy" — the runner *is* the adapter; a catalog with no runner is a
  declaration nothing consumes. Phase 5 must ship the runner and prove it against
  real checks, even if the *live loop wiring* is Phase 6.

Everything below is Architecture A.

### P1 — The `.ora/evidence.yaml` catalog (platform-neutral schema, discovery, write-protection) (§10, amendment)
- **Schema — structured `argv` (shell-FREE) is the default; the shell is an
  opt-in escape hatch (amendment reqs 2 & 4).** A `cmd:` shell string is *not*
  the default form, because it bakes in a POSIX shell. Instead a check declares an
  **`argv` list** run via `subprocess.run(argv, shell=False)` — no `sh -c`, no
  shell grammar, platform-neutral by construction:
  ```yaml
  # .ora/evidence.yaml — what checks EXIST for this repo, plus how they must run (§7)
  checks:
    test:    { argv: [python, -m, unittest, discover, -s, orchestrator/tests],
               mutates: false, timeout: 1200, network: deny }   # shell-FREE, cross-platform
    lint:    { cmd: "eslint . 2>&1 | tee lint.log", shell: true,   # needs a real shell (pipe)
               mutates: false, timeout: 120, network: deny }       # → POSIX shell; Windows requires ORA_POSIX_SHELL, else REFUSED
    native:  { argv_posix: [make], argv_windows: [nmake],           # genuinely platform-divergent
               mutates: false, timeout: 300, network: deny }
  runner:
    working_dir: <repo-root>     # fixed; checks do not roam (a runtime_paths/pathlib path, never a hardcoded root)
    env:         isolated        # no ambient secrets (cross-platform clean env)
    network:     deny            # deny | local | allow — per-check `network` overrides
    redact:      by-sensitivity  # §7 axis: secret never emitted, sensitive scrubbed
    on_unknown:  gated           # a check not declared here is not auto-run
  ```
  Three execution forms, in portability-preference order: (1) **`argv`** (a list —
  shell-free, the recommended default; the runner resolves a bare `python`/`python3`
  interpreter to `sys.executable` so the `python` vs `python3` split never bites);
  (2) **`cmd` + `shell: true`** (only when a real shell feature is needed — a pipe,
  a glob — run under `/bin/sh` on POSIX and under **`ORA_POSIX_SHELL`** on Windows,
  which **refuses cleanly if unset, never falling back to `cmd.exe`**, reusing
  `bash_execute._posix_shell_path`, §1.4/amendment req 2); (3) **`argv_posix` /
  `argv_windows` (or `cmd_posix`/`cmd_windows`)** — explicit per-platform variants
  when a check *truly* differs (amendment req 4). Phase 5 **extends**
  `tool_events.validate_check_declaration` (additively) to accept `argv` *or* `cmd`
  (exactly one execution form; `shell:true` valid only with `cmd`; a per-platform
  variant valid only in a matched pair), adds `validate_runner_block(runner)`
  (working_dir present, `env ∈ {isolated, inherit}`, `network ∈ _EVIDENCE_NETWORK`,
  **`redact` present** — ⚖ code-F2, `on_unknown ∈ {gated, skip}`), and a top-level
  `parse_catalog(path) -> Catalog` (PyYAML `safe_load`, malformed → a loud parse
  error, never a silent empty catalog).
- **Discovery — env + `pathlib`, no shell, no hardcoded root (amendment reqs 1 &
  5).** The runner takes an **explicit `repo_root`** (Phase 6 / the Contract
  producer passes it). Standalone/CLI discovery order: explicit arg →
  `ORA_PROJECT_ROOT` (env, set when a project tool runs,
  `project_registry.py:917`) → a **`pathlib`-based upward walk** for
  `<root>/.ora/evidence.yaml` (not a `git rev-parse` subprocess — pure-Python and
  cross-platform; `git rev-parse --show-toplevel` stays an *optional* fast path,
  never the only mechanism). Every root derives from `runtime_paths` / the passed
  `repo_root`, never from the OS or the current user (amendment req 5).
- **Write-protection is already enforced** (§1.2) — `.ora/evidence.yaml` is a
  protected-config path (both the shell-redirect and file-tool write channels,
  §1.2), so an executor cannot rewrite the catalog to skip a check. Phase 5 relies
  on this; it adds no new write path (the catalog is authored by a human /
  committed as repo data, like `ora-project.json`). This is the §16-2 integrity
  anchor: the recipe is declared *independently of the executor*.
- **`~/ora` ships its own catalog** (repo data, not `orchestrator/` code), in the
  shell-free `argv` form so it is cross-platform:
  ```yaml
  checks:
    test:    { argv: [python, -m, unittest, discover, -s, orchestrator/tests],
               mutates: false, timeout: 1200, network: deny }
    js-test: { argv: [node, server/static/ora-visual-compiler/tests/run.js],
               mutates: false, timeout: 300,  network: deny }
  runner: { working_dir: <repo-root>, env: isolated, network: deny, redact: by-sensitivity, on_unknown: gated }
  ```
  `python` resolves to `sys.executable`; both checks run shell-free on macOS,
  Windows, and Linux. **They are shipped + parsed + validated, but NOT executed by
  the runner's own test suite** (⚖ seam-F5): running `discover -s orchestrator/tests`
  from inside `test_evidence_runner.py` would re-run that very file → recursion.
  The end-to-end execution proof runs a **fixture** repo carrying a trivial
  `argv: [python, -c, "..."]` check (shell-free, no recursion); the `~/ora`
  catalog proves discover+parse+validate only. **The exact commands to enshrine
  are OQ8.**

### P2 — The evidence runner + its declared constraints + how it is gated as an executor (§7)
`orchestrator/evidence_runner.py` (one consolidated module — the consolidated-
files house rule; the parser, runner, sandbox-run, Contract producer, and
dirty-state helpers are one cohesive unit, as `execution_packet.py` was for
Phase 4). Core function:
```
run_check(check: Check, runner_block: Runner, repo_root: str, *, worktree: str|None)
    -> CheckResult(name, cmd, exit_code, passed, stdout_tail_redacted,
                   duration_ms, enforcement_model, mutates, skipped, skip_reason)
```
- **The runner is itself an executor, gated through the Phase-1 manifest** (§7,
  the load-bearing rule). Before running a check, the runner resolves axes from
  the check's *declared* `mutates` + `network` and calls **`tool_events.gate(...,
  interactive_approver=None)` DIRECTLY** — **not** `dispatcher.dispatch()` (⚖
  seam-F2). The distinction is load-bearing: `dispatcher.dispatch()` inherits the
  dispatcher's permission mode, whose **default is `approve-each`
  (`dispatcher.py:364`)**, which installs an `input()` human prompt — a
  *programmatic* runner has no human at that prompt and would **hang/fail**.
  Calling `tool_events.gate` directly with `interactive_approver=None` sends a
  blocked check straight to the gate's **deny-and-queue** path (a Paused record,
  never a wait) — the queue-not-wait guarantee is then under the runner's control.
  Axes: `mutates:false` → `mutability:reversible_write` (**not `read`** — running
  a test suite *executes* repo code; the landed precedent `code_execute_axes`
  classifies even read-only code execution as `reversible_write`, §1.7/⚖ code-F6);
  `mutates:true` → `reversible_write` under worktree isolation; `network:deny` →
  `egress:none`; `env:isolated` → the check cannot reach secrets →
  `sensitivity:private`; `category:execute`; **`enforcement` = `orchestrated` for a
  check that RAN** (only an enforcing backend runs it — see the platform-backend
  bullet; a check whose constraints can't be enforced REFUSES rather than recording
  a weaker level, so there is no over-claim). So a declared low-risk check
  **passes** the gate. **Honoring `on_unknown: gated` is
  NEW runner logic, not an automatic gate consequence** (⚖ code-F7): `gate()`
  blocks only on `axes["unknown"]` being `True`; the catalog's `on_unknown` is a
  runner-block *policy* no existing code reads — so the runner must itself **map**
  an undeclared check (or one the sandbox can't honor) to `axes["unknown"]=True`
  before the gate call, and the gate's existing fail-closed-on-unknown then does
  the rest. Every check leaves a `tool-event` record — observed, not narrated
  (§16-3).
- **Declared constraints, enforced by the runner** (§7 — all seven, verified
  covered ⚖ spec-F6): a **timeout** (`subprocess` timeout, the check's `timeout`),
  a **fixed working_dir** (the runner never `cd`s out — checks do not roam), **env
  isolation** (a clean env — but see the HOME caveat below), a **network policy**
  (`deny` **enforced by the check's execution backend** — the macOS sandbox's
  `(deny network*)`, a declared `ORA_EVIDENCE_SANDBOX` wrapper, or native Linux
  `unshare -rn`; **a check whose backend cannot enforce its declared network policy
  REFUSES — it is never run unenforced**, see the platform-backend bullet), **secret
  redaction on
  captured output** (drive `by-sensitivity` through the existing `tool_events`
  redaction — secret never emitted, sensitive scrubbed; the runner caps + tails
  stdout, never inlines a full log — §9; note the code default
  `EVIDENCE_RUNNER_DEFAULTS` *omits* `redact`, so `validate_runner_block` must add
  it — ⚖ code-F2), a **defined exit-code handling** (`exit==0 → passed`, non-zero
  → failed, timeout → failed-with-reason; a runner crash is *observable*,
  `_note_failure`), and the explicit **`mutates` flag** (below). "An undeclared
  check is not silently run" is the `on_unknown` mapping above.
- **The sandbox — the read side is the load-bearing part, NOT a trivial write-root
  swap (⚖ BLOCKER seam-F1 / adv-F1 / spec-F1).** `code_execute._sandbox_profile`
  (`code_execute.py:84-105`) **denies all reads** under `$HOME` **and** every Ora
  private root — `WORKSPACE` (=`~/ora`, `runtime_paths.py:41`), `VAULT`,
  `CONVERSATIONS` (`_PRIVATE_DENY_ROOTS`, `code_execute.py:31`) — then re-allows
  reads of **only** scratch+tmp, and runs with `cwd=SCRATCH_DIR`. A repo under
  review (a worktree under `~/ora-worktrees`, or `~/ora` itself) lives **under a
  denied root**, so a verbatim reuse would **deny the check reading its own repo's
  source** — it can't run at all. So the runner's profile must, per run: (a)
  **re-allow `file-read*`** (and `file-write*` for `mutates:true`) under the
  **specific `repo_root`/worktree**, (b) **remove that path from the deny set**
  when it is nested under a denied private root, (c) keep **every OTHER** private
  root denied (`~/.ssh`, vault, conversations — the stdout-exfiltration close
  stays), and (d) set **`cwd=worktree`, not `SCRATCH_DIR`**. **Residual, stated
  honestly:** if `repo_root == ~/ora` itself, re-allowing `~/ora` reads re-exposes
  what the deny protected. **Note (⚖ Rev-1 PORT-1 code-claims):** a worktree under
  `runtime_paths.SCRATCH_DIR_STR` is **NOT** "outside the private-deny roots" —
  `SCRATCH_DIR` = `~/ora/scratch`, doubly nested inside both `~/ora` (a
  `_PRIVATE_DENY_ROOT`) and `$HOME`. So what makes the worktree readable is **the
  per-run re-allow of the specific worktree path** (re-allow `file-read*` under it,
  then keep every *other* private root — `~/.ssh`, vault, conversations — denied),
  **not** its location. A `clean_worktree` created at any path is fine as long as
  that exact path is the re-allowed subpath and the credential roots stay denied.
  **This read-side sub-design is a new open question (OQ11).**
- **Cross-platform execution backend — ENFORCE-OR-REFUSE, never run a check whose
  declared constraints the backend can't enforce (Rev-2, the judge's required
  direction).** A check RUNS only under a backend that **actually enforces its
  declared constraints (network policy first of all)**; where no enforcing backend
  is available, the check **refuses cleanly** (`skipped=true` + a `skip_reason`
  pointing to `ORA_EVIDENCE_SANDBOX`) — it is **never run under an unenforced
  `network: deny`** (honest labeling does not make an unenforced constraint true;
  §7 line 186, §15 line 394 "runs it mechanically under those constraints"). So a
  check that RAN is genuinely `orchestrated`; there is no "ran-but-unenforced" state.
  The three enforcing backends, in preference order:
  - **macOS `sandbox-exec` (native, no config) → `orchestrated`.** The generalized
    profile: network kernel-denied, writes kernel-confined to the worktree, reads
    re-allowed for the specific `repo_root` while other private roots stay denied
    (OQ11). The full §7 guarantee.
  - **A declared wrapper `ORA_EVIDENCE_SANDBOX` (a FIRST-CLASS SUPPORTED Phase-5
    path — the judge's option A) → `orchestrated`.** An operator-declared command
    that wraps the check with real network isolation — a container, WSL running
    `unshare -rn`, or Windows Sandbox — mirroring how `ORA_POSIX_SHELL` makes the
    shell path supported. This is **the** Windows enforcement route (and works on
    Linux too). The runner runs the check *through* the wrapper; the wrapper
    enforces the declared `network` policy, and the runner still supplies the
    credential-stripping clean env + worktree cwd. Validated at resolve time (must
    name a real executable, like `ORA_POSIX_SHELL`); an invalid value counts as no
    backend.
  - **Optional native Linux backend (`unshare -rn`, capability-probed) →
    `orchestrated`.** If an unprivileged network-namespace can be created, use it
    automatically so Linux CI needs no config; if the kernel disables unprivileged
    userns, fall through to `ORA_EVIDENCE_SANDBOX`-or-refuse. **Build-in-P5 vs
    require `ORA_EVIDENCE_SANDBOX` on Linux is OQ13.**
  - **No enforcing backend → REFUSE cleanly.** A `network: deny` / `network: local`
    check on a platform with no native backend and no declared `ORA_EVIDENCE_SANDBOX`
    is refused with a clear message (declare `ORA_EVIDENCE_SANDBOX` / run where a
    native backend exists) — the amendment's "refuse cleanly when unavailable,"
    applied to enforcement, not just the shell.
  - **The credential-stripping clean env + disposable worktree are DEFENSE IN DEPTH
    on every backend, not a substitute for enforcement.** The runner builds its own
    clean env (the `code_execute._clean_env` pattern — strip API keys / tokens /
    **`SSH_AUTH_SOCK`** / keychain; platform-aware home/temp — see the env bullet;
    it must **NOT** delegate to `bash_execute._clean_env`, which leaks
    `SSH_AUTH_SOCK` — ⚖ Rev-1 PORT-1; it reuses only `bash_execute._posix_shell_path`,
    the resolver). These reduce blast radius but do not themselves enforce network
    denial (⚖ Rev-1 PORT-5), which is why an enforcing backend is required to run.
  - **Other refusals (amendment req 2 / §7):** a `shell:true` check with no
    `ORA_POSIX_SHELL` refuses (never `cmd.exe`); a `network: allow` check refuses
    **everywhere** (no egress-logging proxy, §7); a `mutates:true` check refuses in
    the non-`clean_worktree` dirty modes (P2 mutates bullet).
  - **"Runs on Windows," reconciled (the judge's "revisit what it means"):** the
    runner *machinery* (parse / validate / discover / Contract producer / git-state
    snapshot — all pure Python) runs on Windows unconditionally. **Check EXECUTION
    on Windows runs under a declared `ORA_EVIDENCE_SANDBOX`** (WSL / container /
    Windows Sandbox — a normal dev-Windows capability, exactly as `shell:true`
    needs `ORA_POSIX_SHELL`); without it, network-constrained checks refuse cleanly.
    The shipped `~/ora` catalog (`python`/`node`, both `network: deny`) runs
    natively on macOS + Linux (via `sandbox-exec` / `unshare`), and on Windows via
    `ORA_EVIDENCE_SANDBOX`. No check ever runs unenforced.
  - **Path roots are `runtime_paths` / `tempfile` / `pathlib`, never hardcoded**
    (amendment reqs 1 & 5): the disposable worktree is created with
    `tempfile.mkdtemp(dir=runtime_paths.SCRATCH_DIR_STR)` (or a `runtime_paths`-
    derived worktrees dir) — never `/tmp`, never `/Users/...`, never the repo
    location; `trace_dir` already flows from `pipeline_trace` (runtime_paths).
  - **Reuse mechanics (OQ3).** Generalize `code_execute._sandbox_profile` + the
    `subprocess.run` core into a shared helper both `code_execute(code)` and
    `run_check(argv|cmd)` call (reuse-over-parallel), parameterized by the
    `repo_root` allow-list AND the platform backend. Re-run `code_execute`'s
    existing sandbox tests (`test_dispatcher_gate.py:497-525`); a separate copy
    avoids the security-review touch but duplicates a hardened profile (drift risk).
- **`env: isolated` clean-env — the credential-stripping one, POSIX-shaped, needs
  a Windows variant (⚖ seam-F4 + Rev-1 PORT-1/PORT-3 + the amendment).** The runner
  generalizes **`code_execute._clean_env` (`code_execute.py:108-116`)** — the
  prevention-by-absence idiom — **NOT `bash_execute._clean_env` (`:682-691`)**,
  which is a leaky allowlist that preserves `HOME`/`USER`/`SSH_AUTH_SOCK` (naming
  which of the two is load-bearing: only the `code_execute` variant delivers the
  defense-in-depth "no credentials present" property on every backend).
  `code_execute._clean_env`
  keeps only `PATH`/`LANG`/`LC_ALL` and sets `HOME`/`TMPDIR` — **POSIX var names**.
  On Windows, a spawned process reads `USERPROFILE` (not `HOME`), `TEMP`/`TMP` (not
  `TMPDIR`), and needs `SystemRoot`/`COMSPEC`/`PATHEXT` to even start (the exact
  Phase-1 residual the handoff flagged). So the runner's clean env is
  **platform-aware**: POSIX → `HOME`/`TMPDIR` (as today); Windows → `USERPROFILE`/
  `TEMP`/`TMP` + `SystemRoot`/`COMSPEC`/`PATHEXT`, still stripped of API keys /
  tokens / credentials (the prevention-by-absence invariant holds on both). `env`
  is also a **provisional tuning surface** (`env ∈ {isolated, inherit}`): a real
  `node`/`npm` check may need a real/dedicated home + a config-dir read-allow. The
  `~/ora` catalog (`python -m unittest`, stdlib) needs neither, so it validates the
  `isolated` default cross-platform.
- **`mutates: true` checks** (§7 "runs under the same sandbox discipline as
  execution"; §10) — run **only under `clean_worktree` isolation** (a fresh
  worktree, so mutations are confined + undoable + the diff stays exact). In
  `review_dirty_diff` and `continue_user_changes`, a `mutates:true` check is
  **refused and recorded with a loud skip reason** — the runner must not mutate a
  working tree the user owns. **The refusal is enforced by the RUNNER pre-flight
  (refuse + record), not by `tool_events.gate`** (which is egress/mutation-tier
  blind for a `reversible_write` — ⚖ seam-F7); the runner decides before it ever
  builds the gate call. This is the "how are mutates:true checks handled" answer
  (OQ4).
- **Network policy — `deny` runs ONLY under an enforcing backend, else refuses;
  `local`/`allow` refused in P5** (Rev-2 + ⚖ spec-F2 / adv-F3 / seam-F7). A
  `network: deny` check runs **only** where the execution backend actually enforces
  denial (macOS `sandbox-exec` / declared `ORA_EVIDENCE_SANDBOX` / native
  `unshare -rn`); with no enforcing backend it **refuses cleanly** — never run
  unenforced (the P0 correction). **`network: local`** can't be honored — the mac
  sandbox does a blanket `(deny network*)` (`code_execute.py:97`) with no
  localhost/port scoping, and no wrapper is guaranteed to scope it — so `local` is
  **refused** in P5 (stays a valid *catalog* value, spec §10, but out-of-scope-to-run
  until a scoping backend exists). **`network: allow`** is refused **everywhere**
  (no egress-logging proxy, §7). All refusals are enforced by the runner pre-flight
  (map → `unknown` → gate), not by the egress-blind gate. (OQ5 folds into OQ13, the
  Windows/Linux enforcement policy.)

### P3 — The catalog-vs-Evidence-Contract boundary, stated plainly (§10) + the Contract producer at planning (§8/§16-2)
**Said so no future reader misreads it (§10 asks for this verbatim):**
> The **catalog (`.ora/evidence.yaml`)** declares *what checks exist and how they
> must run* — a repo-level, write-protected, executor-independent fact. The
> **Evidence Contract** is *task-specific and produced at planning time*: which
> catalog checks are **relevant to this task**, what **bespoke probe** proves
> *this* feature works, and what result counts as **sufficient**. The catalog
> can only list standard checks; it cannot know which matter for *this* task.
> Conflating them is how the loop's integrity quietly leaks — if the executor
> picks its own checks at runtime, self-reporting sneaks back in one level up.

- **The Contract producer IS a live Phase-5 deliverable, wired at the planning
  stage (spec §15/`spec:394` REQUIRES it — resolves the judge's under-scoping).**
  `apply_evidence_contract(context_pkg, instruction, risk_tier, *, invoker,
  repo_root=None) -> directive` — the sibling to `risk_gate.apply_criteria`
  (§1.5), called at the **same** planning point (`boot.py:9304`,
  `server.py:2846`), standard+ only (light → none; the instruction is the
  criterion, evidence is the catalog checks only — §8). It runs one planning-model
  call (sidebar slot, injected → testable/offline-safe) that, **without attempting
  the task**, proposes `bespoke_probes` (what would demonstrate *this* feature — a
  description in Phase 5, executed in Phase 6) and states `sufficiency`. Stashed on
  `context_pkg["evidence_contract"]`; an `evidence_contract` tool-event recorded.
  On genuine failure: `HOLD:` (high-risk+) / `WARN:` (standard) — never a silent
  light fall-through (mirrors condition 6). **This is what makes §16-2 real
  (Phase 5's headline commitment): the recipe is authored at a step prior to and
  separate from execution.**
- **Repo-root discovery + the repo-less Contract (resolves the "no `repo_root` at
  the planning seam" blocker — ⚖ seam-F3 / judge-P1).** The producer attempts, in
  order: an explicit `repo_root` arg → `ORA_PROJECT_ROOT` (env) → a `pathlib`
  upward walk from cwd for `.ora/evidence.yaml` (no shell, cross-platform). **If a
  catalog is found**, the Contract also selects `required_standard_checks ⊆
  catalog.checks`. **If none is found** (the common general-chat case), it emits a
  **repo-less Contract** — `bespoke_probes` + `sufficiency`, `required_standard_checks:
  []` — so the planning stage *always* emits a Contract (§15 met) rather than being
  silently skipped. The CONTRACT runs live at planning in P5; only the **runner
  (check execution)** stays library-driven-by-Phase-6. **Where the producer lives
  is OQ6** — recommend `evidence_runner.py` (cohesive), called from the same
  planning wiring, not `risk_gate.py`.
- The Contract is *declared independently of the executor* (§16-2): the planning
  step, not the implementing step, sets it — the same separation `apply_criteria`
  already enforces for acceptance criteria.

### P4 — Filling the diff+validate lane: `generated_by` / `result` / `sufficient` (§4, §5, §9)
The runner's output fills the **declared** diff_validate lane (the one
`route_lanes` already emits for `any_mutation`):
- `generated_by` = the **declared** `cmd`(s) actually run (from the catalog, tied
  to the Contract's `required_standard_checks`) — so a lane result ties back to a
  *declared catalog command*, never an executor self-report (the §9/§10 reason the
  field exists).
- `result` = the per-check `CheckResult`s (name, exit, passed, redacted stdout
  tail, duration, `enforcement_model` = `orchestrated` for a check that RAN under an
  enforcing backend / absent for a refused check that carries `skipped` +
  `skip_reason`, `mutates`), plus a `delta.ref` to the `git diff` written
  trace-local (§9: large artifacts referenced, never inlined).
- `sufficient` — **judged against the Evidence Contract's `sufficiency`, never
  self-asserted** (§10/§16-2). The runner sets `sufficient=True` only when
  **every** `required_standard_check` ran and `passed` (and the bespoke probe, once
  Phase 6 executes probes, passed); any unfilled, failed, skipped, or gated check
  → `sufficient=False`, consistent with Phase 4's `lane_is_sufficient` (`None →
  not sufficient`) and `all_evidence_sufficient` (empty → not passed). **The
  load-bearing sentence, landed in the code comment and the packet:** *a green
  run means nothing broke that you knew to check — it does NOT mean the executor
  solved the right problem*; the wrong-problem catch is the planning-stage
  acceptance criteria (Phase 2) + the verify stage (Phase 6). `sufficient`
  answers "did the declared evidence pass," not "was this the right thing."
- Phase 5 fills **only** the `diff_validate` lane (§15 — the one adapter used
  daily, made trustworthy first). The `collect_provenance` lane stays declared-
  but-unfilled (its claim-to-source map is Phase 8); other lanes (`run_observe`,
  `render_inspect`, `deploy_probe`) are not built (Phase 8). "Consulted ≠ used
  correctly" (§4) is respected by *not* pretending the event log alone is
  provenance evidence.

### P5 — The three dirty-state modes + `state_before`/`state_after` snapshot forms (§9, §11)
The runner's git-state helper (mirroring `engram_promotion._git`) fills the
Phase-4-reserved `execution.mode` / `state_before` / `state_after`:
- `clean_worktree` — `git worktree add` a fresh branch off the base;
  `state_before` = base commit SHA + tree hash; execution runs in the worktree;
  `state_after` = the worktree's post-run tree hash (or a throwaway commit SHA);
  `delta.ref` = `git diff <before>..<after>` → trace dir. The isolated, exact-diff
  mode; the only mode that may run `mutates:true` checks. The worktree is the
  §13 "inspectable, unmerged branch" the escalation path (Phase 6) links to —
  never a dangling untracked tree.
- `review_dirty_diff` — no worktree; `state_before` = HEAD SHA + a hash of the
  pre-existing uncommitted diff; `state_after` = current working-tree hash;
  `delta.ref` = `git diff` of the uncommitted change under review. `mutates:true`
  checks refused (P2).
- `continue_user_changes` — `state_before` = HEAD SHA + a snapshot/stash-ref hash
  of the user's dirty floor (the user's work is the baseline, **never reverted**);
  `state_after` = current tree; `delta.ref` = the diff *above* the user baseline
  (only the executor's addition). `mutates:true` checks refused (P2).
All snapshot forms are git SHAs / tree hashes (small, flat — §9), the diff always
a **ref**, never inlined. **Two-tree clarification (⚖ seam-F10):** `trace_dir`
(`~/ora/data/pipeline-traces/…`) and the `repo_root`/worktree under review are
**distinct trees**. The git-state helper (SHAs, `git diff`) and the diff-writer
run **OUTSIDE the sandbox** — an `engram_promotion`-style `subprocess` against the
repo, writing the diff into `trace_dir` — while the *checks* run INSIDE the
sandbox and can only write to the worktree + capture stdout. So the sandbox's
worktree write-confinement and the diff landing trace-local are not in tension.
Phase 5 builds the state-snapshot + mode machinery and its unit tests; the
*selection* of which mode a live turn uses is the Phase-6 loop's call (Phase 5
defaults to `review_dirty_diff` as the least-assuming mode when a driver names
none — OQ7).

### P6 — "Green run ≠ right problem" — AND "green ≠ honest test" — landed in code + packet (§10, §12, §16-2)
This is not a doc line — it is enforced by structural facts Phase 5 ships:
1. `sufficient` is set from **actual check exit codes vs the Contract's declared
   required set** (P4), never from the executor's say-so, and an unfilled/failed/
   skipped check is never truthy (P4, reusing Phase-4's tri-state invariant).
2. The recipe — **which checks run** — is **declared independently of the
   executor**: the catalog is write-protected (§1.2), and the Contract is
   produced at the planning step, not the implementing step (P3). **But state the
   honest limit (⚖ adv-F2):** the write-protected catalog fixes the check's
   **command string** and the sandbox **bounds its side effects** — it does
   **not** make a passing check *trustworthy* when the executor authored the code
   the command *invokes* (a `package.json` test script or a repo `.py` the model
   edited during execution). That is exactly §12's grading-your-own-homework risk,
   and it is **not** closed by the runner alone — it is closed by acceptance
   criteria set at planning (§16-1) **and the verify stage authoring additional
   adversarial acceptance tests** (Phase 6). So Phase 5's runner delivers "the
   declared checks ran, mechanically, under bounded side effects, and passed" —
   which is *necessary* but explicitly *not sufficient* for "the task is done
   right."
3. The packet + the renderer keep the mechanical evidence and the producer claim
   **separated and ordered** (Phase 4's `render_for_review`), so a green lane
   next to a fluent claim can't be read as "the right thing was built" — the
   renderer already labels the claim unverified. Phase 5 adds one line to the
   `evidence_runner` module docstring + the packet's evidence block:
   *"`sufficient` means the declared checks passed — not that the task was the
   right one (that is the acceptance criteria + verify stage, §16-1/§12), and not
   that the checks themselves are honest if the executor wrote the code they
   run."*

### P7 — Custom-path reach + MSI deferral (§15 Phase-0), stated not silent
Per §1.8: the runner auto-runs on **no** terminal path and touches **none** of
the MSI custom paths. `~/ora` core holds the generic runner + catalog mechanism;
`~/ora` ships its own catalog as repo data. MSI's own `.ora/evidence.yaml` +
adapter wiring is **Phase 8** (project-plugin convention: MSI-specific code stays
in `~/sites/mainstreetindependent/ora-project/`). **Deliverable of P7:** this
enumeration recorded in the packet + module docstring, so the Phase-8 MSI adapter
has an exact worklist and no path silently reviews prose the old way.

---

## 3. Design consequences the judge should weigh explicitly

1. **What runs live in P5 vs what is loop-driven.** *Live on real turns:* the
   **Contract producer** at the planning stage (spec §15 requires it — P3, resolved
   from the judge's under-scoping; it is cheap — one model call + an optional
   catalog read, no check execution). *Real & usable, driven by tests + Phase 6:*
   the catalog (a genuine `~/ora` artifact), the runner (proven by tests that run
   real `argv` checks under the platform backend), the dirty-state/state-snapshot
   machinery. *Not auto-run at the gear terminal:* the **runner** (check execution)
   — there is no live plan→execute→capture loop until Phase 6; the runner fires on
   no live pipeline path in P5. The split is clean: **Contract = live at planning;
   check execution = library, Phase-6-driven.**
2. **The runner is a genuine new executor and MUST pass the same gate (§7) —
   via a DIRECT `tool_events.gate` call, not `dispatcher.dispatch()`.** The
   adversarial pass corrected the earlier "the gate call is the same either way"
   hedge (⚖ seam-F2): `dispatcher.dispatch()` inherits the dispatcher's
   permission mode, whose **default is `approve-each` (`dispatcher.py:364`)** and
   which installs an `input()` human prompt — a *programmatic* runner would hang
   there. So the runner calls `tool_events.gate(action, axes,
   interactive_approver=None)` directly, sending a blocked check to the
   deny-and-queue path (never a wait). It invents no bypass — an ungated runner is
   the §7 back door. It must also **map** an undeclared / unsandboxable check to
   `axes["unknown"]=True` itself (honoring `on_unknown` is new runner logic, not
   an automatic gate consequence — ⚖ code-F7).
3. **The catalog being write-protected is load-bearing, and it already holds.**
   `.ora/evidence.yaml ∈ _PROTECTED_BASENAMES` (Phase 1) → an executor cannot
   edit the catalog to skip a check. Phase 5 relies on this; if the judge wants
   belt-and-suspenders, the runner can additionally re-parse the catalog from
   `HEAD` (git-committed form) rather than the working tree, so a mid-run edit
   can't take effect — flag if desired (a possible P2 hardening).
4. **`sufficient` is a mechanical aggregate against a declared bar, not a
   quality judgment.** It answers "did the declared checks pass," judged against
   `contract.sufficiency`. The "right problem" question is out of the lane's
   scope by construction (P4/P6). This is the §10/§16-2 guard, and it is the
   sentence the packet must state so no reader over-reads a green lane.
5. **ENFORCE-OR-REFUSE, not run-and-label (the judge's Rev-2 direction, and the
   §7/§16-2 integrity boundary).** A check runs **only** under a backend that
   actually enforces its declared constraints (network first) — macOS
   `sandbox-exec`, a declared `ORA_EVIDENCE_SANDBOX` wrapper, or native Linux
   `unshare -rn` — recording `enforcement_model: orchestrated`; a check whose
   backend cannot enforce its declared policy **REFUSES cleanly** (`skipped` +
   `skip_reason`), it is **never run under an unenforced `network: deny`**. Honest
   labeling does not make an unenforced constraint true — so there is no
   "ran-but-`boundary_only`" state for a network-constrained check. This is
   distinct from the packet's `in_harness` core-gear value, and it is the §7
   guarantee boundary Phase 5 must not blur.
7. **Portability is release-blocking; "runs on Windows" means the machinery runs
   everywhere + check execution runs under a declared enforcing backend (the
   amendment + judge Rev-2).** No macOS-only path: the runner *machinery* (parse /
   validate / discover / Contract / git-state — pure Python) runs on every
   platform; *check execution* runs under macOS `sandbox-exec` / a declared
   `ORA_EVIDENCE_SANDBOX` (WSL / container / Windows Sandbox — the supported
   Windows route, like `ORA_POSIX_SHELL` for the shell) / native Linux
   `unshare -rn`, else refuses cleanly. Catalog checks are shell-free `argv` by
   default; all path roots derive from `runtime_paths`/`tempfile`/`pathlib`;
   Windows behaviour is tested by simulation (§5), not skipped green. The §7
   Portability section enumerates every cross-platform surface, the tests, and the
   remaining assumptions.
6. **Reuse vs a security-review touch — and the sandbox read-side is the real
   work.** The runner's sandbox should generalize `code_execute`'s hardened
   profile (reuse-over-parallel house rule), which means touching a
   security-reviewed file. But the adversarial pass established this is **not a
   trivial write-root swap** (⚖ BLOCKER seam-F1/adv-F1/spec-F1): `code_execute`
   denies **all reads** under `$HOME` + `~/ora` + vault + conversations, so a
   check can't read its own repo unless the profile **re-allows reads of the
   specific `repo_root`/worktree** while keeping the other private roots denied
   (P2). That parameterization is a genuine refactor of the profile (a
   `repo_root` allow-list argument + `cwd=worktree`). The safety comes from the
   **per-run re-allow of the worktree's EXACT path** (while `~/.ssh`/vault/
   conversations stay denied), **not** from the worktree's location — `SCRATCH_DIR`
   is itself inside `~/ora`/`$HOME`, so "outside the private-deny roots" is not an
   available shortcut (P2 read-side note / OQ11). Recommend the shared-helper
   extraction with a focused re-test of `code_execute`'s existing sandbox tests
   (`test_dispatcher_gate.py:497-525`); a clean copy avoids the touch but
   duplicates the hardened profile (drift risk).

---

## 4. Scope boundary — what Phase 5 deliberately does NOT do
- **No full loop.** No produce→capture→verify→revise wiring, no dual-verify-on-
  evidence, no findings routing, no revision router, no escalation-with-linked-
  branch (Phase 6). The runner is a library the Phase-6 loop drives.
- **No auto-run of CHECK EXECUTION at the gear terminal** (Architecture A). The
  *runner* fires on no live pipeline path in Phase 5 (the loop is Phase 6); parity
  stays clean, text default byte-identical. **Distinct from the Contract producer,
  which DOES run live at the planning stage** (spec §15 requires it — P3): planning
  is not execution, it is cheap, and it is byte-additive to the existing
  `apply_criteria` planning step.
- **Only the diff+validate lane is filled** (§15). `collect_provenance` stays
  declared (Phase 8's claim-to-source map); `run_observe` / `render_inspect` /
  `deploy_probe` are not built (Phase 8).
- **No claim-to-source map, no precise `source_read` labeling** (Phase 8).
- **No MSI catalog / no MSI adapter wiring** (Phase 8). `~/ora` ships only its own
  catalog as repo data; the mechanism stays project-agnostic (§1.8/P7).
- **No egress-logging proxy** — `network: allow` checks are refused/gated, not run
  un-proxied (§7, P2). Building the proxy is out of scope.
- **No new durable persistence** — evidence + diffs are written **trace-local**
  (the same trace dir the Phase-4 packet uses), inheriting stealth/no-packet;
  durable tiered persistence + redaction-before-durable-write is Phase 7.
- **No before-clock change.** The risk tier, the irreversible hold, and the
  criteria pass are Phase 2 and untouched; the Contract producer is an additive
  planning sibling, not a change to the risk gate.
- **No change to `execution_packet.py`'s live behaviour** — the fill is additive
  (an optional param / a helper, §1.1); a P4 turn with no runner still builds a
  declared-empty-lane packet exactly as today.

---

## 5. Test + parity plan
- **New unit tests** (a new `orchestrator/tests/test_evidence_runner.py` +
  additions to `test_execution_packet.py`):
  - **catalog**: `parse_catalog` on a valid `.ora/evidence.yaml`; malformed YAML →
    a loud parse error (never a silent empty catalog); `validate_check_declaration`
    (existing) + the new `validate_runner_block` reject a bad `network`/`env`/
    missing `cmd`; the shipped `~/ora/.ora/evidence.yaml` parses + validates.
  - **runner — behaviour tested on ALL platforms; only the KERNEL-sandbox proof is
    mac-gated (the P0 amendment fix — macOS-only green is NOT enough).** *Cross-
    platform (run on mac/Linux CI, no skip):* a fixture `argv` check that exits 0 →
    `passed`, exit 1 → failed, timeout → failed-with-reason; `argv` runs
    `shell=False`; a bare `python`/`python3` `argv[0]` resolves to `sys.executable`;
    a secret in the env is absent (clean env — cross-platform); captured output is
    redacted by-sensitivity; exit-code handling is identical on every platform. *Mac-
    gated (the kernel guarantee only):* under `sandbox_available()`, a `network:deny`
    check cannot reach the network and reads outside the repo are denied (mirrors
    `code_execute`'s sandbox regressions, `test_dispatcher_gate.py:497-525`).
    *Enforce-or-refuse (run on mac/Linux CI):* with **no** enforcing backend
    available (neither `sandbox_available()` nor `ORA_EVIDENCE_SANDBOX` nor native
    `unshare`), a `network:deny` check **REFUSES cleanly** (`skipped=true`,
    `skip_reason` names `ORA_EVIDENCE_SANDBOX`) — it is **never run unenforced**;
    with a declared (mocked) `ORA_EVIDENCE_SANDBOX`, the check runs *through* the
    wrapper and records `enforcement_model: orchestrated`.
  - **portability (amendment req 6 — Windows-behaviour simulation, run on
    mac/Linux CI; mirrors `test_portability.py`'s `ntpath`/`PureWindowsPath` +
    platform-monkeypatch pattern):** with `os.name`/`sys.platform` simulated as
    Windows — (a) with no `ORA_EVIDENCE_SANDBOX`, a `network:deny` check **refuses
    cleanly** (never runs unenforced, never records `orchestrated`); with a declared
    `ORA_EVIDENCE_SANDBOX` it runs through the wrapper; (b) a `shell:true` check
    with no `ORA_POSIX_SHELL` is **refused cleanly** (asserts the refusal message,
    asserts **no `cmd.exe`** fallback); with a declared shell it runs; (c) a
    per-platform check picks `argv_windows` under simulated-nt and `argv_posix`
    otherwise; (d) a Windows-style `repo_root` (`PureWindowsPath`,
    `C:\\Users\\...\\repo`) flows through the sandbox allow-list logic; (e) a
    static scan asserts **no hardcoded `/tmp` / `/Users` / `/private`** — the
    worktree path derives from `runtime_paths`/`tempfile` (amendment reqs 1 & 5).
  - **gate integration**: a `mutates:false, network:deny` check passes the gate; a
    `network:allow` check is refused/gated; an undeclared check (`on_unknown:
    gated`) is not run; every run leaves a tool-event.
  - **`mutates:true`**: runs only under `clean_worktree`; refused with a loud skip
    reason under `review_dirty_diff` / `continue_user_changes`.
  - **dirty-state + state snapshots**: each mode's `state_before`/`state_after`
    are git SHAs/tree-hashes; `delta.ref` is a path, not an inlined blob;
    `continue_user_changes` never reverts the user floor; `clean_worktree` adds +
    (in teardown) removes the worktree (the workflow-discipline primitive).
  - **Contract producer**: standard+ produces `{required_standard_checks ⊆
    catalog, bespoke_probes, sufficiency}` on `context_pkg`; light → none;
    no-invoker → no-op (offline-safe); genuine failure → `HOLD:`/`WARN:` (never
    silent light).
  - **lane fill + sufficiency**: a filled diff_validate lane carries
    `generated_by` = the declared cmds, `result` = the CheckResults,
    `sufficient=True` only when every required check passed; a failed/skipped/
    gated check → `sufficient=False`; the empty-≠-passed invariant
    (`all_evidence_sufficient`) still holds; `render_for_review` shows a filled
    lane as "sufficient (via <cmd>)" and a failed one as "INSUFFICIENT," never a
    bare green check.
  - **"green ≠ right problem" / "green ≠ honest test"**: the docstring/packet
    sentence (P6) is present; a `sufficient=True` lane with no acceptance criteria
    still renders the loud "NO ACCEPTANCE CRITERIA DECLARED" banner. **Known P5
    behaviour to state, not paper over (⚖ adv-F4):** the renderer reads criteria
    from `packet.planning.converged_brief.acceptance_criteria`
    (`execution_packet.py:251`), but `build_execution_packet` hardcodes
    `planning=None` (`:400`) while `apply_criteria` stashes on a **different**
    location, `context_pkg["acceptance_criteria"]` (`risk_gate.py:952`). So in P5
    the banner fires **unconditionally** — the criteria *exist* but the packet
    never carries them. Two options (OQ12): a **small P5 win** — wire
    `context_pkg["acceptance_criteria"]` into `packet.planning` at construction so
    a filled lane can be judged against a real setpoint; **or** leave the
    planning-block wiring to Phase 6 and record the unconditional banner as a known
    gap.
  - **additive/back-compat**: existing `test_execution_packet` /
    `test_risk_gate` / `test_tool_events` shape assertions still pass; a P4-style
    turn with no runner builds a declared-empty-lane packet unchanged.
- **Parity:** run with `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`; capture a
  pre-edit baseline in the SAME implementation worktree, diff sorted FAIL/ERROR
  name lists pre-vs-post, target **zero new failures** against the 22F/5E
  environmental baseline. Note: the runner's real-check tests run a fixture
  `argv` check (a trivial `python -c`) *under the backend*, not the live suite —
  they must not recurse into the outer suite (a fixture repo, never `discover -s
  orchestrator/tests` from inside the runner tests).
- **Adversarial pre-check** before the review packet: a small Workflow over ONLY
  the changed logic (catalog parse/validate, gate axes for each mutates/network
  combination, sandbox write-confinement + network-deny, mutates:true refusal in
  dirty modes, sufficiency = declared-required-all-passed, state-snapshot
  correctness, the additive lane-fill); verify each finding against the code
  myself (the majority vote under-reports); fold the real ones; re-run focused +
  full parity; resubmit with diff + parity evidence.

---

## 6. Open questions for the judge
1. **How live should Phase 5 go? (the headline — now split by piece, resolving the
   judge's under-scoping.)** *Committed (spec §15 requires it — P3):* the **Contract
   producer runs LIVE at the planning stage** in P5 (standard+), the cheap sibling
   to `apply_criteria`. It is repo-root-aware (explicit → `ORA_PROJECT_ROOT` →
   `pathlib` walk-up) and, when no catalog is discoverable, emits a **repo-less
   Contract** (bespoke probe + sufficiency, `required_standard_checks: []`) so the
   planning stage *always* emits a Contract — it is never silently skipped for lack
   of a `repo_root`. *Library, Phase-6-driven:* the **runner (check execution)**
   auto-runs on no live terminal path in P5 (the loop is Phase 6), proven by tests
   that run real `argv` checks against a **fixture** under the platform backend.
   *Rejected as default:* auto-run the runner at the gear terminal (Architecture B)
   — the §17 unusability + parity risk. So: **Contract = live; execution = library.**
2. **Where is `.ora/evidence.yaml` discovered?** *Recommended:* explicit
   `repo_root` arg (Phase 6 / the Contract producer passes the tree it operates
   on); standalone order = explicit → `ORA_PROJECT_ROOT` → a **`pathlib` upward
   walk** for `.ora/evidence.yaml` (`git rev-parse --show-toplevel` only as an
   optional fast path, never the sole mechanism — cross-platform, amendment req 1).
   For P5, ship `~/ora`'s catalog and test against it. Alternative: a fixed
   `<repo-root>/.ora/evidence.yaml` only, no walk-up.
3. **How is the runner sandboxed CROSS-PLATFORM (ENFORCE-OR-REFUSE)?**
   *Recommended:* a platform `_sandbox_backend` that **enforces the declared network
   policy or the check refuses** — **macOS** generalizes
   `code_execute._sandbox_profile` (network deny; writes confined to the worktree;
   **reads of the repo re-allowed** while other private roots stay denied, OQ11;
   `cwd=worktree`; clean env) → `orchestrated`; a **declared `ORA_EVIDENCE_SANDBOX`
   wrapper** (container / WSL+`unshare` / Windows Sandbox) → `orchestrated` (the
   first-class Windows path); **native Linux `unshare -rn`** (capability-probed) →
   `orchestrated`; **no enforcing backend → the check REFUSES cleanly** (never runs
   unenforced). The clean env + disposable worktree are defense-in-depth on every
   backend, not a substitute for enforcement. Shared sandbox helper both
   `code_execute` and `run_check` use (reuse-over-parallel); re-run
   `test_dispatcher_gate.py:497-525`. *Alternative:* a fresh sandbox copy inside
   `evidence_runner.py` (no security-review touch, at the cost of a duplicated
   profile — drift risk).
4. **How are `mutates: true` checks handled?** *Recommended:* run only under
   `clean_worktree` isolation; refuse (gate + loud skip reason) in
   `review_dirty_diff` / `continue_user_changes` (never mutate a tree the user
   owns). Alternative: always force a throwaway worktree copy even in the dirty
   modes (heavier, but lets a mutating check run in review_dirty_diff).
5. **Network policy in P5.** *Recommended:* run **`network: deny` checks only**;
   refuse **both** `network: local` and `network: allow` (⚖ spec-F2/adv-F3) — the
   mac sandbox does a blanket `(deny network*)` with **no localhost scoping**, and
   no egress-logging proxy exists (§7). `local` stays a valid *catalog* value (the
   spec's §10 example uses it) but is out-of-scope-to-*run* until the sandbox
   gains localhost scoping (a flagged future item). The refusal is enforced by the
   **runner** (pre-flight → map to `unknown` → gate/queue), not by the egress-blind
   gate. Alternative: allow un-proxied egress (rejected — reintroduces the §7 blind
   spot).
6. **Contract producer location + wiring.** *Recommended:* `apply_evidence_contract`
   in `evidence_runner.py` (cohesive with the runner), called at the same planning
   point as `apply_criteria` (standard+ only). Alternative: put it in `risk_gate.py`
   next to `apply_criteria` (co-located planning), or keep it a pure library the
   Phase-6 planning stage calls (no live wiring in P5).
7. **Default dirty-state mode when a driver names none.** *Recommended:*
   `review_dirty_diff` (least-assuming — evaluates what is already there, demands
   no clean tree, mutates nothing). Alternative: refuse to run without an explicit
   mode (safest, but less ergonomic for the Phase-6 loop).
8. **`~/ora`'s own check set (shell-free `argv`, cross-platform).** *Recommended:*
   `test` = `argv: [python, -m, unittest, discover, -s, orchestrator/tests]`,
   `js-test` = `argv: [node, server/static/ora-visual-compiler/tests/run.js]`.
   Confirm the canonical set + timeouts (the full Python suite is ~3721 tests → the
   1200 s timeout is a provisional tuning constant, flagged).
9. **The lane-fill attach seam.** *Recommended:* a free-standing
   `fill_evidence_lanes(packet, results)` helper (touches `execution_packet.py`
   least) OR an additive `evidence_results=None` kwarg on `build_execution_packet`
   (absent → Phase-4 behaviour). Either is additive/back-compat; recommend the
   helper.
10. **Provisional tuning surfaces** (flagged per house rule, retunable, not
    calibrated): the `~/ora` check timeouts; the stdout tail cap; the
    `on_unknown`/`env`/`network` enum values; the default dirty-state mode; the
    `sufficient` aggregation rule (all-required-passed). None are empirically
    calibrated.
11. **Sandbox read-side approach (raised by the adversarial pass, ⚖ BLOCKER
    seam-F1/adv-F1/spec-F1).** The check must read its own repo, but
    `code_execute`'s profile denies all reads under `$HOME`/`~/ora`/vault/
    conversations. *Recommended:* the runner's profile takes a per-run
    `repo_root` allow-list — re-allow `file-read*` (and `file-write*` for
    `mutates:true`) under the specific repo tree, remove it from the deny set,
    keep every other private root denied, `cwd=worktree`. **Note (Rev-2, correcting
    the earlier claim):** `SCRATCH_DIR` is INSIDE `~/ora`/`$HOME` (§P2 read-side
    note), so a worktree "under scratch" is **not** outside the private-deny roots —
    what makes the worktree readable is the **per-run re-allow of its exact path**
    (then keep `~/.ssh`/vault/conversations denied), regardless of where it sits.
    *Alternative:* require the target repo to sit outside every private root
    (simplest profile, but forces a copy even for `review_dirty_diff`). The judge
    should pick the read-side model — it is the one genuine build-time subtlety in
    the sandbox reuse.
12. **Wire acceptance criteria into `packet.planning` in P5, or defer to Phase 6?
    (⚖ adv-F4.)** `apply_criteria` stashes criteria on
    `context_pkg["acceptance_criteria"]`, but the renderer reads
    `packet.planning.converged_brief.acceptance_criteria`, and
    `build_execution_packet` hardcodes `planning=None` — so the "NO ACCEPTANCE
    CRITERIA DECLARED" banner fires unconditionally today. *Recommended (small P5
    win):* thread `context_pkg["acceptance_criteria"]` into `packet.planning` at
    construction, so a filled evidence lane can actually be judged against a
    declared setpoint. *Alternative:* leave the planning-block wiring to Phase 6
    and record the unconditional banner as a known gap.
13. **Windows/Linux enforcement — how much backend to build in P5. → JUDGE-RESOLVED
    (design-gate approval).** Ship **`ORA_EVIDENCE_SANDBOX` as the first-class
    Windows enforcement route**, and include **native Linux `unshare -rn` only if
    it can be capability-probed and safely degrades to refuse**. **No check may run
    under an unenforced `network: deny`.** (This is the judge's directive; the
    implementation follows it exactly — the native Linux backend is gated behind a
    probe that, on failure, falls through to `ORA_EVIDENCE_SANDBOX`-or-refuse.)
14. **Catalog execution form.** *Recommended:* shell-free `argv` is the default and
    the only form the shipped `~/ora` catalog uses; `cmd`+`shell:true` (via
    `ORA_POSIX_SHELL`, refuse-not-cmd.exe) is the opt-in escape hatch; `argv_windows`
    /`argv_posix` for genuine platform divergence (amendment reqs 2 & 4).
    *Alternative:* keep a `cmd` shell string as the default (rejected — bakes in a
    POSIX shell, the amendment's exact anti-pattern).

---

## 7. Portability (required by the amendment — cross-platform surfaces, tests, remaining assumptions)

Per the spec Amendment ("Cross-Platform Portability Is Release-Blocking"), Phase 5
must run on macOS **and** Windows; the judge blocks any macOS-dependent path
without a guarded Windows-compatible route. This design has **no macOS-only
execution path** — it leans on the cross-platform substrate Phase 1 already
shipped and hardened.

**Cross-platform surfaces this design touches, and how each is made portable:**
| Surface | Portability approach | Amendment req |
|---|---|---|
| Check execution | **ENFORCE-OR-REFUSE** (judge Rev-2): a check runs only under a backend that enforces its declared network policy → `orchestrated`; else refuses cleanly. Backends: macOS `sandbox-exec`; a declared `ORA_EVIDENCE_SANDBOX` wrapper (the first-class Windows route — container / WSL+`unshare` / Windows Sandbox); optional native Linux `unshare -rn`. Never runs a check under an unenforced constraint. | core / §7 |
| Env isolation | The runner builds its **own** credential-stripping clean env (the `code_execute._clean_env` pattern, platform-aware — POSIX `HOME`/`TMPDIR`, Windows `USERPROFILE`/`TEMP`/`SystemRoot`/`COMSPEC`/`PATHEXT`; strips `SSH_AUTH_SOCK`/keys). It does **not** reuse `bash_execute._clean_env` (leaky allowlist) — only `bash_execute._posix_shell_path`. | 3 |
| Command form | Shell-free **`argv`** default (`subprocess.run(argv, shell=False)`); `cmd`+`shell:true` only for genuine shell needs, run via `ORA_POSIX_SHELL` on Windows (refuse-not-`cmd.exe`, reusing only `bash_execute._posix_shell_path`); `argv_windows`/`argv_posix` for genuine divergence. Interpreter `python`/`python3` → `sys.executable`. | 2, 4 |
| Path roots (runner's OWN) | Worktree via `tempfile.mkdtemp(dir=runtime_paths.SCRATCH_DIR_STR)`; `trace_dir` via `pipeline_trace`/`runtime_paths`; discovery via `pathlib`. **No `/tmp`, `/Users/...`, `/private`, no repo-location or current-user roots.** | 1, 5 |
| Catalog discovery | `pathlib` upward walk + `ORA_PROJECT_ROOT` env; `git rev-parse` only an optional fast path, never the sole mechanism. | 1 |
| Catalog `argv` OPERAND paths | Operands like `orchestrator/tests` are **opaque tool arguments**, not runner filesystem paths — their cross-platform resolution is the invoked tool's job (Python's `unittest` and Node accept forward slashes on Windows). Stated as a residual (below), not claimed as the runner's own handling. | 3 (scoped) |
| POSIX-only APIs | The **runner's own** code avoids `select()` on pipes (uses `subprocess.run(capture_output=True)`, the `code_execute`/`bash_execute` precedent), process groups/signals, executable bits, symlinks, `/dev/null`, colon-path parsing, and slash-only path *literals* (its own paths are `pathlib`). Path comparison reuses Phase-1 `_matchable`/`_cmp_key` (already `\`↔`/` + case normalized). | 3 |

**Tests added (amendment req 6 — Windows behaviour simulated on mac/Linux CI, mirroring `test_portability.py`'s `ntpath`/`PureWindowsPath` + platform-monkeypatch pattern; macOS-only green is explicitly NOT sufficient):** enforce-or-refuse — a `network:deny` check with **no** enforcing backend **refuses cleanly** (never runs unenforced, never records `orchestrated`) and with a declared/mocked `ORA_EVIDENCE_SANDBOX` runs `orchestrated`; the `shell:true`-without-`ORA_POSIX_SHELL` clean refusal (asserts no `cmd.exe`); `argv_windows`/`argv_posix` selection; a `PureWindowsPath` `repo_root` through the allow-list logic; a static scan asserting no hardcoded `/tmp`/`/Users`/`/private`; `argv` shell-free execution + `sys.executable` interpreter resolution on every platform (§5).

**Remaining platform assumptions (stated honestly, not hidden):**
- **Check execution requires an ENFORCING backend on every platform; no check runs unenforced (judge Rev-2).** macOS has a native one (`sandbox-exec`); Linux may (native `unshare -rn`, capability-probed); **Windows requires a declared `ORA_EVIDENCE_SANDBOX`** (WSL / container / Windows Sandbox — a normal dev-Windows capability, exactly as `shell:true` needs `ORA_POSIX_SHELL`). Where none is available, a `network:deny`/`local` check **refuses cleanly** — it is never run under an unenforced constraint. The credential-stripping clean env + disposable worktree are defense-in-depth on top of enforcement, not a substitute for it.
- **"Runs on Windows" means: the runner MACHINERY (parse / validate / discover / Contract / git-state — pure Python) runs unconditionally, and CHECK EXECUTION runs under a declared `ORA_EVIDENCE_SANDBOX`.** The shipped `~/ora` catalog runs natively on macOS + Linux and under `ORA_EVIDENCE_SANDBOX` on Windows; without it, its checks refuse cleanly (the judge-accepted "revisit what runs on Windows for the shipped catalog").
- **`shell:true` checks require `ORA_POSIX_SHELL` on Windows** and refuse cleanly without it (never `cmd.exe`). The shell-free `argv` default avoids this for the common case; the `~/ora` catalog uses `argv` only.
- **Catalog `argv` operand paths rely on the invoked tool's slash-tolerance (⚖ Rev-1 PORT-2).** Operands like `orchestrator/tests` / `server/static/.../run.js` are opaque arguments to Python/Node, which accept forward slashes on Windows — this is a property of the *invoked tool*, not the runner. A portability test asserts the shipped `~/ora` catalog's `argv` operands resolve under a simulated-Windows cwd; a project whose tool is slash-intolerant must declare `argv_windows`.
- **How much enforcing backend Phase 5 ships** (universal `ORA_EVIDENCE_SANDBOX` + optional native Linux `unshare -rn`) is OQ13 — a decision for the judge, not silently assumed.
- **A live Windows host has not been used to test** (Phase 1's same caveat): behaviour is proven by simulation on mac/Linux CI. Real-Windows validation is a follow-up when a host is available (`_clean_env` `SystemRoot`/`COMSPEC` is the known Phase-1 residual to re-check there).

---

## ⚖ Revision 2 — judge design-gate findings (enforce-or-refuse), all folded

The judge blocked Revision 1: it **ran** `network: deny` checks off-mac while
honestly labeling them unenforced — but honest labeling does not make an
unenforced constraint true, and §7/§15 require checks to run *under* their declared
constraints. All three findings folded:
- **[P0] off-mac execution did not run under declared constraints → ENFORCE-OR-REFUSE.**
  Retired the `boundary_only`-runs-off-mac path. A check now runs **only** under a
  backend that enforces its declared network policy (macOS `sandbox-exec`; a
  declared `ORA_EVIDENCE_SANDBOX` wrapper — now a **first-class supported Windows
  path**, the judge's option A; optional native Linux `unshare -rn`); with no
  enforcing backend it **refuses cleanly** (`skipped` + `skip_reason`), never run
  unenforced (§0, P2 backend/network/constraints bullets, consequence 5/7, §5
  tests, OQ13, §7). "Runs on Windows" now means: machinery runs everywhere + check
  execution runs under a declared `ORA_EVIDENCE_SANDBOX` (like `shell:true` needs
  `ORA_POSIX_SHELL`).
- **[P1] stale `enforcement_model: orchestrated` overclaims** (§1.7, P4 `CheckResult`)
  — now **correct** because an unenforceable check *refuses* rather than running
  under a weaker label; both lines reworded to say `orchestrated` for a check that
  RAN / `skipped`+`skip_reason` for a refused one.
- **[P1] OQ11 still said "worktree OUTSIDE the private-deny roots (e.g. under
  scratch)"** — corrected: `SCRATCH_DIR` is inside `~/ora`/`$HOME`; the per-run
  re-allow of the worktree's exact path is what works, not its location.

OQ13 is reframed from "run-under-`boundary_only` vs require-sandbox" to "how much
enforcing backend to ship" (universal `ORA_EVIDENCE_SANDBOX` + optional native
Linux). OQ5 (network) folded into OQ13. The Rev-1 and Rev-0 folds below still stand
except where superseded by enforce-or-refuse (the Rev-1 §7 remaining-assumptions
"network not enforced, recorded honestly" is replaced by "enforce-or-refuse").

## ⚖ Revision 1 — judge design-gate findings (portability), all folded

The judge blocked Revision 0 on the spec's new **Cross-Platform Portability
Amendment**. All five findings folded. **[HISTORICAL — the P0 `boundary_only`-runs
approach below was SUPERSEDED by Revision 2's enforce-or-refuse; read the Rev-2
block above for the live design. Retained only as a record of the Rev-1 step.]**
- **[P0 — SUPERSEDED by Rev 2] macOS-only execution → platform backend.** *(Rev 1
  had the runner RUN on Windows/Linux under `boundary_only`; Rev 2 retired that —
  a check now runs only under an enforcing backend or refuses.)* The runner no
  longer "does not run off-mac." It abstracts `_sandbox_backend()`, macOS under
  `orchestrated` (kernel sandbox), recording the per-platform `enforcement_model`.
- **[P0] skip-green off-mac tests → Windows simulations.** The test plan tests the
  platform-backend selection, `argv` execution, `sys.executable` resolution, clean
  env, and exit handling **on all platforms**, and simulates Windows
  (`os.name`/`ntpath`/`PureWindowsPath`) for the enforce-or-refuse behaviour (Rev 2
  updated this from the Rev-1 `boundary_only`-still-runs assertion), the
  `shell:true`-without-`ORA_POSIX_SHELL` refusal, per-platform variants, and a
  no-hardcoded-path scan (§5, current form).
- **[P1] POSIX command assumption → shell-free `argv`.** The catalog default is a
  structured `argv` list run `shell=False` (platform-neutral); `cmd`+`shell:true`
  requires `ORA_POSIX_SHELL` (refuse-not-`cmd.exe`); `argv_windows`/`argv_posix`
  for genuine divergence (P1 schema, OQ14). The `~/ora` catalog uses `argv` only.
- **[P1] under-scoped Evidence Contract → committed live at planning.** The Contract
  producer is a live Phase-5 deliverable at the planning stage (spec §15), with
  repo-root discovery (env + `pathlib`) and a **repo-less Contract** fallback so it
  is never silently skipped for lack of a `repo_root` (P3, OQ1). Only check
  *execution* stays library/Phase-6.
- **[P2] missing Portability section → added** (§7): cross-platform surfaces, tests
  added, remaining platform assumptions.

Two new OQs surfaced (OQ13 Windows enforcement policy; OQ14 catalog execution
form).

**Then a focused portability adversarial pass (2 lenses × verify; 14 findings, 7
folded / 7 correctly rejected) sharpened the off-mac honesty — the rejected 7
CONFIRMED the load-bearing claims are exact** (gate-direct-not-dispatch;
`sys.executable` resolution; `git worktree add` on an empty `mkdtemp` dir
succeeds; `EVIDENCE_RUNNER_DEFAULTS` omits `redact`; the runner avoids `select()`
on pipes; reqs 6 & 7 satisfied). The 7 folded were honesty/precision + one
correctness fix:
- **[PORT-1, correctness] two `_clean_env`s.** `bash_execute._clean_env` is a leaky
  allowlist that *preserves* `HOME`/`USER`/`SSH_AUTH_SOCK`; the runner must build
  its OWN credential-stripping env (the `code_execute._clean_env` pattern) for
  BOTH `argv` and `shell:true`, reusing only `bash_execute._posix_shell_path` (the
  resolver), never its env/execution (P2 backend + env bullets, §7).
- **[PORT-1 code-claims] `SCRATCH_DIR` is INSIDE `~/ora`/`$HOME`**, not "outside the
  private-deny roots" — so what makes a worktree readable is the per-run
  re-allow of its exact path, not its location (P2 read-side note, OQ11).
- **[PORT-3] "writes contained by construction" overclaimed** — a cwd is not a
  write jail off-mac; downgraded to "writes expected + diffed-then-discarded, but
  nothing prevents out-of-tree writes off-mac" (§0/P2/§7).
- **[PORT-4] "`_sandbox_backend` reuse" overclaimed** — Phase 1's is mac-or-`None`
  fail-closed; the off-mac `boundary_only` execution is NEW build work; only the
  dispatch shape + clean-env pattern are reused (P2/§7).
- **[PORT-5] "network:deny enforced by prevention-by-absence" conflated** no-creds
  with network-denied; corrected — off-mac `network:deny` is NOT enforced, the
  clean env only removes secrets (P2 network bullet, §7).
- **[PORT-2] catalog `argv` operand paths are slash-only** but that is the invoked
  tool's slash-tolerance (Python/Node accept `/` on Windows), not the runner's own
  path handling — reworded + a test added (§7).

The Revision-0 completeness-critic folds below still stand.

## ⚖ Revision 0 — completeness-critic folds (adversarial pass — 4 diverse lenses × adversarial verify; 45 raw findings, 26 CONFIRMED/survived, 19 correctly REJECTED)

The pass ran four diverse lenses (code-claim verifier / spec-completeness /
seam-integration architecture / adversarial-design) against the design packet,
the spec, and the pinned repo `@82553162`, each finding then handed to an
independent verifier told to **refute** it. A large share of the *verify* agents
hit **server-side rate-limiting** (not usage), so several load-bearing survivors
rest on the reviewer's CONFIRMED verdict alone — **I re-verified the two
BLOCKER/MAJOR ones against the code myself**: the sandbox read-deny (the worktree
is under `$HOME`, which `code_execute._sandbox_profile` denies wholesale — a fresh
`python3` check confirmed the path nesting) and the gate-approve-each hang (the
dispatcher's default `_permission_mode='approve-each'` installs an `input()`
approver, `dispatcher.py:364`; `get_turn_context` degrades gracefully so a
*passing* check is fine, but a *blocked* one via `dispatch()` would hang). Both
confirmed real.

**Folded — the load-bearing architecture + integrity folds:**
- **[seam-F1 / adv-F1 / spec-F1 — BLOCKER] sandbox read-deny.** The sandbox reuse
  is **not** a trivial write-root swap: `code_execute` denies all reads under
  `$HOME` + `~/ora` + vault + conversations, so a check can't read its own repo.
  **Fold:** a dedicated P2 read-side sub-design (re-allow reads of the specific
  `repo_root`/worktree, `cwd=worktree`, prefer a fresh worktree outside the
  private-deny roots) + consequence 6 + new OQ11.
- **[seam-F2 — MAJOR] gate must be DIRECT `tool_events.gate`, not
  `dispatcher.dispatch()`.** `dispatch()` inherits the `approve-each` default →
  an `input()` prompt a programmatic runner can't answer. **Fold:** P2 + consequence
  2 resolved to a direct `gate(interactive_approver=None)` call (queue-not-wait).
- **[seam-F3 — MAJOR] the live Contract lever is blocked by no `repo_root` at the
  planning seam.** **Fold:** OQ1 demoted — the live lever needs a threaded
  `repo_root` (or a repo-less Contract); strengthens "keep it a library."
- **[adv-F2 — MAJOR] "different only because" overclaim.** The write-protected
  catalog protects the command *string*, not the repo *code* the command invokes
  (a model-edited `package.json`/`.py`). **Fold:** P6 reframed to add "green ≠
  honest test" — the runner bounds side-effects + fixes which checks run, but
  grading-your-own-homework is closed by acceptance criteria + the verify stage
  (Phase 6), not the runner alone.
- **[code-F7 / seam-F7 — MINOR] `on_unknown` + network refusal are RUNNER logic,
  not gate behaviour.** `gate()` blocks only on `axes["unknown"]`; it is
  egress-blind. **Fold:** P2 states the runner must map undeclared/unsandboxable
  checks to `axes["unknown"]=True` itself, and enforce `network`/`mutates`-in-dirty
  refusals pre-flight.

**Folded — schema-completeness + precision:**
- **[code-F2 / spec-F2 / adv-F3 — MINOR] `EVIDENCE_RUNNER_DEFAULTS` "adapts"
  (not "verbatim") the §10 block — it omits `redact`.** **Fold:** §1.2 corrected;
  `validate_runner_block` must add `redact`. `network: local` dropped to
  refused-in-P5 (no localhost scoping); OQ5/P2 corrected.
- **[code-F6 — MINOR] `mutates:false → reversible_write`, not `read`** (executing
  a test suite isn't observe-only; matches `code_execute_axes`). **Fold:** P2
  standardized.
- **[seam-F4 — MINOR] `env: isolated` HOME breaks real npm/node/git tooling.**
  **Fold:** P2 flags `env ∈ {isolated, inherit}` as provisional for real runners.
- **[seam-F5 — MINOR] `~/ora` catalog self-recursion.** **Fold:** §0/P1 — the
  `~/ora` catalog is parse+validate only; execution proof uses a fixture.
- **[seam-F10 — MINOR] `trace_dir` ≠ `repo_root`.** **Fold:** stated — the
  git-state helper + diff-writer run OUTSIDE the sandbox and write to `trace_dir`;
  sandboxed checks write only to the worktree + capture stdout (see P2/P5).
- **[adv-F4 — MINOR] the acceptance-criteria banner fires unconditionally in P5**
  (renderer reads `packet.planning`, which stays `None`). **Fold:** §5 note + new
  OQ12 (wire `context_pkg["acceptance_criteria"]` into `packet.planning`, or defer).
- **[code-F1/F3/F4/F5/F14, spec-F3/F4/F5 — NIT] citation fixes.** dispatcher
  shell-write `602-610` (not `629-634`); `engram._git(repo, args)` at `:102`,
  `_repo_root_for` `:112`; `code_execute (deny network*)` at `:97`, write-confine
  `:101-104`; `tool_selector` def `:162` / call `:213`; `validate_check_declaration`
  requires only `cmd`. All corrected in §1.

**Re-checked and correctly REJECTED (the design was already right — not folded):**
The 19 rejected findings were each a *verification that a load-bearing claim is
exact*: the gate blocks on exactly four conditions (spec/code-F10); the
bash-profiler Phase-5 deferral comments are verbatim (code-F11); the `risk_gate`
signatures + wiring at `boot.py:9304`/`server.py:2846` (code-F12); the
`EvidenceLane` fields declared-empty + `route_lanes` diff_validate declaration
(code-F8); the `tool_events` vocabulary citations (code-F9); the catalog-vs-Contract
boundary landed on both surfaces (spec-F7); §16-2 recipe-independence genuinely
enforced (spec-F8); the state-snapshot forms match §11 (spec-F10); the seven §7
runner constraints all covered (spec-F6); the evidence/judgment structural
separation preserved (spec-F12); the additive lane-fill genuinely additive
(seam-F9); the write-protection integrity sound (adv-F5); the "no live path"
honesty framing accurate (adv-F6). None hid a wrongly-dismissed defect.

**Net effect:** the pass did **not** overturn Architecture A. It materially
corrected the *buildability* of the sandbox (a real read-side refactor, not a swap)
and the gate integration (direct `gate`, not `dispatch`), sharpened *scope honesty*
(the live Contract lever is blocked without a `repo_root`; the `~/ora` catalog is
parse-only; the banner fires unconditionally) and *integrity honesty* (green ≠
honest test when the executor wrote the check's code), and fixed a batch of
citations. All folded into §0–§6 and the OQs above. No new blocker survives.
