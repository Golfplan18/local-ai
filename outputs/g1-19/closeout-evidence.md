# G1.19 Closeout Evidence — Trigger Manager

Date: 2026-07-24

Runtime baseline: `7521dc0833da061b5c0c96899e8fab61219cd305`

Vault baseline after recording G1.20 acceptance: `2fb6a18ca6`

Environment: macOS 26.5.2, Python 3.14.3, Node v22.22.3

Gate state: implemented for independent judgment. G1.21 remains unauthorized, G1.17 remains user-deferred, and the hardware/Windows tranche remains deferred.

## Scope and architecture disposition

G1.19 extends the accepted G1.18 Process authoring/execution service and G1.20 Run/Inspector telemetry. A Trigger is a separate, immutable activation object over one exact registered Process Definition. It is not a second Process engine and it does not embed scheduling into the Process Definition.

Every admitted firing enters `ProcessAutomationService.begin_triggered_run()` and the ordinary governed Process Run. The Trigger ledger binds the exact trigger definition, cause identity, input projection, project, principal, definition version/digest, firing, and Run. The resulting Run, checkpoint, evidence, failure/recovery, final review, and Inspector contracts remain the accepted G1.1/G1.18/G1.20 contracts.

The shipped boundary includes:

- immutable Trigger definitions plus a digest-chained state/firing ledger, independent definition anchors, lock-scoped atomic writes, tamper detection, and restart repair only for an exact interrupted creation;
- draft-first construction and exact Principal review before activation; registration alone grants no firing authority;
- stale-safe pause, resume, and retirement using exact state digests;
- deterministic source-bound firing identities and exactly-once claims for manual requests, file identities, completed framework Runs, Project milestone snapshots, and local-calendar time windows;
- file-change events dispatched by the existing runtime event path, exact completed-Run framework events, manual firing, and app-resident time evaluation;
- Project milestone snapshots bound to the Project Matrix and bounded standard-privacy Project Dialogue material, excluding private and stealth Dialogues, with the resulting Run stopping at its declared human checkpoint;
- direct and transitive framework-trigger causal-cycle rejection;
- restart-safe recovery of claimed, Run-bound, and scheduled incomplete firings without changing their deterministic Run identity;
- Trigger and firing projection into Processes, Attention, and the existing Run Inspector; and
- a browser Trigger Manager that creates drafts, presents the exact review, activates, pauses, resumes, retires, fires manual Triggers, restores state after reload, and keeps failures visible.

## Runtime-Principle disposition for time

Time-based triggers are allowed only when passage of time is itself the declared Process input. Each time Trigger must persist a written statement of:

1. why file, Process-completion, Project, or explicit manual runtime events cannot express the intended cause;
2. why the calendar boundary is semantically necessary; and
3. what bounded work the firing admits.

The implementation performs no polling sweep and installs no cron, LaunchAgent, or operating-system scheduled task. The in-app clock exists only while Ora is running, recalculates named-IANA-zone local calendar windows across DST, and applies the declared `run_once` or `skip` missed-window policy. It expressly makes no 24/7 delivery promise.

## Held boundaries

- G1.21 retains ownership of email and Telegram channels, credentials, inbound authenticity, and outbound effects. Inbound email/Telegram Trigger drafts may be represented, but activation fails closed until G1.21.
- G1.17 remains deferred. Trigger definitions add no Persona, MindSpec, relationship-blurb, or new Style precedence.
- G1.20 remains the telemetry surface; G1.19 adds no parallel telemetry database or full replacement Inspector.
- Hardware/Windows deferrals and G1.24 responsibilities are unchanged.

## Adversarial proofs

The focused suite proves:

1. A Trigger cannot activate implicitly or without an exact Principal review bound to the immutable spec and activation request.
2. Concurrent creation/claim delivery yields one identity; interrupted exact creation repairs safely; a conflicting retry fails closed.
3. Generic automation entry cannot forge a triggered Run. Only the Trigger Manager's authenticated, current firing path can call the dedicated service entry.
4. Manual retry produces the same firing and Run, while a distinct manual request produces a distinct firing.
5. File dispatch binds the actual path, digest, size, modification identity, and bounded excerpt. Replayed bytes do not refire; changed bytes do.
6. Framework completion derives one exact completed, accepted source Run and exact accepted result. Out-of-band labels cannot produce a completion firing.
7. Direct and multi-Trigger causal loops are rejected before activation or firing.
8. Project milestone material is content-bound and excludes private/stealth Dialogue content.
9. Spring-forward and fall-back windows resolve in the named local zone; missed-window `run_once` and `skip` policies remain distinct.
10. A time Trigger without the full written Runtime-Principle justification is rejected.
11. Inbound channel activation is rejected pending G1.21.
12. Definition, anchor, ledger, stale lifecycle, failed admission, and restart recovery boundaries fail closed without duplicate effects.
13. Public endpoints expose only exact draft/lifecycle/manual actions; filesystem, framework, time, and inbound sources cannot be caller-forged through a generic dispatch endpoint.
14. Browser reload, exact review, stale rejection, manual Run creation, time intermittency, and G1.21 disclosure are mechanically covered.
15. Vault canonicals and runtime mirrors remain body-identical, while tracker, program, and Registry record submission rather than premature acceptance.

## Exact command provenance

All commands below were run from the accepted checkout shown in the command. Results and exit statuses are literal.

### Focused Trigger matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_19_process_triggers.py \
  --tb=short
# 19 passed in 3.77s; exit 0
```

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
  orchestrator/tests/test_g1_19_process_triggers.py \
  --tb=short
# 160 passed, 85 subtests passed in 31.58s; exit 0
```

### Browser DOM matrix

```bash
cd /Users/oracle/ora-msi-central-routing
for test_file in \
  test-process-trigger-manager.js \
  test-process-run-inspector.js \
  test-process-attention.js \
  test-process-entry.js \
  test-process-plan-review.js \
  test-process-surface-boundaries.js
do
  node "server/static/tests/$test_file" || exit 1
done
# 18/18 + 28/28 + 15/15 + 26/26 + 19/19 + 8/8 = 114/114; exit 0
```

### Compilation and JavaScript syntax

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m py_compile \
  orchestrator/process_triggers.py \
  orchestrator/process_automation.py \
  orchestrator/runtime_event_dispatcher.py \
  server/server.py \
  orchestrator/tests/test_g1_19_process_triggers.py
node --check server/static/js/process-trigger-manager.js
node --check server/static/js/sidebar-oversight.js
# exit 0
```

### Registered mirror drift

```bash
cd /Users/oracle/ora-msi-central-routing
python3 scripts/verify-implementation.py --check drift
# Passed: 1 — ['drift']; Failed: 0; exit 0
```

### Exact documentation body parity

```bash
cd /Users/oracle/ora-msi-central-routing
python3 - <<'PY'
from pathlib import Path

pairs = [
    (
        Path('/Users/oracle/Documents/vault/Projects/Ora/Guide — Using Ora.md'),
        Path('/Users/oracle/ora-msi-central-routing/docs/user-guide.md'),
    ),
    (
        Path('/Users/oracle/Documents/vault/Projects/Ora/Reference — Ora Technical Documentation.md'),
        Path('/Users/oracle/ora-msi-central-routing/docs/technical-documentation.md'),
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

### Runtime-state residue and diff integrity

```bash
cd /Users/oracle/ora-msi-central-routing
test ! -e data/process-triggers
git diff 7521dc0833da061b5c0c96899e8fab61219cd305..HEAD --check
# exit 0

cd /Users/oracle/Documents/vault
git diff 2fb6a18ca6..HEAD --check
# exit 0
```

The runtime checkout retains only the accepted pre-existing untracked `data/conversation-manifest.jsonl.lock`; Trigger tests leave no installed Trigger state. The vault contains unrelated user work that was preserved and excluded from the G1.19 commit.
