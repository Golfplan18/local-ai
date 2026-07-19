"""G1.1 Phase 2.5 — authenticated, progressively disclosed Run inspection.

The inspector is a read-only projection over the four governed object
families and their append-only records.  It does not create a second runtime,
infer authority, or persist UI state.  Live local Artifact identities are
recaptured at inspection time so external-editor drift is visible and stale
evidence cannot be presented as current proof.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from governed_process_runtime import (
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunNotFoundError,
        inspect_live_artifact_identity,
    )
    from process_delegation_attention import ProcessDelegationAttentionService
    from process_plan_approval import (
        ProcessPlanApprovalService,
        capture_target_identity,
    )
    import runtime_paths as _runtime_paths
except ImportError:  # pragma: no cover
    from orchestrator.governed_process_runtime import (
        GovernedProcessRuntime,
        GovernedRuntimeError,
        RunNotFoundError,
        inspect_live_artifact_identity,
    )
    from orchestrator.process_delegation_attention import (
        ProcessDelegationAttentionService,
    )
    from orchestrator.process_plan_approval import (
        ProcessPlanApprovalService,
        capture_target_identity,
    )
    from orchestrator import runtime_paths as _runtime_paths


INSPECTOR_SCHEMA_VERSION = "ora.process-run-inspector/1.0"
INSPECTOR_VIEWS = (
    "overview",
    "plan",
    "current_state",
    "decisions",
    "changes",
    "evidence",
    "permissions",
    "artifacts",
    "technical",
)


class ProcessRunInspectorError(RuntimeError):
    """A Run cannot be projected through the inspector boundary."""


class ProcessRunInspectorIntegrityError(ProcessRunInspectorError):
    """Authenticated Run, plan, Artifact, record, or live identity drifted."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest_json(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProcessRunInspectorIntegrityError(
            f"invalid inspector timestamp: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise ProcessRunInspectorIntegrityError(
            f"inspector timestamp lacks a timezone: {value!r}"
        )
    return parsed


def _artifact_ref(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": artifact["artifact_id"],
        "role": artifact["role"],
        "status": artifact["status"],
        "media_type": artifact["media_type"],
        "locator": copy.deepcopy(artifact["locator"]),
        "identity_digest": artifact["identity"]["digest"],
    }


def _definition_ref(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "definition_id": str(value["definition_id"]),
        "version": str(value["version"]),
        "digest": str(value["digest"]),
    }


def _node_routes(node: Mapping[str, Any]) -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    raw_routes = node.get("routes")
    if isinstance(raw_routes, Mapping):
        routes.extend(
            {"condition": str(condition), "target_node_id": str(target)}
            for condition, target in raw_routes.items()
        )
    elif isinstance(raw_routes, Sequence) and not isinstance(raw_routes, (str, bytes)):
        routes.extend(
            {
                "condition": str(route["condition"]),
                "target_node_id": str(route["target_node_id"]),
            }
            for route in raw_routes
            if isinstance(route, Mapping)
        )
    for field, condition in (
        ("next_node_id", "next"),
        ("default_node_id", "default"),
        ("body_node_id", "loop_body"),
        ("exit_node_id", "loop_exit"),
        ("on_approved_node_id", "approved"),
        ("on_denied_node_id", "denied"),
        ("on_unavailable_node_id", "unavailable"),
        ("return_node_id", "return"),
        ("on_error_node_id", "error"),
    ):
        if field in node:
            routes.append({
                "condition": condition,
                "target_node_id": str(node[field]),
            })
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for route in routes:
        key = (route["condition"], route["target_node_id"])
        if key not in seen:
            unique.append(route)
            seen.add(key)
    return unique


def _state_entries(state: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(state, Mapping):
        return {}
    raw = state.get("files")
    if raw is None:
        raw = state.get("worktree_entries")
    if not isinstance(raw, list):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        if not isinstance(path, str):
            continue
        key = f"{item.get('path_encoding', 'utf-8')}:{path}"
        entries[key] = copy.deepcopy(dict(item))
    return entries


def _file_changes(
    baseline: Mapping[str, Any] | None,
    current: Mapping[str, Any] | None,
    *,
    limit: int = 1000,
) -> dict[str, Any]:
    before = _state_entries(baseline)
    after = _state_entries(current)
    rows: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            rows.append({"change": "added", "current": after[key]})
        elif key not in after:
            rows.append({"change": "removed", "baseline": before[key]})
        elif before[key] != after[key]:
            rows.append({
                "change": "modified",
                "baseline": before[key],
                "current": after[key],
            })
    counts = {
        kind: sum(1 for row in rows if row["change"] == kind)
        for kind in ("added", "modified", "removed")
    }
    return {
        "counts": {**counts, "total": len(rows)},
        "entries": rows[:limit],
        "truncated": len(rows) > limit,
    }


class ProcessRunInspectorService:
    """Build one exact, restart-derived Run Inspector snapshot."""

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        plan_service: ProcessPlanApprovalService | None = None,
        attention_service: ProcessDelegationAttentionService | None = None,
        sessions_root: str | Path | None = None,
        repository_root: str | Path | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.runtime = runtime or GovernedProcessRuntime()
        self.sessions_root = Path(sessions_root) if sessions_root else (
            _runtime_paths.ORA_HOME / "sessions"
        )
        self.repository_root = Path(repository_root) if repository_root else Path(
            _runtime_paths.ORA_HOME
        )
        self._now = now or _utc_now
        self.plan_service = plan_service or ProcessPlanApprovalService(
            runtime=self.runtime,
            sessions_root=self.sessions_root,
            repository_root=self.repository_root,
            now=self._now,
        )
        self.attention_service = attention_service or ProcessDelegationAttentionService(
            runtime=self.runtime,
            plan_service=self.plan_service,
            sessions_root=self.sessions_root,
            repository_root=self.repository_root,
            now=self._now,
        )

    def _plan_state(
        self, run: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        dialogue_ref = str(run.get("input_bindings", {}).get("dialogue_ref") or "")
        if not dialogue_ref or "phase-2.3" not in run.get("labels", []):
            return None
        state = self.plan_service.get_state(dialogue_ref)
        if state is None or state.get("run_id") != run["run_id"]:
            raise ProcessRunInspectorIntegrityError(
                "Phase 2.3 Run lacks its exact canonical plan state"
            )
        return state

    def _artifacts(
        self, run: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        now = _parse_time(self._now())
        rows: list[dict[str, Any]] = []
        raw: dict[str, dict[str, Any]] = {}
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run["run_id"], artifact_id)
            raw[artifact_id] = artifact
            live = inspect_live_artifact_identity(
                artifact, captured_at=self._now()
            )
            time_current = _parse_time(artifact["identity"]["fresh_until"]) >= now
            live_current = not live["applicable"] or (
                live["supported"]
                and live["available"]
                and live["matches"] is True
            )
            rows.append({
                **_artifact_ref(artifact),
                "identity": copy.deepcopy(artifact["identity"]),
                "lineage": copy.deepcopy(artifact["lineage"]),
                "time_current": time_current,
                "live_identity": {
                    key: copy.deepcopy(value)
                    for key, value in live.items()
                    if key != "current_state"
                },
                "current": bool(time_current and live_current),
            })
        return rows, raw

    @staticmethod
    def _latest_artifact_sequences(
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, int]:
        result: dict[str, int] = {}
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            if event.get("event_type") == "artifact_recorded":
                result[str(details.get("artifact_id") or "")] = int(record["sequence"])
        return result

    def _repository_tracking(
        self,
        run: Mapping[str, Any],
        definition: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
        artifacts: Mapping[str, Mapping[str, Any]],
        plan_state: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        baseline = None
        if plan_state and plan_state.get("current_plan"):
            baseline = plan_state["current_plan"]["repository_artifact_scope"]["target"]

        sequences = self._latest_artifact_sequences(records)
        candidates = [
            artifact for artifact in artifacts.values()
            if artifact["identity"]["kind"] == "composite"
            and artifact["locator"]["kind"] in {"git_ref", "file"}
            and artifact["role"] in {"result", "working"}
        ]
        expected_artifact = max(
            candidates,
            key=lambda item: sequences.get(item["artifact_id"], -1),
            default=None,
        )

        if expected_artifact is not None:
            live = inspect_live_artifact_identity(
                expected_artifact, captured_at=self._now()
            )
            expected_digest = expected_artifact["identity"]["digest"]
            locator = copy.deepcopy(expected_artifact["locator"])
            expected_source = {
                "kind": "artifact",
                "artifact_id": expected_artifact["artifact_id"],
                "identity_digest": expected_digest,
            }
            current_state = live.get("current_state")
            current_digest = live.get("current_digest")
            available = bool(live["available"])
            supported = bool(live["supported"])
            matches = live["matches"] is True
            reason = str(live["reason"])
        elif baseline is not None:
            locator = copy.deepcopy(baseline["locator"])
            expected_digest = str(baseline["identity"]["digest"])
            expected_source = {
                "kind": "approved_plan_baseline",
                "identity_digest": expected_digest,
            }
            try:
                current = capture_target_identity(
                    locator["ref"], captured_at=self._now()
                )
                current_state = current["state"]
                current_digest = current["identity"]["digest"]
                available = True
                supported = True
                matches = current_digest == expected_digest
                reason = (
                    "Approved target matches its persisted identity."
                    if matches
                    else "Approved target changed after its persisted identity was captured."
                )
            except Exception as exc:
                current_state = None
                current_digest = None
                available = False
                supported = True
                matches = False
                reason = f"Approved target is unavailable: {exc}"
        else:
            return None

        node = {
            item["node_id"]: item for item in definition["graph"]["nodes"]
        }[run["current_node_id"]]
        node_records: list[Mapping[str, Any]] = []
        entry_sequence = 0
        for record in records:
            transition = record.get("transition") or {}
            event = record.get("event") or {}
            details = event.get("details") or {}
            if transition.get("target_node_id") == run["current_node_id"]:
                entry_sequence = int(record["sequence"])
            elif event.get("event_type") == "node_advanced" and details.get(
                "to_node_id"
            ) == run["current_node_id"]:
                entry_sequence = int(record["sequence"])
        node_records = [
            record for record in records
            if int(record["sequence"]) > entry_sequence
            and record["node_id"] == run["current_node_id"]
        ]
        in_progress = bool(
            node.get("kind") == "action"
            and node.get("external_effect") is True
            and any(
                (record.get("event") or {}).get("event_type")
                == "external_action_authorized"
                for record in node_records
            )
            and not any(
                (record.get("event") or {}).get("event_type")
                in {"repository_state_captured", "action_completed"}
                and (
                    (record.get("event") or {}).get("event_type") != "repository_state_captured"
                    or ((record.get("event") or {}).get("details") or {}).get("phase")
                    == "post_action"
                )
                for record in node_records
            )
        )
        if not available:
            state = "target_unavailable"
        elif not supported:
            state = "identity_schema_unsupported"
        elif matches:
            state = "current"
        elif in_progress:
            state = "unverified_mutation_in_progress"
        else:
            state = "external_change_detected"

        baseline_state = baseline.get("state") if isinstance(baseline, Mapping) else None
        return {
            "locator": locator,
            "expected": expected_source,
            "current_identity_digest": current_digest,
            "state": state,
            "current": state == "current",
            "evidence_current": state == "current",
            "reason": reason,
            "file_changes_from_approved_baseline": _file_changes(
                baseline_state, current_state
            ),
            "git": {
                "baseline_head": (
                    baseline_state.get("head")
                    if isinstance(baseline_state, Mapping)
                    else None
                ),
                "current_head": (
                    current_state.get("head", current_state.get("git_head"))
                    if isinstance(current_state, Mapping)
                    else None
                ),
            },
        }

    def _evidence_view(
        self,
        run: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
        artifacts: Mapping[str, Mapping[str, Any]],
        artifact_rows: Sequence[Mapping[str, Any]],
        tracking: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        artifact_state = {
            row["artifact_id"]: row for row in artifact_rows
        }
        requirements = {
            item["evidence_id"]: copy.deepcopy(item)
            for item in run["contracts"]["evidence"]["requirements"]
        }
        results = [
            artifact for artifact in artifacts.values()
            if artifact["role"] == "result"
        ]
        latest_reviews: dict[tuple[str, str], Mapping[str, Any]] = {}
        all_refs: list[dict[str, Any]] = []
        for record in records:
            all_refs.extend(copy.deepcopy(record.get("evidence_refs") or []))
            event = record.get("event") or {}
            details = event.get("details") or {}
            if event.get("event_type") == "final_review_completed":
                latest_reviews[(
                    str(details.get("artifact_id") or ""),
                    str(details.get("evidence_id") or ""),
                )] = record

        checks: list[dict[str, Any]] = []
        for result in results:
            for evidence_id, requirement in requirements.items():
                if not requirement["required"]:
                    continue
                review = latest_reviews.get((result["artifact_id"], evidence_id))
                effective = "MISSING"
                reason = "No final review is persisted for this exact result."
                evidence_artifact_id = None
                if review is not None:
                    details = review["event"]["details"]
                    evidence_artifact_id = details.get("evidence_artifact_id")
                    effective = str(details.get("outcome") or "INDETERMINATE")
                    reason = "Persisted final-review observation."
                    if effective == "PASS":
                        try:
                            self.runtime._current_passing_review(
                                run["run_id"], result["artifact_id"], evidence_id
                            )
                        except GovernedRuntimeError as exc:
                            effective = "STALE"
                            reason = str(exc)
                    if evidence_artifact_id in artifact_state and not artifact_state[
                        evidence_artifact_id
                    ]["current"]:
                        effective = "STALE"
                        reason = "The exact evidence Artifact is no longer current."
                    result_live = artifact_state.get(result["artifact_id"])
                    if result_live is not None and not result_live["current"]:
                        effective = "STALE"
                        reason = "The reviewed result Artifact is no longer current."
                    if tracking is not None and not tracking["evidence_current"]:
                        effective = "STALE"
                        reason = (
                            "Live target identity changed; prior evidence is invalid "
                            "for the current target state."
                        )
                checks.append({
                    "evidence_id": evidence_id,
                    "artifact_id": result["artifact_id"],
                    "subject_identity_digest": result["identity"]["digest"],
                    "evidence_artifact_id": evidence_artifact_id,
                    "required": True,
                    "effective_outcome": effective,
                    "current": effective == "PASS",
                    "reason": reason,
                })

        required_without_result = bool(requirements) and not results
        acceptance_supported = bool(results) and bool(checks) and all(
            item["current"] for item in checks
        )
        if tracking is not None and not tracking["evidence_current"]:
            acceptance_supported = False
        unresolved = [
            {
                "evidence_id": item["evidence_id"],
                "artifact_id": item["artifact_id"],
                "outcome": item["effective_outcome"],
                "reason": item["reason"],
            }
            for item in checks if not item["current"]
        ]
        if required_without_result:
            unresolved.extend({
                "evidence_id": evidence_id,
                "artifact_id": None,
                "outcome": "MISSING",
                "reason": "No result Artifact exists for required evidence.",
            } for evidence_id, requirement in requirements.items() if requirement["required"])
        return {
            "policy": copy.deepcopy(run["contracts"]["evidence"]),
            "checks": checks,
            "acceptance_supported_now": acceptance_supported,
            "unresolved": unresolved,
            "evidence_artifacts": [
                _artifact_ref(artifact) for artifact in artifacts.values()
                if artifact["role"] in {"evidence", "external_effect_receipt"}
            ],
            "recorded_references": all_refs,
        }

    @staticmethod
    def _record_summary(record: Mapping[str, Any]) -> dict[str, Any]:
        if record["record_type"] == "transition":
            transition = record["transition"]
            kind = transition["directive"]
            summary = transition["reason"]
        else:
            event = record["event"]
            kind = event["event_type"]
            details = event.get("details") or {}
            summary = str(
                details.get("reason")
                or details.get("operation")
                or details.get("action")
                or details.get("observation_type")
                or kind
            )
        return {
            "sequence": record["sequence"],
            "record_id": record["record_id"],
            "recorded_at": record["recorded_at"],
            "node_id": record["node_id"],
            "kind": kind,
            "summary": summary,
            "artifact_ids": copy.deepcopy(record["artifact_ids"]),
        }

    def inspect(self, run_id: str) -> dict[str, Any]:
        try:
            run = self.runtime.load_run(run_id)
            definition = self.runtime.load_definition(run_id)
            records = self.runtime.load_records(run_id)
            artifact_rows, artifacts = self._artifacts(run)
            plan_state = self._plan_state(run)
            attention, _is_unread = self.attention_service._run_row(run)
        except RunNotFoundError:
            raise
        except ProcessRunInspectorError:
            raise
        except Exception as exc:
            raise ProcessRunInspectorIntegrityError(
                f"Run Inspector source integrity failed for {run_id}: {exc}"
            ) from exc

        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        current_node = nodes.get(run["current_node_id"])
        if current_node is None:
            raise ProcessRunInspectorIntegrityError(
                "Run current node is absent from its exact Process Definition"
            )
        tracking = self._repository_tracking(
            run, definition, records, artifacts, plan_state
        )
        evidence = self._evidence_view(
            run, records, artifacts, artifact_rows, tracking
        )

        transitions = [
            copy.deepcopy(record) for record in records
            if record["record_type"] == "transition"
        ]
        decision_events = []
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            observation_type = str(details.get("observation_type") or "")
            if (
                event.get("event_type") in {
                    "final_review_completed", "delegation_activated",
                    "external_action_authorized",
                }
                or any(token in observation_type for token in (
                    "approved", "approval", "revision", "stale", "withheld",
                    "authorized", "retained",
                ))
            ):
                decision_events.append(copy.deepcopy(record))

        external_effects = []
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            if event.get("event_type") == "action_completed" and details.get(
                "external_effect"
            ) is True:
                external_effects.append({
                    "record_id": record["record_id"],
                    "sequence": record["sequence"],
                    "recorded_at": record["recorded_at"],
                    "node_id": record["node_id"],
                    "action": details.get("action"),
                    "operation": details.get("completion_operation"),
                    "selectors": copy.deepcopy(details.get("selectors") or []),
                    "effect_type": details.get("effect_type"),
                    "receipt_artifact_id": details.get("receipt_artifact_id"),
                    "receipt_identity_digest": details.get("receipt_identity_digest"),
                })

        invoked = copy.deepcopy(run["relationships"]["invoked_definition_refs"])
        constructed = copy.deepcopy(
            run["relationships"]["constructed_definition_refs"]
        )

        plan_view = {
            "status": plan_state.get("status") if plan_state else (
                "approved_contract" if run["contracts"]["approved_plan"] else "unavailable"
            ),
            "approved_contract": copy.deepcopy(run["contracts"]["approved_plan"]),
            "plan_versions": copy.deepcopy(
                plan_state.get("plan_versions", []) if plan_state else []
            ),
            "current_plan": copy.deepcopy(
                plan_state.get("current_plan") if plan_state else None
            ),
            "principal_view": copy.deepcopy(
                (plan_state.get("current_plan") or {}).get("principal_view")
                if plan_state else None
            ),
            "technical_view": copy.deepcopy(
                (plan_state.get("current_plan") or {}).get("technical_view")
                if plan_state else None
            ),
            "approval": copy.deepcopy(
                plan_state.get("approval") if plan_state else None
            ),
            "lifecycle": copy.deepcopy(
                plan_state.get("dialogue_lifecycle") if plan_state else None
            ),
            "export": copy.deepcopy(
                plan_state.get("export") if plan_state else None
            ),
        }

        visited = []
        for record in records:
            node_id = str(record["node_id"])
            if node_id not in visited:
                visited.append(node_id)
            transition = record.get("transition") or {}
            target = str(transition.get("target_node_id") or "")
            if target and target not in visited:
                visited.append(target)
            event = record.get("event") or {}
            event_target = str((event.get("details") or {}).get("to_node_id") or "")
            if event_target and event_target not in visited:
                visited.append(event_target)

        trigger_fields = {
            key: copy.deepcopy(value)
            for key, value in run["input_bindings"].items()
            if "trigger" in str(key).lower()
        }
        required_decision = (
            copy.deepcopy((attention.get("attention") or {}).get("required_decision"))
            if attention.get("needs_attention") else None
        )
        objective = str(run["contracts"]["approved_plan"].get("objective") or "")
        result_artifacts = [
            row for row in artifact_rows if row["role"] == "result"
        ]
        timeline = [self._record_summary(record) for record in records]
        overview = {
            "objective": objective or definition["purpose"],
            "title": objective or definition["title"],
            "run_state": run["state"],
            "visible_status": attention["visible_status"],
            "current_phase": {
                "node_id": current_node["node_id"],
                "label": current_node["label"],
                "kind": current_node["kind"],
            },
            "credible_next_actions": _node_routes(current_node),
            "required_human_decision": required_decision,
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "invoked_capabilities": invoked,
            "capabilities_created_or_modified": constructed,
            "result_artifacts": result_artifacts,
            "external_effects": external_effects,
            "trigger": {
                "entrypoint": run["entrypoint"],
                "bindings": trigger_fields,
            },
            "evidence_current": evidence["acceptance_supported_now"],
        }

        views = {
            "overview": overview,
            "plan": plan_view,
            "current_state": {
                "state": run["state"],
                "current_node": copy.deepcopy(current_node),
                "next_routes": _node_routes(current_node),
                "attempt": run["contracts"]["correction_loop"]["attempt"],
                "max_attempts": run["contracts"]["correction_loop"]["max_attempts"],
                "visited_node_ids": visited,
                "node_count": len(nodes),
                "timeline": timeline,
                "updated_at": run["updated_at"],
            },
            "decisions": {
                "transitions": transitions,
                "decision_events": decision_events,
                "required_human_decision": required_decision,
            },
            "changes": {
                "repository": tracking,
                "external_effects": external_effects,
                "state_captures": [
                    copy.deepcopy(record) for record in records
                    if (record.get("event") or {}).get("event_type")
                    == "repository_state_captured"
                ],
                "receipts": [
                    _artifact_ref(artifact) for artifact in artifacts.values()
                    if artifact["role"] == "external_effect_receipt"
                ],
            },
            "evidence": evidence,
            "permissions": {
                "principal_id": run["contracts"]["authority"]["principal_id"],
                "grants": copy.deepcopy(run["contracts"]["authority"]["grants"]),
                "reserved_actions": copy.deepcopy(
                    run["contracts"]["authority"]["reserved_actions"]
                ),
                "artifact_scope": copy.deepcopy(run["contracts"]["artifact_scope"]),
                "stop_escalation": copy.deepcopy(
                    run["contracts"]["stop_escalation"]
                ),
                "required_human_decision": required_decision,
            },
            "artifacts": {
                "items": artifact_rows,
                "results": result_artifacts,
                "created_or_modified_capabilities": constructed,
            },
            "technical": {
                "definition": copy.deepcopy(definition),
                "definition_ref": _definition_ref(definition),
                "run": copy.deepcopy(run),
                "records": copy.deepcopy(records),
                "files": [
                    {
                        "artifact_id": artifact["artifact_id"],
                        "role": artifact["role"],
                        "locator": copy.deepcopy(artifact["locator"]),
                        "identity_digest": artifact["identity"]["digest"],
                    }
                    for artifact in artifacts.values()
                    if artifact["locator"]["kind"] in {"file", "git_ref"}
                ],
                "diff": (
                    copy.deepcopy(tracking["file_changes_from_approved_baseline"])
                    if tracking else None
                ),
                "tests": copy.deepcopy(
                    ((plan_state or {}).get("current_plan") or {}).get(
                        "test_inspection_plan", []
                    )
                ),
                "logs": [
                    self._record_summary(record) for record in records
                    if (record.get("event") or {}).get("event_type") in {
                        "infrastructure_attempt", "controlled_probe_execution_completed"
                    }
                    or (
                        record.get("event")
                        and (record.get("event") or {}).get("event_type")
                        not in {
                            "artifact_recorded", "node_advanced",
                            "dialogue_observation_recorded",
                        }
                    )
                ],
                "external_editor_changes": copy.deepcopy(tracking),
            },
        }
        if tuple(views) != INSPECTOR_VIEWS:
            raise ProcessRunInspectorIntegrityError(
                "Run Inspector view set differs from the Phase 2.5 contract"
            )
        body = {
            "schema_version": INSPECTOR_SCHEMA_VERSION,
            "generated_at": self._now(),
            "run_id": run["run_id"],
            "dialogue_ref": str(run["input_bindings"].get("dialogue_ref") or ""),
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "view_order": list(INSPECTOR_VIEWS),
            "views": views,
        }
        return {**body, "snapshot_digest": _digest_json(body)}


__all__ = [
    "INSPECTOR_SCHEMA_VERSION",
    "INSPECTOR_VIEWS",
    "ProcessRunInspectorError",
    "ProcessRunInspectorIntegrityError",
    "ProcessRunInspectorService",
]
