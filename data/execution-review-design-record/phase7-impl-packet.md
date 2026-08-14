# Execution Review — Phase 7 IMPLEMENTATION PACKET (tiered persistence, spec §14)

## ⚖ Revision 1 — judge CODE-REVIEW BLOCK folded (fail-closed redaction)

Judge verdict on Rev 0: **BLOCK** — 1 P1 + 1 P3, both confirmed real and folded:

- **[P1 — redaction failed OPEN]** `redact_for_durable`'s except returned the **original unredacted
  packet**, which `persist_packet` then wrote durably (judge reproduced with a deepcopy-bombed `execution`
  block: the failure marker was stamped but the durable note still contained the raw PII). **FOLD (fail
  closed):** (1) the redactor's except now returns **`None`** — never the original; (2) `persist_packet`
  treats `None` as a hard skip: stamps `persistence.redacted = "REDACTION FAILED — durable write withheld
  (fail-closed)"` + a distinct `_note_failure` marker (`execution_persistence_fail_closed`) and returns the
  tier with **NO durable write** (the trace-local packet + the escalation handback — which carries only the
  Phase-6 `redacted_review_summary` reference, no packet body — still exist: degrade, never fail open);
  (3) **a second fail-open of the same class, self-found during the fold:** `_scrub_free_text`'s inner
  except (a raising `scrub_content`) kept the RAW text in the private/public layer — now returns a
  `[SENSITIVE — N chars withheld]` descriptor instead. **Regression tests:** the judge's exact deepcopy-bomb
  repro at the redactor level (returns `None`, never the original) AND end-to-end (a durable_note turn with
  failed redaction writes NO note, NO ledger line, and an os.walk of the store finds NO PII on disk), plus a
  broken-`scrub_content` test (raw token withheld). An adversarial re-check of the fold (2 lenses ×
  per-finding verify: remaining-fail-open-paths + over-closing/regression; a full run, not rate-limited)
  returned **ZERO findings**.
- **[P3 — POSIX/Mac fixture paths in tests]** `/Users/x/.ssh/id_rsa` and `/tmp/relocated-store` fixtures
  replaced with `tempfile`-derived paths, and the path-sensitivity test now ALSO asserts a Windows-shaped
  fixture (`C:\Users\x\.ssh\id_rsa`) classifies identically (the point of the test IS path sensitivity).
- Judge-confirmed fixed from the design conditions: `git check-ignore` hand-verified on both store paths;
  base = current `origin/main` `b4b257dd`.

**Post-fold parity (re-run on the FINAL code): 3910 tests, 27 FAIL/ERROR — sorted name lists IDENTICAL to
the 3869/27 baseline. ZERO new, ZERO disappeared. Net new tests now +41.** Focused suites 163 all pass.
Diff regenerated (whitespace-clean); still NO commit.

*Adjacent surface, noted for completeness (NOT changed — pre-existing, Phase-6-judge-approved):* on an
escalated turn the handback to the human queue carries `redacted_review_summary(packet)` (drops the
producer-claim fence, 4000-cap) — that durable reference includes the acceptance-criteria fence and is
independent of the Phase-7 redactor. Unchanged scope; flagged so the judge sees the full durable-write map.

Rev-0 packet below (historical; parity figures superseded by the post-fold numbers above):

---

*Status: IMPLEMENTED — delivered to the CODE-REVIEW gate. **NO commit** until the judge approves the code
(overrides commit-by-default for this project). Design gate PASSED (approve-with-conditions, Rev 3); both
conditions honored (see §6). Implemented in the fresh worktree `/Users/oracle/ora-worktrees/phase7-impl`
(branch `execution-review-phase7-impl` off CURRENT origin/main `b4b257dd` — the docs-only PRs #189/#190 that
landed past Phase 6 `8ae29eb3` touch no Phase-7 substrate, so every design file:line anchor held exactly).*

Durable artifacts: this packet + `/Users/oracle/ora-worktrees/phase7-impl.diff` (the full diff, incl. the two
new files) + the approved design `/Users/oracle/ora-worktrees/phase7-design.md`.

---

## 1. What was built (per the approved design)

**A single new consolidated module `orchestrator/execution_persistence.py`** owns the whole §14 concern:
- `decide_tier(packet) -> str` — the promotion function. `durable_note` iff escalated OR escalation-withheld
  OR a plan-level finding; `ledger_line` iff a mutation turn degraded without converging; else `git_only`
  (the default — self-evidencing, converged-clean, source-read-only-owed). Defensive `.get()`; never raises.
- `redact_for_durable(packet, *, max_sensitivity) -> ExecutionPacket` — a **scrubbed shallow-copy** packet,
  three-layer keyed on the TRUE `max_sensitivity` (from the folded `sig`): `secret`→existence-only marker,
  `sensitive`→`[SENSITIVE:N chars]` descriptor, `private`/`public`→`scrub_content`-and-keep. Scrubs
  `producer_claim.summary`/`known_limitations`, `task.instruction`, `verification.findings[].description`,
  **`planning.converged_brief.*` (added in the pre-check fold — §5)**, and the `delta.ref` path. Reuses
  `tool_events.scrub_content` / `resolve_path_sensitivity` / `_SENS_RANK`.
- `execution_records_dir()` / `ledger_sink_path()` — env-overridable, `runtime_paths.DATA_DIR_STR`-rooted.
- `append_ledger_line(...)` — O_APPEND single-line append (the `tool_events.record` idiom), stealth-gated,
  top-level `conversation_id` stamped.
- `write_durable_note(redacted_packet, ...)` — a self-contained, non-RAG-indexed markdown record in a
  per-conversation subdir; renders the **redacted** packet via `render_for_review`; write-tmp + `os.replace`.
- `purge_conversation(conversation_id)` — the stealth-purge backstop (rmtree the note subdir + scrub the
  ledger by id); called by the new closeout layer.
- `persist_packet(packet, *, sig, context_pkg, trace_dir, stealth, now_iso) -> str` — the entry point:
  decide → set `packet.persistence` → (if promoted) redact → write note and/or ledger. NEVER raises;
  `git_only` writes nothing.

**Wiring (5 edited files):**
- `orchestrator/execution_loop.py` — `persist_packet` fires at the `run_loop` terminal **BEFORE**
  `write_packet` (so the trace JSON records the final tier) and on the source-read-only branch; the additive
  `loop_state["escalation_withheld"] = True` marker; `full_signals` (carries `max_sensitivity`, since
  `engage_signals` returns only the two §6 booleans).
- `orchestrator/execution_packet.py` — build default `persistence.tier` `"trace_local"` → `"git_only"` (the
  §14 cheapest default; `persist_packet` promotes). Nothing reads this value.
- `orchestrator/conversation_closeout.py` — a new **Layer 10** in `_purge_stealth` calling
  `execution_persistence.purge_conversation` (reads roots at call time, the Layers-6a/8/9 idiom).
- `.gitignore` — `data/execution-records/` added to the existing "Execution Review runtime state" section
  (the non-git zero-residue guarantee depends on it — Rev-2 P1).

**Loop-only + parity:** `construct_and_write` (the common self-evidencing path) does NOT call `persist_packet`
— a self-evidencing packet is `git_only` by construction. With `ORA_EXECUTION_LOOP` OFF (default), `run_loop`
never fires, so persist is dormant. Flag-OFF behavior is Phase-6 response/control-flow parity (only the inert
trace-JSON `persistence.tier` value changes).

---

## 2. Tests

New `orchestrator/tests/test_execution_persistence.py` (37 tests): the `decide_tier` truth table; the
three-layer redaction (secret/sensitive/private/public, copy semantics, delta-path, **planning
acceptance_criteria str + list**); the ledger + note writers; `persist_packet` end-to-end (git_only writes
nothing, ledger_line = 1 line, durable_note = note + index, stealth writes nothing, never-raises,
true-max-sensitivity from `sig`, **planning-PII absent from the note body**); the `purge_conversation`
backstop (removes note subdir + ledger lines, matches the fs-safe transform on a `:`/`/`-bearing id, no-op on
absent); the common-path git_only parity; `_fs_safe`; the store rooting; and the **`.gitignore`
effective-ignore guard** (`git check-ignore` matches the ledger + a nested note path — Rev-3 P2).

Existing-test edits (enumerated, semantic not regressions): `test_execution_packet.py` — the one
`persistence.tier == "trace_local"` assertion → `"git_only"` (+ method renamed for accuracy).
`test_execution_loop.py` — a module-level store redirect (`setUpModule`/`tearDownModule` point
`ORA_EXECUTION_RECORDS_DIR`/`ORA_EXECUTION_LEDGER_PATH` at a tempdir so the suite never touches the real
store) + two wiring tests (`test_converged_turn_is_git_only`, `test_escalation_persists_durable_note_and_ledger`).

---

## 3. Adversarial pre-check (the gate the judge would run) — 1 BLOCKER found + FOLDED

Ran a 4-lens adversarial pre-check (redaction-leak / promotion-ordering / stealth-raise-parity /
purge-portability-concurrency), each finding independently verified against the code. **All four lenses
converged on the SAME real blocker (0 rejected, 0 uncertain):**

- **[BLOCKER] planning-block redaction leak.** `redact_for_durable` scrubbed execution/task/verification but
  **omitted `planning`**, while `render_for_review` (which produces the durable-note body) emits
  `planning.converged_brief.acceptance_criteria` verbatim. `acceptance_criteria` is model-authored prose
  *derived from the (possibly sensitive) instruction* (`risk_gate.run_criteria_pass` feeds the raw instruction
  to the model), and `planning` is populated on exactly the standard+/high-risk turns that promote to
  `durable_note`. So on a `sensitive`/`secret` turn, the instruction/producer_claim/findings were
  descriptor-ized but the criteria leaked into the durable note **in the clear** — defeating the module's own
  guarantee. *(The approved design's §1.6 scrub-target table shared this blind spot — the pre-check caught
  what neither the design gate nor I saw.)*
  - **FOLD:** `redact_for_durable` now deep-copies `packet.planning` and runs `converged_brief`'s free-text
    fields (`acceptance_criteria` [str OR list of bullets], `approach`, `known_risks`, `review_questions`)
    through `_scrub_free_value` (a str/list-aware wrapper over `_scrub_free_text`) at the same `level`, and
    passes `planning=<scrubbed>` into `dataclasses.replace`; the redaction descriptor now lists `planning`.
    Two regression tests added (redactor-level + note-body-level PII absence). Hand-verified + re-run green.

---

## 4. Parity

- Pre-edit baseline captured in the pristine scout (code-identical to `b4b257dd` — the intervening commits are
  docs-only): **3869 tests, 27 FAIL/ERROR** (the documented 22 FAIL + 5 ERROR environmental set:
  lens-integrity, retry-fallback, openai-images, mode-relationship-priorities, user-settings, visual-routing).
- Post-edit full suite, re-run on the FINAL post-fold code (`ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`):
  **3907 tests, 27 FAIL/ERROR — sorted name lists IDENTICAL to baseline. ZERO new, ZERO disappeared.**
- Net new tests: **+38** (all passing). Diff whitespace-clean.

---

## 5. Files touched

| File | Change |
|---|---|
| `orchestrator/execution_persistence.py` | **NEW** — the §14 module (decide/redact/ledger/note/purge/persist) |
| `orchestrator/tests/test_execution_persistence.py` | **NEW** — 37 tests |
| `orchestrator/execution_loop.py` | persist at the terminal (before write_packet) + source-read branch; `escalation_withheld` marker; `full_signals` |
| `orchestrator/execution_packet.py` | build default tier `trace_local`→`git_only` |
| `orchestrator/conversation_closeout.py` | new Layer 10 → `purge_conversation` |
| `.gitignore` | `data/execution-records/` (non-git zero-residue guarantee) |
| `orchestrator/tests/test_execution_loop.py` | store redirect + 2 wiring tests |
| `orchestrator/tests/test_execution_packet.py` | `trace_local`→`git_only` assertion |

---

## 6. Design-gate conditions honored

- **Rev-2 P1 (non-git store):** `.gitignore` adds `data/execution-records/`; verified `git check-ignore`
  matches the ledger AND a nested note path (unit test + hand-run). The zero-residue guarantee is now real.
- **Rev-3 P2 (effective-ignore test):** the gitignore guard asserts `git check-ignore` behavior, not text
  presence, for both paths.
- **Rebase condition:** implemented off CURRENT origin/main `b4b257dd`.

## 7. GOTCHAs honored
- `reversible: true` at high-risk left as-is (§6 gate, spec-correct).
- The store env-overrides (`ORA_EXECUTION_RECORDS_DIR` / `ORA_EXECUTION_LEDGER_PATH`) keep every test hermetic
  — no test touches the real `~/ora/data/execution-records/` or the live server's store.
- `persist_packet` fires on the main terminal thread (stealth threadlocal correct); never raises; loop-only.

**ON APPROVAL:** re-fetch origin/main (advances via concurrent sessions), rebase, branch → commit → push → PR
→ squash-merge → delete branch (local+remote) → prune worktree → fast-forward `~/ora` main (ff-only); report
PR # + bare SHA.
