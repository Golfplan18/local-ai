# G1.22A Closeout Evidence — Pre-Channel System Protection

Date: 2026-07-25

Runtime baseline: `f7eb86a43f2c9c8970ea780908dc85abf83d29f2`

Vault baseline after recording G1.19 acceptance: `ac6a5236f1879bfce6591e7af7661c5dfbf7bea2`

Security correction implementation: `8f1cd4289680cf092716e87521414449e4e33483`

Reconciled vault record: `7e1f04fd4e049c9ddd0b930840cf192b3f5bcfc2`

Environment: macOS 26.5.2, Python 3.14.3

Gate state: pre-channel tranche implemented for independent judgment. G1.21 and G1.22B remain held; full G1.22 is not claimed.

Correction state: five confirmed security findings and the credential-deletion correctness defect are corrected and submitted for independent re-judgment. This packet does not claim Gate acceptance.

## Scope and architecture disposition

G1.22A reconciles current protection behavior and implements the mechanical self-protection/non-channel tranche authorized after G1.19 acceptance. `Framework — System Protection and Outbound Security.md` is the single canonical. `orchestrator/system_protection.py` is its executable projection, not a second authority.

The tranche composes the existing risk axes, Paused queue, one-shot approval token, governed Process authority, provider registry/OS keyring, checkpoints, and `actions.jsonl`. It adds no parallel approval system and no scheduled recovery or cleanup. The shared floor now applies before protected effects at:

- the ordinary tool dispatcher and shell classifier;
- arbitrary governed Process action authorization;
- shipped destructive server APIs;
- shipped slash-command adapters;
- direct credential mutation and provider-secret resolution; and
- generic non-channel external writes exposed through the dispatcher.

Absolute denials cover whole protected roots, raw drives, generic authority source/configuration/state mutation, credential retrieval, noncanonical credential identities, missing/unresolved/broad exact scope, opaque or unclassified destructive effects, unavailable or unauthenticated audit/approval state, and every channel/agent-mask action.

Exact reviewable actions reuse Paused review and an unpredictable queue nonce, consume one exact one-shot approval, authenticate pre-state, persist an HMAC-chained write-ahead receipt, expose authority only inside that receipt's exact action/selector scope, reauthenticate post-state, and persist one completion or failure receipt. Compound deletion adapters bind every state file they can mutate: Style store plus settings default, Theme directory plus index, and Model Profile plus active pointer. Credential pre/post identities re-read canonical keyring presence without exposing secret bytes. Concurrent terminal attempts have one winner. A record plus an adjacent digest cannot be rewritten into valid history because the audit uses a separately protected HMAC key.

The accepted Programming repository operations remain governed by their exact G1.1 plan/node/checkpoint/target/receipt contract. This tranche does not widen or replace that path.

## Current-state reconciliation

| Existing surface | Before G1.22A | Reconciled disposition |
|---|---|---|
| Tool risk gate and Paused queue | Useful risk axes and one-shot review, but public token minting, predictable/weak request binding, and permissive approval-store recovery | Direct mint denied; persisted random queue nonce and SHA-256 request binding; strict no-follow atomic store; approval infrastructure failure blocks without overwriting state |
| Dispatcher/shell | Reviewable tools, but unknown/destructive effects and targets were not a complete system policy | Shared fail-closed classification, exact filesystem selectors, destructive target extraction, raw-device and authority-state denial, protected receipt scope around handler execution |
| Governed Process runtime | Strong definition-specific authority but no global system-reserved floor | Global pre-mutation denial for generic credential, channel, destructive, self-modification, and named outbound grants; accepted Programming operations preserved |
| Server/slash effects | Several browser or caller-confirmed direct mutations | Exact action adapters, server-derived selector/state, existing one-shot approval, write-ahead/terminal receipts; opaque and legacy bulk paths denied |
| Credentials | Provider keyring registry usually used, with residual inline/arbitrary aliases | Registry-declared environment/keyring coordinates only; direct mutation receipted; retrieval unavailable; legacy noncanonical Replicate alias removed |
| Audit | Existing `actions.jsonl` sink without this binding | HMAC-authenticated action/approval/pre-state/start/post-state/terminal chain in the existing sink |

## Security correction disposition

The 2026-07-25 correction closes the scan's five reproduced paths at their shared authority boundaries:

1. `execution-approvals.json` and its authentication key are inaccessible through generic file operations. The versioned store is authenticated as one HMAC-SHA-256 object, so pending requests, tokens, standing allows, and their mutable use/binding state cannot be substituted independently.
2. The exact normalized selectors and authenticated pre-state are captured before review and included in the pending request and token identity. Execution-time mismatch invalidates the token before any start receipt or effect.
3. Execution/task-gate resolution authenticates the exact linked Dialogue and Principal before calling a resolver, consuming authority, removing the queue entry, or marking the discussion resolved. Direct slash resolution applies the same rule.
4. Project registration hashes and parses one immutable manifest snapshot, carries its identity through protected review, persists it in the pointer, and revalidates it on registration, list, resolution, tool/slash discovery, and invocation. Changed and legacy-unbound manifests fail closed until explicit re-registration.
5. Governed external-effect classification uses authoritative `effect_type`/`scope_kind` metadata rather than operation spelling. The accepted governed Run contract remains the review adapter—exact approved grant, selector scope, checkpoint, and receipt—so no parallel Process or approval engine is created.

Credential deletion now propagates backend and verification failures. A successful terminal receipt is available only after exact keyring state proves `present=false`; a failed deletion records failure rather than manufacturing absence.

## Adversarial proofs

The focused suite proves:

1. whole protected roots, raw devices, channels, missing scope, unresolved/broad scope, generic authority source/state edits, and noncanonical credential identities are denied before effect;
2. direct Process authority cannot grant protected effects while the issued Programming mutation contract remains available;
3. unknown tools, unknown shell effects, opaque slash/server actions, and legacy bulk apply paths fail closed;
4. one exact reviewed effect succeeds once with authenticated pre-state, write-ahead record, active execution scope, post-state, and one terminal record;
5. forged/unsigned/MAC-altered queue and approval state, direct token minting, changed arguments, changed selectors or pre-state, cross-Dialogue/Principal/scope use, replay, fabricated execution starts, and fabricated state identities fail without mutation;
6. registered-manifest mutation, registration-time drift, and legacy unbound pointers remain unavailable until reviewed re-registration;
7. semantically external aliases cannot downgrade review, while legitimate local reversible and exact governed Run controls remain operational;
8. record substitution, adjacent-digest rewriting, corrupt approval storage, audit-write failure, and concurrent terminal completion fail closed;
9. direct credential store/delete cannot bypass the active receipt; failed deletion propagates and cannot report success; registered provider status remains available without exposing a secret; exact receipted mutation succeeds; and arbitrary provider identities cannot resolve; and
10. the tracker, program, Registry, canonical, and this evidence preserve the held G1.17/G1.21/channel/Windows/hardware/G1.24 boundaries.

## Exact command provenance

All commands below were run from the accepted checkout shown in the command. Results and exit statuses are literal.

### Focused protection suite

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py \
  --tb=short
# 30 passed; exit 0
```

### Security correction reproducer matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py::TestPolicyFloor::test_semantic_external_effects_require_review_independent_of_name \
  orchestrator/tests/test_g1_22a_system_protection.py::TestApprovalAndReceipts::test_approval_store_and_authentication_key_are_not_generic_files \
  orchestrator/tests/test_g1_22a_system_protection.py::TestApprovalAndReceipts::test_signed_approval_store_tampering_fails_closed \
  orchestrator/tests/test_g1_22a_system_protection.py::TestApprovalAndReceipts::test_reviewed_selector_and_pre_state_cannot_be_rebound \
  orchestrator/tests/test_resolution_chain.py::TestContinueResolution::test_execution_gate_rejects_foreign_dialogue_without_mutation \
  orchestrator/tests/test_resolution_chain.py::TestContinueResolution::test_execution_gate_rejects_foreign_principal_without_mutation \
  orchestrator/tests/test_slash_commands.py::TestApproveDenyCommand::test_gate_approval_rejects_foreign_dialogue_and_principal \
  orchestrator/tests/test_project_registry.py::TestPointerFileLifecycle::test_manifest_mutation_invalidates_get_list_and_invocation \
  orchestrator/tests/test_project_registry.py::TestPointerFileLifecycle::test_registration_rejects_review_to_write_manifest_drift \
  orchestrator/tests/test_user_settings.py::SettingsEndpointTests::test_api_key_delete_backend_failure_is_not_reported_as_success \
  --tb=short
# 10 passed; exit 0
```

### Protection and direct-boundary matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py \
  orchestrator/tests/test_tool_events.py \
  orchestrator/tests/test_dispatcher_gate.py \
  orchestrator/tests/test_user_settings.py \
  orchestrator/tests/test_retrieval_rebuild.py \
  orchestrator/tests/test_risk_gate.py \
  orchestrator/tests/test_resolution_chain.py \
  orchestrator/tests/test_slash_commands.py \
  orchestrator/tests/test_project_registry.py \
  --tb=short
# 446 passed, 5 subtests passed; exit 0
```

### Adjacent runtime matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py \
  orchestrator/tests/test_tool_events.py \
  orchestrator/tests/test_dispatcher_gate.py \
  orchestrator/tests/test_retrieval_rebuild.py \
  orchestrator/tests/test_user_settings.py \
  orchestrator/tests/test_conversation_lifecycle.py \
  orchestrator/tests/test_project_registry.py \
  orchestrator/tests/test_governed_process_runtime.py \
  --tb=short
# 359 passed, 69 subtests passed; exit 0
```

### Provider and credential regression matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_provider_registry.py \
  orchestrator/tests/test_vendor_catalog_registry.py \
  orchestrator/tests/test_sync_endpoints_vendor_auth.py \
  orchestrator/tests/test_user_settings.py \
  --tb=short
# 104 passed; exit 0
```

### Compound server-state regression matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_v3_theme_api.py \
  orchestrator/tests/test_style_store.py \
  orchestrator/tests/test_active_configuration.py \
  orchestrator/tests/test_g1_16_model_profile_api.py \
  orchestrator/tests/test_conversation_lifecycle.py \
  orchestrator/tests/test_project_registry.py \
  --tb=short
# 253 passed, 9 subtests passed; exit 0
```

### Compilation

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m py_compile \
  orchestrator/system_protection.py \
  orchestrator/active_configuration.py \
  orchestrator/project_registry.py \
  orchestrator/tool_events.py \
  orchestrator/dispatcher.py \
  orchestrator/risk_gate.py \
  orchestrator/governed_process_runtime.py \
  orchestrator/resolution_chain.py \
  orchestrator/slash_commands.py \
  orchestrator/user_settings.py \
  orchestrator/tools/bash_execute.py \
  orchestrator/tools/credential_store.py \
  orchestrator/tools/file_ops.py \
  orchestrator/boot.py \
  server/server.py \
  orchestrator/tests/test_g1_22a_system_protection.py \
  orchestrator/tests/test_project_registry.py \
  orchestrator/tests/test_resolution_chain.py \
  orchestrator/tests/test_slash_commands.py \
  orchestrator/tests/test_user_settings.py
# exit 0
```

### Registered mirror drift

```bash
cd /Users/oracle/ora-msi-central-routing
python3 scripts/verify-implementation.py --check drift
# Passed: 1 — ['drift']; Failed: 0; Skipped: 0; exit 0
```

G1.22A adds one vault-only canonical plus a Python executable projection; it creates no markdown framework mirror. The registered drift check therefore remains the applicable no-new-drift proof. G1.24 retains the full-state DCP campaign.

### Diff integrity

```bash
cd /Users/oracle/ora-msi-central-routing
git diff f7eb86a43f2c9c8970ea780908dc85abf83d29f2..HEAD --check
# exit 0

cd /Users/oracle/Documents/vault
git diff ac6a5236f1879bfce6591e7af7661c5dfbf7bea2..8a29cb4b51 --check
# exit 0

cd /Users/oracle/Documents/vault
git diff 63ad64b3d5..7e1f04fd4e --check
# exit 0
```

The vault uses two exact G1.22A ranges because unrelated MSI commit
`63ad64b3d5` was independently added between the initial G1.22A record and
the security-correction record. That commit and the unrelated vault working
tree are outside this Gate's scope and were not modified, staged, or claimed
by these checks.

## Held boundaries and limitations

- G1.17 remains user-deferred. Persona/MindSpec, relationship-blurb injection, and new Persona precedence are unchanged and unavailable.
- G1.21 has not started. Telegram, email, agent masks, transport credentials, inbound authenticity, and sends are unavailable.
- G1.22B retains channel allowlists, authenticated communications audit, private-Project RAG exclusion as channel evidence, the live `Exports/`/`Resources/` outbound seam, and live allowed/denied/replayed outbound proofs. Full G1.22 cannot pass without them.
- Verification is on the accepted macOS checkout. Windows raw-device names are statically denied, but live Windows refusal remains in G1.3/G1.23/G1.7. Linux has no separate deployment proof in this tranche.
- Hardware work remains deferred. G1.24 still owns the release-candidate full-state DCP audit and drift closure.
- Direct administrator modification of the executable checkout is outside the supported model/tool/API threat boundary and remains subject to host access control and deployment integrity.
