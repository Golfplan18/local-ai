#!/usr/bin/env python3
"""A/V Phase 9 — user settings persistence + endpoint tests.

Two layers:
  1. ``user_settings`` module — load/save/reset, deep-merge, validation,
     API-key keyring shim with stubbed keyring backend.
  2. Flask endpoints — GET /api/settings, POST /api/settings,
     POST/DELETE /api/settings/api-key.

The keyring is monkey-patched at the module level so tests don't read
or write the real macOS Keychain.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
REPO = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))


class _FakeKeyring:
    """In-memory replacement for the keyring module."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, value: str) -> None:
        self.store[(service, username)] = value

    def get_password(self, service: str, username: str):
        return self.store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) in self.store:
            del self.store[(service, username)]
        else:
            raise Exception("not found")


class UserSettingsModuleTests(unittest.TestCase):

    def setUp(self):
        import user_settings
        self._mod = user_settings
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)

        # Redirect persistence to a tmp file.
        self._saved_path = self._mod._SETTINGS_PATH
        self._mod._SETTINGS_PATH = self._tmp_path / "user-settings.json"
        self._saved_dir = self._mod._CONFIG_DIR
        self._mod._CONFIG_DIR = self._tmp_path

        # Stub keyring at the module level.
        self._fake_keyring = _FakeKeyring()
        self._keyring_patch = mock.patch.dict(
            sys.modules, {"keyring": self._fake_keyring}
        )
        self._keyring_patch.start()

    def tearDown(self):
        self._mod._SETTINGS_PATH = self._saved_path
        self._mod._CONFIG_DIR = self._saved_dir
        self._keyring_patch.stop()
        self._tmp.cleanup()

    def test_load_returns_defaults_when_file_missing(self):
        s = self._mod.load_settings()
        self.assertEqual(s["whisper"]["model_size"], "large-v3")
        self.assertEqual(s["capture"]["frame_rate"], 30)
        self.assertEqual(
            s["aside"]["model_id"], "gemini/gemini-3.1-flash-lite")

    def test_save_then_load_roundtrip(self):
        self._mod.save_settings({
            "whisper": {"model_size": "medium"},
            "capture": {"frame_rate": 60},
        })
        s = self._mod.load_settings()
        self.assertEqual(s["whisper"]["model_size"], "medium")
        self.assertEqual(s["capture"]["frame_rate"], 60)
        # Other defaults still in place.
        self.assertEqual(s["whisper"]["default_language"], "auto")

    def test_settings_persistence_uses_runtime_home(self):
        relocated = self._tmp_path / "relocated-ora"
        settings_path = relocated / "config" / "user-settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({
            "capture": {"frame_rate": 24},
            "future_section": {"some_flag": True},
        }), encoding="utf-8")
        fake_home = self._tmp_path / "home"
        decoy = fake_home / "ora" / "config" / "user-settings.json"
        decoy.parent.mkdir(parents=True)
        decoy_bytes = b'{"capture": {"frame_rate": 50}, "decoy": true}\n'
        decoy.write_bytes(decoy_bytes)

        # A fresh interpreter resolves the real roots without setUp's patched
        # persistence constants or another test's imported runtime_paths.
        script = textwrap.dedent("""
            import sys
            from pathlib import Path
            sys.path.insert(0, sys.argv[1])
            import runtime_paths
            import user_settings

            expected = Path(sys.argv[2])
            assert runtime_paths.CONFIG_DIR == expected.parent
            assert user_settings._SETTINGS_PATH == expected
            loaded = user_settings.load_settings()
            assert loaded["capture"]["frame_rate"] == 24
            assert "decoy" not in loaded
            saved = user_settings.save_settings({"capture": {"frame_rate": 60}})
            assert saved["future_section"]["some_flag"] is True
            loaded = user_settings.load_settings()
            assert loaded["capture"]["frame_rate"] == 60
            assert loaded["future_section"]["some_flag"] is True
            assert expected.is_file()
            assert user_settings.reset_settings() == user_settings.DEFAULTS
            assert not expected.exists()
            assert user_settings.load_settings() == user_settings.DEFAULTS
        """)
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(ORCHESTRATOR),
             str(settings_path)],
            env={**os.environ, "ORA_HOME": str(relocated),
                 "HOME": str(fake_home), "USERPROFILE": str(fake_home)},
            cwd=REPO, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(decoy.read_bytes(), decoy_bytes)

    def test_partial_update_doesnt_clobber_other_sections(self):
        self._mod.save_settings({"whisper": {"model_size": "small"}})
        self._mod.save_settings({"capture": {"frame_rate": 24}})
        s = self._mod.load_settings()
        self.assertEqual(s["whisper"]["model_size"], "small")
        self.assertEqual(s["capture"]["frame_rate"], 24)

    def test_unknown_keys_preserved_on_roundtrip(self):
        # Forward compatibility: a future server adds a new field;
        # an older server must not silently drop it on save.
        self._mod._write_raw({
            "future_section": {"some_flag": True},
            "whisper": {"model_size": "small"},
        })
        s = self._mod.load_settings()
        self.assertEqual(s["future_section"]["some_flag"], True)
        # Saving a different section should preserve it.
        self._mod.save_settings({"capture": {"frame_rate": 60}})
        s = self._mod.load_settings()
        self.assertEqual(s["future_section"]["some_flag"], True)

    def test_invalid_frame_rate_rejected(self):
        with self.assertRaises(self._mod.SettingsError):
            self._mod.save_settings({"capture": {"frame_rate": 1000}})

    def test_invalid_whisper_model_rejected(self):
        with self.assertRaises(self._mod.SettingsError):
            self._mod.save_settings({"whisper": {"model_size": "huge"}})

    def test_invalid_render_threshold_rejected(self):
        with self.assertRaises(self._mod.SettingsError):
            self._mod.save_settings({
                "export": {"background_render_threshold_seconds": -1},
            })
        with self.assertRaises(self._mod.SettingsError):
            self._mod.save_settings({
                "export": {"background_render_threshold_seconds": 99999},
            })

    def test_aside_model_roundtrip_and_validation(self):
        self._mod.save_settings({"aside": {"model_id": "local-model"}})
        self.assertEqual(
            self._mod.load_settings()["aside"]["model_id"], "local-model")
        with self.assertRaises(self._mod.SettingsError):
            self._mod.save_settings({"aside": {"model_id": 42}})
        with self.assertRaises(self._mod.SettingsError):
            self._mod.save_settings({"aside": "not-an-object"})

    def test_no_aa_path_default(self):
        # Regression guard (2026-07-01): an "aa_path" DEFAULT here is
        # returned unconditionally by get_setting()'s deep merge, which
        # makes the sync script's key-presence auto-activation
        # unreachable — every sync scrapes even with an AA key
        # configured. The AA data path must stay auto-derived.
        self.assertNotIn("aa_path", self._mod.DEFAULTS["external_apis"])
        self.assertIsNone(self._mod.get_setting("external_apis.aa_path"))

    def test_reset_clears_overrides(self):
        self._mod.save_settings({"capture": {"frame_rate": 24}})
        self.assertEqual(self._mod.load_settings()["capture"]["frame_rate"], 24)
        self._mod.reset_settings()
        self.assertEqual(self._mod.load_settings()["capture"]["frame_rate"], 30)

    def test_get_setting_dotted_path(self):
        self._mod.save_settings({"whisper": {"model_size": "tiny"}})
        self.assertEqual(self._mod.get_setting("whisper.model_size"), "tiny")
        self.assertIsNone(self._mod.get_setting("whisper.nonexistent"))
        self.assertEqual(
            self._mod.get_setting("nope.also.nope", default="fallback"),
            "fallback",
        )

    def test_set_and_get_api_key_via_keyring_stub(self):
        self._mod._set_api_key_storage("anthropic", "secret123")
        self.assertTrue(self._mod.api_key_present("anthropic"))
        self.assertFalse(self._mod.api_key_present("openai"))
        self.assertEqual(
            self._fake_keyring.store[("ora", "anthropic-api-key")],
            "secret123",
        )

    def test_public_credential_mutation_requires_active_protection_receipt(self):
        from orchestrator.system_protection import ProtectionDenied

        with self.assertRaises(ProtectionDenied):
            self._mod.set_api_key("anthropic", "secret123")
        self.assertFalse(self._mod.api_key_present("anthropic"))
        with self.assertRaises(ProtectionDenied):
            self._mod.delete_api_key("anthropic")

    def test_artificial_analysis_provider_registered(self):
        # Key writes to ora/aa-api-key under the keyring service.
        self._mod._set_api_key_storage("artificial_analysis", "aa_secret_value")
        self.assertTrue(self._mod.api_key_present("artificial_analysis"))
        self.assertEqual(
            self._fake_keyring.store[("ora", "aa-api-key")],
            "aa_secret_value",
        )

    def test_delete_api_key_removes_from_keyring(self):
        self._mod._set_api_key_storage("anthropic", "secret123")
        self._mod._delete_api_key_storage("anthropic")
        self.assertFalse(self._mod.api_key_present("anthropic"))

    def test_delete_missing_key_is_noop(self):
        # Should not raise even though the key was never set.
        self._mod._delete_api_key_storage("anthropic")
        self.assertFalse(self._mod.api_key_present("anthropic"))

    def test_unknown_provider_rejected(self):
        with self.assertRaises(self._mod.SettingsError):
            self._mod.set_api_key("not-a-real-provider", "x")

    def test_empty_value_rejected(self):
        with self.assertRaises(self._mod.SettingsError):
            self._mod.set_api_key("anthropic", "")

    def test_every_provider_row_states_how_its_key_is_used(self):
        """Set/Not set alone could not answer "is this billing me per call?"."""
        rows = {r["provider"]: r for r in self._mod.list_api_key_status()}
        for provider, row in rows.items():
            self.assertTrue(row.get("transport"),
                            f"{provider} row states no transport")
            self.assertIn("metered", row["transport"],
                          f"{provider} transport omits the billing model")
        # A direct-dispatch vendor bills per token on the user's own key.
        self.assertIn("Direct calls", rows["minimax"]["transport"])
        # A provider with no direct dispatch rides OpenRouter.
        self.assertIn("OpenRouter", rows["openrouter"]["transport"])
        # Only the two providers with a subscription route can carry one, and
        # the key is None rather than absent so the panel can branch on it.
        for provider, row in rows.items():
            self.assertIn("subscription_transport", row)
            if provider not in ("anthropic", "openai"):
                self.assertIsNone(row["subscription_transport"],
                                  f"{provider} claims a subscription route")

    def test_minimax_claims_no_key_format(self):
        """MiniMax issues both eyJ… and sk-… keys.

        The panel warns when a pasted key does not match key_prefix, so
        naming either format told holders of the other that their working
        key was malformed.
        """
        rows = {r["provider"]: r for r in self._mod.list_api_key_status()}
        self.assertIsNone(rows["minimax"]["key_prefix"])

    def test_list_api_key_status_returns_all_providers(self):
        self._mod._set_api_key_storage("anthropic", "x")
        rows = self._mod.list_api_key_status()
        provider_ids = {r["provider"] for r in rows}
        self.assertIn("anthropic", provider_ids)
        self.assertIn("openai", provider_ids)
        self.assertIn("assemblyai", provider_ids)
        self.assertIn("deepgram", provider_ids)
        self.assertIn("elevenlabs", provider_ids)
        for r in rows:
            if r["provider"] == "anthropic":
                self.assertTrue(r["present"])
            elif r["provider"] == "openai":
                self.assertFalse(r["present"])
            self.assertIn("label", r)


class SettingsEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Resolve server.py from this checkout/worktree, not ~/ora. The latter
        # made endpoint tests preload the main checkout's user_settings module
        # and invalidated every worktree-side default/validation assertion.
        os.environ["ORA_HOME"] = str(REPO)
        sys.path.insert(0, str(REPO / "server"))
        try:
            from server import app as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as exc:
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(exc)

    def setUp(self):
        if not self.import_ok:
            self.skipTest(
                f"could not import server.py: "
                f"{getattr(self, 'import_err', '<unknown>')}"
            )
        import user_settings as US
        self._US = US
        self._tmp = tempfile.TemporaryDirectory()
        self._tmp_path = Path(self._tmp.name)
        self._saved_path = US._SETTINGS_PATH
        US._SETTINGS_PATH = self._tmp_path / "user-settings.json"
        self._saved_dir = US._CONFIG_DIR
        US._CONFIG_DIR = self._tmp_path

        self._fake_keyring = _FakeKeyring()
        self._keyring_patch = mock.patch.dict(
            sys.modules, {"keyring": self._fake_keyring}
        )
        self._keyring_patch.start()

        import oversight_actions
        import oversight_queue
        import tool_events
        protection_data = self._tmp_path / "protection-data"
        protection_data.mkdir()
        self._protection_patches = [
            mock.patch.object(
                tool_events, "APPROVALS_PATH",
                str(protection_data / "execution-approvals.json"),
            ),
            mock.patch.object(
                tool_events, "GLOBAL_SINK_DEFAULT",
                str(protection_data / "tool-events.jsonl"),
            ),
            mock.patch.object(
                oversight_queue, "HUMAN_QUEUE_PATH",
                str(protection_data / "human-queue.jsonl"),
            ),
            mock.patch.object(
                oversight_actions, "HUMAN_QUEUE_PATH",
                str(protection_data / "human-queue.jsonl"),
            ),
            mock.patch.object(
                oversight_actions, "OVERSIGHT_DATA_DIR",
                str(protection_data),
            ),
        ]
        for patcher in self._protection_patches:
            patcher.start()
        tool_events._queued_hashes.clear()

        self.client = self.S.app.test_client()

    def _approve_protected_retry(self, first_response, callback):
        self.assertEqual(first_response.status_code, 409)
        payload = first_response.get_json()
        self.assertEqual(payload["status"], "awaiting_system_protection_approval")
        import oversight_queue
        import tool_events
        entry = oversight_queue.find_paused_by_id(payload["queue_id"])
        self.assertIsNotNone(entry)
        message = tool_events.resolve_gate_entry({
            "id": entry.id,
            "kind": entry.kind,
            "conversation_id": entry.conversation_id,
            "event": entry.event,
        }, approve=True)
        self.assertIn("One-shot token", message)
        return callback()

    def tearDown(self):
        if self.import_ok:
            import tool_events
            tool_events._queued_hashes.clear()
            for patcher in reversed(self._protection_patches):
                patcher.stop()
            self._US._SETTINGS_PATH = self._saved_path
            self._US._CONFIG_DIR = self._saved_dir
            self._keyring_patch.stop()
            self._tmp.cleanup()

    def test_get_returns_defaults_initially(self):
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("settings", data)
        self.assertIn("api_keys", data)
        self.assertEqual(data["settings"]["whisper"]["model_size"], "large-v3")
        self.assertTrue(any(r["provider"] == "anthropic" for r in data["api_keys"]))

    def test_extension_provider_is_dynamic_secret_free_and_credential_scoped(self):
        from flask import Flask
        import provider_registry
        from server.feature_plugins import FeaturePluginSource, load_feature_plugins

        fixture_root = (
            REPO / "orchestrator" / "tests" / "fixtures"
            / "feature_plugins" / "settings_probe"
        )
        providers_before = list(provider_registry.PROVIDERS)
        by_id_before = dict(provider_registry._BY_ID)
        self.assertNotIn("settings_probe", provider_registry.provider_ids())

        try:
            loaded = load_feature_plugins(
                Flask("settings-probe-endpoint-test"),
                self.S._feature_plugin_context,
                sources=(FeaturePluginSource(
                    "settings_probe",
                    "orchestrator.tests.fixtures.feature_plugins.settings_probe",
                    fixture_root,
                ),),
            )
            self.assertIn("settings_probe", loaded.descriptors)
            secret = "settings-probe-secret-must-not-leak"
            set_payload = {"provider": "settings_probe", "value": secret}
            first_store = self.client.post(
                "/api/settings/api-key", json=set_payload,
            )
            self.assertFalse(self._US.api_key_present("settings_probe"))
            stored = self._approve_protected_retry(
                first_store,
                lambda: self.client.post(
                    "/api/settings/api-key", json=set_payload,
                ),
            )
            self.assertEqual(stored.status_code, 200)
            self.assertTrue(self._US.api_key_present("settings_probe"))

            response = self.client.get("/api/settings")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIn("settings_probe", payload["providers"])
            row = next(
                item for item in payload["api_keys"]
                if item["provider"] == "settings_probe"
            )
            self.assertEqual(row["label"], "Settings probe")
            self.assertTrue(row["present"])
            for forbidden in (
                "key", "value", "secret", "keyring_username", "_feature_owner",
            ):
                self.assertNotIn(forbidden, row)
            self.assertNotIn(secret, response.get_data(as_text=True))

            verified = self.client.post(
                "/api/settings/api-key/verify",
                json={"provider": "settings_probe"},
            )
            self.assertEqual(verified.status_code, 200)
            self.assertIsNone(verified.get_json()["ok"])

            probe_module = sys.modules[
                "orchestrator.tests.fixtures.feature_plugins.settings_probe"
            ]
            context = probe_module.LAST_CONTEXT
            self.assertTrue(context.has_credential("settings_probe"))
            self.assertEqual(context.get_credential("settings_probe"), secret)
            with self.assertRaises(self._US.SettingsError):
                context.get_credential("openai")

            first_delete = self.client.delete(
                "/api/settings/api-key/settings_probe"
            )
            deleted = self._approve_protected_retry(
                first_delete,
                lambda: self.client.delete(
                    "/api/settings/api-key/settings_probe"
                ),
            )
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse(self._US.api_key_present("settings_probe"))
            self.assertFalse(context.has_credential("settings_probe"))
        finally:
            provider_registry.PROVIDERS[:] = providers_before
            provider_registry._BY_ID.clear()
            provider_registry._BY_ID.update(by_id_before)

    def test_post_updates_settings(self):
        resp = self.client.post(
            "/api/settings",
            json={"updates": {"capture": {"frame_rate": 60}}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.get_json()["settings"]["capture"]["frame_rate"], 60
        )

    def test_post_validates_input(self):
        resp = self.client.post(
            "/api/settings",
            json={"updates": {"capture": {"frame_rate": 9999}}},
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_rejects_non_dict_updates(self):
        resp = self.client.post(
            "/api/settings",
            json={"updates": "string"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_key_post_stores_in_keyring_stub(self):
        first = self.client.post(
            "/api/settings/api-key",
            json={"provider": "elevenlabs", "value": "xyz123"},
        )
        self.assertNotIn(("ora", "elevenlabs-api-key"), self._fake_keyring.store)
        resp = self._approve_protected_retry(
            first,
            lambda: self.client.post(
                "/api/settings/api-key",
                json={"provider": "elevenlabs", "value": "xyz123"},
            ),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self._fake_keyring.store[("ora", "elevenlabs-api-key")], "xyz123"
        )

    def test_api_key_post_rejects_unknown_provider(self):
        resp = self.client.post(
            "/api/settings/api-key",
            json={"provider": "fake-provider", "value": "x"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_key_post_rejects_empty_value(self):
        resp = self.client.post(
            "/api/settings/api-key",
            json={"provider": "openai", "value": ""},
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_key_delete_removes_from_keyring(self):
        # Pre-populate.
        self._fake_keyring.set_password("ora", "openai-api-key", "abc")
        first = self.client.delete("/api/settings/api-key/openai")
        self.assertIn(("ora", "openai-api-key"), self._fake_keyring.store)
        resp = self._approve_protected_retry(
            first,
            lambda: self.client.delete("/api/settings/api-key/openai"),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(("ora", "openai-api-key"), self._fake_keyring.store)

    def test_api_key_delete_backend_failure_is_not_reported_as_success(self):
        self._fake_keyring.set_password("ora", "openai-api-key", "abc")
        first = self.client.delete("/api/settings/api-key/openai")
        with mock.patch.object(
            self._fake_keyring, "delete_password",
            side_effect=RuntimeError("backend locked"),
        ):
            response = self._approve_protected_retry(
                first,
                lambda: self.client.delete(
                    "/api/settings/api-key/openai"
                ),
            )
        self.assertNotEqual(response.status_code, 200)
        self.assertIn("remains present", response.get_json()["error"])
        self.assertEqual(
            self._fake_keyring.get_password("ora", "openai-api-key"), "abc",
        )
        from orchestrator import system_protection
        terminal_pair = system_protection.verify_audit()[-2:]
        self.assertEqual(
            [record["event_type"] for record in terminal_pair],
            ["protected_action_started", "protected_action_failed"],
        )
        self.assertEqual(
            terminal_pair[0]["request"]["action"], "credential_delete",
        )
        self.assertEqual(
            terminal_pair[1]["execution_id"], terminal_pair[0]["execution_id"],
        )

    def test_api_key_delete_unknown_provider_returns_400(self):
        resp = self.client.delete("/api/settings/api-key/notreal")
        self.assertEqual(resp.status_code, 400)

    def test_api_key_values_never_returned_in_get(self):
        self._fake_keyring.set_password("ora", "anthropic-api-key", "secret-leaks-bad")
        resp = self.client.get("/api/settings")
        text = resp.get_data(as_text=True)
        self.assertNotIn("secret-leaks-bad", text,
                         "API key values must never appear in /api/settings response")

    def test_chatgpt_account_endpoints_report_connect_and_disconnect(self):
        from orchestrator import codex_subscription

        disconnected = {
            "state": "disconnected", "connected": False,
            "configured": False, "message": "Not connected.",
            "catalog_revision": 0,
        }
        connecting = {
            "state": "connecting", "connected": False,
            "configured": True, "message": "Complete sign-in.",
            "catalog_revision": 0,
            "auth_url": "https://auth.openai.test/authorize",
        }
        with mock.patch.object(
            codex_subscription, "status", return_value=disconnected,
        ), mock.patch.object(
            codex_subscription, "connect", return_value=connecting,
        ) as connect, mock.patch.object(
            codex_subscription, "disconnect", return_value=disconnected,
        ) as disconnect, mock.patch.object(
            self.S, "_sync_chatgpt_subscription_router",
        ) as sync:
            status_response = self.client.get(
                "/api/settings/chatgpt-subscription"
            )
            connect_response = self.client.post(
                "/api/settings/chatgpt-subscription/connect"
            )
            disconnect_response = self.client.delete(
                "/api/settings/chatgpt-subscription"
            )

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.get_json()["state"], "disconnected")
        self.assertEqual(connect_response.status_code, 200)
        self.assertEqual(
            connect_response.get_json()["auth_url"],
            "https://auth.openai.test/authorize",
        )
        self.assertEqual(disconnect_response.status_code, 200)
        self.assertEqual(disconnect_response.get_json()["state"], "disconnected")
        connect.assert_called_once_with()
        disconnect.assert_called_once_with()
        self.assertEqual(sync.call_count, 3)

    def test_chatgpt_account_mutations_reject_cross_site_requests(self):
        from orchestrator import codex_subscription

        with mock.patch.object(codex_subscription, "connect") as connect, \
             mock.patch.object(codex_subscription, "disconnect") as disconnect:
            connect_response = self.client.post(
                "/api/settings/chatgpt-subscription/connect",
                headers={"Origin": "https://attacker.example"},
            )
            disconnect_response = self.client.delete(
                "/api/settings/chatgpt-subscription",
                headers={"Sec-Fetch-Site": "cross-site"},
            )

        self.assertEqual(connect_response.status_code, 403)
        self.assertEqual(disconnect_response.status_code, 403)
        connect.assert_not_called()
        disconnect.assert_not_called()

    def test_model_registry_surfaces_connected_codex_model_as_subscription(self):
        from orchestrator import codex_subscription

        endpoint = {
            "id": "codex-subscription:sdk-gpt", "type": "api",
            "status": "active", "enabled": True, "provider": "openai",
            "display_name": "GPT Codex", "description": "Subscription model",
            "service": "codex-subscription", "model_id": "gpt-native",
            "dispatch": "subscription", "vision_capable": True,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "aa_intelligence_index": 88,
            "output_tokens_per_second": 110,
            "metrics_inherited_from": "openai/gpt-native",
            "subscription_provider": "OpenAI",
            "subscription_transport": "ChatGPT via the bundled Codex runtime",
        }
        with mock.patch.object(
            codex_subscription, "is_configured", return_value=True,
        ), mock.patch.object(
            codex_subscription, "model_endpoints", return_value=[endpoint],
        ), mock.patch.object(
            codex_subscription, "status",
            return_value={"state": "connected", "catalog_revision": 1},
        ), mock.patch.object(
            self.S, "_sync_chatgpt_subscription_router",
        ):
            response = self.client.get("/api/model-registry?categories=chat")

        self.assertEqual(response.status_code, 200)
        model = response.get_json()["models"][endpoint["id"]]
        self.assertTrue(model["_subscription_endpoint"])
        self.assertEqual(model["subscription_provider"], "OpenAI")
        self.assertEqual(
            model["subscription_transport"],
            "ChatGPT via the bundled Codex runtime",
        )
        self.assertTrue(model["vision_capable"])
        self.assertEqual(model["input_modalities"], ["text", "image"])
        self.assertEqual(model["output_modalities"], ["text"])
        self.assertEqual(model["pricing"]["input_per_token"], 0)
        self.assertFalse(model["is_free"])
        self.assertEqual(model["aa_intelligence_index"], 88)
        self.assertEqual(model["output_tokens_per_second"], 110)
        self.assertEqual(model["metrics_inherited_from"], "openai/gpt-native")
        self.assertNotIn("_subscription_selector_cost_per_m", model)

    def test_subscription_catalog_change_rebakes_before_router_reload_once(self):
        from orchestrator import active_configuration

        events = []
        prior_signature = self.S._chatgpt_catalog_signature
        self.S._chatgpt_catalog_signature = None
        self.addCleanup(
            setattr, self.S, "_chatgpt_catalog_signature", prior_signature,
        )
        with mock.patch.object(
            active_configuration, "bake_missing_presets",
            side_effect=lambda **kwargs: (
                events.append(("bake", kwargs))
                or list(active_configuration.PRESET_ORDER)
            ),
        ) as bake, mock.patch.object(
            self.S, "_reload_pipeline_router_after_config_change",
            side_effect=lambda: (events.append(("reload", {})) or True),
        ) as reload_router:
            status = {"state": "connected", "catalog_revision": 7}
            self.S._sync_chatgpt_subscription_router(status)
            self.S._sync_chatgpt_subscription_router(status)

        self.assertEqual(events, [
            ("bake", {"force": True}),
            ("reload", {}),
        ])
        bake.assert_called_once_with(force=True)
        reload_router.assert_called_once_with()

    def test_partial_subscription_rebake_does_not_reload_and_retries(self):
        from orchestrator import active_configuration

        prior_signature = self.S._chatgpt_catalog_signature
        self.S._chatgpt_catalog_signature = None
        self.addCleanup(
            setattr, self.S, "_chatgpt_catalog_signature", prior_signature,
        )
        with mock.patch.object(
            active_configuration, "bake_missing_presets",
            side_effect=[
                ["free", "budget"],
                list(active_configuration.PRESET_ORDER),
            ],
        ) as bake, mock.patch.object(
            self.S, "_reload_pipeline_router_after_config_change",
            return_value=True,
        ) as reload_router:
            status = {"state": "connected", "catalog_revision": 8}
            self.S._sync_chatgpt_subscription_router(status)
            self.assertIsNone(self.S._chatgpt_catalog_signature)
            reload_router.assert_not_called()
            self.S._sync_chatgpt_subscription_router(status)

        self.assertEqual(bake.call_count, 2)
        reload_router.assert_called_once_with()

    def test_newer_disconnect_waits_for_connected_bake_and_finishes_last(self):
        from orchestrator import active_configuration

        prior_signature = self.S._chatgpt_catalog_signature
        self.S._chatgpt_catalog_signature = None
        self.addCleanup(
            setattr, self.S, "_chatgpt_catalog_signature", prior_signature,
        )
        connected_bake_entered = threading.Event()
        release_connected_bake = threading.Event()
        disconnected_bake_entered = threading.Event()
        events = []

        def bake(**_kwargs):
            name = threading.current_thread().name
            events.append(f"bake:{name}")
            if name == "connected-sync":
                connected_bake_entered.set()
                release_connected_bake.wait(timeout=2)
            else:
                disconnected_bake_entered.set()
            return list(active_configuration.PRESET_ORDER)

        def reload_router():
            events.append(f"reload:{threading.current_thread().name}")
            return True

        with mock.patch.object(
            active_configuration, "bake_missing_presets", side_effect=bake,
        ), mock.patch.object(
            self.S, "_reload_pipeline_router_after_config_change",
            side_effect=reload_router,
        ):
            connected = threading.Thread(
                name="connected-sync",
                target=self.S._sync_chatgpt_subscription_router,
                args=({"state": "connected", "catalog_revision": 8},),
            )
            disconnected = threading.Thread(
                name="disconnected-sync",
                target=self.S._sync_chatgpt_subscription_router,
                args=({"state": "disconnected", "catalog_revision": 9},),
            )
            connected.start()
            self.assertTrue(connected_bake_entered.wait(timeout=1))
            disconnected.start()
            self.assertFalse(
                disconnected_bake_entered.wait(timeout=0.05),
                "disconnect bake must wait for the connected transaction lock",
            )
            release_connected_bake.set()
            connected.join(timeout=2)
            disconnected.join(timeout=2)

        self.assertFalse(connected.is_alive())
        self.assertFalse(disconnected.is_alive())
        self.assertEqual(events, [
            "bake:connected-sync",
            "reload:connected-sync",
            "bake:disconnected-sync",
            "reload:disconnected-sync",
        ])
        self.assertEqual(self.S._chatgpt_catalog_signature, (False, 9))

    @staticmethod
    def _http_error(code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError(
            "https://provider.example/models", code, "failure", {}, None
        )

    def test_api_key_verification_rejects_confirmed_auth_failure(self):
        entry = {
            "id": "anthropic",
            "dispatch": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
        }
        with mock.patch(
            "urllib.request.urlopen", side_effect=self._http_error(401)
        ):
            ok, message = self.S._verify_provider_key(entry, "bad-key")
        self.assertIs(ok, False)
        self.assertIn("rejected", message)

    def test_api_key_verification_preserves_rate_limit_as_valid(self):
        entry = {
            "id": "anthropic",
            "dispatch": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
        }
        with mock.patch(
            "urllib.request.urlopen", side_effect=self._http_error(429)
        ):
            ok, message = self.S._verify_provider_key(entry, "limited-key")
        self.assertIs(ok, True)
        self.assertIn("rate-limited", message)

    def test_api_key_verification_treats_transient_http_failure_as_inconclusive(self):
        entry = {
            "id": "anthropic",
            "dispatch": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
        }
        with mock.patch(
            "urllib.request.urlopen", side_effect=self._http_error(503)
        ):
            ok, message = self.S._verify_provider_key(entry, "possibly-valid")
        self.assertIsNone(ok)
        self.assertIn("Couldn't confirm", message)

    def test_api_key_verification_treats_non_auth_400_as_inconclusive(self):
        entry = {
            "id": "openai",
            "dispatch": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
        }
        with mock.patch(
            "urllib.request.urlopen", side_effect=self._http_error(400)
        ):
            ok, _message = self.S._verify_provider_key(entry, "possibly-valid")
        self.assertIsNone(ok)

    def test_gemini_400_remains_confirmed_auth_rejection(self):
        entry = {
            "id": "gemini",
            "dispatch": "gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
        }
        with mock.patch(
            "urllib.request.urlopen", side_effect=self._http_error(400)
        ):
            ok, message = self.S._verify_provider_key(entry, "bad-google-key")
        self.assertIs(ok, False)
        self.assertIn("rejected", message)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
