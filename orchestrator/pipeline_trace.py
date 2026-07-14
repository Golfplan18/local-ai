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

import argparse
import html
import json
import os
import re
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

MAX_TRACE_JSON_BYTES = 1024 * 1024
MAX_TRACE_TEXT_BYTES = 512 * 1024
MAX_TRACE_EXPORT_BYTES = 5 * 1024 * 1024
TRACE_EXPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"

_STEP_LABELS = {
    "step1-phase-a": "Prompt cleanup",
    "step1-pre-routing": "Route selection",
    "step2-context": "Context package",
    "step3-depth": "Depth analysis",
    "step3-single-analyst-fallback": "Single-analyst fallback",
    "step4-eval": "Evaluation",
    "step5-revised": "Revision",
    "step6-verifier-cycle-1": "Verifier cycle 1",
    "step6-verifier-cycle-2": "Verifier cycle 2",
    "step7-consolidated": "Consolidation",
    "step7-external-consolidation-handoff": "External consolidation handoff",
    "step8-formatted": "Final formatting",
    "step-health": "Step health",
}

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
    root_real = root.resolve(strict=False)
    raw_candidate = Path(trace_dir)
    if raw_candidate.is_symlink():
        raise ValueError(f"trace directory is not an owned directory: {raw_candidate}")
    candidate = raw_candidate.resolve(strict=False)
    try:
        parts = candidate.relative_to(root_real).parts
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


def _read_text_limited_no_follow(path: Path, limit: int) -> tuple[str | None, str | None]:
    """Read one regular direct child with a byte cap and no symlink follow."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except Exception as exc:
        return None, f"read failed: {exc}"
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            return None, "not a regular file"
        size = os.fstat(fd).st_size
        if size > limit:
            return None, f"file too large: {size} bytes > {limit} bytes"
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            try:
                return stream.read(), None
            except UnicodeDecodeError as exc:
                return None, f"text decode failed: {exc}"
    finally:
        if fd >= 0:
            os.close(fd)


def _read_json_limited_no_follow(path: Path, limit: int) -> tuple[Any | None, str | None]:
    text, error = _read_text_limited_no_follow(path, limit)
    if error:
        return None, error
    try:
        return json.loads(text or ""), None
    except Exception as exc:
        return None, f"json parse failed: {exc}"


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
        root = _safe_trace_root(create=True)
        conv_dir = _rp.safe_owned_subdir(root, conv, create=True)
        base_ts = _now_ts()
        suffix = 1
        while True:
            ts = base_ts if suffix == 1 else f"{base_ts}-{suffix}"
            trace_path = conv_dir / ts
            trace_dir = str(trace_path)
            # Defence-in-depth: never create a path containing a literal "~".
            # _resolve_ora_home() should already prevent this, but if TRACE_ROOT
            # is ever reintroduced as a literal-"~" path, disable tracing for the
            # turn rather than littering the working directory with a "~" tree.
            if "~" in trace_dir:
                print("[pipeline_trace] start_trace: refusing literal '~' path "
                      f"{trace_dir!r}; tracing disabled this turn", file=sys.stderr)
                return None
            try:
                os.mkdir(trace_path)
                break
            except FileExistsError:
                suffix += 1
                continue
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


def record_model_call_config(trace_dir: str | None,
                             endpoint: dict | None,
                             call_meta: dict[str, Any] | None = None) -> None:
    """Append a redacted per-call endpoint/config snapshot.

    Records model identity and sampling/runtime knobs only. Prompt content and
    credentials are intentionally excluded; API keys/base URLs with embedded
    credentials are never persisted.
    """
    if not trace_dir:
        return
    endpoint = endpoint or {}
    call_meta = call_meta or {}
    sampling_keys = (
        "temperature", "top_p", "top_k", "max_tokens",
        "max_completion_tokens", "timeout", "request_timeout",
        "reasoning_effort",
    )
    record = {
        "timestamp_utc": _dt.datetime.utcnow().isoformat() + "Z",
        "step": call_meta.get("step") or "",
        "slot": call_meta.get("slot"),
        "gear": call_meta.get("gear"),
        "config_name": call_meta.get("config_name"),
        "invocation_id": call_meta.get("invocation_id"),
        "physical_attempt": call_meta.get("physical_attempt"),
        "attempt_index": call_meta.get("attempt_index"),
        "provider_attempt": call_meta.get("provider_attempt"),
        "effective_max_tokens": call_meta.get("effective_max_tokens"),
        "endpoint_id": endpoint.get("id") or endpoint.get("name"),
        "endpoint_name": endpoint.get("name"),
        "endpoint_type": endpoint.get("type"),
        "service": endpoint.get("service"),
        "provider": endpoint.get("provider"),
        "model_id": (
            endpoint.get("model_id") or endpoint.get("model")
            or endpoint.get("id") or endpoint.get("name")
        ),
        "openrouter_fallback_model_id": endpoint.get("openrouter_fallback_model_id"),
        "sampling": {
            k: endpoint.get(k)
            for k in sampling_keys
            if endpoint.get(k) is not None
        },
    }
    base_url = endpoint.get("base_url") or endpoint.get("url")
    if isinstance(base_url, str) and base_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            if parsed.hostname:
                record["base_url_host"] = (
                    f"{parsed.hostname}:{parsed.port}"
                    if parsed.port else parsed.hostname
                )
            elif parsed.netloc:
                record["base_url_host"] = parsed.netloc.rsplit("@", 1)[-1]
            else:
                record["base_url_host"] = ""
        except Exception:
            record["base_url_host"] = ""
    append_jsonl(trace_dir, "model-call-config.jsonl", record)


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
    "direct", "trace-probe-control",
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
        root_real = root.resolve(strict=False)
        candidate = Path(trace_dir)
        candidate_real = candidate.resolve(strict=False)
        rel_parts = candidate_real.relative_to(root_real).parts
        if len(rel_parts) != 2:
            return None
        conversation_dir = root / rel_parts[0]
        owned = _rp.safe_owned_subdir(root, rel_parts[0], rel_parts[1], create=False)
        if (root.is_symlink() or conversation_dir.is_symlink()
                or owned.is_symlink()):
            return None
        return "/".join(rel_parts)
    except Exception:
        return None


def resolve_trace_ref(trace_ref: str | None) -> str | None:
    """Resolve ``<conversation_id>/<turn>`` to a manifest-bearing turn dir.

    Rejects traversal, absolute paths, root refs, and conversation-dir refs.
    """
    if not trace_ref or not isinstance(trace_ref, str):
        return None
    ref = trace_ref.strip().replace("\\", "/")
    if not ref or ref.startswith("/") or ref.startswith("../") or "/../" in ref:
        return None
    parts = [p for p in ref.split("/") if p]
    if len(parts) != 2 or any(p in (".", "..") for p in parts):
        return None
    try:
        candidate = _safe_trace_dir(parts[0], parts[1], create=False)
    except Exception:
        return None
    manifest = candidate / MANIFEST_FILENAME
    if (not candidate.is_dir() or candidate.is_symlink()
            or not manifest.is_file() or manifest.is_symlink()):
        return None
    return str(candidate.resolve(strict=False))


def read_manifest(trace_dir: str | None) -> dict[str, Any] | None:
    if not trace_dir:
        return None
    try:
        owned_trace_dir = _validated_existing_trace_dir(trace_dir)
        data, error = _read_json_limited_no_follow(
            owned_trace_dir / MANIFEST_FILENAME,
            MAX_TRACE_JSON_BYTES,
        )
        if error:
            return None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def update_manifest_fields(trace_dir: str | None, **fields: Any) -> dict[str, Any] | None:
    """Best-effort in-place manifest update preserving unrelated fields."""
    if not trace_dir:
        return None
    try:
        manifest = read_manifest(trace_dir)
        if manifest is None:
            return None
        manifest.update(fields)
        _atomic_write_json(os.path.join(trace_dir, MANIFEST_FILENAME), manifest)
        return manifest
    except Exception as exc:
        print(f"[pipeline_trace] update_manifest_fields failed: {exc}",
              file=sys.stderr)
        return None


def append_child_trace_ref(parent_trace_dir: str | None,
                           child_trace_ref: str | None) -> None:
    """Append a child trace ref to the parent manifest, deduping in order."""
    if not parent_trace_dir or not child_trace_ref:
        return
    try:
        manifest = read_manifest(parent_trace_dir)
        if manifest is None:
            return
        refs = manifest.get("child_trace_refs")
        if not isinstance(refs, list):
            refs = []
        refs = [r for r in refs if isinstance(r, str)]
        if child_trace_ref not in refs:
            refs.append(child_trace_ref)
        update_manifest_fields(parent_trace_dir, child_trace_refs=refs)
    except Exception as exc:
        print(f"[pipeline_trace] append_child_trace_ref failed: {exc}",
              file=sys.stderr)


def append_probe_trace_ref(source_trace_dir: str | None,
                           probe_trace_ref: str | None) -> None:
    """Record a probe relationship without treating the probe as a child."""
    if not source_trace_dir or not probe_trace_ref:
        return
    try:
        manifest = read_manifest(source_trace_dir)
        if manifest is None:
            return
        refs = manifest.get("probe_trace_refs")
        if not isinstance(refs, list):
            refs = []
        refs = [ref for ref in refs if isinstance(ref, str)]
        if probe_trace_ref not in refs:
            refs.append(probe_trace_ref)
        update_manifest_fields(source_trace_dir, probe_trace_refs=refs)
    except Exception as exc:
        print(f"[pipeline_trace] append_probe_trace_ref failed: {exc}",
              file=sys.stderr)


def set_retention_state(trace_ref: str, state: str) -> dict[str, Any] | None:
    """Set retention_state for a resolved turn trace ref."""
    if state not in {"default", "pinned"}:
        raise ValueError("retention state must be 'default' or 'pinned'")
    parts = _trace_ref_parts(trace_ref)
    if parts is None:
        return None
    conversation_id, _turn_ts = parts
    with _rp.conversation_lifecycle_lock(conversation_id):
        trace_dir = resolve_trace_ref(trace_ref)
        if trace_dir is None:
            return None
        owned = _validated_existing_trace_dir(trace_dir)
        manifest = read_manifest(str(owned))
        if manifest is None:
            return None
        if manifest.get("terminal_status") == "open":
            raise ValueError("cannot pin an open trace")
        manifest = dict(manifest)
        manifest["retention_state"] = state
        _atomic_write_json(str(owned / MANIFEST_FILENAME), manifest)
        return manifest


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
        "investigates_trace_ref": None,
        "probe_trace_refs": [],
        "contract_snapshot": None,
        "contract_capture_error": None,
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
    if kind == "trace-debug":
        return ["step-debug-request", "step-debug-result"]
    if kind == "trace-probe":
        return ["step-probe-prepare", "step-probe-approval", "step-probe-model-attempt", "step-probe-result", "step-health"]
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
                      parent_trace_ref: str | None = None,
                      framework_id: str | None = None,
                      milestone_id: str | None = None,
                      child_trace_refs: list[str] | None = None) -> None:
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
            "framework_id": (
                framework_id if framework_id is not None
                else manifest.get("framework_id")
            ),
            "milestone_id": (
                milestone_id if milestone_id is not None
                else manifest.get("milestone_id")
            ),
            "expected_steps": _expected_steps_for(kind, gear, actual),
            "actual_steps": actual,
            "derived_artifacts": derived,
            "finalized_at": _dt.datetime.utcnow().isoformat() + "Z",
        })
        if parent_trace_ref:
            manifest["parent_trace_ref"] = parent_trace_ref
        if child_trace_refs is not None:
            existing = manifest.get("child_trace_refs")
            merged: list[str] = []
            for ref in (existing if isinstance(existing, list) else []):
                if isinstance(ref, str) and ref not in merged:
                    merged.append(ref)
            for ref in child_trace_refs:
                if isinstance(ref, str) and ref not in merged:
                    merged.append(ref)
            manifest["child_trace_refs"] = merged
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



def _trace_ref_parts(trace_ref: str | None) -> tuple[str, str] | None:
    if not trace_ref or not isinstance(trace_ref, str):
        return None
    ref = trace_ref.strip().replace("\\", "/")
    if not ref or ref.startswith("/") or ref.startswith("../") or "/../" in ref:
        return None
    parts = [p for p in ref.split("/") if p]
    if len(parts) != 2 or any(p in (".", "..") for p in parts):
        return None
    return parts[0], parts[1]


def _dedupe_strings(values: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(values, list):
        return out
    for value in values:
        if isinstance(value, str) and value not in out:
            out.append(value)
    return out


def _step_role_label(step_name: str) -> str:
    if step_name in _STEP_LABELS:
        return _STEP_LABELS[step_name]
    stem = step_name
    if stem.startswith("step"):
        stem = stem[4:]
    return stem.replace("-", " ").strip().title() or step_name


def _manifest_step_sets(manifest: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    expected = _dedupe_strings(manifest.get("expected_steps"))
    actual = _dedupe_strings(manifest.get("actual_steps"))
    derived = _dedupe_strings(manifest.get("derived_artifacts"))
    observed = set(actual) | set(derived)
    missing = [step for step in expected if step not in observed]
    unexpected = [step for step in actual if step not in expected]
    return expected, actual, derived, missing, unexpected


def _safe_projection_context_locked(trace_ref: str) -> tuple[Path, dict[str, Any], str, str] | None:
    parts = _trace_ref_parts(trace_ref)
    if parts is None:
        return None
    conversation_id, turn_ts = parts
    trace_dir = resolve_trace_ref(trace_ref)
    if trace_dir is None:
        return None
    owned = _validated_existing_trace_dir(trace_dir)
    manifest = read_manifest(str(owned))
    if manifest is None:
        return None
    return owned, manifest, conversation_id, turn_ts


def _trace_manifest_projection_from_manifest(trace_ref: str, manifest: dict[str, Any]) -> dict[str, Any]:
    expected, actual, derived, missing, unexpected = _manifest_step_sets(manifest)
    ordered: list[str] = []
    for step in expected + actual:
        if step.startswith("step") and step not in ordered:
            ordered.append(step)
    if "step-health" in derived and "step-health" not in ordered:
        ordered.append("step-health")
    steps = [{
        "step_name": step,
        "label": _step_role_label(step),
        "expected": step in expected,
        "actual": step in actual,
        "missing": step in missing,
        "health": step == "step-health",
    } for step in ordered]
    fields = {
        key: manifest.get(key)
        for key in (
            "schema_version", "conversation_id", "turn_timestamp_utc",
            "trace_kind", "terminal_status", "gear", "mode", "framework_id",
            "milestone_id", "redaction_level", "retention_state",
            "parent_trace_ref", "child_trace_refs", "finalized_at",
            "investigates_trace_ref", "probe_trace_refs", "contract_capture_error",
        )
    }
    fields.update({
        "trace_ref": trace_ref,
        "expected_steps": expected,
        "actual_steps": actual,
        "derived_artifacts": derived,
        "missing_steps": missing,
        "unexpected_steps": unexpected,
        "steps": steps,
        "open": manifest.get("terminal_status") == "open",
    })
    return fields


def trace_manifest_projection(trace_ref: str | None) -> dict[str, Any] | None:
    """Return a browser-safe manifest summary for one trace ref."""
    if not trace_ref:
        return None
    parts = _trace_ref_parts(trace_ref)
    if parts is None:
        return None
    conversation_id, _turn_ts = parts
    try:
        with _rp.conversation_lifecycle_lock(conversation_id):
            ctx = _safe_projection_context_locked(trace_ref)
            if ctx is None:
                return None
            _trace_dir, manifest, _conv, _turn = ctx
            return _trace_manifest_projection_from_manifest(trace_ref, manifest)
    except Exception:
        return None


def _trace_step_projection_locked(trace_ref: str,
                                  safe_step: str,
                                  trace_dir: Path,
                                  manifest: dict[str, Any]) -> dict[str, Any] | None:
    expected, actual, derived, _missing, _unexpected = _manifest_step_sets(manifest)
    allowed = set(expected) | set(actual)
    if safe_step == "step-health":
        if "step-health" not in derived and not (trace_dir / "step-health.json").exists():
            return None
    elif safe_step not in allowed:
        return None
    json_path = trace_dir / f"{safe_step}.json"
    md_path = trace_dir / f"{safe_step}.md"
    errors: list[str] = []
    payload = None
    json_present = False
    markdown = None
    markdown_present = False
    if json_path.exists():
        json_present = True
        payload, error = _read_json_limited_no_follow(json_path, MAX_TRACE_JSON_BYTES)
        if error:
            errors.append(f"{safe_step}.json: {error}")
            payload = None
    elif safe_step != "step-health":
        errors.append(f"{safe_step}.json is missing")
    if md_path.exists():
        markdown_present = True
        markdown, error = _read_text_limited_no_follow(md_path, MAX_TRACE_TEXT_BYTES)
        if error:
            errors.append(f"{safe_step}.md: {error}")
            markdown = None
    return {
        "trace_ref": trace_ref,
        "step_name": safe_step,
        "label": _step_role_label(safe_step),
        "expected": safe_step in expected,
        "actual": safe_step in actual,
        "health": safe_step == "step-health",
        "json_present": json_present,
        "markdown_present": markdown_present,
        "payload": payload,
        "markdown": markdown,
        "errors": errors,
    }


def trace_step_projection(trace_ref: str | None, step_name: str | None) -> dict[str, Any] | None:
    """Return a bounded projection for one manifest-listed step."""
    if not trace_ref or not step_name:
        return None
    try:
        safe_step = _safe_trace_filename(step_name, label="trace step projection")
    except Exception:
        return None
    if not safe_step.startswith("step"):
        return None
    parts = _trace_ref_parts(trace_ref)
    if parts is None:
        return None
    conversation_id, _turn_ts = parts
    try:
        with _rp.conversation_lifecycle_lock(conversation_id):
            ctx = _safe_projection_context_locked(trace_ref)
            if ctx is None:
                return None
            trace_dir, manifest, _conv, _turn = ctx
            return _trace_step_projection_locked(trace_ref, safe_step, trace_dir, manifest)
    except Exception:
        return None


def _escaped_simple_markdown(text: str | None) -> str:
    """Escape first, then allow only inert formatting tags."""
    s = html.escape(text or "", quote=True)
    code_blocks: list[str] = []

    def _hold_code(match: re.Match[str]) -> str:
        code_blocks.append(f"<pre><code>{match.group(2).strip()}</code></pre>")
        return f"\n@@CODEBLOCK{len(code_blocks) - 1}@@\n"

    s = re.sub(r"```(\w*)\n?([\s\S]*?)```", _hold_code, s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"^###### (.+)$", r"<h6>\1</h6>", s, flags=re.M)
    s = re.sub(r"^##### (.+)$", r"<h5>\1</h5>", s, flags=re.M)
    s = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", s, flags=re.M)
    s = re.sub(r"^### (.+)$", r"<h3>\1</h3>", s, flags=re.M)
    s = re.sub(r"^## (.+)$", r"<h2>\1</h2>", s, flags=re.M)
    s = re.sub(r"^# (.+)$", r"<h1>\1</h1>", s, flags=re.M)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    s = re.sub(r"^&gt; ?(.*)$", r"<blockquote>\1</blockquote>", s, flags=re.M)
    s = s.replace("</blockquote>\n<blockquote>", "<br>")

    def _table(match: re.Match[str]) -> str:
        lines = match.group(0).strip().split("\n")
        sep = next((i for i, line in enumerate(lines) if re.match(r"^\|[\s\-:|]+\|$", line.strip())), -1)
        if sep < 1:
            return match.group(0)
        head = "".join(f"<th>{cell.strip()}</th>" for cell in lines[0].strip()[1:-1].split("|"))
        rows = []
        for row in lines[sep + 1:]:
            rows.append("<tr>" + "".join(f"<td>{cell.strip()}</td>" for cell in row.strip()[1:-1].split("|")) + "</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>\n"

    s = re.sub(r"((?:^\|.+\|[ \t]*\n)+)", _table, s, flags=re.M)
    s = re.sub(r"^[-*] (.+)$", r"<li>\1</li>", s, flags=re.M)
    s = re.sub(r"(<li>.*</li>(\n|$))+", lambda m: "<ul>" + m.group(0).replace("\n", "") + "</ul>", s)
    s = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", s, flags=re.M)
    s = re.sub(r"(<li>.*</li>(\n|$))+", lambda m: "<ol>" + m.group(0).replace("\n", "") + "</ol>" if "\n" in m.group(0) else m.group(0), s)
    for idx, block in enumerate(code_blocks):
        s = s.replace(f"@@CODEBLOCK{idx}@@", block)
    s = re.sub(r"\n*(</?(?:h[1-6]|ul|ol|li|table|thead|tbody|tr|th|td|pre|blockquote|code|br)[^>]*>)\n*", r"\1", s)
    s = re.sub(r"\n{2,}", "<br><br>", s)
    s = s.replace("\n", "<br>")
    return s


def trace_export_html(trace_ref: str | None) -> tuple[str, str] | None:
    if not trace_ref:
        return None
    parts = _trace_ref_parts(trace_ref)
    if parts is None:
        return None
    conversation_id, _turn_ts = parts
    try:
        with _rp.conversation_lifecycle_lock(conversation_id):
            ctx = _safe_projection_context_locked(trace_ref)
            if ctx is None:
                return None
            trace_dir, raw_manifest, _conv, _turn = ctx
            manifest = _trace_manifest_projection_from_manifest(trace_ref, raw_manifest)
            safe_ref = str(manifest["trace_ref"])
            filename = "ora-trace-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", safe_ref) + ".html"
            sections: list[str] = []
            warning = ""
            if manifest.get("terminal_status") == "open":
                warning = '<div class="warning">This trace is still open and may be incomplete.</div>'
            if manifest.get("redaction_level") == "private":
                warning += '<div class="warning">Private trace: handle the exported file accordingly.</div>'
            for row in manifest.get("steps") or []:
                name = row.get("step_name")
                try:
                    safe_step = _safe_trace_filename(name, label="trace step projection")
                except Exception:
                    safe_step = ""
                step = _trace_step_projection_locked(safe_ref, safe_step, trace_dir, raw_manifest) if safe_step else None
                if step is None:
                    sections.append(f"<section><h2>{html.escape(name or 'unknown', quote=True)}</h2><p>Step unavailable.</p></section>")
                    continue
                md_html = _escaped_simple_markdown(step.get("markdown")) if step.get("markdown") else "<p>No Markdown sibling recorded.</p>"
                payload = html.escape(json.dumps(step.get("payload"), indent=2, default=_json_default), quote=True) if step.get("payload") is not None else ""
                errors = "".join(f"<li>{html.escape(e, quote=True)}</li>" for e in step.get("errors") or [])
                sections.append(
                    "<section class=\"step\">"
                    f"<h2>{html.escape(step['step_name'], quote=True)} - {html.escape(step['label'], quote=True)}</h2>"
                    f"<div class=\"markdown\">{md_html}</div>"
                    + (f"<pre><code>{payload}</code></pre>" if payload else "")
                    + (f"<ul class=\"errors\">{errors}</ul>" if errors else "")
                    + "</section>"
                )
            missing = "".join(f"<li>{html.escape(s, quote=True)}</li>" for s in manifest.get("missing_steps") or []) or "<li>None</li>"
            summary = html.escape(json.dumps({k: manifest.get(k) for k in (
                "trace_ref", "trace_kind", "terminal_status", "gear", "mode",
                "framework_id", "milestone_id", "retention_state", "redaction_level",
                "parent_trace_ref", "child_trace_refs", "finalized_at",
            )}, indent=2, default=_json_default), quote=True)
            doc = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\"{html.escape(TRACE_EXPORT_CSP, quote=True)}\"><title>Ora Trace Walk</title><style>
body{{font-family:Georgia,'Times New Roman',serif;margin:2rem;line-height:1.5;background:#f7f1e6;color:#201b16}}pre{{white-space:pre-wrap;background:#211f1b;color:#f5efe2;padding:1rem;border-radius:10px;overflow:auto}}code{{font-family:Menlo,Consolas,monospace}}.warning{{border:1px solid #a65f00;background:#fff4d8;padding:.75rem;margin:.75rem 0;border-radius:8px}}.step{{border-top:1px solid #c7bca8;padding-top:1rem;margin-top:1rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #b8ad99;padding:.25rem .5rem}}blockquote{{border-left:4px solid #9c7b4f;margin-left:0;padding-left:1rem;color:#584834}}.errors{{color:#8a1f11}}</style></head>
<body><h1>Ora Trace Walk</h1>{warning}<pre><code>{summary}</code></pre><h2>Missing expected steps</h2><ul>{missing}</ul>{''.join(sections)}</body></html>"""
            encoded = doc.encode("utf-8")
            if len(encoded) > MAX_TRACE_EXPORT_BYTES:
                notice = html.escape(f"Export too large: {len(encoded)} bytes > {MAX_TRACE_EXPORT_BYTES} bytes", quote=True)
                doc = f"<!doctype html><html><head><meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\"{html.escape(TRACE_EXPORT_CSP, quote=True)}\"><title>Ora Trace Walk</title></head><body><h1>Ora Trace Walk</h1><p>{notice}</p></body></html>"
            return doc, filename
    except Exception:
        return None


def list_trace_refs(conversation_id: str | None) -> list[str]:
    refs: list[str] = []
    if not conversation_id:
        return refs
    with _rp.conversation_lifecycle_lock(conversation_id):
        for trace_dir in list_traces(conversation_id):
            ref = trace_ref_for_dir(trace_dir)
            if ref and resolve_trace_ref(ref):
                refs.append(ref)
    return refs


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


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or pin Ora trace manifests.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("pin", "unpin", "status"):
        p = sub.add_parser(name)
        p.add_argument("trace_ref")
    args = parser.parse_args(argv)
    if args.command == "status":
        trace_dir = resolve_trace_ref(args.trace_ref)
        manifest = read_manifest(trace_dir) if trace_dir else None
        if manifest is None:
            print(json.dumps({"ok": False, "error": "trace_ref not found"}))
            return 1
        print(json.dumps({
            "ok": True,
            "trace_ref": args.trace_ref,
            "retention_state": manifest.get("retention_state", "default"),
        }, indent=2))
        return 0
    state = "pinned" if args.command == "pin" else "default"
    manifest = set_retention_state(args.trace_ref, state)
    if manifest is None:
        print(json.dumps({"ok": False, "error": "trace_ref not found"}))
        return 1
    print(json.dumps({
        "ok": True,
        "trace_ref": args.trace_ref,
        "retention_state": manifest.get("retention_state"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
