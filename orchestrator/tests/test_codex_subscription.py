#!/usr/bin/env python3
"""Behavioral coverage for Ora's isolated ChatGPT/Codex subscription path."""
from __future__ import annotations

import contextlib
import json
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


class _FakeTextInput:
    def __init__(self, text):
        self.text = text


class _FakeImageInput:
    def __init__(self, url):
        self.url = url


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
    TextInput = _FakeTextInput
    ImageInput = _FakeImageInput

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

    def test_discovered_models_preserve_sdk_image_modality(self):
        self._connect()
        self.client.model_rows = [
            types.SimpleNamespace(
                id="sdk-gpt", model="gpt-native", display_name="GPT Codex",
                description="A coding model", hidden=False,
                input_modalities=[types.SimpleNamespace(value="text")],
                is_default=True,
            ),
            types.SimpleNamespace(
                id="sdk-vision", model="gpt-vision",
                display_name="GPT Vision", description="A vision model",
                hidden=False, input_modalities=["image", "text"],
                output_modalities=["text"], is_default=False,
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
        by_id = {endpoint["id"]: endpoint for endpoint in endpoints}
        self.assertEqual(set(by_id), {
            "codex-subscription:sdk-gpt", "codex-subscription:sdk-vision",
        })
        text_endpoint = by_id["codex-subscription:sdk-gpt"]
        self.assertEqual(text_endpoint["model_id"], "gpt-native")
        self.assertEqual(text_endpoint["dispatch"], "subscription")
        self.assertEqual(text_endpoint["service"], "codex-subscription")
        self.assertFalse(text_endpoint["vision_capable"])
        self.assertEqual(text_endpoint["input_modalities"], ["text"])
        vision_endpoint = by_id["codex-subscription:sdk-vision"]
        self.assertTrue(vision_endpoint["vision_capable"])
        self.assertEqual(vision_endpoint["input_modalities"], ["text", "image"])
        self.assertEqual(vision_endpoint["output_modalities"], ["text"])
        self.assertFalse(vision_endpoint["capabilities"]["tool_access"])
        self.assertNotIn("context_window", vision_endpoint)

    def test_modality_change_invalidates_catalog_revision_once(self):
        self._connect()
        row = types.SimpleNamespace(
            id="sdk-gpt", model="gpt-native", display_name="GPT Codex",
            hidden=False, input_modalities=["text"], is_default=True,
        )
        self.client.model_rows = [row]
        subscription.model_endpoints()
        initial_revision = subscription.status()["catalog_revision"]
        subscription.model_endpoints()
        self.assertEqual(
            subscription.status()["catalog_revision"], initial_revision,
        )
        row.input_modalities = ["text", "image"]
        subscription.model_endpoints()
        self.assertEqual(
            subscription.status()["catalog_revision"], initial_revision + 1,
        )
        subscription.model_endpoints()
        self.assertEqual(
            subscription.status()["catalog_revision"], initial_revision + 1,
        )

    def test_exact_counterparts_supply_metrics_and_selector_only_penny_costs(self):
        self._connect()
        self.client.model_rows = [
            types.SimpleNamespace(
                id="sdk-old", model="gpt-old", display_name="GPT Old",
                hidden=False, input_modalities=["text", "image"],
                is_default=False,
            ),
            types.SimpleNamespace(
                id="sdk-new", model="gpt-new", display_name="GPT New",
                hidden=False, input_modalities=["text"], is_default=False,
            ),
            types.SimpleNamespace(
                id="sdk-expensive", model="gpt-expensive",
                display_name="GPT Expensive", hidden=False,
                input_modalities=["text"], is_default=False,
            ),
            types.SimpleNamespace(
                id="sdk-unmatched", model="gpt-native",
                display_name="GPT Unmatched", hidden=False,
                input_modalities=["text"], is_default=False,
            ),
        ]
        catalog_path = Path(self.tmp.name) / "model-catalog.json"
        registry_path = Path(self.tmp.name) / "model-registry.json"
        catalog_path.write_text(json.dumps({"models": [
            {"id": "openai/gpt-old", "size_bucket": "large",
             "release_date": "2024-01-01", "context_window": 200000,
             "openrouter_pricing": {"blended_per_m": 2.0}},
            {"id": "openai/gpt-new", "size_bucket": "large",
             "release_date": "2025-01-01", "context_window": 300000,
             "openrouter_pricing": {"blended_per_m": 2.0}},
            {"id": "openai/gpt-expensive", "size_bucket": "large",
             "release_date": "2025-06-01",
             "openrouter_pricing": {"blended_per_m": 8.0}},
            # A fuzzy near-match must not enrich sdk-unmatched.
            {"id": "openai/gpt-native-preview", "size_bucket": "large",
             "openrouter_pricing": {"blended_per_m": 1.0}},
        ]}))
        registry_path.write_text(json.dumps({"models": {
            model_id: {
                "aa_intelligence_index": 70 + index,
                "aa_coding_index": 80 + index,
                "aa_agentic_index": 60 + index,
                "output_tokens_per_second": 100 + index,
                "latency_ttft_seconds": 0.4 + index / 10,
                "reasoning_model": False,
                "vision_capable": True,
            }
            for index, model_id in enumerate((
                "openai/gpt-old", "openai/gpt-new",
                "openai/gpt-expensive",
            ))
        }}))

        with mock.patch.object(
            subscription.runtime_paths, "model_catalog_path",
            return_value=catalog_path,
        ), mock.patch.object(
            subscription.runtime_paths, "model_registry_path",
            return_value=registry_path,
        ):
            endpoints = subscription.model_endpoints()
            candidates = subscription.selector_candidates(endpoints)

        by_id = {endpoint["id"]: endpoint for endpoint in endpoints}
        enriched = by_id["codex-subscription:sdk-old"]
        self.assertEqual(enriched["metrics_inherited_from"], "openai/gpt-old")
        self.assertEqual(enriched["aa_coding_index"], 80)
        self.assertEqual(enriched["context_window"], 200000)
        self.assertTrue(enriched["vision_capable"])
        self.assertEqual(enriched["input_modalities"], ["text", "image"])
        self.assertEqual(enriched["output_modalities"], ["text"])
        self.assertNotIn(
            "metrics_inherited_from",
            by_id["codex-subscription:sdk-unmatched"],
        )

        self.assertEqual([candidate["id"] for candidate in candidates], [
            "codex-subscription:sdk-old",
            "codex-subscription:sdk-new",
            "codex-subscription:sdk-expensive",
        ])
        self.assertEqual(
            [candidate["_subscription_selector_cost_per_m"]
             for candidate in candidates],
            [0.01, 0.02, 0.03],
        )
        for candidate in candidates:
            self.assertNotIn("openrouter_pricing", candidate)
            self.assertNotIn("pricing", candidate)

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

    def test_image_inference_uses_native_text_then_canvas_image_items(self):
        self._connect()
        canvas = {
            "name": "preview.png", "mime": "image/png",
            "base64": "aW1hZ2U=", "source": "v3_canvas_preview",
        }
        result = subscription.run_completion(
            [{"role": "user", "content": "Read the current canvas."}],
            "gpt-native",
            images=[canvas],
            input_modalities=["text", "image"],
        )
        self.assertEqual(result["text"], "subscription answer")
        run_input, _run_kwargs = self.client.run_call
        self.assertEqual(len(run_input), 2)
        self.assertIsInstance(run_input[0], _FakeTextInput)
        self.assertIn("Read the current canvas.", run_input[0].text)
        self.assertIsInstance(run_input[1], _FakeImageInput)
        self.assertEqual(run_input[1].url, "data:image/png;base64,aW1hZ2U=")
        self.assertTrue(canvas["_codex_subscription_image_submitted"])

        with self.assertRaises(subscription.CodexSubscriptionError) as caught:
            subscription.run_completion(
                [{"role": "user", "content": "Read the current canvas."}],
                "gpt-native",
                images=[
                    {"mime": "image/png", "base64": "dXBsb2Fk",
                     "source": "upload"},
                    canvas,
                ],
                input_modalities=["text", "image"],
            )
        self.assertEqual(caught.exception.kind, "invalid_image_input")

    def test_image_inference_fails_closed_without_advertised_modality(self):
        self._connect()
        canvas = {
            "name": "preview.png", "mime": "image/png",
            "base64": "aW1hZ2U=", "source": "v3_canvas_preview",
        }
        with self.assertRaises(subscription.CodexSubscriptionError) as caught:
            subscription.run_completion(
                [{"role": "user", "content": "Read the current canvas."}],
                "gpt-native", images=[canvas],
            )
        self.assertEqual(caught.exception.kind, "text_only_image_input")
        self.assertIsNone(self.client.run_call)

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
        "vision_capable": True,
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"], "capabilities": {},
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
        self.assertTrue(v1["vision_capable"])
        self.assertEqual(v1["input_modalities"], ["text", "image"])
        self.assertTrue(
            boot.vision_capable_for_endpoint(v1),
            "v1 conversion must retain SDK vision truth",
        )

    def test_boot_dispatch_records_attempt_and_sdk_token_usage(self):
        endpoint = {
            "id": self.ENDPOINT["id"], "type": "api",
            "service": "codex-subscription", "model": "gpt-native",
            "dispatch": "subscription",
            "vision_capable": True,
            "input_modalities": ["text", "image"],
        }
        canvas = {
            "name": "preview.png", "mime": "image/png",
            "base64": "aW1hZ2U=", "source": "v3_canvas_preview",
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
                [{"role": "user", "content": "hello"}], endpoint,
                images=[canvas],
            )
        self.assertEqual(result, "answer")
        run.assert_called_once_with(
            [{"role": "user", "content": "hello"}], "gpt-native",
            images=[canvas], input_modalities=["text", "image"],
        )
        self.assertEqual(physical.call_args.kwargs["provider_attempt"], "codex-subscription")
        self.assertEqual(usage.call_args.kwargs["prompt_tokens"], 10)
        self.assertEqual(usage.call_args.kwargs["completion_tokens"], 4)
        self.assertEqual(usage.call_args.kwargs["cache_read_tokens"], 2)

    def test_text_only_canvas_rejection_is_terminal_before_dispatch(self):
        endpoint = {
            **self.ENDPOINT,
            "vision_capable": False,
            "input_modalities": ["text"],
        }
        images = [{
            "name": "preview.png", "mime": "image/png",
            "base64": "aW1hZ2U=", "source": "v3_canvas_preview",
        }]
        with mock.patch.object(
            boot, "prepare_messages_with_continuity",
            side_effect=lambda messages, *_args, **_kwargs: (messages, {}),
        ), mock.patch.object(
            mlx_mutex, "track_api_call", return_value=contextlib.nullcontext(),
        ), mock.patch.object(
            boot, "_record_physical_model_call_config",
        ) as physical, mock.patch.object(
            subscription, "run_completion",
        ) as run, mock.patch.object(
            endpoint_health, "record_failure",
        ) as failure, mock.patch.object(
            endpoint_health, "record_success",
        ) as success:
            with self.assertRaises(boot.TerminalInputAbort) as caught:
                boot.call_model(
                    [{"role": "user", "content": "Read this canvas."}],
                    endpoint, images=images,
                )
        self.assertIn("text-only", caught.exception.safe_message)
        physical.assert_not_called()
        run.assert_not_called()
        failure.assert_not_called()
        success.assert_not_called()

    def test_dynamic_fallback_input_rejection_aborts_without_degradation(self):
        primary = {
            "name": "primary", "type": "api", "service": "openrouter",
            "model": "vendor/primary", "vision_capable": True,
        }
        fallback = {
            "name": "fallback", "type": "api",
            "service": "codex-subscription", "model": "gpt-native",
            "vision_capable": False, "input_modalities": ["text"],
        }
        def dispatch(_messages, endpoint, images=None, **_kwargs):
            if endpoint is primary:
                return "[Error primary unavailable]"
            self.assertIs(endpoint, fallback)
            return boot._call_codex_subscription(
                _messages, endpoint, images=images,
            )

        with mock.patch.object(
            boot, "_run_model_with_tools", side_effect=dispatch,
        ) as model_call, mock.patch.object(
            boot, "_resolve_fallback_endpoint", return_value=fallback,
        ), mock.patch.object(
            boot, "_record_physical_model_call_config",
        ) as physical, mock.patch.object(
            subscription, "run_completion",
        ) as run:
            with self.assertRaises(boot.TerminalInputAbort) as caught:
                boot._call_with_supplement(
                    [{"role": "user", "content": "Read this canvas."}],
                    primary, "analyst", images=[{
                        "mime": "image/png", "base64": "aW1hZ2U=",
                        "source": "v3_canvas_preview",
                    }],
                    context_pkg={}, slot="depth", gear=3,
                )
        self.assertIn("text-only", caught.exception.safe_message)
        self.assertEqual(model_call.call_count, 2)
        physical.assert_not_called()
        run.assert_not_called()

    def test_vision_canvas_skips_extractor_and_notice_requires_sdk_success(self):
        context_pkg = {
            "image_path": "/tmp/current-preview.png",
            "cleaned_prompt": "Read this canvas.",
        }
        canvas = {
            "name": "preview.png", "mime": "image/png",
            "base64": "aW1hZ2U=", "source": "v3_canvas_preview",
        }
        with mock.patch.object(
            boot, "route_for_image_input", wraps=boot.route_for_image_input,
        ) as route, mock.patch(
            "visual_extraction.extract_spatial_from_image",
        ) as extract:
            error = boot._prepare_image_routing(
                context_pkg, [self.ENDPOINT], [canvas], "Read this canvas.",
            )
        self.assertIsNone(error)
        self.assertTrue(context_pkg["vision_direct_pass"])
        self.assertIs(route.call_args.kwargs["requested_model"], self.ENDPOINT)
        extract.assert_not_called()
        self.assertEqual(
            boot._append_codex_canvas_image_notice("Answer", [canvas]),
            "Answer",
        )
        canvas["_codex_subscription_image_submitted"] = True
        noticed = boot._append_codex_canvas_image_notice("Answer", [canvas])
        self.assertEqual(
            noticed,
            "Answer\n\n" + boot.CODEX_CANVAS_IMAGE_NOTICE,
        )
        self.assertEqual(noticed.count(boot.CODEX_CANVAS_IMAGE_NOTICE), 1)

    def test_server_terminal_surfaces_exact_notice_after_successful_image_call(self):
        from server import app as server_app
        import risk_gate

        endpoint = {
            **self.ENDPOINT,
            "name": self.ENDPOINT["id"],
            "model": self.ENDPOINT["model_id"],
            "context_window": 100000,
        }
        canvas = {
            "name": "preview.png", "mime": "image/png",
            "base64": "aW1hZ2U=", "source": "v3_canvas_preview",
        }

        def successful_call(_messages, _endpoint, images=None):
            self.assertEqual(images, [canvas])
            canvas["_codex_subscription_image_submitted"] = True
            return "Answer"

        with mock.patch.object(server_app, "load_config", return_value={}), \
             mock.patch.object(server_app, "get_endpoint", return_value=endpoint), \
             mock.patch.object(server_app, "_direct_system_prompt",
                               return_value="SYSTEM"), \
             mock.patch.object(server_app, "call_model",
                               side_effect=successful_call), \
             mock.patch.object(risk_gate, "now_ts", return_value=1.0), \
             mock.patch.object(risk_gate, "assign_tier",
                               return_value={"risk_tier": "light"}), \
             mock.patch.object(risk_gate, "evaluate_hold",
                               return_value=(None, None)), \
             mock.patch.object(risk_gate, "record_route_observed"):
            chunks = list(server_app._direct_stream_impl(
                "Read this canvas.", [], images=[canvas],
            ))
        events = [json.loads(chunk[6:]) for chunk in chunks]
        response = [
            event["text"] for event in events
            if event.get("type") == "response"
        ][-1]
        self.assertEqual(
            response,
            "Answer\n\n" + boot.CODEX_CANVAS_IMAGE_NOTICE,
        )
        self.assertEqual(response.count(boot.CODEX_CANVAS_IMAGE_NOTICE), 1)

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
