"""
runtime_pipeline.py — Runtime End-of-Pipeline Processing (Phase 11)

Executes after output delivery in every pipeline session. Runs asynchronously
so the user can start a new session immediately.

Runtime steps:
  1. Session logging
  2. Conversation summary (five-level) — already implemented, calls existing code
  3. Continuity Prompt archiving
  4. Knowledge extraction via Document Processing Framework
  5. Quality gate
  6. Vault write (auto-approved notes)
  7. ChromaDB ingestion
  8. Pass 1 relationship extraction
  9. Glossary gap check
  10. Tag validation
  11. Entity extraction for co-occurrence
  12. Pass 2 relationship discovery (semantic neighbors for new notes)
  13. Convergence check (flag notes with ≥5 arrival_history entries)
  14. Engram promotion (and optional git autocommit/push)

Performance budget: 3-10 minutes total, runs asynchronously after output delivery.

Usage:
    from orchestrator.tools.runtime_pipeline import RuntimePipeline
    pipeline = RuntimePipeline(config, call_fn)
    pipeline.run_async(session_data)
"""

from __future__ import annotations

import json
import os
import stat
import sys
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    from orchestrator import runtime_paths as _rp
except ImportError:  # pragma: no cover - legacy top-level import context
    import runtime_paths as _rp  # type: ignore

VAULT_PATH = _rp.VAULT_STR
STAGING_DIR = os.path.join(_rp.DATA_DIR_STR, "extraction-staging")
REVIEW_DIR = os.path.join(_rp.DATA_DIR_STR, "review-queue")
SESSION_LOG_DIR = os.path.join(_rp.DATA_DIR_STR, "session-logs")
CONTINUITY_DIR = os.path.join(_rp.DATA_DIR_STR, "continuity")


@dataclass
class SessionData:
    """Data from a completed pipeline session."""
    session_id: str
    timestamp: str
    mode: str
    gear: int
    # Stable lifecycle identity. ``session_id`` is the legacy six-character
    # processing run id; conversation_id is what Delete Forever and privacy
    # propagation can use to find every automatically-derived note.
    conversation_id: str = ""
    conversation_tag: str = ""
    models_used: list[str] = field(default_factory=list)
    rag_resources: list[str] = field(default_factory=list)
    token_consumption: dict = field(default_factory=dict)  # {stage: tokens}
    budget_signals: list[int] = field(default_factory=list)
    user_prompt: str = ""
    cleaned_prompt: str = ""
    final_output: str = ""
    conversation_history: list[dict] = field(default_factory=list)
    continuity_prompt: str = ""
    nexus: str = ""  # project nexus for continuity archiving
    source_type: str = ""  # override for input type detection ("chat" from server)


CHROMADB_PATH = str(_rp.ORA_HOME / "chromadb")
ENTITY_INDEX_PATH = os.path.join(_rp.DATA_DIR_STR, "entity-index.json")
CONVERGENCE_THRESHOLD = 5  # arrival_history entries needed for engram promotion flag
_STAGING_WRITE_LOCK = threading.Lock()


def _metadata_tag_state(metadata: dict, tag: str) -> bool | None:
    """Return indexed tag membership, or None when legacy metadata is silent."""
    marker = f"tag_{tag}"
    if marker in metadata:
        value = metadata.get(marker)
        if isinstance(value, bool):
            return value
        normalized = str(value or "").strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return None

    if "tags" not in metadata:
        return None
    value = metadata.get("tags")
    if isinstance(value, str):
        raw = value.strip()
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = raw.split(",")
        value = decoded
    if not isinstance(value, (list, tuple, set, frozenset)):
        return None
    if any(isinstance(item, (dict, list, tuple, set)) for item in value):
        return None
    return tag.lower() in {str(item).strip().lower() for item in value}


def _staging_directory(*, create: bool = False) -> Path:
    """Return the managed extraction root without following a root symlink."""
    configured = Path(STAGING_DIR)
    return _rp.safe_owned_subdir(
        configured.parent, configured.name, create=create,
    )


@dataclass
class RuntimeResult:
    """Results of runtime pipeline processing."""
    session_id: str
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    notes_extracted: int = 0
    notes_approved: int = 0
    notes_review: int = 0
    notes_promoted: int = 0
    notes_duplicates: int = 0
    engram_autocommit: dict = field(default_factory=dict)
    relationships_found: int = 0
    pass2_relationships: int = 0
    convergence_flags: list[str] = field(default_factory=list)
    glossary_gaps: list[str] = field(default_factory=list)
    tag_warnings: list[str] = field(default_factory=list)
    total_time_seconds: float = 0.0


class RuntimePipeline:
    """
    End-of-pipeline processing that runs after every session.

    Args:
        config: Endpoints configuration dict.
        call_fn: Model call function(messages, endpoint) -> str.
        vault_path: Path to vault root.
    """

    def __init__(self, config: dict = None, call_fn=None,
                 vault_path: str = None):
        self.config = config or {}
        self.call_fn = call_fn
        self.vault_path = vault_path or VAULT_PATH
        self.chromadb_path = os.path.abspath(os.path.expanduser(str(
            self.config.get("chromadb_path") or CHROMADB_PATH
        )))
        self._executor = ThreadPoolExecutor(max_workers=1)

    def run_async(self, session_data: SessionData) -> None:
        """
        Run the pipeline asynchronously. Returns immediately.
        The user can start a new session while this runs.
        """
        self._executor.submit(self._run, session_data)

    def run_sync(self, session_data: SessionData) -> RuntimeResult:
        """Run the pipeline synchronously (for testing or debugging)."""
        return self._run(session_data)

    def _run(self, session_data: SessionData) -> RuntimeResult:
        """Execute all runtime steps in sequence."""
        start_time = time.time()
        result = RuntimeResult(session_id=session_data.session_id)
        staged_paths: list[str] = []

        # Step 1: Session logging
        try:
            self._step1_session_log(session_data)
            result.steps_completed.append("session_logging")
        except Exception as e:
            result.steps_failed.append(f"session_logging: {e}")

        # Step 2: Conversation summary (delegate to existing code)
        try:
            self._step2_conversation_summary(session_data)
            result.steps_completed.append("conversation_summary")
        except Exception as e:
            result.steps_failed.append(f"conversation_summary: {e}")

        # Step 3: Continuity Prompt archiving
        try:
            self._step3_continuity_archive(session_data)
            result.steps_completed.append("continuity_archive")
        except Exception as e:
            result.steps_failed.append(f"continuity_archive: {e}")

        # Step 4-6: Knowledge extraction → Quality gate → Vault write
        try:
            extract_result = self._step4_knowledge_extraction(session_data)
            result.notes_extracted = extract_result.get("extracted", 0)
            result.notes_approved = extract_result.get("approved", 0)
            result.notes_review = extract_result.get("review", 0)
            staged_paths = list(extract_result.get("staged_paths") or [])
            result.steps_completed.append("knowledge_extraction")
        except Exception as e:
            result.steps_failed.append(f"knowledge_extraction: {e}")

        # Step 7: ChromaDB ingestion
        try:
            self._step7_chromadb_ingest(staged_paths)
            result.steps_completed.append("chromadb_ingestion")
        except Exception as e:
            result.steps_failed.append(f"chromadb_ingestion: {e}")

        # Step 8: Relationship extraction
        try:
            rel_count = self._step8_relationship_extraction(staged_paths)
            result.relationships_found = rel_count
            result.steps_completed.append("relationship_extraction")
        except Exception as e:
            result.steps_failed.append(f"relationship_extraction: {e}")

        # Step 9: Glossary gap check
        try:
            gaps = self._step9_glossary_check(staged_paths)
            result.glossary_gaps = gaps
            result.steps_completed.append("glossary_check")
        except Exception as e:
            result.steps_failed.append(f"glossary_check: {e}")

        # Step 10: Tag validation
        try:
            warnings = self._step10_tag_validation(staged_paths)
            result.tag_warnings = warnings
            result.steps_completed.append("tag_validation")
        except Exception as e:
            result.steps_failed.append(f"tag_validation: {e}")

        # Step 11: Entity extraction
        try:
            self._step11_entity_extraction(staged_paths)
            result.steps_completed.append("entity_extraction")
        except Exception as e:
            result.steps_failed.append(f"entity_extraction: {e}")

        # Step 12: Pass 2 relationship discovery (semantic neighbors)
        # Query each new note against ChromaDB for high-similarity existing notes.
        # Heuristic classification runs inline; model classification deferred.
        try:
            p2_count = self._step12_pass2_relationships(
                staged_paths,
                include_private=session_data.conversation_tag == "private",
            )
            result.pass2_relationships = p2_count
            result.steps_completed.append("pass2_relationships")
        except Exception as e:
            result.steps_failed.append(f"pass2_relationships: {e}")

        # Step 13: Convergence check
        # Flag notes whose arrival_history crossed the engram promotion threshold.
        try:
            flags = self._step13_convergence_check(staged_paths)
            result.convergence_flags = flags
            result.steps_completed.append("convergence_check")
        except Exception as e:
            result.steps_failed.append(f"convergence_check: {e}")

        # Step 14: Promote staged notes into the vault as engrams — the
        # previously-missing final step that closes the conversation→engram loop.
        # Runs last so promoted engrams carry the relationships/enrichment added
        # by steps 8/12. ORA_RUNTIME_ENGRAM_PROMOTION controls vault writes;
        # ORA_RUNTIME_ENGRAM_AUTOCOMMIT controls the optional git commit/push.
        try:
            if os.environ.get("ORA_RUNTIME_ENGRAM_PROMOTION", "").strip().lower() in (
                    "1", "on", "true", "yes"):
                from orchestrator.tools.engram_promotion import promote_staging_files
                promo = promote_staging_files(
                    staged_paths,
                    index=True,
                    chromadb_path=self.chromadb_path,
                )
                result.notes_promoted = promo.get("promoted", 0)
                result.notes_duplicates = promo.get("duplicates", 0)
                result.engram_autocommit = promo.get("autocommit", {})
                result.steps_completed.append("engram_promotion")
        except Exception as e:
            result.steps_failed.append(f"engram_promotion: {e}")

        result.total_time_seconds = time.time() - start_time

        # Write runtime result log
        self._log_result(result)

        return result

    # -------------------------------------------------------------------
    # Individual steps
    # -------------------------------------------------------------------

    def _step1_session_log(self, data: SessionData):
        """Write complete session record."""
        os.makedirs(SESSION_LOG_DIR, exist_ok=True)

        log = {
            "session_id": data.session_id,
            "timestamp": data.timestamp,
            "mode": data.mode,
            "gear": data.gear,
            "models_used": data.models_used,
            "rag_resources": data.rag_resources,
            "token_consumption": data.token_consumption,
            "budget_signals": data.budget_signals,
            "prompt_length": len(data.user_prompt),
            "output_length": len(data.final_output),
        }

        path = os.path.join(SESSION_LOG_DIR, f"{data.session_id}.json")
        with open(path, "w") as f:
            json.dump(log, f, indent=2)

    def _step2_conversation_summary(self, data: SessionData):
        """
        Generate and store conversation summary.
        Delegates to the existing conversation processing pipeline.
        """
        # Build session transcript for processing
        if not data.conversation_history:
            return

        # The conversation processing pipeline in server.py handles this
        # For runtime, we ensure the latest exchange is processed
        # This is already called by server.py inline mode — here we ensure
        # it ran, and if not, call it as batch for the full session
        pass  # Delegated to existing inline processing in server.py

    def _step3_continuity_archive(self, data: SessionData):
        """Archive continuity prompt for active project."""
        if not data.continuity_prompt:
            return

        os.makedirs(CONTINUITY_DIR, exist_ok=True)

        # Write to project-specific continuity file
        nexus = data.nexus or "commons"
        path = os.path.join(CONTINUITY_DIR, f"continuity-{nexus}.md")

        with open(path, "w") as f:
            f.write(f"# Continuity — {nexus}\n\n")
            f.write(f"*Last updated: {data.timestamp}*\n")
            f.write(f"*Session: {data.session_id}*\n\n")
            f.write(data.continuity_prompt)

    def _step4_knowledge_extraction(self, data: SessionData) -> dict:
        """
        Run Document Processing Framework on session transcript.
        Returns counts of extracted/approved/review notes.
        """
        if not data.final_output and not data.conversation_history:
            return {"extracted": 0, "approved": 0, "review": 0,
                    "staged_paths": []}

        # Build session transcript
        transcript = self._build_transcript(data)
        if not transcript:
            return {"extracted": 0, "approved": 0, "review": 0,
                    "staged_paths": []}

        try:
            from input_detect import detect_input_type
            from extraction_engine import ExtractionEngine
            from quality_gate import evaluate_batch

            # Detect type — override with source_type when set (e.g. "chat" from server)
            type_result = detect_input_type(transcript)
            if data.source_type and type_result.get("type") != data.source_type:
                type_result["type"] = data.source_type
                type_result["confidence"] = "high"
                type_result["details"]["source_type_override"] = True
                # Ensure chat path runs both extraction paths
                if data.source_type == "chat":
                    type_result["paths"] = [1, 2]

            # Run extraction
            engine = ExtractionEngine(call_fn=self.call_fn, config=self.config)
            source_file = data.conversation_id or data.session_id
            extraction = engine.extract(
                transcript,
                type_result,
                source_file=source_file,
                history_messages=(data.conversation_history or None),
            )

            if not extraction.screened:
                return {"extracted": 0, "approved": 0, "review": 0,
                        "staged_paths": []}

            # Quality gate
            from orchestrator.tools.batch_processor import write_review_note

            signal_confidence = {
                sig.id: sig.confidence
                for sig in (getattr(extraction, "signals", None) or [])
                if getattr(sig, "id", None)
            }
            gate_results = evaluate_batch(
                extraction.screened, signal_confidence=signal_confidence
            )

            approved = gate_results.get("approved", [])
            review = gate_results.get("review", [])

            # Write approved notes to staging
            staged_paths: list[str] = []
            for note, _ in approved:
                staged_paths.append(self._write_note_to_staging(
                    note,
                    source_file=source_file,
                    private=data.conversation_tag == "private",
                ))

            # Persist the notes the gate routed to human judgement. This
            # path used to count them and drop them, so anything the gate
            # flagged in a chat session was lost with no trace. Failing to
            # write one must not lose the approved notes, so it degrades
            # loudly rather than raising.
            review_paths: list[str] = []
            for note, gate_result in review:
                try:
                    review_paths.append(
                        write_review_note(note, gate_result, REVIEW_DIR)
                    )
                except OSError as exc:
                    print(
                        "[runtime_pipeline] could not persist review note "
                        f"{getattr(note, 'title', 'Untitled')!r}: "
                        f"{type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )

            return {
                "extracted": len(extraction.screened),
                "approved": len(approved),
                "review": len(review),
                "staged_paths": staged_paths,
                "review_paths": review_paths,
            }
        except ImportError:
            return {"extracted": 0, "approved": 0, "review": 0,
                    "staged_paths": []}
        except Exception:
            return {"extracted": 0, "approved": 0, "review": 0,
                    "staged_paths": []}

    def _staged_note_paths(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None,
    ) -> list[str]:
        """Resolve an explicit run-owned path set, or scan only for legacy callers."""
        try:
            staging_dir = _staging_directory(create=False)
        except Exception as exc:
            print(f"[runtime_pipeline] unsafe staging root: {exc}", file=sys.stderr)
            return []
        if note_paths is None:
            if not staging_dir.is_dir():
                return []
            candidates = (
                str(staging_dir / name)
                for name in os.listdir(staging_dir)
                if name.endswith(".md")
            )
        else:
            candidates = (os.fspath(path) for path in note_paths)

        staging_root = os.path.abspath(staging_dir)
        resolved: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            path = os.path.abspath(candidate)
            if (not path.endswith(".md")
                    or os.path.normcase(os.path.dirname(path))
                    != os.path.normcase(staging_root)):
                print(f"[runtime_pipeline] skipped non-staging run path: {path}",
                      file=sys.stderr)
                continue
            try:
                mode = os.stat(path, follow_symlinks=False).st_mode
            except OSError:
                continue
            if path in seen or not stat.S_ISREG(mode):
                continue
            seen.add(path)
            resolved.append(path)
        return resolved

    def _step7_chromadb_ingest(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None = None,
    ):
        """Ingest newly staged notes into ChromaDB knowledge collection."""
        try:
            from orchestrator.tools.knowledge_index import index_single_file
        except ImportError:
            # Knowledge index not available — skip
            return

        for path in self._staged_note_paths(note_paths):
            try:
                index_single_file(
                    path,
                    verbose=False,
                    chromadb_path=self.chromadb_path,
                )
            except Exception as exc:
                # Fail open: the session continues and the note stays in
                # staging, but the miss must be visible — a silent pass
                # here left staged notes unindexed for weeks.
                print(f"[runtime_pipeline] chromadb ingest failed for "
                      f"{os.path.basename(path)}: {type(exc).__name__}: {exc}",
                      file=sys.stderr)

    def _step8_relationship_extraction(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None = None,
    ) -> int:
        """Run Pass 1 relationship discovery on newly staged notes."""
        count = 0
        try:
            from orchestrator.tools.relationship_discovery import discover_relationships

            for path in self._staged_note_paths(note_paths):
                relationships = discover_relationships(path, self.vault_path)
                count += len(relationships)
        except ImportError:
            pass

        return count

    def _step9_glossary_check(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None = None,
    ) -> list[str]:
        """Check definitions_required against glossary index."""
        gaps = []

        for path in self._staged_note_paths(note_paths):
            try:
                with open(path, "r") as fh:
                    content = fh.read()

                # Extract definitions_required from YAML
                import re
                yaml_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if yaml_match:
                    yaml_text = yaml_match.group(1)
                    # Simple parse for definitions_required
                    in_defs = False
                    for line in yaml_text.split('\n'):
                        if line.strip().startswith('definitions_required:'):
                            in_defs = True
                            continue
                        if in_defs and line.strip().startswith('- '):
                            term = line.strip()[2:].strip()
                            # Check if glossary note exists
                            if not self._glossary_exists(term):
                                gaps.append(term)
                        elif in_defs and not line.strip().startswith('- '):
                            in_defs = False
            except Exception:
                continue

        return gaps

    def _step10_tag_validation(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None = None,
    ) -> list[str]:
        """Validate tags against controlled vocabulary."""
        # Controlled vocabulary from Framework — Knowledge Artifact Coach
        controlled_tags = {
            "atomic", "molecular", "compound", "process", "glossary",
            "framework/instruction", "framework/builder", "position",
            "archived", "incubating", "private",
            "epistemology", "narrative_theory", "cosmology",
            "political_economy", "ai_methodology",
        }

        warnings = []

        for path in self._staged_note_paths(note_paths):
            f = os.path.basename(path)
            try:
                with open(path, "r") as fh:
                    content = fh.read()

                import re
                yaml_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if yaml_match:
                    yaml_text = yaml_match.group(1)
                    in_tags = False
                    for line in yaml_text.split('\n'):
                        if line.strip().startswith('tags:'):
                            in_tags = True
                            continue
                        if in_tags and line.strip().startswith('- '):
                            tag = line.strip()[2:].strip()
                            if tag and tag not in controlled_tags:
                                warnings.append(f"{f}: unrecognized tag '{tag}'")
                        elif in_tags and not line.strip().startswith('- '):
                            in_tags = False
            except Exception:
                continue

        return warnings

    def _step11_entity_extraction(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None = None,
    ):
        """Retire the unused, provenance-free entity cache.

        Repository-wide call-site review found no reader for
        ``entity-index.json``; the runtime step was its sole writer. Keeping a
        title-only cache made Private retagging and Delete Forever impossible to
        implement exactly, so runtime removes the obsolete cache instead of
        generating another unmanaged derivative.
        """
        del note_paths
        path = os.path.abspath(ENTITY_INDEX_PATH)
        if not (os.path.lexists(path)):
            return
        if os.path.isdir(path) and not os.path.islink(path):
            raise ValueError(f"refusing to retire non-file entity index: {path}")
        os.unlink(path)
        print(f"[runtime_pipeline] retired unused entity index: {path}",
              file=sys.stderr)

    def _step12_pass2_relationships(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None = None,
        *,
        include_private: bool = False,
    ) -> int:
        """
        Pass 2 relationship discovery at runtime: query each newly staged
        note against ChromaDB for semantic neighbors, classify relationship
        type using heuristic. O(1) per new note — no full-vault scan.
        """
        try:
            import chromadb
            from orchestrator.embedding import get_collection
            client = chromadb.PersistentClient(path=self.chromadb_path)
            collection = get_collection(client, "knowledge")
        except Exception:
            return 0

        try:
            from orchestrator.tools.relationship_discovery import update_note_relationships
        except ImportError:
            update_note_relationships = None

        new_relationships = 0
        similarity_threshold = 0.85

        for path in self._staged_note_paths(note_paths):
            fname = os.path.basename(path)
            try:
                with open(path, "r") as fh:
                    content = fh.read()
            except Exception:
                continue

            note_title = fname[:-3]

            # Query this note against the collection for nearest neighbors
            try:
                results = collection.query(
                    query_texts=[content[:2000]],  # first 2000 chars
                    n_results=10,
                    where=(None if include_private else {"tag_private": False}),
                )
            except Exception:
                continue

            if not results or not results.get("ids"):
                continue

            proposed_relationships: list[dict] = []
            known_target_paths: dict[str, list[str]] = {}
            for i, match_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                similarity = max(0, 1 - (distance / 2))

                if similarity < similarity_threshold:
                    continue

                # Get match title from metadata
                match_title = str(match_id)
                match_metadata: dict = {}
                if results.get("metadatas") and i < len(results["metadatas"][0]):
                    match_metadata = results["metadatas"][0][i] or {}
                    match_title = str(match_metadata.get("title") or match_id)

                # Skip self-matches
                if match_title == note_title:
                    continue

                archived_state = _metadata_tag_state(match_metadata, "archived")
                raw_path = str(
                    match_metadata.get("path")
                    or match_metadata.get("obsidian_path")
                    or ""
                ).strip()
                target_path = ""
                if raw_path:
                    candidate = (
                        raw_path if os.path.isabs(raw_path)
                        else os.path.join(self.vault_path, raw_path)
                    )
                    candidate = os.path.realpath(candidate)
                    vault_root = os.path.realpath(self.vault_path)
                    try:
                        inside_vault = os.path.commonpath(
                            [vault_root, candidate]
                        ) == vault_root
                    except ValueError:
                        inside_vault = False
                    expected_title = os.path.basename(candidate).rsplit(".", 1)[0]
                    if (
                        inside_vault
                        and os.path.isfile(candidate)
                        and expected_title == match_title
                    ):
                        target_path = candidate
                        known_target_paths.setdefault(match_title, []).append(candidate)

                if not target_path:
                    metadata_hint = (
                        "archived" if archived_state is True
                        else "active" if archived_state is False
                        else "unknown"
                    )
                    print(
                        f"[runtime_pipeline] canonical archived-target YAML "
                        f"unavailable for {match_title}; policy failed open "
                        f"(indexed state: {metadata_hint})",
                        file=sys.stderr,
                    )

                # Heuristic classification
                rel_type = self._classify_relationship_heuristic(
                    note_title, match_title, similarity
                )

                if rel_type and rel_type != "no_relationship":
                    proposed_relationships.append({
                        "target": match_title,
                        "type": rel_type,
                        "confidence": round(similarity, 3),
                        "source": "pass2_runtime",
                    })

            if not proposed_relationships:
                continue
            if update_note_relationships:
                try:
                    new_relationships += int(update_note_relationships(
                        path,
                        proposed_relationships,
                        vault_path=self.vault_path,
                        known_paths=known_target_paths,
                        return_count=True,
                    ))
                except Exception as exc:
                    print(
                        f"[runtime_pipeline] Pass 2 relationship mutation failed "
                        f"for {path}: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
            else:
                new_relationships += len(proposed_relationships)

        return new_relationships

    @staticmethod
    def _classify_relationship_heuristic(source_title: str, target_title: str,
                                          similarity: float) -> str:
        """Heuristic relationship type classification from title analysis."""
        s_words = set(source_title.lower().split()) - {
            "the", "a", "an", "of", "in", "for", "and", "to", "is"
        }
        t_words = set(target_title.lower().split()) - {
            "the", "a", "an", "of", "in", "for", "and", "to", "is"
        }
        shared = s_words & t_words

        if similarity >= 0.95:
            return "parallels"
        elif shared and len(shared) >= 2:
            return "qualifies"
        elif similarity >= 0.90:
            return "extends"
        elif similarity >= 0.85:
            return "parallels"
        return "no_relationship"

    def _step13_convergence_check(
        self,
        note_paths: Iterable[str | os.PathLike[str]] | None = None,
    ) -> list[str]:
        """
        Check newly staged notes for convergence: if arrival_history
        crossed the engram promotion threshold, flag it.
        Runs inline at dedup time via arrival_history count — nanosecond cost.
        """
        flags = []

        for path in self._staged_note_paths(note_paths):
            fname = os.path.basename(path)
            try:
                with open(path, "r") as fh:
                    content = fh.read()

                # Parse YAML frontmatter for arrival_history
                if not content.startswith("---"):
                    continue
                end = content.index("---", 3)
                import yaml
                fm = yaml.safe_load(content[3:end])
                if not fm:
                    continue

                arrival = fm.get("arrival_history", [])
                if isinstance(arrival, list) and len(arrival) >= CONVERGENCE_THRESHOLD:
                    title = fname[:-3]
                    flags.append(
                        f"{title}: {len(arrival)} independent arrivals — "
                        f"engram promotion candidate"
                    )
            except Exception:
                continue

        return flags

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _build_transcript(self, data: SessionData) -> str:
        """Build a session transcript from conversation history."""
        if not data.conversation_history:
            # Fallback: build from prompt and output
            if data.user_prompt and data.final_output:
                return (
                    f"**User:**\n\n{data.user_prompt}\n\n"
                    f"**Assistant:**\n\n{data.final_output}"
                )
            return ""

        parts = []
        for msg in data.conversation_history:
            role = msg.get("role", "user").title()
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(f"**{role}:**\n\n{content}")

        return "\n\n".join(parts)

    def _write_note_to_staging(
        self,
        note,
        *,
        source_file: str = "",
        private: bool = False,
    ):
        """Write an extracted note to the staging directory."""
        import re

        title = getattr(note, "title", "Untitled")
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
        safe_title = re.sub(r'\s+', ' ', safe_title).strip()[:200]
        safe_title = safe_title or "Untitled"

        fm = getattr(note, "yaml_frontmatter", {})
        body = getattr(note, "body", "")

        lines = ["---"]
        nexus = fm.get("nexus", "")
        if isinstance(nexus, list) and nexus:
            lines.append("nexus:")
            for n in nexus:
                lines.append(f"  - {n}")
        else:
            lines.append("nexus:")
        lines.append(f"type: {fm.get('type', 'working')}")
        # Strict lifecycle ownership. Once promoted into a user-vault root,
        # source_file alone is only provenance (a user-authored note may cite
        # the same Dialogue); these fields are what authorize surgical
        # privacy/delete handling.
        lines.append("artifact_kind: conversation_runtime_derivative")
        lines.append("managed_by: ora")
        tags = fm.get("tags", [])
        if not isinstance(tags, list):
            tags = [tags] if tags else []
        tags = [str(tag) for tag in tags if str(tag).strip()]
        if private and "private" not in tags:
            tags.append("private")
        if isinstance(tags, list) and tags:
            lines.append("tags:")
            for t in tags:
                lines.append(f"  - {t}")
        else:
            lines.append("tags:")
        if source_file:
            # ``source_file`` is a standard DP provenance field consumed by
            # knowledge_index.  Using the stable conversation id makes
            # privacy changes and Delete Forever exact instead of relying on
            # filenames or semantic matching.
            lines.append(
                "source_file: " + json.dumps(source_file, ensure_ascii=False)
            )
        subtype = getattr(note, "subtype", None)
        if subtype:
            lines.append(f"subtype: {subtype}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {title}")
        lines.append("")
        lines.append(body)

        content = "\n".join(lines)
        # Different conversations may finish concurrently. Serialize filename
        # allocation with creation so equal titles never overwrite each other
        # or cause one run to claim another run's path.
        with _STAGING_WRITE_LOCK:
            staging_dir = _staging_directory(create=True)
            path = staging_dir / f"{safe_title}.md"
            counter = 1
            while os.path.lexists(path):
                if path.is_symlink():
                    raise ValueError(f"refusing symlinked staging note: {path}")
                path = staging_dir / f"{safe_title}-{counter}.md"
                counter += 1
            _rp.atomic_write_text(path, content)
        return str(path)

    def _glossary_exists(self, term: str) -> bool:
        """Check if a glossary note exists for a given term."""
        # Search vault for matching glossary note
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.lower() == f"{term.lower()}.md":
                    return True
                # Also check with domain qualifier pattern: "Term (Domain).md"
                if f.lower().startswith(f"{term.lower()} ("):
                    return True
        return False

    def _log_result(self, result: RuntimeResult):
        """Write runtime pipeline result to log."""
        os.makedirs(SESSION_LOG_DIR, exist_ok=True)
        path = os.path.join(SESSION_LOG_DIR, f"{result.session_id}-runtime.json")

        log = {
            "session_id": result.session_id,
            "timestamp": datetime.now().isoformat(),
            "steps_completed": result.steps_completed,
            "steps_failed": result.steps_failed,
            "notes_extracted": result.notes_extracted,
            "notes_approved": result.notes_approved,
            "notes_review": result.notes_review,
            "notes_promoted": result.notes_promoted,
            "notes_duplicates": result.notes_duplicates,
            "engram_autocommit": result.engram_autocommit,
            "relationships_found": result.relationships_found,
            "pass2_relationships": result.pass2_relationships,
            "convergence_flags": result.convergence_flags,
            "glossary_gaps": result.glossary_gaps,
            "tag_warnings": result.tag_warnings,
            "total_time_seconds": result.total_time_seconds,
        }

        with open(path, "w") as f:
            json.dump(log, f, indent=2)


if __name__ == "__main__":
    print("Runtime End-of-Pipeline Processing (Phase 11)")
    print()
    print("Steps executed after every session:")
    print("  1. Session logging")
    print("  2. Conversation summary (five-level)")
    print("  3. Continuity Prompt archiving")
    print("  4. Knowledge extraction (Document Processing Framework)")
    print("  5. Quality gate")
    print("  6. Vault write (auto-approved)")
    print("  7. ChromaDB ingestion")
    print("  8. Relationship extraction (Pass 1)")
    print("  9. Glossary gap check")
    print("  10. Tag validation")
    print("  11. Entity extraction for co-occurrence")
    print("  12. Pass 2 relationships (semantic neighbors for new notes)")
    print("  13. Convergence check (engram promotion flags)")
    print("  14. Engram promotion (optional git autocommit/push)")
    print()
    print("Runs asynchronously — user can start new session immediately")
    print(f"Session logs: {SESSION_LOG_DIR}")
    print(f"Staging dir: {STAGING_DIR}")
