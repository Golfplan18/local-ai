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
        """The memory guard serializes only the analyst pair in call order."""
        context_pkg = {"cleaned_prompt": "test prompt", "trace_dir": None}
        depth, breadth, _ = self._both_local_same_machine()
        events = []

        def supplement(_messages, endpoint, step_name, *args, **kwargs):
            if step_name == "analyst":
                events.append(("call", endpoint["name"]))
            return ("substantive model output " * 20, True, "ok")

        def release(endpoint, *, mlx_evictor=None):
            events.append(("release", endpoint["name"]))
            return True

        with mock.patch.object(
            boot, "resolve_gear4_endpoints",
            return_value=boot.Gear4EndpointResolution(
                depth, breadth, False, 4),
        ), mock.patch.object(
            boot, "should_release_kv_cache", return_value=True,
        ), mock.patch.object(
            boot, "release_kv_cache", side_effect=release,
        ), mock.patch.object(
            boot, "_assemble_step_prompt", return_value="system prompt",
        ), mock.patch.object(
            boot, "_call_with_supplement", side_effect=supplement,
        ), mock.patch.object(
            boot, "_call_with_retry",
            return_value=("step output " * 30, True, "ok"),
        ), mock.patch.object(
            boot, "_extract_structured_verdict", return_value="PASS",
        ):
            result = boot.run_gear4(
                context_pkg, {}, history=None, images=None,
                execution_context="interactive",
            )

        self.assertIsInstance(result, str)
        self.assertEqual(events[:3], [
            ("call", "hermes-70b"),
            ("release", "hermes-70b"),
            ("call", "kimi-72b"),
        ])

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

        evict = mock.Mock(return_value=True)
        self.assertTrue(resilience.release_kv_cache(depth, mlx_evictor=evict))
        evict.assert_called_once_with("/models/depth")


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
