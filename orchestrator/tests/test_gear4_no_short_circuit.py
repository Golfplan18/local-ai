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

    def test_run_gear4_still_falls_back_when_endpoint_resolution_fails(self):
        """The remaining Gear-3 fallback path (depth or breadth = None)
        is a correctness guard, not a parallel-safety gate. Keep it."""
        context_pkg = {"cleaned_prompt": "test prompt", "trace_dir": None}
        config: dict = {}

        with mock.patch.object(
            boot, "resolve_gear4_endpoints",
            return_value=(None, None, True),
        ), mock.patch.object(
            boot, "run_gear3", return_value="gear-3-fallback",
        ) as gear3_mock:
            result = boot.run_gear4(
                context_pkg, config, history=None, images=None,
                execution_context="interactive",
            )

        gear3_mock.assert_called_once()
        self.assertEqual(result, "gear-3-fallback")


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
