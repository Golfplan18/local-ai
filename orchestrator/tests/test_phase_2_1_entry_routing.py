"""G1.1 Phase 2.1 — Ora-native entry and four-intent routing proofs."""

from __future__ import annotations

import copy
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

import boot  # noqa: E402
import process_entry_routing as entry  # noqa: E402
from server import server  # noqa: E402


PROGRAMMING_REF = {
    "definition_id": "ora/programming",
    "version": "2.0.1",
    "digest": "sha256:b79d06b401ca54ec62588ab9cd64393fc049d4cf599298a5b057d93aa4e2a927",
}


def _request(objective: str, **overrides):
    value = {
        "source": "inquiry",
        "objective": objective,
        "project_ref": "commons",
        "project_confirmed": False,
    }
    value.update(overrides)
    return value


class Phase21CatalogTests(unittest.TestCase):
    def test_programming_catalog_is_exact_and_not_activated(self):
        catalog = entry.list_entry_definitions(ROOT)
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["definition_ref"], PROGRAMMING_REF)
        self.assertEqual(catalog[0]["kind"], "process_definition")
        self.assertFalse(catalog[0]["activated"])
        self.assertEqual(catalog[0]["status"], "approved")

    def test_catalog_reauthenticates_projection_on_every_read(self):
        canonical = entry.list_entry_definitions(ROOT)[0]
        with mock.patch(
            "process_entry_routing._contracts.validate_process_definition",
            wraps=entry._contracts.validate_process_definition,
        ) as validate, mock.patch.object(
            entry.ProcessDefinitionRegistry,
            "_verify_issued_content_identity",
            wraps=entry.ProcessDefinitionRegistry._verify_issued_content_identity,
        ) as verify:
            again = entry.list_entry_definitions(ROOT)[0]
        self.assertEqual(again["definition_ref"], canonical["definition_ref"])
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(verify.call_count, 1)

    def test_tampered_catalog_identity_is_rejected_by_routing(self):
        catalog = entry.list_entry_definitions(ROOT)
        tampered = copy.deepcopy(catalog)
        tampered[0]["definition_ref"]["digest"] = "sha256:" + ("0" * 64)
        with self.assertRaises(entry.ProcessEntryRoutingError):
            entry.route_process_entry(
                _request(
                    "Run Programming",
                    source="shared_picker",
                    selected_definition_ref=PROGRAMMING_REF,
                ),
                catalog=tampered,
            )


class Phase21RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = entry.list_entry_definitions(ROOT)

    def route(self, request, visible=lambda _project: True):
        return entry.route_process_entry(
            request, catalog=self.catalog, project_visible=visible,
        )

    def test_ordinary_generation_stays_ordinary(self):
        result = self.route(_request("Create a concise summary of this report."))
        self.assertEqual(result["intent"], "ordinary_generation")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["next_action"], "submit_ordinary_generation")

    def test_one_off_spreadsheet_is_ordinary_but_reusable_one_is_construction(self):
        one_off = self.route(_request(
            "Create a spreadsheet for this cash-flow report."
        ))
        reusable = self.route(_request(
            "Build a reusable spreadsheet template for monthly cash-flow reports."
        ))
        self.assertEqual(one_off["intent"], "ordinary_generation")
        self.assertEqual(reusable["intent"], "capability_construction")
        self.assertEqual(reusable["status"], "awaiting_project_confirmation")

    def test_construction_language_requires_project_confirmation(self):
        result = self.route(_request("Build a reusable automation for this report."))
        self.assertEqual(result["intent"], "capability_construction")
        self.assertEqual(result["status"], "awaiting_project_confirmation")
        self.assertEqual(result["next_action"], "choose_project")

    def test_ordinary_language_automation_requires_project_confirmation(self):
        result = self.route(_request("Automate my weekly cash-flow report."))
        self.assertEqual(result["intent"], "capability_construction")
        self.assertEqual(result["classification_basis"], ["explicit automation request"])
        self.assertEqual(result["status"], "awaiting_project_confirmation")
        self.assertEqual(result["next_action"], "choose_project")

    def test_recurring_and_triggered_work_require_project_confirmation(self):
        requests = (
            "Email me the cash-flow report every Friday.",
            "Reconcile new invoices whenever they arrive.",
            "When a repository check fails, notify me.",
            "Back up this folder nightly.",
            "Prepare the cash-flow report each Monday.",
            "Check invoice totals every month.",
            "Review the repository every Friday.",
            "Set up a repeatable monthly cash-flow review.",
            "Arrange to email me the report each Friday.",
        )
        for objective in requests:
            with self.subTest(objective=objective):
                result = self.route(_request(objective))
                self.assertEqual(result["intent"], "capability_construction")
                self.assertEqual(
                    result["classification_basis"],
                    ["recurring or triggered work request"],
                )
                self.assertEqual(result["status"], "awaiting_project_confirmation")
                self.assertEqual(result["next_action"], "choose_project")
                self.assertFalse(result["project_confirmed"])

    def test_frequency_describing_one_input_is_not_automatically_recurring(self):
        result = self.route(_request("Summarize this weekly cash-flow report once."))
        self.assertEqual(result["intent"], "ordinary_generation")

    def test_recurring_or_automation_subject_matter_stays_ordinary(self):
        requests = (
            "Review what happens when a repository check fails.",
            "Check whether invoice totals change every month.",
            "Create a guide explaining how to automate weekly reports.",
        )
        for objective in requests:
            with self.subTest(objective=objective):
                result = self.route(_request(objective))
                self.assertEqual(result["intent"], "ordinary_generation")
                self.assertEqual(
                    result["classification_basis"],
                    ["explanatory or content request about work"],
                )
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["next_action"], "submit_ordinary_generation")

    def test_explicit_programming_action_is_construction(self):
        result = self.route(_request(
            "Make this repeatable.", source="construction_action",
        ))
        self.assertEqual(result["intent"], "capability_construction")
        self.assertEqual(result["status"], "awaiting_project_confirmation")

    def test_confirmed_construction_is_ready_for_later_interview_only(self):
        result = self.route(_request(
            "Implement a new API endpoint in the repository.",
            project_ref="ora", project_confirmed=True,
        ))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["next_action"], "begin_management_interview")
        self.assertFalse(result["creates_process_run"])
        self.assertEqual(result["authority_effects"], [])

    def test_confirmed_hidden_project_fails_closed(self):
        with self.assertRaisesRegex(entry.ProcessEntryRoutingError, "not available"):
            self.route(
                _request(
                    "Build a reusable automation.",
                    project_ref="archived-project", project_confirmed=True,
                ),
                visible=lambda _project: False,
            )

    def test_unconfirmed_hidden_project_cannot_poison_ready_membership(self):
        with self.assertRaisesRegex(entry.ProcessEntryRoutingError, "not available"):
            self.route(
                _request(
                    "Create a concise summary.",
                    project_ref="invented-project", project_confirmed=False,
                ),
                visible=lambda _project: False,
            )

    def test_direct_natural_language_programming_invocation_is_exact(self):
        result = self.route(_request(
            "Run Programming to verify this repository.",
            source="natural_language",
        ))
        self.assertEqual(result["intent"], "capability_invocation")
        self.assertEqual(result["definition_ref"], PROGRAMMING_REF)
        self.assertEqual(result["status"], "awaiting_activation")
        self.assertEqual(result["next_action"], "begin_activation_review")

    def test_named_capability_operation_cannot_fall_through_generation(self):
        requests = (
            "Have Programming verify this repository.",
            "Could Programming inspect these files?",
            "Ask Programming to review this patch.",
            "Have Programming handle this repository.",
            "Use Programming to review this patch.",
        )
        for objective in requests:
            with self.subTest(objective=objective):
                result = self.route(_request(objective, source="natural_language"))
                self.assertEqual(result["intent"], "capability_invocation")
                self.assertEqual(result["definition_ref"], PROGRAMMING_REF)
                self.assertEqual(result["status"], "awaiting_activation")
                self.assertEqual(result["next_action"], "begin_activation_review")

    def test_named_capability_availability_is_activation_review(self):
        result = self.route(_request(
            "Make Programming available for this project.",
            source="natural_language",
        ))
        self.assertEqual(result["intent"], "capability_activation")
        self.assertEqual(result["definition_ref"], PROGRAMMING_REF)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["next_action"], "begin_activation_review")
        self.assertEqual(result["authority_effects"], [])
        self.assertFalse(result["creates_process_run"])

    def test_named_capability_as_subject_matter_stays_ordinary(self):
        requests = (
            "Summarize the Programming framework.",
            "Review the Programming documentation.",
            "Compare Programming with Terrain Mapping.",
            "Explain how to use Programming.",
            "Use Programming as an example in the guide.",
            "Run a comparison of Programming for the guide.",
            "Use Programming’s documentation to explain the model.",
            "Use the Programming guide to explain the model.",
        )
        for objective in requests:
            with self.subTest(objective=objective):
                result = self.route(_request(objective, source="natural_language"))
                self.assertEqual(result["intent"], "ordinary_generation")
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["next_action"], "submit_ordinary_generation")
                self.assertIsNone(result["definition_ref"])
                self.assertIsNone(result["framework_id"])

    def test_direct_natural_language_legacy_framework_invocation_is_ready(self):
        result = self.route(_request(
            "Run Terrain Mapping on this decision.",
            source="natural_language",
        ))
        self.assertEqual(result["intent"], "capability_invocation")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["framework_id"], "terrain-mapping")
        self.assertIsNone(result["definition_ref"])

    def test_direct_natural_language_framework_alias_resolves(self):
        result = self.route(_request(
            "Use PFF on this draft.",
            source="natural_language",
        ))
        self.assertEqual(result["intent"], "capability_invocation")
        self.assertEqual(result["framework_id"], "process-formalization")

    def test_direct_named_activation_is_separate(self):
        result = self.route(_request(
            "Activate Programming for this project.",
            source="natural_language",
        ))
        self.assertEqual(result["intent"], "capability_activation")
        self.assertEqual(result["definition_ref"], PROGRAMMING_REF)
        self.assertEqual(result["next_action"], "begin_activation_review")
        self.assertEqual(result["authority_effects"], [])

    def test_named_modification_is_construction_not_invocation(self):
        result = self.route(_request(
            "Modify Programming for a new repository policy.",
            source="natural_language",
        ))
        self.assertEqual(result["intent"], "capability_construction")
        self.assertEqual(result["status"], "awaiting_project_confirmation")

    def test_unknown_invocation_asks_for_definition(self):
        result = self.route(_request("Run the deployment workflow now."))
        self.assertEqual(result["intent"], "capability_invocation")
        self.assertEqual(result["status"], "awaiting_definition_selection")
        self.assertIsNone(result["definition_ref"])

    def test_shared_picker_requires_exact_definition_identity(self):
        with self.assertRaisesRegex(entry.ProcessEntryRoutingError, "requires an exact"):
            self.route(_request("Use this process.", source="shared_picker"))
        result = self.route(_request(
            "Use this process.",
            source="shared_picker",
            selected_definition_ref=PROGRAMMING_REF,
        ))
        self.assertEqual(result["intent"], "capability_invocation")
        self.assertEqual(result["definition_ref"], PROGRAMMING_REF)
        self.assertEqual(result["status"], "awaiting_activation")

    def test_shared_legacy_framework_picker_is_capability_invocation(self):
        result = self.route(_request(
            "Map the terrain for this decision.",
            source="shared_picker",
            selected_framework_id="terrain-mapping",
        ))
        self.assertEqual(result["intent"], "capability_invocation")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["framework_id"], "terrain-mapping")
        self.assertIsNone(result["definition_ref"])

    def test_shared_picker_rejects_unregistered_framework(self):
        with self.assertRaisesRegex(entry.ProcessEntryRoutingError, "not available"):
            self.route(_request(
                "Use it.",
                source="shared_picker",
                selected_framework_id="made-up-framework",
            ))

    def test_framework_and_process_definition_cannot_both_be_selected(self):
        with self.assertRaisesRegex(entry.ProcessEntryRoutingError, "not both"):
            self.route(_request(
                "Use it.",
                source="shared_picker",
                selected_definition_ref=PROGRAMMING_REF,
                selected_framework_id="terrain-mapping",
            ))

    def test_process_library_requires_exact_definition_identity(self):
        with self.assertRaisesRegex(entry.ProcessEntryRoutingError, "requires an exact"):
            self.route(_request("Use it.", source="process_library"))

    def test_wrong_version_or_digest_is_rejected(self):
        for key, replacement in (
            ("version", "2.0.0"),
            ("digest", "sha256:" + ("a" * 64)),
        ):
            ref = dict(PROGRAMMING_REF)
            ref[key] = replacement
            with self.subTest(key=key), self.assertRaisesRegex(
                entry.ProcessEntryRoutingError, "not available at that exact identity",
            ):
                self.route(_request(
                    "Use Programming.",
                    source="shared_picker",
                    selected_definition_ref=ref,
                ))

    def test_user_cannot_supply_technical_form_or_authority(self):
        for forbidden in (
            "technical_form",
            "intent",
            "status",
            "activated",
            "authority_effects",
            "creates_process_run",
        ):
            request = _request("Build a reusable tool.")
            request[forbidden] = "app"
            with self.subTest(field=forbidden), self.assertRaisesRegex(
                entry.ProcessEntryRoutingError, "unsupported process entry fields",
            ):
                self.route(request)

    def test_contract_digest_is_deterministic_and_content_sensitive(self):
        request = _request("Create a concise summary.")
        first = self.route(request)
        second = self.route(copy.deepcopy(request))
        changed = self.route(_request("Create a detailed summary."))
        self.assertEqual(first["contract_digest"], second["contract_digest"])
        self.assertNotEqual(first["contract_digest"], changed["contract_digest"])


class Phase21ServerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = server.app.test_client()

    def test_entry_route_endpoint_is_side_effect_free(self):
        response = self.client.post("/api/process-entry/route", json=_request(
            "Build a reusable automation.",
        ))
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["entry"]["status"], "awaiting_project_confirmation")
        self.assertFalse(payload["entry"]["creates_process_run"])
        self.assertEqual(payload["entry"]["authority_effects"], [])

    def test_entry_route_rejects_caller_classification(self):
        request = _request("Build a reusable automation.")
        request["intent"] = "ordinary_generation"
        response = self.client.post("/api/process-entry/route", json=request)
        self.assertEqual(response.status_code, 400)

    def test_process_library_endpoint_returns_authenticated_exact_identity(self):
        response = self.client.get("/api/process-library/entries")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["definitions"][0]["definition_ref"], PROGRAMMING_REF)
        self.assertFalse(payload["definitions"][0]["activated"])

    def test_catalog_integrity_failure_is_service_unavailable_not_empty_success(self):
        with mock.patch.object(
            server, "_process_entry_catalog", side_effect=RuntimeError("identity drift"),
        ):
            library = self.client.get("/api/process-library/entries")
        self.assertEqual(library.status_code, 503)
        self.assertFalse(library.get_json()["ok"])

        with mock.patch.object(
            server, "list_pickable_frameworks", side_effect=RuntimeError("identity drift"),
        ):
            picker = self.client.get("/api/frameworks/picker")
        self.assertEqual(picker.status_code, 503)
        self.assertEqual(picker.get_json()["frameworks"], [])

    def test_omitted_client_entry_cannot_bypass_project_gate(self):
        result = server._decode_process_entry_request(
            None, "Automate my weekly cash-flow report.", "",
        )
        self.assertEqual(result["source"], "natural_language")
        self.assertEqual(result["intent"], "capability_construction")
        self.assertEqual(result["status"], "awaiting_project_confirmation")

    def test_programming_picker_omission_is_server_reconstructed(self):
        result = server._decode_process_entry_request(
            None, "Use Programming to verify this repository.", "programming",
        )
        self.assertEqual(result["source"], "shared_picker")
        self.assertEqual(result["definition_ref"], PROGRAMMING_REF)
        self.assertEqual(result["intent"], "capability_invocation")
        self.assertEqual(result["status"], "awaiting_activation")

    def test_legacy_framework_picker_omission_is_server_reconstructed(self):
        result = server._decode_process_entry_request(
            None, "Map the terrain for this decision.", "terrain-mapping",
        )
        self.assertEqual(result["source"], "shared_picker")
        self.assertEqual(result["framework_id"], "terrain-mapping")
        self.assertEqual(result["intent"], "capability_invocation")

    def test_client_preview_objective_must_equal_submitted_inquiry(self):
        with self.assertRaisesRegex(entry.ProcessEntryRoutingError, "must match"):
            server._decode_process_entry_request(
                _request("Build one thing."), "Build something else.", "",
            )

    def test_chat_rejects_unconfirmed_direct_construction_before_pipeline(self):
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-1",
        ), mock.patch.object(
            server, "_delete_pending_submission",
        ) as delete, mock.patch.object(
            server, "_invoke_pipeline",
        ) as invoke:
            response = self.client.post("/chat", json={
                "message": "Automate my weekly cash-flow report.",
                "conversation_id": "phase-2-1-test",
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["entry"]["status"],
                         "awaiting_project_confirmation")
        delete.assert_called_once_with("submission-1")
        invoke.assert_not_called()

    def test_chat_rejects_unconfirmed_recurring_work_before_pipeline(self):
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-recurring",
        ), mock.patch.object(
            server, "_delete_pending_submission",
        ) as delete, mock.patch.object(
            server, "_invoke_pipeline",
        ) as invoke:
            response = self.client.post("/chat", json={
                "message": "Email me the cash-flow report every Friday.",
                "conversation_id": "phase-2-1-test",
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["entry"]["intent"],
                         "capability_construction")
        self.assertEqual(response.get_json()["entry"]["status"],
                         "awaiting_project_confirmation")
        delete.assert_called_once_with("submission-recurring")
        invoke.assert_not_called()

    def test_chat_rejects_effect_establishing_setup_and_arrangement(self):
        requests = (
            "Set up a repeatable monthly cash-flow review.",
            "Arrange to email me the report each Friday.",
        )
        for index, objective in enumerate(requests):
            with self.subTest(objective=objective), mock.patch.object(
                server, "_log_pending_submission", return_value=f"submission-setup-{index}",
            ), mock.patch.object(
                server, "_delete_pending_submission",
            ) as delete, mock.patch.object(
                server, "_invoke_pipeline",
            ) as invoke:
                response = self.client.post("/chat", json={
                    "message": objective,
                    "conversation_id": "phase-2-1-setup-test",
                })
            self.assertEqual(response.status_code, 409)
            contract = response.get_json()["entry"]
            self.assertEqual(contract["intent"], "capability_construction")
            self.assertEqual(contract["status"], "awaiting_project_confirmation")
            self.assertEqual(contract["next_action"], "choose_project")
            delete.assert_called_once_with(f"submission-setup-{index}")
            invoke.assert_not_called()

    def test_chat_cannot_invoke_unactivated_programming_definition(self):
        requests = (
            "Have Programming verify this repository.",
            "Use Programming to review this patch.",
        )
        for index, objective in enumerate(requests):
            with self.subTest(objective=objective), mock.patch.object(
                server, "_log_pending_submission", return_value=f"submission-invoke-{index}",
            ), mock.patch.object(
                server, "_delete_pending_submission",
            ) as delete, mock.patch.object(
                server, "_invoke_pipeline",
            ) as invoke:
                response = self.client.post("/chat", json={
                    "message": objective,
                    "conversation_id": "phase-2-1-test",
                })
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.get_json()["entry"]["status"],
                             "awaiting_activation")
            delete.assert_called_once_with(f"submission-invoke-{index}")
            invoke.assert_not_called()

    def test_chat_routes_named_availability_to_activation_review(self):
        response_value = server._json_response({"status": "ok"})
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-activation",
        ), mock.patch.object(
            server, "_invoke_pipeline", return_value=response_value,
        ) as invoke:
            response = self.client.post("/chat", json={
                "message": "Make Programming available for this project.",
                "conversation_id": "phase-2-1-test",
            })
        self.assertEqual(response.status_code, 200)
        contract = invoke.call_args.kwargs["extra_context"]["process_entry"]
        self.assertEqual(contract["intent"], "capability_activation")
        self.assertEqual(contract["definition_ref"], PROGRAMMING_REF)
        self.assertEqual(contract["next_action"], "begin_activation_review")
        self.assertEqual(contract["authority_effects"], [])
        self.assertFalse(contract["creates_process_run"])

    def test_chat_allows_automation_and_recurrence_explanations(self):
        requests = (
            "Review what happens when a repository check fails.",
            "Check whether invoice totals change every month.",
            "Create a guide explaining how to automate weekly reports.",
        )
        for index, objective in enumerate(requests):
            response_value = server._json_response({"status": "ok"})
            with self.subTest(objective=objective), mock.patch.object(
                server, "_log_pending_submission", return_value=f"submission-content-{index}",
            ), mock.patch.object(
                server, "_invoke_pipeline", return_value=response_value,
            ) as invoke:
                response = self.client.post("/chat", json={
                    "message": objective,
                    "conversation_id": "phase-2-1-content-test",
                })
            self.assertEqual(response.status_code, 200)
            contract = invoke.call_args.kwargs["extra_context"]["process_entry"]
            self.assertEqual(contract["intent"], "ordinary_generation")
            self.assertEqual(contract["status"], "ready")
            self.assertEqual(contract["next_action"], "submit_ordinary_generation")

    def test_chat_allows_programming_subject_matter_as_ordinary(self):
        requests = (
            "Summarize the Programming framework.",
            "Review the Programming documentation.",
            "Use Programming as an example in the guide.",
            "Run a comparison of Programming for the guide.",
            "Use Programming’s documentation to explain the model.",
            "Use the Programming guide to explain the model.",
        )
        for index, objective in enumerate(requests):
            response_value = server._json_response({"status": "ok"})
            with self.subTest(objective=objective), mock.patch.object(
                server, "_log_pending_submission", return_value=f"submission-docs-{index}",
            ), mock.patch.object(
                server, "_invoke_pipeline", return_value=response_value,
            ) as invoke:
                response = self.client.post("/chat", json={
                    "message": objective,
                    "conversation_id": "phase-2-1-content-test",
                })
            self.assertEqual(response.status_code, 200)
            contract = invoke.call_args.kwargs["extra_context"]["process_entry"]
            self.assertEqual(contract["intent"], "ordinary_generation")
            self.assertEqual(contract["status"], "ready")
            self.assertIsNone(contract["definition_ref"])
            self.assertIsNone(contract["framework_id"])

    def test_chat_threads_direct_natural_language_framework_invocation(self):
        response_value = server._json_response({"status": "ok"})
        with mock.patch.object(
            server, "_log_pending_submission", return_value="submission-3",
        ), mock.patch.object(
            server, "_invoke_pipeline", return_value=response_value,
        ) as invoke:
            response = self.client.post("/chat", json={
                "message": "Run Terrain Mapping on this decision.",
                "conversation_id": "phase-2-1-test",
            })
        self.assertEqual(response.status_code, 200)
        kwargs = invoke.call_args.kwargs
        self.assertEqual(kwargs["framework_selected"], "terrain-mapping")
        self.assertEqual(
            kwargs["extra_context"]["process_entry"]["framework_id"],
            "terrain-mapping",
        )


class Phase21PromptAndSurfaceTests(unittest.TestCase):
    def test_routing_contract_is_injected_into_every_pipeline_role(self):
        mode_text = (
            "## DEPTH ANALYSIS GUIDANCE\n\nDepth.\n\n"
            "## BREADTH ANALYSIS GUIDANCE\n\nBreadth.\n\n"
            "## ANALYTICAL BRIEF AND EVALUATION CRITERIA\n\nBrief.\n\n"
            "## REVISION GUIDANCE\n\nRevise.\n\n"
            "## CONSOLIDATION GUIDANCE\n\nConsolidate.\n\n"
            "## VERIFICATION CRITERIA\n\nVerify.\n\n"
            "## OUTPUT FORMAT GUIDANCE\n\nFormat.\n"
        )
        contract = entry.route_process_entry(
            _request("Create a concise summary."),
            catalog=entry.list_entry_definitions(ROOT),
        )
        context = {
            "mode_text": mode_text,
            "mode_name": "phase-2-1-test",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
            "process_entry": contract,
        }
        for role in ("analyst", "evaluator", "reviser", "verifier", "consolidator", "formatter"):
            with self.subTest(role=role):
                prompt = boot.build_system_prompt_for_gear(context, step=role)
                self.assertIn("GOVERNED PROCESS ENTRY (ROUTING EVIDENCE ONLY)", prompt)
                self.assertIn(contract["contract_digest"], prompt)
                self.assertIn("creates no Process Run", prompt)

    def test_index_exposes_all_five_entry_surfaces_without_technical_form_question(self):
        html = (ROOT / "server" / "index-v3.html").read_text(encoding="utf-8")
        self.assertIn('placeholder="What should happen?"', html)
        self.assertIn('id="inputToolbarProgramming"', html)
        self.assertIn('id="inputToolbarFramework"', html)
        self.assertIn('id="sidebarProcessLibraryOpen"', html)
        self.assertIn('/static/js/process-entry.js', html)
        self.assertNotIn('What technical form should', html)


if __name__ == "__main__":
    unittest.main()
