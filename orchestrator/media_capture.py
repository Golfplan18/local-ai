"""Media capture subsystem — Audio/Video Phase 1.

Wraps FFmpeg as a subprocess for screen + microphone capture on macOS
(``avfoundation`` input) and Windows (``gdigrab`` / ``ddagrab`` + ``dshow``;
not yet exercised in Phase 1). The application code calling this module is
identical across platforms; only the FFmpeg command-string parameterization
differs per OS.

Storage routing is conversation-tag aware
-----------------------------------------
* ``tag == "stealth"`` → ``~/ora/sessions/<conversation_id>/captures/``.
  Purged when the conversation is purged. Honors the no-trace contract.
* ``tag == "private"`` or ``""`` (standard) → user-configured capture
  directory (default ``~/ora/captures/``). Persistent across conversation
  deletion.

Pause / resume model
--------------------
FFmpeg has no native pause. We implement pause as "stop the current
segment, keep the capture alive". Each Start / Resume cycle writes a
new segment file (``<capture_id>-segment-<N>.mp4``). Stop concatenates
the segments via FFmpeg's concat demuxer into the final file
(``<capture_id>.mp4``) and removes the per-segment temporaries.

Stderr / stdout parsing
-----------------------
* ``stderr`` carries FFmpeg's ``-stats`` line (``time=HH:MM:SS.SS …``);
  we parse for duration.
* ``stdout`` carries the ``ametadata`` filter output, one
  ``lavfi.astats.Overall.RMS_level=<float>`` line per audio frame group;
  we parse for live level metering.

Subscribers receive ``capture_event`` dicts via :meth:`CaptureManager.subscribe`.
The Flask SSE generator (``/api/capture/stream/<id>``) consumes these and
forwards them to the browser as ``capture_status`` frames.

Public API
----------
``CaptureManager.start_capture(conversation_id, options) -> capture_id``
``CaptureManager.pause_capture(capture_id) -> None``
``CaptureManager.resume_capture(capture_id) -> None``
``CaptureManager.stop_capture(capture_id) -> dict`` (``{file_path, duration_ms}``)
``CaptureManager.get_state(capture_id) -> dict`` snapshot
``CaptureManager.subscribe(handler) -> unsubscribe_callable``
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ── Conversation-tag awareness for stealth routing ───────────────────────────
try:
    from conversation_memory import get_conversation_tag
except Exception:  # pragma: no cover — defensive on import-order quirks
    def get_conversation_tag(_conv_id: str) -> str:
        return ""


# ── Module configuration ─────────────────────────────────────────────────────

WORKSPACE_ROOT = Path(os.path.expanduser("~/ora")).resolve()
SESSIONS_ROOT = WORKSPACE_ROOT / "sessions"
DEFAULT_CAPTURE_DIR = WORKSPACE_ROOT / "captures"
FFMPEG_BINARY = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PAUSED = "paused"
STATE_STOPPING = "stopping"
STATE_COMPLETE = "complete"
STATE_FAILED = "failed"


# ── Per-capture state container ──────────────────────────────────────────────

@dataclass
class _Capture:
    capture_id: str
    conversation_id: str
    tag: str  # "" | "stealth" | "private"
    options: dict
    capture_dir: Path
    segment_paths: list[Path] = field(default_factory=list)
    current_process: subprocess.Popen | None = None
    state: str = STATE_IDLE
    started_at: float = 0.0
    paused_offset_ms: float = 0.0  # accumulated duration from completed segments
    last_segment_started_at: float = 0.0
    last_duration_ms: float = 0.0
    last_rms_level_db: float | None = None
    last_error: str | None = None
    last_stderr_tail: str = ""
    final_file_path: Path | None = None
    _stderr_thread: threading.Thread | None = None
    _stdout_thread: threading.Thread | None = None


# ── Platform-specific FFmpeg input flags ─────────────────────────────────────
#
# Application code is identical across platforms; only the input flags differ.
# Phase 1 implements macOS only; the Windows branch is stubbed and will be
# fleshed out in Phase 10 (cross-platform validation).

_WEBCAM_CORNER_OVERLAY = {
    "top-left":     "20:20",
    "top-right":    "W-w-20:20",
    "bottom-left":  "20:H-h-20",
    "bottom-right": "W-w-20:H-h-20",
}


def _build_ffmpeg_command(
    capture: _Capture,
    segment_path: Path,
) -> list[str]:
    """Construct the FFmpeg argv for one capture segment.

    Supports four feature flags via ``capture.options``:

    ============== =====================================================
    Option         Effect
    ============== =====================================================
    video_device   Index in avfoundation. Resolved by the client.
    audio_device   Index, or None to skip audio capture.
    frame_rate     int, default 30.
    crop           ``{x, y, w, h}`` dict, optional. Region of the source
                   to keep (Phase 4 region-selection feature).
    webcam_device  avfoundation index of a webcam, optional. When set,
                   captured as a second input and overlaid as PiP.
    webcam_corner  one of top-left / top-right / bottom-left /
                   bottom-right (default).
    webcam_scale   PiP width in pixels (default 320).
    ============== =====================================================
    """
    opts = capture.options
    frame_rate = int(opts.get("frame_rate", 30))
    video_device = str(opts.get("video_device", "3"))
    audio_device = opts.get("audio_device", "0")
    audio_input = "" if audio_device is None else str(audio_device)
    webcam_device = opts.get("webcam_device")
    webcam_corner = opts.get("webcam_corner") or "bottom-right"
    webcam_scale = int(opts.get("webcam_scale") or 320)
    crop = opts.get("crop") or None

    if platform.system() != "Darwin":
        if platform.system() == "Windows":  # pragma: no cover — Phase 10
            raise NotImplementedError("Windows capture lands in Phase 10")
        raise RuntimeError(f"Unsupported capture platform: {platform.system()}")

    cmd: list[str] = [
        FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel", "info",
        "-stats",
        "-y",
    ]

    # ── Input 0: primary screen (+ optional mic) ──────────────────────
    screen_input_spec = (
        f"{video_device}:{audio_input}" if audio_input else f"{video_device}"
    )
    cmd += [
        "-f", "avfoundation",
        "-framerate", str(frame_rate),
        "-pix_fmt", "uyvy422",
        "-capture_cursor", "1",
        "-i", screen_input_spec,
    ]

    # ── Input 1: optional webcam (video only) ─────────────────────────
    if webcam_device is not None and str(webcam_device) != "":
        cmd += [
            "-f", "avfoundation",
            "-framerate", str(frame_rate),
            "-pix_fmt", "uyvy422",
            "-i", str(webcam_device),
        ]

    # ── Filter graph ───────────────────────────────────────────────────
    has_pip = webcam_device is not None and str(webcam_device) != ""
    has_crop = bool(crop)

    filter_parts: list[str] = []
    video_map = "0:v"

    if has_crop and has_pip:
        filter_parts.append(
            f"[0:v]crop={int(crop['w'])}:{int(crop['h'])}:"
            f"{int(crop['x'])}:{int(crop['y'])}[base]"
        )
        filter_parts.append(f"[1:v]scale={webcam_scale}:-1[cam]")
        overlay_pos = _WEBCAM_CORNER_OVERLAY.get(
            webcam_corner, _WEBCAM_CORNER_OVERLAY["bottom-right"]
        )
        filter_parts.append(f"[base][cam]overlay={overlay_pos}[v]")
        video_map = "[v]"
    elif has_pip:
        filter_parts.append(f"[1:v]scale={webcam_scale}:-1[cam]")
        overlay_pos = _WEBCAM_CORNER_OVERLAY.get(
            webcam_corner, _WEBCAM_CORNER_OVERLAY["bottom-right"]
        )
        filter_parts.append(f"[0:v][cam]overlay={overlay_pos}[v]")
        video_map = "[v]"
    elif has_crop:
        filter_parts.append(
            f"[0:v]crop={int(crop['w'])}:{int(crop['h'])}:"
            f"{int(crop['x'])}:{int(crop['y'])}[v]"
        )
        video_map = "[v]"

    # Audio metering: rendered as a labeled chain in filter_complex when
    # we have a graph, or as a simple -af otherwise.
    if filter_parts and audio_input:
        filter_parts.append(
            "[0:a]astats=metadata=1:reset=1,"
            "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-[a]"
        )

    if filter_parts:
        cmd += ["-filter_complex", ";".join(filter_parts)]
        cmd += ["-map", video_map]
        if audio_input:
            cmd += ["-map", "[a]"]
    elif audio_input:
        # Simple path (Phase 1 baseline): plain -af on the implicit audio.
        cmd += [
            "-af",
            "astats=metadata=1:reset=1,"
            "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
        ]

    # ── Encoder settings (always) ──────────────────────────────────────
    cmd += [
        "-c:v", "h264_videotoolbox",
        "-b:v", "30M",
        "-allow_sw", "1",
        "-realtime", "1",
        "-pix_fmt", "yuv420p",
    ]
    if audio_input:
        cmd += ["-c:a", "aac", "-ar", "44100", "-ac", "2"]

    cmd.append(str(segment_path))
    return cmd

    if system == "Windows":  # pragma: no cover — Phase 10
        raise NotImplementedError("Windows capture lands in Phase 10")

    raise RuntimeError(f"Unsupported capture platform: {system}")


# ── stderr / stdout parsers (run in background threads) ──────────────────────

_TIME_RE = re.compile(r"time=(\d+):(\d{2}):(\d{2})\.(\d+)")
_RMS_RE = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?\d+(?:\.\d+)?)")


def _parse_time_to_ms(match: re.Match) -> float:
    h = int(match.group(1))
    m = int(match.group(2))
    s = int(match.group(3))
    frac = match.group(4)
    frac_ms = int(round(float("0." + frac) * 1000))
    return ((h * 3600) + (m * 60) + s) * 1000.0 + frac_ms


def _drain_stderr(capture: _Capture, manager: "CaptureManager", stream) -> None:
    """Read FFmpeg stderr; parse `time=` for duration. Retain the trailing
    portion so failed captures can surface FFmpeg's diagnostics."""
    tail: list[str] = []
    try:
        for raw in iter(stream.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace")
            except Exception:
                continue
            # Keep last ~80 lines for failure diagnostics. Bounded so a
            # long capture doesn't accumulate megabytes.
            tail.append(line)
            if len(tail) > 80:
                tail.pop(0)
            tm = _TIME_RE.search(line)
            if tm:
                segment_ms = _parse_time_to_ms(tm)
                total_ms = capture.paused_offset_ms + segment_ms
                capture.last_duration_ms = total_ms
                manager._broadcast({
                    "type": "duration",
                    "capture_id": capture.capture_id,
                    "duration_ms": total_ms,
                })
    except Exception as e:
        capture.last_error = f"stderr-drain: {e}"
    finally:
        # Always retain the tail so callers (stop_capture, get_state) have
        # something to show when a segment dies before writing data.
        capture.last_stderr_tail = "".join(tail)


def _drain_stdout(capture: _Capture, manager: "CaptureManager", stream) -> None:
    """Read FFmpeg stdout; parse audio RMS lines from the ametadata filter."""
    try:
        for raw in iter(stream.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace")
            except Exception:
                continue
            rms = _RMS_RE.search(line)
            if rms:
                try:
                    db = float(rms.group(1))
                except ValueError:
                    continue
                capture.last_rms_level_db = db
                manager._broadcast({
                    "type": "level",
                    "capture_id": capture.capture_id,
                    "rms_db": db,
                })
    except Exception as e:
        capture.last_error = f"stdout-drain: {e}"


# ── CaptureManager ───────────────────────────────────────────────────────────

class CaptureManager:
    """Single instance manages all active captures.

    Construct once at server startup; expose via :func:`get_default_manager`.
    """

    def __init__(self, default_capture_dir: Path | None = None) -> None:
        self._captures: dict[str, _Capture] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[dict], None]] = []
        self._default_capture_dir = default_capture_dir or DEFAULT_CAPTURE_DIR
        self._default_capture_dir.mkdir(parents=True, exist_ok=True)

    # ── pub/sub ──────────────────────────────────────────────────────────────

    def subscribe(self, handler: Callable[[dict], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(handler)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(handler)
                except ValueError:
                    pass

        return _unsubscribe

    def _broadcast(self, event: dict) -> None:
        # Snapshot subscribers under lock; call handlers outside the lock so
        # a slow handler doesn't block emitters.
        with self._lock:
            handlers = list(self._subscribers)
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start_capture(
        self,
        conversation_id: str,
        options: dict | None = None,
    ) -> str:
        """Begin a new capture for ``conversation_id``.

        Returns the new ``capture_id``. Spawns the first FFmpeg segment.
        """
        opts = dict(options or {})
        tag = (get_conversation_tag(conversation_id) or "").strip()

        if tag == "stealth":
            capture_dir = SESSIONS_ROOT / conversation_id / "captures"
        else:
            capture_dir = self._default_capture_dir
        capture_dir.mkdir(parents=True, exist_ok=True)

        capture_id = uuid.uuid4().hex[:12]
        capture = _Capture(
            capture_id=capture_id,
            conversation_id=conversation_id,
            tag=tag,
            options=opts,
            capture_dir=capture_dir,
        )
        with self._lock:
            self._captures[capture_id] = capture

        self._launch_segment(capture)
        self._broadcast({
            "type": "started",
            "capture_id": capture_id,
            "conversation_id": conversation_id,
            "tag": tag,
            "capture_dir": str(capture_dir),
        })
        return capture_id

    def pause_capture(self, capture_id: str) -> None:
        capture = self._require(capture_id)
        if capture.state != STATE_RECORDING:
            return
        self._stop_segment_gracefully(capture)
        capture.state = STATE_PAUSED
        self._broadcast({
            "type": "paused",
            "capture_id": capture_id,
            "duration_ms": capture.last_duration_ms,
        })

    def resume_capture(self, capture_id: str) -> None:
        capture = self._require(capture_id)
        if capture.state != STATE_PAUSED:
            return
        self._launch_segment(capture)
        self._broadcast({
            "type": "resumed",
            "capture_id": capture_id,
        })

    def stop_capture(self, capture_id: str) -> dict:
        """Finalize the capture and return ``{file_path, duration_ms}``."""
        capture = self._require(capture_id)
        if capture.state == STATE_RECORDING:
            self._stop_segment_gracefully(capture)
        capture.state = STATE_STOPPING

        try:
            final_path = self._concat_segments(capture)
            capture.final_file_path = final_path
            capture.state = STATE_COMPLETE
            self._broadcast({
                "type": "complete",
                "capture_id": capture_id,
                "file_path": str(final_path),
                "duration_ms": capture.last_duration_ms,
            })
            return {
                "file_path": str(final_path),
                "duration_ms": capture.last_duration_ms,
                "tag": capture.tag,
            }
        except Exception as e:
            capture.state = STATE_FAILED
            capture.last_error = str(e)
            self._broadcast({
                "type": "failed",
                "capture_id": capture_id,
                "error": str(e),
            })
            raise

    def get_state(self, capture_id: str) -> dict:
        capture = self._require(capture_id)
        return {
            "capture_id": capture.capture_id,
            "conversation_id": capture.conversation_id,
            "tag": capture.tag,
            "state": capture.state,
            "duration_ms": capture.last_duration_ms,
            "rms_level_db": capture.last_rms_level_db,
            "segment_count": len(capture.segment_paths),
            "capture_dir": str(capture.capture_dir),
            "final_file_path": (
                str(capture.final_file_path) if capture.final_file_path else None
            ),
            "last_error": capture.last_error,
        }

    def list_captures(self) -> list[dict]:
        with self._lock:
            ids = list(self._captures.keys())
        return [self.get_state(cid) for cid in ids]

    # ── internals ────────────────────────────────────────────────────────────

    def _require(self, capture_id: str) -> _Capture:
        with self._lock:
            cap = self._captures.get(capture_id)
        if not cap:
            raise KeyError(f"unknown capture_id: {capture_id}")
        return cap

    def _launch_segment(self, capture: _Capture) -> None:
        seg_index = len(capture.segment_paths)
        segment_path = capture.capture_dir / f"{capture.capture_id}-segment-{seg_index}.mp4"
        capture.segment_paths.append(segment_path)

        argv = _build_ffmpeg_command(capture, segment_path)
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        capture.current_process = proc
        capture.state = STATE_RECORDING
        capture.last_segment_started_at = time.time()
        if capture.started_at == 0.0:
            capture.started_at = capture.last_segment_started_at

        # Background readers for stderr (duration) and stdout (RMS levels).
        t_err = threading.Thread(
            target=_drain_stderr,
            args=(capture, self, proc.stderr),
            name=f"capture-stderr-{capture.capture_id}",
            daemon=True,
        )
        t_out = threading.Thread(
            target=_drain_stdout,
            args=(capture, self, proc.stdout),
            name=f"capture-stdout-{capture.capture_id}",
            daemon=True,
        )
        capture._stderr_thread = t_err
        capture._stdout_thread = t_out
        t_err.start()
        t_out.start()

    def _stop_segment_gracefully(self, capture: _Capture) -> None:
        proc = capture.current_process
        if not proc:
            return
        try:
            # FFmpeg honors a "q" on stdin as a clean shutdown request — it
            # finalizes the muxer (writes the moov atom for MP4) before
            # exiting. SIGTERM truncates the file mid-frame, which produces
            # files that won't play.
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        finally:
            capture.paused_offset_ms = capture.last_duration_ms
            capture.current_process = None

    def _concat_segments(self, capture: _Capture) -> Path:
        """Concatenate per-segment files into the final capture file."""
        segments = [p for p in capture.segment_paths if p.exists() and p.stat().st_size > 0]
        if not segments:
            tail = (capture.last_stderr_tail or "")[-1500:]
            raise RuntimeError(
                "no segments produced — capture failed before writing any data. "
                "FFmpeg stderr tail:\n" + tail
            )

        final_path = capture.capture_dir / f"{capture.capture_id}.mp4"

        if len(segments) == 1:
            # Single segment — just rename. No concat needed.
            segments[0].replace(final_path)
            return final_path

        # Multi-segment concat via FFmpeg's concat demuxer.
        list_file = capture.capture_dir / f"{capture.capture_id}-concat.txt"
        try:
            with list_file.open("w", encoding="utf-8") as f:
                for seg in segments:
                    # Concat demuxer requires the safe-but-quoted path syntax.
                    f.write(f"file '{seg.as_posix()}'\n")

            argv = [
                FFMPEG_BINARY,
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(final_path),
            ]
            result = subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"concat failed (rc={result.returncode}): {result.stderr.decode('utf-8', 'replace')[-500:]}"
                )
        finally:
            try:
                list_file.unlink()
            except FileNotFoundError:
                pass

        # Remove per-segment files now that the final exists.
        for seg in segments:
            try:
                seg.unlink()
            except FileNotFoundError:
                pass

        return final_path


# ── Module-level singleton ───────────────────────────────────────────────────

_default_manager: CaptureManager | None = None
_default_manager_lock = threading.Lock()


def get_default_manager() -> CaptureManager:
    """Return the process-wide :class:`CaptureManager`, creating it on first call."""
    global _default_manager
    with _default_manager_lock:
        if _default_manager is None:
            _default_manager = CaptureManager()
        return _default_manager


# ── Device discovery (avfoundation list parser) ─────────────────────────────

_AVF_LINE = re.compile(r"\[(\d+)\]\s+(.+)$")


def list_avfoundation_devices() -> dict:
    """Run ``ffmpeg -f avfoundation -list_devices true -i ""`` and parse output.

    Returns ``{"video": [{"index": int, "name": str}, ...], "audio": [...]}``.
    Empty lists if FFmpeg or avfoundation is unavailable.
    """
    if platform.system() != "Darwin":
        return {"video": [], "audio": []}
    try:
        result = subprocess.run(
            [FFMPEG_BINARY, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except Exception:
        return {"video": [], "audio": []}

    text = result.stderr.decode("utf-8", errors="replace")
    section = None  # "video" | "audio"
    out = {"video": [], "audio": []}
    for line in text.splitlines():
        if "AVFoundation video devices" in line:
            section = "video"
            continue
        if "AVFoundation audio devices" in line:
            section = "audio"
            continue
        if section is None:
            continue
        m = _AVF_LINE.search(line.strip())
        if m:
            try:
                out[section].append({"index": int(m.group(1)), "name": m.group(2).strip()})
            except (ValueError, KeyError):
                pass
    return out


def capture_region_snapshot(video_device: str | int, target: Path) -> bool:
    """Grab a single still frame from a video device into ``target`` JPEG.

    Used by the Phase 4 region-selection flow: the client picks a screen,
    Ora pulls one frame, the user drags a rectangle on the still in the
    visual pane, and the resulting coordinates feed the capture's `crop`
    option on Start.

    Returns True on success.
    """
    if platform.system() != "Darwin":
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-f", "avfoundation",
        "-framerate", "30",
        "-pix_fmt", "uyvy422",
        "-capture_cursor", "0",
        "-i", str(video_device),
        "-frames:v", "1",
        "-q:v", "5",
        str(target),
    ]
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15)
    except Exception:
        return False
    return (result.returncode == 0 and target.exists() and target.stat().st_size > 0)


__all__ = [
    "CaptureManager",
    "get_default_manager",
    "list_avfoundation_devices",
    "capture_region_snapshot",
    "STATE_IDLE",
    "STATE_RECORDING",
    "STATE_PAUSED",
    "STATE_STOPPING",
    "STATE_COMPLETE",
    "STATE_FAILED",
]
