"""G1.4 reviewed creation and contributor-context contracts."""
from __future__ import annotations

import os
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
for value in (REPO, REPO / "orchestrator", REPO / "server"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))
os.environ.setdefault("ORA_HOME", str(REPO))

from orchestrator.embedding import install_test_stub  # noqa: E402

install_test_stub()
import active_project  # noqa: E402
import conversation_memory as runtime_memory  # noqa: E402
from orchestrator import boot  # noqa: E402
from orchestrator import conversation_memory as package_memory  # noqa: E402
from server import app as server  # noqa: E402


DESCRIPTION = "Explore cash-flow exception patterns and decide a reusable response."


class G14ConversationManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sessions = self.root / "sessions"
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.atomic = self.vault / "Atomic — Cash Flow Exception.md"
        self.atomic.write_text(
            "---\nnexus:\n  - ora\ntype: engram\ntags:\n  - atomic\n---\n"
            "# Cash Flow Exception\n\nA durable observation about late receipts.\n",
            encoding="utf-8",
        )
        self.stack = ExitStack()
        for module in (runtime_memory, package_memory):
            self.stack.enter_context(
                mock.patch.object(module, "_DEFAULT_SESSIONS_ROOT", self.sessions)
            )
        self.stack.enter_context(mock.patch.object(server.rp, "vault_dir", return_value=self.vault))
        self.stack.enter_context(mock.patch.object(active_project, "get_active_project", return_value="ora"))
        self.stack.enter_context(mock.patch.object(active_project, "resolve_project_ids", return_value=["ora"]))
        with server._conversation_discovery_lock:
            server._conversation_discovery_reviews.clear()
        self.client = server.app.test_client()

        runtime_memory.create_conversation_envelope(
            "source-dialogue",
            title="Prior cash-flow work",
            description="Review prior finance observations and identify the exception pattern.",
            sessions_root=self.sessions,
        )
        runtime_memory.save_turn_spatial_state(
            "source-dialogue",
            "The receipt arrived late.",
            "Treat it as a timing exception.",
            sessions_root=self.sessions,
        )

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def _source_row(self, **overrides):
        row = {
            "conversation_id": "source-dialogue",
            "source_kind": "live",
            "result_type": "live_conversation",
            "tag": "",
            "tags": [],
            "title": "Prior cash-flow work",
            "snippet": "The receipt arrived late.",
            "score": 100,
            "search_relevance": 100,
            "last_activity_at": "2026-07-20T12:00:00Z",
            "closed": False,
        }
        row.update(overrides)
        return row

    def _private_contributor_target(self, target_id):
        source_id = f"{target_id}-private-source"
        secret = f"PRIVATE-CONTRIBUTOR-TEXT-{target_id}"
        runtime_memory.create_conversation_envelope(
            source_id,
            title="Private contributor",
            description="Private source for the lifecycle interleaving test.",
            tag="private",
            sessions_root=self.sessions,
        )
        runtime_memory.save_turn_spatial_state(
            source_id,
            secret,
            "Private contributor response.",
            sessions_root=self.sessions,
        )
        runtime_memory.create_conversation_envelope(
            target_id,
            title="Private target",
            description="Target whose privacy changes before execution.",
            tag="private",
            contributors=[{
                "kind": "conversation",
                "ref": source_id,
                "title": "Private contributor",
            }],
            sessions_root=self.sessions,
        )
        return secret

    def _discover(self, rows=None):
        rows = rows if rows is not None else [self._source_row()]
        with (
            mock.patch.object(server, "_browser_live_rows", return_value=rows),
            mock.patch.object(server, "_browser_chroma_exact_rows", return_value=[]),
            mock.patch.object(server, "_browser_chroma_fuzzy_rows", return_value=[]),
            mock.patch.object(server, "_browser_chroma_semantic_rows", return_value=[]),
            mock.patch.object(server, "_browser_vault_markdown_rows", return_value=[]),
        ):
            response = self.client.get(
                "/api/conversations/browser",
                query_string={
                    "q": DESCRIPTION,
                    "purpose": "creation",
                    "conversations": "1",
                    "engrams": "1",
                },
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def _acknowledge(self, review_token, contributors=None, **overrides):
        payload = {
            "title": "Cash-flow exception analysis",
            "description": DESCRIPTION,
            "review_token": review_token,
            "contributors": contributors or [],
            "tag": "",
            "acknowledged": True,
        }
        payload.update(overrides)
        return self.client.post("/api/conversations/review", json=payload)

    def _create(self, review_token, contributors=None, **overrides):
        acknowledged = self._acknowledge(review_token, contributors, **overrides)
        if acknowledged.status_code != 200:
            return acknowledged
        contract = acknowledged.get_json()
        return self.client.post("/api/conversations/create", json={
            "review_token": review_token,
            "creation_token": contract["creation_token"],
        })

    def test_discovery_is_observation_only_then_exact_acceptance_commits(self):
        before = {path.name for path in self.sessions.iterdir()}
        discovery = self._discover()
        self.assertTrue(discovery["review_token"].startswith("review-"))
        self.assertEqual({path.name for path in self.sessions.iterdir()}, before)

        response = self._create(
            discovery["review_token"], contributors=["source-dialogue"]
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        result = response.get_json()
        stored = runtime_memory.load_conversation_json(
            result["conversation_id"], sessions_root=self.sessions
        )
        self.assertEqual(stored["display_name"], "Cash-flow exception analysis")
        self.assertEqual(stored["description"], DESCRIPTION)
        self.assertEqual(stored["project_ids"], ["ora"])
        self.assertEqual(stored["messages"], [])
        self.assertEqual(stored["contributors"], [{
            "kind": "conversation",
            "ref": "source-dialogue",
            "title": "Prior cash-flow work",
        }])

        replay = self._create(
            discovery["review_token"], contributors=["source-dialogue"]
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.get_json()["conversation_id"], result["conversation_id"])
        self.assertTrue(replay.get_json()["idempotent_replay"])

    def test_unreviewed_changed_and_forged_inputs_cannot_create(self):
        discovery = self._discover()
        count = len(list(self.sessions.iterdir()))
        direct = self.client.post("/api/conversations/create", json={
            "review_token": discovery["review_token"],
        })
        self.assertEqual(direct.status_code, 400)
        unacknowledged = self._acknowledge(
            discovery["review_token"], acknowledged=False
        )
        self.assertEqual(unacknowledged.status_code, 400)
        acknowledged = self._acknowledge(discovery["review_token"])
        self.assertEqual(acknowledged.status_code, 200)
        tampered_contract = self.client.post("/api/conversations/create", json={
            "review_token": discovery["review_token"],
            "creation_token": acknowledged.get_json()["creation_token"],
            "title": "Client-side replacement title",
        })
        self.assertEqual(tampered_contract.status_code, 400)
        self.assertEqual(self._create("review-missing").status_code, 409)
        self.assertEqual(
            self._create(discovery["review_token"], description=DESCRIPTION + " Changed.").status_code,
            409,
        )
        self.assertEqual(
            self._create(discovery["review_token"], contributors=["forged-dialogue"]).status_code,
            409,
        )
        self.assertEqual(len(list(self.sessions.iterdir())), count)

    def test_concurrent_delivery_of_one_contract_creates_one_dialogue(self):
        discovery = self._discover()
        acknowledged = self._acknowledge(
            discovery["review_token"], contributors=["source-dialogue"]
        )
        self.assertEqual(acknowledged.status_code, 200)
        contract = acknowledged.get_json()
        payload = {
            "review_token": discovery["review_token"],
            "creation_token": contract["creation_token"],
        }
        barrier = threading.Barrier(2)
        responses = []
        errors = []

        def deliver():
            try:
                with server.app.test_client() as client:
                    barrier.wait(timeout=5)
                    response = client.post("/api/conversations/create", json=payload)
                    responses.append((response.status_code, response.get_json()))
            except Exception as exc:  # pragma: no cover - diagnostic capture
                errors.append(exc)

        threads = [threading.Thread(target=deliver) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])
        self.assertEqual(len(responses), 2)
        self.assertEqual({status for status, _ in responses}, {200, 201})
        identities = {body["conversation_id"] for _, body in responses}
        self.assertEqual(identities, {contract["conversation_id"]})
        self.assertTrue(any(body["idempotent_replay"] for _, body in responses))
        created = [
            path for path in self.sessions.iterdir()
            if path.name == contract["conversation_id"]
        ]
        self.assertEqual(len(created), 1)

    def test_interrupted_success_recovers_same_identity_without_token_loss(self):
        discovery = self._discover()
        acknowledged = self._acknowledge(discovery["review_token"])
        self.assertEqual(acknowledged.status_code, 200)
        contract = acknowledged.get_json()
        payload = {
            "review_token": discovery["review_token"],
            "creation_token": contract["creation_token"],
        }
        real_create = runtime_memory.create_conversation_envelope

        def create_then_interrupt(*args, **kwargs):
            real_create(*args, **kwargs)
            raise OSError("injected response-boundary interruption")

        with mock.patch.object(
            runtime_memory,
            "create_conversation_envelope",
            side_effect=create_then_interrupt,
        ):
            interrupted = self.client.post("/api/conversations/create", json=payload)
        self.assertEqual(interrupted.status_code, 500)
        self.assertIsNotNone(runtime_memory.load_conversation_json(
            contract["conversation_id"], sessions_root=self.sessions
        ))

        recovered = self.client.post("/api/conversations/create", json=payload)
        self.assertEqual(recovered.status_code, 201, recovered.get_data(as_text=True))
        self.assertEqual(recovered.get_json()["conversation_id"], contract["conversation_id"])
        replay = self.client.post("/api/conversations/create", json=payload)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.get_json()["conversation_id"], contract["conversation_id"])
        self.assertEqual(
            len([path for path in self.sessions.iterdir() if path.name == contract["conversation_id"]]),
            1,
        )

    def test_expired_review_cannot_create(self):
        discovery = self._discover()
        with server._conversation_discovery_lock:
            server._conversation_discovery_reviews[discovery["review_token"]]["created_at"] = (
                time.time() - server._CONVERSATION_DISCOVERY_TTL_SECONDS - 1
            )
        self.assertEqual(self._create(discovery["review_token"]).status_code, 409)

    def test_atomic_note_must_authenticate_inside_vault(self):
        encoded = server._browser_encode_source_id("engram", str(self.atomic))
        atomic_row = {
            "conversation_id": encoded,
            "source_kind": "engram",
            "result_type": "vault_note",
            "tags": ["atomic"],
            "title": "Cash Flow Exception",
            "snippet": "A durable observation.",
            "score": 100,
            "search_relevance": 100,
        }
        token = server._register_conversation_discovery(
            DESCRIPTION, [atomic_row], target_tag=""
        )
        response = self._create(token, contributors=[encoded])
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        stored = runtime_memory.load_conversation_json(
            response.get_json()["conversation_id"], sessions_root=self.sessions
        )
        self.assertEqual(stored["contributors"][0]["path"], str(self.atomic.resolve()))

        non_atomic = self.vault / "Working note.md"
        non_atomic.write_text("---\ntype: working\ntags: [working]\n---\nbody", encoding="utf-8")
        bad_ref = server._browser_encode_source_id("engram", str(non_atomic))
        bad_token = server._register_conversation_discovery(
            DESCRIPTION,
            [{
                **atomic_row,
                "conversation_id": bad_ref,
                "tags": ["working"],
            }],
            target_tag="",
        )
        self.assertEqual(self._create(bad_token, contributors=[bad_ref]).status_code, 409)

    def test_private_contributor_cannot_flow_into_standard(self):
        runtime_memory.create_conversation_envelope(
            "private-source",
            title="Private finance work",
            description="Keep this finance observation inside the private context boundary.",
            tag="private",
            sessions_root=self.sessions,
        )
        private_row = self._source_row(
            conversation_id="private-source",
            title="Private finance work",
            tag="private",
        )
        token = server._register_conversation_discovery(
            DESCRIPTION, [private_row], target_tag=""
        )
        denied = self._create(token, contributors=["private-source"])
        self.assertEqual(denied.status_code, 409)

        private_token = server._register_conversation_discovery(
            DESCRIPTION, [private_row], target_tag="private"
        )
        allowed = self._create(
            private_token,
            contributors=["private-source"],
            tag="private",
        )
        self.assertEqual(allowed.status_code, 201, allowed.get_data(as_text=True))

    def test_contributor_bundle_uses_complete_units_in_single_physical_lane(self):
        runtime_memory.create_conversation_envelope(
            "target-dialogue",
            title="Target",
            description=DESCRIPTION,
            contributors=[{
                "kind": "conversation",
                "ref": "source-dialogue",
                "title": "Prior cash-flow work",
            }, {
                "kind": "atomic_note",
                "path": str(self.atomic),
                "title": "Cash Flow Exception",
            }],
            sessions_root=self.sessions,
        )
        indexed_unit = {
            "lane": "contributor",
            "unit_id": "knowledge:atomic-1",
            "provenance_id": "knowledge:atomic-1",
            "source_id": "selected-source-1",
            "explicit_index": 1,
            "order": 0,
            "content": "A durable observation about late receipts.",
        }
        with mock.patch.object(
            server, "_indexed_atomic_contributor_units",
            return_value=[indexed_unit],
        ):
            bundle = server.build_contributor_bundle("target-dialogue")
        self.assertEqual(
            [source["status"] for source in bundle["sources"]],
            ["available", "available"],
        )
        self.assertTrue(any(
            "The receipt arrived late" in unit["content"]
            for unit in bundle["units"]
        ))
        self.assertTrue(any(
            "A durable observation" in unit["content"]
            for unit in bundle["units"]
        ))
        prompt = boot.build_system_prompt_for_gear({
            "mode_text": (REPO / "modes" / "root-cause-analysis.md").read_text(encoding="utf-8"),
            "mode_name": "root-cause-analysis",
            "conversation_rag": "",
            "concept_rag": "",
            "relationship_rag": "",
        })
        self.assertNotIn("DIALOGUE CONTRIBUTORS", prompt)
        token = boot.set_optional_context_context(
            bundle["units"], {"sources": bundle["sources"]},
        )
        try:
            prepared, stats = boot.prepare_messages_with_continuity(
                [{"role": "system", "content": prompt},
                 {"role": "user", "content": "Current question"}],
                {"type": "api", "context_window": 100_000, "max_tokens": 1_000},
                history=[],
            )
        finally:
            boot.reset_optional_context_context(token)
        reference_messages = [
            message for message in prepared
            if "OPTIONAL REFERENCE DATA" in message.get("content", "")
        ]
        self.assertEqual(len(reference_messages), 1)
        self.assertIn("The receipt arrived late", reference_messages[0]["content"])
        self.assertIn("A durable observation", reference_messages[0]["content"])
        self.assertTrue(stats["context_coverage"]["lossless_when_fit"])

    def test_fork_preserves_contributor_lineage(self):
        runtime_memory.create_conversation_envelope(
            "parent-with-contributor",
            title="Parent",
            description=DESCRIPTION,
            contributors=[{
                "kind": "conversation",
                "ref": "source-dialogue",
                "title": "Prior cash-flow work",
            }],
            sessions_root=self.sessions,
        )
        runtime_memory.fork_conversation(
            "parent-with-contributor", "child-with-contributor",
            sessions_root=self.sessions,
        )
        child = runtime_memory.load_conversation_json(
            "child-with-contributor", sessions_root=self.sessions
        )
        self.assertEqual(child["contributors"][0]["ref"], "source-dialogue")
        self.assertEqual(child["description"], DESCRIPTION)

    def test_public_chat_threads_contributors_into_pipeline_context(self):
        runtime_memory.create_conversation_envelope(
            "context-target",
            title="Context target",
            description=DESCRIPTION,
            contributors=[{
                "kind": "conversation",
                "ref": "source-dialogue",
                "title": "Prior cash-flow work",
            }],
            sessions_root=self.sessions,
        )
        with (
            mock.patch.object(server, "_log_pending_submission", return_value="submission-1"),
            mock.patch.object(
                server,
                "_invoke_pipeline_unlocked",
                return_value=server._json_response({"ok": True}),
            ) as invoke,
        ):
            response = self.client.post("/chat", json={
                "message": "Use the relevant prior observation.",
                "conversation_id": "context-target",
                "panel_id": "context-target",
                "history": [],
            })
        self.assertEqual(response.status_code, 200)
        bundle = invoke.call_args.kwargs["extra_context"]["contributor_bundle"]
        self.assertEqual(bundle["sources"][0]["status"], "available")
        self.assertTrue(any(
            "timing exception" in unit["content"] for unit in bundle["units"]
        ))

    def _assert_private_contributor_rechecked_after_standard_transition(
        self, route_kind,
    ):
        target_id = f"{route_kind}-privacy-race"
        secret = self._private_contributor_target(target_id)
        real_invoke = server._invoke_pipeline

        def transition_then_invoke(*args, **kwargs):
            with server._conversation_lifecycle_lock(target_id):
                self.assertEqual(
                    runtime_memory.get_conversation_tag(
                        target_id, sessions_root=self.sessions,
                    ),
                    "private",
                )
                runtime_memory.set_conversation_tag(
                    target_id, "", sessions_root=self.sessions,
                )
            return real_invoke(*args, **kwargs)

        with (
            mock.patch.object(
                server, "_log_pending_submission",
                return_value=f"submission-{route_kind}",
            ),
            mock.patch.object(
                server, "_invoke_pipeline", side_effect=transition_then_invoke,
            ),
            mock.patch.object(
                server, "_invoke_pipeline_unlocked",
                return_value=server._json_response({"ok": True}),
            ) as invoke,
        ):
            if route_kind == "json":
                response = self.client.post("/chat", json={
                    "message": "Run after the privacy transition.",
                    "conversation_id": target_id,
                    "panel_id": target_id,
                    "history": [],
                    "tag": "private",
                })
            else:
                response = self.client.post(
                    "/chat/multipart",
                    data={
                        "message": "Run after the privacy transition.",
                        "conversation_id": target_id,
                        "panel_id": target_id,
                        "history": "[]",
                        "tag": "private",
                    },
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(invoke.call_args.kwargs["tag"], "")
        context = invoke.call_args.kwargs["extra_context"]
        self.assertNotIn(secret, json.dumps(context, sort_keys=True))
        self.assertEqual(
            context["contributor_bundle"]["sources"][0]["status"],
            "withheld",
        )

    def test_json_private_contributor_is_rechecked_after_standard_transition(self):
        self._assert_private_contributor_rechecked_after_standard_transition(
            "json",
        )

    def test_multipart_private_contributor_is_rechecked_after_standard_transition(self):
        self._assert_private_contributor_rechecked_after_standard_transition(
            "multipart",
        )

    def test_direct_wrapper_binds_the_same_structured_contributor_units(self):
        observed = {}
        extra_context = {
            "contributor_bundle": {
                "units": [{
                    "lane": "contributor", "unit_id": "direct-contributor",
                    "provenance_id": "direct-contributor",
                    "source_id": "selected-source-0", "explicit_index": 0,
                    "content": "direct contributor evidence",
                }],
                "sources": [{
                    "source_id": "selected-source-0", "explicit_index": 0,
                    "status": "available",
                }],
                "exclude_conversation_ids": [],
                "exclude_paths": [],
            },
        }

        def implementation(*_args, **_kwargs):
            state = server._boot_context_api()._OPTIONAL_CONTEXT_CV.get() or {}
            observed["units"] = list(state.get("units") or [])
            yield "direct-result"

        with mock.patch.object(
            server, "_direct_stream_impl", side_effect=implementation,
        ):
            result = list(server._direct_stream(
                "Current question", [], panel_id="direct-target",
                extra_context=extra_context,
            ))
        self.assertEqual(result, ["direct-result"])
        self.assertEqual(len(observed["units"]), 1)
        self.assertEqual(
            observed["units"][0]["content"], "direct contributor evidence",
        )

    def test_direct_physical_call_emits_coverage_sse_without_duplicate_lane(self):
        import risk_gate
        import tool_events
        from orchestrator import oversight_events

        # Exercise the exact boot module that owns ``server.call_model``.
        # Another hermetic suite force-loads ``boot`` during collection, so
        # resolving sys.modules here can otherwise bind ContextVars and the
        # transport mock to a newer module while this server call remains
        # bound to its original function globals.
        call_globals = server.call_model.__globals__
        legacy_boot = types.SimpleNamespace(**{
            name: call_globals[name] for name in (
                "set_conversation_tag_context",
                "reset_conversation_tag_context",
                "set_turn_trace_context",
                "reset_turn_trace_context",
                "_finalize_optional_context_package",
                "set_dialogue_history_context",
                "reset_dialogue_history_context",
                "_set_context_units_from_package",
                "reset_optional_context_context",
                "set_model_stage_context",
                "reset_model_stage_context",
                "get_context_coverage",
            )
        })
        endpoint = {
            "type": "api", "id": "direct-test", "context_window": 100_000,
            "max_tokens": 1_000,
        }
        captured = []

        def transport(messages, _endpoint, images=None):
            captured.append(messages)
            return "Direct final answer"

        secret = "/Users/private/SECRET_TITLE.md"
        extra_context = {
            "contributor_bundle": {
                "units": [{
                    "lane": "contributor", "unit_id": secret,
                    "provenance_id": secret, "source_id": secret,
                    "source_path": secret, "title": secret,
                    "explicit_index": 0,
                    "content": "DIRECT UNIQUE EVIDENCE",
                }],
                "sources": [{
                    "source_id": secret, "title": secret,
                    "explicit_index": 0, "status": "available",
                }],
                "exclude_conversation_ids": [], "exclude_paths": [],
            },
        }
        with (
            mock.patch.object(server, "load_config", return_value={}),
            mock.patch.object(server, "get_endpoint", return_value=endpoint),
            mock.patch.object(server, "_direct_system_prompt", return_value="system"),
            mock.patch.object(server, "set_permission_mode"),
            mock.patch.object(server, "_boot_context_api", return_value=legacy_boot),
            mock.patch.dict(call_globals, {"call_api_endpoint": transport}),
            mock.patch.object(risk_gate, "now_ts", return_value=1.0),
            mock.patch.object(
                risk_gate, "strip_risk_prefix",
                side_effect=lambda value: (value, None),
            ),
            mock.patch.object(
                risk_gate, "assign_tier", return_value={"risk_tier": "light"},
            ),
            mock.patch.object(risk_gate, "evaluate_hold", return_value=(None, None)),
            mock.patch.object(risk_gate, "record_route_observed"),
            mock.patch.object(tool_events, "set_turn_context"),
            mock.patch.object(tool_events, "update_turn_risk_tier"),
            mock.patch.object(
                oversight_events, "lifecycle_context_scope",
                return_value=mock.MagicMock(
                    __enter__=mock.Mock(return_value=None),
                    __exit__=mock.Mock(return_value=False),
                ),
            ),
        ):
            events = list(server._direct_stream(
                "Current question", [], panel_id="direct-target",
                extra_context=extra_context,
            ))
        self.assertEqual(len(captured), 1)
        joined = "\n".join(message["content"] for message in captured[0])
        self.assertEqual(joined.count("OPTIONAL REFERENCE DATA"), 1)
        self.assertEqual(joined.count("DIRECT UNIQUE EVIDENCE"), 1)
        payloads = [
            json.loads(event.removeprefix("data: ").strip()) for event in events
        ]
        coverage_events = [
            payload for payload in payloads
            if payload.get("type") == "pipeline_stage"
            and payload.get("stage") == "context_coverage"
        ]
        self.assertEqual(len(coverage_events), 1)
        coverage = coverage_events[0]["context_coverage"]
        self.assertEqual(coverage["physical_calls"], 1)
        self.assertEqual(coverage["lanes"]["contributor"]["selected_units"], 1)
        self.assertGreater(coverage["budget"]["capacity_tokens"], 0)
        serialized_events = "".join(events)
        self.assertNotIn(secret, serialized_events)
        for key in (
            "selected_unit_ids", "deferred_unit_ids", "source_coverage",
        ):
            self.assertNotIn(key, serialized_events)

    def test_more_than_twenty_contributor_refs_are_persisted(self):
        candidates = {}
        for index in range(25):
            source_id = f"source-{index}"
            runtime_memory.create_conversation_envelope(
                source_id,
                title=f"Source {index}",
                description=DESCRIPTION,
                sessions_root=self.sessions,
            )
            candidates[source_id] = {
                "kind": "conversation", "ref": source_id,
                "title": f"Source {index}",
            }
        reviewed = server._resolve_reviewed_contributors(
            {"candidates": candidates},
            [f"source-{index}" for index in range(25)],
            target_tag="",
        )
        self.assertEqual(len(reviewed), 25)
        runtime_memory.create_conversation_envelope(
            "many-contributors",
            title="Many contributors",
            description=DESCRIPTION,
            contributors=reviewed,
            sessions_root=self.sessions,
        )
        stored = runtime_memory.load_conversation_json(
            "many-contributors", sessions_root=self.sessions,
        )
        self.assertEqual(len(stored["contributors"]), 25)
        self.assertEqual(stored["contributors"][-1]["ref"], "source-24")
        runtime_bundle = server.build_contributor_bundle(
            "many-contributors", target_tag="",
        )
        self.assertEqual(len(runtime_bundle["sources"]), 25)
        self.assertEqual(len(runtime_bundle["units"]), 25)

    def test_dialogue_contributor_inherits_ancestry_at_fork_cutoff(self):
        runtime_memory.fork_conversation(
            "source-dialogue", "source-child",
            fork_point_turn_index=0,
            sessions_root=self.sessions,
        )
        runtime_memory.save_turn_spatial_state(
            "source-child", "Child question", "Child answer",
            sessions_root=self.sessions,
        )
        runtime_memory.save_turn_spatial_state(
            "source-dialogue", "Later parent secret", "Must not cross cutoff",
            sessions_root=self.sessions,
        )
        runtime_memory.create_conversation_envelope(
            "target-fork-contributor",
            title="Target",
            description=DESCRIPTION,
            contributors=[{
                "kind": "conversation", "ref": "source-child", "title": "Child",
            }],
            sessions_root=self.sessions,
        )
        bundle = server.build_contributor_bundle("target-fork-contributor")
        content = "\n".join(unit["content"] for unit in bundle["units"])
        self.assertIn("The receipt arrived late", content)
        self.assertIn("Child answer", content)
        self.assertNotIn("Later parent secret", content)
        self.assertEqual(
            set(bundle["exclude_conversation_ids"]),
            {"source-dialogue", "source-child"},
        )

    def test_stricter_dialogue_ancestor_is_withheld_at_every_selection_seam(self):
        runtime_memory.create_conversation_envelope(
            "private-parent",
            title="Private parent",
            description=DESCRIPTION,
            tag="private",
            sessions_root=self.sessions,
        )
        runtime_memory.save_turn_spatial_state(
            "private-parent", "Private premise", "Private conclusion",
            sessions_root=self.sessions,
        )
        runtime_memory.fork_conversation(
            "private-parent", "standard-child", creation_tag="",
            sessions_root=self.sessions,
        )
        row = self._source_row(
            conversation_id="standard-child", title="Standard child", tag="",
        )
        self.assertFalse(server._browser_creation_row_allowed(row, ""))
        self.assertTrue(server._browser_creation_row_allowed(row, "private"))

        review = {"candidates": {
            "standard-child": {
                "kind": "conversation", "ref": "standard-child",
                "title": "Standard child",
            },
        }}
        with self.assertRaises(ValueError):
            server._resolve_reviewed_contributors(
                review, ["standard-child"], target_tag="",
            )

        runtime_memory.create_conversation_envelope(
            "standard-target",
            title="Standard target",
            description=DESCRIPTION,
            contributors=[{
                "kind": "conversation", "ref": "standard-child",
                "title": "Standard child",
            }],
            sessions_root=self.sessions,
        )
        bundle = server.build_contributor_bundle(
            "standard-target", target_tag="",
        )
        self.assertEqual(bundle["sources"][0]["status"], "withheld")
        self.assertEqual(bundle["units"], [])
        self.assertEqual(
            set(bundle["exclude_conversation_ids"]),
            {"private-parent", "standard-child"},
        )

    def test_archive_mixed_privacy_uses_strictest_at_candidate_review_and_runtime(self):
        source_id = "archive-mixed-privacy-source"
        archive_ref = server._browser_encode_source_id("archive", source_id)
        chunks = [
            {
                "_row_id": 1, "conversation_id": source_id,
                "pair_num": 1, "tag": "", "conversation_title": "Public hit",
                "text": (
                    "---\ntype: chat\ntags: []\n---\n"
                    "## Exchange\n\n**User:**\n\nPublic prompt\n\n"
                    "**Assistant:**\n\nPublic response\n"
                ),
            },
            {
                "_row_id": 2, "conversation_id": source_id,
                "pair_num": 2, "tag": "", "conversation_title": "Stale standard",
                "text": (
                    "---\ntype: chat\ntags: [private]\n---\n"
                    "## Exchange\n\n**User:**\n\nPRIVATE ARCHIVE CONTENT\n\n"
                    "**Assistant:**\n\nPrivate response\n"
                ),
            },
        ]
        row = self._source_row(
            conversation_id=archive_ref,
            source_conversation_id=source_id,
            source_kind="archive",
            result_type="archive_conversation",
            tag="",
            title="PRIVATE ARCHIVE TITLE",
            snippet="PRIVATE ARCHIVE CONTENT",
        )
        patches = (
            mock.patch.object(
                server, "_browser_archive_chunk_metadata", return_value=chunks,
            ),
            mock.patch.object(
                server, "_browser_read_chunk_text",
                side_effect=lambda meta: meta["text"],
            ),
        )
        with patches[0], patches[1]:
            envelope = server._browser_archive_envelope(archive_ref)
            self.assertEqual(envelope["tag"], "private")
            self.assertFalse(server._browser_creation_row_allowed(row, ""))
            self.assertTrue(server._browser_creation_row_allowed(row, "private"))

            discovery = self._discover(rows=[row])
            serialized = json.dumps(discovery)
            self.assertEqual(discovery["rows"], [])
            self.assertNotIn("PRIVATE ARCHIVE TITLE", serialized)
            self.assertNotIn("PRIVATE ARCHIVE CONTENT", serialized)

            review = {"candidates": {
                archive_ref: {
                    "kind": "conversation", "ref": archive_ref,
                    "title": "PRIVATE ARCHIVE TITLE",
                },
            }}
            with self.assertRaises(ValueError):
                server._resolve_reviewed_contributors(
                    review, [archive_ref], target_tag="",
                )
            permitted = server._resolve_reviewed_contributors(
                review, [archive_ref], target_tag="private",
            )
            self.assertEqual(permitted[0]["ref"], archive_ref)

            runtime_memory.create_conversation_envelope(
                "standard-archive-target",
                title="Standard archive target",
                description=DESCRIPTION,
                contributors=[{
                    "kind": "conversation", "ref": archive_ref,
                    "title": "PRIVATE ARCHIVE TITLE",
                }],
                sessions_root=self.sessions,
            )
            standard_bundle = server.build_contributor_bundle(
                "standard-archive-target", target_tag="",
            )
            self.assertEqual(standard_bundle["sources"][0]["status"], "withheld")
            self.assertEqual(standard_bundle["units"], [])
            private_bundle = server.build_contributor_bundle(
                "standard-archive-target", target_tag="private",
            )
            self.assertEqual(private_bundle["sources"][0]["status"], "available")
            self.assertIn(
                "PRIVATE ARCHIVE CONTENT",
                "\n".join(unit["content"] for unit in private_bundle["units"]),
            )

    def test_atomic_privacy_matrix_applies_at_candidate_validation_and_runtime(self):
        matrix = {
            "": {"": True, "private": False, "stealth": False},
            "private": {"": True, "private": True, "stealth": False},
            "stealth": {"": True, "private": True, "stealth": True},
        }
        for target_tag, expectations in matrix.items():
            for source_tag, expected in expectations.items():
                tags = ["atomic"] + ([source_tag] if source_tag else [])
                with self.subTest(target=target_tag, source=source_tag):
                    self.assertEqual(
                        server._atomic_contributor_privacy_allows(tags, target_tag),
                        expected,
                    )

        private_note = self.vault / "Atomic — Private.md"
        private_note.write_text(
            "---\ntype: engram\ntags: [atomic, private]\n---\nPrivate fact.",
            encoding="utf-8",
        )
        encoded = server._browser_encode_source_id("engram", str(private_note))
        row = {
            "conversation_id": encoded,
            "source_kind": "engram",
            "tags": ["atomic", "private"],
            "title": "Private atomic",
        }
        self.assertFalse(server._browser_creation_row_allowed(row, ""))
        self.assertTrue(server._browser_creation_row_allowed(row, "private"))
        review = {
            "candidates": {
                encoded: {"kind": "atomic_note", "path": str(private_note),
                          "title": "Private atomic"},
            },
        }
        with self.assertRaises(ValueError):
            server._resolve_reviewed_contributors(
                review, [encoded], target_tag="",
            )
        self.assertEqual(
            server._resolve_reviewed_contributors(
                review, [encoded], target_tag="private",
            )[0]["path"],
            str(private_note.resolve()),
        )
        runtime_memory.create_conversation_envelope(
            "standard-runtime-target",
            title="Standard",
            description=DESCRIPTION,
            contributors=[{
                "kind": "atomic_note", "path": str(private_note),
                "title": "Private atomic",
            }],
            sessions_root=self.sessions,
        )
        runtime_bundle = server.build_contributor_bundle(
            "standard-runtime-target", target_tag="",
        )
        self.assertEqual(runtime_bundle["sources"][0]["status"], "withheld")
        self.assertEqual(runtime_bundle["units"], [])

    def test_creation_search_rejects_vague_descriptions(self):
        response = self.client.get(
            "/api/conversations/browser",
            query_string={"q": "cash flow", "purpose": "creation"},
        )
        self.assertEqual(response.status_code, 400)

    def test_canonical_guide_and_gate_records_match_shipped_controls(self):
        vault_ora = Path.home() / "Documents" / "vault" / "Projects" / "Ora"
        guide_raw = (vault_ora / "Guide — Using Ora.md").read_text(encoding="utf-8")
        guide_body = guide_raw.split("---", 2)[2].lstrip("\n")
        mirror = (REPO / "docs" / "user-guide.md").read_text(encoding="utf-8")
        self.assertEqual(guide_body, mirror)
        for token in (
            "Start a Dialogue without duplicating prior work",
            "Nothing is created at this point",
            "unsent draft",
            "one parent and many contributors",
            "Private material cannot contribute into a Standard Dialogue",
            "Archived Dialogues and atomic notes remain read-only",
        ):
            self.assertIn(token, guide_body)
        tracker = (vault_ora / "Working — Ora Setup and Refinement.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "implementation complete; pending Gate G1.4 judgment", tracker
        )


if __name__ == "__main__":
    unittest.main()
