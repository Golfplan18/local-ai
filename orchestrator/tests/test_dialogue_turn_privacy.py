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

from orchestrator import conversation_closeout as closeout
from orchestrator import conversation_memory as memory
from orchestrator import vault_export
from orchestrator.conversation_chunk import (
    attach_chunk_ownership,
    build_chroma_metadata,
    build_chunk_markdown,
)
from orchestrator.tools import daily_note, knowledge_search
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
    assert [m["content"] for m in memory.resolve_effective_conversation_history(
        "standard-child", sessions_root=tmp_path,
    )] == ["s-user", "s-assistant"]

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
        "gist": "", "name": "Mixed Dialogue",
    }]
    assert private[0]["exchanges"] == 2


def test_library_search_filters_exact_authority_before_every_score(monkeypatch):
    from server import app as server_app

    class BombText(str):
        def lower(self):  # pragma: no cover - reached only on a privacy leak
            raise AssertionError("ineligible conversation text was lexically scored")

    metadata = {
        1: {
            "conversation_id": "mixed", "turn_privacy": "private",
            "chroma:document": BombText("private needleword"), "pair_num": 2,
        },
        2: {
            "conversation_id": "mixed", "turn_privacy": "standard",
            "chroma:document": "public needleword", "pair_num": 1,
        },
        3: {
            "conversation_id": "legacy",
            "chroma:document": BombText("unknown needleword"), "pair_num": 1,
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
                    (1, "private-row", BombText("private needleword"), 0.1),
                    (3, "unknown-row", BombText("unknown needleword"), 0.2),
                    (2, "standard-row", "public needleword", 0.3),
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
                    BombText("private needleword"),
                    BombText("unknown needleword"),
                    "public needleword",
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

    searchable, _mapping = server_app._browser_searchable_conversation({
        "messages": [
            {"role": "user", "content": "public needleword", "turn_privacy": "standard"},
            {"role": "assistant", "content": "public answer", "turn_privacy": "standard"},
            {"role": "user", "content": "private secretword", "turn_privacy": "private"},
            {"role": "assistant", "content": "private answer", "turn_privacy": "private"},
            {"role": "user", "content": "unknown secretword"},
            {"role": "assistant", "content": "unknown answer"},
        ],
    }, "")
    assert server_app._conversation_search_snippet(
        searchable, "secretword",
    )["score"] == 0
    assert server_app._conversation_search_snippet(
        searchable, "needleword",
    )["score"] > 0

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
        "<!-- pair 001 | 2026-08-29 10:00:00 | privacy: standard -->\n"
        "<!-- pair 002 | 2026-08-29 10:01:00 | privacy: standard -->\n",
        encoding="utf-8",
    )
    rows = {}
    manifest = []
    for turn in (1, 2):
        chunk_id = f"chunk-{turn}"
        path = chunks / f"{chunk_id}.md"
        path.write_text(
            "---\ntags:\n---\n"
            '<!-- ora-conversation-id: "mixed" -->\n'
            f'<!-- ora-chunk-id: "{chunk_id}" -->\n\n'
            '<!-- ora-turn-privacy: "standard" -->\n\nbody\n',
            encoding="utf-8",
        )
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
    conversations = _FakeCollection(rows)
    knowledge = _FakeCollection({})
    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
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
    envelope = memory.load_conversation_json("mixed", sessions_root=sessions)
    assert envelope["tag"] == "private"
    assert envelope["project_ids"] == ["ora"]
    assert [m["turn_privacy"] for m in envelope["messages"]] == [
        "private", "private", "standard", "standard",
    ]
    assert conversations.rows["chunk-1"]["turn_privacy"] == "private"
    assert conversations.rows["chunk-2"]["turn_privacy"] == "standard"
    assert 'ora-turn-privacy: "private"' in (
        chunks / "chunk-1.md"
    ).read_text(encoding="utf-8")
    assert 'ora-turn-privacy: "standard"' in (
        chunks / "chunk-2.md"
    ).read_text(encoding="utf-8")
    raw_text = raw_path.read_text(encoding="utf-8")
    assert "pair 001 | 2026-08-29 10:00:00 | privacy: private" in raw_text
    assert "pair 002 | 2026-08-29 10:01:00 | privacy: standard" in raw_text


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

    with mock.patch.object(closeout._rp, "DATA_DIR_STR", str(data_dir)):
        retag = closeout.update_conversation_turn_privacy(
            "review-dialogue", 1, "standard", sessions_root=sessions,
            conversations_dir=chunks, collection=_FakeCollection({}),
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
                conversations_dir=chunks, collection=_FakeCollection({}),
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
            conversations_dir=chunks, collection=_FakeCollection({}),
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
        sessions, "worker-retag", "canonical user", "canonical assistant",
        tag="", privacy="standard", chunk_id="worker-chunk",
    )
    assert memory.set_conversation_turn_privacy(
        "worker-retag", 1, "private", sessions_root=sessions,
    )

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
            "canonical user", "canonical assistant", "worker-retag", {}, [],
            source_chunk_id="worker-chunk", source_turn_index=1,
        )
        assert len(captured) == 1
        assert captured[0].conversation_tag == "private"
        assert captured[0].turn_privacy == "private"
        assert captured[0].source_chunk_id == "worker-chunk"
        assert captured[0].source_turn_index == 1
        assert captured[0].conversation_history[-2]["chunk_id"] == "worker-chunk"
        assert captured[0].conversation_history[-1]["turn_privacy"] == "private"

        envelope_path = sessions / "worker-retag" / "conversation.json"
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope["messages"][1]["chunk_id"] = "other-chunk"
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        server_app._run_end_of_session_pipeline(
            "canonical user", "canonical assistant", "worker-retag", {}, [],
            source_chunk_id="worker-chunk", source_turn_index=1,
        )
        assert len(captured) == 1

        envelope["messages"][1]["chunk_id"] = "worker-chunk"
        envelope["messages"][1].pop("turn_privacy")
        envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
        server_app._run_end_of_session_pipeline(
            "canonical user", "canonical assistant", "worker-retag", {}, [],
            source_chunk_id="worker-chunk", source_turn_index=1,
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

    conversations = FailingCollection({
        "chunk-private": {
            "conversation_id": "mixed", "turn_index": 1,
            "turn_privacy": "private", "tag": "private",
            "tag_private": True,
        },
    })
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


def test_full_export_and_v3_controls_preserve_mixed_truth(tmp_path):
    sessions = tmp_path / "sessions"
    vault = tmp_path / "vault"
    _save(
        sessions, "export", "s-user", "s-assistant", tag="",
        privacy="standard", chunk_id="s",
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
        sessions, "parent-export", "inherited user", "inherited assistant",
        tag="", privacy="standard", chunk_id="parent-chunk",
    )
    assert memory.fork_conversation(
        "parent-export", "child-export", creation_tag="",
        sessions_root=sessions,
    )
    _save(
        sessions, "child-export", "local user", "local assistant",
        tag="", privacy="standard", chunk_id="child-chunk",
    )
    fork_export = vault_export.export_session_to_vault(
        "child-export", session_title="Forked export", vault_root=vault,
        sessions_root=sessions, raw_conversations_dir=tmp_path / "raw",
        node_cli=tmp_path / "missing",
        master_matrix_path=tmp_path / "matrix-missing",
        _validator=lambda _envelope: None,
    )
    fork_text = fork_export.markdown_path.read_text(encoding="utf-8")
    assert "inherited user" in fork_text
    assert "inherited assistant" in fork_text
    assert "local user" in fork_text
    assert "local assistant" in fork_text

    orphan_path = sessions / "child-export" / "conversation.json"
    orphan = json.loads(orphan_path.read_text(encoding="utf-8"))
    orphan["messages"].append({
        "role": "assistant", "content": "orphan assistant",
        "turn_privacy": "standard",
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

    server_source = (REPO / "server/app.py").read_text(encoding="utf-8")
    composer_branch = server_source.split(
        'def conversation_privacy_tag(conversation_id):', 1,
    )[1].split('# ── V3 Backlog 2C:', 1)[0]
    assert "set_conversation_tag(conversation_id, target)" in composer_branch
    assert "update_conversation_privacy_tag(" not in composer_branch
