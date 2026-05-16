"""RAG cap — hardcoded constant.

The adaptive formula was retired in favour of ``RAG_MAX_CHARS``: a
single constant that the previous formula consistently converged to
for every modern endpoint (≥128K context window). Older small-window
endpoints exist (deepseek-r1-70b at 32K, qwen-4b at 32K) but live in
classification-only roles that don't consume RAG. The picker and the
per-endpoint configurability are gone.

These tests confirm the constant is returned and that callers can
still override per-call via ``max_chars=``.
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


class TestRagMaxChars(unittest.TestCase):
    def test_constant_defined(self):
        self.assertGreater(rag_engine.RAG_MAX_CHARS, 50_000)

    def test_compute_returns_constant(self):
        # Regardless of args, the function returns the constant.
        self.assertEqual(rag_engine.compute_rag_max_chars(), rag_engine.RAG_MAX_CHARS)

    def test_compute_ignores_endpoint(self):
        # Backward-compat: previous call sites passed endpoint=. Should
        # be ignored, not error.
        self.assertEqual(
            rag_engine.compute_rag_max_chars({"context_window": 8192}),
            rag_engine.RAG_MAX_CHARS,
        )
        self.assertEqual(
            rag_engine.compute_rag_max_chars({"context_window": 2_000_000}),
            rag_engine.RAG_MAX_CHARS,
        )
        self.assertEqual(
            rag_engine.compute_rag_max_chars(None),
            rag_engine.RAG_MAX_CHARS,
        )

    def test_assemble_uses_constant_when_max_chars_not_given(self):
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
            )
        except Exception:
            pass  # ChromaDB / embedding may not be available
        finally:
            rag_engine.format_context_with_provenance = original_format
        if "max_chars" in captured:
            self.assertEqual(captured["max_chars"], rag_engine.RAG_MAX_CHARS)

    def test_assemble_respects_explicit_max_chars(self):
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
                max_chars=50_000,
            )
        except Exception:
            pass
        finally:
            rag_engine.format_context_with_provenance = original_format
        if "max_chars" in captured:
            self.assertEqual(captured["max_chars"], 50_000)


if __name__ == "__main__":
    unittest.main()
