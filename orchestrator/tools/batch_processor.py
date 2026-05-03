"""
batch_processor.py — Batch Processing Mode for Document Processing Pipeline (Phase 10, Step 12)

Queue management for large processing jobs (e.g., 3,500 historical conversations).

Queue architecture:
  INPUT QUEUE → FORMAT CONVERSION → TYPE DETECTION → EXTRACTION PIPELINE →
  QUALITY GATE → DEDUPLICATION → REVIEW QUEUES → VAULT WRITE → RELATIONSHIP INDEX

Features:
  - Resumable processing via manifest (crash-safe)
  - Per-document context isolation (no cross-document contamination)
  - Progress tracking and reporting
  - Configurable concurrency and time limits

Usage:
    from orchestrator.tools.batch_processor import BatchProcessor
    processor = BatchProcessor(config=endpoints_config, call_fn=call_model)
    processor.process_directory("/path/to/input/")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


MANIFEST_PATH = os.path.expanduser("~/ora/data/processing-manifest.json")
STAGING_DIR = os.path.expanduser("~/ora/data/extraction-staging/")
REVIEW_DIR = os.path.expanduser("~/ora/data/review-queue/")


@dataclass
class ProcessingStats:
    """Statistics for a batch processing run."""
    started: str = ""
    total_files: int = 0
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    notes_extracted: int = 0
    notes_approved: int = 0
    notes_rejected: int = 0
    notes_review: int = 0
    current_file: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class FileStatus:
    """Processing status for a single file."""
    path: str
    status: str = "pending"  # pending, processing, completed, failed, skipped
    input_type: str = ""
    processed_at: str = ""
    notes_extracted: int = 0
    notes_approved: int = 0
    notes_rejected: int = 0
    notes_review: int = 0
    error: str | None = None
    duration_seconds: float = 0.0


class BatchProcessor:
    """
    Batch document processing orchestrator.

    Coordinates format conversion, type detection, extraction, quality gate,
    deduplication, and vault write for a directory of input files.
    """

    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".pptx", ".html", ".htm",
        ".rtf", ".txt", ".md", ".json",
    }

    def __init__(self, config: dict = None, call_fn=None,
                 vault_path: str = None, manifest_path: str = None):
        """
        Args:
            config: Endpoints configuration dict.
            call_fn: Model call function(messages, endpoint) -> str.
            vault_path: Path to vault root.
            manifest_path: Path to processing manifest JSON.
        """
        self.config = config or {}
        self.call_fn = call_fn
        self.vault_path = vault_path or os.path.expanduser("~/Documents/vault")
        self.manifest_path = manifest_path or MANIFEST_PATH
        self.stats = ProcessingStats()
        self._manifest = {}
        self._file_statuses: dict[str, FileStatus] = {}

    def process_directory(self, input_dir: str,
                          time_limit_hours: float = None,
                          file_limit: int = None) -> ProcessingStats:
        """
        Process all supported files in a directory.

        Args:
            input_dir: Directory containing files to process.
            time_limit_hours: Optional time limit for the batch run.
            file_limit: Optional maximum number of files to process.

        Returns:
            ProcessingStats with final counts.
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        # Ensure output directories exist
        os.makedirs(STAGING_DIR, exist_ok=True)
        os.makedirs(REVIEW_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)

        # Load or create manifest
        self._load_manifest()

        # Build input queue
        queue = self._build_queue(input_path)

        self.stats = ProcessingStats(
            started=datetime.now().isoformat(),
            total_files=len(queue),
        )

        start_time = time.time()
        time_limit_seconds = time_limit_hours * 3600 if time_limit_hours else None
        processed_count = 0

        for file_status in queue:
            # Check time limit
            if time_limit_seconds:
                elapsed = time.time() - start_time
                if elapsed >= time_limit_seconds:
                    break

            # Check file limit
            if file_limit and processed_count >= file_limit:
                break

            # Process single file
            self.stats.current_file = file_status.path
            self._process_file(file_status)
            processed_count += 1

            # Save manifest after each file (crash-safe)
            self._save_manifest()

        self.stats.elapsed_seconds = time.time() - start_time
        self.stats.current_file = ""

        # Final manifest save
        self._save_manifest()

        return self.stats

    def process_single(self, file_path: str) -> FileStatus:
        """
        Process a single file through the full pipeline.

        Args:
            file_path: Path to the file to process.

        Returns:
            FileStatus with processing results.
        """
        os.makedirs(STAGING_DIR, exist_ok=True)
        os.makedirs(REVIEW_DIR, exist_ok=True)

        status = FileStatus(path=file_path)
        self._process_file(status)
        return status

    def get_progress(self) -> dict:
        """Return current processing progress."""
        return {
            "stats": asdict(self.stats),
            "files": {
                path: asdict(status)
                for path, status in self._file_statuses.items()
            },
        }

    def resume(self) -> ProcessingStats:
        """
        Resume processing from the last saved manifest.
        Picks up from the first pending file.
        """
        self._load_manifest()

        # Find pending files
        pending = [
            FileStatus(path=path, **info)
            for path, info in self._manifest.get("files", {}).items()
            if info.get("status") == "pending"
        ]

        if not pending:
            return self.stats

        self.stats = ProcessingStats(
            started=datetime.now().isoformat(),
            total_files=len(pending),
        )

        start_time = time.time()

        for file_status in pending:
            self.stats.current_file = file_status.path
            self._process_file(file_status)
            self._save_manifest()

        self.stats.elapsed_seconds = time.time() - start_time
        self.stats.current_file = ""
        self._save_manifest()

        return self.stats

    # -------------------------------------------------------------------
    # Internal methods
    # -------------------------------------------------------------------

    def _build_queue(self, input_path: Path) -> list[FileStatus]:
        """Build ordered input queue from directory contents."""
        files = []

        for f in sorted(input_path.iterdir()):
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                # Check manifest — skip already completed files
                if str(f) in self._manifest.get("files", {}):
                    existing_status = self._manifest["files"][str(f)].get("status")
                    if existing_status == "completed":
                        self.stats.skipped += 1
                        continue

                files.append(FileStatus(path=str(f)))

        # Sort by modification time (oldest first)
        files.sort(key=lambda fs: os.path.getmtime(fs.path)
                   if os.path.exists(fs.path) else 0)

        return files

    def _process_file(self, file_status: FileStatus):
        """Process a single file through the full pipeline."""
        file_status.status = "processing"
        self._file_statuses[file_status.path] = file_status
        start_time = time.time()

        try:
            # Step 1: Format conversion
            from orchestrator.tools.format_convert import convert_to_markdown
            markdown = convert_to_markdown(file_status.path)

            # Step 2: Input type detection
            from orchestrator.tools.input_detect import detect_input_type
            type_result = detect_input_type(markdown)
            file_status.input_type = type_result["type"]

            # Skip fragments and unknown types
            if type_result["type"] in ("fragment", "unknown"):
                file_status.status = "skipped"
                file_status.error = f"Input type '{type_result['type']}' — requires human review"
                self.stats.skipped += 1
                return

            # Step 3: HCP processing for long-form sources
            if type_result.get("hcp"):
                from orchestrator.tools.hcp import process_long_form, format_chunk_for_extraction
                chunks = process_long_form(markdown, self.call_fn,
                                           self._get_endpoint("sidebar"))
                # Process each chunk independently
                all_screened = []
                for chunk in chunks:
                    chunk_text = format_chunk_for_extraction(chunk)
                    chunk_result = self._run_extraction(
                        chunk_text, type_result, file_status.path
                    )
                    if chunk_result:
                        all_screened.extend(chunk_result)
            else:
                # Standard extraction
                all_screened = self._run_extraction(
                    markdown, type_result, file_status.path
                ) or []

            # Step 4: Quality gate
            from orchestrator.tools.quality_gate import QualityGate, evaluate_batch
            gate_results = evaluate_batch(all_screened)

            file_status.notes_extracted = len(all_screened)
            file_status.notes_approved = len(gate_results.get("approved", []))
            file_status.notes_rejected = len(gate_results.get("rejected", []))
            file_status.notes_review = len(gate_results.get("review", []))

            # Step 5: Deduplication (for approved notes)
            from orchestrator.tools.deduplication import DeduplicationEngine
            dedup = DeduplicationEngine()
            approved_notes = [note for note, _ in gate_results.get("approved", [])]
            if approved_notes:
                dedup_results = dedup.check_batch(approved_notes)
                # Filter out duplicates
                final_approved = []
                for note, dedup_result in zip(approved_notes, dedup_results):
                    if dedup_result.action in ("keep",):
                        final_approved.append(note)
                    elif dedup_result.action == "merge_into":
                        # Write merge provenance
                        file_status.notes_approved -= 1
                file_status.notes_approved = len(final_approved)

            # Step 6: Write approved notes to staging
            for note, _ in gate_results.get("approved", []):
                self._write_to_staging(note)

            # Step 7: Write review queue notes
            for note, result in gate_results.get("review", []):
                self._write_to_review(note, result)

            # Step 8: Path 2 — conversation re-emission as chunks.
            # Re-emits each prompt+response pair as a Schema §12 chunk
            # file plus a Conv RAG §2 ChromaDB record using the same
            # shape as live `_save_conversation`. Historical timestamps
            # preserved so the chunks land at their original date.
            if type_result["type"] == "chat" and 2 in type_result.get("paths", []):
                try:
                    from orchestrator.tools.path2_emitter import emit_path2_chunks
                    from orchestrator.vault_export import _parse_raw_session_log
                    messages = _parse_raw_session_log(markdown)
                    if messages:
                        conversation_id = os.path.basename(file_status.path)
                        chromadb_path = self.config.get(
                            "chromadb_path",
                            os.path.expanduser("~/ora/chromadb/"),
                        )
                        conversations_dir = os.path.expanduser(
                            "~/Documents/conversations/",
                        )
                        path2_result = emit_path2_chunks(
                            messages,
                            conversation_id=conversation_id,
                            raw_path=file_status.path,
                            conversations_dir=conversations_dir,
                            chromadb_path=chromadb_path,
                        )
                        # Stats summary onto the FileStatus for the manifest.
                        # (Use existing fields where possible; add path2_result
                        # detail in `error` only if errors fired so the manifest
                        # surface stays compact.)
                        if path2_result.get("errors"):
                            file_status.error = (file_status.error or "")
                            file_status.error += (
                                f" path2_errors: {len(path2_result['errors'])}"
                            )
                except Exception as e:
                    # Don't let Path 2 failure block Path 1 results.
                    file_status.error = (file_status.error or "")
                    file_status.error += f" path2_exception: {e}"

            file_status.status = "completed"
            file_status.processed_at = datetime.now().isoformat()
            self.stats.processed += 1
            self.stats.notes_extracted += file_status.notes_extracted
            self.stats.notes_approved += file_status.notes_approved
            self.stats.notes_rejected += file_status.notes_rejected
            self.stats.notes_review += file_status.notes_review

        except Exception as e:
            file_status.status = "failed"
            file_status.error = str(e)
            self.stats.failed += 1

        finally:
            file_status.duration_seconds = time.time() - start_time

    def _run_extraction(self, markdown: str, type_result: dict,
                        source_file: str) -> list | None:
        """Run the three-pass extraction engine on markdown text."""
        try:
            from orchestrator.tools.extraction_engine import ExtractionEngine
            engine = ExtractionEngine(call_fn=self.call_fn, config=self.config)
            result = engine.extract(markdown, type_result, source_file)
            return result.screened
        except Exception:
            return None

    def _get_endpoint(self, slot: str) -> dict | None:
        """Resolve a slot to an endpoint."""
        try:
            from orchestrator.boot import get_slot_endpoint
            return get_slot_endpoint(self.config, slot)
        except ImportError:
            return None

    def _write_to_staging(self, note):
        """Write an approved note to the staging directory."""
        title = getattr(note, "title", "Untitled")
        # Sanitize filename
        safe_title = _sanitize_filename(title)
        path = os.path.join(STAGING_DIR, f"{safe_title}.md")

        # Build note file content
        content = self._format_note_file(note)

        # Handle filename collisions
        counter = 1
        while os.path.exists(path):
            path = os.path.join(STAGING_DIR, f"{safe_title}-{counter}.md")
            counter += 1

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_to_review(self, note, gate_result):
        """Write a note to the human review queue."""
        title = getattr(note, "title", "Untitled")
        safe_title = _sanitize_filename(title)
        path = os.path.join(REVIEW_DIR, f"{safe_title}.json")

        review_data = {
            "title": title,
            "note_type": getattr(note, "note_type", ""),
            "subtype": getattr(note, "subtype", None),
            "body": getattr(note, "body", ""),
            "yaml_frontmatter": getattr(note, "yaml_frontmatter", {}),
            "relationships": getattr(note, "relationships", []),
            "source_file": getattr(note, "source_file", ""),
            "review_reasons": getattr(gate_result, "reasons", []),
            "checks": getattr(gate_result, "checks", {}),
            "status": "pending",  # pending, approved, rejected, edited
            "reviewed_at": None,
        }

        counter = 1
        while os.path.exists(path):
            path = os.path.join(REVIEW_DIR, f"{safe_title}-{counter}.json")
            counter += 1

        with open(path, "w", encoding="utf-8") as f:
            json.dump(review_data, f, indent=2)

    def _format_note_file(self, note) -> str:
        """Format a note as a vault-ready markdown file."""
        fm = getattr(note, "yaml_frontmatter", {})
        title = getattr(note, "title", "")
        body = getattr(note, "body", "")
        relationships = getattr(note, "relationships", [])

        lines = ["---"]

        # Frontmatter
        nexus = fm.get("nexus", "")
        if isinstance(nexus, list) and nexus:
            lines.append("nexus:")
            for n in nexus:
                lines.append(f"  - {n}")
        else:
            lines.append("nexus:")

        lines.append(f"type: {fm.get('type', 'working')}")

        tags = fm.get("tags", [])
        if isinstance(tags, list) and tags:
            lines.append("tags:")
            for t in tags:
                lines.append(f"  - {t}")
        else:
            lines.append("tags:")

        subtype = getattr(note, "subtype", None) or fm.get("subtype")
        if subtype:
            lines.append(f"subtype: {subtype}")

        defs = fm.get("definitions_required")
        if defs and isinstance(defs, list):
            lines.append("definitions_required:")
            for d in defs:
                lines.append(f"  - {d}")

        if relationships:
            lines.append("relationships:")
            for rel in relationships:
                lines.append(f"  - type: {rel.get('type', 'supports')}")
                lines.append(f"    target: \"{rel.get('target', '')}\"")
                lines.append(f"    confidence: {rel.get('confidence', 'medium')}")

        lines.append("---")
        lines.append("")
        lines.append(f"# {title}")
        lines.append("")
        lines.append(body)

        source = getattr(note, "source_file", "")
        if source:
            lines.append("")
            lines.append(f"**Source document:** {source}")

        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Manifest management
    # -------------------------------------------------------------------

    def _load_manifest(self):
        """Load the processing manifest from disk."""
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, "r") as f:
                self._manifest = json.load(f)
        else:
            self._manifest = {
                "created": datetime.now().isoformat(),
                "files": {},
            }

    def _save_manifest(self):
        """Save the processing manifest to disk."""
        # Update manifest with current file statuses
        if "files" not in self._manifest:
            self._manifest["files"] = {}

        for path, status in self._file_statuses.items():
            self._manifest["files"][path] = {
                "status": status.status,
                "input_type": status.input_type,
                "processed_at": status.processed_at,
                "notes_extracted": status.notes_extracted,
                "notes_approved": status.notes_approved,
                "notes_rejected": status.notes_rejected,
                "notes_review": status.notes_review,
                "error": status.error,
                "duration_seconds": status.duration_seconds,
            }

        self._manifest["last_updated"] = datetime.now().isoformat()
        self._manifest["stats"] = asdict(self.stats)

        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        with open(self.manifest_path, "w") as f:
            json.dump(self._manifest, f, indent=2)


def _sanitize_filename(title: str) -> str:
    """Sanitize a note title for use as a filename."""
    import re
    # Remove or replace problematic characters
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    safe = re.sub(r'\s+', ' ', safe).strip()
    # Limit length
    if len(safe) > 200:
        safe = safe[:200]
    return safe or "Untitled"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: batch_processor.py <input_directory> [--limit N] [--hours N]")
        print("  Process all supported documents in a directory.")
        print(f"  Supported formats: {', '.join(sorted(BatchProcessor.SUPPORTED_EXTENSIONS))}")
        print(f"  Manifest: {MANIFEST_PATH}")
        print(f"  Staging: {STAGING_DIR}")
        print(f"  Review queue: {REVIEW_DIR}")
        sys.exit(1)

    input_dir = sys.argv[1]
    file_limit = None
    time_limit = None

    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            file_limit = int(sys.argv[i + 1])
        elif arg == "--hours" and i + 1 < len(sys.argv):
            time_limit = float(sys.argv[i + 1])

    processor = BatchProcessor()
    stats = processor.process_directory(
        input_dir,
        time_limit_hours=time_limit,
        file_limit=file_limit,
    )

    print(f"\nBatch Processing Complete")
    print(f"  Files: {stats.processed} processed, {stats.failed} failed, {stats.skipped} skipped")
    print(f"  Notes: {stats.notes_extracted} extracted")
    print(f"    Approved: {stats.notes_approved}")
    print(f"    Rejected: {stats.notes_rejected}")
    print(f"    Review: {stats.notes_review}")
    print(f"  Duration: {stats.elapsed_seconds:.1f}s")
