"""Temporary, resumable state for milestone-bounded Framework execution.

Normal successful runs remove their scratch after the final output and
synchronous events are safe. Normal failures keep the minimum state needed
to inspect completed work and resume at the first unfinished milestone.
Stealth runs never retain scratch; the recorded conversation identity lets
conversation closeout remove orphaned scratch if a process dies first.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import runtime_paths as _rp


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _scratch_root() -> Path:
    return Path(_rp.SCRATCH_DIR_STR)


def _session_folder(execution_id: str) -> Path:
    if not isinstance(execution_id, str) or not _SAFE_ID.fullmatch(execution_id):
        raise ValueError(f"invalid Framework execution id: {execution_id!r}")
    root = _scratch_root()
    folder = root / execution_id
    if not _rp.within_base(folder, root) or folder == root:
        raise ValueError("Framework scratch path escapes the configured root")
    return folder


@dataclass
class ScratchSession:
    """One Framework execution's temporary working folder."""

    execution_id: str
    framework_name: str
    folder: str
    started_at: float = field(default_factory=time.time)
    manifest_path: str = ""

    @classmethod
    def create(
        cls,
        framework_name: str,
        execution_id: Optional[str] = None,
        *,
        conversation_id: Optional[str] = None,
        conversation_tag: str = "",
    ) -> "ScratchSession":
        """Create a new scratch session without replacing an existing run."""
        execution_id = execution_id or _new_execution_id()
        root = _scratch_root()
        root.mkdir(parents=True, exist_ok=True)
        folder_path = _session_folder(execution_id)
        folder_path.mkdir()
        sess = cls(
            execution_id=execution_id,
            framework_name=framework_name,
            folder=str(folder_path),
            manifest_path=str(folder_path / "manifest.json"),
        )
        try:
            sess._write_manifest({
                "schema_version": 2,
                "execution_id": execution_id,
                "framework_name": framework_name,
                "started_at": sess.started_at,
                "status": "running",
                "terminal_state": "running",
                "conversation_id": conversation_id or None,
                "conversation_tag": conversation_tag or "",
                "milestones_completed": [],
                "milestone_results": {},
            })
        except BaseException:
            if folder_path.is_dir() and not folder_path.is_symlink():
                shutil.rmtree(folder_path)
            raise
        return sess

    @classmethod
    def attach(cls, execution_id: str) -> "ScratchSession":
        """Attach to an existing normal-run scratch session for resume."""
        folder_path = _session_folder(execution_id)
        manifest_path = folder_path / "manifest.json"
        if not folder_path.is_dir() or folder_path.is_symlink():
            raise FileNotFoundError(f"No scratch session at {folder_path}")
        with open(manifest_path, encoding="utf-8") as stream:
            manifest = json.load(stream)
        if not isinstance(manifest, dict):
            raise ValueError("Framework scratch manifest is not an object")
        if manifest.get("execution_id") != execution_id:
            raise ValueError("Framework scratch manifest identity mismatch")
        return cls(
            execution_id=execution_id,
            framework_name=manifest.get("framework_name", "<unknown>"),
            folder=str(folder_path),
            started_at=manifest.get("started_at", time.time()),
            manifest_path=str(manifest_path),
        )

    # ---------- Run identity / resume ----------

    def record_run(self, **fields: Any) -> None:
        """Add the admitted run identity needed for a truthful resume."""
        manifest = self._read_manifest()
        manifest.update(fields)
        self._write_manifest(manifest)

    def manifest(self) -> dict:
        return self._read_manifest()

    def completed_milestone_ids(self) -> tuple[str, ...]:
        values = self._read_manifest().get("milestones_completed") or []
        return tuple(value for value in values if isinstance(value, str))

    def milestone_result_metadata(self, milestone_id: str) -> dict:
        results = self._read_manifest().get("milestone_results") or {}
        value = results.get(milestone_id) if isinstance(results, dict) else None
        return dict(value) if isinstance(value, dict) else {}

    def mark_resumed(self) -> None:
        manifest = self._read_manifest()
        manifest["status"] = "running"
        manifest["terminal_state"] = "running"
        manifest["resumed_at"] = time.time()
        manifest["resume_count"] = int(manifest.get("resume_count") or 0) + 1
        for key in ("failed_at", "failed_milestone", "failure_reason"):
            manifest.pop(key, None)
        self._write_manifest(manifest)

    # ---------- Read / write milestone deliverables ----------

    def write_milestone(
        self,
        milestone_id: str,
        content: str,
        *,
        result_metadata: Optional[dict] = None,
    ) -> str:
        """Persist one accepted milestone and mark it completed."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("accepted milestone content must be nonempty text")
        path = self.milestone_path(milestone_id)
        _rp.atomic_write_text(path, content)
        manifest = self._read_manifest()
        if milestone_id not in manifest.get("milestones_completed", []):
            manifest.setdefault("milestones_completed", []).append(milestone_id)
        metadata = dict(result_metadata or {})
        if metadata:
            manifest.setdefault("milestone_results", {})[milestone_id] = metadata
        self._write_manifest(manifest)
        return path

    def write_unaccepted_candidate(self, milestone_id: str, content: str) -> str:
        """Preserve a material failed/degraded candidate without completing it."""
        if not isinstance(content, str) or not content.strip():
            return ""
        path = self.candidate_path(milestone_id)
        _rp.atomic_write_text(path, content)
        return path

    def write_final_output(self, content: str) -> str:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("final Framework output must be nonempty text")
        path = str(Path(self.folder) / "final-output.md")
        _rp.atomic_write_text(path, content)
        return path

    def read_milestone(self, milestone_id: str) -> str:
        with open(self.milestone_path(milestone_id), encoding="utf-8") as stream:
            return stream.read()

    def has_milestone(self, milestone_id: str) -> bool:
        return os.path.isfile(self.milestone_path(milestone_id))

    def read_all_prior(
        self, milestone_ids: list[str] | tuple[str, ...],
    ) -> dict[str, str]:
        out = {}
        for milestone_id in milestone_ids:
            if self.has_milestone(milestone_id):
                out[milestone_id] = self.read_milestone(milestone_id)
        return out

    def milestone_path(self, milestone_id: str) -> str:
        return str(Path(self.folder) / f"milestone-{_safe_milestone_id(milestone_id)}.md")

    def candidate_path(self, milestone_id: str) -> str:
        return str(
            Path(self.folder)
            / f"milestone-{_safe_milestone_id(milestone_id)}-unaccepted.md"
        )

    # ---------- Lifecycle ----------

    def mark_failed(
        self,
        milestone_id: str,
        reason: str,
        *,
        terminal_state: str = "failed",
    ) -> None:
        manifest = self._read_manifest()
        manifest["status"] = "failed"
        manifest["terminal_state"] = terminal_state
        manifest["failed_at"] = time.time()
        manifest["failed_milestone"] = milestone_id
        manifest["failure_reason"] = reason
        self._write_manifest(manifest)

    def mark_complete(self) -> None:
        manifest = self._read_manifest()
        manifest["status"] = "complete"
        manifest["terminal_state"] = "succeeded"
        manifest["completed_at"] = time.time()
        self._write_manifest(manifest)

    def cleanup(self) -> None:
        """Delete only this validated execution folder."""
        folder = _session_folder(self.execution_id)
        if folder.is_symlink():
            folder.unlink()
        elif folder.is_dir():
            shutil.rmtree(folder)

    # ---------- Internal ----------

    def _read_manifest(self) -> dict:
        if not os.path.isfile(self.manifest_path):
            return {}
        with open(self.manifest_path, encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("Framework scratch manifest is not an object")
        return value

    def _write_manifest(self, manifest: dict) -> None:
        payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        _rp.atomic_write_text(self.manifest_path, payload)


def purge_conversation_scratch(conversation_id: str) -> dict[str, Any]:
    """Delete orphaned Framework scratch owned by one Stealth conversation."""
    removed: list[str] = []
    errors: list[str] = []
    root = _scratch_root()
    if not root.exists():
        return {"removed": removed, "errors": errors}
    if root.is_symlink() or not root.is_dir():
        return {
            "removed": removed,
            "errors": [f"Framework scratch root is not a regular directory: {root}"],
        }
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.is_symlink() or not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        try:
            with open(manifest_path, encoding="utf-8") as stream:
                manifest = json.load(stream)
            if not isinstance(manifest, dict):
                continue
            if manifest.get("conversation_id") != conversation_id:
                continue
            if manifest.get("conversation_tag") != "stealth":
                continue
            execution_id = manifest.get("execution_id")
            if execution_id != child.name:
                raise ValueError("manifest execution id does not match folder")
            ScratchSession.attach(execution_id).cleanup()
            removed.append(execution_id)
        except FileNotFoundError:
            continue
        except Exception as exc:
            errors.append(f"{child}: {type(exc).__name__}: {exc}")
    return {"removed": removed, "errors": errors}


def _safe_milestone_id(milestone_id: str) -> str:
    safe = "".join(
        character
        for character in str(milestone_id)
        if character.isalnum() or character in "._-"
    )
    if not safe:
        raise ValueError("milestone id has no safe filename characters")
    return safe


def _new_execution_id() -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{ts}-{short}"


__all__ = ["ScratchSession", "purge_conversation_scratch"]
