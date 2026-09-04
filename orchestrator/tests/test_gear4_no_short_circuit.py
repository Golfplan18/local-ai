"""Verify Gear 4 no longer silently downgrades to Gear 3 when both
analysts resolve to local endpoints on the same machine.

Before the 2026-05-19 concurrency overhaul: ``run_gear4`` short-
circuited to ``run_gear3`` whenever ``parallel_safe == False``,
discarding half the mode's adversarial structure (one of Depth or
Breadth wasn't applied). After the overhaul: ``run_gear4`` always
runs the parallel analyst submission; the per-machine MLX mutex
inside ``call_model`` serializes them naturally on a same-machine
all-local setup.

The Gear-3 fallback for missing endpoints is retained as a correctness
guard (Gear 4 needs both depth and breadth resolved).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import boot
from tools import resilience


class TestGear4NoShortCircuit(unittest.TestCase):
    def _both_local_same_machine(self):
        return (
            {"id": "hermes-70b", "name": "hermes-70b", "type": "local",
             "machine": "studio-128"},
            {"id": "kimi-72b", "name": "kimi-72b", "type": "local",
             "machine": "studio-128"},
            False,
        )

    def test_run_gear4_does_not_call_run_gear3_when_parallel_safe_false(self):
        """The marquee behaviour-change verifier."""
        context_pkg = {"cleaned_prompt": "test prompt", "trace_dir": None}
        config: dict = {}

        with mock.patch.object(
            boot, "resolve_gear4_endpoints",
            return_value=self._both_local_same_machine(),
        ), mock.patch.object(
            boot, "run_gear3",
            side_effect=AssertionError(
                "run_gear3 must not be called from inside run_gear4 when "
                "parallel_safe=False — that's the regression we just fixed"
            ),
        ), mock.patch.object(
            boot, "_assemble_step_prompt", return_value="system prompt"
        ), mock.patch.object(
            boot, "_call_with_supplement",
            return_value=("analyst output that is at least 200 characters long " * 10, True, "ok"),
        ), mock.patch.object(
            boot, "_call_with_retry",
            return_value=("step output that meets min-char threshold " * 10, True, "ok"),
        ), mock.patch.object(
            boot, "_extract_structured_verdict",
            return_value="PASS",
        ):
            result = boot.run_gear4(
                context_pkg, config, history=None, images=None,
                execution_context="interactive",
            )

        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)

    def test_run_gear4_delegates_only_on_true_effective_gear3(self):
        """A router-selected Gear 3 delegates independently of scheduling."""
        context_pkg = {
            "cleaned_prompt": "test prompt",
            "trace_dir": None,
            "framework_execution": {"strict": True},
        }
        config: dict = {}

        with mock.patch.object(
            boot, "resolve_gear4_endpoints",
            return_value=boot.Gear4EndpointResolution(None, None, False, 3),
        ), mock.patch.object(
            boot, "run_gear3", return_value="gear-3-fallback",
        ) as gear3_mock:
            result = boot.run_gear4(
                context_pkg, config, history=None, images=None,
                execution_context="interactive",
            )

        gear3_mock.assert_called_once()
        self.assertEqual(result, "gear-3-fallback")
        self.assertNotIn("framework_execution_state", context_pkg)

    def test_over_threshold_local_analysts_run_release_then_run(self):
        """Safety follows the attempted pair, including both recovery lanes."""
        import threading

        memory = sys.modules[boot.should_release_kv_cache.__module__]

        def local(name, ram, engine="mlx"):
            return {
                "id": name, "name": name, "type": "local", "engine": engine,
                "model": name, "model_path": "/models/" + name,
                "ram_resident_gb": ram, "ram_overhead_gb": 0,
            }

        api = {"id": "api", "name": "api", "type": "api"}
        for failed_slot, depth_ram, breadth_ram, fallback, available, expected_releases, release_ok, terminal_failure in (
            (None, 55, 40, None, 100, ["depth"], True, False),
            (None, 10, 10, None, 100, [], True, False),
            ("depth", 55, 40, local("small", 10), 100, ["depth"], True, False),
            ("depth", 55, 40, api, 100, ["depth"], True, False),
            ("depth", 55, 40, local("breadth", 40), 100, ["depth"], True, False),
            ("breadth", 35, 10, local("large", 50, "ollama"), 100, ["depth"], True, False),
            ("both", 0, 0, {
                "depth": local("local-depth", 35),
                "breadth": local("large", 50, "ollama"),
            }, 100, ["local-depth"], True, False),
            ("both", 0, 0, {
                "depth": local("local-depth", 35),
                "breadth": local("large", 50, "ollama"),
            }, None, [], True, False),
            (None, 55, 40, None, 100, ["depth"], False, True),
            (None, 55, 40, api, 100, ["depth"], False, False),
            ("api", 55, 40, api, 100, ["depth"], False, True),
            ("breadth", 35, 10, local("large", 50, "ollama"), 100, ["depth"], False, True),
            (None, 55, 40, local("large", 50), 100, ["depth", "depth"], False, True),
            ("formatter-api", 55, 40, api, 100, ["depth"], False, True),
        ):
            with self.subTest(failed_slot=failed_slot, fallback=fallback, release_ok=release_ok):
                depth, breadth = local("depth", depth_ram), local("breadth", breadth_ram)
                if failed_slot == "both":
                    depth["type"] = breadth["type"] = "api"
                events, active, overlap = [], set(), []
                depth_started = threading.Event()
                fallback_started = threading.Event()
                breadth_started = threading.Event()

                def fallback_for(slot, *_args, **_kwargs):
                    if failed_slot == "formatter-api" and slot == "formatter":
                        return breadth
                    return fallback[slot] if failed_slot == "both" else fallback

                def supplement(_messages, endpoint, step_name, *args, **kwargs):
                    if step_name != "analyst":
                        events.append((step_name, endpoint["name"]))
                        if failed_slot == "formatter-api" and step_name == "formatter":
                            return ("[Error] API transport failed", False, "transport failure")
                        return ("substantive model output " * 20, True, "ok")
                    name = endpoint["name"]
                    events.append(("call", name))
                    if name == "large":
                        overlap.append(bool(active & {"depth", "local-depth"}))
                        fallback_started.set()
                    active.add(name)
                    try:
                        if name == "local-depth" or (name == "depth" and failed_slot == "breadth"):
                            depth_started.set()
                            # Keep the healthy lane in flight while the other
                            # selects a larger fallback. A correct handoff waits.
                            fallback_started.wait(0.1)
                        elif name == "breadth" and failed_slot in {"breadth", "both"}:
                            self.assertTrue(depth_started.wait(1))
                        elif failed_slot is None and depth_ram + breadth_ram <= 80:
                            if name == "depth":
                                self.assertTrue(breadth_started.wait(1))
                            else:
                                breadth_started.set()
                        if name == failed_slot or (failed_slot == "both" and name in {"depth", "breadth"}):
                            return ("", False, "transport failure")
                        return ("substantive model output " * 20, True, "ok")
                    finally:
                        active.remove(name)
                        events.append(("done", name))

                def release(endpoint, *, mlx_evictor=None):
                    self.assertNotIn(endpoint["name"], active)
                    events.append(("release", endpoint["name"]))
                    if failed_slot == "depth" and fallback == breadth:
                        # Loading failed before caching the primary. Confirmed
                        # absence must allow its configured 40 GB fallback.
                        self.assertNotIn(endpoint["model_path"], boot._mlx_cache)
                        return memory.release_kv_cache(endpoint, mlx_evictor=mlx_evictor)
                    return release_ok

                def model_call(messages, endpoint, images=None):
                    step_name = boot._CALL_METADATA_CV.get()["step"].split(":")[0]
                    return supplement(messages, endpoint, step_name)[0]

                with mock.patch.object(
                    boot, "resolve_gear4_endpoints",
                    return_value=boot.Gear4EndpointResolution(depth, breadth, True, 4),
                ), mock.patch.object(memory, "get_available_ram_gb", return_value=available), \
                     mock.patch.object(memory, "get_total_ram_gb", return_value=128), \
                     mock.patch.object(boot, "_mlx_cache", {}), \
                     mock.patch.object(boot, "release_kv_cache", side_effect=release), \
                     mock.patch.object(boot, "_resolve_fallback_endpoint", side_effect=fallback_for), \
                     mock.patch.object(boot, "get_slot_endpoint", return_value=api), \
                     mock.patch.object(boot, "_assemble_step_prompt", return_value="system"), \
                     mock.patch.object(boot, "_run_model_with_tools", side_effect=model_call), \
                     mock.patch.object(boot, "_extract_structured_verdict", return_value="PASS"), \
                     mock.patch.object(boot, "run_gear3") as gear3, \
                     mock.patch.object(boot, "_framework_mark_success") as mark_success:
                    context_pkg = {"cleaned_prompt": "test", "trace_dir": None}
                    if terminal_failure:
                        with self.assertRaises(boot.ModelInvocationFailure) as raised:
                            boot.run_gear4(context_pkg, {})
                        self.assertEqual(raised.exception.kind, "resource_release_failed")
                        self.assertIn("depth", str(raised.exception))
                        mark_success.assert_not_called()
                        if failed_slot != "formatter-api":
                            self.assertEqual(context_pkg.get("_trace_terminal_status"), "error")
                            self.assertFalse(any(kind not in {"call", "done", "release"} for kind, _ in events))
                        else:
                            self.assertIn(("formatter", "api"), events)
                    else:
                        result = boot.run_gear4(context_pkg, {})
                        self.assertIsInstance(result, str)
                        self.assertTrue(result.strip())

                gear3.assert_not_called()
                self.assertFalse(any(overlap), events)
                if not release_ok:
                    self.assertTrue(any(kind == "release" for kind, _ in events))
                    self.assertEqual(set(name for kind, name in events if kind == "release"), {"depth"})
                    blocked = "large" if failed_slot == "breadth" else "breadth"
                    self.assertFalse(any(name == blocked for kind, name in events if kind != "release"), events)
                    if fallback is api:
                        self.assertIn(("call", "api"), events)
                    if terminal_failure and fallback is not None and fallback["type"] == "local":
                        self.assertNotIn(("call", "large"), events)
                else:
                    self.assertEqual([name for kind, name in events if kind == "release"], expected_releases)
                if release_ok and failed_slot is None and expected_releases:
                    self.assertEqual(events[:4], [
                        ("call", "depth"), ("done", "depth"),
                        ("release", "depth"), ("call", "breadth"),
                    ])
                elif release_ok and failed_slot is None:
                    self.assertLess(events.index(("call", "breadth")), events.index(("done", "depth")))

    def test_missing_gear4_endpoints_are_an_explicit_typed_failure(self):
        context_pkg = {"cleaned_prompt": "test prompt", "trace_dir": None}
        with mock.patch.object(
            boot, "resolve_gear4_endpoints",
            return_value=boot.Gear4EndpointResolution(None, None, True, 4),
        ), mock.patch.object(boot, "run_gear3") as gear3_mock:
            with self.assertRaises(boot.ModelInvocationFailure) as raised:
                boot.run_gear4(
                    context_pkg, {}, history=None, images=None,
                    execution_context="interactive",
                )

        self.assertEqual(raised.exception.kind, "endpoint_resolution_failed")
        gear3_mock.assert_not_called()

    def test_failed_ram_probes_are_unknown_and_conservative(self):
        with mock.patch.object(
            resilience.subprocess, "run", side_effect=OSError("unsupported"),
        ):
            self.assertIsNone(resilience.get_available_ram_gb())
            self.assertIsNone(resilience.get_total_ram_gb())
        with mock.patch.object(
            resilience, "check_hardware_constraints", return_value={
                "ram_available_gb": None,
                "ram_total_gb": None,
                "ram_known": False,
                "ram_pressure": True,
                "models_loaded": 0,
                "can_parallel": False,
            },
        ):
            state = resilience.get_degradation_path(4, {})
        self.assertEqual(state.degradation_level, 1)
        self.assertIsNone(state.fallback_gear)
        self.assertIn("unknown", state.reason.lower())

        import threading

        memory = sys.modules[boot.should_release_kv_cache.__module__]
        for total, available in ((None, None), (128, None), (None, 100)):
            with self.subTest(total=total, available=available):
                depth, breadth, _ = self._both_local_same_machine()
                for endpoint in (depth, breadth):
                    endpoint["ram_resident_gb"] = 10
                events = []
                breadth_started = threading.Event()

                def supplement(_messages, endpoint, step_name, *args, **kwargs):
                    if step_name == "analyst":
                        name = endpoint["name"]
                        events.append(("call", name))
                        if name == depth["name"]:
                            breadth_started.wait(0.1)
                        else:
                            breadth_started.set()
                        events.append(("done", name))
                    return ("substantive model output " * 20, True, "ok")

                with mock.patch.object(
                    boot, "resolve_gear4_endpoints",
                    return_value=boot.Gear4EndpointResolution(depth, breadth, True, 4),
                ), mock.patch.object(memory, "get_total_ram_gb", return_value=total), \
                     mock.patch.object(memory, "get_available_ram_gb", return_value=available), \
                     mock.patch.object(boot, "release_kv_cache") as release, \
                     mock.patch.object(boot, "run_gear3") as gear3, \
                     mock.patch.object(boot, "_assemble_step_prompt", return_value="system"), \
                     mock.patch.object(boot, "_call_with_supplement", side_effect=supplement), \
                     mock.patch.object(boot, "_call_with_retry", return_value=("output " * 50, True, "ok")), \
                     mock.patch.object(boot, "_extract_structured_verdict", return_value="PASS"):
                    result = boot.run_gear4({"cleaned_prompt": "test", "trace_dir": None}, {})
                self.assertIsInstance(result, str)
                self.assertEqual(events, [
                    ("call", depth["name"]), ("done", depth["name"]),
                    ("call", breadth["name"]), ("done", breadth["name"]),
                ])
                release.assert_not_called()
                gear3.assert_not_called()

    def test_cache_release_uses_only_selected_distinct_local_models(self):
        depth = {
            "id": "depth-endpoint", "type": "local", "engine": "mlx",
            "model_path": "/models/depth", "ram_resident_gb": 50,
            "ram_overhead_gb": 5,
        }
        breadth = {
            "id": "breadth-endpoint", "type": "local", "engine": "mlx",
            "model_path": "/models/breadth", "ram_resident_gb": 35,
            "ram_overhead_gb": 5,
        }
        with mock.patch.object(
            resilience, "get_available_ram_gb", return_value=100,
        ):
            self.assertTrue(
                resilience.should_release_kv_cache({}, depth, breadth),
            )
            self.assertFalse(
                resilience.should_release_kv_cache({}, depth, dict(depth)),
            )
            self.assertFalse(resilience.should_release_kv_cache(
                {}, depth, {**breadth, "type": "api"},
            ))
            self.assertFalse(resilience.should_release_kv_cache(
                {}, {**depth, "ram_resident_gb": 10},
                {**breadth, "ram_resident_gb": 10},
            ))
            self.assertFalse(resilience.should_release_kv_cache(
                {}, {**depth, "ram_resident_gb": None}, breadth,
            ))

        with mock.patch.object(resilience, "get_available_ram_gb", return_value=None):
            self.assertFalse(resilience.should_release_kv_cache({}, depth, breadth))

        evict = mock.Mock(return_value=True)
        self.assertTrue(resilience.release_kv_cache(depth, mlx_evictor=evict))
        evict.assert_called_once_with("/models/depth")
        with mock.patch("requests.post", return_value=mock.Mock(ok=True)) as post:
            self.assertTrue(resilience.release_kv_cache({
                **breadth, "engine": "ollama", "model": "selected-model",
                "url": "http://fixture.invalid:11435",
            }, mlx_evictor=evict))
        post.assert_called_once_with(
            "http://fixture.invalid:11435/api/generate",
            json={"model": "selected-model", "keep_alive": 0}, timeout=10,
        )
        evict.assert_called_once()


class TestShortCircuitNotInSource(unittest.TestCase):
    """Belt-and-braces source check: the removed line shouldn't come back."""

    def test_short_circuit_string_absent(self):
        boot_text = (ORCH_DIR / "boot.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "if not parallel_safe:\n        return run_gear3(",
            boot_text,
            "The Gear-3-on-fallback short-circuit must stay retired",
        )

    def test_force_parallel_env_hatch_retired(self):
        router_text = (ORCH_DIR / "router.py").read_text(encoding="utf-8")
        self.assertNotIn(
            'os.environ.get("ORA_FORCE_GEAR4_PARALLEL") == "1"',
            router_text,
            "The ORA_FORCE_GEAR4_PARALLEL escape hatch became redundant — "
            "the new default is always parallel + mutex-serialize",
        )


if __name__ == "__main__":
    unittest.main()
