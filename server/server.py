#!/usr/bin/env python3
"""
Universal Chat Server — server.py
Browser-based chat interface with pipeline-integrated agentic loop.
All tiers: Tier 0 through Tier C.

Model-calling, tool execution, and pipeline logic live in orchestrator/boot.py.
This file handles Flask routing, SSE streaming, conversation persistence, and UI APIs.
"""

import os, sys, json, re, threading, time, uuid, shutil
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests

WORKSPACE         = os.path.expanduser("~/ora/")
CONVERSATIONS_DIR = os.path.expanduser("~/Documents/conversations/")
CONVERSATIONS_RAW = os.path.expanduser("~/Documents/conversations/raw/")
ENDPOINTS    = os.path.join(WORKSPACE, "config/endpoints.json")
MODELS_JSON  = os.path.join(WORKSPACE, "config/models.json")
INTERFACE_JSON = os.path.join(WORKSPACE, "config/interface.json")
LAYOUTS_DIR  = os.path.join(WORKSPACE, "config/layouts/")
THEMES_DIR   = os.path.join(WORKSPACE, "config/themes/")
MAX_ITERATIONS = 10

sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/tools/"))
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))
# Also expose ~/ora itself so package-qualified imports
# (`from orchestrator.<module>`) resolve regardless of cwd / PYTHONPATH —
# the launch.json invocation doesn't set either.
sys.path.insert(0, WORKSPACE.rstrip("/"))

# Import all shared functions from orchestrator
from boot import (
    load_boot_md, load_endpoints as load_config, get_active_endpoint as get_endpoint,
    get_slot_endpoint, call_model, parse_tool_calls, strip_tool_calls, execute_tool,
    run_step1_cleanup, run_step2_context_assembly, build_system_prompt_for_gear,
    run_gear3, run_gear4, _run_model_with_tools, run_pipeline, parse_user_command,
    route_output, TOOLS_AVAILABLE, compare_intent_with_mode,
    list_pickable_frameworks,
)
from dispatcher import (
    dispatch as dispatcher_dispatch, set_permission_mode,
    set_mcp_client, TOOL_REGISTRY, reset_consecutive,
)
from hooks import fire_hooks
from compaction import compact_context

# Phase 13-14 imports (graceful fallback if not available)
try:
    from sidebar_window import get_sidebar_window, clear_all_sidebar_windows
    SIDEBAR_WINDOW_AVAILABLE = True
except ImportError:
    SIDEBAR_WINDOW_AVAILABLE = False

# V3 Phase 1.3 — incognito module retired. Stealth/private modes are now
# carried as a ``tag`` field on the conversation envelope (Phase 1.1) with
# tag-aware close-out dispatch handling purge for stealth (Phase 1.5). The
# privacy caveat string is preserved here because it is still surfaced to
# the user when stealth or private threads route through commercial API
# endpoints — local deletion does not affect what remote providers received.
PRIVACY_CAVEAT = (
    "This mode removes the local record. Anything sent to commercial API "
    "endpoints during this session was received by the provider and is not "
    "affected by local deletion. True privacy requires local models for "
    "the conversation."
)

try:
    from resilience import get_degradation_path, format_degradation_signal, should_release_kv_cache, release_kv_cache
    RESILIENCE_AVAILABLE = True
except ImportError:
    RESILIENCE_AVAILABLE = False

try:
    from runtime_pipeline import RuntimePipeline
    RUNTIME_PIPELINE_AVAILABLE = True
except ImportError:
    RUNTIME_PIPELINE_AVAILABLE = False

try:
    from flask import Flask, request, Response, stream_with_context, send_from_directory
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


# ── Async job queue (WP-7.6) ────────────────────────────────────────────────
#
# orchestrator/job_queue.py tracks every async capability invocation
# and mirrors each job to disk. The browser polls per-conversation
# state via the hydration endpoint below; the SSE fan-out that used
# to live here was retired 2026-05-01 (browser fully migrated to
# polling 2026-04-30, no live consumers remained).

try:
    from job_queue import get_default_queue as _get_job_queue
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
    if not conv_id:
        return _json_response({"error": "conversation_id required"}, status=400)
    options = body.get("options") or {}
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
    try:
        mgr = _get_transcription_manager()
        state = mgr.get_state(tid)
        source = _transcription_source_paths.get(tid) or state.get("source_path") or ""
        full_state = mgr._jobs.get(tid)
        segments = full_state.segments if full_state else []
        plain_text = full_state.plain_text if full_state else ""
        vault_path = _write_transcript_note(
            source_media_path=source,
            plain_text=plain_text,
            segments=segments,
            language=state.get("language"),
            duration_ms=state.get("duration_ms"),
            transcription_model="whisper-large-v3-local",
        )
        _transcription_vault_paths[tid] = str(vault_path)
    except Exception as exc:
        # Vault write failures show up on the next /state poll via the
        # absence of vault_path. The transcription itself remains in
        # the 'complete' state — the user can re-run vault export
        # manually if desired.
        print(f"[server] transcription vault-write failed for {tid}: {exc}")


if _HAS_TRANSCRIPTION and _get_transcription_manager is not None:
    try:
        _get_transcription_manager().subscribe(_transcription_complete_hook)
    except Exception as _e:  # pragma: no cover — defensive
        print(f"[server] transcription manager subscribe failed: {_e}")


_TRANSCRIPTION_STAGING_DIR = os.path.expanduser("~/ora/staging/transcripts/")
os.makedirs(_TRANSCRIPTION_STAGING_DIR, exist_ok=True)


@app.route("/api/transcribe", methods=["POST"])
def transcribe_upload_and_start():
    """Multipart upload + Whisper start in one round-trip.

    Body: ``multipart/form-data`` with field ``file`` containing the
    audio/video. Optional form fields: ``language`` (ISO code or
    'auto'), ``model`` (model name without ggml- prefix).

    Returns: ``{ transcription_id, source_path }``.
    """
    if not _HAS_TRANSCRIPTION or _get_transcription_manager is None:
        return _json_response({"error": "transcription unavailable"}, status=503)
    f = request.files.get("file")
    if f is None or not f.filename:
        return _json_response({"error": "file is required"}, status=400)

    safe_name = os.path.basename(f.filename or "upload").strip() or "upload"
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    staged_path = os.path.join(_TRANSCRIPTION_STAGING_DIR,
                               f"{timestamp}-{safe_name}")
    try:
        f.save(staged_path)
    except Exception as e:
        return _json_response({"error": f"upload save failed: {e}"}, status=500)

    options = {}
    lang = (request.form.get("language") or "").strip()
    model = (request.form.get("model") or "").strip()
    # Fill in user-settings defaults when the browser didn't override.
    if not lang and _HAS_USER_SETTINGS and _user_settings is not None:
        try:
            lang = _user_settings.get_setting("whisper.default_language") or ""
        except Exception:
            lang = ""
    if not model and _HAS_USER_SETTINGS and _user_settings is not None:
        try:
            model = _user_settings.get_setting("whisper.model_size") or ""
        except Exception:
            model = ""
    if lang:
        options["language"] = lang
    if model:
        options["model"] = model

    try:
        tid = _get_transcription_manager().start(staged_path, options)
    except Exception as e:
        return _json_response({"error": f"start failed: {e}"}, status=500)
    _transcription_source_paths[tid] = staged_path

    return _json_response({"transcription_id": tid, "source_path": staged_path})


@app.route("/api/transcribe/<transcription_id>/state", methods=["GET"])
def transcribe_state(transcription_id):
    if not _HAS_TRANSCRIPTION or _get_transcription_manager is None:
        return _json_response({"error": "transcription unavailable"}, status=503)
    try:
        state = _get_transcription_manager().get_state(transcription_id)
    except KeyError:
        return _json_response({"error": "unknown transcription_id"}, status=404)
    state["vault_path"] = _transcription_vault_paths.get(transcription_id)
    return _json_response(state)


# /api/transcribe/stream retired 2026-05-01 — transcribe-input.js
# polls /api/transcribe/<id>/state since 2026-04-30.


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


_MEDIA_LIBRARY_STAGING_DIR = os.path.expanduser("~/ora/staging/media-library/")
os.makedirs(_MEDIA_LIBRARY_STAGING_DIR, exist_ok=True)


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
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    try:
        lib = _get_media_library(conversation_id)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)

    file_storage = request.files.get("file")
    if file_storage is not None and file_storage.filename:
        safe_name = os.path.basename(file_storage.filename or "upload").strip() or "upload"
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        staged_path = os.path.join(_MEDIA_LIBRARY_STAGING_DIR,
                                   f"{conversation_id}-{timestamp}-{safe_name}")
        try:
            file_storage.save(staged_path)
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
    try:
        lib = _get_media_library(conversation_id)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    if not lib.remove(entry_id):
        return _json_response({"error": "unknown entry_id"}, status=404)
    return _json_response({"removed": entry_id})


@app.route("/api/media-library/<conversation_id>/<entry_id>/rename", methods=["POST"])
def media_library_rename(conversation_id, entry_id):
    if not _HAS_MEDIA_LIBRARY or _get_media_library is None:
        return _json_response({"error": "media library unavailable"}, status=503)
    body = request.get_json(silent=True) or {}
    new_name = (body.get("new_name") or "").strip()
    if not new_name:
        return _json_response({"error": "new_name required"}, status=400)
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
    if not conversation_id:
        return _json_response({"error": "conversation_id required"}, status=400)
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return _json_response({"error": "url required"}, status=400)
    if not (url.startswith("http://") or url.startswith("https://")):
        return _json_response({"error": "url must start with http:// or https://"}, status=400)
    try:
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
# Four endpoints:
#   GET    /api/settings                  — current settings + API key status
#   POST   /api/settings                  — partial update, returns merged state
#   POST   /api/settings/api-key          — store a key in keyring
#   DELETE /api/settings/api-key/<provider> — remove a key from keyring
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
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({
        "settings": settings,
        "api_keys": api_keys,
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
    try:
        _user_settings.set_api_key(provider, value)
    except _user_settings.SettingsError as e:
        return _json_response({"error": str(e)}, status=400)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"provider": provider, "stored": True})


@app.route("/api/settings/api-key/<provider>", methods=["DELETE"])
def settings_delete_api_key(provider):
    if not _HAS_USER_SETTINGS or _user_settings is None:
        return _json_response({"error": "settings module unavailable"}, status=503)
    if not provider:
        return _json_response({"error": "provider required"}, status=400)
    try:
        # Validate the provider id before reaching keyring.
        _user_settings._provider_username(provider)
        _user_settings.delete_api_key(provider)
    except _user_settings.SettingsError as e:
        return _json_response({"error": str(e)}, status=400)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"provider": provider, "deleted": True})


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
    try:
        tl = _get_timeline(conversation_id)
        return _json_response({"available": True, "timeline": tl.load()})
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


@app.route("/api/timeline/<conversation_id>", methods=["PUT"])
def timeline_save(conversation_id):
    if not _HAS_TIMELINE or _get_timeline is None:
        return _json_response({"error": "timeline unavailable"}, status=503)
    body = request.get_json(silent=True) or {}
    try:
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


@app.route("/api/watermark/<conversation_id>/upload", methods=["POST"])
def watermark_upload(conversation_id):
    if not conversation_id:
        return _json_response({"error": "conversation_id required"}, status=400)
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
    uploads_dir = os.path.expanduser(
        f"~/ora/sessions/{conversation_id}/uploads/"
    )
    try:
        os.makedirs(uploads_dir, exist_ok=True)
    except Exception as e:
        return _json_response({"error": f"uploads dir: {e}"}, status=500)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    target_name = f"watermark-{timestamp}{ext}"
    target_path = os.path.join(uploads_dir, target_name)
    try:
        f.save(target_path)
    except Exception as e:
        return _json_response({"error": f"save failed: {e}"}, status=500)
    # Cap upload size at 10 MB after-the-fact (cheap; better than letting
    # a 1 GB image through). Files larger than that get deleted.
    try:
        if os.path.getsize(target_path) > 10 * 1024 * 1024:
            os.unlink(target_path)
            return _json_response(
                {"error": "watermark image must be under 10 MB"}, status=400
            )
    except Exception:
        pass
    return _json_response({
        "conversation_id": conversation_id,
        "image_path": target_path,
        "filename": target_name,
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

    try:
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
    )
    _HAS_PREVIEW = True
except Exception as _e:  # pragma: no cover — defensive
    _preview_proxy_state = None
    _preview_start_proxy_render = None
    _preview_extract_frame = None
    _preview_invalidate_proxy = None
    _preview_proxy_path = None
    _HAS_PREVIEW = False
    print(f"[server] preview unavailable: {_e}")


@app.route("/api/preview/<conversation_id>/state", methods=["GET"])
def preview_state(conversation_id):
    if not _HAS_PREVIEW or _preview_proxy_state is None:
        return _json_response({"available": False}, status=503)
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
    try:
        _preview_invalidate_proxy(conversation_id)
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)
    return _json_response({"invalidated": True})


# /api/render/stream retired 2026-05-01 — render-controls.js polls
# /api/render/<id>/state since 2026-04-30.


# Pipeline serialization lock. The MLX runtime on Apple Silicon segfaults
# (SIGSEGV) when several pipelines race to load or invoke models
# concurrently. Production Ora is single-user and never legitimately
# overlaps pipelines, so a single global lock is the minimum sufficient
# fix. Held for the lifetime of the SSE generator.
_pipeline_lock = threading.Lock()


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


TIER2_DIR = os.path.join(WORKSPACE, "modules/tools/tier2/")

# Domain detection: map mode names and keyword patterns to Tier 2 module files.
# Each entry is (module_filename, mode_matches, keyword_patterns).
_TIER2_MODULES = [
    ("wicked-problems.md",
     {"systems-dynamics", "strategic-interaction", "scenario-planning"},
     r"\b(wicked|intractable|stakeholder|policy|political|systemic|institution)\b"),
    ("engineering-technical.md",
     {"root-cause-analysis", "constraint-mapping", "project-mode", "structured-output"},
     r"\b(engineer|technical|software|hardware|system|debug|failure|architect|code|infra|deploy|api)\b"),
    ("political-social-analysis.md",
     {"cui-bono", "relationship-mapping", "strategic-interaction"},
     r"\b(politic|government|regulat|legislat|advocacy|institution|social|policy|voter|election)\b"),
    ("design-analysis.md",
     {"passion-exploration", "terrain-mapping"},
     r"\b(design|UX|user experience|interface|visual|product design|brand|layout|prototype)\b"),
    ("contemplative-spiritual.md",
     set(),
     r"\b(meditat|spiritual|contemplat|mindful|buddhis|awareness|consciousness|dharma|practic)\b"),
    ("problem-definition.md",
     {"deep-clarification", "dialectical-analysis", "paradigm-suspension",
      "competing-hypotheses", "steelman-construction", "synthesis",
      "decision-under-uncertainty"},
     None),  # Always included for Tier 3 or when no other domain matches
]


def _select_tier2_modules(mode: str, cleaned_prompt: str, tier: int) -> list:
    """Select relevant Tier 2 domain modules based on mode and prompt content.

    Returns list of (filename, content) tuples for modules to inject.
    """
    prompt_lower = cleaned_prompt.lower()
    selected = []
    matched_any_domain = False

    for filename, mode_set, pattern in _TIER2_MODULES:
        if filename == "problem-definition.md":
            continue  # handled as fallback below

        match = False
        if mode in mode_set:
            match = True
        elif pattern and re.search(pattern, prompt_lower):
            match = True

        if match:
            matched_any_domain = True
            path = os.path.join(TIER2_DIR, filename)
            try:
                with open(path) as f:
                    selected.append((filename, f.read()))
            except FileNotFoundError:
                pass

    # problem-definition.md: include for Tier 3 (broad exploration)
    # or when mode matches, or when no domain-specific module matched
    pd_modes = {"deep-clarification", "dialectical-analysis", "paradigm-suspension",
                "competing-hypotheses", "steelman-construction", "synthesis",
                "decision-under-uncertainty"}
    if tier >= 3 or mode in pd_modes or not matched_any_domain:
        path = os.path.join(TIER2_DIR, "problem-definition.md")
        try:
            with open(path) as f:
                selected.append(("problem-definition.md", f.read()))
        except FileNotFoundError:
            pass

    return selected


def _generate_clarification_questions(step1, config):
    """Use the breadth model to generate clarification questions for Tier 2/3.

    Loads domain-specific Tier 2 question bank modules and injects them
    into the Breadth model's context so it generates targeted questions
    rather than generic ones.
    """
    tier = step1["triage_tier"]
    cleaned = step1["cleaned_prompt"]
    mode = step1["mode"]
    corrections = step1.get("corrections_log", "")
    inferred = step1.get("inferred_items", "")

    # Select and load relevant Tier 2 modules
    modules = _select_tier2_modules(mode, cleaned, tier)

    # Build system prompt with domain question banks
    system_parts = [
        "You generate clarification questions for a user whose prompt needs "
        "clarification before the AI system can provide a high-quality response.",
        "",
        "You have access to domain-specific question banks below. Use them to "
        "generate questions that are specific and grounded in the domain, not "
        "generic. Select the most relevant questions from the banks and adapt "
        "them to the user's specific prompt. Do not copy questions verbatim — "
        "tailor them.",
    ]

    if modules:
        system_parts.append("")
        system_parts.append("=" * 60)
        system_parts.append("DOMAIN QUESTION BANKS")
        system_parts.append("=" * 60)
        for filename, content in modules:
            system_parts.append("")
            system_parts.append(content)

    system_parts.append("")
    system_parts.append("Output only the numbered questions, nothing else.")

    system_prompt = "\n".join(system_parts)

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
            f"\nUsing the domain question banks above, generate 2-3 targeted "
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
            f"\nUsing the domain question banks above, generate 3-5 broadening "
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


# In-memory vision-retry queue keyed by conversation_id. Each entry is a
# dict {image_path, attempt_reason, queued_at}. Also mirrored to disk at
# ``~/ora/sessions/<conversation_id>/vision-retry-queue.json`` so a future
# daemon (or user-triggered "retry queued visions" action) can flush it
# without depending on server process lifetime. No automatic retry here —
# that's future work.
_vision_retry_queue: dict[str, list[dict]] = {}


def _vision_retry_queue_path(conversation_id: str) -> str:
    """Resolve the per-session JSON file path for the retry queue."""
    conv_slug = re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id or "default") or "default"
    return os.path.join(VISUAL_UPLOADS_ROOT, conv_slug, "vision-retry-queue.json")


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
    path = _vision_retry_queue_path(conversation_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(entries, fh, indent=2)
    except Exception as e:
        print(f"[vision-retry-queue] persist failed for {conversation_id}: {e}")


def _run_pipeline_from_step2(step1, config, history, user_input, clarification_text="", images=None, execution_context="interactive", extra_context=None):
    """Resume pipeline from Step 2 onward, optionally enriched with clarification answers.

    ``extra_context`` (WP-3.3): an optional dict of extra keys to merge into the
    assembled ``context_pkg`` before the system prompt is built. Used by the
    multipart endpoint to thread ``spatial_representation`` + ``image_path``
    into ``build_system_prompt_for_gear`` without changing the Step 1/2 contract.
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

    context_pkg = run_step2_context_assembly(step1, config)
    # WP-3.3: thread merged-input extras (spatial_representation, image_path,
    # …) into the context package for build_system_prompt_for_gear.
    if extra_context:
        for k, v in extra_context.items():
            if v is not None:
                context_pkg[k] = v

    # WP-4.2: capability-conditional vision routing gate. If image_path is
    # present and the downstream model is text-only, select a vision-capable
    # extractor (fallback cascade); if nothing is available anywhere, flag
    # no_vision_available for WP-4.4 UX. No-op when there's no image.
    try:
        from boot import route_for_image_input
        route_for_image_input(context_pkg, requested_model=None)
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

    yield _sse("pipeline_stage", stage="step2_done", gear=gear,
               label=f"Gear {gear} selected")

    # --- Resilience check: degradation path (Phase 14) ---
    degradation_signal = ""
    if RESILIENCE_AVAILABLE and gear >= 3:
        deg_state = get_degradation_path(gear, config)
        if deg_state.fallback_gear:
            gear = deg_state.fallback_gear
            context_pkg["gear"] = gear
        degradation_signal = format_degradation_signal(deg_state)
        if degradation_signal:
            yield _sse("pipeline_stage", stage="degradation",
                        gear=gear, label=f"Degradation: level {deg_state.degradation_level}")

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

    endpoint = get_endpoint(config)

    if gear <= 2:
        system_prompt = build_system_prompt_for_gear(context_pkg, "breadth")
        ep = endpoint  # Gear 1/2: single model, use active endpoint
        if ep is None:
            yield _sse("error", text="No active endpoint configured.")
            return
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend([m for m in history if m["role"] != "system"])
        messages.append({"role": "user", "content": context_pkg["cleaned_prompt"]})
        response = _run_model_with_tools(messages, ep, images=images)

    elif gear == 3:
        response = run_gear3(context_pkg, config, history, images=images)

    elif gear >= 4:
        # KV cache release check for sequential fallback
        if RESILIENCE_AVAILABLE and should_release_kv_cache(config):
            depth_model = config.get("slot_assignments", {}).get("depth", "")
            if depth_model:
                release_kv_cache(depth_model)
        response = run_gear4(context_pkg, config, history, images=images,
                             execution_context=execution_context)

    else:
        response = _run_model_with_tools(
            [{"role": "system", "content": load_boot_md()},
             {"role": "user", "content": user_input}],
            endpoint, images=images
        )

    # Prepend degradation signal if any (never silent)
    if degradation_signal:
        response = f"{degradation_signal}\n\n---\n\n{response}"

    yield _sse("pipeline_stage", stage="complete", gear=gear,
               mode=step1["mode"], label="Pipeline complete")
    yield _sse("response", text=response)


def _pipeline_stream(user_input, history, panel_id="main", images=None, extra_context=None,
                       manual_mode_selection="", framework_selected=""):
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
    config = load_config()
    endpoint = get_endpoint(config)

    if endpoint is None:
        yield _sse("error", text="No AI endpoints configured. Add a connection or install a local model.")
        return

    # --- Framework slash-command short-circuit ---
    # Detect /framework <name> <query> and route to the layered milestone
    # executor instead of the standard step1 → step2 → gear pipeline.
    # Phase A.5 cleanup and mode classification are bypassed entirely;
    # framework invocations are explicit and the executor handles structured
    # milestone-to-milestone handoffs.
    from milestone_executor import is_framework_command, run_framework_command
    if is_framework_command(user_input):
        yield _sse("pipeline_stage", stage="framework_execution",
                   label="Running framework via layered milestone executor…")
        try:
            result_text = run_framework_command(user_input, config)
        except Exception as exc:
            yield _sse("error", text=f"Framework execution error: {exc}")
            return
        yield _sse("response", text=result_text)
        return

    # --- Step 1: Prompt Cleanup + Mode Selection ---
    yield _sse("pipeline_stage", stage="step1_cleanup", label="Cleaning prompt…")

    conv_context = ""
    if history:
        recent = [m for m in history[-6:] if m["role"] != "system"]
        conv_context = "\n".join(f"{m['role'].upper()}: {m['content'][:500]}" for m in recent)

    step1 = run_step1_cleanup(user_input, conv_context, config)
    tier = step1["triage_tier"]

    # V3 Input Handling Phase 1 — alignment-prefilter comparison. Computed
    # but not gated yet; the UI consumes the data once Phase 6 wires the
    # popup. Storing on ``step1`` so the clarification-resume path
    # (_pending_clarification) carries it along.
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

    confidence = step1.get("classification_confidence", "")
    conf_tag = f" ({confidence})" if confidence else ""
    yield _sse("pipeline_stage", stage="step1_done",
               mode=step1["mode"], triage_tier=tier,
               confidence=confidence,
               detected_invocation=step1.get("detected_invocation", ""),
               manual_mode_selection=manual_mode_selection,
               framework_selected=framework_selected,
               intent_comparison=intent_comparison,
               territory=pre_routing.get("territory"),
               dispatched_mode_id=pre_routing.get("dispatched_mode_id"),
               dispatch_announcement=pre_routing.get("dispatch_announcement"),
               completeness_gaps=pre_routing.get("completeness_gaps", []),
               pending_clarification_stage=pre_routing.get("pending_clarification_stage"),
               label=f"Mode: {step1['mode']}{conf_tag} | Tier {tier}")

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

        _pending_clarification[panel_id] = {
            "step1": step1,
            "config": config,
            "history": history,
            "user_input": user_input,
            "images": images,
            "extra_context": extra_context,
            "pre_routing_stage": pending_stage,
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
    if tier >= 2:
        yield _sse("pipeline_stage", stage="clarification_generating",
                    label="Generating clarification questions…")
        questions = _generate_clarification_questions(step1, config)

        # Store pending state for resumption
        _pending_clarification[panel_id] = {
            "step1": step1,
            "config": config,
            "history": history,
            "user_input": user_input,
            "images": images,
            "extra_context": extra_context,
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
    yield from _run_pipeline_from_step2(step1, config, history, user_input,
                                        images=images, extra_context=extra_context)


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
    elif tool_name == "schedule_task":
        return "[scheduling task…]"
    elif tool_name.startswith("mcp_"):
        parts = tool_name.split("_", 2)
        return f"[calling {parts[1] if len(parts) > 1 else 'mcp'}: {parts[2] if len(parts) > 2 else tool_name}]"
    else:
        return f"[{tool_name}…]"


def _direct_stream(user_input, history, images=None):
    """Generator: legacy single-model agentic loop with SSE tool events.
    Routes all tool calls through the unified dispatcher."""
    config   = load_config()
    endpoint = get_endpoint(config)

    if endpoint is None:
        yield _sse("error", text="No AI endpoints configured. Add a connection or install a local model.")
        return

    messages = list(history)
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": load_boot_md()})
    messages.append({"role": "user", "content": user_input})

    # Auto-approve in server mode (permission handled by UI later)
    set_permission_mode("auto-approve")

    for iteration in range(MAX_ITERATIONS):
        # Pass images only on the first call (they accompany the user's original message)
        response = call_model(messages, endpoint, images=images if iteration == 0 else None)
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            reset_consecutive()
            clean = strip_tool_calls(response)
            yield _sse("response", text=clean)
            return

        for tc in tool_calls:
            label = _tool_status_label(tc["name"], tc["parameters"])
            yield _sse("tool_status", text=label)
            result = execute_tool(tc["name"], tc["parameters"])
            yield _sse("tool_result", name=tc["name"], result=result[:500])
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"[Tool: {tc['name']}]\n{result}"})

        # Context compaction check
        ctx_window = endpoint.get("context_window", 8192)
        messages = compact_context(messages, call_model, ctx_window)

    clean = strip_tool_calls(response)
    yield _sse("response", text=clean)


def agentic_loop_stream(user_input, history, use_pipeline=True, panel_id="main", images=None, extra_context=None,
                          manual_mode_selection="", framework_selected=""):
    """Route to pipeline or direct stream based on mode.

    ``extra_context`` (WP-3.3): optional merged-input dict (spatial_representation,
    image_path) threaded into the pipeline path. Ignored by _direct_stream,
    which has no pipeline context_pkg to merge into.

    V3 Input Handling Phase 1: ``manual_mode_selection`` / ``framework_selected``
    threaded into ``_pipeline_stream`` for the alignment-prefilter comparison
    after Step 1. ``_direct_stream`` ignores them — direct mode bypasses the
    classifier entirely.
    """
    if use_pipeline:
        yield from _pipeline_stream(user_input, history, panel_id=panel_id,
                                    images=images, extra_context=extra_context,
                                    manual_mode_selection=manual_mode_selection,
                                    framework_selected=framework_selected)
    else:
        yield from _direct_stream(user_input, history, images=images)

# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(os.path.join(WORKSPACE, "server"), "index.html")

@app.route("/v2")
def index_v2():
    return send_from_directory(os.path.join(WORKSPACE, "server"), "index-v2.html")

@app.route("/v3")
def index_v3():
    return send_from_directory(os.path.join(WORKSPACE, "server"), "index-v3.html")

@app.route("/health")
def health():
    config   = load_config()
    endpoint = get_endpoint(config)
    return json.dumps({"status":"ok","endpoint": endpoint.get("name") if endpoint else None})


@app.route("/api/frameworks/picker", methods=["GET"])
def frameworks_picker():
    """V3 Phase 2 — list of pickable frameworks for the input-box framework picker.

    Returns ``{ frameworks: [ {id, display_name, display_description, category}, ... ] }``
    with one row per framework that declares both ``## Display Name`` and
    ``## Display Description`` sections. Pipeline-internal frameworks (F-* and
    Phase A) are silently excluded — they do not declare these fields.

    The picker UI consumes this directly; rows are pre-sorted by category then
    alphabetical Display Name. This endpoint is read-only and side-effect-free
    so it can be called freely on every picker open.
    """
    rows = list_pickable_frameworks()
    return json.dumps({"frameworks": rows}), 200, {"Content-Type": "application/json"}


@app.route("/api/document/process", methods=["POST"])
def document_process():
    """V3 Input Handling Phase 8 — accept a dropped/attached document.

    Body: ``multipart/form-data`` with field ``file``. Optional form
    fields: ``conversation_id``, ``tag`` (one of empty/private/stealth).

    The server stages the file under ``~/ora/staging/documents/`` and
    spawns a background worker that converts to markdown, writes the
    result as an Incubator vault note tagged ``incubating`` (and
    ``private`` when applicable) or to a stealth temp dir. Returns
    ``{processing_id, source_path}`` immediately; clients listen on
    ``/api/document/stream`` for state events.
    """
    try:
        from document_input import start as _doc_start  # type: ignore
    except Exception as e:
        return _json_response({"error": f"document module unavailable: {e}"}, status=503)

    f = request.files.get("file")
    if f is None or not f.filename:
        return _json_response({"error": "file is required"}, status=400)

    safe_name = os.path.basename(f.filename or "upload").strip() or "upload"
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    staging_dir = os.path.expanduser("~/ora/staging/documents/")
    os.makedirs(staging_dir, exist_ok=True)
    staged_path = os.path.join(staging_dir, f"{timestamp}-{safe_name}")
    try:
        f.save(staged_path)
    except Exception as e:
        return _json_response({"error": f"upload save failed: {e}"}, status=500)

    options: dict[str, str] = {"original_name": safe_name}
    conv = (request.form.get("conversation_id") or "").strip()
    if conv:
        options["conversation_id"] = conv
    tag = _normalize_tag(request.form.get("tag", ""))
    if tag:
        options["tag"] = tag

    try:
        pid = _doc_start(staged_path, options)
    except Exception as e:
        return _json_response({"error": f"start failed: {e}"}, status=500)

    return _json_response({"processing_id": pid, "source_path": staged_path})


@app.route("/api/document/<processing_id>/state", methods=["GET"])
def document_state(processing_id):
    try:
        from document_input import get_state as _doc_state  # type: ignore
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
    from document_input import subscribe as _doc_subscribe  # type: ignore
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
)


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


def _log_pending_submission(payload: dict) -> str:
    """Write a submission to ``pending/`` immediately at handler entry.

    Called BEFORE any other processing — before validation, before parsing,
    before any error path that could 400. Returns the ``submission_id``
    the caller threads into ``_invoke_pipeline`` for later finalization.

    On any I/O failure, returns an empty string and prints a warning. The
    handler should still proceed — we do not want a disk error to drop
    the user's submission entirely. (It will at least live in memory long
    enough to reach ``_save_conversation``'s raw-log append.)
    """
    submission_id = _new_submission_id()
    try:
        os.makedirs(CONVERSATIONS_PENDING, exist_ok=True)
        body = dict(payload)
        body["submission_id"] = submission_id
        body.setdefault("captured_at", datetime.utcnow().isoformat() + "Z")
        path = os.path.join(CONVERSATIONS_PENDING, f"{submission_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2, default=str)
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


def _save_conversation(user_input, ai_response, panel_id, is_new_session, tag=""):
    """
    Three steps, all inline, immediately after every response:

    1. Append prompt-response pair to the session's raw log in
       ~/Documents/conversations/raw/  (audit trail, one file per session)

    2. Write a processed chunk file to ~/Documents/conversations/
       (YAML frontmatter + contextual header + exchange body, one file per pair)
       Filename: YYYY-MM-DD_HH-MM_session-[id]_pair-[NNN]_[topic-slug].md

    3. Index the processed chunk into ChromaDB "conversations" collection
       using nomic-embed-text-v1.5 (embedding = header + user prompt only,
       per Conversation Processing Pipeline spec)

    V3 Phase 1.2: ``tag`` (one of CONVERSATION_TAGS — empty / stealth /
    private) is denormalized into the chunk's ChromaDB metadata under the
    same key, so RAG queries can filter on conversation-level mode without
    joining against conversation.json. The conversation.json envelope is
    the source of truth (set at creation, immutable per Phase 1.1); chunks
    are the denormalized cache.
    """
    os.makedirs(CONVERSATIONS_RAW, exist_ok=True)
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)

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
        session_id   = uuid.uuid4().hex[:6]
        raw_name     = f"{date_str}_{time_str}_{_slug(user_input)}.md"
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
        raw_name = f"{date_str}_{time_str}_{_slug(user_input)}.md"
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
                f"source_platform: local\n\n"
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
    chunk_name = f"{date_str}_{time_str}_{topic_slug}.md"
    chunk_path = os.path.join(CONVERSATIONS_DIR, chunk_name)
    chunk_id   = f"session-{session_id}-pair-{pair_num:03d}"

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

    chunk_content = (
        f"{frontmatter}\n"
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
        embed_text = f"{context_header}\n\n{user_input}"
        embedding  = _nomic_embed(embed_text)

        # Conversation title: first user input slice (capped). Stable across
        # turns — only set on first save; preserved otherwise.
        first_user = sess.get("first_user_input", user_input) or user_input
        conversation_title = first_user[:80].strip() if first_user else f"Session {session_id}"

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
            documents=[embed_text],
            metadatas=[meta],
        )
        if embedding is not None:
            add_kwargs["embeddings"] = [embedding]

        collection.add(**add_kwargs)
    except Exception:
        pass  # ChromaDB failure never blocks the conversation

    # V3 Backlog 2A Chunk 2 — return the chunk identifier so the caller
    # can include it in the plain-HTTP reply (file-as-source-of-truth).
    return chunk_id


def _invoke_pipeline(user_input, history, panel_id, is_main, images=None, extra_context=None, tag="",
                      manual_mode_selection="", framework_selected="", submission_id=""):
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

    Side-effects (spatial state persistence, end-of-session pipeline)
    that don't gate the reply continue to fire in daemon threads as
    before. The save itself runs synchronously inside ``_pipeline_lock``
    so the chunk_id is known before we reply.

    WP-3.3: ``extra_context`` is merged into the pipeline's context_pkg
    by ``_run_pipeline_from_step2`` — threads spatial_representation +
    image_path through to ``build_system_prompt_for_gear``.

    V3 Phase 1.1: ``tag`` carries the conversation-level mode. Honored
    on first save only.

    V3 Input Handling Phase 1: ``manual_mode_selection`` and
    ``framework_selected`` carry the user's input-box-toolbar choices.
    """
    if not user_input:
        return json.dumps({"error": "empty message"}), 400

    # Parse /direct, /save, /saveboth commands from input
    clean_input, use_pipeline, output_target = parse_user_command(user_input)

    # Sidebar window integration: use rolling window for sidebar panels
    is_sidebar = panel_id.startswith("sidebar")
    if is_sidebar and SIDEBAR_WINDOW_AVAILABLE:
        sidebar_win = get_sidebar_window(panel_id)
        history = sidebar_win.get_history()  # Override with rolling window
    else:
        sidebar_win = None

    # Mark the conversation as Pending for the duration of the run so the
    # sidebar list endpoint can group it correctly. Cleared in finally.
    _pending_conversations.add(panel_id)

    final_response = None
    active_mode    = None
    active_gear    = None
    last_stage     = None
    chunk_id       = None
    failure_summary = None
    cfg            = None
    ep             = None

    try:
        # Serialize pipeline execution. MLX concurrent model loads crash
        # the process (observed SIGSEGV during live-fire 2026-04-18);
        # single-user software so a global lock is the right guard.
        with _pipeline_lock:
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
                        framework_selected=framework_selected):
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
                    elif t == "error":
                        failure_summary = d.get("text") or d.get("error") or "pipeline error"
            except Exception as e:
                # Any uncaught pipeline exception becomes the failure summary.
                # The submission log persists as a pending file; on next
                # boot it surfaces as an errored chunk via orphan recovery.
                failure_summary = f"pipeline crashed: {e}"
                print(f"[ERROR] _invoke_pipeline pipeline crash: {e}")

            if final_response is not None:
                # Handle file output routing (e.g. /save, /saveboth)
                if output_target != "screen":
                    routed = route_output(final_response, output_target)
                    if output_target.startswith("file:"):
                        # When routed to file, the on-screen response is the
                        # file pointer text, so the chunk reflects what the
                        # user effectively saw.
                        final_response = routed

                # Sidebar window: record exchange in rolling window
                if is_sidebar and SIDEBAR_WINDOW_AVAILABLE and sidebar_win is not None:
                    sidebar_win.add_exchange(clean_input, final_response)

                is_new_session = len(history) == 0

                # Initialize session data early so the runtime pipeline thread can read it
                if is_new_session or panel_id not in _session_data:
                    _session_data[panel_id] = {
                        "raw_path": "",  # populated by _save_conversation
                        "session_id": uuid.uuid4().hex[:6],
                        "pair_count": 0,
                        "model": (ep.get("name", "unknown") if ep else "unknown"),
                        "start": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

                # V3 Backlog 2A Chunk 2 — synchronous save inside the lock
                # so the chunk_id is known before we reply. The submission
                # log finalizer + orphan-marker clear run inline; spatial
                # state and end-of-session pipeline still fire async.
                try:
                    chunk_id = _save_conversation(
                        clean_input, final_response, panel_id,
                        is_new_session, tag)
                except Exception as e:
                    failure_summary = f"_save_conversation failed: {e}"
                    print(f"[ERROR] _save_conversation: {e}")

                # Clear orphan-recovery markers if this conversation was
                # previously interrupted. A successful save means we caught
                # up; the Errored row should clear.
                if chunk_id:
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
                            data.pop("interrupted_input", None)
                            data.pop("interrupted_at", None)
                            data.pop("interrupted_submission_id", None)
                            env_path = _conversation_path(panel_id,
                                                          _DEFAULT_SESSIONS_ROOT)
                            env_path.write_text(
                                json.dumps(data, indent=2,
                                            ensure_ascii=False),
                                encoding="utf-8",
                            )
                            clear_conversation_error(panel_id)
                    except Exception as e:
                        print(f"[WARNING] orphan-marker clear failed: {e}")

                # WP-5.3 — append this turn to conversation.json so the next
                # turn can retrieve prior spatial state. Async (best-effort).
                threading.Thread(
                    target=_persist_turn_spatial_state,
                    args=(panel_id, clean_input, final_response, extra_context, tag),
                    daemon=True,
                ).start()

                if is_main:
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
                if RUNTIME_PIPELINE_AVAILABLE and not is_sidebar:
                    threading.Thread(
                        target=_run_end_of_session_pipeline,
                        args=(clean_input, final_response, panel_id, cfg, history),
                        daemon=True,
                    ).start()
    finally:
        _pending_conversations.discard(panel_id)

    # On a successful save, finalize the submission log (move pending →
    # processed). On a failure, leave the pending file in place — the
    # next boot will surface it as an orphan errored chunk.
    if chunk_id and submission_id:
        _finalize_pending_submission(submission_id)

    # ── Build the plain-HTTP reply ──────────────────────────────────────
    if final_response is not None and chunk_id:
        return json.dumps({
            "status":          "ok",
            "conversation_id": panel_id,
            "chunk_id":        chunk_id,
        })

    # Failure path. Mark the conversation envelope errored so the sidebar
    # surfaces the failure in the Errored group; the existing Backlog 2D
    # error-chunk pattern owns the failure-trace + recommendation body
    # (writing it here would duplicate the orchestrator's own error path).
    summary = failure_summary or "pipeline produced no response"
    try:
        from conversation_memory import mark_conversation_errored
        mark_conversation_errored(panel_id, summary)
    except Exception as e:
        print(f"[WARNING] mark_conversation_errored failed: {e}")

    # The submission log stays in pending/ on failure — it will be picked
    # up by the next-boot orphan scan if the server crashed, or is left
    # for manual cleanup if the pipeline returned without a response.
    return json.dumps({
        "status":          "errored",
        "conversation_id": panel_id,
        "chunk_id":        chunk_id,
        "failure_summary": summary,
    })


@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json(force=True)
    user_input = data.get("message","").strip()
    history    = data.get("history", [])
    panel_id   = data.get("panel_id", "main")
    is_main    = data.get("is_main_feed", True)
    tag        = _normalize_tag(data.get("tag", ""))
    # V3 Phase 1 — alignment-prefilter inputs. ``manual_mode_selection`` is
    # the user's picked mode from the input-box mode picker (or empty);
    # ``framework_selected`` is the user's picked framework (or empty); they
    # are mutually exclusive at the UI layer (V3 Input Handling Q3) but the
    # server treats them independently and lets ``compare_intent_with_mode``
    # apply the framework-suppresses-prefilter rule.
    manual_mode_selection = (data.get("manual_mode_selection") or "").strip()
    framework_selected    = (data.get("framework_selected") or "").strip()
    if not user_input:
        return json.dumps({"error":"empty message"}), 400

    # V3 Backlog 2A Chunk 1 — capture the submission to disk BEFORE any
    # other processing. A user input must never be lost. The pending file
    # is the recoverable record; on successful save it moves to
    # processed/, on a server crash the next boot surfaces it as an
    # errored chunk for the user to retry / dismiss.
    submission_id = _log_pending_submission({
        "endpoint":              "/chat",
        "conversation_id":       panel_id,
        "panel_id":              panel_id,
        "is_main_feed":          is_main,
        "tag":                   tag,
        "user_input":            user_input,
        "history":               history,
        "manual_mode_selection": manual_mode_selection,
        "framework_selected":    framework_selected,
        "attachments":           data.get("attachments", []),
    })

    # Process attachments: text content inlined, images passed separately
    raw_attachments = data.get("attachments", [])
    text_parts, images = _process_attachments(raw_attachments)
    if text_parts:
        user_input = user_input + "\n\n" + "\n\n".join(text_parts)

    return _invoke_pipeline(user_input, history, panel_id, is_main, images=images,
                             tag=tag,
                             manual_mode_selection=manual_mode_selection,
                             framework_selected=framework_selected,
                             submission_id=submission_id)


# ── WP-3.3: Merged visual + text input (multipart) ───────────────────────────

# Uploads for /chat/multipart land here, partitioned by conversation_id.
VISUAL_UPLOADS_ROOT = os.path.expanduser("~/ora/sessions/")


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
        conv_slug = re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id or "default") or "default"
        out_dir = os.path.join(VISUAL_UPLOADS_ROOT, conv_slug, "uploads")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_path = os.path.join(out_dir, f"{ts}-canvas-preview.png")
        with open(out_path, "wb") as f:
            f.write(raw)
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
        conv_slug = re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id or "default") or "default"
        out_dir = os.path.join(VISUAL_UPLOADS_ROOT, conv_slug, "uploads")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_path = os.path.join(out_dir, f"{ts}-{base}")
        file_storage.save(out_path)
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
    framework_selected    = (form.get("framework_selected") or "").strip()

    if not user_input:
        return json.dumps({"error": "empty message"}), 400
    if not conversation_id:
        return json.dumps({"error": "missing conversation_id"}), 400

    # Optional image upload — saved FIRST so the submission log can record
    # the path. Image binaries live separately on disk; the pending file
    # carries only the path reference, not the bytes.
    image_path = None
    file_storage = request.files.get("image")
    if file_storage is not None:
        image_path = _save_multipart_image(conversation_id, file_storage)

    # V3 Item 12 Q1 follow-up — vision-capable canvas preview bundling.
    # The browser sends a `canvas_preview_png` data URL when the canvas
    # has content; we persist it to the same uploads dir so vision-
    # capable models can read it from disk just like a user-uploaded
    # image. Text-only models ignore the file and use
    # spatial_representation instead.
    canvas_preview_path = None
    canvas_preview_data_url = (form.get("canvas_preview_png") or "").strip()
    if canvas_preview_data_url and not image_path:
        canvas_preview_path = _save_canvas_preview_png(
            conversation_id, canvas_preview_data_url,
        )

    # V3 Backlog 2A Chunk 1 — capture the submission to disk BEFORE any
    # parsing or validation that could 400. Stored values are the raw form
    # strings so a malformed spatial_representation or annotations payload
    # is still preserved in the pending file. Validation 400s call
    # _delete_pending_submission so they don't surface as orphans.
    spatial_raw     = form.get("spatial_representation", "")
    annotations_raw = form.get("annotations", "")
    history_raw_str = form.get("history", "")
    submission_id = _log_pending_submission({
        "endpoint":              "/chat/multipart",
        "conversation_id":       conversation_id,
        "panel_id":              panel_id,
        "is_main_feed":          is_main,
        "tag":                   tag,
        "user_input":            user_input,
        "history_raw":           history_raw_str,
        "manual_mode_selection": manual_mode_selection,
        "framework_selected":    framework_selected,
        "spatial_raw":           spatial_raw,
        "annotations_raw":       annotations_raw,
        "image_path":            image_path,
    })

    # Optional history as JSON string
    history = []
    if history_raw_str:
        try:
            history = json.loads(history_raw_str)
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []

    # Optional spatial_representation (JSON string) — validate before proceeding.
    spatial_rep = None
    if spatial_raw:
        try:
            spatial_rep = json.loads(spatial_raw)
        except Exception as e:
            _delete_pending_submission(submission_id)
            return json.dumps({
                "error": "invalid spatial_representation JSON",
                "detail": str(e),
            }), 400
        try:
            from visual_validator import validate_spatial_representation
            result = validate_spatial_representation(spatial_rep)
            if not result.valid:
                _delete_pending_submission(submission_id)
                return json.dumps({
                    "error": "spatial_representation failed validation",
                    "errors": [e.as_dict() for e in result.errors],
                    "warnings": [w.as_dict() for w in result.warnings],
                }), 400
        except Exception as e:
            print(f"[WARNING] spatial_representation validation error: {e}")
            # Fail-open on unexpected validator error — treat as text-only.
            spatial_rep = None

    # WP-5.2 — optional annotations (JSON string) — validate before proceeding.
    annotations_payload = None
    if annotations_raw:
        try:
            annotations_parsed = json.loads(annotations_raw)
        except Exception as e:
            _delete_pending_submission(submission_id)
            return json.dumps({
                "error": "invalid annotations JSON",
                "detail": str(e),
            }), 400
        try:
            from visual_validator import validate_annotations
            result = validate_annotations(annotations_parsed)
            if not result.valid:
                _delete_pending_submission(submission_id)
                return json.dumps({
                    "error": "annotations failed validation",
                    "errors": [e.as_dict() for e in result.errors],
                    "warnings": [w.as_dict() for w in result.warnings],
                }), 400
            # Normalize onto the wrapper shape for downstream consumption.
            if isinstance(annotations_parsed, list):
                annotations_payload = {"annotations": annotations_parsed}
            else:
                annotations_payload = annotations_parsed
        except Exception as e:
            print(f"[WARNING] annotations validation error: {e}")
            # Fail-open: treat as absent rather than blocking the user's turn.
            annotations_payload = None

    # Build extra_context threaded into the pipeline
    extra_context = {}
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
          f"prior_spatial={'yes' if extra_context.get('prior_spatial_representation') else 'no'}")

    return _invoke_pipeline(
        user_input, history, panel_id, is_main,
        images=None,  # Image flows via image_path, not the inline base64 channel.
        extra_context=extra_context or None,
        tag=tag,
        manual_mode_selection=manual_mode_selection,
        framework_selected=framework_selected,
        submission_id=submission_id,
    )


# ── WP-7.4.8: canvas save / autosave persistence ─────────────────────────────

# Canvas saves land here, partitioned by conversation_id like multipart uploads.
CANVAS_ROOT = os.path.expanduser("~/ora/sessions/")

# Filename ceiling for raster previews. PNG data URLs from a 10000×10000
# Konva stage can balloon — we cap at 8 MB to keep autosave I/O bounded.
_PREVIEW_MAX_BYTES = 8 * 1024 * 1024


def _canvas_dir(conversation_id: str) -> str:
    """Resolve the canvas directory for a conversation, creating it if needed."""
    conv_slug = re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id or "default") or "default"
    out_dir = os.path.join(CANVAS_ROOT, conv_slug, "canvas")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


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
      1. Sanitises conversation_id and writes the canvas bytes to a
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

    out_dir = _canvas_dir(conversation_id)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    canvas_name = f"{ts}.ora-canvas"
    canvas_path = os.path.join(out_dir, canvas_name)
    latest_path = os.path.join(out_dir, "latest.ora-canvas")

    try:
        with open(canvas_path, "wb") as f:
            f.write(blob)
        # latest mirror — overwrite each save so callers have a stable path.
        with open(latest_path, "wb") as f:
            f.write(blob)
    except Exception as e:
        return json.dumps({"error": "write failed", "message": str(e)}), 500

    preview_path = None
    if preview_data_url:
        png_bytes = _decode_preview_data_url(preview_data_url)
        if png_bytes is not None:
            preview_name = f"{ts}.preview.png"
            preview_path = os.path.join(out_dir, preview_name)
            try:
                with open(preview_path, "wb") as f:
                    f.write(png_bytes)
                # latest preview mirror.
                with open(os.path.join(out_dir, "latest.preview.png"), "wb") as f:
                    f.write(png_bytes)
            except Exception as e:
                # Preview is non-fatal — log and continue.
                print(f"[WARNING] canvas_save preview write failed: {e}")
                preview_path = None

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
    """V3 Input Handling Phase 9 — return the latest canvas snapshot.

    Returns the gzip-compressed bytes of ``latest.ora-canvas`` for the
    given conversation, or 404 if no canvas has been saved yet.

    Response shape::

        200 application/octet-stream  — raw gzipped canvas-state bytes
        404 application/json           — {"error": "no canvas saved"}

    Frontend callers (v3-conversation.js) decode via OraCanvasFileFormat.
    Full visual rehydration of the user-input layer requires an inverse
    of canvas-serializer.js that does not yet exist; this endpoint ships
    so the data is reachable when that work lands. Until then the
    caller can still consult the bytes (e.g. to confirm a snapshot
    exists for the conversation) without trying to reconstruct shapes.
    """
    conv_slug = re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id or "default") or "default"
    latest_path = os.path.join(CANVAS_ROOT, conv_slug, "canvas", "latest.ora-canvas")
    if not os.path.exists(latest_path):
        return json.dumps({"error": "no canvas saved"}), 404, {"Content-Type": "application/json"}
    try:
        with open(latest_path, "rb") as f:
            blob = f.read()
    except Exception as e:
        return json.dumps({"error": "read failed", "message": str(e)}), 500, {"Content-Type": "application/json"}
    return Response(blob, mimetype="application/octet-stream")


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


@app.route("/api/conversation/<conversation_id>", methods=["GET"])
def conversations_fetch(conversation_id):
    """Return the full conversation.json envelope for a conversation.

    Used by the UI when the user navigates to a conversation in the list,
    to load its messages into the output pane. Returns 404 if the
    conversation does not exist.
    """
    conversation_id = (conversation_id or "").strip()
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400

    try:
        from conversation_memory import load_conversation_json
    except Exception as e:
        return json.dumps({"error": f"load_conversation_json import failed: {e}"}), 500

    data = load_conversation_json(conversation_id)
    if data is None:
        return json.dumps({"error": "conversation not found", "conversation_id": conversation_id}), 404

    # Annotate with the in-memory pending flag so the client doesn't have to
    # cross-reference the list endpoint.
    data["pending"] = conversation_id in _pending_conversations
    return json.dumps(data)


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
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400

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

    path = mark_conversation_read(conversation_id, timestamp=ts if isinstance(ts, str) else None)
    if path is None:
        return json.dumps({"error": "conversation not found or unwriteable", "conversation_id": conversation_id}), 404

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

    The child inherits the parent's tag + message history, with
    ``parent_conversation_id`` pointing at the parent (Backlog 2C).
    Used by the Stealth and Private dropdowns' Fork option, and may
    also serve general-mode forks.

    Request body (optional):
        {
          "new_id": "<override>",            # caller-supplied id; default is
                                             # parent_id + "-fork-<ts>"
          "fork_point_chunk_id": "<id>"      # parent's chunk_id at the
                                             # fork point (Backlog 2C). Used
                                             # by pipeline ancestry walks.
        }

    Response: 200 with the new envelope, or 404 if parent is missing.
    """
    parent_id = (conversation_id or "").strip()
    if not parent_id:
        return json.dumps({"error": "conversation_id is required"}), 400

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

    fork_point_chunk_id = None
    if isinstance(body, dict):
        raw = body.get("fork_point_chunk_id")
        if isinstance(raw, str) and raw.strip():
            fork_point_chunk_id = raw.strip()

    try:
        from conversation_memory import fork_conversation
    except Exception as e:
        return json.dumps({"error": f"fork_conversation import failed: {e}"}), 500

    new_envelope = fork_conversation(
        parent_id, requested_id,
        fork_point_chunk_id=fork_point_chunk_id,
    )
    if new_envelope is None:
        return json.dumps({
            "error":           "parent conversation not found or unreadable",
            "conversation_id": parent_id,
        }), 404

    return json.dumps({
        "ok":                       True,
        "new_conversation_id":      new_envelope["conversation_id"],
        "tag":                      new_envelope.get("tag", ""),
        "parent_conversation_id":   new_envelope.get("parent_conversation_id"),
        "fork_point_chunk_id":      new_envelope.get("fork_point_chunk_id"),
        "created":                  new_envelope.get("created"),
        "forked_at":                new_envelope.get("forked_at"),
        "message_count":            len(new_envelope.get("messages") or []),
    })


# ── V3 Phase 6.1: conversation bootstrap ─────────────────────────────────────

@app.route("/api/bootstrap", methods=["POST"])
def api_bootstrap():
    """V3 Phase 6.1 — Conversation bootstrap endpoint.

    Side-channel call (NOT pipeline routing): topic → ChromaDB query across
    knowledge + conversations collections → local-fast model assembly →
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

    Privacy: queries against the conversations collection apply the
    default ``tag != "private"`` filter unless the caller is themselves in
    private mode (in which case private-tagged matches are surfaced too).
    The knowledge collection has no privacy filter — mental models are
    not personal data.
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
        cfg = load_config()
        chroma_path = cfg.get("chromadb_path", os.path.join(WORKSPACE, "chromadb/"))
        client = chromadb.PersistentClient(path=chroma_path)

        # Knowledge collection (mental models, no privacy filter).
        try:
            kn = client.get_collection("knowledge")
            kn_results = kn.query(query_texts=[topic], n_results=5)
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
            conv = client.get_collection("conversations")
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
            "summary":      f"No prior knowledge or conversations on this topic.\n\nStarting fresh on: **{topic}**",
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

    # ── Step 3: Local-fast model assembly ───────────────────────────────────
    summary_text = ""
    fallback = False
    fallback_reason = None
    try:
        cfg = load_config()
        ep = get_slot_endpoint(cfg, "sidebar")  # sidebar slot resolves the local-fast bucket
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
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400
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

    path = mark_conversation_errored(
        conversation_id,
        summary,
        timestamp=ts if isinstance(ts, str) else None,
    )
    if path is None:
        return json.dumps({"error": "conversation not found", "conversation_id": conversation_id}), 404
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
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400
    try:
        from conversation_memory import clear_conversation_error
    except Exception as e:
        return json.dumps({"error": f"clear_conversation_error import failed: {e}"}), 500
    path = clear_conversation_error(conversation_id)
    if path is None:
        return json.dumps({"error": "conversation not found", "conversation_id": conversation_id}), 404
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
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400
    try:
        from conversation_memory import load_conversation_json
    except Exception as e:
        return json.dumps({"error": f"load_conversation_json import failed: {e}"}), 500

    data = load_conversation_json(conversation_id)
    if data is None:
        return json.dumps({"error": "conversation not found", "conversation_id": conversation_id}), 404

    # V3 Backlog 2A Chunk 1 — orphan recovery: if this conversation was
    # flagged errored because the server was interrupted before the
    # pipeline could run (no save reached the envelope), the original
    # prompt lives in ``interrupted_input``. Prefer it over the last user
    # message in the envelope so retry re-submits exactly what the user
    # typed, not the prior turn's prompt.
    interrupted = data.get("interrupted_input")
    if isinstance(interrupted, str) and interrupted.strip():
        return json.dumps({
            "ok":               True,
            "conversation_id":  conversation_id,
            "last_user_prompt": interrupted,
            "tag":              data.get("tag", "") or "",
            "source":           "interrupted_input",
        })

    messages = data.get("messages") or []
    last_user = None
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            last_user = m["content"]
            break
    if not last_user:
        return json.dumps({"error": "no user prompt to retry", "conversation_id": conversation_id}), 404
    return json.dumps({
        "ok":               True,
        "conversation_id":  conversation_id,
        "last_user_prompt": last_user,
        "tag":              data.get("tag", "") or "",
        "source":           "messages",
    })


# ── V3 Phase 1.5: conversation close-out dispatch ────────────────────────────

@app.route("/api/conversation/<conversation_id>/close", methods=["POST"])
def conversation_close(conversation_id):
    """Dispatch close-out for a conversation based on its tag.

    The dispatch reads the conversation's ``tag`` from conversation.json
    (set immutably at creation per V3 Phase 1.1) and:

    * empty (standard) → 200 with action "noop"
    * ``private`` → 200 with action "noop" (UI removes from active list)
    * ``stealth`` → full purge (session dir, chunks, raw log, ChromaDB
      records); 200 with action "purge" and the deletion summary

    Per-layer failures during purge are collected and returned in
    ``errors`` so the UI can surface them — the endpoint never aborts on
    a partial failure.

    Vault artifacts under ``~/Documents/vault/Sessions/`` are not
    auto-purged; vault export is explicit and out-of-band.
    """
    conversation_id = (conversation_id or "").strip()
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400

    try:
        from orchestrator.conversation_closeout import close_conversation
    except Exception as e:
        return json.dumps({"error": f"close_conversation import failed: {e}"}), 500

    try:
        result = close_conversation(conversation_id)
    except Exception as e:
        return json.dumps({
            "error": f"close_conversation failed: {e}",
            "conversation_id": conversation_id,
        }), 500

    return json.dumps(result), 200


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
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400

    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}
    new_name = body.get("display_name") if isinstance(body, dict) else None
    if not isinstance(new_name, str):
        new_name = ""

    try:
        from conversation_memory import set_display_name, load_conversation_json
    except Exception as e:
        return json.dumps({"error": f"set_display_name import failed: {e}"}), 500

    path = set_display_name(conversation_id, new_name)
    if path is None:
        return json.dumps({
            "error": "conversation not found or unwriteable",
            "conversation_id": conversation_id,
        }), 404

    data = load_conversation_json(conversation_id) or {}
    return json.dumps({
        "ok": True,
        "conversation_id": conversation_id,
        "display_name": data.get("display_name", ""),
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
    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400

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

    if isinstance(body, dict) and "pinned" in body:
        target_pinned = bool(body.get("pinned"))
    else:
        existing = load_conversation_json(conversation_id) or {}
        target_pinned = not bool(existing.get("pinned"))

    path = set_conversation_pinned(conversation_id, target_pinned)
    if path is None:
        return json.dumps({
            "error": "conversation not found or unwriteable",
            "conversation_id": conversation_id,
        }), 404

    return json.dumps({
        "ok": True,
        "conversation_id": conversation_id,
        "pinned": target_pinned,
    })


# ── V3 Backlog 6: right-side scratchpad ─────────────────────────────────────

@app.route("/api/scratchpad", methods=["POST"])
def api_scratchpad():
    """Plain-HTTP scratchpad endpoint for the right-column Q&A.

    V3 Backlog 2A Chunk 4 (2026-04-30) — migrated from SSE streaming. The
    user does not see model thinking; the answer is pushed to the right-
    column output as soon as it's ready. Spec item 6 — local-fast model,
    no save, no ChromaDB write, no server-side history. Each request is
    independent; the client maintains a short autopurging history of the
    last ~10 entries in DOM.

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

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"}), 400

    try:
        cfg = load_config()
        ep = get_slot_endpoint(cfg, "sidebar")
        if not ep:
            return json.dumps({"error": "local-fast endpoint not configured"})
        from boot import call_local_endpoint
        answer = call_local_endpoint(
            [{"role": "user", "content": prompt}],
            ep,
        )
        if isinstance(answer, str) and answer.startswith("[Error"):
            return json.dumps({"error": answer})
        return json.dumps({"answer": answer or ""})
    except Exception as e:
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

    if not conversation_id:
        return json.dumps({"error": "conversation_id is required"}), 400
    if not image_path:
        return json.dumps({"error": "image_path is required"}), 400
    if attempt_reason not in ("no_vision_available", "extraction_failed"):
        return json.dumps({
            "error": "attempt_reason must be 'no_vision_available' or 'extraction_failed'",
            "received": attempt_reason,
        }), 400

    entry = {
        "conversation_id": conversation_id,
        "image_path": image_path,
        "attempt_reason": attempt_reason,
        "queued_at": datetime.now().isoformat(),
    }

    # Merge the disk queue with the in-memory queue (disk wins on restart).
    # Using the disk-resident list as the source of truth avoids dropping
    # entries persisted by a prior server process.
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

def _persist_turn_spatial_state(panel_id, user_input, ai_response, extra_context, tag=""):
    """WP-5.3 — append this turn to conversation.json so subsequent turns
    can retrieve the prior spatial state.

    Each turn's ``spatial_representation``, ``annotations``, and
    ``vision_extraction_result`` are persisted from ``extra_context``. If
    ``extra_context`` is None or missing a given field, that slot stores
    as ``None`` — forward-compat safe, backward-compat safe.

    Runs on a background thread; exceptions never propagate back to the
    caller. This is a side-channel relative to the existing raw .md log +
    ChromaDB indexing — the conversation.json is specifically the source
    of truth for visual state continuity.
    """
    try:
        from conversation_memory import save_turn_spatial_state
        spatial_rep = None
        annotations = None
        vision_extr = None
        if isinstance(extra_context, dict):
            spatial_rep = extra_context.get("spatial_representation")
            annotations = extra_context.get("annotations")
            vision_extr = extra_context.get("vision_extraction_result")
        save_turn_spatial_state(
            conversation_id=panel_id,
            user_input=user_input,
            ai_response=ai_response,
            spatial_representation=spatial_rep,
            annotations=annotations,
            vision_extraction_result=vision_extr,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            tag=tag,
        )
    except Exception as e:
        print(f"[WARNING] WP-5.3 conversation.json persist failed: {e}")


# ── runtime pipeline helper ──────────────────────────────────────────────────

def _run_end_of_session_pipeline(user_input, ai_response, panel_id, config, history=None):
    """Fire async end-of-session processing (Phase 11 runtime pipeline)."""
    if not RUNTIME_PIPELINE_AVAILABLE:
        return
    try:
        from runtime_pipeline import SessionData
        sess = _session_data.get(panel_id, {})
        bridge = _bridge_state.get(panel_id, {})

        # Build full conversation history including the current exchange
        conv_history = list(history or [])
        conv_history.append({"role": "user", "content": user_input})
        conv_history.append({"role": "assistant", "content": ai_response})

        session_data = SessionData(
            session_id=sess.get("session_id", "unknown"),
            timestamp=datetime.now().isoformat(),
            mode=bridge.get("active_mode", ""),
            gear=bridge.get("active_gear", 0) or 0,
            models_used=[sess.get("model", "")],
            user_prompt=user_input,
            final_output=ai_response,
            conversation_history=conv_history,
            source_type="chat",
        )
        pipeline = RuntimePipeline(config=config, call_fn=call_model)
        pipeline.run_async(session_data)
    except Exception:
        pass  # Runtime pipeline failure never blocks the conversation


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
    from sidebar_window import clear_sidebar_window
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

# ── layout API ───────────────────────────────────────────────────────────────

# WP-2.3 — Active layout presets. Keep in sync with the on-disk preset set
# enumerated at /api/layouts (listdir LAYOUTS_DIR top level). Legacy files
# live under LAYOUTS_DIR/legacy/ and are not included in the active set.
_ACTIVE_LAYOUTS = ("solo", "studio")


def _default_layout():
    """Return tier-appropriate default layout.

    WP-2.3 retune: picks from the active-layouts set {solo, studio}.
      - Base default: ``solo`` (two-pane chat + visual).
      - Upgrade to ``studio`` (three-pane: chat + visual + sidebar chat) when
        BOTH local-mid AND local-premium buckets are populated — this is when
        there is spare compute for a second concurrent conversation stream.
      - Fail-closed: if the resolved preset falls outside ``_ACTIVE_LAYOUTS``
        (e.g. stale endpoints/bucket config), log a warning and fall back to
        ``solo`` rather than returning a retired layout.
    """
    preset = "solo"
    try:
        router_cfg = _load_routing_config() or {}
        buckets = router_cfg.get("buckets", {}) or {}
        has_mid     = len(buckets.get("local-mid", []) or []) > 0
        has_premium = len(buckets.get("local-premium", []) or []) > 0
        if has_mid and has_premium:
            preset = "studio"
    except Exception:
        preset = "solo"

    if preset not in _ACTIVE_LAYOUTS:
        # Fail-closed: never return a retired layout name.
        try:
            print(f"[_default_layout] resolved preset '{preset}' not in "
                  f"active set {_ACTIVE_LAYOUTS}; falling back to 'solo'.")
        except Exception:
            pass
        preset = "solo"

    layout_path = os.path.join(LAYOUTS_DIR, f"{preset}.json")
    try:
        with open(layout_path) as f:
            d = json.load(f)
        d["theme"] = "default-light"
        # Resolve default_bucket → slot_assignments for panels that declare one.
        d = _resolve_default_buckets(d)
        return d
    except Exception:
        # Hard-wire the solo fallback if the file itself is missing / malformed.
        return {"layout": {"preset_base": "solo", "panels": [
            {"id": "main",   "type": "chat",   "width_pct": 50, "model_slot": "breadth",
             "is_main_feed": True,  "bridge_subscribe_to": None,   "label": "Main Chat"},
            {"id": "visual", "type": "visual", "width_pct": 50, "model_slot": None,
             "is_main_feed": False, "bridge_subscribe_to": "main", "label": "Visual"},
        ]}, "theme": "default-light"}


def _resolve_default_buckets(layout_cfg):
    """WP-2.3 — honor ``default_bucket`` on layout panels.

    For every panel in ``layout_cfg['layout']['panels']`` that declares a
    ``default_bucket`` field AND a ``model_slot``, look up the slot's
    current assignment. If the slot is unassigned (no explicit user choice
    via the model switcher), prefer a model from the declared bucket. If
    the bucket is empty, fall back to any available model and log the
    fallback — never block layout resolution on bucket misconfiguration.

    The resolution is annotated back onto the panel under
    ``resolved_slot_assignment`` for client diagnostics (non-authoritative;
    the server's slot-assignment layer remains the source of truth).
    """
    if not isinstance(layout_cfg, dict):
        return layout_cfg
    layout = layout_cfg.get("layout") or {}
    panels = layout.get("panels") or []
    if not isinstance(panels, list):
        return layout_cfg

    try:
        cfg = load_config()
    except Exception:
        cfg = {}
    slot_assignments = (cfg.get("slot_assignments") or {}) if isinstance(cfg, dict) else {}

    try:
        router_cfg = _load_routing_config() or {}
        buckets = router_cfg.get("buckets", {}) or {}
    except Exception:
        buckets = {}

    try:
        models_cfg = load_models()
        known_ids = {m.get("id") for m in models_cfg.get("local_models", [])} | \
                    {m.get("id") for m in models_cfg.get("commercial_models", [])}
    except Exception:
        known_ids = set()

    for panel in panels:
        if not isinstance(panel, dict):
            continue
        default_bucket = panel.get("default_bucket")
        slot_name = panel.get("model_slot")
        if not default_bucket or not slot_name:
            continue
        # If user has already assigned a model to the slot, respect it.
        explicit = slot_assignments.get(slot_name)
        if explicit:
            panel["resolved_slot_assignment"] = {
                "source": "user_slot_assignment",
                "model_id": explicit,
                "bucket": default_bucket,
            }
            continue
        # Otherwise pick the first entry of the declared bucket.
        bucket_list = buckets.get(default_bucket) or []
        chosen = None
        for mid in bucket_list:
            if not known_ids or mid in known_ids:
                chosen = mid
                break
        if chosen:
            panel["resolved_slot_assignment"] = {
                "source": "default_bucket",
                "model_id": chosen,
                "bucket": default_bucket,
            }
            continue
        # Empty bucket — degrade gracefully: any known model OR just log.
        any_model = next(iter(known_ids)) if known_ids else None
        try:
            print(f"[_resolve_default_buckets] bucket '{default_bucket}' empty "
                  f"for slot '{slot_name}' on panel '{panel.get('id')}'; "
                  f"falling back to '{any_model or '(none)'}'.")
        except Exception:
            pass
        panel["resolved_slot_assignment"] = {
            "source": "empty_bucket_fallback",
            "model_id": any_model,
            "bucket": default_bucket,
            "fallback_reason": f"bucket '{default_bucket}' has no registered models",
        }

    return layout_cfg

@app.route("/api/layout")
def layout_get():
    try:
        with open(INTERFACE_JSON) as f:
            return f.read(), 200, {"Content-Type": "application/json"}
    except FileNotFoundError:
        return json.dumps(_default_layout()), 200, {"Content-Type": "application/json"}

@app.route("/api/layout", methods=["POST"])
def layout_post():
    data = request.get_json(force=True)
    try:
        # Preserve theme from current config
        try:
            with open(INTERFACE_JSON) as f:
                current = json.load(f)
            data.setdefault("theme", current.get("theme", "default-light"))
        except Exception:
            data.setdefault("theme", "default-light")
        with open(INTERFACE_JSON, "w") as f:
            json.dump(data, f, indent=2)
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/layouts")
def layouts_list():
    try:
        names = [f[:-5] for f in os.listdir(LAYOUTS_DIR) if f.endswith(".json")]
        return json.dumps({"layouts": sorted(names)})
    except Exception:
        return json.dumps({"layouts": []})

@app.route("/api/layouts/<name>")
def layout_load(name):
    path = os.path.normpath(os.path.join(LAYOUTS_DIR, f"{name}.json"))
    if not path.startswith(LAYOUTS_DIR):
        return "Forbidden", 403
    try:
        with open(path) as f:
            return f.read(), 200, {"Content-Type": "application/json"}
    except FileNotFoundError:
        return json.dumps({"error": "not found"}), 404

@app.route("/api/layouts/<name>", methods=["POST"])
def layout_save(name):
    data = request.get_json(force=True)
    path = os.path.normpath(os.path.join(LAYOUTS_DIR, f"{name}.json"))
    if not path.startswith(LAYOUTS_DIR):
        return "Forbidden", 403
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

# ── theme API ─────────────────────────────────────────────────────────────────

@app.route("/api/theme")
def theme_get():
    try:
        with open(INTERFACE_JSON) as f:
            cfg = json.load(f)
        theme_name = cfg.get("theme", "default-light")
    except Exception:
        theme_name = "default-light"
    path = os.path.normpath(os.path.join(THEMES_DIR, f"{theme_name}.css"))
    if not path.startswith(THEMES_DIR) or not os.path.exists(path):
        return Response("", mimetype="text/css")
    with open(path) as f:
        return Response(f.read(), mimetype="text/css")

@app.route("/api/theme", methods=["POST"])
def theme_set():
    data = request.get_json(force=True)
    theme = data.get("theme", "default-light")
    try:
        with open(INTERFACE_JSON) as f:
            cfg = json.load(f)
        cfg["theme"] = theme
        with open(INTERFACE_JSON, "w") as f:
            json.dump(cfg, f, indent=2)
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/themes")
def themes_list():
    try:
        names = [f[:-4] for f in os.listdir(THEMES_DIR) if f.endswith(".css")]
        return json.dumps({"themes": sorted(names)})
    except Exception:
        return json.dumps({"themes": ["default-light", "default-dark"]})

# ── V3 theme library API ──────────────────────────────────────────────────
# Folder-per-theme structure used by /v3 — each theme is a directory under
# server/static/themes/<id>/ containing manifest.json and theme.css.
# Index of installed themes lives at server/static/themes/index.json.

V3_THEMES_DIR = os.path.join(WORKSPACE, "server/static/themes/")
V3_THEMES_INDEX = os.path.join(V3_THEMES_DIR, "index.json")
COMMUNITY_DIRECTORY_URL = "https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/community-css-themes.json"

def _v3_slugify(text):
    slug = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return slug or 'theme'

def _v3_read_index():
    try:
        with open(V3_THEMES_INDEX) as f:
            return json.load(f)
    except Exception:
        return {"themes": []}

def _v3_write_index(data):
    os.makedirs(V3_THEMES_DIR, exist_ok=True)
    with open(V3_THEMES_INDEX, "w") as f:
        json.dump(data, f, indent=2)

def _v3_theme_dir(theme_id):
    if not re.match(r'^[a-z0-9_-]+$', theme_id or ''):
        raise ValueError(f"Invalid theme id: {theme_id}")
    return os.path.join(V3_THEMES_DIR, theme_id)

def _v3_install(theme_id, name, manifest, css):
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
    if not any(t.get("id") == theme_id for t in index.get("themes", [])):
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
    index = _v3_read_index()
    out = []
    for entry in index.get("themes", []):
        theme_id = entry.get("id")
        if not theme_id:
            continue
        manifest_path = os.path.join(V3_THEMES_DIR, theme_id, "manifest.json")
        manifest = {}
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception:
            pass
        out.append({**entry, "manifest": manifest})
    return json.dumps({"themes": out})

@app.route("/api/v3-themes/install", methods=["POST"])
def v3_themes_install_api():
    data = request.get_json(force=True) or {}
    manifest = data.get("manifest") or {}
    name = data.get("name") or manifest.get("name")
    css = data.get("css")
    if not name or not css:
        return json.dumps({"error": "Missing name or css"}), 400
    theme_id = _v3_slugify(name)
    if theme_id == "default":
        return json.dumps({"error": "Cannot overwrite default theme"}), 400
    try:
        return json.dumps(_v3_install(theme_id, name, manifest, css))
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/v3-themes/<theme_id>", methods=["DELETE"])
def v3_themes_delete_api(theme_id):
    if theme_id == "default":
        return json.dumps({"error": "Cannot delete default theme"}), 400
    try:
        theme_dir = _v3_theme_dir(theme_id)
        if os.path.isdir(theme_dir):
            shutil.rmtree(theme_dir)
        index = _v3_read_index()
        index["themes"] = [t for t in index.get("themes", []) if t.get("id") != theme_id]
        _v3_write_index(index)
        return json.dumps({"ok": True})
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
        return json.dumps(_v3_install(theme_id, name, manifest, css))
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

# ── bridge API (polling) ──────────────────────────────────────────────────────

@app.route("/api/bridge/<panel_id>", methods=["POST"])
def bridge_update(panel_id):
    data = request.get_json(force=True)
    existing = _bridge_state.get(panel_id, {})
    merged = {
        "current_topic":  data.get("current_topic", existing.get("current_topic", "")),
        "recent_messages": data.get("recent_messages", existing.get("recent_messages", []))[-5:],
        "active_mode":    data.get("active_mode",  existing.get("active_mode")),
        "active_gear":    data.get("active_gear",  existing.get("active_gear")),
        "pipeline_stage": data.get("pipeline_stage", existing.get("pipeline_stage")),
        "updated_at":     time.time(),
    }
    # WP-2.3 — Preserve ora-visual blocks on the bridge so subscribed
    # visual panels (solo/studio layouts) can pick them up on the next poll.
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
        config     = load_config()
        chroma_path = config.get("chromadb_path", os.path.expanduser("~/ora/chromadb/"))
        client     = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_collection("knowledge")
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

    def generate():
        step1 = pending["step1"]
        config = pending["config"]
        history = pending["history"]
        user_input = pending["user_input"]

        yield _sse("start", endpoint="resumed", pipeline=True)
        yield _sse("pipeline_stage", stage="step2_context",
                    label="Assembling context with clarification…")

        final_response = [None]
        active_mode = [step1.get("mode")]
        active_gear = [None]

        for chunk in _run_pipeline_from_step2(step1, config, history, user_input, answers,
                                              images=pending.get("images"),
                                              extra_context=pending.get("extra_context")):
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

        if final_response[0] is not None:
            is_new_session = len(history) == 0
            threading.Thread(
                target=_save_conversation,
                args=(user_input, final_response[0], panel_id, is_new_session),
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

    def generate():
        step1 = pending["step1"]
        config = pending["config"]
        history = pending["history"]
        user_input = pending["user_input"]

        yield _sse("start", endpoint="resumed", pipeline=True)
        yield _sse("pipeline_stage", stage="step2_context",
                    label="Assembling context (clarification skipped)…")

        final_response = [None]
        for chunk in _run_pipeline_from_step2(step1, config, history, user_input,
                                              images=pending.get("images"),
                                              extra_context=pending.get("extra_context")):
            yield chunk
            try:
                d = json.loads(chunk[6:])
                if d.get("type") == "response":
                    final_response[0] = d.get("text", "")
            except Exception:
                pass

        if final_response[0] is not None:
            threading.Thread(
                target=_save_conversation,
                args=(user_input, final_response[0], panel_id, len(history) == 0),
                daemon=True,
            ).start()

        _pipeline_state.update({"stage": None, "label": "", "active": False})
        yield _sse("done")

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


# ── vision detection ──────────────────────────────────────────────────────────

def _has_vision_endpoint():
    config = load_config()
    ep_by_name = {e["name"]: e for e in config.get("endpoints", [])}
    for name in ["gemini-api", "anthropic-api", "openai-api"]:
        ep = ep_by_name.get(name, {})
        if ep.get("status") == "active":
            return True, name
    return False, None

def _call_vision_generate_layout(description, image_b64, endpoint_name):
    """Call a vision-capable API model to generate interface.json from image + description."""
    config     = load_config()
    ep_by_name = {e["name"]: e for e in config.get("endpoints", [])}
    ep = ep_by_name.get(endpoint_name, {})
    service = ep.get("service", "")
    model   = ep.get("model", "")

    schema = json.dumps({
        "layout": {"preset_base": "custom", "panels": [
            {"id": "main", "type": "chat", "width_pct": 65, "model_slot": "breadth",
             "is_main_feed": True, "bridge_subscribe_to": None, "label": "Main Chat"},
            {"id": "sidebar", "type": "chat", "width_pct": 35, "model_slot": "sidebar",
             "is_main_feed": False, "bridge_subscribe_to": "main", "label": "Sidebar"}
        ]},
        "theme": "default-light"
    }, indent=2)

    prompt = (f"Generate a valid interface.json configuration for this layout.\n\n"
              f"Description: {description or '(see image)'}\n\n"
              f"Rules:\n"
              f"- Panel types: chat, vault, pipeline, clarification, switcher\n"
              f"- Model slots: breadth, depth, evaluator, sidebar, step1_cleanup, consolidator\n"
              f"- width_pct values must sum to 100\n"
              f"- Exactly one panel must have is_main_feed: true (chat panels only)\n"
              f"- bridge_subscribe_to references another panel id or null\n"
              f"- Max 6 panels\n"
              f"- Available themes: default-dark, default-light, high-contrast, terminal, warm\n\n"
              f"Output ONLY the JSON, no explanation:\n{schema}")

    try:
        if service == "gemini":
            import keyring
            from google import genai
            from google.genai import types as gtypes
            key = os.environ.get("GEMINI_API_KEY", "") or keyring.get_password("ora", "gemini-api-key") or ""
            client = genai.Client(api_key=key)
            parts = []
            if image_b64:
                import base64
                parts.append(gtypes.Part.from_bytes(
                    data=base64.b64decode(image_b64),
                    mime_type="image/jpeg"
                ))
            parts.append(prompt)
            resp = client.models.generate_content(
                model=model or "models/gemini-2.5-flash", contents=parts)
            return resp.text
        elif service == "claude":
            import anthropic, keyring
            key = os.environ.get("ANTHROPIC_API_KEY", "") or keyring.get_password("ora", "anthropic-api-key") or ""
            client = anthropic.Anthropic(api_key=key)
            content = []
            if image_b64:
                content.append({"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": image_b64}})
            content.append({"type": "text", "text": prompt})
            resp = client.messages.create(
                model=model or "claude-opus-4-6", max_tokens=2048,
                messages=[{"role": "user", "content": content}])
            return resp.content[0].text
        elif service == "openai":
            from openai import OpenAI
            import keyring
            key = os.environ.get("OPENAI_API_KEY", "") or keyring.get_password("ora", "openai-api-key") or ""
            client = OpenAI(api_key=key)
            content = [{"type": "text", "text": prompt}]
            if image_b64:
                content.insert(0, {"type": "image_url",
                                   "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}})
            resp = client.chat.completions.create(
                model=model or "gpt-4o",
                messages=[{"role": "user", "content": content}], max_tokens=2048)
            return resp.choices[0].message.content
    except Exception as e:
        return f"[vision error: {e}]"

@app.route("/api/generate-layout", methods=["POST"])
def generate_layout():
    data        = request.get_json(force=True)
    description = data.get("description", "").strip()
    image_b64   = data.get("image")

    if not description and not image_b64:
        return json.dumps({"error": "Provide a description or image"}), 400

    has_vision, vision_ep = _has_vision_endpoint()

    if image_b64 and not has_vision:
        return json.dumps({"error": "No vision-capable endpoint active. "
                           "Activate Gemini API, Claude API, or OpenAI API to use image-based layout generation."}), 422

    raw_response = None
    if image_b64 and has_vision:
        raw_response = _call_vision_generate_layout(description, image_b64, vision_ep)
    else:
        # Text-only: route to current breadth model
        config   = load_config()
        endpoint = get_endpoint(config)
        schema   = json.dumps({
            "layout": {"preset_base": "custom", "panels": [
                {"id": "main", "type": "chat", "width_pct": 65, "model_slot": "breadth",
                 "is_main_feed": True, "bridge_subscribe_to": None, "label": "Main Chat"}
            ]},
            "theme": "default-light"
        }, indent=2)
        prompt = (f"Generate a valid interface.json for this layout description:\n\n"
                  f"{description}\n\n"
                  f"Panel types: chat, vault, pipeline, clarification, switcher\n"
                  f"Model slots: breadth, depth, evaluator, sidebar, step1_cleanup, consolidator\n"
                  f"width_pct values must sum to 100. One panel must have is_main_feed: true.\n"
                  f"Available themes: default-dark, default-light, high-contrast, terminal, warm\n\n"
                  f"Output ONLY the JSON:\n{schema}")
        if endpoint:
            raw_response = call_model([{"role": "user", "content": prompt}], endpoint)

    if not raw_response:
        return json.dumps({"error": "No response from model"}), 503

    # Extract JSON
    match = re.search(r'\{[\s\S]*\}', raw_response)
    if not match:
        return json.dumps({"error": "Model did not return valid JSON", "raw": raw_response[:500]}), 422
    try:
        layout_cfg = json.loads(match.group())
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"JSON parse error: {e}", "raw": raw_response[:500]}), 422

    # Basic validation
    panels = layout_cfg.get("layout", {}).get("panels", [])
    if not panels:
        return json.dumps({"error": "No panels in generated layout"}), 422
    total_w = sum(p.get("width_pct", 0) for p in panels)
    if total_w and abs(total_w - 100) > 5:
        # Auto-fix: normalize widths
        for p in panels:
            p["width_pct"] = round(p.get("width_pct", 0) * 100 / total_w)

    return json.dumps({"layout": layout_cfg, "vision_used": bool(image_b64 and has_vision)})

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
      prompt (str), image_data_url (str), mask_data_url (str),
      parent_image_id (str | optional), strength (float | optional),
      provider_override (str | optional).

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

    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return Response(json.dumps({"error": {
            "code": "missing_required_input",
            "message": "image_edits requires a non-empty 'prompt'."
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
        return keyring.get_password("ora-stability", "api-key") or ""
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
        return keyring.get_password("ora", "replicate-api-token") or ""
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
            if override_ep and override_ep.get("vision_capable", False):
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

    Walks the routing config's bucket system in preference order:
    `local-premium` → `local-mid` → `commercial` → any active endpoint with
    ``vision_capable: true``. Returns None if none reachable so the caller
    can fall back to the mock path.
    """
    try:
        config = load_config()
    except Exception:
        return None
    endpoints = config.get("endpoints", []) or []
    # First pass: walk preferred buckets if defined.
    buckets = config.get("buckets", {}) or {}
    bucket_order = ["local-premium", "local-mid", "commercial", "local-fast"]
    by_id = {ep.get("id"): ep for ep in endpoints if ep.get("id")}
    for bname in bucket_order:
        for ep_id in buckets.get(bname, []) or []:
            ep = by_id.get(ep_id)
            if not ep:
                continue
            if not ep.get("enabled", False):
                continue
            if ep.get("status") not in ("active", None):
                # Treat missing status as active (older configs); missing
                # vision_capable is False by default below.
                continue
            if ep.get("vision_capable", False):
                return ep
    # Second pass: scan flat endpoint list for any vision-capable active.
    for ep in endpoints:
        if (ep.get("enabled", False)
                and ep.get("vision_capable", False)
                and ep.get("status") in ("active", None)):
            return ep
    return None


def _find_endpoint_by_id(endpoint_id):
    try:
        config = load_config()
    except Exception:
        return None
    for ep in config.get("endpoints", []) or []:
        if ep.get("id") == endpoint_id:
            return ep
    return None


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
        "You are an experienced visual-arts critic. Given an image, a rubric, "
        "and an optional genre, return a structured critique with per-criterion "
        "numeric scores (0–10), a short comment per criterion, and a prose "
        "discussion of the work as a whole. You always return your answer in "
        "two fenced blocks: a ```json``` block with the rubric_scores object, "
        "and a ```prose``` block with the discussion."
    )

    user_prompt = (
        f"Critique the attached image.\n"
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


# ── model switcher ───────────────────────────────────────────────────────────

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

@app.route("/models")
def models_endpoint():
    config     = load_config()
    models_cfg = load_models()
    ep_by_name = {e["name"]: e for e in config.get("endpoints", [])}

    system_ram = get_system_ram_gb()
    overhead   = models_cfg.get("overhead_reservation_gb", 8)
    budget     = system_ram - overhead

    for cm in models_cfg.get("commercial_models", []):
        ep = ep_by_name.get(cm["id"], {})
        cm["available"] = ep.get("status") == "active"

    return json.dumps({
        "system_ram_gb":      round(system_ram, 1),
        "overhead_gb":        overhead,
        "available_budget_gb": round(budget, 1),
        "local_models":       models_cfg.get("local_models", []),
        "commercial_models":  models_cfg.get("commercial_models", []),
        "slot_assignments":   config.get("slot_assignments", {}),
        "gear4_overrides":    config.get("gear4_overrides", {}),
    })

@app.route("/config", methods=["GET"])
def config_get():
    config = load_config()
    return json.dumps({
        "slot_assignments": config.get("slot_assignments", {}),
        "gear4_overrides":  config.get("gear4_overrides", {}),
    })

@app.route("/config", methods=["POST"])
def config_post():
    data             = request.get_json(force=True)
    slot_assignments = data.get("slot_assignments", {})
    gear4_overrides  = data.get("gear4_overrides")  # None if not sent

    models_cfg  = load_models()
    all_models  = {m["id"]: m for m in
                   models_cfg.get("local_models", []) + models_cfg.get("commercial_models", [])}
    system_ram  = get_system_ram_gb()
    overhead    = models_cfg.get("overhead_reservation_gb", 8)
    budget      = system_ram - overhead

    unique_local = {}
    for model_id in slot_assignments.values():
        m = all_models.get(model_id)
        if m and m.get("ram_gb", 0) > 0:
            unique_local[model_id] = m["ram_gb"]
    total_ram = sum(unique_local.values())

    if total_ram > budget:
        return json.dumps({
            "error": f"RAM exceeded: {total_ram:.1f} GB required, {budget:.1f} GB available"
        }), 400

    try:
        with open(ENDPOINTS) as f:
            cfg = json.load(f)
        cfg["slot_assignments"] = slot_assignments
        if gear4_overrides is not None:
            cfg["gear4_overrides"] = gear4_overrides
        with open(ENDPOINTS, "w") as f:
            json.dump(cfg, f, indent=2)
        result = {"ok": True, "slot_assignments": slot_assignments}
        if gear4_overrides is not None:
            result["gear4_overrides"] = gear4_overrides
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


# ── Routing Configuration API ─────────────────────────────────────────────

ROUTING_CONFIG = os.path.join(WORKSPACE, "config/routing-config.json")
PROVIDER_DB    = os.path.join(WORKSPACE, "config/provider-database.json")

def _load_routing_config():
    try:
        with open(ROUTING_CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_routing_config(cfg):
    with open(ROUTING_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")

def _get_router():
    """Get or create Router instance."""
    try:
        from router import Router
        return Router()
    except Exception:
        return None


@app.route("/config/routing")
def routing_config_get():
    """Return the full routing configuration."""
    cfg = _load_routing_config()
    return json.dumps(cfg)


@app.route("/config/routing", methods=["POST"])
def routing_config_post():
    """Update routing configuration (partial update — merges into existing)."""
    data = request.get_json(force=True)
    cfg = _load_routing_config()

    # Merge supported top-level keys
    for key in ["endpoints", "buckets", "pipelines", "reservation",
                "constraints", "ui_state", "diversity"]:
        if key in data:
            cfg[key] = data[key]

    _save_routing_config(cfg)
    return json.dumps({"ok": True})


@app.route("/config/routing/pipelines", methods=["POST"])
def routing_pipelines_post():
    """Update just the pipeline configuration."""
    data = request.get_json(force=True)
    cfg = _load_routing_config()
    cfg["pipelines"] = data.get("pipelines", cfg.get("pipelines", {}))
    _save_routing_config(cfg)
    return json.dumps({"ok": True})


@app.route("/config/routing/buckets", methods=["POST"])
def routing_buckets_post():
    """Update bucket contents (model ordering within tiers)."""
    data = request.get_json(force=True)
    cfg = _load_routing_config()
    cfg["buckets"] = data.get("buckets", cfg.get("buckets", {}))
    _save_routing_config(cfg)
    return json.dumps({"ok": True})


@app.route("/config/routing/status")
def routing_status():
    """Return current system routing status — what would happen now for each gear."""
    router = _get_router()
    if not router:
        return json.dumps({"error": "Router not available"}), 500
    return json.dumps(router.get_status())


@app.route("/config/providers")
def providers_get():
    """Return the provider database for bucket auto-population."""
    try:
        with open(PROVIDER_DB) as f:
            return json.dumps(json.load(f))
    except Exception:
        return json.dumps({})


# ── Extension Bridge (Chrome extension ↔ server ↔ browser_evaluate) ────────

from extension_bridge import (
    get_pending_request_nowait as _ext_get_pending,
    submit_result as _ext_submit_result,
    record_poll as _ext_record_poll,
    is_connected as _ext_is_connected,
    evaluate as _ext_evaluate,
)


@app.route("/api/extension/pending")
def extension_pending():
    """Polled by the Chrome extension to check for evaluation requests."""
    _ext_record_poll()
    req = _ext_get_pending()
    if req:
        return json.dumps({"request": req})
    return json.dumps({"request": None})


@app.route("/api/extension/result", methods=["POST"])
def extension_result():
    """Chrome extension posts evaluation results here."""
    data = request.json or {}
    _ext_submit_result(
        data.get("id", ""),
        response=data.get("response"),
        error=data.get("error"),
    )
    return json.dumps({"ok": True})


@app.route("/api/extension/evaluate", methods=["POST"])
def extension_evaluate():
    """Blocking evaluate endpoint for standalone callers (boot.py, CLI).

    Queues the request to the extension, waits for the result,
    and returns it. Times out after the specified duration.
    """
    if not _ext_is_connected():
        return json.dumps({"error": "Extension not connected"}), 503

    data = request.json or {}
    service = data.get("service", "")
    prompt = data.get("prompt", "")
    config = data.get("config", {})
    timeout = min(data.get("timeout", 180), 300)

    result = _ext_evaluate(service, prompt, config, timeout=timeout)

    if result is None:
        return json.dumps({"error": "Timeout or extension disconnected"}), 504
    if result.startswith("[extension]"):
        return json.dumps({"error": result}), 502
    return json.dumps({"response": result})


@app.route("/api/extension/status")
def extension_status():
    """Check if the Chrome extension is connected."""
    return json.dumps({"connected": _ext_is_connected()})


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


if __name__ == "__main__":
    import argparse, signal as _signal, socket

    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", action="store_true", help="Start task scheduler")
    args, _ = parser.parse_known_args()

    port = 5000
    for p in range(5000, 5011):
        try:
            s = socket.socket(); s.bind(("localhost", p)); s.close(); port = p; break
        except OSError:
            continue

    # Platform check — validate engine matches this machine
    try:
        from platform_check import startup_check
        for msg in startup_check():
            print(msg)
    except ImportError:
        pass

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

    # Start scheduler if requested
    if args.scheduler:
        from scheduler import get_scheduler
        sched = get_scheduler()
        sched.start()

    print(f"Local AI Chat Server starting on http://localhost:{port}")
    print(f"Active endpoint: {endpoint.get('name') if endpoint else 'NONE — add an endpoint first'}")
    print(f"Tools: {'available' if TOOLS_AVAILABLE else 'UNAVAILABLE'} ({len(TOOL_REGISTRY)} registered)")
    if mcp_count:
        print(f"MCP tools: {mcp_count}")
    if args.scheduler:
        print("Scheduler: running")
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
        if args.scheduler:
            sched.stop()
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

    app.run(host="localhost", port=port, debug=False, threaded=True)
