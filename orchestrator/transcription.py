"""Audio/video transcription subsystem — Audio/Video Phase 2.

Wraps ``whisper-cli`` (whisper.cpp, Homebrew-installed) as a subprocess.
Spawned per request and torn down on completion per the design's local-first
constraint. The pipeline is:

    1. ``ffmpeg`` extracts a normalized 16 kHz mono wav from the input
       (works for any audio or video format the codebase declares as
       supported in §D — MP3, M4A, WAV, FLAC, OGG, AAC, MP4, MOV, AVI,
       MKV, WebM).
    2. ``whisper-cli`` transcribes the wav and emits a structured JSON
       file with utterance-level segments and word-level confidence.
    3. The temp wav is removed; the JSON + cleaned text + metadata are
       returned to the caller.

Progress is parsed from whisper-cli's ``--print-progress`` output (lines
like ``whisper_print_progress_callback: progress = 27%``). Subscribers
receive ``transcription_event`` dicts via :meth:`TranscriptionManager.subscribe`.
The Flask SSE generator forwards them as ``transcription_status`` frames.

Public API
----------
``TranscriptionManager.start(source_path, options) -> transcription_id``
``TranscriptionManager.get_state(transcription_id) -> dict``
``TranscriptionManager.subscribe(handler) -> unsubscribe_callable``
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ── Module configuration ─────────────────────────────────────────────────────

WORKSPACE_ROOT = Path(os.path.expanduser("~/ora")).resolve()
WHISPER_MODELS_DIR = WORKSPACE_ROOT / "models" / "whisper"
WHISPER_BINARY = shutil.which("whisper-cli") or "/opt/homebrew/bin/whisper-cli"
FFMPEG_BINARY = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

DEFAULT_MODEL_FILENAME = "ggml-large-v3.bin"
DEFAULT_LANGUAGE = "auto"  # whisper auto-detect

STATE_QUEUED = "queued"
STATE_EXTRACTING = "extracting"  # ffmpeg pulling audio out of video / normalizing
STATE_TRANSCRIBING = "transcribing"
STATE_COMPLETE = "complete"
STATE_FAILED = "failed"


# ── Per-transcription state ──────────────────────────────────────────────────

@dataclass
class _Transcription:
    transcription_id: str
    source_path: Path
    options: dict
    state: str = STATE_QUEUED
    started_at: float = 0.0
    progress_pct: float = 0.0
    language: str | None = None
    duration_ms: float | None = None
    segments: list[dict] = field(default_factory=list)
    plain_text: str = ""
    last_error: str | None = None
    last_stderr_tail: str = ""
    output_json_path: Path | None = None
    # Count of segments dropped by the non-speech / hallucination filter,
    # surfaced via get_state for UI transparency. 0 when filtering is
    # disabled or no segments matched.
    hallucinations_filtered: int = 0


# ── Helpers ──────────────────────────────────────────────────────────────────

_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d+)\s*%")


# ── Hallucination filter (2026-05-01) ────────────────────────────────────────
#
# Whisper has a well-known failure mode where it emits trained-on-YouTube
# closing-credit phrases when fed silence, ambient noise, or non-speech
# audio. The training corpus contained millions of subtitles ending in
# "Thanks for watching!" / "Please subscribe" so the model defaults to
# those phrases when uncertain.
#
# This filter is conservative — it only drops segments whose normalized
# text exactly matches a curated short-list of high-signal hallucination
# phrases. It does NOT touch ambiguous strings like "thank you" or
# "[music]" that could legitimately appear in a real recording.
#
# A second pass drops adjacent duplicate segments only when the same
# normalized text repeats THREE or more times in a row — Whisper's other
# canonical failure mode is repetition loops on long silences. Two
# consecutive identical segments are kept (real speech can repeat).

_HALLUCINATION_PATTERNS: frozenset[str] = frozenset({
    "thanks for watching",
    "thanks for watching!",
    "thanks for watching.",
    "thank you for watching",
    "thank you for watching.",
    "thank you for watching!",
    "please subscribe",
    "please subscribe!",
    "please subscribe.",
    "please like and subscribe",
    "subscribe to my channel",
    "subscribe to my channel!",
    "subscribe to the channel",
    "subtitles by the amara.org community",
    "subtitles by amara.org",
    "subtitles by",
    "transcribed by",
    "translated by",
    "captions by",
    # Music-symbol-only segments — Whisper sometimes emits ♪ on silence.
    "♪",
    "♪♪",
    "♪♪♪",
    "♪ ♪",
    "♪ ♪ ♪",
})


def _normalize_for_hallucination_check(text: str) -> str:
    """Lower-case, strip whitespace, collapse internal whitespace."""
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _is_hallucination(text: str) -> bool:
    return _normalize_for_hallucination_check(text) in _HALLUCINATION_PATTERNS


def _filter_hallucinations(segments: list[dict]) -> tuple[list[dict], int]:
    """Drop segments matching a known hallucination pattern OR a third+
    consecutive identical-text repeat. Returns ``(kept_segments, drop_count)``.

    The function is pure (no side effects, no I/O) so it's cheap to test
    and safe to skip when the caller wants raw whisper output.
    """
    kept: list[dict] = []
    drops = 0
    last_norm: str | None = None
    consecutive: int = 0
    for seg in segments:
        text = (seg.get("text") or "")
        if _is_hallucination(text):
            drops += 1
            # Reset the repetition counter — the dropped segment shouldn't
            # count toward "consecutive identical" for following entries.
            last_norm = None
            consecutive = 0
            continue
        norm = _normalize_for_hallucination_check(text)
        if norm and norm == last_norm:
            consecutive += 1
            if consecutive >= 2:
                # 3rd or later identical occurrence — drop.
                drops += 1
                continue
        else:
            consecutive = 0
        kept.append(seg)
        last_norm = norm
    return kept, drops


def _resolve_model_path(options: dict) -> Path:
    """Resolve the .bin model file from options or default."""
    model_name = (options.get("model") or "").strip()
    if model_name:
        # Accept either a bare name like "large-v3" or "ggml-large-v3.bin"
        if not model_name.startswith("ggml-"):
            model_name = f"ggml-{model_name}.bin"
        if not model_name.endswith(".bin"):
            model_name = f"{model_name}.bin"
        candidate = WHISPER_MODELS_DIR / model_name
        if candidate.exists():
            return candidate
    default = WHISPER_MODELS_DIR / DEFAULT_MODEL_FILENAME
    if default.exists():
        return default
    raise FileNotFoundError(
        f"Whisper model not found. Looked in: {WHISPER_MODELS_DIR}. "
        f"Expected default: {DEFAULT_MODEL_FILENAME}. Download with:\n"
        f"  curl -L -o {default} "
        f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{DEFAULT_MODEL_FILENAME}"
    )


def _extract_to_wav(source: Path, target_wav: Path) -> None:
    """Run ffmpeg to produce a 16 kHz mono wav suitable for whisper-cli."""
    argv = [
        FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(source),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(target_wav),
    ]
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg extract failed (rc={result.returncode}): "
            f"{result.stderr.decode('utf-8', 'replace')[-500:]}"
        )


# ── TranscriptionManager ─────────────────────────────────────────────────────

class TranscriptionManager:
    """Single instance manages all in-flight transcriptions."""

    def __init__(self) -> None:
        self._jobs: dict[str, _Transcription] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[dict], None]] = []
        WHISPER_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # pub/sub ────────────────────────────────────────────────────────────────

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
        with self._lock:
            handlers = list(self._subscribers)
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass

    # public lifecycle ───────────────────────────────────────────────────────

    def start(self, source_path: str | Path, options: dict | None = None) -> str:
        """Begin a transcription. Runs in a background thread; returns immediately."""
        opts = dict(options or {})
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"source not found: {src}")

        transcription_id = uuid.uuid4().hex[:12]
        job = _Transcription(
            transcription_id=transcription_id,
            source_path=src,
            options=opts,
            started_at=time.time(),
        )
        with self._lock:
            self._jobs[transcription_id] = job

        self._broadcast({
            "type": "queued",
            "transcription_id": transcription_id,
            "source_path": str(src),
        })

        # Run in a background thread so the API call returns immediately.
        t = threading.Thread(
            target=self._run,
            args=(job,),
            name=f"transcribe-{transcription_id}",
            daemon=True,
        )
        t.start()
        return transcription_id

    def get_state(self, transcription_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(transcription_id)
        if not job:
            raise KeyError(f"unknown transcription_id: {transcription_id}")
        return {
            "transcription_id": job.transcription_id,
            "source_path": str(job.source_path),
            "state": job.state,
            "progress_pct": job.progress_pct,
            "language": job.language,
            "duration_ms": job.duration_ms,
            "segment_count": len(job.segments),
            "hallucinations_filtered": job.hallucinations_filtered,
            "plain_text": job.plain_text,
            "last_error": job.last_error,
            "output_json_path": str(job.output_json_path) if job.output_json_path else None,
        }

    # ── runner ───────────────────────────────────────────────────────────────

    def _run(self, job: _Transcription) -> None:
        try:
            model_path = _resolve_model_path(job.options)
        except FileNotFoundError as e:
            self._fail(job, f"missing model: {e}")
            return

        # Step 1 — extract to wav
        job.state = STATE_EXTRACTING
        self._broadcast({
            "type": "extracting",
            "transcription_id": job.transcription_id,
        })
        with tempfile.TemporaryDirectory(prefix="ora-whisper-") as tmpdir:
            tmpdir_path = Path(tmpdir)
            wav_path = tmpdir_path / "input.wav"
            try:
                _extract_to_wav(job.source_path, wav_path)
            except Exception as e:
                self._fail(job, str(e))
                return

            # Step 2 — transcribe
            job.state = STATE_TRANSCRIBING
            self._broadcast({
                "type": "transcribing",
                "transcription_id": job.transcription_id,
            })

            language = (job.options.get("language") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
            output_stem = tmpdir_path / "out"
            argv = [
                WHISPER_BINARY,
                "-m", str(model_path),
                "-f", str(wav_path),
                "-l", language,
                "-oj",                    # output JSON (machine-parseable)
                "-of", str(output_stem),  # base path for output files
                "-pp",                    # print-progress to stderr
                "-pc",                    # print colors disabled when redirected
                "-np",                    # no-prints (suppress final-text echo)
                "-t", "8",                # threads
            ]

            tail: list[str] = []
            try:
                proc = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,  # unbuffered binary; the drainer reads line-by-line
                )

                # Drain stderr in a thread so progress updates flow live.
                def _drain():
                    try:
                        for raw in iter(proc.stderr.readline, b""):
                            try:
                                line = raw.decode("utf-8", errors="replace")
                            except Exception:
                                continue
                            tail.append(line)
                            if len(tail) > 80:
                                tail.pop(0)
                            m = _PROGRESS_RE.search(line)
                            if m:
                                pct = float(m.group(1))
                                job.progress_pct = pct
                                self._broadcast({
                                    "type": "progress",
                                    "transcription_id": job.transcription_id,
                                    "progress_pct": pct,
                                })
                    except Exception as e:
                        job.last_error = f"stderr-drain: {e}"

                t_err = threading.Thread(target=_drain, daemon=True)
                t_err.start()

                # Drain stdout to keep the pipe from filling up (whisper-cli
                # may print results to stdout even with -np set).
                stdout_data, _ = proc.communicate()
                t_err.join(timeout=2.0)

                if proc.returncode != 0:
                    job.last_stderr_tail = "".join(tail)[-1500:]
                    self._fail(
                        job,
                        f"whisper-cli failed (rc={proc.returncode}). stderr tail:\n{job.last_stderr_tail}",
                    )
                    return
            except Exception as e:
                self._fail(job, f"whisper-cli exec: {e}")
                return

            # Step 3 — load the JSON output and persist a copy beside the source
            json_in_tmp = output_stem.with_suffix(".json")
            if not json_in_tmp.exists():
                self._fail(
                    job,
                    f"whisper-cli produced no JSON at {json_in_tmp}. stderr tail:\n{''.join(tail)[-800:]}",
                )
                return
            try:
                whisper_json = json.loads(json_in_tmp.read_text(encoding="utf-8"))
            except Exception as e:
                self._fail(job, f"json parse: {e}")
                return

            # Persist the JSON next to the source for posterity (so the user
            # can re-run downstream processing without re-transcribing).
            persistent_json = job.source_path.with_suffix(".whisper.json")
            try:
                persistent_json.write_text(json.dumps(whisper_json, indent=2), encoding="utf-8")
                job.output_json_path = persistent_json
            except Exception:
                # Non-fatal. Use the in-memory data.
                job.output_json_path = None

        self._populate_from_whisper_json(job, whisper_json)

        job.state = STATE_COMPLETE
        self._broadcast({
            "type": "complete",
            "transcription_id": job.transcription_id,
            "language": job.language,
            "duration_ms": job.duration_ms,
            "segment_count": len(job.segments),
            "hallucinations_filtered": job.hallucinations_filtered,
            "plain_text_chars": len(job.plain_text),
        })

    # ── helpers ──────────────────────────────────────────────────────────────

    def _fail(self, job: _Transcription, error: str) -> None:
        job.state = STATE_FAILED
        job.last_error = error
        self._broadcast({
            "type": "failed",
            "transcription_id": job.transcription_id,
            "error": error,
        })

    def _populate_from_whisper_json(self, job: _Transcription, data: dict) -> None:
        """Extract the bits we need from whisper.cpp's JSON shape.

        whisper.cpp -oj output looks like:
          {
            "result": {"language": "en"},
            "transcription": [
              {"timestamps": {"from": "00:00:00,000", "to": "00:00:05,000"},
               "offsets": {"from": 0, "to": 5000},
               "text": " Hello world."},
              ...
            ]
          }
        """
        result = data.get("result", {}) or {}
        job.language = result.get("language")

        segments_raw = data.get("transcription", []) or []
        last_offset_to = 0
        out_segments: list[dict] = []
        for seg in segments_raw:
            offsets = seg.get("offsets", {}) or {}
            start_ms = int(offsets.get("from") or 0)
            end_ms = int(offsets.get("to") or 0)
            text = (seg.get("text") or "").strip()
            out_segments.append({
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
            })
            if end_ms > last_offset_to:
                last_offset_to = end_ms

        # Apply the non-speech hallucination filter unless the caller
        # explicitly disabled it (options.disable_hallucination_filter).
        # Filtering is on by default — Whisper's "Thanks for watching!"
        # failure mode on silent audio is well-documented.
        opts = job.options or {}
        if opts.get("disable_hallucination_filter"):
            kept = out_segments
            drops = 0
        else:
            kept, drops = _filter_hallucinations(out_segments)
        job.segments = kept
        job.hallucinations_filtered = drops
        job.duration_ms = float(last_offset_to)
        # Whisper sometimes prepends a leading space to each segment; collapse
        # double-spaces and strip. Use the FILTERED segments so dropped
        # hallucinations don't bleed into plain_text either.
        joined = " ".join(seg.get("text", "") for seg in kept)
        job.plain_text = re.sub(r"\s+", " ", joined).strip()


# ── Module-level singleton ───────────────────────────────────────────────────

_default_manager: TranscriptionManager | None = None
_default_manager_lock = threading.Lock()


def get_default_manager() -> TranscriptionManager:
    global _default_manager
    with _default_manager_lock:
        if _default_manager is None:
            _default_manager = TranscriptionManager()
        return _default_manager


__all__ = [
    "TranscriptionManager",
    "get_default_manager",
    "STATE_QUEUED",
    "STATE_EXTRACTING",
    "STATE_TRANSCRIBING",
    "STATE_COMPLETE",
    "STATE_FAILED",
]
