"""Non-secret user-settings persistence for the Ora Settings modal.

Single source of truth for user-configurable defaults that don't
belong in env vars or per-conversation state. Read/written through
``~/ora/config/user-settings.json``. Secrets (API keys) are NOT
stored here; they live in the system keyring.

Sections
--------
* ``capture`` — default directory, frame rate, audio device, system-audio default, webcam default
* ``whisper`` — model size, default language
* ``export`` — default directory, default render preset, background-render threshold
* ``keyboard`` — per-command shortcut overrides used by the browser UI
* ``external_apis`` — non-secret provider choices (keys live in keyring)
* ``interface`` — tooltip/help affordances
* ``aside`` — dedicated scratchpad model choice
* ``styles`` — active output-style id, Persona id, and user-context toggle

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

# Provider registry is the single source of truth for which providers
# exist, their keyring usernames, labels, and signup/console metadata.
# Imported defensively because user_settings is loaded both as a bare
# module (orchestrator/ on sys.path) and as ``orchestrator.user_settings``.
try:  # pragma: no cover - import shim
    import provider_registry as _registry
except ImportError:  # pragma: no cover
    from orchestrator import provider_registry as _registry

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
        # NOTE: no "default_system_audio" — the checkbox it backed was
        # wired to nothing (FFmpeg's command builder has no system-audio
        # path; system audio needs a loopback device, which then appears
        # as an ordinary audio device above). Removed 2026-07-01.
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
        # NOTE: no "tts_provider" — it had zero runtime consumers (the
        # speech route reads speech.provider); removed 2026-07-01.
        # NOTE: deliberately no "aa_path" default. The Artificial
        # Analysis data path is auto-derived by the sync script from
        # key presence (keyring 'ora/aa-api-key' or AA_API_KEY env) —
        # a stored default here shadowed that auto-activation through
        # get_setting()'s deep merge and pinned every sync to the
        # scrape path (bug fixed 2026-07-01). ORA_AA_PATH / --aa-path
        # remain as expert overrides.
    },
    "interface": {
        # Universal hover tooltips on every interactive element. When
        # off, the helper restores native browser title attributes so
        # the user still sees something on hover (just OS-styled).
        "tooltips_enabled": True,
        # Optional visual-pane help/menu affordance. Off by default to
        # preserve the minimal canvas surface.
        "visual_help_enabled": False,
        # Keep the interface orienting controls visible by default. Users who
        # prefer the minimal presentation can opt into hover/focus reveal.
        "auto_hide_controls": False,
    },
    "aside": {
        # Dedicated default, intentionally independent of the active model
        # configuration's SMALL/utility selection. If unavailable at runtime,
        # /api/scratchpad logs loudly and falls back to that utility chain.
        "model_id": "gemini/gemini-3.1-flash-lite",
    },
    "keyboard": {
        # command_id -> shortcut string. Missing / null / "" means "use
        # the browser-side default from keyboard-shortcuts.js".
        "shortcuts": {},
    },
    "styles": {
        # Output Style framework. default_id is the account-wide default
        # Output Style profile id ("" = no style; a one-off /style overrides
        # it per turn). Ships defaulting to "explainer" so output is styled out
        # of the box. use_custom_values is the global modifier shown on the
        # Output Styles tab (wires in with mind.md onboarding). Register is
        # determined by the pipeline path (conversational at gears 1-2, written
        # at gears 3-4), not a stored toggle.
        "default_id": "explainer",
        "persona_id": "ora",
        "use_custom_values": False,
    },
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
    kb = updates.get("keyboard") or {}
    if "shortcuts" in kb and not isinstance(kb["shortcuts"], dict):
        raise SettingsError("keyboard.shortcuts must be a dict")

    interface = updates.get("interface")
    if interface is not None and not isinstance(interface, dict):
        raise SettingsError("interface must be an object")
    interface = interface or {}
    for key in ("tooltips_enabled", "visual_help_enabled", "auto_hide_controls"):
        if key in interface and not isinstance(interface[key], bool):
            raise SettingsError(f"interface.{key} must be a boolean")

    st = updates.get("styles") or {}
    if "default_id" in st and not isinstance(st["default_id"], str):
        raise SettingsError("styles.default_id must be a string ('' = none)")
    if "use_custom_values" in st and not isinstance(st["use_custom_values"], bool):
        raise SettingsError("styles.use_custom_values must be a boolean")

    aside = updates.get("aside")
    if aside is not None and not isinstance(aside, dict):
        raise SettingsError("aside must be an object")
    if isinstance(aside, dict) and "model_id" in aside:
        model_id = aside["model_id"]
        if not isinstance(model_id, str):
            raise SettingsError("aside.model_id must be a string")


# ── API key handling (keyring) ──────────────────────────────────────────────

def provider_ids() -> list[str]:
    """Return the current provider ids, including loaded feature providers."""
    return _registry.provider_ids()


def _provider_username(provider: str) -> str:
    declaration = _registry.by_id(provider)
    if declaration is None:
        raise SettingsError(f"unknown provider: {provider!r}")
    return declaration["keyring_username"]


def feature_credential(owner: str, credential_name: str) -> str | None:
    """Read only a provider credential explicitly declared by ``owner``."""
    import keyring

    try:
        username = _registry.credential_username_for_owner(owner, credential_name)
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc
    try:
        return keyring.get_password(_KEYRING_SERVICE, username)
    except Exception:
        return None


def set_api_key(provider: str, value: str) -> None:
    """Store an API key for ``provider`` in the system keyring."""
    if not value:
        raise SettingsError("api key value cannot be empty")
    try:
        from orchestrator import system_protection as _sp
    except ImportError:  # pragma: no cover
        import system_protection as _sp
    username = _provider_username(provider)
    _sp.require_active_execution(
        "credential_store", f"credential:ora/{username}",
    )
    _set_api_key_storage(provider, value)


def _set_api_key_storage(provider: str, value: str) -> None:
    """Keyring adapter; authority must be enforced by the public caller."""
    if not value:
        raise SettingsError("api key value cannot be empty")
    import keyring  # pulled lazily so tests can stub via sys.modules
    keyring.set_password(_KEYRING_SERVICE, _provider_username(provider), value)


def delete_api_key(provider: str) -> None:
    """Remove an API key for ``provider`` from the keyring (if present)."""
    try:
        from orchestrator import system_protection as _sp
    except ImportError:  # pragma: no cover
        import system_protection as _sp
    username = _provider_username(provider)
    _sp.require_active_execution(
        "credential_delete", f"credential:ora/{username}",
    )
    _delete_api_key_storage(provider)


def _delete_api_key_storage(provider: str) -> None:
    """Keyring deletion adapter; authority is enforced by the public caller."""
    import keyring
    username = _provider_username(provider)
    try:
        keyring.delete_password(_KEYRING_SERVICE, username)
    except Exception as exc:
        # Backends disagree on the not-found exception type. Treat it as
        # already absent only when a strict post-read proves absence; every
        # other backend failure propagates.
        try:
            remaining = keyring.get_password(_KEYRING_SERVICE, username)
        except Exception as verify_exc:
            raise SettingsError(
                f"credential deletion could not be verified: {verify_exc}"
            ) from exc
        if remaining is None:
            return
        raise SettingsError("credential deletion failed; credential remains present") from exc
    try:
        remaining = keyring.get_password(_KEYRING_SERVICE, username)
    except Exception as exc:
        raise SettingsError(
            f"credential deletion could not be verified: {exc}"
        ) from exc
    if remaining is not None:
        raise SettingsError("credential deletion failed; credential remains present")


def api_key_present(provider: str) -> bool:
    """Return True if ``provider``'s key is set in the keyring (no value leak)."""
    import keyring
    try:
        return bool(
            keyring.get_password(_KEYRING_SERVICE, _provider_username(provider))
        )
    except Exception:
        return False


_SUBSCRIPTION_TRANSPORTS = {
    "anthropic": "Claude subscription via the local Claude Code CLI",
    "openai": "ChatGPT subscription via the bundled Codex runtime",
}


def _subscription_transport(provider_id: str) -> str | None:
    """The subscription transport this provider also runs on, if any.

    Only two providers have one, and only OpenAI's has to be discovered at
    runtime — ``is_configured`` is a directory check, not a network call, so
    this stays cheap enough for a settings render. Returns None when the
    provider has no subscription route or it was never connected, which is
    the honest answer: the key is doing all the work.
    """
    label = _SUBSCRIPTION_TRANSPORTS.get(provider_id)
    if not label:
        return None
    if provider_id == "openai":
        try:
            try:
                from . import codex_subscription
            except ImportError:
                import codex_subscription  # type: ignore
            if not codex_subscription.is_configured():
                return None
        except Exception:
            return None
    elif provider_id == "anthropic":
        import shutil
        if not shutil.which("claude"):
            return None
    return label


def list_api_key_status() -> list[dict]:
    """Return enriched per-provider rows for the settings panel.

    Each row carries the registry metadata (label, category, signup /
    console URLs, key-format hint, essential / auto-activate / direct /
    verifiable flags, note) plus the live ``present`` boolean. Secrets are
    never included — only whether a key exists. The panel renders the
    two-column grouped UI entirely from these rows.
    """
    rows = []
    for row in _registry.ui_rows():
        row = dict(row)
        row["present"] = api_key_present(row["provider"])
        row["subscription_transport"] = _subscription_transport(row["provider"])
        rows.append(row)
    return rows


def group_order() -> list[list]:
    """[[category, group_label], …] in render order, for the panel."""
    return [list(pair) for pair in _registry.GROUP_ORDER]


__all__ = [
    "DEFAULTS",
    "SettingsError",
    "load_settings",
    "save_settings",
    "reset_settings",
    "get_setting",
    "provider_ids",
    "set_api_key",
    "delete_api_key",
    "api_key_present",
    "feature_credential",
    "list_api_key_status",
    "group_order",
]
