"""Aside model preference, dispatch, and five-turn memory regressions."""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ORA_HOME"] = _REPO
for _path in (_REPO, os.path.join(_REPO, "server"), os.path.join(_REPO, "orchestrator")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()

from orchestrator.router import Router  # noqa: E402
import server  # noqa: E402
from sidebar_window import SidebarWindow  # noqa: E402


class SidebarWindowTests(unittest.TestCase):
    def test_keeps_only_five_latest_turn_pairs_in_order(self):
        window = SidebarWindow()
        for idx in range(7):
            window.add_exchange(f"u{idx}", f"a{idx}")
        self.assertEqual(window.get_turn_count(), 5)
        self.assertEqual(window.get_history()[0], {"role": "user", "content": "u2"})
        self.assertEqual(window.get_history()[-1], {"role": "assistant", "content": "a6"})

    def test_transaction_serializes_exchanges(self):
        window = SidebarWindow()
        holder_entered = threading.Event()
        release_holder = threading.Event()
        waiter_entered = threading.Event()

        def hold():
            with window.transaction():
                holder_entered.set()
                release_holder.wait(timeout=2)

        def wait_for_window():
            with window.transaction():
                waiter_entered.set()

        holder = threading.Thread(target=hold)
        waiter = threading.Thread(target=wait_for_window)
        holder.start()
        self.assertTrue(holder_entered.wait(timeout=1))
        waiter.start()
        self.assertFalse(waiter_entered.wait(timeout=0.05))
        release_holder.set()
        holder.join(timeout=1)
        waiter.join(timeout=1)
        self.assertTrue(waiter_entered.is_set())


class ExplicitEndpointResolutionTests(unittest.TestCase):
    def _router(self):
        return Router(config_dict={
            "endpoints": [
                {"id": "gemini/preferred", "type": "api", "service": "gemini",
                 "model_id": "preferred", "enabled": True, "status": "active"},
                {"id": "local/ready", "type": "local", "enabled": True,
                 "status": "active", "model_path": "/tmp/model"},
                {"id": "api/off", "type": "api", "enabled": False,
                 "status": "active"},
                {"id": "browser/session", "type": "browser", "enabled": True,
                 "status": "active"},
            ]
        })

    @mock.patch("endpoint_health.is_in_cooldown", return_value=False)
    def test_resolves_active_api_and_local_models(self, _cooldown):
        router = self._router()
        self.assertEqual(
            router.resolve_endpoint_by_id("gemini/preferred")["id"],
            "gemini/preferred",
        )
        self.assertEqual(
            router.resolve_endpoint_by_id("LOCAL/READY")["id"],
            "local/ready",
        )

    @mock.patch("endpoint_health.is_in_cooldown", return_value=False)
    def test_rejects_disabled_and_unsupported_models(self, _cooldown):
        router = self._router()
        self.assertIsNone(router.resolve_endpoint_by_id("api/off"))
        self.assertIsNone(router.resolve_endpoint_by_id("browser/session"))
        self.assertIsNone(router.resolve_endpoint_by_id("missing"))

    @mock.patch("endpoint_health.is_in_cooldown")
    def test_list_contains_only_explicitly_resolvable_models(self, cooldown):
        router = self._router()
        self.assertEqual(
            [endpoint["id"] for endpoint in router.list_interactive_endpoints()],
            ["gemini/preferred", "local/ready"],
        )
        cooldown.assert_not_called()

    @mock.patch("endpoint_health.is_in_cooldown", return_value=True)
    def test_resolver_rejects_cooling_model(self, _cooldown):
        self.assertIsNone(
            self._router().resolve_endpoint_by_id("gemini/preferred"))


class ScratchpadEndpointTests(unittest.TestCase):
    def setUp(self):
        server.clear_sidebar_window("aside")
        self.client = server.app.test_client()
        self.preferred = {"name": "gemini/preferred", "type": "api",
                          "service": "gemini", "model": "preferred"}
        self.fallback = {"name": "small/fallback", "type": "api",
                         "service": "openrouter", "model": "fallback"}
        self.patches = [
            mock.patch.object(server, "load_config", return_value={}),
            mock.patch.object(server, "get_endpoint_by_id", return_value=self.preferred),
            mock.patch.object(server, "get_slot_endpoint", return_value=self.fallback),
            mock.patch.object(server._user_settings, "get_setting",
                              return_value="gemini/gemini-3.1-flash-lite"),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        server.clear_sidebar_window("aside")

    def test_preferred_model_wins_and_prior_exchange_is_sent(self):
        calls = []

        def invoke(messages, endpoint):
            calls.append((list(messages), endpoint))
            return "first answer" if len(calls) == 1 else "second answer"

        with mock.patch.object(server, "call_model", side_effect=invoke):
            first = self.client.post("/api/scratchpad", json={"prompt": "first"})
            second = self.client.post("/api/scratchpad", json={"prompt": "second"})

        self.assertEqual(json.loads(first.data)["answer"], "first answer")
        self.assertEqual(json.loads(second.data)["answer"], "second answer")
        self.assertEqual(calls[0][1], self.preferred)
        self.assertEqual(calls[1][0], [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "second"},
        ])

    def test_failed_exchange_is_not_added_to_memory(self):
        seen = []

        def invoke(messages, _endpoint):
            seen.append(list(messages))
            return "[Error] unavailable" if len(seen) == 1 else "ok"

        with mock.patch.object(server, "call_model", side_effect=invoke):
            failed = self.client.post("/api/scratchpad", json={"prompt": "lost"})
            succeeded = self.client.post("/api/scratchpad", json={"prompt": "kept"})

        self.assertIn("error", json.loads(failed.data))
        self.assertEqual(json.loads(succeeded.data)["answer"], "ok")
        self.assertEqual(seen[1], [{"role": "user", "content": "kept"}])

    def test_unavailable_preference_falls_back_to_small(self):
        with mock.patch.object(server, "get_endpoint_by_id", return_value=None), \
             mock.patch.object(server, "call_model", return_value="fallback answer") as call:
            response = self.client.post("/api/scratchpad", json={"prompt": "hello"})
        self.assertEqual(json.loads(response.data)["answer"], "fallback answer")
        self.assertEqual(call.call_args.args[1], self.fallback)

    def test_model_inventory_uses_explicit_resolver_choices(self):
        models = [{
            "id": "gemini/preferred",
            "display_name": "Preferred",
            "type": "api",
            "provider": "gemini",
        }]
        with mock.patch.object(
                server, "list_interactive_endpoints", return_value=models):
            response = self.client.get("/api/aside/models")
        self.assertEqual(json.loads(response.data), {"models": models})

    def test_sidebar_status_and_clear_share_the_aside_window(self):
        seen = []

        def invoke(messages, _endpoint):
            seen.append(list(messages))
            return "answer"

        with mock.patch.object(server, "call_model", side_effect=invoke):
            self.client.post("/api/scratchpad", json={"prompt": "first"})
            status = self.client.get("/api/sidebar/status?panel_id=aside")
            cleared = self.client.post(
                "/api/sidebar/clear", json={"panel_id": "aside"})
            self.client.post("/api/scratchpad", json={"prompt": "second"})

        self.assertEqual(json.loads(status.data)["turn_count"], 1)
        self.assertTrue(json.loads(cleared.data)["ok"])
        self.assertEqual(seen[1], [{"role": "user", "content": "second"}])


if __name__ == "__main__":
    unittest.main()
