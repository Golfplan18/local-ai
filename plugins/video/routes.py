"""HTTP and conversation-lifecycle surface owned by the video plugin."""

from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any, Callable

from flask import Response, request, send_file, send_from_directory

from server.feature_plugins import PluginRoute

from .backend import media_capture, media_library, preview, render, timeline
from .backend import url_import, video_suggestions, waveform


_context: Any = None
_render_conversations: dict[str, str] = {}


def _json(payload: Any, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status, mimetype="application/json")


def _run_many(items: tuple[tuple[str, Callable[[], Any]], ...], verb: str) -> dict:
    values: dict[str, Any] = {}
    errors: list[str] = []
    for label, callback in items:
        try:
            values[label] = callback()
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            print(f"[video-plugin] {verb} {label} failed: {exc}", flush=True)
    return {verb: values, "errors": errors}


def _staging_dir(conversation_id: str, *, create: bool = False) -> Path:
    return _context.safe_owned_subdir(
        _context.ora_home,
        "staging",
        "media-library",
        conversation_id,
        create=create,
    )


def _purge_staging(conversation_id: str) -> int:
    path = _staging_dir(conversation_id)
    if path.is_symlink():
        path.unlink()
        return 1
    if not path.exists():
        return 0
    if not path.is_dir():
        raise ValueError(f"media staging path is not a directory: {path}")
    removed = sum(len(files) for _root, _dirs, files in os.walk(path))
    shutil.rmtree(path)
    return removed


def on_quiesce(conversation_id: str) -> dict:
    """Kill and tombstone video workers before Delete Forever purges files."""
    return _run_many((
        ("captures", lambda: media_capture.get_default_manager().forget_conversation(conversation_id)),
        ("url_imports", lambda: url_import.get_default_manager().forget_conversation(conversation_id)),
        ("preview", lambda: preview.forget_conversation(conversation_id)),
        ("renders", lambda: render.get_default_manager().forget_conversation(conversation_id)),
        ("media_library", lambda: media_library.forget_library(conversation_id)),
    ), "quiesced")


def on_release(conversation_id: str) -> dict:
    """Release only finished video records when a reversible Close succeeds."""
    return _run_many((
        ("captures", lambda: media_capture.get_default_manager().release_finished(conversation_id)),
        ("url_imports", lambda: url_import.get_default_manager().release_finished(conversation_id)),
        ("renders", lambda: render.get_default_manager().release_finished(conversation_id)),
        ("timeline", lambda: timeline.release_timeline(conversation_id)),
        ("media_library", lambda: media_library.release_library(conversation_id)),
    ), "released")


def on_clear(conversation_id: str) -> dict:
    """Clear video caches and Ora-owned upload staging after permanent purge."""
    def clear_render_lookup() -> int:
        matches = [key for key, value in _render_conversations.items()
                   if value.casefold() == conversation_id.casefold()]
        for key in matches:
            _render_conversations.pop(key, None)
        return len(matches)

    return _run_many((
        ("timeline", lambda: timeline.forget_timeline(conversation_id)),
        ("media_staging_files", lambda: _purge_staging(conversation_id)),
        ("render_lookup", clear_render_lookup),
    ), "cleared")


def _capture_complete(event: dict) -> None:
    if event.get("type") != "complete" or not event.get("file_path"):
        return
    conversation_id = event.get("conversation_id")
    if not conversation_id and event.get("capture_id"):
        try:
            conversation_id = media_capture.get_default_manager().get_state(
                event["capture_id"]
            ).get("conversation_id")
        except Exception:
            return
    if not conversation_id:
        return
    try:
        media_library.get_library(conversation_id).add_entry(event["file_path"])
    except Exception as exc:
        print(f"[video-plugin] captured file registration failed: {exc}", flush=True)


def _render_complete(event: dict) -> None:
    if event.get("type") != "complete":
        return
    conversation_id = _render_conversations.get(event.get("render_id"))
    output = event.get("output_path")
    if not conversation_id or not output:
        return
    try:
        media_library.get_library(conversation_id).add_entry(
            output, display_name=os.path.basename(output)
        )
    except Exception as exc:
        print(f"[video-plugin] rendered file registration failed: {exc}", flush=True)


def _capture_devices():
    return _json({"available": True, **media_capture.list_avfoundation_devices()})


def _capture_snapshot():
    body = request.get_json(silent=True) or {}
    device = str(body.get("video_device") or "").strip()
    if not device:
        return _json({"error": "video_device required"}, 400)
    directory = _context.safe_owned_subdir(
        _context.ora_home, "staging", "region-snapshots", create=True
    )
    target = directory / f"snapshot-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}.jpg"
    try:
        ok = media_capture.capture_region_snapshot(device, target)
    except Exception as exc:
        return _json({"error": f"snapshot failed: {exc}"}, 500)
    if not ok or not target.is_file():
        return _json({"error": "snapshot produced no file"}, 500)
    return send_from_directory(str(directory), target.name, mimetype="image/jpeg")


def _capture_start():
    body = request.get_json(silent=True) or {}
    conversation_id = str(body.get("conversation_id") or "").strip()
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            tag, _created = _context.ensure_artifact_envelope(
                conversation_id, body.get("tag", "")
            )
        except Exception as exc:
            return _json({"error": str(exc)}, 409)
        options = dict(body.get("options") or {})
        options["_effective_conversation_tag"] = tag
        try:
            capture_id = media_capture.get_default_manager().start_capture(
                conversation_id, options
            )
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
    state = media_capture.get_default_manager().get_state(capture_id)
    return _json({"capture_id": capture_id, "state": state})


def _capture_action(capture_id: str, action: str):
    manager = media_capture.get_default_manager()
    try:
        if action == "pause":
            manager.pause_capture(capture_id)
        elif action == "resume":
            manager.resume_capture(capture_id)
        elif action == "stop":
            return _json(manager.stop_capture(capture_id))
        return _json({"state": manager.get_state(capture_id)})
    except KeyError:
        return _json({"error": "unknown capture_id"}, 404)
    except Exception as exc:
        return _json({"error": str(exc)}, 500)


def _capture_pause(capture_id):
    return _capture_action(capture_id, "pause")


def _capture_resume(capture_id):
    return _capture_action(capture_id, "resume")


def _capture_stop(capture_id):
    return _capture_action(capture_id, "stop")


def _capture_state(capture_id):
    try:
        return _json(media_capture.get_default_manager().get_state(capture_id))
    except KeyError:
        return _json({"error": "unknown capture_id"}, 404)


def _library_list(conversation_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        try:
            entries = media_library.get_library(conversation_id).list_entries()
            return _json({"available": True, "entries": entries})
        except Exception as exc:
            return _json({"error": str(exc)}, 500)


def _library_add(conversation_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    body = request.get_json(silent=True) or {}
    requested_tag = request.form.get("tag", "") if (request.files or request.form) else body.get("tag", "")
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            _context.ensure_artifact_envelope(conversation_id, requested_tag)
        except Exception as exc:
            return _json({"error": str(exc)}, 409)
        try:
            library = media_library.get_library(conversation_id)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
        upload = request.files.get("file")
        if upload is not None and upload.filename:
            name = os.path.basename(upload.filename).strip() or "upload"
            target = _staging_dir(conversation_id, create=True) / (
                f"{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}-{name}"
            )
            try:
                _context.save_upload(upload, str(target))
            except Exception as exc:
                return _json({"error": f"save failed: {exc}"}, 500)
            try:
                entry = library.add_entry(target, display_name=name, mime=upload.mimetype)
            except Exception as exc:
                return _json({"error": f"add failed: {exc}"}, 500)
            return _json({"entry": entry})
        if str(body.get("path") or "").strip():
            try:
                entry = library.add_entry(
                    str(body["path"]).strip(),
                    display_name=body.get("display_name"),
                    mime=body.get("mime") or "",
                )
            except FileNotFoundError as exc:
                return _json({"error": str(exc)}, 404)
            except Exception as exc:
                return _json({"error": f"add failed: {exc}"}, 500)
            return _json({"entry": entry})
        return _json({"error": "either file or path required"}, 400)


def _library_remove(conversation_id, entry_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    cross_site = _context.cross_site_mutation_response()
    if cross_site is not None:
        return cross_site
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            library = media_library.get_library(conversation_id)
            entry = library.get_entry(entry_id)
            if entry is None:
                return _json({"error": "unknown entry_id"}, 404)
            removed = _context.protected_media_reference_delete(
                conversation_id=conversation_id,
                entry_id=entry_id,
                entry=entry,
                state_path=library.state_path,
                effect=lambda: library.remove(
                    entry_id, expected_entry=entry,
                ),
            )
            if not removed:
                return _json({"error": "entry changed before deletion"}, 409)
            return _json({"removed": entry_id})
        except Exception as exc:
            response = getattr(exc, "ora_http_response", None)
            return response if response is not None else _json({"error": str(exc)}, 500)


def _library_rename(conversation_id, entry_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    name = str((request.get_json(silent=True) or {}).get("new_name") or "").strip()
    if not name:
        return _json({"error": "new_name required"}, 400)
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            entry = media_library.get_library(conversation_id).rename(entry_id, name)
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
        return _json({"entry": entry}) if entry else _json({"error": "unknown entry_id"}, 404)


def _library_thumbnail(conversation_id, entry_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        try:
            path = media_library.get_library(conversation_id).get_thumbnail_path(entry_id)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
        if path is None:
            return _json({"error": "no thumbnail"}, 404)
        return send_from_directory(str(path.parent), path.name, mimetype="image/jpeg")


def _library_waveform(conversation_id, entry_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        library = media_library.get_library(conversation_id)
        entry = library.get_entry(entry_id)
        if entry is None:
            return _json({"error": "unknown entry"}, 404)
        if entry.get("kind") not in {"audio", "video"}:
            return _json({"error": "entry has no audio track"}, 404)
        source_path = entry.get("source_path")
        if not source_path:
            return _json({"error": "entry has no source path"}, 404)
        source = Path(source_path)
        if not source.is_file():
            return _json({"error": "source file missing"}, 404)
        path = waveform.waveform_cache_path(library.thumbnails_dir, entry_id)
        if not path.exists() and not waveform.render_waveform(source, path):
            return _json({"error": "waveform render failed"}, 404)
        return send_from_directory(str(path.parent), path.name, mimetype="image/png")


def _transcript_for_entry(conversation_id: str, entry_id: str):
    entry = media_library.get_library(conversation_id).get_entry(entry_id)
    if entry is None:
        return None, _json({"error": "unknown entry"}, 404)
    source = entry.get("source_path")
    if not source:
        return None, _json({"error": "entry has no source path"}, 404)
    path = Path(source or "").with_suffix(".whisper.json")
    if not path.is_file():
        return None, _json({"error": "no transcript"}, 404)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, _json({"error": f"json parse: {exc}"}, 500)
    segments = []
    duration = 0
    for segment in raw.get("transcription", []) or []:
        offsets = segment.get("offsets", {}) or {}
        try:
            start, end = int(offsets.get("from") or 0), int(offsets.get("to") or 0)
        except (TypeError, ValueError):
            continue
        text = str(segment.get("text") or "").strip()
        if text:
            segments.append({"start_ms": start, "end_ms": end, "text": text})
            duration = max(duration, end)
    return {
        "entry_id": entry_id,
        "language": (raw.get("result", {}) or {}).get("language"),
        "duration_ms": duration,
        "segments": segments,
    }, None


def _library_transcript(conversation_id, entry_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        transcript, error = _transcript_for_entry(conversation_id, entry_id)
        return error if error is not None else _json(transcript)


def _import_start(conversation_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    body = request.get_json(silent=True) or {}
    url = str(body.get("url") or "").strip()
    if not url:
        return _json({"error": "url required"}, 400)
    if not url.startswith(("http://", "https://")):
        return _json({"error": "url must start with http:// or https://"}, 400)
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            _context.ensure_artifact_envelope(conversation_id, body.get("tag", ""))
            import_id = url_import.get_default_manager().start(conversation_id, url)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
    return _json({"import_id": import_id, "conversation_id": conversation_id, "url": url})


def _import_state(conversation_id, import_id):
    try:
        state = url_import.get_default_manager().get_state(import_id)
    except KeyError:
        return _json({"error": "unknown import_id"}, 404)
    except Exception as exc:
        return _json({"error": str(exc)}, 500)
    return _json(state) if state.get("conversation_id") == conversation_id else _json({"error": "unknown import_id"}, 404)


def _imports_list(conversation_id):
    try:
        return _json({"imports": url_import.get_default_manager().list_states(conversation_id)})
    except Exception as exc:
        return _json({"error": str(exc)}, 500)


def _suggest_edits(conversation_id, entry_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        transcript, error = _transcript_for_entry(conversation_id, entry_id)
        if error is not None:
            return error
        body = request.get_json(silent=True) or {}
        try:
            result = video_suggestions.generate_suggestions_heuristic(
                transcript,
                entry_id=entry_id,
                goals=body.get("goals"),
                existing_clips=body.get("existing_clips"),
            )
            return _json(result)
        except video_suggestions.SuggestionValidationError as exc:
            return _json({"error": f"suggestion validation: {exc}"}, 500)
        except Exception as exc:
            return _json({"error": f"suggestion generation: {exc}"}, 500)


def _timeline_load(conversation_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        try:
            return _json({"available": True, "timeline": timeline.get_timeline(conversation_id).load()})
        except Exception as exc:
            return _json({"error": str(exc)}, 500)


def _timeline_save(conversation_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    body = request.get_json(silent=True) or {}
    tag = body.pop("_conversation_tag", "")
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            _context.ensure_artifact_envelope(conversation_id, tag)
            return _json({"timeline": timeline.get_timeline(conversation_id).save(body)})
        except Exception as exc:
            return _json({"error": str(exc)}, 500)


_WATERMARK_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _watermark_upload(conversation_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return _json({"error": "file is required"}, 400)
    extension = Path(os.path.basename(upload.filename)).suffix.lower()
    if extension not in _WATERMARK_EXTENSIONS:
        return _json({
            "error": f"unsupported extension {extension!r}; use PNG, JPEG, or WebP",
        }, 400)
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            _context.ensure_artifact_envelope(conversation_id, request.form.get("tag", ""))
            directory = _context.safe_owned_subdir(
                _context.ora_home, "sessions", conversation_id, "uploads", create=True
            )
            target = directory / (
                f"watermark-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}{extension}"
            )
            _context.save_upload(upload, str(target))
            if target.stat().st_size > 10 * 1024 * 1024:
                target.unlink()
                return _json({"error": "watermark image must be under 10 MB"}, 400)
        except Exception as exc:
            return _json({"error": f"save failed: {exc}"}, 500)
    return _json({
        "conversation_id": conversation_id,
        "image_path": str(target),
        "filename": target.name,
    })


def _render_presets():
    presets = [{
        "key": key,
        "label": value["label"],
        "container": value["container"],
        "video": value["video"],
    } for key, value in render.PRESETS.items()]
    return _json({"available": True, "presets": presets})


def _render_start(conversation_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    body = request.get_json(silent=True) or {}
    export_dir = _context.get_setting("export.default_directory", None)
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            _context.ensure_artifact_envelope(conversation_id, body.get("tag", ""))
            render_id = render.get_default_manager().start(
                conversation_id,
                str(body.get("preset") or "standard").strip(),
                timeline.get_timeline(conversation_id).load(),
                media_library.get_library(conversation_id).list_entries(),
                export_dir=Path(export_dir).expanduser() if export_dir else None,
            )
            _render_conversations[render_id] = conversation_id
            state = render.get_default_manager().get_state(render_id)
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
    return _json({"render_id": render_id, "state": state})


def _render_state(render_id):
    try:
        return _json(render.get_default_manager().get_state(render_id))
    except KeyError:
        return _json({"error": "unknown render_id"}, 404)


def _render_cancel(render_id):
    try:
        render.get_default_manager().cancel(render_id)
    except KeyError:
        return _json({"error": "unknown render_id"}, 404)
    return _json({"cancelled": render_id})


def _preview_state(conversation_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        try:
            state = preview.proxy_state(conversation_id)
            state["available"] = True
            return _json(state)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)


def _preview_frame(conversation_id):
    try:
        milliseconds = int(request.args.get("ms", "0"))
    except (TypeError, ValueError):
        milliseconds = 0
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        try:
            content = preview.extract_frame(conversation_id, milliseconds)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
    return Response(content, mimetype="image/png", headers={
        "Cache-Control": "no-store", "Content-Length": str(len(content)),
    })


def _preview_proxy_start(conversation_id):
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": "invalid conversation_id"}, 400)
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            render_id = preview.start_proxy_render(conversation_id)
        except RuntimeError as exc:
            return _json({"error": str(exc)}, 400)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
    return _json({"render_id": render_id})


def _preview_proxy_file(conversation_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
        path = preview.proxy_path(conversation_id)
        if not path.is_file() or path.stat().st_size == 0:
            return _json({"error": "no proxy"}, 404)
        return send_file(str(path), mimetype="video/mp4", conditional=True, max_age=0)


def _preview_invalidate(conversation_id):
    with _context.conversation_read_scope(conversation_id) as (conversation_id, error):
        if error is not None:
            return error
    with _context.conversation_lifecycle_lock(conversation_id):
        if _context.is_conversation_deleted(conversation_id):
            return _json({"status": "deleted"}, 410)
        try:
            preview.invalidate_proxy(conversation_id)
        except Exception as exc:
            return _json({"error": str(exc)}, 500)
    return _json({"invalidated": True})


def _video_parameter_error(spec: dict, value: Any) -> str | None:
    """Return a refusal reason when one value violates its slot contract."""
    name = spec["name"]
    declared_type = spec.get("type")
    if declared_type == "text":
        if not isinstance(value, str):
            return f"video_generates input '{name}' must be text."
        if spec.get("required") and not value.strip():
            return f"video_generates requires a non-empty '{name}'."
        return None

    if declared_type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"video_generates input '{name}' must be a finite number."
        try:
            is_finite = math.isfinite(value)
        except (OverflowError, TypeError):
            is_finite = False
        if not is_finite:
            return f"video_generates input '{name}' must be a finite number."
        minimum = spec.get("min")
        maximum = spec.get("max")
        if minimum is not None and value < minimum:
            return f"video_generates input '{name}' must be at least {minimum}."
        if maximum is not None and value > maximum:
            return f"video_generates input '{name}' must be at most {maximum}."
        return None

    if declared_type == "enum":
        allowed = spec.get("enum_values")
        if not isinstance(allowed, list) or value not in allowed:
            choices = ", ".join(repr(item) for item in (allowed or []))
            return (
                f"video_generates input '{name}' must be one of the declared "
                f"values: {choices or 'none'}."
            )
        return None

    return (
        f"video_generates input '{name}' has unsupported declared type "
        f"{declared_type!r}."
    )


def _validated_video_inputs(
    contract: dict,
    inputs: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate every submitted input and preserve accepted values exactly."""
    specs: dict[str, dict] = {}
    required_names: set[str] = set()
    for field_group, required in (("required_inputs", True),
                                  ("optional_inputs", False)):
        for raw_spec in contract.get(field_group, []):
            if not isinstance(raw_spec, dict):
                continue
            name = raw_spec.get("name")
            if not isinstance(name, str):
                continue
            spec = dict(raw_spec)
            spec["required"] = required
            specs[name] = spec
            if required:
                required_names.add(name)

    for name in inputs:
        if name not in specs:
            return None, f"video_generates does not declare input '{name}'."

    for name in required_names:
        if name not in inputs or inputs[name] is None:
            return None, f"video_generates requires input '{name}'."

    validated: dict[str, Any] = {}
    for name, value in inputs.items():
        error = _video_parameter_error(specs[name], value)
        if error is not None:
            return None, error
        validated[name] = value
    return validated, None


def _capability_video_generates():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return _json({"error": {"code": "prompt_rejected", "message": "Request body must be JSON."}}, 400)
    if not isinstance(data, dict):
        return _json({"error": {
            "code": "prompt_rejected",
            "message": "Request body must be a JSON object.",
        }}, 400)
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        return _json({"error": {
            "code": "prompt_rejected",
            "message": "video_generates 'inputs' must be a JSON object.",
        }}, 400)
    conversation_id = data.get("conversation_id")
    if not _context.valid_live_conversation_id(conversation_id):
        return _json({"error": {
            "code": "prompt_rejected",
            "message": "video_generates requires a valid conversation_id.",
        }}, 400)

    with _context.conversation_read_scope(conversation_id) as (
        conversation_id, error_response,
    ):
        if error_response is not None:
            return error_response
        try:
            registry = _context.load_async_capability_registry(conversation_id)
        except Exception as exc:
            return _json({"error": {
                "code": "model_unavailable",
                "message": f"Async video providers unavailable: {exc}",
            }}, 503)

        contract = registry.get_contract("video_generates")
        handler_inputs, error = _validated_video_inputs(contract, inputs)
        if error is not None:
            return _json({"error": {
                "code": "prompt_rejected",
                "message": error,
            }}, 400)
        assert handler_inputs is not None

        provider_override = data.get("provider_override") or None
        try:
            # Bind OpenRouter across the complete cascade, including a
            # Replicate refusal followed by an OpenRouter fallback. The async
            # loader has already bound Replicate to this same Dialogue.
            import openrouter_images
            with openrouter_images.video_conversation(conversation_id):
                result = registry.invoke(
                    "video_generates",
                    handler_inputs,
                    provider_id=provider_override,
                )
        except Exception as exc:
            code = getattr(exc, "code", "model_unavailable")
            status = 502 if code == "model_unavailable" else 400
            return _json({"error": {"code": code, "message": str(exc)}}, status)
    job = getattr(result, "output", result)
    if not isinstance(job, dict) or not job.get("id"):
        return _json({"error": {"code": "model_unavailable", "message": "Async dispatcher returned no job descriptor."}}, 502)
    anchor = data.get("placeholder_anchor")
    if isinstance(anchor, dict):
        job = {**job, "placeholder_anchor": anchor}
    return _json({"job": job, "conversation_id": conversation_id})


def build_routes(context: Any) -> tuple[PluginRoute, ...]:
    """Configure one video import identity and return all plugin routes."""
    global _context
    _context = context
    media_capture.get_default_manager().subscribe(_capture_complete)
    render.get_default_manager().subscribe(_render_complete)
    return (
        PluginRoute("/api/capture/devices", "capture_devices", _capture_devices),
        PluginRoute("/api/capture/region-snapshot", "capture_snapshot", _capture_snapshot, ("POST",)),
        PluginRoute("/api/capture/start", "capture_start", _capture_start, ("POST",)),
        PluginRoute("/api/capture/<capture_id>/pause", "capture_pause", _capture_pause, ("POST",)),
        PluginRoute("/api/capture/<capture_id>/resume", "capture_resume", _capture_resume, ("POST",)),
        PluginRoute("/api/capture/<capture_id>/stop", "capture_stop", _capture_stop, ("POST",)),
        PluginRoute("/api/capture/<capture_id>/state", "capture_state", _capture_state),
        PluginRoute("/api/media-library/<conversation_id>", "library_list", _library_list),
        PluginRoute("/api/media-library/<conversation_id>/add", "library_add", _library_add, ("POST",)),
        PluginRoute("/api/media-library/<conversation_id>/<entry_id>", "library_remove", _library_remove, ("DELETE",)),
        PluginRoute("/api/media-library/<conversation_id>/<entry_id>/rename", "library_rename", _library_rename, ("POST",)),
        PluginRoute("/api/media-library/<conversation_id>/<entry_id>/thumbnail", "library_thumbnail", _library_thumbnail),
        PluginRoute("/api/media-library/<conversation_id>/<entry_id>/waveform", "library_waveform", _library_waveform),
        PluginRoute("/api/media-library/<conversation_id>/<entry_id>/transcript", "library_transcript", _library_transcript),
        PluginRoute("/api/media-library/<conversation_id>/import-url", "import_start", _import_start, ("POST",)),
        PluginRoute("/api/media-library/<conversation_id>/import/<import_id>/state", "import_state", _import_state),
        PluginRoute("/api/media-library/<conversation_id>/imports", "imports_list", _imports_list),
        PluginRoute("/api/media-library/<conversation_id>/<entry_id>/suggest-edits", "suggest_edits", _suggest_edits, ("POST",)),
        PluginRoute("/api/timeline/<conversation_id>", "timeline_load", _timeline_load),
        PluginRoute("/api/timeline/<conversation_id>", "timeline_save", _timeline_save, ("PUT",)),
        PluginRoute("/api/watermark/<conversation_id>/upload", "watermark_upload", _watermark_upload, ("POST",)),
        PluginRoute("/api/render/presets", "render_presets", _render_presets),
        PluginRoute("/api/render/<conversation_id>", "render_start", _render_start, ("POST",)),
        PluginRoute("/api/render/<render_id>/state", "render_state", _render_state),
        PluginRoute("/api/render/<render_id>/cancel", "render_cancel", _render_cancel, ("POST",)),
        PluginRoute("/api/preview/<conversation_id>/state", "preview_state", _preview_state),
        PluginRoute("/api/preview/<conversation_id>/frame", "preview_frame", _preview_frame),
        PluginRoute("/api/preview/<conversation_id>/proxy/start", "preview_proxy_start", _preview_proxy_start, ("POST",)),
        PluginRoute("/api/preview/<conversation_id>/proxy/file", "preview_proxy_file", _preview_proxy_file),
        PluginRoute("/api/preview/<conversation_id>/invalidate", "preview_invalidate", _preview_invalidate, ("POST",)),
        PluginRoute("/api/capability/video_generates", "capability_video_generates", _capability_video_generates, ("POST",)),
    )
