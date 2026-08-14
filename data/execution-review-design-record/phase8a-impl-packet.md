# Execution Review — Phase 8 Chunk A IMPLEMENTATION packet (Rev 0)
## collect_provenance lane + claim-to-source map + web-read library guard

*Execution Thread, 2026-07-05. Design: `phase8-design.md` Rev 4 (judge-approved; Chunks A+B cleared). Worktree `/Users/oracle/ora-worktrees/phase8a-impl`, branch `execution-review-phase8a-impl` off origin/main `38a7eccd` (re-fetched at start; the loop-activation commit — **the loop is LIVE in prod**, raising these stakes deliberately). Durable diff: `phase8a-impl.diff`. NO commit — this packet goes to the CODE-REVIEW gate.*

---

## 1. What was built (design §2, complete)

**14 files: 4 new, 10 edited — +~1,900/−54.** Everything in approved-design scope; nothing beyond it.

### 1.1 New module `orchestrator/execution_provenance.py` (~640 lines)
- **Source registry** (`build_registry`): web consultation chunks (with the formatter's `injected` stamp — un-injected chunks can never support a claim), step-4.5/V8 claim-evidence chunks, conversation+concept RAG via marker-line parse, **relationship RAG via its OWN format parser** (`### title` + `*Via: …*` — pre-check fold: the marker regex was a structural no-op for this lane), deterministic tool results, `file_read` events from the turn log (per-path sensitivity: secret → existence-only entry with NO ref/hash/excerpt; sensitive → descriptor; private/public → **hash-verified re-read** for the excerpt, mismatch ⇒ withheld + `content_changed`, >2MB ⇒ never slurped + `oversize`), opaque MCP entries (§17). Dedup on (kind, ref); `opaque_channels` counted as DISTINCT channels, not events.
- **Excerpt scrub at BUILD time** keyed on per-source sensitivity (three layers; fail-closed to descriptor when `scrub_content` unavailable).
- **Level 1** (always): map rows from flagged+V8 claims with their retrieval evidence — every row `support_status: "unassessed"` (retrieval ≠ support), `claims_total: None` ⇒ **`sufficient=True` is unreachable at Level 1 by construction** (the Rev-3/4 blocker fold, test-asserted).
- **Level 2** (flag `ORA_PROVENANCE_CLAIM_MAP`, default OFF): one model pass (different-family invoker built via the landed §12 selector; same-family recorded on the lane AND rendered). Strict row parser; **support citations restricted to the EXACT ids shown to the mapper** (pre-check fold: fabricated-provenance guard); **unparsed non-empty lines counted and BLOCK sufficiency** (pre-check fold: a lost line could be an unsupported claim).
- **Sufficiency:** Level-2-ran AND claims_total>0 AND all-supported AND zero unparsed AND zero opaque channels.
- **§7 post-hoc confirmation:** `execution.source_reads` candidates stamped `confirmed: true` / `used: false` (additive; matches capped guard-`what` variants — pre-check fold).
- **Placement:** full artifact `<trace_dir>/provenance-map.json` (30d sweep, stealth-never); bounded lane summary (rows≤12, short excerpts, `map_ref`).

### 1.2 The library guard (§2.3, the Rev-4 OQ-5 mechanism)
- `tool_events`: `suppress_library_recording` (counted `threading.local`), `library_recording_suppressed`, `sanitize_url` (signed/credential query params stripped; fail-CLOSED "[URL withheld]" if the scrubber is unavailable), `record_web_reads` (**BYTE-budgeted batching**: ~6KB soft budget vs the 8KB truncation cap, per-`what` 512-char cap + 16-hex tail hash, `batch_part` splits, nothing dropped; `exit_ok` param so FAILED reads are recorded honestly), `ACTION_MANIFEST` gains `web_fetch`/`web_search` (public/read/external — without these, `manifest_axes` fails closed to secret and `_redact_for_record` strips the URLs).
- `tools/web_search.py` + `tools/web_fetch.py`: guards INSIDE the modules (no call-site helpers anywhere) — search events carry the query PLUS one read per RESULT URL (previously never captured anywhere); fetch events carry sanitized URL + chars + **CONTENT-only hash**; **failed fetches/searches record with `exit.ok: false`** (pre-check fold — egress observed, source signal unaffected since risk_gate requires ok).
- `dispatcher.py`: thread-local suppression around the two web handlers (double-record kill, same-thread exact); **its own web_fetch stanza now sanitizes the URL and hashes content-only** (OQ-6) and **`args_redacted` is sanitized for the web tools** (pre-check fold: the dispatcher path suppresses the guard, so it must sanitize itself — the raw signed URL previously rode `reads[].what` into public-safe candidates).
- `claim_verification.py`: **the judge-P1 fix** — `_ctx_submit` (`contextvars.copy_context()` into every worker; the `web_consultation` 2026-05-28 idiom) so worker guard events carry the TURN context instead of misfiling to the global sink with no conversation_id and `stealth: False`.

### 1.3 Seam retention (§2.2)
`assemble_consultation_package` returns `"chunks"` (+ `injected` stamped in the formatter at the char-budget break); boot stashes `context_pkg["web_source_chunks"]`. `_run_claim_verification_preflight` → **pinned 4-tuple** (+`per_claim_evidence`); `_run_unflagged_claim_scan` → 3-tuple; all five call sites updated; evidence stashed into `context_pkg["claim_evidence"]` with **`origin: "unflagged"` stamped at the V8 extension points** (pre-check fold: no producer set it); step-4.5 traces persist `per_claim_evidence` + gear-3 gains `flagged_claims_parsed` (asymmetry closed). The two 3-tuple test mocks updated (`test_quality_gate`, `test_gear4_analyst_recovery`).

### 1.4 Loop + renderer + persistence (§2.4–§2.8)
- `execution_loop.py`: owed branch → **real fill** (owed marker survives ONLY as fallback when the fill returns None — fallback test-asserted); **mixed turns get the fill too** (informational; `converged()` untouched — OQ-4); `redacted_review_summary` → `render_for_review(packet, durable_summary=True)` (coverage line only, no rows/excerpts — the handback-leak blocker fold) + fail-closed "" ⇒ reference-only handback; **OQ6 rewire**: handback carries `note_ref` (stamped by persist BEFORE the handback is built) + `packet_ref` labeled ephemeral.
- `execution_packet.py`: `_render_provenance_lane` — informational header on mixed turns, NEVER the bare `INSUFFICIENT` token; `mapper family:` line rendered when present (pre-check fold); `durable_summary` plumbed through `render_for_review`.
- `execution_persistence.py`: `redact_for_durable` walks **every lane's `result` + `generated_by`** through the three-layer scrub, **wired into `dataclasses.replace`**; structural-token whitelist keeps `support_status`/ids legible on sensitive turns; **URL refs survive at private (scrubbed), filesystem refs keep the path-withhold rule** (pre-check fold: `resolve_path_sensitivity` classifies every URL "sensitive", which blanked all web refs from durable notes); fail-CLOSED inherited (lane-scrub failure ⇒ `None` ⇒ every durable write withheld, test-asserted). `decide_tier`: **OQ-3 exactly** — `not any_mutation AND unsupported>0` ⇒ `ledger_line` (the missing mutation guard was a self-caught deviation, fixed before the pre-check); unassessed/partial NEVER promotes. `persist_packet` stamps `persistence["note_ref"]`.

## 2. Adversarial pre-check (4 lenses × per-finding verify, 26 agents)

**22 findings verified: 17 REAL (deduped to 12 distinct) — ALL folded; 3 REJECTED** (fragment-space URL credentials = judge-approved enumerated scope; extraction-chunk `injected` bypass = approved v1 scope; retrieved_at fallback = cannot occur, chunks carry timestamps at birth). Plus **1 self-caught deviation folded before the pre-check** (the OQ-3 `any_mutation` guard). The 12 folds, each with a regression test:

| # | Sev | Finding | Fold |
|---|---|---|---|
| 1 | major | relationship_rag marker parse was a structural no-op (different format) | dedicated `_parse_relationship_sources` parser |
| 2 | major | dispatcher web events bypassed `sanitize_url` (guard suppressed on that path) — signed URLs rode `reads[].what` + `args_redacted` | dispatcher sanitizes both |
| 3 | major | Level-2 accepted support citations of sources never SHOWN to the mapper → false `sufficient=True` reachable | `offered_ids` returned by the prompt builder; citations outside it rejected |
| 4 | minor | Level-2 silently dropped unparseable (wrapped) rows | `unparsed_lines` counted; >0 blocks sufficiency |
| 5 | major | durable lane scrub withheld EVERY web URL ref (`resolve_path_sensitivity` has no URL branch) | URL refs scrubbed-and-kept; path rule for filesystem refs only |
| 6 | minor | `origin: "unflagged"` never stamped by any producer | stamped at all V8 extension points in boot |
| 7 | minor | guard skipped FAILED fetches/searches ("every invocation" contract) | `exit_ok=False` recording on all error paths |
| 8 | minor | `confirm_source_reads` could never match capped guard-`what`s | capped variants added to the match set |
| 9 | minor | unbounded `f.read()` of huge files for a 700-char excerpt | 2MB size guard, `oversize` flag |
| 10 | minor | `opaque_channels` counted events, not channels | derived from distinct registry entries |
| 11 | minor | §9-required mixed-turn run_loop test missing | added (converged unchanged + informational render + no INSUFFICIENT token) |
| 12 | minor | same-family mapper recorded but never RENDERED (§12 "renders say so") | `mapper family:` line in the provenance block |

## 3. Tests + parity

- **Focused: 204 pass** — `test_execution_provenance.py` (**40 tests**, incl. the two judge-P1 conditions: worker event → TURN trace with conversation_id [+ the bare-submit NEGATIVE control proving copy_context is load-bearing]; stealth worker records NOTHING; plus byte-budget long-URL splitting with per-line byte assertions, sanitize_url incl. fail-closed, guard integrations, registry rules incl. Windows-shaped secret fixture, Level-1-never-sufficient truth table, Level-2 folds, dispatcher sanitize+suppression integration via the real `dispatch()`, lane-scrub/fail-closed/OQ-3/note_ref, all 12 fold regressions) + `test_execution_loop.py` (+4: filled/fallback/mixed/handback-note_ref) + persistence/packet/quality-gate/gear4-recovery updates.
- **Parity (FINAL, post-all-folds):** baseline captured pre-edit in THIS worktree @ `38a7eccd`: **22F+5E=27** (sorted lists at `phase8a-baseline-failures.txt`). Final run: **3,951 tests, sorted FAIL/ERROR lists IDENTICAL (`diff` clean) — ZERO new** (`phase8a-post-failures.txt`). Suite env: `ORA_PIPELINE_TRACE=off ORA_TOOL_EVENTS=off`. Diff: 15 files, +2,152/−57.
- **Live-behavior note (disclosed, design-approved):** the guard + seam retention are flag-independent observation-layer changes — web-grounded turns now emit web read events and can fire `source_read_suspected` where they never could (closing the §16-3 blindness found in the activation smoke test). With the loop LIVE, source-read-only turns now write a FILLED provenance lane trace-locally; durable behavior changes only via OQ-3 (`ledger_line` on explicitly-unsupported claims) and OQ6 (`note_ref` in handbacks). Level 2 stays dormant (`ORA_PROVENANCE_CLAIM_MAP` unset).

## 4. Portability (release-blocking amendment)

- No new roots: provenance artifacts live under the turn `trace_dir`; no literal paths; every new file I/O pins `encoding="utf-8"`; no `fcntl`/POSIX-only APIs; no new locks (per-turn files only).
- Windows-shaped fixtures: `C:\Users\x\.ssh\id_rsa` secret-source registry test (existence-only asserted); sanitize/batching operate on strings (platform-neutral); `_capped_what`/byte budget use encoded lengths.
- `contextvars`/`threading.local` are cross-platform; the guard adds no subprocess/shell surface.
- Remaining assumption (unchanged from Phase 5): sandbox enforcement is macOS/Linux — untouched by this chunk (no runner changes).

## 5. Scope boundary honored

No flag flips (`ORA_EXECUTION_LOOP` untouched; `ORA_PROVENANCE_CLAIM_MAP` born OFF). No gear-reinvocation actuator, no mutating-check actuator (Chunk B), no adapter families (C), no MSI wiring (D), no `reversible:true` change, no re-fetches (local-file re-reads are hash-verified + size-guarded), no loop/stop-rule semantics changes on mutation turns (test-asserted), research turns remain record+render (no revision cycle).

---
*Gate: NO commit until the judge approves. On approval: re-fetch origin/main, rebase, branch → commit → push → PR → squash-merge → delete branch (local+remote) → prune worktree → ff `~/ora` main; report PR# + bare SHA.*
