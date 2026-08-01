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
import sys
import tempfile
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
            import server as S  # type: ignore
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
