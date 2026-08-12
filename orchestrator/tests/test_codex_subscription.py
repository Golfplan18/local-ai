#!/usr/bin/env python3
"""Behavioral coverage for Ora's isolated ChatGPT/Codex subscription path."""
from __future__ import annotations

import contextlib
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
REPO = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))
sys.path.insert(0, str(REPO))

import boot
import endpoint_health
import mlx_mutex
import router
import tool_events
from orchestrator import codex_subscription as subscription


class _FakeLogin:
    def __init__(self, client):
        self.client = client
        self.auth_url = "https://auth.openai.test/authorize"
        self.cancelled = False

    def wait(self):
        self.client.chatgpt_account = types.SimpleNamespace(
            type="chatgpt", email="reader@example.test",
            plan_type=types.SimpleNamespace(value="plus"),
        )
        return types.SimpleNamespace(success=True)

    def cancel(self):
        self.cancelled = True
        return types.SimpleNamespace(status="cancelled")


class _FakeThread:
    def __init__(self, client):
        self.client = client

    def run(self, prompt, **kwargs):
        self.client.run_call = (prompt, kwargs)
        if self.client.run_error is not None:
            raise self.client.run_error
        return types.SimpleNamespace(
            final_response="subscription answer",
            usage=types.SimpleNamespace(last=types.SimpleNamespace(
                input_tokens=17, output_tokens=5, cached_input_tokens=3,
            )),
        )


class _FakeClient:
    def __init__(self):
        self.chatgpt_account = None
        self.account_error = None
        self.model_rows = []
        self.login_handle = None
        self.logout_calls = 0
        self.thread_start_kwargs = None
        self.run_call = None
        self.run_error = None

    def account(self, *, refresh_token=False):
        if self.account_error is not None:
            raise self.account_error
        account = None
        if self.chatgpt_account is not None:
            account = types.SimpleNamespace(root=self.chatgpt_account)
        return types.SimpleNamespace(account=account)

    def login_chatgpt(self):
        self.login_handle = _FakeLogin(self)
        return self.login_handle

    def logout(self):
        self.logout_calls += 1
        self.chatgpt_account = None

    def models(self, *, include_hidden=False):
        return types.SimpleNamespace(data=self.model_rows)

    def thread_start(self, **kwargs):
        self.thread_start_kwargs = kwargs
        return _FakeThread(self)

    def close(self):
        return None


class _FakeSDK:
    ApprovalMode = types.SimpleNamespace(deny_all="deny-all")
    Sandbox = types.SimpleNamespace(read_only="read-only")

    def __init__(self, client):
        self.client = client
        self.config = None
        self.codex_calls = 0

    def CodexConfig(self, **kwargs):
        self.config = types.SimpleNamespace(**kwargs)
        return self.config

    def Codex(self, config):
        self.codex_calls += 1
        self.config = config
        return self.client


class CodexSubscriptionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_home = subscription.CODEX_HOME
        subscription.CODEX_HOME = Path(self.tmp.name) / "codex-subscription"
        self.client = _FakeClient()
        self.sdk = _FakeSDK(self.client)
        self.import_patch = mock.patch.object(
            subscription.importlib, "import_module", return_value=self.sdk,
        )
        self.import_patch.start()
        self._reset_adapter()

    def tearDown(self):
        self._reset_adapter()
        self.import_patch.stop()
        subscription.CODEX_HOME = self.saved_home
        self.tmp.cleanup()

    @staticmethod
    def _reset_adapter():
        with subscription._state_lock:
            client = subscription._client
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            subscription._client = None
            subscription._login_handle = None
            subscription._login_auth_url = None
            subscription._login_generation = 0
            subscription._last_error = None
            subscription._reauth_required = False
            subscription._catalog_revision = 0
            subscription._model_fingerprint = ()

    def _wait_for_state(self, wanted):
        deadline = time.time() + 1
        while time.time() < deadline:
            state = subscription.status()
            if state["state"] == wanted:
                return state
            time.sleep(0.01)
        self.fail(f"subscription never reached {wanted!r}")

    def _connect(self):
        started = subscription.connect()
        self.assertEqual(started["state"], "connecting")
        return self._wait_for_state("connected")

    def test_never_configured_status_does_not_start_runtime_or_create_home(self):
        state = subscription.status()
        self.assertEqual(state["state"], "disconnected")
        self.assertFalse(subscription.CODEX_HOME.exists())
        self.assertEqual(self.sdk.codex_calls, 0)

    def test_wrapped_account_connects_and_persists_across_adapter_restart(self):
        state = self._connect()
        self.assertEqual(state["email"], "reader@example.test")
        self.assertEqual(state["plan"], "Plus")
        self.assertTrue(subscription.CODEX_HOME.is_dir())
        self.assertEqual(self.sdk.config.cwd, str(subscription.CODEX_HOME))
        self.assertEqual(self.sdk.config.env["CODEX_HOME"], str(subscription.CODEX_HOME))
        for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
            self.assertEqual(self.sdk.config.env[name], "")
        overrides = set(self.sdk.config.config_overrides)
        self.assertIn('cli_auth_credentials_store="keyring"', overrides)
        self.assertIn('forced_login_method="chatgpt"', overrides)
        self.assertIn("features.shell_tool=false", overrides)
        self.assertIn("features.multi_agent=false", overrides)
        self.assertIn(
            "features.multi_agent_v2={enabled=false,max_concurrent_threads_per_session=1}",
            overrides,
        )
        self.assertIn('web_search="disabled"', overrides)
        self.assertIn("mcp_servers={}", overrides)

        self._reset_adapter()
        restored = subscription.status()
        self.assertEqual(restored["state"], "connected")
        self.assertEqual(restored["email"], "reader@example.test")
        self.assertEqual(restored["plan"], "Plus")
        self.assertEqual(self.sdk.codex_calls, 2)

        disconnected = subscription.disconnect()
        self.assertEqual(disconnected["state"], "disconnected")
        self.assertEqual(self.client.logout_calls, 1)
        self.assertTrue(subscription.CODEX_HOME.is_dir())

    def test_discovered_models_are_text_only_runtime_routes(self):
        self._connect()
        self.client.model_rows = [
            types.SimpleNamespace(
                id="sdk-gpt", model="gpt-native", display_name="GPT Codex",
                description="A coding model", hidden=False,
                input_modalities=[types.SimpleNamespace(value="text")],
                is_default=True,
            ),
            types.SimpleNamespace(
                id="hidden", model="hidden", display_name="Hidden",
                description="", hidden=True, input_modalities=["text"],
                is_default=False,
            ),
            types.SimpleNamespace(
                id="audio-only", model="audio", display_name="Audio",
                description="", hidden=False, input_modalities=["audio"],
                is_default=False,
            ),
        ]
        endpoints = subscription.model_endpoints()
        self.assertEqual([e["id"] for e in endpoints], ["codex-subscription:sdk-gpt"])
        endpoint = endpoints[0]
        self.assertEqual(endpoint["model_id"], "gpt-native")
        self.assertEqual(endpoint["dispatch"], "subscription")
        self.assertEqual(endpoint["service"], "codex-subscription")
        self.assertFalse(endpoint["vision_capable"])
        self.assertFalse(endpoint["capabilities"]["tool_access"])
        self.assertNotIn("context_window", endpoint)

    def test_inference_is_ephemeral_read_only_deny_all_and_metered(self):
        self._connect()
        result = subscription.run_completion([
            {"role": "system", "content": "Ora system contract"},
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "user", "content": "Follow-up"},
        ], "gpt-native")
        self.assertEqual(result, {
            "text": "subscription answer", "input_tokens": 17,
            "output_tokens": 5, "cached_input_tokens": 3,
        })
        start = self.client.thread_start_kwargs
        self.assertEqual(start["model"], "gpt-native")
        self.assertEqual(start["model_provider"], "openai")
        self.assertTrue(start["ephemeral"])
        self.assertEqual(start["approval_mode"], "deny-all")
        self.assertEqual(start["sandbox"], "read-only")
        self.assertEqual(start["base_instructions"], "Ora system contract")
        self.assertIn("Do not call tools", start["developer_instructions"])
        self.assertIn("or read files", start["developer_instructions"])
        isolated_cwd = Path(start["cwd"])
        self.assertFalse(isolated_cwd.exists(), "ephemeral cwd must be removed")
        prompt, run_kwargs = self.client.run_call
        self.assertIn("[USER]\nQuestion", prompt)
        self.assertIn("[ASSISTANT]\nEarlier answer", prompt)
        self.assertIn("[USER]\nFollow-up", prompt)
        self.assertEqual(run_kwargs["approval_mode"], "deny-all")
        self.assertEqual(run_kwargs["sandbox"], "read-only")
        self.assertEqual(run_kwargs["model"], "gpt-native")

    def test_unauthorized_turn_forces_subsequent_reconnect_status(self):
        self._connect()
        self.client.run_error = RuntimeError("unauthorized: expired secret token-value")
        with self.assertRaises(subscription.CodexSubscriptionError) as caught:
            subscription.run_completion(
                [{"role": "user", "content": "hello"}], "gpt-native"
            )
        self.assertEqual(caught.exception.kind, "reauth_required")
        state = subscription.status()
        self.assertEqual(state["state"], "error")
        self.assertIn("Disconnect and reconnect", state["message"])
        self.assertNotIn("token-value", state["message"])
        self.assertEqual(subscription.model_endpoints(), [])

    def test_status_never_returns_raw_runtime_exception_text(self):
        subscription.CODEX_HOME.mkdir(parents=True)
        self.client.account_error = RuntimeError("sensitive-account-payload")
        state = subscription.status()
        self.assertEqual(state["state"], "error")
        self.assertNotIn("sensitive-account-payload", str(state))


class SubscriptionRoutingAndDispatchTests(unittest.TestCase):
    ENDPOINT = {
        "id": "codex-subscription:sdk-gpt", "type": "api",
        "status": "active", "enabled": True, "provider": "openai",
        "display_name": "GPT Codex", "service": "codex-subscription",
        "model_id": "gpt-native", "dispatch": "subscription",
        "vision_capable": False, "capabilities": {},
    }

    def test_router_merges_connected_runtime_model_and_preserves_dispatch(self):
        with mock.patch.object(subscription, "is_configured", return_value=True), \
             mock.patch.object(subscription, "model_endpoints", return_value=[self.ENDPOINT]):
            routed = router.Router(config_dict={"endpoints": [], "machines": []})
        resolved = routed.resolve_endpoint_by_id(self.ENDPOINT["id"])
        self.assertIsNotNone(resolved)
        v1 = routed._to_v1_endpoint(resolved)
        self.assertEqual(v1["model"], "gpt-native")
        self.assertEqual(v1["service"], "codex-subscription")
        self.assertEqual(v1["dispatch"], "subscription")

    def test_boot_dispatch_records_attempt_and_sdk_token_usage(self):
        endpoint = {
            "id": self.ENDPOINT["id"], "type": "api",
            "service": "codex-subscription", "model": "gpt-native",
            "dispatch": "subscription",
        }
        with mock.patch.object(
            subscription, "run_completion",
            return_value={
                "text": "answer", "input_tokens": 10,
                "output_tokens": 4, "cached_input_tokens": 2,
            },
        ) as run, mock.patch.object(
            boot, "_record_physical_model_call_config"
        ) as physical, mock.patch.object(boot, "_record_model_usage") as usage:
            result = boot._call_codex_subscription(
                [{"role": "user", "content": "hello"}], endpoint
            )
        self.assertEqual(result, "answer")
        run.assert_called_once_with(
            [{"role": "user", "content": "hello"}], "gpt-native"
        )
        self.assertEqual(physical.call_args.kwargs["provider_attempt"], "codex-subscription")
        self.assertEqual(usage.call_args.kwargs["prompt_tokens"], 10)
        self.assertEqual(usage.call_args.kwargs["completion_tokens"], 4)
        self.assertEqual(usage.call_args.kwargs["cache_read_tokens"], 2)

    def test_boot_maps_reauth_without_api_fallback(self):
        endpoint = {
            "id": self.ENDPOINT["id"], "type": "api",
            "service": "codex-subscription", "model": "gpt-native",
            "dispatch": "subscription",
            "openrouter_fallback_model_id": None,
        }
        error = subscription.CodexSubscriptionError(
            "reauth_required", "raw should not surface"
        )
        with mock.patch.object(subscription, "run_completion", side_effect=error):
            result = boot.call_api_endpoint(
                [{"role": "user", "content": "hello"}], endpoint
            )
        self.assertIn("reconnect required", result)
        self.assertNotIn("raw should not surface", result)

    def test_subscription_model_call_is_boundary_only(self):
        endpoint = {
            "id": "subscription-boundary-test", "type": "api",
            "service": "codex-subscription", "model": "gpt-native",
            "dispatch": "subscription",
        }
        events = []
        with mock.patch.object(boot, "call_api_endpoint", return_value="ok"), \
             mock.patch.object(mlx_mutex, "track_api_call", return_value=contextlib.nullcontext()), \
             mock.patch.object(endpoint_health, "record_success"), \
             mock.patch.object(endpoint_health, "record_failure"), \
             mock.patch.object(tool_events, "record", side_effect=events.append):
            self.assertEqual(
                boot.call_model([{"role": "user", "content": "hello"}], endpoint),
                "ok",
            )
        self.assertEqual(events[-1]["enforcement_model"], "boundary_only")

    def test_existing_direct_openai_dispatch_does_not_enter_subscription(self):
        response = types.SimpleNamespace(
            choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content="direct answer"),
                finish_reason="stop",
            )],
            usage=None,
        )
        completions = types.SimpleNamespace(create=lambda **_kwargs: response)
        fake_openai = types.SimpleNamespace(
            OpenAI=lambda **_kwargs: types.SimpleNamespace(
                chat=types.SimpleNamespace(completions=completions)
            )
        )
        endpoint = {
            "id": "openai/gpt-4o", "type": "api", "service": "openai",
            "model": "gpt-4o",
        }
        with mock.patch.dict(sys.modules, {"openai": fake_openai}), \
             mock.patch.object(boot, "_canonical_provider_key", return_value="key"), \
             mock.patch.object(subscription, "run_completion") as subscription_run:
            result = boot._call_api_endpoint_inner(
                [{"role": "user", "content": "hello"}], endpoint
            )
        self.assertEqual(result, "direct answer")
        subscription_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
