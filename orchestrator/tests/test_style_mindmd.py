"""mind.md user-context gating and the MindSpec self-mode archive gate."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import user_settings              # noqa: E402  (before boot — WORKSPACE shadowing)
import milestone_executor as me   # noqa: E402  (before boot → the worktree copy)
import boot                       # noqa: E402

_orig_get = user_settings.get_setting


def _set_custom(val):
    user_settings.get_setting = lambda path, default=None: (
        val if path == "styles.use_custom_values" else default)


def test_select_off_by_default():
    user_settings.get_setting = lambda *a, **k: False
    try:
        assert "[USER CONTEXT" not in boot.load_boot_md()
    finally:
        user_settings.get_setting = _orig_get


def test_select_on_injects_mind_md():
    if not os.path.isfile(boot.MIND_MD):
        print("  (~/ora/mind.md absent — skipping select-on)")
        return
    _set_custom(True)
    try:
        assert "[USER CONTEXT" in boot.load_boot_md()
        prompt = boot.load_boot_md()
        assert "subordinate to the Ora constitution" in prompt
        assert "supersedes the default Mind Seeds" not in prompt
    finally:
        user_settings.get_setting = _orig_get


def test_save_gate_self_mode_only():
    old_home = me._rp.ORA_HOME
    with tempfile.TemporaryDirectory() as tmp:
        me._rp.ORA_HOME = Path(tmp)
        import persona
        old_compile = persona.compile_self_spec
        old_resolve = persona.resolve_persona
        try:
            persona.resolve_persona = lambda *a, **k: {"id": "ora"}
            persona.compile_self_spec = lambda *a, **k: {
                "ok": True, "id": "ora-personalized", "active": False,
            }
            me._maybe_persist_self_mindspec(
                "mindspec-interview", "MSI-Self", "MY VALUES")
            archive = Path(tmp) / "mindspec" / "self-spec.md"
            assert archive.read_text() == "MY VALUES"
            archive.unlink()
            me._maybe_persist_self_mindspec(
                "mindspec-interview", "MSI-Agent", "X")  # wrong mode
            me._maybe_persist_self_mindspec(
                "other-framework", "MSI-Self", "X")      # wrong fw
            me._maybe_persist_self_mindspec(
                "mindspec-interview", "MSI-Self", "")    # empty
            assert not archive.exists(), (
                "must not write for non-self / non-interview / empty output")
        finally:
            persona.compile_self_spec = old_compile
            persona.resolve_persona = old_resolve
            me._rp.ORA_HOME = old_home


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS  " + t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL  %s -> %r" % (t.__name__, exc))
    print("\n%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
