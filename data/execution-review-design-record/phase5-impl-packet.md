# Execution Review — Phase 5 Implementation Packet (Code adapter + catalog + runner + Evidence Contract + dirty-state)

*Status: CODE-REVIEW GATE — **REVISION 2** (approve-with-conditions folds). Design
gate APPROVED-WITH-CONDITIONS. The code-review gate blocked Rev 0 (5 findings, all
folded → Rev 1), then **approved-with-3-conditions**; all 3 now RESOLVED (§3.6). NO
commit — awaiting confirmation.*

## 3.6 Approve-with-conditions folds (Revision 2) — all 3 resolved

| Condition | Fold (tested + parity-clean) |
|---|---|
| **[P2]** Missing-catalog required checks bypassed tool-event recording (`run_contract`). | The missing-check refusal now calls `_record_check_event` too — a declared-required-but-absent check leaves an `evidence_check` tool-event, same as every other outcome (observed, not narrated). Test added. |
| **[P2]** Packet had stale "flag-gated OFF" / "52 tests" language. | All stale references corrected throughout (the wiring is unconditional; test/line counts updated). |
| **[P3]** Catalog validation accepted malformed execution-form combinations. | `validate_check` now rejects: **mixing** argv-form + cmd-form; a **`cmd` form without `shell: true`** (would refuse at runtime); and **`shell: true` without a cmd form**. Tests added; the shipped catalog still validates. |

Worktree: `/Users/oracle/ora-worktrees/phase5-impl` (branch
`execution-review-phase5-impl` off `82553162`; baseline clean 22F/5E = 27,
3721 tests). Durable diff: `/Users/oracle/ora-worktrees/phase5-impl.diff` (6 files,
+1695/-1, whitespace-clean). Design packet: `/Users/oracle/ora-worktrees/phase5-design.md`.

## 3.5 Code-review-gate folds (Revision 1) — all 5 findings addressed

| # | Finding | Fold (all tested + parity-clean) |
|---|---|---|
| **P1-1** | Evidence Contract absent from normal execution (flag-gated OFF). | The flag gate is **removed** — `apply_evidence_contract` runs **unconditionally in the live planning path** (standard+) at both seams (`boot.py`, `server.py`), additive + never-raises (response text unchanged). Parity clean with it ON. |
| **P1-2** | Checks left **no tool-event** when they ran/refused (verified empty sink) — violates "observed, not narrated" (§16-3). | `run_check` now wraps `_run_check_impl` + `_record_check_event`, recording **exactly one `evidence_check` tool-event per outcome** (ran → backend enforcement; refused/gated → `in_harness`). **Empirically verified**: the previously-empty sink now records the event. |
| **P1-3** | Gate axes hardcoded `orchestrated` for every backend, contradicting the honest `declared-sandbox` a wrapper gets. | `_gate_check` uses `_ENFORCEMENT_MODEL[backend]` (per-backend); `declared-sandbox` added to `tool_events.ENFORCEMENT`. Consistent across gate axes, `CheckResult`, and the tool-event. |
| **P2-1** | `ORA_EVIDENCE_SANDBOX` parsed with `raw.split()` → breaks on `Program Files`-style spaced/quoted paths (the Windows route). | Parsed with `shlex.split(raw, posix=(os.name != "nt"))` **+ a balanced-surrounding-quote strip on the `nt` branch** (a focused re-check caught that `posix=False` *retains* quotes, so the quoted path still failed — the earlier test passed only on POSIX). Now verified under **simulated `os.name="nt"`**; malformed → None (no crash). |
| **P2-2** | Per-platform variants not enforced as matched pairs → a POSIX-only check passes validation then refuses on Windows. | `validate_check` requires a variant to come as a **matched windows+posix pair** (or a base `argv`/`cmd`) + type-checks; test added. Shipped catalog (base `argv`) still validates. |

---

## 1. What shipped (the diff)

| File | What |
|---|---|
| **`orchestrator/evidence_runner.py`** (NEW, ~1020 lines) | The consolidated module: catalog parse/validate, the ENFORCE-OR-REFUSE runner + platform backends + macOS sandbox profile, the credential-stripping clean env, the direct-gate integration + per-check tool-event recording, the planning-stage Evidence Contract producer, git dirty-state snapshots, and the additive lane-fill. |
| **`.ora/evidence.yaml`** (NEW) | Ora's own catalog — shell-free `argv` (`python -m unittest`, `node …/run.js`), both `network: deny`. Version-controlled repo data; write-protected via Phase-1 `_PROTECTED_BASENAMES`. |
| **`orchestrator/boot.py`** (+13) | Planning-seam wiring: `apply_evidence_contract` after `apply_criteria`, run **unconditionally in the live planning path** (standard+); additive (response text unchanged). |
| **`server/server.py`** (+11) | Same planning-seam wiring on the server path. |
| **`orchestrator/tool_events.py`** (+5/−1) | Added `declared-sandbox` to the `ENFORCEMENT` vocabulary (P1-3). |
| **`orchestrator/tests/test_evidence_runner.py`** (NEW, 61 tests) | Full coverage incl. the mac-gated **real `network: deny` enforcement** under `sandbox-exec`, the per-check tool-event recording, the security-fold + code-review-fold regressions, and Windows-behaviour simulations. |

## 2. The design as built (enforce-or-refuse, per the approved Rev 2)

- **ENFORCE-OR-REFUSE.** `run_check` runs a check **only** under a backend that
  actually enforces its declared network policy; else it **refuses cleanly**
  (`skipped=True` + `skip_reason`) — a check is **never run under an unenforced
  `network: deny`**. Backends: macOS `sandbox-exec` / native Linux `unshare -rn`
  (runner-VERIFIED → `enforcement_model: orchestrated`); a declared
  `ORA_EVIDENCE_SANDBOX` wrapper (operator-ATTESTED → `enforcement_model:
  declared-sandbox`, a distinct honest label — never overclaimed as `orchestrated`).
  `network: local`/`allow` → refuse (no scoping / no proxy, §7).
- **The runner is gated via a DIRECT `tool_events.gate(interactive_approver=None)`**
  — never `dispatcher.dispatch()` (which would inherit the `approve-each` `input()`
  prompt a programmatic runner can't answer).
- **The macOS sandbox profile** re-allows reads of the specific worktree (the
  repo must read its own source) while keeping `$HOME`/`~/ora`/vault/conversations
  denied, and kernel-denies network. It **refuses** an SBPL-unsafe or
  ancestor-of-a-sensitive-root worktree (see §3), and re-denies any private root
  nested under the worktree.
- **The runner builds its OWN credential-stripping, platform-aware clean env** —
  never `bash_execute._clean_env` (which preserves `SSH_AUTH_SOCK`). POSIX
  `HOME`/`TMPDIR`; Windows `USERPROFILE`/`TEMP`/`SystemRoot`/`COMSPEC`/`PATHEXT`.
- **Catalog:** shell-free `argv` default (resolves `python`→`sys.executable`);
  `cmd`+`shell:true` runs `/bin/sh` on POSIX / `ORA_POSIX_SHELL` on Windows
  (refuse-not-`cmd.exe`); `argv_windows`/`argv_posix` for genuine divergence.
  `validate_check` extends the Phase-1 vocabulary (argv-or-cmd); `validate_runner_block`
  requires `redact` (§7 load-bearing).
- **The Evidence Contract producer** (`apply_evidence_contract`) is the
  planning-stage sibling to `apply_criteria` — discovers a catalog (env + pathlib),
  emits a repo-less contract when none is found (never silently skipped), keeps only
  declared checks in `required_standard_checks`. Wired live at both planning seams —
  runs **unconditionally on standard+ turns** (spec §15/§16-2); additive (response
  text unchanged; a no-invoker/offline turn is a graceful no-op).
- **Dirty-state** (`snapshot_before`/`snapshot_after`): git SHA/tree-hash snapshots
  (§9, small+flat), `delta.ref` a written `git diff` path (never inlined); the
  git-state helper runs OUTSIDE the sandbox. `mutates:true` runs **only** under an
  explicit `clean_worktree` (a missing mode fails safe → refuse).
- **Lane fill** (`fill_evidence_lanes`): additive; fills the Phase-4 diff_validate
  lane's `generated_by`/`result`/`sufficient`; `sufficient` judged against the
  Contract (`contract_sufficient`) — every required check must have run + passed;
  empty/refused/failed → not sufficient. The "green ≠ right problem / ≠ honest test"
  sentence is in the module docstring.

## 3. Adversarial pre-check — 2 EMPIRICALLY-REPRODUCED exploits + 7 defects, all folded

A 2-lens adversarial pre-check (+ a focused fold-recheck) over only the changed
logic found real defects — several reproduced **live against the real
`sandbox-exec`**. All folded + re-verified:

| # | Severity | Defect | Fix (verified) |
|---|---|---|---|
| SEC-1 | BLOCKER-in-module | **SBPL profile INJECTION** — an unescaped worktree path with `"` injected `(allow network*)`, escaping network-deny while recording false `orchestrated` (reproduced: live socket opened). | `sandbox_worktree_unsafe()` refuses any SBPL-unsafe path (`" \ ( ) newline`) before building the profile. **Verified blocked live.** |
| SEC-2 | BLOCKER-in-module | **Vault RE-EXPOSE** — a worktree that is an ancestor of the vault re-allowed it (reproduced: `cat vault/secret` succeeded). | Refuse ancestor-of-sensitive-root worktrees; `_macos_profile` re-denies nested private roots after the allow. **Both verified blocked live vs real sandbox-exec.** |
| SEC-3 | MAJOR | `mutates:true` escaped isolation under the default `mode=None`. | Refuse unless `mode == "clean_worktree"` explicitly (fail-safe). |
| SEC-4 | MAJOR→(reworked) | A declared wrapper recorded false `orchestrated`; my first probe was itself unsound (offline false-positive + argv-shape divergence, both reproduced). | A wrapper is now `declared-sandbox` (operator-attested, honest — never `orchestrated`); a **reject-only, attributive** probe refuses only a *demonstrated* online passthrough (baseline-OPEN + wrapped-OPEN). **Both re-check findings verified closed.** |
| SEC-5 | MINOR | `env: inherit` leaked `SSH_AUTH_SOCK`/keys. | Dropped `inherit`; always credential-stripped. |
| PORT-1 | MAJOR | `shell:true` always refused on POSIX (used the Windows-only resolver). | `/bin/sh` on POSIX, `ORA_POSIX_SHELL` on Windows. |
| PORT-2 | MINOR | `unshare` probe cache not platform-keyed. | Platform-gated before the cache. |

The pre-check also **confirmed** (rejected-as-not-a-defect): the wiring is
additive + parity-safe (writes only `context_pkg['evidence_contract']` + a
tool-event; response text unchanged — parity confirmed with it running); the
`_gate_check` no-backend branch is harmless defense-in-depth; the nested
`bash_execute` import is fine.

## 4. Parity + tests
- **+61 net new tests (3782 total); full suite = 27 FAIL/ERROR identical to the
  22F/5E environmental baseline; ZERO new failures** — including with the Contract
  producer now unconditional in the live planning path. (`ORA_PIPELINE_TRACE=off
  ORA_TOOL_EVENTS=off`; pre-edit baseline captured in the same worktree; sorted
  FAIL/ERROR name lists diffed pre-vs-post.)
- 61 `test_evidence_runner` tests (the full +61 net-new), incl. the **mac-gated
  real `network: deny`** enforcement under `sandbox-exec`, the per-check + missing-
  check observability recording, the Windows-quote-strip simulation, the malformed
  execution-form rejection, and the security-fold + code-review-fold regressions.

## 5. Portability (release-blocking amendment — required section)
- **No macOS-only execution path.** The runner machinery (parse/validate/discover/
  Contract/git-state) is pure Python and runs everywhere; check EXECUTION runs under
  an enforcing backend (macOS `sandbox-exec` / declared `ORA_EVIDENCE_SANDBOX` — the
  first-class Windows route / native Linux `unshare -rn`) or refuses cleanly.
- **Commands** are shell-free `argv` (`subprocess.run(argv, shell=False)`); `shell:true`
  uses `/bin/sh` (POSIX) / `ORA_POSIX_SHELL` (Windows, refuse-not-`cmd.exe`).
- **Paths** from `runtime_paths`/`tempfile`/`pathlib` — a test asserts no hardcoded
  `/tmp`/`/Users`/`/private`. Clean env is platform-aware.
- **Tests added** (Windows sims on mac/Linux CI, `ntpath`/`PureWindowsPath` +
  `os.name`/`sys.platform` monkeypatch): enforce-or-refuse under simulated-nt, the
  `shell:true`-without-`ORA_POSIX_SHELL` clean refusal (no `cmd.exe`), per-platform
  variant selection, Windows clean-env vars, the platform-gated unshare cache, the
  no-hardcoded-path scan.
- **Remaining platform assumptions:** the runner-VERIFIED kernel guarantee is
  macOS (`sandbox-exec`) / Linux (`unshare`); Windows enforcement is via a declared
  `ORA_EVIDENCE_SANDBOX` (operator-attested → `declared-sandbox` label, never
  overclaimed; a demonstrable online passthrough is still refused). A live Windows
  host has not been used — behaviour is proven by simulation.

## 6. Scope boundary — what Phase 5 does NOT do
No full produce→capture→verify→revise loop (Phase 6). The **runner (check
EXECUTION)** auto-runs on no live path (Phase 6 drives it); the **Contract producer**
is the live wiring and runs unconditionally at planning (standard+). Only the
diff+validate lane is filled; `collect_provenance`/other adapters + the
claim-to-source map are Phase 8. No MSI catalog (Phase 8). No egress-logging proxy
(`network:allow` refused). Evidence + diffs are trace-local (durable persistence is
Phase 7).

## 7. On approval
Land per the git workflow: re-check `origin/main` hasn't advanced (rebase if it
has), commit → push → PR → squash-merge → delete branch (local+remote) → prune the
worktree → fast-forward `~/ora` main. Report the PR number + bare commit SHA.
