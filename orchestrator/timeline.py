"""Per-conversation timeline state — Audio/Video Phase 5.

The timeline is a non-destructive description of how clips from the
conversation's media library are arranged. Source files are never
modified; the Phase 7 render step reads this state and emits the
FFmpeg command chain that produces the final output.

Storage
-------
``~/ora/sessions/<conversation_id>/timeline.json`` — full state, replaced
on every mutation. The lifecycle is conversation-bound: the JSON is
sweeped along with the rest of the session directory if the conversation
is purged (Stealth) or deleted.

Schema (version 1)
------------------
::

    {
      "schema_version": 1,
      "conversation_id": "<id>",
      "duration_ms": 0,                  # max clip end across all tracks
      "playhead_ms": 0,
      "zoom_pixels_per_ms": 0.05,
      "tracks": [
        {
          "id": "<unique>",
          "kind": "video" | "audio" | "pip" | "music",
          "label": "<display>",
          "muted": false,
          "clips": [
            {
              "id": "<unique within track>",
              "media_entry_id": "<media library entry id>",
              "track_position_ms": 0,    # start position on the track
              "in_point_ms": 0,          # trim start within the source
              "out_point_ms": 0,         # trim end within the source
              "transition_in": "cut",    # cut | dissolve | fade-from-black
              "transition_out": "cut",   # cut | dissolve | fade-to-black
              "transition_duration_ms": 500,
              "volume": 1.0,             # 0.0 - 2.0 multiplier
              "fade_in_ms": 0,
              "fade_out_ms": 0
            }
          ]
        }
      ]
    }

Public API
----------
``Timeline(conversation_id)``
``timeline.load() -> dict``
``timeline.save(state) -> dict`` (validated, normalized state actually written)
``timeline.create_default() -> dict``
``get_timeline(conversation_id)`` — cached module-level lookup
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

WORKSPACE_ROOT = Path(os.path.expanduser("~/ora")).resolve()
SESSIONS_ROOT = WORKSPACE_ROOT / "sessions"

VALID_TRACK_KINDS = {"video", "audio", "pip", "music", "overlay"}
VALID_TRANSITIONS_IN = {"cut", "dissolve", "fade-from-black"}
VALID_TRANSITIONS_OUT = {"cut", "dissolve", "fade-to-black"}

# Phase 6 overlay clip types. The timeline stores these as clips on
# `overlay`-kind tracks; FFmpeg drawtext / overlay filters produce them at
# render time (Phase 7). They have no source media — content lives in
# the clip's overlay_content field.
VALID_OVERLAY_TYPES = {"lower-third", "title-card", "watermark"}
VALID_GRADIENT_KINDS = {"none", "linear", "radial"}
VALID_WATERMARK_CORNERS = {"top-left", "top-right", "bottom-left", "bottom-right"}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _default_watermark() -> dict:
    return {
        "enabled": False,
        "corner": "bottom-right",
        "opacity": 0.55,
        # When set, render uses this image via FFmpeg ``overlay`` instead
        # of the default ◎ glyph. Absolute path under
        # ``~/ora/sessions/<conv>/uploads/``.
        "image_path": None,
    }


def _default_state(conversation_id: str) -> dict:
    return {
        "schema_version": 1,
        "conversation_id": conversation_id,
        "duration_ms": 0,
        "playhead_ms": 0,
        "zoom_pixels_per_ms": 0.05,
        "watermark": _default_watermark(),
        "tracks": [
            {
                "id": _new_id("track"),
                "kind": "video",
                "label": "Video",
                "muted": False,
                "clips": [],
            },
            {
                "id": _new_id("track"),
                "kind": "audio",
                "label": "Audio",
                "muted": False,
                "clips": [],
            },
        ],
    }


def _default_overlay_content(overlay_type: str) -> dict:
    """Per-type defaults for a fresh overlay clip's content."""
    common = {
        "text": "",
        "font": "system-ui",
        "font_size": 36,
        "color": "#FFFFFF",
        "background_color": "#000000",
        "background_opacity": 0.0,
        "fade_in_ms": 200,
        "fade_out_ms": 200,
    }
    if overlay_type == "title-card":
        common.update({
            "text": "Title",
            "font_size": 96,
            "background_color": "#0E1117",
            "background_opacity": 1.0,
            "gradient": {
                "kind": "linear",
                "from_color": "#0E1117",
                "to_color": "#1A2030",
                "angle_deg": 135,
            },
            "fade_in_ms": 400,
            "fade_out_ms": 400,
        })
    elif overlay_type == "lower-third":
        common.update({
            "text": "Lower-third caption",
            "font_size": 36,
            "color": "#FFFFFF",
            "background_color": "#000000",
            "background_opacity": 0.55,
            "position": {"x_pct": 0.05, "y_pct": 0.78, "width_pct": 0.55},
        })
    elif overlay_type == "watermark":
        # Watermark at the timeline level is the documented surface; this
        # overlay-clip variant exists for completeness if a user wants a
        # time-ranged watermark instead of a global one.
        common.update({
            "text": "◎",
            "font_size": 48,
            "color": "#FFFFFF",
            "background_opacity": 0.0,
        })
    common.setdefault("position", {"x_pct": 0.5, "y_pct": 0.5, "width_pct": 1.0})
    common.setdefault("gradient", {
        "kind": "none",
        "from_color": "#000000",
        "to_color": "#000000",
        "angle_deg": 0,
    })
    return common


def _normalize_overlay_content(raw: dict, overlay_type: str) -> dict:
    """Clamp / fill defaults on an overlay clip's `overlay_content` field."""
    base = _default_overlay_content(overlay_type)
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for k, v in raw.items():
        out[k] = v

    out["text"] = str(out.get("text") or "")
    out["font"] = str(out.get("font") or "system-ui")
    try:
        out["font_size"] = max(8, int(out.get("font_size", 36) or 36))
    except (TypeError, ValueError):
        out["font_size"] = 36
    out["color"] = str(out.get("color") or "#FFFFFF")
    out["background_color"] = str(out.get("background_color") or "#000000")
    try:
        out["background_opacity"] = max(0.0, min(1.0, float(out.get("background_opacity", 0.0))))
    except (TypeError, ValueError):
        out["background_opacity"] = 0.0

    out["fade_in_ms"]  = max(0, int(out.get("fade_in_ms",  0) or 0))
    out["fade_out_ms"] = max(0, int(out.get("fade_out_ms", 0) or 0))

    # Position
    pos = out.get("position") or {}
    if not isinstance(pos, dict):
        pos = {}
    out["position"] = {
        "x_pct":     max(0.0, min(1.0, float(pos.get("x_pct", 0.5) or 0.0))),
        "y_pct":     max(0.0, min(1.0, float(pos.get("y_pct", 0.5) or 0.0))),
        "width_pct": max(0.05, min(1.0, float(pos.get("width_pct", 1.0) or 1.0))),
    }

    # Gradient (title cards mainly). Multi-stop support 2026-05-01:
    # the optional ``stops`` field carries 2..8 color strings interpolated
    # uniformly. When absent, ``from_color`` / ``to_color`` define a
    # 2-color gradient (the prior shape, kept for backward compatibility).
    grad = out.get("gradient") or {}
    if not isinstance(grad, dict):
        grad = {}
    g_kind = (grad.get("kind") or "none").strip()
    if g_kind not in VALID_GRADIENT_KINDS:
        g_kind = "none"

    raw_stops = grad.get("stops")
    norm_stops: list[str] = []
    if isinstance(raw_stops, list):
        for s in raw_stops:
            if isinstance(s, str) and s.strip():
                norm_stops.append(str(s).strip())
            elif isinstance(s, dict) and isinstance(s.get("color"), str):
                # Tolerate {color: "#xxx"} stop objects as well — leaves
                # room for per-stop position data later without breaking
                # this normalizer.
                norm_stops.append(s["color"].strip())
        # Cap at 8 (FFmpeg gradients filter limit) and require ≥ 2 to
        # be considered a valid multi-stop set; otherwise fall through.
        if len(norm_stops) > 8:
            norm_stops = norm_stops[:8]
        if len(norm_stops) < 2:
            norm_stops = []

    out["gradient"] = {
        "kind":       g_kind,
        "from_color": str(grad.get("from_color") or "#000000"),
        "to_color":   str(grad.get("to_color") or "#000000"),
        "angle_deg":  max(0, min(360, int(grad.get("angle_deg", 0) or 0))),
    }
    if norm_stops:
        out["gradient"]["stops"] = norm_stops
    return out


def _normalize_clip(raw: dict) -> dict:
    """Clamp / fill defaults on a single clip dict. Returns a new dict."""
    c = dict(raw)
    c.setdefault("id", _new_id("clip"))
    c.setdefault("media_entry_id", "")
    c["track_position_ms"] = max(0, int(c.get("track_position_ms", 0) or 0))
    c["in_point_ms"]  = max(0, int(c.get("in_point_ms",  0) or 0))
    c["out_point_ms"] = max(c["in_point_ms"] + 1, int(c.get("out_point_ms", 1) or 1))
    t_in = (c.get("transition_in")  or "cut").strip()
    if t_in not in VALID_TRANSITIONS_IN:
        t_in = "cut"
    c["transition_in"] = t_in
    t_out = (c.get("transition_out") or "cut").strip()
    if t_out not in VALID_TRANSITIONS_OUT:
        t_out = "cut"
    c["transition_out"] = t_out
    c["transition_duration_ms"] = max(0, int(c.get("transition_duration_ms", 500) or 0))
    try:
        vol = float(c.get("volume", 1.0))
    except (TypeError, ValueError):
        vol = 1.0
    c["volume"] = max(0.0, min(2.0, vol))
    c["fade_in_ms"]  = max(0, int(c.get("fade_in_ms",  0) or 0))
    c["fade_out_ms"] = max(0, int(c.get("fade_out_ms", 0) or 0))

    # Phase 6 overlay-clip support. Detected by presence of `overlay_type`
    # on the incoming clip; the field is otherwise absent for media clips.
    overlay_type = (c.get("overlay_type") or "").strip()
    if overlay_type:
        if overlay_type not in VALID_OVERLAY_TYPES:
            overlay_type = "lower-third"
        c["overlay_type"] = overlay_type
        c["overlay_content"] = _normalize_overlay_content(
            c.get("overlay_content") or {}, overlay_type)
        # Overlay clips don't reference a source media file.
        c["media_entry_id"] = ""
    return c


def _normalize_track(raw: dict) -> dict:
    t = dict(raw)
    t.setdefault("id", _new_id("track"))
    kind = (t.get("kind") or "video").strip()
    if kind not in VALID_TRACK_KINDS:
        kind = "video"
    t["kind"] = kind
    t.setdefault("label", kind.capitalize())
    t["muted"] = bool(t.get("muted", False))
    t["clips"] = [_normalize_clip(c) for c in (t.get("clips") or [])]
    # Ensure clip ids are unique within the track.
    seen = set()
    for c in t["clips"]:
        if c["id"] in seen:
            c["id"] = _new_id("clip")
        seen.add(c["id"])
    return t


def _normalize_watermark(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return _default_watermark()
    out = _default_watermark()
    out["enabled"] = bool(raw.get("enabled", out["enabled"]))
    corner = (raw.get("corner") or out["corner"]).strip()
    if corner not in VALID_WATERMARK_CORNERS:
        corner = "bottom-right"
    out["corner"] = corner
    try:
        out["opacity"] = max(0.0, min(1.0, float(raw.get("opacity", out["opacity"]))))
    except (TypeError, ValueError):
        pass
    # Image path: keep as-is if it's a non-empty string, otherwise None.
    img = raw.get("image_path")
    if isinstance(img, str) and img.strip():
        out["image_path"] = img.strip()
    else:
        out["image_path"] = None
    return out


def _normalize_state(state: dict, conversation_id: str) -> dict:
    out = {
        "schema_version": 1,
        "conversation_id": conversation_id,
        "playhead_ms": max(0, int(state.get("playhead_ms", 0) or 0)),
        "zoom_pixels_per_ms": max(0.001, float(state.get("zoom_pixels_per_ms", 0.05) or 0.05)),
        "watermark": _normalize_watermark(state.get("watermark") or {}),
        "tracks": [_normalize_track(t) for t in (state.get("tracks") or [])],
    }
    # Track-id uniqueness.
    seen = set()
    for t in out["tracks"]:
        if t["id"] in seen:
            t["id"] = _new_id("track")
        seen.add(t["id"])
    # Compute total duration: max(clip.track_position_ms + (out-in)) across all clips.
    longest = 0
    for t in out["tracks"]:
        for c in t["clips"]:
            length = max(0, c["out_point_ms"] - c["in_point_ms"])
            end = c["track_position_ms"] + length
            if end > longest:
                longest = end
    out["duration_ms"] = longest
    return out


class Timeline:
    """Per-conversation timeline state. Disk-backed, thread-safe."""

    def __init__(self, conversation_id: str) -> None:
        if not conversation_id:
            raise ValueError("conversation_id required")
        self.conversation_id = conversation_id
        self._lock = threading.Lock()
        self.session_dir = SESSIONS_ROOT / conversation_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.session_dir / "timeline.json"

    # ── public ──────────────────────────────────────────────────────────────

    def load(self) -> dict:
        with self._lock:
            if not self.state_path.exists():
                return _default_state(self.conversation_id)
            try:
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                # Corrupt — preserve a sidecar copy for forensics, return default.
                backup = self.state_path.with_suffix(".json.broken")
                try:
                    self.state_path.replace(backup)
                except Exception:
                    pass
                return _default_state(self.conversation_id)
        return _normalize_state(raw, self.conversation_id)

    def save(self, state: dict) -> dict:
        normalized = _normalize_state(state or {}, self.conversation_id)
        with self._lock:
            tmp = self.state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
            tmp.replace(self.state_path)
        return normalized

    def create_default(self) -> dict:
        st = _default_state(self.conversation_id)
        return self.save(st)


# Module-level cache (one Timeline per conversation_id) ─────────────────────

_timelines: dict[str, Timeline] = {}
_timelines_lock = threading.Lock()


def get_timeline(conversation_id: str) -> Timeline:
    if not conversation_id:
        raise ValueError("conversation_id required")
    with _timelines_lock:
        tl = _timelines.get(conversation_id)
        if tl is None:
            tl = Timeline(conversation_id)
            _timelines[conversation_id] = tl
        return tl


__all__ = [
    "Timeline",
    "get_timeline",
    "VALID_TRACK_KINDS",
    "VALID_TRANSITIONS_IN",
    "VALID_TRANSITIONS_OUT",
    "VALID_OVERLAY_TYPES",
    "VALID_GRADIENT_KINDS",
    "VALID_WATERMARK_CORNERS",
]
