# G1.22A Closeout Evidence — Pre-Channel System Protection

Date: 2026-07-26

Runtime baseline: `f7eb86a43f2c9c8970ea780908dc85abf83d29f2`

Vault baseline after recording G1.19 acceptance: `ac6a5236f1879bfce6591e7af7661c5dfbf7bea2`

Security correction implementation: `8f1cd4289680cf092716e87521414449e4e33483`

Residual authority correction: `fc731394128bcad5350c77d87248707274228c4c`

Shell-wrapper correction: `7fe125d9fa87e41bcb64be4bdc9db6967c1a9329`

Reconciled vault record: `eb202f3c4a99a6e011ee468e2b21470fb8b8e7e4`

Environment: macOS 26.5.2, Python 3.14.3

Gate state: pre-channel tranche implemented for independent judgment. G1.21 and G1.22B remain held; full G1.22 is not claimed.

Correction state: the five original security findings, the credential-deletion correctness defect, the two residual authority gaps, and the remaining `env` nested-command bypass are corrected and submitted for independent re-judgment. This packet does not claim Gate acceptance.

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

## Residual authority correction disposition

The residual correction closes both independently reproduced paths at the earliest shared boundaries:

1. Approval-authority protection now evaluates the possible resolved target set rather than comparing exact text. Equivalent normalized paths, existing symlinks and hardlinks, wildcard/bracket/brace selectors, unresolved variables, immediate directory access, and recursive roots that contain an authority alias are refused before a handler, filesystem iterator, or shell subprocess can execute. Direct file read/write/list, edit, search, and shell entry points independently repeat the sink-side refusal. Shallow access that mechanically cannot reach the nested authority files remains available.
2. Inline task-approval markers in chat history are untrusted locators only. The runtime selects exactly one active HMAC-authenticated pending task hold for the exact Dialogue and Principal, verifies its queue-record digest, task fingerprint, nonce, and action, and derives the continuation payload from that server-side event. Missing, fabricated, altered, stale, foreign, already-resolved, replayed, and ambiguous state appends neither authority nor queue mutation. One exact authenticated approval produces one one-shot task token and the legitimate task executes once.

These changes add no approval engine and no channel authority. They strengthen the existing Paused queue, authenticated approval store, risk gate, and execution path.

## Shell-wrapper correction disposition

The 2026-07-26 correction closes the sealed scan's remaining `env` nested-command path and audits the known shell-launch surface:

1. A known shell profile must account for every executable the command can launch. Terminal `env` inspection — the `env` utility with options and `NAME=VALUE` operands and no utility operand — remains read-only, but a utility operand or ambiguous execution option makes the command unknown.
2. Generic launcher utilities, execution-capable `awk`, `find` execution predicates, and child-process options on `tar`, `pandoc`, `yt-dlp`, and `zip` fail closed. A single help/version flag cannot give an unknown executable a known profile.
3. The registered dispatcher rejects these forms before approval consumption or handler entry. The direct shell sink repeats the refusal before `subprocess.run` or `subprocess.Popen`, in foreground and background modes.
4. The exact protected approval-store targets remain unreachable. Refusal leaves a pre-issued exact approval token unconsumed, proving that later review cannot be spent on hidden nested execution.

This correction changes no channel, outbound, Persona, hardware, Windows-live, or G1.24 authority.

## Adversarial proofs

The focused suite proves:

1. whole protected roots, raw devices, channels, missing scope, unresolved/broad scope, generic authority source/state edits, and noncanonical credential identities are denied before effect;
2. *(retired 2026-08-19 — the governed Process engine and `classify_governed_action` were removed by `519294b1` on 2026-08-05. There is no Process authority left to grant protected effects, so this claim has no subject. Any equivalent obligation for the Programming vertical belongs to that vertical's own acceptance matrix, not this one.)* ~~direct Process authority cannot grant protected effects while the issued Programming mutation contract remains available;~~
3. unknown tools, unknown shell effects, opaque slash/server actions, and legacy bulk apply paths fail closed;
4. one exact reviewed effect succeeds once with authenticated pre-state, write-ahead record, active execution scope, post-state, and one terminal record;
5. forged/unsigned/MAC-altered queue and approval state, direct token minting, changed arguments, changed selectors or pre-state, cross-Dialogue/Principal/scope use, replay, fabricated execution starts, and fabricated state identities fail without mutation;
6. registered-manifest mutation, registration-time drift, and legacy unbound pointers remain unavailable until reviewed re-registration;
7. semantically external aliases cannot downgrade review, while legitimate local reversible and exact governed Run controls remain operational; **— NOT retired; re-pointed 2026-08-19 and currently unproven. See "Claim #7 is live at a different boundary" below.**
8. record substitution, adjacent-digest rewriting, corrupt approval storage, audit-write failure, and concurrent terminal completion fail closed;
9. direct credential store/delete cannot bypass the active receipt; failed deletion propagates and cannot report success; registered provider status remains available without exposing a secret; exact receipted mutation succeeds; and arbitrary provider identities cannot resolve; and
10. exact, equivalent, pattern, recursive, symlink, and hardlink forms of approval-authority access are refused before file or shell execution, including a recursive root whose tree contains a later authority alias;
11. chat-only, substituted-task, stale-queue, foreign-Dialogue, foreign-Principal, altered-queue, already-resolved, replayed, and ambiguous inline task state grants no authority and changes no queue or approval record, while exact authenticated approval and one execution still work; and
12. utility-bearing `env`, generic launch wrappers, embedded execution languages, and profiled-tool execution options are refused before approval consumption, handler entry, or foreground/background subprocess creation;
13. bounded terminal `env` inspection and bare assignment-only forms remain available — a leading `NAME=VALUE` prefix before a utility does not (see the shell environment-assignment correction below) — while registered-dispatcher refusals preserve their exact unused token; and
14. the tracker, program, Registry, canonical, and this evidence preserve the held G1.17/G1.21/channel/Windows/hardware/G1.24 boundaries.

## Exact command provenance

All commands below were run from the accepted checkout shown in the command. Results and exit statuses are literal.

### Focused protection suite

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py \
  --tb=short
# 32 passed, 10 subtests passed; exit 0
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

### Residual-authority reproducer matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py::TestApprovalAndReceipts::test_approval_authority_refuses_recursive_patterns_and_aliases_pre_execution \
  orchestrator/tests/test_risk_gate.py::TestAuthenticatedInlineTaskApproval::test_chat_only_fabricated_marker_cannot_mint_authority \
  orchestrator/tests/test_risk_gate.py::TestAuthenticatedInlineTaskApproval::test_stale_foreign_and_substituted_markers_leave_state_unchanged \
  orchestrator/tests/test_risk_gate.py::TestAuthenticatedInlineTaskApproval::test_multiple_same_dialogue_holds_are_ambiguous_and_unchanged \
  orchestrator/tests/test_risk_gate.py::TestAuthenticatedInlineTaskApproval::test_queue_task_identity_substitution_cannot_authorize \
  orchestrator/tests/test_risk_gate.py::TestAuthenticatedInlineTaskApproval::test_server_stream_uses_authenticated_queue_not_history_authority \
  orchestrator/tests/test_risk_gate.py::TestAuthenticatedInlineTaskApproval::test_exact_server_state_approves_once_and_executes_once \
  orchestrator/tests/test_risk_gate.py::TestAuthenticatedInlineTaskApproval::test_server_stream_exact_inline_approval_issues_one_task_token \
  --tb=short
# 8 passed; exit 0
```

### Shell-wrapper reproducer matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_shell_profiles.py::TestFailClosed::test_command_launching_wrappers_and_profiled_launch_options_are_unknown \
  orchestrator/tests/test_shell_profiles.py::TestFailClosed::test_env_inspection_and_assignment_only_forms_remain_read_only \
  orchestrator/tests/test_shell_profiles.py::TestFailClosed::test_help_flag_does_not_profile_an_unknown_executable \
  orchestrator/tests/test_shell_profiles.py::TestFailClosed::test_find_delete_and_exec_unknown_or_dangerous \
  orchestrator/tests/test_dispatcher_gate.py::TestGateBeforeExecution::test_command_launching_wrappers_cannot_consume_approval_or_enter_handler \
  orchestrator/tests/test_dispatcher_gate.py::TestGateBeforeExecution::test_env_inspection_only_forms_reach_registered_handler \
  orchestrator/tests/test_g1_22a_system_protection.py::TestApprovalAndReceipts::test_direct_shell_sink_refuses_unknown_wrappers_in_both_modes \
  --tb=short
# 7 passed, 36 subtests passed; exit 0
```

### Sealed-scan proof-of-concept after correction

```bash
cd /Users/oracle/ora-msi-central-routing
python3 /private/var/folders/b7/xxm8n5nx66s8g1pg7nfqvsrr0000gn/T/codex-security-scans-APsi4h/ora-msi-central-routing/7333a312685b7e8045a475392092c82bfca31ad0_20260726T025522Z_44p5fte5/findings/env-nested-shell-authority-bypass/poc/reproduce_profile_bypass.py \
  --source-root /Users/oracle/ora-msi-central-routing
{
  "direct_policy": "deny",
  "direct_policy_code": "approval-authority-scope",
  "opaque_policy": "deny",
  "opaque_policy_code": "unclassified-effect",
  "wrapped_mutability": "irreversible",
  "wrapped_policy": "deny",
  "wrapped_policy_code": "unclassified-effect",
  "wrapped_profile": "env",
  "wrapped_subprocess_reached": false,
  "wrapped_unknown": true
}
# exit 1
```

The sealed reproducer uses exit `0` only when the vulnerable condition is present. Exit `1` here is the expected corrected result: its nested subprocess was not reached and the utility-bearing `env` form was unclassified and denied.

### Owning G1.22A authority matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py \
  orchestrator/tests/test_risk_gate.py \
  orchestrator/tests/test_risk_gate_pipeline.py \
  orchestrator/tests/test_tool_events.py \
  orchestrator/tests/test_dispatcher_gate.py \
  orchestrator/tests/test_shell_profiles.py \
  orchestrator/tests/test_resolution_chain.py \
  orchestrator/tests/test_slash_commands.py \
  --tb=short
# 366 passed, 1 warning, 36 subtests passed; exit 0
```

### Owning plus adjacent runtime matrix

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_g1_22a_system_protection.py \
  orchestrator/tests/test_risk_gate.py \
  orchestrator/tests/test_risk_gate_pipeline.py \
  orchestrator/tests/test_tool_events.py \
  orchestrator/tests/test_dispatcher_gate.py \
  orchestrator/tests/test_shell_profiles.py \
  orchestrator/tests/test_resolution_chain.py \
  orchestrator/tests/test_slash_commands.py \
  orchestrator/tests/test_retrieval_rebuild.py \
  orchestrator/tests/test_user_settings.py \
  orchestrator/tests/test_conversation_lifecycle.py \
  orchestrator/tests/test_project_registry.py \
  orchestrator/tests/test_governed_process_runtime.py \
  --tb=short
# 603 passed, 4 warnings, 105 subtests passed; exit 0
```

### Static cross-platform shell/profile regression

```bash
cd /Users/oracle/ora-msi-central-routing
python3 -m pytest -q \
  orchestrator/tests/test_portability.py \
  orchestrator/tests/test_dispatcher_windows_live.py \
  --tb=short
# 68 passed, 2 skipped; exit 0
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
# 253 passed, 3 warnings, 9 subtests passed; exit 0
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
  orchestrator/tools/file_edit.py \
  orchestrator/tools/file_ops.py \
  orchestrator/tools/search_files.py \
  orchestrator/boot.py \
  server/app.py \
  orchestrator/tests/test_dispatcher_gate.py \
  orchestrator/tests/test_g1_22a_system_protection.py \
  orchestrator/tests/test_risk_gate.py \
  orchestrator/tests/test_risk_gate_pipeline.py \
  orchestrator/tests/test_shell_profiles.py \
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

git diff 7333a312685b7e8045a475392092c82bfca31ad0..7fe125d9fa87e41bcb64be4bdc9db6967c1a9329 --check
# exit 0

cd /Users/oracle/Documents/vault
git diff ac6a5236f1879bfce6591e7af7661c5dfbf7bea2..8a29cb4b51 --check
# exit 0

cd /Users/oracle/Documents/vault
git diff 63ad64b3d5..7e1f04fd4e --check
# exit 0

cd /Users/oracle/Documents/vault
git diff 7e1f04fd4e..44f53fc4d6 --check
# exit 0

cd /Users/oracle/Documents/vault
git diff d101a6c00a..eb202f3c4a --check
# exit 0
```

The vault uses four exact G1.22A ranges because unrelated MSI commit
`63ad64b3d5` was independently added between the initial G1.22A record and
the security-correction record. The third range isolates the residual-authority
record; the fourth isolates this shell-wrapper correction from the then-current
vault head. Those commits and the unrelated vault working
tree are outside this Gate's scope and were not modified, staged, or claimed
by these checks.

## Shell environment-assignment correction (2026-08-19)

The 2026-07-26 packet above closed the `env` nested-command path but left a
separate leading-assignment vector open, and this document previously implied
the opposite by describing "environment assignments" as read-only without
qualifying which spelling. Recorded here because a reader of the packet alone
would have concluded the shell surface was closed.

The defect: `resolve_shell_profile` stripped a leading `NAME=VALUE` prefix
before classifying the verb, so `PATH=<attacker-dir> ls` profiled as a known
read (`unknown=False`, `mutability=read`) while the shell executed the
attacker's binary. Confirmed by execution, not inspection: the command
returned `rc=0` with the attacker's output and no refusal. Three sub-defects:

1. Verb substitution (`PATH=`).
2. Library injection (`LD_PRELOAD`, `LD_LIBRARY_PATH`, `DYLD_INSERT_LIBRARIES`)
   and helper-program injection through an already-allowlisted verb
   (`GIT_SSH_COMMAND`, `GIT_EXTERNAL_DIFF`, `PAGER`, `EDITOR`, `GIT_DIR`).
   This class is why the correction is not a denylist: every interpreter and
   tool ships its own such variable, so the set cannot be enumerated.
3. Profile-name corruption — the profile was named from the unstripped token,
   so `basename("PATH=/tmp/attacker")` recorded `action = "bash:attacker"`,
   an attacker-controlled string, in the audit trail.

The correction: any leading `NAME=VALUE` prefix before a utility fails closed,
in every compound segment. Assignment stripping is retained for operand
resolution, so declared read/write targets still surface on the refusal
record. The profile is named from the stripped verb.

Measured cost of the fail-closed posture: 12,688 recorded tool events contain
56 shell command strings, none carrying a leading assignment; no Ora-internal
caller emits one. Bare assignments (`FOO=bar`) and terminal `env` inspection
are unaffected.

## Matrix re-baselining 2026-08-19 — claim #2 retired, claim #7 is live at a different boundary

The governed Process kernel was removed by `519294b1` on 2026-08-05, four days
after this packet was sealed. That removal took `classify_governed_action`,
`governed_process_runtime.py`, `test_governed_process_runtime.py`, and
`TestPolicyFloor::test_semantic_external_effects_require_review_independent_of_name`
with it. Those four references are dropped from the executable matrices above.

**Claim #2 is retired.** It named an authority — direct Process authority —
that no longer exists. Nothing inherited it. The claim has no subject.

**Claim #7 is NOT retired.** Retiring it was considered and rejected on
evidence. The deleted test exercised the threat through
`classify_governed_action`, but the threat itself — an action escaping outbound
review because of what it is *named* — is alive at the surviving
`classify_action` boundary, and is now untested.

`system_protection.py:751` computes:

```python
outbound_write = mutability == "external_write" or (
    egress == "external" and bool(_OUTBOUND_WORDS.search(normalized_action)))
```

`_OUTBOUND_WORDS` (`:77–80`) is nine words: publish, push, send, upload,
deploy, post. With identical axes (`egress=external`,
`mutability=reversible_write`), the live classifier returns:

| action | outcome |
|---|---|
| `mcp_tracker_post_issue` | deny — missing-exact-scope |
| `mcp_tracker_push_record` | deny — missing-exact-scope |
| `mcp_tracker_create_issue` | **allow** |
| `mcp_tracker_sync_record` | **allow** |

Same effect; the only difference is the verb in the name. `sync_record`,
`create_issue`, and `reconcile_remote_record` — the three operations the
deleted test asserted must reach review — are all `allow` today at
`classify_action`.

**Current exposure is latent, not active.** Both MCP servers configured with
`egress: external` (`playwright`, `github`) also declare
`mutability: external_write`, which sets `outbound_write` regardless of name.
The gap opens when any server declares `egress: external` with
`mutability: reversible_write` — an ordinary declaration for a read-write API
client — at which point tool naming alone decides whether an external effect
is reviewed.

**Disposition:** claim #7 stays in the matrix, re-pointed from
`classify_governed_action` to `classify_action`'s outbound classification, and
is **unproven** until a replacement test exists. It must not be marked passing
on the strength of the deleted test, and it must not be retired on the strength
of the deleted API.

## Held boundaries and limitations

- G1.17 remains user-deferred. Persona/MindSpec, relationship-blurb injection, and new Persona precedence are unchanged and unavailable.
- G1.21 has not started. Telegram, email, agent masks, transport credentials, inbound authenticity, and sends are unavailable.
- G1.22B retains channel allowlists, authenticated communications audit, private-Project RAG exclusion as channel evidence, the live `Exports/`/`Resources/` outbound seam, and live allowed/denied/replayed outbound proofs. Full G1.22 cannot pass without them.
- Verification is on the accepted macOS checkout. Windows raw-device names are statically denied, but live Windows refusal remains in G1.3/G1.23/G1.7. Linux has no separate deployment proof in this tranche.
- Hardware work remains deferred. G1.24 still owns the release-candidate full-state DCP audit and drift closure.
- Direct administrator modification of the executable checkout is outside the supported model/tool/API threat boundary and remains subject to host access control and deployment integrity.
