"""Exact-version registry for reusable governed Process Definitions.

Registration is intentionally smaller than the future Process Library UI. It
validates one approved definition, preserves its issued identity, authenticates
the stored JSON through a separate registry envelope, and resolves only an
explicit ID/version/digest triple. Registration never invokes or activates a
capability.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
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
REGISTRY_ENTRY_SCHEMA_VERSION = "ora.process-definition-registry-entry/1.0"
REGISTRATION_ANCHOR_SCHEMA_VERSION = "ora.process-definition-registration-anchor/1.0"
REGISTRATION_ANCHOR_DIRECTORY = ".registration-anchors"
_REGISTRY_LOCK = threading.RLock()


class ProcessDefinitionRegistryError(RuntimeError):
    pass


class DefinitionNotFoundError(ProcessDefinitionRegistryError):
    pass


class DefinitionVersionConflict(ProcessDefinitionRegistryError):
    pass


class DefinitionIntegrityError(ProcessDefinitionRegistryError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_json(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


_SELF_DIGEST_PLACEHOLDER = "sha256:" + ("0" * 64)


def _normalized_definition_content(
    definition: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the canonical content covered by a Process Definition digest.

    The three fields which carry the definition's own digest are replaced by
    one fixed placeholder to avoid an impossible self-referential hash. Every
    other field, including the graph and package-member identities, remains in
    the canonical JSON coverage.
    """

    normalized = copy.deepcopy(dict(definition))
    normalized["digest"] = _SELF_DIGEST_PLACEHOLDER
    manifest = normalized["package_manifest"]
    manifest["definition_ref"]["digest"] = _SELF_DIGEST_PLACEHOLDER
    entry_member_id = manifest["entry_member_id"]
    entry_member = next(
        member
        for member in manifest["members"]
        if member["member_id"] == entry_member_id
    )
    entry_member["identity"]["digest"] = _SELF_DIGEST_PLACEHOLDER
    return normalized


def process_definition_content_digest(definition: Mapping[str, Any]) -> str:
    """Compute the issued normalized-JSON identity for a definition.

    An already-issued definition may instead carry a digest of its canonical
    source body. The registry selects that canonical verification only when the
    entry member explicitly declares complete-canonical-body coverage.
    """

    validated = _contracts.validate_process_definition(definition)
    return _digest_json(_normalized_definition_content(validated))


def _storage_entry(definition: Mapping[str, Any]) -> dict[str, Any]:
    definition_copy = copy.deepcopy(dict(definition))
    return {
        "schema_version": REGISTRY_ENTRY_SCHEMA_VERSION,
        "definition": definition_copy,
        "storage_content_digest": _digest_json(definition_copy),
    }


def _definition_ref(definition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(definition["definition_id"]),
        "version": str(definition["version"]),
        "digest": str(definition["digest"]),
    }


def _registration_anchor(
    definition: Mapping[str, Any], storage_content_digest: str
) -> dict[str, Any]:
    return {
        "schema_version": REGISTRATION_ANCHOR_SCHEMA_VERSION,
        "definition_ref": _definition_ref(definition),
        "storage_content_digest": storage_content_digest,
    }


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


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise DefinitionNotFoundError(f"registered {label} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProcessDefinitionRegistryError(
            f"cannot read registered {label} {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise DefinitionIntegrityError(f"registered {label} must be a JSON object")
    return value


def _read_storage_entry(path: Path) -> dict[str, Any]:
    entry = _read_json_object(path, "Process Definition")
    if set(entry) != {
        "schema_version", "definition", "storage_content_digest"
    }:
        raise DefinitionIntegrityError(
            "registered Process Definition lacks its authenticated storage envelope"
        )
    if entry["schema_version"] != REGISTRY_ENTRY_SCHEMA_VERSION:
        raise DefinitionIntegrityError(
            "registered Process Definition storage envelope version is unsupported"
        )
    definition = entry["definition"]
    computed = _digest_json(definition)
    if entry["storage_content_digest"] != computed:
        raise DefinitionIntegrityError(
            "registered Process Definition storage content digest mismatch"
        )
    return entry


def _read_registration_anchor(path: Path) -> dict[str, Any]:
    anchor = _read_json_object(path, "Process Definition registration anchor")
    if set(anchor) != {
        "schema_version", "definition_ref", "storage_content_digest"
    }:
        raise DefinitionIntegrityError(
            "registered Process Definition anchor has an invalid shape"
        )
    if anchor["schema_version"] != REGISTRATION_ANCHOR_SCHEMA_VERSION:
        raise DefinitionIntegrityError(
            "registered Process Definition anchor version is unsupported"
        )
    return anchor


def _read_definition(path: Path, anchor: Mapping[str, Any]) -> dict[str, Any]:
    entry = _read_storage_entry(path)
    if entry["storage_content_digest"] != anchor.get("storage_content_digest"):
        raise DefinitionIntegrityError(
            "registered Process Definition differs from its immutable registration anchor"
        )
    return _contracts.validate_process_definition(entry["definition"])


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
        self._anchor_root = self.root / REGISTRATION_ANCHOR_DIRECTORY
        if self._anchor_root.exists() and (
            self._anchor_root.is_symlink() or not self._anchor_root.is_dir()
        ):
            raise ProcessDefinitionRegistryError(
                "Process Definition registration-anchor root must be a real directory"
            )
        self._anchor_root.mkdir(parents=False, exist_ok=True)
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

    def _anchor_dir(self, definition_id: str, *, create: bool = False) -> Path:
        directory = self._anchor_root / _storage_key(definition_id)
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ProcessDefinitionRegistryError(
                f"invalid Process Definition anchor directory: {directory}"
            )
        if create:
            directory.mkdir(parents=False, exist_ok=True)
        return directory

    def _anchor_path(self, definition_id: str, version: str) -> Path:
        return self._anchor_dir(definition_id) / f"{_storage_key(version)}.json"

    @staticmethod
    def _ref(definition: Mapping[str, Any]) -> dict[str, str]:
        return _definition_ref(definition)

    @staticmethod
    def _verify_issued_content_identity(definition: Mapping[str, Any]) -> None:
        manifest = definition["package_manifest"]
        entry_member = next(
            member
            for member in manifest["members"]
            if member["member_id"] == manifest["entry_member_id"]
        )
        coverage = set(entry_member["identity"]["coverage"])
        if "complete_canonical_body" not in coverage:
            calculated = process_definition_content_digest(definition)
            if calculated != definition["digest"]:
                raise DefinitionIntegrityError(
                    "normalized content digest does not match the issued "
                    "Process Definition identity"
                )
            return
        locator = entry_member["locator"]
        if locator["kind"] != "file":
            raise DefinitionIntegrityError(
                "canonical-body identity requires a file locator"
            )
        vault_root = Path(
            os.environ.get("ORA_VAULT_PATH")
            or os.environ.get("ORA_VAULT")
            or (Path.home() / "Documents" / "vault")
        ).resolve()
        raw_ref = Path(str(locator["ref"]))
        canonical_path = (
            raw_ref.resolve()
            if raw_ref.is_absolute()
            else (vault_root / raw_ref).resolve()
        )
        try:
            canonical_path.relative_to(vault_root)
        except ValueError as exc:
            raise DefinitionIntegrityError(
                "canonical Process Definition locator escapes the vault root"
            ) from exc
        if not canonical_path.is_file() or canonical_path.is_symlink():
            raise DefinitionIntegrityError(
                f"authoritative canonical Process Definition is unavailable: {canonical_path}"
            )
        canonical_body = canonical_path.read_text(encoding="utf-8")
        if canonical_body.startswith("---\n"):
            _frontmatter, separator, canonical_body = canonical_body[4:].partition(
                "\n---\n"
            )
            if not separator:
                raise DefinitionIntegrityError(
                    "authoritative canonical Process Definition has invalid frontmatter"
                )
        canonical_body = canonical_body.lstrip("\n").rstrip()
        declared = str(definition["digest"])
        normalized = canonical_body.replace(declared, _SELF_DIGEST_PLACEHOLDER)
        calculated = "sha256:" + hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()
        if calculated != declared:
            raise DefinitionIntegrityError(
                "authoritative canonical Process Definition digest does not match "
                "the issued identity"
            )
        if "embedded_kernel_projection" in coverage:
            match = re.search(
                r"<!-- PROGRAMMING_PROCESS_DEFINITION_BEGIN -->\n"
                r"```json\n(.*?)\n```\n"
                r"<!-- PROGRAMMING_PROCESS_DEFINITION_END -->",
                canonical_body,
                flags=re.DOTALL,
            )
            if match is None:
                raise DefinitionIntegrityError(
                    "authoritative canonical body lacks its embedded kernel projection"
                )
            try:
                projected = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise DefinitionIntegrityError(
                    "authoritative embedded kernel projection is invalid JSON"
                ) from exc
            if projected != definition:
                raise DefinitionIntegrityError(
                    "registered Process Definition differs from the authoritative "
                    "canonical projection"
                )

    def _load_registered_definition(
        self, definition_id: str, version: str
    ) -> dict[str, Any]:
        try:
            anchor = _read_registration_anchor(
                self._anchor_path(definition_id, version)
            )
        except DefinitionNotFoundError as exc:
            raise DefinitionIntegrityError(
                "registered Process Definition lacks its independent registration anchor"
            ) from exc
        definition = _read_definition(
            self._definition_path(definition_id, version), anchor
        )
        if self._ref(definition) != anchor["definition_ref"]:
            raise DefinitionIntegrityError(
                "registered Process Definition identity differs from its registration anchor"
            )
        self._verify_issued_content_identity(definition)
        return definition

    def register(self, definition: Mapping[str, Any]) -> dict[str, Any]:
        """Register an approved exact definition, idempotently but never mutably."""

        validated = _contracts.validate_process_definition(definition)
        self._verify_issued_content_identity(validated)
        storage_entry = _storage_entry(validated)
        registration_anchor = _registration_anchor(
            validated, storage_entry["storage_content_digest"]
        )
        if validated["status"] not in {"approved", "active"}:
            raise ProcessDefinitionRegistryError(
                "only an approved or active Process Definition may be registered"
            )
        with _REGISTRY_LOCK:
            path = self._definition_dir(validated["definition_id"], create=True) / (
                f"{_storage_key(validated['version'])}.json"
            )
            anchor_path = self._anchor_dir(
                validated["definition_id"], create=True
            ) / f"{_storage_key(validated['version'])}.json"
            idempotent = False
            if path.exists() != anchor_path.exists():
                raise DefinitionIntegrityError(
                    "Process Definition and registration-anchor presence differ"
                )
            if path.exists():
                existing = self._load_registered_definition(
                    validated["definition_id"], validated["version"]
                )
                if existing != validated:
                    raise DefinitionVersionConflict(
                        "a different Process Definition already owns "
                        f"{validated['definition_id']}@{validated['version']}"
                    )
                idempotent = True
            else:
                _atomic_definition(path, storage_entry)
                _atomic_definition(anchor_path, registration_anchor)
                os.chmod(anchor_path, 0o444)
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
            "storage_content_digest": storage_entry["storage_content_digest"],
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
            definition = self._load_registered_definition(definition_id, version)
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
                if directory == self._anchor_root:
                    continue
                if directory.is_symlink() or not directory.is_dir():
                    raise ProcessDefinitionRegistryError(
                        f"invalid entry in Process Definition registry: {directory}"
                    )
                for path in sorted(directory.iterdir()):
                    entry = _read_storage_entry(path)
                    raw_definition = entry["definition"]
                    if not isinstance(raw_definition, dict):
                        raise DefinitionIntegrityError(
                            "registered Process Definition body must be a JSON object"
                        )
                    definition_id = str(raw_definition.get("definition_id") or "")
                    version = str(raw_definition.get("version") or "")
                    if path != self._definition_path(definition_id, version):
                        raise DefinitionIntegrityError(
                            "registered Process Definition storage path does not match "
                            "its declared identity"
                        )
                    refs.append(
                        self._ref(
                            self._load_registered_definition(definition_id, version)
                        )
                    )
        return sorted(refs, key=lambda item: (item["definition_id"], item["version"]))


__all__ = [
    "DefinitionIntegrityError",
    "DefinitionNotFoundError",
    "DefinitionVersionConflict",
    "ProcessDefinitionRegistry",
    "ProcessDefinitionRegistryError",
    "process_definition_content_digest",
]
