"""G1.1 Phase 2.6 — exact Process Library and terminal Run lifecycle.

The Process Definition registry remains immutable exact-version storage. This
service adds no marketplace and no standing automation. It projects registry
entries for discovery, enforces project/universal scope for manual invocation,
and treats one authenticated terminal Run disposition as the only source of
promotion authority. Promotion makes an accepted registered definition
available for manual invocation; it never creates triggers or deployment.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from active_project import canonicalize_project_nexus
    from governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
        TERMINAL_RUN_STATES,
    )
    from process_definition_registry import (
        DEFAULT_PROCESS_DEFINITIONS_DIR,
        PROCESS_DEFINITIONS_ENV,
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
    )
except ImportError:  # pragma: no cover
    from orchestrator.active_project import canonicalize_project_nexus
    from orchestrator.governed_process_runtime import (
        AuthorityDeniedError,
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunConflictError,
        RunNotFoundError,
        TERMINAL_RUN_STATES,
    )
    from orchestrator.process_definition_registry import (
        DEFAULT_PROCESS_DEFINITIONS_DIR,
        PROCESS_DEFINITIONS_ENV,
        ProcessDefinitionRegistry,
        ProcessDefinitionRegistryError,
    )


LIBRARY_SCHEMA_VERSION = "ora.process-library/1.0"
LIFECYCLE_SCHEMA_VERSION = "ora.process-lifecycle-disposition/1.0"
LIFECYCLE_DISPOSITIONS = ("promote", "preserve", "archive", "discard")
_OUTPUT_ROLES = frozenset({"working", "result", "process_definition"})


class ProcessLibraryError(RuntimeError):
    """The Process Library request cannot be completed."""


class ProcessLibraryInputRequired(ProcessLibraryError):
    """An exact user choice or identity is required."""


class ProcessLibraryConflict(ProcessLibraryError):
    """The requested lifecycle action conflicts with persisted state."""


class ProcessLibraryIntegrityError(ProcessLibraryError):
    """A registry, Run, Artifact, or lifecycle identity does not authenticate."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    return _digest_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def _definition_ref(definition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(definition["definition_id"]),
        "version": str(definition["version"]),
        "digest": str(definition["digest"]),
    }


def _normalize_ref(value: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "definition_id", "version", "digest",
    }:
        raise ProcessLibraryInputRequired(
            "definition_ref must contain exact definition_id, version, and digest"
        )
    ref = {field: str(value[field] or "").strip() for field in value}
    if not ref["definition_id"] or not ref["version"]:
        raise ProcessLibraryInputRequired("definition_ref values must be non-empty")
    if (
        len(ref["digest"]) != 71
        or not ref["digest"].startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in ref["digest"][7:])
    ):
        raise ProcessLibraryInputRequired(
            "definition_ref digest must be an exact lowercase sha256 identity"
        )
    return ref


def _canonical_definition_artifact_digest(definition: Mapping[str, Any]) -> str:
    """Identity required for a complete inline Process Definition Artifact."""

    return _digest_text(
        json.dumps(definition, sort_keys=True, ensure_ascii=False)
    )


class ProcessLibraryLifecycleService:
    """Restart-derived library discovery and one-time Run closure service."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        registry: ProcessDefinitionRegistry | None = None,
        registry_root: str | Path | None = None,
        seed_definitions: Sequence[Mapping[str, Any]] = (),
        now: Callable[[], str] | None = None,
    ) -> None:
        self.runtime = runtime or GovernedProcessRuntime()
        self.registry = registry
        self.registry_root = Path(
            registry_root
            or os.environ.get(PROCESS_DEFINITIONS_ENV)
            or DEFAULT_PROCESS_DEFINITIONS_DIR
        ).expanduser().resolve()
        self.seed_definitions = [copy.deepcopy(dict(item)) for item in seed_definitions]
        self._now = now or _utc_now

    def _registry_for_read(self) -> ProcessDefinitionRegistry | None:
        if self.registry is not None:
            return self.registry
        if not self.registry_root.exists():
            return None
        if self.registry_root.is_symlink() or not self.registry_root.is_dir():
            raise ProcessLibraryIntegrityError(
                "Process Definition registry root is not a real directory"
            )
        if not any(self.registry_root.iterdir()):
            return None
        anchor_root = self.registry_root / ".registration-anchors"
        if not anchor_root.is_dir() or anchor_root.is_symlink():
            raise ProcessLibraryIntegrityError(
                "Process Definition registry lacks its independent anchor root"
            )
        self.registry = ProcessDefinitionRegistry(self.registry_root)
        return self.registry

    def _registry_required(self) -> ProcessDefinitionRegistry:
        if self.registry is None:
            self.registry = ProcessDefinitionRegistry(self.registry_root)
        return self.registry

    def _validated_seed_definitions(self) -> list[dict[str, Any]]:
        validated = []
        for definition in self.seed_definitions:
            try:
                ProcessDefinitionRegistry._verify_issued_content_identity(definition)
            except (KeyError, ProcessDefinitionRegistryError) as exc:
                raise ProcessLibraryIntegrityError(
                    "Process Library seed definition could not be authenticated"
                ) from exc
            validated.append(copy.deepcopy(definition))
        return validated

    def _iter_runs(self) -> list[dict[str, Any]]:
        if not self.runtime.root.exists():
            return []
        runs: list[dict[str, Any]] = []
        for entry in sorted(self.runtime.root.iterdir()):
            if entry.is_symlink() or not entry.is_dir():
                raise ProcessLibraryIntegrityError(
                    f"invalid Process Run storage entry: {entry}"
                )
            run_path = entry / "run.json"
            if not run_path.is_file() or run_path.is_symlink():
                raise ProcessLibraryIntegrityError(
                    f"Process Run storage entry lacks a real run.json: {entry}"
                )
            try:
                raw = json.loads(run_path.read_text(encoding="utf-8"))
                run = self.runtime.load_run(str(raw["run_id"]))
            except (OSError, KeyError, ValueError, json.JSONDecodeError,
                    GovernedRuntimeError) as exc:
                raise ProcessLibraryIntegrityError(
                    f"Process Run storage integrity failed at {entry}"
                ) from exc
            if entry != self.runtime._run_dir(run["run_id"]):
                raise ProcessLibraryIntegrityError(
                    "Process Run storage path differs from its declared identity"
                )
            runs.append(run)
        return runs

    def _output_bindings(self, run: Mapping[str, Any]) -> list[dict[str, Any]]:
        bindings = []
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
            if artifact["role"] not in _OUTPUT_ROLES:
                continue
            bindings.append({
                "artifact_id": artifact["artifact_id"],
                "role": artifact["role"],
                "identity_digest": artifact["identity"]["digest"],
                "recorded_status": artifact["status"],
            })
        return sorted(bindings, key=lambda item: item["artifact_id"])

    def _accepted_linked_result(
        self,
        run: Mapping[str, Any],
        capability_artifact_id: str,
    ) -> dict[str, Any] | None:
        requirements = [
            item for item in run["contracts"]["evidence"]["requirements"]
            if item["required"]
        ]
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
            if (
                artifact["role"] != "result"
                or capability_artifact_id
                not in artifact["lineage"]["source_artifact_ids"]
            ):
                continue
            try:
                for requirement in requirements:
                    self.runtime._current_passing_review(
                        run["run_id"], artifact["artifact_id"],
                        requirement["evidence_id"],
                    )
            except GovernedRuntimeError:
                continue
            return artifact
        return None

    def _promotion_binding(
        self,
        run: Mapping[str, Any],
        definition_ref: Mapping[str, Any],
        capability_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        ref = _normalize_ref(definition_ref)
        registry = self._registry_required()
        try:
            definition = registry.resolve(
                ref["definition_id"], ref["version"], ref["digest"]
            )
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryInputRequired(
                "promotion requires an exact registered Process Definition"
            ) from exc
        expected_digest = _canonical_definition_artifact_digest(definition)
        matches = []
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
            if artifact["role"] != "process_definition":
                continue
            if capability_artifact_id and artifact_id != capability_artifact_id:
                continue
            if (
                artifact["identity"]["kind"] == "content_digest"
                and artifact["identity"]["digest"] == expected_digest
                and "complete_content" in artifact["identity"]["coverage"]
            ):
                matches.append(artifact)
        if len(matches) != 1:
            raise ProcessLibraryInputRequired(
                "promotion requires one exact content-bound Process Definition Artifact"
            )
        capability = matches[0]
        accepted_result = self._accepted_linked_result(
            run, capability["artifact_id"]
        )
        if accepted_result is None:
            raise ProcessLibraryInputRequired(
                "promotion requires a currently accepted result derived from the "
                "exact Process Definition Artifact"
            )
        return {
            "definition": definition,
            "definition_ref": ref,
            "capability_artifact": capability,
            "accepted_result": accepted_result,
        }

    def _validate_lifecycle_record(
        self,
        run: Mapping[str, Any],
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        event = record.get("event") or {}
        details = event.get("details") or {}
        required = {
            "schema_version", "disposition", "decision_by", "idempotency_key",
            "terminal_state", "terminal_record_id", "terminal_sequence",
            "output_bindings", "output_bindings_digest",
            "promoted_definition_ref", "capability_artifact_id",
        }
        if (
            record.get("record_type") != "event"
            or event.get("event_type") != "lifecycle_disposition_recorded"
            or set(details) != required
            or details.get("schema_version") != LIFECYCLE_SCHEMA_VERSION
            or details.get("disposition") not in LIFECYCLE_DISPOSITIONS
            or details.get("decision_by")
            != run["contracts"]["authority"]["principal_id"]
            or details.get("terminal_state") != run["state"]
            or run["state"] not in TERMINAL_RUN_STATES
        ):
            raise ProcessLibraryIntegrityError(
                "Run lifecycle disposition has an invalid authority or terminal binding"
            )
        records = self.runtime.load_records(run["run_id"])
        terminal = next(
            (
                item for item in records
                if item["record_id"] == details["terminal_record_id"]
            ),
            None,
        )
        bindings = self._output_bindings(run)
        if (
            terminal is None
            or terminal.get("record_type") != "transition"
            or (terminal.get("transition") or {}).get("to_state") != run["state"]
            or terminal["sequence"] != details.get("terminal_sequence")
            or details.get("output_bindings") != bindings
            or details.get("output_bindings_digest") != _digest_json(bindings)
            or record.get("artifact_ids")
            != [item["artifact_id"] for item in bindings]
            or record.get("evidence_refs") != terminal.get("evidence_refs")
        ):
            raise ProcessLibraryIntegrityError(
                "Run lifecycle disposition differs from its terminal or Artifact identity"
            )
        promotion = None
        if details["disposition"] == "promote":
            if run["state"] != "completed":
                raise ProcessLibraryIntegrityError(
                    "non-completed Run contains a promotion disposition"
                )
            try:
                promotion = self._promotion_binding(
                    run,
                    details.get("promoted_definition_ref"),
                    str(details.get("capability_artifact_id") or ""),
                )
            except ProcessLibraryError as exc:
                raise ProcessLibraryIntegrityError(
                    "persisted promotion no longer authenticates its exact capability"
                ) from exc
        elif (
            details.get("promoted_definition_ref") is not None
            or details.get("capability_artifact_id") is not None
        ):
            raise ProcessLibraryIntegrityError(
                "non-promotion lifecycle disposition carries promotion authority"
            )
        closure = {
            "record_id": record["record_id"],
            "sequence": record["sequence"],
            "recorded_at": record["recorded_at"],
            **copy.deepcopy(dict(details)),
            "effective_artifacts": [
                {
                    **binding,
                    "lifecycle_status": (
                        "promoted"
                        if details["disposition"] == "promote"
                        and binding["artifact_id"]
                        == details["capability_artifact_id"]
                        else {
                            "promote": "preserved",
                            "preserve": "preserved",
                            "archive": "archived",
                            "discard": "discarded",
                        }[details["disposition"]]
                    ),
                }
                for binding in bindings
            ],
        }
        if promotion is not None:
            closure["accepted_result_artifact_id"] = promotion[
                "accepted_result"
            ]["artifact_id"]
        return closure

    def _run_closure(self, run: Mapping[str, Any]) -> dict[str, Any] | None:
        lifecycle_records = [
            record for record in self.runtime.load_records(run["run_id"])
            if (record.get("event") or {}).get("event_type")
            == "lifecycle_disposition_recorded"
        ]
        if not lifecycle_records:
            return None
        if len(lifecycle_records) != 1:
            raise ProcessLibraryIntegrityError(
                "Process Run has multiple lifecycle dispositions"
            )
        return self._validate_lifecycle_record(run, lifecycle_records[0])

    def _promotions(self) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
        promoted: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for run in self._iter_runs():
            closure = self._run_closure(run)
            if closure is None or closure["disposition"] != "promote":
                continue
            ref = closure["promoted_definition_ref"]
            key = (ref["definition_id"], ref["version"], ref["digest"])
            promoted.setdefault(key, []).append({
                "run_id": run["run_id"],
                "record_id": closure["record_id"],
                "recorded_at": closure["recorded_at"],
                "capability_artifact_id": closure["capability_artifact_id"],
                "accepted_result_artifact_id": closure[
                    "accepted_result_artifact_id"
                ],
            })
        return promoted

    @staticmethod
    def _scope_visible(scope: Mapping[str, Any], project_ref: str | None) -> bool:
        if project_ref is None:
            return True
        if scope["kind"] == "universal":
            return True
        return scope["selector"] == project_ref

    def list_entries(
        self,
        *,
        project_ref: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        """Return authenticated exact versions; never select a latest version."""

        canonical_project = (
            canonicalize_project_nexus(project_ref) if project_ref else None
        )
        promotions = self._promotions()
        entries = []
        try:
            definitions: dict[tuple[str, str, str], dict[str, Any]] = {}
            registry = self._registry_for_read()
            refs = registry.list_definition_refs() if registry is not None else []
            for ref in refs:
                definition = registry.resolve(
                    ref["definition_id"], ref["version"], ref["digest"]
                )
                definitions[(
                    ref["definition_id"], ref["version"], ref["digest"],
                )] = definition
            for definition in self._validated_seed_definitions():
                ref = _definition_ref(definition)
                key = (ref["definition_id"], ref["version"], ref["digest"])
                existing = definitions.get(key)
                if existing is not None and existing != definition:
                    raise ProcessLibraryIntegrityError(
                        "registered definition conflicts with its canonical seed"
                    )
                definitions[key] = definition
            for key, definition in definitions.items():
                ref = _definition_ref(definition)
                if (
                    not include_archived
                    and definition["status"] in {"archived", "retired"}
                ):
                    continue
                if not self._scope_visible(definition["scope"], canonical_project):
                    continue
                promotion_records = promotions.get(key, [])
                available = bool(promotion_records)
                manifest = definition["package_manifest"]
                aliases = sorted({
                    definition["title"].casefold(),
                    definition["definition_id"].rsplit("/", 1)[-1].replace("-", " "),
                    *[str(label).replace("-", " ") for label in definition.get("labels", [])],
                })
                entries.append({
                    "kind": "process_definition",
                    "id": definition["definition_id"].rsplit("/", 1)[-1],
                    "display_name": definition["title"],
                    "display_description": definition["purpose"],
                    "category": "process-definition",
                    "definition_ref": copy.deepcopy(ref),
                    "scope": copy.deepcopy(definition["scope"]),
                    "status": definition["status"],
                    "lifecycle_status": (
                        "available" if available else "registered"
                    ),
                    "promoted": available,
                    "activated": False,
                    "manual_invocation_available": available,
                    "standing_automation": False,
                    "entrypoints": copy.deepcopy(
                        definition["input_schema"].get("properties", {})
                        .get("entrypoint", {}).get("enum", [])
                    ),
                    "package": {
                        "package_id": manifest["package_id"],
                        "package_version": manifest["package_version"],
                        "entry_member_id": manifest["entry_member_id"],
                        "members": copy.deepcopy(manifest["members"]),
                    },
                    "promotion_records": copy.deepcopy(promotion_records),
                    "aliases": aliases,
                })
        except ProcessDefinitionRegistryError as exc:
            raise ProcessLibraryIntegrityError(
                "Process Library registry integrity failed"
            ) from exc
        entries.sort(key=lambda item: (
            item["display_name"].casefold(),
            item["definition_ref"]["definition_id"],
            item["definition_ref"]["version"],
        ))
        body = {
            "schema_version": LIBRARY_SCHEMA_VERSION,
            "generated_at": self._now(),
            "project_ref": canonical_project,
            "entries": entries,
            "standing_automation_included": False,
        }
        return {**body, "catalog_digest": _digest_json(body)}

    def get_run_lifecycle(self, run_id: str) -> dict[str, Any]:
        try:
            run = self.runtime.load_run(run_id)
        except RunNotFoundError:
            raise
        except GovernedRuntimeError as exc:
            raise ProcessLibraryIntegrityError(
                "Process Run lifecycle source integrity failed"
            ) from exc
        closure = self._run_closure(run)
        promotable = []
        if run["state"] == "completed" and closure is None:
            try:
                registry = self._registry_for_read()
                refs = registry.list_definition_refs() if registry is not None else []
                for ref in refs:
                    try:
                        binding = self._promotion_binding(run, ref)
                    except ProcessLibraryInputRequired:
                        continue
                    promotable.append({
                        "definition_ref": copy.deepcopy(ref),
                        "display_name": binding["definition"]["title"],
                        "capability_artifact_id": binding[
                            "capability_artifact"
                        ]["artifact_id"],
                        "accepted_result_artifact_id": binding[
                            "accepted_result"
                        ]["artifact_id"],
                    })
            except ProcessDefinitionRegistryError as exc:
                raise ProcessLibraryIntegrityError(
                    "Process Library registry integrity failed"
                ) from exc
        actions = []
        if run["state"] in TERMINAL_RUN_STATES and closure is None:
            actions = ["preserve", "archive", "discard"]
            if promotable:
                actions.insert(0, "promote")
        body = {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "run_id": run_id,
            "run_state": run["state"],
            "principal_id": run["contracts"]["authority"]["principal_id"],
            "status": (
                "closed" if closure is not None
                else "awaiting_disposition"
                if run["state"] in TERMINAL_RUN_STATES
                else "not_terminal"
            ),
            "available_actions": actions,
            "promote_options": promotable,
            "closure": closure,
        }
        return {**body, "lifecycle_digest": _digest_json(body)}

    def close_run(
        self,
        run_id: str,
        *,
        disposition: str,
        decision_by: str,
        idempotency_key: str,
        promoted_definition_ref: Mapping[str, Any] | None = None,
        capability_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        exact_disposition = str(disposition or "").strip().lower()
        if exact_disposition not in LIFECYCLE_DISPOSITIONS:
            raise ProcessLibraryInputRequired(
                "disposition must be promote, preserve, archive, or discard"
            )
        try:
            run = self.runtime.load_run(run_id)
            if exact_disposition == "promote":
                binding = self._promotion_binding(
                    run, promoted_definition_ref, capability_artifact_id
                )
                promoted_definition_ref = binding["definition_ref"]
                capability_artifact_id = binding[
                    "capability_artifact"
                ]["artifact_id"]
            record = self.runtime.record_lifecycle_disposition(
                run_id,
                exact_disposition,
                decision_by=decision_by,
                idempotency_key=idempotency_key,
                promoted_definition_ref=promoted_definition_ref,
                capability_artifact_id=capability_artifact_id,
            )
        except RunConflictError as exc:
            raise ProcessLibraryConflict(str(exc)) from exc
        except AuthorityDeniedError:
            raise
        except GovernedRuntimeError as exc:
            raise ProcessLibraryInputRequired(str(exc)) from exc
        lifecycle = self.get_run_lifecycle(run_id)
        if (
            lifecycle["status"] != "closed"
            or lifecycle["closure"]["record_id"] != record["record_id"]
        ):
            raise ProcessLibraryIntegrityError(
                "persisted Run lifecycle disposition did not reauthenticate"
            )
        return lifecycle


__all__ = [
    "LIBRARY_SCHEMA_VERSION",
    "LIFECYCLE_DISPOSITIONS",
    "LIFECYCLE_SCHEMA_VERSION",
    "ProcessLibraryConflict",
    "ProcessLibraryError",
    "ProcessLibraryInputRequired",
    "ProcessLibraryIntegrityError",
    "ProcessLibraryLifecycleService",
]
