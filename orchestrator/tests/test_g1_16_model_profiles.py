"""G1.16 Model Profile authority, inheritance, health, and migration proofs."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from textwrap import dedent
from unittest import mock

from orchestrator import framework_parser
from orchestrator import model_profiles as mp


def profile(*model_ids: str) -> dict:
    ids = list(model_ids) or ["model-ok"]
    primary = ids[0]
    fallback = ids[1:]
    return {
        "name": "synthetic",
        "toggles": {"adversarial_diversity": False},
        "cells": {
            "utility": {
                "step1_cleanup": {"primary": primary, "fallback": fallback},
            },
            "analysis": {
                "gear4": {"depth": {"primary": primary, "fallback": fallback}},
                "gear3": {"depth": {"primary": primary, "fallback": fallback}},
            },
        },
    }


def inventory(records: dict[str, dict], aliases: dict[str, str] | None = None) -> dict:
    return {"models": records, "aliases": aliases or {}, "routing": {}}


class ModelProfileHealthTests(unittest.TestCase):
    def test_all_four_health_states_are_machine_readable(self):
        ok = mp.evaluate_profile_health(
            profile("ok"), inventory({"ok": {"reachable": True}}))
        degraded = mp.evaluate_profile_health(
            profile("uncertain", "ok"),
            inventory({"uncertain": {}, "ok": {"reachable": True}}),
        )
        deprecated = mp.evaluate_profile_health(
            profile("retired", "ok"), inventory({"ok": {"reachable": True}}))
        unavailable = mp.evaluate_profile_health(
            profile("down"), inventory({"down": {"reachable": False}}))
        self.assertEqual(
            [ok["status"], degraded["status"], deprecated["status"], unavailable["status"]],
            ["ok", "degraded", "deprecated", "unavailable"],
        )

    def test_exact_alias_is_not_mislabeled_deprecated(self):
        health = mp.evaluate_profile_health(
            profile("issued-old"),
            inventory({"issued-new": {"reachable": True}}, {"issued-old": "issued-new"}),
        )
        self.assertEqual(health["status"], "ok")


class ModelProfileInheritanceTests(unittest.TestCase):
    def setUp(self):
        self.profiles = {
            name: profile("ok")
            for name in ("global", "project", "process", "step", "one-run")
        }
        self.inv = inventory({"ok": {"reachable": True}})
        self.read_patch = mock.patch.object(
            mp, "_read_profile", side_effect=lambda name: copy.deepcopy(self.profiles[name]))
        self.inventory_patch = mock.patch.object(mp, "load_model_inventory", return_value=self.inv)
        self.toggle_patch = mock.patch.object(
            mp.ac, "get_toggles", return_value={"adversarial_diversity": False})
        self.active_patch = mock.patch.object(mp.ac, "get_active_name", return_value="global")
        self.read_patch.start(); self.inventory_patch.start(); self.toggle_patch.start()
        self.active_patch.start()

    def tearDown(self):
        mock.patch.stopall()

    def _binding_record(self):
        locks = mp.capture_project_binding("project", "my-project", routing_config={
            "slots": {
                "image_generates": {"preferred": "image-locked"},
                "image_extracts": {"preferred": "extract-locked"},
                "vision_input": {"preferred": "vision-locked"},
            },
            "vision_extraction": {"enabled": False, "mode": "locked"},
        })
        return {"default_model_profile": "project", "model_locks": locks}

    def test_five_level_precedence_is_exact_and_complete(self):
        record = self._binding_record()
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            result = mp.resolve_effective_profile(
                global_profile="global", project_nexus="my-project",
                process_profile="process", step_profile="step",
                one_run_profile="one-run",
            )
        self.assertEqual(
            [row["source"] for row in result["chain"]],
            ["global", "project", "process", "step", "one_run"],
        )
        self.assertEqual(result["selected"]["name"], "one-run")

    def test_each_closer_level_overrides_only_the_levels_before_it(self):
        record = self._binding_record()
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            project = mp.resolve_effective_profile(
                global_profile="global", project_nexus="my-project")
            process = mp.resolve_effective_profile(
                global_profile="global", project_nexus="my-project",
                process_profile="process")
            step = mp.resolve_effective_profile(
                global_profile="global", project_nexus="my-project",
                process_profile="process", step_profile="step")
        self.assertEqual(project["selected"]["source"], "project")
        self.assertEqual(process["selected"]["source"], "process")
        self.assertEqual(step["selected"]["source"], "step")

    def test_project_snapshot_survives_source_profile_change(self):
        record = self._binding_record()
        original_digest = record["model_locks"]["profile_digest"]
        self.profiles["project"] = profile("different-live-model")
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            token = mp.resolve_effective_profile(
                global_profile="global", project_nexus="my-project",
            )["selected"]["runtime_name"]
            locked = mp.load_project_locked_profile(token)
        self.assertEqual(mp.profile_digest(locked), original_digest)
        self.assertNotEqual(mp.profile_digest(self.profiles["project"]), original_digest)

    def test_existing_over_cap_project_snapshot_cannot_activate(self):
        snapshot = profile("cloud-model")
        snapshot["roles"] = {
            "project-model": {
                "primary": "local-too-large", "fallback": [],
            },
        }
        snapshot["cells"]["utility"]["step1_cleanup"] = {
            "role": "project-model",
        }
        locks = {
            "schema_version": mp.LOCK_SCHEMA_VERSION,
            "project_nexus": "my-project",
            "profile_name": "project",
            "profile_digest": mp.profile_digest(snapshot),
            "profile_snapshot": snapshot,
            "toggles": {"adversarial_diversity": False},
            "image_model": None,
            "vision_mode": {},
            "captured_at": "2026-08-14T00:00:00+00:00",
        }
        locks["binding_digest"] = mp._binding_digest(locks)
        record = {"default_model_profile": "project", "model_locks": locks}
        with (
            mock.patch.object(mp.pm, "read_project_meta", return_value=record),
            mock.patch.object(mp.ac, "_get_system_ram_gb", return_value=100),
            mock.patch.object(mp.ac, "_load_local_models", return_value=[
                {"id": "local-too-large", "ram_gb": 86},
            ]),
        ):
            with self.assertRaisesRegex(mp.ModelProfileError, "85% hard cap"):
                mp.resolve_effective_profile(
                    global_profile="global", project_nexus="my-project",
                )

    def test_tampered_project_snapshot_fails_closed(self):
        record = self._binding_record()
        record["model_locks"]["profile_snapshot"]["cells"]["utility"][
            "step1_cleanup"]["primary"] = "changed"
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            with self.assertRaisesRegex(mp.ModelProfileError, "snapshot digest"):
                mp.resolve_effective_profile(
                    global_profile="global", project_nexus="my-project")

    def test_project_identity_prevents_cross_project_lock_replay(self):
        record = self._binding_record()
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            token = mp.project_lock_token("my-project", record["model_locks"])
            self.assertEqual(
                mp.profile_digest(mp.load_project_locked_profile(token)),
                record["model_locks"]["profile_digest"],
            )
            with self.assertRaisesRegex(mp.ModelProfileError, "identity"):
                mp.validate_project_binding(record, expected_nexus="other-project")
            with self.assertRaisesRegex(mp.ModelProfileError, "identity"):
                mp.project_lock_token("other-project", record["model_locks"])

    def test_same_profile_rebind_invalidates_old_full_binding_token(self):
        record = self._binding_record()
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            token = mp.project_lock_token("my-project", record["model_locks"])
            rebound = mp.capture_project_binding(
                "project", "my-project", routing_config={
                    "slots": {
                        "image_generates": {"preferred": "different-image"},
                        "image_extracts": {"preferred": "extract-locked"},
                        "vision_input": {"preferred": "vision-locked"},
                    },
                    "vision_extraction": {"enabled": True, "mode": "changed"},
                },
            )
            record["model_locks"] = rebound
            with self.assertRaisesRegex(mp.ModelProfileError, "stale"):
                mp.load_project_locked_profile(token)

    def test_equal_content_profile_rename_invalidates_old_binding_token(self):
        record = self._binding_record()
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            token = mp.project_lock_token("my-project", record["model_locks"])
            renamed = mp.capture_project_binding(
                "process", "my-project", routing_config={
                    "slots": {
                        "image_generates": {"preferred": "image-locked"},
                        "image_extracts": {"preferred": "extract-locked"},
                        "vision_input": {"preferred": "vision-locked"},
                    },
                    "vision_extraction": {"enabled": False, "mode": "locked"},
                },
            )
            self.assertEqual(
                renamed["profile_digest"], record["model_locks"]["profile_digest"],
            )
            record["default_model_profile"] = "process"
            record["model_locks"] = renamed
            with self.assertRaisesRegex(mp.ModelProfileError, "stale"):
                mp.load_project_locked_profile(token)

    def test_visual_locks_replace_only_project_owned_visual_routes(self):
        locks = self._binding_record()["model_locks"]
        current = {
            "unrelated": {"keep": True},
            "slots": {
                "image_generates": {"preferred": "live-image", "fallback": ["keep"]},
                "image_extracts": {"preferred": "live-extract"},
                "vision_input": {"preferred": "live-vision"},
            },
            "vision_extraction": {"enabled": True},
        }
        result = mp.routing_config_with_project_locks(current, locks)
        self.assertEqual(result["slots"]["image_generates"]["preferred"], "image-locked")
        self.assertEqual(result["slots"]["image_generates"]["fallback"], ["keep"])
        self.assertEqual(result["vision_extraction"], {"enabled": False, "mode": "locked"})
        self.assertEqual(result["unrelated"], {"keep": True})

    def test_milestone_executor_passes_distinct_process_step_and_run_levels(self):
        from orchestrator.milestone_executor import _resolve_milestone_model_profile
        record = self._binding_record()
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            result = _resolve_milestone_model_profile(
                project_nexus="my-project",
                process_profile="process",
                milestone=SimpleNamespace(model_profile="step"),
                one_run_profile="one-run",
            )
        self.assertEqual(result["selected"]["source"], "one_run")
        self.assertEqual(
            [row["source"] for row in result["chain"]],
            ["global", "project", "process", "step", "one_run"],
        )

    def test_actual_framework_execution_receives_all_levels_and_visual_locks(self):
        from orchestrator import milestone_executor as executor

        framework = framework_parser.parse_framework_text(dedent("""\
            # Production profile proof

            ## LAYER 1: Work
            Produce the result.

            ## MILESTONES DELIVERED

            ### Milestone 1: Result
            - **Endpoint produced:** A result.
            - **Verification criterion:** It exists.
            - **Layers covered:** 1
            - **Required prior milestones:** None
            - **Gear:** 4
            - **Model Profile:** step
            - **Output format:** Markdown.
            - **Drift check question:** Is it complete?
        """), path="production-profile-proof.md")
        record = self._binding_record()
        observed = {}

        def run_gear4(context_pkg, _config, config_name=None, **_kwargs):
            observed["context_pkg"] = copy.deepcopy(context_pkg)
            observed["config_name"] = config_name
            return "authenticated deliverable"

        trace_context = {}
        with (
            mock.patch.object(mp.pm, "read_project_meta", return_value=record),
            mock.patch.object(executor, "parse_framework_file", return_value=framework),
            mock.patch.object(
                executor, "_lookup_framework_default_configuration",
                return_value="process",
            ),
            mock.patch("boot.run_gear4", side_effect=run_gear4),
            mock.patch.object(
                executor, "_run_drift_check",
                return_value=("IN_SCOPE", "verified"),
            ),
        ):
            result = executor.execute_framework(
                "production-profile-proof.md", "do the work", config={},
                project_nexus="my-project", config_name="one-run",
                trace_context=trace_context,
            )
        self.assertTrue(result.success)
        self.assertEqual(observed["config_name"], "one-run")
        self.assertEqual(
            observed["context_pkg"]["model_profile_locks"],
            record["model_locks"],
        )
        resolution = trace_context["model_profile_resolution"]
        self.assertEqual(
            [row["source"] for row in resolution["chain"]],
            ["global", "project", "process", "step", "one_run"],
        )

    def test_gear2_executor_uses_the_endpoint_from_each_effective_level(self):
        from orchestrator import milestone_executor as executor
        import boot

        framework = framework_parser.parse_framework_text(dedent("""\
            # Gear 2 profile proof

            ## LAYER 1: Work
            Produce the result.

            ## MILESTONES DELIVERED

            ### Milestone 1: Result
            - **Endpoint produced:** A result.
            - **Verification criterion:** It exists.
            - **Layers covered:** 1
            - **Required prior milestones:** None
            - **Gear:** 2
            - **Output format:** Markdown.
            - **Drift check question:** Is it complete?
        """), path="gear2-profile-proof.md")
        record = self._binding_record()
        project_token = mp.project_lock_token("my-project", record["model_locks"])
        cases = (
            ("project", None, None, None, project_token),
            ("process", "process", None, None, "process"),
            ("step", "process", "step", None, "step"),
            ("one-run", "process", "step", "one-run", "one-run"),
        )

        for label, process_profile, step_profile, one_run_profile, expected in cases:
            with self.subTest(level=label):
                framework.all_milestones()[0].model_profile = step_profile
                invoked = {}

                def slot_endpoint(_config, slot, *, config_name=None, **_kwargs):
                    invoked["slot"] = slot
                    invoked["resolved_config"] = config_name
                    return {"id": f"endpoint::{config_name}"}

                def run_model(_messages, endpoint, **_kwargs):
                    invoked["endpoint"] = endpoint["id"]
                    return "authenticated deliverable"

                trace_context = {}
                with (
                    mock.patch.object(mp.pm, "read_project_meta", return_value=record),
                    mock.patch.object(
                        executor, "parse_framework_file", return_value=framework),
                    mock.patch.object(
                        executor, "_lookup_framework_default_configuration",
                        return_value=process_profile,
                    ),
                    mock.patch.object(
                        executor, "_run_drift_check",
                        return_value=("IN_SCOPE", "verified"),
                    ),
                    mock.patch.object(
                        boot, "get_slot_endpoint", side_effect=slot_endpoint),
                    mock.patch.object(
                        boot, "get_active_endpoint",
                        side_effect=AssertionError(
                            "named Gear-2 execution used the global endpoint"),
                    ),
                    mock.patch.object(
                        boot, "_run_model_with_tools", side_effect=run_model),
                ):
                    result = executor.execute_framework(
                        "gear2-profile-proof.md", "do the work", config={},
                        project_nexus="my-project", config_name=one_run_profile,
                        trace_context=trace_context,
                    )

                self.assertTrue(result.success, result.final_output)
                self.assertEqual(invoked["slot"], "fast")
                self.assertEqual(invoked["resolved_config"], expected)
                self.assertEqual(invoked["endpoint"], f"endpoint::{expected}")
                self.assertEqual(
                    trace_context["model_profile_resolution"]["selected"][
                        "runtime_name"
                    ],
                    expected,
                )


class ModelProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.receipts = Path(self.temp.name) / "receipts.jsonl"
        self.current = profile("retired", "stable")
        self.saved = []
        self.inv = inventory({
            "stable": {"reachable": True, "provider": "vendor"},
            "replacement": {"reachable": True, "provider": "vendor"},
        })
        self.patches = [
            mock.patch.object(mp, "MIGRATION_RECEIPTS_PATH", self.receipts),
            mock.patch.object(mp, "load_model_inventory", return_value=self.inv),
            mock.patch.object(mp, "_read_profile", side_effect=lambda _name: copy.deepcopy(self.current)),
            mock.patch.object(
                mp.ac, "_save_config",
                side_effect=lambda _name, value: (self.saved.append(copy.deepcopy(value)), setattr(self, "current", copy.deepcopy(value))),
            ),
        ]
        for patcher in self.patches: patcher.start()

    def tearDown(self):
        mock.patch.stopall()
        self.temp.cleanup()

    def test_preview_is_read_only_and_confirmation_is_required(self):
        before = copy.deepcopy(self.current)
        proposal = mp.preview_migration("legacy")
        self.assertEqual(self.current, before)
        self.assertEqual(self.saved, [])
        with self.assertRaisesRegex(mp.ModelProfileError, "confirmation"):
            mp.confirm_migration(
                "legacy", proposal["proposal_id"], user_confirmed=False)
        self.assertEqual(self.current, before)
        self.assertFalse(self.receipts.exists())

    def test_confirm_binds_exact_proposal_and_retry_is_idempotent(self):
        proposal = mp.preview_migration("legacy")
        receipt = mp.confirm_migration(
            "legacy", proposal["proposal_id"], user_confirmed=True)
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(receipt["before_digest"], proposal["expected_digest"])
        self.assertEqual(receipt["after_digest"], proposal["proposed_digest"])
        retry = mp.confirm_migration(
            "legacy", proposal["proposal_id"], user_confirmed=True)
        self.assertEqual(retry, receipt)
        self.assertEqual(len(self.saved), 1)
        persisted = json.loads(self.receipts.read_text(encoding="utf-8").strip())
        self.assertEqual(persisted["proposal_id"], proposal["proposal_id"])

    def test_changed_profile_invalidates_preview(self):
        proposal = mp.preview_migration("legacy")
        self.current["description"] = "changed after review"
        with self.assertRaisesRegex(mp.ModelProfileError, "review a new proposal"):
            mp.confirm_migration(
                "legacy", proposal["proposal_id"], user_confirmed=True)
        self.assertEqual(self.saved, [])

    def test_over_cap_live_migration_is_rejected_before_profile_write(self):
        before = mp._canonical_json(self.current)
        proposal = mp.preview_migration("legacy")
        with (
            mock.patch.object(mp.ac, "_get_system_ram_gb", return_value=100),
            mock.patch.object(mp.ac, "_load_local_models", return_value=[
                {"id": "replacement", "ram_gb": 86},
            ]),
        ):
            with self.assertRaisesRegex(mp.ModelProfileError, "85% hard cap"):
                mp.confirm_migration(
                    "legacy", proposal["proposal_id"], user_confirmed=True,
                )
        self.assertEqual(mp._canonical_json(self.current), before)
        self.assertEqual(self.saved, [])
        self.assertFalse(self.receipts.exists())

    def test_over_cap_project_migration_is_rejected_before_binding_write(self):
        locks = {
            "schema_version": mp.LOCK_SCHEMA_VERSION,
            "project_nexus": "my-project",
            "profile_name": "Legacy",
            "profile_digest": mp.profile_digest(self.current),
            "profile_snapshot": copy.deepcopy(self.current),
            "toggles": {"adversarial_diversity": False},
            "image_model": None,
            "vision_mode": {},
            "captured_at": "2026-07-22T00:00:00+00:00",
        }
        locks["binding_digest"] = mp._binding_digest(locks)
        record = {"default_model_profile": "Legacy", "model_locks": locks}
        before = mp._canonical_json(record)
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            proposal = mp.preview_migration("Legacy", "my-project")

        with (
            mock.patch.object(mp.pm, "read_project_meta", return_value=record),
            mock.patch.object(mp.pm, "set_project_model_binding") as persist,
            mock.patch.object(mp.ac, "_get_system_ram_gb", return_value=100),
            mock.patch.object(mp.ac, "_load_local_models", return_value=[
                {"id": "replacement", "ram_gb": 86},
            ]),
        ):
            with self.assertRaisesRegex(mp.ModelProfileError, "85% hard cap"):
                mp.confirm_migration(
                    "Legacy", proposal["proposal_id"], user_confirmed=True,
                    project_nexus="my-project",
                )
        persist.assert_not_called()
        self.assertEqual(mp._canonical_json(record), before)
        self.assertFalse(self.receipts.exists())

    def test_receipt_failure_rolls_back_the_profile(self):
        before = copy.deepcopy(self.current)
        proposal = mp.preview_migration("legacy")
        with mock.patch.object(mp, "_append_receipt", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(mp.ModelProfileError, "rolled back"):
                mp.confirm_migration(
                    "legacy", proposal["proposal_id"], user_confirmed=True)
        self.assertEqual(self.current, before)
        self.assertEqual(len(self.saved), 2)  # proposed write, then exact rollback

    def test_forged_receipt_cannot_claim_an_unperformed_migration(self):
        proposal = mp.preview_migration("legacy")
        forged = {
            "schema_version": mp.MIGRATION_SCHEMA_VERSION,
            "receipt_id": "mpr-" + proposal["proposal_id"][:24],
            "proposal_id": proposal["proposal_id"],
            "target": "profile",
            "profile_name": "legacy",
            "project_nexus": None,
            "before_digest": proposal["expected_digest"],
            "after_digest": proposal["proposed_digest"],
            "replacements": proposal["replacements"],
            "user_confirmed": True,
            "recorded_at": "2026-07-22T00:00:00+00:00",
            "before_binding_digest": None,
            "after_binding_digest": None,
            "receipt_digest": "0" * 64,
        }
        self.receipts.write_text(json.dumps(forged) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(mp.ModelProfileError, "receipt digest"):
            mp.confirm_migration(
                "legacy", proposal["proposal_id"], user_confirmed=True,
            )
        self.assertEqual(self.saved, [])
        self.assertEqual(mp.profile_digest(self.current), proposal["expected_digest"])

    def test_well_formed_but_unperformed_receipt_fails_post_state(self):
        proposal = mp.preview_migration("legacy")
        forged = {
            "schema_version": mp.MIGRATION_SCHEMA_VERSION,
            "receipt_id": "mpr-" + proposal["proposal_id"][:24],
            "proposal_id": proposal["proposal_id"],
            "target": "profile", "profile_name": "legacy",
            "project_nexus": None,
            "before_digest": proposal["expected_digest"],
            "after_digest": proposal["proposed_digest"],
            "replacements": proposal["replacements"],
            "user_confirmed": True,
            "recorded_at": "2026-07-22T00:00:00+00:00",
            "before_binding_digest": None,
            "after_binding_digest": None,
        }
        forged["receipt_digest"] = mp._digest(forged)
        self.receipts.write_text(json.dumps(forged) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(mp.ModelProfileError, "post-state"):
            mp.confirm_migration(
                "legacy", proposal["proposal_id"], user_confirmed=True,
            )
        self.assertEqual(self.saved, [])

    def test_retry_reauthenticates_the_current_post_state(self):
        before = copy.deepcopy(self.current)
        proposal = mp.preview_migration("legacy")
        receipt = mp.confirm_migration(
            "legacy", proposal["proposal_id"], user_confirmed=True,
        )
        self.assertEqual(mp.profile_digest(self.current), receipt["after_digest"])
        self.current = before
        with self.assertRaisesRegex(mp.ModelProfileError, "post-state"):
            mp.confirm_migration(
                "legacy", proposal["proposal_id"], user_confirmed=True,
            )

    def test_project_migration_replaces_the_locked_snapshot_not_the_live_source(self):
        locks = {
            "schema_version": mp.LOCK_SCHEMA_VERSION,
            "project_nexus": "my-project",
            "profile_name": "Legacy",
            "profile_digest": mp.profile_digest(self.current),
            "profile_snapshot": copy.deepcopy(self.current),
            "toggles": {"adversarial_diversity": False},
            "image_model": "image-locked",
            "vision_mode": {},
            "captured_at": "2026-07-22T00:00:00+00:00",
        }
        locks["binding_digest"] = mp._binding_digest(locks)
        record = {"default_model_profile": "Legacy", "model_locks": locks}

        def persist(_nexus, name, new_locks):
            record["default_model_profile"] = name
            record["model_locks"] = copy.deepcopy(new_locks)
            return record

        with (
            mock.patch.object(mp.pm, "read_project_meta", return_value=record),
            mock.patch.object(mp.pm, "set_project_model_binding", side_effect=persist),
        ):
            proposal = mp.preview_migration("Legacy", "my-project")
            receipt = mp.confirm_migration(
                "Legacy", proposal["proposal_id"], user_confirmed=True,
                project_nexus="my-project",
            )
        self.assertEqual(receipt["target"], "project")
        self.assertEqual(self.saved, [])
        self.assertEqual(
            record["model_locks"]["profile_digest"], proposal["proposed_digest"])
        self.assertEqual(record["model_locks"]["image_model"], "image-locked")


class ModelProfilePersistenceTests(unittest.TestCase):
    def test_exact_project_binding_survives_write_and_reload(self):
        from orchestrator import project_meta
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pointers = root / "pointers"
            projects = root / "Projects"
            pointers.mkdir(); projects.mkdir()
            created = project_meta.create_project(
                "Bound Project", pointer_dir=pointers,
                vault_projects_dir=projects,
            )
            snapshot = profile("model-ok")
            locks = {
                "schema_version": mp.LOCK_SCHEMA_VERSION,
                "project_nexus": created["nexus"],
                "profile_name": "Balanced",
                "profile_digest": mp.profile_digest(snapshot),
                "profile_snapshot": snapshot,
                "toggles": {"adversarial_diversity": False},
                "image_model": "image-locked",
                "vision_mode": {"vision_extraction": {"enabled": False}},
                "captured_at": "2026-07-22T00:00:00+00:00",
            }
            locks["binding_digest"] = mp._binding_digest(locks)
            project_meta.set_project_model_binding(
                created["nexus"], "Balanced", locks, pointer_dir=pointers)
            reloaded = project_meta.read_project_meta(created["nexus"], pointers)
            validated = mp.validate_project_binding(
                reloaded, expected_nexus=created["nexus"])
            self.assertEqual(validated, locks)

    def test_generic_project_update_cannot_replace_runtime_locks(self):
        from orchestrator import project_meta
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pointers = root / "pointers"
            projects = root / "Projects"
            pointers.mkdir(); projects.mkdir()
            created = project_meta.create_project(
                "Guarded Project", pointer_dir=pointers,
                vault_projects_dir=projects,
            )
            project_meta.update_project_meta(created["nexus"], {
                "default_model_profile": "forged",
                "model_locks": {"binding_digest": "forged"},
            }, pointer_dir=pointers)
            reloaded = project_meta.read_project_meta(created["nexus"], pointers)
            self.assertIsNone(reloaded.get("default_model_profile"))
            self.assertEqual(reloaded.get("model_locks"), {})


class ModelProfileFrameworkTests(unittest.TestCase):
    def test_milestone_model_profile_is_parsed_as_step_override(self):
        parsed = framework_parser.parse_framework_text(dedent("""\
            # Profile-bound process

            ## LAYER 1: Work
            Do the work.

            ## MILESTONES DELIVERED

            ### Milestone 1: Result
            - **Endpoint produced:** A result.
            - **Verification criterion:** It exists.
            - **Layers covered:** 1
            - **Required prior milestones:** None
            - **Gear:** 4
            - **Model Profile:** step-specialist
            - **Output format:** Markdown.
            - **Drift check question:** Is it the requested result?
        """), path="profile-bound.md")
        self.assertEqual(parsed.all_milestones()[0].model_profile, "step-specialist")

    def test_interactive_elicitation_preserves_project_and_one_run_until_execution(self):
        from orchestrator import framework_elicitation as elicitation
        from orchestrator import milestone_executor as executor

        framework = framework_parser.parse_framework_text(dedent("""\
            # Interactive profile proof

            ## LAYER 1: Work
            Produce the result.

            ## MILESTONES DELIVERED

            ### Milestone 1: Result
            - **Endpoint produced:** A result.
            - **Verification criterion:** It exists.
            - **Layers covered:** 1
            - **Required prior milestones:** None
            - **Gear:** 4
            - **Model Profile:** step
            - **Output format:** Markdown.
            - **Drift check question:** Is it complete?
        """), path="interactive-profile-proof.md")
        marker = elicitation.elicitation_marker(
            framework.name, "all", "my-project", "one-run",
        )
        ctx = elicitation.is_continuation([
            {"role": "assistant", "content": "Question\n\n" + marker},
        ])
        self.assertEqual(ctx.project_nexus, "my-project")
        self.assertEqual(ctx.one_run_profile, "one-run")
        summary = elicitation._SummaryState(
            elicited_bullets=["The result is defined"], pending_bullets=[],
            action="PRODUCE_DELIVERABLE", next_question="",
        )
        result = executor.FrameworkExecutionResult(
            framework_name=framework.name, execution_id="exec", user_input="input",
            milestones=[], final_output="done", success=True,
        )
        with (
            mock.patch.object(elicitation, "parse_framework_file", return_value=framework),
            mock.patch.object(elicitation, "_ask_summarizer", return_value=summary),
            mock.patch("milestone_executor.execute_framework", return_value=result) as execute,
        ):
            text = elicitation.continue_elicitation(
                ctx, [], {}, latest_user_text="continue",
                current_project_nexus="my-project",
            )
        self.assertIn("done", text)
        self.assertEqual(execute.call_args.kwargs["project_nexus"], "my-project")
        self.assertEqual(execute.call_args.kwargs["config_name"], "one-run")


if __name__ == "__main__":
    unittest.main()
