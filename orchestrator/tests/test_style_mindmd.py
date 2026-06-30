"""Slice E: custom-values onboarding — load_boot_md SELECT (gated on the toggle)
and the MindSpec-interview SAVE gate. The SAVE test patches file_write so it
never touches the real ~/ora/mind.md."""

import os
import sys

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
        assert "[YOUR VALUES" not in boot.load_boot_md()
    finally:
        user_settings.get_setting = _orig_get


def test_select_on_injects_mind_md():
    if not os.path.isfile(boot.MIND_MD):
        print("  (~/ora/mind.md absent — skipping select-on)")
        return
    _set_custom(True)
    try:
        assert "[YOUR VALUES" in boot.load_boot_md()
    finally:
        user_settings.get_setting = _orig_get


def test_save_gate_self_mode_only():
    import file_ops as fo   # top-level via TOOLS_DIR (boot put it on sys.path)
    captured = []
    orig = fo.file_write
    fo.file_write = lambda path, content: captured.append((path, content))
    try:
        me._maybe_persist_self_mindspec("mindspec-interview", "MSI-Self", "MY VALUES")
        assert captured, "self interview should be saved"
        assert captured[-1][0].endswith("mind.md") and captured[-1][1] == "MY VALUES"
        captured.clear()
        me._maybe_persist_self_mindspec("mindspec-interview", "MSI-Agent", "X")  # wrong mode
        me._maybe_persist_self_mindspec("other-framework", "MSI-Self", "X")      # wrong fw
        me._maybe_persist_self_mindspec("mindspec-interview", "MSI-Self", "")    # empty
        assert not captured, "must not write for non-self / non-interview / empty output"
    finally:
        fo.file_write = orig


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
