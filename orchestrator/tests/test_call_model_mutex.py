"""Verify call_model holds the per-machine MLX mutex for local endpoints
and the in-flight counter for API endpoints.

Stubs out the actual model invocation so the test runs without a server
or model files.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import boot
import mlx_mutex


class TestCallModelMutex(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_local_call_holds_machine_mutex_during_invocation(self):
        """While call_local_endpoint runs, try_acquire on the same machine
        must fail (mutex is held)."""
        machine_id = "studio-128"
        observed = {}

        def fake_local(messages, endpoint, images=None):
            with mlx_mutex.try_acquire(machine_id) as got_it:
                observed["mutex_was_free"] = got_it
            return "local-result"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            result = boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "local", "machine": machine_id, "name": "hermes"},
            )

        self.assertEqual(result, "local-result")
        self.assertFalse(
            observed["mutex_was_free"],
            "Mutex must be held during the local call, not free",
        )

    def test_local_call_releases_mutex_after_return(self):
        with mock.patch.object(boot, "call_local_endpoint", return_value="ok"):
            boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "local", "machine": "studio-128", "name": "hermes"},
            )
        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertTrue(got_it, "Mutex should be free after call_model returns")

    def test_local_call_releases_mutex_on_exception(self):
        def boom(messages, endpoint, images=None):
            raise RuntimeError("model crashed")

        with mock.patch.object(boot, "call_local_endpoint", side_effect=boom):
            with self.assertRaises(RuntimeError):
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "local", "machine": "studio-128", "name": "hermes"},
                )
        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertTrue(got_it, "Mutex must be released on exception")

    def test_missing_machine_field_defaults_to_studio_128(self):
        observed = {}

        def fake_local(messages, endpoint, images=None):
            observed["waiting_on_default"] = mlx_mutex.waiting_count("studio-128")
            with mlx_mutex.try_acquire("studio-128") as got_it:
                observed["default_machine_was_free"] = got_it
            return "ok"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "local", "name": "hermes"},
            )

        self.assertFalse(
            observed["default_machine_was_free"],
            "When endpoint omits 'machine', call_model must default to studio-128",
        )

    def test_two_local_calls_on_same_machine_serialize(self):
        """The whole point: two threads can't both be inside
        call_local_endpoint on the same machine simultaneously."""
        machine_id = "studio-128"
        in_flight = {"count": 0, "max_seen": 0, "lock": threading.Lock()}

        def fake_local(messages, endpoint, images=None):
            with in_flight["lock"]:
                in_flight["count"] += 1
                in_flight["max_seen"] = max(in_flight["max_seen"], in_flight["count"])
            time.sleep(0.05)
            with in_flight["lock"]:
                in_flight["count"] -= 1
            return "ok"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            def call():
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "local", "machine": machine_id, "name": "hermes"},
                )

            threads = [threading.Thread(target=call) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        self.assertEqual(
            in_flight["max_seen"], 1,
            "At most one local call may be in flight per machine at a time",
        )

    def test_two_local_calls_on_different_machines_run_in_parallel(self):
        in_flight = {"count": 0, "max_seen": 0, "lock": threading.Lock()}

        def fake_local(messages, endpoint, images=None):
            with in_flight["lock"]:
                in_flight["count"] += 1
                in_flight["max_seen"] = max(in_flight["max_seen"], in_flight["count"])
            time.sleep(0.1)
            with in_flight["lock"]:
                in_flight["count"] -= 1
            return "ok"

        with mock.patch.object(boot, "call_local_endpoint", side_effect=fake_local):
            def call(machine):
                boot.call_model(
                    [{"role": "user", "content": "hi"}],
                    {"type": "local", "machine": machine, "name": "hermes"},
                )

            ta = threading.Thread(target=call, args=("studio-128",))
            tb = threading.Thread(target=call, args=("studio-64",))
            ta.start()
            tb.start()
            ta.join(timeout=5)
            tb.join(timeout=5)

        self.assertEqual(
            in_flight["max_seen"], 2,
            "Different machines should allow concurrent local calls",
        )


class TestCallModelApiTracking(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_api_call_increments_in_flight_counter(self):
        observed = {}

        def fake_api(messages, endpoint, images=None):
            observed["in_flight_during_call"] = mlx_mutex.in_flight_count("test-api")
            return "api-result"

        with mock.patch.object(boot, "call_api_endpoint", side_effect=fake_api):
            result = boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "api", "id": "test-api"},
            )

        self.assertEqual(result, "api-result")
        self.assertEqual(observed["in_flight_during_call"], 1)
        self.assertEqual(mlx_mutex.in_flight_count("test-api"), 0)

    def test_api_call_does_not_block_on_local_machine_mutex(self):
        """API calls must not be gated by a local-machine mutex —
        even when the local mutex is held by another thread."""
        a_holding = threading.Event()
        release_a = threading.Event()

        def thread_a():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        ta = threading.Thread(target=thread_a)
        ta.start()
        a_holding.wait(timeout=2)

        with mock.patch.object(boot, "call_api_endpoint", return_value="api-ok"):
            start = time.time()
            result = boot.call_model(
                [{"role": "user", "content": "hi"}],
                {"type": "api", "id": "openrouter"},
            )
            elapsed = time.time() - start

        release_a.set()
        ta.join(timeout=2)

        self.assertEqual(result, "api-ok")
        self.assertLess(elapsed, 0.5, "API call should not wait on local mutex")


class TestDialogueContinuityCallPaths(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()
        self.endpoint = {
            "type": "api", "id": "continuity-test",
            "context_window": 100_000, "max_tokens": 1_000,
        }
        self.history = [
            {"role": "user", "content": "continuity-user-marker"},
            {"role": "assistant", "content": "continuity-assistant-marker"},
        ]
        self.current = [
            {"role": "system", "content": "current-system"},
            {"role": "user", "content": "current-user"},
        ]
        self.context_pkg = {
            "optional_context_units": [{
                "lane": "contributor",
                "unit_id": "contributor-marker-unit",
                "source_id": "selected-source-0",
                "explicit_index": 0,
                "content": "contributor-reference-marker",
            }],
            "context_source_inventory": {"sources": [{
                "source_id": "selected-source-0",
                "explicit_index": 0,
                "status": "available",
            }]},
        }

    def _assert_one_continuity_lane(self, messages):
        contents = [message.get("content") for message in messages]
        self.assertEqual(contents.count("continuity-user-marker"), 1)
        self.assertEqual(contents.count("continuity-assistant-marker"), 1)
        self.assertLess(
            contents.index("continuity-user-marker"),
            contents.index("current-user"),
        )

    def _assert_one_optional_lane(self, messages):
        references = [
            message.get("content", "") for message in messages
            if "OPTIONAL REFERENCE DATA" in message.get("content", "")
        ]
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].count("contributor-reference-marker"), 1)

    def test_gear1_and_gear2_single_pass_calls_receive_continuity(self):
        for gear in (1, 2):
            captured = []

            def transport(messages, endpoint, images=None):
                captured.append(messages)
                return "ok"

            with self.subTest(gear=gear), mock.patch.object(
                boot, "call_api_endpoint", side_effect=transport,
            ):
                result = boot.run_single_pass_with_tools(
                    list(self.current), self.endpoint,
                    slot="fast" if gear == 2 else "primary",
                    gear=gear, config_name=None,
                    history=self.history,
                    context_pkg=self.context_pkg,
                )
                self.assertEqual(result, "ok")
                self._assert_one_continuity_lane(captured[0])
                self._assert_one_optional_lane(captured[0])

    def test_gear3_wrapper_carries_continuity_to_physical_calls(self):
        captured = []

        def transport(messages, endpoint, images=None):
            captured.append(messages)
            return "gear3-ok"

        def implementation(*_args, **_kwargs):
            return boot.call_model(list(self.current), self.endpoint)

        with mock.patch.object(
            boot, "_run_gear3_impl", side_effect=implementation,
        ), mock.patch.object(
            boot, "call_api_endpoint", side_effect=transport,
        ):
            self.assertEqual(
                boot.run_gear3(
                    dict(self.context_pkg), {}, history=self.history,
                ), "gear3-ok",
            )
        self._assert_one_continuity_lane(captured[0])
        self._assert_one_optional_lane(captured[0])

    def test_gear4_worker_inherits_continuity_context(self):
        from concurrent.futures import ThreadPoolExecutor

        captured = []

        def transport(messages, endpoint, images=None):
            captured.append(messages)
            return "gear4-ok"

        def implementation(*_args, **_kwargs):
            with ThreadPoolExecutor(max_workers=1) as executor:
                return boot._submit_with_context(
                    executor,
                    boot.call_model,
                    list(self.current),
                    self.endpoint,
                ).result(timeout=2)

        with mock.patch.object(
            boot, "_run_gear4_impl", side_effect=implementation,
        ), mock.patch.object(
            boot, "call_api_endpoint", side_effect=transport,
        ):
            self.assertEqual(
                boot.run_gear4(
                    dict(self.context_pkg), {}, history=self.history,
                ), "gear4-ok",
            )
        self._assert_one_continuity_lane(captured[0])
        self._assert_one_optional_lane(captured[0])

    def test_physical_call_trace_records_non_sensitive_context_coverage(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            boot.pipeline_trace, "TRACE_ROOT", str(Path(temp_dir) / "traces"),
        ):
            trace_dir = boot.pipeline_trace.start_trace(
                "coverage-test", raw_input="current-user",
            )
            self.assertIsNotNone(trace_dir)
            trace_token = boot.set_turn_trace_context(trace_dir)
            stage_tokens = boot.set_model_stage_context(
                "gear2-single-pass", slot="fast", gear=2,
                config_name="test-config",
            )
            optional_token = boot.set_optional_context_context(
                self.context_pkg["optional_context_units"],
                self.context_pkg["context_source_inventory"],
            )
            try:
                boot.prepare_messages_with_continuity(
                    list(self.current), self.endpoint, history=self.history,
                )
                boot._record_physical_model_call_config(
                    self.endpoint, max_tokens=1_000,
                    attempt_index=1, provider_attempt="hermetic-test",
                )
            finally:
                boot.reset_optional_context_context(optional_token)
                boot.reset_model_stage_context(stage_tokens)
                boot.reset_turn_trace_context(trace_token)

            records = [
                json.loads(line) for line in (
                    Path(trace_dir) / "model-call-config.jsonl"
                ).read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(len(records), 1)
        coverage = records[0]["context_coverage"]
        self.assertEqual(records[0]["step"], "gear2-single-pass")
        self.assertGreater(coverage["budget"]["used_tokens"], 0)
        self.assertEqual(
            coverage["budget"]["capacity_tokens"],
            self.endpoint["context_window"]
            - boot._endpoint_output_reserve(
                self.endpoint, self.endpoint["context_window"],
            )
            - 128,
        )
        self.assertEqual(coverage["lanes"]["history"]["selected_units"], 1)
        self.assertEqual(coverage["lanes"]["contributor"]["selected_units"], 1)
        self.assertEqual(coverage["source_counts"], {"represented": 1})
        self.assertEqual(coverage["deferred_unit_count"], 0)
        self.assertNotIn("title", json.dumps(coverage).casefold())


class TestDialogueTokenAccounting(unittest.TestCase):
    class _QuarterTokenizer:
        @staticmethod
        def _render(messages):
            return "".join(
                f"<{message['role']}>{message['content']}</{message['role']}>"
                for message in messages
            ) + "<assistant>"

        def apply_chat_template(self, messages, *, tokenize=False,
                                add_generation_prompt=True, **_kwargs):
            rendered = self._render(messages)
            if tokenize:
                return list(range(max(1, (len(rendered) + 3) // 4)))
            return rendered

        def encode(self, text):
            return list(range(max(1, (len(text) + 3) // 4)))

    def test_cached_exact_tokenizer_uses_more_of_ordinary_text_budget(self):
        history = []
        for index in range(30):
            history.extend([
                {"role": "user", "content": f"u-{index}-" + ("x" * 400)},
                {"role": "assistant",
                 "content": f"a-{index}-" + ("y" * 400)},
            ])
        required = [
            {"role": "system", "content": "required system"},
            {"role": "user", "content": "required current"},
        ]
        exact_endpoint = {
            "type": "local", "engine": "mlx", "model": "/fake/exact",
            "context_window": 4_000, "max_tokens": 500,
        }
        fallback_endpoint = {
            **exact_endpoint,
            "model": "/fake/no-tokenizer",
        }
        boot._mlx_cache["/fake/exact"] = (
            object(), self._QuarterTokenizer(),
        )
        try:
            _exact_messages, exact_stats = boot.pack_conversation_history(
                history, exact_endpoint, required,
            )
            _fallback_messages, fallback_stats = boot.pack_conversation_history(
                history, fallback_endpoint, required,
            )
        finally:
            boot._mlx_cache.pop("/fake/exact", None)

        self.assertEqual(exact_stats["token_counting"], "exact_chat_template")
        self.assertEqual(
            fallback_stats["token_counting"], "utf8_byte_upper_bound",
        )
        self.assertGreater(
            exact_stats["history_selected_units"],
            fallback_stats["history_selected_units"],
        )
        self.assertLess(exact_stats["history_selected_units"], 30)
        self.assertLessEqual(
            exact_stats["estimated_call_input_tokens"],
            exact_stats["safe_input_capacity"],
        )

    def test_unicode_fallback_is_a_utf8_byte_bound_with_framing(self):
        content = "😀界" * 1_000
        messages = [{"role": "user", "content": content}]

        estimate = boot.estimate_message_tokens(messages, {
            "type": "api", "model": "no-local-tokenizer",
        })

        self.assertGreaterEqual(estimate, len(content.encode("utf-8")))
        self.assertGreater(
            boot.estimate_message_tokens(
                [{"role": "user", "content": ""}],
            ),
            0,
        )

    def test_mlx_default_generation_request_matches_reserved_allowance(self):
        captured = {}
        tokenizer = self._QuarterTokenizer()

        def generate(_model, _tokenizer, **kwargs):
            captured.update(kwargs)
            return "local answer"

        fake_mlx = types.SimpleNamespace(
            load=lambda _path: (object(), tokenizer),
            generate=generate,
        )
        endpoint = {
            "type": "local", "engine": "mlx", "model": "/fake/mlx-model",
            "context_window": 100_000,
        }
        boot._mlx_cache.pop("/fake/mlx-model", None)
        try:
            with mock.patch.dict(sys.modules, {"mlx_lm": fake_mlx}), \
                 mock.patch.object(boot, "_model_max_output_tokens",
                                   return_value=None):
                result = boot.call_local_endpoint(
                    [{"role": "user", "content": "local input"}],
                    endpoint,
                )
        finally:
            boot._mlx_cache.pop("/fake/mlx-model", None)

        self.assertEqual(result, "local answer")
        self.assertEqual(captured["max_tokens"], 32_000)
        self.assertEqual(
            captured["max_tokens"],
            boot._endpoint_initial_output_tokens(
                endpoint, endpoint["context_window"],
            ),
        )

class TestUnknownEndpoint(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_unknown_type_returns_error_string_without_mutex(self):
        result = boot.call_model(
            [{"role": "user", "content": "hi"}],
            {"type": "weird"},
        )
        self.assertIn("Unknown endpoint type", result)
        with mlx_mutex.try_acquire("studio-128") as got_it:
            self.assertTrue(got_it)


if __name__ == "__main__":
    unittest.main()
