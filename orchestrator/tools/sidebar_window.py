"""
sidebar_window.py — Sidebar Five-Turn Rolling Window (Phase 13.1)

Implements a rolling window of five turn pairs maximum for sidebar
conversations. After each exchange, if the history exceeds five pairs,
the oldest pair is removed. History lives only in process memory —
never written to disk or ChromaDB. A caller may clear a named window;
otherwise it is discarded when the server process exits.

Why: Sidebar is currently fully stateless (single message only). Five
turns provides minimal conversational continuity for multi-step quick
queries without permanent storage overhead.

Usage:
    from orchestrator.tools.sidebar_window import SidebarWindow
    window = SidebarWindow()
    window.add_exchange(user_msg, assistant_msg)
    history = window.get_history()  # returns list of message dicts
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import threading


# Provisional tuning constant: recalibrate after real Aside usage.
MAX_TURNS = 5


@dataclass
class SidebarWindow:
    """
    Five-turn rolling window for sidebar conversations.

    In-memory only — never persisted to disk or ChromaDB.
    """
    _turns: list[tuple[str, str]] = field(default_factory=list)
    max_turns: int = MAX_TURNS
    _lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False)

    @contextmanager
    def transaction(self):
        """Serialize one history-read/model-call/history-write exchange."""
        with self._lock:
            yield self

    def add_exchange(self, user_message: str, assistant_message: str):
        """Add a turn pair. Evicts oldest if at capacity."""
        with self._lock:
            self._turns.append((user_message, assistant_message))
            if len(self._turns) > self.max_turns:
                self._turns = self._turns[-self.max_turns:]

    def get_history(self) -> list[dict]:
        """Return history as a list of message dicts for model context."""
        with self._lock:
            messages = []
            for user_msg, asst_msg in self._turns:
                messages.append({"role": "user", "content": user_msg})
                messages.append({"role": "assistant", "content": asst_msg})
            return messages

    def get_turn_count(self) -> int:
        """Return the number of turn pairs in the window."""
        with self._lock:
            return len(self._turns)

    def clear(self):
        """Clear all history for this named window."""
        with self._lock:
            self._turns.clear()

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._turns) == 0


# Global sidebar windows, keyed by panel_id
_sidebar_windows: dict[str, SidebarWindow] = {}
_sidebar_windows_lock = threading.RLock()


def get_sidebar_window(panel_id: str = "sidebar") -> SidebarWindow:
    """Get or create a sidebar window for a panel."""
    with _sidebar_windows_lock:
        if panel_id not in _sidebar_windows:
            _sidebar_windows[panel_id] = SidebarWindow()
        return _sidebar_windows[panel_id]


def clear_sidebar_window(panel_id: str = "sidebar"):
    """Clear a sidebar window (on session end or panel close)."""
    with _sidebar_windows_lock:
        window = _sidebar_windows.get(panel_id)
    if window is not None:
        window.clear()


def clear_all_sidebar_windows():
    """Clear all sidebar windows (on server restart)."""
    with _sidebar_windows_lock:
        _sidebar_windows.clear()
