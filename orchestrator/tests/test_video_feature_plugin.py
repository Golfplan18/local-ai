"""Focused contract tests for the removable in-process video plugin."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from flask import Flask  # noqa: E402
from server import app as server  # noqa: E402
from server.feature_plugins import load_video_plugin  # noqa: E402
from plugins.video.backend import media_library  # noqa: E402


class PluginLoaderTests(unittest.TestCase):
    def test_video_routes_and_assets_are_registered_only_by_the_plugin(self):
        plugin = server._video_plugin.descriptor
        self.assertIsNotNone(plugin)
        endpoints = {
            rule.endpoint for rule in server.app.url_map.iter_rules()
            if rule.endpoint.startswith("plugin_video_")
        }
        self.assertEqual(len(endpoints), len(plugin.routes))
        self.assertIn("plugin_video_capture_start", endpoints)
        self.assertIn("plugin_video_capability_video_generates", endpoints)
        self.assertIn("serve_video_plugin_asset", {
            rule.endpoint for rule in server.app.url_map.iter_rules()
        })
        self.assertNotIn("media_library", sys.modules)
        self.assertNotIn("orchestrator.media_library", sys.modules)
        self.assertIs(sys.modules["plugins.video.backend.media_library"], media_library)
        for asset in (*plugin.scripts, *plugin.styles):
            self.assertTrue((plugin.static_root / asset).is_file(), asset)

    def test_missing_plugin_root_is_a_supported_empty_state(self):
        app = Flask("plugin-absent-test")
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "not-installed"
            loaded = load_video_plugin(
                app,
                lambda _root: self.fail("context must not be built without a plugin"),
                plugin_root=missing,
            )
            env = os.environ.copy()
            env["ORA_FEATURE_PLUGINS_DIR"] = tmp
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            absent_boot = subprocess.run(
                [sys.executable, "-c", """
from server import app as server
assert server._video_plugin.descriptor is None
rules = {rule.rule for rule in server.app.url_map.iter_rules()}
assert '/plugins/video/<path:filename>' not in rules
assert server.app.test_client().get('/plugins/video/video-plugin.js').status_code == 404
"""],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertIsNone(loaded.descriptor)
        self.assertEqual(loaded.asset_tags(), "")
        self.assertEqual(
            absent_boot.returncode,
            0,
            absent_boot.stdout + absent_boot.stderr,
        )


class LifecycleDelegationTests(unittest.TestCase):
    class _Recorder:
        def __init__(self):
            self.phases = []

        def run_lifecycle(self, phase, conversation_id):
            self.phases.append((phase, conversation_id))
            return {"results": {"video": {phase: True}}, "errors": []}

    def test_close_uses_release_not_quiesce(self):
        recorder = self._Recorder()
        with (
            mock.patch.object(server, "_video_plugin", recorder),
            mock.patch.object(server, "_HAS_TRANSCRIPTION", False),
            mock.patch.object(server, "_HAS_JOB_QUEUE", False),
        ):
            result = server._release_conversation_runtime_memory("close-me")
        self.assertEqual(recorder.phases, [("release", "close-me")])
        self.assertFalse(result["errors"])

    def test_delete_quiesces_before_clear(self):
        recorder = self._Recorder()
        with (
            mock.patch.object(server, "_video_plugin", recorder),
            mock.patch.object(server, "_HAS_TRANSCRIPTION", False),
            mock.patch.object(server, "_HAS_JOB_QUEUE", False),
            mock.patch.object(server, "SIDEBAR_WINDOW_AVAILABLE", False),
            mock.patch(
                "orchestrator.document_input.purge_conversation",
                return_value={"jobs": 0, "outputs": 0, "errors": []},
            ),
        ):
            server._quiesce_conversation_workers("delete-me")
            server._clear_conversation_runtime_state("delete-me")
        self.assertEqual(recorder.phases, [
            ("quiesce", "delete-me"),
            ("clear", "delete-me"),
        ])


class MovedRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()
        self.old_sessions = media_library.SESSIONS_ROOT
        self.old_ora_home = server.rp.ORA_HOME
        media_library.SESSIONS_ROOT = self.sessions
        media_library._libraries.clear()
        server.rp.ORA_HOME = self.root
        self.addCleanup(self._restore)

    def _restore(self):
        media_library._libraries.clear()
        media_library.SESSIONS_ROOT = self.old_sessions
        server.rp.ORA_HOME = self.old_ora_home

    def test_moved_transcript_route_returns_normalized_segments(self):
        conversation_id = "plugin-route"
        session = self.sessions / conversation_id
        session.mkdir()
        source = self.root / "clip.wav"
        source.write_bytes(b"fixture")
        source.with_suffix(".whisper.json").write_text(json.dumps({
            "result": {"language": "en"},
            "transcription": [{
                "offsets": {"from": 120, "to": 780},
                "text": " hello ",
            }],
        }))
        library = media_library.get_library(conversation_id)
        library._entries = [{
            "id": "entry-1",
            "source_path": str(source),
            "kind": "audio",
        }]

        response = server.app.test_client().get(
            f"/api/media-library/{conversation_id}/entry-1/transcript"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["segments"], [{
            "start_ms": 120, "end_ms": 780, "text": "hello",
        }])

if __name__ == "__main__":
    unittest.main()
