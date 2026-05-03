"""URL-import subsystem — Audio/Video Phase 8 follow-up.

Wraps ``yt-dlp`` (Homebrew-installed) as a subprocess to download a
public video/audio URL and register it with the per-conversation
media library. Handles YouTube, Vimeo, Twitter, podcast RSS feeds,
and the ~1500 other sources yt-dlp covers.

Two-step flow per import:

1. ``yt-dlp --dump-json --no-download <url>`` to fetch metadata
   (title, duration, upload_date, video id). Fast — seconds.
2. ``yt-dlp -o '<dir>/%(id)s.%(ext)s' --merge-output-format mp4
   --newline <url>`` for the actual download. Progress lines are
   parsed from stdout/stderr and broadcast as events.

On completion the file lands at
``~/ora/sessions/<conversation_id>/imports/<video_id>.mp4`` and a
new media-library entry is created with ``display_name`` set to the
upstream title.

Public surface
--------------
``URLImportManager.start(conversation_id, url) -> import_id``
``URLImportManager.get_state(import_id) -> dict``
``URLImportManager.subscribe(callback) -> unsubscribe``
``get_default_manager() -> URLImportManager``

Failure modes are surfaced via the ``state`` field on the returned
dict: ``queued`` → ``fetching_metadata`` → ``downloading`` →
``registering`` → ``complete`` | ``failed``.
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
from typing import Callable, Iterable

# ── locate yt-dlp ────────────────────────────────────────────────────────────

YTDLP_BINARY = shutil.which("yt-dlp") or "/opt/homebrew/bin/yt-dlp"

# ── states ──────────────────────────────────────────────────────────────────

STATE_QUEUED = "queued"
STATE_FETCHING_METADATA = "fetching_metadata"
STATE_DOWNLOADING = "downloading"
STATE_REGISTERING = "registering"
STATE_COMPLETE = "complete"
STATE_FAILED = "failed"


# ── per-import state ────────────────────────────────────────────────────────

@dataclass
class _Import:
    import_id: str
    conversation_id: str
    url: str
    output_dir: Path
    state: str = STATE_QUEUED
    title: str | None = None
    video_id: str | None = None
    duration_ms: int | None = None
    extractor: str | None = None
    progress_pct: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    eta_seconds: int | None = None
    output_path: Path | None = None
    library_entry_id: str | None = None
    last_error: str | None = None
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None


# Captures lines like:
#   [download]   2.5% of ~  10.50MiB at  1.20MiB/s ETA 00:08
_PROGRESS_RE = re.compile(
    r"\[download\]\s+"
    r"(?P<pct>[\d.]+)%"
    r"\s+of\s+~?\s*(?P<total>[\d.]+)(?P<total_unit>(?:[KMGT]i?)?B)"
    r"(?:\s+at\s+(?P<rate>[\d.]+)(?P<rate_unit>(?:[KMGT]i?)?B)/s)?"
    r"(?:\s+ETA\s+(?P<eta>[\d:]+))?"
)

_UNIT_FACTORS = {
    "B": 1,
    "KiB": 1024, "KB": 1000,
    "MiB": 1024 ** 2, "MB": 1000 ** 2,
    "GiB": 1024 ** 3, "GB": 1000 ** 3,
    "TiB": 1024 ** 4, "TB": 1000 ** 4,
}


def _to_bytes(value: float, unit: str) -> int:
    return int(value * _UNIT_FACTORS.get(unit, 1))


def _parse_eta(token: str) -> int | None:
    if not token:
        return None
    parts = token.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


# ── manager ─────────────────────────────────────────────────────────────────

class URLImportManager:
    """One instance per process. Tracks all in-flight imports."""

    def __init__(
        self,
        sessions_root: Path | None = None,
        media_library_factory: Callable | None = None,
    ) -> None:
        self._jobs: dict[str, _Import] = {}
        self._lock = threading.Lock()
        self._subs: list[Callable[[dict], None]] = []
        self._sessions_root = sessions_root or Path.home() / "ora" / "sessions"
        # Inject the media-library factory so tests can stub registration.
        self._lib_factory = media_library_factory

    # ── public API ───────────────────────────────────────────────────────

    def start(self, conversation_id: str, url: str) -> str:
        if not conversation_id:
            raise ValueError("conversation_id required")
        url = (url or "").strip()
        if not url:
            raise ValueError("url required")
        if not YTDLP_BINARY or not Path(YTDLP_BINARY).exists():
            raise RuntimeError(
                "yt-dlp binary not found. Install via `brew install yt-dlp`."
            )

        import_id = uuid.uuid4().hex[:12]
        output_dir = self._sessions_root / conversation_id / "imports"
        output_dir.mkdir(parents=True, exist_ok=True)

        job = _Import(
            import_id=import_id,
            conversation_id=conversation_id,
            url=url,
            output_dir=output_dir,
        )
        with self._lock:
            self._jobs[import_id] = job
        self._broadcast({
            "type": "queued",
            "import_id": import_id,
            "conversation_id": conversation_id,
            "url": url,
        })

        t = threading.Thread(
            target=self._run_import,
            args=(job,),
            name=f"url-import-{import_id}",
            daemon=True,
        )
        t.start()
        return import_id

    def get_state(self, import_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(import_id)
        if job is None:
            raise KeyError(f"unknown import_id: {import_id}")
        return self._snapshot(job)

    def list_states(self, conversation_id: str) -> list[dict]:
        with self._lock:
            jobs = [j for j in self._jobs.values()
                    if j.conversation_id == conversation_id]
        return [self._snapshot(j) for j in jobs]

    def subscribe(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        with self._lock:
            self._subs.append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                if callback in self._subs:
                    self._subs.remove(callback)

        return _unsubscribe

    # ── internals ────────────────────────────────────────────────────────

    def _snapshot(self, job: _Import) -> dict:
        return {
            "import_id": job.import_id,
            "conversation_id": job.conversation_id,
            "url": job.url,
            "state": job.state,
            "title": job.title,
            "video_id": job.video_id,
            "duration_ms": job.duration_ms,
            "extractor": job.extractor,
            "progress_pct": round(job.progress_pct, 2),
            "downloaded_bytes": job.downloaded_bytes,
            "total_bytes": job.total_bytes,
            "eta_seconds": job.eta_seconds,
            "output_path": str(job.output_path) if job.output_path else None,
            "library_entry_id": job.library_entry_id,
            "last_error": job.last_error,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        }

    def _broadcast(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(event)
            except Exception:
                pass

    def _fail(self, job: _Import, error: str) -> None:
        job.state = STATE_FAILED
        job.last_error = error
        job.completed_at = time.time()
        self._broadcast({
            "type": "failed",
            "import_id": job.import_id,
            "error": error,
        })

    def _run_import(self, job: _Import) -> None:
        try:
            # Step 1 — fetch metadata.
            job.state = STATE_FETCHING_METADATA
            self._broadcast({
                "type": "metadata_started",
                "import_id": job.import_id,
            })
            try:
                meta = self._fetch_metadata(job.url)
            except Exception as e:
                self._fail(job, f"metadata: {e}")
                return

            job.title = meta.get("title")
            job.video_id = meta.get("id")
            job.extractor = meta.get("extractor_key") or meta.get("extractor")
            duration = meta.get("duration")
            if duration is not None:
                try:
                    job.duration_ms = int(float(duration) * 1000)
                except (ValueError, TypeError):
                    pass

            self._broadcast({
                "type": "metadata_ready",
                "import_id": job.import_id,
                "title": job.title,
                "video_id": job.video_id,
                "duration_ms": job.duration_ms,
            })

            # Step 2 — download.
            job.state = STATE_DOWNLOADING
            self._broadcast({
                "type": "download_started",
                "import_id": job.import_id,
            })

            try:
                final_path = self._download(job)
            except Exception as e:
                self._fail(job, f"download: {e}")
                return

            if final_path is None or not final_path.exists():
                self._fail(job, "download finished but no output file found")
                return
            job.output_path = final_path

            # Step 3 — register with media library.
            job.state = STATE_REGISTERING
            self._broadcast({
                "type": "registering",
                "import_id": job.import_id,
            })

            try:
                entry = self._register_with_library(job)
            except Exception as e:
                # Download succeeded but library registration failed; surface
                # the file path so the user can recover manually.
                self._fail(job, f"library register: {e}")
                return

            job.library_entry_id = entry.get("id") if entry else None
            job.state = STATE_COMPLETE
            job.progress_pct = 100.0
            job.completed_at = time.time()
            self._broadcast({
                "type": "complete",
                "import_id": job.import_id,
                "library_entry_id": job.library_entry_id,
                "output_path": str(job.output_path),
            })
        except Exception as e:
            self._fail(job, f"unexpected: {e}")

    def _fetch_metadata(self, url: str) -> dict:
        proc = subprocess.run(
            [
                YTDLP_BINARY,
                "--dump-json",
                "--no-download",
                "--no-warnings",
                "--quiet",
                url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-600:]
            raise RuntimeError(
                f"yt-dlp metadata fetch failed (rc={proc.returncode}): {tail}"
            )
        out = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        # When the URL is a playlist, --dump-json emits one JSON per line.
        # Take the first entry — playlist support is a future enhancement.
        first_line = out.split("\n", 1)[0] if out else ""
        if not first_line:
            raise RuntimeError("yt-dlp returned no metadata")
        return json.loads(first_line)

    def _download(self, job: _Import) -> Path | None:
        out_template = str(job.output_dir / "%(id)s.%(ext)s")
        cmd = [
            YTDLP_BINARY,
            "-o", out_template,
            "--no-playlist",
            "--newline",
            "--no-warnings",
            "--merge-output-format", "mp4",
            "--print", "after_move:filepath",
            job.url,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        final_path: Path | None = None
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            self._handle_progress_line(job, line)
            # `--print after_move:filepath` writes the final path on its own
            # line; it may be interleaved with download progress.
            stripped = line.strip()
            if stripped and (
                stripped.startswith(str(job.output_dir))
                or stripped.startswith(os.fspath(job.output_dir))
            ):
                p = Path(stripped)
                if p.exists():
                    final_path = p
        proc.wait(timeout=10)
        if proc.returncode != 0:
            raise RuntimeError(
                f"yt-dlp exited with rc={proc.returncode}"
            )
        if final_path is None and job.video_id:
            # Fall back to scanning the output dir for the video id.
            for ext in ("mp4", "webm", "mkv", "m4a", "mp3"):
                candidate = job.output_dir / f"{job.video_id}.{ext}"
                if candidate.exists():
                    final_path = candidate
                    break
        return final_path

    def _handle_progress_line(self, job: _Import, line: str) -> None:
        m = _PROGRESS_RE.search(line)
        if m is None:
            return
        try:
            pct = float(m.group("pct"))
        except (TypeError, ValueError):
            return
        total_val = m.group("total")
        total_unit = m.group("total_unit")
        eta = _parse_eta(m.group("eta") or "")
        total_bytes = None
        if total_val and total_unit:
            try:
                total_bytes = _to_bytes(float(total_val), total_unit)
            except (TypeError, ValueError):
                total_bytes = None
        downloaded = int((pct / 100.0) * total_bytes) if total_bytes else 0

        # Throttle: only broadcast on whole-percent ticks to avoid event flood.
        prev_int_pct = int(job.progress_pct)
        new_int_pct = int(pct)

        job.progress_pct = pct
        job.total_bytes = total_bytes
        job.downloaded_bytes = downloaded
        job.eta_seconds = eta

        if new_int_pct != prev_int_pct:
            self._broadcast({
                "type": "progress",
                "import_id": job.import_id,
                "progress_pct": pct,
                "downloaded_bytes": downloaded,
                "total_bytes": total_bytes,
                "eta_seconds": eta,
            })

    def _register_with_library(self, job: _Import) -> dict | None:
        # Lazy import so the test suite can stub via media_library_factory
        # without tripping side effects of media_library import.
        if self._lib_factory is not None:
            lib = self._lib_factory(job.conversation_id)
        else:
            from media_library import get_library  # type: ignore
            lib = get_library(job.conversation_id)
        if job.output_path is None:
            return None
        display_name = job.title or job.output_path.stem
        return lib.add_entry(
            source_path=str(job.output_path),
            display_name=display_name,
        )


# ── module-level singleton ───────────────────────────────────────────────────

_default_manager: URLImportManager | None = None
_default_lock = threading.Lock()


def get_default_manager() -> URLImportManager:
    global _default_manager
    with _default_lock:
        if _default_manager is None:
            _default_manager = URLImportManager()
        return _default_manager


__all__ = [
    "URLImportManager",
    "get_default_manager",
    "STATE_QUEUED",
    "STATE_FETCHING_METADATA",
    "STATE_DOWNLOADING",
    "STATE_REGISTERING",
    "STATE_COMPLETE",
    "STATE_FAILED",
]
