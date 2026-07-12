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
import stat
import sys
import datetime as _dt
from pathlib import Path
from typing import Any

try:
    from orchestrator import runtime_paths as _rp
except ImportError:  # pragma: no cover - legacy top-level import context
    import runtime_paths as _rp  # type: ignore

def _resolve_ora_home() -> str:
    """Resolve the Ora installation root without depending on ``HOME``.

    Prefer the ``ORA_HOME`` env var (exported by ``start.sh`` and the
    launchd jobs); otherwise derive from this file's own location
    (``orchestrator/pipeline_trace.py`` → parent.parent == the ora root).

    We deliberately avoid ``os.path.expanduser("~/ora")`` here. When ``HOME``
    is unset AND the passwd-database lookup transiently fails, ``expanduser``
    returns the literal string ``"~"`` unchanged — and ``os.makedirs`` then
    creates a ``~`` directory under the current working directory instead of
    the real home. Deriving from ``__file__`` never needs ``HOME`` and can
    never yield a literal ``"~"``. (Root cause of the stray ``~/ora/...``
    trace directories observed through 2026-05-30.)
    """
    env_home = os.environ.get("ORA_HOME")
    if env_home and "~" not in env_home:
        return env_home
    return str(Path(__file__).resolve().parent.parent)


TRACE_ROOT = os.path.join(_resolve_ora_home(), "data", "pipeline-traces")

# Environment variable gate. Setting ``ORA_PIPELINE_TRACE=off`` (or any
# value in ``_DISABLE_VALUES``) disables tracing globally regardless of
# any per-call ``stealth`` flag. Default is on.
_DISABLE_VALUES = frozenset({"off", "false", "0", "no", "disabled"})


def _safe_trace_root(*, create: bool = False) -> Path:
    """Return ``TRACE_ROOT`` without following a substituted root symlink.

    ``TRACE_ROOT`` remains patchable for tests and relocatable deployments,
    so its parent is the configured/trusted boundary.  The trace-store child
    itself is always validated with the shared owned-directory primitive.
    """
    root = Path(TRACE_ROOT)
    if not root.name:
        raise ValueError("invalid empty trace root")
    return _rp.safe_owned_subdir(root.parent, root.name, create=create)


def _safe_trace_dir(
    conversation_id: str,
    turn_timestamp: str,
    *,
    create: bool = False,
) -> Path:
    """Return one owned turn directory with every child component checked."""
    root = _safe_trace_root(create=create)
    return _rp.safe_owned_subdir(
        root, conversation_id, turn_timestamp, create=create,
    )


def _validated_existing_trace_dir(trace_dir: str | os.PathLike[str]) -> Path:
    """Validate a caller-supplied turn dir against the owned trace tree."""
    root = _safe_trace_root(create=False)
    candidate = Path(trace_dir).absolute()
    try:
        parts = candidate.relative_to(root.absolute()).parts
    except ValueError as exc:
        raise ValueError(f"trace directory is outside TRACE_ROOT: {candidate}") from exc
    if len(parts) != 2:
        raise ValueError(f"trace directory has invalid depth: {candidate}")
    validated = _rp.safe_owned_subdir(root, *parts, create=False)
    if not validated.exists() or validated.is_symlink() or not validated.is_dir():
        raise ValueError(f"trace directory is not an owned directory: {validated}")
    return validated


def _safe_trace_filename(value: str, *, label: str) -> str:
    """Validate one direct filename/stem supplied to a trace writer."""
    name = str(value or "")
    if (not name or name in {".", ".."} or "/" in name or "\\" in name
            or "\x00" in name
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
        raise ValueError(f"unsafe {label}: {name!r}")
    return name


def _matching_conversation_dirs(
    conversation_id: str,
) -> tuple[list[Path], list[Path], list[str]]:
    """Find case-equivalent owned trace dirs without following symlinks."""
    # Validate the ID as one direct child even when the trace root is absent.
    if (not conversation_id or conversation_id in {".", ".."}
            or "/" in conversation_id or "\\" in conversation_id
            or "\x00" in conversation_id
            or any(ord(ch) < 32 or ord(ch) == 127
                   for ch in conversation_id)):
        raise ValueError(f"unsafe conversation trace id: {conversation_id!r}")
    root = _safe_trace_root(create=False)
    if not root.exists():
        return [], [], []

    identity = conversation_id.casefold()
    directories: list[Path] = []
    symlinks: list[Path] = []
    errors: list[str] = []
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.name.casefold() != identity:
                continue
            path = root / entry.name
            if entry.is_symlink():
                symlinks.append(path)
            elif entry.is_dir(follow_symlinks=False):
                directories.append(path)
            else:
                errors.append(f"refusing non-directory conversation trace path {path}")
    return (
        sorted(directories, key=lambda item: item.name),
        sorted(symlinks, key=lambda item: item.name),
        errors,
    )


def _read_json_no_follow(path: Path) -> Any:
    """Read a regular JSON file while refusing a final-component symlink."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"not a regular file: {path}")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            return json.load(stream)
    finally:
        if fd >= 0:
            os.close(fd)


def _read_text_no_follow(path: Path) -> str:
    """Read a regular text file while refusing a final-component symlink."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"not a regular file: {path}")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            return stream.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _tracing_globally_disabled() -> bool:
    """True when the ORA_PIPELINE_TRACE env var disables tracing."""
    val = os.environ.get("ORA_PIPELINE_TRACE", "").strip().lower()
    return val in _DISABLE_VALUES


def _now_ts() -> str:
    """UTC timestamp formatted for filesystem use."""
    return _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def start_trace(conversation_id: str | None,
                raw_input: str = "",
                ambiguity_mode: str = "assume",
                style_id: str | None = None,
                style_register: str | None = None,
                stealth: bool = False,
                conversation_tag: str = "") -> str | None:
    """Open a new per-turn trace directory.

    Args:
        conversation_id: stable id from the conversation memory layer, or
            ``None`` for orphan invocations (CLI, tests). Orphan traces
            land under ``_orphan/``.
        raw_input: the user's raw prompt — captured here so it is always
            preserved even if Step 1 mangles it.
        ambiguity_mode: ``ask`` or ``assume`` — captured for
            reproducibility.
        stealth: when True, no trace directory is created and no files
            are written. Returns ``None`` immediately. This is the
            primary mechanism for keeping stealth conversations from
            leaking through the trace layer. ``_purge_stealth`` in
            ``conversation_closeout.py`` adds a defence-in-depth sweep
            that walks ``TRACE_ROOT/<conversation_id>/`` and unlinks any
            trace dir that ever existed for the stealth conversation.
        conversation_tag: the conversation-level mode (V3 Phase 1.1 —
            empty / "private" / "stealth"). Stamped on the manifest as
            ``redaction_level`` so downstream viewers/exports (Chunk 2)
            know to treat the trace content as private. Stealth never
            reaches here with a trace (the ``stealth`` flag suppresses
            creation entirely).

    Returns:
        Absolute path to the new trace directory, or ``None`` if:
          - stealth=True (explicit no-trace request)
          - ORA_PIPELINE_TRACE env var disables tracing globally
          - trace creation failed (disk full, permissions, etc.)

        ``None`` is the disabled sentinel — every downstream ``write_*``
        helper short-circuits when passed ``None`` so call sites do not
        need their own guards.
    """
    # Stealth mode and global-disable both produce no-trace immediately.
    if stealth or _tracing_globally_disabled():
        return None

    try:
        conv = conversation_id or "_orphan"
        ts = _now_ts()
        trace_dir = str(_safe_trace_dir(conv, ts, create=True))
        # Defence-in-depth: never create a path containing a literal "~".
        # _resolve_ora_home() should already prevent this, but if TRACE_ROOT
        # is ever reintroduced as a literal-"~" path, disable tracing for the
        # turn rather than littering the working directory with a "~" tree.
        if "~" in trace_dir:
            print("[pipeline_trace] start_trace: refusing literal '~' path "
                  f"{trace_dir!r}; tracing disabled this turn", file=sys.stderr)
            return None
        meta = {
            "conversation_id": conversation_id,
            "turn_timestamp_utc": ts,
            "raw_input": raw_input,
            "ambiguity_mode": ambiguity_mode,
            "style_id": style_id,
            "style_register": style_register,
            "started_at": _dt.datetime.utcnow().isoformat() + "Z",
        }
        _atomic_write_json(os.path.join(trace_dir, "metadata.json"), meta)
        # Trace-manifest skeleton (Chunk 0). Opened with
        # ``terminal_status: "open"``; ``finalize_manifest`` overwrites it
        # at turn end with the honest kind/status/step derivation. A turn
        # that dies so hard its finalizer never runs leaves "open" on disk
        # — itself an honest signal (the turn never reached any exit path).
        try:
            _atomic_write_json(
                os.path.join(trace_dir, MANIFEST_FILENAME),
                _manifest_skeleton(conversation_id, ts, conversation_tag),
            )
        except Exception as _mf_exc:
            # Fail-open: a manifest failure must never cost the turn its
            # trace (metadata.json is already down at this point).
            print(f"[pipeline_trace] manifest skeleton failed: {_mf_exc}",
                  file=sys.stderr)
        # Maintain a latest-pointer for quick inspection (mirrors the
        # /tmp/ora-trace-latest.txt convention but per-conversation).
        try:
            latest = os.path.join(os.path.dirname(trace_dir), "_latest.txt")
            _atomic_write_text(latest, ts)
        except Exception:
            pass
        return trace_dir
    except Exception as e:
        print(f"[pipeline_trace] start_trace failed: {e}", file=sys.stderr)
        return None


def purge_conversation_traces(conversation_id: str) -> dict:
    """Defence-in-depth: wipe every trace directory belonging to a
    conversation. Called by ``conversation_closeout._purge_stealth``
    so stealth-tagged conversations have zero residue even if the
    primary skip-creation path is ever bypassed by a bug.

    Returns ``{"deleted": bool, "path": str, "error": str | None}``.
    Safe to call when no trace directory exists — returns
    ``deleted: False`` without raising.
    """
    path = os.path.join(TRACE_ROOT, str(conversation_id or ""))
    if not conversation_id:
        return {
            "deleted": False,
            "path": "",
            "paths": [],
            "symlink_removed": False,
            "error": "empty conversation_id",
        }
    try:
        with _rp.conversation_lifecycle_lock(conversation_id):
            return _purge_conversation_traces_unlocked(conversation_id)
    except Exception as e:
        return {
            "deleted": False,
            "path": path,
            "paths": [],
            "symlink_removed": False,
            "error": str(e),
        }


def _purge_conversation_traces_unlocked(conversation_id: str) -> dict:
    """Remove case-equivalent trace trees; caller holds the lifecycle lock."""
    import shutil

    requested_path = os.path.join(TRACE_ROOT, conversation_id)
    directories, symlinks, errors = _matching_conversation_dirs(conversation_id)
    removed: list[str] = []
    symlink_removed = False

    # A symlink occupying an Ora-owned conversation slot is residue owned by
    # Ora, but its target is not. Unlink only the directory entry.
    for path in symlinks:
        try:
            path.unlink()
            removed.append(str(path))
            symlink_removed = True
        except Exception as exc:
            errors.append(f"unlink trace symlink {path}: {exc}")

    for path in directories:
        try:
            shutil.rmtree(path)
            removed.append(str(path))
        except Exception as exc:
            errors.append(f"remove trace tree {path}: {exc}")

    return {
        "deleted": bool(removed),
        "path": requested_path,
        "paths": removed,
        "symlink_removed": symlink_removed,
        "error": "; ".join(errors) if errors else None,
    }


def retag_conversation_trace_manifests(
    conversation_id: str,
    tag: str,
) -> dict[str, Any]:
    """Retag every owned trace manifest for one Dialogue.

    ``tag`` is the conversation tag (``""`` or ``"private"``), translated
    to the trace schema's exact ``redaction_level`` value. The operation is
    cross-process serialized and fail-open: malformed or suspicious entries
    are reported while every other manifest is still attempted.

    Call :func:`_retag_conversation_trace_manifests_unlocked` only when the
    caller already holds :func:`runtime_paths.conversation_lifecycle_lock`.
    """
    if tag not in {"", "private"}:
        raise ValueError("trace privacy tag must be standard ('') or 'private'")
    with _rp.conversation_lifecycle_lock(conversation_id):
        return _retag_conversation_trace_manifests_unlocked(
            conversation_id, tag,
        )


def _retag_conversation_trace_manifests_unlocked(
    conversation_id: str,
    tag: str,
) -> dict[str, Any]:
    """Unlocked implementation for the consolidated lifecycle transaction."""
    if tag not in {"", "private"}:
        raise ValueError("trace privacy tag must be standard ('') or 'private'")

    level = "private" if tag == "private" else "default"
    updated: list[str] = []
    unchanged: list[str] = []
    errors: list[str] = []
    directories, symlinks, discovery_errors = _matching_conversation_dirs(
        conversation_id,
    )
    errors.extend(discovery_errors)
    errors.extend(
        f"refusing symlinked conversation trace path {path}"
        for path in symlinks
    )
    identity = conversation_id.casefold()

    for conversation_dir in directories:
        try:
            entries = list(os.scandir(conversation_dir))
        except Exception as exc:
            errors.append(f"scan trace directory {conversation_dir}: {exc}")
            continue
        for entry in sorted(entries, key=lambda item: item.name):
            if entry.name.startswith("_"):
                continue
            turn_dir = conversation_dir / entry.name
            if entry.is_symlink():
                errors.append(f"refusing symlinked turn trace path {turn_dir}")
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            manifest_path = turn_dir / MANIFEST_FILENAME
            try:
                file_stat = manifest_path.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            except Exception as exc:
                errors.append(f"inspect trace manifest {manifest_path}: {exc}")
                continue
            if not stat.S_ISREG(file_stat.st_mode):
                errors.append(f"refusing non-regular trace manifest {manifest_path}")
                continue
            try:
                manifest = _read_json_no_follow(manifest_path)
                if not isinstance(manifest, dict):
                    raise ValueError("manifest root is not an object")
                manifest_id = manifest.get("conversation_id")
                if (not isinstance(manifest_id, str)
                        or manifest_id.casefold() != identity):
                    raise ValueError(
                        "manifest conversation_id does not match owned trace directory"
                    )
                if manifest.get("redaction_level") == level:
                    unchanged.append(str(manifest_path))
                    continue
                replacement = dict(manifest)
                replacement["redaction_level"] = level
                _atomic_write_json(str(manifest_path), replacement)
                updated.append(str(manifest_path))
            except Exception as exc:
                errors.append(f"retag trace manifest {manifest_path}: {exc}")

    return {
        "conversation_id": conversation_id,
        "tag": tag,
        "redaction_level": level,
        "updated": len(updated),
        "paths": updated,
        "unchanged": len(unchanged),
        "errors": errors,
    }


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
        owned_trace_dir = _validated_existing_trace_dir(trace_dir)
        safe_step_name = _safe_trace_filename(step_name, label="trace step name")
        json_path = str(owned_trace_dir / f"{safe_step_name}.json")
        _atomic_write_json(json_path, payload)
        if markdown is not None:
            md_path = str(owned_trace_dir / f"{safe_step_name}.md")
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
        owned_trace_dir = _validated_existing_trace_dir(trace_dir)
        safe_filename = _safe_trace_filename(
            filename, label="trace JSONL filename",
        )
        path = str(owned_trace_dir / safe_filename)
        line = json.dumps(record, default=_json_default) + "\n"
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception as e:
        print(f"[pipeline_trace] append_jsonl({filename}) failed: {e}",
              file=sys.stderr)


# Corpus-wide ora-visual emission log. Unlike the per-turn trace files, this
# is a single fixed-path JSONL that accumulates one record per visual-envelope
# emission ATTEMPT across every turn — the data needed to measure the real
# envelope valid-rate (and its model-tier dependence) over time. Phase 0
# observability: previously only a single ``step-visual-hook.json`` ever landed
# on disk, so the true emission failure rate was unmeasurable.
def emission_log_path() -> str:
    """Resolve the global visual-emission sink at call time."""
    try:
        from orchestrator import runtime_paths as _rp
    except ImportError:  # pragma: no cover - legacy top-level import context
        try:
            import runtime_paths as _rp  # type: ignore
        except ImportError:
            return os.path.join(
                _resolve_ora_home(), "data", "visual-emission-log.jsonl",
            )
    return os.path.join(_rp.DATA_DIR_STR, "visual-emission-log.jsonl")


# Compatibility constant for diagnostics/tests; writers use the dynamic helper.
EMISSION_LOG_PATH = emission_log_path()


def append_emission_record(record: dict[str, Any]) -> None:
    """Append one ora-visual emission-attempt record to the corpus emission log.

    Not gated on a per-turn ``trace_dir`` — it always lands in
    ``data/visual-emission-log.jsonl`` so the valid-rate can be aggregated
    across turns. A ``timestamp_utc`` is filled in when absent. Fail-open: a
    logging error prints to stderr and never disturbs the pipeline.
    """
    try:
        try:
            from orchestrator import runtime_paths as _rp
        except ImportError:  # pragma: no cover - legacy top-level import context
            import runtime_paths as _rp  # type: ignore
        record.setdefault("timestamp_utc", _dt.datetime.utcnow().isoformat() + "Z")
        path = emission_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        encoded = (json.dumps(record, default=_json_default) + "\n").encode("utf-8")
        with _rp.locked_file(path):
            _rp.append_bytes_no_follow(path, encoded, mode=0o644)
    except Exception as e:
        print(f"[pipeline_trace] append_emission_record failed: {e}",
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
        owned_trace_dir = _validated_existing_trace_dir(trace_dir)
        payload = {
            "gear": gear,
            "step_health": {
                k: {"ok": bool(ok), "reason": reason}
                for k, (ok, reason) in step_health.items()
            },
            "contingencies_fired": list(contingencies_fired),
            "finished_at": _dt.datetime.utcnow().isoformat() + "Z",
        }
        _atomic_write_json(str(owned_trace_dir / "step-health.json"),
                           payload)
    except Exception as e:
        print(f"[pipeline_trace] write_step_health failed: {e}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Trace manifest (Chunk 0 — the join layer)
# ---------------------------------------------------------------------------
# One trace-manifest.json per turn directory. Written as a skeleton by
# ``start_trace`` and overwritten in place by ``finalize_manifest`` from the
# single generator-level ``finally`` in the server's turn paths. The manifest
# is the mechanical join between conversation.json turns (``trace_ref``) and
# the trace store, and the anti-false-confidence record: expected vs actual
# steps, plus an honest ``trace_kind`` / ``terminal_status`` for every turn
# path including the metadata-only short-circuits.

MANIFEST_FILENAME = "trace-manifest.json"
MANIFEST_SCHEMA_VERSION = 1

# Turn kinds whose *normal* end is not a completed analytical pipeline.
# A turn of one of these kinds that exits without an error hint finalizes
# as ``short_circuit`` — never ``abandoned``.
SHORT_CIRCUIT_KINDS = frozenset({
    "runtime_command", "risk_hold", "resolution_continuation",
    "framework_elicitation", "framework_command", "no_endpoint_error",
    "direct",
})

# Required (always-written on a clean run) step files per gear for full
# pipeline turns. Everything else that lands as step*.json is a legitimate
# observed step (verifier cycles, claim verification, unflagged scans,
# quality gate, web consultation, contingency fallbacks) but is deliberately
# NOT expected-counted, so its absence can never render as a missing step
# (design Q3 as modified by the 2026-07-11 design-gate verdict).
_REQUIRED_STEPS_COMMON = ["step1-phase-a", "step1-pre-routing"]
_REQUIRED_STEPS_BY_GEAR = {
    1: _REQUIRED_STEPS_COMMON + ["step2-context"],
    2: _REQUIRED_STEPS_COMMON + ["step2-context"],
    3: _REQUIRED_STEPS_COMMON + [
        "step2-context", "step3-depth", "step4-eval", "step5-revised",
    ],
    4: _REQUIRED_STEPS_COMMON + [
        "step2-context", "step3-depth", "step3-breadth",
        "step4-eval-of-depth", "step4-eval-of-breadth",
        "step5-revised-depth", "step5-revised-breadth",
        "step7-consolidated", "step8-formatted",
    ],
}

# step*.json files that are derived summaries, not pipeline steps. They are
# excluded from ``actual_steps`` and listed under ``derived_artifacts``
# instead, so viewer missing-step rendering stays clean (design-gate
# condition 5). ``cost-summary`` doesn't match the step* glob but belongs
# in the derived list when present.
_DERIVED_STEP_STEMS = frozenset({
    "step-health", "step-visual-hook", "step-visual-emissions",
})
_DERIVED_EXTRA_FILES = ("cost-summary.json",)

# Contingency fallback markers: run_gear3/run_gear4 (orchestrator/boot.py)
# have documented, legitimate fallback branches that complete a turn with a
# materially smaller step footprint than the gear's normal table — a
# single-endpoint gear-3 turn collapses analyst→eval→revise into one
# "step3-single-analyst-fallback" call and returns; a gear-4 turn invoked
# with an external-consolidation request skips native consolidation and
# formatting entirely, writing "step7-external-consolidation-handoff" and
# returning. Both write step-health.json and complete normally — they are
# not errors or degradations to flag. When the marker is present in
# actual_steps it REPLACES (never merely supplements) the listed normal
# steps in expected_steps, so these legitimate completions never render a
# permanent false "missing step" warning.
_CONTINGENCY_SATISFIERS = {
    3: {
        "step3-single-analyst-fallback": {
            "step3-depth", "step4-eval", "step5-revised",
        },
    },
    4: {
        "step7-external-consolidation-handoff": {
            "step7-consolidated", "step8-formatted",
        },
    },
}


def trace_ref_for_dir(trace_dir: str | None) -> str | None:
    """Return the machine-resolvable trace ref for a turn directory.

    The ref is ``"<conversation_id>/<turn_timestamp>"`` relative to
    ``TRACE_ROOT`` — no absolute paths, so conversation.json entries stay
    portable across machines and relocations. Returns ``None`` for a
    ``None``/empty ``trace_dir`` or a directory outside the trace root.
    """
    if not trace_dir:
        return None
    try:
        root = _safe_trace_root(create=False)
        candidate = Path(trace_dir)
        rel_parts = candidate.absolute().relative_to(root.absolute()).parts
        if len(rel_parts) != 2:
            return None
        conversation_dir = root / rel_parts[0]
        if (root.is_symlink() or conversation_dir.is_symlink()
                or candidate.is_symlink()):
            return None
        if not _rp.within_base(candidate.resolve(strict=False), root.resolve(strict=False)):
            return None
        return "/".join(rel_parts)
    except Exception:
        return None


def _manifest_skeleton(conversation_id: str | None,
                       turn_ts: str,
                       conversation_tag: str = "") -> dict[str, Any]:
    """The schema-v1 manifest as written at trace start."""
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "turn_timestamp_utc": turn_ts,
        "trace_kind": "unknown",
        "terminal_status": "open",
        "gear": None,
        "mode": None,
        "framework_id": None,
        "milestone_id": None,
        "expected_steps": [],
        "actual_steps": [],
        "derived_artifacts": [],
        "redaction_level": ("private" if conversation_tag == "private"
                            else "default"),
        "retention_state": "default",
        "parent_trace_ref": None,
        "child_trace_refs": [],
        "finalized_at": None,
    }


def _expected_steps_for(kind: str, gear: int | None,
                        actual: list[str] | None = None) -> list[str]:
    """Static required-step derivation (design Q3: per-gear tables).

    Short-circuit kinds expect nothing beyond metadata — except ``direct``
    (the gear-1/2 bypass), which runs step1 before bypassing and therefore
    expects the step1 files. A pipeline turn expects its gear's table,
    adjusted for any contingency-fallback marker actually observed (see
    ``_CONTINGENCY_SATISFIERS`` — a legitimate reduced-footprint completion,
    not a missing step). A clarification resume expects the gear table
    minus the step1 files (the resume reuses the paused turn's stored
    step1 dict; step1 is never re-run, so expecting it would manufacture a
    false missing-step warning). Unknown gear → empty list (never guess).
    Lists are sorted so expected/actual diff cleanly.
    """
    if kind == "direct":
        return sorted(_REQUIRED_STEPS_COMMON)
    if kind in SHORT_CIRCUIT_KINDS or kind == "clarification_pending":
        # A paused (clarification_pending) turn legitimately ends after
        # step1; its step1 files show up in actual_steps as observed.
        return []
    table = _REQUIRED_STEPS_BY_GEAR.get(gear) if gear else None
    if not table:
        return []
    required = set(table)
    if kind == "clarification_resume":
        required = {s for s in required if not s.startswith("step1")}
    else:
        actual_set = set(actual or [])
        for marker, replaced in _CONTINGENCY_SATISFIERS.get(gear, {}).items():
            if marker in actual_set:
                required -= replaced
                required.add(marker)
    return sorted(required)


def _scan_turn_dir(trace_dir: str) -> tuple[list[str], list[str]]:
    """Classify the turn dir's contents into (actual_steps, derived).

    ``actual_steps`` = stems of ``step*.json`` files that are real pipeline
    steps; ``derived`` = summary/derived artifacts present (step-health,
    visual hook/emissions, cost-summary). Markdown siblings and JSONL logs
    are neither.
    """
    actual: list[str] = []
    derived: list[str] = []
    for name in os.listdir(trace_dir):
        if not name.endswith(".json") or name.endswith(".tmp"):
            continue
        stem = name[:-len(".json")]
        if stem in _DERIVED_STEP_STEMS:
            derived.append(stem)
        elif name in _DERIVED_EXTRA_FILES:
            derived.append(stem)
        elif stem.startswith("step"):
            actual.append(stem)
        # metadata.json / trace-manifest.json are structural, not steps.
    return sorted(actual), sorted(derived)


def finalize_manifest(trace_dir: str | None,
                      kind: str = "unknown",
                      status_hint: str | None = None,
                      mode: str | None = None,
                      gear: int | None = None,
                      parent_trace_ref: str | None = None) -> None:
    """Finalize the turn's trace manifest. Idempotent; never raises.

    Called from the single generator-level ``finally`` wrapping each server
    turn path (design Q1), so it also fires on ``GeneratorExit`` (client
    disconnect) and uncaught exceptions. Safe to call repeatedly — it
    re-derives from the turn dir and atomically overwrites
    (``compute_cost_summary`` precedent).

    ``terminal_status`` derivation, in precedence order (design-gate
    conditions 1 and 2):

    1. ``status_hint == "error"`` → ``error``. Set by the caller both for
       caught-yield-error-and-return paths and for exceptions propagating
       out of the generator body.
    2. ``status_hint == "paused"`` → ``paused``. A clarification pause is
       an intentional stop, never ``abandoned``.
    3. ``status_hint == "completed"`` or ``step-health.json`` present →
       ``completed``. The explicit hint covers gear-1/2 pipeline turns,
       which never write step-health.
    4. kind in the short-circuit set → ``short_circuit``.
    5. otherwise → ``abandoned``.
    """
    if not trace_dir:
        return
    try:
        owned_trace_dir = _validated_existing_trace_dir(trace_dir)
        trace_dir = str(owned_trace_dir)
        manifest_path = os.path.join(trace_dir, MANIFEST_FILENAME)
        # Start from the on-disk manifest so fields this finalizer does not
        # own (retention_state, redaction_level, child_trace_refs, a
        # previously-set parent_trace_ref) survive re-finalization.
        manifest: dict[str, Any] | None = None
        try:
            with open(manifest_path) as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                manifest = loaded
        except Exception:
            manifest = None
        if manifest is None:
            # Pre-manifest trace dir (or unreadable skeleton) — rebuild from
            # the dir name; conversation_id is the parent dir name.
            conv = os.path.basename(os.path.dirname(trace_dir)) or None
            manifest = _manifest_skeleton(
                None if conv == "_orphan" else conv,
                os.path.basename(trace_dir),
            )

        actual, derived = _scan_turn_dir(trace_dir)
        step_health_present = "step-health" in derived

        # step-health.json is the ACTUAL-execution ground truth, written by
        # whichever gear function actually completed. The caller's ``gear``
        # is only a pre-dispatch prediction, stamped before run_gear3 /
        # run_gear4 execute — and both silently degrade to a lower gear
        # internally (single-endpoint / unrecoverable-analyst fallback)
        # without the caller ever finding out. When both a fallback and a
        # final completion write step-health.json, the LAST write (the
        # gear that actually finished) wins on disk — so step-health.json
        # always wins here when present and readable, never just when the
        # caller passed gear=None (a stale gear=4 hint must not survive a
        # turn that actually ran and completed as gear 3).
        if step_health_present:
            try:
                with open(os.path.join(trace_dir, "step-health.json")) as f:
                    _sh_gear = json.load(f).get("gear")
                if _sh_gear is not None:
                    gear = _sh_gear
            except Exception:
                pass
        if mode is None:
            try:
                with open(os.path.join(trace_dir,
                                       "step1-pre-routing.json")) as f:
                    mode = json.load(f).get("dispatched_mode_id")
            except Exception:
                mode = None

        # A full-pipeline turn refines to its gear-specific kind once the
        # gear is known; a turn abandoned before gear selection stays the
        # honest bare "chat".
        if kind == "chat" and gear:
            kind = f"chat-gear{gear}"

        if status_hint == "error":
            status = "error"
        elif status_hint == "paused":
            status = "paused"
        elif status_hint == "completed" or step_health_present:
            status = "completed"
        elif kind in SHORT_CIRCUIT_KINDS:
            status = "short_circuit"
        else:
            status = "abandoned"

        manifest.update({
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "trace_kind": kind,
            "terminal_status": status,
            "gear": gear,
            "mode": mode,
            "expected_steps": _expected_steps_for(kind, gear, actual),
            "actual_steps": actual,
            "derived_artifacts": derived,
            "finalized_at": _dt.datetime.utcnow().isoformat() + "Z",
        })
        if parent_trace_ref:
            manifest["parent_trace_ref"] = parent_trace_ref
        _atomic_write_json(manifest_path, manifest)
    except Exception as e:
        # Fail-open (design-gate Q1): the manifest must never break a turn.
        print(f"[pipeline_trace] finalize_manifest failed: {e}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _atomic_write_json(path: str, data: Any) -> None:
    _rp.atomic_write_text(
        path,
        json.dumps(data, indent=2, default=_json_default),
    )


def _atomic_write_text(path: str, text: str) -> None:
    _rp.atomic_write_text(path, text)


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
        root = _safe_trace_root(create=False)
        conv_dir = _rp.safe_owned_subdir(root, conv, create=False)
        if not conv_dir.exists():
            return None
        latest_pointer = conv_dir / "_latest.txt"
        if latest_pointer.exists() and not latest_pointer.is_symlink():
            ts = _read_text_no_follow(latest_pointer).strip()
            try:
                candidate = _rp.safe_owned_subdir(
                    conv_dir, ts, create=False,
                )
            except ValueError:
                candidate = None
            if candidate is not None and candidate.is_dir():
                return str(candidate)
        # Fallback: scan and pick the lexicographically latest
        entries = sorted(
            entry.name for entry in os.scandir(conv_dir)
            if entry.is_dir(follow_symlinks=False)
            and not entry.is_symlink()
            and not entry.name.startswith("_")
        )
        if entries:
            return str(conv_dir / entries[-1])
        return None
    except Exception:
        return None


def list_traces(conversation_id: str | None) -> list[str]:
    """Return all trace directories for a conversation, oldest first."""
    try:
        conv = conversation_id or "_orphan"
        root = _safe_trace_root(create=False)
        conv_dir = _rp.safe_owned_subdir(root, conv, create=False)
        if not conv_dir.exists():
            return []
        return sorted(
            str(conv_dir / entry.name)
            for entry in os.scandir(conv_dir)
            if entry.is_dir(follow_symlinks=False)
            and not entry.is_symlink()
            and not entry.name.startswith("_")
        )
    except Exception:
        return []
