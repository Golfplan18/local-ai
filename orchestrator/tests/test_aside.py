"""Aside model preference, dispatch, and five-turn memory regressions."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ORA_HOME"] = _REPO
for _path in (_REPO, os.path.join(_REPO, "server"), os.path.join(_REPO, "orchestrator")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from orchestrator.embedding import install_test_stub  # noqa: E402
install_test_stub()

from orchestrator.router import Router  # noqa: E402
from orchestrator import help_retrieval  # noqa: E402
from server import app as server  # noqa: E402
from sidebar_window import SidebarWindow  # noqa: E402


class SidebarWindowTests(unittest.TestCase):
    def test_keeps_only_five_latest_turn_pairs_in_order(self):
        window = SidebarWindow()
        for idx in range(7):
            window.add_exchange(f"u{idx}", f"a{idx}")
        self.assertEqual(window.get_turn_count(), 5)
        self.assertEqual(window.get_history()[0], {"role": "user", "content": "u2"})
        self.assertEqual(window.get_history()[-1], {"role": "assistant", "content": "a6"})

    def test_transaction_serializes_exchanges(self):
        window = SidebarWindow()
        holder_entered = threading.Event()
        release_holder = threading.Event()
        waiter_entered = threading.Event()

        def hold():
            with window.transaction():
                holder_entered.set()
                release_holder.wait(timeout=2)

        def wait_for_window():
            with window.transaction():
                waiter_entered.set()

        holder = threading.Thread(target=hold)
        waiter = threading.Thread(target=wait_for_window)
        holder.start()
        self.assertTrue(holder_entered.wait(timeout=1))
        waiter.start()
        self.assertFalse(waiter_entered.wait(timeout=0.05))
        release_holder.set()
        holder.join(timeout=1)
        waiter.join(timeout=1)
        self.assertTrue(waiter_entered.is_set())


class ExplicitEndpointResolutionTests(unittest.TestCase):
    def setUp(self):
        # Router.__init__ merges the machine's config/models.json local models
        # into its endpoint table even when handed an explicit config_dict.
        # That is right in production — models.json is the source of truth for
        # local models — but it made these fixtures machine-dependent: on this
        # developer's Mac the six discovered MLX endpoints joined the four
        # below, so the exact-membership assertion could only pass on a machine
        # with no local models installed. These tests are about explicit
        # endpoint resolution, so the discovery merge is switched off.
        merge = mock.patch.object(
            Router, "_merge_models_json_local_endpoints", lambda self: None)
        merge.start()
        self.addCleanup(merge.stop)

    def _router(self):
        return Router(config_dict={
            "endpoints": [
                {"id": "gemini/preferred", "type": "api", "service": "gemini",
                 "model_id": "preferred", "enabled": True, "status": "active"},
                {"id": "local/ready", "type": "local", "enabled": True,
                 "status": "active", "model_path": "/tmp/model"},
                {"id": "api/off", "type": "api", "enabled": False,
                 "status": "active"},
                {"id": "browser/session", "type": "browser", "enabled": True,
                 "status": "active"},
            ]
        })

    @mock.patch("endpoint_health.is_in_cooldown", return_value=False)
    def test_resolves_active_api_and_local_models(self, _cooldown):
        router = self._router()
        self.assertEqual(
            router.resolve_endpoint_by_id("gemini/preferred")["id"],
            "gemini/preferred",
        )
        self.assertEqual(
            router.resolve_endpoint_by_id("LOCAL/READY")["id"],
            "local/ready",
        )

    @mock.patch("endpoint_health.is_in_cooldown", return_value=False)
    def test_rejects_disabled_and_unsupported_models(self, _cooldown):
        router = self._router()
        self.assertIsNone(router.resolve_endpoint_by_id("api/off"))
        self.assertIsNone(router.resolve_endpoint_by_id("browser/session"))
        self.assertIsNone(router.resolve_endpoint_by_id("missing"))

    @mock.patch("endpoint_health.is_in_cooldown")
    def test_list_contains_only_explicitly_resolvable_models(self, cooldown):
        router = self._router()
        self.assertEqual(
            [endpoint["id"] for endpoint in router.list_interactive_endpoints()],
            ["gemini/preferred", "local/ready"],
        )
        cooldown.assert_not_called()

    @mock.patch("endpoint_health.is_in_cooldown", return_value=True)
    def test_resolver_rejects_cooling_model(self, _cooldown):
        self.assertIsNone(
            self._router().resolve_endpoint_by_id("gemini/preferred"))


class ScratchpadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.dialogue = "aside-dialogue-a"
        self.other_dialogue = "aside-dialogue-b"
        server.clear_sidebar_window(self.dialogue)
        server.clear_sidebar_window(self.other_dialogue)
        self.client = server.app.test_client()
        self.preferred = {"name": "gemini/preferred", "type": "api",
                          "service": "gemini", "model": "preferred"}
        self.fallback = {"name": "small/fallback", "type": "api",
                         "service": "openrouter", "model": "fallback"}
        self.patches = [
            mock.patch.object(server, "load_config", return_value={}),
            mock.patch.object(server, "get_endpoint_by_id", return_value=self.preferred),
            mock.patch.object(server, "get_slot_endpoint", return_value=self.fallback),
            mock.patch.object(server._user_settings, "get_setting",
                              return_value="gemini/gemini-3.1-flash-lite"),
            mock.patch.object(server, "get_help_context", return_value=""),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        server.clear_sidebar_window(self.dialogue)
        server.clear_sidebar_window(self.other_dialogue)

    def test_preferred_model_wins_and_prior_exchange_is_sent(self):
        calls = []

        def invoke(messages, endpoint):
            calls.append((list(messages), endpoint))
            return "first answer" if len(calls) == 1 else "second answer"

        with mock.patch.object(server, "call_model", side_effect=invoke):
            first = self.client.post("/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "first"})
            second = self.client.post("/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "second"})

        self.assertEqual(json.loads(first.data)["answer"], "first answer")
        self.assertEqual(json.loads(second.data)["answer"], "second answer")
        self.assertEqual(calls[0][1], self.preferred)
        self.assertEqual(calls[1][0], [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "second"},
        ])
        with mock.patch.object(server, "call_model", side_effect=invoke):
            other = self.client.post("/api/scratchpad", json={
                "conversation_id": self.other_dialogue, "prompt": "only B",
            })
            missing = self.client.post("/api/scratchpad", json={"prompt": "unowned"})
        self.assertEqual(json.loads(other.data)["conversation_id"], self.other_dialogue)
        self.assertEqual(calls[2][0], [{"role": "user", "content": "only B"}])
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(server.get_sidebar_window(self.dialogue).get_turn_count(), 2)
        with mock.patch.object(server, "call_model", return_value="[Error] unavailable"):
            failed = self.client.post("/api/scratchpad", json={
                "conversation_id": self.dialogue, "prompt": "failed exchange",
            })
        self.assertEqual(json.loads(failed.data), {
            "error": "[Error] unavailable", "conversation_id": self.dialogue,
        })
        self.assertEqual(server.get_sidebar_window(self.dialogue).get_turn_count(), 2)


    def test_failed_exchange_is_not_added_to_memory(self):
        seen = []

        def invoke(messages, _endpoint):
            seen.append(list(messages))
            return "[Error] unavailable" if len(seen) == 1 else "ok"

        with mock.patch.object(server, "call_model", side_effect=invoke):
            failed = self.client.post("/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "lost"})
            succeeded = self.client.post("/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "kept"})

        self.assertIn("error", json.loads(failed.data))
        self.assertEqual(json.loads(succeeded.data)["answer"], "ok")
        self.assertEqual(seen[1], [{"role": "user", "content": "kept"}])

    def test_help_context_is_ephemeral_and_prepended(self):
        seen = []

        def invoke(messages, _endpoint):
            seen.append(list(messages))
            return "helpful answer"

        with mock.patch.object(server, "get_help_context", return_value="HELP CONTEXT"), \
             mock.patch.object(server, "call_model", side_effect=invoke):
            response = self.client.post(
                "/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "How do I install Ora?"})

        self.assertEqual(json.loads(response.data)["answer"], "helpful answer")
        self.assertEqual(seen[0], [
            {"role": "system", "content": "HELP CONTEXT"},
            {"role": "user", "content": "How do I install Ora?"},
        ])
        self.assertEqual(server.get_sidebar_window(self.dialogue).get_history(), [
            {"role": "user", "content": "How do I install Ora?"},
            {"role": "assistant", "content": "helpful answer"},
        ])

    def test_help_failure_does_not_block_non_help_question(self):
        with mock.patch.object(
                server, "get_help_context", side_effect=RuntimeError("offline")), \
             mock.patch.object(server, "call_model", return_value="a limerick") as call:
            response = self.client.post(
                "/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "Write a limerick"})

        self.assertEqual(json.loads(response.data)["answer"], "a limerick")
        self.assertEqual(call.call_args.args[0], [
            {"role": "user", "content": "Write a limerick"},
        ])

    def test_slow_first_help_lookup_preserves_causal_exchange_order(self):
        first_lookup_started = threading.Event()
        release_first_lookup = threading.Event()
        second_lookup_started = threading.Event()
        second_reached_endpoint_resolution = threading.Event()
        responses = {}
        model_calls = []

        def lookup(prompt):
            if prompt == "first":
                first_lookup_started.set()
                release_first_lookup.wait(timeout=2)
            else:
                second_lookup_started.set()
            return ""

        def invoke(messages, _endpoint):
            model_calls.append(list(messages))
            return f"answer to {messages[-1]['content']}"

        def resolve_endpoint(_endpoint_id):
            if threading.current_thread().name == "aside-second":
                second_reached_endpoint_resolution.set()
            return self.preferred

        def submit(prompt):
            with server.app.test_client() as client:
                responses[prompt] = client.post(
                    "/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": prompt})

        with mock.patch.object(server, "get_endpoint_by_id",
                               side_effect=resolve_endpoint), \
             mock.patch.object(server, "get_help_context", side_effect=lookup), \
             mock.patch.object(server, "call_model", side_effect=invoke):
            first = threading.Thread(
                target=submit, args=("first",), name="aside-first")
            second = threading.Thread(
                target=submit, args=("second",), name="aside-second")
            first.start()
            self.assertTrue(first_lookup_started.wait(timeout=1))
            second.start()
            self.assertTrue(second_reached_endpoint_resolution.wait(timeout=1))
            self.assertFalse(second_lookup_started.wait(timeout=0.1))
            release_first_lookup.set()
            first.join(timeout=2)
            second.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(json.loads(responses["first"].data)["answer"],
                         "answer to first")
        self.assertEqual(json.loads(responses["second"].data)["answer"],
                         "answer to second")
        self.assertEqual(model_calls, [
            [{"role": "user", "content": "first"}],
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "answer to first"},
                {"role": "user", "content": "second"},
            ],
        ])
        self.assertEqual(server.get_sidebar_window(self.dialogue).get_history(), [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer to first"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "answer to second"},
        ])

    def test_unavailable_preference_falls_back_to_small(self):
        with mock.patch.object(server, "get_endpoint_by_id", return_value=None), \
             mock.patch.object(server, "call_model", return_value="fallback answer") as call:
            response = self.client.post("/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "hello"})
        self.assertEqual(json.loads(response.data)["answer"], "fallback answer")
        self.assertEqual(call.call_args.args[1], self.fallback)

    def test_model_inventory_uses_explicit_resolver_choices(self):
        models = [{
            "id": "gemini/preferred",
            "display_name": "Preferred",
            "type": "api",
            "provider": "gemini",
        }]
        with mock.patch.object(
                server, "list_interactive_endpoints", return_value=models):
            response = self.client.get("/api/aside/models")
        self.assertEqual(json.loads(response.data), {"models": models})

    def test_sidebar_status_and_clear_share_the_aside_window(self):
        seen = []

        def invoke(messages, _endpoint):
            seen.append(list(messages))
            return "answer"

        with mock.patch.object(server, "call_model", side_effect=invoke):
            self.client.post("/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "first"})
            status = self.client.get("/api/sidebar/status", query_string={"panel_id": self.dialogue})
            server.get_sidebar_window(self.other_dialogue).add_exchange("B prompt", "B answer")
            cleared = self.client.post(
                "/api/sidebar/clear", json={"panel_id": self.dialogue})
            self.client.post("/api/scratchpad", json={"conversation_id": self.dialogue, "prompt": "second"})

        self.assertEqual(json.loads(status.data)["turn_count"], 1)
        self.assertTrue(json.loads(cleared.data)["ok"])
        self.assertEqual(seen[1], [{"role": "user", "content": "second"}])
        self.assertEqual(server.get_sidebar_window(self.other_dialogue).get_history(), [
            {"role": "user", "content": "B prompt"},
            {"role": "assistant", "content": "B answer"},
        ])
        with server._conversation_lifecycle_lock(self.dialogue):
            server._deleted_conversations.add(self.dialogue)
            server.clear_sidebar_window(self.dialogue)
        try:
            with mock.patch.object(server, "call_model") as invoke:
                late = self.client.post("/api/scratchpad", json={
                    "conversation_id": self.dialogue, "prompt": "late",
                })
                status = self.client.get("/api/sidebar/status", query_string={
                    "panel_id": self.dialogue,
                })
            self.assertEqual(late.status_code, 410)
            self.assertEqual(status.status_code, 410)
            invoke.assert_not_called()
        finally:
            server._deleted_conversations.discard(self.dialogue)



class _FakeHelpCollection:
    def __init__(self, *, metadata=None):
        self.name = "help"
        self.metadata = metadata
        self.rows = {}
        self.upsert_calls = []
        self.delete_calls = []

    def get(self, include=None):
        del include
        ids = list(self.rows)
        return {
            "ids": ids,
            "metadatas": [self.rows[chunk_id]["metadata"] for chunk_id in ids],
        }

    def upsert(self, *, ids, documents, metadatas):
        self.upsert_calls.append(list(ids))
        for chunk_id, document, metadata in zip(ids, documents, metadatas):
            self.rows[chunk_id] = {"document": document, "metadata": metadata}

    def delete(self, *, ids):
        self.delete_calls.append(list(ids))
        for chunk_id in ids:
            self.rows.pop(chunk_id, None)

    def query(self, **_kwargs):
        return {"metadatas": [[]], "documents": [[]], "distances": [[]]}


class _FakeHelpClient:
    def __init__(self, collection=None, *, fail_query=False):
        self.collection = collection or _FakeHelpCollection()
        self.fail_query = fail_query

    def get_or_create_collection(self, **_kwargs):
        return self.collection

    def get_collection(self, **_kwargs):
        if self.fail_query:
            raise RuntimeError("Chroma unavailable")
        return self.collection

    def list_collections(self):
        return [self.collection]


class HelpRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.help_dir = Path(self.tmp.name)
        (self.help_dir / "install-guide.md").write_text(
            "# Install Guide\n\n## Run the installer\n\n"
            "Use scripts/install.py to install Ora on macOS.\n",
            encoding="utf-8",
        )
        (self.help_dir / "user-guide.md").write_text(
            "# Using Ora\n\n## Aside\n\n"
            "Aside gives quick product answers and is not saved.\n",
            encoding="utf-8",
        )
        for filename, title in (
            ("accessible-overview.md", "Accessible Overview"),
            ("install-manual.md", "Manual Install"),
            ("install-recovery.md", "Install Recovery"),
        ):
            (self.help_dir / filename).write_text(
                f"# {title}\n\nTracked help content.\n", encoding="utf-8")
        (self.help_dir / "private.md").write_text(
            "# Private\n\nThis untracked file must never be indexed.\n",
            encoding="utf-8",
        )
        (self.help_dir / "notes.txt").write_text(
            "not markdown", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_heading_chunks_are_deterministic_and_whitelisted(self):
        first = help_retrieval.load_help_chunks(self.help_dir)
        second = help_retrieval.load_help_chunks(self.help_dir)

        self.assertEqual(first, second)
        self.assertTrue(all(chunk.source.startswith("help/") for chunk in first))
        self.assertTrue(any("Run the installer" in chunk.heading for chunk in first))
        self.assertFalse(any(
            chunk.source.endswith("private.md") for chunk in first))
        self.assertTrue(all(len(chunk.content_hash) == 64 for chunk in first))

    def test_fake_chroma_refresh_handles_changed_unchanged_and_stale_chunks(self):
        chunks = help_retrieval.load_help_chunks(self.help_dir)
        collection = _FakeHelpCollection()
        first = chunks[0]
        collection.rows[first.chunk_id] = {
            "document": "old",
            "metadata": {"content_hash": "old", "corpus": "help"},
        }
        collection.rows["stale-help-chunk"] = {
            "document": "stale",
            "metadata": {"content_hash": "stale", "corpus": "help"},
        }
        client = _FakeHelpClient(collection)

        changed = help_retrieval.refresh_help_index(
            help_dir=self.help_dir, client=client)
        self.assertTrue(changed["changed"])
        self.assertEqual(changed["upserted"], len(chunks))
        self.assertEqual(changed["deleted"], 1)
        self.assertNotIn("stale-help-chunk", collection.rows)

        collection.upsert_calls.clear()
        collection.delete_calls.clear()
        unchanged = help_retrieval.refresh_help_index(
            help_dir=self.help_dir, client=client)
        self.assertFalse(unchanged["changed"])
        self.assertEqual(collection.upsert_calls, [])
        self.assertEqual(collection.delete_calls, [])

        (self.help_dir / "install-guide.md").write_text(
            "# Install Guide\n\n## Run the installer\n\n"
            "Use scripts/install.py --profile solo to install Ora on macOS.\n",
            encoding="utf-8",
        )
        refreshed = help_retrieval.refresh_help_index(
            help_dir=self.help_dir, client=client)
        self.assertTrue(refreshed["changed"])
        self.assertGreaterEqual(refreshed["upserted"], 1)

    def test_query_fails_open_to_source_labelled_lexical_results(self):
        snippets = help_retrieval.search_help(
            "How do I install Ora?",
            help_dir=self.help_dir,
            client=_FakeHelpClient(fail_query=True),
        )
        self.assertTrue(snippets)
        self.assertEqual(snippets[0].source, "help/install-guide.md")
        self.assertIn("Run the installer", snippets[0].heading)

        unrelated = help_retrieval.search_help(
            "Compose a poem about geese",
            help_dir=self.help_dir,
            client=_FakeHelpClient(fail_query=True),
        )
        self.assertEqual(unrelated, [])

        video = help_retrieval.search_help(
            "How do I start using Ora video?",
            help_dir=Path(_REPO) / "help",
            client=_FakeHelpClient(fail_query=True),
        )
        self.assertTrue(video)
        self.assertIn("Use Audio & Video", video[0].heading)
        sections = [(snippet.source, snippet.heading) for snippet in video]
        self.assertEqual(len(sections), len(set(sections)))

    def test_refresh_preserves_foreign_and_unknown_rows(self):
        chunks = help_retrieval.load_help_chunks(self.help_dir)
        collection = _FakeHelpCollection(
            metadata={"ora:logical_collection": "help"})
        for chunk in chunks:
            collection.rows[chunk.chunk_id] = {
                "document": chunk.text,
                "metadata": chunk.metadata(),
            }
        collision = chunks[0]
        collection.rows[collision.chunk_id] = {
            "document": "foreign collision",
            "metadata": {"content_hash": "foreign", "corpus": "knowledge"},
        }
        collection.rows["foreign-stale"] = {
            "document": "foreign stale",
            "metadata": {"content_hash": "foreign", "corpus": "knowledge"},
        }
        collection.rows["unknown-stale"] = {
            "document": "unknown stale",
            "metadata": {"content_hash": "unknown"},
        }
        collection.rows["help-stale"] = {
            "document": "help stale",
            "metadata": {"content_hash": "stale", "corpus": "help"},
        }
        before = json.loads(json.dumps(collection.rows))

        with self.assertRaisesRegex(RuntimeError, "help index is incomplete"):
            help_retrieval.refresh_help_index(
                help_dir=self.help_dir, client=_FakeHelpClient(collection))

        self.assertEqual(collection.rows, before)
        self.assertEqual(collection.upsert_calls, [])
        self.assertEqual(collection.delete_calls, [])

    def test_refresh_refuses_configured_alias_and_foreign_owner(self):
        collection = _FakeHelpCollection(
            metadata={"ora:logical_collection": "knowledge"})
        client = _FakeHelpClient(collection)
        with mock.patch.dict(
                help_retrieval.embedding.COLLECTIONS,
                {"help": "shared", "knowledge": "shared"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "configured for help"):
                help_retrieval.refresh_help_index(
                    help_dir=self.help_dir, client=client)
        self.assertEqual(collection.upsert_calls, [])
        self.assertEqual(collection.delete_calls, [])

        collection.metadata = {"ora:logical_collection": "knowledge"}
        with self.assertRaisesRegex(RuntimeError, "owned by logical corpus"):
            help_retrieval.refresh_help_index(
                help_dir=self.help_dir, client=client)
        self.assertEqual(collection.upsert_calls, [])
        self.assertEqual(collection.delete_calls, [])

    def test_core_product_question_uses_accessible_overview_lexically(self):
        (self.help_dir / "accessible-overview.md").write_text(
            "# Ora — An Accessible Overview\n\n## What Ora is\n\n"
            "Ora makes AI reliable enough to trust with real work.\n",
            encoding="utf-8",
        )

        snippets = help_retrieval.search_help(
            "What is Ora?",
            help_dir=self.help_dir,
            client=_FakeHelpClient(fail_query=True),
        )

        self.assertTrue(snippets)
        self.assertEqual(snippets[0].source, "help/accessible-overview.md")
        self.assertIn("What Ora is", snippets[0].heading)


if __name__ == "__main__":
    unittest.main()
