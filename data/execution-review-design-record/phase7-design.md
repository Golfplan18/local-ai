# Execution Review — Phase 7 DESIGN PACKET: Tiered persistence (spec §14 + §15 Phase 7)

*Status: **DESIGN GATE PASSED — approved-with-conditions** (Revision 3: P2 test-strengthening folded; Rev-2
block + Rev-1 critic folds). NO code written. Scouted read-only @ `/Users/oracle/ora-worktrees/phase7-scout`
(detached @ `8ae29eb3`). Current origin/main = `b4b257dd` (docs-only PRs #189/#190 past Phase 6 — touch no
Phase-7 substrate; all anchors hold). Implementation: FRESH worktree off CURRENT origin/main (re-fetch +
**rebase onto `b4b257dd`** first).*

---

## ⚖ Revision 3 — design-gate APPROVAL condition (P2), folded

Judge verdict: **APPROVE WITH CONDITIONS.** The prior P1 (non-git store) + minor (parity wording) are confirmed
folded. Two conditions:

- **[P2 — verify effective ignore, not text presence]** The Rev-2 gitignore-guard test asserted `.gitignore`
  *contains* the pattern; the real invariant is that **git actually treats the store paths as ignored**.
  **FOLD:** the guard now asserts `git check-ignore` returns a match for BOTH
  `data/execution-records/execution-ledger.jsonl` AND a nested note path — behavior, not text (§10/§9).
- **[Condition — rebase]** Implement on CURRENT origin/main. Confirmed tip = `b4b257dd` (PR #190, docs-only);
  local `main` is behind at `8ae29eb3`. The impl worktree branches off / rebases onto `b4b257dd`; no Phase-7
  substrate changed, so all file:line anchors hold.

---

## ⚖ Revision 2 — judge design-gate BLOCK, folded

Judge verdict: **BLOCK** (1 P1) + 1 minor condition. Both folded:

- **[P1 — the non-git store is not actually non-git]** The whole true-zero-residue guarantee (§7) rests on
  `data/execution-records/` being outside git, but `.gitignore` does not cover that path (verified:
  `git check-ignore data/execution-records/…` matches nothing), and Rev-1's projected-files list omitted a
  `.gitignore` change. Without the rule the store is git-tracked — notes/ledger could be accidentally
  committed (`git add -A`) and then closeout's `rmtree` cannot reach git history → the residue this store
  exists to prevent. **FOLD:** Phase 7 **adds `data/execution-records/` to `.gitignore`** (a one-line rule
  matching the existing `data/oversight/` / `data/pipeline-traces/` / `data/tool-events.jsonl` convention,
  `.gitignore:46/66/146`). `.gitignore` is added to the projected touched files (§11); the non-git guarantee
  is now stated as **contingent on that ignore rule** (§4/§7); a test asserts the pattern is present so it
  can't be silently removed (§10); the impl checklist verifies `git check-ignore` matches the store path (§9).
- **[Minor — tighten "byte-identical"]** The flag-OFF claim is **response/control-flow parity**, not
  byte-identical output: the trace JSON's `persistence.tier` value does change `trace_local`→`git_only` (which
  nothing reads). **FOLD:** wording corrected in §0/§2/§7.

*(Judge-confirmed sound, no change needed: the `tool_events` turn-context conversation_id source, the closeout
purge shape vs existing layers, and the retention "exempt-by-omission" claim.)*

---

## ⚖ Revision 1 — folds from the adversarial completeness-critic (pre-check the judge would run)

A 5-lens completeness-critic (× per-finding verify) returned **9 REAL findings** (2 blocker, 4 major,
3 minor) + 6 correctly-rejected. All 9 folded here (+ 2 self-folds), BEFORE this reaches the judge:

- **[BLOCKER] `sensitive` free text written in the clear.** `redact_for_durable` originally applied only
  `scrub_content` (secret-token regexes) to a `sensitive`-classed packet — no PII/regulated-data redaction,
  violating §7/§14/§17. **FOLD:** three-layer redactor keyed on the TRUE max sensitivity, mirroring
  `_redact_for_record` — `secret`→drop-to-existence, `sensitive`→`[SENSITIVE:N chars]` descriptors,
  `private`/`public`→`scrub_content`-and-keep (§5).
- **[BLOCKER] `conversation_id` empty in production.** The ledger id + note key were sourced from
  `context_pkg`, which never carries `conversation_id`/`task_id` at the terminal → both stealth backstops
  silently no-op. **FOLD:** source it from `tool_events.get_turn_context()["conversation_id"]` — the same id
  the tool-event sink stamps and closeout keys on (seeded at step 2 from the trace dir, `boot.py:7220`) (§6/§7).
- **[MAJOR] `redact_for_durable` can't read `max_sensitivity`.** It isn't a packet field. **FOLD:** thread the
  folded `sig` (in scope at `execution_loop.py:850`) into `persist_packet`→`redact_for_durable` (§2/§5).
- **[MAJOR] durable note kept the claim where the precedent drops it.** **FOLD:** durable note is now strictly
  ≥ the trace-local conservatism (sensitive→descriptor, secret→drop); the public/private scrub-and-keep is
  justified against the *different-purpose* handback precedent (§5).
- **[MAJOR] filename prefix-match fragile (raw-vs-slug).** **FOLD:** durable notes live in a **per-conversation
  subdirectory** purged by `rmtree` (mirrors closeout Layer 5 exactly — a directory match, not a fragile
  filename-prefix match); write side and purge side share one id transform (§4/§6).
- **[MINOR] git-history residue.** A vault-git durable note leaves content in git history that a working-tree
  delete can't reach. **FOLD:** durable notes now live in the **non-git `data/execution-records/`** operational
  store → the closeout `rmtree` achieves true zero-residue; the vault option is retained as OQ1 with its
  Layer-5-equivalent residue stated honestly (§4).
- **[MINOR] "exempt glob" doesn't exist.** **FOLD:** corrected to **exempt-by-omission** — nothing globs/sweeps
  the store; the ledger is simply not in `ROTATABLE_JSONL` (§1.3/§6).
- **[MINOR] "redacted render_for_review body" type mismatch.** The renderer takes a packet; the redactor
  returned a dict. **FOLD:** `redact_for_durable` returns a **scrubbed shallow-copy ExecutionPacket**;
  `write_durable_note` renders THAT copy (never the raw packet) (§2/§5).
- **Self-fold:** source-read-only owed-provenance turns → `git_only` (routine research; the Phase-8 provenance
  deferral is systemic, not per-turn signal), tightening `ledger_line` to mutation-turn degrades (§3, OQ3).
- **Self-fold (rejected-but-cheap):** `persist_packet` sets the tier BEFORE `write_packet` so the trace JSON
  records the correct §14 tier (§2 fire point).

**Consolidation:** all execution-review durable persistence now lives under one non-git operational store
`data/execution-records/` (ledger + notes), purged by one new closeout layer. This resolved the durable-note
location, ledger location, git-history-residue, and glob-safety questions together.

*(Rejected findings, verified sound: trace-tier-stale [nothing reads `persistence.tier`; self-folded anyway
as cheap], injected-root-param [call-time `_rp` read is the Layers-6a/8/9 idiom], same-family-None-reviewer
[never-raises covers it; defensive `.get()` stated], ledger-noise [genuine OQ3 knob — narrower default
adopted], packet-has-no-conv-id [subsumed by the conversation_id fold], persist-preempts-handback [never-raises
+ `write_packet` already precedes the handback].)*

---

## 0. The one-paragraph statement

Phase 7 gives every `ExecutionPacket` a real **§14 durable-memory tier** — `git_only` / `ledger_line` /
`durable_note` — computed by a **promotion function** from the packet's *own already-populated signals*
(`status`, `loop.stop_condition`, `loop.escalation`, `verification.findings[].class`), with
**sensitivity-driven redaction** (spec §7 axis) applied before any durable write, routing retention + stealth
purge **through Ora's existing memory-pruning discipline rather than duplicating it**. The default is the
cheapest tier (`git_only` = nothing beyond git history + the already-retention-swept trace packet); a turn is
promoted **only** when genuinely informative — it **escalated**, **failed to converge**, or carries a
**plan-level finding**. One new consolidated module `orchestrator/execution_persistence.py` (a) decides the
tier, (b) redacts by reusing the *already-built* `tool_events` scrub/sensitivity primitives (three-layer,
keyed on the true max sensitivity), (c) appends one compact line to a single consolidated
`data/execution-records/execution-ledger.jsonl`, and (d) for the durable tier writes one self-contained,
**non-RAG-indexed, non-git** markdown execution record under `data/execution-records/<conversation>/`. It fires
**once, at the `run_loop` terminal**, is **stealth-gated + never-raises** exactly like the escalation-handback
precedent, and preserves **Phase-6 response + control-flow parity whenever the loop flag is OFF or the turn is
self-evidencing** (both compute `git_only` and write nothing durable; the only on-disk delta is the trace
JSON's inert `persistence.tier` value). The store is kept out of git by a `.gitignore` rule Phase 7 adds (§11).

---

## 1. Substrate scout — what already exists (hand-verified file:line)

### 1.1 The Phase-7 fill points (the packet)
- **`ExecutionPacket.persistence`** — `execution_packet.py:134` — the reserved block.
- **The hardcoded literal** — `execution_packet.py:406` (inside `build_execution_packet`, def @ 322):
  `persistence={"tier": "trace_local", "redacted": "phase3-public-safe-source-reads"}`. **`"trace_local"` is
  NOT a §14 tier** — a Phase-4 placeholder. `git_only`/`ledger_line`/`durable_note` appear nowhere yet.
- **`write_packet`** — `execution_packet.py:417` — writes `execution-packet.json` (JSON) to `trace_dir` only;
  guards `packet is None or not trace_dir` (423); best-effort `_mark_failure` (432). Docstring (419): *"never a
  vault or durable store (Phase 7 owns durable persistence)."*
- **`construct_and_write`** — `execution_packet.py:518` — the common self-evidencing terminal (build +
  `write_packet`, trace-local, guarded, never-raises). Caller gates stealth.
- **`populate_loop_fields`** — `execution_packet.py:462` — sets the **promotion signals**: `packet.loop=loop`
  (505); `sc=='criteria_met'→status='converged'` (507-508); `sc=='max_iterations_escalated'→status='escalated'`
  (509-510). **Does NOT touch `persistence`.**
- **`ExecutionPacket.status`** — `:120` — `in_progress | converged | escalated`.
- **`render_for_review`** — `:236` — §12 evidence-first renderer; **no redaction inside** — renders the full
  `producer_claim.summary` (281-285).
- **`_mark_failure`** — `:306` → `tool_events._note_failure` (`tool_events.py:429`) — the never-raises marker
  idiom, distinct `where` tag per site.
- **`to_dict()`** — `:150` — `dataclasses.asdict` deep-copies EVERYTHING → a naïve durable dump leaks the full
  deliverable; the scrub must run on a copy BEFORE any durable write.
- **`ExecutionPacket` has NO `conversation_id` field** — only `task_id` (117), `= context_pkg.get('task_id')
  or context_pkg.get('conversation_id') or ''` (388-389). The durable conversation_id comes from the turn
  context, not the packet (§6).

### 1.2 The fire point + the durable-write precedent (the loop)
- **`_execution_review_terminal`** — `boot.py:9070` — `if loop_enabled() and should_engage(ro):` (9084) →
  build (9089) + `run_loop(..., actuator=None)` (9095); ELSE → `construct_and_write` (9108). **Mutually
  exclusive per turn.** Returns `response` on any error (9113). Called at `boot.py:9520` (run_pipeline) and
  `server.py:3006` (SSE) — **both main terminal threads, never inside a Gear-4 worker** (verified).
- **`run_loop` terminal** — `execution_loop.py:1058-1067` — `populate_loop_fields` (1058) → `packet_path =
  write_packet(packet, trace_dir)` (1060) → IF `escalation is not None`: `handback_reference` (1063) →
  `push_handback` (1067). **THE fire point.** (Gotcha: an escalation can be *downgraded* to degrade at
  1024-1036 AFTER `stop_condition` is set — the tier decision fires at 1058+, post-downgrade.)
- **`loop_state`** — `stop_condition='criteria_met'` (912) / `'max_iterations_escalated'` (925) / `None` on
  degrade (930) or escalation-withheld (1028-1033); `escalation` dict (1000-1023) or `None` (1029).
- **`route_findings`** — `:603` — splits by `class` → `(execution_level, plan_level)`; `_parse_finding` (512)
  defaults `class` to `execution_level`.
- **`push_handback`** — `:780` — **the durable-write template**: checks `_is_stealth_context()` FIRST (795),
  returns `False` ("no durable residue") before either backend (the primary `oversight_queue.add_entry` has no
  stealth guard; the fallback self-guards); never raises (`_mark_failure` 815). `handback_reference` (752)
  sources `cid` from `context_pkg` (759) — **which is empty in production (§6 finding)** — and sets it
  top-level (765).
- **`redacted_review_summary`** — `:737` — the existing scrub-before-handback: renders then **drops the whole
  `UNVERIFIED PRODUCER CLAIM` fence** (a triage reference, not a record), caps at `_REDACTED_SUMMARY_CAP=4000`.
- **Triple stealth defense:** caller `if not stealth` (terminal) + `run_loop` entry `847` + `push_handback`'s
  own `_is_stealth_context` (795).
- **`loop_enabled`** — `:83` — `ORA_EXECUTION_LOOP` default OFF (read at boot.py:9084/9408, server.py:2891).
- **`should_engage`** — `:112` — True only on `any_mutation OR source_read_suspected`.

### 1.3 The memory-pruning discipline to ROUTE THROUGH (spec §14: do not duplicate)
- **retention rotation** — `retention_sweeper.py:87` `ROTATABLE_JSONL` is a **hardcoded 3-element allowlist**
  (`model-catalog-changes.jsonl`, `compaction-events.jsonl`, `tool_events.global_sink_path()`); `_sweep_jsonl`
  (221) iterates **only** that list. **There is NO exempt-glob** — the sweeper never scans `data/oversight/`
  or any dir but `TRACES_DIR/LOGS_DIR/…/SESSIONS_DIR`. So a new sink is **exempt-by-omission**: not listed →
  not rotated (the docstring's `data/oversight/*.jsonl` at 41-50 is prose, not code).
- **THE decisive constraint — retention-vs-purge tension** (`retention_sweeper.py:41-50` docstring): a sink
  cannot be both gzip-rotated AND stealth-purged-in-place (gzip archives put lines beyond the purge's reach).
  A stealth-sensitive ledger must therefore be exempt-by-omission (not in `ROTATABLE_JSONL`).
- **stealth purge** — `conversation_closeout.py:_purge_stealth` (195), Layers 1-9. Layer 9 (482-511): the
  reusable JSONL-scrub loop `for log_name in ("events.jsonl","actions.jsonl","human-queue.jsonl")` (484) —
  keep lines where `rec.get('conversation_id') != purged_id`, atomic `tmp.replace`. Layer 6a (416): same over
  `tool_events.global_sink_path()`. **Layer 5 (288): the ONLY vault-content layer —
  `shutil.rmtree(<root>/<conversation_id>)`, keyed by a per-conversation SUBDIR** (the pattern the durable-note
  purge mirrors). All newer layers (6a/8/9) read `_rp` roots **at call time** (no injected param).
- **engram promotion** — `tools/engram_promotion.py:224` `staging_note_to_engram` → `~/Documents/vault/
  Engrams/<date>_<slug>.md`, **RAG-indexed** (`knowledge_index.index_file`, 246), HARDCODED `expanduser` paths
  (37-39). Disqualified as the durable-note form (§4).

### 1.4 The consolidated-JSONL + rooting idiom (the ledger)
- **`runtime_paths.DATA_DIR_STR`** (`:44`, `DATA_DIR` @16 = `ORA_HOME/data`) — the cross-platform,
  ORA_HOME-relocatable data root.
- **`tool_events.global_sink_path()`** (`tool_events.py:496`) — env-override-then-default single-source path
  helper — the model for `ledger_sink_path()`.
- **The atomic single-line append core** — `tool_events.record` (`:564-570`): `os.open(path,
  O_WRONLY|O_APPEND|O_CREAT,0o644)` + `os.write` + `os.close` — the strongest multi-process cross-platform
  single-line append (server + daemon + Gear-4 workers). Reuse; do NOT copy the un-locked `open('a')` idiom
  (oversight_events' in-process `threading.Lock` is useless across processes).
- **`runtime_paths.locked_file`** (`:100`) — cross-platform advisory lock (fcntl/msvcrt) if RMW is ever needed.
- **`os.replace`** — atomic full-file swap (POSIX + Windows) — the durable-note write pattern.
- **Dual-import shim** (`try: import runtime_paths / except: from orchestrator import runtime_paths`) — copy
  verbatim.

### 1.5 The sensitivity/redaction plumbing — the redaction driver (all reusable)
- **`SENSITIVITY=("public","private","sensitive","secret")`** (`:91`), `_SENS_RANK` (99), `max_sensitivity`
  (117, default `secret`). **Never string-compare — use the rank.**
- **`resolve_path_sensitivity(path)`** (`:327`) — boundary-anchored path→level (`secret|sensitive|private`,
  never `public`; unknown→`sensitive`; error→`secret`). Cross-platform.
- **`scrub_content(text)->(text,found)`** (`:362`) — the free-text **secret** scrubber (`_SCRUB_PATTERNS`:
  `sk-`/`ghp_`/AWS/Slack/`bearer`/URL-userinfo/`password|api_key|secret|token|credential=…`). **Catches only
  secret token formats — NOT PII/regulated content.**
- **`_redact_for_record(event)`** (`:466`) — **the three-layer model to mirror**: `secret`→existence-only
  (args/reads dropped); `sensitive`→`[SENSITIVE:N chars]` descriptors (480-490); `private/public`→
  `scrub_content`. Operates on a tool-event dict, does NOT recurse into packet blocks — so Phase 7 needs a
  packet-shaped redactor reusing the same three layers.
- **Phase-1 upstream secret gate** — `tool_events.gate()` (839): a `secret` action is blocked/queued before it
  runs → never a recorded source_read. This is the mechanism behind §7 "secret never enters a packet" — for
  path/read-derived secrets. It does NOT cover a secret quoted in model free-text (that residual is
  `scrub_content`'s job).
- **Phase-3 public-safe + cap** — `_public_safe_candidates` (`risk_gate.py:162`) → `source_reads` are already
  public-safe; `record_route_observed` (983) **caps the recorded event sensitivity at `sensitive`** (1043-1045),
  but the TRUE max survives on `signals.max_sensitivity` / `route_signals.max_sensitivity`. **The redactor must
  read the true max from the folded `signals`, not the capped event stamp.**
- **The true max source** — `max_sensitivity` lives on the folded `signals` dict (`risk_gate.py:566,605-606`),
  which rides on `ro` → is bound as `sig` at `execution_loop.py:850` (in scope at the fire point). It is NOT a
  packet field. Phase 7 threads `sig` into the redactor.

### 1.6 Packet fields that can carry sensitive/secret content (scrub targets)
| Field | Kind | Handling by tier (§5) |
|---|---|---|
| `execution.producer_claim.summary` | **free text** (deliverable ≤100k) | public/private→`scrub_content`+cap+keep; sensitive→descriptor; secret→drop |
| `task.instruction` | **free text** (prompt ≤20k) | same three-layer |
| `verification.findings[].description` | **free text** (reviewer, P6) | same three-layer |
| `evidence_lanes[].result.checks[].stdout_tail` | captured output | already `scrub_content`-redacted (`evidence_runner.py:775`) |
| `execution.source_reads` | structured/path | already public-safe (Phase 3); re-assert |
| `execution.delta.ref` / `trace_ref` | path | `resolve_path_sensitivity`; trace path → `private` (kept) |

---

## 2. Core design call — Architecture A: one consolidated `execution_persistence.py`, fired at the loop terminal

New module `orchestrator/execution_persistence.py` (mirrors `retention_sweeper.py` as its own module) exposes:

1. `decide_tier(packet) -> str` — the promotion function (§3), defensive `.get()` throughout.
2. `redact_for_durable(packet, *, max_sensitivity) -> ExecutionPacket` — returns a **scrubbed shallow-copy
   packet** (three-layer, §5). Copy semantics so the live packet + its trace JSON are untouched.
3. `ledger_sink_path() -> str` / `execution_records_dir() -> str` — env-override-then-default, runtime_paths-
   rooted (§6).
4. `append_ledger_line(line, *, conversation_id, stealth) -> bool` — O_APPEND, stealth-gated (§6).
5. `write_durable_note(redacted_packet, *, conversation_id, stealth) -> str | None` — one non-git,
   non-RAG-indexed markdown record in a per-conversation subdir (§4).
6. `purge_conversation(conversation_id) -> dict` — the single owner of the store's stealth purge (the new
   closeout layer calls THIS): `rmtree` the conversation subdir + scrub the ledger jsonl by `conversation_id`.
7. `persist_packet(packet, *, sig, context_pkg, trace_dir, stealth, now_iso) -> str` — the entry point:
   `decide_tier` → **set `packet.persistence`** → (if promoted) `redact_for_durable` → `append_ledger_line`
   and/or `write_durable_note`. **NEVER raises** (`_mark_failure(where='execution_packet_durable_persist')`);
   returns the tier, `git_only` on any failure.

**Fire point:** `run_loop`, at the terminal — **BEFORE `write_packet`** so the trace JSON records the correct
§14 tier (self-fold): `populate_loop_fields` (1058) → **`persist_packet(...)`** (sets `packet.persistence` +
does the durable writes) → `write_packet` (1060, now records the correct tier) → handback (1062-1067). Also
inserted on the source-read-only early-write branch (879). The durable writes use the **deterministic**
`trace_ref = os.path.join(trace_dir, "execution-packet.json")` (self-contained — no dependency on
`write_packet`'s return, so the note survives the 30-day trace sweep). `persist_packet` re-checks
`_is_stealth_context()` itself (defense-in-depth) and stays isolated from the handback (its never-raises
contract means a caught failure returns `git_only`, never skipping the escalation).

**Loop-only writes, universal `git_only` default.** A self-evidencing packet (`status=in_progress`,
`loop=None`, `findings=[]`) → `decide_tier` = `git_only` unconditionally → no durable write. So durable
**writes** are loop-only; the `git_only` **tier** is universal (the build-time default, §3.4). *(Answer to the
kickoff's loop-only-vs-both question: the mechanism is loop-scoped; every packet still carries a correct §14
tier; a self-evidencing turn is git_only by construction — spec-correct "do not default to durable." Adding the
promoter to the hot common path would be dead code; if a future phase ever makes a self-evidencing turn
durable-worthy, the same `persist_packet` is added then.)*

**New module, not extend `execution_packet.py`:** persistence is a distinct concern with its own I/O, its own
store, and integration into `conversation_closeout` — matches the `retention_sweeper.py` precedent (OQ7).

---

## 3. Design pillar 1 — the promotion rule (`decide_tier`)

The three §14 durable triggers map 1:1 onto signals already on the packet after `populate_loop_fields`.
Default is the cheapest tier; nothing is durable unless it earns it.

### 3.1 `durable_note` — genuinely informative (the §14 triggers, verbatim)
ANY of:
- **escalated** — `packet.status == "escalated"` OR `(packet.loop or {}).get("escalation") is not None` (covers
  §12 `policy_human_review`).
- **failed to converge (hard)** — the **escalation-withheld** case (`execution_loop.py:1028-1033`, an evidence
  escalation with no creatable §13 branch): the loop tried to escalate and couldn't — genuinely informative.
  Detected via a new additive `loop_state["escalation_withheld"] = True` at 1033 (a one-line marker, so
  `decide_tier` reads a flag, not a fragile note-substring — OQ5).
- **plan-level finding** — any `f.get("class") == "plan_level"` in `verification.findings` — **even if
  converged** (§14: a plan-level finding is worth remembering).

### 3.2 `ledger_line` — a mutation turn that degraded without converging (a breadcrumb)
Else, `ledger_line` iff: `any_mutation` is True AND `stop_condition is None` AND not escalation-withheld — the
degrade-to-text-review case (`execution_loop.py:930`: the loop engaged, mutated, but couldn't converge or
verify). A "loop ran, mutated, unverified" breadcrumb — worth a searchable one-liner, not a full note.

### 3.3 `git_only` — the default cheapest tier (routine)
Else `git_only`: a self-evidencing turn; a converged mutation turn (`criteria_met`, any iteration count — it
converged, so it is a clean pass whose record is git history + the retention-swept trace); **and a
source-read-only owed-provenance turn** (`execution_loop.py:869-880`, `any_mutation` False) — a routine
research/fact-check turn whose only "non-convergence" is the *systemic* Phase-8 provenance deferral, not
per-turn signal (self-fold; see OQ3 for the counter-argument). Nothing durable is written.

### 3.4 The default is set at build time
`build_execution_packet:406` stops hardcoding `"trace_local"` and sets the §14 default `persistence =
{"tier": TIER_GIT_ONLY, "redacted": None}`. `persist_packet` recomputes/promotes after the loop. Rationale:
`"trace_local"` is not a valid §14 tier; `git_only` is the correct cheapest default. *(The one common-path
change — a trace-JSON field value nothing downstream reads; §10 covers the test impact.)*

### 3.5 The ledger is the universal index of non-git_only turns
A `durable_note` also appends a `ledger_line` (with `note_ref` → the record). So the single ledger is the one
place to grep "which turns produced a durable record / degraded," serving §14's "one consolidated file."
Net writes: `git_only`→nothing; `ledger_line`→1 line; `durable_note`→1 line (+`note_ref`) + 1 record.

**Truth table (the test spec — reads use defensive `.get()`):**

| any_mutation | status | stop_condition | escalation / withheld | plan-level finding | → tier |
|---|---|---|---|---|---|
| — | in_progress | (self-evidencing) | — | — | **git_only** |
| False | in_progress | None (source-read-only owed) | — | — | **git_only** |
| True | converged | criteria_met | none | no | **git_only** |
| True | converged | criteria_met | none | **yes** | **durable_note** |
| True | escalated | max_iterations_escalated | dict | any | **durable_note** |
| True | in_progress | None | **withheld=True** | any | **durable_note** |
| True | in_progress | None (degrade-to-text) | none | no | **ledger_line** |

*(The tier boundaries are provisional — flagged retunable; the empirical question is ledger volume once the
loop runs live. OQ3 presents the noise/signal knob.)*

---

## 4. Design pillar 2 — what a `durable_note` PHYSICALLY is (headline OQ1)

**Recommendation: a self-contained, NON-RAG-indexed, NON-git markdown execution record** at
`data/execution-records/<fs_safe(conversation_id)>/<task_id>__<iso>.md`, rooted via `runtime_paths.DATA_DIR_STR`,
with flat §9 frontmatter and a §12 evidence-first **redacted** body. **Explicitly NOT the engram/vault-RAG
path, and NOT the git-tracked vault** (Rev-1 fold #6).

**Why `data/execution-records/` (non-git, operational) over `vault/`:**
- **True stealth zero-residue.** The store is kept **out of git** by a `.gitignore` rule Phase 7 adds
  (`data/execution-records/`, §11 — matching the existing `data/oversight/` / `data/pipeline-traces/`
  convention, `.gitignore:66/46`), so the files are never committed and the closeout `rmtree` of the
  conversation subdir leaves *nothing* — no git-history residue. A vault-git note, by contrast, leaves content
  in vault git history that a working-tree delete can't reach (the same limitation as existing Layer-5 Session
  exports — see OQ1). **The guarantee is contingent on that ignore rule** (verified in the impl checklist, §9).
- **Subsystem consistency.** All other execution-review persistence (traces, tool-events, the ledger) lives
  under `data/`. Execution records are **operational** memory, not user knowledge — `data/` is their home.
- **§9 satisfied.** §9's ground state is "a folder of Markdown files" (Obsidian/git are *optional* layers);
  `data/execution-records/*.md` is exactly that — greppable, self-contained, human-readable.

**Why NOT `engram_promotion` (the tempting reuse):** three hand-verified disqualifiers, each fatal to §14's
own goal — (1) **RAG pollution:** every engram is `knowledge_index.index_file`'d (246) into concept-RAG — the
exact retrieval noise §14 exists to prevent; execution records must stay off the retrieval surface. (2)
**Stealth-purge gap:** flat `Engrams/` dir, no conversation keying → unreachable by any vault stealth layer.
(3) **Non-portable:** hardcoded `expanduser` paths (37-39). This is a deliberate **reuse-over-parallel
exception** ([[feedback-reuse-over-parallel]]) — the primitive's defining behaviour (RAG indexing) is
*harmful* to the goal. We DO reuse the cheaper primitives (markdown ground state, the redaction chain).

**Per-conversation subdirectory (Rev-1 fold #8):** notes live in `…/execution-records/<id-dir>/…`, and the
stealth purge does `rmtree(execution-records/<id-dir>)` — a **directory match mirroring Layer 5 exactly**, not
a fragile filename-prefix match. The write side and purge side apply **the identical id transform** (a shared
`_fs_safe(conversation_id)` helper — a filesystem-safe fold for portability, since a raw id can carry a
Windows-invalid `:`); because both sides call the same helper, they always agree.

**Content (self-contained — survives the 30-day trace sweep):** flat frontmatter (`task_id`, `created`,
`status`, `risk_tier`, `reversible`, `tier`, `conversation_id`, `tags`) + the **redacted** `render_for_review`
body — produced by rendering the *scrubbed shallow-copy packet* from `redact_for_durable`, never the raw
packet (Rev-1 fold #3/#9) — + a deterministic `trace_ref` marked "may be swept after 30d." §16-3 preserved:
the producer claim stays labeled unverified, never elevated.

**Escalation-handback synergy (OQ6):** escalated turns always earn a `durable_note`; `handback_reference` can
point its reference at the durable note (survives) instead of the 30-day-swept trace JSON — minimal, optional.

---

## 5. Design pillar 3 — sensitivity-driven redaction (three-layer, reuse-not-reinvent) — Rev-1 folds #1/#2/#5

`redact_for_durable(packet, *, max_sensitivity) -> ExecutionPacket` returns a **scrubbed shallow-copy packet**
(so the renderer, ledger, and note all consume a redacted object; the live packet + trace JSON are untouched).
`max_sensitivity` is the **TRUE max** from the folded `sig` (`sig.get("max_sensitivity")`, threaded into
`persist_packet`; §1.5), **not** the Phase-3-capped event stamp.

**Three layers, keyed on `max_sensitivity`, mirroring `_redact_for_record` (`tool_events.py:466-493`)** — over
the free-text fields `producer_claim.summary`, `task.instruction`, `findings[].description`:
- **`secret`** — DROP to an existence-only marker (`"[SECRET — content withheld]"`). This should be
  **unreachable** (upstream-gated, §1.5); Phase 7 asserts it and drops as belt-and-suspenders.
- **`sensitive`** — replace each free-text field with a **descriptor** `"[SENSITIVE:N chars — withheld]"`
  (mirrors `_redact_for_record:480-490`). PII / regulated / production data is thereby **never written durably
  in the clear** (Rev-1 fold #1 — §7 "ALWAYS redacted from durable storage" + §14 + §17 satisfied).
- **`private` / `public`** — `scrub_content` the free text (catch inline secret tokens) and **keep** it, capped
  (`_DURABLE_SUMMARY_CAP`, provisional 4000). `private` in the user's **own private** operational store is
  spec-permitted (§7: private = "not for durable *public* storage").

**Path fields** (`delta.ref`, `trace_ref`) → `resolve_path_sensitivity`; a `secret`/`sensitive` path → a
descriptor; trace paths resolve `private` and are kept. **`source_reads`** → already public-safe (Phase 3);
re-assert each entry is public before persisting (durable > trace-local — don't assume the trace guarantee
carries).

**The ledger one-line `summary`** derives from the *scrubbed-copy* producer summary (so `[SENSITIVE…]` /
`[SECRET…]` propagate), hard-truncated (~200 chars). **`persistence.redacted`** records the layer applied +
the true max, e.g. `"three-layer@sensitive: producer/instruction/findings→descriptors; source_reads
public-safe; secret=none"` (replacing `"phase3-public-safe-source-reads"`).

**Divergence from the handback precedent, justified (Rev-1 fold #2):** `redacted_review_summary` *drops the
claim unconditionally* because the handback is a **triage reference** for the human queue. The durable_note is
the **record** — §16-3 wants the claim *present but labeled unverified* — so it keeps a scrubbed claim for
public/private and drops/descriptor-izes it for sensitive/secret. This is **strictly ≥ the trace-local
conservatism** and spec-faithful (sensitive redacted, secret absent), while remaining a useful record.

**Honesty (§16/§17):** the **primary** guarantee that `secret` never reaches durable storage is upstream (§7
gate + public-safe source_reads); `scrub_content` is the **belt** — pattern-based, so a *novel* secret format
quoted in model free-text could slip through the `public`/`private` layer. The `sensitive` descriptor layer is
content-agnostic (drops the whole field) so it does not share that limitation. Stated, not overclaimed.

---

## 6. Design pillar 4 — the ledger (location, shape, append, retention, stealth)

**Location:** `data/execution-records/execution-ledger.jsonl` — consolidated with the durable notes under the
one operational store, purged by the one new closeout layer (§7). **Exempt from rotation by omission** (Rev-1
fold #7): it is not in `ROTATABLE_JSONL` and nothing globs/sweeps `data/execution-records/` — so it is neither
rotated nor at risk of a gzip archive escaping the stealth purge (the retention-vs-purge constraint, §1.3).
Growth is bounded by the promotion rule (only degraded mutation turns + durable_notes append). **No code change
to `retention_sweeper.py`** (a one-line docstring note is optional).

**Path helper:** `ledger_sink_path()` = `os.environ.get("ORA_EXECUTION_LEDGER_PATH") or
os.path.join(execution_records_dir(), "execution-ledger.jsonl")` (mirrors `global_sink_path`).

**`conversation_id` source (Rev-1 fold #4):** `tool_events.get_turn_context().get("conversation_id")` — the
SAME id the tool-event sink stamps and closeout Layer 9/6a keys on (seeded at step 2 from the trace dir,
`boot.py:7220`; by the server as `panel_id`, `server.py:3306/3738`; and the framework path, `boot.py:9247`).
**Not `context_pkg`** (never carries it at the terminal) and **not `packet.task_id`** (may differ). This makes
the ledger's id match the purge target by construction. *(Honest scope: the write-time stealth gate is the
**unconditional primary** guarantee; the post-hoc closeout backstop matches only when the turn context carries
a conversation_id — the same condition under which tool-events themselves are purgeable, so the ledger's
purgeability is exactly as good as the tool-event sink's.)*

**Line shape (compact projection — §9 small+flat; large artifacts referenced):**
```json
{"ts":"<iso-utc>","task_id":"…","conversation_id":"…","tier":"ledger_line|durable_note",
 "status":"…","stop_condition":"…|null","risk_tier":"…","iteration":N,"escalated":bool,
 "finding_classes":["plan_level",…],"summary":"<scrubbed ≤200>","trace_ref":"…|null","note_ref":"…|null"}
```
The diff/producer_claim/full findings are **referenced**, never inlined.

**Append:** the O_APPEND core (`tool_events.record:564-570`) — strongest multi-process cross-platform
single-line append. `conversation_id` top-level (Layer-9-style matcher). tz-aware `datetime.now(timezone.utc)`.
**Stealth:** `append_ledger_line` checks `_is_stealth_context()` first, no-ops on stealth. Fires on the **main
terminal thread** (after Gear-4 workers join) — so the stealth `threading.local` is correctly set (avoids the
oversight_events worker-threadlocal-doesn't-propagate gotcha).

---

## 7. Design pillar 5 — stealth, never-raises, parity

- **Stealth = zero durable residue.** Write-time (unconditional): (1) terminal `if not stealth`; (2) `run_loop`
  entry `847`; (3) `persist_packet`'s own `_is_stealth_context()`. Post-hoc backstop: (4) the new closeout
  layer calls `execution_persistence.purge_conversation(id)` → `rmtree(data/execution-records/<id-dir>)`
  (deletes notes; **true zero-residue — the store is git-ignored, §11**) + scrubs `execution-ledger.jsonl` by
  `conversation_id` (Layer-9-style). Because the store is git-ignored (never committed), the backstop leaves no
  history residue (Rev-1 fold #6 + Rev-2 P1 — resolved, not merely disclaimed). The new layer reads `_rp` roots
  at call time (Layers-6a/8/9 idiom).
- **Never-raises:** `persist_packet` and each helper wrap their body → `_mark_failure(…, "execution_packet_
  durable_persist")` → safe return (`git_only`/`False`/`None`). A raised persistence error must never read as
  "no reality contact" (`execution_loop.py:45-47`). `persist_packet` is isolated from the handback.
- **Parity:**
  - **Flag OFF (default):** no loop → only `construct_and_write` → tier `git_only` at build → **no durable
    write** → **response + control-flow parity** with Phase 6; the only on-disk delta is the trace JSON's
    `persistence.tier` value (`"trace_local"` → `"git_only"`, which nothing reads) — not byte-identical output,
    but no behavioral change (Rev-2 minor condition).
  - **Flag ON:** durable writes only for genuinely-noteworthy loop turns; converged-clean → `git_only`.
  - **The one deliberate existing-test change:** Phase-4/6 tests asserting `persistence["tier"]=="trace_local"`
    → `"git_only"` (§10). Full-suite FAIL/ERROR name-list parity: **ZERO new** vs the 27-failure baseline.

---

## 8. Scope boundary — explicitly NOT Phase 7

- **Phase-6 follow-ups** (flip `ORA_EXECUTION_LOOP` default-ON; wire the live actuator) — Phase-6 tuning.
  Phase 7 designs against the flag as-is (default OFF, `actuator=None`).
- **Phase 8** — the `collect_provenance` claim-to-source map; the isolated mutating actuator; MSI's own
  loop/persistence wiring; generalizing adapters. **Persisting a `collect_provenance` lane fill is Phase 8's
  problem** — Phase 7 persists the packet *as it stands* (source-read-only turns are `git_only`, owed-provenance
  marker recorded, map unbuilt).
- **Do NOT "fix" `reversible: true` at high-risk** — the §6 tier-boundary gate, spec-correct (carried gotcha).
- **Do NOT RAG-index execution records** — keeping them off the concept-RAG surface is the point of §14.

---

## 9. Portability section (release-blocking amendment applies)

- **Store path** — `execution_records_dir()` from `runtime_paths.DATA_DIR_STR` (+ env override); ledger via
  `ledger_sink_path()`. No hardcoded mac/user paths (explicitly avoiding `engram_promotion`'s bug, 37-39).
- **Non-git store (Rev-2 P1 / Rev-3 P2)** — Phase 7 adds `data/execution-records/` to `.gitignore`; the impl
  checklist **verifies `git check-ignore` matches BOTH `data/execution-records/execution-ledger.jsonl` AND a
  nested note path** (effective-ignore behavior, not text presence — the §7 true-zero-residue guarantee is
  contingent on it). Git ignore patterns use `/` on every platform, so the rule is cross-platform.
- **`_fs_safe(conversation_id)`** — a shared helper applied on BOTH the note-write and the purge side, so a
  Windows-invalid `:` in an id can't split them; the identical transform guarantees write/purge agreement.
- **Atomic append** — O_APPEND (proven cross-platform in the tool-event sink); **note write** — write-tmp +
  `os.replace` (atomic POSIX + Windows). No `select()`/process-group/symlink/`/dev/null` assumptions.
- **Timestamps** — tz-aware `datetime.now(timezone.utc)` (not naïve `utcnow()`).
- **Imports** — the dual-import shim.
- **Windows-sim tests** (not skip-green): ledger append + `decide_tier` + `redact_for_durable` under
  `ntpath`/`PureWindowsPath`; a note written under a relocated `ORA_HOME`/`ORA_EXECUTION_LEDGER_PATH`; and a
  **stealth round-trip** asserting a note written with id X is deleted by `purge_conversation(X)` under the
  shared `_fs_safe` transform (Rev-1 fold #8). Mirror `test_portability.py`.
- **Remaining assumptions:** none beyond the landed Phase 1-6 substrate reused.

---

## 10. Test + parity plan

New `orchestrator/tests/test_execution_persistence.py`:
- **`decide_tier` truth table** (§3.5) — every combination, incl. self-evidencing→git_only,
  source-read-only-owed→git_only, escalation-withheld→durable_note, degrade-to-text→ledger_line.
- **`redact_for_durable` three-layer** (Rev-1 folds #1/#2/#5) — a `sensitive`-max packet → free-text fields
  become `[SENSITIVE…]` descriptors (NOT passed through in the clear); a `secret`-max packet → dropped; a
  `public`/`private` packet with a planted `sk-…`/`password=…` → `[SCRUBBED]` and kept; the returned object is
  a **copy** (original packet unmutated); `max_sensitivity` read from `sig`, not the packet.
- **note render** — the note body renders the **scrubbed copy** (Rev-1 fold #3/#9): assert the raw producer
  claim never appears; §16-3 label present.
- **ledger append** — one valid JSON line, top-level `conversation_id` from the turn context (Rev-1 fold #4);
  `durable_note` line carries `note_ref`; compact projection (no inlined claim/diff).
- **stealth zero-residue** — a stealth turn writes NO ledger line and NO note; `purge_conversation(id)` removes
  a later-written note subdir + strips the ledger line by id (Rev-1 folds #4/#6/#8).
- **never-raises** — malformed packet → `git_only` + one marker; a durable-write failure → marker, pipeline
  unaffected.
- **flag-OFF parity unit** — `construct_and_write` self-evidencing turn → `tier="git_only"`, no durable side
  effect.
- **gitignore guard** (Rev-2 P1 / Rev-3 P2) — a test asserts git **effectively ignores** the store:
  `git check-ignore` returns a match for BOTH `data/execution-records/execution-ledger.jsonl` AND a nested note
  path `data/execution-records/<conv>/<task>__<ts>.md` — the invariant is behavior ("git treats these paths as
  ignored"), not mere text presence — so the §7 true-zero-residue guarantee can't be silently broken by a
  future ignore-file edit.
- **Windows-sim** (§9).

**Full-suite parity:** pre-edit baseline in the SAME worktree; `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`;
diff sorted FAIL/ERROR name lists; **ZERO new** vs the 27-failure environmental baseline (22 FAIL + 5 ERROR:
lens-integrity, retry-fallback, openai-images, mode-relationship-priorities, user-settings, visual-routing).

**Enumerated deliberate existing-test edits** (semantic, not regressions): assertions of
`persistence["tier"]=="trace_local"` / the old `redacted` string in `test_execution_packet.py` /
`test_execution_loop.py` → the new values (located by grepping `trace_local` in the tests; listed in the impl
packet).

---

## 11. Files touched (projected)

- **NEW** `orchestrator/execution_persistence.py` — the module (§2), incl. `purge_conversation`.
- **NEW** `orchestrator/tests/test_execution_persistence.py` (§10).
- `orchestrator/execution_packet.py` — line 406 default tier `trace_local`→`git_only` + `TIER_*` constants; no
  other behaviour change.
- `orchestrator/execution_loop.py` — call `persist_packet` BEFORE `write_packet` at ~1058-1060 (and on the
  source-read-only branch ~879); add the additive `loop_state["escalation_withheld"] = True` at 1033 (OQ5);
  optionally rewire `handback_reference`'s reference to the durable note (OQ6).
- `orchestrator/conversation_closeout.py` — add ONE new stealth layer that calls
  `execution_persistence.purge_conversation(conversation_id)` (reads `_rp` roots at call time; rmtree the
  conversation subdir + scrub the ledger). No change to the existing Layer 9 tuple.
- `orchestrator/retention_sweeper.py` — **no code change** (exempt-by-omission); an optional one-line docstring
  note that `data/execution-records/` is intentionally not swept.
- **`.gitignore`** (Rev-2 P1) — add `data/execution-records/` so the store is never committed. The §7
  true-zero-residue guarantee depends on this rule; it matches the existing `data/oversight/` /
  `data/pipeline-traces/` / `data/tool-events.jsonl` convention (`.gitignore:66/46/146`).

---

## 12. Open questions for the judge (each with a recommendation)

1. **[HEADLINE] `durable_note` physical store.** *Recommend `data/execution-records/` (non-git operational
   markdown, true stealth zero-residue, subsystem-consistent, §9-satisfied, non-RAG-indexed).* Alternative:
   `vault/Execution Records/` (Obsidian-visible + cross-machine) — but git-tracked, so the closeout backstop
   reaches only the working tree and content committed before a later purge persists in vault git history (the
   **same guarantee level as existing Layer-5 Session exports** — stated honestly, not hidden). *Accept the
   non-git operational store, or does the judge want Obsidian visibility at the Layer-5-equivalent residue cost?
   And is the reuse-over-parallel exception (no engram reuse) accepted?*
2. **Ledger + note location consolidation.** *Recommend both under `data/execution-records/`* (ledger +
   per-conversation note subdirs, one closeout layer, exempt-by-omission). *Accept the consolidated store?*
3. **`git_only`-vs-`ledger_line` boundary (§14 underspecified) — the noise/signal knob.** *Recommend the
   NARROW default: `ledger_line` only for a mutation turn that degraded without converging; converged (any
   iterations) and source-read-only-owed → `git_only`.* **Counter-argument (from the critic, noted for the
   judge):** the ledger is grep-only, not RAG-indexed, so a broader `ledger_line` (e.g. every source-read turn)
   would not pollute *retrieval* in the §14 sense — one could argue for recording more. *Recommendation stands
   (keep the ledger genuinely sparse + honor "do not default to durable"), but the boundary is the judge's
   call; the threshold is a retunable constant validated once the loop runs live.*
4. **Loop-only durable writes vs persist-both.** *Recommend loop-only mechanism; `git_only` universal
   build-time default* (§2) — self-evidencing turns are git_only by construction. *Accept?*
5. **The `escalation_withheld` structural marker.** *Recommend the one-line additive
   `loop_state["escalation_withheld"]=True` at `execution_loop.py:1033`* so `decide_tier` reads a flag, not a
   note-substring. *Accept?*
6. **Rewire the escalation handback's reference to the durable note.** *Recommend: yes, minimal, optional* — an
   escalated turn always earns a durable_note, and pointing the handback at it (vs the 30-day-swept trace JSON)
   makes the reference survive. `persist_packet` stays isolated (never-raises) so this can't suppress an
   escalation. *Do it in Phase 7 or defer?*
7. **New module `execution_persistence.py` vs extend `execution_packet.py`.** *Recommend the new module* —
   distinct concern, own store + closeout integration; matches `retention_sweeper.py`. *Accept?*
8. **Redaction conservatism vs record usefulness.** The durable_note keeps a scrubbed public/private producer
   claim (§16-3 labeled-unverified), diverging from the handback's drop-everything. *Recommend keep-scrubbed
   for public/private, descriptor for sensitive, drop for secret* (a useful yet spec-faithful record). *Accept,
   or does the judge prefer the handback's uniform drop for maximum conservatism at the cost of record value?*

---

## 13. GOTCHA list carried forward
- `reversible: true` at high-risk is the §6 tier-boundary gate — **spec-correct, do not "fix"**.
- `stop_condition` can legitimately be `None` (degrade / escalation-withheld / source-read-only) — neither
  converged nor escalated; handle deliberately (§3).
- The tier decision fires **after** the escalation-downgrade block (1024-1036), i.e. at 1058+.
- `to_dict()` serializes the full producer_claim/instruction — redact a **copy** before any durable write
  (§5); never render the raw packet into the note; `_redact_for_record` does NOT recurse into packet blocks.
- The redactor's `max_sensitivity` is the TRUE max from `sig`, not the Phase-3-capped event stamp.
- `conversation_id` comes from `tool_events.get_turn_context()`, not `context_pkg` (empty in prod) or
  `packet.task_id`.
- Write side and purge side of the store MUST use the identical `_fs_safe(conversation_id)` transform.
- oversight_events stealth uses `threading.local` (does NOT reach Gear-4 workers); `persist_packet` fires on
  the main terminal thread, so it reads the correct stealth state — do not move it into a worker.
- A sink cannot be both gzip-rotated AND stealth-purged-in-place (`retention_sweeper.py:41-50`) → the ledger is
  exempt-by-omission.
- `scrub_content` is pattern-based (public/private layer only); the `sensitive` descriptor layer is
  content-agnostic; the primary secret guarantee is upstream. State, don't overclaim.

---

## 14. Invariants honored (spec §16 — persistence must not weaken)
1. **Acceptance criteria set separately/prior** — persistence only READS the packet; never sets criteria.
2. **Evidence recipe declared independently** — untouched; the ledger/note record declared evidence, add none.
3. **Reality contact observed, not narrated** — the durable record preserves the evidence-first render (§12);
   the producer claim stays labeled unverified and is never elevated to evidence.

*Deliver to the judge's DESIGN gate. STOP — no code until approved.*
