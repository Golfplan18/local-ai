"""
pipeline_trace.py — Per-turn pipeline forensic trace.

Writes a complete forensic record of every Ora pipeline turn to
``~/ora/data/pipeline-traces/<conversation_id>/<turn-timestamp>/``.

Goal: every silent-failure spot in the pipeline becomes inspectable
after the fact. Each pipeline step lands one structured JSON file
(machine-diffable) and one Markdown sibling (human-readable). Failures
that previously dissolved into empty strings or auto-PASS verdicts get
their own log entry instead of vanishing.

Design constraints:
- Trace writing must never crash the pipeline. Every disk operation is
  wrapped in try/except; failure produces a stderr line and continues.
- Atomic writes (write to ``<name>.tmp`` then rename) so partial files
  do not appear under crash conditions.
- No external dependencies — stdlib only.
- Caller passes a ``trace_dir`` value (or ``None`` to disable tracing).
  This keeps the trace pluggable and lets tests bypass it.

The full trace contract lives in:
``~/Documents/vault/Paper — Subtle-Calculation Errors in LLM Pipelines.md``
"""

from __future__ import annotations

import json
import os
import sys
import datetime as _dt
from pathlib import Path
from typing import Any

TRACE_ROOT = os.path.expanduser("~/ora/data/pipeline-traces")


def _now_ts() -> str:
    """UTC timestamp formatted for filesystem use."""
    return _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def start_trace(conversation_id: str | None,
                raw_input: str = "",
                ambiguity_mode: str = "assume") -> str | None:
    """Open a new per-turn trace directory.

    Args:
        conversation_id: stable id from the conversation memory layer, or
            ``None`` for orphan invocations (CLI, tests). Orphan traces
            land under ``_orphan/``.
        raw_input: the user's raw prompt — captured here so it is always
            preserved even if Step 1 mangles it.
        ambiguity_mode: ``ask`` or ``assume`` — captured for
            reproducibility.

    Returns:
        Absolute path to the new trace directory, or ``None`` if trace
        creation failed. ``None`` is the disabled sentinel for all the
        ``write_*`` helpers below.
    """
    try:
        conv = conversation_id or "_orphan"
        ts = _now_ts()
        trace_dir = os.path.join(TRACE_ROOT, conv, ts)
        os.makedirs(trace_dir, exist_ok=True)
        meta = {
            "conversation_id": conversation_id,
            "turn_timestamp_utc": ts,
            "raw_input": raw_input,
            "ambiguity_mode": ambiguity_mode,
            "started_at": _dt.datetime.utcnow().isoformat() + "Z",
        }
        _atomic_write_json(os.path.join(trace_dir, "metadata.json"), meta)
        # Maintain a latest-pointer for quick inspection (mirrors the
        # /tmp/ora-trace-latest.txt convention but per-conversation).
        try:
            latest = os.path.join(TRACE_ROOT, conv, "_latest.txt")
            with open(latest, "w") as f:
                f.write(ts)
        except Exception:
            pass
        return trace_dir
    except Exception as e:
        print(f"[pipeline_trace] start_trace failed: {e}", file=sys.stderr)
        return None


def write_step(trace_dir: str | None,
               step_name: str,
               payload: dict[str, Any],
               markdown: str | None = None) -> None:
    """Write a structured step record (JSON) plus optional markdown sibling.

    ``step_name`` becomes the filename stem. Use stable, sortable names:
    ``step1-phase-a``, ``step2-context``, ``step3-depth``,
    ``step6-verifier-cycle-1``, etc.

    The JSON payload should be self-contained — include the system
    prompt, user message, raw model response, parsed result, and any
    elapsed-time or health flags the caller knows about.
    """
    if not trace_dir:
        return
    try:
        json_path = os.path.join(trace_dir, f"{step_name}.json")
        _atomic_write_json(json_path, payload)
        if markdown is not None:
            md_path = os.path.join(trace_dir, f"{step_name}.md")
            _atomic_write_text(md_path, markdown)
    except Exception as e:
        print(f"[pipeline_trace] write_step({step_name}) failed: {e}",
              file=sys.stderr)


def append_jsonl(trace_dir: str | None,
                 filename: str,
                 record: dict[str, Any]) -> None:
    """Append a record to a JSONL log inside the trace directory.

    Used for things that can fire multiple times per turn — RAG
    failures, supplemental-RAG requests, contingency fall-backs.
    """
    if not trace_dir:
        return
    try:
        path = os.path.join(trace_dir, filename)
        line = json.dumps(record, default=_json_default) + "\n"
        with open(path, "a") as f:
            f.write(line)
    except Exception as e:
        print(f"[pipeline_trace] append_jsonl({filename}) failed: {e}",
              file=sys.stderr)


def record_rag_failure(trace_dir: str | None,
                       query_type: str,
                       query: str,
                       error: str) -> None:
    """Log a RAG retrieval failure that would otherwise silently fall
    back to an empty string.

    ``query_type``: ``conversation-rag`` or ``concept-rag`` or
    ``relationship-rag`` or ``rag-engine-init``.
    """
    append_jsonl(trace_dir, "rag-failures.jsonl", {
        "timestamp_utc": _dt.datetime.utcnow().isoformat() + "Z",
        "query_type": query_type,
        "query": query[:500],
        "error": str(error)[:2000],
    })


def record_supplemental_request(trace_dir: str | None,
                                step: str,
                                gap_statement: str,
                                query_terms: str,
                                why_it_matters: str,
                                supplement_result: str | None,
                                resolved: bool) -> None:
    """Log a SUPPLEMENTAL RAG REQUEST emitted by a pipeline step.

    Captures the gap the model surfaced, what the orchestrator did with
    it, and whether the resubmission resolved the gap. Empirical record
    of where vault coverage is thin.
    """
    append_jsonl(trace_dir, "supplemental-rag.jsonl", {
        "timestamp_utc": _dt.datetime.utcnow().isoformat() + "Z",
        "step": step,
        "gap_statement": gap_statement[:2000],
        "query_terms": query_terms[:500],
        "why_it_matters": why_it_matters[:1000],
        "supplement_result_len": (
            len(supplement_result) if supplement_result else 0
        ),
        "resolved": resolved,
    })


def write_step_health(trace_dir: str | None,
                      step_health: dict[str, tuple[bool, str]],
                      gear: int,
                      contingencies_fired: list[str]) -> None:
    """Write the per-turn step-health summary.

    Captures every step's pass/fail verdict, the reason for each
    failure, the gear chosen, and which contingency paths fired.
    """
    if not trace_dir:
        return
    try:
        payload = {
            "gear": gear,
            "step_health": {
                k: {"ok": bool(ok), "reason": reason}
                for k, (ok, reason) in step_health.items()
            },
            "contingencies_fired": list(contingencies_fired),
            "finished_at": _dt.datetime.utcnow().isoformat() + "Z",
        }
        _atomic_write_json(os.path.join(trace_dir, "step-health.json"),
                           payload)
    except Exception as e:
        print(f"[pipeline_trace] write_step_health failed: {e}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _atomic_write_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=_json_default)
    os.replace(tmp, path)


def _atomic_write_text(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def _json_default(obj: Any) -> str:
    """Fallback for objects that aren't JSON-serializable."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return repr(obj)


# ---------------------------------------------------------------------------
# Public read-side helpers (for inspection / chunk-3 verification)
# ---------------------------------------------------------------------------

def latest_trace_dir(conversation_id: str | None) -> str | None:
    """Return the most recent trace directory for a conversation, or
    ``None`` if no trace exists.
    """
    try:
        conv = conversation_id or "_orphan"
        latest_pointer = os.path.join(TRACE_ROOT, conv, "_latest.txt")
        if os.path.exists(latest_pointer):
            with open(latest_pointer) as f:
                ts = f.read().strip()
            candidate = os.path.join(TRACE_ROOT, conv, ts)
            if os.path.isdir(candidate):
                return candidate
        # Fallback: scan and pick the lexicographically latest
        conv_dir = os.path.join(TRACE_ROOT, conv)
        if not os.path.isdir(conv_dir):
            return None
        entries = sorted(
            d for d in os.listdir(conv_dir)
            if os.path.isdir(os.path.join(conv_dir, d))
            and not d.startswith("_")
        )
        if entries:
            return os.path.join(conv_dir, entries[-1])
        return None
    except Exception:
        return None


def list_traces(conversation_id: str | None) -> list[str]:
    """Return all trace directories for a conversation, oldest first."""
    try:
        conv = conversation_id or "_orphan"
        conv_dir = os.path.join(TRACE_ROOT, conv)
        if not os.path.isdir(conv_dir):
            return []
        return sorted(
            os.path.join(conv_dir, d)
            for d in os.listdir(conv_dir)
            if os.path.isdir(os.path.join(conv_dir, d))
            and not d.startswith("_")
        )
    except Exception:
        return []
