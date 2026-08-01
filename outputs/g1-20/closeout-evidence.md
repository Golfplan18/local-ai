# G1.20 Closeout Evidence — Process Run Telemetry, Liveness, and Controls

Date: 2026-07-24

Runtime baseline: `cb57d71a8893554370785f7b1b0eefcae4848dc8`

Vault baseline after recording G1.18 acceptance: `87d29cc8562cf443d10215f662daa499bd14777d`

Environment: macOS 26.5.2, Python 3.14.3, Node v22.22.3

Gate state: implemented for independent judgment; G1.19 remains unauthorized.

## Scope and architecture disposition

G1.20 extends the accepted G1.1 nine-view Run Inspector and G1.18 automation service. It adds no Process engine, telemetry store, Trigger/schedule, Persona/MindSpec binding, channel, outbound authority, or generic Run force-control.

The shipped boundary is:

- deterministic Inspector telemetry derived from the exact Run, issued definition, records, Artifacts, and live worker owner;
- token/cost values withheld unless a runtime-authenticated usage receipt exists; no-tools isolation never manufactures zero usage;
- reserved exact worker start/finish records and fail-closed orphan recovery;
- stale-safe, idempotent pause/resume/stop for G1.18 automated Runs only, with pre-mutation request/application authentication, one atomic checkpoint-plus-pause record batch, persistent `user_control`, `human_handoff`, and `failure_recovery` pause kinds, and the existing managed `stop_process` boundary;
- a Principal-authenticated mechanical blocked route for Stop;
- opt-in, Model Profile-bound drift/quality/trace evaluation only at an authenticated human handoff or output failure, with source, content subject, and evaluator identity independently derived at the runtime boundary, using digest-verified bounded content, exact inputs/contracts, and exact failure trace or a deterministic `INDETERMINATE`; and
- an authority-inert model verdict that cannot advance, retry, authorize, complete, review, or accept a Run.

The existing Inspector modal and sidebar Process zone are the only new presentation surfaces. The accepted G1.18 definition, Process Library, interview, authority, evidence, checkpoint, recovery, and final-review contracts remain the governing architecture.

## Adversarial proofs

The focused suite proves:

1. Layer 1 is always present and binds state/node, time/estimate, attempt/retry ceiling, authenticated usage or explicit absence, Artifact counts/currentness, error state, health, and liveness.
2. Quality evaluation is unavailable at ordinary steps, idempotent at an eligible seam, and receives digest-verified Artifact bytes, exact inputs, criteria, instructions, source, and failure trace—not opaque IDs alone.
3. Missing, drifted, unreadable, or over-limit evaluation material returns `INDETERMINATE` without a model call and without changing Run authority.
4. Wrong, partial, outcome-without-start, public generic, duplicate, stale-source, and digest-substituted telemetry records fail closed. A complete fabricated old-source start plus matching `PASS` outcome cannot append either record because the direct authoritative API is unavailable.
5. User Pause terminates the exact worker when present, persists its distinct authority state, and rejects direct execute, public retry, direct runtime resume, and restarted-service retry until exact Resume. Forged and stale Pause calls leave the Run and record chain byte-for-byte unchanged; two racing authenticated calls add exactly one adjacent `checkpoint_created`/`run_paused` pair.
6. Concurrent worker/control completion cannot advance through a recorded user Pause, while the authenticated Resume continues the same Run from its checkpoint.
7. Stop terminates the exact worker, reaches one approved blocked terminal, and retry returns the same terminal identity.
8. Persisted control requests/applications interrupted before their state effect reconcile once after restart.
9. A stale control digest is rejected before effect.
10. A lost worker is visible as orphaned, completes its exact attempt as defective, and pauses without replay.
11. No-tools/model-backed execution reports explicit unknown token/cost values because no authenticated usage receipt exists.
12. Browser controls post only the exact state digest and deterministic bounded idempotency identity; the sidebar keeps healthy work quiet while showing health, attempts/retries, and live-worker state.
13. Vault canonicals and runtime mirrors remain body-identical, record the G1.17 deferral, and keep G1.19 unauthorized pending independent G1.20 acceptance.

## Exact command provenance

All commands below were run from the accepted checkout shown in the command. Results and exit statuses are literal.

### Focused and adjacent Python matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_20_process_run_telemetry.py \
  orchestrator/tests/test_g1_18_process_automation.py \
  orchestrator/tests/test_governed_process_runtime.py \
  orchestrator/tests/test_phase_2_4_delegation_attention.py \
  orchestrator/tests/test_phase_2_5_run_inspector.py \
  orchestrator/tests/test_phase_2_6_process_library_lifecycle.py \
  --tb=short
# 141 passed, 85 subtests passed; exit 0
```

### Browser DOM matrix

```bash
cd /Users/oracle/ora-msi-central-routing
for test_file in \
  server/static/tests/test-process-run-inspector.js \
  server/static/tests/test-process-attention.js \
  server/static/tests/test-process-entry.js \
  server/static/tests/test-process-plan-review.js \
  server/static/tests/test-process-surface-boundaries.js
do
  node "$test_file" || exit 1
done
# 28/28 + 15/15 + 26/26 + 19/19 + 8/8 = 96/96; exit 0
```

### Compilation and JavaScript syntax

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m py_compile \
  orchestrator/governed_process_runtime.py \
  orchestrator/process_automation.py \
  orchestrator/process_run_inspector.py \
  orchestrator/tools/bash_execute.py \
  server/app.py \
  orchestrator/tests/test_g1_18_process_automation.py \
  orchestrator/tests/test_g1_20_process_run_telemetry.py
node --check server/static/js/process-run-inspector.js
node --check server/static/js/sidebar-oversight.js
# exit 0
```

### Registered mirror drift

```bash
cd /Users/oracle/ora-msi-central-routing
python3 scripts/verify-implementation.py --check drift
# Passed: 1 — ['drift']; Failed: 0; exit 0
```

The all-category verifier is not claimed by G1.20: its manifest-backed framework-pair category intentionally continues to report G1.14's seven missing twins and fourteen unreconciled drift findings, and unrelated historical full-suite failures remain outside this gate. The bounded registered-pair drift check above is the applicable no-new-drift proof.

### Exact documentation body parity

```bash
cd /Users/oracle/ora-msi-central-routing
python3 - <<'PY'
from pathlib import Path

pairs = [
    (
        Path('/Users/oracle/Documents/vault/Projects/Ora/Reference — Ora Technical Documentation.md'),
        Path('/Users/oracle/ora-msi-central-routing/docs/technical-documentation.md'),
    ),
    (
        Path('/Users/oracle/Documents/vault/Projects/Ora/Guide — Using Ora.md'),
        Path('/Users/oracle/ora-msi-central-routing/docs/user-guide.md'),
    ),
]

def body(path):
    text = path.read_text(encoding='utf-8')
    if text.startswith('---\n'):
        text = text.split('\n---\n', 1)[1]
    return text.lstrip('\n').rstrip()

for canonical, mirror in pairs:
    assert body(canonical) == body(mirror), canonical
print('2/2 body-identical')
PY
# 2/2 body-identical; exit 0
```

### Diff integrity

```bash
cd /Users/oracle/ora-msi-central-routing
git diff cb57d71a8893554370785f7b1b0eefcae4848dc8..HEAD --check
# exit 0

cd /Users/oracle/Documents/vault
git diff 87d29cc8562cf443d10215f662daa499bd14777d..HEAD --check
# exit 0
```

## Preserved boundaries and limitations

- G1.17 remains user-deferred; Persona is unavailable and existing interaction/output Style plus honne/tatemae behavior is unchanged.
- G1.19 remains unauthorized. No Trigger or scheduler record is created by telemetry or controls.
- Force controls apply only to definitions carrying the authenticated G1.18 automation contract. Other governed Runs use their declared checkpoint, authority, correction, and terminal routes.
- The deterministic estimate is historical arithmetic, not a deadline or provider promise.
- Generic Runs without authenticated usage data report its absence; they do not report invented zero cost.
- Optional quality evaluation can fail or remain unavailable without changing Run authority. Its verdict is never acceptance evidence.
- Hardware/Windows deferrals and G1.24's reserved responsibilities are unchanged.
