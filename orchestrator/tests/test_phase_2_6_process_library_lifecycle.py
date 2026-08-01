"""G1.1 Phase 2.6 — exact Process Library and Run lifecycle proofs."""

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
import process_definition_registry as registry_module  # noqa: E402
import process_entry_routing as entry  # noqa: E402
import process_library_lifecycle as library  # noqa: E402
from server import app as server  # noqa: E402
from tests import test_phase_1_7_kernel_trials as phase17  # noqa: E402


NOW = phase17.NOW


class Phase26Fixture(phase17.TrialCase):
    def setUp(self):
        super().setUp()
        self.registry_root = Path(self.temp.name) / "definitions"
        self.registry = registry_module.ProcessDefinitionRegistry(
            self.registry_root, now=lambda: NOW
        )
        self.service = library.ProcessLibraryLifecycleService(
            runtime=self.runtime,
            registry=self.registry,
            now=lambda: NOW,
        )

    def completed_result_run(self, run_id: str):
        definition = phase17._cash_review_definition()
        self.create(run_id, definition)
        result = self.runtime.record_inline_artifact(
            run_id,
            f"{run_id}-result",
            "accepted exact result",
            role="result",
            node_id="calculate",
            action="produce_artifact",
            selector=phase17.OUTPUT,
            satisfied_conditions=phase17.CONDITIONS,
        )
        self.runtime.complete_action_node(
            run_id,
            "calculate_permitted_cash_flow",
            reason="result produced",
            artifact_ids=[result["artifact"]["artifact_id"]],
        )
        self.accept_existing_result(run_id, result["artifact"]["artifact_id"])
        return definition, result

    def completed_construction_run(self, run_id: str = "run-library-promotion"):
        target = phase17._cash_review_definition()
        construction = phase17._construction_definition(target)
        self.create(run_id, construction)
        definition_artifact = self.runtime.record_inline_artifact(
            run_id,
            "constructed-definition",
            json.dumps(target, sort_keys=True),
            role="process_definition",
            node_id="construct-definition",
            action="construct_definition",
            selector=phase17.DEFINITION_SCOPE,
            satisfied_conditions=phase17.CONDITIONS,
            media_type="application/vnd.ora.process-definition+json",
        )
        self.runtime.complete_action_node(
            run_id,
            "construct_reusable_process_definition",
            reason="exact definition constructed",
            artifact_ids=[definition_artifact["artifact"]["artifact_id"]],
        )
        result = self.runtime.register_process_definition(
            run_id,
            self.registry,
            target,
            definition_artifact_id=definition_artifact["artifact"]["artifact_id"],
            registration_artifact_id="registration-result",
            selector=phase17.DEFINITION_SCOPE,
            satisfied_conditions=phase17.CONDITIONS,
        )
        registration = result["registration"]
        self.assertEqual(
            result["registration_record"]["event"]["details"]["definition_ref"],
            phase17._definition_ref(target),
        )
        self.assertEqual(registration["definition_ref"], phase17._definition_ref(target))
        self.runtime.complete_action_node(
            run_id,
            "register_reusable_process_definition",
            reason="registered without activation",
            artifact_ids=[result["artifact"]["artifact_id"]],
        )
        self.accept_existing_result(run_id, result["artifact"]["artifact_id"])
        return target, definition_artifact, result

    def promote(self, run_id="run-library-promotion"):
        target, definition_artifact, result = self.completed_construction_run(run_id)
        ref = phase17._definition_ref(target)
        state = self.service.close_run(
            run_id,
            disposition="promote",
            decision_by="principal-001",
            promoted_definition_ref=ref,
            capability_artifact_id=definition_artifact["artifact"]["artifact_id"],
        )
        return target, definition_artifact, result, state


class Phase26ProcessLibraryTests(Phase26Fixture):
    def test_seed_catalog_read_is_side_effect_free_and_exposes_exact_package(self):
        target = phase17._cash_review_definition()
        absent_root = Path(self.temp.name) / "absent-registry"
        service = library.ProcessLibraryLifecycleService(
            runtime=self.runtime,
            registry_root=absent_root,
            seed_definitions=[target],
            now=lambda: NOW,
        )

        catalog = service.list_entries(project_ref="project:trial")
        item = catalog["entries"][0]
        self.assertFalse(absent_root.exists())
        self.assertEqual(item["definition_ref"], phase17._definition_ref(target))
        self.assertEqual(item["scope"], target["scope"])
        self.assertEqual(
            item["package"]["package_id"], target["package_manifest"]["package_id"]
        )
        self.assertEqual(
            item["package"]["members"], target["package_manifest"]["members"]
        )
        self.assertEqual(item["lifecycle_status"], "registered")
        self.assertFalse(item["manual_invocation_available"])
        self.assertFalse(item["standing_automation"])

        empty_root = Path(self.temp.name) / "empty-registry"
        empty_root.mkdir()
        empty_service = library.ProcessLibraryLifecycleService(
            runtime=self.runtime,
            registry_root=empty_root,
            seed_definitions=[target],
            now=lambda: NOW,
        )
        self.assertEqual(len(empty_service.list_entries()["entries"]), 1)
        self.assertEqual(list(empty_root.iterdir()), [])

    def test_project_and_universal_scope_filter_without_latest_version_inference(self):
        project = phase17._cash_review_definition()
        universal = phase17._definition("business/universal-review")
        universal["scope"] = {"kind": "universal", "selector": "*"}
        universal = phase17._seal_definition(universal)
        universal_v2 = copy.deepcopy(universal)
        universal_v2["version"] = "2.0.0"
        universal_v2["package_manifest"]["package_version"] = "2.0.0"
        universal_v2 = phase17._seal_definition(universal_v2)
        self.registry.register(project)
        self.registry.register(universal)
        self.registry.register(universal_v2)

        in_scope = self.service.list_entries(project_ref="project:trial")["entries"]
        out_of_scope = self.service.list_entries(project_ref="project:other")[
            "entries"
        ]
        self.assertEqual(len(in_scope), 3)
        self.assertEqual(
            {
                (item["definition_ref"]["definition_id"],
                 item["definition_ref"]["version"])
                for item in out_of_scope
            },
            {
                ("business/universal-review", "1.0.0"),
                ("business/universal-review", "2.0.0"),
            },
        )
        self.assertTrue(all("definition_ref" in item for item in in_scope))

    def test_promotion_enables_manual_invocation_without_standing_automation(self):
        target, _definition_artifact, _result, lifecycle = self.promote()
        ref = phase17._definition_ref(target)
        item = self.service.list_entries(project_ref="project:trial")["entries"][0]

        self.assertEqual(lifecycle["status"], "closed")
        self.assertEqual(lifecycle["closure"]["disposition"], "promote")
        self.assertEqual(
            lifecycle["closure"]["idempotency_key"],
            runtime.lifecycle_disposition_idempotency_key(
                "run-library-promotion",
                "promote",
                ref,
                lifecycle["closure"]["capability_artifact_id"],
            ),
        )
        self.assertEqual(item["definition_ref"], ref)
        self.assertEqual(item["lifecycle_status"], "available")
        self.assertTrue(item["manual_invocation_available"])
        self.assertFalse(item["activated"])
        self.assertFalse(item["standing_automation"])

        routed = entry.route_process_entry(
            {
                "source": "process_library",
                "objective": "Use the cash-flow review for this project.",
                "project_ref": "project:trial",
                "project_confirmed": False,
                "selected_definition_ref": ref,
            },
            catalog=[item],
            project_visible=lambda _project: True,
        )
        self.assertEqual(routed["status"], "ready")
        self.assertEqual(routed["definition_ref"], ref)

        activation = entry.route_process_entry(
            {
                "source": "process_library",
                "objective": "Activate the cash-flow review for this project.",
                "project_ref": "project:trial",
                "project_confirmed": False,
                "selected_definition_ref": ref,
            },
            catalog=[item],
            project_visible=lambda _project: True,
        )
        self.assertEqual(activation["status"], "ready")
        self.assertEqual(activation["next_action"], "begin_activation_review")
        self.assertEqual(activation["authority_effects"], [])

    def test_invocation_fails_closed_outside_exact_project_scope(self):
        target, _definition_artifact, _result, _lifecycle = self.promote()
        item = self.service.list_entries()["entries"][0]
        with self.assertRaisesRegex(
            entry.ProcessEntryRoutingError, "outside the confirmed project scope"
        ):
            entry.route_process_entry(
                {
                    "source": "process_library",
                    "objective": "Use the cash-flow review here.",
                    "project_ref": "project:other",
                    "project_confirmed": False,
                    "selected_definition_ref": phase17._definition_ref(target),
                },
                catalog=[item],
                project_visible=lambda _project: True,
            )

    def test_exact_registration_tampering_blocks_library_listing(self):
        target = phase17._cash_review_definition()
        self.registry.register(target)
        path = self.registry._definition_path(target["definition_id"], target["version"])
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["definition"]["purpose"] = "substituted"
        path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaises(library.ProcessLibraryIntegrityError):
            self.service.list_entries()


class Phase26LifecycleTests(Phase26Fixture):
    def test_preserve_is_idempotent_and_second_disposition_is_rejected(self):
        self.completed_result_run("run-preserve")
        first = self.service.close_run(
            "run-preserve",
            disposition="preserve",
            decision_by="principal-001",
        )
        second = self.service.close_run(
            "run-preserve",
            disposition="preserve",
            decision_by="principal-001",
        )
        self.assertEqual(first, second)
        self.assertEqual(first["closure"]["disposition"], "preserve")
        self.assertTrue(all(
            item["lifecycle_status"] == "preserved"
            for item in first["closure"]["effective_artifacts"]
        ))
        with self.assertRaises(library.ProcessLibraryConflict):
            self.service.close_run(
                "run-preserve",
                disposition="archive",
                decision_by="principal-001",
            )

    def test_slash_and_long_run_ids_use_bounded_deterministic_retry_identity(self):
        run_ids = (
            "run/grouped-result",
            "run/" + ("long-valid-segment" * 40),
        )
        keys = []
        for run_id in run_ids:
            with self.subTest(run_id_length=len(run_id)):
                self.completed_result_run(run_id)
                first = self.service.close_run(
                    run_id,
                    disposition="preserve",
                    decision_by="principal-001",
                )
                retry = self.service.close_run(
                    run_id,
                    disposition="preserve",
                    decision_by="principal-001",
                )
                self.assertEqual(retry, first)
                key = first["closure"]["idempotency_key"]
                self.assertRegex(key, r"^lifecycle:[0-9a-f]{64}$")
                self.assertEqual(len(key), 74)
                self.assertNotIn(run_id, key)
                self.assertEqual(
                    key,
                    runtime.lifecycle_disposition_idempotency_key(
                        run_id, "preserve"
                    ),
                )
                keys.append(key)
        self.assertEqual(len(set(keys)), 2)

    def test_archive_and_discard_are_explicit_metadata_not_file_deletion(self):
        for disposition, expected in (("archive", "archived"), ("discard", "discarded")):
            with self.subTest(disposition=disposition):
                run_id = f"run-{disposition}"
                _definition, result = self.completed_result_run(run_id)
                artifact_path = self.runtime._artifact_path(
                    run_id, result["artifact"]["artifact_id"]
                )
                artifact_bytes = artifact_path.read_bytes()
                lifecycle = self.service.close_run(
                    run_id,
                    disposition=disposition,
                    decision_by="principal-001",
                )
                self.assertTrue(artifact_path.is_file())
                self.assertEqual(artifact_path.read_bytes(), artifact_bytes)
                self.assertFalse(any(
                    (record.get("event") or {}).get("event_type")
                    in {"delegation_activated", "process_invoked"}
                    for record in self.runtime.load_records(run_id)
                ))
                effective = {
                    item["artifact_id"]: item["lifecycle_status"]
                    for item in lifecycle["closure"]["effective_artifacts"]
                }
                self.assertEqual(
                    effective[result["artifact"]["artifact_id"]], expected
                )

    def test_nonterminal_wrong_principal_and_generic_forgery_are_rejected(self):
        definition = phase17._cash_review_definition()
        self.create("run-still-running", definition)
        with self.assertRaises(library.ProcessLibraryConflict):
            self.service.close_run(
                "run-still-running",
                disposition="preserve",
                decision_by="principal-001",
            )

        self.completed_result_run("run-wrong-principal")
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.service.close_run(
                "run-wrong-principal",
                disposition="preserve",
                decision_by="not-the-principal",
            )
        with self.assertRaises(runtime.AuthorityDeniedError):
            self.runtime.record_event(
                "run-wrong-principal",
                "lifecycle_disposition_recorded",
                {"disposition": "promote"},
            )

    def test_promotion_requires_exact_registered_content_and_accepted_lineage(self):
        target = phase17._cash_review_definition()
        self.registry.register(target)
        self.completed_result_run("run-no-capability")
        with self.assertRaisesRegex(
            library.ProcessLibraryInputRequired,
            "Process Definition Artifact",
        ):
            self.service.close_run(
                "run-no-capability",
                disposition="promote",
                decision_by="principal-001",
                promoted_definition_ref=phase17._definition_ref(target),
            )

    def test_lifecycle_tampering_and_duplicate_records_fail_closed(self):
        self.completed_result_run("run-tampered-lifecycle")
        self.service.close_run(
            "run-tampered-lifecycle",
            disposition="preserve",
            decision_by="principal-001",
        )
        records_path = self.runtime._events_path("run-tampered-lifecycle")
        records = [
            json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()
        ]
        records[-1]["event"]["details"]["disposition"] = "promote"
        records_path.write_text(
            "\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(library.ProcessLibraryIntegrityError):
            self.service.get_run_lifecycle("run-tampered-lifecycle")

    def test_restart_reconstructs_closure_and_promotion_from_registry_and_run(self):
        target, _definition_artifact, _result, original = self.promote(
            "run-restart-promotion"
        )
        restarted = library.ProcessLibraryLifecycleService(
            runtime=runtime.GovernedProcessRuntime(
                Path(self.temp.name) / "runs", now=lambda: NOW
            ),
            registry=registry_module.ProcessDefinitionRegistry(
                self.registry_root, now=lambda: NOW
            ),
            now=lambda: NOW,
        )
        self.assertEqual(
            restarted.get_run_lifecycle("run-restart-promotion"), original
        )
        item = restarted.list_entries(project_ref="project:trial")["entries"][0]
        self.assertEqual(item["definition_ref"], phase17._definition_ref(target))
        self.assertTrue(item["manual_invocation_available"])


class Phase26ServerBoundaryTests(Phase26Fixture):
    def test_promoted_exact_version_is_invocable_through_http_without_activation(self):
        target, _definition_artifact, _result, _state = self.promote(
            "run-http-promotion"
        )
        ref = phase17._definition_ref(target)
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_library_service", return_value=self.service
        ), mock.patch.object(
            server, "_process_entry_project_visible", return_value=True
        ):
            response = client.post("/api/process-entry/route", json={
                "source": "process_library",
                "objective": "Use the cash-flow review for this project.",
                "project_ref": "project:trial",
                "project_confirmed": False,
                "selected_definition_ref": ref,
            })
        self.assertEqual(response.status_code, 200)
        routed = response.get_json()["entry"]
        self.assertEqual(routed["status"], "ready")
        self.assertEqual(routed["next_action"], "begin_exact_definition_invocation")
        self.assertEqual(routed["definition_ref"], ref)
        item = self.service.list_entries(project_ref="project:trial")["entries"][0]
        self.assertFalse(item["activated"])
        self.assertFalse(item["standing_automation"])

    def test_library_and_lifecycle_endpoints_preserve_exact_contract(self):
        run_id = "run/grouped-result"
        self.completed_result_run(run_id)
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_library_service", return_value=self.service
        ):
            before = client.get(f"/api/process-runs/{run_id}/lifecycle")
            closed = client.post(
                f"/api/process-runs/{run_id}/lifecycle",
                json={
                    "disposition": "preserve",
                    "decision_by": "principal-001",
                },
            )
            retry = client.post(
                f"/api/process-runs/{run_id}/lifecycle",
                json={
                    "disposition": "preserve",
                    "decision_by": "principal-001",
                    "idempotency_key": (
                        "lifecycle:run/grouped-result:preserve:outputs"
                    ),
                },
            )
            catalog = client.get(
                "/api/process-library/entries?project_ref=project:trial"
            )
        self.assertEqual(before.status_code, 200)
        self.assertEqual(
            before.get_json()["lifecycle"]["status"], "awaiting_disposition"
        )
        self.assertEqual(
            before.get_json()["lifecycle"]["principal_id"], "principal-001"
        )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(
            closed.get_json()["lifecycle"]["closure"]["disposition"], "preserve"
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.get_json(), closed.get_json())
        key = closed.get_json()["lifecycle"]["closure"]["idempotency_key"]
        self.assertRegex(key, r"^lifecycle:[0-9a-f]{64}$")
        self.assertNotIn(run_id, key)
        self.assertEqual(catalog.status_code, 200)
        self.assertIn("catalog_digest", catalog.get_json()["library"])

    def test_lifecycle_endpoint_rejects_unknown_fields(self):
        self.completed_result_run("run-api-invalid")
        client = server.app.test_client()
        with mock.patch.object(
            server, "_process_library_service", return_value=self.service
        ):
            response = client.post(
                "/api/process-runs/run-api-invalid/lifecycle",
                json={
                    "disposition": "preserve",
                    "idempotency_key": "lifecycle:api:invalid",
                    "delete_files": True,
                },
            )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(response.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
