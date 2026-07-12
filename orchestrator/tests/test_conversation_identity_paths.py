"""Regression tests for conversation identity and deletion-safe paths.

The lifecycle contract has two deliberately different ID boundaries:

* new writers require a portable lowercase ``[a-z0-9_-]+`` ID and persist it
  verbatim, so distinct IDs can never collapse through punctuation replacement;
* Delete Forever accepts any legacy ID that is still one safe direct path
  segment, allowing old punctuation-bearing envelopes to be removed.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ORCHESTRATOR = REPO / "orchestrator"
SERVER_DIR = REPO / "server"
for value in (str(REPO), str(ORCHESTRATOR), str(SERVER_DIR)):
    if value not in sys.path:
        sys.path.insert(0, value)


class _SavedUpload:
    def __init__(self, filename: str = "image.png", payload: bytes = b"image"):
        self.filename = filename
        self.payload = payload

    def save(self, destination) -> None:
        if hasattr(destination, "write"):
            destination.write(self.payload)
        else:
            Path(destination).write_bytes(self.payload)


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


class TestConversationLifecycleFileLock(unittest.TestCase):
    def test_lock_identity_is_casefolded_and_hashed(self):
        from orchestrator import runtime_paths

        with tempfile.TemporaryDirectory() as td, mock.patch.object(
            runtime_paths, "DATA_DIR_STR", td,
        ), mock.patch.object(runtime_paths, "locked_file") as locked:
            locked.return_value.__enter__.return_value = None
            with runtime_paths.conversation_lifecycle_lock("Legacy.ID"):
                pass
            with runtime_paths.conversation_lifecycle_lock("legacy.id"):
                pass

        first = Path(locked.call_args_list[0].args[0])
        second = Path(locked.call_args_list[1].args[0])
        self.assertEqual(first, second)
        self.assertEqual(first.parent.name, "lifecycle-locks")
        self.assertNotIn("legacy", first.name)

    def test_lock_file_symlink_is_not_followed(self):
        from orchestrator import runtime_paths

        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / "data"
            locks = data / "lifecycle-locks"
            locks.mkdir(parents=True)
            outside = Path(td) / "outside.lock"
            outside.write_text("must remain", encoding="utf-8")
            digest = hashlib.sha256(b"dialogue-a").hexdigest()
            (locks / f"{digest}.lock").symlink_to(outside)

            with (
                mock.patch.object(runtime_paths, "DATA_DIR_STR", str(data)),
                self.assertRaises(OSError),
            ):
                with runtime_paths.conversation_lifecycle_lock("dialogue-a"):
                    pass

            self.assertEqual(outside.read_text(encoding="utf-8"), "must remain")


class TestJobQueueCanonicalPaths(unittest.TestCase):
    def test_safe_ids_have_distinct_exact_mirrors_and_unsafe_ids_fail(self):
        from orchestrator.job_queue import JobQueue

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue = JobQueue(sessions_root=root)
            queue.dispatch("a", "video_generates", {"prompt": "one"})
            queue.dispatch("a-b", "video_generates", {"prompt": "two"})
            self.assertTrue((root / "a" / "jobs.json").is_file())
            self.assertTrue((root / "a-b" / "jobs.json").is_file())

            for unsafe in ("a.b", "a:b", "a b", "a/b", "../a", "A"):
                with self.assertRaises(ValueError, msg=unsafe):
                    queue.dispatch(unsafe, "video_generates", {"prompt": "bad"})

    def test_forget_can_tombstone_legacy_safe_segment_without_writing(self):
        from orchestrator.job_queue import JobQueue

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue = JobQueue(sessions_root=root)
            self.assertEqual(queue.forget_conversation("legacy.id"), 0)
            self.assertEqual(queue.list_jobs("legacy.id"), [])
            self.assertFalse((root / "legacy.id").exists())

    def test_forget_drains_inflight_completion_before_session_purge(self):
        from orchestrator.job_queue import JobQueue

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue = JobQueue(sessions_root=root)
            job = queue.dispatch("queue-race", "video_generates", {})
            persist_started = threading.Event()
            release_persist = threading.Event()
            forget_done = threading.Event()
            original_persist = queue._persist

            def blocking_persist(conversation_id):
                persist_started.set()
                release_persist.wait(timeout=3)
                original_persist(conversation_id)

            with mock.patch.object(queue, "_persist", side_effect=blocking_persist):
                completion = threading.Thread(
                    target=queue.mark_complete,
                    args=("queue-race", job["id"], {"path": "result.mp4"}),
                )
                completion.start()
                self.assertTrue(persist_started.wait(timeout=2))
                forgetting = threading.Thread(
                    target=lambda: (
                        queue.forget_conversation("QUEUE-RACE"),
                        forget_done.set(),
                    ),
                )
                forgetting.start()
                self.assertFalse(forget_done.wait(timeout=0.1))
                release_persist.set()
                completion.join(timeout=3)
                forgetting.join(timeout=3)

            self.assertFalse(completion.is_alive())
            self.assertFalse(forgetting.is_alive())
            shutil.rmtree(root / "queue-race")
            with self.assertRaises(RuntimeError):
                queue.dispatch("queue-race", "video_generates", {})
            self.assertFalse((root / "queue-race").exists())


class TestCaptureDeletionRace(unittest.TestCase):
    def test_stale_resume_observes_tombstone_after_forget(self):
        from orchestrator import media_capture

        with tempfile.TemporaryDirectory() as td:
            capture_dir = Path(td) / "captures"
            manager = media_capture.CaptureManager(capture_dir)
            capture = media_capture._Capture(
                capture_id="capture-race-id",
                conversation_id="capture-race",
                tag="",
                options={},
                capture_dir=capture_dir,
                state=media_capture.STATE_PAUSED,
            )
            with manager._lock:
                manager._captures[capture.capture_id] = capture

            stale_reference_obtained = threading.Event()
            release_stale_call = threading.Event()
            observed: dict[str, Exception] = {}
            original_require = manager._require

            def delayed_require(capture_id):
                result = original_require(capture_id)
                stale_reference_obtained.set()
                release_stale_call.wait(timeout=3)
                return result

            def resume():
                try:
                    manager.resume_capture(capture.capture_id)
                except Exception as exc:
                    observed["error"] = exc

            with (
                mock.patch.object(manager, "_require", side_effect=delayed_require),
                mock.patch.object(manager, "_launch_segment") as launch,
            ):
                worker = threading.Thread(target=resume)
                worker.start()
                self.assertTrue(stale_reference_obtained.wait(timeout=2))
                result = manager.forget_conversation("CAPTURE-RACE")
                release_stale_call.set()
                worker.join(timeout=3)

            self.assertFalse(worker.is_alive())
            self.assertEqual(result["captures"], 1)
            self.assertIsInstance(observed.get("error"), RuntimeError)
            launch.assert_not_called()


class TestTranscriptionDeletionRace(unittest.TestCase):
    def test_persistent_json_replace_does_not_follow_symlink(self):
        from orchestrator import transcription

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "outside.json"
            sidecar = root / "source.whisper.json"
            sidecar.symlink_to(outside)
            transcription._atomic_write_text_no_follow(sidecar, '{"ok": true}')
            self.assertFalse(outside.exists())
            self.assertFalse(sidecar.is_symlink())
            self.assertEqual(json.loads(sidecar.read_text()), {"ok": True})

    def test_forget_tombstones_job_and_scrubs_content(self):
        from orchestrator import transcription

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.wav"
            source.write_bytes(b"audio")
            with (
                mock.patch.object(transcription, "WHISPER_MODELS_DIR", root),
                mock.patch.object(transcription.threading, "Thread", _NoopThread),
            ):
                manager = transcription.TranscriptionManager()
                tid = manager.start(source, {
                    "_conversation_id": "transcription-race",
                    "_conversation_tag": "private",
                    "provider": "openrouter_audio",
                    "openrouter_audio_question": "sensitive custom question",
                })
                job = manager._jobs[tid]
                job.plain_text = "sensitive transcript"
                job.segments = [{"text": "sensitive transcript"}]
                job.last_error = "sensitive provider detail"

                result = manager.forget_conversation("TRANSCRIPTION-RACE")

                self.assertEqual(result["transcriptions"], 1)
                self.assertTrue(job._deleted)
                self.assertEqual(job.plain_text, "")
                self.assertEqual(job.segments, [])
                self.assertEqual(job.options, {})
                self.assertIsNone(job.last_error)
                with self.assertRaises(KeyError):
                    manager.get_state(tid)
                with self.assertRaises(RuntimeError):
                    manager.start(source, {
                        "_conversation_id": "transcription-race",
                    })

    def test_forget_waits_for_conversation_owned_workdir_cleanup(self):
        from orchestrator import transcription

        with tempfile.TemporaryDirectory() as td:
            session_dir = Path(td) / "sessions" / "transcription-barrier" / "transcriptions"
            session_dir.mkdir(parents=True)
            source = session_dir / "source.wav"
            source.write_bytes(b"audio")
            extraction_started = threading.Event()
            release_extraction = threading.Event()
            forget_done = threading.Event()

            def blocking_extract(_source, target, **_kwargs):
                Path(target).write_bytes(b"derived-sensitive-audio")
                extraction_started.set()
                release_extraction.wait(timeout=3)

            with (
                mock.patch.object(transcription, "WHISPER_MODELS_DIR", Path(td)),
                mock.patch.object(transcription, "_resolve_model_path",
                                  return_value=Path(td) / "model.bin"),
                mock.patch.object(transcription, "_extract_to_wav",
                                  side_effect=blocking_extract),
            ):
                manager = transcription.TranscriptionManager()
                manager.start(source, {
                    "_conversation_id": "transcription-barrier",
                })
                self.assertTrue(extraction_started.wait(timeout=2))
                workdirs = list(session_dir.glob(".ora-whisper-*"))
                self.assertEqual(len(workdirs), 1)
                forgetting = threading.Thread(
                    target=lambda: (
                        manager.forget_conversation("transcription-barrier"),
                        forget_done.set(),
                    ),
                )
                forgetting.start()
                self.assertFalse(forget_done.wait(timeout=0.1))
                release_extraction.set()
                forgetting.join(timeout=3)

            self.assertFalse(forgetting.is_alive())
            self.assertTrue(forget_done.is_set())
            self.assertEqual(list(session_dir.glob(".ora-whisper-*")), [])

    def test_forget_waits_for_inflight_remote_provider_and_scrubs_result(self):
        from orchestrator import transcription

        provider_started = threading.Event()
        release_provider = threading.Event()
        forget_done = threading.Event()
        client_kwargs: dict[str, object] = {}

        class Completions:
            @staticmethod
            def create(**_kwargs):
                provider_started.set()
                release_provider.wait(timeout=3)
                message = types.SimpleNamespace(content="remote transcript")
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=message)],
                )

        class OpenAIClient:
            chat = types.SimpleNamespace(completions=Completions())

        def openai_factory(**kwargs):
            client_kwargs.update(kwargs)
            return OpenAIClient()

        openai_module = types.SimpleNamespace(OpenAI=openai_factory)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.wav"
            source.write_bytes(b"audio")
            with (
                mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}),
                mock.patch.dict(sys.modules, {"openai": openai_module}),
                mock.patch.object(transcription, "WHISPER_MODELS_DIR", root),
            ):
                manager = transcription.TranscriptionManager()
                tid = manager.start(source, {
                    "_conversation_id": "remote-barrier",
                    "provider": "openrouter_audio",
                    "openrouter_audio_model": "vendor/audio-model",
                })
                self.assertTrue(provider_started.wait(timeout=2))
                job = manager._jobs[tid]
                forgetting = threading.Thread(
                    target=lambda: (
                        manager.forget_conversation("remote-barrier"),
                        forget_done.set(),
                    ),
                )
                forgetting.start()
                self.assertFalse(forget_done.wait(timeout=0.1))
                release_provider.set()
                forgetting.join(timeout=3)

            self.assertFalse(forgetting.is_alive())
            self.assertTrue(forget_done.is_set())
            self.assertEqual(job.plain_text, "")
            self.assertEqual(job.segments, [])
            self.assertEqual(
                client_kwargs["timeout"],
                transcription.REMOTE_REQUEST_TIMEOUT_SECONDS,
            )
            self.assertEqual(
                client_kwargs["max_retries"],
                transcription.REMOTE_MAX_RETRIES,
            )

    def test_forget_signals_all_jobs_before_waiting_on_first_worker(self):
        from orchestrator import transcription

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = transcription._Transcription(
                transcription_id="first",
                source_path=root / "first.wav",
                options={},
                conversation_id="multi-transcription",
            )
            second = transcription._Transcription(
                transcription_id="second",
                source_path=root / "second.wav",
                options={"provider": "openrouter_audio"},
                conversation_id="multi-transcription",
            )
            observed: dict[str, bool] = {}

            class FirstWorker:
                alive = True

                def is_alive(self):
                    return self.alive

                def join(self, timeout=None):
                    observed["second_cancelled_before_join"] = (
                        second._cancel_event.is_set()
                    )
                    self.alive = False
                    first._done_event.set()

            first.worker = FirstWorker()
            manager = transcription.TranscriptionManager()
            manager._jobs = {"first": first, "second": second}

            result = manager.forget_conversation("multi-transcription")

            self.assertTrue(observed["second_cancelled_before_join"])
            self.assertTrue(first._cancel_event.is_set())
            self.assertTrue(second._cancel_event.is_set())
            self.assertTrue(first._deleted)
            self.assertTrue(second._deleted)
            self.assertEqual(result["transcriptions"], 2)

    def test_local_state_reports_resolved_fallback_model(self):
        from orchestrator import transcription

        with tempfile.TemporaryDirectory() as td:
            manager = transcription.TranscriptionManager()
            job = transcription._Transcription(
                transcription_id="model-state",
                source_path=Path(td) / "source.wav",
                options={
                    "model": "requested-but-unavailable",
                    "_resolved_model": "ggml-large-v3.bin",
                },
                conversation_id="model-owner",
            )
            manager._jobs[job.transcription_id] = job

            state = manager.get_state(job.transcription_id)

            self.assertEqual(
                state["transcription_model"],
                "whisper-local:ggml-large-v3.bin",
            )


class TestExecutionPersistenceLegacyCollision(unittest.TestCase):
    def test_legacy_punctuation_purge_preserves_colliding_safe_id(self):
        from orchestrator import execution_persistence as persistence

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shared = root / "a_b"
            shared.mkdir()
            legacy = shared / "legacy.md"
            safe = shared / "safe.md"
            legacy.write_text("---\nconversation_id: a:b\n---\nlegacy\n")
            safe.write_text("---\nconversation_id: a_b\n---\nsafe\n")
            with (
                mock.patch.dict(os.environ, {
                    "ORA_EXECUTION_RECORDS_DIR": str(root),
                    "ORA_EXECUTION_LEDGER_PATH": str(root / "ledger.jsonl"),
                }),
            ):
                result = persistence.purge_conversation("a:b")
            self.assertFalse(legacy.exists())
            self.assertTrue(safe.exists())
            self.assertFalse(result["errors"])


class TestDispatcherLogRetirement(unittest.TestCase):
    def test_uncorrelated_session_logs_are_retired_without_following_symlinks(self):
        from orchestrator import dispatcher

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "logs"
            root.mkdir()
            legacy = root / "session-20260712.log"
            legacy.write_text("private params and result\n")
            outside = Path(td) / "outside.log"
            outside.write_text("keep\n")
            linked = root / "session-linked.log"
            linked.symlink_to(outside)

            result = dispatcher.retire_legacy_session_logs(root)

            self.assertCountEqual(
                result["removed"], [str(legacy), str(linked)],
            )
            self.assertEqual(result["errors"], [])
            self.assertFalse(legacy.exists())
            self.assertFalse(linked.exists())
            self.assertEqual(outside.read_text(), "keep\n")

    def test_compatibility_logger_creates_no_replacement_sink(self):
        from orchestrator import dispatcher

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "logs"
            with (
                mock.patch.object(dispatcher, "LOG_DIR", str(root)),
                mock.patch.object(dispatcher, "_retired_dispatch_log_roots", set()),
            ):
                dispatcher._log_dispatch(
                    "file_read", {"path": "/private"}, None,
                    "auto-approved", "secret result", 1,
                )
            self.assertFalse(root.exists())


class TestOversightLifecycleOwnership(unittest.TestCase):
    def test_paused_queue_promotes_nested_conversation_id_to_top_level(self):
        from orchestrator import oversight_queue

        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "human-queue.jsonl"
            with (
                mock.patch.object(
                    oversight_queue, "HUMAN_QUEUE_PATH", str(queue_path),
                ),
                mock.patch.object(
                    oversight_queue, "_generate_name", return_value="Paused",
                ),
            ):
                entry = oversight_queue.add_entry({
                    "event": {
                        "event_type": "MilestoneClaimed",
                        "conversation_id": "owned-dialogue",
                    },
                    "verdict": {"reasoning": "sensitive"},
                })

            stored = json.loads(queue_path.read_text())
            self.assertEqual(stored["conversation_id"], "owned-dialogue")
            self.assertEqual(entry.conversation_id, "owned-dialogue")
            self.assertEqual(entry.to_dict()["conversation_id"], "owned-dialogue")

    def test_stealth_paused_entry_never_writes_or_calls_naming_model(self):
        from orchestrator import oversight_queue

        with tempfile.TemporaryDirectory() as td:
            queue_path = Path(td) / "human-queue.jsonl"
            with (
                mock.patch.object(
                    oversight_queue, "HUMAN_QUEUE_PATH", str(queue_path),
                ),
                mock.patch.object(oversight_queue, "_generate_name") as naming,
            ):
                entry = oversight_queue.add_entry({
                    "event": {
                        "event_type": "MilestoneClaimed",
                        "conversation_id": "stealth-dialogue",
                        "stealth": True,
                    },
                    "verdict": {"reasoning": "secret"},
                })

            self.assertFalse(queue_path.exists())
            self.assertEqual(entry.conversation_id, "stealth-dialogue")
            naming.assert_not_called()

    def test_router_log_stamps_identity_and_suppresses_stealth(self):
        from orchestrator import oversight_events, oversight_router

        with tempfile.TemporaryDirectory() as td:
            router_path = Path(td) / "router.jsonl"
            with mock.patch.object(
                oversight_router, "ROUTER_LOG_PATH", str(router_path),
            ):
                oversight_events.set_conversation_id_context("router-dialogue")
                oversight_events.set_stealth_context(False)
                oversight_router._append_router_log({"action": "logged_only"})
                oversight_events.set_stealth_context(True)
                oversight_router._append_router_log({
                    "action": "invoked", "verdict": {"raw_output": "secret"},
                })
                oversight_events.clear_stealth_context()
                oversight_events.clear_conversation_id_context()

            rows = [json.loads(line) for line in router_path.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["conversation_id"], "router-dialogue")


class TestPreviewReadPaths(unittest.TestCase):
    def test_runtime_root_and_proxy_path_are_read_only(self):
        from orchestrator import preview, runtime_paths

        self.assertEqual(preview.WORKSPACE_ROOT, runtime_paths.ORA_HOME.resolve())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            with mock.patch.object(preview, "SESSIONS_ROOT", root):
                proxy = preview.proxy_path("read-only-id")
                meta = preview.proxy_meta_path("read-only-id")
                self.assertEqual(proxy, root / "read-only-id" / "preview-proxy.mp4")
                self.assertEqual(meta, root / "read-only-id" / "preview-proxy.json")
                self.assertFalse((root / "read-only-id").exists())

    def test_forget_blocks_factories_and_late_proxy_reads(self):
        from orchestrator import preview

        conversation_id = "deleted-preview-contract"
        preview.forget_conversation(conversation_id)
        with mock.patch.object(preview, "get_timeline") as get_timeline:
            with self.assertRaises(RuntimeError):
                preview.proxy_state(conversation_id)
        get_timeline.assert_not_called()

    def test_path_traversal_is_rejected_without_creating_any_directory(self):
        from orchestrator import preview

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            with mock.patch.object(preview, "SESSIONS_ROOT", root):
                for unsafe in ("", "..", "../escape", "a/b", "a\\b"):
                    with self.assertRaises(ValueError, msg=unsafe):
                        preview.proxy_path(unsafe)
                self.assertFalse(root.exists())


class TestConversationMemoryIdentity(unittest.TestCase):
    def test_case_variants_share_write_lock_and_symlink_sessions_are_hidden(self):
        from orchestrator import conversation_memory as memory

        self.assertIs(
            memory._conversation_write_lock("Legacy-ID"),
            memory._conversation_write_lock("legacy-id"),
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            external = Path(td) / "external"
            external.mkdir(parents=True)
            (external / "conversation.json").write_text(json.dumps({
                "conversation_id": "outside",
                "messages": [],
            }))
            root.mkdir()
            (root / "linked-session").symlink_to(
                external, target_is_directory=True,
            )

            self.assertEqual(memory.iter_conversations(root), [])


class TestServerCanonicalStorage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server  # type: ignore
        cls.server = server

    def tearDown(self):
        self.server._deleted_conversations.clear()
        self.server._conversation_creation_tags.clear()
        self.server._unreadable_conversations.clear()
        self.server._closed_conversations.clear()
        with self.server._transcription_metadata_lock:
            self.server._transcription_source_paths.clear()
            self.server._transcription_vault_paths.clear()
            self.server._transcription_conversations.clear()
            self.server._transcription_tags.clear()
            self.server._transcription_vault_status.clear()
            self.server._transcription_vault_errors.clear()

    def test_new_writer_ids_are_portable_but_legacy_deletion_ids_remain_safe(self):
        server = self.server
        for valid in ("a", "a-b", "a_b", "a123"):
            self.assertTrue(server._valid_live_conversation_id(valid), valid)
            self.assertEqual(server._canonical_live_conversation_id(valid), valid)
        self.assertFalse(server._valid_live_conversation_id("A123"))
        self.assertTrue(server._valid_existing_conversation_id("A123"))
        self.assertIs(
            server._conversation_lifecycle_lock("A123"),
            server._conversation_lifecycle_lock("a123"),
        )
        server._deleted_conversations.add(
            server._conversation_storage_identity("A123"),
        )
        self.assertTrue(server._is_conversation_deleted("a123"))
        for legacy in ("legacy.id", "legacy:id", "legacy id"):
            self.assertFalse(server._valid_live_conversation_id(legacy), legacy)
            self.assertTrue(server._valid_existing_conversation_id(legacy), legacy)
        for unsafe in ("", "..", "../escape", "a/b", "a\\b"):
            self.assertFalse(server._valid_existing_conversation_id(unsafe), unsafe)

    def test_lifecycle_state_caches_share_casefold_identity(self):
        server = self.server
        identity = server._conversation_storage_identity("Legacy-ID")
        server._conversation_creation_tags[identity] = "private"
        server._unreadable_conversations.add(identity)
        server._closed_conversations.add(identity)

        self.assertEqual(
            server._conversation_creation_tags.get(
                server._conversation_storage_identity("legacy-id")
            ),
            "private",
        )
        self.assertIn(
            server._conversation_storage_identity("legacy-id"),
            server._unreadable_conversations,
        )
        self.assertTrue(server._is_conversation_closed("legacy-id"))

    def test_agentic_stream_scopes_and_restores_all_turn_context(self):
        server = self.server
        import boot
        import tool_events
        from orchestrator import oversight_events

        oversight_events.set_stealth_context(False)
        oversight_events.set_conversation_id_context("outer-dialogue")
        tool_token = tool_events.set_turn_context(
            conversation_id="outer-dialogue", surface="outer",
        )
        tag_token = boot.set_conversation_tag_context("")
        trace_token = boot.set_turn_trace_context("/tmp/outer-trace")
        private_values = "## Private Context\n\nsecret\n"

        def direct_stream(*_args, **_kwargs):
            stealth, conversation_id = oversight_events.resolve_lifecycle_context()
            self.assertTrue(stealth)
            self.assertEqual(conversation_id, "inner-dialogue")
            self.assertEqual(
                tool_events.get_turn_context()["conversation_id"],
                "inner-dialogue",
            )
            self.assertIn("secret", boot._filter_private_values(private_values))
            yield "frame"

        try:
            with (
                mock.patch.object(
                    server, "_effective_conversation_tag", return_value="stealth",
                ),
                mock.patch.object(server, "_direct_stream", side_effect=direct_stream),
            ):
                frames = list(server.agentic_loop_stream(
                    "prompt", [], use_pipeline=False,
                    panel_id="inner-dialogue", conversation_tag="stealth",
                ))

            self.assertEqual(frames, ["frame"])
            self.assertEqual(
                oversight_events.resolve_lifecycle_context(),
                (False, "outer-dialogue"),
            )
            self.assertEqual(
                tool_events.get_turn_context()["conversation_id"],
                "outer-dialogue",
            )
            self.assertNotIn("secret", boot._filter_private_values(private_values))
            self.assertEqual(boot._TURN_TRACE_DIR_CV.get(), "/tmp/outer-trace")
        finally:
            boot.reset_turn_trace_context(trace_token)
            boot.reset_conversation_tag_context(tag_token)
            tool_events.reset_turn_context(tool_token)
            oversight_events.clear_conversation_id_context()
            oversight_events.clear_stealth_context()

    def test_new_identity_rejects_legacy_case_twin_and_session_symlink(self):
        server = self.server
        from orchestrator import conversation_memory as memory

        with tempfile.TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"
            sessions.mkdir()
            (sessions / "LegacyOwner").mkdir()
            external = Path(td) / "external"
            external.mkdir()
            (sessions / "symlink-owner").symlink_to(
                external, target_is_directory=True,
            )
            with mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions):
                with self.assertRaises(ValueError):
                    server._assert_no_casefold_session_collision("legacyowner")
                with self.assertRaises(ValueError):
                    server._assert_no_casefold_session_collision("symlink-owner")

    def test_multipart_canvas_and_retry_paths_use_exact_canonical_id(self):
        server = self.server
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            png_url = "data:image/png;base64," + base64.b64encode(b"png").decode()
            with (
                mock.patch.object(server, "VISUAL_UPLOADS_ROOT", str(root)),
                mock.patch.object(server, "CANVAS_ROOT", str(root)),
            ):
                image_path = server._save_multipart_image(
                    "a-b", _SavedUpload("photo.png", b"photo"),
                )
                preview_path = server._save_canvas_preview_png("a", png_url)
                canvas_dir = server._canvas_dir("a-b")
                retry_path = server._vision_retry_queue_path("a")

            self.assertEqual(Path(image_path).parent, root / "a-b" / "uploads")
            self.assertEqual(Path(preview_path).parent, root / "a" / "uploads")
            self.assertEqual(Path(canvas_dir), root / "a-b" / "canvas")
            self.assertEqual(Path(retry_path), root / "a" / "vision-retry-queue.json")
            self.assertNotEqual((root / "a").resolve(), (root / "a-b").resolve())

    def test_transcription_upload_is_owned_by_zero_turn_envelope(self):
        server = self.server
        from orchestrator import conversation_memory as memory

        class Manager:
            def __init__(self):
                self.calls = []

            def start(self, source_path, options):
                self.calls.append((source_path, dict(options)))
                return "transcription-owned"

        manager = Manager()
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"
            with (
                mock.patch.object(server, "_HAS_TRANSCRIPTION", True),
                mock.patch.object(server, "_get_transcription_manager",
                                  return_value=manager),
                mock.patch.object(server, "_HAS_USER_SETTINGS", False),
                mock.patch.object(server, "_TRANSCRIPTION_STAGING_DIR",
                                  str(sessions)),
                mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
            ):
                response = server.app.test_client().post(
                    "/api/transcribe",
                    data={
                        "conversation_id": "transcription-owned",
                        "tag": "private",
                        "file": (io.BytesIO(b"audio"), "voice.wav"),
                    },
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            payload = response.get_json()
            self.assertTrue(payload["envelope_created"])
            self.assertTrue(payload["envelope_available"])
            self.assertEqual(payload["tag"], "private")
            source_path, options = manager.calls[0]
            self.assertEqual(
                Path(source_path).parent,
                sessions / "transcription-owned" / "transcriptions",
            )
            self.assertEqual(options["_conversation_id"], "transcription-owned")
            self.assertEqual(options["_conversation_tag"], "private")
            envelope = json.loads(
                (sessions / "transcription-owned" / "conversation.json").read_text()
            )
            self.assertEqual(envelope["tag"], "private")

    def test_fast_transcription_cannot_reset_written_vault_status_to_pending(self):
        server = self.server
        from orchestrator import conversation_memory as memory

        class Job:
            segments = [{"text": "fast"}]
            plain_text = "fast"

        class Manager:
            _jobs = {"fast-tid": Job()}
            source_path = ""

            def start(self, source_path, options):
                self.source_path = source_path
                server._transcription_complete_hook({
                    "type": "complete",
                    "transcription_id": "fast-tid",
                    "conversation_id": options["_conversation_id"],
                    "tag": options["_conversation_tag"],
                })
                return "fast-tid"

            def get_state(self, _tid):
                return {
                    "source_path": self.source_path,
                    "state": "complete",
                    "language": "en",
                    "duration_ms": 1,
                }

        manager = Manager()
        with tempfile.TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"
            with (
                mock.patch.object(server, "_HAS_TRANSCRIPTION", True),
                mock.patch.object(server, "_get_transcription_manager",
                                  return_value=manager),
                mock.patch.object(server, "_HAS_USER_SETTINGS", False),
                mock.patch.object(server, "_TRANSCRIPTION_STAGING_DIR",
                                  str(sessions)),
                mock.patch.object(server, "_write_transcript_note",
                                  return_value=Path(td) / "transcript.md"),
                mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
            ):
                response = server.app.test_client().post(
                    "/api/transcribe",
                    data={
                        "conversation_id": "fast-transcription",
                        "file": (io.BytesIO(b"audio"), "fast.wav"),
                    },
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            self.assertEqual(
                server._transcription_vault_status["fast-tid"], "written",
            )

    def test_transcription_completion_respects_tombstone_and_ownership(self):
        server = self.server

        class Job:
            segments = [{"text": "hello"}]
            plain_text = "hello"

        class Manager:
            _jobs = {"tid": Job()}

            @staticmethod
            def get_state(_tid):
                return {
                    "source_path": "/tmp/source.wav",
                    "language": "en",
                    "duration_ms": 1000,
                }

        writer = mock.Mock(return_value=Path("/tmp/transcript.md"))
        event = {
            "type": "complete",
            "transcription_id": "tid",
            "conversation_id": "transcription-hook",
            "tag": "",
        }
        with (
            mock.patch.object(server, "_HAS_TRANSCRIPTION", True),
            mock.patch.object(server, "_get_transcription_manager",
                              return_value=Manager()),
            mock.patch.object(server, "_write_transcript_note", writer),
            mock.patch.object(server, "_effective_conversation_tag",
                              return_value="private"),
        ):
            server._transcription_complete_hook(event)
            writer.assert_called_once()
            self.assertEqual(
                writer.call_args.kwargs["conversation_id"],
                "transcription-hook",
            )
            self.assertTrue(writer.call_args.kwargs["private"])

            writer.reset_mock()
            server._deleted_conversations.add(
                server._conversation_storage_identity("TRANSCRIPTION-HOOK"),
            )
            server._transcription_complete_hook(event)
            writer.assert_not_called()

    def test_transcription_state_exposes_event_status_alias(self):
        server = self.server

        class Manager:
            @staticmethod
            def get_state(_tid):
                return {
                    "transcription_id": "tid-state",
                    "state": "complete",
                    "conversation_id": "transcription-state",
                }

        with (
            mock.patch.object(server, "_HAS_TRANSCRIPTION", True),
            mock.patch.object(server, "_get_transcription_manager",
                              return_value=Manager()),
        ):
            with server._transcription_metadata_lock:
                server._transcription_vault_status["tid-state"] = "written"
            response = server.app.test_client().get(
                "/api/transcribe/tid-state/state",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["type"], "complete")

    def test_media_staging_purge_cannot_delete_prefix_sibling(self):
        server = self.server
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(server, "_MEDIA_LIBRARY_STAGING_DIR", str(root)):
                a_dir = Path(server._media_library_staging_dir("a", create=True))
                ab_dir = Path(server._media_library_staging_dir("a-b", create=True))
                (a_dir / "one.mov").write_bytes(b"a")
                (ab_dir / "two.mov").write_bytes(b"ab")

                self.assertEqual(server._purge_media_library_staging("a"), 1)
                self.assertFalse(a_dir.exists())
                self.assertTrue((ab_dir / "two.mov").is_file())

    def test_media_staging_writer_rejects_conversation_symlink(self):
        server = self.server
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "media-staging"
            outside = Path(td) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "media-owner").symlink_to(
                outside, target_is_directory=True,
            )
            with mock.patch.object(
                server, "_MEDIA_LIBRARY_STAGING_DIR", str(root),
            ):
                with self.assertRaises(ValueError):
                    server._media_library_staging_dir(
                        "media-owner", create=True,
                    )
            self.assertEqual(list(outside.iterdir()), [])

    def test_filestorage_atomic_replace_does_not_follow_target_symlink(self):
        server = self.server
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "outside.bin"
            outside.write_bytes(b"outside")
            target = root / "upload.bin"
            target.symlink_to(outside)

            server._save_filestorage_no_follow(
                _SavedUpload(payload=b"inside"), str(target),
            )

            self.assertEqual(outside.read_bytes(), b"outside")
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_bytes(), b"inside")

    def test_watermark_writer_rejects_symlinked_upload_directory(self):
        server = self.server
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            owner = home / "sessions" / "watermark-owner"
            outside = Path(td) / "outside"
            owner.mkdir(parents=True)
            outside.mkdir()
            (owner / "uploads").symlink_to(
                outside, target_is_directory=True,
            )
            with mock.patch.dict(os.environ, {"ORA_HOME": str(home)}):
                with self.assertRaises(ValueError):
                    server._store_watermark_upload(
                        "watermark-owner", _SavedUpload(), ".png",
                    )
            self.assertEqual(list(outside.iterdir()), [])

    def test_canvas_latest_replace_does_not_follow_symlink(self):
        server = self.server
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            canvas_dir = root / "canvas-owner" / "canvas"
            canvas_dir.mkdir(parents=True)
            outside = Path(td) / "outside.canvas"
            outside.write_bytes(b"outside")
            latest = canvas_dir / "latest.ora-canvas"
            latest.symlink_to(outside)
            with mock.patch.object(server, "CANVAS_ROOT", str(root)):
                _snapshot, returned_latest, _preview = (
                    server._write_canvas_artifacts(
                        "canvas-owner", b"inside", None,
                    )
                )
            self.assertEqual(Path(returned_latest), latest)
            self.assertEqual(outside.read_bytes(), b"outside")
            self.assertFalse(latest.is_symlink())
            self.assertEqual(latest.read_bytes(), b"inside")

    def test_deleted_or_missing_preview_get_never_calls_factory_or_mkdir(self):
        server = self.server
        client = server.app.test_client()
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"
            factory = mock.Mock(side_effect=AssertionError("factory must not run"))
            with (
                mock.patch.object(server.rp, "ORA_HOME", home),
                mock.patch.object(server, "_HAS_PREVIEW", True),
                mock.patch.object(server, "_preview_proxy_state", factory),
            ):
                missing = client.get("/api/preview/missing-preview/state")
                self.assertEqual(missing.status_code, 404)
                self.assertFalse((sessions / "missing-preview").exists())

                (sessions / "deleted-preview").mkdir(parents=True)
                server._deleted_conversations.add("deleted-preview")
                deleted = client.get("/api/preview/deleted-preview/state")
                self.assertEqual(deleted.status_code, 410)
            factory.assert_not_called()

    def test_deleted_or_missing_media_and_timeline_reads_skip_factories(self):
        server = self.server
        client = server.app.test_client()
        media_factory = mock.Mock(
            side_effect=AssertionError("media factory must not run"),
        )
        timeline_factory = mock.Mock(
            side_effect=AssertionError("timeline factory must not run"),
        )
        media_routes = (
            ("get", "/api/media-library/{cid}"),
            ("get", "/api/media-library/{cid}/entry/thumbnail"),
            ("get", "/api/media-library/{cid}/entry/waveform"),
            ("get", "/api/media-library/{cid}/entry/transcript"),
            ("post", "/api/media-library/{cid}/entry/suggest-edits"),
        )

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / "sessions"
            with (
                mock.patch.object(server.rp, "ORA_HOME", home),
                mock.patch.object(server, "_HAS_MEDIA_LIBRARY", True),
                mock.patch.object(server, "_get_media_library", media_factory),
                mock.patch.object(server, "_HAS_TIMELINE", True),
                mock.patch.object(server, "_get_timeline", timeline_factory),
                mock.patch.object(server, "_HAS_VIDEO_SUGGESTIONS", True),
                mock.patch.object(server, "_gen_suggestions_heuristic",
                                  mock.Mock()),
            ):
                for method, route in media_routes:
                    with self.subTest(state="missing", route=route):
                        response = getattr(client, method)(
                            route.format(cid="missing-read"),
                        )
                        self.assertEqual(response.status_code, 404)

                missing_timeline = client.get("/api/timeline/missing-read")
                self.assertEqual(missing_timeline.status_code, 404)
                self.assertFalse((sessions / "missing-read").exists())

                server._deleted_conversations.add("deleted-read")
                for method, route in media_routes:
                    with self.subTest(state="deleted", route=route):
                        response = getattr(client, method)(
                            route.format(cid="deleted-read"),
                        )
                        self.assertEqual(response.status_code, 410)

                deleted_timeline = client.get("/api/timeline/deleted-read")
                self.assertEqual(deleted_timeline.status_code, 410)
                self.assertFalse((sessions / "deleted-read").exists())

        media_factory.assert_not_called()
        timeline_factory.assert_not_called()

    def test_timeline_factory_finishes_before_delete_purge(self):
        server = self.server
        from orchestrator import conversation_closeout as closeout

        factory_started = threading.Event()
        release_factory = threading.Event()
        purge_called = threading.Event()
        observed: dict[str, object] = {}

        class BlockingTimeline:
            def load(self):
                factory_started.set()
                release_factory.wait(timeout=3)
                return {"conversation_id": "timeline-barrier", "tracks": []}

        def fake_purge(conversation_id, **_kwargs):
            purge_called.set()
            return {
                "conversation_id": conversation_id,
                "action": "delete_forever",
                "deleted": {},
                "retained": {"explicit_vault_exports": True},
                "errors": [],
            }

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "sessions" / "timeline-barrier").mkdir(parents=True)
            with (
                mock.patch.object(server.rp, "ORA_HOME", home),
                mock.patch.object(server, "_HAS_TIMELINE", True),
                mock.patch.object(server, "_get_timeline",
                                  return_value=BlockingTimeline()),
                mock.patch.object(server, "_quiesce_conversation_workers",
                                  return_value={"cleaned": {}, "errors": []}),
                mock.patch.object(server, "_clear_conversation_runtime_state",
                                  return_value={"cleared": {}, "errors": []}),
                mock.patch.object(closeout, "delete_conversation_forever",
                                  side_effect=fake_purge),
            ):
                reader = threading.Thread(
                    target=lambda: observed.setdefault(
                        "response",
                        server.app.test_client().get(
                            "/api/timeline/timeline-barrier",
                        ),
                    ),
                )
                reader.start()
                self.assertTrue(factory_started.wait(timeout=2))
                deleter = threading.Thread(
                    target=server._delete_conversation_runtime,
                    args=("timeline-barrier",),
                )
                deleter.start()
                self.assertFalse(purge_called.wait(timeout=0.1))
                release_factory.set()
                reader.join(timeout=3)
                deleter.join(timeout=3)

        self.assertFalse(reader.is_alive())
        self.assertFalse(deleter.is_alive())
        self.assertTrue(purge_called.is_set())
        self.assertEqual(observed["response"].status_code, 200)

    def test_preview_factory_finishes_before_delete_purge(self):
        server = self.server
        from orchestrator import conversation_closeout as closeout

        factory_started = threading.Event()
        release_factory = threading.Event()
        purge_called = threading.Event()
        observed: dict[str, object] = {}

        def blocking_state(_conversation_id):
            factory_started.set()
            release_factory.wait(timeout=3)
            return {"has_proxy": False}

        def fake_purge(conversation_id, **_kwargs):
            purge_called.set()
            return {
                "conversation_id": conversation_id,
                "action": "delete_forever",
                "deleted": {},
                "retained": {"explicit_vault_exports": True},
                "errors": [],
            }

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "sessions" / "preview-barrier").mkdir(parents=True)
            with (
                mock.patch.object(server.rp, "ORA_HOME", home),
                mock.patch.object(server, "_HAS_PREVIEW", True),
                mock.patch.object(server, "_preview_proxy_state",
                                  side_effect=blocking_state),
                mock.patch.object(server, "_quiesce_conversation_workers",
                                  return_value={"cleaned": {}, "errors": []}),
                mock.patch.object(server, "_clear_conversation_runtime_state",
                                  return_value={"cleared": {}, "errors": []}),
                mock.patch.object(closeout, "delete_conversation_forever",
                                  side_effect=fake_purge),
            ):
                reader = threading.Thread(
                    target=lambda: observed.setdefault(
                        "response",
                        server.app.test_client().get(
                            "/api/preview/preview-barrier/state",
                        ),
                    ),
                )
                reader.start()
                self.assertTrue(factory_started.wait(timeout=2))
                deleter = threading.Thread(
                    target=server._delete_conversation_runtime,
                    args=("preview-barrier",),
                )
                deleter.start()
                self.assertFalse(purge_called.wait(timeout=0.1))
                release_factory.set()
                reader.join(timeout=3)
                deleter.join(timeout=3)

        self.assertFalse(reader.is_alive())
        self.assertFalse(deleter.is_alive())
        self.assertTrue(purge_called.is_set())
        self.assertEqual(observed["response"].status_code, 200)

    def test_waveform_cache_render_finishes_before_delete_purge(self):
        server = self.server
        from orchestrator import conversation_closeout as closeout

        render_started = threading.Event()
        release_render = threading.Event()
        purge_called = threading.Event()
        observed: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            session_dir = home / "sessions" / "waveform-barrier"
            thumbnails = session_dir / "thumbnails"
            session_dir.mkdir(parents=True)
            source = home / "source.wav"
            source.write_bytes(b"audio")
            cache_path = thumbnails / "entry.waveform.png"

            class Library:
                @staticmethod
                def get_entry(_entry_id):
                    return {
                        "kind": "audio",
                        "source_path": str(source),
                    }

            library = Library()
            library.thumbnails_dir = thumbnails

            def render_waveform(_source, target):
                render_started.set()
                release_render.wait(timeout=3)
                Path(target).parent.mkdir(parents=True, exist_ok=True)
                Path(target).write_bytes(b"png")
                return True

            waveform_module = types.SimpleNamespace(
                render_waveform=render_waveform,
                waveform_cache_path=lambda _root, _entry_id: cache_path,
            )

            def fake_purge(conversation_id, **_kwargs):
                self.assertTrue(cache_path.exists())
                shutil.rmtree(session_dir)
                purge_called.set()
                return {
                    "conversation_id": conversation_id,
                    "action": "delete_forever",
                    "deleted": {},
                    "retained": {"explicit_vault_exports": True},
                    "errors": [],
                }

            with (
                mock.patch.dict(sys.modules, {"waveform": waveform_module}),
                mock.patch.object(server.rp, "ORA_HOME", home),
                mock.patch.object(server, "_HAS_MEDIA_LIBRARY", True),
                mock.patch.object(server, "_get_media_library",
                                  return_value=library),
                mock.patch.object(server, "send_from_directory",
                                  return_value=server._json_response({"ok": True})),
                mock.patch.object(server, "_quiesce_conversation_workers",
                                  return_value={"cleaned": {}, "errors": []}),
                mock.patch.object(server, "_clear_conversation_runtime_state",
                                  return_value={"cleared": {}, "errors": []}),
                mock.patch.object(closeout, "delete_conversation_forever",
                                  side_effect=fake_purge),
            ):
                reader = threading.Thread(
                    target=lambda: observed.setdefault(
                        "response",
                        server.app.test_client().get(
                            "/api/media-library/waveform-barrier/entry/waveform",
                        ),
                    ),
                )
                reader.start()
                self.assertTrue(render_started.wait(timeout=2))
                deleter = threading.Thread(
                    target=server._delete_conversation_runtime,
                    args=("waveform-barrier",),
                )
                deleter.start()
                self.assertFalse(purge_called.wait(timeout=0.1))
                release_render.set()
                reader.join(timeout=3)
                deleter.join(timeout=3)

            self.assertFalse(cache_path.exists())

        self.assertFalse(reader.is_alive())
        self.assertFalse(deleter.is_alive())
        self.assertTrue(purge_called.is_set())
        self.assertEqual(observed["response"].status_code, 200)

    def test_delete_forever_route_accepts_legacy_punctuation_id(self):
        server = self.server
        expected = {
            "conversation_id": "legacy.id",
            "action": "delete_forever",
            "deleted": {},
            "retained": {"explicit_vault_exports": True},
            "errors": [],
        }
        with (
            mock.patch.object(server, "_cross_site_mutation_response", return_value=None),
            mock.patch.object(server, "_delete_conversation_runtime",
                              return_value=expected) as delete,
        ):
            response = server.app.test_client().post(
                "/api/conversation/legacy.id/delete-forever",
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        delete.assert_called_once_with("legacy.id")

    def test_worker_quiesce_tombstones_preview(self):
        server = self.server
        from orchestrator import document_input

        preview_forget = mock.Mock(return_value=True)
        with (
            mock.patch.object(server, "_HAS_CAPTURE", False),
            mock.patch.object(server, "_HAS_URL_IMPORT", False),
            mock.patch.object(server, "_HAS_PREVIEW", True),
            mock.patch.object(server, "_preview_forget_conversation",
                              preview_forget),
            mock.patch.object(server, "_HAS_RENDER", False),
            mock.patch.object(document_input, "purge_conversation",
                              return_value={"jobs": 0}),
        ):
            result = server._quiesce_conversation_workers("preview-cleanup")

        preview_forget.assert_called_once_with("preview-cleanup")
        self.assertEqual(result["cleaned"]["preview"], True)


class TestDocumentIdentityPath(unittest.TestCase):
    def test_stealth_output_uses_exact_canonical_session_child(self):
        from orchestrator import document_input

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.object(document_input, "STEALTH_TEMP_ROOT", str(root)):
                output = document_input._write_destination(
                    markdown="body",
                    original_name="Report.pdf",
                    tag="stealth",
                    conversation_id="a-b",
                )
            self.assertEqual(Path(output).parent, root / "a-b" / "documents")
            self.assertTrue(Path(output).is_file())

    def test_stealth_output_rejects_symlinked_documents_directory(self):
        from orchestrator import document_input

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            owner = root / "doc-owner"
            outside = Path(td) / "outside"
            owner.mkdir(parents=True)
            outside.mkdir()
            (owner / "documents").symlink_to(
                outside, target_is_directory=True,
            )

            with (
                mock.patch.object(document_input, "STEALTH_TEMP_ROOT", str(root)),
                self.assertRaises(ValueError),
            ):
                document_input._write_destination(
                    markdown="secret body",
                    original_name="Report.pdf",
                    tag="stealth",
                    conversation_id="doc-owner",
                )

            self.assertEqual(list(outside.iterdir()), [])

    def test_stealth_output_replaces_file_symlink_without_following_target(self):
        from orchestrator import document_input

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            documents = root / "doc-owner" / "documents"
            documents.mkdir(parents=True)
            outside = Path(td) / "outside.md"
            outside.write_text("must remain", encoding="utf-8")
            output = documents / "Report.md"
            output.symlink_to(outside)

            with mock.patch.object(
                document_input, "STEALTH_TEMP_ROOT", str(root),
            ):
                written = document_input._write_destination(
                    markdown="secret body",
                    original_name="Report.pdf",
                    tag="stealth",
                    conversation_id="doc-owner",
                )

            self.assertEqual(Path(written), output)
            self.assertFalse(output.is_symlink())
            self.assertIn("secret body", output.read_text(encoding="utf-8"))
            self.assertEqual(outside.read_text(encoding="utf-8"), "must remain")

    def test_standard_output_rejects_symlinked_incubator_directory(self):
        from orchestrator import document_input

        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            outside = Path(td) / "outside"
            vault.mkdir()
            outside.mkdir()
            (vault / "Incubator").symlink_to(
                outside, target_is_directory=True,
            )

            with (
                mock.patch.object(
                    document_input, "VAULT_INCUBATOR_DIR",
                    str(vault / "Incubator"),
                ),
                self.assertRaises(ValueError),
            ):
                document_input._write_destination(
                    markdown="private body",
                    original_name="Report.pdf",
                    tag="private",
                    conversation_id="doc-owner",
                )

            self.assertEqual(list(outside.iterdir()), [])

    def test_standard_output_rejects_file_symlink_without_touching_target(self):
        from orchestrator import document_input

        with tempfile.TemporaryDirectory() as td:
            incubator = Path(td) / "vault" / "Incubator"
            incubator.mkdir(parents=True)
            outside = Path(td) / "outside.md"
            outside.write_text("must remain", encoding="utf-8")
            (incubator / "Report.md").symlink_to(outside)

            with (
                mock.patch.object(
                    document_input, "VAULT_INCUBATOR_DIR", str(incubator),
                ),
                self.assertRaises(ValueError),
            ):
                document_input._write_destination(
                    markdown="private body",
                    original_name="Report.pdf",
                    tag="private",
                    conversation_id="doc-owner",
                )

            self.assertEqual(outside.read_text(encoding="utf-8"), "must remain")

    def test_purge_rejects_symlinked_session_documents_without_deleting_target(self):
        from orchestrator import document_input

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staging = root / "staging"
            sessions = root / "sessions"
            incubator = root / "vault" / "Incubator"
            outside = root / "outside"
            staging.mkdir()
            (sessions / "doc-owner").mkdir(parents=True)
            incubator.mkdir(parents=True)
            outside.mkdir()
            outside_note = outside / "Report.md"
            outside_note.write_text("must remain", encoding="utf-8")
            (sessions / "doc-owner" / "documents").symlink_to(
                outside, target_is_directory=True,
            )

            document_input.reset_for_tests()
            try:
                with (
                    mock.patch.object(document_input, "STAGING_DIR", str(staging)),
                    mock.patch.object(
                        document_input, "VAULT_INCUBATOR_DIR", str(incubator),
                    ),
                    mock.patch.object(
                        document_input, "STEALTH_TEMP_ROOT", str(sessions),
                    ),
                ):
                    with document_input._jobs_lock:
                        document_input._jobs["job"] = {
                            "processing_id": "job",
                            "conversation_id": "doc-owner",
                            "vault_path": str(
                                sessions / "doc-owner" / "documents" / "Report.md"
                            ),
                            "output_created": True,
                        }
                    result = document_input.purge_conversation("doc-owner")

                self.assertEqual(result["created_outputs"], 0)
                self.assertTrue(result["errors"])
                self.assertEqual(
                    outside_note.read_text(encoding="utf-8"), "must remain",
                )
            finally:
                document_input.reset_for_tests()

    def test_document_start_rejects_lossy_punctuation_ids(self):
        from orchestrator import document_input

        document_input.reset_for_tests()
        try:
            with mock.patch.object(document_input.threading, "Thread", _NoopThread):
                for unsafe in ("a.b", "a:b", "a b", "a/b", "A"):
                    with self.assertRaises(ValueError, msg=unsafe):
                        document_input.start("/tmp/source.pdf", {
                            "conversation_id": unsafe,
                        })
                processing_id = document_input.start("/tmp/source.pdf", {
                    "conversation_id": "a-b",
                })
                self.assertEqual(
                    document_input.get_state(processing_id)["conversation_id"],
                    "a-b",
                )
        finally:
            document_input.reset_for_tests()


if __name__ == "__main__":
    unittest.main()
