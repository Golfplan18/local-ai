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
import re
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
    from process_automation import (
        active_automation_worker,
        automation_run_controls,
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
    from orchestrator.process_automation import (
        active_automation_worker,
        automation_run_controls,
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


class ProcessRunTelemetryInputRequired(ProcessRunInspectorError):
    pass


class ProcessRunTelemetryConflict(ProcessRunInspectorError):
    pass


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


def _parse_quality_verdict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProcessRunInspectorError(
                "quality evaluator returned invalid JSON"
            ) from exc
    if not isinstance(value, Mapping):
        raise ProcessRunInspectorError("quality evaluator returned no verdict object")
    verdict = copy.deepcopy(dict(value))
    if (
        set(verdict) != {
            "verdict", "drift_verdict", "quality_verdict",
            "findings", "rationale",
        }
        or verdict.get("verdict") not in {
            "PASS", "WARN", "FAIL", "INDETERMINATE",
        }
        or verdict.get("drift_verdict") not in {
            "NONE", "POSSIBLE", "PRESENT", "INDETERMINATE",
        }
        or verdict.get("quality_verdict") not in {
            "PASS", "WARN", "FAIL", "INDETERMINATE",
        }
        or not isinstance(verdict.get("findings"), list)
        or not all(isinstance(item, str) and item.strip() for item in verdict["findings"])
        or len(verdict["findings"]) > 20
        or not isinstance(verdict.get("rationale"), str)
        or not verdict["rationale"].strip()
    ):
        raise ProcessRunInspectorError("quality evaluator verdict schema is invalid")
    verdict["findings"] = [item.strip()[:1000] for item in verdict["findings"]]
    verdict["rationale"] = verdict["rationale"].strip()[:4000]
    return verdict


def _default_quality_evaluator(
    package: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Run one opt-in, profile-bound evaluation; never advance the Run."""

    runtime_name = str(binding.get("runtime_name") or "")
    if not runtime_name:
        raise ProcessRunInspectorError(
            "the exact Run has no Model Profile binding for quality evaluation"
        )
    try:
        try:
            from .boot import (
                call_model,
                load_routing_config,
                resolve_single_pass_endpoint,
            )
        except ImportError:  # pragma: no cover
            from boot import (  # type: ignore
                call_model,
                load_routing_config,
                resolve_single_pass_endpoint,
            )
        config = load_routing_config()
        endpoint, _cell = resolve_single_pass_endpoint(
            config, gear=1, config_name=runtime_name,
        )
        prompt = (
            "Evaluate only the supplied authenticated Process Run packet. "
            "Do not authorize, advance, retry, or modify the Run. Return exactly "
            "one JSON object with keys verdict, drift_verdict, quality_verdict, "
            "findings, rationale. verdict and quality_verdict are PASS, WARN, "
            "FAIL, or INDETERMINATE. drift_verdict is NONE, POSSIBLE, PRESENT, "
            "or INDETERMINATE. findings is a JSON array of short strings.\n\n"
            + json.dumps(package, sort_keys=True, ensure_ascii=False)
        )
        raw = call_model([
            {"role": "system", "content": "You are an authority-inert Process telemetry evaluator."},
            {"role": "user", "content": prompt},
        ], endpoint)
    except ProcessRunInspectorError:
        raise
    except Exception as exc:
        raise ProcessRunInspectorError(
            f"quality evaluator unavailable: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(raw, str) or raw.startswith("[Error"):
        raise ProcessRunInspectorError("quality evaluator model call failed")
    return _parse_quality_verdict(raw)


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

    def _worker_liveness(
        self,
        run: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Authenticate persisted worker lifetime against the live owner."""

        starts: dict[str, Mapping[str, Any]] = {}
        finishes: dict[str, Mapping[str, Any]] = {}
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            event_type = event.get("event_type")
            if event_type == "process_worker_started":
                expected = {
                    "run_id", "definition_ref", "execution_id", "node_id",
                    "attempt", "pid", "worker_boundary", "worker_request_digest",
                }
                execution_id = str(details.get("execution_id") or "")
                if (
                    set(details) != expected
                    or not execution_id
                    or details.get("run_id") != run["run_id"]
                    or details.get("definition_ref") != run["definition_ref"]
                    or record.get("node_id") != details.get("node_id")
                    or execution_id in starts
                ):
                    raise ProcessRunInspectorIntegrityError(
                        "worker start record does not bind one exact Run invocation"
                    )
                starts[execution_id] = record
            elif event_type == "process_worker_finished":
                expected = {
                    "run_id", "definition_ref", "execution_id",
                    "worker_start_record_id", "node_id", "attempt", "pid",
                    "worker_boundary", "worker_request_digest", "outcome",
                    "returncode", "control_action",
                }
                execution_id = str(details.get("execution_id") or "")
                start = starts.get(execution_id)
                start_details = ((start or {}).get("event") or {}).get("details") or {}
                if (
                    set(details) != expected
                    or start is None
                    or details.get("worker_start_record_id") != start.get("record_id")
                    or record.get("node_id") != start.get("node_id")
                    or int(record.get("sequence", 0)) <= int(start.get("sequence", 0))
                    or any(
                        details.get(field) != start_details.get(field)
                        for field in (
                            "run_id", "definition_ref", "execution_id", "node_id",
                            "attempt", "pid", "worker_boundary",
                            "worker_request_digest",
                        )
                    )
                    or details.get("outcome") not in {
                        "exited", "failed", "controlled", "timeout", "spawn_failed",
                    }
                    or details.get("control_action") not in {None, "pause", "stop"}
                    or execution_id in finishes
                ):
                    raise ProcessRunInspectorIntegrityError(
                        "worker finish record does not authenticate its exact start"
                    )
                finishes[execution_id] = record

        unmatched = [
            (execution_id, record)
            for execution_id, record in starts.items()
            if execution_id not in finishes
        ]
        if len(unmatched) > 1:
            raise ProcessRunInspectorIntegrityError(
                "Run has multiple unfinished isolated worker records"
            )
        live = active_automation_worker(run["run_id"])
        if not unmatched:
            if live is not None and live.get("alive"):
                raise ProcessRunInspectorIntegrityError(
                    "live worker lacks its persisted start record"
                )
            last_finish = max(
                finishes.values(), key=lambda item: int(item["sequence"]),
                default=None,
            )
            return {
                "status": "idle",
                "healthy": True,
                "action_required": False,
                "active": False,
                "execution_id": None,
                "pid": None,
                "node_id": None,
                "attempt": None,
                "worker_boundary": None,
                "started_at": None,
                "last_finished_at": (
                    last_finish.get("recorded_at") if last_finish else None
                ),
                "reason": "No isolated worker is currently active.",
            }

        execution_id, start = unmatched[0]
        details = start["event"]["details"]
        completed_after_start = any(
            int(record["sequence"]) > int(start["sequence"])
            and (record.get("event") or {}).get("event_type")
            == "attempt_completed"
            and (record.get("event") or {}).get("details", {}).get("segment_id")
            == details.get("node_id")
            for record in records
        )
        if completed_after_start:
            return {
                "status": "recovered_after_restart",
                "healthy": True,
                "action_required": False,
                "active": False,
                "execution_id": execution_id,
                "pid": details.get("pid"),
                "node_id": details.get("node_id"),
                "attempt": details.get("attempt"),
                "worker_boundary": details.get("worker_boundary"),
                "started_at": start["recorded_at"],
                "last_finished_at": None,
                "reason": "Lost worker ownership was fail-closed into a persisted recovery checkpoint.",
            }
        live_matches = bool(
            live
            and live.get("alive") is True
            and live.get("execution_id") == execution_id
            and live.get("run_id") == run["run_id"]
            and live.get("node_id") == details.get("node_id")
            and live.get("attempt") == details.get("attempt")
            and live.get("pid") == details.get("pid")
            and live.get("request_digest")
            == details.get("worker_request_digest")
        )
        return {
            "status": "alive" if live_matches else "orphaned_after_restart",
            "healthy": live_matches,
            "action_required": not live_matches,
            "active": live_matches,
            "execution_id": execution_id,
            "pid": details.get("pid"),
            "node_id": details.get("node_id"),
            "attempt": details.get("attempt"),
            "worker_boundary": details.get("worker_boundary"),
            "started_at": start["recorded_at"],
            "last_finished_at": None,
            "reason": (
                "The runtime owns this exact live worker."
                if live_matches
                else "Persisted worker ownership was lost; execution must fail closed into recovery."
            ),
        }

    def _deterministic_telemetry(
        self,
        run: Mapping[str, Any],
        definition: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
        artifact_rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        now = _parse_time(self._now())
        start_record = next(
            (
                record for record in records
                if (record.get("event") or {}).get("event_type") == "run_started"
            ),
            records[0] if records else None,
        )
        start_time = _parse_time(
            str((start_record or {}).get("recorded_at") or run["created_at"])
        )
        terminal = run["state"] in {"completed", "blocked", "cancelled"}
        terminal_record = next(
            (
                record for record in reversed(records)
                if (record.get("transition") or {}).get("to_state")
                in {"completed", "blocked", "cancelled"}
            ),
            None,
        )
        end_time = (
            _parse_time(str((terminal_record or {}).get("recorded_at") or run["updated_at"]))
            if terminal else now
        )
        elapsed_seconds = max(0.0, (end_time - start_time).total_seconds())

        attempt_starts: dict[tuple[str, int], Mapping[str, Any]] = {}
        durations: list[float] = []
        attempts_by_segment: dict[str, int] = {}
        last_error = None
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            if event.get("event_type") == "attempt_started":
                key = (str(details.get("segment_id") or ""), int(details.get("attempt") or 0))
                attempt_starts[key] = record
                attempts_by_segment[key[0]] = attempts_by_segment.get(key[0], 0) + 1
            elif event.get("event_type") == "attempt_completed":
                key = (str(details.get("segment_id") or ""), int(details.get("attempt") or 0))
                started = attempt_starts.get(key)
                if started is not None:
                    durations.append(max(
                        0.0,
                        (_parse_time(record["recorded_at"]) - _parse_time(started["recorded_at"])).total_seconds(),
                    ))
                defects = list(details.get("defect_codes") or [])
                if defects:
                    last_error = {
                        "record_id": record["record_id"],
                        "recorded_at": record["recorded_at"],
                        "node_id": record["node_id"],
                        "codes": defects,
                        "retryable": run["state"] not in {"completed", "blocked", "cancelled"},
                        "active": True,
                    }
                elif (
                    last_error is not None
                    and last_error.get("node_id") == record.get("node_id")
                ):
                    last_error["active"] = False
                    last_error["resolved_at"] = record["recorded_at"]
            elif event.get("event_type") == "isolated_process_verification_failed":
                last_error = {
                    "record_id": record["record_id"],
                    "recorded_at": record["recorded_at"],
                    "node_id": record["node_id"],
                    "codes": [str(details.get("error_type") or "verification_failed")],
                    "retryable": bool(details.get("retryable")),
                    "active": True,
                }
            elif (
                event.get("event_type") == "isolated_process_verification_completed"
                and last_error is not None
                and last_error.get("node_id") == record.get("node_id")
            ):
                last_error["active"] = False
                last_error["resolved_at"] = record["recorded_at"]

        nodes = definition["graph"]["nodes"]
        completed_nodes = {
            str(record["node_id"])
            for record in records
            if (record.get("event") or {}).get("event_type") in {
                "action_completed", "isolated_process_verification_completed",
            }
        }
        remaining = [
            node for node in nodes
            if node["node_id"] not in completed_nodes
            and node["kind"] in {"action", "verification_boundary"}
        ]
        if terminal:
            estimate = 0.0
            estimate_reason = "Run is terminal."
        elif durations and remaining:
            estimate = (sum(durations) / len(durations)) * len(remaining)
            estimate_reason = "Deterministic mean of completed attempt durations times remaining executable nodes."
        elif not remaining:
            estimate = 0.0
            estimate_reason = "No unvisited executable nodes remain."
        else:
            estimate = None
            estimate_reason = "No completed attempt duration is available for an estimate."

        worker_events = [
            record for record in records
            if (record.get("event") or {}).get("event_type")
            in {"process_worker_started", "process_worker_finished"}
        ]
        no_tools_only = bool(worker_events) and all(
            (record["event"]["details"].get("worker_boundary") in {
                "separate_no_tools_process", "injected_test_worker",
            })
            for record in worker_events
        )
        usage = {
            "input_tokens": 0 if no_tools_only else None,
            "output_tokens": 0 if no_tools_only else None,
            "total_tokens": 0 if no_tools_only else None,
            "cost_usd": 0.0 if no_tools_only else None,
            "measured": no_tools_only,
            "source": (
                "isolated_no_tools_worker" if no_tools_only
                else "no_authenticated_usage_record"
            ),
        }
        artifact_counts: dict[str, int] = {}
        for artifact in artifact_rows:
            role = str(artifact["role"])
            artifact_counts[role] = artifact_counts.get(role, 0) + 1
        retries = sum(max(0, count - 1) for count in attempts_by_segment.values())
        liveness = self._worker_liveness(run, records)
        active_error = bool(last_error and last_error.get("active"))
        automation = isinstance(
            (definition.get("output_schema") or {}).get("x-ora-process"), Mapping,
        )
        controls = (
            automation_run_controls(self.runtime, run["run_id"])
            if automation else {
                "schema_version": "ora.process-run-controls/1.0",
                "run_id": run["run_id"],
                "available_actions": [],
                "control_state_digest": None,
                "active_worker": None,
            }
        )
        return {
            "schema_version": "ora.process-run-telemetry/1.0",
            "layer": "deterministic",
            "run_state": run["state"],
            "current_node_id": run["current_node_id"],
            "started_at": start_time.isoformat().replace("+00:00", "Z"),
            "updated_at": run["updated_at"],
            "elapsed_seconds": elapsed_seconds,
            "estimated_remaining_seconds": estimate,
            "estimate_reason": estimate_reason,
            "attempts": {
                "total": sum(attempts_by_segment.values()),
                "retries": retries,
                "by_segment": attempts_by_segment,
                "ceiling": run["contracts"]["correction_loop"]["max_attempts"],
            },
            "usage": usage,
            "artifacts": {
                "total": len(artifact_rows),
                "by_role": artifact_counts,
                "current": sum(bool(item["current"]) for item in artifact_rows),
            },
            "last_error": last_error,
            "liveness": liveness,
            "health": {
                "status": (
                    "action_required" if liveness["action_required"] or active_error
                    else "healthy"
                ),
                "reason": (
                    liveness["reason"] if liveness["action_required"]
                    else ("A persisted failure requires review." if active_error else "No deterministic fault is active.")
                ),
            },
            "controls": controls,
        }

    @staticmethod
    def _quality_eligibility(
        run: Mapping[str, Any],
        definition: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        current = nodes[run["current_node_id"]]
        excluded = {
            "process_quality_evaluation_started",
            "process_quality_evaluation_completed",
            "process_quality_evaluation_failed",
        }
        relevant = [
            record for record in records
            if (record.get("event") or {}).get("event_type") not in excluded
        ]
        if run["state"] == "pending" and current["kind"] == "human_checkpoint":
            return {
                "eligible": True,
                "reason": "human_handoff",
                "source_record_id": relevant[-1]["record_id"] if relevant else None,
            }
        latest_attempt = next(
            (
                record for record in reversed(relevant)
                if (record.get("event") or {}).get("event_type")
                == "attempt_completed"
            ),
            None,
        )
        latest_verification = next(
            (
                record for record in reversed(relevant)
                if (record.get("event") or {}).get("event_type") in {
                    "isolated_process_verification_failed",
                    "isolated_process_verification_completed",
                }
            ),
            None,
        )
        latest_review = next(
            (
                record for record in reversed(relevant)
                if (record.get("event") or {}).get("event_type")
                == "final_review_completed"
            ),
            None,
        )
        failure = None
        if latest_attempt and (
            latest_attempt["event"]["details"].get("defect_codes")
        ):
            failure = latest_attempt
        if latest_verification and (
            latest_verification["event"]["event_type"]
            == "isolated_process_verification_failed"
            or latest_verification["event"]["details"].get("outcome") == "FAIL"
        ):
            if failure is None or latest_verification["sequence"] > failure["sequence"]:
                failure = latest_verification
        if latest_review and latest_review["event"]["details"].get("outcome") != "PASS":
            if failure is None or latest_review["sequence"] > failure["sequence"]:
                failure = latest_review
        if failure is not None:
            return {
                "eligible": True,
                "reason": "output_failure",
                "source_record_id": failure["record_id"],
            }
        return {
            "eligible": False,
            "reason": "not_at_handoff_or_output_failure",
            "source_record_id": None,
        }

    @staticmethod
    def _quality_evaluations(
        run: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        starts: dict[str, Mapping[str, Any]] = {}
        outcomes: dict[str, Mapping[str, Any]] = {}
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            event_type = event.get("event_type")
            if event_type == "process_quality_evaluation_started":
                evaluation_id = str(details.get("evaluation_id") or "")
                if not evaluation_id or evaluation_id in starts:
                    raise ProcessRunInspectorIntegrityError(
                        "quality evaluation start identity is invalid"
                    )
                starts[evaluation_id] = record
            elif event_type in {
                "process_quality_evaluation_completed",
                "process_quality_evaluation_failed",
            }:
                evaluation_id = str(details.get("evaluation_id") or "")
                start = starts.get(evaluation_id)
                start_details = ((start or {}).get("event") or {}).get("details") or {}
                if (
                    start is None
                    or evaluation_id in outcomes
                    or details.get("evaluation_start_record_id")
                    != start.get("record_id")
                    or any(
                        details.get(field) != start_details.get(field)
                        for field in (
                            "run_id", "definition_ref", "evaluation_id",
                            "idempotency_key", "subject_digest", "eligible_reason",
                            "source_sequence", "evaluator_binding",
                        )
                    )
                    or int(record["sequence"]) <= int(start["sequence"])
                ):
                    raise ProcessRunInspectorIntegrityError(
                        "quality evaluation result does not authenticate its start"
                    )
                outcomes[evaluation_id] = record
        rows = []
        for evaluation_id, start in starts.items():
            result = outcomes.get(evaluation_id)
            start_details = start["event"]["details"]
            result_event = (result or {}).get("event") or {}
            result_details = result_event.get("details") or {}
            rows.append({
                "evaluation_id": evaluation_id,
                "status": (
                    "completed" if result_event.get("event_type")
                    == "process_quality_evaluation_completed"
                    else "failed" if result is not None else "interrupted"
                ),
                "eligible_reason": start_details["eligible_reason"],
                "subject_digest": start_details["subject_digest"],
                "evaluator_binding": copy.deepcopy(start_details["evaluator_binding"]),
                "started_at": start["recorded_at"],
                "finished_at": result.get("recorded_at") if result else None,
                "verdict": copy.deepcopy(result_details.get("verdict")),
                "error_type": result_details.get("error_type"),
                "record_ids": [
                    start["record_id"],
                    *([result["record_id"]] if result else []),
                ],
            })
        return rows

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

    @staticmethod
    def _governed_decisions(
        run: Mapping[str, Any],
        definition: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Authenticate graph decisions against the exact issued definition."""

        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        records_by_id = {str(record["record_id"]): record for record in records}
        decisions: list[dict[str, Any]] = []
        for record in records:
            event = record.get("event") or {}
            if event.get("event_type") != "node_advanced":
                continue
            details = event.get("details") or {}
            source_id = str(details.get("from_node_id") or "")
            target_id = str(details.get("to_node_id") or "")
            source = nodes.get(source_id)
            if source is None or source.get("kind") not in {
                "decision", "human_checkpoint",
            }:
                continue
            if (
                record.get("record_type") != "event"
                or record.get("node_id") != source_id
                or target_id not in nodes
                or set(details) != {
                    "from_node_id", "to_node_id", "advance_kind", "reason", "route",
                }
                or not isinstance(details.get("route"), Mapping)
            ):
                raise ProcessRunInspectorIntegrityError(
                    "governed decision record does not authenticate its graph edge"
                )

            route = details["route"]
            common = {
                "record_id": record["record_id"],
                "sequence": record["sequence"],
                "recorded_at": record["recorded_at"],
                "source_node_id": source_id,
                "source_label": source["label"],
                "target_node_id": target_id,
                "target_label": nodes[target_id]["label"],
                "reason": details["reason"],
            }
            if source["kind"] == "human_checkpoint":
                base_route_fields = {
                    "outcome", "decision_by", "authority_request_type",
                }
                authority_route_fields = base_route_fields | {
                    "authority_request_id",
                    "authority_resolution_record_id",
                    "authority_resolution_digest",
                }
                if (
                    details.get("advance_kind") != "human_checkpoint"
                    or (
                        set(route) != base_route_fields
                        and set(route) != authority_route_fields
                    )
                    or route.get("outcome") not in {
                        "approved", "denied", "unavailable",
                    }
                    or not isinstance(route.get("decision_by"), str)
                    or not route["decision_by"]
                    or route.get("authority_request_type")
                    != source.get("authority_request_type")
                ):
                    raise ProcessRunInspectorIntegrityError(
                        "human-checkpoint decision does not authenticate its authority route"
                    )
                target_field = {
                    "approved": "on_approved_node_id",
                    "denied": "on_denied_node_id",
                    "unavailable": "on_unavailable_node_id",
                }[route["outcome"]]
                if target_field not in source:
                    target_field = "on_denied_node_id"
                if (
                    target_id != str(source[target_field])
                    or (
                        route["outcome"] == "approved"
                        and route["decision_by"]
                        != run["contracts"]["authority"]["principal_id"]
                    )
                ):
                    raise ProcessRunInspectorIntegrityError(
                        "human-checkpoint decision target is not the declared graph route"
                    )
                if set(route) == authority_route_fields:
                    resolution = records_by_id.get(
                        str(route["authority_resolution_record_id"])
                    )
                    resolution_event = (
                        (resolution or {}).get("event") or {}
                    )
                    resolution_details = resolution_event.get("details") or {}
                    escalation = records_by_id.get(
                        str(resolution_details.get("escalation_record_id") or "")
                    )
                    escalation_transition = (
                        (escalation or {}).get("transition") or {}
                    )
                    request = escalation_transition.get("authority_request") or {}
                    binding = {
                        field: copy.deepcopy(resolution_details.get(field))
                        for field in (
                            "run_id", "request_id", "definition_ref",
                            "escalation_record_id", "request", "source_node_id",
                            "target_node_id", "outcome", "decision_by",
                        )
                    }
                    expected_resolution_fields = set(binding) | {
                        "idempotency_key", "resolution_digest",
                    }
                    expected_resolution_digest = _digest_json(binding)
                    if (
                        resolution is None
                        or resolution.get("record_type") != "event"
                        or resolution_event.get("event_type")
                        != "authority_request_resolved"
                        or resolution.get("node_id") != source_id
                        or set(resolution_details) != expected_resolution_fields
                        or int(resolution.get("sequence", 0))
                        != int(record["sequence"]) - 1
                        or resolution_details.get("resolution_digest")
                        != expected_resolution_digest
                        or resolution_details.get("idempotency_key")
                        != "authority:" + expected_resolution_digest.split(":", 1)[1]
                        or route["authority_resolution_digest"]
                        != resolution_details.get("resolution_digest")
                        or route["authority_request_id"]
                        != resolution_details.get("request_id")
                        or resolution_details.get("run_id") != run["run_id"]
                        or resolution_details.get("definition_ref")
                        != run["definition_ref"]
                        or resolution_details.get("source_node_id") != source_id
                        or resolution_details.get("target_node_id") != target_id
                        or resolution_details.get("outcome") != route["outcome"]
                        or resolution_details.get("decision_by")
                        != route["decision_by"]
                        or route["decision_by"]
                        != run["contracts"]["authority"]["principal_id"]
                        or escalation_transition.get("directive") != "ESCALATE"
                        or request != resolution_details.get("request")
                        or request.get("requested_from")
                        != run["contracts"]["authority"]["principal_id"]
                        or request.get("request_id")
                        != route["authority_request_id"]
                        or (
                            route["outcome"] == "approved"
                            and request.get("resume_node_id") != target_id
                        )
                        or resolution.get("evidence_refs")
                        != (escalation or {}).get("evidence_refs")
                        or resolution.get("artifact_ids")
                        != (escalation or {}).get("artifact_ids")
                    ):
                        raise ProcessRunInspectorIntegrityError(
                            "authority decision does not bind its exact persisted request"
                        )
                decisions.append({
                    **common,
                    "decision_kind": "human_checkpoint",
                    "outcome": route["outcome"],
                    "decision_by": route["decision_by"],
                    "authority_request_type": route["authority_request_type"],
                    "route": copy.deepcopy(dict(route)),
                })
                continue

            if (
                details.get("advance_kind") != "decision"
                or set(route) != {"condition", "matched", "default_used"}
                or not isinstance(route.get("condition"), str)
                or not isinstance(route.get("matched"), bool)
                or not isinstance(route.get("default_used"), bool)
            ):
                raise ProcessRunInspectorIntegrityError(
                    "decision-node record does not authenticate its route selection"
                )
            declared_routes = source["routes"]
            if isinstance(declared_routes, Mapping):
                matched_target = declared_routes.get(route["condition"])
                matched_route = (
                    {"target_node_id": matched_target}
                    if matched_target is not None else None
                )
            else:
                matched_route = next(
                    (
                        item for item in declared_routes
                        if item["condition"] == route["condition"]
                    ),
                    None,
                )
            expected_target = (
                str(matched_route["target_node_id"])
                if matched_route is not None
                else str(source["default_node_id"])
            )
            if (
                route["matched"] != (matched_route is not None)
                or route["default_used"] != (matched_route is None)
                or target_id != expected_target
            ):
                raise ProcessRunInspectorIntegrityError(
                    "decision-node outcome differs from the declared graph route"
                )
            decisions.append({
                **common,
                "decision_kind": "decision_node",
                "condition": route["condition"],
                "matched": route["matched"],
                "default_used": route["default_used"],
                "route": copy.deepcopy(dict(route)),
            })
        return decisions

    @staticmethod
    def _repository_target_groups(
        candidates: Sequence[Mapping[str, Any]],
        sequences: Mapping[str, int],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for artifact in candidates:
            locator = copy.deepcopy(artifact["locator"])
            key = json.dumps(locator, sort_keys=True, separators=(",", ":"))
            group = grouped.setdefault(key, {
                "locator": locator,
                "artifact_ids": [],
                "roles": [],
                "latest_sequence": -1,
            })
            group["artifact_ids"].append(artifact["artifact_id"])
            if artifact["role"] not in group["roles"]:
                group["roles"].append(artifact["role"])
            group["latest_sequence"] = max(
                group["latest_sequence"],
                sequences.get(artifact["artifact_id"], -1),
            )
        return sorted(
            grouped.values(),
            key=lambda item: (
                -int(item["latest_sequence"]),
                json.dumps(item["locator"], sort_keys=True),
            ),
        )

    @staticmethod
    def _authenticated_repository_captures(
        run: Mapping[str, Any],
        definition: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
        artifacts: Mapping[str, Mapping[str, Any]],
        baseline: Mapping[str, Any] | None,
    ) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        artifact_sequences = ProcessRunInspectorService._latest_artifact_sequences(
            records
        )
        captures: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for record in records:
            event = record.get("event") or {}
            if event.get("event_type") != "repository_state_captured":
                continue
            details = event.get("details") or {}
            artifact_id = str(details.get("artifact_id") or "")
            artifact = artifacts.get(artifact_id)
            target_binding = details.get("target_binding")
            node = nodes.get(record.get("node_id"))
            if (
                record.get("record_type") != "event"
                or set(details) != {
                    "phase", "artifact_id", "identity_digest", "target_binding",
                    "operation", "approved_plan_digest",
                }
                or details.get("phase") not in {"pre_action", "post_action"}
                or artifact is None
                or artifact_id not in record.get("artifact_ids", [])
                or artifact_sequences.get(artifact_id, -1) >= record["sequence"]
                or artifact.get("role") != "working"
                or artifact.get("media_type")
                != "application/vnd.ora.repository-state+json"
                or artifact.get("identity", {}).get("kind") != "composite"
                or artifact.get("identity", {}).get("digest")
                != details.get("identity_digest")
                or not isinstance(target_binding, Mapping)
                or set(target_binding) != {"locator", "baseline_identity_digest"}
                or artifact.get("locator") != target_binding.get("locator")
                or artifact.get("lineage", {}).get("producing_node_id")
                != record.get("node_id")
                or details.get("approved_plan_digest")
                != run["contracts"]["approved_plan"]["digest"]
                or node is None
                or node.get("kind") != "action"
                or node.get("external_effect") is not True
                or node.get("operation") != details.get("operation")
            ):
                raise ProcessRunInspectorIntegrityError(
                    "repository state capture does not authenticate its target lineage"
                )
            if baseline is not None and (
                target_binding["locator"] != baseline["locator"]
                or target_binding["baseline_identity_digest"]
                != baseline["identity"]["digest"]
            ):
                raise ProcessRunInspectorIntegrityError(
                    "repository state capture differs from the approved target binding"
                )
            captures.append((record, artifact))
        return captures

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
        target_groups = self._repository_target_groups(candidates, sequences)
        captures = self._authenticated_repository_captures(
            run, definition, records, artifacts, baseline
        )

        approved_locator = (
            copy.deepcopy(baseline["locator"]) if baseline is not None else None
        )
        capture_locators = {
            json.dumps(
                artifact["locator"], sort_keys=True, separators=(",", ":")
            )
            for _record, artifact in captures
        }
        if approved_locator is None and len(capture_locators) == 1:
            approved_locator = copy.deepcopy(captures[-1][1]["locator"])
        if approved_locator is None and len(target_groups) == 1:
            approved_locator = copy.deepcopy(target_groups[0]["locator"])
        if approved_locator is None:
            if not target_groups:
                return None
            return {
                "locator": None,
                "expected": None,
                "current_identity_digest": None,
                "state": "ambiguous_unbound_targets",
                "current": False,
                "evidence_current": False,
                "reason": (
                    "Multiple repository targets exist without an approved baseline "
                    "or unique runtime-issued mutation lineage."
                ),
                "candidate_targets": target_groups,
                "other_targets": target_groups,
                "file_changes_from_approved_baseline": _file_changes(None, None),
                "git": {"baseline_head": None, "current_head": None},
            }

        target_candidates = [
            artifact for artifact in candidates
            if artifact["locator"] == approved_locator
        ]
        target_captures = [
            (record, artifact) for record, artifact in captures
            if artifact["locator"] == approved_locator
        ]
        expected_artifact = max(
            (artifact for _record, artifact in target_captures),
            key=lambda item: sequences.get(item["artifact_id"], -1),
            default=None,
        )
        if expected_artifact is None and baseline is None:
            expected_artifact = max(
                (
                    artifact for artifact in target_candidates
                    if artifact["role"] == "result"
                ),
                key=lambda item: sequences.get(item["artifact_id"], -1),
                default=None,
            )

        other_targets = [
            group for group in target_groups
            if group["locator"] != approved_locator
        ]

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
            expected_artifact = max(
                target_candidates,
                key=lambda item: sequences.get(item["artifact_id"], -1),
                default=None,
            )
            if expected_artifact is None:
                return None
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
            "candidate_targets": target_groups,
            "other_targets": other_targets,
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
        telemetry = self._deterministic_telemetry(
            run, definition, records, artifact_rows,
        )
        telemetry["quality_evaluation"] = {
            "mode": "opt_in_failure_or_handoff_only",
            "eligibility": self._quality_eligibility(run, definition, records),
            "history": self._quality_evaluations(run, records),
            "authority_effect": "none",
        }

        transitions = [
            copy.deepcopy(record) for record in records
            if record["record_type"] == "transition"
        ]
        governed_decisions = self._governed_decisions(run, definition, records)
        governed_decision_record_ids = {
            decision["record_id"] for decision in governed_decisions
        }
        decision_events = []
        for record in records:
            event = record.get("event") or {}
            details = event.get("details") or {}
            observation_type = str(details.get("observation_type") or "")
            if (
                record["record_id"] in governed_decision_record_ids
                or
                event.get("event_type") in {
                    "final_review_completed", "delegation_activated",
                    "external_action_authorized", "authority_request_resolved",
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
            "telemetry": {
                "elapsed_seconds": telemetry["elapsed_seconds"],
                "estimated_remaining_seconds": telemetry[
                    "estimated_remaining_seconds"
                ],
                "estimate_reason": telemetry["estimate_reason"],
                "attempts": copy.deepcopy(telemetry["attempts"]),
                "usage": copy.deepcopy(telemetry["usage"]),
                "artifacts": copy.deepcopy(telemetry["artifacts"]),
                "last_error": copy.deepcopy(telemetry["last_error"]),
                "health": copy.deepcopy(telemetry["health"]),
                "liveness": copy.deepcopy(telemetry["liveness"]),
                "quality_evaluation": copy.deepcopy(
                    telemetry["quality_evaluation"]
                ),
            },
            "controls": copy.deepcopy(telemetry["controls"]),
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
                "telemetry": telemetry,
            },
            "decisions": {
                "transitions": transitions,
                "decision_events": decision_events,
                "governed_decisions": governed_decisions,
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


class ProcessRunTelemetryService:
    """Opt-in, authority-inert quality evaluation for eligible Run seams."""

    _IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")

    def __init__(
        self,
        *,
        runtime: GovernedProcessRuntime | None = None,
        evaluator: Callable[
            [Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
        ] | None = None,
    ) -> None:
        self.runtime = runtime or GovernedProcessRuntime()
        self.evaluator = evaluator or _default_quality_evaluator

    @staticmethod
    def _evaluator_binding(
        run: Mapping[str, Any],
        definition: Mapping[str, Any],
    ) -> dict[str, Any]:
        context = run.get("input_bindings", {}).get("execution_context")
        resolutions = (
            context.get("model_resolutions")
            if isinstance(context, Mapping) else None
        )
        nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
        current = nodes[run["current_node_id"]]
        selected = None
        resolution_key = None
        if isinstance(resolutions, Mapping) and resolutions:
            operation = current.get("operation")
            if operation in resolutions:
                resolution_key = str(operation)
                selected = resolutions[operation]
            else:
                resolution_key = sorted(str(key) for key in resolutions)[0]
                selected = resolutions[resolution_key]
        selected_value = (
            selected.get("selected") if isinstance(selected, Mapping) else None
        )
        return {
            "kind": "exact_run_model_profile",
            "resolution_key": resolution_key,
            "runtime_name": (
                selected_value.get("runtime_name")
                if isinstance(selected_value, Mapping) else None
            ),
            "model_profile_digest": (
                selected_value.get("digest")
                if isinstance(selected_value, Mapping) else None
            ),
            "execution_context_binding_digest": (
                context.get("binding_digest")
                if isinstance(context, Mapping) else None
            ),
        }

    def evaluate(
        self,
        run_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not self._IDEMPOTENCY_RE.fullmatch(str(idempotency_key or "")):
            raise ProcessRunTelemetryInputRequired(
                "quality evaluation idempotency key is invalid"
            )
        run = self.runtime.load_run(run_id)
        definition = self.runtime.load_definition(run_id)
        records = self.runtime.load_records(run_id)
        prior = [
            record for record in records
            if (record.get("event") or {}).get("event_type")
            == "process_quality_evaluation_started"
            and (record.get("event") or {}).get("details", {}).get(
                "idempotency_key"
            ) == idempotency_key
        ]
        if prior:
            if len(prior) != 1:
                raise ProcessRunInspectorIntegrityError(
                    "quality evaluation retry identity is ambiguous"
                )
            history = ProcessRunInspectorService._quality_evaluations(run, records)
            row = next(
                item for item in history
                if item["evaluation_id"]
                == prior[0]["event"]["details"]["evaluation_id"]
            )
            return {"status": "idempotent_retry", "evaluation": row}

        eligibility = ProcessRunInspectorService._quality_eligibility(
            run, definition, records,
        )
        if not eligibility["eligible"]:
            raise ProcessRunTelemetryConflict(
                "quality evaluation is available only at a human handoff or output failure"
            )
        source_records = [
            record for record in records
            if (record.get("event") or {}).get("event_type") not in {
                "process_quality_evaluation_started",
                "process_quality_evaluation_completed",
                "process_quality_evaluation_failed",
            }
        ]
        source_sequence = int(source_records[-1]["sequence"])
        artifacts = []
        for artifact_id in run["artifact_ids"]:
            artifact = self.runtime.load_artifact(run_id, artifact_id)
            artifacts.append({
                "artifact_id": artifact_id,
                "role": artifact["role"],
                "identity_digest": artifact["identity"]["digest"],
                "producing_node_id": artifact["lineage"]["producing_node_id"],
            })
        package = {
            "schema_version": "ora.process-quality-evaluation-subject/1.0",
            "run_id": run_id,
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "run_state": run["state"],
            "current_node_id": run["current_node_id"],
            "eligible_reason": eligibility["reason"],
            "source_record_id": eligibility["source_record_id"],
            "source_sequence": source_sequence,
            "artifacts": artifacts,
            "timeline": [
                ProcessRunInspectorService._record_summary(record)
                for record in source_records[-50:]
            ],
        }
        subject_digest = _digest_json(package)
        binding = self._evaluator_binding(run, definition)
        evaluation_id = "quality-" + hashlib.sha256(
            f"{run_id}\0{idempotency_key}\0{subject_digest}".encode("utf-8")
        ).hexdigest()[:32]
        common = {
            "run_id": run_id,
            "definition_ref": copy.deepcopy(run["definition_ref"]),
            "evaluation_id": evaluation_id,
            "idempotency_key": idempotency_key,
            "subject_digest": subject_digest,
            "eligible_reason": eligibility["reason"],
            "source_record_id": eligibility["source_record_id"],
            "source_sequence": source_sequence,
            "evaluator_binding": binding,
        }
        start = self.runtime.record_process_quality_evaluation(
            run_id,
            "process_quality_evaluation_started",
            common,
            node_id=run["current_node_id"],
        )
        try:
            verdict = _parse_quality_verdict(
                self.evaluator(copy.deepcopy(package), copy.deepcopy(binding))
            )
        except Exception as exc:
            error_body = {
                "error_type": type(exc).__name__,
                "error": str(exc)[:1000],
            }
            failed = self.runtime.record_process_quality_evaluation(
                run_id,
                "process_quality_evaluation_failed",
                {
                    **common,
                    "evaluation_start_record_id": start["record_id"],
                    "error_type": error_body["error_type"],
                    "error_digest": _digest_json(error_body),
                },
                node_id=run["current_node_id"],
            )
            return {
                "status": "failed",
                "evaluation": {
                    "evaluation_id": evaluation_id,
                    "error_type": error_body["error_type"],
                    "record_ids": [start["record_id"], failed["record_id"]],
                    "authority_effect": "none",
                },
            }
        completed = self.runtime.record_process_quality_evaluation(
            run_id,
            "process_quality_evaluation_completed",
            {
                **common,
                "evaluation_start_record_id": start["record_id"],
                "response_digest": _digest_json(verdict),
                "verdict": verdict,
            },
            node_id=run["current_node_id"],
        )
        return {
            "status": "completed",
            "evaluation": {
                "evaluation_id": evaluation_id,
                "verdict": verdict,
                "record_ids": [start["record_id"], completed["record_id"]],
                "authority_effect": "none",
            },
        }


__all__ = [
    "INSPECTOR_SCHEMA_VERSION",
    "INSPECTOR_VIEWS",
    "ProcessRunInspectorError",
    "ProcessRunInspectorIntegrityError",
    "ProcessRunInspectorService",
    "ProcessRunTelemetryConflict",
    "ProcessRunTelemetryInputRequired",
    "ProcessRunTelemetryService",
]
