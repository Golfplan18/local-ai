# Execution Review — Phase 1-4 Portability Review Packet

**Verdict: `needs judge review`.**

Scope: a comprehensive macOS + Windows compatibility audit of the LANDED
Execution Review Phase 1-4 code, with fixes for every real Windows break found.
Built in a fresh worktree off current `origin/main` (`82553162`, branch
`execution-review-phase1-4-portability`). No commit yet — this build is
judge-gated; land only after the judge approves.

- Durable diff: `/Users/oracle/ora-worktrees/phase1-4-portability-impl.diff` (9 files, +354/−38, ws-clean).
- Full-suite parity: **3738 tests, 22F/5E identical to the `82553162` baseline — NEW failures = 0, disappeared = 0** (verified by diffing sorted FAIL/ERROR name lists).
- Focused Phase 1-4 suites (portability + shell_profiles + tool_events + dispatcher_gate + execution_packet + risk_gate + risk_gate_pipeline + quality_gate + slash_commands): all pass. +17 new Windows-simulation tests.

The judge thread's `block` (3 findings) is fully addressed; two additional
real breaks of the same class were found and fixed; the audit workflow's own
raw findings were adjudicated (the encoding-less reads were latent, hardened
defensively).

---

## 1. Findings fixed (severity-ordered)

### [P1 — security] `dispatcher.validate_path` write-containment was unsafe on Windows *and* latently on POSIX
`orchestrator/dispatcher.py` — `ALLOWED_BASES` + `validate_path`.
- **Mechanism 1 (containment):** writes were allowed by raw `resolved.startswith(base)`. This treats a mere-prefix **sibling** as inside: `C:\Users\a\ora-project\evil.txt`.startswith(`C:\Users\a\ora`) → allowed on Windows; the identical hole exists on POSIX (`~/ora-worktrees/x` starts with `~/ora`). It was also **not case-normalized**, so Windows case-insensitivity (`C:\Users\A\ORA\…`) was handled inconsistently.
- **Mechanism 2 (deny-list):** the sensitive-path deny-list matched `pattern in resolved.lower()`. The `/`-shaped patterns (e.g. `.aws/credentials`) never match a Windows backslash path (`C:\Users\a\.aws\credentials`) — the same separator-anchoring class Phase 1 fixed for the secret regexes, but `validate_path` was never routed through the normalizer.
- **Fix:** boundary-anchored + case-normalized containment via a new shared helper `runtime_paths.within_any_base` (requires the next char after `base` to be a separator; compares through `norm_key`), and a separator-normalized deny-list match (`resolved.replace("\\","/").lower()`). Live-called from the file read/write gate (`dispatcher.py:767/775`).

### [P1 — security] `file_ops._validate_path` — a *second copy* of the same containment + deny-list bug, plus hardcoded roots
`orchestrator/tools/file_ops.py` — live-called from `file_read` / `file_write`.
The judge cited only the dispatcher copy; `file_ops` had the identical
`startswith(base)` + backslash-blind deny-list, and additionally hardcoded its
roots (`~/ora`, `~/Documents/vault`, `~/Documents/conversations`) instead of
sourcing them from `runtime_paths`.
- **Fix:** roots now come from `runtime_paths` (honor `ORA_HOME`/`ORA_VAULT`/`ORA_CONVERSATIONS`); containment uses the same `within_any_base`; deny-list is separator-normalized. Both containment gates now share one boundary-safe implementation.

### [P1] `bash_execute._clean_env` dropped the Windows-essential system variables
`orchestrator/tools/bash_execute.py`.
- **Mechanism:** the subprocess env copied only a POSIX allowlist (`PATH`, `HOME`, `SHELL`, …). On Windows, spawning **any** process — including the declared Git Bash / WSL `sh` via `ORA_POSIX_SHELL` — fails without `%SystemRoot%` (winsock/crypto DLL load), and command resolution needs `COMSPEC`/`PATHEXT`. So even the Phase-1 "run under the declared POSIX shell" path would fail to spawn on a real Windows host. (Documented as a deferred item in the Phase-1 handoff; it is in Phase 1-4 scope and fixed here.)
- **Fix:** under `os.name == "nt"`, additionally propagate `SystemRoot`, `SystemDrive`, `windir`, `COMSPEC`, `PATHEXT`, `TEMP`, `TMP`, `USERPROFILE`, `LOCALAPPDATA`, `APPDATA`, `NUMBER_OF_PROCESSORS`, `PROCESSOR_ARCHITECTURE`. The POSIX environment is left byte-identical (the branch is `nt`-only).

### [P1] `server.py` core roots were not `ORA_HOME`-aware
`server/server.py` — the live chat/pipeline server entrypoint.
- **Mechanism:** `WORKSPACE = os.path.expanduser("~/ora/")` and the two `CONVERSATIONS` roots were hardcoded before `runtime_paths` was imported, so a Windows install outside `%USERPROFILE%\ora`, or an `ORA_HOME`/`ORA_CONVERSATIONS` relocation, was not honored by the main server path (the Phase-1 pass had moved a couple of server *sinks* but not the server *root* itself).
- **Fix:** `WORKSPACE` now derives from `ORA_HOME` (mirroring `runtime_paths.ORA_HOME`'s own derivation, so the two never disagree) in the pre-import bootstrap shim; the conversation roots are sourced from `runtime_paths` after the import. `os.path.join(root, "")` preserves the trailing-separator semantics the rest of the module relies on; the repo-root `sys.path` entry strips either separator (Windows trailing `\`). Verified: on default macOS the derived values are byte-identical to before.

### [P2] `slash_commands.py` hardcoded `/Users/oracle/ora` import fallbacks (×4) + hardcoded search roots
`orchestrator/slash_commands.py` — reachable from the pipeline short-circuit.
- **Mechanism:** four historical-tool import fallbacks did `sys.path.insert(0, "/Users/oracle/ora")` — an absolute path that is neither cross-platform nor a safe default. Two module-level path roots (`VAULT_DIR`, `ORA_DIR`) also bypassed `runtime_paths`.
- **Fix:** the four fallbacks use a `__file__`-derived repo root (`_ORA_ROOT`); `VAULT_DIR`/`ORA_DIR` now source from `runtime_paths` (guarded import, `__file__`+expanduser fallback). Default output/search dirs (`Corpus Instances`, `Outputs`) are byte-identical on default.

### [Low / defensive] Encoding-less reads in the Phase 2-4 modules
`orchestrator/risk_gate.py` (event-log read, sticky read/write) and
`orchestrator/execution_packet.py` (packet write).
- **Adjudication:** these are **not** live bugs today — the `tool_events` sink and the packet are written via `json.dump(...)` with the default `ensure_ascii=True`, so the on-disk bytes are ASCII and reading them under any locale codepage (incl. Windows cp1252) is safe. But house style since the Rev-8 `mcp_client` fix is to pin UTF-8, and it future-proofs against a later `ensure_ascii=False`.
- **Fix:** pinned `encoding="utf-8"` on those opens (behavior-identical on macOS; robust on a non-UTF-8-locale Windows host).

---

## 2. Files changed
| file | change |
|---|---|
| `orchestrator/runtime_paths.py` | NEW `within_base` / `within_any_base` — the single boundary-anchored, case-normalized containment helper |
| `orchestrator/dispatcher.py` | `validate_path` → `within_any_base` containment + separator-normalized deny-list; `ALLOWED_BASES` simplified |
| `orchestrator/tools/file_ops.py` | roots from `runtime_paths`; `_validate_path` → shared containment + normalized deny-list |
| `server/server.py` | `WORKSPACE` derives from `ORA_HOME`; `CONVERSATIONS_DIR/RAW` from `runtime_paths`; Windows-safe `sys.path` rstrip |
| `orchestrator/tools/bash_execute.py` | `_clean_env` propagates the Windows-essential system vars under `os.name=='nt'` |
| `orchestrator/slash_commands.py` | `_ORA_ROOT` (`__file__`-derived) replaces 4 hardcoded fallbacks; `VAULT_DIR`/`ORA_DIR` from `runtime_paths` |
| `orchestrator/risk_gate.py` | `encoding="utf-8"` on the event-log read + sticky read/write |
| `orchestrator/execution_packet.py` | `encoding="utf-8"` on the trace-local packet write |
| `orchestrator/tests/test_portability.py` | +17 Windows-simulation tests (below) |

---

## 3. Cross-platform surfaces audited
- **New Phase 2/3/4 modules** (`risk_gate.py`, `execution_packet.py`) read in full: every path op, file open (mode + encoding), separator/drive assumption, subprocess/platform branch, and every place a path is *matched* vs passed through opaque. Finding: they are portable **by construction** — opaque-string passthrough, `os.path.join`, `runtime_paths`, ASCII-only JSON — so the only items were the defensive encoding pins.
- **Phase 2/3/4 wiring diffs** (`phase2/3/4-impl.diff`) cross-checked against current code for new hardcoded paths / POSIX assumptions / normalizer bypasses. The terminal packet-construction call sites derive `trace_dir` from the existing `pipeline_trace` plumbing (`os.makedirs` + `os.path.join`) — portable.
- **Phase 1 substrate** re-verified intact and not bypassed: `tool_events._matchable`/`_cmp_key` still gate all protected/secret/private classification; `runtime_paths.norm_key`/`locked_file`; `bash_execute` POSIX-shell fail-closed via `ORA_POSIX_SHELL`; `code_execute` mac-gated; `search_files` os.walk fallback; `mcp_client` no-`select` reader.
- **Write-containment gates** (`dispatcher.validate_path`, `file_ops._validate_path`) — the two live file read/write safety boundaries.
- **Server bootstrap** and **slash-command** reachable code paths.
- **Repo static scan** (`scripts/check-portability.py`) run before/after; the execution-review hardcodes it flagged are removed (see §5 for the out-of-scope remainder).

---

## 4. Tests added (`orchestrator/tests/test_portability.py`, +17)
Following the existing `ntpath` / `PureWindowsPath` / `os.name`-monkeypatch / subprocess conventions — all run on macOS/Linux CI, no Windows host required.
- `TestWithinBaseBoundary` (3) — self/descendant allowed, **sibling-prefix rejected** (POSIX-real + Windows-sim via patched `norm_key`), case-insensitive descendant, different-drive rejected.
- `TestValidatePathContainment` (4) — dispatcher + file_ops block a POSIX **sibling** write; **deny-list matches backslash paths** (`C:\…\.aws\credentials`, `\.ssh\id_rsa`, `\.gnupg\…`); a **path with spaces** inside a base is allowed.
- `TestFileOpsRootsFromRuntimePaths` (2) — roots equal `runtime_paths`; no hardcoded user path in source.
- `TestCleanEnvWindowsVars` (2) — Windows propagates `SystemRoot`/`COMSPEC`/`PATHEXT`/…; POSIX env unchanged (no Windows keys leak).
- `TestServerRootHonorsOraHome` (1) — isolated **subprocess** import with a relocated `ORA_HOME`/`ORA_CONVERSATIONS` (paths with spaces) asserts `server.WORKSPACE`/`CONVERSATIONS_DIR` follow the env — suite-order-independent.
- `TestSlashCommandRepoRoot` (2) — `_ORA_ROOT` is `__file__`-derived; no `/Users/oracle/ora` literal in source.
- `TestExecutionPacketTracePathPortable` (1) — `construct_and_write` into a **trace dir with spaces + nesting**, non-ASCII deliverable, UTF-8 round-trip.
- `TestRiskGateEventLogEncoding` (2) — fold reads a **real-UTF-8** event log (non-ASCII URL) without crashing; sticky round-trip under a relocated `DATA_DIR`.

These directly satisfy the required drive-letter / backslash / sibling-prefix / spaces / case-insensitive coverage, the `ORA_POSIX_SHELL`-refusal coverage (pre-existing, re-verified intact), and env-derived-root + temp/trace-path coverage.

---

## 5. Remaining platform assumptions / explicit safe-refusals
**Explicit safe-refusals (correct, unchanged):**
- `bash_execute` on Windows without a valid `ORA_POSIX_SHELL` **refuses** (never `cmd.exe`); with one, it now also has the env to actually spawn it.
- `code_execute` (sandbox-exec) is macOS-only, gated `unavailable` off-mac, never claims `orchestrated` off-mac.
- `search_files` uses the Python `os.walk` fallback where Unix `grep` is absent.

**Pre-existing, OUT of execution-review scope — documented, not fixed** (per "keep fixes scoped to Phase 1-4"). None of these are Windows *breaks* introduced by Phase 1-4; `check-portability.py` still exits nonzero because of them:
- `orchestrator/output_runtime.py` (meta-layer OFF renderer) hardcodes `/opt/homebrew/bin/python3` in pip-install-on-ImportError (3×) — macOS-only; recommend a `sys.executable`/PATH fallback in a separate pass.
- `server/server.py` restart/open endpoints (`~L14119/14152` homebrew python, `~L4940` `open`) and several `expanduser("~/ora/staging/…")` media/visual roots — **cross-platform** (`expanduser` resolves on Windows) but not `ORA_HOME`-relocation-aware; these are non-execution-review server features. Recommend a follow-up root-sweep like the Phase-1 "post-landing follow-ups."
- `test_*` `/tmp` literals and `/opt/homebrew/bin/python3` in unrelated test files; `osascript`/`launchctl` strings in `test_shell_profiles.py` are **test inputs** being classified, not macOS-only code (checker false positives); `bash_execute.py` SHELL_PROFILE entry for `launchctl` is command *classification*, not a platform dependency.

**Note (spec-correct, do not "fix"):** the packet `reversible` frontmatter flag is the §6 post-hoc-routing gate — high-risk is intentionally `reversible: true`.

---

## 6. Phase 5 implications
- The new `runtime_paths.within_base` / `within_any_base` helpers are the correct primitive for Phase 5's dirty-state / worktree containment checks (`clean_worktree` boundary, "is this write inside the scratch worktree") — use them rather than re-deriving `startswith`.
- The `_clean_env` Windows fix is a prerequisite for Phase 5's evidence runner ever executing catalog checks (`npm test`, `python3 -m unittest`) under a declared shell on Windows.
- Phase 5's `.ora/evidence.yaml` catalog is already write-gated (`evidence.yaml` in `tool_events._PROTECTED_BASENAMES`), and the protected-basename match runs through the Windows-normalized matcher — so catalog protection holds on Windows (covered by the existing `TestWindowsProtectedPaths`).
- No Phase 5 code was touched; no conflicts introduced.

---

## 7. Landing (pending judge approval)
On approval, land per the git workflow: re-check `origin/main` hasn't advanced, branch off current, commit → push → PR → squash-merge → delete branch + prune the `phase1-4-portability` worktree → fast-forward `~/ora` main. If blocked: fold in the same worktree, re-run adversarial pre-check + parity, resubmit.
