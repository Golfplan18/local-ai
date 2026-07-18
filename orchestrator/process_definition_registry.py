"""Exact-version registry for reusable governed Process Definitions.

Registration is intentionally smaller than the future Process Library UI. It
validates one approved definition, stores that exact JSON identity immutably,
and resolves only an explicit ID/version/digest triple. Registration never
invokes or activates a capability.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import process_contracts as _contracts
except ImportError:  # pragma: no cover
    from orchestrator import process_contracts as _contracts


PROCESS_DEFINITIONS_ENV = "ORA_PROCESS_DEFINITIONS_DIR"
DEFAULT_PROCESS_DEFINITIONS_DIR = Path.home() / "ora" / "data" / "process-definitions"
_REGISTRY_LOCK = threading.RLock()


class ProcessDefinitionRegistryError(RuntimeError):
    pass


class DefinitionNotFoundError(ProcessDefinitionRegistryError):
    pass


class DefinitionVersionConflict(ProcessDefinitionRegistryError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_json(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _storage_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_root(explicit: str | os.PathLike[str] | None) -> Path:
    raw = explicit or os.environ.get(PROCESS_DEFINITIONS_ENV) or DEFAULT_PROCESS_DEFINITIONS_DIR
    root = Path(os.path.abspath(os.path.expanduser(str(raw))))
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ProcessDefinitionRegistryError(
            f"Process Definition registry root must be a real directory: {root}"
        )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_definition(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise DefinitionNotFoundError(f"registered Process Definition not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProcessDefinitionRegistryError(
            f"cannot read registered Process Definition {path}: {exc}"
        ) from exc
    return _contracts.validate_process_definition(value)


def _atomic_definition(path: Path, definition: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=False, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ProcessDefinitionRegistryError(
            f"refusing Process Definition registry write through symlink: {path}"
        )
    payload = json.dumps(definition, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


class ProcessDefinitionRegistry:
    """Immutable exact-version storage, without invocation or activation policy."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        *,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.root = _safe_root(root)
        self._now = now or _utc_now

    def _definition_dir(self, definition_id: str, *, create: bool = False) -> Path:
        directory = self.root / _storage_key(definition_id)
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ProcessDefinitionRegistryError(
                f"invalid Process Definition registry directory: {directory}"
            )
        if create:
            directory.mkdir(parents=False, exist_ok=True)
        return directory

    def _definition_path(self, definition_id: str, version: str) -> Path:
        return self._definition_dir(definition_id) / f"{_storage_key(version)}.json"

    @staticmethod
    def _ref(definition: Mapping[str, Any]) -> dict[str, str]:
        return {
            "definition_id": str(definition["definition_id"]),
            "version": str(definition["version"]),
            "digest": str(definition["digest"]),
        }

    def register(self, definition: Mapping[str, Any]) -> dict[str, Any]:
        """Register an approved exact definition, idempotently but never mutably."""

        validated = _contracts.validate_process_definition(definition)
        if validated["status"] not in {"approved", "active"}:
            raise ProcessDefinitionRegistryError(
                "only an approved or active Process Definition may be registered"
            )
        with _REGISTRY_LOCK:
            path = self._definition_dir(validated["definition_id"], create=True) / (
                f"{_storage_key(validated['version'])}.json"
            )
            idempotent = False
            if path.exists():
                existing = _read_definition(path)
                if existing != validated:
                    raise DefinitionVersionConflict(
                        "a different Process Definition already owns "
                        f"{validated['definition_id']}@{validated['version']}"
                    )
                idempotent = True
            else:
                _atomic_definition(path, validated)
        definition_ref = self._ref(validated)
        receipt = {
            "definition_ref": definition_ref,
            "registered_at": self._now(),
            "registry_locator": (
                "registry:process-definitions/"
                f"{validated['definition_id']}@{validated['version']}"
            ),
            "idempotent": idempotent,
            "activated": False,
        }
        receipt["receipt_digest"] = _digest_json(receipt)
        return receipt

    def resolve(
        self,
        definition_id: str,
        version: str,
        digest: str,
    ) -> dict[str, Any]:
        """Resolve only one exact registered identity; never select latest."""

        with _REGISTRY_LOCK:
            path = self._definition_path(definition_id, version)
            definition = _read_definition(path)
        expected = {
            "definition_id": definition_id,
            "version": version,
            "digest": digest,
        }
        if self._ref(definition) != expected:
            raise DefinitionNotFoundError(
                "no registered Process Definition matches the exact ID/version/digest"
            )
        return copy.deepcopy(definition)

    def list_definition_refs(self) -> list[dict[str, str]]:
        """Return validated exact identities for discovery, never activation state."""

        refs: list[dict[str, str]] = []
        with _REGISTRY_LOCK:
            for directory in sorted(self.root.iterdir()):
                if directory.is_symlink() or not directory.is_dir():
                    raise ProcessDefinitionRegistryError(
                        f"invalid entry in Process Definition registry: {directory}"
                    )
                for path in sorted(directory.iterdir()):
                    refs.append(self._ref(_read_definition(path)))
        return sorted(refs, key=lambda item: (item["definition_id"], item["version"]))


__all__ = [
    "DefinitionNotFoundError",
    "DefinitionVersionConflict",
    "ProcessDefinitionRegistry",
    "ProcessDefinitionRegistryError",
]
