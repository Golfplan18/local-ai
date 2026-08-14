# Execution Review — Phase 3 Design Packet (Universal Capture)

*Status: DESIGN GATE. No code written. Mirrors how Phase 2 opened — seam scout
of the landed substrate → design mapped to the spec → adversarial
completeness-critic pass (folded, ⚖ below) → deliver to the judge.
Implementation waits for the judge's design approval, then lands in a fresh
worktree off current `origin/main`.*

Spec: `/Users/oracle/ora-worktrees/ora-execution-review-spec.md` — Phase 3 is
§15 ("Universal capture") resting on §6 (two clocks / two signals), §7 (read
taxonomy, "read classification is post-hoc"), and §4 (collect-provenance /
claim-to-source map). Substrate scouted read-only in the pinned worktree
`/Users/oracle/ora-worktrees/phase3` @ `2ead4450` (current `origin/main`).

---

## 0. The one-paragraph statement of Phase 3

Phase 2 already folds an after-clock `route_observed` from the Phase 1
tool-event log and records two folded facts: **what the turn changed**
(`any_mutation` / `max_mutability` — this is §6 *signal 1*, and it is correct
and done) and **whether any read happened at all** (`reads_present`). But
`reads_present` is *not* §6 *signal 2*. Signal 2 is the **source read** —
"reads whose content grounds the output's claims" (§6), computed by the coarse
over-approximation "did the output make claims about material it read?" (§6,
§15), and **explicitly excluding** `local_context_read` — reading your own
codebase to decide *how* to act (§7). Phase 3's whole job is to turn the raw
"any read" boolean into that discriminating-but-coarse source-read signal,
record it as a distinct after-clock signal, and leave a clean seam for the
precise per-claim `source_read` labeling that §4/§7 defer to the provenance
lane (Phase 8). Nothing here builds the claim-to-source map, the packet, or the
lane router; those are later phases.

---

## 1. Substrate scout — evidence (file:line, all @ `2ead4450`)

### 1.1 The after-clock fold as it stands
- `risk_gate.fold_route_observed(events_path, *, conversation_id, turn_ts)`
  — `orchestrator/risk_gate.py:429-484`. Reads the JSONL sink line-by-line and
  folds `signals = {any_mutation, max_mutability, reads_present,
  max_sensitivity, max_egress, gate_outcomes, events_scanned}`. Scoping: a
  per-turn trace file is folded whole; the **global sink** is filtered by
  `conversation_id` (top-level or `correlation.conversation_id`) and an
  optional `turn_ts` low-water window (`ev["ts"] >= turn_ts`, no upper bound —
  see §1.6). **Takes no output.**
- `reads_present` is set by a single line: `if ev.get("reads"):
  signals["reads_present"] = True` (`risk_gate.py:475-476`). Any event carrying
  a non-empty `reads[]` flips it — a context read and a source read are
  indistinguishable here, and reads with no `reads[]` array (§1.2) are missed.
- `risk_gate.record_route_observed(turn_key, risk_tier)` —
  `orchestrator/risk_gate.py:820-849` (verified: signature is exactly
  `(turn_key, risk_tier=None)`, no output param). Folds, computes one
  `divergence` note (a `light`/`standard` turn observed `external_write`+
  mutability — `risk_gate.py:838-840`), records a `route_observed` event
  carrying `route_signals` + `divergence`. **Takes no output.** The inline
  comment at `risk_gate.py:835-837` already flags the limit: "no output_type
  until Phase 4 … Recorded, not enforced."

### 1.2 What each read channel records (the raw read event)
`orchestrator/dispatcher.py:820-836` builds `reads[]` for exactly four tools:
| channel | `reads[]` entry | content_hash? |
|---|---|---|
| `file_read` | `{what: path, where:"local", content_hash: sha256(result)[:16]}` | ✅ (hash of result) |
| `web_fetch` | `{what: url, where:"network", content_hash: sha256(result)[:16]}` | ✅ |
| `web_search` | `{what:"query:<q>", where:"network"}` | ❌ |
| `knowledge_search` | `{what:"chromadb:<coll>:<q>", where:"local"}` | ❌ |

The read *content* is never placed in the event — only the 16-hex `content_hash`
(two channels) plus a short descriptor; `args_redacted` caps each param at 200
chars and `exit.reason` is populated only on error (`dispatcher.py:850-853`), so
a successful source-channel event stays a few hundred bytes regardless of how
large the read was. The over-approximation must live within that; it cannot diff
read content against output content.

Pipeline RAG is recorded separately: `boot.py:7405-7426` emits one `rag_read`
event with `reads=[{what:"chromadb:conversations" | "chromadb:knowledge" |
"relationship-graph", where:"local", chars: len(text)}]` — **no content, no
hash, but a `chars` count.** The manifest comment (`tool_events.py:148-149`) and
`boot.py:7400-7404` both name RAG as "the pipeline's principal claim-grounding
read channel (spec §6 signal 2)." `rag_read`'s declared sensitivity is
**`private`** (`tool_events.py:150-152`), so its descriptor `what` passes
`scrub_content` on write while `chars` is untouched.

**Not recorded as reads at all:** `search_files` / `list_directory` (dispatcher
builds `reads=None` for them) and any `bash_execute` read (e.g. `cat file`) —
shell `read_paths` feed *sensitivity* resolution (`dispatcher.py:597-601`) but
are never emitted as `reads[]`. So a grep, a directory listing, and a shelled
`cat` are invisible to `reads_present` today.

### 1.3 Redaction interaction — and the load-bearing consequence for the new fields
`tool_events._redact_for_record` — `orchestrator/tool_events.py:463-490`, applied
**at write time to each tool event**: `secret` → the whole `reads` list is
**popped** (existence only); `sensitive` → `reads[].what` = `"[SENSITIVE PATH]"`
(the `content_hash` survives); `private`/`public` → `reads[].what` is scrubbed.

Consequence the design must state (finding [11]): `fold_route_observed` reads
these events back **already redacted**. So any `source_candidate_reads` /
`source_read_channels` Phase 3 folds inherit the upstream redaction — they are
built from descriptors that were already scrubbed/stripped. Critically,
`_redact_for_record` operates only on an event's **top-level** `reads` /
`args_redacted`; it does **not** recurse into `route_signals`. The
`route_observed` event itself is `sensitivity: public`, so `_redact_for_record`
does nothing to it. **All redaction safety of the new nested fields therefore
rests entirely on upstream per-event pre-redaction** — this dependency is
implicit and must be stated, and it has a real gap: a `secret`-sensitivity
source read contributes **no descriptor** (its `reads` was popped upstream), and
a `sensitive` one contributes `[SENSITIVE PATH]` + hash. The §4 claim-to-source
map (Phase 8) must tolerate those holes — they are correct, not a Phase-3 bug.

### 1.4 Terminal-path call sites — the COMPLETE enumeration (13 sites)
`grep`-verified across `orchestrator/` + `server/`. Every non-hold, non-error
terminal path already has the final assistant text in scope where
`record_route_observed` fires:
| site | output var in scope | class |
|---|---|---|
| `boot.py:9412` (main terminal) | `response` | ✅ deliverable, after visual hook |
| `boot.py:9292` (irreversible hold) | — | pause, no claim output → signal 2 False |
| `boot.py:9194` (framework one-shot) | — | ⚠ `return run_framework_command() finally record` — output **not** captured in a var |
| `server/server.py:2957` (pipeline stream) | `response` | ✅ deliverable |
| `server/server.py:2841` (hold) | — | pause → signal 2 False |
| `server/server.py:3277` (framework success) | `result_text` | ✅ in a var (unlike boot.py:9194) |
| `server/server.py:3269` (framework error) | — | run failed → reads-only fallback |
| `server/server.py:3737` (`_direct_stream`, no-tool exit) | `clean` | ✅ |
| `server/server.py:3793` (`_direct_stream`, MAX_ITERATIONS overrun) | `clean` | ✅ |
| `server/server.py:3718` (`_direct_stream` hold) | — | pause → signal 2 False |
| `framework_elicitation.py:324` (deliverable) | `result` (FrameworkExecutionResult, in scope in the `finally`) | ✅ object — needs `format_execution_result(result)` |

Takeaways for the design: the output IS reachable at every deliverable-producing
terminal path **except** `boot.py:9194` (the CLI framework `return-in-finally`);
its server twin `server.py:3277` already holds `result_text` in a var. Hold and
framework-error paths have no claim-bearing output, so signal 2 is `False` there
by construction.

### 1.5 Redaction/consumers/stealth verified by independent grep
- **No runtime consumer of the `signals` dict outside `risk_gate.py` + the two
  test files.** `grep` for `route_signals` / `reads_present` / `any_mutation` /
  `max_mutability` across `orchestrator/` + `server/` returns only the
  `risk_gate` producer and the unrelated `tool_events.max_mutability` helper. So
  **adding keys to `signals` is safe for every runtime consumer**; the only
  parity risk is the two test files' shape assertions (§1.7).
- **Stealth turns suppress the entire record** (findings [10]/[15]): `record()`
  at `tool_events.py:516-525` returns early for any non-gate event when
  `stealth` is set. `route_observed` is not a gate event → **it is not written on
  stealth turns.** Worse for signal 2: the individual tool events on a stealth
  turn are *also* suppressed at write, so the fold would find zero reads even if
  the turn genuinely contacted a source. Phase 3 inherits this: **stealth turns
  get no source-read observation at all** (see Open Question 5 — accepted as
  "stealth = ephemeral / not reviewed," but it must be stated, not silent).

### 1.6 Turn-scoping window (known limitation, inherited from Phase 2)
The global-sink fold filters `ev["ts"] >= turn_ts` with **no upper bound**
(`risk_gate.py:458`). On a conversation with truly concurrent sibling turns, a
later sibling's read events can be folded into this turn. Phase 2 already has
this property for the mutation signal; Phase 3 makes it marginally more
consequential because it now pairs the folded reads against *this* turn's
`output_text` (finding [18]). Conversations are normally sequential, so this is a
narrow edge — recorded as an accepted limitation, not closed here.

### 1.7 Existing tests (the parity surface)
`orchestrator/tests/test_risk_gate.py` class `TestRouteObserved` (536-589):
`test_fold_trace_file` (asserts `reads_present` True, `any_mutation`,
`max_mutability`, `max_egress`, `gate_outcomes`),
`test_global_sink_scoped_by_conversation`, `test_missing_path_safe`,
`test_record_divergence_for_light_mutation`, `test_record_never_raises`.
`orchestrator/tests/test_risk_gate_pipeline.py`:
`test_normal_turn_records_route_observed` (mocks `record_route_observed`
wholesale), plus a hold-path-not-reached test. Phase 3 must be **additive** to
the `signals` dict, not a rename, or `test_fold_trace_file` breaks.

---

## 2. The design

### P1 — Classify read events into source-eligible vs local-context, at fold time (coarse, structural, no model call)
The §7 determinant is "what the output does with the material, not where it
lives." At the coarse level we cannot know that per-read, so we over-approximate
by **channel**, keyed off the event's `action` (already on every event — no new
recording needed):

- **Always source-eligible (external / knowledge grounding), never subject to
  any local tie-break:** `web_fetch`, `web_search`, `knowledge_search`,
  `rag_read`. These fetch reality outside the returned artifact; when the turn
  produces a substantive output they ground claims. Over-routing is safe (§6).
  This is exactly the channel the manifest already annotates as "signal 2."
- **Ambiguous (local file / directory reads):** `file_read`, `search_files`,
  `list_directory`, and shell reads. `local_context_read` (read-to-edit) vs
  `source_read` (read-to-describe) genuinely can't be split without the output.
  **Default: over-approximate every ambiguous local read to source** (max
  over-route, spec-sanctioned). The optional precision refinement (clear a local
  read as context only when its *exact same path* also appears as a
  **successful** mutation this turn) is deferred — see the corrected Open
  Question 1, which retired the original fold-wide-max heuristic as unsound.

Fold on the **event** (`action` + `mutability == "read"`), not solely on the
presence of `reads[]`, so grep/listing/shelled-`cat` count toward the read
signal even though they carry no `reads[]` array today (§1.2 gap). Keep
`reads[]` as the provenance *detail* for the channels that do populate it.

### P2 — Feed the output into the after-clock so the "makes claims" discriminator can run
Add an **optional trailing kwarg** `output_text=None` to `record_route_observed`
(and thread it into a fold helper). Optional-with-default means none of the 13
positional call sites (§1.4) break, and the pipeline tests that mock the
function wholesale are unaffected (finding [13]); only the deliverable-producing
sites pass the output. At those sites the output is already in scope — pass
`response` / `clean` / `format_execution_result(result)`.

The "makes claims" test is deliberately cheap and over-approximating:
- **substantive output** (length over a provisional floor; not a pure
  gate/tool-status/error string) ⇒ claims present;
- a source-eligible read + substantive output ⇒ `source_read_suspected = True`.
- Optional (confidence only, never the gate): light lexical overlap between
  output tokens and read descriptors (`what` = query terms / URL host /
  filename stem) can *raise* confidence — absence must **not** clear the signal
  (over-routing is safe).

**Paths without output_text:** hold/gated and framework-error paths (§1.4) pass
no output — `source_read_suspected` is `False` there by construction (a paused
or failed run produced no grounded deliverable). The one deliverable path
lacking a captured output var, `boot.py:9194`, falls back to the
reads-channel-only over-approximation (source-eligible read present ⇒ suspected)
unless the judge wants it refactored to capture the return value (Open Question
4). Every fallback is a safe over-route, never an under-route.

This keeps §16-3 honest: the observation is mechanical, from the log plus the
produced artifact — never the executor's narration.

### P3 — Emit a distinct signal, additive to the Phase 2 shape
Extend `signals` (do **not** rename existing keys — §1.7; safe because no
runtime code outside `risk_gate` reads the dict — §1.5):
- `source_read_suspected: bool` — the §6 signal 2 (coarse).
- `source_read_channels: list[str]` — which channels fired.
- `source_candidate_reads: list[dict]` — the raw (already upstream-redacted —
  §1.3) read descriptors (`what`/`where`/`content_hash`/`chars`) for the
  source-eligible reads, preserved for Phase 8's claim-to-source map (§4 seam).
- `reads_present` stays exactly as-is (back-compat; the raw "any read" boolean).

The two §6 signals then read cleanly off one dict: `any_mutation` (signal 1) and
`source_read_suspected` (signal 2). "Either signal takes the output out of pure
text review" (§6) becomes a one-line predicate for the Phase 4 router.

### P4 — The §4 claim-to-source-map is a SEAM Phase 3 hands off, not a thing Phase 3 builds
§4 is explicit: the claim-to-source map is built in the collect-provenance lane,
and *that* is "the point at which raw reads are finally classified as
claim-grounding `source_read`s." That lane is Phase 8. Phase 3's contract to it:
1. Record `source_candidate_reads` (with `content_hash` where the channel has
   one) so a later map can point a claim at a snapshot/URL.
2. **Flag — do not close — the provenance gaps** (Phase 3's over-approximation
   does not need them; §4's claim-to-source map does):
   - `web_search` / `knowledge_search` carry no `content_hash`;
   - `rag_read` carries `chars` but no content/hash;
   - no channel captures the §4 requirements — "source snapshots or URLs with
     timestamps, the relevant excerpts, and a claim-to-source map." (Timestamps
     exist as the event `ts`; excerpts/snapshots do not.)
   - **descriptors can be absent by design**: a `secret` source read has its
     `reads` popped upstream (§1.3), and any event over `MAX_LINE_BYTES`
     (`tool_events.py:85`, 8 KB) drops `reads` in the truncation keep-set
     (`tool_events.py:549-558`). The latter effectively never fires for
     `file_read`/`web_fetch` — their content is hashed to 16 chars so the event
     stays small (this is why the completeness-critic's "large read → truncated
     descriptor" claim was rejected) — but the keep-set omission is real for
     genuinely oversized events, so **Phase 8's map must tolerate missing
     descriptors** regardless of cause.
   These are Phase 8 deliverables. Phase 3 records *enough to know a source read
   is suspected and on which channel*; it does not begin excerpt/snapshot
   capture (that would be Phase-8 scope creep and would change the redaction
   surface — §1.3).

### P5 — The §6 consistency check: record the raw material now, assert at Phase 4
§6 wants both halves of the misroute check: a "text" task that grounded claims
in a source is under-reviewed; an "execution" task with no delta *and* no source
read is over-heavy. Phase 3 now supplies the missing half (signal 2). But
`output_type` — the declared hint the check compares against — does not exist as
a first-class field until the Phase 4 packet. So Phase 3 keeps Phase 2's
discipline verbatim: **record** `source_read_suspected` (and keep `divergence`'s
name/shape stable), and leave the `output_type`-vs-observed assertion to Phase
4. No enforcement, no new gate. (Reminder: `irreversible` is gated *before* the
run by Phase 2's hold — post-hoc routing lives only inside reversible tiers, §6;
Phase 3 changes nothing on the before-clock.)

### A note on the word "dispatch" in §15
§15 says the over-approximation happens "at dispatch." Read against §6 (route is
decided *after* the run), "dispatch" here means the **routing decision on the
after-clock**, not per-tool-call time. Phase 3's signal is folded after the run
from the log + the produced output, exactly like Phase 2's `route_observed` —
not computed inside `dispatcher.dispatch()`.

---

## 3. Design consequence the judge should weigh explicitly

`rag_read` is emitted whenever step-2 context assembly populates conversation /
concept / relationship RAG (`boot.py:7411-7419`), and step 2 runs **for every
gear, including gear 1-2** (`run_step2_context_assembly` is called before the
gear branch at `boot.py:9231`). So treating `rag_read` as source-eligible means
**any RAG-grounded turn trips signal 2 — including a gear-2 factual lookup, not
only gear-3/4 analytical modes** (finding [17] corrected the earlier framing).
This is not a bug: §1/§2 say a research or grounded output is
*non-self-evidencing* and should be controlled like a code change, and a
retrieval-grounded factual lookup is exactly that. The over-approximation is
doing its job — the broad default is deliberate, and precision returns only in
the Phase 8 provenance lane. The real discriminator at routing is therefore
"did the turn contact a source channel (RAG / web / knowledge) and produce
substantive output?" (spanning gears), **not** "analytical vs greeting." The
judge should confirm that broad, cross-gear firing is the intended Phase 3
behavior rather than a signal that should demand a stronger per-turn claims test
(Open Question 3).

---

## 4. Scope boundary — what Phase 3 deliberately does NOT do
- No claim-to-source map, no precise per-read `source_read` labeling (Phase 8).
- No excerpt/snapshot/provenance capture — the gaps are flagged, not closed (§3, P4).
- No `ExecutionPacket`, no evidence/judgment lane router, no `output_type` gate,
  no packet-to-review renderer (Phase 4).
- No model call — the over-approximation stays deterministic and structural, so
  it is "honestly cheap now" (§15).
- No before-clock change — the risk tier, the irreversible hold, and the
  criteria pass are Phase 2 and untouched.
- No new redaction machinery — safety of the new fields rests on the existing
  upstream per-event redaction (§1.3); Phase 3 adds no field that could carry
  unredacted secret/sensitive content.

---

## 5. Test + parity plan
- **New unit tests** in `test_risk_gate.py::TestRouteObserved` (and pipeline
  tests): source-eligible channel classification per action; ambiguous local
  read over-approximated to source; substantive-vs-trivial output gate;
  `source_candidate_reads` preservation incl. `content_hash`; secret read ⇒ no
  descriptor folded (upstream-popped) and signal still fires from the event;
  sensitive read ⇒ `[SENSITIVE PATH]` descriptor; `output_text=None` fallback
  (framework path) ⇒ suspected from channel; RAG-only gear-2 turn ⇒ suspected;
  greeting / no-read turn ⇒ not suspected; hold-path ⇒ not suspected; additive
  shape (existing `reads_present` / `any_mutation` / `divergence` / `max_*`
  assertions still pass); new-key redaction is a no-op on the `public`
  `route_observed` event (documents the §1.3 dependency).
- **Parity**: run with `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`; establish
  the branch's fork-point baseline, diff sorted FAIL/ERROR name lists
  branch-vs-base, target **zero new failures**. Known non-ours drift on main:
  `test_capability_registry` (commit `6a666a79` added
  `image_generates_barb_cartoon` to routing-config.json but not
  capabilities.json — chip `task_9482d7fb`, not Phase 3).
- **Adversarial pre-check** before the review packet: small Workflow over only
  the changed fold logic; verify each finding against the code myself (majority
  vote under-reports); fold the real ones; re-run focused + full parity.

---

## 6. Open questions for the judge
1. **Local-file read tie-break (corrected — the original recommendation was
   unsound).** The Phase-3-draft heuristic "over-approximate local reads to
   source *unless the turn is write-dominated by `max_mutability`*" is
   **withdrawn**: `max_mutability` is a fold-wide maximum, so (a) an *unrelated*
   file edit elsewhere in the turn would wrongly clear a genuine local source
   read, and (b) `max_mutability` reflects even a **blocked/denied** write
   attempt (mutability is set on the event regardless of `mutated`), so a gated
   write would clear a source read that actually happened (finding [14]/[7]).
   Options now: **(A, recommended)** over-approximate *all* ambiguous local reads
   to source unconditionally — simplest, safest, zero binding, and correct by
   the over-route asymmetry; **(B)** clear a local read as context only when its
   *exact same path* also appears as a `mutated: true` event this turn — more
   precise but requires per-target read/write path binding, which is fragile
   because write paths live in `args_redacted` and `sensitive` redaction turns
   them into `[SENSITIVE:N chars]` (§1.3). Always-source channels
   (web/knowledge/rag) are **never** subject to either — they are unconditional.
2. **The invisible reads (§1.2 gap).** `search_files` / `list_directory` / shell
   reads record no `reads[]`. Fold on the *event* (`action`+`mutability=read`)
   so they count — no dispatcher change — accepting they won't appear in
   `source_candidate_reads` (a grep is rarely claim-grounding; provenance can
   live without it)? Or add `reads[]` to those tools now (a small dispatcher
   change that widens what Phase 8 can trace)? *Recommend:* fold on the event
   now; flag the provenance omission; add `reads[]` in Phase 8 if the provenance
   lane needs it.
3. **RAG breadth (§3).** Confirm that `rag_read`-as-source-eligible — which makes
   any RAG-grounded turn (including gear-2 lookups) `source_read_suspected` — is
   the intended coarse behavior, vs requiring a stronger per-turn claims test
   before RAG trips signal 2.
4. **Framework `return-in-finally` (boot.py:9194).** Its server twin
   (`server.py:3277`) already captures `result_text`; only the CLI path returns
   in a `finally`. Refactor the CLI path to capture the output var so the "makes
   claims" test runs, or accept the P2 fallback (source-eligible-read-present ⇒
   suspected when output text is unavailable)? *Recommend:* the fallback —
   minimal change, safe over-route; capture the var only if the judge wants the
   output test everywhere.
5. **Stealth turns get no source-read observation.** On a stealth turn both the
   individual tool events and the `route_observed` record are suppressed at write
   (§1.5), so signal 2 is neither observed nor persisted. Accept as "stealth =
   ephemeral / not reviewed" (consistent with the Phase-1/2 stealth model), or
   does Phase 3 owe a stealth-scoped observation? *Recommend:* accept + state
   the limitation; a review apparatus over content the user chose to keep
   ephemeral would defeat the point of stealth.
6. **Provisional constants + concurrent-sibling window.** The "substantive
   output" length floor and any lexical-overlap threshold are provisional tuning
   surfaces (flagged per house rule) — retunable, not calibrated. Separately, the
   low-water `turn_ts` window (§1.6) can, on genuinely concurrent same-conversation
   turns, pair a sibling's reads with this turn's output — a narrow inherited
   edge. Ship provisional with a calibration note (as Phase 2's tier patterns
   did) and leave the window bound as an accepted limitation?

---

## ⚖ Completeness-critic folds (adversarial pass — 4 lenses × adversarial verify; 21 raw, 19 CONFIRMED, 2 REJECTED)

The pass ran four diverse lenses (code-claim verifier / spec-completeness /
seam-integration / adversarial-design), each finding adversarially verified
against the pinned repo, returning **both** confirmed and rejected findings so
the rejected ones could be re-checked by hand (the majority vote under-reports).

**Folded (confirmed, real):**
- **[9] blocker / [4] major / [5],[16]** — §1.4 terminal table was incomplete
  (omitted the server-side framework one-shots `server.py:3269`/`:3277`). §1.4
  rewritten as the complete grep-verified **13-site** enumeration; established
  that output is reachable everywhere except `boot.py:9194`, and that
  `server.py:3277` already holds `result_text`. This also grounds P2's
  "output in scope" claim in a full enumeration rather than a sample.
- **[14] blocker / [7] major** — the draft Open-Question-1 write-dominated
  tie-break was unsound (`max_mutability` is fold-wide → unrelated writes, and
  even *blocked* writes, would clear a genuine source read). OQ1 rewritten:
  recommendation flipped to "over-approximate all ambiguous local reads
  unconditionally (A)," with per-target binding demoted to an optional precise
  path (B); always-source channels explicitly exempt from any tie-break (P1).
- **[10] major / [15] major** — stealth turns suppress the whole
  `route_observed` record *and* the underlying tool events. Added §1.5 + Open
  Question 5; stated the limitation instead of leaving it silent.
- **[11] major** — the new nested fields live inside `route_signals`, which
  `_redact_for_record` never traverses; their redaction safety rests entirely on
  upstream per-event pre-redaction. Added §1.3 "load-bearing consequence" +
  scope-boundary line + a test.
- **[17] major** — §3's "analytical vs greeting" framing was wrong at the
  boundary: gear-1/2 RAG-grounded lookups also emit `rag_read` and trip signal 2.
  §3 rewritten to the correct cross-gear discriminator ("contacted a source
  channel + substantive output").
- **[6],[12],[13],[18] minor / [0],[1],[3],[8] nit** — hold-path predicate stated
  (signal 2 False on pauses); `rag_read` sensitivity corrected to `private`;
  P2 stated as an optional trailing kwarg so no call site breaks + pipeline mocks
  unaffected; concurrent-sibling window recorded (§1.6 + OQ6); citation fixes
  (`comment at 835-837` not "docstring 838-840"; `tool_events.py:148-149` not
  150-152); framework_elicitation `result`-in-`finally` note confirmed; §4 gap
  note that descriptors can be absent by design.
- **Independent finds (mine, folded alongside):** no runtime consumer of the
  `signals` dict outside `risk_gate` + tests (§1.5) — strengthens the
  additive-shape safety claim; server framework success/error split
  (`3277`/`3269`).

**Re-checked and correctly REJECTED (not folded):**
- *rag_read block cited 7405-7426 "stops one line short"* — false; `7426` **is**
  the `record()` closing line, `7427-7428` is only the `except: pass`. Citation
  is precise.
- *source_candidate_reads defeated by MAX_LINE_BYTES truncation for large reads*
  — the causal mechanism does not exist: read content is hashed to 16 chars, so
  `file_read`/`web_fetch` events stay a few hundred bytes and never trip the 8 KB
  truncation. The *general* kernel (descriptors can be absent — by
  secret-redaction, or by truncation on a genuinely oversized event) is real and
  was folded into P4, but the rejected size-driven claim was not.
