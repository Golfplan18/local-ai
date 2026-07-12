"""Slice B: _resolve_effective_style_id precedence (project default > engine
default > None). Patches the lazily-imported lookups on their modules."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Import the worktree project modules BEFORE boot. boot.py hardcodes
# WORKSPACE=~/ora and prepends ~/ora/orchestrator to sys.path at import time;
# importing these first caches the worktree copies so the lazy lookups in
# _resolve_effective_style_id resolve to them. (In production WORKSPACE *is*
# ~/ora, so this ordering concern is test-only.)
import project_registry   # noqa: E402
import active_project     # noqa: E402
import user_settings      # noqa: E402
import boot               # noqa: E402

_orig = (active_project.get_active_project, project_registry.get_project)
# Neutralize the account-default (settings) source by default; the tests that
# exercise it set get_setting explicitly and reset to this neutralizer.
user_settings.get_setting = lambda *a, **k: None


def _patch(nexus, proj):
    active_project.get_active_project = lambda: nexus
    project_registry.get_project = lambda n, **k: proj


def _restore():
    active_project.get_active_project, project_registry.get_project = _orig


def _proj(default_style_id):
    return project_registry.Project(
        nexus="fake", name="Fake", root=Path("/tmp/fake"),
        default_style_id=default_style_id,
    )


def test_project_default_wins():
    _patch("fake", _proj("business"))
    try:
        assert boot._resolve_effective_style_id({}) == "business"
        # one-off is applied later (server merge); here project beats engine cfg
        assert boot._resolve_effective_style_id({"default_style_id": "explainer"}) == "business"
    finally:
        _restore()


def test_engine_default_when_no_project():
    _patch("commons", None)   # commons/unregistered → get_project None
    try:
        assert boot._resolve_effective_style_id({"default_style_id": "technical"}) == "technical"
        assert boot._resolve_effective_style_id({}) is None
    finally:
        _restore()


def test_engine_default_when_no_project_legacy_general():
    _patch("general", None)   # legacy id — still recognized permanently
    try:
        assert boot._resolve_effective_style_id({"default_style_id": "technical"}) == "technical"
        assert boot._resolve_effective_style_id({}) is None
    finally:
        _restore()


def test_project_with_no_style_falls_through_to_engine():
    _patch("fake", _proj(None))
    try:
        assert boot._resolve_effective_style_id({"default_style_id": "academic"}) == "academic"
        assert boot._resolve_effective_style_id({}) is None
    finally:
        _restore()


def test_lookup_failure_is_safe():
    active_project.get_active_project = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        assert boot._resolve_effective_style_id({"default_style_id": "business"}) == "business"
        assert boot._resolve_effective_style_id({}) is None
    finally:
        _restore()


def test_manifest_field_parses_and_rejects_bad():
    import json
    import tempfile
    d = tempfile.mkdtemp()
    good = Path(d) / "ora-project.json"
    good.write_text(json.dumps({"nexus": "demo", "name": "Demo", "default_style_id": "explainer"}))
    proj = project_registry._parse_project_from_manifest(good, Path(d))
    assert proj.default_style_id == "explainer"
    bad = Path(d) / "bad.json"
    bad.write_text(json.dumps({"nexus": "demo", "name": "Demo", "default_style_id": ""}))
    try:
        project_registry._parse_project_from_manifest(bad, Path(d))
    except project_registry.ManifestError:
        return
    raise AssertionError("empty default_style_id should raise ManifestError")


def test_settings_default_used_when_no_project():
    _patch("commons", None)   # no active project
    user_settings.get_setting = lambda path, default=None: (
        "marketing" if path == "styles.default_id" else default)
    try:
        assert boot._resolve_effective_style_id({}) == "marketing"
    finally:
        user_settings.get_setting = lambda *a, **k: None
        _restore()


def test_settings_default_used_when_no_project_legacy_general():
    _patch("general", None)   # legacy id — still recognized permanently
    user_settings.get_setting = lambda path, default=None: (
        "marketing" if path == "styles.default_id" else default)
    try:
        assert boot._resolve_effective_style_id({}) == "marketing"
    finally:
        user_settings.get_setting = lambda *a, **k: None
        _restore()


def test_project_beats_settings_default():
    _patch("fake", _proj("business"))
    user_settings.get_setting = lambda path, default=None: "marketing"
    try:
        assert boot._resolve_effective_style_id({}) == "business"
    finally:
        user_settings.get_setting = lambda *a, **k: None
        _restore()


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
