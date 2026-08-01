# G1.19 Closeout Evidence — Trigger Manager

Date: 2026-07-24

Runtime baseline: `7521dc0833da061b5c0c96899e8fab61219cd305`

Vault baseline after recording G1.20 acceptance: `2fb6a18ca6`

Environment: macOS 26.5.2, Python 3.14.3, Node v22.22.3

Gate state: revised after independent G1.19 findings and resubmitted for judgment. G1.21 remains unauthorized, G1.17 remains user-deferred, and the hardware/Windows tranche remains deferred.

## Scope and architecture disposition

G1.19 extends the accepted G1.18 Process authoring/execution service and G1.20 Run/Inspector telemetry. A Trigger is a separate, immutable activation object over one exact registered Process Definition. It is not a second Process engine and it does not embed scheduling into the Process Definition.

Every admitted firing enters `ProcessAutomationService.begin_triggered_run()` and the ordinary governed Process Run. The Trigger ledger persists the entire prepared invocation contract: exact trigger definition, cause identity, resolved inputs, Project, Principal, definition version/digest, Model/Style selections and resolved context, deterministic idempotency key, firing, invocation digest, and Run ID. The execution boundary accepts only the firing binding, rederives the complete contract from that claim, and returns the same Run on replay. It accepts no caller-authored invocation fields. The resulting Run, checkpoint, evidence, failure/recovery, final review, and Inspector contracts remain the accepted G1.1/G1.18/G1.20 contracts.

The shipped boundary includes:

- immutable Trigger definitions plus a digest-chained state/firing ledger, independent definition anchors, lock-scoped atomic writes, tamper detection, and restart repair only for an exact interrupted creation;
- draft-first construction and exact Principal review before activation; registration alone grants no firing authority;
- draft-only activation plus stale-safe pause, resume, and retirement using exact state digests; exact lifecycle retries resolve their original application before stale-state rejection, while cross-action/key collisions fail closed;
- deterministic source-bound firing identities and exactly-once claims for manual requests, file identities, completed framework Runs, Project milestone snapshots, and local-calendar time windows;
- file-change events dispatched by the existing runtime event path, exact completed-Run framework events, manual firing, and one-shot app-resident time wakes;
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

The implementation performs no polling sweep and installs no cron, LaunchAgent, or operating-system scheduled task. Startup performs one declared missed-window reconciliation. The in-app clock then calculates one authenticated future named-zone occurrence and blocks until that instant or an activation/lifecycle change signals recalculation. After a due firing it calculates the next one-shot wake; with no active time Trigger it waits indefinitely and performs no periodic work. Local calendar boundaries are recalculated across DST, and the declared `run_once` or `skip` missed-window policy remains explicit. It expressly makes no 24/7 delivery promise.

## Held boundaries

- G1.21 retains ownership of email and Telegram channels, credentials, inbound authenticity, and outbound effects. Inbound email/Telegram Trigger drafts may be represented, but activation fails closed until G1.21.
- G1.17 remains deferred. Trigger definitions add no Persona, MindSpec, relationship-blurb, or new Style precedence.
- G1.20 remains the telemetry surface; G1.19 adds no parallel telemetry database or full replacement Inspector.
- Hardware/Windows deferrals and G1.24 responsibilities are unchanged.

## Adversarial proofs

The focused suite proves:

1. A Trigger cannot activate implicitly or without an exact Principal review bound to the immutable spec and activation request.
2. Concurrent creation/claim delivery yields one identity; interrupted exact creation repairs safely; a conflicting retry fails closed.
3. Generic automation entry cannot forge a triggered Run. The dedicated entry accepts only a firing binding and derives inputs, definition, Project, Principal, profiles, deterministic key, invocation digest, and Run ID from the authenticated persisted claim.
4. Reusing a valid claim with attacker-supplied content, Principal, or idempotency key is rejected before mutation; exact replay returns the one original Run without appending Run records.
5. Activation cannot release a paused Trigger. Pause/Resume/retire must use the exact lifecycle route, and an exact retry returns the original lifecycle state even after a later transition.
6. A file event selected before Pause but reaching the claim lock afterward creates no claim and no Run. The immutable spec and current active lifecycle are reauthenticated atomically before every new claim.
7. Manual retry produces the same firing and Run, while a distinct manual request produces a distinct firing.
8. File dispatch binds the actual path, digest, size, modification identity, and bounded excerpt. Replayed bytes do not refire; changed bytes do.
9. Framework completion derives one exact completed, accepted source Run and exact accepted result. Out-of-band labels cannot produce a completion firing.
10. Direct and multi-Trigger causal loops are rejected before activation or firing.
11. Project milestone material is content-bound and excludes private/stealth Dialogue content.
12. Spring-forward and fall-back windows resolve in the named local zone; missed-window `run_once` and `skip` policies remain distinct.
13. The clock performs one startup reconciliation, one recalculated future wake, and no interval scan; actual time activation and lifecycle changes signal recalculation.
14. A time Trigger without the full written Runtime-Principle justification is rejected.
15. Inbound channel activation is rejected pending G1.21.
16. Definition, anchor, ledger, stale lifecycle, failed admission, and restart recovery boundaries fail closed without duplicate effects.
17. Public endpoints expose only exact draft/lifecycle/manual actions; filesystem, framework, time, and inbound sources cannot be caller-forged through a generic dispatch endpoint.
18. Browser reload, exact review, stale rejection, manual Run creation, one-shot time intermittency, and G1.21 disclosure are mechanically covered.
19. Vault canonicals and runtime mirrors remain body-identical, while tracker, program, and Registry record submission rather than premature acceptance.

## Exact command provenance

All commands below were run from the accepted checkout shown in the command. Results and exit statuses are literal.

### Focused Trigger matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_19_process_triggers.py \
  --tb=short
# 23 passed; exit 0
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
# 164 passed, 85 subtests passed in 33.22s; exit 0
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
