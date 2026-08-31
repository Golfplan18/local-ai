from __future__ import annotations

import ast
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import pytest
import yaml

from orchestrator import conversation_closeout as closeout
from orchestrator import conversation_memory as memory
from orchestrator import export as output_export
from orchestrator import vault_export
from orchestrator.conversation_chunk import (
    attach_chunk_ownership,
    build_chroma_metadata,
    build_chunk_markdown,
)
from orchestrator.tools import daily_note, knowledge_index, knowledge_search
from orchestrator.tools import batch_processor
from orchestrator.tools.runtime_pipeline import RuntimePipeline, SessionData


REPO = Path(__file__).resolve().parents[2]


def _save(
    root: Path,
    conversation_id: str,
    user: str,
    assistant: str,
    *,
    tag: str,
    privacy: str,
    chunk_id: str,
    project_ids: list[str] | None = None,
) -> None:
    assert memory.save_turn_spatial_state(
        conversation_id,
        user,
        assistant,
        tag=tag,
        turn_privacy=privacy,
        chunk_id=chunk_id,
        project_ids=project_ids,
        sessions_root=root,
    )


def _current_output_export_identity(
    sessions_root: Path,
    conversation_id: str,
    displayed_turn_index: int = 0,
) -> dict[str, object]:
    effective = memory.resolve_effective_conversation_history(
        conversation_id, sessions_root=sessions_root,
    )
    owner = memory.displayed_exchange_owner(effective, displayed_turn_index)
    assert owner is not None
    return {
        "scope": "current_output",
        "conversation_id": conversation_id,
        "source_conversation_id": owner["conversation_id"],
        "source_turn_index": owner["turn_index"],
        "source_chunk_id": owner["chunk_id"],
        "turn_privacy": owner["turn_privacy"],
        "project": "commons",
    }


def test_mixed_dialogue_persists_exact_authority_and_composer_independently(tmp_path):
    _save(
        tmp_path, "mixed", "standard question", "standard answer",
        tag="", privacy="standard", chunk_id="chunk-standard",
        project_ids=["ora", "research"],
    )
    assert memory.set_conversation_tag(
        "mixed", "private", sessions_root=tmp_path,
    )
    _save(
        tmp_path, "mixed", "private question", "private answer",
        tag="private", privacy="private", chunk_id="chunk-private",
        project_ids=["ignored"],
    )

    envelope = memory.load_conversation_json("mixed", sessions_root=tmp_path)
    assert envelope["tag"] == "private"
    assert envelope["project_ids"] == ["ora", "research"]
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard", "private", "private",
    ]
    assert [m["content"] for m in memory.filter_conversation_history_for_tag(
        envelope["messages"], "",
    )] == ["standard question", "standard answer"]
    assert len(memory.filter_conversation_history_for_tag(
        envelope["messages"], "private",
    )) == 4

    # Composer mutation does not retag history; exact turn mutation does not
    # mutate the composer or project membership.
    assert memory.set_conversation_tag("mixed", "", sessions_root=tmp_path)
    changed = memory.set_conversation_turn_privacy(
        "mixed", 2, "standard", sessions_root=tmp_path,
    )
    assert changed["chunk_id"] == "chunk-private"
    envelope = memory.load_conversation_json("mixed", sessions_root=tmp_path)
    assert envelope["tag"] == ""
    assert envelope["project_ids"] == ["ora", "research"]
    assert {message["turn_privacy"] for message in envelope["messages"]} == {
        "standard",
    }


def test_unknown_conflicting_authority_is_not_guessed_or_consumed(tmp_path):
    assert memory.save_turn_spatial_state(
        "invalid", "u", "a", tag="", turn_privacy="not-a-value",
        sessions_root=tmp_path,
    ) is None
    assert memory.save_turn_spatial_state(
        "conflict", "u", "a", tag="", turn_privacy="stealth",
        sessions_root=tmp_path,
    ) is None

    history = [
        {"role": "user", "content": "safe", "turn_privacy": "standard"},
        {"role": "assistant", "content": "safe-a", "turn_privacy": "standard"},
        {"role": "user", "content": "unknown"},
        {"role": "assistant", "content": "unknown-a"},
        {"role": "user", "content": "conflict", "turn_privacy": "standard"},
        {"role": "assistant", "content": "conflict-a", "turn_privacy": "private"},
    ]
    assert [m["content"] for m in memory.filter_conversation_history_for_tag(
        history, "private",
    )] == ["safe", "safe-a"]

    pipeline = RuntimePipeline(config={}, call_fn=lambda *_args: "must not run")
    data = SessionData(
        session_id="refused", timestamp="2026-08-29T12:00:00",
        mode="standard", gear=1, conversation_id="mixed",
        conversation_tag="", turn_privacy="",
    )
    with mock.patch.object(pipeline, "_step1_session_log") as first_write:
        result = pipeline.run_sync(data)
    first_write.assert_not_called()
    assert result.steps_failed and result.steps_failed[0].startswith(
        "privacy_authority:"
    )
    pipeline._executor.shutdown(wait=True)


def test_clarification_resume_requires_and_preserves_paused_contract():
    from server import app as server_app

    pending = {
        "source": "manual_mode_selection",
        "config_name": None,
        "model_id": "paused-model",
        "conversation_tag": "",
        "turn_privacy": "standard",
    }
    contract = server_app._require_clarification_authority(pending)
    assert contract == {
        "config_name": None,
        "model_id": "paused-model",
        "conversation_tag": "",
        "turn_privacy": "standard",
    }
    server_app._pending_clarification["paused"] = pending
    try:
        assert server_app._manual_clarification_authority("paused") == contract
    finally:
        server_app._pending_clarification.pop("paused", None)

    for missing in contract:
        incomplete = dict(pending)
        incomplete.pop(missing)
        with pytest.raises(ValueError, match="Paused turn"):
            server_app._require_clarification_authority(incomplete)
    conflicting = {**pending, "turn_privacy": "private"}
    with pytest.raises(ValueError, match="conflicting"):
        server_app._require_clarification_authority(conflicting)

    with mock.patch.object(
        server_app, "_effective_conversation_tag", return_value="private",
    ):
        assert server_app._conversation_turn_tag(
            "paused", "", exact_tag=True,
        ) == ""


def test_fork_uses_truthful_effective_boundary_and_refuses_private_leak(tmp_path):
    _save(
        tmp_path, "parent", "s-user", "s-assistant", tag="",
        privacy="standard", chunk_id="s", project_ids=["ora"],
    )
    assert memory.set_conversation_tag("parent", "private", sessions_root=tmp_path)
    _save(
        tmp_path, "parent", "p-user", "p-assistant", tag="private",
        privacy="private", chunk_id="p",
    )

    standard_child = memory.fork_conversation(
        "parent", "standard-child", creation_tag="",
        fork_point_turn_index=0, sessions_root=tmp_path,
    )
    assert standard_child["project_ids"] == ["ora"]
    assert standard_child["fork_point_effective_message_count"] == 2
    assert standard_child["fork_point_chunk_id"] == "s"
    assert [m["content"] for m in memory.resolve_effective_conversation_history(
        "standard-child", sessions_root=tmp_path,
    )] == ["s-user", "s-assistant"]

    with pytest.raises(ValueError, match="chunk identity"):
        memory.fork_conversation(
            "parent", "wrong-chunk-child", creation_tag="",
            fork_point_turn_index=0, fork_point_chunk_id="p",
            sessions_root=tmp_path,
        )
    assert not (tmp_path / "wrong-chunk-child" / "conversation.json").exists()

    with pytest.raises(ValueError, match="privacy"):
        memory.fork_conversation(
            "parent", "unsafe-child", creation_tag="",
            fork_point_turn_index=1, sessions_root=tmp_path,
        )
    private_child = memory.fork_conversation(
        "parent", "private-child", creation_tag="private",
        fork_point_turn_index=1, sessions_root=tmp_path,
    )
    assert len(memory.resolve_effective_conversation_history(
        "private-child", sessions_root=tmp_path,
    )) == 4

    # A grandchild fork at an inherited displayed turn remains clipped to that
    # turn rather than accidentally inheriting its direct parent's full prefix.
    grandchild = memory.fork_conversation(
        "private-child", "grandchild", creation_tag="private",
        fork_point_turn_index=0, sessions_root=tmp_path,
    )
    assert grandchild["fork_point_effective_message_count"] == 2
    assert len(memory.resolve_effective_conversation_history(
        "grandchild", sessions_root=tmp_path,
    )) == 2


def test_fork_refuses_parent_with_incomplete_ancestry_before_persistence(
        tmp_path):
    _save(
        tmp_path, "ancestor", "ancestor user", "ancestor assistant",
        tag="", privacy="standard", chunk_id="ancestor-chunk",
    )
    assert memory.fork_conversation(
        "ancestor", "broken-parent", creation_tag="", sessions_root=tmp_path,
    )
    _save(
        tmp_path, "broken-parent", "local user", "local assistant",
        tag="", privacy="standard", chunk_id="local-chunk",
    )
    (tmp_path / "ancestor" / "conversation.json").unlink()

    diagnostics: list[str] = []
    degraded = memory.resolve_effective_conversation_history(
        "broken-parent", sessions_root=tmp_path, diagnostics=diagnostics,
    )
    assert [message["content"] for message in degraded] == [
        "local user", "local assistant",
    ]
    assert diagnostics

    with pytest.raises(ValueError, match="fork parent history is incomplete"):
        memory.fork_conversation(
            "broken-parent", "refused-child", creation_tag="",
            sessions_root=tmp_path,
        )
    assert not (tmp_path / "refused-child" / "conversation.json").exists()


def test_fork_refuses_every_incomplete_or_conflicting_prefix_shape(tmp_path):
    variants = (
        "orphan", "building", "unowned", "chunk-conflict",
        "privacy-conflict",
    )
    for label in variants:
        parent_id = f"{label}-parent"
        child_id = f"{label}-child"
        _save(
            tmp_path, parent_id, "safe user", "safe assistant",
            tag="", privacy="standard", chunk_id=f"{label}-chunk",
        )
        path = tmp_path / parent_id / "conversation.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        messages = envelope["messages"]
        if label == "orphan":
            messages.append({
                "role": "user", "content": "orphan",
                "turn_privacy": "standard", "chunk_id": "orphan-chunk",
            })
        elif label == "building":
            messages[1]["visual_outcome"] = {"state": "building"}
        elif label == "unowned":
            messages[0].pop("chunk_id", None)
            messages[1].pop("chunk_id", None)
        elif label == "chunk-conflict":
            messages[1]["chunk_id"] = "different-chunk"
        elif label == "privacy-conflict":
            messages[1]["turn_privacy"] = "private"
        path.write_text(json.dumps(envelope), encoding="utf-8")

        with pytest.raises(ValueError, match="incomplete|privacy"):
            memory.fork_conversation(
                parent_id, child_id, creation_tag="", sessions_root=tmp_path,
            )
        assert not (tmp_path / child_id / "conversation.json").exists()


def test_fork_summary_and_library_search_use_effective_history(tmp_path):
    _save(
        tmp_path, "search-parent", "public question",
        "inheritpublicneedle public answer",
        tag="", privacy="standard", chunk_id="public",
    )
    assert memory.set_conversation_tag(
        "search-parent", "private", sessions_root=tmp_path,
    )
    _save(
        tmp_path, "search-parent", "inheritprivatesecret", "private answer",
        tag="private", privacy="private", chunk_id="private",
    )
    parent_path = tmp_path / "search-parent" / "conversation.json"
    parent_envelope = json.loads(parent_path.read_text(encoding="utf-8"))
    parent_envelope["display_name"] = "private-derived Dialogue title"
    parent_envelope["description"] = "private-derived Dialogue description"
    parent_path.write_text(json.dumps(parent_envelope), encoding="utf-8")
    assert memory.fork_conversation(
        "search-parent", "search-child", creation_tag="private",
        fork_point_turn_index=1, sessions_root=tmp_path,
    )

    summaries = memory.iter_conversations(
        tmp_path, include_closed=True,
    )
    child = next(
        row for row in summaries
        if row["conversation_id"] == "search-child"
    )
    assert child["title"] == "public question (fork)"
    assert child["message_count"] == 4
    assert child["local_message_count"] == 0
    assert child["inherited_message_count"] == 4
    assert child["privacy_summary"] == "mixed"
    assert child["contains_private"] is True

    child_envelope = memory.load_conversation_json(
        "search-child", sessions_root=tmp_path,
    )
    assert child_envelope["display_name"] == "public question (fork)"
    assert child_envelope["description"] == ""
    assert child_envelope["fork_point_chunk_id"] == "private"
    effective_history = memory.resolve_effective_conversation_history(
        "search-child", sessions_root=tmp_path,
    )
    assert child_envelope["messages"] == []
    assert len(effective_history) == 4

    from server import app as server_app

    with (
        mock.patch.dict("sys.modules", {"conversation_memory": memory}),
        mock.patch.object(
            memory, "iter_conversations", return_value=[child],
        ),
        mock.patch.object(
            memory, "load_conversation_json", return_value=child_envelope,
        ),
        mock.patch.object(
            memory, "resolve_effective_conversation_history",
            return_value=effective_history,
        ),
    ):
        public_rows = server_app._browser_live_rows(
            "inheritpublicneedle", target_tag="",
        )
        hidden_private_rows = server_app._browser_live_rows(
            "inheritprivatesecret", target_tag="",
        )
        private_rows = server_app._browser_live_rows(
            "inheritprivatesecret", target_tag="private",
        )

    assert [row["conversation_id"] for row in public_rows] == ["search-child"]
    assert public_rows[0]["matched_turn_privacy"] == "standard"
    assert hidden_private_rows == []
    assert [row["conversation_id"] for row in private_rows] == ["search-child"]
    assert private_rows[0]["matched_turn_privacy"] == "private"


def test_archived_related_uses_supported_filter_contract():
    from server import app as server_app

    with (
        mock.patch.object(
            server_app, "_valid_existing_conversation_id", return_value=True,
        ),
        mock.patch.object(
            server_app, "_browser_archive_related_rows", return_value=[],
        ) as related_rows,
    ):
        response = server_app.app.test_client().get(
            "/api/conversation/archive:source/related?target_tag=private",
        )

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["rows"] == []
    related_rows.assert_called_once_with(
        "archive:source",
        required_tags=[],
        show_archived=False,
        target_tag="private",
    )


def test_chunk_search_and_daily_note_use_exact_pre_score_authority(tmp_path):
    when = datetime(2026, 8, 29, 10, 0)
    metadata = build_chroma_metadata(
        "u", "a", conversation_id="mixed", session_id="session",
        pair_num=1, model_id="local", raw_path="/tmp/raw",
        chunk_path="/tmp/chunk", when=when, first_user_input="u",
        topic_primary="topic", topics=[], turn_summary="summary",
        thread_id="thread", turn_privacy="standard",
    )
    assert metadata["turn_privacy"] == "standard"
    assert knowledge_search._build_where_clause(
        "conversations", None, False, False, privacy_tag="",
    ) == {"turn_privacy": {"$eq": "standard"}}
    assert knowledge_search._build_where_clause(
        "conversations", None, False, False, privacy_tag="private",
    ) == {"turn_privacy": {"$in": ["standard", "private"]}}
    assert not knowledge_search._metadata_passes_filters(
        {"conversation_id": "legacy"}, collection="conversations",
        type_filter=None, include_private=True, include_archived=False,
        privacy_tag="private",
    )

    chunks = tmp_path / "chunks"
    sessions = tmp_path / "sessions"
    chunks.mkdir()
    (sessions / "mixed").mkdir(parents=True)
    (sessions / "mixed" / "conversation.json").write_text(
        json.dumps({"display_name": "Mixed Dialogue"}), encoding="utf-8",
    )
    for minute, privacy in ((0, "standard"), (1, "private"), (2, None)):
        markdown = build_chunk_markdown(
            f"u-{minute}", f"a-{minute}", "context", when=when,
            tag="private" if privacy == "private" else "",
            turn_privacy=privacy,
        )
        markdown = attach_chunk_ownership(
            markdown, conversation_id="mixed", chunk_id=f"chunk-{minute}",
        )
        (chunks / f"2026-08-29_10-{minute:02d}_chunk-{minute}.md").write_text(
            markdown, encoding="utf-8",
        )
    with (
        mock.patch.object(daily_note, "CONVERSATIONS_DIR", str(chunks)),
        mock.patch.object(daily_note, "SESSIONS_DIR", str(sessions)),
    ):
        public = daily_note.collect_conversations("2026-08-29")
        private = daily_note.collect_conversations(
            "2026-08-29", include_private=True,
        )
    assert public == [{
        "id": "mixed", "exchanges": 1, "first": "10:00", "last": "10:00",
        "gist": "", "name": "u-0",
    }]
    assert private[0]["exchanges"] == 2
    assert private[0]["name"] == "Mixed Dialogue"


def test_library_search_filters_exact_authority_before_every_score(
        monkeypatch, tmp_path):
    from server import app as server_app

    class BombText(str):
        def lower(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible conversation text was lexically scored")

    metadata = {
        1: {
            "conversation_id": "mixed", "turn_privacy": "private",
            "conversation_title": BombText("private title"),
            "chroma:document": BombText(
                "## Exchange\n\n**User:**\n\nprivate needleword\n\n"
                "**Assistant:**\n\nprivate answer"
            ), "pair_num": 2,
        },
        2: {
            "conversation_id": "mixed", "turn_privacy": "standard",
            "conversation_title": BombText("private-derived title"),
            "chroma:document": (
                "## Context\n\nprivate-derived title\n\n## Exchange\n\n"
                "**User:**\n\npublic needleword\n\n"
                "**Assistant:**\n\npublic answer"
            ), "pair_num": 1,
        },
        3: {
            "conversation_id": "legacy",
            "chroma:document": BombText(
                "## Exchange\n\n**User:**\n\nunknown needleword\n\n"
                "**Assistant:**\n\nunknown answer"
            ), "pair_num": 1,
        },
    }
    statements: list[tuple[str, tuple]] = []

    class Cursor:
        def __init__(self):
            self.result = []

        def execute(self, sql, params=()):
            statements.append((sql, tuple(params)))
            if "FROM embedding_fulltext_search" in sql:
                self.result = [
                    (1, "private-row", metadata[1]["chroma:document"], 0.1),
                    (3, "unknown-row", metadata[3]["chroma:document"], 0.2),
                    (2, "standard-row", metadata[2]["chroma:document"], 0.3),
                ]
            elif "FROM embedding_metadata" in sql and "WHERE id = ?" in sql:
                values = []
                for key, value in metadata[int(params[0])].items():
                    if isinstance(value, bool):
                        values.append((key, None, None, None, value))
                    elif isinstance(value, int):
                        values.append((key, None, value, None, None))
                    else:
                        values.append((key, value, None, None, None))
                self.result = values
            else:  # pragma: no cover - protects the fake's contract
                raise AssertionError(sql)
            return self

        def fetchall(self):
            return self.result

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    monkeypatch.setattr("sqlite3.connect", lambda *_args, **_kwargs: Connection())
    exact = server_app._browser_chroma_exact_rows(
        "needleword", logical_collection="conversations", limit=20,
        target_tag="",
    )
    fuzzy = server_app._browser_chroma_fuzzy_rows(
        "needleword", logical_collection="conversations", limit=20,
        target_tag="",
    )
    assert [row["turn_privacy"] for row in exact] == ["standard"]
    assert [row["turn_privacy"] for row in fuzzy] == ["standard"]
    assert exact[0]["title"] == "public needleword"
    assert "private-derived title" not in exact[0]["snippet"]
    scored_sql = [sql for sql, _params in statements if "embedding_fulltext_search" in sql]
    assert scored_sql
    assert all("turn_authority" in sql and "turn_privacy" in sql for sql in scored_sql)
    assert all("standard" in params for sql, params in statements if sql in scored_sql)

    class BombDistance:
        def __float__(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible conversation vector was scored")

    class SemanticCollection:
        def __init__(self):
            self.query_kwargs = None

        def count(self):
            return 3

        def query(self, **kwargs):
            self.query_kwargs = kwargs
            # Deliberately violate the requested where filter. The local
            # backstop must still reject authority before reading distance.
            return {
                "ids": [["private-row", "unknown-row", "standard-row"]],
                "documents": [[
                    metadata[1]["chroma:document"],
                    metadata[3]["chroma:document"],
                    metadata[2]["chroma:document"],
                ]],
                "metadatas": [[metadata[1], metadata[3], metadata[2]]],
                "distances": [[BombDistance(), BombDistance(), 0.2]],
            }

    semantic_collection = SemanticCollection()
    fake_chromadb = mock.Mock()
    fake_chromadb.PersistentClient.return_value = object()
    with (
        mock.patch.dict("sys.modules", {"chromadb": fake_chromadb}),
        mock.patch(
            "orchestrator.embedding.get_collection",
            return_value=semantic_collection,
        ),
    ):
        semantic = server_app._browser_chroma_semantic_rows(
            "needleword", logical_collection="conversations", limit=20,
            target_tag="",
        )
    assert semantic_collection.query_kwargs["where"] == {
        "turn_privacy": {"$eq": "standard"},
    }
    assert [row["turn_privacy"] for row in semantic] == ["standard"]

    sqlite_path = tmp_path / "chroma.sqlite3"
    sqlite_path.write_text("", encoding="utf-8")
    candidate_statements: list[tuple[str, tuple]] = []

    class CandidateCursor:
        def __init__(self):
            self.result = []

        def execute(self, sql, params=()):
            candidate_statements.append((sql, tuple(params)))
            if "FROM collections c" in sql:
                self.result = [("segment",)]
            else:
                self.result = [("standard-row",)]
            return self

        def fetchone(self):
            return self.result[0] if self.result else None

        def fetchall(self):
            return self.result

    class CandidateConnection:
        def cursor(self):
            return CandidateCursor()

        def close(self):
            return None

    monkeypatch.setattr(knowledge_search, "_sqlite_path", lambda: str(sqlite_path))
    monkeypatch.setattr(
        knowledge_search.sqlite3,
        "connect",
        lambda *_args, **_kwargs: CandidateConnection(),
    )
    assert knowledge_search._sqlite_candidate_ids(
        "conversations", "needleword", ["needleword"], limit=20,
        allowed_turn_privacies=("standard",),
    ) == ["standard-row"]
    candidate_queries = [
        (sql, params) for sql, params in candidate_statements
        if "FROM collections c" not in sql
    ]
    assert candidate_queries
    assert all("turn_authority" in sql for sql, _params in candidate_queries)
    assert all("standard" in params for _sql, params in candidate_queries)
    for sql, params in candidate_queries:
        if "JOIN embedding_metadata m" not in sql:
            continue
        assert not {
            "conversation_title", "raw_path", "source_file",
            "source_document", "source_path",
        }.intersection(params)

    searchable, _mapping = server_app._browser_searchable_conversation({
        "display_name": "private-derived title",
        "description": "private-derived secretword description",
        "messages": [
            {"role": "user", "content": "public needleword", "turn_privacy": "standard"},
            {"role": "assistant", "content": "public answer", "turn_privacy": "standard"},
            {"role": "user", "content": "private secretword", "turn_privacy": "private"},
            {"role": "assistant", "content": "private answer", "turn_privacy": "private"},
            {"role": "user", "content": "unknown secretword"},
            {"role": "assistant", "content": "unknown answer"},
        ],
    }, "")
    assert searchable["display_name"] == "public needleword"
    assert searchable["description"] == ""
    assert server_app._conversation_search_snippet(
        searchable, "secretword",
    )["score"] == 0
    assert server_app._conversation_search_snippet(
        searchable, "needleword",
    )["score"] > 0

    summaries = [
        {
            "conversation_id": "mixed-live",
            "title": "private-derived title",
            "description": "private-derived description",
            "last_error_summary": "private-derived failure detail",
            "contributors": [{"title": "private-derived contributor"}],
            "contains_private": True,
            "has_unknown_turn_privacy": False,
            "tag": "private",
        },
        {
            "conversation_id": "private-only",
            "parent_conversation_id": "mixed-live",
            "title": "private-only title",
            "description": "private-only description",
            "contains_private": True,
            "has_unknown_turn_privacy": False,
            "tag": "private",
        },
        {
            "conversation_id": "unknown-only",
            "parent_conversation_id": "mixed-live",
            "title": "unknown title",
            "description": "unknown description",
            "contains_private": False,
            "has_unknown_turn_privacy": True,
            "tag": "",
        },
        {
            "conversation_id": "standard-child",
            "parent_conversation_id": "mixed-live",
            "title": "private-derived child title",
            "description": "private-derived child description",
            "contains_private": False,
            "has_unknown_turn_privacy": False,
            "tag": "",
        },
    ]
    effective = {
        "mixed-live": [
            {"role": "user", "content": "standard safe title", "turn_privacy": "standard"},
            {"role": "assistant", "content": "standard safe answer", "turn_privacy": "standard"},
            {"role": "user", "content": "private-derived title", "turn_privacy": "private"},
            {"role": "assistant", "content": "private answer", "turn_privacy": "private"},
        ],
        "private-only": [
            {"role": "user", "content": "private-only title", "turn_privacy": "private"},
            {"role": "assistant", "content": "private-only answer", "turn_privacy": "private"},
        ],
        "unknown-only": [
            {"role": "user", "content": "unknown title"},
            {"role": "assistant", "content": "unknown answer"},
        ],
        "standard-child": [
            {"role": "user", "content": "standard child title", "turn_privacy": "standard"},
            {"role": "assistant", "content": "standard child answer", "turn_privacy": "standard"},
        ],
    }
    envelopes = {
        cid: {
            "conversation_id": cid,
            "display_name": row["title"],
            "description": row["description"],
            "messages": messages,
        }
        for row in summaries
        for cid, messages in [(row["conversation_id"], effective[row["conversation_id"]])]
    }
    with (
        mock.patch.dict("sys.modules", {"conversation_memory": memory}),
        mock.patch.object(memory, "iter_conversations", return_value=summaries),
        mock.patch.object(
            memory, "load_conversation_json",
            side_effect=lambda cid: envelopes[cid],
        ),
        mock.patch.object(
            memory, "resolve_effective_conversation_history",
            side_effect=lambda cid: effective[cid],
        ),
    ):
        standard_rows = server_app._browser_live_rows("", target_tag="")
        hidden_title_rows = server_app._browser_live_rows(
            "private-derived", target_tag="",
        )
        with mock.patch.object(
            server_app, "_valid_existing_conversation_id", return_value=True,
        ):
            related_response = server_app.app.test_client().get(
                "/api/conversation/mixed-live/related?engrams=false"
            )
    assert [row["conversation_id"] for row in standard_rows] == [
        "mixed-live", "standard-child",
    ]
    assert standard_rows[0]["title"] == "standard safe title"
    assert standard_rows[0]["description"] == ""
    assert standard_rows[0]["contains_private"] is True
    assert "contains-private" in standard_rows[0]["tags"]
    assert "last_error_summary" not in standard_rows[0]
    assert "contributors" not in standard_rows[0]
    assert hidden_title_rows == []
    assert related_response.status_code == 200
    related_rows = json.loads(related_response.get_data(as_text=True))["rows"]
    assert [row["conversation_id"] for row in related_rows] == [
        "mixed-live", "standard-child",
    ]
    assert related_rows[0]["relation"] == "self"
    assert related_rows[0]["title"] == "standard safe title"
    assert related_rows[0]["description"] == ""
    assert related_rows[0]["contains_private"] is True
    assert "private-derived" not in json.dumps(related_rows)

    private_candidate = {
        "source_kind": "archive",
        "conversation_id": "archive:mixed",
        "matched_chunk_id": "private-row",
        "turn_privacy": "private",
    }
    with mock.patch.object(
        server_app, "_browser_archive_envelope",
        side_effect=AssertionError("private candidate text was loaded"),
    ):
        assert not server_app._browser_creation_row_allowed(
            private_candidate, "",
        )


def test_library_knowledge_paths_authenticate_owner_before_every_score(
        monkeypatch, tmp_path):
    from server import app as server_app

    class BombText(str):
        def lower(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible knowledge text was lexically scored")

    class BombRank:
        def __float__(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible knowledge FTS rank was consumed")

    def derivative(
        path: str,
        privacy: str | None,
        document: str,
        *,
        private: bool = False,
    ) -> dict:
        metadata = {
            "type": "engram",
            "artifact_kind": "conversation_runtime_derivative",
            "managed_by": "ora",
            "source_file": f"{path}.source",
            "source_chunk_id": f"{path}-chunk",
            "source_turn_index": 1,
            "tag_private": private,
            "tag_stealth": False,
            "path": path,
            "title": os.path.basename(path),
            "chroma:document": document,
        }
        if privacy is not None:
            metadata["turn_privacy"] = privacy
        return metadata

    records = {
        1: derivative(
            "/vault/private.md", "private",
            BombText("private needleword knowledge"), private=True,
        ),
        2: derivative(
            "/vault/unknown.md", None,
            BombText("unknown needleword knowledge"),
        ),
        3: {
            "type": "resource",
            "path": "/vault/public-note.md",
            "title": "public-note",
            "tag_private": False,
            "tag_stealth": False,
            "chroma:document": "ordinary public needleword knowledge",
        },
        4: derivative(
            "/vault/standard.md", "standard",
            "standard derivative needleword knowledge",
        ),
        5: {
            "type": "resource",
            "path": "/vault/private-sector.md",
            "title": "private-sector",
            "tags": '["private-sector"]',
            "tag_private": False,
            "tag_stealth": False,
            "chroma:document": "ordinary policy needleword knowledge",
        },
        6: {
            "type": "resource",
            "path": "/vault/conflicted.md",
            "source_chunk_id": "orphan-owner-claim",
            "tag_private": False,
            "tag_stealth": False,
            "chroma:document": BombText(
                "malformed derivative needleword knowledge"
            ),
        },
        7: {
            "type": "resource",
            "path": "/vault/conflicted.md",
            "tag_private": False,
            "tag_stealth": False,
            "chroma:document": BombText(
                "ordinary sibling on malformed path needleword knowledge"
            ),
        },
    }

    statements: list[tuple[str, tuple]] = []
    admitted_batches: list[tuple[tuple[str, ...], ...]] = []
    search_events: list[str] = []

    class AuthorityCollection:
        def __init__(self):
            self.calls: list[dict] = []

        def get(self, **kwargs):
            search_events.append("inventory")
            self.calls.append(kwargs)
            return {
                "ids": [f"row-{index}" for index in records],
                "metadatas": list(records.values()),
            }

    indexed = knowledge_index._compose_chroma_metadata(
        str(tmp_path / "derived.md"), {
            "type": "engram",
            "artifact_kind": "conversation_runtime_derivative",
            "managed_by": "ora",
            "source_file": "source-dialogue",
            "source_chunk_id": "source-chunk",
            "source_turn_index": 7,
            "turn_privacy": "standard",
        },
    )
    assert {
        key: indexed[key]
        for key in (
            "artifact_kind", "managed_by", "source_file",
            "source_chunk_id", "source_turn_index", "turn_privacy",
        )
    } == {
        "artifact_kind": "conversation_runtime_derivative",
        "managed_by": "ora",
        "source_file": "source-dialogue",
        "source_chunk_id": "source-chunk",
        "source_turn_index": 7,
        "turn_privacy": "standard",
    }

    class Cursor:
        def __init__(self):
            self.result = []

        def execute(self, sql, params=()):
            statements.append((sql, tuple(params)))
            if "CREATE TEMP TABLE" in sql:
                self.result = []
            elif "FROM embedding_fulltext_search" in sql:
                search_events.append("fts")
                self.result = [
                    (1, "private-row", records[1]["chroma:document"], BombRank()),
                    (2, "unknown-row", records[2]["chroma:document"], BombRank()),
                    (6, "orphan-claim-row", records[6]["chroma:document"], BombRank()),
                    (7, "conflicted-ordinary-row", records[7]["chroma:document"], BombRank()),
                    (3, "public-row", records[3]["chroma:document"], 0.2),
                    (4, "standard-row", records[4]["chroma:document"], 0.3),
                    (5, "private-sector-row", records[5]["chroma:document"], 0.4),
                ]
            elif "FROM embedding_metadata" in sql and "WHERE id = ?" in sql:
                values = []
                for key, value in records[int(params[0])].items():
                    if isinstance(value, bool):
                        values.append((key, None, None, None, value))
                    elif isinstance(value, int):
                        values.append((key, None, value, None, None))
                    else:
                        values.append((key, value, None, None, None))
                self.result = values
            else:  # pragma: no cover - protects the fake's contract
                raise AssertionError(sql)
            return self

        def executemany(self, sql, params):
            batch = tuple(tuple(value) for value in params)
            statements.append((sql, batch))
            admitted_batches.append(batch)
            self.result = []
            return self

        def fetchall(self):
            return self.result

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            return None

    authority_collection = AuthorityCollection()
    fts_chromadb = mock.Mock()
    fts_chromadb.PersistentClient.return_value = object()
    monkeypatch.setattr("sqlite3.connect", lambda *_args, **_kwargs: Connection())
    with (
        mock.patch.dict("sys.modules", {"chromadb": fts_chromadb}),
        mock.patch(
            "orchestrator.embedding.get_collection",
            return_value=authority_collection,
        ),
    ):
        exact = server_app._browser_chroma_exact_rows(
            "needleword", logical_collection="knowledge", limit=20,
            target_tag="",
        )
        fuzzy = server_app._browser_chroma_fuzzy_rows(
            "needleword", logical_collection="knowledge", limit=20,
            target_tag="",
        )
    assert {row["path"] for row in exact} == {
        "/vault/public-note.md", "/vault/standard.md",
        "/vault/private-sector.md",
    }
    assert {row["path"] for row in fuzzy} == {
        "/vault/public-note.md", "/vault/standard.md",
        "/vault/private-sector.md",
    }
    scoring_sql = [
        (sql, params) for sql, params in statements
        if "FROM embedding_fulltext_search" in sql
    ]
    assert scoring_sql
    assert all(
        "ora_browser_admitted_knowledge_paths" in sql
        and "knowledge_path" in sql
        for sql, _params in scoring_sql
    )
    expected_admitted = {
        ("/vault/private-sector.md",),
        ("/vault/public-note.md",),
        ("/vault/standard.md",),
    }
    assert admitted_batches == [
        tuple(sorted(expected_admitted)), tuple(sorted(expected_admitted)),
    ]
    assert authority_collection.calls == [
        {"include": ["metadatas"]}, {"include": ["metadatas"]},
    ]
    assert search_events[0] == "inventory"
    second_inventory = search_events.index("inventory", 1)
    assert "fts" in search_events[1:second_inventory]
    assert "fts" in search_events[second_inventory + 1:]

    class BombDistance:
        def __float__(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible knowledge vector was scored")

    class SemanticCollection:
        def __init__(self):
            self.get_kwargs = None
            self.query_kwargs: list[dict] = []

        def count(self):
            return 7

        def get(self, **kwargs):
            self.get_kwargs = kwargs
            return {
                "ids": [f"row-{index}" for index in records],
                "metadatas": list(records.values()),
            }

        def query(self, **kwargs):
            self.query_kwargs.append(kwargs)
            # Deliberately violate every requested scope. The exact row
            # backstop must still reject authority before distance conversion.
            return {
                "ids": [[
                    "private-row", "unknown-row", "public-row", "standard-row",
                    "private-sector-row", "orphan-claim-row",
                    "conflicted-ordinary-row",
                ]],
                "documents": [[
                    records[1]["chroma:document"],
                    records[2]["chroma:document"],
                    records[3]["chroma:document"],
                    records[4]["chroma:document"],
                    records[5]["chroma:document"],
                    records[6]["chroma:document"],
                    records[7]["chroma:document"],
                ]],
                "metadatas": [[
                    records[1], records[2], records[3], records[4], records[5],
                    records[6], records[7],
                ]],
                "distances": [[
                    BombDistance(), BombDistance(), 0.2, 0.3, 0.4,
                    BombDistance(), BombDistance(),
                ]],
            }

    semantic_collection = SemanticCollection()
    fake_chromadb = mock.Mock()
    fake_chromadb.PersistentClient.return_value = object()
    with (
        mock.patch.dict("sys.modules", {"chromadb": fake_chromadb}),
        mock.patch(
            "orchestrator.embedding.get_collection",
            return_value=semantic_collection,
        ),
    ):
        semantic = server_app._browser_chroma_semantic_rows(
            "needleword", logical_collection="knowledge", limit=20,
            target_tag="",
        )
    assert semantic_collection.get_kwargs["include"] == ["metadatas"]
    assert "where" not in semantic_collection.get_kwargs
    assert len(semantic_collection.query_kwargs) == 1
    assert semantic_collection.query_kwargs[0]["where"] == {
        "path": {"$in": [
            "/vault/private-sector.md",
            "/vault/public-note.md",
            "/vault/standard.md",
        ]},
    }
    assert {row["path"] for row in semantic} == {
        "/vault/public-note.md", "/vault/standard.md",
        "/vault/private-sector.md",
    }

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "needleword-private.md").write_text(
        "---\ntype: resource\ntags: [private]\n---\nprivate needleword body",
        encoding="utf-8",
    )
    (vault_root / "needleword-unknown.md").write_text(
        "---\n"
        "type: engram\n"
        "artifact_kind: conversation_runtime_derivative\n"
        "managed_by: ora\n"
        "source_file: source-dialogue\n"
        "source_chunk_id: unknown-chunk\n"
        "source_turn_index: 1\n"
        "---\nunknown needleword body",
        encoding="utf-8",
    )
    (vault_root / "needleword-public.md").write_text(
        "---\ntype: resource\ntags: [atomic]\n---\npublic needleword body",
        encoding="utf-8",
    )
    (vault_root / "needleword-standard.md").write_text(
        "---\n"
        "type: engram\n"
        "tags: [atomic]\n"
        "artifact_kind: conversation_runtime_derivative\n"
        "managed_by: ora\n"
        "source_file: source-dialogue\n"
        "source_chunk_id: standard-chunk\n"
        "source_turn_index: 1\n"
        "turn_privacy: standard\n"
        "---\nstandard needleword body",
        encoding="utf-8",
    )
    with (
        mock.patch.object(
            server_app, "_browser_chroma_exact_rows",
            side_effect=AssertionError("ineligible Engram body drove FTS"),
        ),
        mock.patch.object(
            server_app, "_browser_chroma_semantic_rows",
            side_effect=AssertionError("ineligible Engram body drove vectors"),
        ),
    ):
        for filename in ("needleword-private.md", "needleword-unknown.md"):
            ref = server_app._browser_encode_source_id(
                "engram", str(vault_root / filename),
            )
            assert server_app._browser_engram_related_rows(
                ref, target_tag="",
            ) == []

    original_match_score = server_app._browser_match_score

    def guarded_match_score(query, title="", text=""):
        candidate = f"{title}\n{text}".lower()
        assert "private" not in candidate
        assert "unknown" not in candidate
        return original_match_score(query, title, text)

    with mock.patch.object(
        server_app, "_browser_match_score", side_effect=guarded_match_score,
    ):
        vault_rows = server_app._browser_vault_markdown_rows(
            "needleword", vault_root=str(vault_root), target_tag="",
        )
    assert {Path(row["path"]).name for row in vault_rows} == {
        "needleword-public.md", "needleword-standard.md",
    }

    final_rows = server_app._browser_filter_rows(
        [{
            "conversation_id": "engram:private",
            "source_kind": "engram",
            **records[1],
        }],
        include_conversations=True,
        include_engrams=True,
        target_tag="",
        min_relevance=0,
        has_query=False,
    )
    assert final_rows == []


def test_direct_knowledge_consumers_share_complete_owner_path_gate(
        monkeypatch, tmp_path):
    from server import app as server_app

    class BombText(str):
        def lower(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible knowledge text was scored")

    class BombDistance:
        def __float__(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible knowledge distance was consumed")

    def derivative(path, privacy, secret, *, private=False, stealth=False):
        metadata = {
            "type": "engram",
            "path": path,
            "artifact_kind": "conversation_runtime_derivative",
            "managed_by": "ora",
            "source_file": f"{path}.source",
            "source_chunk_id": f"{path}.chunk",
            "source_turn_index": 1,
            "tag_private": private,
            "tag_stealth": stealth,
            "title": os.path.basename(path),
        }
        if privacy is not None:
            metadata["turn_privacy"] = privacy
        return {"metadata": metadata, "document": secret}

    rows = {
        "public": {
            "metadata": {
                "type": "resource", "path": "/vault/public.md",
                "tag_private": False, "tag_stealth": False,
                "title": "public",
            },
            "document": "public needleword body",
        },
        "standard": derivative(
            "/vault/standard.md", "standard",
            "standard derivative needleword body",
        ),
        "private": derivative(
            "/vault/private.md", "private",
            BombText("private-secret needleword body"), private=True,
        ),
        "stealth": derivative(
            "/vault/stealth.md", "stealth",
            BombText("stealth-secret needleword body"), stealth=True,
        ),
        "unknown": derivative(
            "/vault/unknown.md", None,
            BombText("unknown-secret needleword body"),
        ),
        "orphan": {
            "metadata": {
                "type": "resource", "path": "/vault/conflicted.md",
                "source_chunk_id": "orphan-owner-claim",
                "tag_private": False, "tag_stealth": False,
            },
            "document": BombText("orphan-secret needleword body"),
        },
        "conflicted-ordinary": {
            "metadata": {
                "type": "resource", "path": "/vault/conflicted.md",
                "tag_private": False, "tag_stealth": False,
            },
            "document": BombText("sibling-secret needleword body"),
        },
    }

    assert memory.knowledge_admitted_paths(
        [row["metadata"] for row in rows.values()], "",
    ) == ["/vault/public.md", "/vault/standard.md"]

    class KnowledgeCollection:
        name = "knowledge"

        def __init__(self):
            self.query_kwargs = []
            self.get_kwargs = []

        def count(self):
            return len(rows)

        def get(self, *, ids=None, **kwargs):
            self.get_kwargs.append({"ids": ids, **kwargs})
            selected_ids = list(rows) if ids is None else [
                str(row_id) for row_id in ids if str(row_id) in rows
            ]
            return {
                "ids": selected_ids,
                "documents": [rows[row_id]["document"] for row_id in selected_ids],
                "metadatas": [rows[row_id]["metadata"] for row_id in selected_ids],
            }

        def query(self, **kwargs):
            self.query_kwargs.append(kwargs)
            selected_ids = list(rows)
            return {
                "ids": [selected_ids],
                "documents": [[rows[row_id]["document"] for row_id in selected_ids]],
                "metadatas": [[rows[row_id]["metadata"] for row_id in selected_ids]],
                "distances": [[
                    0.2 if row_id == "public"
                    else 0.3 if row_id == "standard"
                    else BombDistance()
                    for row_id in selected_ids
                ]],
            }

    collection = KnowledgeCollection()
    fake_chromadb = mock.Mock()
    fake_chromadb.PersistentClient.return_value = object()
    with (
        mock.patch.dict("sys.modules", {"chromadb": fake_chromadb}),
        mock.patch(
            "orchestrator.embedding.get_or_create_collection",
            return_value=collection,
        ),
    ):
        semantic = knowledge_search.knowledge_search_raw(
            "needleword", collection="knowledge", n_results=20,
            privacy_tag="",
        )
        candidate_call = {}

        def candidate_ids(*_args, **kwargs):
            candidate_call.update(kwargs)
            return list(rows)

        with mock.patch.object(
            knowledge_search, "_sqlite_candidate_ids",
            side_effect=candidate_ids,
        ):
            lexical = knowledge_search.lexical_search_raw(
                "needleword", collection="knowledge", n_results=20,
                privacy_tag="",
            )

    assert [row["id"] for row in semantic] == ["public", "standard"]
    assert [row["id"] for row in lexical] == ["public", "standard"]
    assert candidate_call["allowed_knowledge_paths"] == (
        "/vault/public.md", "/vault/standard.md",
    )
    vector_path_clauses = [
        clause
        for clause in collection.query_kwargs[0]["where"]["$and"]
        if "path" in clause
    ]
    assert vector_path_clauses == [{
        "path": {"$in": ["/vault/public.md", "/vault/standard.md"]},
    }]
    inventory_calls = [
        call for call in collection.get_kwargs
        if call.get("include") == ["metadatas"] and call.get("ids") is None
    ]
    assert inventory_calls
    assert all("where" not in call for call in inventory_calls)

    def server_collection(_client, logical):
        if logical == "knowledge":
            return collection
        raise RuntimeError("conversation collection intentionally absent")

    with (
        mock.patch.dict("sys.modules", {"chromadb": fake_chromadb}),
        mock.patch(
            "orchestrator.embedding.get_collection",
            side_effect=server_collection,
        ),
        mock.patch.object(
            server_app, "load_config",
            return_value={"chromadb_path": str(tmp_path / "chroma")},
        ),
        mock.patch.object(server_app, "get_slot_endpoint", return_value=None),
    ):
        client = server_app.app.test_client()
        bootstrap_response = client.post(
            "/api/bootstrap", json={"topic": "needleword", "tag": ""},
        )
        vault_response = client.get("/api/vault-search?q=needleword")

    assert bootstrap_response.status_code == 200
    bootstrap = json.loads(bootstrap_response.get_data(as_text=True))
    assert bootstrap["match_count"] == 2
    assert [source["metadata"]["path"] for source in bootstrap["sources_used"]] == [
        "/vault/public.md", "/vault/standard.md",
    ]
    assert all(secret not in bootstrap["summary"] for secret in (
        "private-secret", "stealth-secret", "unknown-secret",
        "orphan-secret", "sibling-secret",
    ))
    assert vault_response.status_code == 200
    vault = json.loads(vault_response.get_data(as_text=True))["results"]
    assert [row["metadata"]["path"] for row in vault] == [
        "/vault/public.md", "/vault/standard.md",
    ]
    assert all(call["where"] == {
        "path": {"$in": ["/vault/public.md", "/vault/standard.md"]},
    } for call in collection.query_kwargs[-2:])

    selected_path = tmp_path / "selected.md"

    class SelectedCollection:
        def __init__(self):
            self.calls = []

        def get(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("include") != ["metadatas"]:
                raise AssertionError("selected contributor document was read")
            ordinary = dict(rows["public"]["metadata"], path=str(selected_path))
            orphan = dict(rows["orphan"]["metadata"], path=str(selected_path))
            return {
                "ids": ["ordinary", "orphan"],
                "metadatas": [ordinary, orphan],
            }

    selected_collection = SelectedCollection()
    with (
        mock.patch.dict("sys.modules", {"chromadb": fake_chromadb}),
        mock.patch(
            "orchestrator.embedding.get_collection",
            return_value=selected_collection,
        ),
    ):
        with pytest.raises(
            server_app._ContributorWithheld, match="withheld",
        ):
            server_app._indexed_atomic_contributor_units(
                selected_path, explicit_index=0, target_tag="",
            )
    assert len(selected_collection.calls) == 1


class _FakeCollection:
    def __init__(self, rows: dict[str, dict]):
        self.rows = {key: dict(value) for key, value in rows.items()}

    def get(self, *, where=None, **_kwargs):
        where = where or {}
        selected = []
        for row_id, metadata in self.rows.items():
            if all(metadata.get(key) == value for key, value in where.items()):
                selected.append((row_id, metadata))
        return {
            "ids": [row_id for row_id, _meta in selected],
            "metadatas": [dict(meta) for _row_id, meta in selected],
        }

    def update(self, *, ids, metadatas):
        for row_id, metadata in zip(ids, metadatas):
            self.rows[str(row_id)] = dict(metadata)


def _install_retag_owned_copy(
    *,
    data_dir: Path,
    chunks: Path,
    raw_dir: Path,
    conversation_id: str,
    chunk_id: str,
    turn_index: int,
    privacy: str,
) -> tuple[_FakeCollection, Path, Path]:
    chunks.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunks / f"2026-08-29_10-{turn_index:02d}_{chunk_id}.md"
    chunk_text = build_chunk_markdown(
        f"user {turn_index}", f"assistant {turn_index}",
        f"The user asked: user {turn_index}",
        when=datetime(2026, 8, 29, 10, turn_index),
        tag="private" if privacy == "private" else "",
        turn_privacy=privacy,
    )
    chunk_path.write_text(attach_chunk_ownership(
        chunk_text,
        conversation_id=conversation_id,
        chunk_id=chunk_id,
    ), encoding="utf-8")
    raw_path = raw_dir / f"{conversation_id}.md"
    raw_path.write_text(
        f"<!-- pair {turn_index:03d} | 2026-08-29 10:{turn_index:02d}:00 "
        f"| privacy: {privacy} -->\n",
        encoding="utf-8",
    )
    manifest = {
        "conversation_id": conversation_id,
        "turn_index": turn_index,
        "turn_privacy": privacy,
        "tag": "private" if privacy == "private" else "",
        "chunk_id": chunk_id,
        "chunk_path": str(chunk_path),
        "chunk_root": str(chunks),
        "artifact_kind": "conversation_chunk",
        "managed_by": "ora",
        "raw_path": str(raw_path),
    }
    manifest_path = data_dir / "conversation-manifest.jsonl"
    with manifest_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest) + "\n")
    collection = _FakeCollection({
        chunk_id: {
            "conversation_id": conversation_id,
            "turn_index": turn_index,
            "turn_privacy": privacy,
            "tag": "private" if privacy == "private" else "",
            "tag_private": privacy == "private",
            "chunk_path": str(chunk_path),
            "raw_path": str(raw_path),
        },
    })
    return collection, chunk_path, raw_path


def test_exact_retag_updates_only_owned_exchange_and_keeps_composer(tmp_path):
    sessions = tmp_path / "sessions"
    chunks = tmp_path / "chunks"
    raw_dir = tmp_path / "raw"
    data_dir = tmp_path / "data"
    vault = tmp_path / "vault"
    for path in (chunks, raw_dir, data_dir, vault):
        path.mkdir()
    _save(
        sessions, "mixed", "u1", "a1", tag="", privacy="standard",
        chunk_id="chunk-1", project_ids=["ora"],
    )
    _save(
        sessions, "mixed", "u2", "a2", tag="", privacy="standard",
        chunk_id="chunk-2",
    )
    assert memory.set_conversation_tag("mixed", "private", sessions_root=sessions)

    raw_path = raw_dir / "mixed.md"
    raw_path.write_text(
        "# Session mixed\n"
        "panel_id: mixed\n"
        "tag: private\n"
        "tag_private: true\n"
        "---\n"
        "<!-- pair 001 | 2026-08-29 10:00:00 | privacy: standard -->\n"
        "<!-- pair 002 | 2026-08-29 10:01:00 | privacy: standard -->\n",
        encoding="utf-8",
    )
    rows = {}
    manifest = []
    chunk_paths = {}
    block_tail_marker = "# keep block-list separator bytes\n"
    for turn in (1, 2):
        chunk_id = f"chunk-{turn}"
        path = chunks / f"2026-08-29_10-0{turn - 1}_{chunk_id}.md"
        markdown = build_chunk_markdown(
            f"u{turn}", f"a{turn}", f"The user asked: u{turn}",
            when=datetime(2026, 8, 29, 10, turn - 1),
            turn_privacy="standard",
        )
        owned_markdown = attach_chunk_ownership(
            markdown, conversation_id="mixed", chunk_id=chunk_id,
        )
        if turn == 1:
            owned_markdown = owned_markdown.replace(
                "tags:\n",
                "tags:\n"
                "  - atomic\n"
                '  - "chunk: [kept], # literal"\n'
                f"{block_tail_marker}"
                "\n"
                'retained_root: "field: [kept], # literal" # trailing comment\n',
                1,
            )
            owned_markdown = owned_markdown.replace(
                "\n---", "\ntag: \ntag_private: false\n---", 1,
            )
        path.write_text(owned_markdown, encoding="utf-8")
        chunk_paths[chunk_id] = path
        rows[chunk_id] = {
            "conversation_id": "mixed", "turn_index": turn,
            "turn_privacy": "standard", "tag": "", "tag_private": False,
            "chunk_path": str(path), "raw_path": str(raw_path),
        }
        manifest.append({
            "conversation_id": "mixed", "turn_index": turn,
            "turn_privacy": "standard", "tag": "", "chunk_id": chunk_id,
            "chunk_path": str(path), "chunk_root": str(chunks),
            "artifact_kind": "conversation_chunk", "managed_by": "ora",
            "raw_path": str(raw_path),
        })
    (data_dir / "conversation-manifest.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in manifest),
        encoding="utf-8",
    )
    staging = data_dir / "extraction-staging"
    staging.mkdir()
    quoted_derivative = staging / "quoted-source-chunk.md"
    quoted_derivative.write_text(
        "---\n"
        "artifact_kind: conversation_runtime_derivative\n"
        "managed_by: ora\n"
        'source_file: "mixed"\n'
        '"source_chunk_id": "chunk-1"\n'
        "source_turn_index: 1\n"
        'turn_privacy: "standard"\n'
        'tags: [atomic, "derivative: [kept], # literal"]\n'
        "---\n"
        "Derived body.\n",
        encoding="utf-8",
    )

    def parse_artifact(path: Path) -> tuple[dict, str]:
        artifact = path.read_text(encoding="utf-8")
        opening_end, close = closeout._frontmatter_bounds(artifact)
        metadata = yaml.safe_load(artifact[opening_end:close])
        assert isinstance(metadata, dict)
        return metadata, artifact[close:]

    def preserved_block_tail(path: Path) -> str:
        artifact = path.read_text(encoding="utf-8")
        opening_end, close = closeout._frontmatter_bounds(artifact)
        front = artifact[opening_end:close]
        start = front.index(block_tail_marker)
        end = front.index("tag: ", start)
        return front[start:end]

    expected_chunk_tags = ["atomic", "chunk: [kept], # literal"]
    expected_derivative_tags = [
        "atomic", "derivative: [kept], # literal",
    ]
    original_chunk_body = parse_artifact(chunk_paths["chunk-1"])[1]
    standard_chunk_privacy_marker = '<!-- ora-turn-privacy: "standard" -->'
    private_chunk_privacy_marker = '<!-- ora-turn-privacy: "private" -->'
    assert original_chunk_body.count(standard_chunk_privacy_marker) == 1
    expected_private_chunk_body = original_chunk_body.replace(
        standard_chunk_privacy_marker, private_chunk_privacy_marker, 1,
    )
    original_block_tail = preserved_block_tail(chunk_paths["chunk-1"])
    original_derivative_body = parse_artifact(quoted_derivative)[1]

    daily_dir = vault / "Daily Notes"
    daily_dir.mkdir()
    with (
        mock.patch.object(daily_note, "CONVERSATIONS_DIR", str(chunks)),
        mock.patch.object(daily_note, "SESSIONS_DIR", str(sessions)),
    ):
        initial_daily = daily_note.collect_conversations("2026-08-29")
    daily_path = daily_dir / "2026-08-29.md"
    daily_path.write_text(
        daily_note.render_note("2026-08-29", initial_daily, [], [], [])
        + "\n## Personal\n\nKeep this unrelated line.\n",
        encoding="utf-8",
    )
    conversations = _FakeCollection(rows)
    knowledge = _FakeCollection({})
    with (
        mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)),
        mock.patch.object(daily_note._rp, "DATA_DIR_STR", str(data_dir)),
    ):
        result = closeout.update_conversation_turn_privacy(
            "mixed", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=knowledge, vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )
    assert result["errors"] == []
    assert result["envelope_updated"] is True
    assert result["propagation_complete"] is True
    assert result["reconciliation_required"] is False
    assert result["runtime_derivative_files"] == [
        str(quoted_derivative),
    ]
    quoted_text = quoted_derivative.read_text(encoding="utf-8")
    assert '"source_chunk_id": "chunk-1"' in quoted_text
    assert 'turn_privacy: "private"' in quoted_text
    derivative_metadata, derivative_body = parse_artifact(quoted_derivative)
    assert derivative_metadata["tags"] == expected_derivative_tags + ["private"]
    assert derivative_body == original_derivative_body
    envelope = memory.load_conversation_json("mixed", sessions_root=sessions)
    assert envelope["tag"] == "private"
    assert envelope["project_ids"] == ["ora"]
    assert [m["turn_privacy"] for m in envelope["messages"]] == [
        "private", "private", "standard", "standard",
    ]
    assert conversations.rows["chunk-1"]["turn_privacy"] == "private"
    assert conversations.rows["chunk-2"]["turn_privacy"] == "standard"
    assert 'ora-turn-privacy: "private"' in (
        chunk_paths["chunk-1"]
    ).read_text(encoding="utf-8")
    assert 'ora-turn-privacy: "standard"' in (
        chunk_paths["chunk-2"]
    ).read_text(encoding="utf-8")
    retagged_chunk = chunk_paths["chunk-1"].read_text(encoding="utf-8")
    assert "\ntag: private\n" in retagged_chunk
    assert "\ntag_private: true\n" in retagged_chunk
    chunk_metadata, chunk_body = parse_artifact(chunk_paths["chunk-1"])
    assert chunk_metadata["tags"] == expected_chunk_tags + ["private"]
    assert chunk_metadata["tag"] == "private"
    assert chunk_metadata["tag_private"] is True
    assert preserved_block_tail(chunk_paths["chunk-1"]) == original_block_tail
    assert chunk_body == expected_private_chunk_body
    raw_text = raw_path.read_text(encoding="utf-8")
    assert "pair 001 | 2026-08-29 10:00:00 | privacy: private" in raw_text
    assert "pair 002 | 2026-08-29 10:01:00 | privacy: standard" in raw_text
    daily_text = daily_path.read_text(encoding="utf-8")
    assert "**u2** — 1 exchange, 10:01" in daily_text
    assert "**u1**" not in daily_text
    assert "Keep this unrelated line." in daily_text
    assert result["daily_notes"]["summaries_refreshed"] == 1

    with (
        mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)),
        mock.patch.object(daily_note._rp, "DATA_DIR_STR", str(data_dir)),
    ):
        reverse = closeout.update_conversation_turn_privacy(
            "mixed", 1, "standard", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=knowledge, vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )
    assert reverse["errors"] == []
    assert reverse["envelope_updated"] is True
    assert reverse["propagation_complete"] is True
    assert reverse["reconciliation_required"] is False
    envelope = memory.load_conversation_json("mixed", sessions_root=sessions)
    assert envelope["tag"] == "private"
    assert [m["turn_privacy"] for m in envelope["messages"]] == [
        "standard", "standard", "standard", "standard",
    ]
    assert conversations.rows["chunk-1"]["turn_privacy"] == "standard"
    assert conversations.rows["chunk-2"]["turn_privacy"] == "standard"
    chunk_metadata, chunk_body = parse_artifact(chunk_paths["chunk-1"])
    assert chunk_metadata["tags"] == expected_chunk_tags
    assert chunk_metadata["tag"] == ""
    assert chunk_metadata["tag_private"] is False
    assert preserved_block_tail(chunk_paths["chunk-1"]) == original_block_tail
    assert chunk_body == original_chunk_body
    assert 'ora-turn-privacy: "standard"' in (
        chunk_paths["chunk-1"]
    ).read_text(encoding="utf-8")
    derivative_metadata, derivative_body = parse_artifact(quoted_derivative)
    assert derivative_metadata["tags"] == expected_derivative_tags
    assert derivative_metadata["turn_privacy"] == "standard"
    assert derivative_body == original_derivative_body
    raw_text = raw_path.read_text(encoding="utf-8")
    assert "pair 001 | 2026-08-29 10:00:00 | privacy: standard" in raw_text
    assert "pair 002 | 2026-08-29 10:01:00 | privacy: standard" in raw_text

    # Even if a future formatter produces a malformed completed candidate,
    # exact retag refuses it before atomic replacement and reports incomplete
    # tightening instead of committing the canonical envelope.
    chunk_before = chunk_paths["chunk-1"].read_bytes()
    derivative_before = quoted_derivative.read_bytes()

    def malformed_candidate(source: str, *_args, **_kwargs) -> str:
        opening_end, close = closeout._frontmatter_bounds(source)
        return source[:opening_end] + "tags: [unterminated\n" + source[close:]

    with (
        mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)),
        mock.patch.object(daily_note._rp, "DATA_DIR_STR", str(data_dir)),
        mock.patch.object(
            closeout, "_private_frontmatter_text",
            side_effect=malformed_candidate,
        ),
    ):
        refused = closeout.update_conversation_turn_privacy(
            "mixed", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=knowledge, vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )
    assert refused["envelope_updated"] is False
    assert refused["propagation_complete"] is False
    assert refused["reconciliation_required"] is False
    assert any(
        "turn privacy chunk" in error
        and "YAML frontmatter is malformed" in error
        for error in refused["errors"]
    )
    assert chunk_paths["chunk-1"].read_bytes() == chunk_before
    assert quoted_derivative.read_bytes() == derivative_before
    envelope = memory.load_conversation_json("mixed", sessions_root=sessions)
    assert [m["turn_privacy"] for m in envelope["messages"]] == [
        "standard", "standard", "standard", "standard",
    ]


def test_exact_retag_requires_full_derivative_owner_tuple(tmp_path):
    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    staging = data_dir / "extraction-staging"
    staging.mkdir(parents=True)
    vault.mkdir()
    _save(
        sessions, "owned", "user", "assistant", tag="",
        privacy="standard", chunk_id="owned-chunk",
    )
    conversations, _chunk_path, _raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="owned",
        chunk_id="owned-chunk",
        turn_index=1,
        privacy="standard",
    )

    def derivative_text(*, source_file: str | None, source_turn: int) -> str:
        source_line = (
            f'source_file: "{source_file}"\n'
            if source_file is not None else ""
        )
        return (
            "---\n"
            "artifact_kind: conversation_runtime_derivative\n"
            "managed_by: ora\n"
            f"{source_line}"
            'source_chunk_id: "owned-chunk"\n'
            f"source_turn_index: {source_turn}\n"
            'turn_privacy: "standard"\n'
            "tag: \n"
            "tag_private: false\n"
            "tags:\n"
            "  - atomic\n"
            "---\n"
            "Derived body.\n"
        )

    derivative_paths = {
        "exact": staging / "exact.md",
        "missing_conversation": staging / "missing-conversation.md",
        "unrelated_conversation": staging / "unrelated-conversation.md",
        "wrong_turn": staging / "wrong-turn.md",
    }
    derivative_paths["exact"].write_text(
        derivative_text(source_file="owned", source_turn=1), encoding="utf-8",
    )
    derivative_paths["missing_conversation"].write_text(
        derivative_text(source_file=None, source_turn=1), encoding="utf-8",
    )
    derivative_paths["unrelated_conversation"].write_text(
        derivative_text(source_file="other-dialogue", source_turn=1),
        encoding="utf-8",
    )
    derivative_paths["wrong_turn"].write_text(
        derivative_text(source_file="owned", source_turn=2), encoding="utf-8",
    )
    ambiguous_text = {
        key: path.read_text(encoding="utf-8")
        for key, path in derivative_paths.items()
        if key != "exact"
    }

    exact_owner = {
        "artifact_kind": "conversation_runtime_derivative",
        "managed_by": "ora",
        "source_file": "owned",
        "source_chunk_id": "owned-chunk",
        "source_turn_index": 1,
        "turn_privacy": "standard",
        "tags": ["atomic"],
        "tag_private": False,
    }
    knowledge_rows = {
        "exact": exact_owner,
        "missing-conversation": {
            key: value for key, value in exact_owner.items()
            if key != "source_file"
        },
        "unrelated-conversation": {
            **exact_owner, "source_file": "other-dialogue",
        },
        "wrong-turn": {**exact_owner, "source_turn_index": 2},
    }
    ambiguous_knowledge = {
        row_id: dict(metadata)
        for row_id, metadata in knowledge_rows.items()
        if row_id != "exact"
    }
    knowledge = _FakeCollection(knowledge_rows)

    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        result = closeout.update_conversation_turn_privacy(
            "owned", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=knowledge, vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )

    assert result["propagation_complete"] is False
    assert result["envelope_updated"] is False
    assert result["runtime_derivative_files"] == [
        str(derivative_paths["exact"]),
    ]
    assert result["runtime_knowledge_records"] == 1
    assert sum(
        "ambiguous runtime derivative" in error
        for error in result["errors"]
    ) == 3
    assert sum(
        "ambiguous runtime knowledge row" in error
        for error in result["errors"]
    ) == 3
    assert 'turn_privacy: "private"' in derivative_paths["exact"].read_text(
        encoding="utf-8",
    )
    exact_derivative = derivative_paths["exact"].read_text(encoding="utf-8")
    assert "\ntag: private\n" in exact_derivative
    assert "\ntag_private: true\n" in exact_derivative
    for key, original in ambiguous_text.items():
        assert derivative_paths[key].read_text(encoding="utf-8") == original
    assert knowledge.rows["exact"]["turn_privacy"] == "private"
    assert knowledge.rows["exact"]["tag_private"] is True
    for row_id, original in ambiguous_knowledge.items():
        assert knowledge.rows[row_id] == original
    envelope = memory.load_conversation_json("owned", sessions_root=sessions)
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard",
    ]


def test_exact_retag_refuses_ambiguous_derivative_authority(tmp_path):
    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    staging = data_dir / "extraction-staging"
    staging.mkdir(parents=True)
    vault.mkdir()
    _save(
        sessions, "duplicate-owner", "user", "assistant", tag="",
        privacy="standard", chunk_id="duplicate-owner-chunk",
    )
    conversations, _chunk_path, _raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="duplicate-owner",
        chunk_id="duplicate-owner-chunk",
        turn_index=1,
        privacy="standard",
    )
    canonical = (
        "---\n"
        "artifact_kind: conversation_runtime_derivative\n"
        "managed_by: ora\n"
        'source_file: "duplicate-owner"\n'
        'source_chunk_id: "duplicate-owner-chunk"\n'
        "source_turn_index: 1\n"
        'turn_privacy: "standard"\n'
        "tags:\n"
        "  - atomic\n"
        "---\n"
        "Derived body.\n"
    )
    unterminated = canonical.rsplit("---\n", 1)[0] + "Derived body.\n"
    variants = {
        "merge-key.md": canonical.replace(
            'source_chunk_id: "duplicate-owner-chunk"\n',
            "defaults: &defaults\n"
            '  source_chunk_id: "duplicate-owner-chunk"\n'
            "<<: *defaults\n"
        ),
        "duplicate-owner.md": canonical.replace(
            'source_file: "duplicate-owner"\n',
            'source_file: "duplicate-owner"\n'
            'source_file: "duplicate-owner"\n',
        ),
        "quoted-duplicate-owner.md": canonical.replace(
            'source_file: "duplicate-owner"\n',
            'source_file: "duplicate-owner"\n'
            '"source_file": "other-dialogue"\n',
        ),
        "conflicting-owner.md": canonical.replace(
            "source_turn_index: 1\n",
            "source_turn_index: 1\nsource_turn_index: 2\n",
        ),
        "duplicate-privacy.md": canonical.replace(
            'turn_privacy: "standard"\n',
            'turn_privacy: "standard"\nturn_privacy: "private"\n',
        ),
        "parallel-privacy-marker.md": canonical + (
            '<!-- ora-turn-privacy: "standard" -->\n'
        ),
        "indented-parallel-owner-marker.md": canonical + (
            '   <!-- ora-conversation-id: "duplicate-owner" -->\n'
        ),
        "indented-parallel-privacy-marker.md": canonical + (
            '  <!-- ora-turn-privacy: "standard" -->\n'
        ),
        "duplicate-tags.md": canonical.replace(
            "tags:\n  - atomic\n",
            "tags:\n  - atomic\ntags:\n  - private\n",
        ),
        "duplicate-legacy-tag.md": canonical.replace(
            "tags:\n  - atomic\n",
            "tag: \ntag: \ntags:\n  - atomic\n",
        ),
        "conflicting-legacy-tag.md": canonical.replace(
            "tags:\n  - atomic\n",
            "tag: private\ntags:\n  - atomic\n",
        ),
        "duplicate-legacy-tag-private.md": canonical.replace(
            "tags:\n  - atomic\n",
            "tag_private: false\ntag_private: false\n"
            "tags:\n  - atomic\n",
        ),
        "conflicting-legacy-tag-private.md": canonical.replace(
            "tags:\n  - atomic\n",
            "tag_private: true\ntags:\n  - atomic\n",
        ),
        "malformed-unquoted-owner.md": canonical.replace(
            "tags:\n  - atomic\n",
            "broken: [\ntags:\n  - atomic\n",
        ),
        "malformed-double-quoted-owner.md": canonical.replace(
            'source_chunk_id: "duplicate-owner-chunk"\n',
            '"source_chunk_id": "duplicate-owner-chunk"\n',
        ).replace(
            "tags:\n  - atomic\n",
            "broken: [\ntags:\n  - atomic\n",
        ),
        "malformed-single-quoted-owner.md": canonical.replace(
            'source_chunk_id: "duplicate-owner-chunk"\n',
            "'source_chunk_id': 'duplicate-owner-chunk'\n",
        ).replace(
            "tags:\n  - atomic\n",
            "broken: [\ntags:\n  - atomic\n",
        ),
        "false-prefix-before-matching-owner.md": canonical.replace(
            'source_chunk_id: "duplicate-owner-chunk"\n',
            '---anything\nsource_chunk_id: "duplicate-owner-chunk"\n',
        ),
        "false-prefix-before-conflicting-owner.md": canonical.replace(
            "  - atomic\n---\n",
            '  - atomic\n---anything\nsource_chunk_id: "other-chunk"\n---\n',
        ),
        "unterminated-unquoted-owner.md": unterminated.replace(
            'source_chunk_id: "duplicate-owner-chunk"\n',
            "source_chunk_id: duplicate-owner-chunk\n",
        ),
        "unterminated-double-quoted-owner.md": unterminated.replace(
            'source_chunk_id: "duplicate-owner-chunk"\n',
            '"source_chunk_id": "duplicate-owner-chunk"\n',
        ),
        "unterminated-single-quoted-owner.md": unterminated.replace(
            'source_chunk_id: "duplicate-owner-chunk"\n',
            "'source_chunk_id': 'duplicate-owner-chunk'\n",
        ),
    }
    non_owner_variants = {
        "malformed-nested-owner-text.md": (
            "---\n"
            "metadata:\n"
            '  source_chunk_id: "duplicate-owner-chunk"\n'
            "broken: [\n"
            "---\n"
            "Unrelated body.\n"
        ),
        "malformed-body-owner-text.md": (
            "---\n"
            "broken: [\n"
            "---\n"
            'source_chunk_id: "duplicate-owner-chunk"\n'
        ),
        "unterminated-nested-owner-text.md": (
            "---\n"
            "metadata:\n"
            '  source_chunk_id: "duplicate-owner-chunk"\n'
            "broken: [\n"
        ),
    }
    originals: dict[Path, str] = {}
    for name, text in {**variants, **non_owner_variants}.items():
        path = staging / name
        path.write_text(text, encoding="utf-8")
        originals[path] = text

    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        result = closeout.update_conversation_turn_privacy(
            "duplicate-owner", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=_FakeCollection({}), vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )

    assert result["propagation_complete"] is False
    assert result["envelope_updated"] is False
    assert result["runtime_derivative_files"] == []
    assert sum(
        "ambiguous runtime derivative" in error for error in result["errors"]
    ) == len(variants)
    for name in (
        "malformed-unquoted-owner.md",
        "malformed-double-quoted-owner.md",
        "malformed-single-quoted-owner.md",
        "false-prefix-before-matching-owner.md",
        "false-prefix-before-conflicting-owner.md",
    ):
        assert any(
            name in error
            and "YAML frontmatter is malformed; retained" in error
            for error in result["errors"]
        )
    for name in (
        "unterminated-unquoted-owner.md",
        "unterminated-double-quoted-owner.md",
        "unterminated-single-quoted-owner.md",
    ):
        assert any(
            name in error
            and "unterminated YAML frontmatter; retained" in error
            for error in result["errors"]
        )
    for name in non_owner_variants:
        assert all(name not in error for error in result["errors"])
    for path, original in originals.items():
        assert path.read_text(encoding="utf-8") == original
    envelope = memory.load_conversation_json(
        "duplicate-owner", sessions_root=sessions,
    )
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard",
    ]


@pytest.mark.parametrize(
    "duplicate_authority,in_frontmatter",
    [
        ('<!-- ora-conversation-id: "duplicate-chunk" -->', False),
        ('   <!-- ora-conversation-id: "duplicate-chunk" -->', False),
        ('<!-- ora-chunk-id: "duplicate-chunk-owner" -->', False),
        ('  <!-- ora-chunk-id: "duplicate-chunk-owner" -->', False),
        ('<!-- ora-turn-privacy: "standard" -->', False),
        ('   <!-- ora-turn-privacy: "standard" -->', False),
        ('<!-- ora-turn-privacy: "private" -->', False),
        ('"turn_privacy": "private"', True),
        ('tag: \ntag: ', True),
        ('tag: private', True),
        ('tag_private: false\ntag_private: false', True),
        ('tag_private: true', True),
    ],
)
def test_exact_retag_refuses_duplicate_chunk_owner_or_privacy_authority(
        tmp_path, duplicate_authority, in_frontmatter):
    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    vault.mkdir()
    _save(
        sessions, "duplicate-chunk", "user", "assistant", tag="",
        privacy="standard", chunk_id="duplicate-chunk-owner",
    )
    conversations, chunk_path, _raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="duplicate-chunk",
        chunk_id="duplicate-chunk-owner",
        turn_index=1,
        privacy="standard",
    )
    original = chunk_path.read_text(encoding="utf-8")
    if in_frontmatter:
        original = original.replace(
            "\n---", f"\n{duplicate_authority}\n---", 1,
        )
    else:
        original += duplicate_authority + "\n"
    chunk_path.write_text(original, encoding="utf-8")

    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        result = closeout.update_conversation_turn_privacy(
            "duplicate-chunk", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=_FakeCollection({}), vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )

    assert result["propagation_complete"] is False
    assert result["envelope_updated"] is False
    assert result["chunk_files"] == []
    assert chunk_path.read_text(encoding="utf-8") == original
    assert any("turn privacy chunk" in error for error in result["errors"])
    envelope = memory.load_conversation_json(
        "duplicate-chunk", sessions_root=sessions,
    )
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard",
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate-panel", "duplicate-tag", "conflicting-tag",
        "duplicate-tag-private", "conflicting-tag-private",
        "indented-duplicate-pair-marker",
    ],
)
def test_exact_retag_refuses_ambiguous_raw_markdown_before_write(
        tmp_path, mutation):
    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    vault.mkdir()
    _save(
        sessions, "raw-ambiguous", "user", "assistant", tag="",
        privacy="standard", chunk_id="raw-ambiguous-chunk",
    )
    conversations, _chunk_path, raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="raw-ambiguous",
        chunk_id="raw-ambiguous-chunk",
        turn_index=1,
        privacy="standard",
    )
    original = (
        "# Session raw-ambiguous\n"
        "panel_id: raw-ambiguous\n"
        "tag: \n"
        "tag_private: false\n"
        "---\n"
        "<!-- pair 001 | 2026-08-29 10:01:00 | privacy: standard -->\n"
    )
    replacements = {
        "duplicate-panel": original.replace(
            "panel_id: raw-ambiguous\n",
            "panel_id: raw-ambiguous\npanel_id: raw-ambiguous\n",
        ),
        "duplicate-tag": original.replace("tag: \n", "tag: \ntag: \n"),
        "conflicting-tag": original.replace("tag: \n", "tag: private\n"),
        "duplicate-tag-private": original.replace(
            "tag_private: false\n",
            "tag_private: false\ntag_private: false\n",
        ),
        "conflicting-tag-private": original.replace(
            "tag_private: false\n", "tag_private: true\n",
        ),
        "indented-duplicate-pair-marker": original + (
            "   <!-- pair 001 | 2026-08-29 10:01:00 "
            "| privacy: standard -->\n"
        ),
    }
    raw_path.write_text(replacements[mutation], encoding="utf-8")
    before = raw_path.read_bytes()

    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        result = closeout.update_conversation_turn_privacy(
            "raw-ambiguous", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=_FakeCollection({}), vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )

    assert result["propagation_complete"] is False
    assert result["envelope_updated"] is False
    assert raw_path.read_bytes() == before
    assert any("turn privacy raw" in error for error in result["errors"])
    envelope = memory.load_conversation_json(
        "raw-ambiguous", sessions_root=sessions,
    )
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard",
    ]


@pytest.mark.parametrize(
    "missing", ["manifest", "index", "raw-pointer", "raw-marker"],
)
def test_exact_retag_reports_incomplete_known_ownership(tmp_path, missing):
    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    vault.mkdir()
    _save(
        sessions, "owned", "user", "assistant", tag="",
        privacy="standard", chunk_id="owned-chunk",
    )
    collection, _chunk_path, raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="owned",
        chunk_id="owned-chunk",
        turn_index=1,
        privacy="standard",
    )
    if missing == "manifest":
        (data_dir / "conversation-manifest.jsonl").unlink()
    elif missing == "index":
        collection = _FakeCollection({})
    elif missing == "raw-pointer":
        collection.rows["owned-chunk"].pop("raw_path")
        manifest_path = data_dir / "conversation-manifest.jsonl"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("raw_path")
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    else:
        raw_path.write_text("no exact pair marker\n", encoding="utf-8")

    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        result = closeout.update_conversation_turn_privacy(
            "owned", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=collection,
            knowledge_collection=_FakeCollection({}), vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )

    assert result["propagation_complete"] is False
    assert result["errors"]
    envelope = memory.load_conversation_json("owned", sessions_root=sessions)
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard",
    ]


def test_runtime_review_record_carries_and_reconciles_exact_turn_ownership(
        tmp_path):
    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    review_dir = data_dir / "review-queue"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    for path in (review_dir, chunks, vault):
        path.mkdir(parents=True)
    _save(
        sessions, "review-dialogue", "private user", "private assistant",
        tag="private", privacy="private", chunk_id="review-chunk",
    )

    note = SimpleNamespace(
        title="Private review derivative",
        note_type="atomic",
        subtype="principle",
        body="Private derived turn content.",
        yaml_frontmatter={"type": "working", "tags": ["atomic"]},
        relationships=[],
        source_file="untrusted-note-source",
    )
    gate_result = SimpleNamespace(
        reasons=["Human judgement required"], checks={"review": "flag"},
    )
    input_detect = ModuleType("input_detect")
    input_detect.detect_input_type = lambda _text: {
        "type": "chat", "confidence": "high", "details": {},
        "paths": [1, 2],
    }
    extraction_engine = ModuleType("extraction_engine")

    class FakeExtractionEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        def extract(self, *_args, **_kwargs):
            return SimpleNamespace(screened=[object()], signals=[])

    extraction_engine.ExtractionEngine = FakeExtractionEngine
    quality_gate = ModuleType("quality_gate")
    quality_gate.evaluate_batch = lambda *_args, **_kwargs: {
        "approved": [], "review": [(note, gate_result)],
    }

    pipeline = RuntimePipeline(config={}, call_fn=lambda *_args: "unused")
    data = SessionData(
        session_id="runtime-review",
        timestamp="2026-08-29T12:00:00",
        mode="standard",
        gear=1,
        conversation_id="review-dialogue",
        conversation_tag="private",
        turn_privacy="private",
        source_chunk_id="review-chunk",
        source_turn_index=1,
        user_prompt="private user",
        final_output="private assistant",
        source_type="chat",
    )
    try:
        with (
            mock.patch.dict("sys.modules", {
                "input_detect": input_detect,
                "extraction_engine": extraction_engine,
                "quality_gate": quality_gate,
            }),
            mock.patch(
                "orchestrator.tools.runtime_pipeline.REVIEW_DIR",
                str(review_dir),
            ),
            mock.patch(
                "orchestrator.tools.knowledge_index.make_title_similarity_search",
                return_value=None,
            ),
        ):
            extraction = pipeline._step4_knowledge_extraction(data)
    finally:
        pipeline._executor.shutdown(wait=True)

    assert extraction["review"] == 1
    assert len(extraction["review_paths"]) == 1
    review_path = Path(extraction["review_paths"][0])
    record = json.loads(review_path.read_text(encoding="utf-8"))
    assert record["artifact_kind"] == "conversation_runtime_derivative"
    assert record["managed_by"] == "ora"
    assert record["source_file"] == "review-dialogue"
    assert record["source_chunk_id"] == "review-chunk"
    assert record["source_turn_index"] == 1
    assert record["turn_privacy"] == "private"
    assert "private" in record["yaml_frontmatter"]["tags"]

    unrelated = review_dir / "other-turn.json"
    unrelated_record = {
        **record,
        "source_chunk_id": "other-chunk",
        "source_turn_index": 2,
    }
    unrelated.write_text(json.dumps(unrelated_record), encoding="utf-8")

    conversations, _chunk_path, _raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="review-dialogue",
        chunk_id="review-chunk",
        turn_index=1,
        privacy="private",
    )

    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        retag = closeout.update_conversation_turn_privacy(
            "review-dialogue", 1, "standard", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=_FakeCollection({}), vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )
    assert retag["errors"] == []
    assert retag["propagation_complete"] is True
    assert retag["runtime_review_records"] == [str(review_path)]
    reconciled = json.loads(review_path.read_text(encoding="utf-8"))
    assert reconciled["turn_privacy"] == "standard"
    assert "private" not in reconciled["yaml_frontmatter"]["tags"]
    assert json.loads(unrelated.read_text(encoding="utf-8")) == unrelated_record
    envelope = memory.load_conversation_json(
        "review-dialogue", sessions_root=sessions,
    )
    assert envelope["tag"] == "private"
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard",
    ]


def test_concurrent_runtime_review_writes_preserve_both_exact_owned_records(
        tmp_path):
    review_dir = tmp_path / "review-queue"
    review_dir.mkdir()
    note = SimpleNamespace(
        title="Shared review title",
        note_type="atomic",
        subtype="principle",
        body="Derived turn content.",
        yaml_frontmatter={"type": "working", "tags": ["atomic"]},
        relationships=[],
        source_file="untrusted-note-source",
    )
    gate_result = SimpleNamespace(
        reasons=["Human judgement required"], checks={"review": "flag"},
    )
    initial_path = os.fspath(review_dir / "Shared review title.json")
    real_exists = os.path.exists
    allocation_barrier = threading.Barrier(2)

    def synchronized_exists(path):
        exists = real_exists(path)
        if os.fspath(path) == initial_path and not exists:
            allocation_barrier.wait(timeout=5)
        return exists

    paths: list[str] = []
    errors: list[BaseException] = []

    def write_one(
        conversation_id: str,
        turn_privacy: str,
        chunk_id: str,
    ) -> None:
        try:
            paths.append(batch_processor.write_review_note(
                note,
                gate_result,
                str(review_dir),
                conversation_id=conversation_id,
                turn_privacy=turn_privacy,
                source_chunk_id=chunk_id,
                source_turn_index=1,
            ))
        except BaseException as exc:  # surfaced below in the test thread
            errors.append(exc)

    with mock.patch.object(
        batch_processor.os.path, "exists", side_effect=synchronized_exists,
    ):
        workers = [
            threading.Thread(
                target=write_one,
                args=("dialogue-private", "private", "chunk-private"),
            ),
            threading.Thread(
                target=write_one,
                args=("dialogue-standard", "standard", "chunk-standard"),
            ),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

    assert all(not worker.is_alive() for worker in workers)
    assert errors == []
    assert len(paths) == 2
    assert len(set(paths)) == 2
    records = [
        json.loads(Path(path).read_text(encoding="utf-8")) for path in paths
    ]
    assert {
        (
            record["source_file"],
            record["source_chunk_id"],
            record["source_turn_index"],
            record["turn_privacy"],
        )
        for record in records
    } == {
        ("dialogue-private", "chunk-private", 1, "private"),
        ("dialogue-standard", "chunk-standard", 1, "standard"),
    }
    records_by_privacy = {
        record["turn_privacy"]: record for record in records
    }
    assert "private" in records_by_privacy["private"]["yaml_frontmatter"]["tags"]
    assert "private" not in records_by_privacy["standard"]["yaml_frontmatter"]["tags"]


def test_review_disposition_and_exact_retag_share_turn_lock_and_ownership(
        tmp_path):
    from server import review as review_server

    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    review_dir = data_dir / "review-queue"
    staging_dir = data_dir / "extraction-staging"
    rejected_dir = data_dir / "review-rejected"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    for path in (review_dir, staging_dir, rejected_dir, chunks, vault):
        path.mkdir(parents=True)
    _save(
        sessions, "review-race", "private user", "private assistant",
        tag="private", privacy="private", chunk_id="review-race-chunk",
    )
    note = SimpleNamespace(
        title="Private review race",
        note_type="atomic",
        subtype="principle",
        body="Private derived content.",
        yaml_frontmatter={"type": "working", "tags": ["atomic", "private"]},
        relationships=[],
        source_file="ignored",
    )
    gate = SimpleNamespace(reasons=["review"], checks={"privacy": "flag"})
    review_path = Path(batch_processor.write_review_note(
        note,
        gate,
        str(review_dir),
        conversation_id="review-race",
        turn_privacy="private",
        source_chunk_id="review-race-chunk",
        source_turn_index=1,
    ))
    conversations, _chunk_path, _raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="review-race",
        chunk_id="review-race-chunk",
        turn_index=1,
        privacy="private",
    )

    shared_lock = threading.Lock()
    action_saved = threading.Event()
    release_action = threading.Event()
    retag_attempted = threading.Event()
    retag_acquired = threading.Event()
    real_save_note = review_server._save_note

    @contextmanager
    def tracked_lifecycle_lock(conversation_id):
        assert conversation_id == "review-race"
        is_retag = threading.current_thread().name == "turn-retag"
        if is_retag:
            retag_attempted.set()
        with shared_lock:
            if is_retag:
                retag_acquired.set()
            yield

    def paused_save_note(filename, record):
        real_save_note(filename, record)
        if threading.current_thread().name == "review-action":
            action_saved.set()
            if not release_action.wait(timeout=5):
                raise TimeoutError("review action test release timed out")

    responses = []
    action_errors: list[BaseException] = []
    retag_results = []
    retag_errors: list[BaseException] = []

    def approve_record():
        try:
            with review_server.app.test_client() as client:
                responses.append(client.post(
                    f"/action/{review_path.name}", data={"action": "approve"},
                ))
        except BaseException as exc:
            action_errors.append(exc)

    def retag_record():
        try:
            retag_results.append(closeout.update_conversation_turn_privacy(
                "review-race", 1, "standard", sessions_root=sessions,
                conversations_dir=chunks, collection=conversations,
                knowledge_collection=_FakeCollection({}), vault_root=vault,
                chromadb_path=tmp_path / "chroma",
            ))
        except BaseException as exc:
            retag_errors.append(exc)

    with (
        mock.patch.object(review_server, "REVIEW_DIR", str(review_dir)),
        mock.patch.object(review_server, "STAGING_DIR", str(staging_dir)),
        mock.patch.object(review_server, "REJECTED_DIR", str(rejected_dir)),
        mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)),
        mock.patch.object(
            closeout._rp, "conversation_lifecycle_lock",
            tracked_lifecycle_lock,
        ),
        mock.patch.object(review_server, "_save_note", paused_save_note),
    ):
        action_thread = threading.Thread(
            target=approve_record, name="review-action",
        )
        action_thread.start()
        assert action_saved.wait(timeout=5)

        retag_thread = threading.Thread(target=retag_record, name="turn-retag")
        retag_thread.start()
        assert retag_attempted.wait(timeout=5)
        assert not retag_acquired.is_set()
        release_action.set()
        action_thread.join(timeout=10)
        retag_thread.join(timeout=10)

        assert not action_thread.is_alive()
        assert not retag_thread.is_alive()
        assert action_errors == []
        assert retag_errors == []
        assert responses[0].status_code == 302
        assert retag_results[0]["propagation_complete"] is True

        queue_record = json.loads(review_path.read_text(encoding="utf-8"))
        assert queue_record["turn_privacy"] == "standard"
        assert "private" not in queue_record["yaml_frontmatter"]["tags"]
        approved_path = staging_dir / "Private review race.md"
        approved_text = approved_path.read_text(encoding="utf-8")
        approved_frontmatter = approved_text.split("---\n", 2)[1]
        assert "artifact_kind: conversation_runtime_derivative" in approved_frontmatter
        assert "managed_by: ora" in approved_frontmatter
        assert 'source_file: "review-race"' in approved_frontmatter
        assert 'source_chunk_id: "review-race-chunk"' in approved_frontmatter
        assert "source_turn_index: 1" in approved_frontmatter
        assert 'turn_privacy: "standard"' in approved_frontmatter
        assert "  - private" not in approved_frontmatter

        with review_server.app.test_client() as client:
            rejected_response = client.post(
                f"/action/{review_path.name}", data={"action": "reject"},
            )
        assert rejected_response.status_code == 302
        rejected_path = rejected_dir / review_path.name
        rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
        assert rejected["artifact_kind"] == "conversation_runtime_derivative"
        assert rejected["managed_by"] == "ora"
        assert rejected["source_file"] == "review-race"
        assert rejected["source_chunk_id"] == "review-race-chunk"
        assert rejected["source_turn_index"] == 1
        assert rejected["turn_privacy"] == "standard"

        tightened = closeout.update_conversation_turn_privacy(
            "review-race", 1, "private", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=_FakeCollection({}), vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )
        assert tightened["propagation_complete"] is True
        assert set(tightened["runtime_review_records"]) == {
            str(review_path), str(rejected_path),
        }
        rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
        assert rejected["turn_privacy"] == "private"
        assert "private" in rejected["yaml_frontmatter"]["tags"]


def test_background_extraction_reloads_and_verifies_canonical_turn(tmp_path):
    from server import app as server_app

    sessions = tmp_path / "sessions"
    _save(
        sessions, "worker-retag", "prior user", "prior assistant",
        tag="", privacy="standard", chunk_id="prior-chunk",
    )
    _save(
        sessions, "worker-retag", "canonical user", "canonical assistant",
        tag="", privacy="standard", chunk_id="worker-chunk",
    )
    assert memory.set_conversation_turn_privacy(
        "worker-retag", 1, "private", sessions_root=sessions,
    )
    assert memory.set_conversation_turn_privacy(
        "worker-retag", 2, "private", sessions_root=sessions,
    )
    stale_prior_history = [
        {
            "role": "user", "content": "prior user",
            "turn_privacy": "standard", "chunk_id": "prior-chunk",
            "turn_index": 1,
        },
        {
            "role": "assistant", "content": "prior assistant",
            "turn_privacy": "standard", "chunk_id": "prior-chunk",
            "turn_index": 1,
        },
    ]

    captured: list[SessionData] = []
    lock_held = {"value": False}
    real_load = memory.load_conversation_json

    @contextmanager
    def checked_lifecycle_lock(conversation_id):
        assert conversation_id == "worker-retag"
        assert lock_held["value"] is False
        lock_held["value"] = True
        try:
            yield
        finally:
            lock_held["value"] = False

    def checked_load(conversation_id, sessions_root=None):
        assert lock_held["value"] is True
        return real_load(conversation_id, sessions_root=sessions_root)

    class CapturingPipeline:
        def __init__(self, *_args, **_kwargs):
            pass

        def run_sync(self, data):
            assert lock_held["value"] is True
            captured.append(data)
            return {}

    with (
        mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
        mock.patch.object(memory, "load_conversation_json", checked_load),
        mock.patch.object(
            server_app, "_conversation_lifecycle_lock",
            checked_lifecycle_lock,
        ),
        mock.patch.object(server_app, "_is_conversation_deleted", return_value=False),
        mock.patch.object(server_app, "_is_conversation_closed", return_value=False),
        mock.patch.object(server_app, "RUNTIME_PIPELINE_AVAILABLE", True),
        mock.patch.object(server_app, "RuntimePipeline", CapturingPipeline),
    ):
        # The composer remains Standard, but the exact canonical turn has
        # already won a retag to Private before this worker acquires its lock.
        server_app._run_end_of_session_pipeline(
            "canonical user", "canonical assistant", "worker-retag", {},
            stale_prior_history,
            source_chunk_id="worker-chunk", source_turn_index=2,
        )
        assert len(captured) == 1
        assert captured[0].conversation_tag == "private"
        assert captured[0].turn_privacy == "private"
        assert captured[0].source_chunk_id == "worker-chunk"
        assert captured[0].source_turn_index == 2
        assert len(captured[0].conversation_history) == 2
        assert [
            message["role"] for message in captured[0].conversation_history
        ] == ["user", "assistant"]
        assert [
            message["content"] for message in captured[0].conversation_history
        ] == ["canonical user", "canonical assistant"]
        assert all(
            message["turn_privacy"] == "private"
            and message["chunk_id"] == "worker-chunk"
            and message["turn_index"] == 2
            for message in captured[0].conversation_history
        )

        envelope_path = sessions / "worker-retag" / "conversation.json"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["messages"][-1]["chunk_id"] = "other-chunk"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        server_app._run_end_of_session_pipeline(
            "canonical user", "canonical assistant", "worker-retag", {},
            stale_prior_history,
            source_chunk_id="worker-chunk", source_turn_index=2,
        )
        assert len(captured) == 1

        envelope["messages"][-1]["chunk_id"] = "worker-chunk"
        envelope["messages"][-1].pop("turn_privacy")
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        server_app._run_end_of_session_pipeline(
            "canonical user", "canonical assistant", "worker-retag", {},
            stale_prior_history,
            source_chunk_id="worker-chunk", source_turn_index=2,
        )
        assert len(captured) == 1


def test_private_to_standard_copy_failure_requires_reconciliation(tmp_path):
    sessions = tmp_path / "sessions"
    data_dir = tmp_path / "data"
    chunks = tmp_path / "chunks"
    vault = tmp_path / "vault"
    for path in (data_dir, chunks, vault):
        path.mkdir()
    _save(
        sessions, "mixed", "private user", "private assistant",
        tag="private", privacy="private", chunk_id="chunk-private",
    )

    class FailingCollection(_FakeCollection):
        def update(self, *, ids, metadatas):
            raise OSError("owned index copy unavailable")

    seeded, _chunk_path, _raw_path = _install_retag_owned_copy(
        data_dir=data_dir,
        chunks=chunks,
        raw_dir=tmp_path / "raw",
        conversation_id="mixed",
        chunk_id="chunk-private",
        turn_index=1,
        privacy="private",
    )
    conversations = FailingCollection(seeded.rows)
    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        result = closeout.update_conversation_turn_privacy(
            "mixed", 1, "standard", sessions_root=sessions,
            conversations_dir=chunks, collection=conversations,
            knowledge_collection=_FakeCollection({}), vault_root=vault,
            chromadb_path=tmp_path / "chroma",
        )
    envelope = memory.load_conversation_json("mixed", sessions_root=sessions)
    assert [message["turn_privacy"] for message in envelope["messages"]] == [
        "standard", "standard",
    ]
    assert result["envelope_updated"] is True
    assert result["propagation_complete"] is False
    assert result["reconciliation_required"] is True
    assert result["errors"]

    from server import app as server_app

    endpoint_result = {
        **result,
        "errors": ["turn privacy metadata: owned index copy unavailable"],
    }
    owner = {
        "conversation_id": "mixed", "turn_index": 1,
        "turn_privacy": "private", "chunk_id": "chunk-private",
    }
    with (
        mock.patch.object(
            memory, "resolve_effective_conversation_history", return_value=[],
        ),
        mock.patch.object(memory, "displayed_exchange_owner", return_value=owner),
        mock.patch.object(
            closeout, "update_conversation_turn_privacy",
            return_value=endpoint_result,
        ),
    ):
        response = server_app.app.test_client().post(
            "/api/conversation/mixed/privacy-tag",
            json={"tag": "", "turn_index": 0},
        )
    payload = json.loads(response.get_data(as_text=True))
    assert response.status_code == 409
    assert payload["ok"] is False
    assert payload["reconciliation_required"] is True
    assert "reconciliation" in payload["error"]


def test_current_output_export_uses_canonical_exchange_and_privacy(tmp_path):
    from server import app as server_app

    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    vault.mkdir()
    _save(
        sessions, "private-output", "private user", "canonical private answer",
        tag="private", privacy="private", chunk_id="private-output-chunk",
    )
    private_payload = _current_output_export_identity(
        sessions, "private-output",
    )
    private_payload.update({
        "content": "browser-supplied public poison",
        "title": "browser title must not win",
    })

    client = server_app.app.test_client()
    captured_render: dict[str, str] = {}

    def capture_render(content, *, title=None, fmt="docx", exports_dir=None):
        captured_render.update({
            "content": content, "title": title or "", "fmt": fmt,
        })
        return tmp_path / f"canonical.{fmt}"

    with (
        mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
        mock.patch.object(output_export, "vault_root", return_value=vault),
    ):
        response = client.post("/api/export", json=private_payload)
        payload = json.loads(response.get_data(as_text=True))
        assert response.status_code == 200
        exported = Path(payload["path"])
        text = exported.read_text(encoding="utf-8")
        frontmatter = text.split("---\n", 2)[1]
        assert "canonical private answer" in text
        assert "browser-supplied public poison" not in text
        assert "browser title must not win" not in text
        assert "  - private" in frontmatter
        assert "**Privacy:** Private" in text

        with (
            mock.patch.object(
                output_export, "export_capabilities",
                return_value={"pandoc": True, "docx": True, "pdf": True},
            ),
            mock.patch.object(
                output_export, "export_to_file", side_effect=capture_render,
            ),
        ):
            docx_payload = {**private_payload, "format": "docx"}
            rendered = client.post("/api/export", json=docx_payload)
        assert rendered.status_code == 200
        assert captured_render["fmt"] == "docx"
        assert "canonical private answer" in captured_render["content"]
        assert "browser-supplied public poison" not in captured_render["content"]
        assert captured_render["content"].startswith("**Privacy:** Private")

        before = set(vault.glob("*.md"))
        mismatched = {
            **private_payload, "source_chunk_id": "different-owner",
        }
        refused = client.post("/api/export", json=mismatched)
        assert refused.status_code == 409
        assert set(vault.glob("*.md")) == before

        privacy_mismatched = {
            **private_payload, "turn_privacy": "standard",
        }
        refused = client.post("/api/export", json=privacy_mismatched)
        assert refused.status_code == 409
        assert "privacy authority" in json.loads(
            refused.get_data(as_text=True),
        )["error"]
        assert set(vault.glob("*.md")) == before

        envelope_path = sessions / "private-output" / "conversation.json"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["messages"][1].pop("turn_privacy")
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        unknown = client.post("/api/export", json=private_payload)
        assert unknown.status_code == 409
        assert "privacy authority" in json.loads(
            unknown.get_data(as_text=True),
        )["error"]
        assert set(vault.glob("*.md")) == before


def test_current_output_export_authenticates_archived_inherited_owner(tmp_path):
    from server import app as server_app

    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    vault.mkdir()
    _save(
        sessions, "archived-output-owner", "archived user",
        "canonical archived answer", tag="", privacy="standard",
        chunk_id="archived-output-chunk",
    )
    assert memory.fork_conversation(
        "archived-output-owner", "archived-output-child", creation_tag="",
        sessions_root=sessions,
    )
    archived_root = sessions / "archived"
    archived_root.mkdir()
    archived_owner = archived_root / "archived-output-owner"
    (sessions / "archived-output-owner").rename(archived_owner)
    payload = _current_output_export_identity(
        sessions, "archived-output-child",
    )

    with (
        mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
        mock.patch.object(output_export, "vault_root", return_value=vault),
    ):
        response = server_app.app.test_client().post(
            "/api/export", json=payload,
        )
        assert response.status_code == 200
        exported = Path(json.loads(response.get_data(as_text=True))["path"])
        text = exported.read_text(encoding="utf-8")
        assert "canonical archived answer" in text
        assert "**Privacy:**" not in text

        before = set(vault.glob("*.md"))
        envelope_path = archived_owner / "conversation.json"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["messages"][1].pop("turn_privacy")
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        refused = server_app.app.test_client().post(
            "/api/export", json=payload,
        )
        assert refused.status_code == 409
        assert "privacy authority" in json.loads(
            refused.get_data(as_text=True),
        )["error"]
        assert set(vault.glob("*.md")) == before


def test_current_output_stealth_export_is_explicit_and_marker_free(tmp_path):
    from server import app as server_app

    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    vault.mkdir()
    _save(
        sessions, "off-record-output", "off record user", "marker free answer",
        tag="stealth", privacy="stealth", chunk_id="off-record-chunk",
    )
    payload = _current_output_export_identity(sessions, "off-record-output")
    payload["content"] = "browser content must not win"

    with (
        mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
        mock.patch.object(output_export, "vault_root", return_value=vault),
    ):
        response = server_app.app.test_client().post(
            "/api/export", json=payload,
        )
    assert response.status_code == 200
    path = Path(json.loads(response.get_data(as_text=True))["path"])
    text = path.read_text(encoding="utf-8")
    assert "marker free answer" in text
    assert "browser content must not win" not in text
    assert "**Privacy:**" not in text
    assert "turn_privacy" not in text
    assert "stealth" not in text.casefold()
    assert "off-record-output" not in text
    assert "off-record-chunk" not in text

@pytest.mark.parametrize(
    "session_title,user_prompt",
    [
        (None, ""),
        ("秘密", "相談"),
    ],
)
def test_stealth_export_uses_source_free_fallback_for_empty_or_non_ascii(
        tmp_path, session_title, user_prompt):
    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    _save(
        sessions, "source-identity-leak", user_prompt,
        "answer\n```ora-visual\n{}\n```",
        tag="stealth", privacy="stealth", chunk_id="source-free-chunk",
    )
    validator = SimpleNamespace(valid=True, errors=[], warnings=[])
    with mock.patch.object(
        vault_export, "_render_envelope_to_svg",
        return_value=("<svg/>", ""),
    ):
        result = vault_export.export_session_to_vault(
            "source-identity-leak", session_title=session_title,
            vault_root=vault, sessions_root=sessions,
            raw_conversations_dir=tmp_path / "raw",
            node_cli=tmp_path / "missing",
            master_matrix_path=tmp_path / "matrix-missing",
            _validator=lambda _envelope: validator,
        )
    text = result.markdown_path.read_text(encoding="utf-8")
    assert result.markdown_path.name.endswith("-dialogue-export.md")
    assert "\n# Dialogue export\n" in text
    assert "source-identity-leak" not in text
    assert "source-identity-leak" not in result.markdown_path.name
    assert "**Privacy:**" not in text
    assert "**Dialogue ID:**" not in text
    assert "**Source:**" not in text
    assert "stealth" not in text.casefold()
    assert len(result.sidecar_paths) == 1
    sidecar = result.sidecar_paths[0]
    assert sidecar.name == (
        f"{result.markdown_path.stem}.fig-1.svg"
    )
    assert "source-identity-leak" not in sidecar.name
    assert sidecar.read_text(encoding="utf-8") == "<svg/>"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-owner", "wrong-owner", "wrong-turn", "wrong-chunk",
        "wrong-privacy", "wrong-content",
    ],
)
def test_full_export_reauthenticates_every_effective_owner_tuple(
        tmp_path, mutation):
    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    _save(
        sessions, "canonical-export", "canonical user", "canonical answer",
        tag="", privacy="standard", chunk_id="canonical-chunk",
    )
    forged = memory.resolve_effective_conversation_history(
        "canonical-export", sessions_root=sessions,
    )
    assert forged is not None
    if mutation == "missing-owner":
        forged[0].pop("_ora_history_owner")
        forged[1].pop("_ora_history_owner")
    elif mutation == "wrong-owner":
        forged[0]["_ora_history_owner"] = "different-dialogue"
        forged[1]["_ora_history_owner"] = "different-dialogue"
    elif mutation == "wrong-turn":
        forged[0]["_ora_history_turn_index"] = 2
        forged[1]["_ora_history_turn_index"] = 2
    elif mutation == "wrong-chunk":
        forged[0]["chunk_id"] = "different-chunk"
        forged[1]["chunk_id"] = "different-chunk"
    elif mutation == "wrong-privacy":
        forged[0]["turn_privacy"] = "private"
        forged[1]["turn_privacy"] = "private"
    else:
        forged[1]["content"] = "forged browser-visible answer"

    with (
        mock.patch.object(
            memory, "resolve_effective_conversation_history",
            return_value=forged,
        ),
        pytest.raises(ValueError, match="Full Dialogue export refused"),
    ):
        vault_export.export_session_to_vault(
            "canonical-export", vault_root=vault, sessions_root=sessions,
            raw_conversations_dir=tmp_path / "raw",
            node_cli=tmp_path / "missing",
            master_matrix_path=tmp_path / "matrix-missing",
            _validator=lambda _envelope: None,
        )
    assert list(vault.rglob("*.md")) == []


@pytest.mark.parametrize(
    "source_tag,forged_privacy",
    [("", "stealth"), ("stealth", "private")],
)
def test_full_export_never_infers_marker_free_stealth_from_conflicting_state(
        tmp_path, source_tag, forged_privacy):
    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    original_privacy = "stealth" if source_tag == "stealth" else "standard"
    _save(
        sessions, "conflicting-export", "private-sensitive user",
        "private-sensitive answer", tag=source_tag,
        privacy=original_privacy, chunk_id="conflicting-chunk",
    )
    path = sessions / "conflicting-export" / "conversation.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    for message in envelope["messages"]:
        message["turn_privacy"] = forged_privacy
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError, match="owner identity"):
        vault_export.export_session_to_vault(
            "conflicting-export", vault_root=vault, sessions_root=sessions,
            raw_conversations_dir=tmp_path / "raw",
            node_cli=tmp_path / "missing",
            master_matrix_path=tmp_path / "matrix-missing",
            _validator=lambda _envelope: None,
        )
    assert list(vault.rglob("*.md")) == []

def test_full_export_rejects_stealth_owner_for_nonstealth_target(tmp_path):
    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    _save(
        sessions, "nonstealth-target", "target user", "target answer",
        tag="", privacy="standard", chunk_id="target-chunk",
    )
    _save(
        sessions, "stealth-owner", "owned user", "owned answer",
        tag="stealth", privacy="stealth", chunk_id="owned-chunk",
    )
    stealth_history = memory.resolve_effective_conversation_history(
        "stealth-owner", sessions_root=sessions,
    )
    assert stealth_history is not None

    with (
        mock.patch.object(
            memory, "resolve_effective_conversation_history",
            return_value=stealth_history,
        ),
        pytest.raises(ValueError, match="non-Stealth target"),
    ):
        vault_export.export_session_to_vault(
            "nonstealth-target", vault_root=vault, sessions_root=sessions,
            raw_conversations_dir=tmp_path / "raw",
            node_cli=tmp_path / "missing",
            master_matrix_path=tmp_path / "matrix-missing",
            _validator=lambda _envelope: None,
        )
    assert list(vault.rglob("*.md")) == []


def test_full_export_routes_hold_all_owner_locks_through_publication(tmp_path):
    from server import app as server_app

    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    _save(
        sessions, "a-export-owner", "owner user", "owner answer",
        tag="", privacy="standard", chunk_id="owner-chunk",
    )
    assert memory.fork_conversation(
        "a-export-owner", "z-export-target", creation_tag="",
        sessions_root=sessions,
    )

    expected = {"a-export-owner", "z-export-target"}
    server_locks: dict[str, threading.RLock] = {}
    process_locks: dict[str, threading.RLock] = {}
    active_server: set[str] = set()
    active_process: set[str] = set()
    server_order: dict[str, list[str]] = {}
    process_order: dict[str, list[str]] = {}
    state_guard = threading.Lock()
    export_entered = threading.Event()
    release_export = threading.Event()
    retag_attempted = threading.Event()
    retag_acquired = threading.Event()
    calls: list[dict[str, object]] = []

    @contextmanager
    def tracked_server_lock(conversation_id):
        identity = conversation_id.casefold()
        lock = server_locks.setdefault(identity, threading.RLock())
        with lock:
            name = threading.current_thread().name
            with state_guard:
                active_server.add(identity)
                server_order.setdefault(name, []).append(identity)
            try:
                yield
            finally:
                with state_guard:
                    active_server.remove(identity)

    @contextmanager
    def tracked_process_lock(conversation_id, timeout=30.0):
        del timeout
        identity = conversation_id.casefold()
        lock = process_locks.setdefault(identity, threading.RLock())
        is_retag = threading.current_thread().name == "turn-retag"
        if is_retag:
            retag_attempted.set()
        with lock:
            if is_retag:
                retag_acquired.set()
            name = threading.current_thread().name
            with state_guard:
                active_process.add(identity)
                process_order.setdefault(name, []).append(identity)
            try:
                yield
            finally:
                with state_guard:
                    active_process.remove(identity)

    def fake_export(conversation_id, **_kwargs):
        with state_guard:
            calls.append({
                "conversation_id": conversation_id,
                "server": set(active_server),
                "process": set(active_process),
            })
        if threading.current_thread().name == "full-export":
            export_entered.set()
            if not release_export.wait(timeout=5):
                raise TimeoutError("full export test release timed out")
        return SimpleNamespace(
            markdown_path=tmp_path / "export.md",
            sidecar_paths=[], warnings=[], envelope_count=0,
            invalid_envelopes=[],
        )

    fake_module = ModuleType("vault_export")
    fake_module.export_session_to_vault = fake_export
    fake_module.ExportResult = object
    responses = []

    def call_full_export():
        with server_app.app.test_client() as client:
            responses.append(client.post(
                "/api/export",
                json={
                    "scope": "full_conversation",
                    "conversation_id": "z-export-target",
                },
            ))

    def attempt_retag():
        with tracked_process_lock("a-export-owner"):
            pass

    with (
        mock.patch.object(memory, "_DEFAULT_SESSIONS_ROOT", sessions),
        mock.patch.object(
            server_app, "_conversation_lifecycle_lock", tracked_server_lock,
        ),
        mock.patch.object(
            server_app.rp, "conversation_lifecycle_lock",
            tracked_process_lock,
        ),
        mock.patch.dict("sys.modules", {"vault_export": fake_module}),
    ):
        export_thread = threading.Thread(
            target=call_full_export, name="full-export",
        )
        export_thread.start()
        assert export_entered.wait(timeout=5)

        retag_thread = threading.Thread(
            target=attempt_retag, name="turn-retag",
        )
        retag_thread.start()
        assert retag_attempted.wait(timeout=5)
        assert not retag_acquired.is_set()

        release_export.set()
        export_thread.join(timeout=10)
        retag_thread.join(timeout=10)
        assert not export_thread.is_alive()
        assert not retag_thread.is_alive()
        assert responses[0].status_code == 200
        assert retag_acquired.is_set()

        with server_app.app.test_client() as client:
            session_response = client.post(
                "/api/session/export",
                json={
                    "conversation_id": "z-export-target",
                    "_sessions_root": str(sessions),
                    "_vault_root": str(vault),
                },
            )
        assert session_response.status_code == 200

    assert len(calls) == 2
    assert all(call["conversation_id"] == "z-export-target" for call in calls)
    assert all(call["server"] == expected for call in calls)
    assert all(call["process"] == expected for call in calls)
    assert server_order["full-export"] == sorted(expected)
    assert process_order["full-export"] == sorted(expected)
    assert server_order[threading.current_thread().name] == sorted(expected)
    assert process_order[threading.current_thread().name] == sorted(expected)


def test_full_export_and_v3_controls_preserve_mixed_truth(tmp_path):
    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    _save(
        sessions, "export", "s-user", "s-assistant", tag="",
        privacy="standard", chunk_id="s", project_ids=["ora", "research"],
    )
    assert memory.set_conversation_tag("export", "private", sessions_root=sessions)
    _save(
        sessions, "export", "p-user", "p-assistant", tag="private",
        privacy="private", chunk_id="p",
    )
    exported = vault_export.export_session_to_vault(
        "export", vault_root=vault, sessions_root=sessions,
        raw_conversations_dir=tmp_path / "raw", node_cli=tmp_path / "missing",
        master_matrix_path=tmp_path / "matrix-missing",
        _validator=lambda _envelope: None,
    )
    text = exported.markdown_path.read_text(encoding="utf-8")
    assert "  - private" in text
    assert "**Privacy:** Standard" in text
    assert "**Privacy:** Private" in text
    assert "**Dialogue ID:** `export`" in text
    assert "**Source:**" in text
    assert memory.load_conversation_json(
        "export", sessions_root=sessions,
    )["project_ids"] == ["ora", "research"]

    _save(
        sessions, "stealth-export", "off-record user", "off-record assistant",
        tag="stealth", privacy="stealth", chunk_id="stealth-chunk",
    )
    stealth_result = vault_export.export_session_to_vault(
        "stealth-export", vault_root=vault, sessions_root=sessions,
        raw_conversations_dir=tmp_path / "raw", node_cli=tmp_path / "missing",
        master_matrix_path=tmp_path / "matrix-missing",
        _validator=lambda _envelope: None,
    )
    stealth_text = stealth_result.markdown_path.read_text(encoding="utf-8")
    stealth_frontmatter = stealth_text.split("---\n", 2)[1]
    assert "off-record user" in stealth_text
    assert "off-record assistant" in stealth_text
    assert "  - private" not in stealth_frontmatter
    assert "**Privacy:**" not in stealth_text
    assert "**Dialogue ID:**" not in stealth_text
    assert "**Source:**" not in stealth_text
    assert str(sessions / "stealth-export" / "conversation.json") not in stealth_text

    _save(
        sessions, "parent-export", "ancestor question one",
        "ancestor answer one", tag="", privacy="standard",
        chunk_id="parent-standard", project_ids=["ora", "research"],
    )
    assert memory.set_conversation_tag(
        "parent-export", "private", sessions_root=sessions,
    )
    _save(
        sessions, "parent-export", "ancestor question two",
        "ancestor answer two", tag="private", privacy="private",
        chunk_id="parent-private",
    )
    assert memory.fork_conversation(
        "parent-export", "child-export", creation_tag="stealth",
        sessions_root=sessions,
    )
    _save(
        sessions, "child-export", "branch question", "branch answer",
        tag="stealth", privacy="stealth", chunk_id="child-chunk",
    )
    parent_path = sessions / "parent-export" / "conversation.json"
    child_path = sessions / "child-export" / "conversation.json"
    parent_before = parent_path.read_bytes()
    child_before = child_path.read_bytes()
    child_envelope = json.loads(child_before)
    assert child_envelope["project_ids"] == ["ora", "research"]
    assert child_envelope["parent_conversation_id"] == "parent-export"

    archived_root = sessions / "archived"
    archived_root.mkdir()
    archived_parent = archived_root / "parent-export" / "conversation.json"
    parent_path.parent.rename(archived_parent.parent)
    fork_export = vault_export.export_session_to_vault(
        "child-export", session_title="Forked export", vault_root=vault,
        sessions_root=sessions, raw_conversations_dir=tmp_path / "raw",
        node_cli=tmp_path / "missing",
        master_matrix_path=tmp_path / "matrix-missing",
        _validator=lambda _envelope: None,
    )
    fork_text = fork_export.markdown_path.read_text(encoding="utf-8")
    canonical_contents = [
        "ancestor question one",
        "ancestor answer one",
        "ancestor question two",
        "ancestor answer two",
        "branch question",
        "branch answer",
    ]
    positions = [fork_text.index(content) for content in canonical_contents]
    assert positions == sorted(positions)
    fork_frontmatter = fork_text.split("---\n", 2)[1]
    assert "  - private" not in fork_frontmatter
    assert "**Privacy:**" not in fork_text
    assert "**Dialogue ID:**" not in fork_text
    assert "**Source:**" not in fork_text
    assert "stealth" not in fork_text.casefold()
    assert child_path.read_bytes() == child_before
    assert archived_parent.read_bytes() == parent_before

    orphan_path = sessions / "child-export" / "conversation.json"
    orphan = json.loads(orphan_path.read_text(encoding="utf-8"))
    orphan["messages"].append({
        "role": "assistant", "content": "orphan assistant",
        "turn_privacy": "stealth",
    })
    orphan_path.write_text(json.dumps(orphan), encoding="utf-8")
    with pytest.raises(ValueError, match="exchange is incomplete"):
        vault_export.export_session_to_vault(
            "child-export", vault_root=vault, sessions_root=sessions,
            raw_conversations_dir=tmp_path / "raw",
            node_cli=tmp_path / "missing",
            master_matrix_path=tmp_path / "matrix-missing",
            _validator=lambda _envelope: None,
        )

    _save(
        sessions, "unknown-export", "unknown user", "unknown assistant",
        tag="", privacy="standard", chunk_id="unknown-chunk",
    )
    unknown_path = sessions / "unknown-export" / "conversation.json"
    unknown = json.loads(unknown_path.read_text(encoding="utf-8"))
    unknown["messages"][1].pop("turn_privacy")
    unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown or conflicting privacy"):
        vault_export.export_session_to_vault(
            "unknown-export", vault_root=vault, sessions_root=sessions,
            raw_conversations_dir=tmp_path / "raw",
            node_cli=tmp_path / "missing",
            master_matrix_path=tmp_path / "matrix-missing",
            _validator=lambda _envelope: None,
        )

    changed_python = [
        "orchestrator/boot.py", "orchestrator/conversation_chunk.py",
        "orchestrator/conversation_closeout.py",
        "orchestrator/conversation_memory.py",
        "orchestrator/export.py",
        "orchestrator/tools/daily_note.py",
        "orchestrator/tools/knowledge_search.py",
        "orchestrator/tools/runtime_pipeline.py",
        "orchestrator/vault_export.py", "server/app.py", "server/review.py",
    ]
    for relative in changed_python:
        ast.parse((REPO / relative).read_text(encoding="utf-8"), filename=relative)

    conversation_js = (REPO / "server/static/js/v3-conversation.js").read_text(
        encoding="utf-8",
    )
    menu_html = (REPO / "server/index-v3.html").read_text(encoding="utf-8")
    show_turn = conversation_js.split("const showTurn =", 1)[1].split(
        "const goFirst", 1,
    )[0]
    assert "state.activeTag" not in show_turn
    assert "setTurnPrivacy" in conversation_js
    assert "turn_index: turnIndex" in conversation_js
    assert "Compose next as Private" in menu_html
    assert "Make displayed turn Private" in menu_html
    assert "conversation.setTurnPrivacy" in menu_html
    assert "reconciliation_required" in conversation_js

    export_toolbar = (
        REPO / "server/static/js/export-toolbar.js"
    ).read_text(encoding="utf-8")
    authority_block = export_toolbar.split(
        "const currentOutputAuthority =", 1,
    )[1].split("async function runExport", 1)[0]
    for field in (
        "conversation_id", "source_conversation_id", "source_turn_index",
        "source_chunk_id", "turn_privacy",
    ):
        assert field in authority_block
    current_output_calls = [
        line for line in export_toolbar.splitlines()
        if "scope: 'current_output'" in line
    ]
    assert len(current_output_calls) == 2
    assert all("content" not in line and "title" not in line
               for line in current_output_calls)

    server_source = (REPO / "server/app.py").read_text(encoding="utf-8")
    composer_branch = server_source.split(
        'def conversation_privacy_tag(conversation_id):', 1,
    )[1].split('# ── V3 Backlog 2C:', 1)[0]
    assert "set_conversation_tag(conversation_id, target)" in composer_branch
    assert "update_conversation_privacy_tag(" not in composer_branch
