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
        locks = mp.capture_project_binding("project", routing_config={
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

    def test_tampered_project_snapshot_fails_closed(self):
        record = self._binding_record()
        record["model_locks"]["profile_snapshot"]["cells"]["utility"][
            "step1_cleanup"]["primary"] = "changed"
        with mock.patch.object(mp.pm, "read_project_meta", return_value=record):
            with self.assertRaisesRegex(mp.ModelProfileError, "snapshot digest"):
                mp.resolve_effective_profile(
                    global_profile="global", project_nexus="my-project")

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

    def test_receipt_failure_rolls_back_the_profile(self):
        before = copy.deepcopy(self.current)
        proposal = mp.preview_migration("legacy")
        with mock.patch.object(mp, "_append_receipt", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(mp.ModelProfileError, "rolled back"):
                mp.confirm_migration(
                    "legacy", proposal["proposal_id"], user_confirmed=True)
        self.assertEqual(self.current, before)
        self.assertEqual(len(self.saved), 2)  # proposed write, then exact rollback

    def test_project_migration_replaces_the_locked_snapshot_not_the_live_source(self):
        locks = {
            "schema_version": mp.LOCK_SCHEMA_VERSION,
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


if __name__ == "__main__":
    unittest.main()
