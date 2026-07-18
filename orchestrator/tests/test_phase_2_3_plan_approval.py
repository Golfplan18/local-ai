"""G1.1 Phase 2.3 — canonical plan and approval boundary proofs."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
os.environ.setdefault("ORA_HOME", str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import conversation_memory as memory  # noqa: E402
import governed_process_runtime as runtime  # noqa: E402
import process_entry_routing as entry  # noqa: E402
import process_management_interview as interview  # noqa: E402
import process_plan_approval as planning  # noqa: E402
from server import server  # noqa: E402


NOW = "2026-07-18T12:00:00Z"
ANSWERS = {
    "intended_result": "A reconciled weekly cash-flow report should be delivered.",
    "affected_parties": "The finance team uses it, and the principal is affected.",
    "inputs_outputs": "It reads invoice CSV files and produces a reconciled PDF report.",
    "reuse": "This is a repeatable capability for future Runs.",
    "initiation": "A finance user starts it manually on demand.",
    "authority": "Ora may choose formatting without asking, but must ask before changing totals.",
    "exceptions": "If an invoice is missing, stop and return to me.",
    "permissions": "Ora may read invoice files and may write the report.",
    "evidence": "Accept when the reconciliation tests pass.",
    "stopping": "Stop and ask me when permission or evidence is missing.",
}


def route():
    return entry.route_process_entry({
        "source": "natural_language",
        "objective": "Automate my weekly cash-flow report.",
        "project_ref": "ora",
        "project_confirmed": True,
    })


def basis(target: Path) -> dict:
    return {
        "target_path": str(target),
        "non_solutions": ["Do not email, publish, deploy, or activate anything."],
        "scope": ["report.py", "tests/test_report.py"],
        "instructions": [{
            "source": "AGENTS.md",
            "digest": "sha256:" + hashlib.sha256(b"test policy").hexdigest(),
            "precedence": "repository",
            "scope": "the exact target repository",
        }],
        "architecture": ["Keep calculation, rendering, and delivery boundaries separate."],
        "dependencies": ["Python standard library and the existing test runner."],
        "implementation_sequence": [
            {
                "step_id": "step-report",
                "description": "Implement the bounded report calculation and rendering change.",
                "depends_on": [],
                "artifacts": ["report.py"],
                "action": "mutate",
            },
            {
                "step_id": "step-test",
                "description": "Add and run exact reconciliation tests.",
                "depends_on": ["step-report"],
                "artifacts": ["tests/test_report.py"],
                "action": "test",
            },
        ],
        "expected_transitions": [
            "The report changes from unverified totals to reconciled output."
        ],
        "tool_permissions": ["Read the repository and write only the declared files."],
        "tests": ["Run the exact reconciliation test suite against the final repository identity."],
        "risks": ["Incorrect totals; stop on any unexplained variance."],
        "recovery": ["Restore the exact pre-action checkpoint if a bounded mutation fails."],
        "completion_criteria": ["All reconciliation tests pass against the exact result."],
        "replanning_triggers": ["Target baseline, scope, authority, or architecture changes."],
        "loop_policy": {
            "max_attempts": 3,
            "repeated_defect_limit": 2,
            "progress_required": True,
            "on_no_progress": "REPLAN",
        },
        "execution_handoff": {
            "requested_actions": ["mutate", "test"],
            "artifact_selectors": ["report.py", "tests/test_report.py"],
            "stop_conditions": ["baseline drift", "permission ambiguity"],
        },
        "activation": {
            "requested": False,
            "mode": "manual invocation only",
            "separate_approval_required": True,
        },
        "versioning": ["Create a new plan version for every material revision."],
    }


class Phase23Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "target"
        self.target.mkdir()
        (self.target / "AGENTS.md").write_text("test policy", encoding="utf-8")
        (self.target / "report.py").write_text("TOTAL = 1\n", encoding="utf-8")
        (self.target / "tests").mkdir()
        (self.target / "tests" / "test_report.py").write_text(
            "def test_total(): assert True\n", encoding="utf-8"
        )
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.runtime = runtime.GovernedProcessRuntime(
            self.root / "runs", now=lambda: NOW
        )
        self.interview = interview.ManagementInterviewService(
            runtime=self.runtime,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            now=lambda: NOW,
        )
        state = self.interview.start_or_resume("dialogue-plan", route())
        while state["status"] == "interviewing":
            question = state["current_question"]
            state = self.interview.answer(
                "dialogue-plan",
                ANSWERS[question["dimension"]],
                question_id=question["question_id"],
                idempotency_key=f"interview:{question['dimension']}",
            )
        self.interview_state = state
        self.service = planning.ProcessPlanApprovalService(
            runtime=self.runtime,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )

    def propose(self, *, key="proposal:1", value=None):
        return self.service.propose(
            "dialogue-plan",
            value or basis(self.target),
            planner_id="planner:programming",
            idempotency_key=key,
        )

    def approve(self, state, *, key="approval:1", decision="approve_without_start"):
        plan = state["current_plan"]
        return self.service.approve(
            "dialogue-plan",
            decision=decision,
            plan_ref={field: plan[field] for field in ("plan_id", "version", "digest")},
            baseline_digest=plan["repository_artifact_scope"]["target"]["identity"]["digest"],
            decision_by="principal:user",
            idempotency_key=key,
        )


class Phase23ServiceTests(Phase23Fixture):
    def test_one_canonical_plan_derives_both_required_views(self):
        state = self.propose()
        plan = state["current_plan"]
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertEqual(state["plan_tags"], ["plan:in-planning"])
        self.assertEqual(set(plan["principal_view"]["content"]), {
            "outcome", "users", "scope", "authority", "risks", "exceptions",
            "proof", "activation",
        })
        self.assertEqual(set(plan["technical_view"]["content"]), {
            "artifacts", "architecture", "dependencies", "implementation_sequence",
            "tests", "evidence", "versioning", "recovery",
        })
        self.assertEqual(plan["principal_view"]["plan_ref"], {
            field: plan[field] for field in ("plan_id", "version", "digest")
        })
        planning._validate_plan(plan)

    def test_plan_reaches_exact_human_checkpoint_without_target_mutation(self):
        before = (self.target / "report.py").read_text(encoding="utf-8")
        state = self.propose()
        run = self.runtime.load_run(state["run_id"])
        self.assertEqual(run["current_node_id"], "plan-approval")
        self.assertEqual(run["state"], "running")
        self.assertEqual((self.target / "report.py").read_text(encoding="utf-8"), before)
        self.assertEqual(run["contracts"]["artifact_scope"]["external_effect_selectors"], [])
        self.assertIn("mutate", run["contracts"]["authority"]["reserved_actions"])

    def test_plan_is_not_exported_before_exact_approval(self):
        self.propose()
        self.assertEqual(list(self.vault.rglob("Plan Execution Contract*.md")), [])

    def test_approval_binds_exact_version_baseline_and_exports_to_vault(self):
        state = self.approve(self.propose())
        self.assertEqual(state["status"], "approved")
        self.assertEqual(state["plan_tags"], ["plan:approved"])
        self.assertEqual(state["current_node_id"], "post-plan-mode")
        path = Path(state["export"]["path"])
        text = path.read_text(encoding="utf-8")
        self.assertIn(f"# {path.stem}\n", text)
        self.assertIn('  - "plan:approved"', text)
        self.assertIn(state["current_plan"]["digest"], text)
        self.assertIn("## Principal View", text)
        self.assertIn("## Technical View", text)
        self.assertIn("## Canonical Machine-Readable Contract", text)

    def test_wrong_plan_version_or_digest_cannot_be_approved(self):
        state = self.propose()
        plan = state["current_plan"]
        with self.assertRaises(planning.ProcessPlanConflict):
            self.service.approve(
                "dialogue-plan",
                decision="approve_without_start",
                plan_ref={
                    "plan_id": plan["plan_id"], "version": "99.0", "digest": plan["digest"],
                },
                baseline_digest=plan["repository_artifact_scope"]["target"]["identity"]["digest"],
                decision_by="principal:user",
                idempotency_key="approval:wrong-version",
            )

    def test_wrong_baseline_cannot_be_approved(self):
        state = self.propose()
        plan = state["current_plan"]
        with self.assertRaises(planning.ProcessPlanConflict):
            self.service.approve(
                "dialogue-plan",
                decision="approve_without_start",
                plan_ref={field: plan[field] for field in ("plan_id", "version", "digest")},
                baseline_digest="sha256:" + "0" * 64,
                decision_by="principal:user",
                idempotency_key="approval:wrong-baseline",
            )

    def test_target_drift_invalidates_approval_and_exports_nothing(self):
        state = self.propose()
        (self.target / "report.py").write_text("TOTAL = 2\n", encoding="utf-8")
        stale = self.approve(state)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["current_node_id"], "plan-approval")
        self.assertIsNone(stale["approval"])
        self.assertEqual(list(self.vault.rglob("Plan Execution Contract*.md")), [])

    def test_non_git_empty_directory_drift_is_content_bound(self):
        state = self.propose()
        (self.target / "new-empty-scope").mkdir()
        stale = self.approve(state)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["stale_records"][-1]["stale_kind"], "target")

    def test_nonprincipal_cannot_approve(self):
        state = self.propose()
        plan = state["current_plan"]
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.service.approve(
                "dialogue-plan",
                decision="approve_and_start",
                plan_ref={field: plan[field] for field in ("plan_id", "version", "digest")},
                baseline_digest=plan["repository_artifact_scope"]["target"]["identity"]["digest"],
                decision_by="principal:attacker",
                idempotency_key="approval:attacker",
            )

    def test_projection_fork_is_detected_even_with_recomputed_observation_digest(self):
        state = self.propose()
        path = self.runtime._events_path(state["run_id"])
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        proposal = next(
            record for record in records
            if (((record.get("event") or {}).get("details") or {}).get("observation_type"))
            == "programming_plan_proposed"
        )
        details = proposal["event"]["details"]
        details["payload"]["plan"]["principal_view"]["content"]["outcome"] = "Substituted"
        details["payload_digest"] = interview._digest_json(details["payload"])
        path.write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(planning.ProcessPlanIntegrityError):
            self.service.get_state("dialogue-plan")

    def test_duplicate_proposal_is_idempotent_across_service_restart(self):
        first = self.propose()
        restarted = planning.ProcessPlanApprovalService(
            runtime=runtime.GovernedProcessRuntime(self.root / "runs", now=lambda: NOW),
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )
        retry = restarted.propose(
            "dialogue-plan", basis(self.target),
            planner_id="planner:programming", idempotency_key="proposal:1",
        )
        self.assertEqual(retry, first)
        self.assertEqual(len(retry["plan_versions"]), 1)

    def test_proposal_idempotency_key_cannot_be_reused_for_different_content(self):
        self.propose(key="proposal:conflict")
        changed = basis(self.target)
        changed["tests"].append("Run an additional exact audit check.")
        with self.assertRaises(planning.ProcessPlanConflict):
            self.propose(key="proposal:conflict", value=changed)

    def test_approval_retry_finishes_after_export_interruption(self):
        state = self.propose()
        real_write = planning._runtime_paths.atomic_write_text
        with mock.patch.object(
            planning._runtime_paths,
            "atomic_write_text",
            side_effect=[OSError("injected export interruption")],
        ):
            with self.assertRaises(OSError):
                self.approve(state, key="approval:retry")
        partial = self.service.get_state("dialogue-plan")
        self.assertEqual(partial["status"], "approval_pending_commit")
        with mock.patch.object(
            planning._runtime_paths,
            "atomic_write_text",
            side_effect=lambda path, text: real_write(path, text),
        ):
            completed = self.approve(state, key="approval:retry")
        self.assertEqual(completed["status"], "approved")
        approvals = [
            record for record in self.runtime.load_records(state["run_id"])
            if (((record.get("event") or {}).get("details") or {}).get("observation_type"))
            == "programming_plan_approval_decided"
        ]
        self.assertEqual(len(approvals), 1)

    def test_target_drift_after_approval_persistence_forces_a_new_version(self):
        first = self.propose()
        with mock.patch.object(
            planning._runtime_paths,
            "atomic_write_text",
            side_effect=OSError("injected export interruption"),
        ):
            with self.assertRaises(OSError):
                self.approve(first, key="approval:stale-recovery")
        (self.target / "report.py").write_text("TOTAL = 3\n", encoding="utf-8")
        stale = self.approve(first, key="approval:stale-recovery")
        self.assertEqual(stale["status"], "stale")
        revised = self.propose(key="proposal:after-stale")
        self.assertEqual(revised["current_plan"]["version"], "2.0")
        approved = self.approve(revised, key="approval:version-2")
        self.assertEqual(approved["status"], "approved")

    def test_stale_recovery_can_demote_a_precheckpoint_approved_contract(self):
        first = self.propose()
        with mock.patch.object(
            self.runtime,
            "resolve_human_checkpoint",
            side_effect=OSError("injected post-contract interruption"),
        ):
            with self.assertRaises(OSError):
                self.approve(first, key="approval:post-contract")
        partial_run = self.runtime.load_run(first["run_id"])
        self.assertIn("plan:approved", partial_run["labels"])
        self.assertEqual(partial_run["current_node_id"], "plan-approval")
        (self.target / "report.py").write_text("TOTAL = 4\n", encoding="utf-8")
        stale = self.approve(first, key="approval:post-contract")
        self.assertEqual(stale["status"], "stale")
        revised = self.propose(key="proposal:post-contract-recovery")
        self.assertEqual(revised["current_plan"]["version"], "2.0")
        self.assertNotIn(
            "plan:approved", self.runtime.load_run(first["run_id"])["labels"]
        )

    def test_request_changes_creates_new_immutable_version(self):
        first = self.propose()
        old = copy.deepcopy(first["current_plan"])
        requested = self.service.request_revision(
            "dialogue-plan",
            action="request_changes",
            plan_ref={field: old[field] for field in ("plan_id", "version", "digest")},
            reason="Add an explicit audit-log verification step.",
            idempotency_key="revision:1",
        )
        self.assertEqual(requested["status"], "revision_requested")
        revised_basis = basis(self.target)
        revised_basis["tests"].append("Verify the audit log is complete.")
        revised = self.propose(key="proposal:2", value=revised_basis)
        self.assertEqual(revised["current_plan"]["version"], "2.0")
        self.assertEqual(revised["plan_versions"][0], {
            field: old[field] for field in ("plan_id", "version", "digest")
        })
        self.assertNotEqual(revised["current_plan"]["digest"], old["digest"])

    def test_only_latest_revised_version_can_be_approved(self):
        first = self.propose()
        old_ref = {field: first["current_plan"][field] for field in ("plan_id", "version", "digest")}
        self.service.request_revision(
            "dialogue-plan", action="change_scope_or_permissions",
            plan_ref=old_ref, reason="Narrow writes to report.py only.",
            idempotency_key="scope:1",
        )
        revised_basis = basis(self.target)
        revised_basis["scope"] = ["report.py"]
        revised = self.propose(key="proposal:2", value=revised_basis)
        with self.assertRaises(planning.ProcessPlanConflict):
            self.service.approve(
                "dialogue-plan", decision="approve_without_start",
                plan_ref=old_ref,
                baseline_digest=first["current_plan"]["repository_artifact_scope"]["target"]["identity"]["digest"],
                decision_by="principal:user", idempotency_key="approval:old",
            )
        self.assertEqual(self.approve(revised)["status"], "approved")

    def test_stop_and_retain_blocks_run_without_export(self):
        state = self.propose()
        plan = state["current_plan"]
        retained = self.service.stop_and_retain(
            "dialogue-plan",
            plan_ref={field: plan[field] for field in ("plan_id", "version", "digest")},
            decision_by="principal:user",
            reason="Retain this plan for later consideration.",
            idempotency_key="retain:1",
        )
        self.assertEqual(retained["status"], "retained")
        self.assertEqual(self.runtime.load_run(state["run_id"])["state"], "blocked")
        self.assertEqual(list(self.vault.rglob("Plan Execution Contract*.md")), [])

    def test_revision_delivery_retry_cannot_create_an_extra_decision(self):
        state = self.propose()
        plan_ref = {
            field: state["current_plan"][field]
            for field in ("plan_id", "version", "digest")
        }
        first = self.service.request_revision(
            "dialogue-plan", action="request_changes", plan_ref=plan_ref,
            reason="Add exact export authentication.", idempotency_key="revision:retry",
        )
        retry = self.service.request_revision(
            "dialogue-plan", action="request_changes", plan_ref=plan_ref,
            reason="Add exact export authentication.", idempotency_key="revision:retry",
        )
        self.assertEqual(retry, first)
        self.assertEqual(len(retry["revision_requests"]), 1)
        with self.assertRaises(planning.ProcessPlanConflict):
            self.service.request_revision(
                "dialogue-plan", action="change_scope_or_permissions",
                plan_ref=plan_ref, reason="Add exact export authentication.",
                idempotency_key="revision:retry",
            )

    def test_retention_retry_finishes_after_decision_persistence(self):
        state = self.propose()
        plan_ref = {
            field: state["current_plan"][field]
            for field in ("plan_id", "version", "digest")
        }
        real_resolve = self.runtime.resolve_human_checkpoint
        with mock.patch.object(
            self.runtime,
            "resolve_human_checkpoint",
            side_effect=OSError("injected checkpoint interruption"),
        ):
            with self.assertRaises(OSError):
                self.service.stop_and_retain(
                    "dialogue-plan", plan_ref=plan_ref,
                    decision_by="principal:user", reason="Retain the reviewed plan.",
                    idempotency_key="retain:retry",
                )
        with mock.patch.object(
            self.runtime, "resolve_human_checkpoint", side_effect=real_resolve,
        ):
            retained = self.service.stop_and_retain(
                "dialogue-plan", plan_ref=plan_ref,
                decision_by="principal:user", reason="Retain the reviewed plan.",
                idempotency_key="retain:retry",
            )
        self.assertEqual(retained["status"], "retained")
        self.assertEqual(self.runtime.load_run(state["run_id"])["state"], "blocked")

    def test_approved_runtime_contract_withholds_all_artifact_writes(self):
        approved = self.approve(self.propose())
        run = self.runtime.load_run(approved["run_id"])
        self.assertEqual(run["contracts"]["artifact_scope"]["write_selectors"], [])
        before = self.runtime.load_artifact(approved["run_id"], "art-plan-v1-0")
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.runtime.record_inline_artifact(
                approved["run_id"], "art-plan-v1-0", "substituted plan",
                role="working", node_id="plan", action="produce_programming_plan",
                selector="scope:plan_outputs",
                satisfied_conditions=["exact_plan_identity", "no_target_mutation"],
            )
        after = self.runtime.load_artifact(approved["run_id"], "art-plan-v1-0")
        self.assertEqual(after, before)

    def test_export_tampering_is_rejected_during_hydration(self):
        approved = self.approve(self.propose())
        Path(approved["export"]["path"]).write_text("substituted\n", encoding="utf-8")
        with self.assertRaises(planning.ProcessPlanIntegrityError):
            self.service.get_state("dialogue-plan")

    def test_planning_lifecycle_real_write_reload_and_restart(self):
        memory.set_conversation_tag(
            "dialogue-plan", "private", sessions_root=self.root / "sessions"
        )
        state = self.propose()
        envelope = memory.load_conversation_json(
            "dialogue-plan", sessions_root=self.root / "sessions"
        )
        self.assertEqual(envelope["tag"], "private")
        self.assertEqual(
            envelope["process_plan_lifecycle"], state["dialogue_lifecycle"]
        )
        self.assertEqual(
            state["dialogue_lifecycle"]["lifecycle"], "plan:in-planning"
        )
        restarted = planning.ProcessPlanApprovalService(
            runtime=runtime.GovernedProcessRuntime(
                self.root / "runs", now=lambda: NOW
            ),
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )
        hydrated = restarted.get_state("dialogue-plan")
        self.assertEqual(hydrated["dialogue_lifecycle"], state["dialogue_lifecycle"])
        self.assertEqual(
            memory.get_conversation_tag(
                "dialogue-plan", sessions_root=self.root / "sessions"
            ),
            "private",
        )

    def test_approved_lifecycle_real_write_reload_and_restart(self):
        approved = self.approve(self.propose())
        envelope = memory.load_conversation_json(
            "dialogue-plan", sessions_root=self.root / "sessions"
        )
        lifecycle = envelope["process_plan_lifecycle"]
        self.assertEqual(lifecycle["lifecycle"], "plan:approved")
        self.assertEqual(lifecycle["plan_ref"], {
            field: approved["current_plan"][field]
            for field in ("plan_id", "version", "digest")
        })
        self.assertEqual(lifecycle["approval_receipt"], approved["approval"])
        restarted = planning.ProcessPlanApprovalService(
            runtime=runtime.GovernedProcessRuntime(
                self.root / "runs", now=lambda: NOW
            ),
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )
        self.assertEqual(
            restarted.get_state("dialogue-plan")["dialogue_lifecycle"], lifecycle
        )
        self.assertEqual(envelope["tag"], "")

    def test_recomputed_envelope_lifecycle_tampering_is_rejected(self):
        self.propose()
        envelope_path = (
            self.root / "sessions" / "dialogue-plan" / "conversation.json"
        )
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        lifecycle = envelope["process_plan_lifecycle"]
        lifecycle["plan_ref"]["digest"] = "sha256:" + "0" * 64
        lifecycle_body = {
            key: value for key, value in lifecycle.items()
            if key != "lifecycle_digest"
        }
        lifecycle["lifecycle_digest"] = memory._digest_json(lifecycle_body)
        envelope_path.write_text(
            json.dumps(envelope, indent=2), encoding="utf-8"
        )
        restarted = planning.ProcessPlanApprovalService(
            runtime=runtime.GovernedProcessRuntime(
                self.root / "runs", now=lambda: NOW
            ),
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )
        with self.assertRaises(planning.ProcessPlanIntegrityError):
            restarted.get_state("dialogue-plan")

    def test_recomputed_approval_receipt_tampering_is_rejected(self):
        self.approve(self.propose())
        envelope_path = (
            self.root / "sessions" / "dialogue-plan" / "conversation.json"
        )
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        lifecycle = envelope["process_plan_lifecycle"]
        lifecycle["approval_receipt"]["decision_by"] = "substituted-principal"
        lifecycle["approval_receipt_digest"] = memory._digest_json(
            lifecycle["approval_receipt"]
        )
        lifecycle_body = {
            key: value for key, value in lifecycle.items()
            if key != "lifecycle_digest"
        }
        lifecycle["lifecycle_digest"] = memory._digest_json(lifecycle_body)
        envelope_path.write_text(
            json.dumps(envelope, indent=2), encoding="utf-8"
        )
        restarted = planning.ProcessPlanApprovalService(
            runtime=runtime.GovernedProcessRuntime(
                self.root / "runs", now=lambda: NOW
            ),
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )
        with self.assertRaises(planning.ProcessPlanIntegrityError):
            restarted.get_state("dialogue-plan")

    def test_receipted_lifecycle_removal_is_rejected_after_restart(self):
        self.propose()
        envelope_path = (
            self.root / "sessions" / "dialogue-plan" / "conversation.json"
        )
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope.pop("process_plan_lifecycle")
        envelope_path.write_text(
            json.dumps(envelope, indent=2), encoding="utf-8"
        )
        restarted = planning.ProcessPlanApprovalService(
            runtime=runtime.GovernedProcessRuntime(
                self.root / "runs", now=lambda: NOW
            ),
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )
        with self.assertRaises(planning.ProcessPlanIntegrityError):
            restarted.get_state("dialogue-plan")

    def test_rejected_export_resolver_creates_nothing_outside_vault(self):
        state = self.propose()
        outside = self.root / "outside-created-by-invalid-resolver"
        service = planning.ProcessPlanApprovalService(
            runtime=self.runtime,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: outside,
            now=lambda: NOW,
        )
        with self.assertRaises(planning.ProcessPlanIntegrityError):
            service.approve(
                "dialogue-plan", decision="approve_without_start",
                plan_ref={
                    field: state["current_plan"][field]
                    for field in ("plan_id", "version", "digest")
                },
                baseline_digest=state["current_plan"]["repository_artifact_scope"]
                ["target"]["identity"]["digest"],
                decision_by="principal:user", idempotency_key="approval:outside",
            )
        self.assertFalse(outside.exists())

    def test_implementation_dependencies_must_precede_their_consumers(self):
        invalid = basis(self.target)
        invalid["implementation_sequence"][0]["depends_on"] = ["step-test"]
        with self.assertRaises(planning.ProcessPlanInputRequired):
            self.propose(value=invalid)

    def test_instruction_identity_must_match_a_real_source(self):
        wrong = basis(self.target)
        wrong["instructions"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(planning.ProcessPlanInputRequired):
            self.propose(value=wrong)
        missing = basis(self.target)
        missing["instructions"][0]["source"] = "MISSING.md"
        with self.assertRaises(planning.ProcessPlanInputRequired):
            self.propose(key="proposal:missing-instruction", value=missing)

    def test_external_instruction_drift_withholds_approval(self):
        policy = self.root / "external-policy.md"
        policy.write_text("version one", encoding="utf-8")
        value = basis(self.target)
        value["instructions"] = [{
            "source": str(policy),
            "digest": "sha256:" + hashlib.sha256(b"version one").hexdigest(),
            "precedence": "governing",
            "scope": "the exact plan",
        }]
        state = self.propose(value=value)
        policy.write_text("version two", encoding="utf-8")
        stale = self.approve(state)
        self.assertEqual(stale["status"], "stale")
        self.assertIsNone(stale["approval"])
        self.assertEqual(stale["stale_records"][-1]["stale_kind"], "instructions")

    def test_approved_plan_cannot_enter_phase_2_4_execution_node(self):
        approved = self.approve(self.propose(), decision="approve_and_start")
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.runtime.advance_decision(
                approved["run_id"], "prg_run", reason="attempt Phase 2.4 bypass"
            )
        self.assertEqual(
            self.runtime.load_run(approved["run_id"])["current_node_id"],
            "post-plan-mode",
        )

    def test_generic_event_api_cannot_forge_contract_replacement(self):
        state = self.propose()
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.runtime.record_event(
                state["run_id"], "run_contracts_replaced", {"contracts": {}},
            )

    def test_missing_plan_fields_fail_before_scope_or_graph_change(self):
        invalid = basis(self.target)
        invalid.pop("recovery")
        before = self.runtime.load_run(self.interview_state["run_id"])
        with self.assertRaises(planning.ProcessPlanInputRequired):
            self.propose(value=invalid)
        after = self.runtime.load_run(self.interview_state["run_id"])
        self.assertEqual(after["current_node_id"], before["current_node_id"])
        self.assertEqual(after["contracts"], before["contracts"])

    def test_activation_request_never_removes_separate_approval_boundary(self):
        requested = basis(self.target)
        requested["activation"]["requested"] = True
        state = self.propose(value=requested)
        self.assertTrue(state["current_plan"]["activation"]["requested"])
        self.assertTrue(
            state["current_plan"]["activation"]["separate_approval_required"]
        )
        self.assertIn(
            "activate",
            self.runtime.load_run(state["run_id"])["contracts"]["authority"]["reserved_actions"],
        )


class Phase23ServerTests(Phase23Fixture):
    def setUp(self):
        super().setUp()
        server.app.config["TESTING"] = True
        self.client = server.app.test_client()
        self.binding_root = mock.patch.object(
            memory, "_DEFAULT_SESSIONS_ROOT", self.root / "sessions"
        )
        self.binding_root.start()
        self.addCleanup(self.binding_root.stop)
        self.interview_factory = mock.patch.object(
            server, "_management_interview_service", return_value=self.interview
        )
        self.interview_factory.start()
        self.addCleanup(self.interview_factory.stop)
        self.plan_factory = mock.patch.object(
            server, "_process_plan_service", return_value=self.service
        )
        self.plan_factory.start()
        self.addCleanup(self.plan_factory.stop)

    def post(self, message, **extra):
        payload = {"message": message, "conversation_id": "dialogue-plan"}
        payload.update(extra)
        return self.client.post("/chat", json=payload)

    def test_plan_hydration_endpoint_returns_both_views(self):
        state = self.propose()
        response = self.client.get("/api/process-plan/dialogue-plan")
        self.assertEqual(response.status_code, 200)
        hydrated = response.get_json()["plan"]
        self.assertEqual(hydrated["current_plan"]["digest"], state["current_plan"]["digest"])
        self.assertIn("principal_view", hydrated["current_plan"])
        self.assertIn("technical_view", hydrated["current_plan"])

    def test_plan_api_returns_typed_authority_denial(self):
        state = self.propose()
        plan = state["current_plan"]
        response = self.client.post("/api/process-plan/dialogue-plan", json={
            "action": "approve_without_start",
            "plan_ref": {
                field: plan[field] for field in ("plan_id", "version", "digest")
            },
            "baseline_digest": plan["repository_artifact_scope"]["target"]
            ["identity"]["digest"],
            "decision_by": "principal:attacker",
            "idempotency_key": "approval:api-attacker",
        })
        self.assertEqual(response.status_code, 403)

    def test_dialogue_turn_preserves_privacy_and_real_lifecycle(self):
        self.assertEqual(memory.CONVERSATION_TAGS, ("", "stealth", "private"))
        self.assertNotIn("plan:in-planning", memory.CONVERSATION_TAGS)
        self.assertNotIn("plan:approved", memory.CONVERSATION_TAGS)
        memory.set_conversation_tag(
            "dialogue-plan", "private", sessions_root=self.root / "sessions"
        )
        state = self.propose()
        with mock.patch.object(
            server, "_save_conversation", return_value="chunk-tagged",
        ) as save, mock.patch.object(
            server, "_finalize_pending_submission",
        ):
            response = server._persist_process_plan_exchange(
                user_input="Prepare the plan.", state=state, history=[],
                panel_id="dialogue-plan", tag="", submission_id="submission:tag",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(save.call_args.args[4], "")
        envelope = memory.load_conversation_json(
            "dialogue-plan", sessions_root=self.root / "sessions"
        )
        self.assertEqual(envelope["tag"], "private")
        self.assertEqual(
            envelope["process_plan_lifecycle"], state["dialogue_lifecycle"]
        )
        self.assertEqual(envelope["messages"][-1]["role"], "assistant")

    def test_chat_proposal_stops_at_approval_and_saves_plan_card(self):
        saved = server._json_response({"status": "ok", "chunk_id": "chunk-plan"})
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-plan",
        ), mock.patch.object(
            server, "_persist_process_plan_exchange", return_value=saved,
        ) as persist:
            response = self.post(
                "Prepare the exact plan.",
                management_plan={
                    "action": "propose",
                    "planning_basis": basis(self.target),
                    "planner_id": "planner:programming",
                    "idempotency_key": "chat-proposal:1",
                },
            )
        self.assertEqual(response.status_code, 200)
        state = self.service.get_state("dialogue-plan")
        self.assertEqual(state["status"], "awaiting_approval")
        persist.assert_called_once()

    def test_chat_proposal_retry_after_dialogue_save_failure_is_idempotent(self):
        payload = {
            "action": "propose",
            "planning_basis": basis(self.target),
            "planner_id": "planner:programming",
            "idempotency_key": "chat-proposal:retry-save",
        }
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-plan-fail",
        ), mock.patch.object(
            server, "_save_conversation", side_effect=OSError("injected save failure"),
        ):
            failed = self.post("Prepare the exact plan.", management_plan=payload)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(
            self.service.get_state("dialogue-plan")["status"], "awaiting_approval"
        )
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-plan-retry",
        ), mock.patch.object(
            server, "_save_conversation", return_value="chunk-plan-retry",
        ), mock.patch(
            "conversation_memory.save_turn_spatial_state",
        ):
            retried = self.post("Prepare the exact plan.", management_plan=payload)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(
            len(self.service.get_state("dialogue-plan")["plan_versions"]), 1
        )

    def test_chat_approval_exports_but_does_not_enter_phase_2_4(self):
        state = self.propose()
        plan = state["current_plan"]
        saved = server._json_response({"status": "ok", "chunk_id": "chunk-approval"})
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-approval",
        ), mock.patch.object(
            server, "_persist_process_plan_exchange", return_value=saved,
        ):
            response = self.post(
                "Approve but do not start.",
                management_plan={
                    "action": "approve_without_start",
                    "plan_ref": {
                        field: plan[field] for field in ("plan_id", "version", "digest")
                    },
                    "baseline_digest": plan["repository_artifact_scope"]["target"]["identity"]["digest"],
                    "decision_by": "principal:user",
                    "idempotency_key": "chat-approval:1",
                },
            )
        self.assertEqual(response.status_code, 200)
        approved = self.service.get_state("dialogue-plan")
        self.assertEqual(approved["next_action"], "await_phase_2_4_delegation")
        followup = self.post("Continue.")
        self.assertEqual(followup.status_code, 409)
        self.assertEqual(followup.get_json()["error"], "awaiting_phase_2_4_delegation")

    def test_chat_rejects_plan_submission_before_interview_completion(self):
        # Use a separate incomplete Dialogue bound to the same service roots.
        state = self.interview.start_or_resume("dialogue-incomplete", route())
        self.assertEqual(state["status"], "interviewing")
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-early-plan",
        ):
            response = self.client.post("/chat", json={
                "message": "Plan now.",
                "conversation_id": "dialogue-incomplete",
                "management_plan": {
                    "action": "propose",
                    "planning_basis": basis(self.target),
                    "planner_id": "planner:programming",
                    "idempotency_key": "early:1",
                },
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "management_interview_incomplete")


if __name__ == "__main__":
    unittest.main()
