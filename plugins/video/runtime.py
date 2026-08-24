"""Configured Ora boundary for the video plugin's backend modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_context: Any = None


def configure(context: Any) -> None:
    global _context
    _context = context


def context() -> Any:
    if _context is None:
        raise RuntimeError("video plugin runtime is not configured")
    return _context


def ora_home() -> Path:
    return Path(context().ora_home)


def plugin_root() -> Path:
    return Path(context().plugin_root)


def safe_owned_subdir(base: str | Path, *segments: str, create: bool = False) -> Path:
    return context().safe_owned_subdir(base, *segments, create=create)


def atomic_write_text(path: str | Path, text: str, *, mode: int = 0o600) -> None:
    context().atomic_write_text(path, text, mode=mode)


def get_setting(path: str, default: Any = None) -> Any:
    return context().get_setting(path, default)


def get_conversation_tag(conversation_id: str) -> str:
    return str(context().get_conversation_tag(conversation_id) or "")


def record_tool_event(event: dict) -> None:
    context().record_tool_event(event)


def tool_manifest_axes(name: str) -> dict:
    return dict(context().tool_manifest_axes(name))
