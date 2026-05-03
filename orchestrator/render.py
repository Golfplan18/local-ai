"""Render subsystem — Audio/Video Phase 7.

Turns a per-conversation timeline into an FFmpeg command chain and
executes it as a subprocess. Output lands in the user's export
directory (default ``~/ora/exports/``) and is auto-added to the
conversation's media library.

Phase 7 MVP scope
-----------------
Renders the FIRST video-kind track + FIRST audio-kind track of the
timeline, with overlays and watermark composited on top:

* Video clips are trimmed (in_point_ms .. out_point_ms) and concatenated
  in track-position order. Gaps between clips are filled with black.
  Cut transitions only — dissolve / fade-from-black deferred.
* Audio clips are trimmed + per-clip volume + per-clip fade in/out
  applied, then concatenated in track-position order. Gaps filled with
  silence.
* Lower-third overlays render via `drawbox` + `drawtext` with `enable=
  'between(t,start,end)'` timing.
* Title-card overlays render as full-frame `drawbox` + `drawtext` over
  the (possibly black-padded) video stream.
* Watermark renders via `drawtext` with the ◎ glyph in the configured
  corner with the configured opacity.

Deferred (logged in deferrals doc):
* Multi-track video composition (P-i-P track layered on main video).
* Dissolve / fade-from-black transitions (need clip overlap timing).
* Multi-audio-track mixing via `amix`.
* Live preview (low-res proxy generated on demand).

Recently shipped:
* Two-pass H.264 encode (2026-05-01) — opt-in per preset via the
  ``v_two_pass`` flag. Enabled for the ``high`` preset; analysis pass
  writes stats to a per-render passlog file, then the encoding pass
  uses those stats for better motion-prediction decisions. Roughly
  doubles render time at the same CRF for measurably tighter
  compression / fewer artifacts on motion-heavy content.

Render presets
--------------
``standard``   — 1080p / 30fps / H.264 / AAC 192k
``high``       — source resolution / 60fps / H.264 / AAC 256k
``web``        — 1080p / 30fps / H.264 with `-movflags +faststart` + crf 22
``audio_only`` — m4a, AAC 192k, no video stream

Public API
----------
``RenderManager.start(conversation_id, preset)`` → ``render_id``
``RenderManager.cancel(render_id)``
``RenderManager.get_state(render_id)``
``RenderManager.subscribe(handler)``
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

WORKSPACE_ROOT = Path(os.path.expanduser("~/ora")).resolve()
DEFAULT_EXPORT_DIR = WORKSPACE_ROOT / "exports"
FFMPEG_BINARY = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE_BINARY = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

STATE_QUEUED = "queued"
STATE_PREPARING = "preparing"
STATE_RENDERING = "rendering"
STATE_COMPLETE = "complete"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

# ── Presets ──────────────────────────────────────────────────────────────────

PRESETS: dict[str, dict] = {
    "standard": {
        "label": "Standard (1080p · 30 fps · MP4)",
        "container": "mp4",
        "video": True,
        "scale_to_height": 1080,
        "frame_rate": 30,
        "v_codec": "libx264",
        "v_crf": 23,
        "v_preset": "fast",
        "v_extra": [],
        "a_codec": "aac",
        "a_bitrate": "192k",
        "movflags": [],
    },
    "high": {
        "label": "High quality (source resolution · 60 fps · MP4)",
        "container": "mp4",
        "video": True,
        "scale_to_height": None,  # source
        "frame_rate": 60,
        "v_codec": "libx264",
        "v_crf": 18,
        "v_preset": "slow",
        "v_extra": [],
        "v_two_pass": True,   # two-pass x264 — better quality per bit
        "a_codec": "aac",
        "a_bitrate": "256k",
        "movflags": [],
    },
    "web": {
        "label": "Web optimized (1080p · 30 fps · faststart MP4)",
        "container": "mp4",
        "video": True,
        "scale_to_height": 1080,
        "frame_rate": 30,
        "v_codec": "libx264",
        "v_crf": 22,
        "v_preset": "fast",
        "v_extra": [],
        "a_codec": "aac",
        "a_bitrate": "192k",
        "movflags": ["+faststart"],
    },
    "mov": {
        "label": "QuickTime (1080p · 30 fps · MOV / H.264)",
        "container": "mov",
        "video": True,
        "scale_to_height": 1080,
        "frame_rate": 30,
        "v_codec": "libx264",
        "v_crf": 22,
        "v_preset": "fast",
        "v_extra": [],
        "a_codec": "aac",
        "a_bitrate": "192k",
        "movflags": [],
    },
    "webm": {
        "label": "WebM (1080p · 30 fps · VP9 / Opus)",
        "container": "webm",
        "video": True,
        "scale_to_height": 1080,
        "frame_rate": 30,
        "v_codec": "libvpx-vp9",
        "v_crf": 33,
        "v_preset": None,  # libvpx-vp9 doesn't use -preset
        "v_extra": ["-b:v", "0", "-row-mt", "1"],
        "a_codec": "libopus",
        "a_bitrate": "128k",
        "movflags": [],
    },
    "audio_only": {
        "label": "Audio only (M4A · AAC 192k)",
        "container": "m4a",
        "video": False,
        "scale_to_height": None,
        "frame_rate": 30,
        "v_codec": None,
        "v_crf": None,
        "v_preset": None,
        "v_extra": [],
        "a_codec": "aac",
        "a_bitrate": "192k",
        "movflags": [],
    },
    "preview_proxy": {
        # 360p proxy used by the preview monitor for in-pane playback. Not
        # surfaced in the user-facing render preset menu; selected
        # programmatically by orchestrator/preview.py.
        "label": "Preview proxy (360p · 24 fps · MP4)",
        "container": "mp4",
        "video": True,
        "scale_to_height": 360,
        "frame_rate": 24,
        "v_codec": "libx264",
        "v_crf": 28,
        "v_preset": "ultrafast",
        "v_extra": ["-tune", "fastdecode"],
        "a_codec": "aac",
        "a_bitrate": "96k",
        "movflags": ["+faststart"],
    },
}


# ── State ────────────────────────────────────────────────────────────────────

@dataclass
class _Render:
    render_id: str
    conversation_id: str
    preset: str
    state: str = STATE_QUEUED
    started_at: float = 0.0
    progress_pct: float = 0.0
    duration_ms: float = 0.0  # total expected output duration
    output_path: Path | None = None
    last_error: str | None = None
    last_stderr_tail: str = ""
    process: subprocess.Popen | None = None
    cancel_requested: bool = False
    # When the preset opts into two-pass x264, x264 writes per-render
    # passlog files we have to clean up after both passes finish.
    passlog_file: Path | None = None


# ── Helpers ──────────────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"time=(\d+):(\d{2}):(\d{2})\.(\d+)")


def _parse_time_to_ms(match: re.Match) -> float:
    h = int(match.group(1))
    m = int(match.group(2))
    s = int(match.group(3))
    frac = match.group(4)
    frac_ms = int(round(float("0." + frac) * 1000))
    return ((h * 3600) + (m * 60) + s) * 1000.0 + frac_ms


def _ff_escape_text(s: str) -> str:
    """Escape text for FFmpeg drawtext filter.

    drawtext is a notoriously fussy filter. Quotes, colons, backslashes,
    newlines, and apostrophes all need escaping. We also strip any chars
    that would break command-line parsing (control chars).
    """
    if s is None:
        return ""
    s = str(s)
    # Drop control chars
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    # Escape backslash first, then ' and :
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace(":", "\\:")
    return s


def _ms_to_sec(ms: float | int) -> float:
    return float(ms) / 1000.0


def _resolve_font_file() -> str:
    """Pick a system font path that drawtext can use.

    drawtext's `font=` looks up by family via fontconfig, but availability
    of fontconfig depends on how FFmpeg was built. The Homebrew build on
    macOS supports both `font=` and explicit `fontfile=`. We prefer the
    explicit path because it works on every install.
    """
    candidates = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Avenir.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"


_FONT_FILE = _resolve_font_file()


# ── Command builder ─────────────────────────────────────────────────────────

def _collect_clip_sources(timeline: dict, library_entries: list[dict]) -> dict:
    """Build a media_entry_id → file_path lookup the renderer can use."""
    by_id = {}
    for entry in library_entries:
        if entry.get("id"):
            by_id[entry["id"]] = entry.get("source_path")
    return by_id


def _first_track_of_kind(timeline: dict, kind: str) -> dict | None:
    for t in timeline.get("tracks", []) or []:
        if t.get("kind") == kind:
            return t
    return None


def _clip_length_ms(clip: dict) -> int:
    return max(0, int(clip.get("out_point_ms", 0)) - int(clip.get("in_point_ms", 0)))


def _sort_clips_by_position(clips: list[dict]) -> list[dict]:
    return sorted(clips, key=lambda c: int(c.get("track_position_ms", 0)))


def _output_extension(preset: dict) -> str:
    return ".m4a" if preset["container"] == "m4a" else "." + preset["container"]


def _build_overlay_drawtext(text: str, x_expr: str, y_expr: str,
                            font_size: int, color: str,
                            bg_color: str, bg_opacity: float,
                            enable_expr: str,
                            shadow_color: str | None = None,
                            shadow_offset: int = 0,
                            outline_color: str | None = None,
                            outline_width: int = 0) -> list[str]:
    """Return one or two filter steps: optional drawbox + drawtext.

    V3 Backlog 2A Phase 6 close-out — shadow + outline (border) support
    via FFmpeg drawtext's ``shadowcolor`` / ``shadowx`` / ``shadowy`` and
    ``borderw`` / ``bordercolor`` parameters. Shadow renders BENEATH the
    glyph; outline (a.k.a. stroke) draws a contrasting band around it.
    Both are common readability features for overlays burned into video.
    """
    steps = []
    if bg_opacity > 0:
        steps.append(
            "drawbox=x={x}-20:y={y}-12:w=tw+40:h=th+24:color={col}@{op}:t=fill:enable='{enable}'".format(
                x=x_expr, y=y_expr,
                col=bg_color.lstrip("#"),
                op=f"{bg_opacity:.2f}",
                enable=enable_expr,
            )
        )

    extras = ""
    if shadow_color and shadow_offset > 0:
        extras += f":shadowcolor={shadow_color.lstrip('#')}:shadowx={shadow_offset}:shadowy={shadow_offset}"
    if outline_color and outline_width > 0:
        extras += f":borderw={outline_width}:bordercolor={outline_color.lstrip('#')}"

    steps.append(
        "drawtext=fontfile='{font}':text='{text}':x={x}:y={y}:fontsize={sz}:"
        "fontcolor={col}{extras}:enable='{enable}'".format(
            font=_FONT_FILE,
            text=_ff_escape_text(text),
            x=x_expr, y=y_expr, sz=font_size,
            col=color.lstrip("#"),
            extras=extras,
            enable=enable_expr,
        )
    )
    return steps


def _watermark_corner_offsets(corner: str, margin: int = 20) -> tuple[str, str]:
    """Map a corner name to (x_expr, y_expr) FFmpeg expressions.

    For drawtext the watermark is the text element ``tw/th``; for image
    overlay it's the overlay's intrinsic ``W/H``. Both share the same
    margin convention so the helper returns drawtext-style expressions
    that the image-overlay code rewrites with ``W`` and ``H``.
    """
    corner = (corner or "bottom-right").strip()
    if corner == "top-left":
        return f"{margin}", f"{margin}"
    if corner == "top-right":
        return f"w-tw-{margin}", f"{margin}"
    if corner == "bottom-left":
        return f"{margin}", f"h-th-{margin}"
    return f"w-tw-{margin}", f"h-th-{margin}"


def _watermark_filter(watermark: dict) -> str | None:
    """Return a drawtext step for the ◎-glyph watermark, or None.

    When the user has uploaded a custom image watermark
    (``watermark.image_path``), this function returns None and the
    image overlay is composited via ``_watermark_image_chain``
    instead — the two paths are mutually exclusive.
    """
    if not watermark or not watermark.get("enabled"):
        return None
    if watermark.get("image_path"):
        return None  # image watermark handled separately
    opacity = max(0.0, min(1.0, float(watermark.get("opacity", 0.55))))
    x_expr, y_expr = _watermark_corner_offsets(watermark.get("corner") or "bottom-right")
    return (
        "drawtext=fontfile='{font}':text='◎':x={x}:y={y}:fontsize=64:"
        "fontcolor=white@{op:.2f}".format(
            font=_FONT_FILE, x=x_expr, y=y_expr, op=opacity)
    )


def _watermark_image_overlay_steps(
    watermark: dict, prev_label: str, next_label: str
) -> list[str]:
    """FFmpeg filter-graph steps to composite a user-uploaded image
    watermark on top of the current video chain.

    Returns ``[]`` if the watermark isn't enabled or if there's no
    image path. Otherwise returns the chain steps needed to:

      1. Load the image via the ``movie`` filter source.
      2. Format and pre-multiply alpha so opacity scaling works.
      3. Apply opacity via ``colorchannelmixer``.
      4. Overlay onto the previous video chain at the configured corner.

    The corner mapping uses ``W`` (main video width) / ``w`` (overlay
    width) per FFmpeg ``overlay`` filter syntax — different from
    drawtext's ``w/tw``.
    """
    if not watermark or not watermark.get("enabled"):
        return []
    image_path = (watermark.get("image_path") or "").strip()
    if not image_path:
        return []
    if not Path(image_path).exists():
        return []
    opacity = max(0.0, min(1.0, float(watermark.get("opacity", 0.55))))
    corner = (watermark.get("corner") or "bottom-right").strip()
    margin = 20
    if corner == "top-left":
        x_overlay, y_overlay = f"{margin}", f"{margin}"
    elif corner == "top-right":
        x_overlay, y_overlay = f"W-w-{margin}", f"{margin}"
    elif corner == "bottom-left":
        x_overlay, y_overlay = f"{margin}", f"H-h-{margin}"
    else:
        x_overlay, y_overlay = f"W-w-{margin}", f"H-h-{margin}"
    # Escape colons and other FFmpeg-special chars in the path for the
    # ``movie`` filter source.
    safe_path = image_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", r"\'")
    return [
        f"movie='{safe_path}',format=rgba,colorchannelmixer=aa={opacity:.3f}[wm_img]",
        f"[{prev_label}][wm_img]overlay={x_overlay}:{y_overlay}[{next_label}]",
    ]


def _overlay_filters(overlay_clips: list[dict]) -> list[str]:
    """Convert overlay clips into a list of drawbox/drawtext filter strings."""
    out: list[str] = []
    for clip in overlay_clips:
        ot = clip.get("overlay_type") or ""
        content = clip.get("overlay_content") or {}
        start_s = _ms_to_sec(clip.get("track_position_ms", 0))
        end_s = start_s + _ms_to_sec(_clip_length_ms(clip))
        enable_expr = f"between(t,{start_s:.3f},{end_s:.3f})"
        text = content.get("text") or ""
        font_size = int(content.get("font_size", 36))
        color = content.get("color") or "#FFFFFF"
        bg_color = content.get("background_color") or "#000000"
        bg_opacity = float(content.get("background_opacity") or 0.0)
        pos = content.get("position") or {}
        x_pct = float(pos.get("x_pct", 0.5))
        y_pct = float(pos.get("y_pct", 0.5))

        if ot == "lower-third":
            x_expr = f"w*{x_pct:.4f}"
            y_expr = f"h*{y_pct:.4f}"
        elif ot == "title-card":
            # Centered on full frame.
            x_expr = "(w-tw)/2"
            y_expr = "(h-th)/2"
            # For title cards we draw a full-screen background BEFORE the
            # text, regardless of background_opacity (the card itself is
            # the visual surface).
            grad = content.get("gradient") or {}
            grad_kind = (grad.get("kind") or "none").strip()
            if grad_kind == "none":
                # Solid background fill.
                fill_color = bg_color.lstrip("#")
                fill_op = bg_opacity if bg_opacity > 0 else 1.0
                out.append(
                    f"drawbox=x=0:y=0:w=iw:h=ih:color={fill_color}@{fill_op:.2f}:"
                    f"t=fill:enable='{enable_expr}'"
                )
            else:
                # Phase 7 simplification: linear/radial gradients render as a
                # solid blend of from + to colors. True gradient drawing in
                # FFmpeg requires geq filter — defer.
                blend = (grad.get("from_color") or bg_color).lstrip("#")
                out.append(
                    f"drawbox=x=0:y=0:w=iw:h=ih:color={blend}@1.0:"
                    f"t=fill:enable='{enable_expr}'"
                )
        elif ot == "watermark":
            x_expr = f"w*{x_pct:.4f}"
            y_expr = f"h*{y_pct:.4f}"
        else:
            continue

        # V3 Backlog 2A Phase 6 close-out — shadow + outline.
        shadow_color  = content.get("text_shadow_color") or None
        shadow_offset = int(content.get("text_shadow_offset") or 0)
        outline_color = content.get("text_outline_color") or None
        outline_width = int(content.get("text_outline_width") or 0)

        out.extend(_build_overlay_drawtext(
            text=text, x_expr=x_expr, y_expr=y_expr,
            font_size=font_size, color=color,
            bg_color=bg_color, bg_opacity=bg_opacity if ot != "title-card" else 0.0,
            enable_expr=enable_expr,
            shadow_color=shadow_color, shadow_offset=shadow_offset,
            outline_color=outline_color, outline_width=outline_width,
        ))
    return out


def _canvas_size(preset: dict) -> str:
    h = preset.get("scale_to_height")
    if h is None or h == 1080:
        return "1920x1080"
    if h == 720:
        return "1280x720"
    # 16:9 canvas at the requested height; libx264 requires even dimensions.
    w = int(round(h * 16 / 9 / 2)) * 2
    return f"{w}x{h}"


def _build_video_track_chain(
    track: dict,
    track_idx: int,
    source_index: dict,
    sources_by_id: dict,
    preset: dict,
    total_ms: int,
    pip_mode: bool,
) -> tuple[list[str], str | None]:
    """Build a single video track's filter chain. Returns (filter_parts, label).

    `pip_mode=True` scales the track to PiP size (320 px wide, bottom-right)
    instead of full-canvas. Used for non-primary video / pip tracks.
    """
    clips = _sort_clips_by_position(track.get("clips") or [])
    if not clips:
        return [], None
    parts: list[str] = []
    canvas_size = _canvas_size(preset)
    base_label = f"v_t{track_idx}_base"
    parts.append(
        f"color=c=black@0.0:s={canvas_size}:r={preset['frame_rate']}:"
        f"d={_ms_to_sec(total_ms):.3f},format=yuva420p[{base_label}]"
    )

    prev = base_label
    target_height = preset["scale_to_height"] or 1080
    for i, c in enumerate(clips):
        clip_length_s = _ms_to_sec(_clip_length_ms(c))
        in_s = _ms_to_sec(c.get("in_point_ms", 0))
        out_s = _ms_to_sec(c.get("out_point_ms", 0))
        position_s = _ms_to_sec(c.get("track_position_ms", 0))
        src_idx = source_index[sources_by_id[c["media_entry_id"]]]
        label = f"v_t{track_idx}_c{i}"

        chain = (
            f"[{src_idx}:v]trim=start={in_s:.3f}:end={out_s:.3f},"
            f"setpts=PTS-STARTPTS+{position_s:.3f}/TB"
        )

        # Per-clip fade transitions (in/out on the SAME stream, no overlap
        # required). Dissolve transitions need xfade across clips and are
        # not implemented in this round — they fall back to cut.
        t_in = (c.get("transition_in") or "cut").lower()
        t_out = (c.get("transition_out") or "cut").lower()
        in_dur_ms = int(c.get("transition_duration_ms", 500) or 500)
        in_dur_s = _ms_to_sec(in_dur_ms)
        if t_in == "fade-from-black":
            chain += (
                f",fade=t=in:st={position_s:.3f}:"
                f"d={in_dur_s:.3f}:color=black"
            )
        if t_out == "fade-to-black":
            fade_start = position_s + clip_length_s - in_dur_s
            chain += (
                f",fade=t=out:st={fade_start:.3f}:"
                f"d={in_dur_s:.3f}:color=black"
            )

        chain += f"[{label}_raw]"
        parts.append(chain)

        # Scale to either canvas height or PiP width.
        scaled = f"{label}_s"
        if pip_mode:
            parts.append(f"[{label}_raw]scale=320:-2[{scaled}]")
        else:
            parts.append(f"[{label}_raw]scale=-2:{target_height}[{scaled}]")

        # Position on the track's canvas.
        out_label = f"{prev}_o{i}"
        if pip_mode:
            position_expr = "x=W-w-20:y=H-h-20"
        else:
            position_expr = "x=(W-w)/2:y=(H-h)/2"
        parts.append(
            f"[{prev}][{scaled}]overlay={position_expr}:eof_action=pass:"
            f"format=auto[{out_label}]"
        )
        prev = out_label

    return parts, prev


def _build_audio_track_chain(
    track: dict,
    track_idx: int,
    source_index: dict,
    sources_by_id: dict,
    total_ms: int,
) -> tuple[list[str], str | None]:
    clips = _sort_clips_by_position(track.get("clips") or [])
    if not clips:
        return [], None
    parts: list[str] = []
    a_clip_labels: list[str] = []
    for i, c in enumerate(clips):
        in_s = _ms_to_sec(c.get("in_point_ms", 0))
        out_s = _ms_to_sec(c.get("out_point_ms", 0))
        position_ms = int(c.get("track_position_ms", 0))
        src_idx = source_index[sources_by_id[c["media_entry_id"]]]
        label = f"a_t{track_idx}_c{i}"
        chain = (
            f"[{src_idx}:a]atrim=start={in_s:.3f}:end={out_s:.3f},"
            f"asetpts=PTS-STARTPTS"
        )
        vol = float(c.get("volume", 1.0))
        if vol != 1.0:
            chain += f",volume={vol:.3f}"
        fi = int(c.get("fade_in_ms", 0))
        fo = int(c.get("fade_out_ms", 0))
        length_s = _ms_to_sec(_clip_length_ms(c))
        if fi > 0:
            chain += f",afade=t=in:st=0:d={_ms_to_sec(fi):.3f}"
        if fo > 0:
            chain += (f",afade=t=out:st={(length_s - _ms_to_sec(fo)):.3f}:"
                      f"d={_ms_to_sec(fo):.3f}")
        if track.get("muted"):
            chain += ",volume=0"
        if position_ms > 0:
            chain += f",adelay={position_ms}|{position_ms}"
        chain += f"[{label}]"
        parts.append(chain)
        a_clip_labels.append(label)

    if len(a_clip_labels) == 1:
        out_label = f"a_t{track_idx}_out"
        parts.append(f"[{a_clip_labels[0]}]anull[{out_label}]")
        return parts, out_label
    inputs = "".join(f"[{l}]" for l in a_clip_labels)
    out_label = f"a_t{track_idx}_concat"
    parts.append(
        f"{inputs}amix=inputs={len(a_clip_labels)}:dropout_transition=0[{out_label}]"
    )
    return parts, out_label


def _build_title_card_gradient(clip: dict, gradient: dict, enable_expr: str,
                               canvas_size: str, frame_rate: int) -> tuple[list[str], str | None] | None:
    """For title cards with non-trivial gradients, generate the gradient via
    FFmpeg's ``gradients`` source filter and time-overlay it.

    Multi-stop support (2026-05-01): when ``gradient.stops`` is a list of
    2..8 color strings, those stops feed FFmpeg's ``c0..c7`` slots and
    ``nb_colors`` is set accordingly. The colors are interpolated
    uniformly (FFmpeg's gradients filter does not support per-stop
    positions). When ``stops`` is absent or has fewer than 2 colors, we
    fall back to the legacy ``from_color`` / ``to_color`` 2-color
    behavior so existing timelines continue to render unchanged.

    Returns (filter_parts, gradient_label_for_overlay) or None if no gradient
    is needed.
    """
    grad_kind = (gradient.get("kind") or "none").strip()
    if grad_kind == "none":
        return None

    raw_stops = gradient.get("stops")
    if isinstance(raw_stops, list) and len(raw_stops) >= 2:
        # Multi-stop path. Cap at FFmpeg's 8-color hard limit.
        colors = [
            str(s).lstrip("#") for s in raw_stops[:8]
            if isinstance(s, str) and s.strip()
        ]
        if len(colors) < 2:  # all entries malformed → fall back
            colors = [
                (gradient.get("from_color") or "#000000").lstrip("#"),
                (gradient.get("to_color") or "#000000").lstrip("#"),
            ]
    else:
        colors = [
            (gradient.get("from_color") or "#000000").lstrip("#"),
            (gradient.get("to_color") or "#000000").lstrip("#"),
        ]

    nb_colors = len(colors)
    color_args = ":".join(f"c{i}=0x{c}ff" for i, c in enumerate(colors))

    parts: list[str] = []
    label = f"grad_{clip.get('id', 'x').replace('-', '_')}"
    type_int = 0 if grad_kind == "linear" else 1  # gradients filter: 0=linear,1=radial
    parts.append(
        f"gradients=size={canvas_size}:{color_args}:"
        f"type={type_int}:speed=0:nb_colors={nb_colors}[{label}_raw]"
    )
    # Trim to the clip's enable window (we'll overlay with enable= for safety
    # too, but the gradients filter is infinite without trim).
    start_ms = int(clip.get("track_position_ms", 0))
    duration_ms = _clip_length_ms(clip)
    parts.append(
        f"[{label}_raw]trim=duration={_ms_to_sec(duration_ms):.3f},"
        f"setpts=PTS-STARTPTS+{_ms_to_sec(start_ms):.3f}/TB[{label}]"
    )
    return parts, label


def _split_for_two_pass(
    argv: list[str], output_path: Path, render_id: str
) -> tuple[list[str], list[str], Path]:
    """Build pass-1 + pass-2 argvs for an x264 two-pass encode.

    Pass 1 analyzes the video and writes stats to a per-render passlog
    file; pass 2 reads those stats and produces the final output. Audio
    is dropped from pass 1 (`-an`) since the analysis only needs video,
    and the output is muxed to a null sink (`-f null /dev/null`) so we
    don't waste IO writing a discardable file. Both passes share the
    same encoder settings — the caller-supplied argv defines those —
    so the only deltas are the pass-specific flags spliced in.

    The passlog path is returned so the caller can clean up
    ``<passlog>-0.log`` and ``<passlog>-0.log.mbtree`` after both
    passes succeed (or fail). x264 names the actual files by appending
    ``-0.log`` and ``-0.log.mbtree`` to the prefix we pass.
    """
    out_str = str(output_path)
    # Locate the output-path argv slot: it's the last element of argv
    # (mirrors how _assemble_command terminates the command).
    if not argv or argv[-1] != out_str:
        raise RuntimeError(
            "_split_for_two_pass: argv tail does not match output_path"
        )

    passlog = output_path.parent / f".x264-pass-{render_id}"

    # Pass 1: drop audio, write to null sink, run analysis.
    pass1 = list(argv[:-1])  # everything except the output path
    pass1 += [
        "-pass", "1",
        "-passlogfile", str(passlog),
        "-an",
        "-f", "null",
        os.devnull,
    ]

    # Pass 2: full argv with -pass 2 inserted.
    pass2 = list(argv[:-1]) + [
        "-pass", "2",
        "-passlogfile", str(passlog),
        out_str,
    ]
    return pass1, pass2, passlog


def _cleanup_passlog(passlog: Path) -> None:
    """Remove x264 passlog files (best-effort)."""
    for suffix in ("-0.log", "-0.log.mbtree", ".log", ".log.mbtree"):
        candidate = Path(str(passlog) + suffix)
        try:
            if candidate.exists():
                candidate.unlink()
        except Exception:
            pass


def _assemble_command(
    timeline: dict,
    sources_by_id: dict,
    output_path: Path,
    preset: dict,
) -> tuple[list[str], int]:
    """Return (argv, expected_duration_ms). Raises if no renderable content.

    Phase 7 fixes — supports:
      * Multi-video-track composition (first video track full-size; pip-kind
        tracks scaled to 320 px bottom-right; subsequent video tracks
        layered full-size on top).
      * Multi-audio-track mixing via amix across all audio + music tracks
        (pip tracks excluded — their audio would duplicate the screen mic).
      * fade-from-black / fade-to-black via the `fade` filter on individual
        clips (no overlap required).
      * Title-card gradients via FFmpeg's `gradients` source filter, time-
        overlaid during the title card's enable window.

    Still deferred:
      * Dissolve transitions via xfade — needs cross-clip overlap timing.
    Multi-stop title-card gradients shipped 2026-05-01 — see
    ``_build_title_card_gradient`` for the ``gradient.stops`` field.
    """
    all_tracks = timeline.get("tracks", []) or []
    video_tracks = [t for t in all_tracks if t.get("kind") in ("video", "pip")]
    audio_tracks = [t for t in all_tracks if t.get("kind") in ("audio", "music")]
    overlay_tracks = [t for t in all_tracks if t.get("kind") == "overlay"]

    overlay_clips: list[dict] = []
    for t in overlay_tracks:
        overlay_clips.extend(t.get("clips") or [])

    # Quick "anything to render" guard.
    has_any_clips = any(t.get("clips") for t in (video_tracks + audio_tracks))
    if preset["video"]:
        has_video = any(t.get("clips") for t in video_tracks)
        if not has_video:
            raise RuntimeError("no clips on any video track to render")
    elif not has_any_clips:
        raise RuntimeError("nothing to render — timeline is empty")

    # Total output duration = max(end of last clip across every track).
    total_ms = 0
    for track in (video_tracks + audio_tracks):
        for c in track.get("clips") or []:
            end = int(c.get("track_position_ms", 0)) + _clip_length_ms(c)
            if end > total_ms:
                total_ms = end
    if total_ms == 0:
        total_ms = int(timeline.get("duration_ms") or 1000)

    # Inputs.
    used_sources: list[str] = []
    source_index: dict[str, int] = {}
    for track in (video_tracks + audio_tracks):
        for c in track.get("clips") or []:
            media_id = c.get("media_entry_id")
            if not media_id:
                continue
            path = sources_by_id.get(media_id)
            if not path:
                raise RuntimeError(f"clip references unknown media entry: {media_id}")
            if path not in source_index:
                source_index[path] = len(used_sources)
                used_sources.append(path)

    cmd: list[str] = [
        FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel", "info",
        "-stats",
        "-y",
    ]
    for src in used_sources:
        cmd += ["-i", src]

    filter_parts: list[str] = []
    canvas_size = _canvas_size(preset)

    # ── Video chain (multi-track) ────────────────────────────────────
    final_video_label = None
    if preset["video"] and video_tracks:
        # Base canvas — solid black, full duration.
        filter_parts.append(
            f"color=c=black:s={canvas_size}:r={preset['frame_rate']}:"
            f"d={_ms_to_sec(total_ms):.3f}[v_base]"
        )
        prev = "v_base"
        # Render each video track and overlay onto the base.
        for ti, track in enumerate(video_tracks):
            pip_mode = (track.get("kind") == "pip" and ti > 0)
            track_parts, track_label = _build_video_track_chain(
                track, ti, source_index, sources_by_id,
                preset, total_ms, pip_mode)
            if not track_label:
                continue
            filter_parts.extend(track_parts)
            out_label = f"{prev}_t{ti}"
            filter_parts.append(
                f"[{prev}][{track_label}]overlay=eof_action=pass[{out_label}]"
            )
            prev = out_label

        # ── Title-card gradient backgrounds (drawn BEFORE drawtext) ──
        grad_overlay_steps: list[tuple[str, str, str]] = []  # (label, enable_expr, _)
        for clip in overlay_clips:
            if clip.get("overlay_type") != "title-card":
                continue
            grad = (clip.get("overlay_content") or {}).get("gradient") or {}
            if (grad.get("kind") or "none") == "none":
                continue
            start_s = _ms_to_sec(clip.get("track_position_ms", 0))
            end_s = start_s + _ms_to_sec(_clip_length_ms(clip))
            enable_expr = f"between(t,{start_s:.3f},{end_s:.3f})"
            grad_built = _build_title_card_gradient(
                clip, grad, enable_expr, canvas_size, preset["frame_rate"])
            if grad_built is None:
                continue
            parts, grad_label = grad_built
            filter_parts.extend(parts)
            grad_overlay_steps.append((grad_label, enable_expr, ""))

        # Composite gradient layers in order.
        for grad_label, enable_expr, _unused in grad_overlay_steps:
            out_label = f"{prev}_grad"
            filter_parts.append(
                f"[{prev}][{grad_label}]overlay=enable='{enable_expr}'"
                f":eof_action=pass[{out_label}]"
            )
            prev = out_label

        # Apply drawtext / drawbox overlays + watermark.
        overlay_steps = _overlay_filters(overlay_clips)
        wm_step = _watermark_filter(timeline.get("watermark") or {})  # text glyph
        if wm_step:
            overlay_steps.append(wm_step)
        # Image watermark gets its own chain step (it's an FFmpeg
        # ``overlay`` filter, not a drawtext you can tack onto the
        # overlay-step comma chain). When present it lands as the
        # final v_out producer.
        wm_image_steps = _watermark_image_overlay_steps(
            timeline.get("watermark") or {},
            "v_post_overlays" if overlay_steps else prev,
            "v_out",
        )
        if overlay_steps and wm_image_steps:
            filter_parts.append(f"[{prev}]" + ",".join(overlay_steps) + "[v_post_overlays]")
            filter_parts.extend(wm_image_steps)
            final_video_label = "v_out"
        elif overlay_steps:
            filter_parts.append(f"[{prev}]" + ",".join(overlay_steps) + "[v_out]")
            final_video_label = "v_out"
        elif wm_image_steps:
            filter_parts.extend(wm_image_steps)
            final_video_label = "v_out"
        else:
            filter_parts.append(f"[{prev}]copy[v_out]")
            final_video_label = "v_out"

    # ── Audio chain (multi-track) ────────────────────────────────────
    final_audio_label = None
    audio_track_outputs: list[str] = []
    for ti, track in enumerate(audio_tracks):
        track_parts, label = _build_audio_track_chain(
            track, 100 + ti, source_index, sources_by_id, total_ms)
        if not label:
            continue
        filter_parts.extend(track_parts)
        audio_track_outputs.append(label)

    if len(audio_track_outputs) == 1:
        filter_parts.append(f"[{audio_track_outputs[0]}]anull[a_out]")
        final_audio_label = "a_out"
    elif len(audio_track_outputs) > 1:
        inputs = "".join(f"[{l}]" for l in audio_track_outputs)
        filter_parts.append(
            f"{inputs}amix=inputs={len(audio_track_outputs)}:"
            f"dropout_transition=0:normalize=0[a_out]"
        )
        final_audio_label = "a_out"
    elif preset["video"]:
        # No audio at all — synthesize silence so the muxer gets both streams.
        filter_parts.append(
            f"anullsrc=channel_layout=stereo:sample_rate=44100:"
            f"d={_ms_to_sec(total_ms):.3f}[a_out]"
        )
        final_audio_label = "a_out"

    if filter_parts:
        cmd += ["-filter_complex", ";".join(filter_parts)]

    # Maps
    if preset["video"] and final_video_label:
        cmd += ["-map", f"[{final_video_label}]"]
    if final_audio_label:
        cmd += ["-map", f"[{final_audio_label}]"]

    # Encoding
    if preset["video"]:
        cmd += ["-c:v", preset["v_codec"]]
        if preset.get("v_preset"):
            cmd += ["-preset", preset["v_preset"]]
        if preset.get("v_crf") is not None:
            cmd += ["-crf", str(preset["v_crf"])]
        cmd += [
            "-pix_fmt", "yuv420p",
            "-r", str(preset["frame_rate"]),
        ]
        if preset.get("v_extra"):
            cmd += list(preset["v_extra"])
        if preset["movflags"]:
            cmd += ["-movflags"] + preset["movflags"]
    if final_audio_label:
        cmd += [
            "-c:a", preset["a_codec"],
            "-b:a", preset["a_bitrate"],
        ]
    cmd += ["-t", f"{_ms_to_sec(total_ms):.3f}", str(output_path)]
    return cmd, total_ms


# ── RenderManager ───────────────────────────────────────────────────────────

class RenderManager:
    def __init__(self, default_export_dir: Path | None = None) -> None:
        self._renders: dict[str, _Render] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[dict], None]] = []
        self._default_export_dir = default_export_dir or DEFAULT_EXPORT_DIR
        self._default_export_dir.mkdir(parents=True, exist_ok=True)

    def subscribe(self, handler: Callable[[dict], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(handler)

        def _unsub() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(handler)
                except ValueError:
                    pass
        return _unsub

    def _broadcast(self, event: dict) -> None:
        with self._lock:
            handlers = list(self._subscribers)
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass

    def get_state(self, render_id: str) -> dict:
        with self._lock:
            r = self._renders.get(render_id)
        if not r:
            raise KeyError(f"unknown render_id: {render_id}")
        return {
            "render_id": r.render_id,
            "conversation_id": r.conversation_id,
            "preset": r.preset,
            "state": r.state,
            "progress_pct": r.progress_pct,
            "duration_ms": r.duration_ms,
            "output_path": str(r.output_path) if r.output_path else None,
            "last_error": r.last_error,
        }

    def cancel(self, render_id: str) -> None:
        with self._lock:
            r = self._renders.get(render_id)
        if not r:
            raise KeyError(f"unknown render_id: {render_id}")
        r.cancel_requested = True
        if r.process and r.state == STATE_RENDERING:
            try:
                r.process.terminate()
            except Exception:
                pass

    def start(self, conversation_id: str, preset_name: str,
              timeline: dict, library_entries: list[dict],
              export_dir: Path | None = None) -> str:
        if preset_name not in PRESETS:
            raise ValueError(f"unknown preset: {preset_name}")
        preset = PRESETS[preset_name]

        render_id = uuid.uuid4().hex[:12]
        ext = _output_extension(preset)
        out_dir = (export_dir or self._default_export_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{render_id}{ext}"

        r = _Render(
            render_id=render_id,
            conversation_id=conversation_id,
            preset=preset_name,
            output_path=output_path,
            started_at=time.time(),
            state=STATE_PREPARING,
        )
        with self._lock:
            self._renders[render_id] = r
        self._broadcast({
            "type": "queued",
            "render_id": render_id,
            "conversation_id": conversation_id,
            "preset": preset_name,
        })

        sources_by_id = _collect_clip_sources(timeline, library_entries)
        try:
            argv, total_ms = _assemble_command(
                timeline, sources_by_id, output_path, preset)
        except Exception as e:
            r.state = STATE_FAILED
            r.last_error = str(e)
            self._broadcast({
                "type": "failed",
                "render_id": render_id,
                "error": str(e),
            })
            return render_id

        r.duration_ms = float(total_ms)

        # If the preset opts into two-pass x264, split the single argv
        # into pass-1 (analysis) + pass-2 (encode) commands. Falls back
        # to single-pass on splitting failure so we never silently drop
        # to a no-encode state.
        passes: list[list[str]] = [argv]
        if preset.get("v_two_pass"):
            try:
                p1, p2, passlog = _split_for_two_pass(
                    argv, output_path, render_id)
                passes = [p1, p2]
                r.passlog_file = passlog
            except Exception as e:
                r.last_error = (
                    f"two-pass split failed, falling back to single-pass: {e}"
                )

        # Run in a background thread so the API call returns fast.
        t = threading.Thread(target=self._run, args=(r, passes),
                             name=f"render-{render_id}", daemon=True)
        t.start()
        return render_id

    def _run(self, r: _Render, passes: list[list[str]]) -> None:
        """Execute one or more ffmpeg passes sequentially.

        Single-pass renders pass a 1-element list; two-pass renders pass
        [pass1, pass2]. Progress maps each pass to 1/N of the total
        progress range so the UI bar advances smoothly across passes.
        Cancellation between passes is honored. Failure on any pass
        terminates the render. The x264 passlog file is cleaned up
        regardless of outcome.
        """
        r.state = STATE_RENDERING
        self._broadcast({
            "type": "rendering",
            "render_id": r.render_id,
        })

        n_passes = max(1, len(passes))
        tail: list[str] = []
        run_failed = False

        try:
            for pass_idx, argv in enumerate(passes):
                if r.cancel_requested:
                    break

                pass_weight = 1.0 / n_passes
                base_pct = pass_idx * pass_weight * 100.0

                proc = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
                r.process = proc

                # Per-pass closure so each iteration has its own proc /
                # base_pct / weight but shares the tail buffer.
                def _drain(p=proc, base=base_pct, weight=pass_weight):
                    try:
                        for raw in iter(p.stderr.readline, b""):
                            try:
                                line = raw.decode("utf-8", errors="replace")
                            except Exception:
                                continue
                            tail.append(line)
                            if len(tail) > 80:
                                tail.pop(0)
                            m = _TIME_RE.search(line)
                            if m and r.duration_ms > 0:
                                elapsed_ms = _parse_time_to_ms(m)
                                local_pct = (elapsed_ms / r.duration_ms) * 100.0
                                pct = max(0.0, min(
                                    100.0, base + local_pct * weight))
                                r.progress_pct = pct
                                self._broadcast({
                                    "type": "progress",
                                    "render_id": r.render_id,
                                    "progress_pct": pct,
                                    "elapsed_ms": elapsed_ms,
                                })
                    except Exception as e:
                        r.last_error = f"stderr-drain: {e}"

                t_err = threading.Thread(target=_drain, daemon=True)
                t_err.start()
                proc.wait()
                t_err.join(timeout=2.0)

                if r.cancel_requested:
                    break

                if proc.returncode != 0:
                    run_failed = True
                    r.last_stderr_tail = "".join(tail)[-1500:]
                    pass_label = (
                        f"pass {pass_idx + 1}/{n_passes}"
                        if n_passes > 1 else "ffmpeg"
                    )
                    r.last_error = (
                        f"{pass_label} exited rc={proc.returncode}. "
                        f"stderr tail:\n{r.last_stderr_tail}"
                    )
                    break

            # Always clean up x264 passlog files (best-effort, no-op for
            # single-pass renders since passlog_file is None).
            if r.passlog_file is not None:
                _cleanup_passlog(r.passlog_file)

            if r.cancel_requested:
                r.state = STATE_CANCELLED
                self._broadcast({
                    "type": "cancelled",
                    "render_id": r.render_id,
                })
                if r.output_path and r.output_path.exists():
                    try: r.output_path.unlink()
                    except Exception: pass
                return

            if run_failed:
                r.state = STATE_FAILED
                self._broadcast({
                    "type": "failed",
                    "render_id": r.render_id,
                    "error": r.last_error,
                })
                return

            r.state = STATE_COMPLETE
            r.progress_pct = 100.0
            self._broadcast({
                "type": "complete",
                "render_id": r.render_id,
                "output_path": str(r.output_path),
                "duration_ms": r.duration_ms,
            })
        except Exception as e:
            if r.passlog_file is not None:
                _cleanup_passlog(r.passlog_file)
            r.state = STATE_FAILED
            r.last_error = f"render exception: {e}"
            self._broadcast({
                "type": "failed",
                "render_id": r.render_id,
                "error": r.last_error,
            })


# ── Module-level singleton ───────────────────────────────────────────────────

_default_manager: RenderManager | None = None
_default_manager_lock = threading.Lock()


def get_default_manager() -> RenderManager:
    global _default_manager
    with _default_manager_lock:
        if _default_manager is None:
            _default_manager = RenderManager()
        return _default_manager


__all__ = [
    "RenderManager",
    "get_default_manager",
    "PRESETS",
    "STATE_QUEUED",
    "STATE_PREPARING",
    "STATE_RENDERING",
    "STATE_COMPLETE",
    "STATE_FAILED",
    "STATE_CANCELLED",
]
