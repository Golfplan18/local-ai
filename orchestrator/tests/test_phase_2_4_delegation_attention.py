"""G1.1 Phase 2.4 — exact delegation and attention-surface proofs."""

from __future__ import annotations

import copy
import json
import os
import sys
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

import governed_process_runtime as runtime  # noqa: E402
import conversation_memory as memory  # noqa: E402
import process_definition_registry as registry_module  # noqa: E402
import process_delegation_attention as delegation  # noqa: E402
import process_plan_approval as planning  # noqa: E402
from server import server  # noqa: E402
from tests import test_phase_2_3_plan_approval as phase23  # noqa: E402
from tests import test_governed_process_runtime as runtime_fixtures  # noqa: E402


NOW = phase23.NOW


def seal_definition(definition):
    sealed = copy.deepcopy(definition)
    placeholder = "sha256:" + "0" * 64
    manifest = sealed["package_manifest"]
    sealed["digest"] = placeholder
    manifest["definition_ref"] = {
        "definition_id": sealed["definition_id"],
        "version": sealed["version"],
        "digest": placeholder,
    }
    entry = next(
        member for member in manifest["members"]
        if member["member_id"] == manifest["entry_member_id"]
    )
    entry["identity"]["digest"] = placeholder
    digest = registry_module.process_definition_content_digest(sealed)
    sealed["digest"] = digest
    manifest["definition_ref"]["digest"] = digest
    entry["identity"]["digest"] = digest
    return sealed


class Phase24Fixture(phase23.Phase23Fixture):
    def setUp(self):
        super().setUp()
        self.registry = registry_module.ProcessDefinitionRegistry(
            self.root / "definitions", now=lambda: NOW
        )
        self.delegation = delegation.ProcessDelegationAttentionService(
            runtime=self.runtime,
            plan_service=self.service,
            registry=self.registry,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            now=lambda: NOW,
        )

    def approved(self, *, decision="approve_without_start"):
        return self.approve(self.propose(), decision=decision)

    def delegate(self, state, *, key="delegation:1"):
        plan = state["current_plan"]
        return self.delegation.delegate(
            "dialogue-plan",
            plan_ref={
                field: plan[field] for field in ("plan_id", "version", "digest")
            },
            approval_receipt_digest=state["dialogue_lifecycle"][
                "approval_receipt_digest"
            ],
            requested_by="principal:user",
            idempotency_key=key,
        )

    def restarted(self):
        restarted_runtime = runtime.GovernedProcessRuntime(
            self.root / "runs", now=lambda: NOW
        )
        restarted_plan = planning.ProcessPlanApprovalService(
            runtime=restarted_runtime,
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            vault_root=self.vault,
            project_folder_resolver=lambda _project: "Projects/Ora",
            now=lambda: NOW,
        )
        return delegation.ProcessDelegationAttentionService(
            runtime=restarted_runtime,
            plan_service=restarted_plan,
            registry=registry_module.ProcessDefinitionRegistry(
                self.root / "definitions", now=lambda: NOW
            ),
            sessions_root=self.root / "sessions",
            repository_root=ROOT,
            now=lambda: NOW,
        )


class Phase24DelegationTests(Phase24Fixture):
    @staticmethod
    def _grant_conditions(run, action):
        return next(
            grant["conditions"]
            for grant in run["contracts"]["authority"]["grants"]
            if action in grant["actions"]
        )

    def _enter_external_execute_step(self, state, *, checkpoint=True):
        self.delegate(state)
        run_id = state["run_id"]
        run = self.runtime.load_run(run_id)
        preflight_conditions = self._grant_conditions(run, "programming_preflight")
        preflight = self.runtime.record_inline_artifact(
            run_id,
            "preflight-evidence",
            "exact approved baseline and authority are current",
            role="evidence",
            node_id="execute-preflight",
            action="programming_preflight",
            selector="scope:declared_outputs",
            satisfied_conditions=preflight_conditions,
        )
        self.runtime.complete_action_node(
            run_id,
            "programming_preflight",
            reason="preflight identities and authority are current",
            artifact_ids=[preflight["artifact"]["artifact_id"]],
        )
        run = self.runtime.load_run(run_id)
        self.assertEqual(run["current_node_id"], "execute-step")
        pre_state = self.delegation.capture_repository_state(
            "dialogue-plan",
            artifact_id="repository-pre-state",
            phase="pre_action",
        )
        if checkpoint:
            self.runtime.create_checkpoint(
                run_id,
                "before-approved-report-mutation",
                segment_id="approved-report-mutation",
                resume_node_id="execute-step",
            )
        return pre_state

    def _post_state(self, state):
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        self.runtime.authorize_action(
            state["run_id"],
            "execute_approved_programming_step",
            ["artifact:report.py"],
            satisfied_conditions=conditions,
            effect_type="local_reversible",
            scope_kind="external",
        )
        report = self.target / "report.py"
        report.write_text(
            report.read_text(encoding="utf-8") + "# approved mutation\n",
            encoding="utf-8",
        )
        return self.delegation.capture_repository_state(
            "dialogue-plan",
            artifact_id="repository-post-state",
            phase="post_action",
        )

    def _post_state_and_receipt(self, state, pre_state):
        post_state = self._post_state(state)
        receipt = self.delegation.issue_repository_mutation_receipt(
            "dialogue-plan",
            artifact_id="repository-mutation-receipt",
            pre_state_artifact_id=pre_state["artifact"]["artifact_id"],
            post_state_artifact_id=post_state["artifact"]["artifact_id"],
        )
        return post_state, receipt

    @staticmethod
    def _mutation_details(
        pre_state, post_state,
        operation="execute_approved_programming_step",
    ):
        return {
            "operation": operation,
            "pre_state_identity": {
                "artifact_id": pre_state["artifact"]["artifact_id"],
                "identity_digest": pre_state["artifact"]["identity"]["digest"],
            },
            "post_state_identity": {
                "artifact_id": post_state["artifact"]["artifact_id"],
                "identity_digest": post_state["artifact"]["identity"]["digest"],
            },
        }

    def test_approval_without_start_preserves_phase_2_3_read_only_boundary(self):
        state = self.approved()
        run = self.runtime.load_run(state["run_id"])
        self.assertEqual(run["current_node_id"], "post-plan-mode")
        self.assertNotIn("delegated", run["labels"])
        self.assertFalse(state["phase_2_4_authorized"])
        self.assertFalse(state["target_mutation_authorized"])
        self.assertIsNone(self.delegation.get_delegation("dialogue-plan")["observation"])

    def test_exact_delegation_persists_authority_checkpoint_and_preflight_only(self):
        state = self.approved()
        delegated = self.delegate(state)
        run = self.runtime.load_run(state["run_id"])
        records = self.runtime.load_records(state["run_id"])

        self.assertEqual(delegated["status"], "delegated")
        self.assertEqual(run["current_node_id"], "execute-preflight")
        self.assertEqual(run["state"], "running")
        self.assertIn("phase-2.4", run["labels"])
        self.assertIn("delegated", run["labels"])
        self.assertEqual(
            {field: run["contracts"]["approved_plan"][field]
             for field in ("plan_id", "version", "digest")},
            delegated["plan_ref"],
        )
        self.assertTrue({
            "activate", "construct_definition", "expand_scope", "publish",
            "register_definition", "remote_git", "send_external",
        }.issubset(set(run["contracts"]["authority"]["reserved_actions"])))
        self.assertEqual(
            run["contracts"]["artifact_scope"]["external_effect_selectors"],
            ["artifact:report.py", "artifact:tests/test_report.py"],
        )
        self.assertFalse(
            set(run["contracts"]["artifact_scope"]["external_effect_selectors"])
            & set(run["contracts"]["artifact_scope"]["write_selectors"])
        )
        event_types = [
            (record.get("event") or {}).get("event_type") for record in records
        ]
        activation_index = event_types.index("delegation_activated")
        checkpoint_index = event_types.index("checkpoint_created", activation_index)
        transition_index = next(
            index for index, record in enumerate(records)
            if (record.get("event") or {}).get("event_type") == "node_advanced"
            and ((record.get("event") or {}).get("details") or {}).get(
                "from_node_id"
            ) == "post-plan-mode"
        )
        self.assertLess(activation_index, checkpoint_index)
        self.assertLess(checkpoint_index, transition_index)
        self.assertFalse(any(
            event_type in {"action_recorded", "attempt_started", "attempt_completed"}
            for event_type in event_types[activation_index:]
        ))

        plan_state = self.service.get_state("dialogue-plan")
        self.assertEqual(plan_state["status"], "approved")
        self.assertTrue(plan_state["phase_2_4_authorized"])
        self.assertFalse(plan_state["target_mutation_authorized"])
        self.assertEqual(plan_state["next_action"], "delegated_execution_active")

    def test_mutation_authority_is_denied_at_execute_preflight(self):
        state = self.approved()
        self.delegate(state)
        run = self.runtime.load_run(state["run_id"])
        self.assertEqual(run["current_node_id"], "execute-preflight")
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        before = self.runtime.load_records(state["run_id"])
        with self.assertRaisesRegex(
            runtime.AuthorityDeniedError, "only at its exact current",
        ):
            self.runtime.authorize_action(
                state["run_id"],
                "execute_approved_programming_step",
                ["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                scope_kind="external",
            )
        with self.assertRaisesRegex(
            runtime.AuthorityDeniedError, "cannot fall through",
        ):
            self.runtime.record_action(
                state["run_id"],
                action="execute_approved_programming_step",
                selectors=["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                external_effect=True,
                details={"operation": "execute_approved_programming_step"},
            )
        self.assertEqual(self.runtime.load_records(state["run_id"]), before)

    def test_mutation_authority_is_denied_before_node_local_checkpoint(self):
        state = self.approved()
        self._enter_external_execute_step(state, checkpoint=False)
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        self.assertFalse(
            self.service.get_state("dialogue-plan")["target_mutation_authorized"]
        )
        before = self.runtime.load_records(state["run_id"])
        with self.assertRaisesRegex(
            runtime.AuthorityDeniedError, "node-local checkpoint",
        ):
            self.runtime.authorize_action(
                state["run_id"],
                "execute_approved_programming_step",
                ["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                scope_kind="external",
            )
        with self.assertRaisesRegex(
            runtime.AuthorityDeniedError, "node-local checkpoint",
        ):
            self.runtime.record_action(
                state["run_id"],
                action="execute_approved_programming_step",
                selectors=["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                external_effect=True,
                details={"operation": "execute_approved_programming_step"},
            )
        self.assertEqual(self.runtime.load_records(state["run_id"]), before)

    def test_mutation_authority_cannot_be_issued_after_unapproved_effect(self):
        state = self.approved()
        self._enter_external_execute_step(state)
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        before = self.runtime.load_records(state["run_id"])
        (self.target / "report.py").write_text(
            "TOTAL = 99\n", encoding="utf-8"
        )
        self.assertFalse(
            self.service.get_state("dialogue-plan")["target_mutation_authorized"]
        )
        with self.assertRaisesRegex(
            runtime.AuthorityDeniedError, "changed after the checkpointed pre-state",
        ):
            self.runtime.authorize_action(
                state["run_id"],
                "execute_approved_programming_step",
                ["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                scope_kind="external",
            )
        self.assertEqual(self.runtime.load_records(state["run_id"]), before)

    def test_external_mutation_cannot_be_mislabelled_as_ordinary_write(self):
        state = self.approved()
        pre_state = self._enter_external_execute_step(state)
        post_state, _receipt = self._post_state_and_receipt(state, pre_state)
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        with self.assertRaisesRegex(
            runtime.AuthorityDeniedError, "classification is fixed",
        ):
            self.runtime.record_action(
                state["run_id"],
                action="execute_approved_programming_step",
                selectors=["scope:declared_outputs"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                external_effect=False,
                details=self._mutation_details(pre_state, post_state),
            )
        self.assertEqual(
            self.runtime.load_run(state["run_id"])["current_node_id"],
            "execute-step",
        )

    def test_external_mutation_cannot_be_recorded_without_issued_receipt(self):
        state = self.approved()
        pre_state = self._enter_external_execute_step(state)
        post_state = self._post_state(state)
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        with self.assertRaisesRegex(
            runtime.GovernedRuntimeError, "runtime-issued repository receipt",
        ):
            self.runtime.record_action(
                state["run_id"],
                action="execute_approved_programming_step",
                selectors=["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                external_effect=True,
                details=self._mutation_details(pre_state, post_state),
            )
        self.assertEqual(
            self.runtime.load_run(state["run_id"])["current_node_id"],
            "execute-step",
        )

    def test_out_of_scope_external_mutation_is_rejected(self):
        state = self.approved()
        self._enter_external_execute_step(state)
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        before_records = self.runtime.load_records(state["run_id"])
        before_content = (self.target / "report.py").read_text(encoding="utf-8")
        with self.assertRaisesRegex(runtime.AuthorityDeniedError, "outside external"):
            self.runtime.authorize_action(
                state["run_id"],
                "execute_approved_programming_step",
                ["artifact:not-approved.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                scope_kind="external",
            )
        self.assertEqual(self.runtime.load_records(state["run_id"]), before_records)
        self.assertEqual(
            (self.target / "report.py").read_text(encoding="utf-8"),
            before_content,
        )

    def test_fabricated_inline_repository_state_cannot_authorize_completion(self):
        state = self.approved()
        authenticated_pre = self._enter_external_execute_step(state)
        authenticated_post = self._post_state(state)
        self.delegation.issue_repository_mutation_receipt(
            "dialogue-plan",
            artifact_id="authenticated-receipt",
            pre_state_artifact_id=authenticated_pre["artifact"]["artifact_id"],
            post_state_artifact_id=authenticated_post["artifact"]["artifact_id"],
        )
        run = self.runtime.load_run(state["run_id"])
        receipt_conditions = self._grant_conditions(
            run, "record_programming_mutation_receipt"
        )
        fabricated_pre = self.runtime.record_inline_artifact(
            state["run_id"], "fabricated-pre", "not a repository capture",
            role="working", node_id="execute-step",
            action="record_programming_mutation_receipt",
            selector="scope:declared_outputs",
            satisfied_conditions=receipt_conditions,
        )
        fabricated_post = self.runtime.record_inline_artifact(
            state["run_id"], "fabricated-post", "also not a repository capture",
            role="working", node_id="execute-step",
            action="record_programming_mutation_receipt",
            selector="scope:declared_outputs",
            source_artifact_ids=[fabricated_pre["artifact"]["artifact_id"]],
            satisfied_conditions=receipt_conditions,
        )
        fabricated_receipt = self.runtime.record_inline_artifact(
            state["run_id"], "fabricated-receipt", "caller-made receipt",
            role="external_effect_receipt", node_id="execute-step",
            action="record_programming_mutation_receipt",
            selector="scope:declared_outputs",
            source_artifact_ids=[
                fabricated_pre["artifact"]["artifact_id"],
                fabricated_post["artifact"]["artifact_id"],
            ],
            satisfied_conditions=receipt_conditions,
            media_type="application/json",
        )
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        with self.assertRaisesRegex(
            runtime.GovernedRuntimeError, "does not bind the exact approved",
        ):
            self.runtime.record_action(
                state["run_id"],
                action="execute_approved_programming_step",
                selectors=["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                external_effect=True,
                receipt_artifact_id=fabricated_receipt["artifact"]["artifact_id"],
                details=self._mutation_details(
                    fabricated_pre, fabricated_post
                ),
            )
        self.assertEqual(
            authenticated_pre["artifact"]["locator"]["ref"],
            str(self.target.resolve()),
        )

    def test_exact_checkpointed_receipted_external_mutation_advances(self):
        state = self.approved()
        pre_state = self._enter_external_execute_step(state)
        ready = self.service.get_state("dialogue-plan")
        self.assertTrue(ready["target_mutation_authorized"])
        self.assertFalse(any(
            (record.get("event") or {}).get("event_type")
            == "external_action_authorized"
            for record in self.runtime.load_records(state["run_id"])
        ))
        run = self.runtime.load_run(state["run_id"])
        conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        self.assertEqual(
            self.runtime.authorize_action(
                state["run_id"],
                "execute_approved_programming_step",
                ["artifact:report.py"],
                satisfied_conditions=conditions,
                effect_type="local_reversible",
                scope_kind="external",
            ),
            ["grant-execute-approved-step"],
        )
        self.assertEqual(
            pre_state["artifact"]["locator"],
            {"kind": "file", "ref": str(self.target.resolve())},
        )
        self.assertEqual(pre_state["artifact"]["identity"]["kind"], "composite")
        post_state, receipt = self._post_state_and_receipt(state, pre_state)
        self.assertEqual(post_state["artifact"]["locator"], pre_state["artifact"]["locator"])
        self.assertEqual(
            receipt["payload"]["target_binding"]["locator"],
            pre_state["artifact"]["locator"],
        )
        action = self.runtime.record_action(
            state["run_id"],
            action="execute_approved_programming_step",
            selectors=["artifact:report.py"],
            satisfied_conditions=conditions,
            effect_type="local_reversible",
            external_effect=True,
            receipt_artifact_id=receipt["artifact"]["artifact_id"],
            details=self._mutation_details(pre_state, post_state),
        )
        self.assertTrue(action["event"]["details"]["external_effect"])
        event_types = [
            (record.get("event") or {}).get("event_type")
            for record in self.runtime.load_records(state["run_id"])
        ]
        self.assertLess(
            event_types.index("external_action_authorized"),
            event_types.index("repository_state_captured", event_types.index(
                "external_action_authorized"
            )),
        )
        self.assertLess(
            event_types.index("repository_mutation_receipt_issued"),
            event_types.index("action_completed"),
        )
        self.runtime.complete_action_node(
            state["run_id"],
            "execute_approved_programming_step",
            reason="exact approved mutation completed with recovery proof",
            artifact_ids=[receipt["artifact"]["artifact_id"]],
        )
        self.assertEqual(
            self.runtime.load_run(state["run_id"])["current_node_id"],
            "attempt-review",
        )
        self.assertFalse(
            self.service.get_state("dialogue-plan")["target_mutation_authorized"]
        )

    def test_exact_checkpointed_correction_mutation_returns_to_attempt_review(self):
        state = self.approved()
        pre_state = self._enter_external_execute_step(state)
        post_state, receipt = self._post_state_and_receipt(state, pre_state)
        run = self.runtime.load_run(state["run_id"])
        execute_conditions = self._grant_conditions(
            run, "execute_approved_programming_step"
        )
        self.runtime.record_action(
            state["run_id"],
            action="execute_approved_programming_step",
            selectors=["artifact:report.py"],
            satisfied_conditions=execute_conditions,
            effect_type="local_reversible",
            external_effect=True,
            receipt_artifact_id=receipt["artifact"]["artifact_id"],
            details=self._mutation_details(pre_state, post_state),
        )
        self.runtime.complete_action_node(
            state["run_id"],
            "execute_approved_programming_step",
            reason="first attempt exposes a correctable defect",
            artifact_ids=[receipt["artifact"]["artifact_id"]],
        )

        run = self.runtime.load_run(state["run_id"])
        review_conditions = self._grant_conditions(run, "inspect_programming_result")
        review = self.runtime.record_inline_artifact(
            state["run_id"], "correctable-defect-evidence",
            "The current report has one bounded local defect.",
            role="evidence", node_id="attempt-review",
            action="inspect_programming_result",
            selector="scope:declared_outputs",
            satisfied_conditions=review_conditions,
        )
        review_refs = [
            {
                "evidence_id": evidence_id,
                "artifact_id": review["artifact"]["artifact_id"],
                "identity_digest": review["artifact"]["identity"]["digest"],
                "outcome": "FAIL",
            }
            for evidence_id in ("ev-identity", "ev-delta", "ev-check", "ev-review")
        ]
        self.runtime.apply_transition(
            state["run_id"], "REVISE",
            target_node_id="revision-route",
            reason="independent review found a bounded execution defect",
            evaluation_boundary="delegated-programming-attempt-review",
            evidence_refs=review_refs,
        )
        self.runtime.advance_decision(
            state["run_id"], "prg_run",
            reason="PRG-Run permits bounded correction",
        )
        self.runtime.advance_bounded_loop(
            state["run_id"], continue_loop=True,
            reason="enter the bounded correction body",
        )
        self.assertEqual(
            self.runtime.load_run(state["run_id"])["current_node_id"], "correct"
        )
        self.assertFalse(
            self.service.get_state("dialogue-plan")["target_mutation_authorized"]
        )

        correction_pre = self.delegation.capture_repository_state(
            "dialogue-plan",
            artifact_id="correction-pre-state",
            phase="pre_action",
        )
        self.assertFalse(
            self.service.get_state("dialogue-plan")["target_mutation_authorized"]
        )
        self.runtime.create_checkpoint(
            state["run_id"], "before-approved-correction",
            segment_id="approved-report-correction",
            resume_node_id="correct",
        )
        self.assertTrue(
            self.service.get_state("dialogue-plan")["target_mutation_authorized"]
        )
        run = self.runtime.load_run(state["run_id"])
        correction_conditions = self._grant_conditions(
            run, "correct_programming_defect"
        )
        self.assertEqual(
            self.runtime.authorize_action(
                state["run_id"], "correct_programming_defect",
                ["artifact:report.py"],
                satisfied_conditions=correction_conditions,
                effect_type="local_reversible",
                scope_kind="external",
            ),
            ["grant-execute-approved-step"],
        )
        report = self.target / "report.py"
        report.write_text(
            report.read_text(encoding="utf-8") + "# bounded correction\n",
            encoding="utf-8",
        )
        correction_post = self.delegation.capture_repository_state(
            "dialogue-plan",
            artifact_id="correction-post-state",
            phase="post_action",
        )
        correction_receipt = self.delegation.issue_repository_mutation_receipt(
            "dialogue-plan",
            artifact_id="correction-mutation-receipt",
            pre_state_artifact_id=correction_pre["artifact"]["artifact_id"],
            post_state_artifact_id=correction_post["artifact"]["artifact_id"],
        )
        self.runtime.record_action(
            state["run_id"],
            action="correct_programming_defect",
            selectors=["artifact:report.py"],
            satisfied_conditions=correction_conditions,
            effect_type="local_reversible",
            external_effect=True,
            receipt_artifact_id=correction_receipt["artifact"]["artifact_id"],
            details=self._mutation_details(
                correction_pre, correction_post,
                operation="correct_programming_defect",
            ),
        )
        self.runtime.complete_action_node(
            state["run_id"], "correct_programming_defect",
            reason="bounded correction completed with exact repository evidence",
            artifact_ids=[correction_receipt["artifact"]["artifact_id"]],
        )
        self.assertEqual(
            self.runtime.load_run(state["run_id"])["current_node_id"],
            "attempt-review",
        )
        self.assertFalse(
            self.service.get_state("dialogue-plan")["target_mutation_authorized"]
        )

    def test_delegation_is_idempotent_and_restart_exact(self):
        state = self.approved()
        first = self.delegate(state)
        before = self.runtime.load_records(state["run_id"])
        second = self.delegate(state)
        after = self.runtime.load_records(state["run_id"])
        self.assertEqual(first, second)
        self.assertEqual(before, after)

        restarted = self.restarted()
        self.assertEqual(restarted.get_delegation("dialogue-plan"), first)
        projection = restarted.projection()
        row = next(item for item in projection["pending"]
                   if item["run_id"] == state["run_id"])
        self.assertTrue(row["quiet"])
        self.assertFalse(row["needs_attention"])
        self.assertEqual(row["visible_status"], "Operating")
        self.assertEqual(projection["unread"], [])
        self.assertFalse(projection["phase_2_5_authorized"])

    def test_started_delegation_retry_cannot_be_reinterpreted_after_target_changes(self):
        state = self.approved()
        first = self.delegate(state)
        before = self.runtime.load_records(state["run_id"])
        (self.target / "report.py").write_text("TOTAL = 9\n", encoding="utf-8")
        self.assertEqual(self.delegate(state), first)
        self.assertEqual(self.runtime.load_records(state["run_id"]), before)
        with self.assertRaises(delegation.ProcessDelegationConflict):
            self.delegate(state, key="delegation:replacement")
        self.assertEqual(self.runtime.load_records(state["run_id"]), before)

    def test_adjacent_authorization_and_activation_rewrite_cannot_replace_approved_authority(self):
        state = self.approved()
        self.delegate(state)
        records_path = self.runtime._events_path(state["run_id"])
        records = [
            json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        authorization = next(
            record for record in records
            if (record.get("event") or {}).get("event_type")
            == "dialogue_observation_recorded"
            and record["event"]["details"].get("observation_type")
            == "programming_delegation_authorized"
        )
        payload = authorization["event"]["details"]["payload"]
        payload["requested_by"] = "principal:attacker"
        authorization_body = {
            key: payload[key]
            for key in (
                "schema_version", "idempotency_key", "dialogue_ref", "run_id",
                "binding_digest", "plan_ref", "approval_receipt_digest",
                "approval_decision", "requested_by", "target_baseline_digest",
            )
        }
        payload["delegation_digest"] = delegation._digest_json(authorization_body)
        authorization["event"]["details"]["payload_digest"] = delegation._digest_json(
            payload
        )
        activation = next(
            record for record in records
            if (record.get("event") or {}).get("event_type") == "delegation_activated"
        )
        activation["event"]["details"]["delegation_digest"] = payload[
            "delegation_digest"
        ]
        records_path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        with self.assertRaises(delegation.ProcessDelegationIntegrityError):
            self.restarted().get_delegation("dialogue-plan")
        with self.assertRaises(delegation.ProcessDelegationIntegrityError):
            self.restarted().projection()

    def test_wrong_plan_receipt_principal_and_retry_identity_fail_closed(self):
        state = self.approved()
        plan = state["current_plan"]
        exact_ref = {
            field: plan[field] for field in ("plan_id", "version", "digest")
        }
        calls = [
            {"plan_ref": {**exact_ref, "version": "99.0"},
             "approval_receipt_digest": state["dialogue_lifecycle"]["approval_receipt_digest"],
             "requested_by": "principal:user", "idempotency_key": "wrong:plan"},
            {"plan_ref": exact_ref, "approval_receipt_digest": "sha256:" + "0" * 64,
             "requested_by": "principal:user", "idempotency_key": "wrong:receipt"},
            {"plan_ref": exact_ref,
             "approval_receipt_digest": state["dialogue_lifecycle"]["approval_receipt_digest"],
             "requested_by": "principal:other", "idempotency_key": "wrong:principal"},
        ]
        for kwargs in calls:
            with self.subTest(key=kwargs["idempotency_key"]):
                with self.assertRaises((
                    delegation.ProcessDelegationError,
                    runtime.AuthorityDeniedError,
                )):
                    self.delegation.delegate("dialogue-plan", **kwargs)
        self.assertFalse(any(
            (record.get("event") or {}).get("event_type") == "delegation_activated"
            for record in self.runtime.load_records(state["run_id"])
        ))

        self.delegate(state)
        with self.assertRaises(delegation.ProcessDelegationConflict):
            self.delegation.delegate(
                "dialogue-plan",
                plan_ref=exact_ref,
                approval_receipt_digest=state["dialogue_lifecycle"][
                    "approval_receipt_digest"
                ],
                requested_by="principal:user",
                idempotency_key="delegation:different",
            )

    def test_baseline_drift_withholds_execution_and_becomes_unread_decision(self):
        state = self.approved()
        (self.target / "report.py").write_text("TOTAL = 2\n", encoding="utf-8")
        withheld = self.delegate(state)
        self.assertEqual(withheld["status"], "withheld")
        run = self.runtime.load_run(state["run_id"])
        self.assertEqual(run["current_node_id"], "post-plan-mode")
        self.assertNotIn("delegated", run["labels"])
        self.assertFalse(any(
            (record.get("event") or {}).get("event_type")
            in {"delegation_activated", "checkpoint_created"}
            for record in self.runtime.load_records(state["run_id"])
        ))

        projection = self.restarted().projection()
        pending = next(item for item in projection["pending"]
                       if item["run_id"] == state["run_id"])
        unread = next(item for item in projection["unread"]
                      if item["run_id"] == state["run_id"])
        self.assertFalse(pending["quiet"])
        self.assertTrue(pending["needs_attention"])
        self.assertEqual(pending["visible_status"], "Waiting for You")
        self.assertEqual(pending, unread)
        self.assertEqual(
            unread["attention"]["condition"], "approved_baseline_stale"
        )
        self.assertEqual(len(unread["attention"]["evidence_refs"]), 2)
        self.assertIn("Revise and approve", unread["attention"]["required_decision"])

    def test_authorized_but_interrupted_activation_is_conspicuous_after_restart(self):
        state = self.approved()
        with mock.patch.object(
            self.runtime,
            "_activate_approved_delegation",
            side_effect=RuntimeError("injected activation interruption"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.delegate(state)
        projection = self.restarted().projection()
        row = next(item for item in projection["pending"]
                   if item["run_id"] == state["run_id"])
        self.assertFalse(row["quiet"])
        self.assertTrue(row["needs_attention"])
        self.assertEqual(row["visible_status"], "Blocked")
        self.assertEqual(
            row["attention"]["condition"], "delegation_activation_incomplete"
        )

    def test_activation_and_preflight_interruptions_resume_without_duplicate_authority(self):
        for method_name in ("create_checkpoint", "advance_decision"):
            with self.subTest(method=method_name):
                case = Phase24Fixture(methodName="runTest")
                case.setUp()
                try:
                    state = case.approved()
                    with mock.patch.object(
                        case.runtime, method_name,
                        side_effect=RuntimeError(
                            f"injected {method_name} interruption"
                        ),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "injected"):
                            case.delegate(state)
                    interrupted = case.restarted().get_delegation("dialogue-plan")
                    self.assertEqual(
                        interrupted["status"], "activation_incomplete"
                    )
                    plan_state = case.service.get_state("dialogue-plan")
                    self.assertFalse(plan_state["target_mutation_authorized"])
                    self.assertEqual(
                        plan_state["next_action"], "finish_phase_2_4_activation"
                    )
                    completed = case.delegate(state)
                    self.assertEqual(completed["status"], "delegated")
                    records = case.runtime.load_records(state["run_id"])
                    self.assertEqual(sum(
                        (record.get("event") or {}).get("event_type")
                        == "delegation_activated" for record in records
                    ), 1)
                    self.assertEqual(sum(
                        (record.get("event") or {}).get("event_type")
                        == "checkpoint_created"
                        and ((record.get("event") or {}).get("details") or {}).get(
                            "segment_id"
                        ) == "phase-2.4-delegated-execution"
                        for record in records
                    ), 1)
                finally:
                    case.doCleanups()

    def test_human_checkpoint_is_pending_and_unread_without_inspector_data(self):
        state = self.propose()
        projection = self.delegation.projection()
        pending = next(item for item in projection["pending"]
                       if item["run_id"] == state["run_id"])
        unread = next(item for item in projection["unread"]
                      if item["run_id"] == state["run_id"])
        self.assertFalse(pending["quiet"])
        self.assertEqual(pending["visible_status"], "Waiting for You")
        self.assertEqual(pending, unread)
        self.assertEqual(unread["attention"]["kind"], "decision")
        self.assertNotIn("records", pending)
        self.assertNotIn("graph", pending)

    def _generic_run_with_evidence(self, run_id):
        definition = runtime_fixtures.make_definition("attention/generic")
        run = runtime_fixtures.make_run(run_id, definition)
        run["input_bindings"]["dialogue_ref"] = "dialogue-plan"
        self.runtime.create_run(definition, run)
        self.runtime.start_run(run_id, reason="approved generic attention proof")
        result = self.runtime.record_inline_artifact(
            run_id, "result", "candidate result", role="result", node_id="act",
            action="produce_artifact", selector=runtime_fixtures.OUTPUT,
            satisfied_conditions=runtime_fixtures.CONDITION,
        )
        evidence = self.runtime.record_inline_artifact(
            run_id, "evidence", "independent proof", role="evidence",
            node_id="verify", action="record_evidence",
            selector=runtime_fixtures.OUTPUT, source_artifact_ids=["result"],
            satisfied_conditions=runtime_fixtures.CONDITION,
        )
        return result, evidence

    def test_authority_request_projects_exact_condition_evidence_and_decision(self):
        result, _evidence = self._generic_run_with_evidence("run-authority")
        request = {
            "request_id": "authority-attention",
            "request_type": "scope_expansion",
            "requested_authority": ["expand_scope"],
            "options": ["approve", "deny"],
            "resume_node_id": "verify",
            "requested_from": "principal-001",
        }
        self.runtime.apply_transition(
            "run-authority", "ESCALATE", target_node_id="verify",
            reason="A declared scope decision is required.",
            evaluation_boundary="independent_quality_review",
            authority_request=request,
            evidence_refs=[runtime_fixtures.evidence_ref(result, "FAIL")],
        )
        projection = self.delegation.projection()
        row = next(item for item in projection["unread"]
                   if item["run_id"] == "run-authority")
        self.assertEqual(row["visible_status"], "Waiting for You")
        self.assertEqual(
            row["attention"]["condition"],
            "A declared scope decision is required.",
        )
        self.assertEqual(row["attention"]["required_decision"], {
            "request_id": "authority-attention",
            "request_type": "scope_expansion",
            "requested_authority": ["expand_scope"],
            "options": ["approve", "deny"],
            "resume_node_id": "verify",
        })
        self.assertEqual(len(row["attention"]["evidence_refs"]), 1)

    def test_completed_result_is_unread_then_read_but_never_pending(self):
        result, evidence = self._generic_run_with_evidence("run-complete")
        review = self.runtime.record_final_review(
            "run-complete", artifact_id="result", evidence_id="result_verified",
            evidence_artifact_id="evidence", outcome="PASS",
            reviewer_id="independent-reviewer", independent=True,
            satisfied_conditions=runtime_fixtures.CONDITION,
        )
        self.runtime.apply_transition(
            "run-complete", "ACCEPT", target_node_id="accepted",
            reason="The exact result passed independent review.",
            evaluation_boundary="independent_quality_review",
            evidence_refs=review["evidence_refs"],
        )
        projection = self.delegation.projection()
        self.assertFalse(any(
            item["run_id"] == "run-complete" for item in projection["pending"]
        ))
        row = next(item for item in projection["unread"]
                   if item["run_id"] == "run-complete")
        self.assertEqual(row["visible_status"], "Completed")
        self.assertEqual(row["attention"]["kind"], "result")
        self.assertEqual(row["attention"]["result_artifacts"], [{
            "artifact_id": "result",
            "identity_digest": result["artifact"]["identity"]["digest"],
            "media_type": "text/markdown",
            "locator": {"kind": "inline", "ref": "inline:run-complete:result"},
        }])
        memory.mark_conversation_read(
            "dialogue-plan", timestamp="2026-07-18T13:00:00Z",
            sessions_root=self.root / "sessions",
        )
        self.assertFalse(any(
            item["run_id"] == "run-complete"
            for item in self.delegation.projection()["unread"]
        ))

    def test_blocked_result_explains_condition_evidence_and_required_decision(self):
        result, _evidence = self._generic_run_with_evidence("run-blocked")
        self.runtime.apply_transition(
            "run-blocked", "BLOCKED", target_node_id="blocked",
            reason="Required source evidence is unavailable.",
            evaluation_boundary="independent_quality_review",
            evidence_refs=[runtime_fixtures.evidence_ref(result, "FAIL")],
        )
        projection = self.delegation.projection()
        self.assertFalse(any(
            item["run_id"] == "run-blocked" for item in projection["pending"]
        ))
        row = next(item for item in projection["unread"]
                   if item["run_id"] == "run-blocked")
        self.assertEqual(row["visible_status"], "Blocked")
        self.assertEqual(
            row["attention"]["condition"],
            "Required source evidence is unavailable.",
        )
        self.assertEqual(len(row["attention"]["evidence_refs"]), 1)
        self.assertIn("missing authority or evidence", row["attention"]["required_decision"])

    def test_registration_cannot_impersonate_standing_deployment(self):
        standing = runtime_fixtures.make_definition("automation/weekly-cash")
        standing["status"] = "active"
        standing["labels"] = [
            "governed", "reusable", "standing", "trigger-weekly",
            "authority-finance",
        ]
        standing = seal_definition(standing)
        ordinary = runtime_fixtures.make_definition("automation/manual-review")
        ordinary["status"] = "active"
        ordinary["labels"] = ["governed", "reusable"]
        ordinary = seal_definition(ordinary)
        self.registry.register(standing)
        self.registry.register(ordinary)

        projected = self.delegation.projection()["automated_processes"]
        self.assertEqual(projected, [])


class Phase24ServerTests(Phase24Fixture):
    def test_approve_and_start_approves_then_delegates_exact_plan(self):
        state = self.propose()
        plan = state["current_plan"]
        payload = {
            "action": "approve_and_start",
            "plan_ref": {
                field: plan[field] for field in ("plan_id", "version", "digest")
            },
            "baseline_digest": plan["repository_artifact_scope"]["target"][
                "identity"
            ]["digest"],
            "decision_by": "principal:user",
            "idempotency_key": "approval:auto-start",
        }
        with mock.patch.object(
            server, "_process_delegation_service", return_value=self.delegation
        ):
            approved = server._apply_process_plan_action(
                self.service, "dialogue-plan", payload
            )
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["delegation"]["status"], "delegated")
        self.assertEqual(approved["current_node_id"], "execute-preflight")
        self.assertTrue(approved["phase_2_4_authorized"])

    def test_delegation_and_attention_api_use_durable_service(self):
        state = self.approved()
        plan = state["current_plan"]
        body = {
            "action": "delegate",
            "plan_ref": {
                field: plan[field] for field in ("plan_id", "version", "digest")
            },
            "approval_receipt_digest": state["dialogue_lifecycle"][
                "approval_receipt_digest"
            ],
            "requested_by": "principal:user",
            "idempotency_key": "delegation:api",
        }
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_delegation_service", return_value=self.delegation
        ):
            response = client.post("/api/process-delegation/dialogue-plan", json=body)
            projection = client.get("/api/process-attention")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["delegation"]["status"], "delegated")
        self.assertEqual(projection.status_code, 200)
        payload = projection.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["pending"]), 1)
        self.assertEqual(payload["unread"], [])
        self.assertFalse(payload["phase_2_5_authorized"])

    def test_api_rejects_non_delegation_action_without_state_change(self):
        state = self.approved()
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_delegation_service", return_value=self.delegation
        ):
            response = client.post(
                "/api/process-delegation/dialogue-plan", json={"action": "execute"}
            )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(any(
            (record.get("event") or {}).get("event_type") == "delegation_activated"
            for record in self.runtime.load_records(state["run_id"])
        ))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
