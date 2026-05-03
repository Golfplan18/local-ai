"""Preview subsystem — Audio/Video Phase 7 follow-up.

Backs the in-pane preview monitor. Two surfaces:

* **Single-frame extraction.** Given a conversation_id and a playhead
  time, return a PNG of what the timeline looks like at that moment.
  Cheap (sub-second for the dominant single-clip case).
* **360p proxy MP4.** Full-timeline render at low resolution, used by
  the preview monitor's playback mode. Cached per conversation in the
  session dir; invalidated on timeline mutation via a content hash.

Frame extraction strategy
-------------------------
1. If a fresh proxy MP4 exists, seek into it and grab a frame. This
   honors the full multi-track / overlay / watermark composition.
2. Otherwise, fall back to the FIRST video-kind clip active at the
   playhead — extract a frame straight from the source file at the
   corresponding source-time. Multi-track / overlays / watermark are
   skipped in this fallback path; the user can hit Play to render the
   full proxy if they want fidelity.

Public API
----------
``proxy_state(conversation_id) -> dict``
``start_proxy_render(conversation_id) -> render_id``
``extract_frame(conversation_id, playhead_ms) -> bytes (PNG)``
``invalidate_proxy(conversation_id) -> None``
``timeline_signature(timeline) -> str``
``proxy_path(conversation_id) -> Path``
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path

from render import (
    FFMPEG_BINARY,
    _ms_to_sec,
    _sort_clips_by_position,
    get_default_manager,
)
from timeline import get_timeline
from media_library import get_library

WORKSPACE_ROOT = Path(os.path.expanduser("~/ora")).resolve()
SESSIONS_ROOT = WORKSPACE_ROOT / "sessions"

PROXY_FILENAME = "preview-proxy.mp4"
PROXY_META_FILENAME = "preview-proxy.json"


# ── Paths ──────────────────────────────────────────────────────────────────

def _conv_dir(conversation_id: str) -> Path:
    d = SESSIONS_ROOT / conversation_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def proxy_path(conversation_id: str) -> Path:
    return _conv_dir(conversation_id) / PROXY_FILENAME


def proxy_meta_path(conversation_id: str) -> Path:
    return _conv_dir(conversation_id) / PROXY_META_FILENAME


# ── Signatures + meta ──────────────────────────────────────────────────────

def timeline_signature(timeline: dict) -> str:
    """Stable hash of the bits of timeline state that affect render output.

    Excludes playhead_ms and zoom (UI-only fields). When this hash
    changes, the cached proxy is stale.
    """
    relevant = {
        "tracks": timeline.get("tracks") or [],
        "watermark": timeline.get("watermark") or {},
    }
    blob = json.dumps(relevant, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _read_proxy_meta(conversation_id: str) -> dict | None:
    p = proxy_meta_path(conversation_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_proxy_meta(conversation_id: str, meta: dict) -> None:
    proxy_meta_path(conversation_id).write_text(
        json.dumps(meta, indent=2), encoding="utf-8")


def proxy_state(conversation_id: str) -> dict:
    """Report cached-proxy status for the conversation."""
    timeline = get_timeline(conversation_id).load()
    sig = timeline_signature(timeline)
    p = proxy_path(conversation_id)
    meta = _read_proxy_meta(conversation_id) or {}
    has_file = p.exists() and p.stat().st_size > 0
    fresh = has_file and meta.get("signature") == sig
    return {
        "has_proxy": has_file,
        "fresh": fresh,
        "signature_current": sig,
        "signature_cached": meta.get("signature"),
        "duration_ms": float(meta.get("duration_ms") or 0) if has_file else 0.0,
        "render_id": meta.get("render_id") if has_file else None,
    }


# ── Proxy render lifecycle ─────────────────────────────────────────────────

def start_proxy_render(conversation_id: str) -> str:
    """Kick off a 360p proxy render. Returns a render_id for SSE tracking.

    The RenderManager writes to ``<session_dir>/<render_id>.mp4``; on
    completion we rename to ``preview-proxy.mp4`` and stamp meta JSON
    with the timeline signature so subsequent ``proxy_state`` calls
    correctly detect freshness.
    """
    timeline = get_timeline(conversation_id).load()
    library = get_library(conversation_id).list_entries()
    sig = timeline_signature(timeline)

    manager = get_default_manager()
    out_dir = _conv_dir(conversation_id)
    render_id = manager.start(
        conversation_id=conversation_id,
        preset_name="preview_proxy",
        timeline=timeline,
        library_entries=library,
        export_dir=out_dir,
    )

    state = {"resolved": False, "unsubscribe": None}

    def _on_event(event: dict) -> None:
        if event.get("render_id") != render_id:
            return
        kind = event.get("type")
        if kind not in ("complete", "failed", "cancelled"):
            return
        if state["resolved"]:
            return
        state["resolved"] = True

        if kind == "complete":
            try:
                src = Path(event.get("output_path") or "")
                if src and src.exists():
                    dst = proxy_path(conversation_id)
                    if dst.exists():
                        try:
                            dst.unlink()
                        except Exception:
                            pass
                    src.replace(dst)
                    _write_proxy_meta(conversation_id, {
                        "signature": sig,
                        "duration_ms": float(event.get("duration_ms") or 0),
                        "render_id": render_id,
                    })
            except Exception:
                pass

        unsub = state.get("unsubscribe")
        if callable(unsub):
            try:
                unsub()
            except Exception:
                pass

    state["unsubscribe"] = manager.subscribe(_on_event)
    return render_id


def invalidate_proxy(conversation_id: str) -> None:
    """Mark the proxy as stale by deleting its meta file. The MP4 stays
    on disk until the next render replaces it (cheap, predictable)."""
    p = proxy_meta_path(conversation_id)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


# ── Single-frame extraction ────────────────────────────────────────────────

def extract_frame(conversation_id: str, playhead_ms: int) -> bytes:
    """Extract a PNG frame at the given playhead position."""
    if playhead_ms < 0:
        playhead_ms = 0

    state = proxy_state(conversation_id)

    # Path 1 — fresh proxy. Seek into it.
    if state["fresh"]:
        proxy_p = proxy_path(conversation_id)
        bytes_out = _extract_frame_from_file(str(proxy_p), int(playhead_ms))
        if bytes_out:
            return bytes_out

    # Path 2 — fallback to the active source clip on the primary video track.
    timeline = get_timeline(conversation_id).load()
    library = get_library(conversation_id).list_entries()
    library_by_id = {e.get("id"): e for e in library if e.get("id")}

    clip, source_time_ms = _find_active_video_clip(timeline, int(playhead_ms))
    if clip is None:
        return _placeholder_frame()

    media = library_by_id.get(clip.get("media_entry_id") or "")
    if not media:
        return _placeholder_frame()

    source_path = media.get("source_path")
    if not source_path or not Path(source_path).exists():
        return _placeholder_frame()

    bytes_out = _extract_frame_from_file(str(source_path), int(source_time_ms))
    return bytes_out or _placeholder_frame()


def _find_active_video_clip(
    timeline: dict, playhead_ms: int,
) -> tuple[dict | None, int]:
    """Locate the clip on the first video/pip track that covers playhead_ms.

    Returns (clip, source_time_ms) or (None, 0).
    """
    primary = None
    for t in timeline.get("tracks") or []:
        if t.get("kind") in ("video", "pip"):
            primary = t
            break
    if not primary:
        return None, 0

    for clip in _sort_clips_by_position(primary.get("clips") or []):
        if clip.get("overlay_type"):
            continue  # safety — overlay clips wouldn't end up here
        clip_start = int(clip.get("track_position_ms", 0))
        clip_in    = int(clip.get("in_point_ms", 0))
        clip_out   = int(clip.get("out_point_ms", 0))
        clip_length = max(0, clip_out - clip_in)
        clip_end = clip_start + clip_length
        if clip_start <= playhead_ms <= clip_end:
            source_time = clip_in + (playhead_ms - clip_start)
            return clip, max(0, int(source_time))
    return None, 0


def _extract_frame_from_file(source_path: str, time_ms: int) -> bytes:
    """Run ffmpeg to grab one PNG frame from the file at the given ms.

    Uses output-side seek (-ss after -i) so the seek lands accurately on
    the frame. For large files this is slower than input-side seek but
    still well under a second for typical proxy/source heights.
    """
    cmd = [
        FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel", "error",
        "-ss", f"{_ms_to_sec(time_ms):.3f}",
        "-i", str(source_path),
        "-frames:v", "1",
        "-vf", "scale=-2:360:force_original_aspect_ratio=decrease",
        "-f", "image2",
        "-c:v", "png",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=10, check=False)
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception:
        pass
    return b""


# ── Placeholder (empty timeline / unrenderable) ────────────────────────────

_PLACEHOLDER_CACHE: dict[str, bytes] = {}
_PLACEHOLDER_LOCK = threading.Lock()

# 1×1 transparent PNG — last-resort if FFmpeg isn't available.
_TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
    b"\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x35\x81\xc8\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)


def _placeholder_frame() -> bytes:
    """Render (and cache) a 640×360 dark-card PNG used when there's
    nothing to preview."""
    with _PLACEHOLDER_LOCK:
        cached = _PLACEHOLDER_CACHE.get("default")
        if cached:
            return cached
        cmd = [
            FFMPEG_BINARY,
            "-hide_banner", "-loglevel", "error",
            "-f", "lavfi",
            "-i", "color=c=#0E1117:s=640x360:r=1:d=1",
            "-frames:v", "1",
            "-f", "image2",
            "-c:v", "png",
            "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=5, check=False)
            if result.returncode == 0 and result.stdout:
                _PLACEHOLDER_CACHE["default"] = result.stdout
                return result.stdout
        except Exception:
            pass
        return _TRANSPARENT_PNG


__all__ = [
    "proxy_path",
    "proxy_meta_path",
    "proxy_state",
    "start_proxy_render",
    "extract_frame",
    "invalidate_proxy",
    "timeline_signature",
]
