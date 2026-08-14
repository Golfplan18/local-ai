# Chunk 2 Design Addendum — Trace Walk Viewer + Export

*Design-gate packet for Codex. Parent plan: `/Users/oracle/Documents/vault/Working — Trace Walk and Earned Autonomy Build Plan.md` (approved 2026-07-09). Program ledger: `/Users/oracle/ora-worktrees/trace-walk-kickoff-prompt.md`. This addendum covers Chunk 2 only. Code anchors were re-derived against `/Users/oracle/ora` HEAD `86c7ab84d053` on 2026-07-12. As always, anchors must be re-verified again in the implementation worktree because `origin/main` moves under parallel sessions.*

## Scope

Build the first user-facing Trace Walk:

- A hover-row affordance in the output pane labelled "How this was made", attached to the currently visible turn and using that turn's `trace_ref`.
- A modal viewer, not an in-pane replacement. The output pane keeps its "turn N of M" navigation; the modal owns step navigation.
- A read-side `/api/trace/*` route family for list, manifest summary, step package, and static export.
- A standalone, self-contained HTML export of one trace walk.
- A UI pin affordance that sets the existing trace manifest `retention_state` to `pinned`.
- Deep links from failure/degradation surfaces where a reliable trace ref exists; no guessing when it does not.

Out of scope:

- Chunk 3 diagnosis/debugger behavior.
- Resume-from-step.
- New trace capture fields, except tiny trace-link plumbing needed for paused/degradation entry points.
- Any vault documentation update before explicit user approval.

## Verified ground truth the design rests on

- `pipeline_trace.py` already owns the trace root, safe path primitives, manifest lifecycle, and ref resolution. `start_trace` creates a manifest-bearing turn directory with atomic timestamp collision handling (`orchestrator/pipeline_trace.py:207`). `resolve_trace_ref` accepts only a two-component `<conversation_id>/<turn>` ref, rejects traversal/root/conversation-dir refs, requires `trace-manifest.json`, and resolves through the owned trace tree (`orchestrator/pipeline_trace.py:834`). `read_manifest`, `set_retention_state`, and `list_traces` already exist (`orchestrator/pipeline_trace.py:858`, `orchestrator/pipeline_trace.py:905`, `orchestrator/pipeline_trace.py:1206`).
- Existing trace read helpers are manifest-oriented, not viewer-oriented. There is no current helper that returns a safe step projection from `step*.json`, `.md` siblings, JSONL logs, or derived artifacts.
- The server has no `/api/trace/*` routes today. The route table around conversation fetch/pin/export is crowded but conventional Flask routes are used throughout (`server/server.py:10120` for conversation fetch, `server/server.py:11155` for conversation pin, `server/server.py:16482` and `server/server.py:16500` for existing vault export endpoints).
- Conversation turns already carry the join key. The server receives the in-band `trace_ref` SSE event from `_pipeline_stream` and passes it through both `_save_conversation` and `_persist_turn_spatial_state` (`server/server.py:7348`, `server/server.py:7386`, `server/server.py:7469`, `server/server.py:7509`). `conversation_memory.save_turn_spatial_state` stores `trace_ref` on the assistant message (`orchestrator/conversation_memory.py:411`, `orchestrator/conversation_memory.py:605`).
- The browser conversation module groups raw `conversation.json` messages into turns without stripping assistant-message fields (`server/static/js/v3-conversation.js:242`). `getCurrentTurn()` returns the current `{user, assistant}` object (`server/static/js/v3-conversation.js:1738`), so the visible assistant turn's `trace_ref` is directly available to UI modules.
- The output pane already has a hover-style export toolbar loaded from `server/static/js/export-toolbar.js` (`server/index-v3.html:292`). That toolbar reads `window.OraConversation.getCurrentTurn()` and is explicitly the output-pane I/O cluster, but the approved plan says Trace Walk must not live inside the Export menu (`server/static/js/export-toolbar.js:1`, `server/static/js/export-toolbar.js:115`).
- The main output-pane header/navigation is in `server/index-v3.html:797`, and one-turn rendering is in `server/static/js/v3-conversation.js:294`. The existing assistant Markdown renderer escapes HTML before applying simple Markdown transforms (`server/static/js/v3-conversation.js:49`), which is the right pattern to reuse for untrusted trace Markdown.
- Degradation is currently an SSE pipeline stage plus a prepended response note, not a structured durable UI card. The server emits `pipeline_stage` with `stage="degradation"` in `_run_pipeline_from_step2` (`server/server.py:3314`), then prepends `degradation_signal` to the response (`server/server.py:3382`). After the turn is saved, the ordinary assistant message trace ref is the reliable deep-link source.
- Paused queue cards are powered by `/api/oversight/paused` (`server/server.py:16723`) and client modules `server/static/js/sidebar-oversight.js` plus `server/static/js/review-queue-panel.js`. The route currently serializes id/name/queued_at/conversation_id-adjacent metadata/reasoning, but not `trace_ref` (`server/server.py:16735`). `oversight_queue.PausedEntry` preserves `event` and `conversation_id` (`orchestrator/oversight_queue.py:80`), and `tool_events.queue_gate_entry` already has turn context with the originating conversation id (`orchestrator/tool_events.py:1044`).
- Chunk 1 tests live primarily in `orchestrator/tests/test_trace_manifest.py`. They already cover trace ref resolution, symlink rejection, retention state preservation, manifest lineage, physical call capture, server/CLI framework lineage, and retry-child behavior. This is the natural home for backend Trace Walk tests.

## Design

### D1 — Backend trace projection API, built on `pipeline_trace`

Add read-side helpers to `orchestrator/pipeline_trace.py` rather than putting path logic in Flask:

- `trace_manifest_projection(trace_ref)`: resolves through `resolve_trace_ref`, reads the manifest, and returns a safe summary: `trace_ref`, manifest fields, `missing_steps`, `unexpected_steps`, `derived_artifacts`, parent/child refs, and a step map.
- `trace_step_projection(trace_ref, step_name)`: validates `step_name` as one direct filename stem, resolves the trace dir, and returns only:
  - `step_name`
  - JSON payload parsed from `<step>.json` when present
  - Markdown sibling text from `<step>.md` when present
  - presence booleans
  - a plain-language role label from a static map
- `trace_export_html(trace_ref)`: returns a self-contained HTML string assembled from the same projections.

The helper must never return filesystem paths to the browser. It should fail closed for invalid refs and suspicious files, but fail open for missing optional siblings by returning `present: false` rather than raising.

### D2 — `/api/trace/*` route family

Add routes in `server/server.py`:

- `GET /api/trace/list/<conversation_id>`: returns trace refs for one valid conversation, oldest first. This is mainly for fallback/debug UI; the normal output-pane path uses the turn's `trace_ref`.
- `GET /api/trace/manifest/<path:trace_ref>`: returns the manifest projection.
- `GET /api/trace/step/<path:trace_ref>/<step_name>`: returns one step projection.
- `GET /api/trace/export/<path:trace_ref>`: returns `text/html` as an attachment or inline-safe HTML, with a filename derived from sanitized trace id parts.
- `POST /api/trace/retention`: body `{trace_ref, pinned}`; calls existing `pipeline_trace.set_retention_state`.

The first four are read-only. The retention route is the one deliberate exception because the approved plan explicitly puts a pin button in Chunk 2. It mutates only the existing manifest field `retention_state`; it must preserve unrelated manifest fields, including `parent_trace_ref`, `child_trace_refs`, framework fields, and redaction level.

Security rules:

- All routes resolve trace refs only through `pipeline_trace.resolve_trace_ref`.
- No route accepts absolute paths, raw path joins, or conversation-directory refs.
- No route serves raw files by path.
- JSON responses include text as JSON strings only.
- HTML export escapes every trace-derived value with `html.escape`; no trace Markdown is inserted as live HTML.

### D3 — Modal viewer

Add a new browser module, `server/static/js/trace-walk.js`, loaded after `v3-conversation.js` and before/near `export-toolbar.js`.

The module owns:

- `window.OraTraceWalk.open({trace_ref, step})`
- A lazily mounted modal with:
  - left panel: expected/actual step map from the manifest projection
  - right panel: selected step package
  - breadcrumb: `Turn N -> Step K of M - <plain-language role>`
  - visible missing-step rows for every `expected_steps - actual_steps`
  - badges for `terminal_status`, `trace_kind`, `gear`, `mode`, `retention_state`, and `redaction_level`
  - parent/child lineage links when present
  - pin button
  - static export button

Rendering rule: the module may use a tiny Markdown renderer only if it follows the existing safe order: escape `&`, `<`, `>` first, then apply limited Markdown transforms. Raw trace Markdown must never be assigned to `innerHTML` before escaping. JSON payloads render in `<pre>` via `textContent`.

No polling. Trace data is static after turn completion.

### D4 — Output-pane hover affordance

Modify `server/static/js/export-toolbar.js` so the hover row gets a separate "How this was made" icon/button outside the Export dropdown. It should:

- Inspect `window.OraConversation.getCurrentTurn()`.
- Read `turn.assistant.trace_ref`.
- Hide or disable itself with "No trace for this turn" when absent, including stealth/untraced turns.
- Call `window.OraTraceWalk.open({trace_ref})` when present.

This keeps the plan's distinction intact: Export means "take out"; Trace Walk means "look deeper".

### D5 — Degradation and paused-queue deep links

Degradation:

- The durable source is the saved assistant turn's `trace_ref`. If a turn response contains Ora's degradation banner and has `trace_ref`, the normal "How this was made" button is sufficient for this chunk.
- Optional polish: when the viewer opens a degraded turn, select the step map row nearest the degradation source if the manifest/step-health identifies one. Do not infer a failing step from the prose banner alone.

Paused queue:

- Extend queued oversight entries to carry `trace_ref` only when the originating turn context can supply it. The likely source is the current trace dir/ref in tool-event turn context at gate time.
- Extend `/api/oversight/paused` to include `trace_ref` when present.
- In `sidebar-oversight.js` and `review-queue-panel.js`, show "Open trace" only when `entry.trace_ref` is present. The button opens `OraTraceWalk` at the relevant gated/tool step if a step hint is present; otherwise it opens the manifest overview.
- Do not resolve "latest trace for this conversation" as a fallback. That would create a false forensic join and violates the Chunk 0/1 invariant.

### D6 — Static export

The static export is generated on demand by `pipeline_trace.trace_export_html(trace_ref)` and returned by `/api/trace/export/<trace_ref>`.

Export contents:

- Inline CSS only, no external scripts, no network resources.
- Manifest summary.
- Step map with missing steps rendered explicitly.
- One section per expected/actual step, with escaped Markdown and escaped JSON.
- Parent/child lineage refs rendered as inert text.
- Redaction banner:
  - `default`: normal local trace export.
  - `private`: explicit "Private trace" banner.
  - stealth: impossible because no trace should exist; if a manifest somehow says stealth/private-inconsistent, show a warning and do not fabricate content.

Export must be useful as the website demo/presentation artifact, but safe enough to open standalone in a browser without executing trace content.

### D7 — Redaction and trust boundary

Chunk 2 treats all trace content as untrusted:

- Server HTML export escapes every field.
- Browser modal escapes before rendering.
- JSON payloads render as text, not interpreted HTML.
- Markdown code fences remain inert.
- Export filenames are sanitized from trace ref components, never raw user content.
- Private traces are labelled; stealth traces are absent.
- Credentials remain covered by Chunk 1's model-call redaction, but this chunk must not weaken it by exposing raw endpoint URLs or paths.

## Trace-doc §10 checklist

This chunk adds no new Ora-managed runtime persistence surface for trace content:

- The modal is transient browser state.
- `/api/trace/*` read routes project existing trace files.
- Static export is generated on demand and downloaded/opened by the user; the server does not persist it.
- Pinning mutates the existing `trace-manifest.json` `retention_state` field introduced in Chunk 0/1.

Checklist:

1. Off-switch: inherited from `ORA_PIPELINE_TRACE`; no trace means no walk/export. The UI must render "No trace for this turn" rather than creating anything.
2. Stealth-awareness: stealth turns have `trace_ref: null`; routes also fail closed if a caller guesses a ref.
3. Purge layer: no new server-side files to purge. Existing trace purge/sweeper covers manifests and step files. Browser-downloaded exports are user-managed artifacts outside Ora's purge boundary and must be labelled accordingly in the export.
4. Gitignore: no new runtime data path. Existing `data/pipeline-traces/` remains the trace store.
5. Documentation: Trace doc update is owed after landing, but vault edits require explicit user go-ahead.

## Tests

Focused backend tests in `orchestrator/tests/test_trace_manifest.py`:

- Manifest projection rejects traversal/root/conversation-directory refs and symlink escapes.
- Step projection rejects unsafe step names and never returns filesystem paths.
- Missing expected steps are computed and surfaced explicitly.
- Markdown/HTML/script payloads in `.md`, `.json`, manifest fields, and model-call-config logs are escaped in export HTML.
- Export includes parent/child lineage, terminal status, redaction banner, and missing-step rows.
- Retention POST path pins/unpins while preserving unrelated manifest fields.
- List route returns only manifest-bearing turn refs.
- Stealth/untraced behavior: no trace ref yields no route success and no UI affordance.

Focused UI/static tests if existing harness supports it, otherwise minimal DOM smoke under jsdom-gated unittest style:

- `trace-walk.js` renders trace-derived Markdown escaped, not executable.
- Output-pane button is visible/enabled only when current assistant turn has `trace_ref`.
- Pin button calls the retention route and updates displayed state.
- Export button targets `/api/trace/export/<trace_ref>`.
- Paused card shows "Open trace" only when `entry.trace_ref` exists.

Integration tests:

- Server happy-path gear-4 turn fixture with trace ref opens manifest + step endpoints and export.
- Server missing-step fixture renders missing step explicitly.
- Framework parent trace projection includes child refs, and child projection includes parent ref.
- Paused queue entry with trace ref deep-links to the walk; entry without trace ref does not guess.

Validation protocol after implementation:

- Focused tests first.
- Full-suite parity using fresh baseline and implementation runs, both with `ORA_HOME` exported, sorted FAIL/ERROR lists byte-identical.
- Implementation packet + diff, then stop for Codex code-review gate.
- After landing approval: live smoke must include a real gear-4 Trace Walk viewed from disk/export, a missing-step or degraded fixture honestly displayed, and a framework parent/child lineage walk if practical.

## Acceptance criteria

- A non-programmer can open a real completed gear-4 turn and walk step-by-step through how the answer was made.
- Missing expected steps are visibly missing, not silently absent.
- The standalone export opens in a browser with no server dependency and no executable trace content.
- Stealth conversations have no walk because no trace exists.
- All trace content routes are safe against traversal/symlink/root-ref bypasses and do not serve raw files.
- Pinning from the viewer preserves existing lineage and manifest fields.
- Degradation/paused deep links appear only when there is a real trace ref.
- Full-suite parity is zero-new against a fresh baseline.

## Open questions for the design gate

- Q1: Should `/api/trace/retention` be accepted as the one small write endpoint in Chunk 2, given the plan simultaneously says `/api/trace/*` is read-only and "Pin button lives here"? Recommendation: yes, but keep every content route read-only and make retention the explicit exception.
- Q2: For the first export, should step Markdown render as escaped simple Markdown HTML, or as literal `<pre>` text? Recommendation: escaped simple Markdown, because the product promise is a readable walk and the safety property comes from escape-before-render, not from refusing all formatting.
- Q3: Should paused queue deep links require new `trace_ref` plumbing now, or defer if the current queue context cannot provide a non-inferential ref cleanly? Recommendation: add the plumbing only if the originating trace ref is available at gate time; otherwise defer rather than guess from conversation latest.
