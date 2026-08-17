#!/usr/bin/env python3
"""
Universal Chat Server — server.py
Browser-based chat interface with pipeline-integrated agentic loop.
All tiers: Tier 0 through Tier C.

Model-calling, tool execution, and pipeline logic live in orchestrator/boot.py.
This file handles Flask routing, SSE streaming, conversation persistence, and UI APIs.
"""

import os, sys, json, re, threading, time, uuid, shutil, io, zipfile, hashlib, copy, queue
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

def _resolve_server_workspace(environ=None, server_file=None) -> str:
    """Resolve and export the checkout root before importing runtime_paths.

    An explicit ORA_HOME remains authoritative. Without one, the server belongs
    to the checkout containing this file—not an unrelated ``~/ora`` checkout.
    Exporting the derived root keeps runtime_paths and legacy WORKSPACE consumers
    on one identity even when a preview harness launches from another cwd.
    """
    env = os.environ if environ is None else environ
    explicit = str(env.get("ORA_HOME") or "").strip()
    root = explicit or str(Path(server_file or __file__).resolve().parents[1])
    env["ORA_HOME"] = root
    # A final empty component appends the host separator, preserving the legacy
    # trailing-separator contract used throughout this module.
    return os.path.join(root, "")


# WORKSPACE must be established before runtime_paths can be imported because it
# lives under orchestrator/, which the sys.path bootstrap below has to add first.
WORKSPACE = _resolve_server_workspace()
MODELS_JSON  = os.path.join(WORKSPACE, "config/models.json")
MENTAL_MODELS_DIR = os.path.join(WORKSPACE, "lenses/")
MAX_ITERATIONS = 10

sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/tools/"))
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
# Also expose the repo root itself so package-qualified imports
# (`from orchestrator.<module>`) resolve regardless of cwd / PYTHONPATH —
# the launch.json invocation doesn't set either. Strip either separator so a
# Windows trailing backslash is handled too.
sys.path.insert(0, WORKSPACE.rstrip("/\\") or WORKSPACE)

import runtime_paths as rp

# Conversation roots come from the single cross-platform source (honors
# ORA_CONVERSATIONS / a relocation), not a hardcoded ~/Documents path. They are
# used only below this point, so sourcing them post-import is safe.
CONVERSATIONS_DIR = os.path.join(rp.CONVERSATIONS_STR, "")
CONVERSATIONS_RAW = os.path.join(rp.CONVERSATIONS_STR, "raw", "")


def _routing_config_path() -> str:
    return str(rp.routing_config_path())


def _routing_config_write_path() -> str:
    path = rp.routing_config_write_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _model_refresh_env() -> dict:
    rp.ensure_runtime_dirs()
    env = os.environ.copy()
    env.update(rp.runtime_refresh_env())
    return env

# Import all shared functions from orchestrator
from boot import (
    load_boot_md, load_routing_config as load_config, get_active_endpoint as get_endpoint,
    get_slot_endpoint, resolve_single_pass_endpoint, get_endpoint_by_id,
    list_interactive_endpoints, call_model,
    parse_tool_calls, strip_tool_calls, execute_tool,
    run_step1_cleanup, run_step2_context_assembly, build_system_prompt_for_gear,
    _single_pass_system_prompt, _compose_output_style, _resolve_effective_style_id,
    run_gear3, run_gear4, _run_model_with_tools, run_single_pass_with_tools,
    run_pipeline, parse_user_command,
    route_output, TOOLS_AVAILABLE, compare_intent_with_mode,
    list_pickable_frameworks, vision_capable_for_endpoint,
    compose_dispatch_announcement, stage3_input_completeness_check,
)
from dispatcher import (
    dispatch as dispatcher_dispatch, set_permission_mode,
    set_mcp_client, TOOL_REGISTRY, reset_consecutive,
)
from hooks import fire_hooks
from compaction import compact_context

# Phase 13-14 imports (graceful fallback if not available)
try:
    from sidebar_window import (
        get_sidebar_window, clear_sidebar_window, clear_all_sidebar_windows,
    )
    SIDEBAR_WINDOW_AVAILABLE = True
except ImportError:
    SIDEBAR_WINDOW_AVAILABLE = False

# Retained for extensions that imported the former incognito-mode warning.
# Stealth/private behavior now lives on the Dialogue envelope, but the remote-
# provider limitation remains true even though core routes no longer consume
# this constant directly.
PRIVACY_CAVEAT = (
    "This mode removes the local record. Anything sent to commercial API "
    "endpoints during this Dialogue was received by the provider and is not "
    "affected by local deletion. True privacy requires local models for "
    "the Dialogue."
)

try:
    from resilience import get_degradation_path, format_degradation_signal, should_release_kv_cache, release_kv_cache
    RESILIENCE_AVAILABLE = True
except ImportError:
    RESILIENCE_AVAILABLE = False

try:
    from orchestrator.tools.runtime_pipeline import RuntimePipeline
    RUNTIME_PIPELINE_AVAILABLE = True
except ImportError:
    RUNTIME_PIPELINE_AVAILABLE = False

try:
    from flask import (
        Flask, request, Response, jsonify, stream_with_context,
        send_from_directory,
    )
    import flask
except ImportError:
    print("Flask not installed. Run: pip install flask")
    sys.exit(1)

# Stdlib queue used by remaining SSE plumbing (chat pipeline, document
# processing). The capture/transcribe/render/jobs SSE fan-outs that
# used to share this were retired 2026-05-01 in favor of polling.
import queue as _stdlib_queue

app = Flask(__name__)

# ── SSE helpers ──────────────────────────────────────────────────────────────

def _sse(event_type, **kwargs):
    """Format a server-sent event."""
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n"


def _boot_context_api():
    """Return the active legacy ``boot`` module that owns its ContextVars.

    The server and CLI intentionally share the top-level compatibility module.
    Resolving it at the request seam also keeps test/dev module reloads from
    leaving the server bound to obsolete ContextVar instances.
    """
    return __import__("boot")


# ── Async job queue (WP-7.6) ────────────────────────────────────────────────
#
# orchestrator/job_queue.py tracks every async capability invocation
# and mirrors each job to disk. The browser polls per-conversation
# state via the hydration endpoint below; the SSE fan-out that used
# to live here was retired 2026-05-01 (browser fully migrated to
# polling 2026-04-30, no live consumers remained).

try:
    # Package-qualified import keeps every caller on the same singleton.
    # Importing the same file as both ``job_queue`` and
    # ``orchestrator.job_queue`` creates two independent in-memory queues.
    from orchestrator.job_queue import get_default_queue as _get_job_queue
    _HAS_JOB_QUEUE = True
except Exception as _e:  # pragma: no cover — defensive
    _get_job_queue = None
    _HAS_JOB_QUEUE = False
    print(f"[server] job_queue unavailable: {_e}")


@app.route("/api/jobs/<conversation_id>")
def jobs_list(conversation_id):
    """Hydration endpoint — return all jobs for a conversation.

    Used when a chat panel mounts (page load or server restart) so the
    UI can re-render the queue strip + chat-stream pending entries for
    every still-active job. Returns the on-disk-mirrored list verbatim
    (terminal entries included so the client can decide whether to
    show recently-finished jobs).
    """
    if not _HAS_JOB_QUEUE or _get_job_queue is None:
        return json.dumps({"jobs": [], "available": False})
    try:
        jobs = _get_job_queue().list_jobs(conversation_id)
    except Exception as exc:  # pragma: no cover — defensive
        return json.dumps({"jobs": [], "error": str(exc)})
    return json.dumps({"jobs": jobs, "available": True})


# ── Audio/Video Phase 1 — capture endpoints ──────────────────────────────────
#
# media_capture.CaptureManager emits events (started, duration, level,
# paused, resumed, complete, failed) to subscribers; this section fans
# them out to per-connection SSE queues. Same pattern as the job_queue
# wiring above.

try:
    from media_capture import (
        get_default_manager as _get_capture_manager,
        list_avfoundation_devices as _list_capture_devices,
        capture_region_snapshot as _capture_region_snapshot,
    )
    _HAS_CAPTURE = True
except Exception as _e:  # pragma: no cover — defensive
    _get_capture_manager = None
    _list_capture_devices = None
    _capture_region_snapshot = None
    _HAS_CAPTURE = False
    print(f"[server] media_capture unavailable: {_e}")

# Capture SSE fan-out retired 2026-05-01 — browser polls
# /api/capture/<id>/state via capture-controls.js since 2026-04-30.


def _json_response(payload: dict, status: int = 200):
    return Response(json.dumps(payload), status=status,
                    mimetype="application/json")


@app.route("/api/capture/devices", methods=["GET"])
def capture_devices():
    """Return the platform's available capture devices.

    On macOS this is the parsed output of
    ``ffmpeg -f avfoundation -list_devices true -i ""``. The browser
    populates the source dropdown from this. ``available: false`` if
    FFmpeg is missing.
    """
    if not _HAS_CAPTURE or _list_capture_devices is None:
        return _json_response({"available": False, "video": [], "audio": []})
    devices = _list_capture_devices()
    return _json_response({"available": True, **devices})


@app.route("/api/capture/region-snapshot", methods=["POST"])
def capture_region_snapshot_endpoint():
    """Grab a single still frame of a video device for region selection.

    Phase 4: the client posts ``{video_device: <index>}``. The server
    captures one frame via FFmpeg and returns it as JPEG. The client
    paints it inside the visual pane and lets the user drag a rectangle
    to define the crop region used on the next Start.
    """
    if not _HAS_CAPTURE or _capture_region_snapshot is None:
        return _json_response({"error": "capture unavailable"}, status=503)
    body = request.get_json(silent=True) or {}
    video_device = (body.get("video_device") or "").strip()
    if not video_device:
        return _json_response({"error": "video_device required"}, status=400)

    snapshots_dir = os.path.expanduser("~/ora/staging/region-snapshots/")
    os.makedirs(snapshots_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    target = os.path.join(snapshots_dir, f"snapshot-{timestamp}.jpg")
    try:
        ok = _capture_region_snapshot(video_device, __import__("pathlib").Path(target))
    except Exception as e:
        return _json_response({"error": f"snapshot failed: {e}"}, status=500)
    if not ok or not os.path.exists(target):
        return _json_response({"error": "snapshot produced no file"}, status=500)

    # Stream the bytes back inline. Small enough that we don't need a
    # separate static-serving step (a screen frame is ~200 KB JPEG).
    return send_from_directory(snapshots_dir, os.path.basename(target),
                               mimetype="image/jpeg")


@app.route("/api/capture/start", methods=["POST"])
def capture_start():
    if not _HAS_CAPTURE or _get_capture_manager is None:
        return _json_response({"error": "capture unavailable"}, status=503)
    body = request.get_json(silent=True) or {}
    conv_id = (body.get("conversation_id") or "").strip()
    if not _valid_live_conversation_id(conv_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    options = dict(body.get("options") or {})
    with _conversation_lifecycle_lock(conv_id):
        if _is_conversation_deleted(conv_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            effective_tag, _created = _ensure_artifact_conversation_envelope(
                conv_id, body.get("tag", ""),
            )
        except Exception as exc:
            return _json_response({"error": str(exc)}, status=409)
        options["_effective_conversation_tag"] = effective_tag
        try:
            capture_id = _get_capture_manager().start_capture(conv_id, options)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
    state = _get_capture_manager().get_state(capture_id)
    return _json_response({"capture_id": capture_id, "state": state})


@app.route("/api/capture/<capture_id>/pause", methods=["POST"])
def capture_pause(capture_id):
    if not _HAS_CAPTURE or _get_capture_manager is None:
        return _json_response({"error": "capture unavailable"}, status=503)
    try:
        _get_capture_manager().pause_capture(capture_id)
        state = _get_capture_manager().get_state(capture_id)
    except KeyError:
        return _json_response({"error": "unknown capture_id"}, status=404)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"state": state})


@app.route("/api/capture/<capture_id>/resume", methods=["POST"])
def capture_resume(capture_id):
    if not _HAS_CAPTURE or _get_capture_manager is None:
        return _json_response({"error": "capture unavailable"}, status=503)
    try:
        _get_capture_manager().resume_capture(capture_id)
        state = _get_capture_manager().get_state(capture_id)
    except KeyError:
        return _json_response({"error": "unknown capture_id"}, status=404)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"state": state})


@app.route("/api/capture/<capture_id>/stop", methods=["POST"])
def capture_stop(capture_id):
    if not _HAS_CAPTURE or _get_capture_manager is None:
        return _json_response({"error": "capture unavailable"}, status=503)
    try:
        result = _get_capture_manager().stop_capture(capture_id)
    except KeyError:
        return _json_response({"error": "unknown capture_id"}, status=404)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response(result)


@app.route("/api/capture/<capture_id>/state", methods=["GET"])
def capture_state(capture_id):
    if not _HAS_CAPTURE or _get_capture_manager is None:
        return _json_response({"error": "capture unavailable"}, status=503)
    try:
        return _json_response(_get_capture_manager().get_state(capture_id))
    except KeyError:
        return _json_response({"error": "unknown capture_id"}, status=404)


# /api/capture/stream retired 2026-05-01 — see comment above.


# ── Audio/Video Phase 2 — transcription endpoints ────────────────────────────
#
# Drop dispatcher path: chat-panel detects audio/video MIME on input-pane
# drop, posts the file to /api/transcribe, server stages it to disk,
# spawns Whisper, and on completion writes a vault note tagged
# `incubating` with `type: transcript`.

try:
    from transcription import (
        get_default_manager as _get_transcription_manager,
    )
    from vault_transcript import write_transcript_note as _write_transcript_note
    _HAS_TRANSCRIPTION = True
except Exception as _e:  # pragma: no cover — defensive
    _get_transcription_manager = None
    _write_transcript_note = None
    _HAS_TRANSCRIPTION = False
    print(f"[server] transcription unavailable: {_e}")

# Track the staged source path per transcription so the vault-write
# hook can resolve the source media without re-querying the manager.
_transcription_source_paths: dict[str, str] = {}
_transcription_vault_paths: dict[str, str] = {}
_transcription_conversations: dict[str, str] = {}
_transcription_tags: dict[str, str] = {}
_transcription_vault_status: dict[str, str] = {}
_transcription_vault_errors: dict[str, str] = {}
_transcription_metadata_lock = threading.RLock()


def _transcription_complete_hook(event: dict) -> None:
    """Vault-write side effect on transcription completion.

    The SSE fan-out that used to layer on top of this was retired
    2026-05-01 (browser polls /api/transcribe/<id>/state since
    2026-04-30). The vault-write side-effect remains: on 'complete'
    we write the canonical transcript note and stash its path in
    ``_transcription_vault_paths`` so the polling endpoint can include
    it in subsequent state responses.
    """
    if event.get("type") != "complete":
        return
    tid = event.get("transcription_id")
    if not tid or not _HAS_TRANSCRIPTION:
        return
    with _transcription_metadata_lock:
        conversation_id = (
            event.get("conversation_id")
            or _transcription_conversations.get(tid)
            or ""
        )
        fallback_tag = event.get("tag") or _transcription_tags.get(tid) or ""
    if not _valid_existing_conversation_id(conversation_id):
        print(
            f"[server] transcription {tid} completed without a valid "
            "conversation owner; refusing an unowned vault derivative",
            file=sys.stderr,
            flush=True,
        )
        return
    try:
        with _conversation_lifecycle_lock(conversation_id):
            if _is_conversation_deleted(conversation_id):
                return
            effective_tag = _effective_conversation_tag(
                conversation_id, fallback_tag,
            )
            # Stealth is creation-only and leaves no durable content outside
            # the session tree. The session-owned source/Whisper JSON are
            # removed by Close/Delete Forever.
            if effective_tag == "stealth":
                with _transcription_metadata_lock:
                    _transcription_vault_status[tid] = "skipped"
                return
            mgr = _get_transcription_manager()
            state = mgr.get_state(tid)
            with _transcription_metadata_lock:
                source = (
                    _transcription_source_paths.get(tid)
                    or state.get("source_path")
                    or ""
                )
            full_state = mgr._jobs.get(tid)
            segments = full_state.segments if full_state else []
            plain_text = full_state.plain_text if full_state else ""
            vault_path = _write_transcript_note(
                source_media_path=source,
                plain_text=plain_text,
                segments=segments,
                language=state.get("language"),
                duration_ms=state.get("duration_ms"),
                transcription_model=(
                    state.get("transcription_model")
                    or "whisper-local:unknown"
                ),
                conversation_id=conversation_id,
                private=effective_tag == "private",
            )
            with _transcription_metadata_lock:
                _transcription_vault_paths[tid] = str(vault_path)
                _transcription_vault_status[tid] = "written"
                _transcription_vault_errors.pop(tid, None)
    except Exception as exc:
        # Vault write failures show up on the next /state poll via the
        # absence of vault_path. The transcription itself remains in
        # the 'complete' state — the user can re-run vault export
        # manually if desired.
        print(f"[server] transcription vault-write failed for {tid}: {exc}")
        with _transcription_metadata_lock:
            _transcription_vault_status[tid] = "failed"
            _transcription_vault_errors[tid] = str(exc)


if _HAS_TRANSCRIPTION and _get_transcription_manager is not None:
    try:
        _get_transcription_manager().subscribe(_transcription_complete_hook)
    except Exception as _e:  # pragma: no cover — defensive
        print(f"[server] transcription manager subscribe failed: {_e}")


_TRANSCRIPTION_STAGING_DIR = os.path.join(str(rp.ORA_HOME), "sessions")


@app.route("/api/transcribe", methods=["POST"])
def transcribe_upload_and_start():
    """Multipart upload + Whisper start in one round-trip.

    Body: ``multipart/form-data`` with field ``file`` containing the
    audio/video and ``conversation_id``. Optional form fields: ``tag``,
    ``language`` (ISO code or 'auto'), ``model`` (model name without
    ggml- prefix).

    Returns: ``{ transcription_id, source_path }``.
    """
    if not _HAS_TRANSCRIPTION or _get_transcription_manager is None:
        return _json_response({"error": "transcription unavailable"}, status=503)
    f = request.files.get("file")
    if f is None or not f.filename:
        return _json_response({"error": "file is required"}, status=400)
    conversation_id = (request.form.get("conversation_id") or "").strip()
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)

    requested_tag = request.form.get("tag", "")
    envelope_created = False
    envelope_available = False

    options = {}
    lang     = (request.form.get("language") or "").strip()
    model    = (request.form.get("model") or "").strip()
    provider = (request.form.get("provider") or "").strip()
    openrouter_model        = (request.form.get("openrouter_model") or "").strip()
    openrouter_audio_model  = (request.form.get("openrouter_audio_model") or "").strip()
    openrouter_audio_question = (request.form.get("openrouter_audio_question") or "").strip()
    # Fill in user-settings defaults when the browser didn't override.
    if _HAS_USER_SETTINGS and _user_settings is not None:
        try:
            if not lang:     lang     = _user_settings.get_setting("whisper.default_language") or ""
            if not model:    model    = _user_settings.get_setting("whisper.model_size") or ""
            if not provider: provider = _user_settings.get_setting("whisper.provider") or ""
            if not openrouter_model:
                openrouter_model = _user_settings.get_setting("whisper.openrouter_model") or ""
            if not openrouter_audio_model:
                openrouter_audio_model = _user_settings.get_setting("whisper.openrouter_audio_model") or ""
            if not openrouter_audio_question:
                openrouter_audio_question = _user_settings.get_setting("whisper.openrouter_audio_question") or ""
        except Exception:
            pass
    provider = (provider or "whisper_local").lower()
    if lang:              options["language"]          = lang
    if model:             options["model"]             = model
    options["provider"]   = provider
    if provider == "openrouter" and openrouter_model:
        options["openrouter_model"] = openrouter_model
    if provider == "openrouter_audio":
        if openrouter_audio_model:
            options["openrouter_audio_model"] = openrouter_audio_model
        if openrouter_audio_question:
            options["openrouter_audio_question"] = openrouter_audio_question

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            effective_tag, envelope_created = (
                _ensure_artifact_conversation_envelope(
                    conversation_id, requested_tag,
                )
            )
            from orchestrator.conversation_memory import (
                _conversation_path as _conversation_envelope_path,
                _DEFAULT_SESSIONS_ROOT as _conversation_sessions_root,
            )
            envelope_available = _conversation_envelope_path(
                conversation_id, _conversation_sessions_root,
            ).is_file()
        except Exception as exc:
            return _json_response({"error": str(exc)}, status=409)

        safe_name = os.path.basename(f.filename or "upload").strip() or "upload"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        staging_root = Path(_TRANSCRIPTION_STAGING_DIR)
        try:
            transcription_staging = rp.safe_owned_subdir(
                staging_root,
                conversation_id,
                "transcriptions",
                create=True,
            )
        except Exception as e:
            return _json_response({
                "error": f"staging setup failed: {e}",
                "envelope_created": envelope_created,
                "envelope_available": envelope_available,
            }, status=500)
        staging_dir = str(transcription_staging)
        safe_name = re.sub(r"[\x00-\x1f\x7f]+", "_", safe_name)
        staged_path = os.path.join(staging_dir, f"{timestamp}-{safe_name}")
        try:
            _save_filestorage_no_follow(f, staged_path)
        except Exception as e:
            return _json_response({
                "error": f"upload save failed: {e}",
                "envelope_created": envelope_created,
                "envelope_available": envelope_available,
            }, status=500)

        options["_conversation_id"] = conversation_id
        options["_conversation_tag"] = effective_tag
        try:
            tid = _get_transcription_manager().start(staged_path, options)
        except Exception as e:
            try:
                os.unlink(staged_path)
            except OSError:
                pass
            return _json_response({
                "error": f"start failed: {e}",
                "envelope_created": envelope_created,
                "envelope_available": envelope_available,
            }, status=500)
        with _transcription_metadata_lock:
            _transcription_source_paths[tid] = staged_path
            _transcription_conversations[tid] = conversation_id
            _transcription_tags[tid] = effective_tag
            status = _transcription_vault_status.setdefault(tid, "pending")
            if status == "pending":
                _transcription_vault_errors.pop(tid, None)

    return _json_response({
        "transcription_id": tid,
        "source_path": staged_path,
        "conversation_id": conversation_id,
        "tag": effective_tag,
        "envelope_created": envelope_created,
        "envelope_available": envelope_available,
    })


@app.route("/api/transcribe/<transcription_id>/state", methods=["GET"])
def transcribe_state(transcription_id):
    if not _HAS_TRANSCRIPTION or _get_transcription_manager is None:
        return _json_response({"error": "transcription unavailable"}, status=503)
    try:
        state = _get_transcription_manager().get_state(transcription_id)
    except KeyError:
        return _json_response({"error": "unknown transcription_id"}, status=404)
    with _transcription_metadata_lock:
        state["vault_path"] = _transcription_vault_paths.get(transcription_id)
        vault_status = _transcription_vault_status.get(
            transcription_id, "pending",
        )
        state["vault_status"] = vault_status
        state["vault_error"] = _transcription_vault_errors.get(transcription_id)
    # Browser polling and manager events share one status field. Keep the
    # persisted manager key for compatibility while emitting the event-shaped
    # alias consumed by transcribe-input.js.
    state["type"] = (
        "finalizing"
        if state.get("state") == "complete" and vault_status == "pending"
        else state.get("state")
    )
    return _json_response(state)


# /api/transcribe/stream retired 2026-05-01 — transcribe-input.js
# polls /api/transcribe/<id>/state since 2026-04-30.


# ── Text-to-speech ───────────────────────────────────────────────────────────
#
# Two providers:
#   local_say   — macOS `say` binary. Free, instant, decent quality, offline.
#                 Voices live in System Settings → Accessibility → Spoken Content.
#   openrouter  — OpenRouter speech endpoint (forwards to ElevenLabs / OpenAI tts /
#                 etc. depending on the chosen model). Paid; better voices.
#
# Endpoints:
#   GET  /api/tts/voices  — list available local-say voices (used by Speech tab).
#   POST /api/tts         — synthesize text → audio bytes. Body: {text, provider,
#                            voice|openrouter_model, openrouter_voice?}.

@app.route("/api/tts/voices", methods=["GET"])
def tts_list_voices():
    """Return the macOS `say -v ?` voice catalog as JSON.

    Output rows look like: ``Samantha            en_US    # ...``.
    The non-Mac case (Linux dev box) returns an empty list — the
    speech tab degrades gracefully to OpenRouter-only.
    """
    import subprocess
    say_bin = shutil.which("say")
    if not say_bin:
        return _json_response({"voices": []})
    try:
        r = subprocess.run([say_bin, "-v", "?"], capture_output=True,
                           text=True, timeout=5)
    except Exception as e:
        return _json_response({"voices": [], "error": str(e)})
    voices = []
    for line in r.stdout.splitlines():
        if not line.strip(): continue
        # Format: "Name    en_US    # sample sentence"
        parts = line.split("#", 1)
        head  = parts[0].rstrip()
        # The locale is the last whitespace-delimited token on `head`.
        toks = head.rsplit(None, 1)
        if len(toks) == 2:
            name, lang = toks[0].strip(), toks[1].strip()
        else:
            name, lang = head.strip(), ""
        if name:
            voices.append({"name": name, "language": lang})
    voices.sort(key=lambda v: v["name"].lower())
    return _json_response({"voices": voices})


def _tts_local_say(text: str, voice: str) -> tuple[bytes | None, str | None]:
    """Run macOS `say` then convert to WAV via `afconvert` for browser
    compatibility (Chrome doesn't reliably play AIFF; WAV plays everywhere).
    Returns (wav_bytes, "audio/wav") or (None, error_message)."""
    import subprocess, tempfile
    say_bin       = shutil.which("say")
    afconvert_bin = shutil.which("afconvert") or "/usr/bin/afconvert"
    if not say_bin:
        return None, "macOS `say` binary not found"
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as a:
        aiff_path = a.name
    wav_path = aiff_path[:-5] + ".wav"
    try:
        argv = [say_bin, "-o", aiff_path]
        if voice: argv += ["-v", voice]
        argv.append(text)
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None, f"say failed: {r.stderr.strip()[:200]}"
        # Convert AIFF → 16-bit little-endian WAV. afconvert ships with macOS.
        if os.path.exists(afconvert_bin):
            r2 = subprocess.run(
                [afconvert_bin, aiff_path, wav_path,
                 "-d", "LEI16@22050", "-f", "WAVE"],
                capture_output=True, text=True, timeout=30,
            )
            if r2.returncode == 0 and os.path.exists(wav_path):
                with open(wav_path, "rb") as f:
                    return f.read(), "audio/wav"
        # Fallback: AIFF bytes if afconvert isn't available (Safari plays them).
        with open(aiff_path, "rb") as f:
            return f.read(), "audio/aiff"
    except Exception as e:
        return None, f"say exception: {e}"
    finally:
        for p in (aiff_path, wav_path):
            try: os.unlink(p)
            except Exception: pass


def _tts_openrouter(text: str, model: str, voice: str) -> tuple[bytes | None, str | None]:
    """Call OpenRouter's /v1/audio/speech endpoint via the OpenAI SDK.
    Returns (mp3_bytes, "audio/mpeg") or (None, error_message)."""
    try:
        import keyring
        key = (os.environ.get("OPENROUTER_API_KEY", "")
               or keyring.get_password("ora", "openrouter-api-key") or "")
    except Exception:
        key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return None, "OpenRouter API key not set"
    if not model:
        return None, "No OpenRouter speech model selected"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")
        kwargs = {"model": model, "input": text}
        if voice: kwargs["voice"] = voice
        resp = client.audio.speech.create(
            **kwargs,
            extra_headers={"HTTP-Referer": "https://ora.local", "X-Title": "Ora"},
        )
        return resp.read(), "audio/mpeg"
    except Exception as e:
        return None, f"openrouter speech failed: {e}"


@app.route("/api/tts", methods=["POST"])
def tts_synthesize():
    """Synthesize text → audio. Returns the audio bytes inline.

    Body (JSON or form): {text, provider?, voice?, openrouter_model?,
    openrouter_voice?}. Provider defaults to user-settings or local_say.
    """
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return _json_response({"error": "text required"}, status=400)
    # Cap input length to avoid runaway TTS calls.
    if len(text) > 20000:
        text = text[:20000]

    provider = (data.get("provider") or "").strip().lower()
    voice    = (data.get("voice") or "").strip()
    or_model = (data.get("openrouter_model") or "").strip()
    or_voice = (data.get("openrouter_voice") or "").strip()
    if _HAS_USER_SETTINGS and _user_settings is not None:
        try:
            if not provider: provider = (_user_settings.get_setting("speech.provider") or "").lower()
            if not voice:    voice    = _user_settings.get_setting("speech.local_voice") or ""
            if not or_model: or_model = _user_settings.get_setting("speech.openrouter_model") or ""
            if not or_voice: or_voice = _user_settings.get_setting("speech.openrouter_voice") or ""
        except Exception:
            pass
    # Platform-aware default: `say` only exists on macOS. Defaulting a
    # Windows/Linux install to local_say made every Read-aloud click 502
    # before the user ever visited the Speech settings.
    provider = provider or ("local_say" if shutil.which("say") else "openrouter")

    if provider == "local_say":
        audio, mime = _tts_local_say(text, voice)
    elif provider == "openrouter":
        audio, mime = _tts_openrouter(text, or_model, or_voice)
    else:
        return _json_response({"error": f"unknown provider: {provider}"}, status=400)

    if audio is None:
        return _json_response({"error": mime or "synthesis failed"}, status=502)

    ext = {"audio/wav": "wav", "audio/aiff": "aiff", "audio/mpeg": "mp3"}.get(mime, "bin")
    from flask import Response
    return Response(audio, mimetype=mime,
                    headers={"Content-Disposition": f"inline; filename=tts.{ext}"})


# ── Audio/Video Phase 3 — media library endpoints ────────────────────────────
#
# Per-conversation reference list of captured / imported media. Items
# added via:
#   1. Capture completion — server hook auto-adds the rendered file.
#   2. Canvas drop in video editing mode — multipart upload, staged.
#   3. JSON ``{path: <abs_path>}`` POST — register existing file.

try:
    from media_library import get_library as _get_media_library
    _HAS_MEDIA_LIBRARY = True
except Exception as _e:  # pragma: no cover — defensive
    _get_media_library = None
    _HAS_MEDIA_LIBRARY = False
    print(f"[server] media_library unavailable: {_e}")


# ── A/V Phase 8 follow-up — URL import (yt-dlp) ──────────────────────────────

try:
    from url_import import get_default_manager as _get_url_import_manager
    _HAS_URL_IMPORT = True
except Exception as _e:  # pragma: no cover — defensive
    _get_url_import_manager = None
    _HAS_URL_IMPORT = False
    print(f"[server] url_import unavailable: {_e}")


# ── A/V Phase 8 — Video Editing Suggestions framework runtime ────────────────

try:
    from video_suggestions import (
        generate_suggestions_heuristic as _gen_suggestions_heuristic,
        SuggestionValidationError as _SuggestionValidationError,
    )
    _HAS_VIDEO_SUGGESTIONS = True
except Exception as _e:  # pragma: no cover — defensive
    _gen_suggestions_heuristic = None
    _SuggestionValidationError = Exception
    _HAS_VIDEO_SUGGESTIONS = False
    print(f"[server] video_suggestions unavailable: {_e}")


# ── A/V Phase 9 — user settings (capture / whisper / export / API keys) ──────

try:
    import user_settings as _user_settings
    _HAS_USER_SETTINGS = True
except Exception as _e:  # pragma: no cover — defensive
    _user_settings = None
    _HAS_USER_SETTINGS = False
    print(f"[server] user_settings unavailable: {_e}")

try:
    import retrieval_config as _retrieval_config
    _HAS_RETRIEVAL_CONFIG = True
except Exception as _e:  # pragma: no cover — defensive
    _retrieval_config = None
    _HAS_RETRIEVAL_CONFIG = False
    print(f"[server] retrieval_config unavailable: {_e}")


_MEDIA_LIBRARY_STAGING_DEFAULT = os.path.join(
    str(rp.ORA_HOME), "staging", "media-library", "",
)
_MEDIA_LIBRARY_STAGING_DIR = _MEDIA_LIBRARY_STAGING_DEFAULT


def _media_library_staging_dir(
    conversation_id: str,
    *,
    create: bool = False,
    existing: bool = False,
) -> str:
    """Return an exact per-conversation staging directory.

    The retired flat ``<id>-<timestamp>-<name>`` convention could not
    distinguish IDs that were prefixes of one another (``a`` versus ``a-b``).
    A direct child makes ownership structural and deletion exact.
    """
    if existing:
        cid = (conversation_id or "").strip()
        if not _valid_existing_conversation_id(cid):
            raise ValueError("invalid conversation_id")
    else:
        cid = _canonical_live_conversation_id(conversation_id)
    if _MEDIA_LIBRARY_STAGING_DIR != _MEDIA_LIBRARY_STAGING_DEFAULT:
        # Explicit test/deployment override is a trusted configured root.
        parent = rp.safe_owned_subdir(
            _MEDIA_LIBRARY_STAGING_DIR, create=create,
        )
    else:
        parent = rp.safe_owned_subdir(
            rp.ORA_HOME, "staging", "media-library", create=create,
        )
    path = parent / cid
    if create:
        return str(rp.safe_owned_subdir(parent, cid, create=True))
    return str(path)


def _save_filestorage_no_follow(file_storage, target_path: str) -> None:
    """Stream one Werkzeug upload into an exclusive sibling then replace."""
    target = Path(target_path)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            file_storage.save(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _purge_media_library_staging(conversation_id: str) -> int:
    """Remove only the target's structurally-owned media staging subtree."""
    path = _media_library_staging_dir(conversation_id, existing=True)
    if os.path.islink(path):
        os.unlink(path)
        return 1
    if not os.path.exists(path):
        return 0
    if not os.path.isdir(path):
        raise ValueError(f"media staging path is not a directory: {path}")
    removed = 0
    for walk_root, dirnames, filenames in os.walk(path, followlinks=False):
        removed += len(filenames)
        removed += sum(
            1 for name in dirnames
            if os.path.islink(os.path.join(walk_root, name))
        )
    shutil.rmtree(path)
    return removed


def _capture_conversation_id_for(capture_id):
    """Look up the conversation_id for an in-flight capture from the manager."""
    if not capture_id or not _HAS_CAPTURE or _get_capture_manager is None:
        return None
    try:
        state = _get_capture_manager().get_state(capture_id)
    except Exception:
        return None
    return state.get("conversation_id")


def _media_library_capture_hook(event: dict) -> None:
    """Auto-add captured files to the conversation's media library.

    Called from the capture-event fan-out. Only acts on `complete` events
    that name a real file. Failures here must NOT block the SSE
    broadcast — we swallow exceptions and log.
    """
    if event.get("type") != "complete":
        return
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return
    conv_id = event.get("conversation_id") or _capture_conversation_id_for(
        event.get("capture_id"))
    if not conv_id:
        return
    file_path = event.get("file_path")
    if not file_path:
        return
    try:
        lib = _get_media_library(conv_id)
        lib.add_entry(file_path)
    except Exception as exc:  # pragma: no cover — defensive
        print(f"[server] media-library auto-add failed: {exc}")


if _HAS_CAPTURE and _HAS_MEDIA_LIBRARY and _get_capture_manager is not None:
    try:
        _get_capture_manager().subscribe(_media_library_capture_hook)
    except Exception as _e:  # pragma: no cover — defensive
        print(f"[server] media-library capture hook subscribe failed: {_e}")


@app.route("/api/media-library/<conversation_id>", methods=["GET"])
def media_library_list(conversation_id):
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"available": False, "entries": []})
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            lib = _get_media_library(conversation_id)
            return _json_response({"available": True, "entries": lib.list_entries()})
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)


@app.route("/api/media-library/<conversation_id>/add", methods=["POST"])
def media_library_add(conversation_id):
    """Add a file to the library.

    Two modes:
      * ``multipart/form-data`` with field ``file`` — staged to
        ``~/ora/staging/media-library/`` and registered.
      * JSON body ``{path: <abs_path>}`` — registers an existing file
        by absolute path (no copy).
    """
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    if request.files or request.form:
        requested_tag = request.form.get("tag", "")
    else:
        requested_tag = (request.get_json(silent=True) or {}).get("tag", "")
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, requested_tag,
            )
        except Exception as exc:
            return _json_response({"error": str(exc)}, status=409)
        return _media_library_add_live(conversation_id)


def _media_library_add_live(conversation_id):
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    try:
        lib = _get_media_library(conversation_id)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)

    file_storage = request.files.get("file")
    if file_storage is not None and file_storage.filename:
        safe_name = os.path.basename(file_storage.filename or "upload").strip() or "upload"
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        staging_dir = _media_library_staging_dir(conversation_id, create=True)
        staged_path = os.path.join(staging_dir, f"{timestamp}-{safe_name}")
        try:
            _save_filestorage_no_follow(file_storage, staged_path)
        except Exception as e:
            return _json_response({"error": f"save failed: {e}"}, status=500)
        try:
            entry = lib.add_entry(staged_path,
                                  display_name=safe_name,
                                  mime=file_storage.mimetype)
        except Exception as e:
            return _json_response({"error": f"add failed: {e}"}, status=500)
        return _json_response({"entry": entry})

    body = request.get_json(silent=True) or {}
    abs_path = (body.get("path") or "").strip()
    if abs_path:
        try:
            entry = lib.add_entry(abs_path,
                                  display_name=body.get("display_name"),
                                  mime=body.get("mime") or "")
        except FileNotFoundError as e:
            return _json_response({"error": str(e)}, status=404)
        except Exception as e:
            return _json_response({"error": f"add failed: {e}"}, status=500)
        return _json_response({"entry": entry})

    return _json_response({"error": "either file or path required"}, status=400)


@app.route("/api/media-library/<conversation_id>/<entry_id>", methods=["DELETE"])
def media_library_remove(conversation_id, entry_id):
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            lib = _get_media_library(conversation_id)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
        entry = lib.get_entry(entry_id)
        if entry is None:
            return _json_response({"error": "unknown entry_id"}, status=404)
        protection = None
        try:
            from orchestrator import system_protection as _sp
            state_path = lib.state_path
            pre_state = _sp.capture_path_identity(state_path)
            protection = _sp.authorize_server_action(
                "media_reference_delete",
                selectors=[_sp.path_selector(state_path)],
                params={
                    "conversation_id_digest": _sp.params_digest({
                        "conversation_id": conversation_id,
                    }),
                    "entry_id": entry_id,
                    "entry_digest": _sp.params_digest(entry),
                },
                pre_state=[pre_state],
            )
            with _sp.protected_effect(protection):
                removed = lib.remove(entry_id)
            _sp.complete_execution(
                protection, ok=removed,
                result={"removed": removed, "entry_id": entry_id},
                post_state=[_sp.capture_path_identity(state_path)],
            )
        except Exception as exc:
            try:
                from orchestrator import system_protection as _sp
                if isinstance(exc, _sp.SystemProtectionError):
                    return _system_protection_error_response(exc)
                if protection is not None:
                    _sp.complete_execution(
                        protection, ok=False,
                        result={"error": type(exc).__name__},
                        post_state=[_sp.capture_path_identity(state_path)],
                    )
            except Exception as receipt_error:
                return _system_protection_error_response(receipt_error)
            return _json_response({"error": str(exc)}, status=500)
        if not removed:
            return _json_response({"error": "entry changed before deletion"}, status=409)
        return _json_response({"removed": entry_id})


@app.route("/api/media-library/<conversation_id>/<entry_id>/rename", methods=["POST"])
def media_library_rename(conversation_id, entry_id):
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    body = request.get_json(silent=True) or {}
    new_name = (body.get("new_name") or "").strip()
    if not new_name:
        return _json_response({"error": "new_name required"}, status=400)
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            lib = _get_media_library(conversation_id)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
        try:
            entry = lib.rename(entry_id, new_name)
        except ValueError as e:
            return _json_response({"error": str(e)}, status=400)
        if entry is None:
            return _json_response({"error": "unknown entry_id"}, status=404)
        return _json_response({"entry": entry})


@app.route("/api/media-library/<conversation_id>/<entry_id>/thumbnail",
           methods=["GET"])
def media_library_thumbnail(conversation_id, entry_id):
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            lib = _get_media_library(conversation_id)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
        thumb = lib.get_thumbnail_path(entry_id)
        if thumb is None:
            return _json_response({"error": "no thumbnail"}, status=404)
        directory = str(thumb.parent)
        return send_from_directory(directory, thumb.name, mimetype="image/jpeg")


@app.route("/api/media-library/<conversation_id>/<entry_id>/waveform",
           methods=["GET"])
def media_library_waveform(conversation_id, entry_id):
    """A/V Phase 5+ polish — audio waveform thumbnail.

    Lazy + cached. First hit runs ffmpeg's ``showwavespic`` filter
    against the entry's source file; the resulting PNG is cached at
    ``<thumbnails_dir>/<entry_id>.waveform.png`` and streamed back.
    Subsequent hits skip ffmpeg.

    Returns 404 for unknown entries, non-audio/video entries, or when
    waveform rendering fails (no audio track, corrupt source, etc.).
    The browser falls back to the existing glyph in that case.
    """
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    try:
        from pathlib import Path as _Path
        from waveform import render_waveform, waveform_cache_path
    except Exception as e:
        return _json_response({"error": f"waveform module: {e}"}, status=503)
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            lib = _get_media_library(conversation_id)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
        entry = lib.get_entry(entry_id)
        if entry is None:
            return _json_response({"error": "unknown entry"}, status=404)
        if entry.get("kind") not in ("audio", "video"):
            return _json_response({"error": "entry has no audio track"}, status=404)
        source_path = entry.get("source_path")
        if not source_path:
            return _json_response({"error": "entry has no source path"}, status=404)
        src = _Path(source_path)
        if not src.exists():
            return _json_response({"error": "source file missing"}, status=404)

        cache_path = waveform_cache_path(lib.thumbnails_dir, entry_id)
        if not cache_path.exists():
            ok = render_waveform(src, cache_path)
            if not ok:
                return _json_response({"error": "waveform render failed"}, status=404)
        return send_from_directory(
            str(cache_path.parent), cache_path.name, mimetype="image/png"
        )


@app.route("/api/media-library/<conversation_id>/<entry_id>/transcript",
           methods=["GET"])
def media_library_transcript(conversation_id, entry_id):
    """A/V Phase 8 — return whisper-cli segments for a library entry.

    Reads the persistent ``.whisper.json`` that ``transcription.py`` writes
    next to every transcribed source file (see ``transcription.py`` line ~329:
    ``persistent_json = job.source_path.with_suffix('.whisper.json')``).
    Returns normalized segments matching the in-memory shape that
    ``TranscriptionManager._populate_from_whisper_json`` produces.

    404s are normal — not every library entry has been transcribed.
    """
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            lib = _get_media_library(conversation_id)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
        entry = lib.get_entry(entry_id)
        if entry is None:
            return _json_response({"error": "unknown entry"}, status=404)
        source_path = entry.get("source_path")
        if not source_path:
            return _json_response({"error": "entry has no source path"}, status=404)
    try:
        from pathlib import Path as _Path
        json_path = _Path(source_path).with_suffix(".whisper.json")
    except Exception as e:
        return _json_response({"error": f"path resolution: {e}"}, status=500)
    if not json_path.exists():
        return _json_response({"error": "no transcript"}, status=404)
    try:
        import json as _json
        raw = _json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        return _json_response({"error": f"json parse: {e}"}, status=500)
    # Normalize to the same shape transcription.py produces internally so
    # the browser sees consistent fields whether the data is fresh from
    # the manager (live transcribe) or read from disk on a later session.
    result = raw.get("result", {}) or {}
    segments_raw = raw.get("transcription", []) or []
    out_segments = []
    duration_ms = 0
    for seg in segments_raw:
        offsets = seg.get("offsets", {}) or {}
        try:
            start_ms = int(offsets.get("from") or 0)
            end_ms = int(offsets.get("to") or 0)
        except (TypeError, ValueError):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out_segments.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
        })
        if end_ms > duration_ms:
            duration_ms = end_ms
    return _json_response({
        "entry_id": entry_id,
        "language": result.get("language"),
        "duration_ms": duration_ms,
        "segments": out_segments,
    })


# ── A/V Phase 8 follow-up — URL import endpoints ─────────────────────────────
#
# Two-endpoint pair (start + state poll). The browser POSTs a URL,
# gets an import_id, then polls state until ``complete`` or
# ``failed``. yt-dlp does the actual download in a background thread
# in url_import.py. On success a new media-library entry appears.

@app.route("/api/media-library/<conversation_id>/import-url", methods=["POST"])
def media_library_import_url(conversation_id):
    if not _HAS_URL_IMPORT or _get_url_import_manager is None:
        return _json_response(
            {"error": "url import unavailable (yt-dlp not installed?)"},
            status=503,
        )
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return _json_response({"error": "url required"}, status=400)
    if not (url.startswith("http://") or url.startswith("https://")):
        return _json_response({"error": "url must start with http:// or https://"}, status=400)
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, payload.get("tag", ""),
            )
            mgr = _get_url_import_manager()
            import_id = mgr.start(conversation_id, url)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
    return _json_response({
        "import_id": import_id,
        "conversation_id": conversation_id,
        "url": url,
    })


@app.route(
    "/api/media-library/<conversation_id>/import/<import_id>/state",
    methods=["GET"],
)
def media_library_import_state(conversation_id, import_id):
    if not _HAS_URL_IMPORT or _get_url_import_manager is None:
        return _json_response({"error": "url import unavailable"}, status=503)
    try:
        mgr = _get_url_import_manager()
        state = mgr.get_state(import_id)
    except KeyError:
        return _json_response({"error": "unknown import_id"}, status=404)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    if state.get("conversation_id") != conversation_id:
        return _json_response({"error": "unknown import_id"}, status=404)
    return _json_response(state)


@app.route("/api/media-library/<conversation_id>/imports", methods=["GET"])
def media_library_imports_list(conversation_id):
    """List all imports for a conversation (in-flight + recently completed)."""
    if not _HAS_URL_IMPORT or _get_url_import_manager is None:
        return _json_response({"imports": []})
    try:
        mgr = _get_url_import_manager()
        states = mgr.list_states(conversation_id)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"imports": states})


@app.route(
    "/api/media-library/<conversation_id>/<entry_id>/suggest-edits",
    methods=["POST"],
)
def media_library_suggest_edits(conversation_id, entry_id):
    """Run the Video Editing Suggestions framework on a clip's transcript.

    POST body (optional): ``{"goals": "...", "existing_clips": [...]}``.
    Reads the same .whisper.json the transcript endpoint reads;
    invokes the heuristic suggestion generator (LLM path is wired
    but gated; user can switch via a future config). Returns the
    validated suggestions JSON.
    """
    if not _HAS_VIDEO_SUGGESTIONS or _gen_suggestions_heuristic is None:
        return _json_response(
            {"error": "video suggestions runtime unavailable"},
            status=503,
        )
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            lib = _get_media_library(conversation_id)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
        entry = lib.get_entry(entry_id)
        if entry is None:
            return _json_response({"error": "unknown entry"}, status=404)
        source_path = entry.get("source_path")
        if not source_path:
            return _json_response({"error": "entry has no source path"}, status=404)

    from pathlib import Path as _Path
    json_path = _Path(source_path).with_suffix(".whisper.json")
    if not json_path.exists():
        return _json_response({"error": "no transcript"}, status=404)
    try:
        import json as _json
        raw = _json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        return _json_response({"error": f"json parse: {e}"}, status=500)

    # Normalize transcript shape (same as the /transcript endpoint).
    result = raw.get("result", {}) or {}
    segments_raw = raw.get("transcription", []) or []
    segments = []
    duration_ms = 0
    for seg in segments_raw:
        offsets = seg.get("offsets", {}) or {}
        try:
            start_ms = int(offsets.get("from") or 0)
            end_ms = int(offsets.get("to") or 0)
        except (TypeError, ValueError):
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
        })
        if end_ms > duration_ms:
            duration_ms = end_ms
    transcript_view = {
        "language": result.get("language"),
        "duration_ms": duration_ms,
        "segments": segments,
    }

    payload = request.get_json(silent=True) or {}
    goals = payload.get("goals")
    existing_clips = payload.get("existing_clips")

    try:
        suggestions = _gen_suggestions_heuristic(
            transcript_view,
            entry_id=entry_id,
            goals=goals,
            existing_clips=existing_clips,
        )
    except _SuggestionValidationError as e:
        return _json_response(
            {"error": f"suggestion validation: {e}"}, status=500
        )
    except Exception as e:
        return _json_response({"error": f"suggestion generation: {e}"}, status=500)
    return _json_response(suggestions)


# ── A/V Phase 9 — user settings endpoints ────────────────────────────────────
#
# Eight endpoint shapes:
#   GET    /api/settings                  — current settings + API key status
#   POST   /api/settings                  — partial update, returns merged state
#   POST   /api/settings/api-key/verify   — verify where possible
#   POST   /api/settings/api-key          — store a key in keyring
#   DELETE /api/settings/api-key/<provider> — remove a key from keyring
#   GET    /api/settings/chatgpt-subscription — isolated account status
#   POST   /api/settings/chatgpt-subscription/connect — start browser login
#   DELETE /api/settings/chatgpt-subscription — log out Ora's session
#
# API key values are never returned to the browser. The status endpoint
# only reports presence (a boolean per provider).

@app.route("/api/settings", methods=["GET"])
def settings_get():
    if not _HAS_USER_SETTINGS or _user_settings is None:
        return _json_response({"error": "settings module unavailable"}, status=503)
    try:
        settings = _user_settings.load_settings()
        api_keys = _user_settings.list_api_key_status()
        try:
            groups = _user_settings.group_order()
        except Exception:
            groups = []
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({
        "settings": settings,
        "api_keys": api_keys,
        "provider_groups": groups,
        "providers": list(_user_settings.PROVIDER_LABELS.keys()),
    })


@app.route("/api/settings", methods=["POST"])
def settings_post():
    if not _HAS_USER_SETTINGS or _user_settings is None:
        return _json_response({"error": "settings module unavailable"}, status=503)
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates")
    if not isinstance(updates, dict):
        return _json_response({"error": "updates dict required"}, status=400)
    try:
        merged = _user_settings.save_settings(updates)
    except _user_settings.SettingsError as e:
        return _json_response({"error": str(e)}, status=400)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"settings": merged})


_chatgpt_catalog_signature = None
_chatgpt_catalog_signature_lock = threading.Lock()


def _sync_chatgpt_subscription_router(account_status: dict) -> None:
    """Re-bake presets, then reload Router when subscription inventory moves."""
    global _chatgpt_catalog_signature
    signature = (
        account_status.get("state") == "connected",
        account_status.get("catalog_revision"),
    )
    # Serialize the entire transition. A newer disconnect must wait for an
    # in-flight connected bake, then run its own bake and become the accepted
    # signature; otherwise the older bake can finish last and restore stale
    # subscription picks after the account has disconnected.
    with _chatgpt_catalog_signature_lock:
        if signature == _chatgpt_catalog_signature:
            return
        try:
            from orchestrator import active_configuration as _active_config
            baked = set(_active_config.bake_missing_presets(force=True) or [])
            required = set(_active_config.PRESET_ORDER)
            if not required.issubset(baked):
                missing = sorted(required.difference(baked))
                raise RuntimeError(
                    f"subscription preset re-bake incomplete: {missing}"
                )
            reloaded = _reload_pipeline_router_after_config_change()
        except Exception as exc:
            print(
                "[model-registry] ChatGPT subscription preset re-bake failed: "
                f"{type(exc).__name__}",
                flush=True,
            )
            reloaded = False
        if reloaded:
            _chatgpt_catalog_signature = signature


def _chatgpt_subscription_response(payload: dict):
    status_code = 200
    if payload.get("state") in {
        "dependency_unavailable", "secure_storage_unavailable", "error"
    }:
        status_code = 503
    return _json_response(payload, status=status_code)


@app.route("/api/settings/chatgpt-subscription", methods=["GET"])
def settings_chatgpt_subscription_status():
    from orchestrator import codex_subscription

    payload = codex_subscription.status()
    _sync_chatgpt_subscription_router(payload)
    return _chatgpt_subscription_response(payload)


@app.route("/api/settings/chatgpt-subscription/connect", methods=["POST"])
def settings_chatgpt_subscription_connect():
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    from orchestrator import codex_subscription

    payload = codex_subscription.connect()
    _sync_chatgpt_subscription_router(payload)
    return _chatgpt_subscription_response(payload)


@app.route("/api/settings/chatgpt-subscription", methods=["DELETE"])
def settings_chatgpt_subscription_disconnect():
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    from orchestrator import codex_subscription

    payload = codex_subscription.disconnect()
    _sync_chatgpt_subscription_router(payload)
    return _chatgpt_subscription_response(payload)


# ── mind.md (user context layer) ────────────────────────────────────────────
#
# Backs the Output Styles tab's user-context toggle. mind.md is user-authored
# adaptation context subordinate to the constitution and selected Persona.
# These endpoints give
# the toggle a real surface: existence/summary for the state check, a
# viewer/editor, and a create-from-template flow. The stock template is
# tracked at mindspec/mind-template.md; a mind.md whose "Default
# configuration" marker line is still present counts as un-customized.

MIND_MD_PATH = os.path.join(WORKSPACE, "mind.md")
MIND_TEMPLATE_PATH = os.path.join(WORKSPACE, "mindspec", "mind-template.md")
SELF_SPEC_PATH = os.path.join(WORKSPACE, "mindspec", "self-spec.md")
_MIND_DEFAULT_MARKER = "*Default configuration. Customize by running the"
# Mirror orchestrator/mind_guided.py::MARKER_PREFIX and
# Legacy projected-marker literal retained only so guided setup preserves
# existing user content; new MindSpec runs create Personas instead.
_MIND_GUIDED_MARKER = "<!-- ora-mind-guided:"
_MIND_PROJECTED_MARKER = "<!-- ora-mind-projected:"
_MIND_MAX_BYTES = 128 * 1024


def _mind_summary() -> dict:
    """The GET /api/mind payload: existence + content + derived facts."""
    if not os.path.isfile(MIND_MD_PATH):
        return {
            "exists": False,
            "template_available": os.path.isfile(MIND_TEMPLATE_PATH),
            "self_spec_available": os.path.isfile(SELF_SPEC_PATH),
        }
    with open(MIND_MD_PATH, encoding="utf-8") as f:
        content = f.read()
    sections = re.findall(r"^## +(.+?)\s*$", content, flags=re.MULTILINE)
    st = os.stat(MIND_MD_PATH)
    return {
        "exists": True,
        "content": content,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "sections": sections,
        "is_default_template": _MIND_DEFAULT_MARKER in content,
        "is_guided": _MIND_GUIDED_MARKER in content,
        "is_projected": _MIND_PROJECTED_MARKER in content,
        "template_available": os.path.isfile(MIND_TEMPLATE_PATH),
        "self_spec_available": os.path.isfile(SELF_SPEC_PATH),
    }


@app.route("/api/mind", methods=["GET"])
def mind_get():
    try:
        return _json_response(_mind_summary())
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


@app.route("/api/mind", methods=["POST"])
def mind_post():
    """Write mind.md. Body is either ``{"content": "..."}`` (editor save)
    or ``{"action": "create_from_template"}`` (seeds from the tracked
    stock template; refuses to overwrite an existing customized file).
    Atomic write (tmp + os.replace) either way."""
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    try:
        if action == "create_from_template":
            if not os.path.isfile(MIND_TEMPLATE_PATH):
                return _json_response(
                    {"error": "template missing (mindspec/mind-template.md)"},
                    status=503)
            current = _mind_summary()
            if current.get("exists") and not current.get("is_default_template"):
                return _json_response(
                    {"error": "mind.md exists and is customized — edit it "
                              "instead of overwriting from the template"},
                    status=409)
            with open(MIND_TEMPLATE_PATH, encoding="utf-8") as f:
                content = f.read()
        else:
            content = payload.get("content")
            if not isinstance(content, str) or not content.strip():
                return _json_response(
                    {"error": "content (non-empty string) required"}, status=400)
            if len(content.encode("utf-8")) > _MIND_MAX_BYTES:
                return _json_response(
                    {"error": f"content too large (max {_MIND_MAX_BYTES} bytes)"},
                    status=400)
        tmp = MIND_MD_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, MIND_MD_PATH)
        return _json_response(_mind_summary())
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


def _mind_guided_mod():
    try:
        import mind_guided as _mg
    except ImportError:
        from orchestrator import mind_guided as _mg
    return _mg


def _persona_mod():
    try:
        import persona as _persona
    except ImportError:
        from orchestrator import persona as _persona
    return _persona


@app.route("/api/mind/guided", methods=["GET"])
def mind_guided_get():
    """The guided-setup wizard's bootstrap: the question registry plus any
    prior answers (parsed from the provenance marker of a guided mind.md)
    so re-running the wizard prefills previous choices."""
    try:
        mg = _mind_guided_mod()
        summary = _mind_summary()
        answers, free_text = None, None
        if summary.get("exists"):
            parsed = mg.parse_marker(summary.get("content", ""))
            if parsed:
                answers = parsed.get("answers")
                free_text = parsed.get("free_text")
        return _json_response({
            "questions": mg.questions_payload(),
            "answers": answers,
            "free_text": free_text,
            "exists": summary.get("exists", False),
            "is_default_template": summary.get("is_default_template", False),
            "is_guided": summary.get("is_guided", False),
        })
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


@app.route("/api/mind/guided", methods=["POST"])
def mind_guided_post():
    """Compose mind.md from wizard answers and write it atomically.

    Body: ``{"answers": {...}, "free_text": {...}, "confirm_overwrite": bool}``.
    An existing mind.md that is neither the stock template nor a previous
    guided file (i.e. hand-edited, or written by the MindSpec interview)
    is only replaced when ``confirm_overwrite`` is set — mirrors the
    create-from-template guard."""
    payload = request.get_json(silent=True) or {}
    try:
        mg = _mind_guided_mod()
        try:
            content = mg.compose(payload.get("answers") or {},
                                 payload.get("free_text") or {})
        except ValueError as e:
            return _json_response({"error": str(e)}, status=400)
        current = _mind_summary()
        if (current.get("exists")
                and not current.get("is_default_template")
                and not current.get("is_guided")
                and not payload.get("confirm_overwrite")):
            return _json_response(
                {"error": "mind.md has hand edits (or a MindSpec interview "
                          "result) — pass confirm_overwrite to replace it",
                 "needs_confirm": True},
                status=409)
        # Preserve a legacy projected block as user context so rerunning the
        # wizard cannot silently delete existing material. New MindSpec runs
        # create Personas and never add such blocks.
        if current.get("is_projected"):
            old_content = current.get("content", "")
            marker_at = old_content.find(_MIND_PROJECTED_MARKER)
            if marker_at >= 0:
                content = content.rstrip() + "\n\n" + old_content[marker_at:].strip() + "\n"
        tmp = MIND_MD_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, MIND_MD_PATH)
        return _json_response(_mind_summary())
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


@app.route("/api/personas", methods=["GET"])
def personas_get():
    """Enumerate the Persona directory and report the current resolution."""
    try:
        persona = _persona_mod()
        result = persona.list_personas()
        selected = persona.resolve_persona()
        result["selected"] = {
            "id": selected["id"],
            "display_name": selected["display_name"],
            "source": selected["source"],
            "warnings": selected["warnings"],
        }
        return _json_response(result)
    except Exception as exc:
        return _json_response({"error": str(exc)}, status=500)


@app.route("/api/personas/compile", methods=["POST"])
def personas_compile_post():
    """Compile the archived MindSpec into one validated inactive Persona."""
    try:
        if not os.path.isfile(SELF_SPEC_PATH):
            return _json_response(
                {"error": "no self-spec found — run the MindSpec interview "
                          "first (/framework mindspec-interview)"},
                status=404)
        with open(SELF_SPEC_PATH, encoding="utf-8") as handle:
            spec_text = handle.read()
        if not spec_text or not spec_text.strip():
            return _json_response(
                {"error": "no self-spec found — run the MindSpec interview "
                          "first (/framework mindspec-interview)"},
                status=404)
        payload = request.get_json(silent=True) or {}
        persona = _persona_mod()
        selected = persona.resolve_persona()
        result = persona.compile_self_spec(
            spec_text,
            base_id=payload.get("base_id") or selected["id"],
            output_id=payload.get("output_id") or None,
        )
        if not result.get("ok"):
            status = 409 if "already exists" in result.get("error", "") else 502
            return _json_response({"error": result.get("error")}, status=status)
        return _json_response(result)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


def _style_assembly_mod():
    try:
        import style_assembly as _sa
    except ImportError:
        from orchestrator import style_assembly as _sa
    return _sa


def _style_store_mod():
    try:
        import style_store as _ss
    except ImportError:
        from orchestrator import style_store as _ss
    return _ss


def _enrich_style_entry(sid, entry):
    """A registry or custom entry -> the card dict the Output Styles picker reads:
    the four headline slots (arrangement / demeanor / elaboration / register) with
    both raw values (for editing) and short labels (for the card face), plus the
    full demeanor picks, devices, and glossary the "more" view expands."""
    entry = entry or {}
    arr = entry.get("arrangement", "")
    elab = entry.get("elaboration", 3)
    card = {
        "id": sid,
        "display_name": entry.get("display_name", sid),
        "description": entry.get("description", ""),
        "custom": bool(entry.get("custom")),
        "forked_from": entry.get("forked_from"),
        "arrangement": arr,
        "elaboration": elab,
        "demeanor": entry.get("demeanor", {}) or {},
        "devices": entry.get("devices", {}) or {},
        "glossary": entry.get("glossary", {}) or {},
        "values_source": entry.get("values_source", "default-mindspec"),
        # Optional conversational-register override (alternate demeanor); shown
        # only in the side popout. Absent/None means "inherit the written demeanor".
        "conversational": entry.get("conversational"),
    }
    try:
        _sa = _style_assembly_mod()
        card["arrangement_label"] = _sa.arrangement_short(arr)
        card["elaboration_label"] = _sa.elaboration_label(elab)
    except Exception:
        card["arrangement_label"] = arr
        card["elaboration_label"] = str(elab)
    return card


def _style_library():
    """The component-library payload explained beneath the cards: the seven
    demeanor axes with their rung text, the device overlays, the arrangement
    schemas, the craft-floor lines, and the elaboration scale."""
    lib = {
        "axes": [], "devices": [], "schemas": [], "craft": [],
        "elaboration_scale": [],
    }
    try:
        _sa = _style_assembly_mod()
        axes, devices = _sa.load_demeanor_axes()
        for axis in _sa.AXIS_ORDER:
            rungs = _sa.RUNGS.get(axis, [])
            lib["axes"].append({
                "id": axis,
                "rungs": [{"id": r, "text": axes.get(axis, {}).get(r, "")}
                          for r in rungs],
            })
        lib["devices"] = [{"id": d, "text": t} for d, t in devices.items()]
        schemas = _sa.load_arrangement_schemas()
        lib["schemas"] = [{"id": s, "label": _sa.arrangement_short(s), "text": txt}
                          for s, txt in schemas.items()]
        lib["craft"] = _sa.load_craft_floor()
        lib["elaboration_scale"] = [{"value": n, "label": _sa.ELABORATION_LABELS[n]}
                                    for n in sorted(_sa.ELABORATION_LABELS)]
    except Exception:
        pass
    return lib


def _styles_settings_block():
    block = {"default_id": "", "persona_id": "ora", "use_custom_values": False}
    try:
        if _HAS_USER_SETTINGS and _user_settings is not None:
            st = (_user_settings.load_settings() or {}).get("styles") or {}
            block = {
                "default_id": st.get("default_id", ""),
                "persona_id": st.get("persona_id", "ora"),
                "use_custom_values": bool(st.get("use_custom_values", False)),
            }
    except Exception:
        pass
    return block


@app.route("/api/styles/registry", methods=["GET"])
def styles_registry_get():
    """Everything the Output Styles configurator renders in one call: the built-in
    genre profiles, the user's saved custom profiles, the component library, and
    the current account settings (active id + the two toggles). Never 500s — an
    unreadable registry (e.g. PyYAML missing) yields empty lists."""
    profiles, custom = [], []
    try:
        for sid, entry in (_style_assembly_mod().load_registry() or {}).items():
            profiles.append(_enrich_style_entry(sid, entry or {}))
    except Exception:
        profiles = []
    try:
        for sid, entry in (_style_store_mod().load_custom_profiles() or {}).items():
            custom.append(_enrich_style_entry(sid, entry))
    except Exception:
        custom = []
    return _json_response({
        "profiles": profiles,
        "custom": custom,
        "library": _style_library(),
        "settings": _styles_settings_block(),
    })


@app.route("/api/styles/custom", methods=["POST"])
def styles_custom_create():
    """Fork a new custom profile from a genre (or another custom), or a blank one.
    Body: {forked_from?: id, display_name?: str}. Returns {profile}."""
    payload = request.get_json(silent=True) or {}
    forked_from = (payload.get("forked_from") or "").strip() or None
    display_name = (payload.get("display_name") or "").strip() or None
    base_entry = None
    if forked_from:
        try:
            base_entry = (_style_assembly_mod().load_registry() or {}).get(forked_from)
        except Exception:
            base_entry = None
        if base_entry is None:
            try:
                base_entry = _style_store_mod().get_custom_profile(forked_from)
            except Exception:
                base_entry = None
    try:
        prof = _style_store_mod().create_custom_profile(
            base_entry=base_entry, display_name=display_name, forked_from=forked_from)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"profile": _enrich_style_entry(prof["id"], prof)})


@app.route("/api/styles/custom/<sid>", methods=["PATCH", "POST"])
def styles_custom_update(sid):
    """Edit one or more lines of a custom profile. Body is the patch directly, or
    {patch: {...}}. Nested blocks (demeanor / devices / glossary) merge key-wise."""
    payload = request.get_json(silent=True) or {}
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else payload
    try:
        prof = _style_store_mod().update_custom_profile(sid, patch or {})
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    if prof is None:
        return _json_response({"error": "unknown custom profile: %s" % sid}, status=404)
    return _json_response({"profile": _enrich_style_entry(sid, prof)})


@app.route("/api/styles/custom/<sid>", methods=["DELETE"])
def styles_custom_delete(sid):
    """Delete a custom profile. If it was the account default, clear the default
    so nothing points at a missing id."""
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection = None
    try:
        from orchestrator import system_protection as _sp
        store = _style_store_mod()
        store_path = store.STORE_PATH
        settings_path = _user_settings._SETTINGS_PATH
        current = store.get_custom_profile(sid)
        if current is None:
            return _json_response({"ok": False})
        selectors = [
            _sp.path_selector(store_path),
            _sp.path_selector(settings_path),
        ]
        pre_state = [
            _sp.capture_path_identity(store_path),
            _sp.capture_path_identity(settings_path),
        ]
        protection = _sp.authorize_server_action(
            "style_profile_delete", selectors=selectors,
            params={"style_id": sid, "profile_digest": _sp.params_digest(current)},
            pre_state=pre_state,
        )
        with _sp.protected_effect(protection):
            existed = store.delete_custom_profile(sid)
            if existed and _HAS_USER_SETTINGS and _user_settings is not None:
                st = (_user_settings.load_settings() or {}).get("styles") or {}
                if st.get("default_id") == sid:
                    _user_settings.save_settings({"styles": {"default_id": ""}})
        _sp.complete_execution(
            protection, ok=existed,
            result={"deleted": existed, "style_id": sid},
            post_state=[
                _sp.capture_path_identity(store_path),
                _sp.capture_path_identity(settings_path),
            ],
        )
    except Exception as e:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(e, _sp.SystemProtectionError):
                return _system_protection_error_response(e)
            if protection is not None:
                _sp.complete_execution(
                    protection, ok=False, result={"error": type(e).__name__},
                    post_state=[
                        _sp.capture_path_identity(store_path),
                        _sp.capture_path_identity(settings_path),
                    ],
                )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"ok": bool(existed)})


@app.route("/api/retrieval/config", methods=["GET"])
def retrieval_config_get():
    if not _HAS_RETRIEVAL_CONFIG or _retrieval_config is None:
        return _json_response({"error": "retrieval config unavailable"}, status=503)
    try:
        return _json_response({"retrieval": _retrieval_config.snapshot()})
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


@app.route("/api/retrieval/config", methods=["POST"])
def retrieval_config_post():
    if not _HAS_RETRIEVAL_CONFIG or _retrieval_config is None:
        return _json_response({"error": "retrieval config unavailable"}, status=503)
    payload = request.get_json(silent=True) or {}
    result: dict = {}
    try:
        reranker_id = (payload.get("reranker_id") or "").strip()
        if reranker_id:
            opt = _retrieval_config.option_by_id(
                _retrieval_config.list_reranker_options(), reranker_id
            )
            if opt is None:
                return _json_response({"error": "unknown reranker"}, status=400)
            _retrieval_config.update_active_reranker(opt)
            result["reranker_saved"] = reranker_id

        embedding_id = (payload.get("embedding_profile_id") or "").strip()
        if embedding_id:
            opt = _retrieval_config.option_by_id(
                _retrieval_config.list_embedding_options(), embedding_id
            )
            if opt is None:
                return _json_response({"error": "unknown embedding profile"}, status=400)
            target_collections = _retrieval_config.target_collections_for_profile(embedding_id)
            if payload.get("activate_embedding"):
                _retrieval_config.update_active_embedding_profile(
                    opt,
                    collection_names=payload.get("collection_names") or target_collections,
                )
                result["embedding_activated"] = embedding_id
            else:
                result["embedding_staged"] = {
                    "profile": opt,
                    "requires_rebuild": True,
                    "target_collections": target_collections,
                }
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)

    result["retrieval"] = _retrieval_config.snapshot()
    return _json_response(result)


# ── Retrieval: embedding rebuild job ────────────────────────────────────────
#
# Switching the embedding model requires re-encoding every stored
# document. The complete primitive already exists as a CLI —
# scripts/re-embed-local.py re-embeds each collection into a PARALLEL
# new collection (sources stay live and searchable), checkpoints every
# 1000 docs, verifies target counts match sources, and with
# --activate-on-success writes the new profile + collection map into
# config/chromadb.json. These endpoints wrap it as a background job so
# the Settings → General → Retrieval pane can run it with progress.
#
# Two caveats surfaced by the 2026-07-01 review, handled here:
#   * orchestrator/embedding.py freezes its config at import — after a
#     successful activation the summary carries requires_restart: true
#     and the pane says so (the running server keeps using the old
#     index until restarted; that index is still valid, so nothing
#     breaks in the meantime).
#   * Project-managed collections (e.g. MSI's) live outside
#     target_collections_for_profile and are NOT rebuilt here — the
#     pane's confirm dialog says so.

_REEMBED_SCRIPT = os.path.join(WORKSPACE, "scripts", "re-embed-local.py")
_reembed_state = {
    "in_progress": False,
    "started_at": 0.0,
    "completed_at": 0.0,
    "profile_id": "",
    "progress": "",       # last progress line from the script
    "last_summary": None,  # {"ok", "returncode", "requires_restart"} | {"error"}
}
_reembed_lock = threading.Lock()

# Progress lines look like:
#   "  progress: 12000/138696 (8.7%)  rate: 43.1 docs/sec"
_REEMBED_PROGRESS_RE = re.compile(r"progress:\s*(\d+)/(\d+)\s*\(([\d.]+)%\)")


def _resolve_reembed_profile(profile_id: str):
    """Return the embedding-option dict for ``profile_id`` or None.

    Split out of the route so tests can patch it — option lists come
    from the machine's retrieval config otherwise.
    """
    if not _HAS_RETRIEVAL_CONFIG or _retrieval_config is None:
        return None
    return _retrieval_config.option_by_id(
        _retrieval_config.list_embedding_options(), profile_id)


def _spawn_reembed(profile_id: str, *, protection_execution) -> tuple:
    """Start the background re-embed for ``profile_id``.

    Returns ``(payload, http_status)``. Refuses when a job is already
    running, when the profile is unknown, already active, or has no
    known vector dimension (the script requires --target-dim; a probe
    must fill it in first).
    """
    import subprocess

    if protection_execution is None:
        return {"error": "system-protection authorization required"}, 403

    opt = _resolve_reembed_profile(profile_id)
    if opt is None:
        return {"error": "unknown embedding profile"}, 400
    if not opt.get("dimensions"):
        return {"error": "embedding dimension unknown for this profile — "
                         "probe it before rebuilding"}, 400
    try:
        active = (_retrieval_config.snapshot() or {}).get("active_embedding") or {}
        if str(active.get("id")) == str(profile_id):
            return {"error": "this profile is already active"}, 400
    except Exception:
        pass  # snapshot is best-effort; the rebuild itself is idempotent

    provider = "openrouter" if opt.get("provider") == "openrouter" else "ollama"

    with _reembed_lock:
        if _reembed_state["in_progress"]:
            return {
                "status": "in_progress",
                "profile_id": _reembed_state["profile_id"],
                "progress": _reembed_state["progress"],
            }, 409
        _reembed_state["in_progress"] = True
        _reembed_state["started_at"] = time.time()
        _reembed_state["completed_at"] = 0.0
        _reembed_state["profile_id"] = profile_id
        _reembed_state["progress"] = "starting…"
        _reembed_state["last_summary"] = None

    cmd = [
        sys.executable, _REEMBED_SCRIPT,
        "--target-provider", provider,
        "--target-embedder", str(opt.get("model") or profile_id),
        "--target-dim", str(int(opt["dimensions"])),
        "--target-profile-id", str(profile_id),
        "--activate-on-success",
    ]

    def _run_in_background():
        from orchestrator import system_protection as _sp
        try:
            with _sp.protected_effect(protection_execution):
                proc = subprocess.Popen(
                    cmd, cwd=WORKSPACE,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    bufsize=1,
                )
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    # Keep whichever line arrived last; progress lines get a
                    # normalized "N/M (P%)" prefix so the pane can render a
                    # stable counter.
                    m = _REEMBED_PROGRESS_RE.search(line)
                    with _reembed_lock:
                        _reembed_state["progress"] = (
                            f"{m.group(1)}/{m.group(2)} ({m.group(3)}%)"
                            if m else line[:200]
                        )
                proc.wait()
            ok = proc.returncode == 0
            with _reembed_lock:
                _reembed_state["in_progress"] = False
                _reembed_state["completed_at"] = time.time()
                _reembed_state["last_summary"] = {
                    "ok": ok,
                    "returncode": proc.returncode,
                    # embedding.py freezes its config at import; the new
                    # index only takes effect after a server restart.
                    "requires_restart": ok,
                }
            _sp.complete_execution(
                protection_execution, ok=ok,
                result={"profile_id": profile_id, "returncode": proc.returncode},
                post_state=[
                    _sp.capture_path_identity(rp.CHROMADB_DIR),
                    _sp.capture_path_identity(
                        _retrieval_config.CHROMADB_CONFIG_PATH,
                    ),
                ],
            )
        except Exception as exc:
            with _reembed_lock:
                _reembed_state["in_progress"] = False
                _reembed_state["completed_at"] = time.time()
                _reembed_state["last_summary"] = {"ok": False, "error": str(exc)}
            try:
                _sp.complete_execution(
                    protection_execution, ok=False,
                    result={"profile_id": profile_id,
                            "error": type(exc).__name__},
                    post_state=[
                        _sp.capture_path_identity(rp.CHROMADB_DIR),
                        _sp.capture_path_identity(
                            _retrieval_config.CHROMADB_CONFIG_PATH,
                        ),
                    ],
                )
            except Exception as receipt_error:
                with _reembed_lock:
                    _reembed_state["last_summary"] = {
                        "ok": False,
                        "error": (
                            "broken system-protection infrastructure: "
                            f"{receipt_error}"
                        ),
                    }

    threading.Thread(target=_run_in_background, daemon=True).start()
    return {"status": "started", "profile_id": profile_id}, 200


@app.route("/api/retrieval/rebuild/start", methods=["POST"])
def retrieval_rebuild_start():
    """Kick off the background embedding rebuild + activate flow."""
    payload = request.get_json(silent=True) or {}
    profile_id = (payload.get("embedding_profile_id") or "").strip()
    if not profile_id:
        return _json_response({"error": "embedding_profile_id required"}, status=400)
    option = _resolve_reembed_profile(profile_id)
    if option is None:
        return _json_response({"error": "unknown embedding profile"}, status=400)
    if not option.get("dimensions"):
        return _json_response({
            "error": (
                "embedding dimension unknown for this profile — probe it "
                "before rebuilding"
            ),
        }, status=400)
    try:
        active = (_retrieval_config.snapshot() or {}).get("active_embedding") or {}
        if str(active.get("id")) == str(profile_id):
            return _json_response({
                "error": "this profile is already active",
            }, status=400)
    except Exception:
        pass
    with _reembed_lock:
        if _reembed_state["in_progress"]:
            return _json_response({
                "status": "in_progress",
                "profile_id": _reembed_state["profile_id"],
                "progress": _reembed_state["progress"],
            }, status=409)
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection_execution = None
    try:
        from orchestrator import system_protection as _sp
        selectors = [
            _sp.path_selector(rp.CHROMADB_DIR),
            _sp.path_selector(_retrieval_config.CHROMADB_CONFIG_PATH),
        ]
        pre_state = [
            _sp.capture_path_identity(rp.CHROMADB_DIR),
            _sp.capture_path_identity(_retrieval_config.CHROMADB_CONFIG_PATH),
        ]
        protection_execution = _sp.authorize_server_action(
            "vector_store_rebuild", selectors=selectors,
            params={"embedding_profile_id": profile_id}, pre_state=pre_state,
        )
    except Exception as exc:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(exc, _sp.SystemProtectionError):
                return _system_protection_error_response(exc)
        except Exception:
            pass
        return _json_response({"error": str(exc)}, status=500)
    body, status = _spawn_reembed(
        profile_id, protection_execution=protection_execution,
    )
    if status != 200:
        try:
            from orchestrator import system_protection as _sp
            _sp.complete_execution(
                protection_execution, ok=False, result=body, post_state=pre_state,
            )
        except Exception as exc:
            return _system_protection_error_response(exc)
    return _json_response(body, status=status)


@app.route("/api/retrieval/rebuild/status", methods=["GET"])
def retrieval_rebuild_status():
    """Current rebuild progress / last result."""
    with _reembed_lock:
        return _json_response(dict(_reembed_state))


def _system_protection_error_response(exc):
    """Typed fail-closed response shared by protected HTTP mutations."""
    try:
        from orchestrator import system_protection as _sp
    except Exception:  # pragma: no cover - import failure is infrastructure
        return _json_response({
            "status": "system_protection_unavailable", "error": str(exc),
        }, status=503)
    if isinstance(exc, _sp.ProtectionReviewRequired):
        return _json_response({
            "status": "awaiting_system_protection_approval",
            "error": str(exc),
            "queue_id": exc.queue_id,
            "retry_required": True,
        }, status=409)
    if isinstance(exc, _sp.ProtectionDenied):
        return _json_response({
            "status": "system_protection_denied", "error": str(exc),
        }, status=403)
    return _json_response({
        "status": "system_protection_broken_infrastructure", "error": str(exc),
    }, status=503)


def _credential_protection_state(provider: str) -> tuple[str, dict]:
    from orchestrator import system_protection as _sp
    username = _user_settings._provider_username(provider)
    selector = f"credential:ora/{username}"
    return selector, _sp.capture_selector_identity(selector)


@app.route("/api/settings/api-key", methods=["POST"])
def settings_set_api_key():
    if not _HAS_USER_SETTINGS or _user_settings is None:
        return _json_response({"error": "settings module unavailable"}, status=503)
    payload = request.get_json(silent=True) or {}
    provider = (payload.get("provider") or "").strip()
    value = payload.get("value")
    if not provider:
        return _json_response({"error": "provider required"}, status=400)
    if value is None or value == "":
        return _json_response({"error": "value required"}, status=400)
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection = None
    try:
        from orchestrator import system_protection as _sp
        selector, pre_state = _credential_protection_state(provider)
        protection = _sp.authorize_server_action(
            "credential_store",
            selectors=[selector],
            params={
                "provider": provider,
                "value_digest": _sp.params_digest({"value": str(value)}),
            },
            pre_state=[pre_state],
        )
        with _sp.protected_effect(protection):
            _user_settings.set_api_key(provider, value)
        _, post_state = _credential_protection_state(provider)
        _sp.complete_execution(
            protection, ok=True, result={"provider": provider, "stored": True},
            post_state=[post_state],
        )
    except Exception as e:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(e, _sp.SystemProtectionError):
                return _system_protection_error_response(e)
            if protection is not None:
                _sp.complete_execution(
                    protection, ok=False, result={"error": type(e).__name__},
                    post_state=[_credential_protection_state(provider)[1]],
                )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)
        if isinstance(e, _user_settings.SettingsError):
            return _json_response({"error": str(e)}, status=400)
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"provider": provider, "stored": True})


@app.route("/api/settings/api-key/<provider>", methods=["DELETE"])
def settings_delete_api_key(provider):
    if not _HAS_USER_SETTINGS or _user_settings is None:
        return _json_response({"error": "settings module unavailable"}, status=503)
    if not provider:
        return _json_response({"error": "provider required"}, status=400)
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection = None
    try:
        from orchestrator import system_protection as _sp
        # Validate the provider id before reaching keyring.
        selector, pre_state = _credential_protection_state(provider)
        protection = _sp.authorize_server_action(
            "credential_delete",
            selectors=[selector], params={"provider": provider},
            pre_state=[pre_state],
        )
        with _sp.protected_effect(protection):
            _user_settings.delete_api_key(provider)
        _, post_state = _credential_protection_state(provider)
        _sp.complete_execution(
            protection, ok=True, result={"provider": provider, "deleted": True},
            post_state=[post_state],
        )
    except Exception as e:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(e, _sp.SystemProtectionError):
                return _system_protection_error_response(e)
            if protection is not None:
                _sp.complete_execution(
                    protection, ok=False, result={"error": type(e).__name__},
                    post_state=[_credential_protection_state(provider)[1]],
                )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)
        if isinstance(e, _user_settings.SettingsError):
            return _json_response({"error": str(e)}, status=400)
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"provider": provider, "deleted": True})


def _verify_provider_key(entry: dict, key: str):
    """Make the cheapest authenticated call that proves a key works.

    Returns ``(ok, message)`` where ok ∈ {True, False, None} (None = couldn't
    determine / not implemented). Uses urllib only (no new deps). Every call
    is free or negligible (auth probes / model lists / a single search), so
    Verify never lands a surprise charge — image / TTS providers (whose only
    auth proof costs a generation) are marked non-verifiable in the registry.
    """
    import urllib.request
    import urllib.error
    import json as _json

    pid = entry["id"]
    dispatch = entry.get("dispatch")
    base = (entry.get("base_url") or "").rstrip("/")

    def _get(url, headers):
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status

    def _post(url, headers, body):
        h = dict(headers); h["Content-Type"] = "application/json"
        req = urllib.request.Request(
            url, data=_json.dumps(body).encode(), headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status

    try:
        if pid == "openrouter":
            _get("https://openrouter.ai/api/v1/key", {"Authorization": f"Bearer {key}"})
        elif pid == "anthropic":
            _get("https://api.anthropic.com/v1/models",
                 {"x-api-key": key, "anthropic-version": "2023-06-01"})
        elif pid == "gemini":
            # Key via header, not the query string, so it can never land in
            # an exception/URL string that round-trips to the browser.
            _get("https://generativelanguage.googleapis.com/v1beta/models",
                 {"x-goog-api-key": key})
        elif pid == "openai" or dispatch == "openai_compatible":
            if not base:
                return None, "No base URL configured for this provider."
            _get(f"{base}/models", {"Authorization": f"Bearer {key}"})
        elif pid == "tavily":
            _post("https://api.tavily.com/search", {},
                  {"api_key": key, "query": "ping", "max_results": 1, "search_depth": "basic"})
        elif pid == "brave":
            _get("https://api.search.brave.com/res/v1/web/search?q=ping&count=1",
                 {"X-Subscription-Token": key, "Accept": "application/json"})
        elif pid == "exa":
            _post("https://api.exa.ai/search", {"x-api-key": key},
                  {"query": "ping", "numResults": 1})
        elif pid == "artificial_analysis":
            # AA auths via x-api-key (Bearer returns 401 — verified
            # empirically 2026-07-01); keep in sync with
            # scripts/sync_model_registry.py::_aa_api_get.
            _get("https://artificialanalysis.ai/api/v2/data/llms/models",
                 {"x-api-key": key})
        elif pid == "fred":
            _get(f"https://api.stlouisfed.org/fred/series?series_id=GNPCA"
                 f"&api_key={key}&file_type=json", {})
        else:
            return None, "Verification isn't available for this provider."
        return True, "Key works."
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "Key was rejected (auth failed). Check the key, and that billing is active."
        if e.code == 429:
            return True, "Key is valid but rate-limited / over quota — check billing."
        if e.code == 400 and pid == "gemini":
            return False, "Key was rejected by Google. Double-check you copied it correctly."
        # A non-auth HTTP failure does not prove the credential is bad. It may
        # be a transient provider outage, a moved probe endpoint, or a request
        # contract change. Keep the result inconclusive so Settings can store
        # the key with an honest "couldn't verify" disclosure instead of
        # blocking a possibly valid credential.
        return None, f"Couldn't confirm the key (HTTP {e.code}). Try verification again later."
    except Exception as e:
        # Scrub the key from the message — some urllib/http exceptions
        # (e.g. InvalidURL on a key with a stray space) embed the full URL,
        # which for FRED contains the key in the query string. Never let a
        # secret round-trip back into the browser.
        msg = str(e).replace(key, "***") if key else str(e)
        return None, f"Couldn't reach the provider: {msg}"


@app.route("/api/settings/api-key/verify", methods=["POST"])
def settings_verify_api_key():
    if not _HAS_USER_SETTINGS or _user_settings is None:
        return _json_response({"error": "settings module unavailable"}, status=503)
    payload = request.get_json(silent=True) or {}
    provider = (payload.get("provider") or "").strip()
    value = (payload.get("value") or "").strip()
    if not provider:
        return _json_response({"error": "provider required"}, status=400)
    try:
        import provider_registry as _reg
        entry = _reg.by_id(provider)
    except Exception:
        entry = None
    if not entry:
        return _json_response({"error": f"unknown provider {provider!r}"}, status=400)
    if not entry.get("verifiable"):
        return _json_response({"ok": None,
                               "message": "Verification isn't available for this provider."})
    # A pasted value wins (verify-before-save); otherwise the stored key.
    key = value
    if not key:
        try:
            import keyring
            key = keyring.get_password("ora", entry["keyring_username"]) or ""
        except Exception:
            key = ""
    if not key:
        return _json_response({"ok": False, "message": "No key to verify — save one first."})
    ok, message = _verify_provider_key(entry, key)
    return _json_response({"ok": ok, "message": message})


# ── Audio/Video Phase 5 — timeline state endpoints ───────────────────────────
#
# Per-conversation timeline persistence. Client loads the full state on
# mount, mutates locally, PUTs the full state on every change. No
# partial-update API; the timeline is small enough that a full PUT keeps
# the server logic simple and avoids race conditions.

try:
    from timeline import get_timeline as _get_timeline
    _HAS_TIMELINE = True
except Exception as _e:  # pragma: no cover — defensive
    _get_timeline = None
    _HAS_TIMELINE = False
    print(f"[server] timeline unavailable: {_e}")


@app.route("/api/timeline/<conversation_id>", methods=["GET"])
def timeline_load(conversation_id):
    if not _HAS_TIMELINE or _get_timeline is None:
        return _json_response({"available": False}, status=503)
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            tl = _get_timeline(conversation_id)
            return _json_response({"available": True, "timeline": tl.load()})
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)


@app.route("/api/timeline/<conversation_id>", methods=["PUT"])
def timeline_save(conversation_id):
    if not _HAS_TIMELINE or _get_timeline is None:
        return _json_response({"error": "timeline unavailable"}, status=503)
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    body = request.get_json(silent=True) or {}
    requested_tag = body.pop("_conversation_tag", "")
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, requested_tag,
            )
            tl = _get_timeline(conversation_id)
            normalized = tl.save(body)
            return _json_response({"timeline": normalized})
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)


# ── A/V Phase 6 follow-up — watermark image upload ───────────────────────────
#
# Lets the user replace the default ◎ glyph with an arbitrary PNG.
# Multipart upload lands at ``~/ora/sessions/<conv_id>/uploads/`` with
# a timestamped filename. Browser stores the absolute path in the
# timeline's watermark.image_path field and saves the timeline; the
# render pipeline then composites via FFmpeg ``overlay`` on next render.
#
# Allowed types: PNG, JPEG, WebP (transparent PNG is the typical case).

_WATERMARK_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _store_watermark_upload(conversation_id, file_storage, extension):
    canonical_id = _canonical_live_conversation_id(conversation_id)
    runtime_home = Path(
        os.environ.get("ORA_HOME") or os.path.expanduser("~/ora")
    )
    uploads_dir = str(rp.safe_owned_subdir(
        runtime_home, "sessions", canonical_id, "uploads", create=True,
    ))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    target_path = os.path.join(
        uploads_dir, f"watermark-{timestamp}{extension}",
    )
    _save_filestorage_no_follow(file_storage, target_path)
    if os.path.getsize(target_path) > 10 * 1024 * 1024:
        os.unlink(target_path)
        raise ValueError("watermark image must be under 10 MB")
    return target_path


@app.route("/api/watermark/<conversation_id>/upload", methods=["POST"])
def watermark_upload(conversation_id):
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    f = request.files.get("file")
    if f is None or not f.filename:
        return _json_response({"error": "file is required"}, status=400)
    safe_name = os.path.basename(f.filename or "watermark").strip() or "watermark"
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _WATERMARK_ALLOWED_EXT:
        return _json_response(
            {"error": f"unsupported extension {ext!r}; "
                      f"use PNG, JPEG, or WebP"},
            status=400,
        )
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, request.form.get("tag", ""),
            )
            target_path = _store_watermark_upload(conversation_id, f, ext)
        except ValueError as e:
            return _json_response({"error": str(e)}, status=400)
        except Exception as e:
            return _json_response({"error": f"save failed: {e}"}, status=500)
    return _json_response({
        "conversation_id": conversation_id,
        "image_path": target_path,
        "filename": os.path.basename(target_path),
    })


# ── Audio/Video Phase 7 — render endpoints ───────────────────────────────────
#
# Renders the conversation's timeline through FFmpeg. Output goes to the
# user's export directory (default ~/ora/exports/) and is auto-added to
# the conversation's media library.

try:
    from render import (
        get_default_manager as _get_render_manager,
        PRESETS as _RENDER_PRESETS,
    )
    _HAS_RENDER = True
except Exception as _e:  # pragma: no cover — defensive
    _get_render_manager = None
    _RENDER_PRESETS = {}
    _HAS_RENDER = False
    print(f"[server] render unavailable: {_e}")


_render_conversation_lookup: dict[str, str] = {}  # render_id → conversation_id


def _render_complete_hook(event: dict) -> None:
    """Auto-add the rendered output file to the media library on completion.

    The SSE fan-out that used to layer on top of this was retired
    2026-05-01 (browser polls /api/render/<id>/state since 2026-04-30).
    The side-effect — adding the rendered file to the conversation's
    media library so it becomes editable as a clip — remains.
    """
    if event.get("type") != "complete":
        return
    rid = event.get("render_id")
    if not rid or not _HAS_MEDIA_LIBRARY:
        return
    try:
        conv = _render_conversation_lookup.get(rid)
        output = event.get("output_path")
        if conv and output and _get_media_library is not None:
            lib = _get_media_library(conv)
            lib.add_entry(output, display_name=os.path.basename(output))
    except Exception as exc:  # pragma: no cover — defensive
        print(f"[server] render auto-add to media library failed: {exc}")


if _HAS_RENDER and _get_render_manager is not None:
    try:
        _get_render_manager().subscribe(_render_complete_hook)
    except Exception as _e:  # pragma: no cover — defensive
        print(f"[server] render manager subscribe failed: {_e}")


@app.route("/api/render/presets", methods=["GET"])
def render_presets():
    if not _HAS_RENDER:
        return _json_response({"available": False, "presets": []})
    out = []
    for key, p in _RENDER_PRESETS.items():
        out.append({
            "key": key,
            "label": p["label"],
            "container": p["container"],
            "video": p["video"],
        })
    return _json_response({"available": True, "presets": out})


@app.route("/api/render/<conversation_id>", methods=["POST"])
def render_start(conversation_id):
    if not _HAS_RENDER or _get_render_manager is None:
        return _json_response({"error": "render unavailable"}, status=503)
    if not _HAS_TIMELINE or _get_timeline is None:
        return _json_response({"error": "timeline unavailable"}, status=503)
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)

    body = request.get_json(silent=True) or {}
    preset_key = (body.get("preset") or "standard").strip()

    # Phase 9 wiring — honor the user's configured export directory.
    export_dir = None
    if _HAS_USER_SETTINGS and _user_settings is not None:
        try:
            user_dir = _user_settings.get_setting("export.default_directory")
            if user_dir:
                from pathlib import Path as _Path
                export_dir = _Path(user_dir).expanduser()
        except Exception:
            export_dir = None

    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, body.get("tag", ""),
            )
            timeline = _get_timeline(conversation_id).load()
            library = _get_media_library(conversation_id).list_entries()
            rid = _get_render_manager().start(
                conversation_id, preset_key, timeline, library,
                export_dir=export_dir)
            _render_conversation_lookup[rid] = conversation_id
        except ValueError as e:
            return _json_response({"error": str(e)}, status=400)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)

    state = _get_render_manager().get_state(rid)
    return _json_response({"render_id": rid, "state": state})


@app.route("/api/render/<render_id>/state", methods=["GET"])
def render_state(render_id):
    if not _HAS_RENDER or _get_render_manager is None:
        return _json_response({"error": "render unavailable"}, status=503)
    try:
        return _json_response(_get_render_manager().get_state(render_id))
    except KeyError:
        return _json_response({"error": "unknown render_id"}, status=404)


@app.route("/api/render/<render_id>/cancel", methods=["POST"])
def render_cancel(render_id):
    if not _HAS_RENDER or _get_render_manager is None:
        return _json_response({"error": "render unavailable"}, status=503)
    try:
        _get_render_manager().cancel(render_id)
    except KeyError:
        return _json_response({"error": "unknown render_id"}, status=404)
    return _json_response({"cancelled": render_id})


try:
    from preview import (
        proxy_state as _preview_proxy_state,
        start_proxy_render as _preview_start_proxy_render,
        extract_frame as _preview_extract_frame,
        invalidate_proxy as _preview_invalidate_proxy,
        proxy_path as _preview_proxy_path,
        forget_conversation as _preview_forget_conversation,
    )
    _HAS_PREVIEW = True
except Exception as _e:  # pragma: no cover — defensive
    _preview_proxy_state = None
    _preview_start_proxy_render = None
    _preview_extract_frame = None
    _preview_invalidate_proxy = None
    _preview_proxy_path = None
    _preview_forget_conversation = None
    _HAS_PREVIEW = False
    print(f"[server] preview unavailable: {_e}")


def _conversation_read_guard(conversation_id: str):
    """Reject unsafe/deleted/missing sessions before any read-side factory."""
    cid = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(cid):
        return cid, _json_response({"error": "invalid conversation_id"}, status=400)
    if _is_conversation_deleted(cid):
        return cid, _json_response({"status": "deleted"}, status=410)
    session_dir = os.path.join(str(rp.ORA_HOME), "sessions", cid)
    if os.path.islink(session_dir) or not os.path.isdir(session_dir):
        return cid, _json_response({"error": "conversation not found"}, status=404)
    return cid, None


@contextmanager
def _conversation_read_scope(conversation_id: str):
    """Hold the delete barrier across a read-side factory or cache writer.

    Delete Forever installs its tombstone before waiting for this same lock.
    A read that got here first may finish, after which deletion purges anything
    it created; a read that gets here second observes the tombstone and never
    constructs a timeline/library/preview object after the purge.
    """
    cid = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(cid):
        yield cid, _json_response(
            {"error": "invalid conversation_id"}, status=400,
        )
        return
    with _conversation_lifecycle_lock(cid):
        yield _conversation_read_guard(cid)


# Compatibility name retained for focused preview tests and older callers.
_preview_read_guard = _conversation_read_guard


@app.route("/api/preview/<conversation_id>/state", methods=["GET"])
def preview_state(conversation_id):
    if not _HAS_PREVIEW or _preview_proxy_state is None:
        return _json_response({"available": False}, status=503)
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            st = _preview_proxy_state(conversation_id)
            st["available"] = True
            return _json_response(st)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)


@app.route("/api/preview/<conversation_id>/frame", methods=["GET"])
def preview_frame(conversation_id):
    if not _HAS_PREVIEW or _preview_extract_frame is None:
        return _json_response({"error": "preview unavailable"}, status=503)
    try:
        ms = int(request.args.get("ms", "0"))
    except (TypeError, ValueError):
        ms = 0
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            png_bytes = _preview_extract_frame(conversation_id, ms)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
        return Response(
            png_bytes,
            mimetype="image/png",
            headers={
                "Cache-Control": "no-store",
                "Content-Length": str(len(png_bytes)),
            },
        )


@app.route("/api/preview/<conversation_id>/proxy/start", methods=["POST"])
def preview_proxy_start(conversation_id):
    if not _HAS_PREVIEW or _preview_start_proxy_render is None:
        return _json_response({"error": "preview unavailable"}, status=503)
    conversation_id = (conversation_id or "").strip()
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    session_dir = os.path.join(str(rp.ORA_HOME), "sessions", conversation_id)
    if os.path.islink(session_dir) or not os.path.isdir(session_dir):
        return _json_response({"error": "conversation not found"}, status=404)
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            rid = _preview_start_proxy_render(conversation_id)
        except RuntimeError as e:
            # No clips on the timeline, etc.
            return _json_response({"error": str(e)}, status=400)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
    return _json_response({"render_id": rid})


@app.route("/api/preview/<conversation_id>/proxy/file", methods=["GET"])
def preview_proxy_file(conversation_id):
    if not _HAS_PREVIEW or _preview_proxy_path is None:
        return _json_response({"error": "preview unavailable"}, status=503)
    with _conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        p = _preview_proxy_path(conversation_id)
        if not p.exists() or p.stat().st_size == 0:
            return _json_response({"error": "no proxy"}, status=404)
        # send_file handles HTTP Range requests automatically — required for
        # <video> element seeking.
        from flask import send_file
        return send_file(
            str(p),
            mimetype="video/mp4",
            conditional=True,
            max_age=0,
        )


@app.route("/api/preview/<conversation_id>/invalidate", methods=["POST"])
def preview_invalidate(conversation_id):
    if not _HAS_PREVIEW or _preview_invalidate_proxy is None:
        return _json_response({"error": "preview unavailable"}, status=503)
    conversation_id, error_response = _preview_read_guard(conversation_id)
    if error_response is not None:
        return error_response
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        try:
            _preview_invalidate_proxy(conversation_id)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)
    return _json_response({"invalidated": True})


# /api/render/stream retired 2026-05-01 — render-controls.js polls
# /api/render/<id>/state since 2026-04-30.


# Pending clarification state: {panel_id: {step1, config, history, user_input}}
_pending_clarification = {}

import base64

def _process_attachments(attachments: list) -> tuple:
    """Split attachments into inlined text and image data.

    Returns (text_parts, images) where:
      - text_parts: list of "[Attached: name]\ncontent" strings for text files
      - images: list of {"name": str, "mime": str, "base64": str} for image files
    """
    text_parts = []
    images = []
    for att in (attachments or []):
        name = att.get("name", "file")
        mime = att.get("type", "")
        data_url = att.get("data", "")
        if not data_url:
            continue

        # Strip data URL prefix to get raw base64
        raw_b64 = data_url.split(",", 1)[-1] if "," in data_url else data_url

        if mime.startswith("image/"):
            images.append({"name": name, "mime": mime, "base64": raw_b64})
        else:
            # Text-like file: decode and inline
            try:
                content = base64.b64decode(raw_b64).decode("utf-8", errors="replace")
                text_parts.append(f"[Attached file: {name}]\n{content}")
            except Exception:
                text_parts.append(f"[Attached file: {name} — could not decode]")
    return text_parts, images


def _generate_clarification_questions(step1, config):
    """Use the breadth model to generate clarification questions for Tier 2/3.

    Uses the cleaned prompt, selected mode, and inferred assumptions directly;
    retired domain question-bank modules are not injected.
    """
    tier = step1["triage_tier"]
    cleaned = step1["cleaned_prompt"]
    mode = step1["mode"]
    inferred = step1.get("inferred_items", "")

    system_prompt = "\n".join([
        "You generate clarification questions for a user whose prompt needs "
        "clarification before the AI system can provide a high-quality response.",
        "",
        "Use the user's cleaned prompt, selected analytical mode, and any "
        "inferred assumptions to generate specific, context-grounded questions.",
        "",
        "Output only the numbered questions, nothing else.",
    ])

    if tier == 2:
        instruction = (
            f"The user's prompt has been triaged as Tier 2 (Targeted Clarification). "
            f"The domain is recognizable but the specific need is ambiguous.\n\n"
            f"Cleaned prompt: {cleaned}\n"
            f"Selected mode: {mode}\n"
        )
        if inferred:
            instruction += f"Inferred items (assumptions made): {inferred}\n"
        instruction += (
            f"\nGenerate 2-3 targeted "
            f"clarification questions that would resolve the ambiguity. Each "
            f"question should be specific and answerable in one sentence. "
            f"Format: one question per line, numbered."
        )
    else:  # Tier 3
        instruction = (
            f"The user's prompt has been triaged as Tier 3 (Full Perceptual Broadening). "
            f"The domain boundaries are unclear and the prompt is exploratory.\n\n"
            f"Cleaned prompt: {cleaned}\n"
            f"Selected mode: {mode}\n"
        )
        if inferred:
            instruction += f"Inferred items (assumptions made): {inferred}\n"
        instruction += (
            f"\nGenerate 3-5 broadening "
            f"questions that help the user discover what they're actually trying "
            f"to accomplish. Questions should open up the problem space, not "
            f"narrow it. Format: one question per line, numbered."
        )

    endpoint = get_slot_endpoint(config, "step1_cleanup")
    if not endpoint:
        return ["What specifically are you trying to accomplish?",
                "What would a successful outcome look like?"]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]
    response = call_model(messages, endpoint)

    # Parse numbered questions from response
    questions = []
    for line in response.splitlines():
        line = line.strip()
        if re.match(r'^\d+[\.\)]\s', line):
            questions.append(re.sub(r'^\d+[\.\)]\s*', '', line))
    return questions or ["What specifically are you trying to accomplish?"]


# ── WP-4.4: Text-only fallback UX ─────────────────────────────────────────────
#
# Two upstream signals from the visual routing pipeline (set in
# ``orchestrator/boot.py::route_for_image_input``):
#   * ``context_pkg['no_vision_available'] = True`` — no vision-capable
#     model exists in any bucket; extraction was never attempted.
#   * ``context_pkg['vision_extraction_result'] is None`` with
#     ``context_pkg['vision_extraction_meta']['parse_errors']`` populated —
#     an extractor ran but the response couldn't be parsed.
#
# When either signal fires, ``_pipeline_stream`` emits a structured
# ``visual_fallback`` SSE frame BEFORE any response tokens so the chat-panel
# client can surface a manual-trace prompt alongside the assistant's prose.
# If neither signal is present, no frame is emitted (backward compat).

# Fixed user-facing string for the overlay. i18n out-of-scope for this WP;
# tracked as future polish. Keeping the wording identical between the two
# fallback reasons keeps the UX consistent — the structured metadata lets
# the overlay show additional debugging affordances if we want to later.
_VISUAL_FALLBACK_USER_MESSAGE = (
    "I couldn't extract structure from your image. Please trace the key "
    "elements manually using the shape tools, or queue this for a "
    "vision-capable model when one becomes available."
)

# Fixed button set advertised to the client. Kept as a list rather than a
# free-form action dict so the client can pattern-match without leaking a
# handler surface to the server.
_VISUAL_FALLBACK_ACTIONS = ["start_tracing", "queue_for_later", "dismiss"]


def _build_visual_fallback_frame(context_pkg: dict | None) -> dict | None:
    """Inspect context_pkg for WP-4.4 fallback signals and build the SSE payload.

    Returns a dict suitable for ``_sse('visual_fallback', **frame)`` when
    either fallback condition is set; otherwise returns ``None`` so the
    caller can skip the SSE emission entirely.
    """
    if not isinstance(context_pkg, dict):
        return None

    # Fallback 1 — no vision-capable model exists anywhere.
    if context_pkg.get("no_vision_available") is True:
        return {
            "reason": "no_vision_available",
            "extractor_attempted": None,
            "parse_errors": [],
            "user_message": _VISUAL_FALLBACK_USER_MESSAGE,
            "actions": list(_VISUAL_FALLBACK_ACTIONS),
        }

    # Fallback 2 — a vision model WAS selected but extraction parsing failed.
    # This specifically requires an image_path AND a selected extractor AND
    # a null vision_extraction_result. That combination rules out the
    # backward-compat no-image / success cases.
    has_image = bool(context_pkg.get("image_path"))
    had_extractor = context_pkg.get("vision_extractor_selected") is not None
    result_is_none = context_pkg.get("vision_extraction_result") is None
    # Only consider this a "failure" when the key exists — the gate sets the
    # key explicitly after attempting extraction. Without the key, we're in
    # the pre-extraction branch (vision-capable direct pass, for instance).
    attempted = "vision_extraction_result" in context_pkg

    if has_image and had_extractor and attempted and result_is_none:
        meta = context_pkg.get("vision_extraction_meta") or {}
        parse_errors = meta.get("parse_errors") or []
        if not isinstance(parse_errors, list):
            parse_errors = [str(parse_errors)]
        extractor_name = meta.get("extractor_model")
        if not extractor_name:
            sel = context_pkg.get("vision_extractor_selected") or {}
            extractor_name = sel.get("display_name") or sel.get("id")
        return {
            "reason": "extraction_failed",
            "extractor_attempted": extractor_name,
            "parse_errors": [str(e) for e in parse_errors],
            "user_message": _VISUAL_FALLBACK_USER_MESSAGE,
            "actions": list(_VISUAL_FALLBACK_ACTIONS),
        }

    return None


def _build_visual_diagnostics_frame(context_pkg: dict | None) -> dict | None:
    """Phase 0 — surface ora-visual suppression to the client.

    The visual hook stashes per-visual diagnostics on
    ``context_pkg['visual_diagnostics']``. This turns those into a compact
    SSE payload, but only when at least one envelope was actually suppressed —
    so the pane stays quiet on healthy turns and gets loud (with the reason)
    when a visual silently failed to render. Returns ``None`` when there is
    nothing to report.
    """
    if not isinstance(context_pkg, dict):
        return None
    diag = context_pkg.get("visual_diagnostics") or {}
    visuals = diag.get("visuals") or []
    blocked = [v for v in visuals if v.get("blocked")]
    if not blocked:
        return None

    def _reason(v):
        val = v.get("validator") or {}
        if not val.get("valid", True):
            errs = val.get("errors") or []
            if errs and "parse failed" in (errs[0].get("message", "") or "").lower():
                return "Not valid JSON — the model didn't emit a parseable envelope"
            return "Schema/structural error — the envelope didn't match the visual contract"
        adv = v.get("adversarial") or {}
        if adv.get("blocks"):
            return "Failed an honesty check (Tufte / clarity rule)"
        return "Suppressed"

    def _fmt(items, kfields):
        out = []
        for it in items or []:
            parts = [str(it.get(k, "")).strip() for k in kfields]
            out.append(": ".join(p for p in parts if p))
        return [s for s in out if s][:5]

    return {
        "visuals_seen": len(visuals),
        "visuals_suppressed": len(blocked),
        "mode": context_pkg.get("mode_name"),
        "suppressed": [{
            "id": v.get("id"),
            "type": v.get("type"),
            "reason": _reason(v),
            "validator_errors": _fmt((v.get("validator") or {}).get("errors"), ("code", "message")),
            "adversarial_blocks": _fmt((v.get("adversarial") or {}).get("blocks"), ("rule", "message")),
        } for v in blocked],
    }


@app.route("/api/visual/regenerate", methods=["POST"])
def visual_regenerate():
    """Phase 1 — on-demand envelope synthesis for the visual pane's
    'Regenerate visual' button. Body: ``{prose, mode,
    manual_visual_type?}``; ``visual_kind`` is an alias. Runs the same
    synthesize→validate→repair loop the pipeline uses on a miss, and returns
    a ready-to-render ora-visual block. Returns ``{ok, block?, type?, reason}``.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}
    prose = (data.get("prose") or "").strip()
    mode = data.get("mode") or ""
    preferred_kind = (
        data.get("manual_visual_type") or data.get("visual_kind") or ""
    ).strip() or None
    if not prose:
        return jsonify({"ok": False, "reason": "no prose supplied"}), 400
    try:
        from boot import (_mode_target_types, _resolve_synthesis_endpoint,
                          _strip_visual_blocks_and_markers, call_model)
        from visual_synthesis import synthesize_envelope, SYSTEM_PROMPT
    except Exception as exc:
        return jsonify({"ok": False, "reason": f"synthesis unavailable: {exc}"}), 500
    target_types = _mode_target_types(mode, preferred_kind) or ["concept_map"]
    endpoint = _resolve_synthesis_endpoint()
    if not endpoint:
        return jsonify({"ok": False, "reason": "no synthesis endpoint resolved"}), 503
    clean = _strip_visual_blocks_and_markers(prose)

    def _call_fn(prompt):
        return call_model(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": prompt}],
            endpoint,
        )

    try:
        env, attempts = synthesize_envelope(clean, mode or "unknown", target_types, _call_fn)
    except Exception as exc:
        return jsonify({"ok": False, "reason": f"synthesis error: {exc}"}), 500
    if env is None:
        return jsonify({"ok": False, "reason": f"synthesis failed after {len(attempts)} attempt(s)"})
    block = "```ora-visual\n" + json.dumps(env, indent=2) + "\n```"
    return jsonify({"ok": True, "block": block, "type": env.get("type"), "envelope": env})


# In-memory vision-retry queue keyed by conversation_id. Each entry is a
# dict {image_path, attempt_reason, queued_at}. Also mirrored to disk at
# ``~/ora/sessions/<conversation_id>/vision-retry-queue.json`` so a future
# daemon (or user-triggered "retry queued visions" action) can flush it
# without depending on server process lifetime. No automatic retry here —
# that's future work.
_vision_retry_queue: dict[str, list[dict]] = {}


def _vision_retry_queue_path(conversation_id: str) -> str:
    """Resolve the per-session JSON file path for the retry queue."""
    canonical_id = _canonical_live_conversation_id(conversation_id)
    session_dir = rp.safe_owned_subdir(
        VISUAL_UPLOADS_ROOT, canonical_id, create=False,
    )
    return str(session_dir / "vision-retry-queue.json")


def _load_vision_retry_queue(conversation_id: str) -> list[dict]:
    """Read the persistent queue file; return empty list on miss/error."""
    path = _vision_retry_queue_path(conversation_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"[vision-retry-queue] load failed for {conversation_id}: {e}")
    return []


def _persist_vision_retry_queue(conversation_id: str, entries: list[dict]) -> None:
    """Write the session queue file. Fail-open: error never blocks the response."""
    try:
        canonical_id = _canonical_live_conversation_id(conversation_id)
        path = str(rp.safe_owned_subdir(
            VISUAL_UPLOADS_ROOT, canonical_id, create=True,
        ) / "vision-retry-queue.json")
        with open(path, "w") as fh:
            json.dump(entries, fh, indent=2)
    except Exception as e:
        print(f"[vision-retry-queue] persist failed for {conversation_id}: {e}")


def _make_server_criteria_invoker(config, config_name):
    """Sidebar-slot criteria invoker for the server path (delegates to the
    boot helper). None when no endpoint is available."""
    try:
        from boot import _make_criteria_invoker
        return _make_criteria_invoker(config, config_name)
    except Exception:
        return None


def _run_pipeline_from_step2(step1, config, history, user_input,
                             clarification_text="", images=None,
                             execution_context="interactive",
                             extra_context=None, trace_dir=None,
                             config_name=None, conversation_tag="",
                             turn_state=None):
    """Resume pipeline from Step 2 onward, optionally enriched with clarification answers.

    ``extra_context`` (WP-3.3): an optional dict of extra keys to merge into the
    assembled ``context_pkg`` before the system prompt is built. Used by the
    multipart endpoint to thread ``spatial_representation`` + ``image_path``
    into ``build_system_prompt_for_gear`` without changing the Step 1/2 contract.

    ``trace_dir``: per-turn forensic-trace directory created by
    ``pipeline_trace.start_trace`` in ``_pipeline_stream``. Passed through
    to ``run_step2_context_assembly`` (which records the context package)
    and rides on ``context_pkg`` so ``run_gear3`` / ``run_gear4`` land
    their step-3..8 traces in the same per-turn directory.

    ``config_name`` (install Chunk 2c): selects a named configuration from
    config/configurations/ for the analysis stages. None falls through to
    the legacy execution_context path.
    """
    # If clarification was provided, enrich the cleaned prompt and — if the
    # pause was at Stage 2 or Stage 3 of the pre-routing pipeline — re-run
    # the routing pipeline so the user's answer can resolve the disambiguation
    # or supply the missing input.
    if clarification_text:
        step1 = dict(step1)  # Don't mutate original
        step1["cleaned_prompt"] = (
            f"{step1['cleaned_prompt']}\n\n"
            f"[User clarification]\n{clarification_text}"
        )
        step1["operational_notation"] = step1["cleaned_prompt"]

        # Phase 9 — re-run the four-stage pipeline with the answer baked in
        prior_pre_routing = step1.get("pre_routing", {}) or {}
        pause_stage = prior_pre_routing.get("pending_clarification_stage")
        if pause_stage in ("stage2", "stage3"):
            try:
                from boot import run_pre_routing_pipeline
                routing = run_pre_routing_pipeline(
                    prompt=step1["operational_notation"],
                    context=None,
                )
                if routing.get("dispatched_mode_id"):
                    step1["mode"] = routing["dispatched_mode_id"]
                    step1["triage_tier"] = 2  # default-on-ambiguity Tier-2
                    step1["pre_routing"] = {
                        "dispatched_mode_id": routing["dispatched_mode_id"],
                        "territory": routing.get("territory"),
                        "bypass_to_direct_response": False,
                        "pending_clarification": routing.get("pending_clarification"),
                        "pending_clarification_stage": routing.get("pending_clarification_stage"),
                        "completeness_gaps": routing.get("completeness_gaps", []),
                        "dispatch_announcement": routing.get("dispatch_announcement"),
                        "lighter_sibling_mode_id": routing.get("lighter_sibling_mode_id"),
                        "confidence": routing.get("confidence", "medium"),
                    }
            except Exception as exc:
                print(f"[pre-routing] resume re-route failed: {exc}")

    try:
        try:
            import tool_events as _te_context
        except ImportError:
            from orchestrator import tool_events as _te_context
        _context_conversation_id = (
            (_te_context.get_turn_context() or {}).get("conversation_id")
        )
    except Exception:
        _context_conversation_id = None
    _context_exclusions = _boot_context_api()._context_source_exclusions(
        _context_conversation_id,
        history,
        (extra_context or {}).get("contributor_bundle"),
    )
    context_pkg = run_step2_context_assembly(
        step1, config, trace_dir=trace_dir,
        config_name=config_name,
        conversation_tag=conversation_tag,
        include_persona=True,
        retrieval_exclusions=_context_exclusions,
    )
    # WP-3.3: thread merged-input extras (spatial_representation, image_path,
    # …) into the context package for build_system_prompt_for_gear.
    if extra_context:
        for k, v in extra_context.items():
            if v is not None:
                context_pkg[k] = v
    _boot_context_api()._finalize_optional_context_package(
        context_pkg,
        conversation_id=_context_conversation_id,
        history=history,
    )
    # Ensure trace_dir is on context_pkg so run_gear3/run_gear4 land their
    # step-3..8 traces in the same per-turn directory. run_step2_context_assembly
    # already does this when given a trace_dir, but make it idempotent.
    if trace_dir and not context_pkg.get("trace_dir"):
        context_pkg["trace_dir"] = trace_dir
    # Carry the execution context so the visual hook's recovery/synthesis gate
    # (interactive vs autonomous/agent) reads a real value instead of always
    # defaulting to 'interactive'.
    context_pkg.setdefault("execution_context", execution_context)

    # WP-4.2: capability-conditional vision routing gate. If image_path is
    # present and the downstream model is text-only, select a vision-capable
    # extractor (fallback cascade); if nothing is available anywhere, flag
    # no_vision_available for WP-4.4 UX. No-op when there's no image.
    try:
        from boot import route_for_image_input
        route_for_image_input(context_pkg, requested_model=None,
                              execution_context=execution_context)
    except Exception as exc:
        print(f"[visual-routing] gate skipped due to error: {exc}")

    # WP-4.4: emit visual_fallback SSE frame BEFORE the first model token if
    # the routing/extraction pipeline signalled either "no vision model
    # anywhere" or "extraction was attempted and failed to parse". The client
    # chat-panel routes this to the visual panel's showFallbackPrompt() which
    # renders an overlay with Start tracing / Queue for later / Dismiss.
    fallback_frame = _build_visual_fallback_frame(context_pkg)
    if fallback_frame is not None:
        yield _sse("visual_fallback", **fallback_frame)

    gear = context_pkg["gear"]
    if turn_state is not None:
        # Authoritative gear for the trace manifest. Gear 1/2 turns never
        # write step-health.json, so without this explicit signal a
        # completed gear-1/2 turn is indistinguishable on disk from a
        # gear-3/4 turn abandoned after step 2.
        turn_state["gear"] = gear

    # --- Execution Review Phase 2: assign risk tier + pre-executor hold ----
    # This funnel is the single entry for every pipeline executor path
    # (direct dispatch + all clarification resumes), so the irreversible-tier
    # hold sits here, reading the tier as data (not the ContextVar, which was
    # seeded upstream). Enrichment recheck: clarification answers were folded
    # into cleaned_prompt above, so re-run Stage A over the enriched prompt.
    # All fail-safe. ``_risk_warn`` surfaces a criteria-pass warning below.
    _risk_warn = ""
    _route_turn_ts = None
    try:
        import risk_gate as _rgate
        import tool_events as _te_srv
        _route_turn_ts = _rgate.now_ts()
        context_pkg["_route_turn_ts"] = _route_turn_ts
        _conv_id = (_te_srv.get_turn_context() or {}).get("conversation_id")
        _enriched = context_pkg.get("cleaned_prompt", user_input)
        _override = (extra_context or {}).get("risk_override")
        _r = _rgate.assign_tier(
            _enriched, _conv_id, mode_text=context_pkg.get("mode_text"),
            is_trivial_text=(gear <= 2), override=_override, surface="chat")
        _tier = _rgate.tier_max(_r["risk_tier"],
                                step1.get("risk_tier") or "")
        context_pkg["risk_tier"] = _tier
        # Hold FIRST (evaluate_hold never raises + fails closed) so no
        # exception in a later step can leak an irreversible task past it.
        _hold_reply, _ = _rgate.evaluate_hold(
            _tier, conversation_id=_conv_id, prompt=_enriched, surface="chat",
            mode_id=context_pkg.get("mode_name", ""),
            output_target=(extra_context or {}).get("output_target", ""),
            config_name=config_name or "", stealth=(conversation_tag == "stealth"),
            description=_enriched)
        if _hold_reply is not None:
            _rgate.record_route_observed(
                trace_dir or (_conv_id, _route_turn_ts), risk_tier=_tier)
            if turn_state is not None:
                # The turn terminated at an intentional risk hold, not an
                # abandoned pipeline run (design-gate condition 1).
                turn_state["kind"] = "risk_hold"
            yield _sse("response", text=_hold_reply)
            return
        _te_srv.update_turn_risk_tier(_tier)
        _crit = _rgate.apply_criteria(
            context_pkg, _enriched, _tier,
            invoker=_make_server_criteria_invoker(config, config_name))
        if _crit and _crit.startswith("HOLD:"):
            _hr, _ = _rgate.evaluate_hold(
                "irreversible", conversation_id=_conv_id, prompt=_enriched,
                surface="chat", mode_id=context_pkg.get("mode_name", ""),
                config_name=config_name or "",
                stealth=(conversation_tag == "stealth"), description=_crit[5:])
            if _hr is not None:
                if turn_state is not None:
                    turn_state["kind"] = "risk_hold"
                yield _sse("response", text=_hr)
                return
        elif _crit and _crit.startswith("WARN:"):
            _risk_warn = _crit[5:]
        # Execution Review Phase 5: the Evidence Contract (planning-stage sibling
        # to apply_criteria, spec §15/§16-2), produced IN THE LIVE PLANNING PATH
        # (standard+). Writes context_pkg['evidence_contract'] + records a
        # tool-event. Additive + never-raises (response text unchanged; the Phase-6
        # loop acts on the directive).
        try:
            from evidence_runner import apply_evidence_contract as _aec
        except ImportError:  # pragma: no cover
            from orchestrator.evidence_runner import apply_evidence_contract as _aec
        _aec(context_pkg, _enriched, _tier,
             invoker=_make_server_criteria_invoker(config, config_name))
        # Execution Review Phase 6: PLANNING-STAGE pre-execution state seam (⚖ Rev-1
        # judge P0) — the server twin of run_pipeline's. Capture the TRUE pre-execution
        # git state BEFORE the gear runs (a terminal-time read would be POST-execution).
        # TIER-INDEPENDENT (⚖ Rev-2 P2). Additive + never-raises; only when the loop is
        # enabled + non-stealth (flag OFF → zero new runtime behaviour).
        try:
            import execution_loop as _el6
        except ImportError:  # pragma: no cover
            from orchestrator import execution_loop as _el6
        if conversation_tag != "stealth" and _el6.loop_enabled():
            _el6.snapshot_pre_execution(context_pkg)
    except Exception as _rge_srv:
        print(f"[risk-gate] server tier/hold skipped: {_rge_srv}")

    yield _sse("pipeline_stage", stage="step2_done", gear=gear,
               label=f"Gear {gear} selected")

    # --- Resilience check: degradation path (Phase 14) ---
    degradation_signal = ""
    if RESILIENCE_AVAILABLE and gear >= 3:
        deg_state = get_degradation_path(gear, config)
        if deg_state.fallback_gear:
            gear = deg_state.fallback_gear
            context_pkg["gear"] = gear
            if turn_state is not None:
                turn_state["gear"] = gear
        degradation_signal = format_degradation_signal(deg_state)
        if degradation_signal:
            yield _sse("pipeline_stage", stage="degradation",
                        gear=gear, label=f"Degradation: level {deg_state.degradation_level}")

    # Capture the exact mode contract after runtime gear degradation has been
    # resolved. The mode text is already in this turn's context package, so
    # this never reloads a potentially edited mode file.
    if trace_dir:
        try:
            try:
                from trace_debug import mode_contract_snapshot, record_contract_snapshot
            except ImportError:
                from orchestrator.trace_debug import mode_contract_snapshot, record_contract_snapshot
            record_contract_snapshot(
                trace_dir,
                mode_contract_snapshot(
                    context_pkg.get("mode_name") or step1.get("mode") or "",
                    context_pkg.get("mode_text") or "",
                    gear,
                ),
            )
        except Exception:
            pass

    # Phase 9 — emit dispatch announcement at Stage 4 entry per Decision E.
    # _run_pipeline_from_step2 is the resume path after clarification, so the
    # announcement fires here for the resumed flow as well as the direct flow.
    announcement = (context_pkg.get("dispatch_announcement")
                    or step1.get("pre_routing", {}).get("dispatch_announcement"))
    if announcement:
        yield _sse("dispatch_announcement",
                   text=announcement,
                   mode=context_pkg.get("mode_name") or step1.get("mode"),
                   territory=context_pkg.get("territory"))

    # --- Gear Execution ---
    yield _sse("pipeline_stage", stage="gear_execution",
               gear=gear, label=f"Running Gear {gear} pipeline…")

    # Diagnostic trace
    print(f"[pipeline-dispatch] mode={step1.get('mode')} gear={gear}", flush=True)

    endpoint = get_endpoint(config)

    if gear <= 2:
        system_prompt = _single_pass_system_prompt(context_pkg, gear)
        ep, fast_slot = resolve_single_pass_endpoint(
            config, gear, config_name=config_name)
        if ep is None:
            terminal_value = "No active endpoint configured."
            if turn_state is not None:
                turn_state["status"] = "error"
            if trace_dir:
                try:
                    from orchestrator import pipeline_trace as _pt_no_endpoint
                    _pt_no_endpoint.write_step(
                        trace_dir, "step3-direct-no-endpoint", {
                            "gear": gear, "endpoint_available": False,
                        })
                    _pt_no_endpoint.record_terminal_output(
                        trace_dir, terminal_value,
                        route="server-pipeline-error",
                        output_target="screen", persisted=False,
                    )
                except Exception:
                    pass
            yield _sse("error", text=terminal_value)
            return
        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": context_pkg["cleaned_prompt"]})
        response = run_single_pass_with_tools(
            messages, ep,
            slot=fast_slot,
            gear=gear,
            config_name=config_name,
            images=images,
            step_name="step3-direct-response",
            history=history,
            context_pkg=context_pkg,
        )
        if trace_dir:
            try:
                from orchestrator import pipeline_trace as _pt_direct
                _pt_direct.write_step(trace_dir, "step3-direct-response", {
                    "gear": gear,
                    "raw_response": response,
                    "endpoint": (
                        ep.get("name") if isinstance(ep, dict) else str(ep)
                    ),
                })
            except Exception:
                pass

    elif gear == 3:
        response = run_gear3(context_pkg, config, history, images=images, config_name=config_name)

    elif gear >= 4:
        # KV cache release check for sequential fallback
        if RESILIENCE_AVAILABLE and should_release_kv_cache(config):
            depth_model = config.get("slot_assignments", {}).get("depth", "")
            if depth_model:
                release_kv_cache(depth_model)
        response = run_gear4(context_pkg, config, history, images=images,
                             execution_context=execution_context,
                             config_name=config_name)

    else:
        _persona_resolution = context_pkg.get("persona_resolution")
        response = _run_model_with_tools(
            [{"role": "system", "content": load_boot_md(
                include_persona=bool(_persona_resolution),
                persona_resolution=_persona_resolution,
            )},
             {"role": "user", "content": user_input}],
            endpoint, images=images
        )

    effective_trace_gear = context_pkg.get("_trace_effective_gear")
    if isinstance(effective_trace_gear, int):
        gear = effective_trace_gear
        if turn_state is not None:
            turn_state["gear"] = effective_trace_gear

    # Prepend degradation signal if any (never silent)
    if degradation_signal:
        response = f"{degradation_signal}\n\n---\n\n{response}"

    # Execution Review Phase 2: surface a criteria-pass warning (condition 6).
    if _risk_warn:
        response = f"⚠️ {_risk_warn}\n\n---\n\n{response}"

    # Server-side visual hook (parity with run_pipeline's tail-of-function
    # invocation). Without this, model-emitted ora-visual blocks with schema
    # violations or critical Tufte / adversarial findings flowed through to
    # the browser unchecked because the server's pipeline path bypassed
    # ``_run_visual_hook``. Identical signature / behaviour to the CLI path.
    try:
        from boot import _run_visual_hook as _server_run_visual_hook
        response = _server_run_visual_hook(response, context_pkg)
    except Exception as _vh_exc:
        # Fail-open: never block legitimate prose on a hook bug.
        print(f"[server visual-hook] skipped due to error: {_vh_exc}")

    if turn_state is not None:
        # Explicit completion signal for the trace manifest — the only
        # honest source for gear-1/2 turns, which write no step-health. A
        # later exception on the way out overwrites this with "error" in
        # the generator-level wrapper.
        if trace_dir:
            try:
                try:
                    from trace_debug import refresh_mode_contract_snapshot
                except ImportError:
                    from orchestrator.trace_debug import refresh_mode_contract_snapshot
                refresh_mode_contract_snapshot(
                    trace_dir,
                    context_pkg.get("mode_name") or step1.get("mode") or "",
                    context_pkg.get("mode_text") or "",
                    gear,
                )
            except Exception:
                pass
        turn_state["status"] = (
            context_pkg.get("_trace_terminal_status") or "completed"
        )
    yield _sse(
        "pipeline_stage", stage="complete", gear=gear,
        mode=step1["mode"], label="Pipeline complete",
        context_coverage=context_pkg.get("context_coverage") or {},
    )
    yield _sse("response", text=response)

    # Execution Review Phase 2: after-clock — record route_observed on this
    # terminal path (condition 7). Best-effort, never raises.
    try:
        _ro = _rgate.record_route_observed(
            trace_dir or ((_te_srv.get_turn_context() or {}).get("conversation_id"),
                          context_pkg.get("_route_turn_ts") or ""),
            risk_tier=context_pkg.get("risk_tier"),
            output_text=response,  # Phase 3: drives the source-read signal
            declared_output_type=context_pkg.get("output_type", "unknown"))
        # Execution Review Phase 4/6: build the ExecutionPacket from the already-folded
        # signals (single fold; no packet ref on route_observed). Self-evidencing turn
        # (or loop disabled) → the Phase-4 trace-local record, byte-identical. Non-self-
        # evidencing turn with the loop enabled → the Phase-6 Capture→verify→stop/
        # escalate loop (records the packet + escalates). The response was already
        # streamed on this path, so a revised deliverable cannot replace it; with
        # actuator=None (first landing) the loop never revises anyway, so the return is
        # ignored. Guarded to non-stealth. Never raises.
        if conversation_tag != "stealth":
            try:
                from boot import _execution_review_terminal as _ert
            except ImportError:  # pragma: no cover
                from orchestrator.boot import _execution_review_terminal as _ert
            _ert(_ro, response, context_pkg, trace_dir,
                 conversation_tag == "stealth", config, config_name)
    except Exception:
        pass

    # Phase 0 — make suppressed visuals loud + actionable. The hook above
    # stashed per-visual diagnostics on context_pkg; surface the reason so the
    # pane can explain why a visual didn't render instead of leaving only the
    # bare inline "[visual … suppressed]" marker in the prose. Emitted only
    # when something was actually suppressed; fail-open.
    try:
        _vdiag_frame = _build_visual_diagnostics_frame(context_pkg)
        if _vdiag_frame:
            yield _sse("visual_diagnostics", **_vdiag_frame)
    except Exception as _vd_exc:
        print(f"[server visual-diagnostics] skipped: {_vd_exc}")


def _pipeline_stream(user_input, history, panel_id="main", images=None, extra_context=None,
                       manual_mode_selection="", manual_lens_selection="",
                       framework_selected="", config_name=None, conversation_tag=""):
    """Generator: run the full pipeline with SSE stage events.

    Trace-manifest wrapper (Chunk 0). The turn body lives in
    ``_pipeline_stream_impl``; this wrapper owns the single generator-level
    ``try/finally`` that finalizes the turn's ``trace-manifest.json`` on
    every exit path — normal return, caught-error-and-return, uncaught
    exception, and ``GeneratorExit`` (client disconnect). ``turn_state`` is
    the branch-local kind/status channel: the impl assigns
    ``turn_state["kind"]`` one line at each branch entry and
    ``turn_state["status"]`` on caught-error and pause exits; the finalizer
    here is the only writer of the manifest's terminal fields.
    """
    turn_state = {
        "trace_dir": None,   # set by impl right after start_trace
        "kind": "unknown",   # honest default — a turn that dies pre-branch
        "status": None,      # status hint: "error" | "paused" | "completed"
        "mode": None,        # step1's mode once known
        "gear": None,        # set at gear dispatch in _run_pipeline_from_step2
        "parent_ref": None,  # paused-turn ref on clarification continuation
        "framework_id": None,
        "milestone_id": None,
        "child_refs": [],
    }
    # Scope every invocation, including tests and future direct callers that
    # bypass ``agentic_loop_stream``.  The implementation intentionally sets
    # several per-turn contexts as the trace and risk tier become known; these
    # outer tokens restore the worker thread exactly on normal return, error,
    # and GeneratorExit instead of letting a Stealth/private tag or trace sink
    # bleed into the next request served by the same thread.
    turn_tag = _effective_conversation_tag(panel_id, conversation_tag)
    boot_context = _boot_context_api()
    tag_token = boot_context.set_conversation_tag_context(turn_tag)
    trace_token = boot_context.set_turn_trace_context(None)
    scope = nullcontext()
    try:
        try:
            from orchestrator.oversight_events import lifecycle_context_scope
            scope = lifecycle_context_scope(
                stealth=turn_tag == "stealth",
                conversation_id=panel_id,
                tool_context={
                    "trace_dir": None,
                    "surface": "chat",
                    "risk_tier": None,
                },
            )
        except Exception as exc:
            # Fail open loudly. The implementation's legacy setters still
            # seed the live turn, but restoration/correlation may be degraded.
            print(
                f"[conversation-lifecycle] pipeline context scope unavailable "
                f"for {panel_id}: {exc}", file=sys.stderr, flush=True,
            )
        with scope:
            try:
                yield from _pipeline_stream_impl(
                    user_input, history, panel_id=panel_id, images=images,
                    extra_context=extra_context,
                    manual_mode_selection=manual_mode_selection,
                    manual_lens_selection=manual_lens_selection,
                    framework_selected=framework_selected,
                    config_name=config_name,
                    conversation_tag=turn_tag, turn_state=turn_state)
            except GeneratorExit:
                # Client disconnect — not an error. The finalizer derives
                # completed (step-health present / completed hint) vs abandoned.
                raise
            except BaseException:
                turn_state["status"] = "error"
                raise
            finally:
                try:
                    from orchestrator import pipeline_trace as _pt_fin
                    _pt_fin.finalize_manifest(
                        turn_state["trace_dir"], kind=turn_state["kind"],
                        status_hint=turn_state["status"], mode=turn_state["mode"],
                        gear=turn_state["gear"],
                        parent_trace_ref=turn_state["parent_ref"],
                        framework_id=turn_state["framework_id"],
                        milestone_id=turn_state["milestone_id"],
                        child_trace_refs=turn_state["child_refs"])
                except Exception as _fin_exc:
                    print(f"[server trace] manifest finalize skipped: {_fin_exc}",
                          flush=True)
    finally:
        boot_context.reset_turn_trace_context(trace_token)
        boot_context.reset_conversation_tag_context(tag_token)


def _pipeline_stream_impl(user_input, history, panel_id="main", images=None, extra_context=None,
                            manual_mode_selection="", manual_lens_selection="",
                            framework_selected="", config_name=None, conversation_tag="",
                            turn_state=None):
    """Generator: run the full pipeline with SSE stage events.

    Yields SSE events for each pipeline stage so the browser can display progress.
    For Tier 2/3 triage, pauses for clarification before proceeding.

    ``extra_context`` (WP-3.3): optional dict threaded into the pipeline's
    context package by the multipart endpoint.

    V3 Input Handling Phase 1: after Step 1, run ``compare_intent_with_mode``
    and surface the result in the ``step1_done`` SSE event. The actual
    prefilter popup gating (pause/resume) is owned by Phase 6; for Phase 1
    the pipeline continues regardless. The UI consumes the comparison data
    once Phase 3-6 land.
    """
    if turn_state is None:
        # Direct invocation (tests, future callers) — still track locally so
        # the branch assignments below never need a guard.
        turn_state = {"trace_dir": None, "kind": "unknown", "status": None,
                      "mode": None, "gear": None, "parent_ref": None}
    manual_mode_selection = (manual_mode_selection or "").strip()
    manual_lens_selection = (manual_lens_selection or "").strip()
    framework_selected = (framework_selected or "").strip()
    if manual_lens_selection and not _lens_available_for_mode(
        manual_mode_selection, manual_lens_selection,
    ):
        print(
            f"[manual-lens-selection] ignored unavailable lens "
            f"'{manual_lens_selection}' for mode "
            f"'{manual_mode_selection or '(none)'}'",
            flush=True,
        )
        manual_lens_selection = ""
    if manual_lens_selection:
        extra_context = dict(extra_context or {})
        extra_context["selected_lens_id"] = manual_lens_selection

    # --- Stealth context + forensic trace setup (TURN HEAD) ---
    # Must run before any short-circuit so the stealth thread-local is set
    # and the trace dir opened (or suppressed) for every code path the
    # turn can take. The four short-circuits below (runtime command /
    # resolution chain / framework elicitation / framework slash-command)
    # all emit oversight events downstream (milestone_executor in
    # particular) whose payloads carry ``user_input``. Without the
    # thread-local set here, those events land in
    # ~/ora/data/oversight/events.jsonl with stealth prompt text — a
    # privacy leak that survives ``conversation_closeout._purge_stealth``
    # only via Layer 7's defence-in-depth scrub. Order matters: this is
    # the *only* layer that prevents the write in the first place.
    # Resolve once at turn head and use the canonical value everywhere below.
    # For a first-turn Stealth conversation there is no envelope yet, so the
    # creation-tag registry is the only way to suppress traces before save.
    conversation_tag = _effective_conversation_tag(panel_id, conversation_tag)
    _conv_tag = conversation_tag
    trace_dir = None
    trace_ref_val = None
    try:
        from boot import PIPELINE_TRACE_AVAILABLE as _pta
        if _pta:
            from orchestrator import pipeline_trace as _pt
            trace_dir = _pt.start_trace(
                conversation_id=panel_id,
                raw_input=user_input,
                ambiguity_mode="assume",
                stealth=(_conv_tag == "stealth"),
                conversation_tag=_conv_tag,
            )
            trace_ref_val = _pt.trace_ref_for_dir(trace_dir)
    except Exception as _trace_exc:
        print(f"[server trace] start_trace skipped: {_trace_exc}", flush=True)
    turn_state["trace_dir"] = trace_dir
    # The wrapper owns restoration; this update makes the newly opened trace
    # available to boot helpers and any copied worker context for this turn.
    _boot_context_api().set_turn_trace_context(trace_dir)

    # Non-inferential trace_ref channel (design-gate condition 3): the
    # generator owns trace_dir, but the conversation savers live in
    # _invoke_pipeline, outside this generator. A dedicated event carries
    # the ref in-band; _invoke_pipeline captures it and threads it through
    # _save_conversation / _persist_turn_spatial_state. Stealth turns have
    # no trace, emit no event, and save trace_ref: null by construction.
    if trace_ref_val:
        yield _sse("trace_ref", ref=trace_ref_val)

    # Set the thread-local stealth context so oversight events emitted
    # during this turn skip on-disk persistence (events.jsonl / actions.jsonl
    # / human-queue.jsonl). In-process handlers still fire so runtime
    # behaviour (fan-out, PROCEED/REVISE/ESCALATE) is unchanged.
    #
    # Also stamp the conversation_id thread-local so every event emitted
    # during the turn carries a conversation_id — that is the key
    # _purge_stealth Layer 9 uses to scrub records from the three
    # oversight logs if the primary skip-the-write defence above is ever
    # bypassed.
    try:
        from orchestrator.oversight_events import (
            set_stealth_context as _set_stealth,
            set_conversation_id_context as _set_cid,
        )
        _set_stealth(_conv_tag == "stealth")
        _set_cid(panel_id)
    except Exception:
        pass

    # Conversation-tag context for mind.md user adaptation: its
    # "## Private Context" section is injected only when this turn's
    # conversation is tagged private/stealth (load_boot_md gates on it;
    # propagates into Gear-4 workers via _submit_with_context). Set every
    # turn — including to "" — so a thread reused across requests never
    # carries a stale private flag.
    try:
        _boot_context_api().set_conversation_tag_context(_conv_tag)
    except Exception:
        pass

    # --- Execution Review Phase 2: risk gate (before-clock), turn head ---
    # Before any slash dispatch (condition 5): a bare `/risk <tier>` sets the
    # conversation sticky; a "1"/"2" reply to a prior irreversible hold
    # approves/cancels it; an inline `/risk <tier> <task>` override is lifted
    # off the input and threaded to the executor funnel via extra_context.
    try:
        import risk_gate as _rgate_srv
        _sticky_reply = _rgate_srv.handle_risk_command(user_input, panel_id)
        if _sticky_reply is not None:
            turn_state["kind"] = "risk_hold"
            yield _sse("response", text=_sticky_reply)
            return
        _tg_marker = _rgate_srv.is_task_gate_continuation(history or [])
        if _tg_marker is not None:
            _tg_reply = _rgate_srv.handle_task_gate_reply(
                _tg_marker, user_input, panel_id,
                principal_id="principal:user",
            )
            if _tg_reply is not None:
                turn_state["kind"] = "risk_hold"
                yield _sse("response", text=_tg_reply)
                return
        _clean_ui, _risk_ovr = _rgate_srv.strip_risk_prefix(user_input)
        if _risk_ovr is not None:
            user_input = _clean_ui
            extra_context = dict(extra_context or {})
            extra_context["risk_override"] = _risk_ovr
    except Exception as _rge_head:
        print(f"[risk-gate] server turn-head skipped: {_rge_head}")

    # --- Trace-backed P-Debug structured route ---
    _trace_debug_payload = (extra_context or {}).get("trace_debug") if isinstance(extra_context, dict) else None
    try:
        try:
            import trace_debug as _tdbg
        except ImportError:
            from orchestrator import trace_debug as _tdbg
        if not isinstance(_trace_debug_payload, dict):
            _trace_debug_payload = _tdbg.parse_natural_language_request(user_input)
    except Exception:
        _tdbg = None
    if isinstance(_trace_debug_payload, dict):
        turn_state["kind"] = "trace-debug"
        try:
            if _tdbg is None:
                try:
                    import trace_debug as _tdbg
                except ImportError:
                    from orchestrator import trace_debug as _tdbg
            _debug_prompt, _debug_meta = _tdbg.build_debug_prompt(
                _trace_debug_payload, conversation_id=panel_id)
            if trace_dir:
                try:
                    import pipeline_trace as _pt_dbg
                except ImportError:
                    from orchestrator import pipeline_trace as _pt_dbg
                _pt_dbg.update_manifest_fields(
                    trace_dir, trace_kind="trace-debug",
                    investigates_trace_ref=_trace_debug_payload.get("trace_ref"))
                _pt_dbg.write_step(
                    trace_dir,
                    "step-debug-request",
                    {k: _trace_debug_payload.get(k) for k in
                     ("trace_ref", "step_hint", "symptom", "source")},
                )
            if not _debug_prompt:
                turn_state["status"] = "error"
                if trace_dir:
                    _pt_dbg.write_step(
                        trace_dir, "step-debug-result",
                        {"status": "error", "error": (_debug_meta or {}).get("error") or "unknown"},
                    )
                yield _sse("error", text="Trace debug error: " + str((_debug_meta or {}).get("error") or "unknown"))
                return
            config = load_config()
            endpoint = get_endpoint(config)
            if endpoint is None:
                turn_state["status"] = "error"
                yield _sse("error", text="No AI endpoints configured. Add a connection or install a local model.")
                return
            yield _sse("pipeline_stage", stage="trace_debug", label="Investigating trace via P-Debug...")
            from milestone_executor import run_framework_command
            _trace_ctx = {"conversation_tag": _conv_tag}
            result_text = run_framework_command(
                _tdbg.build_framework_command(_debug_prompt, config_name=config_name),
                config, trace_dir=trace_dir, conversation_tag=_conv_tag,
                trace_context=_trace_ctx,
                project_nexus=_framework_project_nexus(extra_context),
                one_run_profile=config_name,
                style_context=extra_context)
            try:
                _tdbg.record_diagnosis_learning(panel_id, _trace_debug_payload.get("trace_ref"), result_text, stealth=(_conv_tag == "stealth"))
            except Exception:
                pass
            turn_state["status"] = _trace_ctx.get("status") or "completed"
            turn_state["framework_id"] = _trace_ctx.get("framework_id")
            turn_state["mode"] = _trace_ctx.get("mode") or turn_state["mode"]
            turn_state["child_refs"] = list(_trace_ctx.get("child_trace_refs") or [])
            if trace_dir:
                _pt_dbg.write_step(
                    trace_dir, "step-debug-result",
                    {"status": turn_state["status"], "child_trace_refs": turn_state["child_refs"]},
                )
            yield _sse("response", text=result_text)
            return
        except Exception as exc:
            turn_state["status"] = "error"
            if trace_dir:
                try:
                    _pt_dbg.write_step(
                        trace_dir, "step-debug-result",
                        {"status": "error", "error": str(exc)},
                    )
                except Exception:
                    pass
            yield _sse("error", text=f"Trace debug framework error: {exc}")
            return

    # --- Runtime slash-command short-circuit ---
    # /instance, /validate, /render, /queue, /approve, /deny — mechanical
    # meta-layer runtime operations that don't need a model endpoint or
    # the analytical pipeline. Handled before the endpoint check so the
    # user can still manage the human queue and run corpus operations even
    # when no AI endpoint is configured.
    from slash_commands import is_runtime_command, run_runtime_command
    if is_runtime_command(user_input):
        turn_state["kind"] = "runtime_command"
        yield _sse("pipeline_stage", stage="runtime_command",
                   label="Running runtime command…")
        try:
            yield _sse(
                "response",
                text=run_runtime_command(
                    user_input,
                    conversation_id=panel_id if panel_id != "main" else "",
                    principal_id="principal:user",
                ),
            )
        except Exception as exc:
            turn_state["status"] = "error"
            yield _sse("error", text=f"Runtime command error: {exc}")
        return

    config = load_config()
    endpoint = get_endpoint(config)

    if endpoint is None:
        turn_state["kind"] = "no_endpoint_error"
        turn_state["status"] = "error"
        terminal_value = (
            "No AI endpoints configured. Add a connection or install a local model."
        )
        if trace_dir:
            try:
                from orchestrator import pipeline_trace as _pt_no_endpoint
                _pt_no_endpoint.write_step(
                    trace_dir, "step3-direct-no-endpoint", {
                        "endpoint_available": False,
                        "entry": "server-pipeline",
                    })
                _pt_no_endpoint.record_terminal_output(
                    trace_dir, terminal_value,
                    route="server-pipeline-error",
                    output_target="screen", persisted=False,
                )
            except Exception:
                pass
        yield _sse("error", text=terminal_value)
        return

    # --- Resolution-chain continuation short-circuit ---
    # If the most recent assistant message carries a resolution marker,
    # the user is mid-discussion to resolve a paused queue entry. Numeric
    # input (1/2/3) commits an action; anything else continues the
    # discussion. Same conversation-as-state design as elicitation.
    import resolution_chain
    resolution_ctx = resolution_chain.is_resolution_continuation(history or [])
    if resolution_ctx is not None:
        turn_state["kind"] = "resolution_continuation"
        yield _sse("pipeline_stage", stage="resolution_continuation",
                   label="Continuing resolution discussion…")
        try:
            text = resolution_chain.continue_resolution(
                resolution_ctx, history or [], user_input,
                conversation_id=panel_id if panel_id != "main" else "",
                config=config,
                principal_id="principal:user",
            )
        except Exception as exc:
            turn_state["status"] = "error"
            yield _sse("error", text=f"Resolution discussion error: {exc}")
            return
        yield _sse("response", text=text)
        return

    # --- Mid-framework continuation short-circuit ---
    # If the most recent assistant message in history carries a marker, the
    # user's reply is part of an in-progress interactive framework execution.
    # Route to the elicitation handler, which makes a small-model call to
    # extract elicited state from the conversation, then asks the next
    # question or produces the final deliverable. Conversation IS the state;
    # there is no separate persistence layer.
    import framework_elicitation
    continuation_ctx = framework_elicitation.is_continuation(history or [])
    if continuation_ctx is not None:
        turn_state["kind"] = "framework_elicitation"
        yield _sse("pipeline_stage", stage="framework_elicitation",
                   label=f"Continuing {continuation_ctx.framework_id} / {continuation_ctx.mode}…")
        try:
            text = framework_elicitation.continue_elicitation(
                continuation_ctx, history or [], config,
                latest_user_text=user_input,
                conversation_id=panel_id,
                current_project_nexus=_framework_project_nexus(extra_context),
                style_context=extra_context,
            )
        except Exception as exc:
            turn_state["status"] = "error"
            yield _sse("error", text=f"Framework elicitation error: {exc}")
            return
        yield _sse("response", text=text)
        return

    # --- Manual analysis-mode clarification continuation ---
    # V3 submits are plain JSON, not a live clarification panel. When a
    # user explicitly picks an analysis and Stage 3 needs missing input,
    # the previous turn saves the completeness question as the assistant
    # reply and records the selected-mode state here. Treat the next user
    # message in the same thread as the answer, append it to the original
    # prompt, and run the already-selected mode instead of reclassifying.
    manual_pending = _pending_clarification.get(panel_id)
    if manual_pending and manual_pending.get("source") == "manual_mode_selection":
        pending = _pending_clarification.pop(panel_id)
        turn_state["kind"] = "clarification_resume"
        turn_state["mode"] = (pending.get("step1") or {}).get("mode")
        # Lineage (design-gate condition 4): the paused turn stored its own
        # trace ref when it returned; this resume turn records it as parent.
        turn_state["parent_ref"] = pending.get("trace_ref")
        yield _sse("pipeline_stage", stage="analysis_mode_clarification",
                   label="Continuing selected analysis…")
        step1 = dict(pending["step1"])
        original_prompt = step1.get("operational_notation") or pending.get("user_input") or ""
        answered_prompt = (
            f"{original_prompt}\n\n[User clarification]\n{user_input}"
        ).strip()
        step1["cleaned_prompt"] = answered_prompt
        step1["operational_notation"] = answered_prompt
        pr = dict(step1.get("pre_routing") or {})
        pr["pending_clarification"] = None
        pr["pending_clarification_stage"] = None
        pr["completeness_gaps"] = []
        pr["dispatch_announcement"] = compose_dispatch_announcement(
            step1.get("mode") or "", answered_prompt,
        )
        pr["manual_clarification_answered"] = True
        step1["pre_routing"] = pr
        try:
            yield from _run_pipeline_from_step2(
                step1,
                pending["config"],
                history,
                pending.get("user_input") or original_prompt,
                images=pending.get("images"),
                extra_context=pending.get("extra_context"),
                trace_dir=trace_dir,
                config_name=config_name,
                conversation_tag=pending.get("conversation_tag") or conversation_tag,
                turn_state=turn_state,
            )
        finally:
            if trace_dir:
                try:
                    from boot import compute_cost_summary as _ccs
                    _ccs(trace_dir)
                except Exception as _cs_exc:
                    print(f"[cost-summary] post-stream computation failed: "
                          f"{_cs_exc}", flush=True)
        return

    # --- Framework slash-command short-circuit ---
    # Detect /framework <name> [<query>] and route to either the one-shot
    # milestone executor (when a query is supplied) or the interactive
    # elicitation handler (when no query — the user wants the framework to
    # walk them through it). Phase A.5 cleanup and mode classification are
    # bypassed entirely; framework invocations are explicit.
    from milestone_executor import (
        is_framework_command, framework_command_has_query,
        run_framework_command, parse_framework_command,
    )
    if is_framework_command(user_input):
        turn_state["kind"] = "framework_command"
        if framework_command_has_query(user_input):
            # Execution Review Phase 2 (condition 4): the /framework one-shot
            # runs the gear pipeline with tools — hold before it if the query
            # classifies irreversible. Fail-safe.
            _fw_tier_srv, _fw_ts_srv = None, None
            try:
                import risk_gate as _rgate_fw
                _fw_ts_srv = _rgate_fw.now_ts()
                _fr = _rgate_fw.assign_tier(user_input, panel_id,
                                            surface="framework")
                _fw_tier_srv = _fr["risk_tier"]
                _fhold, _ = _rgate_fw.evaluate_hold(
                    _fw_tier_srv, conversation_id=panel_id,
                    prompt=user_input, surface="framework",
                    stealth=(_conv_tag == "stealth"), description=user_input)
                if _fhold is not None:
                    turn_state["kind"] = "risk_hold"
                    yield _sse("response", text=_fhold)
                    return
            except Exception as _rge_fw:
                print(f"[risk-gate] server framework hold skipped: {_rge_fw}")
            # Seed the turn context so the framework's tool events carry this
            # conversation_id (the framework path bypasses step-2 seeding);
            # without it route_observed folds zero events (they'd land under
            # conversation_id=None). Also stamps the tier for the per-call gate.
            try:
                import tool_events as _te_fw2
                _te_fw2.set_turn_context(conversation_id=panel_id, surface="chat",
                                         stealth=(_conv_tag == "stealth"),
                                         risk_tier=_fw_tier_srv)
            except Exception:
                pass
            yield _sse("pipeline_stage", stage="framework_execution",
                       label="Running framework via layered milestone executor…")
            try:
                turn_state["kind"] = "framework-run"
                _trace_ctx = {"conversation_tag": _conv_tag}
                result_text = run_framework_command(
                    user_input, config, trace_dir=trace_dir,
                    conversation_tag=_conv_tag,
                    trace_context=_trace_ctx,
                    project_nexus=_framework_project_nexus(extra_context),
                    one_run_profile=config_name,
                    style_context=extra_context)
                turn_state["status"] = _trace_ctx.get("status") or "completed"
                turn_state["framework_id"] = _trace_ctx.get("framework_id")
                turn_state["mode"] = _trace_ctx.get("mode") or turn_state["mode"]
                turn_state["child_refs"] = list(_trace_ctx.get("child_trace_refs") or [])
            except Exception as exc:
                turn_state["status"] = "error"
                yield _sse("error", text=f"Framework execution error: {exc}")
                # Finding 3: record what the failed framework run observed.
                try:
                    _rgate_fw.record_route_observed(
                        (panel_id, _fw_ts_srv or ""), risk_tier=_fw_tier_srv)
                except Exception:
                    pass
                return
            yield _sse("response", text=result_text)
            # Finding 3: record route_observed on the framework terminal path.
            try:
                _rgate_fw.record_route_observed(
                    (panel_id, _fw_ts_srv or ""), risk_tier=_fw_tier_srv,
                    output_text=result_text)  # Phase 3: source-read signal
            except Exception:
                pass
            return
        # Empty-query form → start an interactive elicitation session.
        try:
            framework_name, _, _ = parse_framework_command(user_input)
        except ValueError as exc:
            turn_state["status"] = "error"
            yield _sse("error", text=f"Framework command error: {exc}")
            return
        turn_state["kind"] = "framework_elicitation"
        yield _sse("pipeline_stage", stage="framework_elicitation_start",
                   label=f"Starting interactive {framework_name} session…")
        try:
            text = framework_elicitation.start_elicitation(
                framework_name, history or [], config,
                project_nexus=_framework_project_nexus(extra_context),
                one_run_profile=config_name,
                style_context=extra_context,
            )
        except Exception as exc:
            turn_state["status"] = "error"
            yield _sse("error", text=f"Framework elicitation error: {exc}")
            return
        yield _sse("response", text=text)
        return

    # --- Step 1: Prompt Cleanup + Mode Selection ---
    # From here the turn is headed into the analytical pipeline; terminal
    # branches below refine the kind (clarification_pending / direct) and
    # finalize_manifest refines "chat" to chat-gear<N> once gear is known.
    turn_state["kind"] = "chat"
    yield _sse("pipeline_stage", stage="step1_cleanup", label="Cleaning prompt…")

    # Phase A receives structured authoritative history and packs it once
    # against its own endpoint.  Keep the legacy rendered lane empty here so
    # the transcript is neither duplicated nor assembled twice in memory.
    conv_context = ""

    # History-truncation stats — see boot._summarize_history_truncation.
    try:
        from boot import _summarize_history_truncation as _shx
        _hist_trunc = _shx(history)
    except Exception:
        _hist_trunc = None

    # Image attachments arrive on either channel:
    #   * /chat path                — base64 attachments decoded into `images`
    #   * /chat/multipart path      — disk-saved image referenced via
    #                                 extra_context["image_path"]
    # Both must surface into Phase A / pre-routing so Stage 3 satisfies
    # visual-input contracts and Phase A skips its "no image" directive.
    image_attached = bool(images) or bool(
        extra_context and extra_context.get("image_path")
    )

    step1 = run_step1_cleanup(user_input, conv_context, config,
                              trace_dir=trace_dir,
                              history_truncation_stats=_hist_trunc,
                              image_attached=image_attached,
                              config_name=config_name,
                              conversation_history=history)
    tier = step1["triage_tier"]

    # Manual mode-pick override. When the caller explicitly named a mode
    # via `manual_mode_selection` AND that mode exists in the registry,
    # the pick supersedes Stage 2's dispatch. Rationale:
    #
    #   * The script/refresh-image-modes.py and `/chat/multipart` from
    #     the V3 UI both send manual_mode_selection when the user has
    #     made an explicit pick; respecting that pick is the obvious
    #     semantic (Phase 6's popup will eventually surface a confirmation
    #     dialog before dispatch — until then, the explicit field IS the
    #     confirmation).
    #   * Stage 2 signal-vocab dispatch is best-effort inference; when a
    #     prompt's signals overlap (e.g. "annotate this CLD" matches both
    #     spatial-reasoning's "annotate this CLD" expert signal AND
    #     systems-dynamics-structural's CLD signals), the user's pick is
    #     the reliable disambiguator.
    #   * Bypass-to-direct-response is preserved — when Stage 1 detects a
    #     pure chitchat/lookup prompt the override is suppressed, so
    #     "what's 2+2 in spatial-reasoning mode" still bypasses cleanly.
    #
    # Validation: mode file must exist at `~/ora/modes/<slug>.md`. Unknown
    # picks fall through to Stage 2's dispatch with a server log entry.
    override_applied = False
    if (manual_mode_selection
        and manual_mode_selection != step1.get("mode")
        and not (step1.get("pre_routing") or {}).get("bypass_to_direct_response")
    ):
        mode_file = os.path.join(WORKSPACE, "modes", f"{manual_mode_selection}.md")
        if os.path.isfile(mode_file):
            prior_mode = step1.get("mode")
            prior_pre_routing = dict(step1.get("pre_routing") or {})
            prior_stage1_output = prior_pre_routing.get("stage1_output") or {}
            try:
                with open(mode_file, "r", encoding="utf-8") as f:
                    manual_mode_text = f.read()
            except OSError:
                manual_mode_text = ""
            manual_territory = _extract_mode_field(manual_mode_text, "territory")
            manual_prompt = step1.get("operational_notation") or user_input
            manual_s3 = stage3_input_completeness_check(
                manual_mode_selection,
                manual_prompt,
                extra_context or {},
            )
            pending_question = None
            if not manual_s3.get("inputs_complete"):
                pending_question = manual_s3.get("completeness_question")
                if manual_s3.get("graceful_degradation_offer"):
                    pending_question = (
                        f"{pending_question}\n\n"
                        f"{manual_s3['graceful_degradation_offer']}"
                    )
            step1["mode"] = manual_mode_selection
            step1["classification_confidence"] = "manual"
            step1["classification_intent"] = "USER_SELECTED_ANALYSIS_MODE"
            step1["detected_invocation"] = (
                step1.get("detected_invocation") or manual_mode_selection
            )
            step1["classification_reasoning"] = (
                f"User explicitly selected {manual_mode_selection}; "
                f"automatic Stage 2 dispatch to {prior_mode} was bypassed."
            )
            pr = step1.setdefault("pre_routing", {})
            pr.clear()
            pr.update({
                "dispatched_mode_id": manual_mode_selection,
                "territory": manual_territory or None,
                "bypass_to_direct_response": False,
                "pending_clarification": pending_question,
                "pending_clarification_stage": (
                    "stage3" if pending_question else None
                ),
                "completeness_gaps": manual_s3.get("missing_fields", []),
                "dispatch_announcement": (
                    None if pending_question else compose_dispatch_announcement(
                        manual_mode_selection, user_input,
                    )
                ),
                "lighter_sibling_mode_id": manual_s3.get("lighter_sibling_mode_id"),
                "confidence": "manual",
                "stage1_match_count": len(prior_stage1_output.get("matches", [])),
                "stage3_output": manual_s3,
                "manual_override_applied": True,
                "manual_override_prior_dispatch": prior_mode,
            })
            print(f"[manual-mode-override] '{prior_mode}' → '{manual_mode_selection}' "
                  f"(Stage 2 dispatch superseded by explicit user pick)", flush=True)
            override_applied = True
        else:
            print(f"[manual-mode-override] '{manual_mode_selection}' not a valid mode "
                  f"(no {mode_file}); falling through to Stage 2 dispatch "
                  f"'{step1.get('mode')}'", flush=True)

    # V3 Input Handling Phase 1 / analysis picker — compare the user's
    # explicit toolbar selection or detected invocation against the final
    # mode. Manual analysis picks may already have overridden Step 1 above;
    # frameworks still suppress the comparison because they own routing.
    # Storing on ``step1`` keeps the data available on clarification resume.
    intent_comparison = compare_intent_with_mode(
        picked_mode=step1["mode"],
        manual_mode_selection=manual_mode_selection,
        detected_invocation=step1.get("detected_invocation", ""),
        framework_selected=framework_selected,
    )
    step1["intent_comparison"] = intent_comparison

    # Phase 9 — surface pre-routing pipeline state to the UI. The four-stage
    # pipeline ran inside run_step1_cleanup; pull its decision off step1 and
    # publish via SSE so the client can show the dispatch announcement,
    # residual disambiguation questions, and completeness gaps per
    # Decision I/J's expanded output format.
    pre_routing = step1.get("pre_routing", {}) or {}
    turn_state["mode"] = step1.get("mode")

    confidence = step1.get("classification_confidence", "")
    conf_tag = f" ({confidence})" if confidence else ""
    yield _sse("pipeline_stage", stage="step1_done",
               mode=step1["mode"], triage_tier=tier,
               confidence=confidence,
               detected_invocation=step1.get("detected_invocation", ""),
               manual_mode_selection=manual_mode_selection,
               manual_lens_selection=manual_lens_selection,
               framework_selected=framework_selected,
               intent_comparison=intent_comparison,
               territory=pre_routing.get("territory"),
               dispatched_mode_id=pre_routing.get("dispatched_mode_id"),
               dispatch_announcement=pre_routing.get("dispatch_announcement"),
               completeness_gaps=pre_routing.get("completeness_gaps", []),
               pending_clarification_stage=pre_routing.get("pending_clarification_stage"),
               label=f"Mode: {step1['mode']}{conf_tag} | Tier {tier}")

    if (pre_routing.get("manual_override_applied")
        and pre_routing.get("pending_clarification")):
        turn_state["kind"] = "clarification_pending"
        turn_state["status"] = "paused"
        _pending_clarification[panel_id] = {
            "source": "manual_mode_selection",
            "step1": step1,
            "config": config,
            "history": history,
            "user_input": user_input,
            "images": images,
            "extra_context": extra_context,
            "conversation_tag": conversation_tag,
            "pre_routing_stage": pre_routing.get("pending_clarification_stage"),
            # This paused turn's own trace ref — the eventual resume turn
            # records it as parent_trace_ref (design-gate condition 4).
            "trace_ref": trace_ref_val,
        }
        yield _sse("pipeline_stage", stage="analysis_mode_elicitation",
                   mode=step1["mode"],
                   label="Missing input for selected analysis")
        yield _sse("response", text=pre_routing["pending_clarification"])
        return

    # --- Legacy direct fallback for unresolved clarification only ---------
    # ``simple`` is an installed Gear-1 mode, not a placeholder. Routed
    # direct-response turns must continue through Step 2 and the Gear-1
    # executor so ``utility.classification``, the named configuration, and
    # physical-call trace identity remain authoritative. Explicit ``/direct``
    # still uses ``_direct_stream`` at its separate command boundary.
    #
    # The only compatibility fallback here is an unresolved clarification on
    # a caller that cannot render the clarification surface. Let the direct
    # model carry that question rather than returning an empty response.
    fallback_to_direct = (
        step1.get("mode") == "standard"
        or pre_routing.get("pending_clarification")
    )
    if fallback_to_direct:
        turn_state["kind"] = "direct"
        print(
            f"[pipeline-bypass] bypass_to_direct={pre_routing.get('bypass_to_direct_response')!r} "
            f"step1_mode={step1.get('mode')!r} pending_clar={bool(pre_routing.get('pending_clarification'))} "
            f"dispatched_mode={pre_routing.get('dispatched_mode_id')!r} "
            f"clar_question={(pre_routing.get('pending_clarification') or '')[:120]!r}",
            flush=True,
        )
        yield from _direct_stream(user_input, history, images=images,
                                  panel_id=panel_id, conversation_tag=conversation_tag,
                                  risk_override=(extra_context or {}).get("risk_override"),
                                  extra_context=extra_context,
                                  turn_state=turn_state)
        return

    # --- Phase 9: pre-routing pipeline question gate ---
    # Stage 2 and Stage 3 questions ride the existing clarification panel.
    # Stage 2 surfaces a disambiguation question (territory/mode unclear);
    # Stage 3 surfaces a completeness question (mode picked but missing input).
    pending_question = pre_routing.get("pending_clarification")
    pending_stage = pre_routing.get("pending_clarification_stage")
    if pending_question:
        yield _sse("pipeline_stage", stage="clarification_generating",
                    label=("Need a quick clarification before I can route this..."
                           if pending_stage == "stage2"
                           else "I need a bit more to run this analysis..."))

        # Frame the question as a single-question list so the existing
        # clarification panel renders it. The plain-language phrasing comes
        # from the pipeline (Disambiguation Style Guide §5.3 / §5.8).
        questions = [{"question": pending_question, "rationale": ""}]
        if pending_stage == "stage3" and pre_routing.get("lighter_sibling_mode_id"):
            questions[0]["lighter_sibling_mode_id"] = pre_routing["lighter_sibling_mode_id"]

        turn_state["kind"] = "clarification_pending"
        turn_state["status"] = "paused"
        _pending_clarification[panel_id] = {
            "step1": step1,
            "config": config,
            "history": history,
            "user_input": user_input,
            "images": images,
            "extra_context": extra_context,
            "conversation_tag": conversation_tag,
            "pre_routing_stage": pending_stage,
            "trace_ref": trace_ref_val,
        }

        yield _sse("clarification_needed",
                    tier=tier,
                    mode=step1["mode"],
                    questions=questions,
                    pre_routing_stage=pending_stage,
                    territory=pre_routing.get("territory"),
                    completeness_gaps=pre_routing.get("completeness_gaps", []),
                    label=("Quick clarification" if pending_stage == "stage2"
                           else "Missing input"))
        return  # Pipeline pauses here — resumed via /api/clarification

    # --- Tier 2/3 fallback clarification gate (legacy path) ---
    # Phase 9 — skip the legacy clarification path when the pre-routing
    # pipeline has already dispatched a mode. In that case the tier value
    # (defaulted to 2 per Decision C's default-on-ambiguity rule) is not a
    # request for clarification, just the analytical-pipeline tier marker.
    # Firing legacy clarification here was emitting a `clarification_needed`
    # event that the plain-HTTP /chat/multipart endpoint can't handle,
    # producing the silent "pipeline produced no response" failure.
    already_dispatched = bool(pre_routing.get("dispatched_mode_id"))
    if tier >= 2 and not already_dispatched:
        yield _sse("pipeline_stage", stage="clarification_generating",
                    label="Generating clarification questions…")
        questions = _generate_clarification_questions(step1, config)

        # Store pending state for resumption
        turn_state["kind"] = "clarification_pending"
        turn_state["status"] = "paused"
        _pending_clarification[panel_id] = {
            "step1": step1,
            "config": config,
            "history": history,
            "user_input": user_input,
            "images": images,
            "extra_context": extra_context,
            "conversation_tag": conversation_tag,
            "trace_ref": trace_ref_val,
        }

        yield _sse("clarification_needed",
                    tier=tier,
                    mode=step1["mode"],
                    questions=questions,
                    label=f"Tier {tier} — clarification recommended")
        return  # Pipeline pauses here — resumed via /api/clarification

    # --- Tier 1 + Stage 4 dispatch announcement ---
    # Phase 9 — emit the dispatch announcement (educational parenthetical)
    # at Stage 4 entry per Decision E.
    if pre_routing.get("dispatch_announcement"):
        yield _sse("dispatch_announcement",
                   text=pre_routing["dispatch_announcement"],
                   mode=step1["mode"],
                   territory=pre_routing.get("territory"))

    yield _sse("pipeline_stage", stage="step2_context", label="Assembling context…")
    try:
        yield from _run_pipeline_from_step2(step1, config, history, user_input,
                                            images=images, extra_context=extra_context,
                                            trace_dir=trace_dir,
                                            config_name=config_name,
                                            conversation_tag=conversation_tag,
                                            turn_state=turn_state)
    finally:
        # 2026-05-28: aggregate per-turn token usage into cost-summary.json.
        # Runs even when the SSE consumer disconnects mid-stream (GeneratorExit)
        # so partial traces still get a cost summary computed.
        if trace_dir:
            try:
                from boot import compute_cost_summary as _ccs
                _ccs(trace_dir)
            except Exception as _cs_exc:
                print(f"[cost-summary] post-stream computation failed: "
                      f"{_cs_exc}", flush=True)


def _tool_status_label(tool_name, params):
    """Generate a human-readable status label for a tool call."""
    if tool_name == "bash_execute":
        cmd = params.get("command", "")
        return f"[executing: {cmd[:50]}{'…' if len(cmd) > 50 else ''}]"
    elif tool_name == "file_edit":
        fp = params.get("file_path", params.get("path", ""))
        return f"[editing: {os.path.basename(fp)}]"
    elif tool_name == "search_files":
        return f"[searching files: {params.get('pattern', '')}]"
    elif tool_name == "spawn_subagent":
        return "[running subagent task…]"
    elif tool_name.startswith("mcp_"):
        parts = tool_name.split("_", 2)
        return f"[calling {parts[1] if len(parts) > 1 else 'mcp'}: {parts[2] if len(parts) > 2 else tool_name}]"
    else:
        return f"[{tool_name}…]"


def _direct_stream(user_input, history, images=None, panel_id="main",
                   conversation_tag="", risk_override=None, extra_context=None,
                   turn_state=None):
    """Lifecycle-scoped wrapper for every legacy direct-model invocation.

    ``_direct_stream`` is called both from the pipeline fallback and directly
    by tests/legacy routes.  Keeping the scope here guarantees those direct
    callers cannot leave oversight, tool-event, private-values, or trace
    context attached to a reused worker thread.
    """
    turn_tag = _effective_conversation_tag(panel_id, conversation_tag)
    trace_dir = (
        turn_state.get("trace_dir")
        if isinstance(turn_state, dict)
        else None
    )
    boot_context = _boot_context_api()
    tag_token = boot_context.set_conversation_tag_context(turn_tag)
    trace_token = boot_context.set_turn_trace_context(trace_dir)
    direct_context = dict(extra_context or {})
    direct_context.setdefault("cleaned_prompt", user_input)
    direct_context.setdefault("conversation_context_chunks", [])
    boot_context._finalize_optional_context_package(
        direct_context, conversation_id=panel_id, history=history,
    )
    history_token = boot_context.set_dialogue_history_context(history)
    optional_token = boot_context._set_context_units_from_package(direct_context)
    scope = nullcontext()
    try:
        try:
            from orchestrator.oversight_events import lifecycle_context_scope
            scope = lifecycle_context_scope(
                stealth=turn_tag == "stealth",
                conversation_id=panel_id,
                tool_context={
                    "trace_dir": trace_dir,
                    "surface": "chat",
                    "risk_tier": None,
                },
            )
        except Exception as exc:
            print(
                f"[conversation-lifecycle] direct context scope unavailable "
                f"for {panel_id}: {exc}", file=sys.stderr, flush=True,
            )
        with scope:
            yield from _direct_stream_impl(
                user_input, history, images=images, panel_id=panel_id,
                conversation_tag=turn_tag, risk_override=risk_override,
                extra_context=direct_context,
                turn_state=turn_state,
            )
    finally:
        boot_context.reset_optional_context_context(optional_token)
        boot_context.reset_dialogue_history_context(history_token)
        boot_context.reset_turn_trace_context(trace_token)
        boot_context.reset_conversation_tag_context(tag_token)


def _direct_system_prompt(config, style_context=None):
    """Assemble the direct/bypass prompt with the resolved Persona style."""
    try:
        persona_resolution = _persona_mod().resolve_persona()
    except Exception as exc:
        print(f"[persona] direct Persona unavailable: {exc}",
              file=sys.stderr, flush=True)
        persona_resolution = None
    prompt = load_boot_md(
        include_persona=bool(persona_resolution),
        persona_resolution=persona_resolution,
    )
    style_package = dict(style_context or {})
    if "style_id" not in style_package:
        style_package["style_id"] = _resolve_effective_style_id(config)
        if not style_package["style_id"] and persona_resolution:
            style_package["style_id"] = "__persona__"
    style_package.update({
        "gear": 1,
        "style_register": "conversational",
        "persona_resolution": persona_resolution,
    })
    style = _compose_output_style(style_package)
    return prompt + ("\n\n" + style if style else "")


def _direct_stream_impl(user_input, history, images=None, panel_id="main",
                        conversation_tag="", risk_override=None,
                        extra_context=None, turn_state=None):
    """Generator: legacy single-model agentic loop with SSE tool events.
    Routes all tool calls through the unified dispatcher.

    ``risk_override`` (Execution Review Phase 2): an inline ``/risk`` tier
    threaded from the pipeline turn head when a turn falls back to direct
    mode — so ``/risk irreversible <trivial prompt>`` still holds here
    instead of silently classifying light.

    ``turn_state`` (Trace Walk Chunk 0): optional — set only by the
    fallback_to_direct call site inside ``_pipeline_stream_impl``, which
    already opened a trace for this turn. This function re-resolves its
    own endpoint independently of that caller's earlier check; if it comes
    up empty here (e.g. the active endpoint was removed in the window
    between the two checks), the turn genuinely produced no response and
    must finalize as an error, not the "direct" short-circuit its kind
    already carries (design-gate condition 1). The explicit-direct wrapper
    also passes turn_state so the same production function records its real
    response or endpoint error in that direct-entry trace.
    """
    _ds_trace_dir = (
        turn_state.get("trace_dir")
        if isinstance(turn_state, dict)
        else None
    )
    config   = load_config()
    endpoint = get_endpoint(config)

    if endpoint is None:
        terminal_value = (
            "No AI endpoints configured. Add a connection or install a local model."
        )
        if turn_state is not None:
            turn_state["status"] = "error"
        if _ds_trace_dir:
            try:
                from orchestrator import pipeline_trace as _pt_direct_error
                _pt_direct_error.write_step(
                    _ds_trace_dir, "step3-direct-no-endpoint",
                    {"endpoint_available": False},
                )
                _pt_direct_error.record_terminal_output(
                    _ds_trace_dir, terminal_value,
                    route="server-direct-error",
                    output_target="screen", persisted=False,
                )
            except Exception:
                pass
        yield _sse("error", text=terminal_value)
        return

    # Keep the current call payload separate from Dialogue continuity.  The
    # latter is packed once, against this endpoint's real remaining capacity,
    # immediately before each physical call below.  This also prevents a
    # client-supplied system message from replacing Ora's Direct prompt.
    messages = [
        {
            "role": "system",
            "content": _direct_system_prompt(config, extra_context),
        },
        {"role": "user", "content": user_input},
    ]

    # Auto-approve in server mode (permission handled by UI later).
    # Execution Review Phase 1: auto-approve now only covers the legacy
    # approve tier — the execution gate in dispatcher.dispatch runs before
    # and independently of this mode, so irreversible / unknown / secret /
    # sensitive actions are blocked+queued here rather than sailing through.
    set_permission_mode("auto-approve")

    # Direct mode runs no step-2 context assembly, so seed the tool-event
    # recorder's turn context here (no trace dir → events go to the global
    # sink, marked surface=chat).
    _ds_tag = _effective_conversation_tag(panel_id, conversation_tag)
    try:
        try:
            import tool_events as _te_ds
        except ImportError:
            from orchestrator import tool_events as _te_ds
        # Resolve the conversation tag here (direct mode runs no step 2) so a
        # stealth turn's tool events are suppressed at write and its
        # non-stealth events are purgeable by conversation id. Without this a
        # stealth direct-mode turn would leak durable content to the global
        # sink — the exact hole the stealth machinery exists to close.
        _te_ds.set_turn_context(trace_dir=_ds_trace_dir, conversation_id=panel_id,
                                stealth=(_ds_tag == "stealth"), surface="chat")
    except Exception:
        pass

    # --- Execution Review Phase 2: risk gate on the direct/bypass path -----
    # The bypass guard routes trivial/self-contained prompts here, but an
    # irreversible-intent prompt (e.g. "send an email to the list") can land
    # here too — so the Stage-A floor + irreversible hold must fire before the
    # auto-approve agentic loop runs. Default light (this IS the trivial path);
    # floors raise it. Fail-safe.
    _route_turn_ts_ds = None
    try:
        import risk_gate as _rgate_ds
        _route_turn_ts_ds = _rgate_ds.now_ts()
        # Strip an inline /risk arriving straight on the direct route (the
        # pipeline turn head never ran for a /direct turn); a threaded
        # risk_override (pipeline fallback) takes precedence.
        _clean_ds, _ovr_ds = _rgate_ds.strip_risk_prefix(user_input)
        if _ovr_ds is not None:
            user_input = _clean_ds
            messages[-1]["content"] = user_input
        _eff_override = risk_override or _ovr_ds
        _r_ds = _rgate_ds.assign_tier(user_input, panel_id,
                                      is_trivial_text=True, override=_eff_override,
                                      surface="direct")
        _hold_ds, _ = _rgate_ds.evaluate_hold(
            _r_ds["risk_tier"], conversation_id=panel_id, prompt=user_input,
            surface="direct", stealth=(_ds_tag == "stealth"),
            description=user_input)
        if _hold_ds is not None:
            _rgate_ds.record_route_observed((panel_id, _route_turn_ts_ds),
                                            risk_tier=_r_ds["risk_tier"])
            if turn_state is not None:
                # The caller already stamped kind="direct" before invoking
                # this generator; a held turn is an intentional stop, not
                # the "direct" short-circuit — re-kind so the manifest
                # reads risk_hold, matching every other risk-hold site.
                turn_state["kind"] = "risk_hold"
            yield _sse("response", text=_hold_ds)
            return
        _te_ds.update_turn_risk_tier(_r_ds["risk_tier"])
    except Exception as _rge_ds:
        print(f"[risk-gate] direct-stream hold skipped: {_rge_ds}")

    def _call_direct_stage(model_messages, model_endpoint, images=None):
        boot_context = _boot_context_api()
        tokens = boot_context.set_model_stage_context(
            "step3-direct-response", gear=1,
        )
        try:
            return call_model(model_messages, model_endpoint, images=images)
        finally:
            boot_context.reset_model_stage_context(tokens)

    response = ""
    for iteration in range(MAX_ITERATIONS):
        call_images = images if iteration == 0 else None
        # Pass images only on the first call (they accompany the user's original message)
        response = _call_direct_stage(
            messages, endpoint, images=call_images,
        )
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            reset_consecutive()
            clean = strip_tool_calls(response)
            if _ds_trace_dir:
                try:
                    from orchestrator import pipeline_trace as _pt_direct_response
                    _pt_direct_response.write_step(
                        _ds_trace_dir, "step3-direct-response", {
                            "raw_response": clean,
                            "endpoint": (
                                endpoint.get("name")
                                if isinstance(endpoint, dict) else str(endpoint)
                            ),
                            "iterations": iteration + 1,
                        })
                except Exception:
                    pass
            if (turn_state is not None
                    and turn_state.get("kind") != "direct"):
                turn_state["status"] = "completed"
            coverage = _boot_context_api().get_context_coverage()
            if coverage:
                yield _sse(
                    "pipeline_stage",
                    stage="context_coverage",
                    label="Context capacity coverage",
                    context_coverage=coverage,
                )
            yield _sse("response", text=clean)
            try:
                _rgate_ds.record_route_observed(
                    (panel_id, _route_turn_ts_ds),
                    risk_tier=_r_ds.get("risk_tier"),
                    output_text=clean)  # Phase 3: source-read signal
            except Exception:
                pass
            return

        for tc in tool_calls:
            label = _tool_status_label(tc["name"], tc["parameters"])
            yield _sse("tool_status", text=label)
            # Use the structured-outcome wrapper so the model sees a clear
            # success/error marker on the tool result. Previously every
            # tool's bare string return looked the same — a tool error
            # could be misread as a real result and the model would build
            # downstream reasoning on top of garbage.
            try:
                from boot import execute_tool_with_outcome as _eto
                result, outcome, reason = _eto(tc["name"], tc["parameters"])
            except Exception:
                result = execute_tool(tc["name"], tc["parameters"])
                outcome, reason = "ok", ""
            yield _sse("tool_result", name=tc["name"],
                       result=result[:500], outcome=outcome, reason=reason)
            messages.append({"role": "assistant", "content": response})
            marker = (
                f"[Tool: {tc['name']} | outcome: {outcome}"
                + (f" | reason: {reason}" if reason else "")
                + "]"
            )
            messages.append({"role": "user", "content": f"{marker}\n{result}"})

        # Context compaction check
        ctx_window = endpoint.get("context_window", 1_000_000)
        messages = compact_context(messages, _call_direct_stage, ctx_window)

    # Agentic loop reached MAX_ITERATIONS while still emitting tool calls
    # (or the model produced nothing on the last iteration). Surface the
    # overrun so the user doesn't receive a stripped-empty response with
    # no signal that the model never converged. Parity with
    # boot._run_model_with_tools's overrun fix.
    clean = strip_tool_calls(response)
    endpoint_name = endpoint.get("name") if isinstance(endpoint, dict) else str(endpoint)
    print(
        f"[_direct_stream] agentic loop hit MAX_ITERATIONS={MAX_ITERATIONS} "
        f"with tool calls still pending; stripped response length="
        f"{len(clean)} chars; endpoint={endpoint_name}",
        flush=True,
    )
    yield _sse("agentic_loop_overrun",
               max_iterations=MAX_ITERATIONS,
               stripped_response_chars=len(clean),
               final_response_was_empty_after_strip=(not clean.strip()))
    if _ds_trace_dir:
        try:
            from orchestrator import pipeline_trace as _pt_direct_overrun
            _pt_direct_overrun.write_step(
                _ds_trace_dir, "step3-direct-response", {
                    "raw_response": clean,
                    "endpoint": endpoint_name,
                    "iterations": MAX_ITERATIONS,
                    "agentic_loop_overrun": True,
                })
        except Exception:
            pass
    if (turn_state is not None
            and turn_state.get("kind") != "direct"):
        turn_state["status"] = "completed"
    yield _sse("response", text=clean)
    # A MAX_ITERATIONS overrun is the highest-mutation direct exit (many tool
    # calls ran); record route_observed here too so this path isn't missed.
    try:
        _rgate_ds.record_route_observed((panel_id, _route_turn_ts_ds),
                                        risk_tier=_r_ds.get("risk_tier"),
                                        output_text=clean)  # Phase 3
    except Exception:
        pass


def _traced_direct_entry_stream(user_input, history, images=None,
                                panel_id="main", conversation_tag="",
                                extra_context=None):
    """Trace the real explicit server direct-entry path, fail-open."""
    turn_state = {
        "trace_dir": None, "kind": "direct-entry", "status": None,
        "mode": None, "gear": 1,
    }
    try:
        from orchestrator import pipeline_trace as _pt_direct_entry
    except Exception:
        _pt_direct_entry = None
    if _pt_direct_entry is not None:
        try:
            turn_state["trace_dir"] = _pt_direct_entry.start_trace(
                conversation_id=panel_id,
                raw_input=user_input,
                stealth=(conversation_tag == "stealth"),
                conversation_tag=conversation_tag,
            )
        except Exception:
            turn_state["trace_dir"] = None
    trace_ref = None
    if _pt_direct_entry is not None and turn_state["trace_dir"]:
        try:
            trace_ref = _pt_direct_entry.trace_ref_for_dir(
                turn_state["trace_dir"]
            )
        except Exception:
            trace_ref = None
    if trace_ref:
        yield _sse("trace_ref", ref=trace_ref)
    try:
        yield from _direct_stream(
            user_input, history, images=images,
            panel_id=panel_id, conversation_tag=conversation_tag,
            extra_context=extra_context,
            turn_state=turn_state,
        )
    except BaseException:
        turn_state["status"] = "error"
        raise
    finally:
        if _pt_direct_entry is not None:
            try:
                _pt_direct_entry.finalize_manifest(
                    turn_state["trace_dir"], kind=turn_state["kind"],
                    status_hint=turn_state["status"], gear=turn_state["gear"],
                )
            except Exception:
                pass


def agentic_loop_stream(user_input, history, use_pipeline=True, panel_id="main", images=None, extra_context=None,
                          manual_mode_selection="", manual_lens_selection="",
                          framework_selected="", config_name=None,
                          conversation_tag=""):
    """Route to pipeline or direct stream based on mode.

    ``extra_context`` (WP-3.3): optional merged-input dict threaded into the
    pipeline path. Direct turns consume only its already-resolved style keys;
    spatial and other pipeline-only context remains unused there.

    V3 Input Handling Phase 1 / analysis picker: ``manual_mode_selection`` /
    ``manual_lens_selection`` / ``framework_selected`` are threaded into
    ``_pipeline_stream`` so explicit analysis picks can bypass automatic
    classification, lenses can foreground a selected mental model, and
    framework picks can suppress mode-intent comparison. ``_direct_stream``
    ignores them — direct mode bypasses the classifier entirely.
    """
    turn_tag = _effective_conversation_tag(panel_id, conversation_tag)
    boot_context = _boot_context_api()
    tag_token = boot_context.set_conversation_tag_context(turn_tag)
    trace_token = boot_context.set_turn_trace_context(None)
    scope = nullcontext()
    try:
        try:
            from orchestrator.oversight_events import lifecycle_context_scope
            scope = lifecycle_context_scope(
                stealth=turn_tag == "stealth",
                conversation_id=panel_id,
                tool_context={
                    "trace_dir": None,
                    "surface": "chat",
                    "risk_tier": None,
                },
            )
        except Exception as exc:
            # Fail open loudly: legacy inner setters still provide the primary
            # pipeline suppression, but this restoration wrapper could not be
            # armed and direct-mode oversight correlation may be incomplete.
            print(
                f"[conversation-lifecycle] turn context scope unavailable "
                f"for {panel_id}: {exc}", file=sys.stderr, flush=True,
            )
        with scope:
            if use_pipeline:
                yield from _pipeline_stream(
                    user_input, history, panel_id=panel_id,
                    images=images, extra_context=extra_context,
                    manual_mode_selection=manual_mode_selection,
                    manual_lens_selection=manual_lens_selection,
                    framework_selected=framework_selected,
                    config_name=config_name,
                    conversation_tag=turn_tag,
                )
            else:
                yield from _traced_direct_entry_stream(
                    user_input, history, images=images,
                    panel_id=panel_id, conversation_tag=turn_tag,
                    extra_context=extra_context,
                )
    finally:
        boot_context.reset_turn_trace_context(trace_token)
        boot_context.reset_conversation_tag_context(tag_token)

# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # V3 cutover 2026-05-02: `/` serves index-v3.html; /v3 remains as a
    # stable alias for direct V3 access. The legacy /classic and /v2 routes
    # (pre-cutover index.html / index-v2.html) were retired 2026-05-30 —
    # both interfaces remain recoverable from git history.
    return send_from_directory(os.path.join(WORKSPACE, "server"), "index-v3.html")

@app.route("/v3")
def index_v3():
    return send_from_directory(os.path.join(WORKSPACE, "server"), "index-v3.html")

@app.route("/health")
def health():
    config   = load_config()
    endpoint = get_endpoint(config)
    # Include the canonical checkout root so launchers can distinguish the
    # supervised Ora instance from another development worktree that happens
    # to answer on one of the fallback ports.  The service is localhost-only;
    # this field is operational identity, not a remotely exposed machine id.
    ora_home = os.path.realpath(WORKSPACE)
    return json.dumps({
        "status": "ok",
        "endpoint": endpoint.get("name") if endpoint else None,
        "ora_home": ora_home,
    })


_ANALYSIS_TERRITORIES = {
    "T0":  ("Default & General", 0),
    "T1":  ("Argument Examination", 1),
    "T2":  ("Interest & Power", 2),
    "T3":  ("Decisions Under Uncertainty", 3),
    "T4":  ("Causal Investigation", 4),
    "T5":  ("Hypothesis Evaluation", 5),
    "T6":  ("Future Exploration", 6),
    "T7":  ("Risk & Failure", 7),
    "T8":  ("Stakeholder Conflict", 8),
    "T9":  ("Paradigm & Assumptions", 9),
    "T10": ("Conceptual Clarification", 10),
    "T11": ("Structural Relationships", 11),
    "T12": ("Cross-Domain Synthesis", 12),
    "T13": ("Negotiation & Conflict Resolution", 13),
    "T14": ("Orientation in Unfamiliar Territory", 14),
    "T15": ("Evaluation by Stance", 15),
    "T16": ("Mechanism Understanding", 16),
    "T17": ("Process & Systems", 17),
    "T18": ("Strategic Interaction", 18),
    "T19": ("Spatial Composition", 19),
    "T20": ("Open Exploration", 20),
    "T21": ("Project & Execution", 21),
}

_ANALYSIS_PICKER_EXCLUDED = {"INDEX", "modes-index", "simple"}


def _extract_mode_field(text: str, field: str) -> str:
    match = re.search(rf"^\s*{re.escape(field)}:\s*(.+?)\s*$", text, re.M)
    if not match:
        return ""
    value = match.group(1).strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        value = value[1:-1]
    return value.strip()


def _extract_mode_list(text: str, field: str, limit: int = 8) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if not re.match(rf"^\s*{re.escape(field)}:\s*$", line):
            continue
        base_indent = len(line) - len(line.lstrip())
        for item_line in lines[i + 1:]:
            stripped = item_line.strip()
            if not stripped:
                continue
            indent = len(item_line) - len(item_line.lstrip())
            if indent <= base_indent and re.match(r"^[A-Za-z0-9_-]+:", stripped):
                break
            match = re.match(r"^-\s+(.+)$", stripped)
            if match:
                value = match.group(1).strip()
                if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
                    value = value[1:-1]
                out.append(value.strip())
                if len(out) >= limit:
                    return out
        break
    return out


def _mode_picker_description(text: str, educational_name: str) -> str:
    for field in ("user_situation_signals", "routes_to_this_mode_when",
                  "prompt_shape_signals"):
        items = _extract_mode_list(text, field, limit=1)
        if items:
            return items[0]
    return educational_name


def _strip_lens_dependency_note(raw_value: str) -> str:
    """Normalize a ``lens_dependencies`` bullet to its mental-model file id."""
    value = (raw_value or "").strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        value = value[1:-1].strip()
    # Mode specs sometimes annotate applicability inline:
    # ``reason-swiss-cheese-model (when failure crosses layers)``.
    value = re.sub(r"\s+\([^)]*\)\s*$", "", value).strip()
    return value


def _extract_lens_dependencies(text: str) -> list[dict]:
    """Parse the opening mode spec's ``lens_dependencies`` block.

    The mode files use a small YAML-ish subset, but we avoid pulling in a
    full YAML dependency in the server hot path. Only three buckets are
    user-facing here: required, optional, and foundational.
    """
    lines = text.splitlines()
    start = None
    base_indent = 0
    for idx, line in enumerate(lines):
        if re.match(r"^\s*lens_dependencies:\s*$", line):
            start = idx + 1
            base_indent = len(line) - len(line.lstrip())
            break
    if start is None:
        return []

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    category = ""
    categories = {"required", "optional", "foundational"}
    for line in lines[start:]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent <= base_indent and not stripped.startswith("-"):
            break

        header = re.match(r"^(required|optional|foundational):(?:\s*\[\])?\s*$", stripped)
        if header:
            category = header.group(1)
            continue
        if not category or category not in categories:
            continue

        bullet = re.match(r"^-\s+(.+?)\s*$", stripped)
        if not bullet:
            continue
        raw = bullet.group(1).strip()
        lens_id = _strip_lens_dependency_note(raw)
        if not lens_id:
            continue
        key = (category, lens_id)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "id": lens_id,
            "category": category,
            "dependency_note": raw if raw != lens_id else "",
        })
    return rows


def _strip_markdown_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5:].lstrip()
    return text


def _extract_lens_field(text: str, field: str) -> str:
    match = re.search(rf"^\s*{re.escape(field)}:\s*(.+?)\s*$", text, re.M)
    if not match:
        return ""
    value = match.group(1).strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        value = value[1:-1]
    return value.strip()


def _extract_lens_applicability(text: str) -> list[str]:
    inline = re.search(r"^applicability:\s*\[(.*?)\]\s*$", text, re.M)
    if inline:
        return [
            item.strip().strip("'\"")
            for item in inline.group(1).split(",")
            if item.strip()
        ]

    block = re.search(r"^applicability:\s*\n((?:\s+-\s+.+\n?)+)", text, re.M)
    if not block:
        return []
    return [
        re.sub(r"^\s+-\s+", "", line).strip().strip("'\"")
        for line in block.group(1).splitlines()
        if line.strip()
    ]


def _lens_picker_description(text: str) -> str:
    body = _strip_markdown_frontmatter(text)
    trigger = re.search(r"^## Trigger\s*\n(.*?)(?=\n## |\Z)", body, re.M | re.S)
    if not trigger:
        return ""
    desc = " ".join(trigger.group(1).strip().split())
    if len(desc) <= 220:
        return desc
    trimmed = desc[:217].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{trimmed}..."


def _lens_picker_base_row(lens_id: str, text: str) -> dict:
    display_name = _extract_lens_field(text, "name")
    if not display_name:
        body = _strip_markdown_frontmatter(text)
        h1 = re.search(r"^#\s+(.+?)\s*$", body, re.M)
        display_name = h1.group(1).strip() if h1 else lens_id.replace("-", " ").title()
    return {
        "id": lens_id,
        "display_name": display_name,
        "display_description": _lens_picker_description(text),
    }


def _lens_picker_row_with_category(base_row: dict, category: str, dependency_note: str = "") -> dict:
    row = dict(base_row)
    row.update({
        "category": category,
        "dependency_note": dependency_note,
    })
    return row


def _read_lens_picker_row(lens_id: str, category: str, dependency_note: str = "") -> dict | None:
    """Return a picker row only when the lens exists at runtime."""
    safe_id = os.path.basename(lens_id)
    if safe_id != lens_id:
        return None
    path = os.path.join(MENTAL_MODELS_DIR, f"{lens_id}.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    return _lens_picker_row_with_category(
        _lens_picker_base_row(lens_id, text),
        category,
        dependency_note,
    )


def _build_lens_picker_index() -> dict:
    rows_by_id: dict[str, dict] = {}
    applicable_by_mode: dict[str, list[str]] = {}
    if not os.path.isdir(MENTAL_MODELS_DIR):
        return {
            "rows_by_id": rows_by_id,
            "applicable_by_mode": applicable_by_mode,
        }
    for entry in sorted(os.listdir(MENTAL_MODELS_DIR)):
        if not entry.endswith(".md"):
            continue
        lens_id = entry[:-3]
        if os.path.basename(lens_id) != lens_id:
            continue
        path = os.path.join(MENTAL_MODELS_DIR, entry)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        rows_by_id[lens_id] = _lens_picker_base_row(lens_id, text)
        for mode_id in _extract_lens_applicability(text):
            applicable_by_mode.setdefault(mode_id, []).append(lens_id)
    return {
        "rows_by_id": rows_by_id,
        "applicable_by_mode": applicable_by_mode,
    }


def _applicable_lens_picker_rows(
    mode_id: str,
    existing_ids: set[str],
    lens_index: dict | None = None,
) -> list[dict]:
    rows: list[dict] = []
    index = lens_index or _build_lens_picker_index()
    rows_by_id = index.get("rows_by_id", {})
    applicable_by_mode = index.get("applicable_by_mode", {})
    for lens_id in sorted(applicable_by_mode.get(mode_id, [])):
        if lens_id in existing_ids:
            continue
        base_row = rows_by_id.get(lens_id)
        if base_row:
            rows.append(_lens_picker_row_with_category(base_row, "related"))
            existing_ids.add(lens_id)
    return rows


def _mode_lens_picker_rows(
    mode_id: str,
    mode_text: str,
    lens_index: dict | None = None,
) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    unavailable: list[str] = []
    existing_ids: set[str] = set()
    index = lens_index or _build_lens_picker_index()
    rows_by_id = index.get("rows_by_id", {})
    for dep in _extract_lens_dependencies(mode_text):
        base_row = rows_by_id.get(dep["id"])
        if base_row:
            row = _lens_picker_row_with_category(
                base_row,
                dep["category"],
                dep.get("dependency_note", ""),
            )
            rows.append(row)
            existing_ids.add(dep["id"])
        else:
            unavailable.append(dep["id"])
    rows.extend(_applicable_lens_picker_rows(mode_id, existing_ids, index))
    return rows, unavailable


def _lens_available_for_mode(mode_id: str, lens_id: str) -> bool:
    safe_mode_id = os.path.basename(mode_id or "")
    safe_lens_id = os.path.basename(lens_id or "")
    if not safe_mode_id or safe_mode_id != mode_id:
        return False
    if not safe_lens_id or safe_lens_id != lens_id:
        return False
    mode_path = os.path.join(WORKSPACE, "modes", f"{mode_id}.md")
    if not os.path.isfile(mode_path):
        return False
    try:
        with open(mode_path, "r", encoding="utf-8") as f:
            mode_text = f.read()
    except OSError:
        return False
    index = _build_lens_picker_index()
    rows_by_id = index.get("rows_by_id", {})
    for dep in _extract_lens_dependencies(mode_text):
        if dep["id"] == lens_id:
            return lens_id in rows_by_id
    if lens_id not in rows_by_id:
        return False
    return lens_id in set(index.get("applicable_by_mode", {}).get(mode_id, []))


def _analysis_territory_meta(raw_territory: str) -> tuple[str, str, int]:
    match = re.search(r"\b(T\d+)\b", raw_territory or "")
    code = match.group(1) if match else "T0"
    name, order = _ANALYSIS_TERRITORIES.get(code, (raw_territory or "Other", 99))
    return code, name, order


def list_pickable_analysis_modes() -> list[dict]:
    """Return mode rows for the V3 Analyses picker.

    The source of truth is the runtime mode directory. Each mode file declares
    its own canonical name, educational name, territory, and trigger signals in
    the opening YAML-ish spec block; the picker reads those fields directly so
    the UI tracks actual executable modes instead of older public-site rosters.
    """
    modes_dir = os.path.join(WORKSPACE, "modes")
    if not os.path.isdir(modes_dir):
        return []

    rows: list[dict] = []
    lens_index = _build_lens_picker_index()
    for entry in os.listdir(modes_dir):
        if not entry.endswith(".md"):
            continue
        mode_id = entry[:-3]
        if mode_id in _ANALYSIS_PICKER_EXCLUDED:
            continue
        path = os.path.join(modes_dir, entry)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue

        display_name = _extract_mode_field(text, "canonical_name")
        if not display_name:
            h1 = re.search(r"^#\s+MODE:\s*(.+?)\s*$", text, re.M)
            display_name = h1.group(1).strip() if h1 else mode_id
        educational_name = _extract_mode_field(text, "educational_name")
        raw_territory = _extract_mode_field(text, "territory")
        territory_code, territory_name, territory_order = _analysis_territory_meta(raw_territory)
        aliases = []
        aliases.extend(_extract_mode_list(text, "prompt_shape_signals", limit=6))
        aliases.extend(_extract_mode_list(text, "user_situation_signals", limit=4))
        lenses, unavailable_lenses = _mode_lens_picker_rows(mode_id, text, lens_index)

        rows.append({
            "id": mode_id,
            "display_name": display_name,
            "display_description": _mode_picker_description(text, educational_name),
            "educational_name": educational_name,
            "territory": territory_code,
            "territory_name": territory_name,
            "territory_order": territory_order,
            "aliases": aliases,
            "lenses": lenses,
            "unavailable_lenses": unavailable_lenses,
        })

    rows.sort(key=lambda r: (r["territory_order"], r["display_name"].lower()))
    return rows


@app.route("/api/frameworks/picker", methods=["GET"])
def frameworks_picker():
    """V3 Phase 2 — list of pickable frameworks for the input-box framework picker.

    Returns ``{ frameworks: [ {id, display_name, display_description,
    category, kind, ...}, ... ] }`` with one row per framework that declares both ``## Display Name`` and
    ``## Display Description`` sections. Pipeline-internal frameworks (F-* and
    Phase A) are silently excluded — they do not declare these fields.

    The picker UI consumes this directly; rows are pre-sorted by category then
    alphabetical Display Name. This endpoint is read-only and side-effect-free
    so it can be called freely on every picker open.
    """
    try:
        rows = list_pickable_frameworks()
    except Exception as exc:
        return _json_response({"frameworks": [], "error": str(exc)}, 503)
    return json.dumps({"frameworks": rows}), 200, {"Content-Type": "application/json"}


def _programming_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Programming request must be a JSON object")
    return payload


@app.route("/api/programming/plan", methods=["POST"])
def programming_plan():
    """Inspect a real repository and return material questions or one plan."""

    try:
        from programming import ProgrammingError, plan_programming
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    try:
        payload = _programming_payload()
        result = plan_programming(
            objective=str(payload.get("objective") or ""),
            repository_path=str(payload.get("repository_path") or ""),
            question_round=int(payload.get("question_round") or 0),
            answers=payload.get("answers") if isinstance(payload.get("answers"), list) else [],
        )
    except (ValueError, ProgrammingError) as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    return _json_response({"ok": True, **result})


@app.route("/api/programming/run", methods=["POST"])
def programming_run():
    """Execute one approved plan and stream milestone/review progress as NDJSON."""

    try:
        from programming import ProgrammingError, run_approved_programming
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    try:
        payload = _programming_payload()
        objective = str(payload.get("objective") or "")
        repository_path = str(payload.get("repository_path") or "")
        plan = payload.get("plan")
        approved = payload.get("approved") is True
        resume_branch = str(payload.get("resume_branch") or "") or None
        continuation = str(payload.get("continuation") or "")
        if not objective or not repository_path or not isinstance(plan, dict):
            raise ProgrammingError("objective, repository_path, and plan are required")
        if not approved:
            raise ProgrammingError("one explicit plan approval is required")
    except (ValueError, ProgrammingError) as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)

    @stream_with_context
    def generate():
        events = queue.Queue()
        finished = object()

        def emit(event):
            events.put(event)

        def work():
            try:
                result = run_approved_programming(
                    objective=objective,
                    repository_path=repository_path,
                    plan=plan,
                    approved=True,
                    progress=emit,
                    resume_branch=resume_branch,
                    continuation=continuation,
                )
                events.put({"type": "result", **result})
            except Exception as exc:
                events.put({"type": "error", "error": str(exc)})
            finally:
                events.put(finished)

        threading.Thread(target=work, daemon=True).start()
        while True:
            event = events.get()
            if event is finished:
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@app.route("/api/programming/recover", methods=["POST"])
def programming_recover():
    """Reconstruct the checked-out approved task from Git after a later session."""

    try:
        from programming import ProgrammingError, recover_programming
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    try:
        payload = _programming_payload()
        result = recover_programming(str(payload.get("repository_path") or ""))
    except (ValueError, ProgrammingError) as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    return _json_response({"ok": True, **result})


@app.route("/api/slash-commands", methods=["GET"])
def slash_commands_registry():
    """Read-only registry of user-facing slash commands.

    The registry includes server-dispatched commands, framework commands, and
    browser-only UI commands so autocomplete/help surfaces can use one source.
    """
    from slash_command_registry import registry_payload
    projects = None
    try:
        from orchestrator import project_registry as _pr
        projects = _pr.list_projects()
    except Exception:
        projects = None
    return json.dumps(registry_payload(projects=projects)), 200, {"Content-Type": "application/json"}


def _project_summary(project) -> dict:
    """Serialize a project-registry Project for browser management UI."""
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "interface": t.interface,
        }
        for t in sorted((project.tools or {}).values(), key=lambda x: x.name)
    ]
    slash_commands = [
        {
            "name": c.name,
            "command": "/" + c.name,
            "description": c.description,
            "interface": c.interface,
        }
        for c in sorted((project.slash_commands or {}).values(), key=lambda x: x.name)
    ]
    capability_slots = sorted((project.capability_slots or {}).keys())
    themes = [
        {"id": theme.id, "name": theme.name, "directory": theme.directory}
        for theme in sorted((project.themes or {}).values(), key=lambda x: x.id)
    ]
    framework_configurations = [
        {
            "framework": fc.framework,
            "profile_name": fc.profile_name,
            "overlays": [
                {
                    "extension_point": ov.extension_point,
                    "file": ov.file,
                }
                for ov in (fc.overlays or [])
            ],
        }
        for fc in (project.framework_configurations or [])
    ]
    framework_configurations.sort(
        key=lambda x: (x["framework"], x["profile_name"]),
    )
    return {
        "nexus": project.nexus,
        "name": project.name,
        "version": project.version,
        "description": project.description,
        "root": str(project.root),
        "tools": tools,
        "slash_commands": slash_commands,
        "frameworks": sorted(project.frameworks or []),
        "peds": sorted(project.peds or []),
        "workflow_specs": sorted(project.workflow_specs or []),
        "chromadb_collections": sorted(project.chromadb_collections or []),
        "capability_slots": capability_slots,
        "themes": themes,
        "framework_configurations": framework_configurations,
        "counts": {
            "tools": len(tools),
            "slash_commands": len(slash_commands),
            "frameworks": len(project.frameworks or []),
            "peds": len(project.peds or []),
            "workflow_specs": len(project.workflow_specs or []),
            "chromadb_collections": len(project.chromadb_collections or []),
            "capability_slots": len(capability_slots),
            "themes": len(themes),
            "framework_configurations": len(framework_configurations),
        },
    }


@app.route("/api/projects", methods=["GET"])
def api_projects_list():
    """Return registered Ora project plugins and their exposed surfaces."""
    try:
        from orchestrator import project_registry as _pr
        projects = _pr.list_projects()
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc), "projects": []}, 503)
    return _json_response({
        "ok": True,
        "projects": [_project_summary(p) for p in projects],
    })


@app.route("/api/active-project", methods=["GET"])
def api_active_project_get():
    """Return the active project nexus that new conversations bind to (G1.33).

    The expand-phase response carries a legacy-safe ``nexus`` plus the runtime
    ``canonical_nexus``. Commons therefore serializes as ``general`` / ``commons``.
    """
    try:
        from orchestrator import project_meta as _pm
        from orchestrator.active_project import (
            project_nexus_fields,
            repair_active_project_if_hidden,
        )

        def visible(nexus: str) -> bool:
            meta = _pm.read_project_meta(nexus)
            return bool(meta and meta.get("status") == "active")

        return _json_response({
            "ok": True,
            **project_nexus_fields(repair_active_project_if_hidden(visible)),
        })
    except Exception as exc:
        return _json_response(
            {
                "ok": False,
                "error": str(exc),
                "nexus": "general",
                "canonical_nexus": "commons",
            },
            503,
        )


def _repair_active_project_visibility():
    """Best-effort: hidden/missing active projects fall back to Commons now."""
    try:
        from orchestrator import project_meta as _pm
        from orchestrator.active_project import repair_active_project_if_hidden

        def visible(nexus: str) -> bool:
            meta = _pm.read_project_meta(nexus)
            return bool(meta and meta.get("status") == "active")

        return repair_active_project_if_hidden(visible)
    except Exception:
        return "commons"


@app.route("/api/active-project", methods=["POST"])
def api_active_project_set():
    """Set the active project. Body: ``{"nexus": "..."}`` ("commons"/legacy "general"/empty resets)."""
    try:
        from orchestrator import project_meta as _pm
        from orchestrator.active_project import (
            project_nexus_fields,
            set_active_project_if_visible,
        )
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    canonical_nexus = data.get("canonical_nexus")
    nexus = (
        canonical_nexus
        if isinstance(canonical_nexus, str) and canonical_nexus.strip()
        else data.get("nexus")
    )
    def visible(candidate: str) -> bool:
        meta = _pm.read_project_meta(candidate)
        return bool(meta and meta.get("status") == "active")

    selected = set_active_project_if_visible(nexus if isinstance(nexus, str) else "", visible)
    return _json_response({"ok": True, **project_nexus_fields(selected)})


@app.route("/api/projects/meta", methods=["GET"])
def api_projects_meta():
    """Switcher list (G1.33): Commons first, then projects by recency, each with
    conversation + unread counts so the switcher can badge cross-project
    activity (Commons == all-inclusive). Pass ``?status=active`` to filter.

    Each project also carries a ``matrix`` field with per-record Matrix
    diagnostics (state / classification / warnings / schema_valid) so one
    bad Matrix cannot fail the entire response.
    """
    try:
        from orchestrator import project_meta as _pm
        from orchestrator.active_project import project_nexus_fields
        projects = _pm.list_project_meta()
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc), "projects": []}, 503)
    status_filter = (request.args.get("status") or "").strip()
    if status_filter:
        projects = [
            p for p in projects
            if p.get("is_default") or p.get("status") == status_filter
        ]
    # Per-project conversation + unread counts (best-effort; Commons gets all).
    counts: dict = {}
    try:
        from conversation_memory import iter_conversations
        for r in iter_conversations():
            la, lr = r.get("last_activity_at"), r.get("last_read_at")
            unread = bool(la) and (not lr or la > lr)
            pids = [p for p in (r.get("project_ids") or []) if isinstance(p, str)]
            for t in ["commons", *pids]:
                c = counts.setdefault(t, {"conversation_count": 0, "unread_count": 0})
                c["conversation_count"] += 1
                if unread:
                    c["unread_count"] += 1
    except Exception:
        counts = {}
    # Lazy import of shared Matrix classifier for per-record diagnostics.
    try:
        from matrix_classifier import diagnose_matrix
    except ImportError:
        from orchestrator.matrix_classifier import diagnose_matrix
    for p in projects:
        canonical_nexus = p["nexus"]
        c = counts.get(canonical_nexus, {"conversation_count": 0, "unread_count": 0})
        p["conversation_count"] = c["conversation_count"]
        p["unread_count"] = c["unread_count"]
        p.update(project_nexus_fields(canonical_nexus))
        # Per-record Matrix diagnostics (failure-isolated).
        try:
            p["matrix"] = diagnose_matrix(
                canonical_nexus,
                p.get("folder_name"),
            )
        except Exception as exc:
            p["matrix"] = {
                "state": "invalid",
                "classification": None,
                "warnings": [f"Matrix diagnostic failed: {exc}"],
                "matrix_path": None,
                "schema_valid": False,
            }
    return _json_response({"ok": True, "projects": projects})


@app.route("/api/projects/create", methods=["POST"])
def api_projects_create():
    """Create a container project from a display name. Body: ``{"name": "..."}``.
    The vault project folder + graceful MOM run in the creation flow (later)."""
    try:
        from orchestrator import project_meta as _pm
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _json_response({"ok": False, "error": "name is required"}, 400)
    try:
        meta = _pm.create_project(name)
    except _pm.ProjectMetaError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    folder = _pm.ensure_project_folder(meta["folder_name"])  # best-effort
    storage_available = folder is not None
    storage_warning = None if storage_available else (
        "Project record created, but vault storage is unavailable. "
        "No project folder was created; configure or restore the vault before "
        "saving project files or an Operation-Matrix."
    )
    return _json_response({
        "ok": True,
        "project": meta,
        "vault_folder": str(folder) if folder else None,
        "storage_available": storage_available,
        "storage_warning": storage_warning,
    })


@app.route("/api/projects/<nexus>", methods=["POST"])
def api_projects_update(nexus):
    """Patch a project's record (name, defaults, status, …). Body: ``{field: value}``."""
    try:
        from orchestrator import project_meta as _pm
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    try:
        if "persona" in data:
            requested_persona = data.get("persona")
            if requested_persona not in (None, ""):
                if not isinstance(requested_persona, str):
                    raise ValueError("persona must be a Persona id or empty")
                available = {
                    item["id"] for item in _persona_mod().list_personas()["personas"]
                }
                if requested_persona.strip() not in available:
                    raise ValueError(f"unknown or malformed Persona: {requested_persona!r}")
                data["persona"] = requested_persona.strip()
        if "model_locks" in data:
            return _json_response({
                "ok": False,
                "error": "model_locks are runtime-authenticated and cannot be supplied directly",
            }, 400)
        if "default_model_profile" in data:
            from orchestrator import model_profiles as _mp
            requested_profile = data.get("default_model_profile")
            if isinstance(requested_profile, str) and requested_profile.strip():
                profile_name = requested_profile.strip()
                locks = _mp.capture_project_binding(profile_name, nexus)
            elif requested_profile in (None, ""):
                profile_name = None
                locks = {}
            else:
                raise _mp.ModelProfileError(
                    "default_model_profile must be a profile name or empty"
                )
            remaining = {
                key: value for key, value in data.items()
                if key != "default_model_profile"
            }
            # One pointer replacement binds the exact name+lock pair and all
            # unrelated Overview edits; a crash cannot expose half a binding.
            meta = _pm.set_project_model_binding(
                nexus, profile_name, locks, updates=remaining,
            )
        else:
            meta = _pm.update_project_meta(nexus, data)
    except (_pm.ProjectMetaError, ValueError) as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    if meta is None:
        return _json_response({"ok": False, "error": f"no project {nexus!r}"}, 404)
    if "status" in data:
        _repair_active_project_visibility()
    return _json_response({"ok": True, "project": meta})


@app.route("/api/projects/<nexus>/status", methods=["POST"])
def api_projects_set_status(nexus):
    """Set a project's status. Body: ``{"status": "active|inactive|archived"}``."""
    try:
        from orchestrator import project_meta as _pm
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    try:
        meta = _pm.set_project_status(nexus, status)
    except _pm.ProjectMetaError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    if meta is None:
        return _json_response({"ok": False, "error": f"no project {nexus!r}"}, 404)
    _repair_active_project_visibility()
    return _json_response({"ok": True, "project": meta})


@app.route("/api/projects/order", methods=["POST"])
def api_projects_reorder():
    """Set the user's project priority order. Body: ``{"order": [nexus, …]}``.

    The whole list is sent, not a single move, so ranks are always contiguous
    and the order on disk matches the order the user is looking at. Projects
    omitted from the list become unranked and sort after every ranked one.
    """
    try:
        from orchestrator import project_meta as _pm
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list):
        return _json_response(
            {"ok": False, "error": "order must be a list of project nexuses"}, 400)
    try:
        projects = _pm.reorder_projects([str(n) for n in order])
    except _pm.ProjectMetaError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    return _json_response({"ok": True, "projects": projects})


@app.route("/api/projects/<nexus>/rename-nexus", methods=["POST"])
def api_projects_rename_nexus(nexus):
    """Rename a project's nexus across the vault, conversations, and pointers
    (G1.33 sub-step 5). Body: ``{"new_nexus": str, "dry_run": bool}``.

    **Dry-run by default** — returns the impact report (which vault files +
    conversations would change) WITHOUT writing. Pass ``"dry_run": false`` to
    execute the cascade. Validation errors (reserved/invalid/colliding/missing)
    return 400."""
    try:
        from orchestrator import nexus_rename as _nr
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    new_nexus = (data.get("new_nexus") or "").strip()
    # Default to a preview; the caller must explicitly opt into writing.
    dry_run = data.get("dry_run", True) is not False
    try:
        report = _nr.rename_nexus(nexus, new_nexus, dry_run=dry_run)
    except _nr.NexusRenameError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    return _json_response({"ok": True, "report": report})


@app.route("/api/projects/<nexus>/mom", methods=["GET"])
def api_projects_mom_get(nexus):
    """Read a project's Mission/Objectives/Milestones from its vault
    Operation-Matrix file (G1.33 sub-step 5). The Matrix filename comes only
    from the record's persisted ``folder_name``; query parameters cannot choose
    a physical file. Resolution verifies frontmatter nexus ownership."""
    try:
        from orchestrator import operation_matrix as _om
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    try:
        from orchestrator import project_meta as _pm
        rec = _pm.read_project_meta(nexus)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    if rec is None:
        return _json_response({"ok": False, "error": f"no project {nexus!r}"}, 404)
    if rec.get("is_default"):
        return _json_response({"ok": True, "mom": _om.read_mom("commons")})
    folder_name = rec.get("folder_name")
    try:
        _pm.validate_folder_identity(folder_name, vault_root=_om.vault_root())
        mom = _om.read_mom(nexus, folder_name)
    except (_pm.ProjectStorageError, _om.MatrixError) as exc:
        return _json_response(
            {"ok": False, "migration_required": True, "error": str(exc)}, 409)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    mom["storage_available"] = _om.vault_root().is_dir()
    return _json_response({"ok": True, "mom": mom})


@app.route("/api/projects/<nexus>/mom", methods=["POST"])
def api_projects_mom_set(nexus):
    """Patch a project's MOM in its vault Operation-Matrix file. Body any of
    ``{"mission": str, "objectives": str, "milestones": [{text,done,indent}],
    "milestones_raw": str}``. Only provided sections are touched; everything
    else in the matrix file is preserved. Persisted project metadata supplies
    both physical ``folder_name`` and the human-facing H1 label."""
    try:
        from orchestrator import operation_matrix as _om
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    try:
        from orchestrator import project_meta as _pm
        rec = _pm.read_project_meta(nexus)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    if rec is None:
        return _json_response({"ok": False, "error": f"no project {nexus!r}"}, 404)
    if rec.get("is_default"):
        return _json_response(
            {"ok": False, "error": "Commons has no Operation-Matrix."}, 404)
    folder_name = rec.get("folder_name")
    try:
        _pm.validate_folder_identity(folder_name, vault_root=_om.vault_root())
    except (_pm.ProjectStorageError, _om.MatrixError) as exc:
        return _json_response(
            {"ok": False, "migration_required": True, "error": str(exc)}, 409)
    # Write gate: MOM writes require a schema-valid project_type declaration.
    # Every classification the MOM framework defines is writable — a Project's
    # checkbox milestones, an Operation's Appendix A prose milestones, and a
    # Passion's Practices / Directions of Travel are all edited here. What the
    # gate still refuses is an ABSENT or scalar project_type, because the
    # classification then cannot be trusted to pick the right milestone form.
    try:
        from matrix_classifier import classify_matrix as _cm_classify, schema_valid as _cm_schema_valid, InvalidProjectTypeError
    except ImportError:
        from orchestrator.matrix_classifier import classify_matrix as _cm_classify, schema_valid as _cm_schema_valid, InvalidProjectTypeError
    try:
        _m_path = _om.resolve_matrix_path(nexus, folder_name)
        if _m_path is not None:
            _m_text = _m_path.read_text(encoding="utf-8")
            _m_fm, _ = _om._split_frontmatter(_m_text)
            _m_class, _m_warns = _cm_classify(_m_fm, str(_m_path))
            if not _cm_schema_valid(_m_fm):
                return _json_response({
                    "ok": False,
                    "error": (
                        "MOM writes require an explicit list-form project_type in "
                        "the Matrix frontmatter (project, operation, passion, or "
                        f"incubator). Current classification is {_m_class!r} with "
                        "schema_valid=False. Add e.g. project_type:\\n  - project "
                        "to the Matrix file first."
                    ),
                    "write_gate": {
                        "classification": _m_class,
                        "schema_valid": False,
                        "warnings": _m_warns,
                    },
                }, 403)
    except InvalidProjectTypeError as exc:
        return _json_response({
            "ok": False,
            "error": f"Matrix classification invalid: {exc}",
            "write_gate": {
                "classification": None,
                "schema_valid": False,
                "warnings": [str(exc)],
            },
        }, 403)
    except Exception:
        pass  # If gate check fails for other reasons, let write_mom proceed.
    try:
        mom = _om.write_mom(
            nexus, folder_name,
            display_name=rec.get("display_name") or rec.get("name") or nexus,
            mission=data.get("mission"),
            objectives=data.get("objectives"),
            milestones=data.get("milestones"),
            milestones_raw=data.get("milestones_raw"),
        )
    except (_pm.ProjectStorageError, _om.MatrixError) as exc:
        return _json_response(
            {"ok": False, "migration_required": True, "error": str(exc)}, 409)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    if mom is None:
        return _json_response(
            {"ok": False, "storage_available": False,
             "error": "vault storage is unavailable; no Matrix file was created"}, 503)
    mom["storage_available"] = True
    return _json_response({"ok": True, "mom": mom})


# --- Small-model MOM assist (G1.33 sub-step 5) -----------------------------
# A read-only "Draft with AI" helper for the project modal's Mission & Goals
# tab. Grounded in the Mission-Objectives-Milestones (MOM) doctrine
# (Framework — Mission, Objectives, Milestones Clarification): Mission = the
# durable "why" (cycle-shaped Service Statement for going concerns); Objectives
# = strategic focal areas; Milestones = verifiable, cadence-specific checkpoints.
# It DRAFTS into the editable fields — it never writes the matrix (the human
# saves). Reuses the cheap "sidebar" slot via the same seam the rest of the
# server uses.

MOM_ASSIST_SYSTEM = """You draft a Mission-Objectives-Milestones (MOM) matrix for a single project. Follow this doctrine exactly.

MISSION is the strategic WHY — durable purpose, core essence, emotional drivers. NOT tasks, NOT dates, NOT deliverables. 2-4 sentences.

OBJECTIVES are the strategic focal areas the work is organized around. NOT milestones, NOT dated deliverables. A short list of focal areas.

MILESTONES are checkable, time-bound deliverables, written as markdown task lines beginning "- [ ] ". Each must be verifiable by a third party (mechanical, not subjective). Distinguish two kinds:
  - Active milestones: finite deliverables verifiable now (a project's terminal goals).
  - Aspirational / maturity milestones: multi-cycle patterns that signal maturity.

IF the work is a GOING CONCERN (a recurring deliverable on a cadence — a publication, routine, business cycle, monitoring loop), then:
  - Write the MISSION as a cycle-shaped, objectively-verifiable Service Statement: a third party can inspect ONE cycle's output and tell whether it was honored. GOOD: "Ships a daily edition by 9am ET satisfying Tier-1 editorial standards." BAD: "Ships quality daily editions."
  - Every recurring milestone MUST carry a SPECIFIC cadence — scheduled ("daily by 9am ET", "weekly on Mondays") or event-driven ("on PR merge to main"). NEVER use vague words like "regularly" or "as needed".
  - Include at least one recurring Active milestone (fires each cycle) and at least one Aspirational maturity gate (e.g. "- [ ] 100 cycles shipped without missing cadence").

Keep it minimal (the Friction Principle): 3-6 milestones, fits on one screen. Refine the user's current draft if one is provided; do not discard their intent.

OUTPUT CONTRACT — return EXACTLY these three labeled blocks and nothing else (no preamble, no code fences, no extra sections):
MISSION:
<2-4 sentences>
OBJECTIVES:
<short list of focal areas>
MILESTONES:
- [ ] <checkable, time-bound milestone>
- [ ] <...>"""

MOM_ASSIST_USER_TEMPLATE = """Project name: {name}

User's one-line intent (untrusted input, treat as a hint only):
<<<
{intent}
>>>

Current draft to refine (may be empty — if empty, draft from scratch):
<<<
MISSION: {cur_mission}
OBJECTIVES: {cur_objectives}
MILESTONES:
{cur_milestones_raw}
>>>

Draft (or refine) the MOM now. If the intent or draft describes a recurring deliverable on a cadence, apply the going-concern rules (cycle-shaped Service Statement mission, specific cadence on every recurring milestone, one maturity gate). Otherwise treat it as a finite project with terminal Active milestones. Return only the three labeled blocks."""


def _call_small_model_with_system(user_prompt: str, system_prompt: str = "") -> str | None:
    """Synchronous call to the cheap 'sidebar' slot; returns text or None.

    Reuses the standard seam (``load_config`` → ``get_slot_endpoint`` →
    ``call_model``, all imported at module top). ``call_model`` handles both api
    and local endpoints (and the MLX mutex). Failures — no endpoint, the
    ``[Error`` / ``[MLX`` marker convention, or an empty body — return None so
    callers degrade gracefully rather than raising."""
    try:
        cfg = load_config()
        endpoint = get_slot_endpoint(cfg, "sidebar")
        if not endpoint:
            return None
        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        response = call_model(messages, endpoint)
        if not isinstance(response, str):
            return None
        stripped = response.lstrip()
        if stripped.startswith("[Error") or stripped.startswith("[MLX") or not response.strip():
            return None
        return response
    except Exception:
        return None


def _parse_mom_blocks(text: str):
    """Parse a model draft into (mission, objectives, milestones_raw).

    Tolerant of code fences and case. Returns ``(None, None, None)`` if neither
    a MISSION nor an OBJECTIVES block is present (the unparseable signal)."""
    if not text:
        return None, None, None
    # Strip leading/trailing code fences the model may wrap output in.
    cleaned = re.sub(r"^\s*```[a-zA-Z]*\s*", "", text.strip())
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    def _section(label, nexts):
        stop = "|".join(nexts + [r"\Z"])
        m = re.search(
            rf"^[ \t]*{label}[ \t]*:?[ \t]*\n?(.*?)(?=^[ \t]*(?:{stop})\b|\Z)",
            cleaned, re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        return m.group(1).strip() if m else None

    mission = _section("MISSION", ["OBJECTIVES", "MILESTONES"])
    objectives = _section("OBJECTIVES", ["MILESTONES"])
    milestones = _section("MILESTONES", [])
    if mission is None and objectives is None:
        return None, None, None
    return (mission or ""), (objectives or ""), (milestones or "")


@app.route("/api/projects/<nexus>/mom-assist", methods=["POST"])
def api_projects_mom_assist(nexus):
    """Draft a project's MOM with the small 'sidebar' model (G1.33 sub-step 5).

    READ-ONLY: returns suggestions for the modal to fill into the editable
    fields; it never writes the matrix (the human reviews + saves). Body:
    ``{"intent": str?, "fields": {"mission","objectives",
    "milestones_raw"}?}``. Returns ``{ok, suggestions:{mission, objectives,
    milestones:[{text,done,indent}], milestones_raw}}``. Degrades to ok:false
    (503 model unavailable / 502 unparseable / 400 Commons) — never a 500."""
    try:
        from orchestrator import operation_matrix as _om
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    if (nexus or "").strip().lower() in ("", "commons", "general"):
        return _json_response(
            {"ok": False, "error": "Commons has no Operation-Matrix."}, 400)
    data = request.get_json(silent=True) or {}
    try:
        from orchestrator import project_meta as _pm
        rec = _pm.read_project_meta(nexus)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    if rec is None:
        return _json_response({"ok": False, "error": f"no project {nexus!r}"}, 404)
    name = rec.get("display_name") or rec.get("name") or nexus
    folder_name = rec.get("folder_name")
    try:
        _pm.validate_folder_identity(folder_name, vault_root=_om.vault_root())
    except _pm.ProjectStorageError as exc:
        return _json_response(
            {"ok": False, "migration_required": True, "error": str(exc)}, 409)
    intent = (data.get("intent") or "").strip()
    fields = data.get("fields") or {}
    cur_mission = (fields.get("mission") or "").strip()
    cur_objectives = (fields.get("objectives") or "").strip()
    cur_milestones_raw = (fields.get("milestones_raw") or "").strip()
    # If the user typed nothing, seed the refine context from the saved matrix.
    if not (cur_mission or cur_objectives or cur_milestones_raw):
        try:
            mom = _om.read_mom(nexus, folder_name)
            if mom and mom.get("exists"):
                cur_mission = mom.get("mission") or ""
                cur_objectives = mom.get("objectives") or ""
                cur_milestones_raw = mom.get("milestones_raw") or ""
        except _om.MatrixError as exc:
            return _json_response(
                {"ok": False, "migration_required": True, "error": str(exc)}, 409)
        except Exception:
            pass
    user_prompt = MOM_ASSIST_USER_TEMPLATE.format(
        name=name, intent=intent or "(none given)",
        cur_mission=cur_mission, cur_objectives=cur_objectives,
        cur_milestones_raw=cur_milestones_raw or "(none)",
    )
    # One-shot retry: small models occasionally wrap output or skip a label.
    mission = objectives = milestones_raw = None
    for _ in range(2):
        raw = _call_small_model_with_system(user_prompt, MOM_ASSIST_SYSTEM)
        if raw is None:
            return _json_response(
                {"ok": False, "error": "AI drafting is unavailable right now. "
                 "Fill the fields manually, or try again."}, 503)
        mission, objectives, milestones_raw = _parse_mom_blocks(raw)
        if mission is not None or objectives is not None:
            break
    if mission is None and objectives is None:
        return _json_response(
            {"ok": False, "error": "The assist returned an unreadable draft. "
             "Try again or fill manually."}, 502)
    parsed = _om.parse_milestones(milestones_raw or "")
    return _json_response({
        "ok": True,
        "suggestions": {
            "mission": (mission or "").strip(),
            "objectives": (objectives or "").strip(),
            "milestones": parsed,
            "milestones_raw": _om.render_milestones(parsed).strip(),
        },
    })


def _obsidian_uri_for(abs_path: str):
    """Build an ``obsidian://open`` URI for a vault-relative file, or None when
    the path is outside the vault. The frontend navigates to it to open the file
    in Obsidian (Q2: file management defers to Obsidian)."""
    try:
        from orchestrator import operation_matrix as _om
        from urllib.parse import quote
        from pathlib import Path as _P
        root = _om.vault_root().resolve()
        rel = _P(abs_path).resolve().relative_to(root)
    except Exception:
        return None
    return "obsidian://open?vault=" + quote(root.name) + "&file=" + quote(str(rel))


@app.route("/api/projects/<nexus>/files", methods=["GET"])
def api_projects_files(nexus):
    """Read-only index of a project's vault output destination (G1.33).

    File management defers to Obsidian (Q2 LOCKED) — each entry carries an
    ``obsidian_uri`` (open in Obsidian) and ``abs_path`` (reveal in Finder via
    POST /api/fs/reveal). The Operation-Matrix file is prepended as a pinned
    entry. A real project's output folder and Matrix filename always come from
    the record's immutable ``folder_name``; client-supplied names are ignored.
    Commons is synthetic and saves at the vault
    root, so its index is the vault root's direct files rather than a fictional
    ``Projects/Commons`` folder."""
    try:
        from orchestrator import project_meta as _pm
        from orchestrator import operation_matrix as _om
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    rec = _pm.read_project_meta(nexus)
    if rec is None:
        return _json_response({"ok": False, "error": f"no project {nexus!r}"}, 404)
    is_commons = bool(rec and rec.get("is_default"))
    folder_name = None if is_commons else rec.get("folder_name")
    try:
        if not is_commons:
            _pm.validate_folder_identity(folder_name, vault_root=_om.vault_root())
        index = _pm.list_project_files(None if is_commons else folder_name)
    except _pm.ProjectStorageError as exc:
        return _json_response(
            {"ok": False, "migration_required": True, "error": str(exc)}, 409)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    for f in index.get("files", []):
        f["obsidian_uri"] = _obsidian_uri_for(f["abs_path"])
    # Prepend the Operation-Matrix file as a pinned entry, if it exists.
    matrix = None
    if not is_commons:
        try:
            mpath = _om.resolve_matrix_path(nexus, folder_name)
            if mpath is not None:
                st = mpath.stat()
                from datetime import datetime as _dt
                matrix = {
                    "name": mpath.name,
                    "rel_path": mpath.name,
                    "abs_path": str(mpath),
                    "size": st.st_size,
                    "mtime": _dt.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                    "obsidian_uri": _obsidian_uri_for(str(mpath)),
                    "is_matrix": True,
                }
        except _om.MatrixError as exc:
            return _json_response(
                {"ok": False, "migration_required": True, "error": str(exc)}, 409)
        except Exception as exc:
            return _json_response({"ok": False, "error": str(exc)}, 500)
    return _json_response({"ok": True, "matrix": matrix, **index})


@app.route("/api/projects/<nexus>/conversations", methods=["GET"])
def api_projects_conversations(nexus):
    """List conversations for the project modal (membership + restore + add).

    Two modes:
      * **members** (default) — the project's own Dialogues. ``?include_closed=1``
        includes closed ones (the restore-closed browser). Commons (empty or
        legacy ``general`` nexus) is the all-inclusive view.
      * **candidates** (``?candidates=1``) — Dialogues NOT in this project, for the
        "add a Dialogue" search: title-filtered by ``?q=`` (case-insensitive
        substring), excludes closed, capped by ``?limit=`` (default 50, max 200),
        so the client never receives the full ~39k corpus.

    Rows carry ``closed`` + ``project_ids`` so the modal can restore (POST
    /api/conversation/<id>/restore) and edit membership safely."""
    try:
        from conversation_memory import iter_conversations
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    nexus_l = (nexus or "").strip().lower()
    all_projects = (not nexus_l) or nexus_l in ("commons", "general")
    candidates = (request.args.get("candidates") or "").strip().lower() in (
        "1", "true", "yes", "on")

    if candidates:
        # Threads to ADD: not already in this project, not closed, title-matched.
        if all_projects:
            # Commons contains everything — nothing to add.
            return _json_response({"ok": True, "conversations": []})
        q = (request.args.get("q") or "").strip().lower()
        try:
            limit = max(1, min(200, int(request.args.get("limit") or 50)))
        except (TypeError, ValueError):
            limit = 50
        try:
            rows = iter_conversations(include_closed=False)
        except Exception as exc:
            return _json_response({"ok": False, "error": str(exc)}, 500)
        out = []
        for r in rows:
            if nexus_l in (r.get("project_ids") or []):
                continue
            if r.get("is_welcome"):
                continue
            if q and q not in (r.get("title") or "").lower():
                continue
            out.append(r)
        out.sort(key=lambda r: (r.get("last_activity_at") or ""), reverse=True)
        return _json_response({"ok": True, "conversations": out[:limit]})

    include_closed = (request.args.get("include_closed") or "").strip().lower() in (
        "1", "true", "yes", "on")
    try:
        rows = iter_conversations(include_closed=include_closed)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    out = []
    for r in rows:
        if not all_projects and nexus_l not in (r.get("project_ids") or []):
            continue
        out.append(r)
    out.sort(key=lambda r: (r.get("last_activity_at") or ""), reverse=True)
    return _json_response({"ok": True, "conversations": out})


@app.route("/api/fs/reveal", methods=["POST"])
def api_fs_reveal():
    """Reveal a file in the OS file manager (Finder on macOS).

    Sandboxed: the path must resolve inside the vault root OR the Ora Exports /
    Ora Resources boundary folders (§2.8) — the only places Ora writes. Best-
    effort and macOS-only (cloud-ora is headless Linux → 501). Body:
    ``{"path": "..."}``."""
    try:
        from orchestrator import operation_matrix as _om
        from orchestrator import export as _export
        from pathlib import Path as _P
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    raw = (data.get("path") or "").strip()
    if not raw:
        return _json_response({"ok": False, "error": "path is required"}, 400)
    try:
        target = _P(raw).resolve()
        allowed_roots = [_om.vault_root().resolve()]
        try:
            allowed_roots += [
                _export.current_exports_dir().resolve(),
                _export.current_resources_dir().resolve(),
            ]
        except Exception:
            pass
        if not any(target == r or r in target.parents for r in allowed_roots):
            return _json_response(
                {"ok": False, "error": "path is outside the allowed folders"}, 403)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 400)
    if not target.exists():
        return _json_response({"ok": False, "error": "no such path"}, 404)
    if sys.platform != "darwin":
        return _json_response(
            {"ok": False, "error": "reveal-in-Finder is macOS-only"}, 501)
    try:
        import subprocess
        subprocess.run(["open", "-R", str(target)], check=False)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    return _json_response({"ok": True, "path": str(target)})


@app.route("/api/projects/register", methods=["POST"])
def api_projects_register():
    """Register a project plugin by root path. Body: {"root": "..."}."""
    try:
        from orchestrator import project_registry as _pr
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    root = (data.get("root") or data.get("path") or "").strip()
    if not root:
        return _json_response({"ok": False, "error": "root is required"}, 400)
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection = None
    try:
        from orchestrator import system_protection as _sp
        manifest_snapshot = _pr.load_project_snapshot(root)
        project = manifest_snapshot.project
        pointer = _pr._pointer_path(project.nexus)
        manifest = Path(project.root) / _pr.MANIFEST_FILENAME
        pointer_state = _sp.capture_path_identity(pointer)
        manifest_state = _sp.capture_path_identity(manifest)
        if manifest_state.get("content_digest") != manifest_snapshot.manifest_sha256:
            raise _pr.ManifestError(
                "project manifest changed while its registration identity was captured"
            )
        selectors = [
            _sp.path_selector(pointer), _sp.path_selector(manifest),
        ]
        pre_state = [pointer_state, manifest_state]
        protection = _sp.authorize_server_action(
            "project_register", selectors=selectors,
            params={
                "nexus": project.nexus, "root": str(project.root),
                "manifest_sha256": manifest_snapshot.manifest_sha256,
            },
            pre_state=pre_state,
        )
        with _sp.protected_effect(protection):
            project = _pr.register_project(
                root,
                expected_manifest_sha256=manifest_snapshot.manifest_sha256,
            )
        _sp.complete_execution(
            protection, ok=True,
            result={"registered": project.nexus, "root": str(project.root)},
            post_state=[
                _sp.capture_path_identity(pointer),
                _sp.capture_path_identity(manifest),
            ],
        )
    except Exception as exc:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(exc, _sp.SystemProtectionError):
                return _system_protection_error_response(exc)
            if protection is not None:
                _sp.complete_execution(
                    protection, ok=False, result={"error": type(exc).__name__},
                    post_state=[
                        _sp.capture_path_identity(pointer),
                        _sp.capture_path_identity(manifest),
                    ],
                )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)
        return _json_response({"ok": False, "error": str(exc)}, 400)
    return _json_response({"ok": True, "project": _project_summary(project)})


@app.route("/api/projects/<nexus>/unregister", methods=["POST", "DELETE"])
def api_projects_unregister(nexus):
    """Unregister a project plugin pointer by nexus."""
    try:
        from orchestrator import project_registry as _pr
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection = None
    try:
        from orchestrator import system_protection as _sp
        pointer = _pr._pointer_path(nexus)
        pre_state = _sp.capture_path_identity(pointer)
        protection = _sp.authorize_server_action(
            "project_unregister", selectors=[_sp.path_selector(pointer)],
            params={"nexus": nexus}, pre_state=[pre_state],
        )
        with _sp.protected_effect(protection):
            removed = _pr.unregister_project(nexus)
        _sp.complete_execution(
            protection, ok=removed, result={"removed": removed, "nexus": nexus},
            post_state=[_sp.capture_path_identity(pointer)],
        )
    except Exception as exc:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(exc, _sp.SystemProtectionError):
                return _system_protection_error_response(exc)
            if protection is not None:
                _sp.complete_execution(
                    protection, ok=False, result={"error": type(exc).__name__},
                    post_state=[_sp.capture_path_identity(pointer)],
                )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)
        return _json_response({"ok": False, "error": str(exc)}, 500)
    if removed:
        return _json_response({"ok": True})
    return _json_response({"ok": False, "error": "project not registered"}, 404)


@app.route("/api/analyses/picker", methods=["GET"])
def analyses_picker():
    """V3 Analyses picker: executable modes plus mode-scoped lenses.

    Lenses are exposed only as a second pass under a selected mode. The
    endpoint resolves lens ids against the runtime mental-model directory so
    renamed or missing lenses are not offered as clickable choices.
    """
    return _json_response({"modes": list_pickable_analysis_modes()})


@app.route("/api/document/process", methods=["POST"])
def document_process():
    """V3 Input Handling Phase 8 — accept a dropped/attached document.

    Body: ``multipart/form-data`` with field ``file``. Optional form
    fields: ``conversation_id``, ``tag`` (one of empty/private/stealth).

    The server stages conversation-owned files under
    ``~/ora/staging/documents/<conversation_id>/`` and
    spawns a background worker that converts to markdown, writes the
    result as an Incubator vault note tagged ``incubating`` (and
    ``private`` when applicable) or to a stealth temp dir. Returns
    ``{processing_id, source_path}`` immediately; clients listen on
    ``/api/document/stream`` for state events.
    """
    try:
        from orchestrator import document_input as _document_input
    except Exception as e:
        return _json_response({"error": f"document module unavailable: {e}"}, status=503)

    f = request.files.get("file")
    if f is None or not f.filename:
        return _json_response({"error": "file is required"}, status=400)

    conv = (request.form.get("conversation_id") or "").strip()
    if conv and not _valid_live_conversation_id(conv):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    requested_tag = _normalize_tag(request.form.get("tag", ""))

    def _document_envelope_available() -> bool:
        if not conv:
            return False
        try:
            from orchestrator.conversation_memory import load_conversation_json
            return load_conversation_json(conv) is not None
        except Exception as exc:
            print(f"[conversation-lifecycle] document envelope verification "
                  f"failed open for {conv}: {exc}",
                  file=sys.stderr, flush=True)
            return False

    def _document_failure(message: str, effective_tag: str):
        return _json_response({
            "error": message,
            "conversation_id": conv or None,
            "tag": effective_tag if conv else "",
            "envelope_created": envelope_created,
            "envelope_available": _document_envelope_available(),
        }, status=500)

    def _stage_and_start(effective_tag: str):
        safe_name = os.path.basename(f.filename or "upload").strip() or "upload"
        safe_name = re.sub(r"[\x00-\x1f\x7f]+", "_", safe_name)
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        staging_root = rp.ORA_HOME / "staging" / "documents"
        try:
            staging_dir = str(
                rp.safe_owned_subdir(staging_root, conv, create=True)
                if conv else rp.safe_owned_subdir(staging_root, create=True)
            )
        except Exception as exc:
            return None, None, _document_failure(
                f"staging setup failed: {exc}", effective_tag,
            )
        staged_path = os.path.join(staging_dir, f"{timestamp}-{safe_name}")
        try:
            _save_filestorage_no_follow(f, staged_path)
        except Exception as exc:
            return None, None, _document_failure(
                f"upload save failed: {exc}", effective_tag,
            )

        options: dict[str, str] = {"original_name": safe_name}
        if conv:
            options["conversation_id"] = conv
        if effective_tag:
            options["tag"] = effective_tag
        try:
            processing_id = _document_input.start(staged_path, options)
        except Exception as exc:
            try:
                os.remove(staged_path)
            except OSError:
                pass
            if conv:
                try:
                    os.rmdir(staging_dir)
                except OSError:
                    pass
            return None, None, _document_failure(
                f"start failed: {exc}", effective_tag,
            )
        return processing_id, staged_path, None

    if conv:
        with _conversation_lifecycle_lock(conv):
            if _is_conversation_deleted(conv):
                return _json_response({
                    "status": "deleted", "conversation_id": conv,
                }, status=410)
            try:
                tag, envelope_created = _ensure_artifact_conversation_envelope(
                    conv, requested_tag,
                )
            except Exception as exc:
                return _json_response({"error": str(exc)}, status=409)
            pid, staged_path, error_response = _stage_and_start(tag)
    else:
        envelope_created = False
        pid, staged_path, error_response = _stage_and_start("")
    if error_response is not None:
        return error_response

    envelope_available = _document_envelope_available()

    return _json_response({
        "processing_id": pid,
        "source_path": staged_path,
        "conversation_id": conv or None,
        "tag": tag if conv else "",
        "envelope_created": envelope_created,
        "envelope_available": envelope_available,
    })


@app.route("/api/document/<processing_id>/state", methods=["GET"])
def document_state(processing_id):
    try:
        from orchestrator.document_input import get_state as _doc_state
    except Exception as e:
        return _json_response({"error": f"document module unavailable: {e}"}, status=503)
    try:
        state = _doc_state(processing_id)
    except KeyError:
        return _json_response({"error": "unknown processing_id"}, status=404)
    return _json_response(state)


# In-process fanout for /api/document/stream subscribers. Mirrors the
# transcribe stream wiring above.
_document_subscribers_lock = threading.Lock()
_document_subscribers: list[_stdlib_queue.Queue] = []


def _document_fanout(event: dict) -> None:
    with _document_subscribers_lock:
        subs = list(_document_subscribers)
    for q in subs:
        try:
            q.put_nowait(event)
        except Exception:
            pass


# Wire the fanout exactly once at import time.
try:
    from orchestrator.document_input import subscribe as _doc_subscribe
    _doc_subscribe(_document_fanout)
except Exception as _e:  # pragma: no cover
    print(f"[server] document subscribe failed: {_e}")


@app.route("/api/document/stream")
def document_stream():
    """SSE stream for document processing events."""
    def generate():
        q = _stdlib_queue.Queue()
        with _document_subscribers_lock:
            _document_subscribers.append(q)
        try:
            yield "retry: 5000\n\n"
            while True:
                try:
                    event = q.get(timeout=15)
                except _stdlib_queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event.get('type', 'state')}\n"
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            with _document_subscribers_lock:
                if q in _document_subscribers:
                    _document_subscribers.remove(q)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/framework/analyze-inputs", methods=["POST"])
def framework_analyze_inputs():
    """V3 Input Handling Phase 7 — pre-flight gap check.

    Body (JSON)::

        {
            "framework_id": "<id>",
            "prompt": "<user's typed prompt>",
            "attachments": [{"name": "...", "type": "..."}, ...],
            "canvas_summary": "<one-line summary or empty>",
            "prior_responses": {"<question name>": "<user response>", ...}
        }

    Returns the gap report from ``framework_input_gap.analyze_framework_inputs``.
    The popup consumes this on every Enter (when a framework is set) and on
    every iteration round if the user filled in responses.
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return json.dumps({"error": "invalid json"}), 400

    framework_id = (data.get("framework_id") or "").strip()
    if not framework_id:
        return json.dumps({"error": "framework_id is required"}), 400

    prompt          = data.get("prompt") or ""
    attachments     = data.get("attachments") or []
    canvas_summary  = data.get("canvas_summary") or ""
    prior_responses = data.get("prior_responses") or {}

    try:
        from framework_input_gap import analyze_framework_inputs
    except Exception as e:
        return json.dumps({"error": f"analyzer unavailable: {e}"}), 500

    try:
        report = analyze_framework_inputs(
            framework_id=framework_id,
            prompt=prompt,
            attachments=attachments,
            canvas_summary=canvas_summary,
            prior_responses=prior_responses,
        )
    except Exception as e:
        return json.dumps({"error": f"analyze failed: {e}"}), 500

    return json.dumps(report), 200, {"Content-Type": "application/json"}


# Per-panel session state: raw log path, session id, pair counter
_session_data = {}


def _slug(text, max_words=5):
    words = re.sub(r'[^\w\s]', '', text.lower()).split()[:max_words]
    return '-'.join(words) if words else 'conversation'


# ---------------------------------------------------------------------------
# Phase 5.8 — Conversation chunk metadata helpers
# ---------------------------------------------------------------------------
# Implementations live in orchestrator/conversation_chunk.py (shared with
# the historical Path 2 emitter). Re-exported here so existing call sites
# and tests continue to work.

from orchestrator.conversation_chunk import (  # noqa: E402
    _extract_entities,
    _extract_keywords,
    _compute_pair_hash,
    _v3_tag_to_schema_tags,
    build_embedding_orientation,
    build_retrieval_document,
)
from orchestrator.historical.path2_orchestrator import MAX_EMBED_CHARS  # noqa: E402


def _generate_chunk_metadata(user_input, ai_response, date_str, panel_id, model_id, pair_num):
    """Generate contextual header and topic tags for a conversation chunk.

    Attempts to use the sidebar model for intelligent generation (per
    Conversation Processing Pipeline spec). Falls back to mechanical
    generation if the dispatch fails or returns nothing usable.

    Routes through `call_local_endpoint` from boot.py so the call works
    against either MLX (in-process, macOS Apple Silicon) or Ollama
    (HTTP, Win/Linux/Mac) — whichever the sidebar endpoint declares
    via its ``engine`` field. The previous implementation POSTed to
    ``{ep_url}/api/chat`` directly, which only worked for Ollama
    endpoints and silently failed for MLX endpoints.
    """
    # Try model-generated metadata via sidebar slot, routed through the
    # canonical engine dispatcher.
    try:
        cfg = load_config()
        sidebar_ep = get_slot_endpoint(cfg, "sidebar")
        if sidebar_ep:
            prompt = (
                f"Generate metadata for this conversation exchange.\n\n"
                f"User: {user_input[:500]}\n\n"
                f"Assistant: {ai_response[:500]}\n\n"
                f"Return exactly this format, nothing else:\n"
                f"HEADER: [2-3 sentences: what the exchange is about, what the user "
                f"was trying to accomplish, written for retrieval orientation]\n"
                f"TOPICS: [1-3 short topic phrases, comma-separated]"
            )
            from orchestrator.boot import call_local_endpoint
            raw = call_local_endpoint(
                [{"role": "user", "content": prompt}],
                sidebar_ep,
            )
            # call_local_endpoint returns "[Error...]" markers on failure;
            # treat those as fallback triggers.
            if raw and not raw.startswith("[Error") and not raw.startswith("[MLX"):
                header_match = re.search(r'HEADER:\s*(.+?)(?:\nTOPICS:|\Z)', raw, re.DOTALL)
                topics_match = re.search(r'TOPICS:\s*(.+)', raw)
                if header_match:
                    header = header_match.group(1).strip()
                    topics = []
                    if topics_match:
                        topics = [t.strip() for t in topics_match.group(1).split(",") if t.strip()][:3]
                    if len(header) > 30:
                        return header, topics
    except Exception:
        pass  # Fall through to mechanical generation

    # Mechanical fallback
    preview = user_input[:140].rstrip()
    if len(user_input) > 140:
        preview += "..."
    context_header = (
        f"Local AI session on {date_str}, panel '{panel_id}', model {model_id}. "
        f"Turn {pair_num} of an ongoing conversation. "
        f"The user asked: {preview}"
    )
    topics = [w for w in re.sub(r'[^\w\s]', '', user_input.lower()).split() if len(w) > 3][:3]
    return context_header, topics


# Stop-words filtered from topic slug generation
_STOP_WORDS = frozenset(
    "a an the this that these those is am are was were be been being have has had "
    "do does did will would shall should may might can could of in to for with on at "
    "by from as into about between through after before above below up down out off "
    "over under again further then once here there when where why how all each every "
    "both few more most other some such no nor not only own same so than too very "
    "and but or if while because until although since what which who whom whose "
    "i me my we our you your he him his she her it its they them their just also "
    "still already even much many well really quite also please help want need "
    "using make sure going like get know think".split()
)


def _topic_slug(user_input, ai_response, max_words=4):
    """Extract meaningful topic words from the exchange, filtering stop-words."""
    # Combine the first part of user input and first sentence of response
    combined = user_input[:300]
    if ai_response:
        # Grab the first substantive line from the response
        for line in ai_response.split('\n'):
            line = line.strip().lstrip('#').strip()
            if len(line) > 15:
                combined += " " + line[:200]
                break

    words = re.sub(r'[^\w\s]', '', combined.lower()).split()
    keywords = []
    seen = set()
    for w in words:
        if len(w) > 2 and w not in _STOP_WORDS and w not in seen:
            keywords.append(w)
            seen.add(w)
        if len(keywords) >= max_words:
            break
    return '-'.join(keywords) if keywords else 'conversation'


def _nomic_embed(text):
    """Embed text via the canonical embedding module (Ollama-backed).

    Routes through `orchestrator.embedding.get_embedding_function()`
    so the embedder is consistent with what the conversations
    collection itself uses. Cross-platform; Ollama runs on Win/Linux/Mac.
    Returns a list of floats, or None if Ollama is unreachable.
    """
    try:
        from orchestrator.embedding import get_embedding_function
        ef = get_embedding_function()
        result = ef([text])
        return list(result[0]) if result else None
    except Exception:
        return None


# V3 Phase 1.1 — conversation-level tag normalization. Mirrors the
# CONVERSATION_TAGS tuple in conversation_memory.py. Empty string is the
# default (standard mode); "stealth" and "private" carry the V3 mode
# semantics. Invalid values silently coerce to "" so a malformed request
# can never put a conversation into an unintended mode.
_VALID_CONVERSATION_TAGS = ("", "stealth", "private")


def _normalize_tag(raw) -> str:
    """Coerce a request-supplied tag value to a valid CONVERSATION_TAGS entry."""
    if not isinstance(raw, str):
        return ""
    val = raw.strip().lower()
    return val if val in _VALID_CONVERSATION_TAGS else ""


# V3 Phase 2 — track conversations that are currently mid-pipeline. The
# /api/conversations list endpoint reads this to surface the Pending group
# (conversations awaiting their next pipeline output). Set membership is
# updated by ``_invoke_pipeline.generate()`` via add-on-entry / remove-on-
# exit (try/finally so cleanup runs even on cancellation).
_pending_conversations: set[str] = set()


# Conversation lifecycle coordination. A Delete Forever request marks its
# tombstone before waiting for the per-conversation lock; writers then either
# finish before the purge or observe the tombstone and decline to create new
# artifacts. Locks are per ID, so unrelated conversations remain concurrent.
_conversation_lifecycle_guard = threading.RLock()
_conversation_lifecycle_locks: dict[str, threading.RLock] = {}
_conversation_creation_tags: dict[str, str] = {}
_deleted_conversations: set[str] = set()
_unreadable_conversations: set[str] = set()
_closed_conversations: set[str] = set()


def _valid_existing_conversation_id(conversation_id: str) -> bool:
    """Accept one safe direct child, including legacy punctuation IDs."""
    if not isinstance(conversation_id, str):
        return False
    value = conversation_id.strip()
    return bool(
        value and value not in {".", ".."} and len(value) <= 255
        and "\x00" not in value and "/" not in value and "\\" not in value
        and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    )


def _valid_live_conversation_id(conversation_id: str) -> bool:
    """Accept the portable, case-stable alphabet used by new writers.

    Conversation storage has to mean the same thing on case-sensitive and
    case-insensitive filesystems.  New IDs are therefore lowercase-only;
    legacy mixed-case IDs remain readable/deletable through
    ``_valid_existing_conversation_id``.
    """
    if not isinstance(conversation_id, str):
        return False
    return bool(
        conversation_id == conversation_id.strip()
        and 0 < len(conversation_id) <= 255
        and re.fullmatch(r"[a-z0-9_-]+", conversation_id)
    )


def _canonical_live_conversation_id(conversation_id: str) -> str:
    """Return a validated storage key verbatim; never lossy-sanitize it."""
    if not _valid_live_conversation_id(conversation_id):
        raise ValueError("invalid conversation_id")
    return conversation_id


def _conversation_storage_identity(conversation_id: str) -> str:
    """Return the cross-platform identity used by locks and tombstones.

    Case variants can name the same directory on Ora's supported default
    filesystems.  Treating them as one lifecycle identity prevents a legacy
    mixed-case delete from racing a lowercase writer against that directory.
    """
    return str(conversation_id or "").casefold()


def _assert_no_casefold_session_collision(conversation_id: str) -> None:
    """Reserve one case-insensitive session identity on every filesystem.

    New IDs are lowercase, but a legacy mixed-case session may already exist
    on a case-sensitive host.  Refuse to create the lowercase twin so Ora's
    Mac/Windows storage identity cannot split into two Linux directories.
    """
    from orchestrator.conversation_memory import _DEFAULT_SESSIONS_ROOT

    cid = _canonical_live_conversation_id(conversation_id)
    root = Path(_DEFAULT_SESSIONS_ROOT)
    if not root.exists():
        return
    if not root.is_dir():
        raise RuntimeError(f"sessions root is not a directory: {root}")
    target = root / cid
    if target.is_symlink():
        raise ValueError(
            f"conversation session path is a symlink: {target}",
        )
    if target.exists() and not target.is_dir():
        raise ValueError(
            f"conversation session path is not a directory: {target}",
        )
    if target.exists() and not rp.within_base(target.resolve(), root.resolve()):
        raise ValueError(
            f"conversation session path escapes the sessions root: {target}",
        )
    identity = _conversation_storage_identity(cid)
    try:
        for child in root.iterdir():
            if child.name != cid and child.name.casefold() == identity:
                raise ValueError(
                    f"conversation_id conflicts with legacy session "
                    f"{child.name!r}",
                )
    except OSError as exc:
        # Creation must not guess when the identity registry is unreadable.
        raise RuntimeError(
            f"could not verify conversation identity under {root}: {exc}",
        ) from exc


def _conversation_lifecycle_lock(conversation_id: str) -> threading.RLock:
    identity = _conversation_storage_identity(conversation_id)
    with _conversation_lifecycle_guard:
        lock = _conversation_lifecycle_locks.get(identity)
        if lock is None:
            lock = threading.RLock()
            _conversation_lifecycle_locks[identity] = lock
        return lock


def _is_conversation_deleted(conversation_id: str) -> bool:
    with _conversation_lifecycle_guard:
        return _conversation_storage_identity(conversation_id) in _deleted_conversations


def _is_conversation_closed(conversation_id: str) -> bool:
    identity = _conversation_storage_identity(conversation_id)
    with _conversation_lifecycle_guard:
        cached = identity in _closed_conversations
    try:
        from orchestrator.conversation_memory import load_conversation_json
        envelope = load_conversation_json(conversation_id)
    except Exception as exc:
        print(f"[conversation-lifecycle] closed-state read failed; using cache for "
              f"{conversation_id}: {exc}", file=sys.stderr, flush=True)
        return cached
    if not isinstance(envelope, dict):
        return cached
    closed = bool(envelope.get("closed"))
    with _conversation_lifecycle_guard:
        if closed:
            _closed_conversations.add(identity)
        else:
            _closed_conversations.discard(identity)
    return closed


def _configured_conversation_chromadb_path() -> str:
    """Resolve the same Chroma root used by conversation saves."""
    try:
        config = load_config() or {}
        value = config.get("chromadb_path") if isinstance(config, dict) else None
        return os.path.abspath(os.path.expanduser(
            value or os.path.join(WORKSPACE, "chromadb")
        ))
    except Exception as exc:
        fallback = os.path.abspath(os.path.join(WORKSPACE, "chromadb"))
        print(f"[conversation-lifecycle] config read failed; using {fallback}: "
              f"{exc}", file=sys.stderr, flush=True)
        return fallback


def _cross_site_mutation_response():
    """Reject browser cross-site mutation attempts against localhost APIs.

    Headerless local CLI/tests remain supported. Browsers send either Origin
    or Sec-Fetch-Site on form/fetch POSTs, so an unrelated web page cannot
    trigger permanent deletion merely by guessing a conversation id.
    """
    fetch_site = (request.headers.get("Sec-Fetch-Site") or "").lower()
    if fetch_site == "cross-site":
        return json.dumps({"error": "cross-site lifecycle request rejected"}), 403
    origin = (request.headers.get("Origin") or "").strip()
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != request.host:
            return json.dumps({"error": "cross-origin lifecycle request rejected"}), 403
    except Exception:
        return json.dumps({"error": "invalid Origin header"}), 403
    return None


def _effective_conversation_tag(conversation_id: str, requested_tag="") -> str:
    """Resolve the immutable creation tag or authoritative envelope tag.

    An existing envelope always wins, including an explicitly Standard empty
    tag. Only a genuinely missing envelope may accept a request's creation
    tag. The first request for a missing envelope wins until persistence lands.
    """
    requested = _normalize_tag(requested_tag)
    identity = _conversation_storage_identity(conversation_id)
    try:
        from orchestrator.conversation_memory import (
            get_conversation_tag,
            load_conversation_json,
            _conversation_path,
            _DEFAULT_SESSIONS_ROOT,
        )
        # Preserve the established lookup seam used by trace/direct callers:
        # a non-Standard persisted tag is a stronger request candidate.  The
        # full envelope read below remains authoritative (including an
        # explicitly Standard empty tag, which this shorthand cannot
        # distinguish from a missing envelope).
        persisted_hint = _normalize_tag(get_conversation_tag(conversation_id))
        if persisted_hint:
            requested = persisted_hint
        envelope = load_conversation_json(conversation_id)
    except Exception as exc:
        print(f"[conversation-lifecycle] tag lookup failed for "
              f"{conversation_id}: {exc}", flush=True)
        envelope = None

    if isinstance(envelope, dict):
        stored = envelope.get("tag", "")
        authoritative = stored if stored in _VALID_CONVERSATION_TAGS else ""
        with _conversation_lifecycle_guard:
            _conversation_creation_tags.pop(identity, None)
            _unreadable_conversations.discard(identity)
        return authoritative

    # ``load_conversation_json`` intentionally returns None for both missing
    # and unreadable files. Existing-but-corrupt state is not a new Dialogue:
    # accepting a request-supplied Standard tag could make a Private/Stealth
    # conversation persist in clear form. Keep execution available but use
    # the non-persistent Stealth behavior and report the corruption loudly.
    try:
        envelope_path = _conversation_path(
            conversation_id, _DEFAULT_SESSIONS_ROOT,
        )
        if envelope_path.exists() or envelope_path.is_symlink():
            with _conversation_lifecycle_guard:
                _unreadable_conversations.add(identity)
            print(f"[conversation-lifecycle] unreadable existing envelope "
                  f"{envelope_path}; treating as Stealth until repaired",
                  file=sys.stderr, flush=True)
            return "stealth"
        with _conversation_lifecycle_guard:
            _unreadable_conversations.discard(identity)
    except Exception as exc:
        print(f"[conversation-lifecycle] envelope existence check failed for "
              f"{conversation_id}: {exc}", file=sys.stderr, flush=True)

    with _conversation_lifecycle_guard:
        return _conversation_creation_tags.setdefault(identity, requested)


@contextmanager
def _conversation_turn_context(
    conversation_id: str,
    requested_tag: str = "",
    *,
    trace_dir: str | None = None,
):
    """Scope lifecycle-sensitive context for clarification turn seams."""
    turn_tag = _effective_conversation_tag(conversation_id, requested_tag)
    boot_context = _boot_context_api()
    tag_token = boot_context.set_conversation_tag_context(turn_tag)
    trace_token = boot_context.set_turn_trace_context(trace_dir)
    scope = nullcontext()
    try:
        try:
            from orchestrator.oversight_events import lifecycle_context_scope
            scope = lifecycle_context_scope(
                stealth=turn_tag == "stealth",
                conversation_id=conversation_id,
                tool_context={
                    "trace_dir": trace_dir,
                    "surface": "chat",
                    "risk_tier": None,
                },
            )
        except Exception as exc:
            print(
                f"[conversation-lifecycle] turn context unavailable for "
                f"{conversation_id}: {exc}", file=sys.stderr, flush=True,
            )
        with scope:
            yield turn_tag
    finally:
        boot_context.reset_turn_trace_context(trace_token)
        boot_context.reset_conversation_tag_context(tag_token)


def _ensure_artifact_conversation_envelope(
    conversation_id: str,
    tag: str,
) -> tuple[str, bool]:
    """Durably bind a pre-turn server artifact to its Dialogue.

    Returns ``(effective_tag, created)``. Callers already hold the server's
    per-conversation lifecycle lock, so the envelope and the artifact are one
    deletion/privacy unit from the perspective of concurrent requests.
    """
    _assert_no_casefold_session_collision(conversation_id)
    if _is_conversation_closed(conversation_id):
        raise RuntimeError("conversation is closed")
    effective_tag = _effective_conversation_tag(conversation_id, tag)
    from orchestrator.conversation_memory import (
        ensure_conversation_envelope,
        _conversation_path,
        _DEFAULT_SESSIONS_ROOT,
    )
    envelope_path = _conversation_path(conversation_id, _DEFAULT_SESSIONS_ROOT)
    existed = envelope_path.exists() or envelope_path.is_symlink()
    project_ids = None
    if not existed:
        try:
            from orchestrator.active_project import (
                get_active_project,
                resolve_project_ids,
            )
            project_ids = resolve_project_ids(get_active_project())
        except Exception as exc:
            print(f"[conversation-lifecycle] artifact project binding failed "
                  f"open for {conversation_id}: {exc}",
                  file=sys.stderr, flush=True)
    path = ensure_conversation_envelope(
        conversation_id,
        tag=effective_tag,
        project_ids=project_ids,
    )
    if path is None:
        print(
            f"[conversation-lifecycle] artifact for {conversation_id} is "
            "proceeding without a durable envelope; lifecycle recovery is "
            "degraded",
            file=sys.stderr,
            flush=True,
        )
        return effective_tag, False
    with _conversation_lifecycle_guard:
        identity = _conversation_storage_identity(conversation_id)
        _conversation_creation_tags.pop(identity, None)
        _unreadable_conversations.discard(identity)
        _closed_conversations.discard(identity)
    return effective_tag, not existed


# ── V3 Backlog 2A Chunk 1: Pre-pipeline submission log ──────────────────────
#
# Every user submission is captured to disk BEFORE any other processing.
# A user input must never be lost — not to a crash, not to a validation
# error, not to a thrown exception. The pending file is the recoverable
# record. On successful pipeline completion, the file is moved to
# ``processed/`` (audit history). On server crash, the file persists and
# the next boot scans for orphans, surfacing them as errored chunks the
# user can retry / dismiss via the existing Item 11 controls.
#
# Layout under ``CONVERSATIONS_RAW``:
#   pending/<submission_id>.json    — captured at submit, deleted on success
#   processed/<submission_id>.json  — moved here after the chunk file lands
#
# ``submission_id`` is ``<UTC ISO compact>-<8-char uuid>`` so it sorts
# chronologically and is unique even under simultaneous submissions.

CONVERSATIONS_PENDING   = os.path.join(CONVERSATIONS_RAW, "pending")
CONVERSATIONS_PROCESSED = os.path.join(CONVERSATIONS_RAW, "processed")


def _new_submission_id() -> str:
    """Stable, sortable, unique id for a submission log file."""
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def _log_pending_submission(payload: dict, submission_id: str | None = None) -> str:
    """Write a submission to ``pending/`` immediately at handler entry.

    Called BEFORE any other processing — before validation, before parsing,
    before any error path that could 400. Returns the ``submission_id``
    the caller threads into ``_invoke_pipeline`` for later finalization.

    On any I/O failure, returns an empty string and prints a warning. Legacy
    callers retain their historical best-effort behavior. Atomic visual
    submits treat an empty return as a hard stop because this pending file is
    the commit marker that authorizes the model call.
    """
    submission_id = submission_id or _new_submission_id()
    try:
        os.makedirs(CONVERSATIONS_PENDING, exist_ok=True)
        body = dict(payload)
        body["submission_id"] = submission_id
        body.setdefault("captured_at", datetime.utcnow().isoformat() + "Z")
        path = os.path.join(CONVERSATIONS_PENDING, f"{submission_id}.json")
        rp.atomic_write_text(
            path,
            json.dumps(body, ensure_ascii=False, indent=2, default=str),
        )
        return submission_id
    except Exception as e:
        print(f"[WARNING] _log_pending_submission failed: {e}")
        return ""


def _finalize_pending_submission(submission_id: str) -> None:
    """Move a pending submission to ``processed/`` after successful save.

    Called from the daemon thread that runs ``_save_conversation`` once the
    chunk file is on disk and ChromaDB is indexed. If the move fails, we
    leave the file in ``pending/`` — better a duplicate errored-chunk on
    next boot than a silent loss of the audit trail.
    """
    if not submission_id:
        return
    try:
        os.makedirs(CONVERSATIONS_PROCESSED, exist_ok=True)
        src = os.path.join(CONVERSATIONS_PENDING, f"{submission_id}.json")
        dst = os.path.join(CONVERSATIONS_PROCESSED, f"{submission_id}.json")
        if os.path.exists(src):
            shutil.move(src, dst)
    except Exception as e:
        print(f"[WARNING] _finalize_pending_submission({submission_id}) failed: {e}")


def _delete_pending_submission(submission_id: str) -> None:
    """Remove a pending submission that was rejected at validation time.

    Called from the handler 400 paths (empty input, malformed JSON, etc.)
    where the submission was never accepted into the pipeline. We do NOT
    want these to surface as errored chunks on next boot — the user
    received an immediate 4xx response and will know the submit failed.
    """
    if not submission_id:
        return
    try:
        path = os.path.join(CONVERSATIONS_PENDING, f"{submission_id}.json")
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"[WARNING] _delete_pending_submission({submission_id}) failed: {e}")


def _scan_orphaned_pending_submissions() -> int:
    """At server startup, find pending submissions that didn't complete.

    Each orphan becomes an errored chunk in the user's conversation list,
    surfaced in the Errored group with the existing Item 11 retry / dismiss
    controls. The pending file is then moved to ``processed/`` so we don't
    re-surface it on the next boot.

    Returns the count of orphans surfaced.
    """
    count = 0
    try:
        if not os.path.isdir(CONVERSATIONS_PENDING):
            return 0
        files = sorted(os.listdir(CONVERSATIONS_PENDING))
    except Exception as e:
        print(f"[WARNING] _scan_orphaned_pending_submissions list failed: {e}")
        return 0

    for fname in files:
        if not fname.endswith(".json"):
            continue
        path = os.path.join(CONVERSATIONS_PENDING, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            print(f"[WARNING] orphan parse failed for {fname}: {e}")
            continue

        try:
            _surface_orphan_as_errored_chunk(payload)
            os.makedirs(CONVERSATIONS_PROCESSED, exist_ok=True)
            shutil.move(path, os.path.join(CONVERSATIONS_PROCESSED, fname))
            count += 1
        except Exception as e:
            print(f"[WARNING] orphan recovery failed for {fname}: {e}")

    if count:
        print(f"[startup] surfaced {count} interrupted submission(s) as errored chunks")
    return count


def _surface_orphan_as_errored_chunk(payload: dict) -> None:
    """Surface an interrupted submission to the user as an errored row.

    Two-track recovery:

    1. **Chunk-file audit trail** at ``CONVERSATIONS_DIR`` carrying the
       Backlog 2D errored shape (``status: errored`` YAML + ``## Failure``
       + ``## Recommendation`` body) so the failure is durable on disk.
    2. **Envelope marker** at ``~/ora/sessions/<id>/conversation.json`` —
       creates the envelope if missing, sets ``last_status: errored``,
       writes the original prompt to ``interrupted_input`` so the
       existing Item 11 retry endpoint can re-submit it. The sidebar
       Errored group is driven off this envelope flag.
    """
    conversation_id = (
        payload.get("conversation_id")
        or payload.get("panel_id")
        or "main"
    )
    panel_id      = payload.get("panel_id") or conversation_id
    user_input    = payload.get("user_input") or "(no input recorded)"
    captured_at   = payload.get("captured_at") or datetime.utcnow().isoformat() + "Z"
    submission_id = payload.get("submission_id") or "unknown"
    tag           = _normalize_tag(payload.get("tag", ""))

    failure_summary = (
        "Server interrupted before pipeline completed. Your submission was "
        "captured to disk and recovered on restart."
    )
    recommendation = (
        "Click **Retry** to re-run this submission, or **Dismiss** to discard "
        "it. The original prompt is preserved on the conversation envelope "
        "so retry will resubmit exactly what you typed."
    )

    # Track 1 — durable chunk file for audit / direct inspection.
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M")
    slug     = _slug(user_input) or "interrupted"
    fname    = f"{date_str}_{time_str}_recovered_{submission_id[:14]}_{slug}.md"
    fpath    = os.path.join(CONVERSATIONS_DIR, fname)

    yaml_block = (
        "---\n"
        f"session_id: recovered-{submission_id[:8]}\n"
        f"pair_num: 0\n"
        f"timestamp: {now.isoformat(timespec='seconds')}\n"
        f"captured_at: {captured_at}\n"
        f"submission_id: {submission_id}\n"
        f"panel_id: {panel_id}\n"
        f"conversation_id: {conversation_id}\n"
        f"tag: {tag}\n"
        "status: errored\n"
        "recovery: orphan_pending\n"
        "---\n"
    )
    body = (
        f"# Interrupted submission — recovered on restart\n\n"
        f"## Failure\n\n{failure_summary}\n\n"
        f"## Recommendation\n\n{recommendation}\n\n"
        f"## Original prompt\n\n{user_input}\n"
    )
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(yaml_block + body)
    except Exception as e:
        print(f"[WARNING] _surface_orphan_as_errored_chunk write failed: {e}")

    # Track 2 — envelope marker so the row surfaces in the sidebar.
    try:
        from conversation_memory import (
            load_conversation_json,
            mark_conversation_errored,
            _conversation_path,
            _DEFAULT_SESSIONS_ROOT,
        )
    except Exception as e:
        print(f"[WARNING] orphan envelope marker imports failed: {e}")
        return

    # Ensure the envelope exists. If the user crashed mid-first-submit on a
    # brand-new conversation, no envelope was ever written; create a minimal
    # one carrying just the tag + interrupted_input. Existing envelopes are
    # left intact (immutability of prior turns).
    env_path = _conversation_path(conversation_id, _DEFAULT_SESSIONS_ROOT)
    existing = load_conversation_json(conversation_id)
    if existing is None:
        try:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            envelope = {
                "conversation_id": conversation_id,
                "display_name":    user_input[:60].strip() or "Recovered submission",
                "tag":             tag,
                "messages":        [],
                "created_at":      captured_at,
            }
            env_path.write_text(
                json.dumps(envelope, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[WARNING] orphan envelope create failed: {e}")
            return

    # Stamp the envelope with the interrupted-input field so retry
    # re-submits the original prompt verbatim.
    try:
        data = load_conversation_json(conversation_id) or {}
        data["interrupted_input"]    = user_input
        data["interrupted_at"]       = captured_at
        data["interrupted_submission_id"] = submission_id
        visual_checkpoint_id = payload.get("visual_checkpoint_id")
        canvas_preview_path = payload.get("canvas_preview_path")
        if (isinstance(visual_checkpoint_id, str)
                and _VISUAL_CHECKPOINT_ID_RE.fullmatch(visual_checkpoint_id)
                and isinstance(canvas_preview_path, str)
                and os.path.isfile(canvas_preview_path)
                and not os.path.islink(canvas_preview_path)):
            data["interrupted_visual_checkpoint_id"] = visual_checkpoint_id
        env_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[WARNING] orphan interrupted_input write failed: {e}")

    # Flip last_status → errored so the sidebar groups it correctly.
    try:
        mark_conversation_errored(conversation_id, failure_summary)
    except Exception as e:
        print(f"[WARNING] orphan mark_errored failed: {e}")


def _resolve_chunk_destination(output_destination: str) -> str:
    """Resolve a caller-supplied chunk output folder, falling back to the
    default ``CONVERSATIONS_DIR`` on any problem.

    Returns the absolute path the chunk should be written to. The raw audit
    log and pending/processed submission folders are unaffected — those
    always live under ``CONVERSATIONS_RAW``.

    Fallback rules (per Obsidian Plugin Design §"Implementation"):
      * empty / missing                → default
      * not an absolute path after expanduser → default + warning
      * path exists but is not a directory   → default + warning
      * path doesn't exist and can't be created → default + warning
      * path exists but isn't writable        → default + warning
    """
    if not output_destination:
        return CONVERSATIONS_DIR
    candidate = os.path.expanduser(output_destination.strip())
    if not candidate:
        return CONVERSATIONS_DIR
    try:
        if not os.path.isabs(candidate):
            print(f"[WARNING] output_destination not absolute, ignoring: {output_destination!r}")
            return CONVERSATIONS_DIR
        if os.path.exists(candidate):
            if not os.path.isdir(candidate):
                print(f"[WARNING] output_destination exists but is not a directory: {candidate}")
                return CONVERSATIONS_DIR
        else:
            os.makedirs(candidate, exist_ok=True)
        if not os.access(candidate, os.W_OK):
            print(f"[WARNING] output_destination not writable: {candidate}")
            return CONVERSATIONS_DIR
        return candidate
    except Exception as e:
        print(f"[WARNING] output_destination resolution failed ({output_destination!r}): {e}")
        return CONVERSATIONS_DIR


def _save_conversation_unlocked(user_input, ai_response, panel_id,
                                is_new_session, tag="",
                                output_destination="", trace_ref=None):
    """
    Three steps, all inline, immediately after every response:

    1. Append prompt-response pair to the session's raw log in
       ~/Documents/conversations/raw/  (audit trail, one file per session)

    2. Write a processed chunk file to ~/Documents/conversations/
       (YAML frontmatter + contextual header + exchange body, one file per pair)
       Filename: YYYY-MM-DD_HH-MM_session-[id]_pair-[NNN]_[topic-slug].md

    3. For Standard and Private only, index the processed chunk into the
       ChromaDB "conversations" collection through the machine-specific
       embedding profile in config/chromadb.json (tracked fresh-install
       fallback: Ollama BGE-M3 at 1,024 dimensions; embedding input = header +
       user prompt only, per the Conversation Processing Pipeline spec)

    V3 Phase 1.2: ``tag`` (one of CONVERSATION_TAGS — empty / stealth /
    private) is denormalized into the chunk's ChromaDB metadata under the
    same key, so RAG queries can filter on conversation-level mode without
    joining against conversation.json. The conversation.json envelope is
    the source of truth: Stealth is fixed at creation, while explicit
    Standard/Private lifecycle mutations propagate into this denormalized
    cache.

    Obsidian Plugin Design (2026-05-17): ``output_destination`` is an
    optional per-request override for the processed chunk folder. Empty /
    missing / invalid falls back to ``CONVERSATIONS_DIR`` per
    ``_resolve_chunk_destination``. The raw audit log stays at
    ``CONVERSATIONS_RAW`` regardless — that's audit infrastructure, not
    user-facing output.

    Trace manifest (Chunk 0): ``trace_ref`` is the turn's trace-store ref
    ("<conversation_id>/<turn_timestamp>", relative to the pipeline-traces
    root), recorded on the conversation-manifest line so any saved turn
    resolves mechanically to its trace dir. ``None`` for stealth/untraced
    turns by construction.
    """
    if _is_conversation_deleted(panel_id):
        print(f"[conversation-lifecycle] skipped save for deleted "
              f"conversation {panel_id}", flush=True)
        return None
    tag = _effective_conversation_tag(panel_id, tag)
    chunk_dir = _resolve_chunk_destination(output_destination)
    os.makedirs(CONVERSATIONS_RAW, exist_ok=True)
    os.makedirs(chunk_dir, exist_ok=True)

    now      = datetime.now()
    ts_iso   = now.isoformat(timespec='seconds')
    ts_str   = now.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M")

    cfg      = load_config()
    endpoint = get_endpoint(cfg) or {}
    model_id = endpoint.get("name", "unknown")

    # ── Init session on first pair ────────────────────────────────────────────
    if is_new_session or panel_id not in _session_data:
        session_id   = uuid.uuid4().hex
        raw_name     = (
            f"{date_str}_{time_str}_session-{session_id}_"
            f"{_slug(user_input)}.md"
        )
        _session_data[panel_id] = {
            "raw_path":   os.path.join(CONVERSATIONS_RAW, raw_name),
            "session_id": session_id,
            "pair_count": 0,
            "model":      model_id,
            "start":      ts_str,
            # Phase 5.8 — thread continuity tracking
            "first_user_input":  user_input,
            "prior_topic":       None,
            "thread_counter":    0,
        }

    sess       = _session_data[panel_id]

    # Fill in raw_path if early-initialized by generate() without it
    if not sess.get("raw_path"):
        raw_name = (
            f"{date_str}_{time_str}_session-{sess['session_id']}_"
            f"{_slug(user_input)}.md"
        )
        sess["raw_path"] = os.path.join(CONVERSATIONS_RAW, raw_name)
    if "first_user_input" not in sess:
        sess["first_user_input"] = user_input
    sess.setdefault("prior_topic", None)
    sess.setdefault("thread_counter", 0)
    sess["pair_count"] += 1
    pair_num   = sess["pair_count"]
    session_id = sess["session_id"]

    # ── Step 1: Append to raw session log ────────────────────────────────────
    is_new_file = not os.path.exists(sess["raw_path"])
    with open(sess["raw_path"], "a", encoding="utf-8") as f:
        if is_new_file:
            f.write(
                f"# Session {session_id}\n\n"
                f"session_start: {sess['start']}\n"
                f"panel_id: {panel_id}\n"
                f"model: {sess['model']}\n"
                f"source_platform: local\n"
                f"tag: {tag}\n"
                f"tag_private: {'true' if tag == 'private' else 'false'}\n\n"
                f"---\n"
            )
        f.write(
            f"\n<!-- pair {pair_num:03d} | {ts_str} -->\n\n"
            f"**User:** {user_input}\n\n"
            f"**Assistant:** {ai_response}\n\n"
            f"---\n"
        )

    # ── Step 2: Write processed chunk file (Schema §12 chunk template) ──────
    # Generate contextual header and topic tags via sidebar model (per spec).
    # Falls back to mechanical generation if model call fails or is too slow.
    context_header, topics = _generate_chunk_metadata(
        user_input, ai_response, date_str, panel_id, model_id, pair_num
    )
    topic_primary = topics[0] if topics else ""

    # Thread-id continuity (Phase 5.8): increment when topic_primary
    # changes from the prior turn. Conversation_id-prefixed for uniqueness.
    if topic_primary != sess.get("prior_topic"):
        sess["thread_counter"] = int(sess.get("thread_counter", 0)) + 1
    sess["prior_topic"] = topic_primary
    thread_counter = sess["thread_counter"]
    thread_id = f"thread_{(panel_id or '')[:8]}_{thread_counter:03d}"

    topic_slug = _topic_slug(user_input, ai_response)
    chunk_id   = f"session-{session_id}-pair-{pair_num:03d}"
    chunk_name = f"{chunk_id}_{date_str}_{time_str}_{topic_slug}.md"
    chunk_path = os.path.join(chunk_dir, chunk_name)

    # Phase 5.8: chunk YAML follows Schema §12 conversation chunk template.
    # nexus, type: chat, tags, dates — no bespoke fields. Bespoke values
    # (session_id, model_id, source_platform, etc.) move to ChromaDB
    # metadata below where they support filtering and audit.
    schema_tags, tag_booleans = _v3_tag_to_schema_tags(tag)
    try:
        from orchestrator.vault_export import _build_canonical_frontmatter
    except Exception:
        _build_canonical_frontmatter = None

    if _build_canonical_frontmatter is not None:
        frontmatter = _build_canonical_frontmatter(
            nexus=[],
            type_="chat",
            tags=schema_tags,
            created_at=ts_iso,
        )
    else:
        # Defensive fallback: emit canonical YAML inline if vault_export
        # import is unavailable for any reason.
        tags_yaml = "tags:\n" + "".join(f"  - {t}\n" for t in schema_tags) if schema_tags else "tags:\n"
        frontmatter = (
            f"---\n"
            f"nexus:\n"
            f"type: chat\n"
            f"{tags_yaml}"
            f"date created: {date_str}\n"
            f"date modified: {date_str}\n"
            f"---\n"
        )

    # Manifest sidecar — record (conversation_id, chunk_path, raw_path, tag)
    # BEFORE the chunk file is written, so the stealth purge can find the
    # on-disk artifacts even if ChromaDB indexing later fails. Without this,
    # a stealth conversation whose ChromaDB write failed would have its chunk
    # file and raw log orphaned: Layer 1 of _purge_stealth finds zero records,
    # Layer 2 has empty chunk_paths, the files persist. The manifest is the
    # authoritative purge list; ChromaDB-based discovery is a fallback.
    try:
        # Root flows from runtime_paths so the writer and the stealth
        # purge (conversation_closeout Layer 8) agree under relocation.
        manifest_path = os.path.join(
            rp.DATA_DIR_STR, "conversation-manifest.jsonl"
        )
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        import json as _json_mf
        with rp.locked_file(manifest_path):
            rp.append_text_no_follow(
                manifest_path,
                _json_mf.dumps({
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "conversation_id": panel_id,
                    "chunk_id": chunk_id,
                    "chunk_path": chunk_path,
                    "chunk_root": os.path.abspath(chunk_dir),
                    "artifact_kind": "conversation_chunk",
                    "managed_by": "ora",
                    "raw_path": sess["raw_path"],
                    "tag": tag,
                    "trace_ref": trace_ref,
                }) + "\n",
            )
    except Exception as _mf_exc:
        # Manifest is a defensive layer — failure to write it should NOT
        # block the conversation save. Surface to stderr so a developer
        # watching the process can see the manifest layer is degraded.
        print(
            f"[WARNING] conversation manifest write failed: {_mf_exc} "
            f"chunk_id={chunk_id} conv={panel_id}",
            flush=True,
        )

    chunk_content = (
        f"{frontmatter}\n"
        f"<!-- ora-conversation-id: {json.dumps(panel_id, ensure_ascii=False)} -->\n"
        f"<!-- ora-chunk-id: {json.dumps(chunk_id, ensure_ascii=False)} -->\n\n"
        f"## Context\n\n"
        f"{context_header}\n\n"
        f"## Exchange\n\n"
        f"**User:**\n\n"
        f"{user_input}\n\n"
        f"**Assistant:**\n\n"
        f"{ai_response}\n"
    )
    with open(chunk_path, "w", encoding="utf-8") as f:
        f.write(chunk_content)

    # Stealth exchanges remain authoritative for direct Dialogue continuity
    # and protected deletion, but never enter persisted/global Conversation
    # RAG or its embedding-provider path.
    if tag == "stealth":
        return chunk_id

    # ── Step 3: Index into ChromaDB conversations collection ─────────────────
    # Phase 5.8: ~22-field metadata schema per Conv RAG §2.
    try:
        import chromadb
        from orchestrator.embedding import get_or_create_collection
        chroma_path = cfg.get("chromadb_path", os.path.join(WORKSPACE, "chromadb/"))
        client      = chromadb.PersistentClient(path=chroma_path)
        # Embedding function bound to the collection so writes are
        # consistent with reads. Cross-platform via Ollama.
        collection  = get_or_create_collection(client, "conversations")
        # Embed header + user prompt only (not assistant response — per spec)
        embed_text = build_embedding_orientation(
            context_header, user_input,
        )[:MAX_EMBED_CHARS]
        retrieval_document = build_retrieval_document(
            context_header, user_input, ai_response,
        )
        embedding  = _nomic_embed(embed_text)
        if embedding is None:
            raise RuntimeError(
                "conversation embedding orientation unavailable; source chunk retained for replay"
            )

        # The envelope display_name is authoritative. Clearing it uses the
        # same derived fallback as the sidebar; this keeps future chunks from
        # reverting a rename that was already propagated to existing rows.
        first_user = sess.get("first_user_input", user_input) or user_input
        conversation_title = ""
        try:
            from orchestrator.conversation_memory import (
                load_conversation_json,
                effective_conversation_title,
                _derive_title,
            )
            envelope = load_conversation_json(panel_id)
            if envelope:
                conversation_title = effective_conversation_title(envelope)
            if not conversation_title:
                conversation_title = _derive_title([
                    {"role": "user", "content": first_user}
                ])
        except Exception as exc:
            print(f"[conversation-lifecycle] title resolution failed for "
                  f"{panel_id}: {exc}", flush=True)
        if not conversation_title:
            conversation_title = f"Session {session_id}"

        # Compose the canonical metadata dict.
        combined_text = f"{user_input}\n{ai_response}"
        entities = _extract_entities(combined_text)
        keywords = _extract_keywords(combined_text)
        references_turns = [pair_num - 1] if pair_num > 1 else []

        try:
            now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            now_utc = ts_iso  # fallback to local-time iso

        meta: dict = {
            # Temporal (Conv RAG §2)
            "timestamp_utc":      now_utc,
            "date":               date_str,
            "year":               int(now.year),
            "month":               int(now.month),

            # Identity
            "conversation_id":    panel_id,
            "conversation_title": conversation_title,
            "session_id":         session_id,

            # Structure
            "turn_index":         pair_num,
            "total_turns":        pair_num,    # updated at close-out
            "chunk_type":         "turn_pair",
            "is_first_turn":      pair_num == 1,
            "is_last_turn":       False,        # updated at close-out

            # Content
            "topic_primary":      topic_primary,
            "turn_summary":       context_header,

            # Source / origin
            "source_platform":    "local",
            "model_id":           model_id,

            # Thread continuity
            "thread_id":          thread_id,

            # Pipeline
            "obsidian_path":      chunk_path,
            "file_hash":          _compute_pair_hash(user_input, ai_response),

            # Type + Phase 5.3 filter booleans + V3 close-out compatibility
            "type":               "chat",
            "tag":                tag,                  # legacy V3 mode flag
            "agent_id":            "user",
            "chunk_path":          chunk_path,           # V3 stealth purge needs this
            "raw_path":            sess["raw_path"],     # V3 stealth purge needs this
            "model_used":          model_id,             # legacy alias, kept for backward compat
            "timestamp":           ts_iso,                # legacy alias
            "pair_num":            pair_num,              # legacy alias for turn_index
            "source":              os.path.basename(chunk_path),  # used by knowledge_search formatter
        }
        meta.update(tag_booleans)
        meta["embedding_text_sha256"] = hashlib.sha256(
            embed_text.encode("utf-8")
        ).hexdigest()

        # ChromaDB rejects empty list metadata; only emit non-empty lists.
        if topics:
            meta["topic_tags"] = topics
            meta["topics"]     = ", ".join(topics)  # legacy alias
        if entities:
            meta["entities"]   = entities
        if keywords:
            meta["keywords"]   = keywords
        if references_turns:
            meta["references_turns"] = references_turns

        add_kwargs = dict(
            ids=[chunk_id],
            documents=[retrieval_document],
            metadatas=[meta],
            embeddings=[embedding],
        )

        collection.add(**add_kwargs)
    except Exception as _indexing_exc:
        # ChromaDB failure never blocks the conversation — the chunk file
        # on disk is the source of truth; the index can be rebuilt. But
        # silently dropping the indexing failure means the user can't
        # retrieve this conversation via RAG and never finds out (fix for
        # silent failure #12). Record the failure to a structured log so
        # it can be audited and replayed.
        #
        # PRIVACY: this log is a new persistence surface. For stealth
        # conversations we skip the write entirely and fall through to
        # stderr — keeping the diagnostic visible to a developer
        # watching the process but never persisting it to disk. For
        # non-stealth conversations the failure log path is also
        # included in _purge_stealth as defence-in-depth so any
        # conversation later re-tagged or accidentally tagged stealth
        # gets its failure-log entries removed on deletion. The whole
        # log directory is gitignored.
        if tag == "stealth":
            print(
                f"[WARNING] conversation indexing failed (stealth — not "
                f"logged): {_indexing_exc} chunk_id={chunk_id} "
                f"conv={panel_id}",
                flush=True,
            )
        else:
            try:
                import json as _json
                failures_log = os.path.join(
                    rp.DATA_DIR_STR, "conversation-indexing-failures.jsonl"
                )
                os.makedirs(os.path.dirname(failures_log), exist_ok=True)
                with rp.locked_file(failures_log):
                    rp.append_text_no_follow(
                        failures_log,
                        _json.dumps({
                            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                            "conversation_id": panel_id,
                            "chunk_id": chunk_id,
                            "chunk_path": chunk_path,
                            "error": str(_indexing_exc)[:2000],
                            "error_type": type(_indexing_exc).__name__,
                            "tag": tag,
                        }) + "\n",
                    )
            except Exception as _log_exc:
                # If even the failure log fails, fall through to stderr so
                # the event is at least visible to anyone watching.
                print(
                    f"[WARNING] conversation indexing failed AND failure "
                    f"log failed: indexing={_indexing_exc} "
                    f"log={_log_exc} chunk_id={chunk_id} conv={panel_id}",
                    flush=True,
                )

    # V3 Backlog 2A Chunk 2 — return the chunk identifier so the caller
    # can include it in the plain-HTTP reply (file-as-source-of-truth).
    return chunk_id


def _save_conversation(user_input, ai_response, panel_id, is_new_session,
                       tag="", output_destination="", trace_ref=None):
    """Lifecycle-serialized wrapper around the conversation artifact save."""
    with _conversation_lifecycle_lock(panel_id):
        if _is_conversation_deleted(panel_id):
            print(f"[conversation-lifecycle] refused late save for deleted "
                      f"conversation {panel_id}", flush=True)
            return None
        if _is_conversation_closed(panel_id):
            print(f"[conversation-lifecycle] refused late save for closed "
                  f"conversation {panel_id}", flush=True)
            return None
        _assert_no_casefold_session_collision(panel_id)
        # Direct/internal first-save callers do not pass through /chat's
        # creation-tag registration. Seed it here when there is no live
        # session state; request-path callers already pass the canonical tag.
        if is_new_session and panel_id not in _session_data:
            with _conversation_lifecycle_guard:
                _conversation_creation_tags[
                    _conversation_storage_identity(panel_id)
                ] = _normalize_tag(tag)
        effective_tag = _effective_conversation_tag(panel_id, tag)
        return _save_conversation_unlocked(
            user_input, ai_response, panel_id, is_new_session,
            effective_tag, output_destination=output_destination,
            trace_ref=trace_ref,
        )


def _apply_style_audience(extra_context, style_audience):
    """G1.36 honne/tatemae — when the input-pane toggle marks this turn
    ``internal``, fold the active project's ``interaction_style`` onto
    ``extra_context["style_id"]`` (how Ora talks TO you), overriding the default
    OUTPUT style for this turn only. ``external`` (default), Commons, an
    unset interaction_style, or an explicit /style one-off already on
    extra_context → unchanged. Returns extra_context (possibly a new dict);
    best-effort, never raises."""
    if (style_audience or "").strip().lower() != "internal":
        return extra_context
    if extra_context and "style_id" in extra_context:
        return extra_context  # an explicit /style one-off wins
    try:
        from orchestrator.active_project import get_active_project
        from orchestrator import project_meta as _pm
        nx = get_active_project()
        if nx and nx.lower() not in ("commons", "general"):
            rec = _pm.read_project_meta(nx)
            isid = (rec or {}).get("interaction_style")
            if isinstance(isid, str) and isid.strip():
                extra_context = dict(extra_context or {})
                extra_context["style_id"] = isid.strip()
    except Exception:
        pass
    return extra_context


def _active_project_model_context():
    """Capture one authenticated active-project identity and binding snapshot."""
    from orchestrator.active_project import get_active_project
    from orchestrator import model_profiles as _mp
    from orchestrator import project_meta as _pm
    nexus = get_active_project()
    if not nexus or nexus.lower() in ("commons", "general"):
        return None, None
    nexus = _pm.validate_nexus(nexus)
    record = _pm.read_project_meta(nexus)
    if record is None:
        raise _pm.ProjectMetaError(f"active project {nexus!r} is unavailable")
    if not record.get("default_model_profile"):
        return nexus, None
    return nexus, _mp.validate_project_binding(record, expected_nexus=nexus)


def _active_project_model_locks():
    """Return authenticated locks for the active project, or None for Commons/unbound."""
    return _active_project_model_context()[1]


def _active_project_model_nexus():
    """Return the exact active non-Commons project only when its record exists."""
    return _active_project_model_context()[0]


def _apply_project_model_locks(extra_context):
    """Thread exact project visual locks into the same turn as its text snapshot."""
    nexus, locks = _active_project_model_context()
    if nexus is None and locks is None:
        return extra_context
    result = dict(extra_context or {})
    if nexus is not None:
        result["model_profile_project_nexus"] = nexus
    if locks is not None:
        result["model_profile_locks"] = locks
    return result


def _framework_project_nexus(extra_context):
    """Read the server-authenticated project identity captured for this turn."""
    if not isinstance(extra_context, dict):
        return None
    nexus = extra_context.get("model_profile_project_nexus")
    if not nexus:
        return None
    from orchestrator import project_meta as _pm
    nexus = _pm.validate_nexus(nexus)
    locks = extra_context.get("model_profile_locks")
    if isinstance(locks, dict) and locks.get("project_nexus") != nexus:
        raise _pm.ProjectMetaError(
            "framework project identity does not match its Model Profile locks"
        )
    return nexus


def _validate_public_model_profile_override(config_name):
    """Reject internal tokens and unavailable names at HTTP entry surfaces."""
    if config_name is None:
        return None
    from orchestrator import model_profiles as _mp
    if isinstance(config_name, str) and config_name.startswith(_mp.LOCK_TOKEN_PREFIX):
        raise _mp.ModelProfileError(
            "runtime-issued project Model Profile tokens are not public overrides"
        )
    name = _mp.validate_profile_name(config_name)
    summary = _mp.profile_summary(name)
    if summary["health"]["status"] == "unavailable":
        raise _mp.ModelProfileError(
            f"cannot run unavailable Model Profile {name!r}: "
            f"{summary['health']['reason']}"
        )
    _mp.validate_profile_allocation(name)
    return name


def _normalize_explicit_history(history) -> list[dict]:
    """Return the truthful subset accepted from a legacy/API caller.

    Role and content are the transcript, and the server does not let a caller
    replace its own record of those — see _authoritative_dialogue_history.
    Canvas state is different: a user turn's spatial_representation and
    annotations are the caller's own drawing, not a claim about what was said,
    and for a conversation with no envelope on disk the request is their only
    source. Dropping them here (as this function did from 2026-08-10) silently
    disabled WP-5.3 spatial continuity on that path — the handler's own
    get_prior_spatial_state lookup could never find a prior turn, so layout
    evolution stopped reaching the model. Both are type-checked before being
    carried through, and only on user turns.
    """
    if not isinstance(history, list):
        return []
    normalized = []
    for message in history:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant", "system"}:
            continue
        if not isinstance(content, str):
            continue
        turn = {"role": role, "content": content}
        if role == "user":
            spatial = message.get("spatial_representation")
            if isinstance(spatial, dict):
                turn["spatial_representation"] = spatial
            annotations = message.get("annotations")
            if isinstance(annotations, list):
                turn["annotations"] = annotations
        normalized.append(turn)
    return normalized


def _authoritative_dialogue_history(
        conversation_id: str, supplied_history=None) -> tuple[list[dict], dict]:
    """Resolve one request's ordered history and local turn metadata.

    An existing Dialogue envelope always wins, including an honestly empty
    child whose visible history consists only of fork ancestry.  Explicit
    history remains available solely for callers whose id has no envelope;
    this preserves the legacy/API contract without letting an ordinary V3
    browser replace or duplicate the server transcript.  An existing but
    unreadable envelope fails closed to empty history instead of trusting the
    request.  This function is read-only.
    """
    explicit = _normalize_explicit_history(supplied_history)
    try:
        from orchestrator.conversation_memory import (
            _DEFAULT_SESSIONS_ROOT,
            _conversation_path,
            _read_history_envelope,
            resolve_effective_conversation_history,
        )

        root = _DEFAULT_SESSIONS_ROOT
        live_path = _conversation_path(conversation_id, root)
        archived_path = _conversation_path(
            conversation_id, root / "archived",
        )
        envelope_exists = live_path.exists() or archived_path.exists()
        envelope = _read_history_envelope(conversation_id, root)
        if envelope_exists:
            effective = resolve_effective_conversation_history(
                conversation_id, sessions_root=root,
            )
            history = effective if isinstance(effective, list) else []
            local_raw = (
                envelope.get("messages")
                if isinstance(envelope, dict) else []
            )
            if not isinstance(local_raw, list):
                local_raw = []
            local_messages = [
                message for message in local_raw
                if isinstance(message, dict)
                and message.get("role") in {"user", "assistant", "system"}
                and isinstance(message.get("content"), str)
            ]
            first_user_input = next(
                (
                    message["content"] for message in local_messages
                    if message.get("role") == "user"
                ),
                "",
            )
            return history, {
                "source": (
                    "conversation_json" if envelope is not None
                    else "unreadable_conversation_json"
                ),
                "envelope_exists": True,
                "local_message_count": len(local_messages),
                # Every persisted normal turn has exactly one user message;
                # assistant-only welcome/seed entries do not advance raw/RAG
                # pair numbering.
                "local_turn_count": sum(
                    1 for message in local_messages
                    if message.get("role") == "user"
                ),
                "first_user_input": first_user_input,
            }
    except Exception as exc:
        # Invalid ids are rejected at the HTTP boundary.  A read-path failure
        # for a valid id must not mutate state or silently accept browser
        # transcript authority.  The returned state deliberately treats an
        # uninspectable storage root as if an envelope existed.
        print(
            f"[dialogue-history] authoritative read failed for "
            f"{conversation_id}: {exc}", file=sys.stderr, flush=True,
        )
        return [], {
            "source": "history_read_failure",
            "envelope_exists": True,
            "local_message_count": 0,
            "local_turn_count": 0,
            "first_user_input": "",
        }

    return explicit, {
        "source": "legacy_explicit" if explicit else "new_conversation",
        "envelope_exists": False,
        "local_message_count": len(explicit),
        "local_turn_count": sum(
            1 for message in explicit if message.get("role") == "user"
        ),
        "first_user_input": next(
            (
                message["content"] for message in explicit
                if message.get("role") == "user"
            ),
            "",
        ),
    }


def _invoke_pipeline_unlocked(user_input, history, panel_id, is_main, images=None, extra_context=None, tag="",
                               manual_mode_selection="", manual_lens_selection="",
                               framework_selected="", submission_id="", output_destination="",
                               config_name=None, style_audience=""):
    """Shared pipeline helper — runs the pipeline synchronously, persists the
    chunk file, and returns a plain JSON reply.

    V3 Backlog 2A (2026-04-30) — file-as-source-of-truth model. The browser
    POSTs once and waits for a single JSON reply::

        {"status": "ok", "conversation_id": ..., "chunk_id": ...}

    or, on pipeline failure::

        {"status": "errored", "conversation_id": ..., "chunk_id": ...,
         "failure_summary": ...}

    The chunk file is on disk before the reply lands, so the browser can
    immediately mark the conversation Unread and (if needed) load the
    chunk via the existing ``/api/conversation/<id>`` endpoint.

    No SSE. No streaming. No pipeline-stage progress events. Per the V3
    spec, the user does not watch the pipeline run — they submit and come
    back later. The 12-second reconciliation scan in the browser catches
    any submissions whose connection dropped.

    The conversation.json append is synchronous because it is the next turn's
    history authority; the end-of-session pipeline remains a daemon-thread
    side effect. The chunk save also runs synchronously so the chunk_id is
    known before we reply; the prior pipeline-wide lock is gone (mlx_mutex
    inside call_model handles the MLX SIGSEGV constraint).

    WP-3.3: ``extra_context`` is merged into the pipeline's context_pkg
    by ``_run_pipeline_from_step2`` — threads spatial_representation +
    image_path through to ``build_system_prompt_for_gear``.

    V3 Phase 1.1: ``tag`` carries the conversation-level mode. Honored
    on first save only.

    V3 Input Handling Phase 1: ``manual_mode_selection`` and
    ``manual_lens_selection`` and ``framework_selected`` carry the user's
    input-box-toolbar choices.
    """
    if not user_input and not (
        extra_context and extra_context.get("visual_checkpoint_id")
    ):
        return json.dumps({"error": "empty message"}), 400

    # Parse /direct, /save, /saveboth, /style commands from input
    clean_input, use_pipeline, output_target, style_override = parse_user_command(user_input)
    # /style <id> one-off — fold onto extra_context so it lands on context_pkg
    # (overriding any project/engine default; "" clears the style this turn).
    if style_override is not None:
        extra_context = dict(extra_context or {})
        extra_context["style_id"] = style_override["style_id"]

    # G1.36 honne/tatemae — an "internal" audience (the input-pane toggle) makes
    # this turn read in the active project's INTERACTION style rather than the
    # default OUTPUT style. An explicit /style one-off above still wins.
    extra_context = _apply_style_audience(extra_context, style_audience)
    extra_context = _apply_project_model_locks(extra_context)

    # Sidebar window integration: use rolling window for sidebar panels.
    # Every ordinary Dialogue request instead reconstructs immutable/current
    # continuity from conversation.json under the lifecycle lock; the browser
    # is neither required nor trusted to post its transcript.
    is_sidebar = panel_id.startswith("sidebar")
    if is_sidebar and SIDEBAR_WINDOW_AVAILABLE:
        sidebar_win = get_sidebar_window(panel_id)
        history = sidebar_win.get_history()  # Override with rolling window
        history_state = {
            "source": "sidebar_window",
            "envelope_exists": False,
            "local_message_count": len(history),
            "local_turn_count": sum(
                1 for message in history
                if isinstance(message, dict) and message.get("role") == "user"
            ),
            "first_user_input": next((
                message.get("content", "") for message in history
                if isinstance(message, dict) and message.get("role") == "user"
            ), ""),
        }
    else:
        sidebar_win = None
        history, history_state = _authoritative_dialogue_history(
            panel_id, history,
        )

    # Mark the conversation as Pending for the duration of the run so the
    # sidebar list endpoint can group it correctly. Cleared in finally.
    _pending_conversations.add(panel_id)

    final_response = None
    active_mode    = None
    active_gear    = None
    last_stage     = None
    chunk_id       = None
    envelope_persisted = False
    failure_summary = None
    cfg            = None
    ep             = None
    trace_ref      = None
    process_invocation_state = None

    def _record_http_terminal(value, *, route, persisted, status_hint=None):
        """Best-effort trace of the exact plain-HTTP boundary value."""
        if not trace_ref:
            return
        try:
            from orchestrator import pipeline_trace as _pt_http_terminal
            _pt_http_terminal.record_terminal_output(
                trace_ref, value, route=route,
                output_target=output_target, persisted=persisted,
            )
            if status_hint:
                trace_dir = _pt_http_terminal.resolve_trace_ref(trace_ref)
                manifest = _pt_http_terminal.read_manifest(trace_dir) or {}
                _pt_http_terminal.finalize_manifest(
                    trace_dir,
                    kind=manifest.get("trace_kind") or "chat",
                    status_hint=status_hint,
                    mode=manifest.get("mode"),
                    gear=manifest.get("gear"),
                    parent_trace_ref=manifest.get("parent_trace_ref"),
                    framework_id=manifest.get("framework_id"),
                    milestone_id=manifest.get("milestone_id"),
                    child_trace_refs=manifest.get("child_trace_refs"),
                )
        except Exception:
            pass

    try:
        # MLX per-machine serialization lives inside call_model
        # (mlx_mutex.acquire on the local branch) since the 2026-05-19
        # concurrency overhaul. The save and oversight health check
        # below run without holding any lock — a second user submitting
        # while the first is mid-run no longer waits at the gate for
        # the entire pipeline.
        cfg = load_config()
        ep  = get_endpoint(cfg)

        # Iterate the (still-streaming) pipeline generator synchronously;
        # we don't yield to the browser, we just collect the final
        # response and the most-recent stage/mode/gear for bridge state.
        try:
            for chunk in agentic_loop_stream(
                    clean_input, history, use_pipeline=use_pipeline,
                    panel_id=panel_id, images=images,
                    extra_context=extra_context,
                    manual_mode_selection=manual_mode_selection,
                    manual_lens_selection=manual_lens_selection,
                    framework_selected=framework_selected,
                    config_name=config_name,
                    conversation_tag=tag):
                try:
                    d = json.loads(chunk[6:])
                except Exception:
                    continue
                t = d.get("type")
                if t == "response":
                    final_response = d.get("text", "")
                elif t == "pipeline_stage":
                    last_stage = d.get("stage")
                    if d.get("mode"):
                        active_mode = d["mode"]
                    if d.get("gear"):
                        active_gear = d["gear"]
                elif t == "trace_ref":
                    # Chunk 0: the pipeline generator's in-band trace-ref
                    # channel — joins this turn's conversation records to
                    # its trace dir. Absent (None) for stealth/untraced.
                    trace_ref = d.get("ref")
                elif t == "error":
                    failure_summary = d.get("text") or d.get("error") or "pipeline error"
        except Exception as e:
            # Any uncaught pipeline exception becomes the failure summary.
            # The submission log persists as a pending file; on next
            # boot it surfaces as an errored chunk via orphan recovery.
            failure_summary = f"pipeline crashed: {e}"
            print(f"[ERROR] _invoke_pipeline pipeline crash: {e}")

        if final_response is not None:
            # Meta-layer oversight health check — if any watcher is
            # stale, prepend a system note so the user sees the warning
            # in the conversation. Per Reference — Meta-Layer Architecture
            # §10 O1; surfacing path settled 2026-05-04.
            try:
                from oversight_health import check_health, format_warnings_as_chat_note
                _oversight_warnings = check_health()
                if _oversight_warnings:
                    _oversight_note = format_warnings_as_chat_note(_oversight_warnings)
                    if _oversight_note:
                        final_response = _oversight_note + final_response
            except Exception as _oh_exc:
                # Health check must never break the chat path
                print(f"[server] oversight health check failed (non-fatal): {_oh_exc}")

            # Pipeline-execution health check (S3, 2026-05-22) — drain
            # any in-pipeline warnings recorded thread-locally during
            # the turn (e.g. Phase A output unparseable) and prepend.
            try:
                from pipeline_health import (
                    collect_and_clear as _ph_collect,
                    format_warnings_as_chat_note as _ph_format,
                )
                _pipeline_warnings = _ph_collect()
                if _pipeline_warnings:
                    _ph_note = _ph_format(_pipeline_warnings)
                    if _ph_note:
                        final_response = _ph_note + final_response
            except Exception as _ph_exc:
                print(f"[server] pipeline health check failed (non-fatal): {_ph_exc}")

            # Handle file output routing (e.g. /save, /saveboth)
            if output_target != "screen":
                routed = route_output(final_response, output_target)
                if output_target.startswith("file:"):
                    # When routed to file, the on-screen response is the
                    # file pointer text, so the chunk reflects what the
                    # user effectively saw.
                    final_response = routed

            # Sidebar window: record exchange in rolling window
            if (final_response is not None and is_sidebar
                    and SIDEBAR_WINDOW_AVAILABLE and sidebar_win is not None):
                sidebar_win.add_exchange(clean_input, final_response)

            # Effective history can be non-empty for a true empty-child fork.
            # Session/raw numbering is local to the child, while a restarted
            # ordinary Dialogue resumes from its own persisted turn count.
            is_new_session = history_state["local_message_count"] == 0

            # Initialize session data only while the lifecycle lock is held.
            # A Delete Forever tombstone may be set while the model is still
            # running; in that case no late in-memory or on-disk state is made.
            if final_response is not None and not _is_conversation_deleted(panel_id):
                if is_new_session or panel_id not in _session_data:
                    _session_data[panel_id] = {
                        "raw_path": "",  # populated by _save_conversation
                        "session_id": uuid.uuid4().hex,
                        "pair_count": history_state["local_turn_count"],
                        "model": (ep.get("name", "unknown") if ep else "unknown"),
                        "start": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "first_user_input": (
                            history_state["first_user_input"] or clean_input
                        ),
                        "prior_topic": None,
                        "thread_counter": 0,
                    }

            # The user-visible chunk and authoritative conversation envelope
            # are one acknowledged save boundary. Both complete synchronously
            # under the lifecycle lock before the pending submission can move
            # to processed or the HTTP response can report success.
            if final_response is not None:
                try:
                    chunk_id = _save_conversation(
                        clean_input, final_response, panel_id,
                        is_new_session, tag,
                        output_destination=output_destination,
                        trace_ref=trace_ref)
                except Exception as e:
                    failure_summary = f"_save_conversation failed: {e}"
                    print(f"[ERROR] _save_conversation: {e}")

            # WP-5.3 — append this turn before releasing the lifecycle lock.
            # ``conversation.json`` is the next turn's history authority. A
            # path return acknowledges success; if a wrapper raises after a
            # completed write, verify the expected new tail once on disk.
            if chunk_id and not _is_conversation_deleted(panel_id):
                persist_issue = ""
                try:
                    envelope_persisted = bool(
                        _persist_turn_spatial_state_unlocked(
                            panel_id, clean_input, final_response,
                            extra_context, tag, trace_ref=trace_ref,
                        )
                    )
                except Exception as e:
                    persist_issue = f"{type(e).__name__}: {e}"
                    print(
                        "[WARNING] conversation envelope persist raised: "
                        f"{persist_issue}"
                    )
                if not envelope_persisted:
                    envelope_persisted = _turn_envelope_acknowledged(
                        panel_id,
                        history_state["local_message_count"],
                        clean_input,
                        final_response,
                    )
                if not envelope_persisted:
                    failure_summary = "conversation envelope persistence failed"
                    if persist_issue:
                        failure_summary += f": {persist_issue}"

            if envelope_persisted:
                # This is the first boundary at which the complete turn is
                # durable in both user-visible and history-authoritative stores.
                _record_http_terminal(
                    final_response, route="server-conversation-save",
                    persisted=True,
                )

            # Clear recovery markers only after the replacement turn reaches
            # the authoritative envelope. If this was a retry of a previously
            # unacknowledged submission, retire that older pending record too
            # so restart recovery cannot surface the same prompt again.
            if envelope_persisted:
                try:
                    from conversation_memory import (
                        load_conversation_json,
                        clear_conversation_error,
                        _conversation_path,
                        _DEFAULT_SESSIONS_ROOT,
                    )
                    data = load_conversation_json(panel_id)
                    if data and (data.get("interrupted_input")
                                  or data.get("interrupted_at")):
                        recovered_submission_id = data.get(
                            "interrupted_submission_id"
                        )
                        data.pop("interrupted_input", None)
                        data.pop("interrupted_at", None)
                        data.pop("interrupted_submission_id", None)
                        data.pop("interrupted_visual_checkpoint_id", None)
                        env_path = _conversation_path(panel_id,
                                                      _DEFAULT_SESSIONS_ROOT)
                        rp.atomic_write_text(
                            env_path,
                            json.dumps(
                                data, indent=2, ensure_ascii=False,
                            ),
                        )
                        clear_conversation_error(panel_id)
                        if isinstance(recovered_submission_id, str):
                            _finalize_pending_submission(
                                recovered_submission_id
                            )
                except Exception as e:
                    print(f"[WARNING] orphan-marker clear failed: {e}")

            if (chunk_id and envelope_persisted and is_main
                    and not _is_conversation_deleted(panel_id)):
                recent = list(history[-4:]) + [
                    {"role": "user",      "content": clean_input},
                    {"role": "assistant", "content": final_response},
                ]
                _bridge_state[panel_id] = {
                    "current_topic":   clean_input,
                    "recent_messages": recent[-5:],
                    "active_mode":     active_mode,
                    "active_gear":     active_gear,
                    "pipeline_stage":  last_stage,
                    "updated_at":      time.time(),
                }

            # Runtime pipeline: fire async end-of-session processing
            if (chunk_id and envelope_persisted and RUNTIME_PIPELINE_AVAILABLE
                    and not is_sidebar
                    and tag != "stealth"
                    and not _is_conversation_deleted(panel_id)):
                threading.Thread(
                    target=_run_end_of_session_pipeline,
                    args=(clean_input, final_response, panel_id, cfg, history),
                    daemon=True,
                ).start()
    finally:
        _pending_conversations.discard(panel_id)

    if _is_conversation_deleted(panel_id):
        _delete_pending_submission(submission_id)
        deleted_reply = json.dumps({
            "status": "deleted",
            "conversation_id": panel_id,
            "chunk_id": None,
        })
        _record_http_terminal(
            deleted_reply, route="server-http-deleted",
            persisted=False, status_hint="error",
        )
        return deleted_reply, 410

    # On a successful save, finalize the submission log (move pending →
    # processed). On a failure, leave the pending file in place — the
    # next boot will surface it as an orphan errored chunk.
    if chunk_id and envelope_persisted and submission_id:
        _finalize_pending_submission(submission_id)

    # ── Build the plain-HTTP reply ──────────────────────────────────────
    if final_response is not None and chunk_id and envelope_persisted:
        payload = {
            "status":          "ok",
            "conversation_id": panel_id,
            "chunk_id":        chunk_id,
        }
        if process_invocation_state is not None:
            payload["process_invocation"] = _public_process_invocation(
                process_invocation_state
            )
        return json.dumps(payload)

    # Failure path. Mark the conversation envelope errored so the sidebar
    # surfaces the failure in the Errored group; the existing Backlog 2D
    # error-chunk pattern owns the failure-trace + recommendation body
    # (writing it here would duplicate the orchestrator's own error path).
    # When no failure_summary was set, include the last_stage we saw so
    # silent drop-outs (generator returned without yielding response/error)
    # surface a useful breadcrumb instead of the bare "no response" string.
    if failure_summary:
        summary = failure_summary
    elif last_stage:
        summary = f"pipeline produced no response (last stage: {last_stage}; mode: {active_mode or '?'})"
    else:
        summary = "pipeline produced no response (no stages observed; check endpoint config)"
    try:
        from conversation_memory import mark_conversation_errored
        mark_conversation_errored(
            panel_id,
            summary,
            interrupted_input=(
                clean_input if chunk_id and not envelope_persisted else None
            ),
            interrupted_submission_id=(
                submission_id if chunk_id and not envelope_persisted else None
            ),
        )
    except Exception as e:
        print(f"[WARNING] mark_conversation_errored failed: {e}")

    # The submission log stays in pending/ on failure — it will be picked
    # up by the next-boot orphan scan if the server crashed, or is left
    # for manual cleanup if the pipeline returned without a response.
    error_reply = json.dumps({
        "status":          "errored",
        "conversation_id": panel_id,
        "chunk_id":        chunk_id,
        "failure_summary": summary,
    })
    _record_http_terminal(
        error_reply, route="server-http-error",
        persisted=False, status_hint="error",
    )
    return error_reply


def _invoke_pipeline(user_input, history, panel_id, is_main, images=None,
                     extra_context=None, tag="", manual_mode_selection="",
                     manual_lens_selection="", framework_selected="",
                     submission_id="", output_destination="", config_name=None,
                     style_audience=""):
    """Run one conversation turn under its lifecycle lock.

    Delete Forever marks a tombstone before waiting on this lock. That lets an
    already-running turn drain without being able to save, then guarantees the
    purge runs after its trace/tool writes have stopped.
    """
    panel_id = (panel_id or "").strip()
    if not _valid_live_conversation_id(panel_id):
        _delete_pending_submission(submission_id)
        return json.dumps({"error": "invalid conversation_id"}), 400
    with _conversation_lifecycle_lock(panel_id):
        if _is_conversation_deleted(panel_id):
            _delete_pending_submission(submission_id)
            return json.dumps({
                "status": "deleted",
                "conversation_id": panel_id,
            }), 410
        if _is_conversation_closed(panel_id):
            _delete_pending_submission(submission_id)
            return json.dumps({
                "status": "closed",
                "conversation_id": panel_id,
            }), 409
        effective_tag = _effective_conversation_tag(panel_id, tag)
        effective_context = dict(extra_context or {})
        effective_context.pop("contributor_bundle", None)
        contributor_bundle = build_contributor_bundle(
            panel_id, target_tag=effective_tag,
        )
        if contributor_bundle.get("sources"):
            effective_context["contributor_bundle"] = contributor_bundle
        return _invoke_pipeline_unlocked(
            user_input, history, panel_id, is_main,
            images=images, extra_context=effective_context or None,
            tag=effective_tag,
            manual_mode_selection=manual_mode_selection,
            manual_lens_selection=manual_lens_selection,
            framework_selected=framework_selected,
            submission_id=submission_id,
            output_destination=output_destination,
            config_name=config_name,
            style_audience=style_audience,
        )


@app.route("/chat", methods=["POST"])
def chat():
    """Ordinary Inquiry. Programming uses only the explicit /api/programming routes."""

    data = request.get_json(force=True)
    user_input = str(data.get("message") or "").strip()
    supplied_history = data.get("history", [])
    history = []
    panel_id = str(data.get("panel_id") or data.get("conversation_id") or "main").strip()
    is_main = data.get("is_main_feed", True)
    tag = _normalize_tag(data.get("tag", ""))
    manual_mode_selection = str(data.get("manual_mode_selection") or "").strip()
    manual_lens_selection = str(data.get("manual_lens_selection") or "").strip()
    framework_selected = str(data.get("framework_selected") or "").strip()
    style_audience = str(data.get("style_audience") or "").strip()
    manual_visual_type = str(data.get("manual_visual_type") or "").strip()
    output_destination = str(data.get("output_destination") or "").strip()
    config_name = data.get("config_name")
    if isinstance(config_name, str):
        config_name = config_name.strip() or None
    try:
        config_name = _validate_public_model_profile_override(config_name)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 400)
    trace_debug_payload = (
        data.get("trace_debug") if isinstance(data.get("trace_debug"), dict) else None
    )
    if not user_input and not trace_debug_payload:
        return _json_response({"error": "empty message"}, 400)
    if not _valid_live_conversation_id(panel_id):
        return _json_response({"error": "invalid conversation_id"}, 400)

    with _conversation_lifecycle_lock(panel_id):
        if _is_conversation_deleted(panel_id):
            return _json_response({"status": "deleted", "conversation_id": panel_id}, 410)
        if _is_conversation_closed(panel_id):
            return _json_response({"status": "closed", "conversation_id": panel_id}, 409)
        try:
            _assert_no_casefold_session_collision(panel_id)
        except (ValueError, RuntimeError) as exc:
            return _json_response({"error": str(exc)}, 409)
        tag = _effective_conversation_tag(panel_id, tag)
        history, history_state = _authoritative_dialogue_history(
            panel_id, supplied_history,
        )
        submission_id = _log_pending_submission({
            "endpoint": "/chat",
            "conversation_id": panel_id,
            "panel_id": panel_id,
            "is_main_feed": is_main,
            "tag": tag,
            "user_input": user_input,
            # Preserve what the caller actually submitted for request-audit
            # fidelity.  Pipeline authority is the separately resolved
            # ``history`` variable above.
            "history": supplied_history,
            "history_source": history_state["source"],
            "manual_mode_selection": manual_mode_selection,
            "manual_lens_selection": manual_lens_selection,
            "framework_selected": framework_selected,
            "output_destination": output_destination,
            "attachments": data.get("attachments", []),
            "trace_debug": trace_debug_payload,
        })

    text_parts, images = _process_attachments(data.get("attachments", []))
    if text_parts:
        user_input += "\n\n" + "\n\n".join(text_parts)
    extra_context = {}
    if manual_visual_type:
        extra_context["visual_kind"] = manual_visual_type
    if trace_debug_payload:
        extra_context["trace_debug"] = trace_debug_payload
    return _invoke_pipeline(
        user_input, history, panel_id, is_main, images=images,
        extra_context=extra_context or None,
        tag=tag,
        manual_mode_selection=manual_mode_selection,
        manual_lens_selection=manual_lens_selection,
        framework_selected=framework_selected,
        submission_id=submission_id,
        output_destination=output_destination,
        config_name=config_name,
        style_audience=style_audience,
    )


# ── WP-3.3: Merged visual + text input (multipart) ───────────────────────────

# Uploads for /chat/multipart land here, partitioned by conversation_id.
VISUAL_UPLOADS_ROOT = os.path.join(str(rp.ORA_HOME), "sessions", "")


def _save_canvas_preview_png(conversation_id: str, data_url: str) -> str | None:
    """Persist a canvas-rendered PNG (data URL) to the conversation's
    uploads dir so the pipeline can route it to vision-capable models
    just like a user-uploaded image. Returns the absolute path or None.

    V3 Item 12 Q1 follow-up — vision-capable rendered-snapshot bundling.
    The text-only path is already covered by `spatial_representation`;
    this gives image-capable models the visual gestalt without having
    to reconstruct it from object data.
    """
    if not data_url or not isinstance(data_url, str):
        return None
    m = re.match(r"^data:image/png;base64,(.+)$", data_url, re.IGNORECASE)
    if not m:
        return None
    try:
        import base64
        raw = base64.b64decode(m.group(1), validate=False)
    except Exception:
        return None
    try:
        canonical_id = _canonical_live_conversation_id(conversation_id)
        out_dir = str(rp.safe_owned_subdir(
            VISUAL_UPLOADS_ROOT, canonical_id, "uploads", create=True,
        ))
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_path = os.path.join(out_dir, f"{ts}-canvas-preview.png")
        rp.atomic_write_bytes(out_path, raw)
        return out_path
    except Exception as e:
        print(f"[WARNING] _save_canvas_preview_png failed: {e}")
        return None


def _save_multipart_image(conversation_id: str, file_storage) -> str | None:
    """Persist a multipart-uploaded image under
    ``~/ora/sessions/<conversation_id>/uploads/<timestamp>-<name>`` and return
    the absolute path. Creates the directory if missing. Returns None on
    failure (so the pipeline continues without the image).
    """
    if file_storage is None:
        return None
    try:
        # Conservative filename sanitization: keep extension, slug the rest.
        name = (file_storage.filename or "upload").strip()
        base = os.path.basename(name) or "upload"
        # Strip any path-traversal tokens
        base = base.replace("..", "_").replace("/", "_").replace("\\", "_")
        canonical_id = _canonical_live_conversation_id(conversation_id)
        out_dir = str(rp.safe_owned_subdir(
            VISUAL_UPLOADS_ROOT, canonical_id, "uploads", create=True,
        ))
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_path = os.path.join(out_dir, f"{ts}-{base}")
        _save_filestorage_no_follow(file_storage, out_path)
        return out_path
    except Exception as e:
        print(f"[WARNING] _save_multipart_image failed: {e}")
        return None


@app.route("/chat/multipart", methods=["POST"])
def chat_multipart():
    """WP-3.3 — Merged visual + text input endpoint.

    Accepts ``multipart/form-data`` with fields:
      * ``message`` (required, str)
      * ``conversation_id`` (required, str — aliased to the existing panel_id)
      * ``spatial_representation`` (optional, JSON-encoded string per
        ``config/visual-schemas/spatial_representation.json``)
      * ``image`` (optional, binary file field)
      * ``history``, ``is_main_feed``, ``panel_id`` (optional — carried over
        from the JSON /chat contract)

    Behavior:
      1. Validates spatial_representation against the schema via
         ``visual_validator.validate_spatial_representation``. Invalid →
         400 with findings.
      2. Saves any uploaded image to
         ``~/ora/sessions/<conversation_id>/uploads/<timestamp>-<name>``.
      3. Invokes the same shared pipeline helper as /chat, threading the
         spatial_representation + image_path through the context package.
      4. Returns SSE exactly like /chat.
    """
    form = request.form
    user_input = (form.get("message") or "").strip()
    conversation_id = (form.get("conversation_id") or form.get("panel_id") or "main").strip()
    panel_id = (form.get("panel_id") or conversation_id).strip() or "main"
    is_main = (form.get("is_main_feed", "true").lower() not in {"false", "0", "no"})
    tag = _normalize_tag(form.get("tag", ""))
    # V3 Phase 1 — same alignment-prefilter inputs as /chat. See chat() above.
    manual_mode_selection = (form.get("manual_mode_selection") or "").strip()
    manual_lens_selection = (form.get("manual_lens_selection") or "").strip()
    framework_selected    = (form.get("framework_selected") or "").strip()
    style_audience        = (form.get("style_audience") or "").strip()  # G1.36 honne/tatemae
    retry_visual_checkpoint_id = (
        form.get("retry_visual_checkpoint_id") or ""
    ).strip()
    retry_visual_source_conversation_id = (
        form.get("retry_visual_source_conversation_id") or ""
    ).strip()
    # Obsidian Plugin Design (2026-05-17) — same override field as /chat.
    output_destination    = (form.get("output_destination") or "").strip()
    # Install Chunk 2c — same config_name field as /chat for per-request
    # named-configuration selection.
    config_name           = (form.get("config_name") or "").strip() or None
    try:
        config_name = _validate_public_model_profile_override(config_name)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 400)
    exhibits_submission_intent = (
        form.get("exhibits_submission_intent") or ""
    ).strip()
    visual_editor = (form.get("visual_editor") or "").strip()
    visual_native_file = request.files.get("visual_native")
    visual_preview_file = request.files.get("canvas_preview_png")
    # Capture raw optional values once.  History is parsed as a legacy/API
    # fallback only; an existing conversation.json remains authoritative.
    spatial_raw = form.get("spatial_representation", "")
    annotations_raw = form.get("annotations", "")
    history_raw_str = form.get("history", "")
    supplied_history = []
    if history_raw_str:
        try:
            supplied_history = json.loads(history_raw_str)
            if not isinstance(supplied_history, list):
                supplied_history = []
        except Exception:
            supplied_history = []

    if (visual_native_file is None) != (visual_preview_file is None):
        return _json_response({
            "error": "visual_native and canvas_preview_png must be supplied together",
        }, 400)
    if visual_native_file is not None and visual_editor not in {"excalidraw", "konva"}:
        return _json_response({"error": "invalid visual_editor"}, 400)
    if not user_input and visual_native_file is None:
        return json.dumps({"error": "empty message"}), 400
    if not conversation_id:
        return json.dumps({"error": "missing conversation_id"}), 400
    if (not _valid_live_conversation_id(conversation_id)
            or not _valid_live_conversation_id(panel_id)):
        return json.dumps({"error": "invalid conversation_id"}), 400
    if conversation_id != panel_id:
        # Legacy multipart callers used the placeholder panel_id="main".
        # Canonicalize that alias to the explicit conversation_id so uploads,
        # pending logs, envelopes, and purge all share one key.
        if panel_id == "main":
            panel_id = conversation_id
        else:
            return json.dumps({
                "error": "conversation_id and panel_id must match",
            }), 400
    if exhibits_submission_intent not in {"", "explicit_send"}:
        return _json_response({
            "error": "invalid Exhibits submission intent",
            "required": "explicit_send",
        }, 422)

    # Validate structured visual metadata before creating any durable files.
    spatial_rep = None
    if spatial_raw:
        try:
            spatial_rep = json.loads(spatial_raw)
        except Exception as exc:
            return _json_response({
                "error": "invalid spatial_representation JSON",
                "detail": str(exc),
            }, 400)
        try:
            from visual_validator import validate_spatial_representation
            result = validate_spatial_representation(spatial_rep)
            if not result.valid:
                return _json_response({
                    "error": "spatial_representation failed validation",
                    "errors": [error.as_dict() for error in result.errors],
                    "warnings": [warning.as_dict() for warning in result.warnings],
                }, 400)
        except Exception as exc:
            print(f"[WARNING] spatial_representation validation error: {exc}")
            spatial_rep = None

    annotations_payload = None
    if annotations_raw:
        try:
            annotations_parsed = json.loads(annotations_raw)
        except Exception as exc:
            return _json_response({
                "error": "invalid annotations JSON", "detail": str(exc),
            }, 400)
        try:
            from visual_validator import validate_annotations
            result = validate_annotations(annotations_parsed)
            if not result.valid:
                return _json_response({
                    "error": "annotations failed validation",
                    "errors": [error.as_dict() for error in result.errors],
                    "warnings": [warning.as_dict() for warning in result.warnings],
                }, 400)
            annotations_payload = (
                {"annotations": annotations_parsed}
                if isinstance(annotations_parsed, list)
                else annotations_parsed
            )
        except Exception as exc:
            print(f"[WARNING] annotations validation error: {exc}")
            annotations_payload = None

    if (retry_visual_checkpoint_id
            and not _VISUAL_CHECKPOINT_ID_RE.fullmatch(retry_visual_checkpoint_id)):
        return _json_response({"error": "invalid retry visual checkpoint"}, 400)
    if (retry_visual_source_conversation_id
            and not _valid_live_conversation_id(
                retry_visual_source_conversation_id
            )):
        return _json_response({"error": "invalid retry visual source Dialogue"}, 400)

    # Serialize artifact capture with Delete Forever. If deletion starts
    # while this block is active it waits, then removes every upload/log this
    # request created; if deletion already started this request creates none.
    with _conversation_lifecycle_lock(panel_id):
        if _is_conversation_deleted(panel_id):
            return json.dumps({
                "status": "deleted", "conversation_id": panel_id,
            }), 410
        if _is_conversation_closed(panel_id):
            return json.dumps({
                "status": "closed", "conversation_id": panel_id,
            }), 409
        try:
            _assert_no_casefold_session_collision(panel_id)
        except (ValueError, RuntimeError) as exc:
            return json.dumps({"error": str(exc)}), 409
        tag = _effective_conversation_tag(panel_id, tag)
        history, history_state = _authoritative_dialogue_history(
            panel_id, supplied_history,
        )

        # Allocate the existing submission identity before any checkpoint
        # write. It names both immutable visual files and the pending marker.
        submission_id = _new_submission_id()

        created_paths: list[str] = []

        def reject_uncommitted(payload, status):
            for path in created_paths:
                try:
                    if os.path.isfile(path) and not os.path.islink(path):
                        os.remove(path)
                except OSError:
                    pass
            return _json_response(payload, status)

        # Optional image upload — saved first so the pending record can carry
        # the path. Image binaries live separately on disk; the pending file
        # carries only the path reference, not the bytes.
        image_path = None
        image_mime = None
        file_storage = request.files.get("image")
        if file_storage is not None:
            image_mime = file_storage.mimetype or "image/png"
            image_path = _save_multipart_image(conversation_id, file_storage)
            if image_path:
                created_paths.append(image_path)

        # Native scene and canonical preview are one accepted checkpoint. The
        # pending submission is written LAST and therefore acts as the commit
        # marker that authorizes the model call.
        visual_checkpoint_id = None
        canvas_preview_path = None
        visual_native_path = None
        checkpoint_paths = ()
        if visual_native_file is not None:
            try:
                native = visual_native_file.read(_VISUAL_NATIVE_MAX_BYTES + 1)
                preview = visual_preview_file.read(_VISUAL_PREVIEW_MAX_BYTES + 1)
            except Exception as exc:
                return reject_uncommitted({
                    "error": "visual checkpoint read failed", "message": str(exc),
                }, 400)
            try:
                checkpoint_paths = _write_visual_checkpoint(
                    conversation_id, submission_id, visual_editor, native, preview,
                    require_content=not user_input,
                )
            except ValueError as exc:
                return reject_uncommitted({"error": str(exc)}, 400)
            except Exception as exc:
                return reject_uncommitted({
                    "error": "visual checkpoint write failed", "message": str(exc),
                }, 500)
            created_paths.extend(checkpoint_paths)
            visual_checkpoint_id = submission_id
            visual_native_path = checkpoint_paths[0]
            canvas_preview_path = checkpoint_paths[1]
        elif retry_visual_checkpoint_id:
            retry_source_id = (
                retry_visual_source_conversation_id or conversation_id
            )
            try:
                retry_dir = str(rp.safe_owned_subdir(
                    CANVAS_ROOT,
                    _canonical_live_conversation_id(retry_source_id),
                    "canvas",
                    create=False,
                ))
            except (OSError, ValueError) as exc:
                return reject_uncommitted({
                    "error": "retry visual checkpoint is unavailable",
                    "message": str(exc),
                }, 409)
            retry_preview = os.path.join(
                retry_dir, retry_visual_checkpoint_id + ".preview.png",
            )
            retry_excalidraw = os.path.join(
                retry_dir, retry_visual_checkpoint_id + ".excalidraw",
            )
            retry_konva = os.path.join(
                retry_dir, retry_visual_checkpoint_id + ".ora-canvas",
            )
            if (not os.path.isfile(retry_preview) or os.path.islink(retry_preview)
                    or not any(
                        os.path.isfile(path) and not os.path.islink(path)
                        for path in (retry_excalidraw, retry_konva)
                    )):
                return reject_uncommitted({
                    "error": "retry visual checkpoint is unavailable",
                }, 409)
            source_native_path = (
                retry_excalidraw if os.path.isfile(retry_excalidraw) else retry_konva
            )
            source_editor = (
                "excalidraw" if source_native_path.endswith(".excalidraw") else "konva"
            )
            if retry_source_id == conversation_id:
                visual_checkpoint_id = retry_visual_checkpoint_id
                visual_native_path = source_native_path
                canvas_preview_path = retry_preview
            else:
                try:
                    from conversation_memory import load_conversation_json
                    retry_target = load_conversation_json(conversation_id) or {}
                except Exception as exc:
                    return reject_uncommitted({
                        "error": "retry visual checkpoint is unavailable",
                        "message": str(exc),
                    }, 409)
                if retry_target.get("parent_conversation_id") != retry_source_id:
                    return reject_uncommitted({
                        "error": "retry visual source is not the target Dialogue parent",
                    }, 409)
                try:
                    with open(source_native_path, "rb") as stream:
                        retry_native = stream.read(_VISUAL_NATIVE_MAX_BYTES + 1)
                    with open(retry_preview, "rb") as stream:
                        retry_preview_bytes = stream.read(_VISUAL_PREVIEW_MAX_BYTES + 1)
                    checkpoint_paths = _write_visual_checkpoint(
                        conversation_id,
                        submission_id,
                        source_editor,
                        retry_native,
                        retry_preview_bytes,
                    )
                except ValueError as exc:
                    return reject_uncommitted({
                        "error": "retry visual checkpoint is invalid",
                        "message": str(exc),
                    }, 409)
                except Exception as exc:
                    return reject_uncommitted({
                        "error": "retry visual checkpoint copy failed",
                        "message": str(exc),
                    }, 500)
                created_paths.extend(checkpoint_paths)
                visual_checkpoint_id = submission_id
                visual_native_path, canvas_preview_path = checkpoint_paths
            visual_editor = source_editor
        # Legacy/API callers post this as a data-URL form string. New clients
        # use a file with the same semantic field name in request.files.
        canvas_preview_data_url = (
            form.get("canvas_preview_png")
            or form.get("canvas_preview_png_data_url")
            or ""
        ).strip()
        if canvas_preview_data_url and not image_path and not canvas_preview_path:
            canvas_preview_path = _save_canvas_preview_png(
                conversation_id, canvas_preview_data_url,
            )
            if canvas_preview_path:
                created_paths.append(canvas_preview_path)

        committed_submission_id = _log_pending_submission({
            "endpoint":              "/chat/multipart",
            "conversation_id":       conversation_id,
            "panel_id":              panel_id,
            "is_main_feed":          is_main,
            "tag":                   tag,
            "user_input":            user_input,
            "history_raw":           history_raw_str,
            "history_source":        history_state["source"],
            "manual_mode_selection": manual_mode_selection,
            "manual_lens_selection": manual_lens_selection,
            "framework_selected":    framework_selected,
            "output_destination":    output_destination,
            "spatial_raw":           spatial_raw,
            "annotations_raw":       annotations_raw,
            "image_path":            image_path,
            "exhibits_submission_intent": exhibits_submission_intent,
            "visual_checkpoint_id": visual_checkpoint_id,
            "visual_editor": visual_editor or None,
            "visual_native_path": visual_native_path,
            "canvas_preview_path": canvas_preview_path,
            "retry_visual_source_conversation_id": (
                retry_visual_source_conversation_id or None
            ),
        }, submission_id=submission_id)
        if not committed_submission_id:
            return reject_uncommitted({"error": "submission commit failed"}, 500)

    # Build extra_context threaded into the pipeline
    extra_context = {}
    model_images = []
    if image_path is not None:
        model_images.append({
            "name": os.path.basename(image_path),
            "mime": image_mime or "image/png",
            "base64": base64.b64encode(Path(image_path).read_bytes()).decode("ascii"),
        })
    if canvas_preview_path is not None:
        model_images.append({
            "name": os.path.basename(canvas_preview_path),
            "mime": "image/png",
            "base64": base64.b64encode(
                Path(canvas_preview_path).read_bytes()
            ).decode("ascii"),
        })
    if visual_checkpoint_id is not None:
        extra_context["visual_checkpoint_id"] = visual_checkpoint_id
    if spatial_rep is not None:
        extra_context["spatial_representation"] = spatial_rep
    if image_path is not None:
        extra_context["image_path"] = image_path
    elif canvas_preview_path is not None:
        # V3 Item 12 Q1 follow-up — fall back to the canvas preview when
        # the user didn't attach an image. Vision-capable models route on
        # image_path; spatial_representation continues to feed text-only
        # models so neither path loses information.
        extra_context["image_path"]            = canvas_preview_path
        extra_context["image_source"]          = "canvas_preview"
    if annotations_payload is not None:
        extra_context["annotations"] = annotations_payload
    if (
        spatial_rep is not None
        or canvas_preview_path is not None
        or annotations_payload is not None
    ):
        spatial_digest = None
        if spatial_rep is not None:
            spatial_body = json.dumps(
                spatial_rep,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            spatial_digest = "sha256:" + hashlib.sha256(spatial_body).hexdigest()
        annotations_digest = None
        if annotations_payload is not None:
            annotations_body = json.dumps(
                annotations_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            annotations_digest = (
                "sha256:" + hashlib.sha256(annotations_body).hexdigest()
            )
        extra_context["exhibits_submission"] = {
            "schema_version": "ora.exhibits-submission/1.0",
            "transfer_method": (
                "explicit_send"
                if exhibits_submission_intent == "explicit_send"
                else "explicit_multipart_submission"
            ),
            "conversation_id": conversation_id,
            "submission_id": submission_id,
            "spatial_identity_digest": spatial_digest,
            "annotations_identity_digest": annotations_digest,
            "canvas_preview_attached": canvas_preview_path is not None,
            "authoritative": False,
            "run_effects": [],
        }
    # WP-5.3 — Spatial continuity across turns. Fetch the prior turn's
    # spatial_representation from either the in-memory history arg or
    # conversation.json on disk, and thread it through extra_context. The
    # pipeline's ``build_system_prompt_for_gear`` injects it under a
    # distinguishing fence so the model can see layout evolution.
    try:
        from conversation_memory import get_prior_spatial_state, get_prior_annotations
        prior_spatial = get_prior_spatial_state(conversation_id, history)
        if prior_spatial:
            extra_context["prior_spatial_representation"] = prior_spatial
        prior_annots = get_prior_annotations(conversation_id, history)
        if prior_annots:
            extra_context["prior_annotations"] = prior_annots
    except Exception as e:
        print(f"[WARNING] prior spatial state lookup failed: {e}")

    # Emit a log line so operators can see the merged inputs reached the server.
    annot_count = 0
    if annotations_payload and isinstance(annotations_payload.get("annotations"), list):
        annot_count = len(annotations_payload["annotations"])
    print(f"[chat/multipart] conversation_id={conversation_id} "
          f"spatial_rep={'yes' if spatial_rep else 'no'} "
          f"image={'yes' if image_path else 'no'} "
          f"annotations={annot_count} "
          f"manual_lens={manual_lens_selection or 'none'} "
          f"prior_spatial={'yes' if extra_context.get('prior_spatial_representation') else 'no'}")

    return _invoke_pipeline(
        user_input, history, panel_id, is_main,
        images=model_images or None,
        extra_context=extra_context or None,
        tag=tag,
        manual_mode_selection=manual_mode_selection,
        manual_lens_selection=manual_lens_selection,
        framework_selected=framework_selected,
        submission_id=submission_id,
        output_destination=output_destination,
        config_name=config_name,
        style_audience=style_audience,
    )


# ── WP-7.4.8: canvas save / autosave persistence ─────────────────────────────

# Canvas saves land here, partitioned by conversation_id like multipart uploads.
CANVAS_ROOT = os.path.join(str(rp.ORA_HOME), "sessions", "")

# Filename ceiling for raster previews. PNG data URLs from a 10000×10000
# Konva stage can balloon — we cap at 8 MB to keep autosave I/O bounded.
_PREVIEW_MAX_BYTES = 8 * 1024 * 1024


def _canvas_dir(conversation_id: str) -> str:
    """Resolve the canvas directory for a conversation, creating it if needed."""
    canonical_id = _canonical_live_conversation_id(conversation_id)
    return str(rp.safe_owned_subdir(
        CANVAS_ROOT, canonical_id, "canvas", create=True,
    ))


_VISUAL_CHECKPOINT_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
_VISUAL_NATIVE_MAX_BYTES = 64 * 1024 * 1024
_VISUAL_PREVIEW_MAX_BYTES = 32 * 1024 * 1024


def _validate_visual_checkpoint_payload(
        editor: str, native: bytes, preview: bytes,
        *, require_content: bool = False) -> None:
    """Validate the two immutable files before either reaches the canvas dir."""
    if editor not in {"excalidraw", "konva"}:
        raise ValueError("editor must be excalidraw or konva")
    if not native or len(native) > _VISUAL_NATIVE_MAX_BYTES:
        raise ValueError("invalid visual native payload size")
    if (not preview or len(preview) > _VISUAL_PREVIEW_MAX_BYTES
            or not preview.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ValueError("preview must be a valid bounded PNG")
    if editor == "excalidraw":
        try:
            scene = json.loads(native.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid Excalidraw scene: {exc}") from exc
        if (not isinstance(scene, dict)
                or scene.get("type") != "excalidraw"
                or not isinstance(scene.get("elements"), list)
                or not isinstance(scene.get("appState"), dict)
                or not isinstance(scene.get("files", {}), dict)):
            raise ValueError("invalid Excalidraw scene shape")
        if require_content and not any(
            isinstance(element, dict) and not element.get("isDeleted", False)
            for element in scene["elements"]
        ):
            raise ValueError("visual content is empty")
    else:
        from orchestrator import canvas_file_format as cff
        state = cff.read_bytes(native)
        if require_content and not state.get("objects"):
            raise ValueError("visual content is empty")


def _write_visual_checkpoint(
        conversation_id: str, checkpoint_id: str, editor: str,
        native: bytes, preview: bytes,
        *, require_content: bool = False) -> tuple[str, str]:
    """Write one immutable native+PNG checkpoint, cleaning up partial failure."""
    if not _VISUAL_CHECKPOINT_ID_RE.fullmatch(checkpoint_id or ""):
        raise ValueError("invalid checkpoint id")
    _validate_visual_checkpoint_payload(
        editor, native, preview, require_content=require_content,
    )
    out_dir = _canvas_dir(conversation_id)
    extension = ".excalidraw" if editor == "excalidraw" else ".ora-canvas"
    native_path = os.path.join(out_dir, checkpoint_id + extension)
    preview_path = os.path.join(out_dir, checkpoint_id + ".preview.png")
    if os.path.lexists(native_path) or os.path.lexists(preview_path):
        raise FileExistsError("visual checkpoint already exists")
    try:
        rp.atomic_write_bytes(native_path, native)
        rp.atomic_write_bytes(preview_path, preview)
    except Exception:
        for path in (native_path, preview_path):
            try:
                if os.path.isfile(path) and not os.path.islink(path):
                    os.remove(path)
            except OSError:
                pass
        raise
    return native_path, preview_path


@app.route("/api/canvas/checkpoint", methods=["POST"])
def canvas_checkpoint():
    """Durably create an immutable native scene and canonical PNG pair."""
    form = request.form
    conversation_id = (form.get("conversation_id") or "main").strip() or "main"
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, 400)
    editor = (form.get("editor") or "").strip()
    native_file = request.files.get("native")
    preview_file = request.files.get("preview")
    if native_file is None or preview_file is None:
        return _json_response({"error": "native and preview files are required"}, 400)
    native = native_file.read(_VISUAL_NATIVE_MAX_BYTES + 1)
    preview = preview_file.read(_VISUAL_PREVIEW_MAX_BYTES + 1)
    checkpoint_id = _new_submission_id()
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, 410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, form.get("tag", ""),
            )
            native_path, preview_path = _write_visual_checkpoint(
                conversation_id, checkpoint_id, editor, native, preview,
            )
        except ValueError as exc:
            return _json_response({"error": str(exc)}, 400)
        except Exception as exc:
            return _json_response({"error": "checkpoint write failed", "message": str(exc)}, 500)
    return _json_response({
        "ok": True,
        "checkpoint_id": checkpoint_id,
        "editor": editor,
        "path": native_path,
        "preview_path": preview_path,
    })


@app.route("/api/canvas/draft", methods=["POST"])
def canvas_excalidraw_draft():
    """Replace only latest.excalidraw; drafts never identify a turn."""
    form = request.form
    conversation_id = (form.get("conversation_id") or "main").strip() or "main"
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, 400)
    scene_file = request.files.get("scene")
    if scene_file is None:
        return _json_response({"error": "missing scene"}, 400)
    scene = scene_file.read(_VISUAL_NATIVE_MAX_BYTES + 1)
    try:
        # Validation requires a PNG for checkpoints; draft validation is the
        # same native scene shape without inventing a preview identity.
        parsed = json.loads(scene.decode("utf-8"))
        if (not isinstance(parsed, dict) or parsed.get("type") != "excalidraw"
                or not isinstance(parsed.get("elements"), list)
                or not isinstance(parsed.get("appState"), dict)):
            raise ValueError("invalid Excalidraw draft")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _json_response({"error": str(exc)}, 400)
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, 410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, form.get("tag", ""),
            )
            path = os.path.join(_canvas_dir(conversation_id), "latest.excalidraw")
            rp.atomic_write_bytes(path, scene)
        except Exception as exc:
            return _json_response({"error": "draft write failed", "message": str(exc)}, 500)
    return _json_response({"ok": True, "path": path})


@app.route("/api/canvas/visual-state/<conversation_id>", methods=["POST"])
def canvas_visual_state(conversation_id):
    """Atomically publish the active editor after its durable files exist."""
    conversation_id = (conversation_id or "").strip()
    if not _valid_live_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, 400)
    payload = request.get_json(silent=True) or {}
    state = payload.get("visual_state")
    if not isinstance(state, dict) or state.get("active_editor") not in {
        "excalidraw", "konva",
    }:
        return _json_response({"error": "invalid visual_state"}, 400)
    for key in ("resume_excalidraw_checkpoint_id", "konva_baseline_checkpoint_id"):
        value = state.get(key)
        if value is not None and not _VISUAL_CHECKPOINT_ID_RE.fullmatch(str(value)):
            return _json_response({"error": f"invalid {key}"}, 400)
    warning_acknowledged = state.get("konva_edit_warning_acknowledged")
    if warning_acknowledged is not None and not isinstance(warning_acknowledged, bool):
        return _json_response({"error": "invalid konva_edit_warning_acknowledged"}, 400)
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, 410)
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, payload.get("tag", ""),
            )
            from orchestrator.conversation_memory import set_visual_state
            path = set_visual_state(conversation_id, state)
            if path is None:
                raise OSError("conversation envelope mutation failed")
        except Exception as exc:
            return _json_response({"error": "visual state write failed", "message": str(exc)}, 500)
    return _json_response({"ok": True, "visual_state": state})


def _decode_preview_data_url(data_url: str) -> bytes | None:
    """Decode an image/png data URL to raw PNG bytes. Returns None on any
    parse failure or when the decoded bytes exceed _PREVIEW_MAX_BYTES."""
    if not data_url or not isinstance(data_url, str):
        return None
    m = re.match(r"^data:image/png;base64,(.+)$", data_url, re.IGNORECASE)
    if not m:
        return None
    try:
        import base64
        raw = base64.b64decode(m.group(1), validate=False)
    except Exception:
        return None
    if len(raw) > _PREVIEW_MAX_BYTES:
        return None
    return raw


def _write_canvas_artifacts(conversation_id: str, blob: bytes,
                            preview_data_url: str | None):
    out_dir = _canvas_dir(conversation_id)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    canvas_path = os.path.join(out_dir, f"{ts}.ora-canvas")
    latest_path = os.path.join(out_dir, "latest.ora-canvas")
    rp.atomic_write_bytes(canvas_path, blob)
    rp.atomic_write_bytes(latest_path, blob)

    preview_path = None
    if preview_data_url:
        png_bytes = _decode_preview_data_url(preview_data_url)
        if png_bytes is not None:
            preview_path = os.path.join(out_dir, f"{ts}.preview.png")
            try:
                rp.atomic_write_bytes(preview_path, png_bytes)
                rp.atomic_write_bytes(
                    os.path.join(out_dir, "latest.preview.png"), png_bytes,
                )
            except Exception as exc:
                print(f"[WARNING] canvas_save preview write failed: {exc}")
                preview_path = None
    return canvas_path, latest_path, preview_path


@app.route("/api/canvas/save", methods=["POST"])
def canvas_save():
    """WP-7.4.8 — Persist a canvas-state file (gzip-compressed) and an
    optional raster preview under ``~/ora/sessions/<conversation_id>/canvas/``.

    Accepts ``multipart/form-data`` with fields:
      * ``conversation_id`` (required) — partitions the storage tree
      * ``canvas`` (required, file) — gzip-compressed canvas-state bytes
        produced by ``OraCanvasFileFormat.write()``
      * ``preview`` (optional, str) — image/png data URL of the current view
      * ``reason`` (optional, str) — diagnostic hint ('manual', 'autosave',
        'ai-generation', 'large-paste', 'image-upload')

    Behavior:
      1. Validates conversation_id and writes the canvas bytes to a
         timestamped file (``<ts>.ora-canvas``) plus a stable
         ``latest.ora-canvas`` mirror.
      2. Optionally decodes the preview data URL and writes
         ``<ts>.preview.png`` next to the canvas file.
      3. Validates the bytes via ``orchestrator.canvas_file_format.read_bytes``
         to catch corruption early — a parse failure returns 400 BEFORE any
         file is written.

    Returns ``{ ok, path, latest, preview_path?, reason }`` on success or
    ``{ error, message }`` with 400 on validation failure.
    """
    try:
        from orchestrator import canvas_file_format as cff
    except Exception as e:
        return json.dumps({"error": "canvas_file_format unavailable", "message": str(e)}), 500

    form = request.form
    conversation_id = (form.get("conversation_id") or "main").strip() or "main"
    if not _valid_live_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    reason = (form.get("reason") or "autosave").strip() or "autosave"
    preview_data_url = form.get("preview") or None

    canvas_file = request.files.get("canvas")
    if canvas_file is None:
        return json.dumps({"error": "missing canvas field"}), 400
    blob = canvas_file.read()
    if not blob:
        return json.dumps({"error": "empty canvas payload"}), 400

    # Validate by parsing — catches corruption before persistence.
    try:
        state = cff.read_bytes(blob)
    except Exception as e:
        return json.dumps({"error": "invalid canvas bytes", "message": str(e)}), 400

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({"status": "deleted"}), 410
        try:
            _ensure_artifact_conversation_envelope(
                conversation_id, form.get("tag", ""),
            )
            canvas_path, latest_path, preview_path = _write_canvas_artifacts(
                conversation_id, blob, preview_data_url,
            )
        except Exception as e:
            return json.dumps({"error": "write failed", "message": str(e)}), 500

    extent = None
    try:
        extent = (state.get("metadata") or {}).get("content_extent")
    except Exception:
        extent = None
    objects_count = len(state.get("objects") or [])
    print(f"[canvas/save] conversation_id={conversation_id} reason={reason} "
          f"objects={objects_count} canvas={canvas_path} preview={'yes' if preview_path else 'no'}")

    return json.dumps({
        "ok": True,
        "path": canvas_path,
        "latest": latest_path,
        "preview_path": preview_path,
        "reason": reason,
        "objects": objects_count,
        "content_extent": extent,
    })


@app.route("/api/canvas/load/<conversation_id>", methods=["GET"])
def canvas_load(conversation_id):
    """Return an exact immutable visual checkpoint or a legacy Konva save.

    ``?checkpoint=<id>`` is authoritative for new turns. ``?turn=<idx>`` is
    retained only for conversations created before checkpoint ids existed.
    ``?preview=1`` returns the checkpoint's canonical flattened PNG.

    Response shape::

        200 application/octet-stream  — raw gzipped canvas-state bytes
        404 application/json           — {"error": "no canvas saved"}
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    if _is_conversation_deleted(conversation_id):
        return json.dumps({"status": "deleted"}), 410
    try:
        canvas_dir = str(rp.safe_owned_subdir(
            CANVAS_ROOT, conversation_id, "canvas", create=False,
        ))
    except ValueError as exc:
        return json.dumps({"error": str(exc)}), 409

    checkpoint_arg = (request.args.get("checkpoint") or "").strip()
    turn_arg = request.args.get("turn")
    draft_arg = (request.args.get("draft") or "").strip()
    preview_only = request.args.get("preview") in {"1", "true", "yes"}
    target_path: str | None = None
    editor = "konva"

    if checkpoint_arg:
        if not _VISUAL_CHECKPOINT_ID_RE.fullmatch(checkpoint_arg):
            return _json_response({"error": "invalid checkpoint id"}, 400)
        if preview_only:
            target_path = os.path.join(canvas_dir, checkpoint_arg + ".preview.png")
            # Editor remains useful to recovery callers even for a preview.
            if os.path.isfile(os.path.join(canvas_dir, checkpoint_arg + ".excalidraw")):
                editor = "excalidraw"
        else:
            excalidraw_path = os.path.join(canvas_dir, checkpoint_arg + ".excalidraw")
            konva_path = os.path.join(canvas_dir, checkpoint_arg + ".ora-canvas")
            if os.path.isfile(excalidraw_path) and not os.path.islink(excalidraw_path):
                target_path = excalidraw_path
                editor = "excalidraw"
            elif os.path.isfile(konva_path) and not os.path.islink(konva_path):
                target_path = konva_path
    elif draft_arg:
        if draft_arg != "excalidraw" or preview_only:
            return _json_response({"error": "invalid draft selector"}, 400)
        target_path = os.path.join(canvas_dir, "latest.excalidraw")
        editor = "excalidraw"
    elif turn_arg is not None:
        try:
            turn_idx = int(turn_arg)
        except (TypeError, ValueError):
            return json.dumps({"error": "invalid turn index"}), 400, {"Content-Type": "application/json"}
        if not os.path.isdir(canvas_dir):
            return json.dumps({"error": "no canvas saved"}), 404, {"Content-Type": "application/json"}
        # Per-turn snapshots are filename-timestamped; sort lexicographically
        # which equals chronologically for the YYYYMMDD-HHMMSS pattern emitted
        # by OraSaveCanvas. Exclude the rolling latest mirror and any
        # preview PNG sidecars.
        snaps = sorted(
            f for f in os.listdir(canvas_dir)
            if re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9]{6}\.ora-canvas", f)
        )
        if not snaps or turn_idx < 0 or turn_idx >= len(snaps):
            return json.dumps({"error": "no canvas for that turn", "available": len(snaps)}), 404, {"Content-Type": "application/json"}
        target_path = os.path.join(canvas_dir, snaps[turn_idx])
    else:
        target_path = os.path.join(canvas_dir, "latest.ora-canvas")

    if not target_path or not os.path.exists(target_path):
        return json.dumps({"error": "no canvas saved"}), 404, {"Content-Type": "application/json"}
    if os.path.islink(target_path) or not os.path.isfile(target_path):
        return json.dumps({"error": "canvas path is not a regular file"}), 409, {"Content-Type": "application/json"}
    try:
        with open(target_path, "rb") as f:
            blob = f.read()
    except Exception as e:
        return json.dumps({"error": "read failed", "message": str(e)}), 500, {"Content-Type": "application/json"}
    response = Response(
        blob,
        mimetype="image/png" if preview_only else "application/octet-stream",
    )
    response.headers["X-Ora-Visual-Editor"] = editor
    response.headers["Cache-Control"] = "no-store"
    return response


# ── V3 Phase 2: conversation list + fetch + mark-read ────────────────────────

@app.route("/api/conversations", methods=["GET"])
def conversations_list():
    """Return all conversations grouped into Pending / Unread / Active.

    Walks ``~/ora/sessions/`` and reads each conversation.json envelope to
    build summary rows. Combines with the in-memory ``_pending_conversations``
    set to identify conversations currently mid-pipeline.

    Grouping rules:
      * **pending** — conversation is currently processing a pipeline run
      * **unread** — not pending AND has at least one assistant message AND
        (``last_read_at`` is null OR ``last_activity_at`` > ``last_read_at``)
      * **active** — everything else

    Each group is sorted by ``last_activity_at`` descending (most recent
    first; nulls sort last). Response shape::

        {
          "pending": [<row>, ...],
          "unread":  [<row>, ...],
          "active":  [<row>, ...]
        }

    where each row carries: ``conversation_id``, ``tag``, ``title``,
    ``message_count``, ``last_activity_at``, ``last_read_at``, ``pending``.
    """
    try:
        from conversation_memory import iter_conversations, ensure_welcome_thread
    except Exception as e:
        return json.dumps({"error": f"iter_conversations import failed: {e}"}), 500

    # V3 spec §6.2 — WELCOME thread. The strict-spec behavior is "first
    # launch only" (only_if_first_launch=True), but the placeholder rollout
    # explicitly intends WELCOME to appear for existing users too as the
    # marker that the help system is under construction. We bypass the
    # first-launch gate so the envelope appears once for everyone; deletion
    # by the user is still respected (existence check prevents recreation).
    try:
        ensure_welcome_thread(only_if_first_launch=False)
    except Exception:
        pass  # Best-effort; never break the list endpoint over a welcome glitch.

    try:
        rows = iter_conversations()
    except Exception as e:
        return json.dumps({"error": f"iter_conversations failed: {e}"}), 500

    # G1.33 — server-side project filter. ?project_id=<nexus> narrows the
    # pinned / unread / active groups to that project; errored + pending
    # (running) PIERCE the filter and stay GLOBAL, so background work and
    # failures aren't hidden while you work in another project (the locked
    # switcher spec). Absent / "commons" / legacy "general" == the
    # all-inclusive view.
    _project_id = (request.args.get("project_id") or "").strip()
    _all_projects = (not _project_id) or _project_id.lower() in ("commons", "general")

    def _in_project(r):
        return _all_projects or (_project_id in (r.get("project_ids") or []))

    pinned: list[dict] = []
    errored: list[dict] = []
    pending: list[dict] = []
    unread: list[dict] = []
    active: list[dict] = []

    for row in rows:
        cid = row["conversation_id"]
        is_pending = cid in _pending_conversations
        row = dict(row)  # shallow copy so we can add the pending flag
        row["pending"] = is_pending

        # V3 Backlog 3F — user-pinned conversations and the WELCOME thread
        # both surface in the Pinned group at the top of the list,
        # regardless of pending / unread / active classification.
        if row.get("is_welcome") or row.get("pinned"):
            if _in_project(row):  # pins are per-project
                pinned.append(row)
            continue

        # Backlog item 11 — errored conversations get their own group.
        # Errored takes priority over Pending so a stuck-and-failed run
        # doesn't disappear into the Pending group.
        if row.get("last_status") == "errored":
            errored.append(row)
            continue

        if is_pending:
            pending.append(row)
            continue

        # Unread/active are project-scoped (errored + pending above are global).
        if not _in_project(row):
            continue

        # Unread heuristic: there's at least one assistant turn AND either no
        # read timestamp yet OR activity has advanced since the last read.
        has_assistant_response = (row.get("message_count") or 0) >= 2
        last_act = row.get("last_activity_at")
        last_read = row.get("last_read_at")
        if has_assistant_response and last_act and (last_read is None or last_act > last_read):
            unread.append(row)
        else:
            active.append(row)

    def _sort_key(r):
        # Sort by last_activity_at descending; None goes last.
        ts = r.get("last_activity_at")
        return (ts is None, "" if ts is None else ts)

    pending.sort(key=_sort_key)
    unread.sort(key=_sort_key)
    # Active descending by activity (most recent first); reverse the natural
    # sort so the leading None values stay at the bottom.
    active.sort(key=lambda r: (r.get("last_activity_at") or ""), reverse=True)
    # Repeat the descending sort for unread/pending (the _sort_key returns
    # ascending; flip them).
    unread.sort(key=lambda r: (r.get("last_activity_at") or ""), reverse=True)
    pending.sort(key=lambda r: (r.get("last_activity_at") or ""), reverse=True)
    errored.sort(key=lambda r: (r.get("last_activity_at") or ""), reverse=True)

    return json.dumps({
        "pinned":  pinned,
        "errored": errored,
        "pending": pending,
        "unread":  unread,
        "active":  active,
    })


_LOW_VALUE_BROWSER_SNIPPET_PATTERNS = (
    "meta-layer oversight: simulated",
    "oversight is running in simulated mode",
    "pipeline-execution warning",
    "prompt cleanup couldn't parse",
    "the pipeline ran against the model's narrative response",
)


def _clean_conversation_browser_text(text: str) -> str:
    text = str(text or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[\s>•*-]*[⚠️ℹ️✅❌]\s*", "", text)
    text = re.sub(
        r"^\*\*(?:Meta-layer oversight: simulated|Pipeline-execution warning)\*\*\s*[-–—>]*\s*",
        "",
        text,
        flags=re.I,
    )
    return text.strip()


def _is_low_value_browser_snippet(text: str) -> bool:
    low = _clean_conversation_browser_text(text).lower()
    return any(p in low for p in _LOW_VALUE_BROWSER_SNIPPET_PATTERNS)


def _fallback_conversation_browser_snippet(messages: list, title: str) -> tuple[str, int | None, int | None]:
    """Pick a useful one-line browse clip when there is no search query."""
    turn_idx = -1
    indexed: list[tuple[int, int, dict]] = []
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "user":
            turn_idx += 1
        indexed.append((idx, max(0, turn_idx), msg))

    title_l = _clean_conversation_browser_text(title).lower()
    for idx, t_idx, msg in reversed(indexed):
        text = _clean_conversation_browser_text(msg.get("content") or "")
        if not text or _is_low_value_browser_snippet(text):
            continue
        if title_l and text.lower() == title_l:
            continue
        return text[:420], idx, t_idx
    return (_clean_conversation_browser_text(title)[:420], None, None)


def _conversation_search_snippet(data: dict, query: str) -> dict:
    messages = data.get("messages") if isinstance(data.get("messages"), list) else []
    terms = _browser_terms(query) if "_browser_terms" in globals() else [
        t.lower() for t in re.findall(r"\w+", query or "") if len(t) > 2
    ]
    title = data.get("display_name") if isinstance(data.get("display_name"), str) else ""
    if not title:
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                title = str(msg.get("content") or "").strip().replace("\n", " ")[:80]
                break
    title_l = title.lower()
    description = _clean_conversation_browser_text(data.get("description") or "")
    best = {
        "score": 0,
        "snippet": "",
        "matched_message_index": None,
        "matched_turn_index": None,
    }
    if terms and title_l:
        hits = sum(1 for t in terms if t in title_l)
        if hits:
            best.update({"score": hits * 4, "snippet": title[:220]})
    if terms and description:
        description_hits = sum(1 for term in terms if term in description.lower())
        if description_hits and description_hits * 3.5 > best["score"]:
            best.update({
                "score": description_hits * 3.5,
                "snippet": _browser_snippet_from_text(description, query),
            })

    last_text = ""
    turn_idx = -1
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "user":
            turn_idx += 1
        text = _clean_conversation_browser_text(msg.get("content") or "")
        if text:
            last_text = text
        if _is_low_value_browser_snippet(text):
            continue
        haystack = text.lower()
        if not terms:
            continue
        hits = sum(1 for t in terms if t in haystack)
        if hits and hits * 3 + min(len(text), 800) / 800 > best["score"]:
            start = 0
            for t in terms:
                pos = haystack.find(t)
                if pos >= 0:
                    start = max(0, pos - 80)
                    break
            snippet = text[start:start + 260]
            best.update({
                "score": hits * 3 + min(len(text), 800) / 800,
                "snippet": snippet,
                "matched_message_index": idx,
                "matched_turn_index": max(0, turn_idx),
            })

    if not terms:
        snippet, msg_idx, fallback_turn_idx = _fallback_conversation_browser_snippet(messages, title)
        best["score"] = 1
        best["snippet"] = snippet or (description or last_text or title or "").strip()[:420]
        best["matched_message_index"] = msg_idx
        best["matched_turn_index"] = fallback_turn_idx
    return best


_BROWSER_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "were", "what", "when", "where", "which", "who", "why",
    "with",
}

_BROWSER_KNOWLEDGE_TYPES = {"engram", "chat", "resource", "working"}


def _browser_terms(query: str) -> list[str]:
    return [
        t.lower()
        for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query or "")
        if len(t) > 2 and t.lower() not in _BROWSER_SEARCH_STOPWORDS
    ]


def _browser_match_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in _browser_terms(query):
        candidates = [term]
        candidates.extend(
            part for part in re.split(r"[-_]+", term)
            if len(part) > 2 and part not in _BROWSER_SEARCH_STOPWORDS
        )
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                terms.append(candidate)
    return terms


def _browser_is_knowledge_note(meta: dict) -> bool:
    return str((meta or {}).get("type") or "").lower() in _BROWSER_KNOWLEDGE_TYPES


def _browser_normalize_tags(value) -> list[str]:
    """Return stable, lowercase tags across live and legacy metadata forms.

    Knowledge records have existed with native lists, JSON-encoded lists,
    comma-delimited strings, and one plain scalar.  Library filtering must
    treat those layouts identically while preserving slash-qualified tags
    such as ``framework/instruction``.
    """
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        values = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        decoded = None
        if raw[:1] in "[({" and raw[-1:] in "])}":
            try:
                decoded = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                try:
                    import ast
                    decoded = ast.literal_eval(raw)
                except (SyntaxError, ValueError):
                    decoded = None
        if isinstance(decoded, (list, tuple, set, frozenset)):
            values = decoded
        else:
            values = raw.split(",") if "," in raw else [raw]
    else:
        values = [value]

    tags: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item is None or item == "":
            # Same rule the top-level guard applies, enforced per item: callers
            # pass composite sources such as [meta.get("tags"), meta.get("tag")]
            # and an absent key arrives as None. Without this, str(None) becomes
            # a literal "none" tag on every record that lacks the key — a
            # phantom entry in the Library's tag filters since 2026-08-11.
            continue
        if isinstance(item, (list, tuple, set, frozenset)):
            candidates = _browser_normalize_tags(item)
        elif isinstance(item, str) and (
            "," in item or (item[:1] in "[({" and item[-1:] in "])}")
        ):
            candidates = _browser_normalize_tags(item)
        else:
            cleaned = str(item).strip().strip("[](){}\"'").strip().lower()
            candidates = [cleaned] if cleaned else []
        for tag in candidates:
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags


def _browser_truthy_metadata(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _browser_metadata_tags(meta: dict | None) -> list[str]:
    meta = meta or {}
    tags = _browser_normalize_tags([meta.get("tags"), meta.get("tag")])
    seen = set(tags)
    # Boolean extracts are the canonical fast-filter fields and also cover
    # old records whose full ``tags`` metadata was never backfilled.
    for key, value in meta.items():
        if not str(key).startswith("tag_") or not _browser_truthy_metadata(value):
            continue
        tag = str(key)[len("tag_"):].strip().lower()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _browser_strictest_privacy_tag(*sources) -> str:
    """Return the most restrictive truthful tag across metadata sources."""
    tags: set[str] = set()
    for source in sources:
        if isinstance(source, dict):
            tags.update(_browser_metadata_tags(source))
        else:
            tags.update(_browser_normalize_tags(source))
    if "stealth" in tags:
        return "stealth"
    if "private" in tags:
        return "private"
    return ""


def _browser_row_tags(row: dict | None) -> list[str]:
    row = row or {}
    values = row.get("tags")
    if values in (None, "", []):
        values = row.get("tag")
    return _browser_normalize_tags(values)


def _browser_parse_requested_tags(values) -> list[str]:
    """Parse repeatable and comma-delimited ``tags`` query parameters."""
    return _browser_normalize_tags(list(values or []))


def _browser_row_matches_tag_filters(
    row: dict,
    *,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
) -> bool:
    tags = _browser_row_tags(row)
    row["tags"] = tags
    # ``show_archived`` governs archived knowledge, not archived-conversation
    # memory (which is the Library's normal Dialogue history lane).
    if row.get("source_kind") == "engram" and "archived" in tags and not show_archived:
        return False
    # Multiple selected tags deliberately narrow with AND semantics.
    return set(_browser_normalize_tags(required_tags)).issubset(tags)


def _browser_frontmatter_tags(content: str, *, path: str = "") -> list[str]:
    """Read tags from a Markdown note without letting YAML failures go quiet."""
    text = str(content or "")
    if not text.startswith("---"):
        return []
    match = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, flags=re.S)
    if not match:
        print(
            f"[conversation-browser] unterminated YAML frontmatter while reading tags: {path or '<memory>'}",
            file=sys.stderr,
        )
        return []
    frontmatter = match.group(1)
    try:
        import yaml
        parsed = yaml.safe_load(frontmatter) or {}
        if isinstance(parsed, dict):
            return _browser_normalize_tags(parsed.get("tags"))
        print(
            f"[conversation-browser] non-mapping YAML frontmatter while reading tags: {path or '<memory>'}",
            file=sys.stderr,
        )
    except Exception as exc:
        # Fail open, loudly.  A narrow fallback still recognizes ordinary
        # inline and block-list tags so an unrelated malformed field does not
        # make an archived note visible by default.
        print(
            f"[conversation-browser] YAML tag parse failed for {path or '<memory>'}: {exc}",
            file=sys.stderr,
        )

    inline = re.search(r"(?m)^tags:[ \t]*(.*?)[ \t]*$", frontmatter)
    if not inline:
        return []
    first = inline.group(1).strip()
    if first:
        return _browser_normalize_tags(first)
    tail = frontmatter[inline.end():]
    block: list[str] = []
    for line in tail.splitlines():
        item = re.match(r"^\s+-\s*(.*?)\s*$", line)
        if item:
            block.append(item.group(1))
            continue
        if line.strip() and not line[:1].isspace():
            break
    return _browser_normalize_tags(block)


def _browser_encode_source_id(prefix: str, value: str) -> str:
    import base64
    raw = str(value or "").encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{prefix}:{encoded}"


def _browser_decode_source_id(prefix: str, value: str) -> str | None:
    import base64
    value = str(value or "")
    marker = f"{prefix}:"
    if not value.startswith(marker):
        return None
    payload = value[len(marker):]
    payload += "=" * (-len(payload) % 4)
    try:
        return base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def _browser_resolve_path(path: str | None) -> str:
    if not path:
        return ""
    return os.path.abspath(os.path.expanduser(str(path)))


def _browser_source_title(meta: dict, doc: str = "") -> str:
    doc = str(doc or "")
    match = re.search(r"Conversation ['\"](.+?)['\"] on ", doc)
    if match:
        return _clean_conversation_browser_text(match.group(1))[:180]
    heading = re.search(r"^#\s+(.+)$", doc, flags=re.M)
    if heading:
        return _clean_conversation_browser_text(heading.group(1))[:180]
    for key in ("conversation_title", "title", "source"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            cleaned = _clean_conversation_browser_text(value)
            if cleaned:
                return cleaned[:180]
    for key in ("raw_path", "chunk_path", "obsidian_path", "path"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return os.path.splitext(os.path.basename(_browser_resolve_path(value)))[0][:180]
    return "(untitled)"


def _browser_snippet_from_text(text: str, query: str, *, limit: int = 420) -> str:
    cleaned = _clean_conversation_browser_text(text)
    if not cleaned:
        return ""
    terms = _browser_terms(query)
    haystack = cleaned.lower()
    start = 0
    for term in terms:
        pos = haystack.find(term)
        if pos >= 0:
            start = max(0, pos - 90)
            break
    snippet = cleaned[start:start + limit].strip()
    if start > 0:
        snippet = "..." + snippet
    if start + limit < len(cleaned):
        snippet += "..."
    return snippet


def _browser_match_score(query: str, title: str = "", text: str = "") -> float:
    terms = _browser_match_terms(query)
    if not terms:
        return 0.0
    import difflib
    clean_query = _clean_conversation_browser_text(query).lower()
    title_l = str(title or "").lower()
    text_l = str(text or "").lower()
    haystack = f"{title_l}\n{text_l}"

    def candidates(value: str) -> set[str]:
        raw = set(re.findall(r"[a-z0-9][a-z0-9_-]{2,}", value or ""))
        split = {
            part
            for token in raw
            for part in re.split(r"[-_]+", token)
            if len(part) > 2
        }
        return raw | split

    haystack_words = candidates(haystack)
    title_words = candidates(title_l)

    def strength(term: str, value: str, words: set[str]) -> float:
        if term in value:
            return 1.0
        if len(term) < 6:
            return 0.0
        best = 0.0
        for word in words:
            if abs(len(word) - len(term)) > max(2, int(len(term) * 0.35)):
                continue
            ratio = difflib.SequenceMatcher(None, term, word).ratio()
            if ratio > best:
                best = ratio
        return best if best >= 0.82 else 0.0

    term_strengths = [strength(term, haystack, haystack_words) for term in terms]
    title_strengths = [strength(term, title_l, title_words) for term in terms]
    score = (sum(term_strengths) / max(len(terms), 1)) * 100.0
    score += sum(title_strengths) * 10.0
    if clean_query and clean_query in text_l:
        score += 65.0
    if clean_query and clean_query in title_l:
        score += 90.0
    return score


def _browser_metadata_for_row(cur, row_id: int) -> dict:
    meta: dict = {}
    for key, s_val, i_val, f_val, b_val in cur.execute(
        """
        SELECT key, string_value, int_value, float_value, bool_value
        FROM embedding_metadata
        WHERE id = ?
        """,
        (row_id,),
    ).fetchall():
        if s_val is not None:
            value = s_val
        elif i_val is not None:
            value = int(i_val)
        elif f_val is not None:
            value = float(f_val)
        elif b_val is not None:
            value = bool(b_val)
        else:
            value = None
        meta[key] = value
    return meta


def _browser_chromadb_path() -> str:
    return os.path.join(WORKSPACE, "chromadb")


def _browser_physical_collection(logical: str) -> str:
    try:
        from orchestrator.embedding import resolve_collection
        return resolve_collection(logical)
    except Exception:
        defaults = {
            "knowledge": "knowledge",
            "conversations": "conversations",
            "atomics": "atomic_dedup",
        }
        try:
            cfg_path = os.path.join(WORKSPACE, "config", "chromadb.json")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return (cfg.get("collections") or {}).get(logical) or defaults.get(logical, logical)
        except Exception:
            return defaults.get(logical, logical)


def _browser_row_from_chroma_hit(
    *,
    logical_collection: str,
    embedding_id: str,
    document: str,
    metadata: dict,
    query: str,
    score: float,
) -> dict | None:
    doc = document or metadata.get("chroma:document") or ""
    if logical_collection == "conversations":
        row_tags = _browser_normalize_tags(
            [metadata.get("tags"), metadata.get("tag")]
        )
        source_id = (
            metadata.get("conversation_id")
            or metadata.get("raw_path")
            or metadata.get("chunk_path")
            or embedding_id
        )
        if not source_id:
            return None
        pair_num = metadata.get("pair_num")
        try:
            matched_turn = max(0, int(pair_num) - 1) if pair_num is not None else None
        except (TypeError, ValueError):
            matched_turn = None
        row_id = _browser_encode_source_id("archive", str(source_id))
        title = _browser_source_title(metadata, doc)
        snippet = _browser_snippet_from_text(doc, query)
        return {
            "conversation_id": row_id,
            "source_conversation_id": source_id,
            "result_type": "archive_conversation",
            "source_kind": "archive",
            "tag": metadata.get("tag") or "",
            "tags": row_tags,
            "title": title,
            "snippet": snippet,
            "matched_turn_index": matched_turn,
            "matched_message_index": None,
            "matched_chunk_id": embedding_id,
            "pair_num": pair_num,
            "total_turns": metadata.get("total_turns"),
            "score": score,
            "search_relevance": _browser_match_score(query, title, doc) if query else None,
            "last_activity_at": (
                metadata.get("timestamp_utc")
                or metadata.get("timestamp")
                or metadata.get("date")
                or ""
            ),
            "raw_path": metadata.get("raw_path") or "",
            "chunk_path": metadata.get("chunk_path") or metadata.get("obsidian_path") or "",
            "closed": False,
        }

    if logical_collection == "knowledge":
        if not _browser_is_knowledge_note(metadata):
            return None
        row_tags = _browser_metadata_tags(metadata)
        source_path = metadata.get("path") or metadata.get("obsidian_path")
        if not source_path:
            source = metadata.get("source")
            if source:
                source_path = str(rp.vault_dir() / "Engrams" / str(source))
        source_id = source_path or embedding_id
        row_id = _browser_encode_source_id("engram", str(source_id))
        title = _browser_source_title(metadata, doc)
        snippet = _browser_snippet_from_text(doc, query)
        return {
            "conversation_id": row_id,
            "source_conversation_id": source_id,
            "result_type": "engram" if str(metadata.get("type") or "").lower() in ("engram", "chat") else "knowledge_note",
            "source_kind": "engram",
            "tag": metadata.get("tags") or "",
            "tags": row_tags,
            "title": title,
            "snippet": snippet,
            "matched_turn_index": 0,
            "matched_message_index": 0,
            "matched_chunk_id": embedding_id,
            "score": score,
            "search_relevance": _browser_match_score(query, title, doc) if query else None,
            "last_activity_at": metadata.get("date modified") or metadata.get("date") or "",
            "path": source_path or "",
            "closed": False,
        }
    return None


def _browser_merge_best(rows_by_id: dict, row: dict | None) -> None:
    if not row or not row.get("conversation_id"):
        return
    existing = rows_by_id.get(row["conversation_id"])

    def rank(item: dict) -> tuple[float, float]:
        relevance = item.get("search_relevance")
        primary = relevance if relevance is not None else item.get("score")
        return (float(primary or 0), float(item.get("score") or 0))

    if existing is None or rank(row) > rank(existing):
        rows_by_id[row["conversation_id"]] = row


def _browser_chroma_exact_rows(
    query: str,
    *,
    logical_collection: str,
    limit: int,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
) -> list[dict]:
    terms = _browser_terms(query)
    if not terms:
        return []
    physical = _browser_physical_collection(logical_collection)
    fts_queries: list[tuple[str, float]] = []
    clean_query = re.sub(r'"', " ", query or "").strip()
    if len(clean_query) >= 8:
        fts_queries.append((f'"{clean_query}"', 180.0))
    if terms:
        fts_queries.append((" ".join(terms), 140.0))
    if len(terms) > 1:
        fts_queries.append((" OR ".join(terms), 95.0))

    out: dict[str, dict] = {}
    try:
        import sqlite3
        con = sqlite3.connect(os.path.join(_browser_chromadb_path(), "chroma.sqlite3"))
        cur = con.cursor()
        seen_row_ids: set[int] = set()
        for fts_query, boost in fts_queries:
            try:
                matches = cur.execute(
                    """
                    SELECT embedding_fulltext_search.rowid,
                           embeddings.embedding_id,
                           embedding_fulltext_search.string_value,
                           bm25(embedding_fulltext_search) AS rank
                    FROM embedding_fulltext_search
                    JOIN embeddings ON embeddings.id = embedding_fulltext_search.rowid
                    JOIN segments ON segments.id = embeddings.segment_id
                    JOIN collections ON collections.id = segments.collection
                    WHERE collections.name = ?
                      AND embedding_fulltext_search.string_value MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (physical, fts_query, max(limit, 20)),
                ).fetchall()
            except Exception:
                continue
            for row_id, embedding_id, fts_text, rank in matches:
                if row_id in seen_row_ids:
                    continue
                seen_row_ids.add(row_id)
                meta = _browser_metadata_for_row(cur, row_id)
                if logical_collection == "knowledge" and not _browser_is_knowledge_note(meta):
                    continue
                doc = meta.get("chroma:document") or fts_text or ""
                term_hits = sum(1 for term in terms if term in doc.lower())
                score = boost + (term_hits * 4.0) - min(abs(float(rank or 0)), 50.0) / 20.0
                candidate = _browser_row_from_chroma_hit(
                    logical_collection=logical_collection,
                    embedding_id=embedding_id,
                    document=doc,
                    metadata=meta,
                    query=query,
                    score=score,
                )
                if candidate and _browser_row_matches_tag_filters(
                    candidate,
                    required_tags=required_tags,
                    show_archived=show_archived,
                ):
                    _browser_merge_best(out, candidate)
        con.close()
    except Exception as exc:
        print(f"[conversation-browser] exact {logical_collection} search failed: {exc}", file=sys.stderr)
    return sorted(out.values(), key=lambda r: float(r.get("score") or 0), reverse=True)[:limit]


def _browser_fuzzy_fts_query(query: str) -> str:
    grams: list[str] = []
    seen: set[str] = set()
    for term in _browser_match_terms(query):
        variants = {
            term,
            re.sub(r"[^a-z0-9]+", "", term.lower()),
        }
        for variant in variants:
            if len(variant) < 6:
                continue
            for idx in range(0, len(variant) - 2):
                gram = variant[idx:idx + 3]
                if len(gram) == 3 and gram not in seen:
                    seen.add(gram)
                    grams.append(gram)
                if len(grams) >= 80:
                    break
            if len(grams) >= 80:
                break
        if len(grams) >= 80:
            break
    return " OR ".join(f'"{gram}"' for gram in grams)


def _browser_chroma_fuzzy_rows(
    query: str,
    *,
    logical_collection: str,
    limit: int,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
) -> list[dict]:
    fts_query = _browser_fuzzy_fts_query(query)
    if not fts_query:
        return []
    physical = _browser_physical_collection(logical_collection)
    out: dict[str, dict] = {}
    try:
        import sqlite3
        con = sqlite3.connect(os.path.join(_browser_chromadb_path(), "chroma.sqlite3"))
        cur = con.cursor()
        matches = cur.execute(
            """
            SELECT embedding_fulltext_search.rowid,
                   embeddings.embedding_id,
                   embedding_fulltext_search.string_value,
                   bm25(embedding_fulltext_search) AS rank
            FROM embedding_fulltext_search
            JOIN embeddings ON embeddings.id = embedding_fulltext_search.rowid
            JOIN segments ON segments.id = embeddings.segment_id
            JOIN collections ON collections.id = segments.collection
            WHERE collections.name = ?
              AND embedding_fulltext_search.string_value MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (physical, fts_query, max(limit * 4, 80)),
        ).fetchall()
        for row_id, embedding_id, fts_text, rank in matches:
            meta = _browser_metadata_for_row(cur, row_id)
            if logical_collection == "knowledge" and not _browser_is_knowledge_note(meta):
                continue
            doc = meta.get("chroma:document") or fts_text or ""
            title = _browser_source_title(meta, doc)
            relevance = _browser_match_score(query, title, doc)
            if relevance < 58.0:
                continue
            score = 80.0 + relevance - min(abs(float(rank or 0)), 50.0) / 20.0
            candidate = _browser_row_from_chroma_hit(
                logical_collection=logical_collection,
                embedding_id=embedding_id,
                document=doc,
                metadata=meta,
                query=query,
                score=score,
            )
            if candidate and _browser_row_matches_tag_filters(
                candidate,
                required_tags=required_tags,
                show_archived=show_archived,
            ):
                _browser_merge_best(out, candidate)
        con.close()
    except Exception as exc:
        print(f"[conversation-browser] fuzzy {logical_collection} search failed: {exc}", file=sys.stderr)
    return _browser_sort_rows(list(out.values()), "relevance")[:limit]


def _browser_vault_markdown_rows(
    query: str,
    limit: int = 40,
    *,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
    vault_root: str | None = None,
) -> list[dict]:
    if not (query or "").strip():
        return []
    vault_root = vault_root or str(rp.vault_dir())
    if not os.path.isdir(vault_root):
        return []
    terms = _browser_match_terms(query)
    query_grams: set[str] = set()
    for term in terms:
        compact = re.sub(r"[^a-z0-9]+", "", term)
        if len(compact) >= 6:
            query_grams.update(
                compact[idx:idx + 3]
                for idx in range(0, len(compact) - 2)
            )

    def plausible_title(title: str) -> bool:
        title_l = title.lower()
        if any(term in title_l for term in terms):
            return True
        compact = re.sub(r"[^a-z0-9]+", "", title_l)
        if len(compact) < 6 or not query_grams:
            return False
        title_grams = {
            compact[idx:idx + 3]
            for idx in range(0, len(compact) - 2)
        }
        return len(query_grams & title_grams) >= 4

    rows: list[dict] = []
    skipped_dirs = {
        ".git", ".obsidian", ".trash", "Archive", "node_modules", "__pycache__",
    }
    try:
        for root, dirs, files in os.walk(vault_root):
            dirs[:] = [d for d in dirs if d not in skipped_dirs and not d.startswith(".")]
            for name in files:
                if not name.lower().endswith(".md"):
                    continue
                path = os.path.join(root, name)
                title = os.path.splitext(name)[0]
                if not plausible_title(title):
                    continue
                filename_score = _browser_match_score(query, title, title)
                if filename_score < 48.0:
                    continue
                content = ""
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read(40000)
                except OSError as exc:
                    print(
                        f"[conversation-browser] vault Markdown read failed for {path}: {exc}",
                        file=sys.stderr,
                    )
                tags = _browser_frontmatter_tags(content, path=path)
                candidate_identity = {
                    "source_kind": "engram",
                    "tags": tags,
                }
                if not _browser_row_matches_tag_filters(
                    candidate_identity,
                    required_tags=required_tags,
                    show_archived=show_archived,
                ):
                    continue
                content_l = content.lower()
                content_hits = sum(
                    1 for term in _browser_match_terms(query)
                    if term in content_l
                )
                score = filename_score + min(content_hits * 8.0, 40.0)
                if score < 58.0:
                    continue
                try:
                    modified = datetime.fromtimestamp(
                        os.path.getmtime(path),
                        tz=timezone.utc,
                    ).isoformat()
                except OSError:
                    modified = ""
                rows.append({
                    "conversation_id": _browser_encode_source_id("engram", path),
                    "source_conversation_id": path,
                    "result_type": "vault_note",
                    "source_kind": "engram",
                    "tag": ", ".join(tags),
                    "tags": tags,
                    "title": _browser_source_title({"path": path}, content) or title,
                    "snippet": _browser_snippet_from_text(content or title, query),
                    "matched_turn_index": 0,
                    "matched_message_index": 0,
                    "matched_chunk_id": path,
                    "score": 70.0 + score,
                    "search_relevance": score,
                    "last_activity_at": modified,
                    "path": path,
                    "closed": False,
                })
    except Exception as exc:
        print(f"[conversation-browser] vault markdown fallback failed: {exc}", file=sys.stderr)
    return _browser_sort_rows(rows, "relevance")[:limit]


def _browser_chroma_semantic_rows(
    query: str,
    *,
    logical_collection: str,
    limit: int,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
) -> list[dict]:
    if not (query or "").strip():
        return []
    out: dict[str, dict] = {}
    try:
        import chromadb
        from orchestrator.embedding import get_collection
        client = chromadb.PersistentClient(path=_browser_chromadb_path())
        col = get_collection(client, logical_collection)
        count = col.count()
        if count <= 0:
            return []
        n_results = min(max(limit, 5), count)
        if logical_collection == "knowledge":
            # Chroma metadata filters are much slower on large local knowledge
            # collections. Overfetch, then apply Ora's type filter below.
            n_results = min(max(limit * 4, 80), count)
        results = col.query(
            query_texts=[query],
            n_results=n_results,
        )
        ids = (results.get("ids") or [[]])[0]
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        dists = (results.get("distances") or [[]])[0]
        for embedding_id, doc, meta, dist in zip(ids, docs, metas, dists):
            if logical_collection == "knowledge" and not _browser_is_knowledge_note(meta or {}):
                continue
            similarity = 1.0 - float(dist if dist is not None else 1.0)
            score = 70.0 + (similarity * 40.0)
            candidate = _browser_row_from_chroma_hit(
                logical_collection=logical_collection,
                embedding_id=embedding_id,
                document=doc or "",
                metadata=meta or {},
                query=query,
                score=score,
            )
            if candidate and _browser_row_matches_tag_filters(
                candidate,
                required_tags=required_tags,
                show_archived=show_archived,
            ):
                _browser_merge_best(out, candidate)
    except Exception as exc:
        print(f"[conversation-browser] semantic {logical_collection} search failed: {exc}", file=sys.stderr)
    return sorted(out.values(), key=lambda r: float(r.get("score") or 0), reverse=True)[:limit]


def _browser_latest_archive_rows(limit: int) -> list[dict]:
    physical = _browser_physical_collection("conversations")
    rows: list[dict] = []
    try:
        import sqlite3
        con = sqlite3.connect(os.path.join(_browser_chromadb_path(), "chroma.sqlite3"))
        cur = con.cursor()
        matches = cur.execute(
            """
            SELECT cid.string_value AS source_id,
                   MAX(COALESCE(ts.string_value, stamp.string_value, d.string_value, '')) AS last_seen,
                   MAX(embeddings.id) AS sample_row_id,
                   MAX(COALESCE(pair.int_value, 0)) AS pair_seen
            FROM embeddings
            JOIN segments ON segments.id = embeddings.segment_id
            JOIN collections ON collections.id = segments.collection
            JOIN embedding_metadata cid
              ON cid.id = embeddings.id AND cid.key = 'conversation_id'
            LEFT JOIN embedding_metadata ts
              ON ts.id = embeddings.id AND ts.key = 'timestamp_utc'
            LEFT JOIN embedding_metadata stamp
              ON stamp.id = embeddings.id AND stamp.key = 'timestamp'
            LEFT JOIN embedding_metadata d
              ON d.id = embeddings.id AND d.key = 'date'
            LEFT JOIN embedding_metadata pair
              ON pair.id = embeddings.id AND pair.key = 'pair_num'
            WHERE collections.name = ?
              AND cid.string_value IS NOT NULL
              AND cid.string_value != ''
            GROUP BY cid.string_value
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (physical, max(limit, 1)),
        ).fetchall()
        for source_id, last_seen, sample_row_id, _pair_seen in matches:
            meta = _browser_metadata_for_row(cur, sample_row_id)
            doc = meta.get("chroma:document") or ""
            row = _browser_row_from_chroma_hit(
                logical_collection="conversations",
                embedding_id=meta.get("chunk_id") or str(sample_row_id),
                document=doc,
                metadata={**meta, "conversation_id": source_id, "timestamp_utc": last_seen},
                query="",
                score=0.5,
            )
            if row:
                rows.append(row)
        con.close()
    except Exception as exc:
        print(f"[conversation-browser] latest archive scan failed: {exc}", file=sys.stderr)
    return rows


def _browser_source_counts(rows: list[dict]) -> dict:
    counts = {"live": 0, "archive": 0, "engram": 0}
    for row in rows:
        kind = row.get("source_kind") or "live"
        if kind in counts:
            counts[kind] += 1
    return counts


_conversation_discovery_lock = threading.RLock()
_conversation_discovery_reviews: dict[str, dict] = {}
_CONVERSATION_DISCOVERY_TTL_SECONDS = 1800
_CONVERSATION_DISCOVERY_LIMIT = 256


def _browser_atomic_creation_row(row: dict) -> bool:
    """Creation discovery admits Dialogues and explicitly atomic notes only."""

    kind = row.get("source_kind") or "live"
    if kind in {"live", "archive"}:
        return True
    return kind == "engram" and "atomic" in _browser_normalize_tags(
        row.get("tags") or row.get("tag")
    )


def _browser_creation_row_allowed(row: dict, target_tag: str) -> bool:
    if not _browser_atomic_creation_row(row):
        return False
    kind = row.get("source_kind") or "live"
    if kind == "engram":
        ref = str(row.get("conversation_id") or "").strip()
        path = _browser_decode_source_id("engram", ref)
        if not path:
            path = str(
                row.get("path") or row.get("source_conversation_id") or ""
            ).strip()
        try:
            _validated_atomic_contributor_path(
                path, target_tag=target_tag,
            )
            return True
        except (OSError, ValueError):
            return False
    if kind == "live":
        ref = str(row.get("conversation_id") or "").strip()
        try:
            from conversation_memory import (
                read_conversation_history_envelope,
                resolve_effective_conversation_history,
            )
            lineage: set[str] = set()
            diagnostics: list[str] = []
            history = resolve_effective_conversation_history(
                ref, diagnostics=diagnostics, lineage_sink=lineage,
            )
            if history is None or (diagnostics and not history):
                return False
            for owner in _resolved_history_owners(history, ref):
                envelope = read_conversation_history_envelope(owner)
                if not isinstance(envelope, dict):
                    return False
                source_tag = (
                    envelope.get("tag")
                    if envelope.get("tag") in _VALID_CONVERSATION_TAGS else ""
                )
                if not _contributor_privacy_allows(source_tag, target_tag):
                    return False
            return True
        except Exception:
            return False
    if kind == "archive":
        ref = str(row.get("conversation_id") or "").strip()
        archive = _browser_archive_envelope(ref)
        if archive is None:
            return False
        try:
            _resolve_archive_contributor(
                ref, archive, target_tag=target_tag,
            )
            return True
        except (OSError, ValueError):
            return False
    source_tag = row.get("tag") if row.get("tag") in _VALID_CONVERSATION_TAGS else ""
    return _contributor_privacy_allows(source_tag, target_tag)


def _review_contributor_from_row(row: dict) -> dict | None:
    kind = row.get("source_kind") or "live"
    title = _clean_conversation_browser_text(row.get("title") or "")[:300]
    if kind in {"live", "archive"}:
        ref = str(row.get("conversation_id") or "").strip()
        if not ref:
            return None
        return {"kind": "conversation", "ref": ref, "title": title}
    if kind == "engram" and _browser_atomic_creation_row(row):
        ref = str(row.get("conversation_id") or "").strip()
        path = _browser_decode_source_id("engram", ref)
        if not path:
            path = str(row.get("path") or row.get("source_conversation_id") or "").strip()
        if not path:
            return None
        return {"kind": "atomic_note", "path": path, "title": title}
    return None


def _browser_row_for_creation_ref(ref: str) -> dict | None:
    """Resolve one explicit Library Add action without trusting client row data."""

    ref = str(ref or "").strip()
    if not ref:
        return None
    if ref.startswith("archive:"):
        envelope = _browser_archive_envelope(ref)
        kind = "archive"
    elif ref.startswith("engram:"):
        envelope = _browser_engram_envelope(ref)
        kind = "engram"
    else:
        try:
            from conversation_memory import load_conversation_json
            envelope = load_conversation_json(ref)
        except Exception:
            envelope = None
        kind = "live"
    if not isinstance(envelope, dict):
        return None
    title = envelope.get("display_name") or ref
    row = {
        "conversation_id": ref,
        "source_kind": kind,
        "result_type": envelope.get("result_type") or f"{kind}_conversation",
        "tag": envelope.get("tag") or "",
        "tags": _browser_normalize_tags(envelope.get("tag")),
        "title": title,
        "snippet": _conversation_search_snippet(envelope, "").get("snippet") or "",
        "score": 1000.0,
        "search_relevance": 100.0,
        "relevance": 100.0,
        "last_activity_at": envelope.get("last_activity_at") or "",
        "closed": bool(envelope.get("closed")),
    }
    if kind == "engram":
        path = _browser_decode_source_id("engram", ref)
        if not path:
            return None
        try:
            exact_path = _validated_atomic_contributor_path(path)
        except ValueError:
            return None
        content = exact_path.read_text(encoding="utf-8")
        row["path"] = str(exact_path)
        row["source_conversation_id"] = str(exact_path)
        row["tags"] = _browser_frontmatter_tags(content, path=str(exact_path))
        row["tag"] = ", ".join(row["tags"])
        row["result_type"] = "vault_note"
    return row


def _prune_conversation_discoveries_locked(now: float) -> None:
    expired = [
        key for key, value in _conversation_discovery_reviews.items()
        if now - float(value.get("created_at") or 0) > _CONVERSATION_DISCOVERY_TTL_SECONDS
    ]
    for key in expired:
        _conversation_discovery_reviews.pop(key, None)


def _active_conversation_discovery_locked(token: str) -> dict:
    now = time.time()
    _prune_conversation_discoveries_locked(now)
    review = _conversation_discovery_reviews.get(token)
    if review is None:
        raise ValueError("discovery review is missing or expired")
    return review


def _register_conversation_discovery(
    description: str,
    rows: list[dict],
    *,
    target_tag: str,
) -> str:
    now = time.time()
    candidates: dict[str, dict] = {}
    for row in rows:
        contributor = _review_contributor_from_row(row)
        if contributor is not None:
            candidates[str(row["conversation_id"])] = contributor
    token = "review-" + uuid.uuid4().hex
    with _conversation_discovery_lock:
        _prune_conversation_discoveries_locked(now)
        while len(_conversation_discovery_reviews) >= _CONVERSATION_DISCOVERY_LIMIT:
            oldest = min(
                _conversation_discovery_reviews,
                key=lambda key: _conversation_discovery_reviews[key]["created_at"],
            )
            _conversation_discovery_reviews.pop(oldest, None)
        _conversation_discovery_reviews[token] = {
            "description": description,
            "target_tag": target_tag,
            "candidates": candidates,
            "created_at": now,
            "accepted_contract": None,
        }
    return token


def _browser_parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _browser_parse_min_relevance(value: str | None) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        parsed = 0.0
    return max(0.0, min(100.0, parsed))


def _browser_row_relevance(row: dict, *, has_query: bool) -> float:
    if not has_query:
        return 0.0
    value = row.get("search_relevance")
    if value is None:
        value = row.get("score")
    try:
        return max(0.0, min(100.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _browser_filter_rows(
    rows: list[dict],
    *,
    include_conversations: bool,
    include_engrams: bool,
    min_relevance: float,
    has_query: bool,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        kind = row.get("source_kind") or "live"
        if kind == "engram":
            if not include_engrams:
                continue
        elif not include_conversations:
            continue
        if not _browser_row_matches_tag_filters(
            row,
            required_tags=required_tags,
            show_archived=show_archived,
        ):
            continue
        relevance = _browser_row_relevance(row, has_query=has_query)
        row["relevance"] = relevance
        if has_query and min_relevance > 0 and relevance < min_relevance:
            continue
        out.append(row)
    return out


def _browser_sort_rows(rows: list[dict], sort_mode: str) -> list[dict]:
    if sort_mode == "recency":
        return sorted(
            rows,
            key=lambda r: (r.get("last_activity_at") or "", float(r.get("relevance") or 0), float(r.get("score") or 0)),
            reverse=True,
        )
    return sorted(
        rows,
        key=lambda r: (
            float(r.get("search_relevance") if r.get("search_relevance") is not None else r.get("score") or 0),
            float(r.get("score") or 0),
            r.get("last_activity_at") or "",
        ),
        reverse=True,
    )


def _browser_live_rows(query: str) -> list[dict]:
    try:
        from conversation_memory import iter_conversations, load_conversation_json
    except Exception as e:
        raise RuntimeError(f"conversation browser import failed: {e}") from e

    try:
        summaries = iter_conversations(include_closed=True)
    except Exception as e:
        raise RuntimeError(f"conversation list failed: {e}") from e

    rows: list[dict] = []
    for row in summaries:
        cid = row.get("conversation_id")
        if not cid:
            continue
        data = load_conversation_json(cid) or {}
        match = _conversation_search_snippet(data, query)
        if query and match.get("score", 0) <= 0:
            continue
        out = dict(row)
        title = out.get("display_name") or out.get("title") or out.get("conversation_id") or ""
        snippet = match.get("snippet") or ""
        out.update({
            "result_type": "live_conversation",
            "source_kind": "live",
            "tags": _browser_normalize_tags(out.get("tag")),
            "snippet": snippet,
            "matched_message_index": match.get("matched_message_index"),
            "matched_turn_index": match.get("matched_turn_index"),
            "score": (float(match.get("score", 0)) + (25.0 if query else 1.0)),
            "search_relevance": _browser_match_score(query, title, snippet) if query else None,
        })
        rows.append(out)
    return rows


def _browser_parse_pair_markdown(text: str) -> tuple[str, str]:
    text = str(text or "")
    user_match = re.search(
        r"\*\*User:\*\*\s*(.*?)(?=\n\*\*Assistant:\*\*|\Z)",
        text,
        flags=re.S,
    )
    assistant_match = re.search(
        r"\*\*Assistant:\*\*\s*(.*)",
        text,
        flags=re.S,
    )
    if user_match or assistant_match:
        user = user_match.group(1).strip() if user_match else ""
        assistant = assistant_match.group(1).strip() if assistant_match else ""
        return user, assistant
    body = re.sub(r"^---\s*.*?\s*---\s*", "", text, flags=re.S).strip()
    return "", body


def _browser_archive_chunk_metadata(source_id: str) -> list[dict]:
    physical = _browser_physical_collection("conversations")
    try:
        import sqlite3
        con = sqlite3.connect(os.path.join(_browser_chromadb_path(), "chroma.sqlite3"))
        cur = con.cursor()
        rows = cur.execute(
            """
            SELECT embeddings.id
            FROM embeddings
            JOIN segments ON segments.id = embeddings.segment_id
            JOIN collections ON collections.id = segments.collection
            JOIN embedding_metadata cid
              ON cid.id = embeddings.id AND cid.key = 'conversation_id'
            LEFT JOIN embedding_metadata pair
              ON pair.id = embeddings.id AND pair.key = 'pair_num'
            WHERE collections.name = ?
              AND cid.string_value = ?
            ORDER BY COALESCE(pair.int_value, 0), embeddings.embedding_id
            """,
            (physical, source_id),
        ).fetchall()
        items: list[dict] = []
        for (row_id,) in rows:
            meta = _browser_metadata_for_row(cur, row_id)
            meta["_row_id"] = row_id
            items.append(meta)
        con.close()
        return items
    except Exception as exc:
        print(f"[conversation-browser] archive load failed: {exc}", file=sys.stderr)
        return []


def _browser_read_chunk_text(meta: dict) -> str:
    for key in ("chunk_path", "obsidian_path", "path"):
        path = _browser_resolve_path(meta.get(key))
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass
    return str(meta.get("chroma:document") or "")


def _browser_archive_envelope(conversation_id: str) -> dict | None:
    source_id = _browser_decode_source_id("archive", conversation_id)
    if not source_id:
        return None
    chunks = _browser_archive_chunk_metadata(source_id)
    if not chunks:
        return None

    messages: list[dict] = []
    privacy_sources: list = list(chunks)
    try:
        from conversation_memory import read_conversation_history_envelope
        retained_source = read_conversation_history_envelope(source_id)
    except Exception:
        retained_source = None
    if isinstance(retained_source, dict):
        privacy_sources.append(retained_source)
    first_doc = chunks[0].get("chroma:document") or ""
    title = _browser_source_title(chunks[0], first_doc)
    created = chunks[0].get("timestamp") or chunks[0].get("timestamp_utc") or chunks[0].get("date")
    last_activity = created
    for idx, meta in enumerate(chunks):
        text = _browser_read_chunk_text(meta)
        privacy_sources.append(_browser_frontmatter_tags(
            text,
            path=str(
                meta.get("chunk_path") or meta.get("obsidian_path")
                or meta.get("path") or meta.get("_row_id") or ""
            ),
        ))
        user_text, assistant_text = _browser_parse_pair_markdown(text)
        ts = meta.get("timestamp") or meta.get("timestamp_utc") or meta.get("date") or created
        if ts:
            last_activity = ts
        pair_num = meta.get("pair_num")
        chunk_id = meta.get("chunk_id") or meta.get("_row_id")
        if user_text:
            messages.append({
                "role": "user",
                "content": user_text,
                "timestamp": ts,
                "archive_pair_num": pair_num,
                "archive_chunk_id": chunk_id,
            })
        if assistant_text:
            messages.append({
                "role": "assistant",
                "content": assistant_text,
                "timestamp": ts,
                "archive_pair_num": pair_num,
                "archive_chunk_id": chunk_id,
            })
        if not user_text and not assistant_text and text.strip():
            messages.append({
                "role": "assistant",
                "content": text.strip(),
                "timestamp": ts,
                "archive_pair_num": pair_num or idx + 1,
                "archive_chunk_id": chunk_id,
            })

    return {
        "conversation_id": conversation_id,
        "source_conversation_id": source_id,
        "display_name": title,
        "tag": _browser_strictest_privacy_tag(*privacy_sources),
        "created": created,
        "last_activity_at": last_activity,
        "archived_source": True,
        "messages": messages,
    }


def _browser_engram_envelope(conversation_id: str) -> dict | None:
    source_id = _browser_decode_source_id("engram", conversation_id)
    if not source_id:
        return None
    path = _browser_resolve_path(source_id)
    content = ""
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            content = ""
    if not content:
        return None
    body = re.sub(r"^---\s*.*?\s*---\s*", "", content, flags=re.S).strip()
    heading = re.search(r"^#\s+(.+)$", body, flags=re.M)
    title = (
        heading.group(1).strip()
        if heading
        else (os.path.splitext(os.path.basename(path))[0] if path else "Engram")
    )
    title = title.replace("-", " ")[:180]
    return {
        "conversation_id": conversation_id,
        "source_conversation_id": source_id,
        "display_name": title,
        "tag": "",
        "created": None,
        "last_activity_at": None,
        "archived_source": True,
        "result_type": "engram",
        "messages": [{
            "role": "assistant",
            "content": body or content,
            "timestamp": None,
        }],
    }


def _browser_memory_envelope(conversation_id: str) -> dict | None:
    return (
        _browser_archive_envelope(conversation_id)
        or _browser_engram_envelope(conversation_id)
    )


def _contributor_privacy_allows(source_tag: str, target_tag: str) -> bool:
    try:
        from conversation_memory import conversation_privacy_allows
    except ImportError:
        from orchestrator.conversation_memory import conversation_privacy_allows
    return conversation_privacy_allows(source_tag, target_tag)


def _atomic_contributor_privacy_allows(tags, target_tag: str) -> bool:
    normalized = set(_browser_normalize_tags(tags))
    if "archived" in normalized:
        return False
    if "stealth" in normalized:
        return target_tag == "stealth"
    if "private" in normalized:
        return target_tag in {"private", "stealth"}
    return True


class _ContributorWithheld(ValueError):
    pass


def _resolve_archive_contributor(
    ref: str,
    archive: dict,
    *,
    target_tag: str,
    lineage_sink: set[str] | None = None,
) -> tuple[list[dict], set[str]]:
    """Return contributor-safe archive messages and their proven lineage.

    A retained fork envelope is the only authority for its ancestry cutoff.
    If that ancestry is missing, malformed, cyclic, or privacy-incompatible,
    the archive remains browsable but cannot be injected as a contributor.
    Legacy/non-fork archives retain their existing chunk reconstruction path.
    """
    source_id = str(archive.get("source_conversation_id") or "").strip()
    if not source_id:
        source_id = _browser_decode_source_id("archive", ref) or ""
    if not source_id:
        raise _ContributorWithheld("archived Dialogue identity is unavailable")

    lineage = lineage_sink if lineage_sink is not None else set()
    lineage.add(source_id)
    try:
        from conversation_memory import (
            read_conversation_history_envelope,
            resolve_effective_conversation_history,
        )
    except ImportError:
        from orchestrator.conversation_memory import (
            read_conversation_history_envelope,
            resolve_effective_conversation_history,
        )

    retained = read_conversation_history_envelope(source_id)
    if not isinstance(retained, dict):
        raise _ContributorWithheld(
            "archived Dialogue ancestry cannot be proven without its retained envelope"
        )
    stored_id = retained.get("conversation_id")
    if (not isinstance(stored_id, str)
            or stored_id.strip().casefold() != source_id.casefold()
            or not isinstance(retained.get("messages"), list)):
        raise _ContributorWithheld(
            "archived Dialogue retained envelope is unreadable"
        )
    is_retained_fork = bool(
        (
            retained.get("parent_conversation_id") is not None
            or retained.get("fork_point_message_count") is not None
            or retained.get("forked_at") is not None
        )
    )
    if is_retained_fork:
        diagnostics: list[str] = []
        history = resolve_effective_conversation_history(
            source_id, diagnostics=diagnostics, lineage_sink=lineage,
        )
        if history is None or diagnostics:
            raise _ContributorWithheld(
                "archived fork ancestry cannot be proven"
            )
        for owner in lineage:
            ancestor = read_conversation_history_envelope(owner)
            owner_tag = (
                ancestor.get("tag")
                if isinstance(ancestor, dict)
                and ancestor.get("tag") in _VALID_CONVERSATION_TAGS
                else ""
            )
            if (ancestor is None
                    or not _contributor_privacy_allows(owner_tag, target_tag)):
                raise _ContributorWithheld(
                    "archived fork ancestry crosses a stricter privacy boundary"
                )
        return history, lineage

    source_tag = (
        archive.get("tag")
        if archive.get("tag") in _VALID_CONVERSATION_TAGS else ""
    )
    if not _contributor_privacy_allows(source_tag, target_tag):
        raise _ContributorWithheld(
            "archived Dialogue is outside the target privacy boundary"
        )
    messages = archive.get("messages")
    if not isinstance(messages, list):
        raise _ContributorWithheld("archived Dialogue transcript is unavailable")
    return messages, lineage


def _dialogue_turn_units(
    messages: list,
    *,
    source_id: str,
    explicit_index: int,
    description: str = "",
) -> list[dict]:
    """Render complete user/assistant semantic units with stable provenance."""
    units: list[dict] = []
    pending: list[dict] = []

    def finish() -> None:
        nonlocal pending, description
        if not pending:
            return
        owner = str(pending[0].get("_ora_history_owner") or source_id)
        turn_index = pending[0].get("_ora_history_turn_index")
        if not isinstance(turn_index, int):
            turn_index = (
                pending[0].get("archive_pair_num")
                if isinstance(pending[0].get("archive_pair_num"), int)
                else len(units) + 1
            )
        parts: list[str] = []
        if description:
            parts.append("Creation description: " + description)
            description = ""
        for message in pending:
            label = "User" if message.get("role") == "user" else "Ora"
            parts.append(f"{label}: {message.get('content', '')}")
        provenance = f"conversation:{owner}:turn:{turn_index}"
        units.append({
            "lane": "contributor",
            "unit_id": provenance,
            "provenance_id": provenance,
            "source_id": f"selected-source-{explicit_index}",
            "source_conversation_id": owner,
            "explicit_index": explicit_index,
            "order": len(units),
            "turn_index": turn_index,
            "content": "\n\n".join(parts),
        })
        pending = []

    for raw in messages or []:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        if role not in {"user", "assistant"} or not isinstance(raw.get("content"), str):
            continue
        message = dict(raw)
        if role == "user":
            finish()
            pending = [message]
        elif pending and pending[0].get("role") == "user":
            pending.append(message)
            finish()
        else:
            finish()
            pending = [message]
            finish()
    finish()
    if description:
        provenance = f"conversation:{source_id}:description"
        units.append({
            "lane": "contributor",
            "unit_id": provenance,
            "provenance_id": provenance,
            "source_id": f"selected-source-{explicit_index}",
            "source_conversation_id": source_id,
            "explicit_index": explicit_index,
            "order": len(units),
            "content": "Creation description: " + description,
        })
    return units


def _resolved_history_owners(messages: list, fallback: str) -> set[str]:
    """Return only Dialogue identities still present in resolved history."""
    owners = {
        str(message.get("_ora_history_owner") or "").strip()
        for message in messages
        if isinstance(message, dict)
        and str(message.get("_ora_history_owner") or "").strip()
    }
    return owners or {fallback}


def _indexed_atomic_contributor_units(
    path: Path,
    *,
    explicit_index: int,
    target_tag: str,
) -> list[dict]:
    """Load the note's existing complete HCP/knowledge records, read-only."""
    import chromadb
    from orchestrator.embedding import get_collection

    client = chromadb.PersistentClient(path=_browser_chromadb_path())
    collection = get_collection(client, "knowledge")
    records = collection.get(
        where={"path": str(path)}, include=["documents", "metadatas"],
    )
    ids = records.get("ids") or []
    documents = records.get("documents") or []
    metadatas = records.get("metadatas") or []
    if len(ids) != len(documents) or len(ids) != len(metadatas):
        raise ValueError("atomic-note index returned mismatched records")
    rows: list[tuple] = []
    canonical = str(path.resolve())
    for record_id, document, metadata in zip(ids, documents, metadatas):
        if not isinstance(document, str) or not isinstance(metadata, dict):
            continue
        indexed_path = metadata.get("path")
        try:
            same_path = str(Path(str(indexed_path)).resolve()) == canonical
        except (OSError, ValueError):
            same_path = False
        if not same_path:
            continue
        indexed_tags = _browser_normalize_tags(
            metadata.get("tags") or metadata.get("tag")
        )
        if metadata.get("tag_private"):
            indexed_tags.append("private")
        if metadata.get("tag_stealth"):
            indexed_tags.append("stealth")
        if metadata.get("tag_archived"):
            indexed_tags.append("archived")
        if not _atomic_contributor_privacy_allows(indexed_tags, target_tag):
            raise _ContributorWithheld("indexed atomic contributor is withheld")
        rows.append((
            int(metadata.get("chunk_index") or 0), str(record_id), document,
            metadata,
        ))
    rows.sort(key=lambda row: (row[0], row[1]))
    return [{
        "lane": "contributor",
        "unit_id": f"knowledge:{row_id}",
        "provenance_id": f"knowledge:{row_id}",
        "source_id": f"selected-source-{explicit_index}",
        "source_path": canonical,
        "explicit_index": explicit_index,
        "order": order,
        "chunk_index": chunk_index,
        "content": document,
    } for order, (chunk_index, row_id, document, _metadata) in enumerate(rows)]


def build_contributor_bundle(
    conversation_id: str,
    *,
    target_tag: str = "",
) -> dict:
    """Resolve every explicit contributor into complete safe semantic units."""
    try:
        from conversation_memory import (
            normalize_contributors,
            read_conversation_history_envelope,
            resolve_effective_conversation_history,
        )
        envelope = read_conversation_history_envelope(conversation_id)
    except Exception:
        envelope = None
    if not isinstance(envelope, dict):
        return {"units": [], "sources": [], "exclude_conversation_ids": [], "exclude_paths": []}

    contributors = normalize_contributors(envelope.get("contributors"), strict=True)
    bundle = {
        "units": [],
        "sources": [],
        "exclude_conversation_ids": [],
        "exclude_paths": [],
    }
    excluded_conversations: set[str] = set()
    excluded_paths: set[str] = set()
    for index, contributor in enumerate(contributors):
        safe_source_id = f"selected-source-{index}"
        row = {
            "source_id": safe_source_id,
            "explicit_index": index,
            "status": "missing",
        }
        units: list[dict] = []
        if contributor["kind"] == "conversation":
            ref = contributor["ref"]
            # Exclude the explicitly selected identity even when its source is
            # now missing/withheld. A stale global index row for that Dialogue
            # must not bypass explicit-source accounting or a fork cutoff.
            excluded_conversations.add(ref)
            lineage: set[str] = set()
            diagnostics: list[str] = []
            history = resolve_effective_conversation_history(
                ref, diagnostics=diagnostics, lineage_sink=lineage,
            )
            source = read_conversation_history_envelope(ref)
            if source is not None and history is not None:
                if diagnostics and not history:
                    row["status"] = "withheld"
                else:
                    permitted = True
                    for owner in _resolved_history_owners(history, ref):
                        ancestor = read_conversation_history_envelope(owner)
                        owner_tag = (
                            ancestor.get("tag")
                            if isinstance(ancestor, dict)
                            and ancestor.get("tag") in _VALID_CONVERSATION_TAGS
                            else ""
                        )
                        if ancestor is None or not _contributor_privacy_allows(owner_tag, target_tag):
                            permitted = False
                            break
                    if permitted:
                        units = _dialogue_turn_units(
                            history,
                            source_id=ref,
                            explicit_index=index,
                            description=_clean_conversation_browser_text(
                                source.get("description") or "",
                            ),
                        )
                        row["status"] = "available" if units else "missing"
                    else:
                        row["status"] = "withheld"
            else:
                archive = _browser_archive_envelope(ref)
                if archive is not None:
                    source_identity = str(archive.get("source_conversation_id") or ref)
                    lineage.add(source_identity)
                    try:
                        archive_messages, _archive_lineage = (
                            _resolve_archive_contributor(
                                ref, archive, target_tag=target_tag,
                                lineage_sink=lineage,
                            )
                        )
                        units = _dialogue_turn_units(
                            archive_messages,
                            source_id=source_identity,
                            explicit_index=index,
                        )
                        row["status"] = "available" if units else "missing"
                    except _ContributorWithheld:
                        row["status"] = "withheld"
            excluded_conversations.update(lineage)
        else:
            # Inventory the declared identity before availability/privacy
            # validation. A contributor that later becomes missing, archived,
            # or withheld must still be excluded from ordinary knowledge RAG;
            # otherwise its stale indexed rows can re-enter as a duplicate.
            try:
                excluded_paths.add(os.path.realpath(os.path.abspath(
                    os.path.expanduser(contributor["path"])
                )))
            except (OSError, ValueError):
                pass
            try:
                path = _validated_atomic_contributor_path(
                    contributor["path"], target_tag=target_tag,
                )
                canonical = str(path.resolve())
                excluded_paths.add(canonical)
                units = _indexed_atomic_contributor_units(
                    path, explicit_index=index, target_tag=target_tag,
                )
                row["status"] = "available" if units else "missing"
            except _ContributorWithheld:
                row["status"] = "withheld"
            except (OSError, ValueError, RuntimeError):
                row["status"] = "missing"
            except Exception:
                row["status"] = "missing"
        bundle["units"].extend(units)
        bundle["sources"].append(row)
    bundle["exclude_conversation_ids"] = sorted(excluded_conversations, key=str.casefold)
    bundle["exclude_paths"] = sorted(excluded_paths, key=str.casefold)
    return bundle


def build_contributor_context(
    conversation_id: str,
    *,
    target_tag: str = "",
) -> str:
    """Compatibility view of the uncapped structured contributor bundle."""
    bundle = build_contributor_bundle(conversation_id, target_tag=target_tag)
    bodies = [unit["content"] for unit in bundle["units"]]
    for row in bundle["sources"]:
        if row["status"] in {"missing", "withheld"}:
            bodies.append(f"[{row['status'].title()} selected contributor]")
    return "\n\n".join(bodies)


def _browser_archive_related_rows(
    conversation_id: str,
    limit: int = 100,
    *,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
) -> list[dict]:
    source_id = _browser_decode_source_id("archive", conversation_id)
    if not source_id:
        return []
    chunks = _browser_archive_chunk_metadata(source_id)
    if not chunks:
        return []

    chain_ids = sorted({
        str(meta.get("chain_id"))
        for meta in chunks
        if meta.get("chain_id")
    })
    chain_labels = sorted({
        str(meta.get("chain_label"))
        for meta in chunks
        if meta.get("chain_label")
    })
    thread_ids = sorted({
        str(meta.get("thread_id"))
        for meta in chunks
        if meta.get("thread_id")
    })

    rows_by_id: dict[str, dict] = {}
    physical = _browser_physical_collection("conversations")
    clauses: list[str] = []
    params: list = [physical, source_id]
    if chain_ids:
        clauses.append("chain.string_value IN (%s)" % ",".join(["?"] * len(chain_ids)))
        params.extend(chain_ids)
    if chain_labels:
        clauses.append("label.string_value IN (%s)" % ",".join(["?"] * len(chain_labels)))
        params.extend(chain_labels)
    if thread_ids:
        clauses.append("thread.string_value IN (%s)" % ",".join(["?"] * len(thread_ids)))
        params.extend(thread_ids)

    if clauses:
        try:
            import sqlite3
            con = sqlite3.connect(os.path.join(_browser_chromadb_path(), "chroma.sqlite3"))
            cur = con.cursor()
            matches = cur.execute(
                f"""
                SELECT embeddings.id, embeddings.embedding_id
                FROM embeddings
                JOIN segments ON segments.id = embeddings.segment_id
                JOIN collections ON collections.id = segments.collection
                JOIN embedding_metadata cid
                  ON cid.id = embeddings.id AND cid.key = 'conversation_id'
                LEFT JOIN embedding_metadata chain
                  ON chain.id = embeddings.id AND chain.key = 'chain_id'
                LEFT JOIN embedding_metadata label
                  ON label.id = embeddings.id AND label.key = 'chain_label'
                LEFT JOIN embedding_metadata thread
                  ON thread.id = embeddings.id AND thread.key = 'thread_id'
                LEFT JOIN embedding_metadata stamp
                  ON stamp.id = embeddings.id AND stamp.key = 'timestamp_utc'
                WHERE collections.name = ?
                  AND cid.string_value != ?
                  AND ({' OR '.join(clauses)})
                ORDER BY COALESCE(stamp.string_value, '') DESC
                LIMIT ?
                """,
                (*params, max(limit * 4, 40)),
            ).fetchall()
            for row_id, embedding_id in matches:
                meta = _browser_metadata_for_row(cur, row_id)
                doc = meta.get("chroma:document") or ""
                related_score = 60.0
                if meta.get("chain_id") in chain_ids:
                    related_score += 30.0
                if meta.get("chain_label") in chain_labels:
                    related_score += 10.0
                if meta.get("thread_id") in thread_ids:
                    related_score += 5.0
                row = _browser_row_from_chroma_hit(
                    logical_collection="conversations",
                    embedding_id=embedding_id,
                    document=doc,
                    metadata=meta,
                    query="",
                    score=related_score,
                )
                if row and _browser_row_matches_tag_filters(
                    row,
                    required_tags=required_tags,
                    show_archived=show_archived,
                ):
                    row["relation"] = "related"
                    _browser_merge_best(rows_by_id, row)
            con.close()
        except Exception as exc:
            print(f"[conversation-browser] archive related lookup failed: {exc}", file=sys.stderr)

    if len(rows_by_id) < limit:
        title = _browser_source_title(chunks[0], chunks[0].get("chroma:document") or "")
        for row in _browser_chroma_semantic_rows(
            title,
            logical_collection="conversations",
            limit=max(20, limit - len(rows_by_id)),
            required_tags=required_tags,
            show_archived=show_archived,
        ):
            if row.get("source_conversation_id") == source_id:
                continue
            row["relation"] = row.get("relation") or "semantic"
            _browser_merge_best(rows_by_id, row)

    return _browser_sort_rows(list(rows_by_id.values()), "relevance")[:limit]


def _browser_engram_related_rows(
    conversation_id: str,
    limit: int = 100,
    *,
    include_conversations: bool = True,
    include_engrams: bool = True,
    required_tags: tuple[str, ...] | list[str] = (),
    show_archived: bool = False,
) -> list[dict]:
    source_id = _browser_decode_source_id("engram", conversation_id)
    if not source_id:
        return []
    envelope = _browser_engram_envelope(conversation_id)
    if not envelope:
        return []
    message = (envelope.get("messages") or [{}])[0]
    content = message.get("content") if isinstance(message, dict) else ""
    heading = re.search(r"^#\s+(.+)$", str(content or ""), flags=re.M)
    query = heading.group(1).strip() if heading else envelope.get("display_name") or str(content or "")[:240]

    rows_by_id: dict[str, dict] = {}
    if include_engrams:
        for row in _browser_chroma_exact_rows(
            query,
            logical_collection="knowledge",
            limit=max(20, limit // 2),
            required_tags=required_tags,
            show_archived=show_archived,
        ):
            if row.get("conversation_id") == conversation_id:
                continue
            row["relation"] = "related"
            _browser_merge_best(rows_by_id, row)
        for row in _browser_chroma_semantic_rows(
            query,
            logical_collection="knowledge",
            limit=max(20, limit // 2),
            required_tags=required_tags,
            show_archived=show_archived,
        ):
            if row.get("conversation_id") == conversation_id:
                continue
            row["relation"] = row.get("relation") or "semantic"
            _browser_merge_best(rows_by_id, row)
    if include_conversations:
        for row in _browser_chroma_semantic_rows(
            query,
            logical_collection="conversations",
            limit=max(20, limit // 2),
            required_tags=required_tags,
            show_archived=show_archived,
        ):
            row["relation"] = row.get("relation") or "conversation"
            _browser_merge_best(rows_by_id, row)
    return _browser_sort_rows(list(rows_by_id.values()), "relevance")[:limit]


@app.route("/api/conversations/browser", methods=["GET"])
def conversations_browser():
    """Search or browse live sessions plus archived conversation memory."""
    query = (request.args.get("q") or "").strip()
    purpose = (request.args.get("purpose") or "browse").strip().lower()
    if purpose not in {"browse", "creation"}:
        return _json_response({"error": "invalid browser purpose"}, status=400)
    if purpose == "creation" and (
        len(query) < 20
        or len(re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]+", query)) < 3
    ):
        return _json_response({
            "error": "creation discovery requires a concrete description",
        }, status=400)
    sort_mode = (request.args.get("sort") or ("relevance" if query else "recency")).strip().lower()
    if sort_mode not in {"relevance", "recency"}:
        sort_mode = "relevance" if query else "recency"
    include_conversations = _browser_parse_bool(
        request.args.get("conversations", request.args.get("include_conversations")),
        True,
    )
    include_engrams = _browser_parse_bool(
        request.args.get("engrams", request.args.get("include_engrams")),
        True,
    )
    required_tags = _browser_parse_requested_tags(request.args.getlist("tags"))
    show_archived = _browser_parse_bool(request.args.get("show_archived"), False)
    min_relevance = _browser_parse_min_relevance(request.args.get("min_relevance"))
    try:
        limit = int(request.args.get("limit") or 100)
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(limit, 500))

    live_rows: list[dict] = []
    if include_conversations:
        try:
            live_rows = _browser_live_rows(query)
        except Exception as e:
            return _json_response({"error": str(e)}, status=500)

    live_ids = {r.get("conversation_id") for r in live_rows}
    rows_by_id: dict[str, dict] = {}
    for row in live_rows:
        _browser_merge_best(rows_by_id, row)

    archive_rows: list[dict] = []
    engram_rows: list[dict] = []
    if query:
        if include_conversations:
            archive_rows.extend(_browser_chroma_exact_rows(
                query,
                logical_collection="conversations",
                limit=120,
                required_tags=required_tags,
                show_archived=show_archived,
            ))
            archive_rows.extend(_browser_chroma_fuzzy_rows(
                query,
                logical_collection="conversations",
                limit=80,
                required_tags=required_tags,
                show_archived=show_archived,
            ))
        if include_engrams:
            engram_rows.extend(_browser_chroma_exact_rows(
                query,
                logical_collection="knowledge",
                limit=80,
                required_tags=required_tags,
                show_archived=show_archived,
            ))
            engram_rows.extend(_browser_chroma_fuzzy_rows(
                query,
                logical_collection="knowledge",
                limit=80,
                required_tags=required_tags,
                show_archived=show_archived,
            ))
            engram_rows.extend(_browser_vault_markdown_rows(
                query,
                limit=40,
                required_tags=required_tags,
                show_archived=show_archived,
            ))
        local_rows = archive_rows + engram_rows
        local_best = max(
            (
                float(row.get("search_relevance") if row.get("search_relevance") is not None else row.get("score") or 0)
                for row in local_rows
            ),
            default=0.0,
        )
        if len(local_rows) < 30 or local_best < 90.0:
            if include_conversations:
                archive_rows.extend(_browser_chroma_semantic_rows(
                    query,
                    logical_collection="conversations",
                    limit=80,
                    required_tags=required_tags,
                    show_archived=show_archived,
                ))
            if include_engrams:
                engram_rows.extend(_browser_chroma_semantic_rows(
                    query,
                    logical_collection="knowledge",
                    limit=60,
                    required_tags=required_tags,
                    show_archived=show_archived,
                ))
    else:
        if include_conversations:
            archive_rows.extend(_browser_latest_archive_rows(limit=limit))

    for row in archive_rows + engram_rows:
        if row.get("source_conversation_id") in live_ids:
            continue
        _browser_merge_best(rows_by_id, row)

    rows = _browser_filter_rows(
        list(rows_by_id.values()),
        include_conversations=include_conversations,
        include_engrams=include_engrams,
        min_relevance=min_relevance,
        has_query=bool(query),
        required_tags=required_tags,
        show_archived=show_archived,
    )
    rows = _browser_sort_rows(rows, sort_mode)
    if purpose == "creation":
        target_tag = (request.args.get("target_tag") or "").strip().lower()
        if target_tag not in _VALID_CONVERSATION_TAGS:
            return _json_response({"error": "invalid creation target tag"}, status=400)
        rows = [
            row for row in rows
            if _browser_creation_row_allowed(row, target_tag)
        ]
        include_ref = (request.args.get("include_ref") or "").strip()
        if include_ref and not any(
            row.get("conversation_id") == include_ref for row in rows
        ):
            included = _browser_row_for_creation_ref(include_ref)
            if included is None or not _browser_creation_row_allowed(included, target_tag):
                return _json_response({
                    "error": "requested contributor no longer resolves",
                }, status=409)
            rows.insert(0, included)
    visible_rows = rows[:limit]
    payload = {
        "query": query,
        "purpose": purpose,
        "sort": sort_mode,
        "include_conversations": include_conversations,
        "include_engrams": include_engrams,
        "tags": required_tags,
        "show_archived": show_archived,
        "min_relevance": min_relevance,
        "rows": visible_rows,
        "total": len(rows),
        "source_counts": _browser_source_counts(rows),
    }
    if purpose == "creation":
        payload["review_token"] = _register_conversation_discovery(
            query,
            visible_rows,
            target_tag=target_tag,
        )
    return _json_response(payload)


def _validated_atomic_contributor_path(
    path_value: str,
    *,
    target_tag: str | None = None,
) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(path_value)))
    vault = Path(rp.vault_dir()).resolve()
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".md":
        raise ValueError("atomic-note contributor is unavailable")
    resolved = path.resolve()
    if not rp.within_base(resolved, vault):
        raise ValueError("atomic-note contributor escapes the configured vault")
    try:
        content = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("atomic-note contributor is unreadable") from exc
    tags = _browser_frontmatter_tags(content, path=str(resolved))
    if "atomic" not in tags:
        raise ValueError("contributor path is not an atomic note")
    if target_tag is not None and not _atomic_contributor_privacy_allows(
        tags, target_tag,
    ):
        raise _ContributorWithheld(
            "atomic-note contributor is outside the target privacy boundary"
        )
    return resolved


def _resolve_reviewed_contributors(
    review: dict,
    selected_refs,
    *,
    target_tag: str,
) -> list[dict]:
    if not isinstance(selected_refs, list):
        raise ValueError("contributors must be a list of reviewed refs")
    candidates = review.get("candidates") or {}
    contributors: list[dict] = []
    seen: set[str] = set()
    for raw_ref in selected_refs:
        if not isinstance(raw_ref, str) or raw_ref in seen:
            if not isinstance(raw_ref, str):
                raise ValueError("contributor refs must be strings")
            continue
        seen.add(raw_ref)
        candidate = candidates.get(raw_ref)
        if not isinstance(candidate, dict):
            raise ValueError("contributor was not part of the reviewed result set")
        if candidate.get("kind") == "atomic_note":
            exact_path = _validated_atomic_contributor_path(
                candidate["path"], target_tag=target_tag,
            )
            contributors.append({
                "kind": "atomic_note",
                "path": str(exact_path),
                "title": candidate.get("title") or exact_path.stem,
            })
            continue
        ref = str(candidate.get("ref") or "")
        try:
            from conversation_memory import (
                read_conversation_history_envelope,
                resolve_effective_conversation_history,
            )
            source = read_conversation_history_envelope(ref)
        except Exception:
            source = None
        if source is None:
            source = _browser_memory_envelope(ref)
        if source is None:
            raise ValueError("Dialogue contributor is unavailable")
        lineage: set[str] = set()
        if not source.get("archived_source"):
            diagnostics: list[str] = []
            resolved = resolve_effective_conversation_history(
                ref, diagnostics=diagnostics, lineage_sink=lineage,
            )
            if resolved is None or (diagnostics and not resolved):
                raise ValueError("Dialogue contributor ancestry is unavailable")
            visible_owners = _resolved_history_owners(resolved, ref)
        else:
            try:
                _resolve_archive_contributor(
                    ref, source, target_tag=target_tag,
                    lineage_sink=lineage,
                )
            except _ContributorWithheld as exc:
                raise ValueError(str(exc)) from exc
            visible_owners = lineage or {ref}
        for owner in visible_owners:
            ancestor = (
                read_conversation_history_envelope(owner)
                if not source.get("archived_source") else source
            )
            source_tag = (
                ancestor.get("tag")
                if isinstance(ancestor, dict)
                and ancestor.get("tag") in _VALID_CONVERSATION_TAGS
                else ""
            )
            if ancestor is None or not _contributor_privacy_allows(source_tag, target_tag):
                raise ValueError(
                    "Dialogue contributor ancestry has a stricter privacy boundary"
                )
        contributors.append({
            "kind": "conversation",
            "ref": ref,
            "title": candidate.get("title") or source.get("display_name") or ref,
        })
    return contributors


def _normalized_creation_title(value) -> str:
    if not isinstance(value, str):
        raise ValueError("title must be a string")
    title = re.sub(r"\s+", " ", value).strip()
    if not title or len(title) > 200:
        raise ValueError("title must contain 1 to 200 characters")
    return title


def _normalized_creation_refs(value) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("contributors must be a list of reviewed refs")
    refs: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("contributor refs must be nonempty strings")
        ref = raw.strip()
        if ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def _conversation_creation_digest(contract: dict) -> str:
    canonical = json.dumps(
        contract,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _envelope_matches_creation_contract(envelope: dict, contract: dict) -> bool:
    """Authenticate a deterministic create recovered after an interrupted reply."""

    return bool(
        isinstance(envelope, dict)
        and envelope.get("conversation_id") == contract.get("conversation_id")
        and envelope.get("display_name") == contract.get("title")
        and envelope.get("description") == contract.get("description")
        and envelope.get("tag", "") == contract.get("tag", "")
        and envelope.get("project_ids", []) == contract.get("project_ids", [])
        and envelope.get("contributors", []) == contract.get("contributors", [])
        and envelope.get("parent_conversation_id") is None
    )


@app.route("/api/conversations/review", methods=["POST"])
def conversations_review():
    """Issue an exact creation contract after explicit human acknowledgment."""

    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return _json_response({"error": "request body must be an object"}, 400)
    if body.get("acknowledged") is not True:
        return _json_response({"error": "explicit review acknowledgment is required"}, 400)
    review_token = body.get("review_token")
    description = body.get("description")
    tag = body.get("tag", "")
    if not isinstance(review_token, str) or not isinstance(description, str):
        return _json_response({"error": "description and review_token are required"}, 400)
    if tag not in _VALID_CONVERSATION_TAGS:
        return _json_response({"error": "invalid creation tag"}, 400)
    try:
        title = _normalized_creation_title(body.get("title"))
        description = description.strip()
        selected_refs = _normalized_creation_refs(body.get("contributors", []))
        from active_project import get_active_project, resolve_project_ids
        project_ids = resolve_project_ids(get_active_project())
        with _conversation_discovery_lock:
            review = _active_conversation_discovery_locked(review_token)
            if review.get("description") != description:
                raise ValueError("description changed after discovery review")
            if review.get("target_tag") != tag:
                raise ValueError("privacy target changed after discovery review")
            contributors = _resolve_reviewed_contributors(
                review,
                selected_refs,
                target_tag=tag,
            )
            digest_input = {
                "contract_version": 1,
                "title": title,
                "description": description,
                "selected_refs": selected_refs,
                "contributors": contributors,
                "tag": tag,
                "project_ids": project_ids,
                "acknowledged": True,
            }
            contract_digest = _conversation_creation_digest(digest_input)
            accepted = review.get("accepted_contract")
            if isinstance(accepted, dict) and accepted.get("response") is not None:
                if accepted.get("contract_digest") != contract_digest:
                    raise ValueError("discovery review already created a different contract")
                return _json_response({
                    "ok": True,
                    "creation_token": accepted["creation_token"],
                    "contract_digest": accepted["contract_digest"],
                    "conversation_id": accepted["conversation_id"],
                    "already_committed": True,
                })
            if not isinstance(accepted, dict) or accepted.get("contract_digest") != contract_digest:
                creation_token = "creation-" + uuid.uuid4().hex
                conversation_id = "thread-reviewed-" + hashlib.sha256(
                    f"{review_token}\0{contract_digest}".encode("utf-8")
                ).hexdigest()[:24]
                accepted = {
                    **digest_input,
                    "contract_digest": contract_digest,
                    "creation_token": creation_token,
                    "conversation_id": conversation_id,
                    "accepted_at": time.time(),
                    "response": None,
                }
                review["accepted_contract"] = accepted
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 409)
    return _json_response({
        "ok": True,
        "creation_token": accepted["creation_token"],
        "contract_digest": accepted["contract_digest"],
        "conversation_id": accepted["conversation_id"],
        "already_committed": False,
    })


@app.route("/api/conversations/create", methods=["POST"])
def conversations_create():
    """Commit one server-issued creation contract exactly once."""

    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return _json_response({"error": "request body must be an object"}, 400)
    if set(body) - {"review_token", "creation_token"}:
        return _json_response({
            "error": "creation accepts only a server-issued reviewed contract",
        }, 400)
    review_token = body.get("review_token")
    creation_token = body.get("creation_token")
    if not isinstance(review_token, str) or not isinstance(creation_token, str):
        return _json_response({"error": "review_token and creation_token are required"}, 400)

    status = 201
    try:
        # The discovery lock is deliberately held through the exclusive file
        # create and response recording. Concurrent deliveries therefore
        # serialize on one accepted contract and observe one committed result.
        with _conversation_discovery_lock:
            review = _active_conversation_discovery_locked(review_token)
            contract = review.get("accepted_contract")
            if not isinstance(contract, dict) or contract.get("creation_token") != creation_token:
                raise ValueError("explicit reviewed creation contract is missing or stale")
            if contract.get("response") is not None:
                response_payload = copy.deepcopy(contract["response"])
                response_payload["idempotent_replay"] = True
                status = 200
            else:
                current_contributors = _resolve_reviewed_contributors(
                    review,
                    contract["selected_refs"],
                    target_tag=contract["tag"],
                )
                if current_contributors != contract["contributors"]:
                    raise ValueError("reviewed contributors changed before creation")
                from conversation_memory import (
                    create_conversation_envelope,
                    load_conversation_json,
                )
                conversation_id = contract["conversation_id"]
                with _conversation_lifecycle_lock(conversation_id):
                    envelope = load_conversation_json(conversation_id)
                    if envelope is None:
                        _assert_no_casefold_session_collision(conversation_id)
                        try:
                            envelope = create_conversation_envelope(
                                conversation_id,
                                title=contract["title"],
                                description=contract["description"],
                                contributors=contract["contributors"],
                                tag=contract["tag"],
                                project_ids=contract["project_ids"],
                            )
                        except FileExistsError:
                            envelope = load_conversation_json(conversation_id)
                    if not _envelope_matches_creation_contract(envelope, contract):
                        raise ValueError("deterministic Dialogue identity does not match its creation contract")
                response_payload = {
                    "ok": True,
                    "conversation_id": conversation_id,
                    "display_name": envelope["display_name"],
                    "description": envelope["description"],
                    "tag": envelope["tag"],
                    "project_ids": envelope["project_ids"],
                    "contributors": envelope["contributors"],
                    "contract_digest": contract["contract_digest"],
                    "idempotent_replay": False,
                }
                contract["response"] = copy.deepcopy(response_payload)
                contract["committed_at"] = time.time()
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 409)
    except OSError as exc:
        # The accepted contract remains available. If the write completed
        # before an interrupted reply, its deterministic identity is recovered
        # and authenticated on retry instead of creating a second Dialogue.
        return _json_response({"error": f"Dialogue creation failed: {exc}"}, 500)
    return _json_response(response_payload, status)


@app.route("/api/conversation/<conversation_id>/restore", methods=["POST"])
def conversations_restore(conversation_id):
    """Make a closed conversation visible in the active sidebar again."""
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    try:
        from conversation_memory import set_conversation_closed, load_conversation_json
    except Exception as e:
        return _json_response({"error": f"conversation restore import failed: {e}"}, status=500)
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        path = set_conversation_closed(conversation_id, False)
        if path is not None:
            with _conversation_lifecycle_guard:
                _closed_conversations.discard(
                    _conversation_storage_identity(conversation_id)
                )
    if path is None:
        return _json_response({"error": "Dialogue not found", "conversation_id": conversation_id}, status=404)
    data = load_conversation_json(conversation_id) or {}
    return _json_response({
        "ok": True,
        "conversation_id": conversation_id,
        "conversation": data,
    })


@app.route("/api/conversation/<conversation_id>/projects", methods=["POST"])
def conversations_set_projects(conversation_id):
    """Replace project memberships or atomically add one membership.

    A conversation can belong to many projects; ``commons`` (and its legacy
    id ``general``) is the implicit baseline (empty list == Commons) and is
    never stored. Body is exactly one of ``{"project_ids": ["nexus", ...]}``
    or ``{"add_project_id": "nexus"}``. Returns the stored list."""
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    try:
        from conversation_memory import (
            add_conversation_project,
            load_conversation_json,
            set_conversation_projects,
        )
    except Exception as e:
        return _json_response({"error": f"set projects import failed: {e}"}, status=500)
    data = request.get_json(silent=True) or {}
    add_requested = "add_project_id" in data
    replace_requested = "project_ids" in data
    if add_requested == replace_requested:
        return _json_response({
            "error": "provide exactly one of add_project_id or project_ids",
        }, status=400)
    add_project_id = data.get("add_project_id")
    project_ids = data.get("project_ids")
    if add_requested and (
        not isinstance(add_project_id, str) or not add_project_id.strip()
    ):
        return _json_response({"error": "add_project_id must be a non-empty string"}, status=400)
    if replace_requested and not isinstance(project_ids, list):
        return _json_response({"error": "project_ids must be a list"}, status=400)
    stored_project_ids = None
    path = None
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return _json_response({"status": "deleted"}, status=410)
        if add_requested:
            stored_project_ids = add_conversation_project(
                conversation_id,
                add_project_id.strip(),
            )
        else:
            path = set_conversation_projects(conversation_id, project_ids)
    if (add_requested and stored_project_ids is None) or (
        replace_requested and path is None
    ):
        return _json_response(
            {"error": "Dialogue not found", "conversation_id": conversation_id},
            status=404)
    if replace_requested:
        stored = load_conversation_json(conversation_id) or {}
        stored_project_ids = stored.get("project_ids", [])
    return _json_response({
        "ok": True,
        "conversation_id": conversation_id,
        "project_ids": stored_project_ids,
    })


@app.route("/api/conversation/<conversation_id>/related", methods=["GET"])
def conversations_related(conversation_id):
    """Return parent, child, and sibling conversation rows for a thread."""
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return _json_response({"error": "invalid conversation_id"}, status=400)
    include_conversations = _browser_parse_bool(
        request.args.get("conversations", request.args.get("include_conversations")),
        True,
    )
    include_engrams = _browser_parse_bool(
        request.args.get("engrams", request.args.get("include_engrams")),
        True,
    )
    required_tags = _browser_parse_requested_tags(request.args.getlist("tags"))
    show_archived = _browser_parse_bool(request.args.get("show_archived"), False)
    min_relevance = _browser_parse_min_relevance(request.args.get("min_relevance"))
    sort_mode = (request.args.get("sort") or "relevance").strip().lower()
    if sort_mode not in {"relevance", "recency"}:
        sort_mode = "relevance"
    if conversation_id.startswith("archive:"):
        rows = _browser_archive_related_rows(
            conversation_id,
            required_tags=required_tags,
            show_archived=show_archived,
        ) if include_conversations else []
        rows = _browser_filter_rows(
            rows,
            include_conversations=include_conversations,
            include_engrams=include_engrams,
            min_relevance=min_relevance,
            has_query=True,
            required_tags=required_tags,
            show_archived=show_archived,
        )
        rows = _browser_sort_rows(rows, sort_mode)
        return _json_response({
            "conversation_id": conversation_id,
            "tags": required_tags,
            "show_archived": show_archived,
            "rows": rows,
        })
    if conversation_id.startswith("engram:"):
        rows = _browser_engram_related_rows(
            conversation_id,
            include_conversations=include_conversations,
            include_engrams=include_engrams,
            required_tags=required_tags,
            show_archived=show_archived,
        )
        rows = _browser_filter_rows(
            rows,
            include_conversations=include_conversations,
            include_engrams=include_engrams,
            min_relevance=min_relevance,
            has_query=True,
            required_tags=required_tags,
            show_archived=show_archived,
        )
        rows = _browser_sort_rows(rows, sort_mode)
        return _json_response({
            "conversation_id": conversation_id,
            "tags": required_tags,
            "show_archived": show_archived,
            "rows": rows,
        })
    if not include_conversations:
        return _json_response({
            "conversation_id": conversation_id,
            "tags": required_tags,
            "show_archived": show_archived,
            "rows": [],
        })
    try:
        from conversation_memory import iter_conversations, load_conversation_json
    except Exception as e:
        return _json_response({"error": f"conversation related import failed: {e}"}, status=500)
    rows = iter_conversations(include_closed=True)
    by_id = {r.get("conversation_id"): r for r in rows}
    current = by_id.get(conversation_id)
    if current is None:
        return _json_response({"error": "Dialogue not found", "conversation_id": conversation_id}, status=404)
    parent_id = current.get("parent_conversation_id")
    related: list[dict] = []

    def add(row: dict | None, relation: str) -> None:
        if not row:
            return
        item = dict(row)
        item["relation"] = relation
        data = load_conversation_json(item["conversation_id"]) or {}
        item["snippet"] = _conversation_search_snippet(data, "").get("snippet") or ""
        related.append(item)

    add(current, "self")
    if parent_id:
        add(by_id.get(parent_id), "parent")
    for row in rows:
        cid = row.get("conversation_id")
        if cid == conversation_id:
            continue
        if row.get("parent_conversation_id") == conversation_id:
            add(row, "fork")
        elif parent_id and row.get("parent_conversation_id") == parent_id:
            add(row, "sibling")

    related = _browser_filter_rows(
        related,
        include_conversations=True,
        include_engrams=include_engrams,
        min_relevance=0.0,
        has_query=False,
        required_tags=required_tags,
        show_archived=show_archived,
    )
    related.sort(key=lambda r: (r.get("relation") != "self", r.get("last_activity_at") or ""), reverse=False)
    return _json_response({
        "conversation_id": conversation_id,
        "tags": required_tags,
        "show_archived": show_archived,
        "rows": related,
    })


@app.route("/api/conversation/<conversation_id>", methods=["GET"])
def conversations_fetch(conversation_id):
    """Return the full conversation.json envelope for a conversation.

    Used by the UI when the user navigates to a conversation in the list,
    to load its messages into the output pane. Returns 404 if the
    conversation does not exist.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400

    try:
        from conversation_memory import load_conversation_json
    except Exception as e:
        return json.dumps({"error": f"load_conversation_json import failed: {e}"}), 500

    data = load_conversation_json(conversation_id)
    if data is None:
        data = _browser_memory_envelope(conversation_id)
    if data is None:
        return json.dumps({"error": "Dialogue not found", "conversation_id": conversation_id}), 404

    # Annotate with the in-memory pending flag so the client doesn't have to
    # cross-reference the list endpoint.
    data["pending"] = conversation_id in _pending_conversations
    return json.dumps(data)


# -- Trace Walk (Chunk 2): safe read-side projections + per-trace pinning ---

@app.route("/api/trace/list/<conversation_id>", methods=["GET"])
def api_trace_list(conversation_id):
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    try:
        import pipeline_trace as _pt
    except ImportError:
        from orchestrator import pipeline_trace as _pt
    refs = _pt.list_trace_refs(conversation_id)
    return json.dumps({"conversation_id": conversation_id, "trace_refs": refs})


@app.route("/api/trace/manifest/<conversation_id>/<turn_ts>", methods=["GET"])
def api_trace_manifest(conversation_id, turn_ts):
    trace_ref = f"{conversation_id}/{turn_ts}"
    try:
        import pipeline_trace as _pt
    except ImportError:
        from orchestrator import pipeline_trace as _pt
    data = _pt.trace_manifest_projection(trace_ref)
    if data is None:
        return json.dumps({"error": "trace_ref not found", "trace_ref": trace_ref}), 404
    return json.dumps(data)


@app.route("/api/trace/step/<conversation_id>/<turn_ts>/<step_name>", methods=["GET"])
def api_trace_step(conversation_id, turn_ts, step_name):
    trace_ref = f"{conversation_id}/{turn_ts}"
    try:
        import pipeline_trace as _pt
    except ImportError:
        from orchestrator import pipeline_trace as _pt
    data = _pt.trace_step_projection(trace_ref, step_name)
    if data is None:
        return json.dumps({
            "error": "step not found or not allowed",
            "trace_ref": trace_ref,
            "step_name": step_name,
        }), 404
    return json.dumps(data)


@app.route("/api/trace/export/<conversation_id>/<turn_ts>", methods=["GET"])
def api_trace_export(conversation_id, turn_ts):
    trace_ref = f"{conversation_id}/{turn_ts}"
    try:
        import pipeline_trace as _pt
    except ImportError:
        from orchestrator import pipeline_trace as _pt
    rendered = _pt.trace_export_html(trace_ref)
    if rendered is None:
        return json.dumps({"error": "trace_ref not found", "trace_ref": trace_ref}), 404
    html_doc, filename = rendered
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": _pt.TRACE_EXPORT_CSP,
    }
    return html_doc, 200, headers


@app.route("/api/trace/probe/prepare", methods=["POST"])
def api_trace_probe_prepare():
    try:
        body = request.get_json(force=True, silent=True)
    except Exception:
        body = None
    if not isinstance(body, dict):
        return json.dumps({"error": "expected JSON object"}), 400
    trace_ref = str(body.get("trace_ref") or "").strip()
    parts = trace_ref.split("/")
    if len(parts) != 2:
        return json.dumps({"error": "trace_ref must be conversation/turn"}), 400
    conversation_id = parts[0]
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    try:
        import trace_debug as _tdbg
    except ImportError:
        from orchestrator import trace_debug as _tdbg
    body = dict(body)
    body["conversation_tag"] = _tdbg.conversation_tag_for_trace_ref(trace_ref)
    result = _tdbg.prepare_probe(body, conversation_id=conversation_id)
    status = 200 if result.get("ok") else 400
    return json.dumps(result, default=str), status


@app.route("/api/trace/probe/approve", methods=["POST"])
def api_trace_probe_approve():
    try:
        body = request.get_json(force=True, silent=True)
    except Exception:
        body = None
    if not isinstance(body, dict):
        return json.dumps({"error": "expected JSON object"}), 400
    try:
        import trace_debug as _tdbg
    except ImportError:
        from orchestrator import trace_debug as _tdbg
    result = _tdbg.approve_probe(str(body.get("approval_id") or ""), str(body.get("approval_digest") or ""))
    return json.dumps(result, default=str), (200 if result.get("ok") else 400)


@app.route("/api/trace/probe/execute", methods=["POST"])
def api_trace_probe_execute():
    try:
        body = request.get_json(force=True, silent=True)
    except Exception:
        body = None
    if not isinstance(body, dict):
        return json.dumps({"error": "expected JSON object"}), 400
    conversation_id = str(body.get("conversation_id") or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    try:
        import trace_debug as _tdbg
    except ImportError:
        from orchestrator import trace_debug as _tdbg
    config = load_config()
    fallback_endpoint = get_endpoint(config)
    if fallback_endpoint is None:
        return json.dumps({"error": "No AI endpoints configured."}), 400
    def _executor(req):
        envelope = req.get("envelope") or {}
        endpoint = _tdbg.endpoint_from_probe_envelope(envelope, fallback_endpoint)
        if endpoint is None:
            raise RuntimeError("recorded probe endpoint is unavailable or has changed")
        return call_model(envelope.get("messages") or [], endpoint)
    result = _tdbg.execute_probe(
        str(body.get("approval_id") or ""), str(body.get("approval_digest") or ""),
        conversation_id=conversation_id, model_executor=_executor,
        conversation_tag=_tdbg.approval_conversation_tag(
            str(body.get("approval_id") or ""),
            str(body.get("approval_digest") or ""),
        ))
    return json.dumps(result, default=str), (200 if result.get("ok") else 400)


@app.route("/api/trace/retention", methods=["POST"])
def api_trace_retention():
    try:
        body = request.get_json(force=True, silent=True)
    except Exception:
        body = None
    if not isinstance(body, dict):
        return json.dumps({"error": "expected JSON object"}), 400
    trace_ref_value = body.get("trace_ref")
    pinned = body.get("pinned")
    if not isinstance(trace_ref_value, str) or not trace_ref_value.strip():
        return json.dumps({"error": "trace_ref must be a non-empty string"}), 400
    if not isinstance(pinned, bool):
        return json.dumps({"error": "pinned must be a boolean"}), 400
    trace_ref = trace_ref_value.strip()
    try:
        import pipeline_trace as _pt
    except ImportError:
        from orchestrator import pipeline_trace as _pt
    try:
        manifest = _pt.set_retention_state(trace_ref, "pinned" if pinned else "default")
    except ValueError as exc:
        message = str(exc) or "retention update rejected"
        status = 409 if "open trace" in message else 400
        return json.dumps({"error": message, "trace_ref": trace_ref}), status
    if manifest is None:
        return json.dumps({"error": "trace_ref not found", "trace_ref": trace_ref}), 404
    return json.dumps({
        "ok": True,
        "trace_ref": trace_ref,
        "retention_state": manifest.get("retention_state"),
    })


@app.route("/api/conversation/<conversation_id>/mark-read", methods=["POST"])
def conversations_mark_read(conversation_id):
    """Update the conversation's ``last_read_at`` to now (or a supplied
    timestamp).

    Called by the UI when the user views a conversation's output, so that
    subsequent list responses no longer flag it as Unread. Returns 200 with
    ``{"ok": true, "last_read_at": "..."}``, or 404 if the conversation is
    missing.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400

    # Optional override timestamp (test harness or batch backfill).
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}
    ts = body.get("timestamp") if isinstance(body, dict) else None

    try:
        from conversation_memory import mark_conversation_read
    except Exception as e:
        return json.dumps({"error": f"mark_conversation_read import failed: {e}"}), 500

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({"status": "deleted"}), 410
        path = mark_conversation_read(
            conversation_id, timestamp=ts if isinstance(ts, str) else None,
        )
    if path is None:
        return json.dumps({"error": "Dialogue not found or unwriteable", "conversation_id": conversation_id}), 404

    # Read back the new value so the client doesn't have to compute it.
    try:
        from conversation_memory import load_conversation_json
        data = load_conversation_json(conversation_id) or {}
        return json.dumps({"ok": True, "last_read_at": data.get("last_read_at")})
    except Exception:
        return json.dumps({"ok": True})


# ── V3 Backlog 6: /api/qqb retired 2026-04-30 ───────────────────────────────
# The right-column endpoint moved to /api/scratchpad (SSE streaming, spec
# conformant — see api_scratchpad below). The /api/bootstrap endpoint
# (defined later) handles new-conversation pre-population separately.


# ── V3 Phase 5: conversation fork ────────────────────────────────────────────

@app.route("/api/conversation/<conversation_id>/fork", methods=["POST"])
def conversations_fork(conversation_id):
    """V3 spec §4.2 / §5.2 — fork a conversation.

    The child inherits the parent's tag but owns a fresh local transcript.
    Its immutable ``fork_point_message_count`` marks the exact parent message
    prefix visible at the requested displayed turn (or the latest prefix when
    no turn is supplied).
    Used by the Stealth and Private dropdowns' Fork option, and may
    also serve general-mode forks.

    Request body (optional):
        {
          "new_id": "<override>",            # caller-supplied id; default is
                                             # parent_id + "-fork-<ts>"
          "fork_point_turn_index": <int>,     # zero-based displayed turn;
                                             # omitted means latest
          "fork_point_chunk_id": "<id>"      # parent's chunk_id at the
                                             # fork point (legacy compatibility)
        }

    Response: 200 with the new envelope, or 404 if parent is missing.
    """
    parent_id = (conversation_id or "").strip()
    if not _valid_live_conversation_id(parent_id):
        return json.dumps({"error": "invalid conversation_id"}), 400

    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}

    # Default child id: parent + fork timestamp suffix. Caller can
    # override via body for their own naming (e.g., content-derived).
    requested_id = (body.get("new_id") or "").strip() if isinstance(body, dict) else ""
    if not requested_id:
        ts_suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        requested_id = f"{parent_id}-fork-{ts_suffix}"
    if not _valid_live_conversation_id(requested_id):
        return json.dumps({"error": "invalid new_id"}), 400

    creation_tag = None
    if isinstance(body, dict) and "tag" in body:
        raw_tag = body.get("tag")
        if not isinstance(raw_tag, str) or raw_tag.strip().lower() not in _VALID_CONVERSATION_TAGS:
            return json.dumps({"error": "invalid creation tag"}), 400
        creation_tag = raw_tag.strip().lower()

    fork_point_chunk_id = None
    fork_point_turn_index = None
    if isinstance(body, dict):
        if "fork_point_turn_index" in body:
            raw_turn_index = body.get("fork_point_turn_index")
            if (isinstance(raw_turn_index, bool)
                    or not isinstance(raw_turn_index, int)
                    or raw_turn_index < 0):
                return json.dumps({
                    "error": "fork_point_turn_index must be a non-negative integer",
                }), 400
            fork_point_turn_index = raw_turn_index
        raw = body.get("fork_point_chunk_id")
        if isinstance(raw, str) and raw.strip():
            fork_point_chunk_id = raw.strip()

    try:
        from conversation_memory import fork_conversation
    except Exception as e:
        return json.dumps({"error": f"fork_conversation import failed: {e}"}), 500

    # Lock both IDs in stable order so concurrent forks cannot overwrite a
    # child and Delete Forever cannot race either envelope read/write.
    first_id, second_id = sorted((parent_id, requested_id))
    with _conversation_lifecycle_lock(first_id):
        with _conversation_lifecycle_lock(second_id):
            if (_is_conversation_deleted(parent_id)
                    or _is_conversation_deleted(requested_id)):
                return json.dumps({"error": "conversation was deleted"}), 410
            try:
                _assert_no_casefold_session_collision(requested_id)
            except (ValueError, RuntimeError) as exc:
                return json.dumps({"error": str(exc)}), 409
            try:
                from orchestrator.conversation_memory import (
                    _conversation_path, _DEFAULT_SESSIONS_ROOT,
                )
                if _conversation_path(requested_id, _DEFAULT_SESSIONS_ROOT).exists():
                    return json.dumps({"error": "new_id already exists"}), 409
            except Exception as exc:
                print(f"[conversation-lifecycle] fork destination check "
                      f"failed for {requested_id}: {exc}",
                      file=sys.stderr, flush=True)
                return json.dumps({
                    "error": "could not verify fork destination",
                    "detail": str(exc),
                }), 500
            try:
                new_envelope = fork_conversation(
                    parent_id, requested_id,
                    fork_point_turn_index=fork_point_turn_index,
                    fork_point_chunk_id=fork_point_chunk_id,
                    creation_tag=creation_tag,
                )
            except ValueError as exc:
                return json.dumps({"error": str(exc)}), 400
    if new_envelope is None:
        return json.dumps({
            "error":           "parent Dialogue not found or unreadable",
            "conversation_id": parent_id,
        }), 404

    return json.dumps({
        "ok":                       True,
        "new_conversation_id":      new_envelope["conversation_id"],
        "tag":                      new_envelope.get("tag", ""),
        "parent_conversation_id":   new_envelope.get("parent_conversation_id"),
        "fork_point_message_count": new_envelope.get("fork_point_message_count"),
        "fork_point_chunk_id":      new_envelope.get("fork_point_chunk_id"),
        "created":                  new_envelope.get("created"),
        "forked_at":                new_envelope.get("forked_at"),
        "inherited_message_count":  new_envelope.get("fork_point_message_count", 0),
        "local_message_count":      len(new_envelope.get("messages") or []),
        "message_count":            len(new_envelope.get("messages") or []),
    })


# ── V3 Phase 6.1: conversation bootstrap ─────────────────────────────────────

@app.route("/api/bootstrap", methods=["POST"])
def api_bootstrap():
    """V3 Phase 6.1 — Conversation bootstrap endpoint.

    Side-channel call (NOT pipeline routing): topic → ChromaDB query across
    knowledge + conversations collections → configured utility-model assembly →
    return structured summary. Bypasses the analysis pipeline entirely
    per spec §6.3.

    Request body:
        {
          "topic": "<string the user wants context on>",
          "tag":   "" | "stealth" | "private"   # caller's mode (optional)
        }

    Response:
        {
          "topic":         "<echo>",
          "summary":       "<assembled markdown summary, 2-4 paragraphs>",
          "match_count":   <int>,
          "sources_used":  [{collection, metadata}, ...],
          "fallback":      <bool, true if model unreachable>,
          "fallback_reason": "<str>"   (only when fallback=true)
        }

    Privacy: knowledge and conversation queries exclude Private records unless
    the caller is themselves in Private mode.
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return json.dumps({"error": "invalid JSON body"}), 400

    topic = (data.get("topic") or "").strip()
    if not topic:
        return json.dumps({"error": "topic is required"}), 400

    caller_tag = _normalize_tag(data.get("tag", ""))

    # ── Step 1: Query ChromaDB collections ──────────────────────────────────
    matches: list[dict] = []
    chroma_path = None
    try:
        import chromadb
        from orchestrator.embedding import get_collection
        cfg = load_config()
        chroma_path = cfg.get("chromadb_path", os.path.join(WORKSPACE, "chromadb/"))
        client = chromadb.PersistentClient(path=chroma_path)

        # Knowledge collection with the canonical mode-conditioned filter.
        try:
            kn = get_collection(client, "knowledge")
            knowledge_where = (
                None if caller_tag == "private" else {"tag_private": False}
            )
            kn_results = kn.query(
                query_texts=[topic], n_results=5, where=knowledge_where,
            )
            docs = (kn_results or {}).get("documents") or [[]]
            metas = (kn_results or {}).get("metadatas") or [[]]
            for i, doc in enumerate(docs[0] if docs else []):
                meta = metas[0][i] if metas and metas[0] and i < len(metas[0]) else {}
                matches.append({
                    "collection": "knowledge",
                    "document":   doc,
                    "metadata":   meta or {},
                })
        except Exception:
            pass  # Knowledge collection may not exist yet; non-fatal

        # Conversations collection with privacy filter.
        try:
            conv = get_collection(client, "conversations")
            where_clause = None if caller_tag == "private" else {"tag": {"$ne": "private"}}
            conv_results = conv.query(
                query_texts=[topic],
                n_results=5,
                where=where_clause,
            )
            docs = (conv_results or {}).get("documents") or [[]]
            metas = (conv_results or {}).get("metadatas") or [[]]
            for i, doc in enumerate(docs[0] if docs else []):
                meta = metas[0][i] if metas and metas[0] and i < len(metas[0]) else {}
                matches.append({
                    "collection": "conversations",
                    "document":   doc,
                    "metadata":   meta or {},
                })
        except Exception:
            pass
    except Exception as e:
        return json.dumps({"error": f"chromadb unavailable: {e}"}), 500

    # If no matches, return a benign empty summary so the caller can still
    # populate the output pane with something stable.
    if not matches:
        return json.dumps({
            "topic":        topic,
            "summary":      f"No prior knowledge or Dialogues on this topic.\n\nStarting fresh on: **{topic}**",
            "match_count":  0,
            "sources_used": [],
        })

    # ── Step 2: Format context block ────────────────────────────────────────
    context_lines = []
    for i, m in enumerate(matches):
        src = f"[{m['collection']}#{i+1}]"
        title = m["metadata"].get("topics") or m["metadata"].get("title") or ""
        snippet = (m["document"] or "")[:500]
        if title:
            context_lines.append(f"{src} {title}\n{snippet}")
        else:
            context_lines.append(f"{src}\n{snippet}")
    context_block = "\n\n".join(context_lines)

    # ── Step 3: configured utility-model assembly ───────────────────────────
    summary_text = ""
    fallback = False
    fallback_reason = None
    try:
        cfg = load_config()
        # Historical compatibility path for the bootstrap helper. New Aside
        # requests use their dedicated user setting in /api/scratchpad.
        ep = get_slot_endpoint(cfg, "sidebar")
        if not ep:
            raise RuntimeError("sidebar slot has no endpoint configured")

        prompt = (
            f"Topic: {topic}\n\n"
            f"Available context from local knowledge and prior conversations:\n\n"
            f"{context_block}\n\n"
            f"Assemble a brief structured summary (2-4 short paragraphs) of what "
            f"is known about this topic from these sources. Cite sources by their "
            f"source tags like [knowledge#1] or [conversations#2]. Do not analyze "
            f"or extrapolate beyond what is there; just summarize what the sources "
            f"actually say."
        )
        # Dispatch through call_local_endpoint so MLX / Ollama / auto all
        # work transparently; the function handles per-engine protocol
        # differences (Ollama POST /api/chat vs MLX in-process generate).
        from boot import call_local_endpoint
        summary_text = call_local_endpoint(
            [{"role": "user", "content": prompt}],
            ep,
        )
        if isinstance(summary_text, str) and summary_text.startswith("[Error"):
            raise RuntimeError(summary_text)
        if not summary_text:
            raise RuntimeError("model returned empty content")
    except Exception as e:
        # Model unreachable / timed out / empty — fall back to the raw
        # context block so the UI still has something useful to show.
        fallback        = True
        fallback_reason = str(e)
        summary_text = (
            f"**{topic}**\n\nModel assembly unavailable; here are the raw "
            f"matched sources:\n\n{context_block}"
        )

    out = {
        "topic":        topic,
        "summary":      summary_text,
        "match_count":  len(matches),
        "sources_used": [
            {"collection": m["collection"], "metadata": m["metadata"]}
            for m in matches
        ],
    }
    if fallback:
        out["fallback"]        = True
        out["fallback_reason"] = fallback_reason
    return json.dumps(out)


# ── V3 Backlog 11: errored-conversation lifecycle ────────────────────────────

@app.route("/api/conversation/<conversation_id>/mark-errored", methods=["POST"])
def conversations_mark_errored(conversation_id):
    """Mark a conversation's last run as errored — Backlog 11.

    Used by the pipeline-failure path (Backlog 2D) to flag the
    conversation for the sidebar's Errored group, and by tests to
    seed errored state. Body:

        { "summary": "<one-line failure summary>",
          "timestamp": "<optional ISO override>" }

    Returns 200 with ``{ok, last_status, last_error_summary}`` on
    success, 404 if conversation.json is missing.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}
    summary = (body.get("summary") if isinstance(body, dict) else "") or ""
    ts      = body.get("timestamp") if isinstance(body, dict) else None

    try:
        from conversation_memory import mark_conversation_errored
    except Exception as e:
        return json.dumps({"error": f"mark_conversation_errored import failed: {e}"}), 500

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({"status": "deleted"}), 410
        path = mark_conversation_errored(
            conversation_id,
            summary,
            timestamp=ts if isinstance(ts, str) else None,
        )
    if path is None:
        return json.dumps({"error": "Dialogue not found", "conversation_id": conversation_id}), 404
    return json.dumps({
        "ok":                 True,
        "last_status":        "errored",
        "last_error_summary": summary,
    })


@app.route("/api/conversation/<conversation_id>/dismiss-error", methods=["POST"])
def conversations_dismiss_error(conversation_id):
    """Clear the errored status on a conversation envelope — Backlog 11.

    Used by the dismiss action in the Errored sidebar group, and
    automatically by the retry endpoint on a successful resubmit.
    Returns 200 with ``{ok}`` whether or not the envelope had an error
    flag set (idempotent).
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    try:
        from conversation_memory import clear_conversation_error
    except Exception as e:
        return json.dumps({"error": f"clear_conversation_error import failed: {e}"}), 500
    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({"status": "deleted"}), 410
        path = clear_conversation_error(conversation_id)
    if path is None:
        return json.dumps({"error": "Dialogue not found", "conversation_id": conversation_id}), 404
    return json.dumps({"ok": True})


@app.route("/api/conversation/<conversation_id>/retry", methods=["POST"])
def conversations_retry(conversation_id):
    """Retry the last user prompt of an errored conversation — Backlog 11.

    Reads the conversation's most recent user message and returns it
    to the client so the client can re-submit through ``/chat/multipart``
    with whatever current canvas + tag context it has. The errored
    flag is NOT cleared automatically here — the client clears it via
    ``/dismiss-error`` after a successful resubmit, or leaves it if
    the retry failed too.

    Returns ``{ok, last_user_prompt, conversation_id}`` or 404 if the
    conversation doesn't exist or has no user messages to retry.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    try:
        from conversation_memory import load_conversation_json
    except Exception as e:
        return json.dumps({"error": f"load_conversation_json import failed: {e}"}), 500

    data = load_conversation_json(conversation_id)
    if data is None:
        return json.dumps({"error": "Dialogue not found", "conversation_id": conversation_id}), 404

    # V3 Backlog 2A Chunk 1 — orphan recovery: if this conversation was
    # flagged errored because the server was interrupted before the
    # pipeline could run (no save reached the envelope), the original
    # prompt lives in ``interrupted_input``. Prefer it over the last user
    # message in the envelope so retry re-submits exactly what the user
    # typed, not the prior turn's prompt.
    interrupted = data.get("interrupted_input")
    if isinstance(interrupted, str) and interrupted.strip():
        response = {
            "ok":               True,
            "conversation_id":  conversation_id,
            "last_user_prompt": interrupted,
            "tag":              data.get("tag", "") or "",
            "source":           "interrupted_input",
        }
        checkpoint_id = data.get("interrupted_visual_checkpoint_id")
        if (isinstance(checkpoint_id, str)
                and _VISUAL_CHECKPOINT_ID_RE.fullmatch(checkpoint_id)):
            response["visual_checkpoint_id"] = checkpoint_id
            response["visual_checkpoint_source_conversation_id"] = conversation_id
        return json.dumps(response)

    messages = data.get("messages") or []
    last_user_message = None
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            last_user_message = m
            break
    last_user = last_user_message.get("content") if last_user_message else None
    if not last_user:
        return json.dumps({"error": "no user prompt to retry", "conversation_id": conversation_id}), 404
    response = {
        "ok":               True,
        "conversation_id":  conversation_id,
        "last_user_prompt": last_user,
        "tag":              data.get("tag", "") or "",
        "source":           "messages",
    }
    checkpoint_id = last_user_message.get("visual_checkpoint_id")
    if (isinstance(checkpoint_id, str)
            and _VISUAL_CHECKPOINT_ID_RE.fullmatch(checkpoint_id)):
        response["visual_checkpoint_id"] = checkpoint_id
        response["visual_checkpoint_source_conversation_id"] = conversation_id
    return json.dumps(response)


# ── V3 Phase 1.5: conversation close-out dispatch ────────────────────────────

def _quiesce_conversation_workers(conversation_id: str) -> dict:
    """Stop conversation-keyed background writers before filesystem purge."""
    cleaned: dict[str, object] = {}
    errors: list[str] = []

    def run(label, callback):
        try:
            value = callback()
            cleaned[label] = value
            if isinstance(value, dict):
                for item in value.get("errors") or []:
                    errors.append(f"{label}: {item}")
        except Exception as exc:
            message = f"{label}: {exc}"
            errors.append(message)
            print(f"[conversation-lifecycle] worker cleanup {message}",
                  flush=True)

    if _HAS_CAPTURE and _get_capture_manager is not None:
        run("captures", lambda: _get_capture_manager().forget_conversation(
            conversation_id))
    if _HAS_TRANSCRIPTION and _get_transcription_manager is not None:
        run(
            "transcriptions",
            lambda: _get_transcription_manager().forget_conversation(
                conversation_id,
            ),
        )
    if _HAS_URL_IMPORT and _get_url_import_manager is not None:
        run("url_imports", lambda: _get_url_import_manager().forget_conversation(
            conversation_id))
    if _HAS_PREVIEW and _preview_forget_conversation is not None:
        run("preview", lambda: _preview_forget_conversation(conversation_id))
    if _HAS_RENDER and _get_render_manager is not None:
        run("renders", lambda: _get_render_manager().forget_conversation(
            conversation_id))
    if _HAS_JOB_QUEUE and _get_job_queue is not None:
        run("job_queue", lambda: _get_job_queue().forget_conversation(
            conversation_id))
    # Media registration callbacks run outside the Flask lifecycle lock.
    # Tombstone and drain both possible import identities before filesystem
    # purge so a stale add_entry cannot recreate media JSON/thumbnails after
    # the session tree has been removed.
    for label, module_name in (
        ("media_library", "media_library"),
        ("media_library_package", "orchestrator.media_library"),
    ):
        module = sys.modules.get(module_name)
        callback = getattr(module, "forget_library", None) if module else None
        if callback is not None:
            run(label, lambda _callback=callback: _callback(conversation_id))
    run("documents", lambda: __import__(
        "orchestrator.document_input", fromlist=["purge_conversation"]
    ).purge_conversation(conversation_id))

    return {"cleaned": cleaned, "errors": errors}


def _release_conversation_runtime_memory(conversation_id: str) -> dict:
    """Release finished media bookkeeping for a conversation being closed.

    Ora keeps per-conversation records in memory for renders, transcriptions,
    captures, URL imports and queued jobs, plus cached timelines and media
    libraries. Until now the only thing that released them was Delete Forever,
    which is available on Off-Record Dialogues alone — so for every Standard
    and Private Dialogue those records lived for the life of the process.

    Close is the right place to release them, but Close is REVERSIBLE and
    retains data, so this is deliberately not the Delete Forever path:

      * nothing is tombstoned — a restored Dialogue can still render, record
        and import, which ``forget_conversation`` would have made impossible;
      * nothing in flight is disturbed — a render, transcription, capture or
        download still running keeps its record and its subprocess, because
        closing a Dialogue is not a request to abandon work;
      * no file is touched — the outputs, and the on-disk mirrors the two
        caches reload from, are exactly as they were.

    Best-effort by design: a failure here must never stop a Close, so every
    call is guarded and the errors are reported rather than raised.
    """
    released: dict[str, object] = {}
    errors: list[str] = []

    def run(label, callback):
        try:
            released[label] = callback()
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            print(f"[conversation-lifecycle] memory release {label}: {exc}",
                  flush=True)

    if _HAS_CAPTURE and _get_capture_manager is not None:
        run("captures", lambda: _get_capture_manager().release_finished(
            conversation_id))
    if _HAS_TRANSCRIPTION and _get_transcription_manager is not None:
        run("transcriptions",
            lambda: _get_transcription_manager().release_finished(
                conversation_id))
    if _HAS_URL_IMPORT and _get_url_import_manager is not None:
        run("url_imports", lambda: _get_url_import_manager().release_finished(
            conversation_id))
    if _HAS_RENDER and _get_render_manager is not None:
        run("renders", lambda: _get_render_manager().release_finished(
            conversation_id))
    if _HAS_JOB_QUEUE and _get_job_queue is not None:
        run("job_queue", lambda: _get_job_queue().release_cached(
            conversation_id))

    # The two disk-backed caches. Both import identities are probed for the
    # same reason the purge path does it — orchestrator/ is on sys.path, so a
    # packaged and a bare import are separate module objects with separate
    # caches, and only the copies this process actually has are touched.
    for label, module_name, function_name in (
        ("timeline", "timeline", "release_timeline"),
        ("timeline_package", "orchestrator.timeline", "release_timeline"),
        ("media_library", "media_library", "release_library"),
        ("media_library_package", "orchestrator.media_library", "release_library"),
    ):
        module = sys.modules.get(module_name)
        callback = getattr(module, function_name, None) if module else None
        if callback is not None:
            run(label, lambda _cb=callback: _cb(conversation_id))

    return {"released": released, "errors": errors}


def _clear_conversation_runtime_state(conversation_id: str) -> dict:
    """Drop content-bearing caches and Ora-owned staging copies."""
    counts: dict[str, object] = {}
    errors: list[str] = []
    identity = _conversation_storage_identity(conversation_id)
    for value in list(_pending_conversations):
        if _conversation_storage_identity(value) == identity:
            _pending_conversations.discard(value)
    for mapping in (
        _pending_clarification,
        _session_data,
        _bridge_state,
        _vision_retry_queue,
    ):
        for key in list(mapping):
            if _conversation_storage_identity(key) == identity:
                mapping.pop(key, None)
    with _conversation_lifecycle_guard:
        _conversation_creation_tags.pop(identity, None)
        _unreadable_conversations.discard(identity)
        _closed_conversations.discard(identity)

    # Aside histories contain the full user/assistant text for up to five
    # turns.  Clear the already-instantiated window without calling the
    # getter, which would manufacture a new correlated cache entry while a
    # Delete Forever purge is in progress.
    if SIDEBAR_WINDOW_AVAILABLE:
        try:
            counts["sidebar_windows"] = clear_sidebar_window(conversation_id)
        except Exception as exc:
            errors.append(f"sidebar_window: {exc}")

    # Both package-qualified and legacy top-level imports may already exist in
    # a long-running process. Clear either cache without instantiating one.
    for label, module_name, function_name in (
        ("timeline", "timeline", "forget_timeline"),
        ("timeline_package", "orchestrator.timeline", "forget_timeline"),
    ):
        module = sys.modules.get(module_name)
        callback = getattr(module, function_name, None) if module else None
        if callback is not None:
            try:
                counts[label] = bool(callback(conversation_id))
            except Exception as exc:
                errors.append(f"{label}: {exc}")

    # Multipart media uploads are Ora-owned copies. Registered external paths
    # and user-configured capture/render outputs are references/exports and are
    # deliberately retained.
    try:
        removed_staging = _purge_media_library_staging(conversation_id)
    except Exception as exc:
        removed_staging = 0
        errors.append(f"media_staging: {exc}")
    counts["media_staging_files"] = removed_staging

    for render_id, cid in list(_render_conversation_lookup.items()):
        if _conversation_storage_identity(cid) == identity:
            _render_conversation_lookup.pop(render_id, None)

    identity = conversation_id.casefold()
    with _transcription_metadata_lock:
        transcription_ids = [
            tid for tid, cid in _transcription_conversations.items()
            if cid.casefold() == identity
        ]
        for tid in transcription_ids:
            _transcription_conversations.pop(tid, None)
            _transcription_tags.pop(tid, None)
            _transcription_source_paths.pop(tid, None)
            _transcription_vault_paths.pop(tid, None)
            _transcription_vault_status.pop(tid, None)
            _transcription_vault_errors.pop(tid, None)
    counts["transcription_metadata"] = len(transcription_ids)

    for message in errors:
        print(f"[conversation-lifecycle] runtime cleanup {message}", flush=True)
    return {"cleared": counts, "errors": errors}


def _assert_stealth_permanent_delete(conversation_id: str) -> None:
    """Refuse permanent deletion unless Stealth is authoritative."""
    from orchestrator.conversation_memory import (
        _DEFAULT_SESSIONS_ROOT,
        _conversation_path,
        read_conversation_history_envelope,
    )

    envelope = read_conversation_history_envelope(conversation_id)
    if isinstance(envelope, dict):
        if envelope.get("tag") != "stealth":
            raise PermissionError(
                "Delete Forever is available only for Off Record Dialogues; "
                "Standard and Private Dialogues use Close"
            )
        return

    live_path = _conversation_path(conversation_id, _DEFAULT_SESSIONS_ROOT)
    archived_path = _conversation_path(
        conversation_id, _DEFAULT_SESSIONS_ROOT / "archived",
    )
    if (live_path.exists() or live_path.is_symlink()
            or archived_path.exists() or archived_path.is_symlink()):
        raise PermissionError(
            "Delete Forever requires a readable authoritative Off Record envelope"
        )

    with _conversation_lifecycle_guard:
        creation_tag = _conversation_creation_tags.get(
            _conversation_storage_identity(conversation_id)
        )
    if creation_tag != "stealth":
        raise PermissionError(
            "Delete Forever is available only for Off Record Dialogues; "
            "Standard and Private Dialogues use Close"
        )


def _delete_conversation_runtime(conversation_id: str) -> dict:
    """Tombstone, quiesce, purge, and clear one Stealth conversation."""
    if not _valid_existing_conversation_id(conversation_id):
        raise ValueError("invalid conversation_id")
    lifecycle_lock = _conversation_lifecycle_lock(conversation_id)
    # Inspect the authoritative envelope under the same barrier as writers,
    # then install the tombstone before releasing it. A request waiting behind
    # this block observes the tombstone and cannot create new residue.
    with lifecycle_lock:
        _assert_stealth_permanent_delete(conversation_id)
        with _conversation_lifecycle_guard:
            _deleted_conversations.add(
                _conversation_storage_identity(conversation_id)
            )

    # Worker shutdown may join a thread whose completion callback briefly
    # consults the server lifecycle state. Do not hold the server lock while
    # joining it; the tombstone plus the drained request barrier above already
    # prevents any new writer from being created in this interval.
    workers = _quiesce_conversation_workers(conversation_id)

    with lifecycle_lock:
        try:
            from orchestrator.conversation_closeout import (
                delete_conversation_forever,
            )
            result = delete_conversation_forever(
                conversation_id,
                chromadb_path=_configured_conversation_chromadb_path(),
            )
        except Exception as exc:
            print(f"[conversation-lifecycle] permanent purge failed for "
                  f"{conversation_id}: {exc}", flush=True)
            result = {
                "conversation_id": conversation_id,
                "action": "delete_forever",
                "deleted": {},
                "retained": {"explicit_vault_exports": True},
                "errors": [f"permanent purge: {exc}"],
            }
        runtime = _clear_conversation_runtime_state(conversation_id)
        result.setdefault("errors", []).extend(workers["errors"])
        result["errors"].extend(runtime["errors"])
        result["worker_cleanup"] = workers["cleaned"]
        result["runtime_cleanup"] = runtime["cleared"]
        result["limitations"] = {
            "external_provider_retention": (
                "Delete Forever removes active Ora-managed local copies, but "
                "cannot recall prompts, responses, or files already sent to a "
                "remote model, transcription, search, or other provider. Any "
                "provider-side copy remains subject to that provider's policy."
            ),
            "bounded_in_flight_remote_work": (
                "Ora cancels and waits for correlated local workers only for a "
                "bounded interval. A remote request already in flight may finish "
                "provider-side even though Ora rejects and purges its late result."
            ),
            "repository_history": (
                "Removing an active vault or app file does not rewrite Git, "
                "backup, filesystem-snapshot, or other external history."
            ),
            "explicit_and_configured_outputs": (
                "Files explicitly exported to the vault and user-configured "
                "capture or render destinations are user-owned outputs and remain."
            ),
            "registered_external_sources": (
                "Media or documents registered by reference outside Ora's managed "
                "staging/session roots remain at their original paths."
            ),
            "document_staging_after_restart": (
                "Pre-change flat staged document uploads whose in-memory "
                "conversation association was lost before this process started "
                "cannot be identified safely by filename alone. New uploads use "
                "durable per-conversation staging directories."
            ),
            "legacy_flat_media_staging": (
                "Pre-change flat media-staging files that are not referenced "
                "by surviving metadata cannot be safely attributed because "
                "legacy conversation IDs used ambiguous filename prefixes."
            ),
            "legacy_sanitized_id_artifacts": (
                "Pre-change job, upload, canvas, and retry artifacts for "
                "punctuation-bearing IDs may share an underscore-sanitized "
                "path with another conversation; ambiguous files are retained "
                "rather than risking deletion of sibling data."
            ),
            "legacy_runtime_derivative_ownership": (
                "Pre-change Engram or Incubator notes that cite this Dialogue "
                "but lack the complete Ora ownership marker are retained as "
                "ambiguous user-vault content. New runtime derivatives carry "
                "strict ownership fields."
            ),
        }
        return result


def _conversation_protection_state(conversation_id: str) -> dict:
    from orchestrator import system_protection as _sp
    selector = "dialogue:" + _conversation_storage_identity(conversation_id)
    body = {
        "selector": selector,
        "kind": "dialogue",
        "conversation_id_digest": _sp.params_digest({
            "conversation_id": _conversation_storage_identity(conversation_id),
        }),
        "deleted": bool(_is_conversation_deleted(conversation_id)),
        "tag": _effective_conversation_tag(conversation_id, ""),
    }
    body["digest"] = _sp.params_digest(body)
    return body


def _protected_delete_conversation_runtime(conversation_id: str) -> dict:
    """Delete one exact Dialogue only after Paused one-shot approval."""
    from orchestrator import system_protection as _sp
    with _conversation_lifecycle_lock(conversation_id):
        _assert_stealth_permanent_delete(conversation_id)
    pre_state = _conversation_protection_state(conversation_id)
    protection = _sp.authorize_server_action(
        "dialogue_delete",
        selectors=[pre_state["selector"]],
        params={"conversation_id_digest": pre_state["conversation_id_digest"]},
        pre_state=[pre_state],
    )
    try:
        with _sp.protected_effect(protection):
            result = _delete_conversation_runtime(conversation_id)
    except Exception as exc:
        try:
            _sp.complete_execution(
                protection, ok=False, result={"error": type(exc).__name__},
                post_state=[_conversation_protection_state(conversation_id)],
            )
        except Exception as receipt_error:
            raise _sp.ProtectionAuditError(
                f"Dialogue deletion failed and its failure receipt could not persist: {receipt_error}"
            ) from exc
        raise
    _sp.complete_execution(
        protection, ok=not bool(result.get("errors")), result=result,
        post_state=[_conversation_protection_state(conversation_id)],
    )
    return result

@app.route("/api/conversation/<conversation_id>/close", methods=["POST"])
def conversation_close(conversation_id):
    """Dispatch close-out for a conversation based on its tag.

    The dispatch reads the authoritative ``tag`` from conversation.json and:

    * empty (standard) → 200 with action "close"; envelope stamped
      ``closed: true`` so the sidebar filters it out. Data is retained.
    * ``private`` → 200 with action "close"; same envelope flag.
    * ``stealth`` → full purge (session dir, chunks, raw log, ChromaDB
      records); 200 with action "purge" and the deletion summary

    Per-layer failures during purge are collected and returned in
    ``errors`` so the UI can surface them — the endpoint never aborts on
    a partial failure.

    Explicit flat vault exports and referenced sidecars under
    ``Vault/Sessions/`` are not auto-purged; export is user-initiated and
    out-of-band.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({
                "status": "deleted", "conversation_id": conversation_id,
            }), 410
        try:
            from orchestrator.conversation_memory import (
                load_conversation_json,
                _conversation_path,
                _DEFAULT_SESSIONS_ROOT,
            )
            envelope = load_conversation_json(conversation_id)
            envelope_path = _conversation_path(
                conversation_id, _DEFAULT_SESSIONS_ROOT,
            )
            if envelope is None and not (
                envelope_path.exists() or envelope_path.is_symlink()
            ):
                with _conversation_lifecycle_guard:
                    creation_tag = _conversation_creation_tags.get(
                        _conversation_storage_identity(conversation_id), "",
                    )
                    _closed_conversations.add(
                        _conversation_storage_identity(conversation_id)
                    )
                return json.dumps({
                    "conversation_id": conversation_id,
                    "tag": creation_tag,
                    "action": "close",
                    "closed": False,
                    "local_only": True,
                    "errors": [],
                }), 200
        except Exception as exc:
            # Close remains available; the authoritative resolver below logs
            # and applies the unreadable-envelope safety policy if needed.
            print(f"[conversation-lifecycle] close preflight failed open for "
                  f"{conversation_id}: {exc}", file=sys.stderr, flush=True)

    effective_tag = _effective_conversation_tag(conversation_id, "")
    with _conversation_lifecycle_guard:
        unreadable = (
            _conversation_storage_identity(conversation_id)
            in _unreadable_conversations
        )
    if unreadable:
        return json.dumps({
            "error": (
                "conversation envelope is unreadable; Close will not guess "
                "its retention policy. Repair it or use Delete Forever."
            ),
            "conversation_id": conversation_id,
        }), 409
    if effective_tag == "stealth":
        try:
            result = _protected_delete_conversation_runtime(conversation_id)
        except Exception as exc:
            try:
                from orchestrator import system_protection as _sp
                if isinstance(exc, _sp.SystemProtectionError):
                    return _system_protection_error_response(exc)
            except Exception:
                pass
            raise
        result["action"] = "purge"  # legacy close contract
        result["tag"] = "stealth"
        return json.dumps(result), 200

    try:
        from orchestrator.conversation_closeout import close_conversation
    except Exception as e:
        return json.dumps({"error": f"close_conversation import failed: {e}"}), 500

    try:
        with _conversation_lifecycle_lock(conversation_id):
            if _is_conversation_deleted(conversation_id):
                return json.dumps({
                    "status": "deleted", "conversation_id": conversation_id,
                }), 410
            result = close_conversation(
                conversation_id,
                chromadb_path=_configured_conversation_chromadb_path(),
            )
            if result.get("closed"):
                with _conversation_lifecycle_guard:
                    _closed_conversations.add(
                        _conversation_storage_identity(conversation_id)
                    )
                # Release finished media bookkeeping now the Dialogue is
                # closed. Reversible and data-retaining: nothing tombstoned,
                # nothing in flight disturbed, no file touched.
                release = _release_conversation_runtime_memory(conversation_id)
                if release.get("errors"):
                    result.setdefault("errors", []).extend(release["errors"])
    except Exception as e:
        return json.dumps({
            "error": f"close_conversation failed: {e}",
            "conversation_id": conversation_id,
        }), 500

    return json.dumps(result), 200


@app.route("/api/conversation/<conversation_id>/delete-forever", methods=["POST"])
def conversation_delete_forever(conversation_id):
    """Permanently delete one Stealth Dialogue's Ora-managed stores.

    Explicit flat vault exports and their sidecars remain user-owned.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    try:
        result = _protected_delete_conversation_runtime(conversation_id)
    except PermissionError as exc:
        return _json_response({"error": str(exc)}, status=409)
    except Exception as exc:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(exc, _sp.SystemProtectionError):
                return _system_protection_error_response(exc)
        except Exception:
            pass
        return _json_response({"error": str(exc)}, status=500)
    return json.dumps(result), 200


@app.route("/api/conversation/<conversation_id>/privacy-tag", methods=["POST"])
def conversation_privacy_tag(conversation_id):
    """Move a current Dialogue between Standard and Private.

    A zero-turn Dialogue receives a durable empty envelope here so any
    pre-turn document/canvas/media artifacts share the same privacy and
    deletion lifecycle across restarts.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    body = request.get_json(force=True, silent=True) or {}
    target = body.get("tag") if isinstance(body, dict) else None
    if target not in {"", "private"}:
        return json.dumps({
            "error": "tag must be standard ('') or private; Off Record is creation-only",
        }), 400

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({
                "status": "deleted", "conversation_id": conversation_id,
            }), 410
        try:
            from orchestrator.conversation_memory import (
                load_conversation_json,
                _conversation_path,
                _DEFAULT_SESSIONS_ROOT,
            )
            envelope_created = False
            if load_conversation_json(conversation_id) is None:
                envelope_path = _conversation_path(
                    conversation_id, _DEFAULT_SESSIONS_ROOT,
                )
                if envelope_path.exists() or envelope_path.is_symlink():
                    return json.dumps({
                        "error": "conversation envelope is unreadable",
                        "conversation_id": conversation_id,
                    }), 409
                creation_tag = _effective_conversation_tag(
                    conversation_id, "",
                )
                if creation_tag == "stealth":
                    return json.dumps({
                        "error": "Off Record is creation-only and cannot be retagged",
                    }), 409
                _effective, envelope_created = (
                    _ensure_artifact_conversation_envelope(
                        conversation_id, creation_tag,
                    )
                )
            from orchestrator.conversation_closeout import (
                update_conversation_privacy_tag,
            )
            from orchestrator import document_input as _document_input
            document_result = {"jobs": 0, "outputs": 0, "errors": []}
            # Tightening privacy updates live document writers first; a
            # failure leaves the authoritative envelope Standard. Relaxing
            # privacy changes the envelope/caches first so any stale document
            # output remains over-protected until its follow-up rewrite.
            if target == "private":
                document_result = _document_input.update_conversation_tag(
                    conversation_id, target,
                )
            result = update_conversation_privacy_tag(
                conversation_id,
                target,
                chromadb_path=_configured_conversation_chromadb_path(),
            )
            if target == "" and result.get("envelope_updated"):
                document_result = _document_input.update_conversation_tag(
                    conversation_id, target,
                )
            result["document_jobs"] = document_result
            result["envelope_created"] = envelope_created
            result.setdefault("errors", []).extend(
                document_result.get("errors") or []
            )
        except PermissionError as exc:
            return json.dumps({"error": str(exc)}), 409
        except ValueError as exc:
            return json.dumps({"error": str(exc)}), 400
        except Exception as exc:
            print(f"[conversation-lifecycle] privacy update failed: {exc}",
                  flush=True)
            return json.dumps({"error": str(exc)}), 500
        if not result.get("envelope_updated"):
            return json.dumps({
                "error": "privacy change was not committed",
                **result,
            }), 409
        return json.dumps({"ok": True, **result}), 200


# ── V3 Backlog 2C: rename a conversation's display name ─────────────────────

@app.route("/api/conversation/<conversation_id>/rename", methods=["POST"])
def conversation_rename(conversation_id):
    """Update the conversation's user-facing display name.

    The conversation_id is unchanged. Only ``display_name`` on the
    conversation.json envelope is updated, which iter_conversations
    reads as the title surfaced in the sidebar and output-pane header.

    Body:
        { "display_name": "<new name, max 200 chars>" }
        Empty string clears the override (UI falls back to derived title).
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site

    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}
    new_name = body.get("display_name") if isinstance(body, dict) else None
    if not isinstance(new_name, str):
        new_name = ""

    try:
        from orchestrator.conversation_memory import (
            set_display_name,
            load_conversation_json,
            effective_conversation_title,
        )
        from orchestrator.conversation_closeout import (
            refresh_conversation_title_metadata,
        )
    except Exception as e:
        return json.dumps({"error": f"set_display_name import failed: {e}"}), 500

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({
                "status": "deleted", "conversation_id": conversation_id,
            }), 410
        previous_data = load_conversation_json(conversation_id) or {}
        previous_title = effective_conversation_title(previous_data)
        path = set_display_name(conversation_id, new_name)
        if path is None:
            return json.dumps({
                "error": "conversation not found or unwriteable",
                "conversation_id": conversation_id,
            }), 404

        data = load_conversation_json(conversation_id) or {}
        effective_title = effective_conversation_title(data)
        metadata = (
            refresh_conversation_title_metadata(
                conversation_id, effective_title,
                chromadb_path=_configured_conversation_chromadb_path(),
                previous_title=previous_title,
            )
            if effective_title
            else {"chromadb_records": 0, "errors": []}
        )
        return json.dumps({
            "ok": True,
            "conversation_id": conversation_id,
            "display_name": data.get("display_name", ""),
            "conversation_title": effective_title,
            "chromadb_records": metadata.get("chromadb_records", 0),
            "errors": metadata.get("errors", []),
        })


# ── V3 Backlog 3F: user-pinned conversations ────────────────────────────────

@app.route("/api/conversation/<conversation_id>/pin", methods=["POST"])
def conversation_pin(conversation_id):
    """Toggle (or explicitly set) the user-pinned state on a conversation.

    Pinned conversations surface in the sidebar's Pinned group at the top
    of the list, independent of Unread / Active / Pending classification.

    Body (optional):
        { "pinned": true | false }
    Omitted body toggles the current state.
    """
    conversation_id = (conversation_id or "").strip()
    if not _valid_existing_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400

    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}

    try:
        from conversation_memory import (
            set_conversation_pinned,
            load_conversation_json,
        )
    except Exception as e:
        return json.dumps({"error": f"set_conversation_pinned import failed: {e}"}), 500

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({"status": "deleted"}), 410
        if isinstance(body, dict) and "pinned" in body:
            target_pinned = bool(body.get("pinned"))
        else:
            existing = load_conversation_json(conversation_id) or {}
            target_pinned = not bool(existing.get("pinned"))

        path = set_conversation_pinned(conversation_id, target_pinned)
    if path is None:
        return json.dumps({
            "error": "Dialogue not found or unwriteable",
            "conversation_id": conversation_id,
        }), 404

    return json.dumps({
        "ok": True,
        "conversation_id": conversation_id,
        "pinned": target_pinned,
    })


# ── V3 Backlog 6: right-side scratchpad ─────────────────────────────────────

@app.route("/api/aside/models", methods=["GET"])
def aside_models():
    """Return only model ids accepted by the explicit Aside resolver."""
    try:
        return json.dumps({"models": list_interactive_endpoints()})
    except Exception as exc:
        print(f"[aside] model inventory failed open: {exc}",
              file=sys.stderr, flush=True)
        return json.dumps({"models": [], "error": str(exc)})

@app.route("/api/scratchpad", methods=["POST"])
def api_scratchpad():
    """Plain-HTTP Aside endpoint for the right-column Q&A.

    V3 Backlog 2A Chunk 4 (2026-04-30) — migrated from SSE streaming. The
    user does not see model thinking; the answer is pushed to the right-
    column output as soon as it's ready. The dedicated Aside model preference
    is independent of the active configuration's SMALL/utility cell. Context
    is an in-memory five-turn rolling window; nothing is written to disk or
    ChromaDB. The client separately keeps its visible DOM history bounded.

    Request body:
        { "prompt": "<string>" }

    Response (200, application/json):
        { "answer": "<assistant text>" }

    Failure (200, application/json):
        { "error": "<description>" }

    400 only on missing/empty prompt or malformed JSON.
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return json.dumps({"error": "invalid JSON body"}), 400

    if not isinstance(data, dict):
        return json.dumps({"error": "Aside request must be an object"}), 400
    unexpected = sorted(set(data) - {"prompt"})
    if unexpected:
        return json.dumps({
            "error": "Aside is informational and cannot carry Run or transfer fields",
            "unsupported_fields": unexpected,
        }), 422

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"}), 400

    try:
        cfg = load_config()
        try:
            if not _HAS_USER_SETTINGS or _user_settings is None:
                raise RuntimeError("user settings module is unavailable")
            preferred_id = _user_settings.get_setting("aside.model_id", "")
        except Exception as settings_exc:
            preferred_id = ""
            print(f"[aside] model preference read failed: {settings_exc}; "
                  "falling back to SMALL/utility", file=sys.stderr, flush=True)

        ep = get_endpoint_by_id(preferred_id) if preferred_id else None
        if preferred_id and not ep:
            print(f"[aside] preferred endpoint {preferred_id!r} is unavailable; "
                  "falling back to SMALL/utility", file=sys.stderr, flush=True)
        if not ep:
            ep = get_slot_endpoint(cfg, "sidebar")
        if not ep:
            error = "Aside model and SMALL fallback are not configured"
            print(f"[aside] {error}", file=sys.stderr, flush=True)
            return json.dumps({"error": error})

        window = get_sidebar_window("aside")
        # One window transaction spans context read + model call + append, so
        # rapid submits cannot both read the same prior turn and then land out
        # of causal order. The lock is per window, not process-global.
        with window.transaction():
            messages = window.get_history()
            messages.append({"role": "user", "content": prompt})
            answer = call_model(messages, ep)
            if isinstance(answer, str) and answer.lstrip().startswith("[Error"):
                print(f"[aside] model call failed open: {answer}",
                      file=sys.stderr, flush=True)
                return json.dumps({"error": answer})
            if not isinstance(answer, str) or not answer.strip():
                error = "Aside model returned no response"
                print(f"[aside] {error}", file=sys.stderr, flush=True)
                return json.dumps({"error": error})
            window.add_exchange(prompt, answer)
        return json.dumps({
            "answer": answer,
            "surface_contract": {
                "surface": "aside",
                "persisted": False,
                "authoritative": False,
                "run_effects": [],
                "transfer_requires": "explicit_send_or_attachment",
            },
        })
    except Exception as e:
        print(f"[aside] request failed open: {e}", file=sys.stderr, flush=True)
        return json.dumps({"error": str(e)})


# ── WP-4.4: queue-for-later endpoint ─────────────────────────────────────────

@app.route("/chat/queue-retry", methods=["POST"])
def chat_queue_retry():
    """Persist a vision-retry request for later processing.

    Payload (application/json)::

        {
          "conversation_id": "<string, required>",
          "image_path":      "<absolute path or URL, required>",
          "attempt_reason":  "no_vision_available" | "extraction_failed"
        }

    Response (200)::

        { "queued": true, "queue_size": <int>, "entry": { ... } }

    Response (400)::

        { "error": "<description>" }

    Storage: entries land both in a module-level in-memory dict keyed by
    ``conversation_id`` (volatile, survives the life of the server process)
    AND in a per-session JSON file at
    ``~/ora/sessions/<conversation_id>/vision-retry-queue.json`` (durable
    across server restarts). Writes are best-effort; disk failures are
    logged but do not fail the endpoint.

    NO automatic retry here — a future daemon or user-triggered action will
    flush the queue. This endpoint is purely persistence.
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return json.dumps({"error": "invalid JSON body"}), 400

    conversation_id = (data.get("conversation_id") or "").strip()
    image_path = (data.get("image_path") or "").strip()
    attempt_reason = (data.get("attempt_reason") or "").strip()

    if not _valid_live_conversation_id(conversation_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    if not image_path:
        return json.dumps({"error": "image_path is required"}), 400
    if attempt_reason not in ("no_vision_available", "extraction_failed"):
        return json.dumps({
            "error": "attempt_reason must be 'no_vision_available' or 'extraction_failed'",
            "received": attempt_reason,
        }), 400

    with _conversation_lifecycle_lock(conversation_id):
        if _is_conversation_deleted(conversation_id):
            return json.dumps({
                "status": "deleted", "conversation_id": conversation_id,
            }), 410
        entry = {
            "conversation_id": conversation_id,
            "image_path": image_path,
            "attempt_reason": attempt_reason,
            "queued_at": datetime.now().isoformat(),
        }

        # Merge the disk queue with the in-memory queue (disk wins on
        # restart). The lifecycle lock spans read + write so Delete Forever
        # cannot purge between them and then receive a recreated queue file.
        existing = _vision_retry_queue.get(conversation_id)
        if existing is None:
            existing = _load_vision_retry_queue(conversation_id)
        existing.append(entry)
        _vision_retry_queue[conversation_id] = existing
        _persist_vision_retry_queue(conversation_id, existing)

    return json.dumps({
        "queued": True,
        "queue_size": len(existing),
        "entry": entry,
    }), 200


# ── bridge state (in-memory, volatile) ───────────────────────────────────────
# {panel_id: {current_topic, recent_messages, active_mode, active_gear, pipeline_stage}}
_bridge_state = {}
_pipeline_state = {"stage": None, "stages": [], "active": False}

def _persist_turn_spatial_state_unlocked(
        panel_id, user_input, ai_response, extra_context, tag="",
        trace_ref=None):
    """WP-5.3 — append this turn to conversation.json so subsequent turns
    can retrieve the prior spatial state.

    Each turn's ``spatial_representation``, ``annotations``, and
    ``vision_extraction_result`` are persisted from ``extra_context``. If
    ``extra_context`` is None or missing a given field, that slot stores
    as ``None`` — forward-compat safe, backward-compat safe.

    Normal chat completion calls this synchronously under the lifecycle lock;
    a few legacy resume paths still use the locked background wrapper below.
    Returns the durable path only when the authoritative append succeeds;
    exceptions are logged and become a false acknowledgement. conversation.json
    is the source of truth for both visual state and Dialogue continuity.
    """
    try:
        from orchestrator.conversation_memory import save_turn_spatial_state
        spatial_rep = None
        annotations = None
        vision_extr = None
        visual_checkpoint_id = None
        if isinstance(extra_context, dict):
            spatial_rep = extra_context.get("spatial_representation")
            annotations = extra_context.get("annotations")
            vision_extr = extra_context.get("vision_extraction_result")
            visual_checkpoint_id = extra_context.get("visual_checkpoint_id")
        try:
            from orchestrator.active_project import (
                get_active_project,
                resolve_project_ids,
            )
            _project_ids = resolve_project_ids(get_active_project())
        except Exception:
            _project_ids = None
        return save_turn_spatial_state(
            conversation_id=panel_id,
            user_input=user_input,
            ai_response=ai_response,
            spatial_representation=spatial_rep,
            annotations=annotations,
            vision_extraction_result=vision_extr,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            tag=tag,
            project_ids=_project_ids,
            trace_ref=trace_ref,
            visual_checkpoint_id=visual_checkpoint_id,
        )
    except Exception as e:
        print(f"[WARNING] WP-5.3 conversation.json persist failed: {e}")
        return None


def _turn_envelope_acknowledged(
        panel_id, expected_message_count, user_input, ai_response):
    """Confirm a turn reached the envelope if a writer lost its return value."""
    try:
        from orchestrator.conversation_memory import load_conversation_json
        data = load_conversation_json(panel_id)
    except Exception:
        return False
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list) or not isinstance(expected_message_count, int):
        return False
    if len(messages) != expected_message_count + 2:
        return False
    user_message, assistant_message = messages[-2:]
    return (
        isinstance(user_message, dict)
        and user_message.get("role") == "user"
        and user_message.get("content") == user_input
        and isinstance(assistant_message, dict)
        and assistant_message.get("role") == "assistant"
        and assistant_message.get("content") == ai_response
    )


def _persist_turn_spatial_state(panel_id, user_input, ai_response,
                                extra_context, tag="", trace_ref=None):
    """Persist envelope state only while the conversation remains live."""
    with _conversation_lifecycle_lock(panel_id):
        if _is_conversation_deleted(panel_id):
            return None
        effective_tag = _effective_conversation_tag(panel_id, tag)
        return _persist_turn_spatial_state_unlocked(
            panel_id, user_input, ai_response, extra_context, effective_tag,
            trace_ref=trace_ref,
        )


# ── runtime pipeline helper ──────────────────────────────────────────────────

def _run_end_of_session_pipeline_unlocked(user_input, ai_response, panel_id, config, history=None):
    """Run end-of-session processing inside its background lifecycle worker.

    The caller already runs on a daemon thread and holds the conversation
    lifecycle lock.  Running the pipeline synchronously *on that thread*
    keeps Delete Forever and privacy changes behind every derivative write;
    ``RuntimePipeline.run_async`` used to release the lock immediately and
    could recreate staging, Chroma, logs, or promoted engrams after purge.
    """
    if not RUNTIME_PIPELINE_AVAILABLE:
        return
    try:
        from orchestrator.tools.runtime_pipeline import SessionData
        sess = _session_data.get(panel_id, {})
        bridge = _bridge_state.get(panel_id, {})

        # Build full conversation history including the current exchange
        conv_history = [
            dict(message)
            for message in (history or [])
            if isinstance(message, dict)
        ]
        conv_history.append({"role": "user", "content": user_input})
        conv_history.append({"role": "assistant", "content": ai_response})

        session_data = SessionData(
            session_id=sess.get("session_id", "unknown"),
            timestamp=datetime.now().isoformat(),
            mode=bridge.get("active_mode", ""),
            gear=bridge.get("active_gear", 0) or 0,
            conversation_id=panel_id,
            conversation_tag=_effective_conversation_tag(panel_id, ""),
            models_used=[sess.get("model", "")],
            user_prompt=user_input,
            final_output=ai_response,
            conversation_history=conv_history,
            source_type="chat",
        )
        pipeline = RuntimePipeline(config=config, call_fn=call_model)
        pipeline.run_sync(session_data)
    except Exception as exc:
        # Runtime extraction remains fail-open for the delivered turn, but a
        # failure must be observable rather than silently disappearing.
        print(f"[runtime-pipeline] conversation {panel_id}: {exc}",
              file=sys.stderr, flush=True)


def _run_end_of_session_pipeline(user_input, ai_response, panel_id, config,
                                 history=None):
    """Start extraction only for a still-live, non-Stealth conversation."""
    with _conversation_lifecycle_lock(panel_id):
        if (_is_conversation_deleted(panel_id)
                or _is_conversation_closed(panel_id)
                or _effective_conversation_tag(panel_id, "") == "stealth"):
            return
        _run_end_of_session_pipeline_unlocked(
            user_input, ai_response, panel_id, config, history,
        )


# V3 Phase 1.4 — /api/incognito and /api/incognito/toggle endpoints removed.
# Mode dispatch is now per-conversation via the ``tag`` field; close-out
# happens through /api/conversation/<conversation_id>/close (Phase 1.5).


# ── sidebar window API ───────────────────────────────────────────────────────

@app.route("/api/sidebar/clear", methods=["POST"])
def sidebar_clear():
    """Clear a sidebar panel's rolling window."""
    if not SIDEBAR_WINDOW_AVAILABLE:
        return json.dumps({"error": "Sidebar window not available"}), 501
    data = request.get_json(force=True)
    pid = data.get("panel_id", "sidebar")
    clear_sidebar_window(pid)
    return json.dumps({"ok": True, "panel_id": pid})

@app.route("/api/sidebar/status")
def sidebar_status():
    """Get sidebar window status."""
    if not SIDEBAR_WINDOW_AVAILABLE:
        return json.dumps({"available": False})
    pid = request.args.get("panel_id", "sidebar")
    win = get_sidebar_window(pid)
    return json.dumps({
        "available": True,
        "panel_id": pid,
        "turn_count": win.get_turn_count(),
        "max_turns": win.max_turns,
    })


# ── static files ──────────────────────────────────────────────────────────────

@app.route("/static/visual-schemas/<path:filename>")
def serve_visual_schemas(filename):
    root = os.path.join(WORKSPACE, "config", "visual-schemas")
    safe = os.path.normpath(os.path.join(root, filename))
    if not safe.startswith(root):
        return "Forbidden", 403
    return send_from_directory(root, filename)


# WP-7.1.1 / WP-7.1.2 — visual-pane toolbar packs. visual-toolbar.js (and
# OraVisualDock via the panel) lazy-fetches /static/config/toolbars/*.json
# when the registry doesn't already contain a definition. The files live
# at ~/ora/config/toolbars/, NOT under server/static, so we map the URL
# space explicitly.
@app.route("/static/config/toolbars/<path:filename>")
def serve_toolbar_packs(filename):
    root = os.path.join(WORKSPACE, "config", "toolbars")
    safe = os.path.normpath(os.path.join(root, filename))
    if not safe.startswith(root):
        return "Forbidden", 403
    return send_from_directory(root, filename)


# WP-7.0.4 — pack-validator schema. OraPackValidator.init() needs the toolbar
# pack JSON Schema to compile its Ajv validator before ANY toolbar register()
# call can succeed. Schemas live at ~/ora/config/schemas/.
@app.route("/static/config/schemas/<path:filename>")
def serve_config_schemas(filename):
    root = os.path.join(WORKSPACE, "config", "schemas")
    safe = os.path.normpath(os.path.join(root, filename))
    if not safe.startswith(root):
        return "Forbidden", 403
    return send_from_directory(root, filename)


# WP-7.8 — installable packs (Diagram Thinking / Photo Editor / Mood Board /
# Cartoon Studio). Pack JSONs live at ~/ora/config/packs/. The V3 boot loads
# defaults named in ~/ora/config/packs/_defaults.json on page load.
@app.route("/static/config/packs/<path:filename>")
def serve_config_packs(filename):
    root = os.path.join(WORKSPACE, "config", "packs")
    safe = os.path.normpath(os.path.join(root, filename))
    if not safe.startswith(root):
        return "Forbidden", 403
    return send_from_directory(root, filename)


# WP-7.3 — capability slot contracts. Pack-toolbar capability:* bindings need
# this so the invocation UI can render the right form per slot. Source of
# truth is ~/ora/config/capabilities.json.
@app.route("/static/config/capabilities.json")
def serve_capabilities_json():
    return send_from_directory(os.path.join(WORKSPACE, "config"), "capabilities.json")


@app.route("/static/<path:filename>")
def serve_static(filename):
    safe = os.path.normpath(os.path.join(WORKSPACE, "server", "static", filename))
    if not safe.startswith(os.path.join(WORKSPACE, "server", "static")):
        return "Forbidden", 403
    return send_from_directory(os.path.join(WORKSPACE, "server", "static"), filename)

# ── V3 theme library API ──────────────────────────────────────────────────
# Folder-per-theme structure used by /v3 — each theme is a directory under
# server/static/themes/<id>/ containing manifest.json and theme.css.
# Index of installed themes lives at server/static/themes/index.json.

V3_THEMES_DIR = os.path.join(WORKSPACE, "server/static/themes/")
V3_THEMES_INDEX = os.path.join(V3_THEMES_DIR, "index.json")
COMMUNITY_DIRECTORY_URL = "https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/community-css-themes.json"
V3_ORA_THEME_FORMAT = "ora-theme/v1"
V3_CUSTOMIZATIONS_START = "/* ora-customizations:start */"
V3_CUSTOMIZATIONS_END = "/* ora-customizations:end */"
V3_CSS_VAR_RE = re.compile(r'(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+);?')
V3_VALID_CSS_VAR_RE = re.compile(r'^--[A-Za-z0-9_-]+$')
_V3_DEFAULT_THEME_VARS_CACHE = None

V3_DEFAULT_THEME_SOURCE_FILES = [
    "server/static/styles/tokens/foundations.css",
    "server/static/styles/tokens/dark.css",
    "server/static/styles/tokens/light.css",
    "server/static/styles/tokens/ora-extensions.css",
    "server/static/ora-visual-compiler/ora-visual-theme.css",
]

V3_BODY_VAR_CANDIDATES = {
    "--font-text": ["--font-text", "--font-interface"],
    "--font-monospace": ["--font-monospace"],
    "--ora-font-body": ["--ora-font-body", "--font-text", "--font-interface"],
    "--ora-font-mono": ["--ora-font-mono", "--font-monospace"],
}

V3_SCOPE_VAR_CANDIDATES = {
    "--background-primary": ["--background-primary"],
    "--background-secondary": ["--background-secondary", "--background-primary-alt"],
    "--background-modifier-form-field": [
        "--background-modifier-form-field",
        "--background-secondary",
        "--background-secondary-alt",
    ],
    "--background-modifier-border": [
        "--background-modifier-border",
        "--background-modifier-border-hover",
    ],
    "--background-modifier-border-focus": [
        "--background-modifier-border-focus",
        "--interactive-accent",
        "--color-accent",
    ],
    "--background-modifier-hover": [
        "--background-modifier-hover",
        "--interactive-hover",
        "--background-secondary-alt",
    ],
    "--interactive-normal": [
        "--interactive-normal",
        "--background-secondary",
    ],
    "--interactive-hover": [
        "--interactive-hover",
        "--background-modifier-hover",
        "--background-secondary-alt",
    ],
    "--interactive-accent": [
        "--interactive-accent",
        "--color-accent",
        "--link-color",
        "--text-accent",
    ],
    "--interactive-accent-hover": [
        "--interactive-accent-hover",
        "--color-accent",
        "--link-color-hover",
        "--text-accent-hover",
    ],
    "--interactive-accent-faint": [
        "--interactive-accent-faint",
        "--color-accent",
        "--link-color",
    ],
    "--icon-color": [
        "--icon-color",
        "--text-muted",
    ],
    "--icon-color-hover": [
        "--icon-color-hover",
        "--text-normal",
    ],
    "--text-normal": ["--text-normal"],
    "--text-muted": ["--text-muted"],
    "--text-faint": ["--text-faint"],
    "--text-on-accent": [
        "--text-on-accent",
        "--background-primary",
    ],
    "--text-error": [
        "--text-error",
        "--color-red",
        "--color-warning",
    ],
    "--text-warning": [
        "--text-warning",
        "--color-orange",
        "--color-warning",
    ],
    "--link-color": [
        "--link-color",
        "--text-accent",
        "--interactive-accent",
        "--color-accent",
    ],
    "--link-color-hover": [
        "--link-color-hover",
        "--text-accent-hover",
        "--interactive-accent-hover",
        "--color-accent",
    ],
    "--color-accent": [
        "--color-accent",
        "--interactive-accent",
        "--link-color",
        "--text-accent",
    ],
}

V3_HEADING_COLOR_CANDIDATES = {
    "--h1-color": ["--h1-color", "--color-purple", "--color-accent"],
    "--h2-color": ["--h2-color", "--color-green"],
    "--h3-color": ["--h3-color", "--color-yellow"],
    "--h4-color": ["--h4-color", "--color-red"],
    "--h5-color": ["--h5-color", "--link-color", "--color-orange"],
    "--h6-color": ["--h6-color", "--color-orange"],
}

V3_COLOR_RGB_PAIRS = [
    "--color-red",
    "--color-orange",
    "--color-yellow",
    "--color-green",
    "--color-blue",
    "--color-cyan",
    "--color-purple",
    "--color-pink",
    "--color-active",
    "--color-warning",
    "--color-accent",
]


def _v3_empty_var_scopes():
    return {"root": {}, "body": {}, "light": {}, "dark": {}}


def _v3_clean_css_value(value):
    value = str(value or "").strip().rstrip(";").strip()
    if not value or "{" in value or "}" in value:
        return None
    return value


def _v3_extract_css_vars(css):
    """Extract CSS custom properties into broad theme scopes.

    Ora imports Obsidian themes as a variable source, not as executable
    selector CSS. This deliberately keeps only custom-property declarations
    found in root/body/light/dark-ish blocks and discards raw app selectors.
    """
    scopes = _v3_empty_var_scopes()
    cleaned = re.sub(r'/\*.*?\*/', '', css or '', flags=re.S)
    for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', cleaned, flags=re.S):
        declarations = {}
        for match in V3_CSS_VAR_RE.finditer(body):
            value = _v3_clean_css_value(match.group(2))
            if value:
                declarations[match.group(1)] = value
        if not declarations:
            continue

        lower = selector.lower()
        targets = []
        if ".theme-light" in lower:
            targets.append("light")
        if ".theme-dark" in lower:
            targets.append("dark")
        if ":root" in lower or re.search(r'(^|[,\s])html($|[,\s.#:])', lower):
            targets.append("root")
        if not targets and re.search(r'(^|[,\s])body($|[,\s.#:])', lower):
            targets.append("body")
        if not targets:
            # Some themes put variables on app wrappers. Lift the variables,
            # but not the selectors, so Ora still receives a usable palette.
            targets.append("root")

        for target in dict.fromkeys(targets):
            scopes[target].update(declarations)
    return scopes


def _v3_merge_var_scopes(target, source):
    for scope, values in (source or {}).items():
        target.setdefault(scope, {}).update(values or {})


def _v3_default_theme_vars():
    global _V3_DEFAULT_THEME_VARS_CACHE
    if _V3_DEFAULT_THEME_VARS_CACHE is not None:
        return {
            scope: dict(values)
            for scope, values in _V3_DEFAULT_THEME_VARS_CACHE.items()
        }

    merged = _v3_empty_var_scopes()
    for rel_path in V3_DEFAULT_THEME_SOURCE_FILES:
        path = os.path.join(WORKSPACE, rel_path)
        try:
            with open(path, encoding="utf-8") as f:
                _v3_merge_var_scopes(merged, _v3_extract_css_vars(f.read()))
        except Exception:
            continue

    merged["body"].setdefault("--ora-font-body", "var(--font-text)")
    merged["body"].setdefault("--ora-font-mono", "var(--font-monospace)")
    _V3_DEFAULT_THEME_VARS_CACHE = {
        scope: dict(values)
        for scope, values in merged.items()
    }
    return _v3_default_theme_vars()


def _v3_lookup_var(scopes, scope, name):
    search_order = [scope]
    if scope in ("light", "dark"):
        search_order.extend(["body", "root"])
    elif scope == "body":
        search_order.append("root")
    for candidate_scope in search_order:
        value = (scopes.get(candidate_scope) or {}).get(name)
        if value:
            return value
    return None


def _v3_choose_var(source, out, scope, candidates, fallback=None):
    for name in candidates:
        value = _v3_lookup_var(source, scope, name)
        if value:
            return value
    for name in candidates:
        value = _v3_lookup_var(out, scope, name)
        if value:
            return value
    return fallback


def _v3_rgb_from_color(value):
    value = (value or "").strip()
    hex_match = re.match(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', value)
    if hex_match:
        raw = hex_match.group(1)
        if len(raw) == 3:
            raw = ''.join(ch + ch for ch in raw)
        return ", ".join(str(int(raw[i:i + 2], 16)) for i in (0, 2, 4))

    rgb_match = re.match(
        r'^rgba?\(\s*([0-9.]+)[,\s]+([0-9.]+)[,\s]+([0-9.]+)',
        value,
        flags=re.I,
    )
    if rgb_match:
        return ", ".join(str(int(float(rgb_match.group(i)))) for i in (1, 2, 3))
    return None


def _v3_set_rgb_pair(scope_vars, color_name):
    rgb_name = f"{color_name}-rgb"
    if scope_vars.get(rgb_name):
        return
    rgb = _v3_rgb_from_color(scope_vars.get(color_name))
    if rgb:
        scope_vars[rgb_name] = rgb


def _v3_apply_scope_derivations(source, out, scope):
    vars_for_scope = out[scope]

    for dest, candidates in V3_SCOPE_VAR_CANDIDATES.items():
        fallback = vars_for_scope.get(dest)
        chosen = _v3_choose_var(source, out, scope, candidates, fallback)
        if chosen:
            vars_for_scope[dest] = chosen

    for color_name in V3_COLOR_RGB_PAIRS:
        rgb_name = f"{color_name}-rgb"
        color_value = _v3_lookup_var(source, scope, color_name)
        rgb_value = _v3_lookup_var(source, scope, rgb_name)
        if color_value:
            vars_for_scope[color_name] = color_value
            if not rgb_value:
                vars_for_scope.pop(rgb_name, None)
        if rgb_value:
            vars_for_scope[rgb_name] = rgb_value

    semantic_colors = {
        "--color-accent": ["--color-accent", "--interactive-accent", "--link-color"],
        "--color-active": ["--color-active", "--interactive-accent", "--color-green"],
        "--color-warning": ["--color-warning", "--text-error", "--color-red"],
    }
    for dest, candidates in semantic_colors.items():
        chosen = _v3_choose_var(source, out, scope, candidates, vars_for_scope.get(dest))
        if chosen:
            vars_for_scope[dest] = chosen
            vars_for_scope.pop(f"{dest}-rgb", None)

    for dest, candidates in V3_HEADING_COLOR_CANDIDATES.items():
        chosen = _v3_choose_var(source, out, scope, candidates, vars_for_scope.get(dest))
        if chosen:
            vars_for_scope[dest] = chosen

    border = vars_for_scope.get("--background-modifier-border")
    text = vars_for_scope.get("--text-normal")
    muted = vars_for_scope.get("--text-muted")
    faint = vars_for_scope.get("--text-faint")
    link = vars_for_scope.get("--link-color")
    hover = vars_for_scope.get("--link-color-hover") or link
    form = vars_for_scope.get("--background-modifier-form-field")
    secondary = vars_for_scope.get("--background-secondary")
    primary = vars_for_scope.get("--background-primary")
    red = vars_for_scope.get("--color-red")
    orange = vars_for_scope.get("--color-orange")
    yellow = vars_for_scope.get("--color-yellow")
    green = vars_for_scope.get("--color-green")
    blue = vars_for_scope.get("--color-blue")
    cyan = vars_for_scope.get("--color-cyan")
    purple = vars_for_scope.get("--color-purple")
    pink = vars_for_scope.get("--color-pink")
    warning = vars_for_scope.get("--color-warning") or red
    accent = vars_for_scope.get("--interactive-accent") or link

    derived = {
        "--ora-button-border": border,
        "--ora-wordmark-base": muted,
        "--ora-wordmark-bright": faint or muted,
        "--ora-wordmark-hover": text,
        "--ora-line-dot-color": border,
        "--ora-input-pane-border": border,
        "--ora-output-pane-border": border,
        "--ora-visual-canvas-border": border,
        "--ora-visual-canvas-bg": secondary,
        "--ora-visual-toolbar-bg": secondary,
        "--ora-visual-toolbar-border": border,
        "--ora-mode-private-pane-border": green,
        "--ora-mode-private-button-border": green,
        "--ora-mode-private-button-icon": green,
        "--ora-mode-private-label": green,
        "--ora-mode-stealth-pane-border": red,
        "--ora-mode-stealth-button-border": red,
        "--ora-mode-stealth-button-icon": red,
        "--ora-mode-stealth-label": red,
        "--text-primary": text,
        "--text-secondary": muted,
        "--border": border,
        "--accent": accent,
        "--accent-hover": hover,
        "--accent-muted": vars_for_scope.get("--background-modifier-hover") or form,
        "--accent-text": vars_for_scope.get("--text-on-accent") or primary,
        "--bg-panel": "transparent",
        "--bg-toolbar": secondary,
        "--bg-hover": vars_for_scope.get("--background-modifier-hover") or form,
        "--bg-canvas-a": border,
        "--ora-status-ok": green,
        "--ora-status-error": warning,
        "--ora-status-warning": orange or yellow,
        "--ora-bg-1": primary,
        "--ora-bg-2": secondary,
        "--ora-fg": text,
        "--ora-border": border,
        "--ora-accent": accent,
        "--ora-vis-bg": primary,
        "--ora-vis-surface": form or secondary,
        "--ora-vis-text": text,
        "--ora-vis-text-secondary": muted,
        "--ora-vis-gridline": border,
        "--ora-vis-axis": muted or text,
        "--ora-vis-rule": border,
        "--ora-vis-cat-1": blue or accent,
        "--ora-vis-cat-2": orange or red,
        "--ora-vis-cat-3": green,
        "--ora-vis-cat-4": purple or pink,
        "--ora-vis-cat-5": yellow or orange,
        "--ora-vis-cat-6": cyan or blue,
        "--ora-vis-cat-7": yellow,
        "--ora-vis-cat-8": text,
        "--ora-vis-highlight": warning,
        "--ora-vis-muted": muted,
        "--ora-vis-positive": green,
        "--ora-vis-negative": warning,
        "--ora-vis-neutral": muted,
        "--ora-vis-ibis-question": blue or accent,
        "--ora-vis-ibis-idea": yellow or orange,
        "--ora-vis-ibis-pro": green,
        "--ora-vis-ibis-con": warning,
        "--ora-vis-dag-exposure": blue or accent,
        "--ora-vis-dag-outcome": orange or red,
        "--ora-vis-dag-latent": muted,
        "--ora-vis-c4-person": blue or accent,
        "--ora-vis-c4-system": text,
        "--ora-vis-c4-container": muted,
        "--ora-vis-c4-external": faint or muted,
        "--ora-vis-stub-bg": secondary,
        "--ora-vis-stub-border": border,
        "--ora-vis-stub-text": muted,
        "--ora-vis-focus-ring": accent,
    }

    if "--ora-bridge-handle" not in vars_for_scope:
        vars_for_scope["--ora-bridge-handle"] = (
            "rgba(1, 1, 1, 0.18)"
            if scope == "light"
            else "rgba(255, 255, 255, 0.18)"
        )

    for name, value in derived.items():
        source_value = _v3_lookup_var(source, scope, name)
        if source_value:
            vars_for_scope[name] = source_value
        elif value:
            vars_for_scope[name] = value

    for color_name in V3_COLOR_RGB_PAIRS:
        _v3_set_rgb_pair(vars_for_scope, color_name)


def _v3_convert_obsidian_theme(css, manifest=None):
    source = _v3_extract_css_vars(css)
    out = _v3_default_theme_vars()

    for scope, vars_for_scope in out.items():
        for var_name in list(vars_for_scope.keys()):
            source_value = _v3_lookup_var(source, scope, var_name)
            if source_value:
                vars_for_scope[var_name] = source_value

    for dest, candidates in V3_BODY_VAR_CANDIDATES.items():
        fallback = out["body"].get(dest)
        chosen = _v3_choose_var(source, out, "body", candidates, fallback)
        if chosen:
            out["body"][dest] = chosen

    for scope in ("light", "dark"):
        _v3_apply_scope_derivations(source, out, scope)

    name = (manifest or {}).get("name") or "Imported Obsidian Theme"
    return _v3_render_theme_vars_css(
        out,
        [
            f"Converted from Obsidian CSS for Ora: {name}",
            "Raw selectors were discarded; missing Ora variables were derived",
            "from matching Obsidian variables and Ora's default theme.",
        ],
    )


def _v3_render_theme_vars_css(scopes, header_lines=None):
    blocks = []
    if header_lines:
        blocks.append("/*")
        for line in header_lines:
            blocks.append(f"   {line}")
        blocks.append("*/")

    selector_for_scope = {
        "root": ":root",
        "body": "body",
        "light": ".theme-light",
        "dark": ".theme-dark",
    }
    for scope in ("root", "body", "light", "dark"):
        vars_for_scope = scopes.get(scope) or {}
        if not vars_for_scope:
            continue
        blocks.append(f"{selector_for_scope[scope]} {{")
        for name, value in vars_for_scope.items():
            cleaned = _v3_clean_css_value(value)
            if V3_VALID_CSS_VAR_RE.match(name) and cleaned:
                blocks.append(f"  {name}: {cleaned};")
        blocks.append("}")
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def _v3_customizations_to_css(customizations):
    customizations = customizations or {}
    lines = []
    for name, value in customizations.items():
        cleaned = _v3_clean_css_value(value)
        if V3_VALID_CSS_VAR_RE.match(str(name)) and cleaned:
            lines.append(f"  {name}: {cleaned};")
    if not lines:
        return ""
    return (
        f"{V3_CUSTOMIZATIONS_START}\n"
        ":root, body, body.theme-dark, body.theme-light {\n"
        + "\n".join(lines)
        + "\n}\n"
        f"{V3_CUSTOMIZATIONS_END}\n"
    )


def _v3_replace_customizations(css, customizations):
    pattern = re.compile(
        re.escape(V3_CUSTOMIZATIONS_START)
        + r'.*?'
        + re.escape(V3_CUSTOMIZATIONS_END)
        + r'\n?',
        flags=re.S,
    )
    base = pattern.sub("", css or "").rstrip()
    section = _v3_customizations_to_css(customizations)
    if not section:
        return base + ("\n" if base else "")
    return base + "\n\n" + section


def _v3_manifest_is_ora(manifest):
    fmt = (manifest or {}).get("oraThemeFormat") or (manifest or {}).get("ora_theme_format")
    return fmt == V3_ORA_THEME_FORMAT

def _v3_slugify(text):
    slug = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return slug or 'theme'

def _v3_read_index():
    try:
        with open(V3_THEMES_INDEX) as f:
            return json.load(f)
    except Exception:
        return {"themes": []}


def _v3_list_project_themes():
    """Walk every registered project and return its declared themes
    (Plugin Convention §13) as a flat list of entries shaped to match
    the V3 themes-index entry schema with the synthesized fields:

      * ``origin`` = "project:<nexus>" (project-shipped theme)
      * ``bundled`` = False (project themes are not core-bundled)
      * ``project_nexus`` = <nexus> (used by /themes/project/<nexus>/...)

    Defensive: if project_registry isn't importable for any reason, the
    server still boots and just serves core themes — same fallback the
    capability_registry merge uses.
    """
    try:
        from orchestrator import project_registry as _pr
        projects = _pr.list_projects()
    except Exception:
        return []
    out = []
    for p in projects:
        for theme_id, theme in (getattr(p, "themes", {}) or {}).items():
            out.append({
                "id": theme_id,
                "name": theme.name,
                "directory": theme.directory,
                "bundled": False,
                "origin": f"project:{p.nexus}",
                "project_nexus": p.nexus,
            })
    return out


def _v3_aggregate_themes():
    """Merge core themes (from ``server/static/themes/index.json``) with
    project-declared themes per Plugin Convention §13.

    Collision rules per §13:
      * **Project shadows project.** Hard error — both projects lose the
        theme. Diagnostic printed; the theme is dropped from the merged
        list entirely.
      * **Project shadows core.** Allowed. Project's entry wins;
        diagnostic printed.
      * **User-installed shadows project.** Allowed (publisher override).
        The core/user-installed entry wins because it's already in the
        core index.

    Reserved: `default` from any project is dropped at parse time
    (project_registry rejects it), so no special handling here.
    """
    core_index = _v3_read_index()
    core_entries = list(core_index.get("themes", []))
    core_ids = {e.get("id") for e in core_entries if e.get("id")}

    project_entries = _v3_list_project_themes()

    # Pass 1: detect project-shadows-project collisions
    seen_by: dict[str, list[str]] = {}
    for e in project_entries:
        tid = e["id"]
        seen_by.setdefault(tid, []).append(e["project_nexus"])
    collided = {tid for tid, ns in seen_by.items() if len(ns) > 1}
    for tid in sorted(collided):
        print(
            f"[server] Theme id {tid!r} declared by multiple projects "
            f"({seen_by[tid]}); dropping from all of them. "
            f"Unregister one project to resolve the collision."
        )

    # Pass 2: filter out collided + user-installed-shadows + emit
    # diagnostics for project-shadows-core.
    merged = list(core_entries)
    for e in project_entries:
        if e["id"] in collided:
            continue
        if e["id"] in core_ids:
            # User-installed at server/static/themes/<id>/ wins over the
            # project (publisher override). Skip the project entry.
            print(
                f"[server] Project {e['project_nexus']!r} declares theme "
                f"{e['id']!r}, but a core/user-installed theme with the "
                f"same id exists; the core entry wins."
            )
            continue
        merged.append(e)

    return merged


def _v3_theme_css_url_for(entry):
    """Return the URL the UI should fetch theme.css from, based on the
    entry's origin. Core / user-installed themes serve from the existing
    /static/themes/<id>/theme.css path (Flask static handler). Project
    themes serve from the new /themes/project/<nexus>/theme.css route.
    """
    if entry.get("origin", "").startswith("project:"):
        return f"/themes/project/{entry['project_nexus']}/theme.css"
    return f"/static/themes/{entry['id']}/theme.css"

def _v3_project_theme_asset_path(entry, filename):
    from orchestrator import project_registry as _pr
    project = _pr.get_project(entry["project_nexus"])
    if project is None:
        return None
    asset_dir = (project.root / entry["directory"]).resolve()
    target = (asset_dir / filename).resolve()
    try:
        target.relative_to(asset_dir)
    except ValueError:
        return None
    return target if target.is_file() else None


def _v3_find_theme_entry(theme_id):
    for entry in _v3_aggregate_themes():
        if entry.get("id") == theme_id:
            return entry
    return None


def _v3_read_theme_asset(theme_id, filename):
    entry = _v3_find_theme_entry(theme_id)
    if not entry:
        raise FileNotFoundError(f"Theme not found: {theme_id}")
    if entry.get("origin", "").startswith("project:"):
        path = _v3_project_theme_asset_path(entry, filename)
    else:
        path = os.path.join(V3_THEMES_DIR, theme_id, filename)
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"Theme asset not found: {theme_id}/{filename}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _v3_read_theme_manifest(theme_id):
    try:
        return json.loads(_v3_read_theme_asset(theme_id, "manifest.json"))
    except Exception:
        return {}


def _v3_existing_theme_ids():
    ids = set()
    for entry in _v3_read_index().get("themes", []):
        if entry.get("id"):
            ids.add(entry["id"])
    for entry in _v3_list_project_themes():
        if entry.get("id"):
            ids.add(entry["id"])
    try:
        for name in os.listdir(V3_THEMES_DIR):
            if re.match(r'^[a-z0-9_-]+$', name):
                ids.add(name)
    except Exception:
        pass
    return ids


def _v3_unique_theme_id(base_id):
    base = _v3_slugify(base_id)
    if base == "default":
        base = "ora-default-copy"
    existing = _v3_existing_theme_ids()
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _v3_write_index(data):
    os.makedirs(V3_THEMES_DIR, exist_ok=True)
    with open(V3_THEMES_INDEX, "w") as f:
        json.dump(data, f, indent=2)

def _v3_theme_dir(theme_id):
    if not re.match(r'^[a-z0-9_-]+$', theme_id or ''):
        raise ValueError(f"Invalid theme id: {theme_id}")
    return os.path.join(V3_THEMES_DIR, theme_id)

def _v3_install(theme_id, name, manifest, css, overwrite=False):
    theme_id = _v3_slugify(theme_id)
    if theme_id == "default":
        raise ValueError("Cannot overwrite default theme")
    if not overwrite:
        theme_id = _v3_unique_theme_id(theme_id)
    theme_dir = _v3_theme_dir(theme_id)
    os.makedirs(theme_dir, exist_ok=True)
    manifest = dict(manifest or {})
    manifest.setdefault("name", name)
    manifest.setdefault("version", "1.0.0")
    with open(os.path.join(theme_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(theme_dir, "theme.css"), "w") as f:
        f.write(css)
    index = _v3_read_index()
    updated = False
    for entry in index.get("themes", []):
        if entry.get("id") == theme_id:
            entry.update({
                "name": name,
                "directory": theme_id,
                "bundled": False,
            })
            updated = True
            break
    if not updated:
        index.setdefault("themes", []).append({
            "id": theme_id,
            "name": name,
            "directory": theme_id,
            "bundled": False,
        })
    _v3_write_index(index)
    return {"ok": True, "id": theme_id, "name": name}

@app.route("/api/v3-themes/list")
def v3_themes_list_api():
    """Aggregate core + project-declared themes per Plugin Convention §13.

    Each returned entry carries the existing index-entry fields plus:
      * ``manifest`` (parsed manifest.json contents, or {} on failure)
      * ``theme_css_url`` (the URL the UI should fetch theme.css from —
        differs for core vs project themes; UI shouldn't hard-code paths)
      * ``origin`` (synthesized for project themes: "project:<nexus>"; the
        existing ``bundled`` flag is preserved for core entries)
    """
    out = []
    for entry in _v3_aggregate_themes():
        theme_id = entry.get("id")
        if not theme_id:
            continue
        manifest = {}
        # Project themes resolve their manifest.json from the project's
        # directory; core / user-installed themes from server/static/themes/.
        if entry.get("origin", "").startswith("project:"):
            try:
                from orchestrator import project_registry as _pr
                project = _pr.get_project(entry["project_nexus"])
                if project is not None:
                    manifest_path = (project.root / entry["directory"]
                                     / "manifest.json")
                    with open(manifest_path) as f:
                        manifest = json.load(f)
            except Exception:
                pass
        else:
            manifest_path = os.path.join(
                V3_THEMES_DIR, theme_id, "manifest.json",
            )
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
            except Exception:
                pass
        out.append({
            **entry,
            "manifest": manifest,
            "theme_css_url": _v3_theme_css_url_for(entry),
        })
    return json.dumps({"themes": out})


@app.route("/themes/project/<nexus>/<path:filename>")
def v3_themes_project_asset(nexus, filename):
    """Serve a project theme asset (theme.css / manifest.json / etc.).

    Resolves through project_registry.get_project(nexus) to find the
    project's ora-project root, then through the project's declared
    ``themes[<id>].directory`` to find the asset directory. The
    ``nexus`` URL segment identifies the project; the project may
    declare multiple themes — for v1, we accept any filename relative
    to the FIRST theme directory declared by that project. If the
    project declares multiple themes, the request must include the
    theme id implicitly via the directory match.

    Implementation note: most projects declare at most one theme, so
    the v1 heuristic of "use the directory of the theme whose assets
    contain the requested filename" is sufficient. Projects that ship
    multiple themes can disambiguate by giving each theme a uniquely-
    named asset OR by structuring requests through theme-specific
    subpaths under the directory.

    Path-safety: forbid traversal — no ``..`` segments, no absolute
    paths — so a crafted URL can't escape the project's theme dir.
    """
    if ".." in filename.split("/") or filename.startswith("/"):
        return Response("Forbidden", status=403)
    try:
        from orchestrator import project_registry as _pr
        project = _pr.get_project(nexus)
    except Exception:
        return Response("Project registry unavailable", status=503)
    if project is None:
        return Response(f"No project registered: {nexus!r}", status=404)
    themes = getattr(project, "themes", {}) or {}
    if not themes:
        return Response(
            f"Project {nexus!r} declares no themes", status=404,
        )

    # Search each declared theme's directory for the filename; serve the
    # first match. Sufficient for projects with one theme (the common
    # case) AND projects with multiple themes when asset filenames are
    # unique across themes (theme.css / manifest.json typically are).
    for theme in themes.values():
        asset_dir = (project.root / theme.directory).resolve()
        target = (asset_dir / filename).resolve()
        # Path-safety: target must be under asset_dir after resolve()
        try:
            target.relative_to(asset_dir)
        except ValueError:
            continue
        if target.is_file():
            return send_from_directory(
                str(asset_dir), filename,
            )
    return Response(
        f"Asset not found in any theme declared by {nexus!r}: "
        f"{filename}",
        status=404,
    )

@app.route("/api/v3-themes/install", methods=["POST"])
def v3_themes_install_api():
    data = request.get_json(force=True) or {}
    manifest = dict(data.get("manifest") or {})
    name = data.get("name") or manifest.get("name")
    css = data.get("css")
    if not name or not css:
        return json.dumps({"error": "Missing name or css"}), 400
    theme_id = _v3_slugify(name)
    if theme_id == "default":
        return json.dumps({"error": "Cannot overwrite default theme"}), 400
    try:
        if not _v3_manifest_is_ora(manifest):
            css = _v3_convert_obsidian_theme(css, manifest)
            manifest["sourceFormat"] = "obsidian-css"
        manifest["oraThemeFormat"] = V3_ORA_THEME_FORMAT
        manifest["oraImportedAt"] = datetime.now(timezone.utc).isoformat()
        result = _v3_install(theme_id, name, manifest, css)
        result["theme_css_url"] = f"/static/themes/{result['id']}/theme.css"
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


def _v3_zip_read_theme_file(zf, basename):
    candidates = []
    for name in zf.namelist():
        if name.endswith("/") or name.startswith("__MACOSX/"):
            continue
        if name.split("/")[-1] == basename:
            candidates.append(name)
    if not candidates:
        raise FileNotFoundError(f"{basename} not found in theme zip")
    preferred = sorted(candidates, key=lambda n: (n.count("/"), n))[0]
    return zf.read(preferred).decode("utf-8")


@app.route("/api/v3-themes/install-zip", methods=["POST"])
def v3_themes_install_zip_api():
    upload = request.files.get("file") if request.files else None
    if not upload:
        return json.dumps({"error": "Missing theme zip"}), 400
    try:
        with zipfile.ZipFile(io.BytesIO(upload.read())) as zf:
            manifest = json.loads(_v3_zip_read_theme_file(zf, "manifest.json"))
            css = _v3_zip_read_theme_file(zf, "theme.css")
        name = request.form.get("name") or manifest.get("name")
        if not name:
            name = os.path.splitext(upload.filename or "theme")[0]
        theme_id = _v3_slugify(name)
        if theme_id == "default":
            return json.dumps({"error": "Cannot overwrite default theme"}), 400
        if _v3_manifest_is_ora(manifest):
            manifest["oraThemeFormat"] = V3_ORA_THEME_FORMAT
        else:
            css = _v3_convert_obsidian_theme(css, manifest)
            manifest["sourceFormat"] = "obsidian-zip"
            manifest["oraThemeFormat"] = V3_ORA_THEME_FORMAT
        manifest["oraImportedAt"] = datetime.now(timezone.utc).isoformat()
        result = _v3_install(theme_id, name, manifest, css)
        result["theme_css_url"] = f"/static/themes/{result['id']}/theme.css"
        return json.dumps(result)
    except zipfile.BadZipFile:
        return json.dumps({"error": "Invalid zip file"}), 400
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


@app.route("/api/v3-themes/<theme_id>/duplicate", methods=["POST"])
def v3_themes_duplicate_api(theme_id):
    data = request.get_json(silent=True) or {}
    try:
        entry = _v3_find_theme_entry(theme_id)
        if not entry:
            return json.dumps({"error": "Theme not found"}), 404
        base_manifest = _v3_read_theme_manifest(theme_id)
        base_name = base_manifest.get("name") or entry.get("name") or theme_id
        name = data.get("name") or f"{base_name} Customized"
        customizations = data.get("customizations") or {}
        css = _v3_read_theme_asset(theme_id, "theme.css")
        css = _v3_replace_customizations(css, customizations)

        manifest = dict(base_manifest)
        manifest["name"] = name
        manifest.setdefault("version", "1.0.0")
        manifest["oraThemeFormat"] = V3_ORA_THEME_FORMAT
        manifest["oraThemeSource"] = {
            "kind": "derived",
            "parentId": theme_id,
            "parentName": base_name,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

        result = _v3_install(_v3_slugify(name), name, manifest, css)
        result["theme_css_url"] = f"/static/themes/{result['id']}/theme.css"
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


@app.route("/api/v3-themes/<theme_id>/save-customizations", methods=["POST"])
def v3_themes_save_customizations_api(theme_id):
    data = request.get_json(force=True) or {}
    try:
        entry = _v3_find_theme_entry(theme_id)
        if not entry:
            return json.dumps({"error": "Theme not found"}), 404
        if theme_id == "default" or entry.get("bundled") or entry.get("origin", "").startswith("project:"):
            return json.dumps({"error": "Duplicate this theme before customizing it"}), 409

        theme_dir = _v3_theme_dir(theme_id)
        css_path = os.path.join(theme_dir, "theme.css")
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        css = _v3_replace_customizations(css, data.get("customizations") or {})
        with open(css_path, "w", encoding="utf-8") as f:
            f.write(css)

        manifest_path = os.path.join(theme_dir, "manifest.json")
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = {}
        manifest["oraThemeFormat"] = V3_ORA_THEME_FORMAT
        manifest["oraCustomizedAt"] = datetime.now(timezone.utc).isoformat()
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return json.dumps({"ok": True, "id": theme_id})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/v3-themes/<theme_id>", methods=["DELETE"])
def v3_themes_delete_api(theme_id):
    if theme_id == "default":
        return json.dumps({"error": "Cannot delete default theme"}), 400
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection = None
    try:
        from orchestrator import system_protection as _sp
        theme_dir = _v3_theme_dir(theme_id)
        selectors = [
            _sp.path_selector(theme_dir),
            _sp.path_selector(V3_THEMES_INDEX),
        ]
        pre_state = [
            _sp.capture_path_identity(theme_dir),
            _sp.capture_path_identity(V3_THEMES_INDEX),
        ]
        protection = _sp.authorize_server_action(
            "theme_delete", selectors=selectors,
            params={"theme_id": theme_id}, pre_state=pre_state,
        )
        with _sp.protected_effect(protection):
            if os.path.isdir(theme_dir):
                shutil.rmtree(theme_dir)
            index = _v3_read_index()
            index["themes"] = [
                t for t in index.get("themes", []) if t.get("id") != theme_id
            ]
            _v3_write_index(index)
        _sp.complete_execution(
            protection, ok=True, result={"ok": True, "theme_id": theme_id},
            post_state=[
                _sp.capture_path_identity(theme_dir),
                _sp.capture_path_identity(V3_THEMES_INDEX),
            ],
        )
        return json.dumps({"ok": True})
    except Exception as e:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(e, _sp.SystemProtectionError):
                return _system_protection_error_response(e)
            if protection is not None:
                _sp.complete_execution(
                    protection, ok=False, result={"error": type(e).__name__},
                    post_state=[
                        _sp.capture_path_identity(theme_dir),
                        _sp.capture_path_identity(V3_THEMES_INDEX),
                    ],
                )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)
        return json.dumps({"error": str(e)}), 500


@app.route("/api/v3-themes/<theme_id>/export")
def v3_themes_export_api(theme_id):
    try:
        manifest = _v3_read_theme_manifest(theme_id)
        css = _v3_read_theme_asset(theme_id, "theme.css")
        manifest.setdefault("name", theme_id)
        manifest["oraThemeFormat"] = V3_ORA_THEME_FORMAT
        manifest["oraExportedAt"] = datetime.now(timezone.utc).isoformat()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.writestr("theme.css", css)
        filename = f"{_v3_slugify(manifest.get('name') or theme_id)}.ora-theme.zip"
        return Response(
            buf.getvalue(),
            mimetype="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FileNotFoundError:
        return json.dumps({"error": "Theme not found"}), 404
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/v3-themes/community-directory")
def v3_themes_community_api():
    try:
        resp = requests.get(COMMUNITY_DIRECTORY_URL, timeout=15)
        if resp.status_code != 200:
            return json.dumps({"error": f"Directory fetch returned {resp.status_code}"}), 502
        return Response(resp.text, mimetype="application/json")
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/v3-themes/community-stats")
def v3_themes_community_stats_api():
    """Proxy Obsidian's per-theme download stats so the browse view can
    sort by popularity. Returns a JSON dict keyed by theme name."""
    try:
        resp = requests.get("https://releases.obsidian.md/stats/theme", timeout=15)
        if resp.status_code != 200:
            return json.dumps({"error": f"Stats fetch returned {resp.status_code}"}), 502
        return Response(resp.text, mimetype="application/json")
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/v3-themes/install-from-github", methods=["POST"])
def v3_themes_install_from_github_api():
    data = request.get_json(force=True) or {}
    repo = (data.get("repo") or "").strip()
    if not repo:
        return json.dumps({"error": "Missing repo"}), 400
    if "github.com/" in repo:
        path = urlparse(repo).path.strip("/").rstrip(".git")
        repo = path
    if "/" not in repo or repo.count("/") != 1:
        return json.dumps({"error": "Invalid repo. Expected 'user/repo' or full GitHub URL."}), 400
    # `fallback` lets the client (e.g. browse view) supply name/author/modes
    # from the community directory when the repo itself lacks manifest.json.
    fallback = data.get("fallback") or {}
    raw_base = f"https://raw.githubusercontent.com/{repo}/HEAD"
    try:
        # Modern Obsidian themes use theme.css; legacy themes use obsidian.css.
        # Try both before giving up.
        css = None
        for filename in ("theme.css", "obsidian.css"):
            css_resp = requests.get(f"{raw_base}/{filename}", timeout=15)
            if css_resp.status_code == 200:
                css = css_resp.text
                break
        if css is None:
            return json.dumps({"error": f"Neither theme.css nor obsidian.css found in {repo}"}), 404

        manifest_resp = requests.get(f"{raw_base}/manifest.json", timeout=15)
        if manifest_resp.status_code == 200:
            try:
                manifest = manifest_resp.json()
            except ValueError:
                manifest = {}
        else:
            manifest = {}

        # Synthesize a manifest if the repo doesn't ship one — use fallback
        # data first, then the repo's last path segment as a final fallback.
        if not manifest.get("name"):
            manifest["name"] = fallback.get("name") or repo.split("/")[-1]
        if not manifest.get("author") and fallback.get("author"):
            manifest["author"] = fallback["author"]
        if not manifest.get("version"):
            manifest["version"] = "1.0.0"
        if not manifest.get("modes") and fallback.get("modes"):
            manifest["modes"] = fallback["modes"]

        name = manifest["name"]
        theme_id = _v3_slugify(name)
        if theme_id == "default":
            return json.dumps({"error": "Cannot overwrite default theme"}), 400
        css = _v3_convert_obsidian_theme(css, manifest)
        manifest["sourceFormat"] = "obsidian-github"
        manifest["sourceRepo"] = repo
        manifest["oraThemeFormat"] = V3_ORA_THEME_FORMAT
        manifest["oraImportedAt"] = datetime.now(timezone.utc).isoformat()
        result = _v3_install(theme_id, name, manifest, css)
        result["theme_css_url"] = f"/static/themes/{result['id']}/theme.css"
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

# ── bridge API (polling) ──────────────────────────────────────────────────────

@app.route("/api/bridge/<panel_id>", methods=["POST"])
def bridge_update(panel_id):
    panel_id = (panel_id or "").strip()
    if not _valid_live_conversation_id(panel_id):
        return json.dumps({"error": "invalid conversation_id"}), 400
    data = request.get_json(force=True)
    with _conversation_lifecycle_lock(panel_id):
        if _is_conversation_deleted(panel_id):
            return json.dumps({"status": "deleted"}), 410
        existing = _bridge_state.get(panel_id, {})
        merged = {
            "current_topic":  data.get("current_topic", existing.get("current_topic", "")),
            "recent_messages": data.get("recent_messages", existing.get("recent_messages", []))[-5:],
            "active_mode":    data.get("active_mode",  existing.get("active_mode")),
            "active_gear":    data.get("active_gear",  existing.get("active_gear")),
            "pipeline_stage": data.get("pipeline_stage", existing.get("pipeline_stage")),
            "updated_at":     time.time(),
        }
        # Preserve ora-visual blocks on the bridge so the V3 Exhibits surface
        # can pick them up on the next poll.
        if "ora_visual_blocks" in data:
            merged["ora_visual_blocks"] = data.get("ora_visual_blocks") or []
        elif "ora_visual_blocks" in existing:
            merged["ora_visual_blocks"] = existing["ora_visual_blocks"]
        _bridge_state[panel_id] = merged
    return json.dumps({"ok": True})

@app.route("/api/bridge/<panel_id>")
def bridge_get(panel_id):
    state = _bridge_state.get(panel_id, {})
    return json.dumps(state)

# ── vault search ──────────────────────────────────────────────────────────────

@app.route("/api/vault-search")
def vault_search():
    query = request.args.get("q", "").strip()
    n     = min(int(request.args.get("n", 6)), 20)
    if not query:
        return json.dumps({"results": []})
    try:
        import chromadb
        from orchestrator.embedding import get_collection
        config     = load_config()
        chroma_path = config.get("chromadb_path", os.path.expanduser("~/ora/chromadb/"))
        client     = chromadb.PersistentClient(path=chroma_path)
        collection = get_collection(client, "knowledge")
        raw = collection.query(query_texts=[query], n_results=n)
        results = []
        for i, doc in enumerate(raw["documents"][0]):
            meta = (raw["metadatas"] or [[]])[0][i] if raw.get("metadatas") else {}
            dist = (raw["distances"] or [[]])[0][i] if raw.get("distances") else None
            results.append({"content": doc, "metadata": meta, "distance": dist})
        return json.dumps({"results": results})
    except Exception as e:
        return json.dumps({"results": [], "error": str(e)})

# ── pipeline state ────────────────────────────────────────────────────────────

@app.route("/api/pipeline")
def pipeline_get():
    return json.dumps(_pipeline_state)

@app.route("/api/pipeline", methods=["POST"])
def pipeline_update():
    data = request.get_json(force=True)
    _pipeline_state.update(data)
    return json.dumps({"ok": True})

# ── clarification API ────────────────────────────────────────────────────────

def _refresh_clarification_dialogue_context(
    panel_id: str,
    pending: dict,
    target_tag: str,
) -> tuple[list[dict], dict | None]:
    """Rebuild mutable Dialogue context at the resume lifecycle seam.

    The caller holds the conversation lifecycle lock.  Paused Step-1/config
    state remains tied to the original prompt, while history and explicit
    contributors are re-read because either may have changed during the pause.
    """
    history, _history_state = _authoritative_dialogue_history(
        panel_id, pending.get("history"),
    )
    extra_context = dict(pending.get("extra_context") or {})
    extra_context.pop("contributor_bundle", None)
    contributor_bundle = build_contributor_bundle(
        panel_id, target_tag=target_tag,
    )
    if contributor_bundle.get("sources"):
        extra_context["contributor_bundle"] = contributor_bundle
    return history, extra_context or None

@app.route("/api/clarification", methods=["POST"])
def clarification_respond():
    """Resume a paused pipeline with the user's clarification answers.

    Expects JSON: {panel_id: str, answers: str}
    Where answers is the user's free-text clarification response.
    Returns an SSE stream continuing the pipeline from Step 2.
    """
    data = request.get_json(force=True)
    panel_id = data.get("panel_id", "main")
    answers = data.get("answers", "").strip()

    pending = _pending_clarification.pop(panel_id, None)
    if not pending:
        return json.dumps({"error": "No pending clarification for this panel"}), 404

    def generate_unlocked(_resume_tag):
        step1 = pending["step1"]
        config = pending["config"]
        user_input = pending["user_input"]

        # Open a fresh per-resume trace, honouring stealth tag.
        _resume_trace_dir = None
        _resume_trace_ref = None
        history, refreshed_extra_context = (
            _refresh_clarification_dialogue_context(
                panel_id, pending, _resume_tag,
            )
        )
        try:
            from boot import PIPELINE_TRACE_AVAILABLE as _pta_r
            if _pta_r:
                from orchestrator import pipeline_trace as _pt_r
                _resume_trace_dir = _pt_r.start_trace(
                    conversation_id=panel_id,
                    raw_input=f"[clarification-resume] {user_input}",
                    ambiguity_mode="assume",
                    stealth=(_resume_tag == "stealth"),
                    conversation_tag=_resume_tag,
                )
                _resume_trace_ref = _pt_r.trace_ref_for_dir(_resume_trace_dir)
        except Exception as _trace_exc:
            print(f"[server trace] clarification-resume start_trace skipped: {_trace_exc}", flush=True)

        # Trace-manifest state for this resume turn. The paused turn stored
        # its own trace ref when it returned; it becomes this turn's parent
        # (design-gate condition 4).
        turn_state = {"trace_dir": _resume_trace_dir,
                      "kind": "clarification_resume", "status": None,
                      "mode": step1.get("mode"), "gear": None,
                      "parent_ref": pending.get("trace_ref")}

        yield _sse("start", endpoint="resumed", pipeline=True)
        yield _sse("pipeline_stage", stage="step2_context",
                    label="Assembling context with clarification…")

        final_response = [None]
        active_mode = [step1.get("mode")]
        active_gear = [None]

        try:
            for chunk in _run_pipeline_from_step2(step1, config, history, user_input, answers,
                                                  images=pending.get("images"),
                                                  extra_context=refreshed_extra_context,
                                                  trace_dir=_resume_trace_dir,
                                                  conversation_tag=_resume_tag,
                                                  turn_state=turn_state):
                yield chunk
                try:
                    d = json.loads(chunk[6:])
                    if d.get("type") == "response":
                        final_response[0] = d.get("text", "")
                    elif d.get("type") == "pipeline_stage":
                        if d.get("gear"):
                            active_gear[0] = d["gear"]
                except Exception:
                    pass
        except GeneratorExit:
            raise
        except BaseException:
            turn_state["status"] = "error"
            raise
        finally:
            # Q2 (design-gate): the resume path previously never computed a
            # cost summary — same best-effort behavior as _pipeline_stream.
            if _resume_trace_dir:
                try:
                    from boot import compute_cost_summary as _ccs_r
                    _ccs_r(_resume_trace_dir)
                except Exception as _cs_exc:
                    print(f"[cost-summary] clarification-resume computation "
                          f"failed: {_cs_exc}", flush=True)
            try:
                from orchestrator import pipeline_trace as _pt_fin_r
                _pt_fin_r.finalize_manifest(
                    _resume_trace_dir, kind=turn_state["kind"],
                    status_hint=turn_state["status"],
                    mode=turn_state["mode"], gear=turn_state["gear"],
                    parent_trace_ref=turn_state["parent_ref"])
            except Exception as _fin_exc:
                print(f"[server trace] clarification-resume manifest "
                      f"finalize skipped: {_fin_exc}", flush=True)

        if final_response[0] is not None:
            is_new_session = len(history) == 0
            chunk_id = _save_conversation(
                user_input, final_response[0], panel_id, is_new_session,
                _resume_tag, trace_ref=_resume_trace_ref,
            )
            if chunk_id:
                threading.Thread(
                    target=_persist_turn_spatial_state,
                    args=(panel_id, user_input, final_response[0],
                          refreshed_extra_context, _resume_tag),
                    kwargs={"trace_ref": _resume_trace_ref},
                    daemon=True,
                ).start()

            _bridge_state[panel_id] = {
                "current_topic": user_input,
                "recent_messages": (list(history[-4:]) + [
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": final_response[0]},
                ])[-5:],
                "active_mode": active_mode[0],
                "active_gear": active_gear[0],
                "pipeline_stage": "complete",
                "updated_at": time.time(),
            }

        _pipeline_state.update({"stage": None, "label": "", "active": False})
        yield _sse("done")

    def generate():
        with _conversation_lifecycle_lock(panel_id):
            if _is_conversation_deleted(panel_id):
                yield _sse("error", text="Conversation was permanently deleted.")
                return
            resolved_tag = _effective_conversation_tag(
                panel_id, pending.get("conversation_tag") or "",
            )
            with _conversation_turn_context(panel_id, resolved_tag):
                yield from generate_unlocked(resolved_tag)

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/clarification/skip", methods=["POST"])
def clarification_skip():
    """Skip clarification and proceed with Tier 1 behavior."""
    data = request.get_json(force=True)
    panel_id = data.get("panel_id", "main")

    pending = _pending_clarification.pop(panel_id, None)
    if not pending:
        return json.dumps({"error": "No pending clarification for this panel"}), 404

    def generate_unlocked(_skip_tag):
        step1 = pending["step1"]
        config = pending["config"]
        user_input = pending["user_input"]

        # Open a fresh per-skip trace, honouring stealth tag.
        _skip_trace_dir = None
        _skip_trace_ref = None
        history, refreshed_extra_context = (
            _refresh_clarification_dialogue_context(
                panel_id, pending, _skip_tag,
            )
        )
        try:
            from boot import PIPELINE_TRACE_AVAILABLE as _pta_s
            if _pta_s:
                from orchestrator import pipeline_trace as _pt_s
                _skip_trace_dir = _pt_s.start_trace(
                    conversation_id=panel_id,
                    raw_input=f"[clarification-skip] {user_input}",
                    ambiguity_mode="assume",
                    stealth=(_skip_tag == "stealth"),
                    conversation_tag=_skip_tag,
                )
                _skip_trace_ref = _pt_s.trace_ref_for_dir(_skip_trace_dir)
        except Exception as _trace_exc:
            print(f"[server trace] clarification-skip start_trace skipped: {_trace_exc}", flush=True)

        # Trace-manifest state — same lineage semantics as the resume
        # endpoint (a skip is a resume without answers).
        turn_state = {"trace_dir": _skip_trace_dir,
                      "kind": "clarification_resume", "status": None,
                      "mode": step1.get("mode"), "gear": None,
                      "parent_ref": pending.get("trace_ref")}

        yield _sse("start", endpoint="resumed", pipeline=True)
        yield _sse("pipeline_stage", stage="step2_context",
                    label="Assembling context (clarification skipped)…")

        final_response = [None]
        try:
            for chunk in _run_pipeline_from_step2(step1, config, history, user_input,
                                                  images=pending.get("images"),
                                                  extra_context=refreshed_extra_context,
                                                  trace_dir=_skip_trace_dir,
                                                  conversation_tag=_skip_tag,
                                                  turn_state=turn_state):
                yield chunk
                try:
                    d = json.loads(chunk[6:])
                    if d.get("type") == "response":
                        final_response[0] = d.get("text", "")
                except Exception:
                    pass
        except GeneratorExit:
            raise
        except BaseException:
            turn_state["status"] = "error"
            raise
        finally:
            # Q2 (design-gate): best-effort cost summary, as on the
            # resume endpoint and _pipeline_stream.
            if _skip_trace_dir:
                try:
                    from boot import compute_cost_summary as _ccs_s
                    _ccs_s(_skip_trace_dir)
                except Exception as _cs_exc:
                    print(f"[cost-summary] clarification-skip computation "
                          f"failed: {_cs_exc}", flush=True)
            try:
                from orchestrator import pipeline_trace as _pt_fin_s
                _pt_fin_s.finalize_manifest(
                    _skip_trace_dir, kind=turn_state["kind"],
                    status_hint=turn_state["status"],
                    mode=turn_state["mode"], gear=turn_state["gear"],
                    parent_trace_ref=turn_state["parent_ref"])
            except Exception as _fin_exc:
                print(f"[server trace] clarification-skip manifest "
                      f"finalize skipped: {_fin_exc}", flush=True)

        if final_response[0] is not None:
            chunk_id = _save_conversation(
                user_input, final_response[0], panel_id, len(history) == 0,
                _skip_tag, trace_ref=_skip_trace_ref,
            )
            if chunk_id:
                threading.Thread(
                    target=_persist_turn_spatial_state,
                    args=(panel_id, user_input, final_response[0],
                          refreshed_extra_context, _skip_tag),
                    kwargs={"trace_ref": _skip_trace_ref},
                    daemon=True,
                ).start()

        _pipeline_state.update({"stage": None, "label": "", "active": False})
        yield _sse("done")

    def generate():
        with _conversation_lifecycle_lock(panel_id):
            if _is_conversation_deleted(panel_id):
                yield _sse("error", text="Conversation was permanently deleted.")
                return
            resolved_tag = _effective_conversation_tag(
                panel_id, pending.get("conversation_tag") or "",
            )
            with _conversation_turn_context(panel_id, resolved_tag):
                yield from generate_unlocked(resolved_tag)

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/clarification/pending")
def clarification_pending():
    """Check if a panel has pending clarification."""
    panel_id = request.args.get("panel_id", "main")
    pending = _pending_clarification.get(panel_id)
    if pending:
        return json.dumps({
            "pending": True,
            "mode": pending["step1"].get("mode"),
            "tier": pending["step1"].get("triage_tier"),
        })
    return json.dumps({"pending": False})


# ── capability slot dispatch ─────────────────────────────────────────────────
# /api/capability/image_generates — server-side bridge for the `image_generates`
# slot (capabilities.json §3.1). The browser POSTs:
#   { slot: 'image_generates',
#     inputs: { prompt, style?, aspect_ratio?, provider_override? },
#     provider_override? }
# The registry auto-registers local-diffusers (when the diffusers package
# is installed); routes-side, we additionally register the OpenAI provider
# so a machine with an OpenAI key but no local diffusers install still has
# a working path. resolve_provider walks preferred → fallback per
# routing-config.json's slots block.

@app.route("/api/capability/image_generates", methods=["POST"])
def capability_image_generates():
    """Dispatch the `image_generates` capability slot.

    Body JSON:
      slot (must be 'image_generates'),
      inputs { prompt (str), style (str, optional),
               aspect_ratio (str, optional), provider_override (str, optional) },
      provider_override (str, optional, top-level — wins if both set).

    Response:
      200 { image: { data: <b64>, mime_type: 'image/png' },
            provider: <provider_id>, metadata: {...} }
      4xx { error: { code, message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "handler_failed",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    inputs_in = data.get("inputs") or {}
    if not isinstance(inputs_in, dict):
        inputs_in = {}

    prompt = (inputs_in.get("prompt") or "").strip()
    if not prompt:
        return Response(json.dumps({"error": {
            "code": "handler_failed",
            "message": "image_generates requires a non-empty 'prompt'."
        }}), status=400, mimetype="application/json")

    style = inputs_in.get("style") or None
    aspect_ratio = inputs_in.get("aspect_ratio") or "1:1"
    provider_override = (
        data.get("provider_override")
        or inputs_in.get("provider_override")
        or None
    )
    try:
        locks = _active_project_model_locks()
        locked_image_model = (locks or {}).get("image_model")
        if isinstance(locked_image_model, str) and locked_image_model:
            if provider_override not in (None, "", locked_image_model):
                return Response(json.dumps({"error": {
                    "code": "model_profile_image_lock_conflict",
                    "message": (
                        "The active project's Model Profile locks image generation "
                        f"to {locked_image_model!r}."
                    ),
                }}), status=409, mimetype="application/json")
            provider_override = locked_image_model
    except ValueError as exc:
        return Response(json.dumps({"error": {
            "code": "model_profile_binding_invalid",
            "message": str(exc),
        }}), status=409, mimetype="application/json")

    # Load the registry (auto-registers local-diffusers when installed)
    # and additionally register the OpenAI provider so the resolver has
    # both options available. Both registrations are best-effort —
    # missing deps don't break the route; resolve_provider just walks
    # past unregistered providers.
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        registry = _load_registry()
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Capability registry unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    # civitai-hector-lora-v1 (Hector editorial-cartoon LoRA) decommissioned
    # 2026-06-01 with the moral-disgust pivot; butt-face device retired.
    try:
        import openai_images as _oai
        _oai.register(registry)
    except Exception:
        pass
    # §5.8.1 Slot 3 — Gemini 2.5 Flash Image, the moderation-lottery
    # fallback when Slot 2 (gpt-image-1) returns prompt_rejected. The
    # capability registry's invoke() walks the routing-config chain
    # automatically on prompt_rejected / model_unavailable /
    # quota_exceeded, so the Slot-1 → Slot-2 → Slot-3 fall-through is
    # transparent to this route — the InvocationResult records the
    # attempt chain.
    try:
        import gemini_images as _gemini
        _gemini.register(registry)
    except Exception:
        pass
    # OpenRouter-catalog image models (openrouter:<vendor>/<model> ids).
    # Registration is catalog-file-based (no network) and MUST happen on
    # this invoke route, not just on GET /api/capability/providers:
    # resolve_provider_chain silently skips unregistered ids, so without
    # this the shipped default chain (and any openrouter:* pick saved in
    # the Visual pane) collapsed to [local-diffusers] at dispatch time.
    try:
        import openrouter_images as _orimg
        _orimg.register(registry)
    except Exception:
        pass

    inputs = {"prompt": prompt, "aspect_ratio": aspect_ratio}
    if style:
        inputs["style"] = style

    try:
        result = registry.invoke(
            "image_generates",
            inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "model_unavailable")
        # No provider registered = local-first install with no API
        # keys configured AND no diffusers install — surface a helpful
        # fix-path message rather than the raw "no_provider_registered".
        if code == "no_provider_registered":
            message = (
                "No image generator is available. Install local image "
                "generation (pip install diffusers transformers accelerate "
                "safetensors torch) OR configure an API key in Settings → "
                "External APIs."
            )
        else:
            message = str(exc)
        # When the registry walked the fallback chain and every provider
        # failed, ``CapabilityError.attempts`` carries the per-provider
        # error codes. Surface it on the error response so the UI can
        # show "tried Slot 1 → refused (content_policy) → tried Slot 2 →
        # refused (model_unavailable) → no providers left."
        attempts = getattr(exc, "attempts", []) or []
        return Response(json.dumps({"error": {
            "code": code,
            "message": message,
            "attempts": attempts,
        }}), status=502 if code in ("model_unavailable", "handler_failed", "no_provider_registered") else 400,
            mimetype="application/json")

    output = getattr(result, "output", result)
    provider_id = getattr(result, "provider_id", "unknown")
    if not isinstance(output, (bytes, bytearray)):
        return Response(json.dumps({"error": {
            "code": "handler_failed",
            "message": "Handler did not return image bytes."
        }}), status=502, mimetype="application/json")

    # Surface the fallback chain so the UI can show "tried gpt-image-1
    # (refused for content_policy) → used gemini-2.5-flash-image".
    # Empty / single-entry attempts means no fallback happened.
    attempts = getattr(result, "attempts", []) or []

    import base64
    return Response(json.dumps({
        "image": {
            "data": base64.b64encode(bytes(output)).decode("ascii"),
            "mime_type": "image/png",
        },
        "provider": provider_id,
        "attempts": attempts,
        "metadata": {
            "aspect_ratio": aspect_ratio,
            "style": style,
        },
    }), status=200, mimetype="application/json")


# ── capability slot dispatch (WP-7.3.3b) ─────────────────────────────────────
# /api/capability/image_edits — server-side bridge between the WP-7.3.1 UI's
# `capability-dispatch` events and the WP-7.3.2a `dispatch_image_edits`
# handler. The browser does the mask normalization (rasterize rect/polygon,
# invert brush) so the request body always carries:
#   { prompt, image_data_url, mask_data_url, parent_image_id?,
#     strength?, provider_override? }
# and we hand the raw bytes to the registered provider via the registry.

def _decode_data_url(data_url, field_name):
    """Return raw bytes from a 'data:<mime>;base64,...' URL."""
    if not isinstance(data_url, str) or not data_url:
        raise ValueError(f"{field_name} missing or not a string")
    if not data_url.startswith("data:"):
        raise ValueError(f"{field_name} not a data URL")
    if ";base64," not in data_url:
        raise ValueError(f"{field_name} not base64-encoded")
    import base64
    _header, _, b64 = data_url.partition(";base64,")
    try:
        return base64.b64decode(b64)
    except Exception as exc:
        raise ValueError(f"{field_name} base64 decode failed: {exc}")


@app.route("/api/capability/image_edits", methods=["POST"])
def capability_image_edits():
    """Dispatch the `image_edits` capability slot.

    Body JSON:
      prompt (str, required — non-empty), image_data_url (str),
      mask_data_url (str), parent_image_id (str | optional),
      strength (float | optional), provider_override (str | optional).

    Response:
      200 { image_b64: str, provider_id: str, mode: 'inpaint' }
      4xx { error: { code, message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    # `prompt` is a required input (capabilities.json §3.2), so a blank one
    # is rejected rather than backfilled. A blank prompt is not a thing to
    # guess at: inventing one edits the user's image with words they did
    # not write, and the provider rejects it anyway (see
    # local_diffusers.dispatch_image_edits, which raises the same code).
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": (
                "image_edits requires a non-empty prompt. Describe what "
                "should appear in the masked region and try again."
            )
        }}), status=400, mimetype="application/json")

    try:
        image_bytes = _decode_data_url(data.get("image_data_url"), "image_data_url")
        mask_bytes = _decode_data_url(data.get("mask_data_url"), "mask_data_url")
    except ValueError as exc:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": str(exc)
        }}), status=400, mimetype="application/json")

    # Mock path: when no API key is configured, return a deterministic
    # stub so the §13.3 acceptance criterion ("verify edited image lands")
    # still exercises end-to-end without hitting OpenAI. Detected by the
    # presence of an explicit `mock=true` flag OR by the absence of any
    # OpenAI key on the server. Returning the mask itself as a 1024×1024
    # PNG (re-encoded via PIL) gives the canvas something visibly
    # different from the source.
    mock_requested = bool(data.get("mock"))
    has_openai_key = bool(
        os.environ.get("OPENAI_API_KEY")
        or _try_keychain_openai_key()
    )
    if mock_requested or not has_openai_key:
        try:
            mock_b64 = _build_mock_image_edits_result(image_bytes, mask_bytes)
        except Exception as exc:
            return Response(json.dumps({"error": {
                "code": "model_unavailable",
                "message": f"Mock fulfillment failed: {exc}"
            }}), status=500, mimetype="application/json")
        return Response(json.dumps({
            "image_b64": mock_b64,
            "provider_id": "mock-image-edits",
            "mode": "inpaint",
            "mocked": True
        }), status=200, mimetype="application/json")

    # Real path: route through the capability registry.
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from openai_images import register_with_default_registry as _reg_oai
        registry = _reg_oai()
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"OpenAI provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    inputs = {
        "image": image_bytes,
        "mask": mask_bytes,
        "prompt": prompt,
    }
    if data.get("strength") is not None:
        try:
            inputs["strength"] = float(data["strength"])
        except (TypeError, ValueError):
            pass

    provider_override = data.get("provider_override") or None

    try:
        result = registry.invoke(
            "image_edits",
            inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        # CapabilityError carries .code; keep it explicit.
        code = getattr(exc, "code", "model_unavailable")
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=502 if code == "model_unavailable" else 400,
            mimetype="application/json")

    # invoke() returns either bytes (handler return) wrapped in
    # InvocationResult, or InvocationResult directly. Handle both.
    output = getattr(result, "output", result)
    provider_id = getattr(result, "provider_id", "unknown")
    if not isinstance(output, (bytes, bytearray)):
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Handler did not return image bytes."
        }}), status=502, mimetype="application/json")

    import base64
    return Response(json.dumps({
        "image_b64": base64.b64encode(bytes(output)).decode("ascii"),
        "provider_id": provider_id,
        "mode": "inpaint"
    }), status=200, mimetype="application/json")


def _try_keychain_openai_key():
    """Return the OpenAI key from the keychain, or '' on failure.

    Mirrors openai_images._get_api_key() but without raising. Used to
    decide whether to use the mock fulfillment path.
    """
    try:
        import keyring
        return keyring.get_password("ora", "openai-api-key") or ""
    except Exception:
        return ""


def _build_mock_image_edits_result(image_bytes, mask_bytes):
    """Build a deterministic 'edited' PNG for the mock path.

    Strategy: composite the source image with the masked area tinted
    blue. This makes the test prompt "make it blue" land on something
    visibly different, which is the §13.3 verification.
    """
    from PIL import Image
    import io
    import base64

    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    mask = Image.open(io.BytesIO(mask_bytes)).convert("RGBA")
    if mask.size != src.size:
        mask = mask.resize(src.size, Image.NEAREST)

    # OpenAI mask convention: transparent = edit area. For the mock we
    # invert and use the transparent pixels as a paint stencil.
    edit_overlay = Image.new("RGBA", src.size, (40, 90, 220, 255))  # blue
    # Build an alpha mask from the (inverted) source mask alpha — pixels
    # where mask alpha == 0 should be edited.
    mask_alpha = mask.split()[3]
    inverted = mask_alpha.point(lambda a: 255 if a == 0 else 0)
    composite = src.copy()
    composite.paste(edit_overlay, (0, 0), inverted)

    out = io.BytesIO()
    composite.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


# ── capability slot dispatch (WP-7.3.3c) ─────────────────────────────────────
# /api/capability/image_outpaints — server-side bridge between the WP-7.3.1 UI's
# `capability-dispatch` events and the WP-7.3.2b `dispatch_image_outpaints`
# handler (Stability provider). The browser POSTs:
#   { prompt, image_data_url, directions: [...], parent_image_id?,
#     aspect_ratio?, provider_override? }
# and we hand the raw bytes to the registered Stability provider via the
# capability registry, OR (mock path) tile the source onto a larger canvas
# so the §13.3 acceptance criterion ("verify image grows") still exercises
# end-to-end without an API key.

_VALID_OUTPAINT_DIRECTIONS = {"top", "bottom", "left", "right"}


@app.route("/api/capability/image_outpaints", methods=["POST"])
def capability_image_outpaints():
    """Dispatch the `image_outpaints` capability slot.

    Body JSON:
      prompt (str), image_data_url (str), directions (list[str]),
      parent_image_id (str | optional), aspect_ratio (str | optional),
      provider_override (str | optional), mock (bool | optional).

    Response:
      200 { image_b64: str, provider_id: str, mode: 'outpaint',
            extended_dimensions: {width, height} }
      4xx { error: { code, message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "handler_failed",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return Response(json.dumps({"error": {
            "code": "handler_failed",
            "message": "image_outpaints requires a non-empty 'prompt'."
        }}), status=400, mimetype="application/json")

    raw_directions = data.get("directions") or []
    if not isinstance(raw_directions, list):
        raw_directions = []
    directions = []
    for d in raw_directions:
        if isinstance(d, str) and d in _VALID_OUTPAINT_DIRECTIONS and d not in directions:
            directions.append(d)
    if not directions:
        return Response(json.dumps({"error": {
            "code": "direction_invalid",
            "message": "image_outpaints requires at least one of: "
                       "top / bottom / left / right."
        }}), status=400, mimetype="application/json")

    try:
        image_bytes = _decode_data_url(data.get("image_data_url"), "image_data_url")
    except ValueError as exc:
        return Response(json.dumps({"error": {
            "code": "handler_failed",
            "message": str(exc)
        }}), status=400, mimetype="application/json")

    aspect_ratio = data.get("aspect_ratio") or None

    # Mock path: when mock is explicitly requested OR no Stability key is
    # configured. Tiles the source onto a larger canvas (no AI needed) —
    # canvas image grows, satisfying the §13.3 test criterion.
    mock_requested = bool(data.get("mock"))
    has_stability_key = bool(
        os.environ.get("STABILITY_API_KEY")
        or _try_keychain_stability_key()
    )
    if mock_requested or not has_stability_key:
        try:
            mock_b64, new_w, new_h = _build_mock_image_outpaints_result(
                image_bytes, directions
            )
        except Exception as exc:
            return Response(json.dumps({"error": {
                "code": "handler_failed",
                "message": f"Mock fulfillment failed: {exc}"
            }}), status=500, mimetype="application/json")
        return Response(json.dumps({
            "image_b64": mock_b64,
            "provider_id": "mock-image-outpaints",
            "mode": "outpaint",
            "extended_dimensions": {"width": new_w, "height": new_h},
            "directions": directions,
            "mocked": True
        }), status=200, mimetype="application/json")

    # Real path: route through the capability registry. Stability is the
    # primary provider for image_outpaints (WP-7.3.2b).
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        import stability as _stability
        registry = _load_registry()
        _stability.register(registry)
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Stability provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    inputs = {
        "image": image_bytes,
        "directions": directions,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    }
    provider_override = data.get("provider_override") or None

    try:
        result = registry.invoke(
            "image_outpaints",
            inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "handler_failed")
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=502 if code in ("model_unavailable", "handler_failed") else 400,
            mimetype="application/json")

    output = getattr(result, "output", result)
    provider_id = getattr(result, "provider_id", "stability")
    if not isinstance(output, (bytes, bytearray)):
        return Response(json.dumps({"error": {
            "code": "handler_failed",
            "message": "Handler did not return image bytes."
        }}), status=502, mimetype="application/json")

    import base64
    return Response(json.dumps({
        "image_b64": base64.b64encode(bytes(output)).decode("ascii"),
        "provider_id": provider_id,
        "mode": "outpaint",
        "directions": directions
    }), status=200, mimetype="application/json")


def _try_keychain_stability_key():
    """Return the Stability key from the keychain, or '' on failure.

    Mirrors stability._get_api_key() but never raises. Used to decide
    whether the mock fulfillment path applies.
    """
    try:
        import keyring
        return keyring.get_password("ora", "stability-api-key") or ""
    except Exception:
        return ""


def _build_mock_image_outpaints_result(image_bytes, directions):
    """Build a deterministic 'outpainted' PNG for the mock path.

    Strategy: tile the source onto a larger canvas. For each requested
    direction we add `pad` pixels (default 256) to that side. The
    original image lands at the appropriate offset; the new region is
    filled with a mirrored / tiled copy of the source so the test sees
    something visibly different from a solid background.

    Returns (base64_str, new_width, new_height).
    """
    from PIL import Image, ImageOps
    import io
    import base64

    pad = 256  # pixels added per direction
    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = src.size

    pad_top    = pad if "top" in directions else 0
    pad_bottom = pad if "bottom" in directions else 0
    pad_left   = pad if "left" in directions else 0
    pad_right  = pad if "right" in directions else 0

    new_w = w + pad_left + pad_right
    new_h = h + pad_top + pad_bottom

    # Start with an opaque grey backdrop so unfilled regions are visible.
    canvas = Image.new("RGBA", (new_w, new_h), (200, 200, 200, 255))

    # Fill extension regions with a flipped copy of the source as a
    # rough "outpaint" — visually distinct from an empty pad. This
    # keeps the mock visibly distinguishable from a no-op.
    if pad_top:
        flipped = ImageOps.flip(src).resize((w, pad_top))
        canvas.paste(flipped, (pad_left, 0))
    if pad_bottom:
        flipped = ImageOps.flip(src).resize((w, pad_bottom))
        canvas.paste(flipped, (pad_left, pad_top + h))
    if pad_left:
        mirrored = ImageOps.mirror(src).resize((pad_left, h))
        canvas.paste(mirrored, (0, pad_top))
    if pad_right:
        mirrored = ImageOps.mirror(src).resize((pad_right, h))
        canvas.paste(mirrored, (pad_left + w, pad_top))

    # Paste source at its offset position.
    canvas.paste(src, (pad_left, pad_top))

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii"), new_w, new_h


# ── capability slot dispatch (WP-7.3.3d) ─────────────────────────────────────
# /api/capability/image_upscales — server-side bridge between the WP-7.3.3d UI's
# `capability-dispatch` events and the WP-7.3.2b `dispatch_image_upscales`
# handler (Stability conservative-tier upscaler). The browser POSTs:
#   { image_data_url, scale_factor?, source_image_id?, provider_override?,
#     mock? }
# and we either route to the registered Stability provider via the capability
# registry or (mock path) call PIL's bicubic resize so the §13.3 acceptance
# criterion ("upscale a 256×256 image to 512×512; verify size doubled") still
# exercises end-to-end without an API key.

@app.route("/api/capability/image_upscales", methods=["POST"])
def capability_image_upscales():
    """Dispatch the `image_upscales` capability slot.

    Body JSON:
      image_data_url (str), scale_factor (float | optional, default 2.0),
      source_image_id (str | optional), provider_override (str | optional),
      mock (bool | optional).

    Response:
      200 { image_b64: str, provider_id: str, mode: 'upscale',
            width: int, height: int, scale_factor: float }
      4xx { error: { code, message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    try:
        scale_factor = float(data.get("scale_factor") or 2.0)
    except (TypeError, ValueError):
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": "scale_factor must be a number."
        }}), status=400, mimetype="application/json")
    if scale_factor <= 1.0:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": "scale_factor must be > 1.0."
        }}), status=400, mimetype="application/json")

    try:
        image_bytes = _decode_data_url(data.get("image_data_url"), "image_data_url")
    except ValueError as exc:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": str(exc)
        }}), status=400, mimetype="application/json")

    # Mock path: when no Stability key is configured OR `mock=true` is
    # explicit, run the §13.3 mock fulfillment (PIL bicubic resize). The
    # mock returns a deterministic, dimensionally-correct PNG so the
    # client wiring + canvas-state plumbing can be exercised without an
    # API key.
    mock_requested = bool(data.get("mock"))
    has_stability_key = bool(
        os.environ.get("STABILITY_API_KEY")
        or _try_keychain_stability_key()
    )
    if mock_requested or not has_stability_key:
        try:
            mock_b64, new_w, new_h = _build_mock_image_upscales_result(
                image_bytes, scale_factor
            )
        except Exception as exc:
            return Response(json.dumps({"error": {
                "code": "model_unavailable",
                "message": f"Mock fulfillment failed: {exc}"
            }}), status=500, mimetype="application/json")
        return Response(json.dumps({
            "image_b64":    mock_b64,
            "provider_id":  "mock-image-upscales",
            "mode":         "upscale",
            "width":        new_w,
            "height":       new_h,
            "scale_factor": scale_factor,
            "mocked":       True,
        }), status=200, mimetype="application/json")

    # Real path: route through the capability registry. Stability is the
    # default provider for image_upscales (WP-7.3.2b register()).
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from stability import register as _reg_stability
        from capability_registry import default_registry
        registry = default_registry()
        _reg_stability(registry)
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Stability provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    inputs = {
        "image":        image_bytes,
        "scale_factor": scale_factor,
    }
    provider_override = data.get("provider_override") or None

    try:
        result = registry.invoke(
            "image_upscales",
            inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "model_unavailable")
        # Map slot common_errors codes to HTTP status: 4xx for input
        # problems (image_too_small / image_too_large), 5xx for backend
        # availability failures.
        status = 502 if code == "model_unavailable" else 400
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=status, mimetype="application/json")

    output = getattr(result, "output", result)
    provider_id = getattr(result, "provider_id", "stability")
    if not isinstance(output, (bytes, bytearray)):
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Handler did not return image bytes."
        }}), status=502, mimetype="application/json")

    # Best-effort dimension probe so the response can carry width/height
    # alongside the bytes. PIL is already a hard dependency of the mock
    # path; in the real path we use it purely for metadata.
    try:
        from PIL import Image
        import io as _io
        with Image.open(_io.BytesIO(bytes(output))) as _img:
            new_w, new_h = _img.size
    except Exception:
        new_w = new_h = 0

    import base64
    return Response(json.dumps({
        "image_b64":    base64.b64encode(bytes(output)).decode("ascii"),
        "provider_id":  provider_id,
        "mode":         "upscale",
        "width":        new_w,
        "height":       new_h,
        "scale_factor": scale_factor,
    }), status=200, mimetype="application/json")


def _build_mock_image_upscales_result(image_bytes, scale_factor):
    """Build a deterministic upscaled PNG for the mock path.

    Strategy: PIL bicubic resize to (orig_w * scale_factor,
    orig_h * scale_factor). This satisfies the §13.3 acceptance
    criterion verbatim ("upscale a 256×256 image to 512×512; verify
    size doubled") while remaining provider-agnostic.

    Returns (base64_str, new_width, new_height).
    """
    from PIL import Image
    import io
    import base64

    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = src.size
    new_w = max(1, int(round(w * float(scale_factor))))
    new_h = max(1, int(round(h * float(scale_factor))))
    upscaled = src.resize((new_w, new_h), Image.BICUBIC)

    out = io.BytesIO()
    upscaled.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii"), new_w, new_h


# ── /api/capability/image_styles (WP-7.3.3e) ─────────────────────────────────
# Server-side bridge between the WP-7.3.1 UI's `capability-dispatch` events
# and the WP-7.3.2c `dispatch_image_styles` handler in
# orchestrator/integrations/replicate.py. Body:
#   { source_image_data_url, style_reference_data_url,
#     strength?, provider_override?, mock? }
# Mock path: PIL Image.blend() of the two inputs at `strength` factor, so
# the §13.3 acceptance criterion ("apply a known style to a known image;
# verify output looks blended") runs end-to-end without a Replicate token.

@app.route("/api/capability/image_styles", methods=["POST"])
def capability_image_styles():
    """Dispatch the `image_styles` capability slot (Contracts §3.5).

    Body JSON:
      source_image_data_url (str), style_reference_data_url (str),
      strength (float 0-1, optional, default 0.75),
      provider_override (str, optional), mock (bool, optional).

    Response:
      200 { image_b64: str, provider_id: str, mode: 'styles', mocked? }
      4xx { error: { code, message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    try:
        source_bytes = _decode_data_url(
            data.get("source_image_data_url"), "source_image_data_url"
        )
        style_bytes = _decode_data_url(
            data.get("style_reference_data_url"), "style_reference_data_url"
        )
    except ValueError as exc:
        return Response(json.dumps({"error": {
            "code": "references_incompatible",
            "message": str(exc)
        }}), status=400, mimetype="application/json")

    # Strength: default 0.75, clamp to [0, 1].
    raw_strength = data.get("strength", 0.75)
    try:
        strength = float(raw_strength)
    except (TypeError, ValueError):
        strength = 0.75
    if strength < 0.0:
        strength = 0.0
    elif strength > 1.0:
        strength = 1.0

    # Mock path: when no Replicate API token is configured, blend the two
    # images with PIL Image.blend at the strength factor. This makes the
    # §13.3 verification ("output looks blended") run without hitting
    # Replicate.
    mock_requested = bool(data.get("mock"))
    has_replicate_token = bool(
        os.environ.get("REPLICATE_API_TOKEN")
        or _try_keychain_replicate_token()
    )
    if mock_requested or not has_replicate_token:
        try:
            mock_b64 = _build_mock_image_styles_result(
                source_bytes, style_bytes, strength
            )
        except Exception as exc:
            return Response(json.dumps({"error": {
                "code": "model_unavailable",
                "message": f"Mock fulfillment failed: {exc}"
            }}), status=500, mimetype="application/json")
        return Response(json.dumps({
            "image_b64": mock_b64,
            "provider_id": "mock-image-styles",
            "mode": "styles",
            "mocked": True,
            "strength": strength,
        }), status=200, mimetype="application/json")

    # Real path: route through the capability registry. Replicate's
    # dispatch_image_styles accepts data URIs directly via
    # `_normalize_image_ref`, so we hand the data URLs straight through.
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        import replicate as _replicate
        registry = _load_registry()
        _replicate.register_replicate_provider(registry)
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Replicate provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    inputs = {
        "source_image":    data.get("source_image_data_url"),
        "style_reference": data.get("style_reference_data_url"),
        "strength":        strength,
    }
    provider_override = data.get("provider_override") or None

    try:
        result = registry.invoke(
            "image_styles",
            inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "model_unavailable")
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=502 if code == "model_unavailable" else 400,
            mimetype="application/json")

    # Replicate's dispatch returns {'image_url': ..., 'image_data_uri': ...}.
    # Normalize to image_b64 for the JS client.
    output = getattr(result, "output", result)
    provider_id = getattr(result, "provider_id", "replicate")

    image_b64 = None
    if isinstance(output, dict):
        if isinstance(output.get("image_data_uri"), str):
            uri = output["image_data_uri"]
            if ";base64," in uri:
                image_b64 = uri.split(";base64,", 1)[1]
        elif isinstance(output.get("image_url"), str):
            # Fetch the URL and base64-encode the bytes.
            try:
                from urllib.request import urlopen
                import base64
                with urlopen(output["image_url"], timeout=30) as resp:
                    image_b64 = base64.b64encode(resp.read()).decode("ascii")
            except Exception as exc:
                return Response(json.dumps({"error": {
                    "code": "model_unavailable",
                    "message": f"Failed to fetch result image: {exc}"
                }}), status=502, mimetype="application/json")
    elif isinstance(output, (bytes, bytearray)):
        import base64
        image_b64 = base64.b64encode(bytes(output)).decode("ascii")

    if not image_b64:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Handler did not return image data."
        }}), status=502, mimetype="application/json")

    return Response(json.dumps({
        "image_b64":   image_b64,
        "provider_id": provider_id,
        "mode":        "styles",
        "strength":    strength,
    }), status=200, mimetype="application/json")


def _try_keychain_replicate_token():
    """Return the Replicate API token from the keychain, or '' on failure."""
    try:
        import keyring
        from orchestrator import provider_registry as _providers
        entry = _providers.by_id("replicate") or {}
        username = entry.get("keyring_username")
        if not username:
            return ""
        return keyring.get_password("ora", username) or ""
    except Exception:
        return ""


def _build_mock_image_styles_result(source_bytes, style_bytes, strength):
    """Build a PIL.Image.blend mock for the §13.3 verification.

    Blends the source image with the style reference at the given
    strength factor (0 = pure source, 1 = pure style). Resizes the style
    image to match the source so blend() succeeds. Returns base64 PNG.
    """
    from PIL import Image
    import io
    import base64

    src = Image.open(io.BytesIO(source_bytes)).convert("RGBA")
    style = Image.open(io.BytesIO(style_bytes)).convert("RGBA")
    if style.size != src.size:
        style = style.resize(src.size, Image.LANCZOS)

    blended = Image.blend(src, style, float(strength))

    out = io.BytesIO()
    blended.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


# ── /api/capability/image_critique (WP-7.3.3h) ───────────────────────────────
# Server-side bridge for the §3.8 `image_critique` slot. The browser POSTs:
#   { image_data_url, rubric?, genre?, depth?, provider_override?, mock? }
# Unlike the image-producing slots, this one does not call an external image
# integration (replicate / openai_images / stability). It routes through Ora's
# analytical pipeline: pick a vision-capable analytical model from the bucket
# system, run a structured-critique prompt, parse the response into
# rubric_scores + prose. When no vision-capable model is available OR `mock`
# is set, return a deterministic canned critique so the §13.3 acceptance
# criterion ("verify critique returns rubric scores + prose") still exercises
# end-to-end without hitting a vision API.

_VALID_CRITIQUE_DEPTHS = ("quick", "standard", "deep")


@app.route("/api/capability/image_critique", methods=["POST"])
def capability_image_critique():
    """Dispatch the `image_critique` capability slot (Contracts §3.8).

    Body JSON:
      image_data_url (str, required), rubric (str, optional),
      genre (str, optional), depth (enum quick/standard/deep, optional),
      provider_override (str, optional), mock (bool, optional).

    Response:
      200 { rubric_scores: {<criterion>: {score, comment}, ...},
            prose: str, provider: str, mocked? }
      4xx { error: { code: 'no_specific_guidance', message } }
      5xx { error: { code: 'model_unavailable', message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "no_specific_guidance",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    try:
        image_bytes = _decode_data_url(data.get("image_data_url"), "image_data_url")
    except ValueError as exc:
        return Response(json.dumps({"error": {
            "code": "no_specific_guidance",
            "message": str(exc)
        }}), status=400, mimetype="application/json")

    rubric = (data.get("rubric") or "").strip()
    genre  = (data.get("genre")  or "").strip()
    depth  = (data.get("depth")  or "standard").strip().lower()
    if depth not in _VALID_CRITIQUE_DEPTHS:
        depth = "standard"

    # §3.8 fix path: with no rubric and no genre, the slot has no guidance
    # to ground the critique against. Surface eagerly without a round-trip.
    if not rubric and not genre:
        return Response(json.dumps({"error": {
            "code": "no_specific_guidance",
            "message": "image_critique needs at least a rubric or a genre."
        }}), status=400, mimetype="application/json")

    # Mock path: when `mock=true` is set OR no vision-capable analytical
    # model is reachable, return a deterministic canned critique. The
    # rubric (if supplied) drives which criteria appear in the output so
    # the §13.3 verification ("rubric scores match the rubric the user
    # asked for") still runs end-to-end.
    mock_requested = bool(data.get("mock"))
    vision_endpoint = None
    if not mock_requested:
        try:
            vision_endpoint = _pick_critique_vision_endpoint()
        except Exception:
            vision_endpoint = None
    if mock_requested or vision_endpoint is None:
        try:
            mock_payload = _build_mock_image_critique_result(
                image_bytes, rubric, genre, depth
            )
        except Exception as exc:
            return Response(json.dumps({"error": {
                "code": "model_unavailable",
                "message": f"Mock fulfillment failed: {exc}"
            }}), status=500, mimetype="application/json")
        mock_payload["mocked"] = True
        return Response(json.dumps(mock_payload),
                        status=200, mimetype="application/json")

    # Real path: build a structured-critique prompt, hand the image bytes
    # to the vision-capable model via boot.call_model, parse the response.
    try:
        system_prompt, user_prompt = _build_critique_prompts(rubric, genre, depth)
        # call_model expects images as [{name, mime, base64}].
        import base64
        b64 = base64.b64encode(image_bytes).decode("ascii")
        # We don't probe the bytes for actual mime; PNG is the safe default
        # and most vision APIs sniff their own format.
        images = [{
            "name": "image_critique_input.png",
            "mime": "image/png",
            "base64": b64,
        }]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        provider_override = data.get("provider_override") or None
        endpoint = vision_endpoint
        if provider_override:
            # If the caller named a specific endpoint, prefer it as long
            # as it claims vision capability; else fall back to the picked
            # one above so we never silently drop the request.
            override_ep = _find_endpoint_by_id(provider_override)
            if override_ep and vision_capable_for_endpoint(override_ep):
                endpoint = override_ep
        raw = call_model(messages, endpoint, images=images)
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Critique pipeline failed: {exc}"
        }}), status=502, mimetype="application/json")

    parsed = _parse_critique_response(raw, rubric)
    if not parsed["rubric_scores"] and not parsed["prose"]:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Vision model returned no parseable critique."
        }}), status=502, mimetype="application/json")

    parsed["provider"] = endpoint.get("display_name") or endpoint.get("id") or "ora-pipeline"
    parsed["depth"]    = depth
    return Response(json.dumps(parsed), status=200, mimetype="application/json")


def _pick_critique_vision_endpoint():
    """Locate a vision-capable analytical endpoint.

    Prefer the explicit ``slots.image_critique`` chain. If that slot has not
    been configured yet, reuse ``slots.vision_input`` as the nearest
    vision-language fallback, then walk the old bucket order as a final
    compatibility path. Returns None if none reachable so the caller can fall
    back to the mock path.
    """
    try:
        config = load_config()
    except Exception:
        return None
    endpoints = config.get("endpoints", []) or []
    by_id = {ep.get("id"): ep for ep in endpoints if ep.get("id")}

    for slot_name in ("image_critique", "vision_input"):
        for ep_id in _chat_slot_chain(config, slot_name):
            ep = _lookup_endpoint_variant(by_id, ep_id)
            if _endpoint_ready_for_vision(ep):
                return ep

    # First pass: walk preferred buckets if defined.
    buckets = config.get("buckets", {}) or {}
    bucket_order = ["local-premium", "local-mid", "commercial", "local-fast"]
    for bname in bucket_order:
        for ep_id in buckets.get(bname, []) or []:
            ep = _lookup_endpoint_variant(by_id, ep_id)
            if _endpoint_ready_for_vision(ep):
                return ep
    # Second pass: scan flat endpoint list for any vision-capable active.
    for ep in endpoints:
        if _endpoint_ready_for_vision(ep):
            return ep
    return None


def _chat_slot_chain(config, slot_name):
    slot = (config.get("slots") or {}).get(slot_name) or {}
    chain = []
    if isinstance(slot, dict):
        preferred = slot.get("preferred")
        if isinstance(preferred, str) and preferred.strip():
            chain.append(preferred.strip())
        for item in slot.get("fallback") or []:
            if isinstance(item, str) and item.strip():
                chain.append(item.strip())
    return chain


def _lookup_endpoint_variant(by_id, endpoint_id):
    if not endpoint_id:
        return None
    candidates = [endpoint_id]
    if endpoint_id.startswith("openrouter:"):
        candidates.append(endpoint_id.split(":", 1)[1])
    else:
        candidates.append("openrouter:" + endpoint_id)
    for cid in candidates:
        ep = by_id.get(cid)
        if ep:
            return ep
    return None


def _endpoint_ready_for_vision(ep):
    return bool(
        ep
        and ep.get("enabled", False)
        and ep.get("status") in ("active", None)
        and vision_capable_for_endpoint(ep)
    )


def _find_endpoint_by_id(endpoint_id):
    try:
        config = load_config()
    except Exception:
        return None
    by_id = {ep.get("id"): ep for ep in config.get("endpoints", []) or [] if ep.get("id")}
    return _lookup_endpoint_variant(by_id, endpoint_id)


def _build_critique_prompts(rubric, genre, depth):
    """Compose system + user prompts for the structured-critique call.

    Returns (system_prompt, user_prompt). The prompts ask the model to
    return a JSON block followed by a prose section, both fenced so the
    parser can split them deterministically. The parser tolerates models
    that omit fences or wrap the JSON differently.
    """
    criteria_hint = rubric if rubric else "(infer from genre)"
    genre_hint = genre if genre else "(unspecified)"
    depth_hint = {
        "quick":    "Keep the critique brief — one or two sentences per criterion, prose under 80 words.",
        "standard": "Aim for a balanced critique — a sentence or two per criterion, prose 80–200 words.",
        "deep":     "Be thorough — three or more sentences per criterion, prose 200–400 words.",
    }.get(depth, "Aim for a balanced critique.")

    system_prompt = (
        "You are a diagram and data-visualization reviewer. Given a rendered "
        "visual artifact, a rubric, and an optional genre, judge whether the "
        "image is readable, faithful to the requested visual purpose, and free "
        "of obvious rendering failures. Return per-criterion numeric scores "
        "(0-10), a short comment per criterion, and a concise prose explanation. "
        "You always return your answer in two fenced blocks: a ```json``` block "
        "with the rubric_scores object, and a ```prose``` block with the "
        "discussion."
    )

    user_prompt = (
        f"Review the attached rendered visual.\n"
        f"\n"
        f"Rubric criteria (comma-separated): {criteria_hint}\n"
        f"Genre: {genre_hint}\n"
        f"Depth: {depth} — {depth_hint}\n"
        f"\n"
        f"Return your answer in this exact form:\n"
        f"\n"
        f"```json\n"
        f'{{"<criterion>": {{"score": <int 0-10>, "comment": "<short>"}}, ...}}\n'
        f"```\n"
        f"\n"
        f"```prose\n"
        f"<discussion of the work as a whole>\n"
        f"```\n"
    )
    return system_prompt, user_prompt


def _parse_critique_response(raw, rubric):
    """Parse the model's response into {rubric_scores, prose}.

    Tolerant: looks for a ```json``` block first, then ```prose```; if
    fences are missing, falls back to the first {...} balanced JSON span
    and treats whatever text precedes/follows it as prose.
    """
    if not isinstance(raw, str):
        raw = "" if raw is None else str(raw)

    rubric_scores = {}
    prose = ""

    # Try fenced blocks first.
    import re
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    prose_match = re.search(r"```prose\s*(.*?)\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    if json_match:
        try:
            obj = json.loads(json_match.group(1))
            if isinstance(obj, dict):
                rubric_scores = _coerce_rubric_scores(obj)
        except Exception:
            rubric_scores = {}
    if prose_match:
        prose = prose_match.group(1).strip()

    # Fallback: try to find a balanced {...} block anywhere if we missed
    # the JSON above. This handles models that drop fences.
    if not rubric_scores:
        brace_match = re.search(r"(\{(?:[^{}]|\{[^{}]*\})*\})", raw, flags=re.DOTALL)
        if brace_match:
            try:
                obj = json.loads(brace_match.group(1))
                if isinstance(obj, dict):
                    rubric_scores = _coerce_rubric_scores(obj)
            except Exception:
                pass
    if not prose:
        # Strip any fenced blocks from raw and use what's left as prose.
        scrubbed = re.sub(r"```[a-zA-Z0-9_-]*\s*.*?\s*```", "", raw, flags=re.DOTALL)
        prose = scrubbed.strip()

    return {"rubric_scores": rubric_scores, "prose": prose}


def _coerce_rubric_scores(obj):
    """Normalise an arbitrary dict into the {criterion: {score, comment}} shape."""
    out = {}
    for key, value in (obj or {}).items():
        criterion = str(key).strip()
        if not criterion:
            continue
        if isinstance(value, dict):
            score = value.get("score", value.get("rating"))
            comment = value.get("comment", value.get("note", value.get("reason", "")))
            entry = {}
            if score is not None:
                try:
                    entry["score"] = int(score) if float(score).is_integer() else float(score)
                except (TypeError, ValueError):
                    entry["score"] = str(score)
            if isinstance(comment, str):
                entry["comment"] = comment
            else:
                entry["comment"] = ""
            out[criterion] = entry
        elif isinstance(value, (int, float)):
            out[criterion] = {"score": value, "comment": ""}
        elif isinstance(value, str):
            out[criterion] = {"score": "", "comment": value}
    return out


def _build_mock_image_critique_result(image_bytes, rubric, genre, depth):
    """Build a deterministic canned critique for the §13.3 verification.

    Strategy: derive criteria from the rubric (split on commas / newlines).
    If no rubric was supplied (genre-only path), use a default
    composition/color/technique trio. Per-criterion scores are derived
    deterministically from the image bytes' length so re-runs are stable
    but different images get different score floors. Prose mentions the
    rubric and genre verbatim so the §13.3 test can verify echo-through.
    """
    if rubric:
        # Split on comma OR newline OR semicolon; trim and dedupe.
        import re
        parts = [p.strip() for p in re.split(r"[,;\n]+", rubric) if p.strip()]
        if not parts:
            parts = ["composition", "color", "technique"]
    else:
        parts = ["composition", "color", "technique"]

    base = (len(image_bytes) % 6) + 5  # 5..10
    rubric_scores = {}
    for idx, criterion in enumerate(parts):
        score = max(1, min(10, base - (idx % 4)))
        rubric_scores[criterion] = {
            "score":   score,
            "comment": f"Mock observation about {criterion}.",
        }

    genre_phrase = f" within the {genre} tradition" if genre else ""
    depth_phrase = {
        "quick":    "A brief impression",
        "standard": "A balanced reading",
        "deep":     "A thorough exegesis",
    }.get(depth, "A balanced reading")

    prose = (
        f"{depth_phrase} of the work{genre_phrase}. "
        f"The piece is evaluated against {len(parts)} criterion(a): "
        f"{', '.join(parts)}. "
        f"This is a mock critique generated without a vision model; install "
        f"a vision-capable endpoint to receive a real assessment."
    )
    return {
        "rubric_scores": rubric_scores,
        "prose":         prose,
        "provider":      "mock-image-critique",
    }


# ── /api/capability/image_varies (WP-7.3.3f) ─────────────────────────────────
# Server-side bridge between the WP-7.3.1 UI's `capability-dispatch` events
# and the WP-7.3.2c `dispatch_image_varies` handler in
# orchestrator/integrations/replicate.py. The browser POSTs:
#   { slot, inputs: { source_image, count?, variation_strength?,
#                     source_image_data_url? }, provider_override? }
# Per Contracts §3.6: required `source_image`; optional `count` (default 4),
# `variation_strength` (default 0.5). Returns an `images` list per JS
# `_extractImages`. Sync.
#
# Routing per the WP-7.3.2 series: DALL-E 2 variations would be the
# OpenAI-side primary if openai_images registered an `image_varies`
# dispatcher; today only image_generates and image_edits are wired there,
# so Replicate's `lucataco/sdxl-img2img` is the lone real provider.
# When no Replicate token is configured (or `mock=true`), the mock path
# tints the source four ways so the §13.3 verification ("verify variations
# look like sibling images of source") runs end-to-end without a key.

@app.route("/api/capability/image_varies", methods=["POST"])
def capability_image_varies():
    """Dispatch the `image_varies` capability slot (Contracts §3.6).

    Body JSON:
      slot: 'image_varies' (ignored — endpoint identifies slot),
      inputs: { source_image (str id, required),
                count (int 1-8, optional, default 4),
                variation_strength (float 0-1, optional, default 0.5),
                source_image_data_url (data URL, optional) },
      provider_override (str, optional), mock (bool, optional).

    Response:
      200 { images: [{ data: <base64>, mime_type: <str> }, ...],
            provider: str, mocked? }
      4xx { error: { code: 'source_ambiguous'|..., message } }
      5xx { error: { code: 'model_unavailable', message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "source_ambiguous",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}

    source_id = inputs.get("source_image")
    if not isinstance(source_id, str) or not source_id.strip():
        return Response(json.dumps({"error": {
            "code": "source_ambiguous",
            "message": "image_varies requires a non-empty 'source_image'."
        }}), status=400, mimetype="application/json")

    # Count: clamp [1, 8], default 4.
    raw_count = inputs.get("count", 4)
    try:
        count = int(raw_count)
    except (TypeError, ValueError):
        count = 4
    count = max(1, min(8, count))

    # Variation strength: clamp [0, 1], default 0.5.
    raw_strength = inputs.get("variation_strength", 0.5)
    try:
        variation_strength = float(raw_strength)
    except (TypeError, ValueError):
        variation_strength = 0.5
    if variation_strength < 0.0:
        variation_strength = 0.0
    elif variation_strength > 1.0:
        variation_strength = 1.0

    # Optional inline source bytes (lets the mock path actually tint).
    source_bytes = None
    src_data_url = inputs.get("source_image_data_url")
    if isinstance(src_data_url, str) and src_data_url.startswith("data:"):
        try:
            source_bytes = _decode_data_url(src_data_url, "source_image_data_url")
        except ValueError:
            source_bytes = None

    # Mock path: explicit mock flag OR no Replicate token configured.
    mock_requested = bool(data.get("mock") or inputs.get("mock"))
    has_replicate_token = bool(
        os.environ.get("REPLICATE_API_TOKEN")
        or _try_keychain_replicate_token()
    )
    if mock_requested or not has_replicate_token:
        try:
            mock_images = _build_mock_image_varies_result(
                source_bytes, count, variation_strength
            )
        except Exception as exc:
            return Response(json.dumps({"error": {
                "code": "model_unavailable",
                "message": f"Mock fulfillment failed: {exc}"
            }}), status=500, mimetype="application/json")
        return Response(json.dumps({
            "images":   mock_images,
            "provider": "mock-image-varies",
            "mode":     "varies",
            "mocked":   True,
            "metadata": {"count": count, "variation_strength": variation_strength},
        }), status=200, mimetype="application/json")

    # Real path: Replicate (`lucataco/sdxl-img2img`) via the registry.
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        import replicate as _replicate
        registry = _load_registry()
        _replicate.register_replicate_provider(registry)
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Replicate provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    handler_inputs = {
        "source_image":       src_data_url or source_id,
        "count":              count,
        "variation_strength": variation_strength,
    }
    provider_override = data.get("provider_override") or inputs.get("provider_override") or None

    try:
        result = registry.invoke(
            "image_varies",
            handler_inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "model_unavailable")
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=502 if code == "model_unavailable" else 400,
            mimetype="application/json")

    # Replicate dispatch returns a list of {'image_url'|'image_data_uri': ...}.
    output = getattr(result, "output", result)
    provider_id = getattr(result, "provider_id", "replicate")

    images_out = []
    if isinstance(output, list):
        from urllib.request import urlopen
        import base64
        for entry in output:
            b64 = None
            if isinstance(entry, dict):
                if isinstance(entry.get("image_data_uri"), str):
                    uri = entry["image_data_uri"]
                    if ";base64," in uri:
                        b64 = uri.split(";base64,", 1)[1]
                elif isinstance(entry.get("image_url"), str):
                    try:
                        with urlopen(entry["image_url"], timeout=30) as resp:
                            b64 = base64.b64encode(resp.read()).decode("ascii")
                    except Exception:
                        b64 = None
            elif isinstance(entry, (bytes, bytearray)):
                b64 = base64.b64encode(bytes(entry)).decode("ascii")
            if b64:
                images_out.append({"data": b64, "mime_type": "image/png"})

    if not images_out:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Handler returned no usable image data."
        }}), status=502, mimetype="application/json")

    return Response(json.dumps({
        "images":   images_out,
        "provider": provider_id,
        "mode":     "varies",
        "metadata": {"count": count, "variation_strength": variation_strength},
    }), status=200, mimetype="application/json")


def _build_mock_image_varies_result(source_bytes, count, variation_strength):
    """Build a deterministic list of `count` tinted variants of source_bytes.

    Strategy: applies a deterministic color tint per variant index (cycling
    through red/green/blue/yellow) at intensity scaled by
    variation_strength. When source_bytes is unavailable (id-only request),
    we emit `count` solid-colored 256×256 placeholders so the §13.3
    "verify image data lands" path still runs. Returns a list of
    {data, mime_type} dicts the JS `_extractImages` accepts.
    """
    from PIL import Image
    import io
    import base64

    # Tint colors cycle (R, G, B, Y, M, C, plus wraparound).
    tints = [
        (255,  60,  60),
        ( 60, 220,  90),
        ( 60, 100, 240),
        (240, 200,  40),
        (200,  80, 220),
        ( 60, 220, 220),
        (240, 140,  40),
        (140, 200, 240),
    ]

    if source_bytes:
        src = Image.open(io.BytesIO(source_bytes)).convert("RGBA")
    else:
        src = Image.new("RGBA", (256, 256), (200, 200, 200, 255))

    out_list = []
    for i in range(count):
        tint = tints[i % len(tints)]
        overlay = Image.new("RGBA", src.size, (tint[0], tint[1], tint[2], 255))
        # blend factor scales with variation_strength; cap below 1 so the
        # source remains recognisable.
        blend = max(0.05, min(0.6, 0.15 + variation_strength * 0.4))
        variant = Image.blend(src, overlay, blend)
        buf = io.BytesIO()
        variant.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        out_list.append({"data": b64, "mime_type": "image/png"})
    return out_list


# ── /api/capability/image_to_prompt (WP-7.3.3g) ──────────────────────────────
# Server-side bridge between the WP-7.3.1 UI's `capability-dispatch` events
# and the WP-7.3.2c `dispatch_image_to_prompt` handler (Replicate
# `salesforce/blip` for the base caption + per-target-style adaptation).
# Body:
#   { slot, inputs: { image (str id, required), target_style? },
#     provider_override?, mock? }
# Per Contracts §3.7: returns text. Sync.
#
# Mock path: BLIP-style template + per-target-style flavor (DALL-E plain,
# SD comma-tag stack, MJ flags, Flux cinematic) so the §13.3 acceptance
# criterion ("verify caption + style adapter applied") runs without a key.

_VALID_TARGET_STYLES = ("dalle", "sd", "mj", "flux")


@app.route("/api/capability/image_to_prompt", methods=["POST"])
def capability_image_to_prompt():
    """Dispatch the `image_to_prompt` capability slot (Contracts §3.7).

    Body JSON:
      slot: 'image_to_prompt' (ignored — endpoint identifies slot),
      inputs: { image (str id, required),
                target_style (enum dalle/sd/mj/flux, optional),
                image_data_url (data URL, optional) },
      provider_override (str, optional), mock (bool, optional).

    Response:
      200 { prompt: str, provider: str, target_style: str, mocked? }
      4xx { error: { code: 'image_unreadable', message } }
      5xx { error: { code: 'model_unavailable', message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "image_unreadable",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}

    image_id = inputs.get("image")
    image_data_url = inputs.get("image_data_url")
    if (not isinstance(image_id, str) or not image_id.strip()) and \
       (not isinstance(image_data_url, str) or not image_data_url.strip()):
        return Response(json.dumps({"error": {
            "code": "image_unreadable",
            "message": "image_to_prompt requires a non-empty 'image'."
        }}), status=400, mimetype="application/json")

    target_style = inputs.get("target_style") or "dalle"
    if not isinstance(target_style, str) or target_style.lower() not in _VALID_TARGET_STYLES:
        target_style = "dalle"
    else:
        target_style = target_style.lower()

    # Optional inline image bytes (used by mock path for size-derived flavor).
    image_bytes = None
    if isinstance(image_data_url, str) and image_data_url.startswith("data:"):
        try:
            image_bytes = _decode_data_url(image_data_url, "image_data_url")
        except ValueError:
            image_bytes = None

    # Mock path: explicit mock flag OR no Replicate token.
    mock_requested = bool(data.get("mock") or inputs.get("mock"))
    has_replicate_token = bool(
        os.environ.get("REPLICATE_API_TOKEN")
        or _try_keychain_replicate_token()
    )
    if mock_requested or not has_replicate_token:
        try:
            prompt_text = _build_mock_image_to_prompt_result(
                image_bytes, target_style
            )
        except Exception as exc:
            return Response(json.dumps({"error": {
                "code": "model_unavailable",
                "message": f"Mock fulfillment failed: {exc}"
            }}), status=500, mimetype="application/json")
        return Response(json.dumps({
            "prompt":       prompt_text,
            "provider":     "mock-image-to-prompt",
            "target_style": target_style,
            "mocked":       True,
        }), status=200, mimetype="application/json")

    # Real path: Replicate (`salesforce/blip`) via the registry.
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        import replicate as _replicate
        registry = _load_registry()
        _replicate.register_replicate_provider(registry)
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Replicate provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    handler_inputs = {
        "image":        image_data_url or image_id,
        "target_style": target_style,
    }
    provider_override = data.get("provider_override") or inputs.get("provider_override") or None

    try:
        result = registry.invoke(
            "image_to_prompt",
            handler_inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "model_unavailable")
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=502 if code == "model_unavailable" else 400,
            mimetype="application/json")

    output = getattr(result, "output", result)
    provider_id = getattr(result, "provider_id", "replicate")

    if not isinstance(output, str) or not output.strip():
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Handler returned no caption text."
        }}), status=502, mimetype="application/json")

    return Response(json.dumps({
        "prompt":       output,
        "provider":     provider_id,
        "target_style": target_style,
    }), status=200, mimetype="application/json")


def _build_mock_image_to_prompt_result(image_bytes, target_style):
    """Build a deterministic BLIP-style mock caption with per-style flavor.

    Returns a single-line prompt the JS `_extractPrompt` lifts via
    `response.prompt`. Per-target-style suffix mirrors the canonical
    behavior of `_adapt_caption_for_style` in
    orchestrator/integrations/replicate.py so the §13.3 acceptance test
    ("each style emits its idiomatic phrasing") runs end-to-end.
    """
    # Vary the base caption by the source bytes' length so re-runs with
    # the same image are deterministic but different images get different
    # captions. When image_bytes is missing, fall back to a placeholder.
    if image_bytes:
        marker = (len(image_bytes) % 5) + 1
    else:
        marker = 3

    base_templates = [
        "a photograph of a landscape with rolling hills under a clear sky",
        "a stylised portrait of a figure facing the viewer in soft light",
        "a still life arrangement of objects on a wooden surface",
        "an architectural study of a tall structure against the horizon",
        "an abstract composition of overlapping geometric shapes",
        "a macro shot of organic textures with shallow depth of field",
    ]
    base = base_templates[marker % len(base_templates)]

    flavor_suffix = {
        "dalle": "",
        "sd":    ", highly detailed, masterpiece, 8k, hyperrealistic",
        "mj":    " --ar 16:9 --v 6 --style raw",
        "flux":  ", cinematic lighting, ultra-realistic",
    }.get(target_style, "")

    return base + flavor_suffix


# ── /api/capability/video_generates (WP-7.3.3i) ──────────────────────────────
# Server-side bridge between the WP-7.3.1 UI's `capability-dispatch` events
# and the WP-7.3.2c `dispatch_video_generates` handler (Replicate
# `minimax/video-01`). Async — the JS expects:
#   200 { job: { id, status, capability, parameters, placeholder_anchor?,
#                dispatched_at, ... }, conversation_id? }
# Per Contracts §3.9: required `prompt`; optional `duration`, `style`,
# `resolution`. Returns video bytes via the WP-7.6.1 job queue (polling
# thread inside replicate._async_dispatch lands the result).
#
# No mock path: async slots return a job dict regardless. When no
# Replicate token is configured, the registry surfaces model_unavailable
# at invoke time, the same way the sync slots do.

_VALID_VIDEO_RESOLUTIONS = ("720p", "1080p", "4k", "square")


@app.route("/api/capability/video_generates", methods=["POST"])
def capability_video_generates():
    """Dispatch the `video_generates` capability slot (Contracts §3.9, async).

    Body JSON:
      slot: 'video_generates' (ignored — endpoint identifies slot),
      inputs: { prompt (str, required), duration (int, optional),
                style (str, optional), resolution (str, optional) },
      placeholder_anchor (dict {x,y,width,height}, optional),
      provider_override (str, optional),
      conversation_id (str, optional — sets the queue bucket).

    Response:
      200 { job: { id, status, capability, parameters,
                   placeholder_anchor?, dispatched_at, ... },
            conversation_id: str | None }
      4xx { error: { code: 'prompt_rejected'|..., message } }
      5xx { error: { code: 'model_unavailable', message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "prompt_rejected",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}

    prompt = (inputs.get("prompt") or "").strip()
    if not prompt:
        return Response(json.dumps({"error": {
            "code": "prompt_rejected",
            "message": "video_generates requires a non-empty 'prompt'."
        }}), status=400, mimetype="application/json")

    # Optional metadata — pass through to the handler and onto the job
    # parameters so job-queue.js can render duration/resolution badges.
    handler_inputs = {"prompt": prompt}
    duration = inputs.get("duration")
    if duration is not None:
        try:
            handler_inputs["duration"] = int(duration)
        except (TypeError, ValueError):
            pass
    style = inputs.get("style")
    if isinstance(style, str) and style.strip():
        handler_inputs["style"] = style.strip()
    resolution = inputs.get("resolution")
    if isinstance(resolution, str) and resolution.strip():
        if resolution.strip().lower() in _VALID_VIDEO_RESOLUTIONS:
            handler_inputs["resolution"] = resolution.strip().lower()

    placeholder_anchor = data.get("placeholder_anchor")
    if not isinstance(placeholder_anchor, dict):
        placeholder_anchor = None

    conversation_id = data.get("conversation_id") or inputs.get("conversation_id") or "default"

    # Async slot: no mock path. The registry surfaces model_unavailable at
    # invoke time when no token is configured. The JS handles that via
    # capability-error → fix path. (We still gate on the queue/integration
    # being importable so we can return a clean 503 instead of an opaque
    # 500 from a missing module.)
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        import replicate as _replicate
        registry = _load_registry()
        _replicate.register_replicate_provider(registry)
        # OpenRouter-catalog video models (openrouter:<vendor>/<model>).
        # Must register on this invoke route too — the configured chain
        # (Wan 2.6 → Veo 3.1 Fast) is all openrouter:* ids, and
        # resolve_provider_chain skips unregistered ids, so without this
        # the chain collapsed to whatever replicate registered.
        try:
            import openrouter_images as _orimg
            _orimg.register(registry)
        except Exception:
            pass
        # Tell the replicate dispatcher which conversation bucket to file
        # the job under (per replicate.set_active_conversation).
        try:
            _replicate.set_active_conversation(conversation_id)
        except Exception:
            pass
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Replicate provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    provider_override = data.get("provider_override") or inputs.get("provider_override") or None

    try:
        result = registry.invoke(
            "video_generates",
            handler_inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "model_unavailable")
        # Per JS `_statusToCode`: 400 → prompt_rejected, 5xx → model_unavailable.
        status = 502 if code == "model_unavailable" else 400
        if code in ("prompt_rejected", "duration_unsupported", "resolution_unsupported"):
            status = 400
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=status, mimetype="application/json")

    # Async dispatcher returns the job dict directly (or via InvocationResult
    # wrapping). Pull it out the same way as the sync slots.
    job = getattr(result, "output", result)
    if not isinstance(job, dict) or not job.get("id"):
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Async dispatcher returned no job descriptor."
        }}), status=502, mimetype="application/json")

    # Stamp the placeholder_anchor on the returned job dict so job-queue.js
    # can render the canvas placeholder over the right region. The queue
    # itself doesn't track this (it's a UI-only field), so we attach it in
    # the response without mutating the persisted job.
    if placeholder_anchor is not None:
        job = dict(job)
        job["placeholder_anchor"] = placeholder_anchor

    return Response(json.dumps({
        "job":             job,
        "conversation_id": conversation_id,
    }), status=200, mimetype="application/json")


@app.route("/api/capability/style_trains", methods=["POST"])
def capability_style_trains():
    """Dispatch the `style_trains` capability slot (Contracts §3.10, async).

    The other async slot. Everything this needs already existed — the slot
    contract, the Replicate routing entry, ``dispatch_style_trains``, and
    ``capability-style-trains.js`` posting here — but the route itself was
    never written, so the Style Trains control 404'd on click.

    Body JSON:
      inputs: { reference_images (list, >=3, required),
                name (str, required — trigger word for the adapter),
                training_depth ('quick'|'standard'|'deep', optional) },
      provider_override (str, optional),
      conversation_id (str, optional — sets the queue bucket).

    Response:
      200 { job: {...}, conversation_id: str | None }
      4xx { error: { code: 'insufficient_examples'|'prompt_rejected', message } }
      5xx { error: { code: 'model_unavailable', message } }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return Response(json.dumps({"error": {
            "code": "prompt_rejected",
            "message": "Request body must be JSON."
        }}), status=400, mimetype="application/json")

    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}

    refs = inputs.get("reference_images")
    if not isinstance(refs, list) or len(refs) < 3:
        return Response(json.dumps({"error": {
            "code": "insufficient_examples",
            "message": "style_trains requires at least 3 reference images."
        }}), status=400, mimetype="application/json")

    name = (inputs.get("name") or "").strip()
    if not name:
        return Response(json.dumps({"error": {
            "code": "prompt_rejected",
            "message": "style_trains requires a non-empty 'name' for the adapter."
        }}), status=400, mimetype="application/json")

    handler_inputs = {"reference_images": refs, "name": name}
    depth = inputs.get("training_depth")
    if isinstance(depth, str) and depth.strip().lower() in ("quick", "standard", "deep"):
        handler_inputs["training_depth"] = depth.strip().lower()

    conversation_id = (
        data.get("conversation_id") or inputs.get("conversation_id") or "default"
    )

    # Async slot: no mock path, same as video_generates. Gate on the queue and
    # integration importing so a missing module is a clean 503 rather than an
    # opaque 500. style_trains routes to Replicate only, so unlike
    # video_generates there is no OpenRouter chain to register here.
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        import replicate as _replicate
        registry = _load_registry()
        _replicate.register_replicate_provider(registry)
        try:
            _replicate.set_active_conversation(conversation_id)
        except Exception:
            pass
    except Exception as exc:
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": f"Replicate provider unavailable: {exc}"
        }}), status=503, mimetype="application/json")

    provider_override = (
        data.get("provider_override") or inputs.get("provider_override") or None
    )

    try:
        result = registry.invoke(
            "style_trains",
            handler_inputs,
            provider_id=provider_override,
        )
    except Exception as exc:
        code = getattr(exc, "code", "model_unavailable")
        status = 400 if code in ("insufficient_examples", "prompt_rejected") else 502
        return Response(json.dumps({"error": {
            "code": code,
            "message": str(exc)
        }}), status=status, mimetype="application/json")

    job = getattr(result, "output", result)
    if not isinstance(job, dict) or not job.get("id"):
        return Response(json.dumps({"error": {
            "code": "model_unavailable",
            "message": "Async dispatcher returned no job descriptor."
        }}), status=502, mimetype="application/json")

    return Response(json.dumps({
        "job":             job,
        "conversation_id": conversation_id,
    }), status=200, mimetype="application/json")


# ── model switcher ───────────────────────────────────────────────────────────

LOCAL_MODELS_DIR = Path.home() / "ora" / "models"
_local_model_inventory_lock = threading.RLock()


def _refresh_local_model_inventory() -> tuple[dict | None, str | None]:
    """Refresh the installed-model snapshot, preserving it on scan failure."""
    try:
        from local_model_discovery import refresh as _refresh
        with _local_model_inventory_lock:
            result = _refresh(
                models_json=Path(MODELS_JSON),
                models_dir=LOCAL_MODELS_DIR,
                routing_config=Path(_routing_config_path()),
                write=True,
            )
            # Retry the live Router after every authoritative scan. A failed
            # reload must not become permanent merely because models.json is
            # already current on the next pane load. False remains the
            # expected no-op result when no Router has been instantiated.
            result["router_reloaded"] = (
                _reload_pipeline_router_after_config_change()
            )
        return result, None
    except Exception as exc:
        # refresh scans before writing, so the existing models.json remains the
        # last-known-good truth when the root is missing or unreadable.
        return None, str(exc)

def get_system_ram_gb():
    try:
        from platform_check import get_system_ram_gb as _get_ram
        return _get_ram()
    except ImportError:
        return 16.0

def load_models():
    try:
        with open(MODELS_JSON) as f:
            return json.load(f)
    except Exception:
        return {"overhead_reservation_gb": 8, "local_models": [], "commercial_models": []}


def _models_payload(models_cfg: dict, discovery_error: str | None = None) -> dict:
    from orchestrator import active_configuration as _ac

    models_document_error = None
    if not isinstance(models_cfg, dict):
        models_document_error = (
            "local model inventory is malformed: root must be an object"
        )
        models_cfg = {}

    config = load_config()
    ep_by_name = {
        (e.get("id") or e.get("name")): e
        for e in config.get("endpoints", [])
        if e.get("id") or e.get("name")
    }

    system_ram = get_system_ram_gb()
    overhead = models_cfg.get("overhead_reservation_gb", 8)
    budget = system_ram - overhead
    local_models = models_cfg.get("local_models")
    active_profile_name = None
    allocation_error = None
    try:
        if models_document_error:
            raise ValueError(models_document_error)
        active_profile_name = _ac.get_active_name(strict=True)
        active_profile = _ac._load_config(active_profile_name)
        allocation = _ac.profile_ram_allocation(
            active_profile,
            system_ram_gb=system_ram,
            local_models=local_models,
        )
    except Exception as exc:
        # This endpoint is display-only.  A missing pointer/profile or
        # untrustworthy inventory must clear prior allocation figures without
        # turning the Models pane itself into an authorization bypass.
        active_profile_name = None
        allocation_error = str(exc)
        automatic_target = max(
            0.0, float(system_ram) * _ac.AUTOMATIC_RAM_TARGET_RATIO,
        )
        hard_cap = max(0.0, float(system_ram) * _ac.HARD_RAM_CAP_RATIO)
        allocation = {
            "automatic_target_gb": automatic_target,
            "hard_cap_gb": hard_cap,
            "active_local_model_ids": [],
            "allocated_local_ram_gb": 0.0,
            "headroom_to_hard_cap_gb": hard_cap,
        }
    commercial_rows = models_cfg.get("commercial_models", [])
    commercial_models = [
        dict(model) for model in commercial_rows if isinstance(model, dict)
    ] if isinstance(commercial_rows, list) else []
    for model in commercial_models:
        ep = ep_by_name.get(model.get("id"), {})
        model["available"] = ep.get("status") == "active"

    return {
        "system_ram_gb": round(system_ram, 1),
        "overhead_gb": overhead,
        "available_budget_gb": round(budget, 1),
        "local_models": [
            dict(model) for model in local_models if isinstance(model, dict)
        ] if isinstance(local_models, list) else [],
        "commercial_models": commercial_models,
        "slot_assignments": config.get("slot_assignments", {}),
        "gear4_overrides": config.get("gear4_overrides", {}),
        "local_discovery_error": discovery_error,
        "active_profile_name": active_profile_name,
        "allocation_error": allocation_error,
        "automatic_target_gb": allocation["automatic_target_gb"],
        "hard_cap_gb": allocation["hard_cap_gb"],
        "active_local_model_ids": allocation["active_local_model_ids"],
        "allocated_local_ram_gb": allocation["allocated_local_ram_gb"],
        "headroom_to_hard_cap_gb": allocation["headroom_to_hard_cap_gb"],
    }

@app.route("/models")
def models_endpoint():
    _refresh_result, discovery_error = _refresh_local_model_inventory()
    models_cfg = load_models()
    return json.dumps(_models_payload(models_cfg, discovery_error))


@app.route("/api/local-models/trash", methods=["POST"])
def local_model_trash():
    """Move one currently discovered physical local model to macOS Trash."""
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    body = request.get_json(silent=True) or {}
    model_id = body.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        return _json_response({"ok": False, "error": "model_id is required"}, status=400)
    model_id = model_id.strip()

    from local_model_discovery import (
        LocalModelDeleteError,
        move_model_to_trash,
        refresh as _refresh,
        resolve_delete_target,
    )
    from orchestrator import system_protection as _sp

    with _local_model_inventory_lock:
        try:
            current = _refresh(
                models_json=Path(MODELS_JSON),
                models_dir=LOCAL_MODELS_DIR,
                routing_config=Path(_routing_config_path()),
                write=True,
            )
            target = resolve_delete_target(
                model_id, current["discovered"], LOCAL_MODELS_DIR
            )
            models_root = Path(LOCAL_MODELS_DIR).expanduser().resolve(strict=True)
        except LocalModelDeleteError as exc:
            return _json_response({"ok": False, "error": str(exc)}, status=404)
        except Exception as exc:
            return _json_response({
                "ok": False,
                "error": f"local model discovery failed: {exc}",
            }, status=503)

        if current.get("discovered") != current.get("previous"):
            _reload_pipeline_router_after_config_change()

        current_row = next(
            row for row in current["discovered"] if row.get("id") == model_id
        )
        machine_id = current_row.get("machine") or "studio-128"
        authorized_target = target
        protection = None

        try:
            selector = _sp.local_model_selector(target, models_root)
            pre_state = _sp.capture_local_model_identity(target, models_root)
            protection = _sp.authorize_server_action(
                "local_model_trash",
                selectors=[selector],
                params={"model_id": model_id, "machine_id": machine_id},
                pre_state=[pre_state],
            )
        except Exception as exc:
            if isinstance(exc, _sp.SystemProtectionError):
                return _system_protection_error_response(exc)
            return _json_response({
                "ok": False,
                "error": f"local model protection failed: {exc}",
            }, status=500)

        try:
            try:
                import mlx_mutex
            except ImportError:
                from orchestrator import mlx_mutex
            with mlx_mutex.acquire(machine_id):
                # The mutex wait can be long enough for external filesystem
                # changes. Re-scan and re-resolve under the lock immediately
                # before eviction and mutation.
                locked = _refresh(
                    models_json=Path(MODELS_JSON),
                    models_dir=LOCAL_MODELS_DIR,
                    routing_config=Path(_routing_config_path()),
                    write=False,
                )
                target = resolve_delete_target(
                    model_id, locked["discovered"], LOCAL_MODELS_DIR
                )
                locked_root = Path(LOCAL_MODELS_DIR).expanduser().resolve(strict=True)
                if _sp.local_model_selector(target, locked_root) != selector:
                    raise LocalModelDeleteError(
                        "local model target changed after approval"
                    )
                with _sp.protected_effect(protection):
                    _boot_context_api().evict_mlx_model(str(target))
                    move_model_to_trash(target)
        except Exception as exc:
            try:
                _sp.complete_execution(
                    protection,
                    ok=False,
                    result={"error": type(exc).__name__, "model_id": model_id},
                    post_state=[
                        _sp.capture_local_model_identity(
                            authorized_target, models_root
                        )
                    ],
                )
            except Exception as receipt_error:
                return _system_protection_error_response(receipt_error)
            if isinstance(exc, _sp.SystemProtectionError):
                return _system_protection_error_response(exc)
            if isinstance(exc, LocalModelDeleteError):
                return _json_response({"ok": False, "error": str(exc)}, status=409)
            return _json_response({
                "ok": False,
                "error": f"could not move local model to Trash: {exc}",
            }, status=500)

        try:
            _sp.complete_execution(
                protection,
                ok=True,
                result={"moved_to_trash": True, "model_id": model_id},
                post_state=[
                    _sp.capture_local_model_identity(
                        authorized_target, models_root
                    )
                ],
            )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)

        try:
            updated = _refresh(
                models_json=Path(MODELS_JSON),
                models_dir=LOCAL_MODELS_DIR,
                routing_config=Path(_routing_config_path()),
                write=True,
            )
        except Exception as exc:
            _reload_pipeline_router_after_config_change()
            return _json_response({
                "ok": False,
                "moved_to_trash": True,
                "model_id": model_id,
                "error": f"model moved to Trash, but inventory refresh failed: {exc}",
            }, status=500)

        router_reloaded = _reload_pipeline_router_after_config_change()
        hardware = _models_payload(load_models())
        return _json_response({
            "ok": True,
            "moved_to_trash": True,
            "model_id": model_id,
            "inventory": updated["discovered"],
            "hardware": hardware,
            "router_reloaded": router_reloaded,
        })


# ── Model registry: read access + on-demand refresh ─────────────────────────
#
# The V3 settings → models pane reads the curated capability registry
# (intelligence scores, latency, TPS, vision flags) via these endpoints
# instead of going to OpenRouter / LiteLLM / Chatbot Arena / AA directly.
# Refresh runs `sync_model_registry.py sync --no-probe`: 4 HTTP fetches,
# ~15-30 seconds wall-time, zero tokens. The reach probe (which DOES
# burn tokens) is not part of the sync subprocess itself — the refresh
# endpoint spawns it separately at the end of every successful refresh
# (_spawn_reach_probe with defaults: never-probed models + verdicts
# older than 7 days), since 2026-06-11's probe-gated picks.
#
# A 5-minute TTL guard short-circuits re-syncs when the registry was
# recently refreshed (multiple pane opens in quick succession shouldn't
# re-pull the whole catalog each time). The TTL is per-instance —
# resets on server restart.

_REGISTRY_REFRESH_TTL_SECONDS = 300  # 5 min
_registry_refresh_state = {
    "last_refresh_at": 0.0,
    "last_result": None,
    "in_progress": False,
}
_registry_refresh_lock = threading.Lock()

# Reach-probe state. Separate from the refresh state because probes run
# on their own cadence: auto-kicked after every registry refresh, plus
# the Models pane's manual re-verify buttons.
# Holds progress so the UI can show a status indicator while a probe runs.
_reach_probe_state = {
    "in_progress": False,
    "started_at": 0.0,
    "completed_at": 0.0,
    "current_index": 0,
    "total": 0,
    "current_model": "",
    "last_summary": None,  # filled when the probe finishes
}
_reach_probe_lock = threading.Lock()


@app.route("/api/model-registry", methods=["GET"])
def model_registry_get():
    """Return the active serving registry as JSON.

    Reads ``config/model-registry.json`` as the base. In default-on
    vendor-authoritative mode, a present generated
    ``config/model-registry.vendor-authoritative.json`` replaces that serving
    view later in this handler. When the base file is missing,
    returns an empty registry shape ({models: {}}) with status=200 —
    the UI handles "no models known yet" gracefully and prompts a
    sync.

    Query param ``categories`` (comma-separated) filters which model
    categories to include. Entries with no ``category`` field are
    treated as ``chat`` (the existing 358-model corpus). Recognized
    values: ``chat``, ``image_generation``, ``image_editing``,
    ``text_to_video``, or ``all`` to bypass the filter. Default:
    ``chat`` — preserves the pre-Chunk-11 contract so the existing
    Models pane keeps working without changes. The rebuilt Visual
    surface (and the image-generation row on Models) opts in by
    passing ``categories=chat,image_generation`` etc.
    """
    _local_refresh, _local_discovery_error = _refresh_local_model_inventory()
    try:
        from orchestrator import model_registry as mr
        registry = mr.load_registry()
        stats = mr.stats()
    except Exception as exc:
        return _json_response({
            "error": f"registry-read-failed: {exc}",
            "models": {},
            "stats": {"loaded": False},
        }, status=500)

    # Per-provider OpenRouter latency/throughput (or_ttft_ms / or_throughput_tps,
    # PR #114) lives on the OpenRouter-sourced BASE registry. Capture it before
    # the vendor-authoritative swap below replaces keyed vendors' OpenRouter
    # entries with NATIVE entries that don't carry these stats — so the swapped
    # inventory can be re-enriched from here via the alias map (the OR twin's
    # latency is the best available signal for a native model we dispatch
    # directly). Keyed by base id.
    _base_or_latency = {
        _mid: {"or_ttft_ms": _m.get("or_ttft_ms"),
               "or_throughput_tps": _m.get("or_throughput_tps")}
        for _mid, _m in (registry.get("models") or {}).items()
        if isinstance(_m, dict) and _m.get("or_ttft_ms") is not None
    }

    # Probe/audit verdict counts from the BASE registry — the reach
    # probe's actual read/write target (`sync_model_registry.py reach`
    # selects targets and flushes verdicts against it). The served
    # inventory built below synthesizes reachable=True onto
    # direct-dispatch / local / subscription entries, so counting THAT
    # under-reports unverified models: the pane once showed
    # "UNVERIFIED 0" while the base registry held 11 null verdicts, and
    # its "Probe 0 unverified only" button would really have probed 11.
    _reach_counts = {
        "total": 0, "reach_true": 0, "reach_rate": 0,
        "reach_false": 0, "reach_null": 0,
        "vendor_true": 0, "vendor_false": 0, "vendor_null": 0,
        "newest_probed_at": None,
    }
    for _m in (registry.get("models") or {}).values():
        if not isinstance(_m, dict) or (_m.get("category") or "chat") != "chat":
            continue
        _reach_counts["total"] += 1
        if _m.get("reachable") is True:
            _reach_counts["reach_true"] += 1
            if _m.get("reachable_rate_limited"):
                _reach_counts["reach_rate"] += 1
        elif _m.get("reachable") is False:
            _reach_counts["reach_false"] += 1
        else:
            _reach_counts["reach_null"] += 1
        if _m.get("vendor_listed") is True:
            _reach_counts["vendor_true"] += 1
        elif _m.get("vendor_listed") is False:
            _reach_counts["vendor_false"] += 1
        else:
            _reach_counts["vendor_null"] += 1
        _d = _m.get("reachable_probed_at")
        if _d and (not _reach_counts["newest_probed_at"]
                   or _d > _reach_counts["newest_probed_at"]):
            _reach_counts["newest_probed_at"] = _d

    # Vendor-catalogue-authoritative inventory (flag-gated, default on): when on
    # and the preview registry exists, serve each keyed vendor's OWN catalogue
    # (native ids) instead of its OpenRouter entries. Native entries carry
    # dispatch="direct" → surface direct_dispatch so the pane paints the DIRECT chip.
    try:
        from orchestrator import vendor_catalog_registry as _vcr
        _va = rp.vendor_authoritative_registry_path()
        if _vcr.enabled() and _va.exists():
            import json as _vaj
            registry = _vaj.loads(_va.read_text())
            _va_models = registry.get("models") or {}
            for _m in _va_models.values():
                if isinstance(_m, dict) and _m.get("dispatch") == "direct":
                    _m["direct_dispatch"] = True
                    _m.setdefault("direct_service", _m.get("service") or _m.get("vendor"))
                    # It's in the vendor's live /models, fetched with the key — reachable.
                    _m.setdefault("reachable", True)
                    _m.setdefault("category", "chat")
            # Re-attach OpenRouter latency/throughput to native entries that lack
            # it (the inversion dropped the OR twin that carried it). Resolve via
            # the SAME alias map the pane uses (exact, no fuzzy match): a native
            # id's legacy/OR alias forms point back at the base-registry row that
            # has or_ttft_ms. Lifts coverage from ~122 to ~278 of ~403 native
            # entries; the rest genuinely lack OR stats anywhere. Tagged
            # or_latency_via_alias so the source is traceable.
            _aliases = registry.get("aliases") or {}
            _canon_to_legacy: dict = {}
            for _legacy, _canon in _aliases.items():
                _canon_to_legacy.setdefault(_canon, []).append(_legacy)
            for _nid, _m in _va_models.items():
                if not isinstance(_m, dict) or _m.get("or_ttft_ms") is not None:
                    continue
                for _cand in [_nid, *_canon_to_legacy.get(_nid, []), *(_m.get("also_known_as") or [])]:
                    _src = _base_or_latency.get(_cand)
                    if _src:
                        _m["or_ttft_ms"] = _src["or_ttft_ms"]
                        if _src.get("or_throughput_tps") is not None:
                            _m.setdefault("or_throughput_tps", _src["or_throughput_tps"])
                        _m["or_latency_via_alias"] = True
                        break
            # stats must describe the SWAPPED inventory, not the OpenRouter one.
            _vt = sum(1 for _e in _va_models.values() if _e.get("vision_capable") is True)
            _vf = sum(1 for _e in _va_models.values() if _e.get("vision_capable") is False)
            stats = {
                "registry_path": "vendor-authoritative",
                "loaded": len(_va_models) > 0,
                "model_count": len(_va_models),
                "vision_capable_true": _vt,
                "vision_capable_false": _vf,
                "vision_capable_null": len(_va_models) - _vt - _vf,
                "intelligence_score_count": sum(
                    1 for _e in _va_models.values() if _e.get("intelligence_score") is not None),
                "generated_at": registry.get("generated_at"),
                "last_probe_at": registry.get("last_probe_at"),
            }
    except Exception as _va_err:
        print(f"[model-registry] vendor-authoritative inventory skipped: {_va_err}", flush=True)

    raw = request.args.get("categories", "chat")
    if raw.strip().lower() in ("all", "*"):
        wanted = None  # no filter
    else:
        wanted = {c.strip() for c in raw.split(",") if c.strip()}

    all_models = registry.get("models") or {}
    if wanted is None:
        filtered = all_models
    else:
        filtered = {
            mid: m for mid, m in all_models.items()
            if (m.get("category") or "chat") in wanted
        }

    # Enrich each model with size_bucket + parameters_b + is_free
    # from the catalog so the Models pane can filter the inventory by
    # the slot's expected size (BIG → large, SMALL → small) and the
    # "Paid only" chip can hide :free entries cleanly. The registry
    # itself doesn't currently carry these — they're computed by the
    # catalog-refresh pipeline. Cheap join: catalog is ~600 entries.
    try:
        import json as _json
        _catalog_path = rp.model_catalog_path()
        if _catalog_path.exists():
            _catalog = _json.loads(_catalog_path.read_text())
            _by_id = {m.get("id"): m for m in (_catalog.get("models") or []) if m.get("id")}
            enriched = {}
            for mid, m in filtered.items():
                cm = _by_id.get(mid) or {}
                merged = dict(m)
                if cm.get("size_bucket") is not None:
                    merged["size_bucket"] = cm["size_bucket"]
                if cm.get("parameters_b") is not None:
                    merged["parameters_b"] = cm["parameters_b"]
                if cm.get("is_free") is not None:
                    merged["is_free"] = cm["is_free"]
                # Output modalities let the pane exclude image/video-
                # OUTPUT models from the chat inventory. They accept
                # image input (hence vision_capable=true) but generate
                # media, not chat — they belong to the Visual tab's
                # capability slots, and their fuzzy-borrowed Arena Elos
                # (gpt-5-image inheriting gpt-5's score) polluted the
                # chat intelligence sort.
                if cm.get("output_modalities"):
                    merged["output_modalities"] = cm["output_modalities"]
                # Surface vendor_audit verdict + bare id to the frontend
                # so the inventory can paint VENDOR-PHANTOM chips. Already
                # mirrored at the top level by sync_model_registry.py's
                # _run_vendor_audit, but pass through defensively in case
                # an older registry only has the provenance copy.
                prov = m.get("_provenance") or {}
                va = prov.get("vendor_audit") or {}
                if "vendor_listed" not in merged and "vendor_listed" in va:
                    merged["vendor_listed"] = va.get("vendor_listed")
                if "vendor_audited_at" not in merged and "audited_at" in va:
                    merged["vendor_audited_at"] = va.get("audited_at")
                enriched[mid] = merged
            filtered = enriched
    except Exception as _enrich_err:
        # Enrichment is best-effort; degrade gracefully without it.
        print(f"[model-registry] enrichment skipped: {_enrich_err}", flush=True)

    # Merge local-MLX endpoints from routing-config.json into the
    # response so the Models pane inventory can list and pick them.
    # Local endpoints aren't in the registry (which is OpenRouter / AA
    # sourced) but the user needs to pick them just like cloud models.
    # They go into the 'chat' category and group as the "Local" vendor.
    try:
        if wanted is None or "chat" in wanted:
            import json as _json2
            _rc_path = rp.routing_config_path()
            if _rc_path.exists():
                _rc = _json2.loads(_rc_path.read_text())
                _configured_locals_by_path = {}
                for _endpoint in (_rc.get("endpoints") or []):
                    if _endpoint.get("type") != "local":
                        continue
                    _raw_path = _endpoint.get("model_path") or _endpoint.get("path")
                    if _raw_path:
                        _canonical_path = os.path.realpath(
                            os.path.expanduser(str(_raw_path))
                        )
                        _configured_locals_by_path.setdefault(
                            _canonical_path, _endpoint
                        )
                _runtime_subscription_endpoints = []
                try:
                    from orchestrator import codex_subscription as _codex_sub
                    if _codex_sub.is_configured():
                        _runtime_subscription_endpoints = (
                            _codex_sub.model_endpoints()
                        )
                        _sync_chatgpt_subscription_router(
                            _codex_sub.status()
                        )
                except Exception as _codex_sub_err:
                    print(
                        "[model-registry] ChatGPT subscription merge skipped: "
                        f"{type(_codex_sub_err).__name__}",
                        flush=True,
                    )
                # The loop below adds and replaces entries in ``filtered``;
                # when catalog enrichment was skipped, ``filtered`` can alias
                # the in-process registry cache itself (wanted=None path) —
                # copy the container first so UI-only additions (DIRECT
                # stamps, local merges) never leak into the shared cache.
                if filtered is all_models:
                    filtered = dict(all_models)
                # Defensive cleanup for process-local registries produced by an
                # older server version that leaked UI-only local rows into its
                # cache. The current successful discovery snapshot is rebuilt
                # once below, by physical path.
                filtered = {
                    mid: model for mid, model in filtered.items()
                    if not model.get("_local_endpoint")
                }
                for ep in [
                    *(_rc.get("endpoints") or []),
                    *_runtime_subscription_endpoints,
                ]:
                    eid = ep.get("id") or ep.get("name")
                    if not eid:
                        continue
                    # Subscription transports are runtime endpoints rather
                    # than metered registry entries. Surface both the static
                    # Claude Code routes and dynamically discovered ChatGPT /
                    # Codex routes as real, pickable models.
                    if (ep.get("type") == "api"
                            and ep.get("dispatch") == "subscription"):
                        if eid not in filtered:
                            provider_id = ep.get("provider") or "subscription"
                            provider_label = ep.get("subscription_provider")
                            if not provider_label:
                                provider_label = (
                                    "Anthropic" if provider_id == "anthropic"
                                    else str(provider_id).replace("-", " ").title()
                                )
                            transport_label = ep.get("subscription_transport")
                            if not transport_label:
                                transport_label = (
                                    "Claude subscription via the local Claude Code CLI"
                                    if ep.get("service") == "claude-code"
                                    else "provider-managed subscription runtime"
                                )
                            subscription_model = {
                                "id": eid,
                                "display_name": ep.get("display_name") or eid,
                                "description": ep.get("description") or "",
                                "provider": provider_id,
                                "vendor": "Subscription",
                                "category": "chat",
                                "vision_capable": False,
                                "input_modalities": ["text"],
                                "output_modalities": ["text"],
                                "context_length": ep.get("context_window"),
                                "pricing": {"input_per_token": 0,
                                            "output_per_token": 0,
                                            "blended_per_m": 0},
                                "is_free": False,
                                "reachable": bool(ep.get("enabled", True)
                                                  and ep.get("status") == "active"),
                                "reachable_rate_limited": False,
                                "vendor_listed": None,
                                "_subscription_endpoint": True,
                                "subscription_provider": provider_label,
                                "subscription_transport": transport_label,
                            }
                            for metric_field in (
                                "aa_intelligence_index", "aa_coding_index",
                                "aa_agentic_index", "intelligence_score",
                                "size_bucket", "parameters_b", "release_date",
                                "output_tokens_per_second", "or_throughput_tps",
                                "latency_ttft_seconds", "latency_total_seconds",
                                "or_ttft_ms", "reasoning_model",
                                "reasoning_capable", "forced_reasoning",
                                "metrics_inherited_from",
                            ):
                                if ep.get(metric_field) is not None:
                                    subscription_model[metric_field] = ep[metric_field]
                            filtered[eid] = subscription_model
                        continue
                    # DIRECT chip: the id has a registered api endpoint with
                    # dispatch=direct (vendor key present, so calls go to the
                    # vendor's own API, not OpenRouter). Copy the row before
                    # stamping — its dict may belong to the registry cache.
                    if ep.get("type") == "api" and ep.get("dispatch") == "direct":
                        if eid in filtered:
                            stamped = dict(filtered[eid])
                            stamped["direct_dispatch"] = True
                            stamped["direct_service"] = ep.get("service") or "direct"
                            filtered[eid] = stamped
                        continue
                    # Static local endpoints are deliberately not emitted here.
                    # They are joined by canonical path to the discovered set
                    # below, so an absent path cannot create a stale row.
                    if ep.get("type") == "local":
                        continue
                _models_path = Path(MODELS_JSON)
                if _models_path.exists():
                    _models_cfg = _json2.loads(_models_path.read_text())

                    def _local_size_bucket(m):
                        roles = set(m.get("recommended_roles") or [])
                        if roles.intersection({"breadth", "depth", "evaluator", "consolidator"}):
                            return "large"
                        ram = m.get("ram_gb")
                        params = m.get("parameters_b")
                        if params is None:
                            params = m.get("active_params_per_token")
                        try:
                            params = float(params) if params is not None else None
                        except (TypeError, ValueError):
                            params = None
                        if params is not None:
                            if params <= 12 and (ram is None or ram <= 8):
                                return "small"
                            if params <= 50:
                                return "midsize"
                            return "large"
                        if ram is not None:
                            if ram <= 8:
                                return "small"
                            if ram <= 32:
                                return "midsize"
                            return "large"
                        return None

                    _seen_local_paths = set()
                    for lm in (_models_cfg.get("local_models") or []):
                        path = lm.get("path") or lm.get("model_path")
                        if not path:
                            continue
                        canonical_path = os.path.realpath(
                            os.path.expanduser(str(path))
                        )
                        if canonical_path in _seen_local_paths:
                            continue
                        _seen_local_paths.add(canonical_path)
                        configured = _configured_locals_by_path.get(
                            canonical_path, {}
                        )
                        eid = configured.get("id") or lm.get("id")
                        if not eid:
                            continue
                        installed = os.path.isdir(canonical_path)
                        ram_gb = lm.get("ram_gb")
                        params = configured.get("parameters_b")
                        if params is None:
                            params = lm.get("parameters_b")
                        if params is None:
                            params = lm.get("active_params_per_token")
                        existing = dict(filtered.get(eid) or {})
                        ram_overhead_gb = configured.get("ram_overhead_gb") or 0
                        existing.update({
                            "id": eid,
                            "display_name": (configured.get("display_name")
                                             or lm.get("display_name")
                                             or existing.get("display_name") or eid),
                            "provider": (configured.get("provider")
                                         or existing.get("provider") or "local"),
                            "vendor": "Local",
                            "local": True,
                            "category": "chat",
                            "vision_capable": bool(configured.get(
                                "vision_capable",
                                lm.get("vision_capable", existing.get("vision_capable", False)),
                            )),
                            "vision_verified_by": ("endpoint_config"
                                                   if configured else "models_json"),
                            "context_length": (configured.get("context_window")
                                               or existing.get("context_length")),
                            "supports_function_calling": (
                                (configured.get("capabilities") or {}).get("tool_access")
                                if configured else existing.get("supports_function_calling")
                            ),
                            "pricing": existing.get("pricing") or {"input_per_token": 0, "output_per_token": 0, "blended_per_m": 0},
                            "is_free": True,
                            "size_bucket": existing.get("size_bucket") or _local_size_bucket(lm),
                            "parameters_b": params,
                            "ram_resident_gb": ram_gb,
                            "ram_overhead_gb": ram_overhead_gb,
                            "ram_total_gb": ((ram_gb or 0) + ram_overhead_gb) or None,
                            "reachable": bool(
                                installed
                                and configured.get("enabled", True)
                                and configured.get("status", "active") == "active"
                            ),
                            "reachable_rate_limited": False,
                            "vendor_listed": None,
                            "_local_endpoint": True,
                            "_installed_local_model": True,
                        })
                        filtered[eid] = existing
    except Exception as _local_err:
        print(f"[model-registry] local-endpoint merge skipped: {_local_err}", flush=True)

    return _json_response({
        "models": filtered,
        # Pre-inversion id → current native id, so the pane resolves saved
        # config/preset picks instead of falsely marking them DEPRECATED.
        # Empty {} on the base (flag-off) registry — harmless.
        "aliases": registry.get("aliases") or {},
        "generated_at": registry.get("generated_at"),
        "last_probe_at": registry.get("last_probe_at"),
        "aa_source": registry.get("aa_source"),
        # Base-registry probe/audit counts for the maintenance section
        # (see the comment where _reach_counts is computed).
        "reach_counts": _reach_counts,
        "stats": stats,
        "local_discovery_error": _local_discovery_error,
    })


@app.route("/api/configurations", methods=["GET"])
def configurations_list():
    """Return everything the Models pane needs to render in one shot:
    the 4 preset slots (free / budget / speed / premium), the user's
    saved customs, the active configuration name, and the active
    toggle state. Backs the presets row + custom-previous grid + header.

    Before returning, refresh the disk-authoritative local inventory and
    re-bake Free from its cloud baseline plus the current compatible local
    models. Other presets retain the existing first-load-only bake behavior.
    """
    try:
        from orchestrator import active_configuration as ac
        from orchestrator import model_profiles as _mp
        # Keep the inventory scan and Free re-bake in one serialized section:
        # the returned card must describe the physical models found by this
        # pane load, not whichever scan won a concurrent Promise.all request.
        with _local_model_inventory_lock:
            local_refresh, _local_error = _refresh_local_model_inventory()
            if local_refresh is not None:
                ac.bake_missing_presets(
                    force=True, preset_names=("free",))
            else:
                ac.bake_missing_presets()
            _reload_pipeline_router_after_config_change()
        return _json_response(_mp.decorate_configuration_catalog(
            ac.list_configurations()))
    except Exception as exc:
        return _json_response({
            "error": f"configurations-list-failed: {exc}",
            "presets": {p: None for p in ["free", "budget", "speed", "premium"]},
            "customs": [],
        }, status=500)


@app.route("/api/model-profiles", methods=["GET"])
def model_profiles_list():
    """List health and the exact effective inheritance result for the UI."""
    try:
        from orchestrator import active_configuration as ac
        from orchestrator import model_profiles as _mp
        ac.bake_missing_presets()
        project_nexus = (request.args.get("project_id") or "").strip() or None
        resolved = _mp.resolve_effective_profile(project_nexus=project_nexus)
        return _json_response({
            "profiles": _mp.list_profile_summaries(),
            "effective": resolved,
            "health_states": list(_mp.HEALTH_STATES),
        })
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=409)
    except Exception as exc:
        return _json_response({"error": f"model-profile-list-failed: {exc}"}, status=500)


@app.route("/api/model-profiles/global", methods=["POST"])
def model_profiles_set_global():
    """Set the account-wide default after health validation."""
    try:
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        from orchestrator import active_configuration as ac
        from orchestrator import model_profiles as _mp
        summary = _mp.profile_summary(_mp.validate_profile_name(name))
        if summary["health"]["status"] == "unavailable":
            raise _mp.ModelProfileError(
                f"cannot select unavailable Model Profile {name!r}"
            )
        ac.set_active_name(name)
        return _json_response({"ok": True, "profile": summary})
    except ValueError as exc:
        return _json_response({"ok": False, "error": str(exc)}, status=400)


@app.route("/api/model-profiles/project/<nexus>", methods=["POST"])
def model_profiles_set_project(nexus):
    """Bind/clear a project's exact profile and visual-routing snapshot."""
    try:
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        from orchestrator import model_profiles as _mp
        from orchestrator import project_meta as _pm
        if isinstance(name, str) and name.strip():
            name = name.strip()
            locks = _mp.capture_project_binding(name, nexus)
        elif name in (None, ""):
            name = None
            locks = {}
        else:
            raise _mp.ModelProfileError("name must be a Model Profile name or empty")
        meta = _pm.set_project_model_binding(nexus, name, locks)
        if meta is None:
            return _json_response({"ok": False, "error": f"no project {nexus!r}"}, 404)
        return _json_response({
            "ok": True,
            "project": meta,
            "effective": _mp.resolve_effective_profile(project_nexus=nexus),
        })
    except ValueError as exc:
        return _json_response({"ok": False, "error": str(exc)}, status=400)


@app.route("/api/model-profiles/migration/preview", methods=["POST"])
def model_profiles_migration_preview():
    """Read-only replacement proposal for a deprecated profile."""
    try:
        body = request.get_json(silent=True) or {}
        from orchestrator import model_profiles as _mp
        proposal = _mp.preview_migration(
            body.get("name"), (body.get("project_nexus") or "").strip() or None,
        )
        return _json_response({"ok": True, "proposal": proposal})
    except ValueError as exc:
        return _json_response({"ok": False, "error": str(exc)}, status=409)


@app.route("/api/model-profiles/migration/confirm", methods=["POST"])
def model_profiles_migration_confirm():
    """Apply one unchanged proposal only after explicit confirmation."""
    try:
        body = request.get_json(silent=True) or {}
        from orchestrator import model_profiles as _mp
        receipt = _mp.confirm_migration(
            body.get("name"), body.get("proposal_id"),
            user_confirmed=body.get("confirmed") is True,
            project_nexus=(body.get("project_nexus") or "").strip() or None,
        )
        return _json_response({"ok": True, "receipt": receipt})
    except ValueError as exc:
        return _json_response({"ok": False, "error": str(exc)}, status=409)


@app.route("/api/configurations/duplicate", methods=["POST"])
def configurations_duplicate():
    """Copy an existing configuration into a new file and activate it.

    Body: ``{"source": "<source-name>", "new_name": "<optional>"}``
    When ``new_name`` is omitted, the helper picks the next available
    ``Configuration NN``. The new copy carries preset_lineage=custom.
    """
    try:
        body = request.get_json(silent=True) or {}
        source = body.get("source")
        new_name = body.get("new_name")
        if not source or not isinstance(source, str):
            return _json_response({"error": "source name required"}, status=400)
        from orchestrator import active_configuration as ac
        created = ac.duplicate_configuration(source, new_name)
        ac.set_active_name(created)
        return _json_response({"name": created, "active": True})
    except (ValueError, FileNotFoundError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        return _json_response({"error": f"duplicate-failed: {exc}"}, status=500)


@app.route("/api/configurations/new", methods=["POST"])
def configurations_new():
    """Create a new blank custom configuration.

    Body: ``{"new_name": "<optional>"}``. Auto-named when omitted.
    The blank config has all slots set to null — the UI shows it red-
    bordered until the user fills every baseline primary, and refuses
    activation while red. The active marker does NOT move to the new
    blank: the user finishes filling it first and then explicitly
    activates by clicking the card.
    """
    try:
        body = request.get_json(silent=True) or {}
        new_name = body.get("new_name")
        from orchestrator import active_configuration as ac
        created = ac.create_blank_configuration(new_name)
        return _json_response({"name": created, "active": False})
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        return _json_response({"error": f"new-config-failed: {exc}"}, status=500)


@app.route("/api/configurations/<name>/slot", methods=["POST"])
def configurations_set_slot(name):
    """Update a single slot on a configuration.

    Body: ``{"slot": "<label>", "model_id": "..."}``.
    Visible-card slots ("big 1", "big 2", "small") fan out per
    SLOT_LABEL_TO_PATHS. Expand-view slots ("consolidator",
    "verifier", "formatter") write to a single post-analysis cell.
    The special label "visual" writes the picked model to every
    cell's vision_substitute field.
    """
    try:
        body = request.get_json(silent=True) or {}
        slot = body.get("slot")
        model_id = body.get("model_id")
        from orchestrator import active_configuration as ac
        if slot == "visual":
            ac.set_visual_substitute(name, model_id)
        else:
            ac.set_slot_primary(name, slot, model_id)
        return _json_response({"name": name, "slot": slot, "model_id": model_id})
    except (ValueError, FileNotFoundError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        return _json_response({"error": f"slot-set-failed: {exc}"}, status=500)


@app.route("/api/configurations/<name>/fallback", methods=["POST"])
def configurations_set_fallback(name):
    """Replace one position in a popout-section's fallback chain.

    Body: ``{"section": "large" | "fast" | "small" | "image",
              "index": <0-based int>, "model_id": "..."}``.

    Single-cell write (no fan-out). Pass an empty model_id to delete
    the position (compacts the chain).
    """
    try:
        body = request.get_json(silent=True) or {}
        section = body.get("section")
        index = body.get("index")
        model_id = body.get("model_id") or ""
        from orchestrator import active_configuration as ac
        ac.set_slot_fallback(name, section, index, model_id)
        return _json_response({
            "name": name, "section": section,
            "index": index, "model_id": model_id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        return _json_response({"error": f"fallback-set-failed: {exc}"}, status=500)


@app.route("/api/configurations/<name>", methods=["DELETE"])
def configurations_delete(name):
    """Delete a custom configuration.

    Deleting the currently-active configuration is allowed; the
    backend auto-reverts the active pointer to ``free``. Refuses to
    delete system configurations (background-default, user-pipeline)
    or the four named presets (free / budget / speed / premium).
    """
    cross_site = _cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    protection = None
    try:
        from orchestrator import system_protection as _sp
        from orchestrator import active_configuration as ac
        config_path = ac._config_path(name)
        selectors = [
            _sp.path_selector(config_path),
            _sp.path_selector(ac.ACTIVE_POINTER_PATH),
        ]
        pre_state = [
            _sp.capture_path_identity(config_path),
            _sp.capture_path_identity(ac.ACTIVE_POINTER_PATH),
        ]
        protection = _sp.authorize_server_action(
            "model_profile_delete", selectors=selectors,
            params={"name": name}, pre_state=pre_state,
        )
        with _sp.protected_effect(protection):
            ac.delete_configuration(name)
        _sp.complete_execution(
            protection, ok=True, result={"deleted": name},
            post_state=[
                _sp.capture_path_identity(config_path),
                _sp.capture_path_identity(ac.ACTIVE_POINTER_PATH),
            ],
        )
        return _json_response({"deleted": name})
    except (ValueError, FileNotFoundError) as exc:
        return _json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        try:
            from orchestrator import system_protection as _sp
            if isinstance(exc, _sp.SystemProtectionError):
                return _system_protection_error_response(exc)
            if protection is not None:
                _sp.complete_execution(
                    protection, ok=False, result={"error": type(exc).__name__},
                    post_state=[
                        _sp.capture_path_identity(config_path),
                        _sp.capture_path_identity(ac.ACTIVE_POINTER_PATH),
                    ],
                )
        except Exception as receipt_error:
            return _system_protection_error_response(receipt_error)
        return _json_response({"error": f"delete-failed: {exc}"}, status=500)


@app.route("/api/configurations/active", methods=["GET"])
def configurations_active_get():
    """Return the active configuration name + its toggle state.

    Backs the Models pane's header strip. The active configuration is
    the one Router.run_pipeline() falls back to when no per-request
    config_name is specified. Toggles live ON the configuration file;
    defaults are inferred from cells when the toggle block is missing.
    """
    try:
        from orchestrator import active_configuration as ac
        name = ac.get_active_name()
        try:
            toggles = ac.get_toggles(name)
        except FileNotFoundError:
            # Pointer references a configuration that no longer exists.
            # Report it so the UI can surface a "configuration missing"
            # state and let the user pick a valid one.
            return _json_response({
                "name": name,
                "missing": True,
                "toggles": {"adversarial_diversity": False, "vision_only": False,
                            "min_context_1m": False},
            })
    except Exception as exc:
        return _json_response({"error": f"active-config-read-failed: {exc}"},
                              status=500)
    return _json_response({
        "name": name,
        "missing": False,
        "toggles": toggles,
    })


@app.route("/api/configurations/active", methods=["POST"])
def configurations_active_set():
    """Set the active configuration. Body: ``{"name": "<config-name>"}``.

    Validates the name resolves to an existing configuration file
    before writing the pointer — prevents pointing dispatch at a
    nonexistent config.
    """
    try:
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        from orchestrator import active_configuration as ac
        ac.set_active_name(name)
        toggles = ac.get_toggles(name)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        return _json_response({"error": f"active-config-set-failed: {exc}"},
                              status=500)
    return _json_response({"name": name, "toggles": toggles, "missing": False})


@app.route("/api/configurations/active/toggles", methods=["POST"])
def configurations_active_toggles():
    """Update Adversarial Diversity / Vision-capable / 1M-context toggles.

    The toggles ALWAYS update the global preset state and re-bake
    all four presets — the user's mental model is "these toggles
    apply to my presets" regardless of what's currently active. When
    the active configuration is a custom, the active custom ALSO
    gets its per-config toggle state updated so the in-card display
    stays in sync.

    Body: ``{"adversarial_diversity": bool, "vision_only": bool,
    "min_context_1m": bool}``; any key may be omitted to leave that
    toggle unchanged. ``min_context_1m`` re-bakes the presets so every
    slot picks ~1M-context models (with graceful per-slot degrade).
    The set_preset_toggles / set_toggles helpers whitelist the accepted
    keys, so unknown keys in the body are ignored.
    """
    try:
        body = request.get_json(silent=True) or {}
        from orchestrator import active_configuration as ac

        # Always update global preset state + rebake all four
        # presets so the toggle's effect is visible on the preset
        # cards regardless of which configuration is active.
        ac.set_preset_toggles(body)
        ac.bake_missing_presets(force=True)
        global_toggles = ac.get_preset_toggles()

        # If the active config is anything OTHER than a canonical
        # preset file (free/budget/speed/premium), also write its
        # per-config toggle state so the in-card display stays in
        # sync. We discriminate by FILE NAME, not preset_lineage —
        # legacy configs (like user-pipeline-auto) may claim
        # lineage=budget but have their own filename, so the bake
        # to budget.json wouldn't reach them.
        name = ac.get_active_name()
        per_config_updated = False
        if name not in ac.PRESET_ORDER:
            try:
                ac.set_toggles(name, body)
                per_config_updated = True
            except FileNotFoundError:
                pass  # active points to nothing — skip silently

        # Re-baking writes named profiles after the inventory-triggered Router
        # reload. Invalidate again only after every preset/custom write so the
        # next dispatch cannot reuse a stale named-profile cache entry.
        _reload_pipeline_router_after_config_change()

        return _json_response({
            "name": name,
            "toggles": global_toggles,
            "rebaked": list(ac.PRESET_ORDER),
            "per_config_updated": per_config_updated,
        })
    except Exception as exc:
        return _json_response({"error": f"toggle-set-failed: {exc}"},
                              status=500)


@app.route("/api/model-registry/picks", methods=["GET"])
def model_registry_picks():
    """Return the PICK set — models the system endorses as winners.

    A model earns the PICK badge when it appears as a primary or
    fallback in any of the auto-populated preset configurations under
    ``config/configurations/``. The UI shows a green ``PICK`` chip on
    each such row in the Models pane inventory so users can see at a
    glance which models the recommendation engine considers worth
    picking — across any of the four presets.

    On fresh installs (before the registry refresh has baked all four
    preset files), the PICK set is smaller than its eventual ~40-60
    models. The refresh trigger (Chunk 10 step 14) handles backfill.

    Always returns 200 — empty payload when no configurations exist.
    """
    try:
        from orchestrator import model_registry as mr
        result = mr.compute_picks()
    except Exception as exc:
        return _json_response({
            "error": f"picks-compute-failed: {exc}",
            "picks": [],
            "by_model": {},
            "configurations_scanned": [],
        }, status=500)
    return _json_response(result)


def _run_refresh_step(summary: dict, prefix: str, script_name: str,
                      timeout: int) -> bool:
    """Run one fail-soft subprocess step of the registry-refresh chain,
    recording ``<prefix>_ok`` / ``<prefix>_returncode`` /
    ``<prefix>_stdout_tail`` / ``<prefix>_stderr_tail`` (or
    ``<prefix>_warning``) on the summary. Returns the step's success so
    callers can chain data-dependent steps."""
    import subprocess
    script = os.path.join(WORKSPACE, "scripts", script_name)
    try:
        if not os.path.exists(script):
            raise RuntimeError(f"script not found at {script}")
        result = subprocess.run(
            [sys.executable, script],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=timeout,
            env=_model_refresh_env(),
        )
        summary[f"{prefix}_ok"] = (result.returncode == 0)
        summary[f"{prefix}_returncode"] = result.returncode
        summary[f"{prefix}_stdout_tail"] = (result.stdout or "").strip().split("\n")[-6:]
        if result.returncode != 0:
            summary[f"{prefix}_stderr_tail"] = (result.stderr or "").strip().split("\n")[-4:]
    except subprocess.TimeoutExpired:
        summary[f"{prefix}_ok"] = False
        summary[f"{prefix}_warning"] = f"{script_name} exceeded the {timeout}s timeout."
    except Exception as exc:
        summary[f"{prefix}_ok"] = False
        summary[f"{prefix}_warning"] = f"{script_name} failed: {exc}"
    return bool(summary.get(f"{prefix}_ok"))


@app.route("/api/model-registry/refresh", methods=["POST"])
def model_registry_refresh():
    """Trigger a registry sync (no-probe) and reload the in-process cache.

    Fires ``scripts/sync_model_registry.py sync --no-probe``: 4 HTTP
    fetches (OpenRouter + LiteLLM + Chatbot Arena + AA's public /models
    page), no tokens, ~15-30s wall-time. The empirical-probe layer is
    explicitly NOT triggered here — it stays a maintainer action because
    it costs API tokens and can take 5-10 minutes.

    TTL guard: if the registry was refreshed within
    ``_REGISTRY_REFRESH_TTL_SECONDS`` seconds, returns the cached result
    immediately instead of re-syncing. Multiple pane opens in quick
    succession therefore cost zero HTTP fetches.

    Concurrency: one sync at a time. Concurrent requests during an
    in-flight sync return ``{"in_progress": true}`` immediately rather
    than queueing.
    """
    now = time.time()
    with _registry_refresh_lock:
        age = now - _registry_refresh_state["last_refresh_at"]
        if _registry_refresh_state["in_progress"]:
            return _json_response({
                "status": "in_progress",
                "message": "A registry refresh is already running.",
            })
        if age < _REGISTRY_REFRESH_TTL_SECONDS and _registry_refresh_state["last_result"]:
            return _json_response({
                "status": "cached",
                "ttl_remaining_seconds": int(_REGISTRY_REFRESH_TTL_SECONDS - age),
                "last_refresh_at": _registry_refresh_state["last_refresh_at"],
                "last_result": _registry_refresh_state["last_result"],
            })
        _registry_refresh_state["in_progress"] = True

    try:
        import subprocess
        script = os.path.join(WORKSPACE, "scripts", "sync_model_registry.py")
        if not os.path.exists(script):
            raise RuntimeError(f"sync script not found at {script}")
        # subprocess.run is intentionally synchronous; the UI shows a
        # spinner during the ~15-30s wall time. A future enhancement
        # could run this async + poll, but the simpler synchronous
        # path is fine for our latency budget.
        result = subprocess.run(
            [sys.executable, script, "sync", "--no-probe"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=120,
            env=_model_refresh_env(),
        )
        ok = (result.returncode == 0)
        summary = {
            "ok": ok,
            "returncode": result.returncode,
            "stdout_tail": (result.stdout or "").strip().split("\n")[-8:],
            "stderr_tail": (result.stderr or "").strip().split("\n")[-4:] if not ok else [],
        }
        # Rebuild the model catalog from the freshly-synced registry. The
        # catalog (config/model-catalog.json) is the list the preset
        # autopicker selects from; it enriches off the registry, so it must
        # rebuild AFTER the sync or the two drift apart — a stale catalog
        # injects models the registry has since dropped, which get picked
        # into presets and then flagged DEPRECATED. Both refresh paths (the
        # manual ↻ button and the 24h auto-refresh) POST here, so coupling
        # the rebuild in keeps catalog and registry in lockstep no matter
        # how the refresh was triggered. Fail-soft: a catalog failure does
        # NOT void the registry sync (and the autopicker's registry-presence
        # filter still guards picks until the next successful rebuild).
        if ok:
            if _run_refresh_step(summary, "catalog", "refresh-catalog.py", 120):
                # Vendor-catalogue-authoritative build (default on): fetch
                # each keyed vendor's own /models and write the authoritative
                # registry that both the endpoint sync (below) and the picker
                # read. Must run after the catalog rebuild (it reads the
                # OpenRouter+AA registry) and BEFORE the endpoint sync (which
                # consumes its output). Gated so a flag-off install skips it.
                try:
                    from orchestrator import vendor_catalog_registry as _vcr_refresh
                    _va_on = _vcr_refresh.enabled()
                except Exception:
                    _va_on = False
                if _va_on:
                    _run_refresh_step(
                        summary, "vendor_authoritative",
                        "build_vendor_authoritative_registry.py", 120)
                # Register endpoints for every catalog model so the router
                # can dispatch them (direct vendor API when the key exists,
                # else OpenRouter). Runs after the catalog rebuild because it
                # reads the catalog; kept synchronous because the pane's
                # immediate re-fetch paints DIRECT chips from the routing-config
                # this writes.
                _run_refresh_step(
                    summary, "endpoints", "sync_endpoints_from_catalog.py", 60)
                # De-duplicate to one canonical endpoint per model. sync_endpoints
                # re-mints legacy/OpenRouter-form duplicates each run; this
                # collapses them to the native canonical and repoints references
                # (idempotent — a no-op once clean), so the cleanup is durable
                # rather than reverted on the next refresh.
                _run_refresh_step(
                    summary, "dedupe", "dedupe_routing_endpoints.py", 60)
        # Force the in-process reader to re-read the new file
        try:
            from orchestrator import model_registry as mr
            mr.reload()
            summary["stats"] = mr.stats()
        except Exception as exc:
            summary["reload_warning"] = str(exc)
        try:
            from orchestrator import active_configuration as ac
            summary["presets_rebaked"] = ac.bake_missing_presets(force=True)
        except Exception as exc:
            summary["preset_rebake_warning"] = str(exc)
        try:
            summary["router_reloaded"] = _reload_pipeline_router_after_config_change()
        except Exception as exc:
            summary["router_reload_warning"] = str(exc)
        # Kick the reachability probe in the background (stale + unprobed
        # models only — the probe's default selection). Auto-pick requires
        # a positive probe verdict since 2026-06-11, so refreshes must
        # keep verdicts current or newly listed models would never become
        # pick-eligible. Non-blocking; the pane polls reach/status.
        if ok:
            try:
                summary["reach_probe"] = _spawn_reach_probe()
            except Exception as reach_exc:
                summary["reach_probe"] = {"status": "error", "message": str(reach_exc)}
        with _registry_refresh_lock:
            _registry_refresh_state["last_refresh_at"] = time.time()
            _registry_refresh_state["last_result"] = summary
            _registry_refresh_state["in_progress"] = False
        return _json_response({
            "status": "ok" if ok else "sync_failed",
            **summary,
        })
    except subprocess.TimeoutExpired:
        with _registry_refresh_lock:
            _registry_refresh_state["in_progress"] = False
        return _json_response({
            "status": "timeout",
            "message": "Registry sync exceeded the 120s timeout.",
        }, status=504)
    except Exception as exc:
        with _registry_refresh_lock:
            _registry_refresh_state["in_progress"] = False
        return _json_response({
            "status": "error",
            "message": str(exc),
        }, status=500)


@app.route("/api/model-registry/reach/start", methods=["POST"])
def model_registry_reach_start():
    """Kick off a reachability probe against every chat model.

    The probe sends a 16-token completion to each chat model and
    classifies the response by HTTP status (200 / 429 / 404 / 410 /
    400 / 5xx). Costs a few cents of OpenRouter tokens and takes
    roughly 15 minutes against the full 358-chat-model catalog.

    Runs in a background thread so the request returns immediately
    with status='started'. The UI polls ``/api/model-registry/reach/
    status`` for progress and final results. A second start request
    while a probe is in flight returns status='in_progress' with no
    new spawn.

    Body (all optional):
      ``revalidate``  (bool, default False) — re-probe every chat model
                      even if a recent verdict exists.
      ``only_unknown`` (bool, default False) — only probe models whose
                      last verdict was null/inconclusive.
      ``stale_days``  (int, default 7) — re-probe models older than this
                      many days.
    """
    body = request.get_json(silent=True) or {}
    return _json_response(_spawn_reach_probe(
        revalidate=bool(body.get("revalidate", False)),
        only_unknown=bool(body.get("only_unknown", False)),
        stale_days=int(body.get("stale_days", 7)),
    ))


def _spawn_reach_probe(revalidate: bool = False, only_unknown: bool = False,
                       stale_days: int = 7) -> dict:
    """Spawn the background reachability probe (shared by the manual
    ``/api/model-registry/reach/start`` route and the automatic kick at
    the end of every registry refresh). Returns the status dict the
    route serializes: ``started`` on spawn, ``in_progress`` when a probe
    is already running (no second spawn)."""
    import subprocess  # function-local by file convention; the closure
    # below needs it bound here — before this refactor the route body
    # never imported it, so every probe spawn died on a NameError that
    # the blanket except swallowed into last_summary.
    with _reach_probe_lock:
        if _reach_probe_state["in_progress"]:
            return {
                "status": "in_progress",
                "started_at": _reach_probe_state["started_at"],
                "current_index": _reach_probe_state["current_index"],
                "total": _reach_probe_state["total"],
            }
        _reach_probe_state["in_progress"] = True
        _reach_probe_state["started_at"] = time.time()
        _reach_probe_state["completed_at"] = 0.0
        _reach_probe_state["current_index"] = 0
        _reach_probe_state["total"] = 0
        _reach_probe_state["current_model"] = ""
        _reach_probe_state["last_summary"] = None

    def _run_in_background():
        try:
            script = os.path.join(WORKSPACE, "scripts", "sync_model_registry.py")
            cmd = [sys.executable, script, "reach"]
            if revalidate:
                cmd.append("--revalidate")
            if only_unknown:
                cmd.append("--only-unknown")
            cmd += ["--stale-days", str(stale_days)]
            # Stream stdout so we can update progress in real time.
            proc = subprocess.Popen(
                cmd, cwd=WORKSPACE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                bufsize=1,
                env=_model_refresh_env(),
            )
            reachable = rate_limited = unreachable = inconclusive = 0
            for line in proc.stdout:
                line = line.rstrip()
                # Parse "[reach] N/M model-id → verdict" lines for progress.
                # See sync_model_registry.py::_run_reach_probe for the format.
                m = re.match(r"\[reach\] (\d+)/(\d+) (\S+)\s+→\s+(.+)$", line)
                if m:
                    idx = int(m.group(1)); total = int(m.group(2))
                    mid = m.group(3); verdict = m.group(4)
                    with _reach_probe_lock:
                        _reach_probe_state["current_index"] = idx
                        _reach_probe_state["total"] = total
                        _reach_probe_state["current_model"] = mid
                    if "rate-limited" in verdict:
                        rate_limited += 1
                    elif "reachable" in verdict:
                        reachable += 1
                    elif "✗" in verdict:
                        unreachable += 1
                    else:
                        inconclusive += 1
            proc.wait()
            # Reload the in-process registry cache so chips update without
            # a separate refresh.
            try:
                from orchestrator import model_registry as mr
                mr.reload()
            except Exception:
                pass
            # Self-heal the auto-presets: the strict pick gate means fresh
            # verdicts change eligibility, and any bake that ran mid-probe
            # picked from a partial pool. Re-bake only when this probe
            # actually produced verdicts.
            try:
                if proc.returncode == 0 and (reachable + rate_limited
                                             + unreachable + inconclusive) > 0:
                    from orchestrator import active_configuration as ac
                    ac.bake_missing_presets(force=True)
            except Exception:
                pass
            with _reach_probe_lock:
                _reach_probe_state["in_progress"] = False
                _reach_probe_state["completed_at"] = time.time()
                _reach_probe_state["last_summary"] = {
                    "reachable": reachable,
                    "rate_limited": rate_limited,
                    "unreachable": unreachable,
                    "inconclusive": inconclusive,
                    "returncode": proc.returncode,
                }
        except Exception as exc:
            with _reach_probe_lock:
                _reach_probe_state["in_progress"] = False
                _reach_probe_state["completed_at"] = time.time()
                _reach_probe_state["last_summary"] = {"error": str(exc)}

    threading.Thread(target=_run_in_background, daemon=True).start()
    return {"status": "started"}


@app.route("/api/model-registry/reach/status", methods=["GET"])
def model_registry_reach_status():
    """Return the current reach-probe progress / last result."""
    with _reach_probe_lock:
        return _json_response(dict(_reach_probe_state))


# ── Routing Configuration API ─────────────────────────────────────────────


def _load_routing_config():
    try:
        with open(_routing_config_path()) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_routing_config(cfg):
    with open(_routing_config_write_path(), "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def _reload_pipeline_router_after_config_change() -> bool:
    """Invalidate the singleton ``boot._router_instance`` so the next
    pipeline run picks up the just-saved routing-config.json.

    The V3 Settings → Models panel autosaves on every change, but
    boot.py's Router is a process-lifetime singleton that snapshots
    the config at first call. Without this hook, panel changes are
    deferred-until-restart even though the file on disk is up to date.

    Returns True on success, False on any failure (logged server-side).
    Best-effort — failure does not block the save.
    """
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        from boot import reload_router as _reload_router
        return bool(_reload_router())
    except Exception as exc:
        print(f"[routing-config] router reload failed (config persisted; "
              f"restart server to pick up changes): {exc}")
        return False


@app.route("/config/routing/slots")
def routing_slots_get():
    """Return just the capability-slots block of routing-config.json.

    Consumed by the V3 Settings → Visual tab (OraVisualSlotsPane),
    which only needs the slots block — not the full routing config.

    ``defaults`` carries the SEED config's per-slot chains so the pane
    can label what an empty slot actually does: since 2026-07-01 the
    capability registry materializes seed defaults into all-empty slots
    at load time, so "(no preference)" is really "the shipped default
    chain", and the pane should say which one.
    """
    cfg = _load_routing_config()
    payload = {"slots": cfg.get("slots", {})}
    try:
        with open(rp.seed_path("config", "routing-config.json")) as f:
            _seed_slots = (json.load(f) or {}).get("slots") or {}
        payload["defaults"] = {
            name: {"preferred": c.get("preferred"),
                   "fallback": c.get("fallback") or []}
            for name, c in _seed_slots.items()
            if isinstance(c, dict) and (c.get("preferred") or c.get("fallback"))
        }
    except Exception:
        payload["defaults"] = {}
    return json.dumps(payload)


@app.route("/config/routing/slots", methods=["POST"])
def routing_slots_post():
    """Per-slot merge update for the capability-slots block.

    Body: ``{"slots": {"<slot_name>": {"preferred": ..., "fallback": [...]}}}``

    Unlike the whole-block ``/config/routing`` POST, this merges each
    named slot's fields into the existing slot dict, so a pane that
    edits only ``image_generates`` can never clobber the other slots
    or strip the ``_note`` annotations routing-config.json carries.
    Underscore-prefixed keys are rejected from the client patch for
    the same reason.
    """
    data = request.get_json(force=True)
    updates = data.get("slots")
    if not isinstance(updates, dict):
        return json.dumps({"ok": False, "error": "slots must be an object"}), 400
    cfg = _load_routing_config()
    slots = cfg.setdefault("slots", {})
    for slot_name, patch in updates.items():
        if not isinstance(patch, dict):
            return json.dumps(
                {"ok": False,
                 "error": f"slot {slot_name!r} patch must be an object"}), 400
        current = slots.setdefault(slot_name, {})
        for key, value in patch.items():
            if key.startswith("_"):
                continue
            current[key] = value
    _save_routing_config(cfg)
    reloaded = _reload_pipeline_router_after_config_change()
    return json.dumps({"ok": True, "router_reloaded": reloaded})


OPENROUTER_REFRESH_SCRIPT = os.path.join(WORKSPACE, "scripts/refresh-openrouter.py")
DIRECT_API_REFRESH_SCRIPT = os.path.join(WORKSPACE, "scripts/refresh-direct-apis.py")
OPENROUTER_STALE_DAYS = 7
DIRECT_API_STALE_DAYS = 7


def _openrouter_catalog_path() -> str:
    return str(rp.overlay_path("config", "openrouter-catalog.json"))


def _direct_api_marker_path() -> str:
    return os.environ.get("ORA_DIRECT_API_REFRESH_MARKER") or str(
        rp.runtime_path("config", ".direct-api-refresh-stamp")
    )


def _refresh_direct_apis_if_stale():
    """Run the direct-API refresher if its marker file is older than
    ``DIRECT_API_STALE_DAYS`` (or missing). Best-effort: each provider
    fails independently (e.g. missing key)."""
    import time, subprocess
    marker_path = _direct_api_marker_path()
    try:
        age_days = (time.time() - os.path.getmtime(marker_path)) / 86400
        if age_days < DIRECT_API_STALE_DAYS:
            return
        print(f"[startup] Direct-API catalog age {age_days:.1f}d — refreshing.")
    except FileNotFoundError:
        print("[startup] Direct-API marker missing — refreshing.")
    except Exception:
        return

    try:
        r = subprocess.run(
            ["/opt/homebrew/bin/python3", DIRECT_API_REFRESH_SCRIPT],
            capture_output=True, text=True, timeout=120,
            env=_model_refresh_env(),
        )
        if r.returncode == 0:
            os.makedirs(os.path.dirname(marker_path), exist_ok=True)
            with open(marker_path, "w") as f:
                f.write(str(time.time()))
            print("[startup] Direct-API catalog refreshed.")
        else:
            print(f"[startup] Direct-API refresh failed: {r.stderr.strip()[:200]}")
    except Exception as e:
        print(f"[startup] Direct-API refresh exception: {e}")


def _refresh_openrouter_if_stale():
    """If the catalog is older than ``OPENROUTER_STALE_DAYS`` (or missing),
    invoke the refresh script. Called once at server startup. Best-effort:
    failures log and proceed — the existing catalog stays in place if the
    refresh fails."""
    import time
    catalog_path = _openrouter_catalog_path()
    try:
        mtime = os.path.getmtime(catalog_path)
        age_days = (time.time() - mtime) / 86400
        if age_days < OPENROUTER_STALE_DAYS:
            return
        print(f"[startup] OpenRouter catalog age {age_days:.1f}d — refreshing.")
    except FileNotFoundError:
        print("[startup] OpenRouter catalog missing — fetching.")
    except Exception:
        return  # Anything weird, leave well enough alone.

    import subprocess
    try:
        r = subprocess.run(
            ["/opt/homebrew/bin/python3", OPENROUTER_REFRESH_SCRIPT],
            capture_output=True, text=True, timeout=60,
            env=_model_refresh_env(),
        )
        if r.returncode == 0:
            print("[startup] OpenRouter catalog refreshed.")
        else:
            print(f"[startup] OpenRouter refresh failed: {r.stderr.strip()[:200]}")
    except Exception as e:
        print(f"[startup] OpenRouter refresh exception: {e}")


@app.route("/config/openrouter/catalog")
def openrouter_catalog_get():
    """Return the cached OpenRouter model catalog.

    The catalog is refreshed by ~/ora/scripts/refresh-openrouter.py.
    Returns an empty stub if the file hasn't been written yet so the
    frontend can render "no openrouter models" rather than 500-erroring.
    """
    try:
        with open(_openrouter_catalog_path()) as f:
            return json.dumps(json.load(f))
    except FileNotFoundError:
        return json.dumps({
            "fetched_at": None, "model_count": 0,
            "models": [], "by_modality": {}, "by_vendor": {},
        })
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


def _openrouter_price_suffix(pricing: dict | None) -> str:
    """Format the per-token price tag appended to an OpenRouter model's
    display name in the capability-provider picker.

    Returns "" when the catalog has no real token pricing — media models
    (video especially) bill per output second / per image through
    OpenRouter, and the public models API reports their prompt/completion
    rates as a literal 0. Rendering that as "($0.0/$0.0/M)" reads as
    "free", which is exactly wrong, so zero/absent pricing shows nothing.
    """
    p = pricing or {}
    prompt, completion = p.get("prompt"), p.get("completion")
    if not prompt and not completion:
        return ""
    return f"  (${prompt}/${completion}/M)"


@app.route("/api/capability/providers")
def capability_providers_get():
    """Return the set of providers registered (or registerable) per
    capability slot.

    Used by the Visual Capabilities settings column to populate the
    preferred-provider dropdown and the fallback list. Includes:

      * Providers actually bound on a fresh registry — these are the
        ones the user can save as preferred / fallback right now.
      * A flag on each so the UI can surface "not yet installed"
        guidance when a known provider exists but its dependencies
        aren't on the path yet (e.g., diffusers without torch).

    Response shape:
      {
        "slots": {
          "<slot_name>": [
            { "provider_id": "<id>", "available": true|false,
              "reason": "<short>" }
          ]
        }
      }
    """
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
        sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/integrations/"))
        from capability_registry import load_registry as _load_registry
        registry = _load_registry()
        # Best-effort: try registering each known image-providing
        # integration. Each is wrapped so a missing dependency on one
        # doesn't break visibility into the others.
        for module_name in ("openai_images", "stability",
                             "replicate", "openrouter_images"):
            try:
                module = __import__(module_name)
                if module_name == "replicate" and hasattr(module, "register_replicate_provider"):
                    module.register_replicate_provider(registry)
                elif hasattr(module, "register"):
                    module.register(registry)
            except Exception:
                pass
    except Exception as exc:
        return json.dumps({"error": str(exc), "slots": {}}), 503

    # Known provider IDs grouped by which integration registers them —
    # used to surface "install diffusers" / "configure API key" hints
    # for providers that are known but not currently registered.
    KNOWN_PROVIDERS = {
        "local-diffusers": ("install diffusers + torch to enable offline image generation", "local"),
        "stability":       ("set Stability API key in Settings → External APIs", "api"),
        "replicate":       ("set Replicate token in Settings → External APIs", "api"),
    }

    # Credential availability per provider. The integration modules
    # register their dispatchers regardless of whether keys exist (so
    # the user can configure them at runtime), so "registered" alone
    # over-reports availability. Here we cross-check actual credential
    # state and downgrade the dot to "not configured" when missing.
    has_stability = bool(os.environ.get("STABILITY_API_KEY") or _try_keychain_stability_key())
    has_replicate = bool(os.environ.get("REPLICATE_API_TOKEN") or _try_keychain_replicate_token())

    PROVIDER_HAS_CREDS = {
        # local-diffusers: registration itself depends on the diffusers
        # package being importable, so a registered local-diffusers is
        # always usable. Treat as always-credentialed.
        "local-diffusers": True,
        "stability":       has_stability,
        "replicate":       has_replicate,
    }

    # Look up OpenRouter catalog so the openrouter:* providers (registered
    # by the openrouter_images integration above) get friendly display
    # names + pricing in the picker. The integration registers handlers
    # for all image/video models; here we just enrich their UI presentation.
    try:
        with open(_openrouter_catalog_path()) as _f:
            _or_catalog = json.load(_f)
    except Exception:
        _or_catalog = {"by_modality": {}, "models": []}
    _or_lookup = {m["id"]: m for m in _or_catalog.get("models", [])}
    has_or_key = bool(
        os.environ.get("OPENROUTER_API_KEY")
        or (lambda: __import__("keyring").get_password("ora", "openrouter-api-key") or "")()
    )

    def _enrich_openrouter_entry(pid: str, slot: str) -> dict:
        model_id = pid.split(":", 1)[1] if ":" in pid else pid
        m = _or_lookup.get(model_id, {})
        price = _openrouter_price_suffix(m.get("pricing_per_million"))
        reason = "" if has_or_key else "set OpenRouter API key in Settings → External APIs"
        # Video gens often run minutes and cost real money — note that.
        if slot == "video_generates" and has_or_key:
            reason = "Async — submission returns immediately; generation takes 30s–10min and requires OpenRouter credits."
        return {
            "provider_id":  pid,
            "display_name": (m.get("display_name") or model_id) + price,
            "available":    has_or_key,
            "reason":       reason,
            "kind":         "api",
        }

    out = {}
    for slot_name in registry.list_slots():
        registered = set(registry.providers_for(slot_name))
        entries = []
        seen = set()
        for pid in registered:
            if pid.startswith("openrouter:"):
                entries.append(_enrich_openrouter_entry(pid, slot_name))
                seen.add(pid)
                continue
            has_creds = PROVIDER_HAS_CREDS.get(pid, True)
            reason_default = KNOWN_PROVIDERS.get(pid, ("", "unknown"))
            entries.append({
                "provider_id": pid,
                "available": has_creds,
                "reason": "" if has_creds else reason_default[0],
                "kind": reason_default[1],
            })
            seen.add(pid)
        for pid, (reason, kind) in KNOWN_PROVIDERS.items():
            if pid in seen:
                continue
            entries.append({
                "provider_id": pid,
                "available": False,
                "reason": reason,
                "kind": kind,
            })
        out[slot_name] = entries
    # vision_input is special: the image-READING backstop is a vision-capable
    # CHAT model (dispatched like any chat endpoint), not an image-gen provider,
    # so its candidates come from the model registry + routing-config endpoints
    # rather than the capability_registry's image integrations.
    try:
        out["vision_input"] = _vision_input_candidates()
    except Exception as _vi_err:
        print(f"[capability/providers] vision_input candidates skipped: {_vi_err}", flush=True)
        out.setdefault("vision_input", [])
    return json.dumps({"slots": out})


def _vision_input_candidates() -> list:
    """Vision-capable chat ENDPOINTS for the vision_input capability slot
    (Settings → Visual → Advanced routing).

    The image-reading backstop RE-RUNS the analyst's task with the image (it
    substitutes for a failed/blind analyst — it is not a captioner), so it needs
    a CAPABLE model. The list is limited to the models the system registered as
    "picks" (the union of primary/fallback ids across the baked presets/configs)
    that are vision-capable — a curated cross-section of the best vision models,
    instead of every vision endpoint. The currently configured preferred/fallback
    are always included so a saved choice never drops off; if picks can't be
    computed, falls back to the top vision endpoints by intelligence. Returns only
    endpoints the router can actually dispatch, ranked smartest-first."""
    TOP_N = 40  # fallback cap when picks are unavailable
    try:
        rc = json.loads(rp.routing_config_path().read_text())
        eps = {e.get("id"): e for e in rc.get("endpoints", []) if isinstance(e, dict)}
    except Exception:
        rc, eps = {}, {}
    _vi = (rc.get("slots") or {}).get("vision_input") or {}
    configured = set()
    if isinstance(_vi, dict):
        if isinstance(_vi.get("preferred"), str):
            configured.add(_vi["preferred"])
        configured.update(x for x in (_vi.get("fallback") or []) if isinstance(x, str))
    reg, aliases = {}, {}
    try:
        _art = json.loads(rp.vendor_authoritative_registry_path().read_text())
        reg = _art.get("models", {}) or {}
        aliases = _art.get("aliases", {}) or {}
    except Exception:
        pass
    if not reg:
        try:
            reg = json.loads(rp.model_registry_path().read_text()).get("models", {}) or {}
        except Exception:
            pass
    # The system's PICKS, resolved to NATIVE registry ids. compute_picks
    # harvests config-form ids (e.g. anthropic/claude-opus-4.5); the alias map
    # maps those to the current native id. Sourcing candidates from the native
    # registry (not the raw routing-config endpoints) keeps the list clean —
    # routing-config still carries legacy/duplicate + subscription + image-gen
    # endpoints that would otherwise double up or leak non-chat entries in.
    pick_native = set()
    try:
        from orchestrator import model_registry as _mr
        for p in (_mr.compute_picks().get("picks") or []):
            if p in reg:
                pick_native.add(p)
            elif aliases.get(p) in reg:
                pick_native.add(aliases[p])
    except Exception as _pk_err:
        print(f"[vision_input] picks unavailable ({_pk_err}); using top-by-intelligence", flush=True)

    def _vision_models(restrict):
        out = []
        for nid, r in reg.items():
            if restrict is not None and nid not in restrict:
                continue
            if r.get("vision_capable") is not True:
                continue
            if nid not in eps:               # must be a dispatchable endpoint
                continue
            intel = r.get("aa_intelligence_index")
            out.append({
                "provider_id": nid,
                "display_name": (eps[nid].get("display_name")
                                 or r.get("display_name") or nid),
                "available": True,
                "reason": "",
                "kind": "api",
                "_intel": intel if intel is not None else -1.0,
            })
        out.sort(key=lambda c: c["_intel"], reverse=True)
        return out

    configured_in_reg = {c for c in configured if c in reg}
    if pick_native:
        cands = _vision_models(pick_native | configured_in_reg)
    else:
        # No picks (compute failed) — fall back to the top vision models.
        cands = _vision_models(None)[:TOP_N]
        have = {c["provider_id"] for c in cands}
        for c in _vision_models(configured_in_reg):
            if c["provider_id"] not in have:
                cands.append(c)
    for c in cands:
        c.pop("_intel", None)
    return cands


# ── G1.34 — Output export ────────────────────────────────────────────────────

@app.route("/api/export/locations", methods=["GET"])
def api_export_locations():
    """Return (and best-effort create) the Exports/Resources boundary folders
    (§2.8) for the UI's quick-access links. ``Ora Exports/`` holds Ora-generated
    non-markdown; ``Ora Resources/`` holds external files — both siblings of the
    vault, outside it so Obsidian never indexes binaries."""
    try:
        from orchestrator import export as _export
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    try:
        dirs = _export.ensure_export_dirs()
        caps = _export.export_capabilities()
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    return _json_response({"ok": True, "capabilities": caps, **dirs})


@app.route("/api/export", methods=["POST"])
def api_export():
    """Export an output (G1.34). Body::

        {
          "scope": "current_output" | "full_conversation",
          "format": "markdown",            # docx/pdf need the bundled Pandoc
          "content": "<markdown>",         # for current_output
          "title": "<optional>",
          "conversation_id": "<for full_conversation>",
          "project": "<nexus, optional — defaults to the active project>"
        }

    Markdown is canonical (Export §1.9). ``current_output`` saves the rendered
    output as a vault markdown note — in the active project's folder when set,
    else at the vault root for Commons. ``full_conversation`` delegates to the
    existing canonical session export. ``docx`` / ``pdf`` render the output's markdown via
    Pandoc into ``~/Documents/Ora Exports/`` when Pandoc (+ a PDF engine) is
    present; otherwise they return ``deferred``."""
    try:
        from orchestrator import export as _export
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 503)
    data = request.get_json(silent=True) or {}
    scope = (data.get("scope") or "current_output").strip()
    fmt = (data.get("format") or "markdown").strip().lower()

    if fmt in _export.PANDOC_FORMATS:
        caps = _export.export_capabilities()
        if not caps.get(fmt):
            missing = "Pandoc" if not caps.get("pandoc") else "a PDF engine (e.g. Typst)"
            return _json_response(
                {"ok": False, "deferred": True,
                 "error": f"{fmt.upper()} export needs {missing} installed. "
                          "Save to Vault (Markdown) and Print work now."}, 501)
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            return _json_response({"ok": False, "error": "content is required"}, 400)
        try:
            path = _export.export_to_file(content, title=data.get("title"), fmt=fmt)
        except Exception as exc:
            return _json_response({"ok": False, "error": str(exc)}, 500)
        if path is None:
            return _json_response(
                {"ok": False, "error": f"{fmt.upper()} conversion failed."}, 500)
        return _json_response({"ok": True, "scope": "file", "format": fmt, "path": str(path)})
    if fmt not in _export.NATIVE_FORMATS:
        return _json_response({"ok": False, "error": f"unknown format {fmt!r}"}, 400)

    if scope == "full_conversation":
        conversation_id = (data.get("conversation_id") or "").strip()
        if not conversation_id:
            return _json_response({"ok": False, "error": "conversation_id required"}, 400)
        try:
            from vault_export import export_session_to_vault  # type: ignore
        except Exception as exc:
            return _json_response({"ok": False, "error": f"vault_export import failed: {exc}"}, 500)
        try:
            result = export_session_to_vault(conversation_id)
        except Exception as exc:
            return _json_response({"ok": False, "error": str(exc)}, 500)
        return _json_response({
            "ok": True, "scope": scope,
            "path": str(getattr(result, "markdown_path", "") or ""),
        })

    # current_output (default) — save one rendered output to the vault.
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        return _json_response({"ok": False, "error": "content is required"}, 400)
    # Resolve the project: explicit body value, else the active project.
    project_nexus = (data.get("project") or "").strip()
    if not project_nexus:
        try:
            from orchestrator.active_project import get_active_project
            project_nexus = get_active_project()
        except Exception as exc:
            return _json_response(
                {"ok": False, "error": f"active project resolution failed: {exc}"},
                503,
            )
    try:
        path = _export.save_output_to_vault(
            content, title=data.get("title"),
            project_nexus=project_nexus)
    except _export.ProjectExportNotFoundError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 404)
    except _export.ProjectExportMigrationRequiredError as exc:
        return _json_response(
            {"ok": False, "migration_required": True, "error": str(exc)}, 409)
    except _export.ProjectExportIdentityError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 409)
    except _export.ExportPathError as exc:
        return _json_response({"ok": False, "error": str(exc)}, 409)
    except Exception as exc:
        return _json_response({"ok": False, "error": str(exc)}, 500)
    if path is None:
        return _json_response(
            {"ok": False, "storage_available": False,
             "error": "could not write to the vault (no vault / no access)"}, 503)
    return _json_response({"ok": True, "scope": "current_output", "path": str(path)})


# ── WP-6.1 — Vault export ────────────────────────────────────────────────────

@app.route("/api/session/export", methods=["POST"])
def api_session_export():
    """Export a completed conversation as canonical Markdown + SVG sidecars.

    Request body (JSON)::

        {
          "conversation_id": "<required>",
          "session_title":   "<optional — derived from first user message otherwise>",

          # Test-only dependency injection (leave unset in production calls):
          "_vault_root":            "<override vault root>",
          "_sessions_root":         "<override ~/ora/sessions root>",
          "_raw_conversations_dir": "<override ~/Documents/conversations/raw>",
          "_node_cli":              "<override Node CLI path>"
        }

    Response::

        200 {
          "success": true,
          "markdown_path": "...",
          "sidecar_paths": ["..."],
          "sidecar_count": N,
          "warnings": [...],
          "envelope_count": N,
          "invalid_envelopes": [...]
        }
        400 {"error": "conversation_id required"}
        404 {"error": "..."}   (conversation not found)
        500 {"error": "..."}   (unexpected failure)

    The UI hook is deferred to WP-6.2; this endpoint is consumed directly by
    tests and (until WP-6.2 ships) by ``curl``.
    """
    data = request.json or {}
    conversation_id = (data.get("conversation_id") or "").strip()
    if not conversation_id:
        return json.dumps({"error": "conversation_id required"}), 400

    # Import lazily so the orchestrator module is only loaded when the
    # endpoint is actually hit.
    try:
        from vault_export import export_session_to_vault, ExportResult  # type: ignore
    except Exception as e:
        return json.dumps({"error": f"vault_export import failed: {e}"}), 500

    kwargs: dict = {}
    if data.get("session_title"):
        kwargs["session_title"] = data["session_title"]

    # Dependency-injection overrides for tests.
    if data.get("_vault_root"):
        kwargs["vault_root"] = data["_vault_root"]
    if data.get("_sessions_root"):
        kwargs["sessions_root"] = data["_sessions_root"]
    if data.get("_raw_conversations_dir"):
        kwargs["raw_conversations_dir"] = data["_raw_conversations_dir"]
    if data.get("_node_cli"):
        kwargs["node_cli"] = data["_node_cli"]

    try:
        result: ExportResult = export_session_to_vault(
            conversation_id=conversation_id,
            **kwargs,
        )
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}), 404
    except Exception as e:
        return json.dumps({"error": f"export failed: {e}"}), 500

    return json.dumps({
        "success": True,
        "markdown_path": str(result.markdown_path),
        "sidecar_paths": [str(p) for p in result.sidecar_paths],
        "sidecar_count": len(result.sidecar_paths),
        "warnings": list(result.warnings),
        "envelope_count": result.envelope_count,
        "invalid_envelopes": list(result.invalid_envelopes),
    })


# ── WP-7.6.3 — Async cancellation endpoint ────────────────────────────────
# The job-queue UI's Cancel button posts here once the user confirms the
# billing warning. We delegate to ``JobQueue.request_cancel`` which:
#   * cancels immediately if the job is still ``queued`` (nothing
#     running yet, no provider billing in flight),
#   * sets ``cancel_requested`` on ``in_progress`` jobs so the
#     provider polling thread (e.g. integrations/replicate.py
#     :_poll_thread) calls the provider's cancel endpoint at the next
#     poll tick and transitions the job to ``cancelled``.
#
# Terminal jobs return 409. Unknown jobs return 404. Either way the
# subsequent ``ora:job_status`` SSE frame is the source of truth — the
# UI keeps optimistic state until the frame arrives, then reconciles.
@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def api_job_cancel(job_id):
    from orchestrator.job_queue import (
        get_default_queue,
        JobNotFound,
        InvalidStatusTransition,
    )
    data = request.json or {}
    conversation_id = (data.get("conversation_id") or "").strip()
    if not conversation_id:
        return json.dumps({"error": "conversation_id required"}), 400
    queue = get_default_queue()
    try:
        job = queue.request_cancel(conversation_id, job_id)
    except JobNotFound:
        return json.dumps({"error": "job not found"}), 404
    except InvalidStatusTransition as exc:
        return json.dumps({"error": str(exc)}), 409
    return json.dumps({"success": True, "job": job})


# ── Oversight panels (V3 sidebar Paused + Operating) ────────────────────────

@app.route("/api/oversight/paused", methods=["GET"])
def api_oversight_paused():
    """Return the Paused queue as a list of entries for the sidebar panel.

    Each entry: id, name, queued_at, engagement, discussion_conversation_id,
    redefinition flag, project_nexus, event_type, reasoning excerpt.
    Sorted oldest-first.
    """
    try:
        from oversight_queue import list_paused
    except ImportError:
        return json.dumps({"entries": []}), 200, {"Content-Type": "application/json"}
    entries = list_paused()
    rows = []
    for e in entries:
        verdict = e.verdict or {}
        context_summary = e.context_summary or {}
        review_kind = (
            "execution_review_escalation"
            if context_summary.get("kind") == "execution_review_escalation"
            else ""
        )
        attempt_branch = ""
        if review_kind:
            candidate = context_summary.get("abandoned_attempt_branch")
            if (isinstance(candidate, str)
                    and re.fullmatch(
                        r"execution-review/escalation-[A-Za-z0-9_-]{1,180}",
                        candidate,
                    )):
                attempt_branch = candidate
        reasoning = (verdict.get("reasoning") or verdict.get("raw_output") or "").strip()
        if len(reasoning) > 600:
            reasoning = reasoning[:600] + "…"
        rows.append({
            "id": e.id,
            "name": e.name,
            "queued_at": e.queued_at,
            "engagement": e.engagement,
            "discussion_conversation_id": e.discussion_conversation_id,
            "redefinition": e.redefinition,
            "project_nexus": (e.event or {}).get("project_nexus", ""),
            "event_type": (e.event or {}).get("event_type", ""),
            "reasoning_excerpt": reasoning,
            "trace_ref": e.trace_ref,
            "trace_step": (e.event or {}).get("trace_step", ""),
            "review_kind": review_kind,
            "abandoned_attempt_branch": attempt_branch,
            "user_explanation": (
                "Ora could not independently verify this turn. It preserved an "
                "inspectable attempt reference and did not automatically merge the "
                "review branch. Review or discuss the evidence before approving."
                if review_kind else ""
            ),
        })
    return json.dumps({"entries": rows}), 200, {"Content-Type": "application/json"}


@app.route("/api/oversight/operating", methods=["GET"])
def api_oversight_operating():
    """Return Operating items aggregated from re-eval queue + active elicitations.

    Read-only in v1 — no actions. Sorted oldest-first.
    """
    try:
        from oversight_queue import list_operating
    except ImportError:
        return json.dumps({"entries": []}), 200, {"Content-Type": "application/json"}
    entries = list_operating()
    rows = [e.to_dict() for e in entries]
    return json.dumps({"entries": rows}), 200, {"Content-Type": "application/json"}


@app.route("/api/oversight/paused/<entry_id>/name", methods=["PATCH", "POST"])
def api_oversight_rename(entry_id):
    """Rename a Paused entry. Body: ``{"name": "..."}``."""
    try:
        from oversight_queue import rename
    except ImportError:
        return json.dumps({"error": "oversight_queue unavailable"}), 503
    data = request.json or {}
    new_name = (data.get("name") or "").strip()
    if not new_name:
        return json.dumps({"error": "name is required"}), 400
    if rename(entry_id, new_name):
        return json.dumps({"success": True}), 200
    return json.dumps({"error": "entry not found"}), 404


@app.route("/api/oversight/paused/<entry_id>/engagement", methods=["POST"])
def api_oversight_engagement(entry_id):
    """Update engagement state. Body: ``{"state": "seen"|"discussing"|"unseen"}``."""
    try:
        from oversight_queue import mark_engagement
    except ImportError:
        return json.dumps({"error": "oversight_queue unavailable"}), 503
    data = request.json or {}
    state = (data.get("state") or "").strip()
    if mark_engagement(entry_id, state):
        return json.dumps({"success": True}), 200
    return json.dumps({"error": "entry not found or invalid state"}), 400


@app.route("/api/oversight/paused/<entry_id>/discuss", methods=["POST"])
def api_oversight_discuss(entry_id):
    """Open (or reuse) a discussion conversation for a Paused entry.

    Returns ``{conversation_id, queue_entry_id, display_name, reused}``. The
    new conversation is seeded with one assistant message containing the
    entry's context, the initial options block, and the resolution marker.
    """
    try:
        from resolution_chain import start_resolution
    except ImportError:
        return json.dumps({"error": "resolution_chain unavailable"}), 503
    try:
        result = start_resolution(entry_id, config=load_config())
    except ValueError as exc:
        return json.dumps({"error": str(exc)}), 404
    return json.dumps(result), 200, {"Content-Type": "application/json"}


_SERVER_HOST = "localhost"
_DEFAULT_SERVER_PORTS = range(5000, 5011)


class ServerPortError(RuntimeError):
    """The requested server port is invalid or cannot be bound."""


def _port_is_available(port: int, *, socket_factory=None) -> bool:
    """Return whether a fresh IPv4 TCP socket can bind localhost:``port``."""
    if socket_factory is None:
        import socket
        socket_factory = socket.socket
    sock = socket_factory()
    try:
        sock.bind((_SERVER_HOST, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _select_server_port(environ=None, *, available=None) -> int:
    """Resolve the startup port without silently overriding explicit intent.

    An explicitly present ``PORT`` must be an ASCII-decimal TCP port and must be
    available.  A collision raises instead of scanning to a different port—the
    preview harness and browser must never believe Ora is on one port while the
    process silently chose another.  Only an absent ``PORT`` retains the legacy
    5000..5010 first-free scan.
    """
    env = os.environ if environ is None else environ
    probe = _port_is_available if available is None else available
    if "PORT" in env:
        raw = str(env.get("PORT", ""))
        if not raw or not raw.isascii() or not raw.isdecimal():
            raise ServerPortError(
                f"PORT must be an ASCII integer from 1 to 65535; got {raw!r}")
        port = int(raw, 10)
        if str(port) != raw or not 1 <= port <= 65535:
            raise ServerPortError(
                f"PORT must be a canonical integer from 1 to 65535; got {raw!r}")
        if not probe(port):
            raise ServerPortError(
                f"PORT={port} is unavailable on {_SERVER_HOST}; refusing to "
                "silently start on a different port")
        return port

    for port in _DEFAULT_SERVER_PORTS:
        if probe(port):
            return port
    raise ServerPortError(
        "no available localhost port in the default range 5000-5010")


if __name__ == "__main__":
    import argparse, signal as _signal

    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", action="store_true",
                        help="Retired by G1.10; accepted only to produce a fail-closed error")
    parser.add_argument("--oversight", action="store_true", help="Start meta-layer oversight daemon (PED watcher, corpus watcher, workflow spec sweeper, revisit sweeper)")
    args, _ = parser.parse_known_args()

    if args.scheduler:
        print("ERROR: --scheduler was retired by G1.10; use exact events or "
              "persisted one-shot deadlines", file=sys.stderr, flush=True)
        raise SystemExit(2)

    # Resolve the port before migrations, daemons, or other startup side effects.
    # PORT is the preview-harness contract; if it is present, invalid or occupied
    # means a loud stop—not an unannounced fallback that opens the wrong URL.
    try:
        port = _select_server_port()
    except ServerPortError as _port_exc:
        print(f"ERROR: {_port_exc}", file=sys.stderr, flush=True)
        raise SystemExit(2)
    if "PORT" in os.environ:
        print(f"[startup] honoring PORT={port}", flush=True)

    # Expand the active-project pointer before any worker threads or HTTP
    # requests can race it.  The normal getter is intentionally read-only;
    # startup is the safe migration boundary for adding the legacy-safe
    # ``nexus`` field alongside the canonical one.
    try:
        from orchestrator.active_project import migrate_active_project_pointer
        if migrate_active_project_pointer():
            print("[startup] active-project pointer expanded for old/new readers")
    except Exception as _active_project_exc:
        print(f"[startup] active-project pointer migration skipped: {_active_project_exc}")

    try:
        from orchestrator.project_meta import migrate_project_folder_names
        _folder_pointer_count = migrate_project_folder_names()
        if _folder_pointer_count:
            print(
                f"[startup] expanded {_folder_pointer_count} project pointer(s) "
                "with immutable folder identity"
            )
    except Exception as _project_folder_exc:
        print(f"[startup] project-folder pointer migration skipped: {_project_folder_exc}")

    # Platform check — validate engine matches this machine
    try:
        from platform_check import startup_check
        for msg in startup_check():
            print(msg)
    except ImportError:
        pass

    # Phase 2a: size the API in-flight cap from the install profile.
    # Hybrid → 8, Organization → 32, Solo → unbounded. ORA_API_POOL_SIZE
    # overrides for testing. Missing install-state.json → unbounded.
    try:
        import mlx_mutex
        _api_cap = mlx_mutex.configure_api_pool_from_install_state()
        if _api_cap is None:
            print("[server] API pool: unbounded")
        else:
            print(f"[server] API pool cap: {_api_cap} concurrent outbound calls")
    except Exception as _exc:
        print(f"[server] API pool config skipped: {_exc}")

    # Phase 2c: emit mlx-worker heartbeat every 30s for oversight_health.
    # Surfaces "this Ora process's MLX path is alive" — when the heartbeat
    # goes stale (no beat for 60s), the chat handler injects a warning
    # into responses via oversight_health.check_health.
    try:
        import mlx_mutex
        mlx_mutex.start_heartbeat(interval_seconds=30.0)
        print("[server] MLX heartbeat: started (30s interval)")
    except Exception as _exc:
        print(f"[server] MLX heartbeat skipped: {_exc}")

    # Embedding health check — verify Ollama daemon and the
    # embedding model are reachable. Cross-platform (Win/Linux/Mac).
    # Loud failure here beats silent fallback to a different embedder
    # locking the chromadb collection at the wrong dimension.
    try:
        from orchestrator.embedding import assert_embedding_ready, EMBEDDING_MODEL
        ready, messages = assert_embedding_ready()
        for msg in messages:
            print(f"[startup] embedding: {msg}")
        if not ready:
            print(
                f"[startup] embedding: WARNING — embedding pipeline degraded. "
                f"Install Ollama (https://ollama.ai), then run: "
                f"`ollama pull {EMBEDDING_MODEL}`. Indexing and search will "
                f"fail loudly until this is resolved."
            )
    except Exception as _embed_err:
        print(f"[startup] embedding: check skipped — {_embed_err}")

    config   = load_config()
    endpoint = get_endpoint(config)

    # Startup checks: index regeneration and RAG manifest freshness
    # (moved from scheduled maintenance to runtime per Runtime Principle)
    try:
        import subprocess as _sp
        _scripts = os.path.join(WORKSPACE, "scripts")

        # Index regeneration: verify modes + frameworks indexes match directories
        _gen_idx = os.path.join(_scripts, "generate-indexes.sh")
        if os.path.exists(_gen_idx):
            _modes_dir = os.path.join(WORKSPACE, "modes")
            _fw_dir = os.path.join(WORKSPACE, "frameworks", "book")
            _needs_regen = False

            _modes_idx = os.path.join(_modes_dir, "modes-index.md")
            if os.path.isdir(_modes_dir) and os.path.exists(_modes_idx):
                _mode_files = [f for f in os.listdir(_modes_dir) if f.endswith(".md") and f != "modes-index.md"]
                with open(_modes_idx, "r") as _f:
                    _idx_text = _f.read()
                for _mf in _mode_files:
                    if _mf.replace(".md", "") not in _idx_text and _mf not in _idx_text:
                        _needs_regen = True
                        break

            if not _needs_regen:
                _fw_idx = os.path.join(_fw_dir, "framework-index.md")
                if os.path.isdir(_fw_dir) and os.path.exists(_fw_idx):
                    _fw_files = [f for f in os.listdir(_fw_dir) if f.endswith(".md") and f != "framework-index.md"]
                    with open(_fw_idx, "r") as _f:
                        _idx_text = _f.read()
                    for _ff in _fw_files:
                        if _ff.replace(".md", "") not in _idx_text and _ff not in _idx_text:
                            _needs_regen = True
                            break

            if _needs_regen:
                _sp.run(["bash", _gen_idx], capture_output=True, timeout=30)
                print("[startup] Indexes regenerated (were out of sync)")
            else:
                print("[startup] Indexes: in sync")

        # RAG manifest freshness: recompile if canonical is newer than compiled
        _cfg_dir = os.path.join(WORKSPACE, "config")
        _canonical = os.path.join(_cfg_dir, "rag-manifest.md")
        _compiled = os.path.join(_cfg_dir, "rag-manifest-compiled.md")
        _compile_sh = os.path.join(_scripts, "compile-rag-manifest.sh")

        if os.path.exists(_canonical) and os.path.exists(_compile_sh):
            if not os.path.exists(_compiled) or os.path.getmtime(_canonical) > os.path.getmtime(_compiled):
                _sp.run(["bash", _compile_sh], capture_output=True, timeout=30)
                print("[startup] RAG manifest recompiled")
            else:
                print("[startup] RAG manifest: up to date")
    except Exception as _e:
        print(f"[startup] Startup checks skipped: {_e}")

    # Fire session_start hooks
    fire_hooks("session_start")

    # Initialize MCP client
    try:
        from mcp_client import get_manager as _get_mcp
        mcp_mgr = _get_mcp()
        set_mcp_client(mcp_mgr)
        mcp_count = len(getattr(mcp_mgr, 'all_tools', []))
    except Exception:
        mcp_count = 0

    # Start meta-layer oversight daemon if requested
    if args.oversight:
        try:
            from oversight_daemon import get_daemon
            oversight = get_daemon()
            oversight.start()
        except Exception as e:
            print(f"[server] Failed to start oversight daemon: {e}")

    print(f"Local AI Chat Server starting on http://{_SERVER_HOST}:{port}")
    print(f"Active endpoint: {endpoint.get('name') if endpoint else 'NONE — add an endpoint first'}")
    print(f"Tools: {'available' if TOOLS_AVAILABLE else 'UNAVAILABLE'} ({len(TOOL_REGISTRY)} registered)")
    # Surface the curated model-registry status so operators can see at
    # a glance whether capability data is fresh. Added 2026-05-20 alongside
    # the registry sync pipeline. No auto-refresh on startup — refreshing
    # is a maintainer action (cron / manual `python3 scripts/sync_model_registry.py sync`).
    try:
        from orchestrator import model_registry
        st = model_registry.stats()
        if st["loaded"]:
            print(
                f"Model registry: {st['model_count']} models "
                f"(vision: {st['vision_capable_true']} true / "
                f"{st['vision_capable_false']} false / {st['vision_capable_null']} unknown; "
                f"intelligence-scored: {st['intelligence_score_count']}) "
                f"generated_at={st.get('generated_at') or '?'}"
            )
        else:
            print("Model registry: NOT LOADED — capability flags fall back to routing-config (run `python3 scripts/sync_model_registry.py sync` to populate)")
    except Exception as e:
        print(f"Model registry: status check failed: {e}")
    if mcp_count:
        print(f"MCP tools: {mcp_count}")
    print("Press Ctrl+C to stop.")

    def _shutdown_handler(sig, frame):
        fire_hooks("session_end")
        # Clear sidebar windows on shutdown
        if SIDEBAR_WINDOW_AVAILABLE:
            clear_all_sidebar_windows()
        # V3 Phase 1.3 — incognito mode retired. Stealth conversations are
        # purged through /api/conversation/<id>/close, not on shutdown.
        try:
            from bash_execute import cleanup_all
            cleanup_all()
        except Exception:
            pass
        raise SystemExit(0)

    _signal.signal(_signal.SIGINT, _shutdown_handler)
    _signal.signal(_signal.SIGTERM, _shutdown_handler)

    # V3 Backlog 2A Chunk 1 — at startup, scan for pending submissions
    # that didn't complete (interrupted by a prior crash). Each is
    # surfaced as an errored chunk + envelope flag so the user sees it
    # in the sidebar's Errored group with the existing retry / dismiss
    # controls.
    try:
        _scan_orphaned_pending_submissions()
    except Exception as _e:
        print(f"[startup] orphan submission scan failed: {_e}")

    # Refresh the OpenRouter catalog if it's gone stale. Runs once per
    # server start; the catalog file is the source of truth for the
    # Buckets / Visual / Transcription / Speech tab pickers.
    try:
        _refresh_openrouter_if_stale()
    except Exception as _e:
        print(f"[startup] OpenRouter refresh hook failed: {_e}")
    try:
        _refresh_direct_apis_if_stale()
    except Exception as _e:
        print(f"[startup] Direct-API refresh hook failed: {_e}")

    # Auto-discover local MLX models in ~/ora/models/. A successful empty
    # scan is authoritative and clears stale inventory; an inaccessible root
    # is an explicit error and leaves the last-known-good file untouched.
    _r, _local_error = _refresh_local_model_inventory()
    if _local_error:
        print(f"[startup] local-models discovery failed: {_local_error}")
    elif _r:
        count = len(_r["discovered"])
        added = _r.get("added") or []
        removed = _r.get("removed") or []
        msg = f"[startup] local-models discovery: {count} model(s)"
        if added:
            msg += f", added {len(added)}"
        if removed:
            msg += f", removed {len(removed)}"
        print(msg)

    # Self-heal the Lucide icon-set: rebuild runtime/icon-set.json
    # whenever the toolbar / pack JSON sources have moved on. Keeps
    # newly-added toolbar icons from rendering as fallback "?" glyphs
    # without requiring a manual `node lucide-tree-shake.js` run.
    try:
        from icon_set_builder import rebuild_if_stale as _icon_rebuild
        _r = _icon_rebuild()
        if _r.get("rebuilt"):
            print(f"[startup] icon-set rebuilt: {_r['icon_count']} icons "
                  f"({_r['reason']})")
    except Exception as _e:
        print(f"[startup] icon-set rebuild failed: {_e}")

    app.run(host=_SERVER_HOST, port=port, debug=False, threaded=True)
