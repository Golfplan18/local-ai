# Framework — Programming

## Display Name
Programming (PRG)

## Display Description
Plan, approve, execute, inspect, correct, and complete bounded programming work through one evidence-governed Process Run.

*A Versioned Programming Process Definition over Ora's Generic Governed-Process Kernel*

*Version 2.0 — Generated Capability Definition*

*Derived from Process Inference v1.4, Process Formalization v2.5, and `ora.process-contracts/1.0`*

---

## Derivation Record

Phase 1.6 regenerated this specialization from the synchronized generating sources. Programming v1.0 remains derivation evidence, not an implementation baseline.

| PIF/PFF input | Exact source | Identity used | Derivation result |
|---|---|---|---|
| Capability and boundary inference | `Framework — Process Inference.md` v1.4 | body SHA-256 `b104d979f1d7cb3c5a9460553b3df9c53c8376c3a124bb7c10b7ea9b5055e09c` | Preserved artifact identity, inspection/mutation recognition, evidence freshness, controlled action, and direct-operation boundaries |
| Reusable definition formalization | `Framework — Process Formalization.md` v2.5 | body SHA-256 `7fe2fe8cfda8cad47971b96ffe6fa18886dac511b53db34b305a64a802e56c65` | Formalized one exact Process Definition, one graph, bounded judgments, seven directives, continuation/recovery, and one package manifest |
| Generic runtime contract | `process_contracts.py`, `governed_process_runtime.py` | `ora.process-contracts/1.0`, `ora.process-graph/1.0`, `ora.process-package/1.0`; accepted runtime baseline `bf55d21370031015e1f4187e5f830e463e8452ab` | Bound the specialization to the same object families and graph grammar used by non-programming processes |
| Programming v1.0 | This canonical's prior version | v1.0 at vault history before Phase 1.6 | Retained exact-identity discipline, review packets, bounded correction, independent review, and post-review drift checks; superseded intermediate `ACCEPT`, five-verdict assumptions, and reduced-assurance pseudo-transitions |

### Capability Discovery Record

The derivation queried the available capability categories before formalization:

| Category | Query result | Binding consequence |
|---|---|---|
| Tools | Repository inspection, Git identity, diffing, test execution, compilation, registry loading, and patch application are available; each declares inspection or mutation at invocation time | Concrete tools remain Run bindings, not definition-level assumptions |
| Skills | No installed skill is required to interpret or execute this definition | Skill-specific bindings remain optional |
| Frameworks | PIF v1.4, PFF v2.5, Process Coherence v4.0, Oversight Configuration v2.0, and F-Quality Gate v2.0 are available by their accepted topology | The specialization consumes their contracts without copying their engines |
| Approved Process Definitions | The generic contract schemas exist; no approved Programming v2 definition existed before this derivation | This file creates `ora/programming@2.0.0`; v1.0 is not invoked as a baseline |
| Solution patterns | Programming v1.0, the reconciled candidate salvage matrix, generic Gear 3 correction/recovery behavior, and external-editor workflows were inspected | Only architecture-compatible invariants survive |

No controlled mutation probe was needed to infer the reusable procedure. Read-only inspection and contract validation were sufficient. Because this capability is intended for registration, exact-version invocation, and later activation, PFF formalization is mandatory; same-Run PIF direct operation is not a substitute.

## Setup Questions

### What should happen?
Required. Describe the observable result in ordinary management language. Do not classify the request as planning, execution, verification, construction, or activation; Ora infers the least-authoritative PRG entry path and confirms it.

### Which project and artifacts are in scope?
Required. Confirm the project every time construction begins. Identify the repository, workspace, service, build output, configuration surface, or other state that may be read or changed. Exact identity must be resolved before approval or mutation.

### What must not happen?
Required before planning approval. State non-solutions, protected user work, prohibited effects, deadlines, cost limits, and policy boundaries.

### What prior plan or result already exists?
Required for `PRG-Execute` or `PRG-Verify`. Supply the exact approved Plan Execution Contract or the exact result/evaluation basis. These paths never invent missing upstream authority.

### What authority is available?
Required before consequential action. Construction, testing, registration, invocation, activation, local mutation, remote Git action, and other external effects are separate grants. One grant never implies another.

### What will count as evidence?
Required before a reviewed boundary. Identify checks, evidence providers, artifact identity providers, and an evaluator independent from the work being judged. Missing required evidence or independence withholds the transition.

### How should interruption and return work?
Optional unless a prior Run is resuming. Supply attention preferences, checkpoint or Run identity, time/resource bounds, and any changed external state.

## How to Use This File

Use one of four entry contracts over this one definition:

- `PRG-Run`: interview, plan, approve, execute, inspect, correct, and close.
- `PRG-Plan`: produce and independently review one canonical plan, then stop without target mutation.
- `PRG-Execute`: execute an exact approved plan without silently replanning.
- `PRG-Verify`: inspect an exact artifact state nonmutatively and return evidence/findings.

The Markdown is the complete human-readable definition. The embedded Generic Kernel Process Definition is its machine-checkable projection, not a second source. Planner, executor, judge, and overseer name step-bound functions; they are not Agent objects, durable actors, lifecycles, or separate engines.

## PURPOSE

Produce a verified programming result or a truthful non-completion record while preserving exact artifact identity, user work, plan approval, bounded authority, independent evidence, recoverable state, and deterministic transition control.

## INPUT CONTRACT

### Required inputs by path

| Path | Required input | Mutation at entry |
|---|---|---|
| `PRG-Run` | Management-language objective; project; target locator; constraints; available authority | None. The path requires plan approval before mutation; mutation remains unavailable until approval and preflight. |
| `PRG-Plan` | Objective; project; target locator; constraints | None for the entire path. |
| `PRG-Execute` | Approved plan ID/version/digest; approval evidence; exact bound baseline; granted actions | Only the exact approved actions after current-state revalidation. |
| `PRG-Verify` | Exact result identity; claimed bounded delta; evaluation basis; permitted inspection methods | None for the entire path. |

### Input rules

1. The first interview question is **What should happen?** Technical form is inferred after intent, not demanded from the Principal.
2. Construction confirms the project every time. Similar paths, worktrees, or repositories are not interchangeable.
3. A dirty worktree is evidence to preserve, not an error to erase. Pre-existing changes remain separated from the Run's delta.
4. Concrete tools, providers, reviewers, and permissions are bound only from current discovery or explicit authority. Plausible names are not bindings.
5. Unresolved information may remain symbolic until the next transition needs it. The Run then uses `ESCALATE` or `BLOCKED`; it never guesses.

## OUTPUT CONTRACT

### Primary artifacts

- **M1 — Approved Plan Execution Contract:** one canonical, versioned, digest-bound plan plus its approval record.
- **M2 — Accepted Programming Result:** exact final artifact identity, bounded delta, current evidence set, final review, and completion event produced only after final `ACCEPT`.
- **Versioned Capability Output:** when the authorized work constructs a reusable capability, an exact Process Definition/package artifact with construction evidence. Registration, invocation, and activation remain separate effects.

### One plan, two projections

M1 has one identity and two read-only projections:

| Projection | Audience and content | Integrity rule |
|---|---|---|
| **Principal projection** | Outcome, scope, exclusions, decisions required, risks, evidence strategy, attention points, and completion criteria in management language | Carries the same plan ID, version, and digest as the Technical projection; it cannot omit an effect that changes authority or risk |
| **Technical projection** | Exact artifacts, files/services, ordered steps, commands or capability requirements, grants, checks, recovery, and node/evidence bindings | Carries the same plan ID, version, and digest as the Principal projection; it cannot introduce actions absent from the canonical plan |

If the projections disagree, approval is invalid. Repair the canonical plan and regenerate both projections; never edit them as independent plans.

### Non-completion artifacts

Defect, Replan, Redefinition, typed Authority Request, Blocked, Pause, and Return packets preserve exact state and a deterministic next destination. A useful draft result may exist while completion is withheld, but it is never mislabeled accepted.

## EXECUTION TIER AND PATHS

Gear 3 is the preferred execution shape: one bounded planning/acting step, independent evaluation, correction, and re-evaluation. Higher or lower model arrangements may implement the same contracts but cannot weaken them.

All four PRG paths create the same Process Run object family, bind the same exact definition identity, use the same event/transition records, and select behavior through the `entrypoint` plus approved input/authority contracts. No `run_kind`, programming controller, dedicated parser, milestone bypass, or separate persistence model is permitted.

## MILESTONES DELIVERED

### M1 — Approved Plan Execution Contract

- **Paths:** final outcome for `PRG-Plan`; required intermediate artifact for `PRG-Run`; supplied prerequisite for `PRG-Execute`.
- **Acceptance:** independent plan review passes; Principal approves the exact digest; target baseline, scope, authority, checks, loops, stops, and unresolved bindings are explicit.
- **Directive:** intermediate review uses `PROCEED`; the `PRG-Plan` final boundary may use `ACCEPT` because the approved plan is that Run's final governed outcome.
- **Mutation rule:** no target mutation precedes M1 approval.

### M2 — Accepted Programming Result

- **Paths:** `PRG-Run`, `PRG-Execute`, and a successful `PRG-Verify` result.
- **Acceptance:** an independent final evaluator judges the exact artifact/digest and evidence set; post-review revalidation proves neither changed; every non-waivable criterion passes; each exception is explicitly authorized and recorded.
- **Directive:** only `ACCEPT` completes M2. `PASS`, `FAIL`, and `BROKEN` are observations supplied to transition evaluation.

## PROCESS APPLICATION CONTRACT

### Process Definition Identity and Applicability

- **Definition ID:** `ora/programming`
- **Version:** `2.0.0`
- **Digest:** `sha256:6996f3bc3696acf3ea1487ba662b157eddffda5d407762dacad830c86affd116`
- **Digest rule:** SHA-256 of this canonical body after replacing every occurrence of the declared definition digest with `sha256:` plus 64 zeroes and removing vault YAML. This avoids self-reference while binding the complete human and machine definition.
- **Status and scope:** approved for controlled governed invocation; universal programming specialization; not automatically activated.
- **Purpose:** Govern programming work through one generic Process Definition/Process Run kernel.
- **Applicability:** The process reads and may mutate external artifacts, uses bounded loops, depends on explicit authority/evidence, and requires an independent final decision.

### Generic Kernel Process Definition

The following projection must validate with `process_contracts.validate_process_definition`. Its graph is the machine navigation form of the natural-language contract below. The Markdown remains authoritative when presentation detail exceeds the schema.

<!-- PROGRAMMING_PROCESS_DEFINITION_BEGIN -->
```json
{
  "schema_version": "ora.process-contracts/1.0",
  "object_family": "process_definition",
  "definition_id": "ora/programming",
  "version": "2.0.0",
  "digest": "sha256:6996f3bc3696acf3ea1487ba662b157eddffda5d407762dacad830c86affd116",
  "title": "Governed Programming",
  "purpose": "Produce an exact programming plan or verified result under explicit authority, current evidence, bounded correction, and independent final review.",
  "status": "approved",
  "scope": {"kind": "universal", "selector": "domain:programming"},
  "input_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["entrypoint", "objective", "project_ref", "target_artifact_selectors"],
    "properties": {
      "entrypoint": {"enum": ["prg_run", "prg_plan", "prg_execute", "prg_verify"]},
      "objective": {"type": "string", "minLength": 1},
      "project_ref": {"type": "string", "minLength": 1},
      "target_artifact_selectors": {"type": "array", "minItems": 1, "items": {"type": "string"}},
      "approved_plan_ref": {"type": ["object", "null"]},
      "verification_basis": {"type": ["object", "null"]},
      "requested_authority_grants": {"type": "array", "items": {"enum": ["construct", "test", "register", "invoke", "activate", "mutate", "git_local", "git_remote", "external_effect"]}},
      "dialogue_ref": {"type": ["string", "null"]}
    },
    "additionalProperties": false
  },
  "output_schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["run_id", "status", "artifact_ids", "evidence_artifact_ids"],
    "properties": {
      "run_id": {"type": "string"},
      "status": {"enum": ["accepted", "returned", "blocked", "paused"]},
      "plan_artifact_id": {"type": ["string", "null"]},
      "principal_projection_artifact_id": {"type": ["string", "null"]},
      "technical_projection_artifact_id": {"type": ["string", "null"]},
      "artifact_ids": {"type": "array", "items": {"type": "string"}},
      "evidence_artifact_ids": {"type": "array", "items": {"type": "string"}},
      "constructed_definition_refs": {"type": "array", "items": {"type": "object"}}
    },
    "additionalProperties": false
  },
  "graph": {
    "schema_version": "ora.process-graph/1.0",
    "graph_id": "ora/programming/2.0.0",
    "entry_node_id": "entry-route",
    "nodes": [
      {"node_id": "entry-route", "kind": "decision", "label": "Select the confirmed PRG entry contract", "routes": [{"condition": "prg_run", "target_node_id": "intent-interview"}, {"condition": "prg_plan", "target_node_id": "intent-interview"}, {"condition": "prg_execute", "target_node_id": "inspect-scope"}, {"condition": "prg_verify", "target_node_id": "inspect-scope"}], "default_node_id": "blocked"},
      {"node_id": "intent-interview", "kind": "action", "label": "Conduct the management-language intent interview", "operation": "elicit_programming_intent", "next_node_id": "inspect-scope", "authority_grant_ids": ["grant-dialogue"], "artifact_access": ["scope:dialogue", "scope:declared_inputs"], "evidence_requirement_ids": ["ev-intent"], "external_effect": false},
      {"node_id": "inspect-scope", "kind": "action", "label": "Inspect exact artifacts, policies, and existing work", "operation": "inspect_programming_scope", "next_node_id": "scope-review", "authority_grant_ids": ["grant-inspect"], "artifact_access": ["scope:declared_inputs"], "evidence_requirement_ids": ["ev-identity", "ev-policy", "ev-authority"], "external_effect": false},
      {"node_id": "scope-review", "kind": "verification_boundary", "label": "Judge scope and identity", "evidence_requirement_ids": ["ev-intent", "ev-identity", "ev-policy", "ev-authority"], "routes": {"PROCEED": "mode-after-scope", "REVISE": "inspect-scope", "REPLAN": "intent-interview", "REDEFINE": "definition-plan", "ESCALATE": "authority", "BLOCKED": "blocked"}},
      {"node_id": "mode-after-scope", "kind": "decision", "label": "Continue according to the selected PRG contract", "routes": [{"condition": "prg_run", "target_node_id": "plan"}, {"condition": "prg_plan", "target_node_id": "plan"}, {"condition": "prg_execute", "target_node_id": "bind-plan"}, {"condition": "prg_verify", "target_node_id": "inspect-result"}], "default_node_id": "blocked"},
      {"node_id": "plan", "kind": "action", "label": "Produce the canonical plan and both projections", "operation": "produce_programming_plan", "next_node_id": "plan-review", "authority_grant_ids": ["grant-plan"], "artifact_access": ["scope:declared_inputs", "scope:plan_outputs"], "evidence_requirement_ids": ["ev-plan", "ev-identity", "ev-authority"], "external_effect": false},
      {"node_id": "plan-review", "kind": "verification_boundary", "label": "Independently review the exact plan", "evidence_requirement_ids": ["ev-plan", "ev-plan-projection-parity", "ev-review", "ev-authority"], "routes": {"PROCEED": "plan-approval", "REVISE": "plan", "REPLAN": "intent-interview", "REDEFINE": "definition-plan", "ESCALATE": "authority", "BLOCKED": "blocked"}},
      {"node_id": "plan-approval", "kind": "human_checkpoint", "label": "Approve the exact canonical plan before mutation", "authority_request_type": "plan_approval", "on_approved_node_id": "post-plan-mode", "on_denied_node_id": "blocked", "on_unavailable_node_id": "authority"},
      {"node_id": "post-plan-mode", "kind": "decision", "label": "Stop with M1 or begin approved execution", "routes": [{"condition": "prg_plan", "target_node_id": "final-review"}, {"condition": "prg_run", "target_node_id": "execute-preflight"}], "default_node_id": "blocked"},
      {"node_id": "bind-plan", "kind": "action", "label": "Bind and revalidate the supplied approved plan", "operation": "bind_approved_plan", "next_node_id": "execute-preflight", "authority_grant_ids": ["grant-inspect"], "artifact_access": ["scope:declared_inputs", "scope:plan_outputs"], "evidence_requirement_ids": ["ev-plan", "ev-identity", "ev-authority"], "external_effect": false},
      {"node_id": "execute-preflight", "kind": "action", "label": "Revalidate artifact, evidence, and authority before acting", "operation": "programming_preflight", "next_node_id": "execute-step", "authority_grant_ids": ["grant-inspect"], "artifact_access": ["scope:declared_inputs", "scope:declared_outputs"], "evidence_requirement_ids": ["ev-identity", "ev-authority", "ev-recovery"], "external_effect": false},
      {"node_id": "execute-step", "kind": "action", "label": "Perform one approved programming step", "operation": "execute_approved_programming_step", "next_node_id": "attempt-review", "authority_grant_ids": ["grant-execute-approved-step"], "artifact_access": ["scope:declared_inputs", "scope:declared_outputs", "scope:declared_external_effects"], "evidence_requirement_ids": ["ev-action", "ev-delta", "ev-check"], "external_effect": true},
      {"node_id": "inspect-result", "kind": "action", "label": "Inspect the supplied result without mutation", "operation": "inspect_programming_result", "next_node_id": "attempt-review", "authority_grant_ids": ["grant-test"], "artifact_access": ["scope:declared_inputs", "scope:declared_outputs"], "evidence_requirement_ids": ["ev-identity", "ev-delta", "ev-check"], "external_effect": false},
      {"node_id": "attempt-review", "kind": "verification_boundary", "label": "Independently judge the current attempt", "evidence_requirement_ids": ["ev-identity", "ev-delta", "ev-check", "ev-review"], "routes": {"PROCEED": "work-remaining", "REVISE": "revision-route", "REPLAN": "replan-route", "REDEFINE": "definition-plan", "ESCALATE": "authority", "BLOCKED": "blocked"}},
      {"node_id": "work-remaining", "kind": "decision", "label": "Continue approved work or prepare final review", "routes": [{"condition": "authorized_work_remains", "target_node_id": "execute-step"}], "default_node_id": "final-review"},
      {"node_id": "revision-route", "kind": "decision", "label": "Return findings or enter bounded correction", "routes": [{"condition": "prg_verify", "target_node_id": "returned"}], "default_node_id": "correction-loop"},
      {"node_id": "correction-loop", "kind": "bounded_loop", "label": "Bound programming correction", "body_node_id": "correct", "exit_node_id": "no-progress", "max_iterations": 12, "progress_evidence_requirement_ids": ["ev-progress"]},
      {"node_id": "correct", "kind": "action", "label": "Correct the cited execution or artifact defect", "operation": "correct_programming_defect", "next_node_id": "attempt-review", "authority_grant_ids": ["grant-execute-approved-step"], "artifact_access": ["scope:declared_outputs"], "evidence_requirement_ids": ["ev-action", "ev-delta", "ev-check", "ev-progress"], "external_effect": true},
      {"node_id": "no-progress", "kind": "decision", "label": "Classify why correction cannot continue", "routes": [{"condition": "plan_defect", "target_node_id": "replan-route"}, {"condition": "definition_defect", "target_node_id": "definition-plan"}, {"condition": "reserved_authority_required", "target_node_id": "authority"}], "default_node_id": "blocked"},
      {"node_id": "replan-route", "kind": "decision", "label": "Replan only where the entry contract permits it", "routes": [{"condition": "prg_run", "target_node_id": "plan"}], "default_node_id": "returned"},
      {"node_id": "definition-plan", "kind": "action", "label": "Plan the bounded replacement-definition work", "operation": "plan_programming_redefinition", "next_node_id": "definition-plan-review", "authority_grant_ids": ["grant-plan"], "artifact_access": ["scope:process_definition"], "evidence_requirement_ids": ["ev-definition-defect", "ev-plan", "ev-authority"], "external_effect": false},
      {"node_id": "definition-plan-review", "kind": "verification_boundary", "label": "Review the replacement-definition plan", "evidence_requirement_ids": ["ev-definition-defect", "ev-plan", "ev-review", "ev-authority"], "routes": {"PROCEED": "definition-plan-approval", "REVISE": "definition-plan", "REPLAN": "intent-interview", "ESCALATE": "authority", "BLOCKED": "blocked"}},
      {"node_id": "definition-plan-approval", "kind": "human_checkpoint", "label": "Approve replacement-definition construction before mutation", "authority_request_type": "definition_construction_approval", "on_approved_node_id": "redefine", "on_denied_node_id": "blocked", "on_unavailable_node_id": "authority"},
      {"node_id": "redefine", "kind": "action", "label": "Draft and test an exact replacement definition", "operation": "redefine_programming_process", "next_node_id": "definition-review", "authority_grant_ids": ["grant-construct"], "artifact_access": ["scope:process_definition"], "evidence_requirement_ids": ["ev-definition-defect", "ev-definition", "ev-check"], "external_effect": true},
      {"node_id": "definition-review", "kind": "verification_boundary", "label": "Review and bind the exact replacement definition", "evidence_requirement_ids": ["ev-definition-defect", "ev-definition", "ev-check", "ev-review"], "routes": {"PROCEED": "plan", "REVISE": "redefine", "REPLAN": "intent-interview", "ESCALATE": "authority", "BLOCKED": "blocked"}},
      {"node_id": "authority", "kind": "human_checkpoint", "label": "Resolve one typed reserved-authority request", "authority_request_type": "programming_reserved_authority", "on_approved_node_id": "resume-route", "on_denied_node_id": "blocked", "on_unavailable_node_id": "blocked"},
      {"node_id": "resume-route", "kind": "decision", "label": "Resume at the persisted authority-return target", "routes": [{"condition": "resume_plan", "target_node_id": "plan"}, {"condition": "resume_execute", "target_node_id": "execute-preflight"}, {"condition": "resume_definition", "target_node_id": "definition-plan"}], "default_node_id": "blocked"},
      {"node_id": "final-review", "kind": "verification_boundary", "label": "Independently judge the exact final outcome", "evidence_requirement_ids": ["ev-identity", "ev-delta", "ev-check", "ev-review", "ev-final-binding"], "routes": {"ACCEPT": "accepted", "REVISE": "revision-route", "REPLAN": "replan-route", "REDEFINE": "definition-plan", "ESCALATE": "authority", "BLOCKED": "blocked"}},
      {"node_id": "accepted", "kind": "terminal_state", "label": "Accepted governed outcome", "outcome": "accepted"},
      {"node_id": "returned", "kind": "terminal_state", "label": "Return exact findings or replanning need", "outcome": "returned"},
      {"node_id": "blocked", "kind": "terminal_state", "label": "No authorized evidence-supported continuation", "outcome": "blocked"}
    ]
  },
  "package_manifest": {
    "schema_version": "ora.process-package/1.0",
    "package_id": "ora/programming",
    "package_version": "2.0.0",
    "definition_ref": {"definition_id": "ora/programming", "version": "2.0.0", "digest": "sha256:6996f3bc3696acf3ea1487ba662b157eddffda5d407762dacad830c86affd116"},
    "entry_member_id": "programming-definition",
    "members": [{
      "member_id": "programming-definition",
      "role": "process_definition",
      "required": true,
      "media_type": "text/markdown",
      "locator": {"kind": "file", "ref": "Projects/Ora/Framework — Programming.md"},
      "identity": {"kind": "content_digest", "digest": "sha256:6996f3bc3696acf3ea1487ba662b157eddffda5d407762dacad830c86affd116", "coverage": ["complete_canonical_body", "embedded_kernel_projection"], "captured_at": "2026-07-17T00:00:00-07:00", "fresh_until": "2036-07-17T00:00:00-07:00"}
    }]
  },
  "labels": ["programming", "governed", "generic-kernel", "pif-1.4-derived", "pff-2.5-formalized"]
}
```
<!-- PROGRAMMING_PROCESS_DEFINITION_END -->

### External Artifacts and Identity

| Artifact or State ID | Description | Identity requirement | Ambiguity or drift behavior |
|---|---|---|---|
| `ART-INTENT` | Objective, non-solutions, constraints, and approved revisions | Durable Dialogue or authoritative user/project record with digest | Ask only the material question; withhold affected planning or action |
| `ART-TARGET` | Repository, workspace, files, services, configuration, dependencies, and relevant untracked state | Content-complete composite identity; include tracked, staged, unstaged, relevant untracked, generated, dependency, linked-worktree/submodule, and relied-on external state; state exclusions | Stop on path ambiguity; preserve existing work; invalidate affected evidence after drift |
| `ART-POLICY` | Repository instructions, project rules, user directives, platform constraints | Exact source, precedence, scope, version/digest | Stop before action whose authority is unclear |
| `ART-PLAN` | Canonical M1 plus Principal and Technical projections | One plan ID/version/digest and projection-parity evidence | Projection disagreement invalidates approval |
| `ART-RESULT` | Current produced or inspected programming result | Exact locator, role, digest/version, lineage, pre-existing-change separation | No review or completion against a stale/replaced identity |
| `ART-EVIDENCE` | Checks, observations, reviews, receipts, and findings | Exact producer/method/input/result/time/environment/subject identity | Recapture after relevant mutation, dependency/provider change, or external drift |
| `ART-CHECKPOINT` | Persisted Run/segment/attempt/action state | Run/definition/plan/node IDs, artifact digests, event sequence, completed-effect receipts | Refuse resume or replay when state cannot be reconstructed exactly |
| `ART-DEFINITION` | Any capability constructed or replaced by the programming work | Definition ID/version/digest/package/lineage and test evidence | Construction never implies registration, invocation, or activation |

### Authorized Actions

| Action ID | Function | Preconditions and authority | Effect and proof |
|---|---|---|---|
| `ACT-INSPECT` | Planner, executor, judge, or overseer step | Read grant and artifact selector | Nonmutating observation with exact subject identity |
| `ACT-CONSTRUCT` | Executor step | Approved plan plus explicit `construct` grant | Create or modify code/configuration/capability artifacts; exact delta and identity required |
| `ACT-TEST` | Executor or independent judge step | Explicit `test` grant; mutation effects declared separately | Exact command/method, environment, output, exit/result, and subject digest |
| `ACT-REGISTER` | Executor step | Separate `register` grant for exact definition/package identity | Registry record and receipt; does not invoke or activate |
| `ACT-INVOKE` | Mechanical dispatcher | Separate `invoke` grant for an exact registered version and Run contract | Child/Run invocation record and deterministic return binding; does not activate standing operation |
| `ACT-ACTIVATE` | Executor step at a human checkpoint | Separate reserved `activate` authority naming triggers, scope, limits, and rollback | Activation record and exact active version; never inferred from registration or invocation |
| `ACT-MUTATE` | Executor step | Approved plan and exact write scope | Bounded local mutation with pre/post identity and recoverable checkpoint where applicable |
| `ACT-GIT-LOCAL` | Executor step | Explicit local Git grant | Named commit/branch/index effect and resulting Git identity |
| `ACT-GIT-REMOTE` | Executor step | Separate remote authority and destination | Remote receipt and synchronized ref identity; no force operation unless separately authorized |
| `ACT-EXTERNAL` | Executor step | Explicit effect-specific authority | Immutable receipt bound to target, request, response, and post-state |
| `ACT-RECOVER` | Executor/recovery step | Recovery contract proves replay safety | Restored state or deterministic stop record; recorded mutation is never replayed without proof |

`ACT-CONSTRUCT`, `ACT-TEST`, `ACT-REGISTER`, `ACT-INVOKE`, and `ACT-ACTIVATE` are deliberately separate. Authority may grant any subset. Constructing or testing a capability does not authorize registration; registration does not authorize invocation; invocation does not authorize activation.

### Planning and Execution Nodes

The embedded graph is the edge authority. Natural-language node responsibilities are:

| Node family | Bounded responsibility | Required output |
|---|---|---|
| Intent and scope | Translate management intent into exact objective/scope without choosing a nearby technical substitute | `ART-INTENT`, `ART-TARGET`, `ART-POLICY`, unresolved-binding list |
| Planning | Produce one canonical plan and both projections; cite exact grants, evidence, stop, recovery, and criteria | Proposed M1 and `EV-PLAN-PROJECTION-PARITY` |
| Approval | Independent plan review followed by Principal approval of the same digest | Approved M1 or typed non-approval route |
| Execution | Perform only the next approved action; persist artifact/effect identity before another action | Attempt and effect records |
| Review | Judge current evidence against exact criteria without acting on the target | One supported directive and findings packet |
| Redefinition | Preserve defect evidence, approve the bounded replacement-definition plan, draft/test an exact replacement, and rebind the same nonterminal Run only after review | Approved definition plan, replacement definition identity, or typed authority request |
| Finalization | Independently review and rederive the exact subject/evidence bindings | `ACCEPT` completion or one explicit non-completion route |

### Bounded Judgment Contracts

| Judgment ID | Step-bound function | Bounded question | Permitted directives/actions | Required evidence and stop |
|---|---|---|---|---|
| `J-PLAN` | Planner | What exact approved sequence can achieve the stated outcome within current authority? | Propose/revise plan; request clarification; `ESCALATE`/`BLOCKED` | Intent, identity, policy, capability discovery; stop before inventing a binding |
| `J-EXECUTE` | Executor | What is the next exact plan-authorized action and what proof must it emit? | Perform one granted action; pause; return effect receipt | Current plan/baseline/authority/checkpoint; stop on drift, stale authority, or undeclared effect |
| `J-ATTEMPT` | Judge independent of the acting step | Does current evidence support a declared continuation? | `PROCEED`, `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, `BLOCKED` | Current identity/delta/checks; stop on missing independence or stale evidence |
| `J-FINAL` | Final judge independent of all judged acting steps | Does the exact current outcome satisfy every applicable final criterion? | `ACCEPT`, `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, `BLOCKED` | Exact result/evidence digests plus post-review revalidation; only this judgment may support completion |
| `J-COHERENCE` | Overseer/Process Coherence step | Is the proposed directive supported by Run state, locks, evidence, authority, loop progress, and declared routes? | Select one declared directive; no target mutation and no invented direction | Full transition packet; stop on ambiguous or undeclared route |

Every judgment record binds `judgment_id`, Run and definition identity, current node, exact artifacts, evidence, grant IDs, permitted conclusions, selected directive, return/resume target, and typed escalation request when applicable. These are functions at nodes, not durable actors.

### Verification Boundaries

| Boundary | Placement | Result examined | Independent requirement | Failure routes |
|---|---|---|---|---|
| `B-SCOPE` | Internal before planning/execution | Exact intent, target, policy, preserved work, proposed scope | Independent from scope investigation when material | `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, `BLOCKED` |
| `B-PLAN` | M1 boundary | Canonical plan and both projections | Independent plan judge plus Principal approval | `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, `BLOCKED`; success is intermediate `PROCEED` except final `PRG-Plan` packaging |
| `B-ATTEMPT` | Internal after each bounded attempt/inspection | Exact post-attempt identity, delta, checks, effects, progress | Judge independent from acting step | `PROCEED`, `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, `BLOCKED` |
| `B-DEFINITION` | Internal after `REDEFINE` work | Old/new definition identities, defect evidence, tests, migration/resume target | Independent from definition authoring | `PROCEED`, `REVISE`, `REPLAN`, `ESCALATE`, `BLOCKED` |
| `B-RESUME` | Internal before resumed action | Checkpoint/current state, receipts, drift, stale evidence, next action | Independent from recovery actor where mutation occurred | `PROCEED`, `REPLAN`, `REDEFINE`, `ESCALATE`, `BLOCKED` |
| `B-FINAL` | Final M1 or M2 boundary | Exact plan/result and complete current evidence | Qualified evaluator independent from judged acting steps | `ACCEPT`, `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, `BLOCKED` |

All v1.0 boundary intent survives. `B-DEFINITION` is added because v2.0 now has a first-class generic `REDEFINE` route; this increases observability before a Run rebinds to an exact replacement version.

### Evidence Contract

| Evidence ID | Claim | Freshness/independence | Missing or stale behavior |
|---|---|---|---|
| `EV-INTENT` | Objective, non-solutions, constraints, and project are explicit | Current through approved revision | Clarify, replan, or block |
| `EV-IDENTITY` | Exact artifact/external state is known and drift-detectable | Capture before approval/action/review, after action, at resume, and after final review | Withhold action/review; recapture |
| `EV-POLICY` | Applicable instructions and precedence are known | Refresh after policy/source change | `ESCALATE` or `BLOCKED` |
| `EV-AUTHORITY` | Exact action/decision is authorized | Must match current plan, scope, version, target, and time | `ESCALATE`; never broaden by inference |
| `EV-PLAN` | One exact canonical plan is reviewable | Refresh after plan/baseline/authority change | Revise or replan |
| `EV-PLAN-PROJECTION-PARITY` | Principal and Technical views represent the same plan | Recompute after either rendering | Invalidate approval |
| `EV-ACTION` | A consequential action occurred as authorized | Capture immediately with receipt | Treat effect as unknown; stop/recover |
| `EV-DELTA` | Run changes are exact and separated from prior work | Recompute after mutation or external edit | Withhold attempt/final acceptance |
| `EV-CHECK` | Criterion-relevant check produced stated result | Stale after affected artifact/dependency/config/provider change | Rerun or mark unknown |
| `EV-REVIEW` | Independent criterion-level judgment exists | Tied to exact subject/evidence set | Boundary cannot pass |
| `EV-PROGRESS` | Another correction has a new hypothesis or measurable gain | Per judged attempt | Stop blind churn; classify failure |
| `EV-RECOVERY` | Resume avoids mutation replay and preserves completed work | Revalidate immediately before resume | Stop or return authority |
| `EV-DEFINITION` | Replacement definition is exact, tested, and resumable | Current exact version/digest only | Keep Run redefining; no rebind |
| `EV-FINAL-BINDING` | Result and evidence remained unchanged after final judgment | Derived after evaluator returns | Invalidate candidate decision; no `ACCEPT` |

Evidence becomes stale when a relevant artifact, dependency, configuration, policy, authority, provider, external state, accepted plan, or evidence artifact changes. Staleness invalidates the supported claim, not necessarily the entire Run. Recapture only affected evidence and retain the superseded identity in lineage.

### Loop Policy

| Loop | Default hard bound | Continue only when | Bound reached or no progress |
|---|---|---|---|
| Planning correction | 3 reviewed versions | Correctable defect and current objective/scope | Classify `REPLAN`, `REDEFINE`, `ESCALATE`, or `BLOCKED` |
| Programming correction | 12 judged attempts | New testable hypothesis, remaining authority/resources, and `EV-PROGRESS` | Bound stops churn but does not diagnose; Process Coherence selects the supported non-`REVISE` route |
| Definition correction | 3 reviewed replacement versions | Definition defect remains correctable within construction authority | `ESCALATE` for reserved promotion/activation/scope authority or `BLOCKED` |
| Infrastructure retry | 3 attempts per operation unless plan states a lower finite bound | Failure is transport/infrastructure, not quality | Record infrastructure failure, then resume, `ESCALATE`, or `BLOCKED`; never convert it directly into a quality directive |

The runtime must preserve ten or more programming attempts without state loss when M1 grants that ceiling. A high ceiling permits continued evidence-backed work; it never forces blind churn.

### Transition Policy

The graph and this table use exactly the seven Process Run directives:

| Directive | Programming meaning | Deterministic destination |
|---|---|---|
| `PROCEED` | An intermediate boundary is supported within the current definition, plan, and authority | Next declared node or persisted resume target |
| `ACCEPT` | The active PRG path's final boundary is satisfied | Terminal accepted state and completion record |
| `REVISE` | Execution or produced artifact is defective; plan and definition remain sound | Bounded correction, or terminal findings return for nonmutating `PRG-Verify` |
| `REPLAN` | Evidence invalidates the plan but not the reusable definition | Planning in `PRG-Run`; exact Replan Return in `PRG-Execute`/`PRG-Verify` |
| `REDEFINE` | The reusable Programming definition is defective or insufficient | Same nonterminal Run returns to definition authority with old identity, defect evidence, replacement draft, tests, and resume target; no human queue by default |
| `ESCALATE` | A typed reserved human authority is required | Human checkpoint with request type, exact decision, options, evidence, and resume/stop target |
| `BLOCKED` | No authorized evidence-supported continuation exists | Terminal blocked state preserving artifacts and restart conditions |

`PASS`, `FAIL`, and `BROKEN` are observations only. `ACCEPT WITH EXCEPTIONS` and `REDUCED ASSURANCE` are not directives. An authorized exception may be recorded in an accepted result only when the final criteria explicitly permit it; the transition remains `ACCEPT`. When required independent final judgment is unavailable, use `ESCALATE` to obtain authority/reviewer or `BLOCKED`; a draft result may be returned but M2 is withheld.

### Independent Final Gate

- **Final gate ID:** `PRG-FINAL-2`
- **Evaluator:** qualified and independent from every acting step whose output it judges.
- **Inputs:** exact Run/definition/plan identity; active PRG path; final artifact identity; bounded delta; current evidence; internal boundary records; authority and exception records.
- **Acceptance:** every applicable criterion passes; effects match grants; evidence is current; no unreviewed correction remains; the evaluator's subject and evidence digests match the independently rederived post-review bindings.
- **Rejection:** use the exact mode-qualified `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, or `BLOCKED` graph route.
- **Completion:** only the final boundary's persisted `ACCEPT` transition may create M1 completion for `PRG-Plan` or M2 for the other successful paths.

### Continuation and Recovery

Persist before pause or external effect: Run/definition/plan/node IDs; attempt and loop state; exact artifact/evidence identities; approved grants; completed actions; checkpoint; receipts and idempotency keys; child invocation/return identities; typed authority request; and deterministic resume/stop target.

On restart:

1. Reconstruct from authoritative records, never conversational memory alone.
2. Compare checkpoint identities with current artifacts, policy, authority, dependencies, and external state.
3. Validate every post-checkpoint external-effect receipt against the digest recorded with that effect.
4. Mark affected evidence stale and route through `B-RESUME`.
5. Never replay a recorded mutation unless exact proof establishes replay safety.
6. Bind any child return to exact definition identity, output artifact identities, and acceptance evidence before resuming the parent.

### Code Visibility and External Editors

Ora is the control surface, not the only editor. The Principal may inspect code, diffs, plans, evidence, receipts, and Run state at any time and may use an external editor. External edits are treated as artifact changes: preserve them, recapture identity, separate them from the Run delta, invalidate affected evidence, and re-evaluate the plan/authority before further mutation. Never hide code behind an opaque generated application, overwrite unexplained user work, or require the user to surrender ordinary repository tools.

### Package Manifest

This is one consolidated capability file. The vault canonical and operational mirror carry the same body; the embedded kernel projection is not a second conceptual member.

| Member | Role | Locator | Identity | Required |
|---|---|---|---|---|
| `programming-definition` | Process Definition and complete instruction | `Projects/Ora/Framework — Programming.md` | `ora/programming@2.0.0` plus declared normalized-body digest | Yes |

### Unresolved Bindings and Assurance Limits

Concrete project, repository, identity provider, executor tool, evidence provider, independent evaluator, persistence location, remote destination, registration target, invocation target, and activation policy are Run-time bindings. Until bound, affected actions remain unavailable. The definition itself grants nothing and activates nothing.

## PROCESSING LAYERS

1. **Management intent interview:** ask what should happen; identify project, non-solutions, constraints, attention needs, and likely PRG path.
2. **Capability and artifact discovery:** query tools, skills, frameworks, Process Definitions, patterns, policies, and exact target state; classify each action inspection/mutation.
3. **Scope review:** independently confirm objective fit, exact identity, user-work preservation, and authority boundary.
4. **Canonical planning:** produce M1 and both projections; review and obtain approval before mutation.
5. **Preflight/resume:** revalidate plan, artifact, authority, evidence, checkpoint, and replay safety.
6. **Bounded action or inspection:** perform one approved action or nonmutating verification step; persist exact evidence/receipt.
7. **Independent attempt judgment:** Process Coherence evaluates the declared transition; policy dispatches it mechanically.
8. **Correction, replanning, redefining, or authority return:** follow the supported route without collapsing failure classes.
9. **Independent final review and closeout:** judge exact current bindings, revalidate after review, and accept or preserve truthful non-completion.

## EVALUATION CRITERIA

1. The selected PRG path is the least-authoritative path consistent with the management intent.
2. All four paths use `ora/programming@2.0.0`, the generic Run/contracts, and no private controller or `run_kind`.
3. The project, exact target identity, pre-existing changes, policies, non-solutions, and exclusions are explicit.
4. Principal and Technical projections share one plan ID/version/digest and no semantic divergence.
5. No mutation occurs before exact plan approval; no action exceeds its grant or artifact selector.
6. Construct, test, register, invoke, and activate authority are mechanically distinct.
7. Every material judgment is step-bound, evidence-backed, and limited to declared conclusions/directives/actions.
8. Intermediate continuation uses `PROCEED`; only the active path's final boundary uses `ACCEPT`.
9. `REVISE`, `REPLAN`, `REDEFINE`, `ESCALATE`, and `BLOCKED` preserve their distinct failure/authority meanings.
10. Evidence is bound to the exact subject and invalidated after relevant drift.
11. Pause/restart preserves state and never replays a mutation without exact safety proof.
12. Final acceptance is independent, post-review bindings match, code remains visible, and every external effect has lineage/receipt.
13. Any versioned capability output records construction separately from registration, invocation, and activation.

## NAMED FAILURE MODES

- **Technical-form interview:** asking the Principal to choose implementation categories before stating the outcome. Return to **What should happen?**
- **Projection fork:** Principal and Technical views become separate plans. Invalidate approval and regenerate both from the canonical plan.
- **Approval-after-action:** mutation precedes M1 approval. Stop, record the unauthorized effect, recover if authorized, and escalate.
- **Authority cascade:** construction or registration is treated as permission to invoke or activate. Refuse the undeclared effect.
- **Controller resurrection:** a Programming parser/controller/runtime bypasses the generic kernel. Reject the implementation.
- **Intermediate acceptance:** `ACCEPT` is used to continue ordinary work. Replace it with `PROCEED`; reserve `ACCEPT` for the active path's final boundary.
- **Observation transition:** `PASS`, `FAIL`, or `BROKEN` changes lifecycle state directly. Return the observation to Process Coherence.
- **Redefinition queue collapse:** every definition defect interrupts a human. Continue authorized draft/test work under `REDEFINE`; use `ESCALATE` only for reserved authority.
- **Blind churn:** attempt budget forces repeated work without a new hypothesis or progress. Stop and classify the failure.
- **Stale proof:** evidence survives a relevant artifact/provider/dependency change. Invalidate and recapture affected evidence.
- **Receiptless recovery:** resume assumes an external effect did not happen. Refuse replay and return authority.
- **Opaque code:** generated UI or automation hides the actual code/diff/evidence. Restore code visibility and external-editor compatibility.
- **Near-neighbor completion:** a technically valid change satisfies a nearby objective rather than the approved intent. `REPLAN`, `REDEFINE`, or block; never accept by resemblance.

## EXECUTION COMMANDS

1. Confirm `PRG-Run`, `PRG-Plan`, `PRG-Execute`, or `PRG-Verify` after the management-language interview.
2. Query available capabilities and exact artifact/policy state before binding tools or proposing mutation.
3. Create one generic Process Run bound to `ora/programming@2.0.0`; attach plan, authority, scope, judgment, evidence, correction, continuation, recovery, and escalation contracts.
4. Traverse only the embedded graph and active path. Resolve each boundary to one declared directive and let the generic dispatcher apply it.
5. Preserve every artifact/effect identity and return the accepted outcome or exact non-completion packet.

## VERSION HISTORY

- **v2.0 — 2026-07-17:** Regenerated from PIF v1.4 and PFF v2.5. Bound the consolidated specialization to `ora.process-contracts/1.0`; added the machine-checkable embedded definition; management-language intent interview; one canonical plan with Principal/Technical projections; explicit construct/test/register/invoke/activate authority separation; step-bound planner/executor/judge/overseer judgments; four PRG paths over one Run; all seven directives with intermediate `PROCEED` and final-only `ACCEPT`; generic `REDEFINE` versus typed `ESCALATE`; stale-evidence invalidation; pause/restart/recovery; external-editor/code visibility; and versioned capability output.
- **v1.0 — 2026-07-15 (superseded as active definition; retained in history):** Established exact artifact identity, approved planning, four programming paths, compact boundary packets, independent review, bounded correction, accepted-exception records, and post-review drift checking. Its old intermediate `ACCEPT` outcomes, reduced-assurance pseudo-transition, and pre-v2.5 derivation semantics do not govern v2.0.

## USER INPUT

[Describe what should happen, the project and target artifacts, what must not happen, and any prior plan/result. Ora will infer and confirm the least-authoritative PRG path before consequential action.]

---

*End of Framework — Programming v2.0*
