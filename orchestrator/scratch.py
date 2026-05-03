"""Execution scratch — per-run temporary folder for milestone deliverables.

Each layered framework execution gets its own scratch folder under
~/ora/scratch/<execution-id>/. Milestone outputs are written here as the
executor advances. The folder is cleaned up after successful completion;
preserved on error so the user can inspect or resume.

Conversation logs and other persistent stores are NOT touched — only the
final framework output enters the conversation log. Intermediate milestone
deliverables stay in scratch.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

SCRATCH_ROOT = os.path.expanduser("~/ora/scratch")


@dataclass
class ScratchSession:
    """Per-execution scratch folder. Use ScratchSession.create() to instantiate."""
    execution_id: str
    framework_name: str
    folder: str
    started_at: float = field(default_factory=time.time)
    manifest_path: str = ""

    @classmethod
    def create(cls, framework_name: str, execution_id: Optional[str] = None) -> "ScratchSession":
        """Create a new scratch session folder."""
        if execution_id is None:
            execution_id = _new_execution_id()
        folder = os.path.join(SCRATCH_ROOT, execution_id)
        os.makedirs(folder, exist_ok=True)
        sess = cls(
            execution_id=execution_id,
            framework_name=framework_name,
            folder=folder,
            manifest_path=os.path.join(folder, "manifest.json"),
        )
        sess._write_manifest({
            "execution_id": execution_id,
            "framework_name": framework_name,
            "started_at": sess.started_at,
            "status": "running",
            "milestones_completed": [],
        })
        return sess

    @classmethod
    def attach(cls, execution_id: str) -> "ScratchSession":
        """Attach to an existing scratch session for resume / inspection."""
        folder = os.path.join(SCRATCH_ROOT, execution_id)
        manifest_path = os.path.join(folder, "manifest.json")
        if not os.path.isdir(folder):
            raise FileNotFoundError(f"No scratch session at {folder}")
        with open(manifest_path) as f:
            manifest = json.load(f)
        return cls(
            execution_id=execution_id,
            framework_name=manifest.get("framework_name", "<unknown>"),
            folder=folder,
            started_at=manifest.get("started_at", time.time()),
            manifest_path=manifest_path,
        )

    # ---------- Read / write milestone deliverables ----------

    def write_milestone(self, milestone_id: str, content: str) -> str:
        """Write a milestone deliverable. Returns the file path."""
        path = self._milestone_path(milestone_id)
        with open(path, "w") as f:
            f.write(content)
        # Update manifest
        manifest = self._read_manifest()
        if milestone_id not in manifest.get("milestones_completed", []):
            manifest.setdefault("milestones_completed", []).append(milestone_id)
        self._write_manifest(manifest)
        return path

    def read_milestone(self, milestone_id: str) -> str:
        """Read a previously written milestone deliverable."""
        path = self._milestone_path(milestone_id)
        with open(path) as f:
            return f.read()

    def has_milestone(self, milestone_id: str) -> bool:
        """Check whether a milestone has been written."""
        return os.path.isfile(self._milestone_path(milestone_id))

    def read_all_prior(self, milestone_ids: list[str]) -> dict[str, str]:
        """Read multiple prior milestone deliverables. Returns dict keyed by id.
        Missing milestones are silently omitted from the returned dict."""
        out = {}
        for mid in milestone_ids:
            if self.has_milestone(mid):
                out[mid] = self.read_milestone(mid)
        return out

    # ---------- Lifecycle ----------

    def mark_failed(self, milestone_id: str, reason: str) -> None:
        """Record a failure in the manifest. Does NOT delete the folder."""
        manifest = self._read_manifest()
        manifest["status"] = "failed"
        manifest["failed_at"] = time.time()
        manifest["failed_milestone"] = milestone_id
        manifest["failure_reason"] = reason
        self._write_manifest(manifest)

    def mark_complete(self) -> None:
        """Mark the session as successfully completed."""
        manifest = self._read_manifest()
        manifest["status"] = "complete"
        manifest["completed_at"] = time.time()
        self._write_manifest(manifest)

    def cleanup(self) -> None:
        """Delete the scratch folder. Call after successful completion when
        intermediate outputs are no longer needed."""
        if os.path.isdir(self.folder):
            shutil.rmtree(self.folder)

    # ---------- Internal ----------

    def _milestone_path(self, milestone_id: str) -> str:
        # Sanitize: only alphanumeric + dot + dash + underscore allowed
        safe = "".join(c for c in milestone_id if c.isalnum() or c in "._-")
        return os.path.join(self.folder, f"milestone-{safe}.md")

    def _read_manifest(self) -> dict:
        if not os.path.isfile(self.manifest_path):
            return {}
        with open(self.manifest_path) as f:
            return json.load(f)

    def _write_manifest(self, manifest: dict) -> None:
        with open(self.manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)


def _new_execution_id() -> str:
    """Return a new execution id: timestamp + short uuid."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{ts}-{short}"


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    sess = ScratchSession.create("smoke-test")
    print(f"Created scratch session at {sess.folder}")
    sess.write_milestone("M1", "First milestone deliverable.\n\nContent goes here.")
    sess.write_milestone("M2", "Second milestone.\n\nDepends on M1.")
    print(f"  has_milestone M1: {sess.has_milestone('M1')}")
    print(f"  has_milestone M3: {sess.has_milestone('M3')}")
    prior = sess.read_all_prior(["M1", "M2", "M3"])
    print(f"  read_all_prior keys: {list(prior.keys())}")
    sess.mark_complete()
    sess.cleanup()
    print(f"  cleaned up; folder exists: {os.path.isdir(sess.folder)}")
