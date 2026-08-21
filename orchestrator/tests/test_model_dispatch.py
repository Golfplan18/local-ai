#!/usr/bin/env python3
"""Tests for model_dispatch.py — project-facing model invocation API."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
ROOT = ORCHESTRATOR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ORCHESTRATOR))

from orchestrator import model_dispatch  # noqa: E402
from orchestrator.model_dispatch import ModelDispatchError, invoke_chat, get_slot_info  # noqa: E402


class TestInvokeChat(unittest.TestCase):
    """invoke_chat with mocked boot internals so tests don't hit a real model."""

    def _mock_boot(self, *, endpoint=None, response="OK"):
        """Patch boot.load_routing_config, boot.get_slot_endpoint, boot.call_model.

        Returns the call_model mock so tests can inspect the messages
        argument that was constructed.
        """
        load_routing_config_mock = mock.Mock(return_value={"endpoints": []})
        get_slot_mock = mock.Mock(return_value=endpoint or {
            "name": "test-endpoint", "type": "api", "service": "claude",
            "model": "claude-test",
        })
        call_model_mock = mock.Mock(return_value=response)
        # Patch by injecting a dummy module that provides the three symbols
        # invoke_chat imports. The function does the import inside its body
        # so test setup runs after the patch.
        boot_stub = mock.MagicMock()
        boot_stub.load_routing_config = load_routing_config_mock
        boot_stub.get_slot_endpoint = get_slot_mock
        boot_stub.call_model = call_model_mock
        sys.modules["orchestrator.boot"] = boot_stub
        return call_model_mock

    def tearDown(self):
        sys.modules.pop("orchestrator.boot", None)

    def test_basic_call_returns_response(self):
        self._mock_boot(response="hello world")
        out = invoke_chat("you are a helpful assistant.", "say hello")
        self.assertEqual(out, "hello world")

    def test_response_is_stripped(self):
        self._mock_boot(response="  \n  some output  \n  ")
        out = invoke_chat("sys", "user")
        self.assertEqual(out, "some output")

    def test_messages_built_correctly(self):
        call_mock = self._mock_boot(response="x")
        invoke_chat("SYSTEM_TEXT", "USER_TEXT")
        args, _ = call_mock.call_args
        messages = args[0]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "SYSTEM_TEXT")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "USER_TEXT")

    def test_extra_messages_inserted(self):
        call_mock = self._mock_boot(response="x")
        invoke_chat(
            "S", "U",
            extra_messages=[
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "second"},
            ],
        )
        args, _ = call_mock.call_args
        messages = args[0]
        self.assertEqual([m["content"] for m in messages], ["S", "first", "second", "U"])

    def test_slot_passed_through(self):
        # The slot determines which endpoint is fetched; verify get_slot_endpoint
        # is called with it.
        load_mock = mock.Mock(return_value={})
        slot_mock = mock.Mock(return_value={
            "name": "x", "type": "api", "service": "claude", "model": "m",
        })
        boot_stub = mock.MagicMock()
        boot_stub.load_routing_config = load_mock
        boot_stub.get_slot_endpoint = slot_mock
        boot_stub.call_model = mock.Mock(return_value="ok")
        sys.modules["orchestrator.boot"] = boot_stub

        invoke_chat("s", "u", slot="depth")
        slot_mock.assert_called_once()
        _, kwargs = slot_mock.call_args
        self.assertIn("depth", slot_mock.call_args[0])

    def test_no_endpoint_for_slot_raises(self):
        # get_slot_endpoint returns None.
        boot_stub = mock.MagicMock()
        boot_stub.load_routing_config = mock.Mock(return_value={})
        boot_stub.get_slot_endpoint = mock.Mock(return_value=None)
        boot_stub.call_model = mock.Mock()
        sys.modules["orchestrator.boot"] = boot_stub

        with self.assertRaises(ModelDispatchError) as ctx:
            invoke_chat("s", "u", slot="ghost-slot")
        self.assertEqual(ctx.exception.reason, "no_slot_endpoint")
        self.assertEqual(ctx.exception.slot, "ghost-slot")

    def test_endpoints_config_failure_raises(self):
        boot_stub = mock.MagicMock()
        boot_stub.load_routing_config = mock.Mock(side_effect=OSError("disk gone"))
        boot_stub.get_slot_endpoint = mock.Mock()
        boot_stub.call_model = mock.Mock()
        sys.modules["orchestrator.boot"] = boot_stub

        with self.assertRaises(ModelDispatchError) as ctx:
            invoke_chat("s", "u")
        self.assertEqual(ctx.exception.reason, "no_endpoints_config")

    def test_model_error_response_raises(self):
        # Ora's call_model returns "[Error ...]" strings on failure.
        # invoke_chat must surface these as ModelDispatchError.
        self._mock_boot(response="[Error calling Claude API: rate limited]")
        with self.assertRaises(ModelDispatchError) as ctx:
            invoke_chat("s", "u")
        self.assertEqual(ctx.exception.reason, "model_error")
        self.assertIn("rate limited", ctx.exception.detail)

    def test_mlx_model_not_found_response_raises(self):
        self._mock_boot(response="[MLX model not found: 'foo' — check ...]")
        with self.assertRaises(ModelDispatchError) as ctx:
            invoke_chat("s", "u")
        self.assertEqual(ctx.exception.reason, "model_error")

    def test_non_string_response_raises(self):
        # Defensive — call_model is documented to return str, but if the
        # contract is ever broken we want a clear error.
        self._mock_boot(response=None)
        with self.assertRaises(ModelDispatchError) as ctx:
            invoke_chat("s", "u")
        self.assertEqual(ctx.exception.reason, "model_error")


class TestGetSlotInfo(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("orchestrator.boot", None)

    def test_returns_endpoint_summary(self):
        boot_stub = mock.MagicMock()
        boot_stub.load_routing_config = mock.Mock(return_value={})
        boot_stub.get_slot_endpoint = mock.Mock(return_value={
            "name": "local-mlx-hermes-4-70b",
            "model_name": "Hermes-4-70B (4-bit)",
            "model": "/opt/ora/models/hermes-4-70b",
            "type": "local",
            "service": None,
            "role": "breadth",
            "ram_required_gb": 40,  # extra field — must be omitted
        })
        sys.modules["orchestrator.boot"] = boot_stub
        info = get_slot_info("breadth")
        self.assertEqual(info["name"], "local-mlx-hermes-4-70b")
        self.assertEqual(info["model_name"], "Hermes-4-70B (4-bit)")
        self.assertEqual(info["type"], "local")
        self.assertEqual(info["role"], "breadth")
        # Extra fields are dropped.
        self.assertNotIn("ram_required_gb", info)

    def test_no_endpoint_returns_empty_dict(self):
        boot_stub = mock.MagicMock()
        boot_stub.load_routing_config = mock.Mock(return_value={})
        boot_stub.get_slot_endpoint = mock.Mock(return_value=None)
        sys.modules["orchestrator.boot"] = boot_stub
        self.assertEqual(get_slot_info("ghost"), {})

    def test_load_failure_returns_empty_dict(self):
        boot_stub = mock.MagicMock()
        boot_stub.load_routing_config = mock.Mock(side_effect=OSError())
        boot_stub.get_slot_endpoint = mock.Mock()
        sys.modules["orchestrator.boot"] = boot_stub
        self.assertEqual(get_slot_info(), {})


if __name__ == "__main__":
    unittest.main()
