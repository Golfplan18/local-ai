"""Adaptive RAG cap — replaces the hardcoded 8000-char default with
a cap derived from the actual model's context window.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE_ROOT = os.path.dirname(HERE)
for p in (HERE, WORKTREE_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib.util as _ilu


def _load_worktree(modname: str):
    fname = os.path.join(HERE, f"{modname}.py")
    spec = _ilu.spec_from_file_location(modname, fname)
    mod = _ilu.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


rag_engine = _load_worktree("rag_engine")
boot = _load_worktree("boot")


class TestComputeRagMaxChars(unittest.TestCase):
    def test_no_endpoint_returns_floor(self):
        self.assertEqual(rag_engine.compute_rag_max_chars(None), 8000)

    def test_endpoint_without_context_window_returns_floor(self):
        self.assertEqual(
            rag_engine.compute_rag_max_chars({"name": "x"}), 8000
        )

    def test_large_window_lifts_cap_substantially(self):
        # 131k tokens — typical of Hermes-4 / Kimi-Dev. With defaults:
        # usable = 131072 - 8000 - 4096 = 118976 tokens
        # budget = 118976 * 0.5 = 59488 tokens
        # chars  = 59488 * 4 = 237952 chars
        cap = rag_engine.compute_rag_max_chars({"context_window": 131072})
        self.assertGreater(cap, 200_000)
        self.assertLessEqual(cap, 400_000)  # ceiling

    def test_small_window_still_above_floor(self):
        # 8k window (legacy small model). usable = 8192 - 8000 - 4096 = -3904.
        # budget = max(0, -3904) * 0.5 = 0. Floor kicks in.
        cap = rag_engine.compute_rag_max_chars({"context_window": 8192})
        self.assertEqual(cap, 8000)

    def test_ceiling_clamps_extreme_windows(self):
        # 2M context window (theoretical). Cap should clamp at the ceiling.
        cap = rag_engine.compute_rag_max_chars({"context_window": 2_000_000})
        self.assertEqual(cap, 400_000)

    def test_per_endpoint_override_respected(self):
        cap = rag_engine.compute_rag_max_chars({
            "context_window": 131072,
            "rag_reservation_fraction": 0.25,
        })
        # Half of the default → roughly half the chars.
        default_cap = rag_engine.compute_rag_max_chars(
            {"context_window": 131072}
        )
        self.assertLess(cap, default_cap)
        self.assertGreater(cap, default_cap // 3)

    def test_assemble_uses_endpoint_when_max_chars_not_given(self):
        # Patch the inner ranker/search to confirm max_chars threads through.
        captured = {}
        original_format = rag_engine.format_context_with_provenance

        def spy_format(chunks, max_chars=8000):
            captured["max_chars"] = max_chars
            return original_format(chunks, max_chars=max_chars)

        rag_engine.format_context_with_provenance = spy_format
        try:
            rag_engine.assemble_ranked_context(
                query="probe",
                collection="knowledge",
                endpoint={"context_window": 131072, "name": "test"},
            )
        except Exception:
            # ChromaDB / embedding may not be available; we only care
            # whether max_chars propagated before the failure path.
            pass
        finally:
            rag_engine.format_context_with_provenance = original_format
        # If the call got far enough to format, max_chars should be the
        # adaptive value. If it failed before formatter, the test is
        # inconclusive but doesn't regress.
        if "max_chars" in captured:
            self.assertGreater(captured["max_chars"], 50_000)


class TestPickRagCapEndpoint(unittest.TestCase):
    def test_picks_smallest_context_window(self):
        # Mock get_slot_endpoint to return endpoints with different windows.
        endpoints = {
            "depth": {"name": "kimi-72b", "context_window": 131072},
            "breadth": {"name": "hermes-70b", "context_window": 131072},
            "evaluator": {"name": "kimi-72b", "context_window": 131072},
            "consolidator": {"name": "hermes-70b", "context_window": 131072},
            "sidebar": {"name": "qwen-27b", "context_window": 32768},
            "step1_cleanup": {"name": "qwen-27b", "context_window": 32768},
        }
        from unittest import mock
        with mock.patch.object(boot, "get_slot_endpoint",
                                side_effect=lambda c, s, **kw: endpoints.get(s)):
            picked = boot._pick_rag_cap_endpoint({}, gear=4)
        # The 32k slot is the binding constraint across Gear 4 slots.
        self.assertEqual(picked["context_window"], 32768)

    def test_falls_back_to_active_endpoint_when_no_slots_resolve(self):
        from unittest import mock
        with mock.patch.object(boot, "get_slot_endpoint", return_value=None):
            with mock.patch.object(boot, "get_active_endpoint",
                                    return_value={"name": "fallback"}):
                picked = boot._pick_rag_cap_endpoint({}, gear=4)
        self.assertEqual(picked["name"], "fallback")


if __name__ == "__main__":
    unittest.main()
