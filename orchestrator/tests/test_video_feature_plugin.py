"""Focused contract tests for the removable in-process video plugin."""

from __future__ import annotations

import ast
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

    def test_plugin_registration_does_not_own_paid_job_recovery(self):
        from plugins import video

        plugin_root = ROOT / "plugins" / "video"
        context = server._feature_plugin_context(plugin_root)
        with mock.patch(
            "orchestrator.integrations.replicate.reconcile_unfinished_jobs",
        ) as reconcile:
            descriptor = video.register(context)
        self.assertEqual(descriptor.plugin_id, "video")
        reconcile.assert_not_called()

    def test_core_startup_resumes_style_training_when_video_is_absent(self):
        from orchestrator import job_queue as job_queue_module
        from orchestrator.integrations import replicate
        from orchestrator.job_queue import JobQueue

        app = Flask("plugin-absent-recovery-test")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loaded = load_video_plugin(
                app,
                lambda _root: self.fail("missing video must build no context"),
                plugin_root=root / "not-installed",
            )
            self.assertIsNone(loaded.descriptor)

            conversation_id = "style-restart"
            dialogue_dir = root / "sessions" / conversation_id
            dialogue_dir.mkdir(parents=True)
            (dialogue_dir / "conversation.json").write_text(
                json.dumps({
                    "conversation_id": conversation_id,
                    "messages": [],
                }),
                encoding="utf-8",
            )
            queue = JobQueue(sessions_root=root / "sessions")
            job = queue.dispatch(
                conversation_id,
                "style_trains",
                {"name": "saved-style"},
                metadata={"provider": "replicate", "model": "trainer"},
            )
            queue.begin_submission(
                conversation_id,
                job["id"],
                {
                    "provider_submission_state": "bound",
                    "provider_prediction_id": "saved-style-prediction",
                    "provider_conversation_id": conversation_id,
                    "provider_job_id": job["id"],
                },
            )
            client = mock.Mock()
            client.poll.return_value = {
                "id": "saved-style-prediction",
                "status": "failed",
                "error": "controlled terminal result",
            }
            with mock.patch.object(job_queue_module, "_default_queue", queue), \
                 mock.patch.object(
                     job_queue_module, "_default_recovery_started", False,
                 ), \
                 mock.patch.object(
                     replicate, "ReplicateClient", return_value=client,
                 ):
                threads = job_queue_module.start_default_queue_recovery()
                for thread in threads:
                    thread.join(5.0)
                    self.assertFalse(thread.is_alive())
                repeated = job_queue_module.start_default_queue_recovery()

            self.assertEqual(len(threads), 1)
            self.assertEqual(repeated, [])
            client.poll.assert_called_once_with("saved-style-prediction")
            client.create.assert_not_called()
            self.assertEqual(
                queue.get_job(conversation_id, job["id"])["status"], "failed",
            )

    def test_server_main_starts_paid_job_recovery_before_other_startup_work(self):
        tree = ast.parse((ROOT / "server" / "app.py").read_text(encoding="utf-8"))
        main_guard = next(
            node for node in tree.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "_select_server_port"
                for child in ast.walk(node)
            )
        )
        calls = [node for node in ast.walk(main_guard) if isinstance(node, ast.Call)]

        def named_call(name):
            return [
                node for node in calls
                if isinstance(node.func, ast.Name) and node.func.id == name
            ]

        port_calls = named_call("_select_server_port")
        recovery_calls = named_call("_start_job_queue_recovery")
        migration_calls = named_call("migrate_active_project_pointer")
        self.assertEqual(len(port_calls), 1)
        self.assertEqual(len(recovery_calls), 1)
        self.assertEqual(len(migration_calls), 1)
        self.assertLess(port_calls[0].lineno, recovery_calls[0].lineno)
        self.assertLess(recovery_calls[0].lineno, migration_calls[0].lineno)

    def test_direct_launch_paid_owner_scope_uses_server_delete_barrier(self):
        from orchestrator.integrations import replicate
        from orchestrator.job_queue import JobOwnerUnavailable, JobQueue

        source_path = ROOT / "server" / "app.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        def is_main_guard(node):
            return (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
                and any(
                    isinstance(child, ast.Assign)
                    and any(
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Attribute)
                        and isinstance(target.value.value, ast.Name)
                        and target.value.value.id == "sys"
                        and target.value.attr == "modules"
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value == "server.app"
                        for target in child.targets
                    )
                    for child in node.body
                )
            )

        alias_guard = next(node for node in tree.body if is_main_guard(node))
        alias_code = compile(
            ast.fix_missing_locations(ast.Module(
                body=[alias_guard], type_ignores=[],
            )),
            str(source_path),
            "exec",
        )
        direct_server = type(sys)("__main__")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = JobQueue(sessions_root=root / "sessions")
            read_scope = mock.MagicMock()
            read_scope.return_value.__enter__.return_value = (
                "style-owner", mock.sentinel.deleted,
            )
            direct_server._conversation_read_scope = read_scope
            direct_server.rp = mock.Mock(ORA_HOME=root)

            with mock.patch.dict(
                sys.modules, {"__main__": direct_server}, clear=False,
            ):
                sys.modules.pop("server.app", None)
                exec(alias_code, {"sys": sys, "__name__": "__main__"})
                self.assertIs(sys.modules["server.app"], direct_server)
                with self.assertRaises(JobOwnerUnavailable):
                    with replicate._authenticated_owner_scope(
                        queue, "style-owner",
                    ):
                        self.fail("deleted Dialogue must not admit paid work")

        read_scope.assert_called_once_with("style-owner")

    def test_paid_job_barrier_failure_reopens_dialogue_without_cleanup(self):
        import orchestrator

        conversation_id = "retry-delete"
        identity = server._conversation_storage_identity(conversation_id)
        recorder = LifecycleDelegationTests._Recorder()
        document_input = mock.Mock()
        conversation_closeout = mock.Mock()

        def clear_test_tombstone():
            with server._conversation_lifecycle_guard:
                server._deleted_conversations.discard(identity)

        clear_test_tombstone()
        self.addCleanup(clear_test_tombstone)

        with (
            mock.patch.object(server, "_video_plugin", recorder),
            mock.patch.object(server, "_HAS_TRANSCRIPTION", False),
            mock.patch.object(server, "_HAS_JOB_QUEUE", False),
            mock.patch.object(
                server, "_assert_stealth_permanent_delete", return_value=None,
            ),
            mock.patch.object(
                server, "_clear_conversation_runtime_state",
            ) as clear_runtime,
            mock.patch.dict(sys.modules, {
                "orchestrator.document_input": document_input,
                "orchestrator.conversation_closeout": conversation_closeout,
            }),
            mock.patch.object(
                orchestrator, "document_input", document_input, create=True,
            ),
            mock.patch.object(
                orchestrator, "conversation_closeout", conversation_closeout,
                create=True,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "paid-job quiescence cannot be confirmed",
            ):
                server._delete_conversation_runtime(conversation_id)

        self.assertFalse(server._is_conversation_deleted(conversation_id))
        self.assertEqual(recorder.phases, [])
        document_input.purge_conversation.assert_not_called()
        conversation_closeout.delete_conversation_forever.assert_not_called()
        clear_runtime.assert_not_called()

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
            contained_pythonpath = []
            for candidate in (str(ROOT), *sys.path):
                resolved = str(Path(candidate or ROOT).resolve())
                if resolved == "/Users/oracle/ora" or resolved.startswith(
                    "/Users/oracle/ora/"
                ):
                    continue
                if resolved not in contained_pythonpath:
                    contained_pythonpath.append(resolved)
            env["PYTHONPATH"] = os.pathsep.join(contained_pythonpath)
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
        queue = mock.Mock()
        queue.forget_conversation.return_value = 0
        with (
            mock.patch.object(server, "_video_plugin", recorder),
            mock.patch.object(server, "_HAS_TRANSCRIPTION", False),
            mock.patch.object(server, "_HAS_JOB_QUEUE", True),
            mock.patch.object(server, "_get_job_queue", return_value=queue),
            mock.patch.object(server, "SIDEBAR_WINDOW_AVAILABLE", False),
            mock.patch(
                "orchestrator.document_input.purge_conversation",
                return_value={"jobs": 0, "outputs": 0, "errors": []},
            ),
        ):
            server._quiesce_conversation_workers("delete-me")
            server._clear_conversation_runtime_state("delete-me")
        queue.forget_conversation.assert_called_once_with("delete-me")
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
