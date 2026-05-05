"""User settings persistence — Audio/Video Phase 9.

Single source of truth for user-configurable defaults that don't
belong in env vars or per-conversation state. Read/written through
``~/ora/config/user-settings.json``. Secrets (API keys) are NOT
stored here; they live in the system keyring.

Sections
--------
* ``capture`` — default directory, frame rate, audio device, system-audio default, webcam default
* ``whisper`` — model size, default language
* ``export`` — default directory, default render preset, background-render threshold
* ``external_apis`` — provider enable flags + non-secret routing (the
  actual keys live in keyring; this section just records "do we want
  to attempt this provider at runtime")

Schema is forward-compatible: unknown keys are preserved on round-trip
so older clients can't accidentally truncate fields newer servers
write.

Public surface
--------------
``load_settings() -> dict`` — current settings, with defaults filled in
``save_settings(updates: dict) -> dict`` — deep-merge updates and persist
``reset_settings() -> dict`` — clear back to defaults
``get_setting(path: str, default=None)`` — dotted-path getter
``set_api_key(provider: str, value: str)`` — keyring write
``delete_api_key(provider: str)`` — keyring delete
``api_key_present(provider: str) -> bool`` — for the UI's "key set" indicator

Provider whitelist for the API key endpoints — keeps the surface
typo-resistant and prevents arbitrary keyring writes via the API.
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────

_CONFIG_DIR = Path.home() / "ora" / "config"
_SETTINGS_PATH = _CONFIG_DIR / "user-settings.json"

# ── defaults ────────────────────────────────────────────────────────────────

DEFAULTS: dict = {
    "version": 1,
    "capture": {
        "default_directory": str(Path.home() / "ora" / "captures"),
        "frame_rate": 30,
        "default_audio_device": "",       # "" = system default
        "default_system_audio": False,
        "default_webcam_device": "",
    },
    "whisper": {
        "model_size": "large-v3",
        "default_language": "auto",        # "auto" | "en" | "fr" | etc.
    },
    "export": {
        "default_directory": str(Path.home() / "ora" / "exports"),
        "default_render_preset": "standard",
        "background_render_threshold_seconds": 90,
    },
    "external_apis": {
        "transcription_provider": "whisper_local",   # whisper_local | assemblyai | deepgram
        "tts_provider": "openai",                    # openai | elevenlabs
    },
    "interface": {
        # Universal hover tooltips on every interactive element. When
        # off, the helper restores native browser title attributes so
        # the user still sees something on hover (just OS-styled).
        "tooltips_enabled": True,
    },
}

# Whitelisted providers for keyring writes/reads.
# Maps provider id → keyring username (under service "ora").
PROVIDER_KEYRING_USERNAME = {
    "anthropic": "anthropic-api-key",
    "openai": "openai-api-key",
    "gemini": "gemini-api-key",
    "assemblyai": "assemblyai-api-key",
    "deepgram": "deepgram-api-key",
    "elevenlabs": "elevenlabs-api-key",
    # OpenAI TTS uses the same key as OpenAI.
}

# Sub-set of providers whose keys are *labelled* in the UI (display order).
PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (chat / vision / TTS)",
    "gemini": "Google Gemini",
    "assemblyai": "AssemblyAI (transcription)",
    "deepgram": "Deepgram (transcription)",
    "elevenlabs": "ElevenLabs (TTS)",
}

_KEYRING_SERVICE = "ora"
_lock = threading.Lock()


class SettingsError(Exception):
    pass


# ── settings persistence ────────────────────────────────────────────────────

def _ensure_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _read_raw() -> dict:
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError as e:
        raise SettingsError(f"settings file is not valid JSON: {e}") from e


def _write_raw(data: dict) -> None:
    _ensure_dir()
    tmp = _SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_SETTINGS_PATH)


def _deep_merge(base: dict, overrides: dict) -> dict:
    """Merge overrides into base. Nested dicts merged; leaves replaced."""
    result = copy.deepcopy(base)
    for k, v in overrides.items():
        if (
            k in result
            and isinstance(result[k], dict)
            and isinstance(v, dict)
        ):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def load_settings() -> dict:
    """Return current settings with defaults filled in for missing keys.

    Forward-compatible: if the on-disk file has keys not in DEFAULTS,
    they're preserved and returned alongside the defaults.
    """
    with _lock:
        raw = _read_raw()
    return _deep_merge(DEFAULTS, raw)


def save_settings(updates: dict) -> dict:
    """Merge ``updates`` into stored settings, persist, return new state.

    Validates known sections; rejects type-mismatched leaves rather
    than silently writing garbage.
    """
    if not isinstance(updates, dict):
        raise SettingsError("updates must be a dict")
    _validate_updates(updates)
    with _lock:
        existing = _read_raw()
        merged = _deep_merge(existing, updates)
        _write_raw(merged)
    # Returned with defaults filled in for callers that need a complete view.
    return _deep_merge(DEFAULTS, merged)


def reset_settings() -> dict:
    """Drop the on-disk settings entirely. Defaults take over."""
    with _lock:
        if _SETTINGS_PATH.exists():
            _SETTINGS_PATH.unlink()
    return copy.deepcopy(DEFAULTS)


def get_setting(path: str, default=None):
    """Dotted-path getter, e.g. ``get_setting('whisper.model_size')``."""
    cur = load_settings()
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _validate_updates(updates: dict) -> None:
    """Type-check the known leaf keys."""
    cap = updates.get("capture") or {}
    if "frame_rate" in cap:
        fr = cap["frame_rate"]
        if not isinstance(fr, int) or fr not in (24, 25, 30, 50, 60):
            raise SettingsError(
                f"capture.frame_rate must be one of 24/25/30/50/60 (got {fr!r})"
            )
    if "default_system_audio" in cap and not isinstance(
        cap["default_system_audio"], bool
    ):
        raise SettingsError("capture.default_system_audio must be a boolean")

    wh = updates.get("whisper") or {}
    if "model_size" in wh and wh["model_size"] not in (
        "tiny", "base", "small", "medium", "large-v3"
    ):
        raise SettingsError(
            f"whisper.model_size must be one of tiny/base/small/medium/large-v3 "
            f"(got {wh['model_size']!r})"
        )

    ex = updates.get("export") or {}
    if "background_render_threshold_seconds" in ex:
        v = ex["background_render_threshold_seconds"]
        if not isinstance(v, int) or v < 0 or v > 7200:
            raise SettingsError(
                "export.background_render_threshold_seconds must be 0..7200"
            )
    if "default_render_preset" in ex:
        # Mirrors render.py's PRESETS keys (excluding internal preview_proxy).
        valid = ("standard", "high", "web", "mov", "webm", "audio_only")
        if ex["default_render_preset"] not in valid:
            raise SettingsError(
                f"export.default_render_preset must be one of {valid} "
                f"(got {ex['default_render_preset']!r})"
            )

    ap = updates.get("external_apis") or {}
    if "transcription_provider" in ap and ap["transcription_provider"] not in (
        "whisper_local", "assemblyai", "deepgram"
    ):
        raise SettingsError(
            "external_apis.transcription_provider must be one of "
            "whisper_local / assemblyai / deepgram"
        )
    if "tts_provider" in ap and ap["tts_provider"] not in (
        "openai", "elevenlabs"
    ):
        raise SettingsError(
            "external_apis.tts_provider must be one of openai / elevenlabs"
        )


# ── API key handling (keyring) ──────────────────────────────────────────────

def _provider_username(provider: str) -> str:
    if provider not in PROVIDER_KEYRING_USERNAME:
        raise SettingsError(f"unknown provider: {provider!r}")
    return PROVIDER_KEYRING_USERNAME[provider]


def set_api_key(provider: str, value: str) -> None:
    """Store an API key for ``provider`` in the system keyring."""
    if not value:
        raise SettingsError("api key value cannot be empty")
    import keyring  # pulled lazily so tests can stub via sys.modules
    keyring.set_password(_KEYRING_SERVICE, _provider_username(provider), value)


def delete_api_key(provider: str) -> None:
    """Remove an API key for ``provider`` from the keyring (if present)."""
    import keyring
    try:
        keyring.delete_password(_KEYRING_SERVICE, _provider_username(provider))
    except Exception:
        # Keyring backends raise different exceptions for "not found".
        # Treat all of them as "already absent."
        pass


def api_key_present(provider: str) -> bool:
    """Return True if ``provider``'s key is set in the keyring (no value leak)."""
    import keyring
    try:
        return bool(
            keyring.get_password(_KEYRING_SERVICE, _provider_username(provider))
        )
    except Exception:
        return False


def list_api_key_status() -> list[dict]:
    """Return a per-provider list of ``{provider, label, present}`` rows."""
    rows = []
    for provider, label in PROVIDER_LABELS.items():
        rows.append({
            "provider": provider,
            "label": label,
            "present": api_key_present(provider),
        })
    return rows


__all__ = [
    "DEFAULTS",
    "PROVIDER_LABELS",
    "PROVIDER_KEYRING_USERNAME",
    "SettingsError",
    "load_settings",
    "save_settings",
    "reset_settings",
    "get_setting",
    "set_api_key",
    "delete_api_key",
    "api_key_present",
    "list_api_key_status",
]
