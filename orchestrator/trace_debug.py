"""Trace-backed P-Debug support for Chunk 3.

This module is intentionally mechanical: exact trace refs in, bounded debug
context out. It never guesses a trace target, never applies corrections, and
never executes tool/external-action replay.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import threading
import time
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import runtime_paths as _rp  # type: ignore
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp  # type: ignore
try:
    import pipeline_trace  # type: ignore
except ImportError:  # pragma: no cover
    from orchestrator import pipeline_trace  # type: ignore

CONTRACT_SCHEMA_VERSION = 1
MAX_CONTRACT_BYTES = 64 * 1024
TRACE_DEBUG_LIBRARY_ENABLED_ENV = "ORA_TRACE_DEBUG_LIBRARY"
TRACE_DEBUG_NL_ENABLED_ENV = "ORA_TRACE_DEBUG_NL"
_APPROVAL_TTL_SECONDS = 10 * 60
MAX_DEBUG_CONTEXT_CHARS = 180_000
MAX_DEBUG_STRING_CHARS = 8_000
MAX_DEBUG_CHILDREN = 8
MAX_DEBUG_DEPTH = 2
MAX_PROBE_DELTA_CHARS = 2000
_APPROVALS: dict[str, dict[str, Any]] = {}
_APPROVAL_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _enabled(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no", "disabled"}


def trace_debug_nl_enabled() -> bool:
    return _enabled(TRACE_DEBUG_NL_ENABLED_ENV, default=False)


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data: Any) -> str:
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


def _framework_source_digest(framework: Any) -> str | None:
    """Hash the execution-time framework source without persisting its body."""
    source = None
    for attr in ("raw_markdown", "text", "content", "source", "raw_text"):
        value = getattr(framework, attr, None)
        if isinstance(value, str) and value:
            source = value.encode("utf-8")
            break
    if source is None:
        return None
    return hashlib.sha256(source).hexdigest()


def _framework_fingerprint(framework: Any) -> str:
    return digest({
        "framework_id": getattr(framework, "name", ""),
        "framework_path": getattr(framework, "file_path", ""),
        "framework_source_sha256": _framework_source_digest(framework),
    })


def _contract_or_failure(kind: str, fields: dict[str, Any]) -> dict[str, Any]:
    encoded = _canonical(fields).encode("utf-8")
    if len(encoded) > MAX_CONTRACT_BYTES:
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "kind": kind,
            "capture_status": "failed",
            "error": f"contract too large: {len(encoded)} bytes > {MAX_CONTRACT_BYTES}",
        }
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "kind": kind,
        "capture_status": "captured",
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
        "canonical_fields": fields,
    }


def framework_contract_snapshot(framework: Any, milestone: Any, *, selected_mode: str | None = None,
                                framework_fingerprint: str | None = None) -> dict[str, Any]:
    framework_id = getattr(framework, "name", "")
    framework_path = getattr(framework, "file_path", "")
    fields = {
        "framework_id": framework_id,
        "framework_path": framework_path,
        "framework_fingerprint": framework_fingerprint or _framework_fingerprint(framework),
        "mode": selected_mode or getattr(milestone, "mode", None) or "all",
        "milestone_id": getattr(milestone, "id", ""),
        "milestone_name": getattr(milestone, "name", ""),
        "endpoint_produced": getattr(milestone, "endpoint_produced", ""),
        "verification_criterion": getattr(milestone, "verification_criterion", ""),
        "drift_check_question": getattr(milestone, "drift_check_question", ""),
        "output_format": getattr(milestone, "output_format", ""),
        "gear": getattr(milestone, "gear", None),
        "layers_covered": list(getattr(milestone, "layers_covered", []) or []),
        "required_prior": list(getattr(milestone, "required_prior", []) or []),
        "conditional_layers": getattr(milestone, "conditional_layers", None),
    }
    return _contract_or_failure("framework-milestone", fields)


def framework_contract_bundle(framework: Any, milestones: list[Any], *, selected_mode: str | None = None) -> dict[str, Any]:
    framework_fingerprint = _framework_fingerprint(framework)
    child_snapshots = [framework_contract_snapshot(
        framework, m, selected_mode=selected_mode,
        framework_fingerprint=framework_fingerprint,
    ) for m in milestones]
    failures = [s for s in child_snapshots if s.get("capture_status") != "captured"]
    if failures:
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "kind": "framework-run",
            "capture_status": "failed",
            "error": "one or more milestone contracts unavailable",
            "child_statuses": [
                {
                    "milestone_id": (s.get("canonical_fields") or {}).get("milestone_id"),
                    "capture_status": s.get("capture_status"),
                    "error": s.get("error"),
                }
                for s in child_snapshots
            ],
        }
    fields = {
        "framework_id": getattr(framework, "name", ""),
        "framework_path": getattr(framework, "file_path", ""),
        "framework_fingerprint": framework_fingerprint,
        "mode": selected_mode or "all",
        "milestones": [s["canonical_fields"] for s in child_snapshots],
    }
    return _contract_or_failure("framework-run", fields)


def extract_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.M | re.I)
    match = pattern.search(text or "")
    if not match:
        return ""
    start = match.end()
    next_h2 = re.search(r"^##\s+", text[start:], re.M)
    end = start + next_h2.start() if next_h2 else len(text)
    return text[start:end].strip()


def mode_contract_snapshot(mode_name: str, mode_text: str, gear: int | None) -> dict[str, Any]:
    criteria = extract_markdown_section(mode_text, "VERIFICATION CRITERIA")
    fields = {
        "mode": mode_name,
        "gear": gear,
        "verification_criteria": criteria,
    }
    if not criteria:
        return {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "kind": "mode-verification",
            "capture_status": "failed",
            "error": "mode verification criteria unavailable",
            "canonical_fields": fields,
        }
    return _contract_or_failure("mode-verification", fields)


def refresh_mode_contract_snapshot(trace_dir: str | None, mode_name: str,
                                   mode_text: str, fallback_gear: int | None) -> None:
    """Capture the loaded mode against the gear actually written by the run."""
    gear = fallback_gear
    try:
        path = Path(trace_dir or "") / "step-health.json"
        if path.is_file() and not path.is_symlink():
            payload, error = pipeline_trace._read_json_limited_no_follow(path, 256 * 1024)  # type: ignore[attr-defined]
            if not error and isinstance(payload, dict) and isinstance(payload.get("gear"), int):
                gear = payload["gear"]
    except Exception:
        pass
    record_contract_snapshot(trace_dir, mode_contract_snapshot(mode_name, mode_text, gear))


def record_contract_snapshot(trace_dir: str | None, snapshot: dict[str, Any]) -> None:
    if not trace_dir:
        return
    if snapshot.get("capture_status") == "captured":
        pipeline_trace.update_manifest_fields(trace_dir, contract_snapshot=snapshot, contract_capture_error=None)
    else:
        pipeline_trace.update_manifest_fields(trace_dir, contract_snapshot=None, contract_capture_error=snapshot)


def _parts(trace_ref: str | None) -> tuple[str, str] | None:
    if not isinstance(trace_ref, str):
        return None
    ref = trace_ref.strip().replace("\\", "/")
    bits = [b for b in ref.split("/") if b]
    if len(bits) != 2 or any(b in {".", ".."} for b in bits):
        return None
    if ref.startswith("/") or ref.startswith("../") or "/../" in ref:
        return None
    return bits[0], bits[1]


def _validate_same_conversation_ref(trace_ref: str, conversation_id: str | None) -> tuple[bool, str]:
    parts = _parts(trace_ref)
    if parts is None:
        return False, "malformed trace_ref"
    if (conversation_id or "") != parts[0]:
        return False, "trace_debug conversation_id must match trace_ref conversation"
    return True, ""


def validate_same_conversation(trace_ref: str, conversation_id: str | None) -> tuple[bool, str]:
    ok, error = _validate_same_conversation_ref(trace_ref, conversation_id)
    if not ok:
        return ok, error
    with _rp.conversation_lifecycle_lock(conversation_id or ""):
        if pipeline_trace.resolve_trace_ref(trace_ref) is None:
            return False, "trace_ref not found"
    return True, ""


def _contract_from_manifest(manifest: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    snap = manifest.get("contract_snapshot")
    if isinstance(snap, dict) and snap.get("capture_status") == "captured":
        fields = snap.get("canonical_fields")
        if not isinstance(fields, dict):
            return None, "captured contract has no canonical fields"
        encoded = _canonical(fields).encode("utf-8")
        if len(encoded) > MAX_CONTRACT_BYTES:
            return None, "execution-time contract exceeds preservation limit"
        expected = hashlib.sha256(encoded).hexdigest()
        if snap.get("fingerprint") != expected:
            return None, "execution-time contract fingerprint mismatch"
        return snap, None
    err = manifest.get("contract_capture_error")
    if isinstance(err, dict):
        return None, err.get("error") or "contract unavailable"
    return None, "execution-time contract unavailable"


_ALLOWED_VERDICTS = {"DEFECT_LOCALIZED", "BAD_DRAW", "CONTRACT_MISMATCH", "NO_DEFECT"}
_LEARNING_SCHEMA_KEYS = {
    "schema_version", "created_at", "conversation_id", "trace_ref", "framework_id",
    "framework_fingerprint", "contract_fingerprint", "mode", "gear", "verdict",
    "failing_step", "verification_probe", "root_cause", "correction_lane",
    "symptom_signature", "correction_summary", "escalation_boundary",
}
_LEARNING_SCHEMA_VERSION = 1
_LEARNING_ROOT_CAUSES = frozenset({
    "retrieval gap", "instruction conflict", "evaluator miss",
    "consolidation compression loss", "model bad-draw", "config mismatch",
    "framework underspecification", "none", "unknown",
})
_LEARNING_TEXT_LIMITS = {
    "framework_id": 200, "mode": 100, "failing_step": 200,
    "verification_probe": 400, "correction_lane": 200,
    "escalation_boundary": 400, "symptom_signature": 600,
    "correction_summary": 1000,
}
_LEARNING_STATUS = {
    "malformed_records": 0,
    "unsupported_schema_records": 0,
}


def _read_jsonl_records_locked(trace_dir: Path, name: str, limit: int = 256 * 1024) -> list[dict[str, Any]]:
    path = trace_dir / name
    if not path.exists() or path.is_symlink() or not path.is_file():
        return []
    text, error = pipeline_trace._read_text_limited_no_follow(path, limit)  # type: ignore[attr-defined]
    if error or text is None:
        return [{"_read_error": error or "unavailable"}]
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def _semantic_state_from_step(step: dict[str, Any]) -> str:
    payload = step.get("payload") if isinstance(step, dict) else None
    if not isinstance(payload, dict):
        return "unknown"
    if isinstance(payload.get("ok"), bool):
        return "pass" if payload["ok"] else "fail"
    for key in ("semantic_status", "semantic_boundary", "evaluation", "verdict"):
        value = payload.get(key)
        if isinstance(value, str):
            low = value.strip().lower()
            if low in {"pass", "passed", "ok", "healthy", "success", "satisfied"}:
                return "pass"
            if low in {"fail", "failed", "error", "unhealthy", "unsatisfied"}:
                return "fail"
    return "unknown"


def _step_health_states(steps: list[dict[str, Any]]) -> dict[str, str]:
    health_step = next((s for s in steps if s.get("step_name") == "step-health"), None)
    payload = health_step.get("payload") if isinstance(health_step, dict) else None
    health = payload.get("step_health") if isinstance(payload, dict) else None
    if not isinstance(health, dict):
        return {}
    states: dict[str, str] = {}
    for name, value in health.items():
        ok = value.get("ok") if isinstance(value, dict) else (
            value[0] if isinstance(value, (list, tuple)) and value else None)
        if isinstance(ok, bool):
            states[str(name)] = "pass" if ok else "fail"
    return states


def _boundary_table(manifest: dict[str, Any], steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected, actual, _derived, missing, unexpected = pipeline_trace._manifest_step_sets(manifest)  # type: ignore[attr-defined]
    by_name = {s.get("step_name"): s for s in steps if isinstance(s, dict)}
    health_states = _step_health_states(steps)
    ordered: list[str] = []
    for name in expected + actual:
        if name.startswith("step") and name != "step-health" and name not in ordered:
            ordered.append(name)
    rows: list[dict[str, Any]] = []
    for idx, name in enumerate(ordered):
        step = by_name.get(name)
        if name in missing:
            structural = "fail"
            evidence = ["manifest expected this step but it is absent"]
        elif not step:
            structural = "unknown"
            evidence = ["step projection unavailable"]
        elif step.get("errors"):
            structural = "fail"
            evidence = list(step.get("errors") or [])[:3]
        elif step.get("json_present") or step.get("markdown_present"):
            structural = "pass"
            evidence = ["manifest lists step and bounded projection is readable"]
        else:
            structural = "unknown"
            evidence = ["manifest lists step but no readable artifact was projected"]
        health_state = health_states.get(name)
        semantic = _semantic_state_from_step(step or {})
        if health_state is not None:
            semantic = health_state
            evidence.append(f"step-health: {health_state}")
        rows.append({
            "boundary_index": idx,
            "step_name": name,
            "structural_evidence": structural,
            "semantic_evidence": semantic,
            "unexpected": name in unexpected,
            "evidence": evidence,
        })
    return rows


def _last_before_first_failure(boundary: list[dict[str, Any]], evidence_key: str) -> str | None:
    last_good = None
    for row in boundary:
        state = row.get(evidence_key)
        if state == "fail":
            return last_good
        if state == "pass":
            last_good = row.get("step_name")
    return last_good


def _trace_walk_snapshot_locked(trace_ref: str, *, depth: int = 0,
                                expected_conversation_id: str | None = None,
                                expected_parent_ref: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    ctx = pipeline_trace._safe_projection_context_locked(trace_ref)  # type: ignore[attr-defined]
    if ctx is None:
        return None, "trace_ref not found"
    trace_dir, raw_manifest, conversation_id, _turn = ctx
    if expected_conversation_id and conversation_id != expected_conversation_id:
        return None, "child trace conversation mismatch"
    if expected_parent_ref and raw_manifest.get("parent_trace_ref") != expected_parent_ref:
        return None, "child trace reciprocal parent ref missing"
    if raw_manifest.get("conversation_id") not in (None, conversation_id):
        return None, "trace manifest conversation mismatch"
    manifest = pipeline_trace._trace_manifest_projection_from_manifest(trace_ref, raw_manifest)  # type: ignore[attr-defined]
    steps: list[dict[str, Any]] = []
    for item in manifest.get("steps") or []:
        name = item.get("step_name") if isinstance(item, dict) else None
        if not name:
            continue
        projection = pipeline_trace._trace_step_projection_locked(trace_ref, name, trace_dir, raw_manifest)  # type: ignore[attr-defined]
        if projection is not None:
            steps.append(projection)
    model_calls = _read_jsonl_records_locked(trace_dir, "model-call-config.jsonl")
    children: list[dict[str, Any]] = []
    child_refs = raw_manifest.get("child_trace_refs")
    if not isinstance(child_refs, list):
        child_refs = []
    if depth < MAX_DEBUG_DEPTH:
        for child_ref in child_refs[:MAX_DEBUG_CHILDREN]:
            if not isinstance(child_ref, str):
                continue
            child_parts = _parts(child_ref)
            if child_parts is None or child_parts[0] != conversation_id:
                children.append({
                    "trace_ref": child_ref,
                    "status": "stale_or_unavailable",
                    "error": "child trace conversation mismatch",
                })
                continue
            child_walk, child_error = _trace_walk_snapshot_locked(
                child_ref,
                depth=depth + 1,
                expected_conversation_id=conversation_id,
                expected_parent_ref=trace_ref,
            )
            if child_walk is None:
                children.append({"trace_ref": child_ref, "status": "stale_or_unavailable", "error": child_error})
            else:
                children.append(child_walk)
        if len(child_refs) > MAX_DEBUG_CHILDREN:
            children.append({
                "_evidence_unavailable": "child trace count limit reached",
                "omitted_child_count": len(child_refs) - MAX_DEBUG_CHILDREN,
            })
    elif raw_manifest.get("child_trace_refs"):
        children.append({"_evidence_unavailable": "child trace recursion depth limit reached"})
    probe_traces: list[dict[str, Any]] = []
    probe_refs = raw_manifest.get("probe_trace_refs")
    if not isinstance(probe_refs, list):
        probe_refs = []
    if depth < MAX_DEBUG_DEPTH:
        for probe_ref in probe_refs[:MAX_DEBUG_CHILDREN]:
            if not isinstance(probe_ref, str):
                continue
            probe_walk, probe_error = _trace_walk_snapshot_locked(
                probe_ref,
                depth=depth + 1,
                expected_conversation_id=conversation_id,
            )
            if probe_walk is None:
                probe_traces.append({"trace_ref": probe_ref, "status": "stale_or_unavailable", "error": probe_error})
            elif probe_walk.get("manifest", {}).get("investigates_trace_ref") != trace_ref:
                probe_traces.append({"trace_ref": probe_ref, "status": "stale_or_unavailable", "error": "probe reciprocal investigation ref missing"})
            else:
                probe_traces.append(probe_walk)
        if len(probe_refs) > MAX_DEBUG_CHILDREN:
            probe_traces.append({
                "_evidence_unavailable": "probe trace count limit reached",
                "omitted_probe_count": len(probe_refs) - MAX_DEBUG_CHILDREN,
            })
    elif probe_refs:
        probe_traces.append({"_evidence_unavailable": "probe trace recursion depth limit reached"})
    boundary = _boundary_table(raw_manifest, steps)
    return {
        "trace_ref": trace_ref,
        "manifest": manifest,
        "raw_manifest_fields": {
            "contract_snapshot": (
                raw_manifest.get("contract_snapshot")
                if _contract_from_manifest(raw_manifest)[0] is not None
                else None
            ),
            "contract_capture_error": (
                raw_manifest.get("contract_capture_error")
                or (_contract_from_manifest(raw_manifest)[1]
                    if raw_manifest.get("contract_snapshot") is not None else None)
            ),
        },
        "steps": steps,
        "step_health": next((s for s in steps if s.get("step_name") == "step-health"), None),
        "model_call_configs": model_calls,
        "probe_events": _read_jsonl_records_locked(trace_dir, "trace-probe-events.jsonl"),
        "child_traces": children,
        "probe_traces": probe_traces,
        "boundary_table": boundary,
        "boundary_summary": {
            "structural_last_known_good": _last_before_first_failure(boundary, "structural_evidence"),
            "first_structural_failure": next((r.get("step_name") for r in boundary if r.get("structural_evidence") == "fail"), None),
            "semantic_last_known_good": _last_before_first_failure(boundary, "semantic_evidence"),
            "first_semantic_failure": next((r.get("step_name") for r in boundary if r.get("semantic_evidence") == "fail"), None),
        },
    }, None


def _bounded_string(value: str, markers: list[dict[str, Any]], path: str, limit: int = MAX_DEBUG_STRING_CHARS) -> str:
    if len(value) <= limit:
        return value
    markers.append({"path": path, "reason": "string truncated", "original_chars": len(value), "kept_chars": limit})
    return value[:limit] + "\n[TRACE_DEBUG_EVIDENCE_TRUNCATED]"


def _bound_value(value: Any, markers: list[dict[str, Any]], path: str = "$") -> Any:
    if "contract_snapshot" in path:
        return value
    if isinstance(value, str):
        return _bounded_string(value, markers, path)
    if isinstance(value, list):
        return [_bound_value(v, markers, f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        return {k: _bound_value(v, markers, f"{path}.{k}") for k, v in value.items()}
    return value


def _strip_heavy_payloads(value: Any, markers: list[dict[str, Any]]) -> Any:
    if isinstance(value, list):
        return [_strip_heavy_payloads(v, markers) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "contract_snapshot":
                out[k] = v
                continue
            if k in {"markdown", "raw_response", "system_prompt", "user_message", "messages"}:
                text = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v
                out[k] = _bounded_string(text, markers, f"aggregate.{k}", 1200)
                if len(text) > 1200:
                    markers.append({"path": f"aggregate.{k}", "reason": "aggregate budget pressure"})
            elif k == "payload" and isinstance(v, dict):
                light = {pk: pv for pk, pv in v.items() if pk in {"semantic_status", "verdict", "ok", "reason", "endpoint"}}
                out[k] = light or {"_evidence_unavailable": "payload omitted by aggregate trace-debug budget"}
            else:
                out[k] = _strip_heavy_payloads(v, markers)
        return out
    return value


def _apply_debug_budget(context: dict[str, Any]) -> dict[str, Any]:
    markers: list[dict[str, Any]] = []
    bounded = _bound_value(context, markers)
    encoded = json.dumps(bounded, ensure_ascii=False, default=str)
    if len(encoded) > MAX_DEBUG_CONTEXT_CHARS:
        bounded = _strip_heavy_payloads(bounded, markers)
        encoded = json.dumps(bounded, ensure_ascii=False, default=str)
    if len(encoded) > MAX_DEBUG_CONTEXT_CHARS:
        markers.append({"path": "$", "reason": "aggregate context truncated", "original_chars": len(encoded), "kept_chars": MAX_DEBUG_CONTEXT_CHARS})
        # Last-resort deterministic contraction preserves the manifest, boundary tables, children summaries, and markers.
        walk = bounded.get("trace_walk") if isinstance(bounded.get("trace_walk"), dict) else {}
        walk_raw = walk.get("raw_manifest_fields") if isinstance(walk.get("raw_manifest_fields"), dict) else {}
        child_summaries = []
        child_contract_omitted = False
        for index, child in enumerate(walk.get("child_traces") or []):
            if not isinstance(child, dict):
                continue
            child_raw = child.get("raw_manifest_fields") if isinstance(child.get("raw_manifest_fields"), dict) else {}
            child_raw = dict(child_raw)
            if child_raw.get("contract_snapshot") is not None:
                child_contract_omitted = True
                child_raw["contract_snapshot"] = None
                child_raw["contract_capture_error"] = "execution-time contract omitted by aggregate trace-debug budget"
                markers.append({
                    "path": f"trace_walk.child_traces[{index}].raw_manifest_fields.contract_snapshot",
                    "reason": "contract unavailable after aggregate budget contraction",
                })
            child_summaries.append({
                "trace_ref": child.get("trace_ref"),
                "manifest": child.get("manifest"),
                "raw_manifest_fields": child_raw,
                "boundary_table": child.get("boundary_table"),
                "boundary_summary": child.get("boundary_summary"),
            })
        bounded["trace_walk"] = {
            "trace_ref": walk.get("trace_ref"),
            "manifest": walk.get("manifest"),
            "raw_manifest_fields": walk_raw,
            "boundary_table": walk.get("boundary_table"),
            "boundary_summary": walk.get("boundary_summary"),
            "child_traces": child_summaries,
            "probe_traces": [
                {"trace_ref": p.get("trace_ref"), "manifest": p.get("manifest"), "boundary_table": p.get("boundary_table"), "boundary_summary": p.get("boundary_summary")}
                for p in (walk.get("probe_traces") or []) if isinstance(p, dict)
            ],
            "_evidence_unavailable": "heavy step payloads omitted by aggregate trace-debug budget",
        }
        if child_contract_omitted and not bounded.get("contract_unavailable"):
            bounded["contract_unavailable"] = "one or more child execution-time contracts omitted by aggregate trace-debug budget"
    bounded["evidence_budget"] = {
        "max_context_chars": MAX_DEBUG_CONTEXT_CHARS,
        "markers": markers,
        "truncated_or_unavailable": bool(markers),
    }
    return bounded


def _load_trace_walk_locked(trace_ref: str, conversation_id: str) -> tuple[dict[str, Any] | None, str | None]:
    with _rp.conversation_lifecycle_lock(conversation_id):
        return _trace_walk_snapshot_locked(trace_ref, depth=0)


def _prior_learning(trace_ref: str, manifest: dict[str, Any], limit: int = 5,
                    *, framework_fingerprint: str | None = None,
                    contract_fingerprint: str | None = None) -> list[dict[str, Any]]:
    framework_id = manifest.get("framework_id")
    mode = manifest.get("mode")
    out: list[dict[str, Any]] = []
    for rec in list_learning_entries():
        if rec.get("trace_ref") == trace_ref:
            continue
        if framework_id and rec.get("framework_id") != framework_id:
            continue
        if framework_fingerprint and rec.get("framework_fingerprint") != framework_fingerprint:
            continue
        if contract_fingerprint and rec.get("contract_fingerprint") != contract_fingerprint:
            continue
        if mode and rec.get("mode") not in (None, "", mode):
            continue
        out.append({k: rec.get(k) for k in _LEARNING_SCHEMA_KEYS | {"recurrence_count"} if k in rec})
        if len(out) >= limit:
            break
    return out


def parse_natural_language_request(text: str) -> dict[str, Any] | None:
    if not trace_debug_nl_enabled():
        return None
    raw = text or ""
    if not re.search(r"\b(trace|debug|investigate|diagnos(?:e|is)|why)\b", raw, re.I):
        return None
    refs = re.findall(r"\b([A-Za-z0-9_.:-]+/[A-Za-z0-9_.:-]+)\b", raw)
    unique = []
    for ref in refs:
        if ref not in unique:
            unique.append(ref)
    if len(unique) != 1:
        return None
    return {"trace_ref": unique[0], "source": "natural-language"}


def build_debug_prompt(payload: dict[str, Any], *, conversation_id: str) -> tuple[str | None, dict[str, Any]]:
    trace_ref = str(payload.get("trace_ref") or "").strip()
    ok, error = _validate_same_conversation_ref(trace_ref, conversation_id)
    if not ok:
        return None, {"error": error, "trace_ref": trace_ref}
    walk, walk_error = _load_trace_walk_locked(trace_ref, conversation_id)
    if walk is None:
        return None, {"error": walk_error or "trace_ref not found", "trace_ref": trace_ref}
    raw_fields = walk.get("raw_manifest_fields") or {}
    contract, contract_error = _contract_from_manifest(raw_fields)
    step_hint = str(payload.get("step_hint") or payload.get("step") or "").strip()
    step_projection = None
    if step_hint:
        step_projection = next((s for s in walk.get("steps") or [] if s.get("step_name") == step_hint), None)
        if step_projection is None:
            return None, {"error": "malformed or unavailable step_hint", "trace_ref": trace_ref, "step_hint": step_hint}
    symptom = str(payload.get("symptom") or "").strip()[:2000]
    manifest = walk.get("manifest") or {}
    contract_fields = (contract or {}).get("canonical_fields") if isinstance(contract, dict) else {}
    debug_context = {
        "trace_ref": trace_ref,
        "symptom": symptom,
        "trace_walk": walk,
        "contract_snapshot": contract,
        "contract_unavailable": contract_error,
        "selected_step": step_projection,
        "prior_learning": _prior_learning(
            trace_ref,
            manifest,
            framework_fingerprint=(contract_fields or {}).get("framework_fingerprint"),
            contract_fingerprint=(contract or {}).get("fingerprint") if isinstance(contract, dict) else None,
        ),
    }
    debug_context = _apply_debug_budget(debug_context)
    prompt = (
        "Mode P-Debug. Perform a trace-backed process investigation using ONLY the structured evidence below.\n"
        "You must walk every manifest-listed step, step-health artifact, model-call config, and child trace before verdict.\n"
        "If contract_unavailable is non-empty, emit CONTRACT_UNAVAILABLE and withhold DEFECT_LOCALIZED/BAD_DRAW/CONTRACT_MISMATCH/NO_DEFECT.\n"
        "Separate structural evidence from semantic evidence. Each boundary must be pass, fail, or unknown.\n"
        "Do not infer last-known-good from mere execution when semantic evidence is unknown.\n"
        "Valid four-way verdicts are DEFECT_LOCALIZED, BAD_DRAW, CONTRACT_MISMATCH, and NO_DEFECT. CONTRACT_UNAVAILABLE is a terminal diagnostic, not a verdict; emit it without a four-way verdict when the exact contract is unavailable.\n"
        "Correction bundles are recommend-only and only required for DEFECT_LOCALIZED.\n\n"
        "TRACE_DEBUG_CONTEXT_JSON:\n"
        + json.dumps(debug_context, indent=2, default=str)
    )
    return prompt, {"trace_ref": trace_ref, "step_hint": step_hint, "contract_available": contract is not None}


def parse_cli_command(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw.startswith("/trace-debug"):
        return None
    tokens = raw.split()
    if len(tokens) < 2:
        return {"error": "usage: /trace-debug <conversation/turn> [--step <step>] [--symptom <text>]"}
    payload: dict[str, Any] = {"trace_ref": tokens[1], "source": "cli"}
    if "--step" in tokens:
        idx = tokens.index("--step")
        if idx + 1 < len(tokens):
            payload["step_hint"] = tokens[idx + 1]
    if "--symptom" in tokens:
        idx = tokens.index("--symptom")
        payload["symptom"] = " ".join(tokens[idx + 1:])
    return payload



def parse_probe_cli_command(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw.startswith("/trace-probe"):
        return None
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return {"action": "error", "error": "malformed trace-probe command quoting"}
    if len(tokens) < 2:
        return {"action": "error", "error": "usage: /trace-probe prepare|approve|execute ..."}
    action = tokens[1]
    if action == "prepare":
        if len(tokens) < 4:
            return {"action": "error", "error": "usage: /trace-probe prepare <conversation/turn> <step> [--delta <text>] [--cost-ceiling <tokens>]"}
        payload: dict[str, Any] = {"action": "prepare", "trace_ref": tokens[2], "step_name": tokens[3]}
        if "--cost-ceiling" in tokens:
            idx = tokens.index("--cost-ceiling")
            if idx + 1 < len(tokens):
                payload["cost_ceiling"] = tokens[idx + 1]
        if "--delta" in tokens:
            idx = tokens.index("--delta")
            end = tokens.index("--cost-ceiling", idx + 1) if "--cost-ceiling" in tokens[idx + 1:] else len(tokens)
            payload["prompt_delta"] = " ".join(tokens[idx + 1:end])
        return payload
    if action == "approve":
        if len(tokens) < 4:
            return {"action": "error", "error": "usage: /trace-probe approve <approval_id> <approval_digest>"}
        return {"action": "approve", "approval_id": tokens[2], "approval_digest": tokens[3]}
    if action == "execute":
        if len(tokens) < 4:
            return {"action": "error", "error": "usage: /trace-probe execute <approval_id> <approval_digest>"}
        return {"action": "execute", "approval_id": tokens[2], "approval_digest": tokens[3]}
    return {"action": "error", "error": "unknown /trace-probe action"}

def build_framework_command(debug_prompt: str, config_name: str | None = None) -> str:
    cfg = f" --config {config_name}" if config_name else ""
    return f"/framework process-inference{cfg} {debug_prompt}"


def _manifest_digest(trace_ref: str) -> str:
    parts = _parts(trace_ref)
    conv = parts[0] if parts else ""
    with _rp.conversation_lifecycle_lock(conv):
        trace_dir = pipeline_trace.resolve_trace_ref(trace_ref)
        manifest = pipeline_trace.read_manifest(trace_dir) if trace_dir else None
        return digest(manifest or {})


def _step_digest(trace_ref: str, step_name: str) -> str:
    parts = _parts(trace_ref)
    conv = parts[0] if parts else ""
    with _rp.conversation_lifecycle_lock(conv):
        ctx = pipeline_trace._safe_projection_context_locked(trace_ref)  # type: ignore[attr-defined]
        if ctx is None:
            return digest({})
        trace_dir, manifest, _c, _t = ctx
        projection = pipeline_trace._trace_step_projection_locked(trace_ref, step_name, trace_dir, manifest)  # type: ignore[attr-defined]
        call_records = [
            record for record in _read_jsonl_records_locked(trace_dir, "model-call-config.jsonl")
            if record.get("step") == step_name and not record.get("_read_error")
        ]
        return digest({"projection": projection or {}, "model_call_configs": call_records})


def _messages_from_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        return [m for m in messages if isinstance(m, dict) and m.get("role") and m.get("content")]
    out: list[dict[str, str]] = []
    if payload.get("system_prompt"):
        out.append({"role": "system", "content": str(payload.get("system_prompt"))})
    user = payload.get("user_message") or payload.get("prompt") or payload.get("input")
    if user:
        out.append({"role": "user", "content": str(user)})
    return out


def _complete_messages(messages: list[dict[str, str]]) -> bool:
    return bool(messages) and any(m.get("role") == "user" and str(m.get("content") or "").strip() for m in messages)


def _effective_call_for_step(trace_dir: Path, step_name: str) -> tuple[dict[str, Any] | None, str]:
    records = [r for r in _read_jsonl_records_locked(trace_dir, "model-call-config.jsonl") if not r.get("_read_error")]
    matches = [r for r in records if r.get("step") == step_name]
    if not matches:
        return None, "no exact model-call configuration for step"
    if len(matches) != 1:
        return None, "ambiguous model-call configuration for step"
    return matches[0], ""


def _replay_envelope(trace_ref: str, step_name: str, conversation_id: str) -> tuple[dict[str, Any] | None, str]:
    with _rp.conversation_lifecycle_lock(conversation_id):
        ctx = pipeline_trace._safe_projection_context_locked(trace_ref)  # type: ignore[attr-defined]
        if ctx is None:
            return None, "trace unavailable"
        trace_dir, manifest, _c, _t = ctx
        projection = pipeline_trace._trace_step_projection_locked(trace_ref, step_name, trace_dir, manifest)  # type: ignore[attr-defined]
        if not projection:
            return None, "step unavailable"
        payload = projection.get("payload") if isinstance(projection.get("payload"), dict) else {}
        if isinstance(payload.get("model_request"), dict):
            env = dict(payload["model_request"])
            env.setdefault("messages", _messages_from_payload(payload))
            if not env.get("endpoint_id"):
                call, call_error = _effective_call_for_step(trace_dir, step_name)
                if not call:
                    return None, call_error or "effective model-call configuration absent"
                env["endpoint_id"] = call.get("endpoint_id")
        else:
            call, call_error = _effective_call_for_step(trace_dir, step_name)
            if not call:
                return None, call_error or "effective model-call configuration absent"
            env = {
                "messages": _messages_from_payload(payload),
                "provider": call.get("provider") or call.get("service") or call.get("endpoint_type"),
                "model": call.get("model_id") or call.get("endpoint_name") or call.get("endpoint_id"),
                "endpoint_id": call.get("endpoint_id"),
                "base_url_host": call.get("base_url_host"),
                "parameters": call.get("sampling") or {},
                "max_tokens": call.get("effective_max_tokens"),
                "physical_attempt": call.get("physical_attempt"),
                "attempt_index": call.get("attempt_index"),
                "endpoint_type": call.get("endpoint_type"),
            }
        if env.get("tools") or env.get("external_actions"):
            return None, "tool/external-action replay refused in Chunk 3"
        if not _complete_messages(env.get("messages") or []):
            return None, "complete replay messages absent"
        required = ["messages", "endpoint_id", "provider", "model", "parameters", "max_tokens"]
        missing = [k for k in required if env.get(k) in (None, "", [])]
        if missing:
            return None, "missing replay fields: " + ", ".join(missing)
        return env, ""


def _estimate_probe_cost(envelope: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(envelope.get("messages") or [], ensure_ascii=False, default=str)
    return {
        "estimated_input_tokens": max(1, len(text) // 4),
        "max_output_tokens": envelope.get("max_tokens"),
        "estimated_total_tokens": max(1, len(text) // 4) + int(envelope.get("max_tokens") or 0),
        "currency_cost": None,
        "cost_known": False,
    }


def _apply_prompt_delta(envelope: dict[str, Any], prompt_delta: str) -> dict[str, Any]:
    if not prompt_delta:
        return envelope
    if len(prompt_delta) > MAX_PROBE_DELTA_CHARS:
        raise ValueError(f"prompt_delta exceeds {MAX_PROBE_DELTA_CHARS} characters")
    updated = dict(envelope)
    messages = [dict(m) for m in (updated.get("messages") or []) if isinstance(m, dict)]
    messages.append({"role": "user", "content": "Counterfactual probe delta:\n" + prompt_delta})
    updated["messages"] = messages
    return updated

def _risk_gate_for_probe(request: dict[str, Any]) -> dict[str, Any]:
    description = "trace probe model-only replay for " + str(request.get("trace_ref") or "")
    try:
        try:
            import risk_gate as _rgate  # type: ignore
        except ImportError:  # pragma: no cover
            from orchestrator import risk_gate as _rgate  # type: ignore
        assigned = _rgate.assign_tier(description, request.get("conversation_id"), surface="trace-probe", record=True)
        hold, fp = _rgate.evaluate_hold(
            assigned.get("risk_tier") or "high-risk",
            conversation_id=request.get("conversation_id"),
            prompt=description,
            surface="trace-probe",
            description=description,
        )
        return {
            "risk_tier": assigned.get("risk_tier"),
            "fingerprint": fp,
            "hold": hold,
            "cleared": hold is None,
            "source": "risk_gate",
        }
    except Exception as exc:
        return {"risk_tier": "high-risk", "cleared": False, "hold": str(exc), "source": "risk_gate_error"}


def conversation_tag_for_trace_ref(trace_ref: str | None) -> str:
    parts = _parts(trace_ref)
    if parts is None:
        return ""
    try:
        with _rp.conversation_lifecycle_lock(parts[0]):
            ctx = pipeline_trace._safe_projection_context_locked(trace_ref)  # type: ignore[attr-defined]
            if ctx is None:
                return ""
            redaction = ctx[1].get("redaction_level")
            return redaction if redaction in {"private", "stealth"} else ""
    except Exception:
        return ""


def _validate_probe_origin(trace_ref: str, origin_trace_ref: str | None,
                           conversation_id: str) -> tuple[str | None, str | None]:
    """Validate an explicit trace-debug origin and its reciprocal target."""
    if not origin_trace_ref:
        return trace_ref, None
    origin = str(origin_trace_ref).strip()
    parts = _parts(origin)
    if parts is None or parts[0] != conversation_id:
        return None, "origin_trace_ref conversation mismatch"
    try:
        with _rp.conversation_lifecycle_lock(conversation_id):
            origin_ctx = pipeline_trace._safe_projection_context_locked(origin)  # type: ignore[attr-defined]
            target_ctx = pipeline_trace._safe_projection_context_locked(trace_ref)  # type: ignore[attr-defined]
            if origin_ctx is None or target_ctx is None:
                return None, "origin or investigated trace unavailable"
            origin_manifest = origin_ctx[1]
            if origin_manifest.get("trace_kind") != "trace-debug":
                return None, "origin_trace_ref must identify a trace-debug trace"
            if origin_manifest.get("investigates_trace_ref") != trace_ref:
                return None, "origin trace does not investigate trace_ref"
    except Exception as exc:
        return None, f"origin validation failed: {exc}"
    return origin, None


def approval_conversation_tag(approval_id: str, approval_digest: str) -> str:
    with _APPROVAL_LOCK:
        rec = _APPROVALS.get(approval_id)
        if not rec or rec.get("request", {}).get("approval_digest") != approval_digest:
            return ""
        return str(rec.get("request", {}).get("conversation_tag") or "")


def _record_probe_event(trace_ref: str | None, event: str, **fields: Any) -> None:
    parts = _parts(trace_ref)
    if parts is None:
        return
    try:
        with _rp.conversation_lifecycle_lock(parts[0]):
            trace_dir = pipeline_trace.resolve_trace_ref(trace_ref)
            if trace_dir:
                pipeline_trace.append_jsonl(trace_dir, "trace-probe-events.jsonl", {
                    "timestamp": _utc_now(), "event": event, **fields,
                })
    except Exception:
        pass


def _latest_debug_origin(conversation_id: str) -> str | None:
    try:
        for ref in reversed(pipeline_trace.list_trace_refs(conversation_id)):
            trace_dir = pipeline_trace.resolve_trace_ref(ref)
            manifest = pipeline_trace.read_manifest(trace_dir) if trace_dir else None
            if isinstance(manifest, dict) and manifest.get("trace_kind") == "trace-debug":
                return ref
    except Exception:
        pass
    return None


def _record_probe_rejection(conversation_id: str, req: dict[str, Any] | None,
                            error: str) -> None:
    origin = (req or {}).get("origin_trace_ref") or _latest_debug_origin(conversation_id)
    _record_probe_event(origin, "execute_rejected", status="REJECTED", error=error)


def prepare_probe(payload: dict[str, Any], *, conversation_id: str) -> dict[str, Any]:
    trace_ref = str(payload.get("trace_ref") or "").strip()
    ok, error = _validate_same_conversation_ref(trace_ref, conversation_id)
    if not ok:
        return {"ok": False, "status": "REJECTED", "error": error}
    origin_ref, origin_error = _validate_probe_origin(
        trace_ref, payload.get("origin_trace_ref"), conversation_id)
    if origin_error:
        _record_probe_event(
            trace_ref, "prepare_rejected", status="REJECTED", error=origin_error)
        return {"ok": False, "status": "REJECTED", "error": origin_error}
    step = str(payload.get("step_name") or payload.get("step_hint") or "").strip()
    envelope, reason = _replay_envelope(trace_ref, step, conversation_id)
    if not envelope:
        _record_probe_event(payload.get("origin_trace_ref") or trace_ref, "prepare_rejected", status="NOT_REPLAYABLE", error=reason)
        return {"ok": False, "status": "NOT_REPLAYABLE", "reason": reason or "complete model request envelope absent"}
    prompt_delta = str(payload.get("prompt_delta") or "")
    if len(prompt_delta) > MAX_PROBE_DELTA_CHARS:
        _record_probe_event(payload.get("origin_trace_ref") or trace_ref, "prepare_rejected", status="REJECTED", error="prompt_delta too large")
        return {"ok": False, "status": "REJECTED", "error": f"prompt_delta exceeds {MAX_PROBE_DELTA_CHARS} characters"}
    envelope = _apply_prompt_delta(envelope, prompt_delta)
    cost_estimate = _estimate_probe_cost(envelope)
    ceiling = payload.get("cost_ceiling")
    if ceiling is not None:
        try:
            if cost_estimate.get("estimated_total_tokens", 0) > int(ceiling):
                _record_probe_event(payload.get("origin_trace_ref") or trace_ref, "prepare_rejected", status="COST_EXCEEDED")
                return {"ok": False, "status": "COST_EXCEEDED", "cost_estimate": cost_estimate, "cost_ceiling": ceiling}
        except Exception:
            _record_probe_event(payload.get("origin_trace_ref") or trace_ref, "prepare_rejected", status="REJECTED", error="invalid cost_ceiling")
            return {"ok": False, "status": "REJECTED", "error": "invalid cost_ceiling"}
    request = {
        "trace_ref": trace_ref,
        "conversation_id": conversation_id,
        "step_name": step,
        "prompt_delta": prompt_delta,
        "counterfactual_probe": bool(prompt_delta),
        "envelope": envelope,
        "envelope_digest": digest(envelope),
        "manifest_digest": _manifest_digest(trace_ref),
        "step_digest": _step_digest(trace_ref, step),
        "cost_ceiling": payload.get("cost_ceiling"),
        "cost_estimate": cost_estimate,
        "expires_at": time.time() + _APPROVAL_TTL_SECONDS,
        "origin_trace_ref": origin_ref,
        "conversation_tag": str(payload.get("conversation_tag") or ""),
    }
    request["risk_decision"] = _risk_gate_for_probe(request)
    if not request["risk_decision"].get("cleared"):
        _record_probe_event(request.get("origin_trace_ref"), "prepare_rejected", status="RISK_HELD")
        return {"ok": False, "status": "RISK_HELD", "risk_decision": request["risk_decision"]}
    request["approval_digest"] = digest({k: request[k] for k in request if k != "envelope"})
    approval_id = hashlib.sha256(f"{request['approval_digest']}:{time.time_ns()}".encode()).hexdigest()[:24]
    with _APPROVAL_LOCK:
        _APPROVALS[approval_id] = {"request": request, "approved": False, "consumed": False}
    _record_probe_event(request.get("origin_trace_ref"), "prepared", status="PREPARED", approval_id=approval_id)
    return {
        "ok": True,
        "status": "PREPARED",
        "approval_id": approval_id,
        "approval_digest": request["approval_digest"],
        "expires_at": request["expires_at"],
        "cost_estimate": request["cost_estimate"],
        "risk_decision": request["risk_decision"],
    }


def approve_probe(approval_id: str, approval_digest: str) -> dict[str, Any]:
    with _APPROVAL_LOCK:
        rec = _APPROVALS.get(approval_id)
        if not rec or rec.get("request", {}).get("approval_digest") != approval_digest:
            return {"ok": False, "error": "approval not found"}
        if rec.get("consumed"):
            _record_probe_event(rec["request"].get("origin_trace_ref"), "approval_rejected", status="REJECTED", error="approval already consumed")
            return {"ok": False, "error": "approval already consumed"}
        if rec["request"].get("expires_at", 0) < time.time():
            _record_probe_event(rec["request"].get("origin_trace_ref"), "approval_rejected", status="REJECTED", error="approval expired")
            return {"ok": False, "error": "approval expired"}
        if not rec["request"].get("risk_decision", {}).get("cleared"):
            _record_probe_event(rec["request"].get("origin_trace_ref"), "approval_rejected", status="REJECTED", error="risk gate not cleared")
            return {"ok": False, "error": "risk gate not cleared"}
        rec["approved"] = True
        _record_probe_event(rec["request"].get("origin_trace_ref"), "approved", status="APPROVED", approval_id=approval_id)
        return {"ok": True, "approval_id": approval_id}


def consume_probe_approval(approval_id: str, approval_digest: str, *, conversation_id: str) -> dict[str, Any]:
    rejection: tuple[dict[str, Any] | None, str] | None = None
    with _APPROVAL_LOCK:
        rec = _APPROVALS.get(approval_id)
        if not rec or rec.get("request", {}).get("approval_digest") != approval_digest:
            rejection = (rec.get("request") if rec else None, "approval not found")
        else:
            req = rec["request"]
            if req.get("conversation_id") != conversation_id:
                rejection = (req, "conversation mismatch")
            elif not rec.get("approved"):
                rejection = (req, "approval not granted")
            elif rec.get("consumed"):
                rejection = (req, "approval already consumed")
            elif req.get("expires_at", 0) < time.time():
                rejection = (req, "approval expired")
            elif req.get("manifest_digest") != _manifest_digest(req["trace_ref"]):
                rejection = (req, "trace mutated")
            elif req.get("step_digest") != _step_digest(req["trace_ref"], req["step_name"]):
                rejection = (req, "step mutated")
            else:
                rec["consumed"] = True
                return {"ok": True, "request": dict(req)}
    if rejection is not None:
        _record_probe_rejection(conversation_id, rejection[0], rejection[1])
        return {"ok": False, "error": rejection[1]}
    return {"ok": False, "error": "approval rejected"}


def execute_probe(approval_id: str, approval_digest: str, *, conversation_id: str,
                  model_executor=None, conversation_tag: str = "") -> dict[str, Any]:
    consumed = consume_probe_approval(approval_id, approval_digest, conversation_id=conversation_id)
    if not consumed.get("ok"):
        return {"ok": False, "status": "REJECTED", "error": consumed.get("error")}
    req = consumed["request"]
    if not conversation_tag:
        conversation_tag = str(req.get("conversation_tag") or conversation_tag_for_trace_ref(req.get("trace_ref")))
    trace_dir = pipeline_trace.start_trace(
        conversation_id=conversation_id,
        raw_input="trace-probe " + req.get("trace_ref", ""),
        ambiguity_mode="assume",
        stealth=(conversation_tag == "stealth"),
        conversation_tag=conversation_tag,
    )
    if not trace_dir:
        return {"ok": False, "status": "REJECTED", "error": "probe trace creation failed; refusing untraced model request"}
    trace_dir = str(Path(trace_dir).resolve(strict=False))
    status = "error"
    terminal_response = None

    def _required_step(step_name: str, payload: dict[str, Any]) -> None:
        pipeline_trace.write_step(trace_dir, step_name, payload)
        path = Path(trace_dir) / f"{step_name}.json"
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"required probe artifact not captured: {step_name}")

    try:
        manifest = pipeline_trace.update_manifest_fields(
            trace_dir,
            trace_kind="trace-probe",
            investigates_trace_ref=req.get("trace_ref"),
        )
        if not isinstance(manifest, dict):
            raise RuntimeError("probe manifest metadata was not persisted")
        if (manifest.get("trace_kind") != "trace-probe"
                or manifest.get("investigates_trace_ref") != req.get("trace_ref")):
            raise RuntimeError("probe manifest metadata read-back mismatch")
        _required_step("step-probe-prepare", {
            "approval_id": approval_id,
            "approval_digest": approval_digest,
            "request": {k: req.get(k) for k in (
                "trace_ref", "step_name", "counterfactual_probe", "cost_ceiling",
                "cost_estimate", "manifest_digest", "step_digest", "envelope_digest")},
        })
        _required_step("step-probe-approval", {
            "server_authoritative": True,
            "consumed": True,
            "risk_decision": req.get("risk_decision") or {},
        })
        if model_executor is None:
            raise RuntimeError("probe model executor unavailable")
        _required_step("step-probe-model-attempt", {
            "status": "started",
            "envelope_digest": req.get("envelope_digest"),
            "provider": (req.get("envelope") or {}).get("provider"),
            "model": (req.get("envelope") or {}).get("model"),
            "max_tokens": (req.get("envelope") or {}).get("max_tokens"),
        })
        trace_token = step_token = call_token = tag_token = tool_token = None
        tool_module = None
        try:
            try:
                import boot as _boot
            except ImportError:
                from orchestrator import boot as _boot
            trace_token = _boot.set_turn_trace_context(trace_dir)
            step_token = _boot._CURRENT_STEP_CV.set("trace-probe-model-attempt")
            call_token = _boot._CALL_METADATA_CV.set({
                "step": "trace-probe-model-attempt",
                "slot": "probe",
                "gear": 0,
                "config_name": None,
                "invocation_id": f"probe-{approval_id}",
            })
            tag_token = _boot.set_conversation_tag_context(conversation_tag)
            try:
                import tool_events as tool_module
            except ImportError:
                from orchestrator import tool_events as tool_module
            tool_token = tool_module.set_turn_context(
                trace_dir=trace_dir,
                conversation_id=conversation_id,
                stealth=conversation_tag == "stealth",
                surface="trace-probe",
            )
            result = model_executor({"envelope": req.get("envelope"), "metadata": {k: req.get(k) for k in req if k != "envelope"}})
        finally:
            if tool_module is not None and tool_token is not None:
                tool_module.reset_turn_context(tool_token)
            if tag_token is not None:
                _boot.reset_conversation_tag_context(tag_token)
            if call_token is not None:
                _boot._CALL_METADATA_CV.reset(call_token)
            if step_token is not None:
                _boot._CURRENT_STEP_CV.reset(step_token)
            if trace_token is not None:
                _boot.reset_turn_trace_context(trace_token)
        if not isinstance(result, str) or not result.strip() or result.lstrip().startswith("[Error"):
            error = str(result or "empty model response")
            pipeline_trace.write_step(trace_dir, "step-probe-result", {
                "error": error[:2000], "inert": True, "provider_failure": True,
            })
            return {"ok": False, "status": "error", "trace_ref": pipeline_trace.trace_ref_for_dir(trace_dir), "error": error}
        inert = {
            "counterfactual_probe": bool(req.get("counterfactual_probe")),
            "result_text": str(result or "")[:8000],
            "inert": True,
        }
        _required_step("step-probe-result", inert)
        pipeline_trace.write_step_health(
            trace_dir, {"step-probe-result": (True, "completed")}, 0, [])
        if not (Path(trace_dir) / "step-health.json").is_file():
            raise RuntimeError("required probe artifact not captured: step-health")
        status = "completed"
        terminal_response = {
            "ok": True, "status": "completed",
            "trace_ref": pipeline_trace.trace_ref_for_dir(trace_dir), "result": inert,
        }
        return terminal_response
    except BaseException as exc:
        status = "abandoned" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "error"
        pipeline_trace.write_step(trace_dir, "step-probe-result", {"error": str(exc), "inert": True})
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        terminal_response = {
            "ok": False,
            "status": "error",
            "trace_ref": pipeline_trace.trace_ref_for_dir(trace_dir),
            "error": str(exc),
        }
        return terminal_response
    finally:
        try:
            pipeline_trace.write_step_health(
                trace_dir,
                {"step-probe-result": (status == "completed", status)},
                0,
                [],
            )
        except Exception:
            pass
        finalize_error = None
        try:
            pipeline_trace.finalize_manifest(
                trace_dir, kind="trace-probe", status_hint=status,
                parent_trace_ref=None,
            )
        except Exception as exc:
            finalize_error = exc
        expected_terminal_status = status if status in {"completed", "error", "abandoned"} else "error"
        finalized = pipeline_trace.read_manifest(trace_dir)
        durable = (
            finalize_error is None
            and isinstance(finalized, dict)
            and finalized.get("trace_kind") == "trace-probe"
            and finalized.get("investigates_trace_ref") == req.get("trace_ref")
            and finalized.get("terminal_status") == expected_terminal_status
        )
        if not durable:
            try:
                fallback_manifest = pipeline_trace.read_manifest(trace_dir)
                actual_steps, derived_artifacts = pipeline_trace._scan_turn_dir(trace_dir)  # type: ignore[attr-defined]
                if not isinstance(fallback_manifest, dict):
                    raise RuntimeError("probe manifest unavailable during finalization fallback")
                fallback_manifest.update({
                    "schema_version": pipeline_trace.MANIFEST_SCHEMA_VERSION,
                    "trace_kind": "trace-probe",
                    "investigates_trace_ref": req.get("trace_ref"),
                    "terminal_status": expected_terminal_status,
                    "expected_steps": pipeline_trace._expected_steps_for(  # type: ignore[attr-defined]
                        "trace-probe", fallback_manifest.get("gear"), actual_steps,
                    ),
                    "actual_steps": actual_steps,
                    "derived_artifacts": derived_artifacts,
                    "finalized_at": _utc_now(),
                })
                pipeline_trace._atomic_write_json(  # type: ignore[attr-defined]
                    os.path.join(trace_dir, pipeline_trace.MANIFEST_FILENAME),
                    fallback_manifest,
                )
            except Exception:
                pass
            finalized = pipeline_trace.read_manifest(trace_dir)
            durable = (
                isinstance(finalized, dict)
                and finalized.get("trace_kind") == "trace-probe"
                and finalized.get("investigates_trace_ref") == req.get("trace_ref")
                and finalized.get("terminal_status") == expected_terminal_status
            )
        if terminal_response is not None and not durable:
            terminal_response.clear()
            terminal_response.update({
                "ok": False,
                "status": "error",
                "trace_ref": pipeline_trace.trace_ref_for_dir(trace_dir),
                "error": "probe terminal finalization was not durable",
            })
        probe_ref = pipeline_trace.trace_ref_for_dir(trace_dir)
        origin_ref = req.get("origin_trace_ref") or req.get("trace_ref")
        origin_dir = pipeline_trace.resolve_trace_ref(origin_ref) if isinstance(origin_ref, str) else None
        if probe_ref and origin_dir:
            pipeline_trace.append_probe_trace_ref(origin_dir, probe_ref)


def learning_library_path() -> str:
    return os.path.join(_rp.DATA_DIR_STR, "trace-debug", "learning-library.jsonl")


def _redact_secret_text(value: Any, limit: int = 1000) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"https?://[^\s/@:]+:[^\s/@]+@", "https://[REDACTED]@", text)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", text)
    return text[:limit]


def append_learning_entry(entry: dict[str, Any], *, stealth: bool = False) -> bool:
    if stealth or not _enabled(TRACE_DEBUG_LIBRARY_ENABLED_ENV, default=True):
        return False
    if not isinstance(entry, dict):
        return False
    conversation_id = str(entry.get("conversation_id") or "")
    trace_ref = str(entry.get("trace_ref") or "")
    if not conversation_id or not trace_ref:
        return False
    verdict = str(entry.get("verdict") or "").strip()
    if verdict not in _ALLOWED_VERDICTS:
        return False
    root_cause = str(entry.get("root_cause") or "unknown").strip().lower()
    if root_cause not in _LEARNING_ROOT_CAUSES:
        return False
    rec: dict[str, Any] = {
        "schema_version": _LEARNING_SCHEMA_VERSION,
        "created_at": _utc_now(),
        "conversation_id": conversation_id,
        "trace_ref": trace_ref,
        "verdict": verdict,
        "root_cause": root_cause,
    }
    for key in ("framework_fingerprint", "contract_fingerprint"):
        if key in entry and entry.get(key) is not None:
            rec[key] = entry.get(key)
    for key, limit in _LEARNING_TEXT_LIMITS.items():
        if key in entry and entry.get(key) is not None:
            rec[key] = _redact_secret_text(entry.get(key), limit)
    if entry.get("gear") is not None:
        try:
            rec["gear"] = int(entry["gear"])
        except (TypeError, ValueError):
            return False
    with _rp.conversation_lifecycle_lock(conversation_id):
        ok, _error = _validate_same_conversation_unlocked(trace_ref, conversation_id)
        if not ok:
            return False
        trace_dir = pipeline_trace.resolve_trace_ref(trace_ref)
        manifest = pipeline_trace.read_manifest(trace_dir) if trace_dir else None
        if not isinstance(manifest, dict) or manifest.get("redaction_level") == "private":
            return False
        path = learning_library_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        line = (json.dumps(rec, sort_keys=True, default=str) + "\n").encode("utf-8")
        with _rp.locked_file(path):
            _rp.append_bytes_no_follow(path, line, mode=0o600)
    return True


def list_learning_entries() -> list[dict[str, Any]]:
    path = learning_library_path()
    if not os.path.exists(path):
        return []
    out: list[dict[str, Any]] = []
    _LEARNING_STATUS["malformed_records"] = 0
    _LEARNING_STATUS["unsupported_schema_records"] = 0
    with _rp.locked_file(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    _LEARNING_STATUS["malformed_records"] += 1
                    continue
                if not isinstance(rec, dict):
                    _LEARNING_STATUS["malformed_records"] += 1
                    continue
                if rec.get("schema_version") != _LEARNING_SCHEMA_VERSION:
                    _LEARNING_STATUS["unsupported_schema_records"] += 1
                    continue
                out.append({k: rec.get(k) for k in _LEARNING_SCHEMA_KEYS if k in rec})
    counts: dict[tuple[Any, Any, Any], int] = {}
    for rec in out:
        key = (rec.get("framework_id"), rec.get("root_cause"), rec.get("verdict"))
        counts[key] = counts.get(key, 0) + 1
    for rec in out:
        rec["recurrence_count"] = counts.get((rec.get("framework_id"), rec.get("root_cause"), rec.get("verdict")), 1)
    return out


def learning_library_status() -> dict[str, int]:
    """Return current valid-record and corruption counters for oversight."""
    entries = list_learning_entries()
    return {
        "records": len(entries),
        **_LEARNING_STATUS,
    }


def record_diagnosis_learning(conversation_id: str, trace_ref: str, result_text: str, *, stealth: bool = False) -> bool:
    verdicts = re.findall(r"^\s*VERDICT\s*:\s*(DEFECT_LOCALIZED|BAD_DRAW|CONTRACT_MISMATCH|NO_DEFECT)\s*$", result_text or "", re.I | re.M)
    if len(verdicts) != 1:
        return False
    trace_dir = pipeline_trace.resolve_trace_ref(trace_ref)
    manifest = pipeline_trace.read_manifest(trace_dir) if trace_dir else {}
    snap = (manifest or {}).get("contract_snapshot") if isinstance(manifest, dict) else None
    return append_learning_entry({
        "conversation_id": conversation_id,
        "trace_ref": trace_ref,
        "framework_id": (manifest or {}).get("framework_id"),
        "mode": (manifest or {}).get("mode"),
        "gear": (manifest or {}).get("gear"),
        "verdict": verdicts[0].upper(),
        "contract_fingerprint": snap.get("fingerprint") if isinstance(snap, dict) else None,
        "framework_fingerprint": ((snap.get("canonical_fields") or {}).get("framework_fingerprint") if isinstance(snap, dict) else None),
        "failing_step": _redact_secret_text(_extract_label(result_text, "FAILING STEP"), 200),
        "verification_probe": _redact_secret_text(_extract_label(result_text, "VERIFICATION PROBE"), 400),
        "root_cause": _redact_secret_text(_extract_label(result_text, "ROOT CAUSE"), 400),
        "correction_lane": _redact_secret_text(_extract_label(result_text, "CORRECTION LANE"), 200),
        "symptom_signature": _redact_secret_text(_extract_label(result_text, "SYMPTOM SIGNATURE"), 600),
        "correction_summary": _redact_secret_text(_extract_label(result_text, "CORRECTION SUMMARY"), 1000),
        "escalation_boundary": _redact_secret_text(_extract_label(result_text, "ESCALATION BOUNDARY"), 400),
    }, stealth=stealth)


def _extract_label(text: str, label: str) -> str:
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*:\s*(.+)$", re.I | re.M)
    match = pattern.search(text or "")
    return match.group(1).strip() if match else ""


def _validate_same_conversation_unlocked(trace_ref: str, conversation_id: str | None) -> tuple[bool, str]:
    ok, error = _validate_same_conversation_ref(trace_ref, conversation_id)
    if not ok:
        return ok, error
    if pipeline_trace.resolve_trace_ref(trace_ref) is None:
        return False, "trace_ref not found"
    return True, ""


def purge_conversation_unlocked(conversation_id: str) -> dict[str, Any]:
    path = learning_library_path()
    result = {"removed": 0, "errors": []}
    if not os.path.exists(path):
        return result
    identity = str(conversation_id or "").casefold()
    try:
        with _rp.locked_file(path):
            kept: list[str] = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    raw = line.rstrip("\n")
                    if not raw.strip():
                        continue
                    try:
                        rec = json.loads(raw)
                    except Exception:
                        kept.append(raw)
                        continue
                    owner = str(rec.get("conversation_id") or "").casefold()
                    if owner == identity:
                        result["removed"] += 1
                    else:
                        kept.append(raw)
            _rp.atomic_write_text(path, "".join(line + "\n" for line in kept))
    except Exception as exc:
        result["errors"].append(str(exc))
    return result


def purge_conversation(conversation_id: str) -> dict[str, Any]:
    with _rp.conversation_lifecycle_lock(conversation_id):
        return purge_conversation_unlocked(conversation_id)


def endpoint_from_probe_envelope(envelope: dict[str, Any], fallback_endpoint: dict[str, Any]) -> dict[str, Any] | None:
    endpoint_id = envelope.get("endpoint_id")
    if not endpoint_id:
        return None
    try:
        try:
            import boot as _boot
        except ImportError:
            from orchestrator import boot as _boot
        endpoint = _boot.get_endpoint_by_id(str(endpoint_id))
    except Exception:
        endpoint = None
    if not isinstance(endpoint, dict):
        return None
    resolved_id = endpoint.get("id") or endpoint.get("name")
    if resolved_id != endpoint_id:
        return None
    for key, endpoint_key in (("endpoint_type", "type"), ("provider", "provider"), ("model", "model_id")):
        recorded = envelope.get(key)
        current = (
            (endpoint.get("model_id") or endpoint.get("model"))
            if endpoint_key == "model_id" else endpoint.get(endpoint_key)
        )
        if recorded not in (None, "") and current not in (recorded, None):
            return None
    recorded_host = envelope.get("base_url_host")
    if recorded_host:
        current_url = endpoint.get("base_url") or endpoint.get("url") or ""
        parsed = urlparse(str(current_url))
        current_host = parsed.hostname or ""
        if parsed.port:
            current_host = f"{current_host}:{parsed.port}"
        if current_host != recorded_host:
            return None
    if envelope.get("max_tokens") is not None:
        endpoint["max_tokens"] = envelope.get("max_tokens")
    for key, value in (envelope.get("parameters") or {}).items():
        if key not in {"api_key", "authorization", "headers"}:
            endpoint[key] = value
    return endpoint
