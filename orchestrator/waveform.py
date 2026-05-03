"""Audio waveform thumbnail generator — Audio/Video Phase 5+ polish.

Wraps ``ffmpeg ... -filter_complex showwavespic`` to render a small PNG
of a media file's audio waveform. Used by the media library to show
audio entries (and video entries' audio tracks) at-a-glance instead
of a generic glyph.

Generated PNGs are cached next to the existing thumbnail files at
``~/ora/sessions/<conv_id>/thumbnails/<entry_id>.waveform.png``. The
endpoint that serves them is lazy: first hit generates, subsequent
hits stream the cached file.

Public surface
--------------
``render_waveform(source, output, *, width, height, color) -> bool``
    Synchronous ffmpeg call. Returns True on success.
``waveform_cache_path(thumbnails_dir, entry_id) -> Path``
    The canonical cache location for a given entry's waveform.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Resolve the ffmpeg used elsewhere in the project. ``transcription.py``
# uses whisper-cli + a sibling ffmpeg — we follow the same lookup so a
# user with the homebrew-ffmpeg/ffmpeg/ffmpeg tap (required for
# drawtext) gets that build for waveform rendering too.
FFMPEG_BINARY = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def waveform_cache_path(thumbnails_dir: Path, entry_id: str) -> Path:
    """Where the cached waveform PNG for an entry lives on disk."""
    return Path(thumbnails_dir) / f"{entry_id}.waveform.png"


def render_waveform(
    source: Path,
    output: Path,
    *,
    width: int = 400,
    height: int = 80,
    color: str = "0xbd93f9",
    timeout: float = 30.0,
) -> bool:
    """Render a waveform PNG of ``source`` to ``output``.

    Synchronous. ffmpeg runs as a subprocess; a typical 10-minute audio
    file completes in ~200-500 ms on Apple Silicon. ``timeout`` exists
    so a corrupt input doesn't hang the request thread.

    Returns True on success, False on any failure (missing ffmpeg,
    non-zero exit, missing output file). The endpoint caller decides
    whether failure surfaces as 404 (no waveform yet) or 500.
    """
    src = Path(source)
    out = Path(output)
    if not src.exists():
        return False
    if not FFMPEG_BINARY or not Path(FFMPEG_BINARY).exists():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)

    # ``showwavespic`` accepts a hex color with leading 0x; the FFmpeg
    # docs and tests both use that form. Forcing s=WxH gives us a
    # predictable PNG. ``-frames:v 1`` is required because showwavespic
    # is a video filter that emits a single frame.
    filter_arg = (
        f"showwavespic=s={width}x{height}:colors={color}"
    )
    cmd = [
        FFMPEG_BINARY,
        "-y",                    # overwrite cached file if regenerating
        "-loglevel", "error",
        "-i", str(src),
        "-filter_complex", filter_arg,
        "-frames:v", "1",
        str(out),
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    if proc.returncode != 0:
        return False
    if not out.exists() or out.stat().st_size == 0:
        return False
    return True


__all__ = ["render_waveform", "waveform_cache_path", "FFMPEG_BINARY"]
